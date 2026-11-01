"""Payload snapshot tests of R10's two cells (harnesses/cells.py `NOTES_VARIANT_CELLS`; PREREG
§17.10, amendment R10), on the Messages wire that Haiku runs on, hand-derived as in
test_messages_wire.py.

* The cells: W-np-0 is W-n-0 with the provenance sentence after the notes instruction, and
  W-npd-0 with the provenance and the disclosure sentences. Their text is asserted here
  literally, so a change to either sentence fails this file. They stay out of PLAN §6's
  table (`CELLS`, `REPLAY_OFF_CELLS`, `REPLAY_PAIRS`), and `get_cell` finds them.
* The bodies: every request of the synthetic 9-step episode, whole. They keep W-n-0's turns
  (the notes text never counts toward W, D5) and differ from W-n-0's bodies in `system` only,
  which is the episode's system prompt, "\\n", and the cell's notes text.
* On real episodes, their messages equal persistgym's reference drop-oldest payload.
"""

from __future__ import annotations

import pytest

from harnesses.cells import (
    CELLS,
    DISCLOSURE_SENTENCE,
    NOTES_INSTRUCTION,
    NOTES_VARIANT_CELLS,
    PROVENANCE_SENTENCE,
    REPLAY_OFF_CELLS,
    REPLAY_PAIRS,
    CellSpec,
    get_cell,
)
from harnesses.fake import FakeModel
from harnesses.items import item_text
from harnesses.runner import run_episode
from harnesses.tests.conftest import SYSTEM, run_synthetic
from harnesses.tests.test_messages_wire import (
    CFG,
    WINDOW_KEEP,
    _assert_wire_invariants,
    _body,
    _turns,
    labels,
    no_reasoning_turns,
)
from harnesses.wire import MESSAGES
from persistgym.survival import reference_window_payload

ARC_SENTENCE = ("Include any context you want to carry forward in your reply, along with the "
                "action you want to take.")
PROVENANCE = ("For each fact you carry forward, also note where it came from: the message you "
              "read it in, or the facts and steps you worked it out from.")
DISCLOSURE = ("Older messages may be dropped from this conversation as it grows, so your notes "
              "may become the only record of what they said.")
NOTES_TEXT = {
    "W-n-0": ARC_SENTENCE,
    "W-np-0": ARC_SENTENCE + " " + PROVENANCE,
    "W-npd-0": ARC_SENTENCE + " " + PROVENANCE + " " + DISCLOSURE,
}
R10_CELLS = ("W-np-0", "W-npd-0")


# --- the cells -----------------------------------------------------------------------------

def test_the_sentences_are_r10s_literally():
    assert NOTES_INSTRUCTION == ARC_SENTENCE
    assert PROVENANCE_SENTENCE == PROVENANCE and DISCLOSURE_SENTENCE == DISCLOSURE
    for cid, text in NOTES_TEXT.items():
        assert get_cell(cid).notes_instruction == text, cid


def test_the_cells_are_w_n_0_but_for_their_notes_text():
    base = CELLS["W-n-0"]
    for cid in R10_CELLS:
        c = get_cell(cid)
        assert c is NOTES_VARIANT_CELLS[cid]
        assert (c.history, c.notes, c.replay, c.reasoning_context, c.optional) == (
            base.history, base.notes, base.replay, base.reasoning_context, base.optional)
        assert c.ascii_id == cid and c.notes_extra
    assert list(NOTES_VARIANT_CELLS) == list(R10_CELLS)


def test_they_stay_out_of_plans_table():
    for cid in R10_CELLS:
        assert cid not in CELLS and cid not in REPLAY_OFF_CELLS
        assert all(cid not in pair for pair in REPLAY_PAIRS)
    assert REPLAY_OFF_CELLS == ("F-0", "W-n-0", "Σ-n-0", "W-0")


def test_the_cells_without_notes_have_no_notes_text():
    assert CELLS["W-0"].notes_instruction is None and CELLS["F-0"].notes_instruction is None
    with pytest.raises(ValueError, match="notes_extra needs the notes instruction"):
        CellSpec("W-x-0", "window", notes=False, replay=False, notes_extra="x")


def test_an_unknown_cell_still_raises_and_names_r10s():
    with pytest.raises(KeyError, match="W-npd-0"):
        get_cell("W-nq-0")


# --- the bodies, hand-derived --------------------------------------------------------------

@pytest.mark.parametrize("cell_id", R10_CELLS)
def test_cell_payloads_exactly(cell_id):
    """Every request of the 9-step episode, whole: W-n-0's turns (visible text only), the
    system prompt plus "\\n" and the cell's notes text, the fixed fields."""
    system = SYSTEM + "\n" + NOTES_TEXT[cell_id]
    _, model, requests = run_synthetic(get_cell(cell_id), cfg=CFG)
    assert [labels(p) for p in model.calls] == [no_reasoning_turns(k, m)
                                                for m, k in enumerate(WINDOW_KEEP)]
    assert [r.trace for r in requests] == [labels(p) for p in model.calls]
    for m, (k, p) in enumerate(zip(WINDOW_KEEP, model.calls, strict=True)):
        assert p == _body(system, _turns(k, m))
        _assert_wire_invariants(p)


@pytest.mark.parametrize("cell_id", R10_CELLS)
def test_they_differ_from_w_n_0_in_system_only(cell_id):
    """The notes text never counts toward W (D5): the same turns as W-n-0 and W-0, with the
    system prompt counted or not, and the same bodies but for `system`."""
    for W, count_system in ((1000, False), (965, True), (949, False)):
        _, mv, rv = run_synthetic(get_cell(cell_id), cfg=CFG, W=W, count_system=count_system)
        _, mn, rn = run_synthetic(CELLS["W-n-0"], cfg=CFG, W=W, count_system=count_system)
        assert len(mv.calls) == len(mn.calls) == 9
        assert [r.info for r in rv] == [r.info for r in rn]
        for pv, pn in zip(mv.calls, mn.calls, strict=True):
            assert pv["system"] == SYSTEM + "\n" + NOTES_TEXT[cell_id]
            assert pn["system"] == SYSTEM + "\n" + NOTES_TEXT["W-n-0"]
            assert {**pv, "system": pn["system"]} == pn


def test_the_instructions_never_reach_the_messages():
    for cid in R10_CELLS:
        _, model, _ = run_synthetic(get_cell(cid), cfg=CFG)
        assert all(PROVENANCE not in str(p["messages"]) for p in model.calls)
        assert all(DISCLOSURE not in str(p["messages"]) for p in model.calls)


def test_window_payload_matches_generator_reference(small_eps):
    """On real episodes, the cells' messages equal persistgym's reference drop-oldest payload
    for the same replies, at every step, and the system prompt is the episode's plus the
    cell's notes text."""
    for ep in small_eps:
        if ep.cell.recoverable:
            continue
        for cid in R10_CELLS:
            events = []
            run_episode(ep, get_cell(cid), CFG, FakeModel(), recorder=events.append)
            replies = [MESSAGES.text(e["response"]) for e in events]
            for m, e in enumerate(events):
                ref = reference_window_payload(ep, replies[:m])
                assert [(x["role"], item_text(x)) for x in e["payload"]["messages"]] == [
                    (x["role"], x["content"]) for x in ref[1:]]
                assert e["payload"]["system"] == ref[0]["content"] + "\n" + NOTES_TEXT[cid]
                _assert_wire_invariants(e["payload"])
