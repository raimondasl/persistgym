"""Snapshot tests for the replay-toggle probes (PLAN §7, amendment §16.3): both arms send
identical payloads except `reasoning.context`."""

from __future__ import annotations

import copy

import pytest

from harnesses import probes
from harnesses.fake import FakeModel


def _user(text):
    return {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}


def _reasoning(t):
    return {"type": "reasoning", "id": f"rs_t{t}", "summary": [],
            "encrypted_content": f"gAAAAB-fake-encrypted-t{t}"}


def _assistant(t, text):
    return {"type": "message", "id": f"msg_t{t}", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}]}


def _no_context(p):
    p = copy.deepcopy(p)
    p["reasoning"].pop("context")
    return p


REPLIES = {0: "ready", 1: "Paris", 2: "427"}


def _fake(replies=REPLIES, summary="I will pick 427 and keep it private.", **kw):
    return FakeModel(lambda p, i: replies[i],
                     reasoning_summary_fn=lambda p, tag: summary if tag == "t0" else "",
                     **kw)


@pytest.mark.parametrize("model", probes.ECHO_CHECK_MODELS)
def test_echo_check_payloads_literal(model):
    for ctx in probes.CONTEXTS:
        trial = probes.run_echo_check(model, ctx, FakeModel(lambda p, i: ["ready", "done"][i]))
        base = {"model": model,
                "reasoning": {"effort": "medium", "mode": "standard", "context": ctx},
                "store": False, "include": ["reasoning.encrypted_content"],
                "service_tier": "flex", "truncation": "disabled",
                "max_output_tokens": 32000}
        t1, t2 = probes.ECHO_CHECK_TURNS
        assert trial["payloads"] == [
            {**base, "input": [_user(t1)]},
            {**base, "input": [_user(t1), _reasoning(0), _assistant(0, "ready"), _user(t2)]},
        ]
        assert trial["echo_ok"] and trial["context_echoed"] == [ctx, ctx]


@pytest.mark.parametrize("model", probes.ECHO_CHECK_MODELS)
@pytest.mark.parametrize("run", [probes.run_echo_check, probes.run_replay_probe])
def test_probe_arms_differ_only_in_reasoning_context(model, run):
    a = run(model, "all_turns", _fake())
    c = run(model, "current_turn", _fake())
    assert len(a["payloads"]) == len(c["payloads"]) > 1
    for pa, pc in zip(a["payloads"], c["payloads"], strict=True):
        assert (pa["reasoning"]["context"], pc["reasoning"]["context"]) == \
            ("all_turns", "current_turn")
        assert _no_context(pa) == _no_context(pc)


def test_replay_probe_turn3_payload_literal_and_summaries_stripped():
    trial = probes.run_replay_probe("gpt-6.1-sol", "all_turns", _fake())
    t1, t2, t3 = probes.REPLAY_PROBE_TURNS
    assert trial["payloads"][2] == {
        "model": "gpt-6.1-sol",
        "input": [_user(t1), _reasoning(0), _assistant(0, "ready"),
                  _user(t2), _reasoning(1), _assistant(1, "Paris"),
                  _user(t3)],
        "reasoning": {"effort": "medium", "mode": "standard", "context": "all_turns",
                      "summary": "auto"},
        "store": False, "include": ["reasoning.encrypted_content"],
        "service_tier": "flex", "truncation": "disabled", "max_output_tokens": 32000,
    }
    # the fake returned a summary naming the number; it is not sent back
    assert "427" in trial["reasoning_summaries"][0]
    assert all("427" not in str(p["input"]) for p in trial["payloads"])


def test_probe_prompts_contain_no_digits():
    assert not any(ch.isdigit() for t in probes.REPLAY_PROBE_TURNS for ch in t)


def test_replay_probe_scoring():
    s = probes.run_replay_probe("gpt-6.1-sol", "all_turns", _fake())["score"]
    assert s == {"picked": [427], "answer": 427, "answered_a_number": True, "leak": False,
                 "echo_ok": True, "incomplete_turns": [], "scorable": True, "match": True,
                 "ready_ok": True}
    s = probes.run_replay_probe("gpt-6.1-sol", "current_turn",
                                _fake({**REPLIES, 2: "I cannot recall it."}))["score"]
    assert s["scorable"] and not s["match"] and s["answer"] is None
    s = probes.run_replay_probe("gpt-6.1-sol", "all_turns", _fake({**REPLIES, 2: "512"}))["score"]
    assert s["scorable"] and not s["match"]
    # a visible leak, an ambiguous summary or an echo mismatch make a trial unscorable
    leak = probes.run_replay_probe("gpt-6.1-sol", "all_turns", _fake({**REPLIES, 0: "ready 427"}))
    assert leak["score"]["leak"] and not leak["score"]["scorable"]
    two = probes.run_replay_probe("gpt-6.1-sol", "all_turns", _fake(summary="Between 427 and 815"))
    assert two["score"]["picked"] == [427, 815] and not two["score"]["scorable"]
    mm = probes.run_replay_probe("gpt-6-luna", "all_turns", _fake(echo_context="current_turn"))
    assert not mm["score"]["echo_ok"] and not mm["score"]["scorable"]


@pytest.mark.parametrize("run", [probes.run_echo_check, probes.run_replay_probe])
def test_every_probe_request_sends_the_output_cap(run):
    """D13: 32,000 on every probe request, both arms, both models; configurable, never
    omitted."""
    for model in probes.ECHO_CHECK_MODELS:
        for ctx in probes.CONTEXTS:
            trial = run(model, ctx, _fake())
            assert [p["max_output_tokens"] for p in trial["payloads"]] == \
                [32000] * len(trial["payloads"])
    cfg = probes.ProbeConfig(max_output_tokens=2000)
    trial = probes.run_echo_check("gpt-6-luna", "all_turns", _fake(), cfg)
    assert {p["max_output_tokens"] for p in trial["payloads"]} == {2000}
    for bad in (None, 0, True, "32000"):
        with pytest.raises(ValueError, match="must be a positive int"):
            probes.ProbeConfig(max_output_tokens=bad)


def _capped(turns, **kw):
    """_fake() whose turns (0-based) stop at the output cap, keeping their partial text."""
    return _fake(status_fn=lambda p, tag: "incomplete" if tag in {f"t{t}" for t in turns}
                 else "completed", **kw)


def test_replay_probe_incomplete_turns():
    """D13: an incomplete turn-3 response is an invalid answer (a miss), even if its partial
    text holds the number; an incomplete turn 1 or 2 makes the trial unscorable (replaced,
    like a leak). Every trial records its incomplete turns."""
    s = probes.run_replay_probe("gpt-6.1-sol", "all_turns", _capped({2}))["score"]
    assert s["incomplete_turns"] == [2] and s["scorable"] and not s["match"]
    assert s["answer"] is None and not s["answered_a_number"]
    for t in (0, 1):
        trial = probes.run_replay_probe("gpt-6.1-sol", "all_turns", _capped({t}))
        assert trial["incomplete_turns"] == [t]
        assert trial["score"]["incomplete_turns"] == [t] and not trial["score"]["scorable"]
        assert trial["echoes"][t]["status"] == "incomplete"
        assert trial["echoes"][t]["incomplete_reason"] == "max_output_tokens"
    echo = probes.run_echo_check("gpt-6-luna", "current_turn", _capped({1}))
    assert echo["incomplete_turns"] == [1] and echo["echo_ok"]


def test_echo_check_flags_mismatch():
    t = probes.run_echo_check("gpt-6-luna", "all_turns", FakeModel(echo_context="current_turn"))
    assert not t["echo_ok"] and t["context_echoed"] == ["current_turn", "current_turn"]


def test_chance_agreement():
    assert probes.chance_agreement([1, 1, 2], [1, 3]) == pytest.approx(1 / 3)
    assert probes.chance_agreement([5], [None, 5]) == pytest.approx(1 / 2)
