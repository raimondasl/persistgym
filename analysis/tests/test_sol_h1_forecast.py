"""The R4 forecast (analysis/sol_h1_forecast.py; PREREG §17.4): its inputs, an independent
re-derivation of its numbers from results/costs.csv, its outputs and what it never reads."""

from __future__ import annotations

import csv
import dataclasses
import json

import pytest

from analysis import sol_h1_forecast as f
from common import costs

ROWS = {r["run_id"]: r for r in csv.DictReader(costs.COSTS_CSV.open(encoding="utf-8"))}


@pytest.fixture(scope="module")
def built():
    return f.build()


def _billed(run_id: str) -> float:
    return float(ROWS[run_id]["cost_usd_billed_est"])


def _at_sol_prices(run_id: str) -> float:
    """A row's token counts priced by hand at sol's Flex prices: $2.00 input, $0.10 cached,
    $10.00 output per million, cache writes at 1.25 times input, Flex half price."""
    r = {k: int(ROWS[run_id][k] or 0) for k in ("input_tokens", "cached_input_tokens",
                                                 "cache_write_tokens", "output_tokens")}
    plain = r["input_tokens"] - r["cached_input_tokens"] - r["cache_write_tokens"]
    return 0.5 * (2.0 * plain + 0.10 * r["cached_input_tokens"]
                  + 2.5 * r["cache_write_tokens"] + 10.0 * r["output_tokens"]) / 1e6


def test_the_design_counts():
    assert f.main_episodes(100) == 440 and f.main_episodes(50) == 220   # 4 x (T + T/10)
    for bad in (0, 95, -10):
        with pytest.raises(ValueError):
            f.main_episodes(bad)
    assert f.R4_CELLS == ("F-0", "W-0", "W-n-0")
    assert f.VALIDITY_EPISODES == 20 * 4 * 2 and f.PILOT_EPISODES == 2 * 4


def test_the_inputs_are_block_1s_runs(built):
    runs, _, _, _ = built
    assert runs[f.SOL_F0_PILOT].episodes == runs[f.SOL_FR_PILOT].episodes == 8
    assert all(runs[r].episodes == 8 for r in f.LUNA_PILOT.values())
    assert all(runs[r].episodes == 160 for r in f.LUNA_VALIDITY)
    assert {runs[r].model for r in (f.SOL_F0_PILOT, f.SOL_FR_PILOT)} == {f.SOL}
    assert {runs[r].model for r in f.LUNA_PILOT.values()} == {f.LUNA}
    for run_id, run in runs.items():
        assert run.billed_usd == _billed(run_id)
    # the two sol rows played the same episodes with nearly the same input; F-0's came from
    # the cache (the reason for the central basis)
    f0, fr = runs[f.SOL_F0_PILOT], runs[f.SOL_FR_PILOT]
    assert abs(f0.input_tokens - fr.input_tokens) < 100
    assert f0.cache_write_tokens * 50 < fr.cache_write_tokens


def test_the_forecast_rederived_independently(built):
    """Every R4 line, recomputed here from the costs.csv rows by hand."""
    _, scs, rows, _ = built
    luna = {c: _billed(r) / 8 for c, r in f.LUNA_PILOT.items()}
    luna_sol = {c: _at_sol_prices(f.LUNA_PILOT[c]) / 8 for c in f.R4_CELLS}
    val = (_billed(f.LUNA_VALIDITY[0]) + _billed(f.LUNA_VALIDITY[1])) / 320 / luna["F-0"]
    bases = {
        "low": (_billed(f.SOL_F0_PILOT) / 8, {c: luna[c] / luna["F-0"] for c in f.R4_CELLS},
                1.0),
        "central": (_billed(f.SOL_FR_PILOT) / 8,
                    {c: luna_sol[c] / luna_sol["F-0"] for c in f.R4_CELLS}, val)}
    for name, (f0, ratio, vf) in bases.items():
        assert scs[name].f0_per_episode == pytest.approx(f0)
        assert scs[name].validity_factor == pytest.approx(vf)
        for c in f.R4_CELLS:
            assert scs[name].ratio[c] == pytest.approx(ratio[c])
        want = {("pilot", "W-0"): 8 * f0 * ratio["W-0"],
                ("pilot", "W-n-0"): 8 * f0 * ratio["W-n-0"],
                ("validity", "F-0"): 160 * f0 * vf}
        for T in (100, 50):
            for c in f.R4_CELLS:
                want[(f"main_T{T}", c)] = 4 * (T + T // 10) * f0 * ratio[c]
        got = {(r["item"], r["harness_cell"]): r["usd"] for r in rows
               if r["scenario"] == name and r["harness_cell"] != "all"}
        assert got == pytest.approx(want)
        for item in ("pilot", "validity", "main_T100", "main_T50"):
            assert f.item_total(rows, name, item) == pytest.approx(
                sum(v for (i, _), v in want.items() if i == item))
    # the committed numbers (PREREG §17.4): central and low, T = 100 and 50
    assert f.r4_total(rows, "central", 100) == pytest.approx(279.49, abs=0.005)
    assert f.r4_total(rows, "central", 50) == pytest.approx(147.06, abs=0.005)
    assert f.r4_total(rows, "low", 100) == pytest.approx(81.06, abs=0.005)
    assert f.item_total(rows, "central", "main_T100") == pytest.approx(264.87, abs=0.005)
    assert f.item_total(rows, "central", "validity") == pytest.approx(10.28, abs=0.005)
    assert f.item_total(rows, "central", "pilot") == pytest.approx(4.34, abs=0.005)
    # window cells cost more at sol's prices than at luna's (cached input 1/20 vs 1/10)
    assert scs["central"].ratio["W-0"] > scs["low"].ratio["W-0"] > 3


def test_the_phase_1a_picture(built):
    runs, _, rows, p1a = built
    line = {r["line"]: r["usd"] for r in p1a}
    spent = sum(float(r["cost_usd_billed_est"] or r["cost_usd_list"]) for r in ROWS.values()
                if costs.phase_of(r["experiment"]) == "1a")
    assert line["spent"] == pytest.approx(spent)
    assert line["cap_1a"] == costs.PHASE_CAPS["1a"] == 500
    # R3's engagement check (2026-10-03) is in the ledger: its two rows are phase 1a
    r3 = ("20261003T055240Z-F-r-gpt-6.1-sol", "20261003T060120Z-F-0-gpt-6.1-sol")
    assert all(costs.phase_of(ROWS[r]["experiment"]) == "1a" for r in r3)
    assert sum(_billed(r) for r in r3) == pytest.approx(0.890249, abs=1e-6)
    assert line["spent"] == pytest.approx(3.87, abs=0.005)
    ctx = f.context_rows(runs)
    assert set(ctx) == {"luna_main_sweep", "luna_controls"}
    assert line["luna_main_sweep_and_controls"] == pytest.approx(
        ctx["luna_main_sweep"] + ctx["luna_controls"])
    assert ctx["luna_main_sweep"] == pytest.approx(
        880 * sum(_billed(f.LUNA_PILOT[c]) / 8 for c in f.LUNA_SWEEP_CELLS))
    assert line["sol_h2"] == 0.0                         # ended by R3's hard stop
    for sc in ("central", "low"):
        for T in (100, 50):
            base = line["spent"] + line["luna_main_sweep_and_controls"]
            r4 = f.r4_total(rows, sc, T)
            assert line[f"r4_{sc}_T{T}"] == pytest.approx(r4)
            assert line[f"total_{sc}_T{T}"] == pytest.approx(base + r4)
    # the committed numbers (PREREG §17.4)
    assert line["total_central_T100"] == pytest.approx(318.87, abs=0.005)
    assert line["total_central_T50"] == pytest.approx(186.44, abs=0.005)
    assert line["total_central_T100"] < 500


def test_window_cells_lose_about_half_of_their_caching(built):
    """The caching claim of the summary and PREREG §17.4, from luna's pilot rows."""
    runs, _, _, _ = built
    share = {c: runs[f.LUNA_PILOT[c]].cached_share for c in f.R4_CELLS}
    for c in f.R4_CELLS:
        r = ROWS[f.LUNA_PILOT[c]]
        assert share[c] == pytest.approx(int(r["cached_input_tokens"]) / int(r["input_tokens"]))
    assert share["F-0"] > 0.9 and 0.4 < share["W-0"] < 0.6 and 0.4 < share["W-n-0"] < 0.6


def test_it_never_reads_reasoning_tokens():
    """Pilot blinding (PREREG §11): the forecast keeps no reasoning-token field, and its
    outputs carry none."""
    assert "reasoning_tokens" not in {x.name for x in dataclasses.fields(f.Run)}


def test_main_writes_the_forecast(tmp_path, capsys):
    assert f.main(["--out-dir", str(tmp_path)]) == 0
    assert "R4 in all, T = 100" in capsys.readouterr().out
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "meta.json", "sol_h1_forecast.csv", "sol_h1_phase_1a.csv", "summary.md"]
    with (tmp_path / "sol_h1_forecast.csv").open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == ["scenario", "item", "harness_cell", "episodes",
                                     "usd_per_episode", "usd"]
        out = list(reader)
    assert {r["scenario"] for r in out} == {"low", "central"}
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "279.49" in summary and "264.87" in summary and "## Limits" in summary
    assert "318.87" in summary and "181.13" in summary and "lose most" not in summary
    assert "reasoning tokens" not in summary
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert meta["experiment"] == "cost_model" and meta["paid_calls"] == 0
    assert meta["config"]["inputs"]["sol_fr_pilot"] == f.SOL_FR_PILOT
    assert f.main(["--no-write"]) == 0
