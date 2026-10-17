# Premise check (2026-09-30)

Before the study started, three independent AI agents checked its premise ("When does the harness matter? A state-persistence account of harness sensitivity"):
- **arc-facts:** reproduce the ARC numbers, read the harness code, cost the ARC leg, check toggles and prize eligibility.
- **prior-art:** novelty and scoop risk.
- **design-review:** hostile review of design, statistics, cost and venues.

**All three returned `go_narrowed`.** This file summarizes what each found, where they disagreed, and how `PLAN.md` responds. Facts with URLs are collected in `background.md`. Where a check conflicts with the original idea card, the check wins.

## 1. arc-facts: go, narrowed
**Bottom line.** The reported numbers are correct, and ARC's MIT harness splits into separable parts. The card's ARC leg had to be redone before spending money.

**Key findings:**
- **Numbers confirmed.**
  - Astra: Standard at max 62.71% ($26,098) vs Adapter at high 99.95% ($18,817). The headline compares different efforts; at matched effort the gap is 35.8pp (max) and 45.1pp (high).
  - Gemini 3.8 Flash at high: 10.37% vs 35.00% (+24.6pp).
- **Only Gemini 3.8 Flash is a usable cheap model.**
  - GPT-6 Luna sits at 0.03-0.59% under both harnesses (noise).
  - GPT-6 Sol shows a gap only at max, at $101-159/game.
  - DeepSeek V4.x Flash has no ARC-AGI-3 score.
  - **The card's plan to use gpt-6-luna on ARC would have measured noise.**
- **Cost was under-estimated.**
  - Gemini Flash at high costs about $80/game at ARC's list-price accounting, not the card's ~$30.
  - The card's 6 games × 4 configs × 2 seeds ≈ $2.3k.
  - Cheap large-gap games (FT09, SB26, LP85, R11L) bring a 4-config × 2-seed pass to ~$0.5-0.8k.
  - Gemini prices double on Jan 1, 2027.
- **No component is independently switchable in the code.**
  - Each needs a small patch: a notes flag, stripping reasoning before replay, or `SummaryCompactor` in `manual_rolling`.
  - Stripping Gemini thought blocks may break the API.
  - The cleanest replay toggle found is Qwen3.6/3.8's `preserve_thinking`.
- **Free data.**
  - Every Gemini-Flash public run is downloadable, with per-step tokens and reasoning summaries.
  - With replay, the model thinks about 2.6× less per turn.
  - 11 of 25 Standard-high runs ended early without a win (vs 5 of 25 for the Adapter). This confound has to be logged via exit reason.
- **Published configs are not in the repo.** Neither the Astra config nor the Gemini Standard-high config is checked in, and the API surface for Standard Gemini is unknown.
- **The ARC Paper Prize needs a linked offline Kaggle code submission.** An API-model-only analysis does not qualify. Kaggle submissions are due Nov 2 and papers Nov 8.
- **Recommendation:** Gemini-Flash-only ARC attribution plus PersistGym; aim at AGENT/TMLR rather than the Paper Prize.

## 2. prior-art: go, narrowed
**Bottom line.** Nobody has published the combination: a state-demand dial held apart from context volume, crossed with harness mechanisms. The prior-art check found no component attribution of ARC's gap anywhere it looked (ARC, forks, arXiv, blogs, LessWrong). But every single piece is covered somewhere, so PersistGym as an artifact is only modestly novel.

**Closest work:**
- **LOCA-bench:** a length dial × strategies, including thinking-block clearing.
- **2609.29875** (Sep 24): when reasoning can be forgotten; replaceable once state is externalized.
- **MiniMax-M2, 2606.00135 and the OpenAI cookbook:** replay ablations by task type.
- **Harness-Bench:** cross-harness variance is largest in state-heavy categories. This is the correlational form of our hypothesis.
- **GSM-Infinite:** the precedent for separating demand from length.
- **ConstraintRot, PM-Bench and hobby benchmarks** (labyrinthbench, compactbench, ctxbench).

**Scoop risk:**
- **High for the ARC leg.** ARC Prize adds an adapter about weekly, and its results page already shows Gemini's gap growing with effort (+9, +20, +25pp).
- **Medium for the dial leg.** Likely scoopers: the TierFlow group (2609.29875, StateComp), then the LOCA-bench group, then the Empirical-Study and HarnessTax teams.

**Recommendations:**
- Post the ARC table within about 3 weeks.
- Drop or shrink the external leaderboard-correlation leg.
- Frame the work as a causal test of Harness-Bench's observation and of 2609.29875's question, citing GSM-Infinite.
- Minor correction: the card mis-described 2605.23950. Its thesis is the "Binding Constraint Thesis"; context drift is a defined quantity. It does run a 3×3 factorial.

**Coverage caveat:** arXiv and Semantic Scholar were rate-limited (HTTP 429) for most of the session. The ARC Discord was not checked.

## 3. design-review: go, narrowed and re-aimed
**Bottom line.** Worth doing, but four design choices needed fixing.
1. **The ARC gap is half-explained already.** OpenAI's Jul 29 post names retained reasoning plus compaction (13.3% → 38.3%, GPT-5.6 Sol, public set) but gives only the combined number.
2. **d in turns is circular for truncating harnesses.** Survival should be computed, not estimated. A better moderator is recoverability × derivedness, which fits HarnessTax and 2608.16370: when state is recoverable, the harness moves cost, not success.
3. **Replay is cleanly togglable only on gpt-6.1-sol**, via `reasoning.context`. It is confounded on DeepSeek, limited to tool chains on gpt-6-luna, and opaque on Gemini.
4. **The planned samples were badly underpowered.** Simulated power was about 0.16-0.31, so kill criterion (a) would fire falsely.

**Other findings:**
- **The card's four ARC configs never isolate the loss policy.** Use a path from Standard instead (S0 → +summary → −notes → +replay = Adapter).
- **The max−min "harness spread" statistic is biased.** Under the null it rises as success falls.
- **Fixed volume does not separate state persistence from needle retrieval.** Add position-matched single-turn and restated-at-need controls; cut the volume dial (LOCA-bench covers it).
- **The fractional factorial aliases the interactions under test.** Use 7 interpretable cells.
- **The external leaderboard check is circular and has n≈10.** Replace it with a within-ARC level-depth analysis.
- **Proposed hypotheses H1-H5 with numeric predictions and kill rules.** Proposed StateCarry as the constructive phase.
- **Venues:** AGENT 2027 (Nov 13), the conditional ARC Paper Track, ICLR 2027 workshops or TMLR, and an early preprint.

## 4. Where the checks disagree, and what the plan does
| Topic | What the checks said | Resolution in PLAN.md |
|---|---|---|
| Is the ARC gap "unexplained"? | prior-art: no component attribution anywhere. design-review: OpenAI already named the two mechanisms (Jul 29). | Both hold: mechanisms named, per-component size unknown. Verified the OpenAI post exists (search results; the page returned 403 to our fetcher). Framing changed to "named but unquantified"; the ARC table is supporting evidence, not the headline. |
| Which ARC games | arc-facts: pick cheap large-gap games (FT09, SB26, LP85, R11L). design-review: choosing the largest gaps from a noisy screen gives winner's-curse bias; pick at random or screen then confirm on fresh seeds. | Pre-registered rule (PLAN §8.3): eligible = both published high runs ≤ $60 and gap ≥ 20 (6 games); draw 4 at random with a recorded seed; fresh seeds re-measure the gap; claims stated as conditional on "games where the Adapter helps". |
| ARC cost | card: $300-700. arc-facts: ~$2.3k for the card's design; ~$0.5-0.8k for 4 cheap games. design-review: $300-1,000, from a per-game estimate (~$35) scaled from Astra. | Use arc-facts' measured per-game costs: 32 runs ≈ $900 at list, ≈ $450 with Flex; hard cap $900. design-review's per-game figure is below the measured ~$80 average, but close to the eligible cheap games' average. |
| How to isolate replay on ARC | card: Adapter minus replay. arc-facts: stripping Gemini thoughts may break the API. design-review: path design. | Path design built up from `manual_rolling` (S0 → S1 → S2 → S4). S0-S2 never send thoughts (as ARC's Standard already does), so no stripping is needed. |
| Cleanest replay toggle | arc-facts: Qwen3.6/3.8 `preserve_thinking` (checked the model cards). design-review: only gpt-6.1-sol; open weights are off-distribution across user turns (checked gpt-oss harmony, not Qwen). | gpt-6.1-sol is the MVP toggle (verify the echo). Qwen3.6-27B (card: trained for historical thinking) plus gpt-oss-120b (not trained) form extension E1, which moves into the MVP if the sol toggle fails. |
| Does gpt-6-luna support `all_turns`? | arc-facts: docs don't say; a search snippet claims all GPT-6 models default to it. design-review: not listed, so probably not. | Unknown. The M0 pilot checks the echoed `reasoning.context`; if unsupported, luna runs only the replay-off cells. |
| What the effort dose-response means | prior-art: consistent with replay being the main component. design-review: predicts the loss policy gives ≥ 1/3 and replay ≤ 1/2. | Both registered as competing predictions (H4 A vs B); report which holds. |
| Paper Track dates and format | arc-facts: papers due Nov 8 (arcprize.org), code Nov 2. design-review: Nov 9 23:59 UTC (Kaggle), ≤ 1,500 words plus a public notebook, CC-BY 4.0 winner licence. | Plan for Nov 8. Check the word limit and licence on Kaggle before any go decision (not re-verified here). |
| When to decide on the Paper Track | design-review: go/no-go Oct 19. deadlines.md: entry and team-merge deadline Oct 26. | Decision P on Oct 19; if go, the researcher joins on Kaggle by Oct 26. Default: skip. |
| When to publish the ARC table | prior-art: within ~3 weeks. design-review: preprint as soon as the MVP is done. | Target Oct 28 (end of M3), right after the MVP gate on Oct 21. |

## 5. Objections and responses
| Objection | Raised by | Response in PLAN.md |
|---|---|---|
| "Needle-in-a-haystack in costume" | card reviewer, design-review | Position-matched single-turn and restated-at-need controls (H3); survival accounting separates retrieval from persistence. |
| "State demand" is circular | card reviewer, design-review | Distance defined relative to the harness threshold; S computed analytically in advance; "needed" and "live" from the generator's dependency graph only; definitions frozen in `PREREG.md`. |
| Replay benefit may be a training quirk | card reviewer, design-review | Two API models plus open weights with trained/untrained contrast (E1); message-structure variant (E2); claims stated per component and state type. |
| Cheap models may not transfer to frontier | card reviewer | Scoped as a limitation. E4 (gpt-6.1-sol on ARC) is gated on a cost pilot. No frontier-model claims. |
| Seven-part plan is three papers | card reviewer | MVP is PersistGym-lite + ARC path; volume dial, k=4, permanence games and external correlation dropped. |
| Underpowered; "CI includes 0" kill rule fires falsely | design-review | ~100 fully crossed templates on luna; 2 distance levels bracketing the threshold; re-simulate power at M1; equivalence-bound kill rules. |
| Max−min spread is biased | design-review | Replaced by pre-registered contrasts; a variance component with a permutation null if a summary is needed. |
| Fractional factorial aliases the interactions | design-review | 7 interpretable harness cells (plus an optional Adapter-analogue cell). |
| The four ARC configs don't isolate the loss policy | design-review | Path design S0 → S1 (summary) → S2 (−notes) → S4 (replay). |
| Published gap may include harness errors | arc-facts | Exit reason logged per run; pre-registered single re-run for error endings; free analysis characterises the published runs. |
| External leaderboard check is circular | design-review, prior-art | Dropped; replaced by level-depth analysis (H5). |
| PersistGym as an artifact is only modestly novel | prior-art | The contribution is the design (recoverability × derivedness, crossed templates, survival accounting) plus the StateCarry builder, not the environment alone. |
| Scoop (ARC Prize, OpenAI, TierFlow, LOCA group) | prior-art, design-review | Free analysis in week 1; preprint target Oct 28; gate G2 re-scopes if a per-component ablation appears. |
| Being read as a vendor comparison | design-review | One-off mechanism study; no rankings or dashboard; figures by task property; researcher reviews all public text. |
| Paper Prize ineligible for an API-only analysis | arc-facts, design-review | Conditional extension E5 only, with an offline open-model Kaggle submission; default skip. |

## 6. Not verified, or to re-check
- gpt-6-luna's `reasoning.context` support: the M0 pilot checks it.
- Whether Gemini Flex can be set through ARC's config `request` block: M0.
- The ARC Paper Track word limit and winner licence: read Kaggle's rules before decision P.
- AGENT 2027 deadline, Nov 13 vs Nov 27: plan for Nov 13 and re-check in November.
- What ARC's "None" effort row means for Astra, and the API surface of the published Standard Gemini runs: ask ARC or check the session configs.
- Papers posted in the last few days: arXiv was rate-limited during the prior-art check. Re-run a quick scoop search at each gate.

## 7. Addendum (2026-09-30): crowding on the ARC Kaggle track
While assessing a related idea ("native-reasoning replay and ledger compaction for an open-weight ARC-AGI-3 agent"), we found it unlikely to be novel, for three reasons:
- **The baseline already has these features.** The common Kaggle baseline agent "Duck" already enables `preserve_thinking` with prefix caching, stores each turn's reasoning, keeps a structured world/goal/action/open-questions block and runs a persistent REPL (citing `configs/inference.json`, `framework/kaggle.py:332` and `tool_agent.py:1892` in that agent's code).
- **Other teams are testing the same arms.** At least four public teams are ablating them (canivel A22, JustAdev742 exp-035 and P30/P31, leejianrong's ledger + world-model slices, Polyphony/Tufa compaction), with results due before Nov 2.
- **Leaderboard gains don't reward memory design.** Gains on that track come mostly from serving throughput.

**Consequences for this plan** (added to PLAN.md §9 Phase 2 and §15):
- StateCarry's niche is API models in ARC's Standard harness, measured against the Provider Adapter and motivated by PersistGym's mechanism results. It is not "ledger memory for ARC" in general.
- Cite Duck and the Kaggle ablations as prior art, and re-check them at G2 and G3.
- The ARC Paper Track (E5) becomes less attractive: a Kaggle entry would compete directly with these teams.

These Kaggle-team details come from an AI agent's review and were not independently re-verified. Confirm them before citing.
