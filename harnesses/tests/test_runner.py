"""Runner and real-episode tests (generated persistgym episodes, fake model, no network)."""

from __future__ import annotations

import gzip
import json
import re

import openai
import pytest

from common import runmeta
from harnesses.cells import CELLS
from harnesses.config import HarnessConfig
from harnesses.fake import FakeModel, padded_text
from harnesses.items import item_text
from harnesses.runner import run_batch, run_episode
from persistgym.episode import Episode
from persistgym.survival import reference_window_payload

CFG = HarnessConfig()


def _record():
    events = []
    return events, events.append


def _visible(payload):
    """(role, text) of the non-reasoning input items."""
    return [(i["role"], item_text(i)) for i in payload["input"] if i.get("type") != "reasoning"]


def test_window_payload_matches_generator_reference(small_eps):
    """At every step, the W cells' visible messages equal persistgym's reference drop-oldest
    payload for the same replies (the model the generator designed near/far with)."""
    for ep in small_eps:
        if ep.cell.recoverable:
            continue
        for cid in ("W-0", "W-n-0"):
            events, rec = _record()
            run_episode(ep, CELLS[cid], CFG, FakeModel(), recorder=rec)
            replies = [item_text(e["response"]["output"][1]) for e in events]
            for m, e in enumerate(events):
                ref = reference_window_payload(ep, replies[:m])
                assert _visible(e["payload"]) == [(x["role"], x["content"]) for x in ref[1:]]
                if cid == "W-0":
                    assert e["payload"]["instructions"] == ref[0]["content"]


def test_need_step_survival_by_cell(small_eps):
    for ep in small_eps:
        for cell in CELLS.values():
            run = run_episode(ep, cell, CFG, FakeModel())
            assert run.exit_reason == "DONE" and not run.excluded
            S = run.need_payload["S"]
            if cell.history == "full":
                assert S is True
            elif cell.history == "window":
                # fake replies are short, so S equals the designed window S
                assert S == ep.design["S_window_obs_only"] == (ep.cell.distance == "near")
            else:
                # summary: S is whether every component sits in a turn after the last
                # compaction (turn index == step index: the fake never looks up)
                end = run.compactions[-1]["compacted_turns"][1] if run.compactions else 0
                assert S == all(c.step >= end for c in ep.components)
                if ep.cell.distance == "far":
                    assert S is False


def _copying_summary(ep: Episode):
    """A fake summarizer that copies every record sentence about the entity it can see."""
    pat = re.compile(rf"For [a-z]+ {ep.entity}, the [a-z ]+ is \d+\.|Rule: [^\n]+\.")

    def fn(payload, j):
        seen = "\n".join(item_text(i) for i in payload["input"])
        return f"SUMMARY s{j}: " + " ".join(dict.fromkeys(pat.findall(seen))) or "nothing"
    return fn


def test_bridge_is_excluded_from_S_and_string_matched(small_eps):
    far = [e for e in small_eps if e.cell.distance == "far" and not e.cell.recoverable]
    for ep in far:
        for cid in ("Σ-n-0", "Σ-0-r"):
            run = run_episode(ep, CELLS[cid], CFG,
                              FakeModel(summary_fn=_copying_summary(ep)))
            assert run.need_info["bridge_index"] == 0
            assert run.need_payload["S"] is False  # the bridge does not count as observed
            assert run.need_bridge_carried["carried"] is True
            # a summarizer that keeps nothing carries nothing
            run0 = run_episode(ep, CELLS[cid], CFG, FakeModel())
            assert run0.need_bridge_carried["carried"] is False


def test_lookup_turn_flows_through_the_harness(small_eps):
    ep = next(e for e in small_eps if e.cell.id == "observed-rec-far")

    def reply(payload, i):
        last = item_text(payload["input"][-1])
        if "needs its" in last and "LOOKUP RESULT" not in last:
            return f"ACTION: lookup({ep.entity})"
        return "ACTION: ack(none)"

    for cid in ("W-n-0", "F-0", "Σ-n-0"):
        events, rec = _record()
        run = run_episode(ep, CELLS[cid], CFG, FakeModel(reply), recorder=rec)
        assert run.n_lookups == 1 and run.n_turns == ep.n_steps + 1
        assert run.n_lookups_unavailable == 0
        steps = [e for e in events if e["kind"] == "step"]
        lookup = next(e for e in steps if e["is_lookup_result"])
        assert lookup["pending_step"] == ep.need_step
        assert item_text(lookup["payload"]["input"][-1]).count("LOOKUP RESULT") == 1
        # S is taken at the need step's first presentation, before the lookup re-shows it
        assert run.need_payload["S"] is (cid == "F-0")


def test_over_cap_lookups_are_recorded_apart_from_lookups(small_eps, tmp_path):
    """Generator 0.2.0 (D3): once the cap is used, a lookup gets one 'lookup unavailable'
    turn and the step is asked again. The episode record counts such turns in
    `n_lookups_unavailable`, next to `n_lookups` (lookups served), as the transcript shows
    them. Here the agent looks up at the need step until it is told no more are available,
    then answers."""
    ep = next(e for e in small_eps if e.cell.id == "observed-rec-far")
    cap = ep.lookup.max_per_episode

    def reply(payload, i):
        last = item_text(payload["input"][-1])
        if "lookup unavailable" in last:
            return f"ACTION: {ep.need.expected_action}"
        return f"ACTION: lookup({ep.entity})" if "needs its" in last else "ACTION: ack(none)"

    for cid in ("W-n-0", "F-0", "Σ-n-0"):
        events, rec = _record()
        run = run_episode(ep, CELLS[cid], CFG, FakeModel(reply), recorder=rec)
        refusals = [e for e in events if e["kind"] == "step" and "lookup unavailable"
                    in item_text(e["payload"]["input"][-1])]
        served = [e for e in events if e["kind"] == "step" and e["is_lookup_result"]
                  and e not in refusals]
        assert (run.n_lookups, run.n_lookups_unavailable) == (cap, 1) == (
            len(served), len(refusals))
        assert refusals[0]["pending_step"] == ep.need_step
        assert run.n_turns == ep.n_steps + cap + 1 and run.need_correct
        # the refusal is one more round-trip inside the need phase (D8)
        assert run.need_phase["n_lookup_result_calls"] == cap + 1 and run.need_phase["complete"]
    # the field is in the per-episode record run_batch writes, next to n_lookups
    run_batch([ep], CELLS["F-0"], CFG, FakeModel(reply), experiment="persistgym",
              run_id="over-cap", results_root=tmp_path / "results", raw_root=tmp_path / "raw")
    path = tmp_path / "results" / "persistgym" / "over-cap" / "episodes.jsonl"
    (row,) = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    keys = list(row)
    assert keys.index("n_lookups_unavailable") == keys.index("n_lookups") + 1
    assert (row["n_lookups"], row["n_lookups_unavailable"]) == (cap, 1)


def test_context_echo_mismatch_excludes_and_stops(small_eps):
    ep = small_eps[0]
    run = run_episode(ep, CELLS["F-r"], CFG, FakeModel(echo_context="current_turn"))
    assert run.excluded and run.exit_reason == "REASONING_CONTEXT_MISMATCH"
    assert run.n_requests == 1 and "all_turns" in run.exclusion_reason
    cfg = CFG.replace(stop_on_context_mismatch=False)
    run = run_episode(ep, CELLS["F-r"], cfg, FakeModel(echo_context="current_turn"))
    assert run.excluded and run.exit_reason == "DONE" and run.n_turns == ep.n_steps
    # the 0 arm asks for current_turn, so the same echo is a match there
    assert not run_episode(ep, CELLS["F-0"], CFG, FakeModel(echo_context="current_turn")).excluded


def test_empty_summaries_are_retried_then_fail(small_eps):
    ep = small_eps[0]
    calls = []

    def flaky(payload, j):
        calls.append(j)
        return "" if len(calls) <= 2 else f"SUMMARY s{j}"

    run = run_episode(ep, CELLS["Σ-n-r"], CFG, FakeModel(summary_fn=flaky))
    assert run.exit_reason == "DONE" and run.n_summary_failures == 2
    run = run_episode(ep, CELLS["Σ-n-r"], CFG, FakeModel(summary_fn=lambda p, j: ""))
    assert run.exit_reason == "AGENT_ERROR" and run.n_summary_failures == 4
    # an incomplete summary counts as a failure too (ARC: status must be "completed")
    run = run_episode(ep, CELLS["Σ-n-r"], CFG.replace(summary_max_attempts=1),
                      FakeModel(status_fn=lambda p, tag: "incomplete" if tag[0] == "s"
                                else "completed"))
    assert run.exit_reason == "AGENT_ERROR"


def test_summary_attempts_are_counted_per_compaction(small_eps):
    """With summary_keep_recent_tokens > 0 and a long summary, one observation can need
    several compactions in a row. Each gets its own `summary_max_attempts` (ARC counts
    response failures per compaction); failures of an earlier, successful compaction must not
    use them up."""
    ep = small_eps[0]
    calls = []

    def every_other_fails(payload, j):
        calls.append(j)
        return "" if len(calls) % 2 == 1 else padded_text(f"SUMMARY s{j}", 1_200)

    cfg = CFG.replace(summary_keep_recent_tokens=6_000, summary_max_attempts=2)
    events, rec = _record()
    run = run_episode(ep, CELLS["Σ-n-0"], cfg, FakeModel(summary_fn=every_other_fails),
                      recorder=rec)
    kinds = [e["kind"] for e in events]
    back_to_back = any(kinds[i:i + 4] == ["summary"] * 4 for i in range(len(kinds)))
    assert back_to_back  # two compactions (fail + success each) before one step request
    assert run.exit_reason == "DONE" and run.n_summary_failures == len(run.compactions)


def test_payloads_are_deterministic_and_survive_jsonl_roundtrip(small_eps):
    ep = small_eps[5]
    again = Episode.from_dict(json.loads(json.dumps(ep.to_dict())))
    a, b = FakeModel(), FakeModel()
    run_episode(ep, CELLS["Σ-n-r"], CFG, a)
    run_episode(again, CELLS["Σ-n-r"], CFG, b)
    assert runmeta.config_hash({"c": a.calls}) == runmeta.config_hash({"c": b.calls})


def test_run_batch_writes_meta_and_transcript(small_eps, tmp_path, monkeypatch):
    def no_client(*a, **k):
        raise AssertionError("the fake path must never build an OpenAI client")
    monkeypatch.setattr(openai, "OpenAI", no_client)
    eps = small_eps[:3]
    meta = run_batch(eps, CELLS["W-n-0"], CFG, FakeModel(), experiment="persistgym",
                     run_id="test-run", results_root=tmp_path / "results",
                     raw_root=tmp_path / "raw")
    out = tmp_path / "results" / "persistgym" / "test-run"
    assert set(runmeta.REQUIRED) <= set(meta)
    assert meta["exit_reason"] == "COMPLETED" and meta["paid"] is False
    assert meta["reasoning_context_requested"] == "current_turn"
    assert meta["reasoning_context_echoed"] == {"current_turn": sum(e.n_steps for e in eps)}
    assert meta["model_returned"] == ["gpt-6-luna-fake-2026-10-01"]
    assert meta["config"]["harness_cell"] == "W-n-0" and len(meta["config_hash"]) == 64
    assert meta["cost_usd"]["costs_csv_row_appended"] is False
    lines = (out / "episodes.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["episode_id"] for x in lines] == [e.episode_id for e in eps]
    assert "blinding" not in meta and meta["tokens"]["reasoning_tokens"] > 0
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["n_episodes"] == 3 and summary["blinded"] is False
    with gzip.open(tmp_path / "raw" / "persistgym" / "test-run" / "transcript.jsonl.gz",
                   "rt", encoding="utf-8") as f:
        events = [json.loads(x) for x in f]
    assert len(events) == sum(e.n_steps for e in eps)
    assert all(e["echo"]["context_ok"] for e in events)


def test_run_batch_aborts_after_mismatched_episodes(small_eps, tmp_path):
    meta = run_batch(small_eps[:5], CELLS["W-n-r"], CFG, FakeModel(echo_context="current_turn"),
                     experiment="persistgym_pilot", run_id="mm",
                     results_root=tmp_path / "r", raw_root=tmp_path / "raw")
    assert meta["exit_reason"] == "ABORTED_CONTEXT_MISMATCH"
    assert meta["n_episodes_run"] == 2 and meta["n_excluded"] == 2


@pytest.mark.parametrize("cid", list(CELLS))
def test_every_cell_runs_every_task_cell(small_eps, cid):
    for ep in small_eps[:8]:
        run = run_episode(ep, CELLS[cid], CFG, FakeModel())
        assert run.exit_reason == "DONE" and run.n_turns == ep.n_steps
        assert run.n_requests == run.n_turns + run.n_summary_requests
        assert run.echo["context_echoed"] == {CELLS[cid].reasoning_context: run.n_requests}
