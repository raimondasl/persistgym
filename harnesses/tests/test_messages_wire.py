"""Payload snapshot tests of the Messages wire (harnesses/wire.py; PREREG §17.8, amendment
R8), hand-derived like test_payload_snapshots.py's, and its response parsing,
usage and pricing.

Synthetic episode as there: observations of exactly 200 tokens, replies of exactly 50, W =
1000, so a window cell keeps turns max(0, m-3)..m-1 at observation m. On the Messages wire a
turn goes back as its visible reply only, so the labels are U<t> (observation t) and A<t>
(its reply), never R<t>: no thinking block is ever sent back (replay off). Labels come from
payload content, never from the session's own bookkeeping.

The last sections assert the single-turn control's request on the Messages wire (F-0's first
request but for its one user message and without `cache_control`), the runner and the fake
model on this wire, and the Haiku price (both cards, the 100,000-token edge).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re

import anthropic
import pytest

from common import costs
from harnesses import pricing, registered, runner, single_turn
from harnesses.cells import CELLS, NOTES_INSTRUCTION
from harnesses.config import HarnessConfig
from harnesses.fake import FakeModel
from harnesses.items import item_text
from harnesses.parallel import CallGate, RunStop
from harnesses.pricing import UsageLedger, cost_usd, messages_usage_numbers, price_for
from harnesses.runner import run_batch, run_episode
from harnesses.session import HarnessSession
from harnesses.tests.conftest import SYSTEM, obs_text, reply_text, run_synthetic, summary_text
from harnesses.wire import (
    EMPTY_REPLY_PLACEHOLDER,
    MESSAGES,
    RESPONSES,
    RequestCheckFailed,
    UnsupportedOnWire,
    wire_for,
)
from persistgym import tokens
from persistgym.config import PRESETS
from persistgym.controls import single_turn_control
from persistgym.episode import TaskCell
from persistgym.render import generate
from persistgym.survival import reference_window_payload

HAIKU = "claude-haiku-5-5"
CFG = HarnessConfig(model=HAIKU, reasoning_effort="medium", service_tier="standard")
NOTES_SYSTEM = SYSTEM + "\n" + NOTES_INSTRUCTION
FIELDS = {"model", "system", "messages", "max_tokens", "thinking", "output_config",
          "cache_control"}
FORBIDDEN = ("temperature", "top_p", "top_k", "tools", "tool_choice", "fallbacks",
             "stop_sequences", "service_tier", "metadata", "reasoning", "input",
             "instructions", "max_output_tokens", "store", "include", "truncation")

# Hand-derived expectations (module docstring): the turns each step request sends verbatim.
FULL_KEEP = [0] * 9
WINDOW_KEEP = [0, 0, 0, 0, 1, 2, 3, 4, 5]


def _user(text):
    return {"role": "user", "content": [{"type": "text", "text": text}]}


def _assistant(text):
    return {"role": "assistant", "content": [{"type": "text", "text": text}]}


def _body(system, messages, cache=True):
    out = {"model": HAIKU, "system": system, "messages": messages, "max_tokens": 32000,
           "thinking": {"type": "adaptive"}, "output_config": {"effort": "medium"}}
    if cache:
        out["cache_control"] = {"type": "ephemeral"}
    return out


def _turns(keep, m):
    """Messages of turns keep..m-1 (observation, reply), then observation m."""
    out = []
    for t in range(keep, m):
        out += [_user(obs_text(t)), _assistant(reply_text(t))]
    return out + [_user(obs_text(m))]


_OBS = re.compile(r"^OBS\[(\d+)\]")
_REP = re.compile(r"^REPLY\[(\d+)\]")


def label(message: dict) -> str:
    """Content-derived label of one Messages message: U<t>, A<t>, or E for the empty-reply
    placeholder; a thinking block anywhere fails the test."""
    assert set(message) == {"role", "content"}
    assert all(b["type"] == "text" and set(b) == {"type", "text"} for b in message["content"])
    text = "".join(b["text"] for b in message["content"])
    if message["role"] == "user":
        m = _OBS.match(text)
        return f"U{m.group(1)}" if m else "BAD-user"
    if text == EMPTY_REPLY_PLACEHOLDER:
        return "E"
    m = _REP.match(text)
    return f"A{m.group(1)}" if m else "BAD-assistant"


def labels(payload: dict) -> list[str]:
    return [label(m) for m in payload["messages"]]


def no_reasoning_turns(keep: int, m: int) -> list[str]:
    out = []
    for t in range(keep, m):
        out += [f"U{t}", f"A{t}"]
    return out + [f"U{m}"]


def _assert_wire_invariants(p: dict, *, cache: bool = True) -> None:
    """What every Messages body of a replay-off cell holds (PREREG §17.8)."""
    assert set(p) == (FIELDS if cache else FIELDS - {"cache_control"})
    assert not any(k in p for k in FORBIDDEN)
    assert p["thinking"] == {"type": "adaptive"}  # display left at the default: omitted
    assert p["output_config"] == {"effort": "medium"} and p["max_tokens"] == 32000
    assert (p.get("cache_control") == {"type": "ephemeral"}) is cache
    roles = [m["role"] for m in p["messages"]]
    assert roles == ["user", "assistant"] * (len(roles) // 2) + ["user"]   # last: the user's
    blocks = [b for m in p["messages"] for b in m["content"]]
    assert not any(b["type"] in ("thinking", "redacted_thinking") for b in blocks)
    MESSAGES.check_payload(p, effort="medium", max_tokens=32000)


# --- which wire, which cells ---------------------------------------------------------------

def test_the_model_string_chooses_the_wire():
    assert wire_for(HAIKU) is MESSAGES and wire_for("claude-haiku-5-5-x") is MESSAGES
    for model in ("gpt-6-luna", "gpt-6.1-sol", "some-other-model", "", None):
        assert wire_for(model) is RESPONSES
    # the price agrees on the provider and API of every priced model
    for model, price in pricing.PRICES.items():
        assert (price.provider, price.api) == (wire_for(model).provider, wire_for(model).api)
    # and HarnessConfig has no wire field: luna's config hash is as before
    assert "api" not in HarnessConfig().to_dict() and "wire" not in HarnessConfig().to_dict()


@pytest.mark.parametrize("cell_id", ["F-r", "W-n-r", "Σ-n-r", "Σ-n-0", "Σ-0-r"])
def test_the_messages_wire_refuses_replay_on_and_summary_cells(cell_id):
    with pytest.raises(UnsupportedOnWire, match="Messages wire runs"):
        HarnessSession(CELLS[cell_id], SYSTEM, CFG, W_tokens=1000, count_system=False)


@pytest.mark.parametrize("change, what", [
    ({"service_tier": "flex"}, "service tier 'flex'"),
    ({"reasoning_mode": "pro"}, "reasoning mode 'pro'"),
    ({"reasoning_effort": "minimal"}, "effort 'minimal'"),
    ({"reasoning_summary": "auto"}, "reasoning summaries"),
    ({"prompt_cache_key": "k"}, "prompt_cache_key")])
def test_the_messages_wire_refuses_settings_it_does_not_send(change, what):
    with pytest.raises(UnsupportedOnWire, match=re.escape(what)):
        HarnessSession(CELLS["F-0"], SYSTEM, CFG.replace(**change), W_tokens=None,
                       count_system=False)
    # and the Responses wire refuses the Messages API's tier
    with pytest.raises(UnsupportedOnWire, match="Messages API's"):
        HarnessSession(CELLS["F-0"], SYSTEM, HarnessConfig(service_tier="standard"),
                       W_tokens=None, count_system=False)


# --- the bodies, hand-derived --------------------------------------------------------------

@pytest.mark.parametrize("cell_id, keep, system", [
    ("F-0", FULL_KEEP, SYSTEM), ("W-0", WINDOW_KEEP, SYSTEM), ("W-n-0", WINDOW_KEEP, NOTES_SYSTEM)])
def test_cell_payloads_exactly(cell_id, keep, system):
    """Every request of the 9-step episode, whole: the turns it keeps (visible text only), the
    system prompt (W-n-0: plus "\\n" and the notes sentence), the fixed fields."""
    _, model, requests = run_synthetic(CELLS[cell_id], cfg=CFG)
    assert [labels(p) for p in model.calls] == [no_reasoning_turns(k, m)
                                                for m, k in enumerate(keep)]
    assert [r.trace for r in requests] == [labels(p) for p in model.calls]
    for m, (k, p) in enumerate(zip(keep, model.calls, strict=True)):
        assert p == _body(system, _turns(k, m))
        _assert_wire_invariants(p)


def test_full_payload_literal_window_cell_where_the_oldest_pair_is_dropped():
    """W-0 at step 4, the first step past the window boundary (200 + 4 x 250 = 1200 > 1000):
    turn 0's observation and reply are gone, turns 1-3 go as visible text, then
    observation 4."""
    _, model, _ = run_synthetic(CELLS["W-0"], cfg=CFG)
    assert model.calls[3] == _body(SYSTEM, _turns(0, 3))
    assert model.calls[4] == {
        "model": "claude-haiku-5-5",
        "system": SYSTEM,
        "messages": [_user(obs_text(1)), _assistant(reply_text(1)),
                     _user(obs_text(2)), _assistant(reply_text(2)),
                     _user(obs_text(3)), _assistant(reply_text(3)),
                     _user(obs_text(4))],
        "max_tokens": 32000,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "medium"},
        "cache_control": {"type": "ephemeral"},
    }


def test_notes_pair_differs_only_in_system():
    """W-n-0 and W-0 keep the same turns (the notes sentence never counts toward W, D5) and
    send the same bodies but for `system`."""
    for W, count_system in ((1000, False), (965, True)):
        _, mn, _ = run_synthetic(CELLS["W-n-0"], cfg=CFG, W=W, count_system=count_system)
        _, m0, _ = run_synthetic(CELLS["W-0"], cfg=CFG, W=W, count_system=count_system)
        assert len(mn.calls) == len(m0.calls) == 9
        for pn, p0 in zip(mn.calls, m0.calls, strict=True):
            assert pn["system"] == NOTES_SYSTEM and p0["system"] == SYSTEM
            assert {**pn, "system": SYSTEM} == p0


def test_window_and_token_counts_are_the_responses_wires():
    """W and every count the history policy uses stay in project tokens (o200k_base): the
    Messages wire keeps the same turns as the Responses wire on the same replies."""
    for cell_id in ("F-0", "W-0", "W-n-0"):
        for kw in ({}, {"W": 949}, {"W": 965, "count_system": True}, {"reply_tokens": {1: 300}}):
            sm, mm, rm = run_synthetic(CELLS[cell_id], cfg=CFG, **kw)
            so, mo, ro = run_synthetic(CELLS[cell_id], **kw)
            assert [r.info for r in rm] == [r.info for r in ro]
            assert [[t for t in r.trace if not t.startswith("R")] for r in ro] == [
                r.trace for r in rm]
            assert [t.reply_tokens for t in sm.turns] == [t.reply_tokens for t in so.turns]
            for pm, po in zip(mm.calls, mo.calls, strict=True):
                texts = [item_text(i) for i in po["input"] if i.get("type") != "reasoning"]
                assert [item_text(m) for m in pm["messages"]] == texts
                assert pm["system"] == po["instructions"]


def test_window_payload_matches_generator_reference(small_eps):
    """On real episodes, the W cells' messages equal persistgym's reference drop-oldest
    payload for the same replies, at every step."""
    for ep in small_eps:
        if ep.cell.recoverable:
            continue
        for cid in ("W-0", "W-n-0"):
            events = []
            run_episode(ep, CELLS[cid], CFG, FakeModel(), recorder=events.append)
            replies = [MESSAGES.text(e["response"]) for e in events]
            for m, e in enumerate(events):
                ref = reference_window_payload(ep, replies[:m])
                assert [(x["role"], item_text(x)) for x in e["payload"]["messages"]] == [
                    (x["role"], x["content"]) for x in ref[1:]]
                if cid == "W-0":
                    assert e["payload"]["system"] == ref[0]["content"]
                _assert_wire_invariants(e["payload"])


# --- an empty visible reply ----------------------------------------------------------------

def _empty_at(turn: int, status: str = "completed") -> FakeModel:
    """Fake whose step call `turn` has thinking only (no text block)."""
    return FakeModel(lambda p, i: "" if i == turn else reply_text(i),
                     summary_fn=lambda p, j: summary_text(j),
                     status_fn=lambda p, tag: status if tag == f"t{turn}" else "completed")


@pytest.mark.parametrize("status", ["completed", "incomplete", "refusal"])
def test_an_empty_visible_reply_goes_back_as_the_placeholder(status):
    """A turn with no visible text (end_turn with thinking only, a stop at max_tokens while
    thinking, a refusal) cannot go back as an empty assistant message (the API rejects an
    empty text block): it goes back as one text block holding the placeholder. Its visible
    reply, the one W counts, is still empty: 0 tokens. At W = 1150 step 4 keeps every turn
    (200 + 250 + 200 + 250 + 250 = 1150), where a 50-token reply would drop turn 0."""
    s, model, _ = run_synthetic(CELLS["F-0"], n_steps=5, cfg=CFG, fake=_empty_at(2, status))
    assert model.calls[3] == _body(SYSTEM, [
        _user(obs_text(0)), _assistant(reply_text(0)), _user(obs_text(1)),
        _assistant(reply_text(1)), _user(obs_text(2)), _assistant(EMPTY_REPLY_PLACEHOLDER),
        _user(obs_text(3))])
    assert (s.turns[2].reply, s.turns[2].reply_tokens) == ("", 0)
    assert labels(model.calls[3]) == ["U0", "A0", "U1", "A1", "U2", "E", "U3"]
    _, model, _ = run_synthetic(CELLS["W-0"], n_steps=5, W=1150, cfg=CFG,
                                fake=_empty_at(2, status))
    assert labels(model.calls[4]) == ["U0", "A0", "U1", "A1", "U2", "E", "U3", "A3", "U4"]
    _, model, _ = run_synthetic(CELLS["W-0"], n_steps=5, W=1150, cfg=CFG)
    assert labels(model.calls[4]) == no_reasoning_turns(1, 4)
    assert tokens.count(EMPTY_REPLY_PLACEHOLDER) > 0  # sent, but never counted toward W


def test_a_refusals_partial_text_is_discarded_from_the_history():
    """A refusal can come mid-stream, after some text. Anthropic: discard the partial output
    (https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback). Its text
    goes back neither in later requests nor into W: the turn goes back as the placeholder and
    counts 0 tokens, as an empty reply. The environment still gets the text, and the step is
    an invalid action (D13). A stop at max_tokens keeps its partial text, as on OpenAI."""
    def fake(status):
        return FakeModel(lambda p, i: reply_text(i), summary_fn=lambda p, j: summary_text(j),
                         status_fn=lambda p, tag: status if tag == "t2" else "completed")
    s, model, _ = run_synthetic(CELLS["F-0"], n_steps=5, cfg=CFG, fake=fake("refusal"))
    assert model.calls[2]["messages"][-1] == _user(obs_text(2))
    assert model.calls[3] == _body(SYSTEM, [
        _user(obs_text(0)), _assistant(reply_text(0)), _user(obs_text(1)),
        _assistant(reply_text(1)), _user(obs_text(2)), _assistant(EMPTY_REPLY_PLACEHOLDER),
        _user(obs_text(3))])
    assert (s.turns[2].reply, s.turns[2].reply_tokens) == ("", 0)
    refused = FakeModel(status_fn=lambda p, tag: "refusal").send(_body(SYSTEM, _turns(0, 0)))
    assert MESSAGES.text(refused) and MESSAGES.kept_reply(refused) == ""  # text kept, not sent
    # W counts it as an empty reply: at W = 1150 step 4 keeps every turn
    _, model, _ = run_synthetic(CELLS["W-0"], n_steps=5, W=1150, cfg=CFG, fake=fake("refusal"))
    assert labels(model.calls[4]) == ["U0", "A0", "U1", "A1", "U2", "E", "U3", "A3", "U4"]
    # a stop at max_tokens after some text keeps it (sent back, counted)
    s, model, _ = run_synthetic(CELLS["F-0"], n_steps=4, cfg=CFG, fake=fake("incomplete"))
    assert labels(model.calls[3]) == no_reasoning_turns(0, 3)
    assert s.turns[2].reply == reply_text(2)
    # the Responses wire keeps every reply (OpenAI's code is unchanged)
    assert RESPONSES.kept_reply({"output": []}) == RESPONSES.text({"output": []}) == ""


def test_a_refused_step_is_invalid_and_its_partial_text_kept_in_the_record(small_eps):
    ep = next(e for e in small_eps if e.cell.id == "derived-nonrec-far"
              and e.need_step < e.n_steps - 1)  # steps after the need step
    need = ep.steps[ep.need_step].observation
    correct = f"ACTION: {ep.need.expected_action}"
    events = []
    fake = FakeModel(lambda p, i: correct if item_text(p["messages"][-1]) == need
                     else "ACTION: ack(none)",
                     status_fn=lambda p, tag: ("refusal" if item_text(p["messages"][-1]) == need
                                               else "completed"))
    run = run_episode(ep, CELLS["F-0"], CFG, fake, recorder=events.append)
    assert run.exit_reason == "DONE" and not run.need_correct
    (inc,) = run.incomplete
    assert inc["reason"] == "refusal:general_harms" and inc["reply_chars"] == len(correct)
    after = [e["payload"]["messages"] for e in events if e["request_index"] > ep.need_step]
    assert after and all(item_text(m) != correct for msgs in after for m in msgs)
    assert all(EMPTY_REPLY_PLACEHOLDER in [item_text(m) for m in msgs] for msgs in after)


def test_a_whitespace_reply_goes_back_as_the_placeholder_and_counts_as_itself():
    s, model, _ = run_synthetic(CELLS["F-0"], n_steps=3, cfg=CFG,
                                fake=FakeModel(lambda p, i: "\n" if i == 1 else reply_text(i)))
    assert model.calls[2]["messages"][3] == _assistant(EMPTY_REPLY_PLACEHOLDER)
    assert (s.turns[1].reply, s.turns[1].reply_tokens) == ("\n", tokens.count("\n"))


# --- the request-side check ----------------------------------------------------------------

def _good() -> dict:
    return _body(SYSTEM, _turns(0, 2))


@pytest.mark.parametrize("change, problem", [
    (lambda p: p["messages"][1]["content"].insert(
        0, {"type": "thinking", "thinking": "", "signature": "s"}), "1 thinking blocks"),
    (lambda p: p["messages"][1]["content"].insert(
        0, {"type": "redacted_thinking", "data": "x"}), "1 thinking blocks"),
    (lambda p: p["messages"].append(_assistant("prefill")), "a prefill"),
    (lambda p: p.update(temperature=1.0), "fields not sent on the Messages wire: temperature"),
    (lambda p: p.update(top_p=0.99), "top_p"),
    (lambda p: p.update(tools=[]), "tools"),
    (lambda p: p.update(fallbacks=[]), "fallbacks"),
    (lambda p: p.update(service_tier="standard_only"), "service_tier"),
    (lambda p: p.update(thinking={"type": "adaptive", "display": "summarized"}), "thinking"),
    (lambda p: p.update(thinking={"type": "enabled", "budget_tokens": 1024}), "thinking"),
    (lambda p: p.update(output_config={"effort": "high"}), "output_config"),
    (lambda p: p.update(output_config={"effort": "medium", "format": {}}), "output_config"),
    (lambda p: p.update(max_tokens=4000), "max_tokens 4000"),
    (lambda p: p.update(cache_control={"type": "ephemeral", "ttl": "1h"}), "cache_control"),
    (lambda p: p.pop("thinking"), "missing fields: thinking"),
    (lambda p: p.update(system=""), "no system prompt"),
    (lambda p: p["messages"][1]["content"][0].update(text=" "), "non-empty text block"),
    (lambda p: p["messages"].insert(1, _user("again")), "not a assistant message")])
def test_the_request_side_check_refuses_before_sending(change, problem):
    _good_body = _good()
    MESSAGES.check_payload(_good_body, effort="medium", max_tokens=32000)
    p = _good()
    change(p)
    with pytest.raises(RequestCheckFailed, match=re.escape(problem)):
        MESSAGES.check_payload(p, effort="medium", max_tokens=32000)
    # the fake model runs the same check (with any effort and cap) before it answers
    if problem not in ("output_config", "max_tokens 4000"):
        with pytest.raises(RequestCheckFailed):
            FakeModel().send(p)


# --- responses: text, status, usage --------------------------------------------------------

def _response(stop="end_turn", text="ACTION: ack(none)", details=None, **usage):
    content = [{"type": "thinking", "thinking": "", "signature": "sig"}]
    if text is not None:
        content.append({"type": "text", "text": text})
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": HAIKU,
            "content": content, "stop_reason": stop, "stop_details": details,
            "usage": {"input_tokens": 10, "cache_read_input_tokens": 900,
                      "cache_creation_input_tokens": 90, "output_tokens": 300,
                      "output_tokens_details": {"thinking_tokens": 250},
                      "service_tier": "standard", "inference_geo": "global", **usage}}


def test_reply_text_is_the_text_blocks_never_thinking():
    r = _response()
    r["content"][0]["thinking"] = "secret reasoning"
    r["content"].append({"type": "text", "text": "\nmore"})
    assert MESSAGES.text(r) == "ACTION: ack(none)\nmore"
    items, dropped = MESSAGES.turn_items(r)
    assert items == [_assistant("ACTION: ack(none)\nmore")] and dropped == []
    r["content"].append({"type": "tool_use", "id": "t", "name": "x", "input": {}})
    assert MESSAGES.turn_items(r)[1] == ["tool_use"]


@pytest.mark.parametrize("stop, details, status", [
    ("end_turn", None, ("completed", None)),
    ("max_tokens", None, ("incomplete", "max_output_tokens")),
    ("refusal", {"type": "refusal", "category": "cyber", "explanation": None},
     ("incomplete", "refusal:cyber")),
    ("refusal", {"type": "refusal", "category": None, "explanation": None},
     ("incomplete", "refusal:null")),
    ("model_context_window_exceeded", None,
     ("incomplete", "unexpected_stop_reason:model_context_window_exceeded")),
    ("stop_sequence", None, ("incomplete", "unexpected_stop_reason:stop_sequence")),
    (None, None, ("incomplete", "unexpected_stop_reason:None"))])
def test_stop_reasons(stop, details, status):
    assert MESSAGES.status(_response(stop, details=details)) == status


def test_usage_in_the_responses_meanings():
    """input = input_tokens + cache reads + cache writes (OpenAI's input_tokens counts cached
    tokens; D8's N relies on it); thinking from output_tokens_details, else None, never 0."""
    u = MESSAGES.usage(_response())
    assert u == {"input_tokens": 1000, "cached_input_tokens": 900, "cache_write_tokens": 90,
                 "output_tokens": 300, "reasoning_tokens": 250}
    r = _response()
    del r["usage"]["output_tokens_details"]
    assert MESSAGES.usage(r)["reasoning_tokens"] is None
    assert messages_usage_numbers(None) == {"input_tokens": 0, "cached_input_tokens": 0,
                                            "cache_write_tokens": 0, "output_tokens": 0,
                                            "reasoning_tokens": None}
    assert MESSAGES.served_tier(_response()) == "standard"
    # output reported but no breakdown: unknown; no output at all (a refusal before any
    # output, documented without output_tokens_details): 0, exactly (thinking <= output)
    assert messages_usage_numbers({"input_tokens": 412, "output_tokens": 5})[
        "reasoning_tokens"] is None
    assert messages_usage_numbers({"input_tokens": 412, "output_tokens": 0}) == {
        "input_tokens": 412, "cached_input_tokens": 0, "cache_write_tokens": 0,
        "output_tokens": 0, "reasoning_tokens": 0}


def test_the_echo_reports_what_the_messages_api_does_not_echo_as_none():
    echo = runner.check_echo(_body(SYSTEM, _turns(0, 0)), _response())
    assert echo == {"context_requested": None, "context_echoed": None, "context_ok": None,
                    "effort_requested": "medium", "effort_echoed": None, "effort_ok": None,
                    "mode_requested": None, "mode_echoed": None,
                    "model_requested": HAIKU, "model_returned": HAIKU,
                    "service_tier_requested": "standard", "service_tier_returned": "standard",
                    "status": "completed", "incomplete_reason": None, "stop_reason": "end_turn"}


# --- the fake model and the runner on this wire --------------------------------------------

def test_fake_messages_response_shape():
    fake = FakeModel()
    r = fake.send(_body(SYSTEM, _turns(0, 1)))
    assert r["type"] == "message" and r["model"] == HAIKU + "-fake-2026-10-01"
    assert r["content"][0] == {"type": "thinking", "thinking": "", "signature": "fake-sig-t0"}
    assert r["content"][1] == {"type": "text", "text": "Fake reply to turn 0.\nACTION: ack(none)"}
    assert r["stop_reason"] == "end_turn" and "reasoning" not in r and "status" not in r
    u = r["usage"]
    assert u["output_tokens_details"]["thinking_tokens"] == 37 and u["service_tier"] == "standard"
    visible = tokens.count(SYSTEM + obs_text(0) + reply_text(0) + obs_text(1))
    assert u["input_tokens"] + u["cache_read_input_tokens"] + u["cache_creation_input_tokens"] \
        in range(visible - 2, visible + 3)
    no_cache = fake.send(_body(SYSTEM, _turns(0, 0), cache=False))["usage"]
    assert no_cache["cache_read_input_tokens"] == no_cache["cache_creation_input_tokens"] == 0
    assert "output_tokens_details" not in FakeModel(report_thinking_tokens=False).send(
        _body(SYSTEM, _turns(0, 0)))["usage"]


def test_runner_on_the_messages_wire(small_eps):
    """No echo to check (never an exclusion); usage summed in the Responses meanings; an
    episode plays to its end in each of R8's cells; the need step's payload S as on OpenAI."""
    for ep in small_eps[:8]:
        for cid in ("F-0", "W-0", "W-n-0"):
            events = []
            run = run_episode(ep, CELLS[cid], CFG, FakeModel(), recorder=events.append)
            assert run.exit_reason == "DONE" and not run.excluded and not run.echo_mismatches
            assert run.n_turns == ep.n_steps and run.n_requests == ep.n_steps
            assert run.echo == {"context_requested": None, "context_echoed": None,
                                "effort_requested": "medium", "effort_echoed": None,
                                "models_returned": {HAIKU + "-fake-2026-10-01": ep.n_steps},
                                "service_tiers_returned": {"standard": ep.n_steps}}
            assert run.usage["reasoning_tokens"] == 37 * ep.n_steps
            assert run.usage["input_tokens"] == sum(MESSAGES.usage(e["response"])
                                                    ["input_tokens"] for e in events)
            assert run.need_payload["n_opaque_items"] == 0
            openai_run = run_episode(ep, CELLS[cid], HarnessConfig(), FakeModel())
            assert run.need_payload["S"] == openai_run.need_payload["S"]
            assert all(e["echo"]["context_ok"] is None for e in events)


def test_runner_reasoning_tokens_not_reported_are_none_not_zero(small_eps):
    ep = small_eps[0]
    run = run_episode(ep, CELLS["F-0"], CFG, FakeModel(report_thinking_tokens=False))
    assert run.usage["reasoning_tokens"] is None and run.usage["output_tokens"] > 0
    assert run.need_phase["reasoning_tokens"] is None and run.need_phase["tokens"] > 0


def test_a_refusal_or_max_tokens_is_an_invalid_action(small_eps):
    """D13 as implemented: any incomplete step scores as an invalid action; on the Messages
    API a stop at max_tokens and a refusal (reason refusal:<category>) are both incomplete."""
    ep = next(e for e in small_eps if e.cell.id == "derived-nonrec-far")
    need = ep.steps[ep.need_step].observation
    correct = f"ACTION: {ep.need.expected_action}"
    for status, reason in (("incomplete", "max_output_tokens"),
                           ("refusal", "refusal:general_harms")):
        fake = FakeModel(lambda p, i: correct if item_text(p["messages"][-1]) == need
                         else "ACTION: ack(none)",
                         status_fn=lambda p, tag, s=status: (
                             s if item_text(p["messages"][-1]) == need else "completed"))
        run = run_episode(ep, CELLS["F-0"], CFG, fake)
        assert run.exit_reason == "DONE" and not run.need_correct
        assert run.need_outcome == "incomplete"
        (inc,) = run.incomplete
        assert (inc["reason"], inc["at_need"], inc["max_output_tokens"]) == (reason, 1, 32000)


def test_run_batch_meta_on_the_messages_wire(small_eps, tmp_path, monkeypatch):
    def no_client(*a, **k):
        raise AssertionError("the fake path must never build an Anthropic client")
    monkeypatch.setattr(anthropic, "Anthropic", no_client)
    eps = small_eps[:3]
    meta = run_batch(eps, CELLS["W-0"], CFG, FakeModel(), experiment="persistgym",
                     run_id="haiku-fake", results_root=tmp_path / "r", raw_root=tmp_path / "raw")
    assert meta["exit_reason"] == "COMPLETED" and meta["n_excluded"] == 0
    assert meta["reasoning_context_requested"] is None
    assert meta["reasoning_context_echoed"] is None and meta["reasoning_effort_echoed"] is None
    assert meta["reasoning_effort"] == "medium" and meta["service_tier_requested"] == "standard"
    assert meta["api"] == "anthropic.messages" and "request-side check" in meta["echo_note"]
    assert meta["prompt_size"] is None  # no ledger: the fake model
    assert meta["inference_geos"] is None
    assert meta["sdk_versions"]["anthropic"] == "1.15.0"
    summary = json.loads((tmp_path / "r" / "persistgym" / "haiku-fake" / "summary.json")
                         .read_text(encoding="utf-8"))
    n = sum(e.n_steps for e in eps)
    assert summary["echo_match"] == {"W-0": {"requests": n, "matched": None,
                                             "effort_matched": None}}
    with gzip.open(tmp_path / "raw" / "persistgym" / "haiku-fake" / "transcript.jsonl.gz",
                   "rt", encoding="utf-8") as f:
        assert all(json.loads(x)["payload"]["model"] == HAIKU for x in f)


def test_openai_meta_is_unchanged(small_eps, tmp_path):
    meta = run_batch(small_eps[:1], CELLS["W-0"], HarnessConfig(), FakeModel(),
                     experiment="persistgym", run_id="luna", results_root=tmp_path / "r",
                     raw_root=tmp_path / "raw")
    assert not {"api", "echo_note", "prompt_size", "inference_geos"} & set(meta)
    assert meta["reasoning_context_requested"] == "current_turn"


# --- the single-turn control on the Messages wire ------------------------------------------

def _flattened(ep) -> str:
    """The single-turn prompt rebuilt by hand, as in test_payload_snapshots.py."""
    text = ep.steps[0].observation
    for i in range(1, ep.need_step + 1):
        text += f"\nAgent: {ep.steps[i - 1].expected_action}\n{ep.steps[i].observation}"
    return text


def test_single_turn_full_request_literal(small_eps):
    """F-0's settings, the episode's system prompt unchanged, the flattened prompt as the
    only message, and no cache_control (the prompt is never sent again)."""
    ep = next(e for e in small_eps if e.cell.id == "observed-nonrec-far")
    req = single_turn.build_request(single_turn_control(ep), CFG)
    assert req.kind == "step" and req.trace == ["U0"]
    assert req.payload == {
        "model": "claude-haiku-5-5",
        "system": ep.system_prompt,
        "messages": [_user(_flattened(ep))],
        "max_tokens": 32000,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "medium"},
    }
    _assert_wire_invariants(req.payload, cache=False)


def test_single_turn_request_is_f0s_but_for_messages_and_cache_control(small_eps):
    for ep in [e for e in small_eps if not e.cell.recoverable]:
        fake = FakeModel()
        run_episode(ep, CELLS["F-0"], CFG, fake)
        first = fake.calls[0]
        payload = single_turn.build_request(single_turn_control(ep), CFG).payload
        assert "cache_control" in first
        assert payload == {k: v for k, v in first.items() if k != "cache_control"} | {
            "messages": [_user(_flattened(ep))]}


# The single-turn request on the registered default config (observed-nonrec-far, main
# template 0) at R8's settings: sha256 of its body as canonical JSON (sorted keys, no spaces,
# UTF-8) and its size, as for luna's (test_payload_snapshots.py)
HAIKU_SINGLE_TURN_SHA256 = "6839a52ebc4eb2bf30944aeb44a7ec5289358ff86a13739f90789e78c36ff713"
HAIKU_SINGLE_TURN_BYTES = 83_306


def test_single_turn_full_request_on_the_registered_default_config():
    (_, eps), = generate("main", [0], PRESETS["default"],
                         [TaskCell.from_id("observed-nonrec-far")], ("base",))
    (ep,) = eps
    assert ep.config_hash == registered.DEFAULT_GENERATOR_HASH  # luna's episodes
    req = single_turn.build_request(single_turn_control(ep), CFG)
    assert req.payload == _body(ep.system_prompt, [_user(_flattened(ep))], cache=False)
    body = json.dumps(req.payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert len(body) == HAIKU_SINGLE_TURN_BYTES
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == HAIKU_SINGLE_TURN_SHA256
    _assert_wire_invariants(req.payload, cache=False)
    # luna's request on the same episode sends the same system prompt and the same prompt
    luna = single_turn.build_request(single_turn_control(ep), HarnessConfig()).payload
    assert item_text(luna["input"][0]) == item_text(req.payload["messages"][0])
    assert luna["instructions"] == req.payload["system"]


# --- pricing (https://platform.claude.com/docs/en/about-claude/pricing, 2026-10-17) ---------

def _usage(plain, read, write, out, one_hour=0, geo="global"):
    usage = {"input_tokens": plain, "cache_read_input_tokens": read,
             "cache_creation_input_tokens": write, "output_tokens": out,
             "cache_creation": {"ephemeral_5m_input_tokens": write - one_hour,
                                "ephemeral_1h_input_tokens": one_hour},
             "inference_geo": geo}
    if geo is None:
        del usage["inference_geo"]
    return usage


@pytest.mark.parametrize("plain, read, write, out, expected", [
    # P = 100,000 exactly: the <= 100k card ($0.10, $0.01, 5m write $0.125, $0.50)
    (10_000, 80_000, 10_000, 1_000, 10_000 * 0.10 + 80_000 * 0.01 + 10_000 * 0.125
     + 1_000 * 0.50),
    # P = 100,001: the > 100k card for every token ($0.50, $0.05, $0.625, $2.50)
    (10_001, 80_000, 10_000, 1_000, 10_001 * 0.50 + 80_000 * 0.05 + 10_000 * 0.625
     + 1_000 * 2.50),
    (0, 0, 0, 32_000, 32_000 * 0.50),
    (200_000, 0, 0, 10, 200_000 * 0.50 + 10 * 2.50)])
def test_haiku_price_cards_and_the_threshold_edge(plain, read, write, out, expected):
    listed, billed = cost_usd(HAIKU, _usage(plain, read, write, out), "standard")
    assert listed == pytest.approx(expected / 1e6) and billed == listed  # no Flex
    assert cost_usd(HAIKU + "-fake-2026-10-01", _usage(plain, read, write, out), None)[0] \
        == pytest.approx(listed)


def test_a_one_hour_cache_write_is_priced_at_twice_input():
    listed, _ = cost_usd(HAIKU, _usage(0, 0, 1_000, 0, one_hour=1_000), "standard")
    assert listed == pytest.approx(1_000 * 0.20 / 1e6)


@pytest.mark.parametrize("geo, factor", [("global", 1.0), ("us", 1.1), (None, 1.1),
                                         ("eu", 1.1)])
@pytest.mark.parametrize("plain, out", [(10_000, 1_000), (100_001, 1_000)])
def test_haiku_is_priced_at_the_inference_geo_it_was_served_in(geo, factor, plain, out):
    """US-only inference costs 1.1x every price, the > 100,000 card included
    (https://platform.claude.com/docs/en/about-claude/pricing#data-residency-pricing); the
    wire sends no inference_geo, so the workspace default decides. A geo not reported, or
    not listed, is priced at the highest multiplier: the estimate errs high, never low."""
    base = cost_usd(HAIKU, _usage(plain, 0, 0, out), "standard")[0]
    listed, billed = cost_usd(HAIKU, _usage(plain, 0, 0, out, geo=geo), "standard")
    assert listed == pytest.approx(base * factor) and billed == listed
    card = 0.50 if plain > 100_000 else 0.10
    assert base == pytest.approx((plain * card + out * card * 5) / 1e6)


def _refusal(category, out=0, **usage):
    """A refusal as documented
    (https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback): empty
    content and a usage with no output_tokens_details."""
    return {"id": "msg_r", "type": "message", "role": "assistant", "model": HAIKU,
            "content": [], "stop_reason": "refusal",
            "stop_details": {"type": "refusal", "category": category, "explanation": None},
            "usage": {"input_tokens": 412, "output_tokens": out, "inference_geo": "global",
                      **usage}}


@pytest.mark.parametrize("category, out, unbilled", [
    ("cyber", 0, True), ("general_harms", 0, True), (None, 0, True),
    ("bio", 0, False), ("frontier_llm", 0, False), ("reasoning_extraction", 0, False),
    ("cyber", 30, False)])  # mid-stream: the input and the output streamed are billed
def test_refusals_anthropic_does_not_bill_have_a_billed_estimate_of_zero(category, out,
                                                                          unbilled):
    r = _refusal(category, out)
    assert pricing.unbilled_refusal("messages", r) is unbilled
    assert not pricing.unbilled_refusal("responses", r)
    listed = (412 * 0.10 + out * 0.50) / 1e6
    ledger = UsageLedger(HAIKU)
    ledger.add(_response())
    first = ledger.cost_usd_list
    assert ledger.add(r) == pytest.approx((listed, 0.0 if unbilled else listed))
    assert ledger.cost_usd_list == pytest.approx(first + listed)
    assert ledger.cost_usd_billed_est == pytest.approx(first + (0 if unbilled else listed))
    assert ledger.unbilled_refusals == int(unbilled)
    row = ledger.costs_row(timestamp_utc="t", run_id="r", milestone="M1",
                           experiment="persistgym_haiku", cell_or_config="F-0", git_commit="g")
    assert ("unbilled_refusals=1" in row["notes"]) is unbilled
    # the episode's cost too: list kept, billed estimate 0
    run = runner.EpisodeRun("e", "t", "c", "base", "F-0", model=HAIKU)
    runner._add_usage(run, r)
    assert run.cost_usd_list == pytest.approx(listed)
    assert run.cost_usd_billed_est == pytest.approx(0.0 if unbilled else listed)


def test_a_refusal_before_any_output_keeps_the_runs_reasoning_tokens():
    """Its usage has no output_tokens_details, but no output at all: 0 thinking tokens, not
    unknown, so one such refusal does not blank the run's reasoning-token total."""
    ledger = UsageLedger(HAIKU)
    for _ in range(1_000):
        ledger.add(_response())
    ledger.add(_refusal("cyber"))
    assert ledger.reasoning_tokens == 250 * 1_000
    row = ledger.costs_row(timestamp_utc="t", run_id="r", milestone="M1",
                           experiment="persistgym_haiku", cell_or_config="F-0", git_commit="g")
    assert row["reasoning_tokens"] == 250_000 and "not reported" not in row["notes"]
    run = runner.EpisodeRun("e", "t", "c", "base", "F-0", model=HAIKU)
    runner._add_usage(run, _response())
    runner._add_usage(run, _refusal(None))
    assert run.usage["reasoning_tokens"] == 250


def test_haiku_ledger_counts_the_inference_geos_served():
    ledger = UsageLedger(HAIKU)
    for geo in ("global", "us", "global", None):
        r = _response()
        if geo is None:
            del r["usage"]["inference_geo"]
        else:
            r["usage"]["inference_geo"] = geo
        ledger.add(r)
    assert ledger.served_geos() == {"None": 1, "global": 2, "us": 1}
    row = ledger.costs_row(timestamp_utc="t", run_id="r", milestone="M1",
                           experiment="persistgym_haiku", cell_or_config="F-0", git_commit="g")
    assert "inference_geos=None:1;global:2;us:1" in row["notes"]
    one = cost_usd(HAIKU, _response()["usage"], "standard")[0]
    assert ledger.cost_usd_list == pytest.approx(one * (2 + 1.1 + 1.1))


def test_haiku_price_record():
    p = price_for(HAIKU)
    assert (p.provider, p.api, p.source_date, p.long_threshold) == (
        "anthropic", "messages", "2026-10-17", 100_000)
    assert (p.input, p.cached, p.output, p.long) == (0.10, 0.01, 0.50, (0.50, 0.05, 2.50))
    assert p.geo_multipliers == (("global", 1.0), ("us", 1.1))
    assert p.worst_card() == pytest.approx((0.55, 0.055, 2.75))
    assert price_for("gpt-6-luna").source_date == pricing.PRICE_SOURCE_DATE == "2026-09-30"
    assert price_for("gpt-6-luna").geo_multiplier("us") == 1.0  # no geo pricing on OpenAI
    assert price_for("gpt-6-luna").worst_card() == (0.10, 0.01, 0.50)
    for unpriced in ("claude-haiku-4-5", "claude-sonnet-5-5", "claude-haiku"):
        with pytest.raises(KeyError):
            price_for(unpriced)


def test_haiku_ledger_and_costs_row(monkeypatch):
    ledger = UsageLedger(HAIKU)
    small = _response(input_tokens=10, cache_read_input_tokens=90_000,
                      cache_creation_input_tokens=9_990)                 # P = 100,000
    big = _response(input_tokens=11, cache_read_input_tokens=90_000,
                    cache_creation_input_tokens=9_990)                   # P = 100,001
    big["usage"]["service_tier"] = "priority"
    ledger.add(small, requested_tier="standard", latency_s=2.0)
    ledger.add(big, requested_tier="standard", latency_s=4.0)
    assert (ledger.max_prompt_tokens, ledger.calls_over_threshold) == (100_001, 1)
    assert ledger.prompt_size() == {"threshold": 100_000, "max_prompt_tokens": 100_001,
                                    "calls_over_threshold": 1}
    row = ledger.costs_row(timestamp_utc="t", run_id="r", milestone="M1",
                           experiment="persistgym_haiku", cell_or_config="F-0",
                           git_commit="g", notes="approved_block=b;")
    assert set(row) == set(costs.COLUMNS)
    assert (row["provider"], row["api"], row["service_tier"]) == (
        "anthropic", "messages", "standard")
    assert row["service_tier_served"] == "priority;standard"
    assert row["price_source_date"] == "2026-10-17"
    assert (row["input_tokens"], row["cached_input_tokens"], row["cache_write_tokens"]) == (
        200_001, 180_000, 19_980)
    assert row["reasoning_tokens"] == 500 and row["cost_usd_billed_est"] == row["cost_usd_list"]
    assert "max_prompt_tokens=100001; calls_over_100000=1" in row["notes"]
    assert "inference_geos=global:2" in row["notes"]
    assert ledger.served_geos() == {"global": 2}
    # thinking tokens not reported: the column is empty, never 0, and the notes say so
    r = _response()
    del r["usage"]["output_tokens_details"]
    ledger.add(r)
    row = ledger.costs_row(timestamp_utc="t", run_id="r", milestone="M1",
                           experiment="persistgym_haiku", cell_or_config="F-0", git_commit="g")
    assert row["reasoning_tokens"] == "" and "reasoning_tokens not reported" in row["notes"]
    # luna's rows are as before
    luna = UsageLedger("gpt-6-luna").costs_row(timestamp_utc="t", run_id="r", milestone="M1",
                                                experiment="persistgym", cell_or_config="F-0",
                                                git_commit="g")
    assert (luna["provider"], luna["api"], luna["price_source_date"]) == (
        "openai", "responses", "2026-09-30")
    assert "max_prompt_tokens" not in luna["notes"] and "inference_geos" not in luna["notes"]
    assert UsageLedger("gpt-6-luna").served_geos() is None


def test_call_gate_bounds_a_messages_call_at_the_dearer_card_and_geo():
    gate = CallGate(10.0, lambda: 0.0, HAIKU, RunStop())
    p = _body(SYSTEM, _turns(0, 2))
    n_bytes = len(json.dumps(p, ensure_ascii=False).encode("utf-8"))
    # $0.625 x 1.1 per input byte (a cache write on the > 100k card, US-only inference) and
    # $2.50 x 1.1 per output token: a call served in the "us" geo stays within the bound
    assert gate.bound_usd(p) == pytest.approx(
        (n_bytes * 0.50 * 1.25 * 1.1 + 32_000 * 2.50 * 1.1) / 1e6)
    worst = _usage(n_bytes, 0, 0, 32_000, geo="us")
    assert cost_usd(HAIKU, worst, "standard")[0] <= gate.bound_usd(p)
    assert gate.bound_usd({k: v for k, v in p.items() if k != "max_tokens"}) == float("inf")
    assert gate.info()["rule"] == CallGate.RULE_MESSAGES and "max_tokens" in gate.rule
    luna = CallGate(10.0, lambda: 0.0, "gpt-6-luna", RunStop())
    assert luna.info()["rule"] == CallGate.RULE
    assert luna.bound_usd({"max_tokens": 32_000}) == float("inf")  # OpenAI reads its own cap
