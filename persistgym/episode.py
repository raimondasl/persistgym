"""Episode data model (the contract the harness cells build on).

An Episode is one template rendered into one task cell and one variant. It is a fixed script
of `steps`; each step is one observation (a new user message) that expects one action. The
only dynamic part is `lookup` in recoverable cells, which `env.EpisodeEnv` handles: a lookup
inserts one extra observation and re-asks the pending step (see DESIGN.md "Lookup").

Everything serializes to plain JSON (`to_dict` / `from_dict`), one episode per JSONL line.

Schema 2 (generator 0.2.0) adds the distractor bindings (`Episode.distractors`, step kind
"distractor", `Step.distractors`), `Component.entity` and `LookupSpec.record_keys`.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

from persistgym.graph import DependencyGraph

FACT_KINDS = ("observed", "derived")
DISTANCES = ("near", "far")
VARIANTS = ("base", "restated", "withheld")
STEP_KINDS = ("routine", "reveal", "distractor", "need")


@dataclass(frozen=True)
class TaskCell:
    fact: str  # "observed" | "derived"
    recoverable: bool
    distance: str  # "near" | "far"

    def __post_init__(self) -> None:
        if self.fact not in FACT_KINDS or self.distance not in DISTANCES:
            raise ValueError(f"bad task cell {self}")

    @property
    def id(self) -> str:
        return f"{self.fact}-{'rec' if self.recoverable else 'nonrec'}-{self.distance}"

    @classmethod
    def from_id(cls, cell_id: str) -> TaskCell:
        fact, rec, dist = cell_id.split("-")
        if rec not in ("rec", "nonrec"):
            raise ValueError(f"bad cell id {cell_id!r}")
        return cls(fact, rec == "rec", dist)


ALL_CELLS: tuple[TaskCell, ...] = tuple(
    TaskCell(f, r, d) for f in FACT_KINDS for r in (False, True) for d in DISTANCES)


@dataclass
class Component:
    """One piece of revealed information. Observed cells have one ('fact'); derived cells
    have 2-3 clues plus a 'rule'. Distractor bindings (`Episode.distractors`) use the same
    shape with role 'distractor': a binding about another entity, never needed."""

    comp_id: str  # "fact" | "clue0" | "clue1" | "clue2" | "rule" | "dist0" | "dist1" ...
    role: str  # "fact" | "clue" | "rule" | "distractor"
    name: str  # quantity name (fact, rule) or clue name, e.g. "priority offset"
    value: int | None  # None for the rule
    sentence: str  # the information-bearing sentence, verbatim as displayed
    record: str  # the full record line as displayed, "<source> <id>. <sentence>"
    step: int | None  # step index that first shows it; None = system prompt (rule) only
    entity: str = ""  # the binding's key: the target entity, or another entity (distractor)


@dataclass
class Option:
    label: str  # "A".."J"
    value: int


@dataclass
class Step:
    index: int
    kind: str  # "routine" | "reveal" | "distractor" | "need"
    routine_type: str | None  # "route" | "threshold" | "broadcast" | "memo" | None (need)
    event: str  # the EVENT text (the part the action depends on)
    observation: str  # the full user message: log tail + EVENT
    obs_tokens: int  # tiktoken o200k_base count of `observation`
    event_start: int  # char span of `event` inside `observation`
    event_end: int
    filler_start: int  # char span of the log filler inside `observation`
    filler_end: int
    expected_action: str  # canonical correct action, e.g. "route(billing)", "assign(C)"
    reveals: list[str] = field(default_factory=list)  # component ids first shown here
    restates: list[str] = field(default_factory=list)  # component ids repeated here (control)
    sim_time: str = ""  # simulated clock time of the observation
    distractors: list[str] = field(default_factory=list)  # distractor ids shown here


@dataclass
class LookupSpec:
    """Lookup semantics (recoverable cells). See env.EpisodeEnv for the exact behaviour."""

    available: bool
    key: str  # the target entity name; lookup(<key>) is case-insensitive
    syntax: str  # e.g. "lookup(<shipment name>)"
    max_per_episode: int
    records: dict[str, str]  # record id (comp_id, null<k>, dist<k>) -> line re-shown
    reveal_steps: dict[str, int]  # record id -> step at which the record is first shown
    record_keys: dict[str, str] = field(default_factory=dict)
    """record id -> the entity it is about (the target or a distractor); a lookup key
    matches an entity it contains as a whole word. Missing ids belong to `key`."""

    def key_of(self, record_id: str) -> str:
        return self.record_keys.get(record_id, self.key)


@dataclass
class Episode:
    schema_version: int
    generator_version: str
    config_hash: str
    config: dict
    episode_id: str
    template_id: str
    template_seed: int
    split: str  # "main" | "pilot"
    cell: TaskCell
    variant: str  # "base" | "restated" | "withheld"
    skin: str
    kind: str  # entity kind, e.g. "shipment"
    entity: str  # e.g. "ORION"
    quantity: str  # e.g. "loading bay"
    need_verb: str  # e.g. "assign"
    system_prompt: str
    system_tokens: int
    steps: list[Step]
    need_step: int
    n_clues: int  # 0 for observed cells
    components: list[Component]  # what the agent must carry (empty when withheld)
    target_value: int
    options: list[Option]
    correct_label: str
    lookup: LookupSpec
    graph: DependencyGraph
    design: dict  # designed survival and distances, see survival.episode_design
    distractors: list[Component] = field(default_factory=list)
    """Distractor bindings (role 'distractor'): same steps and text in every cell and
    variant of a template; never needed (PREREG D1)."""

    # ------------------------------------------------------------------
    @property
    def n_steps(self) -> int:
        return len(self.steps)

    @property
    def observations(self) -> list[str]:
        return [s.observation for s in self.steps]

    @property
    def obs_tokens(self) -> list[int]:
        return [s.obs_tokens for s in self.steps]

    @property
    def need(self) -> Step:
        return self.steps[self.need_step]

    @property
    def correct_option(self) -> Option:
        return self.option(self.correct_label)

    def option(self, label: str) -> Option:
        for o in self.options:
            if o.label == label:
                return o
        raise KeyError(label)

    def component(self, comp_id: str) -> Component:
        for c in self.components:
            if c.comp_id == comp_id:
                return c
        raise KeyError(comp_id)

    @property
    def reveal_steps(self) -> list[int]:
        return sorted({c.step for c in self.components if c.step is not None})

    @property
    def fact_available(self) -> bool:
        return bool(self.components)

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["cell"] = self.cell.id
        d["graph"] = self.graph.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Episode:
        d = dict(d)
        d["cell"] = TaskCell.from_id(d["cell"])
        d["steps"] = [Step(**s) for s in d["steps"]]
        d["components"] = [Component(**c) for c in d["components"]]
        d["distractors"] = [Component(**c) for c in d.get("distractors", [])]
        d["options"] = [Option(**o) for o in d["options"]]
        d["lookup"] = LookupSpec(**d["lookup"])
        d["graph"] = DependencyGraph.from_dict(d["graph"])
        return cls(**d)


def read_jsonl(path: str | Path) -> Iterator[Episode]:
    """Episodes from an episodes.jsonl or episodes.jsonl.gz file written by the CLI."""
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield Episode.from_dict(json.loads(line))
