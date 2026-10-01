import csv

import pytest

from common import costs, runmeta


def _row(**over):
    row = {c: "" for c in costs.COLUMNS}
    row.update(experiment="toggle_pilot", cost_usd_list="1.50", cost_usd_billed_est="0.75")
    row.update(over)
    return row


def test_committed_costs_csv_has_exact_header():
    with costs.COSTS_CSV.open(newline="", encoding="utf-8") as f:
        assert next(csv.reader(f)) == costs.COLUMNS


def test_append_and_sum(tmp_path):
    p = tmp_path / "costs.csv"
    p.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    costs.append_row(_row(), p)
    costs.append_row(_row(experiment="arc_path", cost_usd_list="20", cost_usd_billed_est="10"), p)
    rows = costs.read_rows(p)
    assert costs.sums_by_phase(rows)["0"] == pytest.approx(0.75)
    assert costs.sums_by_phase(rows, "cost_usd_list")["1b"] == pytest.approx(20)
    # headroom uses the larger of list and billed spend, conservatively
    assert costs.headroom(100, "1b", rows) == pytest.approx(900 - 20 - 100)


def test_append_rejects_bad_rows(tmp_path):
    p = tmp_path / "costs.csv"
    p.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        costs.append_row({"experiment": "toggle_pilot"}, p)
    with pytest.raises(ValueError):
        costs.append_row(_row(experiment="mystery"), p)


def test_config_hash_is_order_independent():
    assert runmeta.config_hash({"a": 1, "b": [1, 2]}) == runmeta.config_hash({"b": [1, 2], "a": 1})


def test_build_meta_requires_fields():
    with pytest.raises(ValueError):
        runmeta.build_meta(experiment="x")
    fields = {k: None for k in runmeta.REQUIRED}
    fields["config"] = {"cell": "F-0"}
    meta = runmeta.build_meta(**fields)
    assert len(meta["config_hash"]) == 64
    assert "git_commit" in meta and "sdk_versions" in meta
