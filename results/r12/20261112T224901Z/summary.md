# R12: Haiku's notes sentences, claude-sonnet-5-5, and a block-truncation window

**FINAL.** PREREG.md §17.12 (amendment R12). Exploratory: no test, no label. Repeat 0, base episodes. Not a model comparison, and nothing is ranked.

## What it does not show

- Everything R8 to R11 say they do not show also holds here: one model per provider in the confirmatory sense, the same synthetic task family, thinking text not inspected.
- No model comparison. Experiment 2 is one run per arm on 25 templates of one larger model of the same provider, at effort medium, whose levels on Sonnet 5.5 are recalibrated and not matched to Haiku's medium ([effort](https://platform.claude.com/docs/en/build-with-claude/effort), checked 2026-11-11). Setting its arms beside Haiku's describes how each behaved on these episodes. It does not rank them.
- The sentences. Three wordings beside R10's two, one run each. Other wordings, other models and other tasks are not run. The neutral sentence is a length-matched control, not a no-effect control: it points attention at the action's format and may change replies by itself.
- Experiment 3 is not concurrent with R8's W-0 and F-0, its comparators, which ran on 2026-10-18. Cost comes mostly from caching mechanics, but success differences against them mix the rule with any change in serving since. One block size (W // 2) is run, on Haiku's short replies, without notes.
- Coarse intervals. Experiment 2 bootstraps over at most 25 templates. Experiment 1's arms play each template once.

## Experiment 1: claude-haiku-5-5, `persistgym_haiku_r12_notes`

Main templates 200-299 in every arm (100 of the registered 200-299), resamples over 100 positions. §2.8's accounting check: 800 need steps replayed, 0 bugs.

**1. Success:**

| Arm | Task cell | Success | 90% interval | Refused episodes | Stopped responses |
|---|---|---|---|---|---|
| W-n-0 | observed-nonrec-far | 3/100 (3.0%) | 1.0% to 6.0% | 4 | {'refusal:bio': 7} |
| W-n-0 | derived-nonrec-far | 5/100 (5.0%) | 2.0% to 9.0% | 12 | {'refusal:bio': 15} |
| W-np-0 | observed-nonrec-far | 85/100 (85.0%) | 79.0% to 91.0% | 15 | {'refusal:bio': 39} |
| W-np-0 | derived-nonrec-far | 86/100 (86.0%) | 80.0% to 91.0% | 20 | {'refusal:bio': 52} |
| W-nd-0 | observed-nonrec-far | 35/100 (35.0%) | 27.0% to 43.0% | 4 | {'refusal:bio': 12} |
| W-nd-0 | derived-nonrec-far | 44/100 (44.0%) | 36.0% to 52.0% | 19 | {'refusal:bio': 47} |
| W-nx-0 | observed-nonrec-far | 1/100 (1.0%) | 0.0% to 3.0% | 2 | {'refusal:bio': 2} |
| W-nx-0 | derived-nonrec-far | 1/100 (1.0%) | 0.0% to 3.0% | 9 | {'refusal:bio': 13} |

**2. §2.8 accounting** (not-recoverable far cells, where P(carried) is a lower bound):

| Arm | Task cell | S verbatim 0 | P(carried) | Success given carried |
|---|---|---|---|---|
| W-n-0 | observed-nonrec-far | 100 | 3/100 (3.0%) | 3/3 (100.0%) |
| W-n-0 | derived-nonrec-far | 100 | 34/100 (34.0%) | 5/34 (14.7%) |
| W-np-0 | observed-nonrec-far | 100 | 87/100 (87.0%) | 85/87 (97.7%) |
| W-np-0 | derived-nonrec-far | 100 | 89/100 (89.0%) | 86/89 (96.6%) |
| W-nd-0 | observed-nonrec-far | 100 | 38/100 (38.0%) | 35/38 (92.1%) |
| W-nd-0 | derived-nonrec-far | 100 | 67/100 (67.0%) | 44/67 (65.7%) |
| W-nx-0 | observed-nonrec-far | 100 | 3/100 (3.0%) | 1/3 (33.3%) |
| W-nx-0 | derived-nonrec-far | 100 | 26/100 (26.0%) | 1/26 (3.8%) |

**3. Choices with the fact evicted** (window arms):

- W-n-0, observed-nonrec-far: chose an option in 3 of 100, 3 correct.
- W-n-0, derived-nonrec-far: chose an option in 5 of 100, 5 correct.
- W-np-0, observed-nonrec-far: chose an option in 85 of 100, 85 correct.
- W-np-0, derived-nonrec-far: chose an option in 86 of 100, 86 correct.
- W-nd-0, observed-nonrec-far: chose an option in 35 of 100, 35 correct.
- W-nd-0, derived-nonrec-far: chose an option in 44 of 100, 44 correct.
- W-nx-0, observed-nonrec-far: chose an option in 1 of 100, 1 correct.
- W-nx-0, derived-nonrec-far: chose an option in 1 of 100, 1 correct.

**4. Contrasts** (percentage points, 90% interval over the same template resamples, described, not tested):

W-nx-0 is a length-matched control, not a no-effect control (see What it does not show).

- W-np-0 - W-n-0, observed-nonrec-far: +82.0 pp [+75.0, +88.0]
- W-np-0 - W-n-0, derived-nonrec-far: +81.0 pp [+74.0, +88.0]
- W-nd-0 - W-n-0, observed-nonrec-far: +32.0 pp [+23.0, +41.0]
- W-nd-0 - W-n-0, derived-nonrec-far: +39.0 pp [+30.0, +48.0]
- W-nx-0 - W-n-0, observed-nonrec-far: -2.0 pp [-5.0, +1.0]
- W-nx-0 - W-n-0, derived-nonrec-far: -4.0 pp [-8.0, +0.0]
- W-np-0 - W-nx-0, observed-nonrec-far: +84.0 pp [+78.0, +90.0]
- W-np-0 - W-nx-0, derived-nonrec-far: +85.0 pp [+79.0, +91.0]
- W-np-0 - W-nd-0, observed-nonrec-far: +50.0 pp [+40.0, +60.0]
- W-np-0 - W-nd-0, derived-nonrec-far: +42.0 pp [+31.0, +52.0]

**5. Responses:**

Thinking blocks by their presence only, so the thinking text is not inspected. A redacted_thinking block counts as one. The retained replies are those in the need step's first request. Their length is one reply's, the median over the replies pooled in the task cell.

| Arm | Refused responses | Categories | With a thinking block | Task cell | Retained replies at the need step (median per episode) | One retained reply's length (median characters) | Output tokens per episode | Cost per episode (USD) |
|---|---|---|---|---|---|---|---|---|
| W-n-0 | 22/4812 (0.5%) | {'refusal:bio': 22} | 2460/4812 (51.1%) | observed-nonrec-far | 14.0 | 103 | 2094 | 0.04350 |
| W-n-0 | 22/4812 (0.5%) | {'refusal:bio': 22} | 2460/4812 (51.1%) | derived-nonrec-far | 14.0 | 107 | 2839 | 0.04371 |
| W-np-0 | 91/4812 (1.9%) | {'refusal:bio': 91} | 4543/4812 (94.4%) | observed-nonrec-far | 11.0 | 1137 | 12635 | 0.05401 |
| W-np-0 | 91/4812 (1.9%) | {'refusal:bio': 91} | 4543/4812 (94.4%) | derived-nonrec-far | 11.0 | 1147 | 13561 | 0.05474 |
| W-nd-0 | 59/4812 (1.2%) | {'refusal:bio': 59} | 3486/4812 (72.4%) | observed-nonrec-far | 14.0 | 140 | 4454 | 0.04599 |
| W-nd-0 | 59/4812 (1.2%) | {'refusal:bio': 59} | 3486/4812 (72.4%) | derived-nonrec-far | 14.0 | 156 | 5591 | 0.04675 |
| W-nx-0 | 15/4812 (0.3%) | {'refusal:bio': 15} | 2473/4812 (51.4%) | observed-nonrec-far | 14.0 | 115 | 2339 | 0.04381 |
| W-nx-0 | 15/4812 (0.3%) | {'refusal:bio': 15} | 2473/4812 (51.4%) | derived-nonrec-far | 14.0 | 116 | 2841 | 0.04384 |

**6. Rounds** (described only):

Task cell "all" pools the task cells: success per arm and round, as §17.12 registers it. The rows per task cell are extra detail.

| Round | Templates | Read | Arm | Task cell | Success |
|---|---|---|---|---|---|
| 1 | 200-224 | 25 | W-n-0 | all | 2/50 (4.0%) |
| 1 | 200-224 | 25 | W-n-0 | observed-nonrec-far | 1/25 (4.0%) |
| 1 | 200-224 | 25 | W-n-0 | derived-nonrec-far | 1/25 (4.0%) |
| 1 | 200-224 | 25 | W-np-0 | all | 44/50 (88.0%) |
| 1 | 200-224 | 25 | W-np-0 | observed-nonrec-far | 21/25 (84.0%) |
| 1 | 200-224 | 25 | W-np-0 | derived-nonrec-far | 23/25 (92.0%) |
| 1 | 200-224 | 25 | W-nd-0 | all | 18/50 (36.0%) |
| 1 | 200-224 | 25 | W-nd-0 | observed-nonrec-far | 9/25 (36.0%) |
| 1 | 200-224 | 25 | W-nd-0 | derived-nonrec-far | 9/25 (36.0%) |
| 1 | 200-224 | 25 | W-nx-0 | all | 0/50 (0.0%) |
| 1 | 200-224 | 25 | W-nx-0 | observed-nonrec-far | 0/25 (0.0%) |
| 1 | 200-224 | 25 | W-nx-0 | derived-nonrec-far | 0/25 (0.0%) |
| 2 | 225-249 | 25 | W-n-0 | all | 2/50 (4.0%) |
| 2 | 225-249 | 25 | W-n-0 | observed-nonrec-far | 1/25 (4.0%) |
| 2 | 225-249 | 25 | W-n-0 | derived-nonrec-far | 1/25 (4.0%) |
| 2 | 225-249 | 25 | W-np-0 | all | 43/50 (86.0%) |
| 2 | 225-249 | 25 | W-np-0 | observed-nonrec-far | 21/25 (84.0%) |
| 2 | 225-249 | 25 | W-np-0 | derived-nonrec-far | 22/25 (88.0%) |
| 2 | 225-249 | 25 | W-nd-0 | all | 19/50 (38.0%) |
| 2 | 225-249 | 25 | W-nd-0 | observed-nonrec-far | 10/25 (40.0%) |
| 2 | 225-249 | 25 | W-nd-0 | derived-nonrec-far | 9/25 (36.0%) |
| 2 | 225-249 | 25 | W-nx-0 | all | 1/50 (2.0%) |
| 2 | 225-249 | 25 | W-nx-0 | observed-nonrec-far | 0/25 (0.0%) |
| 2 | 225-249 | 25 | W-nx-0 | derived-nonrec-far | 1/25 (4.0%) |
| 3 | 250-274 | 25 | W-n-0 | all | 2/50 (4.0%) |
| 3 | 250-274 | 25 | W-n-0 | observed-nonrec-far | 1/25 (4.0%) |
| 3 | 250-274 | 25 | W-n-0 | derived-nonrec-far | 1/25 (4.0%) |
| 3 | 250-274 | 25 | W-np-0 | all | 43/50 (86.0%) |
| 3 | 250-274 | 25 | W-np-0 | observed-nonrec-far | 22/25 (88.0%) |
| 3 | 250-274 | 25 | W-np-0 | derived-nonrec-far | 21/25 (84.0%) |
| 3 | 250-274 | 25 | W-nd-0 | all | 25/50 (50.0%) |
| 3 | 250-274 | 25 | W-nd-0 | observed-nonrec-far | 11/25 (44.0%) |
| 3 | 250-274 | 25 | W-nd-0 | derived-nonrec-far | 14/25 (56.0%) |
| 3 | 250-274 | 25 | W-nx-0 | all | 1/50 (2.0%) |
| 3 | 250-274 | 25 | W-nx-0 | observed-nonrec-far | 1/25 (4.0%) |
| 3 | 250-274 | 25 | W-nx-0 | derived-nonrec-far | 0/25 (0.0%) |
| 4 | 275-299 | 25 | W-n-0 | all | 2/50 (4.0%) |
| 4 | 275-299 | 25 | W-n-0 | observed-nonrec-far | 0/25 (0.0%) |
| 4 | 275-299 | 25 | W-n-0 | derived-nonrec-far | 2/25 (8.0%) |
| 4 | 275-299 | 25 | W-np-0 | all | 41/50 (82.0%) |
| 4 | 275-299 | 25 | W-np-0 | observed-nonrec-far | 21/25 (84.0%) |
| 4 | 275-299 | 25 | W-np-0 | derived-nonrec-far | 20/25 (80.0%) |
| 4 | 275-299 | 25 | W-nd-0 | all | 17/50 (34.0%) |
| 4 | 275-299 | 25 | W-nd-0 | observed-nonrec-far | 5/25 (20.0%) |
| 4 | 275-299 | 25 | W-nd-0 | derived-nonrec-far | 12/25 (48.0%) |
| 4 | 275-299 | 25 | W-nx-0 | all | 0/50 (0.0%) |
| 4 | 275-299 | 25 | W-nx-0 | observed-nonrec-far | 0/25 (0.0%) |
| 4 | 275-299 | 25 | W-nx-0 | derived-nonrec-far | 0/25 (0.0%) |

| Run | Arm | Templates | Ending | Started (UTC) | Finished (UTC) |
|---|---|---|---|---|---|
| 20261112T150644Z-W-n-0-claude-haiku-5-5 | W-n-0 | 200-224 | COMPLETED | 2026-11-12T15:06:46+00:00 | 2026-11-12T15:21:17+00:00 |
| 20261112T152127Z-W-np-0-claude-haiku-5-5 | W-np-0 | 200-224 | COMPLETED | 2026-11-12T15:21:29+00:00 | 2026-11-12T15:50:13+00:00 |
| 20261112T155022Z-W-nd-0-claude-haiku-5-5 | W-nd-0 | 200-224 | COMPLETED | 2026-11-12T15:50:24+00:00 | 2026-11-12T16:08:28+00:00 |
| 20261112T160838Z-W-nx-0-claude-haiku-5-5 | W-nx-0 | 200-224 | COMPLETED | 2026-11-12T16:08:41+00:00 | 2026-11-12T16:23:17+00:00 |
| 20261112T162328Z-W-np-0-claude-haiku-5-5 | W-np-0 | 225-249 | COMPLETED | 2026-11-12T16:23:30+00:00 | 2026-11-12T16:50:39+00:00 |
| 20261112T165047Z-W-nd-0-claude-haiku-5-5 | W-nd-0 | 225-249 | COMPLETED | 2026-11-12T16:50:49+00:00 | 2026-11-12T17:06:49+00:00 |
| 20261112T170658Z-W-nx-0-claude-haiku-5-5 | W-nx-0 | 225-249 | COMPLETED | 2026-11-12T17:06:59+00:00 | 2026-11-12T17:19:41+00:00 |
| 20261112T171952Z-W-n-0-claude-haiku-5-5 | W-n-0 | 225-249 | COMPLETED | 2026-11-12T17:19:54+00:00 | 2026-11-12T17:33:27+00:00 |
| 20261112T173336Z-W-nd-0-claude-haiku-5-5 | W-nd-0 | 250-274 | COMPLETED | 2026-11-12T17:33:37+00:00 | 2026-11-12T17:51:29+00:00 |
| 20261112T175138Z-W-nx-0-claude-haiku-5-5 | W-nx-0 | 250-274 | COMPLETED | 2026-11-12T17:51:39+00:00 | 2026-11-12T18:05:30+00:00 |
| 20261112T180539Z-W-n-0-claude-haiku-5-5 | W-n-0 | 250-274 | COMPLETED | 2026-11-12T18:05:40+00:00 | 2026-11-12T18:18:36+00:00 |
| 20261112T181844Z-W-np-0-claude-haiku-5-5 | W-np-0 | 250-274 | COMPLETED | 2026-11-12T18:18:45+00:00 | 2026-11-12T18:43:54+00:00 |
| 20261112T184402Z-W-nx-0-claude-haiku-5-5 | W-nx-0 | 275-299 | COMPLETED | 2026-11-12T18:44:04+00:00 | 2026-11-12T18:57:19+00:00 |
| 20261112T185728Z-W-n-0-claude-haiku-5-5 | W-n-0 | 275-299 | COMPLETED | 2026-11-12T18:57:29+00:00 | 2026-11-12T19:11:03+00:00 |
| 20261112T191112Z-W-np-0-claude-haiku-5-5 | W-np-0 | 275-299 | COMPLETED | 2026-11-12T19:11:13+00:00 | 2026-11-12T19:38:07+00:00 |
| 20261112T193815Z-W-nd-0-claude-haiku-5-5 | W-nd-0 | 275-299 | COMPLETED | 2026-11-12T19:38:16+00:00 | 2026-11-12T19:54:32+00:00 |

**Exclusions** (per arm and task cell, repeat 0, §13):

- W-n-0, observed-nonrec-far: {'keys': 100}
- W-n-0, derived-nonrec-far: {'keys': 100}
- W-np-0, observed-nonrec-far: {'keys': 100}
- W-np-0, derived-nonrec-far: {'keys': 100}
- W-nd-0, observed-nonrec-far: {'keys': 100}
- W-nd-0, derived-nonrec-far: {'keys': 100}
- W-nx-0, observed-nonrec-far: {'keys': 100}
- W-nx-0, derived-nonrec-far: {'keys': 100}

## Experiment 2: claude-sonnet-5-5, `persistgym_sonnet_r12`

Main templates 200-224 in every arm (25 of the registered 200-224), resamples over 25 positions. §2.8's accounting check: 100 need steps replayed, 0 bugs.

**1. Success:**

| Arm | Task cell | Success | 90% interval | Refused episodes | Stopped responses |
|---|---|---|---|---|---|
| W-n-0 | observed-nonrec-far | 24/25 (96.0%) | 88.0% to 100.0% | 0 | - |
| W-n-0 | derived-nonrec-far | 25/25 (100.0%) | 100.0% to 100.0% | 0 | - |
| W-np-0 | observed-nonrec-far | 24/25 (96.0%) | 88.0% to 100.0% | 0 | - |
| W-np-0 | derived-nonrec-far | 23/25 (92.0%) | 84.0% to 100.0% | 4 | {'refusal:reasoning_extraction': 8} |
| F-0 | observed-nonrec-far | 25/25 (100.0%) | 100.0% to 100.0% | 0 | - |
| F-0 | derived-nonrec-far | 25/25 (100.0%) | 100.0% to 100.0% | 0 | - |

**2. §2.8 accounting** (not-recoverable far cells, where P(carried) is a lower bound):

| Arm | Task cell | S verbatim 0 | P(carried) | Success given carried |
|---|---|---|---|---|
| W-n-0 | observed-nonrec-far | 25 | 24/25 (96.0%) | 24/24 (100.0%) |
| W-n-0 | derived-nonrec-far | 25 | 25/25 (100.0%) | 25/25 (100.0%) |
| W-np-0 | observed-nonrec-far | 25 | 24/25 (96.0%) | 24/24 (100.0%) |
| W-np-0 | derived-nonrec-far | 25 | 25/25 (100.0%) | 23/25 (92.0%) |
| F-0 | observed-nonrec-far | 0 | n/a | n/a |
| F-0 | derived-nonrec-far | 0 | n/a | n/a |

**3. Choices with the fact evicted** (window arms):

- W-n-0, observed-nonrec-far: chose an option in 24 of 25, 24 correct.
- W-n-0, derived-nonrec-far: chose an option in 25 of 25, 25 correct.
- W-np-0, observed-nonrec-far: chose an option in 24 of 25, 24 correct.
- W-np-0, derived-nonrec-far: chose an option in 23 of 25, 23 correct.

**4. Contrasts** (percentage points, 90% interval over the same template resamples, described, not tested):

- W-np-0 - W-n-0, observed-nonrec-far: +0.0 pp [-8.0, +8.0]
- W-np-0 - W-n-0, derived-nonrec-far: -8.0 pp [-16.0, +0.0]
- F-0 - W-n-0, observed-nonrec-far: +4.0 pp [+0.0, +12.0]
- F-0 - W-n-0, derived-nonrec-far: +0.0 pp [+0.0, +0.0]

**5. Responses:**

Thinking blocks by their presence only, so the thinking text is not inspected. A redacted_thinking block counts as one. The retained replies are those in the need step's first request. Their length is one reply's, the median over the replies pooled in the task cell.

| Arm | Refused responses | Categories | With a thinking block | Task cell | Retained replies at the need step (median per episode) | One retained reply's length (median characters) | Output tokens per episode | Cost per episode (USD) |
|---|---|---|---|---|---|---|---|---|
| W-n-0 | 0/1242 (0.0%) | - | 2/1242 (0.2%) | observed-nonrec-far | 12 | 752 | 7602 | 1.04674 |
| W-n-0 | 0/1242 (0.0%) | - | 2/1242 (0.2%) | derived-nonrec-far | 12 | 766 | 8128 | 1.04373 |
| W-np-0 | 8/1242 (0.6%) | {'refusal:reasoning_extraction': 8} | 3/1242 (0.2%) | observed-nonrec-far | 10 | 1625 | 12662 | 1.12794 |
| W-np-0 | 8/1242 (0.6%) | {'refusal:reasoning_extraction': 8} | 3/1242 (0.2%) | derived-nonrec-far | 11 | 874 | 11574 | 1.10775 |
| F-0 | 0/1242 (0.0%) | - | 0/1241 (0.0%) | observed-nonrec-far | 23.5 | 105 | 1184 | 0.20750 |
| F-0 | 0/1242 (0.0%) | - | 0/1241 (0.0%) | derived-nonrec-far | 23 | 107 | 1285 | 0.20046 |

F-0: request 21 of main-000203/observed-nonrec-far/base in run 20261112T205954Z-F-0-claude-sonnet-5-5 is not in its transcript, whose process was killed while writing it. The episode's record, usage and cost are counted. The thinking-block share is out of the responses in the transcripts, and the need-step columns leave the episode out if that request was its need step.

**Exclusions** (per arm and task cell, repeat 0, §13):

- W-n-0, observed-nonrec-far: {'keys': 25}
- W-n-0, derived-nonrec-far: {'keys': 25}
- W-np-0, observed-nonrec-far: {'keys': 25}
- W-np-0, derived-nonrec-far: {'keys': 25}
- F-0, observed-nonrec-far: {'keys': 25, 'dropped_duplicates': 1}
- F-0, derived-nonrec-far: {'keys': 25}

## Experiment 3: `persistgym_haiku_r12_block`

Not part of this reading (`--experiment` leaves it out).

## 7. Experiment 2 beside Haiku (described only, no contrast between the models)

Sonnet runs at effort medium, whose levels on Sonnet 5.5 are recalibrated, so it is not matched to Haiku's medium.

Templates 200-224 (25), both experiments.

| Model | Arm | Task cell | Success | P(carried) | Success given carried |
|---|---|---|---|---|---|
| claude-sonnet-5-5 | W-n-0 | observed-nonrec-far | 24/25 (96.0%) | 24/25 (96.0%) | 24/24 (100.0%) |
| claude-sonnet-5-5 | W-n-0 | derived-nonrec-far | 25/25 (100.0%) | 25/25 (100.0%) | 25/25 (100.0%) |
| claude-sonnet-5-5 | W-np-0 | observed-nonrec-far | 24/25 (96.0%) | 24/25 (96.0%) | 24/24 (100.0%) |
| claude-sonnet-5-5 | W-np-0 | derived-nonrec-far | 23/25 (92.0%) | 25/25 (100.0%) | 23/25 (92.0%) |
| claude-sonnet-5-5 | F-0 | observed-nonrec-far | 25/25 (100.0%) | n/a | n/a |
| claude-sonnet-5-5 | F-0 | derived-nonrec-far | 25/25 (100.0%) | n/a | n/a |
| claude-haiku-5-5 | W-n-0 | observed-nonrec-far | 1/25 (4.0%) | 1/25 (4.0%) | 1/1 (100.0%) |
| claude-haiku-5-5 | W-n-0 | derived-nonrec-far | 1/25 (4.0%) | 10/25 (40.0%) | 1/10 (10.0%) |
| claude-haiku-5-5 | W-np-0 | observed-nonrec-far | 21/25 (84.0%) | 22/25 (88.0%) | 21/22 (95.5%) |
| claude-haiku-5-5 | W-np-0 | derived-nonrec-far | 23/25 (92.0%) | 24/25 (96.0%) | 23/24 (95.8%) |
| claude-haiku-5-5 | W-nd-0 | observed-nonrec-far | 9/25 (36.0%) | 9/25 (36.0%) | 9/9 (100.0%) |
| claude-haiku-5-5 | W-nd-0 | derived-nonrec-far | 9/25 (36.0%) | 18/25 (72.0%) | 9/18 (50.0%) |
| claude-haiku-5-5 | W-nx-0 | observed-nonrec-far | 0/25 (0.0%) | 2/25 (8.0%) | 0/2 (0.0%) |
| claude-haiku-5-5 | W-nx-0 | derived-nonrec-far | 0/25 (0.0%) | 8/25 (32.0%) | 0/8 (0.0%) |

