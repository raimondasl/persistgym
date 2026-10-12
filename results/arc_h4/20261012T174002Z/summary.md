# H4 on the ARC path runs (PREREG §3 H4, as amended by R6, §17.6 change 3)

Computed 2026-10-12T17:40:02+00:00 at commit 0a1fd20 (dirty: False) by `uv run python -m analysis.arc_h4 --with-s1`, from `results`. Descriptive only: 4 units, no significance claims (§3 H4, D34).

**Status: FINAL.**

**Units:** the 4 path games (FT09, SB26, R11L, CD82) at replicate 1, each config's counted run (§7.5: a re-run replaces its original; R7: an R7 replacement replaces an S1 or S2 run that ended by the summarizer failure, and its own re-run replaces it).
**Configs:** S0, S1, S2, S4, with `--with-s1`: the analyst passes it only if `results/decisions.md` records "S1: yes", merged to `main` before the first block-3 ARC run (§17.6 change 1).

## Primary reading: the scorecard's RHAE

| Game | RHAE S0 | RHAE S1 | RHAE S2 | RHAE S4 | S1 − S0 | S2 − S1 | S4 − S2 | S4 − S0 |
|---|---|---|---|---|---|---|---|---|
| FT09 | 18.11 | 100.00 | 18.06 | 100.00 | 81.89 | -81.94 | 81.94 | 81.89 |
| SB26 | 5.44 | 100.00 | 100.00 | 100.00 | 94.56 | 0.00 | 0.00 | 94.56 |
| R11L | 6.45 | 11.21 | 14.29 | 14.29 | 4.75 | 3.08 | 0.00 | 7.83 |
| CD82 | 6.94 | 41.11 | 12.95 | 73.02 | 34.17 | -28.16 | 60.07 | 66.08 |
| **Mean (R̄_c)** | **9.24** | **63.08** | **36.32** | **71.83** | 53.84 | -26.76 | 35.50 | **62.59** |

G = R̄_S4 − R̄_S0 = **62.59** RHAE over 4 units (90% interval [29.51, 87.44]; resamples with G ≤ 0: 0.00%). Shares are reported because G ≥ 10 (D34).

| Share | Point estimate | 90% interval |
|---|---|---|
| σ_loss (S0→S1: loss policy) | 0.860 | [0.541, 1.000] |
| σ_notes (S1→S2: notes removal) | -0.427 | [-0.879, 0.011] |
| σ_replay (S2→S4: native replay and its item format; under R7 also the summary budget, see the note on R7) | 0.567 | [0.000, 0.960] |

**σ_replay under R7** (§17.7 change 4): S2→S4 also changes the summary budget, from S2's 65,536 to S4's 8,192 output tokens (3 of the 4 counted S2 runs played under 65,536). In every S4 run of block 2 the 8,192 budget never bound: 132 summaries, 0 retries, at most 3,073 output tokens per attempt (from those runs' harness compaction records). So for the counted S4 runs the step still differs only by native replay and its item format.

- **Prediction A** (σ_loss ≥ 1/3, σ_replay ≤ 1/2, −0.10 ≤ σ_notes ≤ 0.10): **does not hold** (sigma_loss >= 1/3: met; sigma_replay <= 1/2: not met; -0.10 <= sigma_notes <= 0.10: not met).
- **Prediction B** (σ_replay ≥ 1/2): **holds**.
- Which hold: **B only**.
- D30, descriptive: σ_replay ≥ 2/3: **no**.

Intervals: 10,000 resamples of the 4 units with replacement, a unit's configs kept together; percentile 90% intervals; RNG seed SEED + 30 = 4086943125952605564. With 4 units there are only 35 distinct resamples (35 drawn here), so the intervals are coarse. Descriptive only.

Leave one game out:

| Game left out | G over the others | σ_replay |
|---|---|---|
| FT09 | 56.16 | 0.357 |
| SB26 | 51.93 | 0.911 |
| R11L | 80.84 | 0.586 |
| CD82 | 61.43 | 0.445 |

## Sensitivity analyses (§3 H4, as frozen)

| Reading | Units | R̄_S0 | R̄_S1 | R̄_S2 | R̄_S4 | G | σ_loss | σ_notes | σ_replay | σ_replay 90% | B | A |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Primary (for reference) | 4 | 9.24 | 63.08 | 36.32 | 71.83 | 62.59 | 0.860 | -0.427 | 0.567 | [0.000, 0.960] | holds | no |
| Original runs instead of re-runs | 4 | 19.25 | 56.37 | 36.57 | 71.83 | 52.57 | 0.706 | -0.377 | 0.671 | [0.172, 1.531] | holds | no |
| Counted runs without R7 (replaced runs back) | 4 | 9.24 | 63.08 | 49.67 | 71.83 | 62.59 | 0.860 | -0.214 | 0.354 | [0.000, 0.745] | no | no |
| Units with a COST_CAP ending left out | 4 | 9.24 | 63.08 | 36.32 | 71.83 | 62.59 | 0.860 | -0.427 | 0.567 | [0.000, 0.960] | holds | no |

σ_replay here: in a reading whose S2 runs include one under 65,536, S2→S4 also lowers the summary budget (the note on R7 under the primary reading).

Original runs used (each chain's first run): FT09 S0: `20261006T171726Z-S0-ft09-s1` (RHAE 58.17) for the counted run `20261009T030646Z-S0-ft09-s101` (18.11); FT09 S2: `20261010T020247Z-S2-ft09-s1` (RHAE 28.57) for the counted run `20261010T202129Z-S2-ft09-s201` (18.06); R11L S2: `20261010T084933Z-S2-r11l-s1` (RHAE 4.76) for the counted run `20261010T103451Z-S2-r11l-s101` (14.29); CD82 S1: `20261011T030015Z-S1-cd82-s1` (RHAE 14.29) for the counted run `20261011T053855Z-S1-cd82-s101` (41.11).

Runs without R7 used: FT09 S2: `20261010T030159Z-S2-ft09-s101` (RHAE 71.43, summary budget 8,192) for `20261010T202129Z-S2-ft09-s201` (18.06, 65,536).

## At K = 150 actions (PREREG §17.5; secondary, descriptive)

The predictions are judged on the primary reading only; their conditions at K are reported, not judged. Censored runs enter at their final values, which are lower bounds.

| Game | RHAE_150 S0 | RHAE_150 S1 | RHAE_150 S2 | RHAE_150 S4 | S1 − S0 | S2 − S1 | S4 − S2 | S4 − S0 |
|---|---|---|---|---|---|---|---|---|
| FT09 | 18.11 | 100.00 | 18.06 | 100.00 | 81.89 | -81.94 | 81.94 | 81.89 |
| SB26 | 5.44 | 100.00 | 53.95 | 100.00 | 94.56 | -46.05 | 46.05 | 94.56 |
| R11L | 6.45 | 11.21 | 14.29 | 14.29 | 4.75 | 3.08 | 0.00 | 7.83 |
| CD82 | 6.94 | 19.21 | 12.95 | 38.46 | 12.27 | -6.26 | 25.51 | 31.52 |
| **Mean (R̄_c)** | **9.24** | **57.60** | **24.81** | **63.19** | 48.37 | -32.79 | 38.38 | **53.95** |

G = R̄_S4 − R̄_S0 = **53.95** RHAE over 4 units (90% interval [25.60, 85.05]; resamples with G ≤ 0: 0.00%). Shares are reported because G ≥ 10 (D34).

| Share | Point estimate | 90% interval |
|---|---|---|
| σ_loss (S0→S1: loss policy) | 0.897 | [0.482, 1.000] |
| σ_notes (S1→S2: notes removal) | -0.608 | [-0.879, -0.153] |
| σ_replay (S2→S4: native replay and its item format; under R7 also the summary budget, see the note on R7) | 0.711 | [0.464, 0.947] |

σ_replay under R7: see the note above.

- **Prediction A** (σ_loss ≥ 1/3, σ_replay ≤ 1/2, −0.10 ≤ σ_notes ≤ 0.10) (condition at K, reported only): **does not hold** (sigma_loss >= 1/3: met; sigma_replay <= 1/2: not met; -0.10 <= sigma_notes <= 0.10: not met).
- **Prediction B** (σ_replay ≥ 1/2) (condition at K, reported only): **holds**.
- Which hold: **B only**.
- D30, descriptive: σ_replay ≥ 2/3: **yes** (dominated by the replay step, the step with no provider-neutral analogue).

Intervals: 10,000 resamples of the 4 units with replacement, a unit's configs kept together; percentile 90% intervals; RNG seed SEED + 30 = 4086943125952605564. With 4 units there are only 35 distinct resamples (35 drawn here), so the intervals are coarse. Descriptive only.

Leave one game out:

| Game left out | G over the others | σ_replay |
|---|---|---|
| FT09 | 44.64 | 0.534 |
| SB26 | 40.41 | 0.886 |
| R11L | 69.32 | 0.738 |
| CD82 | 61.43 | 0.695 |

Censored counted runs (lower bounds): S0 0, S1 0, S2 0, S4 0. Mean levels cleared within K: S0 2.50, S1 4.75, S2 3.25, S4 5.00; S4 − S0: 2.50.

| Reading | Units | R̄_S0 | R̄_S1 | R̄_S2 | R̄_S4 | G | σ_loss | σ_notes | σ_replay | σ_replay 90% | B | A |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Lower bounds | 4 | 9.24 | 57.60 | 24.81 | 63.19 | 53.95 | 0.897 | -0.608 | 0.711 | [0.464, 0.947] | holds | no |
| Censored units left out | 4 | 9.24 | 57.60 | 24.81 | 63.19 | 53.95 | 0.897 | -0.608 | 0.711 | [0.464, 0.947] | holds | no |
| Original runs instead of re-runs | 4 | 8.98 | 56.37 | 25.06 | 63.19 | 54.21 | 0.874 | -0.578 | 0.703 | [0.543, 0.892] | holds | no |
| Counted runs without R7 (replaced runs back) | 4 | 9.24 | 57.60 | 38.15 | 63.19 | 53.95 | 0.897 | -0.361 | 0.464 | [0.338, 0.648] | no | no |
| Units with a COST_CAP ending left out | 4 | 9.24 | 57.60 | 24.81 | 63.19 | 53.95 | 0.897 | -0.608 | 0.711 | [0.464, 0.947] | holds | no |

Censored counted runs per reading: lower bounds: S0 0, S1 0, S2 0, S4 0; censored units left out: S0 0, S1 0, S2 0, S4 0; original runs instead of re-runs: S0 0, S1 1, S2 2, S4 0; counted runs without R7 (replaced runs back): S0 0, S1 0, S2 1, S4 0; units with a COST_CAP ending left out: S0 0, S1 0, S2 0, S4 0.

## Runs

| Run | Game | Config | Rep. | Counted | In reading | Ending: agent; exit | D19 | RHAE | Levels | Actions | Median s per call | Model returned | Config hash (summary budget) | context_trims | Flags |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `20261006T144656Z-S4-cd82-s1` | CD82 | S4 | 1 | True | True | GAME_WIN; GAME_WIN | GAME_WIN | 73.02 | 6 of 6 | 206 | 17.36 | gemini-3.8-flash | `e7432aafd0ad` (8,192) | n/a | - |
| `20261006T171726Z-S0-ft09-s1` | FT09 | S0 | 1 | False | False | TIME_BUDGET; TIME_BUDGET | TIME_BUDGET | 58.17 | 5 of 6 | 236 | 181.25 | gemini-3.8-flash | `615ea035324f` (none) | n/a | replaced by 20261009T030646Z-S0-ft09-s101 (the originals sensitivity analysis only) |
| `20261007T133444Z-S4-sb26-s1` | SB26 | S4 | 1 | True | True | GAME_WIN; GAME_WIN | GAME_WIN | 100.00 | 8 of 8 | 138 | 12.96 | gemini-3.8-flash | `e7432aafd0ad` (8,192) | n/a | - |
| `20261007T143700Z-S0-sb26-s1` | SB26 | S0 | 1 | True | True | ACTION_BUDGET; ACTION_BUDGET | ACTION_BUDGET | 5.44 | 3 of 8 | 238 | 156.68 | gemini-3.8-flash | `615ea035324f` (none) | n/a | - |
| `20261008T013832Z-S0-cd82-s1` | CD82 | S0 | 1 | True | True | TIME_BUDGET; TIME_BUDGET | TIME_BUDGET | 6.94 | 2 of 6 | 235 | 170.06 | gemini-3.8-flash | `615ea035324f` (none) | n/a | - |
| `20261008T134155Z-S0-r11l-s1` | R11L | S0 | 1 | True | True | ACTION_BUDGET; ACTION_BUDGET | ACTION_BUDGET | 6.45 | 2 of 6 | 365 | 50.98 | gemini-3.8-flash | `615ea035324f` (none) | n/a | - |
| `20261008T212807Z-S4-r11l-s1` | R11L | S4 | 1 | True | True | ACTION_BUDGET; ACTION_BUDGET | ACTION_BUDGET | 14.29 | 2 of 6 | 281 | 31.55 | gemini-3.8-flash | `e7432aafd0ad` (8,192) | n/a | - |
| `20261009T020602Z-S4-ft09-s1` | FT09 | S4 | 1 | True | True | GAME_WIN; GAME_WIN | GAME_WIN | 100.00 | 6 of 6 | 112 | 9.05 | gemini-3.8-flash | `e7432aafd0ad` (8,192) | n/a | - |
| `20261009T030646Z-S0-ft09-s101` | FT09 | S0 | 1 | True | True | TIME_BUDGET; TIME_BUDGET | TIME_BUDGET | 18.11 | 3 of 6 | 214 | 175.95 | gemini-3.8-flash | `615ea035324f` (none) | n/a | - |
| `20261010T005046Z-S1-sb26-s1` | SB26 | S1 | 1 | True | True | GAME_WIN; GAME_WIN | GAME_WIN | 100.00 | 8 of 8 | 131 | 15.47 | gemini-3.8-flash | `d2f7825fab54` (8,192) | 0 | - |
| `20261010T020247Z-S2-ft09-s1` | FT09 | S2 | 1 | False | False | AGENT_ERROR; AGENT_ERROR | AGENT_ERROR | 28.57 | 3 of 6 | 49 | 35.86 | gemini-3.8-flash | `2f0dd011bc04` (8,192) | 0 | replaced by 20261010T030159Z-S2-ft09-s101 (the originals sensitivity analysis only) |
| `20261010T030159Z-S2-ft09-s101` | FT09 | S2 | 1 | False | False | AGENT_ERROR; AGENT_ERROR | AGENT_ERROR | 71.43 | 5 of 6 | 112 | 85.80 | gemini-3.8-flash | `2f0dd011bc04` (8,192) | 0 | replaced by its R7 replacement 20261010T202129Z-S2-ft09-s201 (the R7 sensitivity analysis only) |
| `20261010T071105Z-S1-ft09-s1` | FT09 | S1 | 1 | True | True | GAME_WIN; GAME_WIN | GAME_WIN | 100.00 | 6 of 6 | 92 | 23.41 | gemini-3.8-flash | `d2f7825fab54` (8,192) | 0 | - |
| `20261010T084933Z-S2-r11l-s1` | R11L | S2 | 1 | False | False | AGENT_ERROR; AGENT_ERROR | AGENT_ERROR | 4.76 | 1 of 6 | 28 | 188.05 | gemini-3.8-flash | `2f0dd011bc04` (8,192) | 0 | replaced by 20261010T103451Z-S2-r11l-s101 (the originals sensitivity analysis only) |
| `20261010T103451Z-S2-r11l-s101` | R11L | S2 | 1 | True | True | ACTION_BUDGET; ACTION_BUDGET | ACTION_BUDGET | 14.29 | 2 of 6 | 286 | 93.76 | gemini-3.8-flash | `2f0dd011bc04` (8,192) | 0 | - |
| `20261010T202129Z-S2-ft09-s201` | FT09 | S2 | 1 | True | True | ACTION_BUDGET; ACTION_BUDGET | ACTION_BUDGET | 18.06 | 3 of 6 | 219 | 80.94 | gemini-3.8-flash | `c41dc494a105` (65,536) | 0 | R7 replacement of 20261010T030159Z-S2-ft09-s101 |
| `20261011T030015Z-S1-cd82-s1` | CD82 | S1 | 1 | False | False | AGENT_ERROR; AGENT_ERROR | AGENT_ERROR | 14.29 | 2 of 6 | 87 | 62.81 | gemini-3.8-flash | `cd475ca08341` (65,536) | 0 | replaced by 20261011T053855Z-S1-cd82-s101 (the originals sensitivity analysis only) |
| `20261011T053855Z-S1-cd82-s101` | CD82 | S1 | 1 | True | True | AGENT_ERROR; AGENT_ERROR | AGENT_ERROR | 41.11 | 4 of 6 | 210 | 43.28 | gemini-3.8-flash | `cd475ca08341` (65,536) | 0 | re-run also ended re-run-eligible: counted as is (D19) |
| `20261011T105637Z-S2-cd82-s1` | CD82 | S2 | 1 | True | True | ACTION_BUDGET; ACTION_BUDGET | ACTION_BUDGET | 12.95 | 2 of 6 | 297 | 81.03 | gemini-3.8-flash | `c41dc494a105` (65,536) | 0 | - |
| `20261011T205715Z-S1-r11l-s1` | R11L | S1 | 1 | True | True | ACTION_BUDGET; ACTION_BUDGET | ACTION_BUDGET | 11.21 | 2 of 6 | 325 | 80.80 | gemini-3.8-flash | `cd475ca08341` (65,536) | 0 | - |
| `20261012T150200Z-S2-sb26-s1` | SB26 | S2 | 1 | True | True | GAME_WIN; GAME_WIN | GAME_WIN | 100.00 | 8 of 8 | 175 | 18.14 | gemini-3.8-flash | `c41dc494a105` (65,536) | 0 | - |

## Checks

- context_trims of the S1 and S2 runs (patch 0016: should be 0): 0 in 12 of 12.
- CD82 S1: re-run 20261011T053855Z-S1-cd82-s101 also ended AGENT_ERROR, re-run-eligible: it is counted as is, flagged (D19 allows no second re-run)

## What it does not show

- **One seed per game and config.** An original and its re-run of one unit show how far two runs can differ (FT09 S0: 58.17 vs 18.11, 40.06 RHAE apart; FT09 S2: 28.57 vs 71.43, 42.86 RHAE apart; R11L S2: 4.76 vs 14.29, 9.52 RHAE apart; CD82 S1: 14.29 vs 41.11, 26.82 RHAE apart). Shares from 4 units are descriptive and coarse: 4 units give only 35 distinct bootstrap resamples.
- **A time confound.** The configs ran on different days (S0 2026-10-07 to 2026-10-09; S1 2026-10-10 to 2026-10-11; S2 2026-10-10 to 2026-10-12; S4 2026-10-06 to 2026-10-09). Gemini 3.8 Flash has no dated snapshot, and its latency drifted (§17.6 change 5). The run table gives the returned model string and the median seconds per call for every run.
- **R7 changed S1's and S2's summary budget mid-block** (8,192 to 65,536 output tokens): of the 8 counted S1 and S2 runs, 5 played under 65,536 and 3 under 8,192, so a mean over units can mix two versions of a config. The R7 sensitivity analysis puts back the runs the R7 replacements replaced, and the originals analysis each chain's first run; the value of a run that ended in the summarizer failure is a lower bound of what it would have scored had it gone on, not what the old config scores when its summary succeeds.
- **D20's yardsticks pool both versions** (§17.7 change 5): D20 judges each S1 or S2 run's seconds per model call against its config's earlier counted runs, whether they played under 8,192 or 65,536, so a run can be judged against runs of the other version; whether the budget changes the seconds per call is not measured here.
- **No StateCarry evidence,** no sol replication of H1, no failure labels and no open-weights run: each was planned and not run (§17.6 change 1).
- **H5 on our runs is not blind** (§17.6 change 4); it is not computed here.
- **The readings at K are secondary.** The slow configs are the ones censored, so neither the lower bounds nor leaving censored units out is unbiased (§17.5).
- **Narrow.** One model at high thinking, two harness configs and the steps between them, on 4 games chosen for a large published Standard-to-Adapter gap (§7.2). Nothing here compares models.
