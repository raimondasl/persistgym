# G1 gate metrics (PREREG §4.4, §10.2)

Computed 2026-10-10T00:16:58+00:00 at commit aeb6d7c (dirty: False) by `uv run python -m analysis.g1`. Model gpt-6-luna, generator config `3d6bc648…` (default).

## LLM validity rates (F-0, validity templates 0-19 × 8 task cells)

- restated (`20261002T084243Z-F-0-gpt-6-luna`): **160/160 = 100.0%** (gate ≥ 85%): **met**; 0 excluded; endings DONE.
- withheld (`20261002T095135Z-F-0-gpt-6-luna`): **19/160 = 11.9%** (gate ≤ 20%): **met**; 0 excluded; endings DONE.

| Task cell | restated | withheld |
|---|---|---|
| derived-nonrec-far | 20/20 | 6/20 |
| derived-nonrec-near | 20/20 | 1/20 |
| derived-rec-far | 20/20 | 2/20 |
| derived-rec-near | 20/20 | 3/20 |
| observed-nonrec-far | 20/20 | 2/20 |
| observed-nonrec-near | 20/20 | 2/20 |
| observed-rec-far | 20/20 | 3/20 |
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

## Reported only: gpt-6.1-sol on the default config (R4; main runs dropped by R6)

- restated: 80/80 = 100.0% (`20261006T182920Z-F-0-gpt-6.1-sol`)
- withheld: 9/80 = 11.2% (`20261006T200237Z-F-0-gpt-6.1-sol`)

## Spend to date (billed estimate; list where a row has none)

- phase 0 $20.57, phase 1a $18.15, phase 1b $290.22, phase 2 $0.00; all $328.94.

## Reading

- LLM rule: **met**. Audits and oracle: **pass**. Spot-check: 160 no shortcut, 0 possible, 0 shortcut, 0 unreviewed.
- PREREG sets no numeric rule for the spot-check; under R6 change 7 there is no redesign pass. **The researcher makes the go/no-go call.**
