# S0's character limit against S1's token trigger (exploratory)

Computed 2026-10-31T16:31:37+00:00 at commit 88a3961 (dirty: False). **Exploratory:** written after the ARC path results were read; no test, no verdict; it enters no hypothesis, gate or kill rule.

S0 drops its oldest user/assistant pair while the request's characters (system prompt included, at 1 character per token) exceed 175,000. S1 summarizes once a request reports 175,000 provider tokens. Counted runs of each config on the 4 path games.

## Provider tokens per character of request text

Clean call steps only: no retries (a step's usage sums them) and not the first step after a summary. Median [quartiles].

| Game | S0 | S1 | S2 | 175k tokens in characters (S0 rate) |
|---|---|---|---|---|
| FT09 | 0.982 [0.980, 0.983] | 0.952 [0.937, 0.963] | 0.973 [0.965, 0.977] | 178,276 (1.019× S0's limit) |
| SB26 | 0.989 [0.987, 0.990] | 0.981 [0.979, 0.983] | 0.983 [0.981, 0.986] | 176,878 (1.011× S0's limit) |
| R11L | 0.861 [0.825, 0.913] | 0.964 [0.957, 0.969] | 0.973 [0.965, 0.979] | 203,192 (1.161× S0's limit) |
| CD82 | 0.988 [0.987, 0.989] | 0.968 [0.946, 0.976] | 0.969 [0.954, 0.977] | 177,120 (1.012× S0's limit) |

## When each run first lost history

The step whose request was the first to have lost history: S0's first trim, the others' first summary.

| Game | S0 | S1 | S2 | S4 |
|---|---|---|---|---|
| FT09 | 12 | 13 | 13 | 11 |
| SB26 | 8 | 7 | 8 | 6 |
| R11L | 6 | 7 | 8 | 5 |
| CD82 | 8 | 9 | 11 | 9 |

## S0 with its limit in tokens (replay of S0's own histories)

S0's untrimmed history before each call step is rebuilt from its step files. Trimmed at 175,000 characters it reproduces every request S0 sent (checked; the script refuses otherwise). It is then trimmed as the harness would with its estimate in tokens: characters × the game's S0 rate, against 175,000. That is S0 with its limit in tokens. Earlier replies kept = assistant messages in the window.

| Game | Call steps | Reproduced at 175k characters | Steps whose window changes | Earlier replies kept, at 175k characters | Extra replies kept per step |
|---|---|---|---|---|---|
| FT09 | 214 | 214 | 0 | 11.50 | 0.00 |
| SB26 | 238 | 238 | 0 | 2.20 | 0.00 |
| R11L | 361 | 361 | 210 | 2.93 | 0.65 |
| CD82 | 235 | 235 | 0 | 5.23 | 0.00 |

On FT09, SB26, CD82 the window never changes. Those games hold 97.8% of the summed S1 − S0 RHAE (215.37 points over the 4 games).

| Game | S0 RHAE | S1 RHAE | S1 − S0 |
|---|---|---|---|
| FT09 | 18.11 | 100.00 | 81.89 |
| SB26 | 5.44 | 100.00 | 94.56 |
| R11L | 6.45 | 11.21 | 4.75 |
| CD82 | 6.94 | 41.11 | 34.17 |

## Verbatim history per call step

The earlier history the model saw verbatim: every message but the system prompt, the summary bridge and the current observation. Means over all call steps of the counted runs.

| Config | Characters | Earlier replies | Characters vs S0 | Replies vs S0 |
|---|---|---|---|---|
| S0 | 114,505 | 5.03 | n/a | n/a |
| S1 | 69,280 | 3.07 | 0.605 | 0.611 |
| S2 | 67,178 | 3.49 | 0.587 | 0.694 |
| S4 | 66,718 | 2.58 | 0.583 | 0.513 |

## The summary trigger

For each summary, the last call before it, when it had no retries. The trigger is the request's `total_tokens`, so it counts the reply and its thinking too.

| Config | Triggers read | Request alone under 175k tokens | Request characters ÷ 175k: median [max] |
|---|---|---|---|
| S1 | 116 | 30 | 1.094 [1.510] |
| S2 | 138 | 54 | 1.094 [1.495] |
| S4 | 132 | 11 | 1.027 [1.527] |

## What it does not show

- **Which part of the loss policy does the work.** S0→S1 also replaces dropped turns by a summary, resets the history at each summary, checks its trigger after the request is sent and counts the reply. This script shows only that the unit of the limit lets S1 keep almost no extra history on these games.
- **Stochastic runs.** One counted run per config and game. The replay holds S0's own requests fixed; a run with the token limit would make different moves.
- **The rate is S0's.** The replay uses each game's median S0 rate. Where replies are long (R11L's S0 wrote long visible replies), the rate is lower and the unit matters more.
- **Exploratory, after the results were read.** Nothing here is a test or enters a decision.
