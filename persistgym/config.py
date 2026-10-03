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

GENERATOR_VERSION = "0.4.0"
SCHEMA_VERSION = 3

# Disjoint seed ranges (half-open), PREREG D7. Template index i of a split has seed
# range start + i, so the balance blocks (K consecutive indices) start at each range start.
# Main sweep templates are taken in order from index 0, validity runs and the G1 spot-check
# use their own range, and pilot templates never share seeds with either (PLAN §16.5).
SEED_RANGES: dict[str, tuple[int, int]] = {
    "main": (0, 50_000),
    "validity": (50_000, 60_000),
    "pilot": (90_000, 100_000),
}

RULE_PLACEMENTS = ("with_last_clue", "with_first_clue", "separate_step", "system_prompt")
RESTATE_MODES = ("as_revealed", "final_value")
SINGLE_TURN_REPLY_MODES = ("oracle", "none")
CLUE_FORMS = ("direct", "chain")
ADDED_IN_0_4 = {"clue_form": "direct", "evidence_notice": False}
"""Fields added by generator 0.4.0 (PREREG §17.3, amendment R3) and their defaults. `to_dict`
leaves a field out while it has its default, so the default config's dict and hash
(`common.runmeta.config_hash`) are those of generator 0.3.0."""
CHAIN_V1_GAP = 109
"""Chain form: the smallest near delta (H1 - clue) and far delta (H1 - anchor); see
`template.CHAIN_DELTA_RANGE`. Repeated here for the config's own checks."""


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
    window_counts_system_prompt: bool = True
    """Whether the window budget W also has to hold the episode's system prompt (PREREG D5:
    sys counts toward W, as in the harness cells and the PREREG formulas). The harness counts
    the episode's system prompt only, not its notes sentence (harnesses/DESIGN.md §4)."""
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
    """Inclusive range of the target value, of every option value and of every distractor
    value (all 3-digit)."""
    minor_component_range: tuple[int, int] = (61, 98)
    """Inclusive range of the 2-digit additive clue values (offset, shift). Kept above 59 so
    they can never collide with clock fields in the log filler."""
    option_spacing: int = 1
    """The K options are one cluster of evenly spaced values around the target (PREREG D2):
    sorted options are target + (i - rank) * option_spacing. With every addend drawn at least
    rank * spacing above the bottom and (K - 1 - rank) * spacing below the top of
    `minor_component_range`, no proper subset of the clues (with the rule) rules out any
    option."""
    clue_form: str = "direct"
    """How each clue value is given (PREREG §17.3, amendment R3; gpt-6.1-sol only, preset
    `sol-chain`). 'direct': the clue's binding prints its value. 'chain': the value is never
    printed; the clue's record gives it through a two-hop relay over helper entities (an
    anchor value, a far and a near difference, and a decoy difference), so that working it
    out takes two 3-digit operations (`template.ChainSpec`), though the units digits alone pick
    the option. Template values (options, clue values, ranks, stand-in) are those of the
    direct form for every seed."""

    # --- distractor bindings (PREREG D1) ---
    n_distractors: int = 2
    """Key-value bindings about other entities of the same kind, in the target's sentence
    frame, shown once each at steps that hold no evidence in any cell. Never needed; their
    values avoid every option and clue value; lookup serves their keys too (D3)."""

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
    evidence_notice: bool = False
    """PREREG §17.3 (amendment R3; gpt-6.1-sol only, preset `sol-chain`): each evidence step
    of the target says, after its record, that the target's quantity will be requested later,
    and (derived) asks the agent to work out as much of it as the records allow and keep it
    in mind without writing it (`render.notice_text`). The withheld control names its
    stand-in instead. Never in the record line, so lookups and the restated block do not
    repeat it."""

    # --- lookup (recoverable cells) ---
    lookup_max_per_episode: int = 3
    """Lookups served per episode (PREREG D3). Once they are used, a lookup returns 'lookup
    unavailable' and costs one turn (once per pending step); it is not scored as an answer."""
    lookup_scope: str = "revealed_so_far"
    """A lookup re-shows only the records already displayed at or before the pending step."""

    # --- action parsing and scoring (PREREG D4: both rules pre-registered) ---
    accept_value_answers: bool = True
    """At the need step, accept the option value as well as its letter."""
    strict_action_parse: bool = False
    """True: only a line 'ACTION: verb(arg)' counts. False: if no ACTION line, fall back to
    the last 'verb(arg)' with a known verb anywhere in the reply."""

    # Survival accounting for notes and summary cells uses one fixed rule (PREREG D6), not a
    # config field: whole-word match of the target value, or of every clue value, with
    # `(?<![0-9A-Za-z])VALUE(?![0-9A-Za-z])`; the rule need not be carried
    # (survival.carried_in_text).

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
        if self.option_spacing < 1:
            raise ValueError("option_spacing must be >= 1")
        if mhi - mlo < (self.K_options - 1) * self.option_spacing:
            raise ValueError("minor_component_range is too narrow for the option cluster: every "
                             "addend must leave room for (K - 1) * option_spacing")
        if hi - lo < (self.K_options - 1) * self.option_spacing + self.n_distractors:
            raise ValueError("value_range must hold the option cluster and the distractor values")
        if not 0 <= self.n_distractors <= 4:
            raise ValueError("n_distractors must be between 0 and 4")
        if self.near_gap_steps >= self.far_gap_steps:
            raise ValueError("near_gap_steps must be smaller than the far gap")
        need_lo, need_hi = self.need_index_range
        if need_lo < self.min_need_index or need_hi < need_lo:
            raise ValueError(
                f"need_index_range {self.need_index_range} too small: far derived cells need "
                f"need index >= {self.min_need_index} with these W, v and clue settings")
        if self.clue_form not in CLUE_FORMS:
            raise ValueError(f"clue_form must be one of {CLUE_FORMS}")
        if self.clue_form == "chain":
            # The relay's H1 value is drawn from [clue max + CHAIN_V1_GAP, 999] for the
            # target's and the stand-in's clue in each slot (template._chains), so that
            # range must not be empty; atom-level partial memory needs consecutive options.
            if self.option_spacing != 1:
                raise ValueError("clue_form 'chain' needs option_spacing 1")
            highest = [mhi] + [hi - (m - 1) * mlo for m in self.n_clues_choices]
            if max(highest) + CHAIN_V1_GAP > 999:
                raise ValueError(
                    f"clue_form 'chain': a clue can reach {max(highest)}, so the relay's "
                    f"H1 value (clue + at least {CHAIN_V1_GAP}) would pass 999; lower "
                    "value_range or raise minor_component_range")

    # ------------------------------------------------------------------
    @property
    def far_gap_steps(self) -> int:
        """Smallest gap g (need index - latest reveal index) with (g+1)*v > W + margin.

        Assumes every observation has exactly v tokens; the generator re-checks the real
        token counts after rendering."""
        return math.floor((self.W_tokens + self.far_margin_tokens) / self.v_tokens)

    @property
    def addend_core_range(self) -> tuple[int, int]:
        """Range of an addend minus its rank shift: addend = core + rank * option_spacing.
        Every addend then lies in [lo + rank * s, hi - (K - 1 - rank) * s] (PREREG D2)."""
        lo, hi = self.minor_component_range
        return lo, hi - (self.K_options - 1) * self.option_spacing

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
        """Every field, tuples as lists, except a field added by generator 0.4.0 that has
        its default (`ADDED_IN_0_4`): so the default config's dict and hash are unchanged."""
        d = dataclasses.asdict(self)
        for k, v in d.items():
            if isinstance(v, tuple):
                d[k] = list(v)
        for k, default in ADDED_IN_0_4.items():
            if d[k] == default:
                del d[k]
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
    "window_counts_system_prompt": ("§6, D5", ("W also holds the episode's system prompt "
                                                "(not the notes sentence)")),
    "max_context_tokens": ("§5", "'contexts stay <= 64k' (full history, assumed replies)"),
    "K_options": ("§5", "number of options at need; chance = 1/K"),
    "need_index_range": ("§5", "episode length ~20-32 steps"),
    "tail_steps_range": ("§5", "routine steps after need (cost without information)"),
    "n_clues_choices": ("§4, D2", "derived = 2-3 clues; exact split within each K-block"),
    "option_spacing": ("§5, D2", "clustered options: no proper clue subset narrows them"),
    "n_distractors": ("§5, D1", "distractor bindings per episode; lookup serves them (D3)"),
    "clue_spacing_steps": ("§4", "'shown at different steps'; spacing sets the reveal span"),
    "rule_placement": ("§5", "where the combining rule is shown"),
    "restate_mode": ("§5", "what restated-at-need repeats for derived facts"),
    "single_turn_reply_mode": ("§5, H3", "what fills reply positions in the flattened control"),
    "warn_future_need": ("§5", "whether agents are told that earlier records matter later"),
    "lookup_max_per_episode": ("§4, D3", "lookups served per episode; then 'unavailable'"),
    "accept_value_answers": ("§4, D4", "need-step scoring: letter only, or letter or value"),
    "strict_action_parse": ("§4, D4", "what counts as the reply's action"),
    "validity_margin_pp": ("§5, §16.3", "no-memory baselines <= chance + 10pp"),
    "clue_form": ("§2.4, R3", ("clue values printed (direct) or given by a two-hop relay "
                               "(chain; sol only)")),
    "evidence_notice": ("§5, R3", ("evidence steps say the value will be requested and ask "
                                   "for it to be worked out privately (sol only)")),
}

DEFAULT_CONFIG = GeneratorConfig()

PRESETS: dict[str, GeneratorConfig] = {
    "default": DEFAULT_CONFIG,
    "sol-chain": GeneratorConfig(clue_form="chain", evidence_notice=True,
                                 rule_placement="with_first_clue"),
}
"""Named generator configs. `default` is every model's config except where PREREG §17.3
(amendment R3) gives gpt-6.1-sol `sol-chain`: chain clues, the evidence notice, and the rule
shown with the first clue, so that the evidence steps are exactly the clue steps."""
PRESET_HASHES: dict[str, str] = {
    "default": "3d6bc648eaa9b9e843fe6e70060495cd197630b0f2d585e66b3cd280b7a3968b",
    "sol-chain": "b0d0b020d5b9135bad3b4cb4c074a19bdbb8590e51dd04a690ba0fcaedbaaf97",
}
"""`common.runmeta.config_hash(PRESETS[name].to_dict())`, pinned (a test checks each). The
spot-check and the registered-settings guard (`harnesses.registered`) read the hashes from
here only."""
