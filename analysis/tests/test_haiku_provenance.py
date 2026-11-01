"""analysis.haiku_provenance (R10's descriptive readings), checked on R9's committed W-n-0 run,
whose far-cell readings R9's output and replies reading report: the same code R10's two runs
will be read with. Copies of R9's run, renamed to R10's cells, check the two-arm path and the
far-only rule."""

from __future__ import annotations

import json
import shutil

import pytest

from analysis import haiku_provenance as hp
from harnesses import registered

ROOT = hp.REPO_ROOT
R9_RUN = "20261024T060051Z-W-n-0-claude-haiku-5-5"
FAR = registered.HAIKU_PROVENANCE_TASK_CELLS
PROV = registered.HAIKU_PROVENANCE_EXPERIMENT


@pytest.fixture(scope="module")
def r9():
    """R9's W-n-0 read as an arm. Without the raw transcripts (a checkout without results/raw)
    the output is PROVISIONAL, and §2.8's replay and the replies reading are skipped."""
    return hp.readings(ROOT, registered.HAIKU_NOTES_EXPERIMENT, ("W-n-0",), {},
                       sweep_closed=False, allow_incomplete=True)


def test_defaults_are_r10s():
    assert registered.HAIKU_PROVENANCE_CELLS == ("W-np-0", "W-npd-0")
    assert FAR == ("observed-nonrec-far", "observed-rec-far", "derived-nonrec-far",
                   "derived-rec-far")
    meta = json.loads((ROOT / hp.R9_OUTPUT / "meta.json").read_text(encoding="utf-8"))
    assert meta["runs"] == [R9_RUN] and meta["config"]["status"] == "FINAL"


def test_r9s_far_readings(r9):
    (arm,) = r9["arms"]
    rates = {c["task_cell"]: (c["successes"], c["n"]) for c in arm["cells"]}
    assert rates == {"observed-nonrec-far": (4, 200), "observed-rec-far": (198, 200),
                     "derived-nonrec-far": (9, 200), "derived-rec-far": (199, 200)}
    acc = {a["task_cell"]: a for a in arm["accounting"]}
    assert (acc["observed-nonrec-far"]["P_carried"]["carried"],
            acc["derived-nonrec-far"]["P_carried"]["carried"]) == (8, 72)
    assert (acc["observed-nonrec-far"]["used_given_carried"]["successes"],
            acc["derived-nonrec-far"]["used_given_carried"]["successes"]) == (4, 9)
    assert arm["choices_nr_far"] == {
        "observed-nonrec-far": {"episodes": 200, "chose_an_option": 4, "correct": 4},
        "derived-nonrec-far": {"episodes": 200, "chose_an_option": 9, "correct": 9}}
    assert sum(c["n"] for c in arm["costs"].values()) == 800


def test_r9s_reference_is_its_cited_output(r9):
    assert r9["r9"]["runs"] == [R9_RUN]
    assert [c["successes"] for c in r9["r9"]["cells"]] == [
        c["successes"] for c in r9["arms"][0]["cells"]]
    assert r9["model_strings"] == {"arms": ["claude-haiku-5-5"], "r9": ["claude-haiku-5-5"]}


def test_the_arm_against_itself_is_zero(r9):
    (by_tc,) = r9["contrasts"].values()
    assert set(by_tc) == set(FAR)
    for v in by_tc.values():
        assert v["pp"] == pytest.approx(0.0) and v["ci90"] == pytest.approx([0.0, 0.0])


def test_the_bootstrap_seed_is_r9s(r9):
    meta = json.loads((ROOT / hp.R9_OUTPUT / "meta.json").read_text(encoding="utf-8"))
    assert r9["bootstrap"]["seed"] == meta["seeds"]["bootstrap"]
    assert r9["bootstrap"]["resamples"] == 10_000


def test_the_replies_reading_reproduces_r9s(r9):
    """The replies reading on R9's own run equals R9's committed pattern tally."""
    if r9["accounting_check"]["missing_transcripts"]:
        assert r9["status"] == "PROVISIONAL" and r9["arms"][0]["replies_nr_far"] is None
        pytest.skip("no raw transcripts in this checkout")
    assert r9["status"] == "FINAL" and r9["accounting_check"]["bugs"] == []
    # the committed tally went through JSON, whose keys are strings
    fresh = json.loads(json.dumps(r9["arms"][0]["replies_nr_far"]))
    assert fresh == r9["r9"]["replies_nr_far"]
    t = r9["arms"][0]["replies_nr_far"]["derived-nonrec-far carried=True"]
    assert (t["failed"], t["failed_need_reply_disowns"], t["failed_retracted_before_need"]) == (
        63, 40, 45)


def test_the_summary_names_the_caveats(r9):
    text = hp.summary(r9)
    assert "Exploratory: no test" in text and "Not a model comparison" in text
    assert "mix the instruction with any change in serving" in text
    assert "undercount" in text


def test_no_run_folder_refuses(tmp_path):
    (tmp_path / "results" / "draw").mkdir(parents=True)
    with pytest.raises(hp.hh.Refusal, match=f"no {PROV}/ folder"):
        hp.readings(tmp_path, PROV, registered.HAIKU_PROVENANCE_CELLS, {}, sweep_closed=False)


def _copy_as(root, cell: str, far_only: bool) -> None:
    """R9's run under R10's experiment as a run of `cell`."""
    src = ROOT / "results" / registered.HAIKU_NOTES_EXPERIMENT / R9_RUN
    dst = root / "results" / PROV / f"{R9_RUN}-as-{cell}"
    dst.mkdir(parents=True)
    meta = json.loads((src / "meta.json").read_text(encoding="utf-8"))
    meta.update(experiment=PROV, cell_or_config=cell, run_id=dst.name)
    (dst / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    lines = []
    for line in (src / "episodes.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if far_only and rec["task_cell"] not in FAR:
            continue
        lines.append(json.dumps({**rec, "harness_cell": cell}))
    (dst / "episodes.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def copied(tmp_path):
    """A results root holding the draw, R9's run, its readings and replies reading, and no raw
    transcripts."""
    for rel in ("results/draw", f"results/{registered.HAIKU_NOTES_EXPERIMENT}/{R9_RUN}",
                hp.R9_OUTPUT):
        shutil.copytree(ROOT / rel, tmp_path / rel)
    (tmp_path / hp.R9_REPLIES).parent.mkdir(parents=True)
    shutil.copy(ROOT / hp.R9_REPLIES, tmp_path / hp.R9_REPLIES)
    return tmp_path


def test_two_arms_read_and_contrast(copied):
    for cell in registered.HAIKU_PROVENANCE_CELLS:
        _copy_as(copied, cell, far_only=True)
    with pytest.raises(hp.hh.Refusal, match="no raw transcript"):
        hp.readings(copied, PROV, registered.HAIKU_PROVENANCE_CELLS, {}, sweep_closed=False)
    r = hp.readings(copied, PROV, registered.HAIKU_PROVENANCE_CELLS, {}, sweep_closed=False,
                    allow_incomplete=True)
    assert r["status"] == "PROVISIONAL" and [a["cell"] for a in r["arms"]] == ["W-np-0",
                                                                              "W-npd-0"]
    assert all(a["counted_repeat_0"] == 800 and a["replies_nr_far"] is None for a in r["arms"])
    assert set(r["contrasts"]) == {"W-np-0 - W-n-0 (R9)", "W-npd-0 - W-n-0 (R9)",
                                   "W-npd-0 - W-np-0"}
    for by_tc in r["contrasts"].values():
        assert all(v["pp"] == pytest.approx(0.0) for v in by_tc.values())
    assert len(r["exclusions"]) == 8
    assert "W-npd-0" in hp.summary(r)


def test_an_incomplete_arm_refuses(copied):
    _copy_as(copied, "W-np-0", far_only=True)
    with pytest.raises(hp.hh.Refusal, match="incomplete"):
        hp.readings(copied, PROV, registered.HAIKU_PROVENANCE_CELLS, {}, sweep_closed=False)


def test_a_record_off_the_far_cells_refuses(copied):
    for cell in registered.HAIKU_PROVENANCE_CELLS:
        _copy_as(copied, cell, far_only=False)
    with pytest.raises(hp.hh.Refusal, match="far task cells only"):
        hp.readings(copied, PROV, registered.HAIKU_PROVENANCE_CELLS, {}, sweep_closed=False,
                    allow_incomplete=True)


def test_the_replies_reading_names_a_run_with_no_transcript(tmp_path):
    """Reading 5 never returns nothing silently: a run holding counted not-recoverable far
    records with no transcript is named, so the output is refused or PROVISIONAL."""
    _, resolved, _ = hp.read(ROOT, registered.HAIKU_NOTES_EXPERIMENT, ("W-n-0",), {},
                             sweep_closed=False)
    tally, missing = hp.replies(resolved, "W-n-0", registered.HAIKU_T, tmp_path,
                                registered.HAIKU_NOTES_EXPERIMENT)
    assert tally is None and missing == [R9_RUN]


def test_a_missing_cost_is_not_counted_as_zero():
    assert hp._mean([1.0, None, 3.0]) == (None, 1)
    assert hp._mean([1.0, 3.0]) == (2.0, 0)
    assert hp._mean([]) == (None, 0)


def test_r9s_costs_have_no_missing_value(r9):
    for c in r9["arms"][0]["costs"].values():
        assert c["cost_missing"] == 0 and c["output_tokens_missing"] == 0
        assert c["cost_usd_billed_mean"] > 0
