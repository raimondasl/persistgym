import json

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm
from scipy import special

from analysis import power_sim as ps


def test_marginal_calibration_hits_the_target():
    for p in (0.6, 0.8, 0.88):
        a = ps.intercept_for(p, 1.0, "marginal")
        assert ps.marginal_success(a, 1.0) == pytest.approx(p, abs=1e-9)
        assert ps.intercept_for(p, 1.0, "conditional") == pytest.approx(special.logit(p))
    # With template heterogeneity the marginal intercept is further from 0 than logit(p).
    assert ps.intercept_for(0.8, 1.0, "marginal") > special.logit(0.8)


@pytest.mark.parametrize("design", ps.SEC10_DESIGNS[:4], ids=lambda d: d.label)
def test_fast_fe_logit_matches_statsmodels(design):
    data = ps.simulate_sec10(design, 0.2, np.random.default_rng(7))
    z = np.column_stack([data["harness"], data["distance"], data["harness"] * data["distance"]])
    fast = ps.fe_logit(data["y"], data["template"], z, engine="fast")
    ref = ps.fe_logit(data["y"], data["template"], z, engine="statsmodels")
    for a, b in zip(fast, ref, strict=True):
        assert a == pytest.approx(b, rel=1e-7, abs=1e-9)


@pytest.mark.parametrize("engine", ["fast", "statsmodels"])
def test_clusters_only_correction_matches_statsmodels(engine):
    # 'clusters' = statsmodels' cluster sandwich without its correction, times G/(G-1).
    data = ps.simulate_sec10(ps.SEC10_DESIGNS[4], 0.2, np.random.default_rng(11))
    z = np.column_stack([data["harness"], data["distance"], data["harness"] * data["distance"]])
    y, codes, zk, g = ps._informative(data["y"], data["template"], z)
    dummies = np.zeros((len(y), g))
    dummies[np.arange(len(y)), codes] = 1.0
    ref = sm.GLM(y, np.column_stack([dummies, zk]), family=sm.families.Binomial()).fit(
        cov_type="cluster", cov_kwds={"groups": codes, "use_correction": False})
    est, se, p = ps.fe_logit(data["y"], data["template"], z, engine=engine,
                             correction="clusters")
    assert est == pytest.approx(ref.params[-3:], rel=1e-7)
    assert se == pytest.approx(ref.bse[-3:] * np.sqrt(g / (g - 1)), rel=1e-7)
    assert p == pytest.approx(2 * special.ndtr(-np.abs(est / se)))
    # With 4 episodes per template, the default factor (dummies counted in K) is much larger.
    default = ps.fe_logit(data["y"], data["template"], z, engine=engine)
    assert (default[1] / se > 1.1).all()
    with pytest.raises(ValueError):
        ps.fe_logit(data["y"], data["template"], z, correction="nope")


def test_h2_glm_matches_statsmodels():
    y0, y1 = ps.simulate_h2(40, 0.08, np.random.default_rng(3))
    assert ps.h2_glm(y0, y1, "fast") == pytest.approx(ps.h2_glm(y0, y1, "statsmodels"), rel=1e-7)


def test_fe_logit_drops_uninformative_templates():
    rng = np.random.default_rng(0)
    groups = np.repeat(np.arange(6), 20)
    x = rng.random(120)
    y = (rng.random(120) < 0.5).astype(float)
    y[groups == 0] = 1.0  # all successes: no information under template fixed effects
    full = ps.fe_logit(y, groups, x[:, None])
    dropped = ps.fe_logit(y[groups != 0], groups[groups != 0], x[groups != 0][:, None])
    assert full[0] == pytest.approx(dropped[0])
    assert ps.fe_logit(np.ones(40), np.repeat([0, 1], 20), x[:40, None]) is None


def test_sec10_data_shape_and_targets():
    design = ps.Sec10Design("t", 4000, 5, 1)
    data = ps.simulate_sec10(design, 0.2, np.random.default_rng(1), calibration="marginal")
    assert len(data["y"]) == design.episodes == 4000 * 5 * 2
    far_ref = (data["harness"] == 0) & (data["distance"] == 1)
    far_aff = (data["harness"] == 1) & (data["distance"] == 1)
    near = data["distance"] == 0
    assert data["y"][near].mean() == pytest.approx(0.9, abs=0.01)
    assert data["y"][far_ref].mean() == pytest.approx(0.8, abs=0.015)
    assert data["y"][far_aff].mean() == pytest.approx(0.6, abs=0.015)


def test_run_sec10_is_seeded_and_complete():
    designs = ps.SEC10_DESIGNS[:1]
    a = ps.run_sec10(5, 11, designs=designs)
    b = ps.run_sec10(5, 11, designs=designs)
    assert a.equals(b)
    assert len(a) == 3 and a.rejection_rate.between(0, 1).all()
    assert a.loc[a.interaction_pp == 10, "plan_s10_low"].item() == 0.23


def test_bootstrap_ci():
    rng = np.random.default_rng(5)
    values = rng.normal(0.1, 0.3, 400)
    lo, hi = ps.percentile_ci(ps.cluster_bootstrap_means(values, rng, 4000), 0.90)
    se = values.std(ddof=1) / np.sqrt(400)
    assert lo < values.mean() < hi
    assert (hi - lo) / 2 == pytest.approx(1.645 * se, rel=0.1)


def test_h2_extremes():
    # A huge effect is always detected.
    big = ps.run_h2(10, 1, templates=(60,), boot=500, setup=ps.H2Setup(p_f0=0.5, bound=0.4))
    assert big.loc[big.true_effect_pp == 40, "P_superior_95"].item() == 1.0
    # With many templates and no true effect, the TOST declares equivalence...
    many = ps.run_h2(10, 1, templates=(2000,), boot=500)
    assert many.loc[many.true_effect_pp == 0, "P_tost_equivalent"].item() == 1.0
    # ...and when the true effect sits on the bound it rarely does (nominal size 5%).
    edge = ps.run_h2(200, 2, templates=(200,), boot=500)
    assert edge.loc[edge.true_effect_pp == 8, "P_tost_equivalent"].item() < 0.10


def test_h2_d11_options_leave_existing_columns_unchanged():
    base = ps.run_h2(20, 5, templates=(30, 60), boot=200)
    setup = ps.H2Setup(holm_one_sided_alpha=0.0125, observed_divisor=3)
    full = ps.run_h2(20, 5, templates=(30, 60), boot=200, setup=setup)
    assert full[base.columns].equals(base)
    assert list(full.T_o) == [10, 10, 20, 20]
    assert list(full.episodes_total) == [2 * (30 * 2 + 10 * 2)] * 2 + [2 * (60 * 2 + 20 * 2)] * 2
    # "supported" needs the bootstrap test AND a positive GLM estimate.
    assert (full.P_supported <= full.P_superior_holm_one_sided).all()
    for col in ("P_superior_holm_one_sided", "P_superior_glm_one_sided", "P_supported",
                "obs_P_point_within_bound"):
        assert full[col].between(0, 1).all()


def test_h2_one_sided_holm_and_observed_cells():
    setup = ps.H2Setup(p_f0=0.5, bound=0.4, holm_one_sided_alpha=0.0125, observed_divisor=3)
    big = ps.run_h2(10, 1, templates=(60,), boot=500, setup=setup)
    hit = big.loc[big.true_effect_pp == 40].iloc[0]
    assert hit.P_superior_holm_one_sided == 1.0 and hit.P_supported == 1.0
    null = big.loc[big.true_effect_pp == 0].iloc[0]
    assert null.P_superior_holm_one_sided <= 0.2
    # With 1000 observed templates and no true difference, the point estimate is within 3pp.
    many = ps.run_h2(5, 2, templates=(3000,), boot=100,
                     setup=ps.H2Setup(holm_one_sided_alpha=0.0125, observed_divisor=3))
    assert (many.T_o == 1000).all() and (many.obs_P_point_within_bound == 1.0).all()
    assert (many.obs_mean_ci90_halfwidth_pp < 3).all()


def test_main_h2_p0_list_and_d11_options(tmp_path):
    args = ["--part", "h2", "--reps", "2", "--boot", "50", "--h2-templates", "30",
            "--h2-p0", "0.6,0.8", "--holm-one-sided-alpha", "0.0125",
            "--h2-observed-divisor", "3", "--cluster-correction", "clusters",
            "--out-dir", str(tmp_path)]
    assert ps.main(args) == 0
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert [s["p_f0"] for s in meta["config"]["h2_setups"]] == [0.6, 0.8]
    assert meta["config"]["h2_setups"][0]["holm_one_sided_alpha"] == 0.0125
    t = pd.read_csv(tmp_path / "h2_sol_power.csv")
    assert sorted(t.p_F0.unique()) == [0.6, 0.8] and len(t) == 4 and (t.T_o == 10).all()


def test_main_writes_tables_and_meta(tmp_path):
    args = ["--reps", "2", "--boot", "50", "--h2-templates", "30", "--out-dir", str(tmp_path)]
    assert ps.main(args) == 0
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert meta["experiment"] == "power_sim" and meta["seeds"] == [ps.DEFAULT_SEED]
    assert sorted(meta["outputs"]) == ["h2_sol_power.csv", "sec10_power.csv"]


# --------------------------------------------------------------------------------------------
# Part 3: luna's H1 and H3
# --------------------------------------------------------------------------------------------
def _toy_luna():
    """4 templates with hand-checkable estimands (see test_luna_estimands_on_toy_data)."""
    return {k: np.array(v, dtype=float) for k, v in {
        "f0_onr": [1, 1, 1, 0], "w0_onr": [0, 0, 1, 0], "f0_or": [1, 1, 1, 1],
        "w0_or": [1, 1, 1, 0], "f0_dnr": [1, 0, 1, 1], "st_onr": [1, 1, 0, 1],
        "st_dnr": [1, 1, 1, 1]}.items()}


def test_luna_estimands_on_toy_data():
    y = _toy_luna()
    est = ps.luna_estimates(y)
    # Penalty_NR = 0.75 - 0.25, Penalty_R = 1.0 - 0.75
    assert est["penalty_nr"] == pytest.approx(0.50)
    assert est["penalty_r"] == pytest.approx(0.25)
    assert est["delta_h1"] == pytest.approx(0.25)
    # single-turn pooled 7/8, F-0 pooled 6/8 over the 2 NR-far cells
    assert est["delta_h3"] == pytest.approx(0.125)
    vals = ps.luna_per_template(y)
    assert vals.dtype.kind == "i"
    assert vals[:, 0].tolist() == [1, 1, 0, -1] and vals[:, 1].tolist() == [0, 1, -1, 1]
    assert vals[:, 0].mean() == pytest.approx(est["delta_h1"])
    assert vals[:, 1].mean() / 2 == pytest.approx(est["delta_h3"])


@pytest.mark.parametrize("setup", [ps.LUNA_PRIMARY, ps.LUNA_PESSIMISTIC,
                                   ps.LunaSetup(r_shift=0.02, delta_h3=0.03)],
                         ids=["primary", "pessimistic", "r_shift"])
def test_luna_levels_give_the_target_deltas_exactly(setup):
    lv = setup.levels()
    delta_h1 = (lv["f0_onr"] - lv["w0_onr"]) - (lv["f0_or"] - lv["w0_or"])
    delta_h3 = (lv["st_onr"] + lv["st_dnr"] - lv["f0_onr"] - lv["f0_dnr"]) / 2
    assert delta_h1 == pytest.approx(setup.delta_h1, abs=1e-12)
    assert delta_h3 == pytest.approx(setup.delta_h3, abs=1e-12)
    # Penalty_NR is fixed by the design (W-0 at the no-memory level on NR)
    assert lv["w0_onr"] == setup.p_w0_nr
    assert lv["w0_or"] == pytest.approx(setup.p_w0_nr + setup.delta_h1 + setup.r_shift)
    with pytest.raises(ValueError):
        ps.LunaSetup(p_f0_obs=0.99, r_shift=0.02).levels()


@pytest.mark.parametrize("setup", [ps.LUNA_PRIMARY, ps.LUNA_PESSIMISTIC],
                         ids=["primary", "pessimistic"])
def test_luna_simulation_hits_the_population_targets(setup):
    y = ps.simulate_luna(60_000, np.random.default_rng(2), setup)
    for cell, p in setup.levels().items():
        assert y[cell].mean() == pytest.approx(p, abs=0.008), cell
    est = ps.luna_estimates(y)
    assert est["delta_h1"] == pytest.approx(0.10, abs=0.01)
    assert est["delta_h3"] == pytest.approx(0.0, abs=0.006)


def test_luna_simulation_is_seeded():
    a = ps.simulate_luna(300, np.random.default_rng(4))
    b = ps.simulate_luna(300, np.random.default_rng(4))
    assert all((a[k] == b[k]).all() for k in ps.LUNA_CELLS)
    assert a["f0_onr"].shape == (300,) and set(np.unique(a["w0_or"])) <= {0.0, 1.0}
    # a scenario with SD 0 draws the same random numbers (the SD only scales them)
    c = ps.simulate_luna(300, np.random.default_rng(4), ps.LUNA_PESSIMISTIC)
    assert c["f0_onr"].shape == (300,)


def test_category_bootstrap_matches_index_bootstrap():
    rng = np.random.default_rng(9)
    vals = np.column_stack([rng.integers(-2, 3, 60), rng.integers(-2, 3, 60)])
    fast = ps.category_bootstrap_sums(vals, np.random.default_rng(1), 100_000)
    idx = np.random.default_rng(2).integers(0, 60, size=(100_000, 60))
    slow = vals[idx].sum(axis=1)
    assert fast.shape == slow.shape == (100_000, 2)
    assert fast.mean(axis=0) == pytest.approx(vals.sum(axis=0), abs=0.1)
    assert fast.mean(axis=0) == pytest.approx(slow.mean(axis=0), abs=0.1)
    assert fast.std(axis=0) == pytest.approx(slow.std(axis=0), rel=0.02)
    for q in (0.025, 0.05, 0.5, 0.95, 0.975):
        assert np.quantile(fast, q, axis=0) == pytest.approx(np.quantile(slow, q, axis=0),
                                                             abs=1.0)


def test_analyse_luna_counts_ties_on_the_null_side():
    # 20 templates: every cell succeeds, except template 0, where F-0 fails on all 3 of its
    # cells, W-0 fails on both and the single-turn control succeeds. Delta_H1 is 0 in every
    # resample (p1 = 1). Delta_H3* = N / 20 with N ~ Binomial(20, 1/20), the copies of
    # template 0, so P(Delta_H3* >= 5pp) = P(N >= 1) = 1 - 0.95^20.
    y = {k: np.ones(20) for k in ps.LUNA_CELLS}
    for k in ("f0_onr", "f0_or", "f0_dnr", "w0_onr", "w0_or"):
        y[k][0] = 0.0
    r = ps.analyse_luna(y, np.random.default_rng(3), boot=20_000)
    assert r["delta_h1"] == 0 and r["delta_h3"] == pytest.approx(0.05)
    assert r["p1"] == 1.0 and not (r["h1_worst"] or r["h1_holm"] or r["h1_unadj"])
    assert r["p3"] == pytest.approx(1 - 0.95 ** 20, abs=0.01)
    assert not r["h3_unadj"] and not r["h3_ci90_within"]


def test_holm_reject():
    assert ps.holm_reject([0.01, 0.04]).tolist() == [True, True]
    assert ps.holm_reject([0.04, 0.01]).tolist() == [True, True]
    assert ps.holm_reject([0.02, 0.06]).tolist() == [True, False]
    assert ps.holm_reject([0.03, 0.04]).tolist() == [False, False]
    assert ps.holm_reject([0.025, 0.05]).tolist() == [True, True]  # at the levels: rejected
    # family of 4 with 2 members counted as not rejected: steps 0.0125, then 0.05 / 3
    assert ps.holm_reject([0.012, 0.016, 1, 1]).tolist() == [True, True, False, False]
    assert ps.holm_reject([0.013, 0.001, 1, 1]).tolist() == [True, True, False, False]
    assert ps.holm_reject([0.013, 0.02, 1, 1]).tolist() == [False, False, False, False]


def _h1_design(y):
    t = len(y["f0_onr"])
    yy = np.concatenate([y["f0_onr"], y["w0_onr"], y["f0_or"], y["w0_or"]])
    w, r = np.repeat([0.0, 1.0, 0.0, 1.0], t), np.repeat([0.0, 0.0, 1.0, 1.0], t)
    return ps._informative(yy, np.tile(np.arange(t), 4), np.column_stack([w, r, w * r]))


def test_fe_logit_mle_matches_statsmodels_and_its_signs_under_separation():
    # Away from the ceiling nothing diverges: the two routes give the same estimates.
    mild = ps.LunaSetup(p_f0_obs=0.7, p_f0_der=0.7, p_w0_nr=0.3)
    y = ps.simulate_luna(150, np.random.default_rng(5), mild)
    yk, codes, z, _ = _h1_design(y)
    fast = ps._fe_logit_mle(yk, codes, z, "fast")
    ref = ps._fe_logit_mle(yk, codes, z, "statsmodels")
    assert fast[1] == pytest.approx(ref[1], rel=1e-6, abs=1e-8)
    assert ps.h1_glm(y) == pytest.approx(ref[1][-1], rel=1e-6)
    # At the primary levels the W-0 effect often runs off (quasi-separation); the interaction's
    # sign still agrees with statsmodels whenever it is not an exact 0.
    rng, separated = np.random.default_rng(6), 0
    for _ in range(40):
        yk, codes, z, _ = _h1_design(ps.simulate_luna(50, rng))
        fast = ps._fe_logit_mle(yk, codes, z, "fast")
        ref = ps._fe_logit_mle(yk, codes, z, "statsmodels")
        separated += abs(ref[1][0]) > 15
        if abs(ref[1][-1]) > 1e-6:
            assert np.sign(fast[1][-1]) == np.sign(ref[1][-1])
    assert separated >= 5


def test_h1_glm_interaction_has_the_sign_of_delta_h1():
    # The FE logit's interaction is the logit-scale difference of penalties. With W-0's R level
    # above its NR level and F-0 equal on R and NR, it is positive whatever the scale.
    setup = ps.LunaSetup(p_f0_obs=0.7, p_f0_der=0.7, p_w0_nr=0.3, sd=0.0)
    lv = setup.levels()
    target = special.logit(lv["w0_or"]) - special.logit(lv["w0_onr"])
    est = ps.h1_glm(ps.simulate_luna(20_000, np.random.default_rng(7), setup))
    # with 4 outcomes per template the FE logit overstates logit effects (incidental
    # parameters), so only the sign and the rough size are checked
    assert est > 0 and target > 0 and 0.5 * target < est < 3 * target


def test_h3_glm_ame_matches_a_statsmodels_computation():
    setup = ps.LunaSetup(p_f0_obs=0.75, p_f0_der=0.65, p_w0_nr=0.3, delta_h3=0.05)
    y = ps.simulate_luna(120, np.random.default_rng(8), setup)
    t = 120
    yy = np.concatenate([y["f0_onr"], y["f0_dnr"], y["st_onr"], y["st_dnr"]])
    der, arm = np.repeat([0.0, 1.0, 0.0, 1.0], t), np.repeat([0.0, 0.0, 1.0, 1.0], t)
    yk, codes, z, g = ps._informative(yy, np.tile(np.arange(t), 4),
                                      np.column_stack([der, arm]))
    dummies = np.zeros((len(yk), g))
    dummies[np.arange(len(yk)), codes] = 1.0
    res = sm.GLM(yk, np.column_stack([dummies, z]), family=sm.families.Binomial()).fit()
    alpha, gamma, beta = res.params[:g], res.params[g], res.params[g + 1]
    ame = sum(special.expit(a + gamma * c + beta) - special.expit(a + gamma * c)
              for a in alpha for c in (0, 1)) / (2 * t)  # no-variation templates add 0
    assert ps.h3_glm_ame(y) == pytest.approx(ame, rel=1e-6)
    assert ps.h3_glm_ame({k: np.ones(30) for k in ps.LUNA_CELLS}) == 0.0


def test_run_luna_power_grows_with_T_and_readings_nest():
    df = ps.run_luna(150, 3, templates=(50, 100, 200), boot=2000)
    for col in ("P_h1_worst_step", "P_h3_worst_step", "P_h1_unadjusted", "P_h3_unadjusted"):
        assert (np.diff(df[col]) >= -0.02).all(), col
        assert df[col].iloc[-1] - df[col].iloc[0] >= 0.15, col
    # per data set: holm4 rejection => worst-step rejection => Holm rejection => unadjusted
    for h in ("h1", "h3"):
        assert (df[f"P_{h}_holm4"] <= df[f"P_{h}_worst_step"]).all()
        assert (df[f"P_{h}_worst_step"] <= df[f"P_{h}_holm"]).all()
        assert (df[f"P_{h}_holm"] <= df[f"P_{h}_unadjusted"]).all()
        assert (df[f"P_{h}_supported_worst_step"] <= df[f"P_{h}_worst_step"]).all()
    assert df.mean_delta_h1_pp.between(7, 13).all() and df.mean_delta_h3_pp.abs().max() < 2
    assert df.equals(ps.run_luna(150, 3, templates=(50, 100, 200), boot=2000))


def test_run_luna_size_at_the_null_boundaries():
    null = ps.luna_sensitivity_setups(ps.LUNA_PRIMARY, [])[-1][1]
    assert null.levels()["st_onr"] == ps.LUNA_PRIMARY.p_f0_obs
    row = ps.run_luna(300, 4, templates=(100,), boot=2000, setup=null).iloc[0]
    assert row.P_h1_worst_step <= 0.06 and row.P_h3_worst_step <= 0.06
    assert row.P_h1_unadjusted <= 0.10 and row.P_h3_unadjusted <= 0.10


def test_luna_decision_picks_the_smallest_T_or_the_cap():
    rows = []
    for name, p1, p3 in (("a", (0.5, 0.79, 0.81, 0.9), (0.85, 0.9, 0.95, 0.99)),
                         ("b", (0.3, 0.4, 0.5, 0.6), (0.9, 0.9, 0.9, 0.9))):
        for t, x1, x3 in zip((170, 180, 190, 200), p1, p3, strict=True):
            row = {"scenario": name, "templates": t}
            for c1, c3 in ps.LUNA_READINGS.values():
                row.update({c1: x1, c3: x3})
            rows.append(row)
    d = ps.luna_decision(pd.DataFrame(rows))
    first = next(iter(ps.LUNA_READINGS))
    a = d[(d.scenario == "a") & (d.reading == first)].iloc[0]
    assert (a.T_h1, a.T_h3, a.T_both, a.T_set, a.T_set_by) == (190, 170, 190, 190, "rule")
    assert a.all_larger_T_meet
    b = d[(d.scenario == "b") & (d.reading == first)].iloc[0]
    assert pd.isna(b.T_both) and b.T_set == 200 and b.T_set_by.startswith("cap")
    assert b.power_h1_at_T_set == 0.6 and b.power_h3_at_T_set == 0.9


def test_luna_sensitivity_setups():
    out = ps.luna_sensitivity_setups(ps.LUNA_PRIMARY, [ps.LUNA_PESSIMISTIC], (0.0, 1.5))
    labels = [label for label, _ in out]
    assert len(out) == 4 + 1 + 1  # 4 swapped fields, sd 1.5 (sd 0 is already a swap), null
    assert [s.sd for _, s in out].count(0.0) == 1
    assert "size" in labels[-1]
    null = out[-1][1]
    assert null.delta_h1 == 0 and null.delta_h3 == null.h3_margin


def _write_episodes(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def test_validity_template_sd(tmp_path):
    rng = np.random.default_rng(10)
    a = ps.intercept_for(0.3, 1.0)
    recs = []
    for t in range(400):
        u = rng.normal(0, 1.0)
        for _ in range(8):
            recs.append({"variant": "withheld", "template_id": f"v{t}",
                         "need_correct": bool(rng.random() < special.expit(a + u)),
                         "excluded": False})
            recs.append({"variant": "restated", "template_id": f"v{t}", "need_correct": True,
                         "excluded": False})
    recs.append({"variant": "withheld", "template_id": "x", "need_correct": True,
                 "excluded": True})  # excluded episodes are left out
    _write_episodes(tmp_path / "episodes.jsonl", recs)
    df = ps.validity_template_sd([tmp_path / "episodes.jsonl"], step=0.02).set_index("variant")
    restated = df.loc["restated"]
    assert np.isnan(restated.sd_hat) and "not identified" in restated.note
    w = df.loc["withheld"]
    assert w.episodes == 3200 and abs(w.sd_hat - 1.0) < 0.25
    assert w.sd_ci95_low <= w.sd_hat <= w.sd_ci95_high and w.lr_vs_sd0 > 10
    assert w.sd_ci95_low <= 1.0 <= w.sd_ci95_high  # covers the truth (this seed)


def test_validity_template_sd_on_lunas_committed_runs():
    paths = sorted(ps.REPO_ROOT.glob(ps.LUNA_VALIDITY_GLOB))
    if not paths:
        pytest.skip("luna's validity runs are not in this checkout")
    df = ps.validity_template_sd(paths).set_index("variant")
    assert (df.loc["restated", ["episodes", "successes"]] == [160, 160]).all()
    assert (df.loc["withheld", ["episodes", "successes"]] == [160, 19]).all()
    assert df.loc["withheld", "sd_hat"] == pytest.approx(0.92, abs=0.02)


def test_main_luna_writes_tables_meta_and_summary(tmp_path):
    args = ["--part", "luna", "--reps", "3", "--luna-boot", "200", "--luna-templates", "50,60",
            "--luna-sensitivity-templates", "50", "--out-dir", str(tmp_path)]
    assert ps.main(args) == 0
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert sorted(meta["outputs"]) == sorted(
        ["luna_power.csv", "luna_decision.csv", "luna_normal_check.csv", "luna_sensitivity.csv",
         "luna_validity_sd.csv", "summary.md"])
    assert [s["name"] for s in meta["config"]["luna_setups"]] == ["primary", "pessimistic"]
    assert meta["config"]["luna_setups"][1]["sd"] == 0.0
    power = pd.read_csv(tmp_path / "luna_power.csv")
    assert len(power) == 4 and set(power.scenario) == {"primary", "pessimistic"}
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    for heading in ("## Assumptions", "## Result: the template count", "## Power by T",
                    "## Cross-check: normal approximation", "## What this does not show"):
        assert heading in summary


def test_luna_cli_lists_must_match_the_scenarios():
    with pytest.raises(SystemExit):
        ps.main(["--part", "luna", "--luna-names", "a,b,c", "--no-write"])
    args = ["--part", "luna", "--luna-names", "only", "--luna-p-f0-obs", "0.9",
            "--luna-p-f0-der", "0.8", "--luna-p-w0-nr", "0.1", "--luna-template-sd", "0.5",
            "--reps", "2", "--luna-boot", "100", "--luna-templates", "50",
            "--luna-sensitivity-templates", "", "--luna-validity-glob", "", "--no-write"]
    assert ps.main(args) == 0


def test_h2_holm_steps_option(tmp_path):
    args = ["--part", "h2", "--reps", "2", "--boot", "50", "--h2-templates", "30",
            "--h2-holm-steps", "2", "--out-dir", str(tmp_path)]
    assert ps.main(args) == 0
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert meta["config"]["h2_setups"][0]["holm_steps"] == 2
    assert ps.H2Setup().holm_steps == 3  # the default is unchanged for part 2


def test_luna_normal_power_closed_form_and_agreement_with_the_simulation():
    # With SD 0 the cells are independent: the variance is a sum of Bernoulli variances.
    setup = ps.replace(ps.LUNA_PRIMARY, sd=0.0)
    lv = setup.levels()
    v1 = sum(lv[k] * (1 - lv[k]) for k in ("f0_onr", "w0_onr", "f0_or", "w0_or"))
    v3 = sum(lv[k] * (1 - lv[k]) for k in ("st_onr", "f0_onr", "st_dnr", "f0_dnr")) / 4
    z = special.ndtri(1 - 0.025)
    h1, h3 = ps.luna_normal_power(setup, 120, 0.025)
    assert h1 == pytest.approx(special.ndtr(0.10 / np.sqrt(v1 / 120) - z), rel=1e-9)
    assert h3 == pytest.approx(special.ndtr(0.05 / np.sqrt(v3 / 120) - z), rel=1e-9)
    # more templates, more power; a looser level, more power
    assert ps.luna_normal_power(ps.LUNA_PRIMARY, 200, 0.025)[0] > ps.luna_normal_power(
        ps.LUNA_PRIMARY, 100, 0.025)[0]
    assert ps.luna_normal_power(ps.LUNA_PRIMARY, 100, 0.05)[1] > ps.luna_normal_power(
        ps.LUNA_PRIMARY, 100, 0.025)[1]
    # close to the simulated test-only power
    sim = ps.run_luna(400, 11, templates=(150,), boot=2000).iloc[0]
    n1, n3 = ps.luna_normal_power(ps.LUNA_PRIMARY, 150, 0.025)
    assert sim.P_h1_worst_step == pytest.approx(n1, abs=0.07)
    assert sim.P_h3_worst_step == pytest.approx(n3, abs=0.07)
    check = ps.luna_normal_check([ps.LUNA_PRIMARY], (150,))
    assert check.normal_h1_worst_step.iloc[0] == pytest.approx(n1)
    t_unc = int(check.normal_T_both_uncapped.iloc[0])
    assert t_unc % 10 == 0 and min(ps.luna_normal_power(ps.LUNA_PRIMARY, t_unc, 0.025)) >= 0.8
    assert min(ps.luna_normal_power(ps.LUNA_PRIMARY, t_unc - 10, 0.025)) < 0.8
