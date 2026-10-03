"""Generator 0.4.0: gpt-6.1-sol's derived-fact variant, preset `sol-chain` (PREREG §17.3,
amendment R3): the config and its pinned hash, the chain records, the evidence notice, the
controls, lookup by helper keys, the oracles and the $0 audits and gates on the variant, and
that the default config is unchanged (with test_golden.py)."""

import copy
import dataclasses
import itertools
import json
import re
import sys
from pathlib import Path

import pytest

from common.runmeta import config_hash
from persistgym import tokens
from persistgym.config import (
    ADDED_IN_0_4,
    CHAIN_V1_GAP,
    GENERATOR_VERSION,
    PRESET_HASHES,
    PRESETS,
    RESEARCHER_DECISIONS,
    GeneratorConfig,
)
from persistgym.env import EpisodeEnv
from persistgym.episode import ALL_CELLS, VARIANTS, TaskCell, content_sha256
from persistgym.oracle import MAX_RELATION_DEPTH, TextOracle, run_episode
from persistgym.render import (
    chain_sentences,
    generate,
    notice_text,
    relation_sentence,
    render_template,
    renderer_for,
)
from persistgym.template import (
    CHAIN_ANCHOR_RANGE,
    CHAIN_DELTA_RANGE,
    CHAIN_MARGIN,
    CHAIN_MIN_GAP,
    hidden_values,
    names_overlap,
    prefix_sums,
    sample_template,
)
from persistgym.validity import (
    NOTICE_MARK,
    atom_narrowing,
    chain_partial_memory,
    heuristic_baselines,
    lookup_audit,
    oracle_scores,
    parse_chain,
    partial_memory_diagnostic,
    partial_memory_from_episodes,
    shortcut_audit,
    stand_in_value_baseline,
    text_hidden_values,
)

from .conftest import SMALL

CHAIN = PRESETS["sol-chain"]
SMALL_CHAIN = CHAIN.replace(W_tokens=SMALL.W_tokens, v_tokens=SMALL.v_tokens,
                            assumed_max_reply_tokens=SMALL.assumed_max_reply_tokens)
GOLDEN = Path(__file__).resolve().with_name("golden_0_4_0_sol_chain.json")
DERIVED_NOTICE = ("The {q} of {k} {e} will be requested in a later update. Before replying, "
                  "work out as much of it as the records so far allow and keep the result in "
                  "mind; do not write it in your reply.")
OBSERVED_NOTICE = ("The {q} of {k} {e} will be requested in a later update. Keep it in mind; "
                   "do not write it in your reply.")


def _failed(report):
    return [c["check"] for c in report if not c["pass"]]


@pytest.fixture(scope="module")
def validity_eps():
    """sol's validity templates 0-19 on sol-chain, 8 cells x 3 variants, full size."""
    return [e for _, es in generate("validity", range(20), CHAIN, ALL_CELLS, VARIANTS)
            for e in es]


@pytest.fixture(scope="module")
def small_main():
    """main templates 0-59 on sol-chain at the small volume, 8 cells x 3 variants."""
    return [e for _, es in generate("main", range(60), SMALL_CHAIN, ALL_CELLS, VARIANTS)
            for e in es]


def _ep(eps, tid, cell, variant="base"):
    return next(e for e in eps if e.template_id == tid and e.cell.id == cell
                and e.variant == variant)


# --- config, presets, versions ------------------------------------------------------------

def test_versions_and_presets():
    assert GENERATOR_VERSION == "0.4.0"
    assert set(PRESETS) == set(PRESET_HASHES) == {"default", "sol-chain"}
    for name, cfg in PRESETS.items():
        assert config_hash(cfg.to_dict()) == PRESET_HASHES[name], name
        assert GeneratorConfig.from_dict(cfg.to_dict()) == cfg
    assert PRESETS["default"] == GeneratorConfig()
    assert (CHAIN.clue_form, CHAIN.evidence_notice, CHAIN.rule_placement) == (
        "chain", True, "with_first_clue")
    assert dataclasses.replace(CHAIN, clue_form="direct", evidence_notice=False,
                               rule_placement="with_last_clue") == GeneratorConfig()
    # the default dict has no 0.4.0 field, so its hash is generator 0.3.0's
    d = GeneratorConfig().to_dict()
    assert not set(ADDED_IN_0_4) & set(d)
    assert set(CHAIN.to_dict()) - set(d) == set(ADDED_IN_0_4)
    for name in ADDED_IN_0_4:
        assert name in RESEARCHER_DECISIONS
    assert CHAIN_V1_GAP == CHAIN_DELTA_RANGE[0] + CHAIN_MARGIN


def test_config_validation():
    with pytest.raises(ValueError, match="clue_form"):
        GeneratorConfig(clue_form="relay")
    with pytest.raises(ValueError, match="option_spacing 1"):
        GeneratorConfig(clue_form="chain", option_spacing=2)
    with pytest.raises(ValueError, match="H1 value"):  # 999 - 61 + 109 > 999: no v1 range
        GeneratorConfig(clue_form="chain", value_range=(300, 999))
    with pytest.raises(ValueError, match="H1 value"):
        GeneratorConfig(clue_form="chain", n_clues_choices=(2,), value_range=(300, 960))
    GeneratorConfig(clue_form="chain", value_range=(300, 951))      # 951 - 61 + 109 = 999


def test_renderer_for_rebuilds_a_variant_episode(validity_eps):
    ep = _ep(validity_eps, "validity-000003", "derived-rec-far")
    again = json.loads(json.dumps(ep.to_dict()))
    r = renderer_for(type(ep).from_dict(again))
    assert r.config_hash == PRESET_HASHES["sol-chain"]
    assert r.render(ep.cell, "base").to_dict() == ep.to_dict()


# --- templates -----------------------------------------------------------------------------

TEMPLATE_FIELDS = ("skin", "site", "entity", "target_value", "option_values", "correct_index",
                   "n_clues", "clue_values", "record_ids", "substitute", "need_index",
                   "tail_steps", "t0", "distractors")


@pytest.mark.parametrize(("split", "n"), [("pilot", 4), ("validity", 20), ("main", 60)])
def test_the_variant_keeps_every_template_value(split, n):
    """Options, clues, rank, letter, m, need step, distractors, stand-in, record ids, tail
    and clock are generator 0.3.0's for every seed; only the chains are new."""
    for i in range(n):
        a, b = sample_template(split, i, GeneratorConfig()), sample_template(split, i, CHAIN)
        for f in TEMPLATE_FIELDS:
            assert getattr(a, f) == getattr(b, f), (split, i, f)
        assert a.chains == [] and len(b.chains) == b.n_clues
        assert set(a.reserved_numbers) < set(b.reserved_numbers)
        assert set(a.reserved_words) < set(b.reserved_words)


def test_the_check_templates():
    """PREREG §17.3's table: the check's pilot templates."""
    want = {0: ("depot", "CURLEW", 2, 517, [424, 93]),
            1: ("warehouse", "HADAR", 3, 812, [654, 82, 76]),
            2: ("warehouse", "ELNATH", 2, 374, None), 3: ("archive", "RHINE", 2, 419, None)}
    for i, (skin, entity, m, target, clues) in want.items():
        t = sample_template("pilot", i, CHAIN)
        assert (t.skin, t.entity, t.n_clues, t.target_value) == (skin, entity, m, target)
        if clues:
            assert t.clue_values == clues
    t = sample_template("pilot", 1, CHAIN)
    c = t.chains[0]
    assert (c.helpers, c.anchor, c.far, c.near, c.decoy) == (
        ["BELLATRIX", "SHAULA", "ORION"], 314, 669, 329, 268)
    assert [c.h1_value - c.near for c in t.chains] == [654, 82, 76]


@pytest.mark.parametrize("split", ["pilot", "validity", "main"])
def test_chain_invariants(split):
    m_lo = CHAIN.minor_component_range[0]
    for i in range(300):
        t = sample_template(split, i, CHAIN)
        s = t.substitute
        taken = (set(t.option_values) | set(t.clue_values) | set(s.clue_values)
                 | set(prefix_sums(t.clue_values)) | set(prefix_sums(s.clue_values))
                 | {s.value} | {d.value for d in t.distractors})
        helpers = [h for ch in t.chains for h in ch.helpers]
        others = [t.entity, s.entity, *(d.entity for d in t.distractors)]
        assert len(set(helpers)) == len(helpers) == 3 * t.n_clues
        assert not any(names_overlap(a, b) for a, b in itertools.combinations(helpers, 2))
        assert not any(names_overlap(h, o) for h in helpers for o in others)
        assert set(helpers) <= set(t.skin_obj.entities)
        seen: set[int] = set()
        for k, (ch, c, cs) in enumerate(zip(t.chains, t.clue_values, s.clue_values,
                                            strict=True)):
            assert ch.anchor + ch.far - ch.near == c
            assert ch.h1_value - ch.stand_in_near == cs
            cmax = (CHAIN.value_range[1] - (t.n_clues - 1) * m_lo if k == 0
                    else CHAIN.minor_component_range[1])
            assert cmax + CHAIN_V1_GAP <= ch.h1_value <= 999
            lo, hi = CHAIN_ANCHOR_RANGE[0] + CHAIN_MARGIN, CHAIN_ANCHOR_RANGE[1] - CHAIN_MARGIN
            assert lo <= ch.anchor <= hi
            lo, hi = CHAIN_DELTA_RANGE[0] + CHAIN_MARGIN, CHAIN_DELTA_RANGE[1] - CHAIN_MARGIN
            assert all(lo <= x <= hi for x in (ch.far, ch.near, ch.stand_in_near, ch.decoy))
            assert ch.decoy_value <= 999
            assert min(abs(ch.far - ch.near), abs(ch.far - ch.stand_in_near),
                       abs(ch.decoy - ch.far)) >= CHAIN_MIN_GAP
            assert len(set(ch.numbers)) == 7 and not set(ch.numbers) & (taken | seen)
            seen |= set(ch.numbers)
            assert sorted(ch.order) == sorted(["near", "far", "anchor", "decoy"])
        assert set(t.reserved_numbers) >= seen | taken
        assert set(t.reserved_words) >= set(helpers)
        assert sample_template(split, i, CHAIN) == t                    # deterministic


# --- rendering -----------------------------------------------------------------------------

def test_sentences_and_the_example():
    """PREREG §17.3's example: pilot-000001's first clue record, word for word."""
    assert relation_sentence("shipment", "HADAR", "base bay", 329, "less", "BELLATRIX") == (
        "For shipment HADAR, the base bay is 329 less than for shipment BELLATRIX.")
    with pytest.raises(ValueError):
        relation_sentence("shipment", "HADAR", "base bay", 329, "fewer", "BELLATRIX")
    t = sample_template("pilot", 1, CHAIN)
    ep = render_template(t, CHAIN, [TaskCell.from_id("derived-rec-far")])[0]
    st = ep.steps[min(ep.reveal_steps)]
    assert st.event == (
        "Dispatch memo M-2463. For shipment HADAR, the base bay is 329 less than for shipment "
        "BELLATRIX. For shipment SHAULA, the base bay is 314. For shipment BELLATRIX, the base "
        "bay is 669 more than for shipment SHAULA. For shipment ORION, the base bay is 268 "
        "more than for shipment SHAULA. Rule: for every shipment, loading bay = base bay + "
        "priority offset + lane shift. The loading bay of shipment HADAR will be requested in "
        "a later update. Before replying, work out as much of it as the records so far allow "
        "and keep the result in mind; do not write it in your reply. Reply ack(M-2463) to "
        "acknowledge it.")
    assert [tokens.count(ep.steps[s].event) for s in ep.reveal_steps] == [149, 134, 136]
    assert ep.reveal_steps == [ep.need_step - 18, ep.need_step - 17, ep.need_step - 16]
    s = chain_sentences("shipment", "base bay", "HADAR", 329, t.chains[0])
    assert s["far"].startswith("For shipment BELLATRIX,") and s["anchor"].endswith("is 314.")


def test_notice_text():
    for fact, text in (("derived", DERIVED_NOTICE), ("observed", OBSERVED_NOTICE)):
        got = notice_text(fact, "shipment", "loading bay", "HADAR")
        assert got == text.format(q="loading bay", k="shipment", e="HADAR")
    n = tokens.count(" " + notice_text("derived", "shipment", "loading bay", "HADAR"))
    assert 45 <= n <= 46
    assert 28 <= tokens.count(" " + notice_text("observed", "shipment", "loading bay",
                                                "HADAR")) <= 29


def _notice_steps(ep) -> list[int]:
    return [s.index for s in ep.steps if NOTICE_MARK in s.observation]


def test_notice_only_at_evidence_steps(validity_eps):
    for ep in validity_eps:
        entity = ep.substitutes[0].entity if ep.variant == "withheld" else ep.entity
        want = notice_text(ep.cell.fact, ep.kind, ep.quantity, entity)
        sched = {c.step for c in ep.components if c.step is not None} or {
            s.step for s in ep.substitutes}
        assert _notice_steps(ep) == sorted(sched), ep.episode_id
        for i in sched:
            event = ep.steps[i].event
            assert event.count(want) == 1 and event.endswith(
                f"{want} Reply ack({ep.steps[i].expected_action[4:-1]}) to acknowledge it.")
        assert NOTICE_MARK not in ep.system_prompt
        assert NOTICE_MARK not in ep.need.observation                   # restated block too
        assert all(NOTICE_MARK not in r for r in ep.lookup.records.values())
        if ep.cell.fact == "derived" and ep.variant != "withheld":
            clues = sorted(c.step for c in ep.components if c.role == "clue")
            rule = next(c.step for c in ep.components if c.role == "rule")
            assert ep.reveal_steps == clues and rule == clues[0]    # rule with the first clue


def test_the_default_config_shows_no_notice(small_main):
    eps = [e for _, es in generate("main", range(2), SMALL, ALL_CELLS, VARIANTS) for e in es]
    for ep in eps:
        assert not _notice_steps(ep) and not any(NOTICE_MARK in r
                                                 for r in ep.lookup.records.values())
    assert any(_notice_steps(ep) for ep in small_main)


def test_observations_and_withheld_lengths(validity_eps):
    """Every observation is exactly v tokens; a withheld evidence step keeps the base
    filler, and its sentences and event keep their token counts (D39)."""
    by = {(e.template_id, e.cell.id, e.variant): e for e in validity_eps}
    for ep in validity_eps:
        assert all(s.obs_tokens == 1500 for s in ep.steps)
        if ep.variant != "withheld":
            continue
        base = by[(ep.template_id, ep.cell.id, "base")]
        orig = {c.comp_id: c.sentence for c in base.components}
        for s in ep.substitutes:
            assert tokens.count(s.sentence) == tokens.count(orig[s.comp_id[4:]])
            a, b = ep.steps[s.step], base.steps[s.step]
            assert a.observation[: a.filler_end] == b.observation[: b.filler_end]
            assert tokens.count(a.event) == tokens.count(b.event)
            if s.comp_id.startswith("sub_clue"):
                p, q = parse_chain(s.sentence, ep.kind), parse_chain(orig[s.comp_id[4:]],
                                                                     ep.kind)
                assert (p.helpers, p.anchor, p.far, p.decoy, p.order) == (
                    q.helpers, q.anchor, q.far, q.decoy, q.order)
                assert p.subject == s.entity and p.value == s.value


def test_hidden_values_never_shown_and_equal_the_generators(validity_eps):
    by_t: dict[str, list] = {}
    for ep in validity_eps:
        by_t.setdefault(ep.template_id, []).append(ep)
    for tid, eps in by_t.items():
        t = sample_template("validity", int(tid[-6:]), CHAIN)
        evid = [c for e in eps for c in e.components]
        subs = [s for e in eps for s in e.substitutes]
        dist = [d.value for d in t.distractors]
        assert text_hidden_values(t.target_value, evid, subs, eps[0].kind, dist) == set(
            hidden_values(t))
        rx = re.compile(r"(?<![0-9])(?:" + "|".join(map(str, hidden_values(t)))
                        + r")(?![0-9])")
        for ep in eps:
            shown_ok = ({ep.target_value, t.substitute.value} if ep.cell.fact == "observed"
                        else set())
            for s in ep.steps[: ep.need_step]:
                assert not set(map(int, rx.findall(s.observation))) - shown_ok


# --- oracles and lookup ---------------------------------------------------------------------

def test_text_oracle_resolves_relations_with_cycle_and_depth_guards():
    o = TextOracle()
    o.reset("")
    o.remember("For box AA, the bay offset is 300. For box BB, the bay offset is 20 more than "
               "for box AA. For box CC, the bay offset is 5 less than for box BB. For box XX, "
               "the bay offset is 1 more than for box YY. For box YY, the bay offset is 1 more "
               "than for box XX. Rule: for every box, shelf number = bay offset + annex shift.")
    o.remember("For box CC, the annex shift is 7.")
    assert o.value_of("BB", "bay offset") == 320 and o.value_of("CC", "bay offset") == 315
    assert o.value_of("CC", "shelf number") == 322
    assert o.value_of("XX", "bay offset") is None                      # a cycle
    names = [f"N{chr(65 + i)}" for i in range(MAX_RELATION_DEPTH + 2)]  # NA, NB, ...
    chain = " ".join(f"For box {b}, the bay offset is 1 more than for box {a}."
                     for a, b in itertools.pairwise(names))
    o.remember(f"For box {names[0]}, the bay offset is 10. " + chain)
    assert o.value_of(names[MAX_RELATION_DEPTH], "bay offset") == 10 + MAX_RELATION_DEPTH
    assert o.value_of(names[MAX_RELATION_DEPTH + 1], "bay offset") is None  # too deep


def test_oracles_on_the_variant(small_main):
    orc = oracle_scores(small_main)
    assert orc["pass"]
    assert orc["text"]["base/nonrec"]["need_acc"] == orc["text"]["restated/rec"]["need_acc"] == 1
    assert orc["lookup_no_memory"]["base/rec"]["need_acc"] == 1.0
    assert orc["text"]["withheld/nonrec"]["need_acc"] == pytest.approx(0.1)


def test_a_helper_key_reshows_its_record_from_its_step_on(validity_eps):
    for variant in ("base", "withheld"):
        ep = _ep(validity_eps, "validity-000001", "derived-rec-near", variant)
        comps = ep.components or ep.substitutes
        clue0 = next(c for c in comps if c.comp_id.endswith("clue0"))
        h1, h2, h3 = parse_chain(clue0.sentence, ep.kind).helpers
        r = renderer_for(ep)
        for h in (h1, h2, h3.lower()):
            text, _, _ = r.lookup_observation(ep, ep.need_step, 0, h)
            assert clue0.sentence in text and f"LOOKUP RESULT for {ep.kind} " in text
            assert NOTICE_MARK not in text
            assert not any(c.sentence in text for c in comps if c.step != clue0.step)
            before, _, _ = r.lookup_observation(ep, clue0.step - 1, 0, h)
            assert "no such record" in before
        target, _, _ = r.lookup_observation(ep, ep.need_step, 0, ep.entity)
        assert ("no such record" in target) is (variant == "withheld")
    # played: lookup(H1) at the need step, then the right answer
    ep = _ep(validity_eps, "validity-000001", "derived-rec-far")
    env = EpisodeEnv(ep)
    h1 = parse_chain(ep.components[0].sentence, ep.kind).helpers[0]
    done = False
    while not done:
        reply = (f"ACTION: lookup({h1})" if env.pending == ep.need_step and not env.result()
                 .n_lookups else f"ACTION: {ep.steps[env.pending].expected_action}")
        _, done = env.step(reply)
    assert env.result().need_correct and env.result().n_lookups == 1


# --- audits ----------------------------------------------------------------------------------

def test_every_audit_passes_on_the_variant(validity_eps, small_main):
    for eps in (validity_eps, small_main):
        report = shortcut_audit(eps) + lookup_audit(eps)
        assert _failed(report) == []
        assert len(report) == 21
        chains = next(c for c in report if c["check"] == "chain_records_well_formed_and_resolve")
        assert chains["detail"]["n_chain_records"] > 0
        hb = heuristic_baselines(eps)
        assert hb["pass"] and all(c["accuracy"] <= 0.2 for c in
                                  hb["nearest_to_stand_in_value"]["by_cell"].values())
        pm = partial_memory_from_episodes(eps)
        assert pm["pass"] and all(c["chain"]["all"]["atom_narrowing_templates"] == 0
                                  for c in pm["cells"].values())


def _poke(ep, step, old, new):
    st = ep.steps[step]
    assert old in st.observation
    st.observation = st.observation.replace(old, new, 1)
    st.event = st.event.replace(old, new, 1)


def test_each_new_check_fails_on_a_bad_episode(validity_eps):
    tid = "validity-000002"
    base = copy.deepcopy(_ep(validity_eps, tid, "derived-nonrec-far"))
    wh = copy.deepcopy(_ep(validity_eps, tid, "derived-nonrec-far", "withheld"))
    assert _failed(shortcut_audit([base, wh])) == []

    def failed(*eps):
        return _failed(shortcut_audit(list(eps)))

    # the notice at a distractor step
    bad = copy.deepcopy(base)
    d = bad.distractors[0]
    notice = notice_text("derived", bad.kind, bad.quantity, bad.entity)
    _poke(bad, d.step, " Reply ack(", f" {notice} Reply ack(")
    assert "evidence_notice_only_at_evidence_steps" in failed(bad, wh)
    # a hidden value (H1's value of clue 0) in a routine step's filler
    bad = copy.deepcopy(base)
    p = parse_chain(bad.components[0].sentence, bad.kind)
    st = next(s for s in bad.steps if s.kind == "routine")
    line = st.observation[st.filler_start:].split("\n", 2)[1]
    _poke(bad, st.index, line, f"{line[:24]} took {p.h1_value}ms")
    assert "chain_hidden_values_never_shown" in failed(bad, wh)
    # a malformed chain record: its decoy points at H1 instead of H2
    bad = copy.deepcopy(base)
    c0 = bad.components[0]
    q = parse_chain(c0.sentence, bad.kind)
    wrong = c0.sentence.replace(f"{q.decoy} more than for {bad.kind} {q.helpers[1]}",
                                f"{q.decoy} more than for {bad.kind} {q.helpers[0]}")
    _poke(bad, c0.step, c0.sentence, wrong)
    c0.sentence = wrong
    assert "chain_records_well_formed_and_resolve" in failed(bad)
    # a wrong n': the stand-in's near delta changed (its clue no longer resolves)
    bad = copy.deepcopy(wh)
    s0 = bad.substitutes[0]
    sp = parse_chain(s0.sentence, bad.kind)
    other = s0.sentence.replace(f" {sp.near} less ", f" {sp.near + 1} less ")
    _poke(bad, s0.step, s0.sentence, other)
    s0.sentence = other
    assert "withheld_stand_ins_equal_length_and_valid" in failed(base, bad)


def test_lookup_audit_fails_when_a_helper_key_does_not_reshow(validity_eps):
    ep = copy.deepcopy(_ep(validity_eps, "validity-000004", "derived-rec-far"))
    assert _failed(lookup_audit([ep])) == []
    ep.lookup.records = {k: v for k, v in ep.lookup.records.items() if "@" not in k}
    ep.lookup.reveal_steps = {k: v for k, v in ep.lookup.reveal_steps.items() if "@" not in k}
    assert _failed(lookup_audit([ep])) == ["lookup_serves_keys_and_refuses_after_cap"]


# --- gates on 200 templates per derived cell (the CLI covers 2,000) --------------------------

def _chain_items(split, n, cfg=CHAIN):
    out = []
    for i in range(n):
        t = sample_template(split, i, cfg)
        out.append((t.n_clues, [(c.anchor, c.far, c.near, c.decoy) for c in t.chains],
                    t.option_values, t.target_value))
    return out


def test_atom_level_and_misreading_gates():
    for split in ("pilot", "validity", "main"):
        cm = chain_partial_memory(_chain_items(split, 200), CHAIN.to_dict())
        assert cm["pass"] and cm["all"]["atom_narrowing_templates"] == 0
        assert all(x <= 0.2 for x in cm["all"]["heuristics"].values())
        assert set(cm["all"]["heuristics"]) == {"flat_signed_sum", "sign_blind",
                                                "anchors_only", "h1_as_clue", "one_hop",
                                                "decoy_pointer"}
    # one missing atom already keeps all 10 options; a known value of every atom narrows
    t = sample_template("pilot", 1, CHAIN)
    atoms = [(c.anchor, c.far, c.near) for c in t.chains]
    assert atom_narrowing(atoms, t.option_values) == 0
    # options beyond what a missing atom's range can reach are ruled out
    assert atom_narrowing([(60, 100, 999)], list(range(-845, -835))) > 0


def test_clue_level_figures_equal_the_default_configs():
    for split in ("pilot", "main"):
        items = {}
        for name, cfg in (("default", GeneratorConfig()), ("chain", CHAIN)):
            items[name] = [(t.n_clues, t.clue_values, t.option_values, t.target_value)
                           for t in (sample_template(split, i, cfg) for i in range(200))]
        assert items["default"] == items["chain"]
        a = partial_memory_diagnostic(items["default"], GeneratorConfig().to_dict())
        b = partial_memory_diagnostic(items["chain"], CHAIN.to_dict())
        assert a == b and a["pass"] and a["all"]["narrowing_templates"] == 0


@pytest.mark.parametrize("cfg", [SMALL, SMALL_CHAIN], ids=["default", "sol-chain"])
def test_the_stand_in_value_baseline_in_both_configs(cfg):
    eps = [e for _, es in generate("main", range(100), cfg, ALL_CELLS, ("withheld",))
           for e in es]
    si = stand_in_value_baseline(eps, 0.2)
    assert si["pass"] and set(si["by_cell"]) == {c.id for c in ALL_CELLS}
    assert all(c["n_templates"] == 100 and c["accuracy"] <= 0.2 for c in si["by_cell"].values())


# --- the variant's golden digests ----------------------------------------------------------------

def test_variant_renders_equal_their_golden_digests():
    """Digests of the variant's renders that R3's check and sol's validity run play, pinned
    before R3's check (pilot 0-3, validity 0-19; 8 cells x 3 variants)."""
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert golden["config_hash"] == PRESET_HASHES["sol-chain"]
    got = {}
    for split, n in golden["sets"]:
        for _, eps in generate(split, range(n), CHAIN, ALL_CELLS, VARIANTS):
            got.update({e.episode_id: content_sha256(e) for e in eps})
    assert got == golden["episodes"]


def test_a_run_through_the_oracle_on_the_check_episodes():
    """The 8 episodes of R3's check templates in the far cells play to the end with the
    text oracle, which needs the chains resolved."""
    for i in (0, 1):
        for ep in render_template(sample_template("pilot", i, CHAIN), CHAIN,
                                  [c for c in ALL_CELLS if c.distance == "far"]):
            assert run_episode(ep, TextOracle()).need_correct


def _write_golden() -> int:
    """Write golden_0_4_0_sol_chain.json once (uv run python -m persistgym.tests.test_variant):
    the content digest of every sol-chain episode of pilot templates 0-3 and validity
    templates 0-19, 8 cells x 3 variants. Refuses to overwrite it."""
    if GOLDEN.exists():
        print(f"refused: {GOLDEN} exists; the fixture is written once", file=sys.stderr)
        return 2
    sets = [["pilot", 4], ["validity", 20]]
    digests = {}
    for split, n in sets:
        for _, eps in generate(split, range(n), CHAIN, ALL_CELLS, VARIANTS):
            digests.update({e.episode_id: content_sha256(e) for e in eps})
    doc = {"generator_version": GENERATOR_VERSION, "preset": "sol-chain",
           "config_hash": config_hash(CHAIN.to_dict()), "sets": sets, "episodes": digests}
    GOLDEN.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                      newline="\n")
    print(f"wrote {len(digests)} digests to {GOLDEN}")
    return 0


if __name__ == "__main__":
    sys.exit(_write_golden())
