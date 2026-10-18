# claude-haiku-5-5's size rule (PREREG §17.8, amendment R8): W-n-0 and T

Billed estimate from block `4-haiku`'s rows of `results/costs.csv` (sha256 `2eaf86372a46…`), by `uv run python -m analysis.haiku_forecast`. Forecasts, not measurements. Every T is in `forecast.csv`, every number in `forecast.json`.

## The rule's outcome

**W-n-0 does not run, T = 200** (step 2 of the rule: F(T = 200, with W-n-0) = 200.247190 > 148.761921; F(T = 200, without W-n-0) = 122.973950 ≤ 148.761921).

- R = $180.00 − $4.99 (block `4-haiku`'s spend, 6 rows) = $175.01; 0.85 R = $148.76.

| F | USD | ≤ 0.85 R? |
|---|---|---|
| T = 200, with W-n-0 | 200.25 | no |
| T = 200, without W-n-0 | 122.97 | yes |

Record (R8): F, R, the outcome and this script's commit go into `results/decisions.md` before any main episode, and the pull request that records them sets `HAIKU_T` = 200, and `HAIKU_CELLS` without W-n-0, which is reported as "pre-registered, not run (budget)".

## The outcome's main runs (T = 200)

| Run | Episodes, repeat 0 | Repeat 1 | USD per episode | USD |
|---|---|---|---|---|
| F-0 | 1,600 | 160 | 0.012503 | 22.01 |
| W-0 | 1,600 | 160 | 0.042535 | 74.86 |
| F-0-restated | 1,600 | 160 | 0.012503 | 22.01 |
| single-turn (prompts) | 800 | 80 | 0.004660 | 4.10 |
| **F** | | | | **122.97** |

## Cost per episode

| Line | USD per episode | Basis | Episodes in the basis | Runs |
|---|---|---|---|---|
| F-0 | 0.012503 | validity, restated | 160 | `20261018T044721Z-F-0-claude-haiku-5-5` |
| W-0 | 0.042535 | pilot | 8 | `20261018T043926Z-W-0-claude-haiku-5-5` |
| W-n-0 | 0.043905 | pilot | 8 | `20261018T044223Z-W-n-0-claude-haiku-5-5` |
| F-0-restated | 0.012503 | validity, restated | 160 | `20261018T044721Z-F-0-claude-haiku-5-5` |
| single-turn | 0.004660 | pilot | 8 | `20261018T044546Z-single-turn-claude-haiku-5-5` |

- Check of pilot template 0 (not applied): F-0's restated validity cost per episode, on 20 templates, is 1.018 times its pilot's.
- The withheld validity run: 0.013490 USD per episode. It feeds no line (its episodes lack the fact) and counts toward the block's spend.
- Input from the cache, per run: pilot F-0: 93% read, 378,678 written; pilot W-0: 42% read, 2,540,661 written; pilot W-n-0: 41% read, 2,604,042 written; pilot single-turn: 0% read, 0 written; validity F-0 restated: 93% read, 7,685,147 written; validity F-0 withheld: 93% read, 7,708,746 written.
- Cold and warm caches (module docstring): F-0's pilot, W-n-0's pilot and the restated validity run played their episodes cold, as the main runs will; W-0's pilot followed F-0's on the same episodes with F-0's system prompt, so its calls before the first eviction may have read F-0's cache, and its estimate may be a little low.

## Sensitivity (reported only: it does not change the outcome)

- Every cost per episode × 1.25: F(T = 200, with W-n-0) = 250.31, without = 153.72; on that basis the rule would give: W-n-0 does not run, T = 190 (step 3). The outcome stays the rule's, above.
- Margin: the outcome's F would still fit 0.85 R with every cost per episode up to × 1.210.
- Why × 1.25: on luna, on the same episodes, each main run's cost per episode came out 0.8% to 7.7% above its pilot basis (module docstring).

## F-0's basis (reported only: it does not change the outcome)

- The rule costs F-0 and the restated control from the restated validity run, as `results/decisions.md` (2026-10-18, item 2) has it: the forecast "from the pilots' and validity runs' costs". PREREG §17.8 says "from the pilots' `costs.csv` rows", and this script's choice was committed after both validity runs' rows were in the ledger (module docstring).
- On F-0's pilot row instead (0.012288 USD per episode, against the validity run's 0.012503): F(T = 200, with W-n-0) = 199.49, without = 122.22; on that basis the rule would give: W-n-0 does not run, T = 200 (step 2). The same as the outcome.

## Limits

- W-0 and W-n-0 rest on 8 and 8 pilot episodes, the single-turn control on 8 pilot prompts; F-0 and the restated control on 160 episodes (validity, restated).
- A transport failure's re-run (R8, Exclusions) adds episodes F does not count; a long wait inside an episode (rate limits, retries) can let its cache expire, which costs more.
- A request over 100,000 tokens is priced at 5 times the rate: the block's rows report 0 such calls. The free token count found none on main templates 0-4 (R8), and the main runs play other templates.
- Prices as the rows were priced (2026-10-17); billed equals list on Anthropic, but for refusals Anthropic does not bill.

## What it does not show

- Nothing about Haiku's success or any H1 or H3 quantity: it reads costs and episode counts only (pilot blinding, PREREG §11).
- Not a comparison of models or providers: costs are in each provider's own tokens and prices (R8).
- Not a measurement of the main runs' cost: the main runs measure that.
- Not a guarantee that the main runs stay within the block: each run still stops at its planned spend, and Claude stops and asks the researcher before block spend would pass $180.00 (R8).
