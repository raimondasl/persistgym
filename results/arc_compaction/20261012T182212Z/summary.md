# Failures after a history compaction (exploratory; PLAN A9)

Computed 2026-10-12T18:22:12+00:00 at commit 7a933fd (dirty: False). **Exploratory** (PREREG §9.10): no test, no verdict; it enters no hypothesis, gate or kill rule.

Window: the first 5 steps after a compaction (K = 10 as a sensitivity reading); "other": every other step, including those before the first compaction. Counted runs of each config on the 4 path games; replaced runs below.

## S1 (counted runs: 4)

Compactions: 120 over 758 steps, one every 6.3 steps.

| Band | Steps in window / other | Clears per step, window / other | Unusable replies per call, window / other |
|---|---|---|---|
| early (K = 5) | 108 / 66 | 0.037 (4) / 0.061 (4) | 0.018 (2) / 0.015 (1) |
| level 3 (K = 5) | 273 / 96 | 0.011 (3) / 0.000 (0) | 0.042 (12) / 0.010 (1) |
| deep (K = 5) | 156 / 59 | 0.038 (6) / 0.051 (3) | 0.031 (5) / 0.017 (1) |
| all (K = 5) | 537 / 221 | 0.024 (13) / 0.032 (7) | 0.034 (19) / 0.013 (3) |
| early (K = 10) | 139 / 35 | 0.036 (5) / 0.086 (3) | 0.021 (3) / 0.000 (0) |
| level 3 (K = 10) | 363 / 6 | 0.008 (3) / 0.000 (0) | 0.035 (13) / 0.000 (0) |
| deep (K = 10) | 202 / 13 | 0.035 (7) / 0.154 (2) | 0.029 (6) / 0.000 (0) |
| all (K = 10) | 704 / 54 | 0.021 (15) / 0.093 (5) | 0.030 (22) / 0.000 (0) |

## S2 (counted runs: 4)

Compactions: 142 over 977 steps, one every 6.9 steps.

| Band | Steps in window / other | Clears per step, window / other | Unusable replies per call, window / other |
|---|---|---|---|
| early (K = 5) | 120 / 60 | 0.025 (3) / 0.083 (5) | 0.040 (5) / 0.048 (3) |
| level 3 (K = 5) | 363 / 182 | 0.003 (1) / 0.005 (1) | 0.008 (3) / 0.032 (6) |
| deep (K = 5) | 165 / 87 | 0.030 (5) / 0.000 (0) | 0.000 (0) / 0.000 (0) |
| all (K = 5) | 648 / 329 | 0.014 (9) / 0.018 (6) | 0.012 (8) / 0.027 (9) |
| early (K = 10) | 145 / 35 | 0.041 (6) / 0.057 (2) | 0.033 (5) / 0.079 (3) |
| level 3 (K = 10) | 524 / 21 | 0.004 (2) / 0.000 (0) | 0.017 (9) / 0.000 (0) |
| deep (K = 10) | 223 / 29 | 0.022 (5) / 0.000 (0) | 0.000 (0) / 0.000 (0) |
| all (K = 10) | 892 / 85 | 0.015 (13) / 0.024 (2) | 0.015 (14) / 0.034 (3) |

## S4 (counted runs: 4)

Compactions: 132 over 737 steps, one every 5.6 steps.

| Band | Steps in window / other | Clears per step, window / other | Unusable replies per call, window / other |
|---|---|---|---|
| early (K = 5) | 67 / 36 | 0.090 (6) / 0.056 (2) | 0.000 (0) / 0.000 (0) |
| level 3 (K = 5) | 295 / 39 | 0.010 (3) / 0.000 (0) | 0.000 (0) / 0.000 (0) |
| deep (K = 5) | 228 / 72 | 0.039 (9) / 0.028 (2) | 0.000 (0) / 0.000 (0) |
| all (K = 5) | 590 / 147 | 0.031 (18) / 0.027 (4) | 0.000 (0) / 0.000 (0) |
| early (K = 10) | 76 / 27 | 0.092 (7) / 0.037 (1) | 0.000 (0) / 0.000 (0) |
| level 3 (K = 10) | 332 / 2 | 0.009 (3) / 0.000 (0) | 0.000 (0) / 0.000 (0) |
| deep (K = 10) | 292 / 8 | 0.034 (10) / 0.125 (1) | 0.000 (0) / 0.000 (0) |
| all (K = 10) | 700 / 37 | 0.029 (20) / 0.054 (2) | 0.000 (0) / 0.000 (0) |

## Replaced runs (D19 originals and R7-replaced runs; not counted)

- S1 (20261011T030015Z-S1-cd82-s1), all bands, K = 5: clears per step 0.017 / 0.037; unusable per call 0.130 / 0.100 (window / other).
- S2 (20261010T020247Z-S2-ft09-s1, 20261010T030159Z-S2-ft09-s101, 20261010T084933Z-S2-r11l-s1), all bands, K = 5: clears per step 0.024 / 0.065; unusable per call 0.000 / 0.009 (window / other).

## Where each run ended

| Run | Config | Counted | Ending | Levels | Last step | Compactions | Steps since last compaction | Unusable replies | Summarizer failure |
|---|---|---|---|---|---|---|---|---|---|
| `20261006T144656Z-S4-cd82-s1` | S4 | True | GAME_WIN | 6 | 206 | 33 | 6 | 0 | False |
| `20261007T133444Z-S4-sb26-s1` | S4 | True | GAME_WIN | 8 | 138 | 36 | 2 | 0 | False |
| `20261008T212807Z-S4-r11l-s1` | S4 | True | ACTION_BUDGET | 2 | 281 | 53 | 2 | 0 | False |
| `20261009T020602Z-S4-ft09-s1` | S4 | True | GAME_WIN | 6 | 112 | 10 | 11 | 0 | False |
| `20261010T005046Z-S1-sb26-s1` | S1 | True | GAME_WIN | 8 | 131 | 33 | 2 | 0 | False |
| `20261010T020247Z-S2-ft09-s1` | S2 | False | AGENT_ERROR | 3 | 49 | 3 | 9 | 0 | True |
| `20261010T030159Z-S2-ft09-s101` | S2 | False | AGENT_ERROR | 5 | 112 | 9 | 10 | 1 | True |
| `20261010T071105Z-S1-ft09-s1` | S1 | True | GAME_WIN | 6 | 92 | 7 | 5 | 1 | False |
| `20261010T084933Z-S2-r11l-s1` | S2 | False | AGENT_ERROR | 1 | 28 | 6 | 3 | 0 | True |
| `20261010T103451Z-S2-r11l-s101` | S2 | True | ACTION_BUDGET | 2 | 286 | 46 | 6 | 3 | False |
| `20261010T202129Z-S2-ft09-s201` | S2 | True | ACTION_BUDGET | 3 | 219 | 17 | 13 | 1 | False |
| `20261011T030015Z-S1-cd82-s1` | S1 | False | AGENT_ERROR | 2 | 87 | 13 | 3 | 12 | False |
| `20261011T053855Z-S1-cd82-s101` | S1 | True | AGENT_ERROR | 4 | 210 | 31 | 3 | 14 | False |
| `20261011T105637Z-S2-cd82-s1` | S2 | True | ACTION_BUDGET | 2 | 297 | 36 | 4 | 12 | False |
| `20261011T205715Z-S1-r11l-s1` | S1 | True | ACTION_BUDGET | 2 | 325 | 49 | 4 | 7 | False |
| `20261012T150200Z-S2-sb26-s1` | S2 | True | GAME_WIN | 8 | 175 | 43 | 2 | 1 | False |

## What it does not show

- **No causal effect of compaction.** Compactions come at fixed context sizes, the points where play has run longest, so time into the run is confounded with time since a compaction; the window and the other steps also differ in level and band.
- **Compactions are frequent** (the rate per config above), so the window covers most steps and the "other" group is small, especially at K = 10: the comparison is between the steps right after a compaction and a minority of steps further from one.
- **Few runs.** One counted run per game and config (4 per config); counts per cell are small, and the rates are descriptive.
- **Not blind.** The endings, levels and some log lines around them were seen before PLAN A9 was written (its list).
- **Exploratory only** (PREREG §9.10); nothing here is a test or enters a decision.
