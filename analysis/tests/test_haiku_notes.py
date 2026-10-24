"""analysis.haiku_notes (R9's descriptive readings), checked on R8's committed W-0 runs, whose
readings the preprint reports (and analysis.replication_readings computes): the same code R9's
W-n-0 run will be read with."""

from __future__ import annotations

import json

import pytest

from analysis import haiku_notes as hn

R8_OUT = hn.REPO_ROOT / "results" / "persistgym_h1h3_haiku" / "20261019T003254Z" / "meta.json"


@pytest.fixture(scope="module")
def w0():
    links = json.loads(R8_OUT.read_text(encoding="utf-8"))["config"]["inputs"]["rerun_links"]
    return hn.readings(hn.REPO_ROOT, "persistgym_haiku", "W-0", dict(links), sweep_closed=True)


def test_defaults_are_r9s_run():
    from harnesses import registered
    assert (registered.HAIKU_NOTES_EXPERIMENT, registered.HAIKU_NOTES_CELL) == (
        "persistgym_haiku_notes", "W-n-0")


def test_r8s_w0_success_per_task_cell(w0):
    rates = {c["task_cell"]: (c["successes"], c["n"]) for c in w0["cells"]}
    assert w0["counted_repeat_0"] == 1600
    assert rates["observed-nonrec-far"] == (0, 200) and rates["derived-nonrec-far"] == (0, 200)
    assert all(v == (200, 200) for k, v in rates.items() if not k.endswith("nonrec-far"))
    assert sum(c["episodes_with_a_refusal"] for c in w0["cells"]) == 26  # W-0: 26 of 1,600
    far = next(c for c in w0["cells"] if c["task_cell"] == "observed-nonrec-far")
    assert far["interval_90"] == [0.0, 0.0]


def test_r8s_w0_chose_no_option_with_the_fact_evicted(w0):
    assert w0["choices_nr_far"] == {
        "observed-nonrec-far": {"episodes": 200, "chose_an_option": 0, "correct": 0},
        "derived-nonrec-far": {"episodes": 200, "chose_an_option": 0, "correct": 0}}


def test_the_accounting_is_luna_s_function(w0):
    nr_far = {a["task_cell"]: a for a in w0["accounting"]}
    assert nr_far["observed-nonrec-far"]["S_verbatim_0"] == 200
    assert nr_far["observed-nonrec-far"]["P_carried"] is None  # W-0 carries nothing


def test_the_bootstrap_seed_is_the_registered_one(w0):
    meta = json.loads(R8_OUT.read_text(encoding="utf-8"))
    assert w0["bootstrap"]["seed"] == meta["seeds"]["bootstrap"]
    assert w0["bootstrap"]["resamples"] == 10_000


def test_no_run_folder_refuses(tmp_path):
    (tmp_path / "results" / "draw").mkdir(parents=True)
    with pytest.raises(hn.hh.Refusal, match="no persistgym_haiku_notes/ folder"):
        hn.readings(tmp_path, "persistgym_haiku_notes", "W-n-0", {}, sweep_closed=False)


def test_the_within_haiku_contrast_reproduces_r8s_delta_h1(w0):
    """Read on W-0 itself, the penalty against F-0 is R8's: Penalty_NR +100, Penalty_R -1.0 and
    their difference R8's published Δ_H1, +101.0 pp [+100.0, +102.5] (same seed, same
    template resamples)."""
    wh = w0["within_haiku"]
    assert wh["penalty_against_f0_nr"]["pp"] == pytest.approx(100.0)
    assert wh["penalty_against_f0_r"]["pp"] == pytest.approx(-1.0)
    assert wh["difference"]["pp"] == pytest.approx(101.0)
    assert wh["difference"]["ci90"] == pytest.approx([100.0, 102.5])
    assert wh["lift_over_w0_nr"]["pp"] == pytest.approx(0.0)
    assert w0["model_strings"] == {"this_cell": ["claude-haiku-5-5"], "r8": ["claude-haiku-5-5"]}
