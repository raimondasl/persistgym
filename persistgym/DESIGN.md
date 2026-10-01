# PersistGym-lite generator: design

_Track: M0 PersistGym build (PLAN.md §5, §6; amendment A1 §16.3 and §16.5). Generator version 0.1.1, episode schema 1. Everything here is $0: no API calls._

_0.1.1 (review of PR #7): a biobank site no longer contains an entity name; a lookup key matches when it contains the entity name as a word; single-turn controls come from non-recoverable cells only and have a scorer; a partial-memory diagnostic is reported (§9, §12)._

PersistGym-lite generates multi-turn episodes in which one target fact is needed at a known step. Each template is rendered into 8 task cells that vary three things one at a time, at a fixed token volume per observation:
- **observed vs derived:** the fact is shown verbatim once, or it must be computed from 2-3 clues plus a combining rule and is never shown in final form;
- **recoverable vs not:** a `lookup` action can re-show the records (costing one turn), or nothing can;
- **near vs far:** the latest reveal is 4 steps before the need step, or beyond the eviction threshold W counting observation tokens only.

The harness cells (F, W, Σ; notes and replay flags) are a separate track. This package gives them episodes, a runner with exact lookup semantics, oracles, survival accounting and validity checks. Every place where a PREREG definition matters is a named config field, listed in §11 and tagged **[RESEARCHER DECISION]**.

## 1. Quick start
```
uv run python -m persistgym render --n 20                    # main split, templates 0-19
uv run python -m persistgym render --split pilot --n 5 --single-turn --gzip
uv run python -m persistgym render --n 50 --W 24000 --v 1500 --set assumed_max_reply_tokens=800
uv run python -m persistgym partial-memory --n 2000          # templates only, no rendering
uv run pytest -q persistgym && uv run ruff check persistgym
```
`render` writes to `results/raw/persistgym/<split>-<start>-<n>-<confighash8>/` (gitignored):
- `episodes.jsonl[.gz]`: one Episode per line (§10);
- `single_turn.jsonl[.gz]`: position-matched single-turn controls for the 4 non-recoverable cells (with `--single-turn`);
- `summary.json`: per-cell shape, the shortcut audit, the heuristic baselines, oracle scores and the partial-memory diagnostic;
- `manifest.json`: config, config hash, generator version, seed ranges, tiktoken version, git commit and dirty flag.

The exit code is 1 if any validity check fails. A rendered episode is about 110 KB of JSON at the defaults (about 2.6 MB per template for 8 cells × 3 variants); use `--gzip` for large N.

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
| reveal | `memo` | `Intake memo M-7350. For sample BEECH, the rack slot is 297. Reply ack(M-7350) to acknowledge it.` | `ack(M-7350)` |
| need | — | `Sample BEECH needs its freezer slot now. Options:` / `A) 799` ... `J) 601` / `Reply store(<letter>) with the letter of the correct option.` | `store(H)` |

Routine actions depend only on the current observation; the dependency graph records this (§7). Reveal steps are acknowledged like broadcasts, so they need no memory either. Only the need step depends on the past.

**Target values.** The target and all K=10 options are distinct 3-digit integers in `value_range` (300-899). Options are listed with letters A-J. Clue values are a 3-digit base plus one or two 2-digit addends in 61-98 (above 59, so they can never collide with clock fields in the logs). No clue value is ever an option.

**Observed facts:** one record, `For sample BEECH, the freezer slot is 460.`

**Derived facts:** 2 or 3 clue records on consecutive steps (`clue_spacing_steps`=1), e.g. `the rack slot is 297`, `the shelf offset is 98`, `the overflow shift is 65`, plus the rule `Rule: for every sample, freezer slot = rack slot + shelf offset + overflow shift.` The rule is shown with the last clue by default (`rule_placement`). The combining operation is always a sum; changing it is a code change. The target never appears before the need step in a derived episode (audited).

**Surface stories (skins).** Five skins (warehouse, biobank, datacenter, archive, depot) change nouns only: facility, entity names, quantity and clue names, record sources, routine tags, sensor metrics and log service names. Every sentence uses the fixed frames in `render.py`, which the oracle parses.

## 3. Task cells and variants
`TaskCell(fact, recoverable, distance)`; ids like `derived-rec-far`. All 8 cells of a template share:
- the need step index, the need event, the options, the correct letter and the correct value;
- the routine event and log filler of every step index (identical observation text wherever both cells have a routine step);
- the clock and the system prompt, except for the lookup paragraph in recoverable cells (and the standing rule in derived cells when `rule_placement` is `system_prompt`).

Within a template, the need observation is byte-identical across all 8 base cells and the withheld cells (audited).

| | where the components are revealed | lookup |
|---|---|---|
| near | latest component at `n - near_gap_steps` (n−4); earlier clues at n−5, n−6 | — |
| far | latest component at `n - far_gap_steps` (n−16 at the defaults); earlier clues at n−17, n−18 | — |
| recoverable | (same placement) | `lookup(<name>)` re-shows the records; system prompt explains it |
| not recoverable | (same placement) | `lookup` is an invalid action |

**Far** (amendment §16.5): observation tokens from the latest reveal step through the need step, inclusive, exceed `W_tokens + far_margin_tokens`. `far_gap_steps = floor((W + margin) / v)`. At the defaults that is 16: 17 observations × 1,500 = 25,500 > 24,000. Since replies only add tokens, every component is evicted by a drop-oldest window of W whatever the replies are. **Near:** every component survives the window when each reply has `assumed_max_reply_tokens` (1,000) tokens. At the defaults the earliest near component is at most 6 steps back (7 observations + 6 replies = 16,500 ≤ 24,000). The generator refuses to emit a cell that breaks either rule, and the audit re-derives both from the text.

**Variants** (`Episode.variant`):
- `base`: the cell as described.
- `restated`: the need event starts with `Records on file for sample BEECH:` and repeats the records (`restate_mode`: as revealed by default, so derived facts still need combining). This is the ceiling with memory taken out of the problem (validity gate: LLM ≥ 85%).
- `withheld`: every reveal record is replaced by a null record from the same source with the same id and no value (`Sample BEECH has been logged at intake.`). The step structure is unchanged and `components` is empty (validity gate: LLM ≤ chance + 10pp).

**Position-matched single-turn control** (`controls.single_turn_control`, H3): the same observations 0..n, with replies between them, flattened into one user message after a one-line preamble. Replies default to the minimal correct reply `ACTION: <expected>` (`single_turn_reply_mode`). Passing a real run's replies yokes the control to that run. The result records each component's token offset in the flattened prompt and in the multi-turn message contents. The two differ only by the separator tokens (`<<< update >>>`, `<<< operator reply >>>`) and the preamble.
- It is built from **non-recoverable** base episodes only. A recoverable cell has the same observations, and its system prompt offers `lookup`, which a single prompt cannot serve, so its control would differ only by offering an action that cannot work. Compare it with the multi-turn non-recoverable cell.
- `controls.score_single_turn(control, reply)` scores a reply exactly as `EpisodeEnv` scores the need step (same parser, letter or value).

## 4. Lookup semantics (exact; `env.EpisodeEnv`)
- Lookup is available only in recoverable cells, at most `lookup_max_per_episode` (3) times per episode.
- When the reply's action is `lookup(<key>)`, the pending step is **not** scored and does not advance. The next observation is a lookup result, padded to v tokens like any observation. It contains:
  - `LOOKUP RESULT for sample BEECH:`, followed by every record about the entity first shown at or before the pending step, verbatim as originally displayed (records that share a step are merged into one line);
  - `Pending request (repeated): <the pending step's event>`.
- The agent then answers the repeated request. **A lookup therefore costs exactly one extra turn and v tokens.**
- The key matches if it contains the entity name as a whole word, ignoring case (`BEECH`, `beech` and `sample BEECH` match; `BEECHES` does not). With one entity per episode this is unambiguous, and it keeps formatting slips from adding turns and tokens that are not about memory (H1's cost outcome). Any other key returns `no records found` and still costs the turn. A lookup before any reveal returns `no records yet`.
- In non-recoverable cells, or once the limit is used, `lookup(...)` is an invalid action. The pending step is scored wrong (`invalid_lookup`), the episode advances and no extra turn is added.
- Lookup observations are deterministic: same template seed, pending step and lookup number give the same text. `render.renderer_for(episode)` rebuilds the renderer from `template_seed` and `config`, so this also works for episodes loaded from JSONL.

**Scoring.** The action is the last `ACTION: verb(arg)` line. If there is none and `strict_action_parse` is false, the last `verb(arg)` with a known verb anywhere in the reply counts. A reply with no parseable action is scored wrong (`unparsed`), with no re-prompt. At the need step the verb must be the episode's `need_verb`, and the argument may be the letter or, if `accept_value_answers`, the option value. `EpisodeResult` gives need success, routine accuracy, the lookups and the turn at which each was used, the number of turns, per-step outcomes and per-turn observation tokens.

## 5. Token budget and filler
- One tokenizer, tiktoken `o200k_base`, is used for generation and window accounting. Provider-reported tokens differ by per-message overhead; the harness logs both.
- Every observation, including lookup results, has exactly `v_tokens` tokens (`token_tolerance` 0; audited by re-counting). The filler is a token-level suffix of a per-slot pool of chronological log lines, so the earliest kept line is cut as a log tail would be. If a BPE merge at the cut makes v unreachable, the pool's newest line is dropped (at most 3 times) to shift the alignment.
- The filler pool of step t is seeded by (template seed, t), so cells share it. Its clock times lie in (T(t−1), T(t)], with `step_seconds`=75.
- **Reserved strings** never appear in filler or routine text: every option value, every clue value, the entity name, the quantity name and the clue names. Numbers are matched unless embedded in a longer digit run; words are matched case-insensitively unless embedded in a longer word. Filler lines that would contain one are resampled. The audit re-checks this independently from the text.

## 6. Templates and seeds
- Template `i` of split `s` has seed `SEED_RANGES[s][0] + i`, with `main` = [0, 1,000,000) and `pilot` = [9,000,000, 9,100,000), so the ranges are disjoint (amendment §16.5: pilot templates use a disjoint seed range). Template ids look like `main-000017`.
- Every random choice uses a named stream `random.Random(f"pg:{seed}:{stream}")`, so adding a stream never shifts the others. String seeding is SHA-512 based and does not depend on `PYTHONHASHSEED`.
- **Balance by construction:** within each block of K consecutive template indices, every letter is correct exactly once, and every rank of the correct value among the sorted options occurs exactly once. Each block uses its own seeded permutations. Option values are a uniform random K-subset of `value_range`.
- Sampled per template: skin, entity, site, option set, rank and letter, number of clues (2 or 3), clue decomposition, record ids, need index, tail length, one routine event per step, and the start clock.

## 7. Dependency graph (`graph.DependencyGraph`, `Episode.graph`)
Built from the script, never from agent trajectories (PLAN §4).
- **Nodes:** `obs:t`, `act:t`, `comp:<id>`, `fact`, plus `env:lookup` in recoverable cells and `system_prompt` when the rule sits there.
- **Edges:**
  - `obs:r → comp:c` (reveals);
  - `comp:c → fact` (`is` for observed, `derives` for derived);
  - `fact → act:n` (determines);
  - `obs:t → act:t` for every other step (routine actions need only their own observation);
  - `env:lookup → comp:c` (re-shows).
- `needed_step("fact")` = n. `live[c]` = [reveal step of c, n]. `live["fact"]` = [latest reveal, n]. `live_at(t)` lists what must be carried at step t. In the withheld variant, the fact has no parents.

## 8. Survival calculator (`survival.py`)
- **Window model** (as ARC Standard): before sending observation m, keep the longest suffix of whole (observation, reply) turns that fits in W tokens. The current observation is always kept. The system prompt counts only if `window_counts_system_prompt`.
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
- **Near and far are designed for drop-oldest windows.** Far holds for any loss policy that keeps at most W tokens of observations, so the reveal is outside the verbatim context whatever the replies are. Near holds only for a policy that keeps the most recent W tokens verbatim. A summary cell that compacts the whole history whenever the context passes W can compact a near reveal: with 1k-token replies a full history passes 24k at step 9 or 10, and a second compaction can land between a near reveal (n−4 to n−6) and the need step. The harness track must either summarize only the turns that fall outside the most recent W tokens, or treat near-cell S in summary cells as measured (string match), not designed.
- `carried_in_text(text, ep)`: P(carried) accounting for logged summaries and notes. A value counts if it appears as a standalone number within `carried_match_window_chars` (200) of the entity name. Derived facts count as carried if the final value is carried, or if every clue value is (plus every clue name, if `carried_requires_rule`).
- `reference_window_payload(ep, replies)`: a reference drop-oldest payload for cross-checking harness implementations. Tests show that its payload-S equals the designed S when replies have the assumed length.

## 9. Oracle and validity checks
- **Oracles** (`oracle.py`):
  - `KeyOracle` replies with the answer key.
  - `TextOracle` reads only what an agent sees (system prompt and observations) and parses the fixed sentence frames. With memory, it must score 100% on need and routine steps in every base and restated episode. This checks that the information is in the text and that derived facts are computable from it.
  - `TextOracle(memory=False, use_lookup=True)` forgets everything and looks up at the need step. It must score 100% on recoverable cells, which checks lookup.
  - Without memory or lookup, the text oracle guesses the first option.
- **Shortcut audit** (`validity.shortcut_audit`). It re-derives everything from the text, independently of the generator's bookkeeping:
  - no reserved string in any filler or routine event;
  - every observation re-counts to exactly v tokens;
  - derived and withheld episodes never show the target before need, and observed episodes show it only at the reveal;
  - options are valid and distinct, and exclude clue values;
  - near and far still hold when recomputed from the step at which each component sentence first appears and the re-counted tokens;
  - the full-history context at need, with assumed replies, is ≤ `max_context_tokens`;
  - cells share the need observation, options and routine text;
  - the correct letter and rank are balanced (chi-square p > 0.01 once there are at least 5K templates).
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

  Each must score ≤ chance + `validity_margin_pp` (10%+10pp = 20%). Because no option value ever occurs outside the option list in these views, the two text heuristics fall back to positional guesses. Block balance then puts every baseline at chance.
- **Result** (from `uv run python -m persistgym render --n 60 --single-turn --gzip`, 1,440 episodes):
  - all 12 audit checks pass;
  - every baseline scores 0.10 on every view (threshold 0.20);
  - need-step accuracy of the oracles:
    - key oracle: 1.00 everywhere;
    - text oracle: 1.00 on base and restated, 0.10 on withheld;
    - lookup oracle without memory: 1.00 on recoverable base and on restated, 0.10 on non-recoverable base and on withheld;
  - routine accuracy is 1.00 for the key and text oracles.

  Re-run that command to reproduce; the numbers are in its `summary.json`. The review of PR #7 re-ran it at generator 0.1.0 and got the same numbers.

  The baselines sit at exactly 0.10 *because of* block balance: no option value ever occurs outside the option list, so every text heuristic falls back to a position, and every position is correct once per block of 10. They rule out positional and frequency shortcuts; they do not rule out an LLM prior over values, which only the paid withheld run at G1 can measure.
- **Partial-memory diagnostic** (`validity.partial_memory_diagnostic`; reported in `summary.json` as `partial_memory`, not gated). It asks what an agent that kept only the base clue of a derived fact can do. Result from `uv run python -m persistgym partial-memory --n 2000` (main templates 0-1,999):

  | | 2 clues (n=1,035) | 3 clues (n=965) | all |
  |---|---|---|---|
  | base clue + rule + the addend range leave exactly one option | 0.550 | 0.347 | 0.452 |
  | expected accuracy, uniform pick among the options left | 0.755 | 0.621 | 0.690 |
  | smallest option above the base clue (no range knowledge) | 0.308 | 0.151 | 0.233 |

  The pilot split (templates 0-1,999) gives 0.687 and 0.246 for the two accuracies. Agents are never told the addend range, so the two accuracy rows bracket plausible base-only behaviour rather than bound it. Even the naive 0.23 is above the 0.20 no-memory threshold. See §12.

## 10. Data model (the harness-cell contract)
`Episode` (episode.py) is a plain dataclass with `to_dict` / `from_dict`. It is stored as one JSON object per JSONL line; `persistgym.read_jsonl(path)` reads `.jsonl` or `.jsonl.gz` back into Episodes.

| Field | Meaning |
|---|---|
| `episode_id` | `<template_id>/<cell id>/<variant>` |
| `template_id`, `template_seed`, `split` | Template identity; reproducible from seed + config |
| `cell` (TaskCell; JSON: cell id), `variant` | Task cell and `base` / `restated` / `withheld` |
| `config`, `config_hash`, `generator_version`, `schema_version` | Full generator config and its SHA-256 (`common.runmeta.config_hash`) |
| `skin`, `kind`, `entity`, `quantity`, `need_verb` | Surface story; `need_verb` is the need action's verb |
| `system_prompt`, `system_tokens` | Task instructions (the harness adds its own notes instruction) |
| `steps` | List of `Step` (below) |
| `need_step` | Index of the need step |
| `options` (`label`, `value`), `correct_label`, `target_value` | The K options, the correct letter and value |
| `components` | What must be carried: `comp_id` (`fact`, `clue0..2`, `rule`), `role`, `name`, `value`, `sentence` (verbatim), `record` (full displayed line), `step` (None = rule in the system prompt). Empty in `withheld` |
| `n_clues` | 0 for observed cells |
| `lookup` | `available`, `key`, `syntax`, `max_per_episode`, `records` (comp_id → line re-shown), `reveal_steps` |
| `graph` | Dependency graph (§7) |
| `design` | Designed distances, survival and context sizes (§8) |

`Step`:
- `index`, `kind` (`routine` / `reveal` / `need`), `routine_type`;
- `event` (the EVENT text) and `observation` (the full user message);
- `obs_tokens`;
- `event_start` / `event_end` and `filler_start` / `filler_end` (character spans in `observation`);
- `expected_action` (canonical, e.g. `ack(M-7350)`, `store(H)`);
- `reveals` (component ids first shown here), `restates` (the restated control), `sim_time`.

The harness should drive episodes through `EpisodeEnv` (`observation`, `step(reply) -> (next observation, done)`, `result()`). It must not replay `steps` directly, because a lookup inserts a turn. `EpisodeEnv.info` (pending step, whether the observation is a lookup result, observation tokens) is bookkeeping for logs and must never be shown to the model.

## 11. Researcher decisions
Each item below is a named field of `GeneratorConfig` (config.py; also listed in `RESEARCHER_DECISIONS`). Each needs the researcher's confirmation in PREREG.md. Defaults come from PLAN.md where it gives a number; the others are marked "proposed".
- [RESEARCHER DECISION] `W_tokens` = 24,000. PLAN §5. Eviction threshold. Amendment §16.5 asks for a tuning rule applied in M1 rather than a fixed number.
- [RESEARCHER DECISION] `v_tokens` = 1,500. PLAN §5. Tokens per observation; with W it fixes the far gap (`floor(W/v)` = 16 steps).
- [RESEARCHER DECISION] `near_gap_steps` = 4. PLAN §5: "reveal about 4 steps before need". For derived facts this places the *latest* component; the earliest is up to 2 steps earlier.
- [RESEARCHER DECISION] `far_margin_tokens` = 0 (proposed). Far = observation tokens from the latest reveal through need > W + margin. Any margin below v (1,500) leaves the far gap at 16 steps at the defaults; a margin of v or more makes it 17 and raises the minimum need index to 21.
- [RESEARCHER DECISION] `assumed_max_reply_tokens` = 1,000 (proposed; ARC Standard's published visible output averages about 907 tokens per action, `docs/background.md` §4). Near cells must keep S=1 at this reply length. At the defaults, near cells keep S=1 up to uniform replies of 4,125 tokens (observed), 3,000 (2 clues) and 2,250 (3 clues). `max_reply_tokens_for_survival` gives the exact limit per episode, and payload-S catches longer real replies.
- [RESEARCHER DECISION] `window_counts_system_prompt` = false (proposed). Whether W must also hold the system prompt; it must match the harness cells.
- [RESEARCHER DECISION] `max_context_tokens` = 64,000. PLAN §5: "contexts stay ≤ 64k". Checked by the audit for full history with assumed replies.
- [RESEARCHER DECISION] `K_options` = 10. PLAN §5. Chance = 10%.
- [RESEARCHER DECISION] `need_index_range` = (20, 24) (proposed). 20 is the minimum for far derived cells at the defaults; 24 keeps full history ≤ 64k with 1k replies. Episodes have 21-27 steps.
- [RESEARCHER DECISION] `tail_steps_range` = (0, 2) (proposed). Routine steps after need. They make "need = last step" untrue, but they cost tokens and carry no outcome.
- [RESEARCHER DECISION] `n_clues_choices` = (2, 3). PLAN §4: "computed from 2-3 observations"; sampled per template.
- [RESEARCHER DECISION] `clue_spacing_steps` = 1 (proposed). Consecutive steps are "different steps". A larger spacing widens the derived reveal span and tightens the near reply budget.
- [RESEARCHER DECISION] `rule_placement` = `with_last_clue` (proposed). Alternatives: `with_first_clue`, `separate_step`, `system_prompt`. This sets the step at which derivation first becomes possible.
- [RESEARCHER DECISION] `restate_mode` = `as_revealed` (proposed). The restated control repeats the clues and rule, so it removes memory but not derivation. `final_value` restates the computed value instead.
- [RESEARCHER DECISION] `single_turn_reply_mode` = `oracle` (proposed). What fills the reply positions in the flattened H3 control. `none` drops them; a real run's replies can be passed per episode.
- [RESEARCHER DECISION] `warn_future_need` = true (proposed). The system prompt sentence "Some requests depend on records shown in earlier updates." It is the same in all cells.
- [RESEARCHER DECISION] `lookup_max_per_episode` = 3 (proposed). The limit on lookups per episode.
- [RESEARCHER DECISION] `accept_value_answers` = true (proposed). At need, accept the option value as well as its letter.
- [RESEARCHER DECISION] `strict_action_parse` = false (proposed). Fall back to the last known `verb(arg)` if the reply has no `ACTION:` line.
- [RESEARCHER DECISION] `carried_match_window_chars` = 200 (proposed). The string-match rule behind P(carried) for summaries and notes; 0 matches the value anywhere.
- [RESEARCHER DECISION] `carried_requires_rule` = false (proposed). Whether carrying all clue values of a derived fact also requires the clue names (a proxy for the rule).
- [RESEARCHER DECISION] `validity_margin_pp` = 10. PLAN §5 and §16.3: no-memory baselines ≤ chance + 10pp.

Also for PREREG, though these are not config fields:
- the seed ranges (`config.SEED_RANGES`);
- that unparseable replies count as wrong with no re-prompt;
- that the combining rule is a sum.

## 12. Known limitations and what this does not show
- **Not yet checked with a model.** The $0 checks show that the generator is internally consistent and has no trivial shortcut. They do not show that an LLM finds the routine steps easy, that restated-at-need reaches ≥ 85%, or that the fact-withheld control sits at chance. Those are the paid validity runs at G1.
- **Partial memory gives a lot away in derived cells.** A model that kept the base clue (and the rule) but lost the 2-digit addends can drop every option outside [base + 61, base + 98] (2 clues) or [base + 123, base + 195] (3 clues). One option is left in 45% of templates, and a uniform pick among those left scores 0.69 (§9). Picking the smallest option above the base, with no idea of the range, scores 0.23. This is memory, not a no-memory shortcut, and window cells never carry the base alone (near keeps every clue, far drops every clue). It matters wherever a model writes what it carries: notes and summary cells, and the accounting P(rescued | not carried), where a summary that kept only the base counts as "not carried" (`carried_in_text`) yet can still succeed. **[RESEARCHER DECISION]** before PREREG: accept and report it (e.g. log a "base only" carried category), or change the option set so the base alone does not narrow it, e.g. options built as several equal-sized clusters of close values with the target in one of them (no-memory accuracy stays 1/K; base-only accuracy falls to about 1 / cluster size). Any such change makes the option set depend on the clues and must keep the no-memory baselines at chance; it is not done here.
- **The fact is salient.** Reveal records are the only events that mention the entity before the need step. No distractor records about other entities are generated (k=1).
- **Fixed sentence frames.** The surface text varies through 5 skins but uses fixed frames; a model may learn the format within one episode.
- **Survival by verbatim match** treats a paraphrased record in a user-role message as not surviving. Window harnesses send observations verbatim, so this matters only for summary cells, where `carried_in_text` is the intended measure.
- **Token counts are tiktoken's,** not provider-reported. The harness should log both, and payload-S should be checked against what was actually sent.
