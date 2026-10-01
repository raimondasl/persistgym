"""DESIGN.md stays in sync with the code; the summary-timing diagnostic behaves as documented."""

from __future__ import annotations

from pathlib import Path

from harnesses import diagnostics
from harnesses.cells import CELLS, NOTES_INSTRUCTION
from harnesses.config import RESEARCHER_DECISIONS

DESIGN = (Path(__file__).resolve().parent.parent / "DESIGN.md").read_text(encoding="utf-8")


def test_every_researcher_decision_is_documented():
    for key in RESEARCHER_DECISIONS:
        assert f"[RESEARCHER DECISION] `{key}`" in DESIGN, key


def test_every_cell_and_the_notes_sentence_are_documented():
    for cid in CELLS:
        assert f"| {cid} " in DESIGN, cid
    assert NOTES_INSTRUCTION in DESIGN


def test_summary_timing_on_two_templates():
    """The first compaction comes at turn 9 at the default volume (the system prompt counts
    toward W, PREREG D5), and keeping the near span verbatim keeps every near reveal
    (DESIGN.md §4.3; the 20-template table comes from
    `python -m harnesses summary-timing --n 20`)."""
    out = diagnostics.summary_timing(2)
    assert out["n_episodes"] == 4 and out["reply_tokens"] == 1000
    ark, keep = out["per_keep_recent"][0], out["per_keep_recent"][16_650]
    assert all(t.startswith("9,") for t in ark["compaction_turns"])
    assert keep["need_S0"] == 0
    # keeping the near span verbatim: more, smaller summary calls and larger step requests
    assert keep["summary_calls_per_episode"] > ark["summary_calls_per_episode"] == 2
    assert (keep["summary_call_input_tokens_min_max"][1]
            < ark["summary_call_input_tokens_min_max"][0])
    assert keep["step_input_tokens_per_episode"] > ark["step_input_tokens_per_episode"]
