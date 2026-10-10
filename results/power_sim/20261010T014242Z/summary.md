# luna power re-simulation for T (PREREG §4.2, R6 change 6): 20261010T014242Z

Command: `uv run python -m analysis.power_sim --part luna --reps 2000 --cluster-correction clusters`

## What is simulated
One luna data set holds, per template, one repeat-0 outcome in each of 7 cells (§2.9: repeats stay out of the primary analyses): F-0 and W-0 on observed-far-R and -NR (H1), and F-0 and the single-turn control on observed- and derived-NR-far (H3). F-0 on observed-NR-far is shared by both tests. Each data set is analysed as §9.1 and §9.4 will analyse the sweep:
- template-cluster percentile bootstrap on the probability scale with 10,000 resamples, shared by both contrasts (drawn as category counts, which is exact: `category_bootstrap_sums`);
- H1: one-sided bootstrap p = share of resamples with Delta_H1 <= 0; H3: share with Delta_H3 >= 5pp; ties count on the null side;
- "supported" = the test rejects and the model check agrees: for H1 a positive W-0 x R interaction in a template-FE logit on H1's 4 cells, for H3 a GLM Delta_H3 (average marginal effect) below 5pp;
- 2,000 simulated sweeps per scenario, each analysed at every T from 50 to 200 on its first T templates (templates are taken in seed order), so the power curves share random numbers.

**Decision reading.** The frozen rule needs power >= 0.80 for H1 at Delta_H1 = 10pp and for H3 at Delta_H3 = 0. This run reads it conservatively: P(supported) for each test at the worst Holm step (one-sided 0.025 with the family of 2). That is at most the power under the real Holm procedure and at most the unadjusted power; both are reported too.

## Assumptions
| Parameter | primary | pessimistic | Why |
|---|---|---|---|
| F-0 success, observed-far (R and NR); the single-turn control's on observed-NR-far under H3's null (`p_f0_obs`) | 0.95 | 0.85 | No F-0 main-cell success may be used (pilots blinded, §11; no main-split episode exists). luna scored 160/160 on restated-at-need (memory taken out), so the ceiling is near 1; full history must still retrieve one binding from beyond W = 24k tokens. Primary 0.95 sits just below that ceiling; pessimistic 0.85 allows real long-context loss. |
| F-0 success, derived-NR-far (the single-turn control's too, under H3's null) (`p_f0_der`) | 0.9 | 0.8 | Restated derived cells also scored 80/80, so the arithmetic is not the problem; a derived fact needs 2-3 clue bindings and the rule retrieved, so each scenario puts it 5pp below the observed level. |
| W-0 success, observed-far-NR: the no-memory level (`p_w0_nr`) | 0.12 | 0.18 | W-0 has evicted the evidence and has no lookup, as in the fact-withheld control. luna's pooled withheld rate is 19/160 = 0.119 (primary 0.12); 0.18 is the upper end of its 95% Wilson interval. Chance is 0.10 (K = 10). |
| Template random-intercept SD (logit), shared by a template's 7 cells (`sd`) | 1 | 0 | Primary 1.0 is PLAN §10's value and close to the ML estimate from luna's withheld run (table below). Every contrast here is paired within template, so a larger shared SD raises power (sensitivity rows); pessimistic 0, the lower end of that estimate's 95% interval, leaves the cells independent. |
| F-0 success on observed-far-R minus on -NR (`r_shift`) | 0 | 0 | 0: F-0 sees the fact in full history, so lookups should add little. Then W-0's R success = p_w0_nr + delta_h1. |
| True Delta_H1 = Penalty_NR - Penalty_R (`delta_h1`) | 0.1 | 0.1 | 10pp, fixed by §4.2 (the kill boundary). Penalty_NR = p_f0_obs - p_w0_nr is set by the design; Penalty_R = Penalty_NR - 10pp. |
| True Delta_H3 = p(single-turn) - p(F-0), NR-far pooled (`delta_h3`) | 0 | 0 | 0, fixed by §4.2; the bound is 5pp (§3 H3). |
| Holm family size (`holm_tests`) | 2 | 2 | 2 (H1, H3): the researcher's decision of 2026-10-06, R6 change 9; worst step one-sided 0.025. The family of 4 (worst step 0.0125) is a sensitivity column. |

Resulting success levels per cell (population averages; Delta_H1 = (f0_onr - w0_onr) - (f0_or - w0_or), Delta_H3 = mean(st) - mean(f0) over the NR-far cells):

| scenario | f0_onr | w0_onr | f0_or | w0_or | f0_dnr | st_onr | st_dnr |
|---|---|---|---|---|---|---|---|
| primary | 0.950 | 0.120 | 0.950 | 0.220 | 0.900 | 0.950 | 0.900 |
| pessimistic | 0.850 | 0.180 | 0.850 | 0.280 | 0.800 | 0.850 | 0.800 |

## Variance measured in luna's validity runs
Random-intercept logit on F-0, validity templates 0-19 x 8 task cells (`validity_template_sd`; 95% profile-likelihood interval, chi-square 1 df):

| variant | templates | episodes | successes | rate | sd_hat | sd_ci95_low | sd_ci95_high | lr_vs_sd0 | note |
|---|---|---|---|---|---|---|---|---|---|
| restated | 20 | 160 | 160 | 1.000 |  |  |  |  | not identified: every episode had the same outcome |
| withheld | 20 | 160 | 19 | 0.119 | 0.920 | 0.000 | 2.170 | 2.189 |  |

Restated-at-need succeeded in every episode, so it carries no variance. The withheld run measures how guesses cluster by template, not how memory success does, and 20 templates leave the interval wide. It is context for the SD assumption, not a measurement of it.

## Result: the template count

| scenario | reading | T_h1 | T_h3 | T_both | T_set | T_set_by | power_h1_at_T_set | power_h3_at_T_set | all_larger_T_meet |
|---|---|---|---|---|---|---|---|---|---|
| primary | worst Holm step, supported (decision) |  |  |  | 200 | cap (200, R6 change 6) | 0.647 | 0.782 |  |
| primary | worst Holm step, bootstrap test only |  |  |  | 200 | cap (200, R6 change 6) | 0.650 | 0.782 |  |
| primary | Holm over H1 and H3 together, supported |  | 190 |  | 200 | cap (200, R6 change 6) | 0.725 | 0.823 |  |
| primary | unadjusted one-sided 0.05 |  | 170 |  | 200 | cap (200, R6 change 6) | 0.759 | 0.860 |  |
| pessimistic | worst Holm step, supported (decision) |  |  |  | 200 | cap (200, R6 change 6) | 0.418 | 0.456 |  |
| pessimistic | worst Holm step, bootstrap test only |  |  |  | 200 | cap (200, R6 change 6) | 0.418 | 0.456 |  |
| pessimistic | Holm over H1 and H3 together, supported |  |  |  | 200 | cap (200, R6 change 6) | 0.475 | 0.495 |  |
| pessimistic | unadjusted one-sided 0.05 |  |  |  | 200 | cap (200, R6 change 6) | 0.532 | 0.566 |  |

- **primary:** no T <= 200 reaches 0.80 for both tests, so R6 change 6 sets **T = 200**; achieved power there: H1 0.647, H3 0.782.
- **pessimistic:** no T <= 200 reaches 0.80 for both tests, so R6 change 6 sets **T = 200**; achieved power there: H1 0.418, H3 0.456.

## Power by T
Monte Carlo SE at 0.80 is about 0.009. Holm columns run the procedure over H1 and H3 on the same data; holm4 is the family of 4 (H2's tests counted as not rejected). P_h1_kill_fires: §3's kill reading at the true 10pp. Full columns in `luna_power.csv`.

| scenario | templates | P_h1_supported_worst_step | P_h3_supported_worst_step | P_h1_supported_holm | P_h3_supported_holm | P_h1_unadjusted | P_h3_unadjusted | P_h1_holm4 | P_h3_holm4 | P_h1_kill_fires |
|---|---|---|---|---|---|---|---|---|---|---|
| primary | 50 | 0.203 | 0.290 | 0.235 | 0.309 | 0.306 | 0.394 | 0.152 | 0.222 | 0.154 |
| primary | 60 | 0.239 | 0.343 | 0.287 | 0.374 | 0.354 | 0.452 | 0.176 | 0.257 | 0.144 |
| primary | 70 | 0.271 | 0.386 | 0.310 | 0.422 | 0.381 | 0.505 | 0.207 | 0.292 | 0.188 |
| primary | 80 | 0.301 | 0.442 | 0.353 | 0.475 | 0.425 | 0.552 | 0.239 | 0.339 | 0.180 |
| primary | 90 | 0.333 | 0.464 | 0.395 | 0.504 | 0.467 | 0.596 | 0.263 | 0.383 | 0.217 |
| primary | 100 | 0.374 | 0.512 | 0.436 | 0.557 | 0.501 | 0.642 | 0.299 | 0.421 | 0.207 |
| primary | 110 | 0.404 | 0.549 | 0.463 | 0.592 | 0.531 | 0.664 | 0.328 | 0.453 | 0.241 |
| primary | 120 | 0.437 | 0.579 | 0.503 | 0.627 | 0.573 | 0.699 | 0.361 | 0.495 | 0.231 |
| primary | 130 | 0.467 | 0.624 | 0.537 | 0.665 | 0.594 | 0.724 | 0.389 | 0.528 | 0.276 |
| primary | 140 | 0.490 | 0.645 | 0.561 | 0.694 | 0.621 | 0.754 | 0.423 | 0.566 | 0.261 |
| primary | 150 | 0.520 | 0.674 | 0.597 | 0.719 | 0.640 | 0.775 | 0.449 | 0.590 | 0.302 |
| primary | 160 | 0.550 | 0.709 | 0.625 | 0.744 | 0.666 | 0.788 | 0.476 | 0.629 | 0.288 |
| primary | 170 | 0.570 | 0.732 | 0.648 | 0.768 | 0.690 | 0.808 | 0.503 | 0.653 | 0.333 |
| primary | 180 | 0.597 | 0.745 | 0.676 | 0.780 | 0.721 | 0.829 | 0.523 | 0.677 | 0.315 |
| primary | 190 | 0.621 | 0.767 | 0.704 | 0.809 | 0.737 | 0.845 | 0.553 | 0.700 | 0.359 |
| primary | 200 | 0.647 | 0.782 | 0.725 | 0.823 | 0.759 | 0.860 | 0.569 | 0.718 | 0.342 |
| pessimistic | 50 | 0.127 | 0.151 | 0.142 | 0.168 | 0.204 | 0.226 | 0.086 | 0.095 | 0.125 |
| pessimistic | 60 | 0.152 | 0.172 | 0.172 | 0.187 | 0.224 | 0.264 | 0.101 | 0.117 | 0.125 |
| pessimistic | 70 | 0.170 | 0.193 | 0.195 | 0.209 | 0.266 | 0.282 | 0.107 | 0.137 | 0.147 |
| pessimistic | 80 | 0.188 | 0.222 | 0.209 | 0.240 | 0.284 | 0.317 | 0.135 | 0.150 | 0.139 |
| pessimistic | 90 | 0.211 | 0.245 | 0.237 | 0.265 | 0.304 | 0.351 | 0.142 | 0.175 | 0.161 |
| pessimistic | 100 | 0.216 | 0.270 | 0.255 | 0.295 | 0.331 | 0.371 | 0.158 | 0.189 | 0.154 |
| pessimistic | 110 | 0.237 | 0.283 | 0.274 | 0.309 | 0.351 | 0.389 | 0.174 | 0.205 | 0.179 |
| pessimistic | 120 | 0.268 | 0.301 | 0.300 | 0.338 | 0.377 | 0.425 | 0.192 | 0.223 | 0.172 |
| pessimistic | 130 | 0.286 | 0.323 | 0.322 | 0.361 | 0.397 | 0.446 | 0.211 | 0.242 | 0.191 |
| pessimistic | 140 | 0.307 | 0.340 | 0.341 | 0.372 | 0.411 | 0.466 | 0.226 | 0.261 | 0.183 |
| pessimistic | 150 | 0.326 | 0.370 | 0.370 | 0.405 | 0.444 | 0.487 | 0.251 | 0.277 | 0.211 |
| pessimistic | 160 | 0.342 | 0.385 | 0.381 | 0.421 | 0.458 | 0.499 | 0.262 | 0.296 | 0.201 |
| pessimistic | 170 | 0.352 | 0.397 | 0.408 | 0.437 | 0.479 | 0.521 | 0.271 | 0.308 | 0.232 |
| pessimistic | 180 | 0.381 | 0.414 | 0.433 | 0.457 | 0.497 | 0.537 | 0.291 | 0.323 | 0.220 |
| pessimistic | 190 | 0.392 | 0.428 | 0.450 | 0.477 | 0.513 | 0.554 | 0.308 | 0.344 | 0.246 |
| pessimistic | 200 | 0.418 | 0.456 | 0.475 | 0.495 | 0.532 | 0.566 | 0.327 | 0.364 | 0.234 |

## Cross-check: normal approximation
`luna_normal_power` computes the test-only power at the worst step another way: a normal approximation with the exact variance of one template's contribution, integrated over the template intercept. It leaves out the model check and the bootstrap's discreteness, so gaps of a few points are expected (compare the size rows below). Full table in `luna_normal_check.csv`.

| scenario | templates | P_h1_worst_step | normal_h1_worst_step | P_h3_worst_step | normal_h3_worst_step |
|---|---|---|---|---|---|
| primary | 50 | 0.206 | 0.230 | 0.290 | 0.290 |
| primary | 100 | 0.382 | 0.408 | 0.512 | 0.511 |
| primary | 150 | 0.525 | 0.562 | 0.674 | 0.683 |
| primary | 200 | 0.650 | 0.686 | 0.782 | 0.803 |
| pessimistic | 50 | 0.127 | 0.147 | 0.151 | 0.152 |
| pessimistic | 100 | 0.216 | 0.250 | 0.270 | 0.261 |
| pessimistic | 150 | 0.326 | 0.350 | 0.370 | 0.365 |
| pessimistic | 200 | 0.418 | 0.444 | 0.456 | 0.462 |

- **primary:** without R6's cap, this approximation reaches 0.80 for both tests at the worst step at about T = 270.
- **pessimistic:** without R6's cap, this approximation reaches 0.80 for both tests at the worst step at about T = 480.

## Sensitivity: the primary scenario with one assumption changed

| scenario | templates | P_h1_supported_worst_step | P_h3_supported_worst_step | P_h1_unadjusted | P_h3_unadjusted |
|---|---|---|---|---|---|
| primary, p_f0_obs = 0.85 (as pessimistic) | 100 | 0.275 | 0.360 | 0.395 | 0.474 |
| primary, p_f0_obs = 0.85 (as pessimistic) | 150 | 0.397 | 0.503 | 0.527 | 0.615 |
| primary, p_f0_obs = 0.85 (as pessimistic) | 200 | 0.499 | 0.608 | 0.631 | 0.723 |
| primary, p_f0_der = 0.8 (as pessimistic) | 100 | 0.373 | 0.377 | 0.504 | 0.503 |
| primary, p_f0_der = 0.8 (as pessimistic) | 150 | 0.520 | 0.526 | 0.643 | 0.648 |
| primary, p_f0_der = 0.8 (as pessimistic) | 200 | 0.649 | 0.638 | 0.758 | 0.749 |
| primary, p_w0_nr = 0.18 (as pessimistic) | 100 | 0.310 | 0.514 | 0.447 | 0.644 |
| primary, p_w0_nr = 0.18 (as pessimistic) | 150 | 0.462 | 0.675 | 0.586 | 0.777 |
| primary, p_w0_nr = 0.18 (as pessimistic) | 200 | 0.579 | 0.782 | 0.701 | 0.861 |
| primary, sd = 0 (as pessimistic) | 100 | 0.334 | 0.472 | 0.458 | 0.584 |
| primary, sd = 0 (as pessimistic) | 150 | 0.473 | 0.620 | 0.585 | 0.734 |
| primary, sd = 0 (as pessimistic) | 200 | 0.600 | 0.745 | 0.715 | 0.829 |
| primary, sd = 0.5 | 100 | 0.351 | 0.491 | 0.480 | 0.605 |
| primary, sd = 0.5 | 150 | 0.488 | 0.647 | 0.611 | 0.744 |
| primary, sd = 0.5 | 200 | 0.621 | 0.762 | 0.733 | 0.836 |
| primary, sd = 1.5 | 100 | 0.405 | 0.565 | 0.545 | 0.675 |
| primary, sd = 1.5 | 150 | 0.582 | 0.723 | 0.698 | 0.803 |
| primary, sd = 1.5 | 200 | 0.709 | 0.825 | 0.811 | 0.890 |
| primary, sd = 2 | 100 | 0.454 | 0.609 | 0.592 | 0.722 |
| primary, sd = 2 | 150 | 0.634 | 0.769 | 0.751 | 0.848 |
| primary, sd = 2 | 200 | 0.765 | 0.873 | 0.858 | 0.921 |
| size: delta_h1 = 0, delta_h3 = 0.05 (F-0 0.05 below primary) | 100 | 0.021 | 0.025 | 0.043 | 0.048 |
| size: delta_h1 = 0, delta_h3 = 0.05 (F-0 0.05 below primary) | 150 | 0.024 | 0.033 | 0.044 | 0.052 |
| size: delta_h1 = 0, delta_h3 = 0.05 (F-0 0.05 below primary) | 200 | 0.020 | 0.030 | 0.043 | 0.058 |

In the size rows both nulls hold at their boundary, so their columns are rejection rates under H0, to compare with the nominal levels (0.025 at the worst step, 0.05 unadjusted; Monte Carlo SE about 0.003 and 0.005). The percentile bootstrap on these discrete outcomes need not hit them exactly; any excess is a property of the registered test, not of this simulation.

## Cost and the phase-1a cap
luna's sweep and controls cost about $0.3552 billed per template (committed forecast `results/cost_model/20261003T071449Z/sol_h1_phase_1a.csv`, line `luna_main_sweep_and_controls` at T = 100, scaled linearly; rough).
- T = 200: about $71.04; phase 1a would reach $89.19 of its $500 cap (spent $18.15, `results/costs.csv`).

## What this does not show
- The success levels and the template SD are assumptions, not measurements: no main-split episode exists and pilot outcomes are blinded. Power depends mostly on them.
- One shared template intercept is the only within-template correlation. Real cells may correlate less (then power is lower, toward the SD 0 rows) or more.
- H1's model check uses a GLM on H1's 4 cells, not the full §9.1 model, and only its sign enters; H3's uses the average marginal effect with no-variation templates at 0. The H1/H3 analysis module is not written yet; it should make the same choices, or the power stated here does not carry over exactly.
- No exclusions are simulated (§13; luna's 320 validity episodes had none).
- The power is for the kill-boundary effect Delta_H1 = 10pp. It says nothing about the size of the real effect.
