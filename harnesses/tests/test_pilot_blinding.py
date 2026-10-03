"""Pilot blinding (PREREG §11): per-episode outcomes of persistgym_pilot runs stay under the
gitignored results/raw/; committed files get only validity levels, pooled tokens, errors,
latency and cost. Fake model, no network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harnesses import blinding, cli, runner
from harnesses.cells import CELLS
from harnesses.config import HarnessConfig
from harnesses.fake import FakeModel
from harnesses.items import item_text
from harnesses.runner import run_batch
from harnesses.tests.conftest import SMALL
from persistgym.config import PRESET_HASHES
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
# Spend finer than the run's total, from meta.json's `parallel` (blinding.blinded_parallel):
# a per-episode estimate, and what the reservations and the per-call gate let overlap.
SPEND_DETAIL = {"last_estimate_usd", "estimate_usd", "reserved_usd", "spent_usd",
                "peak_episodes_in_flight", "calls_waited", "peak_calls_in_flight"}


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
        assert path[-1] not in OUTCOMES and path[-1] not in SPEND_DETAIL, path
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
                                             "matched": summary["latency"]["n_calls"],
                                             "effort_matched": summary["latency"]["n_calls"]}}
    # the per-episode outcomes are in the gitignored raw folder
    rows = [json.loads(x) for x in (raw / "episodes.jsonl").read_text(encoding="utf-8")
            .splitlines()]
    assert [r["episode_id"] for r in rows] == [e.episode_id for e in eps]
    assert all("need_correct" in r and r["need_phase"]["tokens"] > 0 for r in rows)
    assert (raw / "transcript.jsonl.gz").exists()
    # sequential play writes its `parallel` block to raw too, as parallel play does
    assert sorted(p.name for p in raw.iterdir()) == ["episodes.jsonl", runner.PARALLEL_INFO,
                                                     "transcript.jsonl.gz"]
    assert json.loads((raw / runner.PARALLEL_INFO).read_text(encoding="utf-8")) == (
        meta["parallel"]) == {"max_episodes_in_flight": 1}
    assert meta["blinding"]["parallel_path"].endswith(
        f"raw/persistgym_pilot/p1/{runner.PARALLEL_INFO}")


def test_a_pilot_whose_raw_parallel_block_cannot_be_written(tmp_path, capsys):
    """The raw copy of `parallel` is written like the reservation log: a failure is reported,
    by path and never by content, and does not stop the run's accounting; meta.json then
    names no raw copy."""
    eps = _pilot_eps()
    raw = tmp_path / "raw" / PILOT / "p1"
    (raw / runner.PARALLEL_INFO).mkdir(parents=True)  # a folder where the file would go
    meta = run_batch(eps, CELLS["F-r"], CFG, FakeModel(ids="payload"), experiment=PILOT,
                     run_id="p1", results_root=tmp_path / "results",
                     raw_root=tmp_path / "raw", parallel=2)
    assert meta["exit_reason"] == "COMPLETED" and meta["blinding"]["parallel_path"] is None
    assert meta["parallel"]["max_episodes_in_flight"] == 2
    err = capsys.readouterr().err
    assert f"warning: could not write {raw / runner.PARALLEL_INFO}" in err
    assert "peak_episodes_in_flight" not in err
    _assert_blinded(meta)


def test_a_parallel_pilot_stays_blinded(tmp_path):
    """PREREG §4.6 with §11: a pilot played 4 episodes at a time commits the same two files,
    blinded; each episode's transcript, while it plays, is under the gitignored raw folder
    only, and is gone from there once it is in the run's transcript."""
    eps = _pilot_eps(variants=("base", "restated"))
    meta = run_batch(eps, CELLS["F-r"], CFG, FakeModel(ids="payload"), experiment=PILOT,
                     run_id="par", results_root=tmp_path / "results",
                     raw_root=tmp_path / "raw", parallel=4)
    assert [p.name for p in _committed_files(tmp_path / "results")] == ["meta.json",
                                                                        "summary.json"]
    for p in _committed_files(tmp_path / "results"):
        _assert_blinded(json.loads(p.read_text(encoding="utf-8")))
    assert meta["parallel"]["max_episodes_in_flight"] == 4
    raw = tmp_path / "raw" / PILOT / "par"
    assert sorted(p.name for p in raw.iterdir()) == ["episodes.jsonl", runner.PARALLEL_INFO,
                                                     "transcript.jsonl.gz"]
    rows = [json.loads(x) for x in (raw / "episodes.jsonl").read_text(encoding="utf-8")
            .splitlines()]
    assert [r["episode_id"] for r in rows] == [e.episode_id for e in eps]
    # the fake model has no planned spend, so no reservations; the peak in flight, which a
    # spend plan would bound, is in the raw copy only
    full = json.loads((raw / runner.PARALLEL_INFO).read_text(encoding="utf-8"))
    assert full["peak_episodes_in_flight"] == 4 and full["spend_reservation"] is None
    assert meta["parallel"] == {k: v for k, v in full.items()
                                if k != "peak_episodes_in_flight"}


def test_parallel_block_is_allowlisted():
    """A pilot's meta.json commits only the fields of `parallel` in
    blinding.PARALLEL_FIELDS, so a field added to ParallelPlay.info, SpendPlan.info or
    CallGate.info later stays in the raw copy until it is added there."""
    gate = {"rule": "g", "calls": 40, "calls_waited": 3, "peak_calls_in_flight": 4,
            "later_gate_field": {"x": 1}}
    plan = {"planned_usd": 1.0, "estimate_rule": "r", "estimate_factor": 2.0,
            "episodes_started": 8, "episodes_measured": 7, "whole_episode_measured": True,
            "last_estimate_usd": 0.1, "later_estimate_usd": 0.2, "call_gate": gate}
    full = {"max_episodes_in_flight": 4, "peak_episodes_in_flight": 4,
            "episodes_started": 8, "episodes_not_started": 0, "stop_reason": None,
            "abandoned_episode_ids": [], "abandoned_transcripts": "raw/x/inflight",
            "later_field": 1, "spend_reservation": plan}
    assert blinding.blinded_parallel(full) == {
        "max_episodes_in_flight": 4, "episodes_started": 8, "episodes_not_started": 0,
        "stop_reason": None, "abandoned_episode_ids": [],
        "abandoned_transcripts": "raw/x/inflight",
        "spend_reservation": {"planned_usd": 1.0, "estimate_rule": "r",
                              "estimate_factor": 2.0, "episodes_started": 8,
                              "episodes_measured": 7, "whole_episode_measured": True,
                              "call_gate": {"rule": "g", "calls": 40}}}
    assert full["spend_reservation"]["last_estimate_usd"] == 0.1  # the input is unchanged
    assert blinding.blinded_parallel({**full, "spend_reservation": None})[
        "spend_reservation"] is None
    assert blinding.blinded_parallel({"max_episodes_in_flight": 1}) == {
        "max_episodes_in_flight": 1}
    # a dict where a plain field is named keeps none of its fields
    assert blinding.blinded_parallel({"stop_reason": {"x": 1}}) == {"stop_reason": {}}


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


def test_echo_match_reports_the_effort_echo_next_to_the_context_echo():
    """PREREG §17.2: the effort echo-match count sits next to the context one, per harness
    cell (an exempt toggle check, PREREG §11). Episodes from before the runner counted
    effort echoes give None, not a count."""
    def ep(cell, efforts, requested="high"):
        e = _ep(cell, "base", False)
        if efforts is not None:
            e["echo"] = {**e["echo"], "effort_requested": requested, "effort_echoed": efforts}
        return e
    runs = {"a": [ep("F-0", {"high": 2}), ep("F-0", {"high": 1, "medium": 1})],
            "b": [ep("F-r", {"high": 2})],
            "old": [ep("F-r", None), ep("F-0", None)],
            "new": [ep("F-r", {"medium": 2}, requested="medium")]}
    models = blinding.pooled_report(runs, experiment=PILOT)["models"]
    assert set(models) == {"m", "m (effort high)"}           # pooled by effort (§17.2)
    m = models["m (effort high)"]
    assert m["reasoning_effort"] == "high"
    assert m["echo_match"] == {"F-0": {"requests": 4, "matched": 4, "effort_matched": 3},
                               "F-r": {"requests": 2, "matched": 2, "effort_matched": 2}}
    m = models["m"]
    assert m["reasoning_effort"] == "medium"                 # episodes from before §17.2
    assert m["echo_match"] == {"F-0": {"requests": 2, "matched": 2, "effort_matched": None},
                               "F-r": {"requests": 4, "matched": 4, "effort_matched": None}}
    assert blinding.run_summary(runs["a"], blinded=True)["echo_match"] == {
        "F-0": {"requests": 4, "matched": 4, "effort_matched": 3}}


def test_a_run_at_another_effort_never_joins_an_earlier_pool():
    """PREREG §11, §17.2: block 1's sol pool (F-r and F-0 at medium) has been reported. If one
    check run at high effort joined it, the difference between the reports before and after
    would be that one arm's reasoning total. Pools are split by effort, so the medium pool is
    unchanged and the high one, a single arm so far, withholds its reasoning tokens."""
    def ep(cell, effort=None):
        e = _ep(cell, "base", False)
        if effort:
            e["echo"] = {**e["echo"], "effort_requested": effort,
                         "effort_echoed": {effort: 2}}
        return e
    before = {"r": [ep("F-r")], "0": [ep("F-0")]}
    after = {**before, "high-r": [ep("F-r", "high")]}
    old = blinding.pooled_report(before, experiment=PILOT)["models"]
    new = blinding.pooled_report(after, experiment=PILOT)["models"]
    assert new["m"] == old["m"] and old["m"]["tokens_pooled"]["reasoning_tokens"] == 6
    high = new["m (effort high)"]
    assert high["harness_cells_pooled"] == ["F-r"]
    assert high["tokens_pooled"]["reasoning_tokens"] is None
    both = blinding.pooled_report({**after, "high-0": [ep("F-0", "high")]},
                                  experiment=PILOT)["models"]
    assert both["m"] == old["m"] and both["m (effort high)"]["tokens_pooled"][
        "reasoning_tokens"] == 6


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


def test_pool_key_separates_generator_configs():
    """PREREG §17.3: a pool on a config other than the default one gets ", generator
    <hash8>"; records without the field (logged before it existed) pool as the default."""
    variant, default = PRESET_HASHES["sol-chain"], PRESET_HASHES["default"]
    assert blinding.pool_key("m", "medium") == blinding.pool_key("m", "medium", default) == "m"
    assert blinding.pool_key("m", "high", None) == "m (effort high)"
    assert blinding.pool_key("m", "high", variant) == f"m (effort high, generator {variant[:8]})"
    assert blinding.pool_key("m", "medium", "f" * 64) == "m (generator ffffffff)"


def test_r3s_first_check_run_never_joins_r2s_pool():
    """PREREG §11, §17.3: R2's two check runs (sol at high, default config) have been
    reported. A report made after R3's F-r run alone (sol at high, sol-chain) keeps it in a
    pool of its own, one harness cell, with its reasoning tokens withheld; R2's pool is
    unchanged."""
    variant = PRESET_HASHES["sol-chain"]

    def ep(cell, gen=None):
        e = _ep(cell, "base", False, model="gpt-6.1-sol")
        e["echo"] = {**e["echo"], "effort_requested": "high", "effort_echoed": {"high": 2}}
        if gen:
            e["generator_config_hash"] = gen
        return e
    r2 = {"r2-r": [ep("F-r")], "r2-0": [ep("F-0", PRESET_HASHES["default"])]}
    old = blinding.pooled_report(r2, experiment=PILOT)["models"]
    new = blinding.pooled_report({**r2, "r3-r": [ep("F-r", variant)]},
                                 experiment=PILOT)["models"]
    key = f"gpt-6.1-sol (effort high, generator {variant[:8]})"
    assert set(new) == {"gpt-6.1-sol (effort high)", key}
    assert new["gpt-6.1-sol (effort high)"] == old["gpt-6.1-sol (effort high)"]
    assert old["gpt-6.1-sol (effort high)"]["tokens_pooled"]["reasoning_tokens"] == 6
    assert new[key]["harness_cells_pooled"] == ["F-r"]
    assert new[key]["tokens_pooled"]["reasoning_tokens"] is None
    assert new[key]["generator_config_hash"] == variant


def test_the_episode_logs_its_generator_config_out_of_committed_files(tmp_path):
    """`EpisodeRun.generator_config_hash` is in the raw episodes.jsonl, and in no committed
    file of a blinded run (summary.json and meta.json come from allowlists)."""
    eps = _pilot_eps()
    run_batch(eps, CELLS["F-0"], CFG, FakeModel(), experiment=PILOT, run_id="g",
              results_root=tmp_path / "results", raw_root=tmp_path / "raw")
    rows = [json.loads(x) for x in (tmp_path / "raw" / PILOT / "g" / "episodes.jsonl")
            .read_text(encoding="utf-8").splitlines()]
    assert [r["generator_config_hash"] for r in rows] == [e.config_hash for e in eps]
    for path in _committed_files(tmp_path / "results"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert not any(p[-1] == "generator_config_hash" for p, _ in _keys(doc)), path
