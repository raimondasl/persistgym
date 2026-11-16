"""R13's runs, one after another, from its committed forecast (PREREG §17.13).

The runs and their stops come from the latest `results/r13_forecast/<UTC>/forecast.json`
(`analysis.r13_forecast`): the pilots, then experiment 4's 4 Σ-n-0 runs of 50 templates on all
8 task cells, and experiment 5's 8 runs, W-nk-0 and a concurrent W-n-0 in 4 rounds of 25
templates, one run of each arm a round, W-nk-0 first in rounds 1 and 3 and W-n-0 first in
rounds 2 and 4 (`registered.r13_round_arms`). Each is a plain `harnesses run` under block
`registered.R13_BLOCK`, whose guard checks it as any other run. The driver takes each part's
runs in the forecast's order and refuses a forecast whose runs are not the part's registered
runs in their registered order, so a round never plays out of turn.

R13 is prepared, not run: until the researcher merges block 9-r13's approval line into
results/decisions.md, the paid guard (common/approval.py) refuses every one of these runs
before any call. The full block would pass phase 1a's $620 cap, so the pull request that adds
the line also raises the cap. The guard checks each run's stop against the cap's headroom when
the run starts, and before a part starts the driver checks that the stops of all its runs left
fit (`cap_refusal`), so a part that cannot finish does not start.

The driver never arms paid calls itself: as for every paid command, the operator sets
`PERSISTGYM_ALLOW_PAID=1` for this one command (DESIGN §8), and without it the driver refuses
before running anything. It stops at the first run that does not end COMPLETED (a refusal, an
API error, a spend or cost stop), so the researcher is told before anything else runs
(DESIGN §7.9). After a stop, a run that ended early is continued under DESIGN §7.9, and the
part resumes at the next run with `--from N` (1-based), never by running the part again.

    uv run python -m harnesses.r13_rounds --part pilots --dry-run   # print the commands only
    PERSISTGYM_ALLOW_PAID=1 env -u ANTHROPIC_BASE_URL uv run --env-file .env \\
        python -m harnesses.r13_rounds --part pilots                 # paid: run them
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from common import costs
from common.approval import ALLOW_ENV
from harnesses import registered
from harnesses.cells import get_cell

REPO = Path(__file__).resolve().parent.parent
PARTS = ("pilots", "sigma", "pinned")
PART_EXPERIMENT = {"sigma": registered.R13_SIGMA_EXPERIMENT,
                   "pinned": registered.R13_PINNED_EXPERIMENT}
PARALLEL = 2
"""As R11 and R12: the organization's 2,000,000 input tokens a minute for Haiku hold about two
window episodes at once (results/decisions.md, 2026-11-06)."""


def latest_forecast(root: Path = REPO) -> dict:
    folder = root / "results" / "r13_forecast"
    runs = sorted(p for p in folder.iterdir() if (p / "forecast.json").exists()) \
        if folder.is_dir() else []
    if not runs:
        raise SystemExit(f"no forecast under {folder}: run `python -m analysis.r13_forecast`")
    return json.loads((runs[-1] / "forecast.json").read_text(encoding="utf-8"))


def planned_runs(part: str) -> list[tuple[str, int, int]]:
    """A main part's registered runs, in run order, as (cell, first template, templates):
    experiment 4 in runs of `R13_SIGMA_RUN_TEMPLATES`, experiment 5 in rounds of
    `R13_ROUND_TEMPLATES` with both arms each round in `r13_round_arms`' order."""
    experiment = PART_EXPERIMENT[part]
    first, stop = registered.R13_SPECS[experiment]["templates"]
    if part == "sigma":
        (cell,) = registered.R13_SPECS[experiment]["cells"]
        n = registered.R13_SIGMA_RUN_TEMPLATES
        return [(cell, start, n) for start in range(first, stop, n)]
    n = registered.R13_ROUND_TEMPLATES
    return [(cell, first + k * n, n) for k in range((stop - first) // n)
            for cell in registered.r13_round_arms(k)]


def _run_args(cell: str, model: str, experiment: str, split: str, start: int, n: int,
              task_cells: tuple[str, ...], planned: float) -> list[str]:
    """One `harnesses run` argument list. The cell goes by its ASCII id (Σ-n-0 as
    sigma-n-0), which `harnesses run` reads as the same cell, so the commands print and log
    as plain ASCII on any console."""
    return ["run", "--cell", get_cell(cell).ascii_id, "--model", model, "--split", split,
            "--start", str(start), "--n", str(n), "--task-cell", *task_cells,
            "--experiment", experiment, "--approved-block", registered.R13_BLOCK,
            "--planned-usd", f"{planned:.2f}", "--parallel", str(PARALLEL)]


def commands(part: str, forecast: dict) -> list[list[str]]:
    """The `harnesses` argument lists of one part, in run order. Raises ValueError for a
    forecast whose pilots are not exactly `R13_PILOTS`' pairs at the size the driver plays,
    or whose runs of a main part are not `planned_runs(part)` in that order, and KeyError for
    a key or cell it lacks."""
    if part == "pilots":
        pilots = [(get_cell(p["cell"]).cell_id, p) for p in forecast["pilots"]]
        pairs = sorted((p["model"], cell) for cell, p in pilots)
        if pairs != sorted(registered.R13_PILOTS):
            raise ValueError(f"the forecast's pilots are {pairs}, not R13's "
                             f"{sorted(registered.R13_PILOTS)} ({registered.R13_REF})")
        out = []
        first, stop = registered.R13_PILOT_TEMPLATES
        for cell, p in pilots:
            task_cells = registered.R13_PILOTS[(p["model"], cell)]
            n = min(stop - first, registered.R13_PILOT_MAX_EPISODES // len(task_cells))
            if p["episodes"] != n * len(task_cells):
                raise ValueError(f"the forecast prices {p['episodes']} episodes for the "
                                 f"{p['model']} {cell} pilot, which plays {n * len(task_cells)}")
            out.append(_run_args(cell, p["model"], registered.PILOT_EXPERIMENT, "pilot",
                                 first, n, task_cells, p["planned_usd"]))
        return out
    experiment = PART_EXPERIMENT[part]
    task_cells = registered.R13_SPECS[experiment]["task_cells"]
    runs = [r for r in forecast["runs"] if r["experiment"] == experiment]
    got = [(get_cell(r["cell"]).cell_id, r["templates"][0],
            r["templates"][1] - r["templates"][0]) for r in runs]
    if got != planned_runs(part):
        raise ValueError(f"the forecast's {experiment} runs are {got}, not R13's "
                         f"{planned_runs(part)} in that order ({registered.R13_REF})")
    return [_run_args(cell, r["model"], experiment, "main", start, n, task_cells,
                      r["planned_usd"]) for (cell, start, n), r in zip(got, runs, strict=True)]


def _paid_subprocess(args: list[str]) -> tuple[int, str]:
    """One `harnesses run` in a child process: the parent's environment as it is (the paid
    switch passes through only if the operator set it, and the transport refuses a custom base
    URL at $0), stdout captured for the result, stderr shown live."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    p = subprocess.run([sys.executable, "-m", "harnesses", *args], cwd=REPO, env=env,
                       stdout=subprocess.PIPE, stderr=None, text=True, encoding="utf-8",
                       errors="replace", check=False)
    return p.returncode, p.stdout


def exit_reason(stdout: str) -> str | None:
    """The `exit_reason` of the JSON object `harnesses run` prints last (indented, so its top
    level starts at column 0 and nested objects do not), or None."""
    start = stdout.rfind("\n{")
    start = 0 if start < 0 and stdout.startswith("{") else start + 1
    if start <= 0 and not stdout.startswith("{"):
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(stdout[start:])
    except ValueError:
        return None
    return obj.get("exit_reason") if isinstance(obj, dict) else None


def drive(cmds: list[list[str]], run: Callable[[list[str]], tuple[int, str]] = _paid_subprocess,
          first: int = 1) -> tuple[int, int]:
    """Run `cmds[first - 1:]` in order; stop at the first that does not exit 0 and end
    COMPLETED. Returns (runs completed in this call, exit code: 0, or 2 for a stop)."""
    done = 0
    for i in range(first - 1, len(cmds)):
        args = cmds[i]
        print(f"[{i + 1}/{len(cmds)}] harnesses {' '.join(args)}", flush=True)
        code, out = run(args)
        reason = exit_reason(out)
        print(out, flush=True)
        if code != 0 or reason != "COMPLETED":
            print(f"stopped: run {i + 1} ended with code {code}, exit_reason {reason}; tell the "
                  f"researcher before anything else runs. Continue an early-ended run under "
                  f"DESIGN §7.9, then resume the part with --from {i + 2}", file=sys.stderr)
            return done, 2
        done += 1
    return done, 0


def cap_refusal(cmds: list[list[str]], rows: list[dict]) -> str | None:
    """Why a part must not start, or None: the stops (`--planned-usd`) of the runs it has left,
    summed by phase (`common.costs.EXPERIMENT_PHASE`), do not all fit in what the phase's cap
    leaves (`costs.headroom`, from the ledger `rows`). The paid guard checks each run's stop
    against the cap when the run starts. Checking the whole part first means a part that cannot
    finish does not start, so experiment 5 never ends between rounds for want of room."""
    need: dict[str, float] = {}
    for args in cmds:
        experiment = args[args.index("--experiment") + 1]
        planned = float(args[args.index("--planned-usd") + 1])
        phase = costs.phase_of(experiment)
        if phase not in costs.PHASE_CAPS:
            return f"experiment {experiment} has no phase cap (common/costs.py)"
        need[phase] = need.get(phase, 0.0) + planned
    for phase, usd in sorted(need.items()):
        left = costs.headroom(0.0, phase, rows)
        if usd > left + 1e-9:
            return (f"the part's {len(cmds)} runs left need ${usd:.2f} by their stops and phase "
                    f"{phase}'s cap (${costs.PHASE_CAPS[phase]:.2f}, common/costs.py) leaves "
                    f"${left:.2f}: the pull request that approves block {registered.R13_BLOCK} "
                    "also raises the cap (PREREG §17.13, Budget)")
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", choices=PARTS, required=True)
    ap.add_argument("--from", dest="first", type=int, default=1, metavar="N",
                    help="start at the part's N-th run (1-based), after a stop")
    ap.add_argument("--dry-run", action="store_true", help="print the commands only")
    a = ap.parse_args(argv)
    try:
        cmds = commands(a.part, latest_forecast())
    except (KeyError, ValueError) as e:  # a key or cell the forecast lacks, or a wrong run
        print(f"refused: {e}; nothing was run", file=sys.stderr)
        return 2
    if not 1 <= a.first <= len(cmds):
        print(f"refused: --from is 1 to {len(cmds)} for part {a.part}", file=sys.stderr)
        return 2
    if a.dry_run:
        for i, args in enumerate(cmds[a.first - 1:], a.first):
            print(f"[{i}/{len(cmds)}] harnesses " + " ".join(args))
        return 0
    if os.environ.get(ALLOW_ENV) != "1":
        print(f"refused: set {ALLOW_ENV}=1 for this one command to run paid calls "
              "(DESIGN §8); nothing was run", file=sys.stderr)
        return 2
    why = cap_refusal(cmds[a.first - 1:], costs.read_rows())
    if why is not None:
        print(f"refused: {why}; nothing was run", file=sys.stderr)
        return 2
    return drive(cmds, first=a.first)[1]


if __name__ == "__main__":
    raise SystemExit(main())
