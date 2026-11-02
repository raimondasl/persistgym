"""analysis.haiku_control (R11's descriptive readings), checked on copies of R9's committed W-n-0
run read as the control: its contrast with R9 is then zero, and its contrasts with R10's arms
reproduce R10's committed ones. No raw transcript is copied, so these outputs are PROVISIONAL,
and reading 6 is checked on small made-up transcripts."""

from __future__ import annotations

import gzip
import json
import shutil

import numpy as np
import pytest

from analysis import haiku_control as hc
from analysis import haiku_provenance as hp
from harnesses import registered

ROOT = hc.REPO_ROOT
R9_RUN = "20261024T060051Z-W-n-0-claude-haiku-5-5"
NR_FAR = registered.HAIKU_CONTROL_TASK_CELLS
CONTROL = registered.HAIKU_CONTROL_EXPERIMENT


def _copy_control(root, *, ending="COMPLETED", keep=lambda rec: rec["task_cell"] in NR_FAR,
                  name="control", planned=hc.PLANNED_USD, change=None, started=None,
                  **meta_fields) -> None:
    """R9's run under R11's experiment, holding the records `keep` keeps (`change` edits them),
    with `planned` as its planned spend and a record of every episode it started, or `started`
    episodes. `meta_fields` go into its meta.json."""
    src = ROOT / "results" / registered.HAIKU_NOTES_EXPERIMENT / R9_RUN
    dst = root / "results" / CONTROL / name
    dst.mkdir(parents=True)
    rows = [json.loads(line) for line in (src / "episodes.jsonl").read_text(
        encoding="utf-8").splitlines()]
    rows = [rec for rec in rows if keep(rec)]
    if change:
        change(rows)
    meta = json.loads((src / "meta.json").read_text(encoding="utf-8"))
    meta.update(experiment=CONTROL, run_id=name, exit_reason=ending, **meta_fields)
    meta["parallel"] = {**meta["parallel"], "episodes_started": started or len(rows),
                        "spend_reservation": {**meta["parallel"]["spend_reservation"],
                                              "planned_usd": planned}}
    (dst / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (dst / "episodes.jsonl").write_text("\n".join(json.dumps(x) for x in rows) + "\n",
                                        encoding="utf-8")


@pytest.fixture(scope="module")
def committed(tmp_path_factory):
    """A results root holding the draw, R9's and R10's runs and cited outputs, and no raw
    transcripts."""
    root = tmp_path_factory.mktemp("committed")
    for rel in ("results/draw", f"results/{registered.HAIKU_NOTES_EXPERIMENT}/{R9_RUN}",
                f"results/{registered.HAIKU_PROVENANCE_EXPERIMENT}", hp.R9_OUTPUT, hc.R10_OUTPUT):
        shutil.copytree(ROOT / rel, root / rel)
    (root / hp.R9_REPLIES).parent.mkdir(parents=True)
    shutil.copy(ROOT / hp.R9_REPLIES, root / hp.R9_REPLIES)
    return root


@pytest.fixture
def copied(committed, tmp_path):
    """`committed`, in a folder of its own for one test's control run."""
    shutil.copytree(committed, tmp_path / "root")
    return tmp_path / "root"


def _template(rec) -> int:
    return hp.hh.template_index(rec["template_id"])


def _below(n):
    return lambda rec: rec["task_cell"] in NR_FAR and _template(rec) < n


def test_defaults_are_r11s():
    assert CONTROL == "persistgym_haiku_control" and hc.CELL == "W-n-0"
    assert NR_FAR == ("observed-nonrec-far", "derived-nonrec-far") == hp.NR_FAR
    meta = json.loads((ROOT / hc.R10_OUTPUT / "meta.json").read_text(encoding="utf-8"))
    assert meta["config"]["status"] == "FINAL" and len(meta["runs"]) == 3


def test_a_full_control_reads_all_200_templates(copied):
    _copy_control(copied)
    with pytest.raises(hp.hh.Refusal, match="no raw transcript"):
        hc.readings(copied, {}, False)
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    assert r["status"] == "PROVISIONAL" and r["templates_read"] == 200 and r["templates"] == "0-199"
    assert r["left_out"] == [] and r["templates_never_played"] == 0
    assert [a["arm"] for a in r["arms"]] == ["W-n-0 (R11)", "W-n-0 (R9)", "W-np-0", "W-npd-0"]
    rates = {a["arm"]: [(c["task_cell"], c["successes"], c["n"]) for c in a["cells"]]
             for a in r["arms"]}
    assert rates["W-n-0 (R11)"] == rates["W-n-0 (R9)"] == [
        ("observed-nonrec-far", 4, 200), ("derived-nonrec-far", 9, 200)]
    assert rates["W-np-0"] == [("observed-nonrec-far", 176, 200), ("derived-nonrec-far", 173, 200)]
    assert rates["W-npd-0"] == [("observed-nonrec-far", 173, 200), ("derived-nonrec-far", 177, 200)]
    assert all(a["responses"] is None for a in r["arms"])


def test_the_contrasts_reproduce_r10s(copied):
    """With R9's run as the control, the control minus R9 is zero, and an arm minus the control
    is R10's committed arm minus R9, interval included: the same resamples."""
    _copy_control(copied)
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    for v in r["contrasts"]["W-n-0 (R11) - W-n-0 (R9)"].values():
        assert v["pp"] == pytest.approx(0.0) and v["ci90"] == pytest.approx([0.0, 0.0])
    want = json.loads((ROOT / hc.R10_OUTPUT / "provenance.json").read_text(
        encoding="utf-8"))["contrasts"]
    for cell in registered.HAIKU_PROVENANCE_CELLS:
        got = r["contrasts"][f"{cell} - W-n-0 (R11)"]
        assert set(got) == set(NR_FAR)
        for tc, v in got.items():
            w = want[f"{cell} - W-n-0 (R9)"][tc]
            assert v["pp"] == pytest.approx(w["pp"]) and v["ci90"] == pytest.approx(w["ci90"])


def test_the_registered_stop_reads_every_arm_on_the_finished_templates(copied):
    """A partial template (one task cell finished) is left out of every arm, and named."""
    _copy_control(copied, ending="SPEND_RESERVATION", keep=lambda rec: (
        rec["task_cell"] in NR_FAR and (_template(rec) < 150 or (
            _template(rec) == 150 and rec["task_cell"] == NR_FAR[0]))))
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    assert r["templates_read"] == 150 and r["templates"] == "0-149"
    # the only incomplete item is the transcripts: the sweep itself is closed by its stop
    assert all("no raw transcript" in x for x in r["incomplete"])
    for a in r["arms"]:
        assert [c["n"] for c in a["cells"]] == [150, 150]
        assert a["counted_repeat_0"] == 300
        assert [c["episodes"] for c in a["choices_nr_far"].values()] == [150, 150]
        assert [c["n"] for c in a["costs"].values()] == [150, 150]
    (row,) = r["left_out"]
    assert (row["template"], row["task_cell"], row["status"]) == (150, NR_FAR[1], "no record")
    assert r["templates_never_played"] == 49
    text = hc.summary(r)
    assert "main templates 0-149 in every arm" in text and "template 150, derived" in text
    assert {e["never_played"] for e in r["exclusions"]} == {49, 50}


def test_the_arms_are_read_on_exactly_the_same_episodes_after_a_stop(copied):
    _copy_control(copied, ending="SPEND_RESERVATION", keep=_below(150))
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    table = {a["arm"]: {c["task_cell"]: c["successes"] for c in a["cells"]} for a in r["arms"]}
    # R9's own successes on templates 0-149 of the 2 cells, from its records
    rows = [json.loads(x) for x in (ROOT / "results" / registered.HAIKU_NOTES_EXPERIMENT / R9_RUN
                                    / "episodes.jsonl").read_text(encoding="utf-8").splitlines()]
    for tc in NR_FAR:
        want = sum(bool(x["need_correct"]) for x in rows
                   if x["task_cell"] == tc and _template(x) < 150)
        assert table["W-n-0 (R9)"][tc] == table["W-n-0 (R11)"][tc] == want


def test_a_hole_leaves_out_that_template_only_and_names_it(copied):
    """An episode the runner excluded (no final record of this key) does not cut later templates."""
    def exclude(rows):
        rec = next(x for x in rows if _template(x) == 10 and x["task_cell"] == NR_FAR[1])
        rec.update(excluded=True, exclusion_reason="made up")
    _copy_control(copied, ending="SPEND_RESERVATION", keep=_below(150), change=exclude)
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    assert r["templates_read"] == 149 and r["templates"] == "0-9, 11-149"
    (row,) = r["left_out"]
    assert (row["template"], row["task_cell"], row["status"]) == (10, NR_FAR[1], "excluded")
    assert all(a["counted_repeat_0"] == 298 for a in r["arms"])
    assert sum(e["excluded_by_runner"] for e in r["exclusions"]) == 1
    assert "template 10, derived-nonrec-far: excluded" in hc.summary(r)


@pytest.mark.parametrize("sweep_closed", [False, True])
def test_an_api_error_awaiting_its_re_run_refuses_even_with_the_sweep_closed(copied, sweep_closed):
    def fail(rows):
        rec = next(x for x in rows if _template(x) == 30 and x["task_cell"] == NR_FAR[1])
        rec.update(exit_reason="API_ERROR", need_correct=False, error="made up")
    _copy_control(copied, ending="SPEND_RESERVATION", keep=_below(150), change=fail)
    with pytest.raises(hp.hh.Refusal, match="await their §13 re-run"):
        hc.readings(copied, {}, sweep_closed)


@pytest.mark.parametrize("kw, why", [
    ({"ending": "COMPLETED"}, "its run ended COMPLETED"),
    ({"ending": "ERROR:KeyboardInterrupt"}, "its run ended ERROR:KeyboardInterrupt"),
    ({"ending": "SPEND_RESERVATION", "planned": 0.70}, "planned spend is 0.7"),
    ({"ending": "SPEND_RESERVATION", "started": 301}, "started 301 episodes and holds 300"),
])
def test_only_the_registered_stop_closes_a_short_sweep(copied, kw, why):
    _copy_control(copied, keep=_below(150), **kw)
    with pytest.raises(hp.hh.Refusal, match="finished 150 of 200 templates") as e:
        hc.readings(copied, {}, False)
    assert why in str(e.value)
    assert hc.readings(copied, {}, False, allow_incomplete=True)["status"] == "PROVISIONAL"
    # the researcher can close it: only the transcripts are then missing
    closed = hc.readings(copied, {}, True, allow_incomplete=True)
    assert closed["templates_read"] == 150
    assert all("no raw transcript" in x for x in closed["incomplete"])


def test_a_cost_cap_stop_closes_the_sweep_and_names_its_pending_keys(copied):
    def stop(rows):
        rec = next(x for x in rows if _template(x) == 150 and x["task_cell"] == NR_FAR[0])
        rec.update(exit_reason="COST_CAP", need_correct=False)
    _copy_control(copied, ending="COST_CAP", change=stop, keep=lambda rec: (
        rec["task_cell"] in NR_FAR and (_template(rec) < 150 or (
            _template(rec) == 150 and rec["task_cell"] == NR_FAR[0]))))
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    assert r["templates_read"] == 150
    assert all("no raw transcript" in x for x in r["incomplete"])
    assert [(x["template"], x["task_cell"], x["status"]) for x in r["left_out"]] == [
        (150, NR_FAR[0], "pending"), (150, NR_FAR[1], "no record")]


def test_a_pending_episode_before_the_last_template_read_refuses_at_the_stop(copied):
    def stop(rows):
        rec = next(x for x in rows if _template(x) == 147 and x["task_cell"] == NR_FAR[1])
        rec.update(exit_reason="RUN_STOPPED", need_correct=False)
    _copy_control(copied, ending="COST_CAP", keep=_below(150), change=stop)
    with pytest.raises(hp.hh.Refusal, match="before the last template read are pending"):
        hc.readings(copied, {}, False)


def test_a_declared_re_run_needs_the_researchers_close(copied):
    """An API error, then its §13 re-run: the key takes the re-run's record, and the stop no
    longer closes the sweep alone."""
    def fail(rows):
        rec = next(x for x in rows if _template(x) == 30 and x["task_cell"] == NR_FAR[1])
        rec.update(exit_reason="API_ERROR", need_correct=False, error="made up")
    _copy_control(copied, ending="SPEND_RESERVATION", keep=_below(150), change=fail, name="a")
    _copy_control(copied, name="b", started_utc="2026-11-03T00:00:00+00:00",
                  finished_utc="2026-11-03T00:01:00+00:00",
                  keep=lambda rec: rec["task_cell"] in NR_FAR and _template(rec) == 30)
    with pytest.raises(hp.hh.Refusal, match="2 runs hold it"):
        hc.readings(copied, {"b": "a"}, False)
    r = hc.readings(copied, {"b": "a"}, True, allow_incomplete=True)
    assert r["templates_read"] == 150 and r["left_out"] == []
    assert all("no raw transcript" in x for x in r["incomplete"])


def test_a_second_run_needs_the_researchers_close(copied):
    """A later run ended elsewhere: the first run's stop does not close the sweep on its own."""
    _copy_control(copied, ending="SPEND_RESERVATION", keep=_below(100), name="first")
    _copy_control(copied, ending="ERROR:KeyboardInterrupt", name="second", keep=lambda rec: (
        rec["task_cell"] in NR_FAR and 100 <= _template(rec) < 150))
    with pytest.raises(hp.hh.Refusal, match="2 runs hold it"):
        hc.readings(copied, {}, False)


def _r9_success(task_cell, n):
    rows = [json.loads(x) for x in (ROOT / "results" / registered.HAIKU_NOTES_EXPERIMENT / R9_RUN
                                    / "episodes.jsonl").read_text(encoding="utf-8").splitlines()]
    out = np.full(200, np.nan)
    for x in rows:
        if x["task_cell"] == task_cell and _template(x) < n:
            out[_template(x)] = float(bool(x["need_correct"]))
    return out


def test_intervals_and_contrasts_are_on_the_templates_read_with_the_registered_resamples(copied):
    """R9's run cut to 150 templates, against W-npd-0 (one run, so its records are simple), by a
    calculation here over the same resamples, with the unread templates left out of each mean."""
    _copy_control(copied, ending="SPEND_RESERVATION", keep=_below(150))
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    meta = json.loads((ROOT / hp.R9_OUTPUT / "meta.json").read_text(encoding="utf-8"))
    assert r["bootstrap"]["seed"] == meta["seeds"]["bootstrap"]
    idx = hp.hh.resample_indices(200, r["bootstrap"]["seed"], 10_000)
    rows = [json.loads(x) for x in (ROOT / "results" / registered.HAIKU_PROVENANCE_EXPERIMENT
                                    / "20261102T002751Z-W-npd-0-claude-haiku-5-5"
                                    / "episodes.jsonl").read_text(encoding="utf-8").splitlines()]
    for tc in NR_FAR:
        ctl = _r9_success(tc, 150)
        arm = np.full(200, np.nan)
        for x in rows:
            if x["task_cell"] == tc and _template(x) < 150:
                arm[_template(x)] = float(bool(x["need_correct"]))
        means = np.nanmean(ctl[idx], axis=1)
        row = next(c for c in r["arms"][1]["cells"] if c["task_cell"] == tc)
        assert row["interval_90"] == pytest.approx([np.nanpercentile(means, 5),
                                                    np.nanpercentile(means, 95)])
        v = r["contrasts"]["W-npd-0 - W-n-0 (R11)"][tc]
        d = 100 * (np.nanmean(arm[idx], axis=1) - np.nanmean(ctl[idx], axis=1))
        assert v["pp"] == pytest.approx(100 * (np.nanmean(arm) - np.nanmean(ctl)))
        assert v["ci90"] == pytest.approx([np.nanpercentile(d, 5), np.nanpercentile(d, 95)])


def _partial_at_150(rec):
    return rec["task_cell"] in NR_FAR and (
        _template(rec) < 150 or (_template(rec) == 150 and rec["task_cell"] == NR_FAR[0]))


def test_replies_and_responses_get_every_arm_on_the_templates_read(copied, monkeypatch):
    """The stop leaves a partial template, which stays out of every arm's replies and responses."""
    _copy_control(copied, ending="SPEND_RESERVATION", keep=_partial_at_150)
    seen = []

    def spy(resolved, *a, **k):
        seen.append({hp.hh.template_index(r.record["template_id"]) for r in resolved.values()})
        return None, {}, []
    def spy_replies(resolved, *a, **k):
        spy(resolved)
        return None, []
    monkeypatch.setattr(hc, "responses", spy)
    monkeypatch.setattr(hp, "replies", spy_replies)
    hc.readings(copied, {}, False, allow_incomplete=True)
    assert len(seen) == 6  # responses for 4 arms, replies for 2
    assert all(s == set(range(150)) for s in seen)


def test_the_control_minus_r9_is_on_the_templates_read_and_has_its_sign(copied):
    def win(rows):
        for tc in NR_FAR:
            for rec in [x for x in rows if x["task_cell"] == tc and not x["need_correct"]][:15]:
                rec["need_correct"] = True
    _copy_control(copied, ending="SPEND_RESERVATION", keep=_below(150), change=win)
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    for v in r["contrasts"]["W-n-0 (R11) - W-n-0 (R9)"].values():
        assert v["pp"] == pytest.approx(10.0)


def test_a_partial_template_stays_out_of_intervals_and_contrasts(copied):
    def win(rows):
        next(x for x in rows if _template(x) == 150)["need_correct"] = True
    _copy_control(copied, ending="SPEND_RESERVATION", keep=_partial_at_150, change=win)
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    idx = hp.hh.resample_indices(200, r["bootstrap"]["seed"], 10_000)
    tc = NR_FAR[0]
    ctl = _r9_success(tc, 150)
    rows = [json.loads(x) for x in (ROOT / "results" / registered.HAIKU_PROVENANCE_EXPERIMENT
                                    / "20261102T002751Z-W-npd-0-claude-haiku-5-5"
                                    / "episodes.jsonl").read_text(encoding="utf-8").splitlines()]
    npd = np.full(200, np.nan)
    for x in rows:
        if x["task_cell"] == tc and _template(x) < 150:
            npd[_template(x)] = float(bool(x["need_correct"]))
    for i, s in ((0, ctl), (1, ctl), (3, npd)):
        row = next(c for c in r["arms"][i]["cells"] if c["task_cell"] == tc)
        means = np.nanmean(s[idx], axis=1)
        assert row["interval_90"] == pytest.approx([np.nanpercentile(means, 5),
                                                    np.nanpercentile(means, 95)])
    v = r["contrasts"]["W-npd-0 - W-n-0 (R11)"][tc]
    assert v["pp"] == pytest.approx(100 * (np.nanmean(npd) - np.nanmean(ctl)))


def test_the_researchers_close_excludes_and_lists(copied):
    def stop(rows):
        rec = next(x for x in rows if _template(x) == 147 and x["task_cell"] == NR_FAR[1])
        rec.update(exit_reason="RUN_STOPPED", need_correct=False)
    _copy_control(copied, ending="ERROR:KeyboardInterrupt", keep=_below(150), change=stop)
    r = hc.readings(copied, {}, True, allow_incomplete=True)
    assert [x["status"] for x in r["left_out"] if x["template"] == 147] == ["excluded"]
    assert any("no final record" in d for d in r["deviations"])
    assert any("never played" in d for d in r["deviations"])


def test_left_out_says_why(copied):
    def exclude(rows):
        rec = next(x for x in rows if _template(x) == 10 and x["task_cell"] == NR_FAR[1])
        rec.update(excluded=True, exclusion_reason="made up")
    _copy_control(copied, ending="SPEND_RESERVATION", keep=_below(150), change=exclude)
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    assert "made up" in r["left_out"][0]["reason"]


def test_user_messages_are_compared_with_r9s(copied, monkeypatch):
    _copy_control(copied)

    def fake(resolved, experiment, cell, raw):
        return None, ({"e#0": "a", "e#1": "b", "e#2": "c"}
                      if experiment == registered.HAIKU_NOTES_EXPERIMENT
                      else {"e#0": "a", "e#1": "b", "e#2": "x"}), []
    monkeypatch.setattr(hc, "responses", fake)
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    assert r["user_messages_against_r9"]["W-n-0 (R11)"] == {"common": 3, "identical": 2}


def test_readings_1_2_and_8_reach_the_output(copied):
    _copy_control(copied)
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    for a in r["arms"]:
        assert {x["task_cell"] for x in a["accounting"]} == set(NR_FAR)
        assert all("stopped_responses" in c for c in a["cells"])
    assert {c["run_id"] for c in r["arms"][3]["conditions"]} == {
        "20261102T002751Z-W-npd-0-claude-haiku-5-5"}
    assert r["arms"][0]["conditions"][0]["model_returned"] == ["claude-haiku-5-5"]
    assert r["arms"][0]["conditions"][0]["inference_geos"]


def test_a_missing_cost_and_a_replay_warning_reach_the_warnings(copied, monkeypatch):
    def no_cost(rows):
        rows[0]["cost_usd_billed_est"] = None
    _copy_control(copied, change=no_cost)
    real = hp.hh.accounting_check

    def check(*a, **k):
        return {**real(*a, **k), "warnings": ["made up replay warning"]}
    monkeypatch.setattr(hp.hh, "accounting_check", check)
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    assert any("have no billed cost" in w for w in r["warnings"])
    assert "made up replay warning" in r["warnings"]


def test_with_everything_present_the_status_is_final(copied, monkeypatch):
    _copy_control(copied)
    monkeypatch.setattr(hp.hh, "accounting_check", lambda *a, **k: {
        "checked": 400, "bugs": [], "missing_transcripts": [], "warnings": []})
    monkeypatch.setattr(hc, "responses", lambda *a, **k: (None, {}, []))
    monkeypatch.setattr(hp, "replies", lambda *a, **k: (None, []))
    r = hc.readings(copied, {}, False)
    assert r["status"] == "FINAL" and r["incomplete"] == []
    assert hc.summary(r).count("**FINAL.**") == 1


def test_the_summary_prints_readings_5_and_6(copied, tmp_path):
    path = tmp_path / CONTROL / "run" / "transcript.jsonl.gz"
    path.parent.mkdir(parents=True)
    lines = [_line("e1", 0, thinking=True), _line("e1", 1, thinking=True, text="saw 568"),
             _line("e1", 2, stop="refusal"), _line("e1", 3)]
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for x in lines:
            f.write(json.dumps(x) + "\n")
    reading, _, _ = hc.responses(_resolved(_record("e1")), CONTROL, "W-n-0", tmp_path, {"e1": FACT})
    _copy_control(copied)
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    replies = {"observed-nonrec-far carried=True": {
        "episodes": 1, "correct": 0, "failed": 1, "failed_declined": 0,
        "failed_need_reply_disowns": 1, "failed_retracted_before_need": 0}}
    for a in r["arms"]:
        a["responses"], a["replies_nr_far"] = reading, replies
    text = hc.summary(r)
    assert "(no transcripts)" not in text and "observed-nonrec-far carried=True" in text


def test_main_writes_its_three_files(copied, tmp_path):
    _copy_control(copied)
    out = tmp_path / "out"
    assert hc.main(["--results-root", str(copied), "--allow-incomplete", "--out-dir", str(out)]) == 0
    assert {p.name for p in out.iterdir()} == set(hc.OUTPUTS)


def test_a_bug_in_the_replay_stops_the_analysis_even_as_provisional(copied, monkeypatch):
    _copy_control(copied)
    monkeypatch.setattr(hp.hh, "accounting_check", lambda *a, **k: {
        "checked": 1, "bugs": ["made up"], "missing_transcripts": [], "warnings": []})
    with pytest.raises(hp.hh.AccountingBug, match="made up"):
        hc.readings(copied, {}, False, allow_incomplete=True)


def test_a_replay_that_cannot_be_made_refuses_though_no_counted_record_needs_it(copied, monkeypatch):
    _copy_control(copied)
    monkeypatch.setattr(hp.hh, "accounting_check", lambda *a, **k: {
        "checked": 1, "bugs": [], "missing_transcripts": ["b"], "warnings": []})
    monkeypatch.setattr(hc, "responses", lambda *a, **k: (None, {}, []))
    monkeypatch.setattr(hp, "replies", lambda *a, **k: (None, []))
    with pytest.raises(hp.hh.Refusal, match="§2.8's replay cannot be made"):
        hc.readings(copied, {}, False)
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    assert r["status"] == "PROVISIONAL" and "§2.8's replay cannot be made" in hc.summary(r)


def test_a_run_with_no_tokens_or_no_time_has_no_rate(copied):
    """A failed launch followed by a second run: the analysis still reads, and prints n/a."""
    _copy_control(copied, ending="SPEND_RESERVATION", keep=_below(150), name="a")
    _copy_control(copied, ending="ERROR:RuntimeError", name="b", tokens={},
                  started_utc="2026-11-03T00:00:00+00:00",
                  finished_utc="2026-11-03T00:00:00+00:00", keep=lambda rec: False)
    r = hc.readings(copied, {}, True, allow_incomplete=True)
    rates = {c["run_id"]: c["uncached_per_minute"] for c in r["arms"][0]["conditions"]}
    assert rates["b"] is None and rates["a"] > 0
    assert "| b | ERROR:RuntimeError |" in hc.summary(r).replace("W-n-0 (R11) ", "")


def test_a_missing_cost_names_the_arm_and_reading_7():
    arms = [{"arm": "W-n-0 (R9)", "costs": {NR_FAR[0]: {
        "n": 200, "cost_missing": 2, "output_tokens_missing": 0}}}]
    (w,) = hc.missing_values(arms)
    assert w.startswith("W-n-0 (R9), observed-nonrec-far: 2 of 200") and "reading 7" in w


def test_a_record_off_the_two_cells_refuses(copied):
    _copy_control(copied, keep=lambda rec: rec["task_cell"] in hp.FAR)
    with pytest.raises(hp.hh.Refusal, match="plays observed-nonrec-far, derived-nonrec-far only"):
        hc.readings(copied, {}, False, allow_incomplete=True)


def test_no_finished_template_refuses(copied):
    _copy_control(copied, ending="SPEND_RESERVATION",
                  keep=lambda rec: rec["task_cell"] == NR_FAR[0])
    with pytest.raises(hp.hh.Refusal, match="finished no template"):
        hc.readings(copied, {}, False, allow_incomplete=True)


def test_no_run_folder_refuses(tmp_path):
    (tmp_path / "results" / "draw").mkdir(parents=True)
    with pytest.raises(hp.hh.Refusal, match=f"no {CONTROL}/ folder"):
        hc.readings(tmp_path, {}, False)


def _org_check(root, name, checked, same=True):
    folder = root / "results" / registered.HAIKU_CONTROL_ORG_CHECK / name
    folder.mkdir(parents=True)
    (folder / "org_check.json").write_text(json.dumps(
        {"checked_utc": checked, "same_org_as_r10_error": same, "same_org_as_r8_error": False}),
        encoding="utf-8")


def test_no_organization_check_is_warned_about(copied):
    _copy_control(copied)
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    assert r["org_checks"] == [] and any("no org-check result is committed" in w
                                         for w in r["warnings"])
    assert "no result committed" in hc.summary(r)


def test_the_organization_checks_must_bracket_the_run(copied):
    """R9's run, the stand-in here, ran on 2026-10-24 from 06:00 to 07:31 UTC."""
    _copy_control(copied)
    _org_check(copied, "a", "2026-10-24T05:00:00+00:00")
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    assert any("no org-check result comes after" in w for w in r["warnings"])
    assert not any("comes before" in w for w in r["warnings"])
    _org_check(copied, "b", "2026-10-24T08:00:00+00:00")
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    assert not any("org-check" in w for w in r["warnings"])
    assert [o["same_org_as_r10_error"] for o in r["org_checks"]] == [True, True]


def test_one_check_naming_another_organization_is_warned_about(copied):
    _copy_control(copied)
    _org_check(copied, "a", "2026-10-24T05:00:00+00:00")
    _org_check(copied, "b", "2026-10-24T08:00:00+00:00", same=False)
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    assert any("another organization" in w for w in r["warnings"])


def test_the_checks_bracket_the_controls_run_not_r9s(copied):
    _copy_control(copied, started_utc="2026-11-04T19:00:00+00:00",
                  finished_utc="2026-11-04T22:00:00+00:00")
    _org_check(copied, "a", "2026-11-04T18:00:00+00:00")
    _org_check(copied, "b", "2026-11-04T23:00:00+00:00")
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    assert not any("org-check" in w for w in r["warnings"])


def test_a_check_between_two_runs_is_not_before_the_first(copied):
    _copy_control(copied, ending="SPEND_RESERVATION", keep=_below(100), name="first",
                  started_utc="2026-11-04T19:00:00+00:00", finished_utc="2026-11-04T20:00:00+00:00")
    _copy_control(copied, name="second", started_utc="2026-11-05T19:00:00+00:00",
                  finished_utc="2026-11-05T20:00:00+00:00",
                  keep=lambda rec: rec["task_cell"] in NR_FAR and 100 <= _template(rec) < 150)
    _org_check(copied, "a", "2026-11-05T00:00:00+00:00")
    r = hc.readings(copied, {}, True, allow_incomplete=True)
    assert any("comes before" in w for w in r["warnings"])
    assert any("comes after" in w for w in r["warnings"])


def test_a_check_only_after_the_run_is_warned_about_and_another_organization_too(copied):
    _copy_control(copied)
    _org_check(copied, "a", "2026-10-24T08:00:00+00:00", same=False)
    r = hc.readings(copied, {}, False, allow_incomplete=True)
    assert any("no org-check result comes before" in w for w in r["warnings"])
    assert any("another organization" in w for w in r["warnings"])


def test_the_summary_names_the_caveats(copied):
    _copy_control(copied)
    text = hc.summary(hc.readings(copied, {}, False, allow_incomplete=True))
    assert "Exploratory: no test" in text and "Not a model comparison" in text
    assert "came after R10's arms, not alongside them" in text
    assert "undercount" in text


def test_the_ranges_read_as_written():
    assert hc._ranges([0, 1, 2, 5, 7, 8]) == "0-2, 5, 7-8"
    assert hc._ranges([3]) == "3"


# --- reading 6, on a made-up transcript ---------------------------------------------------------

FACT = {"target": 568, "label": "I", "clues": [79, 558]}
PAYLOAD = {"system": "Follow the rules.",
           "messages": [{"role": "user", "content": "first obs"},
                        {"role": "assistant", "content": [{"type": "text", "text": "noted 568"}]},
                        {"role": "user", "content": "pick:\nA) 12\nI) 568\n"}]}


def _record(eid, cell=NR_FAR[0], template="main-000000"):
    # the need step is 3 (last evidence step 1, gap 2); one refusal, at step 2
    return {"episode_id": eid, "task_cell": cell, "template_id": template, "variant": "base",
            "need_correct": True, "n_requests": 4,
            "incomplete": [{"turn": 2, "pending_step": 2, "at_need": 0, "reason": "refusal:bio"}],
            "need_payload": {"assistant_carried": {"carried": True}},
            "designed": {"evidence_steps": [1], "gap_steps_latest": 2}}


def _line(eid, step, *, thinking=False, text="x", stop="end_turn"):
    content = ([{"type": "thinking", "thinking": ""}] if thinking else []) + [
        {"type": "text", "text": text}]
    return {"episode_id": eid, "kind": "step", "pending_step": step, "is_lookup_result": False,
            "payload": PAYLOAD, "response": {"content": content, "stop_reason": stop}}


def _resolved(*records):
    return {("W-n-0", rec["episode_id"], 0): hp.hh.Resolved(("W-n-0", rec["episode_id"], 0),
                                                            "counted", rec, "run", None)
            for rec in records}


def test_the_responses_reading_keeps_the_counted_episodes(tmp_path):
    path = tmp_path / CONTROL / "run" / "transcript.jsonl.gz"
    path.parent.mkdir(parents=True)
    lines = [_line("e1", 0, thinking=True), _line("e1", 1, thinking=True, text="saw 568"),
             _line("e1", 2, stop="refusal"), _line("e1", 3),
             _line("not-counted", 0, thinking=True)]
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for x in lines:
            f.write(json.dumps(x) + "\n")
    reading, hashes, missing = hc.responses(_resolved(_record("e1")), CONTROL, "W-n-0", tmp_path,
                                            {"e1": FACT})
    assert missing == [] and set(hashes) == {"e1#0", "e1#1", "e1#2", "e1#3"}
    assert (reading["episodes"], reading["runs"]) == (1, ["run"])
    assert (reading["responses"], reading["refused_responses"]) == (4, 1)
    assert (reading["with_thinking"], reading["responses_in_transcript"]) == (2, 4)
    assert reading["refused_by_turn"]["0-4"] == 1
    assert reading["need_first_request_thinking"] == [0, 1]
    assert set(reading["leak_check"]) == set(reading["at_need"]) == set(NR_FAR)
    assert reading["leak_check"][NR_FAR[0]]["target_in_need_option_line"] == 1
    assert reading["fact_value_in_replies"][NR_FAR[0]]["replies_holding_value"] == 1


def test_a_template_not_read_is_left_out_of_the_responses_reading(tmp_path):
    late = _record("e2", template="main-000150")
    resolved = hc.restrict(_resolved(late), [0, 1])
    assert resolved == {}
    reading, hashes, missing = hc.responses(resolved, CONTROL, "W-n-0", tmp_path, {})
    assert (hashes, missing) == ({}, []) and reading["episodes"] == 0


def test_responses_that_disagree_with_the_records_refuse(tmp_path):
    path = tmp_path / CONTROL / "run" / "transcript.jsonl.gz"
    path.parent.mkdir(parents=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(json.dumps(_line("e1", 0)) + "\n")
    with pytest.raises(hp.hh.Refusal, match="hold 1 responses, its records 4"):
        hc.responses(_resolved(_record("e1")), CONTROL, "W-n-0", tmp_path, {"e1": FACT})


def test_a_missing_transcript_is_named(tmp_path):
    reading, hashes, missing = hc.responses(_resolved(_record("e1")), CONTROL, "W-n-0", tmp_path, {})
    assert reading is None and hashes == {} and missing == ["run"]
