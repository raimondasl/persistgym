"""D8 need-phase tokens and D12 compacted_between (fake model, no network).

Expected values are recomputed from the raw transcript events (what was sent and returned at
which pending step), not from the runner's own running sums."""

from __future__ import annotations

import pytest

from harnesses.cells import CELLS
from harnesses.config import HarnessConfig
from harnesses.fake import FakeModel, padded_text
from harnesses.items import item_text
from harnesses.runner import run_episode
from harnesses.tests.conftest import SMALL
from persistgym.episode import ALL_CELLS
from persistgym.render import generate

CFG = HarnessConfig()
SUMMARY_CELLS = [c for c in CELLS if CELLS[c].history == "summary"]


def _events(ep, cid, fake=None, cfg=CFG):
    events = []
    run = run_episode(ep, CELLS[cid], cfg, fake or FakeModel(), recorder=events.append)
    return run, events


def _need_tokens(ep, events):
    """D8 from the transcript: input + output tokens of every call made while the need step
    was pending."""
    need = [e for e in events if e["pending_step"] == ep.need_step]
    u = [e["response"]["usage"] for e in need]
    return need, sum(x["input_tokens"] + x["output_tokens"] for x in u)


def _long_replies(n_tokens):
    return lambda p, i: padded_text("Notes.", n_tokens) + "\nACTION: ack(none)"


def _lookup_at_need(ep):
    def reply(payload, i):
        last = item_text(payload["input"][-1])
        if "needs its" in last and "LOOKUP RESULT" not in last:
            return f"ACTION: lookup({ep.entity})"
        return "ACTION: ack(none)"
    return reply


# --- D8 ---------------------------------------------------------------------------------

@pytest.mark.parametrize("cid", ["F-0", "W-0", "W-n-r", "Σ-n-0"])
def test_need_phase_tokens_match_the_transcript(small_eps, cid):
    for ep in small_eps:
        run, events = _events(ep, cid)
        need, tokens = _need_tokens(ep, events)
        n = run.need_phase
        assert n["complete"] is True and n["n_calls"] == len(need) >= 1
        assert n["tokens"] == tokens == n["input_tokens"] + n["output_tokens"]
        assert n["reasoning_tokens"] == sum(
            e["response"]["usage"]["output_tokens_details"]["reasoning_tokens"] for e in need)
        assert n["reasoning_tokens"] <= n["output_tokens"]  # output includes reasoning
        first = next(e for e in need if e["kind"] == "step")
        assert n["first_step_call"]["reasoning_tokens"] == (
            first["response"]["usage"]["output_tokens_details"]["reasoning_tokens"])
        assert n["first_step_call"]["input_tokens"] == first["response"]["usage"]["input_tokens"]


def test_need_phase_includes_lookup_round_trips(small_eps):
    """Every call from the first call at the need step through the call that returns the
    scored action, lookups included."""
    ep = next(e for e in small_eps if e.cell.id == "observed-rec-far")
    for cid in ("W-0", "F-0"):
        run, events = _events(ep, cid, FakeModel(_lookup_at_need(ep)))
        need, tokens = _need_tokens(ep, events)
        n = run.need_phase
        assert run.n_lookups == 1 and n["complete"]
        assert (n["n_calls"], n["n_step_calls"], n["n_lookup_result_calls"]) == (2, 2, 1)
        assert n["tokens"] == tokens
        first = need[0]["response"]["usage"]
        assert n["tokens"] > first["input_tokens"] + first["output_tokens"]
        # the need phase is one contiguous run of calls, ending with the scored action
        idx = [events.index(e) for e in need]
        assert idx == list(range(idx[0], idx[0] + len(idx)))
        assert all(e["pending_step"] > ep.need_step for e in events[idx[-1] + 1:])
        assert "lookup" not in item_text(need[-1]["response"]["output"][1])  # scored action


def test_need_phase_includes_a_summary_fired_at_the_need_step(small_eps):
    """With 250-token replies, template 0's near Σ episodes compact at the need step itself.
    The summary call is a call at the need step: it is in `tokens` and also in
    `summary_tokens`, so the reading that leaves it out is tokens - summary_tokens."""
    seen = 0
    for ep in (e for e in small_eps if e.template_id == small_eps[0].template_id):
        run, events = _events(ep, "Σ-n-0", FakeModel(_long_replies(250)))
        if not any(c["at_step"] == ep.need_step for c in run.compactions):
            continue
        seen += 1
        need, tokens = _need_tokens(ep, events)
        n = run.need_phase
        assert [e["kind"] for e in need] == ["summary", "step"]
        assert n["n_summary_calls"] == 1 and n["tokens"] == tokens
        s = need[0]["response"]["usage"]
        assert n["summary_tokens"] == s["input_tokens"] + s["output_tokens"] > 0
        step = need[1]["response"]["usage"]
        assert n["tokens"] - n["summary_tokens"] == step["input_tokens"] + step["output_tokens"]
        assert n["first_step_call"]["input_tokens"] == step["input_tokens"]
        # D12: this summary is applied to the payload of the need step's first call, so the
        # agent first saw the need-step observation after it: it counts
        (c,) = [c for c in run.compactions if c["at_step"] == ep.need_step]
        assert c["at_lookup_result"] == 0 and run.compacted_between == 1
    assert seen >= 1


def test_need_phase_incomplete_or_absent_when_the_episode_stops(small_eps):
    ep = small_eps[0]
    # mismatch on the need step's first call: the phase starts but never returns the action
    fake = FakeModel(echo_context=lambda p, k: "current_turn" if k == ep.need_step
                     else "all_turns")
    run = run_episode(ep, CELLS["F-r"], CFG, fake)
    assert run.exit_reason == "REASONING_CONTEXT_MISMATCH"
    assert run.need_phase["n_calls"] == 1 and run.need_phase["complete"] is False
    # stopped before the need step: no need phase at all
    run = run_episode(ep, CELLS["F-r"], CFG, FakeModel(echo_context="current_turn"))
    assert run.need_phase is None


# --- D12 --------------------------------------------------------------------------------

def _expected_between(ep, events):
    """D12 from the transcript: 1 iff a summary call fired (and succeeded) after the first
    evidence step and before the agent first saw the need-step observation, i.e. at a
    pending step s with r_first < s < n, or at s = n before the first need-step call (not
    while a lookup result at n was pending)."""
    r_first = min(c.step for c in ep.components if c.step is not None)
    n = ep.need_step
    return int(any(r_first < e["pending_step"] < n
                   or (e["pending_step"] == n and not e["is_lookup_result"])
                   for e in events if e["kind"] == "summary"))


def _long_replies_with_lookups_at_need(ep, n_tokens):
    """Long replies, and a lookup in reply to every presentation of the need step (the
    environment allows 3; the 4th reply is the scored action)."""
    def reply(payload, i):
        last = item_text(payload["input"][-1])
        action = (f"lookup({ep.entity})" if "needs its" in last else "ack(none)")
        return padded_text("Notes.", n_tokens) + f"\nACTION: {action}"
    return reply


@pytest.mark.parametrize("reply_tokens, lookups", [(None, False), (150, False),
                                                   (250, False), (150, True), (400, True)])
def test_compacted_between_matches_the_transcript(small_eps, reply_tokens, lookups):
    def fake(ep):
        if lookups:
            return FakeModel(_long_replies_with_lookups_at_need(ep, reply_tokens))
        return FakeModel(_long_replies(reply_tokens)) if reply_tokens else FakeModel()
    values = {"near": set(), "far": set()}
    for ep in small_eps:
        for cid in SUMMARY_CELLS:
            run, events = _events(ep, cid, fake(ep))
            assert run.compacted_between == _expected_between(ep, events)
            summaries = [e for e in events if e["kind"] == "summary"]
            assert [c["at_step"] for c in run.compactions] == [
                e["pending_step"] for e in summaries]
            assert [c["at_lookup_result"] for c in run.compactions] == [
                int(e["is_lookup_result"]) for e in summaries]
            values[ep.cell.distance].add(run.compacted_between)
    # far evidence always passes through a summary by the need step (PREREG §2.7)
    assert values["far"] == {1}
    if reply_tokens == 150:
        assert values["near"] == {0, 1}  # the near case really is measured, not designed


def test_a_compaction_during_a_lookup_at_the_need_step_does_not_count(small_eps):
    """D12: the agent first saw the need-step observation before such a summary fired, so it
    does not set compacted_between; it is marked at_lookup_result = 1. Template 0's
    recoverable near Σ episodes with 150-token replies and lookups at the need step compact
    at step 11 (before the evidence) and during a lookup round-trip at the need step 20."""
    seen = 0
    for ep in small_eps:
        if ep.template_id != small_eps[0].template_id or ep.cell.id != "observed-rec-near":
            continue
        for cid in SUMMARY_CELLS:
            run, events = _events(ep, cid,
                                  FakeModel(_long_replies_with_lookups_at_need(ep, 150)))
            r_first, n = min(ep.reveal_steps), ep.need_step
            at_lookup = [c for c in run.compactions
                         if c["at_step"] == n and c["at_lookup_result"] == 1]
            assert run.n_lookups == 3 and at_lookup
            # the reading D12 no longer uses would count it
            assert any(r_first < c["at_step"] <= n for c in run.compactions)
            assert run.compacted_between == 0 == _expected_between(ep, events)
            assert run.need_payload["S"] is True  # the need step showed the evidence verbatim
            seen += 1
    assert seen == len(SUMMARY_CELLS)


def test_compacted_between_only_in_summary_cells(small_eps):
    for ep in small_eps[:8]:
        for cid in CELLS:
            run = run_episode(ep, CELLS[cid], CFG, FakeModel())
            if CELLS[cid].history == "summary":
                assert run.compacted_between in (0, 1)
            else:
                assert run.compacted_between is None and run.compactions == []


def test_compacted_between_unset_without_evidence_or_need_step():
    withheld = [ep for _, eps in generate("main", range(1), SMALL, ALL_CELLS, ("withheld",))
                for ep in eps]
    for ep in withheld:
        assert ep.reveal_steps == []
        assert run_episode(ep, CELLS["Σ-n-0"], CFG, FakeModel()).compacted_between is None
    base = next(ep for _, eps in generate("main", range(1), SMALL, ALL_CELLS, ("base",))
                for ep in eps if ep.cell.distance == "far")
    # every summary fails: the episode ends (AGENT_ERROR) before the need step is presented
    run = run_episode(base, CELLS["Σ-n-0"], CFG, FakeModel(summary_fn=lambda p, j: ""))
    assert run.exit_reason == "AGENT_ERROR" and run.need_payload is None
    assert run.compacted_between is None


def test_compaction_step_is_the_pending_step_not_the_turn(small_eps):
    """Lookups add turns, so a compaction after a lookup has at_turn = at_step + 1, and D12
    uses the step. Here the agent looks up at step 2 (allowed at any step in a recoverable
    cell)."""
    ep = next(e for e in small_eps if e.cell.id == "observed-rec-far")

    def reply(payload, i):
        return f"ACTION: lookup({ep.entity})" if i == 2 else "ACTION: ack(none)"

    run, events = _events(ep, "Σ-n-0", FakeModel(reply))
    assert run.n_lookups == 1 and run.compactions
    assert all(c["at_turn"] == c["at_step"] + 1 for c in run.compactions)
    assert all(c["at_lookup_result"] == 0 for c in run.compactions)
    assert [c["at_step"] for c in run.compactions] == [
        e["pending_step"] for e in events if e["kind"] == "summary"]
    assert run.compacted_between == _expected_between(ep, events) == 1
