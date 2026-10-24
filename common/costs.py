"""Append-only cost log (results/costs.csv) and phase-cap checks.

Every paid call batch gets one row. Before each paid block, run
`uv run python -m common.costs` and compare the sums with the caps in PLAN.md §12 (as amended
by A2, §17.3).
Exceeding a cap requires the researcher's explicit approval first.

Spend against a cap is measured by `spend_usd`: the billed estimate, or the list cost where
a row has no billed estimate. Both columns stay in every row and both sums are printed.

An ARC run and a PersistGym run may go at the same time (PREREG §0.3 line 15, §12) and append
their rows at the same moment. `append_row` and `read_rows` therefore hold an operating-system
lock on the file (common/oslock.py): rows never interleave, and a reader sees each row whole
or not at all. Code that writes this file by other means does not take that lock.
"""

from __future__ import annotations

import csv
import io
import math
import os
import sys
from pathlib import Path

from common import oslock

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
    # PREREG §17.4 (amendment R4): sol's H1 replication, its main runs (its pilot and
    # validity runs are persistgym_pilot and persistgym_validity)
    "persistgym_sol_h1": "1a",
    # PREREG §17.8 (amendment R8): claude-haiku-5-5's replication of H1/H3, its main runs
    # and controls (its pilots and validity run are persistgym_pilot and
    # persistgym_validity); harnesses/registered.py haiku_refusal holds every Haiku paid run
    # to R8 (its main runs after HAIKU_G1_PASSED), and every one refuses if the kill switch
    # R8_IN_EFFECT is set False
    "persistgym_haiku": "1a",
    # PREREG §17.9 (amendment R9): claude-haiku-5-5's W-n-0 cell, one exploratory run with R8's
    # settings (harnesses/registered.py _haiku_notes_refusal; kill switch R9_IN_EFFECT)
    "persistgym_haiku_notes": "1a",
    "arc_path": "1b",
    "statecarry_persistgym": "2",
    "statecarry_arc_dev": "2",
    "statecarry_heldout": "2",
}


def append_row(row: dict, path: Path = COSTS_CSV) -> None:
    """Append one validated row. Never rewrites existing rows.

    Safe when two processes append at once (an ARC run and a PersistGym run, PREREG §0.3
    line 15, §12): the append holds the ledger's operating-system lock (common/oslock.py),
    which `read_rows` takes too, so rows never interleave and a reader never sees half a row.
    Under the lock it writes the whole row in one go at the end of the file, after a line
    break if the last line lacks one (a row torn by a crash is then a separate, unreadable
    row that the paid guard refuses, not glued to this one), and flushes it to disk. A file
    that is missing or empty gets the header first."""
    row = {**{c: "" for c in OPTIONAL_COLUMNS}, **row}
    missing = [c for c in COLUMNS if c not in row]
    extra = [k for k in row if k not in COLUMNS]
    if missing or extra:
        raise ValueError(f"costs.csv row mismatch: missing={missing} extra={extra}")
    if row["experiment"] not in EXPERIMENT_PHASE and not str(row["experiment"]).startswith("ext_"):
        raise ValueError(f"unknown experiment {row['experiment']!r}; add it to EXPERIMENT_PHASE")
    buf = io.StringIO(newline="")
    # LF-terminated, as git stores the file (rows appended before 2026-10-19 ended "\r\n" in
    # Windows working copies; `read_rows` reads both alike)
    csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n").writerow(row)
    data = buf.getvalue().encode("utf-8")
    with oslock.locked(path, os.O_RDWR | os.O_CREAT | os.O_APPEND) as fd:
        size = os.lseek(fd, 0, os.SEEK_END)
        if size == 0:
            data = (",".join(COLUMNS) + "\n").encode("utf-8") + data
        else:
            os.lseek(fd, size - 1, os.SEEK_SET)
            last = os.read(fd, 1)
            if last != b"\n":   # a torn last line (ended by its CR, or by nothing)
                data = b"\n" + data
            os.lseek(fd, 0, os.SEEK_END)
        oslock.write_all(fd, data)
        os.fsync(fd)


def read_rows(path: Path = COSTS_CSV) -> list[dict]:
    """Every row, read under the ledger's lock (see `append_row`), so a row another process
    is appending is read whole or not at all."""
    with oslock.locked(path) as fd:
        data = oslock.read_all(fd)
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
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
