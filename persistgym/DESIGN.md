# PersistGym-lite generator: design

_Track: M0 PersistGym build (PLAN.md §5, §6; amendment A1 §16.3 and §16.5). Generator version 0.4.0, episode schema 3. Everything here is $0: no API calls._

_0.4.0 (PREREG §17.3, amendment R3; gpt-6.1-sol only): a second generator config, preset `sol-chain` (`config.PRESETS`), for sol's H2 runs. Its derived facts give each clue value through a chain record, a two-hop relay over helper entities that takes two 3-digit operations to resolve (§2; the units digits alone pick the option, so it does not force multi-step reasoning), its evidence steps carry the evidence notice (§3), the rule is shown with the first clue, and every helper names a lookup key of its record (§4). Three new audit checks, an atom-level partial-memory gate, six gated misreadings and a gated stand-in baseline check it (§9). The template values (options, letters, ranks, clue counts and values, distractors, stand-in, steps, record ids, clock) are 0.3.0's for every seed. **The default config is unchanged:** its two new fields are left out of its dict at their defaults, so its config hash is still `3d6bc648…`, and its episodes are byte for byte those of 0.3.0 apart from `generator_version` (`tests/golden_0_3_0.json`, taken before any 0.4.0 change). New chain draws and reserved strings happen in chain form only, so the default filler and routine events cannot shift. The new `nearest_to_stand_in_value` baseline is gated in every config, luna's included; it changes no episode._

_0.3.0 (PREREG D39, fact-withheld control): the withheld variant no longer shows null records that name the target entity (`Sample LINDEN has been logged at intake.`). At each evidence step it shows, in place of each fact or clue binding, a binding of equal token length about a stand-in entity, with values outside the option, clue and distractor values; the rule sentence, which binds no entity, is kept (§3). Every observation keeps its v tokens, and the evidence steps keep the base episode's log filler. Two new audit checks and a withheld branch of the lookup audit verify this (§9). To guarantee a stand-in of equal token length, 16 entity names that sat in small token-length classes were replaced (§2). The stand-in's name never contains the target's or is contained in it (TERN and BITTERN). **Base and restated episodes are not byte-identical to 0.2.0.** Templates that used a replaced name show the new one. The stand-in's values are reserved strings (§5), so a filler line or routine event that drew one of them is resampled, and that shifts the rest of its random stream: most observations' log filler differs from 0.2.0 in every variant, and so do some templates' routine events (with their expected actions). Apart from the renamed entities, the options, clue values, distractor values and steps, record ids, need index, tail length, start clock, system prompt, evidence and need events and per-step token counts are unchanged. Keeping the 0.2.0 text would mean not reserving the stand-in's values, so they could appear in the log filler, unlike the values of the distractor bindings that D39 asks the stand-in bindings to be._

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
uv run python -m persistgym audit --n 1000                   # every check, in chunks
uv run python -m persistgym spotcheck                        # G1 spot-check pages (§13)
uv run python -m persistgym render --preset sol-chain --split validity --n 20 --gzip
uv run python -m persistgym spotcheck --preset sol-chain     # sol's variant (§13)
uv run pytest -q persistgym && uv run ruff check persistgym
```
`--start` and `--n` must be multiples of the balance block K = 10 (PREREG D7); `--partial-blocks` lifts this for quick checks. `--preset` (render, partial-memory, audit, spotcheck) starts from a named config (`config.PRESETS`: `default`, or `sol-chain`, sol's variant, PREREG §17.3); `--set` overrides single fields of it. `audit` renders and audits many templates in chunks of whole blocks (default 50) so that memory stays small, and pools the results exactly (§9).

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

**Chain records (generator 0.4.0, `clue_form` = `chain`; PREREG §17.3; gpt-6.1-sol's preset `sol-chain` only).** The clue values are the direct form's, but none is printed. Each clue's record gives its value through a two-hop relay over three helper entities of the skin, in four sentences about the clue's name, in an order shuffled per clue (`template.ChainSpec`, `render.chain_text`; pilot template 1, clue 0):
- anchor (H2): `For shipment SHAULA, the base bay is 314.`;
- far hop (H1 = H2 + f): `For shipment BELLATRIX, the base bay is 669 more than for shipment SHAULA.`;
- near hop (clue = H1 − n): `For shipment HADAR, the base bay is 329 less than for shipment BELLATRIX.`;
- decoy (H3 = H2 + x, never needed): `For shipment ORION, the base bay is 268 more than for shipment SHAULA.`

So the clue is 314 + 669 − 329 = 654. The rule is unchanged (a plain sum) and, in `sol-chain`, shown with the first clue (`rule_placement` `with_first_clue`), so the evidence steps are exactly the clue steps; `Component.sentence` is the four-sentence record and `Component.value` the clue value, which is never shown.
- **Helpers** (stream `chain-helpers`): the skin's entities whose names neither contain nor are contained in the target's, the stand-in's or a distractor's (`names_overlap`), shuffled; the first 3m that overlap no earlier one. Clue i uses the next three as H1, H2 and H3. At most 9 of a skin's 28 names.
- **Numbers** (stream `chains`; the order from `chain-order`). With c the target's clue, c′ the stand-in's and cmax the largest value the slot can take (98 for an addend, 899 − 61(m − 1) for the base): H1's value v1 ~ U[cmax + 109, 999], whatever c and c′ are; n = v1 − c and n′ = v1 − c′; f ~ U[109, min(990, v1 − 69)] and a = v1 − f; x ~ U[109, min(990, 999 − a)]. A draw is kept only if a, f, x, n, n′, v1 and a + x are distinct, f is at least 10 from n, n′ and x (`CHAIN_MIN_GAP`), and none of the seven is an option, a clue value or running total of the target or the stand-in, the stand-in's value, a distractor value or a number of an earlier chain. So n, n′ ∈ [109, 938], a ∈ [69, 890] and f, x ∈ [109, 990]: every needed atom lies at least 9 (`CHAIN_MARGIN`, K − 1) inside its declared range (`CHAIN_ANCHOR_RANGE` [60, 999], `CHAIN_DELTA_RANGE` [100, 999]), and no printed number is below 60, so none can be a clock field.
- **Reserved and hidden.** Every chain number and helper name, and the running totals of the target and the stand-in, are reserved strings (§5), in chain form only. `template.hidden_values` lists what an agent never sees before the need step: in chain form the target, the clue values and running totals, H1's and H3's values, and the stand-in's value, clue values and running totals (in the direct form, the target and the running totals of 2 or more clues), less the distractor values: those are drawn as in 0.3.0, avoiding options and clue values but not running totals, so a 3-clue running total can equal one, which every episode shows (6 of main templates 0-999 in chain form).
- `GeneratorConfig` refuses chain form unless `option_spacing` is 1 and every slot leaves room for v1 (cmax + 109 ≤ 999).

**Distractor bindings (PREREG D1).** Each episode shows `n_distractors` = 2 bindings about other entities of the same kind, in the target's sentence frame and from the same record source as an observed fact (`For sample ROWAN, the freezer slot is 643.`). They are never needed. Their values come from `value_range` and are neither options nor clue values. They sit at steps that hold no evidence in any of the 8 cells (sampled per template from the steps between `lead_in_min_steps` and n − 1), so every cell and variant shows them at the same steps in the same words. They keep the target binding from being the only record about an entity, and they give `lookup` keys other than the target (§4). Because their values are never options, a model that binds a distractor's value to the target answers with a value that is not offered.

**Surface stories (skins).** Five skins (warehouse, biobank, datacenter, archive, depot) change nouns only: facility, entity names, quantity and clue names, record sources, routine tags, sensor metrics and log service names. Every sentence uses the fixed frames in `render.py`, which the oracle parses.

**Entity names and token length (0.3.0).** Each skin has 28 entity names. Grouped by their token count as they appear in a binding (`" NAME"` in `o200k_base`, `template.entity_token_length`), every group holds at least `skins.MIN_TOKEN_CLASS` = 6 names: the target, up to 4 distractors (the config maximum) and the withheld control's stand-in (§3). Generator 0.3.0 replaced the 16 names that sat in smaller groups, in place, so other templates keep their names: warehouse ARCTURUS, BETELGEUSE, ALNILAM → BELLATRIX, ALPHARD, MARKAB; biobank FIR, HAWTHORN, SEQUOIA, MAGNOLIA → WALNUT, LAUREL, HICKORY, CHERRY; datacenter EOS, MNEMOSYNE → DIONE, EUTERPE; archive AMAZON, ZAMBEZI, MURRAY → THAMES, MERSEY, TIGRIS; depot CORMORANT, OSPREY, GOSHAWK, SANDPIPER → THRUSH, LINNET, BUNTING, GREBE. Names now take 2 or 3 tokens, except 6 datacenter names of 4 tokens (the smallest group).

## 3. Task cells and variants
`TaskCell(fact, recoverable, distance)`; ids like `derived-rec-far`. All 8 cells of a template share:
- the need step index, the need event, the options, the correct letter and the correct value;
- the routine event and log filler of every step index (identical observation text wherever both cells have a routine step);
- the distractor bindings: same steps, same observation text;
- the clock and the system prompt, except for the lookup paragraph in recoverable cells (and the standing rule in derived cells when `rule_placement` is `system_prompt`).

Within a template, the need observation is byte-identical across all 8 base cells and the withheld cells (audited). A withheld episode is byte-identical to the base episode of its cell except for the bindings at the evidence steps, which keep their token counts and the base log filler (audited, D39).

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
- `withheld` (PREREG §4.3, D39; validity gate: LLM ≤ chance + 10pp): the fact-withheld control. No scripted observation before the need step names the target entity. At each evidence step of the cell, the record keeps its source and id (so the expected `ack` is unchanged), and each binding about the target is replaced by a **stand-in binding** in the same frame about the template's stand-in entity (`Template.substitute`, `Episode.substitutes`):
  - observed: `For sample LINDEN, the freezer slot is 310.` → `For sample HEMLOCK, the freezer slot is 350.`;
  - derived: each clue binding → the same clue name about the stand-in with its own clue value (`the rack slot is 267`, `the shelf offset is 83`); the rule sentence binds no entity and is kept verbatim, so it stays where the base shows it (with a clue, at its own step or in the system prompt).

  The stand-in is another entity of the skin, never a distractor, whose name has the target's token length (§2) and neither contains nor is contained in the target's name (`template.names_overlap`; the depot skin has TERN and BITTERN, which share a token length). Its value is drawn from `value_range` like a distractor value; its clues are drawn as the target's are (a 3-digit base and 2-digit addends, as many as the template has, summing to the stand-in's value). None of these values is an option, a clue value of the target or a distractor value, and all are reserved strings (§5). So every stand-in sentence has the token count of the sentence it replaces, the observation keeps exactly v tokens and the base filler, and neither the stand-in's value nor what its clues give under the rule is an option: an agent that takes the stand-in for the target answers with a value that is not offered. One stand-in serves all 8 cells of a template. The step structure is unchanged (evidence steps keep `kind` = `reveal` with `reveals` empty and `substitutes` set), the distractor bindings stay, and `components` is empty. Generator 0.2.0 showed null records naming the target instead (`Sample LINDEN has been logged at intake.`), which told the agent which entity mattered.

**Evidence notice** (`evidence_notice`, generator 0.4.0; PREREG §17.3; on in `sol-chain` only). At each evidence step of the cell, after the record and before the ack request, the event says (`render.notice_text`), for a derived fact: `The loading bay of shipment HADAR will be requested in a later update. Before replying, work out as much of it as the records so far allow and keep the result in mind; do not write it in your reply.`, and for an observed fact: `The loading bay of shipment HADAR will be requested in a later update. Keep it in mind; do not write it in your reply.` (45-47 and 28-30 tokens with the leading space, by the entity's length). It comes out of the log filler, so the observation stays at v tokens. It is never in a record line, so lookup responses and the restated block never repeat it; never at a distractor, routine or need step; never in the system prompt. It names the entity, since a chain record names four. In the withheld variant it names the stand-in (same token length), so it is false there. The target binding is then marked at reveal in both fact kinds, unlike the distractor bindings (PREREG D1 does not hold for this config). A withheld chain-form evidence step changes only the near hop (the stand-in, with n′; same position in the order) and the notice: the anchor, far hop, decoy, rule, source and record id stay byte for byte, and every sentence, event and observation keeps its token count (`render._check_equal_length` compares the events too).

**Position-matched single-turn control** (`controls.single_turn_control`, H3): the same observations 0..n, with replies between them, flattened into one user message after a one-line preamble. Replies default to the minimal correct reply `ACTION: <expected>` (`single_turn_reply_mode`). Passing a real run's replies yokes the control to that run. The result records each component's token offset in the flattened prompt and in the multi-turn message contents. The two differ only by the separator tokens (`<<< update >>>`, `<<< operator reply >>>`) and the preamble.
- It is built from **non-recoverable** base episodes only. A recoverable cell has the same observations, and its system prompt offers `lookup`, which a single prompt cannot serve, so its control would differ only by offering an action that cannot work. Compare it with the multi-turn non-recoverable cell.
- `controls.score_single_turn(control, reply)` scores a reply exactly as `EpisodeEnv` scores the need step (same parser, letter or value).

## 4. Lookup semantics (exact; `env.EpisodeEnv`; PREREG D3)
- Lookup is available only in recoverable cells. At most `lookup_max_per_episode` (3) lookups are **served** per episode.
- When the reply's action is `lookup(<key>)`, the pending step is **not** scored and does not advance. The next observation is a lookup response, padded to v tokens like any observation, and it ends with `Pending request (repeated): <the pending step's event>`. The agent then answers the repeated request. **A lookup therefore costs exactly one extra turn and v tokens.**
- **Keys.** Every binding has a key, the entity it is about: the target entity or one of the 2 distractor entities (`LookupSpec.record_keys`). In the withheld control the evidence records are keyed to the stand-in (the rule shown with them too), so `lookup(<stand-in>)` re-shows them and `lookup(<target>)` gets "no such record", since no record about the target is ever shown (D39). A key matches an entity if it contains the entity name as a whole word, ignoring case (`BEECH`, `beech`, `sample BEECH`, `key="BEECH"`, `sample:BEECH` and `BEECH's slot` match; `BEECHES` and `sampleBEECH` do not). The key is matched as the agent wrote it, whatever its length; only the echo in a "no such record" reply drops punctuation and keeps at most 40 characters. Entity names are single distinct words, so the match never confuses the target with a distractor, and formatting slips do not add turns and tokens that are not about memory (H1's cost outcome).
- **Served lookup.** The response starts `LOOKUP RESULT for sample LINDEN:` and re-shows, verbatim as originally displayed and in display order, every record shown at or before the pending step about a matched entity: the fact record, or every clue record with the rule (records that share a step are merged into one line), or a distractor's binding. A key that names several entities re-shows all of their records. A key with no such record shown so far, whether it never appears or appears later, gets `LOOKUP RESULT for '<key>': no such record.` and still costs the turn and counts as a lookup.
- **Over the cap.** Once 3 lookups are served, the next lookup at a pending step gets `LOOKUP RESULT: lookup unavailable. All 3 lookups allowed per session have been used.` and the pending request again. It costs one turn, is counted in `n_lookups_unavailable` (not in `n_lookups`), and is not an answer, so the pending step is still scored on the agent's next action. A second over-cap lookup at the same pending step is an invalid action (`invalid_lookup`, scored wrong); this keeps episodes finite. So a lookup habit costs turns and tokens, not success, as long as the agent answers after being told.
- In non-recoverable cells `lookup` is not offered and is an invalid action: the pending step is scored wrong (`invalid_lookup`), the episode advances and no extra turn is added.
- **Helper keys (chain form, PREREG §17.3).** Each helper named in a clue's chain record is a key of that record too (`LookupSpec.records` entries `<comp_id>@<helper>`, with the record's line and step, keyed to the helper): lookup(BELLATRIX) re-shows that clue's record from its step on, in base and withheld episodes. Lines are not repeated, so a key that names several entities of one record shows it once.
- Lookup observations are deterministic: same template seed, pending step and lookup number give the same text. `render.renderer_for(episode)` rebuilds the renderer from `template_seed` and `config`, so this also works for episodes loaded from JSONL.

**Scoring** (pre-registered under PREREG D4). The action is the last `ACTION: verb(arg)` line. If there is none and `strict_action_parse` is false (the default), the last `verb(arg)` with a known verb anywhere in the reply counts. A reply with no parseable action is scored wrong (`unparsed`), with no re-prompt. At the need step the verb must be the episode's `need_verb`, and the argument may be the letter or, with `accept_value_answers` (the default), the option value. After lookups the first non-lookup action at the need step is scored. A harness can declare a reply invalid before parsing with `step(reply, invalid="incomplete")`, for a response that stopped at its output cap (PREREG §6, §13, D13): the pending step is scored wrong (`incomplete`) with no action, even if the partial text holds a correct action or a lookup, and the episode advances. `EpisodeResult` gives need success, routine accuracy, the lookups served and the step at which each was used, the over-cap lookups, the number of turns, per-step outcomes and per-turn observation tokens.

## 5. Token budget and filler
- One tokenizer, tiktoken `o200k_base`, is used for generation and window accounting. Provider-reported tokens differ by per-message overhead; the harness logs both.
- Every observation, including lookup responses, has exactly `v_tokens` tokens (`token_tolerance` 0; audited by re-counting). The filler is a token-level suffix of a per-slot pool of chronological log lines, so the earliest kept line is cut as a log tail would be. If a BPE merge at the cut makes v unreachable, the pool's newest line is dropped (at most 3 times) to shift the alignment.
- The filler pool of step t is seeded by (template seed, t), so cells share it. Its clock times lie in (T(t−1), T(t)], with `step_seconds` = 75. Lookup responses at pending step t use slots of 15 s after T(t) (slot j for the j-th lookup, slot 3 for "lookup unavailable").
- **Reserved strings** never appear in filler or routine text: every option value, every clue value, every distractor value, the stand-in's value and clue values, the target, distractor and stand-in entity names, the quantity name and the clue names. They are reserved in every variant, so all variants share the filler. Numbers are matched unless embedded in a longer digit run; words are matched case-insensitively unless embedded in a longer word. Filler lines that would contain one are resampled. The audit re-checks this independently from the text. A side effect: over an episode the filler shows nearly every non-reserved value of the addends' range (61-98), so a number that never occurs is probably reserved, and an observer that knows the generator can use those absences to guess better than chance even on the withheld view. No gated baseline uses this, it is the same in every harness cell, and it holds in the default config too (PREREG §17.3, "What it does not show").

## 6. Templates and seeds (PREREG D7)
- Template `i` of split `s` has seed `SEED_RANGES[s][0] + i`. The ranges are half-open and disjoint: `main` = [0, 50,000), `validity` = [50,000, 60,000) (validity runs and the G1 spot-check), `pilot` = [90,000, 100,000) (amendment §16.5: pilot templates use a disjoint seed range). Main templates are taken in order from index 0. Template ids look like `main-000017`, `validity-000003`.
- Every random choice uses a named stream `random.Random(f"pg:{seed}:{stream}")`, so adding a stream never shifts the others. String seeding is SHA-512 based and does not depend on `PYTHONHASHSEED`.
- **Balance by construction:** template `i` is in block `i // K` (K = 10), so blocks start at each range start. Within each block, every letter is correct exactly once, every rank of the target in the cluster occurs exactly once, and the number of clues is split as evenly as the choices allow: exactly 5 templates with 2 clues and 5 with 3 (PREREG D2 (c)). Each block uses its own seeded permutations, so the three are independent of each other.
- **Run whole blocks.** Template counts and start indices are multiples of 10 so that every block is complete (the CLI enforces it). Under the D11 sol design, the derived-far count T_d should be a multiple of 30, so that T_o = T_d / 3 is a multiple of 10 too. The audit checks exactness in every complete block and lists incomplete ones.
- **Repeat subset.** PREREG §2.9 gives `repeat_index` = 1 to main templates whose seed is divisible by 10 (on both luna and sol: the researcher kept the repeat subset on sol when deciding D7 on 2026-10-01; PREREG §2.9, PLAN §17). With main seeds equal to indices, that is the first template of every block; its letter, rank and clue count come from the block permutations like any other.
- Sampled per template: skin, entity, site, option cluster position, rank, letter and clue count (block-balanced), clue values, the 2 distractor entities, values and steps, the withheld control's stand-in (entity, value and clue values, from its own stream `withheld`), record ids, need index, tail length, one routine event per step, and the start clock.

## 7. Dependency graph (`graph.DependencyGraph`, `Episode.graph`)
Built from the script, never from agent trajectories (PLAN §4).
- **Nodes:** `obs:t`, `act:t`, `comp:<id>` (`fact`, `clue0..2`, `rule`, the distractors `dist0`, `dist1`, and in the withheld control the stand-ins `sub_<id>` with role `substitute`), `fact`, plus `env:lookup` in recoverable cells and `system_prompt` when the rule sits there.
- **Edges:**
  - `obs:r → comp:c` (reveals; distractors and stand-ins too);
  - `comp:c → fact` (`is` for observed, `derives` for derived; never from a distractor or a stand-in);
  - `fact → act:n` (determines);
  - `obs:t → act:t` for every other step (routine, reveal and distractor actions need only their own observation);
  - `env:lookup → comp:c` (re-shows; distractors and stand-ins too).
- `needed_step("fact")` = n; a distractor or stand-in is never needed (`needed_step` None). `live[c]` = [reveal step of c, n] for the target's components only. `live["fact"]` = [latest reveal, n]. `live_at(t)` lists what must be carried at step t. In the withheld variant, the fact has no parents.

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
  - Lookup responses never count (PREREG §2.8). They are recognised by `episode.LOOKUP_EVENT_MARKER` (`EVENT: LOOKUP RESULT`), which every lookup response contains and no scripted observation does (tested), and `n_lookup_responses` reports how many were left out. Otherwise a lookup taken before the need step would re-show the records and give S = 1 in a far window cell, the case §2.8 treats as a window-accounting bug.
  - Use the payload of the need step's **first** presentation. A later presentation also holds the model's own lookup reply, which may quote the options next to the entity name.
- **Near and far are designed for drop-oldest windows.** Far holds for any loss policy that keeps at most W tokens of observations, so the reveal is outside the verbatim context whatever the replies are. Near holds only for a policy that keeps the most recent W tokens verbatim. A summary cell that compacts the whole history whenever the context passes W can compact a near reveal: with 1k-token replies and the system prompt counted, a full history passes 24k at step 9, and a second compaction can land between a near reveal (n−4 to n−6) and the need step. harnesses/DESIGN.md §4.3 measures this; near-cell S in summary cells is measured, not designed.
- `carried_in_text(text, ep)`: S_carried and P(carried) for logged summaries and notes (PREREG §2.8, D6). A value counts if it occurs anywhere in the model's text as a whole word, by `(?<![0-9A-Za-z])VALUE(?![0-9A-Za-z])` (`survival.whole_word_regex`): `slot 310.` and `(310)` match, `3101`, `A310` and `310b` do not. An observed fact is carried if its value is; a derived fact if its final value is, or else every clue value is. The rule need not be carried, and the entity need not be named (`entity_mentioned` is reported only). Distractor values never equal the target or a clue value, so carrying a distractor never counts. With clustered options (D2) a partial carry (some clues) is worth nothing (§9), so there is no "partly carried" category.
- `reference_window_payload(ep, replies)`: a reference drop-oldest payload for cross-checking harness implementations. Tests show that its payload-S equals the designed S when replies have the assumed length.

## 9. Oracle and validity checks
- **Oracles** (`oracle.py`):
  - `KeyOracle` replies with the answer key.
  - `TextOracle` reads only what an agent sees (system prompt and observations) and parses the fixed sentence frames. With memory, it must score 100% on need and routine steps in every base and restated episode. This checks that the information is in the text and that derived facts are computable from it. Distractor bindings are about other entities and do not disturb it.
  - `TextOracle(memory=False, use_lookup=True)` forgets everything and looks up at the need step. It must score 100% on recoverable cells, which checks lookup.
  - Without memory or lookup, the text oracle guesses the first option.
  - Chain form: it also parses the relation sentences (`oracle.RELATION_RE`) and resolves a value through them, at most `MAX_RELATION_DEPTH` (4) hops, with a cycle guard.
- **Shortcut audit** (`validity.shortcut_audit`). It re-derives everything from the text, independently of the generator's bookkeeping:
  - no reserved string in any filler or routine event;
  - every observation re-counts to exactly v tokens;
  - derived and withheld episodes never show the target before need, and observed episodes show it only at the reveal;
  - options are valid and distinct, form one evenly spaced cluster, and exclude clue values;
  - distractor bindings (D1): 2 per episode, about other entities, with values that are neither options nor clue values nor each other, each shown exactly once, at its own non-evidence step before need;
  - the withheld control (D39), in two checks:
    - `withheld_never_names_target_before_need`: no observation before need, and not the system prompt, names the target entity as a word;
    - `withheld_stand_ins_equal_length_and_valid`: the stand-ins sit exactly at the cell's evidence steps (re-derived from the config), each shown once in a reveal step; one stand-in entity per template, from the skin, never the target or a distractor, with the target's token length and a name that neither contains nor is contained in the target's (the first check matches whole words only); each fact or clue stand-in is the binding frame with the replaced value's digit count and a value that is no option, clue value, distractor value or target; the rule stand-in is the rule sentence verbatim; the stand-in's value (observed) or the sum of its clues (derived) is never an option. When the base episode of the cell is audited too, the two are identical except for these bindings: same step kinds and system prompt, identical observations at every other step, and at the evidence steps the same head and filler, the same event and the same whole observation once the stand-in sentences are swapped back, the same expected action, and equal token counts per sentence, per event and per observation;
  - near and far still hold when recomputed from the step at which each component sentence first appears, the re-counted tokens and the system prompt;
  - the full-history context at need, with assumed replies, is ≤ `max_context_tokens`;
  - cells share the need observation, options, routine text and distractor bindings;
  - the correct letter and rank are balanced (chi-square p > 0.01 once there are at least 5K templates);
  - in every complete block of 10 templates, each letter and rank occurs once and the clue counts split 5/5 (D2, D7);
  - generator 0.4.0 (PREREG §17.3), three more:
    - `chain_records_well_formed_and_resolve` (chain form; nothing to check otherwise): each clue record of a derived episode parses (`validity.parse_chain`) into exactly one anchor, far hop, near hop about the target and decoy, about the clue's name; the helpers are distinct and overlap neither each other nor the target, a distractor or the stand-in; the atoms lie in their ranges with the 9-margin; the far delta is at least 10 from the near deltas and the decoy delta; the chain's numbers are distinct; anchor + far − near is the clue value; and the rule over the resolved clues is the target;
    - `chain_hidden_values_never_shown` (chain form): no value an agent never sees (re-derived from the records, `validity.text_hidden_values`, equal to `template.hidden_values`) appears in the system prompt or any observation before the need step, in any variant (an observed fact's own value at its reveal excepted);
    - `evidence_notice_only_at_evidence_steps` (every config): with the notice, its exact text once in the event of each evidence step of the cell (re-derived from the config) and nowhere else; without it, nowhere.
  - and `withheld_stand_ins_equal_length_and_valid` has a chain branch: each stand-in record is the base record with only the near hop swapped (target → stand-in, n → n′); n′ is 3-digit and no option, clue or distractor value; H1's value − n′ is the stand-in's clue with the direct form's digit count; the swap-back maps the stand-in's notice to the target's.
- **Lookup audit** (`validity.lookup_audit`, D3). It plays every recoverable base episode with lookups at the need step and checks that lookup(target) re-shows every target record and no distractor (with the key written `key="<name>"`, so punctuation next to the name is exercised), that lookup(distractor) re-shows that binding and no target record, that an unknown key gets "no such record", that a 4th lookup gets "lookup unavailable", costs one turn and leaves the next answer scored as usual, and that a second over-cap lookup at the same step is an invalid action. It also plays every recoverable withheld episode and checks that lookup(target) gets "no such record" and shows no stand-in, and that lookup(stand-in) re-shows every stand-in record and no distractor (D39). In chain form, lookup(H1 of clue 0) re-shows clue 0's record and no other clue's (the stand-in's in withheld episodes). No lookup response holds the evidence notice.
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

  - `nearest_to_stand_in_value` (generator 0.4.0, every config; gated per task cell): on the withheld view, the option nearest the stand-in's value as the text oracle derives it. The stand-in's value is never an option and is drawn whatever the rank, so it picks the lowest or highest option, right at most twice per block of 10.

  Each must score ≤ chance + `validity_margin_pp` (10% + 10pp = 20%). No option value ever occurs outside the option list in these views (distractor, clue and stand-in values are never options), so the two text heuristics fall back to positional guesses. Block balance then puts every baseline at chance.
- **Partial memory** (`validity.partial_memory_diagnostic`, per derived cell in `summary.json` as `partial_memory`; **gated**, PREREG D2). It asks what an agent that kept only some of the clues (with the rule) can do. The gate, in every derived cell:
  - `narrowing_templates` = 0: enumerating every proper subset of the clues (the empty one included), no subset leaves fewer than 10 options consistent with the clue ranges (base 100-999, addends 61-98);
  - `base_and_rule_uniform_accuracy` ≤ 0.20: the agent kept the base clue and the rule, knows the addend range, and picks uniformly among the consistent options;
  - `smallest_above_base_accuracy` ≤ 0.20: the agent kept the base clue and picks the smallest option above it.

  Reported, not gated: `nearest_to_midrange_accuracy` (base + mid-range addends, nearest option), and `generator_aware_bayes`, the accuracy of the Bayes-optimal guess of an agent that knows the generator's sampling exactly, for each subset of kept clues (`validity.generator_aware_weights`). That second number is an upper bound no agent is told how to reach: an addend near the edge of its range says something about the target's rank, because the addends are shifted by the rank to keep every option consistent.

- **Chain records** (`validity.chain_partial_memory`, chain form; **gated** per derived cell, PREREG §17.3), next to the clue-level gate above, which is unchanged (the clue values are 0.3.0's):
  - `atom_narrowing_templates` = 0: the fact's value is Σ(a_i + f_i − n_i), 3m needed atoms; for every proper subset of them, with the rule and the chain structure known, every option stays reachable when missing anchors range over [60, 999] and missing differences over [100, 999] (`validity.atom_narrowing`; the reachable values form an interval, so this is exact). It holds by construction: one missing atom, 9 or more inside its range, reaches every option. The gate uses the declared ranges; a guess that also knows how the generator draws a missing atom (for example, that v1 lies in [cmax + 109, 999]) does better than one that knows only the ranges, and is not gated, like the clue-level Bayes guess.
  - six misreadings, each ≤ 0.20, each picking the option nearest the sum it computes (`validity.CHAIN_HEURISTICS`): every number of the target's records signed by its word (error +x per clue), signs ignored (+2n), the anchor alone (n − f), H1's value as the clue (+n), one hop from the anchor (−f), the decoy as the near hop's base (x − f). A single error of 10 or more lands outside the cluster.
  The render summary computes these from the atoms parsed from the episode text; `partial-memory` from `Template.chains`.
- **Result** (generator 0.3.0, from `uv run python -m persistgym render --n 60 --single-turn --gzip`, main templates 0-59, 1,440 episodes, 6 complete blocks; the numbers are in its `summary.json`):
  - all 18 audit checks pass, including the two withheld-control checks on 480 withheld episodes and the lookup audit on 240 recoverable base and 240 recoverable withheld episodes;
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
- **Result for `sol-chain`** (generator 0.4.0; PREREG §17.3 reports the same figures):
  - `uv run python -m persistgym render --preset sol-chain --split validity --n 20 --gzip` (480 episodes) and `--split main --n 60 --single-turn` (1,440 episodes): all 21 checks pass (the 17 of 0.3.0, the 3 new ones and the lookup audit); every no-memory baseline scores 0.10; `nearest_to_stand_in_value` scores 0.10 (validity) and 0.05 (main) in each task cell; the key oracle 1.00 everywhere, the text oracle 1.00 on base and restated and 0.10 on withheld, the no-memory lookup oracle 1.00 on recoverable base and on restated episodes; the clue-level gate as in 0.3.0; atom narrowing 0; `validity_pass=True`. Pilot templates 0-3 (4 templates, an incomplete block, `--partial-blocks`) pass every check of the shortcut and lookup audits; their accuracy gates are not judged (1 of 4 templates is 0.25), in either config.
  - `uv run python -m persistgym audit --preset sol-chain --n 1000` (main templates 0-999, 24,000 episodes, 3,000 per task cell): all 21 checks pass; every no-memory baseline, the prior label and `nearest_to_stand_in_value` score 0.100 (the last in each task cell); the oracles as above; per derived cell, 0 clue-level and 0 atom-level narrowing templates, 0.100 for both gated clue-level heuristics, generator-aware Bayes at most 0.177 (reported), and the six misreadings 0.092-0.110 by clue count (0.098-0.101 pooled); `validity_pass=True`. The same command with the default preset passes too, with `nearest_to_stand_in_value` at 0.100 in each task cell. (Its first run on the variant found 6 templates whose 3-clue running total equals a distractor value, which `hidden_values` then still listed as never shown; §2.)
  - `uv run python -m persistgym partial-memory --preset sol-chain --n 2000` on the pilot, validity and main splits: the clue-level figures of 0.3.0 (0 narrowing; 0.100 and 0.100 for the gated heuristics; generator-aware Bayes at most 0.155, 0.168 and 0.164); atom narrowing 0 in 2,000 templates on each split; the six misreadings score 0.081-0.118 by split and clue count, 0.093-0.108 pooled.
  - The evidence events of validity templates 0-19 have 130-153 tokens, and the restated block 173-262 (180 at m = 2 and 259 at m = 3 on the check's pilot templates 0 and 1).

## 10. Data model (the harness-cell contract)
`Episode` (episode.py) is a plain dataclass with `to_dict` / `from_dict`. It is stored as one JSON object per JSONL line; `persistgym.read_jsonl(path)` reads `.jsonl` or `.jsonl.gz` back into Episodes. Schema 2 adds the distractor fields below, `Component.entity` and `LookupSpec.record_keys`. Schema 3 (generator 0.3.0) adds `Episode.substitutes` and `Step.substitutes` (D39).

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
| `components` | What must be carried (chain form: a clue's `sentence` is its four-sentence chain record and `value` its clue value, never shown): `comp_id` (`fact`, `clue0..2`, `rule`), `role`, `name`, `value`, `sentence` (verbatim), `record` (full displayed line), `step` (None = rule in the system prompt), `entity`. Empty in `withheld` |
| `distractors` | The distractor bindings, as `Component`s with `comp_id` `dist0`, `dist1`, role `distractor` and the other entity in `entity`. The same in every cell and variant; never needed |
| `substitutes` | Withheld variant only (D39): the stand-in bindings, as `Component`s with `comp_id` `sub_<id>` of the component they replace (`sub_fact`, `sub_clue0..2`, `sub_rule`), role `substitute`, the stand-in entity in `entity` and the step of the replaced component; `sub_rule` is the rule sentence verbatim (value None) and is absent when the rule sits in the system prompt. Empty in base and restated; never needed |
| `n_clues` | 0 for observed cells |
| `lookup` | `available`, `key` (the target entity), `syntax`, `max_per_episode`, `records` (record id → line re-shown; target components, or the stand-ins in withheld episodes, and the distractors; in chain form also `<comp_id>@<helper>` for each helper of a clue record), `reveal_steps` (record id → step first shown), `record_keys` (record id → entity) |
| `graph` | Dependency graph (§7) |
| `design` | Designed distances, survival and context sizes (§8) |

`Step`:
- `index`, `kind` (`routine` / `reveal` / `distractor` / `need`), `routine_type`;
- `event` (the EVENT text) and `observation` (the full user message);
- `obs_tokens`;
- `event_start` / `event_end` and `filler_start` / `filler_end` (character spans in `observation`);
- `expected_action` (canonical, e.g. `ack(M-7350)`, `store(H)`);
- `reveals` (component ids first shown here), `restates` (the restated control), `distractors` (distractor ids shown here), `substitutes` (stand-in ids shown here, withheld variant), `sim_time`.

`EpisodeResult` (env.py): `need_correct`, `need_action`, `need_label`, `routine_correct` / `routine_total`, `n_lookups` and `lookup_steps` (lookups served), `n_lookups_unavailable` and `lookup_unavailable_steps` (over-cap lookups), `n_turns`, `step_outcomes` (`correct`, `wrong`, `unparsed`, `invalid_lookup`, `incomplete`) and `turns` (`Turn` with `outcome` also `lookup` or `lookup_unavailable`, `is_lookup_result`, `is_lookup_unavailable`).

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
- [RESEARCHER DECISION] `clue_form` = `direct` (`chain` in `sol-chain`; PREREG §17.3, R3). Clue values printed, or given by a two-hop relay over helper entities (§2; gpt-6.1-sol only).
- [RESEARCHER DECISION] `evidence_notice` = false (true in `sol-chain`; PREREG §17.3, R3). Evidence steps say that the value will be requested and ask for it to be worked out privately (§3; gpt-6.1-sol only).
- [RESEARCHER DECISION] `validity_margin_pp` = 10. PLAN §5 and §16.3: no-memory baselines and the gated partial-memory heuristics ≤ chance + 10pp.

Also fixed for PREREG, though not config fields:
- the presets (`config.PRESETS`) and their pinned hashes (`config.PRESET_HASHES`): `default` for every model, `sol-chain` for gpt-6.1-sol's runs (PREREG §17.3; `harnesses/registered.py` enforces it);
- the chain constants (`template.CHAIN_ANCHOR_RANGE`, `CHAIN_DELTA_RANGE`, `CHAIN_MARGIN`, `CHAIN_MIN_GAP`): changing any of them needs a new generator version;
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
- **The withheld control keeps the rule sentence.** PREREG §4.3 says the control "replaces every evidence binding with a distractor binding of equal token length". Generator 0.3.0 replaces the fact and clue bindings; the rule sentence binds no entity ("for every sample, ...") and carries no information about the target, so it is kept verbatim where the base shows it. A derived withheld episode therefore shows the stand-in's clues with the rule, a complete derivation of a value that is never an option. If "every evidence binding" is read as including the rule, the rule would need its own replacement of equal token length (for example a rule about another quantity), which is not implemented.
- **`sol-chain` asks for intentional memory.** Its notice tells the agent which value will be needed and asks for it to be worked out and kept privately. sol's H2 on it tests the replay of state the model was told to keep, which is narrower than incidental state; and the notice marks the target (D1 does not hold), and is false about the stand-in in the withheld control. luna's runs use the default config, so luna's and sol's derived cells are not comparable.
- **Fixed sentence frames.** The surface text varies through 5 skins but uses fixed frames; a model may learn the format within one episode.
- **Survival by verbatim match** treats a paraphrased record in a user-role message as not surviving. Window harnesses send observations verbatim, so this matters only for summary cells, where `carried_in_text` is the intended measure. String match also misses paraphrased carry ("the code ends in 17"), so P(carried) is an undercount.
- **Token counts are tiktoken's,** not provider-reported. The harness should log both, and payload-S should be checked against what was actually sent.

## 13. G1 spot-check package (`spotcheck.py`; PREREG §4.4)
PREREG §4.4 asks the researcher to spot-check 20 episodes per task cell for shortcuts, "e.g. the fact being inferable from filler"; operationally, generated episodes from the validity range, reviewed without model output. `spotcheck` builds the pages for that review; `spotcheck-findings` checks what the researcher exports.
```
uv run python -m persistgym spotcheck                 # validity templates 0-19 x 8 task cells
uv run python -m persistgym spotcheck-findings --out-id g1-validity-0-20-3d6bc648
```
- **Episodes.** The base variant of validity templates 0 to n − 1 (`--n`, default 20: seeds 50,000-50,019) in all 8 task cells, 160 episodes, rendered with the default `GeneratorConfig`. The command refuses unless the config hash (`common.runmeta.config_hash`, the function the runner uses) equals `spotcheck.EXPECTED_CONFIG_HASH`, the `generator_config_hashes` value `3d6bc648…` of the two luna validity runs of 2026-10-02. So these are the templates and the config those runs used; they sent the restated and withheld variants of the same template-cell pairs (a test checks the ids against both runs' `meta.json`). `--n` is a whole number of balance blocks (D7).
- **Audits.** The build re-runs the $0 checks of §9 (shortcut audit, lookup audit, heuristic baselines, partial-memory gate, oracles) on these templates in all three variants, 480 episodes at n = 20. The index page and the manifest list the results; the exit code is 1 if one fails. The two chi-square balance checks pass without a test below 5 templates per letter or rank (50 at K = 10), so they are listed as not run at n = 20; the exact per-block check (`letter_rank_and_n_clues_exact_within_complete_blocks`) does run.
- **Pages** (`results/raw/spotcheck/<id>/`, gitignored, 17 MB at n = 20, regenerable): `index.html` (instructions, audit results, progress per task cell, export and import) and one page per task cell. They are static HTML with inline CSS and JS and a Content-Security-Policy that allows nothing else, in light and dark themes. Each episode is a card with:
  - a summary box with the answer: the target key; the value, or the clues, the rule and the derived value; the options with the correct one marked; the evidence steps, the distractor bindings and whether lookup is offered;
  - the scan line (below);
  - the need-step observation in full;
  - the full episode, system prompt first. Each step's log tail is collapsed and opens by itself if it holds a marked string. A Skim toggle shows only the steps with evidence, a distractor binding, the target key or an option string;
  - highlights, with a legend: evidence bindings, the target key, option strings (the correct one outlined) and distractor bindings.
- **Scan** (`scan_episode`). Every occurrence of an option string (a whole number) or of the target key (a whole word, any case), in the system prompt and every observation, outside the places it belongs: option strings in the need step's option list and, for an observed fact, in its binding at the step that reveals it; the key in the evidence bindings at the steps that reveal them and in the need question. A binding repeated at another step is therefore reported. The audits use the same matching rules. The scan found nothing in any of the 160 episodes.
- **Findings.** Each card has a three-way verdict and a notes box. Nothing is pre-filled. They are saved in the browser's localStorage under `persistgym-spotcheck/<id>/`, a namespace every page of the package shares, and every storage access is wrapped so the pages work, and say so, when storage is blocked: a finding the page cannot write stays in memory, the browser asks before the page closes, and findings already stored are still read and exported. **Export findings CSV** downloads `findings.csv` with all rows: `episode_id, task_cell, template_seed, verdict, notes`, where verdict is `no_shortcut`, `possible_shortcut`, `shortcut` or empty. It is RFC 4180 with CRLF line ends, byte for byte what Python's csv module writes (tested with node when it is installed). **Import** loads an exported file back; it skips rows whose episode id, task cell or seed are not in the package.
- **Package** (`results/spotcheck/<id>/`, committed): `manifest.json`, `findings_template.csv` (every row with an empty verdict and notes) and `README.md` (how to open the pages and where to save the export). Rebuilding with the same id rebuilds the pages and keeps these files if they describe the same episodes; otherwise it refuses. The researcher saves the export as `findings.csv` there. `.gitattributes` turns off line-end conversion for these CSVs, so git keeps them byte for byte (CRLF). `spotcheck-findings` checks it against the manifest (the header, each episode once with its task cell and seed, known verdicts), prints the counts per task cell and every possible or definite shortcut with its notes, and exits 1 while episodes are unreviewed.
- **`--preset sol-chain`** (PREREG §17.3): sol's variant, against its pinned hash (`config.PRESET_HASHES`), on the 4 far task cells only (`spotcheck.PRESET_CELLS`; 80 episodes at n = 20, as R3 proposes), with the audits on all 8 cells and 3 variants. Each clue's relay is worked out in the summary box, marked as not shown in the episode, and the notice is shown; the scan allows the target key inside the notice at the evidence steps. The default preset keeps checking the luna validity runs' hash.
- **Manifest digest.** A manifest records `episodes_sha256`, the sha256 of its base episodes as canonical JSON without `generator_version` (`episode.versionless_json`), and a rebuild with the same id must match it, the split, variant, config hash and episode ids; the generator version is not compared. luna's committed manifest (generator 0.3.0) has no digest; it matches while the episodes have the digest pinned at 0.3.0 (`spotcheck.GOLDEN_0_3_0_SPOTCHECK_SHA256`).
- **What it does not show.** The scan and the audits match exact strings, so they cannot see a value that is implied rather than written (a pattern in the filler, a story that makes one option likelier); the researcher's review looks for those. Twenty templates per cell, the same twenty in every cell, can reveal a shortcut but cannot show that none exists.
