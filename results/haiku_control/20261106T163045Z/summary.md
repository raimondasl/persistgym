# claude-haiku-5-5: R11's later W-n-0 control (persistgym_haiku_control)

**FINAL.** PREREG.md §17.11 (amendment R11). Exploratory: no test, no label. Repeat 0, the 2 not-recoverable far task cells, main templates 0-195 in every arm (196 of 200). Not a model comparison. §2.8's accounting check: 393 need steps replayed, 0 bugs. R11's run came after R10's arms, not alongside them.

**Templates left out of every arm:** 4, of which 3 were never played.

- template 196, derived-nonrec-far: no record: the run has no record of it

| Arm | Task cell | Success | 90% interval | Refused episodes | Stopped responses |
|---|---|---|---|---|---|
| W-n-0 (R11) | observed-nonrec-far | 10/196 (5.1%) | 2.6% to 7.7% | 7 | {'refusal:bio': 17} |
| W-n-0 (R11) | derived-nonrec-far | 6/196 (3.1%) | 1.0% to 5.1% | 20 | {'refusal:bio': 49} |
| W-n-0 (R9) | observed-nonrec-far | 4/196 (2.0%) | 0.5% to 3.6% | 5 | {'refusal:bio': 12} |
| W-n-0 (R9) | derived-nonrec-far | 9/196 (4.6%) | 2.5% to 7.2% | 18 | {'refusal:bio': 39} |
| W-np-0 | observed-nonrec-far | 174/196 (88.8%) | 85.0% to 92.3% | 30 | {'refusal:bio': 82} |
| W-np-0 | derived-nonrec-far | 169/196 (86.2%) | 82.1% to 90.3% | 42 | {'refusal:bio': 119} |
| W-npd-0 | observed-nonrec-far | 169/196 (86.2%) | 82.1% to 90.2% | 30 | {'refusal:bio': 57} |
| W-npd-0 | derived-nonrec-far | 174/196 (88.8%) | 84.9% to 92.4% | 36 | {'refusal:bio': 108} |

**§2.8 accounting** (P(carried) is a lower bound):

| Arm | Task cell | S verbatim 0 | P(carried) | Used given carried | Not carried: success, no lookup | Not carried: success, lookup |
|---|---|---|---|---|---|---|
| W-n-0 (R11) | observed-nonrec-far | 196 | 18/196 (9.2%) | 10/18 (55.6%) | 0/178 (0.0%) | n/a |
| W-n-0 (R11) | derived-nonrec-far | 196 | 73/196 (37.2%) | 6/73 (8.2%) | 0/123 (0.0%) | n/a |
| W-n-0 (R9) | observed-nonrec-far | 196 | 8/196 (4.1%) | 4/8 (50.0%) | 0/188 (0.0%) | n/a |
| W-n-0 (R9) | derived-nonrec-far | 196 | 70/196 (35.7%) | 9/70 (12.9%) | 0/126 (0.0%) | n/a |
| W-np-0 | observed-nonrec-far | 196 | 183/196 (93.4%) | 174/183 (95.1%) | 0/13 (0.0%) | n/a |
| W-np-0 | derived-nonrec-far | 196 | 178/196 (90.8%) | 169/178 (94.9%) | 0/18 (0.0%) | n/a |
| W-npd-0 | observed-nonrec-far | 196 | 174/196 (88.8%) | 169/174 (97.1%) | 0/22 (0.0%) | n/a |
| W-npd-0 | derived-nonrec-far | 196 | 188/196 (95.9%) | 174/188 (92.6%) | 0/8 (0.0%) | n/a |

**Choices with the fact evicted:**

- W-n-0 (R11), observed-nonrec-far: chose an option in 10 of 196, 10 correct.
- W-n-0 (R11), derived-nonrec-far: chose an option in 6 of 196, 6 correct.
- W-n-0 (R9), observed-nonrec-far: chose an option in 4 of 196, 4 correct.
- W-n-0 (R9), derived-nonrec-far: chose an option in 9 of 196, 9 correct.
- W-np-0, observed-nonrec-far: chose an option in 174 of 196, 174 correct.
- W-np-0, derived-nonrec-far: chose an option in 169 of 196, 169 correct.
- W-npd-0, observed-nonrec-far: chose an option in 169 of 196, 169 correct.
- W-npd-0, derived-nonrec-far: chose an option in 174 of 196, 174 correct.

**Contrasts** (percentage points, 90% interval over the same template resamples; described, not tested):

- W-n-0 (R11) - W-n-0 (R9), observed-nonrec-far: +3.1 pp [+0.0, +6.2]
- W-n-0 (R11) - W-n-0 (R9), derived-nonrec-far: -1.5 pp [-4.1, +1.0]
- W-np-0 - W-n-0 (R11), observed-nonrec-far: +83.7 pp [+78.5, +88.4]
- W-np-0 - W-n-0 (R11), derived-nonrec-far: +83.2 pp [+78.3, +87.8]
- W-npd-0 - W-n-0 (R11), observed-nonrec-far: +81.1 pp [+76.3, +85.9]
- W-npd-0 - W-n-0 (R11), derived-nonrec-far: +85.7 pp [+81.0, +89.9]

**Replies** (R9's text patterns, which undercount on W-n-0's replies; pointers, not a coding):

| Arm | Cell, notes carried the fact | Episodes | Correct | Failed | Failed: declined | Failed: need reply disowns its figure | Failed: retracted before the need step |
|---|---|---|---|---|---|---|---|
| W-n-0 (R11) | observed-nonrec-far carried=True | 18 | 10 | 8 | 8 | 3 | 0 |
| W-n-0 (R11) | observed-nonrec-far carried=False | 178 | 0 | 178 | 178 | 2 | 0 |
| W-n-0 (R11) | derived-nonrec-far carried=True | 73 | 6 | 67 | 67 | 45 | 52 |
| W-n-0 (R11) | derived-nonrec-far carried=False | 123 | 0 | 123 | 123 | 4 | 4 |
| W-n-0 (R9) | observed-nonrec-far carried=True | 8 | 4 | 4 | 4 | 2 | 0 |
| W-n-0 (R9) | observed-nonrec-far carried=False | 188 | 0 | 188 | 188 | 1 | 0 |
| W-n-0 (R9) | derived-nonrec-far carried=True | 70 | 9 | 61 | 61 | 39 | 43 |
| W-n-0 (R9) | derived-nonrec-far carried=False | 126 | 0 | 126 | 126 | 0 | 0 |

**Responses:**

| Arm | Refused responses | By turn (0-4, 5-9, 10-14, 15 on) | With a thinking block | By turn (first requests; 0-4, 5-9, 10-14, 15 on) | Need step's first request |
|---|---|---|---|---|---|
| W-n-0 (R11) | 66/9416 (0.7%) | 6, 20, 8, 32 | 5144/9416 (54.6%) | 1700/1960 (86.7%), 1178/1960 (60.1%), 654/1960 (33.4%), 1612/3536 (45.6%) | 392/392 (100.0%) |
| W-n-0 (R9) | 51/9416 (0.5%) | 6, 15, 6, 24 | 4866/9416 (51.7%) | 1667/1960 (85.1%), 1078/1960 (55.0%), 610/1960 (31.1%), 1511/3536 (42.7%) | 392/392 (100.0%) |
| W-np-0 | 201/9416 (2.1%) | 8, 28, 32, 133 | 9028/9416 (95.9%) | 1934/1960 (98.7%), 1858/1960 (94.8%), 1798/1960 (91.7%), 3438/3536 (97.2%) | 392/392 (100.0%) |
| W-npd-0 | 165/9416 (1.8%) | 11, 17, 22, 115 | 8950/9416 (95.1%) | 1926/1960 (98.3%), 1848/1960 (94.3%), 1754/1960 (89.5%), 3422/3536 (96.8%) | 392/392 (100.0%) |

**The notes** (from the last evidence step to the step before the need step: replies holding the fact's value; at the need step: replies retained, and their median length in characters):

- W-n-0 (R11), observed-nonrec-far: 236/3120 (7.6%); 14.0 replies, 1400.0 characters.
- W-n-0 (R11), derived-nonrec-far: 284/3096 (9.2%); 14.0 replies, 1723.0 characters.
- W-n-0 (R9), observed-nonrec-far: 170/3125 (5.4%); 14.0 replies, 1299.5 characters.
- W-n-0 (R9), derived-nonrec-far: 344/3101 (11.1%); 14.0 replies, 1670.0 characters.
- W-np-0, observed-nonrec-far: 2550/3072 (83.0%); 11.0 replies, 14248.0 characters.
- W-np-0, derived-nonrec-far: 2439/3033 (80.4%); 11.0 replies, 13876.0 characters.
- W-npd-0, observed-nonrec-far: 2631/3096 (85.0%); 12.0 replies, 12204.5 characters.
- W-npd-0, derived-nonrec-far: 2692/3050 (88.3%); 11.0 replies, 12803.5 characters.

**The leak check** (the fact's value in the need step's first request: in the system prompt, in earlier user messages, in its option line, elsewhere in the need observation; clue values outside the replies):

- W-n-0 (R11), observed-nonrec-far: {'target_in_system': 0, 'target_in_earlier_user': 0, 'target_in_need_option_line': 196, 'target_in_need_elsewhere': 0, 'clue_outside_replies': 0}
- W-n-0 (R11), derived-nonrec-far: {'target_in_system': 0, 'target_in_earlier_user': 0, 'target_in_need_option_line': 196, 'target_in_need_elsewhere': 0, 'clue_outside_replies': 0}
- W-n-0 (R9), observed-nonrec-far: {'target_in_system': 0, 'target_in_earlier_user': 0, 'target_in_need_option_line': 196, 'target_in_need_elsewhere': 0, 'clue_outside_replies': 0}
- W-n-0 (R9), derived-nonrec-far: {'target_in_system': 0, 'target_in_earlier_user': 0, 'target_in_need_option_line': 196, 'target_in_need_elsewhere': 0, 'clue_outside_replies': 0}
- W-np-0, observed-nonrec-far: {'target_in_system': 0, 'target_in_earlier_user': 0, 'target_in_need_option_line': 196, 'target_in_need_elsewhere': 0, 'clue_outside_replies': 0}
- W-np-0, derived-nonrec-far: {'target_in_system': 0, 'target_in_earlier_user': 0, 'target_in_need_option_line': 196, 'target_in_need_elsewhere': 0, 'clue_outside_replies': 0}
- W-npd-0, observed-nonrec-far: {'target_in_system': 0, 'target_in_earlier_user': 0, 'target_in_need_option_line': 196, 'target_in_need_elsewhere': 0, 'clue_outside_replies': 0}
- W-npd-0, derived-nonrec-far: {'target_in_system': 0, 'target_in_earlier_user': 0, 'target_in_need_option_line': 196, 'target_in_need_elsewhere': 0, 'clue_outside_replies': 0}

User messages at a common episode and step, against R9's: W-n-0 (R11) 9416 of 9416 identical; W-np-0 9416 of 9416 identical; W-npd-0 9416 of 9416 identical.

**Cost per episode** (billed estimate, USD; output tokens):

| Arm | Task cell | Episodes | Cost per episode | Output tokens per episode |
|---|---|---|---|---|
| W-n-0 (R11) | observed-nonrec-far | 196 | 0.04350 | 2258 |
| W-n-0 (R11) | derived-nonrec-far | 196 | 0.04371 | 2972 |
| W-n-0 (R9) | observed-nonrec-far | 196 | 0.04317 | 2140 |
| W-n-0 (R9) | derived-nonrec-far | 196 | 0.04361 | 2858 |
| W-np-0 | observed-nonrec-far | 196 | 0.05455 | 13384 |
| W-np-0 | derived-nonrec-far | 196 | 0.05443 | 13570 |
| W-npd-0 | observed-nonrec-far | 196 | 0.05293 | 11744 |
| W-npd-0 | derived-nonrec-far | 196 | 0.05386 | 12933 |

**Run conditions:**

| Arm | Run | Ending | Started | Finished | Parallel | Uncached input tokens a minute | Model strings | Geos |
|---|---|---|---|---|---|---|---|---|
| W-n-0 (R11) | 20261106T050520Z-W-n-0-claude-haiku-5-5 | SPEND_RESERVATION | 2026-11-06T05:05:21+00:00 | 2026-11-06T06:35:14+00:00 | 2 | 1,400,342 | claude-haiku-5-5 | {'global': 9440} |
| W-n-0 (R9) | 20261024T060051Z-W-n-0-claude-haiku-5-5 | COMPLETED | 2026-10-24T06:00:52+00:00 | 2026-10-24T07:31:11+00:00 | 8 | 5,811,409 | claude-haiku-5-5 | {'global': 38857} |
| W-np-0 | 20261101T184553Z-W-np-0-claude-haiku-5-5 | ABORTED_API_ERRORS | 2026-11-01T18:45:55+00:00 | 2026-11-01T18:50:02+00:00 | 8 | 2,024,786 | claude-haiku-5-5 | {'global': 618} |
| W-np-0 | 20261101T190445Z-W-np-0-claude-haiku-5-5 | COMPLETED | 2026-11-01T19:04:46+00:00 | 2026-11-01T23:22:57+00:00 | 3 | 1,127,857 | claude-haiku-5-5 | {'global': 18940} |
| W-npd-0 | 20261102T002751Z-W-npd-0-claude-haiku-5-5 | COMPLETED | 2026-11-02T00:27:52+00:00 | 2026-11-02T04:55:34+00:00 | 3 | 1,096,488 | claude-haiku-5-5 | {'global': 19300} |

**Organization** (`harnesses org-check`):

- 2026-11-06T05:04:35+00:00: the one R10's error names: True; the one R8's errors name: False.
- 2026-11-06T16:30:11+00:00: the one R10's error names: True; the one R8's errors name: False.

**Exclusions** (the control, per task cell, repeat 0; §13):

- W-n-0, observed-nonrec-far: {'keys': 197, 'never_played': 3}
- W-n-0, derived-nonrec-far: {'keys': 196, 'never_played': 4}
