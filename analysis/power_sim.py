"""Power simulation for PLAN.md §10 (rewritten from its description), sol's H2 and luna's H1/H3.

Part 1 (``sec10``) re-runs the §10 table. Each template has a random intercept with SD 1.0 on
the logit scale. Under the reference harness, success falls linearly from 0.9 (nearest distance
level) to 0.8 (farthest); under the other harness it falls by an extra 10 or 20pp at the far end
(the harness x distance interaction). Each template is crossed with both harnesses, every
distance level and ``seeds`` repeats. The test is the harness x distance coefficient of a
logistic GLM with template fixed effects and template-clustered (cluster-robust) SEs, two-sided
at alpha 0.05, counted as a detection only when the estimate has the true sign. Templates with
no outcome variation carry no information under template fixed effects and are dropped before
fitting (the FE estimates of the other coefficients are unchanged by this).

Part 2 (``h2``) is the sol H2 case of amendment §16.5: F-r vs F-0, paired within template, on
the 2 derived-far cells per template (recoverable and not), one episode per template x cell x
arm, success 0.8 under F-0 (the far level of §10), template SD 1.0. The estimand is the
probability-scale difference of cell means (PLAN §10). The CI comes from a template-cluster
percentile bootstrap. Reported, for 30/40/60/80 templates:
- TOST equivalence at +/-8pp (the 90% CI lies inside the bounds; PLAN §4 H2): its power when the
  true effect is 0, and its false-equivalence rate when the true effect is +8pp;
- the 8pp superiority contrast (95% CI above 0, and 98.3% CI for the worst Holm step over H1-H3):
  its power when the true effect is +8pp, and its false-positive rate when it is 0;
- the same superiority test in the confirmatory model (logistic GLM, template and cell fixed
  effects, cluster-robust SEs).

Two options serve decision D11 option A (sol on derived-far and observed-far cells only) and
D26 (a Holm family of 4 one-sided bootstrap tests):
- ``--holm-one-sided-alpha A`` adds the one-sided percentile-bootstrap test at the worst Holm
  step (D26: 0.05 / 4 = 0.0125): p = the share of resamples <= 0, reject iff p <= A. Also
  reported: the GLM's one-sided test at A, and "supported" (the bootstrap test rejects and the
  GLM estimate is positive, D26).
- ``--h2-observed-divisor K`` adds the observed-far cells on T_o = ceil(T_d / K) templates
  (2 cells, F-r vs F-0, true difference 0, success p_F0). Reported marginally: the chance that
  the point estimate of the observed difference is under 3pp (PLAN §4 H2's "less than 3pp
  difference on observed facts") and its mean 90% CI half-width. These draws use their own
  random stream, so they leave the derived-far columns unchanged.
``--h2-p0`` takes a comma-separated list; every value reuses the same seed (common random
numbers across p_F0).

The probability targets are converted to logits either conditionally (the target holds for a
template with intercept 0) or marginally (the target is the population-average success). Part 1
runs both by default (``--sec10-calibration``); part 2 always uses the marginal calibration,
because its estimand is on the probability scale.

``--h2-holm-steps`` sets the Holm family size behind part 2's two-sided "P_superior_holm"
column (default 3, as in its committed runs).

Part 3 (``luna``) sizes luna's template count T by PREREG §4.2's frozen rule: the smallest
multiple of 10 with simulated power >= 0.80 both for H1 at Delta_H1 = 10pp and for H3 at a true
Delta_H3 = 0, capped at 200 (R6 change 6). H1 and H3 are simulated together, because F-0 on
observed-NR-far enters both and Holm runs over both (a family of 2, decided 2026-10-06, R6
change 9). Per template, one repeat-0 outcome in each of 7 cells (``LUNA_CELLS``), with one
template random intercept shared by all 7. Each simulated sweep is analysed as §9.1 and §9.4
will analyse the real one: template-cluster percentile bootstrap with 10,000 resamples (drawn
as category counts, which is exact and fast), one-sided bootstrap p-values, Holm, and
"supported" = the test rejects and the model check agrees. The decision reading is
P(supported) at the worst Holm step (one-sided 0.025), the most conservative; the real Holm
procedure, the unadjusted level and the family of 4 are reported next to it. ``LunaSetup``
explains how the penalties are set so that Delta_H1 is exactly 10pp. The run also writes the
template SD measured in luna's validity runs, a one-at-a-time sensitivity table, a
normal-approximation cross-check (``luna_normal_power``, which also gives the T the rule would
need without the cap), the cost of each T from the committed forecast, and ``summary.md``.
``--part all`` still runs parts 1 and 2 only.

Cluster-robust small-sample factor (``--cluster-correction``). The default, ``statsmodels``, is
statsmodels' G/(G-1) * (N-1)/(N-K) with the template dummies counted in K. With template fixed
effects nested in the clusters this is conservative when templates have few observations: about
+16% on the SE with 4 episodes per template (the H2 GLM and the 100 x 2 x 1 luna design), +7% with
8, +3% with 20, and the size falls below nominal. ``clusters`` uses G/(G-1) only. Which one the
confirmatory model uses is a PREREG choice; the bootstrap contrasts do not depend on it.

Run: ``uv run python -m analysis.power_sim [--reps 200] [--seed 20260930] [--no-write]``;
part 3: ``uv run python -m analysis.power_sim --part luna --reps 2000``
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import warnings
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import optimize, special
from statsmodels.tools import sm_exceptions

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SEED = 20260930
TEMPLATE_SD = 1.0
ALPHA = 0.05
CORRECTIONS = ("statsmodels", "clusters")

# PLAN.md §10 table, for comparison only (the card's row was reported as one range).
SEC10_REFERENCE = {
    ("60 x 5 x 2", 0.10): (0.23, 0.23), ("60 x 5 x 2", 0.20): (0.57, 0.57),
    ("120 x 5 x 2", 0.10): (0.39, 0.39), ("120 x 5 x 2", 0.20): (0.88, 0.88),
    ("120 x 2 x 2", 0.20): (0.77, 0.77),
    ("card: 30 x 5 x 2", 0.10): (0.16, 0.31), ("card: 30 x 5 x 2", 0.20): (0.16, 0.31),
}


@dataclass(frozen=True)
class Sec10Design:
    label: str
    templates: int
    distances: int
    seeds: int

    @property
    def episodes(self) -> int:  # per model per harness pair
        return self.templates * self.distances * self.seeds * 2


SEC10_DESIGNS = (
    Sec10Design("60 x 5 x 2", 60, 5, 2),
    Sec10Design("120 x 5 x 2", 120, 5, 2),
    Sec10Design("120 x 2 x 2", 120, 2, 2),
    Sec10Design("card: 30 x 5 x 2", 30, 5, 2),
    Sec10Design("luna plan: 100 x 2 x 1", 100, 2, 1),  # added: PLAN §5/§10 design
)


# --------------------------------------------------------------------------------------------
# Logit-scale calibration
# --------------------------------------------------------------------------------------------
_GH_X, _GH_W = np.polynomial.hermite_e.hermegauss(60)
_GH_W = _GH_W / _GH_W.sum()


def marginal_success(intercept: float, sd: float = TEMPLATE_SD) -> float:
    """Population-average success E[expit(intercept + u)], u ~ N(0, sd^2)."""
    return float(np.sum(_GH_W * special.expit(intercept + sd * _GH_X)))


@lru_cache(maxsize=4096)
def intercept_for(p: float, sd: float = TEMPLATE_SD, calibration: str = "marginal") -> float:
    """Logit intercept giving success p: for a median template ('conditional') or on average
    over templates ('marginal')."""
    if not 0 < p < 1:
        raise ValueError(f"success must be in (0, 1), got {p}")
    if calibration == "conditional" or sd == 0:
        return float(special.logit(p))
    if calibration != "marginal":
        raise ValueError(f"unknown calibration {calibration!r}")
    return float(optimize.brentq(lambda a: marginal_success(a, sd) - p, -30, 30, xtol=1e-12))


# --------------------------------------------------------------------------------------------
# Template fixed-effects logistic GLM with cluster-robust SEs
# --------------------------------------------------------------------------------------------
FitResult = tuple[np.ndarray, np.ndarray, np.ndarray]  # slope estimates, SEs, two-sided p


def _informative(y: np.ndarray, groups: np.ndarray, slopes: np.ndarray):
    """Drop templates whose outcomes are all 0 or all 1; return y, codes 0..G-1, slopes."""
    y = np.asarray(y, dtype=float)
    codes, uniq = pd.factorize(groups)
    sums = np.bincount(codes, weights=y, minlength=len(uniq))
    counts = np.bincount(codes, minlength=len(uniq))
    informative = (sums > 0) & (sums < counts)
    keep = informative[codes]
    codes, _ = pd.factorize(codes[keep])
    return y[keep], codes, np.asarray(slopes, dtype=float)[keep], int(informative.sum())


def _fe_logit_statsmodels(y, codes, z) -> FitResult:
    n_groups = codes.max() + 1
    dummies = np.zeros((len(y), n_groups))
    dummies[np.arange(len(y)), codes] = 1.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = sm.GLM(y, np.column_stack([dummies, z]), family=sm.families.Binomial()).fit(
            cov_type="cluster", cov_kwds={"groups": codes})
    k = z.shape[1]
    return (np.asarray(res.params[-k:]), np.asarray(res.bse[-k:]),
            np.asarray(res.pvalues[-k:]))


def _fe_blocks(y, codes, z, alpha, beta):
    """Residuals and Hessian blocks of the FE logit at (alpha, beta): the intercept block's
    diagonal, the intercept x slope block, and the Schur complement of the intercept block."""
    k, g = z.shape[1], len(alpha)
    mu = special.expit(alpha[codes] + z @ beta)
    w, r = mu * (1 - mu), y - mu
    h_aa = np.bincount(codes, weights=w, minlength=g)
    h_ab = np.column_stack([np.bincount(codes, weights=w * z[:, j], minlength=g)
                            for j in range(k)])
    h_bb = (z * w[:, None]).T @ z
    schur = h_bb - h_ab.T @ (h_ab / h_aa[:, None])
    return r, h_aa, h_ab, schur


def _deviance(y, eta) -> float:
    """Binomial deviance of 0/1 outcomes at linear predictor eta (log-expit, no overflow)."""
    return 2.0 * float(np.sum(y * np.logaddexp(0.0, -eta) + (1 - y) * np.logaddexp(0.0, eta)))


def _fe_logit_newton(y, codes, z, max_iter: int = 100, tol: float = 1e-10,
                     dev_tol: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """MLE (template intercepts, slopes) of the FE logit by Newton steps, with the template
    intercepts profiled out through a Schur complement.

    Converged when no parameter moves by tol. With ``dev_tol`` it also stops when the deviance
    changes by at most dev_tol, statsmodels' IRLS rule (tol 1e-8): under quasi-separation the
    parameters never settle, but the deviance does, and the coefficients returned are large
    and finite, as statsmodels returns them."""
    k = z.shape[1]
    g = codes.max() + 1
    counts = np.bincount(codes, minlength=g)
    ybar = np.clip(np.bincount(codes, weights=y, minlength=g) / counts, 1e-3, 1 - 1e-3)
    alpha, beta = special.logit(ybar), np.zeros(k)
    dev = _deviance(y, alpha[codes]) if dev_tol is not None else None
    for _ in range(max_iter):
        r, h_aa, h_ab, schur = _fe_blocks(y, codes, z, alpha, beta)
        g_a = np.bincount(codes, weights=r, minlength=g)
        d_b = np.linalg.solve(schur, z.T @ r - h_ab.T @ (g_a / h_aa))
        d_a = (g_a - h_ab @ d_b) / h_aa
        alpha, beta = alpha + d_a, beta + d_b
        if max(np.abs(d_a).max(), np.abs(d_b).max()) < tol:
            return alpha, beta
        if dev_tol is not None:
            dev, previous = _deviance(y, alpha[codes] + z @ beta), dev
            if abs(dev - previous) <= dev_tol:
                return alpha, beta
    raise FloatingPointError("FE logit did not converge")


def _fe_logit_fast(y, codes, z, max_iter: int = 100, tol: float = 1e-10) -> FitResult:
    """The same model as _fe_logit_statsmodels, by Newton steps with the template intercepts
    profiled out through a Schur complement. Cluster-robust sandwich with statsmodels' default
    small-sample factor G/(G-1) * (N-1)/(N-K) and normal p-values.

    At the MLE every template's intercept score is zero, so the cluster scores only have slope
    components and the slope block of the sandwich is S^-1 B S^-1, with S the Schur complement
    of the intercept block in the Hessian.
    """
    n, k = z.shape
    alpha, beta = _fe_logit_newton(y, codes, z, max_iter, tol)
    g = len(alpha)
    r, _, _, schur = _fe_blocks(y, codes, z, alpha, beta)
    scores = np.column_stack([np.bincount(codes, weights=r * z[:, j], minlength=g)
                              for j in range(k)])
    s_inv = np.linalg.inv(schur)
    cov = s_inv @ (scores.T @ scores) @ s_inv
    cov *= g / (g - 1) * (n - 1) / (n - (g + k))
    se = np.sqrt(np.diag(cov))
    return beta, se, 2 * special.ndtr(-np.abs(beta / se))


def fe_logit(y: np.ndarray, groups: np.ndarray, slopes: np.ndarray,
             engine: str = "fast", correction: str = "statsmodels") -> FitResult | None:
    """Logistic GLM y ~ template fixed effects + slopes, cluster-robust SEs by template.

    Templates whose outcomes are all 0 or all 1 are dropped first: their fixed effects diverge
    and they carry no information about the slopes. Returns None when the fit fails.
    ``correction`` picks the small-sample factor (module docstring): 'statsmodels' (G/(G-1) *
    (N-1)/(N-K), template dummies in K) or 'clusters' (G/(G-1) only).
    """
    if correction not in CORRECTIONS:
        raise ValueError(f"unknown cluster correction {correction!r}")
    y, codes, z, n_groups = _informative(y, groups, slopes)
    if n_groups < 2 or len(y) <= n_groups + z.shape[1]:
        return None
    fit = _fe_logit_fast if engine == "fast" else _fe_logit_statsmodels
    try:
        est, se, p = fit(y, codes, z)
    except (np.linalg.LinAlgError, ValueError, FloatingPointError):
        return None
    if correction == "clusters":
        n, k = len(y), z.shape[1]
        se = se * np.sqrt((n - (n_groups + k)) / (n - 1))
        p = 2 * special.ndtr(-np.abs(est / se))
    if not (np.isfinite(est).all() and np.isfinite(se).all() and np.isfinite(p).all()):
        return None
    return est, se, p


def fe_logit_last_coef(y: np.ndarray, groups: np.ndarray, slopes: np.ndarray,
                       engine: str = "fast", correction: str = "statsmodels"
                       ) -> tuple[float, float, float] | None:
    """(estimate, SE, two-sided p) of the last slope column, or None if the fit fails."""
    fit = fe_logit(y, groups, slopes, engine, correction)
    if fit is None:
        return None
    est, se, p = fit
    return float(est[-1]), float(se[-1]), float(p[-1])


# --------------------------------------------------------------------------------------------
# Part 1: PLAN §10 harness x distance interaction
# --------------------------------------------------------------------------------------------
def simulate_sec10(design: Sec10Design, effect: float, rng: np.random.Generator, *,
                   p_near: float = 0.9, p_far: float = 0.8, sd: float = TEMPLATE_SD,
                   calibration: str = "conditional") -> dict[str, np.ndarray]:
    """One data set: templates x {reference, affected harness} x distance levels x seeds."""
    t, d, s = design.templates, design.distances, design.seeds
    x = np.linspace(0.0, 1.0, d)
    p_ref = p_near + (p_far - p_near) * x
    p_aff = p_ref - effect * x
    eta = np.array([[intercept_for(p, sd, calibration) for p in row] for row in (p_ref, p_aff)])
    u = rng.normal(0.0, sd, t)
    shape = (t, 2, d, s)  # template, harness, distance, seed
    lin = np.broadcast_to(u[:, None, None, None] + eta[None, :, :, None], shape)
    y = rng.random(shape) < special.expit(lin)
    tt, hh, dd, _ = np.meshgrid(np.arange(t), [0.0, 1.0], x, np.arange(s), indexing="ij")
    return {"y": y.ravel().astype(float), "template": tt.ravel(), "harness": hh.ravel(),
            "distance": dd.ravel()}


def fit_sec10(data: dict[str, np.ndarray], engine: str = "fast",
              correction: str = "statsmodels") -> tuple[float, float, float] | None:
    h, x = data["harness"], data["distance"]
    return fe_logit_last_coef(data["y"], data["template"], np.column_stack([h, x, h * x]),
                              engine, correction)


def run_sec10(reps: int, seed: int, *, effects=(0.0, 0.10, 0.20),
              calibration: str = "conditional", engine: str = "fast",
              correction: str = "statsmodels",
              designs: tuple[Sec10Design, ...] = SEC10_DESIGNS) -> pd.DataFrame:
    rows = []
    seqs = np.random.SeedSequence([seed, 10]).spawn(len(designs) * len(effects))
    for i, (design, effect) in enumerate((d, e) for d in designs for e in effects):
        rng = np.random.default_rng(seqs[i])
        hits = fails = 0
        for _ in range(reps):
            data = simulate_sec10(design, effect, rng, calibration=calibration)
            fit = fit_sec10(data, engine, correction)
            if fit is None:
                fails += 1
                continue
            est, _, p = fit
            if p < ALPHA and (effect == 0 or np.sign(est) == -np.sign(effect)):
                hits += 1
        ref = SEC10_REFERENCE.get((design.label, round(effect, 2)))
        rows.append({"design": design.label, "templates": design.templates,
                     "distance_levels": design.distances, "seeds": design.seeds,
                     "episodes_per_harness_pair": design.episodes, "interaction_pp": effect * 100,
                     "calibration": calibration, "reps": reps,
                     "rejection_rate": hits / reps,
                     "mc_se": np.sqrt(hits / reps * (1 - hits / reps) / reps),
                     "failed_fits": fails,
                     "plan_s10_low": ref[0] if ref else np.nan,
                     "plan_s10_high": ref[1] if ref else np.nan})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------------
# Part 2: sol H2, paired F-r vs F-0 on derived-far cells
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class H2Setup:
    p_f0: float = 0.80  # success under F-0 on derived-far cells
    cells: int = 2  # derived-far cells per template (recoverable, non-recoverable)
    bound: float = 0.08  # equivalence bound and superiority effect (PLAN §4 H2)
    holm_steps: int = 3  # H1, H2, H3
    sd: float = TEMPLATE_SD
    calibration: str = "marginal"
    # D26: one-sided bootstrap test at the worst Holm step (None = not reported)
    holm_one_sided_alpha: float | None = None
    # D11 option A: observed-far cells on ceil(T_d / divisor) templates (None = not simulated)
    observed_divisor: int | None = None
    observed_cells: int = 2  # observed-far cells per template (recoverable, non-recoverable)
    observed_bound_pp: float = 3.0  # PLAN §4 H2: "less than 3pp difference on observed facts"

    def observed_templates(self, templates: int) -> int:
        return 0 if self.observed_divisor is None else math.ceil(templates / self.observed_divisor)


DEFAULT_H2 = H2Setup()


def simulate_h2(templates: int, effect: float, rng: np.random.Generator,
                setup: H2Setup = DEFAULT_H2) -> tuple[np.ndarray, np.ndarray]:
    """Outcomes (templates x cells) under F-0 and F-r, sharing each template's intercept."""
    a0 = intercept_for(setup.p_f0, setup.sd, setup.calibration)
    a1 = intercept_for(setup.p_f0 + effect, setup.sd, setup.calibration)
    u = rng.normal(0.0, setup.sd, templates)[:, None]
    shape = (templates, setup.cells)
    y0 = (rng.random(shape) < special.expit(a0 + u)).astype(float)
    y1 = (rng.random(shape) < special.expit(a1 + u)).astype(float)
    return y0, y1


def cluster_bootstrap_means(per_template: np.ndarray, rng: np.random.Generator,
                            boot: int) -> np.ndarray:
    """Bootstrap distribution of the mean of per-template values (templates resampled)."""
    n = len(per_template)
    return per_template[rng.integers(0, n, size=(boot, n))].mean(axis=1)


def percentile_ci(dist: np.ndarray, level: float) -> tuple[float, float]:
    q = (1 - level) / 2
    lo, hi = np.quantile(dist, [q, 1 - q])
    return float(lo), float(hi)


def h2_glm(y0: np.ndarray, y1: np.ndarray, engine: str = "fast",
           correction: str = "statsmodels") -> tuple[float, float, float] | None:
    """Confirmatory model: logit with template and cell fixed effects plus the arm."""
    t, c = y0.shape
    y = np.concatenate([y0.ravel(), y1.ravel()])
    template = np.tile(np.repeat(np.arange(t), c), 2)
    cell = np.tile(np.tile(np.arange(c), t), 2)
    arm = np.repeat([0.0, 1.0], t * c)
    cell_dummies = np.column_stack([(cell == k).astype(float) for k in range(1, c)])
    return fe_logit_last_coef(y, template, np.column_stack([cell_dummies, arm]), engine,
                              correction)


def run_h2(reps: int, seed: int, *, templates=(30, 40, 60, 80), boot: int = 2000,
           setup: H2Setup = DEFAULT_H2, engine: str = "fast",
           correction: str = "statsmodels") -> pd.DataFrame:
    effects = (0.0, setup.bound)
    holm_level = 1 - ALPHA / setup.holm_steps
    one_alpha = setup.holm_one_sided_alpha
    obs_setup = replace(setup, cells=setup.observed_cells)
    rows = []
    seqs = np.random.SeedSequence([seed, 2]).spawn(len(templates) * len(effects))
    # Observed-far cells get their own stream so the derived-far columns do not depend on them.
    obs_seqs = np.random.SeedSequence([seed, 3]).spawn(len(templates) * len(effects))
    for i, (t, effect) in enumerate((t, e) for t in templates for e in effects):
        rng, obs_rng = np.random.default_rng(seqs[i]), np.random.default_rng(obs_seqs[i])
        t_obs = setup.observed_templates(t)
        tost = sup = sup_holm = glm_sup = glm_fail = 0
        sup_one = glm_one = supported = obs_within = 0
        estimates, halfwidths, obs_halfwidths = [], [], []
        for _ in range(reps):
            y0, y1 = simulate_h2(t, effect, rng, setup)
            diff = (y1 - y0).mean(axis=1)
            dist = cluster_bootstrap_means(diff, rng, boot)
            lo90, hi90 = percentile_ci(dist, 0.90)
            lo95, _ = percentile_ci(dist, 0.95)
            lo_holm, _ = percentile_ci(dist, holm_level)
            tost += (lo90 > -setup.bound) and (hi90 < setup.bound)
            sup += lo95 > 0
            sup_holm += lo_holm > 0
            fit = h2_glm(y0, y1, engine, correction)
            if fit is None:
                glm_fail += 1
            else:
                glm_sup += (fit[2] < ALPHA) and (fit[0] > 0)
            if one_alpha is not None:
                # D26: one-sided percentile-bootstrap p-value = share of resamples on the null side.
                boot_reject = float(np.mean(dist <= 0)) <= one_alpha
                sup_one += boot_reject
                if fit is not None:
                    glm_one += (fit[0] > 0) and (fit[2] / 2 <= one_alpha)
                    supported += boot_reject and (fit[0] > 0)
            if t_obs:
                o0, o1 = simulate_h2(t_obs, 0.0, obs_rng, obs_setup)
                obs_diff = (o1 - o0).mean(axis=1)
                # |mean| < bound in integer arithmetic: no float ties at exactly 3pp.
                net, n = abs(int((o1 - o0).sum())), o0.size
                obs_within += 100 * net < setup.observed_bound_pp * n
                lo, hi = percentile_ci(cluster_bootstrap_means(obs_diff, obs_rng, boot), 0.90)
                obs_halfwidths.append((hi - lo) / 2)
            estimates.append(diff.mean())
            halfwidths.append((hi90 - lo90) / 2)
        row = {"templates": t, "episodes": 2 * t * setup.cells,
               "true_effect_pp": effect * 100, "p_F0": setup.p_f0,
               "calibration": setup.calibration, "reps": reps, "boot": boot,
               "P_tost_equivalent": tost / reps, "P_superior_95": sup / reps,
               "P_superior_holm": sup_holm / reps, "P_superior_glm": glm_sup / reps,
               "glm_failed_fits": glm_fail,
               "mean_estimate_pp": 100 * float(np.mean(estimates)),
               "mean_ci90_halfwidth_pp": 100 * float(np.mean(halfwidths))}
        if one_alpha is not None:
            row.update({"holm_one_sided_alpha": one_alpha,
                        "P_superior_holm_one_sided": sup_one / reps,
                        "P_superior_glm_one_sided": glm_one / reps,
                        "P_supported": supported / reps})
        if t_obs:
            row.update({"T_o": t_obs, "episodes_observed": 2 * t_obs * setup.observed_cells,
                        "episodes_total": 2 * (t * setup.cells + t_obs * setup.observed_cells),
                        "obs_bound_pp": setup.observed_bound_pp,
                        "obs_P_point_within_bound": obs_within / reps,
                        "obs_mean_ci90_halfwidth_pp": 100 * float(np.mean(obs_halfwidths))})
        rows.append(row)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------------
# Part 3: luna's H1 and H3 (PREREG §4.2, §3 H1, §3 H3, §9.1, §9.4; R6 changes 6 and 9)
# --------------------------------------------------------------------------------------------
# The 7 cells one luna template contributes to H1 and H3 (repeat 0, one episode or prompt each):
#   f0_onr  F-0 on observed-far-NR (in H1 and in H3)    w0_onr  W-0 on observed-far-NR
#   f0_or   F-0 on observed-far-R                       w0_or   W-0 on observed-far-R
#   f0_dnr  F-0 on derived-far-NR                       st_onr  single-turn, observed-far-NR
#   st_dnr  single-turn, derived-far-NR
LUNA_CELLS = ("f0_onr", "w0_onr", "f0_or", "w0_or", "f0_dnr", "st_onr", "st_dnr")
LUNA_TEMPLATES = tuple(range(50, 201, 10))
LUNA_T_CAP = 200  # R6 change 6
LUNA_BOOT = 10_000  # PREREG §9.1
POWER_TARGET = 0.80  # PREREG §4.2
# PREREG §3 H1's kill reading: point estimate < 10pp and upper 90% bound < 15pp
H1_KILL_POINT, H1_KILL_UPPER = 0.10, 0.15
# luna's main sweep and controls at T = 100, billed, "context, rough" (analysis/sol_h1_forecast.py)
LUNA_COST_FORECAST = (REPO_ROOT / "results" / "cost_model" / "20261003T071449Z"
                      / "sol_h1_phase_1a.csv")
LUNA_COST_LINE, LUNA_COST_T = "luna_main_sweep_and_controls", 100
LUNA_VALIDITY_GLOB = "results/persistgym_validity/*-F-0-gpt-6-luna/episodes.jsonl"


@dataclass(frozen=True)
class LunaSetup:
    """One scenario for luna's H1 and H3. Success levels are population averages (the marginal
    calibration), so the probability-scale estimands equal their targets exactly.

    H1 (§3 H1): Penalty_NR = p(F-0, NR) - p(W-0, NR) and Penalty_R likewise, on observed-far.
    W-0 cannot see a far fact (S = 0 by construction), and without lookups it cannot get it
    back, so its NR success is the no-memory level ``p_w0_nr`` and Penalty_NR is fixed by the
    design. Penalty_R is then set to Penalty_NR - ``delta_h1``, which puts W-0's R success at
    ``p_w0_nr + delta_h1 + r_shift``: Delta_H1 = Penalty_NR - Penalty_R = ``delta_h1`` exactly.

    H3 (§3 H3): the single-turn control's success is F-0's plus ``delta_h3`` in both NR-far
    cells, so the pooled Delta_H3 = ``delta_h3`` exactly.

    Every template has one random intercept on the logit scale, with SD ``sd``, shared by its 7
    cells (PLAN §10's model). It is the only source of correlation between a template's cells.
    """
    name: str = "primary"
    p_f0_obs: float = 0.95  # F-0 on observed-far-NR (and on -R, plus r_shift)
    p_f0_der: float = 0.90  # F-0 on derived-far-NR
    p_w0_nr: float = 0.12  # W-0 on observed-far-NR: the no-memory level
    sd: float = 1.0  # template random-intercept SD, logit scale
    r_shift: float = 0.0  # p(F-0, observed-far-R) - p(F-0, observed-far-NR)
    delta_h1: float = 0.10  # true Delta_H1: the kill boundary (§3 H1, §4.2)
    delta_h3: float = 0.0  # true Delta_H3 (§4.2)
    h3_margin: float = 0.05  # H3's non-inferiority bound (§3 H3)
    holm_tests: int = 2  # Holm family: H1 and H3 (decided 2026-10-06; R6 change 9)
    calibration: str = "marginal"

    @property
    def worst_step(self) -> float:
        """The one-sided level of the worst Holm step, ALPHA / family size."""
        return ALPHA / self.holm_tests

    def levels(self) -> dict[str, float]:
        """Success level of each cell in LUNA_CELLS."""
        p_f0_r = self.p_f0_obs + self.r_shift
        penalty_nr = self.p_f0_obs - self.p_w0_nr
        levels = {"f0_onr": self.p_f0_obs, "w0_onr": self.p_w0_nr, "f0_or": p_f0_r,
                  "w0_or": p_f0_r - (penalty_nr - self.delta_h1), "f0_dnr": self.p_f0_der,
                  "st_onr": self.p_f0_obs + self.delta_h3,
                  "st_dnr": self.p_f0_der + self.delta_h3}
        bad = {k: v for k, v in levels.items() if not 0 < v < 1}
        if bad:
            raise ValueError(f"{self.name}: success levels outside (0, 1): {bad}")
        return levels


LUNA_PRIMARY = LunaSetup()
LUNA_PESSIMISTIC = LunaSetup("pessimistic", p_f0_obs=0.85, p_f0_der=0.80, p_w0_nr=0.18, sd=0.0)


def simulate_luna(templates: int, rng: np.random.Generator,
                  setup: LunaSetup = LUNA_PRIMARY) -> dict[str, np.ndarray]:
    """One data set: 0/1 outcomes per template for each cell in LUNA_CELLS. The draws do not
    depend on the success levels or the SD (only their transforms do), so scenarios given the
    same generator share their random numbers, and the first t templates of a data set are a
    data set of t templates (templates are taken in seed order, §2.9)."""
    levels = setup.levels()
    u = setup.sd * rng.standard_normal(templates)
    out = {}
    for cell in LUNA_CELLS:
        a = intercept_for(levels[cell], setup.sd, setup.calibration)
        out[cell] = (rng.random(templates) < special.expit(a + u)).astype(float)
    return out


def luna_estimates(y: dict[str, np.ndarray]) -> dict[str, float]:
    """The §3 estimands from cell means: the penalties, Delta_H1 and Delta_H3 (pooled over the
    observed and derived NR-far cells)."""
    p = {k: float(np.mean(v)) for k, v in y.items()}
    penalty_nr, penalty_r = p["f0_onr"] - p["w0_onr"], p["f0_or"] - p["w0_or"]
    pooled_st = (np.sum(y["st_onr"]) + np.sum(y["st_dnr"])) / (y["st_onr"].size
                                                                + y["st_dnr"].size)
    pooled_f0 = (np.sum(y["f0_onr"]) + np.sum(y["f0_dnr"])) / (y["f0_onr"].size
                                                                + y["f0_dnr"].size)
    return {"penalty_nr": penalty_nr, "penalty_r": penalty_r,
            "delta_h1": penalty_nr - penalty_r, "delta_h3": float(pooled_st - pooled_f0)}


def luna_per_template(y: dict[str, np.ndarray]) -> np.ndarray:
    """Integer contributions per template, (templates x 2): column 0 is the template's term of
    T * Delta_H1, column 1 its term of 2T * Delta_H3. With one outcome per template and cell
    (no exclusions), the column means are Delta_H1 and 2 * Delta_H3."""
    d1 = (y["f0_onr"] - y["w0_onr"]) - (y["f0_or"] - y["w0_or"])
    d3 = (y["st_onr"] - y["f0_onr"]) + (y["st_dnr"] - y["f0_dnr"])
    return np.rint(np.column_stack([d1, d3])).astype(np.int64)


def category_bootstrap_sums(values: np.ndarray, rng: np.random.Generator,
                            boot: int) -> np.ndarray:
    """Template-cluster bootstrap of column sums of per-template integer rows, (boot x columns).

    Resampling T templates with replacement picks each distinct row with probability (its
    count / T) on every draw, so the counts of the distinct rows in a resample are
    Multinomial(T, counts / T). Drawing those counts gives the same bootstrap distribution as
    drawing T template indices, at a cost that does not grow with T. Every contrast uses the
    same resamples (§9.1: resample templates, recompute each contrast)."""
    rows, counts = np.unique(values, axis=0, return_counts=True)
    draws = rng.multinomial(len(values), counts / len(values), size=boot)
    return draws @ rows


def holm_reject(pvalues, alpha: float = ALPHA) -> np.ndarray:
    """Holm's step-down procedure: which hypotheses are rejected at familywise level alpha."""
    p = np.asarray(pvalues, dtype=float)
    reject = np.zeros(len(p), dtype=bool)
    for i, j in enumerate(np.argsort(p, kind="stable")):
        if p[j] > alpha / (len(p) - i):
            break
        reject[j] = True
    return reject


def _fe_logit_mle(y, codes, z, engine: str = "fast") -> tuple[np.ndarray, np.ndarray] | None:
    """MLE (template intercepts, slopes) of the FE logit on informative templates, for a point
    estimate only (no SEs): Newton steps with statsmodels' deviance stopping rule ('fast'),
    and statsmodels itself if they fail.

    Here the fit often meets quasi-separation: with F-0 near 1 and W-0 near chance, few
    templates have W-0 succeed where F-0 fails, so the W-0 coefficient runs off to -inf.
    statsmodels stops when the deviance stops changing and returns large finite coefficients;
    that is what the confirmatory statsmodels fit (§9.1) would report, so those signs are used
    (the tests check that both routes agree in sign). None if neither gives finite values."""
    if engine == "fast":
        with np.errstate(all="ignore"):
            try:
                alpha, beta = _fe_logit_newton(y, codes, z, dev_tol=1e-8)
                if np.isfinite(alpha).all() and np.isfinite(beta).all():
                    return alpha, beta
            except (np.linalg.LinAlgError, ValueError, FloatingPointError):
                pass
    g = codes.max() + 1
    dummies = np.zeros((len(y), g))
    dummies[np.arange(len(y)), codes] = 1.0
    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")
        try:
            params = np.asarray(sm.GLM(y, np.column_stack([dummies, z]),
                                       family=sm.families.Binomial()).fit().params)
        except (np.linalg.LinAlgError, ValueError, FloatingPointError,
                sm_exceptions.PerfectSeparationError):
            return None
    return (params[:g], params[g:]) if np.isfinite(params).all() else None


def h1_glm(y: dict[str, np.ndarray], engine: str = "fast") -> float | None:
    """The logit-scale Delta_H1 from a logit with template fixed effects on H1's 4 cells (W-0,
    R and W-0 x R): the interaction, Penalty_NR - Penalty_R in logits. Its sign is the model
    sign that "supported" needs (§9.4). The confirmatory GLM of §9.1 is fitted on every cell
    with harness x recoverable x derived x distance terms; this smaller model stands in for it,
    for the sign only. None if the fit fails."""
    t = len(y["f0_onr"])
    yy = np.concatenate([y["f0_onr"], y["w0_onr"], y["f0_or"], y["w0_or"]])
    w, r = np.repeat([0.0, 1.0, 0.0, 1.0], t), np.repeat([0.0, 0.0, 1.0, 1.0], t)
    yk, codes, z, n_groups = _informative(yy, np.tile(np.arange(t), 4),
                                          np.column_stack([w, r, w * r]))
    if n_groups < 2:
        return None
    fit = _fe_logit_mle(yk, codes, z, engine)
    return None if fit is None else float(fit[1][-1])


def h3_glm_ame(y: dict[str, np.ndarray], engine: str = "fast") -> float | None:
    """§9.4's model check for H3: a binomial GLM with template fixed effects, a derived-cell
    term and the arm (single-turn vs F-0) on the 2 NR-far cells, turned into a
    probability-scale Delta_H3 (the average marginal effect of the arm over every template and
    cell). A template whose 4 outcomes are equal has an infinite fixed effect, so both arms'
    fitted success is 0 or 1 there and it adds 0 to the average; it still counts in the
    denominator. None if the fit fails."""
    t = len(y["f0_onr"])
    yy = np.concatenate([y["f0_onr"], y["f0_dnr"], y["st_onr"], y["st_dnr"]])
    der, arm = np.repeat([0.0, 1.0, 0.0, 1.0], t), np.repeat([0.0, 0.0, 1.0, 1.0], t)
    yk, codes, z, n_groups = _informative(yy, np.tile(np.arange(t), 4),
                                          np.column_stack([der, arm]))
    if n_groups < 2:
        return 0.0 if n_groups == 0 else None
    fit = _fe_logit_mle(yk, codes, z, engine)
    if fit is None:
        return None
    alpha, (gamma, beta) = fit
    base = alpha[:, None] + np.array([0.0, gamma])[None, :]
    ame = float((special.expit(base + beta) - special.expit(base)).sum() / (2 * t))
    return ame if np.isfinite(ame) else None


def analyse_luna(y: dict[str, np.ndarray], rng: np.random.Generator, boot: int = LUNA_BOOT,
                 setup: LunaSetup = LUNA_PRIMARY, engine: str = "fast") -> dict:
    """H1 and H3 on one data set, as the confirmatory analysis runs them (§9.1, §9.4):
    template-cluster percentile bootstrap on the probability scale; one-sided bootstrap
    p-values (the share of resamples on the null side, ties included); Holm over the family;
    "supported" = the test rejects and the model check agrees.
    - H1: H0 is Delta_H1 <= 0; p1 = share of resamples with Delta_H1* <= 0; the model check is
      a positive logit interaction (h1_glm).
    - H3: H0 is Delta_H3 >= margin; p3 = share of resamples with Delta_H3* >= margin; the model
      check is a GLM Delta_H3 below the margin (h3_glm_ame).
    Sums stay integers, so a resample that lands exactly on 0 or on the margin is counted on
    the null side without float error. A model check is fitted only when its test rejects at
    ALPHA, the most any reading allows; otherwise "agree" is False and nothing is supported."""
    vals = luna_per_template(y)
    t = len(vals)
    sums = category_bootstrap_sums(vals, rng, boot)
    est = vals.sum(axis=0)
    h3_threshold = math.ceil(2 * t * setup.h3_margin - 1e-9)  # 2T * margin, as an integer
    p1 = float(np.mean(sums[:, 0] <= 0))
    p3 = float(np.mean(sums[:, 1] >= h3_threshold))
    # 90% percentile intervals of the sums (T * Delta_H1 and 2T * Delta_H3)
    lo1, hi1 = percentile_ci(sums[:, 0], 0.90)
    lo3, hi3 = percentile_ci(sums[:, 1], 0.90)
    glm1 = h1_glm(y, engine) if p1 <= ALPHA else None
    ame3 = h3_glm_ame(y, engine) if p3 <= ALPHA else None
    family = [p1, p3] + [1.0] * (setup.holm_tests - 2)  # other members counted as not rejected
    holm = holm_reject(family)
    holm4 = holm_reject([p1, p3, 1.0, 1.0])  # the family of 4, a sensitivity analysis
    worst, unadj = setup.worst_step, ALPHA
    return {
        "delta_h1": est[0] / t, "delta_h3": est[1] / (2 * t), "p1": p1, "p3": p3,
        "h1_ci90": (lo1 / t, hi1 / t), "h3_ci90": (lo3 / (2 * t), hi3 / (2 * t)),
        "h1_glm_failed": p1 <= ALPHA and glm1 is None,
        "h3_glm_failed": p3 <= ALPHA and ame3 is None,
        # an interaction of +-1e-16 is an exact 0 in float noise: not a positive sign
        "h1_glm_agree": glm1 is not None and glm1 > 1e-8,
        "h3_glm_agree": ame3 is not None and ame3 < setup.h3_margin,
        "h1_worst": p1 <= worst, "h3_worst": p3 <= worst,
        "h1_holm": bool(holm[0]), "h3_holm": bool(holm[1]),
        "h1_holm4": bool(holm4[0]), "h3_holm4": bool(holm4[1]),
        "h1_unadj": p1 <= unadj, "h3_unadj": p3 <= unadj,
        # §3 readings on point estimates and unadjusted 90% CIs, compared on the sums' scale
        # (1e-9 absorbs float error in thresholds such as 0.1 * 70, never a real difference)
        "h1_kill": (est[0] < H1_KILL_POINT * t - 1e-9) and (hi1 < H1_KILL_UPPER * t - 1e-9),
        "h3_ci90_within": hi3 <= 2 * t * setup.h3_margin + 1e-9,
    }


def run_luna(reps: int, seed: int, *, templates=LUNA_TEMPLATES, boot: int = LUNA_BOOT,
             setup: LunaSetup = LUNA_PRIMARY, engine: str = "fast",
             label: str | None = None) -> pd.DataFrame:
    """Power of H1 and H3 for each template count, one row per count.

    Each replication draws one data set of max(templates) templates, and every count t is
    analysed on its first t templates (common random numbers across t, as the sweep takes
    templates in seed order). Every scenario run with the same seed gets the same draws."""
    templates = tuple(sorted(templates))
    data_rng = np.random.default_rng(np.random.SeedSequence([seed, 4]))
    boot_rng = np.random.default_rng(np.random.SeedSequence([seed, 5]))
    keys = ("h1_worst", "h3_worst", "h1_holm", "h3_holm", "h1_holm4", "h3_holm4", "h1_unadj",
            "h3_unadj", "h1_kill", "h3_ci90_within", "h1_glm_failed", "h3_glm_failed")
    hits = {t: dict.fromkeys(keys + ("h1_sup_worst", "h3_sup_worst", "h1_sup_holm",
                                     "h3_sup_holm", "both_sup_holm", "h1_veto", "h3_veto"),
                             0) for t in templates}
    sums = {t: {"delta_h1": 0.0, "delta_h3": 0.0, "hw1": 0.0, "hw3": 0.0} for t in templates}
    for _ in range(reps):
        full = simulate_luna(templates[-1], data_rng, setup)
        for t in templates:
            r = analyse_luna({k: v[:t] for k, v in full.items()}, boot_rng, boot, setup, engine)
            h = hits[t]
            for k in keys:
                h[k] += bool(r[k])
            h["h1_veto"] += r["h1_unadj"] and not r["h1_glm_agree"]
            h["h3_veto"] += r["h3_unadj"] and not r["h3_glm_agree"]
            h["h1_sup_worst"] += r["h1_worst"] and r["h1_glm_agree"]
            h["h3_sup_worst"] += r["h3_worst"] and r["h3_glm_agree"]
            h["h1_sup_holm"] += r["h1_holm"] and r["h1_glm_agree"]
            h["h3_sup_holm"] += r["h3_holm"] and r["h3_glm_agree"]
            h["both_sup_holm"] += (r["h1_holm"] and r["h1_glm_agree"] and r["h3_holm"]
                                   and r["h3_glm_agree"])
            s = sums[t]
            s["delta_h1"] += r["delta_h1"]
            s["delta_h3"] += r["delta_h3"]
            s["hw1"] += (r["h1_ci90"][1] - r["h1_ci90"][0]) / 2
            s["hw3"] += (r["h3_ci90"][1] - r["h3_ci90"][0]) / 2
    levels = setup.levels()
    rows = []
    for t in templates:
        h, s = hits[t], sums[t]
        rate = {k: v / reps for k, v in h.items()}
        rows.append({
            "scenario": label or setup.name, "templates": t, "reps": reps, "boot": boot,
            **{f"p_{k}": v for k, v in levels.items()}, "template_sd": setup.sd,
            "true_delta_h1_pp": 100 * setup.delta_h1, "true_delta_h3_pp": 100 * setup.delta_h3,
            "holm_tests": setup.holm_tests, "worst_step_alpha": setup.worst_step,
            # decision columns (§4.2 at the worst Holm step; "supported" as in §9.4)
            "P_h1_supported_worst_step": rate["h1_sup_worst"],
            "P_h3_supported_worst_step": rate["h3_sup_worst"],
            "mc_se_h1": math.sqrt(rate["h1_sup_worst"] * (1 - rate["h1_sup_worst"]) / reps),
            "mc_se_h3": math.sqrt(rate["h3_sup_worst"] * (1 - rate["h3_sup_worst"]) / reps),
            # the bootstrap tests alone, at the worst step, under Holm and unadjusted
            "P_h1_worst_step": rate["h1_worst"], "P_h3_worst_step": rate["h3_worst"],
            "P_h1_supported_holm": rate["h1_sup_holm"],
            "P_h3_supported_holm": rate["h3_sup_holm"],
            "P_both_supported_holm": rate["both_sup_holm"],
            "P_h1_holm": rate["h1_holm"], "P_h3_holm": rate["h3_holm"],
            "P_h1_unadjusted": rate["h1_unadj"], "P_h3_unadjusted": rate["h3_unadj"],
            "P_h1_holm4": rate["h1_holm4"], "P_h3_holm4": rate["h3_holm4"],
            # §3 readings
            "P_h1_kill_fires": rate["h1_kill"], "P_h3_ci90_upper_within": rate["h3_ci90_within"],
            # model check: P(the test rejects at 0.05 but the model disagrees), failed fits
            "P_h1_glm_veto": rate["h1_veto"], "P_h3_glm_veto": rate["h3_veto"],
            "h1_glm_failed": h["h1_glm_failed"], "h3_glm_failed": h["h3_glm_failed"],
            "mean_delta_h1_pp": 100 * s["delta_h1"] / reps,
            "mean_delta_h3_pp": 100 * s["delta_h3"] / reps,
            "mean_h1_ci90_halfwidth_pp": 100 * s["hw1"] / reps,
            "mean_h3_ci90_halfwidth_pp": 100 * s["hw3"] / reps})
    return pd.DataFrame(rows)


def smallest_template_count(df: pd.DataFrame, columns: tuple[str, ...],
                            target: float = POWER_TARGET) -> int | None:
    """§4.2's rule on one scenario's rows: the smallest template count at which every column
    reaches the target; None if none does."""
    ok = df[(df[list(columns)] >= target).all(axis=1)]
    return int(ok.templates.min()) if len(ok) else None


LUNA_READINGS = {
    "worst Holm step, supported (decision)": ("P_h1_supported_worst_step",
                                              "P_h3_supported_worst_step"),
    "worst Holm step, bootstrap test only": ("P_h1_worst_step", "P_h3_worst_step"),
    "Holm over H1 and H3 together, supported": ("P_h1_supported_holm", "P_h3_supported_holm"),
    "unadjusted one-sided 0.05": ("P_h1_unadjusted", "P_h3_unadjusted"),
}


def luna_decision(power: pd.DataFrame, cap: int = LUNA_T_CAP,
                  target: float = POWER_TARGET) -> pd.DataFrame:
    """For each scenario and reading: the smallest T meeting the target for H1, for H3 and for
    both, and the T that R6 change 6 then sets (the cap if no T up to it meets the rule)."""
    rows = []
    for name, df in power.groupby("scenario", sort=False):
        df = df[df.templates <= cap]
        for reading, (c1, c3) in LUNA_READINGS.items():
            both = smallest_template_count(df, (c1, c3), target)
            chosen = both if both is not None else cap
            at = df[df.templates == chosen]
            rows.append({"scenario": name, "reading": reading, "target": target,
                         "T_h1": smallest_template_count(df, (c1,), target),
                         "T_h3": smallest_template_count(df, (c3,), target),
                         "T_both": both, "T_set": chosen,
                         "T_set_by": "rule" if both is not None else f"cap ({cap}, R6 change 6)",
                         "power_h1_at_T_set": float(at[c1].iloc[0]) if len(at) else np.nan,
                         "power_h3_at_T_set": float(at[c3].iloc[0]) if len(at) else np.nan,
                         # MC noise: does every larger count also meet the target?
                         "all_larger_T_meet": (bool((df[df.templates >= both][[c1, c3]]
                                                     >= target).all(axis=None))
                                               if both is not None else None)})
    return pd.DataFrame(rows)


def luna_sensitivity_setups(primary: LunaSetup, others: list[LunaSetup],
                            extra_sd: tuple[float, ...] = ()) -> list[tuple[str, LunaSetup]]:
    """Primary with one assumption changed at a time: to each other scenario's value, to each
    extra template SD, and a size check at both null boundaries (Delta_H1 = 0, Delta_H3 at the
    margin), where the rejection rates should be at most the nominal levels. At H3's boundary
    F-0 sits one margin below the primary levels, so the single-turn control stays at them
    (primary's F-0 plus 5pp would reach 1)."""
    out = []
    fields = ("p_f0_obs", "p_f0_der", "p_w0_nr", "sd", "r_shift")
    for other in others:
        for f in fields:
            if getattr(other, f) != getattr(primary, f):
                out.append((f"{primary.name}, {f} = {getattr(other, f):g} (as {other.name})",
                            replace(primary, **{f: getattr(other, f)})))
    for sd in extra_sd:
        if sd != primary.sd and all(s.sd != sd for _, s in out):
            out.append((f"{primary.name}, sd = {sd:g}", replace(primary, sd=sd)))
    m = primary.h3_margin
    out.append((f"size: delta_h1 = 0, delta_h3 = {m:g} (F-0 {m:g} below {primary.name})",
                replace(primary, delta_h1=0.0, delta_h3=m, p_f0_obs=primary.p_f0_obs - m,
                        p_f0_der=primary.p_f0_der - m)))
    return out


def luna_normal_power(setup: LunaSetup, templates: int, alpha: float) -> tuple[float, float]:
    """Cross-check by another route: normal-approximation power of the H1 and H3 tests
    (one-sided at alpha) from the exact variance of one template's contribution, integrated
    over the template intercept by Gauss-Hermite quadrature. It leaves out the model check and
    the bootstrap's discreteness, so it should sit close to the simulated test-only power."""
    lv = setup.levels()
    p = {k: special.expit(intercept_for(v, setup.sd, setup.calibration) + setup.sd * _GH_X)
         for k, v in lv.items()}

    def var(mean_u, var_u):  # law of total variance over the intercept
        return float(np.sum(_GH_W * var_u) + np.sum(_GH_W * mean_u ** 2)
                     - np.sum(_GH_W * mean_u) ** 2)

    m1 = p["f0_onr"] - p["w0_onr"] - p["f0_or"] + p["w0_or"]
    v1 = var(m1, sum(p[k] * (1 - p[k]) for k in ("f0_onr", "w0_onr", "f0_or", "w0_or")))
    m3 = (p["st_onr"] - p["f0_onr"] + p["st_dnr"] - p["f0_dnr"]) / 2
    v3 = var(m3, sum(p[k] * (1 - p[k]) for k in ("st_onr", "f0_onr", "st_dnr", "f0_dnr")) / 4)
    z = special.ndtri(1 - alpha)
    return (float(special.ndtr(setup.delta_h1 / math.sqrt(v1 / templates) - z)),
            float(special.ndtr((setup.h3_margin - setup.delta_h3) / math.sqrt(v3 / templates)
                               - z)))


def luna_normal_check(setups: list[LunaSetup], templates, max_templates: int = 1000
                      ) -> pd.DataFrame:
    """luna_normal_power at each simulated T, at the worst Holm step and unadjusted, plus the
    smallest multiple of 10 (up to max_templates, past the cap) at which both tests reach the
    target at the worst step by this approximation."""
    rows = []
    for s in setups:
        uncapped = next((t for t in range(10, max_templates + 1, 10)
                         if min(luna_normal_power(s, t, s.worst_step)) >= POWER_TARGET), None)
        for t in templates:
            h1w, h3w = luna_normal_power(s, t, s.worst_step)
            h1u, h3u = luna_normal_power(s, t, ALPHA)
            rows.append({"scenario": s.name, "templates": t, "normal_h1_worst_step": h1w,
                         "normal_h3_worst_step": h3w, "normal_h1_unadjusted": h1u,
                         "normal_h3_unadjusted": h3u, "normal_T_both_uncapped": uncapped})
    return pd.DataFrame(rows)


def validity_template_sd(paths: list[Path], grid_max: float = 4.0,
                         step: float = 0.01) -> pd.DataFrame:
    """The template variance measured in validity runs (§4.2, §9.8), per variant: the ML
    template SD of a random-intercept logit (one intercept for every task cell), with a 95%
    profile-likelihood interval (chi-square 1 df, so conservative at the boundary 0) and the
    likelihood-ratio statistic against SD 0. When every episode succeeded (or none did) the SD
    is not identified."""
    recs = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            recs += [json.loads(line) for line in fh if line.strip()]
    df = pd.DataFrame([{"variant": r["variant"], "template": r["template_id"],
                        "success": bool(r["need_correct"])} for r in recs
                       if not r.get("excluded")])
    x, w = np.polynomial.hermite_e.hermegauss(80)
    w = w / w.sum()
    rows = []
    for variant, g in df.groupby("variant", sort=True):
        per = g.groupby("template").success.agg(["sum", "count"])
        k, n = per["sum"].to_numpy(float), per["count"].to_numpy(float)
        row = {"variant": variant, "templates": len(per), "episodes": int(n.sum()),
               "successes": int(k.sum()), "rate": k.sum() / n.sum(), "sd_hat": np.nan,
               "sd_ci95_low": np.nan, "sd_ci95_high": np.nan, "lr_vs_sd0": np.nan,
               "note": ""}
        if k.sum() in (0, n.sum()):
            row["note"] = "not identified: every episode had the same outcome"
            rows.append(row)
            continue

        def nll(a, s, k=k, n=n):
            p = np.clip(special.expit(a + s * x[None, :]), 1e-300, 1 - 1e-16)
            lik = np.exp(k[:, None] * np.log(p) + (n - k)[:, None] * np.log1p(-p)) @ w
            return -float(np.log(lik).sum())

        grid = np.arange(0.0, grid_max + step / 2, step)
        prof = np.array([optimize.minimize_scalar(lambda a, s=s: nll(a, s), bounds=(-15, 15),
                                                  method="bounded").fun for s in grid])
        best = int(prof.argmin())
        inside = grid[2 * (prof - prof[best]) <= 3.841459]
        row.update({"sd_hat": grid[best], "sd_ci95_low": inside.min(),
                    "sd_ci95_high": inside.max(), "lr_vs_sd0": 2 * (prof[0] - prof[best])})
        if inside.max() >= grid[-1]:
            row["note"] = f"upper bound reaches the grid end ({grid_max:g})"
        rows.append(row)
    return pd.DataFrame(rows)


def luna_cost_per_template(path: Path = LUNA_COST_FORECAST) -> float | None:
    """Billed USD per template of luna's main sweep and controls (4 replay-off cells x 8 task
    cells, restated control, single-turn control, repeat subset), from the committed forecast
    at T = 100; None if the file or line is missing."""
    try:
        df = pd.read_csv(path)
    except OSError:
        return None
    hit = df[df.line == LUNA_COST_LINE]
    return float(hit.usd.iloc[0]) / LUNA_COST_T if len(hit) else None


def _phase_1a_spent() -> float | None:
    try:
        from common import costs
        return costs.spend_by_phase(costs.read_rows()).get("1a")
    except (OSError, ValueError):
        return None


def _md_table(df: pd.DataFrame, floatfmt: str = "{:.3f}") -> str:
    def fmt(v):
        if isinstance(v, float):
            return "" if np.isnan(v) else floatfmt.format(v)
        return "" if v is None else str(v)
    lines = ["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)]
    lines += ["| " + " | ".join(fmt(v) for v in row) + " |"
              for row in df.itertuples(index=False)]
    return "\n".join(lines)


LUNA_WHY = {
    "p_f0_obs": (
        ("F-0 success, observed-far (R and NR); the single-turn control's on observed-NR-far "
         "under H3's null"),
        ("No F-0 main-cell success may be used (pilots blinded, §11; no main-split episode "
         "exists). luna scored 160/160 on restated-at-need (memory taken out), so the ceiling "
         "is near 1; full history must still retrieve one binding from beyond W = 24k tokens. "
         "Primary 0.95 sits just below that ceiling; pessimistic 0.85 allows real long-context "
         "loss.")),
    "p_f0_der": (
        "F-0 success, derived-NR-far (the single-turn control's too, under H3's null)",
        ("Restated derived cells also scored 80/80, so the arithmetic is not the problem; a "
         "derived fact needs 2-3 clue bindings and the rule retrieved, so each scenario puts "
         "it 5pp below the observed level.")),
    "p_w0_nr": (
        "W-0 success, observed-far-NR: the no-memory level",
        ("W-0 has evicted the evidence and has no lookup, as in the fact-withheld control. "
         "luna's pooled withheld rate is 19/160 = 0.119 (primary 0.12); 0.18 is the upper end "
         "of its 95% Wilson interval. Chance is 0.10 (K = 10).")),
    "sd": (
        "Template random-intercept SD (logit), shared by a template's 7 cells",
        ("Primary 1.0 is PLAN §10's value and close to the ML estimate from luna's withheld "
         "run (table below). Every contrast here is paired within template, so a larger "
         "shared SD raises power (sensitivity rows); pessimistic 0, the lower end of that "
         "estimate's 95% interval, leaves the cells independent.")),
    "r_shift": (
        "F-0 success on observed-far-R minus on -NR",
        ("0: F-0 sees the fact in full history, so lookups should add little. Then W-0's R "
         "success = p_w0_nr + delta_h1.")),
    "delta_h1": (
        "True Delta_H1 = Penalty_NR - Penalty_R",
        ("10pp, fixed by §4.2 (the kill boundary). Penalty_NR = p_f0_obs - p_w0_nr is set by "
         "the design; Penalty_R = Penalty_NR - 10pp.")),
    "delta_h3": (
        "True Delta_H3 = p(single-turn) - p(F-0), NR-far pooled",
        "0, fixed by §4.2; the bound is 5pp (§3 H3)."),
    "holm_tests": (
        "Holm family size",
        ("2 (H1, H3): the researcher's decision of 2026-10-06, R6 change 9; worst step "
         "one-sided 0.025. The family of 4 (worst step 0.0125) is a sensitivity column.")),
}


def luna_summary(power: pd.DataFrame, decision: pd.DataFrame, sens: pd.DataFrame | None,
                 validity: pd.DataFrame | None, setups: list[LunaSetup], run_id: str,
                 command: str, cost_per_t: float | None, spent_1a: float | None,
                 normal: pd.DataFrame | None = None) -> str:
    """summary.md of a luna power run: assumptions, the template count each scenario sets,
    power by T, sensitivity, cost and what the run does not show."""
    reps, boot = int(power.reps.iloc[0]), int(power.boot.iloc[0])
    names = [s.name for s in setups]
    worst = setups[0].worst_step
    out = [
        f"# luna power re-simulation for T (PREREG §4.2, R6 change 6): {run_id}", "",
        f"Command: `{command}`", "",
        "## What is simulated",
        ("One luna data set holds, per template, one repeat-0 outcome in each of 7 cells "
         "(§2.9: repeats stay out of the primary analyses): F-0 and W-0 on observed-far-R and "
         "-NR (H1), and F-0 and the single-turn control on observed- and derived-NR-far (H3). "
         "F-0 on observed-NR-far is shared by both tests. Each data set is analysed as §9.1 "
         "and §9.4 will analyse the sweep:"),
        (f"- template-cluster percentile bootstrap on the probability scale with {boot:,} "
         "resamples, shared by both contrasts (drawn as category counts, which is exact: "
         "`category_bootstrap_sums`);"),
        ("- H1: one-sided bootstrap p = share of resamples with Delta_H1 <= 0; H3: share "
         "with Delta_H3 >= 5pp; ties count on the null side;"),
        ("- \"supported\" = the test rejects and the model check agrees: for H1 a positive "
         "W-0 x R interaction in a template-FE logit on H1's 4 cells, for H3 a GLM Delta_H3 "
         "(average marginal effect) below 5pp;"),
        (f"- {reps:,} simulated sweeps per scenario, each analysed at every T from "
         f"{power.templates.min()} to {power.templates.max()} on its first T templates "
         "(templates are taken in seed order), so the power curves share random numbers."),
        "",
        ("**Decision reading.** The frozen rule needs power >= 0.80 for H1 at Delta_H1 = "
         "10pp and for H3 at Delta_H3 = 0. This run reads it conservatively: P(supported) for "
         f"each test at the worst Holm step (one-sided {worst:g} with the family of "
         f"{setups[0].holm_tests}). That is at most the power under the real Holm procedure "
         "and at most the unadjusted power; both are reported too."), "",
        "## Assumptions",
        "| Parameter | " + " | ".join(names) + " | Why |",
        "|---|" + "---|" * len(names) + "---|"]
    for f, (label, why) in LUNA_WHY.items():
        vals = " | ".join(f"{getattr(s, f):g}" for s in setups)
        out.append(f"| {label} (`{f}`) | {vals} | {why} |")
    lv = pd.DataFrame([{"scenario": s.name, **s.levels()} for s in setups])
    out += ["", ("Resulting success levels per cell (population averages; Delta_H1 = "
                 "(f0_onr - w0_onr) - (f0_or - w0_or), Delta_H3 = mean(st) - mean(f0) over the "
                 "NR-far cells):"), "", _md_table(lv), ""]
    if validity is not None and len(validity):
        out += ["## Variance measured in luna's validity runs",
                ("Random-intercept logit on F-0, validity templates 0-19 x 8 task cells "
                 "(`validity_template_sd`; 95% profile-likelihood interval, chi-square 1 df):"),
                "", _md_table(validity), "",
                ("Restated-at-need succeeded in every episode, so it carries no variance. The "
                 "withheld run measures how guesses cluster by template, not how memory "
                 "success does, and 20 templates leave the interval wide. It is context for "
                 "the SD assumption, not a measurement of it."), ""]
    out += ["## Result: the template count", "", _md_table(decision.drop(columns=["target"])),
            ""]
    for name in names:
        d = decision[(decision.scenario == name)
                     & (decision.reading == next(iter(LUNA_READINGS)))].iloc[0]
        if d.T_both is None or pd.isna(d.T_both):
            out.append(f"- **{name}:** no T <= {LUNA_T_CAP} reaches 0.80 for both tests, so R6 "
                       f"change 6 sets **T = {LUNA_T_CAP}**; achieved power there: H1 "
                       f"{d.power_h1_at_T_set:.3f}, H3 {d.power_h3_at_T_set:.3f}.")
        else:
            out.append(f"- **{name}:** T = {int(d.T_both)} (H1 {d.power_h1_at_T_set:.3f}, "
                       f"H3 {d.power_h3_at_T_set:.3f}).")
    cols = ["scenario", "templates", "P_h1_supported_worst_step", "P_h3_supported_worst_step",
            "P_h1_supported_holm", "P_h3_supported_holm", "P_h1_unadjusted",
            "P_h3_unadjusted", "P_h1_holm4", "P_h3_holm4", "P_h1_kill_fires"]
    out += ["", "## Power by T",
            (f"Monte Carlo SE at 0.80 is about {math.sqrt(0.16 / reps):.3f}. Holm columns "
             "run the procedure over H1 and H3 on the same data; holm4 is the family of 4 "
             "(H2's tests counted as not rejected). P_h1_kill_fires: §3's kill reading at the "
             "true 10pp. Full columns in `luna_power.csv`."), "",
            _md_table(power[cols]), ""]
    if normal is not None and len(normal):
        both = power.merge(normal, on=["scenario", "templates"])
        both = both[both.templates % 50 == 0]
        cols = ["scenario", "templates", "P_h1_worst_step", "normal_h1_worst_step",
                "P_h3_worst_step", "normal_h3_worst_step"]
        out += ["## Cross-check: normal approximation",
                ("`luna_normal_power` computes the test-only power at the worst step another "
                 "way: a normal approximation with the exact variance of one template's "
                 "contribution, integrated over the template intercept. It leaves out the model "
                 "check and the bootstrap's discreteness. Full table in "
                 "`luna_normal_check.csv`."), "", _md_table(both[cols]), ""]
        for name, g in normal.groupby("scenario", sort=False):
            t_unc = g.normal_T_both_uncapped.iloc[0]
            out.append(f"- **{name}:** without R6's cap, this approximation reaches 0.80 for both "
                       "tests at the worst step at "
                       + (f"about T = {int(t_unc)}." if pd.notna(t_unc) else "no T <= 1000."))
        out.append("")
    if sens is not None and len(sens):
        cols = ["scenario", "templates", "P_h1_supported_worst_step",
                "P_h3_supported_worst_step", "P_h1_unadjusted", "P_h3_unadjusted"]
        out += ["## Sensitivity: the primary scenario with one assumption changed", "",
                _md_table(sens[cols]), "",
                ("In the size row both nulls hold at their boundary, so its columns are "
                 "rejection rates under H0 and should not exceed the nominal level."), ""]
    if cost_per_t is not None:
        source = LUNA_COST_FORECAST.relative_to(REPO_ROOT).as_posix()
        out += ["## Cost and the phase-1a cap",
                (f"luna's sweep and controls cost about ${cost_per_t:.4f} billed per template "
                 f"(committed forecast `{source}`, line `{LUNA_COST_LINE}` at T = "
                 f"{LUNA_COST_T}, scaled linearly; rough).")]
        for t in sorted({int(x) for x in decision.T_set}):
            line = f"- T = {t}: about ${cost_per_t * t:.2f}"
            if spent_1a is not None:
                line += (f"; phase 1a would reach ${spent_1a + cost_per_t * t:.2f} of its "
                         f"$500 cap (spent ${spent_1a:.2f}, `results/costs.csv`)")
            out.append(line + ".")
        out.append("")
    out += ["## What this does not show",
            ("- The success levels and the template SD are assumptions, not measurements: no "
             "main-split episode exists and pilot outcomes are blinded. Power depends mostly "
             "on them."),
            ("- One shared template intercept is the only within-template correlation. Real "
             "cells may correlate less (then power is lower, toward the SD 0 rows) or more."),
            ("- H1's model check uses a GLM on H1's 4 cells, not the full §9.1 model, and only "
             "its sign enters; H3's uses the average marginal effect with no-variation "
             "templates at 0. The H1/H3 analysis module is not written yet; it should make "
             "the same choices, or the power stated here does not carry over exactly."),
            "- No exclusions are simulated (§13; luna's 320 validity episodes had none).",
            ("- The power is for the kill-boundary effect Delta_H1 = 10pp. It says nothing "
             "about the size of the real effect."), ""]
    return "\n".join(out)


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------
def _print(name: str, df: pd.DataFrame) -> None:
    print(f"\n=== {name} ===")
    with pd.option_context("display.max_rows", 200, "display.max_columns", 40,
                           "display.width", 250):
        print(df.to_string(index=False, float_format=lambda x: f"{x:,.3f}"))


def _floats(text: str) -> list[float]:
    return [float(x) for x in text.split(",") if x.strip()]


def luna_setups_from_args(args: argparse.Namespace) -> list[LunaSetup]:
    """One LunaSetup per scenario. Each list option gives one value per scenario, in the order
    of --luna-names; a single value applies to every scenario."""
    names = [x.strip() for x in args.luna_names.split(",") if x.strip()]
    lists = {"p_f0_obs": _floats(args.luna_p_f0_obs), "p_f0_der": _floats(args.luna_p_f0_der),
             "p_w0_nr": _floats(args.luna_p_w0_nr), "sd": _floats(args.luna_template_sd),
             "r_shift": _floats(args.luna_r_shift)}
    for field, values in lists.items():
        if len(values) not in (1, len(names)):
            raise SystemExit(f"luna option for {field}: give 1 value or one per scenario "
                             f"({len(names)}: {', '.join(names)})")
    setups = [LunaSetup(name=n, delta_h1=args.luna_delta_h1, delta_h3=args.luna_delta_h3,
                        h3_margin=args.luna_h3_margin, holm_tests=args.luna_holm_tests,
                        **{f: v[i if len(v) > 1 else 0] for f, v in lists.items()})
              for i, n in enumerate(names)]
    for s in setups:
        s.levels()  # raises on a level outside (0, 1)
    return setups


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--reps", type=int, default=200, help="simulated data sets per design cell")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--boot", type=int, default=2000, help="bootstrap resamples (H2)")
    ap.add_argument("--part", choices=("sec10", "h2", "luna", "all"), default="all",
                    help="'all' runs sec10 and h2, as before part luna existed")
    ap.add_argument("--sec10-calibration", choices=("conditional", "marginal", "both"),
                    default="both")
    ap.add_argument("--h2-p0", default=str(H2Setup.p_f0),
                    help="success under F-0 on derived-far cells (comma-separated list allowed)")
    ap.add_argument("--h2-templates", default="30,40,60,80",
                    help="comma-separated template counts for the H2 case")
    ap.add_argument("--h2-holm-steps", type=int, default=H2Setup.holm_steps,
                    help="Holm family size behind the H2 part's 'P_superior_holm' column "
                         "(default 3: H1, H2, H3, as in its committed runs)")
    ap.add_argument("--holm-one-sided-alpha", type=float, default=None,
                    help="also report the one-sided bootstrap test at this alpha, the worst "
                         "Holm step (D26: 0.05 / 4 = 0.0125)")
    ap.add_argument("--h2-observed-divisor", type=int, default=None,
                    help="also simulate observed-far cells on ceil(T_d / this) templates "
                         "(D11 option A: 3)")
    luna = ap.add_argument_group(
        "part luna", "luna's H1 and H3 (part 3 of the module docstring). The list options take "
        "one value per scenario, in --luna-names order; the first is the primary scenario.")
    luna.add_argument("--luna-names", default=f"{LUNA_PRIMARY.name},{LUNA_PESSIMISTIC.name}")
    for flag, field, help_ in (
            ("--luna-p-f0-obs", "p_f0_obs", "F-0 success on observed-far (R and NR)"),
            ("--luna-p-f0-der", "p_f0_der", "F-0 success on derived-NR-far"),
            ("--luna-p-w0-nr", "p_w0_nr", "W-0 success on observed-far-NR (no memory)"),
            ("--luna-template-sd", "sd", "template random-intercept SD, logit scale"),
            ("--luna-r-shift", "r_shift", "F-0 success on observed-far-R minus on -NR")):
        a, b = getattr(LUNA_PRIMARY, field), getattr(LUNA_PESSIMISTIC, field)
        luna.add_argument(flag, default=f"{a:g}" if a == b else f"{a:g},{b:g}", help=help_)
    luna.add_argument("--luna-delta-h1", type=float, default=LUNA_PRIMARY.delta_h1,
                      help="true Delta_H1 (PREREG §4.2: 10pp)")
    luna.add_argument("--luna-delta-h3", type=float, default=LUNA_PRIMARY.delta_h3,
                      help="true Delta_H3 (PREREG §4.2: 0)")
    luna.add_argument("--luna-h3-margin", type=float, default=LUNA_PRIMARY.h3_margin,
                      help="H3's non-inferiority bound (PREREG §3 H3: 5pp)")
    luna.add_argument("--luna-holm-tests", type=int, default=LUNA_PRIMARY.holm_tests,
                      help="Holm family size (2: H1 and H3, decided 2026-10-06)")
    luna.add_argument("--luna-templates", default=",".join(map(str, LUNA_TEMPLATES)))
    luna.add_argument("--luna-boot", type=int, default=LUNA_BOOT,
                      help="bootstrap resamples per simulated sweep (PREREG §9.1: 10,000)")
    luna.add_argument("--luna-sensitivity-templates", default="100,150,200",
                      help="template counts of the one-at-a-time sensitivity rows ('' = none)")
    luna.add_argument("--luna-sensitivity-sd", default="0.5,1.5,2",
                      help="extra template SDs for the sensitivity rows")
    luna.add_argument("--luna-validity-glob", default=LUNA_VALIDITY_GLOB,
                      help="luna's validity episodes, for the measured template SD ('' = skip)")
    ap.add_argument("--engine", choices=("fast", "statsmodels"), default="fast",
                    help="FE-logit implementation (identical model; 'fast' is checked against "
                         "statsmodels in the tests)")
    ap.add_argument("--cluster-correction", choices=CORRECTIONS, default="statsmodels",
                    help="small-sample factor of the cluster-robust SEs (module docstring)")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="default: results/power_sim/<run_id>/")
    ap.add_argument("--no-write", action="store_true", help="print only")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    started = datetime.now(UTC)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    t0 = time.perf_counter()
    tables: dict[str, pd.DataFrame] = {}
    if args.part in ("sec10", "all"):
        cals = ("conditional", "marginal") if args.sec10_calibration == "both" else (
            args.sec10_calibration,)
        tables["sec10_power"] = pd.concat(
            [run_sec10(args.reps, args.seed, calibration=c, engine=args.engine,
                       correction=args.cluster_correction) for c in cals],
            ignore_index=True)
    setups = [H2Setup(p_f0=float(x), holm_steps=args.h2_holm_steps,
                      holm_one_sided_alpha=args.holm_one_sided_alpha,
                      observed_divisor=args.h2_observed_divisor)
              for x in args.h2_p0.split(",") if x.strip()]
    if args.part in ("h2", "all"):
        counts = tuple(int(x) for x in args.h2_templates.split(",") if x.strip())
        tables["h2_sol_power"] = pd.concat(
            [run_h2(args.reps, args.seed, templates=counts, boot=args.boot, setup=s,
                    engine=args.engine, correction=args.cluster_correction) for s in setups],
            ignore_index=True)
    luna_setups = luna_setups_from_args(args)
    sens_setups = luna_sensitivity_setups(luna_setups[0], luna_setups[1:],
                                          tuple(_floats(args.luna_sensitivity_sd)))
    summary = None
    if args.part == "luna":
        counts = tuple(int(x) for x in args.luna_templates.split(",") if x.strip())
        kw = {"boot": args.luna_boot, "engine": args.engine}
        power = pd.concat([run_luna(args.reps, args.seed, templates=counts, setup=s, **kw)
                           for s in luna_setups], ignore_index=True)
        tables["luna_power"] = power
        tables["luna_decision"] = decision = luna_decision(power)
        tables["luna_normal_check"] = normal = luna_normal_check(luna_setups, counts)
        sens_counts = tuple(int(x) for x in args.luna_sensitivity_templates.split(",")
                            if x.strip())
        sens = None
        if sens_counts:
            sens = pd.concat([run_luna(args.reps, args.seed, templates=sens_counts, setup=s,
                                       label=label, **kw) for label, s in sens_setups],
                             ignore_index=True)
            tables["luna_sensitivity"] = sens
        validity = None
        if args.luna_validity_glob:
            paths = sorted(REPO_ROOT.glob(args.luna_validity_glob))
            if paths:
                tables["luna_validity_sd"] = validity = validity_template_sd(paths)
        command = "uv run python -m analysis.power_sim " + " ".join(
            sys.argv[1:] if argv is None else argv)
        summary = luna_summary(power, decision, sens, validity, luna_setups, run_id, command,
                               luna_cost_per_template(), _phase_1a_spent(), normal)
    for name, df in tables.items():
        _print(name, df)
    elapsed = time.perf_counter() - t0
    print(f"\n{elapsed:.1f} s")

    if not args.no_write:
        from common import runmeta

        out = args.out_dir or REPO_ROOT / "results" / "power_sim" / run_id
        out.mkdir(parents=True, exist_ok=True)
        for name, df in tables.items():
            df.to_csv(out / f"{name}.csv", index=False, float_format="%.6g",
                      lineterminator="\n")
        outputs = [f"{n}.csv" for n in tables]
        if summary is not None:
            (out / "summary.md").write_text(summary, encoding="utf-8", newline="\n")
            outputs.append("summary.md")
        config = {**{k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
                  "h2_setup": asdict(setups[0]), "h2_setups": [asdict(s) for s in setups],
                  "template_sd": TEMPLATE_SD, "alpha": ALPHA,
                  "sec10_designs": [asdict(d) for d in SEC10_DESIGNS]}
        if args.part == "luna":
            config.update({"luna_setups": [asdict(s) for s in luna_setups],
                           "luna_sensitivity": [{"label": label, **asdict(s)}
                                                for label, s in sens_setups],
                           "power_target": POWER_TARGET, "luna_T_cap": LUNA_T_CAP})
        meta = runmeta.write_meta(
            out, experiment="power_sim", run_id=run_id, cell_or_config="power_sim_v1",
            config=config, model_requested=None, model_returned=None, reasoning_effort=None,
            reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
            repeat_index=None, seeds=[args.seed],
            started_utc=started.isoformat(timespec="seconds"),
            finished_utc=runmeta.utc_now(), exit_reason="completed", tokens=None, cost_usd=0.0,
            raw_transcript_path=None, outputs=sorted(outputs),
            runtime_s=round(elapsed, 1), paid_calls=0)
        print(f"wrote {out} ({meta.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
