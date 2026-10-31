# S0's character limit against S1's token trigger (exploratory)

Computed 2026-10-31T17:45:43+00:00 at commit 9991529 (dirty: False). **Exploratory:** written after the ARC path results were read. No test, no verdict. It enters no hypothesis, gate or kill rule.

S0 drops its oldest user/assistant pair while the request's characters (system prompt included, at 1 character per token) exceed 175,000. S1 summarizes once a call reports 175,000 provider tokens, its reply and thinking included. Counted runs of each config on the 4 path games.

## Provider tokens per character of request text

Clean call steps only: no retries (a step's usage sums its attempts) and not the first step after a summary. Median [quartiles]. Reply share: the median share of request characters that are the model's earlier replies.

| Game | S0 | S1 | S2 | S0 reply share | 175k tokens in characters (S0 median rate) |
|---|---|---|---|---|---|
| FT09 | 0.982 [0.980, 0.983] | 0.952 [0.937, 0.963] | 0.973 [0.965, 0.977] | 0.011 | 178,276 (1.019× S0's limit) |
| SB26 | 0.989 [0.987, 0.990] | 0.981 [0.979, 0.983] | 0.983 [0.981, 0.986] | 0.002 | 176,878 (1.011× S0's limit) |
| R11L | 0.861 [0.825, 0.913] | 0.964 [0.957, 0.969] | 0.973 [0.965, 0.979] | 0.259 | 203,192 (1.161× S0's limit) |
| CD82 | 0.988 [0.987, 0.989] | 0.968 [0.946, 0.976] | 0.969 [0.954, 0.977] | 0.002 | 177,120 (1.012× S0's limit) |

## When each run first lost history

The step whose request was the first to have lost history: S0's first trim, the others' first summary.

| Game | S0 | S1 | S2 | S4 |
|---|---|---|---|---|
| FT09 | 12 | 13 | 13 | 11 |
| SB26 | 8 | 7 | 8 | 6 |
| R11L | 6 | 7 | 8 | 5 |
| CD82 | 8 | 9 | 11 | 9 |

## S0's windows with its limit in tokens (a replay of S0's own histories)

S0's untrimmed history before each call step is rebuilt from its step files. Trimmed at 175,000 characters it reproduces the recorded request of every S0 call step (checked: the script refuses otherwise). It is then trimmed as the harness would with its estimate in tokens: characters × the game's median S0 rate, against 175,000. That approximates S0's windows with its limit in tokens, on S0's own moves. The last column repeats it at the game's lower-quartile S0 rate. Earlier replies kept = assistant messages in the window.

| Game | Call steps | Reproduced at 175k characters | Steps whose window changes | Earlier replies kept, at 175k characters | Extra replies kept per step | Steps changed at the lower-quartile rate |
|---|---|---|---|---|---|---|
| FT09 | 214 | 214 | 0 | 11.50 | 0.00 | 0 |
| SB26 | 238 | 238 | 0 | 2.20 | 0.00 | 1 |
| R11L | 361 | 361 | 210 | 2.93 | 0.65 | 247 |
| CD82 | 235 | 235 | 0 | 5.23 | 0.00 | 0 |

At the median rate the window never changes on FT09, SB26, CD82. Those games hold 97.8% of the summed S1 − S0 RHAE (215.37 points over the 4 games).

| Game | S0 RHAE | S1 RHAE | S1 − S0 |
|---|---|---|---|
| FT09 | 18.11 | 100.00 | 81.89 |
| SB26 | 5.44 | 100.00 | 94.56 |
| R11L | 6.45 | 11.21 | 4.75 |
| CD82 | 6.94 | 41.11 | 34.17 |

## Verbatim history per call step

The earlier history the model saw verbatim: every message but the system prompt, the summary bridge and the current observation. Pooled: means over all call steps of the counted runs, so each game weighs by its steps, and the step mix differs by config. Per game below.

| Config | Characters | Earlier replies | Characters vs S0 | Replies vs S0 |
|---|---|---|---|---|
| S0 | 114,505 | 5.03 | n/a | n/a |
| S1 | 69,280 | 3.07 | 0.605 | 0.611 |
| S2 | 67,178 | 3.49 | 0.587 | 0.694 |
| S4 | 66,718 | 2.58 | 0.583 | 0.513 |

Per game, each config against S0 (characters / earlier replies):

| Game | S0 characters / replies | S1 | S2 | S4 |
|---|---|---|---|---|
| FT09 | 151,746 / 11.50 | 0.527 / 0.481 | 0.490 / 0.491 | 0.499 / 0.418 |
| SB26 | 71,607 / 2.20 | 0.808 / 0.681 | 0.812 / 0.726 | 0.807 / 0.640 |
| R11L | 116,797 / 2.93 | 0.614 / 1.000 | 0.602 / 0.927 | 0.571 / 0.737 |
| CD82 | 120,516 / 5.23 | 0.564 / 0.609 | 0.533 / 0.717 | 0.563 / 0.520 |

S4's characters are the readable projection the harness logs (`messages_sent`). It leaves out the replayed reasoning items that the provider counts as prompt tokens. So S4's characters undercount what it sent, and they are not like-for-like with S0-S2.

## The summary trigger

For each summary, the last call before it, when it had no retries. The trigger is the call's `total_tokens`, so it counts the reply and its thinking too. It is checked after the request is sent, so the request that trips it can be past the limit.

| Config | Triggers read | Request alone under 175k tokens | Request characters ÷ 175k: median [min, max] |
|---|---|---|---|
| S1 | 116 | 30 | 1.094 [0.753, 1.510] |
| S2 | 138 | 54 | 1.094 [0.777, 1.495] |
| S4 | 132 | 11 | 1.027 [0.602, 1.527] |

For S4 the characters are the readable projection only (above).

## What it does not show

- **Which part of the loss policy does the work.** S0→S1 also replaces dropped turns by a summary, resets the history at each summary, checks its trigger after the request is sent and counts the reply. This script shows only that a limit in tokens, replayed on S0's own histories at each game's median S0 rate, changes no window on FT09, SB26, CD82. On R11L it changes 210 of 361 windows and keeps 0.65 more earlier replies per step. It measures S0's histories, not S1's.
- **Stochastic runs.** One counted run per config and game. The replay holds S0's own moves, observations and replies fixed. A run with the token limit would make different moves.
- **One rate per game.** Where the window never changes, the token limit sits only 1.1-1.9% above S0's character limit, so a rate a little below the median can change a few windows (the last replay column). The lowest S0 rate is R11L's (0.861), where earlier replies are a median 0.259 of the request's characters, against at most 0.011 on the other games. That is an association, not a measured cause.
- **Exploratory, after the results were read.** Nothing here is a test or enters a decision.
