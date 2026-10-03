# sol H1 replication (PREREG §17.4, amendment R4): cost forecast

Billed estimate (Flex, cache writes at 1.25 times the input price), from block 1's measured `results/costs.csv` rows, by `uv run python -m analysis.sol_h1_forecast`. Forecasts, not measurements. Per-cell lines are in `sol_h1_forecast.csv`, the phase-1a lines in `sol_h1_phase_1a.csv`.

## R4 (sol, medium effort, default generator config, 4 observed task cells)

| Item | Episodes | Central (USD) | Low (USD) |
|---|---|---|---|
| Pilot, W-0 and W-n-0 (pilot templates 0-1) | 16 | 4.34 | 1.21 |
| Validity, F-0, restated and withheld (G1) | 160 | 10.28 | 3.53 |
| Main runs at T = 100, F-0 + W-0 + W-n-0 | 1,320 | 264.87 | 76.32 |
| Main runs at T = 50, F-0 + W-0 + W-n-0 | 660 | 132.43 | 38.16 |
| **R4 in all, T = 100** | | **279.49** | 81.06 |
| **R4 in all, T = 50** | | **147.06** | 42.90 |

Main runs per harness cell at T = 100 (central): F-0 26.17; W-0 115.55; W-n-0 123.15.

**Scenarios.**
- low: sol's F-0 pilot row (warm cache); luna's measured W/F-0 cost ratios. Forecast per episode on sol (USD): F-0 0.0221; W-0 0.0735; W-n-0 0.0779; validity 0.0221.
- central: sol's F-r pilot row (cold cache, the same episodes); luna's W/F-0 token mix priced at sol's prices; luna's validity/base factor. Forecast per episode on sol (USD): F-0 0.0595; W-0 0.2626; W-n-0 0.2799; validity 0.0643.
- Why the central basis: sol's F-0 pilot run played its 8 episodes right after the F-r run had played the same 8 with nearly the same input, so almost all of its input came from the cache (3,030 cache-write tokens against the F-r run's 252,326). A main-sweep run plays episodes no other run has just played, so each call writes its new suffix to the cache, at 1.25 times the input price; at medium effort sol hardly reasons, so the F-r run's payloads stand in for a cold F-0 run's. Window cells lose about half of their prompt caching (luna's pilot read from the cache 94% of its input in F-0, 52% in W-0 and 49% in W-n-0), and sol's cached input costs 1/20 of its input price against luna's 1/10, so luna's W/F-0 token mix is priced at sol's prices.

## Phase 1a against its $500 cap

| Line | USD |
|---|---|
| Spent in phase 1a (`results/costs.csv`, R3's engagement check included) | 3.87 |
| luna's main sweep (T = 100, 4 replay-off cells) and controls, rough | 35.52 |
| sol's H2 core and validity on `sol-chain`: not run (R3's hard stop) | 0.00 |
| R4 at T = 100, central (low) | 279.49 (81.06) |
| R4 at T = 50, central (low) | 147.06 (42.90) |
| **Total at T = 100, central (low)** | **318.87** (120.44) |
| **Total at T = 50, central (low)** | **186.44** (82.29) |

Headroom under the cap, central: 181.13 at T = 100, 313.56 at T = 50. Every main-run line scales with T, which §4.2's rule sets at M1 for luna.

Context row (rough, not R4's forecast): luna's lines use its block-1 pilot cost per episode per cell; its restated control as F-0 episodes at luna's validity/base factor; each single-turn prompt bounded by one F-0 episode. sol's H2 runs are not counted: R3's engagement check found NOT_ENGAGED on 2026-10-03, and R3's hard stop ended H2 on sol (`results/decisions.md`).

## Limits

- sol's W-0 and W-n-0 have never run: their cost is luna's measured token mix priced at sol's prices. R4's pilot measures them, and block 3's approval uses that.
- Near and far episodes are assumed to cost the same per episode: they share their skeleton (PREREG §2.7). sol's basis ran on far cells only, observed and derived.
- Small bases: sol's is one run of 8 episodes (2 pilot templates × the 4 far task cells), luna's one run of 8 per cell (1 pilot template × the 8 task cells).
- Lookups add calls in recoverable cells, more in W cells; the luna pilot's 8 episodes include 4 recoverable ones, so its ratios include some of this.
- luna's W-0 pilot ran minutes after its F-0 pilot on the same episodes, so some of its early calls may have been read from F-0's cache; its ratio may be a little low.
- Prices of 2026-09-30 (`harnesses/pricing.py`); Flex assumed served throughout.
