import copy
import gzip
import json

import pytest

from persistgym.cli import main, parse_overrides
from persistgym.config import GeneratorConfig
from persistgym.controls import score_single_turn, single_turn_control
from persistgym.episode import read_jsonl
from persistgym.filler import Reserved
from persistgym.validity import (
    heuristic_baselines,
    last_seen_option,
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


def test_audit_passes(small_eps):
    assert _failed(shortcut_audit(small_eps)) == []


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


def test_single_turn_control(small_eps):
    ep = pick(small_eps, "derived-nonrec-far")
    c = single_turn_control(ep)
    for i in range(ep.need_step + 1):
        assert ep.steps[i].observation in c["prompt"]
    for i in range(ep.need_step, ep.n_steps):
        if i > ep.need_step:
            assert ep.steps[i].observation not in c["prompt"]
    assert c["prompt"].rstrip().endswith(ep.need.event.rstrip())
    assert len(c["replies"]) == ep.need_step
    offs = c["component_offsets"]
    assert set(offs) == {x.comp_id for x in ep.components}
    for o in offs.values():
        # flattened offset = content offset + small per-turn separator overhead
        assert 0 < o["single_turn"] - o["multi_turn_content"] < 30 + 15 * ep.need_step
    given = single_turn_control(ep, replies=["ok"] * ep.need_step)
    assert given["reply_mode"] == "given"
    with pytest.raises(ValueError):
        single_turn_control(ep, replies=["ok"])
    with pytest.raises(ValueError):
        single_turn_control(pick(small_eps, "derived-nonrec-far", "restated"))
    with pytest.raises(ValueError):  # recoverable: the prompt would offer an unservable lookup
        single_turn_control(pick(small_eps, "derived-rec-far"))


def test_single_turn_scoring_matches_env(small_eps):
    ep = pick(small_eps, "observed-nonrec-far")
    c = single_turn_control(ep)
    verb, right = ep.need_verb, ep.correct_label
    wrong = next(o.label for o in ep.options if o.label != right)
    assert score_single_turn(c, f"reasoning\nACTION: {verb}({right})")["correct"]
    assert score_single_turn(c, f"ACTION: {verb}({right.lower()})")["correct"]
    assert score_single_turn(c, f"ACTION: {verb}({ep.target_value})")["correct"]
    r = score_single_turn(c, f"ACTION: {verb}({wrong})")
    assert not r["correct"] and r["outcome"] == "wrong" and r["label"] == wrong
    assert score_single_turn(c, "no idea")["outcome"] == "unparsed"
    assert score_single_turn(c, f"ACTION: lookup({ep.entity})")["outcome"] == "wrong"


def test_partial_memory_diagnostic_toy():
    # 2 clues, addends 61-98: the base-consistent window is [base + 61, base + 98]
    items = [(2, 500, [570, 600, 700, 300], 570),   # only 570 in [561, 598]
             (2, 500, [570, 590, 700, 300], 590),   # 570 and 590 remain
             (3, 400, [530, 600, 590, 300], 590)]   # 3 clues: [523, 595] keeps 530, 590
    pm = partial_memory_diagnostic(items, (61, 98), 4)
    two, three = pm["by_n_clues"]["2"], pm["by_n_clues"]["3"]
    assert two["base_and_range_unique_rate"] == 0.5
    assert two["base_and_range_expected_accuracy"] == 0.75
    assert two["nearest_above_base_accuracy"] == 0.5  # 570 is nearest above 500 both times
    assert three["base_and_range_mean_options_left"] == 2
    assert three["nearest_above_base_accuracy"] == 0.0
    assert pm["all"]["n_templates"] == 3
    with pytest.raises(ValueError):
        partial_memory_diagnostic([(2, 500, [700, 300], 700)], (61, 98), 2)


def test_partial_memory_from_episodes_matches_templates(small_eps):
    from persistgym.template import sample_template

    pm = partial_memory_from_episodes(small_eps)
    cfg = small_eps[0].config
    items = []
    for i in range(10):
        t = sample_template("main", i, GeneratorConfig.from_dict(cfg))
        items.append((t.n_clues, t.clue_values[0], t.option_values, t.target_value))
    assert pm == partial_memory_diagnostic(items, tuple(cfg["minor_component_range"]), 10)


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


def test_cli_render(tmp_path, capsys):
    out = tmp_path / "run"
    code = main(["render", "--n", "2", "--split", "pilot", "--W", "6400", "--v", "400",
                 "--set", "assumed_max_reply_tokens=200", "--single-turn", "--gzip",
                 "--out", str(out)])
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
    assert summary["partial_memory"]["all"]["n_templates"] == 2
    assert set(summary["cells"]) == {
        f"{f}-{r}-{d}" for f in ("observed", "derived") for r in ("nonrec", "rec")
        for d in ("near", "far")}
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["config_hash"]) == 64 and "git_commit" in manifest
    assert "validity_pass=True" in capsys.readouterr().out
