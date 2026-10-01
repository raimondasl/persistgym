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
