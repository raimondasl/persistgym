Version: 1.0

**Status: Frozen on 2026-10-01 by Raimondas Lencevicius (sign-off in PR #4).**

**Change rule.** After freezing, this file changes only by a dated amendment that states its reason, appended to the amendment log (§17) and merged through a pull request. Hypotheses, predictions and thresholds are never edited after any result they concern has been seen. Analyses not registered here are reported as exploratory.

# PREREG: when does the harness matter?

## Summary in plain language
A reading aid. Where it and the numbered sections differ, the numbered sections win.

**The question.** With the model fixed, when does the agent harness (what history it keeps, whether it asks for notes, whether it replays the model's earlier reasoning) change whether the agent *succeeds*, not only what it costs? Our bet: success suffers when the needed fact was worked out from several observations (*derived*), cannot be looked up again (*not recoverable*), and was thrown away by the harness (*evicted*). When the fact can be looked up again, the harness should change cost, not success.

**What we run.**
- **PersistGym-lite**, a generated task of about 20-32 turns. At one turn the agent must pick the right value out of 10 options (chance 10%). The value was shown earlier directly (observed) or as clues to add up (derived), may or may not be retrievable with `lookup`, and sits a few turns back (near) or beyond the harness window W (far). gpt-6-luna runs H1 and H3 (about 100 templates per task cell); gpt-6.1-sol runs H2 on derived-far and observed-far cells only (120 and 40 templates at the central size, at most 210 and 70).
- **ARC-AGI-3**, Gemini 3.8 Flash at high thinking, standard tier, in ARC's own harness: 4 fixed public games (FT09, SB26, R11L, CD82) × 4 configs × 2 seeds = 32 runs. The configs step from the Standard harness (S0) to the Provider Adapter (S4): S1 summarizes instead of dropping old turns, S2 also drops the notes instruction, S4 adds native reasoning replay.
- **StateCarry** (phase 2), our state component for the Standard harness: 3 held-out games (SP80, VC33, TN36) × {S0, S4, S0+StateCarry} × 2 seeds = 18 runs.

**Numeric predictions.**
- **H1** (luna; observed fact, far; window without notes vs full history): not recoverable, success drops ≥ 25 points; recoverable, it stays within 5 points while lookups and need-phase tokens rise ≥ 30%. The confirmatory test is the difference between the two drops.
- **H2** (sol; replay on vs off): < 3 points apart on observed far facts; on derived far facts, replay adds ≥ 8 points, or else the no-replay arm uses ≥ 25% more reasoning tokens at the need step.
- **H3** (luna): with the fact still in context, multi-turn and single-prompt differ by ≤ 5 points.
- **H4** (ARC, descriptive): A: loss policy carries ≥ 1/3 of the S0→S4 gap, replay ≤ 1/2, notes within ±10%. B: replay carries ≥ 1/2.
- **H5** (ARC): the Adapter's advantage in P(clear a level | reached it) is larger at levels ≥ 4 than at 1-2.
- **StateCarry**: closes ≥ 50% of the held-out S0→S4 gap at a billed cost per game ≤ S4's.

**Kill rules** (Claude proposes, the researcher decides; §10): (1) no verifiable replay toggle → H2 moves to open weights; (2) billed ARC forecast plus 20% reserve over $900 → 3 games, then medium thinking; (3) PersistGym fails validity after one redesign → ARC alone; (4) ARC gap < 10 RHAE → stop the ARC path leg; (5) H1 and H2 inside equivalence bounds and replay ≥ 2/3 of the ARC gap → short note, no StateCarry; (6) a one-component ARC ablation appears → the ARC table becomes supporting material; (7) StateCarry v0 closes < 25% on dev games → stop the builder.

**Not claimed.** No model ranking. ARC results cover 4 public games picked for large published gaps, one model, one effort. The path split is order-dependent and descriptive (8 game-seed units), and its replay step bundles replay with the native message format. PersistGym is synthetic. "Inside equivalence bounds" is not "no effect". StateCarry is not a new idea (§15).

**Money** (forecasts, not measurements; §12). Caps, approved by the researcher on 2026-10-01: phase 0 $100, 1a $500, 1b $900, 2 $1,250. The billed forecast through phase 2 is $2,563.38 at 1k output tokens per PersistGym call. Spend to date is $0. Each paid block needs a researcher-merged approval line. Paid runs go one at a time until per-stream locks are added before block 3; from then on the ARC runs (back to back, in a beacon-seeded order) and the PersistGym runs may go side by side, one run at a time in each stream. When a counted ARC run is stopped by its $120 guard, no further paid run starts until the researcher clears the hold (§12).

## 0. How to read this file

### 0.1 Sources
- Built from `PLAN.md` §4-§10 as amended by A1 (`PLAN.md` §16, PR #2) and A2 (`PLAN.md` §17, PR #18, merged to `main` on 2026-10-01 as `9090bca`). Where §17 and an earlier PLAN section, §16 included, disagree, §17 wins (PLAN header, A2).
- The researcher's decisions of 2026-10-01 on items D1-D39 (§16), the two follow-ups to A2 the same day (the phase 2 cap is $1,250 and the T_d ceiling is 210), and the answers to the sign-off list the same day (§0.3) (`results/decisions.md`). Several decisions replace PLAN text: the game draw, the third held-out game, the service tier, `TIME_BUDGET` re-runs, the phase 2 cap and part of the sol design. A2 records the same changes in PLAN. The PLAN quotes below stay verbatim, and the Operational text says what replaces them.
- Code facts come from merged pull requests #8 and #14 (ARC patches 0001-0016), #13 (paid guard, need-phase tokens, `compacted_between`), #15 (generator 0.2.0), #16 (game draw script), #17 (option-A recordings, cost scenario, power simulation), #18 (A2: `PHASE_CAPS` and the cost run below), #19 (the guard counts billed spend), #21 (patch 0017, the ARC config freeze record, the guarded ARC launcher), #22 (D13: the 32,000 output cap on every OpenAI request, and `incomplete` responses), #25 (generator 0.3.0: D39's withheld control with stand-in bindings), #24 (the PersistGym launcher takes the paid-run lock, checks the ledger and requires a frozen PREREG; the shared `common.approval.require_paid_run` and `common/prereg.py`) and #23 (the ARC launcher checks `arc/config_freeze.json` and `arc/patches` against `origin/main` and against the §7.1 tables; it contains #24). #18, #19, #20 and #21 were merged on 2026-10-01, before the freeze; their merge commits are in the sign-off table (§0.4). #22, #25, #24 and #23 are merged after them and before the freeze, in that order; their merge commits are recorded in `results/decisions.md` after those merges, not in this file (§0.4).
- Numbers cite the committed results file they come from (each run folder has a `meta.json`). Cost forecasts come from `results/cost_model/20261001T203318Z/` (A2, merged with PR #18). That run replaces `20261001T185959Z` (PR #17) for every option-A number; its ARC tables are identical to the older run's. The ARC config hashes come from `arc/config_freeze.json` (merged with PR #21).
- Facts and their URLs are in `docs/background.md` and `docs/premise-check.md`. The few new outside facts in this file carry their own URL and check date.

### 0.2 Conventions
- **Blockquotes (`>`) are copied from PLAN as written.** No prediction or threshold inside them has been changed. Each one cites its PLAN section so the two files can be diffed. "[...]" marks an elision, and omitted table rows are named below the table (§6). Nested list items are sometimes run together on one line; their words are unchanged. Section numbers *inside* a blockquote are PLAN's own. The quotes are of PLAN as amended by A1 (as on `main` at `07e2b5c`, before A2 was merged). A2 appends **[A2]** notes to some quoted passages, at the end of a line or table cell; the quotes leave those notes out, and the Decision paragraphs here state the same decisions.
- **Text marked "Operational"** says how each quantity is computed and from which logged field (§2.1). It changes no prediction or threshold. Where PLAN can be read more than one way, it states the reading used.
- **Decisions.** Each paragraph headed "**Decision.**" states the rule the researcher decided and ends with "(decided 2026-10-01, D*n*)". A short "*Why*" follows where the choice is not obvious. §16 maps D1-D39 to their outcomes in plain words. Where a sign-off answer (§0.3) changes a decided text, the change follows it in a paragraph headed "**Changed at sign-off**". These decisions are logged in `results/decisions.md` (entries of 2026-10-01).
- "PLAN §x" always means `PLAN.md`; "§x" alone means a section of this file.

### 0.3 Sign-off: details confirmed or changed
The D items left these operational details open, and this draft had to fill them in. None of them changes a hypothesis, prediction or threshold. "Rec." is Claude's recommendation. The researcher answered every line on 2026-10-01: lines 1-11, 13 and 14 are **confirmed** as recommended, and lines 12 and 15 are **changed by the researcher**. The changed lines are written into the decided text (§4.6, §7.4, §7.7, §12 and the register, §16).

1. **Which ending decides a re-run** (§7.5, D19): the agent's own ending (`agent_exit_reason`), not the field ARC can rewrite after the game; a missing one counts as `UNKNOWN`. Rec.: yes. **Confirmed.**
2. **Unreadable scorecard** (§7.5): a finished run whose scorecard result cannot be read is re-run once, as `UNKNOWN`. Rec.: yes. **Confirmed.**
3. **Latency yardstick** (§7.5, D20): "the config's earlier counted runs" means the median of their per-run median seconds per call, over all games. Rec.: yes. **Confirmed.**
4. **3-game fallback** (§7.4, D32): the dropped game's runs leave the block-3 run order, and the other runs keep their order. Rec.: yes. **Confirmed.**
5. **NIST down for 24 h** (§7.3, D15): the drand fallback is used only after the researcher decides so in `results/decisions.md`. Rec.: yes. **Confirmed.**
6. **Notes sentence and W** (§2.1, D5): the notes sentence does not count toward W, so a notes cell and its partner drop the same turns. Rec.: yes. **Confirmed.**
7. **Lookup counting** (§2.5, D3): "no such record" uses up one of the 3 lookups; a second over-cap lookup at the same step is invalid and scores 0. Rec.: yes. **Confirmed.**
8. **sol's optional replay pairs** (§4.6, D36): the exploratory W/Σ replay pairs on sol use the D11 cells, not all 8 task cells. Rec.: yes. **Confirmed.**
9. **Who gets phase 1a's money first** (§4.2, §4.6): luna's 4 replay-off cells and controls, then sol's T_d under the §4.2 rule, and luna's exploratory replay-on cells (which run only if luna's toggle passes G0) only from what is left. At 1k output tokens per call and the simulated variance, no affordable T_d reaches the 0.80 target within $500, so this order gives sol T_d = 150 ($481.34) and no replay-on cells; putting the replay-on cells first would give T_d = 120 ($494.18). Rec.: yes. **Confirmed.**
10. **Controls and the repeat** (§2.9, §4.6, D7): the restated-at-need and single-turn controls also get repeat 1 on seeds divisible by 10. Rec.: yes, as priced (about $1.70). **Confirmed.**
11. **How the guard counts spend** (§12): at the billed estimate, the basis of every cap and forecast here (PR #19). Rec.: merge #19 before the freeze. **Confirmed;** #19 was merged on 2026-10-01.
12. **Where the $120 run guard is set, and what a run that reaches it does** (§7.7, D22; §12). As drafted: the ARC launcher sets the guard at run time and records it in each run's `meta.json`; the frozen config hashes do not cover it. A consequence: every counted run needs $120 of room in its block's `max_usd` and under the 1b cap when it starts, so once phase 1b spend passes $780 the next counted run is refused and the stop-and-ask rule applies, even when the forecast fits (G0's billed headroom is $88.14; §12). Rec.: keep it there, with no patch 0018. **Changed by the researcher:**
    - The guard stays where it is, and the $120-of-room rule stays: a counted run needs $120 of room under its block's `max_usd` and under the 1b cap when it starts; otherwise it does not start, and Claude stops and asks the researcher.
    - Spending approvals stay per block. Block 2 is the 8 counted seed-1 runs; block 3 is approved as two blocks (line 15).
    - **Hold.** Any paid run that reaches its $120 run guard (D22: every counted ARC run has one, S0+StateCarry included) ends `COST_CAP`, final as D22 decided, and places a hold. While the hold stands, no further paid run starts in either stream (line 15). Only the researcher clears it, with a line naming that run, merged into `results/decisions.md`. The grammar of that line is defined in the code that adds the hold (for example `cleared_hold: <run_id>`). That code lands as a $0 pull request before block 2.
13. **Optional S3** (§7.1): it has no frozen profile, so it runs only if an amendment first adds and freezes one. Rec.: yes. **Confirmed.**
14. **PersistGym launcher** (§12): as drafted, unlike the ARC launcher, it neither took the paid-run lock nor checked that PREREG.md is frozen. Rec.: add both before block 1; until then the one-run-at-a-time rule is kept by hand. **Confirmed.** Done by PR #24, merged before the freeze: the PersistGym launcher (`harnesses/cli.py`) takes the shared paid-run lock, refuses unless this checkout's `costs.csv` holds the last paid run's row, and requires PREREG.md to be frozen and the same blob in `HEAD` as on `origin/main`, with the same shared checks as the ARC launcher (`common.approval.require_paid_run`; §12). Under line 15, its lock becomes the PersistGym stream's own lock once the per-stream locks land.
15. **One paid run at a time vs D18's 72 h window** (§12, §7.4). As drafted: back to back, block 3's 24 ARC runs take about 60-79 h at the path games' published durations (§12), so the last one may start more than 72 h after the first, and the PersistGym main sweep cannot overlap them either. Rec.: one run at a time in blocks 1 and 2; before block 3, change the launchers so that paid runs can overlap, each holding its planned spend against the block and phase caps while it runs, and keep D18 as decided. The alternative: keep one run at a time and replace the 72 h window with "back to back in the SEED + 3 order". **Changed by the researcher:**
    - **ARC runs** go back to back, one at a time, in the SEED + 3 order. This replaces D18's "All block-3 runs start within 72 h of each other"; the rest of D18, both run orders included, is unchanged.
    - **PersistGym runs** go one at a time, but a run may play up to 16 episodes in parallel. This changes no payload and no cost. The run reserves spend for the episodes in flight, so it never exceeds its planned spend.
    - **Two streams.** The ARC stream (Gemini) and the PersistGym stream (OpenAI) may run at the same time, each with its own paid-run lock and its own approval blocks. Block 3 is approved as two blocks: `3-arc` (the 24 ARC path runs) and `3-persistgym` (the PersistGym main sweep).
    - The code for the per-stream locks and the parallel episodes lands as $0 pull requests before block 3, and the hold's code (line 12) before block 2. Until the per-stream locks land, one paid run at a time overall.
16. **Where an error re-run goes in the back-to-back order** (§7.5, D19; line 15): the re-run starts right after the run it replaces, before the next run in the block's order (SEED + 2 in block 2, SEED + 3 in block 3); the rest of the order is unchanged. Rec.: yes. **Added by Claude after the researcher's answers, to settle a point the reviews found open; confirmed by the researcher's merge of PR #4.**

### 0.4 Freeze procedure
1. **Before the freeze** (PLAN §16.3):
   - the operational slice of the free ARC analysis is done (§7.8): done;
   - the pull requests this text relies on are merged by the researcher: #18 (A2; it also sets `PHASE_CAPS` in `common/costs.py` to the caps of §12), #21 (patch 0017, config freeze record, ARC launcher), #19 (billed spend basis; PREREG.md must match `origin/main`), #20 (test timeout, housekeeping). Then `origin/main` is merged into this branch, and the "open"/"until merged" notes in §0.1, §7.1 and §12 are updated: done on 2026-10-01 (merged in the order #20, #18, #21, #19; merge commits in the table below; `origin/main` at `2b0a958` merged into this branch);
   - the pull requests that bring the code in line with the signed-off text are merged by the researcher before PR #4, in this order: #22 (D13: `max_output_tokens` 32,000 on every OpenAI step, summary and probe request, and `incomplete` responses; §6), #25 (D39: the withheld control's stand-in bindings, generator 0.3.0; §4.3), #24 (the PersistGym launcher takes the paid-run lock, checks the ledger and requires a frozen PREREG; §12) and #23 (the ARC launcher checks `arc/config_freeze.json` and `arc/patches` against `origin/main` and the §7.1 tables; §7.1, §12; it contains #24). This file already describes the code as it stands once all four are merged. Their merge commits do not exist when this text is written, so they are recorded in `results/decisions.md` after the merges, not in this file;
   - the ARC config freeze record (§7.1) is filled: done, from PR #21.
2. The researcher confirms each line of §0.3 (or changes it) and checks that each decided text below says what was decided: answered on 2026-10-01 (§0.3). A changed line is written into the text by Claude in its own commit ("m0: PREREG sign-off answers"), which the researcher checks before merging (step 4).
3. Claude makes one final commit on this branch, which changes only: the version line to `Version: 1.0`; the status line to `**Status: Frozen on <date> by <researcher> (sign-off in PR #4).**`; and the sign-off table below. The draw script (§7.3) and both paid launchers (§12; the PersistGym launcher since PR #24) refuse unless the version is a release version of at least 0.2 (no `-draft` suffix) and the status line starts with "Frozen" (one rule for all three, `common/prereg.py`).
4. The researcher merges the pull request (PR #4). Its merge commit on `main` is the **freeze commit**. It is recorded in `results/decisions.md`; it cannot be written into this file.
5. The game draw (§7.3) runs once, for the freeze commit, no earlier than 10 minutes after it: `uv run python -m arc.draw_games <freeze-commit-sha>`. Before then it exits with code 3 and is re-run later. Its output goes to `results/draw/<run_id>/` and `results/decisions.md`.
6. Only then, and only once the payload snapshot tests pass (PLAN §6, §16.2; CLAUDE.md), may the block-1 pilots (paid) be requested (PLAN §16.2), through the researcher's approval line (§12). Run metadata records the PREREG version string; a paid run under a `-draft` version is a protocol violation.

| Sign-off field | Value |
|---|---|
| Frozen by | Raimondas Lencevicius |
| Date | 2026-10-01 (the researcher's local date, UTC−4; the freeze commit's UTC time is recorded with its SHA in `results/decisions.md`) |
| Freeze commit | The merge of PR #4 into `main`; its SHA is recorded in `results/decisions.md` after the merge (step 4) |
| D-items resolved (D1-D39) | All 39, decided 2026-10-01 (§16) |
| §0.3 lines confirmed | All 15 answered on 2026-10-01: lines 1-11, 13 and 14 confirmed as recommended; lines 12 and 15 changed by the researcher and written in (§0.3). Line 16 (error re-run position) added by Claude and confirmed by the merge of PR #4 |
| Operational-slice commit used for D14, D16, D21, D22, D27, D28 | `ef251ba` (run `results/arc_public_ops/20261001T035436Z/`); SP80 and TN36 recordings added in run `results/arc_public_ops/20261001T185155Z/` (PR #17) |
| Merge commits of #18 (A2), #21 (ARC freeze), #19 (spend basis), #20 | `9090bca` (#18), `7955f11` (#21), `2b0a958` (#19), `46c61a1` (#20), all on `main` on 2026-10-01 |
| Merge commits of #22 (D13 output cap), #25 (D39 withheld control), #24 (PersistGym lock), #23 (ARC freeze check) | Merged before the freeze, in that order (step 1). Their SHAs are recorded in `results/decisions.md` after the merges; they do not exist when this text is written |
| Spend to date at freeze | $0 (`results/costs.csv` has no rows at this commit) |

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
2. PREREG freeze, then the beacon-seeded draw (§7.3), which orders the 4 fixed path games.
3. Block 1, pilots (§11), then gate G0 (§10.1).
4. Block 2, seed-1 S0+S4 (8 counted runs), then Checkpoint C (§10.3).
5. Block 3, approved as two blocks: the other 24 ARC runs (`3-arc`) and the PersistGym main sweep (`3-persistgym`), then G2 (§10.4). The PersistGym main sweep starts only after gate G1 (§10.2) has passed and been recorded (PLAN §11).
6. Block 4, phase 2 (StateCarry), with gates G3 and G4 (§8).

Each block needs the researcher's explicit approval (§12).

## 2. Definitions (PLAN §4, §5, §16.5)
> Definitions to fix in `PREREG.md` (these need the researcher's judgment): (PLAN §4)

### 2.1 Episodes, tokens and logged fields
> **One environment family.** Each episode is a sequence of about 20-32 steps.
> - Every environment step is a **new user message** containing an observation, as in ARC's harness, and the agent replies with one action. (PLAN §5)

**Operational.**
- Steps are numbered t = 1..T. The observation at step t is o_t; the agent's reply is a_t.
- **Project tokenizer:** `tiktoken` encoding `o200k_base` (version pinned in `uv.lock`). Every planned distance, the window W, the padding budget v and the survival calculator use it. Provider-reported tokens are logged next to it and are what cost is computed from (PLAN §5: "Use one tokenizer for generation and window accounting, and also log provider-reported tokens"). This encoding is part of D5.
- **`system_tokens`** counts the episode's system prompt **without** the notes sentence. The notes sentence (§5) is never counted toward W, so a notes cell and its no-notes partner (W-n-0 and W-0, Σ-n-r and Σ-0-r) evict and compact at the same steps (PR #15; §0.3, line 6).

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
| `n_lookups`, `lookup_steps`, `n_lookups_unavailable`, `n_lookup_responses` | Lookups served, over-cap lookups, and lookup responses seen in the need payload (§2.5, §2.8) | harness, survival calculator |
| `need_phase` | Need-phase tokens and calls; `need_phase.first_step_call` is `usage[n]` (§3 H1, H2) | harness |
| `compacted_between`, `compactions[].at_step`, `compactions[].at_lookup_result` | Summary timing in Σ cells (§5) | harness |
| `success` | §2.6 | analysis |
| `S_planned`, `S_verbatim`, `S_carried`, `S` | §2.8 | survival calculator, analysis |
| `exit_status` | `ok`, `transport_error`, `echo_mismatch`, ... | harness |
| `cost_usd_list`, `cost_usd_billed_est` | From `usage` and the dated price table | analysis |

For ARC runs: `run_id`, `game_id`, `config_id` (S0, S1, S2, S4, S0+SC), `config_hash`, `fork_commit`, `patch_sha256`, `seed`, `replicate`, `is_rerun`, `rerun_of`, `exit_reason` and `agent_exit_reason` (§7.5), `levels_cleared`, `level_actions[ℓ]`, `rhae` (from ARC's online scorecard), `scorecard_id`, `n_calls`, `n_compactions`, `context_trims`, tokens (input, cached, output, reasoning), `cost_usd_list` (the harness's no-cache accounting), `cost_usd_billed_est`, `service_tier` (requested and served), `wall_clock_s` and `reported_models`.

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

**Decision.** Accept the binding wording, the ban on the value string outside the three exceptions, and the 2 distractor bindings per episode. Generator 0.2.0 (PR #15) implements this:
- the distractor bindings use the target's sentence frame and sit at steps that hold no evidence in any of the 8 task cells, so every cell shows them at the same steps in the same words;
- their values come from the value range and are never an option or a clue value (audit check `distractor_bindings_valid`);
- `lookup` serves distractor keys too (§2.5).

(decided 2026-10-01, D1)

*Why:* without distractor keys the target is the only bound key, so it stands out, and a generic lookup could point only at it. If a distractor value were also an option, the rule that options occur nowhere else (§2.6) would break.

### 2.4 Derived fact
> **Derived fact:** a value computed from 2-3 observations shown at different steps. It is never shown in final form. (PLAN §4)
>
> **Reveal:** [...] Derived: shows one of 2-3 clues plus, at some step, the combining rule. (PLAN §5)

**Operational.**
- The generator sets `fact_kind = derived`. There are m ∈ {2, 3} clue bindings, each in a different observation, plus one **rule binding** that states the combining rule g in words. The rule binding may share an observation with a clue. `fact_value = g(clue_values)`, where g is a plain sum.
- The **evidence set** is all clue bindings plus the rule binding. `evidence_steps` holds their sorted steps.
- "Never shown in final form": the `fact_value` string occurs in no observation, system prompt or filler, except the need-step option list and the restated-at-need control. A lookup in the recoverable variant re-shows the clues and the rule, never the value (PLAN §5).
- **Every clue is needed:** for every proper subset of the clues (with the rule), all K options stay consistent. The oracle checks this by enumeration. An agent that kept only some of the clues is therefore at chance.
- **Clustered options** make this hold with a plain sum. The 10 options are one cluster of consecutive values, with the target at its block-balanced rank. Each addend is drawn, rank-shifted, inside its range, so that with the rule and any proper subset of the clues every option has a completion within the clue ranges.
- Clue values obey the same string rules as an observed value (§2.3). Each one appears only in its own binding, in lookup responses and in the restated control. **Two addends may be equal** (in a small share of three-clue templates; PR #15). Forcing them apart would let an agent that kept the base and one addend rule out an option, which breaks (b) below. `S_carried` then needs that value only once (§2.8).
- m is a template property, assigned from the template seed: exactly 5 templates with m = 2 and 5 with m = 3 in every complete 10-template block (§2.9).

**Decision.** Accept (a) the rule binding as part of the evidence set, (b) the condition that all K options stay consistent under any proper subset of clues, implemented by clustered options, and (c) the exact 5/5 split of m within each 10-template block. Partial memory is a $0 validity gate in every derived task cell (§4.4): the oracle's enumeration must find no template where a proper subset of the clues narrows the options, and each partial-memory heuristic (the base clue plus the rule with a uniform pick; "the smallest option above the base clue") must score ≤ 0.20. (decided 2026-10-01, D2)

*Why:* in generator 0.1.1, keeping only the base clue and the rule narrowed the options to one in 0.45 of templates, and the two heuristics scored 0.69 and 0.23, above the 0.20 no-memory bar; generator 0.2.0 gives 0 narrowing templates and 0.100 on both heuristics (`persistgym/DESIGN.md`, PR #15), and so does 0.3.0, whose template values are unchanged (PR #25). Clustered options remove that without modular rules. A side effect: neighbouring options differ by 1, so an arithmetic slip lands on a wrong option. The per-cell restated-derived rate at G1 shows whether the 85% ceiling still holds.

### 2.5 Recoverable
> **Recoverable:** a `lookup` action re-shows the fact (or its clues) at the cost of one step. (PLAN §4)
>
> **Lookup (recoverable variant only):** `lookup(key)` re-shows the fact, or the clues for derived facts, in the next observation. It costs one step. (PLAN §5)

**Operational.**
- When `recoverable = true`, the action list in the instructions includes a generic `lookup(key)`: "re-show an earlier record". It accepts any key that has appeared in a binding earlier in the episode, distractor keys included. Offering it therefore does not reveal which key will be needed.
- **Matching:** a key matches a binding iff it contains that binding's entity name as a whole word, ignoring case. The key is matched as written, so `key="LINDEN"`, `sample:LINDEN` and `LINDEN's freezer slot` all match LINDEN.
- **Mechanics:** if the agent replies `lookup(key)` at step t, the next user message is a **lookup response**. It contains the same binding(s) verbatim: the fact binding, or every clue binding plus the rule binding. After them comes the unchanged pending task of step t, and the whole message is padded to v tokens. The agent then acts on step t. One lookup therefore adds exactly one user message and one model call. `n_lookups` counts lookups served, "no such record" answers included; over-cap lookups (below) are counted separately in `n_lookups_unavailable`. The scripted steps, the identity of `need_step` and the success scoring do not change.
- Every lookup response carries the marker line `EVENT: LOOKUP RESULT`, and no scripted observation does (the generator checks both). This is how §2.8 leaves lookup responses out.
- A key whose records have not been shown yet answers "no such record": a key that never appears, or the target's key before its reveal. This also costs one step and counts as one of the lookups.
- **Cap:** at most 3 lookups per episode. A 4th answers "lookup unavailable": it costs one step, is not scored, and the pending step is asked again. A second over-cap lookup at the same pending step is an invalid action (§2.6). This keeps every episode finite (§0.3, line 7, with "no such record" above).
- When `recoverable = false`, `lookup` is not in the action list. A `lookup(...)` reply is an invalid action: it scores 0 at the need step, and at a routine step it is logged and the episode continues.

**Decision.** Accept the generic lookup over any earlier key, the lookup response merged with the pending task (one extra step), the cap of 3, and the lenient whole-word match, with "no such record" and "lookup unavailable" as above. (decided 2026-10-01, D3)

*Why:* a generic lookup avoids cueing the target. Strict key matching made near-miss keys cost extra turns that are not about memory, and those turns feed H1's cost outcome. Scoring a 4th lookup as a wrong answer would turn a lookup habit into a success penalty in the recoverable cells (Penalty_R in H1).

### 2.6 Needed, live and success
> **Needed:** the step at which the fact determines the only correct action. "Needed" and "live" come from the generator's dependency graph, never from agent trajectories. (PLAN §4)

**Operational.**
- The generator's dependency graph has one node per scripted step and edges from evidence steps to the need step. `need_step` = n is the unique step whose correct action depends on the target fact. `correct_action` = choose(`fact_value`).
- `options` lists K = 10 distinct values, exactly one of which equals `fact_value`, in the clustered form of §2.4. The distractor options have the same format and, like the value, occur nowhere else in the episode.
- **Live:** the fact is live on steps [min(`evidence_steps`), n]. No other step's correct action depends on it, and the generator checks this on the graph. Routine steps depend only on their own observation (PLAN §5).
- **Success:** `success = 1` iff `action_parsed` at the need step equals `correct_action`. If the agent looks something up at the need step, its first non-lookup action is scored; a lookup refused as invalid (§2.5) is the scored action and scores 0. Unparseable, invalid or missing actions score 0, and so does a step response with status `incomplete`, which is an invalid action at any step (§6, PR #22). Accuracy on routine steps is logged as `routine_acc`, a competence check, not an outcome.
- **Parser** (written by the harness track, frozen with the payload snapshot tests, the same in all cells): the need step accepts either the option's letter or its value. When a reply has no `ACTION:` line, the parser falls back to the last known `verb(arg)` in the reply.

**Decision.** Accept scoring the first non-lookup action and scoring invalid output as 0, plus the two parser rules above (letter or value; fallback to the last `verb(arg)`). (decided 2026-10-01, D4)

*Why:* scoring invalid output as failure keeps every episode in the analysis; the failure labels (§9.7) separate format errors from memory failures afterwards. Both parser rules were already in the generator and are now registered rather than implicit.

### 2.7 Near and far
> **Near / far:** the reveal lies inside / beyond the harness eviction threshold W, in tokens. (PLAN §4)
>
> near = reveal about 4 steps before need; far = reveal beyond W. (PLAN §5)
>
> "Far" defined by observation tokens alone, so eviction does not depend on reply length; survival checked against the payload actually sent. (PLAN §16.5)

**Operational.** Let n = `need_step`, r_first = min(`evidence_steps`), r_last = max(`evidence_steps`), sys = `system_tokens` (§2.1), and O(a, b) = Σ_{t=a..b} `obs_tokens[t]`.
- **Far:** sys + O(r_last, n) > W. Replies only add tokens, and a drop-oldest window keeps a contiguous suffix of turns. So every window cell drops all of the evidence before the need step, whatever the agent writes. In summary cells the payload must exceed W at some step after r_last and no later than n, so the evidence has passed through a summary by the need step (the trigger is defined in §5). The generator places far evidence by observation tokens alone, with a margin, which implies this inequality.
- **Near:** every evidence step lies in [n − 6, n − 1]. An observed fact's reveal sits at n − 4. Derived clues and the rule are spread over [n − 6, n − 1]. In addition, sys + O(r_first, n) + (n − r_first) × R_plan ≤ W, with a planning allowance of R_plan = 1,000 tokens per visible reply. Near evidence is *planned* to survive in window cells. Actual survival is checked on the payload sent (`S_verbatim`, §2.8).
- Near and far are properties of the rendered template, not of the harness. The same episodes run in every harness cell (PLAN §5, fully crossed). In F cells, "far" only places the evidence far back; nothing is evicted.
- **Shared skeleton:** all 8 task-cell renderings of a template share T, `need_step` n, the routine steps and the filler. They differ only in where the evidence bindings sit, in the bindings themselves (observed vs derived), and in whether `lookup` is offered. Near and far renderings therefore have the same length, which H1's token reading relies on (§3 H1, D8).

**Decision.** Accept the far inequality, the near window [n − 6, n − 1] with R_plan = 1,000, the shared skeleton (same T and n in all 8 task cells of a template), and `o200k_base` as the project tokenizer. The survival calculator and the harness both count sys toward W (`window_counts_system_prompt = true`), without the notes sentence. (decided 2026-10-01, D5)

*Why:* counting sys in both places stops W from being counted two ways. Near cells tolerate visible replies far longer than R_plan, so R_plan = 1,000 is safe. W is defined in project tokens, so a mismatch with the providers' tokenizers affects only cost estimates.

### 2.8 Survives (S), carried and rescued
> **Survives (S):** whether the fact (or all its clues) is still in the context the harness sends at the need step. Computed from token positions for window harnesses. Measured by string match for summary and notes, since those depend on what the model writes. (PLAN §4)

**Operational.** All quantities use `payload[n]`, the **first** request at the need step, sent before any lookup response.
- **`S_planned`** (computed before running, by the survival calculator): 1 in F cells. In window cells it is 1 for near and 0 for far, by §2.7, from `obs_tokens`, `system_tokens` and W. In summary cells it is 0 for far and left unset for near, because whether a summary fires between the evidence and the need step depends on reply lengths (§5).
- **`S_verbatim`** = 1 iff every string in `evidence_spans` occurs in a user message of `payload[n]`, excluding the need observation itself and any lookup response. Lookup responses are recognised by their `EVENT: LOOKUP RESULT` marker (§2.5). So a lookup taken before the need step cannot make evicted evidence count as surviving.
- **`S_carried`** (cells with notes or summaries, when `S_verbatim` = 0) = 1 iff text the model wrote and that is still in `payload[n]` contains the right string as a whole-word match. That text is the summary bridge message plus the retained assistant replies. The match uses the regex `(?<![0-9A-Za-z])VALUE(?![0-9A-Za-z])`. For an observed fact the string is `fact_value`. For a derived fact it is `fact_value`, or else every value in `clue_values` (an addend that occurs twice is needed once; the rule is not required). Lookup responses and the need observation are excluded.
- **`S`** = `S_verbatim` OR `S_carried`.
- **Window accounting ignores replayed reasoning.** W counts project-tokenizer tokens of the system prompt (without the notes sentence), the observations and the visible replies only. In replay cells, reasoning items travel with the turns they belong to and are dropped with them. This keeps W-n-r and W-n-0 on the same eviction rule, and it matches the identical-payload replay toggle (§6).
- **Accounting check.** Two kinds of mismatch are kept apart, because only one of them is a bug.
  - *Bugs:* in window cells, `S_verbatim` must equal the survival recomputed by replaying the drop-oldest rule on the project-token counts of the turns actually sent. In window cells at far distance, `S_verbatim` = 1 is impossible by §2.7. Any episode that breaks either condition is a window-accounting bug, and analysis stops until it is found.
  - *Expected near losses:* in near window cells, `S_planned` = 1 but `S_verbatim` = 0 can happen without a bug, when visible replies longer than R_plan or lookup responses push the evidence out. These episodes are counted per cell, reported, and analysed by their assigned cell (§13). If they exceed 2% of any near window cell in the block-1 pilots (pooled tokens only, §11), R_plan or W is re-tuned under §4.2 before the main sweep.
- **Carried, used, rescued** (PLAN §5, §10): among episodes with `S_verbatim` = 0, P(carried) = mean `S_carried`; P(used | carried) = mean `success` where `S_carried` = 1; P(rescued | not carried) = mean `success` where `S_carried` = 0, split by whether a lookup was taken. Chance is 0.10. Episodes with `S_verbatim` = 1 give the residual at S = 1.

**Decision.** Accept whole-word string matching on the value or all clues (rule not required), the exclusion of replayed reasoning from W, the bug stop, and the 2% pilot re-tuning trigger for expected near losses. The generator's older carried matcher (a 200-character window around the entity name) is replaced by the regex above. (decided 2026-10-01, D6)

*Why:* with clustered options (§2.4), partial carry is worth nothing, so no "base clue only" category is needed. String match misses paraphrased carry, so P(carried) is a lower bound.

### 2.9 Templates, repeats and seeds
> **Templates.** A template is one sampled skeleton: surface story, fact values, filler. Each template is rendered into **all 8 task cells and all harness cells** (fully crossed). All contrasts are therefore within-template, and template fixed effects absorb difficulty. Add templates rather than seeds: run 1 repeat per template × cell, and 2 repeats on a 10% subset to estimate within-template noise. (PLAN §5)
>
> Pilot templates use a disjoint seed range. (PLAN §16.5)

**Operational.**
- `template_seed` ranges never overlap: main [0, 50,000), taken in order from 0; validity and the G1 spot-check [50,000, 60,000); pilots [90,000, 100,000). $0 checks may use any range. The generator refuses indices outside a range.
- **Balance blocks:** the generator balances option letter, target rank and (for derived facts) m within each block of 10 consecutive seeds, counted from the range start. Template counts are therefore multiples of 10, so every block is complete. On sol this holds for both T_d and T_o = T_d / 3, because T_d is a multiple of 30 (§4.2).
- **Repeats:** main templates whose seed is divisible by 10 also get `repeat_index` = 1, on **both** luna and sol, controls included (§0.3, line 10). Primary analyses use `repeat_index` = 0 only. Repeat 1 is used only to estimate within-template noise.
- Provider sampling is not seeded. Repeats measure that noise.

**Decision.** Seed ranges main [0, 50,000) from 0 in complete 10-template blocks, validity [50,000, 60,000), pilots [90,000, 100,000); the 10% repeat subset (PLAN §5) on both luna and sol; primary analyses on repeat 0 only. The proposal to drop the repeat subset on sol was rejected. (decided 2026-10-01, D7)

*Why:* starting at 0 keeps the generator's balance blocks whole. Keeping sol's repeats costs about $24.85 at the central sol size (T_d = 120, 1k output tokens per call; `results/cost_model/20261001T203318Z/optA_sizing_1a.csv`), and they are the only estimate of within-template noise on sol.

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
- **Tokens prediction (primary reading, need phase):** let N(h, d) be the mean, over observed-R episodes in harness h at distance d, of `need_phase.tokens`: provider-reported input tokens (cached included) plus output tokens (reasoning included), summed over every call from the first call at the need step through the call that returns the scored action, lookup round-trips included. The prediction is met iff R_need = [N(W-0, far) / N(F-0, far)] / [N(W-0, near) / N(F-0, near)] ≥ 1.30 (point estimate).
- **Secondary token readings, reported next to it:** R_tok, the same ratio on mean provider-reported total tokens per episode, T(h, d); and the literal ratio T(W-0, far) / T(F-0, far).
- **Kill** (as written): Δ_H1 < 10pp (point estimate) **and** the upper bound of its 90% CI < 15pp.

**Decision.** Need-phase tokens (R_need) are the primary reading of "total tokens rise by at least 30%"; R_tok and the literal ratio are secondary and reported; the zero-lookup rule is kept. (decided 2026-10-01, D8)

*Why:* the literal ratio cannot reach 1.30, because the window caps W-0's input below F-0's even when W-0 looks things up (PR #7 review). A difference-in-differences of episode totals removes the cap but not the denominator problem: an episode makes about 28 calls (PLAN §12), so each lookup adds only about one call in 28, and an episode total can rise by only a few percent per lookup within the 3-lookup cap. This is stated before any data. Need-phase tokens cancel the window cap through the near/far ratio and follow the extra calls at the need step, so 1.30 is reachable. R_need is therefore driven largely by the same behaviour as the lookups prediction. This reinterprets PLAN's "total tokens".

### H2: reasoning replay carries derived state
> Model: gpt-6.1-sol, plus gpt-6-luna if the M0 pilot shows it honours `all_turns`. Arms: full history, `reasoning.context` = `all_turns` (F-r) vs `current_turn` (F-0).
>
> **Predictions:**
> - Less than 3pp difference on observed facts.
> - On derived facts at far distance: at least 8pp more success with replay, or, if success does not move, at least 25% more reasoning tokens in the no-replay arm (the model re-derives what it no longer sees).
>
> **Falsified** if the derived-fact success effect is under 3pp *and* the token effect is under 10%. **Equivalence** (treated as "no effect"): the 90% CI of the success effect lies inside ±8pp *and* the token effect is under 10%. (PLAN §4)

**Operational.**
- The **primary** model is gpt-6.1-sol. Cells F-r vs F-0 on the D11 task cells: derived × far × {R, NR} for T_d templates and observed × far × {R, NR} for the first T_o of them, with no near cells (§4.2). If luna passes the G0 toggle check (§10.1), its H2 run is reported as a replication outside the Holm family.
- **Echo:** any episode in which some response's `reasoning_context_echoed` differs from the requested value is excluded (CLAUDE.md). If more than 5% of a cell's episodes are excluded, the run stops and the researcher is told. [Amended 2026-10-02, see §17.2]
- **Observed facts:** Δ_obs = p(F-r) − p(F-0), pooled over the 2 observed-far task cells run on sol. Prediction: |Δ_obs| < 3pp (point estimate), reported with its 90% CI.
- **Derived, far:** Δ_der = p(F-r) − p(F-0), pooled over derived × far × {R, NR}. Prediction: Δ_der ≥ 8pp.
- **Token effect:** TE = (mean need-step reasoning tokens in F-0) / (mean need-step reasoning tokens in F-r) − 1, over derived-far episodes, using the reasoning tokens of `need_phase.first_step_call` (`usage[n]`, the need step's first call). TE is a ratio of means with template-cluster bootstrap intervals (§9.1). The log-link model of §9.5 gives the model-based estimate, which must agree in sign (D26). Prediction (the alternative branch): TE ≥ 25%. Total reasoning tokens per episode are reported as a secondary measure.
- **Falsified:** Δ_der < 3pp **and** TE < 10%, both as point estimates.
- **Equivalence:** the 90% CI of Δ_der lies inside (−8pp, +8pp) **and** TE < 10% (point estimate).
- **"Signal"** for running the W/Σ replay pairs (PLAN §7: "The W/Σ replay pairs run only if H2 shows signal") means H2 is not falsified: Δ_der ≥ 3pp or TE ≥ 10%.

**Decision.** Need-step reasoning tokens are the primary token measure; "under 3pp" and "under 10%" are judged on point estimates; Δ_der pools over recoverability; sol is the only confirmatory model; "signal" means not falsified. Under D11, Δ_obs pools the 2 observed-far cells only, which narrows the observed-fact prediction to far distance. (decided 2026-10-01, D9)

*Why:* need-step reasoning targets the re-derivation step. An episode total would mix in any global "thinks less with replay" effect; on ARC, reasoning per call differs about fivefold between the harnesses (25,707 vs 4,726 reasoning tokens per action, token-weighted, over 8 recorded games; `results/arc_public_ops/20261001T035436Z/summary.md`). With observed-far cells on T_o = T_d/3 templates, the observed check is weak: with no true difference, |Δ_obs| < 3pp holds in only 0.35-0.39 of simulated runs at T_d = 120, with a 90% CI half-width of 9.4-11.4pp (`results/power_sim/20261001T190327Z/h2_sol_power.csv`). So Δ_obs is reported with its CI.

### H3: little residual cost of multi-turn structure when the fact survives
> Comparison: at S=1, far distance, multi-turn full history vs the position-matched single-turn control. The control has the same tokens and the fact at the same offset, but in one prompt.
>
> **Prediction:** the difference is at most 5pp. We report it either way. It bounds how much of any effect is "needle-in-a-haystack" retrieval rather than state persistence. (PLAN §4)

**Operational.**
- Model gpt-6-luna (PLAN §7 lists H3 among luna's high-N runs). The multi-turn arm is F-0 in the far, not-recoverable cells, observed and derived pooled. S = 1 there by construction.
- **Control construction:** the system prompt is unchanged. One user message holds o_1..o_n in order. Each observation is followed by the oracle's correct routine action, written as a plain "Agent: ..." line, and the message ends with the need-step question. The evidence sits at the same observation-token offset from the need question as in the multi-turn episode. Reply tokens differ, because the control uses oracle-length replies.
- **Δ_H3** = p(single-turn control) − p(F-0, multi-turn). The prediction holds iff the upper bound of the 90% CI of Δ_H3 is ≤ 5pp, i.e. one-sided non-inferiority at α = 0.05. The result is reported either way.

**Decision.** Accept the NR-only scope, oracle routine replies in the control, F-0 as the multi-turn arm, and the one-sided reading. (decided 2026-10-01, D10)

*Why:* a single prompt cannot serve a lookup, so single-turn controls exist only for non-recoverable cells (the generator refuses the others). Oracle replies make the control independent of any model run, at the cost of slightly shorter evidence-to-need gaps than real replies, which favours the control a little.

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
- A **unit** u = (game, replicate) over the 4 path games of §7.2; there are 8. For config c, R̄_c is the mean RHAE over the 8 units.
- **Gap** G = R̄_S4 − R̄_S0. Step shares: σ_loss = (R̄_S1 − R̄_S0)/G, σ_notes = (R̄_S2 − R̄_S1)/G, σ_replay = (R̄_S4 − R̄_S2)/G. They sum to 1.
- **Prediction A holds** iff σ_loss ≥ 1/3 **and** σ_replay ≤ 1/2 **and** −0.10 ≤ σ_notes ≤ 0.10 (point estimates). **Prediction B holds** iff σ_replay ≥ 1/2. The report says which hold: both (possible only at exactly 1/2), one, or neither.
- **Intervals:** 10,000 bootstrap resamples of the 8 units, with replacement, keeping a unit's four configs together; percentile 90% intervals. The fraction of resamples with G ≤ 0 is also reported. Descriptive only.
- Shares are reported only if G ≥ 10 RHAE. Otherwise kill criterion 4 fires (§10.4), and the table reports levels and RHAE without shares.
- **Optional S3** (PLAN §8.2), if run, is exploratory and stays out of the shares.
- **Sensitivity analyses:** scoring the original errored runs instead of their re-runs (§7.5); excluding units that contain a `COST_CAP` ending (§7.7). (The v0.1 sensitivity analysis without games whose published Standard run ended early is dropped: under D14 no path game has such an ending.)

**Decision.** Judge Predictions A and B on point estimates, with the bootstrap intervals shown next to them, and withhold the shares when G < 10 RHAE. (decided 2026-10-01, D34)

*Why:* point estimates fit "descriptive" and "no significance claims" with 8 units. When G is small, each share's denominator is near 0, so shares can take any size or sign; kill criterion 4 fires at G < 10 anyway.

### H5: the Adapter advantage grows with level depth
> The Adapter's advantage in P(clear level ℓ | reached ℓ) is larger at levels ≥4 than at levels 1-2.
> - Tested first on ARC's published public-set runs (free; §8.1).
> - Then on our runs. (PLAN §4)

**Operational.**
- One observation per (run, level ℓ). **Reached(ℓ)**: the run took at least one action on ℓ (`level_actions[ℓ]` > 0). **Cleared(ℓ)**: the run completed ℓ. Analysis is conditional on reached.
- Depth bands: early = levels 1-2, deep = levels ≥ 4. Level 3 is reported but left out of the contrast.
- **Model** (PLAN §10): logistic regression, cleared ~ harness × band + game fixed effects, among reached levels. A_b is the Adapter-minus-Standard difference in P(clear | reached) in band b, on the probability scale (average marginal effect).
- **H5 contrast:** A_deep − A_early > 0 (point estimate), with a 90% interval from a game-cluster bootstrap (10,000 resamples). Descriptive, like H4 (PLAN §10).
- **Data:** (a) the published Gemini 3.8 Flash high-effort public-set runs, one per game and harness, 25 games, analysed in the hypothesis slice *after* the freeze commit (PLAN §16.3). Other efforts and models are exploratory. (b) Our runs, S0 vs S4 on the 4 path games.
- **Sensitivity:** drop levels at which a run ended by an (inferred) error rather than by budget.
- **Not a blind test on the published runs.** Per-game scores for both harnesses (`docs/background.md` §4) and at least one per-level ending (LP85, PLAN §16.4) were seen before this draft. The operational slice also inferred where each published run ended, which reveals the last level each run reached. H5 on published runs is therefore a pre-specified analysis of partly seen data. Only H5 on our own runs is a test on unseen data.

**Decision.** Reached = at least one action on ℓ; two bands (1-2 and ≥ 4) with level 3 left out of the contrast; the probability-scale average marginal effect with a game-cluster bootstrap; high effort as the only registered published-data analysis. (decided 2026-10-01, D35)

*Why:* the bands follow H5's own wording, and high effort matches H4 and the path study. "At least one action" avoids counting a run that ended right after clearing ℓ − 1 as a failure to clear ℓ. Per-level data exist in the slice's `per_run.csv` but were not tabulated by harness, so the hypothesis slice stays after the freeze.

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
  - **luna:** about 100 templates per cell (PLAN §7). The count is the smallest multiple of 10 with simulated power ≥ 0.80 both for Δ_H1 = 10pp (H1) and for H3's 5pp non-inferiority bound when the true Δ_H3 = 0, within the phase-1a cap.
  - **sol design:** F-r vs F-0 on the 2 derived-far task cells for T_d templates, and on the 2 observed-far task cells for the first T_o = T_d / 3 of them. There are no near cells on sol. T_d is always a multiple of 30, so T_o is a multiple of 10 and every balance block is whole (D7). The central case is T_d = 120 and T_o = 40: 640 episodes, plus 64 repeat episodes (§2.9), 704 in all.
  - **sol count:** T_d is the smallest such value with probability ≥ 0.80 that the 90% CI of Δ_der lies inside ±8pp when the true Δ_der = 0, within the phase-1a cap.
  - **sol ceiling: T_d ≤ 210** (T_o = 70). T_d may be raised above the central 120 only before the sol main sweep starts and before any H2 outcome has been computed. It never changes after that. A T_d that the 1a cap in force ($500, §12) does not afford also needs the researcher to raise the 1a cap first.
  - **Order within the 1a cap** (§0.3, line 9): T_d is sized after luna's 4 replay-off cells and its controls; luna's replay-on cells (§4.6) run only from what is left. At the simulated variance this already binds at 1k output tokens per call, because no affordable T_d reaches 0.80.
- If the cap does not allow 0.80, the largest affordable count is used and the achieved power is stated in the results. A sol result that is neither equivalent nor falsified is then reported as **inconclusive**, not as "no effect".
- T_d and T_o are recorded in `results/decisions.md` before the sol main sweep starts (§17: a value set by a pre-registered rule, not an amendment).

**Decision.** [Amended 2026-10-02, see §17.2] Keep the 0.80 power target and the "largest affordable count, else inconclusive" rule. Run sol on derived-far cells for T_d templates plus observed-far cells for T_o = T_d/3 of them, with no near cells; the central T_d is 120, and T_d may be raised, in multiples of 30, up to 210 only as stated above. (decided 2026-10-01, D11; the ceiling of 210 is the researcher's follow-up to A2 the same day, replacing 200)

*Why:* Δ_der and TE use only the derived-far cells. The derived-near cells feed no H2 quantity, and the observed-near cells feed only Δ_obs. The same number of episodes therefore buys much more power for Δ_der. In the committed simulation (`results/power_sim/20261001T190327Z/h2_sol_power.csv`: template SD 1.0 on the logit scale, 1,000 replications, success under F-0 of 0.8 or 0.6):

| T_d (T_o) | 90 (30) | 120 (40) | 150 (50) | 180 (60) | 210 (70) |
|---|---|---|---|---|---|
| One-sided bootstrap test at α = 0.0125, true +8pp, p_F0 = 0.8 | 0.463 | 0.606 | 0.695 | 0.799 | 0.870 |
| Same, p_F0 = 0.6 | 0.308 | 0.414 | 0.489 | 0.537 | 0.645 |
| TOST equivalence at ±8pp, true 0, p_F0 = 0.8 | 0.348 | 0.539 | 0.655 | 0.764 | 0.866 |
| Same, p_F0 = 0.6 | 0.074 | 0.278 | 0.378 | 0.542 | 0.675 |
| Phase 1a forecast, 8 luna cells (USD) | 425.85 | 494.18 | 562.51 | 630.83 | 699.16 |
| of which sol's repeat subset (USD) | 18.63 | 24.85 | 31.06 | 37.27 | 43.48 |
| Phase 1a forecast, luna's 4 replay-off cells only (USD) | 344.69 | 413.02 | 481.34 | 549.67 | 617.99 |

The test's size at a true 0 is 0.010-0.018, and its false-equivalence rate at a true +8pp is 0.028-0.063. α = 0.0125 is the worst step of the Holm family (§9.4). Every column is an allowed T_d; 210 is the ceiling. So the 0.80 TOST target is out of reach at the central size, and an H2 result may be inconclusive. Costs: this design departs from PLAN §5 and §7 ("fully crossed", "all 8 task cells") for sol, and it narrows H2's observed-fact prediction to far distance (§3 H2).

The cost rows are billed forecasts at 1k output tokens per call, with luna's controls per D36 and the D7 repeats on luna and sol (`results/cost_model/20261001T203318Z/optA_sizing_1a.csv`). "8 luna cells" means all 8 harness cells of §5 on luna, the replay-on cells included; the replay-off cells are F-0, W-n-0, Σ-n-0 and W-0. Against the $500 cap, the largest T_d that fits is: with 8 luna cells, 120 at 1k output tokens per call and none at 2k or 3k; with luna's 4 replay-off cells, 150 at 1k, 90 at 2k and none at 3k (`option_a_summary.md` in the same run). These are forecasts; the block-1 pilots measure tokens per call before block 3 is approved.

### 4.3 Controls (as written)
> **Controls, on the same templates:**
> - **Position-matched single-turn:** the same token sequence flattened into one prompt, with the fact at the same offset. Used for H3.
> - **Restated-at-need:** the fact is repeated in the need-step observation. This is the ceiling with memory taken out of the problem. (PLAN §5)

**Operational.** The single-turn control is built as in §3 H3, for the 4 non-recoverable task cells only. Restated-at-need appends the evidence bindings verbatim to the need observation (for a derived fact, the clue and rule bindings, not the value); it runs as full F-0 episodes on all 8 task cells. The **fact-withheld** control used by the validity gate replaces every evidence binding with a distractor binding of equal token length.

**As implemented** (generator 0.3.0, PR #25). The fact-withheld control replaces every **fact and clue binding** with a binding of equal token length for a **stand-in entity**, in the same sentence frame and at the same step: an observed fact's binding becomes the same sentence about the stand-in, with the stand-in's own value, and each clue binding of a derived fact becomes the same clue about the stand-in, with the stand-in's own clue value.
- The stand-in is another entity of the episode's skin whose name has the target's token length. It is never one of the episode's distractor keys (§2.3), and its name never contains the target's name or is contained in it.
- The stand-in's value, and for a derived fact its clue values (which sum to that value), are never an option, a clue value of the target or a distractor value.
- So each stand-in binding has the token length of the binding it replaces, every observation keeps its base observation's token count (exactly v) and log filler, and the withheld episode differs from the base episode of its task cell only inside these bindings. No scripted observation before the need step names the target, and a `lookup` of the target's key answers "no such record" (§2.5).
- The **rule sentence** of a derived fact, which states the combining rule and names no entity, is **kept verbatim** where the base episode shows it. So the code reads "every evidence binding" above as every fact and clue binding: the rule binding, which is part of the evidence set (§2.4), is not replaced.

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
- **Partial memory** (derived cells, D2): the base clue plus the rule with a uniform pick over the options it leaves; the smallest option above the base clue. In addition, the oracle's enumeration must find no template where a proper subset of the clues narrows the options.

A literal "last-seen" or "most frequent in the episode" heuristic on the normal rendering is not a no-memory baseline here: under §2.3 the target is the only option string that occurs before the option list, so such a heuristic recalls the fact and would score near 100% on observed cells. That is why it runs on the fact-withheld rendering, where any option string found before the list is a leak.

**Decision.** Restated-at-need for a derived fact restates the clues and the rule, not the value; the fact-withheld control uses equal-length distractor bindings; validity runs use F-0; the 85% and 20% LLM thresholds apply to the rate pooled over the 8 task cells; the heuristic baselines above, including D2's partial-memory heuristics, apply per task cell. (decided 2026-10-01, D39)

*Why:* restating the clues keeps the derivation in the ceiling, which is the right ceiling for derived cells. Block balance pins the position and frequency baselines at exactly 0.10, so only the paid withheld run and the researcher's spot-check can detect a model's prior over values.

**As implemented** (PR #25, generator 0.3.0). The equal-length bindings of the fact-withheld control are bindings for a stand-in entity that replace each fact and clue binding, as stated in §4.3. The stand-in is not one of the episode's 2 distractor keys (§2.3), its values are never an option, a clue value of the target or a distractor value, and the rule sentence, which names no entity, is kept verbatim.

### 4.5 Survival calculator (as written)
> For every harness × task cell, it computes S from token positions *before* running:
> - For window harnesses, S is mechanical, so the window effect at S=0 is not itself a finding.
> - The estimands are the non-mechanical parts: the rescue rate P(success | S=0), via notes, lookup or re-derivation; the residual at S=1; the value of replay for derived state.
> - For summary and notes cells, log whether the fact or clues appear in the summary or retained notes. This gives an accounting of P(carried), P(used | carried) and P(rescued | not carried). (PLAN §5)

### 4.6 Run matrix (PLAN §7, §12, §16.1)
> Core: F-r vs F-0 on all 8 task cells. The W/Σ replay pairs run only if H2 shows signal. (PLAN §7)
>
> Phase 1a stays under $450 by sizing (30 sol templates; luna's 4 replay-off cells first). (PLAN §16.1)

**Operational.** Which harness cells run on which model in the main sweep. luna rows use all 8 task cells and the template count set by §4.2. sol rows use the D11 cells (§4.2), not all 8; this replaces PLAN §7's "Core: F-r vs F-0 on all 8 task cells". The phase-1a cap in force ($500, A2) bounds the sizes (§12); the "$450" in the quote above is the cap before A2. Within the 1a cap, the confirmatory rows (luna's replay-off cells with their controls, then sol's H2 core) come before the exploratory rows (§4.2; §0.3, line 9).

| Model | Harness cells | Controls | Status |
|---|---|---|---|
| gpt-6-luna | F-0, W-n-0, Σ-n-0, W-0, run first | Restated-at-need on all 8 task cells, as full F-0 episodes; position-matched single-turn on the 4 non-recoverable task cells | Confirmatory for H1 and H3; the rest is accounting (§2.8) and cost outcomes (§9.5) |
| gpt-6-luna | F-r, W-n-r, Σ-n-r | none | Only if luna's toggle is verified at G0 (D29) and the phase-1a cap allows. Exploratory (§9.10) |
| gpt-6.1-sol | F-r, F-0 on the D11 cells | none | H2 core, confirmatory |
| gpt-6.1-sol | W-n-r vs W-n-0, Σ-n-r vs Σ-n-0, on the D11 cells (§0.3, line 8) | none | Only if H2 shows "signal" (§3 H2) and the phase-1a cap allows. Exploratory |
| either | Σ-0-r (optional) | none | Only on a verified toggle and if the cap allows. Exploratory |

Validity runs (§4.4) use F-0 on each model that runs a main sweep. The sol H1 replication is not in the MVP (PLAN §4 [A1]).

**How the main sweep runs** (§0.3, line 15, changed by the researcher on 2026-10-01; line 9 confirmed). The main sweep is approved as its own block, `3-persistgym`, apart from the ARC block `3-arc` (§12). Its runs go one at a time, and a run may play up to 16 episodes in parallel. Parallel play changes no payload, cell assignment or cost; the run reserves spend for the episodes in flight, so it never exceeds its planned spend. Once the per-stream locks have landed (before block 3), the main sweep may run while ARC runs are going. Within the block, the order of line 9 decides what gives way when the 1a cap runs short.

**Decision.** This run matrix, with the two changed rows: restated-at-need on all 8 task cells as full F-0 episodes on luna, the single-turn control on the 4 non-recoverable task cells only, and sol's F-r vs F-0 on the D11 cells. (decided 2026-10-01, D36)

*Why:* fixing the matrix now stops cells being added or dropped after results are seen. The generator cannot build single-turn controls for recoverable cells, and restated-at-need needs a stated harness cell.

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
- **Window (W) cells:** before each call, drop the oldest (user, assistant) pair until sys + observation tokens + visible-reply tokens ≤ W, in project tokens, with sys counted without the notes sentence (§2.1). The current observation is always sent. Replayed reasoning items move with their turns and do not count toward W (§2.8).
- **Summary (Σ) cells:** before sending step t, if the payload would exceed W, every earlier turn is replaced by one user-role bridge message. It holds a summary written by the same model, using a generic summary prompt modelled on ARC's `SUMMARY_REQUEST_PROMPT`. The prompt text and its output cap (`max_output_tokens` 32,000, as every luna and sol request; §6) are frozen with the payload snapshot tests. Summary calls are logged as separate calls and count toward cost.
- **`compacted_between`** (Σ cells): 1 iff a summary was applied after the first reveal step and before the agent first saw the need-step observation. With s the environment step pending when the summary fired, it counts when r_first < s < n, or when s = n and the summary was applied to the payload of the need step's first call. A summary fired during a lookup round-trip at the need step does not count: the agent had already seen the need-step observation. Such a summary is logged in `compactions` with `at_lookup_result` = 1.
- **Notes:** in "-n-" cells, ARC's sentence is appended verbatim to the system prompt, as its last line. In the other cells it is absent. Nothing else in the system prompt differs between cells.
- **Replay:** "-r" sets `reasoning.context: all_turns` and "-0" sets `current_turn`. Both send the encrypted reasoning items (`store: false`, `include: ["reasoning.encrypted_content"]`), so the payloads are identical apart from `reasoning.context` (PLAN §7).
- **StateCarry** joins as one more cell in phase 2 (PLAN §6, §9). Its cell definition is fixed by amendment before its first paid run.

**Decision.** Accept the summary trigger ("before sending, if the payload would exceed W") and the replace-all-earlier-turns bridge. In Σ cells, distance is not a survival manipulation: Σ-cell S is measured only (`S_verbatim`, `S_carried`; `S_planned` stays unset for near), `compacted_between` is logged as defined above, Σ results are reported split by `compacted_between`, and Σ cells enter no confirmatory test. (decided 2026-10-01, D12)

*Why:* replace-all matches ARC's Gemini "fresh state" bridge, which S1 uses and Σ-n-0 is meant to mirror. With it, a summary between a near reveal and the need step compacts the near evidence in a sizeable share of Σ near episodes, so logging `compacted_between` keeps the accounting honest. No hypothesis in H1-H3 uses Σ cells.

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

PLAN §7's rows for Qwen3.6-27B and gpt-oss-120b (extension E1) and DeepSeek V4.1 Flash (not used for replay) are omitted above. The sol row's "~40 templates per cell" and "all 8 task cells" are replaced by D11 (§4.2).

**Operational.**
- **gpt-6-luna and gpt-6.1-sol:** Responses API with `reasoning.effort: medium`, `reasoning.mode: standard`, `reasoning.context` set explicitly on every request (never omitted, never `auto`), `store: false`, `include: ["reasoning.encrypted_content"]`, Flex service tier, `max_output_tokens: 32000`, default sampling. OpenAI's reasoning guide, checked 2026-09-30, says GPT-6.1 Sol, GPT-6 Sol and GPT-6 Luna default to `medium` effort, and that `standard` is the default reasoning mode for GPT-6 models ([OpenAI reasoning guide](https://developers.openai.com/api/docs/guides/reasoning)). The pilot confirms that the echoed request fields match.
- **Gemini 3.8 Flash:** Interactions API with `thinking_level: high` set explicitly (the default is medium, PLAN §16.1), on the standard service tier (D21, §7.6).
- **Pins:** none of luna, 6.1-sol or Gemini 3.8 Flash has a dated snapshot (PLAN §16.2, §16.6). The `model_returned` string on each response is therefore the pin. If it changes during a sweep, the change is flagged, and results are also reported split by model string.
- A response with status `incomplete` at the need step (for example, hitting `max_output_tokens`) counts as a content failure and scores 0.
- **Output cap** (D13, as implemented by PR #22): `max_output_tokens: 32000` is sent explicitly on every luna and sol request: every step request in every harness cell (§5), every summary request in the Σ cells, and every request of the `reasoning.context` echo check and the replay-use probe (§10.1). A config cannot omit it. On OpenAI the cap includes reasoning tokens. Summary requests carry the same 32,000 (`summary_max_output_tokens`), not ARC's 8,192-token summary cap, which belongs to the ARC leg's Gemini configs (§7.1, S1).
- **`incomplete` responses, as implemented** (PR #22). A step response with status `incomplete` counts as an invalid action at **any** step, not only at the need step, whatever `incomplete_details.reason` says; the reason is logged.
  - Its partial text is never parsed, so a `lookup(...)` in it is not served.
  - At the need step it is the scored action and scores 0, a content failure (§2.6, §13). That includes an incomplete answer to a lookup response at the need step.
  - At a routine step it counts against `routine_acc`, and the episode continues.
  - The episode is neither excluded nor re-run (§13).
  - The incomplete turn is replayed as it was returned: its reasoning item, and its partial message if there is one, stay in the history. A turn that stopped while reasoning has no visible reply, so it adds only its observation's tokens toward W (§2.8). The r and 0 arms of a pair still differ only in `reasoning.context`.
  - An incomplete summary response is never scored; it is retried, like any failed summary call (`harnesses/DESIGN.md` §4.3).
  - In the replay-use probe (D29, §10.1), an incomplete turn-3 response counts as a miss, and an incomplete turn 1 or 2 makes the trial unscorable, so it is replaced like a trial excluded under D29.

**Decision.** [Amended 2026-10-02, see §17.2] Effort `medium`, mode `standard`, explicit `reasoning.context`, `max_output_tokens` 32,000 and the Flex tier for OpenAI. (decided 2026-10-01, D13)

*Why:* medium is the documented default and keeps sol's H2 core, the largest phase-1a line, within reach of the cap. H2 is a PersistGym-only test, so it need not match the ARC leg's high effort; the risk that medium effort understates the value of replay is listed in §15.

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

**Operational** (as implemented by patches 0001-0017, `arc/README.md`; technical choices accepted by the researcher on 2026-10-01).
- **S1/S2 never drop old turns** (patch 0016). In `manual_rolling` with a summary compactor (S1, S2), the drop-oldest trim is disabled, not merely pushed out by a larger `MAX_CONTEXT_LENGTH`. History is lost only by summarizing, as in S4: at the 175k-token usage trigger, or when the provider rejects an action request as too long (one summary and one retry per action request; a second overflow ends the run with `AGENT_ERROR`). S1/S2 use S4's `MAX_CONTEXT_LENGTH` of 1,048,576 and record `context_trims`, which must stay 0. S0 still drops the oldest pair above 175k characters.
- **Shared request block** in all four profiles: `thinking_level: high`, `thinking_summaries: auto`, `store: false`, `max_output_tokens: 65536`. In S0-S2 the thought summaries are logged but never sent back to the model. ARC's published Standard recordings carry no summaries, so its Standard run probably did not request them; this known difference is reported with the results.
- **Transport retry** (patch 0009) stays on, with identical settings, in all four configs. It changes no request body; ARC's published runs did not have it.
- **Service tier:** `request.service_tier: standard` is set in all four profiles (patch 0017, D21). Patch 0003 validates the value and records the tier served; a test in 0017 checks that no path profile can request `flex` or `priority`.
- **Cost guard:** the D22 guard ($120 per counted run, §7.7) is not in the profiles. The paid launcher sets it at run time (patch 0010's `MAX_RUN_COST_USD`), so the config hashes below do not cover it; each run's `meta.json` (`cost_cap_usd`) and `run_meta.json` (`cost_guard`) record it. The researcher kept it there at sign-off and added a hold after any run that reaches it (§0.3, line 12; §7.7).

**Config freeze record** (PR #21, merged as `7955f11`; `arc/config_freeze.json`, written by `uv run python -m arc.config_hash`). For each profile, the patched harness's own `get_model_config` resolves the config, and `config_hash` is the SHA-256 of its canonical JSON (`common.runmeta.config_hash`, the same hash every run's `meta.json` carries). A separate script (not committed) that parses the patched `model_configs.yaml` with PyYAML, not the harness's loader, re-derived all four hashes, and they match (`arc/README.md`). If the block-1 pilot forces a config change, the change is made by amendment "A-cfg" (§17), merged before the first block-2 run. Since PR #23 the ARC launcher reads the tables in this section (§12), so any config change after the freeze needs a dated amendment that writes the new values into these tables themselves; a table added only to §17 is not enough. The amendment is merged together with the regenerated `arc/config_freeze.json` (and any changed patch files); until the record and these tables agree on `origin/main`, every paid ARC run refuses.

| Config | Config entry name | `config_hash` (SHA-256) |
|---|---|---|
| S0 | `google-gemini-3-8-flash-high` | `615ea035324fdcdb114b00cfcf7eab55c56ea97b5d8808c12ad9097e93992dda` |
| S1 | `google-gemini-3-8-flash-high-rolling-summary` | `d2f7825fab5411a1218b7a5d20520c5abb5f97d488907176b4391f760e7e54fd` |
| S2 | `google-gemini-3-8-flash-high-rolling-summary-notes-off` | `2f0dd011bc04963835aa2ac2d28b3229ef61e0e496dbd9d417699a920e796bab` |
| S4 | `google-gemini-3-8-flash-high-provider-adapter` | `e7432aafd0ad7a291be197a5634d5cbb6ee0b43edeefda1aebe26d21af54cf08` |
| S3 (optional) | none: no profile is built or frozen | none; S3 runs only if an amendment first adds and freezes its profile (§0.3, line 13) |

Shared by all four configs:

| Item | Value |
|---|---|
| Upstream harness | `arcprize/arc-agi-3-benchmarking`, pinned at `4ca00e607e3364a501fcbf7d1b7537dd2729cec3` (`4ca00e6`) |
| Patch series | `arc/patches/0001-*.patch` to `0017-*.patch`, the 17 files listed in `arc/config_freeze.json` |
| Patch-series SHA-256 | `14e25cc71411eaf5e3ca4cb87e78569061586e0a428477ce5e2fabfe02d631d6` |
| Patched commit | `67f6dd0d37eccb8f77a7645f0e0e9fc2ea400359` |
| Patched tree | `5206d039db6761c4f56c932fed716321113360f1` |

**Checks behind the record** (PR #21, `arc/README.md`): `apply_patches.py --each` ran the upstream unit tests after every patch: 872 passed after 0017. The only failure was the known flaky upstream test `test_recorder::test_concurrent_recording`, once after 0015 in that run and once in another full-suite run after 0017, both with other test runs loading the machine. It passes on its own, and no patch touches the recorder. The $0 offline runs with a stub model passed for S0, S1, S2 and S4 (`offline_smoke.py --toy`), and so did the launcher's inner modes (`run_path_offline.py`). The paid launcher refuses any run whose patch files, patched commit or tree, or resolved profile hash differ from this record (§12). Since PR #23 it also refuses unless `arc/config_freeze.json` is the same blob in `HEAD` as on `origin/main` and is the record the run loaded; the record's four profile hashes, patch-series SHA-256 and upstream pin, and the patched commit and tree, equal the tables in this section of the frozen PREREG.md on `origin/main` (`arc/prereg_freeze.py`); and `arc/patches` is the same tree in `HEAD` as on `origin/main`, with the patch files the run applies byte-identical to the committed ones. Once this file is on `main`, a root test (`test_the_repository_prereg_table_matches_the_committed_record`) also fails whenever the record and these tables differ.

### 7.2 Eligibility rule
> **Eligible:** public games where both published high-effort runs cost ≤ $60 *and* the published Standard-to-Adapter gap is ≥ 20 points. These are FT09, SB26, R11L, LP85, SC25 and CD82 (see `docs/background.md`). **[A1]** This filter can select Standard runs that were cheap because they ended in an error; the researcher decides before the draw whether to keep or amend it (§16.4).
>
> The published runs are one-seed screens. Our fresh seeds re-measure the gap, and claims are stated as conditional on "games where the Adapter helps". (PLAN §8.3)

**Operational.** The inputs are the published Gemini 3.8 Flash high-effort public-set runs, one per game and harness, and the operational slice's inferred endings (commit `ef251ba`; `results/arc_public_ops/20261001T185155Z/eligibility.csv` adds the SP80 and TN36 recordings). Costs are at ARC's no-cache list accounting; the gap is Adapter RHAE − Standard RHAE.

**Decision** (the researcher's §16.4 choice: amend the rule).
- **Path games:** public games where both published high-effort runs cost ≤ $60, the published gap is ≥ 20, **and** the published Standard-high run ended normally (`GAME_WIN`, `ACTION_BUDGET` or `TIME_BUDGET`, as inferred by the operational slice). These are **FT09, SB26, R11L and CD82**. LP85 and SC25 leave the pool: their Standard-high runs ended `ERROR_OR_CLOSED`. All four games are path games, so there is no path draw (§7.3).
- **Held-out games** (replacing D16): among the remaining public games with gap ≥ 20 and a normal Standard-high ending, the 3 with the lowest max(published Standard cost, published Adapter cost). These are **SP80, VC33 and TN36**. RE86 is excluded by the ending rule.

(decided 2026-10-01, D14)

| Game | Role | Published gap (RHAE) | Standard-high ending | List cost S0 / S4 (USD) | Billed estimate S0 / S4 (USD) |
|---|---|---|---|---|---|
| FT09 | path | 85.7 | `ACTION_BUDGET` | 28.73 / 8.01 | 27.70 / 3.44 |
| SB26 | path | 97.2 | `ACTION_BUDGET` | 29.32 / 17.01 | 23.55 / 12.67 |
| R11L | path | 67.1 | `ACTION_BUDGET` | 54.75 / 34.99 | 47.93 / 24.46 |
| CD82 | path | 35.2 | `ACTION_BUDGET` | 11.68 / 29.01 | 9.48 / 19.91 |
| SP80 | held out | 33.3 | `ACTION_BUDGET` | 29.21 / 66.72 | 25.85 / 39.13 |
| VC33 | held out | 78.8 | `ACTION_BUDGET` | 86.99 / 39.70 | 77.75 / 21.10 |
| TN36 | held out | 53.6 | `ACTION_BUDGET` | 42.87 / 90.89 | 37.69 / 67.37 |

Sources: gaps and endings from `results/arc_public_ops/20261001T185155Z/eligibility.csv`; costs from `results/cost_model/20261001T203318Z/optA_arc_run_costs.csv` (identical to the file of the same name in `20261001T185959Z`), which reads `results/arc_public_ops/20261001T185155Z/recordings_per_action.csv`. "Billed estimate" re-prices each recording's cached input at the cached price, as an estimate of standard-tier billing with implicit caching. The recorded SP80 and TN36 costs match the premise table.

*Why:* the two games removed are the ones whose published Standard-high runs stopped early, so their published costs understate a complete run. Their clean-run bounds are about $174 for LP85 ($156 if capped at 12 h) and $88 for SC25, against published costs of $24.33 and $39.95 (`results/arc_public_ops/20261001T035436Z/summary.md`), and LP85's whole 22.2-point gap is one stopped level (PLAN §16.4). PLAN §16.4 left this choice open until after the operational slice, which computed no H5 quantity.

**Consequences, stated now.**
- The pool has 4 games, fewer than the 5 that v0.1 §7.3 required without an ARC design amendment. This decision is that amendment; PLAN amendment A2 records it, and PLAN §8.3's "Draw 4 of the 6" and PLAN §9's "VC33 or RE86" are superseded.
- Path and held-out games are no longer exchangeable. The held-out games come from a separate, cost-ranked rule, and each of them exceeds the $60 filter on at least one harness (SP80 Adapter $66.72, VC33 Standard $86.99, TN36 Adapter $90.89).

### 7.3 Game order from a public beacon
> **Draw 4** of the 6 with a recorded random seed. [...] The 2 undrawn games become StateCarry held-out games. (PLAN §8.3)
>
> **Draw first.** Run the seeded draw at the PREREG commit, as a permutation of the 6 eligible games: the first 4 are path (dev) games, the last 2 are held out. Never pilot on a held-out game. (PLAN §16.3)

**Operational.** Under D14 the path and held-out sets are fixed, so the draw no longer chooses games. It orders the 4 path games, which sets the truncated-pilot game (D17), the game dropped under the 3-game fallback (D32), and, through SEED, the run orders (D18) and the analysis seeds (§9.1, §9.7).

```python
import random

PATH_GAMES = ["FT09", "SB26", "R11L", "CD82"]  # D14, in PLAN §8.3 order
# SEED comes from a public beacon after the freeze (D15)
perm = random.Random(SEED).sample(PATH_GAMES, k=len(PATH_GAMES))
pilot_game = perm[0]      # D17
fallback_drop = perm[3]   # D32
```

**Decision.** SEED comes from a public randomness beacon published after the freeze:
- T = the freeze commit's committer time + 10 minutes.
- SEED = `int(outputValue[:16], 16)` of the first NIST Randomness Beacon 2.0 pulse whose timeStamp is ≥ T, fetched from `https://beacon.nist.gov/beacon/2.0/pulse/time/<T in ms>`. The script also checks that the preceding pulse is before T, so the pulse used is the first one at or after T.
- **Fallback,** only if NIST has no such pulse within 24 h of T: the first drand mainnet (`default` chain) round at or after T, from `https://api.drand.sh/public/<round>`, with SEED = `int(randomness[:16], 16)`. If NIST cannot be reached at all for 24 h, the fallback needs the researcher's decision, recorded in `results/decisions.md` first (§0.3, line 5).
- The draw runs **once**, with `arc/draw_games.py` (PR #16), which refuses unless the commit is the freeze commit on `origin/main`'s first-parent history and PREREG.md there is frozen (§0.4). The pulse URL, the SEED, the raw beacon responses, the permutation, the run orders and the Python version go to `results/draw/<run_id>/` and into `results/decisions.md`.

(decided 2026-10-01, D15)

*Why:* anyone could compute a date seed's permutation in advance; a beacon value published after the freeze cannot be shopped for. NIST's `/pulse/time/<t>` returns the pulse at that time or the next one ([NIST Beacon 2.0](https://csrc.nist.gov/projects/interoperable-randomness-beacons/beacon-20), checked 2026-10-01). drand's API is documented at [drand HTTP API v1](https://docs.drand.love/developer/API-v1/drand-http-api) (checked 2026-10-01). The script keeps the raw responses byte for byte but does not verify the beacons' own signatures.

- The **recorded output is authoritative.** Python guarantees only that `random()` reproduces across versions for a given seed, not the algorithms of other methods such as `sample` ([Python 3.12 `random` docs](https://docs.python.org/3.12/library/random.html), "Notes on Reproducibility", checked 2026-09-30).
- Nobody can compute the permutation before the beacon value exists.

**Decision.** Third held-out game: replaced by D14's held-out rule, which selects VC33 together with SP80 and TN36 and excludes RE86. (decided 2026-10-01, D16)

**Decision.** The truncated ARC pilot (§11) runs on `perm[0]` of the beacon-seeded order of the 4 path games. No pilot ever runs on SP80, VC33 or TN36. (decided 2026-10-01, D17)

*Why:* a seeded choice cannot be steered toward a cheap game. The pilot measures cost and tokens per action, and pilot blinding forbids reading per-config level progress (§11).

### 7.4 Runs, seeds, logging and run order
> **Runs:** 4 games × 4 configs (S0, S1, S2, S4) × 2 seeds = 32 runs.
>
> **Log per run:** config hash, fork commit, model string, exit reason (`GAME_WIN`, `ACTION_BUDGET`, `TIME_BUDGET`, `API_ERROR`, `AGENT_ERROR`, …), per-level results, actions, tokens (input, cached, output, reasoning), cost (list and actually billed) and wall clock. (PLAN §8.3)
>
> If it continues, seed-1 S1+S2 and all of seed 2 run as one wave, so the four configs are compared over the same days (Gemini 3.8 Flash has no dated snapshot). (PLAN §16.2)

**Operational.**
- Replicates s ∈ {1, 2}. A re-run of replicate s gets seed s + 100. If the API exposes a sampling seed, it is set to the run's seed and recorded; otherwise the seed only labels the replicate.
- Counted runs are played on ARC's online scorecard. Local or offline play is for testing only (PLAN §16.3).
- The full exit-reason set is `GAME_WIN`, `ACTION_BUDGET`, `TIME_BUDGET`, `SCORECARD_CLOSED`, `API_ERROR`, `AGENT_ERROR`, `UNKNOWN` (`docs/background.md` §2), plus `COST_CAP` from the guard in §7.7. `run_meta.json` records both `exit_reason` and `agent_exit_reason` (§7.5).

**Decision.** Block 2's 8 runs run in the order `random.Random(SEED + 2).sample(units, k=len(units))`. Block 3's 24 runs use `SEED + 3` the same way. In both cases `units` is the list of (game, config, replicate) tuples sorted lexicographically, and SEED is the beacon seed of D15. (decided 2026-10-01, D18)

**Changed at sign-off** (§0.3, line 15; the researcher, 2026-10-01). Block 3's ARC runs go **back to back, one at a time, in the SEED + 3 order**. This replaces the last sentence of D18 as decided, "All block-3 runs start within 72 h of each other." The rest of D18 is unchanged: block 2 runs in the SEED + 2 order and block 3 in the SEED + 3 order, both as defined above. Block 3's ARC runs are approved as their own block, `3-arc`, and the PersistGym main sweep (`3-persistgym`) may run beside them once the per-stream locks have landed (§12).

*Why:* there is no dated Gemini snapshot, so a random order keeps time trends from lining up with configs. No config can be looked at early, and that is intended. With one ARC run at a time, the 72 h window could not be promised: back to back, block 3's 24 ARC runs take about 60-79 h at the path games' published durations (§12).

*Confirmed at sign-off (§0.3, line 4):* if the 3-game fallback drops `perm[3]` (D32) before block 3, its units are deleted from the SEED + 3 order and the remaining units keep their order.

### 7.5 Error re-run rule
> **Pre-registered rule for errors:** a run ending in `API_ERROR`, `AGENT_ERROR` or `TIME_BUDGET` is re-run once with a new seed. Both runs are reported. (PLAN §8.3)
>
> The tier latency rule, the cost-guard value, the re-run reserve, and whether `TIME_BUDGET` endings are re-run. (PLAN §16.5)

**Operational: which exit field.** The rule reads **`agent_exit_reason`** (patch 0015), the ending the agent's own loop recorded, not `exit_reason`. `Swarm.close_scorecard` can rewrite `exit_reason` after the game is over: if closing the scorecard fails, every agent is marked `API_ERROR`, even a run that ended `GAME_WIN` or `ACTION_BUDGET` (`arc/README.md`, "Exit reasons in this harness"). Reading `exit_reason` would therefore re-run, and replace, finished runs because of a bookkeeping failure after the game, which says nothing about how the config played. A run whose scorecard was closed server-side (`exit_reason` = `SCORECARD_CLOSED`) has `agent_exit_reason` = `API_ERROR`, so it is re-run under either field. Both fields are logged and reported. A missing `agent_exit_reason` (the process died) counts as `UNKNOWN` (§0.3, line 1).

In the pinned harness, `API_ERROR` means the ARC environment step failed, and a model API failure after the harness's retries ends as `AGENT_ERROR`. With patch 0009, a model call that fails because the 12 h clock ran out during a throttling backoff is recorded as `TIME_BUDGET` (`arc/README.md`).

**Decision.** Error re-runs, on `agent_exit_reason`:
- **Re-run once** (new seed): `API_ERROR`, `AGENT_ERROR` and `UNKNOWN` (a `SCORECARD_CLOSED` run is included through its `API_ERROR`); `TIME_BUDGET` only under D20 below.
- **Final as is:** `GAME_WIN`, `ACTION_BUDGET`, `COST_CAP` (§7.7), and `TIME_BUDGET` outside a latency incident (flagged).
- **Counted run:** the re-run replaces the errored run in every primary analysis. If the re-run also ends in a re-run-eligible exit, it is counted as is, with levels cleared before the end scoring normally, and it is flagged. There is no second re-run.
- **Both runs are reported** (as written). A sensitivity analysis scores the original runs as is.
- **When:** the re-run starts right after the run it replaces, ahead of the next run in the block's order (§7.4); the rest of the order is unchanged (§0.3, line 16).

(decided 2026-10-01, D19)

*Why:* treating infrastructure endings as re-runnable measures each config when the system works, and the sensitivity analysis keeps the "errors are a harness property" reading visible. Among the published high-effort runs, 5 of 25 Standard runs ended `ERROR_OR_CLOSED` and none of the Adapter runs did (`results/arc_public_ops/20261001T035436Z/summary.md`).

*Confirmed at sign-off (§0.3, line 2):* if the scorecard result of a run that is final under this rule cannot be read, the run is re-run once, as `UNKNOWN`.

**Decision.** A `TIME_BUDGET` ending is final: scored as is and flagged. The exception is a provider-latency incident: the run's median seconds per model call exceeds 2× the median of that config's earlier counted runs (or the pilot's median, if there is no earlier counted run). Such a run is re-run once under D19. (decided 2026-10-01, D20)

Operational reading (§0.3, line 3, confirmed): "the median of that config's earlier counted runs" is the median of their per-run median seconds per model call, over all games. The launcher records each run's median seconds per successful model call in `meta.json` (`latency`) and in the `costs.csv` row (`latency_s`).

*Why:* Standard-like configs are slow (median 80 s per action on the Standard harness vs 6 s on the Adapter, over the 8 recorded games; `results/arc_public_ops/20261001T035436Z/summary.md`). On ARC that pace is a property of the harness, so a re-run at the same pace would usually time out again, at full cost (about $96-115 list per run on the path games, §7.7). ARC itself scores `TIME_BUDGET` as is, and PLAN §16.5 left this question to PREREG. This replaces PLAN §8.3's re-run of every `TIME_BUDGET` ending (recorded in A2).

### 7.6 Service tier
> **[A1]** Flex is uncertain for ARC: Google's target is 1-15 min per call with no fallback. One tier is chosen for all ARC configs by a pre-registered latency rule; runs never switch tier (§16.4). (PLAN §8.3)
>
> **One service tier for all ARC configs,** chosen by a pre-registered latency rule from the M0 probes. No per-run fallback (§15 updated). (PLAN §16.4)

**Decision.** The Gemini **standard tier** is fixed now for every ARC config and for phase 2. There is no Flex latency gate: block 1's Flex latency probe (~$3) is dropped and replaced by a standard-tier payload acceptance check (≤ $1). `request.service_tier: standard` is set in every ARC profile at the config freeze, and runs never switch tier. **Warning rule:** before each block, the researcher is told if any planned run's 1.5 × published actions × published seconds per action exceeds 12 h. (decided 2026-10-01, D21)

*Why:* under D14, the drafted Flex rule would need a 90th-percentile Flex latency of about a minute per call (6 h / (1.5 × 234 actions) ≈ 62 s, where 234 is the largest published action count on the path games, R11L's Adapter run; `results/arc_public_ops/20261001T185155Z/eligibility.csv`), while the published Standard median is already 80 s per action before any Flex queueing, and Google targets 1-15 min per Flex call with no fallback (PLAN §16.1). The drafted rule would almost surely have chosen the standard tier anyway. The standard tier's billed forecast fits the 1b cap at the G0 rule (§10.1). This replaces PLAN §16.4's "chosen ... from the M0 probes" (recorded in A2), and the "Flex everywhere" fallback no longer applies to ARC (§10.1).

### 7.7 Per-run cost guard
> **Extra harness patches,** kept as files in `arc/`: [...] an optional per-run cost guard (exit `COST_CAP`; the researcher decides whether it is an acceptable, reported deviation); [...] (PLAN §16.3)

**Decision.** Adopt the guard (patch 0010) at **$120 per run** at ARC's no-cache list accounting, computed by the harness from its own configured prices. It applies to every counted ARC run, including S0+StateCarry, whose own calls count. A `COST_CAP` ending is scored as is, not re-run, flagged and reported as a deviation from ARC's protocol. H4 and the StateCarry win are also reported without the units that contain one. (decided 2026-10-01, D22)

*Why, and when it binds:* at the published Standard pace, the 12 h clock caps an S0, S1, S2 or S0+StateCarry run at about $96-115 list on the path games (SB26 $96, R11L $98, CD82 $103, FT09 $115: 12 h × each run's list cost per second, `cost_total_usd` / `duration_s` in `results/arc_public_ops/20261001T185155Z/recordings_per_action.csv`). FT09 is closest to the guard (about $124 at its median pace of 80 s per action), so the clock usually binds first. The guard binds mainly Adapter-pace runs of more than about 800-1,250 calls ($120 / $0.150 and $120 / $0.096, the path games' published Adapter list cost per call, `cost_per_step_mean` in the same run's `summary.md`). A `COST_CAP` on S4 would shrink the gap and inflate StateCarry closure, which is why units with a `COST_CAP` are also reported without them.

**As implemented** (PR #21): the ARC launcher sets the guard to $120 for every counted run and to the planned spend for pilots and checks, at run time rather than in the frozen profiles (§7.1; §0.3, line 12). It refuses a counted run planned below $120. The guard checks before each action, so a run can overshoot by at most one step.

**Changed at sign-off** (§0.3, line 12; the researcher, 2026-10-01).
- The guard stays where it is: set by the launcher at run time, outside the frozen profiles, with no patch 0018. The $120-of-room rule stays (§12).
- **Hold.** Any paid run that reaches its $120 run guard (every counted ARC run has one, S0+StateCarry included) ends `COST_CAP`, scored as D22 decided above, and places a hold. While the hold stands, no further paid run starts in either stream, ARC or PersistGym (§12); a run already under way in the other stream is not stopped. Only the researcher clears the hold, with a line naming that run, merged into `results/decisions.md`. The grammar of that line is defined in the code that adds the hold (for example `cleared_hold: <run_id>`). That code lands as a $0 pull request before block 2.

*Why:* the researcher wants to be asked about every run that reaches the guard before any more money is spent.

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

**Done:** run `results/arc_public_ops/20261001T035436Z/` (commit `ef251ba`, on `main`), extended with the SP80 and TN36 recordings in run `results/arc_public_ops/20261001T185155Z/` (PR #17). It reproduces the premise check's 11 of 25 vs 5 of 25 early endings. Neither run computes P(clear | reached).

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
- **Games:** the dev set is the 4 path games (§7.2). The held-out set is SP80, VC33 and TN36 (D14), which replaces "the 2 undrawn eligible games plus VC33 or RE86".
- **Closure** C = (R̄_SC − R̄_S0) / (R̄_S4 − R̄_S0). Each R̄ is a mean of RHAE over game-replicate units (a ratio of means, not a mean of per-game ratios). A 90% bootstrap interval over units is reported. As with H4, the claim rests on the point estimate and is descriptive.
- **Cost per game** is the mean over games of the mean over replicates of counted-run cost on the primary basis (D23). S0+StateCarry includes every StateCarry call (promotion, digest). Re-run costs are reported separately and left out of the comparison.
- **StateCarry freeze:** the code commit and config hash of the StateCarry version under test are recorded by a pre-declared amendment ("A-SC", §17) before any G3 evaluation run, and again before any held-out run.

**Decision.** Cost basis: the primary basis is the **billed estimate**, from provider-reported cached tokens at the standard tier's prices. ARC's no-cache list cost is reported alongside. Re-run costs are excluded from the comparison and reported separately. (decided 2026-10-01, D23)

*Why:* billed is what a Standard-harness user actually pays, and the only basis on which StateCarry's cache-friendly layout can pay off. It is also the harder bar. In the 8 recorded games, a Standard call costs 2.6 times an Adapter call billed ($0.168 vs $0.064, medians) and 1.7 times at list ($0.191 vs $0.114) (`results/arc_public_ops/20261001T035436Z/summary.md`). The cost half of the win is therefore likely to fail on billed cost unless StateCarry cuts reasoning tokens or calls; the "partial" band (below) then applies.

**Decision.** Gate and claim rules (option B):
- **G3:** the frozen v0 runs once, with a fresh replicate, on each of the 4 dev games. These 4 runs are compared with the path-study counted S0 and S4 runs on the same games. Continue iff C_dev ≥ 0.25 **and** the cost per game of S0+SC ≤ that of S4. Development runs made before the v0 freeze do not enter G3.
- **G3 budget:** the 4 G3 runs are their own phase-2 budget line, outside the $150 dev cap.
- **Held-out set:** all 3 held-out games are committed; there is no conditional cut to 2 games.
- **Held-out order** (PLAN §16.4 option, adopted): the 12 held-out S0+S4 runs go first. The 6 StateCarry held-out runs proceed only if the held-out G ≥ 10 RHAE, the same bar as kill criterion 4. Otherwise closure cannot be estimated, and that is reported.
- **Phase-2 cap:** raised from $950 to **$1,250** (PLAN §17.3). A2 first proposed $1,150; the researcher set $1,250 on 2026-10-01 as a follow-up to A2.
- **G4 wording:** **win** iff C ≥ 0.50 **and** cost(SC) ≤ cost(S4). **Partial** iff 0.25 ≤ C < 0.50, or C ≥ 0.50 with the cost condition failing. **Negative** iff C < 0.25.

(decided 2026-10-01, D24)

*Why:* counting G3 inside the $150 dev cap would leave little money for development before v0 is frozen. A ratio of means is stable when one game's gap is near 0, but lets a large-gap game dominate. Gating the StateCarry runs on a held-out gap ≥ 10 saves 6 runs when there is nothing to close.

*Forecast at this draft* (`results/cost_model/20261001T203318Z/option_a_summary.md` and `optA_forecasts.csv`; billed, standard tier, 1k output tokens per PersistGym call, S0+StateCarry priced at the S0/S4 midpoint): phase 2 comes to **$1,233.19** with the 20% re-run reserves on the G3 and held-out runs, $16.81 under the $1,250 cap, and $1,054.94 without those reserves. At the Checkpoint C pricing rule it is $1,704.09, $454.09 over the cap. The held-out runs alone are $967.98 with their reserve, and the G3 runs $101.48. Block 4 is approved separately, with measured costs, and the stop-and-ask rule applies before the cap is exceeded.

## 9. Analysis plan (PLAN §10)

### 9.1 Primary PersistGym analysis
> **Primary PersistGym analysis, per model.** Success at the need step, analysed with the fully crossed within-template design.
> - **Primary contrasts (H1-H3):** probability-scale differences of cell means, with 90% and 95% CIs from a cluster bootstrap over templates (10,000 resamples).
> - **Confirmatory model:** logistic regression with template fixed effects, harness × recoverable × derived × distance terms and cluster-robust SEs. This is what the power simulation assumed.
> - **Sensitivity model:** a Bayesian logistic GLMM with template random intercepts (e.g. `bambi`).
> - Report both logit and probability scales. Interactions can flip sign between scales near ceilings; the pre-registered scale for kill rules is the probability scale. (PLAN §10)

**Operational.**
- **Bootstrap:** resample templates with replacement; recompute each contrast from all of the resampled templates' episodes in the contrast's cells; 10,000 resamples; **percentile** intervals; bootstrap RNG seed = SEED + 10 (SEED from D15).
- **Confirmatory GLM:** `statsmodels` binomial GLM with template dummies and a covariance clustered by template, fitted separately per model. On sol the design has only the D11 cells, so the distance term drops out there. Templates with no outcome variation in the fitted subset carry no within-template information and are dropped from the GLM only; their count is reported. The bootstrap keeps them.
- **Cluster-robust SEs** use the small-sample factor G/(G − 1) only (G = number of templates; `analysis/power_sim.py --cluster-correction clusters`), not the `statsmodels` default, which also counts the template dummies.
- The Bayesian sensitivity model needs a new dependency (`bambi`), which the analysis track adds with `uv add` and notes in its PR.

**Decision.** Percentile intervals; no-variation templates dropped from the GLM only; the quasi-Poisson log-link model for cost outcomes (§9.5); cluster-robust SEs with the G/(G − 1) factor only. (decided 2026-10-01, D25)

*Why:* the `statsmodels` default counts the template dummies as parameters, which inflates the SEs with only a few episodes per template (PR #6 review). Under D26 only the GLM's sign and point estimate enter a decision, so this choice changes only the reported GLM SEs and p-values; it is stated so they can be reproduced.

### 9.2 Not used
> **Not used:** max−min harness spread. Under the null it rises as success falls; a simulation with no true effect gave an expected 8.7pp at p=0.95 and 16.1pp at p=0.60. If a single "how much does the harness matter" summary is wanted, use a harness variance component with a permutation null. (PLAN §10)

### 9.3 Scales
Every primary contrast is reported on both the probability and the logit scale. Kill and equivalence rules use the probability scale only (PLAN §4, §10). If the two scales disagree in sign, that is reported.

### 9.4 Multiplicity
> **Multiplicity:** Holm correction across the primary confirmatory contrasts (H1, H2, H3). H4 and H5 are descriptive. (PLAN §10)

**Decision.** The Holm family has **4 one-sided tests** at a familywise α = 0.05:
1. H1: H0 is Δ_H1 ≤ 0.
2. H2 success: H0 is Δ_der ≤ 0 (sol).
3. H2 tokens: H0 is TE ≤ 0 (sol).
4. H3: H0 is Δ_H3 ≥ 5pp (non-inferiority).

Each p-value is the one-sided percentile-bootstrap p-value from §9.1 (the share of resamples on the null side), on the probability scale; for test 3, on the ratio scale. A hypothesis is called "supported" only if its Holm-adjusted test rejects **and** the model-based estimate agrees: for tests 1 and 2, the confirmatory GLM estimate has the same sign; for test 3, the log-link estimate of §9.5 is above 0; for test 4, a binomial GLM with template fixed effects and an arm indicator (single-turn vs multi-turn) on the H3 cells gives a probability-scale Δ_H3 below 5pp (the confirmatory GLM of §9.1 has no term for the single-turn control).

The §3 readings ("prediction holds", "falsified", "kill", "equivalence") use point estimates or unadjusted 90% CIs, as PLAN writes them; "supported" uses the Holm-adjusted tests. Both are reported, and only "supported" is used for a confirmatory claim. The results quote the achieved power at the worst Holm step (one-sided α = 0.0125) from the committed D11 simulation (§4.2). (decided 2026-10-01, D26)

*Why:* splitting H2's "or" prediction into two tests protects both branches. In the committed simulation, "supported" (the test rejects and the GLM estimate is positive) had the same probability as the bootstrap test alone in every row (`results/power_sim/20261001T190327Z/h2_sol_power.csv`).

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

The sizing rule is in §4.2. The current sol simulation is the table in §4.2.

### 9.9 ARC analysis
> - Per game and config: RHAE (mean over 2 seeds), levels cleared, actions relative to the human baseline, tokens and cost.
> - Path shares are (step difference) / (S4 − S0), with a bootstrap over the 8 game-seed units, and the table is labelled descriptive.
> - H5 uses a per-level logistic model of P(clear | reached, depth, harness) with game fixed effects, on the published runs and on ours.
> - Always report exit reasons. (PLAN §10)

The operational versions are in H4 and H5 (§3). Exit reasons (`exit_reason` and `agent_exit_reason`) are reported per run, including original runs that were replaced by re-runs.

### 9.10 Exploratory analyses
Everything not registered in §3, §8 or this section is labelled **exploratory**. That includes S3, H5 at other efforts or for other models, the event studies, luna's H2 replication, the W/Σ replay pairs, Σ-cell results, and the per-cell validity rates.

## 10. Gates, kill and equivalence rules (PLAN §11, §14, §16.2, §16.3)
> **Kill criteria in `PLAN.md` §14 are binding.** If one fires, stop that leg and propose the fallback in the plan. Don't quietly extend it. (CLAUDE.md)

Every gate metric is computed by a committed script. The decision, the numbers behind it and the spend to date are written to `results/decisions.md`. **The researcher makes every go/no-go call**; Claude proposes.

### 10.1 G0 (Oct 7)
> Go if: snapshot tests pass; sol's echoed `reasoning.context` matches the request; Gemini S0-S2 run; ARC pilot cost ≤ $30/run with Flex. [...] **[A1]** The cost rule becomes "forecast billed 1b + re-run reserve ≤ $900 at the chosen tier"; the toggle rule adds the replay-use probe; G0 approves only the seed-1 S0+S4 block (§16.2). (PLAN §11)
>
> **G0 toggle rule** adds a replay-use probe (~$2). Turn 1 asks the model to privately pick a 3-digit number and reply only "ready"; turn 2 is filler; turn 3 asks for the number. Both arms send identical payloads; only `reasoning.context` differs. Chance is 1/1000. The probe is excluded from all analyses. (PLAN §16.3)

The text elided from PLAN §11 above gives G0's cost and toggle fallbacks; they are kill criteria 1 and 2 (§10.8) and the fallback list below. "The chosen tier" is the standard tier (D21).

**Decision.** The other G0 conditions:
- **"Snapshot tests pass":** every payload snapshot test, for each PersistGym harness cell (§5) and each ARC config S0-S4 (§7.1), passes at the commit the block-1 runs use. This includes the S1/S2 patches (0006-0008, 0013, 0016) and their snapshot tests.
- **"Gemini S0-S2 run":** in the truncated pilot (§11), on the standard tier, S0 reaches 50 actions, S1 reaches its first compaction plus 5 turns, and S2 reaches 30 actions, each on the Interactions API at `thinking_level: high` with the payload accepted and no `API_ERROR` or `AGENT_ERROR` ending. S1's compaction must produce the user-role bridge message. S4 must reach 50 actions, because D27 needs its billed/list ratio.

(decided 2026-10-01, D37)

*Why:* reaching the truncation point shows that the configs run, not that they run a full game within the 12 h clock. The $0 offline games with a stub model (PLAN §16.3) cover full-game mechanics without cost.

**Decision.** Cost forecast, rule 1:
- **At G0:** F = Σ over the 4 path games g and the configs c ∈ {S0, S1, S2, S4} of 2 × L(g, c) × b(c). L(g, c) is the published list cost of game g under the Standard harness for c = S0 and under the Adapter for c = S4; S1 and S2 are priced at the midpoint of the two (the rule PLAN §16.1 used). b(c) is the billed/list cost ratio measured for config c in the truncated pilot, from its provider-reported usage at standard-tier prices. **Go on cost iff F + reserve ≤ $900**, with the reserve of D28. The clean-run clause of v0.1 is moot, because no path game's published run ended early.
- **At Checkpoint C (conservative check):** the remaining 24 runs are forecast with seed-2 S0 and S4 per game at their measured seed-1 costs, and S1 and S2 per game at the measured S0 cost per call × max(measured S0 actions, measured S4 actions), plus the re-run allowance of §10.3. If that exceeds the remaining 1b cap, a 1b cap increase of up to about $170 may be requested there, from measured costs.

(decided 2026-10-01, D27)

*Forecasts at this draft* (`results/cost_model/20261001T203318Z/optA_forecasts.csv` and `option_a_summary.md`; standard tier; billed, with list in parentheses; the published recordings' cached shares stand in for b(c); the ARC rows are the same as in the older run `20261001T185959Z`):
- G0 rule, phase 1b with the 20% reserve: **$811.86** ($1,024.75) against $900. Billed headroom is $88.14; the forecast is $25.37 per counted run with the reserve.
- Checkpoint C rule, phase 1b with the reserve: **$1,042.92** ($1,251.80), i.e. a billed cap increase of $142.92, within the ~$170 allowed.
- Block 2 (8 seed-1 S0+S4 runs): $169.14 ($213.49) without the reserve, $202.97 ($256.19) with it.

*Why:* the cautious rules (S1/S2 at the larger of the two published costs, or at S0's cost per call × the longer run) would fail G0, a gate that releases only block 2. The real S1/S2 exposure is better judged at Checkpoint C from measured per-action costs on the same games. Choosing the forecast rule after seeing that the cautious rules fail accepts a known risk of asking for a cap increase at Checkpoint C.

**Decision.** Re-run reserve = 20% of F. G0 thus requires 1.2 F ≤ $900. (decided 2026-10-01, D28)

*Why:* every path game's published Standard run ended `ACTION_BUDGET`; the 11-of-25 early-ending rate comes mostly from long or errored games outside the path set, and the backoff patch targets transport errors.

**Decision.** [Amended 2026-10-02, see §17.1] Toggle rule. The OpenAI toggle on a model is verified iff:
1. the echoed `reasoning.context` equals the request on 100% of that model's pilot responses, in both arms; **and**
2. the replay-use probe passes, with 20 trials per arm: the `all_turns` arm recalls the exact number in ≥ 10 of 20 trials, and the `current_turn` arm in ≤ 1 of 20.

A trial whose visible turn-1 reply contains any 3-digit number is excluded and replaced. If the echo passes but the probe fails, that model's toggle is **not verified**, and the model runs no replay arm. If no API model is verified, kill criterion 1 applies. If luna is verified but sol is not, making luna H2's primary model needs an amendment. The probe's per-arm results are needed for G0; they are not H2's task or outcome, so §11's blinding does not cover them. (decided 2026-10-01, D29)

*Why:* chance is 1/1000, so 10/20 against 1/20 is an overwhelming separation; a stricter bar could reject a toggle that works when the model does not always commit to a number.

**Fallbacks if the ARC cost rule fails** (PLAN §12, in order, as they apply after D21):
1. "Flex everywhere" no longer applies to ARC: the tier is fixed at standard (D21). OpenAI already runs on Flex (D13).
2. 3 ARC games (D32).
3. Medium thinking. This needs a PREREG amendment, since H4 and the eligibility rule are defined at high effort (PLAN §14, item 2 [A1]).
4. Fewer sol templates (the §4.2 sizing rule). [Amended 2026-10-02, see §17.2]

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
- **Errors:** the number of the 8 counted seed-1 runs whose final `agent_exit_reason` is re-run-eligible under D19, after their one re-run. The rule fires if this is > 3.
- **Cost (D27, replacing PLAN's "measured cost per run × 24"):** ρ is the number of block-2 re-runs divided by 8. The forecast for the remaining 24 runs is [Σ over games of the measured seed-1 billed cost of S0 and of S4, for seed 2] + [Σ over games of 2 × 2 × (measured S0 billed cost per call) × max(measured S0 actions, measured S4 actions), for S1 and S2 in both seeds], times (1 + ρ). "Remaining" is $900 minus the billed phase-1b spend to date (pilot spend counts to phase 0). The rule fires if the forecast > remaining; the researcher may then raise the 1b cap by up to about $170 (D27) or re-scope.
- If any rule fires, Claude proposes stopping or re-scoping, and the researcher decides. If the leg continues, the run order follows D18.

### 10.4 G2 (Oct 21)
> G2: kill the ARC leg if the S0→S4 gap is < 10 RHAE points. Overall kill if H1 *and* H2 are inside equivalence bounds *and* the ARC gap is dominated by a mechanism with no provider-neutral analogue: write a short note (survival accounting + ARC path table) and skip Phase 2. Scoop check: if a per-component ARC ablation has appeared, the ARC table stops being the headline. (PLAN §11)

**Operational.**
- **Kill criterion 4:** G = R̄_S4 − R̄_S0 over the 8 counted units (H4) is < 10.
- **Kill criterion 5** requires all three of the following:
  - "H1 inside equivalence bounds" means H1's kill condition holds (§3 H1). See D38.
  - "H2 inside equivalence bounds" means H2's equivalence condition holds (§3 H2). If H2 moved to open weights (kill criterion 1), the condition is read on that run.
  - "Dominated" is defined by D30.

**Decision.** "H1 inside equivalence bounds" is read as H1's kill condition: Δ_H1 < 10pp and the upper bound of its 90% CI < 15pp. (decided 2026-10-01, D38)

*Why:* PLAN gives H1 a kill rule but no separate equivalence rule, and the kill rule is the closest bound it states.

**Decision.** "Dominated by a mechanism with no provider-neutral analogue" means **σ_replay ≥ 2/3** as a point estimate. σ_replay is the share of the S2→S4 step, which bundles native replay with the native item format and is the only step with no provider-neutral analogue. (decided 2026-10-01, D30)

*Why:* at 2/3, the provider-neutral steps (loss policy plus notes) carry at most a third of the gap. A bar of 1/2 would skip phase 2 on Prediction B alone, and a CI-based bar could not fire with 8 units.

### 10.5 Scoop rule (kill criterion 6)
> **Any time.** A per-component ablation of ARC's gap appears (ARC Prize, OpenAI or others) → the ARC table becomes supporting material. Lead with PersistGym + StateCarry. (PLAN §14)

**Decision.** "A per-component ablation" is a public document (paper, preprint, blog post, results page or merged PR) that reports ARC-AGI-3 scores, on any model, for at least two harness configurations differing in exactly **one** of {loss policy, notes instruction, reasoning replay}, under ARC's harness or a fork of it. OpenAI's Jul 29 post (combined effect only) does not qualify. The scoop search is re-run at each gate (CLAUDE.md). (decided 2026-10-01, D31)

*Why:* a narrow trigger fires only on work that actually decomposes the gap. Partial ablations are cited and positioned against, as PLAN §15 plans. One such signal is already logged: an unmerged ARC harness branch adding the notes sentence to the Adapter prompt, with no published scores (`results/decisions.md`, 2026-10-01).

### 10.6 3-game fallback
> How a game is dropped under the 3-game fallback (seeded, not by cost). (PLAN §16.5)

**Decision.** If the 3-game fallback is triggered, **drop `perm[3]`**, the last path game in the beacon-seeded order (§7.3). If it has already been run, its runs are reported as exploratory and it stays a dev game. Otherwise it is set aside (neither path nor held-out) unless the researcher decides otherwise at G2. H4, Checkpoint C and kill criterion 4 then use the 3 remaining path games (6 units instead of 8), with the same thresholds; Checkpoint C's cost rule then counts 18 remaining runs instead of 24, and its error rule 6 seed-1 runs instead of 8. (decided 2026-10-01, D32)

*Why:* a position-based drop is fixed by the beacon after the freeze and cannot be steered by results or costs, which meets PLAN §16.5's "seeded, not by cost".

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

For criterion 2, "the chosen tier" is the standard tier (D21), the forecast follows D27, and the Checkpoint C re-check follows §10.3.

## 11. Pilots and pilot blinding (PLAN §16.3, §16.5)
> **Pilot blinding:** pilots report only validity levels, pooled tokens, errors, latency and cost; never per-arm success, per-arm reasoning tokens (H2's token outcome) or per-config ARC level progress. Pilot templates use a disjoint seed range. (PLAN §16.5)
>
> **Truncated ARC pilot** on one drawn path game replaces the FT09 full-run pilot: S0 and S4 to 50 actions, S1 to its first compaction plus 5 turns, S2 to 30 actions. (PLAN §16.3)
>
> Pilot runs are excluded from all analyses. (PLAN §11)

**Block 1 contents** (PLAN §16.2, as changed by D21): the OpenAI `reasoning.context` echo check (~$0.35); the replay-use probe (~$2); a Gemini payload acceptance check on the standard tier (≤ $1; the Flex latency probe is dropped); the truncated ARC pilot on `perm[0]` (D17), on the standard tier; luna and sol pilots, and the validity runs. The block-1 forecast is $53.90 billed (`results/cost_model/20261001T203318Z/optA_approval_blocks.csv`).

**Operational.**
- Pilot reports come from committed scripts that output only the allowed fields: validity levels; pooled tokens (summed over arms); errors; latency; cost; echo-match rate; for ARC, cost per action, tokens per action, compaction occurrence and exit status.
- No script, person or agent computes per-arm success, per-arm reasoning tokens or per-config ARC level progress (levels cleared, RHAE) from pilot data. Raw pilot transcripts stay in `results/raw/` and are not read for those quantities.
- **As implemented** (PR #13; a technical choice accepted by the researcher on 2026-10-01): pilot episode outcomes (`episodes.jsonl`: need correctness, need-phase tokens, usage, lookups) are written only to the gitignored `results/raw/<experiment>/<run_id>/`. The committed run folder holds `meta.json` (with reasoning tokens set to null) and `summary.json`, both built from an allowlist. Each pilot run's `costs.csv` row leaves `reasoning_tokens` empty.
- **Known limit:** CLAUDE.md requires one `costs.csv` row per run, and each row still carries that run's output tokens, calls and cost, which approximate the withheld quantities. Blinding is therefore partial, and this is reported.
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

**Forecasts at this draft** (billed; Gemini on the standard tier; OpenAI on Flex with cache writes; 1k output tokens per PersistGym call; `results/cost_model/20261001T203318Z/`, PLAN §17.2). These are forecasts from one published run per game and harness and from PLAN's token assumptions, not measured costs.

| Item | USD | Source file |
|---|---|---|
| Block 1, pilots | 53.90 | `optA_approval_blocks.csv` |
| Block 2, seed-1 S0+S4 (with the 20% reserve) | 202.97 | same |
| Block 3, commitment (24 ARC runs and reserve; PersistGym main sweep) | 1,073.32 | same |
| of which `3-arc` (Google) / `3-persistgym` (OpenAI, central size: T_d = 120, 8 luna cells) | 608.90 / 464.43 | same |
| Block 4, phase 2 | 1,233.19 | same |
| Blocks 1-3 (through G2) | 1,330.19 | same |
| Phase 0 / 1a / 1b / 2 | 24.15 / 494.18 / 811.86 / 1,233.19 | `optA_totals_by_phase_payee.csv` |
| Total through phase 2 | 2,563.38 (Google 2,054.00, OpenAI 509.37) | same |
| Total at 2k / 3k output tokens per call; with ARC at no-cache list (1k) | 2,779.00 / 2,994.16; 3,123.20 | `option_a_summary.md` |
| Phase 1a at T_d = 120: 8 luna cells; luna's 4 replay-off cells only | 494.18 (headroom 5.82); 413.02 | `optA_sizing_1a.csv` |
| Phase 1a at 2k / 3k output tokens per call (T_d = 120, 8 luna cells) | 702.01 / 909.37 | same |
| luna controls (D36): 880 restated-at-need F-0 episodes + 440 single-turn prompts | 18.72 (17.29 + 1.43) | `option_a_summary.md` |
| Phase 1b at the G0 rule (§10.1); at the Checkpoint C rule | 811.86 (headroom 88.14); 1,042.92 | `optA_forecasts.csv` |
| Phase 2 central (headroom); at the Checkpoint C rule | 1,233.19 (16.81); 1,704.09 | same |

The luna control line replaces PLAN §12's 1,600 single prompts, which came to $5.20. Phase 1a by T_d is in §4.2.

**Hard caps** (approved by the researcher on 2026-10-01; PLAN §17.3; `PHASE_CAPS` in `common/costs.py`, PR #18, merged). Claude stops and asks the researcher before any of them is exceeded.
- **Phase 0:** $100.
- **Phase 1a (PersistGym):** **$500** (was $450). The central size (T_d = 120, 8 luna cells) is forecast at $494.18, $5.82 under it. Under the §4.2 sizing rule with the order of §0.3, line 9, luna's exploratory replay-on cells give way first: at 1k output tokens per call and the simulated variance, sol gets T_d = 150 and luna no replay-on cells ($481.34); at 2k, T_d = 90; at 3k, no T_d fits without a cap raise (§4.2). [Amended 2026-10-02, see §17.2]
- **Phase 1b (ARC path):** $900. At Checkpoint C the researcher may raise it by up to about $170 (D27).
- **Phase 2 (StateCarry):** **$1,250** (was $950; D24, and the researcher's follow-up to A2). The central forecast with reserves is $16.81 under it (§8).

**Approval lines** (PR #13). Each block's approval is one line that the researcher adds to `results/decisions.md` and merges to `main`. Its grammar, as an indented template with placeholders:

```
    approved_block: <name> | experiments: <exp1>,<exp2>,... | max_usd: <amount>
```

- The line starts at column 0, with exactly this spacing, outside any code block or HTML comment. `<name>` matches `[A-Za-z0-9._-]+`. The experiments are budget experiments listed in `common/costs.py` (or start with `ext_`), comma-separated with no spaces and no repeats. `<amount>` is a positive decimal number of US dollars, with no `$`, sign, exponent or thousands separator.
- The paid guard (`common/approval.py`) refuses unless the same line is on `origin/main` (fetched first), in `HEAD` and in the working tree. Removing, changing or commenting out the line in any of the three revokes the approval. One line per block. Block 3 has two lines, one for `3-arc` and one for `3-persistgym` (§0.3, line 15).
- **Block spend** is the sum, over `costs.csv` rows tagged `approved_block=<name>;`, of each row's spend. A run is refused if block spend + its planned spend > `max_usd`, and the phase cap is checked the same way.
- Only the researcher adds approval lines. Approving the caps approves no block.

**Spend measure.** Since PR #19 (merged on 2026-10-01; §0.3, line 11), the guard counts each row at its **billed estimate**, and at its list cost only when the billed estimate is empty; a row with neither is refused. Block spend, the phase caps and a PersistGym run's own in-run stop all use this one measure (`common.costs.spend_usd`), which is the basis of every cap and forecast here (D23). The D22 per-run guard inside the ARC harness is different: it counts no-cache list cost (§7.7).

**Paid-run procedure.**
- **Paid runs, one at a time per stream** (§0.3, lines 14 and 15; line 15 changed by the researcher on 2026-10-01).
  - **Until the per-stream locks land** (before block 3), one paid run at a time overall: no paid run, ARC or PersistGym, starts while another is going. Both launchers enforce this with one lock shared by every checkout (`common/paidlock.py`; the ARC launcher since PR #21, the PersistGym launcher since PR #24; §0.3, line 14), taken before the spend checks so that two runs cannot both pass them.
  - **ARC stream:** one run at a time, in the D18 order: SEED + 2 in block 2, and SEED + 3 in block 3, back to back (§7.4). For block 3, "back to back" replaces D18's 72 h start window. Back to back at the published durations of the path games, block 3's 24 ARC runs (S1 and S2 in both seeds, S0 and S4 in seed 2) take about 60 h with S1 and S2 at the S0/S4 midpoint and about 79 h with S1 and S2 at S0's duration: the four published S0 runs sum to 14.7 h and the four S4 runs to 5.3 h (`duration_s` in `results/arc_public_ops/20261001T185155Z/recordings_per_action.csv`). With S1 and S2 at S0's duration, the last run would start more than 72 h after the first in every order, even with no gaps between runs. These are published durations, not our configs' measured ones.
  - **PersistGym stream:** one run at a time. A run may play up to 16 episodes in parallel; this changes no payload and no cost, and the run reserves spend for the episodes in flight, so it never exceeds its planned spend (§4.6).
  - **Both streams at once.** Once the per-stream locks land (as $0 pull requests, before block 3, together with the parallel episodes), the ARC stream (Gemini) and the PersistGym stream (OpenAI) may run at the same time, each with its own paid-run lock and its own approval blocks. Block 3 is approved as two blocks: `3-arc` (the 24 ARC path runs and their reserve) and `3-persistgym` (the PersistGym main sweep). *Operational:* where both streams spend under one cap (phase 2), a run's planned spend counts against that cap from its start until its `costs.csv` row is written, so two overlapping runs cannot both use the same room.
- **Hold after a `COST_CAP`** (§0.3, line 12, changed by the researcher on 2026-10-01; §7.7). Any paid run that reaches its $120 run guard ends `COST_CAP` and places a hold: no further paid run starts in either stream until the researcher merges a line into `results/decisions.md` that clears the hold and names the run. Both launchers are to refuse while a hold stands. The code, including the line's grammar, lands as a $0 pull request before block 2.
- **ARC runs** go through `arc/run_path.py` only (PR #21), from a checkout of `origin/main`, with `PERSISTGYM_ALLOW_PAID=1` set for that one command. One invocation is one game × one config × one seed (experiments `arc_pilot` and `arc_path`), or one payload acceptance check of the four profiles (`gemini_probe`). It refuses, with exit code 2 and before anything is spent:
  - a game other than FT09, SB26, R11L and CD82 (so no pilot or path run on SP80, VC33 or TN36), a config other than S0, S1, S2 and S4, or a `statecarry_*` experiment (phase 2 is not supported yet);
  - a counted run that is truncated or planned below $120 (D22);
  - a profile that does not request the standard tier, prices that differ from the dated price table, or a date after 2026-12-31;
  - a missing `GOOGLE_API_KEY`, or for a game run a missing `ARC_API_KEY` (presence is checked; values are never printed or written);
  - a paid-run lock held by another run, or the last paid run's `costs.csv` row missing from this checkout (since PR #24 matched on its run ID and its `timestamp_utc`);
  - a failed paid guard: no valid approval line for the block and experiment, block spend + planned spend above `max_usd`, or no headroom under the phase cap;
  - PREREG.md uncommitted, not the same blob in `HEAD` as on `origin/main`, or not frozen (§0.4). The lock, ledger, guard and PREREG checks are one shared function, `common.approval.require_paid_run`, which the PersistGym launcher runs too (PR #24);
  - `arc/config_freeze.json` not the same blob in `HEAD` as on `origin/main`, or the record the run loaded differing from it (PR #23);
  - a freeze record whose four profile hashes, patch-series SHA-256 or upstream pin (or patched commit or tree) differ from the §7.1 tables of the frozen PREREG.md on `origin/main`, or a §7.1 without filled tables (`arc/prereg_freeze.py`, PR #23). So a config change after the freeze needs a dated amendment that updates the §7.1 tables themselves (A-cfg, §7.1, §17);
  - `arc/patches` not the same tree in `HEAD` as on `origin/main`, or patch files on disk that are not exactly the committed `.patch` files (PR #23);
  - patch files, a patched commit or tree, or a resolved profile hash that differ from the freeze record (§7.1).
- **Every paid run is accounted for,** even after a crash or Ctrl+C: one `costs.csv` row tagged `approved_block=<name>;`, with list and billed estimates and the median seconds per call, and a `meta.json` with the config hash, both exit fields, the reported model strings and the tier requested and served. If that accounting fails, the lock stays held until the row is added by hand.
- **$120 of room per counted ARC run** (kept at sign-off, §0.3, line 12). A counted run's planned spend is D22's $120, so it needs $120 of room both in its block's `max_usd` and under the 1b cap when it starts, whatever it is expected to cost. The last runs of a block are refused once less than $120 is left, so an ARC block's `max_usd` must leave that room.
- **PersistGym runs** go through `harnesses/cli.py` only (`run`, `probe-echo`, `probe-replay`), under the same approval line and guard, with `PERSISTGYM_ALLOW_PAID=1` set. Since PR #24 a paid command runs the same shared checks as the ARC launcher (`common.approval.require_paid_run`; §0.3, line 14), and refuses with exit code 2, before anything is spent:
  - a paid-run lock held by another run, ARC or PersistGym, or kept by a run whose spend could not be written to `costs.csv`. The command takes the lock after its argument checks and before any spend check, and holds it for the whole command; a probe holds one lock across all its models;
  - the last paid run's `costs.csv` row missing from this checkout (matched on its run ID and its `timestamp_utc`), or a `costs.csv` that cannot be read;
  - a failed paid guard, as for ARC runs;
  - PREREG.md uncommitted, not the same blob in `HEAD` as on `origin/main`, or not frozen (the rule of `common/prereg.py`, which the draw script and the ARC launcher use too; §0.4).

  If a run made calls whose `costs.csv` row cannot be written, or whose accounting never ran, the lock stays held, with the reason in the lock file, until the row is added by hand and the lock is removed.

**Operational.**
- Every paid call batch is logged to `results/costs.csv` (CLAUDE.md). The file is summed and compared with the cap before each block. Spend to date when this version was written: $0 (`results/costs.csv` has no rows; `main` at `2b0a958`).
- Provider-side spend limits back up the stop-and-ask rule (PLAN §16.1); the researcher has set them for the OpenAI and Gemini projects (`results/decisions.md`, 2026-10-01).
- Paid calls are made only under a frozen (non-draft) PREREG version.
- All Gemini ARC runs finish before 2026-12-31 (PLAN §8.3, §11).

## 13. Exclusions, errors and deviations

**Decision.** PersistGym episode handling:
- **OpenAI echo mismatch:** the episode is excluded (CLAUDE.md). If a cell exceeds 5%, the run stops and the researcher is told. [Amended 2026-10-02, see §17.2]
- **Transport failure after the harness's retries** (HTTP 429/5xx, timeouts): the episode is re-run once with the same template and seeds. A second failure means exclusion. Counts are reported per cell.
- **Content failures** (unparseable, invalid or refused actions; an `incomplete` response at the need step) score 0 and are not re-run.
- Episodes are analysed by their **assigned** cell. `S_planned` ≠ `S_verbatim` mismatches are reported, not excluded (but see the bug stop in §2.8).

(decided 2026-10-01, D33)

*Why:* this follows CLAUDE.md's echo rule and keeps the cells balanced. Failure counts are reported per cell, so informative missingness in long-context cells stays visible.

**As implemented** (PR #22, §6): an `incomplete` step response is an invalid action at any step, whatever its reason. At the need step it is the content failure above. At a routine step it counts against `routine_acc` and the episode continues. Neither case is excluded or re-run.

**ARC runs:** errors follow §7.5 and the cost guard follows §7.7.

**Deviations** from this PREREG are logged in `results/decisions.md` with the date and reason, and are listed in every write-up.

## 14. Extensions (PLAN §9)
Extensions are **not** pre-registered here, apart from the two rules carried over below. Each one needs a dated amendment fixing its settings before its first paid run.
- **E1** (open-weights replay): if it moves into the MVP under kill criterion 1, H2's predictions, falsification and equivalence rules apply unchanged to Qwen3.6-27B with `preserve_thinking` on vs off. The serving settings are fixed by amendment.
- **E3** (Terminal-Bench cost win), as written: "Pre-registered win: success within ±3pp and at least 15% fewer tokens." (PLAN §9)
- E2, E4, E5 and E6 have no pre-registered predictions.

## 15. What this pre-registration does NOT claim
- **It is not a model comparison.** Nothing here ranks models or vendors, and no result is stated as "model X beats model Y". Figures plot effects against task properties.
- **The ARC results are conditional and narrow.** They concern 4 public games chosen by a rule (published gap ≥ 20, both published runs ≤ $60, a normal Standard ending), so they are games where the Adapter is known to help. They cover Gemini 3.8 Flash at high thinking on the Interactions API and the standard tier, measured in a 2026 window with no dated snapshot. They say nothing about the Semi-Private or private sets, about other efforts or models, or about frontier models.
- **The held-out games are not a random sample.** They come from a separate rule that ranks by published cost, and each exceeds the $60 filter on at least one harness, so path and held-out games are not exchangeable.
- **The path decomposition is order-dependent and descriptive.** The S2→S4 step bundles native replay with the native item format, so no share is attributed to replay alone. With 8 game-seed units, no significance is claimed.
- **It does not explain ARC's published gap.** The published runs are one-seed screens, may have used a different API surface, and include early endings. Our runs re-measure the gap; they do not audit those runs. Our S1 and S2 have no published counterpart, and our S0 requests thought summaries that ARC's Standard run probably did not (§7.1).
- **PersistGym is synthetic.** Its results are not claimed to transfer to coding agents, ARC or real tasks without separate evidence. Window effects at S = 0 are mechanical and are not findings in themselves.
- **H2 is narrow.** It runs at medium effort (D13), which may understate the value of replay relative to the high-effort ARC leg, and its observed-fact check covers far distance only (D11). [Amended 2026-10-02, see §17.2]
- **Opaque replay is not inspected.** What a model "sees" in encrypted reasoning items cannot be observed. Toggle validity rests on the echoed field and the replay-use probe.
- **Equivalence is not absence.** "Inside equivalence bounds" means the effect is within the stated bounds at the stated confidence. It does not mean there is no effect, and an underpowered result is called inconclusive. At the central sol size, the H2 equivalence test has well under 0.80 power (§4.2). [Amended 2026-10-02, see §17.2]
- **StateCarry is not claimed to be new as an idea.** Ledger-style state and reasoning replay already exist (Ledger 2608.00808, the Kaggle "Duck" baseline, public Kaggle ablations). The claim is limited to closing the Standard-to-Adapter gap under ARC's rules on held-out games. It is not a state-of-the-art claim, and a coding success win would not be new.
- **Costs are period-specific.** They are forecasts at the prices checked on 2026-09-29/30. Gemini 3.8 Flash prices double on 2027-01-01.
- **H5 on published runs is observational and not blind.** It cannot separate depth from game difficulty beyond game fixed effects. Per-game scores were seen before this pre-registration, and the operational slice revealed where each published run ended (§3 H5). Only H5 on our own runs is a test on unseen data.

## 16. Decision register
All 39 items were decided by the researcher on 2026-10-01. The text above carries each decision where it applies, marked "(decided 2026-10-01, D*n*)". The researcher answered the sign-off list the same day (§0.3); the rows below name the lines that concern them, and the two changed lines (12 and 15) follow their decisions in paragraphs headed "Changed at sign-off".

| ID | Section | Item | Outcome |
|---|---|---|---|
| D1 | §2.3 | Observed fact | Accepted as drafted: one key-value binding; the value string appears nowhere else except the options, lookups and the restated control; 2 distractor bindings whose values are never options or clues |
| D2 | §2.4 | Derived fact | Accepted, with clustered options so that no proper subset of clues narrows the options; partial memory added to the $0 validity gate; m split exactly 5/5 per 10-template block |
| D3 | §2.5 | Lookup | Accepted: generic lookup over any earlier key, whole-word match; one extra step; cap of 3; a 4th lookup answers "lookup unavailable" (how "no such record" and a second over-cap lookup count was confirmed at sign-off, §0.3 line 7) |
| D4 | §2.6 | Success scoring | Accepted: first non-lookup action scored, invalid output scores 0; letter or value accepted; parser fallback to the last `verb(arg)` |
| D5 | §2.7 | Near and far | Accepted as drafted; the system prompt counts toward W everywhere (leaving the notes sentence out of W was confirmed at sign-off, §0.3 line 6) |
| D6 | §2.8 | Survival | Accepted: whole-word match on the value or all clues; replayed reasoning not counted in W; bug stop; 2% re-tuning trigger |
| D7 | §2.9 | Seeds and repeats | Main seeds from 0 in complete blocks of 10, so sol's T_d is a multiple of 30; validity and pilot ranges as drafted; the 10% repeat subset kept on both luna and sol (the luna-only change was rejected); primary analysis on repeat 0 (controls get the repeat: confirmed at sign-off, §0.3 line 10) |
| D8 | §3 H1 | H1 token reading | Changed: need-phase tokens are the primary reading; episode-total and literal ratios are secondary |
| D9 | §3 H2 | H2 token measure | Accepted as drafted; the observed-fact check covers far cells only (D11) |
| D10 | §3 H3 | H3 control | Accepted as drafted |
| D11 | §4.2 | sol design and sizing | Changed: sol runs derived-far (T_d) and observed-far (T_o = T_d/3) cells only; central T_d = 120; T_d a multiple of 30, raised up to 210 (the researcher's follow-up to A2) only before the sol main sweep and before any H2 outcome, with a 1a cap raise first if the cap does not afford it; 0.80 target kept, else "inconclusive" (which cells get 1a's money first was confirmed at sign-off, §0.3 line 9) [Amended 2026-10-02, see §17.2] |
| D12 | §5 | Summary cells | Accepted, plus: Σ-cell survival is measured only, `compacted_between` logged and reported, Σ cells in no confirmatory test |
| D13 | §6 | OpenAI settings | Accepted as drafted: medium effort, standard mode, explicit context, 32,000 output cap, Flex. As implemented (PR #22): the cap is sent on every step, summary and probe request, and an `incomplete` step response is an invalid action at any step (0 at the need step), whatever its reason, replayed as returned [Amended 2026-10-02, see §17.2] |
| D14 | §7.2 | ARC games | Changed (option A): path games FT09, SB26, R11L, CD82 (normal Standard ending required); held-out SP80, VC33, TN36 by a cost-ranked rule; no draw of games |
| D15 | §7.3 | Draw seed | Changed: seed from the first NIST beacon pulse at least 10 minutes after the freeze commit, with a drand fallback; it orders the 4 path games (the drand fallback when NIST cannot be reached was confirmed at sign-off, §0.3 line 5) |
| D16 | §7.3 | Third held-out game | Replaced by D14's held-out rule (VC33 is in; RE86 is out) |
| D17 | §7.3 | Pilot game | Accepted: the first game of the beacon-seeded order; never a held-out game |
| D18 | §7.4 | Run order | Accepted as drafted, with the beacon seed. Changed at sign-off (§0.3 line 15): the 72 h start window for block 3 is replaced by "back to back, one at a time, in the SEED + 3 order"; both run orders are unchanged |
| D19 | §7.5 | Error re-runs | Accepted; `TIME_BUDGET` follows D20 (reading `agent_exit_reason` rather than `exit_reason`, and re-running a run whose scorecard cannot be read, were confirmed at sign-off, §0.3 lines 1 and 2) |
| D20 | §7.5 | `TIME_BUDGET` | Changed: final as is, unless a provider-latency incident (median seconds per call over 2× the config's earlier runs; how that median is taken was confirmed at sign-off, §0.3 line 3) |
| D21 | §7.6 | Service tier | Changed: Gemini standard tier for all ARC runs, fixed now; Flex probe dropped; per-run 12 h warning rule |
| D22 | §7.7 | Cost guard | Accepted: $120 per run at list; `COST_CAP` final and reported; trade-off text corrected. Changed at sign-off (§0.3 line 12): the guard stays in the launcher and the $120-of-room rule stays; a run that reaches the guard places a hold: no further paid run starts, in either stream, until the researcher clears it with a merged line in `results/decisions.md` |
| D23 | §8 | Cost basis | Accepted: billed estimate primary, list reported alongside, re-runs excluded |
| D24 | §8 | StateCarry gates and budget | Option B: G3 runs as their own budget line; all 3 held-out games committed, no 2-game cut; held-out S0+S4 first with a gap ≥ 10; phase-2 cap raised to $1,250 (the researcher's follow-up to A2; A2 first proposed $1,150); win/partial/negative bands |
| D25 | §9.1 | Bootstrap and GLM details | Accepted, plus cluster-robust SEs with the G/(G − 1) factor only |
| D26 | §9.4 | Holm family | Accepted: 4 one-sided tests; model estimate must agree; worst-step power quoted from the committed simulation |
| D27 | §10.1 | Cost forecast | Rule 1: G0 prices S1/S2 at the S0/S4 midpoint; a conservative check at Checkpoint C; a 1b cap raise of up to about $170 may be requested there |
| D28 | §10.1 | Re-run reserve | Accepted: 20% |
| D29 | §10.1 | Replay toggle rule | Accepted as drafted [Amended 2026-10-02, see §17.1] |
| D30 | §10.4 | "Dominated" | Accepted: replay share ≥ 2/3 |
| D31 | §10.5 | Scoop trigger | Accepted: a public one-component ARC ablation; scoop search at every gate |
| D32 | §10.6 | 3-game fallback | Accepted: drop the last game of the beacon-seeded order (what happens to the block-3 run order was confirmed at sign-off, §0.3 line 4) |
| D33 | §13 | PersistGym errors | Accepted as drafted |
| D34 | §3 H4 | H4 readings | Accepted as drafted |
| D35 | §3 H5 | H5 details | Accepted as drafted |
| D36 | §4.6 | Run matrix | Changed: single-turn control on non-recoverable cells only; restated-at-need as full F-0 episodes; sol on the D11 cells (sol's optional replay pairs on the D11 cells were confirmed at sign-off, §0.3 line 8) |
| D37 | §10.1 | Other G0 conditions | Accepted, on the standard tier, with the S1/S2 patches' snapshot tests required |
| D38 | §10.4 | H1 in kill criterion 5 | Accepted: read as H1's kill condition |
| D39 | §4.3, §4.4 | Controls and validity | Accepted, with D2's partial-memory heuristics added to the per-cell baselines. As implemented (PR #25, generator 0.3.0): the withheld control replaces each fact and clue binding with an equal-length binding for a stand-in entity whose values are never an option, clue or distractor value; the rule sentence, which names no entity, is kept verbatim |

## 17. Amendment log
Amendments made: R1 (2026-10-02, §17.1) and R2 (2026-10-02, §17.2), at the end of this file. Pre-declared amendments, each merged by PR before the event it guards:
- **A-cfg:** only if the block-1 pilot forces an ARC config change after the freeze record (§7.1) is filled; merged before the first block-2 run. It writes the new values into the §7.1 tables themselves and is merged together with the regenerated `arc/config_freeze.json`: the ARC launcher reads §7.1, so a table added only to this log would make every paid ARC run refuse (PR #23).
- **A-SC:** the StateCarry code commit and config hash, before any G3 evaluation run and again before any held-out run (§8).
- **A-judge:** the LLM-judge model and prompt, before failure labelling (§9.7).

Values set by a pre-registered rule (W, v, template counts including T_d and T_o, the draw output) are recorded in `results/decisions.md`. They are not amendments.

**Draft history** (before freeze; not amendments):
- 0.1-draft (2026-10-01): first draft from PLAN §4-§10 and A1, with 39 decision items.
- 0.2-draft (2026-10-01): the researcher's decisions on D1-D39 written in; text aligned with the code in PRs #13-#17 (seed ranges from 0, clustered options, equal addends, lookup messages, system prompt in W, the `LOOKUP RESULT` marker, patch 0016, `compacted_between`, the standard tier, `agent_exit_reason`, approval lines); plain-language summary added.
- 0.2-draft, review fixes (2026-10-01): D22's trade-off text as decided, with per-game numbers; T_d a multiple of 30 (D7); `n_lookups` and `n_lookups_unavailable` defined; the guard's spend measure on OpenAI Flex; five more sign-off points for gaps the decisions did not cover (§0.3).
- 0.3-draft (2026-10-01): brought to sign-off. The researcher's follow-ups to A2 written in: phase 2 cap $1,250 (D24) and T_d ceiling 210, always a multiple of 30 with T_o = T_d/3 (D11; the T_o = 67 exception is gone). Caps and forecasts from A2's cost run `results/cost_model/20261001T203318Z/` (luna controls per D36, 1a $494.18 against $500). ARC config freeze record filled (§7.1; patches 0001-0017, PR #21). Paid-run procedure added (§12). §0.3 is now a numbered sign-off list with recommendations, and the freeze steps moved to §0.4. No hypothesis, prediction or threshold changed; the blockquotes are unchanged.
- 0.3-draft, review fixes (2026-10-01): sign-off line 15 added (one paid run at a time against D18's 72 h window for block 3, with published-duration sums in §12); line 9 restated plainly, since its order already binds at 1k output tokens per call, and §4.2, §4.6 and §12's phase 1a text made consistent with it; line 12 states the $120-of-room consequence for the 1b cap; §0.4 says how a changed §0.3 line is written in; the ARC launcher needs `ARC_API_KEY` only for a game run; register rows name their sign-off points. No hypothesis, prediction, threshold or blockquote changed.
- 0.3-draft, sign-off answers (2026-10-01): the researcher's answers to §0.3 written in. Lines 1-11, 13 and 14 confirmed as recommended. Line 12 changed: the guard and the $120-of-room rule stay, approvals stay per block, and a run that reaches its $120 guard places a hold: no further paid run starts until the researcher clears it (§7.7, §12). Line 15 changed: block 3's ARC runs go back to back, one at a time, in the SEED + 3 order, replacing D18's 72 h window; PersistGym runs go one at a time, with up to 16 episodes in parallel; the ARC and PersistGym streams may run side by side, each with its own lock and approval blocks, and block 3 is approved as `3-arc` and `3-persistgym` (§4.6, §7.4, §12). Notes on PRs #18-#21 updated now that they are merged (§0.1, §0.4, §7.1, §12). No hypothesis, prediction, threshold or blockquote changed. The freeze commit that follows changes only the version line, the status line and the sign-off table (§0.4, step 3).
- 1.0, text update before the merge of PR #4 (2026-10-01): the text follows PRs #22, #25, #24 and #23, which the researcher merges before this PR (§0.1; §0.4, step 1 and the sign-off table). D13 as implemented: the 32,000 output cap on every OpenAI step, summary and probe request, and an `incomplete` step response as an invalid action at any step (§2.6, §5, §6, §13, §16). D39 as implemented: stand-in bindings in place of each fact and clue binding, with the rule sentence kept, generator 0.3.0 (§2.4, §4.3, §4.4, §16). The PersistGym launcher's lock, ledger and frozen-PREREG checks (§0.3 line 14, §0.4, §12). The ARC launcher's checks of the freeze record and patches against `origin/main` and the §7.1 tables, so that A-cfg updates §7.1 itself (§7.1, §12, §17). Their merge commits go to `results/decisions.md` after the merges. The version and status lines are unchanged. No hypothesis, prediction, threshold, decision or blockquote changed.
- 1.0, review fixes (2026-10-01): the signed-off sentences of §4.3 (the withheld control "replaces every evidence binding with a distractor binding of equal token length") and §6 (an `incomplete` response at the need step is a content failure) are back verbatim, with the implementation after each in text marked "As implemented"; `persistgym/DESIGN.md` §12 and `harnesses/DESIGN.md` §7.5 quote them. §6: an incomplete turn's empty reply adds nothing to W, but its observation still counts. §4.3: "no scripted observation" names the target. No hypothesis, prediction, threshold, decision or blockquote changed.

### 17.1 Amendment R1 (2026-10-02): D29 replay-use probe redesign
**Status.** Proposed by Claude on 2026-10-02 after the researcher chose option A: pre-register a redesigned probe, then run it. It takes effect when the researcher merges the pull request that adds it, and that merge adopts the pass rule below. The version line and the "Frozen" status line are unchanged.

**What it changes.** D29's condition 2 (§10.1): the replay-use probe and its pass rule. The D29 text in §10.1 stays as frozen, with a pointer here. Nothing else changes: no hypothesis, prediction, other threshold, other decision or blockquote.

**Reason.**
- D29's probe learns the privately picked number from the turn-1 reasoning summary. In block 1 (2026-10-02; 20 trials per arm on each model; runs `results/replay_probe/20261002T034558Z-replay-gpt-6.1-sol` and `results/replay_probe/20261002T034914Z-replay-gpt-6-luna`), the summaries almost never named a number. sol's turn-1 summaries were empty in 40 of 40 trials, and luna's in 32 of 40; only 2 of luna's 40 named exactly one number. Both models reasoned briefly in turn 1 (medians of 15.5 to 16.5 reasoning tokens on sol and 24 to 26.5 on luna). So 0 sol trials and 2 luna trials were scorable, against the 20 per arm that D29 needs. More trials would not fix this.
- The new probe does not need a summary. It asks the same question twice from the same state and checks whether the two answers agree.
- **Timing.** This amendment is written **after** seeing the original probe's results, which are reported below as descriptive numbers only, and **before** any run of the new probe. No data from the new probe exists as it is written.

**Descriptive results of the original probe** (block 1; not a test of anything; from `uv run python -m harnesses probe-summary` on the two runs above, which reads each run's `trials.jsonl` and raw transcript; 20 trials and 60 responses per arm):

| | sol, `all_turns` | sol, `current_turn` | luna, `all_turns` | luna, `current_turn` |
|---|---|---|---|---|
| Turn-1 summary empty | 20 | 20 | 17 | 15 |
| Turn-1 summary names exactly one number | 0 | 0 | 1 | 1 |
| Scorable under D29 | 0 | 0 | 1 | 1 |
| Exact recalls among scorable trials | none scorable | none scorable | 0 of 1 | 1 of 1 |
| Turn-3 reply is a three-digit number | 20 | 0 | 18 | 17 |
| Numbers given in turn 3 | 583 ×16, 683 ×2, 628, 684 | none | 583 ×17, 617 | 583 ×15, 417, 482 |
| Echoed `reasoning.context` equals the request | 60 of 60 | 60 of 60 | 60 of 60 | 60 of 60 |
| Visible leaks; incomplete responses | 0; 0 | 0; 0 | 0; 0 | 0; 0 |
| Turn-1 reasoning tokens (min / median / max) | 12 / 15.5 / 21 | 12 / 16.5 / 27 | 20 / 24 / 33 | 20 / 26.5 / 37 |

- All 20 of sol's `current_turn` turn-3 replies said it had no number to give (for example "I didn't actually pick a number."). Of luna's 8 non-empty turn-1 summaries, 2 named exactly one number (583 both times), one named three (100, 583 and 999, `current_turn`) and 5 named none. luna's turn-3 replies without a number were short statements such as "I can't provide it." or "I didn't retain a number."
- All 240 responses were requested with `reasoning.summary: "auto"` and echoed `"detailed"`.
- **What these numbers do not show.** sol's contrast (a number in 20 of 20 `all_turns` trials, in 0 of 20 `current_turn` trials) fits replay use, but with no known pick it cannot tell recall of a pick from a favourite number: luna, whose `current_turn` arm cannot see the turn-1 reasoning, still answered 583 in 15 of 20 `current_turn` trials. These numbers neither verify nor reject either model's toggle.

**The new probe: fork consistency.** It runs as `uv run python -m harnesses probe-replay --design fork` (`harnesses/probes.py`; `harnesses/DESIGN.md` §9.3). The experiment name stays `replay_probe`, and the original design stays available, unchanged. Each trial:
1. **The list.** A fresh list of L = 20 distinct three-digit numbers (100-999) from a per-trial seeded generator: `random.Random(seed).sample(range(100, 1000), 20)`, then shuffled by the same generator. The seed is 290,000 + the attempt index (0-39). This seed stream is reserved for the probe and lies outside every template range of §2.9. Attempt *i* shows the same list in both arms and to both models.
2. **Turn 1** (user) shows the list and asks the model to privately pick one number from it at random, not to write the number or any hint about it, and to reply only "ready". Exact text: "Here is a list of three-digit numbers:" and a line break, the 20 numbers separated by ", ", a blank line, then "Privately pick one number from this list at random. Do not write the number or any hint about it. Reply with only the word: ready".
3. **Turn 2** is the original probe's filler turn: "Unrelated question: what is the capital of France? Reply with only the city name."
4. **Turn 3** is asked in K = 2 independent forks: two separate API calls with byte-identical inputs. Both carry the same history, including the same encrypted reasoning items the original probe sends (with their summary text stripped), and the same request settings. Text: "Which number from the list did you privately pick at the start of this conversation? Reply with only the number."
5. **Settings.** Both arms send identical payloads except `reasoning.context` (`all_turns` or `current_turn`), as in the original probe: `max_output_tokens` 32,000 (D13), effort medium, mode standard, Flex, and `reasoning.summary: "auto"` as in the original probe. Each response's echoed summary setting is recorded.

**Scoring.**
- A trial is **scorable** iff the turn-1 and turn-2 responses completed, the visible turn-1 and turn-2 replies contain no three-digit number, and every echoed `reasoning.context` (turns 1 and 2 and both forks) equals the request.
- A **fork answer** is the first three-digit number in that fork's turn-3 reply, if it is in the trial's list; otherwise there is none. A refusal, a number outside the list and an incomplete turn-3 response (D13, §6) all count as none.
- The forks **agree** iff both fork answers exist and are equal.
- Unscorable trials are replaced, with at most 40 attempts per arm per model. An arm stops once it has 20 scorable trials.

**Reported per model and arm** (`fork_report.json` next to the run's `meta.json`): scorable trials and attempts; agreements; for each fork, how many answers were in the list; the distribution of answers and of the list positions answered, to expose value or position preferences; and the chance-agreement baseline, which is the `current_turn` arm's agreement rate. (For reference, two independent, uniform answers from the list would agree with probability 1/20.)

**New pass rule** (replaces D29's condition 2). A model's toggle is verified iff:
- **(a)** D29's echo condition holds, unchanged: the echoed `reasoning.context` equals the request on 100% of that model's pilot responses, in both arms. The block-1 echo check met it on both models (4 of 4 responses each), as did all 120 responses of each model's original probe. It covers the new probe's responses too; **and**
- **(b)** with 20 scorable trials per arm, the `all_turns` arm's forks agree in **≥ 15 of 20** trials and the `current_turn` arm's forks agree in **≤ 5 of 20**.

If an arm has fewer than 20 scorable trials after 40 attempts, the toggle is not verified for that model.

**Unchanged from D29.** If the echo passes but the probe fails, that model's toggle is not verified and the model runs no replay arm. If no API model is verified, kill criterion 1 applies. If luna is verified but sol is not, making luna H2's primary model needs an amendment. The probe is excluded from all analyses. Its per-arm results, now the per-arm agreement counts, are needed for G0 and are exempt from §11's blinding as a toggle check. §6's D13 rule carries over: an incomplete turn-3 response is an invalid answer, and an incomplete turn 1 or 2 makes the trial unscorable.

*Why:* when the turn-1 reasoning holds the pick and the model reads it, both `all_turns` forks read the same pick, so they agree unless recall fails. Without it, the two forks agree only through shared preferences for a value or a list position, and a fresh shuffled list in every trial weakens both. The `current_turn` bound of 5 of 20 leaves room for such preferences far above the 1/20 uniform rate.

**What the new probe does not show.** Agreement under `all_turns` well above the `current_turn` baseline shows that the two forks share information from the turn-1 reasoning. It does not show which number the model picked, how much of a long replayed history the model uses, or that replay carries the derived state of the PersistGym tasks. H2 tests that last point.

### 17.2 Amendment R2 (2026-10-02): sol at high reasoning effort after a blinded engagement check; sol's T_d = 210
**Status.** Proposed by Claude on 2026-10-02 after the researcher's two decisions that day (`results/decisions.md`): raise sol to high reasoning effort for H2, subject to a blinded check of pooled reasoning volume with a rule fixed in advance (Decision 1, option b); and raise sol's T_d to its ceiling of 210 (Decision 2). It takes effect when the researcher merges the pull request that adds it, and that merge adopts the check's rule below. The version line and the "Frozen" status line are unchanged.

**What it changes.**
1. **D13 (§6), for gpt-6.1-sol only, if the check below finds that reasoning engages:** `reasoning.effort: high` on every sol request of sol's validity runs (§4.4), of the H2 core (F-r and F-0 on the D11 cells, repeats included) and of sol's exploratory W/Σ replay pairs (§4.6), summary requests included. Every other D13 setting is unchanged. gpt-6-luna stays at `medium` for everything.
2. **D11 (§4.2): T_d = 210 and T_o = 70, fixed now.** This replaces the rule that T_d is the smallest multiple of 30 with power ≥ 0.80. The sol main sweep is F-r and F-0 on derived-far × {R, NR} for 210 templates and on observed-far × {R, NR} for the first 70: 1,120 episodes, plus 112 repeat episodes (§2.9), 1,232 in all.
3. **Effort echo (§3 H2, §13), for every PersistGym run from the merge on:** an episode in which any response's echoed `reasoning.effort` differs from the request is excluded and counted, in the same way as a `reasoning.context` mismatch, and the same stop rule applies. In block 1, every OpenAI response so far echoed the requested effort, `medium`: 9,579 of 9,579 responses (the echo checks, both replay-probe designs, the PersistGym pilots and luna's two validity runs, whose `results/costs.csv` rows count the same 9,579 calls), counted from the `effort_requested` and `effort_echoed` fields of their raw transcripts by `uv run python -m harnesses echo-count`.
4. Nothing else changes: no hypothesis, prediction, threshold, other decision or blockquote. The frozen text of §3 H2, §4.2, §6, §10.1 (fallback 4), §12 (the Phase 1a cap), §13, §15 and the register rows D11 and D13 stays, with a pointer here.

**Reason.**
- **Effort.** In block 1's sol pilot at medium effort (runs `results/persistgym_pilot/20261002T083238Z-F-r-gpt-6.1-sol` and `results/persistgym_pilot/20261002T083706Z-F-0-gpt-6.1-sol`: 16 episodes on the 4 far task cells, 360 calls), sol reported 115 reasoning tokens in total, pooled over both arms (`results/persistgym_pilot/pooled-20261002T084201Z/pilot_report.json`), about 0.3 per call. This pooled total is a quantity §11 allows. H2's success branch needs reasoning at earlier steps that replay can carry. With almost none, H2 would come out null almost by construction: a weak test of replay, not evidence against it. §15 already lists the risk that medium effort understates the value of replay.
- **T_d.** Block 1 measured costs well below the forecasts behind D11: sol's pilot cost $0.652 billed for 16 episodes ($0.041 per episode) at medium, and luna's two validity runs $1.351 for 320 episodes. At sol's pilot cost per episode, the 1,232 sol main-sweep episodes would cost about $50 at medium; the check below measures the cost at high. In the committed simulation (`results/power_sim/20261001T190327Z/h2_sol_power.csv`), moving from the central T_d = 120 to 210 raises the TOST equivalence power at ±8pp from 0.539 to 0.866 at p_F0 = 0.8 (0.278 to 0.675 at 0.6), and the one-sided test's power (α = 0.0125) at a true +8pp from 0.606 to 0.870 (0.414 to 0.645).
- **Timing.** Written after seeing, from block 1, only what §11 allows from pilots (pooled tokens, errors, latency, cost and echo-match rates), luna's validity levels and the replay-probe results (§17.1 and `results/decisions.md`). The one exception, an ARC pilot level count seen by mistake, is recorded as a deviation in `results/decisions.md` and concerns no PersistGym quantity. Written before any sol validity run, any main-sweep run and any computation of an H2 quantity. No result of the check below exists as it is written.

**The engagement check** (experiment `persistgym_pilot` under block 1's approval; a pilot under §11, excluded from all analyses).
- **Runs:** sol at `reasoning.effort: high`, every other D13 setting unchanged; harness cells F-r and F-0, one run each, F-r first; the 4 D11 task cells; pilot indices 0 and 1, the same 16 generated episodes as the medium pilot. Commands:

  ```
  PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses run --cell F-r \
      --model gpt-6.1-sol --effort high --split pilot --start 0 --n 2 \
      --task-cell observed-nonrec-far observed-rec-far derived-nonrec-far derived-rec-far \
      --experiment persistgym_pilot --approved-block "1-pilots" --planned-usd 6
  PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses run --cell F-0 \
      --model gpt-6.1-sol --effort high --split pilot --start 0 --n 2 \
      --task-cell observed-nonrec-far observed-rec-far derived-nonrec-far derived-rec-far \
      --experiment persistgym_pilot --approved-block "1-pilots" --planned-usd 6
  ```
- **Scored by** the committed $0 command `uv run python -m harnesses reasoning-check <F-r run_id> <F-0 run_id> --reference 20261002T083238Z-F-r-gpt-6.1-sol 20261002T083706Z-F-0-gpt-6.1-sol` (`harnesses/reasoning_check.py`), which reads both runs' raw episodes and transcripts and writes `reasoning_check.json` in a new folder, `results/persistgym_pilot/reasoning-check-<time>/`; `--reference` adds the medium pilot to the descriptive figures below. It reports only quantities pooled over both arms: never a per-arm value, no quantity of the need step on its own, and no success measure.
- **Evidence-step calls:** in each derived-far episode, the first step call at each evidence step (a step whose observation shows a clue of the target fact or the rule; the episode's `evidence_steps`), not a lookup result and not a summary call. Calls of an episode excluded for an echo mismatch (§13) do not count. An episode that stops early for another reason (an API error, the planned spend, the turn limit) counts with the calls it made, and the check re-runs no episode (§13's transport re-run does not apply to it), so an arm that stopped early gives fewer calls to the pool. The rule comes with the last clue and a derived fact has 2 or 3 clues, so the 8 derived-far episodes give 16 to 24 such calls: 20 on pilot indices 0 and 1, whose templates have 2 and 3 clues, and 16 on indices 2 and 3.
- **E** = the share of evidence-step calls, pooled over both arms and both derived-far task cells, whose provider-reported reasoning tokens (`usage.output_tokens_details.reasoning_tokens`) are at least 32.
- **Rule: reasoning engages iff E ≥ 0.50.**
  - **Engages:** change 1 takes effect. Claude forecasts sol's validity run (F-0 at high, validity templates 0-19 on all 8 task cells, restated and withheld) at the check's measured cost per episode. If it fits block 1's remaining limit it runs under block 1; otherwise Claude asks first. G1's validity gate (§4.4) applies to sol at high.
  - **Does not engage:** no sol validity run and no sol main-sweep run, at either effort. Claude proposes option (c) to the researcher, making derived facts need more reasoning (a generator change with new $0 and validity checks), as a further amendment. The researcher decides.
  - **Unscorable:** if fewer than 6 of the 8 derived-far episodes end normally (exit `DONE`, not excluded), or either run stops on an echo mismatch, the check runs once more on pilot indices 2 and 3 under the same rule. If it is still unscorable, the researcher is told and nothing runs at high.
  - **Recorded:** the verdict, E with its numerator and denominator, and the figures below go into `results/decisions.md` with the committed `reasoning_check.json`, and the researcher is told, before any sol validity run.
- **Reported alongside, descriptive only,** pooled over both arms, for the two check runs and, for reference, the two block-1 sol pilot runs at medium: step calls before the need step; mean and median reasoning tokens per such call, and the share with at least 1; E with its numerator and denominator; output tokens of all calls; billed cost per episode; errors; the echo-match rates of `reasoning.context` and `reasoning.effort`.
- **Blinding.** Each check run is one arm, so its `results/costs.csv` row, `meta.json` and `summary.json` carry that arm's output tokens and cost (§11, known limit); at high effort these are mostly reasoning tokens. Nobody compares them between the arms, and the check and the pooled pilot report use pooled values only.

*Why 32 and 0.50:* 32 reasoning tokens is room to restate a clue value and a running total, and about twice the median length of sol's turn-1 reasoning in the original replay probe (15.5 and 16.5 tokens, §17.1), a turn that asked only for a private pick and the word "ready". E ≥ 0.50 means most evidence steps leave reasoning that replay could carry. At medium, the pilot's pooled total of 115 tokens lets at most 3 of its 360 calls reach 32 tokens, so the bar asks for a step change, not a fine difference. The check uses evidence steps because replay can carry only what was reasoned before the need step. It leaves the need step out because need-step reasoning is H2's token outcome.

**What the check does not show.** Token counts do not show content. A reasoning item of 32 or more tokens at an evidence step need not hold the clue or the derived value: sol's turn-1 reasoning summaries in the original replay probe were empty in 40 of 40 trials at medium (§17.1), PersistGym runs request no summaries, and encrypted items are not inspected (§15). Engagement is needed for H2's success branch to be a fair test, but does not make it one. The check says nothing about which arm reasons more (for what each run's own files carry, see **Blinding** above), or about how high effort changes success.

**Toggle verification.** R1's fork probe verified sol's toggle at medium effort. It is not re-run at high: the toggle is verified per model under D29 as amended by R1, the probe's settings are registered at medium (§17.1), and the echoed `reasoning.context` is still checked on every response at high (§3 H2). Whether replay use differs at high effort is not tested.

**Cost and approval.** The check is forecast at about $2 billed for both runs, with a planned spend of $6 per run. The forecast is a rough guess, since no sol call at high effort has been seen: the medium pilot cost $0.652 for the same 16 episodes, and the guess assumes high effort adds about 600 reasoning tokens per call, billed as Flex output, plus cache writes of the replayed items in F-r. Block 1 has $47.16 of its $70 limit left before the check ($22.84 spent, `results/costs.csv`). A run that reaches its planned spend stops (`COST_CAP`); on the same assumptions that happens at roughly 4,000 to 6,000 reasoning tokens per call (at about 2,000 to 3,000 with $3, which was first proposed and raised to keep the check from stopping early). The unfinished episodes of a run that stopped there count against the unscorable rule above. The sol main sweep at T_d = 210 belongs to block 3 (`3-persistgym`) and needs its own approval. This amendment adds no spending approval.

**T_d from here on.** T_d = 210 and T_o = 70 are not lowered without a further amendment, so §10.1's fallback 4 (fewer sol templates) now needs one too, and §12's Phase 1a sizing at T_d = 150 no longer applies. If the phase-1a forecast at measured costs (sol at high if it engages) exceeds the 1a cap, the researcher must raise the cap first, as D11 already requires. The G1 power re-simulation (§9.8) still runs with the measured variance, and its achieved power at T_d = 210 is reported, but it no longer sets T_d. The values are recorded in `results/decisions.md` before the sol main sweep (§4.2).

**As implemented** (the pull request that adds this amendment; `harnesses/DESIGN.md` §12). `harnesses/registered.py` holds the registered efforts (luna `medium`, sol `high`) and the check's constants. `harnesses run` defaults to the model's registered effort (a dated snapshot or alias of a model counts as that model) and, before the paid-run lock, refuses any other effort outside `persistgym_pilot`. It also refuses a non-pilot sol run unless the `reasoning_check.json` files under `results/persistgym_pilot/` for sol at high effort, under this rule, say ENGAGED in the order above: on pilot indices 0 and 1, or on 2 and 3 after an UNSCORABLE check on 0 and 1. Any file that says NOT_ENGAGED refuses, and so do two check pairs on the same indices. `reasoning-check` scores only check runs on those indices. The probes keep their registered medium settings (§17.1). The runner excludes an episode whose echoed effort differs (exit `REASONING_EFFORT_MISMATCH`), counts it toward the abort after 2 excluded episodes, and reports effort echo-match counts next to the context ones in the pilot summaries. The pooled pilot report (`pilot-report`) pools by model and requested effort, so the check runs never join block 1's sol pool at medium; otherwise, a report made after only the F-r run would show that arm's reasoning total as its difference from block 1's report.
