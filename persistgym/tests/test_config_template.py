import dataclasses
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
from persistgym.template import sample_template, seed_for, split_of_seed

DESIGN = Path(__file__).resolve().parent.parent / "DESIGN.md"


def test_defaults_follow_plan():
    c = DEFAULT_CONFIG
    assert (c.W_tokens, c.v_tokens, c.K_options, c.k_targets) == (24_000, 1_500, 10, 1)
    assert c.near_gap_steps == 4
    assert c.tokenizer == "o200k_base"
    # (g + 1) * v > W: 17 observations of 1500 tokens = 25500 > 24000
    assert c.far_gap_steps == 16
    assert c.min_need_index == 16 + 2 + 2


def test_config_validation():
    with pytest.raises(ValueError):
        GeneratorConfig(k_targets=2)
    with pytest.raises(ValueError):
        GeneratorConfig(rule_placement="nowhere")
    with pytest.raises(ValueError):
        GeneratorConfig(need_index_range=(10, 12))  # far derived cells cannot fit
    with pytest.raises(ValueError):
        GeneratorConfig(minor_component_range=(20, 40))  # would collide with clock fields


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
    (a0, a1), (b0, b1) = SEED_RANGES["main"], SEED_RANGES["pilot"]
    assert a1 <= b0 or b1 <= a0
    assert seed_for("pilot", 3) == b0 + 3
    assert split_of_seed(b0 + 3) == ("pilot", 3)
    with pytest.raises(ValueError):
        seed_for("main", a1 - a0)
    t = sample_template("pilot", 0, DEFAULT_CONFIG)
    assert t.template_id == "pilot-000000" and t.seed == b0


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
        assert sum(t.clue_values) == t.target_value
        assert len(t.clue_values) == t.n_clues in cfg.n_clues_choices
        assert not set(t.clue_values) & set(t.option_values)
        assert 100 <= t.clue_values[0] <= 999
        assert all(61 <= x <= 98 for x in t.clue_values[1:])
        assert cfg.need_index_range[0] <= t.need_index <= cfg.need_index_range[1]
        assert len(t.routine) == t.n_steps
        for r in t.routine:
            assert t.reserved.clean(r.event)


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


def test_letters_and_ranks_balanced_within_blocks():
    K = DEFAULT_CONFIG.K_options
    ts = [sample_template("main", i, DEFAULT_CONFIG) for i in range(3 * K)]
    letters = Counter(t.correct_label for t in ts)
    ranks = Counter(sorted(t.option_values).index(t.target_value) for t in ts)
    assert set(letters.values()) == {3} and len(letters) == K
    assert set(ranks.values()) == {3} and len(ranks) == K
