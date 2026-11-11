"""R12's runs, one after another, from its committed forecast (PREREG §17.12).

The runs and their stops come from the latest `results/r12_forecast/<UTC>/forecast.json`
(`analysis.r12_forecast`): the pilots, then experiment 1's 16 runs (4 notes arms in rounds of 25
templates, the arms' order rotated each round, so every arm plays at every hour of the run),
experiment 2's 3 Sonnet runs, and experiment 3's 4 W-b-0 runs of 50 templates. Each is a plain
`harnesses run` under block `registered.R12_BLOCK`, whose guard checks it as any other run.

The driver stops at the first run that does not end COMPLETED (a refusal, an API error, a spend
or cost stop), so the researcher is told before anything else runs (DESIGN §7.9).

    uv run python -m harnesses.r12_rounds --part pilots --dry-run   # print the commands only
    uv run --env-file .env python -m harnesses.r12_rounds --part pilots   # paid: run them
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from harnesses import registered

REPO = Path(__file__).resolve().parent.parent
PARTS = ("pilots", "notes", "sonnet", "block")
PART_EXPERIMENT = {"notes": registered.R12_NOTES_EXPERIMENT,
                   "sonnet": registered.R12_SONNET_EXPERIMENT,
                   "block": registered.R12_BLOCK_EXPERIMENT}
PARALLEL = 2
"""As R11: the organization's 2,000,000 input tokens a minute for Haiku hold about two window
episodes at once (results/decisions.md, 2026-11-06)."""


def latest_forecast(root: Path = REPO) -> dict:
    folder = root / "results" / "r12_forecast"
    runs = sorted(p for p in folder.iterdir() if (p / "forecast.json").exists())
    if not runs:
        raise SystemExit(f"no forecast under {folder}: run `python -m analysis.r12_forecast`")
    return json.loads((runs[-1] / "forecast.json").read_text(encoding="utf-8"))


def _run_args(cell: str, model: str, experiment: str, split: str, start: int, n: int,
              task_cells: tuple[str, ...], planned: float) -> list[str]:
    return ["run", "--cell", cell, "--model", model, "--split", split, "--start", str(start),
            "--n", str(n), "--task-cell", *task_cells, "--experiment", experiment,
            "--approved-block", registered.R12_BLOCK, "--planned-usd", f"{planned:.2f}",
            "--parallel", str(PARALLEL)]


def commands(part: str, forecast: dict) -> list[list[str]]:
    """The `harnesses` argument lists of one part, in run order."""
    if part == "pilots":
        out = []
        for p in forecast["pilots"]:
            task_cells = registered.R12_PILOTS[(p["model"], p["cell"])]
            first, stop = registered.R12_PILOT_TEMPLATES
            n = min(stop - first, registered.R12_PILOT_MAX_EPISODES // len(task_cells))
            out.append(_run_args(p["cell"], p["model"], registered.PILOT_EXPERIMENT, "pilot",
                                 first, n, task_cells,
                                 p["planned_usd"]))
        return out
    experiment = PART_EXPERIMENT[part]
    task_cells = registered.R12_SPECS[experiment]["task_cells"]
    return [_run_args(r["cell"], r["model"], experiment, "main", r["templates"][0],
                      r["templates"][1] - r["templates"][0], task_cells, r["planned_usd"])
            for r in forecast["runs"] if r["experiment"] == experiment]


def _paid_subprocess(args: list[str]) -> tuple[int, str]:
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_BASE_URL"}
    env["PERSISTGYM_ALLOW_PAID"] = "1"
    p = subprocess.run([sys.executable, "-m", "harnesses", *args], cwd=REPO, env=env,
                       capture_output=True, text=True, encoding="utf-8", check=False)
    sys.stderr.write(p.stderr)
    return p.returncode, p.stdout


def exit_reason(stdout: str) -> str | None:
    """The `exit_reason` of the JSON `harnesses run` prints last, or None."""
    start = stdout.rfind("{\n")
    try:
        return json.loads(stdout[start:])["exit_reason"] if start >= 0 else None
    except (ValueError, KeyError):
        return None


def drive(cmds: list[list[str]], run: Callable[[list[str]], tuple[int, str]] = _paid_subprocess
          ) -> tuple[int, int]:
    """Run `cmds` in order; stop at the first that does not exit 0 and end COMPLETED. Returns
    (runs completed, exit code: 0, or 2 for a stop)."""
    for i, args in enumerate(cmds):
        print(f"[{i + 1}/{len(cmds)}] harnesses {' '.join(args)}", flush=True)
        code, out = run(args)
        reason = exit_reason(out)
        print(out, flush=True)
        if code != 0 or reason != "COMPLETED":
            print(f"stopped: run {i + 1} ended with code {code}, exit_reason {reason}; tell the "
                  "researcher before anything else runs", file=sys.stderr)
            return i, 2
    return len(cmds), 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", choices=PARTS, required=True)
    ap.add_argument("--dry-run", action="store_true", help="print the commands only")
    a = ap.parse_args(argv)
    cmds = commands(a.part, latest_forecast())
    if a.dry_run:
        for args in cmds:
            print("harnesses " + " ".join(args))
        return 0
    return drive(cmds)[1]


if __name__ == "__main__":
    raise SystemExit(main())
