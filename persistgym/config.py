"""Generator configuration for PersistGym-lite.

Every field whose value is a pre-registration choice for the researcher is listed in
`RESEARCHER_DECISIONS` (and in DESIGN.md, tagged [RESEARCHER DECISION]). Defaults come from
PLAN.md §4-§6 and amendment §16 where the plan gives a number, and are marked "proposed" where
it does not.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass

GENERATOR_VERSION = "0.1.0"
SCHEMA_VERSION = 1

# Disjoint seed ranges (half-open). Pilot templates never share seeds with main templates
# (PLAN §16.5 "Pilot templates use a disjoint seed range").
SEED_RANGES: dict[str, tuple[int, int]] = {
    "main": (0, 1_000_000),
    "pilot": (9_000_000, 9_100_000),
}

RULE_PLACEMENTS = ("with_last_clue", "with_first_clue", "separate_step", "system_prompt")
RESTATE_MODES = ("as_revealed", "final_value")
SINGLE_TURN_REPLY_MODES = ("oracle", "none")


@dataclass(frozen=True)
class GeneratorConfig:
    # --- volume and distance (PLAN §5, §16.5) ---
    W_tokens: int = 24_000
    """Eviction threshold W of the window/summary harness cells, in tokens (o200k_base)."""
    v_tokens: int = 1_500
    """Fixed token budget of every observation (user message), including the event text."""
    tokenizer: str = "o200k_base"
    token_tolerance: int = 0
    """Allowed |observation tokens - v|. The fitter aims for exactly v."""
    near_gap_steps: int = 4
    """Near cells: the latest reveal component is this many steps before the need step."""
    far_margin_tokens: int = 0
    """Far cells: observation tokens from the latest reveal step through the need step
    (inclusive) must be > W + far_margin_tokens. Observation tokens only (§16.5)."""
    assumed_max_reply_tokens: int = 1_000
    """Reply length assumed when computing designed survival for window cells, and the
    reply length under which every near cell must have S=1."""
    window_counts_system_prompt: bool = False
    """Whether the window budget W also has to hold the system prompt."""
    max_context_tokens: int = 64_000
    """Full-history context at the need step (system + observations + replies of
    assumed_max_reply_tokens) must stay at or below this (PLAN §5 'contexts stay <= 64k').
    Checked by the audit, not enforced by the generator."""

    # --- episode shape (PLAN §5) ---
    K_options: int = 10
    k_targets: int = 1
    need_index_range: tuple[int, int] = (20, 24)
    """Inclusive range of the 0-based need-step index, sampled per template (same for all
    cells of a template). 20 is the minimum for far derived cells at the defaults; 24 keeps
    full-history contexts <= max_context_tokens with 1k-token replies."""
    tail_steps_range: tuple[int, int] = (0, 2)
    """Inclusive range of routine steps after the need step, sampled per template."""
    lead_in_min_steps: int = 2
    """Minimum routine steps before the earliest reveal component in any cell."""

    # --- derived facts (PLAN §4 definitions) ---
    n_clues_choices: tuple[int, ...] = (2, 3)
    clue_spacing_steps: int = 1
    rule_placement: str = "with_last_clue"
    value_range: tuple[int, int] = (300, 899)
    """Inclusive range of the target value and of every option value (all 3-digit)."""
    minor_component_range: tuple[int, int] = (61, 98)
    """Inclusive range of the 2-digit additive clue values (offset, shift). Kept above 59 so
    they can never collide with clock fields in the log filler."""

    # --- controls ---
    restate_mode: str = "as_revealed"
    """Restated-at-need control: repeat the records as originally shown (derived facts still
    need combining) or show the final value."""
    single_turn_reply_mode: str = "oracle"
    """Position-matched single-turn control: replies interleaved in the flattened prompt.
    'oracle' = the minimal correct reply per step; 'none' = observations only."""

    # --- agent-facing task text ---
    warn_future_need: bool = True
    """System prompt says that later requests can depend on earlier records."""

    # --- lookup (recoverable cells) ---
    lookup_max_per_episode: int = 3
    lookup_scope: str = "revealed_so_far"
    """A lookup re-shows only the records already displayed before the pending step."""

    # --- action parsing and scoring ---
    accept_value_answers: bool = True
    """At the need step, accept the option value as well as its letter."""
    strict_action_parse: bool = False
    """True: only a line 'ACTION: verb(arg)' counts. False: if no ACTION line, fall back to
    the last 'verb(arg)' with a known verb anywhere in the reply."""

    # --- survival accounting for summary/notes cells ---
    carried_match_window_chars: int = 200
    """A value counts as carried in a summary/note only if it appears within this many
    characters of the entity name (0 = anywhere in the text)."""
    carried_requires_rule: bool = False
    """Derived facts: whether carrying all clue values also requires the rule to be carried."""

    # --- validity (PLAN §5, §16.3) ---
    validity_margin_pp: float = 10.0
    """No-memory baselines must score <= chance + this many percentage points."""

    skins: tuple[str, ...] = ("warehouse", "biobank", "datacenter", "archive", "depot")
    step_seconds: int = 75
    """Simulated wall-clock seconds between consecutive observations (log timestamps)."""

    # ------------------------------------------------------------------
    def __post_init__(self) -> None:
        if self.k_targets != 1:
            raise ValueError("only k=1 (one target per episode) is implemented")
        if self.rule_placement not in RULE_PLACEMENTS:
            raise ValueError(f"rule_placement must be one of {RULE_PLACEMENTS}")
        if self.restate_mode not in RESTATE_MODES:
            raise ValueError(f"restate_mode must be one of {RESTATE_MODES}")
        if self.single_turn_reply_mode not in SINGLE_TURN_REPLY_MODES:
            raise ValueError(f"single_turn_reply_mode must be one of {SINGLE_TURN_REPLY_MODES}")
        if self.lookup_scope != "revealed_so_far":
            raise ValueError("only lookup_scope='revealed_so_far' is implemented")
        if not 2 <= self.K_options <= 26:
            raise ValueError("K_options must be between 2 and 26")
        lo, hi = self.value_range
        if not (100 <= lo and hi <= 999 and hi - lo + 1 >= self.K_options):
            raise ValueError("value_range must be 3-digit and hold at least K values")
        mlo, mhi = self.minor_component_range
        if not (60 <= mlo <= mhi <= 99):
            raise ValueError("minor_component_range must be 2-digit and above 59")
        if min(self.n_clues_choices) < 2 or max(self.n_clues_choices) > 3:
            raise ValueError("n_clues_choices must be within 2..3")
        if self.near_gap_steps >= self.far_gap_steps:
            raise ValueError("near_gap_steps must be smaller than the far gap")
        need_lo, need_hi = self.need_index_range
        if need_lo < self.min_need_index or need_hi < need_lo:
            raise ValueError(
                f"need_index_range {self.need_index_range} too small: far derived cells need "
                f"need index >= {self.min_need_index} with these W, v and clue settings")

    # ------------------------------------------------------------------
    @property
    def far_gap_steps(self) -> int:
        """Smallest gap g (need index - latest reveal index) with (g+1)*v > W + margin.

        Assumes every observation has exactly v tokens; the generator re-checks the real
        token counts after rendering."""
        return math.floor((self.W_tokens + self.far_margin_tokens) / self.v_tokens)

    @property
    def max_reveal_span(self) -> int:
        """Steps between the earliest and latest reveal component, worst case."""
        n_steps = max(self.n_clues_choices)
        if self.rule_placement == "separate_step":
            n_steps += 1
        return (n_steps - 1) * self.clue_spacing_steps

    @property
    def min_need_index(self) -> int:
        return self.far_gap_steps + self.max_reveal_span + self.lead_in_min_steps

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        for k, v in d.items():
            if isinstance(v, tuple):
                d[k] = list(v)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> GeneratorConfig:
        names = {f.name: f for f in dataclasses.fields(cls)}
        kw = {}
        for k, v in d.items():
            if k not in names:
                raise ValueError(f"unknown config field {k!r}")
            kw[k] = tuple(v) if isinstance(v, list) else v
        return cls(**kw)

    def replace(self, **changes) -> GeneratorConfig:
        return dataclasses.replace(self, **changes)


# Fields whose values the researcher must confirm in PREREG.md. Each entry: (PLAN reference,
# why it matters). DESIGN.md lists every one of them; a test checks that it does.
RESEARCHER_DECISIONS: dict[str, tuple[str, str]] = {
    "W_tokens": ("§5, §16.5", "eviction threshold; tuning rule in M1, contexts <= 64k"),
    "v_tokens": ("§5, §16.5", "per-observation volume; fixes distance in tokens per step"),
    "near_gap_steps": ("§5", "'near = reveal about 4 steps before need'"),
    "far_margin_tokens": ("§4, §16.5", "how far beyond W counts as 'far' (obs tokens only)"),
    "assumed_max_reply_tokens": ("§5, §16.5", "reply length behind designed S for near cells"),
    "window_counts_system_prompt": ("§6", "whether W also holds the system prompt"),
    "max_context_tokens": ("§5", "'contexts stay <= 64k' (full history, assumed replies)"),
    "K_options": ("§5", "number of options at need; chance = 1/K"),
    "need_index_range": ("§5", "episode length ~20-32 steps"),
    "tail_steps_range": ("§5", "routine steps after need (cost without information)"),
    "n_clues_choices": ("§4", "derived = computed from 2-3 observations"),
    "clue_spacing_steps": ("§4", "'shown at different steps'; spacing sets the reveal span"),
    "rule_placement": ("§5", "where the combining rule is shown"),
    "restate_mode": ("§5", "what restated-at-need repeats for derived facts"),
    "single_turn_reply_mode": ("§5, H3", "what fills reply positions in the flattened control"),
    "warn_future_need": ("§5", "whether agents are told that earlier records matter later"),
    "lookup_max_per_episode": ("§4", "how many lookups a recoverable episode allows"),
    "accept_value_answers": ("§4", "need-step scoring: letter only, or letter or value"),
    "strict_action_parse": ("§4", "what counts as the reply's action"),
    "carried_match_window_chars": ("§4, §10", "string-match rule behind P(carried)"),
    "carried_requires_rule": ("§4, §10", "derived carried = all clues, with or without rule"),
    "validity_margin_pp": ("§5, §16.3", "no-memory baselines <= chance + 10pp"),
}

DEFAULT_CONFIG = GeneratorConfig()
