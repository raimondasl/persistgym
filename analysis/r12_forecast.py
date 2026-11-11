"""What R12's runs should cost, and the stops and block limit that follow (PREREG §17.12; $0).

Three sources, all committed records or code:

1. **Haiku's measured token profiles.** For each harness cell R12 runs on Haiku or on Sonnet,
   the mean tokens per episode on the cell's task cells, from the committed episode records of
   the runs that played that cell: R8's F-0 and W-0 (`persistgym_haiku`), R9's W-n-0, R10's
   W-np-0, and R11's W-n-0. Each record's `usage` holds input (cache reads and writes
   included), cache reads, cache writes and output (thinking included). W-nd-0 and W-nx-0 have
   never run: they are bracketed by W-n-0's short notes (low) and W-np-0's long ones (high).
2. **Re-pricing.** A profile priced at `harnesses.pricing`'s card for a model: Haiku's own, and
   claude-sonnet-5-5's (checked 2026-11-11). Sonnet's high case doubles the output, since a
   larger model may write more. Sonnet's tokenizer is assumed to count as Haiku's.
3. **The block window (W-b-0), by replay.** It has never run, so its prompt sizes come from the
   generator's episodes (the default config, templates 0-199, all 8 task cells) under
   `persistgym.survival.block_keep_starts`, with every reply at the mean visible length of R8's
   W-0 replies in that task cell. Each request writes to the cache what is new since the last
   request's prompt (all of it after a drop) and reads the rest. The same replay under the
   sliding window, set beside R8's W-0, and with no window, beside R8's F-0, calibrates it: the
   replay counts in the generator's tokenizer, so each cell's total is scaled by R8's billed
   input over the replayed input for F-0. The output is R8's W-0's.

Each run's stop (--planned-usd) is its high forecast times `STOP_MARGIN`, so a run at the high
cost finishes, and one send can pass a stop by at most `most_one_send`. The block's limit is the
high forecast of every run times `BLOCK_MARGIN`, plus every pilot's stop. The paid guard admits a
run only if its stop fits in what is left of the block and of phase 1a's cap, so a later run
whose stop no longer fits refuses, and Claude stops and tells the researcher.

Run: ``uv run python -m analysis.r12_forecast``. It writes
``results/r12_forecast/<UTC>/forecast.json`` and ``meta.json``, and prints the forecast. With
``--no-write`` it only prints.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from analysis import persistgym_h1h3 as hh
from common import runmeta
from harnesses import pricing, registered
from harnesses.config import DEFAULT_MAX_OUTPUT_TOKENS
from persistgym.config import DEFAULT_CONFIG
from persistgym.episode import ALL_CELLS
from persistgym.render import generate
from persistgym.survival import block_keep_starts, window_keep_start

REPO_ROOT = Path(__file__).resolve().parent.parent
TWO = registered.HAIKU_CONTROL_TASK_CELLS
ALL8 = registered.HAIKU_TASK_CELLS
SOURCES = {  # harness cell -> (experiment, run ids) of Haiku's committed runs that played it
    "F-0": ("persistgym_haiku", ("20261018T141157Z-F-0-claude-haiku-5-5",)),
    "W-0": ("persistgym_haiku", ("20261018T144829Z-W-0-claude-haiku-5-5",
                                 "20261018T154817Z-W-0-claude-haiku-5-5",
                                 "20261018T154918Z-W-0-claude-haiku-5-5")),
    "W-n-0": (registered.HAIKU_CONTROL_EXPERIMENT,
              ("20261106T050520Z-W-n-0-claude-haiku-5-5",)),
    "W-np-0": (registered.HAIKU_PROVENANCE_EXPERIMENT,
               ("20261101T184553Z-W-np-0-claude-haiku-5-5",
                "20261101T190445Z-W-np-0-claude-haiku-5-5")),
}
STOP_MARGIN = 1.25
"""Each run's stop is its high forecast times this, so a run at the high cost finishes."""
BLOCK_MARGIN = 1.10
"""The block's limit is every run's high forecast times this, plus the pilots' stops."""
MAX_ATTEMPTS = 6
FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens",
          "reasoning_tokens")


def _records(root: Path, cell: str) -> list[dict]:
    experiment, runs = SOURCES[cell]
    out: dict[str, dict] = {}
    for run in runs:
        path = root / "results" / experiment / run / "episodes.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("exit_reason") == "DONE" and r["episode_id"] not in out:
                out[r["episode_id"]] = r  # each episode once, by its first finished record
    return list(out.values())


def profile(root: Path, cell: str, task_cells: tuple[str, ...]) -> dict:
    """Mean tokens per episode (`FIELDS`) of Haiku's runs of `cell` on `task_cells`, main
    templates 0-199 (module docstring, 1)."""
    rows = [r for r in _records(root, cell) if r["task_cell"] in task_cells
            and r["variant"] == "base" and hh.template_index(r["template_id"]) < 200]
    if not rows:
        raise SystemExit(f"no records of {cell} on {', '.join(task_cells)}")
    out = {f: sum(int((r.get("usage") or {}).get(f) or 0) for r in rows) / len(rows)
           for f in FIELDS}
    out["episodes"] = len(rows)
    out["billed_usd_per_episode"] = sum(float(r["cost_usd_billed_est"]) for r in rows) / len(rows)
    out["requests"] = sum(int(r["n_requests"]) for r in rows) / len(rows)
    return out


def price(p: dict, model: str, output_factor: float = 1.0) -> float:
    """List cost per episode of a profile on `model`'s card, global geo (one card; for Haiku
    the <= 100,000 card, which every request of these cells uses)."""
    c = pricing.price_for(model)
    plain = p["input_tokens"] - p["cached_input_tokens"] - p["cache_write_tokens"]
    return (plain * c.input + p["cached_input_tokens"] * c.cached
            + p["cache_write_tokens"] * c.input * pricing.CACHE_WRITE_MULTIPLIER
            + p["output_tokens"] * output_factor * c.output) / 1e6


def _replay(obs: list[int], reply: float, W: int, sys_t: int, need: int, policy: str
            ) -> tuple[float, float]:
    """(input, cache-write) tokens of one episode's step requests 0..need under `policy`
    ("none", "slide" or "block"), replies of `reply` tokens each (module docstring, 3)."""
    obs = obs[: need + 1]
    rep = [reply] * need
    if policy == "block":
        starts = block_keep_starts(obs, rep, W, sys_t)
    elif policy == "slide":
        starts = [window_keep_start(obs[: m + 1], rep[:m], W, sys_t) for m in range(len(obs))]
    else:
        starts = [0] * len(obs)
    total = write = 0.0
    prev_start, prev_size = None, 0.0
    for m, s in enumerate(starts):
        size = sys_t + obs[m] + sum(obs[s:m]) + sum(rep[s:m])
        total += size
        write += size if s != prev_start else size - prev_size
        prev_start, prev_size = s, size
    return total, write


def block_window(root: Path) -> dict:
    """W-b-0's forecast per episode on the 8 task cells, by replay calibrated on R8's F-0 and
    W-0 (module docstring, 3)."""
    w0 = _records(root, "W-0")
    f0 = _records(root, "F-0")
    by_cell: dict[str, dict] = {}
    for c in ALL8:
        rw = [r for r in w0 if r["task_cell"] == c and r["variant"] == "base"]
        rf = [r for r in f0 if r["task_cell"] == c and r["variant"] == "base"]
        visible = sum(int(r["usage"]["output_tokens"]) - int(r["usage"]["reasoning_tokens"] or 0)
                      for r in rw) / sum(int(r["n_requests"]) for r in rw)
        by_cell[c] = {"reply": visible, "w0": rw, "f0": rf, "sim": {"none": [0.0, 0.0],
                                                                   "slide": [0.0, 0.0],
                                                                   "block": [0.0, 0.0]}}
    cfg = DEFAULT_CONFIG
    for _, eps in generate("main", range(200), cfg, ALL_CELLS, ("base",)):
        for ep in eps:
            d = by_cell[ep.cell.id]
            sys_t = ep.system_tokens if cfg.window_counts_system_prompt else 0
            for policy in ("none", "slide", "block"):
                t, w = _replay(ep.obs_tokens, d["reply"], cfg.W_tokens, sys_t, ep.need_step,
                               policy)
                d["sim"][policy][0] += t / 200
                d["sim"][policy][1] += w / 200
    out = {}
    for c, d in by_cell.items():
        mean = {f: sum(int(r["usage"].get(f) or 0) for r in rows) / len(rows)
                for rows, f in ((d["f0"], "input_tokens"), (d["w0"], "input_tokens"))}
        scale = (sum(int(r["usage"]["input_tokens"]) for r in d["f0"]) / len(d["f0"])
                 / d["sim"]["none"][0])
        out_tokens = sum(int(r["usage"]["output_tokens"]) for r in d["w0"]) / len(d["w0"])
        prof = {}
        for policy in ("slide", "block"):
            inp, wr = (x * scale for x in d["sim"][policy])
            prof[policy] = {"input_tokens": inp, "cached_input_tokens": inp - wr,
                            "cache_write_tokens": wr, "output_tokens": out_tokens}
        measured_w0 = sum(float(r["cost_usd_billed_est"]) for r in d["w0"]) / len(d["w0"])
        out[c] = {"reply_tokens": d["reply"], "scale": scale,
                  "w0_input_measured": mean["input_tokens"],
                  "w0_input_replayed": prof["slide"]["input_tokens"],
                  "w0_usd_measured": measured_w0,
                  "w0_usd_replayed": price(prof["slide"], registered.HAIKU_MODEL),
                  "block_usd": price(prof["block"], registered.HAIKU_MODEL),
                  "block_profile": prof["block"]}
    return out


def most_one_send(model: str, max_prompt_tokens: int) -> float:
    """The most one send can add after its run's stop has passed (`MAX_ATTEMPTS` attempts, all
    of the prompt a cache write, the output cap, the dearest geo)."""
    c = pricing.price_for(model)
    worst = max(dict(c.geo_multipliers).values())
    one = (max_prompt_tokens * c.input * pricing.CACHE_WRITE_MULTIPLIER
           + DEFAULT_MAX_OUTPUT_TOKENS * c.output) / 1e6
    return one * MAX_ATTEMPTS * worst


def forecast(root: Path) -> dict:
    haiku, sonnet = registered.HAIKU_MODEL, registered.SONNET_MODEL
    prof = {c: profile(root, c, TWO) for c in ("F-0", "W-n-0", "W-np-0")}
    per = {  # (model, cell) -> (low, high) USD per episode on the 2 task cells
        (haiku, "W-n-0"): (price(prof["W-n-0"], haiku),) * 2,
        (haiku, "W-np-0"): (price(prof["W-np-0"], haiku),) * 2,
        (haiku, "W-nd-0"): (price(prof["W-n-0"], haiku), price(prof["W-np-0"], haiku)),
        (haiku, "W-nx-0"): (price(prof["W-n-0"], haiku), price(prof["W-np-0"], haiku)),
        (sonnet, "W-n-0"): (price(prof["W-n-0"], sonnet), price(prof["W-n-0"], sonnet, 2.0)),
        (sonnet, "W-np-0"): (price(prof["W-np-0"], sonnet), price(prof["W-np-0"], sonnet, 2.0)),
        (sonnet, "F-0"): (price(prof["F-0"], sonnet), price(prof["F-0"], sonnet, 2.0)),
    }
    bw = block_window(root)
    bw_low = sum(v["block_usd"] for v in bw.values()) / len(bw)
    # the high case scales the replay by the most it misses R8's W-0 cost in any task cell
    worst_miss = max(v["w0_usd_measured"] / v["w0_usd_replayed"] for v in bw.values())
    per[(haiku, "W-b-0")] = (bw_low, bw_low * max(worst_miss, 1.0))

    runs = []  # one entry per planned run: (experiment, model, cell, templates)
    spec = registered.R12_SPECS
    notes = spec[registered.R12_NOTES_EXPERIMENT]
    first, stop = notes["templates"]
    for k, start in enumerate(range(first, stop, 25)):
        cells = notes["cells"][k % 4:] + notes["cells"][: k % 4]  # rotate the order
        for cell in cells:
            runs.append((registered.R12_NOTES_EXPERIMENT, haiku, cell, (start, start + 25)))
    son = spec[registered.R12_SONNET_EXPERIMENT]
    for cell in son["cells"]:
        runs.append((registered.R12_SONNET_EXPERIMENT, sonnet, cell, son["templates"]))
    blk = spec[registered.R12_BLOCK_EXPERIMENT]
    for start in range(blk["templates"][0], blk["templates"][1], 50):
        runs.append((registered.R12_BLOCK_EXPERIMENT, haiku, "W-b-0", (start, start + 50)))
    rows, totals = [], {"low": 0.0, "high": 0.0, "stops": 0.0, "one_send": 0.0}
    for experiment, model, cell, (a, b) in runs:
        n = (b - a) * len(spec[experiment]["task_cells"])
        lo, hi = per[(model, cell)]
        stop_usd = math.ceil(n * hi * STOP_MARGIN * 100) / 100
        extra = most_one_send(model, 40_000 if cell != "F-0" else 80_000)
        rows.append({"experiment": experiment, "model": model, "cell": cell,
                     "templates": [a, b], "episodes": n, "low_usd": n * lo, "high_usd": n * hi,
                     "planned_usd": stop_usd, "most_one_send_usd": extra})
        totals["low"] += n * lo
        totals["high"] += n * hi
        totals["stops"] += stop_usd
        totals["one_send"] = max(totals["one_send"], extra)
    pilots = []
    first, stop = registered.R12_PILOT_TEMPLATES
    for (model, cell), task_cells in registered.R12_PILOTS.items():
        # as harnesses/r12_rounds.py plays them: pilot templates 0-1, at most 8 episodes
        n = min(stop - first, registered.R12_PILOT_MAX_EPISODES // len(task_cells)) * len(task_cells)
        hi = per[(model, cell)][1]
        pilots.append({"model": model, "cell": cell, "episodes": n,
                       "planned_usd": math.ceil(n * hi * STOP_MARGIN * 100) / 100 + 0.5})
    pilot_total = sum(p["planned_usd"] for p in pilots)
    block = math.ceil(totals["high"] * BLOCK_MARGIN + pilot_total)
    spent = sum(float(r["cost_usd_billed_est"] or r["cost_usd_list"] or 0)
                for r in _ledger(root) if _phase(r["experiment"]) == "1a")
    return {"prereg": registered.R12_REF, "profiles": prof,
            "per_episode_usd": {f"{m} {c}": list(v) for (m, c), v in per.items()},
            "block_window": {c: {k: v for k, v in d.items() if k != "block_profile"}
                             for c, d in bw.items()},
            "runs": rows, "pilots": pilots,
            "totals": {**totals, "pilots": pilot_total, "block_max_usd": block},
            "phase_1a_spent_usd": spent,
            "phase_1a_after_block_usd": spent + block}


def _ledger(root: Path) -> list[dict]:
    import csv
    with (root / "results" / "costs.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _phase(experiment: str) -> str:
    from common import costs
    return costs.EXPERIMENT_PHASE.get(experiment, "?")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    now = datetime.now(UTC)
    r = forecast(REPO_ROOT)
    print(json.dumps({k: r[k] for k in ("per_episode_usd", "totals", "phase_1a_spent_usd",
                                        "phase_1a_after_block_usd")}, indent=2))
    if a.no_write:
        return 0
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    out = REPO_ROOT / "results" / "r12_forecast" / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "forecast.json").write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8",
                                       newline="\n")
    runmeta.write_meta(
        out, git=runmeta.git_state(), experiment="r12_forecast", run_id=run_id,
        cell_or_config="R12",
        config={"sources": {k: list(v[1]) for k, v in SOURCES.items()},
                "stop_margin": STOP_MARGIN, "block_margin": BLOCK_MARGIN,
                "max_attempts": MAX_ATTEMPTS},
        model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
        repeat_index=0, seeds={}, started_utc=now.isoformat(timespec="seconds"),
        finished_utc=runmeta.utc_now(), exit_reason="completed", tokens=None, cost_usd=0.0,
        raw_transcript_path=None, outputs=["forecast.json", "meta.json"], paid_calls=0)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
