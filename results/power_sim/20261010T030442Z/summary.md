# luna power re-simulation for T (PREREG §4.2, R6 change 6): 20261010T030442Z

Command: `uv run python -m analysis.power_sim --part luna --reps 2000`

## What is simulated
One luna data set holds, per template, one repeat-0 outcome in each of 7 cells (§2.9: repeats stay out of the primary analyses): F-0 and W-0 on observed-far-R and -NR (H1), and F-0 and the single-turn control on observed- and derived-NR-far (H3). F-0 on observed-NR-far is shared by both tests. Each data set is analysed as §9.1 and §9.4 will analyse the sweep:
- template-cluster percentile bootstrap on the probability scale with 10,000 resamples, shared by both contrasts (drawn as category counts, which is exact: `category_bootstrap_sums`);
- H1: one-sided bootstrap p = share of resamples with Delta_H1 <= 0; H3: share with Delta_H3 >= 5pp; ties count on the null side;
- "supported" = the test rejects and the model check agrees: for H1 a positive W-0 x R interaction in a template-FE logit on H1's 4 cells, for H3 a GLM Delta_H3 (average marginal effect) below 5pp;
- 2,000 simulated sweeps per scenario, each analysed at every T from 50 to 300 on its first T templates (templates are taken in seed order), so the power curves share random numbers.

**Decision reading.** The frozen rule needs power >= 0.80 for H1 at Delta_H1 = 10pp and for H3 at Delta_H3 = 0. This run reads it conservatively: P(supported) for each test at the worst Holm step (one-sided 0.025 with the family of 2). That is at most the power under the real Holm procedure and at most the unadjusted power; both are reported too.

## Assumptions
| Parameter | primary | pessimistic | Why |
|---|---|---|---|
| F-0 success, observed-far (R and NR); the single-turn control's on observed-NR-far under H3's null (`p_f0_obs`) | 0.95 | 0.85 | No F-0 main-cell success may be used (pilots blinded, §11; no main-split episode exists). luna scored 160/160 on restated-at-need (memory taken out), so the ceiling is near 1; full history must still retrieve one binding from beyond W = 24k tokens. Primary 0.95 sits just below that ceiling; pessimistic 0.85 allows real long-context loss. |
| F-0 success, derived-NR-far (the single-turn control's too, under H3's null) (`p_f0_der`) | 0.9 | 0.8 | Restated derived cells also scored 80/80, so the arithmetic is not the problem; a derived fact needs 2-3 clue bindings and the rule retrieved, so each scenario puts it 5pp below the observed level. |
| W-0 success, observed-far-NR: the no-memory level (`p_w0_nr`) | 0.12 | 0.18 | W-0 has evicted the evidence and has no lookup, as in the fact-withheld control. luna's pooled withheld rate is 19/160 = 0.119 (primary 0.12); 0.18 is the upper end of its 95% Wilson interval. Chance is 0.10 (K = 10). |
| Template random-intercept SD (logit), shared by a template's 7 cells (`sd`) | 0.92 | 0 | Primary 0.92 is the template SD on the logit scale (a variance of 0.85) measured in luna's validity runs, as §4.2 asks ("the variance measured in the validity runs"): the ML estimate from its fact-withheld run (table below; the restated run carries none). PLAN §10's 1.0 is a sensitivity row. Every contrast here is paired within template, so a larger shared SD raises power (sensitivity rows); pessimistic 0, the lower end of that estimate's 95% interval, leaves the cells independent. |
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

Restated-at-need succeeded in every episode, so it carries no variance. §4.2 has the power re-simulation use the variance measured in the validity runs, so the primary scenario takes the withheld run's estimate: a template SD of 0.92 on the logit scale (`LUNA_VALIDITY_SD`; a variance of 0.85). That run measures how guesses cluster by template, not how memory success does, and 20 templates leave the interval wide, so the sensitivity rows vary the SD.

## Result: the template count

| scenario | reading | T_h1 | T_h3 | T_both | T_set | T_set_by | power_h1_at_T_set | power_h3_at_T_set | all_larger_T_meet | T_h1_uncapped | T_h3_uncapped | T_both_uncapped | T_grid_max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| primary | worst Holm step, supported (decision) |  |  |  | 200 | cap (200, R6 change 6) | 0.647 | 0.781 |  | 290 | 220 | 290 | 300 |
| primary | worst Holm step, bootstrap test only |  |  |  | 200 | cap (200, R6 change 6) | 0.648 | 0.781 |  | 290 | 220 | 290 | 300 |
| primary | Holm over H1 and H3 together, supported |  | 200 |  | 200 | cap (200, R6 change 6) | 0.721 | 0.828 |  | 240 | 200 | 240 | 300 |
| primary | unadjusted one-sided 0.05 |  | 170 |  | 200 | cap (200, R6 change 6) | 0.753 | 0.854 |  | 230 | 170 | 230 | 300 |
| pessimistic | worst Holm step, supported (decision) |  |  |  | 200 | cap (200, R6 change 6) | 0.438 | 0.443 |  |  |  |  | 300 |
| pessimistic | worst Holm step, bootstrap test only |  |  |  | 200 | cap (200, R6 change 6) | 0.438 | 0.443 |  |  |  |  | 300 |
| pessimistic | Holm over H1 and H3 together, supported |  |  |  | 200 | cap (200, R6 change 6) | 0.492 | 0.502 |  |  |  |  | 300 |
| pessimistic | unadjusted one-sided 0.05 |  |  |  | 200 | cap (200, R6 change 6) | 0.554 | 0.568 |  |  |  |  | 300 |

- **primary:** no T <= 200 reaches 0.80 for both tests, so R6 change 6 sets **T = 200**; achieved power there: H1 0.647, H3 0.781. Without R6's cap the simulated rule would need **T = 290** (`T_both_uncapped`).
- **pessimistic:** no T <= 200 reaches 0.80 for both tests, so R6 change 6 sets **T = 200**; achieved power there: H1 0.438, H3 0.443. Without R6's cap no simulated T up to 300 reaches 0.80 for both tests.

The uncapped T is read from this simulation, on its grid of T up to 300; it sets nothing (R6 change 6 caps T at 200). Its curves carry Monte Carlo noise, so a T near the target can move by 10 between runs.

## Power by T
Monte Carlo SE at 0.80 is about 0.009. Holm columns run the procedure over H1 and H3 on the same data; holm4 is the family of 4 (H2's tests counted as not rejected). P_h1_kill_fires: §3's kill reading at the true 10pp. Full columns in `luna_power.csv`.

| scenario | templates | P_h1_supported_worst_step | P_h3_supported_worst_step | P_h1_supported_holm | P_h3_supported_holm | P_h1_unadjusted | P_h3_unadjusted | P_h1_holm4 | P_h3_holm4 | P_h1_kill_fires |
|---|---|---|---|---|---|---|---|---|---|---|
| primary | 50 | 0.195 | 0.281 | 0.228 | 0.308 | 0.299 | 0.384 | 0.149 | 0.209 | 0.178 |
| primary | 60 | 0.224 | 0.322 | 0.259 | 0.344 | 0.336 | 0.422 | 0.172 | 0.246 | 0.154 |
| primary | 70 | 0.273 | 0.356 | 0.315 | 0.395 | 0.385 | 0.472 | 0.203 | 0.279 | 0.201 |
| primary | 80 | 0.314 | 0.399 | 0.359 | 0.429 | 0.434 | 0.509 | 0.235 | 0.326 | 0.184 |
| primary | 90 | 0.341 | 0.440 | 0.397 | 0.474 | 0.468 | 0.552 | 0.262 | 0.352 | 0.223 |
| primary | 100 | 0.374 | 0.466 | 0.431 | 0.508 | 0.495 | 0.588 | 0.304 | 0.383 | 0.208 |
| primary | 110 | 0.413 | 0.518 | 0.474 | 0.568 | 0.532 | 0.638 | 0.339 | 0.426 | 0.237 |
| primary | 120 | 0.442 | 0.551 | 0.509 | 0.602 | 0.568 | 0.662 | 0.360 | 0.457 | 0.221 |
| primary | 130 | 0.464 | 0.588 | 0.549 | 0.639 | 0.604 | 0.694 | 0.384 | 0.498 | 0.260 |
| primary | 140 | 0.494 | 0.618 | 0.565 | 0.669 | 0.620 | 0.728 | 0.422 | 0.530 | 0.246 |
| primary | 150 | 0.519 | 0.652 | 0.589 | 0.702 | 0.638 | 0.750 | 0.447 | 0.563 | 0.288 |
| primary | 160 | 0.546 | 0.671 | 0.623 | 0.732 | 0.665 | 0.779 | 0.466 | 0.590 | 0.287 |
| primary | 170 | 0.576 | 0.698 | 0.659 | 0.756 | 0.708 | 0.802 | 0.492 | 0.625 | 0.301 |
| primary | 180 | 0.603 | 0.731 | 0.673 | 0.781 | 0.718 | 0.824 | 0.524 | 0.649 | 0.303 |
| primary | 190 | 0.627 | 0.756 | 0.700 | 0.798 | 0.738 | 0.841 | 0.543 | 0.681 | 0.336 |
| primary | 200 | 0.647 | 0.781 | 0.721 | 0.828 | 0.753 | 0.854 | 0.575 | 0.708 | 0.325 |
| primary | 210 | 0.666 | 0.793 | 0.744 | 0.842 | 0.776 | 0.874 | 0.596 | 0.732 | 0.367 |
| primary | 220 | 0.697 | 0.816 | 0.773 | 0.863 | 0.799 | 0.881 | 0.619 | 0.751 | 0.343 |
| primary | 230 | 0.719 | 0.834 | 0.792 | 0.871 | 0.815 | 0.893 | 0.644 | 0.774 | 0.381 |
| primary | 240 | 0.735 | 0.847 | 0.804 | 0.886 | 0.825 | 0.907 | 0.665 | 0.785 | 0.368 |
| primary | 250 | 0.753 | 0.863 | 0.823 | 0.903 | 0.840 | 0.917 | 0.689 | 0.812 | 0.399 |
| primary | 260 | 0.767 | 0.877 | 0.839 | 0.910 | 0.856 | 0.922 | 0.710 | 0.826 | 0.386 |
| primary | 270 | 0.781 | 0.883 | 0.846 | 0.914 | 0.859 | 0.930 | 0.721 | 0.841 | 0.414 |
| primary | 280 | 0.789 | 0.898 | 0.856 | 0.928 | 0.871 | 0.941 | 0.736 | 0.860 | 0.413 |
| primary | 290 | 0.804 | 0.904 | 0.862 | 0.935 | 0.875 | 0.946 | 0.751 | 0.872 | 0.444 |
| primary | 300 | 0.817 | 0.917 | 0.876 | 0.941 | 0.889 | 0.950 | 0.770 | 0.883 | 0.434 |
| pessimistic | 50 | 0.129 | 0.143 | 0.140 | 0.157 | 0.210 | 0.214 | 0.088 | 0.093 | 0.117 |
| pessimistic | 60 | 0.145 | 0.168 | 0.159 | 0.186 | 0.242 | 0.248 | 0.095 | 0.109 | 0.115 |
| pessimistic | 70 | 0.175 | 0.181 | 0.197 | 0.202 | 0.268 | 0.277 | 0.111 | 0.112 | 0.124 |
| pessimistic | 80 | 0.197 | 0.197 | 0.218 | 0.225 | 0.297 | 0.301 | 0.140 | 0.130 | 0.132 |
| pessimistic | 90 | 0.221 | 0.218 | 0.240 | 0.255 | 0.317 | 0.330 | 0.157 | 0.144 | 0.151 |
| pessimistic | 100 | 0.239 | 0.248 | 0.275 | 0.283 | 0.360 | 0.349 | 0.174 | 0.172 | 0.133 |
| pessimistic | 110 | 0.278 | 0.273 | 0.307 | 0.309 | 0.385 | 0.376 | 0.199 | 0.199 | 0.163 |
| pessimistic | 120 | 0.286 | 0.285 | 0.321 | 0.323 | 0.401 | 0.395 | 0.213 | 0.210 | 0.148 |
| pessimistic | 130 | 0.310 | 0.309 | 0.354 | 0.351 | 0.429 | 0.429 | 0.226 | 0.220 | 0.170 |
| pessimistic | 140 | 0.338 | 0.330 | 0.381 | 0.366 | 0.449 | 0.442 | 0.245 | 0.240 | 0.176 |
| pessimistic | 150 | 0.339 | 0.346 | 0.391 | 0.378 | 0.468 | 0.460 | 0.263 | 0.262 | 0.193 |
| pessimistic | 160 | 0.361 | 0.368 | 0.401 | 0.417 | 0.473 | 0.494 | 0.276 | 0.281 | 0.183 |
| pessimistic | 170 | 0.374 | 0.383 | 0.420 | 0.430 | 0.501 | 0.510 | 0.299 | 0.301 | 0.201 |
| pessimistic | 180 | 0.399 | 0.411 | 0.445 | 0.459 | 0.519 | 0.533 | 0.310 | 0.321 | 0.195 |
| pessimistic | 190 | 0.424 | 0.429 | 0.475 | 0.482 | 0.540 | 0.548 | 0.327 | 0.339 | 0.215 |
| pessimistic | 200 | 0.438 | 0.443 | 0.492 | 0.502 | 0.554 | 0.568 | 0.348 | 0.353 | 0.216 |
| pessimistic | 210 | 0.443 | 0.455 | 0.502 | 0.511 | 0.575 | 0.579 | 0.360 | 0.366 | 0.236 |
| pessimistic | 220 | 0.471 | 0.477 | 0.530 | 0.527 | 0.594 | 0.597 | 0.382 | 0.391 | 0.221 |
| pessimistic | 230 | 0.486 | 0.499 | 0.549 | 0.553 | 0.612 | 0.618 | 0.396 | 0.406 | 0.250 |
| pessimistic | 240 | 0.501 | 0.519 | 0.565 | 0.574 | 0.625 | 0.635 | 0.417 | 0.432 | 0.247 |
| pessimistic | 250 | 0.514 | 0.532 | 0.579 | 0.592 | 0.640 | 0.657 | 0.435 | 0.442 | 0.263 |
| pessimistic | 260 | 0.535 | 0.550 | 0.601 | 0.615 | 0.655 | 0.679 | 0.445 | 0.455 | 0.267 |
| pessimistic | 270 | 0.551 | 0.565 | 0.618 | 0.632 | 0.665 | 0.688 | 0.465 | 0.470 | 0.281 |
| pessimistic | 280 | 0.574 | 0.584 | 0.632 | 0.646 | 0.678 | 0.701 | 0.481 | 0.496 | 0.275 |
| pessimistic | 290 | 0.575 | 0.604 | 0.643 | 0.665 | 0.697 | 0.717 | 0.497 | 0.504 | 0.292 |
| pessimistic | 300 | 0.591 | 0.621 | 0.659 | 0.686 | 0.705 | 0.733 | 0.501 | 0.532 | 0.289 |

## Cross-check: normal approximation
`luna_normal_power` computes the test-only power at the worst step another way: a normal approximation with the exact variance of one template's contribution, integrated over the template intercept. It leaves out the model check and the bootstrap's discreteness, so gaps of a few points are expected (compare the size rows below). Full table in `luna_normal_check.csv`.

| scenario | templates | P_h1_worst_step | normal_h1_worst_step | P_h3_worst_step | normal_h3_worst_step |
|---|---|---|---|---|---|
| primary | 50 | 0.201 | 0.227 | 0.281 | 0.287 |
| primary | 100 | 0.378 | 0.403 | 0.466 | 0.506 |
| primary | 150 | 0.521 | 0.556 | 0.652 | 0.677 |
| primary | 200 | 0.648 | 0.679 | 0.781 | 0.798 |
| primary | 250 | 0.756 | 0.774 | 0.863 | 0.878 |
| primary | 300 | 0.821 | 0.844 | 0.917 | 0.928 |
| pessimistic | 50 | 0.129 | 0.147 | 0.143 | 0.152 |
| pessimistic | 100 | 0.239 | 0.250 | 0.248 | 0.261 |
| pessimistic | 150 | 0.339 | 0.350 | 0.346 | 0.365 |
| pessimistic | 200 | 0.438 | 0.444 | 0.443 | 0.462 |
| pessimistic | 250 | 0.514 | 0.530 | 0.532 | 0.550 |
| pessimistic | 300 | 0.591 | 0.606 | 0.621 | 0.627 |

- **primary:** this approximation reaches 0.80 for both tests at the worst step (test only) at about T = 270; it runs above the simulation, so the uncapped T quoted above is the simulation's.
- **pessimistic:** this approximation reaches 0.80 for both tests at the worst step (test only) at about T = 480; it runs above the simulation, so the uncapped T quoted above is the simulation's.

## Sensitivity: the primary scenario with one assumption changed

| scenario | templates | P_h1_supported_worst_step | P_h3_supported_worst_step | P_h1_unadjusted | P_h3_unadjusted |
|---|---|---|---|---|---|
| primary, p_f0_obs = 0.85 (as pessimistic) | 100 | 0.276 | 0.353 | 0.384 | 0.474 |
| primary, p_f0_obs = 0.85 (as pessimistic) | 150 | 0.384 | 0.496 | 0.518 | 0.618 |
| primary, p_f0_obs = 0.85 (as pessimistic) | 200 | 0.496 | 0.604 | 0.622 | 0.723 |
| primary, p_f0_der = 0.8 (as pessimistic) | 100 | 0.370 | 0.373 | 0.496 | 0.503 |
| primary, p_f0_der = 0.8 (as pessimistic) | 150 | 0.519 | 0.518 | 0.639 | 0.642 |
| primary, p_f0_der = 0.8 (as pessimistic) | 200 | 0.640 | 0.633 | 0.753 | 0.742 |
| primary, p_w0_nr = 0.18 (as pessimistic) | 100 | 0.312 | 0.514 | 0.438 | 0.640 |
| primary, p_w0_nr = 0.18 (as pessimistic) | 150 | 0.445 | 0.679 | 0.579 | 0.784 |
| primary, p_w0_nr = 0.18 (as pessimistic) | 200 | 0.565 | 0.782 | 0.694 | 0.863 |
| primary, sd = 0 (as pessimistic) | 100 | 0.334 | 0.472 | 0.458 | 0.584 |
| primary, sd = 0 (as pessimistic) | 150 | 0.473 | 0.620 | 0.585 | 0.734 |
| primary, sd = 0 (as pessimistic) | 200 | 0.600 | 0.745 | 0.715 | 0.829 |
| primary, sd = 0.5 | 100 | 0.351 | 0.491 | 0.480 | 0.605 |
| primary, sd = 0.5 | 150 | 0.488 | 0.647 | 0.611 | 0.744 |
| primary, sd = 0.5 | 200 | 0.621 | 0.762 | 0.733 | 0.836 |
| primary, sd = 1 | 100 | 0.374 | 0.512 | 0.503 | 0.643 |
| primary, sd = 1 | 150 | 0.519 | 0.678 | 0.639 | 0.776 |
| primary, sd = 1 | 200 | 0.648 | 0.782 | 0.759 | 0.861 |
| primary, sd = 1.5 | 100 | 0.405 | 0.565 | 0.545 | 0.675 |
| primary, sd = 1.5 | 150 | 0.582 | 0.723 | 0.698 | 0.803 |
| primary, sd = 1.5 | 200 | 0.709 | 0.825 | 0.811 | 0.890 |
| primary, sd = 2 | 100 | 0.454 | 0.609 | 0.592 | 0.722 |
| primary, sd = 2 | 150 | 0.634 | 0.769 | 0.751 | 0.848 |
| primary, sd = 2 | 200 | 0.765 | 0.873 | 0.858 | 0.921 |
| size: delta_h1 = 0, delta_h3 = 0.05 (F-0 0.05 below primary) | 100 | 0.021 | 0.024 | 0.040 | 0.053 |
| size: delta_h1 = 0, delta_h3 = 0.05 (F-0 0.05 below primary) | 150 | 0.026 | 0.035 | 0.043 | 0.055 |
| size: delta_h1 = 0, delta_h3 = 0.05 (F-0 0.05 below primary) | 200 | 0.021 | 0.037 | 0.041 | 0.059 |

In the size rows both nulls hold at their boundary, so their columns are rejection rates under H0, to compare with the nominal levels (0.025 at the worst step, 0.05 unadjusted; Monte Carlo SE about 0.003 and 0.005). The percentile bootstrap on these discrete outcomes need not hit them exactly; any excess is a property of the registered test, not of this simulation.

## Cost and the phase-1a cap
luna's sweep and controls cost about $0.3552 billed per template (committed forecast `results/cost_model/20261003T071449Z/sol_h1_phase_1a.csv`, line `luna_main_sweep_and_controls` at T = 100, scaled linearly; rough).
- T = 200: about $71.04; phase 1a would reach $89.19 of its $500 cap (spent $18.15, `results/costs.csv`).
- T = 290 (without R6's cap): about $103.01; phase 1a would reach $121.15 of its $500 cap (spent $18.15, `results/costs.csv`).

## What this does not show
- The success levels are assumptions, not measurements: no main-split episode exists and pilot outcomes are blinded. The template SD is measured, but on the fact-withheld validity run (how guesses cluster), with a wide interval. Power depends mostly on these.
- One shared template intercept is the only within-template correlation. Real cells may correlate less (then power is lower, toward the SD 0 rows) or more.
- H1's model check uses a GLM on H1's 4 cells, not the full §9.1 model, and only its sign enters; H3's uses the average marginal effect with no-variation templates at 0. The H1/H3 analysis module is not written yet; it should make the same choices, or the power stated here does not carry over exactly. It must also key episodes on (episode_id, repeat_index, 0 if absent) and deduplicate §13's transport re-runs explicitly (harnesses/DESIGN.md §7.8): one repeat-0 outcome per template and cell, as simulated here.
- No exclusions are simulated (§13; luna's 320 validity episodes had none).
- The power is for the kill-boundary effect Delta_H1 = 10pp. It says nothing about the size of the real effect.
