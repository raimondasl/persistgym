import dataclasses
import itertools
import re
from collections import Counter
from pathlib import Path

import pytest

from persistgym.config import (
    DEFAULT_CONFIG,
    RESEARCHER_DECISIONS,
    SEED_RANGES,
    GeneratorConfig,
)
from persistgym.skins import SKINS
from persistgym.template import (
    evidence_steps_any_cell,
    sample_template,
    seed_for,
    split_of_seed,
)
from persistgym.validity import clue_subsets, consistent_options

DESIGN = Path(__file__).resolve().parent.parent / "DESIGN.md"


def test_defaults_follow_plan():
    c = DEFAULT_CONFIG
    assert (c.W_tokens, c.v_tokens, c.K_options, c.k_targets) == (24_000, 1_500, 10, 1)
    assert c.near_gap_steps == 4
    assert c.tokenizer == "o200k_base"
    # (g + 1) * v > W: 17 observations of 1500 tokens = 25500 > 24000
    assert c.far_gap_steps == 16
    assert c.min_need_index == 16 + 2 + 2
    # PREREG decisions of 2026-10-01: D5 (sys counts toward W), D1 (2 distractors),
    # D2 (one cluster of consecutive options; addend cores leave room for the cluster)
    assert c.window_counts_system_prompt is True
    assert c.n_distractors == 2
    assert c.option_spacing == 1 and c.addend_core_range == (61, 89)
    assert not hasattr(c, "carried_match_window_chars")  # D6: one fixed regex rule


def test_config_validation():
    with pytest.raises(ValueError):
        GeneratorConfig(k_targets=2)
    with pytest.raises(ValueError):
        GeneratorConfig(rule_placement="nowhere")
    with pytest.raises(ValueError):
        GeneratorConfig(need_index_range=(10, 12))  # far derived cells cannot fit
    with pytest.raises(ValueError):
        GeneratorConfig(minor_component_range=(20, 40))  # would collide with clock fields
    with pytest.raises(ValueError):
        GeneratorConfig(option_spacing=5)  # 9 x 5 > 98 - 61: no addend leaves room
    with pytest.raises(ValueError):
        GeneratorConfig(n_distractors=9)


def test_config_round_trip():
    c = GeneratorConfig(W_tokens=12_000, v_tokens=750, n_clues_choices=(2,))
    assert GeneratorConfig.from_dict(c.to_dict()) == c
    with pytest.raises(ValueError):
        GeneratorConfig.from_dict({"nope": 1})


def test_researcher_decisions_are_fields_and_documented():
    fields = {f.name for f in dataclasses.fields(GeneratorConfig)}
    text = DESIGN.read_text(encoding="utf-8")
    for name in RESEARCHER_DECISIONS:
        assert name in fields, name
        assert f"`{name}`" in text, f"{name} missing from DESIGN.md"
    assert text.count("[RESEARCHER DECISION]") >= len(RESEARCHER_DECISIONS)


def test_seed_ranges_disjoint_and_ids():
    """PREREG D7: main [0, 50000) from 0, validity [50000, 60000), pilot [90000, 100000)."""
    assert SEED_RANGES == {"main": (0, 50_000), "validity": (50_000, 60_000),
                           "pilot": (90_000, 100_000)}
    ranges = sorted(SEED_RANGES.values())
    assert all(a[1] <= b[0] for a, b in itertools.pairwise(ranges))
    b0 = SEED_RANGES["pilot"][0]
    assert seed_for("main", 0) == 0 and seed_for("validity", 7) == 50_007
    assert seed_for("pilot", 3) == b0 + 3
    assert split_of_seed(b0 + 3) == ("pilot", 3)
    assert split_of_seed(59_999) == ("validity", 9_999)
    with pytest.raises(ValueError):
        seed_for("main", 50_000)
    with pytest.raises(ValueError):
        split_of_seed(60_000)
    t = sample_template("pilot", 0, DEFAULT_CONFIG)
    assert t.template_id == "pilot-000000" and t.seed == b0
    assert sample_template("validity", 0, DEFAULT_CONFIG).template_id == "validity-000000"


def test_template_is_deterministic_and_seed_specific():
    a = sample_template("main", 7, DEFAULT_CONFIG)
    b = sample_template("main", 7, DEFAULT_CONFIG)
    c = sample_template("main", 8, DEFAULT_CONFIG)
    assert a == b
    assert a != c
    assert a != sample_template("pilot", 7, DEFAULT_CONFIG)


def test_template_values():
    cfg = DEFAULT_CONFIG
    for i in range(40):
        t = sample_template("main", i, cfg)
        lo, hi = cfg.value_range
        assert len(t.option_values) == len(set(t.option_values)) == cfg.K_options
        assert all(lo <= v <= hi for v in t.option_values)
        assert t.option_values[t.correct_index] == t.target_value
        # D2: one cluster of consecutive values with the target at its block-balanced rank
        srt = sorted(t.option_values)
        assert srt == list(range(srt[0], srt[0] + cfg.K_options))
        assert srt.index(t.target_value) == t.rank
        assert sum(t.clue_values) == t.target_value
        assert len(t.clue_values) == t.n_clues in cfg.n_clues_choices
        assert not set(t.clue_values) & set(t.option_values)
        assert 100 <= t.clue_values[0] <= 999
        # each addend leaves room for the whole cluster on both sides of its range
        assert all(61 + t.rank <= x <= 98 - (9 - t.rank) for x in t.clue_values[1:])
        assert cfg.need_index_range[0] <= t.need_index <= cfg.need_index_range[1]
        assert len(t.routine) == t.n_steps
        for r in t.routine:
            assert t.reserved.clean(r.event)


def test_distractor_bindings_are_sampled_as_specified():
    """D1: 2 other entities of the skin, values in the value range that are neither options
    nor clue values, at distinct steps before need that hold no evidence in any cell."""
    cfg = DEFAULT_CONFIG
    for i in range(60):
        t = sample_template("main", i, cfg)
        ds = t.distractors
        assert len(ds) == cfg.n_distractors == 2
        assert len({d.entity for d in ds}) == 2 and t.entity not in {d.entity for d in ds}
        assert all(d.entity in t.skin_obj.entities for d in ds)
        vals = {d.value for d in ds}
        assert len(vals) == 2 and not vals & (set(t.option_values) | set(t.clue_values))
        assert all(cfg.value_range[0] <= v <= cfg.value_range[1] for v in vals)
        busy = evidence_steps_any_cell(t.need_index, t.n_clues, cfg)
        steps = [d.step for d in ds]
        assert len(set(steps)) == 2 and not set(steps) & busy
        assert all(cfg.lead_in_min_steps <= s < t.need_index for s in steps)
        assert all(not t.reserved.clean(f"x {d.entity} {d.value} x") for d in ds)


def test_no_proper_clue_subset_narrows_the_options():
    """D2 (b): with the rule and any proper subset of the clues, every option has a
    completion of the missing clues within the clue ranges."""
    cfg = DEFAULT_CONFIG
    for i in range(300):
        t = sample_template("main", i, cfg)
        for sub in clue_subsets(t.n_clues):
            known = {j: t.clue_values[j] for j in sub}
            assert consistent_options(known, t.n_clues, t.option_values,
                                      cfg.minor_component_range) == t.option_values, (i, sub)
        # and the full set pins the target down
        full = consistent_options(dict(enumerate(t.clue_values)), t.n_clues, t.option_values,
                                  cfg.minor_component_range)
        assert full == [t.target_value]


def test_no_skin_text_contains_one_of_its_entity_names():
    """The entity is the lookup key and the anchor of P(carried); it must not also appear in
    the site or other fixed text (e.g. sample LINDEN at 'the Linden clinical lab')."""
    for sk in SKINS.values():
        fixed = " ".join([sk.facility, *sk.sites, sk.kind, sk.quantity, *sk.components,
                          *sk.sources, sk.need_verb, sk.route_noun, *sk.route_tags,
                          *(m for m, _ in sk.sensor_metrics), *sk.broadcast_senders,
                          *sk.services, *sk.null_records])
        for e in sk.entities:
            assert not re.search(rf"(?<![A-Za-z]){e}(?![A-Za-z])", fixed, re.IGNORECASE), (
                sk.name, e)


def test_letters_ranks_and_clue_counts_balanced_within_blocks():
    """Every block of K = 10 templates: each letter and rank exactly once, and exactly 5
    templates with 2 clues and 5 with 3 (D2 (c)), in every split."""
    K = DEFAULT_CONFIG.K_options
    for split in ("main", "validity", "pilot"):
        for block in range(3):
            ts = [sample_template(split, block * K + i, DEFAULT_CONFIG) for i in range(K)]
            assert {t.block for t in ts} == {block}
            assert sorted(t.correct_label for t in ts) == list("ABCDEFGHIJ")
            assert sorted(t.rank for t in ts) == list(range(K))
            assert Counter(t.n_clues for t in ts) == {2: 5, 3: 5}
