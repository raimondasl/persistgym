# G0 gate metrics (PREREG §10.1)

Computed 2026-10-06T13:31:52+00:00 at commit a255e05 (dirty: False) by `uv run python -m analysis.g0`.

## Cost rule (D27 rule 1, D28)

| Config | b(c) = billed/list in the pilot |
|---|---|
| S0 | 0.832 |
| S1 | 0.790 |
| S2 | 0.786 |
| S4 | 0.763 |

| Game | L(S0) | L(S4) | L(S1) = L(S2) | F(game), billed |
|---|---|---|---|---|
| FT09 | 28.73 | 8.01 | 18.37 | 117.91 |
| SB26 | 29.32 | 17.01 | 23.16 | 147.73 |
| R11L | 54.75 | 34.99 | 44.87 | 285.86 |
| CD82 | 11.68 | 29.01 | 20.34 | 127.80 |

- F = **$679.30** billed; with the 20% reserve **$815.15** against the $900 phase-1b cap (headroom $84.85): **met**.

## Toggle rule (D29 as amended by R1)

- gpt-6.1-sol: forks agree 20/20 (`all_turns`) and 0/20 (`current_turn`), echo all matched: **verified**.
- gpt-6-luna: forks agree 13/20 (`all_turns`) and 6/20 (`current_turn`), echo all matched: **not verified**.

## Gemini S0-S2 run (D37)

- S0: NORMAL_ENDING_BLINDED, limits {'max_actions': 50, 'after_summary_turns': None}, compactions 0, tiers {'standard': 50}: **reached**
- S4: NORMAL_ENDING_BLINDED, limits {'max_actions': 50, 'after_summary_turns': None}, compactions 10, tiers {'standard': 50} (S4: not a G0 condition)
- S1: NORMAL_ENDING_BLINDED, limits {'max_actions': 60, 'after_summary_turns': 5}, compactions 1, tiers {'standard': 13}: **reached**
- S2: NORMAL_ENDING_BLINDED, limits {'max_actions': 30, 'after_summary_turns': None}, compactions 5, tiers {'standard': 30}: **reached**

Snapshot tests: a test run, recorded in `results/decisions.md`.

The researcher makes the go/no-go call.
