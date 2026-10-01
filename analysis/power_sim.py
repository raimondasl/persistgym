"""Power simulation for PLAN.md §10 (rewritten from its description) plus the sol H2 case.

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

The probability targets are converted to logits either conditionally (the target holds for a
template with intercept 0; ``--calibration conditional``) or marginally (the target is the
population-average success; default for H2, because its estimand is on the probability scale).

Run: ``uv run python -m analysis.power_sim [--reps 200] [--seed 20260930] [--no-write]``
"""

from __future__ import annotations

import argparse
import sys
import time
import warnings
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import optimize, special

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SEED = 20260930
TEMPLATE_SD = 1.0
ALPHA = 0.05

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


def _fe_logit_fast(y, codes, z, max_iter: int = 100, tol: float = 1e-10) -> FitResult:
    """The same model as _fe_logit_statsmodels, by Newton steps with the template intercepts
    profiled out through a Schur complement. Cluster-robust sandwich with statsmodels' default
    small-sample factor G/(G-1) * (N-1)/(N-K) and normal p-values.

    At the MLE every template's intercept score is zero, so the cluster scores only have slope
    components and the slope block of the sandwich is S^-1 B S^-1, with S the Schur complement
    of the intercept block in the Hessian.
    """
    n, k = z.shape
    g = codes.max() + 1
    counts = np.bincount(codes, minlength=g)
    ybar = np.clip(np.bincount(codes, weights=y, minlength=g) / counts, 1e-3, 1 - 1e-3)
    alpha, beta = special.logit(ybar), np.zeros(k)

    def blocks(alpha, beta):
        mu = special.expit(alpha[codes] + z @ beta)
        w, r = mu * (1 - mu), y - mu
        h_aa = np.bincount(codes, weights=w, minlength=g)
        h_ab = np.column_stack([np.bincount(codes, weights=w * z[:, j], minlength=g)
                                for j in range(k)])
        h_bb = (z * w[:, None]).T @ z
        schur = h_bb - h_ab.T @ (h_ab / h_aa[:, None])
        return r, h_aa, h_ab, schur

    for _ in range(max_iter):
        r, h_aa, h_ab, schur = blocks(alpha, beta)
        g_a = np.bincount(codes, weights=r, minlength=g)
        d_b = np.linalg.solve(schur, z.T @ r - h_ab.T @ (g_a / h_aa))
        d_a = (g_a - h_ab @ d_b) / h_aa
        alpha, beta = alpha + d_a, beta + d_b
        if max(np.abs(d_a).max(), np.abs(d_b).max()) < tol:
            break
    else:
        raise FloatingPointError("FE logit did not converge")
    r, _, _, schur = blocks(alpha, beta)
    scores = np.column_stack([np.bincount(codes, weights=r * z[:, j], minlength=g)
                              for j in range(k)])
    s_inv = np.linalg.inv(schur)
    cov = s_inv @ (scores.T @ scores) @ s_inv
    cov *= g / (g - 1) * (n - 1) / (n - (g + k))
    se = np.sqrt(np.diag(cov))
    return beta, se, 2 * special.ndtr(-np.abs(beta / se))


def fe_logit(y: np.ndarray, groups: np.ndarray, slopes: np.ndarray,
             engine: str = "fast") -> FitResult | None:
    """Logistic GLM y ~ template fixed effects + slopes, cluster-robust SEs by template.

    Templates whose outcomes are all 0 or all 1 are dropped first: their fixed effects diverge
    and they carry no information about the slopes. Returns None when the fit fails.
    """
    y, codes, z, n_groups = _informative(y, groups, slopes)
    if n_groups < 2 or len(y) <= n_groups + z.shape[1]:
        return None
    fit = _fe_logit_fast if engine == "fast" else _fe_logit_statsmodels
    try:
        est, se, p = fit(y, codes, z)
    except (np.linalg.LinAlgError, ValueError, FloatingPointError):
        return None
    if not (np.isfinite(est).all() and np.isfinite(se).all() and np.isfinite(p).all()):
        return None
    return est, se, p


def fe_logit_last_coef(y: np.ndarray, groups: np.ndarray, slopes: np.ndarray,
                       engine: str = "fast") -> tuple[float, float, float] | None:
    """(estimate, SE, two-sided p) of the last slope column, or None if the fit fails."""
    fit = fe_logit(y, groups, slopes, engine)
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


def fit_sec10(data: dict[str, np.ndarray], engine: str = "fast"
              ) -> tuple[float, float, float] | None:
    h, x = data["harness"], data["distance"]
    return fe_logit_last_coef(data["y"], data["template"], np.column_stack([h, x, h * x]),
                              engine)


def run_sec10(reps: int, seed: int, *, effects=(0.0, 0.10, 0.20),
              calibration: str = "conditional", engine: str = "fast",
              designs: tuple[Sec10Design, ...] = SEC10_DESIGNS) -> pd.DataFrame:
    rows = []
    seqs = np.random.SeedSequence([seed, 10]).spawn(len(designs) * len(effects))
    for i, (design, effect) in enumerate((d, e) for d in designs for e in effects):
        rng = np.random.default_rng(seqs[i])
        hits = fails = 0
        for _ in range(reps):
            fit = fit_sec10(simulate_sec10(design, effect, rng, calibration=calibration), engine)
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


def h2_glm(y0: np.ndarray, y1: np.ndarray, engine: str = "fast"
           ) -> tuple[float, float, float] | None:
    """Confirmatory model: logit with template and cell fixed effects plus the arm."""
    t, c = y0.shape
    y = np.concatenate([y0.ravel(), y1.ravel()])
    template = np.tile(np.repeat(np.arange(t), c), 2)
    cell = np.tile(np.tile(np.arange(c), t), 2)
    arm = np.repeat([0.0, 1.0], t * c)
    cell_dummies = np.column_stack([(cell == k).astype(float) for k in range(1, c)])
    return fe_logit_last_coef(y, template, np.column_stack([cell_dummies, arm]), engine)


def run_h2(reps: int, seed: int, *, templates=(30, 40, 60, 80), boot: int = 2000,
           setup: H2Setup = DEFAULT_H2, engine: str = "fast") -> pd.DataFrame:
    effects = (0.0, setup.bound)
    holm_level = 1 - ALPHA / setup.holm_steps
    rows = []
    seqs = np.random.SeedSequence([seed, 2]).spawn(len(templates) * len(effects))
    for i, (t, effect) in enumerate((t, e) for t in templates for e in effects):
        rng = np.random.default_rng(seqs[i])
        tost = sup = sup_holm = glm_sup = glm_fail = 0
        estimates, halfwidths = [], []
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
            fit = h2_glm(y0, y1, engine)
            if fit is None:
                glm_fail += 1
            else:
                glm_sup += (fit[2] < ALPHA) and (fit[0] > 0)
            estimates.append(diff.mean())
            halfwidths.append((hi90 - lo90) / 2)
        rows.append({"templates": t, "episodes": 2 * t * setup.cells,
                     "true_effect_pp": effect * 100, "p_F0": setup.p_f0,
                     "calibration": setup.calibration, "reps": reps, "boot": boot,
                     "P_tost_equivalent": tost / reps, "P_superior_95": sup / reps,
                     "P_superior_holm": sup_holm / reps, "P_superior_glm": glm_sup / reps,
                     "glm_failed_fits": glm_fail,
                     "mean_estimate_pp": 100 * float(np.mean(estimates)),
                     "mean_ci90_halfwidth_pp": 100 * float(np.mean(halfwidths))})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------
def _print(name: str, df: pd.DataFrame) -> None:
    print(f"\n=== {name} ===")
    with pd.option_context("display.max_rows", 200, "display.max_columns", 40,
                           "display.width", 250):
        print(df.to_string(index=False, float_format=lambda x: f"{x:,.3f}"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--reps", type=int, default=200, help="simulated data sets per design cell")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--boot", type=int, default=2000, help="bootstrap resamples (H2)")
    ap.add_argument("--part", choices=("sec10", "h2", "all"), default="all")
    ap.add_argument("--sec10-calibration", choices=("conditional", "marginal", "both"),
                    default="both")
    ap.add_argument("--h2-p0", type=float, default=H2Setup.p_f0,
                    help="success under F-0 on derived-far cells")
    ap.add_argument("--h2-templates", default="30,40,60,80",
                    help="comma-separated template counts for the H2 case")
    ap.add_argument("--engine", choices=("fast", "statsmodels"), default="fast",
                    help="FE-logit implementation (identical model; 'fast' is checked against "
                         "statsmodels in the tests)")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="default: results/power_sim/<run_id>/")
    ap.add_argument("--no-write", action="store_true", help="print only")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    started = datetime.now(UTC)
    t0 = time.perf_counter()
    tables: dict[str, pd.DataFrame] = {}
    if args.part in ("sec10", "all"):
        cals = ("conditional", "marginal") if args.sec10_calibration == "both" else (
            args.sec10_calibration,)
        tables["sec10_power"] = pd.concat(
            [run_sec10(args.reps, args.seed, calibration=c, engine=args.engine) for c in cals],
            ignore_index=True)
    setup = H2Setup(p_f0=args.h2_p0)
    if args.part in ("h2", "all"):
        counts = tuple(int(x) for x in args.h2_templates.split(",") if x.strip())
        tables["h2_sol_power"] = run_h2(args.reps, args.seed, templates=counts, boot=args.boot,
                                        setup=setup, engine=args.engine)
    for name, df in tables.items():
        _print(name, df)
    elapsed = time.perf_counter() - t0
    print(f"\n{elapsed:.1f} s")

    if not args.no_write:
        from common import runmeta

        run_id = started.strftime("%Y%m%dT%H%M%SZ")
        out = args.out_dir or REPO_ROOT / "results" / "power_sim" / run_id
        out.mkdir(parents=True, exist_ok=True)
        for name, df in tables.items():
            df.to_csv(out / f"{name}.csv", index=False, float_format="%.6g",
                      lineterminator="\n")
        config = {**{k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
                  "h2_setup": asdict(setup), "template_sd": TEMPLATE_SD, "alpha": ALPHA,
                  "sec10_designs": [asdict(d) for d in SEC10_DESIGNS]}
        meta = runmeta.write_meta(
            out, experiment="power_sim", run_id=run_id, cell_or_config="power_sim_v1",
            config=config, model_requested=None, model_returned=None, reasoning_effort=None,
            reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
            repeat_index=None, seeds=[args.seed],
            started_utc=started.isoformat(timespec="seconds"),
            finished_utc=runmeta.utc_now(), exit_reason="completed", tokens=None, cost_usd=0.0,
            raw_transcript_path=None, outputs=sorted(f"{n}.csv" for n in tables),
            runtime_s=round(elapsed, 1), paid_calls=0)
        print(f"wrote {out} ({meta.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
