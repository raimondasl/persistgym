"""Pilot blinding (PREREG §11; PLAN §16.5).

> Pilots report only validity levels, pooled tokens, errors, latency and cost; never per-arm
> success, per-arm reasoning tokens (H2's token outcome) or per-config ARC level progress.

For an experiment in `BLINDED_EXPERIMENTS`:
* `runner.run_batch` writes `episodes.jsonl` (per-episode outcomes: `need_correct`, the
  need-phase tokens, per-episode usage, lookups) only under the gitignored
  `results/raw/<experiment>/<run_id>/`;
* the committed `results/<experiment>/<run_id>/` gets `meta.json`, whose `tokens` leave out
  `reasoning_tokens`, and `summary.json` (`run_summary`): errors, latency, cost and the
  echo-match rate, nothing else;
* the transport's `results/costs.csv` row leaves `reasoning_tokens` empty;
* `pooled_report` (CLI `pilot-report`) is the committed script that reads the raw episodes
  of every run and reports, per model, pooled tokens (summed over the harness cells run),
  validity levels of the restated and withheld variants, errors, latency, cost and the
  per-cell echo-match rate (exempt: a toggle check, not an outcome; PREREG §11, D29).

Both summaries are built from an allowlist of fields, so a field added to `EpisodeRun` later
never reaches a committed pilot file by accident.

What this does not blind: the per-run `results/costs.csv` row (CLAUDE.md requires one per
run) and the run's `meta.json` token totals still carry that run's input and output tokens,
calls and cost, and one run is one harness cell. Output tokens are mostly reasoning tokens,
so they approximate the withheld column; n_calls approximates lookups. Only the explicit
`reasoning_tokens` fields are left empty.

The CLI also refuses pilot-split templates under any other experiment, and `run_batch`
refuses a run id that is not a plain folder name, so pilot episodes cannot be written
outside results/raw/ by either route.
"""

from __future__ import annotations

import json
import math
import statistics
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

BLINDED_EXPERIMENTS = frozenset({"persistgym_pilot"})
WITHHELD_NOTE = "reasoning_tokens withheld: pilot blinding (PREREG §11)"
VALIDITY_VARIANTS = ("restated", "withheld")
TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens",
                "reasoning_tokens")


def is_blinded(experiment: str) -> bool:
    return experiment in BLINDED_EXPERIMENTS


def blinded_tokens(tokens: dict) -> dict:
    """Run-level token totals that a blinded run may commit: all but reasoning (None)."""
    return {**tokens, "reasoning_tokens": None}


# --- pieces shared by the run summary and the pooled report -----------------------------

def _errors(eps: list[dict]) -> dict:
    return {
        "exit_reasons": dict(sorted(Counter(e["exit_reason"] for e in eps).items())),
        "n_excluded": sum(bool(e.get("excluded")) for e in eps),
        "n_summary_failures": sum(int(e.get("n_summary_failures") or 0) for e in eps),
        "n_unparsed_routine": sum(int(e.get("n_unparsed_routine") or 0) for e in eps),
    }


def _latency(values: Iterable[float]) -> dict:
    v = sorted(float(x) for x in values)
    if not v:
        return {"n_calls": 0, "median_s": None, "p90_s": None, "max_s": None}
    p90 = v[max(math.ceil(0.9 * len(v)) - 1, 0)]  # nearest rank
    return {"n_calls": len(v), "median_s": round(statistics.median(v), 3),
            "p90_s": round(p90, 3), "max_s": round(v[-1], 3)}


def _cost(eps: list[dict]) -> dict:
    out = {}
    for key in ("cost_usd_list", "cost_usd_billed_est"):
        vals = [e.get(key) for e in eps]
        out[key] = None if None in vals else round(sum(vals), 6)
    return out


def _echo_match(eps: list[dict]) -> dict:
    """Per harness cell: requests and how many echoed the requested reasoning.context."""
    out: dict[str, dict[str, int]] = {}
    for e in eps:
        echo = e.get("echo") or {}
        want = str(echo.get("context_requested"))
        got = echo.get("context_echoed") or {}
        d = out.setdefault(e["harness_cell"], {"requests": 0, "matched": 0})
        d["requests"] += sum(got.values())
        d["matched"] += int(got.get(want, 0))
    return dict(sorted(out.items()))


def run_summary(eps: list[dict], *, blinded: bool) -> dict:
    """The committed summary of one run (one harness cell). Allowlisted fields only."""
    return {
        "blinded": blinded,
        "n_episodes": len(eps),
        "errors": _errors(eps),
        "latency": _latency(x for e in eps for x in e.get("call_latency_s") or []),
        "cost_usd": _cost(eps),
        "echo_match": _echo_match(eps),
    }


# --- the pooled pilot report ---------------------------------------------------------------

def load_raw_runs(raw_root: Path, experiment: str) -> dict[str, list[dict]]:
    """run_id -> episode records, from results/raw/<experiment>/<run_id>/episodes.jsonl."""
    runs: dict[str, list[dict]] = {}
    base = raw_root / experiment
    for path in sorted(base.glob("*/episodes.jsonl")) if base.exists() else []:
        lines = path.read_text(encoding="utf-8").splitlines()
        runs[path.parent.name] = [json.loads(x) for x in lines if x.strip()]
    return runs


def _validity_levels(eps: list[dict]) -> dict:
    """need-correct rate of the restated and withheld variants, pooled over the harness cells
    and task cells given. Only finished, non-excluded episodes count. Base-variant success
    is never reported."""
    out = {}
    for variant in VALIDITY_VARIANTS:
        vs = [e for e in eps if e.get("variant") == variant]
        if not vs:
            continue
        counted = [e for e in vs if e["exit_reason"] == "DONE" and not e.get("excluded")]
        k = sum(bool(e["need_correct"]) for e in counted)
        out[variant] = {"n_episodes": len(vs), "n_counted": len(counted), "n_need_correct": k,
                        "rate": round(k / len(counted), 4) if counted else None}
    return out


def pooled_report(runs: dict[str, list[dict]], *, experiment: str) -> dict:
    """Per model, pooled over every run (harness cell) given. Reasoning tokens are reported
    only when at least 2 harness cells are pooled, so a pool can never equal one arm."""
    by_model: dict[str, list[dict]] = {}
    for eps in runs.values():
        for e in eps:
            by_model.setdefault(str(e.get("model")), []).append(e)
    models = {}
    for model, eps in sorted(by_model.items()):
        cells = sorted({e["harness_cell"] for e in eps})
        tokens = {k: sum(int((e.get("usage") or {}).get(k, 0)) for e in eps)
                  for k in TOKEN_FIELDS}
        note = None
        if len(cells) < 2:
            tokens["reasoning_tokens"] = None
            note = (f"{WITHHELD_NOTE}: only one harness cell ({cells[0]}) in the pool, so a "
                    "pooled total would be that arm's")
        models[model] = {
            "harness_cells_pooled": cells,
            "n_episodes": len(eps),
            "n_episodes_by_variant": dict(sorted(Counter(e.get("variant") for e in eps)
                                                 .items())),
            "tokens_pooled": tokens,
            "tokens_note": note,
            "validity_levels": _validity_levels(eps),
            "errors": _errors(eps),
            "latency": _latency(x for e in eps for x in e.get("call_latency_s") or []),
            "cost_usd": _cost(eps),
            "echo_match": _echo_match(eps),
        }
    return {"experiment": experiment, "run_ids": sorted(runs), "models": models,
            "rule": ("PREREG §11 pilot blinding: validity levels, pooled tokens, errors, "
                     "latency and cost only; no per-arm success or per-arm reasoning tokens")}
