import copy
import gzip
import json

import pytest

from persistgym import tokens
from persistgym.cli import main, parse_overrides
from persistgym.config import GeneratorConfig
from persistgym.controls import (
    REPLY_ACTION_CLASSES,
    reply_action_class,
    score_single_turn,
    single_turn_control,
)
from persistgym.env import EpisodeEnv
from persistgym.episode import read_jsonl
from persistgym.filler import Reserved
from persistgym.skins import get_skin
from persistgym.template import entity_token_length
from persistgym.validity import (
    generator_aware_weights,
    heuristic_baselines,
    last_seen_option,
    lookup_audit,
    most_frequent_option,
    option_hits,
    oracle_scores,
    partial_memory_diagnostic,
    partial_memory_from_episodes,
    shortcut_audit,
)

from .conftest import pick


def _failed(report):
    return [c["check"] for c in report if not c["pass"]]


def _detail(report, name):
    return next(c for c in report if c["check"] == name)["detail"]


def test_audit_passes(small_eps):
    report = shortcut_audit(small_eps)
    assert _failed(report) == []
    blocks = next(c for c in report if c["check"].startswith("letter_rank_and_n_clues"))
    assert blocks["detail"]["complete_blocks"] == 1 and not blocks["detail"]["incomplete_blocks"]


def test_lookup_audit_passes(small_eps):
    report = lookup_audit(small_eps)
    assert _failed(report) == [] and report[0]["detail"]["n_episodes"] == 10 * 4
    assert report[0]["detail"]["n_withheld_episodes"] == 10 * 4


def test_audit_catches_withheld_problems(small_eps):
    """D39: a withheld episode that names the target before need (as the null records of
    generator 0.2.0 did), a stand-in value that is an option, a stand-in of another token
    length, a derived stand-in whose clues sum to an option, and an evidence step whose
    filler differs from the base episode all fail the audit."""
    named, stand_ins = ("withheld_never_names_target_before_need",
                        "withheld_stand_ins_equal_length_and_valid")
    base = pick(small_eps, "observed-nonrec-far")
    wh = copy.deepcopy(pick(small_eps, "observed-nonrec-far", "withheld"))
    assert _failed(shortcut_audit([base, wh])) == []
    x = wh.substitutes[0]
    st = wh.steps[x.step]
    null = f"{wh.kind.capitalize()} {wh.entity} has been logged at intake."
    st.observation = st.observation.replace(x.sentence, null)
    assert named in _failed(shortcut_audit([base, wh]))

    wh = copy.deepcopy(pick(small_eps, "observed-nonrec-far", "withheld"))
    x = wh.substitutes[0]
    st = wh.steps[x.step]
    opt = wh.options[0].value
    new = x.sentence.replace(f" {x.value}.", f" {opt}.")
    st.observation, st.event = (st.observation.replace(x.sentence, new),
                                st.event.replace(x.sentence, new))
    x.value, x.sentence = opt, new
    report = shortcut_audit([base, wh])
    assert stand_ins in _failed(report)
    assert any("is an option" in str(d) for d in _detail(report, stand_ins))

    wh = copy.deepcopy(pick(small_eps, "observed-nonrec-far", "withheld"))
    x = wh.substitutes[0]
    st = wh.steps[x.step]
    other = next(e for e in get_skin(wh.skin).entities
                 if entity_token_length(e) != entity_token_length(wh.entity))
    new = x.sentence.replace(x.entity, other)
    st.observation, st.event = (st.observation.replace(x.sentence, new),
                                st.event.replace(x.sentence, new))
    x.entity, x.sentence = other, new
    assert stand_ins in _failed(shortcut_audit([base, wh]))

    dbase = pick(small_eps, "derived-nonrec-far")
    wh = copy.deepcopy(pick(small_eps, "derived-nonrec-far", "withheld"))
    assert _failed(shortcut_audit([dbase, wh])) == []
    x = wh.substitutes[0]  # the stand-in base clue: make the clues sum to an option
    target = wh.options[0].value - sum(y.value for y in wh.substitutes[1:] if y.value)
    st = wh.steps[x.step]
    new = x.sentence.replace(f" {x.value}.", f" {target}.")
    st.observation, st.event = (st.observation.replace(x.sentence, new),
                                st.event.replace(x.sentence, new))
    x.value, x.sentence = target, new
    report = shortcut_audit([dbase, wh])
    assert stand_ins in _failed(report)
    assert any("is an option" in str(d) for d in _detail(report, stand_ins))

    wh = copy.deepcopy(pick(small_eps, "derived-nonrec-far", "withheld"))
    st = wh.steps[wh.substitutes[0].step]
    mid = (st.filler_start + st.filler_end) // 2
    st.observation = st.observation[:mid] + "~" + st.observation[mid + 1:]
    assert stand_ins in _failed(shortcut_audit([dbase, wh]))
    assert stand_ins not in _failed(shortcut_audit([wh]))  # needs the base episode

    # text after the filler but outside the event field (the log footer) must match too
    wh = copy.deepcopy(pick(small_eps, "derived-nonrec-far", "withheld"))
    st = wh.steps[wh.substitutes[0].step]
    assert st.observation.count("--- end of log ---") == 1
    st.observation = st.observation.replace("--- end of log ---", "--- end of LOG ---")
    assert stand_ins in _failed(shortcut_audit([dbase, wh]))

    # a stand-in whose name contains the target's (as BITTERN contains TERN) spells the
    # target at the evidence steps without naming it as a word
    wh = copy.deepcopy(pick(small_eps, "observed-nonrec-far", "withheld"))
    old, new_name = wh.substitutes[0].entity, f"{wh.entity}X"
    for st in wh.steps:
        st.observation, st.event = (st.observation.replace(old, new_name),
                                    st.event.replace(old, new_name))
    for x in wh.substitutes:
        x.entity, x.sentence = new_name, x.sentence.replace(old, new_name)
    report = shortcut_audit([base, wh])
    assert named not in _failed(report) and stand_ins in _failed(report)
    assert any("overlaps the target name" in str(d) for d in _detail(report, stand_ins))


def test_audit_catches_distractor_problems(small_eps):
    """D1: a distractor value equal to an option, or a distractor binding shown twice."""
    ep = copy.deepcopy(pick(small_eps, "observed-nonrec-far"))
    ep.distractors[0].value = ep.options[0].value
    assert "distractor_bindings_valid" in _failed(shortcut_audit([ep]))
    ep = copy.deepcopy(pick(small_eps, "observed-nonrec-far"))
    ep.steps[ep.need_step - 1].observation += "\n" + ep.distractors[1].sentence
    assert "distractor_bindings_valid" in _failed(shortcut_audit([ep]))


def test_audit_catches_unbalanced_block(small_eps):
    eps = [copy.deepcopy(e) for e in small_eps if e.variant == "base"]
    for e in eps:  # pretend template 0 has template 1's letter
        if e.template_id == "main-000000":
            other = next(x for x in eps if x.template_id == "main-000001")
            e.correct_label = other.correct_label
    assert "letter_rank_and_n_clues_exact_within_complete_blocks" in _failed(
        shortcut_audit(eps))


def test_audit_catches_a_leak_in_filler(small_eps):
    ep = copy.deepcopy(pick(small_eps, "derived-nonrec-far"))
    s = ep.steps[3]
    leak = f" {ep.target_value} "
    mid = (s.filler_start + s.filler_end) // 2
    s.observation = s.observation[:mid] + leak + s.observation[mid + len(leak):]
    failed = _failed(shortcut_audit([ep]))
    assert "filler_has_no_reserved_strings" in failed
    assert "derived_and_withheld_never_show_target_before_need" in failed


def test_audit_catches_wrong_token_count(small_eps):
    ep = copy.deepcopy(pick(small_eps, "observed-nonrec-near"))
    ep.steps[0].observation += " extra words"
    assert "observation_tokens_equal_v" in _failed(shortcut_audit([ep]))


def test_audit_catches_a_far_cell_that_is_not_far(small_eps):
    ep = copy.deepcopy(pick(small_eps, "observed-nonrec-far"))
    fact = ep.components[0]
    # move the reveal next to the need step
    ep.steps[ep.need_step - 1].observation += "\n" + fact.sentence
    assert "near_far_hold_when_recomputed_from_text" not in _failed(shortcut_audit([ep]))
    ep.steps[fact.step].observation = ep.steps[fact.step].observation.replace(fact.sentence, "")
    assert "near_far_hold_when_recomputed_from_text" in _failed(shortcut_audit([ep]))


def test_baseline_functions():
    from types import SimpleNamespace as O

    E = O(options=[O(label="A", value=301), O(label="B", value=455), O(label="C", value=702)])

    text = "x 455 y 702 z 455\nA) 301\nB) 455\nC) 702"
    hits = option_hits(text, E)
    assert hits == {"B": (2, 14), "C": (1, 8)}
    assert most_frequent_option(hits, E) == "B"
    assert last_seen_option(hits, E) == "B"
    assert most_frequent_option({}, E) == "A"
    assert last_seen_option({}, E) == "C"
    assert option_hits("14552 1455 455x", E) == {"B": (1, 11)}


def test_heuristic_baselines_at_chance(small_eps):
    res = heuristic_baselines(small_eps, calibration_labels=list("ABCDEFGHIJ" * 2 + "A"))
    assert res["pass"]
    for view, rows in res["views"].items():
        for name, row in rows.items():
            assert row["accuracy"] <= res["threshold"], (view, name)
            assert row["n_templates"] == 10
    assert res["prior_label"]["guess"] == "A"


def test_oracle_scores_pass(small_eps):
    res = oracle_scores(small_eps)
    assert res["pass"]
    assert res["key"]["base/rec"]["need_acc"] == 1.0
    assert res["lookup_no_memory"]["base/rec"]["mean_lookups"] == 1.0


def test_reserved_regex():
    r = Reserved([412, 88], ["ORION", "loading bay"])
    assert not r.clean("bay 412 ok") and not r.clean("x=88;") and not r.clean("orion")
    assert not r.clean("the Loading Bay")
    assert r.clean("41234 1412 880 ORIONS horion loading-bay")


def _flattened(ep, replies) -> str:
    """PREREG §3 H3, rebuilt by hand: o_1, "Agent: <a_1>", o_2, ..., o_need, one newline
    between pieces, no preamble or marks; an empty reply writes no line."""
    pieces = []
    for i in range(ep.need_step + 1):
        pieces.append(ep.steps[i].observation)
        if i < ep.need_step and replies[i]:
            pieces.append(f"Agent: {replies[i]}")
    return "\n".join(pieces)


def test_single_turn_control(small_eps):
    ep = pick(small_eps, "derived-nonrec-far")
    c = single_turn_control(ep)
    for i in range(ep.need_step + 1):
        assert ep.steps[i].observation in c["prompt"]
    for i in range(ep.need_step, ep.n_steps):
        if i > ep.need_step:
            assert ep.steps[i].observation not in c["prompt"]
    assert c["prompt"].endswith(ep.need.event)  # ends with the need-step question
    assert c["replies"] == [ep.steps[i].expected_action for i in range(ep.need_step)]
    assert c["reply_mode"] == "oracle"
    assert c["prompt"] == _flattened(ep, c["replies"])
    assert set(c["component_offsets"]) == {x.comp_id for x in ep.components}
    given = single_turn_control(ep, replies=["ok"] * ep.need_step)
    assert given["reply_mode"] == "given"
    assert given["prompt"] == _flattened(ep, ["ok"] * ep.need_step)
    none = single_turn_control(ep, mode="none")
    assert none["reply_mode"] == "none" and "Agent:" not in none["prompt"]
    assert none["prompt"] == "\n".join(ep.observations[:ep.need_step + 1])
    with pytest.raises(ValueError):
        single_turn_control(ep, replies=["ok"])
    with pytest.raises(ValueError):
        single_turn_control(pick(small_eps, "derived-nonrec-far", "restated"))
    with pytest.raises(ValueError):  # recoverable: the prompt would offer an unservable lookup
        single_turn_control(pick(small_eps, "derived-rec-far"))


def _nonrec_base(eps):
    return [e for e in eps if not e.cell.recoverable and e.variant == "base"]


def test_single_turn_prompt_is_prereg_h3s(small_eps):
    """PREREG §3 H3: one message of o_1..o_need in order, each observation before the need
    step followed by one plain "Agent: <its expected action>" line, ending with the need-step
    question; no preamble and no marks. Its lines are the observations' own lines and the
    reply lines, one newline apart."""
    for ep in _nonrec_base(small_eps):
        c = single_turn_control(ep)
        lines = c["prompt"].splitlines()
        want = []
        for i in range(ep.need_step + 1):
            want += ep.steps[i].observation.splitlines()
            if i < ep.need_step:
                want.append(f"Agent: {ep.steps[i].expected_action}")
        assert lines == want
        assert lines[0].startswith("=== console update ")              # o_1's first line
        assert c["prompt"].endswith(ep.need.event)
        assert sum(x.startswith("Agent: ") for x in lines) == ep.need_step
        assert "<<<" not in c["prompt"] and "Console session transcript" not in c["prompt"]


def test_single_turn_evidence_sits_at_the_multi_turn_observation_token_offset(small_eps,
                                                                            default_eps):
    """PREREG §3 H3: "The evidence sits at the same observation-token offset from the need
    question as in the multi-turn episode." Counted with the project tokenizer on each
    observation on its own (PREREG §2.1, as obs_tokens), the offset of every evidence
    component is computed here from the episode's own fields, and the control records the
    same, measured on its prompt's observation spans and on the episode. In the prompt's own
    encoding the gap also holds the reply lines between, plus at most one token per step
    boundary (BPE joins an observation's end with the newline after it)."""
    for ep in _nonrec_base([*small_eps, *default_eps]):
        c = single_turn_control(ep)
        n, enc = ep.need_step, ep.config["tokenizer"]
        need = ep.steps[n]
        to_question = tokens.TokenIndex(need.observation, enc).token_at(need.event_start)
        for comp in (x for x in ep.components if x.step is not None):
            s = comp.step
            obs = ep.steps[s].observation
            at = tokens.TokenIndex(obs, enc).token_at(obs.index(comp.sentence))
            want = (ep.steps[s].obs_tokens - at + sum(ep.steps[i].obs_tokens
                                                      for i in range(s + 1, n)) + to_question)
            o = c["component_offsets"][comp.comp_id]
            assert o["obs_tokens_to_need"] == o["multi_turn_obs_tokens_to_need"] == want
            replies = sum(tokens.count(f"Agent: {ep.steps[i].expected_action}", enc)
                          for i in range(s, n))
            assert replies <= o["single_turn_to_need"] - want <= replies + (n - s)
            assert o["single_turn"] + o["single_turn_from_end"] == c["prompt_tokens"]
            # the evidence sentence starts at its recorded token of the prompt
            idx = tokens.TokenIndex(c["prompt"], enc)
            assert idx.token_at(c["prompt"].index(comp.sentence)) == o["single_turn"]


def test_single_turn_scoring_matches_env(small_eps):
    ep = pick(small_eps, "observed-nonrec-far")
    c = single_turn_control(ep)
    verb, right = ep.need_verb, ep.correct_label
    wrong = next(o.label for o in ep.options if o.label != right)
    assert score_single_turn(c, f"reasoning\nACTION: {verb}({right})")["correct"]
    assert score_single_turn(c, f"ACTION: {verb}({right.lower()})")["correct"]
    assert score_single_turn(c, f"ACTION: {verb}({ep.target_value})")["correct"]
    # a reply in the prompt's own reply style is the need-verb call (strict parse is off)
    assert not c["strict_action_parse"]
    assert score_single_turn(c, f"Agent: {verb}({right})")["correct"]
    r = score_single_turn(c, f"ACTION: {verb}({wrong})")
    assert not r["correct"] and r["outcome"] == "wrong" and r["label"] == wrong
    assert score_single_turn(c, "no idea")["outcome"] == "unparsed"
    assert score_single_turn(c, f"ACTION: lookup({ep.entity})")["outcome"] == "wrong"


def _need_replies(ep) -> list[str]:
    """Need-step replies in every form the parse tells apart."""
    verb, right = ep.need_verb, ep.correct_label
    wrong = next(o.label for o in ep.options if o.label != right)
    routine = ep.steps[ep.need_step - 1].expected_action
    return [f"ACTION: {verb}({right})", f"ACTION: {verb}({wrong})",
            f"ACTION: {verb}({ep.target_value})", f"Agent: {verb}({right})",
            f"Agent: {verb}({wrong})", f"{verb}({right}), or so I think.",
            # a known call after the need-verb call, with no ACTION line: the last one counts
            f"{verb}({right}) after the last {routine}",
            f"Agent: {verb}({right})\nAgent: {routine}", f"Agent: {routine}",
            f"ACTION: {routine}", f"ACTION: lookup({ep.entity})", f"lookup({ep.entity})",
            f"ACTION: answer({right})", f"ACTION: {right}", "no idea", "",
            f"ACTION: {routine}\nACTION: {verb}({right})",
            f"ACTION: {verb}({right})\nACTION: {routine}",
            f"ACTION: {verb}({right}) and answer({wrong})"]


def _env_need_outcome(ep, reply: str) -> str:
    """How `EpisodeEnv` scores `reply` at the need step, after oracle routine replies."""
    env = EpisodeEnv(ep)
    for i in range(ep.need_step):
        env.step(f"ACTION: {ep.steps[i].expected_action}")
    env.step(reply)
    return env.outcomes[ep.need_step]


def test_single_turn_scoring_is_the_need_steps_on_every_reply_form(small_eps):
    """`score_single_turn` scores every reply as `EpisodeEnv` scores the need step, with the
    same known verbs for the non-strict parse (PREREG D4): a routine call after the need-verb
    call is the action read (wrong), not skipped. A lookup is wrong here and invalid_lookup in
    the env: both score 0 in a non-recoverable cell."""
    for cell in ("observed-nonrec-near", "observed-nonrec-far", "derived-nonrec-near",
                 "derived-nonrec-far"):
        ep = pick(small_eps, cell)
        c = single_turn_control(ep)
        for reply in _need_replies(ep):
            want = _env_need_outcome(ep, reply)
            got = score_single_turn(c, reply)
            assert got["outcome"] == {"invalid_lookup": "wrong"}.get(want, want), reply
            assert got["correct"] is (want == "correct")
    ep = pick(small_eps, "observed-nonrec-far")
    routine = ep.steps[ep.need_step - 1].expected_action
    reply = f"{ep.need_verb}({ep.correct_label}) after the last {routine}"
    assert score_single_turn(single_turn_control(ep), reply)["outcome"] == "wrong"


def test_reply_action_class_reads_the_verb_alone(small_eps):
    """The format check's class of a reply (`reply_action_class`): the kind of action the
    scorer reads, by its verb alone, so a right and a wrong option get the same class."""
    assert REPLY_ACTION_CLASSES == ("need_verb", "routine_verb", "other_verb", "none")
    ep = pick(small_eps, "derived-nonrec-far")
    c = single_turn_control(ep)
    got = [reply_action_class(c, r) for r in _need_replies(ep)]
    assert got == ["need_verb", "need_verb", "need_verb", "need_verb", "need_verb",
                   "need_verb", "routine_verb", "routine_verb", "routine_verb",
                   "routine_verb", "routine_verb", "routine_verb", "other_verb", "none", "none",
                   "none", "need_verb", "routine_verb", "need_verb"]
    for reply, cls in zip(_need_replies(ep), got, strict=True):     # the scorer's own parse
        outcome = score_single_turn(c, reply)["outcome"]
        assert (cls == "none") is (outcome == "unparsed")
        if outcome == "correct":
            assert cls == "need_verb"
    strict = {**c, "strict_action_parse": True}               # no ACTION line: nothing read
    assert reply_action_class(strict, f"Agent: {ep.need_verb}({ep.correct_label})") == "none"


TOY = {"K_options": 4, "validity_margin_pp": 10.0, "minor_component_range": [61, 98],
       "option_spacing": 1}


def test_partial_memory_diagnostic_toy():
    """The old option sets (spread over the value range) fail the D2 gate; clustered ones
    built as the generator builds them pass."""
    # 2 clues, addends 61-98: with the base kept, only options in [base + 61, base + 98]
    # stay consistent
    spread = [(2, [500, 70], [570, 600, 700, 300], 570),   # only 570 in [561, 598]
              (2, [500, 90], [570, 590, 700, 300], 590)]   # 570 and 590 remain
    pm = partial_memory_diagnostic(spread, TOY)
    row = pm["by_n_clues"]["2"]
    assert row["narrowing_templates"] == 2 and "clue0" in row["narrowing_examples"]
    assert row["base_and_rule_uniform_accuracy"] == 0.75  # (1 + 1/2) / 2
    assert row["smallest_above_base_accuracy"] == 0.5  # 570 is smallest above 500 both times
    assert not pm["pass"]
    # clustered as the generator builds them (K = 4, rank r): options L..L+3, target L + r,
    # each addend = core + r with the core in [61, 95], base = target - addends
    clustered = [(2, [500, 61 + r], [561 + i for i in range(4)], 561 + r) for r in range(4)]
    clustered += [(3, [450 - r, 70 + r, 80 + r], [600 + i for i in range(4)], 600 + r)
                  for r in range(4)]
    assert all(sum(clues) == target for _, clues, _, target in clustered)
    pm = partial_memory_diagnostic(clustered, TOY)
    assert pm["pass"] and pm["all"]["narrowing_templates"] == 0
    assert pm["all"]["base_and_rule_options_left_mean"] == 4
    assert pm["all"]["base_and_rule_uniform_accuracy"] == 0.25
    assert pm["all"]["smallest_above_base_accuracy"] == 0.25  # rank 0 once per block


def test_generator_aware_bayes_toy():
    """The exact posterior for an agent that knows the sampler: with the base clue alone and
    2 clues it is flat; an addend at the bottom of its range gives the rank away."""
    opts = [600, 601, 602, 603]
    flat = generator_aware_weights({0: 520}, 2, opts, 1, (61, 95))
    assert len(set(flat)) == 1 and flat[0] > 0
    # addend 61 = core + rank needs rank 0 (cores start at 61)
    assert generator_aware_weights({1: 61}, 2, opts, 1, (61, 95)) == [1, 0, 0, 0]
    # 3 clues, base known: the 2 missing addend cores sum to L - base - rank, whose count
    # falls off along the triangle of a sum of two uniforms
    assert generator_aware_weights({0: 450}, 3, opts, 1, (61, 95)) == [29, 28, 27, 26]
    assert generator_aware_weights({0: 478}, 3, opts, 1, (61, 95)) == [1, 0, 0, 0]
    # base and one addend known: the other core is fixed; only the known addend's range binds
    assert generator_aware_weights({0: 450, 1: 75}, 3, opts, 1, (61, 95)) == [1, 1, 1, 1]


def test_partial_memory_from_episodes_matches_templates(small_eps):
    from persistgym.template import sample_template

    pm = partial_memory_from_episodes(small_eps)
    cfg = small_eps[0].config
    items = []
    for i in range(10):
        t = sample_template("main", i, GeneratorConfig.from_dict(cfg))
        items.append((t.n_clues, t.clue_values, t.option_values, t.target_value))
    expected = partial_memory_diagnostic(items, cfg)
    assert set(pm["cells"]) == {f"derived-{r}-{d}" for r in ("nonrec", "rec")
                                for d in ("near", "far")}
    assert all(c == expected for c in pm["cells"].values())
    assert pm["pass"] and expected["all"]["narrowing_templates"] == 0
    assert expected["by_n_clues"]["2"]["n_templates"] == 5  # exact split in the block


def test_partial_memory_gate_on_2000_templates():
    """D2 gate at scale (templates only): zero narrowing templates, both gated heuristics
    <= 0.20, and the reported generator-aware bound below 0.20 too."""
    from persistgym.template import sample_template

    cfg = GeneratorConfig()
    items = [(t.n_clues, t.clue_values, t.option_values, t.target_value)
             for t in (sample_template("main", i, cfg) for i in range(2000))]
    pm = partial_memory_diagnostic(items, cfg.to_dict())
    a = pm["all"]
    assert pm["pass"] and a["narrowing_templates"] == 0
    assert a["base_and_rule_uniform_accuracy"] == pytest.approx(0.1)
    assert a["smallest_above_base_accuracy"] == pytest.approx(0.1)  # rank 0, 1 in 10
    assert a["generator_aware_bayes"]["rule_only"] == pytest.approx(0.1)
    assert pm["by_n_clues"]["2"]["generator_aware_bayes"]["clue0"] == pytest.approx(0.1)
    assert a["generator_aware_bayes_max"] < 0.2


def test_cli_partial_memory(tmp_path, capsys):
    out = tmp_path / "pm.json"
    assert main(["partial-memory", "--n", "30", "--out", str(out)]) == 0
    pm = json.loads(out.read_text(encoding="utf-8"))
    assert pm["all"]["n_templates"] == 30 and pm["indices"] == [0, 30]
    assert "partial memory" in capsys.readouterr().out


def test_parse_overrides():
    assert parse_overrides(["v_tokens=400", "need_index_range=[20,22]", "skins=[\"depot\"]"]) == {
        "v_tokens": 400, "need_index_range": (20, 22), "skins": ("depot",)}
    with pytest.raises(ValueError):
        parse_overrides(["nokey"])


def test_cli_render_requires_whole_blocks(tmp_path, capsys):
    """D7: template counts and start indices in whole balance blocks of K = 10."""
    for start, n in ((0, 2), (5, 10), (0, 15)):
        code = main(["render", "--n", str(n), "--start", str(start), "--no-checks",
                     "--out", str(tmp_path / f"x{start}-{n}")])
        assert code == 2
        assert "multiples of the balance block K=10" in capsys.readouterr().err
        assert not (tmp_path / f"x{start}-{n}").exists()


def test_cli_render(tmp_path, capsys):
    out = tmp_path / "run"
    code = main(["render", "--n", "2", "--split", "pilot", "--W", "6400", "--v", "400",
                 "--set", "assumed_max_reply_tokens=200", "--single-turn", "--gzip",
                 "--partial-blocks", "--out", str(out)])
    assert code == 0
    with gzip.open(out / "episodes.jsonl.gz", "rt", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 2 * 8 * 3
    first = json.loads(lines[0])
    assert first["template_id"] == "pilot-000000" and first["config"]["v_tokens"] == 400
    eps = list(read_jsonl(out / "episodes.jsonl.gz"))
    assert len(eps) == 48 and eps[0].to_dict() == first
    with gzip.open(out / "single_turn.jsonl.gz", "rt", encoding="utf-8") as f:
        controls = [json.loads(line) for line in f]
    assert len(controls) == 2 * 4  # non-recoverable base cells only
    assert all("-nonrec-" in c["cell"] and "lookup(" not in c["system_prompt"] for c in controls)
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["validity_pass"] is True
    pm = summary["partial_memory"]
    assert pm["pass"] and len(pm["cells"]) == 4
    assert all(c["all"]["n_templates"] == 2 for c in pm["cells"].values())
    checks = {c["check"]: c for c in summary["shortcut_audit"]}
    assert checks["lookup_serves_keys_and_refuses_after_cap"]["detail"]["n_episodes"] == 2 * 4
    assert checks["letter_rank_and_n_clues_exact_within_complete_blocks"]["detail"][
        "incomplete_blocks"] == [["pilot", 0]]
    assert set(summary["cells"]) == {
        f"{f}-{r}-{d}" for f in ("observed", "derived") for r in ("nonrec", "rec")
        for d in ("near", "far")}
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["config_hash"]) == 64 and "git_commit" in manifest
    assert "validity_pass=True" in capsys.readouterr().out
