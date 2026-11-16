"""What R13's runs should cost, and the stops and block limit that follow (PREREG §17.13; $0).

R13 plays two harness cells that have never run on Haiku, Σ-n-0 (experiment 4) and W-nk-0
(experiment 5), and W-n-0 beside W-nk-0. Every source is a committed record or committed code:

1. **W-n-0, measured.** The mean tokens per episode (`FIELDS`) of R12 experiment 1's W-n-0 runs
   (`persistgym_haiku_r12_notes`), which played the episodes R13's W-n-0 arm plays: the 2
   not-recoverable far task cells, main templates 200-299. Each record's `usage` holds input
   (cache reads and writes included), cache reads, cache writes and output (thinking
   included). Low and high are both its cost on Haiku's card, as R12's measured cells.
2. **W-nk-0, W-n-0 plus the pinned block, by replay.** The generator's episodes (the default
   config, templates 200-299, the same 2 task cells) are played as W-n-0 and as W-nk-0 through
   `harnesses.runner.run_episode`, `harnesses.session.HarnessSession` and
   `harnesses.fake.FakeModel` (`ReplayModel`), so every request, the pinned block in it
   included, is the one the real code sends. The block's cost is W-nk-0's replayed cache reads
   and writes minus W-n-0's, under the cache rule and the calibration (below), added to W-n-0's
   measured profile.
   * Low: every reply at the mean visible length of R12's W-n-0 replies in its task cell (output
     minus thinking tokens, per request), in both arms; W-n-0's measured output.
   * High: W-nk-0's replies at `PINNED_HIGH_REPLY_TOKENS` (150, 2.4 to 2.8 times those means),
     so four of them fill the block to its 600-token cap (`R13_PINNED_TOKENS`) from the fourth
     dropped turn on, and the window drops its first turn earlier. The difference is taken from
     W-n-0's replay at the mean, so it also holds what longer replies add to W-n-0's own turns.
     The output is W-n-0's measured output times `PINNED_HIGH_OUTPUT_FACTOR` (2), about what
     150-token replies would write, which also leaves room for a block that makes Haiku write
     more.
3. **Σ-n-0, by replay.** The generator's episodes (templates 0-199, all 8 task cells) played as
   Σ-n-0 the same way: one summary request (ARC's summary system prompt and request prompt)
   when the context would pass W, then the bridge before the kept turns.
   * Low: replies at the mean visible length of R8's W-0 replies in the task cell
     (`persistgym_haiku`, the same episodes). Summaries at luna's mean summary length in the
     task cell, from its committed Σ-n-0 run (`persistgym` 20261010T100804Z): each
     compaction's `bridge_tokens` less the bridge template's own tokens. Output per step call
     is R8's W-0's in the task cell. Output per summary call is the summary (scaled to billed
     tokens, below) plus R8's W-0 thinking per call.
   * High: replies at the mean visible length of R9's W-n-0 replies (`persistgym_haiku_notes`,
     the same episodes and task cells), since Σ-n-0 sends the notes instruction and Haiku's
     notes replies run 1.7 to 1.9 times its W-0 replies. Output per step call is R9's W-n-0's.
     Summaries are `SUMMARY_HIGH_FACTOR` (4) times luna's length, and output per summary call 4
     times the low case's. As for R12's W-b-0, that cost is then scaled by the most the same
     replay of R8's W-0 misses R8's measured W-0 cost in any task cell (`worst_miss`). The
     replay makes no lookups, and R8's W-0 made them in the recoverable far cells.

**The cache rule.** Every multi-turn request carries a top-level `cache_control` (automatic
prompt caching, 5-minute TTL, `harnesses.wire.CACHE_CONTROL`), which writes one cache entry, at
the request's last block. A request reads only entries that earlier requests wrote ("Cache
reads look backward for entries that prior requests wrote"), within 20 block positions, its own
last block counted first (so at most 19 blocks back), and the system prompt comes before the
messages. Haiku 5.5's smallest cacheable prompt is 512 tokens, below every prompt here
(https://platform.claude.com/docs/en/build-with-claude/prompt-caching, read 2026-11-15). So
each request reads the longest earlier prompt of its episode that is a prefix of its own
(same system prompt, then the same first messages, within `LOOKBACK_BLOCKS`) and writes the
rest (`CacheLedger`). A step after a step that dropped nothing reads the earlier prompt and
writes the reply and the new observation. On a sliding window after the first drop the
prompt changes right after the system prompt at every step, so the whole prompt, the pinned
block with it, is written at every request the block is in. A summary request has a
different system prompt, so it writes all of its prompt, and so does the first step after a
compaction, which starts with the new bridge.

**Calibration.** The replay counts tokens in the generator's tokenizer, so each task cell's
replayed reads and writes are scaled by billed input over replayed input of a cell measured on
the same episodes, as R12 did: R8's F-0 (replayed with its own replies' mean length) for
experiment 4, R12's W-n-0 for experiment 5. As R12 did with its block window, the same replay
of R8's W-0 is set beside W-0's measured tokens and cost, a check of the cache rule
(`profiles`, `Σ-n-0`, `by_task_cell`, `w0_check`). Measured visible reply lengths are in
billed tokens and are used as the generator's tokens (as R12), which errs long.

Prices: `harnesses.pricing`'s Haiku card at or below 100,000 tokens (every prompt here is far
below), global geo. Served in the "us" geo, every cost here would be 10% higher
(`pricing.HAIKU_GEO_MULTIPLIERS`), and `most_one_send` already prices that geo.

Each run's stop (--planned-usd) is its high forecast times `STOP_MARGIN`, so a run at the high
cost finishes, and one send can pass a stop by at most `most_one_send`. The block's limit is the
high forecast of every run times `BLOCK_MARGIN`, plus every pilot's stop (R12's rule). The paid
guard admits a run only if its stop fits in what is left of the block and of phase 1a's cap,
so a later run whose stop no longer fits refuses, and Claude stops and tells the researcher.

Not modelled: failed summary attempts (a retry reads the failed attempt's prompt from the
cache), refusals, and lookups (the high case's `worst_miss` covers R8's).

Run: ``uv run python -m analysis.r13_forecast``. It writes
``results/r13_forecast/<UTC>/forecast.json`` and ``meta.json``, and prints the forecast. With
``--no-write`` it only prints. ``--workers N`` replays in N processes (default: the CPUs).
The output does not depend on N.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

from analysis import persistgym_h1h3 as hh
from analysis import r12_forecast as r12
from common import costs, runmeta
from harnesses import pricing, registered
from harnesses.cells import R13_PINNED_TOKENS, get_cell
from harnesses.config import ARC_SUMMARY_BRIDGE_TEMPLATE, HarnessConfig
from harnesses.fake import FakeModel, padded_text
from harnesses.items import item_text
from harnesses.runner import run_episode
from persistgym import tokens
from persistgym.config import DEFAULT_CONFIG, PRESET_HASHES
from persistgym.episode import ALL_CELLS
from persistgym.render import generate

REPO_ROOT = Path(__file__).resolve().parent.parent
HAIKU = registered.HAIKU_MODEL
SIGMA = registered.R13_SIGMA_EXPERIMENT
PINNED = registered.R13_PINNED_EXPERIMENT
SPECS = registered.R13_SPECS
ALL8 = SPECS[SIGMA]["task_cells"]
TWO = SPECS[PINNED]["task_cells"]
SOURCES = {  # name -> (experiment, run ids) of the committed runs read
    "R8 F-0": (registered.HAIKU_EXPERIMENT, ("20261018T141157Z-F-0-claude-haiku-5-5",)),
    "R8 W-0": (registered.HAIKU_EXPERIMENT, ("20261018T144829Z-W-0-claude-haiku-5-5",
                                             "20261018T154817Z-W-0-claude-haiku-5-5",
                                             "20261018T154918Z-W-0-claude-haiku-5-5")),
    "R9 W-n-0": (registered.HAIKU_NOTES_EXPERIMENT,
                 ("20261024T060051Z-W-n-0-claude-haiku-5-5",)),
    "R12 W-n-0": (registered.R12_NOTES_EXPERIMENT,
                  ("20261112T150644Z-W-n-0-claude-haiku-5-5",
                   "20261112T171952Z-W-n-0-claude-haiku-5-5",
                   "20261112T180539Z-W-n-0-claude-haiku-5-5",
                   "20261112T185728Z-W-n-0-claude-haiku-5-5")),
    "luna Σ-n-0": ("persistgym", ("20261010T100804Z-sigma-n-0-gpt-6-luna",)),
}
STOP_MARGIN = 1.25
"""Each run's stop is its high forecast times this, so a run at the high cost finishes (R12)."""
BLOCK_MARGIN = 1.10
"""The block's limit is every run's high forecast times this, plus the pilots' stops (R12)."""
MAX_ATTEMPTS = r12.MAX_ATTEMPTS
MAX_PROMPT_TOKENS = 40_000
"""The prompt `most_one_send` prices, in billed tokens, as R12's window cells; the forecast
refuses if a replayed prompt, scaled to billed tokens, is larger."""
PILOT_EXTRA_USD = 0.5
"""What R12 added to each pilot's stop above its high forecast times `STOP_MARGIN`."""
SUMMARY_HIGH_FACTOR = 4.0
"""Σ-n-0's high case: summaries this many times luna's length, and output per summary call
this many times the low case's (module docstring, 3)."""
PINNED_HIGH_REPLY_TOKENS = 150
"""W-nk-0's high case: every reply this long, so four fill the block's cap exactly."""
PINNED_HIGH_OUTPUT_FACTOR = 2.0
"""W-nk-0's high case: W-n-0's measured output times this (module docstring, 2)."""
LOOKBACK_BLOCKS = 20
"""How many block positions a request's cache breakpoint checks, itself first (module
docstring, the cache rule)."""
MIN_CACHE_TOKENS = 512
"""Haiku 5.5's smallest cacheable prompt; the forecast refuses a replayed prompt below it."""
FIELDS = r12.FIELDS
CFG = HarnessConfig(model=HAIKU, reasoning_effort=registered.REGISTERED_EFFORT[HAIKU],
                    service_tier=registered.HAIKU_REQUEST["service_tier"])
"""R8's request settings, which R13 keeps (PREREG §17.13): the episode's own W, the defaults
of `HarnessConfig` (ARC's summary prompts, the 32,000-token caps)."""
BRIDGE_TOKENS = tokens.count(ARC_SUMMARY_BRIDGE_TEMPLATE.format(summary=""))
"""The bridge template's own tokens, which luna's `bridge_tokens` include."""
TOTALS = ("episodes", "requests", "step_requests", "summary_requests", "input", "read",
          "write", "pinned", "compactions")
"""The integer sums `replay` keeps per plan and task cell (plus `max_prompt`, `min_prompt`)."""


# --- the committed records ----------------------------------------------------------------------

@cache
def _records(root: Path, name: str) -> tuple[dict, ...]:
    experiment, runs = SOURCES[name]
    out: dict[str, dict] = {}
    for run in runs:
        path = root / "results" / experiment / run / "episodes.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("exit_reason") == "DONE" and r["episode_id"] not in out:
                out[r["episode_id"]] = r  # each episode once, by its first finished record
    return tuple(out.values())


def rows(root: Path, name: str, task_cells: tuple[str, ...], templates: tuple[int, int]
         ) -> list[dict]:
    """The finished base-variant records of source `name` on `task_cells` and main templates
    [first, last + 1), each episode once; every one from the default generator config."""
    first, stop = templates
    out = [r for r in _records(root, name) if r["task_cell"] in task_cells
           and r["variant"] == "base" and first <= hh.template_index(r["template_id"]) < stop]
    if not out:
        raise SystemExit(f"no records of {name} on {', '.join(task_cells)}")
    bad = {r["generator_config_hash"] for r in out} - {PRESET_HASHES["default"]}
    if bad:
        raise SystemExit(f"{name}: records from another generator config: {sorted(bad)}")
    return out


def profile(rs: list[dict]) -> dict:
    """Mean tokens per episode (`FIELDS`) of the records `rs`, their number, mean billed cost
    and mean requests: R12's `profile`."""
    out = {f: sum(int((r.get("usage") or {}).get(f) or 0) for r in rs) / len(rs) for f in FIELDS}
    out["episodes"] = len(rs)
    out["billed_usd_per_episode"] = sum(float(r["cost_usd_billed_est"]) for r in rs) / len(rs)
    out["requests"] = sum(int(r["n_requests"]) for r in rs) / len(rs)
    return out


def per_request(rs: list[dict]) -> dict:
    """Billed tokens per request of the records `rs`: visible output (output minus thinking),
    output (thinking included) and thinking."""
    n = sum(int(r["n_requests"]) for r in rs)
    out = sum(int(r["usage"]["output_tokens"]) for r in rs)
    thinking = sum(int(r["usage"]["reasoning_tokens"] or 0) for r in rs)
    return {"visible": (out - thinking) / n, "output": out / n, "thinking": thinking / n}


def luna_summary_tokens(root: Path, task_cell: str) -> float:
    """luna's mean summary length in `task_cell` (generator tokens): each compaction's
    `bridge_tokens` less the bridge template's own (`BRIDGE_TOKENS`)."""
    lengths = [c["bridge_tokens"] - BRIDGE_TOKENS
               for r in rows(root, "luna Σ-n-0", (task_cell,), (0, registered.HAIKU_T))
               for c in r["compactions"]]
    return sum(lengths) / len(lengths)


# --- the replay ----------------------------------------------------------------------------------

class CacheLedger:
    """A `run_episode` recorder that prices each request's prompt under the cache rule (module
    docstring): its size (the system prompt and every message's text, in the generator's
    tokenizer), the part read from the cache (the longest earlier prompt of the episode that
    is a prefix of this one, within `lookback` block positions, this one's last block first)
    and the part written (the rest). One ledger per episode: no entry outlives its episode."""

    def __init__(self, lookback: int = LOOKBACK_BLOCKS):
        self.lookback = lookback
        self.entries: list[tuple[str, list[dict], int]] = []  # (system, messages, size)
        self.totals = {k: 0 for k in TOTALS if k not in ("episodes", "compactions")}
        self.totals["max_prompt"] = 0
        self.totals["min_prompt"] = None
        self._memo: dict[str, int] = {}

    def count(self, text: str) -> int:
        n = self._memo.get(text)
        if n is None:
            n = self._memo[text] = tokens.count(text)
        return n

    def __call__(self, event: dict) -> None:
        self.add(event["kind"], event["payload"], event["info"])

    def add(self, kind: str, payload: dict, info: dict | None = None) -> dict:
        """Price one request (`kind` "step" or "summary"); returns its size, read and write."""
        system, messages = payload["system"], payload["messages"]
        size = self.count(system) + sum(self.count(item_text(m)) for m in messages)
        read = max((s for sys0, msgs0, s in self.entries
                    if len(msgs0) <= len(messages)
                    and len(messages) - len(msgs0) < self.lookback
                    and sys0 == system and messages[:len(msgs0)] == msgs0), default=0)
        self.entries.append((system, messages, size))
        t = self.totals
        t["requests"] += 1
        t[f"{kind}_requests"] += 1
        t["input"] += size
        t["read"] += read
        t["write"] += size - read
        t["pinned"] += int((info or {}).get("pinned_tokens") or 0)
        t["max_prompt"] = max(t["max_prompt"], size)
        t["min_prompt"] = size if t["min_prompt"] is None else min(t["min_prompt"], size)
        return {"size": size, "read": read, "write": size - read}


class ReplayModel(FakeModel):
    """`FakeModel` with every reply padded to `reply_tokens` and every summary to
    `summary_tokens` (generator tokens), and its usage left at 0: the forecast prices each
    payload itself (`CacheLedger`), so the fake does not count every prompt a second time.
    `FakeModel.send` still runs the request-side check on every payload."""

    def __init__(self, reply_tokens: int, summary_tokens: int = 1):
        super().__init__(
            lambda p, i: padded_text(f"Reply to turn {i}.\nACTION: ack(none)", reply_tokens),
            summary_fn=lambda p, j: padded_text(f"SUMMARY s{j}: what to carry.",
                                                summary_tokens),
            reasoning_tokens=0)

    def _messages_response(self, payload: dict, tag: str, n: int, text: str) -> dict:
        content = [{"type": "thinking", "thinking": "", "signature": f"fake-sig-{tag}"}]
        if text:
            content.append({"type": "text", "text": text})
        return {"id": f"msg_{tag}", "type": "message", "role": "assistant",
                "model": payload.get("model", "") + self.model_suffix, "content": content,
                "stop_reason": "end_turn", "stop_sequence": None, "stop_details": None,
                "usage": {"input_tokens": 0, "cache_creation_input_tokens": 0,
                          "cache_read_input_tokens": 0, "output_tokens": 0,
                          "service_tier": "standard", "inference_geo": "global"}}


def replay_episode(episode, cell: str, reply_tokens: int, summary_tokens: int = 1) -> dict:
    """One episode played as `cell` by the runner, the session and `ReplayModel`, priced by a
    `CacheLedger`: its `TOTALS`, `max_prompt` and `min_prompt`."""
    ledger = CacheLedger()
    run = run_episode(episode, get_cell(cell), CFG, ReplayModel(reply_tokens, summary_tokens),
                      recorder=ledger)
    if run.exit_reason != "DONE":
        raise RuntimeError(f"replay of {episode.episode_id} as {cell}: {run.exit_reason} "
                           f"{run.error}")
    return {**ledger.totals, "episodes": 1, "compactions": len(run.compactions)}


@dataclass
class Plan:
    """One replay: `cell` on main templates [first, last + 1) and `task_cells`, replies of
    `reply[task cell]` tokens and summaries of `summary[task cell]` tokens."""
    name: str
    cell: str
    templates: tuple[int, int]
    task_cells: tuple[str, ...]
    reply: dict[str, int]
    summary: dict[str, int] = field(default_factory=dict)


def _merge(into: dict, add: dict) -> None:
    for k in TOTALS:
        into[k] = into.get(k, 0) + add[k]
    into["max_prompt"] = max(into.get("max_prompt", 0), add["max_prompt"])
    lows = [x for x in (into.get("min_prompt"), add["min_prompt"]) if x is not None]
    into["min_prompt"] = min(lows) if lows else None


def _replay_templates(plans: list[Plan], indices: list[int]) -> dict:
    out: dict = {}
    for _, eps in generate("main", indices, DEFAULT_CONFIG, ALL_CELLS, ("base",)):
        for ep in eps:
            if ep.config_hash != PRESET_HASHES["default"]:
                raise RuntimeError(f"{ep.episode_id}: not the default generator config")
            t = hh.template_index(ep.template_id)
            for p in plans:
                if p.templates[0] <= t < p.templates[1] and ep.cell.id in p.task_cells:
                    r = replay_episode(ep, p.cell, p.reply[ep.cell.id],
                                       p.summary.get(ep.cell.id, 1))
                    _merge(out.setdefault(p.name, {}).setdefault(ep.cell.id, {}), r)
    return out


def replay(plans: list[Plan], workers: int = 1) -> dict:
    """plan name -> task cell -> integer sums over the plan's episodes (`TOTALS`, and the
    largest and smallest prompt). The generator's episodes of every template a plan needs are
    made once and played by every plan that needs them, in `workers` processes; the sums do
    not depend on `workers`."""
    indices = sorted({t for p in plans for t in range(*p.templates)})
    if workers <= 1:
        return _replay_templates(plans, indices)
    chunks = [indices[i::workers * 4] for i in range(workers * 4)]
    out: dict = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for part in pool.map(_replay_templates, [plans] * len(chunks), chunks):
            for name, cells in part.items():
                for c, sums in cells.items():
                    _merge(out.setdefault(name, {}).setdefault(c, {}), sums)
    return out


def per_episode(sums: dict) -> dict:
    """The replay's means per episode of one plan and task cell."""
    n = sums["episodes"]
    return {k: sums[k] / n for k in TOTALS if k != "episodes"}


def billed(read: float, write: float, output: float, thinking: float) -> dict:
    """A billed token profile (`FIELDS`) from cache reads, cache writes, output and the
    thinking part of the output; no input is uncached under the cache rule."""
    return {"input_tokens": read + write, "cached_input_tokens": read,
            "cache_write_tokens": write, "output_tokens": output, "reasoning_tokens": thinking}


def price(p: dict) -> float:
    """List cost per episode of a profile on Haiku's card, global geo (`r12_forecast.price`)."""
    return r12.price(p, HAIKU)


# --- the cost models ------------------------------------------------------------------------

def plans(root: Path) -> tuple[list[Plan], dict]:
    """R13's replays (module docstring, 2 and 3) and the measured lengths they use."""
    lo4, hi4 = SPECS[SIGMA]["templates"], SPECS[PINNED]["templates"]
    f0 = {c: per_request(rows(root, "R8 F-0", (c,), lo4)) for c in ALL8}
    w0 = {c: per_request(rows(root, "R8 W-0", (c,), lo4)) for c in ALL8}
    r9 = {c: per_request(rows(root, "R9 W-n-0", (c,), lo4)) for c in ALL8}
    wn = {c: per_request(rows(root, "R12 W-n-0", (c,), hi4)) for c in TWO}
    summary = {c: luna_summary_tokens(root, c) for c in ALL8}
    lengths = {"R8 F-0": f0, "R8 W-0": w0, "R9 W-n-0": r9, "R12 W-n-0": wn,
               "luna summary": summary}

    def r(d):
        return {c: round(v["visible"]) for c, v in d.items()}

    sm = {c: round(v) for c, v in summary.items()}
    out = [
        Plan("F-0", "F-0", lo4, ALL8, r(f0)),
        Plan("W-0", "W-0", lo4, ALL8, r(w0)),
        Plan("Σ-n-0 low", "Σ-n-0", lo4, ALL8, r(w0), sm),
        Plan("Σ-n-0 high", "Σ-n-0", lo4, ALL8, r(r9),
             {c: round(v * SUMMARY_HIGH_FACTOR) for c, v in summary.items()}),
        Plan("W-n-0", "W-n-0", hi4, TWO, r(wn)),
        Plan("W-nk-0 low", "W-nk-0", hi4, TWO, r(wn)),
        Plan("W-nk-0 high", "W-nk-0", hi4, TWO, {c: PINNED_HIGH_REPLY_TOKENS for c in TWO}),
    ]
    return out, lengths


def sigma(root: Path, sims: dict, lengths: dict) -> dict:
    """Σ-n-0's forecast per episode, and per task cell with the W-0 check (module docstring,
    3)."""
    lo4 = SPECS[SIGMA]["templates"]
    by_cell = {}
    for c in ALL8:
        f0 = profile(rows(root, "R8 F-0", (c,), lo4))
        w0rows = rows(root, "R8 W-0", (c,), lo4)
        w0 = profile(w0rows)
        scale = f0["input_tokens"] / per_episode(sims["F-0"][c])["input"]
        rw = per_episode(sims["W-0"][c])
        w0_replayed = billed(rw["read"] * scale, rw["write"] * scale, w0["output_tokens"],
                             w0["reasoning_tokens"])
        cases = {}
        for case, steps, summ in (("low", lengths["R8 W-0"][c], 1.0),
                                  ("high", lengths["R9 W-n-0"][c], SUMMARY_HIGH_FACTOR)):
            s = per_episode(sims[f"Σ-n-0 {case}"][c])
            summary_thinking = summ * lengths["R8 W-0"][c]["thinking"]
            one_summary = summ * lengths["luna summary"][c] * scale + summary_thinking
            prof = billed(s["read"] * scale, s["write"] * scale,
                          s["step_requests"] * steps["output"]
                          + s["summary_requests"] * one_summary,
                          s["step_requests"] * steps["thinking"]
                          + s["summary_requests"] * summary_thinking)
            cases[case] = {"profile": prof, "usd": price(prof),
                           "step_requests": s["step_requests"],
                           "summary_requests": s["summary_requests"],
                           "compactions": s["compactions"],
                           "reply_tokens": round(steps["visible"]),
                           "summary_tokens": round(lengths["luna summary"][c] * summ),
                           "summary_call_output_tokens": one_summary,
                           "max_prompt_billed": sims[f"Σ-n-0 {case}"][c]["max_prompt"] * scale,
                           "min_prompt": sims[f"Σ-n-0 {case}"][c]["min_prompt"]}
        by_cell[c] = {"scale": scale, **cases,
                      "w0_check": {"input_measured": w0["input_tokens"],
                                   "input_replayed": w0_replayed["input_tokens"],
                                   "cached_measured": w0["cached_input_tokens"],
                                   "cached_replayed": w0_replayed["cached_input_tokens"],
                                   "usd_measured": w0["billed_usd_per_episode"],
                                   "usd_replayed": price(w0_replayed)}}
    worst_miss = max(1.0, max(v["w0_check"]["usd_measured"] / v["w0_check"]["usd_replayed"]
                              for v in by_cell.values()))
    low = sum(v["low"]["usd"] for v in by_cell.values()) / len(by_cell)
    high = sum(v["high"]["usd"] for v in by_cell.values()) / len(by_cell) * worst_miss
    return {"low_usd": low, "high_usd": high, "worst_miss": worst_miss,
            "low": _mean(by_cell, "low"), "high": _mean(by_cell, "high"),
            "by_task_cell": by_cell}


def pinned(root: Path, sims: dict, lengths: dict) -> dict:
    """W-n-0's measured cost and W-nk-0's forecast per episode, and per task cell (module
    docstring, 1 and 2)."""
    hi4 = SPECS[PINNED]["templates"]
    by_cell = {}
    for c in TWO:
        wn = profile(rows(root, "R12 W-n-0", (c,), hi4))
        base = per_episode(sims["W-n-0"][c])
        scale = wn["input_tokens"] / base["input"]
        cases = {}
        for case, out_factor in (("low", 1.0), ("high", PINNED_HIGH_OUTPUT_FACTOR)):
            k = per_episode(sims[f"W-nk-0 {case}"][c])
            d_read = (k["read"] - base["read"]) * scale
            d_write = (k["write"] - base["write"]) * scale
            prof = {"input_tokens": wn["input_tokens"] + d_read + d_write,
                    "cached_input_tokens": wn["cached_input_tokens"] + d_read,
                    "cache_write_tokens": wn["cache_write_tokens"] + d_write,
                    "output_tokens": wn["output_tokens"] * out_factor,
                    "reasoning_tokens": wn["reasoning_tokens"] * out_factor}
            cases[case] = {"profile": prof, "usd": price(prof),
                           "added_read": d_read, "added_write": d_write,
                           "pinned_tokens_per_episode": k["pinned"],
                           "reply_tokens": (round(lengths["R12 W-n-0"][c]["visible"])
                                            if case == "low" else PINNED_HIGH_REPLY_TOKENS),
                           "max_prompt_billed": sims[f"W-nk-0 {case}"][c]["max_prompt"] * scale,
                           "min_prompt": sims[f"W-nk-0 {case}"][c]["min_prompt"]}
        by_cell[c] = {"scale": scale, "w_n_0_usd": price(wn), **cases,
                      "w_n_0_check": {"cached_measured": wn["cached_input_tokens"],
                                      "cached_replayed": base["read"] * scale,
                                      "write_measured": wn["cache_write_tokens"],
                                      "write_replayed": base["write"] * scale}}
    mean = {k: sum(v[k] if k == "w_n_0_usd" else v[k]["usd"] for v in by_cell.values())
            / len(by_cell) for k in ("w_n_0_usd", "low", "high")}
    return {"w_n_0_usd": mean["w_n_0_usd"], "low_usd": mean["low"], "high_usd": mean["high"],
            "low": _mean(by_cell, "low"), "high": _mean(by_cell, "high"),
            "by_task_cell": by_cell}


def _mean(by_cell: dict, case: str) -> dict:
    """The mean token profile (`FIELDS`) per episode of a case over the task cells."""
    return {f: sum(v[case]["profile"][f] for v in by_cell.values()) / len(by_cell)
            for f in FIELDS}


# --- runs, pilots, stops and the block --------------------------------------------------------

def run_order() -> list[tuple[str, str, tuple[int, int]]]:
    """R13's runs in order, (experiment, cell, templates): experiment 4's runs of
    `R13_SIGMA_RUN_TEMPLATES` templates, then experiment 5's rounds of `R13_ROUND_TEMPLATES`,
    each round's two arms in `r13_round_arms` order."""
    out = []
    first, stop = SPECS[SIGMA]["templates"]
    step = registered.R13_SIGMA_RUN_TEMPLATES
    for start in range(first, stop, step):
        out += [(SIGMA, cell, (start, start + step)) for cell in SPECS[SIGMA]["cells"]]
    first, stop = SPECS[PINNED]["templates"]
    step = registered.R13_ROUND_TEMPLATES
    for k, start in enumerate(range(first, stop, step)):
        out += [(PINNED, cell, (start, start + step)) for cell in registered.r13_round_arms(k)]
    return out


def pilot_episodes(cell: str) -> int:
    """A pilot's episodes, as harnesses/r13_rounds.py plays them: pilot templates within
    `R13_PILOT_TEMPLATES`, at most `R13_PILOT_MAX_EPISODES`, every task cell of the pilot."""
    task_cells = registered.R13_PILOTS[(HAIKU, cell)]
    first, stop = registered.R13_PILOT_TEMPLATES
    return min(stop - first, registered.R13_PILOT_MAX_EPISODES // len(task_cells)) * len(task_cells)


def stop_usd(episodes: int, high: float) -> float:
    """A run's stop: its high forecast times `STOP_MARGIN`, up to the next cent (R12)."""
    return math.ceil(episodes * high * STOP_MARGIN * 100) / 100


def schedule(per: dict[tuple[str, str], tuple[float, float]], spent: float,
             one_send: float) -> dict:
    """`runs`, `pilots`, `totals` and the phase 1a numbers from the per-episode forecasts `per`
    ((model, cell) -> (low, high)), R12's rules."""
    rows_, totals = [], {"low": 0.0, "high": 0.0, "stops": 0.0, "one_send": 0.0}
    for experiment, cell, (a, b) in run_order():
        n = (b - a) * len(SPECS[experiment]["task_cells"])
        lo, hi = per[(HAIKU, cell)]
        stop = stop_usd(n, hi)
        rows_.append({"experiment": experiment, "model": HAIKU, "cell": cell,
                      "templates": [a, b], "episodes": n, "low_usd": n * lo, "high_usd": n * hi,
                      "planned_usd": stop, "most_one_send_usd": one_send})
        totals["low"] += n * lo
        totals["high"] += n * hi
        totals["stops"] += stop
        totals["one_send"] = max(totals["one_send"], one_send)
    pilots = []
    for (model, cell) in registered.R13_PILOTS:
        n = pilot_episodes(cell)
        pilots.append({"model": model, "cell": cell, "episodes": n,
                       "planned_usd": stop_usd(n, per[(model, cell)][1]) + PILOT_EXTRA_USD})
    pilot_total = sum(p["planned_usd"] for p in pilots)
    block = math.ceil(totals["high"] * BLOCK_MARGIN + pilot_total)
    return {"runs": rows_, "pilots": pilots,
            "totals": {**totals, "pilots": pilot_total, "block_max_usd": block},
            "phase_1a_spent_usd": spent, "phase_1a_after_block_usd": spent + block}


def phase_1a_spent(root: Path) -> float:
    """Phase 1a's spend in results/costs.csv, as R12's forecast reads it: each row's billed
    estimate, or its list cost when that is empty, over the rows of phase 1a's experiments."""
    with (root / "results" / "costs.csv").open(encoding="utf-8", newline="") as f:
        ledger = list(csv.DictReader(f))
    return sum(float(r["cost_usd_billed_est"] or r["cost_usd_list"] or 0)
               for r in ledger if costs.EXPERIMENT_PHASE.get(r["experiment"], "?") == "1a")


def check_prompts(*models: dict) -> None:
    """Refuse a forecast whose replayed prompts leave the ground its prices stand on: one
    larger than `MAX_PROMPT_TOKENS` billed tokens (`most_one_send`'s prompt; Haiku's > 100,000
    card is far above it), or one below `MIN_CACHE_TOKENS` (it would not be cached)."""
    for m in models:
        for c, v in m["by_task_cell"].items():
            for case in ("low", "high"):
                if v[case]["max_prompt_billed"] > MAX_PROMPT_TOKENS:
                    raise SystemExit(f"{c} ({case}): a replayed prompt of "
                                     f"{v[case]['max_prompt_billed']:.0f} billed tokens passes "
                                     f"{MAX_PROMPT_TOKENS}")
                if v[case]["min_prompt"] < MIN_CACHE_TOKENS:
                    raise SystemExit(f"{c} ({case}): a replayed prompt of "
                                     f"{v[case]['min_prompt']} tokens is below "
                                     f"{MIN_CACHE_TOKENS}, the smallest Haiku caches")


def forecast(root: Path, workers: int = 1) -> dict:
    ps, lengths = plans(root)
    sims = replay(ps, workers)
    sg = sigma(root, sims, lengths)
    pn = pinned(root, sims, lengths)
    check_prompts(sg, pn)
    per = {(HAIKU, "Σ-n-0"): (sg["low_usd"], sg["high_usd"]),
           (HAIKU, "W-nk-0"): (pn["low_usd"], pn["high_usd"]),
           (HAIKU, "W-n-0"): (pn["w_n_0_usd"],) * 2}
    wn = profile(rows(root, "R12 W-n-0", TWO, SPECS[PINNED]["templates"]))
    plan = schedule(per, phase_1a_spent(root), r12.most_one_send(HAIKU, MAX_PROMPT_TOKENS))
    return {"prereg": registered.R13_REF,
            "profiles": {"W-n-0": wn, "W-nk-0": {k: pn[k] for k in ("low", "high",
                                                                     "by_task_cell")},
                         "Σ-n-0": {k: sg[k] for k in ("low", "high", "worst_miss",
                                                      "by_task_cell")}},
            "per_episode_usd": {f"{m} {c}": list(v) for (m, c), v in per.items()},
            **plan}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    a = ap.parse_args(argv)
    now = datetime.now(UTC)
    r = forecast(REPO_ROOT, a.workers)
    print(json.dumps({k: r[k] for k in ("per_episode_usd", "totals", "phase_1a_spent_usd",
                                        "phase_1a_after_block_usd")}, indent=2))
    if a.no_write:
        return 0
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    out = REPO_ROOT / "results" / "r13_forecast" / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "forecast.json").write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8",
                                       newline="\n")
    runmeta.write_meta(
        out, git=runmeta.git_state(), experiment="r13_forecast", run_id=run_id,
        cell_or_config="R13",
        config={"sources": {k: list(v[1]) for k, v in SOURCES.items()},
                "stop_margin": STOP_MARGIN, "block_margin": BLOCK_MARGIN,
                "max_attempts": MAX_ATTEMPTS, "max_prompt_tokens": MAX_PROMPT_TOKENS,
                "pilot_extra_usd": PILOT_EXTRA_USD, "summary_high_factor": SUMMARY_HIGH_FACTOR,
                "pinned_high_reply_tokens": PINNED_HIGH_REPLY_TOKENS,
                "pinned_high_output_factor": PINNED_HIGH_OUTPUT_FACTOR,
                "pinned_cap_tokens": R13_PINNED_TOKENS, "lookback_blocks": LOOKBACK_BLOCKS,
                "generator_config_hash": PRESET_HASHES["default"],
                "harness": CFG.to_dict(), "price_source_date": pricing.HAIKU_PRICE_SOURCE_DATE},
        model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
        repeat_index=0, seeds={}, started_utc=now.isoformat(timespec="seconds"),
        finished_utc=runmeta.utc_now(), exit_reason="completed", tokens=None, cost_usd=0.0,
        raw_transcript_path=None, outputs=["forecast.json", "meta.json"], paid_calls=0)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
