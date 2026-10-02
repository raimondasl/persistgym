"""The engagement check of PREREG §17.2 (amendment R2; harnesses/reasoning_check.py) on
synthetic check runs made with the fake model: the statistic, the verdicts, the pair checks,
the allowlisted output (no per-arm value, need-step quantity or success measure can be read
from it), the CLI and the guard it unlocks. Also `echo-count`. Fake model, no network."""

from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path

import pytest

from harnesses import cli, probes, reasoning_check, registered
from harnesses.cells import CELLS
from harnesses.config import HarnessConfig
from harnesses.fake import FakeModel
from harnesses.items import item_text
from harnesses.matrix import DERIVED_FAR, RunMatrix
from harnesses.runner import run_batch
from harnesses.tests.conftest import SMALL

SOL, LUNA = "gpt-6.1-sol", "gpt-6-luna"
PILOT = "persistgym_pilot"
FAR = ["observed-nonrec-far", "observed-rec-far", "derived-nonrec-far", "derived-rec-far"]
IDS = ("chk-F-r", "chk-F-0")


def _eps(start: int = 0):
    """The check's episodes: 2 pilot templates x the 4 far task cells (small volume)."""
    return RunMatrix.full(2, FAR).episodes("pilot", start, SMALL)


def _evidence_obs(eps) -> set[str]:
    return {ep.steps[s].observation for ep in eps if ep.cell.id in DERIVED_FAR
            for s in ep.reveal_steps}


def _n_evidence(eps) -> int:
    """Evidence-step calls over both arms, one per evidence step of each derived-far episode."""
    return 2 * sum(len(ep.reveal_steps) for ep in eps if ep.cell.id in DERIVED_FAR)


def _answers(ep) -> tuple[str, str]:
    """The need step's right action and a wrong one of the same form (another option)."""
    right = ep.need.expected_action
    other = next(o.label for o in ep.options if o.label != ep.correct_label)
    return right, f"{right.split('(')[0]}({other})"


def _fake(eps, at_evidence, elsewhere=0, *, correct_in=(), **kw):
    """A fake whose reasoning tokens are `at_evidence` on an evidence step's observation and
    `elsewhere` otherwise, each a number or {context: number} (a per-arm difference). At the
    need step it answers right in the arms named in `correct_in` and wrong in the others."""
    evidence = _evidence_obs(eps)
    need = {ep.steps[ep.need_step].observation: _answers(ep) for ep in eps}

    def pick(v, payload):
        return v[payload["reasoning"]["context"]] if isinstance(v, dict) else v

    def tokens(payload, n):
        last = item_text(payload["input"][-1])
        return pick(at_evidence if last in evidence else elsewhere, payload)

    def reply(payload, n):
        last = item_text(payload["input"][-1])
        if last in need:
            right, wrong = need[last]
            return f"ACTION: {right if payload['reasoning']['context'] in correct_in else wrong}"
        return "ACTION: ack(none)"
    return FakeModel(reply, reasoning_tokens_fn=tokens, **kw)


def _runs(root: Path, eps, fake_for, *, model=SOL, effort="high", ids=IDS,
          cells=("F-r", "F-0"), cfg_for=None):
    for cid, rid in zip(cells, ids, strict=True):
        cfg = HarnessConfig(model=model, reasoning_effort=effort)
        if cfg_for:
            cfg = cfg_for(cid, cfg)
        run_batch(eps, CELLS[cid], cfg, fake_for(cid), experiment=PILOT, run_id=rid,
                  results_root=root / "results", raw_root=root / "raw")


def _check(root: Path, ids=IDS, reference=()):
    return reasoning_check.check(list(ids), list(reference), results_root=root / "results",
                                 raw_root=root / "raw")


def _stable(report: dict) -> dict:
    return {k: v for k, v in report.items() if k != "generated_utc"}


# --- the statistic and the verdicts -----------------------------------------------------------

@pytest.mark.parametrize(("at_evidence", "verdict", "E"), [
    (40, "ENGAGED", 1.0), (32, "ENGAGED", 1.0),                 # 32 is at the floor
    (31, "NOT_ENGAGED", 0.0), (0, "NOT_ENGAGED", 0.0),
    ({"all_turns": 32, "current_turn": 0}, "ENGAGED", 0.5),     # E = 0.50 exactly engages
    ({"all_turns": 31, "current_turn": 90}, "ENGAGED", 0.5),
    ({"all_turns": 31, "current_turn": 0}, "NOT_ENGAGED", 0.0)])
def test_the_rule(tmp_path, at_evidence, verdict, E):
    eps = _eps()
    _runs(tmp_path, eps, lambda cid: _fake(eps, at_evidence, elsewhere=100))
    out = _check(tmp_path)
    n = _n_evidence(eps)
    assert out["verdict"] == verdict and out["E"] == E
    assert out["evidence_step_calls"] == n and 16 <= n <= 24
    assert out["evidence_step_calls_at_floor"] == round(E * n)
    assert out["derived_far_episodes"] == 8 and out["derived_far_ended_normally"] == 8
    assert out["model"] == SOL and out["effort"] == "high"
    assert out["check_run_ids"] == list(IDS) and out["reference_run_ids"] == []
    assert out["rule"] == registered.rule()
    assert (f"E = {round(E * n)}/{n}") in out["verdict_reason"]


def test_evidence_calls_are_the_first_step_call_at_each_evidence_step(tmp_path):
    """Lookups at the need step add lookup-result calls, never evidence-step calls; steps
    without evidence count only before the need step, as pre-need-step calls."""
    eps = _eps()
    need = {ep.steps[ep.need_step].observation: ep for ep in eps}

    def fake(cid):
        f = _fake(eps, 50, elsewhere=3)

        def reply(payload, n):  # recoverable cells: one lookup at the need step
            ep = need.get(item_text(payload["input"][-1]))
            return (f"ACTION: lookup({ep.entity})" if ep is not None and ep.cell.recoverable
                    else "ACTION: ack(none)")
        f.reply_fn = reply
        return f
    _runs(tmp_path, eps, fake)
    out = _check(tmp_path)
    assert out["evidence_step_calls"] == _n_evidence(eps) and out["E"] == 1.0
    pre = out["descriptive"]["check"]["pre_need_step_calls"]
    assert pre["n_calls"] == 2 * sum(ep.need_step for ep in eps)
    n_ev = out["evidence_step_calls"]
    assert pre["reasoning_tokens_mean"] == pytest.approx(
        (50 * n_ev + 3 * (pre["n_calls"] - n_ev)) / pre["n_calls"], abs=1e-3)
    assert pre["reasoning_tokens_median"] == 3 and pre["share_with_reasoning"] == 1.0
    assert out["descriptive"]["check"]["n_calls"] > 2 * sum(ep.n_steps for ep in eps)


def test_unscorable_when_too_few_derived_far_episodes_end_normally(tmp_path):
    """Here every episode of the F-0 run stops early (MAX_TURNS): 4 of 8 end normally."""
    eps = _eps()
    _runs(tmp_path, eps, lambda cid: _fake(eps, 40),
          cfg_for=lambda cid, cfg: cfg.replace(max_turns=2) if cid == "F-0" else cfg)
    out = _check(tmp_path)
    assert out["verdict"] == "UNSCORABLE" and out["derived_far_ended_normally"] == 4
    assert "4 of 8 derived-far episodes ended normally" in out["verdict_reason"]
    assert out["descriptive"]["check"]["errors"]["exit_reasons"] == {"DONE": 8,
                                                                     "MAX_TURNS": 8}


def test_unscorable_when_a_run_stops_on_an_echo_mismatch(tmp_path):
    """An effort echo that differs from the request excludes the episode (PREREG §17.2); after
    2 such episodes the run stops, and the check is unscorable. Excluded episodes give no
    evidence-step calls."""
    eps = _eps()
    _runs(tmp_path, eps, lambda cid: _fake(eps, 40, echo_effort="medium" if cid == "F-0"
                                           else "request"))
    out = _check(tmp_path)
    assert out["verdict"] == "UNSCORABLE" and out["runs_stopped_on_echo_mismatch"] == 1
    assert "1 run(s) stopped on an echo mismatch" in out["verdict_reason"]
    assert out["evidence_step_calls"] == _n_evidence(eps) // 2       # the F-r run's only
    echo = out["descriptive"]["check"]["echo_match"]
    assert echo["context_matched"] == echo["responses"]
    assert echo["responses"] - echo["effort_matched"] == 2           # one call per episode
    assert out["descriptive"]["check"]["errors"]["n_excluded"] == 2


# --- blinding --------------------------------------------------------------------------------

def test_the_output_is_exactly_the_allowlist(tmp_path):
    eps = _eps()
    _runs(tmp_path, eps, lambda cid: _fake(eps, 40))
    _runs(tmp_path, eps, lambda cid: _fake(eps, 0), effort="medium", ids=("ref-r", "ref-0"))
    out = _check(tmp_path, reference=("ref-0", "ref-r"))
    assert tuple(out) == reasoning_check.OUTPUT_KEYS
    for pool in out["descriptive"].values():
        assert tuple(pool) == reasoning_check.POOL_KEYS
        assert set(pool["pre_need_step_calls"]) == {"n_calls", "reasoning_tokens_mean",
                                                    "reasoning_tokens_median",
                                                    "share_with_reasoning"}
        assert set(pool["echo_match"]) == {"responses", "context_matched", "effort_matched"}
    ref = out["descriptive"]["reference"]
    assert out["reference_run_ids"] == ref["run_ids"] == ["ref-r", "ref-0"]   # F-r first
    assert (ref["model"], ref["effort"], ref["E"]) == (SOL, "medium", 0.0)
    assert out["verdict"] == "ENGAGED"                                 # the check runs decide
    forbidden = {"F-r", "F-0", "all_turns", "current_turn", "need_correct", "need_label",
                 "need_outcome", "need_phase", "need_payload", "first_step_call", "success",
                 "rate", "usage", "reasoning_tokens", "n_lookups"}
    for key, value in _walk(out):
        assert key not in forbidden, key                    # no per-arm or outcome field
        assert value not in ("all_turns", "current_turn"), key


def _walk(obj):
    """(key, value) of every dict entry in a JSON document, recursively."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v if not isinstance(v, (dict, list)) else None
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _swap_arms(root: Path) -> None:
    """Swap, between the two runs' raw files, every call's reasoning tokens and every
    episode's need-step outcome: the per-arm difference reverses, the pools do not change."""
    raw = root / "raw" / PILOT
    calls = {}
    for rid in IDS:
        with gzip.open(raw / rid / "transcript.jsonl.gz", "rt", encoding="utf-8") as f:
            calls[rid] = [json.loads(x) for x in f]
    eps = {rid: [json.loads(x) for x in (raw / rid / "episodes.jsonl").read_text(
        encoding="utf-8").splitlines()] for rid in IDS}
    a, b = IDS
    assert len(calls[a]) == len(calls[b]) and len(eps[a]) == len(eps[b])
    new = copy.deepcopy(calls)
    for x, y, nx, ny in zip(calls[a], calls[b], new[a], new[b], strict=True):
        assert (x["episode_id"], x["pending_step"]) == (y["episode_id"], y["pending_step"])
        ux, uy = x["response"]["usage"], y["response"]["usage"]
        nx["response"]["usage"], ny["response"]["usage"] = copy.deepcopy(uy), copy.deepcopy(ux)
    new_eps = copy.deepcopy(eps)
    for x, y, nx, ny in zip(eps[a], eps[b], new_eps[a], new_eps[b], strict=True):
        for k in ("need_correct", "need_label", "need_outcome", "need_phase", "usage",
                  "cost_usd_list", "cost_usd_billed_est"):
            nx[k], ny[k] = y[k], x[k]
    for rid in IDS:
        with gzip.open(raw / rid / "transcript.jsonl.gz", "wt", encoding="utf-8") as f:
            f.write("".join(json.dumps(r) + "\n" for r in new[rid]))
        (raw / rid / "episodes.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in new_eps[rid]), encoding="utf-8")


def test_a_per_arm_difference_cannot_be_read_from_the_output(tmp_path):
    """The arms differ in reasoning tokens everywhere, at the need step included, and in
    need-step success (F-r always right, F-0 always wrong). Swapping every per-arm value
    between the runs reverses the difference and leaves the output unchanged, so it holds
    no per-arm value; and changing need-step success alone changes nothing either."""
    eps = _eps()
    tokens = {"all_turns": 120, "current_turn": 7}
    _runs(tmp_path, eps, lambda cid: _fake(eps, tokens, elsewhere={"all_turns": 60,
                                                                   "current_turn": 1},
                                           correct_in=("all_turns",)))
    raw = tmp_path / "raw" / PILOT
    rows = {rid: [json.loads(x) for x in (raw / rid / "episodes.jsonl").read_text(
        encoding="utf-8").splitlines()] for rid in IDS}
    assert all(r["need_correct"] for r in rows[IDS[0]])               # the arms do differ
    assert not any(r["need_correct"] for r in rows[IDS[1]])
    before = _check(tmp_path)
    _swap_arms(tmp_path)
    rows = {rid: [json.loads(x) for x in (raw / rid / "episodes.jsonl").read_text(
        encoding="utf-8").splitlines()] for rid in IDS}
    assert not any(r["need_correct"] for r in rows[IDS[0]])           # reversed
    assert _stable(_check(tmp_path)) == _stable(before)

    # need-step success alone: every episode right in both arms, or wrong in both
    for correct_in, root in ((("all_turns", "current_turn"), tmp_path / "right"),
                             ((), tmp_path / "wrong")):
        _runs(root, eps, lambda cid, c=correct_in: _fake(eps, tokens, elsewhere={
            "all_turns": 60, "current_turn": 1}, correct_in=c))
    assert _stable(_check(tmp_path / "right")) == _stable(_check(tmp_path / "wrong"))


# --- the pair checks ----------------------------------------------------------------------------

@pytest.mark.parametrize(("kw", "message"), [
    ({"effort": "medium"}, "effort high"),
    ({"model": LUNA}, "scores gpt-6.1-sol at effort high"),
    ({"cells": ("F-r", "F-r")}, "exactly one F-r run and one F-0 run"),
    ({"cells": ("F-r", "W-n-0")}, "exactly one F-r run and one F-0 run")])
def test_check_runs_must_be_sol_at_high_effort_in_both_arms(tmp_path, kw, message):
    eps = _eps()
    _runs(tmp_path, eps, lambda cid: _fake(eps, 40), **kw)
    with pytest.raises(reasoning_check.CheckError, match=message):
        _check(tmp_path)


def test_check_runs_must_play_the_same_far_episodes(tmp_path):
    eps = _eps()
    _runs(tmp_path, eps, lambda cid: _fake(eps, 40), cells=("F-r",), ids=IDS[:1])
    other = _eps(start=2)
    _runs(tmp_path, other, lambda cid: _fake(other, 40), cells=("F-0",), ids=IDS[1:])
    with pytest.raises(reasoning_check.CheckError, match="same episodes"):
        _check(tmp_path)
    near = RunMatrix.full(2, ["derived-rec-near", *FAR[1:]]).episodes("pilot", 0, SMALL)
    _runs(tmp_path / "near", near, lambda cid: _fake(near, 40))
    with pytest.raises(reasoning_check.CheckError, match="4 far task cells"):
        _check(tmp_path / "near")
    with pytest.raises(reasoning_check.CheckError, match="missing"):
        _check(tmp_path, ids=("chk-F-r", "no-such-run"))


def test_reference_runs_must_pool_both_arms(tmp_path):
    """A single reference run would report one arm's figures: refused."""
    eps = _eps()
    _runs(tmp_path, eps, lambda cid: _fake(eps, 40))
    _runs(tmp_path, eps, lambda cid: _fake(eps, 0), effort="medium", ids=("ref-r", "ref-0"))
    with pytest.raises(reasoning_check.CheckError, match="exactly one F-r run and one F-0"):
        _check(tmp_path, reference=("ref-r",))
    with pytest.raises(reasoning_check.CheckError, match="given twice"):
        _check(tmp_path, reference=("chk-F-r", "ref-0"))


def test_the_runs_episodes_must_regenerate(tmp_path):
    eps = _eps()
    _runs(tmp_path, eps, lambda cid: _fake(eps, 40))
    meta_path = tmp_path / "results" / PILOT / IDS[0] / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["config"]["generator_config_hashes"] = ["0" * 64]
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(reasoning_check.CheckError, match="re-generate"):
        _check(tmp_path)


# --- the CLI and the guard -------------------------------------------------------------------

def test_reasoning_check_cli_writes_the_report_and_unlocks_sols_runs(tmp_path, capsys):
    eps = _eps()
    _runs(tmp_path, eps, lambda cid: _fake(eps, 40))
    results = tmp_path / "results"
    assert registered.engagement_refusal(results, SOL) is not None
    args = ["reasoning-check", *IDS, "--results-root", str(results), "--raw-root",
            str(tmp_path / "raw")]
    assert cli.main(args) == 0
    captured = capsys.readouterr()
    (path,) = (results / PILOT).glob("reasoning-check-*/reasoning_check.json")
    report = json.loads(path.read_text(encoding="utf-8"))
    assert json.loads(captured.out) == report and report["verdict"] == "ENGAGED"
    assert "verdict: ENGAGED" in captured.err and "written:" in captured.err
    # the guard of `run` now lets sol's non-pilot runs go at high effort (PREREG §17.2)
    assert registered.engagement_refusal(results, SOL) is None
    assert registered.check_run_settings("persistgym", SOL, "high", results) is None
    # bad arguments refuse
    assert cli.main([*args[:1], "../x", IDS[1], *args[3:]]) == 2
    assert cli.main([*args[:1], IDS[0], IDS[0], *args[3:]]) == 2
    assert "refused:" in capsys.readouterr().err


def test_a_not_engaged_check_keeps_sols_runs_refused(tmp_path, capsys):
    eps = _eps()
    _runs(tmp_path, eps, lambda cid: _fake(eps, 5))
    results = tmp_path / "results"
    assert cli.main(["reasoning-check", *IDS, "--results-root", str(results), "--raw-root",
                     str(tmp_path / "raw")]) == 0
    assert "verdict: NOT_ENGAGED" in capsys.readouterr().err
    assert "does not engage" in registered.check_run_settings("persistgym_validity", SOL,
                                                              "high", results)


# --- echo counts ---------------------------------------------------------------------------------

def test_echo_count(tmp_path, capsys):
    """Run transcripts (one echo per request) and probe transcripts (the echoes of a trial)
    are both counted, by the four echo fields only."""
    eps = _eps()[:2]
    raw = tmp_path / "raw"
    run_batch(eps, CELLS["F-r"], HarnessConfig(), FakeModel(), experiment=PILOT, run_id="ok",
              results_root=tmp_path / "results", raw_root=raw)
    run_batch(eps, CELLS["F-0"], HarnessConfig(), FakeModel(echo_effort="low"),
              experiment="persistgym_validity", run_id="low", results_root=tmp_path / "results",
              raw_root=raw)
    trial = probes.run_echo_check(SOL, "all_turns", FakeModel(lambda p, i: "ready"))
    (raw / "toggle_pilot" / "echo").mkdir(parents=True)
    with gzip.open(raw / "toggle_pilot" / "echo" / "transcript.jsonl.gz", "wt",
                   encoding="utf-8") as f:
        f.write(json.dumps({"repeat": 0, **trial}) + "\n")
    out = reasoning_check.echo_counts(raw)
    n_ok = sum(ep.n_steps for ep in eps)
    assert out["runs"] == {
        "toggle_pilot/echo": {"responses": 2, "context_matched": 2, "effort_matched": 2},
        f"{PILOT}/ok": {"responses": n_ok, "context_matched": n_ok, "effort_matched": n_ok},
        "persistgym_validity/low": {"responses": 2, "context_matched": 2,
                                    "effort_matched": 0}}  # one call each, then excluded
    assert out["total"] == {"responses": n_ok + 4, "context_matched": n_ok + 4,
                            "effort_matched": n_ok + 2}
    assert set(out["experiments"]) == {"toggle_pilot", "replay_probe", PILOT,
                                       "persistgym_validity", "persistgym",
                                       "statecarry_persistgym"}
    assert cli.main(["echo-count", "--raw-root", str(raw), "--experiment", PILOT]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["experiments"] == [PILOT] and list(printed["runs"]) == [f"{PILOT}/ok"]
    assert cli.main(["echo-count", "--raw-root", str(raw), "--experiment", "../x"]) == 2
