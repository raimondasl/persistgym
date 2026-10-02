"""Append-only cost log (results/costs.csv) and phase-cap checks.

Every paid call batch gets one row. Before each paid block, run
`uv run python -m common.costs` and compare the sums with the caps in PLAN.md §12 (as amended
by A2, §17.3).
Exceeding a cap requires the researcher's explicit approval first.

Spend against a cap is measured by `spend_usd`: the billed estimate, or the list cost where
a row has no billed estimate. Both columns stay in every row and both sums are printed.
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COSTS_CSV = REPO_ROOT / "results" / "costs.csv"

COLUMNS = [
    "timestamp_utc", "run_id", "milestone", "experiment", "cell_or_config",
    "model_requested", "model_returned", "provider", "api", "service_tier", "service_tier_served",
    "n_calls", "input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens",
    "reasoning_tokens", "latency_s",
    "cost_usd_list", "cost_usd_billed_est", "price_source_date", "git_commit", "notes",
]

# Added 2026-10-01 (researcher-approved schema change). Optional in append_row: empty when
# the provider does not report them, so writers built before the change keep working.
OPTIONAL_COLUMNS = {"service_tier_served", "cache_write_tokens", "latency_s"}

# Hard caps per budget phase (USD): PLAN.md §12 as amended by A2 (§17.3, 2026-10-01): 1a 450 -> 500,
# 2 950 -> 1250, both approved by the researcher. Stop and ask the researcher before exceeding.
# tests/test_common.py checks that this matches the §17.3 table.
PHASE_CAPS = {"0": 100.0, "1a": 500.0, "1b": 900.0, "2": 1250.0}

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
    row = {**{c: "" for c in OPTIONAL_COLUMNS}, **row}
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


def spend_usd(cost_usd_list, cost_usd_billed_est):
    """Spend as every budget check measures it: the billed estimate, or the list cost when the
    billed estimate is missing (None). Raises ValueError when both are missing: such a row
    cannot be counted, and the paid guard refuses it (`common.approval.check_ledger`).

    Block spend against an approval's max_usd, the phase caps (`headroom`), a run's stop at its
    planned spend (the transport's `spent_usd`) and the split of `--planned-usd` over a
    probe's models all use this one function, re-exported as `common.approval.spend_usd`.

    Why billed: every cap and estimate for PersistGym in PLAN §12, §16 and §17 is in
    Flex-billed dollars, and D23 makes the billed estimate the primary cost basis. On Flex the
    list cost is twice the billed estimate, so counting it would trip the caps at about half
    the real spend. The billed estimate is what the researcher pays: the Flex price for Flex
    runs, with cached and cache-write input at their own prices (`harnesses.pricing`). The
    list cost stays in every costs.csv row and in reports.

    It is an estimate from our price table. The provider-side hard spend limits, which the
    researcher sets in real billed dollars, remain the backstop if it under-estimates."""
    if cost_usd_billed_est is not None:
        return cost_usd_billed_est
    if cost_usd_list is not None:
        return cost_usd_list
    raise ValueError("no cost: cost_usd_billed_est and cost_usd_list are both empty")


def _amount(value) -> float | None:
    s = (value or "").strip()
    if not s:
        return None
    x = float(s)
    if not math.isfinite(x) or x < 0:  # a NaN would pass every cap comparison
        raise ValueError(f"{s!r} is not a finite, non-negative amount")
    return x


def spend_by_phase(rows: list[dict]) -> dict[str, float]:
    """Sum of `spend_usd` per budget phase. Raises ValueError for a row with no cost."""
    sums: dict[str, float] = {p: 0.0 for p in PHASE_CAPS}
    for i, r in enumerate(rows, 2):  # line 1 is the header
        try:
            spent = spend_usd(_amount(r.get("cost_usd_list")),
                              _amount(r.get("cost_usd_billed_est")))
        except ValueError as e:
            raise ValueError(f"costs.csv line {i}: {e}") from None
        p = phase_of(r["experiment"])
        sums[p] = sums.get(p, 0.0) + spent
    return sums


def headroom(planned_usd: float, phase: str, rows: list[dict]) -> float:
    """Cap minus (spent + planned) for a phase; negative means the block would exceed the cap.
    Spent is the phase's `spend_usd`: billed estimates, list cost only where a row has no
    billed estimate."""
    return PHASE_CAPS[phase] - spend_by_phase(rows).get(phase, 0.0) - planned_usd


def main() -> int:
    rows = read_rows()
    try:
        spent = spend_by_phase(rows)
        billed, listed = sums_by_phase(rows), sums_by_phase(rows, "cost_usd_list")
    except ValueError as e:
        print(f"cannot sum spend: {e}", file=sys.stderr)
        return 1
    print("spend: billed estimate, list where a row has none (what the caps count)")
    print(f"{'phase':<6}{'spend':>12}{'billed_est':>12}{'list':>12}{'cap':>10}")
    for p in sorted(set(billed) | set(listed) | set(spent)):
        cap = PHASE_CAPS.get(p)
        print(f"{p:<6}{spent.get(p, 0):>12.2f}{billed.get(p, 0):>12.2f}"
              f"{listed.get(p, 0):>12.2f}{(f'{cap:.0f}' if cap else '-'):>10}")
    print(f"{'total':<6}{sum(spent.values()):>12.2f}{sum(billed.values()):>12.2f}"
          f"{sum(listed.values()):>12.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
