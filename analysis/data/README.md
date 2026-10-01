# analysis/data: committed inputs for the cost model

All files were transcribed on 2026-09-30. No API was called and nothing here was downloaded. Most rows come from documents in this repo; the exceptions are the `parameters.csv` rows whose source is "2026-09-30 low-spend review" and the review rows of `plan_a1_reference.csv`, which come from that review's verdict file, a scratch file outside the repo that cannot be re-checked from here.

| File | What it holds | Source |
|---|---|---|
| `arc_gemini38flash_high_public.csv` | The published Gemini 3.8 Flash high-effort runs on the 25 public ARC-AGI-3 games: per-game RHAE score, gap, cost (ARC's no-cache list accounting), actions and human-baseline actions, one Standard and one Provider Adapter run per game. | `docs/background.md` §4, which aggregates the free arcprize.org session and recording endpoints (pulled by the premise check on 2026-09-30; results page: https://arcprize.org/results/google-gemini-3-8-flash). |
| `prices.csv` | Token prices in USD per million tokens. | PLAN.md §12 and `docs/background.md` §6, checked 2026-09-29/30 at https://ai.google.dev/gemini-api/docs/pricing and https://developers.openai.com/api/docs/pricing. Gemini 3.8 Flash prices double on 2027-01-01 (that row is kept for reference and is not used). |
| `parameters.csv` | Every other number the cost model uses, one row each, with its source: discounts and the OpenAI cache-write multiplier, ARC token profiles, the ARC and PersistGym designs, pilot sizes, phase caps and GPU prices. Rows marked `assumption` are this model's own choices; change them here, never in code. | PLAN.md §5, §7-§9, §12 and amendment A1 §16 (branch `m0/plan-amendment-a1`); `docs/background.md` §4 and §6; CLAUDE.md; a few pilot sizes from the 2026-09-30 low-spend review (marked as such). |
| `plan_a1_reference.csv` | The budget numbers stated in PLAN.md §12/§16 and in the 2026-09-30 low-spend review. **Used only for the comparison table**; no computation reads it. | PLAN.md §16 (amendment A1) and the review's verdict file (a scratch file outside the repo; the numbers are transcribed here so the comparison is reproducible). |

Notes:
- "Flex" is 50% off every token class on both providers (PLAN §12). Whether Gemini Flex also halves the cached-token price is unverified (A1 step 1c).
- OpenAI cache writes cost 1.25x the uncached input price on GPT-5.6 and later (https://developers.openai.com/api/docs/guides/prompt-caching, checked 2026-09-30 per PLAN §16.1); the model applies it to every uncached input token.
- The ARC "cache-billed" cases apply one factor per harness, computed from the published per-game token totals and cached shares (17% Standard, 53% Adapter), to every game.
- Published run costs include runs that ended early (11 of 25 Standard-high runs; `docs/background.md` §4), so per-game costs may understate the cost of complete runs (PLAN §16.4, LP85 example). The model does not correct for this.
