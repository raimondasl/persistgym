"""PersistGym harness cells (PLAN.md §6).

A cell fixes three harness components and nothing else:
* history / loss policy: full history, a drop-oldest token window W, or a summary at W;
* the notes instruction (ARC Standard's carry-forward sentence, verbatim);
* reasoning replay: `reasoning.context` = `all_turns` (r) or `current_turn` (0).

Encrypted reasoning items are sent in every cell, so the r and 0 arms of a pair send the same
items and differ only in `reasoning.context` (PLAN §7). See harnesses/DESIGN.md.
"""

from __future__ import annotations

from dataclasses import dataclass

# ARC Standard's carry-forward sentence, verbatim (PLAN §6; ARC harness at 4ca00e6,
# benchmarking/agent.py::_build_system_prompt,
# https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/benchmarking/agent.py).
NOTES_INSTRUCTION = (
    "Include any context you want to carry forward in your reply, along with the action you "
    "want to take."
)

HISTORY_POLICIES = ("full", "window", "summary")

REPLAY_CONTEXT = {True: "all_turns", False: "current_turn"}


@dataclass(frozen=True)
class CellSpec:
    cell_id: str  # as in PLAN §6, e.g. "Σ-n-r"
    history: str  # "full" | "window" | "summary"
    notes: bool
    replay: bool
    role: str = ""
    optional: bool = False

    def __post_init__(self) -> None:
        if self.history not in HISTORY_POLICIES:
            raise ValueError(f"bad history policy {self.history!r}")

    @property
    def reasoning_context(self) -> str:
        """The `reasoning.context` value this cell requests (always set explicitly)."""
        return REPLAY_CONTEXT[self.replay]

    @property
    def ascii_id(self) -> str:
        """File-system safe id: 'Σ' becomes 'sigma' (e.g. 'sigma-n-r')."""
        return self.cell_id.replace("Σ", "sigma")

    @property
    def pair_id(self) -> str:
        """The cell id without its replay suffix; r and 0 arms of a pair share it."""
        return self.cell_id.rsplit("-", 1)[0]


# PLAN §6 table, in its order.
CELLS: dict[str, CellSpec] = {c.cell_id: c for c in (
    CellSpec("F-r", "full", notes=False, replay=True, role="ceiling"),
    CellSpec("F-0", "full", notes=False, replay=False, role="H1/H3 comparator"),
    CellSpec("W-n-r", "window", notes=True, replay=True),
    CellSpec("W-n-0", "window", notes=True, replay=False, role="≈ ARC Standard"),
    CellSpec("Σ-n-r", "summary", notes=True, replay=True),
    CellSpec("Σ-n-0", "summary", notes=True, replay=False),
    CellSpec("W-0", "window", notes=False, replay=False, role="isolates notes"),
    CellSpec("Σ-0-r", "summary", notes=False, replay=True, role="≈ ARC Adapter", optional=True),
)}

# Replay-off cells: the only cells to run on a model that does not honour `all_turns`
# (PLAN §7: luna runs F-0, W-n-0, Σ-n-0, W-0 if its echo check fails).
REPLAY_OFF_CELLS = tuple(c for c in CELLS if not CELLS[c].replay)

# r/0 pairs that differ only in reasoning.context.
REPLAY_PAIRS = (("F-r", "F-0"), ("W-n-r", "W-n-0"), ("Σ-n-r", "Σ-n-0"))


def get_cell(cell_id: str) -> CellSpec:
    """Look up a cell by its PLAN id or its ASCII id ('sigma-n-r', also 'S-n-r')."""
    if cell_id in CELLS:
        return CELLS[cell_id]
    for c in CELLS.values():
        if cell_id in (c.ascii_id, c.cell_id.replace("Σ", "S")):
            return c
    raise KeyError(f"unknown harness cell {cell_id!r}; known: {', '.join(CELLS)}")
