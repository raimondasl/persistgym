# PersistGym-lite generator: design

_Track: M0 PersistGym build (PLAN.md §5, §6; amendment A1 §16.3 and §16.5). Generator version 0.2.0, episode schema 2. Everything here is $0: no API calls._

_0.2.0 (researcher decisions of 2026-10-01 on the PREREG draft; D-numbers refer to its decision register):_
- _D1: every episode carries 2 distractor bindings about other entities (§2);_
- _D2: the options are one cluster of consecutive values, so no proper subset of the clues narrows them, and partial memory is a gated validity check (§2, §9); the number of clues is split exactly 5/5 within each block of 10 templates (§6);_
- _D3: lookup serves the distractor keys too; a key without a record answers "no such record"; a lookup over the cap answers "lookup unavailable" for one turn instead of being scored wrong (§4);_
- _D4: the two parser rules are documented as pre-registered (§4);_
- _D5: the system prompt counts toward W (§8, §11);_
- _D6: P(carried) uses the PREREG whole-word regex, with no proximity window and no rule requirement (§8);_
- _D7: seed ranges main [0, 50,000), validity [50,000, 60,000), pilot [90,000, 100,000), in whole blocks of 10 templates (§6)._

_0.1.1 (review of PR #7): a biobank site no longer contains an entity name; a lookup key matches when it contains the entity name as a word; single-turn controls come from non-recoverable cells only and have a scorer; a partial-memory diagnostic is reported._

PersistGym-lite generates multi-turn episodes in which one target fact is needed at a known step. Each template is rendered into 8 task cells that vary three things one at a time, at a fixed token volume per observation:
- **observed vs derived:** the fact is shown verbatim once, or it must be computed from 2-3 clues plus a combining rule and is never shown in final form;
- **recoverable vs not:** a `lookup` action can re-show the records (costing one turn), or nothing can;
- **near vs far:** the latest reveal is 4 steps before the need step, or beyond the eviction threshold W counting observation tokens only.

The harness cells (F, W, Σ; notes and replay flags) are a separate track. This package gives them episodes, a runner with exact lookup semantics, oracles, survival accounting and validity checks. Every place where a PREREG definition matters is a named config field, listed in §11 and tagged **[RESEARCHER DECISION]**.

## 1. Quick start
```
uv run python -m persistgym render --n 20                    # main split, templates 0-19
uv run python -m persistgym render --split validity --n 10 --single-turn --gzip
uv run python -m persistgym render --n 50 --W 24000 --v 1500 --set assumed_max_reply_tokens=800
uv run python -m persistgym render --split pilot --n 2 --partial-blocks   # quick $0 look
uv run python -m persistgym partial-memory --n 2000          # templates only, no rendering
uv run pytest -q persistgym && uv run ruff check persistgym
```
`--start` and `--n` must be multiples of the balance block K = 10 (PREREG D7); `--partial-blocks` lifts this for quick checks.

`render` writes to `results/raw/persistgym/<split>-<start>-<n>-<confighash8>/` (gitignored):
- `episodes.jsonl[.gz]`: one Episode per line (§10);
- `single_turn.jsonl[.gz]`: position-matched single-turn controls for the 4 non-recoverable cells (with `--single-turn`);
- `summary.json`: per-cell shape, the shortcut and lookup audits, the heuristic baselines, oracle scores and the partial-memory gate per derived cell;
- `manifest.json`: config, config hash, generator version, seed ranges, tiktoken version, git commit and dirty flag.

The exit code is 1 if any validity check fails. A rendered episode is about 110 KB of JSON at the defaults (8 cells × 3 variants per template); 60 templates with `--gzip` take about 28 MB.

In Python:
```python
from persistgym import GeneratorConfig, ALL_CELLS, sample_template, render_template, EpisodeEnv
cfg = GeneratorConfig()
t = sample_template("main", 0, cfg)
eps = render_template(t, cfg, ALL_CELLS, ("base", "restated", "withheld"))
env = EpisodeEnv(eps[0]); obs = env.observation
obs, done = env.step("...model reply...\nACTION: route(billing)")
```

## 2. Episode structure
An episode is a fixed script of `n_steps` steps, indexed from 0. Every step is one observation, sent as a new user message, and expects one action. The need step index `n` is sampled per template from `need_index_range` (default 20-24); 0-2 routine tail steps follow it, so episodes have 21-27 steps at the defaults.

**Observation layout** (every observation, exactly v tokens):
```
=== console update 16:17:23 ===
--- log tail (earlier lines omitted) ---
06-14T16:17:06Z DEBUG lims-api cache hit_ratio=0.54 keys=49067      <- first line cut at a token boundary
...realistic service logs, chronological...
--- end of log ---
EVENT: <the event text>
```
The system prompt (not an observation) says that logs never need a response, that the reply's last line must be `ACTION: <action>`, and, if `warn_future_need`, that "Some requests depend on records shown in earlier updates." In recoverable cells it also describes `lookup`.

**Step types** (`Step.kind`, plus `Step.routine_type`):

| kind | routine_type | Event (example) | Expected action |
|---|---|---|---|
| routine | `route` | `Ticket T-2940 arrived with tag 'customs'. Route it to the team named by its tag: reply route(<tag>).` | `route(customs)` |
| routine | `threshold` | `Sensor S2 reports fan speed 3161 rpm; the limit is 2778 rpm. Reply alert(S2) if ... otherwise reply ok(S2).` | `alert(S2)` |
| routine | `broadcast` | `Broadcast BX-K5FY from the change board. Reply ack(BX-K5FY) to acknowledge it.` | `ack(BX-K5FY)` |
| reveal | `memo` | `Intake memo M-4062. For sample LINDEN, the freezer slot is 310. Reply ack(M-4062) to acknowledge it.` | `ack(M-4062)` |
| distractor | `memo` | `Intake memo M-4271. For sample ROWAN, the freezer slot is 643. Reply ack(M-4271) to acknowledge it.` | `ack(M-4271)` |
| need | — | `Sample LINDEN needs its freezer slot now. Options:` / `A) 310` ... `J) 305` / `Reply store(<letter>) with the letter of the correct option.` | `store(A)` |

Routine actions depend only on the current observation; the dependency graph records this (§7). Reveal and distractor steps are acknowledged like broadcasts, so they need no memory either. Only the need step depends on the past.

**Options (PREREG D2).** The K = 10 options are **one cluster of consecutive 3-digit values** (`option_spacing` = 1), listed with letters A-J in a seeded order. The target sits at a block-balanced rank r in the cluster: sorted, the options are target − r, ..., target + 9 − r. The cluster's lowest value is uniform over `value_range` (300-899) whatever r, so the values say nothing about the rank. A memory or arithmetic slip of a few units therefore lands on a wrong option rather than on a value that is not offered.

**Observed facts:** one record, `For sample LINDEN, the freezer slot is 310.`

**Derived facts:** 2 or 3 clue records on consecutive steps (`clue_spacing_steps` = 1), e.g. `the rack slot is 220`, `the shelf offset is 90`, plus the rule `Rule: for every sample, freezer slot = rack slot + shelf offset.` The rule is shown with the last clue by default (`rule_placement`). The combining operation is always a sum; changing it is a code change. The target never appears before the need step in a derived episode (audited).
- **Clue values.** Each addend (offset, shift) is core + r × spacing, with the core uniform in [61, 89] (`minor_component_range` 61-98 minus room for the cluster, `GeneratorConfig.addend_core_range`); addends are drawn independently and may be equal. The base clue (3-digit) is what is left of the target. Every addend therefore lies in [61 + r, 89 + r]: with the rule and **any proper subset of the clues**, every one of the 10 options has a completion of the missing clues within the clue ranges (base 100-999, addends 61-98), so no option can be ruled out (§9). No clue value is ever an option.

**Distractor bindings (PREREG D1).** Each episode shows `n_distractors` = 2 bindings about other entities of the same kind, in the target's sentence frame and from the same record source as an observed fact (`For sample ROWAN, the freezer slot is 643.`). They are never needed. Their values come from `value_range` and are neither options nor clue values. They sit at steps that hold no evidence in any of the 8 cells (sampled per template from the steps between `lead_in_min_steps` and n − 1), so every cell and variant shows them at the same steps in the same words. They keep the target binding from being the only record about an entity, and they give `lookup` keys other than the target (§4). Because their values are never options, a model that binds a distractor's value to the target answers with a value that is not offered.

**Surface stories (skins).** Five skins (warehouse, biobank, datacenter, archive, depot) change nouns only: facility, entity names, quantity and clue names, record sources, routine tags, sensor metrics and log service names. Every sentence uses the fixed frames in `render.py`, which the oracle parses.

## 3. Task cells and variants
`TaskCell(fact, recoverable, distance)`; ids like `derived-rec-far`. All 8 cells of a template share:
- the need step index, the need event, the options, the correct letter and the correct value;
- the routine event and log filler of every step index (identical observation text wherever both cells have a routine step);
- the distractor bindings: same steps, same observation text;
- the clock and the system prompt, except for the lookup paragraph in recoverable cells (and the standing rule in derived cells when `rule_placement` is `system_prompt`).

Within a template, the need observation is byte-identical across all 8 base cells and the withheld cells (audited).

| | where the components are revealed | lookup |
|---|---|---|
| near | latest component at `n - near_gap_steps` (n−4); earlier clues at n−5, n−6 | — |
| far | latest component at `n - far_gap_steps` (n−16 at the defaults); earlier clues at n−17, n−18 | — |
| recoverable | (same placement) | `lookup(<name>)` re-shows records; system prompt explains it |
| not recoverable | (same placement) | `lookup` is an invalid action |

**Far** (amendment §16.5): observation tokens from the latest reveal step through the need step, inclusive, exceed `W_tokens + far_margin_tokens`. `far_gap_steps = floor((W + margin) / v)`. At the defaults that is 16: 17 observations × 1,500 = 25,500 > 24,000. This counts observation tokens only, which is stricter than the PREREG inequality sys + O(r_last, n) > W and implies it (PREREG D5). Since replies only add tokens, every component is evicted by a drop-oldest window of W whatever the replies are. **Near:** every component survives the window when the system prompt counts toward W (D5) and each reply has `assumed_max_reply_tokens` (1,000) tokens. At the defaults the earliest near component is at most 6 steps back (sys + 7 observations + 6 replies ≤ 150 + 16,500 ≤ 24,000). The generator refuses to emit a cell that breaks either rule, and the audit re-derives both from the text.

**Variants** (`Episode.variant`):
- `base`: the cell as described.
- `restated`: the need event starts with `Records on file for sample LINDEN:` and repeats the records (`restate_mode`: as revealed by default, so derived facts still need combining). This is the ceiling with memory taken out of the problem (validity gate: LLM ≥ 85%).
- `withheld`: every reveal record is replaced by a null record from the same source with the same id and no value (`Sample LINDEN has been logged at intake.`). The step structure is unchanged, the distractor bindings stay, and `components` is empty (validity gate: LLM ≤ chance + 10pp).

**Position-matched single-turn control** (`controls.single_turn_control`, H3): the same observations 0..n, with replies between them, flattened into one user message after a one-line preamble. Replies default to the minimal correct reply `ACTION: <expected>` (`single_turn_reply_mode`). Passing a real run's replies yokes the control to that run. The result records each component's token offset in the flattened prompt and in the multi-turn message contents. The two differ only by the separator tokens (`<<< update >>>`, `<<< operator reply >>>`) and the preamble.
- It is built from **non-recoverable** base episodes only. A recoverable cell has the same observations, and its system prompt offers `lookup`, which a single prompt cannot serve, so its control would differ only by offering an action that cannot work. Compare it with the multi-turn non-recoverable cell.
- `controls.score_single_turn(control, reply)` scores a reply exactly as `EpisodeEnv` scores the need step (same parser, letter or value).

## 4. Lookup semantics (exact; `env.EpisodeEnv`; PREREG D3)
- Lookup is available only in recoverable cells. At most `lookup_max_per_episode` (3) lookups are **served** per episode.
- When the reply's action is `lookup(<key>)`, the pending step is **not** scored and does not advance. The next observation is a lookup response, padded to v tokens like any observation, and it ends with `Pending request (repeated): <the pending step's event>`. The agent then answers the repeated request. **A lookup therefore costs exactly one extra turn and v tokens.**
- **Keys.** Every binding has a key, the entity it is about: the target entity or one of the 2 distractor entities (`LookupSpec.record_keys`). A key matches an entity if it contains the entity name as a whole word, ignoring case (`BEECH`, `beech`, `sample BEECH`, `key="BEECH"`, `sample:BEECH` and `BEECH's slot` match; `BEECHES` and `sampleBEECH` do not). The key is matched as the agent wrote it, whatever its length; only the echo in a "no such record" reply drops punctuation and keeps at most 40 characters. Entity names are single distinct words, so the match never confuses the target with a distractor, and formatting slips do not add turns and tokens that are not about memory (H1's cost outcome).
- **Served lookup.** The response starts `LOOKUP RESULT for sample LINDEN:` and re-shows, verbatim as originally displayed and in display order, every record shown at or before the pending step about a matched entity: the fact record, or every clue record with the rule (records that share a step are merged into one line), or a distractor's binding. A key that names several entities re-shows all of their records. A key with no such record shown so far, whether it never appears or appears later, gets `LOOKUP RESULT for '<key>': no such record.` and still costs the turn and counts as a lookup.
- **Over the cap.** Once 3 lookups are served, the next lookup at a pending step gets `LOOKUP RESULT: lookup unavailable. All 3 lookups allowed per session have been used.` and the pending request again. It costs one turn, is counted in `n_lookups_unavailable` (not in `n_lookups`), and is not an answer, so the pending step is still scored on the agent's next action. A second over-cap lookup at the same pending step is an invalid action (`invalid_lookup`, scored wrong); this keeps episodes finite. So a lookup habit costs turns and tokens, not success, as long as the agent answers after being told.
- In non-recoverable cells `lookup` is not offered and is an invalid action: the pending step is scored wrong (`invalid_lookup`), the episode advances and no extra turn is added.
- Lookup observations are deterministic: same template seed, pending step and lookup number give the same text. `render.renderer_for(episode)` rebuilds the renderer from `template_seed` and `config`, so this also works for episodes loaded from JSONL.

**Scoring** (pre-registered under PREREG D4). The action is the last `ACTION: verb(arg)` line. If there is none and `strict_action_parse` is false (the default), the last `verb(arg)` with a known verb anywhere in the reply counts. A reply with no parseable action is scored wrong (`unparsed`), with no re-prompt. At the need step the verb must be the episode's `need_verb`, and the argument may be the letter or, with `accept_value_answers` (the default), the option value. After lookups the first non-lookup action at the need step is scored. `EpisodeResult` gives need success, routine accuracy, the lookups served and the step at which each was used, the over-cap lookups, the number of turns, per-step outcomes and per-turn observation tokens.

## 5. Token budget and filler
- One tokenizer, tiktoken `o200k_base`, is used for generation and window accounting. Provider-reported tokens differ by per-message overhead; the harness logs both.
- Every observation, including lookup responses, has exactly `v_tokens` tokens (`token_tolerance` 0; audited by re-counting). The filler is a token-level suffix of a per-slot pool of chronological log lines, so the earliest kept line is cut as a log tail would be. If a BPE merge at the cut makes v unreachable, the pool's newest line is dropped (at most 3 times) to shift the alignment.
- The filler pool of step t is seeded by (template seed, t), so cells share it. Its clock times lie in (T(t−1), T(t)], with `step_seconds` = 75. Lookup responses at pending step t use slots of 15 s after T(t) (slot j for the j-th lookup, slot 3 for "lookup unavailable").
- **Reserved strings** never appear in filler or routine text: every option value, every clue value, every distractor value, the target and distractor entity names, the quantity name and the clue names. Numbers are matched unless embedded in a longer digit run; words are matched case-insensitively unless embedded in a longer word. Filler lines that would contain one are resampled. The audit re-checks this independently from the text.

## 6. Templates and seeds (PREREG D7)
- Template `i` of split `s` has seed `SEED_RANGES[s][0] + i`. The ranges are half-open and disjoint: `main` = [0, 50,000), `validity` = [50,000, 60,000) (validity runs and the G1 spot-check), `pilot` = [90,000, 100,000) (amendment §16.5: pilot templates use a disjoint seed range). Main templates are taken in order from index 0. Template ids look like `main-000017`, `validity-000003`.
- Every random choice uses a named stream `random.Random(f"pg:{seed}:{stream}")`, so adding a stream never shifts the others. String seeding is SHA-512 based and does not depend on `PYTHONHASHSEED`.
- **Balance by construction:** template `i` is in block `i // K` (K = 10), so blocks start at each range start. Within each block, every letter is correct exactly once, every rank of the target in the cluster occurs exactly once, and the number of clues is split as evenly as the choices allow: exactly 5 templates with 2 clues and 5 with 3 (PREREG D2 (c)). Each block uses its own seeded permutations, so the three are independent of each other.
- **Run whole blocks.** Template counts and start indices are multiples of 10 so that every block is complete (the CLI enforces it). Under the D11 sol design, the derived-far count T_d should be a multiple of 30, so that T_o = T_d / 3 is a multiple of 10 too. The audit checks exactness in every complete block and lists incomplete ones.
- **Repeat subset.** PREREG §2.9 gives `repeat_index` = 1 to main templates whose seed is divisible by 10 (luna only, PREREG D7). With main seeds equal to indices, that is the first template of every block; its letter, rank and clue count come from the block permutations like any other.
- Sampled per template: skin, entity, site, option cluster position, rank, letter and clue count (block-balanced), clue values, the 2 distractor entities, values and steps, record ids, need index, tail length, one routine event per step, and the start clock.

## 7. Dependency graph (`graph.DependencyGraph`, `Episode.graph`)
Built from the script, never from agent trajectories (PLAN §4).
- **Nodes:** `obs:t`, `act:t`, `comp:<id>` (`fact`, `clue0..2`, `rule`, and the distractors `dist0`, `dist1`), `fact`, plus `env:lookup` in recoverable cells and `system_prompt` when the rule sits there.
- **Edges:**
  - `obs:r → comp:c` (reveals; distractors too);
  - `comp:c → fact` (`is` for observed, `derives` for derived; never from a distractor);
  - `fact → act:n` (determines);
  - `obs:t → act:t` for every other step (routine, reveal and distractor actions need only their own observation);
  - `env:lookup → comp:c` (re-shows; distractors too).
- `needed_step("fact")` = n; a distractor is never needed (`needed_step` None). `live[c]` = [reveal step of c, n] for the target's components only. `live["fact"]` = [latest reveal, n]. `live_at(t)` lists what must be carried at step t. In the withheld variant, the fact has no parents.

## 8. Survival calculator (`survival.py`)
- **Window model** (as ARC Standard): before sending observation m, keep the longest suffix of whole (observation, reply) turns that fits in W tokens. The current observation is always kept. The episode's system prompt counts toward W (`window_counts_system_prompt` = true, PREREG D5), as in the harness cells and the PREREG formulas. The harness counts exactly `Episode.system_tokens` (95-150 tokens at the defaults): the notes sentence that notes cells append is **not** counted, so the two cells of a notes pair (W-n-0/W-0, Σ-n-r/Σ-0-r) evict at the same steps (harnesses/DESIGN.md §4).
- `window_keep_start(obs_tokens, reply_tokens, W, system_tokens)`: the first kept turn.
- `designed_survival(...)` and `episode_design(...)` give S before any run. `Episode.design` stores:
  - gaps (steps) from the latest and the earliest reveal;
  - observation tokens from those reveals to need;
  - `far_by_obs_tokens`;
  - `S_window_obs_only` (replies of 0 tokens) and `S_window_assumed_replies`;
  - full-history context size at need.
- `max_reply_tokens_for_survival(ep)`: the largest uniform reply length at which S is still 1 (None for far cells).
- `survival_from_payload(ep, messages, system=None, exclude_indices=())`: S from the payload actually sent. A component survives if its displayed sentence appears verbatim in user, system or developer text.
  - Accepted message shapes: chat-style, Responses-style (`content` parts and reasoning items, which count as opaque) and Gemini-style (`parts`, role `model`).
  - Summary cells insert a model-written summary as a user message. Exclude its index so that S stays environment-side, and string-match the summary separately.
  - Assistant text is reported as `assistant_carried`.
  - Use the payload of the need step's **first** presentation. After a lookup, the payload holds the re-shown records (S=1 by construction) and the model's own lookup reply, which may quote the options next to the entity name.
- **Near and far are designed for drop-oldest windows.** Far holds for any loss policy that keeps at most W tokens of observations, so the reveal is outside the verbatim context whatever the replies are. Near holds only for a policy that keeps the most recent W tokens verbatim. A summary cell that compacts the whole history whenever the context passes W can compact a near reveal: with 1k-token replies and the system prompt counted, a full history passes 24k at step 9, and a second compaction can land between a near reveal (n−4 to n−6) and the need step. harnesses/DESIGN.md §4.3 measures this; near-cell S in summary cells is measured, not designed.
- `carried_in_text(text, ep)`: S_carried and P(carried) for logged summaries and notes (PREREG §2.8, D6). A value counts if it occurs anywhere in the model's text as a whole word, by `(?<![0-9A-Za-z])VALUE(?![0-9A-Za-z])` (`survival.whole_word_regex`): `slot 310.` and `(310)` match, `3101`, `A310` and `310b` do not. An observed fact is carried if its value is; a derived fact if its final value is, or else every clue value is. The rule need not be carried, and the entity need not be named (`entity_mentioned` is reported only). Distractor values never equal the target or a clue value, so carrying a distractor never counts. With clustered options (D2) a partial carry (some clues) is worth nothing (§9), so there is no "partly carried" category.
- `reference_window_payload(ep, replies)`: a reference drop-oldest payload for cross-checking harness implementations. Tests show that its payload-S equals the designed S when replies have the assumed length.

## 9. Oracle and validity checks
- **Oracles** (`oracle.py`):
  - `KeyOracle` replies with the answer key.
  - `TextOracle` reads only what an agent sees (system prompt and observations) and parses the fixed sentence frames. With memory, it must score 100% on need and routine steps in every base and restated episode. This checks that the information is in the text and that derived facts are computable from it. Distractor bindings are about other entities and do not disturb it.
  - `TextOracle(memory=False, use_lookup=True)` forgets everything and looks up at the need step. It must score 100% on recoverable cells, which checks lookup.
  - Without memory or lookup, the text oracle guesses the first option.
- **Shortcut audit** (`validity.shortcut_audit`). It re-derives everything from the text, independently of the generator's bookkeeping:
  - no reserved string in any filler or routine event;
  - every observation re-counts to exactly v tokens;
  - derived and withheld episodes never show the target before need, and observed episodes show it only at the reveal;
  - options are valid and distinct, form one evenly spaced cluster, and exclude clue values;
  - distractor bindings (D1): 2 per episode, about other entities, with values that are neither options nor clue values nor each other, each shown exactly once, at its own non-evidence step before need;
  - near and far still hold when recomputed from the step at which each component sentence first appears, the re-counted tokens and the system prompt;
  - the full-history context at need, with assumed replies, is ≤ `max_context_tokens`;
  - cells share the need observation, options, routine text and distractor bindings;
  - the correct letter and rank are balanced (chi-square p > 0.01 once there are at least 5K templates);
  - in every complete block of 10 templates, each letter and rank occurs once and the clue counts split 5/5 (D2, D7).
- **Lookup audit** (`validity.lookup_audit`, D3). It plays every recoverable base episode with lookups at the need step and checks that lookup(target) re-shows every target record and no distractor (with the key written `key="<name>"`, so punctuation next to the name is exercised), that lookup(distractor) re-shows that binding and no target record, that an unknown key gets "no such record", that a 4th lookup gets "lookup unavailable", costs one turn and leaves the next answer scored as usual, and that a second over-cap lookup at the same step is an invalid action.
- **No-memory heuristic baselines** (`validity.heuristic_baselines`) run on three views without the fact:
  - the need observation alone;
  - the full transcript up to need in the withheld control;
  - the full transcript of derived base cells, where the target is never shown in final form.

  The baselines are:
  - most-frequent option: the option value that occurs most often outside the option list; ties go to the first listed;
  - last-seen option: the value that occurs last outside the list, or the last-listed option if none occurs;
  - first option;
  - median-value option;
  - prior label: the most frequent correct letter in the other split's templates.

  Each must score ≤ chance + `validity_margin_pp` (10% + 10pp = 20%). No option value ever occurs outside the option list in these views (distractor and clue values are never options), so the two text heuristics fall back to positional guesses. Block balance then puts every baseline at chance.
- **Partial memory** (`validity.partial_memory_diagnostic`, per derived cell in `summary.json` as `partial_memory`; **gated**, PREREG D2). It asks what an agent that kept only some of the clues (with the rule) can do. The gate, in every derived cell:
  - `narrowing_templates` = 0: enumerating every proper subset of the clues (the empty one included), no subset leaves fewer than 10 options consistent with the clue ranges (base 100-999, addends 61-98);
  - `base_and_rule_uniform_accuracy` ≤ 0.20: the agent kept the base clue and the rule, knows the addend range, and picks uniformly among the consistent options;
  - `smallest_above_base_accuracy` ≤ 0.20: the agent kept the base clue and picks the smallest option above it.

  Reported, not gated: `nearest_to_midrange_accuracy` (base + mid-range addends, nearest option), and `generator_aware_bayes`, the accuracy of the Bayes-optimal guess of an agent that knows the generator's sampling exactly, for each subset of kept clues (`validity.generator_aware_weights`). That second number is an upper bound no agent is told how to reach: an addend near the edge of its range says something about the target's rank, because the addends are shifted by the rank to keep every option consistent.

- **Result** (from `uv run python -m persistgym render --n 60 --single-turn --gzip`, main templates 0-59, 1,440 episodes, 6 complete blocks; the numbers are in its `summary.json`):
  - all 16 audit checks pass, including the lookup audit on 240 recoverable base episodes;
  - every baseline scores 0.10 on every view (threshold 0.20);
  - need-step accuracy of the oracles:
    - key oracle: 1.00 everywhere;
    - text oracle: 1.00 on base and restated, 0.10 on withheld;
    - lookup oracle without memory: 1.00 on recoverable base and on restated, 0.10 on non-recoverable base and on withheld;
  - routine accuracy is 1.00 for the key and text oracles;
  - partial memory, in each of the 4 derived cells (60 templates, 30 with 2 clues and 30 with 3): no narrowing template, 10 options left with the base clue and the rule, 0.100 for the uniform pick and 0.100 for the smallest option above the base; reported: 0.133 for the nearest mid-range option and at most 0.160 for the generator-aware Bayes guess (kept clues: the two addends of a 3-clue fact);
  - `validity_pass=True`.

  The baselines sit at exactly 0.10 *because of* block balance: no option value ever occurs outside the option list, so every text heuristic falls back to a position, and every position is correct once per block of 10. They rule out positional and frequency shortcuts; they do not rule out an LLM prior over values, which only the paid withheld run at G1 can measure.
- **Partial memory at scale** (from `uv run python -m persistgym partial-memory --n 2000`, main templates 0-1,999, 1,000 with 2 clues and 1,000 with 3):

  | | 2 clues | 3 clues | all |
  |---|---|---|---|
  | templates where a proper clue subset narrows the options (gated: 0) | 0 | 0 | 0 |
  | base + rule + addend range, uniform pick (gated: ≤ 0.20) | 0.100 | 0.100 | 0.100 |
  | smallest option above the base (gated: ≤ 0.20) | 0.107 | 0.093 | 0.100 |
  | nearest option to base + mid-range addends (reported) | 0.097 | 0.072 | 0.085 |
  | generator-aware Bayes, best subset of kept clues (reported) | 0.133 | 0.164 | 0.164 |

  By kept clues, the generator-aware Bayes accuracy is 0.100 with the rule only, 0.112 with the base clue alone (exactly 0.100 for 2 clues), 0.127-0.139 with one addend (alone or with the base) and 0.164 with both addends of a 3-clue fact. The pilot split (`--split pilot`, templates 0-1,999) gives 0 narrowing templates, 0.100 and 0.100 for the gated heuristics and at most 0.155 for the Bayes guess. Generator 0.1.1 had 0.45 of templates narrowed to one option by the base clue alone and 0.69 / 0.23 for the two gated heuristics.

## 10. Data model (the harness-cell contract)
`Episode` (episode.py) is a plain dataclass with `to_dict` / `from_dict`. It is stored as one JSON object per JSONL line; `persistgym.read_jsonl(path)` reads `.jsonl` or `.jsonl.gz` back into Episodes. Schema 2 adds the distractor fields below, `Component.entity` and `LookupSpec.record_keys`.

| Field | Meaning |
|---|---|
| `episode_id` | `<template_id>/<cell id>/<variant>` |
| `template_id`, `template_seed`, `split` | Template identity; reproducible from seed + config |
| `cell` (TaskCell; JSON: cell id), `variant` | Task cell and `base` / `restated` / `withheld` |
| `config`, `config_hash`, `generator_version`, `schema_version` | Full generator config and its SHA-256 (`common.runmeta.config_hash`) |
| `skin`, `kind`, `entity`, `quantity`, `need_verb` | Surface story; `need_verb` is the need action's verb |
| `system_prompt`, `system_tokens` | Task instructions (the harness adds its own notes sentence, which W does not count) |
| `steps` | List of `Step` (below) |
| `need_step` | Index of the need step |
| `options` (`label`, `value`), `correct_label`, `target_value` | The K options, the correct letter and value |
| `components` | What must be carried: `comp_id` (`fact`, `clue0..2`, `rule`), `role`, `name`, `value`, `sentence` (verbatim), `record` (full displayed line), `step` (None = rule in the system prompt), `entity`. Empty in `withheld` |
| `distractors` | The distractor bindings, as `Component`s with `comp_id` `dist0`, `dist1`, role `distractor` and the other entity in `entity`. The same in every cell and variant; never needed |
| `n_clues` | 0 for observed cells |
| `lookup` | `available`, `key` (the target entity), `syntax`, `max_per_episode`, `records` (record id → line re-shown; target components, `null<k>` in withheld episodes, distractors), `reveal_steps` (record id → step first shown), `record_keys` (record id → entity) |
| `graph` | Dependency graph (§7) |
| `design` | Designed distances, survival and context sizes (§8) |

`Step`:
- `index`, `kind` (`routine` / `reveal` / `distractor` / `need`), `routine_type`;
- `event` (the EVENT text) and `observation` (the full user message);
- `obs_tokens`;
- `event_start` / `event_end` and `filler_start` / `filler_end` (character spans in `observation`);
- `expected_action` (canonical, e.g. `ack(M-7350)`, `store(H)`);
- `reveals` (component ids first shown here), `restates` (the restated control), `distractors` (distractor ids shown here), `sim_time`.

`EpisodeResult` (env.py): `need_correct`, `need_action`, `need_label`, `routine_correct` / `routine_total`, `n_lookups` and `lookup_steps` (lookups served), `n_lookups_unavailable` and `lookup_unavailable_steps` (over-cap lookups), `n_turns`, `step_outcomes` (`correct`, `wrong`, `unparsed`, `invalid_lookup`) and `turns` (`Turn` with `outcome` also `lookup` or `lookup_unavailable`, `is_lookup_result`, `is_lookup_unavailable`).

The harness should drive episodes through `EpisodeEnv` (`observation`, `step(reply) -> (next observation, done)`, `result()`). It must not replay `steps` directly, because a lookup inserts a turn. `EpisodeEnv.info` (pending step, whether the observation is a lookup response or a "lookup unavailable" response, observation tokens) is bookkeeping for logs and must never be shown to the model.

## 11. Researcher decisions
Each item below is a named field of `GeneratorConfig` (config.py; also listed in `RESEARCHER_DECISIONS`). Defaults come from PLAN.md where it gives a number; the others are marked "proposed". Items the researcher decided on 2026-10-01 carry their PREREG D-number.
- [RESEARCHER DECISION] `W_tokens` = 24,000. PLAN §5. Eviction threshold. Amendment §16.5 asks for a tuning rule applied in M1 rather than a fixed number.
- [RESEARCHER DECISION] `v_tokens` = 1,500. PLAN §5. Tokens per observation; with W it fixes the far gap (`floor(W/v)` = 16 steps).
- [RESEARCHER DECISION] `near_gap_steps` = 4. PLAN §5: "reveal about 4 steps before need". For derived facts this places the *latest* component; the earliest is up to 2 steps earlier.
- [RESEARCHER DECISION] `far_margin_tokens` = 0 (proposed). Far = observation tokens from the latest reveal through need > W + margin. Any margin below v (1,500) leaves the far gap at 16 steps at the defaults; a margin of v or more makes it 17 and raises the minimum need index to 21.
- [RESEARCHER DECISION] `assumed_max_reply_tokens` = 1,000 (D5: R_plan = 1,000; ARC Standard's published visible output averages about 907 tokens per action, `docs/background.md` §4). Near cells must keep S=1 at this reply length. At the defaults, with the system prompt (95-150 tokens) counted, near cells keep S=1 up to uniform replies of 4,087-4,101 tokens (observed), 2,970-2,981 (2 clues) and 2,225-2,234 (3 clues). `max_reply_tokens_for_survival` gives the exact limit per episode, and payload-S catches longer real replies.
- [RESEARCHER DECISION] `window_counts_system_prompt` = true (D5). W also holds the episode's system prompt, as the harness cells and the PREREG formulas count it. The harness counts the episode's system prompt only, not the notes sentence, so notes pairs evict at the same steps (§8).
- [RESEARCHER DECISION] `max_context_tokens` = 64,000. PLAN §5: "contexts stay ≤ 64k". Checked by the audit for full history with assumed replies (at most 61,650 at the defaults in the 60-template render).
- [RESEARCHER DECISION] `K_options` = 10. PLAN §5. Chance = 10%.
- [RESEARCHER DECISION] `option_spacing` = 1 (D2). The options are one cluster of consecutive values, and each addend is drawn at least rank × spacing above the bottom and (K − 1 − rank) × spacing below the top of its range, so no proper subset of the clues narrows the options. A spacing s needs (K − 1) × s ≤ 37 (98 − 61); a larger s leaves fewer addend values.
- [RESEARCHER DECISION] `n_distractors` = 2 (D1). Distractor bindings per episode, at non-evidence steps, with values that avoid every option and clue value; lookup serves their keys (D3).
- [RESEARCHER DECISION] `need_index_range` = (20, 24) (proposed). 20 is the minimum for far derived cells at the defaults; 24 keeps full history ≤ 64k with 1k replies. Episodes have 21-27 steps.
- [RESEARCHER DECISION] `tail_steps_range` = (0, 2) (proposed). Routine steps after need. They make "need = last step" untrue, but they cost tokens and carry no outcome.
- [RESEARCHER DECISION] `n_clues_choices` = (2, 3) (D2). PLAN §4: "computed from 2-3 observations". Split exactly 5/5 within each block of 10 templates.
- [RESEARCHER DECISION] `clue_spacing_steps` = 1 (proposed). Consecutive steps are "different steps". A larger spacing widens the derived reveal span and tightens the near reply budget.
- [RESEARCHER DECISION] `rule_placement` = `with_last_clue` (proposed). Alternatives: `with_first_clue`, `separate_step`, `system_prompt`. This sets the step at which derivation first becomes possible.
- [RESEARCHER DECISION] `restate_mode` = `as_revealed` (proposed). The restated control repeats the clues and rule, so it removes memory but not derivation. `final_value` restates the computed value instead.
- [RESEARCHER DECISION] `single_turn_reply_mode` = `oracle` (proposed). What fills the reply positions in the flattened H3 control. `none` drops them; a real run's replies can be passed per episode.
- [RESEARCHER DECISION] `warn_future_need` = true (proposed). The system prompt sentence "Some requests depend on records shown in earlier updates." It is the same in all cells.
- [RESEARCHER DECISION] `lookup_max_per_episode` = 3 (D3). Lookups served per episode; then "lookup unavailable" for one turn per pending step (§4).
- [RESEARCHER DECISION] `accept_value_answers` = true (D4). At need, accept the option value as well as its letter.
- [RESEARCHER DECISION] `strict_action_parse` = false (D4). Fall back to the last known `verb(arg)` if the reply has no `ACTION:` line.
- [RESEARCHER DECISION] `validity_margin_pp` = 10. PLAN §5 and §16.3: no-memory baselines and the gated partial-memory heuristics ≤ chance + 10pp.

Also fixed for PREREG, though not config fields:
- the seed ranges (`config.SEED_RANGES`, D7) and whole blocks of 10 templates;
- that unparseable replies count as wrong with no re-prompt (D4);
- that the combining rule is a sum, the base clue is 3-digit (100-999) and addends may repeat;
- the S_carried rule (D6): whole-word regex on the value or every clue value, rule not required (§8); it replaced `carried_match_window_chars` and `carried_requires_rule`;
- the over-cap rule (D3): one "lookup unavailable" turn per pending step, then an invalid action.

## 12. Known limitations and what this does not show
- **Not yet checked with a model.** The $0 checks show that the generator is internally consistent and has no trivial shortcut. They do not show that an LLM finds the routine steps easy, that restated-at-need reaches ≥ 85%, or that the fact-withheld control sits at chance. Those are the paid validity runs at G1.
- **Partial memory is worth little, not nothing.** No proper subset of the clues rules out an option, and the gated partial-memory heuristics sit at chance (§9). An agent that knew the generator's sampling exactly could still use where a kept addend lies in its range: up to 0.164 with both addends of a 3-clue fact and no base. Agents are never told the ranges, so this bounds partial-memory rescue rather than describing it.
- **Clustered options make the need step exacting.** Neighbouring options differ by 1, so an arithmetic slip in a derived cell, or a misremembered last digit in an observed cell, lands on a wrong option. This can lower the restated-at-need ceiling, mainly in derived cells. The per-cell restated rate at G1 will show whether the 85% ceiling still holds (PREREG D2).
- **Repeated addends.** Addends are drawn independently, so a 3-clue fact has two equal addends in about 1 template in 29. S_carried then needs that value only once.
- **The target is still more salient in derived cells.** Distractor bindings give every episode 2 other single-record entities, so an observed target no longer stands out (D1). A derived target still has 2-3 records and a rule, while each distractor has one record.
- **The withheld control keeps the entity.** Its null records still name the target entity (`Sample LINDEN has been logged at intake.`); PREREG §4.3 describes equal-length distractor bindings instead (D39), which is not done here.
- **Fixed sentence frames.** The surface text varies through 5 skins but uses fixed frames; a model may learn the format within one episode.
- **Survival by verbatim match** treats a paraphrased record in a user-role message as not surviving. Window harnesses send observations verbatim, so this matters only for summary cells, where `carried_in_text` is the intended measure. String match also misses paraphrased carry ("the code ends in 17"), so P(carried) is an undercount.
- **Token counts are tiktoken's,** not provider-reported. The harness should log both, and payload-S should be checked against what was actually sent.
