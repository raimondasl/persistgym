"""Template sampling. A template is one sampled skeleton (surface story, fact values, option
set, routine events, clock, filler seed). It is rendered into all 8 task cells and all
variants, so every contrast is within-template (PLAN §5).

Seeds: template `index` i of split s has seed SEED_RANGES[s][0] + i. Every random choice comes
from a named stream `random.Random(f"pg:{seed}:{stream}")`, so adding a stream never shifts
the others. Python's string seeding is SHA-512 based and independent of PYTHONHASHSEED.

Balance by construction: within each block of K consecutive template indices, every option
letter is the correct letter exactly once, every rank (position of the correct value among
the sorted option values) occurs exactly once, and the numbers of clues are split as evenly as
possible (5 templates with 2 clues and 5 with 3 at K = 10; PREREG D2). Run template counts in
whole blocks (PREREG D7).

Options are one cluster of evenly spaced values around the target (PREREG D2). Each addend
clue is drawn far enough from the edges of its range that every option stays consistent with
any proper subset of the clues: an agent that kept only some clues (with the rule) cannot
rule out any option.

The fact-withheld control (PREREG §4.3, D39) shows bindings about a stand-in entity in place
of the target's bindings (`SubstituteSpec`). The stand-in has the target's token length, and
its values have the formats of the values they replace and are never options, clue values or
distractor values, so the withheld episode keeps every observation's text and token count
except the bindings themselves.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache

from persistgym import tokens
from persistgym.config import SEED_RANGES, GeneratorConfig
from persistgym.filler import Reserved
from persistgym.skins import Skin, get_skin

LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
BASE_CLUE_RANGE = (100, 999)
"""The base clue is a 3-digit value (its displayed format); addends use
`GeneratorConfig.minor_component_range`."""


def rng(seed: int, stream: str) -> random.Random:
    return random.Random(f"pg:{seed}:{stream}")


def seed_for(split: str, index: int) -> int:
    if split not in SEED_RANGES:
        raise ValueError(f"unknown split {split!r}; known: {sorted(SEED_RANGES)}")
    lo, hi = SEED_RANGES[split]
    if not 0 <= index < hi - lo:
        raise ValueError(f"template index {index} outside the {split} range")
    return lo + index


def split_of_seed(seed: int) -> tuple[str, int]:
    for split, (lo, hi) in SEED_RANGES.items():
        if lo <= seed < hi:
            return split, seed - lo
    raise ValueError(f"seed {seed} is in no split range")


def template_id(split: str, index: int) -> str:
    return f"{split}-{index:06d}"


@dataclass
class RoutineSpec:
    type: str  # "route" | "threshold" | "broadcast"
    event: str
    expected_action: str


@dataclass
class DistractorSpec:
    """A key-value binding about another entity (PREREG D1). Never needed."""

    entity: str
    value: int
    record_id: str
    step: int


@dataclass
class SubstituteSpec:
    """The stand-in of the fact-withheld control (PREREG §4.3, D39): another entity of the
    skin whose name has the target's token length, with a value in place of the observed fact
    and clue values in place of the target's clues (same count and digit formats). `value` is
    the sum of `clue_values`, as for the target. None of these values is an option, a clue
    value of the target or a distractor value."""

    entity: str
    value: int
    clue_values: list[int]  # [base, addend(, addend)], len == the template's n_clues


@lru_cache(maxsize=4096)
def entity_token_length(name: str, enc: str = "o200k_base") -> int:
    """Tokens of an entity name as it appears in a binding (" NAME", after a word)."""
    return tokens.count(f" {name}", enc)


@dataclass
class Template:
    template_id: str
    split: str
    index: int
    seed: int
    skin: str
    site: str
    entity: str
    target_value: int
    option_values: list[int]  # display order, A..
    correct_index: int
    n_clues: int
    clue_values: list[int]  # [base, offset(, shift)]; sum == target_value; addends may repeat
    record_ids: dict[str, str]  # "fact"/"clue0".."clue2"/"rule" -> record id "M-####"
    substitute: SubstituteSpec  # stand-in of the fact-withheld control (D39)
    need_index: int
    tail_steps: int
    routine: list[RoutineSpec]  # one per step index (used where the step is routine)
    t0: str  # ISO time of step 0
    reserved_numbers: list[int] = field(default_factory=list)
    reserved_words: list[str] = field(default_factory=list)
    distractors: list[DistractorSpec] = field(default_factory=list)

    @property
    def skin_obj(self) -> Skin:
        return get_skin(self.skin)

    @property
    def n_steps(self) -> int:
        return self.need_index + 1 + self.tail_steps

    @property
    def correct_label(self) -> str:
        return LABELS[self.correct_index]

    @property
    def rank(self) -> int:
        """Position of the target among the sorted option values."""
        return sorted(self.option_values).index(self.target_value)

    @property
    def block(self) -> int:
        """Balance block: template indices block*K .. block*K + K - 1 of the split."""
        return self.index // len(self.option_values)

    @property
    def reserved(self) -> Reserved:
        return Reserved(self.reserved_numbers, self.reserved_words)

    @property
    def t0_dt(self) -> datetime:
        return datetime.fromisoformat(self.t0)


def _block_perm(split: str, what: str, block: int, k: int) -> list[int]:
    perm = list(range(k))
    random.Random(f"pg:{split}:{what}:{block}").shuffle(perm)
    return perm


def component_schedule(need_index: int, n_clues: int, fact: str, distance: str,
                       cfg: GeneratorConfig) -> dict[str, int | None]:
    """Reveal step of every component of one task cell (None = rule in the system prompt).
    The latest reveal is `near_gap_steps` or `far_gap_steps` before the need step."""
    n = need_index
    g = cfg.near_gap_steps if distance == "near" else cfg.far_gap_steps
    s = cfg.clue_spacing_steps
    if fact == "observed":
        return {"fact": n - g}
    clues = [f"clue{i}" for i in range(n_clues)]
    steps: dict[str, int | None] = {}
    if cfg.rule_placement == "separate_step":
        steps["rule"] = n - g
        for i, cid in enumerate(reversed(clues)):
            steps[cid] = n - g - (i + 1) * s
    else:
        for i, cid in enumerate(clues):
            steps[cid] = n - g - (len(clues) - 1 - i) * s
        steps["rule"] = {"with_last_clue": steps[clues[-1]], "with_first_clue": steps[clues[0]],
                         "system_prompt": None}[cfg.rule_placement]
    return {cid: steps[cid] for cid in [*clues, "rule"]}


def evidence_steps_any_cell(need_index: int, n_clues: int, cfg: GeneratorConfig) -> set[int]:
    """Steps that show evidence in at least one of the 8 task cells of a template."""
    out: set[int] = set()
    for fact in ("observed", "derived"):
        for distance in ("near", "far"):
            sched = component_schedule(need_index, n_clues, fact, distance, cfg)
            out |= {st for st in sched.values() if st is not None}
    return out


def _clustered_options(r: random.Random, rank: int, cfg: GeneratorConfig) -> tuple[int, list[int]]:
    """Target and the sorted option values: K evenly spaced values with the target at `rank`.
    The cluster's lowest value is uniform over the value range whatever the rank, so the
    option values carry no information about the rank."""
    K, s = cfg.K_options, cfg.option_spacing
    lo, hi = cfg.value_range
    target = r.randint(lo + rank * s, hi - (K - 1 - rank) * s)
    return target, [target + (i - rank) * s for i in range(K)]


def _clues(r: random.Random, target: int, rank: int, n_clues: int,
           cfg: GeneratorConfig) -> list[int]:
    """[base, addend(, addend)] summing to the target. Each addend is core + rank * spacing,
    with the core uniform in `cfg.addend_core_range` (drawn independently, so two addends may
    be equal). Every addend then lies in [lo + rank * s, hi - (K - 1 - rank) * s] of
    `minor_component_range`, so for any proper subset of the clues every option has a
    completion within the clue ranges (PREREG D2). The base is what is left of the target."""
    clo, chi = cfg.addend_core_range
    addends = [r.randint(clo, chi) + rank * cfg.option_spacing for _ in range(n_clues - 1)]
    base = target - sum(addends)
    if not BASE_CLUE_RANGE[0] <= base <= BASE_CLUE_RANGE[1]:
        raise RuntimeError(f"base clue {base} is not a 3-digit value; widen value_range")
    return [base, *addends]


def _substitute(r: random.Random, skin: Skin, entity: str, dist_entities: list[str],
                n_clues: int, taken: set[int], cfg: GeneratorConfig) -> SubstituteSpec:
    """The stand-in of the fact-withheld control (PREREG D39).

    The entity is another entity of the skin with the target's token length that is not a
    distractor, so a binding about it has the target binding's token length. The value is
    drawn from `value_range` like a distractor value, and the clues are drawn as the target's
    are (each addend is core + shift with an independent rank shift; the base is what is
    left), so they keep the target's formats: a 3-digit value and base, 2-digit addends. No
    value is in `taken` (options, the target's clue values, distractor values); the value,
    which is also what the stand-in's clues and the rule derive, is therefore never an
    option."""
    n_tok = entity_token_length(entity, cfg.tokenizer)
    cands = [e for e in skin.entities if e != entity and e not in dist_entities
             and entity_token_length(e, cfg.tokenizer) == n_tok]
    if not cands:
        raise RuntimeError(f"skin {skin.name!r}: no stand-in entity with the token length of "
                           f"{entity!r} outside the distractors (see skins.MIN_TOKEN_CLASS)")
    sub_entity = r.choice(cands)
    lo, hi = cfg.value_range
    clo, chi = cfg.addend_core_range
    for _ in range(1000):
        value = r.randint(lo, hi)
        shift = r.randrange(cfg.K_options) * cfg.option_spacing
        addends = [r.randint(clo, chi) + shift for _ in range(n_clues - 1)]
        clues = [value - sum(addends), *addends]
        if (value not in taken and not set(clues) & taken
                and BASE_CLUE_RANGE[0] <= clues[0] <= BASE_CLUE_RANGE[1]):
            return SubstituteSpec(sub_entity, value, clues)
    raise RuntimeError("cannot sample withheld-control values outside the taken values")


def _routine(r: random.Random, skin: Skin, reserved: Reserved, used_ids: set[str]) -> RoutineSpec:
    for _ in range(1000):
        kind = r.choice(("route", "threshold", "broadcast"))
        if kind == "route":
            rid = f"T-{r.randint(1000, 9999)}"
            tag = r.choice(skin.route_tags)
            event = (f"{skin.route_noun} {rid} arrived with tag '{tag}'. Route it to the team "
                     f"named by its tag: reply route(<tag>).")
            action = f"route({tag})"
        elif kind == "threshold":
            rid = f"{r.choice('BCDFGHKLNPRSTVWXZ')}{r.randint(1, 9)}"
            metric, unit = r.choice(skin.sensor_metrics)
            limit = r.randint(2500, 8500)
            x = limit + r.choice((-1, 1)) * r.randint(10, 1400)
            event = (f"Sensor {rid} reports {metric} {x} {unit}; the limit is {limit} {unit}. "
                     f"Reply alert({rid}) if the reading is above the limit, otherwise reply "
                     f"ok({rid}).")
            action = f"alert({rid})" if x > limit else f"ok({rid})"
        else:
            rid = "BX-" + "".join(r.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(4))
            sender = r.choice(skin.broadcast_senders)
            event = f"Broadcast {rid} from the {sender}. Reply ack({rid}) to acknowledge it."
            action = f"ack({rid})"
        if reserved.clean(event) and rid not in used_ids:
            used_ids.add(rid)
            return RoutineSpec(kind, event, action)
    raise RuntimeError("cannot sample a reserved-clean routine event")


def sample_template(split: str, index: int, cfg: GeneratorConfig) -> Template:
    seed = seed_for(split, index)
    K = cfg.K_options
    skin = get_skin(cfg.skins[rng(seed, "skin").randrange(len(cfg.skins))])
    r_story = rng(seed, "story")
    entity = r_story.choice(skin.entities)
    site = r_story.choice(skin.sites)

    # Block-balanced: the correct letter, the target's rank among the sorted options and the
    # number of clues (an exact split within each block of K templates).
    block, pos = divmod(index, K)
    rank = _block_perm(split, "rank", block, K)[pos]
    correct_index = _block_perm(split, "label", block, K)[pos]
    choices = cfg.n_clues_choices
    n_clues = choices[_block_perm(split, "nclues", block, K)[pos] % len(choices)]

    # Options: one cluster of K evenly spaced values with the target at `rank` (PREREG D2).
    target, values = _clustered_options(rng(seed, "options"), rank, cfg)
    others = [v for v in values if v != target]
    rng(seed, "display").shuffle(others)
    option_values = others[:correct_index] + [target] + others[correct_index:]

    clue_values = _clues(rng(seed, "clues"), target, rank, n_clues, cfg)

    need_lo, need_hi = cfg.need_index_range
    tail_lo, tail_hi = cfg.tail_steps_range
    r_shape = rng(seed, "shape")
    need_index = r_shape.randint(need_lo, need_hi)
    tail_steps = r_shape.randint(tail_lo, tail_hi)

    # Distractor bindings (PREREG D1): other entities of the same kind, with values from the
    # value range that are neither options nor clue values, shown at steps that hold no
    # evidence in any of the 8 cells, so every cell shows them at the same steps and in the
    # same words.
    r_dist = rng(seed, "distractors")
    n_dist = cfg.n_distractors
    dist_entities = r_dist.sample([e for e in skin.entities if e != entity], n_dist)
    taken = set(values) | set(clue_values)
    lo, hi = cfg.value_range
    dist_values = r_dist.sample([v for v in range(lo, hi + 1) if v not in taken], n_dist)
    busy = evidence_steps_any_cell(need_index, n_clues, cfg)
    free = [i for i in range(cfg.lead_in_min_steps, need_index) if i not in busy]
    if len(free) < n_dist:
        raise RuntimeError(f"{template_id(split, index)}: no room for {n_dist} distractors")
    dist_steps = sorted(r_dist.sample(free, n_dist))

    # Stand-in of the fact-withheld control (PREREG D39), from its own stream.
    sub = _substitute(rng(seed, "withheld"), skin, entity, dist_entities, n_clues,
                      taken | set(dist_values), cfg)

    reserved_numbers = sorted(set(values) | set(clue_values) | set(dist_values)
                              | {sub.value} | set(sub.clue_values))
    reserved_words = [entity, *dist_entities, sub.entity, skin.quantity, *skin.components]
    reserved = Reserved(reserved_numbers, reserved_words)

    used: set[str] = set()

    def new_id(r: random.Random) -> str:
        while True:
            rid = f"M-{r.randint(1000, 9999)}"
            if rid not in used:
                used.add(rid)
                return rid

    r_ids = rng(seed, "ids")
    record_ids = {cid: new_id(r_ids) for cid in ("fact", "clue0", "clue1", "clue2", "rule")}
    distractors = [DistractorSpec(e, v, new_id(r_dist), st)
                   for e, v, st in zip(dist_entities, dist_values, dist_steps, strict=True)]

    r_routine = rng(seed, "routine")
    n_total = need_index + 1 + tail_steps
    routine = [_routine(r_routine, skin, reserved, used) for _ in range(n_total)]

    r_time = rng(seed, "time")
    t0 = datetime(2026, r_time.randint(1, 12), r_time.randint(1, 28), r_time.randint(6, 17),
                  r_time.randint(0, 59), r_time.randint(0, 59), tzinfo=UTC)

    return Template(
        template_id=template_id(split, index), split=split, index=index, seed=seed,
        skin=skin.name, site=site, entity=entity, target_value=target,
        option_values=option_values, correct_index=correct_index, n_clues=n_clues,
        clue_values=clue_values, record_ids=record_ids, substitute=sub,
        need_index=need_index, tail_steps=tail_steps, routine=routine, t0=t0.isoformat(),
        reserved_numbers=reserved_numbers, reserved_words=reserved_words,
        distractors=distractors)
