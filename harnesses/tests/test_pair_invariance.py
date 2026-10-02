"""Cells that should differ in one component differ in exactly that field of the payload.

* r vs 0 arms (F-r/F-0, W-n-r/W-n-0, Σ-n-r/Σ-n-0): identical payloads at every request
  (summary requests included) except `reasoning.context`; encrypted reasoning items are sent
  in both arms.
* notes on vs off (W-n-0 vs W-0; Σ-n-r vs Σ-0-r): identical except the instructions of step
  requests; summary requests are identical (the summary call has its own instructions).
"""

from __future__ import annotations

import copy

import pytest

from harnesses.cells import CELLS, NOTES_INSTRUCTION, REPLAY_OFF_CELLS, REPLAY_PAIRS
from harnesses.config import HarnessConfig
from harnesses.fake import FakeModel
from harnesses.items import n_reasoning_items
from harnesses.tests.conftest import SYSTEM, reply_text, run_synthetic, summary_text

CONFIGS = [HarnessConfig(), HarnessConfig(summary_keep_recent_tokens=500),
           HarnessConfig(reasoning_effort="high", service_tier="default",
                         max_output_tokens=4000, reasoning_summary="auto")]


def _without(payload: dict, *path: str) -> dict:
    p = copy.deepcopy(payload)
    d = p
    for k in path[:-1]:
        d = d[k]
    d.pop(path[-1])
    return p


@pytest.mark.parametrize("cfg", CONFIGS)
@pytest.mark.parametrize("r_id, o_id", REPLAY_PAIRS)
def test_replay_pairs_differ_only_in_reasoning_context(r_id, o_id, cfg):
    _, mr, _ = run_synthetic(CELLS[r_id], cfg=cfg)
    _, mo, _ = run_synthetic(CELLS[o_id], cfg=cfg)
    assert len(mr.calls) == len(mo.calls) > 0
    for pr, po in zip(mr.calls, mo.calls, strict=True):
        assert pr["reasoning"]["context"] == "all_turns"
        assert po["reasoning"]["context"] == "current_turn"
        assert _without(pr, "reasoning", "context") == _without(po, "reasoning", "context")
    # encrypted reasoning items are sent in the 0 arm too: one per earlier turn sent verbatim
    for p in mo.calls:
        n_replies = sum(1 for i in p["input"] if i.get("role") == "assistant")
        assert n_reasoning_items(p["input"]) == n_replies
    assert sum(n_reasoning_items(p["input"]) for p in mo.calls) > 0


@pytest.mark.parametrize("r_id, o_id", REPLAY_PAIRS)
def test_replay_pairs_stay_identical_after_incomplete_responses(r_id, o_id):
    """D13: step calls 2 (stopped while reasoning: no message) and 5 (stopped with partial
    text) hit the output cap. Both arms replay those turns the same way, so the payloads
    still differ only in `reasoning.context`."""
    def fake():
        return FakeModel(lambda p, i: "" if i == 2 else reply_text(i),
                         summary_fn=lambda p, j: summary_text(j),
                         status_fn=lambda p, tag: ("incomplete" if tag in ("t2", "t5")
                                                   else "completed"))
    _, mr, _ = run_synthetic(CELLS[r_id], fake=fake())
    _, mo, _ = run_synthetic(CELLS[o_id], fake=fake())
    assert len(mr.calls) == len(mo.calls) > 5
    for pr, po in zip(mr.calls, mo.calls, strict=True):
        assert _without(pr, "reasoning", "context") == _without(po, "reasoning", "context")
    # the reasoning-only turn 2 is sent without a reply wherever it is still verbatim
    sent = [p for p in mo.calls if any(i.get("id") == "rs_t2" for i in p["input"])]
    assert sent and all(not any(i.get("id") == "msg_t2" for i in p["input"]) for p in sent)


@pytest.mark.parametrize("cfg", CONFIGS[:2])
@pytest.mark.parametrize("notes_id, plain_id", [("W-n-0", "W-0"), ("Σ-n-r", "Σ-0-r")])
def test_notes_pairs_differ_only_in_step_instructions(notes_id, plain_id, cfg):
    _, mn, rn = run_synthetic(CELLS[notes_id], cfg=cfg)
    _, mp, _ = run_synthetic(CELLS[plain_id], cfg=cfg)
    assert len(mn.calls) == len(mp.calls)
    for req, pn, pp in zip(rn, mn.calls, mp.calls, strict=True):
        if req.kind == "step":
            assert pn["instructions"] == SYSTEM + "\n" + NOTES_INSTRUCTION
            assert pp["instructions"] == SYSTEM
            assert _without(pn, "instructions") == _without(pp, "instructions")
        else:
            assert pn == pp
            assert NOTES_INSTRUCTION not in pn["instructions"]


def test_notes_sentence_appears_only_in_notes_cells():
    for cid, cell in CELLS.items():
        _, m, reqs = run_synthetic(cell, n_steps=5)
        steps = [p for r, p in zip(reqs, m.calls, strict=True) if r.kind == "step"]
        assert all((NOTES_INSTRUCTION in p["instructions"]) == cell.notes for p in steps), cid
        # never inside the conversation items
        assert all(NOTES_INSTRUCTION not in str(p["input"]) for p in m.calls), cid


def test_replay_off_cells_are_the_luna_fallback_set():
    assert set(REPLAY_OFF_CELLS) == {"F-0", "W-n-0", "Σ-n-0", "W-0"}


def test_reasoning_settings_are_always_explicit():
    cfg = HarnessConfig(model="gpt-6.1-sol", reasoning_effort="low", reasoning_mode="pro",
                        service_tier="default")
    for cell in CELLS.values():
        _, m, _ = run_synthetic(cell, n_steps=5, cfg=cfg)
        for p in m.calls:
            assert p["model"] == "gpt-6.1-sol" and p["service_tier"] == "default"
            assert p["reasoning"] == {"effort": "low", "mode": "pro",
                                      "context": cell.reasoning_context}
