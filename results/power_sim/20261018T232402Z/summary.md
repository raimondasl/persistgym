# luna power re-simulation for T (PREREG §4.2, R6 change 6): 20261018T232402Z

Command: `uv run python -m analysis.power_sim --part luna --reps 2000 --luna-boot 10000 --luna-templates 200 --luna-sensitivity-templates 200 --luna-sensitivity-sd 0.5,1,1.5,2 --luna-names primary,pessimistic --luna-p-f0-obs 0.95,0.85 --luna-p-f0-der 0.9,0.8 --luna-p-w0-nr 0.023,0.18 --luna-template-sd 0.92,0 --luna-validity-glob results/persistgym_validity/*-F-0-claude-haiku-5-5/episodes.jsonl`

## What is simulated
One luna data set holds, per template, one repeat-0 outcome in each of 7 cells (§2.9: repeats stay out of the primary analyses): F-0 and W-0 on observed-far-R and -NR (H1), and F-0 and the single-turn control on observed- and derived-NR-far (H3). F-0 on observed-NR-far is shared by both tests. Each data set is analysed as §9.1 and §9.4 will analyse the sweep:
- template-cluster percentile bootstrap on the probability scale with 10,000 resamples, shared by both contrasts (drawn as category counts, which is exact: `category_bootstrap_sums`);
- H1: one-sided bootstrap p = share of resamples with Delta_H1 <= 0; H3: share with Delta_H3 >= 5pp; ties count on the null side;
- "supported" = the test rejects and the model check agrees: for H1 a positive W-0 x R interaction in a template-FE logit on H1's 4 cells, for H3 a GLM Delta_H3 (average marginal effect) below 5pp;
- 2,000 simulated sweeps per scenario, each analysed at every T from 200 to 200 on its first T templates (templates are taken in seed order), so the power curves share random numbers.

**Decision reading.** The frozen rule needs power >= 0.80 for H1 at Delta_H1 = 10pp and for H3 at Delta_H3 = 0. This run reads it conservatively: P(supported) for each test at the worst Holm step (one-sided 0.025 with the family of 2). That is at most the power under the real Holm procedure and at most the unadjusted power; both are reported too.

## Assumptions
| Parameter | primary | pessimistic | Why |
|---|---|---|---|
| F-0 success, observed-far (R and NR); the single-turn control's on observed-NR-far under H3's null (`p_f0_obs`) | 0.95 | 0.85 | No F-0 main-cell success may be used (pilots blinded, §11; no main-split episode exists). luna scored 160/160 on restated-at-need (memory taken out), so the ceiling is near 1; full history must still retrieve one binding from beyond W = 24k tokens. Primary 0.95 sits just below that ceiling; pessimistic 0.85 allows real long-context loss. |
| F-0 success, derived-NR-far (the single-turn control's too, under H3's null) (`p_f0_der`) | 0.9 | 0.8 | Restated derived cells also scored 80/80, so the arithmetic is not the problem; a derived fact needs 2-3 clue bindings and the rule retrieved, so each scenario puts it 5pp below the observed level. |
| W-0 success, observed-far-NR: the no-memory level (`p_w0_nr`) | 0.023 | 0.18 | W-0 has evicted the evidence and has no lookup, as in the fact-withheld control. luna's pooled withheld rate is 19/160 = 0.119 (primary 0.12); 0.18 is the upper end of its 95% Wilson interval. Chance is 0.10 (K = 10). |
| Template random-intercept SD (logit), shared by a template's 7 cells (`sd`) | 0.92 | 0 | Primary 0.92 is the template SD on the logit scale (a variance of 0.85) measured in luna's validity runs, as §4.2 asks ("the variance measured in the validity runs"): the ML estimate from its fact-withheld run (table below; the restated run carries none). PLAN §10's 1.0 is a sensitivity row. Every contrast here is paired within template, so a larger shared SD raises power (sensitivity rows); pessimistic 0, the lower end of that estimate's 95% interval, leaves the cells independent. |
| F-0 success on observed-far-R minus on -NR (`r_shift`) | 0 | 0 | 0: F-0 sees the fact in full history, so lookups should add little. Then W-0's R success = p_w0_nr + delta_h1. |
| True Delta_H1 = Penalty_NR - Penalty_R (`delta_h1`) | 0.1 | 0.1 | 10pp, fixed by §4.2 (the kill boundary). Penalty_NR = p_f0_obs - p_w0_nr is set by the design; Penalty_R = Penalty_NR - 10pp. |
| True Delta_H3 = p(single-turn) - p(F-0), NR-far pooled (`delta_h3`) | 0 | 0 | 0, fixed by §4.2; the bound is 5pp (§3 H3). |
| Holm family size (`holm_tests`) | 2 | 2 | 2 (H1, H3): the researcher's decision of 2026-10-06, R6 change 9; worst step one-sided 0.025. The family of 4 (worst step 0.0125) is a sensitivity column. |

Resulting success levels per cell (population averages; Delta_H1 = (f0_onr - w0_onr) - (f0_or - w0_or), Delta_H3 = mean(st) - mean(f0) over the NR-far cells):

| scenario | f0_onr | w0_onr | f0_or | w0_or | f0_dnr | st_onr | st_dnr |
|---|---|---|---|---|---|---|---|
| primary | 0.950 | 0.023 | 0.950 | 0.123 | 0.900 | 0.950 | 0.900 |
| pessimistic | 0.850 | 0.180 | 0.850 | 0.280 | 0.800 | 0.850 | 0.800 |

## Variance measured in luna's validity runs
Random-intercept logit on F-0, validity templates 0-19 x 8 task cells (`validity_template_sd`; 95% profile-likelihood interval, chi-square 1 df):

| variant | templates | episodes | successes | rate | sd_hat | sd_ci95_low | sd_ci95_high | lr_vs_sd0 | note |
|---|---|---|---|---|---|---|---|---|---|
| restated | 20 | 160 | 160 | 1.000 |  |  |  |  | not identified: every episode had the same outcome |
| withheld | 20 | 160 | 0 | 0.000 |  |  |  |  | not identified: every episode had the same outcome |

Restated-at-need succeeded in every episode, so it carries no variance. §4.2 has the power re-simulation use the variance measured in the validity runs, so the primary scenario takes the withheld run's estimate: a template SD of 0.92 on the logit scale (`LUNA_VALIDITY_SD`; a variance of 0.85). That run measures how guesses cluster by template, not how memory success does, and 20 templates leave the interval wide, so the sensitivity rows vary the SD.

## Result: the template count

| scenario | reading | T_h1 | T_h3 | T_both | T_set | T_set_by | power_h1_at_T_set | power_h3_at_T_set | all_larger_T_meet | T_h1_uncapped | T_h3_uncapped | T_both_uncapped | T_grid_max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| primary | worst Holm step, supported (decision) | 200 |  |  | 200 | cap (200, R6 change 6) | 0.849 | 0.781 |  | 200 |  |  | 200 |
| primary | worst Holm step, bootstrap test only | 200 |  |  | 200 | cap (200, R6 change 6) | 0.849 | 0.781 |  | 200 |  |  | 200 |
| primary | Holm over H1 and H3 together, supported | 200 | 200 | 200 | 200 | rule | 0.894 | 0.842 | True | 200 | 200 | 200 | 200 |
| primary | unadjusted one-sided 0.05 | 200 | 200 | 200 | 200 | rule | 0.912 | 0.864 | True | 200 | 200 | 200 | 200 |
| pessimistic | worst Holm step, supported (decision) |  |  |  | 200 | cap (200, R6 change 6) | 0.416 | 0.456 |  |  |  |  | 200 |
| pessimistic | worst Holm step, bootstrap test only |  |  |  | 200 | cap (200, R6 change 6) | 0.416 | 0.456 |  |  |  |  | 200 |
| pessimistic | Holm over H1 and H3 together, supported |  |  |  | 200 | cap (200, R6 change 6) | 0.473 | 0.494 |  |  |  |  | 200 |
| pessimistic | unadjusted one-sided 0.05 |  |  |  | 200 | cap (200, R6 change 6) | 0.530 | 0.565 |  |  |  |  | 200 |

- **primary:** no T <= 200 reaches 0.80 for both tests, so R6 change 6 sets **T = 200**; achieved power there: H1 0.849, H3 0.781. Without R6's cap no simulated T up to 200 reaches 0.80 for both tests.
- **pessimistic:** no T <= 200 reaches 0.80 for both tests, so R6 change 6 sets **T = 200**; achieved power there: H1 0.416, H3 0.456. Without R6's cap no simulated T up to 200 reaches 0.80 for both tests.

The uncapped T is read from this simulation, on its grid of T up to 200; it sets nothing (R6 change 6 caps T at 200). Its curves carry Monte Carlo noise, so a T near the target can move by 10 between runs.

## Power by T
Monte Carlo SE at 0.80 is about 0.009. Holm columns run the procedure over H1 and H3 on the same data; holm4 is the family of 4 (H2's tests counted as not rejected). P_h1_kill_fires: §3's kill reading at the true 10pp. Full columns in `luna_power.csv`.

| scenario | templates | P_h1_supported_worst_step | P_h3_supported_worst_step | P_h1_supported_holm | P_h3_supported_holm | P_h1_unadjusted | P_h3_unadjusted | P_h1_holm4 | P_h3_holm4 | P_h1_kill_fires |
|---|---|---|---|---|---|---|---|---|---|---|
| primary | 200 | 0.849 | 0.781 | 0.894 | 0.842 | 0.912 | 0.864 | 0.790 | 0.726 | 0.442 |
| pessimistic | 200 | 0.416 | 0.456 | 0.473 | 0.494 | 0.530 | 0.565 | 0.328 | 0.363 | 0.235 |

## Cross-check: normal approximation
`luna_normal_power` computes the test-only power at the worst step another way: a normal approximation with the exact variance of one template's contribution, integrated over the template intercept. It leaves out the model check and the bootstrap's discreteness, so gaps of a few points are expected (compare the size rows below). Full table in `luna_normal_check.csv`.

| scenario | templates | P_h1_worst_step | normal_h1_worst_step | P_h3_worst_step | normal_h3_worst_step |
|---|---|---|---|---|---|
| primary | 200 | 0.849 | 0.860 | 0.781 | 0.798 |
| pessimistic | 200 | 0.416 | 0.444 | 0.456 | 0.462 |

- **primary:** this approximation reaches 0.80 for both tests at the worst step (test only) at about T = 210; it runs above the simulation, so the uncapped T quoted above is the simulation's.
- **pessimistic:** this approximation reaches 0.80 for both tests at the worst step (test only) at about T = 480; it runs above the simulation, so the uncapped T quoted above is the simulation's.

## Sensitivity: the primary scenario with one assumption changed

| scenario | templates | P_h1_supported_worst_step | P_h3_supported_worst_step | P_h1_unadjusted | P_h3_unadjusted |
|---|---|---|---|---|---|
| primary, p_f0_obs = 0.85 (as pessimistic) | 200 | 0.631 | 0.604 | 0.736 | 0.719 |
| primary, p_f0_der = 0.8 (as pessimistic) | 200 | 0.847 | 0.635 | 0.912 | 0.741 |
| primary, p_w0_nr = 0.18 (as pessimistic) | 200 | 0.561 | 0.782 | 0.693 | 0.862 |
| primary, sd = 0 (as pessimistic) | 200 | 0.827 | 0.743 | 0.894 | 0.832 |
| primary, sd = 0.5 | 200 | 0.831 | 0.764 | 0.898 | 0.837 |
| primary, sd = 1 | 200 | 0.859 | 0.782 | 0.911 | 0.863 |
| primary, sd = 1.5 | 200 | 0.881 | 0.826 | 0.930 | 0.887 |
| primary, sd = 2 | 200 | 0.901 | 0.870 | 0.950 | 0.921 |
| size: delta_h1 = 0, delta_h3 = 0.05 (F-0 0.05 below primary) | 200 | 0.019 | 0.038 | 0.041 | 0.060 |

In the size rows both nulls hold at their boundary, so their columns are rejection rates under H0, to compare with the nominal levels (0.025 at the worst step, 0.05 unadjusted; Monte Carlo SE about 0.003 and 0.005). The percentile bootstrap on these discrete outcomes need not hit them exactly; any excess is a property of the registered test, not of this simulation.

## Cost and the phase-1a cap
luna's sweep and controls cost about $0.3552 billed per template (committed forecast `results/cost_model/20261003T071449Z/sol_h1_phase_1a.csv`, line `luna_main_sweep_and_controls` at T = 100, scaled linearly; rough).
- T = 200: about $71.04; phase 1a would reach $292.62 of its $500 cap (spent $221.59, `results/costs.csv`).

## What this does not show
- The success levels are assumptions, not measurements: no main-split episode exists and pilot outcomes are blinded. The template SD is measured, but on the fact-withheld validity run (how guesses cluster), with a wide interval. Power depends mostly on these.
- One shared template intercept is the only within-template correlation. Real cells may correlate less (then power is lower, toward the SD 0 rows) or more.
- H1's model check uses a GLM on H1's 4 cells, not the full §9.1 model, and only its sign enters; H3's uses the average marginal effect with no-variation templates at 0. The H1/H3 analysis module is not written yet; it should make the same choices, or the power stated here does not carry over exactly. It must also key episodes on (episode_id, repeat_index, 0 if absent) and deduplicate §13's transport re-runs explicitly (harnesses/DESIGN.md §7.8): one repeat-0 outcome per template and cell, as simulated here.
- No exclusions are simulated (§13; luna's 320 validity episodes had none).
- The power is for the kill-boundary effect Delta_H1 = 10pp. It says nothing about the size of the real effect.
