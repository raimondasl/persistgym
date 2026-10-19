import csv
import re
import subprocess

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


def test_append_writes_whole_lf_rows(tmp_path):
    """The locked append (common/oslock.py) writes one LF-terminated row at the end of the
    file, as git stores the ledger: no CR on any platform."""
    p = tmp_path / "costs.csv"
    header = (",".join(costs.COLUMNS) + "\n").encode()   # as committed: LF
    p.write_bytes(header)
    costs.append_row(_row(run_id="r1", notes="a, \"quoted\" note"), p)
    data = p.read_bytes()
    assert data.startswith(header) and data.endswith(b"\n") and b"\r" not in data
    assert data.count(b"\n") == 2
    (row,) = costs.read_rows(p)
    assert (row["run_id"], row["notes"]) == ("r1", "a, \"quoted\" note")


def test_append_never_glues_a_row_to_a_torn_last_line(tmp_path):
    """A row cut short by a crash stays a separate, unreadable row (the paid guard refuses
    it), instead of swallowing the next one."""
    p = tmp_path / "costs.csv"
    p.write_text(",".join(costs.COLUMNS) + "\n2026-10-03T00:00:00+00:00,torn,M0",
                 encoding="utf-8")
    costs.append_row(_row(run_id="r2"), p)
    rows = costs.read_rows(p)
    assert [r["run_id"] for r in rows] == ["torn", "r2"]
    assert rows[1]["cost_usd_billed_est"] == "0.75" and rows[0]["cost_usd_list"] is None
    p.write_bytes(p.read_bytes() + b"x,half\r")          # torn right after its CR
    costs.append_row(_row(run_id="r3"), p)
    assert [r["run_id"] for r in costs.read_rows(p)] == ["torn", "r2", "half", "r3"]


def test_append_to_a_missing_ledger_writes_the_header(tmp_path):
    p = tmp_path / "costs.csv"
    costs.append_row(_row(run_id="r1"), p)
    assert [r["run_id"] for r in costs.read_rows(p)] == ["r1"]


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


# --- the git state of a paid run (common/runmeta.py) ---------------------------------------

def _record_runs(monkeypatch, platform: str) -> list[dict]:
    seen = []

    def run(args, **kw):
        seen.append({"args": args, **kw})
        return subprocess.CompletedProcess(args, 0, stdout="0" * 40 + "\n", stderr="")
    monkeypatch.setattr(runmeta.subprocess, "run", run)
    monkeypatch.setattr(runmeta.sys, "platform", platform)
    return seen


@pytest.mark.parametrize("platform, flags", [("win32", 0x08000000), ("linux", 0)])
def test_git_starts_without_a_console_window_on_windows(monkeypatch, platform, flags):
    """A process that has lost its console (the 2026-10-02 incident: a run left going after
    the shell that started it was stopped) cannot start a console program that would attach
    to it (exit 0xC0000142); git started with CREATE_NO_WINDOW gets no console window."""
    seen = _record_runs(monkeypatch, platform)
    assert runmeta.git_state() == {"git_commit": "0" * 40, "git_dirty": True}
    assert [s["args"][1:] for s in seen] == [["rev-parse", "HEAD"],
                                             ["status", "--porcelain", "--untracked-files=no"]]
    assert all(s["creationflags"] == flags and s["check"] is True
               and s["stdin"] == subprocess.DEVNULL for s in seen)
    assert runmeta.CREATE_NO_WINDOW == 0x08000000


def test_a_git_that_fails_raises(monkeypatch):
    """The error stays explicit: no guessed commit is ever recorded."""
    def fails(args, **kw):
        raise subprocess.CalledProcessError(3221225794, args)
    monkeypatch.setattr(runmeta.subprocess, "run", fails)
    with pytest.raises(subprocess.CalledProcessError, match="3221225794"):
        runmeta.git_state()


def test_build_meta_records_the_git_state_given_and_starts_no_git(monkeypatch):
    def fails(repo=None):
        raise AssertionError("git_state must not run")
    fields = {k: None for k in runmeta.REQUIRED}
    fields["config"] = {"cell": "F-0"}
    state = {"git_commit": "c0de" * 10, "git_dirty": False}
    monkeypatch.setattr(runmeta, "git_state", fails)
    meta = runmeta.build_meta(git=state, **fields)
    assert {k: meta[k] for k in runmeta.GIT_KEYS} == state
    # the run's own PREREG and SDK versions may be given (account-run)
    meta = runmeta.build_meta(git=state, prereg_version="9.9", sdk_versions={"x": "1"},
                              **fields)
    assert (meta["prereg_version"], meta["sdk_versions"]) == ("9.9", {"x": "1"})
    for bad in ({"git_commit": "c0de"}, {"git_commit": "zz" * 20, "git_dirty": False},
                {"git_commit": "c0de" * 10, "git_dirty": "no"}, None):
        with pytest.raises(ValueError, match="not a git state"):
            runmeta.check_git_state(bad)
