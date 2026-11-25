# R13: Σ-n-0 on Haiku, and W-nk-0 beside a concurrent W-n-0

**FINAL.** PREREG.md §17.13 (amendment R13). Exploratory: no test, no label. Repeat 0, base episodes. Not a model comparison, and nothing is ranked. Intervals: 10,000 template resamples, seed SEED + 10.

## What it does not show

- Everything R8 to R12 say they do not show also holds here: one model per provider in the confirmatory sense, the same synthetic task family, thinking text not inspected.
- Experiment 4 is not concurrent with its comparators. R8's W-0 and F-0 ran on 2026-10-18, R9's W-n-0 on 2026-10-24 and R12's W-b-0 on 2026-11-12 and 2026-11-13. Success differences against them mix the summary with any change in serving since.
- One summary rule is run: ARC's summary prompts, with every earlier turn compacted when the context passes W. Other summary prompts, or summaries that keep recent turns, are not run.
- In experiment 5 the pinned block differs from W-n-0's scrolling history in two ways at once. The replies are kept outside the window, and the block carries its own label. A difference between the arms does not separate the two. One cap (600 reply tokens) is run.
- No model comparison. luna's Σ-n-0 is another model of another provider, on another API. Setting it beside Haiku's describes how each behaved on these episodes. It does not rank them.
- R12 experiment 1's arms ran on 2026-11-12, not at the same time as experiment 5, and are set beside it, described only.
- Coarse intervals: every arm plays each template once. P(carried) is a string match, so a lower bound, and the decline and disown counts are text patterns, not a validated coding.

## Experiment 4: claude-haiku-5-5, `persistgym_haiku_r13_sigma`

Main templates 0-199 in every arm (200 of the registered 0-199), resamples over 200 positions. §2.8's accounting check: 0 need steps replayed, 0 bugs.

**1. Success:**

| Arm | Task cell | Success | 90% interval | Refused episodes | Stopped responses |
|---|---|---|---|---|---|
| Σ-n-0 | observed-nonrec-near | 194/200 (97.0%) | 95.0% to 99.0% | 8 | {'refusal:bio': 13} |
| Σ-n-0 | observed-nonrec-far | 178/200 (89.0%) | 85.5% to 92.5% | 5 | {'refusal:bio': 12} |
| Σ-n-0 | observed-rec-near | 197/200 (98.5%) | 97.0% to 100.0% | 3 | {'refusal:bio': 4} |
| Σ-n-0 | observed-rec-far | 198/200 (99.0%) | 97.5% to 100.0% | 3 | {'refusal:bio': 5} |
| Σ-n-0 | derived-nonrec-near | 193/200 (96.5%) | 94.5% to 98.5% | 11 | {'refusal:bio': 26} |
| Σ-n-0 | derived-nonrec-far | 193/200 (96.5%) | 94.0% to 98.5% | 11 | {'refusal:bio': 44} |
| Σ-n-0 | derived-rec-near | 198/200 (99.0%) | 97.5% to 100.0% | 5 | {'refusal:bio': 6} |
| Σ-n-0 | derived-rec-far | 196/200 (98.0%) | 96.5% to 99.5% | 4 | {'refusal:bio': 7} |
| W-0 (R8) | observed-nonrec-near | 200/200 (100.0%) | 100.0% to 100.0% | 3 | {'refusal:bio': 6} |
| W-0 (R8) | observed-nonrec-far | 0/200 (0.0%) | 0.0% to 0.0% | 3 | {'refusal:bio': 7} |
| W-0 (R8) | observed-rec-near | 200/200 (100.0%) | 100.0% to 100.0% | 2 | {'refusal:bio': 3} |
| W-0 (R8) | observed-rec-far | 200/200 (100.0%) | 100.0% to 100.0% | 2 | {'refusal:bio': 2} |
| W-0 (R8) | derived-nonrec-near | 200/200 (100.0%) | 100.0% to 100.0% | 4 | {'refusal:bio': 5} |
| W-0 (R8) | derived-nonrec-far | 0/200 (0.0%) | 0.0% to 0.0% | 4 | {'refusal:bio': 14} |
| W-0 (R8) | derived-rec-near | 200/200 (100.0%) | 100.0% to 100.0% | 3 | {'refusal:bio': 4} |
| W-0 (R8) | derived-rec-far | 200/200 (100.0%) | 100.0% to 100.0% | 5 | {'refusal:bio': 7} |
| F-0 (R8) | observed-nonrec-near | 199/200 (99.5%) | 98.5% to 100.0% | 4 | {'refusal:bio': 10} |
| F-0 (R8) | observed-nonrec-far | 200/200 (100.0%) | 100.0% to 100.0% | 1 | {'refusal:bio': 3} |
| F-0 (R8) | observed-rec-near | 199/200 (99.5%) | 98.5% to 100.0% | 1 | {'refusal:bio': 4} |
| F-0 (R8) | observed-rec-far | 198/200 (99.0%) | 97.5% to 100.0% | 3 | {'refusal:bio': 8} |
| F-0 (R8) | derived-nonrec-near | 198/200 (99.0%) | 97.5% to 100.0% | 4 | {'refusal:bio': 10} |
| F-0 (R8) | derived-nonrec-far | 200/200 (100.0%) | 100.0% to 100.0% | 3 | {'refusal:bio': 12} |
| F-0 (R8) | derived-rec-near | 198/200 (99.0%) | 97.5% to 100.0% | 2 | {'refusal:bio': 10} |
| F-0 (R8) | derived-rec-far | 198/200 (99.0%) | 97.5% to 100.0% | 4 | {'refusal:bio': 12} |
| W-b-0 (R12) | observed-nonrec-near | 200/200 (100.0%) | 100.0% to 100.0% | 1 | {'refusal:bio': 1} |
| W-b-0 (R12) | observed-nonrec-far | 0/200 (0.0%) | 0.0% to 0.0% | 3 | {'refusal:bio': 6} |
| W-b-0 (R12) | observed-rec-near | 200/200 (100.0%) | 100.0% to 100.0% | 1 | {'refusal:bio': 1} |
| W-b-0 (R12) | observed-rec-far | 200/200 (100.0%) | 100.0% to 100.0% | 1 | {'refusal:bio': 1} |
| W-b-0 (R12) | derived-nonrec-near | 200/200 (100.0%) | 100.0% to 100.0% | 2 | {'refusal:bio': 2} |
| W-b-0 (R12) | derived-nonrec-far | 0/200 (0.0%) | 0.0% to 0.0% | 4 | {'refusal:bio': 7} |
| W-b-0 (R12) | derived-rec-near | 200/200 (100.0%) | 100.0% to 100.0% | 3 | {'refusal:bio': 4} |
| W-b-0 (R12) | derived-rec-far | 200/200 (100.0%) | 100.0% to 100.0% | 2 | {'refusal:bio': 4} |

**2. Contrasts** (percentage points, 90% interval over the same template resamples, described, not tested):

The comparators ran on 2026-10-18 (R8), 2026-10-24 (R9) and 2026-11-12 to 13 (R12), so these differences mix the cell with any change in serving (see What it does not show).

- Σ-n-0 - W-0 (R8), observed-nonrec-near: -3.0 pp [-5.0, -1.0]
- Σ-n-0 - W-0 (R8), observed-nonrec-far: +89.0 pp [+85.5, +92.5]
- Σ-n-0 - W-0 (R8), observed-rec-near: -1.5 pp [-3.0, +0.0]
- Σ-n-0 - W-0 (R8), observed-rec-far: -1.0 pp [-2.5, +0.0]
- Σ-n-0 - W-0 (R8), derived-nonrec-near: -3.5 pp [-5.5, -1.5]
- Σ-n-0 - W-0 (R8), derived-nonrec-far: +96.5 pp [+94.0, +98.5]
- Σ-n-0 - W-0 (R8), derived-rec-near: -1.0 pp [-2.5, +0.0]
- Σ-n-0 - W-0 (R8), derived-rec-far: -2.0 pp [-3.5, -0.5]
- Σ-n-0 - F-0 (R8), observed-nonrec-near: -2.5 pp [-4.5, -0.5]
- Σ-n-0 - F-0 (R8), observed-nonrec-far: -11.0 pp [-14.5, -7.5]
- Σ-n-0 - F-0 (R8), observed-rec-near: -1.0 pp [-2.5, +0.5]
- Σ-n-0 - F-0 (R8), observed-rec-far: +0.0 pp [-1.5, +1.5]
- Σ-n-0 - F-0 (R8), derived-nonrec-near: -2.5 pp [-5.0, +0.0]
- Σ-n-0 - F-0 (R8), derived-nonrec-far: -3.5 pp [-6.0, -1.5]
- Σ-n-0 - F-0 (R8), derived-rec-near: +0.0 pp [-1.0, +1.0]
- Σ-n-0 - F-0 (R8), derived-rec-far: -1.0 pp [-3.0, +1.0]
- Σ-n-0 - W-b-0 (R12), observed-nonrec-near: -3.0 pp [-5.0, -1.0]
- Σ-n-0 - W-b-0 (R12), observed-nonrec-far: +89.0 pp [+85.5, +92.5]
- Σ-n-0 - W-b-0 (R12), observed-rec-near: -1.5 pp [-3.0, +0.0]
- Σ-n-0 - W-b-0 (R12), observed-rec-far: -1.0 pp [-2.5, +0.0]
- Σ-n-0 - W-b-0 (R12), derived-nonrec-near: -3.5 pp [-5.5, -1.5]
- Σ-n-0 - W-b-0 (R12), derived-nonrec-far: +96.5 pp [+94.0, +98.5]
- Σ-n-0 - W-b-0 (R12), derived-rec-near: -1.0 pp [-2.5, +0.0]
- Σ-n-0 - W-b-0 (R12), derived-rec-far: -2.0 pp [-3.5, -0.5]
- Σ-n-0 - W-n-0 (R9), observed-nonrec-far: +87.0 pp [+83.0, +91.0]
- Σ-n-0 - W-n-0 (R9), derived-nonrec-far: +92.0 pp [+88.5, +95.0]

R9's W-n-0 in its contrast: templates 0-199 (200), the templates read that it finished in both not-recoverable far cells.

**3. §2.8 accounting in the bridge** (Σ-n-0):

P(carried) is a string match on the need step's first request: a lower bound. Each cell gives P(carried), then the success given carried.

| Arm | Task cell | S verbatim 0 | In the bridge | In the retained replies | In either |
|---|---|---|---|---|---|
| Σ-n-0 | observed-nonrec-near | 0 | n/a, n/a | n/a, n/a | n/a, n/a |
| Σ-n-0 | observed-nonrec-far | 200 | 184/200 (92.0%), 178/184 (96.7%) | 0/200 (0.0%), n/a | 184/200 (92.0%), 178/184 (96.7%) |
| Σ-n-0 | observed-rec-near | 0 | n/a, n/a | n/a, n/a | n/a, n/a |
| Σ-n-0 | observed-rec-far | 200 | 171/200 (85.5%), 170/171 (99.4%) | 1/200 (0.5%), 1/1 (100.0%) | 171/200 (85.5%), 170/171 (99.4%) |
| Σ-n-0 | derived-nonrec-near | 21 | 0/21 (0.0%), n/a | 12/21 (57.1%), 12/12 (100.0%) | 12/21 (57.1%), 12/12 (100.0%) |
| Σ-n-0 | derived-nonrec-far | 198 | 198/198 (100.0%), 193/198 (97.5%) | 5/198 (2.5%), 5/5 (100.0%) | 198/198 (100.0%), 193/198 (97.5%) |
| Σ-n-0 | derived-rec-near | 21 | 0/21 (0.0%), n/a | 9/21 (42.9%), 9/9 (100.0%) | 9/21 (42.9%), 9/9 (100.0%) |
| Σ-n-0 | derived-rec-far | 199 | 198/199 (99.5%), 195/198 (98.5%) | 4/199 (2.0%), 4/4 (100.0%) | 198/199 (99.5%), 195/198 (98.5%) |

**4. Compaction and near cells:**

| Task cell | Episodes | Compactions per episode | compacted_between: n, S = 1, success |
|---|---|---|---|
| observed-nonrec-near | 200 | 1.00 | 0: 200, 200, 194 |
| observed-nonrec-far | 200 | 1.00 | 1: 200, 184, 178 |
| observed-rec-near | 200 | 0.99 | 0: 199, 199, 197; none: 1, 0, 0 |
| observed-rec-far | 200 | 1.00 | 1: 200, 171, 198 |
| derived-nonrec-near | 200 | 0.99 | 0: 178, 178, 174; 1: 21, 12, 19; none: 1, 0, 0 |
| derived-nonrec-far | 200 | 0.99 | 1: 198, 198, 193; none: 2, 0, 0 |
| derived-rec-near | 200 | 0.99 | 0: 178, 178, 177; 1: 21, 9, 21; none: 1, 0, 0 |
| derived-rec-far | 200 | 1.00 | 1: 199, 198, 196; none: 1, 0, 0 |

Near-cell episodes whose evidence was not in the need step's request (need_payload.S false), and their success:

- Σ-n-0: derived-nonrec-near 21 of 200 (19/21 (90.5%)), derived-rec-near 21 of 200 (21/21 (100.0%)), observed-nonrec-near 0 of 200 (n/a), observed-rec-near 0 of 200 (n/a).
- W-0 (R8): derived-nonrec-near 0 of 200 (n/a), derived-rec-near 0 of 200 (n/a), observed-nonrec-near 0 of 200 (n/a), observed-rec-near 0 of 200 (n/a).
- F-0 (R8): derived-nonrec-near 0 of 200 (n/a), derived-rec-near 0 of 200 (n/a), observed-nonrec-near 0 of 200 (n/a), observed-rec-near 0 of 200 (n/a).
- W-b-0 (R12): derived-nonrec-near 0 of 200 (n/a), derived-rec-near 0 of 200 (n/a), observed-nonrec-near 0 of 200 (n/a), observed-rec-near 0 of 200 (n/a).

**5. Summary calls** (Σ-n-0):

| Task cell | Summary requests per episode | Failed attempts per episode | Stopped summary responses | AGENT_ERROR episodes | Bridge tokens (median) | At the need step (median) | Summary output tokens (median per call, mean per episode) |
|---|---|---|---|---|---|---|---|
| observed-nonrec-near | 1.01 | 0.015 | {'refusal:bio': 3} | 0 | 554 | 554 | 1183, 1211 |
| observed-nonrec-far | 1.01 | 0.010 | {'refusal:bio': 2} | 0 | 554 | 554 | 1220, 1238 |
| observed-rec-near | 1.01 | 0.020 | {'refusal:bio': 4} | 1 | 545 | 545 | 1239, 1241 |
| observed-rec-far | 1.00 | 0.005 | {'refusal:bio': 1} | 0 | 536 | 536 | 1177, 1193 |
| derived-nonrec-near | 1.02 | 0.025 | {'refusal:bio': 5} | 1 | 546 | 546 | 1166, 1210 |
| derived-nonrec-far | 1.03 | 0.045 | {'refusal:bio': 9} | 2 | 572 | 572 | 1172, 1246 |
| derived-rec-near | 1.01 | 0.020 | {'refusal:bio': 4} | 1 | 556 | 556 | 1173, 1207 |
| derived-rec-far | 1.03 | 0.030 | {'refusal:bio': 6} | 1 | 548 | 548 | 1119, 1193 |
| all | 1.02 | 0.021 | {'refusal:bio': 34} | 6 | 552 | 552 | 1180, 1217 |

**6. Choices with the fact evicted** (not-recoverable far cells):

- Σ-n-0, observed-nonrec-far: chose an option in 178 of 200, 178 correct.
- Σ-n-0, derived-nonrec-far: chose an option in 193 of 200, 193 correct.
- W-0 (R8), observed-nonrec-far: chose an option in 0 of 200, 0 correct.
- W-0 (R8), derived-nonrec-far: chose an option in 0 of 200, 0 correct.
- W-b-0 (R12), observed-nonrec-far: chose an option in 1 of 200, 0 correct.
- W-b-0 (R12), derived-nonrec-far: chose an option in 0 of 200, 0 correct.

**7. Responses:**

Thinking blocks by their presence only, so the thinking text is not inspected. A redacted_thinking block counts as one.

| Arm | Refused step responses | Categories | Step responses with a thinking block | Summary responses with one |
|---|---|---|---|---|
| Σ-n-0 | 117/38453 (0.3%) | {'refusal:bio': 117} | 17757/38453 (46.2%) | 1620/1629 (99.4%) |

| Arm | Task cell | Episodes | Output tokens | Cost (USD) | Input tokens | Cache-read share of input |
|---|---|---|---|---|---|---|
| Σ-n-0 | observed-nonrec-near | 200 | 3112 | 0.01522 | 398,170 | 78.8% |
| Σ-n-0 | observed-nonrec-far | 200 | 3126 | 0.01495 | 398,006 | 79.4% |
| Σ-n-0 | observed-rec-near | 200 | 2928 | 0.01515 | 399,715 | 78.9% |
| Σ-n-0 | observed-rec-far | 200 | 2937 | 0.01497 | 403,201 | 79.6% |
| Σ-n-0 | derived-nonrec-near | 200 | 3380 | 0.01507 | 398,321 | 79.5% |
| Σ-n-0 | derived-nonrec-far | 200 | 3515 | 0.01514 | 398,795 | 79.5% |
| Σ-n-0 | derived-rec-near | 200 | 3044 | 0.01493 | 399,716 | 79.5% |
| Σ-n-0 | derived-rec-far | 200 | 3149 | 0.01503 | 401,065 | 79.5% |
| Σ-n-0 | all | 1600 | 3149 | 0.01506 | 399,624 | 79.4% |
| W-0 (R8) | observed-nonrec-near | 200 | 970 | 0.04237 | 540,153 | 41.3% |
| W-0 (R8) | observed-nonrec-far | 200 | 1350 | 0.04225 | 540,114 | 41.8% |
| W-0 (R8) | observed-rec-near | 200 | 1155 | 0.04263 | 542,994 | 41.4% |
| W-0 (R8) | observed-rec-far | 200 | 1260 | 0.04638 | 574,494 | 39.4% |
| W-0 (R8) | derived-nonrec-near | 200 | 1199 | 0.04178 | 540,437 | 42.4% |
| W-0 (R8) | derived-nonrec-far | 200 | 1681 | 0.04180 | 540,697 | 42.8% |
| W-0 (R8) | derived-rec-near | 200 | 1361 | 0.04217 | 543,301 | 42.3% |
| W-0 (R8) | derived-rec-far | 200 | 1557 | 0.04607 | 575,050 | 40.2% |
| W-0 (R8) | all | 1600 | 1317 | 0.04318 | 549,655 | 41.4% |
| F-0 (R8) | observed-nonrec-near | 200 | 939 | 0.01269 | 638,843 | 92.1% |
| F-0 (R8) | observed-nonrec-far | 200 | 977 | 0.01241 | 639,157 | 92.5% |
| F-0 (R8) | observed-rec-near | 200 | 1172 | 0.01286 | 642,883 | 92.1% |
| F-0 (R8) | observed-rec-far | 200 | 1154 | 0.01262 | 641,865 | 92.4% |
| F-0 (R8) | derived-nonrec-near | 200 | 1147 | 0.01225 | 639,013 | 92.8% |
| F-0 (R8) | derived-nonrec-far | 200 | 1188 | 0.01232 | 639,408 | 92.7% |
| F-0 (R8) | derived-rec-near | 200 | 1333 | 0.01239 | 642,386 | 92.8% |
| F-0 (R8) | derived-rec-far | 200 | 1408 | 0.01261 | 643,963 | 92.6% |
| F-0 (R8) | all | 1600 | 1165 | 0.01252 | 640,940 | 92.5% |
| W-b-0 (R12) | observed-nonrec-near | 200 | 969 | 0.01291 | 453,736 | 84.9% |
| W-b-0 (R12) | observed-nonrec-far | 200 | 1372 | 0.01228 | 453,823 | 86.5% |
| W-b-0 (R12) | observed-rec-near | 200 | 1191 | 0.01307 | 456,360 | 84.9% |
| W-b-0 (R12) | observed-rec-far | 200 | 1247 | 0.01322 | 478,744 | 85.8% |
| W-b-0 (R12) | derived-nonrec-near | 200 | 1189 | 0.01212 | 453,782 | 86.6% |
| W-b-0 (R12) | derived-nonrec-far | 200 | 1528 | 0.01190 | 454,006 | 87.4% |
| W-b-0 (R12) | derived-rec-near | 200 | 1366 | 0.01229 | 456,363 | 86.6% |
| W-b-0 (R12) | derived-rec-far | 200 | 1427 | 0.01286 | 478,995 | 86.6% |
| W-b-0 (R12) | all | 1600 | 1286 | 0.01258 | 460,726 | 86.2% |

**8. Beside luna's Σ-n-0** (described only, no contrast between the models):

luna's Σ-n-0 is another model on another API: set beside Haiku's, described only, with no contrast between the models.

Σ-n-0 (luna) (gpt-6-luna): templates 0-199 (200).

| Task cell | Success | P(carried), either | Success given carried |
|---|---|---|---|
| observed-nonrec-near | 200/200 (100.0%) | n/a | n/a |
| observed-nonrec-far | 86/200 (43.0%) | 77/200 (38.5%) | 77/77 (100.0%) |
| observed-rec-near | 200/200 (100.0%) | n/a | n/a |
| observed-rec-far | 200/200 (100.0%) | 62/200 (31.0%) | 62/62 (100.0%) |
| derived-nonrec-near | 194/200 (97.0%) | 10/21 (47.6%) | 10/10 (100.0%) |
| derived-nonrec-far | 184/200 (92.0%) | 184/200 (92.0%) | 184/184 (100.0%) |
| derived-rec-near | 200/200 (100.0%) | 7/21 (33.3%) | 7/7 (100.0%) |
| derived-rec-far | 200/200 (100.0%) | 181/200 (90.5%) | 181/181 (100.0%) |

| Task cell | P(carried) in the bridge | compacted_between: n, S = 1, success |
|---|---|---|
| observed-nonrec-near | n/a | 0: 200, 200, 200 |
| observed-nonrec-far | 77/200 (38.5%) | 1: 200, 77, 86 |
| observed-rec-near | n/a | 0: 200, 200, 200 |
| observed-rec-far | 62/200 (31.0%) | 1: 200, 62, 200 |
| derived-nonrec-near | 0/21 (0.0%) | 0: 179, 179, 178; 1: 21, 10, 16 |
| derived-nonrec-far | 184/200 (92.0%) | 1: 200, 184, 184 |
| derived-rec-near | 0/21 (0.0%) | 0: 179, 179, 179; 1: 21, 7, 21 |
| derived-rec-far | 181/200 (90.5%) | 1: 200, 181, 200 |

**Exclusions** (per arm and task cell, repeat 0, §13):

- Σ-n-0, observed-nonrec-near: {'keys': 200}
- Σ-n-0, observed-nonrec-far: {'keys': 200}
- Σ-n-0, observed-rec-near: {'keys': 200}
- Σ-n-0, observed-rec-far: {'keys': 200}
- Σ-n-0, derived-nonrec-near: {'keys': 200}
- Σ-n-0, derived-nonrec-far: {'keys': 200}
- Σ-n-0, derived-rec-near: {'keys': 200}
- Σ-n-0, derived-rec-far: {'keys': 200}

## Experiment 5: claude-haiku-5-5, `persistgym_haiku_r13_pinned`

Main templates 200-299 in every arm (100 of the registered 200-299), resamples over 100 positions. §2.8's accounting check: 400 need steps replayed, 0 bugs.

**1. Success:**

| Arm | Task cell | Success | 90% interval | Refused episodes | Stopped responses |
|---|---|---|---|---|---|
| W-nk-0 | observed-nonrec-far | 74/100 (74.0%) | 67.0% to 81.0% | 10 | {'refusal:bio': 24} |
| W-nk-0 | derived-nonrec-far | 84/100 (84.0%) | 78.0% to 90.0% | 16 | {'refusal:bio': 71} |
| W-n-0 | observed-nonrec-far | 2/100 (2.0%) | 0.0% to 5.0% | 1 | {'refusal:bio': 3} |
| W-n-0 | derived-nonrec-far | 2/100 (2.0%) | 0.0% to 5.0% | 7 | {'refusal:bio': 20} |

**2. Contrasts** (percentage points, 90% interval over the same template resamples, described, not tested):

W-nk-0's block keeps the replies outside the window and labels them, so the contrast does not separate the two (see What it does not show).

- W-nk-0 - W-n-0, observed-nonrec-far: +72.0 pp [+64.0, +79.0]
- W-nk-0 - W-n-0, derived-nonrec-far: +82.0 pp [+76.0, +88.0]

**3. §2.8 accounting** (each source apart, and either):

P(carried) is a string match on the need step's first request: a lower bound. Each cell gives P(carried), then the success given carried.

| Arm | Task cell | S verbatim 0 | In the pinned block | In the retained replies | In either |
|---|---|---|---|---|---|
| W-nk-0 | observed-nonrec-far | 100 | 78/100 (78.0%), 74/78 (94.9%) | 3/100 (3.0%), 3/3 (100.0%) | 78/100 (78.0%), 74/78 (94.9%) |
| W-nk-0 | derived-nonrec-far | 100 | 97/100 (97.0%), 84/97 (86.6%) | 6/100 (6.0%), 4/6 (66.7%) | 97/100 (97.0%), 84/97 (86.6%) |
| W-n-0 | observed-nonrec-far | 100 | - | 4/100 (4.0%), 2/4 (50.0%) | 4/100 (4.0%), 2/4 (50.0%) |
| W-n-0 | derived-nonrec-far | 100 | - | 25/100 (25.0%), 2/25 (8.0%) | 25/100 (25.0%), 2/25 (8.0%) |

**4. The block at the need step** (W-nk-0's first request there):

| Task cell | Reached the need step | With the block | Block tokens (median) | Replies in it (median) | Newest reply alone over the cap | Replies left out (episodes) |
|---|---|---|---|---|---|---|
| observed-nonrec-far | 100 | 100 | 290 | 8.0 | 0 | 2 (1) |
| derived-nonrec-far | 100 | 100 | 348 | 8.0 | 0 | 0 (0) |

**5. Declines** (failed episodes whose carried notes held the fact):

Declines and disowns are R9's text patterns (`analysis.haiku_notes_replies`), which R9's hand checks found to undercount (40 of 62 declines, 45 of 63 retractions): pointers rather than a validated coding.

| Arm | Task cell | Carried | Failed, carried | Declined | Disowns its figure | Either |
|---|---|---|---|---|---|---|
| W-nk-0 | observed-nonrec-far | 78 of 100 | 4 | 4 | 0 | 4 |
| W-nk-0 | derived-nonrec-far | 97 of 100 | 13 | 13 | 1 | 13 |
| W-nk-0 | both | 175 of 200 | 17 | 17 | 1 | 17 |
| W-n-0 | observed-nonrec-far | 4 of 100 | 2 | 2 | 2 | 2 |
| W-n-0 | derived-nonrec-far | 25 of 100 | 23 | 23 | 16 | 23 |
| W-n-0 | both | 29 of 200 | 25 | 25 | 18 | 25 |

**6. Choices with the fact evicted** (not-recoverable far cells):

- W-nk-0, observed-nonrec-far: chose an option in 74 of 100, 74 correct.
- W-nk-0, derived-nonrec-far: chose an option in 84 of 100, 84 correct.
- W-n-0, observed-nonrec-far: chose an option in 2 of 100, 2 correct.
- W-n-0, derived-nonrec-far: chose an option in 2 of 100, 2 correct.

**7. Responses:**

Thinking blocks by their presence only, so the thinking text is not inspected. A redacted_thinking block counts as one.

| Arm | Refused step responses | Categories | Step responses with a thinking block | Summary responses with one |
|---|---|---|---|---|
| W-nk-0 | 95/4812 (2.0%) | {'refusal:bio': 95} | 2015/4812 (41.9%) | - |
| W-n-0 | 23/4812 (0.5%) | {'refusal:bio': 23} | 2176/4812 (45.2%) | - |

The retained replies at the need step's first request: one reply's length, the median over the replies pooled in the task cell.

| Arm | Task cell | Retained replies (median per episode) | One retained reply's length (median characters) |
|---|---|---|---|
| W-nk-0 | observed-nonrec-far | 14.0 | 105 |
| W-nk-0 | derived-nonrec-far | 14.0 | 105 |
| W-n-0 | observed-nonrec-far | 14.0 | 105 |
| W-n-0 | derived-nonrec-far | 14.0 | 112 |

| Arm | Task cell | Episodes | Output tokens | Cost (USD) | Input tokens | Cache-read share of input |
|---|---|---|---|---|---|---|
| W-nk-0 | observed-nonrec-far | 100 | 1764 | 0.04374 | 550,224 | 41.0% |
| W-nk-0 | derived-nonrec-far | 100 | 2257 | 0.04381 | 551,608 | 41.4% |
| W-nk-0 | all | 200 | 2011 | 0.04377 | 550,916 | 41.2% |
| W-n-0 | observed-nonrec-far | 100 | 2054 | 0.04349 | 546,919 | 41.2% |
| W-n-0 | derived-nonrec-far | 100 | 2772 | 0.04375 | 548,721 | 41.6% |
| W-n-0 | all | 200 | 2413 | 0.04362 | 547,820 | 41.4% |

**8. Rounds** (described only):

Task cell "all" pools the task cells: success per arm and round. The rows per task cell are extra detail.

"First arm" is the arm whose run started the round, read from the runs' start times below. "Registered" is the order §17.13 registers.

| Round | Templates | Read | First arm | Registered first arm | Arm | Task cell | Success |
|---|---|---|---|---|---|---|---|
| 1 | 200-224 | 25 | W-nk-0 | W-nk-0 | W-nk-0 | all | 37/50 (74.0%) |
| 1 | 200-224 | 25 | W-nk-0 | W-nk-0 | W-nk-0 | observed-nonrec-far | 15/25 (60.0%) |
| 1 | 200-224 | 25 | W-nk-0 | W-nk-0 | W-nk-0 | derived-nonrec-far | 22/25 (88.0%) |
| 1 | 200-224 | 25 | W-nk-0 | W-nk-0 | W-n-0 | all | 0/50 (0.0%) |
| 1 | 200-224 | 25 | W-nk-0 | W-nk-0 | W-n-0 | observed-nonrec-far | 0/25 (0.0%) |
| 1 | 200-224 | 25 | W-nk-0 | W-nk-0 | W-n-0 | derived-nonrec-far | 0/25 (0.0%) |
| 2 | 225-249 | 25 | W-n-0 | W-n-0 | W-nk-0 | all | 43/50 (86.0%) |
| 2 | 225-249 | 25 | W-n-0 | W-n-0 | W-nk-0 | observed-nonrec-far | 20/25 (80.0%) |
| 2 | 225-249 | 25 | W-n-0 | W-n-0 | W-nk-0 | derived-nonrec-far | 23/25 (92.0%) |
| 2 | 225-249 | 25 | W-n-0 | W-n-0 | W-n-0 | all | 2/50 (4.0%) |
| 2 | 225-249 | 25 | W-n-0 | W-n-0 | W-n-0 | observed-nonrec-far | 2/25 (8.0%) |
| 2 | 225-249 | 25 | W-n-0 | W-n-0 | W-n-0 | derived-nonrec-far | 0/25 (0.0%) |
| 3 | 250-274 | 25 | W-nk-0 | W-nk-0 | W-nk-0 | all | 37/50 (74.0%) |
| 3 | 250-274 | 25 | W-nk-0 | W-nk-0 | W-nk-0 | observed-nonrec-far | 19/25 (76.0%) |
| 3 | 250-274 | 25 | W-nk-0 | W-nk-0 | W-nk-0 | derived-nonrec-far | 18/25 (72.0%) |
| 3 | 250-274 | 25 | W-nk-0 | W-nk-0 | W-n-0 | all | 1/50 (2.0%) |
| 3 | 250-274 | 25 | W-nk-0 | W-nk-0 | W-n-0 | observed-nonrec-far | 0/25 (0.0%) |
| 3 | 250-274 | 25 | W-nk-0 | W-nk-0 | W-n-0 | derived-nonrec-far | 1/25 (4.0%) |
| 4 | 275-299 | 25 | W-n-0 | W-n-0 | W-nk-0 | all | 41/50 (82.0%) |
| 4 | 275-299 | 25 | W-n-0 | W-n-0 | W-nk-0 | observed-nonrec-far | 20/25 (80.0%) |
| 4 | 275-299 | 25 | W-n-0 | W-n-0 | W-nk-0 | derived-nonrec-far | 21/25 (84.0%) |
| 4 | 275-299 | 25 | W-n-0 | W-n-0 | W-n-0 | all | 1/50 (2.0%) |
| 4 | 275-299 | 25 | W-n-0 | W-n-0 | W-n-0 | observed-nonrec-far | 0/25 (0.0%) |
| 4 | 275-299 | 25 | W-n-0 | W-n-0 | W-n-0 | derived-nonrec-far | 1/25 (4.0%) |

| Run | Arm | Templates | Ending | Started (UTC) | Finished (UTC) |
|---|---|---|---|---|---|
| 20261125T011046Z-W-nk-0-claude-haiku-5-5 | W-nk-0 | 200-224 | COMPLETED | 2026-11-25T01:10:48+00:00 | 2026-11-25T01:20:49+00:00 |
| 20261125T012059Z-W-n-0-claude-haiku-5-5 | W-n-0 | 200-224 | COMPLETED | 2026-11-25T01:21:01+00:00 | 2026-11-25T01:30:51+00:00 |
| 20261125T013102Z-W-n-0-claude-haiku-5-5 | W-n-0 | 225-249 | COMPLETED | 2026-11-25T01:31:04+00:00 | 2026-11-25T01:40:27+00:00 |
| 20261125T014036Z-W-nk-0-claude-haiku-5-5 | W-nk-0 | 225-249 | COMPLETED | 2026-11-25T01:40:38+00:00 | 2026-11-25T01:49:47+00:00 |
| 20261125T014957Z-W-nk-0-claude-haiku-5-5 | W-nk-0 | 250-274 | COMPLETED | 2026-11-25T01:49:59+00:00 | 2026-11-25T01:59:56+00:00 |
| 20261125T020005Z-W-n-0-claude-haiku-5-5 | W-n-0 | 250-274 | COMPLETED | 2026-11-25T02:00:07+00:00 | 2026-11-25T02:10:11+00:00 |
| 20261125T021021Z-W-n-0-claude-haiku-5-5 | W-n-0 | 275-299 | COMPLETED | 2026-11-25T02:10:22+00:00 | 2026-11-25T02:20:13+00:00 |
| 20261125T022022Z-W-nk-0-claude-haiku-5-5 | W-nk-0 | 275-299 | COMPLETED | 2026-11-25T02:20:23+00:00 | 2026-11-25T02:29:29+00:00 |

**9. Beside R12 experiment 1's arms** (described only):

R12 experiment 1 ran on 2026-11-12, not at the same time as experiment 5.

W-n-0 (R12) (claude-haiku-5-5): templates 200-299 (100).

| Task cell | Success | P(carried), either | Success given carried |
|---|---|---|---|
| observed-nonrec-far | 3/100 (3.0%) | 3/100 (3.0%) | 3/3 (100.0%) |
| derived-nonrec-far | 5/100 (5.0%) | 34/100 (34.0%) | 5/34 (14.7%) |

W-np-0 (R12) (claude-haiku-5-5): templates 200-299 (100).

| Task cell | Success | P(carried), either | Success given carried |
|---|---|---|---|
| observed-nonrec-far | 85/100 (85.0%) | 87/100 (87.0%) | 85/87 (97.7%) |
| derived-nonrec-far | 86/100 (86.0%) | 89/100 (89.0%) | 86/89 (96.6%) |

W-nd-0 (R12) (claude-haiku-5-5): templates 200-299 (100).

| Task cell | Success | P(carried), either | Success given carried |
|---|---|---|---|
| observed-nonrec-far | 35/100 (35.0%) | 38/100 (38.0%) | 35/38 (92.1%) |
| derived-nonrec-far | 44/100 (44.0%) | 67/100 (67.0%) | 44/67 (65.7%) |

W-nx-0 (R12) (claude-haiku-5-5): templates 200-299 (100).

| Task cell | Success | P(carried), either | Success given carried |
|---|---|---|---|
| observed-nonrec-far | 1/100 (1.0%) | 3/100 (3.0%) | 1/3 (33.3%) |
| derived-nonrec-far | 1/100 (1.0%) | 26/100 (26.0%) | 1/26 (3.8%) |

**Exclusions** (per arm and task cell, repeat 0, §13):

- W-nk-0, observed-nonrec-far: {'keys': 100}
- W-nk-0, derived-nonrec-far: {'keys': 100}
- W-n-0, observed-nonrec-far: {'keys': 100}
- W-n-0, derived-nonrec-far: {'keys': 100}

