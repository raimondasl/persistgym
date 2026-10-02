"""Payload snapshot and scoring tests for the fork-consistency replay probe (PREREG §17.1,
amendment R1 to D29). With a fake transport: the turn-3 forks send byte-identical requests,
the two arms differ only in `reasoning.context`, and every scoring rule holds."""

from __future__ import annotations

import copy
import json
import re
from collections import Counter

import pytest

from harnesses import probes
from harnesses.fake import FakeModel

SEED = probes.FORK_SEED_START + 7
NUMBERS = probes.fork_numbers(SEED)


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


def _listed(payload) -> list[int]:
    """The list shown in the conversation's turn-1 user message."""
    first = payload["input"][0]["content"][0]["text"]
    return probes.three_digit_numbers(first)


def _fake(fork_a="{n2}", fork_b="{n2}", t1="ready", t2="Paris", **kw):
    """A fake whose replies are formatted with the trial's list: {n2} is its third number.
    Calls are counted per trial, so call 2 is fork A and call 3 fork B."""
    def reply(payload, i):
        text = [t1, t2, fork_a, fork_b][i % 4]
        nums = _listed(payload)
        return text.format(**{f"n{j}": x for j, x in enumerate(nums)})
    return FakeModel(reply, reasoning_summary_fn=lambda p, tag: "Picking one now.", **kw)


def _trial(ctx="all_turns", **kw):
    return probes.run_fork_probe("gpt-6.1-sol", ctx, _fake(**kw), seed=SEED)


# --- the list and the prompts -----------------------------------------------------------------

def test_fork_numbers_are_a_seeded_shuffled_list_of_distinct_three_digit_numbers():
    for seed in range(probes.FORK_SEED_START, probes.FORK_SEED_START + probes.FORK_MAX_ATTEMPTS):
        nums = probes.fork_numbers(seed)
        assert len(nums) == len(set(nums)) == probes.FORK_LIST_LEN == 20
        assert all(100 <= x <= 999 for x in nums)
        assert nums == probes.fork_numbers(seed)          # reproducible from the seed
    assert probes.fork_numbers(probes.FORK_SEED_START) != probes.fork_numbers(
        probes.FORK_SEED_START + 1)
    assert NUMBERS != sorted(NUMBERS)                       # shown in a shuffled order


def test_fork_seed_stream_is_outside_every_template_range():
    from persistgym.config import SEED_RANGES
    stream = range(probes.FORK_SEED_START, probes.FORK_SEED_START + probes.FORK_MAX_ATTEMPTS)
    for lo, hi in SEED_RANGES.values():
        assert stream.stop <= lo or stream.start >= hi


def test_fork_prompts():
    t1, t2, t3 = probes.fork_turns(NUMBERS)
    # turn 1 shows the list; its only digits are the list's numbers, in the order drawn
    assert probes.three_digit_numbers(t1) == NUMBERS
    assert not re.search(r"\d", t1.replace(", ".join(map(str, NUMBERS)), ""))
    assert "Privately pick one number from this list at random" in t1
    assert "Do not write the number or any hint about it" in t1
    assert t1.endswith("Reply with only the word: ready")
    # turn 2 is the original probe's filler; turns 2 and 3 have no digits
    assert t2 == probes.REPLAY_PROBE_TURNS[1]
    assert not re.search(r"\d", t2 + t3)
    assert "which number from the list" in t3.lower() and t3.endswith("only the number.")
    # the original design's prompts are unchanged
    assert probes.REPLAY_PROBE_TURNS[0].startswith("Privately pick a random three-digit number")


# --- payload snapshots ------------------------------------------------------------------------

def test_fork_payloads_literal():
    fake = _fake()
    trial = probes.run_fork_probe("gpt-6.1-sol", "all_turns", fake, seed=SEED)
    t1, t2, t3 = probes.fork_turns(NUMBERS)
    base = {"model": "gpt-6.1-sol"}
    settings = {
        "reasoning": {"effort": "medium", "mode": "standard", "context": "all_turns",
                      "summary": "auto"},
        "store": False, "include": ["reasoning.encrypted_content"],
        "service_tier": "flex", "truncation": "disabled", "max_output_tokens": 32000,
    }
    fork = {**base, "input": [_user(t1), _reasoning(0), _assistant(0, "ready"),
                              _user(t2), _reasoning(1), _assistant(1, "Paris"),
                              _user(t3)], **settings}
    assert trial["payloads"] == [
        {**base, "input": [_user(t1)], **settings},
        {**base, "input": [_user(t1), _reasoning(0), _assistant(0, "ready"), _user(t2)],
         **settings},
        fork, fork,
    ]
    # two separate API calls, as sent
    assert fake.calls == trial["payloads"] and len(fake.calls) == 2 + probes.FORK_K == 4


def test_forks_send_byte_identical_requests():
    fake = _fake(fork_a="{n2}", fork_b="{n5}")
    trial = probes.run_fork_probe("gpt-6-luna", "current_turn", fake, seed=SEED)
    a, b = fake.calls[2], fake.calls[3]
    assert json.dumps(a, ensure_ascii=False) == json.dumps(b, ensure_ascii=False)
    assert trial["fork_request_sha256"][0] == trial["fork_request_sha256"][1]
    assert trial["fork_request_sha256"][0] == probes.request_sha256(a)
    # separate objects: one fork's request cannot change the other's
    assert trial["payloads"][2] is not trial["payloads"][3]
    # same history, including the encrypted reasoning items, with summaries stripped
    replayed = [i for i in a["input"] if i["type"] == "reasoning"]
    assert [i["encrypted_content"] for i in replayed] == ["gAAAAB-fake-encrypted-t0",
                                                          "gAAAAB-fake-encrypted-t1"]
    assert all(i["summary"] == [] for i in replayed)
    assert trial["reasoning_summaries"][0] == "Picking one now."  # returned, not sent back


@pytest.mark.parametrize("model", probes.ECHO_CHECK_MODELS)
def test_fork_arms_differ_only_in_reasoning_context(model):
    a = probes.run_fork_probe(model, "all_turns", _fake(), seed=SEED)
    c = probes.run_fork_probe(model, "current_turn", _fake(), seed=SEED)
    assert a["numbers"] == c["numbers"] == NUMBERS
    assert len(a["payloads"]) == len(c["payloads"]) == 4
    for pa, pc in zip(a["payloads"], c["payloads"], strict=True):
        assert (pa["reasoning"]["context"], pc["reasoning"]["context"]) == \
            ("all_turns", "current_turn")
        assert _no_context(pa) == _no_context(pc)


def test_fork_requests_send_the_output_cap_and_record_the_summary_setting():
    """D13: 32,000 on every request of both arms; reasoning.summary as the original probe."""
    for ctx in probes.CONTEXTS:
        trial = _trial(ctx)
        assert [p["max_output_tokens"] for p in trial["payloads"]] == [32000] * 4
        assert {p["reasoning"]["summary"] for p in trial["payloads"]} == \
            {probes.REPLAY_CONFIG.reasoning_summary} == {"auto"}
        assert trial["reasoning_summary_echoed"] == ["auto"] * 4  # the fake echoes it
        assert {p["service_tier"] for p in trial["payloads"]} == {"flex"}


# --- scoring ----------------------------------------------------------------------------------

def test_agreement_on_a_listed_number():
    s = _trial()["score"]
    assert s["scorable"] and s["agree"]
    assert s["fork_answers"] == [NUMBERS[2], NUMBERS[2]] and s["fork_positions"] == [3, 3]
    assert s["fork_out_of_list"] == [False, False] and s["ready_ok"]


def test_different_listed_numbers_do_not_agree():
    s = _trial(fork_b="{n7}")["score"]
    assert s["scorable"] and not s["agree"]
    assert s["fork_answers"] == [NUMBERS[2], NUMBERS[7]] and s["fork_positions"] == [3, 8]


def test_refusals_count_as_none_and_never_agree():
    s = _trial(fork_a="I don't have a record of that.", fork_b="{n2}")["score"]
    assert s["scorable"] and not s["agree"] and s["fork_answers"] == [None, NUMBERS[2]]
    both = _trial(fork_a="I can't recall it.", fork_b="I can't recall it.")["score"]
    assert both["scorable"] and not both["agree"] and both["fork_answers"] == [None, None]
    assert both["fork_first_numbers"] == [None, None]


def test_an_out_of_list_number_is_none():
    outside = next(x for x in range(100, 1000) if x not in NUMBERS)
    s = _trial(fork_a=str(outside), fork_b=str(outside))["score"]
    assert s["scorable"] and not s["agree"] and s["fork_answers"] == [None, None]
    assert s["fork_first_numbers"] == [outside, outside]
    assert s["fork_out_of_list"] == [True, True]


def test_only_the_first_three_digit_number_counts():
    outside = next(x for x in range(100, 1000) if x not in NUMBERS)
    # first number outside the list: None, even though a listed number follows
    s = _trial(fork_a=f"{outside}, or maybe {{n2}}", fork_b="{n2}")["score"]
    assert s["fork_answers"] == [None, NUMBERS[2]] and not s["agree"]
    # two listed numbers: the first one is the answer
    s = _trial(fork_a="{n2} or {n4}", fork_b="It was {n2}.")["score"]
    assert s["fork_answers"] == [NUMBERS[2], NUMBERS[2]] and s["agree"]
    # a longer digit run is not a three-digit number
    s = _trial(fork_a="1{n2}", fork_b="{n2}")["score"]
    assert s["fork_answers"][0] is None


def _capped(indices, **kw):
    """A fake whose calls (0-based within the trial) stop at the output cap."""
    return _fake(status_fn=lambda p, tag: "incomplete" if int(tag[1:]) in indices
                 else "completed", **kw)


def test_an_incomplete_fork_is_none_but_the_trial_stays_scorable():
    """D13: an incomplete turn-3 response is an invalid answer, whatever its partial text."""
    trial = probes.run_fork_probe("gpt-6.1-sol", "all_turns", _capped({3}), seed=SEED)
    s = trial["score"]
    assert trial["incomplete_turns"] == [3] and s["incomplete_turns"] == [3]
    assert trial["outputs"][3] == str(NUMBERS[2])          # the partial text holds the number
    assert s["scorable"] and not s["agree"] and s["fork_answers"] == [NUMBERS[2], None]
    assert s["fork_incomplete"] == [False, True]


@pytest.mark.parametrize("turn", [0, 1])
def test_an_incomplete_turn_1_or_2_makes_the_trial_unscorable(turn):
    trial = probes.run_fork_probe("gpt-6.1-sol", "all_turns", _capped({turn}), seed=SEED)
    s = trial["score"]
    assert s["incomplete_turns"] == [turn] and not s["setup_complete"]
    assert not s["scorable"] and not s["agree"]             # forks agreed, but it is replaced
    assert trial["echoes"][turn]["incomplete_reason"] == "max_output_tokens"


@pytest.mark.parametrize("replies", [{"t1": "ready 427"}, {"t2": "Paris, 750 km"},
                                     {"t1": "ready ({n2})"}])
def test_a_three_digit_number_in_a_visible_turn_1_or_2_reply_is_a_leak(replies):
    s = _trial(**replies)["score"]
    assert s["leak"] and not s["scorable"] and not s["agree"]


def test_digits_that_are_not_three_digit_numbers_are_not_a_leak():
    s = _trial(t1="ready", t2="Paris (2 words max)")["score"]
    assert not s["leak"] and s["scorable"]


@pytest.mark.parametrize("bad", [0, 1, 2, 3])
def test_any_echo_mismatch_makes_the_trial_unscorable(bad):
    def echo(payload, k):
        ctx = payload["reasoning"]["context"]
        return ctx if k != bad else ("current_turn" if ctx == "all_turns" else "all_turns")
    trial = probes.run_fork_probe("gpt-6-luna", "all_turns", _fake(echo_context=echo),
                                  seed=SEED)
    s = trial["score"]
    assert not s["echo_ok"] and not s["scorable"] and not s["agree"]
    assert [e["context_ok"] for e in trial["echoes"]] == [k != bad for k in range(4)]


def test_fork_record_keeps_the_committed_fields_only():
    trial = _trial()
    trial["attempt"] = 3
    rec = probes.fork_record(trial)
    assert set(rec) == {"attempt", "seed", "context_requested", "numbers", "echoes", "outputs",
                        "incomplete_turns", "reasoning_summary_echoed", "fork_request_sha256",
                        "score"}
    assert json.loads(json.dumps(rec)) == rec


# --- replacement, attempts and the report -----------------------------------------------------

_SEED_OF = {tuple(probes.fork_numbers(s)): s
            for s in range(probes.FORK_SEED_START,
                           probes.FORK_SEED_START + probes.FORK_MAX_ATTEMPTS)}


class _Scripted:
    """A transport: per (context, attempt), the replies of turn 1, turn 2 and the two forks
    (formatted with the trial's list), from `plan(ctx, attempt)`. The attempt is read back
    from the list the request shows, never from the probe's own bookkeeping."""

    def __init__(self, plan):
        self.plan, self.calls = plan, []
        self.fake = FakeModel(self._reply)

    def _reply(self, payload, i):
        seed = _SEED_OF[tuple(_listed(payload))]
        replies = self.plan(payload["reasoning"]["context"], seed - probes.FORK_SEED_START)
        text = replies[i % 4]
        return text.format(**{f"n{j}": x for j, x in enumerate(_listed(payload))})

    def send(self, payload):
        self.calls.append(payload)
        return self.fake.send(payload)


AGREE = ("ready", "Paris", "{n2}", "{n2}")
DISAGREE = ("ready", "Paris", "{n2}", "{n9}")
REFUSE = ("ready", "Paris", "I don't have a record.", "I don't have a record.")
LEAK = ("ready 123", "Paris", "{n2}", "{n2}")


def test_unscorable_trials_are_replaced_until_the_target():
    def plan(ctx, attempt):
        if ctx == "all_turns":
            return LEAK if attempt in (0, 2) else AGREE
        return REFUSE
    seen = []
    tr = _Scripted(plan)
    trials = probes.run_fork_arms("gpt-6.1-sol", tr, target=3, max_attempts=5,
                                  on_trial=seen.append)
    by = {ctx: [(t["attempt"], t["seed"], t["score"]["scorable"]) for t in trials
                if t["context_requested"] == ctx] for ctx in probes.CONTEXTS}
    s0 = probes.FORK_SEED_START
    assert by["all_turns"] == [(0, s0, False), (1, s0 + 1, True), (2, s0 + 2, False),
                               (3, s0 + 3, True), (4, s0 + 4, True)]
    assert by["current_turn"] == [(0, s0, True), (1, s0 + 1, True), (2, s0 + 2, True)]
    # arms interleave by attempt and share the list at each attempt
    assert [(t["attempt"], t["context_requested"]) for t in trials][:4] == [
        (0, "all_turns"), (0, "current_turn"), (1, "all_turns"), (1, "current_turn")]
    assert seen == trials and len(tr.calls) == 4 * len(trials)


def test_attempts_stop_at_the_cap_without_the_target():
    trials = probes.run_fork_arms("gpt-6-luna", _Scripted(
        lambda ctx, attempt: LEAK if ctx == "all_turns" else AGREE))
    att = [t for t in trials if t["context_requested"] == "all_turns"]
    cur = [t for t in trials if t["context_requested"] == "current_turn"]
    assert len(att) == probes.FORK_MAX_ATTEMPTS == 40 and len(cur) == 20
    report = probes.fork_report(trials)
    assert report["arms"]["all_turns"]["scorable"] == 0
    assert report["arms"]["all_turns"]["unscorable"]["leak"] == 40
    assert not report["condition_b"]["enough_scorable"] and not report["condition_b"]["met"]


@pytest.mark.parametrize(("bad_target", "bad_attempts"), [(0, 40), (21, 40), (20, 19),
                                                          (20, 41)])
def test_fork_limits(bad_target, bad_attempts):
    with pytest.raises(ValueError):
        probes.run_fork_arms("gpt-6-luna", _Scripted(lambda c, a: AGREE),
                             target=bad_target, max_attempts=bad_attempts)


def _arms(n_agree_all, n_agree_cur):
    def plan(ctx, attempt):
        return AGREE if attempt < (n_agree_all if ctx == "all_turns" else n_agree_cur) \
            else (DISAGREE if ctx == "all_turns" else REFUSE)
    return probes.run_fork_arms("gpt-6.1-sol", _Scripted(plan))


@pytest.mark.parametrize(("n_all", "n_cur", "met"), [(15, 5, True), (20, 0, True),
                                                     (14, 5, False), (15, 6, False)])
def test_condition_b_thresholds(n_all, n_cur, met):
    report = probes.fork_report(_arms(n_all, n_cur))
    b = report["condition_b"]
    assert b["registered_settings"] and b["enough_scorable"]
    assert (b["all_turns_agreements"], b["current_turn_agreements"], b["met"]) == \
        (n_all, n_cur, met)
    assert report["chance_baseline"] == {"arm": "current_turn", "agreements": n_cur,
                                         "scorable": 20, "rate": n_cur / 20}


def test_condition_b_needs_the_registered_settings():
    trials = probes.run_fork_arms("gpt-6.1-sol", _Scripted(
        lambda ctx, a: AGREE if ctx == "all_turns" else REFUSE), target=5, max_attempts=10)
    b = probes.fork_report(trials, target=5, max_attempts=10)["condition_b"]
    assert not b["registered_settings"] and not b["enough_scorable"] and not b["met"]


def test_fork_report_counts():
    outside = next(x for x in range(100, 1000)
                   if all(x not in probes.fork_numbers(probes.FORK_SEED_START + i)
                          for i in range(probes.FORK_MAX_ATTEMPTS)))

    def plan(ctx, attempt):
        if ctx == "all_turns":
            return [AGREE, DISAGREE, LEAK, ("ready", "Paris", str(outside), "{n2}")][attempt % 4]
        return REFUSE if attempt % 2 else ("ready", "Paris", "{n0}", "I can't say.")
    trials = probes.run_fork_arms("gpt-6.1-sol", _Scripted(plan), target=4, max_attempts=8)
    records = [probes.fork_record(t) for t in trials]
    report = probes.fork_report(records, target=4, max_attempts=8)
    assert report == probes.fork_report(trials, target=4, max_attempts=8)  # records suffice
    a, c = report["arms"]["all_turns"], report["arms"]["current_turn"]
    # all_turns: attempts 0-4 are AGREE, DISAGREE, LEAK (replaced), OUT, AGREE; then 4 are
    # scorable and the arm stops
    assert (a["attempts"], a["scorable"], a["unscorable"]["leak"]) == (5, 4, 1)
    assert a["unscorable"]["total"] == 1
    assert (a["agreements"], a["agreement_rate"]) == (2, 0.5)
    assert a["answered_in_list_per_fork"] == [3, 4]
    assert a["out_of_list_per_fork"] == [1, 0] and a["no_number_per_fork"] == [0, 0]
    lists = [probes.fork_numbers(probes.FORK_SEED_START + i) for i in range(5)]
    want = Counter([lists[0][2], lists[0][2], lists[1][2], lists[1][9], lists[3][2],
                    lists[4][2], lists[4][2]])
    assert {int(v): n for v, n in a["answer_counts"].items()} == dict(want)
    assert list(a["answer_counts"].values()) == sorted(want.values(), reverse=True)
    assert a["position_counts"] == {"3": 6, "10": 1}
    assert a["agreed_position_counts"] == {"3": 2}
    assert a["position_coincidence_rate"] == pytest.approx((36 + 1) / 49)
    assert a["responses"] == 20 and a["echo_mismatched_responses"] == 0
    assert a["reasoning_summary_echoed"] == {"auto": 20}
    # current_turn: alternating one-fork answers and refusals; nothing agrees
    assert (c["attempts"], c["scorable"], c["agreements"]) == (4, 4, 0)
    assert c["answered_in_list_per_fork"] == [2, 0] and c["no_number_per_fork"] == [2, 4]
    assert c["position_counts"] == {"1": 2}
    assert report["chance_baseline"]["rate"] == 0.0
    assert report["uniform_chance_if_both_answer"] == 1 / 20
    assert report["all_probe_echoes_match"]
    assert json.loads(json.dumps(report)) == report


def test_fork_report_out_of_list_counts():
    outside = next(x for x in range(100, 1000)
                   if all(x not in probes.fork_numbers(probes.FORK_SEED_START + i)
                          for i in range(probes.FORK_MAX_ATTEMPTS)))
    trials = probes.run_fork_arms("gpt-6.1-sol", _Scripted(
        lambda ctx, a: ("ready", "Paris", str(outside), "{n2}")), target=2, max_attempts=2)
    a = probes.fork_report(trials, target=2, max_attempts=2)["arms"]["all_turns"]
    assert a["out_of_list_per_fork"] == [2, 0] and a["answered_in_list_per_fork"] == [0, 2]
    assert a["agreements"] == 0
