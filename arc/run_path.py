"""Guarded launcher for paid ARC runs: Gemini 3.8 Flash in the patched ARC harness, played
online through ARC's scorecard. One invocation is one run.

    uv run --env-file .env python -m arc.run_path --approved-block <block> \\
        --experiment arc_pilot --config S0 --game ft09 --seed 1 --planned-usd 15 \\
        --max-actions 50
    uv run --env-file .env python -m arc.run_path --approved-block <block> \\
        --experiment gemini_probe --acceptance-check --planned-usd 1

It spends money only after every check below passes, in this order:
1. The arguments make sense (`make_plan`): a plain block name, a known profile (S0, S1, S2,
   S4), a path game (FT09, SB26, R11L, CD82; never a held-out game), truncation only for
   the pilot, the experiment's mode, the price table valid today, the frozen profile asks
   for the standard tier, and GOOGLE_API_KEY (plus ARC_API_KEY for a game) is set. Keys
   are never printed.
2. No other paid run holds the lock (`common.paidlock`): one paid run at a time. The lock
   is taken before the spend checks, so two runs cannot both pass them. A run that could
   not write its costs row leaves the lock held, and the last paid run's costs row must be
   in this checkout's results/costs.csv (each checkout has its own ledger).
3. The paid guard (`common.approval.require_paid_approval`): PERSISTGYM_ALLOW_PAID=1, the
   researcher's line `approved_block: <name> | experiments: <list> | max_usd: <n>` on
   origin/main (fetched now), HEAD and the working tree, the experiment listed, block spend
   + planned spend <= max_usd, and phase headroom.
4. PREREG.md frozen (`common.prereg.prereg_state`, the rule draw_games.py uses) and the
   same blob in HEAD and on origin/main (read after the guard's fetch). Steps 2-4 are
   `common.approval.require_paid_run`, which the PersistGym launcher (harnesses/cli.py)
   runs too.
5. The patched harness matches arc/config_freeze.json: the patch files' SHA-256, the patched
   commit and tree, and each resolved profile's config hash.

Then it runs arc/run_path_inner.py in the patched harness with a sanitized environment
(only the needed keys added), in a short scratch directory, and whatever happens:
* copies the harness files to results/raw/<experiment>/<run_id>/ (gitignored);
* appends ONE results/costs.csv row tagged `approved_block=<name>;`, with the list and
  billed estimates priced from the run's per-step usage (arc/pricing.py);
* writes results/<experiment>/<run_id>/meta.json via common.runmeta.

The harness cost guard (patch 0010, ARC's no-cache list accounting) stops a run at
`--planned-usd` for pilots and probes, and at D22's $120 for counted runs (which therefore
need `--planned-usd` >= 120). Since list >= billed, a run's spend exceeds its planned spend
by at most one model call. Pilot outcomes stay in results/raw/ only (pilot blinding,
PREREG §11): the committed meta.json and costs.csv row of an `arc_pilot` run show errors,
tokens (no reasoning tokens), latency and cost, not how the game went.

Exit codes: 0 the run (or check) completed; 1 it ran but failed or was interrupted;
2 refused before spending.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arc import apply_patches as ap
from arc import config_hash as freeze
from arc import pricing
from arc import run_path_inner as inner
from common import approval, costs, paidlock, runmeta
from common.approval import MAIN, PaidCallsNotAllowed, RemoteRef

PATH_GAMES = ("ft09", "sb26", "r11l", "cd82")      # D14: the path (dev) games
HELD_OUT_GAMES = ("sp80", "vc33", "tn36")          # D14: never played by this launcher yet
PLAY_EXPERIMENTS = {"arc_pilot": "M0", "arc_path": "M1"}   # experiment -> default milestone
ACCEPT_EXPERIMENTS = {"gemini_probe": "M0"}
BLINDED_EXPERIMENTS = frozenset({"arc_pilot"})     # PREREG §11 pilot blinding
COUNTED_RUN_COST_GUARD_USD = 120.0                 # D22: harness cost guard, list accounting
NORMAL_ENDINGS = frozenset({"GAME_WIN", "ACTION_BUDGET"})
BLINDED_ENDING = "NORMAL_ENDING_BLINDED"
WITHHELD_NOTE = "pilot blinding (PREREG §11): reasoning tokens and game outcome withheld"
WORK_NAME = "paid"
INTERRUPT_GRACE_S = 120.0
ARC_KEY = "ARC_API_KEY"
GAME_RE = re.compile(r"(?P<base>[a-z0-9]{4})(?:-(?P<version>[0-9a-f]{4,64}))?")
RESULTS = runmeta.REPO_ROOT / "results"


class Refused(RuntimeError):
    pass


@dataclass(frozen=True)
class Paths:
    """Where the launcher reads and writes; tests point these at temporary copies."""
    repo: Path = runmeta.REPO_ROOT
    costs: Path = costs.COSTS_CSV
    results: Path = RESULTS
    raw: Path = RESULTS / "raw"
    freeze: Path = freeze.FREEZE_PATH
    lock: Path | None = None             # default: the git common directory
    remote: RemoteRef = MAIN


@dataclass(frozen=True)
class Plan:
    experiment: str
    approved_block: str
    planned_usd: float
    milestone: str
    run_id: str
    labels: tuple[str, ...]              # profiles: one for a game run, 1-4 for the check
    acceptance: bool
    game: str | None = None
    seed: int | None = None
    rerun_of: str | None = None
    max_actions: int | None = None
    after_summary_turns: int | None = None
    cost_cap_usd: float = 0.0            # the harness guard (list accounting)
    model: str = ""
    key_names: tuple[str, ...] = ()
    profiles: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    @property
    def blinded(self) -> bool:
        return self.experiment in BLINDED_EXPERIMENTS

    @property
    def cell(self) -> str:
        return "+".join(self.labels)

    def describe(self) -> str:
        if self.acceptance:
            return f"{self.experiment}: acceptance check of {self.cell}"
        return f"{self.experiment}: {self.cell} on {self.game}, seed {self.seed}"


@dataclass(frozen=True)
class Harness:
    worktree: Path
    commit: str
    tree: str
    series_sha256: str


# ── Arguments and plan ─────────────────────────────────────────────────


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--approved-block", required=True,
                   help="the researcher-approved block (its approval line lists the experiment)")
    p.add_argument("--experiment", required=True,
                   choices=sorted({*PLAY_EXPERIMENTS, *ACCEPT_EXPERIMENTS}))
    p.add_argument("--planned-usd", required=True, type=float,
                   help="planned spend of this run in USD; the run stops near it")
    p.add_argument("--acceptance-check", action="store_true",
                   help="one minimal request per profile, no game (experiment gemini_probe)")
    p.add_argument("--config", help="profile label for a game run: S0, S1, S2 or S4")
    p.add_argument("--configs", default=",".join(freeze.PROFILES),
                   help="profiles for --acceptance-check (default: all four)")
    p.add_argument("--game", help="path game, e.g. ft09 or ft09-<version>")
    p.add_argument("--seed", type=int, help="replicate label (not sent to the model)")
    p.add_argument("--rerun-of", help="run_id this run re-runs (PREREG §7.5)")
    p.add_argument("--max-actions", type=int, help="arc_pilot only: stop after N actions")
    p.add_argument("--after-summary-turns", type=int,
                   help="arc_pilot only: stop M turns after the first harness summary")
    p.add_argument("--milestone", help="costs.csv milestone (default by experiment)")
    p.add_argument("--keep-worktree", action="store_true",
                   help="keep the patched harness in arc/.work/paid")
    return p.parse_args(argv)


def _label(value: str) -> str:
    label = value.strip().upper()
    if label not in freeze.PROFILES:
        raise Refused(f"unknown profile {value!r}; use one of {', '.join(freeze.PROFILES)}")
    return label


def make_plan(args: argparse.Namespace, record: Mapping[str, Any], *,
              today: date | None = None, environ: Mapping[str, str] | None = None,
              now: datetime | None = None) -> Plan:
    """Check the arguments against the rules above; no network, no spend."""
    environ = os.environ if environ is None else environ
    today = today or datetime.now(UTC).date()
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    exp = args.experiment
    # Exactly a block name: the guard strips whitespace before it looks up the approval,
    # but the costs row is tagged with this string, so " 1-pilots" would pass the guard
    # and then be missing from the block's spend.
    if not approval.NAME_RE.fullmatch(args.approved_block):
        raise Refused(f"--approved-block {args.approved_block!r} is not a block name "
                      "([A-Za-z0-9._-]+, no spaces)")
    if not (math.isfinite(args.planned_usd) and args.planned_usd > 0):
        raise Refused("--planned-usd must be a positive, finite number of dollars")
    truncating = args.max_actions is not None or args.after_summary_turns is not None
    if args.acceptance_check != (exp in ACCEPT_EXPERIMENTS):
        raise Refused("--acceptance-check goes with --experiment gemini_probe, and "
                      "gemini_probe only with --acceptance-check")
    if args.acceptance_check:
        if args.config or args.game or args.seed is not None or truncating or args.rerun_of:
            raise Refused("--acceptance-check plays no game: drop --config, --game, --seed, "
                          "--rerun-of and the truncation options")
        labels = tuple(dict.fromkeys(_label(x) for x in args.configs.split(",") if x.strip()))
        if not labels:
            raise Refused("--configs names no profile")
        run_id = f"{stamp}-accept"
        cap = args.planned_usd
        game = seed = None
    else:
        if not args.config or not args.game or args.seed is None:
            raise Refused("a game run needs --config, --game and --seed")
        labels = (_label(args.config),)
        m = GAME_RE.fullmatch(args.game.strip().lower())
        if m is None:
            raise Refused(f"--game {args.game!r} is not a game ID like ft09 or ft09-<version>")
        game = m.group(0)
        if m["base"] not in PATH_GAMES:
            held = m["base"] in HELD_OUT_GAMES
            raise Refused(f"{m['base']} is {'a held-out game' if held else 'not a path game'}; "
                          f"{exp} runs only on {', '.join(PATH_GAMES)} (D14; no pilot on a "
                          "held-out game)")
        if args.seed < 0:
            raise Refused("--seed must be >= 0")
        seed = args.seed
        for name, value in (("--max-actions", args.max_actions),
                            ("--after-summary-turns", args.after_summary_turns)):
            if value is not None and value < 1:
                raise Refused(f"{name} must be >= 1")
        if exp == "arc_path":
            if truncating:
                raise Refused("counted arc_path runs are never truncated; --max-actions and "
                              "--after-summary-turns are for the arc_pilot experiment")
            if args.planned_usd < COUNTED_RUN_COST_GUARD_USD:
                raise Refused(f"a counted run can spend up to the D22 cost guard of "
                              f"${COUNTED_RUN_COST_GUARD_USD:.0f} (list), so --planned-usd "
                              f"must be at least that")
            cap = COUNTED_RUN_COST_GUARD_USD
        else:
            if args.after_summary_turns is not None and args.max_actions is None:
                raise Refused("--after-summary-turns needs --max-actions as a hard limit")
            cap = args.planned_usd
        run_id = f"{stamp}-{labels[0]}-{m['base']}-s{seed}"
    if args.rerun_of is not None:
        try:
            plain_name(args.rerun_of)
        except Refused:
            raise Refused("--rerun-of must be a run_id") from None
    profiles = record.get("profiles") or {}
    missing = [lb for lb in labels if lb not in profiles]
    if missing:
        raise Refused(f"the freeze record has no profile {missing}")
    models = {profiles[lb]["config"]["request"]["model"] for lb in labels}
    if len(models) != 1:
        raise Refused(f"the profiles request different models: {sorted(models)}")
    (model,) = models
    key_names = []
    for lb in labels:
        cfg = profiles[lb]["config"]
        tier = cfg["request"].get("service_tier")
        if tier != pricing.TIER:
            raise Refused(f"{lb} requests service tier {tier!r}, not {pricing.TIER!r} (D21)")
        try:
            price = pricing.price_for(model, tier, on=today)
        except pricing.PriceError as e:
            raise Refused(str(e)) from None
        if (cfg.get("pricing") or {}) != {"input": price.input, "output": price.output}:
            raise Refused(f"{lb}'s configured pricing {cfg.get('pricing')} differs from "
                          f"arc/pricing.py ({price.input}/{price.output})")
        key_names.append(cfg["client"].get("api_key_env", "GOOGLE_API_KEY"))
    if not args.acceptance_check:
        key_names.append(ARC_KEY)
    key_names = list(dict.fromkeys(key_names))
    unset = [k for k in key_names if not (environ.get(k) or "").strip()]
    if unset:
        raise Refused(f"{', '.join(unset)} not set; run with `uv run --env-file .env ...`")
    milestone = args.milestone or {**PLAY_EXPERIMENTS, **ACCEPT_EXPERIMENTS}[exp]
    return Plan(experiment=exp, approved_block=args.approved_block,
                planned_usd=float(args.planned_usd), milestone=milestone, run_id=run_id,
                labels=labels, acceptance=args.acceptance_check, game=game, seed=seed,
                rerun_of=args.rerun_of, max_actions=args.max_actions,
                after_summary_turns=args.after_summary_turns, cost_cap_usd=cap, model=model,
                key_names=tuple(key_names), profiles={lb: profiles[lb] for lb in labels})


def plain_name(name: str) -> str:
    """`name` must be one plain path component (it becomes a folder name)."""
    if (not name or name in (".", "..") or name != name.strip()
            or any(ch in name for ch in '/\\:\0')):
        raise Refused(f"{name!r} is not a plain folder name")
    return name


# ── Checks that need git ───────────────────────────────────────────────


# PREREG.md in HEAD, the blob on origin/main, is frozen (the rule of common/prereg.py, which
# draw_games.py uses too). Kept under this name for the launcher's callers and tests.
prereg_not_frozen = approval.prereg_not_frozen


def check_paid(plan: Plan, paths: Paths, lock: paidlock.HeldLock) -> approval.PaidApproval:
    """Steps 2-4 of the module docstring, shared with the PersistGym launcher
    (`common.approval.require_paid_run`): the lock is held by this run, this checkout's
    costs.csv holds the last paid run's row, the paid guard, and a frozen, merged PREREG."""
    return approval.require_paid_run(
        lock=lock, approved_block=plan.approved_block, experiment=plan.experiment,
        planned_usd=plan.planned_usd, costs_path=paths.costs, repo=paths.repo,
        remote=paths.remote)


# ── Patched harness ────────────────────────────────────────────────────


def prepare_harness(plan: Plan, record: Mapping[str, Any], *, name: str = WORK_NAME) -> Harness:
    """Build the patched harness in arc/.work/<name> and check it against the freeze record."""
    env = ap.sanitized_env()
    ap.check_pin(env)
    patches = ap.patch_files()
    problems = freeze.record_problems(record, patches)
    if problems:
        raise Refused("arc/config_freeze.json does not match arc/patches: "
                      + "; ".join(problems) + ". Regenerate it (`uv run python -m "
                      "arc.config_hash`) and get it merged before a paid run")
    worktree = ap.WORK_DIR / name
    try:
        ap.create_worktree(worktree, env)
        ap.apply_series(worktree, patches, env)
        commit = ap._git(["rev-parse", "HEAD"], worktree, env)
        tree = ap._git(["rev-parse", "HEAD^{tree}"], worktree, env)
        if (commit, tree) != (record.get("patched_commit"), record.get("patched_tree")):
            raise Refused(f"the patched harness is commit {commit} / tree {tree}, not the "
                          f"frozen {record.get('patched_commit')} / "
                          f"{record.get('patched_tree')}")
        ap.sync_environment(worktree, env)
        ids = [plan.profiles[lb]["config_id"] for lb in plan.labels]
        resolved = freeze.resolve_profiles(worktree, env, ids)
        for lb in plan.labels:
            got = runmeta.config_hash(resolved.get(plan.profiles[lb]["config_id"]))
            if got != plan.profiles[lb]["sha256"]:
                raise Refused(f"{lb} resolves to config hash {got}, not the frozen "
                              f"{plan.profiles[lb]['sha256']}")
    except BaseException:
        try:
            ap.remove_worktree(worktree, env)
        except ap.PatchError as e:
            print(f"warning: could not remove {worktree}: {e}", file=sys.stderr)
        raise
    return Harness(worktree, commit, tree, ap.series_digest(patches))


def inner_env(plan: Plan, harness: Harness, scratch: Path,
              environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """The inner process's environment: sanitized (no keys, no provider or ARC settings),
    then only the keys this run needs."""
    environ = os.environ if environ is None else environ
    env = ap.sanitized_env(environ)
    for name in ("OPERATION_MODE", "ENVIRONMENTS_DIR"):
        env.pop(name, None)
    env.update({
        "PYTHONPATH": os.pathsep.join([str(harness.worktree), str(ap.ARC_DIR)]),
        "PYTHONUTF8": "1",
        "ARC_HARNESS_COMMIT_SHA": harness.commit,
        "RECORDINGS_DIR": str(scratch / "rec"),
    })
    for name in plan.key_names:
        env[name] = environ[name]
    return env


def inner_command(plan: Plan, harness: Harness, out: Path) -> list[str]:
    base = ["uv", "run", "--no-sync", "--project", str(harness.worktree), "python",
            str(freeze.INNER)]
    if plan.acceptance:
        hashes = {plan.profiles[lb]["config_id"]: plan.profiles[lb]["sha256"]
                  for lb in plan.labels}
        return [*base, "accept", "--configs",
                ",".join(plan.profiles[lb]["config_id"] for lb in plan.labels),
                "--out", str(out), "--expect-config-hashes", json.dumps(hashes),
                "--cost-cap-usd", repr(plan.cost_cap_usd)]
    (lb,) = plan.labels
    tags = ["persistgym", plan.experiment, lb, f"seed-{plan.seed}", plan.run_id]
    command = [*base, "play", "--config", plan.profiles[lb]["config_id"], "--game", plan.game,
               "--out", str(out), "--expect-config-hash", plan.profiles[lb]["sha256"],
               "--cost-cap-usd", repr(plan.cost_cap_usd), "--tags", ",".join(tags)]
    if plan.max_actions is not None:
        command += ["--max-actions", str(plan.max_actions)]
    if plan.after_summary_turns is not None:
        command += ["--after-summary-turns", str(plan.after_summary_turns)]
    return command


def run_inner(command: list[str], cwd: Path, env: Mapping[str, str], *,
              grace_s: float = INTERRUPT_GRACE_S) -> int:
    """Run the inner process with live output. On Ctrl+C (which reaches the child too) give
    it `grace_s` to close the ARC scorecard before killing it."""
    print(f"$ {' '.join(command)}  (in {cwd})", flush=True)
    proc = subprocess.Popen(command, cwd=cwd, env=dict(env))
    try:
        return proc.wait()
    except KeyboardInterrupt:
        print(f"interrupted: waiting up to {grace_s:.0f} s for the run to close its "
              "scorecard", file=sys.stderr, flush=True)
        try:
            return proc.wait(timeout=grace_s)
        except subprocess.TimeoutExpired:
            return kill_tree(proc)
        except BaseException:  # a second Ctrl+C: stop the run before accounting for it
            kill_tree(proc)
            raise


def kill_tree(proc: subprocess.Popen) -> int:
    """Kill the inner process and everything it started. The inner process is `uv run`,
    which starts python as a child; on Windows, killing uv alone leaves that python running
    (checked 2026-10-01), and it would go on spending after the launcher has accounted for
    the run and released the lock. `taskkill /T` ends the whole tree."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True,
                       check=False)
    proc.kill()
    return proc.wait()


# ── Accounting ─────────────────────────────────────────────────────────


def collect_outputs(scratch: Path, raw_dir: Path) -> None:
    """Copy the inner process's files and the harness run directory into raw_dir (under
    short names: harness/ and recording.jsonl)."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    out = scratch / "out"
    if out.is_dir():
        shutil.copytree(out, raw_dir, dirs_exist_ok=True)
    run_dirs = sorted(p.parent for p in (scratch / "recordings").glob("*/run_meta.json"))
    if len(run_dirs) == 1:
        shutil.copytree(run_dirs[0], raw_dir / "harness", dirs_exist_ok=True)
    elif run_dirs:
        for i, d in enumerate(run_dirs):
            shutil.copytree(d, raw_dir / f"harness_{i}", dirs_exist_ok=True)
    recordings = sorted((scratch / "rec").glob("*.jsonl"))
    for i, rec in enumerate(recordings):
        shutil.copyfile(rec, raw_dir / ("recording.jsonl" if len(recordings) == 1
                                        else f"recording_{i}.jsonl"))


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _calls(raw_dir: Path) -> list[dict]:
    path = raw_dir / inner.CALLS_FILE
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _latency(calls: list[dict]) -> dict[str, Any]:
    ok = sorted(float(c["duration_s"]) for c in calls
                if isinstance(c.get("status"), int) and 200 <= c["status"] < 300)
    if not ok:
        return {"n_ok_calls": 0, "median_s": None, "p90_s": None, "max_s": None}
    return {"n_ok_calls": len(ok), "median_s": round(statistics.median(ok), 3),
            "p90_s": round(ok[max(math.ceil(0.9 * len(ok)) - 1, 0)], 3),
            "max_s": round(ok[-1], 3)}


@dataclass
class Accounting:
    usage: pricing.Usage
    cost_list: float
    cost_billed: float
    n_calls: int
    n_http_requests: int
    latency: dict[str, Any]
    models_returned: list[str]
    tiers_served: dict[str, int]
    exit_reason: str
    agent_exit_reason: str | None
    detail: dict[str, Any]           # committed for every experiment
    outcome: dict[str, Any]          # committed unless blinded
    unrecorded_usage: pricing.Usage | None = None

    @property
    def any_call(self) -> bool:
        return self.n_http_requests > 0 or self.usage != pricing.Usage()


def account_game(plan: Plan, raw_dir: Path, price: pricing.Price) -> Accounting:
    harness_dir = raw_dir / "harness"
    run_meta = _read_json(harness_dir / "run_meta.json") or {}
    result = _read_json(raw_dir / inner.RESULT_FILE) or {}
    steps = [_read_json(p) or {} for p in sorted(harness_dir.glob("step_*.json"))]
    compactions = [_read_json(p) or {} for p in sorted(harness_dir.glob("compaction_*.json"))]
    recorded = sum((pricing.Usage.from_record(r.get("usage")) for r in [*steps, *compactions]),
                   pricing.Usage())
    total = pricing.Usage.from_record(run_meta.get("total_usage"))
    unrecorded = total.minus(recorded)
    usage = recorded + unrecorded
    listed, billed = pricing.cost_usd(usage, price)
    calls = _calls(raw_dir)
    model_calls = [r for r in [*steps, *compactions] if r.get("usage")]
    n_ok = sum(1 for c in calls if isinstance(c.get("status"), int) and 200 <= c["status"] < 300)
    n_calls = n_ok if calls else (len(model_calls) + sum(int(s.get("retries") or 0)
                                                        for s in steps))
    tiers = Counter(str(s["service_tier"]) for s in steps if s.get("service_tier"))
    runtime = run_meta.get("runtime") or {}
    exit_reason = run_meta.get("exit_reason") or result.get("exit_reason") or "UNKNOWN"
    detail = {
        "config_id": plan.profiles[plan.labels[0]]["config_id"],
        "game_requested": plan.game,
        "arc_environment": run_meta.get("arc_environment"),
        "requested_service_tier": run_meta.get("requested_service_tier"),
        "service_tiers_served": dict(tiers),
        "reported_models": run_meta.get("reported_models") or [],
        "n_compactions": len(compactions),
        "context_trims": runtime.get("context_trims"),
        "transport_retry": run_meta.get("transport_retry"),
        "cost_guard": run_meta.get("cost_guard"),
        "wall_clock_s": run_meta.get("duration_seconds"),
        "inner_error": result.get("error"),
        "interrupted": bool(result.get("interrupted")),
        "truncation_limits": {"max_actions": plan.max_actions,
                              "after_summary_turns": plan.after_summary_turns},
        "unrecorded_usage": vars(unrecorded) if unrecorded != pricing.Usage() else None,
    }
    outcome = {
        "scorecard_id": result.get("card_id"),
        "game_id_served": result.get("game_id_served"),
        "n_steps": len(steps),
        "action_counter": result.get("action_counter"),
        "truncation": result.get("truncation"),
        "outcome": run_meta.get("outcome"),
    }
    return Accounting(usage, listed, billed, n_calls, len(calls), _latency(calls),
                      list(run_meta.get("reported_models") or []), dict(tiers), exit_reason,
                      run_meta.get("agent_exit_reason"), detail, outcome,
                      unrecorded if unrecorded != pricing.Usage() else None)


def account_acceptance(plan: Plan, raw_dir: Path, price: pricing.Price) -> Accounting:
    records = _read_json(raw_dir / inner.ACCEPT_FILE) or []
    usage = sum((pricing.Usage.from_record(r.get("usage")) for r in records), pricing.Usage())
    listed, billed = pricing.cost_usd(usage, price)
    calls = _calls(raw_dir)
    n_ok = sum(1 for c in calls if isinstance(c.get("status"), int) and 200 <= c["status"] < 300)
    tiers = Counter(str(r["service_tier"]) for r in records if r.get("service_tier"))
    models = list(dict.fromkeys(r["reported_model"] for r in records
                                if r.get("reported_model")))
    checked = [r for r in records if "accepted" in r]
    all_ok = len(checked) == len(plan.labels) and all(r["accepted"] for r in checked)
    by_id = {plan.profiles[lb]["config_id"]: lb for lb in plan.labels}
    per_config = {by_id.get(r.get("config_id"), r.get("config_id")): {
        k: r.get(k) for k in ("accepted", "error", "skipped", "reported_model", "service_tier",
                              "latency_s", "request_settings")} for r in records}
    return Accounting(usage, listed, billed, n_ok if calls else len(checked), len(calls),
                      _latency(calls), models, dict(tiers),
                      "ALL_ACCEPTED" if all_ok else "NOT_ALL_ACCEPTED", None,
                      {"acceptance": per_config}, {})


def blind_ending(reason: str | None) -> str | None:
    return BLINDED_ENDING if reason in NORMAL_ENDINGS else reason


def costs_row(plan: Plan, acct: Accounting, *, git: dict) -> dict[str, Any]:
    tiers_requested = sorted({plan.profiles[lb]["config"]["request"]["service_tier"]
                              for lb in plan.labels})
    exit_reason = blind_ending(acct.exit_reason) if plan.blinded else acct.exit_reason
    notes = [f"{approval.spend_tag(plan.approved_block)} arc_run={plan.describe()}",
             f"exit_reason={exit_reason}", f"git_dirty={git['git_dirty']}"]
    if plan.rerun_of:
        notes.append(f"rerun_of={plan.rerun_of}")
    if acct.unrecorded_usage is not None:
        notes.append("includes usage recorded only in run_meta total_usage")
    if any(t != pricing.TIER for t in acct.tiers_served):
        notes.append(f"served tier differs from {pricing.TIER} on some calls; priced at "
                     f"{pricing.TIER}")
    if plan.blinded:
        notes.append(WITHHELD_NOTE)
    latency = acct.latency.get("median_s")
    return {
        "timestamp_utc": runmeta.utc_now(), "run_id": plan.run_id,
        "milestone": plan.milestone, "experiment": plan.experiment,
        "cell_or_config": plan.cell, "model_requested": plan.model,
        "model_returned": ";".join(acct.models_returned), "provider": "google",
        "api": "interactions", "service_tier": ";".join(tiers_requested),
        "service_tier_served": ";".join(sorted(acct.tiers_served)),
        "n_calls": acct.n_calls, "input_tokens": acct.usage.prompt_tokens,
        "cached_input_tokens": acct.usage.cached_tokens, "cache_write_tokens": "",
        "output_tokens": acct.usage.completion_tokens,
        "reasoning_tokens": "" if plan.blinded else acct.usage.reasoning_tokens,
        "latency_s": "" if latency is None else f"{latency:.3f}",
        "cost_usd_list": f"{acct.cost_list:.6f}",
        "cost_usd_billed_est": f"{acct.cost_billed:.6f}",
        "price_source_date": pricing.PRICE_SOURCE_DATE, "git_commit": git["git_commit"],
        "notes": "; ".join(notes),
    }


def write_meta(plan: Plan, acct: Accounting, harness: Harness, granted: approval.PaidApproval,
               *, out_dir: Path, raw_dir: Path, started: str, row: dict | None,
               record: Mapping[str, Any]) -> Path:
    if plan.acceptance:
        config: Any = {lb: plan.profiles[lb]["config"] for lb in plan.labels}
    else:
        config = plan.profiles[plan.labels[0]]["config"]
    tokens = {"input_tokens": acct.usage.prompt_tokens,
              "cached_input_tokens": acct.usage.cached_tokens,
              "output_tokens": acct.usage.completion_tokens,
              "reasoning_tokens": None if plan.blinded else acct.usage.reasoning_tokens}
    exit_reason, agent_exit = acct.exit_reason, acct.agent_exit_reason
    extra: dict[str, Any] = {}
    if plan.blinded:
        exit_reason, agent_exit = blind_ending(exit_reason), blind_ending(agent_exit)
        extra["blinding"] = {"rule": WITHHELD_NOTE,
                             "raw_outcome_path": _rel(raw_dir)}
    else:
        extra["outcome"] = acct.outcome
    return runmeta.write_meta(
        out_dir, experiment=plan.experiment, run_id=plan.run_id, cell_or_config=plan.cell,
        config=config, model_requested=plan.model, model_returned=acct.models_returned,
        reasoning_effort={"thinking_level": "high"}, reasoning_context_requested=None,
        reasoning_context_echoed=None, template_id=plan.game,
        repeat_index=plan.seed, seeds={"replicate_seed": plan.seed,
                                       "note": "labels the replicate; not sent to the model"},
        started_utc=started, finished_utc=runmeta.utc_now(), exit_reason=exit_reason,
        agent_exit_reason=agent_exit, tokens=tokens,
        cost_usd={"list": round(acct.cost_list, 6), "billed_est": round(acct.cost_billed, 6),
                  "basis": "billed estimate primary (D23); list = ARC's no-cache accounting",
                  "price_source": pricing.PRICE_SOURCE_URL,
                  "price_source_date": pricing.PRICE_SOURCE_DATE,
                  "costs_csv_row_appended": row is not None},
        raw_transcript_path=_rel(raw_dir),
        config_freeze={"labels": list(plan.labels),
                       "sha256": {lb: plan.profiles[lb]["sha256"] for lb in plan.labels},
                       "patch_series_sha256": harness.series_sha256,
                       "patched_commit": harness.commit, "patched_tree": harness.tree,
                       "pinned_commit": record["upstream"]["pinned_commit"]},
        service_tier={"requested": pricing.TIER, "served": acct.tiers_served},
        latency=acct.latency, n_calls=acct.n_calls, n_http_requests=acct.n_http_requests,
        approved_block=plan.approved_block, planned_usd=plan.planned_usd, phase=granted.phase,
        cost_cap_usd=plan.cost_cap_usd, rerun_of=plan.rerun_of, paid=True, **acct.detail,
        **extra)


def redact_keys(path: Path, values: Sequence[str]) -> bool:
    """Replace any key value found in a file meant to be committed. True if one was found.
    A last line of defence: no key should ever reach these files."""
    text = path.read_text(encoding="utf-8")
    found = [v for v in values if len(v) >= 8 and v in text]
    for value in found:
        text = text.replace(value, "[REDACTED]")
    if found:
        path.write_text(text, encoding="utf-8")
        print(f"WARNING: a key value was found in {path} and redacted; check how it got "
              "there before committing anything", file=sys.stderr)
    return bool(found)


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(runmeta.REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def execute(plan: Plan, granted: approval.PaidApproval, harness: Harness, paths: Paths,
            record: Mapping[str, Any], *, lock: Path, held: dict) -> int:
    raw_dir = paths.raw / plan.experiment / plan.run_id
    out_dir = paths.results / plan.experiment / plan.run_id
    price = pricing.price_for(plan.model, pricing.TIER)
    scratch = Path(tempfile.mkdtemp(prefix="arcrun-"))
    started = runmeta.utc_now()
    code = 1
    try:
        command = inner_command(plan, harness, scratch / "out")
        code = run_inner(command, scratch, inner_env(plan, harness, scratch))
    finally:
        row = None
        try:
            collect_outputs(scratch, raw_dir)
            account = account_acceptance if plan.acceptance else account_game
            acct = account(plan, raw_dir, price)
            if acct.any_call:
                candidate = costs_row(plan, acct, git=runmeta.git_state(paths.repo))
                costs.append_row(candidate, paths.costs)
                row = candidate
        except BaseException:
            # The run may have spent money the ledger does not show: keep the lock so that
            # no paid run starts until the row is added by hand.
            why = (f"run {plan.run_id} ({plan.describe()}) may have spent money that "
                   f"{paths.costs} does not show: add its row by hand (tagged "
                   f"{approval.spend_tag(plan.approved_block)}; harness files in {scratch} "
                   f"and {raw_dir}), then delete this lock file")
            paidlock.keep(lock, held, why)
            print(f"ERROR: could not account for the run. {why}: {lock}", file=sys.stderr)
            raise
        if row is not None:
            try:
                paidlock.record_last_run(lock, run_id=plan.run_id, costs_csv=paths.costs)
            except OSError as e:
                print(f"warning: could not record the last paid run next to {lock}: {e}",
                      file=sys.stderr)
        meta = write_meta(plan, acct, harness, granted, out_dir=out_dir, raw_dir=raw_dir,
                          started=started, row=row, record=record)
        committed = [meta]
        if not plan.blinded and not plan.acceptance:
            scorecard = (_read_json(raw_dir / inner.RESULT_FILE) or {}).get("scorecard")
            if scorecard is not None:  # ARC's scorecard: the counted run's outcome
                path = out_dir / "scorecard.json"
                path.write_text(json.dumps(inner.scrub(scorecard), indent=2) + "\n",
                                encoding="utf-8")
                committed.append(path)
        for path in committed:
            redact_keys(path, [os.environ.get(k, "") for k in plan.key_names])
        shutil.rmtree(scratch, ignore_errors=True)
        print(summary_text(plan, acct, meta, row))
    if plan.acceptance:
        return 0 if code == 0 and acct.exit_reason == "ALL_ACCEPTED" else 1
    return code


def summary_text(plan: Plan, acct: Accounting, meta: Path, row: dict | None) -> str:
    exit_reason = blind_ending(acct.exit_reason) if plan.blinded else acct.exit_reason
    lines = [f"\n{plan.describe()} (run {plan.run_id})",
             f"  exit reason: {exit_reason}",
             (f"  cost: list ${acct.cost_list:.4f}, billed estimate "
              f"${acct.cost_billed:.4f} (planned ${plan.planned_usd:.2f})"),
             f"  model calls: {acct.n_calls}; median latency: {acct.latency.get('median_s')} s",
             f"  tiers served: {acct.tiers_served or 'none reported'}",
             f"  meta: {meta}",
             f"  costs.csv row: {'appended' if row else 'none (no model call was made)'}"]
    if plan.acceptance:
        for lb, r in acct.detail["acceptance"].items():
            lines.append(f"  {lb}: accepted={r.get('accepted')} "
                         f"tier={r.get('service_tier')} model={r.get('reported_model')}"
                         + (f" error={r['error']}" if r.get("error") else ""))
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────


def main(argv: Sequence[str] | None = None, *, paths: Paths | None = None) -> int:
    paths = paths or Paths()
    args = parse_args(argv)
    try:
        record = freeze.load_record(paths.freeze)
        plan = make_plan(args, record)
        lock = paths.lock or paidlock.lock_path(paths.repo)
    except (Refused, freeze.FreezeError, paidlock.LockHeld) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    harness: Harness | None = None
    try:
        with paidlock.paid_run_lock(lock, run_id=plan.run_id, what=plan.describe()) as held:
            granted = check_paid(plan, paths, paidlock.HeldLock(lock, held))
            print(f"approved: block {plan.approved_block!r} ({granted.phase}), planned "
                  f"${plan.planned_usd:.2f}, block headroom after this run "
                  f"${granted.block_headroom_usd:.2f}; harness cost guard "
                  f"${plan.cost_cap_usd:.2f} (list)", flush=True)
            harness = prepare_harness(plan, record)
            return execute(plan, granted, harness, paths, record, lock=lock, held=held)
    except (Refused, PaidCallsNotAllowed, paidlock.LockHeld, ap.PatchError,
            freeze.FreezeError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    finally:
        if harness is not None and not args.keep_worktree:
            try:
                ap.remove_worktree(harness.worktree, ap.sanitized_env())
            except ap.PatchError as e:
                print(f"warning: could not remove {harness.worktree}: {e}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
