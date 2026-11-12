"""analysis.r12 (R12's descriptive readings, PREREG §17.12) and the block rule in
analysis.persistgym_h1h3's §2.8 replay, on synthetic fixtures.

R12's runs here are made from copies of committed R8 to R11 records, relabelled to R12's cells,
models and templates (as `test_haiku_control` reads R9's run as R11's control), so every
reading is known from the committed records. No raw transcript is copied, so those outputs are
PROVISIONAL. Readings 5 and 8's drops are checked on small made-up transcripts, and the block
replay on a made-up transcript where the two rules differ and on real episodes played by the
harness's W-b-0 with the fake model. No test reads an outcome of R12's own runs. The last tests
check that luna's and R8 to R11's helpers give their committed outputs."""

from __future__ import annotations

import copy
import gzip
import json
import shutil
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import cache

import numpy as np
import pytest

from analysis import haiku_control as hc
from analysis import haiku_notes as hn
from analysis import haiku_provenance as hp
from analysis import persistgym_h1h3 as hh
from analysis import r12
from harnesses import registered
from harnesses.cells import R12_CELLS
from harnesses.fake import padded_text
from persistgym.survival import block_keep_starts, window_keep_start

ROOT = r12.REPO_ROOT
HAIKU, SONNET_MODEL = registered.HAIKU_MODEL, registered.SONNET_MODEL
NOTES, SONNET, BLOCK = r12.NOTES, r12.SONNET, r12.BLOCK
NR_FAR = registered.HAIKU_CONTROL_TASK_CELLS
ALL8 = registered.HAIKU_TASK_CELLS
R9_META = (ROOT / "results" / registered.HAIKU_NOTES_EXPERIMENT
           / "20261024T060051Z-W-n-0-claude-haiku-5-5" / "meta.json")
CLOCK = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
NOTES_SOURCES = {"W-n-0": "R9 W-n-0", "W-np-0": "R10 W-np-0", "W-nd-0": "R10 W-npd-0",
                 "W-nx-0": "R11 W-n-0"}
SONNET_SOURCES = {"W-n-0": "R9 W-n-0", "W-np-0": "R10 W-np-0", "F-0": "R8 F-0"}


# --- the fixtures: R12's runs from committed records -------------------------------------------

@cache
def _resolution(which: str) -> dict:
    if which == "R9":
        return hp.r9_read(ROOT)[1]
    if which == "R10":
        return hc.r10_read(ROOT)[1]
    if which == "R11":
        return hp.read(ROOT, registered.HAIKU_CONTROL_EXPERIMENT, ("W-n-0",), {}, False)[1]
    return hn.r8_counted(ROOT)[1]


@cache
def source(name: str) -> dict[tuple[int, str], dict]:
    """A committed arm's counted repeat-0 base records, by (template, task cell)."""
    which, cell = name.split()
    return {(hh.template_index(r.record["template_id"]), r.record["task_cell"]): r.record
            for r in _resolution(which).values()
            if r.status == "counted" and r.record is not None and r.key[0] == cell
            and r.key[2] == 0 and (r.record.get("variant") or "base") == "base"}


def records(src: str, cell: str, templates, task_cells, offset: int) -> list[dict]:
    """`src`'s records of templates t - offset, relabelled to `cell` and template t."""
    out = []
    for t in templates:
        for tc in task_cells:
            rec = copy.deepcopy(source(src)[(t - offset, tc)])
            rec.update(template_id=f"main-{t:06d}", harness_cell=cell,
                       episode_id=hh.episode_id_of(cell, "base", t, tc))
            out.append(rec)
    return out


def success(src: str, templates, task_cell: str, offset: int) -> np.ndarray:
    return np.array([float(bool(source(src)[(t - offset, task_cell)]["need_correct"]))
                     for t in templates])


class Root:
    """A results root holding the draw and R8's runs and cited output, to which R12's runs are
    written."""

    def __init__(self, path):
        self.path = path
        self.n = 0

    def run(self, experiment, cell, recs, *, model=HAIKU, ending="COMPLETED", name=None) -> str:
        self.n += 1
        started = CLOCK + timedelta(minutes=10 * self.n)
        run_id = name or f"{started:%Y%m%dT%H%M%SZ}-{cell}-{model}"
        folder = self.path / "results" / experiment / run_id
        folder.mkdir(parents=True)
        meta = json.loads(R9_META.read_text(encoding="utf-8"))
        meta.update(experiment=experiment, run_id=run_id, cell_or_config=cell,
                    model_requested=model, model_returned=[model], exit_reason=ending,
                    started_utc=started.isoformat(),
                    finished_utc=(started + timedelta(minutes=9)).isoformat())
        meta["config"] = {**meta["config"], "harness_cell": cell,
                          "episode_ids": [r["episode_id"] for r in recs]}
        meta["parallel"] = {**meta["parallel"], "episodes_started": len(recs)}
        (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        (folder / "episodes.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs),
                                               encoding="utf-8")
        return run_id

    def notes(self, rounds=range(4), keep=None, change=None) -> list[str]:
        """Experiment 1 as registered: 4 rounds of 25 templates, the arms' order rotated."""
        ids, order = [], list(NOTES_SOURCES)
        for k in rounds:
            ts = range(200 + 25 * k, 225 + 25 * k)
            for j in range(4):
                cell = order[(j + k) % 4]
                recs = records(NOTES_SOURCES[cell], cell, ts, NR_FAR, 200)
                recs = [r for r in recs if keep is None or keep(cell, r)]
                if change:
                    change(cell, recs)
                ids.append(self.run(NOTES, cell, recs))
        return ids

    def sonnet(self) -> list[str]:
        return [self.run(SONNET, cell, records(src, cell, range(200, 225), NR_FAR, 200),
                         model=SONNET_MODEL) for cell, src in SONNET_SOURCES.items()]

    def block(self, keep=None) -> list[str]:
        """Experiment 3: R8's counted W-0 records as W-b-0, in 4 runs of 50 templates."""
        ids = []
        for k in range(4):
            recs = records("R8 W-0", "W-b-0", range(50 * k, 50 * k + 50), ALL8, 0)
            ids.append(self.run(BLOCK, "W-b-0", [r for r in recs if keep is None or keep(r)]))
        return ids

    def all(self):
        self.notes()
        self.sonnet()
        self.block()


@pytest.fixture(scope="module")
def committed(tmp_path_factory):
    root = tmp_path_factory.mktemp("committed")
    for rel in ("results/draw", f"results/{registered.HAIKU_EXPERIMENT}", hn.R8_OUTPUT):
        shutil.copytree(ROOT / rel, root / rel)
    return root


@pytest.fixture
def root(committed, tmp_path):
    shutil.copytree(committed, tmp_path / "root")
    return Root(tmp_path / "root")


def _read(root, links=None, closed=frozenset(), **kw):
    kw.setdefault("allow_incomplete", True)
    kw.setdefault("raw_root", root.path / "no-raw")
    return r12.readings(root.path, links or {}, closed, **kw)


def _arm(x: dict, name: str) -> dict:
    return next(a for a in x["arms"] if a["arm"] == name)


def _cell(arm: dict, tc: str) -> dict:
    return next(c for c in arm["cells"] if c["task_cell"] == tc)


def _seed() -> int:
    return hh.read_seed(ROOT / "results")[0] + hh.BOOT_SEED_OFFSET


# --- R12's registered readings -----------------------------------------------------------------

def test_the_experiments_are_r12s():
    assert r12.EXPERIMENTS == (NOTES, SONNET, BLOCK)
    assert (r12.templates_of(NOTES), r12.templates_of(SONNET), r12.templates_of(BLOCK)) == (
        range(200, 300), range(200, 225), range(200))
    assert r12.CONTRASTS[NOTES] == (("W-np-0", "W-n-0"), ("W-nd-0", "W-n-0"),
                                    ("W-nx-0", "W-n-0"), ("W-np-0", "W-nx-0"),
                                    ("W-np-0", "W-nd-0"))
    assert r12.CONTRASTS[SONNET] == (("W-np-0", "W-n-0"), ("F-0", "W-n-0"))
    assert r12.CONTRASTS[BLOCK] == (("W-b-0", "W-0 (R8)"), ("W-b-0", "F-0 (R8)"))
    assert r12.BOOT == 10_000


def test_the_templates_read_are_mapped_to_0_n_minus_1_except_in_experiment_3():
    assert r12.positions(NOTES, [205, 200, 201]) == ({200: 0, 201: 1, 205: 2}, 3)
    assert r12.positions(SONNET, list(range(200, 225))) == (
        {t: t - 200 for t in range(200, 225)}, 25)
    assert r12.positions(BLOCK, [0, 7, 199]) == ({0: 0, 7: 7, 199: 199}, registered.HAIKU_T)


def test_a_full_sweep_reads_every_registered_template(root):
    root.all()
    r = _read(root)
    assert r["status"] == "PROVISIONAL"
    assert all("no raw transcript" in x for x in r["incomplete"])
    ex = r["experiments"]
    assert [(ex[e]["templates_read"], ex[e]["templates"], ex[e]["resamples_over"])
            for e in r12.EXPERIMENTS] == [(100, "200-299", 100), (25, "200-224", 25),
                                          (200, "0-199", 200)]
    assert [a["arm"] for a in ex[NOTES]["arms"]] == ["W-n-0", "W-np-0", "W-nd-0", "W-nx-0"]
    assert [a["arm"] for a in ex[SONNET]["arms"]] == ["W-n-0", "W-np-0", "F-0"]
    assert [a["arm"] for a in ex[BLOCK]["arms"]] == ["W-b-0", "W-0 (R8)", "F-0 (R8)"]
    for e, sources, offset, ts in ((NOTES, NOTES_SOURCES, 200, range(200, 300)),
                                   (SONNET, SONNET_SOURCES, 200, range(200, 225))):
        for cell, src in sources.items():
            for tc in NR_FAR:
                c = _cell(_arm(ex[e], cell), tc)
                assert (c["successes"], c["n"]) == (int(success(src, ts, tc, offset).sum()),
                                                    len(ts))
    for name in ("W-b-0", "W-0 (R8)"):
        for tc in ALL8:
            c = _cell(_arm(ex[BLOCK], name), tc)
            assert (c["successes"], c["n"]) == (int(success("R8 W-0", range(200), tc, 0).sum()),
                                                200)
    assert all(a["responses"] is None for e in r12.EXPERIMENTS for a in ex[e]["arms"])
    assert r["bootstrap"]["seed"] == _seed()
    assert ex[BLOCK]["comparators"]["runs"] == [
        "20261018T141157Z-F-0-claude-haiku-5-5", "20261018T144829Z-W-0-claude-haiku-5-5",
        "20261018T154817Z-W-0-claude-haiku-5-5", "20261018T154918Z-W-0-claude-haiku-5-5"]


def test_experiment_1_bootstraps_over_its_templates_mapped_to_0_99(root):
    """Intervals and contrasts by a calculation here: 100 positions, not raw template numbers
    (indexing by 200-299 with T = 200 would fail or leave every template out)."""
    root.notes()
    r = _read(root)
    x = r["experiments"][NOTES]
    idx = hh.resample_indices(100, _seed(), 10_000)
    for tc in NR_FAR:
        s = {cell: success(src, range(200, 300), tc, 200) for cell, src in NOTES_SOURCES.items()}
        for cell in NOTES_SOURCES:
            means = s[cell][idx].mean(axis=1)
            assert _cell(_arm(x, cell), tc)["interval_90"] == pytest.approx(
                [np.percentile(means, 5), np.percentile(means, 95)])
        for a, b in r12.CONTRASTS[NOTES]:
            v = x["contrasts"][f"{a} - {b}"][tc]
            d = 100 * (s[a][idx].mean(axis=1) - s[b][idx].mean(axis=1))
            assert v["pp"] == pytest.approx(100 * (s[a].mean() - s[b].mean()))
            assert v["ci90"] == pytest.approx([np.percentile(d, 5), np.percentile(d, 95)])


def test_a_hole_in_one_arm_leaves_the_template_out_of_every_arm_and_names_it(root):
    def exclude(cell, recs):
        for x in recs:
            if (cell, x["template_id"], x["task_cell"]) == ("W-nd-0", "main-000210", NR_FAR[1]):
                x.update(excluded=True, exclusion_reason="made up")
    root.notes(change=exclude)
    r = _read(root)
    x = r["experiments"][NOTES]
    assert (x["templates_read"], x["templates"], x["resamples_over"]) == (99, "200-209, 211-299",
                                                                          99)
    (row,) = x["left_out"]
    assert (row["template"], row["arm"], row["task_cell"], row["status"]) == (
        210, "W-nd-0", NR_FAR[1], "excluded")
    assert "made up" in row["reason"]
    assert all(c["n"] == 99 for a in x["arms"] for c in a["cells"])
    assert sum(e["excluded_by_runner"] for e in x["exclusions"]) == 1
    idx = hh.resample_indices(99, _seed(), 10_000)
    ts = [t for t in range(200, 300) if t != 210]
    s = success("R9 W-n-0", ts, NR_FAR[0], 200)
    means = s[idx].mean(axis=1)
    assert _cell(_arm(x, "W-n-0"), NR_FAR[0])["interval_90"] == pytest.approx(
        [np.percentile(means, 5), np.percentile(means, 95)])
    assert "template 210, W-nd-0, derived-nonrec-far: excluded" in r12.summary(r)


def test_experiment_2_bootstraps_over_25_positions_with_its_two_contrasts(root):
    root.sonnet()
    r = _read(root)
    x = r["experiments"][SONNET]
    assert x["model"] == SONNET_MODEL and x["resamples_over"] == 25
    idx = hh.resample_indices(25, _seed(), 10_000)
    for tc in NR_FAR:
        s = {cell: success(src, range(200, 225), tc, 200) for cell, src in SONNET_SOURCES.items()}
        for a, b in (("W-np-0", "W-n-0"), ("F-0", "W-n-0")):
            v = x["contrasts"][f"{a} - {b}"][tc]
            d = 100 * (s[a][idx].mean(axis=1) - s[b][idx].mean(axis=1))
            assert v["pp"] == pytest.approx(100 * (s[a].mean() - s[b].mean()))
            assert v["ci90"] == pytest.approx([np.percentile(d, 5), np.percentile(d, 95)])
    assert set(x["contrasts"]) == {"W-np-0 - W-n-0", "F-0 - W-n-0"}
    assert _arm(x, "F-0")["choices_nr_far"] is None       # nothing is evicted in F-0
    assert r["experiments"][NOTES] is None and r["beside"] is None


def test_experiment_3_uses_r8s_resamples_and_reads_its_comparators(root):
    """W-b-0 here holds R8's W-0 records: W-b-0 minus R8's W-0 is 0 in every task cell, and minus
    R8's F-0 is R8's W-0 minus F-0 over the T = 200 resamples, by template number."""
    root.block(keep=lambda rec: rec["template_id"] != "main-000017")
    r = _read(root)
    x = r["experiments"][BLOCK]
    assert x["templates_read"] == 199 and x["resamples_over"] == 200
    assert {(z["template"], z["arm"], z["status"]) for z in x["left_out"]} == {
        (17, "W-b-0", "no record")}
    idx = hh.resample_indices(200, _seed(), 10_000)
    for tc in ALL8:
        zero = x["contrasts"]["W-b-0 - W-0 (R8)"][tc]
        assert zero["pp"] == pytest.approx(0.0) and zero["ci90"] == pytest.approx([0.0, 0.0])
        w, f = (success(src, range(200), tc, 0) for src in ("R8 W-0", "R8 F-0"))
        w[17] = f[17] = np.nan
        d = 100 * (np.nanmean(w[idx], axis=1) - np.nanmean(f[idx], axis=1))
        v = x["contrasts"]["W-b-0 - F-0 (R8)"][tc]
        assert v["pp"] == pytest.approx(100 * (np.nanmean(w) - np.nanmean(f)))
        assert v["ci90"] == pytest.approx([np.nanpercentile(d, 5), np.nanpercentile(d, 95)])
        assert _cell(_arm(x, "F-0 (R8)"), tc)["n"] == 199


def test_reading_6_rounds_and_run_times(root):
    ids = root.notes()
    x = _read(root)["experiments"][NOTES]
    rows = x["rounds"]["success"]
    assert len(rows) == 4 * 4 * 2 and {r["templates"] for r in rows} == {
        "200-224", "225-249", "250-274", "275-299"}
    for cell in NOTES_SOURCES:
        for tc in NR_FAR:
            mine = [r for r in rows if r["arm"] == cell and r["task_cell"] == tc]
            assert sum(r["successes"] for r in mine) == _cell(_arm(x, cell), tc)["successes"]
            assert [r["n"] for r in mine] == [25, 25, 25, 25]
    runs = x["rounds"]["runs"]
    assert [r["run_id"] for r in runs] == ids                # in start order
    assert runs[0]["started_utc"] == "2026-11-12T08:10:00+00:00"
    assert runs[0]["finished_utc"] == "2026-11-12T08:19:00+00:00"
    assert [r["arm"] for r in runs[:5]] == ["W-n-0", "W-np-0", "W-nd-0", "W-nx-0", "W-np-0"]
    assert runs[4]["templates"] == "225-249"


def test_reading_7_sets_sonnet_beside_haikus_experiment_1_on_200_224(root):
    root.notes()
    root.sonnet()
    r = _read(root)
    b = r["beside"]
    assert (b["templates"], b["n_templates"]) == ("200-224", 25)
    assert [(a["model"], a["arm"]) for a in b["arms"]] == [
        *((SONNET_MODEL, c) for c in SONNET_SOURCES), *((HAIKU, c) for c in NOTES_SOURCES)]
    haiku = next(a for a in b["arms"] if a["model"] == HAIKU and a["arm"] == "W-np-0")
    sonnet = next(a for a in b["arms"] if a["model"] == SONNET_MODEL and a["arm"] == "W-np-0")
    for tc in NR_FAR:
        want = int(success("R10 W-np-0", range(200, 225), tc, 200).sum())
        assert [c["successes"] for c in haiku["cells"] if c["task_cell"] == tc] == [want]
        assert [c["successes"] for c in sonnet["cells"] if c["task_cell"] == tc] == [want]
    assert all(set(x) == {"task_cell", "P_carried", "used_given_carried"}
               for a in b["arms"] for x in a["accounting"])
    assert "contrast" not in json.dumps(b)
    assert "no contrast between the models" in r12.summary(r)


def test_reading_8_cost_and_context(root):
    root.block()
    x = _read(root)["experiments"][BLOCK]
    cc = x["cost_and_context"]
    arms = {a["arm"]: a for a in cc["arms"]}
    assert set(arms) == {"W-b-0", "W-0 (R8)", "F-0 (R8)"}
    assert arms["W-b-0"]["costs"] == arms["W-0 (R8)"]["costs"]
    recs = [source("R8 F-0")[(t, NR_FAR[0])] for t in range(200)]
    c = arms["F-0 (R8)"]["costs"][NR_FAR[0]]
    assert c["n"] == 200
    assert c["cost_usd_billed_mean"] == pytest.approx(
        np.mean([x["cost_usd_billed_est"] for x in recs]))
    assert c["input_tokens_mean"] == pytest.approx(np.mean([x["usage"]["input_tokens"]
                                                            for x in recs]))
    assert c["cache_read_share"] == pytest.approx(
        sum(x["usage"]["cached_input_tokens"] for x in recs)
        / sum(x["usage"]["input_tokens"] for x in recs))
    assert arms["F-0 (R8)"]["costs"]["all"]["n"] == 1600
    near = [tc for tc in ALL8 if tc.endswith("-near")]
    assert set(arms["W-b-0"]["near_need_payload_S_false"]) == set(near)
    for tc in near:
        want = sum(source("R8 W-0")[(t, tc)]["need_payload"]["S"] is False for t in range(200))
        assert arms["W-b-0"]["near_need_payload_S_false"][tc] == {"n": 200, "S_false": want}
        assert arms["F-0 (R8)"]["near_need_payload_S_false"][tc]["S_false"] == 0
    assert cc["block_drops"] is None                     # no transcripts here
    assert any("reading 8's drops cannot be made" in z for z in _read(root)["incomplete"])


def test_reading_5_costs_and_refusals_from_the_records(root):
    root.sonnet()
    x = _read(root)["experiments"][SONNET]
    f0 = _arm(x, "F-0")
    recs = [source("R8 F-0")[(t, NR_FAR[1])] for t in range(25)]
    c = f0["costs"][NR_FAR[1]]
    assert c["output_tokens_mean"] == pytest.approx(np.mean([x["usage"]["output_tokens"]
                                                             for x in recs]))
    assert "all" not in f0["costs"]


# --- refusals before any reading -------------------------------------------------------------

def test_a_record_off_the_registered_task_cells_refuses(root):
    recs = records("R8 W-0", "W-n-0", range(200, 201), ("observed-nonrec-near",), 200)
    root.run(NOTES, "W-n-0", recs)
    with pytest.raises(hh.Refusal, match="plays observed-nonrec-far, derived-nonrec-far only"):
        _read(root)


def test_a_record_off_the_registered_templates_refuses(root):
    root.run(SONNET, "F-0", records("R8 F-0", "F-0", range(225, 226), NR_FAR, 200),
             model=SONNET_MODEL)
    with pytest.raises(hh.Refusal, match="main templates 200-224 only"):
        _read(root)


def test_a_run_of_another_model_in_an_experiment_refuses(root):
    root.run(NOTES, "W-n-0", records("R9 W-n-0", "W-n-0", range(200, 201), NR_FAR, 200),
             model=SONNET_MODEL)
    with pytest.raises(hh.Refusal, match="not R12's runs of it"):
        _read(root)


def test_a_cell_off_the_experiment_refuses(root):
    root.run(SONNET, "W-nd-0", records("R10 W-npd-0", "W-nd-0", range(200, 201), NR_FAR, 200),
             model=SONNET_MODEL)
    with pytest.raises(hh.Refusal, match="is not one of"):
        _read(root)


@pytest.mark.parametrize("closed", [frozenset(), frozenset({NOTES})])
def test_an_api_error_awaiting_its_re_run_refuses_even_with_the_sweep_closed(root, closed):
    def fail(cell, recs):
        if cell == "W-np-0" and recs[0]["template_id"] == "main-000225":
            recs[3].update(exit_reason="API_ERROR", need_correct=False, error="made up")
    root.notes(change=fail)
    with pytest.raises(hh.Refusal, match="await their §13 re-run"):
        _read(root, closed=closed, allow_incomplete=False)
    r = _read(root, closed=closed)
    assert any("await their §13 re-run" in z for z in r["incomplete"])


def test_a_short_sweep_needs_the_researchers_close(root):
    """R12 registers no stop that closes a sweep: a run that ended early is continued, so the
    last round missing refuses until the researcher closes experiment 1's sweep."""
    root.notes(rounds=range(3))
    with pytest.raises(hh.Refusal, match="50 of 200 repeat-0 episodes have no record"):
        _read(root, allow_incomplete=False)
    r = _read(root)
    assert any("have no record" in z for z in r["incomplete"])
    closed = _read(root, closed={NOTES})
    x = closed["experiments"][NOTES]
    assert (x["templates_read"], x["templates_never_played"]) == (75, 25)
    assert any("never played" in d for d in x["deviations"])
    assert not any("have no record" in z for z in closed["incomplete"])


def test_a_declared_re_run_completes_the_sweep(root, monkeypatch):
    def fail(cell, recs):
        if cell == "W-np-0" and recs[0]["template_id"] == "main-000225":
            recs[3].update(exit_reason="API_ERROR", need_correct=False, error="made up")
    ids = root.notes(change=fail)
    original = ids[4]
    rerun = root.run(NOTES, "W-np-0", records("R10 W-np-0", "W-np-0", range(226, 227), NR_FAR,
                                              200))
    with pytest.raises(hh.Refusal, match="not declared as a re-run"):
        _read(root)
    _final(monkeypatch)
    r = _read(root, links={rerun: original})
    x = r["experiments"][NOTES]
    assert x["templates_read"] == 100 and x["left_out"] == []
    assert not any(z.startswith("Experiment 1") for z in r["incomplete"])
    row = next(z for z in x["runs"] if z["run_id"] == rerun)
    assert (row["records"], row["records_counted"]) == (2, 1)   # the API error's key only
    with pytest.raises(hh.Refusal, match="is not a run of R12's experiments"):
        _read(root, links={"nowhere": original})


def test_an_experiment_with_no_run_refuses_unless_allowed(root):
    root.notes()
    with pytest.raises(hh.Refusal, match="no run under results/persistgym_sonnet_r12/"):
        _read(root, allow_incomplete=False)
    r = _read(root)
    assert r["experiments"][SONNET] is None and r["experiments"][BLOCK] is None
    assert r["beside"] is None
    assert "Not read: no run." in r12.summary(r)


def test_an_experiment_with_no_finished_template_is_not_read(root):
    root.run(SONNET, "W-n-0", records("R9 W-n-0", "W-n-0", range(200, 225), NR_FAR, 200),
             model=SONNET_MODEL)
    r = _read(root)
    x = r["experiments"][SONNET]
    assert x["templates_read"] == 0 and "arms" not in x
    assert any("no template finished" in z for z in r["incomplete"])
    assert "Not read: no template finished" in r12.summary(r)


def test_an_unknown_experiment_to_close_refuses(root):
    with pytest.raises(hh.Refusal, match="names no R12 experiment"):
        _read(root, closed={"persistgym_haiku"})


def _final(monkeypatch):
    monkeypatch.setattr(hh, "accounting_check", lambda runs, *a, **k: {
        "checked": len(runs), "bugs": [], "missing_transcripts": [], "warnings": [], "runs": []})
    monkeypatch.setattr(r12, "responses", lambda *a, **k: (None, []))
    monkeypatch.setattr(r12, "block_drops", lambda *a, **k: (None, [], []))


def test_with_everything_present_the_status_is_final(root, monkeypatch):
    root.all()
    _final(monkeypatch)
    r = r12.readings(root.path, {}, frozenset())
    assert r["status"] == "FINAL" and r["incomplete"] == []
    assert r12.summary(r).count("**FINAL.**") == 1


def test_a_bug_in_the_replay_stops_the_analysis_even_as_provisional(root, monkeypatch):
    root.sonnet()
    monkeypatch.setattr(hh, "accounting_check", lambda *a, **k: {
        "checked": 1, "bugs": ["made up"], "missing_transcripts": [], "warnings": []})
    with pytest.raises(hh.AccountingBug, match="made up"):
        _read(root)


def test_the_summary_names_the_caveats_and_every_reading(root):
    root.all()
    text = r12.summary(_read(root))
    for needle in ("Exploratory: no test", "Not a model comparison", "not concurrent with R8's",
                   "**1. Success:**", "**2. §2.8 accounting**", "**3. Choices",
                   "**4. Contrasts**", "**5. Responses:**", "**6. Rounds**",
                   "## 7. Experiment 2 beside Haiku", "**8. Cost and context**",
                   "W-b-0 - F-0 (R8), derived-rec-near"):
        assert needle in text, needle
    assert "PROVISIONAL" in text


def test_main_writes_its_three_files(root, tmp_path):
    root.sonnet()
    out = tmp_path / "out"
    assert r12.main(["--results-root", str(root.path), "--allow-incomplete", "--raw-root",
                     str(tmp_path / "raw"), "--out-dir", str(out)]) == 0
    assert {p.name for p in out.iterdir()} == set(r12.OUTPUTS)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["paid_calls"] == 0 and meta["config"]["status"] == "PROVISIONAL"
    assert r12.main(["--results-root", str(root.path), "--raw-root", str(tmp_path / "raw"),
                     "--no-write"]) == 2


# --- readings 5 and 8 on made-up transcripts ---------------------------------------------------

FACT = {"target": 568, "label": "I", "clues": [79, 558]}
PAYLOAD = {"system": "Follow the rules.",
           "messages": [{"role": "user", "content": "first obs"},
                        {"role": "assistant", "content": [{"type": "text", "text": "noted 568"}]},
                        {"role": "user", "content": "pick:\nA) 12\nI) 568\n"}]}


def _record(eid, cell=NR_FAR[0], template="main-000200", n_requests=4, refusals=("bio",)):
    return {"episode_id": eid, "task_cell": cell, "template_id": template, "variant": "base",
            "need_correct": True, "n_requests": n_requests,
            "incomplete": [{"turn": 2, "pending_step": 2, "at_need": 0, "reason": f"refusal:{c}"}
                           for c in refusals],
            "need_payload": {"assistant_carried": {"carried": True}},
            "designed": {"evidence_steps": [1], "gap_steps_latest": 2}}


def _line(eid, step, *, thinking=False, text="x", stop="end_turn", info=None):
    content = ([{"type": "thinking", "thinking": ""}] if thinking else []) + [
        {"type": "text", "text": text}]
    return {"episode_id": eid, "kind": "step", "turn": step, "pending_step": step,
            "is_lookup_result": False, "info": info or {}, "payload": PAYLOAD,
            "response": {"content": content, "stop_reason": stop}}


def _resolved(cell, *recs, run="run"):
    return {(cell, rec["episode_id"], 0): hh.Resolved((cell, rec["episode_id"], 0), "counted",
                                                      rec, run, None) for rec in recs}


def _write(path, lines):
    path.parent.mkdir(parents=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for x in lines:
            f.write(json.dumps(x) + "\n")


def test_reading_5_from_a_transcript(tmp_path):
    _write(tmp_path / NOTES / "run" / "transcript.jsonl.gz",
           [_line("e1", 0, thinking=True), _line("e1", 1, thinking=True, text="saw 568"),
            _line("e1", 2, stop="refusal"), _line("e1", 3), _line("other", 0, thinking=True)])
    rec = _record("e1")
    arm = r12.Arm("W-n-0", "W-n-0", HAIKU, NOTES, _resolved("W-n-0", rec), [])
    reading, missing = r12.responses(arm, arm.resolved, NR_FAR, 300, tmp_path, {"e1": FACT})
    assert missing == []
    assert (reading["episodes"], reading["responses"], reading["refused_responses"]) == (1, 4, 1)
    assert reading["refusal_categories"] == {"refusal:bio": 1}
    assert (reading["with_thinking"], reading["responses_in_transcript"]) == (2, 4)
    # the need step's first request (step 3) retains one reply, "noted 568", of 9 characters
    assert reading["at_need"][NR_FAR[0]] == {"episodes": 1, "retained_replies_median": 1,
                                             "retained_reply_chars_median": 9.0}
    assert reading["at_need"][NR_FAR[1]]["episodes"] == 0


def test_reading_5_names_a_missing_transcript_and_refuses_a_disagreeing_one(tmp_path):
    rec = _record("e1")
    arm = r12.Arm("W-n-0", "W-n-0", HAIKU, NOTES, _resolved("W-n-0", rec), [])
    assert r12.responses(arm, arm.resolved, NR_FAR, 300, tmp_path, {}) == (None, ["run"])
    _write(tmp_path / NOTES / "run" / "transcript.jsonl.gz", [_line("e1", 0)])
    with pytest.raises(hh.Refusal, match="hold 1 responses, its records 4"):
        r12.responses(arm, arm.resolved, NR_FAR, 300, tmp_path, {"e1": FACT})


def test_reading_8_counts_the_block_drops_per_episode(tmp_path):
    def info(drop):
        return {"truncation": "block", "block_drop": drop}
    near = "observed-nonrec-near"
    a, b = _record("a", template="main-000000"), _record("b", cell=near, template="main-000000")
    _write(tmp_path / BLOCK / "run" / "transcript.jsonl.gz",
           [_line("a", 0, info=info(False)), _line("a", 1, info=info(True)),
            _line("a", 2, info=info(True)), _line("b", 0, info=info(False)),
            _line("b", 1, info={"block_drop": True}), _line("x", 0, info=info(True))])
    arm = r12.Arm("W-b-0", "W-b-0", HAIKU, BLOCK, _resolved("W-b-0", a, b), [])
    drops, missing, odd = r12.block_drops(arm, arm.resolved, (NR_FAR[0], near), 200, tmp_path)
    assert missing == [] and odd == ["run: b turn 1"]
    assert drops[NR_FAR[0]] == {"episodes": 1, "drops_per_episode": 2.0, "episodes_with_a_drop": 1,
                                "distribution": {"2": 1}}
    assert drops["all"]["drops_per_episode"] == 1.5
    assert r12.block_drops(arm, arm.resolved, (NR_FAR[0],), 200, tmp_path / "none")[1] == ["run"]


def test_the_generators_facts_cover_r12s_templates_and_task_cells():
    from analysis import haiku_provenance_extras as hpe
    facts = hpe.episode_facts(range(200, 201), ("observed-nonrec-far", "derived-rec-near"))
    assert sorted(facts) == ["main-000200/derived-rec-near/base",
                             "main-000200/observed-nonrec-far/base"]
    assert all(set(f) == {"target", "label", "clues"} for f in facts.values())
    assert facts["main-000200/observed-nonrec-far/base"]["clues"] == []


def test_cost_row_never_counts_a_missing_value_as_zero():
    recs = [{"cost_usd_billed_est": 0.1, "usage": {"input_tokens": 100, "cached_input_tokens": 80,
                                                   "output_tokens": 5}},
            {"cost_usd_billed_est": None, "usage": {"input_tokens": 300,
                                                    "cached_input_tokens": None}}]
    row = r12.cost_row(recs)
    assert row["cost_usd_billed_mean"] is None and row["cost_missing"] == 1
    assert row["input_tokens_mean"] == 200.0 and row["cache_read_share"] is None
    assert row["output_tokens_missing"] == 1
    assert r12.cost_row(recs[:1])["cache_read_share"] == pytest.approx(0.8)
    w = r12.missing_values({BLOCK: {"arms": [{"arm": "W-b-0", "costs": {"all": row}}]}})
    assert any("1 of 2 counted records have no billed cost" in x for x in w)


# --- the block rule in §2.8's replay ----------------------------------------------------------

# W = 60 project tokens, a 5-token system prompt, 10-token observations and 2-token replies, need
# step 10. The sliding window keeps turns 7-10 at the need step. The block rule keeps its start
# until the context passes 60, then drops to the earliest turn whose context fits in 30: starts
# 0 (turns 0-3), 3 (4-6), 6 (7-9) and 9 (10-11). So observed-near evidence at step 8 survives the
# sliding window and is dropped by the block rule.
W, SYS, OBS, REP, NEED = 60, 5, 10, 2, 10


@cache
def _pad(prefix: str, n: int) -> str:
    return padded_text(prefix, n)


def _starts(rule: str, turns: int = NEED + 2) -> list[int]:
    obs, rep = [OBS] * turns, [REP] * (turns - 1)
    if rule == "block":
        return block_keep_starts(obs, rep, W, SYS)
    keep, out = 0, []
    for j in range(turns):
        keep = max(keep, window_keep_start(obs[: j + 1], rep[:j], W, SYS))
        out.append(keep)
    return out


def _block_transcript(eid: str, rule: str = "block"):
    """The step requests of one episode as a W-b-0 session sends them (Messages wire)."""
    starts = _starts(rule)
    reply = _pad("ok", REP)
    def text(s: str) -> list[dict]:
        return [{"type": "text", "text": s}]
    for i in range(NEED + 2):
        msgs = []
        for t in range(starts[i], i):
            msgs += [{"role": "user", "content": text(_pad(f"Obs {t}.", OBS))},
                     {"role": "assistant", "content": text(reply)}]
        msgs.append({"role": "user", "content": text(_pad(f"Obs {i}.", OBS))})
        yield {"episode_id": eid, "kind": "step", "turn": i, "pending_step": i,
               "is_lookup_result": False,
               "info": {"keep_start": starts[i], "truncation": "block",
                        "block_drop": i > 0 and starts[i] != starts[i - 1]},
               "payload": {"system": _pad("System prompt.", SYS), "messages": msgs},
               "response": {"content": text(reply), "stop_reason": "end_turn"}}


SETTINGS = {"W": W, "count_system": True, "notes_separator": "\n", "tokenizer": "o200k_base"}


def _block_run(tmp_path, s_verbatim: bool, cell: str = "W-b-0"):
    eid = hh.episode_id_of(cell, "base", 0, "observed-nonrec-near")
    rec = {"episode_id": eid, "task_cell": "observed-nonrec-near", "template_id": "main-000000",
           "variant": "base", "harness_cell": cell, "exit_reason": "DONE",
           "need_payload": {"S": s_verbatim}, "need_info": {"keep_start": _starts("block")[NEED]},
           "designed": {"evidence_steps": [8], "gap_steps_latest": 2}}
    _write(tmp_path / BLOCK / "r" / "transcript.jsonl.gz", list(_block_transcript(eid)))
    return hh.Run(run_id="r", folder=tmp_path, cell=cell, variants=("base",), repeat_index=0,
                  started=CLOCK, exit_reason="COMPLETED", model_returned=[HAIKU], records=[rec],
                  window=SETTINGS), eid


def test_the_two_rules_differ_on_the_made_up_episode():
    assert _starts("slide")[NEED] == 7
    assert _starts("block") == [0, 0, 0, 0, 3, 3, 3, 6, 6, 6, 9, 9]


def test_the_block_replay_where_the_sliding_one_differs(tmp_path):
    _, eid = _block_run(tmp_path, False)
    wanted = {eid: {"need_step": NEED, "evidence_steps": [8]}}
    path = tmp_path / BLOCK / "r" / "transcript.jsonl.gz"
    got = hh.window_recheck(path, wanted, notes=False, settings=SETTINGS, api=hh.MESSAGES_API,
                            truncation="block")[eid]
    assert (got["S"], got["keep"], got["user_messages_sent"], got["user_messages_expected"]) == (
        False, 9, 2, 2)
    slide = hh.window_recheck(path, wanted, notes=False, settings=SETTINGS, api=hh.MESSAGES_API)
    assert (slide[eid]["S"], slide[eid]["keep"], slide[eid]["user_messages_expected"]) == (
        True, 7, 4)
    with pytest.raises(ValueError, match="unknown truncation"):
        hh.window_recheck(path, wanted, notes=False, settings=SETTINGS, truncation="other")


def test_the_accounting_check_replays_w_b_0_by_the_block_rule(tmp_path, monkeypatch):
    run, _ = _block_run(tmp_path, False)
    check = hh.accounting_check([run], tmp_path, BLOCK, hh.MESSAGES_API)
    assert (check["checked"], check["bugs"], check["warnings"]) == (1, [], [])
    # the sliding replay of the same run would call it a bug
    monkeypatch.setitem(hh.SPECS, "W-b-0", replace(hh.SPECS["W-b-0"], truncation="slide"))
    (bug,) = hh.accounting_check([run], tmp_path, BLOCK, hh.MESSAGES_API)["bugs"]
    assert "S_verbatim = 0, but the drop-oldest replay gives 1 (window start 7" in bug


def test_a_record_that_disagrees_with_the_block_replay_is_a_bug(tmp_path):
    run, _ = _block_run(tmp_path, True)
    (bug,) = hh.accounting_check([run], tmp_path, BLOCK, hh.MESSAGES_API)["bugs"]
    assert "S_verbatim = 1, but the block replay gives 0 (window start 9" in bug


def test_a_far_w_b_0_episode_with_its_fact_in_the_window_is_a_bug():
    rec = {"episode_id": "e", "task_cell": "observed-nonrec-far", "need_payload": {"S": True}}
    run = hh.Run(run_id="r", folder=ROOT, cell="W-b-0", variants=("base",), repeat_index=0,
                 started=CLOCK, exit_reason="COMPLETED", model_returned=[HAIKU], records=[rec],
                 window=SETTINGS)
    assert hh.far_window_bugs([run]) and "W-b-0" in hh.WINDOW_CELLS


def test_the_block_replay_matches_the_harness_on_real_episodes(tmp_path, monkeypatch):
    """Real episodes (generator, small volume) played on the Messages wire by the harness's
    W-b-0 with the fake model: the block replay agrees with the runner's S, window start and
    payload in every episode, and the sliding replay does not."""
    from harnesses.config import HarnessConfig
    from harnesses.fake import FakeModel
    from harnesses.runner import run_batch
    from persistgym.config import GeneratorConfig
    from persistgym.episode import ALL_CELLS
    from persistgym.render import generate

    small = GeneratorConfig(W_tokens=6_400, v_tokens=400, assumed_max_reply_tokens=200)
    eps = [ep for _, e in generate("main", range(2), small, ALL_CELLS, ("base",)) for ep in e]
    long_reply = _pad("Notes:", 1_500) + "\nACTION: ack(none)"
    short = _pad("Notes:", 150) + "\nACTION: ack(none)"

    def reply(payload, i):
        if i % 6 == 4:
            return "ACTION: lookup(record)"
        return long_reply if i % 5 == 0 else short

    cfg = HarnessConfig(model=HAIKU, reasoning_effort="medium", service_tier="standard")
    results = tmp_path / "results"
    run_batch(eps, R12_CELLS["W-b-0"], cfg, FakeModel(reply, report_thinking_tokens=False),
              experiment=BLOCK, run_id="r-W-b-0", results_root=results, raw_root=results / "raw")
    monkeypatch.setattr(registered, "HAIKU_GENERATOR_HASH", eps[0].config_hash)
    runs = r12.discover(tmp_path, BLOCK)
    assert len(runs) == 1 and runs[0].cell == "W-b-0"
    check = hh.accounting_check(runs, results / "raw", BLOCK, hh.MESSAGES_API)
    assert check["bugs"] == [] and check["warnings"] == []
    assert check["checked"] == len(eps)
    with gzip.open(results / "raw" / BLOCK / "r-W-b-0" / "transcript.jsonl.gz", "rt",
                   encoding="utf-8") as fh:
        lines = [json.loads(x) for x in fh]
    assert sum(bool(x["info"].get("block_drop")) for x in lines) > 0
    assert all(x["info"]["truncation"] == "block" for x in lines if x["kind"] == "step")
    monkeypatch.setitem(hh.SPECS, "W-b-0", replace(hh.SPECS["W-b-0"], truncation="slide"))
    slide = hh.accounting_check(runs, results / "raw", BLOCK, hh.MESSAGES_API)
    assert slide["bugs"] or slide["warnings"]


# --- luna's and R8 to R11's helpers are unchanged ------------------------------------------------

def test_the_cell_lists_only_gain_r12s_cells():
    assert hh.WINDOW_CELLS == ("W-0", "W-n-0", "W-np-0", "W-npd-0", "W-nd-0", "W-nx-0", "W-b-0")
    assert hh.CARRY_CELLS == ("W-n-0", "Σ-n-0", "W-np-0", "W-npd-0", "W-nd-0", "W-nx-0")
    assert hh.SUMMARY_CELLS == ("Σ-n-0",)
    assert {c: hh.SPECS[c].truncation for c in hh.SPECS if c not in R12_CELLS} == {
        c: "slide" for c in hh.SPECS if c not in R12_CELLS}
    assert hh.s_planned("W-b-0", "near") == 1 and hh.s_planned("W-b-0", "far") == 0


def _json(x):
    return json.loads(json.dumps(hh._clean(x), default=hh._json_default))


def test_lunas_committed_tables_are_reproduced():
    """luna's accounting, success and exclusion tables, from its committed records, equal its
    cited FINAL output."""
    out = ROOT / hh.LUNA_CITED_OUTPUT
    cfg = json.loads((out / "meta.json").read_text(encoding="utf-8"))["config"]
    h = json.loads((out / "h1h3.json").read_text(encoding="utf-8"))
    prof = hh.profile()
    found, _ = hh.discover(ROOT / "results", cfg["inputs"]["input_list"], prof)
    resolved, _ = hh.resolve(found, cfg["rerun_links"],
                             sweep_closed=cfg["sweep_closed"] is not None, echo=prof.echo,
                             stopped={})
    table, _ = hh.episode_table(resolved, prof.api)
    prim = table[(table.repeat == 0) & (table.status == "counted")
                 & (table.template < cfg["templates"])].reset_index(drop=True)
    assert _json(hh.accounting(prim, prof.cells)) == h["accounting"]
    assert _json(hh.cell_table(prim, prof.kinds, stopped=not prof.echo)) == h["cells"]
    assert _json(hh.exclusion_table(resolved, cfg["templates"], prof.kinds,
                                    prof.echo)) == h["exclusions"]


def test_r8s_committed_tables_are_reproduced():
    """R8's accounting, success and exclusion tables, from its committed records, equal its
    cited FINAL output."""
    h = json.loads((ROOT / hn.R8_OUTPUT / "h1h3.json").read_text(encoding="utf-8"))
    _, resolved = hn.r8_counted(ROOT)
    prof = hh.profile(HAIKU)
    table, _ = hh.episode_table(resolved, prof.api)
    prim = table[(table.repeat == 0) & (table.status == "counted")
                 & (table.template < prof.T)].reset_index(drop=True)
    assert _json(hh.accounting(prim, prof.cells)) == h["accounting"]
    assert _json(hh.cell_table(prim, prof.kinds, stopped=True)) == h["cells"]
    assert _json(hh.exclusion_table(resolved, prof.T, prof.kinds, prof.echo)) == h["exclusions"]


def test_r11s_committed_readings_are_reproduced(tmp_path):
    """R11's FINAL readings that need no transcript (R9's, R10's and R11's arms) equal its
    committed output."""
    out = next((ROOT / "results" / "haiku_control").glob("*/control.json"))
    want = json.loads(out.read_text(encoding="utf-8"))
    r = hc.readings(ROOT, {}, False, raw_root=tmp_path, allow_incomplete=True)
    assert (r["templates"], r["templates_read"]) == (want["templates"], want["templates_read"])
    for got, w in zip(r["arms"], want["arms"], strict=True):
        for key in ("arm", "counted_repeat_0", "cells", "accounting", "choices_nr_far", "costs"):
            assert _json(got[key]) == w[key], (got["arm"], key)
    assert _json(r["contrasts"]) == want["contrasts"]
    assert _json(r["exclusions"]) == want["exclusions"]
