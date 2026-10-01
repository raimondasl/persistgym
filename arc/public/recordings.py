"""Parse arcprize.org recording NDJSON and summarise time, cost and tokens per action.

Real schema (checked on the 16 pulled recordings, 2026-09-30). One JSON object per line:

    {"timestamp": "2026-09-09T14:43:18.369722+00:00",
     "data": {"game_id", "guid", "state", "levels_completed", "win_levels", "full_reset",
              "available_actions", "frame",
              "action_input": {"id": "ACTION1" | ... | "RESET", "data": {...},
                               "reasoning": null | "<JSON string>"}}}

- Line 0 is the opening RESET (``reasoning`` null). It is not counted in the session's
  ``actions``; every later line is one counted action, RESETs included.
- ``data`` is the frame AFTER the action, so line i's action was taken on level
  ``lines[i-1].levels_completed``. Counting this way reproduces the session's
  ``level_actions`` exactly (checked in ops.py for every recording).
- ``reasoning`` is null for forced RESETs (no model call) and otherwise the harness's
  ``ActionMetadata`` (pinned harness ``runtime_models.py`` L549-576): ``output``, ``reasoning``
  (summary text, Adapter only), ``usage`` {``input_tokens``, ``input_tokens_details.
  cached_tokens``, ``output_tokens`` (visible + thinking for Gemini: ``runtime_models.py``
  L161-198 for google-genai and L201-228 for Interactions fold thoughts into
  ``output_tokens``; the API surface of the published Standard runs is unknown, so
  ``Summary.n_output_lt_reasoning`` checks the identity on the data: 0 on all 16 recordings),
  ``output_tokens_details.reasoning_tokens``, ``total_tokens``}, ``cost``
  {``input_cost``, ``output_cost``, ``total_cost``} = tokens x configured list price, no cache
  discount; Adapter runs add ``state`` {``input_items_sent``, ``history_items_before_prune``,
  ``history_items_after_prune``} and, on a step that followed a harness-summary compaction,
  ``state.harness_compaction`` {``usage``, ``cost``}.
- On compaction steps the top-level ``usage`` and ``cost`` already include the compaction
  call (``agent.py`` L857-862 adds the pending compaction usage before pricing), so summing
  ``cost.total_cost`` over steps counts everything once.
- ``usage`` sums every attempt of a step (``agent.py`` L1018-1030 accumulates usage across
  retries), which explains occasional steps with about double the input tokens.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import pairwise
from pathlib import Path

# Gemini 3.8 Flash list prices through 2026-12-31 (docs/background.md §6,
# https://ai.google.dev/gemini-api/docs/pricing): input $0.75/M, cached input $0.075/M.
PRICE_INPUT_PER_M = 0.75
PRICE_CACHED_PER_M = 0.075

PLATEAU_RULE = ("warm-up ends at the first model step whose action-call input tokens reach "
                "90% of the run's 95th percentile of action-call input tokens; plateau "
                "statistics use the model steps after it")
FRAME_TOKENS_EST = 13_000      # one 64x64 frame is about 12.8k tokens (docs/background.md §4)
MAX_ANIMATION_FRAMES = 7       # frames per observation sent to the model (pinned harness)
MULTI_ATTEMPT_RULE = (
    "action-call input > 1.5 x (previous step's action-call input + its output tokens + "
    "min(frames observed, 7) x 13k), previous action-call input >= 30k, neither step a "
    "compaction step; i.e. more input than one turn of growth can explain, as when usage sums "
    "two or more attempts (agent.py L1018-1030)")
METHOD_NOTE = (
    "Per-step values come from each recording line's action metadata. Token and cost means "
    "are per model call (forced RESETs make no call, cost nothing and are excluded; compare "
    "`n_steps` with `n_model_steps`), so 'per action' in the headline means per model call. "
    "Cost = summed "
    "`cost.total_cost` (ARC's no-cache list accounting: input and output tokens x $0.75 / "
    "$3.75 per M; includes harness-summary compaction calls). `cost_cached_price_usd` re-prices "
    "cached input at $0.075/M (an estimate of billed cost with implicit caching, not ARC's "
    "number). Visible output = output_tokens - reasoning_tokens. Seconds per step = gaps "
    "between consecutive recording timestamps (server time). Action-call input excludes the "
    "compaction call's input on compaction steps. Plateau: " + PLATEAU_RULE + ". Compaction "
    "events = steps carrying `state.harness_compaction` (Adapter only; the Standard harness "
    "has no compaction, and its drop-oldest truncation leaves no trace in the recording). "
    "Multi-attempt steps (heuristic): " + MULTI_ATTEMPT_RULE + ". `n_output_lt_reasoning` "
    "counts steps where output_tokens < reasoning_tokens; it must be 0 for visible output = "
    "output - reasoning to be valid.")


@dataclass
class Step:
    index: int                 # line number in the NDJSON (0 = opening RESET)
    timestamp: datetime
    action: str
    level_before: int | None   # levels_completed of the previous frame (None for line 0)
    levels_completed: int
    state: str
    model_call: bool           # False for RESETs without metadata
    n_frames: int = 1          # frames in this line's observation (animations give several)
    frames_seen: int = 1       # frames the model saw before choosing this action
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost: float = 0.0
    compaction: bool = False
    compaction_input_tokens: int = 0
    compaction_cost: float = 0.0

    @property
    def action_input_tokens(self) -> int:
        return self.input_tokens - self.compaction_input_tokens


def parse_line(index: int, rec: dict, prev_levels: int | None) -> Step:
    data = rec["data"]
    ai = data.get("action_input") or {}
    raw = ai.get("reasoning")
    step = Step(index=index, timestamp=datetime.fromisoformat(rec["timestamp"]),
                action=str(ai.get("id")), level_before=prev_levels,
                levels_completed=int(data["levels_completed"]), state=str(data["state"]),
                model_call=False, n_frames=len(data.get("frame") or []) or 1)
    if raw is None:
        return step
    meta = json.loads(raw) if isinstance(raw, str) else raw
    usage = meta.get("usage") or {}
    step.model_call = True
    step.input_tokens = int(usage.get("input_tokens") or 0)
    step.cached_tokens = int((usage.get("input_tokens_details") or {}).get("cached_tokens") or 0)
    step.output_tokens = int(usage.get("output_tokens") or 0)
    step.reasoning_tokens = int(
        (usage.get("output_tokens_details") or {}).get("reasoning_tokens") or 0)
    step.cost = float((meta.get("cost") or {}).get("total_cost") or 0.0)
    hc = (meta.get("state") or {}).get("harness_compaction")
    if hc:
        step.compaction = True
        step.compaction_input_tokens = int((hc.get("usage") or {}).get("input_tokens") or 0)
        step.compaction_cost = float((hc.get("cost") or {}).get("total_cost") or 0.0)
    return step


def parse_lines(lines: list[dict]) -> list[Step]:
    steps: list[Step] = []
    for i, rec in enumerate(lines):
        s = parse_line(i, rec, steps[-1].levels_completed if steps else None)
        if steps:
            s.frames_seen = steps[-1].n_frames
        steps.append(s)
    return steps


def load_steps(path: Path) -> list[Step]:
    with path.open(encoding="utf-8") as f:
        return parse_lines([json.loads(line) for line in f if line.strip()])


def level_action_counts(steps: list[Step], level_count: int) -> list[int]:
    """Actions per level, counted like the session's ``level_actions`` (opening RESET excluded)."""
    counts = [0] * level_count
    for s in steps[1:]:
        if s.level_before is not None and s.level_before < level_count:
            counts[s.level_before] += 1
    return counts


def _p95(values: list[int]) -> float:
    xs = sorted(values)
    return xs[min(len(xs) - 1, round(0.95 * (len(xs) - 1)))]


def warmup_end(model_steps: list[Step]) -> int:
    """Position (in model_steps) of the first step at or above 90% of the p95 action input."""
    if not model_steps:
        return 0
    thr = 0.9 * _p95([s.action_input_tokens for s in model_steps])
    for k, s in enumerate(model_steps):
        if s.action_input_tokens >= thr:
            return k
    return 0


def multi_attempt_steps(model_steps: list[Step]) -> list[int]:
    """Line indices of steps whose input is too large for one attempt (MULTI_ATTEMPT_RULE).

    One turn of growth is at most the previous input, plus the previous reply (the Adapter
    also replays its thinking, so all output tokens are allowed), plus the new observation.
    """
    out = []
    for prev, cur in pairwise(model_steps):
        if cur.compaction or prev.compaction or prev.action_input_tokens < 30_000:
            continue
        growth = prev.output_tokens + min(cur.frames_seen, MAX_ANIMATION_FRAMES) * FRAME_TOKENS_EST
        if cur.action_input_tokens > 1.5 * (prev.action_input_tokens + growth):
            out.append(cur.index)
    return out


@dataclass
class Summary:
    n_steps: int                  # counted actions (lines - 1)
    n_model_steps: int
    n_forced_resets: int          # counted RESETs without metadata
    duration_s: float             # first to last recording timestamp
    s_per_step_mean: float
    s_per_step_median: float
    cost_total_usd: float
    cost_cached_price_usd: float
    cost_per_step_mean: float
    input_total: int
    cached_total: int
    output_total: int
    reasoning_total: int
    input_per_step_mean: float
    cached_per_step_mean: float
    output_per_step_mean: float
    reasoning_per_step_mean: float
    visible_out_per_step_mean: float
    cached_share: float
    warmup_steps: int
    plateau_cost_per_step_mean: float
    plateau_cost_per_step_median: float
    input_plateau_median: float   # action-call input tokens after warm-up
    input_max: int
    n_compactions: int
    compaction_cost_usd: float
    steps_per_compaction: float | None
    n_multi_attempt_steps: int
    last_step_multi_attempt: bool
    n_output_lt_reasoning: int    # steps with output_tokens < reasoning_tokens (must be 0 for
                                  # visible = output - reasoning to hold)

    def as_dict(self) -> dict:
        return asdict(self)


def summarize(steps: list[Step]) -> Summary:
    if len(steps) < 2:
        raise ValueError("recording has no counted actions")
    counted = steps[1:]
    model = [s for s in steps if s.model_call]
    if not model:
        raise ValueError("recording has no model steps")
    gaps = [(b.timestamp - a.timestamp).total_seconds() for a, b in pairwise(steps)]
    n = len(counted)
    nm = len(model)
    inp = sum(s.input_tokens for s in model)
    cached = sum(s.cached_tokens for s in model)
    out = sum(s.output_tokens for s in model)
    rsn = sum(s.reasoning_tokens for s in model)
    cost = sum(s.cost for s in model)
    cost_cached = cost - cached * (PRICE_INPUT_PER_M - PRICE_CACHED_PER_M) / 1e6
    w = warmup_end(model)
    plateau = model[w:] or model
    pcost = [s.cost for s in plateau]
    n_comp = sum(s.compaction for s in model)
    multi = multi_attempt_steps(model)
    return Summary(
        n_steps=n, n_model_steps=len(model),
        n_forced_resets=sum(1 for s in counted if not s.model_call),
        duration_s=(steps[-1].timestamp - steps[0].timestamp).total_seconds(),
        s_per_step_mean=statistics.fmean(gaps), s_per_step_median=statistics.median(gaps),
        cost_total_usd=cost, cost_cached_price_usd=cost_cached, cost_per_step_mean=cost / nm,
        input_total=inp, cached_total=cached, output_total=out, reasoning_total=rsn,
        input_per_step_mean=inp / nm, cached_per_step_mean=cached / nm,
        output_per_step_mean=out / nm, reasoning_per_step_mean=rsn / nm,
        visible_out_per_step_mean=(out - rsn) / nm,
        cached_share=cached / inp if inp else 0.0,
        warmup_steps=w,
        plateau_cost_per_step_mean=statistics.fmean(pcost),
        plateau_cost_per_step_median=statistics.median(pcost),
        input_plateau_median=statistics.median(s.action_input_tokens for s in plateau),
        input_max=max(s.input_tokens for s in model),
        n_compactions=n_comp,
        compaction_cost_usd=sum(s.compaction_cost for s in model),
        steps_per_compaction=(n / n_comp) if n_comp else None,
        n_multi_attempt_steps=len(multi),
        last_step_multi_attempt=bool(multi) and multi[-1] == model[-1].index,
        n_output_lt_reasoning=sum(1 for s in model if s.output_tokens < s.reasoning_tokens),
    )
