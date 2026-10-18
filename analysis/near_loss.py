"""Expected near losses in a model's pilots (PREREG §2.8), pooled, before its main sweep.

Run: `uv run python -m analysis.near_loss [--raw-root DIR] [--model MODEL]` ($0; reads files
only). The model defaults to gpt-6-luna (its block-1 pilots); claude-haiku-5-5 for amendment R8
(PREREG §17.8: near losses above 2% are reported, not re-tuned, and Claude stops and asks).

PREREG §2.8: in near window cells `S_planned` = 1 by design, but `S_verbatim` = 0 can happen
without a bug, when visible replies longer than R_plan or lookup responses push the evidence
out. "If they exceed 2% of any near window cell in the block-1 pilots (pooled tokens only, §11),
R_plan or W is re-tuned under §4.2 before the main sweep."

Pilot blinding (§11) withholds per-arm success. This script reads only each episode's
`harness_cell`, `task_cell` and `need_payload.S` (verbatim survival of the evidence in the
payload sent at the need step, §2.8), never correctness, and prints only the count pooled over
the near window episodes. If that count is 0, every near window cell is at 0% and the rule
cannot fire. If it is above 0, the script prints no per-cell count and says so: the per-cell
reading then needs the researcher's go-ahead.

The raw pilot episodes are gitignored (`results/raw/persistgym_pilot/<run_id>/episodes.jsonl`),
so this runs in the checkout that holds them (the default root) or with `--raw-root`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import runmeta

MODEL = "gpt-6-luna"
WINDOW_CELLS = ("W-0", "W-n-0")          # the replay-off window cells luna's pilots played


def harness_cell(run_name: str, model: str = MODEL) -> str:
    """`20261002T082913Z-W-0-gpt-6-luna` -> `W-0`."""
    return run_name.split("Z-", 1)[1].rsplit(f"-{model}", 1)[0]


def pooled_near_losses(raw_pilot: Path, model: str = MODEL) -> dict:
    runs, near, lost, missing = [], 0, 0, 0
    for run in sorted(raw_pilot.glob(f"*-{model}")):
        if harness_cell(run.name, model) not in WINDOW_CELLS:
            continue
        runs.append(run.name)
        for line in (run / "episodes.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if not e["task_cell"].endswith("-near"):
                continue
            near += 1
            s = (e.get("need_payload") or {}).get("S")
            if s is None:
                missing += 1
            elif s is False:
                lost += 1
    return {"runs": runs, "near_window_episodes": near, "near_lost_pooled": lost,
            "S_missing": missing, "rule_cannot_fire": near > 0 and lost == 0 and missing == 0}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--raw-root", type=Path, default=runmeta.REPO_ROOT / "results" / "raw")
    ap.add_argument("--model", default=MODEL, help=f"default: {MODEL}")
    a = ap.parse_args(argv)
    r = pooled_near_losses(a.raw_root / "persistgym_pilot", a.model)
    print(json.dumps(r, indent=2))
    if r["rule_cannot_fire"]:
        print("Pooled near losses are 0: every near window cell is at 0%, under the 2% rule "
              "(PREREG §2.8). No re-tuning.")
        return 0
    print("Pooled near losses are above 0 or unreadable: the per-cell reading needs the "
          "researcher's go-ahead (pilot blinding, §11).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
