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

The last section asserts the one request of H3's position-matched single-turn control
(harnesses/single_turn.py; PREREG §3 H3, §4.3) on real episodes at the small volume: its whole
body, and that it is F-0's request with the flattened prompt as its only input item.
"""

from __future__ import annotations

import pytest

from harnesses import registered, single_turn
from harnesses.cells import CELLS, NOTES_INSTRUCTION
from harnesses.config import (
    ARC_SUMMARY_BRIDGE_TEMPLATE,
    ARC_SUMMARY_REQUEST_PROMPT,
    ARC_SUMMARY_SYSTEM_PROMPT,
    HarnessConfig,
)
from harnesses.fake import FakeModel
from harnesses.items import item_text
from harnesses.runner import run_episode
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
from persistgym.controls import single_turn_control

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
STEP_MAX_OUTPUT_TOKENS = 32_000  # PREREG D13
# PREREG §6 (D13): every luna and sol request carries 32,000; §5 freezes the summary cap here
SUMMARY_MAX_OUTPUT_TOKENS = 32_000


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
        assert set(p) == set(FIXED_KEYS) | {"instructions", "input", "reasoning",
                                            "max_output_tokens"}
        if kind == "step":
            assert p["instructions"] == instructions
            assert p["max_output_tokens"] == STEP_MAX_OUTPUT_TOKENS
        else:
            assert p["instructions"] == ARC_SUMMARY_SYSTEM_PROMPT
            assert p["max_output_tokens"] == SUMMARY_MAX_OUTPUT_TOKENS
            assert p["input"][-1]["content"][0]["text"] == ARC_SUMMARY_REQUEST_PROMPT


# PREREG §4.6: sol runs the H2 core (F-r, F-0) and, if H2 shows signal, the W/Σ replay pairs
SOL_CELLS = ["F-r", "F-0", "W-n-r", "W-n-0", "Σ-n-r", "Σ-n-0"]


@pytest.mark.parametrize("cell_id", SOL_CELLS)
def test_sols_registered_config_sends_high_effort_on_every_request(cell_id):
    """PREREG §6 as amended by R2 (§17.2): sol's registered config sends `reasoning.effort:
    high` on every step and summary request of each cell sol runs, and the requests are
    otherwise those of the default config: the same turns, reasoning items, instructions
    and settings."""
    sol = HarnessConfig(model="gpt-6.1-sol",
                        reasoning_effort=registered.registered_effort("gpt-6.1-sol"))
    expected, instructions, context = EXPECTED[cell_id]
    _, model, _ = run_synthetic(CELLS[cell_id], cfg=sol)
    got = [("summary" if model.is_summary(p) else "step", label_payload(p)) for p in model.calls]
    assert got == expected
    kinds = {"step", "summary"} if CELLS[cell_id].history == "summary" else {"step"}
    assert {kind for kind, _ in got} == kinds
    for p in model.calls:
        assert p["model"] == "gpt-6.1-sol"
        assert p["reasoning"] == {"effort": "high", "mode": "standard", "context": context}
        assert p["instructions"] == (ARC_SUMMARY_SYSTEM_PROMPT if model.is_summary(p)
                                     else instructions)
    _, default, _ = run_synthetic(CELLS[cell_id])
    for ps, pd in zip(model.calls, default.calls, strict=True):
        assert {**ps, "model": pd["model"],
                "reasoning": {**ps["reasoning"], "effort": "medium"}} == pd


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
        "max_output_tokens": 32000,
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
                              "max_output_tokens": 32000}
    bridge = ARC_SUMMARY_BRIDGE_TEMPLATE.format(summary=summary_text(1))
    assert model.calls[5] == {**common, "instructions": SYSTEM + "\n" + NOTES_INSTRUCTION,
                              "input": [_user(bridge), _user(obs_text(4))],
                              "max_output_tokens": 32000}


# --- output caps (PREREG D13) -------------------------------------------------------------

def test_default_step_output_cap_is_the_registered_one():
    assert HarnessConfig().max_output_tokens == STEP_MAX_OUTPUT_TOKENS
    assert HarnessConfig().summary_max_output_tokens == SUMMARY_MAX_OUTPUT_TOKENS


@pytest.mark.parametrize("cell_id", list(CELLS))
def test_every_request_sends_its_output_cap_explicitly(cell_id):
    """D13: every request of every cell, step and summary, carries `max_output_tokens`
    32,000 by default; each configured cap reaches its own kind of request only."""
    for cfg, step_cap, summary_cap in (
            (HarnessConfig(), 32_000, 32_000),
            (HarnessConfig(max_output_tokens=4_000), 4_000, 32_000),
            (HarnessConfig(summary_max_output_tokens=2_000), 32_000, 2_000)):
        _, model, requests = run_synthetic(CELLS[cell_id], cfg=cfg)
        caps = {(r.kind, p["max_output_tokens"]) for r, p in zip(requests, model.calls,
                                                                  strict=True)}
        expected = {("step", step_cap)}
        if CELLS[cell_id].history == "summary":
            expected.add(("summary", summary_cap))
        assert caps == expected


@pytest.mark.parametrize("cell_id", list(CELLS))
def test_default_config_sends_exactly_32000_on_every_request(cell_id):
    """PREREG §6 (D13): luna and sol requests carry `max_output_tokens: 32000`, with no
    exception for summary calls."""
    _, model, _ = run_synthetic(CELLS[cell_id])
    assert model.calls and {p["max_output_tokens"] for p in model.calls} == {32_000}


def _stops_at_cap_while_reasoning(turn: int) -> FakeModel:
    """Fake whose step call `turn` stops at the output cap before any visible text."""
    return FakeModel(lambda p, i: "" if i == turn else reply_text(i),
                     summary_fn=lambda p, j: summary_text(j),
                     status_fn=lambda p, tag: "incomplete" if tag == f"t{turn}" else "completed")


def test_incomplete_step_response_is_replayed_as_returned():
    """D13: a step response that hit the cap while reasoning has a reasoning item and no
    message. Later requests send that turn as returned (its observation and reasoning item,
    no reply), and its empty reply counts 0 tokens toward W. At W = 1150, step 4 keeps every
    turn (200 + 250 + 200 + 250 + 250 = 1150), where 50-token replies would drop turn 0."""
    _, model, _ = run_synthetic(CELLS["F-r"], n_steps=5, fake=_stops_at_cap_while_reasoning(2))
    assert label_payload(model.calls[3]) == [*turns(0, 2), "U2", "R2", "U3"]
    assert model.calls[3]["max_output_tokens"] == 32_000
    _, model, _ = run_synthetic(CELLS["W-n-0"], n_steps=5, W=1150,
                                fake=_stops_at_cap_while_reasoning(2))
    assert label_payload(model.calls[4]) == [*turns(0, 2), "U2", "R2", *turns(3, 4), "U4"]
    _, model, _ = run_synthetic(CELLS["W-n-0"], n_steps=5, W=1150)
    assert label_payload(model.calls[4]) == step(1, 4)


@pytest.mark.parametrize("bad", [None, 0, -1, True, 32000.0, "32000"])
def test_output_caps_must_be_positive_ints(bad):
    """No config can drop the cap from the payload (None used to mean "omitted")."""
    with pytest.raises(ValueError, match="must be a positive int"):
        HarnessConfig(max_output_tokens=bad)
    with pytest.raises(ValueError, match="must be a positive int"):
        HarnessConfig(summary_max_output_tokens=bad)


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


def test_window_counts_system_prompt_when_configured():
    """With count_system, the 15-token episode system prompt also has to fit: at W = 965
    step 3 is kept whole (15 + 3 x 250 + 200 = 965), at W = 964 it drops turn 0."""
    assert tokens.count(SYSTEM) == 15
    for W, keep in ((965, 0), (964, 1)):
        _, m0, _ = run_synthetic(CELLS["W-0"], n_steps=4, W=W, count_system=True)
        assert label_payload(m0.calls[3]) == step(keep, 3)


def test_notes_sentence_never_counts_toward_W():
    """PREREG D5: W counts the episode's system prompt, not the notes sentence, so W-n-0
    and W-0 (and Σ-n-r and Σ-0-r) keep and compact the same turns; only `instructions`
    differs. At W = 965 the notes sentence would push W-n-0 one turn shorter if counted."""
    assert tokens.count(NOTES_SYSTEM) > tokens.count(SYSTEM)
    for notes, plain in (("W-n-0", "W-0"), ("Σ-n-r", "Σ-0-r")):
        sn, mn, _ = run_synthetic(CELLS[notes], n_steps=6, W=965, count_system=True)
        s0, m0, _ = run_synthetic(CELLS[plain], n_steps=6, W=965, count_system=True)
        assert sn.system_tokens == s0.system_tokens == 15
        assert [label_payload(p) for p in mn.calls] == [label_payload(p) for p in m0.calls]
        assert sn.compactions == s0.compactions


def test_session_state_after_summary():
    session, _, _ = run_synthetic(CELLS["Σ-n-r"])
    assert [c["compacted_turns"] for c in session.compactions] == [[0, 4], [4, 7]]
    assert session.bridge == ARC_SUMMARY_BRIDGE_TEMPLATE.format(summary=summary_text(2))
    assert session.start == 7 and session.bridge_no == 2


# --- H3's single-turn control (PREREG §3 H3, §4.3, D36; harnesses/single_turn.py) -----------

def _flattened(ep) -> str:
    """The single-turn prompt rebuilt by hand from the episode, as PREREG §3 H3 states it
    (persistgym/DESIGN.md §3, "Position-matched single-turn control"): observations 0..need
    in order, each before the need step followed by the oracle's routine action as a plain
    "Agent: <expected action>" line, one newline between pieces; no preamble, no marks, and
    the need observation (ending with the need question) last."""
    text = ep.steps[0].observation
    for i in range(1, ep.need_step + 1):
        text += f"\nAgent: {ep.steps[i - 1].expected_action}\n{ep.steps[i].observation}"
    return text


def test_single_turn_full_request_literal(small_eps):
    """The complete request body of one single-turn prompt (observed-nonrec-far, main
    template 0): F-0's settings, the episode's system prompt unchanged, and the flattened
    prompt as the only input item. No reasoning item and no earlier output is sent."""
    ep = next(e for e in small_eps if e.cell.id == "observed-nonrec-far")
    control = single_turn_control(ep)
    req = single_turn.build_request(control, HarnessConfig(
        reasoning_effort=registered.registered_effort("gpt-6-luna")))
    assert req.kind == "step" and req.trace == ["U0"]
    assert req.payload == {
        "model": "gpt-6-luna",
        "instructions": ep.system_prompt,
        "input": [_user(_flattened(ep))],
        "reasoning": {"effort": "medium", "mode": "standard", "context": "current_turn"},
        "store": False,
        "include": ["reasoning.encrypted_content"],
        "service_tier": "flex",
        "truncation": "disabled",
        "max_output_tokens": 32000,
    }
    # literally (PREREG §3 H3): o_1, then its routine action as a plain "Agent: ..." line,
    # then o_2, ...; the message ends with the need-step question
    prompt = item_text(req.payload["input"][0])
    assert prompt.startswith("=== console update ")
    assert prompt.startswith(ep.steps[0].observation + "\nAgent: route(billing)\n"
                             + ep.steps[1].observation + "\nAgent: route(consent)\n")
    assert ep.steps[0].observation.endswith("Route it to the team named by its tag: reply "
                                            "route(<tag>).")
    assert prompt.endswith("\nAgent: " + ep.steps[ep.need_step - 1].expected_action + "\n"
                           + ep.need.observation)
    assert prompt.endswith("Sample LINDEN needs its freezer slot now. Options:\nA) 310\nB) 308"
                           "\nC) 306\nD) 303\nE) 304\nF) 311\nG) 307\nH) 309\nI) 302\nJ) 305\n"
                           "Reply store(<letter>) with the letter of the correct option.")


def test_single_turn_request_is_f0s_with_the_flattened_prompt(small_eps):
    """On every non-recoverable base episode (3 templates x 4 task cells): the single-turn
    request equals F-0's first request as the harness sends it, every key but `input`, whose
    one user message holds exactly the observations F-0 sends at the need step, in the same
    order, with the oracle's routine actions between them."""
    eps = [e for e in small_eps if not e.cell.recoverable]
    assert len(eps) == 12 and {e.cell.id for e in eps} == set(single_turn.NONREC_TASK_CELLS)
    for ep in eps:
        fake = FakeModel()
        run_episode(ep, CELLS["F-0"], HarnessConfig(), fake)
        first, at_need = fake.calls[0], fake.calls[ep.need_step]
        payload = single_turn.build_request(single_turn_control(ep), HarnessConfig()).payload
        assert payload == {**first, "input": [_user(_flattened(ep))]}
        assert [item_text(i) for i in at_need["input"] if i.get("role") == "user"] == (
            ep.observations[:ep.need_step + 1])
        assert at_need["instructions"] == payload["instructions"] == ep.system_prompt
        assert NOTES_INSTRUCTION not in payload["instructions"]


def test_single_turn_exists_for_nonrecoverable_cells_only(small_eps):
    """D36: a single prompt cannot serve a lookup, so there is no control, and no request,
    for a recoverable task cell."""
    rec = next(e for e in small_eps if e.cell.recoverable)
    with pytest.raises(ValueError, match="non-recoverable"):
        single_turn_control(rec)
    with pytest.raises(ValueError, match="non-recoverable"):
        single_turn.task_cells([rec.cell.id])
