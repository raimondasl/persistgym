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
