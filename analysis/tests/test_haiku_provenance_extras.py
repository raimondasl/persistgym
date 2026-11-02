"""analysis.haiku_provenance_extras on small made-up records and transcripts. $0."""

import gzip
import json

import pytest

from analysis import haiku_provenance_extras as hpe


def _record(cell="observed-nonrec-far", correct=False, carried=True, incomplete=(), requests=5):
    return {"task_cell": cell, "need_correct": correct, "n_requests": requests,
            "incomplete": list(incomplete),
            "need_payload": {"assistant_carried": {"carried": carried}},
            "designed": {"evidence_steps": [1], "gap_steps_latest": 2}}


def _refusal(turn, at_need=0, reason="refusal:bio"):
    return {"turn": turn, "pending_step": turn, "at_need": at_need, "reason": reason}


def test_turn_bins():
    assert [hpe.turn_bin(t) for t in (0, 4, 5, 9, 10, 14, 15, 30)] == [
        "0-4", "0-4", "5-9", "5-9", "10-14", "10-14", "15 on", "15 on"]


def test_the_failures_split_by_carried_and_by_a_refusal_at_the_need_step():
    r = hpe.record_readings([
        _record(carried=True, incomplete=[_refusal(9, at_need=1)]),
        _record(carried=True),
        _record(carried=False, cell="derived-nonrec-far"),
        _record(carried=False, incomplete=[_refusal(9, at_need=1)]),
        _record(carried=True, correct=True),
    ])
    both = r["failures"]["both"]
    assert both["failed"] == 4
    assert both["carried, refused at the need step"] == 1
    assert both["carried, no refusal at the need step"] == 1
    assert both["not carried, no refusal at the need step"] == 1
    assert both["not carried, refused at the need step"] == 1
    assert r["failures"]["derived-nonrec-far"] == {
        "failed": 1, "not carried, no refusal at the need step": 1}


def test_refusals_are_counted_per_response_and_by_turn():
    r = hpe.record_readings([
        _record(cell="observed-rec-far", correct=True, requests=10,
                incomplete=[_refusal(2), _refusal(16), {"turn": 3, "reason": "max_tokens"}]),
        _record(requests=10, incomplete=[_refusal(7)]),
    ])
    assert (r["responses"], r["refused_responses"]) == (20, 3)
    assert r["refused_share"] == pytest.approx(0.15)
    assert r["refused_by_turn"] == {"0-4": 1, "5-9": 1, "10-14": 0, "15 on": 1}
    assert r["refusal_categories"] == {"refusal:bio": 3}


def test_recoverable_episodes_enter_neither_split():
    r = hpe.record_readings([_record(cell="derived-rec-far", incomplete=[_refusal(4)])])
    assert r["failures"]["both"] == {}
    assert r["success_by_refusal"]["both"] == {}


def test_success_is_split_by_where_a_refusal_fell():
    # the need step of `_record` is 3 (last evidence step 1, gap 2)
    r = hpe.record_readings([
        _record(correct=True, incomplete=[_refusal(2)]),
        _record(correct=False, incomplete=[_refusal(2)]),
        _record(correct=True),
        _record(correct=False, incomplete=[_refusal(2), _refusal(3, at_need=1)]),
    ])
    assert r["success_by_refusal"]["both"] == {
        "no refusal up to the need step: episodes": 1,
        "no refusal up to the need step: success": 1,
        "refused at the need step: episodes": 1, "refused at the need step: success": 0,
        "refused before the need step only: episodes": 2,
        "refused before the need step only: success": 1}


def test_a_refusal_after_the_need_step_does_not_count_as_before_it():
    r = hpe.record_readings([_record(correct=True, incomplete=[_refusal(4)])])
    assert r["success_by_refusal"]["both"] == {
        "no refusal up to the need step: episodes": 1,
        "no refusal up to the need step: success": 1}


FACT = {"target": 568, "label": "I", "clues": [79, 558]}


def _payload(system="Follow the rules.", users=("first obs", "pick:\nA) 12\nI) 568\n"),
             replies=("noted 568",)):
    msgs = []
    for i, u in enumerate(users):
        msgs.append({"role": "user", "content": u})
        if i < len(replies):
            msgs.append({"role": "assistant", "content": [{"type": "text", "text": replies[i]}]})
    return {"system": system, "messages": msgs}


def test_a_clean_need_request_has_the_value_only_in_its_option_line_and_the_replies():
    r = hpe.need_request_reading(_payload(), FACT)
    assert r == {"target_in_system": 0, "target_in_earlier_user": 0,
                 "target_in_need_option_line": 1, "target_in_need_elsewhere": 0,
                 "clue_outside_replies": 0, "n_replies": 1, "reply_chars": len("noted 568")}


@pytest.mark.parametrize("payload,key", [
    (_payload(system="The answer is 568."), "target_in_system"),
    (_payload(users=("update: 568", "pick:\nI) 568\n")), "target_in_earlier_user"),
    (_payload(users=("x", "it is 568\nI) 568\n")), "target_in_need_elsewhere"),
    (_payload(users=("offset 79", "pick:\nI) 568\n")), "clue_outside_replies"),
])
def test_a_leak_is_counted_where_it_is(payload, key):
    assert hpe.need_request_reading(payload, FACT)[key] == 1


def test_the_value_is_matched_as_a_whole_word():
    r = hpe.need_request_reading(_payload(users=("v5680", "pick:\nI) 568\n")), FACT)
    assert r["target_in_earlier_user"] == 0


def _line(step, *, payload=None, thinking=False, text="x", stop="end_turn", eid="e1", kind="step"):
    content = ([{"type": "thinking", "thinking": ""}] if thinking else []) + [
        {"type": "text", "text": text}]
    return {"episode_id": eid, "kind": kind, "pending_step": step, "is_lookup_result": False,
            "payload": payload or _payload(),
            "response": {"content": content, "stop_reason": stop}}


@pytest.fixture
def transcript(tmp_path):
    lines = [
        _line(0, thinking=True),
        _line(1, thinking=True, text="saw 568"),         # the evidence step
        _line(2, text="still 568", stop="refusal"),      # refused: left out of the held share
        _line(2, text="no value here"),                  # a later request at the step
        _line(3, thinking=False),                        # the need step's first request
        _line(3, thinking=True),                         # a later request at the need step
        _line(0, eid="other"),                           # not this run's counted record
    ]
    path = tmp_path / "t.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for x in lines:
            f.write(json.dumps(x) + "\n")
    return path


def test_the_transcript_tallies(transcript):
    t = hpe.transcript_readings(transcript, {"e1": _record()}, {"e1": FACT})
    assert t["responses"] == 6
    assert t["thinking"] == 3
    assert dict(t["turn_first"]) == {0: 1, 1: 1, 2: 1, 3: 1}
    assert dict(t["turn_thinking"]) == {0: 1, 1: 1, 2: 0, 3: 0}
    assert t["later_need_requests"]["observed-nonrec-far"] == 1
    assert t["need"]["e1"]["target_in_need_option_line"] == 1
    # steps 1 and 2 lie in the span; step 2's first response was refused, so only step 1 counts
    assert t["held"]["e1"] == [1, 1]
    assert set(t["user_hash"]) == {"e1#0", "e1#1", "e1#2", "e1#3"}


def test_merge_adds_up_an_arms_runs(transcript):
    t = hpe.transcript_readings(transcript, {"e1": _record()}, {"e1": FACT})
    m = hpe.merge([t, t])
    assert m["responses"] == 12
    assert m["later_need_requests"]["observed-nonrec-far"] == 2
    assert m["need"] == t["need"]


def test_the_arm_summary_pools_turns_and_cells(transcript):
    records = {"e1": _record()}
    t = hpe.transcript_readings(transcript, records, {"e1": FACT})
    s = hpe.arm_transcript_summary(t, records)
    assert s["thinking_share"] == pytest.approx(0.5)
    assert s["first_requests_by_turn_bin"]["0-4"] == [2, 4]
    assert s["first_requests_by_turn"]["0"] == [1, 1]
    cell = s["fact_value_in_replies"]["observed-nonrec-far"]
    assert (cell["replies_holding_value"], cell["replies"]) == (1, 1)
    assert s["leak_check"]["observed-nonrec-far"]["target_in_need_option_line"] == 1
    assert s["at_need"]["observed-nonrec-far"]["episodes"] == 1
    assert s["at_need"]["derived-nonrec-far"]["episodes"] == 0
