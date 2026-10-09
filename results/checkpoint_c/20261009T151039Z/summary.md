# Checkpoint C metrics (PREREG §10.3)

Computed 2026-10-09T15:10:39+00:00 at commit 660bc56 (dirty: False) by `uv run python -m analysis.checkpoint_c`, from `results`.

**Status: FINAL.**

| Rule | Reading | Fires |
|---|---|---|
| Gap | mean 62.59 RHAE over 4 games (< 5) | does not fire |
| Errors | 0 of 8 (> 3) | does not fire |
| Cost | forecast $1,045.23 against remaining $609.78 | **FIRES** |

## The 4 path games (FT09, SB26, R11L, CD82)

### Gap rule: does not fire

| Game | S0 run | S4 run | RHAE S0 | RHAE S4 | Gap |
|---|---|---|---|---|---|
| FT09 | `20261009T030646Z-S0-ft09-s101` | `20261009T020602Z-S4-ft09-s1` | 18.11 | 100.00 | 81.89 |
| SB26 | `20261007T143700Z-S0-sb26-s1` | `20261007T133444Z-S4-sb26-s1` | 5.44 | 100.00 | 94.56 |
| R11L | `20261008T134155Z-S0-r11l-s1` | `20261008T212807Z-S4-r11l-s1` | 6.45 | 14.29 | 7.83 |
| CD82 | `20261008T013832Z-S0-cd82-s1` | `20261006T144656Z-S4-cd82-s1` | 6.94 | 73.02 | 66.08 |

Mean gap over 4 of 4 games: **62.59** RHAE (fires if < 5): does not fire.

At K = 150 (PREREG §17.5, descriptive; fires no rule):

| Game | RHAE_K S0 (status, levels) | RHAE_K S4 (status, levels) | Gap at K |
|---|---|---|---|
| FT09 | 18.11 (OBSERVED, 3) | 100.00 (COMPLETE, 6) | 81.89 |
| SB26 | 5.44 (OBSERVED, 3) | 100.00 (COMPLETE, 8) | 94.56 |
| R11L | 6.45 (OBSERVED, 2) | 14.29 (OBSERVED, 2) | 7.83 |
| CD82 | 6.94 (OBSERVED, 2) | 38.46 (OBSERVED, 4) | 31.52 |

Mean gap at K = 150 over 4 games: **53.95**; censored counted runs (their values are lower bounds): S0 0, S4 0. Without the games that contain a censored run (§17.5's sensitivity analysis): 53.95 over 4 games.

### Error rule: does not fire

| Game | Config | Counted run | Re-run? | Ending (D19) | Re-run-eligible | Why |
|---|---|---|---|---|---|---|
| FT09 | S0 | `20261009T030646Z-S0-ft09-s101` | yes | TIME_BUDGET | False | TIME_BUDGET, 175.95 s per call against 2 × 156.68 s: not a latency incident: final, not an error (D20) |
| FT09 | S4 | `20261009T020602Z-S4-ft09-s1` | no | GAME_WIN | False | GAME_WIN: final (D19) |
| SB26 | S0 | `20261007T143700Z-S0-sb26-s1` | no | ACTION_BUDGET | False | ACTION_BUDGET: final (D19) |
| SB26 | S4 | `20261007T133444Z-S4-sb26-s1` | no | GAME_WIN | False | GAME_WIN: final (D19) |
| R11L | S0 | `20261008T134155Z-S0-r11l-s1` | no | ACTION_BUDGET | False | ACTION_BUDGET: final (D19) |
| R11L | S4 | `20261008T212807Z-S4-r11l-s1` | no | ACTION_BUDGET | False | ACTION_BUDGET: final (D19) |
| CD82 | S0 | `20261008T013832Z-S0-cd82-s1` | no | TIME_BUDGET | False | TIME_BUDGET, 170.06 s per call against 2 × 168.96 s: not a latency incident: final, not an error (D20) |
| CD82 | S4 | `20261006T144656Z-S4-cd82-s1` | no | GAME_WIN | False | GAME_WIN: final (D19) |

Errors: **0 of 8** (fires if > 3): does not fire. Pending re-runs: 0 (up to 0 if each pending re-run also ends re-run-eligible).
TIME_BUDGET: a TIME_BUDGET is an error only if the counted run is itself a D20 latency incident; a final TIME_BUDGET (not an incident) is not an error, nor is COST_CAP.

### Cost rule (D27): **FIRES**

| Game | S0 billed | S4 billed | S0 calls | S0 $/call | S0 actions | S4 actions | Seed 2 (S0 + S4) | S1 + S2, both seeds |
|---|---|---|---|---|---|---|---|---|
| FT09 | $48.84 | $6.18 | 222 | $0.2200 | 214 | 112 | $55.02 | $188.32 |
| SB26 | $38.51 | $13.81 | 246 | $0.1565 | 238 | 138 | $52.32 | $149.03 |
| R11L | $43.34 | $26.80 | 362 | $0.1197 | 365 | 281 | $70.14 | $174.79 |
| CD82 | $45.73 | $16.87 | 243 | $0.1882 | 235 | 206 | $62.60 | $176.89 |

- ρ = (1 re-runs) / 8 = 0.125.
- Forecast for the remaining 24 runs: ($240.08 + $689.02) × (1 + ρ) = **$1,045.23** billed.
- Remaining 1b: $900.00 cap − $290.22 spent = **$609.78**; headroom -$435.46: **FIRES**.
- With D27's raise of about $170.00: headroom -$265.46 (still fires).
- Cap the forecast needs: $1,335.46 (a raise of $435.46 over $900.00).
- *Descriptive, not the pre-registered rule:* with S1 and S2 at S0's measured billed cost per run, S1 + S2 = $705.65, forecast $1,063.95, headroom -$454.17, cap needed $1,354.17.

Under the 3-game fallback (D32), CD82 (perm[3]) leaves block 3; its block-2 runs are reported as exploratory, and Checkpoint C uses the 3 other games with the same thresholds (6 seed-1 runs, 18 remaining runs).

## 3-game fallback, D32 (FT09, SB26, R11L)

### Gap rule: does not fire

| Game | S0 run | S4 run | RHAE S0 | RHAE S4 | Gap |
|---|---|---|---|---|---|
| FT09 | `20261009T030646Z-S0-ft09-s101` | `20261009T020602Z-S4-ft09-s1` | 18.11 | 100.00 | 81.89 |
| SB26 | `20261007T143700Z-S0-sb26-s1` | `20261007T133444Z-S4-sb26-s1` | 5.44 | 100.00 | 94.56 |
| R11L | `20261008T134155Z-S0-r11l-s1` | `20261008T212807Z-S4-r11l-s1` | 6.45 | 14.29 | 7.83 |

Mean gap over 3 of 3 games: **61.43** RHAE (fires if < 5): does not fire.

At K = 150 (PREREG §17.5, descriptive; fires no rule):

| Game | RHAE_K S0 (status, levels) | RHAE_K S4 (status, levels) | Gap at K |
|---|---|---|---|
| FT09 | 18.11 (OBSERVED, 3) | 100.00 (COMPLETE, 6) | 81.89 |
| SB26 | 5.44 (OBSERVED, 3) | 100.00 (COMPLETE, 8) | 94.56 |
| R11L | 6.45 (OBSERVED, 2) | 14.29 (OBSERVED, 2) | 7.83 |

Mean gap at K = 150 over 3 games: **61.43**; censored counted runs (their values are lower bounds): S0 0, S4 0. Without the games that contain a censored run (§17.5's sensitivity analysis): 61.43 over 3 games.

### Error rule: does not fire

| Game | Config | Counted run | Re-run? | Ending (D19) | Re-run-eligible | Why |
|---|---|---|---|---|---|---|
| FT09 | S0 | `20261009T030646Z-S0-ft09-s101` | yes | TIME_BUDGET | False | TIME_BUDGET, 175.95 s per call against 2 × 156.68 s: not a latency incident: final, not an error (D20) |
| FT09 | S4 | `20261009T020602Z-S4-ft09-s1` | no | GAME_WIN | False | GAME_WIN: final (D19) |
| SB26 | S0 | `20261007T143700Z-S0-sb26-s1` | no | ACTION_BUDGET | False | ACTION_BUDGET: final (D19) |
| SB26 | S4 | `20261007T133444Z-S4-sb26-s1` | no | GAME_WIN | False | GAME_WIN: final (D19) |
| R11L | S0 | `20261008T134155Z-S0-r11l-s1` | no | ACTION_BUDGET | False | ACTION_BUDGET: final (D19) |
| R11L | S4 | `20261008T212807Z-S4-r11l-s1` | no | ACTION_BUDGET | False | ACTION_BUDGET: final (D19) |

Errors: **0 of 6** (fires if > 3): does not fire. Pending re-runs: 0 (up to 0 if each pending re-run also ends re-run-eligible).
TIME_BUDGET: a TIME_BUDGET is an error only if the counted run is itself a D20 latency incident; a final TIME_BUDGET (not an incident) is not an error, nor is COST_CAP.

### Cost rule (D27): **FIRES**

| Game | S0 billed | S4 billed | S0 calls | S0 $/call | S0 actions | S4 actions | Seed 2 (S0 + S4) | S1 + S2, both seeds |
|---|---|---|---|---|---|---|---|---|
| FT09 | $48.84 | $6.18 | 222 | $0.2200 | 214 | 112 | $55.02 | $188.32 |
| SB26 | $38.51 | $13.81 | 246 | $0.1565 | 238 | 138 | $52.32 | $149.03 |
| R11L | $43.34 | $26.80 | 362 | $0.1197 | 365 | 281 | $70.14 | $174.79 |

- ρ = (1 re-runs) / 6 = 0.167.
- Forecast for the remaining 18 runs: ($177.48 + $512.13) × (1 + ρ) = **$804.55** billed.
- Remaining 1b: $900.00 cap − $290.22 spent = **$609.78**; headroom -$194.77: **FIRES**.
- With D27's raise of about $170.00: headroom -$24.77 (still fires).
- Cap the forecast needs: $1,094.77 (a raise of $194.77 over $900.00).
- *Descriptive, not the pre-registered rule:* with S1 and S2 at S0's measured billed cost per run, S1 + S2 = $522.75, forecast $816.93, headroom -$207.15, cap needed $1,107.15.
- With ρ over all 8 block-2 runs (0.125) instead: forecast $775.81.

## Per run

| Run | Game | Config | Rep. | Counted | Ending: agent; exit | RHAE | Actions | Billed (G0 forecast, ratio) | s per action | Model calls | Median s per call | D20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `20261006T144656Z-S4-cd82-s1` | CD82 | S4 | 1 | True | GAME_WIN; GAME_WIN | 73.02 | 206 | $16.87 ($22.13, 0.76×) | 43.6 | 239 | 17.36 | n/a (not TIME_BUDGET) |
| `20261006T171726Z-S0-ft09-s1` | FT09 | S0 | 1 | False | TIME_BUDGET; TIME_BUDGET | 58.17 | 236 | $50.15 ($23.90, 2.10×) | 183.4 | 237 | 181.25 | 181.25 s vs 2 × 73.30 s (from pilot 20261002T035726Z-S0-r11l-s1): **incident** |
| `20261007T133444Z-S4-sb26-s1` | SB26 | S4 | 1 | True | GAME_WIN; GAME_WIN | 100.00 | 138 | $13.81 ($12.98, 1.06×) | 26.7 | 174 | 12.96 | n/a (not TIME_BUDGET) |
| `20261007T143700Z-S0-sb26-s1` | SB26 | S0 | 1 | True | ACTION_BUDGET; ACTION_BUDGET | 5.44 | 238 | $38.51 ($24.39, 1.58×) | 166.6 | 246 | 156.68 | n/a (not TIME_BUDGET) |
| `20261008T013832Z-S0-cd82-s1` | CD82 | S0 | 1 | True | TIME_BUDGET; TIME_BUDGET | 6.94 | 235 | $45.73 ($9.71, 4.71×) | 184.1 | 243 | 170.06 | 170.06 s vs 2 × 168.96 s (from `20261006T171726Z-S0-ft09-s1`, `20261007T143700Z-S0-sb26-s1`): **not an incident** |
| `20261008T134155Z-S0-r11l-s1` | R11L | S0 | 1 | True | ACTION_BUDGET; ACTION_BUDGET | 6.45 | 365 | $43.34 ($45.54, 0.95×) | 76.4 | 362 | 50.98 | n/a (not TIME_BUDGET) |
| `20261008T212807Z-S4-r11l-s1` | R11L | S4 | 1 | True | ACTION_BUDGET; ACTION_BUDGET | 14.29 | 281 | $26.80 ($26.69, 1.00×) | 59.0 | 330 | 31.55 | n/a (not TIME_BUDGET) |
| `20261009T020602Z-S4-ft09-s1` | FT09 | S4 | 1 | True | GAME_WIN; GAME_WIN | 100.00 | 112 | $6.18 ($6.11, 1.01×) | 32.3 | 122 | 9.05 | n/a (not TIME_BUDGET) |
| `20261009T030646Z-S0-ft09-s101` | FT09 | S0 | 1 | True | TIME_BUDGET; TIME_BUDGET | 18.11 | 214 | $48.84 ($23.90, 2.04×) | 202.3 | 222 | 175.95 | 175.95 s vs 2 × 156.68 s (from `20261007T143700Z-S0-sb26-s1`, `20261008T013832Z-S0-cd82-s1`, `20261008T134155Z-S0-r11l-s1`): **not an incident** |

Phase 1b: $290.22 spent of $900.00 (`costs.csv`, every phase-1b row, billed estimate, list where a row has none).

## What this does not show

- One seed per config and game: the gap is noisy, which is why its threshold (5) is looser than G2's kill at 10 (§10.3).
- Four games (three under D32), chosen because ARC's published Standard-to-Adapter gap on them was at least 20 (§7.2): the gap is conditional on games where the Adapter helped, and says nothing about other games, models or efforts.
- It does not decompose the gap: S1 and S2 have not run, so nothing here says which step (loss policy, notes, replay) accounts for it (H4).
- The cost forecast prices S1 and S2 from S0's measured cost per call. S1 and S2 keep their history until a summary at 175k tokens, where S0 drops its oldest turns above 175k characters, and they were slower per call than S0 in the pilot, so their cost per call may be higher; it is not measured here.
- The gap at K is descriptive (§17.5): it fires no rule, and its censored runs are lower bounds.
- Nothing here compares models; it describes one model's runs under two configs.

The researcher makes the go/no-go call.
