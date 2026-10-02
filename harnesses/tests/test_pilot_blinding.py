"""Pilot blinding (PREREG §11): per-episode outcomes of persistgym_pilot runs stay under the
gitignored results/raw/; committed files get only validity levels, pooled tokens, errors,
latency and cost. Fake model, no network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harnesses import blinding, cli
from harnesses.cells import CELLS
from harnesses.config import HarnessConfig
from harnesses.fake import FakeModel
from harnesses.items import item_text
from harnesses.runner import run_batch
from harnesses.tests.conftest import SMALL
from persistgym.episode import TaskCell
from persistgym.render import generate

CFG = HarnessConfig()
PILOT = "persistgym_pilot"
# Per-episode or per-arm outcome fields that must never appear in a committed pilot file.
OUTCOMES = {"need_correct", "need_label", "routine_accuracy", "need_phase", "need_payload",
            "need_bridge_carried", "n_lookups", "n_lookups_unavailable", "compacted_between",
            "usage", "rate",
            # D13: the need step's outcome and the per-step incomplete records (one at the
            # need step is a 0) are per-episode outcomes too
            "need_outcome", "incomplete"}


def _pilot_eps(variants=("base",), cells=("derived-nonrec-far", "observed-rec-far")):
    return [ep for _, eps in generate("pilot", range(1), SMALL,
                                      [TaskCell.from_id(c) for c in cells], variants)
            for ep in eps]


def _keys(obj, path=()):
    """(key path, value) of every key in a JSON document."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield path + (k,), v
            yield from _keys(v, path + (k,))
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v, path)


def _committed_files(results: Path) -> list[Path]:
    return sorted(p for p in results.rglob("*") if p.is_file())


def _assert_blinded(doc: dict) -> None:
    for path, value in _keys(doc):
        assert path[-1] not in OUTCOMES, path
        if path[-1] == "reasoning_tokens":
            assert value is None, path


def test_pilot_run_commits_no_per_episode_outcomes(tmp_path):
    eps = _pilot_eps()
    meta = run_batch(eps, CELLS["F-r"], CFG, FakeModel(), experiment=PILOT, run_id="p1",
                     results_root=tmp_path / "results", raw_root=tmp_path / "raw")
    out = tmp_path / "results" / PILOT / "p1"
    raw = tmp_path / "raw" / PILOT / "p1"
    assert [p.name for p in _committed_files(tmp_path / "results")] == ["meta.json",
                                                                        "summary.json"]
    for p in _committed_files(tmp_path / "results"):
        text = p.read_text(encoding="utf-8")
        assert '"need_correct"' not in text and '"need_phase"' not in text
        _assert_blinded(json.loads(text))
    assert meta["tokens"]["reasoning_tokens"] is None and meta["tokens"]["input_tokens"] > 0
    assert meta["blinding"]["episodes_path"].endswith("raw/persistgym_pilot/p1/episodes.jsonl")
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["blinded"] is True and summary["n_episodes"] == len(eps)
    assert summary["errors"]["exit_reasons"] == {"DONE": len(eps)}
    assert summary["latency"]["n_calls"] == sum(e.n_steps for e in eps)
    assert summary["cost_usd"]["cost_usd_list"] > 0
    assert summary["echo_match"] == {"F-r": {"requests": summary["latency"]["n_calls"],
                                             "matched": summary["latency"]["n_calls"]}}
    # the per-episode outcomes are in the gitignored raw folder
    rows = [json.loads(x) for x in (raw / "episodes.jsonl").read_text(encoding="utf-8")
            .splitlines()]
    assert [r["episode_id"] for r in rows] == [e.episode_id for e in eps]
    assert all("need_correct" in r and r["need_phase"]["tokens"] > 0 for r in rows)
    assert (raw / "transcript.jsonl.gz").exists()


def test_pilot_commits_only_routine_incomplete_counts(tmp_path):
    """D13: an incomplete response at the need step scores 0, so it is an outcome. A pilot's
    committed summary counts incomplete responses at routine steps only; the per-step
    records, need step included, stay in the raw episodes."""
    eps = _pilot_eps(cells=("derived-nonrec-far",))
    (ep,) = eps
    capped = {ep.steps[0].observation, ep.steps[ep.need_step].observation}
    hit = set()

    def reply(payload, i):
        if item_text(payload["input"][-1]) in capped:
            hit.add(f"t{i}")
            return ""
        return "ACTION: ack(none)"

    run_batch(eps, CELLS["F-r"], CFG,
              FakeModel(reply, status_fn=lambda p, tag: "incomplete" if tag in hit
                        else "completed"),
              experiment=PILOT, run_id="inc", results_root=tmp_path / "results",
              raw_root=tmp_path / "raw")
    for p in _committed_files(tmp_path / "results"):
        _assert_blinded(json.loads(p.read_text(encoding="utf-8")))
    summary = json.loads((tmp_path / "results" / PILOT / "inc" / "summary.json")
                         .read_text(encoding="utf-8"))
    assert summary["errors"]["n_incomplete_routine"] == 1
    (row,) = [json.loads(x) for x in (tmp_path / "raw" / PILOT / "inc" / "episodes.jsonl")
              .read_text(encoding="utf-8").splitlines()]
    assert [r["at_need"] for r in row["incomplete"]] == [0, 1]
    assert row["need_outcome"] == "incomplete"


@pytest.mark.parametrize("run_id", ["../../x", "..", "a/b", "a\\b", "C:x", "", " p1"])
def test_run_id_cannot_move_episodes_out_of_raw(tmp_path, run_id):
    """A run id like '../../x' would put a blinded run's episodes.jsonl at results/x/, a
    committed path. run_batch refuses it before writing anything."""
    with pytest.raises(ValueError, match="plain folder name"):
        run_batch(_pilot_eps(), CELLS["F-r"], CFG, FakeModel(), experiment=PILOT,
                  run_id=run_id, results_root=tmp_path / "results",
                  raw_root=tmp_path / "results" / "raw")
    assert not list(tmp_path.rglob("*"))


def test_cli_refuses_a_path_run_id_before_any_transport(monkeypatch, capsys):
    def no_transport(*a, **k):
        raise AssertionError("must refuse before building a transport")
    monkeypatch.setattr(cli, "_guarded_transport", no_transport)
    assert cli.main(["run", "--cell", "F-r", "--n", "1", "--task-cell", "derived-rec-far",
                     "--gen-set", "W_tokens=6400", "--gen-set", "v_tokens=400",
                     "--gen-set", "assumed_max_reply_tokens=200",
                     "--run-id", "../../leak", "--approved-block", "x",
                     "--planned-usd", "1"]) == 2
    assert "plain folder name" in capsys.readouterr().err


def test_other_experiments_are_not_blinded(tmp_path):
    assert not blinding.is_blinded("persistgym")
    assert not blinding.is_blinded("persistgym_validity")
    assert not blinding.is_blinded("toggle_pilot")  # D29: toggle checks are exempt
    run_batch(_pilot_eps(), CELLS["F-0"], CFG, FakeModel(), experiment="persistgym",
              run_id="m", results_root=tmp_path / "results", raw_root=tmp_path / "raw")
    assert (tmp_path / "results" / "persistgym" / "m" / "episodes.jsonl").exists()
    assert not (tmp_path / "raw" / "persistgym" / "m" / "episodes.jsonl").exists()


def _two_arm_pilot(tmp_path, cells=("F-r", "F-0")):
    eps = _pilot_eps(variants=("base", "restated"))
    for cid in cells:
        run_batch(eps, CELLS[cid], CFG, FakeModel(), experiment=PILOT, run_id=f"run-{cid}",
                  results_root=tmp_path / "results", raw_root=tmp_path / "raw")
    return eps


def test_pooled_report_pools_over_arms(tmp_path):
    eps = _two_arm_pilot(tmp_path)
    runs = blinding.load_raw_runs(tmp_path / "raw", PILOT)
    assert sorted(runs) == ["run-F-0", "run-F-r"]
    report = blinding.pooled_report(runs, experiment=PILOT)
    (model,) = report["models"]
    m = report["models"][model]
    assert m["harness_cells_pooled"] == ["F-0", "F-r"] and m["n_episodes"] == 2 * len(eps)
    raw = [e for r in runs.values() for e in r]
    assert m["tokens_pooled"]["reasoning_tokens"] == sum(e["usage"]["reasoning_tokens"]
                                                         for e in raw) > 0
    assert m["tokens_pooled"]["input_tokens"] == sum(e["usage"]["input_tokens"] for e in raw)
    # validity levels for the restated variant only, pooled over both arms; never base
    assert set(m["validity_levels"]) == {"restated"}
    assert m["validity_levels"]["restated"]["n_episodes"] == len(eps)  # half the episodes
    assert set(m["echo_match"]) == {"F-0", "F-r"}  # exempt per-arm toggle check
    for path, _ in _keys(report):
        assert path[-1] not in OUTCOMES - {"rate"}, path
    # no per-arm grouping anywhere except the exempt echo-match table
    assert {p[-1] for p, _ in _keys(report)} & {"F-0", "F-r"} == {"F-0", "F-r"}
    assert all("echo_match" in p for p, _ in _keys(report) if p[-1] in ("F-0", "F-r"))


def test_pooled_report_withholds_reasoning_for_a_single_arm(tmp_path):
    _two_arm_pilot(tmp_path, cells=("F-0",))
    report = blinding.pooled_report(blinding.load_raw_runs(tmp_path / "raw", PILOT),
                                    experiment=PILOT)
    (m,) = report["models"].values()
    assert m["harness_cells_pooled"] == ["F-0"]
    assert m["tokens_pooled"]["reasoning_tokens"] is None
    assert "only one harness cell" in m["tokens_note"]


def _ep(cell, variant, correct, exit_reason="DONE", excluded=False, model="m"):
    return {"harness_cell": cell, "variant": variant, "need_correct": correct, "model": model,
            "exit_reason": exit_reason, "excluded": excluded, "n_summary_failures": 0,
            "n_unparsed_routine": 1, "usage": {"input_tokens": 10, "reasoning_tokens": 3},
            "cost_usd_list": 0.5, "cost_usd_billed_est": 0.25, "call_latency_s": [1.0, 3.0],
            "echo": {"context_requested": "current_turn",
                     "context_echoed": {"current_turn": 2}}}


def test_validity_levels_count_finished_unexcluded_episodes_only():
    runs = {"a": [_ep("F-0", "restated", True), _ep("F-0", "restated", False),
                  _ep("F-0", "restated", True, excluded=True),
                  _ep("F-0", "restated", True, exit_reason="API_ERROR"),
                  _ep("F-0", "withheld", False), _ep("F-0", "base", True)],
            "b": [_ep("F-r", "withheld", True), _ep("F-r", "base", True)]}
    m = blinding.pooled_report(runs, experiment=PILOT)["models"]["m"]
    assert m["validity_levels"] == {
        "restated": {"n_episodes": 4, "n_counted": 2, "n_need_correct": 1, "rate": 0.5},
        "withheld": {"n_episodes": 2, "n_counted": 2, "n_need_correct": 1, "rate": 0.5}}
    assert m["errors"] == {"exit_reasons": {"API_ERROR": 1, "DONE": 7}, "n_excluded": 1,
                           "n_summary_failures": 0, "n_unparsed_routine": 8,
                           "n_incomplete_routine": 0}
    assert m["latency"] == {"n_calls": 16, "median_s": 2.0, "p90_s": 3.0, "max_s": 3.0}
    assert m["cost_usd"] == {"cost_usd_list": 4.0, "cost_usd_billed_est": 2.0}
    assert m["tokens_pooled"]["reasoning_tokens"] == 24


def test_pilot_report_cli_writes_the_pooled_report(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(cli, "RAW", tmp_path / "raw")
    assert cli.main(["pilot-report"]) == 1  # nothing to pool yet
    _two_arm_pilot(tmp_path)
    assert cli.main(["pilot-report"]) == 0
    (path,) = (tmp_path / "results" / PILOT).glob("pooled-*/pilot_report.json")
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["run_ids"] == ["run-F-0", "run-F-r"] and "git_commit" in report
    assert '"need_correct"' not in path.read_text(encoding="utf-8")
    assert "written:" in capsys.readouterr().err


@pytest.mark.parametrize("values, expected", [
    ([], {"n_calls": 0, "median_s": None, "p90_s": None, "max_s": None}),
    ([5.0], {"n_calls": 1, "median_s": 5.0, "p90_s": 5.0, "max_s": 5.0}),
    (list(range(1, 11)), {"n_calls": 10, "median_s": 5.5, "p90_s": 9.0, "max_s": 10.0}),
])
def test_latency_stats(values, expected):
    assert blinding._latency(values) == expected
