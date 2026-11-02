# claude-haiku-5-5: R10's notes-instruction variants (persistgym_haiku_provenance)

**FINAL.** PREREG.md §17.10 (amendment R10). Exploratory: no test, no label. Repeat 0, the 4 far task cells, main templates 0-199. Not a model comparison. §2.8's accounting check: 1605 need steps replayed, 0 bugs. R9's W-n-0 ran on 2026-10-24, so differences from it mix the instruction with any change in serving.

| Arm | Task cell | Success | 90% interval | Refused episodes | Stopped responses |
|---|---|---|---|---|---|
| W-np-0 | observed-nonrec-far | 176/200 (88.0%) | 84.0% to 91.5% | 31 | {'refusal:bio': 85} |
| W-np-0 | observed-rec-far | 199/200 (99.5%) | 98.5% to 100.0% | 8 | {'refusal:bio': 18} |
| W-np-0 | derived-nonrec-far | 173/200 (86.5%) | 82.5% to 90.5% | 42 | {'refusal:bio': 119} |
| W-np-0 | derived-rec-far | 197/200 (98.5%) | 97.0% to 100.0% | 21 | {'refusal:bio': 36} |
| W-npd-0 | observed-nonrec-far | 173/200 (86.5%) | 82.5% to 90.5% | 30 | {'refusal:bio': 57} |
| W-npd-0 | observed-rec-far | 197/200 (98.5%) | 97.0% to 99.5% | 18 | {'refusal:bio': 30} |
| W-npd-0 | derived-nonrec-far | 177/200 (88.5%) | 84.5% to 92.0% | 37 | {'refusal:bio': 109} |
| W-npd-0 | derived-rec-far | 195/200 (97.5%) | 95.5% to 99.0% | 25 | {'refusal:bio': 51} |
| W-n-0 (R9, results/haiku_notes/20261024T073307Z) | observed-nonrec-far | 4/200 (2.0%) | 0.5% to 3.5% | 5 | {'refusal:bio': 12} |
| W-n-0 (R9, results/haiku_notes/20261024T073307Z) | observed-rec-far | 198/200 (99.0%) | 97.5% to 100.0% | 2 | {'refusal:bio': 5} |
| W-n-0 (R9, results/haiku_notes/20261024T073307Z) | derived-nonrec-far | 9/200 (4.5%) | 2.5% to 7.0% | 18 | {'refusal:bio': 39} |
| W-n-0 (R9, results/haiku_notes/20261024T073307Z) | derived-rec-far | 199/200 (99.5%) | 98.5% to 100.0% | 6 | {'refusal:bio': 9} |

**§2.8 accounting** (P(carried) is a lower bound):

| Arm | Task cell | S verbatim 0 | P(carried) | Used given carried | Not carried: success, no lookup | Not carried: success, lookup |
|---|---|---|---|---|---|---|
| W-np-0 | observed-nonrec-far | 200 | 187/200 (93.5%) | 176/187 (94.1%) | 0/13 (0.0%) | n/a |
| W-np-0 | observed-rec-far | 200 | 160/200 (80.0%) | 159/160 (99.4%) | n/a | 40/40 (100.0%) |
| W-np-0 | derived-nonrec-far | 200 | 182/200 (91.0%) | 173/182 (95.1%) | 0/18 (0.0%) | n/a |
| W-np-0 | derived-rec-far | 200 | 187/200 (93.5%) | 184/187 (98.4%) | n/a | 13/13 (100.0%) |
| W-npd-0 | observed-nonrec-far | 200 | 178/200 (89.0%) | 173/178 (97.2%) | 0/22 (0.0%) | n/a |
| W-npd-0 | observed-rec-far | 200 | 177/200 (88.5%) | 174/177 (98.3%) | n/a | 23/23 (100.0%) |
| W-npd-0 | derived-nonrec-far | 200 | 192/200 (96.0%) | 177/192 (92.2%) | 0/8 (0.0%) | n/a |
| W-npd-0 | derived-rec-far | 200 | 196/200 (98.0%) | 191/196 (97.4%) | n/a | 4/4 (100.0%) |
| W-n-0 (R9, results/haiku_notes/20261024T073307Z) | observed-nonrec-far | 200 | 8/200 (4.0%) | 4/8 (50.0%) | 0/192 (0.0%) | n/a |
| W-n-0 (R9, results/haiku_notes/20261024T073307Z) | observed-rec-far | 200 | 4/200 (2.0%) | 2/4 (50.0%) | n/a | 196/196 (100.0%) |
| W-n-0 (R9, results/haiku_notes/20261024T073307Z) | derived-nonrec-far | 200 | 72/200 (36.0%) | 9/72 (12.5%) | 0/128 (0.0%) | n/a |
| W-n-0 (R9, results/haiku_notes/20261024T073307Z) | derived-rec-far | 200 | 51/200 (25.5%) | 51/51 (100.0%) | 0/1 (0.0%) | 148/148 (100.0%) |

**Choices with the fact evicted** (not-recoverable far cells):

- W-np-0, observed-nonrec-far: chose an option in 176 of 200, 176 correct.
- W-np-0, derived-nonrec-far: chose an option in 173 of 200, 173 correct.
- W-npd-0, observed-nonrec-far: chose an option in 173 of 200, 173 correct.
- W-npd-0, derived-nonrec-far: chose an option in 177 of 200, 177 correct.
- W-n-0 (R9, results/haiku_notes/20261024T073307Z), observed-nonrec-far: chose an option in 4 of 200, 4 correct.
- W-n-0 (R9, results/haiku_notes/20261024T073307Z), derived-nonrec-far: chose an option in 9 of 200, 9 correct.

**Contrasts** (percentage points, 90% interval over the same template resamples; described, not tested):

- W-np-0 - W-n-0 (R9), observed-nonrec-far: +86.0 pp [+82.0, +90.0]
- W-np-0 - W-n-0 (R9), observed-rec-far: +0.5 pp [-1.0, +2.0]
- W-np-0 - W-n-0 (R9), derived-nonrec-far: +82.0 pp [+77.5, +86.5]
- W-np-0 - W-n-0 (R9), derived-rec-far: -1.0 pp [-2.5, +0.5]
- W-npd-0 - W-n-0 (R9), observed-nonrec-far: +84.5 pp [+80.5, +88.5]
- W-npd-0 - W-n-0 (R9), observed-rec-far: -0.5 pp [-2.5, +1.5]
- W-npd-0 - W-n-0 (R9), derived-nonrec-far: +84.0 pp [+79.0, +88.5]
- W-npd-0 - W-n-0 (R9), derived-rec-far: -2.0 pp [-4.0, +0.0]
- W-npd-0 - W-np-0, observed-nonrec-far: -1.5 pp [-6.5, +3.5]
- W-npd-0 - W-np-0, observed-rec-far: -1.0 pp [-2.5, +0.5]
- W-npd-0 - W-np-0, derived-nonrec-far: +2.0 pp [-3.0, +7.0]
- W-npd-0 - W-np-0, derived-rec-far: -1.0 pp [-3.5, +1.5]

**Replies** (not-recoverable far cells; R9's text patterns, which undercount on W-n-0's replies and may overcount on R10's, so the arms' counts are not comparable with R9's; pointers, not a coding):

| Arm | Cell, notes carried the fact | Episodes | Correct | Failed | Failed: declined | Failed: need reply disowns its figure | Failed: retracted before the need step |
|---|---|---|---|---|---|---|---|
| W-np-0 | observed-nonrec-far carried=True | 187 | 176 | 11 | 11 | 2 | 2 |
| W-np-0 | observed-nonrec-far carried=False | 13 | 0 | 13 | 13 | 2 | 0 |
| W-np-0 | derived-nonrec-far carried=True | 182 | 173 | 9 | 9 | 2 | 3 |
| W-np-0 | derived-nonrec-far carried=False | 18 | 0 | 18 | 18 | 1 | 0 |
| W-npd-0 | observed-nonrec-far carried=True | 178 | 173 | 5 | 5 | 0 | 1 |
| W-npd-0 | observed-nonrec-far carried=False | 22 | 0 | 22 | 22 | 0 | 0 |
| W-npd-0 | derived-nonrec-far carried=True | 192 | 177 | 15 | 15 | 3 | 2 |
| W-npd-0 | derived-nonrec-far carried=False | 8 | 0 | 8 | 8 | 0 | 0 |
| W-n-0 (R9, results/haiku_notes/20261024T073307Z) | observed-nonrec-far carried=True | 8 | 4 | 4 | 4 | 2 | 0 |
| W-n-0 (R9, results/haiku_notes/20261024T073307Z) | observed-nonrec-far carried=False | 192 | 0 | 192 | 192 | 2 | 0 |
| W-n-0 (R9, results/haiku_notes/20261024T073307Z) | derived-nonrec-far carried=True | 72 | 9 | 63 | 63 | 40 | 45 |
| W-n-0 (R9, results/haiku_notes/20261024T073307Z) | derived-nonrec-far carried=False | 128 | 0 | 128 | 128 | 0 | 0 |

**Cost per episode** (billed estimate, USD; output tokens):

| Arm | Task cell | Episodes | Cost per episode | Output tokens per episode |
|---|---|---|---|---|
| W-np-0 | observed-nonrec-far | 200 | 0.05459 | 13377 |
| W-np-0 | observed-rec-far | 200 | 0.05533 | 12757 |
| W-np-0 | derived-nonrec-far | 200 | 0.05453 | 13630 |
| W-np-0 | derived-rec-far | 200 | 0.05601 | 14059 |
| W-npd-0 | observed-nonrec-far | 200 | 0.05301 | 11798 |
| W-npd-0 | observed-rec-far | 200 | 0.05452 | 12505 |
| W-npd-0 | derived-nonrec-far | 200 | 0.05398 | 13006 |
| W-npd-0 | derived-rec-far | 200 | 0.05575 | 14091 |
| W-n-0 (R9, results/haiku_notes/20261024T073307Z) | observed-nonrec-far | 200 | 0.04322 | 2139 |
| W-n-0 (R9, results/haiku_notes/20261024T073307Z) | observed-rec-far | 200 | 0.04720 | 1905 |
| W-n-0 (R9, results/haiku_notes/20261024T073307Z) | derived-nonrec-far | 200 | 0.04368 | 2866 |
| W-n-0 (R9, results/haiku_notes/20261024T073307Z) | derived-rec-far | 200 | 0.04754 | 2547 |

Model strings: the arms ['claude-haiku-5-5'], R9's run ['claude-haiku-5-5'].

**Exclusions** (per arm and task cell, repeat 0; §13):

- W-np-0, observed-nonrec-far: {'keys': 200, 'dropped_duplicates': 2}
- W-np-0, observed-rec-far: {'keys': 200, 'dropped_duplicates': 2}
- W-np-0, derived-nonrec-far: {'keys': 200}
- W-np-0, derived-rec-far: {'keys': 200}
- W-npd-0, observed-nonrec-far: {'keys': 200}
- W-npd-0, observed-rec-far: {'keys': 200}
- W-npd-0, derived-nonrec-far: {'keys': 200}
- W-npd-0, derived-rec-far: {'keys': 200}
