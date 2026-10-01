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
