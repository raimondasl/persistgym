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
