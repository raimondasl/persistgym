"""Harness configuration: request settings shared by every cell, and the summary policy.

Every field whose value is a pre-registration choice is listed in `RESEARCHER_DECISIONS`
(and in harnesses/DESIGN.md, tagged [RESEARCHER DECISION]).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

# ARC's harness-summary prompts, verbatim (ARC harness at 4ca00e6,
# benchmarking/compaction.py, MIT licence:
# https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/benchmarking/compaction.py).
# They are already domain-neutral, so the generic PersistGym summary uses them unchanged.
ARC_SUMMARY_SYSTEM_PROMPT = (
    "You create concise conversation summaries for reliable continuation. "
    "Return only the requested summary."
)
ARC_SUMMARY_REQUEST_PROMPT = (
    "Summarize the conversation so you can continue making progress on the task in a future "
    "context. The conversation history will be replaced by this summary and will no longer be "
    "available.\nUse your judgment about what matters for this task."
)
ARC_SUMMARY_BRIDGE_TEMPLATE = (
    "Earlier conversation history was compacted. Use the following summary as prior context. "
    "If it conflicts with newer input, prefer the newer input.\n\n{summary}"
)

REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
REASONING_MODES = ("standard", "pro")
SERVICE_TIERS = ("auto", "default", "flex", "scale", "priority", "fast", "ultrafast", "standard")
"""OpenAI's tiers, and "standard", the only tier a run on Anthropic's Messages API records (it
sends none; `harnesses.wire.MESSAGES_SERVICE_TIER`). Each wire refuses the other's."""
ENCRYPTED_REASONING = "reasoning.encrypted_content"
DEFAULT_MAX_OUTPUT_TOKENS = 32_000
"""PREREG D13 (decided 2026-10-01; §6: luna and sol requests carry `max_output_tokens: 32000`):
the cap of every request, sent explicitly: every step and summary request of every harness
cell, and every probe request. It includes reasoning tokens."""


def require_output_cap(name: str, value) -> None:
    """An output cap must be a positive int (bool is not), so it is always sent explicitly."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive int, got {value!r}")


@dataclass(frozen=True)
class HarnessConfig:
    # --- model and request settings (PLAN §7, amendment §16.5) ---
    model: str = "gpt-6-luna"
    reasoning_effort: str = "medium"
    """Always sent explicitly (`reasoning.effort`), on every step and summary request. 'medium'
    is the documented default for luna and sol. The registered effort is per model
    (`harnesses.registered.REGISTERED_EFFORT`; PREREG §6 as amended by R2, §17.2): luna
    medium, sol high. The CLI's `run` and `dry-run` default to it, and `run` refuses any other
    effort outside pilots. The runner checks the echoed effort on every response
    (`stop_on_effort_mismatch`)."""
    reasoning_mode: str = "standard"
    """Always sent explicitly (`reasoning.mode`)."""
    reasoning_summary: str | None = None
    """`reasoning.summary`; None = not requested (the field is omitted)."""
    service_tier: str = "flex"
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    """`max_output_tokens` of every step request, always sent (PREREG D13: 32,000). On OpenAI
    the cap includes reasoning tokens. A step response that stops at it (status `incomplete`)
    is logged and scored as an invalid action (PREREG §6, §13). Summary requests send
    `summary_max_output_tokens`, also 32,000 under D13."""
    prompt_cache_key: str | None = None
    """None = omitted (automatic prefix caching only)."""

    # --- loss policy (PLAN §6) ---
    W_tokens: int | None = None
    """Window / summary threshold in tokens. None = the episode's generator W, so the harness
    evicts exactly where the generator designed near and far."""
    window_counts_system_prompt: bool | None = None
    """Whether W also has to hold the episode's system prompt (never the notes sentence, so
    notes pairs evict at the same steps; PREREG D5). None = the episode's generator setting
    (true since generator 0.2.0)."""
    tokenizer: str = "o200k_base"
    """Tokenizer for window and summary accounting (same as the generator)."""

    # --- notes instruction ---
    notes_separator: str = "\n"
    """Joins the episode's system prompt and the notes sentence (the prompt is one line per
    instruction, so the sentence becomes its last line)."""

    # --- summary cells (PLAN §6: generic summary modelled on ARC's SUMMARY_REQUEST_PROMPT) ---
    summary_system_prompt: str | None = ARC_SUMMARY_SYSTEM_PROMPT
    """Instructions of the summary call. ARC replaces the task instructions with its summary
    system prompt; None keeps the task instructions (with the notes sentence if the cell has
    it) instead."""
    summary_request_prompt: str = ARC_SUMMARY_REQUEST_PROMPT
    summary_bridge_template: str = ARC_SUMMARY_BRIDGE_TEMPLATE
    summary_max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    """`max_output_tokens` of the summary call, always sent (PREREG D13: 32,000, as every
    luna and sol request; PREREG §5 freezes it with the payload snapshot tests). It includes
    reasoning. ARC's own summary cap, 8,192, belongs to the ARC leg's Gemini configs only. An
    incomplete summary is retried (`summary_max_attempts`), never scored."""
    summary_keep_recent_tokens: int = 0
    """0 = compact the whole history at the trigger, as ARC does. > 0 = keep the most recent
    whole turns that fit in this many tokens (with the current observation) verbatim and
    summarize only the older ones."""
    summary_max_attempts: int = 4
    """Attempts per compaction when the summary comes back empty or incomplete (ARC:
    MAX_RETRIES + 1 = 4)."""

    # --- echo checks (CLAUDE.md: check the echoed reasoning.context on every response) ---
    stop_on_context_mismatch: bool = True
    """Stop an episode at the first response whose echoed reasoning.context differs from the
    request. The episode is excluded either way."""
    stop_on_effort_mismatch: bool = True
    """The same for the echoed reasoning.effort (PREREG §17.2, amendment R2: an effort
    mismatch excludes the episode as a context mismatch does)."""
    abort_after_mismatched_episodes: int = 2
    """Abort the whole run after this many excluded (echo-mismatched) episodes, whichever echo
    differed."""

    max_turns: int = 200
    """Safety stop for one episode (lookups add at most lookup_max_per_episode turns)."""

    def __post_init__(self) -> None:
        if self.reasoning_effort not in REASONING_EFFORTS:
            raise ValueError(f"reasoning_effort must be one of {REASONING_EFFORTS}")
        if self.reasoning_mode not in REASONING_MODES:
            raise ValueError(f"reasoning_mode must be one of {REASONING_MODES}")
        if self.service_tier not in SERVICE_TIERS:
            raise ValueError(f"service_tier must be one of {SERVICE_TIERS}")
        require_output_cap("max_output_tokens", self.max_output_tokens)
        require_output_cap("summary_max_output_tokens", self.summary_max_output_tokens)
        if self.summary_keep_recent_tokens < 0:
            raise ValueError("summary_keep_recent_tokens must be >= 0")
        if self.W_tokens is not None and self.summary_keep_recent_tokens >= self.W_tokens:
            raise ValueError("summary_keep_recent_tokens must be smaller than W_tokens")
        if "{summary}" not in self.summary_bridge_template:
            raise ValueError("summary_bridge_template must contain '{summary}'")
        if self.summary_max_attempts < 1:
            raise ValueError("summary_max_attempts must be >= 1")

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> HarnessConfig:
        names = {f.name for f in dataclasses.fields(cls)}
        unknown = set(d) - names
        if unknown:
            raise ValueError(f"unknown harness config fields {sorted(unknown)}")
        return cls(**d)

    def replace(self, **changes) -> HarnessConfig:
        return dataclasses.replace(self, **changes)


# Fields (or fixed behaviours) the researcher must confirm in PREREG.md. Each entry:
# (PLAN reference, what it decides). DESIGN.md lists every one; a test checks that it does.
RESEARCHER_DECISIONS: dict[str, tuple[str, str]] = {
    "reasoning_effort": ("§16.5, PREREG D13, R2", ("registered per model, sent explicitly: "
                                                    "luna medium; sol high after an ENGAGED "
                                                    "engagement check (PREREG §17.2)")),
    "reasoning_mode": ("§16.5", "standard, sent explicitly"),
    "reasoning_summary": ("§7", "whether harness cells request reasoning summaries (off)"),
    "service_tier": ("§12, §16.1", "flex for every cell; never switched per episode"),
    "max_output_tokens": ("§12, PREREG D13", ("32,000 on every step request, sent explicitly; "
                                               "an incomplete step response is invalid")),
    "W_tokens": ("§5, §6", "taken from the episode so eviction matches the design"),
    "window_counts_system_prompt": ("§6, D5", ("taken from the episode config (true); the "
                                               "notes sentence is never counted")),
    "token_accounting": ("§5, §6", ("visible text only: observations, replies, bridge; "
                                     "reasoning items are not counted")),
    "summary_trigger": ("§6", "pre-send: visible context > W (ARC: provider total >= 175k)"),
    "summary_keep_recent_tokens": ("§6, DESIGN §8", "0 = compact everything, as ARC"),
    "summary_system_prompt": ("§6", "ARC's summary system prompt replaces the task prompt"),
    "summary_request_reasoning": ("§6, §7", ("summary call keeps the arm's reasoning.context "
                                             "and the compacted turns' reasoning items")),
    "summary_max_output_tokens": ("§6, PREREG D13", ("32,000 on every summary request, as "
                                                      "every OpenAI request (not ARC's "
                                                      "8,192)")),
    "notes_placement": ("§6", "last line of the instructions"),
    "stop_on_context_mismatch": ("§7, CLAUDE.md", "stop and exclude the episode"),
    "stop_on_effort_mismatch": ("PREREG §17.2 (R2)", ("stop and exclude the episode, as for "
                                                      "reasoning.context")),
    "output_items_replay": ("§7", "output items sent back verbatim, null fields dropped"),
    # The Messages wire (claude-*; PREREG §17.8, amendment R8, not yet merged; DESIGN §13)
    "messages_replay_off": ("PREREG §17.8 (R8, pending)", (
        "earlier turns go back as visible text only, never a thinking block; replay-on and "
        "summary cells refused")),
    "messages_empty_reply": ("PREREG §17.8 (R8, pending)", (
        "a turn with no visible text goes back as '(no reply)'; it counts 0 toward W")),
    "messages_refusal_partial": ("PREREG §17.8 (R8, pending)", (
        "a refusal's partial text is discarded from the history: '(no reply)', 0 toward W")),
    "messages_inference_geo": ("PREREG §17.8 (R8, pending)", (
        "no inference_geo sent; each call priced at the geo served (us 1.1x; none reported: "
        "1.1x)")),
    "messages_prompt_caching": ("PREREG §17.8 (R8, pending)", (
        "top-level cache_control (5 minutes) in multi-turn cells, none in the single-turn "
        "control")),
    "messages_service_tier": ("PREREG §17.8 (R8, pending)", (
        "no service_tier sent; standard recorded as requested, usage.service_tier as served")),
    "messages_stop_reasons": ("PREREG §17.8 (R8, pending)", (
        "max_tokens, refusal and any unexpected stop reason are incomplete: an invalid "
        "action (D13)")),
}
