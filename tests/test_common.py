import csv
import re

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


def test_phase_caps_are_the_a2_caps():
    # PLAN.md amendment A2 (§17.3), approved by the researcher on 2026-10-01: 1a 450 -> 500,
    # phase 2 950 -> 1250; 0 and 1b unchanged.
    assert costs.PHASE_CAPS == {"0": 100.0, "1a": 500.0, "1b": 900.0, "2": 1250.0}
    assert costs.headroom(0, "1a", []) == pytest.approx(500)
    assert costs.headroom(0, "2", []) == pytest.approx(1250)


def _plan_cap_table() -> dict[str, float]:
    """'Cap from A2' column of the PLAN.md §17.3 table, by phase."""
    plan = (costs.REPO_ROOT / "PLAN.md").read_text(encoding="utf-8")
    heading = re.search(r"^### 17\.3 Phase caps$", plan, flags=re.MULTILINE)
    assert heading, "PLAN.md has no '### 17.3 Phase caps' heading"
    section = plan[heading.end():].split("\n#", 1)[0]
    row = re.compile(r"^\| (0|1a|1b|2) \| \$([\d,]+) \| \$([\d,]+) \|", flags=re.MULTILINE)
    return {m[1]: float(m[3].replace(",", "")) for m in row.finditer(section)}


def test_phase_caps_match_plan_section_17_3():
    assert _plan_cap_table() == costs.PHASE_CAPS


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
