"""Latency in the study's records, by harness configuration (exploratory; $0).

PREREG registers no latency outcome. The study records latency only as an operational field.
ARC's D20 latency-incident rule reads it (PREREG §7.5, §17.6), and every paid batch's
`costs.csv` row carries the median seconds per call (`latency_s`). ARC's 12 h clock (§17.5)
is a wall-clock limit, which slow calls run into. This script summarizes what those records
hold, by harness configuration. Every number it prints is exploratory. It makes no paid call.

Inputs (all committed):

* ``results/arc_path/<run>/meta.json``: each ARC path run's wall clock (`wall_clock_s`),
  actions (`outcome.n_steps`), ending, re-run link and latency (the median and 90th percentile
  of the seconds per successful model call); the run's ``costs.csv`` row for its tokens.
  Which run counts for each (game, config) is H4's reading's `counted` flag
  (``results/arc_h4/20261012T174002Z/h4.json``): a replaced run (a D19 re-run's original or
  an R7 replacement's) is listed but left out of the per-config summary. A run's calls
  include its summary (compaction) calls, which S1, S2 and S4 make and S0 does not, so the
  per-action columns are the comparable ones across configurations.
* ``results/arc_public_ops/20261001T185155Z/recordings_per_action.csv``: ARC's published
  Gemini 3.8 Flash high-effort recordings (10 games x 2 harnesses). Seconds per step there are
  gaps between recording timestamps (server time), on other dates, so they are not the same
  measure as ours. Both the median step and the mean step (duration / steps) are given.
* ``results/<experiment>/<run>/episodes.jsonl`` for the PersistGym sweeps listed in
  `PERSISTGYM_EXPERIMENTS`: each episode record's `call_latency_s` (the runner's wall-clock
  seconds per call, to the millisecond, retries and their waits included) and `usage`.
  Validity runs and pilots are left out. Every record with at least one call counts
  (`n_records`), API_ERROR and RUN_STOPPED records and re-run duplicates included (DESIGN
  §7.8 is not applied: every call is a latency sample). Cells are pooled by model, tier,
  harness cell and `variant`, so the restated-at-need control (F-0 with variant `restated`)
  is a row of its own. `persistgym_r12_exp1_cells` pools R12 experiment 1 alone, where the
  four notes cells played the same 200 episodes in rotated order on one day.
* ``results/<experiment>/<run>/meta.json`` of those runs: the per-call spend gate's
  `calls_waited` (`calls_gate_waited` here; empty when the run recorded no gate).

The runner's timing and ``costs.csv``'s differ. The runner times the whole send of a call. In
a parallel paid run that includes any wait at the per-call spend gate
(`harnesses.parallel.EpisodeChannel`, `CallGate`), and in every run the transport's own
checks and bookkeeping before and after the call. ``costs.csv``'s `latency_s` is the median of
the transport's timing (`harnesses/pricing.py`), which starts after the gate, except in rows
that `harnesses/account.py` rebuilt for a killed run, which take the runner's timings. Where
the gate held many calls, a run's median here is above its `latency_s`. The cell tables also
give the median over the runs whose gate held no call.

What the numbers are not. Latency here is mostly the provider's response time in the weeks the
runs happened, with retry waits included (and on PersistGym any wait at the spend gate), on
one service tier per model, with up to 16 episodes in flight (PersistGym) or one game at a
time (ARC). It drifted within the study: three of S0's four counted ARC runs took 2.1-2.4
times its pilot's seconds per call (PREREG §17.6). The configurations ran at different times,
and the pooled PersistGym cells mix dates, template sets and numbers of episodes in flight. So
a difference between configurations mixes what the configuration asks of the model with when
and how it ran.

Run: ``uv run python -m analysis.latency_ledger``. It writes
``results/latency_ledger/<UTC>/`` (arc_configs.csv, arc_runs.csv, arc_published.csv,
persistgym_cells.csv, persistgym_r12_exp1_cells.csv, persistgym_runs.csv, summary.md,
meta.json). With ``--no-write`` it only prints.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

from common import runmeta

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLISHED = Path("results/arc_public_ops/20261001T185155Z/recordings_per_action.csv")
H4 = Path("results/arc_h4/20261012T174002Z/h4.json")
PERSISTGYM_EXPERIMENTS = (
    "persistgym",                     # luna's main sweep and repeats (gpt-6-luna, Flex)
    "persistgym_haiku",               # R8
    "persistgym_haiku_notes",         # R9
    "persistgym_haiku_provenance",    # R10
    "persistgym_haiku_control",       # R11
    "persistgym_haiku_r12_notes",     # R12 experiment 1
    "persistgym_sonnet_r12",          # R12 experiment 2, claude-sonnet-5-5
    "persistgym_haiku_r12_block",     # R12 experiment 3
)
R12_EXP1 = "persistgym_haiku_r12_notes"
ARC_CONFIGS = ("S0", "S1", "S2", "S4")
CLOCK_ENDING = "TIME_BUDGET"


def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _p90(xs):
    xs = sorted(xs)
    if not xs:
        return None
    k = max(-(-9 * len(xs) // 10) - 1, 0)    # ceil(0.9 n) - 1, as arc/run_path.py takes it
    return xs[k]


def _r(x, nd=3):
    return None if x is None else round(x, nd)


def costs_rows(root: Path) -> dict[str, dict]:
    with open(root / "results" / "costs.csv", encoding="utf-8", newline="") as f:
        return {r["run_id"]: r for r in csv.DictReader(f)}


# ------------------------------------------------------------------ ARC

def arc_runs(root: Path, costs: dict[str, dict]) -> list[dict]:
    """One row per ARC path run. Keys starting with '_' hold unrounded values for the
    summaries and are not written."""
    counted = {r["run_id"]: r["counted"]
               for r in json.loads((root / H4).read_text(encoding="utf-8"))["runs"]}
    out = []
    for meta_path in sorted((root / "results" / "arc_path").glob("*/meta.json")):
        m = json.loads(meta_path.read_text(encoding="utf-8"))
        run_id = m["run_id"]
        row = costs.get(run_id)
        if row is None:
            raise SystemExit(f"{run_id}: no costs.csv row")
        n_calls = int(row["n_calls"])
        actions = (m.get("outcome") or {}).get("n_steps")
        wall = m["wall_clock_s"]
        reasoning = int(row["reasoning_tokens"])
        out.append({
            "run_id": run_id, "config": m["cell_or_config"], "game": m["template_id"],
            "exit_reason": m["exit_reason"], "rerun_of": m.get("rerun_of") or "",
            "counted": counted[run_id],
            "actions": actions, "n_calls": n_calls, "n_compactions": m.get("n_compactions"),
            "wall_clock_h": _r(wall / 3600, 2),
            "s_per_action": _r(wall / actions, 1) if actions else None,
            "median_s_per_call": m["latency"]["median_s"], "p90_s_per_call": m["latency"]["p90_s"],
            "reasoning_tokens_per_action": round(reasoning / actions) if actions else None,
            "reasoning_tokens_per_call": round(reasoning / n_calls),
            "output_tokens_per_call": round(int(row["output_tokens"]) / n_calls),
            "input_tokens_per_call": round(int(row["input_tokens"]) / n_calls),
            "retries": m["transport_retry"]["retries"],
            "retry_wait_s": m["transport_retry"]["wait_seconds"],
            "_s_per_action": wall / actions if actions else None,
        })
    return out


def arc_configs(runs: list[dict]) -> list[dict]:
    out = []
    for c in ARC_CONFIGS:
        rs = [r for r in runs if r["config"] == c and r["counted"]]
        if not rs:
            continue
        med = [r["median_s_per_call"] for r in rs]
        spa = [r["s_per_action"] for r in rs if r["s_per_action"] is not None]
        rea = [r["reasoning_tokens_per_action"] for r in rs
               if r["reasoning_tokens_per_action"] is not None]
        out.append({
            "config": c, "n_counted_runs": len(rs),
            "games": " ".join(sorted({r["game"] for r in rs})),
            "s_per_action_min": min(spa), "s_per_action_max": max(spa),
            "s_per_action_median": _r(_median([r["_s_per_action"] for r in rs]), 1),
            "median_s_per_call_min": min(med), "median_s_per_call_max": max(med),
            "median_s_per_call_median": _r(_median(med)),
            "wall_clock_h_max": max(r["wall_clock_h"] for r in rs),
            "n_clock_endings": sum(r["exit_reason"] == CLOCK_ENDING for r in rs),
            "reasoning_tokens_per_action_min": min(rea),
            "reasoning_tokens_per_action_max": max(rea),
        })
    return out


def arc_published(root: Path) -> list[dict]:
    with open(root / PUBLISHED, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for h in ("standard", "provider_adapter"):
        rs = [r for r in rows if r["harness"] == h]
        med = [float(r["s_per_step_median"]) for r in rs]
        mean = [float(r["s_per_step_mean"]) for r in rs]
        rea = [float(r["reasoning_per_step_mean"]) for r in rs]
        out.append({
            "harness": h, "n_games": len(rs),
            "s_per_step_median_min": _r(min(med), 1), "s_per_step_median_max": _r(max(med), 1),
            "s_per_step_median_median": _r(_median(med), 1),
            "s_per_step_mean_min": _r(min(mean), 1), "s_per_step_mean_max": _r(max(mean), 1),
            "s_per_step_mean_median": _r(_median(mean), 1),
            "reasoning_per_step_mean_median": round(_median(rea)),
        })
    return out


# ------------------------------------------------------------------ PersistGym

def persistgym_records(root: Path, costs: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """Every episode record with at least one timed call, and one row per run."""
    records, runs = [], []
    for exp in PERSISTGYM_EXPERIMENTS:
        for ep_path in sorted((root / "results" / exp).glob("*/episodes.jsonl")):
            run_id = ep_path.parent.name
            row = costs.get(run_id)
            if row is None:
                raise SystemExit(f"{run_id}: no costs.csv row")
            meta = json.loads((ep_path.parent / "meta.json").read_text(encoding="utf-8"))
            gate = (((meta.get("parallel") or {}).get("spend_reservation") or {})
                    .get("call_gate") or {})
            waited = gate.get("calls_waited") if gate else None
            tier = row["service_tier_served"]
            mine = []
            for line in ep_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                e = json.loads(line)
                lat = e.get("call_latency_s") or []
                if not lat:
                    continue
                mine.append({"experiment": exp, "run_id": run_id, "gate_waited": waited,
                             "model": e["model"], "tier": tier, "cell": e["harness_cell"],
                             "variant": e.get("variant", "base"), "calls": lat,
                             "output_tokens": (e.get("usage") or {}).get("output_tokens", 0)})
            if not mine:
                continue
            records += mine
            calls = [x for r in mine for x in r["calls"]]
            runs.append({
                "experiment": exp, "run_id": run_id,
                "harness_cells": " ".join(sorted({r["cell"] for r in mine})),
                "variants": " ".join(sorted({r["variant"] for r in mine})),
                "tier_served": tier, "n_records": len(mine), "n_calls": len(calls),
                "calls_gate_waited": waited,
                "median_s_per_call": _r(_median(calls)),
                "costs_row_latency_s": float(row["latency_s"]) if row["latency_s"] else None,
                "output_tokens_per_call": round(sum(r["output_tokens"] for r in mine)
                                                / len(calls)),
            })
    return records, runs


def persistgym_cells(records: list[dict]) -> list[dict]:
    pooled: dict[tuple, list[dict]] = {}
    for r in records:
        pooled.setdefault((r["model"], r["tier"], r["cell"], r["variant"]), []).append(r)
    out = []
    for (model, tier, cell, variant), rs in sorted(pooled.items()):
        calls = [x for r in rs for x in r["calls"]]
        waited = {r["run_id"]: r["gate_waited"] for r in rs}
        no_wait = [x for r in rs if r["gate_waited"] == 0 for x in r["calls"]]
        out.append({
            "model": model, "tier_served": tier, "harness_cell": cell, "variant": variant,
            "n_runs": len(waited), "n_records": len(rs), "n_calls": len(calls),
            "n_calls_gate_waited": (None if None in waited.values()
                                    else sum(waited.values())),
            "median_s_per_call": _r(_median(calls)),
            "median_s_per_call_runs_gate_held_none": _r(_median(no_wait)),
            "p90_s_per_call": _r(_p90(calls)),
            "median_calls_per_record": float(_median([len(r["calls"]) for r in rs])),
            "median_model_s_per_record": _r(_median([sum(r["calls"]) for r in rs]), 1),
            "output_tokens_per_call": round(sum(r["output_tokens"] for r in rs) / len(calls)),
        })
    return out


# ------------------------------------------------------------------ output

def _head(rows: list[dict]) -> list[str]:
    return [k for k in rows[0] if not k.startswith("_")]


def _csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=_head(rows), lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def _md(rows: list[dict]) -> str:
    head = _head(rows)
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join("" if r[k] is None else str(r[k]) for k in head) + " |"
              for r in rows]
    return "\n".join(lines)


def summary(tables: dict[str, list[dict]]) -> str:
    parts = ["# Latency in the study's records (exploratory)", "",
             ("Produced by `analysis/latency_ledger.py`. Its docstring says what these numbers "
              "are not. PREREG registers no latency outcome."), ""]
    for name, rows in tables.items():
        parts += [f"## {name}", "", _md(rows), ""]
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")   # the tables hold 'Σ'
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    now = datetime.now(UTC)
    costs = costs_rows(REPO_ROOT)
    runs = arc_runs(REPO_ROOT, costs)
    records, pg_runs = persistgym_records(REPO_ROOT, costs)
    tables = {"arc_configs": arc_configs(runs), "arc_runs": runs,
              "arc_published": arc_published(REPO_ROOT),
              "persistgym_cells": persistgym_cells(records),
              "persistgym_r12_exp1_cells": persistgym_cells(
                  [r for r in records if r["experiment"] == R12_EXP1]),
              "persistgym_runs": pg_runs}
    text = summary(tables)
    print(text)
    if a.no_write:
        return 0
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    out = REPO_ROOT / "results" / "latency_ledger" / run_id
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        (out / f"{name}.csv").write_text(_csv(rows), encoding="utf-8", newline="\n")
    (out / "summary.md").write_text(text, encoding="utf-8", newline="\n")
    outputs = [f"{n}.csv" for n in tables] + ["summary.md", "meta.json"]
    runmeta.write_meta(
        out, git=runmeta.git_state(), experiment="latency_ledger", run_id=run_id,
        cell_or_config="all",
        config={"published": PUBLISHED.as_posix(), "h4": H4.as_posix(),
                "persistgym_experiments": list(PERSISTGYM_EXPERIMENTS), "r12_exp1": R12_EXP1},
        model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
        repeat_index=0, seeds={}, started_utc=now.isoformat(timespec="seconds"),
        finished_utc=runmeta.utc_now(), exit_reason="completed", tokens=None, cost_usd=0.0,
        raw_transcript_path=None, outputs=outputs, paid_calls=0)
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
