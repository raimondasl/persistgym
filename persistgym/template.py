"""Template sampling. A template is one sampled skeleton (surface story, fact values, option
set, routine events, clock, filler seed). It is rendered into all 8 task cells and all
variants, so every contrast is within-template (PLAN §5).

Seeds: template `index` i of split s has seed SEED_RANGES[s][0] + i. Every random choice comes
from a named stream `random.Random(f"pg:{seed}:{stream}")`, so adding a stream never shifts
the others. Python's string seeding is SHA-512 based and independent of PYTHONHASHSEED.

Balance by construction: within each block of K consecutive template indices, every option
letter is the correct letter exactly once and every rank (position of the correct value among
the sorted option values) occurs exactly once.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime

from persistgym.config import SEED_RANGES, GeneratorConfig
from persistgym.filler import Reserved
from persistgym.skins import Skin, get_skin

LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


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
    clue_values: list[int]  # [base, offset(, shift)]; sum == target_value
    record_ids: dict[str, str]  # "fact"/"clue0".."clue2"/"rule" -> record id "M-####"
    null_choice: list[int]  # which null sentence each withheld record uses
    need_index: int
    tail_steps: int
    routine: list[RoutineSpec]  # one per step index (used where the step is routine)
    t0: str  # ISO time of step 0
    reserved_numbers: list[int] = field(default_factory=list)
    reserved_words: list[str] = field(default_factory=list)

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
    def reserved(self) -> Reserved:
        return Reserved(self.reserved_numbers, self.reserved_words)

    @property
    def t0_dt(self) -> datetime:
        return datetime.fromisoformat(self.t0)


def _block_perm(split: str, what: str, block: int, k: int) -> list[int]:
    perm = list(range(k))
    random.Random(f"pg:{split}:{what}:{block}").shuffle(perm)
    return perm


def _decompose(r: random.Random, target: int, n_clues: int, cfg: GeneratorConfig,
               forbidden: set[int]) -> list[int]:
    mlo, mhi = cfg.minor_component_range
    for _ in range(10_000):
        minors = r.sample(range(mlo, mhi + 1), n_clues - 1)
        base = target - sum(minors)
        vals = [base, *minors]
        if 100 <= base <= 999 and base not in forbidden and len(set(vals)) == len(vals):
            return vals
    raise RuntimeError(f"cannot decompose {target} into {n_clues} clues")


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

    # Options: K distinct values; the correct one has a block-balanced rank and letter.
    lo, hi = cfg.value_range
    values = sorted(rng(seed, "options").sample(range(lo, hi + 1), K))
    block, pos = divmod(index, K)
    rank = _block_perm(split, "rank", block, K)[pos]
    correct_index = _block_perm(split, "label", block, K)[pos]
    target = values[rank]
    others = [v for v in values if v != target]
    rng(seed, "display").shuffle(others)
    option_values = others[:correct_index] + [target] + others[correct_index:]

    n_clues = rng(seed, "nclues").choice(cfg.n_clues_choices)
    clue_values = _decompose(rng(seed, "clues"), target, n_clues, cfg, set(values))

    need_lo, need_hi = cfg.need_index_range
    tail_lo, tail_hi = cfg.tail_steps_range
    r_shape = rng(seed, "shape")
    need_index = r_shape.randint(need_lo, need_hi)
    tail_steps = r_shape.randint(tail_lo, tail_hi)

    reserved_numbers = sorted(set(values) | set(clue_values))
    reserved_words = [entity, skin.quantity, *skin.components]
    reserved = Reserved(reserved_numbers, reserved_words)

    r_ids = rng(seed, "ids")
    record_ids: dict[str, str] = {}
    used: set[str] = set()
    for cid in ("fact", "clue0", "clue1", "clue2", "rule"):
        while True:
            rid = f"M-{r_ids.randint(1000, 9999)}"
            if rid not in used:
                used.add(rid)
                record_ids[cid] = rid
                break
    null_choice = [r_ids.randrange(len(skin.null_records)) for _ in range(4)]

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
        clue_values=clue_values, record_ids=record_ids, null_choice=null_choice,
        need_index=need_index, tail_steps=tail_steps, routine=routine, t0=t0.isoformat(),
        reserved_numbers=reserved_numbers, reserved_words=reserved_words)
