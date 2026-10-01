import json
from dataclasses import replace

import pandas as pd
import pytest

from analysis import cost_model as cm


@pytest.fixture(scope="module")
def model() -> cm.CostModel:
    return cm.CostModel()


def draws(model, case):
    return model.draws.loc[model.draws.case == case]


def test_inputs_load_and_every_parameter_has_a_source():
    params = pd.read_csv(cm.DATA_DIR / "parameters.csv", dtype=str, keep_default_na=False)
    assert params.name.is_unique
    assert (params.source.str.len() > 0).all()
    inp = cm.load_inputs()
    assert set(inp.prices) == {cm.GEMINI, cm.LUNA, cm.SOL}
    assert inp.prices[cm.SOL] == cm.Price(2.0, 0.10, 10.0)
    assert len(inp.games) == 25


def test_eligible_pool_matches_plan_8_3(model):
    assert model.eligible == sorted(["FT09", "SB26", "R11L", "LP85", "SC25", "CD82"])


def test_cache_billed_factors_from_published_token_profile(model):
    # Standard: 70M in (17% cached) + 8M out; Adapter: 95M in (53% cached) + 4.3M out.
    std = (70 * (0.83 * 0.75 + 0.17 * 0.075) + 8 * 3.75) / (70 * 0.75 + 8 * 3.75)
    pa = (95 * (0.47 * 0.75 + 0.53 * 0.075) + 4.3 * 3.75) / (95 * 0.75 + 4.3 * 3.75)
    f = model.factors
    assert f["standard_cached"]["S0"] == pytest.approx(std)
    assert f["standard_cached"]["S4"] == pytest.approx(pa)
    assert f["flex_cached"]["S0"] == pytest.approx(std / 2)
    assert f["list_nocache"] == {"S0": 1.0, "S4": 1.0}


def test_arc_path_draws(model):
    d = draws(model, "list_nocache")
    assert len(d) == 15 and d.drawn.is_unique
    # 4 seeds-and-configs x sum(S0+S4) of the drawn games, with S1 = S2 at the midpoint.
    assert d.path_1b.min() == pytest.approx(637.72)
    assert d.path_1b.max() == pytest.approx(1053.76)
    assert d.path_1b.mean() == pytest.approx(895.6)
    assert (d.path_1b > 900).sum() == 6
    assert cm.overcap_games(model) == (["R11L", "SC25"], True)
    flex = draws(model, "flex_nocache").set_index("draw").path_1b
    assert (flex * 2).to_numpy() == pytest.approx(d.set_index("draw").path_1b.to_numpy())
    # The remainder plus the seed-1 S0+S4 block is the whole path, in every case.
    for case in cm.ALL_ARC_CASES:
        x = draws(model, case)
        assert (x.remainder_1b + x.seed1_s0s4).to_numpy() == pytest.approx(x.path_1b.to_numpy())


def test_heldout_runs(model):
    h = model.heldout
    assert len(h.loc[h.case == "list_nocache"]) == 30  # 15 undrawn pairs x 2 third games
    lst = h.loc[h.case == "list_nocache", "heldout"]
    assert lst.min() == pytest.approx(597.3)
    assert lst.max() == pytest.approx(934.95)
    # Held-out games are never drawn games.
    for d in draws(model, "list_nocache").itertuples():
        assert not set(d.undrawn.split("+")) & set(d.drawn.split("+"))


def test_truncated_pilot_s1_runs_to_first_compaction_plus_five(model):
    actions = cm.arc_pilot_actions(model.inp)
    assert actions == {"S0": 50, "S1": 14 + 5, "S2": 30, "S4": 50}  # ceil(175k / 13,018) = 14
    per_action = cm.arc_pooled_usd_per_action(model.inp)
    assert per_action["S0"] == pytest.approx(188.76 / 928)
    assert per_action["S4"] == pytest.approx(147.09 / 1152)


def test_persistgym_token_accounting(model):
    inp = model.inp
    f0 = cm.simulate_episode(cm.PG_CELLS["F-0"], 1000, inp)
    assert len(f0) == 28
    assert sum(c.input for c in f0) == pytest.approx(64000 * 29 / 2)  # linear ramp to 64k
    assert f0[-1].input == pytest.approx(64000)
    fr = cm.simulate_episode(cm.PG_CELLS["F-r"], 1000, inp)
    assert sum(c.input for c in fr) - sum(c.input for c in f0) == pytest.approx(800 * 378)
    w = cm.simulate_episode(cm.PG_CELLS["W-n-0"], 1000, inp)
    assert max(c.input for c in w) == pytest.approx(24000)
    assert all(c.cached == 0 for c in w if c.input == 24000)  # cache lost once the window is full
    s = cm.simulate_episode(cm.PG_CELLS["Sum-n-0"], 1000, inp)
    assert len(s) > 28 and max(c.input for c in s) <= 24000


def test_persistgym_per_episode_costs(model):
    # sol F-0 at Flex, 1k output: 928k input (85% cached) + 28k output.
    no_writes = (928e3 * (0.15 * 1.0 + 0.85 * 0.05) + 28e3 * 5.0) / 1e6
    writes = (928e3 * (0.15 * 1.25 + 0.85 * 0.05) + 28e3 * 5.0) / 1e6
    assert model.episode(cm.SOL, "F-0", 1000, True, False) == pytest.approx(no_writes)
    assert model.episode(cm.SOL, "F-0", 1000, True, True) == pytest.approx(writes)
    assert model.episode(cm.SOL, "F-0", 1000, False, True) == pytest.approx(2 * writes)
    t = model.per_episode_table()
    assert set(t.cell) == set(cm.PG_CELLS) and set(t.output_per_call) == {1000, 2000, 3000}
    one_k = t.loc[t.output_per_call == 1000].set_index(["model", "cell"])
    for m in (cm.LUNA, cm.SOL):
        assert one_k.loc[(m, "F-r"), "usd_flex_writes"] > one_k.loc[(m, "F-0"), "usd_flex_writes"]
        assert one_k.loc[(m, "W-n-0"), "write_uplift"] > one_k.loc[(m, "F-0"), "write_uplift"]
    assert (t.usd_flex_writes > t.usd_flex_no_writes).all()


def test_central_items_add_up(model):
    items = model.items(cm.CENTRAL)
    assert {i[2] for i in items} <= set(cm.PAYEES)
    assert cm.total(items, payee="ARC Prize") == 0 and cm.total(items, payee="GPU") == 0
    by_phase = cm.pivot_payee(items, "phase")
    by_block = cm.pivot_payee(items, "block")
    grand = cm.total(items)
    assert by_phase.iloc[-1]["total"] == pytest.approx(grand)
    assert by_block.iloc[-1]["total"] == pytest.approx(grand)
    assert by_phase.iloc[-1][["Google", "OpenAI"]].sum() == pytest.approx(grand)


def test_mean_scenario_is_the_average_over_draws(model):
    per = [cm.total(model.items(replace(cm.CENTRAL, draw=d, third=t))) for d, t in model.combos()]
    assert cm.total(model.items(cm.CENTRAL)) == pytest.approx(sum(per) / len(per))


def test_cap_1a_sizing(model):
    s = replace(cm.CENTRAL, output_tokens=3000)
    assert cm.total(model.items(s), phase="1a") > 450
    capped = model.items(replace(s, cap_1a=True))
    assert cm.total(capped, phase="1a") == pytest.approx(450)
    assert cm.total(capped, phase="1b") == pytest.approx(cm.total(model.items(s), phase="1b"))


def test_phase_sized_to_its_cap_is_not_flagged_over_cap(model):
    # The scaled 1a sum is 450 only up to float rounding; it must not read as over the cap.
    t = cm.totals_table(model)
    capped = t.loc[t.scenario.str.contains("sized to its cap") & (t.phase == "1a")]
    assert capped.total.item() == pytest.approx(450)
    assert not capped.over_cap.item()
    assert cm.above_cap(450.0000000000001, 450) is False and cm.above_cap(450.01, 450) is True
    # The central case really is over the 1a cap (the repeat subset pushes it to ~$481).
    central = t.loc[(t.scenario == "central / ARC flex_cached") & (t.phase == "1a")]
    assert central.over_cap.item()


def test_blocks_table_ranges_are_ordered(model):
    b = cm.blocks_table(model)
    assert set(b.case) == set(cm.ALL_ARC_CASES)
    assert (b.low <= b.central + 1e-9).all() and (b.central <= b.high + 1e-9).all()
    assert (b.high_1a_capped <= b.high + 1e-9).all()


def test_comparison_covers_every_reference_key(model):
    comp = cm.comparison_table(model)
    ref = pd.read_csv(cm.DATA_DIR / cm.REFERENCE_FILE)
    assert list(comp.key) == list(ref.key)
    # The ARC path arithmetic is pure bookkeeping on the published table: it must agree.
    arc = comp.loc[comp.key.str.startswith(("arc_1b", "arc_seed1", "arc_remainder", "heldout_"))]
    assert (arc[["diff_low", "diff_high"]].abs() < 0.01).all().all()


def test_main_writes_tables_and_meta(tmp_path, capsys):
    assert cm.main(["--out-dir", str(tmp_path)]) == 0
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert meta["experiment"] == "cost_model" and meta["paid_calls"] == 0
    assert set(meta["config"]["input_sha256"]) == set(cm.INPUT_FILES)
    for name in meta["outputs"]:
        assert (tmp_path / name).exists()
    assert "differ by more than 5%" in capsys.readouterr().out
    opt = meta["config"]["option_a"]
    assert cm.OPTION_A_FILE in opt["input_sha256"] and len(opt["input_sha256"]) == 2
    assert "option_a_summary.md" in meta["outputs"]
    assert {f"{n}.csv" for n in cm.option_a_tables(cm.OptionAModel())} <= set(meta["outputs"])


# --------------------------------------------------------------------------------------------
# Option A (decisions of 2026-10-01)
# --------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def option_a(model) -> cm.OptionAModel:
    return cm.OptionAModel(model)


def test_option_a_inputs_and_recorded_costs(model, option_a):
    params = pd.read_csv(cm.DATA_DIR / cm.OPTION_A_FILE, dtype=str, keep_default_na=False)
    assert params.name.is_unique and (params.source.str.len() > 0).all()
    # 1a $500 and phase 2 $1,250: approved by the researcher on 2026-10-01 (PLAN §17.3).
    assert option_a.caps == {"0": 100, "1a": 500, "1b": 900, "2": 1250}
    arc = option_a.arc
    assert set(arc.loc[arc.role == "path", "game"]) == {"FT09", "SB26", "R11L", "CD82"}
    assert set(arc.loc[arc.role == "heldout", "game"]) == {"SP80", "VC33", "TN36"}
    # The recordings' list costs are the published costs of the premise table, to the cent.
    published = model.inp.games.set_index("game")
    lst = arc.loc[arc.basis == "list_nocache"].set_index("game")
    assert lst.S0.to_numpy() == pytest.approx(published.loc[lst.index, "std_cost_usd"], abs=0.006)
    assert lst.S4.to_numpy() == pytest.approx(published.loc[lst.index, "pa_cost_usd"], abs=0.006)
    # Billed re-prices cached input only, so it never exceeds list.
    billed = arc.loc[arc.basis == "billed_standard"].set_index("game")
    assert (billed.S0 <= lst.S0).all() and (billed.S4 <= lst.S4).all()
    assert billed.loc["FT09", "S0"] == pytest.approx(27.7040, abs=1e-3)


def test_option_a_arc_rules(option_a):
    for basis in cm.OA_BASES:
        mid = option_a.arc_path(basis, "midpoint")
        # Midpoint rule: 2 seeds x (S0 + S4 + 2 x midpoint) = 4 x the seed-1 S0+S4 block.
        assert mid["path_1b"] == pytest.approx(4 * mid["seed1_s0s4"])
        cpc = option_a.arc_path(basis, "checkpoint_c")
        assert cpc["seed1_s0s4"] == mid["seed1_s0s4"] and cpc["path_1b"] >= mid["path_1b"]
    a = option_a.arc.set_index(["basis", "game"])
    # CD82: S0 $11.6785 over 60 calls, S4 took 207 actions.
    assert a.loc[("list_nocache", "CD82"), "checkpoint_c"] == pytest.approx(11.6785 / 60 * 207,
                                                                             rel=1e-4)
    assert (option_a.arc.checkpoint_c >= option_a.arc.S0 - 1e-9).all()
    with pytest.raises(ValueError):
        option_a.arc_s12("billed_standard", "nope")


def test_option_a_sol_reallocation_and_repeats(model, option_a):
    s = cm.OPTION_A_CENTRAL
    assert option_a.sol_templates(s) == (120, 40)
    # The ceiling is T_d = 210 (T_o = 70); T_d is always a multiple of 30 (D7, D11).
    assert option_a.sol_templates(replace(s, sol_td=210)) == (210, 70)
    for bad in (0, -30, 100, 200, 240):
        with pytest.raises(ValueError, match="not allowed"):
            option_a.sol_templates(replace(s, sol_td=bad))
    assert option_a.with_repeats(120, True) == 132 and option_a.with_repeats(70, True) == 77
    central = {n: u for *_, n, u in model.items(cm.CENTRAL)}
    # T_d = 120, T_o = 40 is budget-neutral with PLAN's 40 templates x 8 task cells.
    assert sum(option_a.sol_lines(s)) == pytest.approx(central["sol H2 core"])
    no_rep = sum(option_a.sol_lines(replace(s, sol_repeats=False)))
    assert sum(option_a.sol_lines(s)) / no_rep == pytest.approx((2 * 132 + 2 * 44) / 320)
    items = {n: u for *_, n, u in option_a.items(s)}
    assert items["luna sweep"] == pytest.approx(central["luna sweep"])  # 100 + 10 repeats


def test_option_a_luna_controls_follow_d36(model, option_a):
    """Restated-at-need: full F-0 episodes on all 8 task cells; single-turn: one prompt on each
    of the 4 non-recoverable task cells; both on luna's 100 templates plus the 10 repeats."""
    s = cm.OPTION_A_CENTRAL
    ctl = option_a.luna_controls(s)
    assert ctl["restated_episodes"] == 110 * 8 and ctl["single_turn_prompts"] == 110 * 4
    assert ctl["restated_usd"] == pytest.approx(880 * model.episode(cm.LUNA, "F-0", 1000))
    assert ctl["single_turn_usd"] == pytest.approx(440 * model.control_prompt(cm.LUNA, 1000,
                                                                              True, True))
    no_rep = option_a.luna_controls(replace(s, repeats=False))
    assert no_rep["restated_episodes"] == 800 and no_rep["single_turn_prompts"] == 400
    items = {n: u for *_, n, u in option_a.items(s)}
    assert "luna control prompts" not in items
    assert items["luna restated-at-need control (F-0 episodes; D36)"] == ctl["restated_usd"]
    assert items["luna single-turn control prompts (D36)"] == ctl["single_turn_usd"]
    # Full episodes cost more than the single prompts PLAN §12 priced (1,600 at 48k input).
    old = {n: u for *_, n, u in model.items(cm.CENTRAL)}["luna control prompts"]
    assert ctl["restated_usd"] + ctl["single_turn_usd"] > old
    # The A1 scenarios are unchanged: they keep the 1,600 single prompts.
    assert old == pytest.approx(1600 * model.control_prompt(cm.LUNA, 1000, True, True))


def test_option_a_items(model, option_a):
    items = option_a.items(cm.OPTION_A_CENTRAL)
    by_name = {n: u for *_, n, u in items}
    assert by_name["ARC dev games (at the dev cap)"] == 150
    g3 = by_name["G3 v0 runs (4, outside the dev cap)"]
    assert g3 == pytest.approx(option_a.arc_g3("billed_standard", "midpoint"))
    assert by_name["G3 re-run reserve"] == pytest.approx(0.2 * g3)
    held = next(u for n, u in by_name.items() if n.startswith("held-out runs (18"))
    assert by_name["held-out re-run reserve"] == pytest.approx(0.2 * held)
    # D21: no Flex probe calls, so the Gemini probe costs less than the A1 one.
    assert 0 < by_name["Gemini acceptance probe (standard tier; no Flex probe, D21)"] < (
        model.gemini_probe)
    assert cm.total(items, phase="1b") == pytest.approx(
        1.2 * option_a.arc_path("billed_standard", "midpoint")["path_1b"])
    by_phase = cm.pivot_payee(items, "phase")
    assert by_phase.iloc[-1]["total"] == pytest.approx(cm.total(items))
    with pytest.raises(ValueError):
        option_a.items(replace(cm.OPTION_A_CENTRAL, arc_basis="flex"))


def test_option_a_tables(option_a):
    t = cm.option_a_tables(option_a)
    f = t["optA_forecasts"]
    g0 = f.loc[f.metric.str.startswith("G0") & (f.basis == "billed_standard")].iloc[0]
    assert g0.usd_with_reserve == pytest.approx(1.2 * g0.usd)
    assert g0.headroom_usd == pytest.approx(900 - g0.usd_with_reserve)
    z = t["optA_sizing_1a"]
    assert set(z.T_d) == {90, 120, 150, 180, 210} and (z.sol_repeats_usd > 0).all()
    assert (z.T_d % 30 == 0).all() and (z.T_o * 3 == z.T_d).all()
    one = z.loc[(z.T_d == 120) & (z.output_per_call == 1000) & (z.luna_cells == 8)].iloc[0]
    assert one.sol_episodes == 704
    ctl = option_a.luna_controls(cm.OPTION_A_CENTRAL)
    assert one.luna_controls_usd == pytest.approx(ctl["restated_usd"] + ctl["single_turn_usd"])
    tot = t["optA_totals_by_phase_payee"]
    assert set(tot.loc[tot.phase != "total", "cap"]) == {100, 500, 900, 1250}
    lines = option_a.summary_lines(t)
    assert any(line.startswith("- G0 forecast") for line in lines)
    assert any(line.startswith("- Restated-at-need:") for line in lines)
    assert not any("roposed" in line for line in lines)
