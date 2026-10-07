# Action-matched readings of the ARC path runs (PREREG §17.5, amendment R5)

Computed 2026-10-07T13:48:53+00:00 at commit 9040baf (dirty: False) by `uv run python -m analysis.arc_action_matched`. K = 150: the registered matched count.

Rules (module docstring; PREREG §17.5):
- **RHAE_K** is ARC's game score with only the levels cleared within the first K actions cleared: a cleared level scores min(100 (baseline / actions)², 115), others 0, weighted by the 1-indexed level number, capped at 100 × the weight share of levels above 0 (arc-agi 0.9.8 `arc_agi/scorecard.py`; https://docs.arcprize.org/methodology).
- **Actions** are the scorecard's: every RESET after the opening one counts, so Σ level_actions = actions.
- **Status at K:** OBSERVED (the run took ≥ K actions; exact), COMPLETE (fewer, ended GAME_WIN or ACTION_BUDGET; final values hold at K), CENSORED (fewer, ended any other way; values are lower bounds).
- Only counted runs enter the H4 readings; a run replaced by its re-run is listed with counted = False (PREREG §7.5).

## Runs at K = 150

| Run | Game | Config | Rep. | Counted | Ending (agent) | Actions (resets) | Levels | Score: scorecard; recomputed | Status at K | Levels cleared within K | RHAE_K |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `20261006T144656Z-S4-cd82-s1` | CD82 | S4 | 1 | True | GAME_WIN | 206 (4) | 6 of 6 | 73.02; 73.02 | OBSERVED | 4 | 38.46 |

## Levels cleared and RHAE_K by action count

Each cell: levels cleared within K; RHAE_K; status. Descriptive.

| Run | Cleared at actions | K = 50 | K = 100 | K = 150 | K = 200 |
|---|---|---|---|---|---|
| `20261006T144656Z-S4-cd82-s1` | 22, 28, 78, 104, 190, 206 | 2; 14.29; OBSERVED | 3; 26.03; OBSERVED | 4; 38.46; OBSERVED | 5; 40.16; OBSERVED |

## Pace and cost

| Run | Wall clock (h) | Seconds per action | Billed USD | Billed USD per action | List USD per action | costs.csv row |
|---|---|---|---|---|---|---|
| `20261006T144656Z-S4-cd82-s1` | 2.49 | 43.6 | 16.87 | 0.0819 | 0.1234 | match |

## Checks

- ARC's score reproduced from the level lists: every run.
- Σ level_actions = actions: every run.
- costs.csv row matches meta.json: every run.

## What this does not show

- Matching actions removes the 12 h clock's effect of speed, not the effects of context length: a config whose history is longer at action K is also slower per call, and its play up to K comes from that history.
- The clock-based primary readings (PREREG §3 H4) remain what ARC's harness rewards; every prediction and rule reads them.
- A run's first K actions are not a random sample of its play: early levels come first, and RHAE_K weights each level by its number over all levels of the game.
- Per-run values only; the H4 path quantities at K are computed from `runs.csv`.
