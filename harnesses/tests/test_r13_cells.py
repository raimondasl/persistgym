"""Payload snapshot tests of R13's two cells on the Messages wire (PREREG §17.13, amendment
R13), hand-derived as in test_messages_wire.py and test_payload_snapshots.py.

* Σ-n-0 on claude-haiku-5-5 (experiment 4): luna's summary cell, now on the Messages wire.
  On the synthetic episode (200-token observations, 50-token replies, W = 1000, 60-token
  summaries, so an 87-token bridge) it summarizes at steps 4 and 7, as on luna
  (test_payload_snapshots.SUMMARY_ALL). The summary request sends ARC's summary system prompt,
  the turns to compact and ARC's summary request prompt. Each step after a compaction sends
  the bridge, then the kept turns: two user messages in a row, which the API combines into
  one turn and the request-side check admits for exactly one leading harness message.
* W-nk-0 (experiment 5): W-n-0 plus the pinned block. When the window drops a turn, its
  reply moves into one user message before the kept turns. The block keeps the newest
  dropped replies within 600 reply tokens, always the newest one, and skips turns with no kept
  reply. It is not counted toward W, so W-nk-0 keeps W-n-0's turns, sends W-n-0's system
  prompt, and differs from W-n-0 only by the block.
* The block is left out of S at the need step and string-matched apart
  (`EpisodeRun.need_pinned_carried`): on real episodes whose replies copy every evidence
  sentence, W-nk-0's S equals W-n-0's.
"""

from __future__ import annotations

import re

import pytest

from harnesses.cells import (
    CELLS,
    NOTES_INSTRUCTION,
    PINNED_REPLIES_TEMPLATE,
    PINNED_REPLY_SEPARATOR,
    R13_CELLS,
    R13_PINNED_TOKENS,
    REPLAY_OFF_CELLS,
    REPLAY_PAIRS,
    CellSpec,
    get_cell,
)
from harnesses.config import (
    ARC_SUMMARY_BRIDGE_TEMPLATE,
    ARC_SUMMARY_REQUEST_PROMPT,
    ARC_SUMMARY_SYSTEM_PROMPT,
)
from harnesses.fake import FakeModel
from harnesses.runner import run_episode
from harnesses.tests.conftest import SYSTEM, obs_text, reply_text, run_synthetic, summary_text
from harnesses.tests.test_messages_wire import (
    CFG,
    NOTES_SYSTEM,
    WINDOW_KEEP,
    _assistant,
    _body,
    _turns,
    _user,
)
from harnesses.wire import (
    EMPTY_REPLY_PLACEHOLDER,
    LEADING_HARNESS_PREFIXES,
    MESSAGES,
    RequestCheckFailed,
)
from persistgym import tokens
from persistgym.survival import window_keep_start

PINNED_KEYS = {"pinned_index", "pinned_turns", "pinned_reply_tokens", "pinned_tokens",
               "pinned_over_cap", "pinned_left_out"}
BRIDGE_PREFIX = ARC_SUMMARY_BRIDGE_TEMPLATE.split("{summary}")[0]
PINNED_PREFIX = PINNED_REPLIES_TEMPLATE.split("{replies}")[0]
_OBS = re.compile(r"^OBS\[(\d+)\]")
_REP = re.compile(r"^REPLY\[(\d+)\]")
_SUM = re.compile(r"SUMMARY s(\d+)")

# Hand-derived (module docstring): one entry per request, in send order.
SIGMA = [
    ("step", ["U0"]),
    ("step", ["U0", "A0", "U1"]),
    ("step", ["U0", "A0", "U1", "A1", "U2"]),
    ("step", ["U0", "A0", "U1", "A1", "U2", "A2", "U3"]),
    ("summary", ["U0", "A0", "U1", "A1", "U2", "A2", "U3", "A3", "Q"]),
    ("step", ["B1", "U4"]),
    ("step", ["B1", "U4", "A4", "U5"]),
    ("step", ["B1", "U4", "A4", "U5", "A5", "U6"]),
    ("summary", ["B1", "U4", "A4", "U5", "A5", "U6", "A6", "Q"]),
    ("step", ["B2", "U7"]),
    ("step", ["B2", "U7", "A7", "U8"]),
]


def mlabel(message: dict) -> str:
    """Content-derived label of one Messages message: U<t>, A<t>, E (the empty-reply
    placeholder), B<k> (the bridge of summary k), P (the pinned block) or Q (the summary
    request)."""
    assert set(message) == {"role", "content"}
    assert all(b["type"] == "text" and set(b) == {"type", "text"} for b in message["content"])
    text = "".join(b["text"] for b in message["content"])
    if message["role"] == "user":
        if text == ARC_SUMMARY_REQUEST_PROMPT:
            return "Q"
        if text.startswith(BRIDGE_PREFIX):
            return f"B{_SUM.search(text).group(1)}"
        if text.startswith(PINNED_PREFIX):
            return "P"
        m = _OBS.match(text)
        return f"U{m.group(1)}" if m else "BAD-user"
    if text == EMPTY_REPLY_PLACEHOLDER:
        return "E"
    m = _REP.match(text)
    return f"A{m.group(1)}" if m else "BAD-assistant"


def mlabels(payload: dict) -> list[str]:
    return [mlabel(m) for m in payload["messages"]]


def pinned_text(replies: list[str]) -> str:
    return PINNED_REPLIES_TEMPLATE.format(replies=PINNED_REPLY_SEPARATOR.join(replies))


def _check(p: dict) -> None:
    """The paid transport's request-side check, with the registered effort and cap."""
    MESSAGES.check_payload(p, effort="medium", max_tokens=32000)


# --- the cells -----------------------------------------------------------------------------

def test_the_pinned_cell_is_w_n_0_but_for_its_block():
    c, base = get_cell("W-nk-0"), CELLS["W-n-0"]
    assert c is R13_CELLS["W-nk-0"] and list(R13_CELLS) == ["W-nk-0"]
    assert c.pinned_tokens == R13_PINNED_TOKENS == 600
    assert (c.history, c.notes, c.replay, c.reasoning_context, c.optional, c.notes_extra,
            c.truncation) == (base.history, base.notes, base.replay, base.reasoning_context,
                              base.optional, base.notes_extra, base.truncation)
    assert c.notes_instruction == NOTES_INSTRUCTION
    assert all(x.pinned_tokens == 0 for x in CELLS.values())
    assert "W-nk-0" not in CELLS and "W-nk-0" not in REPLAY_OFF_CELLS
    assert all("W-nk-0" not in pair for pair in REPLAY_PAIRS)


def test_the_block_text_is_r13s_literally():
    assert PINNED_REPLIES_TEMPLATE == (
        "Earlier conversation history was dropped. Your replies from those turns follow, "
        "oldest first.\n\n{replies}")
    assert PINNED_REPLY_SEPARATOR == "\n\n---\n\n"
    assert LEADING_HARNESS_PREFIXES == (BRIDGE_PREFIX, PINNED_PREFIX)
    assert BRIDGE_PREFIX == ("Earlier conversation history was compacted. Use the following "
                             "summary as prior context. If it conflicts with newer input, "
                             "prefer the newer input.\n\n")


@pytest.mark.parametrize("kwargs, problem", [
    ({"history": "full", "notes": True, "replay": False}, "pinned block needs"),
    ({"history": "summary", "notes": True, "replay": False}, "pinned block needs"),
    ({"history": "window", "notes": False, "replay": False}, "pinned block needs"),
    ({"history": "window", "notes": True, "replay": True}, "pinned block needs"),
    ({"history": "window", "notes": True, "replay": False, "truncation": "block"},
     "pinned block needs"),
])
def test_a_pinned_block_needs_a_replay_off_sliding_window_notes_cell(kwargs, problem):
    with pytest.raises(ValueError, match=problem):
        CellSpec("X-k-0", pinned_tokens=600, **kwargs)


@pytest.mark.parametrize("bad", [-1, True, 1.5, "600"])
def test_a_bad_cap_raises(bad):
    with pytest.raises(ValueError, match="bad pinned_tokens"):
        CellSpec("X-k-0", "window", notes=True, replay=False, pinned_tokens=bad)


# --- Σ-n-0 on the Messages wire ------------------------------------------------------------

def test_sigma_payloads_exactly():
    assert tokens.count(ARC_SUMMARY_BRIDGE_TEMPLATE.format(summary=summary_text(1))) == 87
    session, model, requests = run_synthetic(get_cell("Σ-n-0"), cfg=CFG)
    got = [("summary" if model.is_summary(p) else "step", mlabels(p)) for p in model.calls]
    assert got == SIGMA
    assert [r.kind for r in requests] == [k for k, _ in SIGMA]
    bridges = {1: ARC_SUMMARY_BRIDGE_TEMPLATE.format(summary=summary_text(1)),
               2: ARC_SUMMARY_BRIDGE_TEMPLATE.format(summary=summary_text(2))}

    def msgs(labels: list[str]) -> list[dict]:
        out = []
        for lab in labels:
            if lab == "Q":
                out.append(_user(ARC_SUMMARY_REQUEST_PROMPT))
            elif lab[0] == "B":
                out.append(_user(bridges[int(lab[1:])]))
            elif lab[0] == "U":
                out.append(_user(obs_text(int(lab[1:]))))
            else:
                out.append(_assistant(reply_text(int(lab[1:]))))
        return out

    for (kind, labs), p in zip(SIGMA, model.calls, strict=True):
        system = ARC_SUMMARY_SYSTEM_PROMPT if kind == "summary" else NOTES_SYSTEM
        assert p == _body(system, msgs(labs))
        _check(p)
    assert [c["compacted_turns"] for c in session.compactions] == [[0, 4], [4, 7]]
    assert [r.info["bridge_index"] for r in requests if r.kind == "step"] == [
        None] * 4 + [0] * 5
    assert all(PINNED_KEYS.isdisjoint(r.info) for r in requests)


def test_sigma_summary_body_literal():
    """The first summary request, whole (ARC's summary system prompt replaces the task
    instructions, D13's 32,000 cap, adaptive thinking, medium effort, 5-minute caching)."""
    _, model, _ = run_synthetic(get_cell("Σ-n-0"), cfg=CFG)
    p = model.calls[4]
    assert p == {
        "model": "claude-haiku-5-5",
        "system": ("You create concise conversation summaries for reliable continuation. "
                   "Return only the requested summary."),
        "messages": [*_turns(0, 4)[:-1], _user(ARC_SUMMARY_REQUEST_PROMPT)],
        "max_tokens": 32000,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "medium"},
        "cache_control": {"type": "ephemeral"},
    }
    assert [m["role"] for m in p["messages"]] == ["user", "assistant"] * 4 + ["user"]


def test_sigma_step_after_a_compaction_starts_with_two_user_messages():
    _, model, _ = run_synthetic(get_cell("Σ-n-0"), cfg=CFG)
    p = model.calls[5]
    assert [m["role"] for m in p["messages"]] == ["user", "user"]
    assert p["messages"][0]["content"][0]["text"].startswith(BRIDGE_PREFIX)
    assert p["messages"][1] == _user(obs_text(4))
    q = model.calls[8]  # the second summary request starts with the first bridge
    assert [m["role"] for m in q["messages"]] == ["user", "user"] + ["assistant", "user"] * 3
    _check(p)
    _check(q)


def test_sigma_on_real_episodes(small_eps):
    for ep in small_eps:
        run = run_episode(ep, get_cell("Σ-n-0"), CFG, FakeModel())  # the fake checks bodies
        assert run.exit_reason == "DONE", ep.episode_id
        assert run.n_summary_requests >= 1 and run.n_summary_failures == 0
        assert len(run.compactions) == run.n_summary_requests
        assert run.need_pinned_carried is None
        if ep.cell.distance == "far":  # the evidence is compacted before the need step
            assert run.need_info["bridge_index"] == 0 and run.need_bridge_carried is not None
        assert run.compacted_between in (0, 1)


# --- W-nk-0: the pinned block ---------------------------------------------------------------

def _pinned_body(keep: int, m: int, replies: dict | None = None) -> list[dict]:
    replies = replies or {}
    msgs = _turns(keep, m)
    if keep:
        kept = [replies.get(t, reply_text(t)) for t in range(keep)]
        msgs = [_user(pinned_text(kept)), *msgs]
    return msgs


def test_pinned_payloads_exactly():
    _, model, requests = run_synthetic(get_cell("W-nk-0"), cfg=CFG)
    assert [mlabels(p) for p in model.calls] == [
        (["P"] if k else []) + [x for t in range(k, m) for x in (f"U{t}", f"A{t}")] + [f"U{m}"]
        for m, k in enumerate(WINDOW_KEEP)]
    for m, (k, p) in enumerate(zip(WINDOW_KEEP, model.calls, strict=True)):
        assert p == _body(NOTES_SYSTEM, _pinned_body(k, m))
        _check(p)
    for m, (k, r) in enumerate(zip(WINDOW_KEEP, requests, strict=True)):
        assert r.info["keep_start"] == k
        assert r.info["pinned_index"] == (0 if k else None)
        assert r.info["pinned_turns"] == list(range(k))
        assert r.info["pinned_reply_tokens"] == 50 * k
        assert r.info["pinned_tokens"] == (tokens.count(pinned_text(
            [reply_text(t) for t in range(k)])) if k else 0)
        assert r.info["pinned_over_cap"] is False and r.info["pinned_left_out"] == 0
        assert r.trace[0] == ("P" if k else "U0"), m


def test_pinned_differs_from_w_n_0_by_the_block_only():
    for W, count_system, reps in ((1000, False, 50), (965, True, 50), (1000, False, {1: 300}),
                                  (2000, True, {0: 700, 2: 10})):
        _, mk, rk = run_synthetic(get_cell("W-nk-0"), cfg=CFG, W=W, count_system=count_system,
                                  reply_tokens=reps)
        _, mn, rn = run_synthetic(CELLS["W-n-0"], cfg=CFG, W=W, count_system=count_system,
                                  reply_tokens=reps)
        assert [{k: v for k, v in r.info.items() if k not in PINNED_KEYS} for r in rk] == [
            r.info for r in rn]
        for pk, pn, r in zip(mk.calls, mn.calls, rk, strict=True):
            lead = 1 if r.info["pinned_index"] == 0 else 0
            assert {**pk, "messages": pk["messages"][lead:]} == pn
        assert all(PINNED_KEYS.isdisjoint(r.info) for r in rn)


def test_the_cap_keeps_the_newest_dropped_replies():
    """250-token replies, so a turn is 450 tokens and the window keeps one earlier turn
    (200 + 450 <= 1000 < 200 + 900): observation m keeps turns m-1.. from m = 2, and turns
    0..m-2 are dropped. 600 reply tokens hold two of them (500), not three (750)."""
    _, model, requests = run_synthetic(get_cell("W-nk-0"), cfg=CFG, n_steps=8,
                                       reply_tokens=250)
    obs, rep = [200] * 8, [250] * 7
    keep = [window_keep_start(obs[: m + 1], rep[:m], 1000) for m in range(8)]
    assert keep == [0, 0, 1, 2, 3, 4, 5, 6]
    want = [[], [], [0], [0, 1], [1, 2], [2, 3], [3, 4], [4, 5]]
    assert [r.info["pinned_turns"] for r in requests] == want
    assert [r.info["pinned_left_out"] for r in requests] == [0, 0, 0, 0, 1, 2, 3, 4]
    assert [r.info["pinned_reply_tokens"] for r in requests] == [250 * len(w) for w in want]
    for m, (w, p) in enumerate(zip(want, model.calls, strict=True)):
        if w:
            assert p["messages"][0] == _user(pinned_text([reply_text(t, 250) for t in w])), m
        _check(p)


def test_the_newest_reply_is_kept_whole_over_the_cap():
    """700-token replies: each turn is 900 tokens, so every earlier turn is dropped
    (200 + 900 > 1000), and the newest dropped reply alone passes 600."""
    _, model, requests = run_synthetic(get_cell("W-nk-0"), cfg=CFG, n_steps=4,
                                       reply_tokens=700)
    assert [r.info["keep_start"] for r in requests] == [0, 1, 2, 3]
    assert [r.info["pinned_turns"] for r in requests] == [[], [0], [1], [2]]
    assert [r.info["pinned_over_cap"] for r in requests] == [False, True, True, True]
    assert [r.info["pinned_left_out"] for r in requests] == [0, 0, 1, 2]
    assert model.calls[3]["messages"][0] == _user(pinned_text([reply_text(2, 700)]))
    for p in model.calls:
        _check(p)


def test_a_turn_with_no_kept_reply_adds_nothing():
    def reply_fn(payload, i):
        return "" if i == 1 else reply_text(i)

    _, model, requests = run_synthetic(get_cell("W-nk-0"), cfg=CFG,
                                       fake=FakeModel(reply_fn,
                                                      summary_fn=lambda p, j: summary_text(j)))
    # turn 1's reply is the empty text (0 tokens toward W, sent as the placeholder)
    keep = [window_keep_start([200] * (m + 1), [0 if t == 1 else 50 for t in range(m)], 1000)
            for m in range(9)]
    assert [r.info["keep_start"] for r in requests] == keep
    assert [r.info["pinned_turns"] for r in requests] == [
        [t for t in range(k) if t != 1] for k in keep]
    assert keep[7] == 4 and model.calls[7]["messages"][0] == _user(pinned_text(
        [reply_text(0), reply_text(2), reply_text(3)]))
    assert model.calls[2]["messages"][3] == _assistant(EMPTY_REPLY_PLACEHOLDER)
    for p in model.calls:
        _check(p)


def test_pinned_on_real_episodes_keeps_s_and_records_carried(small_eps):
    """Replies that copy every evidence sentence: the block holds the evidence, yet S at the
    need step equals W-n-0's (the block is not an observation), and the block is matched apart.
    """
    n_with_block = 0
    for ep in small_eps:
        text = "\n".join(c.sentence for c in ep.components) + "\nACTION: ack(none)"

        def reply_fn(payload, i, text=text):
            return text

        rk = run_episode(ep, get_cell("W-nk-0"), CFG, FakeModel(reply_fn))
        rn = run_episode(ep, CELLS["W-n-0"], CFG, FakeModel(reply_fn))
        assert rk.exit_reason == rn.exit_reason == "DONE", ep.episode_id
        assert rk.need_payload["S"] == rn.need_payload["S"], ep.episode_id
        assert rk.need_payload["components"] == rn.need_payload["components"]
        assert rn.need_pinned_carried is None and "pinned_index" not in rn.need_info
        if rk.need_info["pinned_index"] == 0:
            n_with_block += 1
            assert rk.need_pinned_carried["carried"] is True, ep.episode_id
        else:
            assert rk.need_pinned_carried is None
        if ep.cell.distance == "far" and ep.components:
            assert rk.need_payload["S"] is False and rk.need_info["pinned_index"] == 0
    assert n_with_block >= len(small_eps) // 2


# --- the request-side check ----------------------------------------------------------------

def _payload(messages: list[dict]) -> dict:
    return _body(NOTES_SYSTEM, messages)


@pytest.mark.parametrize("lead", [
    ARC_SUMMARY_BRIDGE_TEMPLATE.format(summary="S"), pinned_text(["R"])])
def test_the_check_admits_one_leading_harness_message(lead):
    _check(_payload([_user(lead), _user("OBS")]))
    _check(_payload([_user(lead), _user("OBS"), _assistant("A"), _user("OBS2")]))
    _check(_payload([_user(lead), _user("OBS"), _assistant("A"),
                     _user(ARC_SUMMARY_REQUEST_PROMPT)]))


@pytest.mark.parametrize("messages, problem", [
    ([_user("OBS"), _user("OBS2")], "message 1 is not a assistant message"),
    ([_user("Earlier conversation history"), _user("OBS")], "message 1 is not a assistant"),
    ([_user(pinned_text(["R"])), _user(pinned_text(["R"])), _user("OBS")],
     "message 2 is not a assistant message"),
    ([_user(pinned_text(["R"])), _user("OBS"), _assistant("A")], "a prefill"),
    ([{"role": "user", "content": [{"type": "text", "text": pinned_text(["R"])},
                                   {"type": "text", "text": "x"}]}, _user("OBS")],
     "message 1 is not a assistant message"),
    ([_assistant(pinned_text(["R"])), _user("OBS")], "message 0 is not a user message"),
])
def test_the_check_refuses_every_other_repeated_role(messages, problem):
    with pytest.raises(RequestCheckFailed, match=problem):
        _check(_payload(messages))


def test_a_pinned_text_inside_a_later_message_is_no_lead():
    with pytest.raises(RequestCheckFailed, match="message 3 is not a assistant message"):
        _check(_payload([_user("OBS"), _assistant("A"), _user(pinned_text(["R"])),
                         _user("OBS2")]))


def test_luna_never_sends_a_pinned_block_or_a_new_info_key():
    for cid in ("F-0", "W-n-0", "W-0", "Σ-n-0", "Σ-n-r", "W-n-r", "F-r"):
        _, model, requests = run_synthetic(CELLS[cid])
        assert all(PINNED_KEYS.isdisjoint(r.info) for r in requests), cid
        assert all("P" not in r.trace for r in requests), cid
        assert all(not any(isinstance(i.get("content"), list) and any(
            str(b.get("text", "")).startswith(PINNED_PREFIX) for b in i["content"])
            for i in p["input"]) for p in model.calls), cid


def test_the_system_prompt_is_the_episodes_plus_the_notes_sentence():
    _, model, _ = run_synthetic(get_cell("W-nk-0"), cfg=CFG)
    assert all(p["system"] == SYSTEM + "\n" + NOTES_INSTRUCTION for p in model.calls)
