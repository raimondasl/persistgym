"""G0 gate metrics (analysis/g0.py, PREREG §10.1)."""

from types import SimpleNamespace

import pandas as pd
import pytest

from analysis import g0


def _model(rows, reserve=0.2, cap=900.0):
    frame = pd.DataFrame(rows)
    frame["midpoint"] = (frame.S0 + frame.S4) / 2
    return SimpleNamespace(arc_rows=lambda basis, role: frame, reserve=reserve,
                           caps={"1b": cap})


def _ratios(b):
    return {c: {"run_id": f"r-{c}", "b": b[c]} for c in g0.CONFIGS}


def test_cost_rule_is_d27_rule_1_with_measured_ratios():
    """F = Σ_g 2 × [L_S0 b_S0 + L_mid (b_S1 + b_S2) + L_S4 b_S4], times 1 + reserve."""
    m = _model([{"game": "a", "S0": 10.0, "S4": 30.0}, {"game": "b", "S0": 4.0, "S4": 2.0}])
    r = g0.cost_rule(m, _ratios({"S0": 0.5, "S1": 0.6, "S2": 0.7, "S4": 0.8}))
    a = 2 * (10 * 0.5 + 20 * 0.6 + 20 * 0.7 + 30 * 0.8)
    b = 2 * (4 * 0.5 + 3 * 0.6 + 3 * 0.7 + 2 * 0.8)
    assert r["F_billed"] == pytest.approx(a + b)
    assert r["F_with_reserve"] == pytest.approx(1.2 * (a + b))
    assert r["go"] and r["headroom"] == pytest.approx(900 - 1.2 * (a + b))


def test_cost_rule_fails_above_the_cap():
    m = _model([{"game": "a", "S0": 500.0, "S4": 500.0}])
    assert not g0.cost_rule(m, _ratios(dict.fromkeys(g0.CONFIGS, 1.0)))["go"]


def test_pilot_ratios_need_every_config(tmp_path):
    p = tmp_path / "costs.csv"
    p.write_text("run_id,experiment,cell_or_config,cost_usd_list,cost_usd_billed_est\n"
                 "x,arc_pilot,S0,10,8\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no arc_pilot row"):
        g0.pilot_ratios(p)


def test_the_repositorys_toggle_results():
    """Block 1's fork probe (PREREG §17.1): sol verified (20/20 vs 0/20), luna not."""
    t = g0.toggle(g0.REPO_ROOT / "results")
    assert t["gpt-6.1-sol"]["verified"] and not t["gpt-6-luna"]["verified"]
