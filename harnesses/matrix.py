"""Run matrix: which task cells run on how many templates (PREREG §4.6; D11).

A `RunMatrix` maps each task cell to a template count n. The cell runs on the first n
templates from `--start` of the split, so cells with fewer templates use a prefix of the
templates of cells with more, and every contrast stays within-template.

Presets:
* `full(n)`: every task cell (or a chosen list) on n templates: PLAN §5's fully crossed design.
* `d11(T_d, T_o)`: the researcher's D11 option A for sol (2026-10-01): F-r vs F-0 on the two
  derived-far cells for T_d templates and on the two observed-far cells for the first
  T_o = T_d / 3 of them; no near cells. Under D7 the template counts are multiples of 10 (T_d
  a multiple of 30), so that the generator's 10-template balance blocks are complete.

Episodes come out template by template (all of a template's cells together, in
`persistgym.episode.ALL_CELLS` order), so a run stopped early by its cost cap leaves whole
templates plus at most one partial template (the one in progress).

Repeats (PREREG §2.9; D7, §0.3 line 10): `matrix.repeat(split, start)` is the same matrix at
`repeat_index` 1. It plays only the main templates whose seed is divisible by
`REPEAT_EVERY`, each in the task cells it plays at repeat 0, so a repeat-1 run of a cell or
control replays exactly those episodes of its repeat-0 run. The episodes are the same: the
generator is seeded by the template, and the provider's sampling is not, which is the
within-template noise a repeat measures. A matrix at repeat 0 plays every template, as
before repeats existed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from persistgym.config import GeneratorConfig
from persistgym.episode import ALL_CELLS, Episode, TaskCell
from persistgym.render import generate
from persistgym.template import seed_for

DERIVED_FAR = ("derived-nonrec-far", "derived-rec-far")
OBSERVED_FAR = ("observed-nonrec-far", "observed-rec-far")
BALANCE_BLOCK = 10  # the generator balances letters and ranks within blocks of 10 templates
CELL_ORDER = [c.id for c in ALL_CELLS]
REPEAT_EVERY = 10
"""PREREG §2.9: main templates whose seed is divisible by 10 also play repeat_index 1."""
REPEAT_SPLIT = "main"
"""PREREG §2.9: repeats are for main templates only."""


@dataclass(frozen=True)
class RunMatrix:
    name: str
    templates: tuple[tuple[str, int], ...]  # (task cell id, number of templates), ALL_CELLS order
    repeat_index: int = 0
    # repeat 1 (`repeat`): the templates it plays, as offsets from --start; None: all of them
    offsets: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        seen = set()
        for cid, n in self.templates:
            TaskCell.from_id(cid)  # raises on a bad id
            if cid in seen:
                raise ValueError(f"task cell {cid} given twice")
            if not isinstance(n, int) or n < 0:
                raise ValueError(f"template count for {cid} must be an integer >= 0, got {n!r}")
            seen.add(cid)
        if not any(n for _, n in self.templates):
            raise ValueError("the run matrix has no episodes")
        if self.repeat_index not in (0, 1) or (self.repeat_index == 1) != (
                self.offsets is not None):
            raise ValueError("a run matrix is at repeat 0 with every template, or at repeat 1 "
                             "with its templates (`repeat`)")

    # ------------------------------------------------------------------
    @classmethod
    def _make(cls, name: str, counts: dict[str, int]) -> RunMatrix:
        unknown = set(counts) - set(CELL_ORDER)
        if unknown:
            raise ValueError(f"unknown task cells {sorted(unknown)}")
        return cls(name, tuple((c, counts[c]) for c in CELL_ORDER if c in counts))

    @classmethod
    def full(cls, n: int, cells: list[str] | None = None) -> RunMatrix:
        return cls._make("full", {c: n for c in (cells or CELL_ORDER)})

    @classmethod
    def d11(cls, T_d: int, T_o: int | None = None) -> RunMatrix:
        if T_o is None:
            if T_d % 3:
                raise ValueError(f"T_o defaults to T_d / 3, but T_d = {T_d} is not a multiple "
                                 "of 3: give the observed-far template count explicitly")
            T_o = T_d // 3
        if not 0 <= T_o <= T_d:
            raise ValueError(f"need 0 <= T_o <= T_d, got T_d = {T_d}, T_o = {T_o}")
        return cls._make("d11", {**dict.fromkeys(DERIVED_FAR, T_d),
                                 **dict.fromkeys(OBSERVED_FAR, T_o)})

    @classmethod
    def parse(cls, specs: list[str]) -> RunMatrix:
        """A custom matrix from 'TASK_CELL=N' strings."""
        counts: dict[str, int] = {}
        for s in specs:
            cid, sep, n = s.partition("=")
            if not sep:
                raise ValueError(f"expected TASK_CELL=N, got {s!r}")
            if cid in counts:
                raise ValueError(f"task cell {cid} given twice")
            counts[cid] = int(n)
        return cls._make("custom", counts)

    def repeat(self, split: str, start: int) -> RunMatrix:
        """This matrix at repeat_index 1 (PREREG §2.9): the templates among its first
        `n_templates` from `start` whose seed is divisible by `REPEAT_EVERY`, each in the task
        cells it plays at repeat 0. Main split only; refuses (ValueError) another split, a
        matrix that is a repeat already, and a range with no such template."""
        if split != REPEAT_SPLIT:
            raise ValueError(f"--repeat-index 1 plays main templates only (PREREG §2.9), got "
                             f"--split {split}")
        if self.repeat_index:
            raise ValueError("the run matrix is a repeat already")
        offsets = tuple(k for k in range(self.n_templates)
                        if seed_for(split, start + k) % REPEAT_EVERY == 0)
        if not offsets:
            raise ValueError(f"no template of {split} {start}-{start + self.n_templates - 1} "
                             f"has a seed divisible by {REPEAT_EVERY}: --repeat-index 1 "
                             "would play nothing (PREREG §2.9)")
        return replace(self, repeat_index=1, offsets=offsets)

    # ------------------------------------------------------------------
    @property
    def n_templates(self) -> int:
        """The templates the matrix spans from --start (at repeat 1 too: the repeat-0 range
        its templates come from)."""
        return max(n for _, n in self.templates)

    @property
    def played(self) -> tuple[int, ...]:
        """The templates the run plays, as offsets from --start: all `n_templates` at repeat
        0, the repeat subset at repeat 1."""
        return tuple(range(self.n_templates)) if self.offsets is None else self.offsets

    @property
    def n_episodes(self) -> int:
        return sum(len(self.cells_for(k)) for k in self.played)

    def cells_for(self, k: int) -> list[str]:
        """Task cells run on the k-th template (0-based from --start)."""
        return [c for c, n in self.templates if k < n]

    def to_dict(self) -> dict:
        """The matrix as meta.json and the run plan record it. At repeat 1 it adds the repeat
        index and the templates played (offsets from --start), and `n_episodes` counts the
        episodes played; `templates_per_task_cell` and `n_templates` stay the matrix's."""
        out = {"name": self.name, "templates_per_task_cell": dict(self.templates),
               "n_templates": self.n_templates, "n_episodes": self.n_episodes}
        if self.repeat_index:
            out.update(repeat_index=self.repeat_index, repeat_every=REPEAT_EVERY,
                       template_offsets=list(self.played))
        return out

    def block_warnings(self, start: int) -> list[str]:
        """D7: main-sweep template counts and the start come in whole 10-template blocks."""
        out = []
        if start % BALANCE_BLOCK:
            out.append(f"--start {start} is not a multiple of {BALANCE_BLOCK}")
        for c, n in self.templates:
            if n % BALANCE_BLOCK:
                out.append(f"{c}: {n} templates is not a multiple of {BALANCE_BLOCK}")
        return out

    def episodes(self, split: str, start: int, gen: GeneratorConfig,
                 variant: str = "base") -> list[Episode]:
        """The run's episodes, template by template. A repeat-1 matrix must get the split
        and start it was made with (`repeat`): any template it would play off the repeat
        subset refuses (ValueError)."""
        if self.repeat_index and (split != REPEAT_SPLIT or any(
                seed_for(split, start + k) % REPEAT_EVERY for k in self.played)):
            raise ValueError(f"this repeat-1 matrix plays main templates whose seed is "
                             f"divisible by {REPEAT_EVERY} only; got {split} from {start}")
        out: list[Episode] = []
        for k in self.played:
            cells = [TaskCell.from_id(c) for c in self.cells_for(k)]
            for _, eps in generate(split, [start + k], gen, cells, (variant,)):
                out.extend(eps)
        return out
