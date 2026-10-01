"""Payload snapshot tests (PLAN §6: "the single most important correctness check").

For every harness cell, over a scripted 9-step episode with a fake model (canned replies and
fake encrypted reasoning items), these tests assert exactly which turns, reasoning items and
instructions are sent at every request, including at the window boundary and at the summary
trigger.

Synthetic episode: observations of exactly 200 tokens, replies of exactly 50 tokens (one turn
= 250 visible tokens), W = 1000, summary text of 60 tokens (bridge = 87 tokens). So:
* window: observation m keeps turns max(0, m-3)..m-1 (200 + 3 x 250 = 950 <= 1000);
* summary: the visible context first exceeds W at step 4 (200 + 4 x 250 = 1200).
Labels: U<t> observation of turn t, R<t> its reasoning item, A<t> its reply, B<k> the bridge
holding summary k, Q the summary request.
"""

from __future__ import annotations

import pytest

from harnesses.cells import CELLS, NOTES_INSTRUCTION
from harnesses.config import (
    ARC_SUMMARY_BRIDGE_TEMPLATE,
    ARC_SUMMARY_REQUEST_PROMPT,
    ARC_SUMMARY_SYSTEM_PROMPT,
    HarnessConfig,
)
from harnesses.tests.conftest import (
    SYSTEM,
    label_payload,
    obs_text,
    reply_text,
    run_synthetic,
    step,
    summary_text,
    turns,
)
from persistgym import tokens

NOTES_SYSTEM = SYSTEM + "\n" + NOTES_INSTRUCTION

# Hand-derived expectations (see module docstring). One entry per request, in send order.
FULL = [("step", step(0, m)) for m in range(9)]
WINDOW = [("step", step(k, m)) for m, k in enumerate([0, 0, 0, 0, 1, 2, 3, 4, 5])]
SUMMARY_ALL = [
    ("step", step(0, 0)),
    ("step", step(0, 1)),
    ("step", step(0, 2)),
    ("step", step(0, 3)),
    ("summary", turns(0, 4) + ["Q"]),
    ("step", ["B1", "U4"]),
    ("step", ["B1", *turns(4, 5), "U5"]),
    ("step", ["B1", *turns(4, 6), "U6"]),
    ("summary", ["B1", *turns(4, 7), "Q"]),
    ("step", ["B2", "U7"]),
    ("step", ["B2", *turns(7, 8), "U8"]),
]
# summary_keep_recent_tokens = 500: keep the newest turns that fit with the observation.
SUMMARY_KEEP_500 = [
    ("step", step(0, 0)),
    ("step", step(0, 1)),
    ("step", step(0, 2)),
    ("step", step(0, 3)),
    ("summary", turns(0, 3) + ["Q"]),
    ("step", ["B1", *turns(3, 4), "U4"]),
    ("step", ["B1", *turns(3, 5), "U5"]),
    ("summary", ["B1", *turns(3, 5), "Q"]),
    ("step", ["B2", *turns(5, 6), "U6"]),
    ("step", ["B2", *turns(5, 7), "U7"]),
    ("summary", ["B2", *turns(5, 7), "Q"]),
    ("step", ["B3", *turns(7, 8), "U8"]),
]

EXPECTED = {
    "F-r": (FULL, SYSTEM, "all_turns"),
    "F-0": (FULL, SYSTEM, "current_turn"),
    "W-n-r": (WINDOW, NOTES_SYSTEM, "all_turns"),
    "W-n-0": (WINDOW, NOTES_SYSTEM, "current_turn"),
    "Σ-n-r": (SUMMARY_ALL, NOTES_SYSTEM, "all_turns"),
    "Σ-n-0": (SUMMARY_ALL, NOTES_SYSTEM, "current_turn"),
    "W-0": (WINDOW, SYSTEM, "current_turn"),
    "Σ-0-r": (SUMMARY_ALL, SYSTEM, "all_turns"),
}

FIXED_KEYS = {"store": False, "include": ["reasoning.encrypted_content"],
              "service_tier": "flex", "truncation": "disabled", "model": "gpt-6-luna"}


def test_every_cell_has_a_snapshot():
    assert set(EXPECTED) == set(CELLS)


def test_synthetic_sizes_are_as_designed():
    assert tokens.count(obs_text(3)) == 200 and tokens.count(reply_text(3)) == 50
    assert tokens.count(ARC_SUMMARY_BRIDGE_TEMPLATE.format(summary=summary_text(1))) == 87


@pytest.mark.parametrize("cell_id", list(EXPECTED))
def test_cell_payloads_exactly(cell_id):
    expected, instructions, context = EXPECTED[cell_id]
    _, model, requests = run_synthetic(CELLS[cell_id])
    got = [("summary" if model.is_summary(p) else "step", label_payload(p)) for p in model.calls]
    assert got == expected
    # the session's own trace agrees with the content-derived labels
    assert [r.trace for r in requests] == [labels for _, labels in expected]
    for (kind, _), p in zip(expected, model.calls, strict=True):
        assert {k: p[k] for k in FIXED_KEYS} == FIXED_KEYS
        assert p["reasoning"] == {"effort": "medium", "mode": "standard", "context": context}
        if kind == "step":
            assert p["instructions"] == instructions
            assert set(p) == set(FIXED_KEYS) | {"instructions", "input", "reasoning"}
        else:
            assert p["instructions"] == ARC_SUMMARY_SYSTEM_PROMPT
            assert p["max_output_tokens"] == 8192
            assert p["input"][-1]["content"][0]["text"] == ARC_SUMMARY_REQUEST_PROMPT
            assert set(p) == set(FIXED_KEYS) | {"instructions", "input", "reasoning",
                                                "max_output_tokens"}


@pytest.mark.parametrize("cell_id", ["Σ-n-r", "Σ-n-0", "Σ-0-r"])
def test_summary_keep_recent_payloads_exactly(cell_id):
    cfg = HarnessConfig(summary_keep_recent_tokens=500)
    _, model, _ = run_synthetic(CELLS[cell_id], cfg=cfg)
    got = [("summary" if model.is_summary(p) else "step", label_payload(p)) for p in model.calls]
    assert got == SUMMARY_KEEP_500


def _user(text):
    return {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}


def _reasoning(t):
    return {"type": "reasoning", "id": f"rs_t{t}", "summary": [],
            "encrypted_content": f"gAAAAB-fake-encrypted-t{t}"}


def _assistant(t):
    return {"type": "message", "id": f"msg_t{t}", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": reply_text(t), "annotations": []}]}


def test_full_payload_literal_window_cell_at_boundary():
    """W-n-r at step 4, the first step past the window boundary: the complete request body."""
    _, model, _ = run_synthetic(CELLS["W-n-r"])
    assert model.calls[4] == {
        "model": "gpt-6-luna",
        "instructions": SYSTEM + "\n" + NOTES_INSTRUCTION,
        "input": [_user(obs_text(1)), _reasoning(1), _assistant(1),
                  _user(obs_text(2)), _reasoning(2), _assistant(2),
                  _user(obs_text(3)), _reasoning(3), _assistant(3),
                  _user(obs_text(4))],
        "reasoning": {"effort": "medium", "mode": "standard", "context": "all_turns"},
        "store": False,
        "include": ["reasoning.encrypted_content"],
        "service_tier": "flex",
        "truncation": "disabled",
    }


def test_full_payload_literal_summary_trigger():
    """Σ-n-0 at step 4: the summary request, then the step request with the bridge."""
    _, model, _ = run_synthetic(CELLS["Σ-n-0"])
    common = {"model": "gpt-6-luna", "store": False,
              "include": ["reasoning.encrypted_content"], "service_tier": "flex",
              "truncation": "disabled",
              "reasoning": {"effort": "medium", "mode": "standard", "context": "current_turn"}}
    history = []
    for t in range(4):
        history += [_user(obs_text(t)), _reasoning(t), _assistant(t)]
    assert model.calls[4] == {**common, "instructions": ARC_SUMMARY_SYSTEM_PROMPT,
                              "input": [*history, _user(ARC_SUMMARY_REQUEST_PROMPT)],
                              "max_output_tokens": 8192}
    bridge = ARC_SUMMARY_BRIDGE_TEMPLATE.format(summary=summary_text(1))
    assert model.calls[5] == {**common, "instructions": SYSTEM + "\n" + NOTES_INSTRUCTION,
                              "input": [_user(bridge), _user(obs_text(4))]}


# --- window boundary and summary trigger at exact equality -----------------------------

@pytest.mark.parametrize("W, keep_at_3, keep_at_4", [(950, 0, 1), (949, 1, 2)])
def test_window_boundary_is_inclusive(W, keep_at_3, keep_at_4):
    """Observation + 3 turns = 200 + 3 x 250 = 950 visible tokens: kept whole at W = 950,
    one turn fewer at W = 949."""
    _, model, _ = run_synthetic(CELLS["W-0"], n_steps=5, W=W)
    assert label_payload(model.calls[3]) == step(keep_at_3, 3)
    assert label_payload(model.calls[4]) == step(keep_at_4, 4)


@pytest.mark.parametrize("W, first_summary_call", [(950, 4), (949, 3)])
def test_summary_trigger_is_strict(W, first_summary_call):
    _, model, _ = run_synthetic(CELLS["Σ-n-r"], n_steps=5, W=W)
    kinds = ["summary" if model.is_summary(p) else "step" for p in model.calls]
    assert kinds.index("summary") == first_summary_call
    assert label_payload(model.calls[first_summary_call]) == turns(0, first_summary_call) + ["Q"]


def test_window_counts_reply_tokens():
    """A 300-token reply to turn 1 makes turn 1 cost 500, so step 3 already drops turn 0
    (200 + 250 + 500 + 250 = 1200 > 1000) and step 4 drops turns 0-1."""
    _, model, _ = run_synthetic(CELLS["W-n-0"], n_steps=6, reply_tokens={1: 300})
    assert [label_payload(p) for p in model.calls] == [
        step(0, 0), step(0, 1), step(0, 2), step(1, 3), step(2, 4), step(2, 5)]


def test_window_counts_instructions_when_configured():
    """With count_system, the 15-token instructions (+ notes sentence in W-n cells) also
    have to fit: at W = 965, W-0 (15 tokens) keeps step 3 whole, W-n-0 does not."""
    n_notes = tokens.count(NOTES_SYSTEM)
    assert tokens.count(SYSTEM) == 15 and n_notes > 15
    _, m0, _ = run_synthetic(CELLS["W-0"], n_steps=4, W=965, count_system=True)
    _, mn, _ = run_synthetic(CELLS["W-n-0"], n_steps=4, W=965, count_system=True)
    assert label_payload(m0.calls[3]) == step(0, 3)
    assert label_payload(mn.calls[3]) == step(1, 3)


def test_session_state_after_summary():
    session, _, _ = run_synthetic(CELLS["Σ-n-r"])
    assert [c["compacted_turns"] for c in session.compactions] == [[0, 4], [4, 7]]
    assert session.bridge == ARC_SUMMARY_BRIDGE_TEMPLATE.format(summary=summary_text(2))
    assert session.start == 7 and session.bridge_no == 2
