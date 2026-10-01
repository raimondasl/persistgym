Version: 0.1-draft

**Status: DRAFT for the researcher's review. Not yet frozen.** Nothing in this file binds any run, and no paid call may be made under it, until the researcher has resolved every decision item, signed it off and committed it as Version 1.0 (§0.3).

**Change rule.** After freezing, this file changes only by a dated amendment that states its reason, appended to the amendment log (§17) and merged through a pull request. Hypotheses, predictions and thresholds are never edited after any result they concern has been seen. Analyses not registered here are reported as exploratory.

# PREREG: when does the harness matter?

## 0. How to read this draft

### 0.1 Sources
- Built from `PLAN.md` §4-§10 as amended by A1 (`PLAN.md` §16), branch `m0/plan-amendment-a1`, commit `66b980f`. Where §16 and an earlier PLAN section disagree, §16 wins (PLAN header).
- Facts and their URLs are in `docs/background.md` and `docs/premise-check.md`. The few new outside facts in this file carry their own URL and check date.

### 0.2 Conventions
- **Blockquotes (`>`) are copied from PLAN as written.** No prediction or threshold inside them has been changed. Each one cites its PLAN section so the two files can be diffed. "[...]" marks an elision, and omitted table rows are named below the table (§6). Nested list items are sometimes run together on one line; their words are unchanged. Section numbers *inside* a blockquote are PLAN's own.
- **Text marked "Operational"** is new. It says how each quantity is computed and from which logged field (§2.1). It changes no prediction or threshold. Where PLAN can be read more than one way, it proposes one reading.
- **[RESEARCHER DECISION]** (D*n*) marks a proposed value or wording that needs the researcher's judgment, followed by one line on the trade-off. §16 lists all of them. At freeze, each tag is replaced by the decided text, and the decision is logged in `results/decisions.md`.
- "PLAN §x" always means `PLAN.md`; "§x" alone means a section of this file.

### 0.3 Freeze procedure
1. **Before freeze** (PLAN §16.3): the operational slice of the free ARC analysis is done (§7.8). Its outputs feed D14, D16, D21, D22, D27 and D28.
2. The researcher resolves every D-item: accept, change or strike.
3. The version line becomes `Version: 1.0` and the status line becomes "Frozen on <date> by <researcher>".
4. The change is merged through a pull request by the researcher. The merge commit is the **freeze commit**, recorded in `results/decisions.md`.
5. The game draw (§7.3) runs once, at the freeze commit.
6. Only then, and only once the payload snapshot tests pass (PLAN §6, §16.2; CLAUDE.md), may the Stage 1 pilots (paid) be requested (PLAN §16.2). Run metadata records the PREREG version string; a paid run under a `-draft` version is a protocol violation.

| Sign-off field | Value |
|---|---|
| Frozen by | |
| Date (UTC) | |
| Freeze commit | |
| D-items resolved (D1-D39) | |
| Operational-slice commit used for D14, D16, D21, D22, D27, D28 | |

## 1. Research question and order of operations
> With the model fixed, when does the harness change task **success** rather than only **cost**?
>
> Working hypothesis: harness effects on success are large when the state needed later
> - (a) is **derived**, i.e. computed from several observations rather than read from one, and
> - (b) is **not recoverable**, i.e. it cannot be re-observed from the environment, and
> - (c) is **evicted** by the harness's loss policy (window truncation or summarization).
>
> When the state can be re-queried, harness differences should turn into extra lookups and tokens instead. (PLAN §2)

**Order of operations** (PLAN §16.2, §16.3):
1. Stage 0 ($0): operational slice, ARC patches and payload snapshot tests, offline ARC games with a stub model, PersistGym build and $0 validity checks, cost model, power re-simulation.
2. PREREG freeze, then the seeded game draw (§7.3).
3. Block 1, pilots (§11), then gate G0 (§10.1).
4. Block 2, seed-1 S0+S4 (8 counted runs), then Checkpoint C (§10.3).
5. Block 3, the other 24 ARC runs plus the PersistGym main sweep, then G2 (§10.4). The PersistGym main sweep starts only after gate G1 (§10.2) has passed and been recorded (PLAN §11).
6. Block 4, phase 2 (StateCarry), with gates G3 and G4 (§8).

Each block needs the researcher's explicit approval (§12).

## 2. Definitions (PLAN §4, §5, §16.5)
> Definitions to fix in `PREREG.md` (these need the researcher's judgment): (PLAN §4)

### 2.1 Episodes, tokens and logged fields
> **One environment family.** Each episode is a sequence of about 20-32 steps.
> - Every environment step is a **new user message** containing an observation, as in ARC's harness, and the agent replies with one action. (PLAN §5)

**Operational.**
- Steps are numbered t = 1..T. The observation at step t is o_t; the agent's reply is a_t.
- **Project tokenizer:** `tiktoken` encoding `o200k_base` (version pinned in `uv.lock`). Every planned distance, the window W, the padding budget v and the survival calculator use it. Provider-reported tokens are logged next to it and are what cost is computed from (PLAN §5: "Use one tokenizer for generation and window accounting, and also log provider-reported tokens"). Choosing this encoding is part of D5.

**Logged fields this PREREG relies on.** The code tracks log these names, or commit a table that maps their names onto these.

| Field | Meaning | Written by |
|---|---|---|
| `template_id`, `template_seed`, `repeat_index` | Template identity (§2.9) | generator |
| `fact_kind` ∈ {observed, derived}; `recoverable` (bool); `distance` ∈ {near, far} | Task cell | generator |
| `control` ∈ {none, restated, withheld, single_turn} | Control condition (§4) | generator |
| `harness_cell` | F-r, F-0, W-n-r, W-n-0, Σ-n-r, Σ-n-0, W-0, Σ-0-r | harness |
| `fact_value`, `clue_values`, `rule_text` | Target value; clue values and combining rule (derived only) | generator |
| `evidence_steps`, `evidence_spans` | Steps and exact rendered text of every evidence binding (§2.3, §2.4) | generator |
| `need_step`, `options`, `correct_action` | From the dependency graph (§2.6) | generator |
| `obs_tokens[t]`, `system_tokens` | Project-tokenizer counts | generator, harness |
| `payload[t]` | Exact request body sent at step t (raw, under `results/raw/`) | harness |
| `reply_text[t]`, `action_parsed[t]` | Visible reply and parsed action | harness |
| `usage[t]` | Provider-reported input, cached input, output and reasoning tokens | API response |
| `model_returned[t]`, `reasoning_context_echoed[t]` | Echoed model string and effective `reasoning.context` | API response |
| `n_lookups`, `lookup_steps` | Lookups taken (§2.5) | harness |
| `success` | §2.6 | analysis |
| `S_planned`, `S_verbatim`, `S_carried`, `S` | §2.8 | survival calculator, analysis |
| `exit_status` | `ok`, `transport_error`, `echo_mismatch`, ... | harness |
| `cost_usd_list`, `cost_usd_billed_est` | From `usage` and the dated price table | analysis |

For ARC runs: `run_id`, `game_id`, `config_id` (S0, S1, S2, S4, S0+SC), `config_hash`, `fork_commit`, `patch_sha256`, `seed`, `replicate`, `is_rerun`, `rerun_of`, `exit_reason`, `levels_cleared`, `level_actions[ℓ]`, `rhae` (from ARC's online scorecard), `scorecard_id`, `n_calls`, `n_compactions`, tokens (input, cached, output, reasoning), `cost_usd_list` (the harness's no-cache accounting), `cost_usd_billed_est`, `service_tier`, `wall_clock_s` and `model_returned`.

### 2.2 Target fact, options and chance
> **Need:** asks for an action whose parameter is the target fact, chosen from K options (plan K=10, so chance = 10%). (PLAN §5)
>
> **Task cells (2 × 2 × 2 = 8):** {observed, derived} × {recoverable, not} × {near, far}, with k=1 (one target per episode). (PLAN §5)

### 2.3 Observed fact
> **Observed fact:** a value shown verbatim in one observation. (PLAN §4)
>
> **Reveal:** Observed: shows the target fact. (PLAN §5)

**Operational.**
- The generator sets `fact_kind = observed` and renders one **binding**: a sentence that names the fact's key and gives its value (for example "the relay code for vault B is 4417"). It appears in exactly one observation, `evidence_steps = [r]`. `evidence_spans` holds the exact rendered binding.
- "Shown verbatim" means that `fact_value` occurs as an exact substring of the binding.
- The `fact_value` string occurs nowhere else in the episode: not in other observations, the system prompt or the filler. There are three exceptions: (i) the need step's option list, where it is unbound and sits among 9 distractors; (ii) a lookup response in the recoverable variant (§2.5); (iii) the restated-at-need control (§4). The generator checks this by exact string search over the rendered episode and re-samples on failure. A $0 validity check re-verifies it.
- Each episode also carries 2 **distractor bindings**: other keys with values in the same format. None of them is ever needed. They stop the target binding from standing out at reveal time.

**[RESEARCHER DECISION]** (D1) Accept the binding wording, the ban on the value string outside the three exceptions, and the 2 distractor bindings per episode. *Trade-off:* the string ban makes string-match survival (§2.8) clean, but the filler generator must avoid the value's format. Distractor bindings make the target less salient, which makes the task harder and so reduces headroom at the 85% restated-at-need gate.

### 2.4 Derived fact
> **Derived fact:** a value computed from 2-3 observations shown at different steps. It is never shown in final form. (PLAN §4)
>
> **Reveal:** [...] Derived: shows one of 2-3 clues plus, at some step, the combining rule. (PLAN §5)

**Operational.**
- The generator sets `fact_kind = derived`. There are m ∈ {2, 3} clue bindings, each in a different observation, plus one **rule binding** that states the combining rule g in words. The rule binding may share an observation with a clue. `fact_value = g(clue_values)`.
- The **evidence set** is all clue bindings plus the rule binding. `evidence_steps` holds their sorted steps.
- "Never shown in final form": the `fact_value` string occurs in no observation, system prompt or filler, except the need-step option list and the restated-at-need control. A lookup in the recoverable variant re-shows the clues and the rule, never the value (PLAN §5).
- **Every clue is needed:** for every proper subset of the clues (with the rule), all K options stay consistent. The oracle checks this by enumeration. An agent that kept only some of the clues is therefore at chance.
- Clue values obey the same string rules as an observed value (§2.3). Each one appears only in its own binding, in lookup responses and in the restated control.
- m is a template property: half of the templates use m = 2 and half m = 3, assigned from the template seed.

**[RESEARCHER DECISION]** (D2) Accept (a) the rule binding as part of the evidence set, (b) the condition that all K options stay consistent under any proper subset of clues, and (c) the 50/50 split of m. *Trade-off:* (b) makes partial memory worthless, which sharpens the derived contrast, but it restricts g to rules such as modular sums. A weaker condition (say, at least 5 of K options stay consistent) allows more natural rules but lets partial memory score above chance.

### 2.5 Recoverable
> **Recoverable:** a `lookup` action re-shows the fact (or its clues) at the cost of one step. (PLAN §4)
>
> **Lookup (recoverable variant only):** `lookup(key)` re-shows the fact, or the clues for derived facts, in the next observation. It costs one step. (PLAN §5)

**Operational.**
- When `recoverable = true`, the action list in the instructions includes a generic `lookup(key)`: "re-show an earlier record". It accepts any key that has appeared in a binding earlier in the episode, distractor keys included. Offering it therefore does not reveal which key will be needed.
- **Mechanics:** if the agent replies `lookup(key)` at step t, the next user message is a **lookup response**. It contains the same binding(s) verbatim: the fact binding, or every clue binding plus the rule binding. After them comes the unchanged pending task of step t, and the whole message is padded to v tokens. The agent then acts on step t. One lookup therefore adds exactly one user message and one model call. `n_lookups` counts lookups. The scripted steps, the identity of `need_step` and the success scoring do not change.
- A key that has not yet appeared returns "no such record", which also costs one step.
- **Cap:** at most 3 lookups per episode. A 4th returns "lookup unavailable" (one step).
- When `recoverable = false`, `lookup` is not in the action list. A `lookup(...)` reply is an invalid action: it scores 0 at the need step, and at a routine step it is logged and the episode continues.

**[RESEARCHER DECISION]** (D3) Accept the generic lookup over any earlier key, the lookup response merged with the pending task (one extra step), and the cap of 3. *Trade-off:* a generic lookup avoids cueing the target but lets the agent look up the wrong key. The cap prevents runaway episodes but censors heavy lookup behaviour, which is part of H1's cost outcome, at 3.

### 2.6 Needed, live and success
> **Needed:** the step at which the fact determines the only correct action. "Needed" and "live" come from the generator's dependency graph, never from agent trajectories. (PLAN §4)

**Operational.**
- The generator's dependency graph has one node per scripted step and edges from evidence steps to the need step. `need_step` = n is the unique step whose correct action depends on the target fact. `correct_action` = choose(`fact_value`).
- `options` lists K = 10 distinct values in a seeded random order, exactly one of which equals `fact_value`. The distractor options have the same format and, like the value, occur nowhere else in the episode.
- **Live:** the fact is live on steps [min(`evidence_steps`), n]. No other step's correct action depends on it, and the generator checks this on the graph. Routine steps depend only on their own observation (PLAN §5).
- **Success:** `success = 1` iff `action_parsed` at the need step equals `correct_action`. If the agent looks something up at the need step, its first non-lookup action is scored. Unparseable, invalid or missing actions score 0. Accuracy on routine steps is logged as `routine_acc`, a competence check, not an outcome.
- The action parser is written by the harness track and frozen with the payload snapshot tests. All cells use the same parser.

**[RESEARCHER DECISION]** (D4) Accept scoring the first non-lookup action, and scoring invalid output as 0. *Trade-off:* scoring invalid output as failure keeps every episode in the analysis, but mixes format errors with memory failures. The failure labels (§9.7) separate the two after the fact.

### 2.7 Near and far
> **Near / far:** the reveal lies inside / beyond the harness eviction threshold W, in tokens. (PLAN §4)
>
> near = reveal about 4 steps before need; far = reveal beyond W. (PLAN §5)
>
> "Far" defined by observation tokens alone, so eviction does not depend on reply length; survival checked against the payload actually sent. (PLAN §16.5)

**Operational.** Let n = `need_step`, r_first = min(`evidence_steps`), r_last = max(`evidence_steps`), sys = `system_tokens`, and O(a, b) = Σ_{t=a..b} `obs_tokens[t]`.
- **Far:** sys + O(r_last, n) > W. Replies only add tokens, and a drop-oldest window keeps a contiguous suffix of turns. So every window cell drops all of the evidence before the need step, whatever the agent writes. In summary cells the payload must exceed W at some step after r_last and no later than n, so the evidence has passed through a summary by the need step (the trigger is defined in §5).
- **Near:** every evidence step lies in [n − 6, n − 1]. An observed fact's reveal sits at n − 4. Derived clues and the rule are spread over [n − 6, n − 1]. In addition, sys + O(r_first, n) + (n − r_first) × R_plan ≤ W, with a planning allowance of R_plan = 1,000 tokens per visible reply. Near evidence is *planned* to survive in window cells. Actual survival is checked on the payload sent (`S_verbatim`, §2.8).
- Near and far are properties of the rendered template, not of the harness. The same episodes run in every harness cell (PLAN §5, fully crossed). In F cells, "far" only places the evidence far back; nothing is evicted.
- **Shared skeleton:** all 8 task-cell renderings of a template share T, `need_step` n, the routine steps and the filler. They differ only in where the evidence bindings sit, in the bindings themselves (observed vs derived), and in whether `lookup` is offered. Near and far renderings therefore have the same length, which H1's token reading relies on (§3 H1, D8).

**[RESEARCHER DECISION]** (D5) Accept the far inequality, the near window [n − 6, n − 1] with R_plan = 1,000, the shared skeleton (same T and n in all 8 task cells of a template), and `o200k_base` as the project tokenizer. *Trade-off:* a larger R_plan protects near cells against long replies but forces a larger W or a smaller v. `o200k_base` may not match the providers' own tokenizers exactly. That affects only cost estimates, because W is defined in project tokens and provider counts are logged.

### 2.8 Survives (S), carried and rescued
> **Survives (S):** whether the fact (or all its clues) is still in the context the harness sends at the need step. Computed from token positions for window harnesses. Measured by string match for summary and notes, since those depend on what the model writes. (PLAN §4)

**Operational.** All quantities use `payload[n]`, the **first** request at the need step, sent before any lookup response.
- **`S_planned`** (computed before running, by the survival calculator): 1 in F cells. In window cells it is 1 for near and 0 for far, by §2.7, from `obs_tokens`, `system_tokens` and W. In summary cells it is 0 for far and left unplanned for near, because whether a summary fires between the evidence and the need step depends on reply lengths.
- **`S_verbatim`** = 1 iff every string in `evidence_spans` occurs in a user message of `payload[n]`, excluding the need observation itself and any lookup response.
- **`S_carried`** (cells with notes or summaries, when `S_verbatim` = 0) = 1 iff text the model wrote and that is still in `payload[n]` contains the right string as a whole-word match. That text is the summary bridge message plus the retained assistant replies. The match uses the regex `(?<![0-9A-Za-z])VALUE(?![0-9A-Za-z])`. For an observed fact the string is `fact_value`. For a derived fact it is `fact_value`, or else every value in `clue_values`. Lookup responses and the need observation are excluded.
- **`S`** = `S_verbatim` OR `S_carried`.
- **Window accounting ignores replayed reasoning.** W counts project-tokenizer tokens of the system prompt, the observations and the visible replies only. In replay cells, reasoning items travel with the turns they belong to and are dropped with them. This keeps W-n-r and W-n-0 on the same eviction rule, and it matches the identical-payload replay toggle (§6).
- **Accounting check.** Two kinds of mismatch are kept apart, because only one of them is a bug.
  - *Bugs:* in window cells, `S_verbatim` must equal the survival recomputed by replaying the drop-oldest rule on the project-token counts of the turns actually sent. In window cells at far distance, `S_verbatim` = 1 is impossible by §2.7. Any episode that breaks either condition is a window-accounting bug, and analysis stops until it is found.
  - *Expected near losses:* in near window cells, `S_planned` = 1 but `S_verbatim` = 0 can happen without a bug, when visible replies longer than R_plan or lookup responses push the evidence out. These episodes are counted per cell, reported, and analysed by their assigned cell (§13). If they exceed 2% of any near window cell in the block-1 pilots (pooled tokens only, §11), R_plan or W is re-tuned under §4.2 before the main sweep.
- **Carried, used, rescued** (PLAN §5, §10): among episodes with `S_verbatim` = 0, P(carried) = mean `S_carried`; P(used | carried) = mean `success` where `S_carried` = 1; P(rescued | not carried) = mean `success` where `S_carried` = 0, split by whether a lookup was taken. Chance is 0.10. Episodes with `S_verbatim` = 1 give the residual at S = 1.

**[RESEARCHER DECISION]** (D6) Accept whole-word string matching on the value or all clues, the exclusion of replayed reasoning from W, the bug stop, and the 2% pilot re-tuning trigger for expected near losses. *Trade-off:* string match misses paraphrased carry (for example "the code ends in 17"), so it undercounts P(carried). Counting replayed reasoning toward W would make window cells evict sooner when replay is on, which would confound replay with loss. Treating every planned-vs-actual mismatch as a bug would halt the analysis on expected behaviour: ARC's Standard harness averages about 907 visible output tokens per action with the notes instruction on (`docs/background.md` §4), close to R_plan.

### 2.9 Templates, repeats and seeds
> **Templates.** A template is one sampled skeleton: surface story, fact values, filler. Each template is rendered into **all 8 task cells and all harness cells** (fully crossed). All contrasts are therefore within-template, and template fixed effects absorb difficulty. Add templates rather than seeds: run 1 repeat per template × cell, and 2 repeats on a 10% subset to estimate within-template noise. (PLAN §5)
>
> Pilot templates use a disjoint seed range. (PLAN §16.5)

**Operational.**
- `template_seed` ranges never overlap. The main sweep uses 1-49,999, taken in order from 1. Validity runs and the G1 spot-check use 50,000-59,999. Pilots use 90,000-99,999. $0 checks may use any range.
- **Repeats:** main templates whose seed is divisible by 10 also get `repeat_index` = 1. Primary analyses use `repeat_index` = 0 only. Repeat 1 is used only to estimate within-template noise.
- Provider sampling is not seeded. Repeats measure that noise.

**[RESEARCHER DECISION]** (D7) Accept these seed ranges and the repeat-0-only primary analysis. *Trade-off:* repeat 0 alone weights every template equally, but drops about 10% of paid episodes from the primary estimate.

## 3. Hypotheses (PLAN §4)
> Kill and equivalence rules below use 90% CIs from a template-level cluster bootstrap on the probability scale. (PLAN §4)

In this section, p(cell) means the mean `success` over the episodes in that cell, using repeat 0 and excluding §13 exclusions. Bootstrap details are in §9.1.

### H1: recoverability turns a success penalty into a cost penalty
> Model: gpt-6-luna (primary). Replication on gpt-6.1-sol if the budget allows (adds cells W-0 and W-n-0 on sol, about 640 episodes). **[A1]** Removed from the MVP: re-costed at about $430-610 at Flex with cache writes, not $30-230 (§16.1). Revisit as an extension.
>
> Comparison: an observed fact at far distance, window harness **without** notes (W-0, so S=0 by construction), vs full history (F-0). W-n-0 is reported alongside it as the notes-rescue condition.
>
> **Predictions:**
> - If the fact is **not recoverable**, success drops by at least 25pp.
> - If it is **recoverable**, success stays within 5pp, but lookups and total tokens rise by at least 30%.
>
> **Falsified or kill** if the difference between the two penalties is below 10pp, with the 90% CI upper bound below 15pp. In that case drop the "success vs cost" framing. (PLAN §4)
>
> H1's non-recoverable arm reported as a manipulation check; the confirmatory test is the difference of penalties. (PLAN §16.5)

**Operational.**
- Model gpt-6-luna. Cells F-0 and W-0, with W-n-0 reported alongside. Task cells: observed × far × {not recoverable (NR), recoverable (R)}.
- Penalty_NR = p(F-0, NR) − p(W-0, NR). Penalty_R = p(F-0, R) − p(W-0, R). **Δ_H1 = Penalty_NR − Penalty_R.**
- **Manipulation check:** Penalty_NR ≥ 25pp (point estimate), reported with its CI.
- **Confirmatory test:** Δ_H1 (Holm family, §9.4).
- **Recoverable success prediction:** |Penalty_R| ≤ 5pp (point estimate).
- **Lookups prediction:** mean `n_lookups` in W-0 divided by mean `n_lookups` in F-0, both in the observed-far-R cell, is ≥ 1.30. If F-0 has no lookups at all, the ratio is undefined, and the prediction is met iff the lower bound of the 90% CI of the difference (W-0 − F-0) is above 0.
- **Tokens prediction:** let T(h, d) be the mean provider-reported total tokens per episode (input including cached, plus output including reasoning), in harness h and the observed-R cell at distance d. The proposed reading is the difference-in-differences ratio R_tok = [T(W-0, far) / T(F-0, far)] / [T(W-0, near) / T(F-0, near)] ≥ 1.30. The literal ratio T(W-0, far) / T(F-0, far) is reported next to it.
- **Kill** (as written): Δ_H1 < 10pp (point estimate) **and** the upper bound of its 90% CI < 15pp.

**[RESEARCHER DECISION]** (D8) Accept the difference-in-differences reading of "total tokens rise by at least 30%", and the zero-lookup rule. *Trade-off:* the literal ratio is confounded, because the window caps input tokens: W-0 sends fewer tokens per call than F-0 even without lookups, so the literal ratio can fall below 1 when the predicted cost penalty is present. The difference-in-differences cancels that cap, because near and far renderings of a template have equal length (the shared skeleton, §2.7), and it reuses near-R cells that already run (§4.6).

### H2: reasoning replay carries derived state
> Model: gpt-6.1-sol, plus gpt-6-luna if the M0 pilot shows it honours `all_turns`. Arms: full history, `reasoning.context` = `all_turns` (F-r) vs `current_turn` (F-0).
>
> **Predictions:**
> - Less than 3pp difference on observed facts.
> - On derived facts at far distance: at least 8pp more success with replay, or, if success does not move, at least 25% more reasoning tokens in the no-replay arm (the model re-derives what it no longer sees).
>
> **Falsified** if the derived-fact success effect is under 3pp *and* the token effect is under 10%. **Equivalence** (treated as "no effect"): the 90% CI of the success effect lies inside ±8pp *and* the token effect is under 10%. (PLAN §4)

**Operational.**
- The **primary** model is gpt-6.1-sol. Cells F-r vs F-0 on all 8 task cells, with the template count sized at M1 (§4.2). If luna passes the G0 toggle check (§10.1), its H2 run is reported as a replication outside the Holm family.
- **Echo:** any episode in which some response's `reasoning_context_echoed` differs from the requested value is excluded (CLAUDE.md). If more than 5% of a cell's episodes are excluded, the run stops and the researcher is told.
- **Observed facts:** Δ_obs = p(F-r) − p(F-0), pooled over the 4 observed task cells. Prediction: |Δ_obs| < 3pp (point estimate).
- **Derived, far:** Δ_der = p(F-r) − p(F-0), pooled over derived × far × {R, NR}. Prediction: Δ_der ≥ 8pp.
- **Token effect:** TE = (mean need-step reasoning tokens in F-0) / (mean need-step reasoning tokens in F-r) − 1, over derived-far episodes, using `usage[n].reasoning` from the need step's first call. TE is a ratio of means with template-cluster bootstrap intervals (§9.1). The log-link model of §9.5 gives the model-based estimate, which must agree in sign (D26). Prediction (the alternative branch): TE ≥ 25%. Total reasoning tokens per episode are reported as a secondary measure.
- **Falsified:** Δ_der < 3pp **and** TE < 10%, both as point estimates.
- **Equivalence:** the 90% CI of Δ_der lies inside (−8pp, +8pp) **and** TE < 10% (point estimate).
- **"Signal"** for running the W/Σ replay pairs (PLAN §7: "The W/Σ replay pairs run only if H2 shows signal") means H2 is not falsified: Δ_der ≥ 3pp or TE ≥ 10%.

**[RESEARCHER DECISION]** (D9) Accept need-step reasoning tokens as the primary token measure, point estimates for "under 3pp" and "under 10%", pooling over recoverability, sol as the only confirmatory model, and "signal" = not falsified. *Trade-off:* need-step tokens target the re-derivation step, but they are noisier and leave out any global "thinks less with replay" effect that a per-episode total would include (on ARC the Adapter thinks about 2.6× less per turn). Point estimates make "falsified" easy to reach with sol's 30-40 templates.

### H3: little residual cost of multi-turn structure when the fact survives
> Comparison: at S=1, far distance, multi-turn full history vs the position-matched single-turn control. The control has the same tokens and the fact at the same offset, but in one prompt.
>
> **Prediction:** the difference is at most 5pp. We report it either way. It bounds how much of any effect is "needle-in-a-haystack" retrieval rather than state persistence. (PLAN §4)

**Operational.**
- Model gpt-6-luna (PLAN §7 lists H3 among luna's high-N runs). The multi-turn arm is F-0 in the far, not-recoverable cells, observed and derived pooled. S = 1 there by construction.
- **Control construction:** the system prompt is unchanged. One user message holds o_1..o_n in order. Each observation is followed by the oracle's correct routine action, written as a plain "Agent: ..." line, and the message ends with the need-step question. The evidence sits at the same observation-token offset from the need question as in the multi-turn episode. Reply tokens differ, because the control uses oracle-length replies.
- **Δ_H3** = p(single-turn control) − p(F-0, multi-turn). The prediction holds iff the upper bound of the 90% CI of Δ_H3 is ≤ 5pp, i.e. one-sided non-inferiority at α = 0.05. The result is reported either way.

**[RESEARCHER DECISION]** (D10) Accept the NR-only scope, oracle routine replies in the control, F-0 as the multi-turn arm, and the one-sided reading. *Trade-off:* oracle replies make the control independent of any model run, but they shorten the gap between evidence and need compared with real replies, which slightly favours the control. Copying the matched F-0 transcript's replies would match tokens exactly, but would make each control depend on one run.

### H4: ARC path decomposition (Gemini 3.8 Flash, high thinking)
> Path: S0 → S1 → S2 → S4, defined in §8.2.
>
> **Prediction A (design review):**
> - Swapping drop-oldest for summary compaction (S0→S1) accounts for at least 1/3 of the S0→S4 gap.
> - The replay step (S2→S4) accounts for at most 1/2.
> - Removing the notes instruction (S1→S2) accounts for little or nothing, i.e. within ±10% of the gap.
>
> **Prediction B (competing; prior-art check):** the replay step accounts for at least 1/2. This reading comes from the published gap growing with reasoning effort (+9, +20, +25pp at low, medium, high).
>
> We register both and report which one the data supports. With 4 games × 2 seeds this is **descriptive**. Shares get bootstrap intervals over game-seed units, and we make no significance claims.
>
> **Kill the ARC leg** if the measured S0→S4 gap, averaged over the 4 games, is below 10 RHAE points. (PLAN §4)

**Operational.**
- RHAE per counted run is the per-game score on ARC's online scorecard (`rhae`). Counted runs are defined in §7.5.
- A **unit** u = (game, replicate); there are 8. For config c, R̄_c is the mean RHAE over the 8 units.
- **Gap** G = R̄_S4 − R̄_S0. Step shares: σ_loss = (R̄_S1 − R̄_S0)/G, σ_notes = (R̄_S2 − R̄_S1)/G, σ_replay = (R̄_S4 − R̄_S2)/G. They sum to 1.
- **Prediction A holds** iff σ_loss ≥ 1/3 **and** σ_replay ≤ 1/2 **and** −0.10 ≤ σ_notes ≤ 0.10 (point estimates). **Prediction B holds** iff σ_replay ≥ 1/2. The report says which hold: both (possible only at exactly 1/2), one, or neither.
- **Intervals:** 10,000 bootstrap resamples of the 8 units, with replacement, keeping a unit's four configs together; percentile 90% intervals. The fraction of resamples with G ≤ 0 is also reported. Descriptive only.
- Shares are reported only if G ≥ 10 RHAE. Otherwise kill criterion 4 fires (§10.4), and the table reports levels and RHAE without shares.
- **Optional S3** (PLAN §8.2), if run, is exploratory and stays out of the shares.
- **Sensitivity analyses:** excluding games flagged under D14; scoring the original errored runs instead of their re-runs (§7.5); excluding units that contain a `COST_CAP` ending (§7.7).

**[RESEARCHER DECISION]** (D34) Accept judging Predictions A and B on point estimates, and withholding the shares when G < 10 RHAE. *Trade-off:* PLAN asks which prediction "the data supports" without saying how; point estimates fit "descriptive" and "no significance claims" best, with the bootstrap intervals shown next to them. When G is small, each share's denominator is near 0, so shares can take any size or sign. Withholding them avoids over-reading noise. Reporting them anyway, clearly labelled, would be more transparent.

### H5: the Adapter advantage grows with level depth
> The Adapter's advantage in P(clear level ℓ | reached ℓ) is larger at levels ≥4 than at levels 1-2.
> - Tested first on ARC's published public-set runs (free; §8.1).
> - Then on our runs. (PLAN §4)

**Operational.**
- One observation per (run, level ℓ). **Reached(ℓ)**: the run took at least one action on ℓ (`level_actions[ℓ]` > 0). **Cleared(ℓ)**: the run completed ℓ. Analysis is conditional on reached.
- Depth bands: early = levels 1-2, deep = levels ≥ 4. Level 3 is reported but left out of the contrast.
- **Model** (PLAN §10): logistic regression, cleared ~ harness × band + game fixed effects, among reached levels. A_b is the Adapter-minus-Standard difference in P(clear | reached) in band b, on the probability scale (average marginal effect).
- **H5 contrast:** A_deep − A_early > 0 (point estimate), with a 90% interval from a game-cluster bootstrap (10,000 resamples). Descriptive, like H4 (PLAN §10).
- **Data:** (a) the published Gemini 3.8 Flash high-effort public-set runs, one per game and harness, 25 games, analysed in the hypothesis slice *after* the freeze commit (PLAN §16.3). Other efforts and models are exploratory. (b) Our runs, S0 vs S4 on the path games.
- **Sensitivity:** drop levels at which a run ended by an (inferred) error rather than by budget.
- **Not a blind test on the published runs.** Per-game scores for both harnesses (`docs/background.md` §4) and at least one per-level ending (LP85, PLAN §16.4) were seen before this draft. The operational slice must also infer where each published run ended, which reveals the last level each run reached. H5 on published runs is therefore a pre-specified analysis of partly seen data. Only H5 on our own runs is a test on unseen data.

**[RESEARCHER DECISION]** (D35) Accept: reached = at least one action on ℓ; two bands (1-2 and ≥ 4) with level 3 left out of the contrast, rather than a continuous depth term; the probability-scale average marginal effect with a game-cluster bootstrap; and high effort as the only registered published-data analysis. *Trade-off:* PLAN §8.1 lists P(clear | reached) "by harness and effort", and PLAN §10 names "depth" without bands. Restricting to high effort matches H4 and the path study, but drops the low- and medium-effort runs, where the published gap is smaller. Bands follow H5's own wording ("levels ≥4" vs "levels 1-2"), but discard level 3. "At least one action" excludes runs that cleared ℓ − 1 and then ended at once, which avoids counting an infrastructure ending as a failure to clear ℓ.

## 4. PersistGym-lite tasks and controls (PLAN §5)

### 4.1 Steps, volume and cells (as written)
> **Step types:**
> - **Routine:** the correct action depends only on the current observation. These keep the agent engaged and give a baseline competence check.
> - **Reveal:** Observed: shows the target fact. Derived: shows one of 2-3 clues plus, at some step, the combining rule.
> - **Need:** asks for an action whose parameter is the target fact, chosen from K options (plan K=10, so chance = 10%).
> - **Lookup (recoverable variant only):** `lookup(key)` re-shows the fact, or the clues for derived facts, in the next observation. It costs one step.
>
> **Volume control:** every observation is padded to a fixed token budget v with realistic, irrelevant log text. Distance in tokens is then fixed by distance in steps. Use one tokenizer for generation and window accounting, and also log provider-reported tokens.
>
> **Task cells (2 × 2 × 2 = 8):** {observed, derived} × {recoverable, not} × {near, far}, with k=1 (one target per episode). Start with W ≈ 24k tokens and v ≈ 1.5k, then tune in M1 so that contexts stay ≤ 64k:
> - near = reveal about 4 steps before need;
> - far = reveal beyond W. (PLAN §5)

### 4.2 Tuning rules for W, v and template counts (PLAN §16.5)
> W, v and template counts stated as tuning rules applied in M1, not as fixed numbers. The M1 power re-simulation also sizes sol templates for H2's ±8pp equivalence test. (PLAN §16.5)

**Operational.**
- **W, v, T:** start at W ≈ 24k and v ≈ 1.5k. At M1, choose W, v and the episode length T using only $0 checks and validity runs (oracle, restated-at-need, fact-withheld, pooled tokens), never main-cell success. Three conditions must hold:
  1. The largest F-cell payload is ≤ 64k project tokens.
  2. Every far rendering meets the far inequality and every near rendering meets the near inequality (§2.7).
  3. The validity gate passes (§4.4).

  The chosen values are recorded in `results/decisions.md` before the M2 sweep. Because the rule is pre-registered, this is not an amendment.
- **Template counts:** the M1 power re-simulation (§9.8) uses the variance measured in the validity runs.
  - luna: about 100 templates per cell (PLAN §7). The count is set to the smallest number with simulated power ≥ 0.80 both for Δ_H1 = 10pp (H1) and for H3's 5pp non-inferiority bound when the true Δ_H3 = 0, within the phase-1a cap.
  - sol: the smallest number with probability ≥ 0.80 that the 90% CI of Δ_der lies inside ±8pp when the true Δ_der = 0, within the phase-1a cap.
- If the cap does not allow 0.80, the largest affordable count is used and the achieved power is stated in the results. A sol result that is neither equivalent nor falsified is then reported as **inconclusive**, not as "no effect".

**[RESEARCHER DECISION]** (D11) Accept the 0.80 power target and the quantities it is computed for. *Trade-off:* a rough unpaired calculation (p ≈ 0.5, 40 templates × 2 derived-far cells per arm) gives a 90% CI half-width of about 13pp. Even a CI centred exactly on 0 fits inside ±8pp only if the within-template correlation between arms is about 0.62 or more (0.72 at 30 templates). The 0.80 target needs a standard error of at most 8 / (1.645 + 1.28) ≈ 2.7pp, i.e. a correlation of about 0.88 at 40 templates (0.91 at 30). So the cap will almost certainly bind, and the H2 equivalence branch is probably unreachable. The alternative is to demote that branch to exploratory now.

### 4.3 Controls (as written)
> **Controls, on the same templates:**
> - **Position-matched single-turn:** the same token sequence flattened into one prompt, with the fact at the same offset. Used for H3.
> - **Restated-at-need:** the fact is repeated in the need-step observation. This is the ceiling with memory taken out of the problem. (PLAN §5)

**Operational.** The single-turn control is built as in §3 H3. Restated-at-need appends the evidence bindings verbatim to the need observation (for a derived fact, the clue and rule bindings, not the value). The **fact-withheld** control used by the validity gate replaces every evidence binding with a distractor binding of equal token length.

### 4.4 Validity gate G1, per model (as written, plus A1)
> - The programmatic oracle, which knows the fact, scores 100%. This is a generator sanity check.
> - The LLM on restated-at-need scores ≥ 85% (enough headroom).
> - The LLM with the fact withheld scores ≤ chance + 10pp = 20%, so the fact is actually needed.
> - The researcher spot-checks 20 episodes per cell for shortcuts, e.g. the fact being inferable from filler. (PLAN §5)
>
> Add $0 validity checks: a programmatic shortcut audit, and no-memory heuristic baselines (most frequent option, last-seen option) that must score ≤ chance + 10pp. (PLAN §16.3)

**Operational.** Validity runs use harness cell F-0 and the validity seed range (§2.9). The 85% and 20% thresholds apply to the pooled rate over the 8 task cells, and per-cell rates are reported. The spot-check uses generated episodes from the validity range; the researcher reviews them without model output.

**Heuristic baselines** ($0; 1,000 generated episodes per task cell; each must score ≤ 20% in **every** task cell):
- **Position:** always choose the first option; always choose the last option.
- **Most frequent option:** on a disjoint set of 1,000 generated episodes of the same task cell, find the value and the list position that are most often correct; predict them on the test episodes.
- **Last-seen option:** on the fact-withheld rendering (§4.3), choose the option whose string occurs latest in the episode text before the option list, and a random option if none occurs.

A literal "last-seen" or "most frequent in the episode" heuristic on the normal rendering is not a no-memory baseline here: under §2.3 the target is the only option string that occurs before the option list, so such a heuristic recalls the fact and would score near 100% on observed cells. That is why it runs on the fact-withheld rendering, where any option string found before the list is a leak.

**[RESEARCHER DECISION]** (D39) Accept: restated-at-need for a derived fact restates the clues and the rule, not the value; the fact-withheld control uses equal-length distractor bindings; validity runs use F-0; the 85% and 20% LLM thresholds apply to the rate pooled over the 8 task cells; and the heuristic baselines above, applied per task cell. *Trade-off:* restating the clues keeps the derivation in the ceiling, which is the right ceiling for derived cells but makes 85% harder to reach there; restating the value would test only retrieval. Pooled LLM thresholds keep the paid validity runs small, but can hide one failing task cell (for example derived-restated at 70%); per-cell thresholds would need more validity episodes. The heuristics are free, so they are applied per cell.

### 4.5 Survival calculator (as written)
> For every harness × task cell, it computes S from token positions *before* running:
> - For window harnesses, S is mechanical, so the window effect at S=0 is not itself a finding.
> - The estimands are the non-mechanical parts: the rescue rate P(success | S=0), via notes, lookup or re-derivation; the residual at S=1; the value of replay for derived state.
> - For summary and notes cells, log whether the fact or clues appear in the summary or retained notes. This gives an accounting of P(carried), P(used | carried) and P(rescued | not carried). (PLAN §5)

### 4.6 Run matrix (PLAN §7, §12, §16.1)
> Core: F-r vs F-0 on all 8 task cells. The W/Σ replay pairs run only if H2 shows signal. (PLAN §7)
>
> Phase 1a stays under $450 by sizing (30 sol templates; luna's 4 replay-off cells first). (PLAN §16.1)

**Operational.** Which harness cells run on which model in the main sweep. Every row uses all 8 task cells and the template counts set by §4.2.

| Model | Harness cells | Controls | Status |
|---|---|---|---|
| gpt-6-luna | F-0, W-n-0, Σ-n-0, W-0, run first | Position-matched single-turn and restated-at-need, on all 8 task cells (PLAN §12's ~1,600 control prompts) | Confirmatory for H1 and H3; the rest is accounting (§2.8) and cost outcomes (§9.5) |
| gpt-6-luna | F-r, W-n-r, Σ-n-r | none | Only if luna's toggle is verified at G0 (D29) and the phase-1a cap allows. Exploratory (§9.10) |
| gpt-6.1-sol | F-r, F-0 | none | H2 core, confirmatory |
| gpt-6.1-sol | W-n-r vs W-n-0, Σ-n-r vs Σ-n-0 | none | Only if H2 shows "signal" (§3 H2) and the phase-1a cap allows. Exploratory |
| either | Σ-0-r (optional) | none | Only on a verified toggle and if the cap allows. Exploratory |

Validity runs (§4.4) use F-0 on each model that runs a main sweep. The sol H1 replication is not in the MVP (PLAN §4 [A1]).

**[RESEARCHER DECISION]** (D36) Accept this run matrix, and running both controls on all 8 task cells even though H3 uses only the far, not-recoverable cells (D10). *Trade-off:* fixing the matrix now stops cells being added or dropped after results are seen. Running the controls on all 8 task cells follows PLAN §12's cost line and gives a restated ceiling per task cell, at the cost of about 1,600 luna control prompts; running only the single-turn control, and only on the 2 task cells H3 uses, would cut that by seven eighths.

## 5. Harness cells (PLAN §6)
> | Cell | History / loss policy | Notes instruction | Reasoning replay | Role |
> |---|---|---|---|---|
> | F-r | full history | off | on | ceiling |
> | F-0 | full history | off | off | H1/H3 comparator |
> | W-n-r | token window W, drop oldest | on | on | |
> | W-n-0 | token window W, drop oldest | on | off | ≈ ARC Standard |
> | Σ-n-r | summary at W (generic summary prompt modelled on ARC's `SUMMARY_REQUEST_PROMPT`, same model) | on | on | |
> | Σ-n-0 | summary at W | on | off | |
> | W-0 | token window W | off | off | isolates notes |
> | Σ-0-r (optional) | summary at W | off | on | ≈ ARC Adapter |
>
> - **Notes instruction:** ARC's sentence, verbatim: "Include any context you want to carry forward in your reply, along with the action you want to take."
> - **Summary cells:** the summary replaces older turns with one user-role bridge message, as ARC does for Gemini.
> - **Payload snapshot tests:** every cell must have one that asserts exactly which turns, reasoning items and instructions are sent at each step. This is the single most important correctness check. No paid run happens until they pass. (PLAN §6)

**Operational.**
- **Window (W) cells:** before each call, drop the oldest (user, assistant) pair until sys + observation tokens + visible-reply tokens ≤ W, in project tokens. The current observation is always sent. Replayed reasoning items move with their turns and do not count toward W (§2.8).
- **Summary (Σ) cells:** before sending step t, if the payload would exceed W, every earlier turn is replaced by one user-role bridge message. It holds a summary written by the same model, using a generic summary prompt modelled on ARC's `SUMMARY_REQUEST_PROMPT`. The prompt text and its output cap are frozen with the payload snapshot tests. Summary calls are logged as separate calls and count toward cost.
- **Notes:** in "-n-" cells, ARC's sentence is appended verbatim to the system prompt. In the other cells it is absent. Nothing else in the system prompt differs between cells.
- **Replay:** "-r" sets `reasoning.context: all_turns` and "-0" sets `current_turn`. Both send the encrypted reasoning items (`store: false`, `include: ["reasoning.encrypted_content"]`), so the payloads are identical apart from `reasoning.context` (PLAN §7).
- **StateCarry** joins as one more cell in phase 2 (PLAN §6, §9). Its cell definition is fixed by amendment before its first paid run.

**[RESEARCHER DECISION]** (D12) Accept the summary trigger ("before sending, if the payload would exceed W") and the replace-all-earlier-turns bridge. *Trade-off:* replacing every earlier turn matches ARC's Gemini "fresh state" bridge, but it is harsher than summarizing only the overflow. Keeping the recent turns verbatim would make Σ cells retain near evidence more often.

## 6. Models and explicit settings (PLAN §7, §16.5)
> | Model | Used for | Replay toggle | Status / check in pilot |
> |---|---|---|---|
> | gpt-6-luna (OpenAI Responses, Flex) | High-N runs: H1, H3, validity; ~100 templates per cell | `reasoning.context`, *if* supported | Docs don't list luna for `all_turns`; one search snippet says all GPT-6 models default to it. **Pilot checks the echoed `reasoning.context`.** If `all_turns` isn't honoured, run only the replay-off cells (F-0, W-n-0, Σ-n-0, W-0) on luna. |
> | gpt-6.1-sol (OpenAI Responses, Flex) | H2 replay toggle; optional H1 replication; ~40 templates per cell | `reasoning.context` = `all_turns` vs `current_turn`, with encrypted reasoning items sent (`store:false`, `include: reasoning.encrypted_content`). The payload stays identical and only rendering changes. | Docs: "GPT-6.1 Sol also supports `all_turns`", and the response echoes the effective mode. **Check the echo on every response**; log and drop mismatches. Core: F-r vs F-0 on all 8 task cells. The W/Σ replay pairs run only if H2 shows signal. |
> | Gemini 3.8 Flash (Interactions API) | ARC path study only | Built up from the Standard harness (no stripping) | Google's docs say thought blocks must be resent within continuous conversation. S0-S2 never send thoughts, which is what ARC's Standard harness already does. **Pilot confirms manual_rolling on Interactions at high thinking.** |
>
> (PLAN §7)
>
> Explicit settings: Gemini `thinking_level: high`; luna/sol `reasoning.effort` (medium proposed, the documented default) and `reasoning.mode: standard`; `reasoning.context` always set explicitly. (PLAN §16.5)

PLAN §7's rows for Qwen3.6-27B and gpt-oss-120b (extension E1) and DeepSeek V4.1 Flash (not used for replay) are omitted above.

**Operational.**
- **gpt-6-luna and gpt-6.1-sol:** Responses API with `reasoning.effort: medium`, `reasoning.mode: standard`, `reasoning.context` set explicitly on every request (never omitted, never `auto`), `store: false`, `include: ["reasoning.encrypted_content"]`, Flex service tier, `max_output_tokens: 32000`, default sampling. OpenAI's reasoning guide, checked 2026-09-30, says GPT-6.1 Sol, GPT-6 Sol and GPT-6 Luna default to `medium` effort, and that `standard` is the default reasoning mode for GPT-6 models ([OpenAI reasoning guide](https://developers.openai.com/api/docs/guides/reasoning)). The pilot confirms that the echoed request fields match.
- **Gemini 3.8 Flash:** Interactions API with `thinking_level: high` set explicitly (the default is medium, PLAN §16.1). The service tier follows §7.6.
- **Pins:** none of luna, 6.1-sol or Gemini 3.8 Flash has a dated snapshot (PLAN §16.2, §16.6). The `model_returned` string on each response is therefore the pin. If it changes during a sweep, the change is flagged, and results are also reported split by model string.
- A response with status `incomplete` at the need step (for example, hitting `max_output_tokens`) counts as a content failure and scores 0.

**[RESEARCHER DECISION]** (D13) Accept effort `medium`, mode `standard`, `max_output_tokens` 32,000 and Flex for OpenAI. *Trade-off:* medium is the documented default and is cheaper than high, which matters because sol's H2 core is the largest line in phase 1a (PLAN §16.1). But the ARC leg runs Gemini at *high*, and the published ARC gap grows with effort, so a medium-effort H2 may understate the value of replay relative to the ARC leg.

## 7. ARC path study (PLAN §8)
> We use ARC's own MIT harness ([arcprize/arc-agi-3-benchmarking](https://github.com/arcprize/arc-agi-3-benchmarking)), forked and pinned at commit `4ca00e6` (2026-09-21, the HEAD of `main` on 2026-09-30). Pull later upstream changes only on purpose, and record them. (PLAN §8)

### 7.1 Path configs (as written)
> Path configs (all at `thinking_level: high`, same Interactions API surface)
>
> | Config | State | Loss policy | Notes instruction | Replay | Code change |
> |---|---|---|---|---|---|
> | S0 = Standard | `manual_rolling` (visible text only) | drop oldest pair above `MAX_CONTEXT_LENGTH` 175k (chars, 1 char/token) | on | none | none (a new config entry) |
> | S1 | `manual_rolling` | ARC `SummaryCompactor` (harness summary, trigger at 175k provider tokens, 8,192-token cap); `MAX_CONTEXT_LENGTH` raised so drop-oldest never fires | on | none | wire `SummaryCompactor` into `manual_rolling` |
> | S2 | as S1 | as S1 | **off** | none | notes flag (the sentence is hard-coded to `provides_continuous_conversation` in `agent.py::_build_system_prompt`) |
> | S4 = Provider Adapter | `continuous_conversation` (native thought steps + signatures) | harness summary at 175k (as ARC's Gemini PA config) | off (automatic) | native | none; reconstruct `google-gemini-3-8-flash-high-provider-adapter` from the checked-in low config (`thinking_level: high`) and confirm against the session config tag |
>
> - **Step meanings:** S0→S1 changes the loss policy. S1→S2 removes the notes instruction. S2→S4 adds native replay, together with the native item format; the two cannot be separated here.
> - **Order dependence:** the decomposition depends on path order, so report it as a *path* decomposition.
> - **Optional S3:** S2 plus `analysis_mode`-style readable reasoning summaries in history, i.e. "readable replay". [...] Run it only if budget allows. `analysis_mode` also re-adds the notes sentence, so the notes flag must override it. (PLAN §8.2)
>
> **Frozen configs.** S0-S4 config hashes are frozen in `PREREG.md` before the seed-1 runs, so S0/S4 results cannot steer the S1/S2 patches. (PLAN §16.4)

**Config freeze record.** This table is filled by a pre-declared amendment ("A-cfg", §17), which must be merged before the first block-2 run. The hash is the run-metadata writer's SHA-256 of the canonical JSON config.

| Config | Config entry name | `config_hash` | Fork commit | Patch files (SHA-256) |
|---|---|---|---|---|
| S0 | | | `4ca00e6` | |
| S1 | | | `4ca00e6` | |
| S2 | | | `4ca00e6` | |
| S4 | | | `4ca00e6` | |
| S3 (optional) | | | `4ca00e6` | |

### 7.2 Eligibility rule
> **Eligible:** public games where both published high-effort runs cost ≤ $60 *and* the published Standard-to-Adapter gap is ≥ 20 points. These are FT09, SB26, R11L, LP85, SC25 and CD82 (see `docs/background.md`). **[A1]** This filter can select Standard runs that were cheap because they ended in an error; the researcher decides before the draw whether to keep or amend it (§16.4).
>
> The published runs are one-seed screens. Our fresh seeds re-measure the gap, and claims are stated as conditional on "games where the Adapter helps". (PLAN §8.3)

**Operational.** The inputs are the published Gemini 3.8 Flash high-effort public-set runs, one per game and harness (`docs/background.md` §4). A game is eligible iff its Standard cost ≤ $60, its Adapter cost ≤ $60 (both at ARC's no-cache list accounting), and Adapter RHAE − Standard RHAE ≥ 20.

**[RESEARCHER DECISION]** (D14) Proposed: **keep the rule as written** (6 games). In addition, the operational slice (§7.8) flags every eligible game whose published Standard-high run is inferred to have ended before its level's action budget without a win (LP85 is the known case). Flagged games stay in the pool. H4 is also reported without them, as a sensitivity analysis. Cost forecasts for flagged games use the slice's clean-run upper bound, not the published cost (D27). *Trade-off:* keeping the rule avoids a data-dependent change made after seeing the slice, and keeps 2 held-out games. But it may draw a game whose real gap is small: LP85's whole 22.2-point gap is one crashed level, and a complete run could cost about $168 instead of $24. Dropping flagged games removes that risk, but shrinks the pool and the held-out set.

### 7.3 The seeded draw
> **Draw 4** of the 6 with a recorded random seed. [...] The 2 undrawn games become StateCarry held-out games. (PLAN §8.3)
>
> **Draw first.** Run the seeded draw at the PREREG commit, as a permutation of the 6 eligible games: the first 4 are path (dev) games, the last 2 are held out. Never pilot on a held-out game. (PLAN §16.3)

**Procedure** (specification only; the ARC track writes the script):
```python
import random

ELIGIBLE = ["FT09", "SB26", "R11L", "LP85", "SC25", "CD82"]  # PLAN §8.3 order, exactly
SEED = 20261003                                              # D15
perm = random.Random(SEED).sample(ELIGIBLE, k=len(ELIGIBLE))
path_games = perm[:4]   # path study and StateCarry dev set, in this order
held_out = perm[4:]     # StateCarry held-out set, plus the third game (D16)
```
- The draw runs **once**, by a committed script, at the freeze commit, under the project's pinned Python 3.12. The output list, the Python version and the commit go into `results/decisions.md`.
- The **recorded output is authoritative.** Python guarantees only that `random()` reproduces across versions for a given seed, not the algorithms of other methods such as `sample` ([Python 3.12 `random` docs](https://docs.python.org/3.12/library/random.html), "Notes on Reproducibility", checked 2026-09-30).
- **If D14 amends the pool,** `ELIGIBLE` is the PLAN §8.3 order with the removed games deleted. The first 4 are path games and the rest are held out. If fewer than 5 games remain, the ARC design must be amended before any paid ARC run.
- **This draft has not computed the permutation.** Nobody computes it, for this or any candidate seed, before the freeze.

**[RESEARCHER DECISION]** (D15) Seed `SEED = 20261003` (the PREREG target date, as an integer). *Trade-off:* a fixed, date-based seed is simple and auditable, but anyone can compute its permutation in advance, which leaves room to appear to shop for seeds or eligibility rules. A public randomness-beacon value published after the freeze would prevent that, at the cost of an outside dependency.

**[RESEARCHER DECISION]** (D16) Third held-out game: **VC33** (PLAN §9: "VC33 or RE86, fixed in PREREG"). *Trade-off,* from the published high-effort runs (`docs/background.md` §4): VC33 has the larger gap (78.8 vs 72.2 RHAE), a much smaller total action cap (5× the summed human baseline: 2,235 vs 6,275 actions) and fewer Adapter actions (370 vs 840), so its runs are shorter and less exposed to the 12 h clock. Its published Standard run cost more, though ($86.99 vs $48.73). The mean published list cost per run is similar ($63.3 vs $67.6). The operational slice's clean-run upper bound should confirm the choice before freeze.

**[RESEARCHER DECISION]** (D17) The truncated ARC pilot (§11) runs on `perm[0]`, the first path game. *Trade-off:* a seeded choice cannot be steered toward a cheap game, but `perm[0]` may be a short game whose per-action cost says less about long runs. The pilot measures per-action cost, so this matters less than it did for the old full-run pilot.

### 7.4 Runs, seeds, logging and run order
> **Runs:** 4 games × 4 configs (S0, S1, S2, S4) × 2 seeds = 32 runs.
>
> **Log per run:** config hash, fork commit, model string, exit reason (`GAME_WIN`, `ACTION_BUDGET`, `TIME_BUDGET`, `API_ERROR`, `AGENT_ERROR`, …), per-level results, actions, tokens (input, cached, output, reasoning), cost (list and actually billed) and wall clock. (PLAN §8.3)
>
> If it continues, seed-1 S1+S2 and all of seed 2 run as one wave, so the four configs are compared over the same days (Gemini 3.8 Flash has no dated snapshot). (PLAN §16.2)

**Operational.**
- Replicates s ∈ {1, 2}. A re-run of replicate s gets seed s + 100. If the API exposes a sampling seed, it is set to the run's seed and recorded; otherwise the seed only labels the replicate.
- Counted runs are played on ARC's online scorecard. Local or offline play is for testing only (PLAN §16.3).
- The full exit-reason set is `GAME_WIN`, `ACTION_BUDGET`, `TIME_BUDGET`, `SCORECARD_CLOSED`, `API_ERROR`, `AGENT_ERROR`, `UNKNOWN` (`docs/background.md` §2), plus `COST_CAP` if the guard in §7.7 is adopted.

**[RESEARCHER DECISION]** (D18) **Run order.** Block 2's 8 runs run in the order `random.Random(SEED + 2).sample(units, k=len(units))`. Block 3's 24 runs use `SEED + 3` the same way. In both cases `units` is the list of (game, config, replicate) tuples sorted lexicographically. All block-3 runs start within 72 h of each other. *Trade-off:* a random order stops time trends from lining up with configs, which matters because there is no dated snapshot. The cost is that no config can be looked at early, and that is intended.

### 7.5 Error re-run rule
> **Pre-registered rule for errors:** a run ending in `API_ERROR`, `AGENT_ERROR` or `TIME_BUDGET` is re-run once with a new seed. Both runs are reported. (PLAN §8.3)
>
> The tier latency rule, the cost-guard value, the re-run reserve, and whether `TIME_BUDGET` endings are re-run. (PLAN §16.5)

**[RESEARCHER DECISION]** (D19) Proposed operational rule:
- **Re-run once** (new seed): `API_ERROR`, `AGENT_ERROR`, `TIME_BUDGET` (as written), plus `UNKNOWN` and `SCORECARD_CLOSED`, which are not model outcomes.
- **Final as is:** `GAME_WIN`, `ACTION_BUDGET`, `COST_CAP` (§7.7).
- **Counted run:** the re-run replaces the errored run in every primary analysis. If the re-run also ends in a re-run-eligible exit, it is counted as is, with levels cleared before the end scoring normally, and it is flagged. There is no second re-run.
- **Both runs are reported** (as written). A sensitivity analysis scores the original runs as is.

*Trade-off:* replacing errored runs measures each config when the infrastructure works. But S0's longer visible outputs may themselves cause `AGENT_ERROR` (failed parses), which is partly a harness property, and the sensitivity analysis shows that case. Adding `UNKNOWN` and `SCORECARD_CLOSED` treats them as infrastructure; leaving them final would count them against the config.

**[RESEARCHER DECISION]** (D20) **`TIME_BUDGET` is re-run** as written. *Trade-off:* re-running treats slow provider latency as noise. If a config is slow for its own reasons (on ARC, the Standard harness thinks about 2.6× more per turn), its re-run times out again and is counted as is, so a real harness effect is still recorded. The alternative, scoring `TIME_BUDGET` as is, follows ARC's rules more literally but lets latency swings enter the gap.

### 7.6 Service tier
> **[A1]** Flex is uncertain for ARC: Google's target is 1-15 min per call with no fallback. One tier is chosen for all ARC configs by a pre-registered latency rule; runs never switch tier (§16.4). (PLAN §8.3)
>
> **One service tier for all ARC configs,** chosen by a pre-registered latency rule from the M0 probes. No per-run fallback (§15 updated). (PLAN §16.4)

**[RESEARCHER DECISION]** (D21) **Latency rule.**
- **Inputs:**
  1. The Stage-1 Gemini Flex latency probe (PLAN §16.2, ~$3): at least 20 sequential calls at `thinking_level: high`, each with ≥ 100k input tokens of ARC-like frames. At Flex prices (50% off list) this costs roughly $1.4, assuming about 16k output tokens per call.
  2. N_max = 1.5 × the largest published action count, under either harness, among the 4 drawn path games (`docs/background.md` §4).
- **Flex** is chosen iff (p90 Flex seconds per call) × N_max ≤ 6 h, and no probe call failed or took more than 15 min. **Otherwise the standard tier** is used for every ARC config and for phase 2.
- If the standard tier is chosen and the operational slice's median published seconds per action × N_max exceeds 12 h, the researcher is told before block 2.

*Trade-off:* Flex halves cost. But Google targets 1-15 min per Flex call with no fallback (PLAN §16.1), and a `TIME_BUDGET` ending hits configs that make more calls hardest. The 50% margin (6 h of the 12 h clock) protects the comparison, at the cost of ruling Flex out for longer games.

### 7.7 Per-run cost guard
> **Extra harness patches,** kept as files in `arc/`: [...] an optional per-run cost guard (exit `COST_CAP`; the researcher decides whether it is an acceptable, reported deviation); [...] (PLAN §16.3)

**[RESEARCHER DECISION]** (D22) **Adopt the guard at $120 per run** at ARC's no-cache list accounting, computed by the harness from its own configured prices. It applies to every counted ARC run, including S0+StateCarry, whose own calls count. A `COST_CAP` ending is scored as is, not re-run, flagged and reported as a deviation from ARC's protocol. H4 and the StateCarry win are also reported without the units that contain one. *Trade-off:* the guard caps one runaway at $120 list (≤ $60 billed at Flex). But it binds S0 sooner than S4, because the published Standard runs cost more per action at list (1.4× pooled over all 25 games, 1.4-2.4× on the six eligible games). So any `COST_CAP` ending inflates the gap. No guard follows ARC's protocol, and leaves the risk to the block approvals and caps.

### 7.8 Free observational analysis (PLAN §8.1, §16.3)
> **Pull** all Gemini 3.8 Flash runs: 6 variants × 25 games. Also pull any other model that has both harnesses on the public set; check GPT-6 Astra and GPT-6 Sol. Throttle requests and cache the raw files under `results/raw/`.
>
> **Compute:**
> - per-level P(clear | reached) by harness and effort (H5, first pass);
> - input, reasoning and visible tokens per action;
> - compaction frequency;
> - how runs ended, including the exit reason if it is exposed. In the premise check's pull of these endpoints, 11 of 25 Standard-high runs ended before their action budget without a win, vs 5 of 25 on the Adapter. This confound has to be characterised. (PLAN §8.1)
>
> - *Operational slice, before PREREG:* how each published run ended (inferred from per-level action budgets, since exit reasons are not published), seconds per action, cost per action, cached share, a clean-run cost upper bound per game, and a recount of the "11 of 25 early endings". These set the eligibility decision, the cost guard and the re-run reserve.
> - *Hypothesis slice, after the PREREG commit:* H5's per-level P(clear | reached) by harness, plus any exploratory event studies. (PLAN §16.3)

**Operational.** The first "Compute" item (per-level P(clear | reached)) belongs to the hypothesis slice. The operational slice must not compute P(clear | reached) by harness, at any depth. Its outputs feed D14, D16, D21, D22, D27 and D28, and are committed before the freeze.

## 8. StateCarry: phase 2 (PLAN §9)
> 1. Check StateCarry cheaply as an extra PersistGym cell on luna. Does it rescue the far / derived / non-recoverable cells?
> 2. Develop on the 4 path-study games (dev set), with a spend cap of $150.
> 3. Evaluate on held-out games: 3 games (the 2 undrawn eligible games plus VC33 or RE86, fixed in PREREG) × {S0, S4, S0+StateCarry} × 2 seeds = 18 runs. Pilot runs from M0 are never counted as dev or held-out data.
>
> **Pre-registered win:** on held-out games, StateCarry closes at least 50% of the S0→S4 gap, at a mean cost per game no higher than S4's.
>
> **Framing:** we are closing the Standard-to-Adapter gap under ARC's fair-comparison rules, not claiming a new state of the art. (PLAN §9)
>
> Continue to held-out evaluation only if v0 closes ≥ 25% of the S0→S4 gap on dev games at ≤ S4 cost. Otherwise stop the builder and write the analysis paper. (PLAN §11, G3)
>
> Claim wording follows the pre-registered win (≥ 50% of gap at ≤ Adapter cost). Otherwise report it as partial or negative. (PLAN §11, G4)
>
> **Cost basis** for the StateCarry win and G3/G4: ARC no-cache list, billed with caching, or both with one primary. The basis can flip the comparison (high effort: about $80 vs $82 at list, about $74 vs $53 billed). StateCarry's own calls count toward its cost. (PLAN §16.5)
>
> **Optional for phase 2:** run the held-out S0+S4 runs before the StateCarry held-out runs, and pre-register a minimum gap for the StateCarry runs to proceed. (PLAN §16.4)

**Operational.**
- **Closure** C = (R̄_SC − R̄_S0) / (R̄_S4 − R̄_S0). Each R̄ is a mean of RHAE over game-replicate units (a ratio of means, not a mean of per-game ratios). A 90% bootstrap interval over units is reported. As with H4, the claim rests on the point estimate and is descriptive.
- **Cost per game** is the mean over games of the mean over replicates of counted-run cost on the primary basis (D23). S0+StateCarry includes every StateCarry call (promotion, digest). Re-run costs are reported separately and left out of the comparison.
- **StateCarry freeze:** the code commit and config hash of the StateCarry version under test are recorded by a pre-declared amendment ("A-SC", §17) before any G3 evaluation run, and again before any held-out run.

**[RESEARCHER DECISION]** (D23) **Cost basis:** primary = **billed estimate**, from provider-reported cached tokens at the chosen tier's prices. Secondary = ARC no-cache list, also reported. Re-run costs are excluded from the comparison and reported separately. *Trade-off:* billed is what a Standard-harness user actually pays, and the only basis on which StateCarry's cache-friendly layout can pay off. It is also the harder bar. In the published high-effort public-set runs (means over 25 games, `docs/background.md` §4), the Standard harness already costs more than the Adapter when billed with caching (~$74 vs ~$53), while at list the Adapter costs a little more (~$83 vs ~$87; ARC's results page shows ~$80 vs ~$82). List matches ARC's published accounting. Excluding re-runs keeps the comparison on counted runs, but hides a config that errors (and so costs) more often.

**[RESEARCHER DECISION]** (D24) **Gate and claim rules.**
- **G3:** the frozen v0 runs once, with a fresh replicate, on each of the 4 dev games. These 4 runs are compared with the path-study counted S0 and S4 runs on the same games. Continue iff C_dev ≥ 0.25 **and** the cost per game of S0+SC ≤ that of S4. Development runs made before the v0 freeze do not enter G3.
- **Dev cap:** the 4 G3 runs count toward the $150 dev spend cap (PLAN §9). At the published S0 list costs of the eligible games ($11.68-$54.75 per run), 4 runs could take most of that cap at list; the researcher is asked before the cap is exceeded (CLAUDE.md).
- **Held-out order** (PLAN §16.4 option, adopted): the 12 held-out S0+S4 runs go first. The 6 StateCarry held-out runs proceed only if the held-out G ≥ 10 RHAE, the same bar as kill criterion 4. Otherwise closure cannot be estimated, and that is reported.
- **G4 wording:** **win** iff C ≥ 0.50 **and** cost(SC) ≤ cost(S4). **Partial** iff 0.25 ≤ C < 0.50, or C ≥ 0.50 with the cost condition failing. **Negative** iff C < 0.25.

*Trade-off:* a ratio of means is stable when one game's gap is near 0, but lets a large-gap game dominate. Gating the StateCarry runs on a held-out gap ≥ 10 saves the 6 StateCarry runs (a third of the held-out runs) when there is nothing to close, but it adds a decision point. Counting the G3 runs toward the $150 dev cap keeps phase-2 spend inside PLAN's line, but leaves little money for development before v0 is frozen; the alternative is a separate, stated G3 budget.

## 9. Analysis plan (PLAN §10)

### 9.1 Primary PersistGym analysis
> **Primary PersistGym analysis, per model.** Success at the need step, analysed with the fully crossed within-template design.
> - **Primary contrasts (H1-H3):** probability-scale differences of cell means, with 90% and 95% CIs from a cluster bootstrap over templates (10,000 resamples).
> - **Confirmatory model:** logistic regression with template fixed effects, harness × recoverable × derived × distance terms and cluster-robust SEs. This is what the power simulation assumed.
> - **Sensitivity model:** a Bayesian logistic GLMM with template random intercepts (e.g. `bambi`).
> - Report both logit and probability scales. Interactions can flip sign between scales near ceilings; the pre-registered scale for kill rules is the probability scale. (PLAN §10)

**Operational.**
- **Bootstrap:** resample templates with replacement; recompute each contrast from all of the resampled templates' episodes in the contrast's cells; 10,000 resamples; **percentile** intervals; bootstrap RNG seed = SEED + 10.
- **Confirmatory GLM:** `statsmodels` binomial GLM with template dummies and a covariance clustered by template, fitted separately per model. Templates with no outcome variation in the fitted subset carry no within-template information and are dropped from the GLM only; their count is reported. The bootstrap keeps them.
- The Bayesian sensitivity model needs a new dependency (`bambi`), which the analysis track adds with `uv add` and notes in its PR.

**[RESEARCHER DECISION]** (D25) Accept percentile intervals, dropping no-variation templates from the GLM, and the quasi-Poisson log-link model for cost outcomes (§9.5). *Trade-off:* percentile intervals are simple, but can under-cover near 0% or 100%; BCa intervals cover better but are harder to audit. Dropping no-variation templates is standard for fixed-effects logit, but it shifts the GLM's population away from the bootstrap's. PLAN asks for "log-linear models"; a log-link GLM handles zero lookups directly, while OLS on log outcomes would need an offset for zeros and estimates a geometric rather than an arithmetic mean ratio.

### 9.2 Not used
> **Not used:** max−min harness spread. Under the null it rises as success falls; a simulation with no true effect gave an expected 8.7pp at p=0.95 and 16.1pp at p=0.60. If a single "how much does the harness matter" summary is wanted, use a harness variance component with a permutation null. (PLAN §10)

### 9.3 Scales
Every primary contrast is reported on both the probability and the logit scale. Kill and equivalence rules use the probability scale only (PLAN §4, §10). If the two scales disagree in sign, that is reported.

### 9.4 Multiplicity
> **Multiplicity:** Holm correction across the primary confirmatory contrasts (H1, H2, H3). H4 and H5 are descriptive. (PLAN §10)

**[RESEARCHER DECISION]** (D26) **The Holm family has 4 one-sided tests** at a familywise α = 0.05:
1. H1: H0 is Δ_H1 ≤ 0.
2. H2 success: H0 is Δ_der ≤ 0 (sol).
3. H2 tokens: H0 is TE ≤ 0 (sol).
4. H3: H0 is Δ_H3 ≥ 5pp (non-inferiority).

Each p-value is the one-sided percentile-bootstrap p-value from §9.1 (the share of resamples on the null side), on the probability scale; for test 3, on the ratio scale. A hypothesis is called "supported" only if its Holm-adjusted test rejects **and** the model-based estimate agrees: for tests 1 and 2, the confirmatory GLM estimate has the same sign; for test 3, the log-link estimate of §9.5 is above 0; for test 4, a binomial GLM with template fixed effects and an arm indicator (single-turn vs multi-turn) on the H3 cells gives a probability-scale Δ_H3 below 5pp (the confirmatory GLM of §9.1 has no term for the single-turn control).

The §3 readings ("prediction holds", "falsified", "kill", "equivalence") use point estimates or unadjusted 90% CIs, as PLAN writes them; "supported" uses the Holm-adjusted tests. Both are reported, and only "supported" is used for a confirmatory claim. *Trade-off:* splitting H2's "or" prediction into two tests is more conservative than PLAN's three-member family, but it protects both branches. Bootstrap p-values match the probability-scale predictions and kill rules. Logit Wald p-values would match the power simulation's assumptions, but can disagree with them near ceilings.

### 9.5 Cost outcomes
> **Cost outcomes:** tokens, reasoning tokens, lookups and dollars per episode. Use log-linear models with template fixed effects, and report ratios. (PLAN §10)

**Operational.** A log-link Poisson GLM (quasi-Poisson variance) with template fixed effects and template-clustered covariance; the ratio is exp(β). It handles zero counts (lookups) without transformation. Tokens are provider-reported (`usage`). Dollars use the dated price table and are reported both as list and as billed estimate.

### 9.6 Accounting
> **Accounting:** P(carried), P(used | carried) and P(rescued | not carried) by cell, from the survival calculator and string-match logs. (PLAN §10)

Defined in §2.8.

### 9.7 Failure labels
> **Failure labels.** The researcher labels about 100 failure transcripts, stratified by cell, as: never encoded, evicted, misapplied, re-derived wrongly. An LLM judge acts as second rater; report Cohen's κ. (PLAN §10)

**Operational.** About 100 failures are drawn from the main sweep, stratified by harness × task cell, by a seeded sample (SEED + 20). Where the transcript allows, the harness cell is hidden from the labeller. The judge model and prompt are fixed by a pre-declared amendment ("A-judge", §17) before labelling starts. The judge's calls are paid and are logged to `results/costs.csv`.

### 9.8 Power
> **Power.** Simulation in the premise check, with template random-intercept SD 1.0 on the logit scale, success 0.9 → 0.8 across distance, clustered GLM with template fixed effects, 200 reps:
>
> | Templates × distance levels × seeds | Episodes per model per harness pair | Power, 10pp interaction | Power, 20pp interaction |
> |---|---|---|---|
> | 60 × 5 × 2 | 1,200 | 0.23 | 0.57 |
> | 120 × 5 × 2 | 2,400 | 0.39 | 0.88 |
> | 120 × 2 × 2 | 960 | n/a | 0.77 |
> | card's plan, 30 tasks × 5 d × 2 seeds per volume | 600 | about 0.16-0.31 (reported as one range, not split by effect size) | |
>
> Our design uses 2 distance levels that bracket the eviction threshold and ~100 fully crossed templates on luna. Mechanical S=0 effects are tens of points and cheap to detect, so the budget goes to the subtle contrasts (H2, H3, rescue rates).
>
> **Action at M1:** re-run the power simulation with the variance measured in the validity runs, and adjust template counts before the M2 sweep. (PLAN §10)

The sizing rule is in §4.2.

### 9.9 ARC analysis
> - Per game and config: RHAE (mean over 2 seeds), levels cleared, actions relative to the human baseline, tokens and cost.
> - Path shares are (step difference) / (S4 − S0), with a bootstrap over the 8 game-seed units, and the table is labelled descriptive.
> - H5 uses a per-level logistic model of P(clear | reached, depth, harness) with game fixed effects, on the published runs and on ours.
> - Always report exit reasons. (PLAN §10)

The operational versions are in H4 and H5 (§3). Exit reasons are reported per run, including original runs that were replaced by re-runs.

### 9.10 Exploratory analyses
Everything not registered in §3, §8 or this section is labelled **exploratory**. That includes S3, H5 at other efforts or for other models, the event studies, luna's H2 replication, the W/Σ replay pairs, and the per-cell validity rates.

## 10. Gates, kill and equivalence rules (PLAN §11, §14, §16.2, §16.3)
> **Kill criteria in `PLAN.md` §14 are binding.** If one fires, stop that leg and propose the fallback in the plan. Don't quietly extend it. (CLAUDE.md)

Every gate metric is computed by a committed script. The decision, the numbers behind it and the spend to date are written to `results/decisions.md`. **The researcher makes every go/no-go call**; Claude proposes.

### 10.1 G0 (Oct 7)
> Go if: snapshot tests pass; sol's echoed `reasoning.context` matches the request; Gemini S0-S2 run; ARC pilot cost ≤ $30/run with Flex. [...] **[A1]** The cost rule becomes "forecast billed 1b + re-run reserve ≤ $900 at the chosen tier"; the toggle rule adds the replay-use probe; G0 approves only the seed-1 S0+S4 block (§16.2). (PLAN §11)
>
> **G0 toggle rule** adds a replay-use probe (~$2). Turn 1 asks the model to privately pick a 3-digit number and reply only "ready"; turn 2 is filler; turn 3 asks for the number. Both arms send identical payloads; only `reasoning.context` differs. Chance is 1/1000. The probe is excluded from all analyses. (PLAN §16.3)

The text elided from PLAN §11 above gives G0's cost and toggle fallbacks; they are kill criteria 1 and 2 (§10.8) and the fallback list below.

**[RESEARCHER DECISION]** (D37) **The other G0 conditions.**
- **"Snapshot tests pass":** every payload snapshot test, for each PersistGym harness cell (§5) and each ARC config S0-S4 (§7.1), passes at the commit the block-1 runs use.
- **"Gemini S0-S2 run":** in the truncated pilot (§11), S0 reaches 50 actions, S1 reaches its first compaction plus 5 turns, and S2 reaches 30 actions, each on the Interactions API at `thinking_level: high` with the payload accepted and no `API_ERROR` or `AGENT_ERROR` ending. S1's compaction must produce the user-role bridge message. S4 must reach 50 actions, because D27 needs its billed/list ratio.

*Trade-off:* reaching the truncation point is a weak bar; it shows the configs run, not that they run for a full game within the 12 h clock. The $0 offline games with a stub model (PLAN §16.3) cover full-game mechanics without cost.

**[RESEARCHER DECISION]** (D27) **Cost forecast.**
- F = Σ over the 4 path games g and the configs c ∈ {S0, S1, S2, S4} of 2 × L(g, c) × b(c).
- L(g, c) is the per-run list forecast: the published list cost of game g under the Standard harness for c = S0, under the Adapter for c = S4, and the larger of the two for S1 and S2. Where the operational slice infers that the relevant published run ended early without a win, its clean-run upper bound replaces it.
- b(c) is the billed/list cost ratio measured for config c in the truncated pilot, from its provider-reported usage priced at the chosen tier's prices, so it can be computed whichever tier the pilot ran on.
- **Go on cost iff F + reserve ≤ $900**, with the reserve as in D28.

*Trade-off:* published costs understate runs that crashed early, which is why the clean-run bound is used there. Using the bound for every game would be safer, but would probably fail G0 and force the 3-game or medium-thinking fallback. Pricing S1 and S2 at the larger of the two published costs is more cautious than PLAN §16.1, which priced them at the mean of the two: re-derived from the `docs/background.md` §4 table, the list forecast over the 15 possible draws is $764-1,166 (mean $1,015) under the larger-of-two rule, against PLAN's $638-1,054 (mean $896) under the mean rule.

**[RESEARCHER DECISION]** (D28) **Re-run reserve = 20% of F.** G0 thus requires 1.2 F ≤ $900, about $23.4 per run (PLAN §16.3). *Trade-off:* 11 of 25 published Standard-high runs ended early without a win, so a 20% reserve could be too small if our error rate is similar. A larger reserve leaves less forecast room under the cap, and the backoff patches should reduce transport errors.

**[RESEARCHER DECISION]** (D29) **Toggle rule.** The OpenAI toggle on a model is verified iff:
1. the echoed `reasoning.context` equals the request on 100% of that model's pilot responses, in both arms; **and**
2. the replay-use probe passes, with 20 trials per arm: the `all_turns` arm recalls the exact number in ≥ 10 of 20 trials, and the `current_turn` arm in ≤ 1 of 20.

A trial whose visible turn-1 reply contains any 3-digit number is excluded and replaced. If the echo passes but the probe fails, that model's toggle is **not verified**, and the model runs no replay arm. If no API model is verified, kill criterion 1 applies. If luna is verified but sol is not, making luna H2's primary model needs an amendment. The probe's per-arm results are needed for G0; they are not H2's task or outcome, so §11's blinding does not cover them. *Trade-off:* ≥ 10/20 is a lenient bar that tolerates a model that does not always commit to a number in its reasoning. A strict bar (≥ 18/20) is a cleaner certificate, but could reject a toggle that works.

**Fallbacks if the ARC cost rule fails** (PLAN §12, in order):
1. Flex everywhere. For ARC this applies only if D21's latency rule allows Flex.
2. 3 ARC games (D32).
3. Medium thinking. This needs a PREREG amendment, since H4 and the eligibility rule are defined at high effort (PLAN §14, item 2 [A1]).
4. Fewer sol templates (30).

### 10.2 G1 (Oct 14)
> Validity gate (§5) passes. If it fails: one redesign pass until Oct 18. If it still fails: stop PersistGym and continue the ARC leg alone. (PLAN §11)

The gate is defined in §4.4.

### 10.3 Checkpoint C (after block 2; ~Oct 12, latest Oct 14)
> Propose stopping or re-scoping the ARC leg if any of these holds after block 2:
> - the seed-1 mean S0→S4 gap is below 5 RHAE (looser than the G2 kill at 10, because one seed is noisy);
> - more than 3 of the 8 runs still end in an error after one re-run;
> - measured cost per run × 24 × (1 + measured re-run rate) exceeds the remaining 1b cap on the chosen tier.
>
> If it continues, seed-1 S1+S2 and all of seed 2 run as one wave, so the four configs are compared over the same days (Gemini 3.8 Flash has no dated snapshot). (PLAN §16.2)

**Operational.**
- **Gap:** the mean over the 4 path games of RHAE(S4, s=1) − RHAE(S0, s=1), using counted runs (§7.5). The rule fires if this is < 5.
- **Errors:** the number of the 8 counted seed-1 runs whose final exit is re-run-eligible under D19, after their one re-run. The rule fires if this is > 3.
- **Cost:** c̄ is the mean billed cost per run over all block-2 runs, counted runs and re-runs together. ρ is the number of re-runs divided by 8. "Remaining" is $900 minus the billed phase-1b spend to date (pilot spend counts to phase 0). The rule fires if c̄ × 24 × (1 + ρ) > remaining.
- If any rule fires, Claude proposes stopping or re-scoping, and the researcher decides. If the leg continues, the run order follows D18.

### 10.4 G2 (Oct 21)
> G2: kill the ARC leg if the S0→S4 gap is < 10 RHAE points. Overall kill if H1 *and* H2 are inside equivalence bounds *and* the ARC gap is dominated by a mechanism with no provider-neutral analogue: write a short note (survival accounting + ARC path table) and skip Phase 2. Scoop check: if a per-component ARC ablation has appeared, the ARC table stops being the headline. (PLAN §11)

**Operational.**
- **Kill criterion 4:** G = R̄_S4 − R̄_S0 over the 8 counted units (H4) is < 10.
- **Kill criterion 5** requires all three of the following:
  - "H1 inside equivalence bounds" means H1's kill condition holds (§3 H1). See D38.
  - "H2 inside equivalence bounds" means H2's equivalence condition holds (§3 H2). If H2 moved to open weights (kill criterion 1), the condition is read on that run.
  - "Dominated" is defined by D30.

**[RESEARCHER DECISION]** (D38) Read "H1 inside equivalence bounds" as H1's kill condition (Δ_H1 < 10pp and the upper bound of its 90% CI < 15pp). *Trade-off:* PLAN gives H1 a kill rule but no separate equivalence rule, and the kill rule is the closest bound it states. A symmetric rule (for example, the 90% CI of Δ_H1 inside ±10pp) would be stricter and would fire less often.

**[RESEARCHER DECISION]** (D30) **"Dominated by a mechanism with no provider-neutral analogue"** means **σ_replay ≥ 2/3** as a point estimate. Here σ_replay is the share of the S2→S4 step, which bundles native replay with the native item format and is the only step with no provider-neutral analogue. *Trade-off:* at 2/3, the provider-neutral steps (loss policy plus notes) carry at most a third of the gap. A bar of 1/2 (Prediction B) would skip phase 2 more readily. Also requiring the bootstrap lower bound to be ≥ 1/2 would make the kill nearly impossible to trigger with 8 units.

### 10.5 Scoop rule (kill criterion 6)
> **Any time.** A per-component ablation of ARC's gap appears (ARC Prize, OpenAI or others) → the ARC table becomes supporting material. Lead with PersistGym + StateCarry. (PLAN §14)

**[RESEARCHER DECISION]** (D31) **"A per-component ablation"** is a public document (paper, preprint, blog post, results page or merged PR) that reports ARC-AGI-3 scores, on any model, for at least two harness configurations differing in exactly **one** of {loss policy, notes instruction, reasoning replay}, under ARC's harness or a fork of it. OpenAI's Jul 29 post (combined effect only) does not qualify. *Trade-off:* "exactly one component" is a narrow trigger, so a partial ablation (for example, replay plus compaction toggled together on several models) would not fire it, even though it erodes the novelty. A broader trigger would fire on work that does not actually decompose the gap.

### 10.6 3-game fallback
> How a game is dropped under the 3-game fallback (seeded, not by cost). (PLAN §16.5)

**[RESEARCHER DECISION]** (D32) If the 3-game fallback is triggered, **drop `perm[3]`**, the last path game in the draw. If it has already been run, its runs are reported as exploratory and it stays a dev game. Otherwise it is set aside (neither path nor held-out) unless the researcher decides otherwise at G2. H4, Checkpoint C and kill criterion 4 then use the 3 remaining path games (6 units instead of 8), with the same thresholds; Checkpoint C's cost rule then counts 18 remaining runs instead of 24, and its error rule 6 seed-1 runs instead of 8. *Trade-off:* a position-based drop is fixed at the draw and cannot be steered by results or costs, but it may drop the game with the cleanest measurement.

### 10.7 G3 and G4
Defined in §8 (D24).

### 10.8 Kill criteria, consolidated (as written)
> 1. **G0.** No verifiable replay toggle on any API model → H2 runs on open weights only (E1). If E1 also fails, drop H2 and state it as a limitation.
> 2. **G0.** ARC pilot > $30/run with Flex → 3 games or medium thinking. If it is still > $30/run, drop the ARC runs and keep the free observational analysis. **[A1]** The trigger becomes "forecast billed 1b + re-run reserve > $900 at the chosen tier" (about $23.4/run with a 20% reserve), re-checked at Checkpoint C (§16.2). Medium thinking would need a PREREG amendment, since H4 and the eligibility rule are defined at high effort.
> 3. **G1.** PersistGym fails the validity gate after one redesign → stop PersistGym and continue ARC alone.
> 4. **G2.** S0→S4 gap on the 4 games < 10 RHAE points → kill the ARC path leg.
> 5. **G2.** H1 and H2 both inside equivalence bounds, *and* the ARC gap is dominated by a mechanism with no provider-neutral analogue → publish a short note, no builder.
> 6. **Any time.** A per-component ablation of ARC's gap appears (ARC Prize, OpenAI or others) → the ARC table becomes supporting material. Lead with PersistGym + StateCarry.
> 7. **G3.** StateCarry v0 closes < 25% of the gap on dev games → stop the builder and write the analysis paper. (PLAN §14)

## 11. Pilots and pilot blinding (PLAN §16.3, §16.5)
> **Pilot blinding:** pilots report only validity levels, pooled tokens, errors, latency and cost; never per-arm success, per-arm reasoning tokens (H2's token outcome) or per-config ARC level progress. Pilot templates use a disjoint seed range. (PLAN §16.5)
>
> **Truncated ARC pilot** on one drawn path game replaces the FT09 full-run pilot: S0 and S4 to 50 actions, S1 to its first compaction plus 5 turns, S2 to 30 actions. (PLAN §16.3)
>
> Pilot runs are excluded from all analyses. (PLAN §11)

**Block 1 contents** (PLAN §16.2): the OpenAI `reasoning.context` echo check (~$0.35); the replay-use probe (~$2); Gemini payload acceptance and the Flex latency probe (~$3); the truncated ARC pilot on `perm[0]` (D17; ~$13 Flex / $26 list); luna and sol pilots, and the validity runs.

**Operational.**
- Pilot reports come from committed scripts that output only the allowed fields: validity levels; pooled tokens (summed over arms); errors; latency; cost; echo-match rate; for ARC, cost per action, tokens per action, compaction occurrence and exit status.
- No script, person or agent computes per-arm success, per-arm reasoning tokens or per-config ARC level progress (levels cleared, RHAE) from pilot data. Raw pilot transcripts stay in `results/raw/` and are not read for those quantities.
- **Exempt,** because they are toggle checks rather than H2's task or outcome: the per-arm echo-match rate and the replay-use probe's per-arm recall (D29).
- Validity runs report validity levels (oracle, restated, withheld) as allowed. They are not main-cell success.
- Pilot templates use seeds 90,000-99,999 (D7). Pilot ARC runs are never counted as dev or held-out data.

## 12. Staged spending approvals and caps (PLAN §12, §16.2)
> Each block needs the researcher's explicit approval, recorded in `results/decisions.md`. Approving one block never carries over to the next. (PLAN §16.2)
>
> | Block | When | Estimate | Paid to | What it buys | Decides |
> |---|---|---|---|---|---|
> | Stage 0 | now to ~Oct 3 | $0 | nobody | Operational free ARC analysis; PREREG and the seeded draw; ARC fork patches and payload snapshot tests; offline ARC games with a stub model; PersistGym build and $0 validity checks; cost model and power re-simulation | Inputs to every later block |
> | 1. Pilots | after PREREG is committed and snapshot tests pass (~Oct 3-7) | ~$42-76 | OpenAI ~$26-47, Google ~$16-29 | OpenAI `reasoning.context` echo check (~$0.35); replay-use probe (~$2); Gemini payload acceptance and Flex latency probe (~$3); truncated ARC pilot on one drawn path game (~$13 Flex / $26 list); luna and sol pilots and validity runs | G0 (Oct 7) |
> | 2. Seed-1 S0+S4 | after G0 (Oct 8-12) | $62-132 at Flex or $125-263 on the standard tier, plus up to $60 of re-runs | Google | 8 counted runs on the 4 drawn games: the first fresh-seed gap, real run cost, and how runs end | Checkpoint C |
> | 3. Commitment | Checkpoint C (~Oct 12; latest G1, Oct 14) | +$0.54-0.79k at Flex or +$0.76-1.15k on the standard tier (up to $1.37k at no-cache list) | Google, OpenAI | The other 24 ARC path runs plus reserve; the PersistGym main sweep | G2 (Oct 21) |
> | 4. Phase 2 | G2 / G3 | ~$0.46-1.1k | Google, OpenAI | StateCarry dev and held-out runs | G3, G4 |

**Hard caps** (PLAN §12; stop and ask the researcher before exceeding any of them): phase 0 $100; phase 1a (PersistGym) $450; phase 1b (ARC path) $900; phase 2 $950.

**Operational.**
- Every paid call batch is logged to `results/costs.csv` (CLAUDE.md). The file is summed and compared with the cap before each block.
- Provider-side spend limits back up the stop-and-ask rule (PLAN §16.1).
- Paid calls are made only under a frozen (non-draft) PREREG version.
- All Gemini ARC runs finish before 2026-12-31 (PLAN §8.3, §11).

## 13. Exclusions, errors and deviations

**[RESEARCHER DECISION]** (D33) **PersistGym episode handling.**
- **OpenAI echo mismatch:** the episode is excluded (CLAUDE.md). If a cell exceeds 5%, the run stops and the researcher is told.
- **Transport failure after the harness's retries** (HTTP 429/5xx, timeouts): the episode is re-run once with the same template and seeds. A second failure means exclusion. Counts are reported per cell.
- **Content failures** (unparseable, invalid or refused actions; an `incomplete` response at the need step) score 0 and are not re-run.
- Episodes are analysed by their **assigned** cell. `S_planned` ≠ `S_verbatim` mismatches are reported, not excluded (but see the bug stop in §2.8).

*Trade-off:* re-running transport failures keeps the cells balanced, but repeats a template's exposure in that cell. Excluding them instead risks unbalanced, informative missingness if failures cluster in long-context cells.

**ARC runs:** errors follow §7.5 and the cost guard follows §7.7.

**Deviations** from this PREREG are logged in `results/decisions.md` with the date and reason, and are listed in every write-up.

## 14. Extensions (PLAN §9)
Extensions are **not** pre-registered here, apart from the two rules carried over below. Each one needs a dated amendment fixing its settings before its first paid run.
- **E1** (open-weights replay): if it moves into the MVP under kill criterion 1, H2's predictions, falsification and equivalence rules apply unchanged to Qwen3.6-27B with `preserve_thinking` on vs off. The serving settings are fixed by amendment.
- **E3** (Terminal-Bench cost win), as written: "Pre-registered win: success within ±3pp and at least 15% fewer tokens." (PLAN §9)
- E2, E4, E5 and E6 have no pre-registered predictions.

## 15. What this pre-registration does NOT claim
- **It is not a model comparison.** Nothing here ranks models or vendors, and no result is stated as "model X beats model Y". Figures plot effects against task properties.
- **The ARC results are conditional and narrow.** They concern 4 public games drawn from a pool chosen for large published gaps and low published cost: Gemini 3.8 Flash at high thinking on the Interactions API, measured in a 2026 window with no dated snapshot. They say nothing about the Semi-Private or private sets, about other efforts or models, or about frontier models.
- **The path decomposition is order-dependent and descriptive.** The S2→S4 step bundles native replay with the native item format, so no share is attributed to replay alone. With 8 game-seed units, no significance is claimed.
- **It does not explain ARC's published gap.** The published runs are one-seed screens, may have used a different API surface, and include early endings. Our runs re-measure the gap; they do not audit those runs.
- **PersistGym is synthetic.** Its results are not claimed to transfer to coding agents, ARC or real tasks without separate evidence. Window effects at S = 0 are mechanical and are not findings in themselves.
- **Opaque replay is not inspected.** What a model "sees" in encrypted reasoning items cannot be observed. Toggle validity rests on the echoed field and the replay-use probe.
- **Equivalence is not absence.** "Inside equivalence bounds" means the effect is within the stated bounds at the stated confidence. It does not mean there is no effect, and an underpowered result is called inconclusive.
- **StateCarry is not claimed to be new as an idea.** Ledger-style state and reasoning replay already exist (Ledger 2608.00808, the Kaggle "Duck" baseline, public Kaggle ablations). The claim is limited to closing the Standard-to-Adapter gap under ARC's rules on held-out games. It is not a state-of-the-art claim, and a coding success win would not be new.
- **Costs are period-specific.** They are estimates at the prices checked on 2026-09-29/30. Gemini 3.8 Flash prices double on 2027-01-01.
- **H5 on published runs is observational and not blind.** It cannot separate depth from game difficulty beyond game fixed effects. Per-game scores were seen before this pre-registration, and the operational slice reveals where each published run ended (§3 H5). Only H5 on our own runs is a test on unseen data.

## 16. Decision register
Every item below is marked **[RESEARCHER DECISION]** in the text. D1-D33 appear in the text in this order; D34-D39 were added in review and sit in the sections listed. The researcher accepts, changes or strikes each one before freeze.

| ID | Section | Item | Proposed |
|---|---|---|---|
| D1 | §2.3 | Observed-fact wording | Key-value binding in one observation; value string banned elsewhere except 3 exceptions; 2 distractor bindings |
| D2 | §2.4 | Derived-fact wording | Evidence set includes the rule; all K options consistent under any proper subset of clues; m = 2/3 split 50/50 |
| D3 | §2.5 | Recoverable wording | Generic `lookup(key)` over any earlier key; one extra step; cap 3 |
| D4 | §2.6 | Needed and success | Score the first non-lookup action at the need step; invalid output = 0 |
| D5 | §2.7 | Near/far | Far: sys + O(r_last, n) > W; near window [n−6, n−1], R_plan = 1,000; same T and n in all 8 task cells of a template; tokenizer `o200k_base` |
| D6 | §2.8 | Survives (S) | Whole-word match of value or all clues; replayed reasoning not counted in W; stop on window-accounting bugs; expected near losses > 2% in pilots trigger re-tuning |
| D7 | §2.9, §11 | Seed ranges and repeats | Main 1-49,999; validity 50,000-59,999; pilots 90,000-99,999; primary analysis on repeat 0 |
| D8 | §3 H1 | H1 token and lookup reading | Difference-in-differences token ratio ≥ 1.30; zero-lookup rule |
| D9 | §3 H2 | H2 token measure and readings | Need-step reasoning tokens; point estimates; sol only in Holm; "signal" = not falsified |
| D10 | §3 H3 | H3 control and test | NR cells; oracle replies; F-0; one-sided 90% CI upper bound ≤ 5pp |
| D11 | §4.2 | W, v and template-count tuning | Power target 0.80 within caps; otherwise "inconclusive" |
| D12 | §5 | Summary-cell trigger and bridge | Summarize before sending if the payload > W; replace all earlier turns |
| D13 | §6 | Reasoning effort and settings | `medium`, `standard`, explicit `reasoning.context`, `max_output_tokens` 32,000, OpenAI Flex |
| D14 | §7.2 | Eligibility rule | Keep as written; flag inferred crashes; sensitivity analysis without flagged games |
| D15 | §7.3 | Draw seed | 20261003, run once at the freeze commit |
| D16 | §7.3 | Third held-out game | VC33 |
| D17 | §7.3 | Truncated-pilot game | `perm[0]` |
| D18 | §7.4 | Run order and wave | Seeded orders (SEED+2, SEED+3); block 3 starts within 72 h |
| D19 | §7.5 | Error re-run details | Add `UNKNOWN`/`SCORECARD_CLOSED`; the re-run is the counted run; no second re-run |
| D20 | §7.5 | `TIME_BUDGET` handling | Re-run once (as written) |
| D21 | §7.6 | Tier latency rule | Flex iff p90 × 1.5 × max published actions ≤ 6 h and no probe call > 15 min; else standard tier |
| D22 | §7.7 | Cost-guard value | $120 per run at list; `COST_CAP` scored as is and reported |
| D23 | §8 | Cost basis for StateCarry and G3/G4 | Billed estimate primary; list secondary; re-run costs excluded |
| D24 | §8 | Closure, G3, held-out order, G4 wording | Ratio of means; G3 runs count toward the $150 dev cap; held-out S0+S4 first with gap ≥ 10; win/partial/negative bands |
| D25 | §9.1, §9.5 | Bootstrap, GLM and cost-model details | Percentile intervals; drop no-variation templates from the GLM only; quasi-Poisson log-link for cost outcomes |
| D26 | §9.4 | Holm family | 4 one-sided bootstrap tests; model-based estimate must agree (H3: arm GLM below 5pp); "supported" vs "prediction holds" kept apart |
| D27 | §10.1 | G0 cost forecast formula | Published cost (S1/S2: larger of S0 and S4), or clean-run bound if crashed, × pilot billed/list ratio at the chosen tier |
| D28 | §10.1 | Re-run reserve | 20% of the forecast |
| D29 | §10.1 | Toggle rule and probe thresholds | 100% echo match; probe ≥ 10/20 vs ≤ 1/20 |
| D30 | §10.4 | Numeric "dominated" | σ_replay ≥ 2/3 (point estimate) |
| D31 | §10.5 | Per-component ablation (kill criterion 6) | Isolates exactly one of loss / notes / replay on ARC-AGI-3 |
| D32 | §10.6 | 3-game fallback drop rule | Drop `perm[3]`; H4, Checkpoint C and kill criterion 4 on the 3 remaining games |
| D33 | §13 | PersistGym episode errors and exclusions | Echo → exclude (5% stop); transport → one re-run; content → 0 |
| D34 | §3 H4 | H4 readings | Predictions A/B on point estimates; shares withheld if G < 10 RHAE |
| D35 | §3 H5 | H5 operational choices | Reached = ≥ 1 action; bands 1-2 vs ≥ 4; probability-scale AME with game-cluster bootstrap; high effort only on published runs |
| D36 | §4.6 | Run matrix | luna: 4 replay-off cells first, replay cells only on a verified toggle; sol: F-r vs F-0, W/Σ pairs only on "signal"; both controls on all 8 task cells (luna) |
| D37 | §10.1 | Other G0 conditions | All payload snapshot tests pass; truncated S0-S2 (and S4) reach their stopping points without API/agent errors |
| D38 | §10.4 | Kill criterion 5, H1 reading | "H1 inside equivalence bounds" = H1's kill condition |
| D39 | §4.3, §4.4 | Controls and validity details | Restated derived = clues + rule; withheld = equal-length distractors; validity in F-0; LLM thresholds pooled; heuristic baselines defined and applied per task cell |

## 17. Amendment log
No amendments yet (draft). Pre-declared amendments, each merged by PR before the event it guards:
- **A-cfg:** the config freeze record (§7.1), before the first block-2 run.
- **A-SC:** the StateCarry code commit and config hash, before any G3 evaluation run and again before any held-out run (§8).
- **A-judge:** the LLM-judge model and prompt, before failure labelling (§9.7).

Values set by a pre-registered rule (W, v, template counts, chosen tier, draw output) are recorded in `results/decisions.md`. They are not amendments.
