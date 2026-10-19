# H1 and H3 on claude-haiku-5-5's PersistGym runs: R8's replication (PREREG §17.8)

Computed 2026-10-19T00:32:54+00:00 at commit 19ea535 (dirty: False) by `uv run python -m analysis.persistgym_h1h3 --model claude-haiku-5-5`, from `results` (the runs named with --run). Templates 0-199, repeat 0, 5600 primary episodes. Bootstrap: 10,000 template resamples, percentile intervals, RNG seed SEED + 10 = 4086943125952605544. H1's model-check rule for a non-finite logit-scale Δ_H1: `firth`.

**Status: FINAL.**

**A replication** (PREREG §17.8, amendment R8), reported in full whatever the outcome: every H1 and H3 quantity of §3 is computed on claude-haiku-5-5's episodes (experiment `persistgym_haiku`, cells F-0, W-0, the restated-at-need control and the single-turn control) exactly as on luna's, with the same predictions, thresholds and model checks. Its tests are outside luna's Holm family: unadjusted one-sided bootstrap p-values and the model checks, with no confirmatory label. luna stays primary (`results/persistgym_h1h3/20261010T232227Z/`), and these episodes are never pooled with luna's.

**Pre-specified rules** (fixed for luna on 2026-10-10, after luna's data and before any Haiku data; R8): the §9.1 GLM's harness levels are F-0 and W-0 on all 8 task cells, with W-n-0 as a third level in a sensitivity fit if it runs; H1's model check reads a Firth-penalized fit when the logit-scale Δ_H1 is not finite, with max_iter 1,000; H3's model check is fitted even when only one template has outcome variation; the Bayesian GLMM uses bambi's default priors, 4 chains × 1,000 draws after 1,000 tuning steps; the seeds are luna's: bootstrap SEED + 10 and Bayesian SEED + 11.

**W-n-0: pre-registered, not run (budget)** (R8's size rule; `registered.HAIKU_CELLS`).

## Deviations (§13: listed in every write-up)

- The sweep was closed by the researcher (results/decisions.md, 2026-10-18: Haiku's sweep closed (R8) (PR #73)); keys with no final record and keys never played are excluded (DESIGN §7.8).

§2.8 accounting check: passed on 1770 window-cell episodes (no far window episode with S_verbatim = 1; S_verbatim equals the drop-oldest replay in every one). The replay read the Messages transcripts: each turn's reply as the session kept it and W counted it (the empty text for a refusal). A turn with no visible text went back as `(no reply)` and counts 0 tokens; so does a whitespace-only reply, as the session counted it (R8).

## Replication (R8; outside luna's Holm family)

### H1: recoverability turns a success penalty into a cost penalty

| Cell (observed, far) | F-0 | W-0 | W-n-0 (alongside) |
|---|---|---|---|
| not recoverable | 1.000 (200/200) | 0.000 (0/200) | not run |
| recoverable | 0.990 (198/200) | 1.000 (200/200) | not run |

| Quantity (probability scale) | Estimate | 90% CI | 95% CI |
|---|---|---|---|
| Penalty_NR = p(F-0, NR) − p(W-0, NR) | +100.0pp | [+100.0pp, +100.0pp] | [+100.0pp, +100.0pp] |
| Penalty_R = p(F-0, R) − p(W-0, R) | -1.0pp | [-2.5pp, +0.0pp] | [-2.5pp, +0.0pp] |
| **Δ_H1 = Penalty_NR − Penalty_R** | +101.0pp | [+100.0pp, +102.5pp] | [+100.0pp, +102.5pp] |

- One-sided bootstrap test, H0: Δ_H1 ≤ 0: p = 0.0000. Unadjusted at one-sided 0.05 (outside luna's Holm family, R8): rejects.
- Model check (§9.4; the §9.1 GLM, fitted by statsmodels on F-0 and W-0 × 8 task cells; the logit-scale Δ_H1 is its W-0 × R coefficient): +∞ (statsmodels stops at 104.64); agrees (> 0): **yes**, read from a Firth-penalized fit of the §9.1 GLM (rule 'firth'). Templates without outcome variation dropped from the GLM: 0.
- **The logit-scale Δ_H1 is not finite:** among the GLM's templates, F-0 observed-nonrec-far: all 1 (200 episodes); W-0 observed-nonrec-far: all 0 (200 episodes); W-0 observed-rec-far: all 1 (200 episodes). The rule in force is `firth` (`H1_SEPARATION_RULE`; the researcher's ruling of 2026-10-10, module docstring; pre-specified for Haiku by R8): a Firth-penalized fit of the same model decides: 8.555.
- Sensitivity lines (the rules not in force, ruling of 2026-10-10; they enter no decision): rule `literal`: the model check would agree: yes, and the replication's label would be: the unadjusted test rejects, and the model check agrees; rule `probability-scale`: the model check would agree: yes, and the replication's label would be: the unadjusted test rejects, and the model check agrees.
- Logit scale (§9.3): Penalty_NR +∞ (statsmodels stops at 80.18), Penalty_R −∞ (statsmodels stops at -24.46), Δ_H1 +∞ (statsmodels stops at 104.64).
- Cross-checks (not decisions): power_sim's emulation of the same fit 109.707 (the same sign as statsmodels); power_sim's stand-in (4 cells; W, R, W × R) 142.309 (the same sign as the model check); the §9.1 GLM with W-n-0 as a third harness level (a sensitivity analysis, ruling of 2026-10-10): not fitted, W-n-0 being pre-registered, not run (budget).
- Bayesian GLMM sensitivity (§9.1; bambi, template random intercepts, every template kept; not a decision): W-0 × R posterior median 8.711, 90% interval [6.901, 10.604], P(> 0) = 1.000; R-hat 1.000 (largest over the parameters 1.005), bulk ESS 2283, 1 divergent transitions after tuning; the same sign as the model check.
- **H1, replication (R8): the unadjusted test rejects, and the model check agrees.** Outside luna's Holm family and with no confirmatory label (R8): it neither confirms nor kills H1, and luna stays primary.
- **Kill reading** (computed as on luna: Δ_H1 < 10pp and the 90% upper bound < 15pp): **does not fire**. H1's kill rule reads luna only (R8), so on Haiku this reading neither kills nor confirms H1.
- Cells with no outcome variation in the GLM (quasi-separation; their coefficients are large and finite only by the stopping rule): F-0 derived-nonrec-far: all 1 (200 episodes); F-0 observed-nonrec-far: all 1 (200 episodes); W-0 derived-nonrec-far: all 0 (200 episodes); W-0 derived-nonrec-near: all 1 (200 episodes); W-0 derived-rec-far: all 1 (200 episodes); W-0 derived-rec-near: all 1 (200 episodes); W-0 observed-nonrec-far: all 0 (200 episodes); W-0 observed-nonrec-near: all 1 (200 episodes); W-0 observed-rec-far: all 1 (200 episodes); W-0 observed-rec-near: all 1 (200 episodes).

H1's predictions (point estimates, §3 H1):

| Prediction | Value | Met |
|---|---|---|
| Manipulation check: Penalty_NR ≥ 25pp | +100.0pp | yes |
| Recoverable success: \|Penalty_R\| ≤ 5pp | -1.0pp | yes |
| Lookups: mean W-0 / F-0 ≥ 1.30 (observed-far-R) | F-0 none; W-0 − F-0 1.000 [1.000, 1.000] | yes |
| Need-phase tokens: R_need ≥ 1.30 | 1.983 [1.957, 2.003] | yes |

All four met: **yes**. Lookups: F-0 0 in 200 episodes, W-0 200 in 200. Secondary token readings: R_tok 1.060 [1.057, 1.063]; the literal ratio T(W-0, far) / T(F-0, far) 0.895 [0.891, 0.900] (it cannot reach 1.30 by design, D8). Intervals are 90%.

W-n-0 alongside: pre-registered, not run (budget) (R8's size rule).

### H3: little residual cost of multi-turn structure when the fact survives

| Arm (NR, far; observed and derived pooled) | Success |
|---|---|
| Single-turn control | 0.998 (399/400) |
| F-0 multi-turn | 1.000 (400/400) |

**Δ_H3 = p(single-turn) − p(F-0) = -0.2pp**, 90% CI [-0.7pp, +0.0pp], 95% CI [-0.7pp, +0.0pp].

- Prediction (90% upper bound ≤ 5pp, §3 H3): **holds** (reported either way).
- One-sided bootstrap test, H0: Δ_H3 ≥ 5pp: p = 0.0000. Unadjusted at one-sided 0.05 (outside luna's Holm family, R8): rejects.
- Model check (§9.4, as registered: a statsmodels binomial GLM with template fixed effects and the arm on the H3 cells; its probability-scale Δ_H3 is the arm's average marginal effect over all 400 (template, task cell) pairs, a template without outcome variation adding 0, reading 15): -0.2pp; below 5pp: **yes**. Over the 2 pairs of the templates with outcome variation only: -50.0pp. Templates with outcome variation: 1. With one, the model is saturated in it, so its AME is the observed Δ_H3 by construction and the check adds nothing beyond the bootstrap's point estimate; the AME over that template's pairs is its own observed difference; no cluster-robust SE.
- Logit scale (§9.3): the arm coefficient −∞ (statsmodels stops at -20.57); no outcome variation: F-0: all 1 (2 episodes).
- Sensitivity (not a decision): power_sim's model (template fixed effects + derived term + arm), AME -0.2pp; power_sim's own check (`ps.h3_glm_ame`), which the simulation used, needs two templates with outcome variation and gives no estimate here; below 5pp: yes.
- **H3, replication (R8): the unadjusted test rejects, and the model check agrees.** Outside luna's Holm family and with no confirmatory label (R8): it neither confirms nor refutes H3, and luna stays primary.

Per cell: observed-nonrec-far: single-turn 0.995 (199/200), F-0 1.000 (200/200), difference -0.5pp [-1.5pp, +0.0pp]; derived-nonrec-far: single-turn 1.000 (200/200), F-0 1.000 (200/200), difference +0.0pp [+0.0pp, +0.0pp].

### Multiplicity (§9.4; R8)

| Test | One-sided p, unadjusted | Rejects at 0.05 | Model check agrees | Label |
|---|---|---|---|---|
| H1 (H0: Δ_H1 ≤ 0) | 0.0000 | yes | yes | the unadjusted test rejects, and the model check agrees |
| H3 (H0: Δ_H3 ≥ 5pp) | 0.0000 | yes | yes | the unadjusted test rejects, and the model check agrees |

Outside luna's Holm family (R8; R6 change 9): luna's family stays H1 and H3 on luna, 2 tests, with the family of 4 as its sensitivity analysis, and these tests change neither its size nor its membership. They carry no confirmatory label: they neither confirm nor kill H1 or H3, and H1's kill rule and D38 read luna only.

Power at T = 200 (R8: one-sided 0.05; from `results/power_sim/20261018T232402Z/luna_power.csv`, whose run measured the template SD on `results/persistgym_validity/*-F-0-claude-haiku-5-5/episodes.jsonl`; simulated with power_sim's model checks, H1: a 4-cell stand-in read through the stopping rule, H3: template fixed effects + derived term + arm): primary, F-0 observed-far at 0.95 (NR) and 0.95 (R): the unadjusted test rejects, H1 0.912 and H3 0.864; it rejects and the model check agrees, H1 0.912 and H3 0.864; pessimistic, F-0 observed-far at 0.85 (NR) and 0.85 (R): the unadjusted test rejects, H1 0.530 and H3 0.565; it rejects and the model check agrees, H1 0.530 and H3 0.565. It describes the simulation's scenarios, not these runs, and did not set T (R8): H1's model check meets separation and is read by the rule in force (`firth`), which power_sim did not simulate; H3's cells have one template with outcome variation, where power_sim's own H3 check gives no estimate.

## §2.8 accounting by cell (base episodes, repeat 0)

| Cell | Task cell | n | S_planned | S_verbatim 1/0 | S = 1 | Near losses | P(carried) | P(used \| carried) | Rescued, lookup | Rescued, no lookup | Residual at S = 1 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F-0 | observed-nonrec-near | 200 | 1 | 200/0 | 200 | - | - | - | n/a | n/a | 0.995 (199/200) |
| F-0 | observed-nonrec-far | 200 | 1 | 200/0 | 200 | - | - | - | n/a | n/a | 1.000 (200/200) |
| F-0 | observed-rec-near | 200 | 1 | 200/0 | 200 | - | - | - | n/a | n/a | 0.995 (199/200) |
| F-0 | observed-rec-far | 200 | 1 | 200/0 | 200 | - | - | - | n/a | n/a | 0.990 (198/200) |
| F-0 | derived-nonrec-near | 200 | 1 | 200/0 | 200 | - | - | - | n/a | n/a | 0.990 (198/200) |
| F-0 | derived-nonrec-far | 200 | 1 | 200/0 | 200 | - | - | - | n/a | n/a | 1.000 (200/200) |
| F-0 | derived-rec-near | 200 | 1 | 200/0 | 200 | - | - | - | n/a | n/a | 0.990 (198/200) |
| F-0 | derived-rec-far | 200 | 1 | 200/0 | 200 | - | - | - | n/a | n/a | 0.990 (198/200) |
| W-0 | observed-nonrec-near | 200 | 1 | 200/0 | 200 | 0 | - | - | n/a | n/a | 1.000 (200/200) |
| W-0 | observed-nonrec-far | 200 | 0 | 0/200 | 0 | - | - | - | n/a | 0.000 (0/200) | n/a |
| W-0 | observed-rec-near | 200 | 1 | 200/0 | 200 | 0 | - | - | n/a | n/a | 1.000 (200/200) |
| W-0 | observed-rec-far | 200 | 0 | 0/200 | 0 | - | - | - | 1.000 (200/200) | n/a | n/a |
| W-0 | derived-nonrec-near | 200 | 1 | 200/0 | 200 | 0 | - | - | n/a | n/a | 1.000 (200/200) |
| W-0 | derived-nonrec-far | 200 | 0 | 0/200 | 0 | - | - | - | n/a | 0.000 (0/200) | n/a |
| W-0 | derived-rec-near | 200 | 1 | 200/0 | 200 | 0 | - | - | n/a | n/a | 1.000 (200/200) |
| W-0 | derived-rec-far | 200 | 0 | 0/200 | 0 | - | - | - | 1.000 (200/200) | n/a | n/a |

Rescued = success among S_verbatim = 0; chance is 0.10. Near losses are expected, not bugs, and stay in their cell (§13).

## Cost outcomes (§9.5): ratio to F-0 in the same task cell

Quasi-Poisson log-link GLM with template fixed effects (§9.5); ratio exp(β) [95% CI]. §9.5 registers the model, not a comparison: each harness cell against F-0 within a task cell is this script's reading 11 (as implemented, not registered).

| Task cell | Outcome | W-0 |
|---|---|---|
| observed-nonrec-near | total tokens (input + output) | 0.846 [0.841, 0.851] |
| observed-nonrec-near | reasoning tokens | 1.070 [0.985, 1.163] |
| observed-nonrec-near | lookups | 0 (no events) |
| observed-nonrec-near | USD, list | 3.339 [3.313, 3.366] |
| observed-nonrec-near | USD, billed estimate | 3.339 [3.313, 3.366] |
| observed-nonrec-far | total tokens (input + output) | 0.846 [0.841, 0.851] |
| observed-nonrec-far | reasoning tokens | 1.991 [1.882, 2.107] |
| observed-nonrec-far | lookups | 0 (no events) |
| observed-nonrec-far | USD, list | 3.405 [3.373, 3.436] |
| observed-nonrec-far | USD, billed estimate | 3.405 [3.373, 3.436] |
| observed-rec-near | total tokens (input + output) | 0.845 [0.840, 0.850] |
| observed-rec-near | reasoning tokens | 1.005 [0.940, 1.074] |
| observed-rec-near | lookups | 0.500 [0.045, 5.514] |
| observed-rec-near | USD, list | 3.314 [3.284, 3.344] |
| observed-rec-near | USD, billed estimate | 3.314 [3.284, 3.344] |
| observed-rec-far | total tokens (input + output) | 0.895 [0.890, 0.901] |
| observed-rec-far | reasoning tokens | 1.106 [1.049, 1.167] |
| observed-rec-far | lookups | n/a (no F-0 events) |
| observed-rec-far | USD, list | 3.674 [3.648, 3.700] |
| observed-rec-far | USD, billed estimate | 3.674 [3.648, 3.700] |
| derived-nonrec-near | total tokens (input + output) | 0.846 [0.841, 0.851] |
| derived-nonrec-near | reasoning tokens | 1.073 [1.013, 1.136] |
| derived-nonrec-near | lookups | 0 (no events) |
| derived-nonrec-near | USD, list | 3.412 [3.374, 3.451] |
| derived-nonrec-near | USD, billed estimate | 3.412 [3.374, 3.451] |
| derived-nonrec-far | total tokens (input + output) | 0.847 [0.842, 0.851] |
| derived-nonrec-far | reasoning tokens | 1.794 [1.697, 1.896] |
| derived-nonrec-far | lookups | 0 (no events) |
| derived-nonrec-far | USD, list | 3.393 [3.353, 3.432] |
| derived-nonrec-far | USD, billed estimate | 3.393 [3.353, 3.432] |
| derived-rec-near | total tokens (input + output) | 0.846 [0.841, 0.851] |
| derived-rec-near | reasoning tokens | 1.053 [0.979, 1.134] |
| derived-rec-near | lookups | 1.000 [0.053, 18.915] |
| derived-rec-near | USD, list | 3.405 [3.366, 3.444] |
| derived-rec-near | USD, billed estimate | 3.405 [3.366, 3.444] |
| derived-rec-far | total tokens (input + output) | 0.893 [0.887, 0.900] |
| derived-rec-far | reasoning tokens | 1.147 [1.028, 1.280] |
| derived-rec-far | lookups | 40.000 [10.946, 146.176] |
| derived-rec-far | USD, list | 3.654 [3.617, 3.691] |
| derived-rec-far | USD, billed estimate | 3.654 [3.617, 3.691] |

## Success by cell (repeat 0; descriptive)

Descriptive, not tests (§9.10): each cell's success rate. Only the contrasts above are registered; the restated-at-need control (the memory-free ceiling, §4.3) and the W cells' derived and near cells enter no registered test here. Stopped responses are the step responses that stopped short, by reason (a refusal with its category, `max_output_tokens` at the output cap): each is an invalid action that scores 0 and stays in (R8).

| Run kind | Task cell | Success | Content failures | Stopped responses |
|---|---|---|---|---|
| F-0 | observed-nonrec-near | 0.995 (199/200) | incomplete 1 | refusal:bio 10 (4 episode(s) with a refusal) |
| F-0 | observed-nonrec-far | 1.000 (200/200) | - | refusal:bio 3 (1 episode(s) with a refusal) |
| F-0 | observed-rec-near | 0.995 (199/200) | incomplete 1 | refusal:bio 4 (1 episode(s) with a refusal) |
| F-0 | observed-rec-far | 0.990 (198/200) | incomplete 2 | refusal:bio 8 (3 episode(s) with a refusal) |
| F-0 | derived-nonrec-near | 0.990 (198/200) | incomplete 2 | refusal:bio 10 (4 episode(s) with a refusal) |
| F-0 | derived-nonrec-far | 1.000 (200/200) | - | refusal:bio 12 (3 episode(s) with a refusal) |
| F-0 | derived-rec-near | 0.990 (198/200) | incomplete 2 | refusal:bio 10 (2 episode(s) with a refusal) |
| F-0 | derived-rec-far | 0.990 (198/200) | incomplete 2 | refusal:bio 12 (4 episode(s) with a refusal) |
| W-0 | observed-nonrec-near | 1.000 (200/200) | - | refusal:bio 6 (3 episode(s) with a refusal) |
| W-0 | observed-nonrec-far | 0.000 (0/200) | incomplete 1, unparsed 177 | refusal:bio 7 (3 episode(s) with a refusal) |
| W-0 | observed-rec-near | 1.000 (200/200) | - | refusal:bio 3 (2 episode(s) with a refusal) |
| W-0 | observed-rec-far | 1.000 (200/200) | - | refusal:bio 2 (2 episode(s) with a refusal) |
| W-0 | derived-nonrec-near | 1.000 (200/200) | - | refusal:bio 5 (4 episode(s) with a refusal) |
| W-0 | derived-nonrec-far | 0.000 (0/200) | incomplete 1, unparsed 172 | refusal:bio 14 (4 episode(s) with a refusal) |
| W-0 | derived-rec-near | 1.000 (200/200) | - | refusal:bio 4 (3 episode(s) with a refusal) |
| W-0 | derived-rec-far | 1.000 (200/200) | - | refusal:bio 7 (5 episode(s) with a refusal) |
| F-0 restated-at-need | observed-nonrec-near | 0.990 (198/200) | incomplete 2 | refusal:bio 10 (3 episode(s) with a refusal) |
| F-0 restated-at-need | observed-nonrec-far | 0.995 (199/200) | incomplete 1 | refusal:bio 5 (1 episode(s) with a refusal) |
| F-0 restated-at-need | observed-rec-near | 1.000 (200/200) | - | refusal:bio 5 (2 episode(s) with a refusal) |
| F-0 restated-at-need | observed-rec-far | 1.000 (200/200) | - | refusal:bio 4 (2 episode(s) with a refusal) |
| F-0 restated-at-need | derived-nonrec-near | 0.990 (198/200) | incomplete 2 | refusal:bio 7 (2 episode(s) with a refusal) |
| F-0 restated-at-need | derived-nonrec-far | 1.000 (200/200) | - | refusal:bio 9 (2 episode(s) with a refusal) |
| F-0 restated-at-need | derived-rec-near | 0.995 (199/200) | unparsed 1 | refusal:bio 1 (1 episode(s) with a refusal) |
| F-0 restated-at-need | derived-rec-far | 0.995 (199/200) | incomplete 1 | refusal:bio 7 (4 episode(s) with a refusal) |
| single-turn control | observed-nonrec-near | 1.000 (200/200) | - | - |
| single-turn control | observed-nonrec-far | 0.995 (199/200) | incomplete 1 | refusal:bio 1 (1 episode(s) with a refusal) |
| single-turn control | derived-nonrec-near | 1.000 (200/200) | - | - |
| single-turn control | derived-nonrec-far | 1.000 (200/200) | - | - |

## Exclusions and duplicates (§13; DESIGN §7.8)

| Run kind | Task cell | Keys | Never played | Excluded by the runner | Request-side check (R8) | Transport excluded | No final record (closed) | Pending | Dropped duplicates |
|---|---|---|---|---|---|---|---|---|---|
| W-0 | observed-nonrec-near | 200 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| W-0 | observed-nonrec-far | 200 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |
| W-0 | observed-rec-near | 200 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| W-0 | observed-rec-far | 200 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |
| W-0 | derived-nonrec-near | 200 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| W-0 | derived-nonrec-far | 200 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| W-0 | derived-rec-near | 200 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| single-turn control | observed-nonrec-near | 200 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |
| single-turn control | observed-nonrec-far | 200 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |
| single-turn control | derived-nonrec-far | 200 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |

No echo exclusion (R8): the Messages API echoes neither effort nor a reasoning context. Its substitutes, the payload snapshot tests and the request-side check of every request, act before a request is sent.

## Repeats (§2.9; descriptive, not in any primary result)

| Run kind | Episode pairs | Agreement | Success at repeat 0 only | at repeat 1 only |
|---|---|---|---|---|
| F-0 | 160 | 1.000 | 0 | 0 |
| W-0 | 160 | 1.000 | 0 | 0 |
| F-0 restated-at-need | 160 | 1.000 | 0 | 0 |
| single-turn control | 80 | 1.000 | 0 | 0 |

## Runs

Model strings returned: `claude-haiku-5-5` (5600).

| Run | Cell | Variants | Repeat | Started | Exit | Records | Counted |
|---|---|---|---|---|---|---|---|
| `20261018T141157Z-F-0-claude-haiku-5-5` | F-0 | base | 0 | 2026-10-18T14:11:59+00:00 | COMPLETED | 1600 | 1600 |
| `20261018T144829Z-W-0-claude-haiku-5-5` | W-0 | base | 0 | 2026-10-18T14:48:31+00:00 | ABORTED_API_ERRORS | 1034 | 1017 |
| `20261018T154817Z-W-0-claude-haiku-5-5` | W-0 | base | 0 | 2026-10-18T15:48:20+00:00 | COMPLETED | 8 | 1 |
| `20261018T154918Z-W-0-claude-haiku-5-5` | W-0 | base | 0 | 2026-10-18T15:49:20+00:00 | COMPLETED | 584 | 582 |
| `20261018T162133Z-F-0-claude-haiku-5-5` | F-0 | restated | 0 | 2026-10-18T16:21:35+00:00 | COMPLETED | 1600 | 1600 |
| `20261018T165717Z-single-turn-claude-haiku-5-5` | single-turn | base | 0 | 2026-10-18T16:57:19+00:00 | ABORTED_API_ERRORS | 356 | 354 |
| `20261018T225735Z-single-turn-claude-haiku-5-5` | single-turn | base | 0 | 2026-10-18T22:57:38+00:00 | COMPLETED | 4 | 1 |
| `20261018T225747Z-single-turn-claude-haiku-5-5` | single-turn | base | 0 | 2026-10-18T22:57:48+00:00 | COMPLETED | 4 | 1 |
| `20261018T225838Z-single-turn-claude-haiku-5-5` | single-turn | base | 0 | 2026-10-18T22:58:39+00:00 | COMPLETED | 444 | 444 |
| `20261018T230235Z-F-0-claude-haiku-5-5-repeat1` | F-0 | base | 1 | 2026-10-18T23:02:37+00:00 | COMPLETED | 160 | 160 |
| `20261018T230709Z-W-0-claude-haiku-5-5-repeat1` | W-0 | base | 1 | 2026-10-18T23:07:11+00:00 | COMPLETED | 160 | 160 |
| `20261018T231530Z-F-0-claude-haiku-5-5-repeat1` | F-0 | restated | 1 | 2026-10-18T23:15:32+00:00 | COMPLETED | 160 | 160 |
| `20261018T231953Z-single-turn-claude-haiku-5-5-repeat1` | single-turn | base | 1 | 2026-10-18T23:19:55+00:00 | COMPLETED | 80 | 80 |
Re-run and continuation links (--rerun): `20261018T154817Z-W-0-claude-haiku-5-5` of `20261018T144829Z-W-0-claude-haiku-5-5`, `20261018T154918Z-W-0-claude-haiku-5-5` of `20261018T144829Z-W-0-claude-haiku-5-5`, `20261018T225735Z-single-turn-claude-haiku-5-5` of `20261018T165717Z-single-turn-claude-haiku-5-5`, `20261018T225747Z-single-turn-claude-haiku-5-5` of `20261018T165717Z-single-turn-claude-haiku-5-5`, `20261018T225838Z-single-turn-claude-haiku-5-5` of `20261018T165717Z-single-turn-claude-haiku-5-5`.

## Checks

- 20261018T144829Z-W-0-claude-haiku-5-5: 3 episode(s) stopped at their need step's first call (no recorded need request), so §2.8's replay does not apply to them

## What it does not show

- **Not a model comparison.** One model of a second provider, claude-haiku-5-5, at medium effort on the standard Messages path, with a pinned snapshot ID without a date suffix (R8) (returned: `claude-haiku-5-5`). It ranks neither the models nor their providers: each model's harness effects are reported against task properties (fact kind, recoverability, distance), in the same form for both, and no contrast between the two models is tested or plotted as a ranking. Differences between their effects are described, not tested (§15).
- **One model per provider.** The provider, the model, its training, its reasoning, and the API and serving path all differ at once: a difference between the two models cannot be attributed to any one of them, and agreement says nothing about other models or providers.
- **Not a second confirmation.** Agreement with luna is a replication outside the Holm family. This output holds Haiku's results only, not luna's (`results/persistgym_h1h3/20261010T232227Z/`) and no agreement statement: where the two disagree, both are to be reported side by side and the disagreement stated, neither overriding the other (R8).
- **The same synthetic task family.** Haiku plays luna's episodes, so luna's limits carry over: PersistGym is synthetic, the results are not claimed to transfer to coding agents, ARC or real tasks, and window effects at S = 0 are mechanical (Penalty_NR is a manipulation check). If both models are at the ceiling in H3's cells, H3 says nothing about harder tasks.
- **Non-inferiority is not absence.** Where H3's bound holds, it says the single-prompt arm is at most 5pp ahead at the stated confidence, not that the multi-turn structure costs nothing; and H3's control uses the oracle's routine replies, so its evidence-to-need gaps are slightly shorter than with real replies (§3 H3).
- **R_need reinterprets PLAN's "total tokens"** (D8), and P(carried) is a lower bound (string match misses paraphrased carry).
- **Not blind to luna.** R8's design and its pre-specified rules were chosen with luna's results known.
- **Costs and tokens are not comparable** across the two models: each is in its own provider's tokens and prices (here Anthropic's, at the prices checked on 2026-10-17, with no Flex discount; the standard tier on every response). W and every planned distance stay in project tokens.
- **Thinking is not inspected.** Its display is omitted, so only its token counts are seen, where reported.
- **Not run on this model:** Σ-n-0 and every replay-on cell (R8); W-n-0 (pre-registered, not run (budget)).
