# G1 gate metrics (PREREG §4.4, §10.2)

Computed 2026-10-18T05:05:34+00:00 at commit 843dd83 (dirty: False) by `uv run python -m analysis.g1 --model claude-haiku-5-5`. Model claude-haiku-5-5, generator config `3d6bc648…` (default).
This is the model's own G1 under PREREG §17.8 (amendment R8): the same thresholds, audits and spot-check package as luna's G1.


## LLM validity rates (F-0, validity templates 0-19 × 8 task cells)

- restated (`20261018T044721Z-F-0-claude-haiku-5-5`): **160/160 = 100.0%** (gate ≥ 85%): **met**; 0 excluded; endings DONE.
- withheld (`20261018T045130Z-F-0-claude-haiku-5-5`): **0/160 = 0.0%** (gate ≤ 20%): **met**; 0 excluded; endings DONE.

| Task cell | restated | withheld |
|---|---|---|
| derived-nonrec-far | 20/20 | 0/20 |
| derived-nonrec-near | 20/20 | 0/20 |
| derived-rec-far | 20/20 | 0/20 |
| derived-rec-near | 20/20 | 0/20 |
| observed-nonrec-far | 20/20 | 0/20 |
| observed-nonrec-near | 20/20 | 0/20 |
| observed-rec-far | 20/20 | 0/20 |
| observed-rec-near | 20/20 | 0/20 |

Per-cell rates are reported, not gated (D39).

## Oracle and $0 audits (`persistgym audit`, default preset)

- validity templates 0-19 (480 episodes): **pass**; failed checks: none; key and text oracles on base and restated all 1.00; highest no-memory baseline 0.100 (gate ≤ 0.20); partial memory pass (`audit_validity.json`).
- main templates 0-999 (24,000 episodes): **pass**; failed checks: none; key and text oracles on base and restated all 1.00; highest no-memory baseline 0.100 (gate ≤ 0.20); partial memory pass (`audit_main.json`).

## Researcher spot-check (`results/spotcheck/g1-validity-0-20-3d6bc648/findings.csv`)

| Task cell | no shortcut | possible | shortcut | unreviewed |
|---|---|---|---|---|
| observed-nonrec-near | 20 | 0 | 0 | 0 |
| observed-nonrec-far | 20 | 0 | 0 | 0 |
| observed-rec-near | 20 | 0 | 0 | 0 |
| observed-rec-far | 20 | 0 | 0 | 0 |
| derived-nonrec-near | 20 | 0 | 0 | 0 |
| derived-nonrec-far | 20 | 0 | 0 | 0 |
| derived-rec-near | 20 | 0 | 0 | 0 |
| derived-rec-far | 20 | 0 | 0 | 0 |
| all | 160 | 0 | 0 | 0 |

Complete: True. Flagged episodes: 0.

## Spend to date (billed estimate; list where a row has none)

- phase 0 $20.57, phase 1a $96.88, phase 1b $507.96, phase 2 $0.00; all $625.41.

## Reading

- LLM rule: **met**. Audits and oracle: **pass**. Spot-check: 160 no shortcut, 0 possible, 0 shortcut, 0 unreviewed.
- PREREG sets no numeric rule for the spot-check; under R6 change 7 there is no redesign pass. **The researcher makes the go/no-go call.**
