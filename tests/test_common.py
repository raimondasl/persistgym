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
    # Headroom counts billed spend (spend_usd), not the larger of list and billed as before:
    # PLAN's caps are in billed dollars (D23), and on Flex list is twice billed, so counting
    # list would stop a phase at about half its real spend.
    assert costs.headroom(100, "1b", rows) == pytest.approx(900 - 10 - 100)


def test_spend_usd_is_billed_falling_back_to_list():
    assert costs.spend_usd(1.50, 0.75) == 0.75          # Flex: billed, half the list cost
    assert costs.spend_usd(1.50, 0.0) == 0.0            # 0 is a billed estimate; only None
                                                        # (an empty cell) falls back
    assert costs.spend_usd(1.50, None) == 1.50          # no billed estimate: list
    with pytest.raises(ValueError, match="both empty"):
        costs.spend_usd(None, None)


def test_headroom_falls_back_to_list_and_refuses_rows_without_cost():
    rows = [_row(cost_usd_billed_est=""), _row(cost_usd_list="", cost_usd_billed_est="2")]
    assert costs.spend_by_phase(rows)["0"] == pytest.approx(1.50 + 2)
    assert costs.headroom(10, "0", rows) == pytest.approx(100 - 3.50 - 10)
    for bad in ({"cost_usd_list": "", "cost_usd_billed_est": ""},
                {"cost_usd_billed_est": "nan"}, {"cost_usd_billed_est": "-1"}):
        with pytest.raises(ValueError, match="costs.csv line 3"):
            costs.headroom(10, "0", [_row(), _row(**bad)])


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


def test_optional_columns_default_to_empty(tmp_path):
    p = tmp_path / "costs.csv"
    p.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    row = {k: v for k, v in _row().items() if k not in costs.OPTIONAL_COLUMNS}
    costs.append_row(row, p)
    (written,) = costs.read_rows(p)
    assert all(written[c] == "" for c in costs.OPTIONAL_COLUMNS)


def test_summary_prints_spend_billed_and_list(monkeypatch, capsys):
    """`python -m common.costs` shows the spend the caps count next to both logged sums."""
    rows = [_row(), _row(experiment="arc_path", cost_usd_list="20", cost_usd_billed_est="")]
    monkeypatch.setattr(costs, "read_rows", lambda: rows)
    assert costs.main() == 0
    lines = {x.split()[0]: x.split()[1:] for x in capsys.readouterr().out.splitlines()[2:]}
    assert lines["0"] == ["0.75", "0.75", "1.50", "100"]   # Flex row: spend is billed
    assert lines["1b"] == ["20.00", "0.00", "20.00", "900"]  # no billed: spend is list
    assert lines["total"] == ["20.75", "0.75", "21.50"]
    monkeypatch.setattr(costs, "read_rows", lambda: [_row(cost_usd_list="",
                                                           cost_usd_billed_est="")])
    assert costs.main() == 1
    assert "line 2: no cost" in capsys.readouterr().err
