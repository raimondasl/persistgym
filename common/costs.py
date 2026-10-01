"""Append-only cost log (results/costs.csv) and phase-cap checks.

Every paid call batch gets one row. Before each paid block, run
`uv run python -m common.costs` and compare the sums with the caps in PLAN.md §12.
Exceeding a cap requires the researcher's explicit approval first.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COSTS_CSV = REPO_ROOT / "results" / "costs.csv"

COLUMNS = [
    "timestamp_utc", "run_id", "milestone", "experiment", "cell_or_config",
    "model_requested", "model_returned", "provider", "api", "service_tier",
    "n_calls", "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens",
    "cost_usd_list", "cost_usd_billed_est", "price_source_date", "git_commit", "notes",
]

# Hard caps per budget phase, PLAN.md §12 (USD). Stop and ask the researcher before exceeding.
PHASE_CAPS = {"0": 100.0, "1a": 450.0, "1b": 900.0, "2": 950.0}

# Which budget phase each `experiment` value counts toward (PLAN.md §12 and amendment A1).
EXPERIMENT_PHASE = {
    "toggle_pilot": "0",
    "replay_probe": "0",
    "gemini_probe": "0",
    "arc_pilot": "0",
    "persistgym_pilot": "1a",
    "persistgym_validity": "1a",
    "persistgym": "1a",
    "arc_path": "1b",
    "statecarry_persistgym": "2",
    "statecarry_arc_dev": "2",
    "statecarry_heldout": "2",
}


def append_row(row: dict, path: Path = COSTS_CSV) -> None:
    """Append one validated row. Never rewrites existing rows."""
    missing = [c for c in COLUMNS if c not in row]
    extra = [k for k in row if k not in COLUMNS]
    if missing or extra:
        raise ValueError(f"costs.csv row mismatch: missing={missing} extra={extra}")
    if row["experiment"] not in EXPERIMENT_PHASE and not str(row["experiment"]).startswith("ext_"):
        raise ValueError(f"unknown experiment {row['experiment']!r}; add it to EXPERIMENT_PHASE")
    with path.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=COLUMNS).writerow(row)


def read_rows(path: Path = COSTS_CSV) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != COLUMNS:
            raise ValueError(f"unexpected costs.csv header: {reader.fieldnames}")
        return list(reader)


def phase_of(experiment: str) -> str:
    return EXPERIMENT_PHASE.get(experiment, "ext" if experiment.startswith("ext_") else "?")


def sums_by_phase(rows: list[dict], field: str = "cost_usd_billed_est") -> dict[str, float]:
    sums: dict[str, float] = {p: 0.0 for p in PHASE_CAPS}
    for r in rows:
        p = phase_of(r["experiment"])
        sums[p] = sums.get(p, 0.0) + float(r[field] or 0.0)
    return sums


def headroom(planned_usd: float, phase: str, rows: list[dict]) -> float:
    """Cap minus (spent + planned) for a phase; negative means the block would exceed the cap."""
    spent = max(sums_by_phase(rows, "cost_usd_billed_est")[phase],
                sums_by_phase(rows, "cost_usd_list")[phase])
    return PHASE_CAPS[phase] - spent - planned_usd


def main() -> int:
    rows = read_rows()
    billed, listed = sums_by_phase(rows), sums_by_phase(rows, "cost_usd_list")
    print(f"{'phase':<6}{'billed_est':>12}{'list':>12}{'cap':>10}")
    for p in sorted(set(billed) | set(listed)):
        cap = PHASE_CAPS.get(p)
        print(f"{p:<6}{billed.get(p, 0):>12.2f}{listed.get(p, 0):>12.2f}"
              f"{(f'{cap:.0f}' if cap else '-'):>10}")
    print(f"total {sum(billed.values()):>11.2f}{sum(listed.values()):>12.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
