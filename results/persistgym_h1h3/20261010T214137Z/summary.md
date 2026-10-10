# H1 and H3 on gpt-6-luna's PersistGym sweep (PREREG §3 H1, §3 H3; R6)

Computed 2026-10-10T21:41:47+00:00 at commit 0dbff43 (dirty: False) by `uv run python -m analysis.persistgym_h1h3`, from `C:\Users\raimo\persistgym\results` (the runs named with --run). Templates 0-199, repeat 0, 8800 primary episodes. Bootstrap: 10,000 template resamples, percentile intervals, RNG seed SEED + 10 = 4086943125952605544. H1's model-check rule for a non-finite logit-scale Δ_H1: `firth`.

**Status: FINAL.**

## Deviations (§13: listed in every write-up)

- The sweep was closed by the researcher (results/decisions.md, 2026-10-10: luna's sweep closed (PR #55), with its correction of 2026-10-10 (one §13 re-run)); keys with no final record and keys never played are excluded (DESIGN §7.8).

§2.8 accounting check: passed on 3520 window-cell episodes (no far window episode with S_verbatim = 1; S_verbatim equals the drop-oldest replay in every one).

## Confirmatory

### H1: recoverability turns a success penalty into a cost penalty

| Cell (observed, far) | F-0 | W-0 | W-n-0 (alongside) |
|---|---|---|---|
| not recoverable | 1.000 (200/200) | 0.075 (15/200) | 0.285 (57/200) |
| recoverable | 1.000 (200/200) | 1.000 (200/200) | 1.000 (200/200) |

| Quantity (probability scale) | Estimate | 90% CI | 95% CI |
|---|---|---|---|
| Penalty_NR = p(F-0, NR) − p(W-0, NR) | +92.5pp | [+89.5pp, +95.5pp] | [+88.5pp, +96.0pp] |
| Penalty_R = p(F-0, R) − p(W-0, R) | +0.0pp | [+0.0pp, +0.0pp] | [+0.0pp, +0.0pp] |
| **Δ_H1 = Penalty_NR − Penalty_R** | +92.5pp | [+89.5pp, +95.5pp] | [+88.5pp, +96.0pp] |

- One-sided bootstrap test, H0: Δ_H1 ≤ 0: p = 0.0000. Holm (family of 2): rejects.
- Model check (§9.4; the §9.1 GLM, fitted by statsmodels on F-0 and W-0 × 8 task cells; the logit-scale Δ_H1 is its W-0 × R coefficient): undefined (∞ − ∞) (statsmodels stops at 101.31); agrees (> 0): **yes**, read from a Firth-penalized fit of the §9.1 GLM (rule 'firth'). Templates without outcome variation dropped from the GLM: 6.
- **The logit-scale Δ_H1 is not finite:** among the GLM's templates, F-0 observed-nonrec-far: all 1 (194 episodes); F-0 observed-rec-far: all 1 (194 episodes); W-0 observed-rec-far: all 1 (194 episodes). The rule in force is `firth` (`H1_SEPARATION_RULE`; the researcher's ruling of 2026-10-10, module docstring): a Firth-penalized fit of the same model decides: 7.086.
- Sensitivity lines (the rules not in force, ruling of 2026-10-10; they enter no decision): rule `literal`: the model check would agree: no, and H1 would be: inconclusive: the Holm test rejects, but the model check does not agree; rule `probability-scale`: the model check would agree: yes, and H1 would be: supported.
- Logit scale (§9.3): Penalty_NR +∞ (statsmodels stops at 101.31), Penalty_R undefined (∞ − ∞) (statsmodels stops at -0.00), Δ_H1 undefined (∞ − ∞) (statsmodels stops at 101.31).
- Cross-checks (not decisions): power_sim's emulation of the same fit 101.307 (the same sign as statsmodels); power_sim's stand-in (4 cells; W, R, W × R) 53.552 (the same sign as the model check); the §9.1 GLM with W-n-0 as a third harness level (a sensitivity analysis, ruling of 2026-10-10), W-0 × R undefined (∞ − ∞) (statsmodels stops at 103.83) (the same sign as the model check).
- Bayesian GLMM sensitivity (§9.1; bambi, template random intercepts, every template kept; not a decision): W-0 × R posterior median 5.253, 90% interval [2.857, 7.523], P(> 0) = 1.000; R-hat 1.002 (largest over the parameters 1.008), bulk ESS 2261; the same sign as the model check.
- **H1: supported.** Supported needs the Holm test and the model check (§9.4): yes and yes.
- **Kill rule** (Δ_H1 < 10pp and the 90% upper bound < 15pp): **does not fire**.
- Cells with no outcome variation in the GLM (quasi-separation; their coefficients are large and finite only by the stopping rule): F-0 derived-nonrec-near: all 1 (194 episodes); F-0 derived-rec-far: all 1 (194 episodes); F-0 derived-rec-near: all 1 (194 episodes); F-0 observed-nonrec-far: all 1 (194 episodes); F-0 observed-nonrec-near: all 1 (194 episodes); F-0 observed-rec-far: all 1 (194 episodes); F-0 observed-rec-near: all 1 (194 episodes); W-0 derived-rec-far: all 1 (194 episodes); W-0 derived-rec-near: all 1 (194 episodes); W-0 observed-nonrec-near: all 1 (194 episodes); W-0 observed-rec-far: all 1 (194 episodes); W-0 observed-rec-near: all 1 (194 episodes).

H1's predictions (point estimates, §3 H1):

| Prediction | Value | Met |
|---|---|---|
| Manipulation check: Penalty_NR ≥ 25pp | +92.5pp | yes |
| Recoverable success: \|Penalty_R\| ≤ 5pp | +0.0pp | yes |
| Lookups: mean W-0 / F-0 ≥ 1.30 (observed-far-R) | F-0 none; W-0 − F-0 1.005 [1.000, 1.015] | yes |
| Need-phase tokens: R_need ≥ 1.30 | 1.994 [1.974, 2.007] | yes |

All four met: **yes**. Lookups: F-0 0 in 200 episodes, W-0 201 in 200. Secondary token readings: R_tok 1.062 [1.059, 1.067]; the literal ratio T(W-0, far) / T(F-0, far) 0.896 [0.891, 0.901] (it cannot reach 1.30 by design, D8). Intervals are 90%.

W-n-0 alongside (not tested): penalty against F-0, NR +71.5pp [+66.0pp, +76.5pp], R +0.0pp [+0.0pp, +0.0pp].

### H3: little residual cost of multi-turn structure when the fact survives

| Arm (NR, far; observed and derived pooled) | Success |
|---|---|
| Single-turn control | 1.000 (400/400) |
| F-0 multi-turn | 0.998 (399/400) |

**Δ_H3 = p(single-turn) − p(F-0) = +0.2pp**, 90% CI [+0.0pp, +0.7pp], 95% CI [+0.0pp, +0.7pp].

- Prediction (90% upper bound ≤ 5pp, §3 H3): **holds** (reported either way).
- One-sided bootstrap test, H0: Δ_H3 ≥ 5pp: p = 0.0000. Holm (family of 2): rejects.
- Model check (§9.4, as registered: a statsmodels binomial GLM with template fixed effects and the arm on the H3 cells; its probability-scale Δ_H3 is the arm's average marginal effect over all 400 (template, task cell) pairs, a template without outcome variation adding 0, reading 15): n/a; below 5pp: **no**. Over the 0 pairs of the templates with outcome variation only: n/a.
- Logit scale (§9.3): the arm coefficient n/a; no outcome variation: single-turn: all 1 (2 episodes).
- Sensitivity (not a decision): power_sim's model (template fixed effects + derived term + arm), AME n/a; below 5pp: no.
- **H3: inconclusive: the Holm test rejects, but the model check does not agree.** Supported needs the Holm test and the model check (§9.4): yes and no.

Per cell: observed-nonrec-far: single-turn 1.000 (200/200), F-0 1.000 (200/200), difference +0.0pp [+0.0pp, +0.0pp]; derived-nonrec-far: single-turn 1.000 (200/200), F-0 0.995 (199/200), difference +0.5pp [+0.0pp, +1.5pp].

### Multiplicity (§9.4; R6 change 9)

| Test | One-sided p | Holm-adjusted p, family of 2 | Rejects | Family of 4 (sensitivity) | Rejects |
|---|---|---|---|---|---|
| H1 (H0: Δ_H1 ≤ 0) | 0.0000 | 0.0000 | yes | 0.0000 | yes |
| H3 (H0: Δ_H3 ≥ 5pp) | 0.0000 | 0.0000 | yes | 0.0000 | yes |

The family of 2 is the researcher's decision of 2026-10-06 (R6 change 9); the family of 4 counts H2's two tests, not run (R3), as not rejected. Supported in the family of 4: H1 yes, H3 no.

Achieved power at T = 200, worst Holm step (one-sided 0.025), P(supported), from `results/power_sim/20261010T030442Z/luna_decision.csv`: primary: H1 0.647, H3 0.781; pessimistic: H1 0.438, H3 0.443. Simulated with F-0 observed-far success at 0.95 (primary) and 0.85 (pessimistic) and with power_sim's model checks (H1: a 4-cell stand-in read through the stopping rule; H3: template fixed effects + derived term + arm), not the ones used here; with F-0 at its ceiling, H1's model check meets separation and is read by the rule in force (`firth`), which power_sim did not simulate, so P(supported) may differ from the values quoted.

## §2.8 accounting by cell (base episodes, repeat 0)

| Cell | Task cell | n | S_planned | S_verbatim 1/0 | S = 1 | Near losses | P(carried) | P(used \| carried) | Rescued, lookup | Rescued, no lookup | Residual at S = 1 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F-0 | observed-nonrec-near | 200 | 1 | 200/0 | 200 | - | - | - | n/a | n/a | 1.000 (200/200) |
| F-0 | observed-nonrec-far | 200 | 1 | 200/0 | 200 | - | - | - | n/a | n/a | 1.000 (200/200) |
| F-0 | observed-rec-near | 200 | 1 | 200/0 | 200 | - | - | - | n/a | n/a | 1.000 (200/200) |
| F-0 | observed-rec-far | 200 | 1 | 200/0 | 200 | - | - | - | n/a | n/a | 1.000 (200/200) |
| F-0 | derived-nonrec-near | 200 | 1 | 200/0 | 200 | - | - | - | n/a | n/a | 1.000 (200/200) |
| F-0 | derived-nonrec-far | 200 | 1 | 200/0 | 200 | - | - | - | n/a | n/a | 0.995 (199/200) |
| F-0 | derived-rec-near | 200 | 1 | 200/0 | 200 | - | - | - | n/a | n/a | 1.000 (200/200) |
| F-0 | derived-rec-far | 200 | 1 | 200/0 | 200 | - | - | - | n/a | n/a | 1.000 (200/200) |
| W-0 | observed-nonrec-near | 200 | 1 | 200/0 | 200 | 0 | - | - | n/a | n/a | 1.000 (200/200) |
| W-0 | observed-nonrec-far | 200 | 0 | 0/200 | 0 | - | - | - | n/a | 0.075 (15/200) | n/a |
| W-0 | observed-rec-near | 200 | 1 | 200/0 | 200 | 0 | - | - | n/a | n/a | 1.000 (200/200) |
| W-0 | observed-rec-far | 200 | 0 | 0/200 | 0 | - | - | - | 1.000 (200/200) | n/a | n/a |
| W-0 | derived-nonrec-near | 200 | 1 | 200/0 | 200 | 0 | - | - | n/a | n/a | 0.995 (199/200) |
| W-0 | derived-nonrec-far | 200 | 0 | 0/200 | 0 | - | - | - | n/a | 0.080 (16/200) | n/a |
| W-0 | derived-rec-near | 200 | 1 | 200/0 | 200 | 0 | - | - | n/a | n/a | 1.000 (200/200) |
| W-0 | derived-rec-far | 200 | 0 | 0/200 | 0 | - | - | - | 1.000 (200/200) | n/a | n/a |
| W-n-0 | observed-nonrec-near | 200 | 1 | 200/0 | 200 | 0 | n/a (0/0) | n/a | n/a | n/a | 1.000 (200/200) |
| W-n-0 | observed-nonrec-far | 200 | 0 | 0/200 | 43 | - | 0.215 (43/200) | 1.000 (43/43) | n/a | 0.089 (14/157) | n/a |
| W-n-0 | observed-rec-near | 200 | 1 | 200/0 | 200 | 0 | n/a (0/0) | n/a | n/a | n/a | 1.000 (200/200) |
| W-n-0 | observed-rec-far | 200 | 0 | 0/200 | 24 | - | 0.120 (24/200) | 1.000 (24/24) | 1.000 (176/176) | n/a | n/a |
| W-n-0 | derived-nonrec-near | 200 | 1 | 200/0 | 200 | 0 | n/a (0/0) | n/a | n/a | n/a | 1.000 (200/200) |
| W-n-0 | derived-nonrec-far | 200 | 0 | 0/200 | 39 | - | 0.195 (39/200) | 1.000 (39/39) | n/a | 0.087 (14/161) | n/a |
| W-n-0 | derived-rec-near | 200 | 1 | 200/0 | 200 | 0 | n/a (0/0) | n/a | n/a | n/a | 1.000 (200/200) |
| W-n-0 | derived-rec-far | 200 | 0 | 0/200 | 24 | - | 0.120 (24/200) | 1.000 (24/24) | 1.000 (176/176) | n/a | n/a |
| Σ-n-0 (expl.) | observed-nonrec-near | 200 | unset | 200/0 | 200 | - | n/a (0/0) | n/a | n/a | n/a | 1.000 (200/200) |
| Σ-n-0 (expl.) | observed-nonrec-far | 200 | 0 | 0/200 | 77 | - | 0.385 (77/200) | 1.000 (77/77) | n/a | 0.073 (9/123) | n/a |
| Σ-n-0 (expl.) | observed-rec-near | 200 | unset | 200/0 | 200 | - | n/a (0/0) | n/a | n/a | n/a | 1.000 (200/200) |
| Σ-n-0 (expl.) | observed-rec-far | 200 | 0 | 0/200 | 62 | - | 0.310 (62/200) | 1.000 (62/62) | 1.000 (138/138) | n/a | n/a |
| Σ-n-0 (expl.) | derived-nonrec-near | 200 | unset | 179/21 | 189 | - | 0.476 (10/21) | 1.000 (10/10) | n/a | 0.545 (6/11) | 0.994 (178/179) |
| Σ-n-0 (expl.) | derived-nonrec-far | 200 | 0 | 0/200 | 184 | - | 0.920 (184/200) | 1.000 (184/184) | n/a | 0.000 (0/16) | n/a |
| Σ-n-0 (expl.) | derived-rec-near | 200 | unset | 179/21 | 186 | - | 0.333 (7/21) | 1.000 (7/7) | 1.000 (5/5) | 1.000 (9/9) | 1.000 (179/179) |
| Σ-n-0 (expl.) | derived-rec-far | 200 | 0 | 0/200 | 181 | - | 0.905 (181/200) | 1.000 (181/181) | 1.000 (19/19) | n/a | n/a |

Rescued = success among S_verbatim = 0 (and, in W-n-0 and Σ-n-0, not carried); chance is 0.10. P(carried) is a lower bound: the string match misses paraphrase (§2.8). Near losses are expected, not bugs, and stay in their cell (§13). Σ-n-0 is exploratory (D12, §9.10); its split by `compacted_between` is in h1h3.json.

## Cost outcomes (§9.5): ratio to F-0 in the same task cell

Quasi-Poisson log-link GLM with template fixed effects (§9.5); ratio exp(β) [95% CI]. §9.5 registers the model, not a comparison: each harness cell against F-0 within a task cell is this script's reading 11 (as implemented, not registered).

| Task cell | Outcome | W-0 | W-n-0 | Σ-n-0 (expl.) |
|---|---|---|---|---|
| observed-nonrec-near | total tokens (input + output) | 0.846 [0.841, 0.851] | 0.848 [0.843, 0.853] | 0.609 [0.605, 0.614] |
| observed-nonrec-near | reasoning tokens | 1.046 [1.013, 1.081] | 1.885 [1.751, 2.029] | 2.044 [1.931, 2.163] |
| observed-nonrec-near | lookups | 0 (no events) | 0 (no events) | 0 (no events) |
| observed-nonrec-near | USD, list | 3.431 [3.388, 3.474] | 3.463 [3.423, 3.504] | 1.096 [1.076, 1.117] |
| observed-nonrec-near | USD, billed estimate | 3.431 [3.388, 3.474] | 3.463 [3.423, 3.504] | 1.096 [1.076, 1.117] |
| observed-nonrec-far | total tokens (input + output) | 0.847 [0.842, 0.852] | 0.849 [0.845, 0.854] | 0.611 [0.606, 0.615] |
| observed-nonrec-far | reasoning tokens | 3.695 [3.545, 3.851] | 4.311 [4.124, 4.505] | 3.835 [3.643, 4.037] |
| observed-nonrec-far | lookups | 0 (no events) | 0 (no events) | 0 (no events) |
| observed-nonrec-far | USD, list | 3.669 [3.625, 3.713] | 3.717 [3.676, 3.758] | 1.142 [1.125, 1.160] |
| observed-nonrec-far | USD, billed estimate | 3.669 [3.625, 3.713] | 3.717 [3.676, 3.758] | 1.142 [1.125, 1.160] |
| observed-rec-near | total tokens (input + output) | 0.843 [0.838, 0.849] | 0.846 [0.840, 0.851] | 0.608 [0.603, 0.613] |
| observed-rec-near | reasoning tokens | 1.031 [0.997, 1.065] | 1.564 [1.480, 1.652] | 1.865 [1.779, 1.957] |
| observed-rec-near | lookups | 0.111 [0.009, 1.395] | 0.333 [0.027, 4.186] | 0 (no events) |
| observed-rec-near | USD, list | 3.419 [3.382, 3.457] | 3.430 [3.394, 3.467] | 1.036 [1.012, 1.060] |
| observed-rec-near | USD, billed estimate | 3.419 [3.382, 3.457] | 3.430 [3.394, 3.467] | 1.036 [1.012, 1.060] |
| observed-rec-far | total tokens (input + output) | 0.896 [0.890, 0.902] | 0.893 [0.887, 0.899] | 0.634 [0.629, 0.638] |
| observed-rec-far | reasoning tokens | 1.149 [1.116, 1.183] | 1.714 [1.614, 1.821] | 2.254 [2.147, 2.367] |
| observed-rec-far | lookups | n/a (no F-0 events) | n/a (no F-0 events) | n/a (no F-0 events) |
| observed-rec-far | USD, list | 3.991 [3.953, 4.031] | 3.990 [3.953, 4.028] | 1.094 [1.075, 1.115] |
| observed-rec-far | USD, billed estimate | 3.991 [3.953, 4.031] | 3.990 [3.953, 4.028] | 1.094 [1.075, 1.115] |
| derived-nonrec-near | total tokens (input + output) | 0.846 [0.841, 0.851] | 0.848 [0.844, 0.853] | 0.610 [0.606, 0.614] |
| derived-nonrec-near | reasoning tokens | 1.025 [0.996, 1.054] | 1.786 [1.705, 1.872] | 1.944 [1.840, 2.055] |
| derived-nonrec-near | lookups | 0 (no events) | 0 (no events) | 0 (no events) |
| derived-nonrec-near | USD, list | 3.808 [3.758, 3.858] | 4.325 [4.251, 4.401] | 1.168 [1.125, 1.212] |
| derived-nonrec-near | USD, billed estimate | 3.808 [3.758, 3.858] | 4.325 [4.251, 4.401] | 1.168 [1.125, 1.212] |
| derived-nonrec-far | total tokens (input + output) | 0.847 [0.842, 0.852] | 0.850 [0.845, 0.855] | 0.611 [0.607, 0.615] |
| derived-nonrec-far | reasoning tokens | 3.076 [2.950, 3.209] | 3.430 [3.267, 3.601] | 2.471 [2.344, 2.604] |
| derived-nonrec-far | lookups | 0 (no events) | 0 (no events) | 0 (no events) |
| derived-nonrec-far | USD, list | 2.926 [2.875, 2.979] | 3.505 [3.450, 3.561] | 1.154 [1.144, 1.163] |
| derived-nonrec-far | USD, billed estimate | 2.926 [2.875, 2.979] | 3.505 [3.450, 3.561] | 1.154 [1.144, 1.163] |
| derived-rec-near | total tokens (input + output) | 0.847 [0.843, 0.852] | 0.849 [0.844, 0.853] | 0.612 [0.607, 0.616] |
| derived-rec-near | reasoning tokens | 1.056 [1.022, 1.091] | 1.615 [1.559, 1.674] | 1.834 [1.756, 1.915] |
| derived-rec-near | lookups | n/a (no F-0 events) | n/a (no F-0 events) | n/a (no F-0 events) |
| derived-rec-near | USD, list | 3.835 [3.789, 3.882] | 4.250 [4.177, 4.323] | 1.070 [1.028, 1.115] |
| derived-rec-near | USD, billed estimate | 3.835 [3.789, 3.882] | 4.250 [4.177, 4.323] | 1.070 [1.028, 1.115] |
| derived-rec-far | total tokens (input + output) | 0.893 [0.887, 0.899] | 0.891 [0.885, 0.897] | 0.613 [0.608, 0.618] |
| derived-rec-far | reasoning tokens | 1.097 [1.061, 1.134] | 1.691 [1.621, 1.763] | 2.256 [2.155, 2.362] |
| derived-rec-far | lookups | 22.667 [12.060, 42.602] | 20.333 [10.736, 38.510] | 2.333 [1.095, 4.971] |
| derived-rec-far | USD, list | 3.334 [3.292, 3.377] | 3.755 [3.703, 3.807] | 1.139 [1.128, 1.150] |
| derived-rec-far | USD, billed estimate | 3.334 [3.292, 3.377] | 3.755 [3.703, 3.807] | 1.139 [1.128, 1.150] |

## Success by cell (repeat 0; descriptive)

Descriptive, not tests (§9.10): each cell's success rate. Only the contrasts above are registered; the restated-at-need control (the memory-free ceiling, §4.3), the W cells' derived and near cells and the Σ-n-0 cells (exploratory, D12) enter no registered test here.

| Run kind | Task cell | Success | Content failures |
|---|---|---|---|
| F-0 | observed-nonrec-near | 1.000 (200/200) | - |
| F-0 | observed-nonrec-far | 1.000 (200/200) | - |
| F-0 | observed-rec-near | 1.000 (200/200) | - |
| F-0 | observed-rec-far | 1.000 (200/200) | - |
| F-0 | derived-nonrec-near | 1.000 (200/200) | - |
| F-0 | derived-nonrec-far | 0.995 (199/200) | - |
| F-0 | derived-rec-near | 1.000 (200/200) | - |
| F-0 | derived-rec-far | 1.000 (200/200) | - |
| W-0 | observed-nonrec-near | 1.000 (200/200) | - |
| W-0 | observed-nonrec-far | 0.075 (15/200) | - |
| W-0 | observed-rec-near | 1.000 (200/200) | - |
| W-0 | observed-rec-far | 1.000 (200/200) | - |
| W-0 | derived-nonrec-near | 0.995 (199/200) | - |
| W-0 | derived-nonrec-far | 0.080 (16/200) | - |
| W-0 | derived-rec-near | 1.000 (200/200) | - |
| W-0 | derived-rec-far | 1.000 (200/200) | - |
| W-n-0 | observed-nonrec-near | 1.000 (200/200) | - |
| W-n-0 | observed-nonrec-far | 0.285 (57/200) | - |
| W-n-0 | observed-rec-near | 1.000 (200/200) | - |
| W-n-0 | observed-rec-far | 1.000 (200/200) | - |
| W-n-0 | derived-nonrec-near | 1.000 (200/200) | - |
| W-n-0 | derived-nonrec-far | 0.265 (53/200) | - |
| W-n-0 | derived-rec-near | 1.000 (200/200) | - |
| W-n-0 | derived-rec-far | 1.000 (200/200) | - |
| Σ-n-0 (expl.) | observed-nonrec-near | 1.000 (200/200) | - |
| Σ-n-0 (expl.) | observed-nonrec-far | 0.430 (86/200) | - |
| Σ-n-0 (expl.) | observed-rec-near | 1.000 (200/200) | - |
| Σ-n-0 (expl.) | observed-rec-far | 1.000 (200/200) | - |
| Σ-n-0 (expl.) | derived-nonrec-near | 0.970 (194/200) | - |
| Σ-n-0 (expl.) | derived-nonrec-far | 0.920 (184/200) | - |
| Σ-n-0 (expl.) | derived-rec-near | 1.000 (200/200) | - |
| Σ-n-0 (expl.) | derived-rec-far | 1.000 (200/200) | - |
| F-0 restated-at-need | observed-nonrec-near | 1.000 (200/200) | - |
| F-0 restated-at-need | observed-nonrec-far | 1.000 (200/200) | - |
| F-0 restated-at-need | observed-rec-near | 1.000 (200/200) | - |
| F-0 restated-at-need | observed-rec-far | 1.000 (200/200) | - |
| F-0 restated-at-need | derived-nonrec-near | 1.000 (200/200) | - |
| F-0 restated-at-need | derived-nonrec-far | 1.000 (200/200) | - |
| F-0 restated-at-need | derived-rec-near | 1.000 (200/200) | - |
| F-0 restated-at-need | derived-rec-far | 1.000 (200/200) | - |
| single-turn control | observed-nonrec-near | 1.000 (200/200) | - |
| single-turn control | observed-nonrec-far | 1.000 (200/200) | - |
| single-turn control | derived-nonrec-near | 1.000 (200/200) | - |
| single-turn control | derived-nonrec-far | 1.000 (200/200) | - |

## Exclusions and duplicates (§13; DESIGN §7.8)

| Run kind | Task cell | Keys | Never played | Echo excluded | Transport excluded | No final record (closed) | Pending | Dropped duplicates |
|---|---|---|---|---|---|---|---|---|
| F-0 | observed-nonrec-near | 200 | 0 | 0 | 0 | 0 | 0 | 1 |
| F-0 | observed-nonrec-far | 200 | 0 | 0 | 0 | 0 | 0 | 1 |
| F-0 | observed-rec-near | 200 | 0 | 0 | 0 | 0 | 0 | 1 |
| F-0 | observed-rec-far | 200 | 0 | 0 | 0 | 0 | 0 | 1 |
| F-0 | derived-nonrec-near | 200 | 0 | 0 | 0 | 0 | 0 | 1 |
| F-0 | derived-rec-near | 200 | 0 | 0 | 0 | 0 | 0 | 1 |
| F-0 | derived-rec-far | 200 | 0 | 0 | 0 | 0 | 0 | 1 |

## Repeats (§2.9; descriptive, not in any primary result)

| Run kind | Episode pairs | Agreement | Success at repeat 0 only | at repeat 1 only |
|---|---|---|---|---|
| F-0 | 160 | 1.000 | 0 | 0 |
| W-0 | 160 | 0.975 | 1 | 3 |
| W-n-0 | 160 | 0.906 | 11 | 4 |
| Σ-n-0 | 160 | 0.963 | 4 | 2 |
| F-0 restated-at-need | 160 | 1.000 | 0 | 0 |
| single-turn control | 80 | 1.000 | 0 | 0 |

## Runs

Model strings returned: `gpt-6-luna` (8800).

| Run | Cell | Variants | Repeat | Started | Exit | Records | Counted |
|---|---|---|---|---|---|---|---|
| `20261010T055742Z-F-0-gpt-6-luna` | F-0 | base | 0 | 2026-10-10T05:57:44+00:00 | COMPLETED | 1600 | 1599 |
| `20261010T073840Z-W-0-gpt-6-luna` | W-0 | base | 0 | 2026-10-10T07:38:42+00:00 | COMPLETED | 1600 | 1600 |
| `20261010T084438Z-W-n-0-gpt-6-luna` | W-n-0 | base | 0 | 2026-10-10T08:44:41+00:00 | COMPLETED | 1600 | 1600 |
| `20261010T100804Z-sigma-n-0-gpt-6-luna` | Σ-n-0 | base | 0 | 2026-10-10T10:08:06+00:00 | COMPLETED | 1600 | 1600 |
| `20261010T113553Z-F-0-gpt-6-luna` | F-0 | restated | 0 | 2026-10-10T11:35:56+00:00 | COMPLETED | 1600 | 1600 |
| `20261010T125241Z-single-turn-gpt-6-luna` | single-turn | base | 0 | 2026-10-10T12:52:44+00:00 | COMPLETED | 800 | 800 |
| `20261010T125444Z-F-0-gpt-6-luna-repeat1` | F-0 | base | 1 | 2026-10-10T12:54:46+00:00 | COMPLETED | 160 | 160 |
| `20261010T130303Z-W-0-gpt-6-luna-repeat1` | W-0 | base | 1 | 2026-10-10T13:03:05+00:00 | COMPLETED | 160 | 160 |
| `20261010T131136Z-W-n-0-gpt-6-luna-repeat1` | W-n-0 | base | 1 | 2026-10-10T13:11:39+00:00 | COMPLETED | 160 | 160 |
| `20261010T132132Z-sigma-n-0-gpt-6-luna-repeat1` | Σ-n-0 | base | 1 | 2026-10-10T13:21:35+00:00 | COMPLETED | 160 | 160 |
| `20261010T133022Z-F-0-gpt-6-luna-repeat1` | F-0 | restated | 1 | 2026-10-10T13:30:24+00:00 | COMPLETED | 160 | 160 |
| `20261010T133738Z-single-turn-gpt-6-luna-repeat1` | single-turn | base | 1 | 2026-10-10T13:37:40+00:00 | COMPLETED | 80 | 80 |
| `20261010T202127Z-F-0-gpt-6-luna` | F-0 | base | 0 | 2026-10-10T20:21:29+00:00 | COMPLETED | 8 | 1 |
Re-run and continuation links (--rerun): `20261010T202127Z-F-0-gpt-6-luna` of `20261010T055742Z-F-0-gpt-6-luna`.

## What it does not show

- **Not a model comparison.** One model, gpt-6-luna, at medium effort on Flex, with no dated snapshot (returned: `gpt-6-luna`). Nothing here ranks models or vendors; the effects are against task properties (recoverability, distance).
- **PersistGym is synthetic.** The results are not claimed to transfer to coding agents, ARC or real tasks. Window effects at S = 0 are mechanical, not findings in themselves: Penalty_NR is a manipulation check, and the confirmatory quantity is the difference of penalties.
- **Non-inferiority is not absence.** Where H3's bound holds, it says the single-prompt arm is at most 5pp ahead at the stated confidence, not that the multi-turn structure costs nothing. A result that is neither supported nor killed is inconclusive, not "no effect"; the achieved power at the worst Holm step was primary: H1 0.647, H3 0.781; pessimistic: H1 0.438, H3 0.443 (H1 at Δ_H1 = 10pp, H3 at Δ_H3 = 0), simulated with F-0 observed-far success at 0.95 (primary) and 0.85 (pessimistic) and with power_sim's model checks, so it may overstate P(supported) if F-0 sits at its ceiling (H1's model check, above).
- **H3's control favours itself a little.** It uses the oracle's routine replies, so its evidence-to-need gaps are slightly shorter than with real replies (§3 H3).
- **R_need reinterprets PLAN's "total tokens"** (D8): it follows need-phase calls and is driven largely by the same behaviour as the lookups prediction; the literal episode ratio cannot reach 1.30 by design.
- **P(carried) is a lower bound** (string match misses paraphrased carry), and Σ-cell results are exploratory (D12).
- **Not run:** H2 (stopped under R3), sol's replication of H1 (R6), the failure labels (R6).
- **Costs are period-specific:** provider-reported tokens at the prices checked on 2026-09-29/30, Flex tier.
