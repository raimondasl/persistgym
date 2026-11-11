"""PersistGym harness cells (PLAN.md §6).

A cell fixes three harness components and nothing else:
* history / loss policy: full history, a drop-oldest token window W, or a summary at W;
* the notes instruction (ARC Standard's carry-forward sentence, verbatim);
* reasoning replay: `reasoning.context` = `all_turns` (r) or `current_turn` (0).

Encrypted reasoning items are sent in every cell, so the r and 0 arms of a pair send the same
items and differ only in `reasoning.context` (PLAN §7). See harnesses/DESIGN.md.

`NOTES_VARIANT_CELLS` are two cells outside PLAN §6's table, for amendment R10 (PREREG §17.10):
W-n-0 with one or two sentences added after the notes instruction. `R12_CELLS` are three more,
for amendment R12 (PREREG §17.12): two such notes variants, and W-b-0, a window that drops old
turns in blocks (`truncation="block"`). `get_cell` finds them all, and `CELLS`,
`REPLAY_OFF_CELLS` and `REPLAY_PAIRS` leave them out.
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

# R10 (PREREG §17.10): the sentences its two cells add after the notes instruction. The
# provenance sentence asks for each carried fact's source, and the disclosure sentence says
# that older messages can be dropped. Exploratory, written after R9's readings.
PROVENANCE_SENTENCE = (
    "For each fact you carry forward, also note where it came from: the message you read it "
    "in, or the facts and steps you worked it out from."
)
DISCLOSURE_SENTENCE = (
    "Older messages may be dropped from this conversation as it grows, so your notes may "
    "become the only record of what they said."
)

# R12 (PREREG §17.12): a sentence of the provenance sentence's length (32 project tokens) that says
# nothing about notes, sources or history, as a length-matched control for it.
NEUTRAL_SENTENCE = (
    "For each action you choose, also check how it is written: the verb that the EVENT asks "
    "for, and its argument in the syntax that the EVENT shows."
)

HISTORY_POLICIES = ("full", "window", "summary")

# How a window cell drops turns (R12): "slide" drops the oldest turns at every step so the kept
# context stays within W (every window cell before R12); "block" keeps its start until the kept
# context passes W, then drops the oldest turns down to W // 2, so the prompt prefix stays the
# same between drops (persistgym.survival.block_keep_start).
TRUNCATIONS = ("slide", "block")

REPLAY_CONTEXT = {True: "all_turns", False: "current_turn"}


@dataclass(frozen=True)
class CellSpec:
    cell_id: str  # as in PLAN §6, e.g. "Σ-n-r"
    history: str  # "full" | "window" | "summary"
    notes: bool
    replay: bool
    role: str = ""
    optional: bool = False
    notes_extra: str = ""  # R10: sentences sent after the notes instruction
    truncation: str = "slide"  # R12: how a window cell drops turns (TRUNCATIONS)

    def __post_init__(self) -> None:
        if self.history not in HISTORY_POLICIES:
            raise ValueError(f"bad history policy {self.history!r}")
        if self.notes_extra and not self.notes:
            raise ValueError(f"cell {self.cell_id}: notes_extra needs the notes instruction")
        if self.truncation not in TRUNCATIONS:
            raise ValueError(f"cell {self.cell_id}: bad truncation {self.truncation!r}")
        if self.truncation != "slide" and self.history != "window":
            raise ValueError(f"cell {self.cell_id}: block truncation needs a window cell")

    @property
    def notes_instruction(self) -> str | None:
        """The notes text this cell appends to the system prompt (after the config's
        separator), or None: the notes instruction, then `notes_extra` after one space."""
        if not self.notes:
            return None
        return NOTES_INSTRUCTION + (" " + self.notes_extra if self.notes_extra else "")

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

# R10 (PREREG §17.10): W-n-0 with the provenance sentence (W-np-0), and with the provenance
# and disclosure sentences (W-npd-0). Not in PLAN §6's table.
NOTES_VARIANT_CELLS: dict[str, CellSpec] = {c.cell_id: c for c in (
    CellSpec("W-np-0", "window", notes=True, replay=False, role="R10: provenance",
             notes_extra=PROVENANCE_SENTENCE),
    CellSpec("W-npd-0", "window", notes=True, replay=False, role="R10: provenance + disclosure",
             notes_extra=PROVENANCE_SENTENCE + " " + DISCLOSURE_SENTENCE),
)}

# R12 (PREREG §17.12): W-n-0 with the disclosure sentence alone (W-nd-0) and with the neutral
# sentence (W-nx-0), and W-0 with block truncation (W-b-0). Not in PLAN §6's table.
R12_CELLS: dict[str, CellSpec] = {c.cell_id: c for c in (
    CellSpec("W-nd-0", "window", notes=True, replay=False, role="R12: disclosure",
             notes_extra=DISCLOSURE_SENTENCE),
    CellSpec("W-nx-0", "window", notes=True, replay=False, role="R12: length-matched neutral",
             notes_extra=NEUTRAL_SENTENCE),
    CellSpec("W-b-0", "window", notes=False, replay=False, role="R12: block truncation",
             truncation="block"),
)}

# Replay-off cells: the only cells to run on a model that does not honour `all_turns`
# (PLAN §7: luna runs F-0, W-n-0, Σ-n-0, W-0 if its echo check fails).
REPLAY_OFF_CELLS = tuple(c for c in CELLS if not CELLS[c].replay)

# r/0 pairs that differ only in reasoning.context.
REPLAY_PAIRS = (("F-r", "F-0"), ("W-n-r", "W-n-0"), ("Σ-n-r", "Σ-n-0"))


def get_cell(cell_id: str) -> CellSpec:
    """Look up a cell by its PLAN id or its ASCII id ('sigma-n-r', also 'S-n-r'), or one of
    R10's `NOTES_VARIANT_CELLS` or R12's `R12_CELLS`."""
    known = {**CELLS, **NOTES_VARIANT_CELLS, **R12_CELLS}
    if cell_id in known:
        return known[cell_id]
    for c in known.values():
        if cell_id in (c.ascii_id, c.cell_id.replace("Σ", "S")):
            return c
    raise KeyError(f"unknown harness cell {cell_id!r}; known: {', '.join(known)}")
