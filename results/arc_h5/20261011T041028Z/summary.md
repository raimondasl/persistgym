# H5 on ARC: the Adapter advantage by level depth (PREREG §3 H5, D35; R6 change 4)

Computed 2026-10-11T04:10:36+00:00 at commit 93d34f0 (dirty: False) by `uv run python -m analysis.arc_h5 --out-dir results/arc_h5/20261011T041028Z`, from `results`.

Descriptive only; H5 is outside the Holm family (§9.4).

**Status: FINAL.**

> **Definitions.** Reached(ℓ): at least one action on ℓ (`level_actions[ℓ] > 0`, RESETs included; D35). Cleared(ℓ): ℓ ≤ levels completed. Bands: early = levels 1-2, deep = levels ≥ 4 (pooled); level 3 is reported, not in the contrast. The level in play when the action budget or the 12 h clock ended a run counts as reached and not cleared if the run took at least one action on it (D35; R5).
>
> A_b: the Adapter-minus-Standard difference in P(clear | reached) in band b, the average marginal effect over every reached row of the band from both harnesses (a game weighs by its reached level-rows in the band); C = A_deep − A_early.
>
> Estimator in force: `ml_limit_or_firth` (the maximum-likelihood limit where C is identified, else Firth's penalized logit for that reading or resample; the ruling: `results/decisions.md`, 2026-10-10, "H5 analysis: two rulings proposed before any H5 quantity is computed"); the other rule is `firth`. Both estimators (Firth's penalized logit and the maximum-likelihood limit) are shown. Bootstrap: games resampled with replacement, RNG SEED + 40 = 4086943125952605574, 10,000 resamples, percentile 90%.

## Published runs, high effort (registered; not blind)

25 games, 50 runs (one per game and harness), Standard vs Provider Adapter; per_run.csv sha256 `ad34bec8bb88de5283e9c823fd75743393a03d961c8766d305201633d6b24d44` (the pinned file).

| Band | Standard: cleared/reached = P(clear \| reached) | Provider Adapter: cleared/reached = P | Adapter − Standard |
|---|---|---|---|
| early (1-2) | 39/47 = 0.830 | 47/50 = 0.940 | +0.110 |
| level 3 (not in the contrast) | 11/17 = 0.647 | 21/22 = 0.955 | +0.307 |
| deep (≥ 4) | 15/26 = 0.577 | 63/75 = 0.840 | +0.263 |

Raw contrast (r_Ad − r_Sd) − (r_Ae − r_Se) = +0.153 (exploratory: no game adjustment, not the registered model; 90% interval [+0.002, +0.345] over 10,000 defined resamples).

Model: `cleared ~ harness × band + game fixed effects` on the early and deep rows; A_b the average marginal effect over the band's reached rows.

| Estimator | A_early | A_deep | C = A_deep − A_early | 90% interval of C | Fraction C ≤ 0 (descriptive, not a test) | Resamples left out of C (reasons) |
|---|---|---|---|---|---|---|
| Firth (`firth`) | +0.144 | +0.408 | +0.264 | [+0.137, +0.403] | 0.1% | 0 |
| ML limit (`ml_limit`) | +0.136 | +0.439 | +0.304 | [+0.163, +0.456] | 0.0% | 263 (not identified in the ML limit: 263) |
| Rule in force (`ml_limit_or_firth`) | +0.136 | +0.439 | +0.304 | [+0.164, +0.458] | 0.0% | 0 |
| statsmodels stopping point (point only) | +0.136 | +0.439 | +0.304 | not bootstrapped | n/a | n/a |

Intervals: 10,000 game-cluster resamples, percentile 90%, RNG seed SEED + 40 = 4086943125952605574. Each interval is over the resamples where its quantity is defined, so it is conditional on that: C under the rule in force was defined in 10,000 of 10,000. With 25 games there are 63,205,303,218,876 distinct resamples (10,000 drawn). Under `ml_limit_or_firth`, 263 resamples used Firth because C was undefined in the ML limit (not identified in the ML limit: 263). "Fraction C ≤ 0 (descriptive, not a test)" is the share of the defined resamples with C ≤ 1e-9 (exploratory; H5 registers no such fraction). Firth: `persistgym_h1h3.firth_fe_logit` returned no fit in 1 resamples, and `firth_line_search` gave their estimate (the same penalized likelihood).

**Verdict** (rule in force `ml_limit_or_firth`, estimate from `ml_limit`): **positive: A_deep − A_early > 0 on the point estimate, as H5 predicts (descriptive)**.
- The other estimator (`firth`): C = +0.264, sign positive.
- statsmodels check (point estimate): largest difference from the ML limit 2.2e-10 (within 1e-6).
- Logit-scale interaction γ_Ad − γ_Sd − γ_Ae (§9.3; no reading rests on it): firth +0.588 (90% [-0.728, +1.937]); ml_limit +0.455 (90% [-0.545, +2.709]).
- ML limit: 11 separated rows; predictions early: lcm 46, separated 4; deep: lcm 31, separated 1, lcm-extrapolated 9, separated-extrapolated 1.
- Games by deep support: both 11, Adapter only 10, Standard only 0, neither 4. Share of A_deep's rows in games where only one harness reached deep (an extrapolated counterfactual): 28.7%.

Per level (the registered descriptive table):

| Level | Band | Standard: runs with the level, cleared/reached = P | Provider Adapter: runs, cleared/reached = P |
|---|---|---|---|
| 1 | early | 25, 22/25 = 0.880 | 25, 25/25 = 1.000 |
| 2 | early | 25, 17/22 = 0.773 | 25, 22/25 = 0.880 |
| 3 | level_3 | 25, 11/17 = 0.647 | 25, 21/22 = 0.955 |
| 4 | deep | 25, 7/11 = 0.636 | 25, 20/21 = 0.952 |
| 5 | deep | 25, 3/7 = 0.429 | 25, 16/20 = 0.800 |
| 6 | deep | 25, 3/3 = 1.000 | 25, 12/16 = 0.750 |
| 7 | deep | 16, 2/3 = 0.667 | 16, 8/10 = 0.800 |
| 8 | deep | 11, 0/2 = 0.000 | 11, 6/7 = 0.857 |
| 9 | deep | 5, 0/0 = n/a | 5, 1/1 = 1.000 |
| 10 | deep | 1, 0/0 = n/a | 1, 0/0 = n/a |

Per game:

| Game | Levels | Standard: completed / last reached / ending | Provider Adapter: same | Deep support | Rows early, deep | Δ_early (firth) | Δ_deep (firth) | Δ_early (ml_limit) | Δ_deep (ml_limit) |
|---|---|---|---|---|---|---|---|---|---|
| AR25 | 8 | 6 / 7 / TIME_BUDGET | 8 / 8 / GAME_WIN | both | 4, 9 | +0.013 | +0.245 | +0.004 | +0.218 |
| BP35 | 9 | 0 / 1 / ACTION_BUDGET | 1 / 2 / ACTION_BUDGET | neither | 3, 0 | +0.355 | n/a | +0.414 | n/a |
| CD82 | 6 | 1 / 2 / ACTION_BUDGET | 4 / 5 / ACTION_BUDGET | adapter only | 4, 2 | +0.296 | +0.362 | +0.321 | +0.367 |
| CN04 | 6 | 4 / 5 / TIME_BUDGET | 4 / 5 / TIME_BUDGET | both | 4, 4 | +0.086 | +0.540 | +0.053 | +0.651 |
| DC22 | 6 | 4 / 5 / TIME_BUDGET | 5 / 6 / TIME_BUDGET | both | 4, 5 | +0.075 | +0.532 | +0.045 | +0.640 |
| FT09 | 6 | 2 / 3 / ACTION_BUDGET | 6 / 6 / GAME_WIN | adapter only | 4, 3 | +0.042 | +0.464 | +0.000 | +0.000 |
| G50T | 7 | 0 / 1 / ACTION_BUDGET | 6 / 7 / ACTION_BUDGET | adapter only | 3, 4 | +0.214 | +0.457 | +0.200 | +0.511 |
| KA59 | 7 | 1 / 2 / ACTION_BUDGET | 3 / 4 / ACTION_BUDGET | adapter only | 4, 1 | +0.376 | +0.259 | +0.467 | +0.221 |
| LF52 | 10 | 1 / 2 / ACTION_BUDGET | 1 / 2 / ACTION_BUDGET | neither | 4, 0 | +0.430 | n/a | +0.585 | n/a |
| LP85 | 8 | 7 / 8 / ERROR_OR_CLOSED | 8 / 8 / GAME_WIN | both | 4, 10 | +0.010 | +0.208 | +0.003 | +0.178 |
| LS20 | 7 | 2 / 3 / ERROR_OR_CLOSED | 2 / 3 / ACTION_BUDGET | neither | 4, 0 | +0.131 | n/a | +0.000 | n/a |
| M0R0 | 6 | 2 / 3 / ACTION_BUDGET | 5 / 6 / TIME_BUDGET | adapter only | 4, 3 | +0.135 | +0.529 | +0.101 | +0.633 |
| R11L | 6 | 3 / 4 / ACTION_BUDGET | 6 / 6 / GAME_WIN | both | 4, 4 | +0.059 | +0.510 | +0.030 | +0.595 |
| RE86 | 8 | 4 / 5 / ERROR_OR_CLOSED | 8 / 8 / GAME_WIN | both | 4, 7 | +0.026 | +0.373 | +0.010 | +0.384 |
| S5I5 | 8 | 7 / 8 / ERROR_OR_CLOSED | 8 / 8 / GAME_WIN | both | 4, 10 | +0.010 | +0.208 | +0.003 | +0.178 |
| SB26 | 8 | 1 / 2 / ACTION_BUDGET | 8 / 8 / GAME_WIN | adapter only | 4, 5 | +0.093 | +0.542 | +0.064 | +0.655 |
| SC25 | 6 | 3 / 4 / ERROR_OR_CLOSED | 5 / 6 / ACTION_BUDGET | both | 4, 4 | +0.142 | +0.524 | +0.113 | +0.620 |
| SK48 | 8 | 1 / 2 / TIME_BUDGET | 4 / 5 / TIME_BUDGET | adapter only | 4, 2 | +0.296 | +0.362 | +0.321 | +0.367 |
| SP80 | 6 | 2 / 3 / ACTION_BUDGET | 4 / 5 / ACTION_BUDGET | adapter only | 4, 2 | +0.173 | +0.499 | +0.141 | +0.586 |
| SU15 | 9 | 3 / 4 / TIME_BUDGET | 9 / 9 / GAME_WIN | both | 4, 7 | +0.042 | +0.463 | +0.021 | +0.534 |
| TN36 | 7 | 2 / 3 / ACTION_BUDGET | 6 / 7 / ACTION_BUDGET | adapter only | 4, 4 | +0.110 | +0.541 | +0.079 | +0.651 |
| TR87 | 6 | 0 / 1 / ACTION_BUDGET | 1 / 2 / ACTION_BUDGET | neither | 3, 0 | +0.355 | n/a | +0.414 | n/a |
| TU93 | 9 | 2 / 3 / ACTION_BUDGET | 5 / 6 / ACTION_BUDGET | adapter only | 4, 3 | +0.135 | +0.529 | +0.101 | +0.633 |
| VC33 | 7 | 3 / 4 / ACTION_BUDGET | 7 / 7 / GAME_WIN | both | 4, 5 | +0.052 | +0.494 | +0.026 | +0.573 |
| WA30 | 9 | 4 / 5 / TIME_BUDGET | 7 / 8 / TIME_BUDGET | both | 4, 7 | +0.060 | +0.513 | +0.035 | +0.616 |

**Error-ending sensitivity** (§3 H5):

Same rows minus each reached level a run ended on by an error ending (published ERROR_OR_CLOSED; ours API_ERROR, AGENT_ERROR, UNKNOWN, SCORECARD_CLOSED); budget endings keep theirs. Same seed, so the resamples are paired with the primary's.

Dropped rows: LP85 standard level 8 (ERROR_OR_CLOSED); LS20 standard level 3 (ERROR_OR_CLOSED); RE86 standard level 5 (ERROR_OR_CLOSED); S5I5 standard level 8 (ERROR_OR_CLOSED); SC25 standard level 4 (ERROR_OR_CLOSED).

| Estimator | A_early | A_deep | C = A_deep − A_early | 90% interval of C | Fraction C ≤ 0 (descriptive, not a test) | Resamples left out of C (reasons) |
|---|---|---|---|---|---|---|
| Firth (`firth`) | +0.144 | +0.338 | +0.194 | [+0.037, +0.364] | 2.0% | 1 (Standard reached no deep level: 1) |
| ML limit (`ml_limit`) | +0.136 | +0.357 | +0.221 | [+0.050, +0.405] | 1.5% | 265 (Standard reached no deep level: 1; not identified in the ML limit: 264) |
| Rule in force (`ml_limit_or_firth`) | +0.136 | +0.357 | +0.221 | [+0.051, +0.409] | 1.5% | 1 (Standard reached no deep level: 1) |
| statsmodels stopping point (point only) | +0.136 | +0.357 | +0.221 | not bootstrapped | n/a | n/a |

Verdict on this sensitivity reading: **positive: A_deep − A_early > 0 on the point estimate, as H5 predicts (descriptive)**.

## Our runs, S0 vs S4 on the 4 path games (registered; not blind, R6 change 4)

Games in draw order: FT09, SB26, R11L, CD82; the counted seed-1 run of each (game, config), a re-run replacing its original (§7.5).

| Band | S0: cleared/reached = P(clear \| reached) | S4: cleared/reached = P | Adapter − Standard |
|---|---|---|---|
| early (1-2) | 8/8 = 1.000 | 8/8 = 1.000 | +0.000 |
| level 3 (not in the contrast) | 2/4 = 0.500 | 3/4 = 0.750 | +0.250 |
| deep (≥ 4) | 0/2 = 0.000 | 11/11 = 1.000 | +1.000 |

Raw contrast (r_Ad − r_Sd) − (r_Ae − r_Se) = +1.000 (exploratory: no game adjustment, not the registered model; 90% interval [+1.000, +1.000] over 9,367 defined resamples).

Model: `cleared ~ harness × band + game fixed effects` on the early and deep rows; A_b the average marginal effect over the band's reached rows.

| Estimator | A_early | A_deep | C = A_deep − A_early | 90% interval of C | Fraction C ≤ 0 (descriptive, not a test) | Resamples left out of C (reasons) |
|---|---|---|---|---|---|---|
| Firth (`firth`) | -0.000 | +0.749 | +0.749 | [+0.655, +0.798] | 0.0% | 633 (Standard reached no deep level: 599; no reached row in the deep band: 34) |
| ML limit (`ml_limit`) | +0.000 | undefined (not identified in the ML limit) | undefined (not identified in the ML limit) | [+1.000, +1.000] | 0.0% | 6,888 (Standard reached no deep level: 599; no reached row in the deep band: 34; not identified in the ML limit: 6,255) |
| Rule in force (`ml_limit_or_firth`) | -0.000 | +0.749 | +0.749 | [+0.667, +1.000] | 0.0% | 633 (Standard reached no deep level: 599; no reached row in the deep band: 34) |
| statsmodels stopping point (point only) | +0.000 | +1.000 | +1.000 | not bootstrapped | n/a | n/a |

Intervals: 10,000 game-cluster resamples, percentile 90%, RNG seed SEED + 40 = 4086943125952605574. Each interval is over the resamples where its quantity is defined, so it is conditional on that: C under the rule in force was defined in 9,367 of 10,000. With 4 games there are 35 distinct resamples (35 drawn). Under `ml_limit_or_firth`, 6,255 resamples used Firth because C was undefined in the ML limit (not identified in the ML limit: 6,255). "Fraction C ≤ 0 (descriptive, not a test)" is the share of the defined resamples with C ≤ 1e-9 (exploratory; H5 registers no such fraction). Firth: `persistgym_h1h3.firth_fe_logit` returned no fit in 2,518 resamples, and `firth_line_search` gave their estimate (the same penalized likelihood).
4 games give only 35 distinct resamples (35 drawn).

**Verdict** (rule in force `ml_limit_or_firth`, estimate from `firth`): **positive: A_deep − A_early > 0 on the point estimate, as H5 predicts (descriptive)**.
- Firth decides this reading: C is undefined in the ML limit (not identified in the ML limit).
- The other estimator (`ml_limit`): C = undefined (not identified in the ML limit), sign cannot be computed.
- statsmodels check (point estimate): largest difference from the ML limit 0 (within 1e-6); A_deep: the ML limit is not identified there, so this is the stopping point: path-dependent; not an estimate: A_early +0.000, A_deep +1.000.
- Logit-scale interaction γ_Ad − γ_Sd − γ_Ae (§9.3; no reading rests on it): firth +4.133 (90% [+3.348, +4.657]); ml_limit undefined (not finite in the ML limit) (90% n/a).
- ML limit: 29 separated rows; predictions early: separated 8; deep: separated 5, not identified 1.
- Games by deep support: both 2, Adapter only 1, Standard only 0, neither 1. Share of A_deep's rows in games where only one harness reached deep (an extrapolated counterfactual): 23.1%.

Per level (the registered descriptive table):

| Level | Band | S0: runs with the level, cleared/reached = P | S4: runs, cleared/reached = P |
|---|---|---|---|
| 1 | early | 4, 4/4 = 1.000 | 4, 4/4 = 1.000 |
| 2 | early | 4, 4/4 = 1.000 | 4, 4/4 = 1.000 |
| 3 | level_3 | 4, 2/4 = 0.500 | 4, 3/4 = 0.750 |
| 4 | deep | 4, 0/2 = 0.000 | 4, 3/3 = 1.000 |
| 5 | deep | 4, 0/0 = n/a | 4, 3/3 = 1.000 |
| 6 | deep | 4, 0/0 = n/a | 4, 3/3 = 1.000 |
| 7 | deep | 1, 0/0 = n/a | 1, 1/1 = 1.000 |
| 8 | deep | 1, 0/0 = n/a | 1, 1/1 = 1.000 |

Per game:

| Game | Levels | S0: completed / last reached / ending | S4: same | Deep support | Rows early, deep | Δ_early (firth) | Δ_deep (firth) | Δ_early (ml_limit) | Δ_deep (ml_limit) |
|---|---|---|---|---|---|---|---|---|---|
| FT09 | 6 | 3 / 4 / TIME_BUDGET | 6 / 6 / GAME_WIN | both | 4, 4 | +0.000 | +0.752 | +0.000 | +1.000 |
| SB26 | 8 | 3 / 4 / ACTION_BUDGET | 8 / 8 / GAME_WIN | both | 4, 6 | +0.000 | +0.741 | +0.000 | +1.000 |
| R11L | 6 | 2 / 3 / ACTION_BUDGET | 2 / 3 / ACTION_BUDGET | neither | 4, 0 | +0.000 | n/a | +0.000 | n/a |
| CD82 | 6 | 2 / 3 / TIME_BUDGET | 6 / 6 / GAME_WIN | adapter only | 4, 3 | -0.000 | +0.761 | +0.000 | n/a |

**Error-ending sensitivity** (§3 H5):

Same rows minus each reached level a run ended on by an error ending (published ERROR_OR_CLOSED; ours API_ERROR, AGENT_ERROR, UNKNOWN, SCORECARD_CLOSED); budget endings keep theirs. Same seed, so the resamples are paired with the primary's.

Dropped rows: none.

| Estimator | A_early | A_deep | C = A_deep − A_early | 90% interval of C | Fraction C ≤ 0 (descriptive, not a test) | Resamples left out of C (reasons) |
|---|---|---|---|---|---|---|
| Firth (`firth`) | -0.000 | +0.749 | +0.749 | [+0.655, +0.798] | 0.0% | 633 (Standard reached no deep level: 599; no reached row in the deep band: 34) |
| ML limit (`ml_limit`) | +0.000 | undefined (not identified in the ML limit) | undefined (not identified in the ML limit) | [+1.000, +1.000] | 0.0% | 6,888 (Standard reached no deep level: 599; no reached row in the deep band: 34; not identified in the ML limit: 6,255) |
| Rule in force (`ml_limit_or_firth`) | -0.000 | +0.749 | +0.749 | [+0.667, +1.000] | 0.0% | 633 (Standard reached no deep level: 599; no reached row in the deep band: 34) |
| statsmodels stopping point (point only) | +0.000 | +1.000 | +1.000 | not bootstrapped | n/a | n/a |

Verdict on this sensitivity reading: **positive: A_deep − A_early > 0 on the point estimate, as H5 predicts (descriptive)**.

Runs (S0 and S4; a replaced original is listed and is not in H5):

| Run | Game | Config | Counted | In reading | Exit reasons (agent; launcher) | Ending (D19) | Kind | Levels completed | Last reached | Ended on | Dropped in sensitivity | Flags |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `20261006T144656Z-S4-cd82-s1` | CD82 | S4 | True | True | GAME_WIN; GAME_WIN | GAME_WIN | win | 6 of 6 | 6 | None | - | - |
| `20261006T171726Z-S0-ft09-s1` | FT09 | S0 | False | False | TIME_BUDGET; TIME_BUDGET | TIME_BUDGET | budget | 5 of 6 | 6 | 6 | - | replaced by 20261009T030646Z-S0-ft09-s101, not in H5 |
| `20261007T133444Z-S4-sb26-s1` | SB26 | S4 | True | True | GAME_WIN; GAME_WIN | GAME_WIN | win | 8 of 8 | 8 | None | - | - |
| `20261007T143700Z-S0-sb26-s1` | SB26 | S0 | True | True | ACTION_BUDGET; ACTION_BUDGET | ACTION_BUDGET | budget | 3 of 8 | 4 | 4 | - | - |
| `20261008T013832Z-S0-cd82-s1` | CD82 | S0 | True | True | TIME_BUDGET; TIME_BUDGET | TIME_BUDGET | budget | 2 of 6 | 3 | 3 | - | - |
| `20261008T134155Z-S0-r11l-s1` | R11L | S0 | True | True | ACTION_BUDGET; ACTION_BUDGET | ACTION_BUDGET | budget | 2 of 6 | 3 | 3 | - | - |
| `20261008T212807Z-S4-r11l-s1` | R11L | S4 | True | True | ACTION_BUDGET; ACTION_BUDGET | ACTION_BUDGET | budget | 2 of 6 | 3 | 3 | - | - |
| `20261009T020602Z-S4-ft09-s1` | FT09 | S4 | True | True | GAME_WIN; GAME_WIN | GAME_WIN | win | 6 of 6 | 6 | None | - | - |
| `20261009T030646Z-S0-ft09-s101` | FT09 | S0 | True | True | TIME_BUDGET; TIME_BUDGET | TIME_BUDGET | budget | 3 of 6 | 4 | 4 | - | re-run of 20261006T171726Z-S0-ft09-s1 (D19) |

## Exploratory (§9.10)

### Published runs, effort medium (exploratory)

| Band | Standard: cleared/reached = P(clear \| reached) | Provider Adapter: cleared/reached = P | Adapter − Standard |
|---|---|---|---|
| early (1-2) | 34/47 = 0.723 | 44/49 = 0.898 | +0.175 |
| level 3 (not in the contrast) | 5/12 = 0.417 | 16/20 = 0.800 | +0.383 |
| deep (≥ 4) | 3/8 = 0.375 | 41/51 = 0.804 | +0.429 |

Raw contrast (r_Ad − r_Sd) − (r_Ae − r_Se) = +0.254 (exploratory: no game adjustment, not the registered model; 90% interval [+0.025, +0.589] over 9,958 defined resamples).

| Estimator | A_early | A_deep | C = A_deep − A_early | 90% interval of C | Fraction C ≤ 0 (descriptive, not a test) | Resamples left out of C (reasons) |
|---|---|---|---|---|---|---|
| Firth (`firth`) | +0.189 | +0.506 | +0.317 | [+0.161, +0.420] | 0.6% | 42 (Standard reached no deep level: 42) |
| ML limit (`ml_limit`) | +0.200 | undefined (not identified in the ML limit) | undefined (not identified in the ML limit) | [+0.201, +0.485] | 0.0% | 9,620 (Standard reached no deep level: 42; not identified in the ML limit: 9,578) |
| Rule in force (`ml_limit_or_firth`) | +0.189 | +0.506 | +0.317 | [+0.164, +0.424] | 0.6% | 42 (Standard reached no deep level: 42) |
| statsmodels stopping point (point only) | +0.200 | +0.572 | +0.372 | not bootstrapped | n/a | n/a |

Intervals: 10,000 game-cluster resamples, percentile 90%, RNG seed SEED + 40 = 4086943125952605574. Each interval is over the resamples where its quantity is defined, so it is conditional on that: C under the rule in force was defined in 9,958 of 10,000. With 25 games there are 63,205,303,218,876 distinct resamples (10,000 drawn). Under `ml_limit_or_firth`, 9,578 resamples used Firth because C was undefined in the ML limit (not identified in the ML limit: 9,578). "Fraction C ≤ 0 (descriptive, not a test)" is the share of the defined resamples with C ≤ 1e-9 (exploratory; H5 registers no such fraction). Firth: `persistgym_h1h3.firth_fe_logit` returned no fit in 140 resamples, and `firth_line_search` gave their estimate (the same penalized likelihood).

Sign of C (rule in force `ml_limit_or_firth`; exploratory, no verdict): **positive**; the other estimator's sign: cannot be computed.
Firth decides this reading: C is undefined in the ML limit (not identified in the ML limit).
Games by deep support: both 4, Adapter only 12, Standard only 1, neither 8.

Per level (exploratory):

| Level | Band | Standard: runs with the level, cleared/reached = P | Provider Adapter: runs, cleared/reached = P |
|---|---|---|---|
| 1 | early | 25, 22/25 = 0.880 | 25, 24/25 = 0.960 |
| 2 | early | 25, 12/22 = 0.545 | 25, 20/24 = 0.833 |
| 3 | level_3 | 25, 5/12 = 0.417 | 25, 16/20 = 0.800 |
| 4 | deep | 25, 2/5 = 0.400 | 25, 15/16 = 0.938 |
| 5 | deep | 25, 1/2 = 0.500 | 25, 10/15 = 0.667 |
| 6 | deep | 25, 0/1 = 0.000 | 25, 8/10 = 0.800 |
| 7 | deep | 16, 0/0 = n/a | 16, 4/6 = 0.667 |
| 8 | deep | 11, 0/0 = n/a | 11, 4/4 = 1.000 |
| 9 | deep | 5, 0/0 = n/a | 5, 0/0 = n/a |
| 10 | deep | 1, 0/0 = n/a | 1, 0/0 = n/a |

### Published runs, effort low (exploratory)

| Band | Standard: cleared/reached = P(clear \| reached) | Provider Adapter: cleared/reached = P | Adapter − Standard |
|---|---|---|---|
| early (1-2) | 33/46 = 0.717 | 44/50 = 0.880 | +0.163 |
| level 3 (not in the contrast) | 6/11 = 0.545 | 17/19 = 0.895 | +0.349 |
| deep (≥ 4) | 5/10 = 0.500 | 30/43 = 0.698 | +0.198 |

Raw contrast (r_Ad − r_Sd) − (r_Ae − r_Se) = +0.035 (exploratory: no game adjustment, not the registered model; 90% interval [-0.302, +0.590] over 9,993 defined resamples).

| Estimator | A_early | A_deep | C = A_deep − A_early | 90% interval of C | Fraction C ≤ 0 (descriptive, not a test) | Resamples left out of C (reasons) |
|---|---|---|---|---|---|---|
| Firth (`firth`) | +0.183 | +0.438 | +0.255 | [+0.018, +0.436] | 3.8% | 7 (Standard reached no deep level: 7) |
| ML limit (`ml_limit`) | +0.195 | undefined (not identified in the ML limit) | undefined (not identified in the ML limit) | [+0.023, +0.468] | 2.9% | 8,675 (Standard reached no deep level: 7; not identified in the ML limit: 8,668) |
| Rule in force (`ml_limit_or_firth`) | +0.183 | +0.438 | +0.255 | [+0.022, +0.444] | 3.6% | 7 (Standard reached no deep level: 7) |
| statsmodels stopping point (point only) | +0.195 | +0.536 | +0.341 | not bootstrapped | n/a | n/a |

Intervals: 10,000 game-cluster resamples, percentile 90%, RNG seed SEED + 40 = 4086943125952605574. Each interval is over the resamples where its quantity is defined, so it is conditional on that: C under the rule in force was defined in 9,993 of 10,000. With 25 games there are 63,205,303,218,876 distinct resamples (10,000 drawn). Under `ml_limit_or_firth`, 8,668 resamples used Firth because C was undefined in the ML limit (not identified in the ML limit: 8,668). "Fraction C ≤ 0 (descriptive, not a test)" is the share of the defined resamples with C ≤ 1e-9 (exploratory; H5 registers no such fraction). Firth: `persistgym_h1h3.firth_fe_logit` returned no fit in 69 resamples, and `firth_line_search` gave their estimate (the same penalized likelihood).

Sign of C (rule in force `ml_limit_or_firth`; exploratory, no verdict): **positive**; the other estimator's sign: cannot be computed.
Firth decides this reading: C is undefined in the ML limit (not identified in the ML limit).
Games by deep support: both 6, Adapter only 11, Standard only 0, neither 8.

Per level (exploratory):

| Level | Band | Standard: runs with the level, cleared/reached = P | Provider Adapter: runs, cleared/reached = P |
|---|---|---|---|
| 1 | early | 25, 21/25 = 0.840 | 25, 25/25 = 1.000 |
| 2 | early | 25, 12/21 = 0.571 | 25, 19/25 = 0.760 |
| 3 | level_3 | 25, 6/11 = 0.545 | 25, 17/19 = 0.895 |
| 4 | deep | 25, 1/6 = 0.167 | 25, 12/17 = 0.706 |
| 5 | deep | 25, 1/1 = 1.000 | 25, 7/12 = 0.583 |
| 6 | deep | 25, 1/1 = 1.000 | 25, 5/7 = 0.714 |
| 7 | deep | 16, 1/1 = 1.000 | 16, 3/4 = 0.750 |
| 8 | deep | 11, 1/1 = 1.000 | 11, 3/3 = 1.000 |
| 9 | deep | 5, 0/0 = n/a | 5, 0/0 = n/a |
| 10 | deep | 1, 0/0 = n/a | 1, 0/0 = n/a |

Other models: not computed: the committed pull has Gemini 3.8 Flash only (results slug google-gemini-3-8-flash, 150 sessions).

### Common support, published runs, high effort (exploratory)

Games where both harnesses reached a deep level: AR25, CN04, DC22, LP85, R11L, RE86, S5I5, SC25, SU15, VC33, WA30.

| Band | Standard: cleared/reached = P(clear \| reached) | Provider Adapter: cleared/reached = P | Adapter − Standard |
|---|---|---|---|
| early (1-2) | 22/22 = 1.000 | 22/22 = 1.000 | +0.000 |
| level 3 (not in the contrast) | 11/11 = 1.000 | 11/11 = 1.000 | +0.000 |
| deep (≥ 4) | 15/26 = 0.577 | 42/46 = 0.913 | +0.336 |

Raw contrast (r_Ad − r_Sd) − (r_Ae − r_Se) = +0.336 (exploratory: no game adjustment, not the registered model; 90% interval [+0.235, +0.508] over 10,000 defined resamples).

| Estimator | A_early | A_deep | C = A_deep − A_early | 90% interval of C | Fraction C ≤ 0 (descriptive, not a test) | Resamples left out of C (reasons) |
|---|---|---|---|---|---|---|
| Firth (`firth`) | +0.000 | +0.360 | +0.360 | [+0.254, +0.500] | 0.0% | 0 |
| ML limit (`ml_limit`) | +0.000 | +0.396 | +0.396 | [+0.272, +0.571] | 0.0% | 0 |
| Rule in force (`ml_limit_or_firth`) | +0.000 | +0.396 | +0.396 | [+0.272, +0.571] | 0.0% | 0 |
| statsmodels stopping point (point only) | +0.000 | +0.396 | +0.396 | not bootstrapped | n/a | n/a |

Intervals: 10,000 game-cluster resamples, percentile 90%, RNG seed SEED + 40 = 4086943125952605574. Each interval is over the resamples where its quantity is defined, so it is conditional on that: C under the rule in force was defined in 10,000 of 10,000. With 11 games there are 352,716 distinct resamples (9,525 drawn). Under `ml_limit_or_firth`, 0 resamples used Firth because C was undefined in the ML limit. "Fraction C ≤ 0 (descriptive, not a test)" is the share of the defined resamples with C ≤ 1e-9 (exploratory; H5 registers no such fraction).

Sign of C (rule in force `ml_limit_or_firth`; exploratory, no verdict): **positive**; the other estimator's sign: positive.
Games by deep support: both 11, Adapter only 0, Standard only 0, neither 0.

Per level (exploratory):

| Level | Band | Standard: runs with the level, cleared/reached = P | Provider Adapter: runs, cleared/reached = P |
|---|---|---|---|
| 1 | early | 11, 11/11 = 1.000 | 11, 11/11 = 1.000 |
| 2 | early | 11, 11/11 = 1.000 | 11, 11/11 = 1.000 |
| 3 | level_3 | 11, 11/11 = 1.000 | 11, 11/11 = 1.000 |
| 4 | deep | 11, 7/11 = 0.636 | 11, 11/11 = 1.000 |
| 5 | deep | 11, 3/7 = 0.429 | 11, 10/11 = 0.909 |
| 6 | deep | 11, 3/3 = 1.000 | 11, 8/10 = 0.800 |
| 7 | deep | 7, 2/3 = 0.667 | 7, 7/7 = 1.000 |
| 8 | deep | 6, 0/2 = 0.000 | 6, 5/6 = 0.833 |
| 9 | deep | 2, 0/0 = n/a | 2, 1/1 = 1.000 |

### Common support, our runs (exploratory)

Games where both harnesses reached a deep level: FT09, SB26.

| Band | S0: cleared/reached = P(clear \| reached) | S4: cleared/reached = P | Adapter − Standard |
|---|---|---|---|
| early (1-2) | 4/4 = 1.000 | 4/4 = 1.000 | +0.000 |
| level 3 (not in the contrast) | 2/2 = 1.000 | 2/2 = 1.000 | +0.000 |
| deep (≥ 4) | 0/2 = 0.000 | 8/8 = 1.000 | +1.000 |

Raw contrast (r_Ad − r_Sd) − (r_Ae − r_Se) = +1.000 (exploratory: no game adjustment, not the registered model; 90% interval [+1.000, +1.000] over 10,000 defined resamples).

| Estimator | A_early | A_deep | C = A_deep − A_early | 90% interval of C | Fraction C ≤ 0 (descriptive, not a test) | Resamples left out of C (reasons) |
|---|---|---|---|---|---|---|
| Firth (`firth`) | -0.000 | +0.742 | +0.742 | [+0.725, +0.756] | 0.0% | 0 |
| ML limit (`ml_limit`) | +0.000 | +1.000 | +1.000 | [+1.000, +1.000] | 0.0% | 0 |
| Rule in force (`ml_limit_or_firth`) | +0.000 | +1.000 | +1.000 | [+1.000, +1.000] | 0.0% | 0 |
| statsmodels stopping point (point only) | +0.000 | +1.000 | +1.000 | not bootstrapped | n/a | n/a |

Intervals: 10,000 game-cluster resamples, percentile 90%, RNG seed SEED + 40 = 4086943125952605574. Each interval is over the resamples where its quantity is defined, so it is conditional on that: C under the rule in force was defined in 10,000 of 10,000. With 2 games there are 3 distinct resamples (3 drawn). Under `ml_limit_or_firth`, 0 resamples used Firth because C was undefined in the ML limit. "Fraction C ≤ 0 (descriptive, not a test)" is the share of the defined resamples with C ≤ 1e-9 (exploratory; H5 registers no such fraction).

Sign of C (rule in force `ml_limit_or_firth`; exploratory, no verdict): **positive**; the other estimator's sign: positive.
Games by deep support: both 2, Adapter only 0, Standard only 0, neither 0.

Per level (exploratory):

| Level | Band | S0: runs with the level, cleared/reached = P | S4: runs, cleared/reached = P |
|---|---|---|---|
| 1 | early | 2, 2/2 = 1.000 | 2, 2/2 = 1.000 |
| 2 | early | 2, 2/2 = 1.000 | 2, 2/2 = 1.000 |
| 3 | level_3 | 2, 2/2 = 1.000 | 2, 2/2 = 1.000 |
| 4 | deep | 2, 0/2 = 0.000 | 2, 2/2 = 1.000 |
| 5 | deep | 2, 0/0 = n/a | 2, 2/2 = 1.000 |
| 6 | deep | 2, 0/0 = n/a | 2, 2/2 = 1.000 |
| 7 | deep | 1, 0/0 = n/a | 1, 1/1 = 1.000 |
| 8 | deep | 1, 0/0 = n/a | 1, 1/1 = 1.000 |

## Checks

- No warnings.

## What it does not show

- **Not blind.** On the published data, the per-game scores, LP85's ending and the inferred endings were seen, and the operational slice revealed each run's last level. Our S0 and S4 runs were seen before R6 (§17.6 change 4).
- **Observational, one run per game and harness.** Depth is confounded with game difficulty beyond the game fixed effects and with level difficulty within a game, and run-to-run variation is not separated from the harness.
- **Conditioning on reached is selection by the harness.** The harness that gets further reaches deep levels more often, so A_deep compares harnesses over different selections of runs. It is not the harness's effect on clearing a fixed level.
- **Extrapolation.** Part of A_deep rests on games where only one harness reached deep (share of the deep rows: published 28.7%; ours 23.1%), through the model's counterfactual for the other harness; the common-support reading is exploratory.
- **The estimator matters at this size.** Firth's estimate and the maximum-likelihood limit can differ in size and in sign; both are shown, and the rule in force is named.
- **Endings.** Published endings are inferred, and ERROR_OR_CLOSED pools errors with stops from outside the harness. The clock and the action budget leave the last level in play reached and not cleared when it had an action, so a slower pace lowers P(clear | reached) at the last level reached (R5).
- **Our 4 games are selected, so our reading is conditional.** The path games were chosen by D14's rule (§7.2): published high-effort gap ≥ 20, both published runs ≤ $60, and a normal Standard-high ending. They are games where the Adapter is known to help, so H5 on our runs is conditional on "games where the Adapter helps" (§7.2, PLAN §8.3), and the Adapter's advantage there may be larger than on the public set. Our S0 also differs from ARC's Standard (thought summaries, API surface, period; §15).
- **The data sets overlap.** The 4 path games are among the 25 published games, so the two readings are not independent.
- **Descriptive only.** Percentile intervals, 35 distinct resamples for our 4 games, and no claim of statistical significance (H5 is outside the Holm family); "Fraction C ≤ 0 (descriptive, not a test)" and the raw pooled contrast are exploratory.
- **Narrow.** One model at high effort; other efforts are exploratory; no other model was pulled; nothing here compares models.

This script was written and tested on synthetic data only before its first real run.
