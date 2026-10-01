import json
import re

import pytest

from persistgym import tokens
from persistgym.config import GeneratorConfig
from persistgym.episode import ALL_CELLS, Episode, TaskCell
from persistgym.render import TemplateRenderer, render_template, schedule
from persistgym.template import sample_template

from .conftest import SMALL, pick


def test_cell_ids_round_trip():
    assert len({c.id for c in ALL_CELLS}) == 8
    for c in ALL_CELLS:
        assert TaskCell.from_id(c.id) == c


def test_default_observations_are_exactly_v_tokens(default_eps):
    for ep in default_eps:
        for s in ep.steps:
            assert s.obs_tokens == 1500
            assert tokens.count(s.observation) == 1500


def test_default_far_is_beyond_W_by_observation_tokens(default_eps):
    for ep in default_eps:
        d = ep.design
        if ep.cell.distance == "far":
            assert d["gap_steps_latest"] == 16
            assert d["obs_tokens_latest_to_need"] == 17 * 1500 > 24_000
            assert d["far_by_obs_tokens"] and not d["S_window_obs_only"]
            assert not d["S_window_assumed_replies"]
        else:
            assert d["gap_steps_latest"] == 4
            assert d["S_window_obs_only"] and d["S_window_assumed_replies"]
        assert 20 <= ep.n_steps <= 32
        assert d["context_tokens_at_need_assumed_replies"] <= 64_000


def test_step_kinds_and_reveal_positions(small_eps):
    for ep in small_eps:
        kinds = [s.kind for s in ep.steps]
        assert kinds.count("need") == 1 and kinds.index("need") == ep.need_step
        assert kinds.count("distractor") == ep.config["n_distractors"]
        n = ep.need_step
        if ep.variant == "withheld":
            assert ep.components == [] and not ep.fact_available
            continue
        steps = {c.comp_id: c.step for c in ep.components}
        if ep.cell.fact == "observed":
            assert list(steps) == ["fact"]
        else:
            clues = [k for k in steps if k.startswith("clue")]
            assert len(clues) == ep.n_clues in (2, 3)
            assert "rule" in steps
            # clues on different steps, spacing 1, rule with the last clue
            cs = [steps[k] for k in clues]
            assert cs == sorted(cs) and len(set(cs)) == len(cs)
            assert steps["rule"] == cs[-1]
        latest = max(steps.values())
        gap = SMALL.near_gap_steps if ep.cell.distance == "near" else SMALL.far_gap_steps
        assert n - latest == gap
        for c in ep.components:
            assert c.sentence in ep.steps[c.step].event
            assert ep.steps[c.step].kind == "reveal"
            assert c.comp_id in ep.steps[c.step].reveals


def test_cells_share_need_options_and_routine(small_rendered):
    for t, eps in small_rendered:
        base = [e for e in eps if e.variant in ("base", "withheld")]
        assert len({e.need.observation for e in base}) == 1
        assert len({(e.correct_label, e.target_value) for e in eps}) == 1
        for i in range(t.n_steps):
            routine = {e.steps[i].observation for e in eps if e.steps[i].kind == "routine"}
            assert len(routine) <= 1


def test_distractor_bindings_identical_in_every_cell_and_variant(small_rendered):
    """D1: the 2 distractor bindings sit at the same steps with the same observation text in
    all 8 cells and 3 variants, in the target's sentence frame about another entity; they
    are never evidence, never needed, and lookup can serve them."""
    for t, eps in small_rendered:
        steps = sorted(d.step for d in t.distractors)
        for e in eps:
            assert [d.step for d in e.distractors] == steps
            assert [s.index for s in e.steps if s.kind == "distractor"] == steps
            for d in e.distractors:
                s = e.steps[d.step]
                assert s.distractors == [d.comp_id] and s.reveals == []
                assert d.sentence == f"For {e.kind} {d.entity}, the {e.quantity} is {d.value}."
                assert d.sentence in s.event and s.expected_action.startswith("ack(M-")
                assert e.lookup.records[d.comp_id] == d.record
                assert e.lookup.key_of(d.comp_id) == d.entity
                assert e.graph.needed_step(f"comp:{d.comp_id}") is None
                assert f"comp:{d.comp_id}" not in e.graph.required_components()
        for i in steps:
            assert len({e.steps[i].observation for e in eps}) == 1
        evidence = {c.step for e in eps for c in e.components if c.step is not None}
        assert not evidence & set(steps)


def test_derived_value_never_shown_before_need(small_eps):
    for ep in small_eps:
        if ep.cell.fact != "derived" and ep.variant != "withheld":
            continue
        rx = re.compile(rf"(?<![0-9]){ep.target_value}(?![0-9])")
        for s in ep.steps[: ep.need_step]:
            assert not rx.search(s.observation), (ep.episode_id, s.index)


def test_restated_need_repeats_records(small_eps):
    for ep in small_eps:
        if ep.variant != "restated":
            continue
        for c in ep.components:
            assert c.sentence in ep.need.event
        assert ep.need.restates == [c.comp_id for c in ep.components]


def test_withheld_keeps_structure(small_eps):
    base = pick(small_eps, "derived-nonrec-far")
    wh = pick(small_eps, "derived-nonrec-far", "withheld")
    assert [s.kind for s in base.steps] == [s.kind for s in wh.steps]
    for s in wh.steps:
        assert s.reveals == []
    assert wh.need.observation == base.need.observation


def test_recoverable_only_changes_system_prompt(small_eps):
    a = pick(small_eps, "observed-nonrec-far")
    b = pick(small_eps, "observed-rec-far")
    assert a.observations == b.observations
    assert "lookup(" not in a.system_prompt and "lookup(" in b.system_prompt
    assert b.lookup.available and not a.lookup.available


def test_json_round_trip(small_eps):
    for ep in small_eps[:24]:
        d = json.loads(json.dumps(ep.to_dict()))
        back = Episode.from_dict(d)
        assert back.to_dict() == ep.to_dict()


def test_rendering_is_deterministic():
    t1 = sample_template("main", 3, SMALL)
    t2 = sample_template("main", 3, SMALL)
    a = [e.to_dict() for e in render_template(t1, SMALL, ALL_CELLS[:2])]
    b = [e.to_dict() for e in render_template(t2, SMALL, ALL_CELLS[:2])]
    assert a == b


@pytest.mark.parametrize("placement", ["with_first_clue", "separate_step", "system_prompt"])
def test_rule_placements(placement):
    cfg = SMALL.replace(rule_placement=placement, need_index_range=(21, 24))
    t = sample_template("main", 1, cfg)
    ep = TemplateRenderer(t, cfg).render(TaskCell("derived", False, "far"))
    steps = schedule(t, TaskCell("derived", False, "far"), cfg)
    rule = ep.component("rule")
    if placement == "system_prompt":
        assert rule.step is None and rule.sentence in ep.system_prompt
        assert ep.design["rule_in_system_prompt"]
    elif placement == "separate_step":
        assert rule.step == ep.need_step - cfg.far_gap_steps
        assert all(steps[f"clue{i}"] < rule.step for i in range(t.n_clues))
    else:
        assert rule.step == steps["clue0"]
    assert ep.design["far_by_obs_tokens"] and not ep.design["S_window_obs_only"]


def test_restate_final_value_mode():
    cfg = SMALL.replace(restate_mode="final_value")
    t = sample_template("main", 2, cfg)
    ep = TemplateRenderer(t, cfg).render(TaskCell("derived", False, "far"), "restated")
    assert f"is {t.target_value}." in ep.need.event


def test_other_volume_settings_still_hit_v():
    cfg = GeneratorConfig(W_tokens=9_000, v_tokens=600, assumed_max_reply_tokens=300,
                          need_index_range=(19, 21))
    assert cfg.far_gap_steps == 15
    t = sample_template("main", 5, cfg)
    for ep in render_template(t, cfg, ALL_CELLS, ("base",)):
        assert set(ep.obs_tokens) == {600}
        if ep.cell.distance == "far":
            assert ep.design["obs_tokens_latest_to_need"] > 9_000
