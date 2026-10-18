"""G1 gate metrics (analysis/g1.py, PREREG §4.4, §10.2)."""

import json

import pytest

from analysis import g1


def test_luna_validity_rates_from_the_committed_runs():
    """Block 1's luna validity runs (results/decisions.md, 2026-10-02): restated 160/160,
    withheld 19/160, both on the default config."""
    runs = g1.validity_runs(g1.REPO_ROOT / "results", g1.MODEL)
    assert set(runs) == {"restated", "withheld"}
    r, w = runs["restated"], runs["withheld"]
    assert (r["correct"], r["n"], r["n_excluded"]) == (160, 160, 0)
    assert (w["correct"], w["n"], w["n_excluded"]) == (19, 160, 0)
    assert len(r["per_cell"]) == len(w["per_cell"]) == 8
    assert sum(c["n"] for c in w["per_cell"].values()) == 160
    assert g1.llm_rule(runs)["pass"]


def test_llm_rule_thresholds():
    def runs(r, w):
        return {"restated": {"rate": r}, "withheld": {"rate": w}}
    assert g1.llm_rule(runs(0.85, 0.20))["pass"]
    assert not g1.llm_rule(runs(0.849, 0.10))["pass"]
    assert not g1.llm_rule(runs(0.95, 0.201))["pass"]
    assert not g1.llm_rule({"restated": {"rate": 1.0}})["pass"]


def test_validity_runs_refuse_two_runs_of_one_variant(tmp_path):
    src = g1.REPO_ROOT / "results" / "persistgym_validity"
    for name in ("20261002T084243Z-F-0-gpt-6-luna", "20261002T084243Z-F-0-gpt-6-luna"[:-14]
                 + "X-F-0-gpt-6-luna"):
        d = tmp_path / "persistgym_validity" / name
        d.mkdir(parents=True)
        for f in ("meta.json", "episodes.jsonl"):
            (d / f).write_bytes((src / "20261002T084243Z-F-0-gpt-6-luna" / f).read_bytes())
    with pytest.raises(ValueError, match="more than one"):
        g1.validity_runs(tmp_path, g1.MODEL)


def test_validity_runs_skip_other_generator_configs(tmp_path):
    src = g1.REPO_ROOT / "results" / "persistgym_validity" / "20261002T084243Z-F-0-gpt-6-luna"
    d = tmp_path / "persistgym_validity" / "20261003T000000Z-F-0-gpt-6-luna"
    d.mkdir(parents=True)
    meta = json.loads((src / "meta.json").read_text(encoding="utf-8"))
    meta["config"]["generator_config_hashes"] = ["0" * 64]
    (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (d / "episodes.jsonl").write_bytes((src / "episodes.jsonl").read_bytes())
    assert g1.validity_runs(tmp_path, g1.MODEL) == {}


def test_audit_on_ten_validity_templates_passes(tmp_path):
    a = g1.run_audit("validity", 10, tmp_path / "audit_validity.json")
    assert a["pass"] and a["oracles_ok"] and a["partial_memory_pass"]
    assert a["n_templates"] == 10 and a["baselines_max"] <= 0.20 and not a["failed_checks"]


def test_summary_for_another_model_names_it_and_drops_sols_section():
    """`--model claude-haiku-5-5` (PREREG §17.8): its own runs under "llm", no sol report."""
    run = {"run_id": "r", "correct": 160, "n": 160, "rate": 1.0, "n_excluded": 0,
           "exit_reasons": ["DONE"], "per_cell": {"observed-rec-far": {"correct": 20, "n": 20}}}
    g = {"generated_utc": "2026-10-18T00:00:00+00:00", "git_commit": "abcdef0", "git_dirty": False,
         "model": "claude-haiku-5-5",
         "llm": {"runs": {"restated": run, "withheld": {**run, "correct": 0, "rate": 0.0}},
                 "rule": g1.llm_rule({"restated": run, "withheld": {**run, "correct": 0, "rate": 0.0}})},
         "audits": [], "audits_pass": True,
         "spotcheck": {"package": "p", "cells": {}, "complete": True, "flagged": [],
                       "totals": {"no_shortcut": 160, "possible_shortcut": 0, "shortcut": 0,
                                  "unreviewed": 0}},
         "spend_by_phase": {"1a": 1.0}}
    text = "\n".join(g1.summary_lines(g))
    assert "Model claude-haiku-5-5" in text and "--model claude-haiku-5-5" in text
    assert "amendment R8" in text and "gpt-6.1-sol" not in text
    assert "160/160 = 100.0%" in text and "LLM rule: **met**" in text
