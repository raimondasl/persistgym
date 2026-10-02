"""Account for a PersistGym paid run whose costs.csv row could not be written (CLI
`account-run`, $0; harnesses/DESIGN.md §8.1).

A paid run whose calls are not in results/costs.csv keeps the PersistGym paid-run lock, with
the reason and the run's usage totals (`OpenAIResponsesTransport.keep_lock_if_unaccounted`),
and keeps its spend reservation. Before this command the operator added the row by hand. On
2026-10-02 a pilot run's `finalize` failed when `git rev-parse HEAD` could not start after its
calls (the root cause is fixed: the git state is now read at the run's start, common/
runmeta.py), so the run had played all its episodes and written its raw transcript and
episodes.jsonl, but not its costs row, summary.json or meta.json.

`account-run <run_id>` rebuilds what the run would have written, from its raw files and with
the repo's own code paths, so that no number is typed by hand:
* the run's settings come from its raw run_plan.json (`runner.RUN_PLAN`, written before the
  first call by runs started after this command existed), or, for a run without one, from
  the same arguments as `run` given on the command line with the git state the run read
  (`--git-commit`, `--git-dirty`); its episodes are rebuilt as `run` builds them, and must be
  those of episodes.jsonl, in order;
* the costs row: a `UsageLedger` fed with every recorded response in call order, and
  `build_costs_row`, as `finalize` builds it (blinded for a pilot), with a note that the row
  was added after the run, and why;
* summary.json (`blinding.run_summary`), meta.json (`runner._write_meta`, with a `recovered`
  field) and, for a blinded run, the raw parallel.json, as `run_batch` writes them;
* then, as `finalize` does after a row: the last-run record, the release of the run's spend
  reservation, and the release of the kept lock (`paidlock.release_kept`).

It verifies everything before it writes anything, and refuses (`Refused`) when: the run's row
is already in costs.csv; the PersistGym lock is not kept by this run, or the process that
took it may still be running; the spend reservation is another run's; raw files are missing,
or summary.json or meta.json already exist; episodes.jsonl holds an episode twice, or other
episodes than the plan's in its order, or stops where the stop rule does not; the transcript
and episodes.jsonl disagree, or the requests do not carry the given settings; the run was
played in parallel (not supported: the order its episodes finished in and its `parallel`
block are not on disk); or a rebuilt total differs from the totals kept in the lock. It then
writes the costs row first, then summary.json and meta.json, then the last-run record, the
reservation and the lock. If a step after the row fails, it says what was done and what
remains, and the lock stays kept, with that added to its reason.

Blinding (PREREG §11): nothing here prints a reasoning-token value, a per-episode outcome or
success; for a pilot-blinded experiment it prints no token or cost value but the number of
calls. The totals check prints key names and whether each matched.
"""

from __future__ import annotations

import gzip
import json
import re
import subprocess
import types
from collections import Counter
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from common import costs, paidlock, runmeta
from common.approval import spend_tag
from harnesses import blinding, runner
from harnesses.cells import CellSpec
from harnesses.config import HarnessConfig
from harnesses.matrix import RunMatrix
from harnesses.openai_transport import build_costs_row
from harnesses.pricing import UsageLedger, usage_numbers
from harnesses.session import HarnessSession
from persistgym.episode import Episode

STREAM = paidlock.PERSISTGYM
PERSISTGYM_EXPERIMENTS = tuple(e for e, s in paidlock.EXPERIMENT_STREAM.items()
                               if s == STREAM)
# Columns of the costs row that hold token counts or costs: not printed for a blinded run
# (n_calls is), and reasoning_tokens never printed.
TOKEN_COST_COLUMNS = ("input_tokens", "cached_input_tokens", "cache_write_tokens",
                      "output_tokens", "reasoning_tokens", "cost_usd_list",
                      "cost_usd_billed_est")
# What `OpenAIResponsesTransport.keep_lock_if_unaccounted` writes for a run that made calls
# whose row was not appended (with the exception that stopped `finalize`, if one did).
KEPT_RE = re.compile(
    r"run (?P<run_id>\S+) \((?P<experiment>[^,()]+), (?P<model>[^()]+)\) made (?P<n>\d+) "
    r"paid calls that (?P<costs>.+?) does not show(?: \((?P<cause>.*)\))?: add its row by "
    r"hand, with (?P<tag>approved_block=\S+;) at the start of its notes and these totals: ")
EPISODE_FIELDS = tuple(f.name for f in fields(runner.EpisodeRun))


class Refused(ValueError):
    """account-run will not write anything, for the reason given."""


class Incomplete(RuntimeError):
    """A write step after the costs row failed: `done` were done, `remaining` remain."""

    def __init__(self, message: str, done: list[str], remaining: list[str]):
        super().__init__(message)
        self.done, self.remaining = done, remaining


@dataclass
class Run:
    """The run as the `run` command would build it from its arguments (harnesses/cli.py)."""
    run_id: str
    args: Any                   # the `run` arguments (argparse.Namespace)
    cell: CellSpec
    cfg: HarnessConfig
    matrix: RunMatrix
    episodes: list[Episode]
    notes: str                  # the costs row's run notes, as `run` builds them
    what: str                   # the paid-run lock's `what`, as `run` builds it


@dataclass
class Recovery:
    """Everything verified and rebuilt, ready to write (`write`)."""
    run: Run
    blinded: bool
    out_dir: Path
    raw_dir: Path
    raw_path: Path
    episodes_path: Path
    costs_path: Path
    lock_path: Path
    lock_info: dict
    reservation: paidlock.Reservation | None
    git: dict
    started: str
    finished: str
    exit_reason: str
    records: list[dict]
    runs: list[runner.EpisodeRun]
    row: dict
    summary: dict
    recorded: dict              # meta.json's `recovered`, `prereg_version`, `sdk_versions`
    totals_match: dict[str, bool]
    plan_path: Path | None
    lines: list[str]            # what --check prints

    def describe(self) -> list[str]:
        return list(self.lines)


# --- reading -----------------------------------------------------------------------------------

def find_plan(raw_root: Path, run_id: str,
              experiment: str | None = None) -> tuple[Path | None, dict | None]:
    """The run's raw run_plan.json and its content, under `experiment` or, if None, under any
    PersistGym-stream experiment; (None, None) if there is none. Refuses if it cannot be read,
    or if two experiments hold one."""
    runner.require_plain_name("run id", run_id)
    found = [raw_root / e / run_id / runner.RUN_PLAN
             for e in ([experiment] if experiment else PERSISTGYM_EXPERIMENTS)]
    found = [p for p in found if p.exists()]
    if len(found) > 1:
        raise Refused(f"run {run_id} has a run plan under {len(found)} experiments "
                      f"({', '.join(p.parent.parent.name for p in found)}): give --experiment")
    if not found:
        return None, None
    try:
        plan = json.loads(found[0].read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Refused(f"cannot read {found[0]}: {e}") from None
    if (not isinstance(plan, dict) or plan.get("run_id") != run_id
            or plan.get("plan_version") != runner.RUN_PLAN_VERSION):
        raise Refused(f"{found[0]} is not run {run_id}'s plan in the format this code reads "
                      f"(plan_version {runner.RUN_PLAN_VERSION})")
    return found[0], plan


def _option(key: str) -> str:
    return "--W" if key == "W" else "--" + key.replace("_", "-")


def run_arguments(plan: dict | None, given: dict, defaults: dict) -> dict:
    """The run's `run` arguments: the run plan's, which arguments given on the command line
    must equal, or, for a run without them, `defaults` (those of `run`) updated with the
    arguments given, which must include --cell."""
    if plan is not None and plan.get("run_args") is not None:
        args = dict(plan["run_args"])
        differ = [_option(k) for k, v in given.items() if args.get(k) != v]
        if differ:
            raise Refused(f"{', '.join(differ)} differ from the run's run_plan.json; give no "
                          f"run arguments, the plan holds them")
        return args
    if "cell" not in given:
        raise Refused("the run has no run_plan.json with its arguments (runs started before "
                      "account-run existed): give the arguments it was started with, as for "
                      "`run` (at least --cell), and the git state it read, --git-commit and "
                      "--git-dirty")
    return {**defaults, **given}


def _read_jsonl(path: Path, what: str) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    out = []
    try:
        with opener(path, "rt", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    raise Refused(f"{what} {path}: line {i} is not JSON") from None
                if not isinstance(rec, dict):
                    raise Refused(f"{what} {path}: line {i} is not a JSON object")
                out.append(rec)
    except (OSError, EOFError) as e:
        raise Refused(f"cannot read the {what} {path}: {e}") from None
    return out


def _utc(text: str, what: str) -> str:
    try:
        t = datetime.fromisoformat(str(text))
    except ValueError:
        raise Refused(f"{what} {text!r} is not an ISO 8601 time") from None
    if t.tzinfo is None:
        raise Refused(f"{what} {text!r} has no time zone (UTC: +00:00)")
    return t.astimezone(UTC).isoformat(timespec="seconds")


# --- verifying ---------------------------------------------------------------------------------

def _check_settings(run: Run, plan: dict | None) -> None:
    a = run.args
    if paidlock.stream_of(a.experiment) != STREAM:
        raise Refused(f"experiment {a.experiment!r} is not a PersistGym-stream experiment "
                      f"({', '.join(PERSISTGYM_EXPERIMENTS)})")
    if a.parallel != 1:
        raise Refused(f"the run played {a.parallel} episodes at once: accounting for a run "
                      "played in parallel is not supported (the order its episodes finished "
                      "in, which its stop rule used, and its `parallel` block are not on "
                      "disk); add its row by hand from the totals in the paid-run lock")
    if plan is None:
        return
    expected = {"experiment": a.experiment, "milestone": a.milestone,
                "harness_cell": run.cell.cell_id, "harness_config": run.cfg.to_dict(),
                "run_matrix": run.matrix.to_dict(),
                "episode_ids": [e.episode_id for e in run.episodes], "notes": run.notes,
                "parallel": a.parallel, "repeat_index": 0,
                "abort_after_api_errors": runner.ABORT_AFTER_API_ERRORS}
    differ = [k for k, v in expected.items() if plan.get(k) != v]
    if differ:
        raise Refused(f"the run's run_plan.json differs from what `run` builds from its "
                      f"arguments in {', '.join(differ)}: this code would not rebuild the "
                      f"run as it ran")


def _check_lock(run: Run, lock_path: Path, costs_path: Path,
                blinded: bool) -> tuple[dict, dict, str | None]:
    """The kept lock's contents, the totals it holds and the cause of the failure."""
    rid, a = run.run_id, run.args
    try:
        info = json.loads(lock_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Refused(f"no PersistGym paid-run lock {lock_path}: an unaccounted run keeps it, "
                      f"so run {rid} is not one (or the lock was deleted by hand: then add "
                      f"its row by hand)") from None
    except (OSError, ValueError) as e:
        raise Refused(f"cannot read the paid-run lock {lock_path}: {e}") from None
    if not isinstance(info, dict) or info.get("run_id") != rid:
        held = info.get("run_id") if isinstance(info, dict) else None
        raise Refused(f"the paid-run lock {lock_path} is held by run {held!r}, not {rid}")
    if info.get("stream") != STREAM:
        raise Refused(f"the paid-run lock {lock_path} names stream {info.get('stream')!r}")
    why = info.get("kept_because")
    if not isinstance(why, str) or not why:
        raise Refused(f"the paid-run lock {lock_path} is held by run {rid} but not kept (no "
                      f"kept_because): the run may still be going")
    if info.get(paidlock.HOLD_NOT_RECORDED):
        raise Refused(f"the paid-run lock {lock_path} is marked {paidlock.HOLD_NOT_RECORDED}: "
                      "the run may have placed a hold the record does not show; settle that "
                      "by hand")
    alive = paidlock.holder_alive(info)
    if alive is not None:
        raise Refused(f"{alive}: account for a run only once its process has ended")
    if "paid calls in flight" in why:
        raise Refused("the run had paid calls in flight when it ended (episodes played in "
                      "parallel, abandoned): their usage is recorded nowhere, so accounting "
                      "for it is not supported; add its rows by hand")
    if paidlock.ALSO in why:
        raise Refused(f"the paid-run lock {lock_path} was kept for more than one reason: "
                      "settle it by hand")
    m = KEPT_RE.match(why)
    if m is None or m["run_id"] != rid:
        raise Refused(f"the paid-run lock's kept_because is not that of a run whose costs row "
                      f"could not be written: {lock_path}")
    if run.what != info.get("what"):
        raise Refused(f"the run arguments describe '{run.what}', the lock '{info.get('what')}'"
                      f": give the arguments the run was started with")
    if (m["experiment"], m["model"]) != (a.experiment, a.model):
        raise Refused(f"the lock names {m['experiment']}, {m['model']}; the arguments "
                      f"{a.experiment}, {a.model}")
    if m["tag"] != spend_tag(str(a.approved_block).strip()):
        raise Refused(f"the lock names the run's block as {m['tag']!r}, the arguments "
                      f"{spend_tag(str(a.approved_block).strip())!r}")
    if Path(m["costs"]).resolve() != costs_path.resolve():
        raise Refused(f"the run's spend belongs in {m['costs']}, not {costs_path}: run "
                      f"account-run from the checkout the run was started from")
    try:
        totals, _ = json.JSONDecoder().raw_decode(why, m.end())
    except ValueError:
        raise Refused("the totals in the paid-run lock's kept_because cannot be read") from None
    if not isinstance(totals, dict) or int(m["n"]) != totals.get("n_calls"):
        raise Refused("the totals in the paid-run lock's kept_because are not the run's")
    if blinded and totals.get("reasoning_tokens") is not None:
        raise Refused("the lock of a pilot-blinded run holds reasoning tokens")
    return info, totals, m["cause"]


def _check_reservation(run: Run, lock_path: Path,
                       plan: dict | None) -> paidlock.Reservation | None:
    a = run.args
    try:
        with paidlock.budget_mutex(lock_path):
            mine = [r for r in paidlock.read_reservations(lock_path) if r.stream == STREAM]
    except (OSError, paidlock.ReservationError) as e:
        raise Refused(f"cannot read the spend reservations next to {lock_path}: {e}") from None
    if not mine:
        return None   # deleted by hand already: nothing to release
    (r,) = mine
    try:
        planned = Decimal(repr(float(a.planned_usd)))
    except (TypeError, ValueError, InvalidOperation):
        raise Refused(f"--planned-usd {a.planned_usd!r} is not an amount") from None
    want = {"run_id": run.run_id, "experiment": a.experiment,
            "approved_block": str(a.approved_block).strip(), "planned_usd": planned}
    got = {"run_id": r.run_id, "experiment": r.experiment, "approved_block": r.approved_block,
           "planned_usd": r.planned_usd}
    if plan is not None and plan.get("reservation_id"):
        want["reservation_id"], got["reservation_id"] = plan["reservation_id"], r.reservation_id
    differ = [k for k in want if want[k] != got[k]]
    if differ:
        raise Refused(f"the PersistGym spend reservation {r.path} is not this run's "
                      f"({', '.join(differ)} differ): {r.describe()}")
    return r


def _check_files(run: Run, out_dir: Path, raw_dir: Path, raw_path: Path,
                 episodes_path: Path, blinded: bool) -> None:
    for path in (raw_path, episodes_path):
        if not path.is_file():
            raise Refused(f"the run's {path.name} is missing: {path}")
    written = [out_dir / "summary.json", out_dir / "meta.json"]
    if blinded:
        written.append(raw_dir / runner.PARALLEL_INFO)
    there = [str(p) for p in written if p.exists()]
    if there:
        raise Refused(f"files run_batch writes after the costs row exist already: "
                      f"{', '.join(there)}; this command writes them")
    inflight = raw_dir / runner.INFLIGHT_DIR
    if inflight.exists():
        raise Refused(f"the run has an in-flight spool folder {inflight} (episodes played in "
                      "parallel): not supported")


def _git_and_start(plan: dict | None, git_given: dict | None, started_given: str | None,
                   lock_info: dict) -> tuple[dict, str, str]:
    """The run's git state, its start time and where the start time came from."""
    if plan is not None:
        try:
            git = runmeta.check_git_state(plan.get("git"))
        except ValueError as e:
            raise Refused(f"the run plan's git state: {e}") from None
        if git_given is not None and git_given != git:
            raise Refused("--git-commit / --git-dirty differ from the git state the run read "
                          "at its start (run_plan.json)")
        started = _utc(plan.get("started_utc"), "the run plan's started_utc")
        if started_given is not None and _utc(started_given, "--started-utc") != started:
            raise Refused("--started-utc differs from the run plan's started_utc")
        return git, started, "plan"
    if git_given is None:
        raise Refused("the run has no run_plan.json: give the git state it read, "
                      "--git-commit <commit> and --git-dirty true|false (the commit its "
                      "launch checkout had checked out)")
    try:
        git = runmeta.check_git_state(git_given)
        runmeta.run_git("cat-file", "-e", f"{git['git_commit']}^{{commit}}")
    except ValueError as e:
        raise Refused(f"--git-commit / --git-dirty: {e}") from None
    except (OSError, subprocess.CalledProcessError):
        raise Refused(f"--git-commit {git_given['git_commit']} is not a commit of this "
                      "repository") from None
    if started_given is not None:
        return git, _utc(started_given, "--started-utc"), "given"
    return git, _utc(lock_info.get("started_utc"), "the lock's started_utc"), "lock"


def _first_payload(run: Run, episode: Episode) -> dict:
    """The first request `run_episode` sends for `episode`: built from the episode alone."""
    session = HarnessSession.for_episode(run.cell, episode, run.cfg)
    session.observe(episode.steps[0].observation)
    return json.loads(json.dumps(session.next_request().payload, ensure_ascii=False))


def _check_episodes(run: Run, records: list[dict], transcript: list[dict]) -> list[float]:
    """Check episodes.jsonl against the plan and the transcript against episodes.jsonl;
    return each call's latency (the runner's timing) in call order. Messages name fields,
    never their values (PREREG §11)."""
    cell, cfg = run.cell, run.cfg
    ids = [e.episode_id for e in run.episodes]
    got = [r.get("episode_id") for r in records]
    if len(set(got)) != len(got):
        raise Refused("episodes.jsonl holds an episode more than once (a run id reused?)")
    if got != ids[:len(got)]:
        raise Refused("the episodes in episodes.jsonl are not the run's, in its order: give "
                      "the arguments the run was started with")
    if not records:
        raise Refused("episodes.jsonl holds no episode")
    latencies: list[float] = []
    k = 0
    for i, (rec, ep) in enumerate(zip(records, run.episodes, strict=False)):
        where = f"episode {i + 1} of episodes.jsonl"
        if tuple(rec) != EPISODE_FIELDS:
            raise Refused(f"{where} does not have the fields this runner writes")
        static = {"template_id": ep.template_id, "task_cell": ep.cell.id,
                  "variant": ep.variant, "harness_cell": cell.cell_id, "model": cfg.model}
        differ = [f for f, v in static.items() if rec[f] != v]
        if differ:
            raise Refused(f"{where}: {', '.join(differ)} differ from the run's settings")
        n = rec["n_requests"]
        calls = transcript[k:k + n]
        k += n
        if (len(calls) != n or [c.get("episode_id") for c in calls] != [ep.episode_id] * n
                or [c.get("request_index") for c in calls] != list(range(n))):
            raise Refused(f"{where}: the transcript does not hold its {n} calls in order")
        if len(rec["call_latency_s"]) != n:
            raise Refused(f"{where}: call_latency_s does not time its {n} calls")
        usage: dict[str, int] = {}
        counts = {key: Counter() for key in ("context_echoed", "effort_echoed",
                                             "models_returned", "service_tiers_returned")}
        for j, c in enumerate(calls):
            payload, response = c.get("payload") or {}, c.get("response") or {}
            reasoning = payload.get("reasoning") or {}
            sent = {"model": payload.get("model"), "context": reasoning.get("context"),
                    "effort": reasoning.get("effort"), "mode": reasoning.get("mode"),
                    "service_tier": payload.get("service_tier"),
                    "harness_cell": c.get("harness_cell")}
            want = {"model": cfg.model, "context": cell.reasoning_context,
                    "effort": cfg.reasoning_effort, "mode": cfg.reasoning_mode,
                    "service_tier": cfg.service_tier, "harness_cell": cell.cell_id}
            differ = [f for f in want if sent[f] != want[f]]
            if differ:
                raise Refused(f"{where}, call {j + 1}: the request's {', '.join(differ)} "
                              "differ from the run's settings")
            echo = runner.check_echo(payload, response)
            if c.get("echo") != echo:
                raise Refused(f"{where}, call {j + 1}: the recorded echo is not the response's")
            for key, v in usage_numbers(response.get("usage")).items():
                usage[key] = usage.get(key, 0) + v
            counts["context_echoed"][str(echo["context_echoed"])] += 1
            counts["effort_echoed"][str(echo["effort_echoed"])] += 1
            counts["models_returned"][str(echo["model_returned"])] += 1
            counts["service_tiers_returned"][str(echo["service_tier_returned"])] += 1
        if n and calls[0]["payload"] != _first_payload(run, ep):
            raise Refused(f"{where}: its first request is not the one this code builds from "
                          "the run's settings")
        if rec["usage"] != usage:
            raise Refused(f"{where}: its usage is not the sum of its calls' usage")
        if (rec["echo"].get("context_requested") != cell.reasoning_context
                or rec["echo"].get("effort_requested") != cfg.reasoning_effort
                or any(rec["echo"].get(key) != dict(v) for key, v in counts.items())):
            raise Refused(f"{where}: its echo counts are not those of its calls")
        if rec["n_summary_requests"] != sum(c.get("kind") == "summary" for c in calls):
            raise Refused(f"{where}: n_summary_requests does not count its summary calls")
        latencies += rec["call_latency_s"]
    if k != len(transcript):
        raise Refused(f"the transcript holds {len(transcript) - k} calls after the last "
                      "episode in episodes.jsonl (an episode stopped by an error or an "
                      "interruption): not supported")
    return latencies


def _exit_reason(run: Run, runs: list[runner.EpisodeRun]) -> str:
    """The run's exit reason, by the sequential loop of `run_batch`."""
    done: list[runner.EpisodeRun] = []
    for i, r in enumerate(runs):
        done.append(r)
        reason = runner._stop_reason(done, r, run.cfg, runner.ABORT_AFTER_API_ERRORS)
        if reason:
            if i != len(runs) - 1:
                raise Refused(f"the run's stop rule ({reason}) stops it after episode {i + 1}, "
                              f"but episodes.jsonl holds {len(runs)}")
            return reason
    if len(runs) != len(run.episodes):
        raise Refused(f"episodes.jsonl holds {len(runs)} of the run's {len(run.episodes)} "
                      "episodes and its stop rule does not stop it there: it stopped for a "
                      "reason its files do not show (an error or an interruption, whose exit "
                      "reason is not on disk): not supported")
    return "COMPLETED"


# --- the plan --------------------------------------------------------------------------------

def prepare(run: Run, *, plan: dict | None, plan_path: Path | None, git: dict | None,
            started: str | None, lock_path: Path, costs_path: Path, results_root: Path,
            raw_root: Path) -> Recovery:
    """Verify everything and rebuild what the run would have written; write nothing. Raises
    Refused with the first reason it may not go on."""
    rid, a = run.run_id, run.args
    runner.require_plain_name("run id", rid)
    runner.require_plain_name("--experiment", a.experiment)
    _check_settings(run, plan)
    blinded = blinding.is_blinded(a.experiment)
    out_dir, raw_dir = results_root / a.experiment / rid, raw_root / a.experiment / rid
    raw_path = raw_dir / "transcript.jsonl.gz"
    episodes_path = (raw_dir if blinded else out_dir) / "episodes.jsonl"
    try:
        rows = costs.read_rows(costs_path)
    except (OSError, ValueError) as e:
        raise Refused(f"cannot read {costs_path}: {e}") from None
    if any(r.get("run_id") == rid for r in rows):
        raise Refused(f"{costs_path} already has a row of run {rid}")
    lock_info, kept_totals, cause = _check_lock(run, lock_path, costs_path, blinded)
    reservation = _check_reservation(run, lock_path, plan)
    _check_files(run, out_dir, raw_dir, raw_path, episodes_path, blinded)
    git_state, start, start_from = _git_and_start(plan, git, started, lock_info)

    records = _read_jsonl(episodes_path, "episodes file")
    transcript = _read_jsonl(raw_path, "raw transcript")
    latencies = _check_episodes(run, records, transcript)
    runs = [runner.EpisodeRun(**r) for r in records]
    exit_reason = _exit_reason(run, runs)

    # The ledger as the transport kept it: every response in call order (a sequential run
    # sends and records one call at a time). The transport's own timings were not saved.
    ledger = UsageLedger(a.model)
    for c, latency in zip(transcript, latencies, strict=True):
        ledger.add(c["response"], requested_tier=c["payload"].get("service_tier"),
                   latency_s=latency)
    rebuilt = ledger.totals()
    if blinded:
        rebuilt = blinding.blinded_tokens(rebuilt)
    keys = sorted(set(rebuilt) | set(kept_totals))
    match = {k: k in rebuilt and k in kept_totals and rebuilt[k] == kept_totals[k]
             for k in keys}
    if not all(match.values()):
        raise Refused("the rebuilt totals differ from those the run kept in its paid-run lock "
                      f"in {', '.join(k for k, ok in match.items() if not ok)}")

    end = datetime.fromtimestamp(raw_path.stat().st_mtime, UTC).isoformat(timespec="seconds")
    accounted = runmeta.utc_now()
    cause_text = cause or "the run's finalize did not run"
    row = build_costs_row(
        ledger, timestamp_utc=end, run_id=rid, milestone=a.milestone,
        approved_block=str(a.approved_block).strip(), experiment=a.experiment,
        cell_or_config=run.cell.ascii_id, git=git_state,
        context_mismatches=sum(1 for c in transcript if not c["echo"]["context_ok"]),
        effort_mismatches=sum(1 for c in transcript if not c["echo"]["effort_ok"]),
        notes=run.notes)
    row["notes"] = (f"{row['notes']}; added by account-run on {accounted[:10]}, after the run, "
                    f"whose costs row could not be written ({cause_text}); timestamp_utc is the "
                    f"raw transcript's last write; latency_s is the median of the runner's "
                    f"per-call timings in episodes.jsonl (the transport's were not saved)")
    summary = blinding.run_summary(records, blinded=blinded)

    approximate = {
        "finished_utc": ("the raw transcript's last write, when the run's last call was "
                         "recorded; run_batch writes the time it wrote meta.json"),
        "costs_row_timestamp_utc": ("the raw transcript's last write; finalize writes the "
                                    "time it built the row"),
        "costs_row_latency_s": ("the median of the runner's per-call timings "
                                "(episodes.jsonl call_latency_s, to the millisecond); the "
                                "transport's own timings were not saved"),
    }
    if start_from == "lock":
        approximate["started_utc"] = ("the paid-run lock's started_utc, taken before the paid "
                                      "guard's checks, seconds before run_batch started")
    elif start_from == "given":
        approximate["started_utc"] = "given on the command line (--started-utc)"
    if plan is not None:
        prereg, sdks = plan.get("prereg_version"), plan.get("sdk_versions")
    else:
        try:
            prereg = runmeta.prereg_version_in(
                runmeta.run_git("show", f"{git_state['git_commit']}:PREREG.md"))
        except (OSError, subprocess.CalledProcessError):
            prereg = None
        sdks = runmeta.sdk_versions()
        approximate["prereg_version"] = "PREREG.md at the run's commit"
        approximate["sdk_versions"] = "this environment's, when the run was accounted for"
    recovered = {
        "by": "harnesses account-run",
        "accounted_utc": accounted,
        "cause": cause_text,
        "what": ("the run's costs.csv row could not be written when it ended, so run_batch "
                 "wrote neither summary.json nor meta.json. account-run rebuilt the row and "
                 "both files (and a pilot's raw parallel.json) from the run's raw transcript "
                 "and episodes.jsonl with the repo's own code, and checked the row's totals "
                 "against those the run kept in its paid-run lock"),
        "settings_from": "run_plan.json" if plan is not None else "the command line",
        "run_plan": runner._rel(plan_path) if plan_path is not None else None,
        "git_state_from": ("run_plan.json (read at the run's start)" if plan is not None
                           else "the command line (--git-commit, --git-dirty)"),
        "approximate": approximate,
    }
    rec = Recovery(
        run=run, blinded=blinded, out_dir=out_dir, raw_dir=raw_dir, raw_path=raw_path,
        episodes_path=episodes_path, costs_path=costs_path, lock_path=lock_path,
        lock_info=lock_info, reservation=reservation, git=git_state, started=start,
        finished=end, exit_reason=exit_reason, records=records, runs=runs, row=row,
        summary=summary,
        recorded={"recovered": recovered, "prereg_version": prereg, "sdk_versions": sdks},
        totals_match=match, plan_path=plan_path, lines=[])
    rec.lines = _describe(rec)
    return rec


def _shown_row(rec: Recovery) -> str:
    """The costs row as account-run prints it: never reasoning tokens, and for a blinded run
    no token or cost value but n_calls (PREREG §11)."""
    hidden = set(TOKEN_COST_COLUMNS) if rec.blinded else {"reasoning_tokens"}
    return "; ".join(f"{k}={'<withheld>' if k in hidden else v}" for k, v in rec.row.items()
                     if k != "notes")


def _describe(rec: Recovery) -> list[str]:
    """What --check prints, and account-run before it writes: no reasoning-token value, no
    outcome and, for a blinded run, no token or cost value but n_calls (PREREG §11)."""
    run, a, r = rec.run, rec.run.args, rec.reservation
    errors = rec.summary["errors"]
    reservation = (f"the spend reservation {r.reservation_id} is this run's" if r is not None
                   else "no PersistGym spend reservation is left")
    totals = ", ".join(f"{k} {'match' if ok else 'DIFFER'}"
                       for k, ok in rec.totals_match.items())
    withheld = ("token and cost values withheld here (pilot blinding, PREREG §11)"
                if rec.blinded else "reasoning_tokens not shown")
    then = [f"record the last paid run in {paidlock.last_run_path(rec.lock_path, STREAM)}"]
    if r is not None:
        then.append(f"release the spend reservation {r.reservation_id}")
    then.append(f"release the kept lock {rec.lock_path}")
    files = [rec.out_dir / "summary.json"]
    if rec.blinded:
        files.append(rec.raw_dir / runner.PARALLEL_INFO)
    files.append(rec.out_dir / "meta.json")
    return [
        (f"run {run.run_id}: {run.what}; {len(rec.records)} in episodes.jsonl, "
         f"{rec.row['n_calls']} calls"),
        (f"  run arguments: {a.experiment}, {run.cell.cell_id}, {a.model} at effort "
         f"{a.effort}, block {a.approved_block}, planned ${float(a.planned_usd):.2f}; from "
         + (str(rec.plan_path) if rec.plan_path else "the command line")),
        (f"  git state: {rec.git['git_commit']} (dirty: {rec.git['git_dirty']}); "
         f"started_utc {rec.started}; the run's last call recorded {rec.finished}"),
        (f"  checked: no costs row of the run in {rec.costs_path}; the lock {rec.lock_path} "
         f"is kept by this run, whose process has ended; {reservation}"),
        ("  checked: the episodes are the run's, in its order; the transcript, episodes.jsonl "
         "and the run's settings agree call by call"),
        f"  totals against those kept in the lock: {totals}",
        (f"  exit reason: {rec.exit_reason}; episode exit reasons: "
         f"{json.dumps(errors['exit_reasons'])}; excluded: {errors['n_excluded']}"),
        "  writes, in this order:",
        f"    the costs row, appended to {rec.costs_path}: {_shown_row(rec)}; {withheld}",
        f"      notes: {rec.row['notes']}",
        *(f"    {path}" + (" (with `recovered`)" if path.name == "meta.json" else "")
          for path in files),
        *(f"    then: {x}" for x in then),
    ]


# --- writing ---------------------------------------------------------------------------------

def write(rec: Recovery) -> list[str]:
    """Write what `prepare` rebuilt, in order: the costs row, summary.json (and, for a
    blinded run, the raw parallel.json), meta.json, the last-run record, the release of the
    reservation and of the kept lock. Returns the steps done. Raises Refused if the row
    appeared meanwhile (nothing written), or Incomplete if a step after the row failed: the
    lock then stays kept, with what remains added to its reason."""
    run = rec.run
    blinded = rec.blinded
    parallel_path = rec.raw_dir / runner.PARALLEL_INFO if blinded else None

    def append_row() -> None:
        # Checked again under the budget mutex, so that two account-runs cannot both add it.
        with paidlock.budget_mutex(rec.lock_path):
            if any(r.get("run_id") == run.run_id for r in costs.read_rows(rec.costs_path)):
                raise Refused(f"{rec.costs_path} has a row of run {run.run_id} now")
            costs.append_row(rec.row, rec.costs_path)

    def summary() -> None:
        rec.out_dir.mkdir(parents=True, exist_ok=True)
        (rec.out_dir / "summary.json").write_text(json.dumps(rec.summary, indent=2) + "\n",
                                                  encoding="utf-8")

    def meta() -> None:
        nonlocal parallel_path
        info = {"max_episodes_in_flight": 1}
        if parallel_path is not None and not runner._write_raw(
                parallel_path, json.dumps(info, indent=2) + "\n"):
            parallel_path = None
        runner._write_meta(
            rec.out_dir, rec.raw_path, run.episodes, rec.runs, run.cell, run.cfg,
            types.SimpleNamespace(paid=True), experiment=run.args.experiment,
            run_id=run.run_id, started=rec.started, exit_reason=rec.exit_reason,
            repeat_index=0, cost_row=rec.row, blinded=blinded,
            episodes_path=rec.episodes_path, run_matrix=run.matrix.to_dict(), parallel=info,
            parallel_path=parallel_path, git=rec.git, finished=rec.finished,
            recorded=rec.recorded)

    def last_run() -> None:
        paidlock.record_last_run(rec.lock_path, stream=STREAM, run_id=run.run_id,
                                 costs_csv=rec.costs_path,
                                 timestamp_utc=rec.row["timestamp_utc"])

    def reservation() -> None:
        if not paidlock.release_reservation(rec.lock_path, stream=STREAM,
                                            reservation_id=rec.reservation.reservation_id):
            raise OSError(f"the spend reservation {rec.reservation.path} changed or is gone")

    def lock() -> None:
        paidlock.release_kept(rec.lock_path, run_id=run.run_id, token=rec.lock_info["token"])

    steps = [(f"append the costs row to {rec.costs_path}", append_row),
             (f"write {rec.out_dir / 'summary.json'}", summary),
             (f"write {rec.out_dir / 'meta.json'}"
              + (f" and {rec.raw_dir / runner.PARALLEL_INFO}" if blinded else ""), meta),
             (f"record the last paid run in {paidlock.last_run_path(rec.lock_path, STREAM)}",
              last_run)]
    if rec.reservation is not None:
        steps.append((f"release the spend reservation {rec.reservation.path}", reservation))
    steps.append((f"release the kept lock {rec.lock_path}", lock))
    done: list[str] = []
    for i, (what, step) in enumerate(steps):
        try:
            step()
        except Refused:
            raise
        except BaseException as e:
            remaining = [w for w, _ in steps[i:]]
            if done:
                # The row is in costs.csv: say so in the lock, so that nobody adds it again.
                paidlock.keep(rec.lock_path, rec.lock_info,
                              f"account-run appended run {run.run_id}'s costs row "
                              f"(timestamp_utc {rec.row['timestamp_utc']}) to "
                              f"{rec.costs_path}; do not add it again. It could not "
                              f"{'; '.join(remaining)} ({type(e).__name__}: {e}): do that "
                              f"by hand")
            raise Incomplete(f"{type(e).__name__}: {e}", done, remaining) from e
        done.append(what)
    return done

