"""Run matrix (PREREG §4.6; D11 option A): which task cells run on which templates."""

from __future__ import annotations

import pytest

from harnesses.matrix import DERIVED_FAR, OBSERVED_FAR, RunMatrix
from harnesses.tests.conftest import SMALL
from persistgym.episode import ALL_CELLS
from persistgym.render import generate


def _full(split, start, n, cells=ALL_CELLS):
    return [ep for _, eps in generate(split, range(start, start + n), SMALL, cells, ("base",))
            for ep in eps]


def test_d11_counts():
    m = RunMatrix.d11(120)
    assert dict(m.templates) == {**dict.fromkeys(DERIVED_FAR, 120),
                                 **dict.fromkeys(OBSERVED_FAR, 40)}
    assert (m.n_templates, m.n_episodes) == (120, 320)  # 640 episodes over F-r and F-0
    assert m.block_warnings(0) == []
    assert dict(RunMatrix.d11(3, 0).templates)["observed-rec-far"] == 0
    with pytest.raises(ValueError, match="not a multiple of 3"):
        RunMatrix.d11(10)
    with pytest.raises(ValueError, match="T_o <= T_d"):
        RunMatrix.d11(3, 4)


def test_d11_episodes_are_the_fully_crossed_episodes_of_those_cells():
    """Observed-far runs on the first T_o of the T_d templates; every episode is identical
    to the one the fully crossed generation gives for that template and cell."""
    m = RunMatrix.d11(3, 1)
    eps = m.episodes("pilot", 5, SMALL)
    full = {e.episode_id: e for e in _full("pilot", 5, 3)}
    assert [(e.template_seed - eps[0].template_seed, e.cell.id) for e in eps] == [
        (0, "observed-nonrec-far"), (0, "observed-rec-far"),
        (0, "derived-nonrec-far"), (0, "derived-rec-far"),
        (1, "derived-nonrec-far"), (1, "derived-rec-far"),
        (2, "derived-nonrec-far"), (2, "derived-rec-far")]
    assert all(e.to_dict() == full[e.episode_id].to_dict() for e in eps)
    assert len({e.template_id for e in eps}) == 3
    assert not [e for e in eps if e.cell.distance == "near"]


def test_full_matrix_matches_the_previous_episode_list():
    assert [e.to_dict() for e in RunMatrix.full(2).episodes("pilot", 0, SMALL)] == [
        e.to_dict() for e in _full("pilot", 0, 2)]
    cells = ["observed-nonrec-far", "derived-rec-near"]
    m = RunMatrix.full(1, cells)
    assert [e.cell.id for e in m.episodes("pilot", 0, SMALL)] == [
        "observed-nonrec-far", "derived-rec-near"]  # ALL_CELLS order


def test_custom_matrix():
    m = RunMatrix.parse(["derived-rec-far=2", "observed-rec-near=1"])
    assert m.name == "custom" and m.n_episodes == 3 and m.cells_for(1) == ["derived-rec-far"]
    assert m.to_dict()["templates_per_task_cell"] == {"observed-rec-near": 1,
                                                      "derived-rec-far": 2}
    for bad, msg in ((["derived-rec-far"], "TASK_CELL=N"),
                     (["derived-rec-far=1", "derived-rec-far=2"], "twice"),
                     (["derived-x-far=1"], "unknown"),
                     (["derived-rec-far=-1"], ">= 0"),
                     (["derived-rec-far=0"], "no episodes")):
        with pytest.raises(ValueError, match=msg):
            RunMatrix.parse(bad)


def test_block_warnings():
    """D7: main-sweep counts come in whole 10-template balance blocks."""
    assert RunMatrix.d11(90).block_warnings(0) == []
    w = RunMatrix.d11(60, 25).block_warnings(5)
    assert any("--start 5" in x for x in w) and any("25 templates" in x for x in w)


# --- repeats (PREREG §2.9; D7, §0.3 line 10) ------------------------------------------------

def test_a_repeat_plays_the_templates_whose_seed_is_divisible_by_10():
    """Repeat 1 plays, of the matrix's templates, only those whose main seed is divisible by
    10, each in the task cells it plays at repeat 0: the same episodes, byte for byte."""
    cells = ["observed-nonrec-far", "derived-rec-near"]
    m = RunMatrix.full(21, cells).repeat("main", 0)
    assert (m.repeat_index, m.played, m.n_templates, m.n_episodes) == (1, (0, 10, 20), 21, 6)
    eps = m.episodes("main", 0, SMALL)
    assert [e.template_seed for e in eps] == [0, 0, 10, 10, 20, 20]
    want = [e for t in (0, 10, 20) for e in _full("main", t, 1)
            if e.cell.id in cells]
    assert [e.to_dict() for e in eps] == [e.to_dict() for e in want]
    assert [e.episode_id for e in eps][:2] == ["main-000000/observed-nonrec-far/base",
                                               "main-000000/derived-rec-near/base"]
    # a start that is not a multiple of 10: the seeds inside [start, start + n)
    m = RunMatrix.full(20, cells).repeat("main", 5)
    assert m.played == (5, 15)
    assert sorted({e.template_seed for e in m.episodes("main", 5, SMALL)}) == [10, 20]


def test_a_repeat_keeps_the_matrix_and_the_variant():
    """D11's observed-far cells play only their first T_o templates at repeat 1 too, and the
    restated-at-need control repeats as restated episodes."""
    m = RunMatrix.d11(30, 10).repeat("main", 0)
    assert m.played == (0, 10, 20) and m.n_episodes == 4 + 2 + 2
    assert [m.cells_for(k) for k in (10, 20)] == [list(DERIVED_FAR)] * 2
    restated = RunMatrix.full(11, ["observed-rec-far"]).repeat("main", 0).episodes(
        "main", 0, SMALL, "restated")
    assert [e.episode_id for e in restated] == ["main-000000/observed-rec-far/restated",
                                                "main-000010/observed-rec-far/restated"]
    assert restated[1].to_dict() == next(
        e for _, eps in generate("main", [10], SMALL, ALL_CELLS, ("restated",)) for e in eps
        if e.cell.id == "observed-rec-far").to_dict()


def test_a_repeats_record_and_repeat_0s_unchanged_record():
    full = RunMatrix.full(100)
    assert full.to_dict() == {
        "name": "full", "templates_per_task_cell": dict.fromkeys(
            [c.id for c in ALL_CELLS], 100), "n_templates": 100, "n_episodes": 800}
    assert (full.repeat_index, full.offsets, full.played) == (0, None, tuple(range(100)))
    r = full.repeat("main", 0)
    assert r.to_dict() == {**full.to_dict(), "n_episodes": 80, "repeat_index": 1,
                           "repeat_every": 10, "template_offsets": list(range(0, 100, 10))}
    assert r.block_warnings(0) == full.block_warnings(0) == []


@pytest.mark.parametrize(("split", "start", "n", "message"), [
    ("pilot", 0, 10, "main templates only"),
    ("validity", 0, 10, "main templates only"),
    ("main", 1, 9, "would play nothing"),
    ("main", 41, 5, "would play nothing")])
def test_a_repeat_refuses_other_splits_and_empty_ranges(split, start, n, message):
    with pytest.raises(ValueError, match=message):
        RunMatrix.full(n).repeat(split, start)


def test_a_repeat_matrix_plays_its_own_templates_only():
    m = RunMatrix.full(11).repeat("main", 0)
    with pytest.raises(ValueError, match="a repeat already"):
        m.repeat("main", 0)
    for split, start in (("main", 3), ("pilot", 0)):
        with pytest.raises(ValueError, match="divisible by 10 only"):
            m.episodes(split, start, SMALL)
    for bad in ({"repeat_index": 1}, {"offsets": (0,)}, {"repeat_index": 2, "offsets": (0,)}):
        with pytest.raises(ValueError, match="repeat 0 with every template"):
            RunMatrix("full", (("observed-rec-far", 1),), **bad)
