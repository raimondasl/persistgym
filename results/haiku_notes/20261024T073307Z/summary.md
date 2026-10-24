# claude-haiku-5-5 W-n-0 (persistgym_haiku_notes): R9's descriptive readings

**FINAL.** PREREG.md §17.9 (amendment R9). Exploratory: no test, no label. Repeat 0, 1600 counted episodes. Not a model comparison. §2.8's accounting check: 1600 need steps replayed, 0 bugs.

| Task cell | Success | 90% interval | Refused episodes | Stopped responses |
|---|---|---|---|---|
| observed-nonrec-near | 195/200 (97.5%) | 95.5% to 99.0% | 5 | {'refusal:bio': 9} |
| observed-nonrec-far | 4/200 (2.0%) | 0.5% to 3.5% | 5 | {'refusal:bio': 12} |
| observed-rec-near | 199/200 (99.5%) | 98.5% to 100.0% | 3 | {'refusal:bio': 3} |
| observed-rec-far | 198/200 (99.0%) | 97.5% to 100.0% | 2 | {'refusal:bio': 5} |
| derived-nonrec-near | 199/200 (99.5%) | 98.5% to 100.0% | 7 | {'refusal:bio': 15} |
| derived-nonrec-far | 9/200 (4.5%) | 2.5% to 7.0% | 18 | {'refusal:bio': 39} |
| derived-rec-near | 199/200 (99.5%) | 98.5% to 100.0% | 4 | {'refusal:bio': 7} |
| derived-rec-far | 199/200 (99.5%) | 98.5% to 100.0% | 6 | {'refusal:bio': 9} |

**§2.8 accounting** (P(carried) is a lower bound):

| Task cell | S verbatim 0 | Near losses | P(carried) | Used given carried | Not carried: success, no lookup | Not carried: success, lookup |
|---|---|---|---|---|---|---|
| observed-nonrec-near | 0 | 0 | n/a | n/a | n/a | n/a |
| observed-nonrec-far | 200 | - | 8/200 (4.0%) | 4/8 (50.0%) | 0/192 (0.0%) | n/a |
| observed-rec-near | 0 | 0 | n/a | n/a | n/a | n/a |
| observed-rec-far | 200 | - | 4/200 (2.0%) | 2/4 (50.0%) | n/a | 196/196 (100.0%) |
| derived-nonrec-near | 0 | 0 | n/a | n/a | n/a | n/a |
| derived-nonrec-far | 200 | - | 72/200 (36.0%) | 9/72 (12.5%) | 0/128 (0.0%) | n/a |
| derived-rec-near | 0 | 0 | n/a | n/a | n/a | n/a |
| derived-rec-far | 200 | - | 51/200 (25.5%) | 51/51 (100.0%) | 0/1 (0.0%) | 148/148 (100.0%) |

**Choices with the fact evicted** (not-recoverable far cells):

- observed-nonrec-far: chose an option in 4 of 200, 4 correct.
- derived-nonrec-far: chose an option in 9 of 200, 9 correct.

**Within Haiku, against R8's runs** (observed far cells, repeat 0, the same templates; described, not tested):

- penalty against F-0, not recoverable: +98.0 pp [+96.5, +99.5]
- penalty against F-0, recoverable: +0.0 pp [-1.5, +1.5]
- difference of the two penalties: +98.0 pp [+95.5, +100.5]
- lift over W-0, not recoverable: +2.0 pp [+0.5, +3.5]

Model strings: this cell ['claude-haiku-5-5'], R8's runs ['claude-haiku-5-5'].

**Exclusions** (per task cell, repeat 0; §13):

- observed-nonrec-near: {'keys': 200}
- observed-nonrec-far: {'keys': 200}
- observed-rec-near: {'keys': 200}
- observed-rec-far: {'keys': 200}
- derived-nonrec-near: {'keys': 200}
- derived-nonrec-far: {'keys': 200}
- derived-rec-near: {'keys': 200}
- derived-rec-far: {'keys': 200}
