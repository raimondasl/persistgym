# PLAN: when does the harness matter?

_Written 2026-09-30 as the hand-off from the `ai-research` scouting repo (idea I-20260929-06). Sources for every outside fact are in `docs/background.md`; the premise checks behind the changes are in `docs/premise-check.md`._

_**Amended 2026-09-30 (A1):** staged low-spend approvals, cost corrections, who gets paid, and new provider facts. The amendment is §16; passages it changes are marked **[A1]**. Where §16 and an earlier section disagree, §16 wins._

_**Amended 2026-10-01 (A2):** the researcher's decisions before the PREREG freeze: fixed ARC games, sol's run matrix, the ARC service tier, cost forecasts and phase caps. The amendment is §17; passages it changes are marked **[A2]**. §16 is left as written. Where §17 and an earlier section, §16 included, disagree, §17 wins._

_**Amended 2026-10-02 (A3):** sol's reasoning effort and template count, after block 1's pilots. The amendment is §18, which points to `PREREG.md` §17.2 (amendment R2); passages it changes are marked **[A3]**._

_**Amended 2026-10-02 (A4):** a derived-fact variant for sol, with a hard stop, after sol's engagement check found no reasoning to replay. The amendment is §19, which points to `PREREG.md` §17.3 (amendment R3); passages it changes are marked **[A4]**._

_**Amended 2026-10-03 (A5):** a pre-registered sol replication of H1, at the researcher's request, so that PersistGym has evidence on a second model, gpt-6.1-sol, after H2 on sol stopped under A4's hard stop. The amendment is §20, which points to `PREREG.md` §17.4 (amendment R4); passages it changes are marked **[A5]**._

_**Amended 2026-10-07 (A6):** action-matched secondary readings for the ARC path study, after block 2's first two runs, in which ARC's 12 h clock bound the Standard config's run but not the Adapter's. The amendment is §21, which points to `PREREG.md` §17.5 (amendment R5); passages it changes are marked **[A6]**._

_**Amended 2026-10-09 (A7):** the minimal path after Checkpoint C's cost rule fired: ARC's S2 on seed 1 (S1 only if decided first) and luna's sweep, then a hard stop, for a project total of about $560; no seed 2, no phase 2, an arXiv preprint before Nov 2. The amendment is §22, which points to `PREREG.md` §17.6 (amendment R6); passages it changes are marked **[A7]**._
_**Amended 2026-10-10 (A8):** ARC's harness summary request in S1 and S2 gets the same 65,536-token output budget as every step request (it was 8,192, which reasoning at high thinking could fill), and a unit whose counted S1/S2 run was lost to that failure gets one replacement run. The amendment is §23, which points to `PREREG.md` §17.7 (amendment R7)._

## 1. Summary
ARC-AGI-3 scores move by 25-45 points between ARC Prize's Standard harness and its Provider Adapter ([GPT-6 Astra](https://arcprize.org/results/openai-gpt-6-astra), [Gemini 3.8 Flash](https://arcprize.org/results/google-gemini-3-8-flash)). Coding-agent success moves by only a few points across harnesses ([HarnessTax](https://arena.ai/blog/coding-agents-harness-tax)). We test whether this is because ARC needs **derived, non-recoverable** state that the Standard harness throws away, while coding state can usually be re-read from disk. The plan has three parts:
- **Measure it** in a small generated environment (PersistGym-lite).
- **Attribute** ARC's gap on Gemini 3.8 Flash to its components: loss policy, notes instruction, reasoning replay.
- **Build** a provider-neutral state component (StateCarry) that should recover most of the Adapter's advantage inside the Standard harness. **[A7]** Not built: phase 2 is not run (§22).

The minimal version runs Oct 1-21. The builder phase runs Oct 22-Nov 4. The first paper target is AGENT 2027 (Nov 13 AoE). **[A7]** There is no builder phase. The first target is an arXiv preprint before Nov 2, then TMLR or an AGENT 2027 short paper (§22).

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

**Reframed:** OpenAI already *named* the two mechanisms behind the ARC gap: retained reasoning, and compaction instead of rolling truncation ([OpenAI, Jul 29 2026](https://openai.com/index/how-two-settings-tripled-our-arc-agi-3-scores/)). It reported only their combined effect (13.3% to 38.3% for GPT-5.6 Sol on the public set). Our ARC contribution is therefore per-component numbers with seeds, the role of the notes instruction, a non-OpenAI replication, and a provider-neutral fix. It is not "explaining an unexplained gap". **[A7]** Narrowed: one seed per game and config; the notes instruction's role is measured only if S1 runs (with S2 alone, the split is the provider-neutral steps together vs native replay); no provider-neutral fix (§22).

## 3. Deliverables
- **PersistGym-lite:** generator, programmatic oracle, survival calculator, harness cells, and run data. MIT license, GitHub, plus an HF dataset.
- **ARC path table:** Gemini 3.8 Flash, 4 public games, 4 configs, 2 seeds, plus a per-level analysis. Published as an early arXiv preprint and blog post (priority). **[A7]** S0, S2 and S4 (S1 only if decided before block 3's first ARC run) × 4 games × seed 1; the preprint goes out before Nov 2 (§22).
- **StateCarry:** an opt-in state mode for ARC's Standard harness, evaluated on held-out public games. Offered upstream to `arcprize/arc-agi-3-benchmarking` if the researcher agrees. **[A7]** Dropped: phase 2 is not run (§22).
- **Paper:** AGENT 2027 (Nov 13). A fuller version goes to TMLR or an ICLR 2027 workshop. **[A7]** After the arXiv preprint: TMLR or an AGENT 2027 short paper of 5 pages (§22).

## 4. Pre-registered hypotheses
These are drafts. At M0, copy them into `PREREG.md` with exact definitions and commit before any paid run, including the M0 pilots. **[A1]** Target Oct 3, not the Oct 7 gate (§16.3). After that, change `PREREG.md` only through a dated amendment that says why.

Definitions to fix in `PREREG.md` (these need the researcher's judgment):
- **Observed fact:** a value shown verbatim in one observation.
- **Derived fact:** a value computed from 2-3 observations shown at different steps. It is never shown in final form.
- **Recoverable:** a `lookup` action re-shows the fact (or its clues) at the cost of one step.
- **Needed:** the step at which the fact determines the only correct action. "Needed" and "live" come from the generator's dependency graph, never from agent trajectories.
- **Survives (S):** whether the fact (or all its clues) is still in the context the harness sends at the need step. Computed from token positions for window harnesses. Measured by string match for summary and notes, since those depend on what the model writes.
- **Near / far:** the reveal lies inside / beyond the harness eviction threshold W, in tokens.

Kill and equivalence rules below use 90% CIs from a template-level cluster bootstrap on the probability scale.

### H1: recoverability turns a success penalty into a cost penalty
Model: gpt-6-luna (primary). Replication on gpt-6.1-sol if the budget allows (adds cells W-0 and W-n-0 on sol, about 640 episodes). **[A1]** Removed from the MVP: re-costed at about $430-610 at Flex with cache writes, not $30-230 (§16.1). Revisit as an extension. **[A5]** Re-instated as a pre-registered replication outside the Holm family: sol at medium effort on the default generator config, F-0, W-0 and W-n-0 on the 4 observed task cells (§20). **[A7]** Its main runs are not run (budget); its pilot and validity runs are reported descriptively, and H1 rests on luna alone (§22).

Comparison: an observed fact at far distance, window harness **without** notes (W-0, so S=0 by construction), vs full history (F-0). W-n-0 is reported alongside it as the notes-rescue condition.

**Predictions:**
- If the fact is **not recoverable**, success drops by at least 25pp.
- If it is **recoverable**, success stays within 5pp, but lookups and total tokens rise by at least 30%. **[A2]** "Total tokens" is read as need-phase tokens in a near/far difference-in-differences; whole-episode readings are secondary (D8, §17.1).

**Falsified or kill** if the difference between the two penalties is below 10pp, with the 90% CI upper bound below 15pp. In that case drop the "success vs cost" framing.

### H2: reasoning replay carries derived state
Model: gpt-6.1-sol, plus gpt-6-luna if the M0 pilot shows it honours `all_turns`. Arms: full history, `reasoning.context` = `all_turns` (F-r) vs `current_turn` (F-0). **[A2]** sol runs only the far cells: derived-far on T_d templates and observed-far on T_d/3 of them (D11 option A, §17.1). On sol, the observed-fact prediction below is therefore checked on observed-far cells only.

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

We register both and report which one the data supports. With 4 games × 2 seeds this is **descriptive**. Shares get bootstrap intervals over game-seed units, and we make no significance claims. **[A6]** Secondary readings at a matched 150 actions are added; the clock-based readings stay primary (§21). **[A7]** 4 games × seed 1 (4 units), with S0, S2 and S4, plus S1 only if decided before block 3's first ARC run. Without S1, Prediction B is tested in full and Prediction A only in its replay clause (§22).

**Kill the ARC leg** if the measured S0→S4 gap, averaged over the 4 games, is below 10 RHAE points. **[A7]** Read on the 4 seed-1 units; the gap (62.59) was known when A7 was written, so this rule cannot fire (§22).

### H5: the Adapter advantage grows with level depth
The Adapter's advantage in P(clear level ℓ | reached ℓ) is larger at levels ≥4 than at levels 1-2.
- Tested first on ARC's published public-set runs (free; §8.1).
- Then on our runs. **[A7]** Our 8 seed-1 S0 and S4 runs, which were seen before A7, so this is no longer a blind test (§22).

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

**Templates.** A template is one sampled skeleton: surface story, fact values, filler. Each template is rendered into **all 8 task cells and all harness cells** (fully crossed). All contrasts are therefore within-template, and template fixed effects absorb difficulty. Add templates rather than seeds: run 1 repeat per template × cell, and 2 repeats on a 10% subset to estimate within-template noise. **[A2]** The repeat subset runs on both luna and sol. Template seeds start at 0, and runs use whole blocks of 10 seeds (D7, §17.1). sol is not fully crossed: its templates are rendered into the far cells only (D11 option A, §17.1).

**Controls, on the same templates:**
- **Position-matched single-turn:** the same token sequence flattened into one prompt, with the fact at the same offset. Used for H3.
- **Restated-at-need:** the fact is repeated in the need-step observation. This is the ceiling with memory taken out of the problem.

**Validity gate (G1), per model:**
- The programmatic oracle, which knows the fact, scores 100%. This is a generator sanity check.
- The LLM on restated-at-need scores ≥ 85% (enough headroom).
- The LLM with the fact withheld scores ≤ chance + 10pp = 20%, so the fact is actually needed.
- The researcher spot-checks 20 episodes per cell for shortcuts, e.g. the fact being inferable from filler.
- **[A2]** In every derived cell, no proper subset of the clues narrows the 10 options, and partial-memory heuristics score ≤ 20%. This is a $0 generator check (D2, §17.1).

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
| gpt-6.1-sol (OpenAI Responses, Flex) | H2 replay toggle; optional H1 replication; ~40 templates per cell | `reasoning.context` = `all_turns` vs `current_turn`, with encrypted reasoning items sent (`store:false`, `include: reasoning.encrypted_content`). The payload stays identical and only rendering changes. | Docs: "GPT-6.1 Sol also supports `all_turns`", and the response echoes the effective mode. **Check the echo on every response**; log and drop mismatches. Core: F-r vs F-0 on all 8 task cells. The W/Σ replay pairs run only if H2 shows signal. **[A2]** Core is now F-r vs F-0 on the 4 far cells only: derived-far on T_d templates (planning value 120) and observed-far on T_d/3; no near cells (D11 option A, §17.1). **[A3]** T_d = 210 and T_o = 70, at `reasoning.effort: high` if a blinded engagement check passes (§18). **[A4]** sol plays a derived-fact variant whose clues take two 3-digit operations each, with a notice at each evidence step, and H2 on sol stops for good if its engagement check fails (§19). **[A7]** The H1 replication's main runs are not run; only its pilot and validity runs exist (§22). |
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
- **Eligible:** public games where both published high-effort runs cost ≤ $60 *and* the published Standard-to-Adapter gap is ≥ 20 points. These are FT09, SB26, R11L, LP85, SC25 and CD82 (see `docs/background.md`). **[A1]** This filter can select Standard runs that were cheap because they ended in an error; the researcher decides before the draw whether to keep or amend it (§16.4). **[A2]** Decided (D14 option A): the games are fixed by rule, with no draw. Path games: FT09, SB26, R11L, CD82. Held-out games: SP80, VC33, TN36 (§17.1).
- **Draw 4** of the 6 with a recorded random seed. **[A2]** No draw. The beacon seed picks only the pilot game, the game dropped under the 3-game fallback and the run orders (D15, §17.1).
- The published runs are one-seed screens. Our fresh seeds re-measure the gap, and claims are stated as conditional on "games where the Adapter helps".
- The 2 undrawn games become StateCarry held-out games. **[A2]** The held-out games are SP80, VC33 and TN36 (§17.1).

**Runs:** 4 games × 4 configs (S0, S1, S2, S4) × 2 seeds = 32 runs. **[A7]** 12 counted runs (S0, S2 and S4 × 4 games × seed 1), or 16 if S1 runs, plus re-runs; S1 runs only if the researcher decides so before block 3's first ARC run, and seed 2 is not run (§22).

**Log per run:** config hash, fork commit, model string, exit reason (`GAME_WIN`, `ACTION_BUDGET`, `TIME_BUDGET`, `API_ERROR`, `AGENT_ERROR`, …), per-level results, actions, tokens (input, cached, output, reasoning), cost (list and actually billed) and wall clock.

**Pre-registered rule for errors:** a run ending in `API_ERROR`, `AGENT_ERROR` or `TIME_BUDGET` is re-run once with a new seed. Both runs are reported. **[A2]** `TIME_BUDGET` is final, except in a provider-latency incident (D20, §17.1).

**Cost controls:**
- Use Gemini **Flex** (50% off) if the harness can pass the service tier through the config's `request` block. Otherwise add a one-line patch. Check that Flex latency fits ARC's 12h wall clock. **[A1]** Flex is uncertain for ARC: Google's target is 1-15 min per call with no fallback. One tier is chosen for all ARC configs by a pre-registered latency rule; runs never switch tier (§16.4). **[A2]** Decided (D21): Gemini standard tier for all ARC runs. Flex is not used for ARC, and the Flex latency probe is dropped (§17.1).
- Finish all Gemini ARC runs before 2026-12-31: Gemini 3.8 Flash prices double on 2027-01-01.

**ARC API key:** playing games requires an ARC API key from arcprize.org (`ARC_API_KEY`). The researcher has to obtain it.

## 9. Phases

### Phase 0 + 1 = MVP (Oct 1-21)
- PersistGym-lite (§5-6) on luna and sol. **[A7]** The main sweep runs on luna only (§22).
- ARC free analysis (§8.1) and path study (§8.2-8.3).

**Deliverables:**
- a survival-accounting figure;
- a success-and-tokens figure by harness × recoverable × derived;
- the ARC path table plus the per-level figure.

### Phase 2: StateCarry builder (Oct 22-Nov 4)
StateCarry is a provider-neutral state component for ARC's Standard harness (`manual_rolling`). Its design follows what the MVP shows: derived, non-recoverable state is what gets lost. **[A7]** Phase 2 is not run (§22).

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
2. Develop on the 4 path-study games (dev set), with a spend cap of $150. **[A2]** The 4 G3 runs are a separate phase-2 line, outside this cap (D24, §17.1).
3. Evaluate on held-out games: 3 games (the 2 undrawn eligible games plus VC33 or RE86, fixed in PREREG) × {S0, S4, S0+StateCarry} × 2 seeds = 18 runs. Pilot runs from M0 are never counted as dev or held-out data. **[A2]** The held-out games are SP80, VC33 and TN36. All three are committed; there is no conditional cut to 2 games (D14 option A, D24 option B; §17.1).

**Pre-registered win:** on held-out games, StateCarry closes at least 50% of the S0→S4 gap, at a mean cost per game no higher than S4's. **[A2]** Cost is compared on the billed basis, with list reported alongside (D23, §17.1).

**Prior art to compare against and cite:**
- Ledger ([2608.00808](https://arxiv.org/abs/2608.00808)) already shows a success win on coding, so a coding *success* win would not be new.
- PRO-LONG ([2607.20064](https://arxiv.org/abs/2607.20064)), Prime Agent ([2608.23552](https://arxiv.org/abs/2608.23552)) and Tycho ([2607.28287](https://arxiv.org/abs/2607.28287)).

**Framing:** we are closing the Standard-to-Adapter gap under ARC's fair-comparison rules, not claiming a new state of the art.

**Crowding on the Kaggle side (found 2026-09-30 while judging a related idea, I-20260929-22).** On the ARC-AGI-3 Kaggle track (offline open models), the common baseline agent "Duck" already turns on `preserve_thinking` with prefix caching. It stores each turn's reasoning, keeps a structured world/goal/action/open-questions block and runs a persistent REPL. At least four public teams are ablating reasoning replay, ledgers, world-model slices and compaction there, with results due before Nov 2. Leaderboard gains on that track come mostly from serving throughput, not memory design.

StateCarry's niche is different: API models inside ARC's *Standard* harness, measured against the Provider Adapter, with a pre-registered mechanism story from PersistGym. Still, (a) cite Duck and the public Kaggle ablations as prior art for ledger- and replay-style state, (b) don't claim the ledger idea as new, and (c) re-check those teams' posts at G2 and G3 (see §15). **[A7]** With no builder, this crowding is a reason to post the arXiv preprint before Nov 2; the posts are re-checked at G2 and before the preprint goes out (§22).

### Extensions (after gates, mostly after Nov 13)
- **E1, open-weights replay.** **[A7]** No extension runs under A7's hard stop (§22).
  - Qwen3.6-27B with `preserve_thinking` on vs off, plus gpt-oss-120b as the untrained contrast, on PersistGym.
  - Runs on vLLM on a rented A100-80GB.
  - Tests whether replay needs training for it.
  - It moves into the MVP if the sol toggle fails at G0.
- **E2, message structure.** Observations as tool outputs inside one user turn vs as separate user turns. This tests the design review's point that "trained to consume replay" may really mean "tool-chain vs user-turn structure".
- **E3, Terminal-Bench cost win.**
  - StateCarry vs the base harness on a 30-task Terminal-Bench 4.0 subset × 3 runs, on a cheap model.
  - Pre-registered win: success within ±3pp and at least 15% fewer tokens. This is the cost win the theory predicts for recoverable state.
- **E4, second ARC model for StateCarry.** gpt-6.1-sol on 2-3 held-out games, only after a one-game cost pilot. This shows provider neutrality.
- **E5, ARC Prize 2026 Paper Track.** Conditional; see §13. Default is **no**. **[A7]** Skipped (§22).
- **E6, release and visibility.** **[A7]** Whether PersistGym's code and data go out with the preprint is the researcher's decision; there is no StateCarry mode to offer (§22).
  - HF dataset and HF Space for PersistGym. The Space plots effects against task properties, not models.
  - Upstream PR of the S1/S2 path configs and an opt-in StateCarry mode to ARC's harness, if the researcher agrees.

## 10. Analysis plan
**Primary PersistGym analysis, per model.** Success at the need step, analysed with the fully crossed within-template design. **[A2]** On sol the design covers the far cells only, so H2's contrasts are within-template on those cells (D11 option A, §17.1).
- **Primary contrasts (H1-H3):** probability-scale differences of cell means, with 90% and 95% CIs from a cluster bootstrap over templates (10,000 resamples).
- **Confirmatory model:** logistic regression with template fixed effects, harness × recoverable × derived × distance terms and cluster-robust SEs. This is what the power simulation assumed.
- **Sensitivity model:** a Bayesian logistic GLMM with template random intercepts (e.g. `bambi`).
- Report both logit and probability scales. Interactions can flip sign between scales near ceilings; the pre-registered scale for kill rules is the probability scale.

**Not used:** max−min harness spread. Under the null it rises as success falls; a simulation with no true effect gave an expected 8.7pp at p=0.95 and 16.1pp at p=0.60. If a single "how much does the harness matter" summary is wanted, use a harness variance component with a permutation null.

**Multiplicity:** Holm correction across the primary confirmatory contrasts (H1, H2, H3). H4 and H5 are descriptive. **[A7]** H2 stopped under A4, so the family is H1 and H3, 2 one-sided tests, as the researcher decided on 2026-10-06 before any H1 or H3 test; the family of 4 is a sensitivity analysis (§22).

**Cost outcomes:** tokens, reasoning tokens, lookups and dollars per episode. Use log-linear models with template fixed effects, and report ratios.

**Accounting:** P(carried), P(used | carried) and P(rescued | not carried) by cell, from the survival calculator and string-match logs.

**Failure labels.** The researcher labels about 100 failure transcripts, stratified by cell, as:
- never encoded,
- evicted,
- misapplied,
- re-derived wrongly.

An LLM judge acts as second rater; report Cohen's κ. **[A7]** Dropped: no failure labels and no LLM judge (§22).

**Power.** Simulation in the premise check, with template random-intercept SD 1.0 on the logit scale, success 0.9 → 0.8 across distance, clustered GLM with template fixed effects, 200 reps:

| Templates × distance levels × seeds | Episodes per model per harness pair | Power, 10pp interaction | Power, 20pp interaction |
|---|---|---|---|
| 60 × 5 × 2 | 1,200 | 0.23 | 0.57 |
| 120 × 5 × 2 | 2,400 | 0.39 | 0.88 |
| 120 × 2 × 2 | 960 | n/a | 0.77 |
| card's plan, 30 tasks × 5 d × 2 seeds per volume | 600 | about 0.16-0.31 (reported as one range, not split by effect size) | |

Our design uses 2 distance levels that bracket the eviction threshold and ~100 fully crossed templates on luna. Mechanical S=0 effects are tens of points and cheap to detect, so the budget goes to the subtle contrasts (H2, H3, rescue rates).

**Action at M1:** re-run the power simulation with the variance measured in the validity runs, and adjust template counts before the M2 sweep. The simulation script was in a temporary folder and is not in this repo, so rewrite it from the description above. **[A7]** luna's template count follows the frozen power rule, capped at 200 (§22).

**ARC analysis:**
- Per game and config: RHAE (mean over 2 seeds), levels cleared, actions relative to the human baseline, tokens and cost. **[A6]** Also, as secondary readings, the score and levels cleared within the first 150 actions, with a levels-by-action curve per run (§21). **[A7]** One seed: each game and config has its counted seed-1 run, for S0, S2 and S4, plus S1 if it runs (§22).
- Path shares are (step difference) / (S4 − S0), with a bootstrap over the 8 game-seed units, and the table is labelled descriptive. **[A7]** The bootstrap is over the 4 seed-1 game units; per-game step differences and the leave-one-game-out values of the replay share are reported too (§22).
- H5 uses a per-level logistic model of P(clear | reached, depth, harness) with game fixed effects, on the published runs and on ours.
- Always report exit reasons.

## 11. Milestones and gates
Weeks start on Thursday Oct 1. Gates are hard stops: record the decision in `results/decisions.md` before continuing.

| Milestone | Dates | Work | Gate | Go / no-go rule |
|---|---|---|---|---|
| **M0** Setup, free data, pilots | Oct 1-7 | Repo scaffold. `PREREG.md` frozen. ARC fork pinned at 4ca00e6, S1/S2 patches, payload snapshot tests. Free ARC analysis (§8.1). Toggle pilots: sol and luna echo, Gemini manual_rolling at high. ARC cost pilot: FT09 under S0 and S4, 30-action smoke tests of S1 and S2, hard cap $60. Pilot runs are excluded from all analyses. **[A1]** Order and content changed: PREREG and the seeded draw first (target Oct 3); a truncated pilot on one drawn path game replaces the FT09 pilot; a $2 replay-use probe is added; the PersistGym build is pulled into M0 (§16.3). | **G0, Oct 7** | Go if: snapshot tests pass; sol's echoed `reasoning.context` matches the request; Gemini S0-S2 run; ARC pilot cost ≤ $30/run with Flex. **If ARC cost > $30/run:** cut to 3 games or medium thinking. **If the sol toggle fails:** H2 moves to open weights (E1 joins the MVP). **[A1]** The cost rule becomes "forecast billed 1b + re-run reserve ≤ $900 at the chosen tier"; the toggle rule adds the replay-use probe; G0 approves only the seed-1 S0+S4 block (§16.2). **[A2]** The tier is Gemini's standard tier (D21). The forecast prices S1 and S2 at the S0/S4 midpoint (D27 rule 1); Checkpoint C adds a conservative check (§17.1). |
| **M1** PersistGym-lite build + validity | Oct 8-14 | Generator, oracle, survival calculator, 7-8 harness cells, validity runs on luna (then sol). Power re-simulation. ARC path runs start Oct 8. | **G1, Oct 14** | Validity gate (§5) passes. If it fails: one redesign pass until Oct 18. If it still fails: stop PersistGym and continue the ARC leg alone. **[A7]** No redesign pass: if luna fails G1, PersistGym stops at once and the paper reports the ARC leg alone (§22). |
| **M2** Main runs + ARC table | Oct 15-21 | luna sweep; sol H2 core (640 episodes); 32 ARC runs finished; analysis. **[A2]** sol runs far cells only: 704 episodes with repeats at T_d = 120 (D11 option A, §17.1). **[A3]** 1,232 episodes with repeats at T_d = 210 (§18). **[A7]** luna's sweep and 4 ARC S2 runs (8 with S1), plus any re-run; no sol main runs (§22). | **P, Oct 19** (Paper Track) and **G2, Oct 21** | P: see §13. G2: kill the ARC leg if the S0→S4 gap is < 10 RHAE points. Overall kill if H1 *and* H2 are inside equivalence bounds *and* the ARC gap is dominated by a mechanism with no provider-neutral analogue: write a short note (survival accounting + ARC path table) and skip Phase 2. Scoop check: if a per-component ARC ablation has appeared, the ARC table stops being the headline. **[A7]** P is skipped. G2 records the gap, the S2 shares and the scoop check; its ARC kill cannot fire, since the gap (62.59) is already known, and the overall kill is moot (§22). |
| **M3** Preprint + StateCarry v0 | Oct 22-28 | Preprint and blog draft of the ARC path table plus survival accounting (researcher reviews; target post Oct 28). StateCarry v0: PersistGym cell on luna, then dev ARC games. **[A7]** The preprint only, with the researcher's review, posted to arXiv before Nov 2; no StateCarry (§22). | **G3, Oct 28** | Continue to held-out evaluation only if v0 closes ≥ 25% of the S0→S4 gap on dev games at ≤ S4 cost. Otherwise stop the builder and write the analysis paper. **[A7]** G3 is removed (§22). |
| **M4** StateCarry held-out evaluation | Oct 29-Nov 4 | 18 held-out ARC runs; final figures. | **G4, Nov 4** | Claim wording follows the pre-registered win (≥ 50% of gap at ≤ Adapter cost). Otherwise report it as partial or negative. **[A7]** M4 and G4 are removed (§22). |
| **M5** Paper | Nov 5-13 | AGENT 2027 paper (full 8 pages, or short 5; see §13). **[A7]** TMLR, or an AGENT 2027 short paper of 5 pages (§22). | Submit **Nov 13 AoE** | |
| **M6** Extensions | Nov 14-Jan 2027 | E1-E4 as gated; full version for TMLR or an ICLR 2027 workshop. **[A7]** Removed: no extensions (§22). | Per extension | All Gemini ARC runs finish before Dec 31, 2026. |

Human time: about 30-40 h for the MVP and 40-55 h overall. It goes to definitions and pre-registration, shortcut audits, labelling about 100 transcripts, confirming toggles, choosing claims, and writing. Coding agents do the rest. **[A7]** No transcripts are labelled; the time goes to writing (§22).

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
| 1a PersistGym | luna: 3,200-6,400 episodes plus about 1,600 control prompts, at $0.005-0.02 each (Flex) = $25-160. sol core: 640 episodes at $0.05-0.35 = $30-230. Validity runs $10-20. The optional sol H1 replication (+640 episodes, +$30-230) runs only if it fits under the cap. | $65-410 | $450. **[A2]** $500 (§17.3). **[A7]** Cap unchanged; only luna's sweep remains, about $35-71, and the sol replication's main runs are dropped (§22) |
| 1b ARC path | 32 runs. Eligible games average about $31 (S0) and $25 (S4) per run at ARC's no-cache list accounting, so about $900 at list or about $450 with Flex. | $450-900 | $900. **[A2]** Unchanged; Checkpoint C may ask for up to ~$170 more (§17.3). **[A7]** Not raised: 12 counted runs (16 with S1), S2 forecast at about $172-194 (§22) |
| **MVP total** | | **~$0.55-1.4k** | |
| 2 StateCarry | PersistGym cell $10-40; ARC dev ≤ $150; 18 held-out runs $350-750 (two cheap games at ~$30/run, plus VC33 or RE86 at ~$65/run, at list; Flex halves this). **[A2]** Held-out games SP80, VC33, TN36 on the standard tier (§17.1) | $510-940 | $950. **[A2]** $1,250 (§17.3). **[A7]** Phase 2 is not run, so nothing is spent here (§22) |
| **Through phase 2** | | **~$1.05-2.35k** | |
| E1 open weights | 15-50 GPU-hours | $20-80 | |
| E3 Terminal-Bench | cheap model, 90 trials; sandboxes (Modal's $30/month free credit or local Docker) | $100-300 | |
| E4 second ARC model | gpt-6.1-sol, 2-3 games, after a one-game pilot | $200-1,000 | pilot first |
| E5 Kaggle port | Kaggle GPUs free; dev GPU $100-300 | $100-300 | |

This is above the profile's ~$1k flag and ~$200/month cash, and well below the ~$5-10k infeasibility line. **The researcher must approve the phase-1 ARC spend before M1.** **[A1]** Replaced by staged approvals (§16.2). The estimates above are corrected in §16.1. **[A2]** The forecasts in §17.2 replace these estimates, and §17.3 sets the caps. None of this money goes to ARC Prize: the ARC API is free, and the ARC rows are Gemini tokens billed by Google. **[A7]** The project target is about $560 in all, which may run over a little; it is kept through the block limits, and the caps in §17.3 stay as stop-and-ask ceilings (§22).

Cheaper fallbacks, in order:
1. Flex everywhere. **[A2]** No longer a fallback: OpenAI already runs on Flex (D13), and ARC stays on the standard tier (D21). The ARC fallbacks are 3 games, then medium thinking.
2. 3 ARC games. **[A7]** Not used: when Checkpoint C's cost rule fired, the researcher chose seed 1 only, keeping all 4 games (§22).
3. Medium thinking. The published medium gap is 20pp.
4. Fewer sol templates (30). **[A2]** Under D11 option A this means a lower T_d (§17.1). **[A3]** T_d = 210 is not lowered without a further PREREG amendment (§18).

## 13. Venues
Dates were checked against the `ai-research` deadlines file (verified 2026-09-29) and the linked pages.

| Venue | Deadline | Type | Use here |
|---|---|---|---|
| arXiv preprint + blog (dev.to, LinkedIn, Bluesky) | Target **Oct 28** (ARC path table + survival accounting); update Nov 13 | Preprint | Establishes priority. OpenAI, ARC Prize and several groups are active (see the scoop risks in `docs/premise-check.md`). The researcher reviews the exact text and posts it. **[A7]** Target: before Nov 2, ahead of the Kaggle ARC-AGI-3 teams' writeups (§22). |
| [AGENT 2027 @ ICSE](https://conf.researchr.org/home/icse-2027/agent-2027) | **Nov 13 AoE**. The workshop page says Nov 27; ICSE says Nov 13 for all workshops. Plan for Nov 13. | Archival IEEE workshop; full 8 pages or short 5; single-anonymous; no AI policy stated | Main target. Archival: if a later ML main-track version is planned (ICML 2027, deadline TBA, last year late January), submit a **short 5-page** version or go non-archival instead. **[A7]** A short 5-page paper is one of the two targets after the preprint. AGENT is archival, so TMLR's prior-publication policy is checked before doing both (§22). |
| [ICSE 2027 Industry Challenge](https://conf.researchr.org/track/icse-2027/icse-2027-industry-challenge) ("Agent Memory in the Wild: Reliability, Efficiency, and Evaluation") | Nov 13 AoE | 5-10 pages + 2 | Possible alternative to AGENT. Read the challenge statement first. It cannot take the same paper as AGENT. |
| [ICLR 2027 workshops](https://iclr.cc/Conferences/2027/CallForWorkshops) | ~Feb 1, 2027 (CFPs after Nov 29) | Non-archival | Full version with extensions. ICLR 2027 requires an AI-use statement at the main conference; check each workshop CFP. |
| [TMLR](https://www.jmlr.org/tmlr/) | Rolling | Journal | Full version. LLMs are allowed as assistive tools. **[A7]** One of the two targets after the preprint (§22). |
| [ARC Prize 2026 Paper Track](https://arcprize.org/competitions/2026/paper) | Papers **Nov 8** (arcprize.org) / Nov 9 23:59 UTC ([Kaggle](https://www.kaggle.com/competitions/arc-prize-2026-paper-track)); plan for Nov 8. Needs an [ARC-AGI-3 Kaggle](https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3) entry by **Oct 26** and a code submission by **Nov 2**. | Prize: $75K top-3 plus a $375K pool for papers scoring > 4.5/5 | **Conditional (E5).** See the eligibility note below. **[A7]** Skipped (§22). |

**ARC Paper Track eligibility.** A paper "must be linked to a Kaggle code submission (ARC-AGI-2 or ARC-AGI-3 track)". The submission "need not achieve a high score". Kaggle evaluation is offline, with no API models. So the API-model analysis alone is **not eligible**. It becomes eligible only if we also submit an offline open-model agent, e.g. Qwen3.6-27B with `preserve_thinking`, or StateCarry on a Milestone-1 open harness, within Kaggle's GPU and ~9h notebook limits.

Other conditions:
- Own code must be CC0 or MIT-0. The design review reports a CC-BY 4.0 winner licence.
- The rubric scores Accuracy (from the Kaggle score), Universality, Progress, Theory, Completeness and Novelty. Accuracy would be weak here.

**Decision P on Oct 19:** **[A7]** Skipped: E1 does not run, so no offline open-model agent exists to make a paper eligible (§22).
- **Go only if all of these hold:** the researcher accepts the licensing and employer-IP implications; the E1 Qwen pipeline works; and there is a clear result worth documenting.
- **Otherwise skip.** The default is skip, because the Kaggle port competes with M4 and M5 for the same two weeks.
- Joining the Kaggle competition, which means accepting its rules, is the researcher's own action and must happen by Oct 26.

## 14. Kill criteria (consolidated)
1. **G0.** No verifiable replay toggle on any API model → H2 runs on open weights only (E1). If E1 also fails, drop H2 and state it as a limitation.
2. **G0.** ARC pilot > $30/run with Flex → 3 games or medium thinking. If it is still > $30/run, drop the ARC runs and keep the free observational analysis. **[A1]** The trigger becomes "forecast billed 1b + re-run reserve > $900 at the chosen tier" (about $23.4/run with a 20% reserve), re-checked at Checkpoint C (§16.2). Medium thinking would need a PREREG amendment, since H4 and the eligibility rule are defined at high effort. **[A2]** The tier is the standard tier and the forecast follows D27 rule 1. A conservative check at Checkpoint C may lead to a request for up to ~$170 more in 1b (§17.1). **[A7]** Checkpoint C's cost check fired on 2026-10-09; the researcher chose seed 1 only, not the listed fallbacks or a 1b raise (§22).
3. **G1.** PersistGym fails the validity gate after one redesign → stop PersistGym and continue ARC alone. **[A7]** No redesign pass: if luna fails G1, PersistGym stops at once (§22).
4. **G2.** S0→S4 gap on the 4 games < 10 RHAE points → kill the ARC path leg. **[A7]** Read on the 4 seed-1 units; the gap (62.59) is already known, so it cannot fire (§22).
5. **G2.** H1 and H2 both inside equivalence bounds, *and* the ARC gap is dominated by a mechanism with no provider-neutral analogue → publish a short note, no builder. **[A7]** Moot: phase 2 is not run, and H2 stopped under A4 (§22).
6. **Any time.** A per-component ablation of ARC's gap appears (ARC Prize, OpenAI or others) → the ARC table becomes supporting material. Lead with PersistGym + StateCarry. **[A7]** Lead with PersistGym; there is no StateCarry (§22).
7. **G3.** StateCarry v0 closes < 25% of the gap on dev games → stop the builder and write the analysis paper. **[A7]** Void: phase 2 is not run (§22).

The card's old rule, "95% CI of the harness × d slope includes 0", is replaced by the equivalence bounds above. With the card's sample sizes, the old rule would have fired even when a true effect exists.

## 15. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Scooped on the ARC leg (ARC Prize adds adapters weekly; OpenAI's July post names the mechanisms) | High | Free analysis in week 1, preprint target Oct 28, ARC table framed as supporting evidence. **[A7]** Preprint before Nov 2 (§22). |
| Scooped on the mechanism leg (TierFlow group: 2609.29875 and StateComp; LOCA-bench group; harness-design study authors) | Medium | Differentiate on recoverability × derivedness, within-template crossed design, survival accounting, and the builder. |
| The StateCarry builder overlaps public ARC Kaggle work. The Duck baseline already has reasoning replay plus a structured world/goal/action block, and 4+ public teams are ablating replay, ledgers and compaction, with results due before Nov 2 | High | Position StateCarry as API-model, Standard-harness, mechanism-driven; cite Duck and the Kaggle ablations; re-check at G2 and G3. If a Kaggle team publishes a Standard-harness gap closure, drop the builder claim and keep the analysis. This also makes E5 (Paper Track) less attractive. **[A7]** Moot: there is no builder (§22). |
| The replay toggle is not what the model actually sees (opaque items; luna may ignore `all_turns`) | Medium | Echo check on every response, payload snapshot tests, open-weights replication with a visible template (E1). |
| The published ARC gap partly reflects harness errors (early-ending Standard runs) | Medium | Log exit reasons, pre-registered re-run rule, report both. |
| Standard-harness API surface for published Gemini runs unknown | Certain | Hold the Interactions API fixed across all our configs and re-measure S0 ourselves. |
| Cost overrun on ARC (runs vary $8-$295 per game; Standard trimming breaks caching) | Medium | Cheap-game rule, Flex, per-phase hard caps, cost logged per run. **[A2]** No Flex for ARC (D21); forecasts and caps in §17.2-§17.3. |
| Price and model changes (Gemini doubles Jan 1, 2027; deprecations) | Certain / medium | Finish ARC runs in 2026; pin versions; record returned model strings. |
| Flex latency, 429s and ARC's 12h wall clock | Medium | Retry with backoff (429s on Flex are not billed); fall back to standard tier for runs that time out, and record it. **[A1]** No per-run fallback: it would tie the tier to run length and config. One tier for all ARC configs, chosen by a pre-registered latency rule from the M0 probes (§16.4). **[A2]** The standard tier for all ARC runs; no Flex (D21, §17.1). |
| **[A1]** Gemini Tier 1 spend cap ($250/month; service pauses for all linked projects until the 1st) | High unless Tier 2 is reached | Researcher moves the billing account to Tier 2 ($100 paid + 3 days) before the seed-1 ARC block; provider-side spend caps back up the stop-and-ask rule (§16.1). |
| **[A1]** Published "gap" partly reflects Standard runs that crashed (e.g. LP85) | Medium | Operational free analysis infers how each published run ended before the draw; our own S0 re-measures the gap (§16.4). **[A2]** LP85 and SC25 are not used (D14 option A, §17.1). |
| Results look like a model quirk, not a mechanism | Medium | Two API models plus open weights (E1); claims stated per component and per state type. **[A7]** Weakened: PersistGym's main sweep runs on luna only, with no sol replication and no E1 (§22). |
| Employer sensitivity (vendor comparisons) | Low | One-off study; no rankings or dashboard; neutral wording; figures by task property; the researcher reviews all public text. |
| Human time is the bottleneck (labelling, definitions) | Medium | Labelling capped at ~100 transcripts; agents build everything else. **[A7]** No labelling (§22). |

## 16. Amendment A1 (2026-09-30): staged low-spend approvals and cost corrections
**Why.** On 2026-09-30 two reviews checked this plan: a fact-check of a plan summary against the files, and a low-spend review that verified provider pricing on the web and re-derived the budget with scripts. The researcher approved starting the $0 work and asked to decide at every major spending point. This amendment records what changed. It changes no hypothesis; `PREREG.md` does not exist yet.

### 16.1 Who gets paid, and corrected costs
**ARC Prize receives nothing.** "The ARC-AGI API is currently free to use during its research preview" ([ARC docs](https://docs.arcprize.org/rate_limits)). Every "ARC" line in §12 is Gemini 3.8 Flash tokens, billed by Google while the model plays ARC games. The preview could end; no terms guarantee it.

**Totals through phase 2**, central case: about 1k output tokens per PersistGym call, 8-cell luna, the mean game draw, moderate re-runs, OpenAI cache writes. These are estimates from published runs and the plan's own assumptions, to be replaced by measured costs after the pilots.

| ARC runs billed at | Total | Google (Gemini) | OpenAI (luna, sol) |
|---|---|---|---|
| Gemini Flex | ~$1.3k | ~$0.85k | ~$0.46k |
| Gemini standard tier with implicit caching | ~$2.0k | ~$1.55k | ~$0.46k |
| ARC's no-cache list accounting | ~$2.4k | ~$1.96k | ~$0.46k |

Everything at list is about $2.9k. A pessimistic case is about $4.0k. Of the totals, $0.65-1.55k falls before G2; phase 2 is a separate approval.

**Corrected line items:**
- **1a PersistGym:** about $230-415, not $65-410. Under §12's assumptions, sol's output alone costs $0.14 per episode at Flex. The sol H2 core (640 episodes) costs about $250 at 1k output tokens per call including cache writes, $360 at 2k and $480 at 3k. The pilots measure this. Phase 1a stays under $450 by sizing (30 sol templates; luna's 4 replay-off cells first).
- **1b ARC path:** $638-1,054 at no-cache list depending on the draw (mean $896). It exceeds $900 exactly in the 6 of 15 draws that contain both R11L and SC25. At Flex it is $319-527.
- **Phase 2 held-out runs:** $597-935 at list, $299-467 at Flex (§12 said $350-750). At list, phase 2 can exceed its $950 cap.
- **Error re-runs** (§8.3 rule) were unbudgeted: add about $60-80 at Flex or $120-160 on the standard tier.
- **sol H1 replication:** about $430-610 at Flex with cache writes, not $30-230. Removed from the MVP.

**Provider facts that change costs or schedule** (checked 2026-09-30):
- OpenAI charges cache writes at "1.25× the standard, uncached input-token rate" on GPT-5.6 and later; cached reads cost 0.1× (0.05× on GPT-6.1 Sol) ([prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)). This adds roughly 10-20% to PersistGym, and more where caches break (window cells).
- OpenAI usage tier 3 ("$100 paid") has a $1,000/month usage limit; hard spend limits make requests return 429 ([rate limits](https://developers.openai.com/api/docs/guides/rate-limits)).
- Gemini spend caps: Tier 1 $250/month, Tier 2 $2,000 ("Paid $100 + 3 days from first successful payment"). At the cap, "service is paused for all projects linked to that billing account until the start of the next billing cycle" ([Gemini billing](https://ai.google.dev/gemini-api/docs/billing)). The docs do not say whether prepaid credit counts as "paid".
- Gemini Flex latency: "Minutes (1–15 min target)", with "No server-side fallback" to the standard tier ([Flex](https://ai.google.dev/gemini-api/docs/flex-inference)). ARC runs are 60-400 sequential calls under a 12h clock, so Flex may not fit.
- Gemini 3.8 Flash defaults to medium thinking ([thinking](https://ai.google.dev/gemini-api/docs/thinking)); `thinking_level: high` must be set explicitly.

### 16.2 Staged spending approvals
This replaces "the researcher must approve the phase-1 ARC spend before M1" (§12). Each block needs the researcher's explicit approval, recorded in `results/decisions.md`. Approving one block never carries over to the next.

| Block | When | Estimate | Paid to | What it buys | Decides |
|---|---|---|---|---|---|
| Stage 0 | now to ~Oct 3 | $0 | nobody | Operational free ARC analysis; PREREG and the seeded draw; ARC fork patches and payload snapshot tests; offline ARC games with a stub model; PersistGym build and $0 validity checks; cost model and power re-simulation | Inputs to every later block |
| 1. Pilots | after PREREG is committed and snapshot tests pass (~Oct 3-7) | ~$42-76 | OpenAI ~$26-47, Google ~$16-29 | OpenAI `reasoning.context` echo check (~$0.35); replay-use probe (~$2); Gemini payload acceptance and Flex latency probe (~$3); truncated ARC pilot on one drawn path game (~$13 Flex / $26 list); luna and sol pilots and validity runs | G0 (Oct 7) |
| 2. Seed-1 S0+S4 | after G0 (Oct 8-12) | $62-132 at Flex or $125-263 on the standard tier, plus up to $60 of re-runs | Google | 8 counted runs on the 4 drawn games: the first fresh-seed gap, real run cost, and how runs end | Checkpoint C |
| 3. Commitment | Checkpoint C (~Oct 12; latest G1, Oct 14) | +$0.54-0.79k at Flex or +$0.76-1.15k on the standard tier (up to $1.37k at no-cache list) | Google, OpenAI | The other 24 ARC path runs plus reserve; the PersistGym main sweep | G2 (Oct 21) |
| 4. Phase 2 | G2 / G3 | ~$0.46-1.1k | Google, OpenAI | StateCarry dev and held-out runs | G3, G4 |

**Checkpoint C** (new; pre-registered in `PREREG.md`). Propose stopping or re-scoping the ARC leg if any of these holds after block 2:
- the seed-1 mean S0→S4 gap is below 5 RHAE (looser than the G2 kill at 10, because one seed is noisy);
- more than 3 of the 8 runs still end in an error after one re-run;
- measured cost per run × 24 × (1 + measured re-run rate) exceeds the remaining 1b cap on the chosen tier.

If it continues, seed-1 S1+S2 and all of seed 2 run as one wave, so the four configs are compared over the same days (Gemini 3.8 Flash has no dated snapshot).

### 16.3 M0 changes
- **PREREG before any paid call.** Commit `PREREG.md` (target Oct 3) before the first paid pilot, not at the Oct 7 gate.
- **Free analysis in two slices.**
  - *Operational slice, before PREREG:* how each published run ended (inferred from per-level action budgets, since exit reasons are not published), seconds per action, cost per action, cached share, a clean-run cost upper bound per game, and a recount of the "11 of 25 early endings". These set the eligibility decision, the cost guard and the re-run reserve.
  - *Hypothesis slice, after the PREREG commit:* H5's per-level P(clear | reached) by harness, plus any exploratory event studies.
- **Draw first.** Run the seeded draw at the PREREG commit, as a permutation of the 6 eligible games: the first 4 are path (dev) games, the last 2 are held out. Never pilot on a held-out game.
- **Truncated ARC pilot** on one drawn path game replaces the FT09 full-run pilot: S0 and S4 to 50 actions, S1 to its first compaction plus 5 turns, S2 to 30 actions. FT09 is one of the two shortest eligible games, so it says little about run cost.
- **G0 cost rule:** forecast billed 1b + re-run reserve ≤ $900 at the chosen tier (about ≤ $23.4/run with a 20% reserve). The old "≤ $30/run" rule allowed 32 × $30 = $960.
- **G0 toggle rule** adds a replay-use probe (~$2). Turn 1 asks the model to privately pick a 3-digit number and reply only "ready"; turn 2 is filler; turn 3 asks for the number. Both arms send identical payloads; only `reasoning.context` differs. Chance is 1/1000. The probe is excluded from all analyses.
- **$0 local ARC testing.** ARC's official `arc-agi` toolkit downloads the public games once and then runs them offline. With a stub model, full S0-S4 games can run end to end at $0 to test patches, compaction, per-level stops and logging. Local play is for testing only; counted runs stay on ARC's online scorecard.
- **Extra harness patches,** kept as files in `arc/`: `exit_reason` written into `run_meta.json`; `service_tier` pass-through; transport-level 429/503 backoff that does not use up `MAX_RETRIES`; an optional per-run cost guard (exit `COST_CAP`; the researcher decides whether it is an acceptable, reported deviation); an offline/local-server mode for testing only.
- **PersistGym build pulled into M0** as far as possible; the generator, not money, is the critical path to G1. Add $0 validity checks: a programmatic shortcut audit, and no-memory heuristic baselines (most frequent option, last-seen option) that must score ≤ chance + 10pp.

### 16.4 ARC design changes
- **One service tier for all ARC configs,** chosen by a pre-registered latency rule from the M0 probes. No per-run fallback (§15 updated).
- **Frozen configs.** S0-S4 config hashes are frozen in `PREREG.md` before the seed-1 runs, so S0/S4 results cannot steer the S1/S2 patches.
- **Eligibility caveat.** The "both published runs ≤ $60" filter can select Standard runs that were cheap because they crashed. Example: the published LP85 Standard-high run cleared 7 levels, then stopped on level 8 after 16 of 795 allowed actions, about 1 h 56 min after opening, with state `NOT_FINISHED`. Level 8 carries 8/36 of the score, so this ending accounts for LP85's whole 22.2-point gap. A complete run could cost up to about $168, not $24. After the operational slice and before the draw, the researcher decides whether to keep or amend the rule; a change shrinks the pool and the held-out set.
- **Optional for phase 2:** run the held-out S0+S4 runs before the StateCarry held-out runs, and pre-register a minimum gap for the StateCarry runs to proceed.

### 16.5 Also to fix in `PREREG.md` (beyond the §4 definitions)
- The draw seed and permutation; the third held-out game (VC33 or RE86).
- Explicit settings: Gemini `thinking_level: high`; luna/sol `reasoning.effort` (medium proposed, the documented default; **[A3]** sol at high if its engagement check passes, §18) and `reasoning.mode: standard`; `reasoning.context` always set explicitly.
- The tier latency rule, the cost-guard value, the re-run reserve, and whether `TIME_BUDGET` endings are re-run.
- The Checkpoint C rules (§16.2).
- **Pilot blinding:** pilots report only validity levels, pooled tokens, errors, latency and cost; never per-arm success, per-arm reasoning tokens (H2's token outcome) or per-config ARC level progress. Pilot templates use a disjoint seed range.
- **Cost basis** for the StateCarry win and G3/G4: ARC no-cache list, billed with caching, or both with one primary. The basis can flip the comparison (high effort: about $80 vs $82 at list, about $74 vs $53 billed). StateCarry's own calls count toward its cost.
- A numeric meaning for "dominated" in kill criterion 5.
- How a game is dropped under the 3-game fallback (seeded, not by cost).
- "Far" defined by observation tokens alone, so eviction does not depend on reply length; survival checked against the payload actually sent.
- H1's non-recoverable arm reported as a manipulation check; the confirmatory test is the difference of penalties.
- W, v and template counts stated as tuning rules applied in M1, not as fixed numbers. The M1 power re-simulation also sizes sol templates for H2's ±8pp equivalence test.

### 16.6 Facts updated (sources go into `docs/background.md`)
- The ARC API key is free and unlocks all 25 public games; the limit is 600 requests per minute.
- The pinned harness hard-codes online play (`swarm.py`); local play needs a one-line patch or a local server. This is read from the code, not yet run.
- Exit reasons are never sent to ARC; published runs show only a game state.
- The harness `main` moved to `09a307b` on 2026-09-30 (two merged PRs: a Grok 4.7 adapter with streaming, and the DeepSeek adapter). Neither touches `agent.py`, `base.py`, `swarm.py` or the Gemini/OpenAI runtimes, and neither is a per-component ablation. The pin stays at `4ca00e6`; check whether the 6-line `compaction.py` change is needed for S1.
- OpenAI's docs list only GPT-5.6 models and GPT-6.1 Sol for `all_turns`; Microsoft's Azure docs say all GPT-6 models including luna. The echo check decides. Neither luna nor 6.1-sol has a dated snapshot ID, so the returned model string is the pin.

### 16.7 Process
- All changes land through pull requests; the researcher merges.
- The researcher is consulted before every paid block (§16.2) and before any cap is exceeded.

## 17. Amendment A2 (2026-10-01): researcher decisions before the PREREG freeze
**Why.** On 2026-10-01 the researcher decided the open items (D1-D39) of the `PREREG.md` draft. Several decisions change this plan. This amendment records them before `PREREG.md` is frozen. No paid call has been made. No hypothesis or threshold changes, but two decisions change how a prediction is read: D8 (H1's token clause) and D11 (H2's observed-fact check now uses far cells only). `PREREG.md` records the final wording of every D item; this section covers only what changes the plan. §16 is left as written; §17.5 lists the parts of it that A2 replaces.

**Where the numbers come from.** Every cost, ops and power figure below is in a committed file, written by a committed script, in a run folder with a `meta.json`:
- `results/arc_public_ops/20261001T185155Z/` (`arc/public/ops.py`, PR #17): `summary.md` and `recordings_per_action.csv`.
- `results/cost_model/20261001T203318Z/` (`analysis/cost_model.py`): the `optA_*.csv` files and `option_a_summary.md`. This run replaces PR #17's `20261001T185959Z` for every option-A number. It prices luna's controls per D36, sizes sol for T_d in {90, 120, 150, 180, 210} and uses the $1,250 phase 2 cap. Its ARC costs and all of its A1 tables are identical to that run's; in `optA_forecasts.csv` only the phase 2 cap and headroom columns change.
- `results/power_sim/20261001T190327Z/h2_sol_power.csv` (`analysis/power_sim.py`, PR #17).

All costs are in USD. The billed estimate comes first; ARC's no-cache list cost is in parentheses where both are given. These are forecasts from one published run per game and harness. They are not measured costs of our configs.

### 17.1 Decisions
**D14 option A: ARC games fixed by rule, with no draw** (§8.3, §9).
- A **normal ending** is `GAME_WIN`, `ACTION_BUDGET` or `TIME_BUDGET`, as the operational slice infers it; the other inferred ending, `ERROR_OR_CLOSED`, is not normal (ops `summary.md`).
- Path (dev) games: public games where both published high-effort runs cost ≤ $60, the published gap is ≥ 20 and the published Standard-high run ended normally. These are FT09, SB26, R11L and CD82: the §8.3 eligible games without LP85 and SC25, whose published Standard-high runs ended `ERROR_OR_CLOSED` (ops `summary.md`).
- Held-out games: SP80, VC33, TN36. The rule: among the remaining public games with a published high-effort gap ≥ 20 and a normal Standard-high ending, keep the 3 with the lowest max(published Standard cost, published Adapter cost). Their published list costs (Standard / Adapter) are $29.21 / $66.72, $86.99 / $39.70 and $42.87 / $90.89 (ops `summary.md`, the D14 line under the eligibility table). The next game by this rule is SU15 ($100.0 / $48.5, Standard-high ended `TIME_BUDGET`); RE86 is excluded by its `ERROR_OR_CLOSED` ending.
- Path and held-out games are no longer exchangeable. The held-out games come from a separate cost rule, and none of the three meets the $60 filter (eligibility table), which is why they are not path games.
- LP85 and SC25 are neither path nor held-out games. No pilot runs on a held-out game.

**D15: beacon seed after the freeze.** The seed comes from the first NIST Randomness Beacon pulse at least 10 minutes after the freeze commit, with drand as the fallback (`arc/draw_games.py`, PR #16). The games are fixed, so the seed picks no games. It picks the truncated-pilot game (`perm[0]` of the 4 path games), the game dropped under the 3-game fallback (`perm[3]`) and the run orders (D18).

**D11 option A: sol runs far cells only** (§4 H2, §7).
- sol runs F-r vs F-0 on the derived-far cells (recoverable and not) on T_d templates. It runs the observed-far cells (recoverable and not) on the first T_o = T_d/3 of them. sol runs no near cells.
- T_d is always a multiple of 30 and T_o = T_d/3, so T_o is a multiple of 10 and every 10-template balance block is whole (D7).
- Planning value: T_d = 120, T_o = 40. That is 320 template-cells per arm, as many as PLAN's 40 templates × 8 cells. With the 10% repeats it is 704 sol episodes (`optA_sizing_1a.csv`).
- **Ceiling: T_d = 210** (T_o = 70), set by the researcher on 2026-10-01. A raise above the planning value may be decided only before the sol main sweep starts and before any H2 outcome has been computed. T_d never changes after that.
- A T_d that the 1a cap in force does not afford also needs the researcher to raise the 1a cap first (the stop-and-ask rule). At 1k output tokens per call with 8 luna cells, $500 affords T_d = 120 at most; T_d = 210 comes to 699.16 (§17.2).
- The 0.80 power target stays. If the 1a cap does not afford it (for example because calls run longer than 1k output tokens), sol uses the largest affordable T_d, the achieved power is reported, and a sol result that is neither equivalent nor falsified is called inconclusive (§17.2).

**Power of this design** (`h2_sol_power.csv`). Each row is 1,000 simulated runs, with template SD 1.0 on the logit scale and success under F-0 (p_F0) of 0.6 or 0.8. No variance has been measured yet. H2's derived-far success effect is tested with a one-sided bootstrap test at α = 0.0125, the strictest step of the 4-test Holm family (D26).

| T_d (T_o) | 90 (30) | 120 (40) | 150 (50) | 180 (60) | 210 (70) |
|---|---|---|---|---|---|
| Power at a true +8pp, p_F0 = 0.8 | 0.463 | 0.606 | 0.695 | 0.799 | 0.870 |
| Power at a true +8pp, p_F0 = 0.6 | 0.308 | 0.414 | 0.489 | 0.537 | 0.645 |
| TOST equivalence (±8pp) at a true 0, p_F0 = 0.8 | 0.348 | 0.539 | 0.655 | 0.764 | 0.866 |
| TOST equivalence (±8pp) at a true 0, p_F0 = 0.6 | 0.074 | 0.278 | 0.378 | 0.542 | 0.675 |

- Every column is an allowed T_d; 210 is the ceiling.
- Size at a true 0: 0.010-0.018.
- "Supported" (the bootstrap test rejects and the GLM estimate is positive) equals the bootstrap power in every row.
- False equivalence at a true +8pp: 0.028-0.063.
- Mean 90% CI half-width of the derived-far effect: 3.9-7.7pp.
- Observed-far cells at a true 0: the point estimate is within 3pp in only 0.207-0.543 of runs, and the 90% CI half-width is 7.2-13.0pp. So H2's "less than 3pp on observed facts" point check often fails by chance alone.

**D7: seeds and repeats** (§5).
- Template seeds: main [0, 50,000), validity [50,000, 60,000), pilots [90,000, 100,000). Runs start and end at multiples of 10, so every 10-template balance block is whole.
- The 10% repeat subset of §5 stays on **both** luna and sol: every template whose seed is a multiple of 10 runs a second time. The proposal to repeat on luna only is rejected. On sol, at T_d = 120 and 1k output tokens per call, the subset costs $24.85 (`optA_sizing_1a.csv`).

**D8: H1's token reading** (§4 H1).
- Primary: need-phase tokens N. N is provider-reported input (cached included) plus output (reasoning included), summed over every call made while the need step is pending, lookups included. "Total tokens rise by at least 30%" is read as R_need = [N(W-0, far) / N(F-0, far)] / [N(W-0, near) / N(F-0, near)] ≥ 1.30, in the observed, recoverable cells.
- Secondary, reported alongside: R_tok, the same ratio with whole-episode tokens, and the literal ratio T(W-0, far) / T(F-0, far).

**D2: clustered options** (§5).
- For a derived fact, the K = 10 options are one cluster of evenly spaced values around the true value (spacing 1, i.e. consecutive values, in generator 0.2.0, PR #15). With the rule and any proper subset of the clues, every option stays possible, so partial memory gives no edge.
- New $0 check in every derived cell: no template where a proper subset of the clues narrows the options, and partial-memory heuristics score ≤ 20% (chance + 10pp).

**D36: run matrix** (§5, §7, §12).
- luna runs the restated-at-need control as full F-0 episodes on all 8 task cells, not as single prompts.
- luna runs the position-matched single-turn control on the 4 non-recoverable task cells only.
- sol runs F-r vs F-0 on the D11 cells only.
- The forecasts in §17.2 price the controls this way, including the D7 repeats.

**D21: Gemini standard tier for all ARC runs** (§8.3, §15).
- All ARC runs, pilots included, use Gemini's standard tier. Flex is not used for ARC, and runs never switch tier.
- Block 1's Flex latency probe is dropped; a standard-tier payload acceptance check takes its place.
- Warning rule, per run: before each block, the researcher is told if any planned run's 1.5 × published actions × published seconds per action exceeds 12 h. Among the published runs of the 7 games, only VC33's Standard-high run (10.39 h; ops `summary.md`) trips it, so VC33's S0 runs in phase 2 will be flagged.
- OpenAI runs stay on Flex (D13).

**D20: `TIME_BUDGET` is final** (§8.3).
- A `TIME_BUDGET` ending is scored as is, flagged and not re-run.
- The exception is a provider-latency incident: the run's median seconds per model call is more than 2× the median of the same config's earlier counted runs, or the pilot's median if there is no earlier counted run. Then the run is re-run once, like an error.

**D23: cost basis** (§9).
- The billed estimate is primary: provider-reported tokens at the prices of the tier used (the standard tier for ARC), with cached input at the cached price. ARC's no-cache list cost is reported alongside.
- This applies to the StateCarry win, G3 and G4. The forecasts in §17.2 use the same basis. How the paid guard measures spend against the caps is still open (§17.4).

**D24 option B: all 3 held-out games** (§9, §12).
- Phase 2 commits to all 3 held-out games: 3 games × {S0, S4, S0+StateCarry} × 2 seeds = 18 runs. There is no conditional cut to 2 games.
- The 4 G3 runs (frozen StateCarry v0, once per dev game) are their own phase-2 budget line, outside the $150 dev cap (§9 step 2). The phase 2 forecast in §17.2 prices them that way.
- The phase 2 cap rises from $950 to $1,250 (§17.3). A2 first proposed $1,150; on 2026-10-01 the researcher set $1,250, which covers the central forecast with its reserves.
- The rest of D24 is recorded in `PREREG.md`: closure as a ratio of means, the held-out S0 and S4 runs first, the StateCarry held-out runs only if the held-out gap is ≥ 10 RHAE, and the G4 bands.

**D27 rule 1: cost forecasts** (§11 G0, §14 item 2).
- G0 prices S1 and S2 at the midpoint of S0 and S4 for each game. Go on cost iff the 1b forecast plus the 20% re-run reserve is ≤ $900, billed at the standard tier.
- Checkpoint C adds a conservative check on the remaining 24 runs. Seed-2 S0 and S4 are priced at their measured seed-1 costs per game, and S1 and S2 at the measured S0 cost per call × the larger of the measured S0 and S4 actions, plus the re-run allowance. If this exceeds the remaining 1b cap, a 1b cap increase of up to about $170 may be requested at Checkpoint C. The researcher decides.

**Approval lines for paid blocks** (§16.2).
- A paid block spends only after the researcher merges one line into `results/decisions.md` on `origin/main`, of the form `approved_block: <name> | experiments: <list> | max_usd: <n>`.
- The paid guard reads the line and never writes one. The exact grammar is at the top of `results/decisions.md` (PR #13).

**Technical choices accepted** (not D items).
- S1 and S2 never drop old turns; they only summarize (patch 0016).
- S0 keeps `thinking_summaries: auto`, so the request is the same along the path. S0-S2 never send the summaries back (`arc/README.md`).
- Transport-level retry with backoff is on in every ARC config (patch 0009).
- Pilot outcomes are written only to the gitignored `results/raw/` (PR #13).
- Paid approvals use the line above.

**All other D items:** the researcher accepted the recommendation. `PREREG.md` records them.

### 17.2 Forecasts behind the decisions
**ARC cost per run, by game** (`optA_arc_run_costs.csv`, from `recordings_per_action.csv`):

| Game | Role | Billed S0 / S4 | List S0 / S4 |
|---|---|---|---|
| FT09 | path | 27.70 / 3.44 | 28.73 / 8.01 |
| SB26 | path | 23.55 / 12.67 | 29.32 / 17.01 |
| R11L | path | 47.93 / 24.46 | 54.75 / 34.99 |
| CD82 | path | 9.48 / 19.91 | 11.68 / 29.01 |
| SP80 | held-out | 25.85 / 39.13 | 29.21 / 66.72 |
| VC33 | held-out | 77.75 / 21.10 | 86.99 / 39.70 |
| TN36 | held-out | 37.69 / 67.37 | 42.87 / 90.89 |

**Ops check** (`summary.md`). There are 20 recordings over 10 games. The recorded costs for SP80 and TN36 match the premise table. Per-level actions re-derived from the recordings match the published sessions in 20 of 20 runs.

**ARC forecasts** (`optA_forecasts.csv`). Billed (list), with the 20% re-run reserve unless noted:
- Block 2 (seed-1 S0+S4, 8 runs): 202.97 (256.19). Without the reserve: 169.14 (213.49).
- G0 forecast for 1b (D27 rule 1): 811.86 (1,024.75) against $900. That is $25.37 per counted run. The billed headroom is $88.14.
- Checkpoint C conservative forecast for 1b: 1,042.92 (1,251.80). On the billed basis, this rule would ask for a 1b cap increase of $142.92, within the ~$170 that D27 lets Claude request (the researcher still decides).
- Held-out, 18 runs: 967.98 with S0+StateCarry priced at the midpoint; 1,381.11 at the Checkpoint C rule.
- G3, 4 runs: 101.48 at the midpoint; 159.25 at the Checkpoint C rule.
- Phase 2, central (1k output tokens per PersistGym call): 1,233.19. That is $16.81 under the $1,250 cap. Without the G3 and held-out reserves it is 1,054.94. At the Checkpoint C rule it is 1,704.09, $454.09 over the cap.

**luna controls (D36)** (`option_a_summary.md`; 1k output, Flex with cache writes). Restated-at-need is 880 full F-0 episodes (100 templates plus the 10 repeat templates, × 8 task cells): 17.29. The single-turn control is 440 prompts (110 × 4 non-recoverable task cells): 1.43. Together 18.72, where the earlier forecast priced PLAN §12's 1,600 single prompts at 5.20. Whether controls get the D7 repeat is not settled; pricing them with it is the conservative choice. A restated-at-need episode is priced like a main F-0 episode; its slightly longer need observation is not priced.

**Totals by phase** (`optA_totals_by_phase_payee.csv`; billed; OpenAI on Flex with cache writes). Phase 0 / 1a / 1b / 2:
- 1k output tokens per call: 24.15 / 494.18 / 811.86 / 1,233.19. Total 2,563.38, of which Google 2,054.00 and OpenAI 509.37.
- 2k: total 2,779.00, with 1a at 702.01.
- 3k: total 2,994.16, with 1a at 909.37.
- ARC at list, 1k: total 3,123.20.
- luna's 4 replay-off cells only, 1k: 1a is 413.02.

**Approval blocks** (`optA_approval_blocks.csv`; billed, 1k): block 1, 53.90; block 2, 202.97; block 3, 1,073.32; block 4, 1,233.19. Blocks 1-3 (through G2): 1,330.19.

**Phase 1a sizing** (`optA_sizing_1a.csv`; 1k output, 8 luna cells, repeats on luna and sol, luna controls per D36):

| T_d (T_o) | 1a total | sol repeat subset | Within $500 |
|---|---|---|---|
| 90 (30) | 425.85 | 18.63 | yes |
| 120 (40) | 494.18 | 24.85 | yes |
| 150 (50) | 562.51 | 31.06 | no |
| 180 (60) | 630.83 | 37.27 | no |
| 210 (70) | 699.16 | 43.48 | no |

- The largest T_d whose 1a fits $500 (`option_a_summary.md`): with 8 luna cells, 120 at 1k output tokens per call and none at 2k or 3k; with 4 luna cells, 150 at 1k, 90 at 2k and none at 3k.
- With 4 luna cells at 1k, T_d = 150 comes to 481.34.
- At T_d = 120 and 2k output tokens per call, even 4 luna cells cost 585.18, over $500. D11's sizing rule then lowers T_d (§17.1).

### 17.3 Phase caps
| Phase | Cap before A2 | Cap from A2 | Basis |
|---|---|---|---|
| 0 | $100 | $100 | Unchanged |
| 1a | $450 | $500 | Approved by the researcher, 2026-10-01 |
| 1b | $900 | $900 | Unchanged; Checkpoint C may ask for up to ~$170 more (D27) |
| 2 | $950 | $1,250 | D24 option B; amount approved by the researcher, 2026-10-01 |

- `PHASE_CAPS` in `common/costs.py` matches this table, and a test checks that it does.
- **Where $450 came from.** §12 set it just above the original 1a estimate of $65-410. A1 re-costed 1a at about $230-415 and kept $450 by sizing (§16.1). It is a stop-and-ask line, not a provider limit. The provider limits are OpenAI's tier-3 usage limit of $1,000 per month and the project spend limits the researcher set on 2026-10-01, whose amounts are not recorded in the repo (`results/decisions.md`).
- **Why $500.** The 1a forecast at T_d = 120, 8 luna cells and 1k output is 494.18. That includes $24.85 for sol's repeat subset and $18.72 for luna's controls under D36. It does not fit under $450, and it leaves $5.82 under $500.
- **Why $1,250.** Phase 2's central forecast is 1,233.19 with the 20% reserves on the G3 and held-out runs, above A2's first proposal of $1,150. $1,250 leaves $16.81. At the Checkpoint C rule phase 2 is 1,704.09, so block 4's approval uses measured costs.
- The stop-and-ask rule is unchanged: Claude stops and asks the researcher before any cap is exceeded.

### 17.4 Open after A2
- **How the guard measures spend.** `common.costs.headroom`, and the paid guard built on it, counts the larger of list and billed spend. On OpenAI Flex, list is twice billed (`harnesses/pricing.py`), so the guard would stop phase 1a at about half its billed forecast. For ARC rows it depends on what `cost_usd_list` will hold; no ARC costs writer exists yet. Before block 3, the researcher decides whether caps are measured on billed spend, as the forecasts here are (D23). PR #19 (open) proposes the billed estimate.
- **1a has little headroom.** At the central size, 1a is $5.82 under its cap. If calls run longer than 1k output tokens, D11's sizing rule lowers T_d (§17.2 lists the largest T_d that fits), luna runs only its 4 replay-off cells, or both: at 2k output tokens per call no allowed T_d fits with 8 luna cells, and with 4 luna cells only T_d = 90 fits. Which gives way first is not yet stated: the `PREREG.md` draft (PR #4, §4.6) runs luna's replay-on cells only if the 1a cap allows, and §17.1 gives sol the largest affordable T_d. The block 1 pilots measure tokens per call before block 3 is approved (§16.1, §16.2).
- **Controls and the D7 repeat.** `PREREG.md` does not say whether the controls get repeat 1. The forecast assumes they do, which adds 10% to the two control lines (conservative).
- **`PREREG.md` follows A2.** The draft (PR #4) still has the D11 ceiling at 200 with T_o = 67, T_d = 210 "for reference only", 1a $500 as proposed and the phase 2 cap at $1,150. It is updated to the ceiling 210, T_o = T_d/3 always, and caps of $500 and $1,250 before the freeze.

### 17.5 Parts of §16 that A2 replaces
§16 stays as written. These parts of it no longer apply:
- §16.1, "Phase 1a stays under $450 by sizing (30 sol templates; luna's 4 replay-off cells first)": the 1a cap is $500, and sol is sized by T_d (§17.1, §17.3).
- §16.1, the totals table and the phase 2 held-out line, and §16.2's block estimates: §17.2 replaces them.
- §16.2, block 1: the Flex latency probe is dropped (D21).
- §16.2, Checkpoint C's cost rule: S1 and S2 are priced by D27's conservative rule, and a 1b cap increase of up to ~$170 may be requested.
- §16.2, approvals "recorded in `results/decisions.md`": an approval is now the researcher-merged `approved_block` line (§17.1).
- §16.3, "Draw first" and the drawn path game for the truncated pilot: there is no draw. The pilot game is `perm[0]` of the fixed path games (D14, D15).
- §16.3, the G0 cost rule "at the chosen tier": the standard tier, with D27 rule 1.
- §16.4, "One service tier for all ARC configs, chosen by a pre-registered latency rule": the standard tier (D21).
- §16.4, the eligibility caveat: decided by D14 option A.
- §16.5: the draw seed and permutation, the third held-out game, the tier latency rule, `TIME_BUDGET` re-runs and the cost basis are decided (D14, D15, D20, D21, D23).

## 18. Amendment A3 (2026-10-02): sol's reasoning effort and template count
**Why.** On 2026-10-02 the researcher decided two changes to sol's H2 runs after block 1's pilots (`results/decisions.md`). `PREREG.md` §17.2 (amendment R2) registers them, with the rule and the code that enforce them; this section only points there.
- **Effort.** sol runs H2, its validity run and its exploratory replay pairs at `reasoning.effort: high`, but only if a blinded engagement check of pooled reasoning tokens at evidence steps passes a rule fixed in advance: at medium, block 1's sol pilot reported 115 reasoning tokens over 360 calls, too little reasoning for replay to carry, so H2 would be a weak test. luna stays at medium (§7, §16.5).
- **Template count.** sol's T_d is fixed at its ceiling of 210 (T_o = 70; 1,232 episodes with repeats), because block 1 measured costs far below the forecasts at medium effort and T_d = 210 gives more power than the central 120 (§5, §17.1 D11). The engagement check measures the cost at high; if the phase-1a forecast at high exceeds the 1a cap, the researcher raises the cap first. The sol main sweep still needs its own approval in block 3.

## 19. Amendment A4 (2026-10-02): a derived-fact variant for sol, with a hard stop
**Why.** sol's engagement check (§18; `PREREG.md` §17.2) found NOT_ENGAGED: none of the 20 evidence-step calls, pooled over both arms, reached 32 reasoning tokens at high effort. On 2026-10-02 the researcher chose option (c) with both levers and a hard stop (`results/decisions.md`). `PREREG.md` §17.3 (amendment R3) registers it, with the rule and the code that enforce it; this section only points there.
- **The variant (sol only).** A derived fact is still a plain sum of 2-3 clues, but each clue's value is never printed: its record gives it through a two-hop relay over helper entities (an anchor value, a far and a near difference, and a decoy), so resolving a clue takes two 3-digit operations (the units digits alone pick the option, so it does not force multi-step reasoning). Each evidence step adds a notice that the value will be requested later and asks the agent to work it out now and not write it. Options, clue values and every other template value are generator 0.3.0's. luna's config and episodes are unchanged.
- **The check.** The same engagement check and rule as §18, on the variant: if reasoning engages, sol's validity run follows on the variant, and G1 applies to it.
- **Hard stop.** If the check fails (or is unscorable twice), or G1 fails on the variant, H2 on sol stops for good and is reported as not testable in this task family; no further variant or effort is tried.
- **What it does not show.** H2 on the variant tests the replay of state the model was told to compute and keep private, which is narrower than incidental state and less like ARC.

## 20. Amendment A5 (2026-10-03): a pre-registered sol replication of H1
**Why.** On 2026-10-03 the researcher asked for a small amendment that pre-registers H1's replication on sol now, before any H1 data exists, whatever happened to H2 (`results/decisions.md`). The same morning sol's engagement check on the variant found NOT_ENGAGED, so H2 on sol stopped under A4's hard stop (§19). Without this replication, PersistGym would have no evidence on gpt-6.1-sol. `PREREG.md` §17.4 (amendment R4) registers it, with its gate and the code that enforces them; this section only points there.
- **The replication.** gpt-6.1-sol at medium effort on the default generator config (luna's episodes), in F-0, W-0 and W-n-0 on the 4 observed task cells, with luna's main-sweep template count (about 100; 1,320 episodes at T = 100 with the repeats). It re-instates §4's "Replication on gpt-6.1-sol if the budget allows", which A1 removed on cost (§16.1). **[A7]** Its main runs are dropped for budget, after its pilot and validity runs and before any main-split episode; it is reported as pre-registered, not run (§22).
- **Status.** Reported next to luna's primary H1 result, with the same estimands, predictions and thresholds, outside the Holm family. It neither confirms nor kills H1; luna stays primary. A2's, A3's and A4's rules for sol concern H2 and do not block it.
- **Pilot and gate.** A pilot of W-0 and W-n-0 on sol (16 episodes), then its own validity gate (F-0, 160 episodes on the 4 observed task cells; restated ≥ 85%, withheld ≤ 20%). If sol fails the gate, the replication does not run.
- **Cost.** About $279 billed at T = 100 on the central forecast from block 1's measured rows, of which window cells, which lose about half of their caching, are about $239; $81 on the lower basis first proposed. Phase 1a then comes to about $319 of its $500 cap (`results/cost_model/20261003T071449Z/`). The pilot and validity runs go in block 1 if they fit, the main runs in block 3 after the confirmatory rows; no new approval.
- **What it does not show.** Two models of one provider's family, at medium effort only. It is not a model comparison: each model's results are effects against task properties.

## 21. Amendment A6 (2026-10-07): action-matched secondary readings for the ARC path study
**Why.** In block 2's first two runs (`results/decisions.md`, 2026-10-07), ARC's 12 h clock bound the Standard config's run but not the Adapter's. Run 2 (FT09 S0) ended `TIME_BUDGET` at 236 actions, about 184 s per action, about twice as slow per action as ARC's published Standard run on FT09 and, under D20, a provider-latency incident; run 1 (CD82 S4) won in 206 actions at 44 s per action. A clock-based reading of H4 then mixes what each config does with each action and how fast its actions come. On 2026-10-07 the researcher decided to pre-register an action-matched secondary reading before any later block-2 result is seen. `PREREG.md` §17.5 (amendment R5) registers it, with the script that computes it; this section only points there.
- **The reading.** For each counted run, ARC's game score and the levels cleared within its first K = 150 actions, with a curve at 50, 100, 150 and 200 actions. H4's path quantities (gap, step shares, Predictions A and B, bootstrap intervals) are computed again from these values as secondary readings, and Checkpoint C reports the seed-1 gap at K next to its own, descriptively. A run that stopped before K actions other than by a win or ARC's action budget is censored: reported as a lower bound and, in a sensitivity analysis, left out. A run whose scorecard the script cannot score or reproduce has no matched values, and its unit is left out. **[A7]** Over the 4 seed-1 units and the configs that run (§22).
- **K = 150** is the largest multiple of 50 that every config should reach inside 12 h at run 2's pace, with S1 and S2 slowed by their pilot latency ratios. It is fixed by pace, not by outcomes.
- **Unchanged.** H4's and H5's primary readings, predictions and thresholds, the kill rules, Checkpoint C's and G2's rules, the 12 h clock, the action budgets, the run plan and the re-run rules. No rule reads a matched value. **[A7]** A7 changes the run plan, a config's first D20 yardstick and the H4 readings (§22).
- **Also decided on 2026-10-07, outside A6:** run 2 is a D20 latency incident and is re-run once, with seed 101, after block 2's last run (a logged deviation from D19's timing); phase 1b is sized at Checkpoint C.
- **What it does not show.** Matching actions removes the effect of speed, not the effects of context length, and the clock-based readings remain what ARC's harness rewards.

## 22. Amendment A7 (2026-10-09): the minimal path
**Why.** Checkpoint C's cost rule fired on 2026-10-09: the forecast for the remaining 24 ARC runs was $1,045.23 against $609.78 left under the 1b cap, or $804.55 on 3 games, so either design needed a 1b raise of $195-435, beyond the ~$170 that D27 allows (`results/checkpoint_c/20261009T151039Z/`). The same day the researcher chose a minimal path: luna's sweep and ARC's S2 on seed 1, possibly S1; an arXiv preprint ahead of the Kaggle ARC-AGI-3 writeups, then TMLR or an AGENT 2027 short paper; and a project total of about $560 that may run over a little (`results/decisions.md`). `PREREG.md` §17.6 (amendment R6) registers the changes to the runs and readings, with the code that enforces them; for those, this section only points there. The venues, milestones and budget target below are plan changes that A7 makes itself.
- **What runs** (R6 change 1). These paid runs remain, and no others:
  - **ARC, block `3-arc`:** S2 at replicate 1 on FT09, SB26, R11L and CD82, 4 counted runs plus any D19 or D20 re-run, back to back in the recorded SEED + 3 order with the dropped units deleted (FT09, R11L, SB26, CD82).
  - **S1** at replicate 1 on the same games, only if the researcher records "S1: yes" in `results/decisions.md`, merged to `main`, before the first block-3 ARC run starts. Otherwise S1 is not run, and an S1 run made later is exploratory. S1 would cost about as much again as S2.
  - **PersistGym, block `3-persistgym`:** luna's replay-off cells (F-0, W-0, W-n-0, Σ-n-0) on the 8 task cells, with the restated-at-need and single-turn controls, after G1. Its template count follows the frozen power rule, capped at 200.
  - **Hard stop.** After these runs, no further paid run. A later paid run needs a new dated amendment, and its results are reported as outside the pre-registration.
- **What is dropped.** Seed 2 of every ARC config; sol's H1 replication main runs (§20), whose pilot and validity runs are reported descriptively as pre-registered, not run (budget); phase 2 (StateCarry, §9), with G3, G4 and kill criterion 7; every extension run (E1-E6; whether PersistGym's code and data are released with the preprint, under E6, stays the researcher's decision); the failure labels and their LLM judge (§10); the ARC Paper Track (E5) and Decision P (§13); and luna's G1 redesign pass, so kill criterion 3 applies at once.
- **The readings** (R6 changes 3-5 and 9). H4 is read on the 4 seed-1 units. Without S1, S2 splits the gap into the provider-neutral steps together (loss policy and notes removal) and the replay step; Prediction B is tested in full and Prediction A only in its replay clause. H5 on our runs uses the 8 seed-1 S0 and S4 runs, which were seen before A7, so it is no longer a blind test. A config's first counted run is judged under D20 against its pilot median scaled by the latency drift that block 2 measured on S0. The Holm family is H1 and H3, as the researcher decided on 2026-10-06, before any H1 or H3 test.
- **Venues** (§13). An arXiv preprint before Nov 2, ahead of the Kaggle ARC-AGI-3 teams' writeups, after the researcher has reviewed the exact text. Then TMLR or an AGENT 2027 short paper of 5 pages (Nov 13 AoE). AGENT is archival, so TMLR's prior-publication policy is checked before doing both.
- **Milestones** (§11). G1 (Oct 14) stays, with no redesign pass. G2 (Oct 21) records the gap, the S2 shares (and S1's, if it runs) and the scoop check; its ARC kill cannot fire. M3 is the preprint and M5 the TMLR submission or the AGENT short paper. G3, G4, M4, M6 and P are removed. All Gemini runs still finish before 2026-12-31.
- **Budget** (§12). Spent: $328.94 billed (phase 0 $20.57, 1a $18.15, 1b $290.22; `results/costs.csv`). Forecasts: S2 about $172-194 at D27's rule (S0's billed cost per call × the larger of S0's and S4's actions, without and with block 2's re-run rate), and luna about $35-71 at T = 100-200. That puts the project at about $537-594 against the target of about $560; S1 or a D20 re-run would add to it. The phase caps in §17.3 are unchanged and stay stop-and-ask ceilings. The target is kept through the block limits (`max_usd`), which the researcher approves block by block. Phase 2 and the extensions spend nothing.
- **Also decided on 2026-10-09, outside A7:** block `3-arc` (S2 on seed 1, up to $250 billed) is proposed in the same `results/decisions.md` entry and approved when the researcher merges it. `3-persistgym` is proposed later, after G1 and the power re-simulation.
- **Parts of §16-§21 that A7 supersedes.** They stay as written, as §17.5 does for §16:
  - §16.2, blocks 3 and 4 and Checkpoint C's "one wave" sentence: block 3 is S2 (and S1, if decided) on seed 1 plus luna's sweep, and there is no block 4.
  - §17.1, D24 (phase 2), and D27's raise of up to ~$170 at Checkpoint C, which was not requested.
  - §17.2, the Checkpoint C, held-out, G3 and phase 2 forecasts and the block 3 and 4 totals.
  - §17.3, the 1b row's "Checkpoint C may ask for up to ~$170 more": not requested. The table and its caps are unchanged.
  - §20, the replication's main runs and their cost; §21, "the run plan" among the unchanged items.
- **Unchanged.** The hypotheses, and every prediction and threshold R6 does not name; the frozen ARC configs, the standard tier, the 12 h clock, the action budgets, the $120 guard and hold, D19 and the counted-run rule; K = 150 (§21); luna's cells, controls, repeats, effort and Flex tier; pilot blinding; the phase caps; and the rule that every paid block needs the researcher's approval line.
- **What it does not show.** One seed per game and config: the FT09 S0 pair (58.17 vs 18.11) shows swings of about 40 RHAE, so shares from 4 units are descriptive and coarse. S0 and S4 ran on Oct 6-9 and S2 runs later, with no dated Gemini snapshot and a latency that has already drifted. Without S1, the notes instruction's own role is not measured. There is no StateCarry evidence, no sol replication of H1, no failure labels and no open-weights run; each is reported as planned, not run. The cut was made for cost after block 2's results had been seen; all 4 games are kept, so no game was chosen on its result.

## 23. Amendment A8 (2026-10-10): the S1/S2 summary budget
**Why.** In block 3, three S2 runs ended because ARC's harness summary came back empty 4 times: FT09 S2 twice, R11L S2 once. The summary request's 8,192-token output budget includes the model's reasoning at high thinking, and on thinking-heavy games that reasoning can fill it. S2 exists to isolate native replay, so runs lost this way would measure the harness's budget, not the config. The researcher chose to fix it on 2026-10-10 (`results/decisions.md`). `PREREG.md` §17.7 (amendment R7) registers it; this section only points there.
- **The change:** patch 0018 sets S1's and S2's `summary_max_output_tokens` to 65,536, the budget of every step request. S0 and S4 are unchanged. S4's summaries never came near 8,192 in block 2.
- **The runs:**
  - one replacement run per unit whose counted S1/S2 run was lost to the summarizer failure: FT09 S2, and R11L S2 if its re-run is lost too;
  - then CD82 S1, CD82 S2 and R11L S1 under the new config;
  - all within block `3-arc`'s $470.
- **Unchanged:** the hypotheses, the readings, the gates and the budget caps.
- **What it does not show:** the S1/S2 runs are not all on one summary budget (SB26 S1 and FT09 S1 ran under 8,192), and a replacement replaces a run whose partial play was seen.
