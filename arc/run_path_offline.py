"""$0 end-to-end check of the paid launcher's inner modes (arc/run_path_inner.py) in the
patched harness. It plays arc/toy_game offline with the stub model of
offline_smoke_inner.py behind its loopback-only socket guard. No key is read, and nothing
can reach a model provider or ARC.

Run from the repository root:

    uv run arc/run_path_offline.py

Three cases, each in a fresh process, then the launcher's own collect and accounting
functions (arc/run_path.py) on what the harness wrote:
* ``play`` S0 with ``--max-actions 4``: stops after 4 actions with ACTION_BUDGET;
* ``play`` S1 with ``--max-actions 50 --after-summary-turns 3``: one harness summary (the
  stub reports 180k tokens on turn 2), then stops 3 turns after it;
* ``accept`` for S0, S1, S2 and S4: one request each, all accepted.
Every case checks that each request body asks for the standard tier at high thinking, that
the call meter saw exactly the requests the stub answered, and that the harness cost guard
was set. The only differences from a paid run: the swarm is forced to offline play, the
inner process's online-only check is skipped, and the stub replaces the HTTPS transport
below the call meter. Output goes to results/raw/arc_run_path_offline/<UTC time>/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CAP_USD = 5.0
CASES = [
    {"mode": "play", "labels": ("S0",), "args": ["--max-actions", "4"]},
    {"mode": "play", "labels": ("S1",),
     "args": ["--max-actions", "50", "--after-summary-turns", "3"]},
    {"mode": "accept", "labels": ("S0", "S1", "S2", "S4"), "args": []},
]
WORKTREE_NAME = "rp-offline"


# ── Driver (patched harness environment only; standard library + harness) ──


def driver(argv: list[str]) -> int:
    """Run run_path_inner.main offline with the stub model."""
    mode, config_ids, out, *extra = argv
    import importlib

    import offline_smoke_inner as osi
    import run_path_inner as rpi

    osi.guard_network()
    importlib.import_module("no_dotenv_plugin")
    import benchmarking.agent as agent_module
    import benchmarking.swarm as swarm_module
    import httpx
    from arc_agi import OperationMode
    from benchmarking.model_config import get_model_config

    stub = osi.StubModel(osi.StubPolicy(script=["ACTION1"] * 50),
                         osi.StubUsage("fixed", {2}))
    agent_module.default_http_transport = lambda: httpx.MockTransport(stub)
    real_init = swarm_module.Swarm.__init__

    def offline_init(self: Any, *a: Any, **k: Any) -> None:
        k["operation_mode"] = OperationMode.OFFLINE
        real_init(self, *a, **k)

    swarm_module.Swarm.__init__ = offline_init
    rpi._online_only = lambda: None
    os.environ["GOOGLE_API_KEY"] = osi.STUB_API_KEY
    ids = config_ids.split(",")
    hashes = {cid: rpi.config_hash(get_model_config(cid)) for cid in ids}
    if mode == "play":
        args = ["play", "--config", ids[0], "--game", "toyg", "--out", out,
                "--expect-config-hash", hashes[ids[0]], "--cost-cap-usd", str(CAP_USD),
                "--tags", "offline-check", *extra]
    else:
        args = ["accept", "--configs", config_ids, "--out", out,
                "--expect-config-hashes", json.dumps(hashes), "--cost-cap-usd", str(CAP_USD)]
    code = rpi.main(args)
    Path(out, "bodies.json").write_text(json.dumps(stub.bodies, indent=1), encoding="utf-8")
    return code


# ── Runner (repository environment) ───────────────────────────────────


def check_case(case: dict, code: int, acct: Any, bodies: list[dict]) -> list[str]:
    problems = [] if code == 0 else [f"inner process exited {code}"]
    for i, body in enumerate(bodies, 1):
        if body.get("service_tier") != "standard":
            problems.append(f"body {i}: service_tier {body.get('service_tier')!r}")
        if body.get("generation_config", {}).get("thinking_level") != "high":
            problems.append(f"body {i}: thinking_level is not high")
    if acct.n_http_requests != len(bodies) or acct.n_calls != len(bodies):
        problems.append(f"meter saw {acct.n_http_requests} requests ({acct.n_calls} ok) for "
                        f"{len(bodies)} stub requests")
    if case["mode"] == "accept":
        if acct.exit_reason != "ALL_ACCEPTED" or len(bodies) != len(case["labels"]):
            problems.append(f"{acct.exit_reason} with {len(bodies)} requests")
        return problems
    truncation = acct.outcome.get("truncation") or {}
    if (acct.exit_reason, acct.agent_exit_reason) != ("ACTION_BUDGET", "ACTION_BUDGET"):
        problems.append(f"exit {acct.exit_reason} / {acct.agent_exit_reason}")
    if (acct.detail.get("cost_guard") or {}).get("max_usd") != CAP_USD:
        problems.append(f"cost guard {acct.detail.get('cost_guard')}")
    if acct.detail.get("arc_environment") != {"kind": "local"}:
        problems.append(f"arc_environment {acct.detail.get('arc_environment')}")
    if case["labels"] == ("S0",):
        if truncation.get("reason") != "max_actions=4" or acct.outcome["n_steps"] != 4:
            problems.append(f"truncation {truncation}, {acct.outcome['n_steps']} steps")
    else:
        if (acct.detail.get("n_compactions"), acct.detail.get("context_trims")) != (1, 0):
            problems.append(f"{acct.detail.get('n_compactions')} compactions, "
                            f"{acct.detail.get('context_trims')} trims")
        before = truncation.get("first_summary_before_step")
        if (not str(truncation.get("reason")).startswith("after_summary_turns=3")
                or before is None or acct.outcome["n_steps"] != before + 2):
            problems.append(f"truncation {truncation}, {acct.outcome['n_steps']} steps")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    if __package__ in (None, ""):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from arc import apply_patches as ap
    from arc import config_hash as freeze
    from arc import offline_smoke, pricing
    from arc import run_path as rp

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--keep", action="store_true", help="keep the scratch worktree")
    args = parser.parse_args(argv)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_root = (args.out or ap.REPO_ROOT / "results" / "raw" / "arc_run_path_offline"
                / stamp).resolve()
    record = freeze.load_record()
    price = pricing.price_for("gemini-3.8-flash")
    env = ap.sanitized_env()
    worktree = ap.WORK_DIR / WORKTREE_NAME
    failures = 0
    try:
        ap.check_pin(env)
        ap.create_worktree(worktree, env)
        ap.apply_series(worktree, ap.patch_files(), env)
        ap.sync_environment(worktree, env)
        for case in CASES:
            labels = case["labels"]
            name = f"{case['mode']}-{'+'.join(labels)}"
            with tempfile.TemporaryDirectory(prefix="arcrpo-",
                                             ignore_cleanup_errors=True) as tmp:
                scratch = Path(tmp)
                offline_smoke.stage_toy_game(scratch / "envs")
                run_env = {**env,
                           "PYTHONPATH": os.pathsep.join([str(worktree), str(ap.ARC_DIR)]),
                           "PYTHONUTF8": "1", "ENVIRONMENTS_DIR": str(scratch / "envs"),
                           "RECORDINGS_DIR": str(scratch / "rec")}
                ids = ",".join(record["profiles"][lb]["config_id"] for lb in labels)
                command = ["uv", "run", "--no-sync", "--project", str(worktree), "python",
                           str(Path(__file__).resolve()), "--driver", case["mode"], ids,
                           str(scratch / "out"), *case["args"]]
                done = ap._run(command, scratch, run_env, capture=True)
                raw = out_root / name
                rp.collect_outputs(scratch, raw)
                (raw / "driver.log").write_text(done.stdout + done.stderr, encoding="utf-8")
            plan = rp.Plan(experiment="arc_pilot" if case["mode"] == "play" else "gemini_probe",
                           approved_block="offline-check", planned_usd=CAP_USD,
                           milestone="M0", run_id=name, labels=labels,
                           acceptance=case["mode"] == "accept", game="toyg", seed=0,
                           model="gemini-3.8-flash",
                           profiles={lb: record["profiles"][lb] for lb in labels})
            account = rp.account_acceptance if plan.acceptance else rp.account_game
            acct = account(plan, raw, price)
            bodies = json.loads((raw / "bodies.json").read_text(encoding="utf-8")) \
                if (raw / "bodies.json").exists() else []
            problems = check_case(case, done.returncode, acct, bodies)
            failures += bool(problems)
            print(f"  {'PASS' if not problems else 'FAIL'} {name:<24} calls={acct.n_calls} "
                  f"exit={acct.exit_reason} " + "; ".join(problems))
    except ap.PatchError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    finally:
        if not args.keep:
            try:
                ap.remove_worktree(worktree, env)
            except ap.PatchError as e:
                print(f"warning: could not remove {worktree}: {e}", file=sys.stderr)
    print(f"output: {out_root}")
    return 1 if failures else 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--driver"]:
        raise SystemExit(driver(sys.argv[2:]))
    raise SystemExit(main())
