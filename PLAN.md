# PLAN: when does the harness matter?

_Written 2026-09-30 as the hand-off from the `ai-research` scouting repo (idea I-20260929-06). Sources for every outside fact are in `docs/background.md`; the premise checks behind the changes are in `docs/premise-check.md`._

## 1. Summary
ARC-AGI-3 scores move by 25-45 points between ARC Prize's Standard harness and its Provider Adapter ([GPT-6 Astra](https://arcprize.org/results/openai-gpt-6-astra), [Gemini 3.8 Flash](https://arcprize.org/results/google-gemini-3-8-flash)). Coding-agent success moves by only a few points across harnesses ([HarnessTax](https://arena.ai/blog/coding-agents-harness-tax)). We test whether this is because ARC needs **derived, non-recoverable** state that the Standard harness throws away, while coding state can usually be re-read from disk. The plan has three parts:
- **Measure it** in a small generated environment (PersistGym-lite).
- **Attribute** ARC's gap on Gemini 3.8 Flash to its components: loss policy, notes instruction, reasoning replay.
- **Build** a provider-neutral state component (StateCarry) that should recover most of the Adapter's advantage inside the Standard harness.

The minimal version runs Oct 1-21. The builder phase runs Oct 22-Nov 4. The first paper target is AGENT 2027 (Nov 13 AoE).

## 2. Research question
With the model fixed, when does the harness change task **success** rather than only **cost**?

Working hypothesis: harness effects on success are large when the state needed later
- (a) is **derived**, i.e. computed from several observations rather than read from one, and
- (b) is **not recoverable**, i.e. it cannot be re-observed from the environment, and
- (c) is **evicted** by the harness's loss policy (window truncation or summarization).

When the state can be re-queried, harness differences should turn into extra lookups and tokens instead.

Sub-questions:
1. Which harness component carries which kind of state?
   - A loss policy that summarizes instead of truncating.
   - The "carry context forward" notes instruction.
   - Replay of the model's own reasoning from earlier turns.
2. How much of ARC's Standard-to-Adapter gap does each component account for?
3. Can a visible, provider-neutral mechanism stand in for opaque reasoning replay?

### What changed from the idea card
Details and sources are in `docs/premise-check.md`.

**Dropped from the card:**
- The d ∈ {1..24} × k ∈ {1,4} × volume grid. Measuring distance in turns is circular for truncating harnesses, the volume × strategy axis is largely covered by [LOCA-bench](https://arxiv.org/abs/2602.07962), and the sample sizes were underpowered.
- The "harness spread (max−min) vs d" headline statistic. It is biased: under the null it grows as success falls.
- The external leaderboard-correlation check. It is circular and has about n=10 points.
- DeepSeek as a replay-toggle model. Its replay is tied to tool mode.
- The ARC "Adapter minus replay" arm. Stripping Gemini thoughts may be rejected by the API.

**Added:**
- Recoverability × derivedness as the main moderator.
- An analytic survival calculator.
- Position-matched and restated-at-need controls.
- Equivalence-bound kill rules.
- An ARC *path* design that builds up from the Standard harness.
- A $0 observational analysis of ARC's published runs.
- The StateCarry builder phase.

**Reframed:** OpenAI already *named* the two mechanisms behind the ARC gap: retained reasoning, and compaction instead of rolling truncation ([OpenAI, Jul 29 2026](https://openai.com/index/how-two-settings-tripled-our-arc-agi-3-scores/)). It reported only their combined effect (13.3% to 38.3% for GPT-5.6 Sol on the public set). Our ARC contribution is therefore per-component numbers with seeds, the role of the notes instruction, a non-OpenAI replication, and a provider-neutral fix. It is not "explaining an unexplained gap".

## 3. Deliverables
- **PersistGym-lite:** generator, programmatic oracle, survival calculator, harness cells, and run data. MIT license, GitHub, plus an HF dataset.
- **ARC path table:** Gemini 3.8 Flash, 4 public games, 4 configs, 2 seeds, plus a per-level analysis. Published as an early arXiv preprint and blog post (priority).
- **StateCarry:** an opt-in state mode for ARC's Standard harness, evaluated on held-out public games. Offered upstream to `arcprize/arc-agi-3-benchmarking` if the researcher agrees.
- **Paper:** AGENT 2027 (Nov 13). A fuller version goes to TMLR or an ICLR 2027 workshop.

## 4. Pre-registered hypotheses
These are drafts. At M0 (Oct 7), copy them into `PREREG.md` with exact definitions and commit before any paid run. After that, change `PREREG.md` only through a dated amendment that says why.

Definitions to fix in `PREREG.md` (these need the researcher's judgment):
- **Observed fact:** a value shown verbatim in one observation.
- **Derived fact:** a value computed from 2-3 observations shown at different steps. It is never shown in final form.
- **Recoverable:** a `lookup` action re-shows the fact (or its clues) at the cost of one step.
- **Needed:** the step at which the fact determines the only correct action. "Needed" and "live" come from the generator's dependency graph, never from agent trajectories.
- **Survives (S):** whether the fact (or all its clues) is still in the context the harness sends at the need step. Computed from token positions for window harnesses. Measured by string match for summary and notes, since those depend on what the model writes.
- **Near / far:** the reveal lies inside / beyond the harness eviction threshold W, in tokens.

Kill and equivalence rules below use 90% CIs from a template-level cluster bootstrap on the probability scale.

### H1: recoverability turns a success penalty into a cost penalty
Model: gpt-6-luna (primary). Replication on gpt-6.1-sol if the budget allows (adds cells W-0 and W-n-0 on sol, about 640 episodes).

Comparison: an observed fact at far distance, window harness **without** notes (W-0, so S=0 by construction), vs full history (F-0). W-n-0 is reported alongside it as the notes-rescue condition.

**Predictions:**
- If the fact is **not recoverable**, success drops by at least 25pp.
- If it is **recoverable**, success stays within 5pp, but lookups and total tokens rise by at least 30%.

**Falsified or kill** if the difference between the two penalties is below 10pp, with the 90% CI upper bound below 15pp. In that case drop the "success vs cost" framing.

### H2: reasoning replay carries derived state
Model: gpt-6.1-sol, plus gpt-6-luna if the M0 pilot shows it honours `all_turns`. Arms: full history, `reasoning.context` = `all_turns` (F-r) vs `current_turn` (F-0).

**Predictions:**
- Less than 3pp difference on observed facts.
- On derived facts at far distance: at least 8pp more success with replay, or, if success does not move, at least 25% more reasoning tokens in the no-replay arm (the model re-derives what it no longer sees).

**Falsified** if the derived-fact success effect is under 3pp *and* the token effect is under 10%. **Equivalence** (treated as "no effect"): the 90% CI of the success effect lies inside ±8pp *and* the token effect is under 10%.

### H3: little residual cost of multi-turn structure when the fact survives
Comparison: at S=1, far distance, multi-turn full history vs the position-matched single-turn control. The control has the same tokens and the fact at the same offset, but in one prompt.

**Prediction:** the difference is at most 5pp. We report it either way. It bounds how much of any effect is "needle-in-a-haystack" retrieval rather than state persistence.

### H4: ARC path decomposition (Gemini 3.8 Flash, high thinking)
Path: S0 → S1 → S2 → S4, defined in §8.2.

**Prediction A (design review):**
- Swapping drop-oldest for summary compaction (S0→S1) accounts for at least 1/3 of the S0→S4 gap.
- The replay step (S2→S4) accounts for at most 1/2.
- Removing the notes instruction (S1→S2) accounts for little or nothing, i.e. within ±10% of the gap.

**Prediction B (competing; prior-art check):** the replay step accounts for at least 1/2. This reading comes from the published gap growing with reasoning effort (+9, +20, +25pp at low, medium, high).

We register both and report which one the data supports. With 4 games × 2 seeds this is **descriptive**. Shares get bootstrap intervals over game-seed units, and we make no significance claims.

**Kill the ARC leg** if the measured S0→S4 gap, averaged over the 4 games, is below 10 RHAE points.

### H5: the Adapter advantage grows with level depth
The Adapter's advantage in P(clear level ℓ | reached ℓ) is larger at levels ≥4 than at levels 1-2.
- Tested first on ARC's published public-set runs (free; §8.1).
- Then on our runs.

## 5. PersistGym-lite: task generator
**One environment family.** Each episode is a sequence of about 20-32 steps.
- Every environment step is a **new user message** containing an observation, as in ARC's harness, and the agent replies with one action. This structure matters: with OpenAI's `current_turn`, reasoning inside one user turn is kept anyway, so the replay toggle only bites across user turns.
- A tool-call-chain variant is extension E2.

**Step types:**
- **Routine:** the correct action depends only on the current observation. These keep the agent engaged and give a baseline competence check.
- **Reveal:**
  - Observed: shows the target fact.
  - Derived: shows one of 2-3 clues plus, at some step, the combining rule.
- **Need:** asks for an action whose parameter is the target fact, chosen from K options (plan K=10, so chance = 10%).
- **Lookup (recoverable variant only):** `lookup(key)` re-shows the fact, or the clues for derived facts, in the next observation. It costs one step.

**Volume control:** every observation is padded to a fixed token budget v with realistic, irrelevant log text. Distance in tokens is then fixed by distance in steps. Use one tokenizer for generation and window accounting, and also log provider-reported tokens.

**Task cells (2 × 2 × 2 = 8):** {observed, derived} × {recoverable, not} × {near, far}, with k=1 (one target per episode). Start with W ≈ 24k tokens and v ≈ 1.5k, then tune in M1 so that contexts stay ≤ 64k:
- near = reveal about 4 steps before need;
- far = reveal beyond W.

**Templates.** A template is one sampled skeleton: surface story, fact values, filler. Each template is rendered into **all 8 task cells and all harness cells** (fully crossed). All contrasts are therefore within-template, and template fixed effects absorb difficulty. Add templates rather than seeds: run 1 repeat per template × cell, and 2 repeats on a 10% subset to estimate within-template noise.

**Controls, on the same templates:**
- **Position-matched single-turn:** the same token sequence flattened into one prompt, with the fact at the same offset. Used for H3.
- **Restated-at-need:** the fact is repeated in the need-step observation. This is the ceiling with memory taken out of the problem.

**Validity gate (G1), per model:**
- The programmatic oracle, which knows the fact, scores 100%. This is a generator sanity check.
- The LLM on restated-at-need scores ≥ 85% (enough headroom).
- The LLM with the fact withheld scores ≤ chance + 10pp = 20%, so the fact is actually needed.
- The researcher spot-checks 20 episodes per cell for shortcuts, e.g. the fact being inferable from filler.

**Survival calculator.** For every harness × task cell, it computes S from token positions *before* running:
- For window harnesses, S is mechanical, so the window effect at S=0 is not itself a finding.
- The estimands are the non-mechanical parts:
  - the rescue rate P(success | S=0), via notes, lookup or re-derivation;
  - the residual at S=1;
  - the value of replay for derived state.
- For summary and notes cells, log whether the fact or clues appear in the summary or retained notes. This gives an accounting of P(carried), P(used | carried) and P(rescued | not carried).

## 6. Harness cells (PersistGym)
| Cell | History / loss policy | Notes instruction | Reasoning replay | Role |
|---|---|---|---|---|
| F-r | full history | off | on | ceiling |
| F-0 | full history | off | off | H1/H3 comparator |
| W-n-r | token window W, drop oldest | on | on | |
| W-n-0 | token window W, drop oldest | on | off | ≈ ARC Standard |
| Σ-n-r | summary at W (generic summary prompt modelled on ARC's `SUMMARY_REQUEST_PROMPT`, same model) | on | on | |
| Σ-n-0 | summary at W | on | off | |
| W-0 | token window W | off | off | isolates notes |
| Σ-0-r (optional) | summary at W | off | on | ≈ ARC Adapter |

- **Notes instruction:** ARC's sentence, verbatim: "Include any context you want to carry forward in your reply, along with the action you want to take."
- **Summary cells:** the summary replaces older turns with one user-role bridge message, as ARC does for Gemini.
- **Payload snapshot tests:** every cell must have one that asserts exactly which turns, reasoning items and instructions are sent at each step. This is the single most important correctness check. No paid run happens until they pass.
- **Observation masking** is not included. It is already covered for coding in [2609.20804](https://arxiv.org/abs/2609.20804), so it waits for later.
- **StateCarry** is added as one more cell in phase 2 (§9).

## 7. Models and how replay is toggled
| Model | Used for | Replay toggle | Status / check in pilot |
|---|---|---|---|
| gpt-6-luna (OpenAI Responses, Flex) | High-N runs: H1, H3, validity; ~100 templates per cell | `reasoning.context`, *if* supported | Docs don't list luna for `all_turns`; one search snippet says all GPT-6 models default to it. **Pilot checks the echoed `reasoning.context`.** If `all_turns` isn't honoured, run only the replay-off cells (F-0, W-n-0, Σ-n-0, W-0) on luna. |
| gpt-6.1-sol (OpenAI Responses, Flex) | H2 replay toggle; optional H1 replication; ~40 templates per cell | `reasoning.context` = `all_turns` vs `current_turn`, with encrypted reasoning items sent (`store:false`, `include: reasoning.encrypted_content`). The payload stays identical and only rendering changes. | Docs: "GPT-6.1 Sol also supports `all_turns`", and the response echoes the effective mode. **Check the echo on every response**; log and drop mismatches. Core: F-r vs F-0 on all 8 task cells. The W/Σ replay pairs run only if H2 shows signal. |
| Gemini 3.8 Flash (Interactions API) | ARC path study only | Built up from the Standard harness (no stripping) | Google's docs say thought blocks must be resent within continuous conversation. S0-S2 never send thoughts, which is what ARC's Standard harness already does. **Pilot confirms manual_rolling on Interactions at high thinking.** |
| Qwen3.6-27B, self-hosted vLLM (extension E1) | Open-weights replay | `chat_template_kwargs: {preserve_thinking: true/false}` (off by default) | The model card says it was "additionally trained to preserve and leverage thinking traces from historical messages". This is the cleanest replay toggle with a visible template. It is also the model we would port if the Kaggle route is chosen. |
| gpt-oss-120b (extension E1) | "Not trained for cross-turn CoT" contrast | Render the harmony template ourselves, with or without earlier CoT | Harmony guidance drops earlier CoT after a final message, so cross-turn replay is off-distribution. |
| DeepSeek V4.1 Flash | **Not used for replay** | none clean | Without tools, `reasoning_content` is ignored. With tools it must be passed back, or the API returns 400. Replay is therefore confounded with the message format. |

Sources: [OpenAI reasoning guide](https://developers.openai.com/api/docs/guides/reasoning), [Gemini thinking docs](https://ai.google.dev/gemini-api/docs/thinking), [Qwen3.6-27B card](https://huggingface.co/Qwen/Qwen3.6-27B), [Qwen3.8-27B card](https://huggingface.co/Qwen/Qwen3.8-27B) (there `preserve_thinking` is on by default), [harmony guide](https://developers.openai.com/cookbook/articles/openai-harmony), [DeepSeek thinking mode](https://api-docs.deepseek.com/guides/thinking_mode).

**Model pinning.** Use dated snapshot IDs where the provider offers them. Always record the `model` string returned in each response, plus the SDK version.

## 8. ARC attribution study
We use ARC's own MIT harness ([arcprize/arc-agi-3-benchmarking](https://github.com/arcprize/arc-agi-3-benchmarking)), forked and pinned at commit `4ca00e6` (2026-09-21, the HEAD of `main` on 2026-09-30). Pull later upstream changes only on purpose, and record them. How the two harnesses differ in code is in `docs/background.md` §2.

### 8.1 Free observational analysis (M0, $0)
arcprize.org serves every public-set run shown on its results pages from unauthenticated endpoints:
- `GET https://arcprize.org/api/sessions/{guid}`: config tag, per-level actions, human-baseline actions.
- `GET https://arcprize.org/api/recordings/{game_id}/{guid}`: NDJSON per step, with visible output, reasoning summary (Adapter only), token usage and cost.

**Pull** all Gemini 3.8 Flash runs: 6 variants × 25 games. Also pull any other model that has both harnesses on the public set; check GPT-6 Astra and GPT-6 Sol. Throttle requests and cache the raw files under `results/raw/`.

**Compute:**
- per-level P(clear | reached) by harness and effort (H5, first pass);
- input, reasoning and visible tokens per action;
- compaction frequency;
- how runs ended, including the exit reason if it is exposed. In the premise check's pull of these endpoints, 11 of 25 Standard-high runs ended before their action budget without a win, vs 5 of 25 on the Adapter. This confound has to be characterised.

The premise check's scripts lived in a temporary folder and are **not** in this repo. Rewrite them; the method is in `docs/background.md`.

### 8.2 Path configs (all at `thinking_level: high`, same Interactions API surface)
| Config | State | Loss policy | Notes instruction | Replay | Code change |
|---|---|---|---|---|---|
| S0 = Standard | `manual_rolling` (visible text only) | drop oldest pair above `MAX_CONTEXT_LENGTH` 175k (chars, 1 char/token) | on | none | none (a new config entry) |
| S1 | `manual_rolling` | ARC `SummaryCompactor` (harness summary, trigger at 175k provider tokens, 8,192-token cap); `MAX_CONTEXT_LENGTH` raised so drop-oldest never fires | on | none | wire `SummaryCompactor` into `manual_rolling` |
| S2 | as S1 | as S1 | **off** | none | notes flag (the sentence is hard-coded to `provides_continuous_conversation` in `agent.py::_build_system_prompt`) |
| S4 = Provider Adapter | `continuous_conversation` (native thought steps + signatures) | harness summary at 175k (as ARC's Gemini PA config) | off (automatic) | native | none; reconstruct `google-gemini-3-8-flash-high-provider-adapter` from the checked-in low config (`thinking_level: high`) and confirm against the session config tag |

- **Step meanings:**
  - S0→S1 changes the loss policy.
  - S1→S2 removes the notes instruction.
  - S2→S4 adds native replay, together with the native item format; the two cannot be separated here.
- **Order dependence:** the decomposition depends on path order, so report it as a *path* decomposition.
- **Optional S3:** S2 plus `analysis_mode`-style readable reasoning summaries in history, i.e. "readable replay". It is a direct precursor of StateCarry's belief digest. Run it only if budget allows. `analysis_mode` also re-adds the notes sentence, so the notes flag must override it.

### 8.3 Games, seeds, logging
**Game selection rule (pre-register):**
- **Eligible:** public games where both published high-effort runs cost ≤ $60 *and* the published Standard-to-Adapter gap is ≥ 20 points. These are FT09, SB26, R11L, LP85, SC25 and CD82 (see `docs/background.md`).
- **Draw 4** of the 6 with a recorded random seed.
- The published runs are one-seed screens. Our fresh seeds re-measure the gap, and claims are stated as conditional on "games where the Adapter helps".
- The 2 undrawn games become StateCarry held-out games.

**Runs:** 4 games × 4 configs (S0, S1, S2, S4) × 2 seeds = 32 runs.

**Log per run:** config hash, fork commit, model string, exit reason (`GAME_WIN`, `ACTION_BUDGET`, `TIME_BUDGET`, `API_ERROR`, `AGENT_ERROR`, …), per-level results, actions, tokens (input, cached, output, reasoning), cost (list and actually billed) and wall clock.

**Pre-registered rule for errors:** a run ending in `API_ERROR`, `AGENT_ERROR` or `TIME_BUDGET` is re-run once with a new seed. Both runs are reported.

**Cost controls:**
- Use Gemini **Flex** (50% off) if the harness can pass the service tier through the config's `request` block. Otherwise add a one-line patch. Check that Flex latency fits ARC's 12h wall clock.
- Finish all Gemini ARC runs before 2026-12-31: Gemini 3.8 Flash prices double on 2027-01-01.

**ARC API key:** playing games requires an ARC API key from arcprize.org (`ARC_API_KEY`). The researcher has to obtain it.

## 9. Phases

### Phase 0 + 1 = MVP (Oct 1-21)
- PersistGym-lite (§5-6) on luna and sol.
- ARC free analysis (§8.1) and path study (§8.2-8.3).

**Deliverables:**
- a survival-accounting figure;
- a success-and-tokens figure by harness × recoverable × derived;
- the ARC path table plus the per-level figure.

### Phase 2: StateCarry builder (Oct 22-Nov 4)
StateCarry is a provider-neutral state component for ARC's Standard harness (`manual_rolling`). Its design follows what the MVP shows: derived, non-recoverable state is what gets lost.

**Components:**
1. **Pre-eviction promotion.** Before the loss policy drops or summarizes a span, one call turns it into typed ledger entries:
   - rule hypotheses, with the turn IDs of their evidence;
   - an action → effect table;
   - open questions.
2. **Visible belief digest** of ≤150 tokens per turn. It stands in for opaque reasoning replay and starts from ARC's `analysis_mode`.
3. **Pointers instead of copies** for facts that can be re-queried.
4. **Cache-friendly layout.** History is append-only, and the ledger sits in a fixed slot so prompt caching survives.

**Steps:**
1. Check StateCarry cheaply as an extra PersistGym cell on luna. Does it rescue the far / derived / non-recoverable cells?
2. Develop on the 4 path-study games (dev set), with a spend cap of $150.
3. Evaluate on held-out games: 3 games (the 2 undrawn eligible games plus VC33 or RE86, fixed in PREREG) × {S0, S4, S0+StateCarry} × 2 seeds = 18 runs. Pilot runs from M0 are never counted as dev or held-out data.

**Pre-registered win:** on held-out games, StateCarry closes at least 50% of the S0→S4 gap, at a mean cost per game no higher than S4's.

**Prior art to compare against and cite:**
- Ledger ([2608.00808](https://arxiv.org/abs/2608.00808)) already shows a success win on coding, so a coding *success* win would not be new.
- PRO-LONG ([2607.20064](https://arxiv.org/abs/2607.20064)), Prime Agent ([2608.23552](https://arxiv.org/abs/2608.23552)) and Tycho ([2607.28287](https://arxiv.org/abs/2607.28287)).

**Framing:** we are closing the Standard-to-Adapter gap under ARC's fair-comparison rules, not claiming a new state of the art.

**Crowding on the Kaggle side (found 2026-09-30 while judging a related idea, I-20260929-22).** On the ARC-AGI-3 Kaggle track (offline open models), the common baseline agent "Duck" already turns on `preserve_thinking` with prefix caching. It stores each turn's reasoning, keeps a structured world/goal/action/open-questions block and runs a persistent REPL. At least four public teams are ablating reasoning replay, ledgers, world-model slices and compaction there, with results due before Nov 2. Leaderboard gains on that track come mostly from serving throughput, not memory design.

StateCarry's niche is different: API models inside ARC's *Standard* harness, measured against the Provider Adapter, with a pre-registered mechanism story from PersistGym. Still, (a) cite Duck and the public Kaggle ablations as prior art for ledger- and replay-style state, (b) don't claim the ledger idea as new, and (c) re-check those teams' posts at G2 and G3 (see §15).

### Extensions (after gates, mostly after Nov 13)
- **E1, open-weights replay.**
  - Qwen3.6-27B with `preserve_thinking` on vs off, plus gpt-oss-120b as the untrained contrast, on PersistGym.
  - Runs on vLLM on a rented A100-80GB.
  - Tests whether replay needs training for it.
  - It moves into the MVP if the sol toggle fails at G0.
- **E2, message structure.** Observations as tool outputs inside one user turn vs as separate user turns. This tests the design review's point that "trained to consume replay" may really mean "tool-chain vs user-turn structure".
- **E3, Terminal-Bench cost win.**
  - StateCarry vs the base harness on a 30-task Terminal-Bench 4.0 subset × 3 runs, on a cheap model.
  - Pre-registered win: success within ±3pp and at least 15% fewer tokens. This is the cost win the theory predicts for recoverable state.
- **E4, second ARC model for StateCarry.** gpt-6.1-sol on 2-3 held-out games, only after a one-game cost pilot. This shows provider neutrality.
- **E5, ARC Prize 2026 Paper Track.** Conditional; see §13. Default is **no**.
- **E6, release and visibility.**
  - HF dataset and HF Space for PersistGym. The Space plots effects against task properties, not models.
  - Upstream PR of the S1/S2 path configs and an opt-in StateCarry mode to ARC's harness, if the researcher agrees.

## 10. Analysis plan
**Primary PersistGym analysis, per model.** Success at the need step, analysed with the fully crossed within-template design.
- **Primary contrasts (H1-H3):** probability-scale differences of cell means, with 90% and 95% CIs from a cluster bootstrap over templates (10,000 resamples).
- **Confirmatory model:** logistic regression with template fixed effects, harness × recoverable × derived × distance terms and cluster-robust SEs. This is what the power simulation assumed.
- **Sensitivity model:** a Bayesian logistic GLMM with template random intercepts (e.g. `bambi`).
- Report both logit and probability scales. Interactions can flip sign between scales near ceilings; the pre-registered scale for kill rules is the probability scale.

**Not used:** max−min harness spread. Under the null it rises as success falls; a simulation with no true effect gave an expected 8.7pp at p=0.95 and 16.1pp at p=0.60. If a single "how much does the harness matter" summary is wanted, use a harness variance component with a permutation null.

**Multiplicity:** Holm correction across the primary confirmatory contrasts (H1, H2, H3). H4 and H5 are descriptive.

**Cost outcomes:** tokens, reasoning tokens, lookups and dollars per episode. Use log-linear models with template fixed effects, and report ratios.

**Accounting:** P(carried), P(used | carried) and P(rescued | not carried) by cell, from the survival calculator and string-match logs.

**Failure labels.** The researcher labels about 100 failure transcripts, stratified by cell, as:
- never encoded,
- evicted,
- misapplied,
- re-derived wrongly.

An LLM judge acts as second rater; report Cohen's κ.

**Power.** Simulation in the premise check, with template random-intercept SD 1.0 on the logit scale, success 0.9 → 0.8 across distance, clustered GLM with template fixed effects, 200 reps:

| Templates × distance levels × seeds | Episodes per model per harness pair | Power, 10pp interaction | Power, 20pp interaction |
|---|---|---|---|
| 60 × 5 × 2 | 1,200 | 0.23 | 0.57 |
| 120 × 5 × 2 | 2,400 | 0.39 | 0.88 |
| 120 × 2 × 2 | 960 | n/a | 0.77 |
| card's plan, 30 tasks × 5 d × 2 seeds per volume | 600 | about 0.16-0.31 (reported as one range, not split by effect size) | |

Our design uses 2 distance levels that bracket the eviction threshold and ~100 fully crossed templates on luna. Mechanical S=0 effects are tens of points and cheap to detect, so the budget goes to the subtle contrasts (H2, H3, rescue rates).

**Action at M1:** re-run the power simulation with the variance measured in the validity runs, and adjust template counts before the M2 sweep. The simulation script was in a temporary folder and is not in this repo, so rewrite it from the description above.

**ARC analysis:**
- Per game and config: RHAE (mean over 2 seeds), levels cleared, actions relative to the human baseline, tokens and cost.
- Path shares are (step difference) / (S4 − S0), with a bootstrap over the 8 game-seed units, and the table is labelled descriptive.
- H5 uses a per-level logistic model of P(clear | reached, depth, harness) with game fixed effects, on the published runs and on ours.
- Always report exit reasons.

## 11. Milestones and gates
Weeks start on Thursday Oct 1. Gates are hard stops: record the decision in `results/decisions.md` before continuing.

| Milestone | Dates | Work | Gate | Go / no-go rule |
|---|---|---|---|---|
| **M0** Setup, free data, pilots | Oct 1-7 | Repo scaffold. `PREREG.md` frozen. ARC fork pinned at 4ca00e6, S1/S2 patches, payload snapshot tests. Free ARC analysis (§8.1). Toggle pilots: sol and luna echo, Gemini manual_rolling at high. ARC cost pilot: FT09 under S0 and S4, 30-action smoke tests of S1 and S2, hard cap $60. Pilot runs are excluded from all analyses. | **G0, Oct 7** | Go if: snapshot tests pass; sol's echoed `reasoning.context` matches the request; Gemini S0-S2 run; ARC pilot cost ≤ $30/run with Flex. **If ARC cost > $30/run:** cut to 3 games or medium thinking. **If the sol toggle fails:** H2 moves to open weights (E1 joins the MVP). |
| **M1** PersistGym-lite build + validity | Oct 8-14 | Generator, oracle, survival calculator, 7-8 harness cells, validity runs on luna (then sol). Power re-simulation. ARC path runs start Oct 8. | **G1, Oct 14** | Validity gate (§5) passes. If it fails: one redesign pass until Oct 18. If it still fails: stop PersistGym and continue the ARC leg alone. |
| **M2** Main runs + ARC table | Oct 15-21 | luna sweep; sol H2 core (640 episodes); 32 ARC runs finished; analysis. | **P, Oct 19** (Paper Track) and **G2, Oct 21** | P: see §13. G2: kill the ARC leg if the S0→S4 gap is < 10 RHAE points. Overall kill if H1 *and* H2 are inside equivalence bounds *and* the ARC gap is dominated by a mechanism with no provider-neutral analogue: write a short note (survival accounting + ARC path table) and skip Phase 2. Scoop check: if a per-component ARC ablation has appeared, the ARC table stops being the headline. |
| **M3** Preprint + StateCarry v0 | Oct 22-28 | Preprint and blog draft of the ARC path table plus survival accounting (researcher reviews; target post Oct 28). StateCarry v0: PersistGym cell on luna, then dev ARC games. | **G3, Oct 28** | Continue to held-out evaluation only if v0 closes ≥ 25% of the S0→S4 gap on dev games at ≤ S4 cost. Otherwise stop the builder and write the analysis paper. |
| **M4** StateCarry held-out evaluation | Oct 29-Nov 4 | 18 held-out ARC runs; final figures. | **G4, Nov 4** | Claim wording follows the pre-registered win (≥ 50% of gap at ≤ Adapter cost). Otherwise report it as partial or negative. |
| **M5** Paper | Nov 5-13 | AGENT 2027 paper (full 8 pages, or short 5; see §13). | Submit **Nov 13 AoE** | |
| **M6** Extensions | Nov 14-Jan 2027 | E1-E4 as gated; full version for TMLR or an ICLR 2027 workshop. | Per extension | All Gemini ARC runs finish before Dec 31, 2026. |

Human time: about 30-40 h for the MVP and 40-55 h overall. It goes to definitions and pre-registration, shortcut audits, labelling about 100 transcripts, confirming toggles, choosing claims, and writing. Coding agents do the rest.

## 12. Budget
Prices were checked 2026-09-29/30 ([Gemini](https://ai.google.dev/gemini-api/docs/pricing), [OpenAI](https://developers.openai.com/api/docs/pricing), [OpenAI Flex](https://developers.openai.com/api/docs/guides/flex-processing), [RunPod](https://www.runpod.io/pricing)); more in `docs/background.md`. Reported runs use API keys only. Numbers below are USD.

| Item | Price (per M tokens: input / cached / output) |
|---|---|
| Gemini 3.8 Flash | $0.75 / $0.075 / $3.75 through 2026-12-31, then $1.50 / — / $7.50. Flex and Batch 50% off. |
| gpt-6-luna | $0.10 / $0.01 / $0.50. Flex 50% off. |
| gpt-6.1-sol | $2 / $0.10 / $10. Flex 50% off. |
| GPU for E1 (RunPod) | A100 80GB $1.19-1.59/h; H100 PCIe $1.99-2.89/h |

**PersistGym per-episode assumption:** about 28 calls, contexts up to 64k, about 85% cached input, about 1k output tokens per call. Window cells break caching once full, so they cost more.

| Phase | What | Estimate | Hard cap (stop and ask the researcher) |
|---|---|---|---|
| 0 (Oct 1-7) | Free ARC analysis $0; toggle and payload pilots $5-20; ARC cost pilot ≤ $60 | $20-80 | $100 |
| 1a PersistGym | luna: 3,200-6,400 episodes plus about 1,600 control prompts, at $0.005-0.02 each (Flex) = $25-160. sol core: 640 episodes at $0.05-0.35 = $30-230. Validity runs $10-20. The optional sol H1 replication (+640 episodes, +$30-230) runs only if it fits under the cap. | $65-410 | $450 |
| 1b ARC path | 32 runs. Eligible games average about $31 (S0) and $25 (S4) per run at ARC's no-cache list accounting, so about $900 at list or about $450 with Flex. | $450-900 | $900 |
| **MVP total** | | **~$0.55-1.4k** | |
| 2 StateCarry | PersistGym cell $10-40; ARC dev ≤ $150; 18 held-out runs $350-750 (two cheap games at ~$30/run, plus VC33 or RE86 at ~$65/run, at list; Flex halves this) | $510-940 | $950 |
| **Through phase 2** | | **~$1.05-2.35k** | |
| E1 open weights | 15-50 GPU-hours | $20-80 | |
| E3 Terminal-Bench | cheap model, 90 trials; sandboxes (Modal's $30/month free credit or local Docker) | $100-300 | |
| E4 second ARC model | gpt-6.1-sol, 2-3 games, after a one-game pilot | $200-1,000 | pilot first |
| E5 Kaggle port | Kaggle GPUs free; dev GPU $100-300 | $100-300 | |

This is above the profile's ~$1k flag and ~$200/month cash, and well below the ~$5-10k infeasibility line. **The researcher must approve the phase-1 ARC spend before M1.**

Cheaper fallbacks, in order:
1. Flex everywhere.
2. 3 ARC games.
3. Medium thinking. The published medium gap is 20pp.
4. Fewer sol templates (30).

## 13. Venues
Dates were checked against the `ai-research` deadlines file (verified 2026-09-29) and the linked pages.

| Venue | Deadline | Type | Use here |
|---|---|---|---|
| arXiv preprint + blog (dev.to, LinkedIn, Bluesky) | Target **Oct 28** (ARC path table + survival accounting); update Nov 13 | Preprint | Establishes priority. OpenAI, ARC Prize and several groups are active (see the scoop risks in `docs/premise-check.md`). The researcher reviews the exact text and posts it. |
| [AGENT 2027 @ ICSE](https://conf.researchr.org/home/icse-2027/agent-2027) | **Nov 13 AoE**. The workshop page says Nov 27; ICSE says Nov 13 for all workshops. Plan for Nov 13. | Archival IEEE workshop; full 8 pages or short 5; single-anonymous; no AI policy stated | Main target. Archival: if a later ML main-track version is planned (ICML 2027, deadline TBA, last year late January), submit a **short 5-page** version or go non-archival instead. |
| [ICSE 2027 Industry Challenge](https://conf.researchr.org/track/icse-2027/icse-2027-industry-challenge) ("Agent Memory in the Wild: Reliability, Efficiency, and Evaluation") | Nov 13 AoE | 5-10 pages + 2 | Possible alternative to AGENT. Read the challenge statement first. It cannot take the same paper as AGENT. |
| [ICLR 2027 workshops](https://iclr.cc/Conferences/2027/CallForWorkshops) | ~Feb 1, 2027 (CFPs after Nov 29) | Non-archival | Full version with extensions. ICLR 2027 requires an AI-use statement at the main conference; check each workshop CFP. |
| [TMLR](https://www.jmlr.org/tmlr/) | Rolling | Journal | Full version. LLMs are allowed as assistive tools. |
| [ARC Prize 2026 Paper Track](https://arcprize.org/competitions/2026/paper) | Papers **Nov 8** (arcprize.org) / Nov 9 23:59 UTC ([Kaggle](https://www.kaggle.com/competitions/arc-prize-2026-paper-track)); plan for Nov 8. Needs an [ARC-AGI-3 Kaggle](https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3) entry by **Oct 26** and a code submission by **Nov 2**. | Prize: $75K top-3 plus a $375K pool for papers scoring > 4.5/5 | **Conditional (E5).** See the eligibility note below. |

**ARC Paper Track eligibility.** A paper "must be linked to a Kaggle code submission (ARC-AGI-2 or ARC-AGI-3 track)". The submission "need not achieve a high score". Kaggle evaluation is offline, with no API models. So the API-model analysis alone is **not eligible**. It becomes eligible only if we also submit an offline open-model agent, e.g. Qwen3.6-27B with `preserve_thinking`, or StateCarry on a Milestone-1 open harness, within Kaggle's GPU and ~9h notebook limits.

Other conditions:
- Own code must be CC0 or MIT-0. The design review reports a CC-BY 4.0 winner licence.
- The rubric scores Accuracy (from the Kaggle score), Universality, Progress, Theory, Completeness and Novelty. Accuracy would be weak here.

**Decision P on Oct 19:**
- **Go only if all of these hold:** the researcher accepts the licensing and employer-IP implications; the E1 Qwen pipeline works; and there is a clear result worth documenting.
- **Otherwise skip.** The default is skip, because the Kaggle port competes with M4 and M5 for the same two weeks.
- Joining the Kaggle competition, which means accepting its rules, is the researcher's own action and must happen by Oct 26.

## 14. Kill criteria (consolidated)
1. **G0.** No verifiable replay toggle on any API model → H2 runs on open weights only (E1). If E1 also fails, drop H2 and state it as a limitation.
2. **G0.** ARC pilot > $30/run with Flex → 3 games or medium thinking. If it is still > $30/run, drop the ARC runs and keep the free observational analysis.
3. **G1.** PersistGym fails the validity gate after one redesign → stop PersistGym and continue ARC alone.
4. **G2.** S0→S4 gap on the 4 games < 10 RHAE points → kill the ARC path leg.
5. **G2.** H1 and H2 both inside equivalence bounds, *and* the ARC gap is dominated by a mechanism with no provider-neutral analogue → publish a short note, no builder.
6. **Any time.** A per-component ablation of ARC's gap appears (ARC Prize, OpenAI or others) → the ARC table becomes supporting material. Lead with PersistGym + StateCarry.
7. **G3.** StateCarry v0 closes < 25% of the gap on dev games → stop the builder and write the analysis paper.

The card's old rule, "95% CI of the harness × d slope includes 0", is replaced by the equivalence bounds above. With the card's sample sizes, the old rule would have fired even when a true effect exists.

## 15. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Scooped on the ARC leg (ARC Prize adds adapters weekly; OpenAI's July post names the mechanisms) | High | Free analysis in week 1, preprint target Oct 28, ARC table framed as supporting evidence. |
| Scooped on the mechanism leg (TierFlow group: 2609.29875 and StateComp; LOCA-bench group; harness-design study authors) | Medium | Differentiate on recoverability × derivedness, within-template crossed design, survival accounting, and the builder. |
| The StateCarry builder overlaps public ARC Kaggle work. The Duck baseline already has reasoning replay plus a structured world/goal/action block, and 4+ public teams are ablating replay, ledgers and compaction, with results due before Nov 2 | High | Position StateCarry as API-model, Standard-harness, mechanism-driven; cite Duck and the Kaggle ablations; re-check at G2 and G3. If a Kaggle team publishes a Standard-harness gap closure, drop the builder claim and keep the analysis. This also makes E5 (Paper Track) less attractive. |
| The replay toggle is not what the model actually sees (opaque items; luna may ignore `all_turns`) | Medium | Echo check on every response, payload snapshot tests, open-weights replication with a visible template (E1). |
| The published ARC gap partly reflects harness errors (early-ending Standard runs) | Medium | Log exit reasons, pre-registered re-run rule, report both. |
| Standard-harness API surface for published Gemini runs unknown | Certain | Hold the Interactions API fixed across all our configs and re-measure S0 ourselves. |
| Cost overrun on ARC (runs vary $8-$295 per game; Standard trimming breaks caching) | Medium | Cheap-game rule, Flex, per-phase hard caps, cost logged per run. |
| Price and model changes (Gemini doubles Jan 1, 2027; deprecations) | Certain / medium | Finish ARC runs in 2026; pin versions; record returned model strings. |
| Flex latency, 429s and ARC's 12h wall clock | Medium | Retry with backoff (429s on Flex are not billed); fall back to standard tier for runs that time out, and record it. |
| Results look like a model quirk, not a mechanism | Medium | Two API models plus open weights (E1); claims stated per component and per state type. |
| Employer sensitivity (vendor comparisons) | Low | One-off study; no rankings or dashboard; neutral wording; figures by task property; the researcher reviews all public text. |
| Human time is the bottleneck (labelling, definitions) | Medium | Labelling capped at ~100 transcripts; agents build everything else. |
