# Decisions log

Gate decisions, approvals and the numbers behind them (CLAUDE.md "Milestone and gate discipline"). Newest at the bottom. The researcher makes every go/no-go and spending call; Claude proposes.

## How approvals are recorded
A paid block (PLAN.md §16.2) can spend only after the researcher adds one approval line to this file, under that day's entry. The paid guard (`common/approval.py`) reads the line; it never writes one. The grammar, with this exact spacing:

```
# grammar only: indented here and with <placeholders>, so it never counts as an approval
    approved_block: <name> | experiments: <exp1>,<exp2>,... | max_usd: <amount>
# example only, never counts for the same reasons
    approved_block: <example-block> | experiments: toggle_pilot,replay_probe | max_usd: 2.50
# clearing a hold, grammar only: indented and with a <placeholder>, so it never clears one
    cleared_hold: <run_id>
```

- A real line starts at column 0: no list marker, indentation, quote or backticks. Only trailing whitespace is ignored. A line inside a fenced code block or an HTML comment never counts, so a gate entry can show a proposed line in a code block without approving anything.
- `<name>` matches `[A-Za-z0-9._-]+`. Each experiment is a key of `EXPERIMENT_PHASE` in `common/costs.py`, or starts with `ext_`. The list is comma-separated with no spaces. `<amount>` is a positive number of US dollars such as `76` or `2.50`, with no `$`, sign, exponent or thousands separator. A line that breaks a rule never counts.
- The line counts only when the same line is in this file on `origin/main` (the guard runs `git fetch origin main` first and refuses if the fetch fails), in the checked-out `HEAD` and in the working tree. Removing or changing it in any of the three revokes the approval. Keep one line per block: two different lines for one block are refused. To change a limit, edit the line; the new line counts once it is merged.
- A run is allowed only for an experiment in the list, and only while the block's spend plus the run's planned spend is at most `max_usd`. Block spend is the sum, over `results/costs.csv` rows whose notes contain `approved_block=<name>;`, of `cost_usd_billed_est`, or of `cost_usd_list` for a row with no billed estimate. So `max_usd` is in billed dollars, like the caps and forecasts in PLAN.md (D23): on Flex, the Flex price. A run measures its own spend the same way and stops at its planned spend. The phase caps (PLAN.md §12) still apply, measured the same way. Paid calls also need `PREREG.md` in `HEAD` to be the one on `origin/main`.
- **Runs of both streams at once** (PREREG §0.3 line 15, §12). An ARC run and a PersistGym run may go at the same time, each under its own paid-run lock (`common/paidlock.py`). While a run is going, its planned spend counts as spent for a run of the other stream, against the block they share (a block whose list names experiments of both streams, such as block 1) and the phase they share (phases 0 and 2), until its costs row is written. So a block's `max_usd` must have room for the planned spend of both runs if both are to go at once; otherwise the second one is refused until the first has ended.
- **Clearing a hold** (PREREG §0.3 line 12, §7.7). A paid run that ends `COST_CAP`, or whose spend passed its run guard before the guard could stop it, places a hold, recorded next to the paid-run lock (`common/hold.py`). While it stands, no further paid run starts in either stream, ARC or PersistGym, and the refusal names the run and the exact line that clears it. Only the researcher clears a hold, by adding that line, `cleared_hold: <run_id>` with the grammar shown above, under that day's entry. The rules are those of an approval line: column 0, exactly that spacing, `<run_id>` matching `[A-Za-z0-9._-]+`, outside any code block or HTML comment, and in this file on `origin/main`, in `HEAD` and in the working tree. Removing or hiding it in any of the three puts the hold back. One line clears one run's hold; two holds need two lines.

## 2026-09-30: start $0 work; staged spending approvals
- **Decision (researcher):** amend PLAN.md (amendment A1) and start the $0 work of Stage 0 immediately. Inform the researcher at every major spending point for a decision.
- **Process (researcher):** all changes land through branches and pull requests; nothing is pushed directly to `main`.
- **Accounts (researcher, 2026-09-30):** ARC API key created. Gemini billing linked (usage tier to be checked in AI Studio). OpenAI org at usage tier 3 ($1,000/month usage limit).
- **Spend to date:** $0.
- **Next spending decision:** Stage 1-2 pilots (about $42-76; see PLAN.md §16 A1), requested only after `PREREG.md` is committed and payload snapshot tests pass.

## 2026-10-01: accounts ready; local ARC games; costs.csv schema
- **Accounts (researcher):** `.env` set up locally with the ARC, Google and OpenAI keys. Gemini billing account is at **Tier 2** ($2,000/month cap), so the Tier 1 $250 pause no longer applies.
- **Approved (researcher):** download the 25 public ARC-AGI-3 games once with the ARC key and run their game code locally, for $0 plumbing and payload tests only. Counted runs stay on ARC's online scorecard. Game sources stay under the gitignored `results/raw/`.
- **Approved (researcher):** add `service_tier_served`, `cache_write_tokens` and `latency_s` to `results/costs.csv` and the CLAUDE.md schema (no rows existed yet).
- **Merged:** PR #1 (scaffold), PR #2 (PLAN amendment A1), PR #3 (background facts).
- **Spend to date:** $0.
- **Merged (later on 2026-10-01):** PR #5 (ARC public-runs operational slice), PR #6 (cost model and power simulation), PR #9 (costs.csv schema). Researcher set provider-side spend limits (OpenAI project, Gemini project).

## 2026-10-01: ARC games downloaded; first $0 real-game runs; scoop signal
- **Games:** the 25 public ARC-AGI-3 games downloaded once with the ARC key (one request at a time, 3 s apart) at the exact versions of ARC's published Gemini 3.8 Flash runs (e.g. `lp85-305b61c3`). Stored under the gitignored `results/raw/arc_games/` with a SHA-256 manifest. Every game's `baseline_actions` equals the published sessions' `level_baseline_actions` (25 of 25).
- **Offline smoke on real games ($0):** the patched harness (PR #8, patches 0001-0015) played LS20 and TR87 under S0, S1, S2 and S4 with the stub model, fully offline: 8 of 8 runs pass the runner's request and `run_meta.json` checks. All ended `ACTION_BUDGET` (the stub plays seeded random actions). S1, S2 and S4 compacted (9 summaries on LS20, 19 on TR87); S0 never summarized. LS20 and TR87 were chosen because they are in neither the path pool nor any held-out candidate set, so no candidate game was played before the D14 decision. Output: `results/raw/arc_offline_smoke/`.
- **Scoop signal (kill criterion 6 check, not a trigger):** ARC Prize's harness repository has an unmerged branch `feature/continuous-conversation-carry-forward-ablation` whose last commit (fecf46b, 2026-08-29, "Add carry-forward prompt ablation") adds the notes sentence to the continuous-conversation (Adapter) system prompt. No PR was opened from it and no published scores were found (GitHub search and a web search on 2026-10-01). It would ablate one component (the notes instruction) on the Adapter side. Re-check at G0: ARC Prize blog and results pages, the repo's PRs and branches.
- **Spend to date:** $0.

## 2026-10-01: researcher decisions D1-D39, phase caps, PRs #12-#17 merged
The researcher decided all 39 open items (D1-D39) of the `PREREG.md` draft (PR #4, decision register in its §16). PLAN.md amendment A2 (§17, PR #18) records what they change in the plan.

**Decisions (researcher):**
- **D14, option A.** The ARC games are fixed by rule, with no draw. Path games: FT09, SB26, R11L, CD82. Held-out games: SP80, VC33, TN36. LP85 and SC25 are not used.
- **D11, option A.** sol runs only far cells: the derived-far cells on T_d templates and the observed-far cells on T_o = T_d/3 of them. The central value is T_d = 120. T_d is always a multiple of 30. It may be raised later to at most 210, and only if that is decided before the sol main sweep starts and before any H2 outcome is computed.
- **D8.** H1's token clause is read on need-phase tokens. Whole-episode token ratios are reported as secondary.
- **D2.** The fix is adopted: a derived fact's options are one cluster of values around the true value (consecutive values in generator 0.2.0, PR #15), so that no proper subset of the clues narrows the options. A $0 check in every derived cell tests that partial memory gives no edge.
- **D23.** The billed estimate is the primary cost basis. The list cost is reported alongside.
- **D24, option B.** All 3 held-out games are committed, with no cut to 2. G3's 4 runs are a separate phase-2 budget line.
- **D21.** Every ARC run uses the Gemini standard tier.
- **D20.** A `TIME_BUDGET` ending is final, unless there is a provider-latency incident. For a config's first counted run, the pilot's median seconds per call is the reference.
- **D15.** The seed comes from the NIST randomness beacon after the PREREG freeze, with drand as the fallback. It sets the pilot game, the fallback drop and the run orders.
- **D7.** The 10% repeat subset is kept on both luna and sol. Template seeds start at 0 and are used in multiples of 10.
- **D27, rule 1.** G0 prices S1 and S2 at the S0/S4 midpoint. Checkpoint C adds a conservative check, where Claude may ask for a phase 1b cap increase of up to about $170.
- **All other D items** follow the decision sheet's recommendation, as written in the PREREG draft. This includes D36: luna runs the restated-at-need control as full F-0 episodes on all 8 task cells, and the single-turn control on the 4 non-recoverable cells only.
- **Claude's technical choices are accepted.** S1 and S2 never drop old turns. S0 keeps thinking summaries on `auto`. Transport-level retry is on. Pilot outcomes go only to the gitignored `results/raw/`. Paid blocks are approved by researcher-merged approval lines in this file on `origin/main` (grammar at the top).
- **Follow-ups to A2.** The researcher took the recommendation on both: (a) the phase 2 cap is $1,250; (b) the T_d ceiling is 210.

**Caps approved (researcher):** phase 1a $500 (was $450) and phase 2 $1,250 (was $950). Phase 0 stays $100 and phase 1b $900. These caps are in PLAN.md §17.3 and `common/costs.py`. Approving the caps approves no paid block; each block still needs its own approval line.

**Forecast at these decisions** (billed, 1k output tokens per PersistGym call; `results/cost_model/20261001T203318Z/option_a_summary.md`):
- Phase 1a: 494.18 against $500. This prices luna's controls as D36 has them.
- Phase 1b (G0 rule, with the re-run reserve): 811.86 against $900.
- Phase 2 (with reserves): 1,233.19 against $1,250.

These are forecasts from published runs, not measured costs.

**Merged:**
- PR #12: test isolation.
- PR #13: the paid guard needs a committed approval line; pilot blinding and logging.
- PR #14: ARC patch 0016.
- PR #15: generator 0.2.0.
- PR #16: the D15 draw script. It has not been run.
- PR #17: option-A recordings, cost scenario and the D11 power simulation.

**Spend to date:** $0. `results/costs.csv` has no rows.

## 2026-10-01: PREREG sign-off answers; PRs #18-#21 merged
The researcher answered the 15 sign-off lines of the `PREREG.md` draft (§0.3, PR #4).

**Answers (researcher):**
- **Confirmed as recommended:** lines 1-11, 13 and 14. On line 9, phase 1a's money goes first to luna's replay-off cells and controls, then to sol's T_d under the §4.2 rule. luna's replay-on cells run only from what is left.
- **Line 12, changed.** Spending approvals stay per block: block 2 is the 8 counted seed-1 runs, and block 3 is approved as two blocks (see line 15). The $120 run guard stays where it is, set by the ARC launcher at run time. A counted run still needs $120 of room under its block's limit and under the phase 1b cap when it starts; otherwise Claude stops and asks. New: any paid run that reaches its $120 guard ends `COST_CAP`, as decided in D22, and places a hold. While the hold stands, no further paid run starts in either stream. Only the researcher clears it, by merging a line into this file that names the run. The code that adds the hold defines that line's exact form, and it lands as a $0 pull request before block 2.
- **Line 15, changed.** ARC runs go back to back, one at a time, in the SEED + 3 order. This replaces D18's rule that all block-3 runs start within 72 hours of each other; the rest of D18 is unchanged. PersistGym runs go one at a time, but a run may play up to 16 episodes in parallel. That costs the same, and the run reserves spend so that it never exceeds its planned spend. The ARC stream (Gemini) and the PersistGym stream (OpenAI) may run at the same time, each with its own paid-run lock and its own approval blocks. Block 3 is approved as two blocks: `3-arc` (the 24 ARC path runs) and `3-persistgym` (the PersistGym main sweep). The per-stream locks and the parallel episodes land as $0 pull requests before block 3. Until then, one paid run at a time overall.

**Merged (researcher, 2026-10-01):** PR #20 (test timeout), PR #18 (PLAN amendment A2; the phase caps in `common/costs.py`), PR #21 (ARC patch 0017, the config freeze record, the guarded ARC launcher) and PR #19 (the guard counts billed spend).

**Next:** PR #4 freezes `PREREG.md` as version 1.0 when the researcher merges it. Its merge commit is the freeze commit, recorded here after the merge. The beacon draw runs once, at least 10 minutes after that commit.

**Spend to date:** $0. `results/costs.csv` has no rows.

## 2026-10-02: PREREG frozen (v1.0)
- **Freeze commit:** `ed340a1cda91153dafe78772861c40343b53dafa`, the merge of PR #4, committed 2026-10-01T23:20:28-04:00 (2026-10-02T03:20:28Z). `PREREG.md` is Version 1.0, "Frozen on 2026-10-01 by Raimondas Lencevicius (sign-off in PR #4)". From here on it changes only by dated amendment with a reason.
- **Merged before the freeze (PREREG §0.4 step 1):** #22 D13 output cap `9fe51ef`, #25 D39 withheld control `589b554`, #24 PersistGym launcher lock `936bc68`, #23 ARC freeze-record check `b0440bc`, #26 DESIGN repeat-subset line `8b1a58b`; earlier #18 `9090bca`, #21 `7955f11`, #19 `2b0a958`, #20 `46c61a1`.
- **Checks on `main` before the freeze merge:** `uv run ruff check .` clean; `uv run pytest -q` 837 passed, 3 skipped (isitdone receipt PASS, tree 193fdde).
- **Spend to date:** $0.
## 2026-10-02: ARC game draw (D15, D17, D18, D32)
- **Freeze commit:** `ed340a1cda91153dafe78772861c40343b53dafa` ("Merge pull request #4 from raimondasl/m0/prereg-draft"), PREREG.md Version 1.0, status "Frozen on 2026-10-01 by Raimondas Lencevicius (sign-off in PR #4).". Committer time 2026-10-01T23:20:28-04:00; T = committer time + 10 min = 2026-10-02T03:30:28.000Z.
- **Seed source:** NIST Randomness Beacon 2.0 pulse https://beacon.nist.gov/beacon/2.0/chain/2/pulse/1966405 (timeStamp 2026-10-02T03:31:00.000Z, statusCode 0), fetched from https://beacon.nist.gov/beacon/2.0/pulse/time/1790911828000; the preceding pulse is before T. `outputValue[:16]` = `38B7BD1E97A12D5E`, so SEED = 4086943125952605534.
- **Permutation:** `random.Random(SEED).sample(['FT09', 'SB26', 'R11L', 'CD82'], 4)` = R11L, SB26, FT09, CD82 (Python 3.12.13). The recorded output is authoritative.
- **Truncated-pilot game (D17):** perm[0] = R11L. **Dropped under the 3-game fallback (D32):** perm[3] = CD82.
- **Block 2 order (D18, SEED + 2):** 1. CD82 S4 r1, 2. FT09 S0 r1, 3. SB26 S4 r1, 4. SB26 S0 r1, 5. CD82 S0 r1, 6. R11L S0 r1, 7. R11L S4 r1, 8. FT09 S4 r1.
- **Block 3 order (D18, SEED + 3):** 1. SB26 S1 r1, 2. R11L S2 r2, 3. FT09 S2 r1, 4. FT09 S1 r1, 5. SB26 S1 r2, 6. R11L S2 r1, 7. SB26 S2 r1, 8. FT09 S1 r2, 9. SB26 S0 r2, 10. CD82 S2 r2, 11. CD82 S1 r2, 12. CD82 S4 r2, 13. FT09 S4 r2, 14. SB26 S4 r2, 15. R11L S4 r2, 16. FT09 S0 r2, 17. CD82 S1 r1, 18. FT09 S2 r2, 19. CD82 S2 r1, 20. CD82 S0 r2, 21. R11L S1 r1, 22. SB26 S2 r2, 23. R11L S0 r2, 24. R11L S1 r2.
- **Output:** `results/draw/20261002T033145Z/` from `arc/draw_games.py` at commit `ed340a1cda91153dafe78772861c40343b53dafa`, drawn 2026-10-02T03:31:45.183Z.
- **Spend:** $0 (no paid calls).
- **Independent check (Claude, 2026-10-02):** re-derived from the committed raw pulses with a separate script: pulse 1966405 (03:31:00Z) is the first at or after T = 03:30:28Z, the previous pulse 1966404 (03:30:00Z) is before T, SEED = int("38B7BD1E97A12D5E", 16) = 4086943125952605534, and `random.Random(SEED).sample(...)` gives R11L, SB26, FT09, CD82. All match.

## 2026-10-02: Block 1 (pilots) — proposed by Claude, approved when the researcher merges the PR that adds this entry
- **What it buys** (PLAN §16.2 block 1; PREREG §12), in this order, one paid run at a time:
  1. OpenAI `reasoning.context` echo check on sol and luna (`toggle_pilot`). If sol's echo does not match, the replay probe and H2 on sol stop and Claude asks (kill criterion 1: E1 decision).
  2. Private-number replay-use probe on sol, and on luna if its echo matches (`replay_probe`).
  3. Gemini acceptance check of S0, S1, S2 and S4 at `thinking_level` high on the standard tier (`gemini_probe`).
  4. Truncated ARC pilot on **R11L** (the drawn pilot game): S0 and S4 to 50 actions, S1 to its first summary plus 5 turns, S2 to 30 actions (`arc_pilot`). Pilot results are blinded (PREREG §11) and excluded from all analyses.
  5. PersistGym pilots on the pilot seed range, at most 10 episodes per cell (`persistgym_pilot`), then the G1 validity runs (`persistgym_validity`): luna, then sol.
- **Forecast** (`results/cost_model/20261001T203318Z/optA_central_line_items.csv`, billed): echo checks $0.28, replay probes $1.18, Gemini acceptance $1.60, ARC pilot $21.08, luna pilots and validity $7.85, sol pilot and validity $21.90; **total $53.90** at 1k output tokens per OpenAI call ($66.93 at 2k). Google about $22.68, OpenAI about $31.22.
- **Limit:** $70 billed for the whole block. Phase caps also apply (phase 0 $100, 1a $500). If a run would pass the limit, it does not start and Claude asks. Provider-side limits set by the researcher (OpenAI project $50, Gemini project $100) are the backstop.
- **Stop rules:** Claude stops and reports before the next step if a step shows payload rejections, error rates above the PREREG thresholds, or a cost per call more than 1.5× the forecast.
- **Decides:** the inputs to G0 on Oct 7 (sol replay toggle, Gemini S0-S2 acceptance, ARC cost forecast) and to G1 (validity gate).

approved_block: 1-pilots | experiments: toggle_pilot,replay_probe,gemini_probe,arc_pilot,persistgym_pilot,persistgym_validity | max_usd: 70

## 2026-10-02: Block 1 steps 1-3 so far; D29 option A (PREREG amendment R1)
**Results so far** (block 1, run one at a time). The run folders and `results/costs.csv` rows are in the main checkout and are committed with block 1's results, not in this entry's pull request. The replay-probe numbers come from `uv run python -m harnesses probe-summary` on the two replay runs.
- **Step 1, echo check (`toggle_pilot`): passed on both models.** sol and luna each echoed the requested `reasoning.context` on 4 of 4 responses, 2 per arm (`results/toggle_pilot/20261002T034458Z-echo-gpt-6.1-sol`, `results/toggle_pilot/20261002T034509Z-echo-gpt-6-luna`). This meets D29's condition 1 so far.
- **Step 2, replay-use probe (`replay_probe`), D29's original design: it could not score.** It learns the picked number from the turn-1 reasoning summary, and the summaries almost never named one: sol's were empty in 40 of 40 trials and luna's in 32 of 40, and only 2 of luna's named exactly one number. So 0 of 40 sol trials and 2 of 40 luna trials were scorable, against 20 per arm needed (`results/replay_probe/20261002T034558Z-replay-gpt-6.1-sol`, `results/replay_probe/20261002T034914Z-replay-gpt-6-luna`).
  - Descriptive only: in turn 3, sol gave a number in 20 of 20 `all_turns` trials (583 ×16, 683 ×2, 628, 684) and in 0 of 20 `current_turn` trials, where every reply said it had no number. luna gave a number in 18 of 20 `all_turns` trials (583 ×17, 617) and in 17 of 20 `current_turn` trials (583 ×15, 417, 482).
  - Every echoed `reasoning.context` matched (120 of 120 responses per model), with no visible leaks and no incomplete responses.
  - These numbers neither verify nor reject either toggle. luna's `current_turn` arm cannot see the turn-1 reasoning and still answered 583 in 15 of 20 trials, so a shared favourite number cannot be told apart from recall. The full table is in PREREG §17.1.
- **Step 3, Gemini acceptance (`gemini_probe`): passed for S0, S1, S2 and S4.** Each config's request was accepted at `thinking_level` high on the standard tier (exit reason `ALL_ACCEPTED`, 4 calls, $0.12; `results/gemini_probe/20261002T035344Z-accept`). This is the payload acceptance check. D37's "Gemini S0-S2 run" condition still needs the truncated ARC pilot (step 4).
- **Spend, steps 1-3:** $0.15 billed ($0.18 list): echo checks $0.0002, replay probes $0.0298, Gemini acceptance $0.1158. Block 1's limit is $70.

**Decision (researcher, 2026-10-02): option A.** Pre-register a redesigned replay-use probe, then run it. Amendment R1 (PREREG §17.1) is that pre-registration, written after seeing the results above and before any run of the new probe:
- **The probe:** each trial shows a fresh shuffled list of 20 three-digit numbers, asks the model to privately pick one and reply "ready", asks the filler question, and then asks which number it picked twice, in two forks with byte-identical requests. If the turn-1 reasoning holds the pick and the model reads it back, the two forks agree. Without it, they agree only by chance or by shared preferences, which the `current_turn` arm measures.
- **The new pass rule:** a model's toggle is verified iff (a) D29's echo condition holds (100% echo match in both arms), and (b) with 20 scorable trials per arm, the `all_turns` arm's forks agree in at least 15 of 20 trials and the `current_turn` arm's in at most 5 of 20. If an arm has fewer than 20 scorable trials after 40 attempts, that model's toggle is not verified. The rest of D29 is unchanged.
- **Approval:** the researcher's merge of the pull request that adds this entry and amendment R1 approves the new pass rule. It adds no spending approval.

**Next.** After the merge, and once no other paid run holds the lock, Claude runs `probe-replay --design fork` on sol and luna as `replay_probe` under block 1's existing approval. Forecast: about $0.05 billed for both models if every trial is scorable, and at most about $0.10 at 40 attempts per arm. This uses the block-1 replay probe's tokens per call from `results/costs.csv`, plus about 70 input tokens for the list, and the command runs with `--planned-usd 1`. The per-arm agreement counts go into this file for G0.

## 2026-10-02: Protocol deviation, pilot blinding (ARC pilot S0 on R11L)
- **What happened:** during the truncated ARC pilot run `20261002T035726Z-S0-r11l-s1` (S0 on R11L, 50 actions, $7.85 billed), the patched harness logged ARC's final scorecard JSON to its console output, and Claude displayed the last lines of that output, which included the run's level count. PREREG §11 says pilots never report per-config ARC level progress. The committed `meta.json` and `costs.csv` row were blinded as designed (checked by key names only).
- **Extent:** one number, the levels S0 completed in this 50-action pilot run. It is not repeated here. No outcome of S4, S1 or S2 was seen: S4 was refused before it started (PREREG.md on `origin/main` had changed with PR #29), and S1 and S2 have not run.
- **Impact:** pilot runs are excluded from every analysis (PREREG §11), and no design or threshold choice remains open that this number could inform. Recorded as a deviation and reported with the results.
- **Fix:** the ARC launcher now writes a blinded run's harness output only to `results/raw/arc_pilot/<run_id>/inner_output.log` (gitignored) and prints nothing from the harness (PR `m0/blind-pilot-output`). The remaining pilot runs (S4, S1, S2) run only after that fix is merged.

## 2026-10-02: Block 1 (pilots), results so far
- **Spend:** $22.84 billed of the $70 block limit (phase 0 $20.57, phase 1a $2.28), 19 rows in `results/costs.csv`.
- **OpenAI echo check** (`toggle_pilot`): echoed `reasoning.context` equalled the request on every response, sol and luna.
- **Replay-use probe:** the original design could not score (empty turn-1 summaries; see amendment R1). The fork design (R1): sol's forks agreed in 20/20 trials with `all_turns` and 0/20 with `current_turn` (echo 160/160), so **sol's toggle is verified**; luna 13/20 vs 6/20, **not verified** (luna runs no replay cells). Cost $0.06.
- **Gemini acceptance** (`gemini_probe`): S0, S1, S2 and S4 accepted at `thinking_level` high on the standard tier; returned model `gemini-3.8-flash`; $0.12.
- **Truncated ARC pilot on R11L** (`arc_pilot`, blinded): S0 50 actions $7.85, S4 50 actions $5.79, S1 to its first summary + 5 turns $1.77 (1 compaction, 0 context trims), S2 30 actions $4.96 (5 compactions, 0 trims); all served on the standard tier; median latency 73 s (S0), 29 s (S4), 104 s (S1), 97 s (S2). Total $20.37 against the $21.08 forecast. Level progress is blinded (PREREG §11; see the S0 deviation entry above).
- **PersistGym pilots** (`persistgym_pilot`, 8 episodes per harness cell, pooled report only): luna F-0, W-0, W-n-0, Σ-n-0 (32 episodes) and sol F-0, F-r on the far cells (16 episodes); all episodes ended normally, 0 exclusions, echo matched 781/781 (luna) and 360/360 (sol). Pooled output tokens per call: about 30 (luna) and 11 (sol); pooled reasoning tokens: 12,193 over 781 luna calls, 115 over 360 sol calls. Cost $0.93: about 10-30× below the forecast, which assumed ~1k output tokens per call.
- **luna validity** (`persistgym_validity`, F-0, validity templates 0-19 × 8 task cells): restated-at-need 160/160 = 100% (gate ≥ 85%); fact-withheld 19/160 = 11.9% (gate ≤ 20%), per cell 0-30% (derived-nonrec-far 6/20). All 320 episodes ended normally. Cost $1.35.
- **Still to run in block 1:** sol's validity run, after the researcher's decisions on sol's reasoning effort and template count.

## 2026-10-02: Researcher decisions on sol's reasoning effort and template count (PREREG amendment R2)
**Decisions (researcher, 2026-10-02):**
- **Decision 1: option (b).** sol runs H2 at `reasoning.effort: high`, but only after a blinded check of pooled reasoning volume, with its rule pre-registered before the check runs: amendment R2, PREREG §17.2. The check runs F-r and F-0 on sol at high effort on the 16 episodes of block 1's sol pilot (pilot templates 0 and 1, the 4 far task cells). Reasoning engages iff E ≥ 0.50, where E is the share of evidence-step calls in the derived-far episodes, pooled over both arms, with at least 32 reasoning tokens. If it engages, sol's validity run, H2 core and exploratory replay pairs run at high; if not, no sol validity or main-sweep run at either effort, and Claude proposes option (c) (derived facts that need more reasoning) as a further amendment. luna stays at medium.
- **Decision 2: yes.** sol's T_d = 210 and T_o = 70, its D11 ceiling: 1,120 main-sweep episodes, plus 112 repeat episodes, 1,232 in all. They are not lowered without a further amendment.
- **Decision 3: accepted.** Claude prepares the G1 spot-check package, 160 generated validity episodes (20 per task cell), for the researcher's review without model output (PREREG §4.4).

**What the decisions rest on** (block 1; only what PREREG §11 allows from pilots). sol's pilot at medium reported 115 reasoning tokens over 360 calls, pooled over both arms (`results/persistgym_pilot/pooled-20261002T084201Z/pilot_report.json`), and cost $0.652 billed for 16 episodes. Every OpenAI response of block 1 echoed the requested effort, `medium`: 9,579 of 9,579 (`uv run python -m harnesses echo-count` on the raw transcripts). At T_d = 210 the simulated TOST power at ±8pp is 0.866 (p_F0 = 0.8) against 0.539 at T_d = 120 (`results/power_sim/20261001T190327Z/h2_sol_power.csv`).

**Approval.** The researcher's merge of the pull request that adds this entry adopts amendment R2 and its rule, and the code that enforces them (`harnesses/registered.py`: outside `persistgym_pilot`, `run` refuses any effort other than the model's registered one, and refuses sol unless the `reasoning_check.json` files say ENGAGED in R2's order and none says NOT_ENGAGED). It adds no spending approval.
- The engagement check runs under block 1's existing approval (`1-pilots`), one run at a time: forecast about $2 billed for both runs (a rough guess: no sol call at high effort has been seen; PREREG §17.2 states its assumptions), planned $6 per run, at most $12 for both. Block 1 has $47.16 of its $70 limit left before the check ($70 − $22.84).
- It is scored by the $0 command `uv run python -m harnesses reasoning-check`, whose report goes to `results/persistgym_pilot/reasoning-check-<time>/`.
- If reasoning engages, sol's validity run (F-0 at high, validity templates 0-19 on all 8 task cells, restated and withheld) runs under block 1 if its forecast at the check's measured cost per episode fits the remaining limit; otherwise Claude asks first.
- The sol main sweep at T_d = 210 belongs to block 3 (`3-persistgym`) and needs its own approval.

**Spend to date:** $22.84 billed, unchanged (this entry's pull request is $0).

## 2026-10-02: Engagement check (PREREG §17.2): the F-0 run's accounting failed
- **What happened:** the check's two paid pilot runs (sol at `reasoning.effort: high`, F-r then F-0, `persistgym_pilot` under block `1-pilots`, pilot templates 0 and 1 × the 4 D11 far task cells, `--planned-usd 6` each) were started one after the other from a background shell, which a time limit later stopped. Both started from `main` at `9c53512`. The F-r run's row records a clean tree (`git_dirty=False`, read by its `finalize` just before it appended the row). The F-0 run started about three seconds after that row was appended and before it was committed, so a tracked file, `results/costs.csv`, differed from the commit: its git state is `git_dirty=True`, as for every run started after an uncommitted costs row (the code it ran is that of `9c53512`). The F-r run (`20261002T173710Z-F-r-gpt-6.1-sol`) finished normally, and its row is in `results/costs.csv`. The F-0 run (`20261002T180358Z-F-0-gpt-6.1-sol`) went on as an orphaned process, played all 8 of its episodes and wrote its raw transcript and `episodes.jsonl` under `results/raw/` (gitignored). Its costs row could not be written: `finalize` ran `git rev-parse HEAD` after the calls, and git could not start (exit 3221225794, 0xC0000142 `STATUS_DLL_INIT_FAILED`: the process had lost its console, so it could start no console program).
- **State:** as designed, the F-0 run kept the PersistGym paid-run lock, with the reason and its totals, and its $6 spend reservation, so no PersistGym paid run can start. It wrote no costs row, `summary.json` or `meta.json`. **The F-0 run's spend is not in `results/costs.csv`** until `account-run` (below) has run, after the pull request that adds this entry is merged. No per-arm success, reasoning-token or need-step quantity of either run has been looked at (PREREG §11).
- **Root-cause fix** (PR `m0/account-run`): a paid run reads its git state once, before its first call, and its costs row and `meta.json` record that value, so no process starts between its first call and its row. On Windows git starts without a console window (`CREATE_NO_WINDOW`), and a run that cannot read its git state refuses before any call. The ARC launcher reads its git state before the harness starts, for the same reason. `run` now also writes a raw `run_plan.json` before its first call, with what is needed to rebuild its accounting and no outcome.
- **Recovery:** the new $0 command `uv run python -m harnesses account-run <run_id>` rebuilds a run's costs row, `summary.json` and `meta.json` from its raw files with the repo's own code, refuses unless the row's totals equal those kept in the lock, then records the run as the last paid run and releases its reservation and its lock (harnesses/DESIGN.md §8.1). It replaces adding the row and deleting the lock and reservation by hand. After the merge, Claude runs it on the F-0 run from the main checkout, with the run's arguments and its git state (`--git-commit 9c535120a1094e825ab0aeced6cfafb813e67229`, `--git-dirty true`; account-run refuses `--git-dirty false` here, since the ledger shows the F-r row the commit lacks), `--check` first, and reports what it wrote.
- **Operational fix:** every paid run is launched as a process of its own, with its own console, never from a shell that a time limit can stop.
- **The check's verdict waits for the recovery:** `reasoning-check` reads both runs' `meta.json`, so it runs only once the F-0 run is accounted for.
- **Spend:** this entry's pull request is $0. The block's spend to date is stated once the F-0 run's row is in `results/costs.csv`; a total now, against the $22.84 of the last entry, would give the F-r run's cost alone.

## 2026-10-02: Engagement check (PREREG §17.2): NOT ENGAGED
- **Accounting recovered:** after PR #39 merged, `uv run python -m harnesses account-run 20261002T180358Z-F-0-gpt-6.1-sol ... --git-commit 9c535120a1094e825ab0aeced6cfafb813e67229 --git-dirty true` checked every rebuilt total against the totals kept in the lock (all matched; `--check` first, then the real run), appended the F-0 run's costs row, wrote its `summary.json` and `meta.json` (with `recovered`), and released the reservation and the lock.
- **Verdict** (`uv run python -m harnesses reasoning-check 20261002T173710Z-F-r-gpt-6.1-sol 20261002T180358Z-F-0-gpt-6.1-sol --reference 20261002T083238Z-F-r-gpt-6.1-sol 20261002T083706Z-F-0-gpt-6.1-sol`; `results/persistgym_pilot/reasoning-check-20261002T225917Z/reasoning_check.json`): **E = 0/20 = 0.00 < 0.50, NOT_ENGAGED.** None of the 20 evidence-step calls of the 8 derived-far episodes, pooled over both arms, reported 32 or more reasoning tokens. All 8 derived-far episodes ended normally, so the check is scorable.
- **Descriptive, pooled over both arms** (PREREG §17.2):

  | | check, effort high | block-1 pilot, effort medium (reference) |
  |---|---|---|
  | Episodes; calls | 16; 360 | 16; 360 |
  | Step calls before the need step | 336 | 336 |
  | Reasoning tokens per such call: mean; median | 0.432; 0 | 0.0; 0 |
  | Share of such calls with any reasoning | 3.3% | 0% |
  | Output tokens, all calls | 4,398 | 4,119 |
  | Billed cost; per episode | $0.699; $0.0437 | $0.652; $0.0408 |
  | Errors | none (16 `DONE`, 0 excluded) | none |
  | Echo match: `reasoning.context`; `reasoning.effort` | 360/360; 360/360 (`high`) | 360/360; 360/360 (`medium`) |

- **What it means:** at high effort, sol still answers this task almost without reasoning before the need step, as at medium. Replay therefore has almost nothing to carry, and H2's success branch would be a weak test at either effort.
- **What it does not show:** anything about either arm, about success, or about reasoning at the need step. Token counts do not show content.
- **Consequence (PREREG §17.2, "Does not engage"):** no sol validity run and no sol main-sweep run, at either effort. Claude proposes option (c), making derived facts need more reasoning, to the researcher as a further amendment; the researcher decides. Nothing else waits on this: luna's runs, the ARC blocks and G0 (Oct 7) are unaffected.
- **Spend:** the check cost $0.699 billed for both runs. Block 1: **$23.54 billed of $70** (phase 0 $20.57, phase 1a $2.98), 21 rows in `results/costs.csv`.

## 2026-10-02: Researcher decision after the engagement check: option (c), both levers, hard stop (PREREG amendment R3)
**Decision (researcher, 2026-10-02):** option (c), with a hard stop and both levers. For gpt-6.1-sol only, derived facts are made to need reasoning: (i) a derivation that takes several steps, and (ii) each evidence step tells the agent that the value will be needed later. One new engagement check, pre-registered before it runs, then decides; if it fails, H2 on sol stops for good. luna's generator config, episodes and validity results stay as they are.

**What the merge adopts** (amendment R3, PREREG §17.3; it adds no spending approval):
- **The variant** (generator 0.4.0, preset `sol-chain`, config hash `b0d0b020d5b9135bad3b4cb4c074a19bdbb8590e51dd04a690ba0fcaedbaaf97`). Each clue value is given by a chain record, a two-hop relay over three helper entities (an anchor value, a far and a near difference, and a decoy), so resolving a clue takes two 3-digit operations (though the units digits alone pick the option, so the variant does not force multi-step reasoning; PREREG §17.3); the rule stays a plain sum, shown with the first clue. Each evidence step adds the notice "The {quantity} of {kind} {ENTITY} will be requested in a later update. Before replying, work out as much of it as the records so far allow and keep the result in mind; do not write it in your reply." (the observed fact's reveal: "... Keep it in mind; do not write it in your reply."). Options, clue values and every other template value are generator 0.3.0's. The default config's hash and episodes are unchanged.
- **The check's rule:** R2's rule (E ≥ 0.50 at ≥ 32 reasoning tokens, evidence-step calls pooled over both arms) on runs of the variant: sol at high effort, F-r then F-0, pilot templates 0 and 1 on the 4 D11 far task cells, `--planned-usd 6` each, under block `1-pilots`; if unscorable, once more on pilot templates 2 and 3. Scored by `reasoning-check` with R2's two check runs as the reference. A new pooled descriptive counts evidence-step replies that write a value the episode never shows.
- **The hard stop:** if the check is NOT_ENGAGED, or UNSCORABLE twice, H2 on sol stops for good and is reported as not testable in this task family, with both checks as descriptive findings; no further variant or effort. If it is ENGAGED but sol's G1 validity gate (§4.4) fails on the variant, H2 on sol stops the same way, with no redesign. Whether the Holm family is then adjusted as 4 or 2 tests is the researcher's decision, before any H1 or H3 test.
- **The spot-check proposal:** sol's G1 spot-check covers 20 episodes per D11 task cell (80 episodes), not all 8 cells (`spotcheck --preset sol-chain`).
- **The code that enforces them** (`harnesses/registered.py`): outside pilots, sol runs only on the `sol-chain` config hash, in F-r and F-0, after an ENGAGED check on that config, and, outside its validity run, after the researcher records G1 (`G1_PASSED`, empty until the G1 decision PR); its validity experiment holds only the validity run (F-0, validity split, restated or withheld). A sol pilot at high effort must play `sol-chain` in F-r or F-0, and after the hard stop no sol pilot runs above medium effort. Check files are keyed by generator config, so R2's NOT_ENGAGED file binds the default config only. `reasoning-check` scores only check runs on the `sol-chain` hash.

**$0 audits on the variant** (committed code; no API call; the figures are in PREREG §17.3 and persistgym/DESIGN.md §9):
- `uv run python -m persistgym audit --preset sol-chain --n 1000` (main templates 0-999, 24,000 episodes, 3,000 per task cell): all 21 checks pass (the 17 of generator 0.3.0, the lookup audit and the 3 new ones); every no-memory baseline 0.100; the new `nearest_to_stand_in_value` 0.100 in each task cell; key and text oracles 1.00 on base and restated, text 0.10 on withheld; 0 narrowing templates at the clue and the atom level; the six misreadings of the chain records 0.092-0.110. The default config passes the same command (`nearest_to_stand_in_value` 0.100 in each task cell).
- `render --preset sol-chain` on validity templates 0-19 and main 0-59: `validity_pass=True`. `partial-memory --preset sol-chain --n 2000` on the pilot, validity and main splits: generator 0.3.0's clue-level figures, 0 atom-level narrowing, misreadings 0.081-0.118.
- The default config's episodes are byte for byte those of generator 0.3.0 (golden fixture of validity 0-19, pilot 0-3 and main 0-9, taken before any change), and its config hash is still `3d6bc648…`.

**Next** (each paid run local, in a console of its own, after the merge):
1. The check's two runs (PREREG §17.3 has the commands), then `reasoning-check`, an entry here, and the researcher is told. Forecast about $1-2 billed for both runs (R2's check cost $0.699 for the same 16 episode ids; the variant adds the evidence-step and need-step reasoning).
2. If ENGAGED: sol's validity run (F-0, validity templates 0-19 × 8 task cells, restated, then withheld) is forecast at the check's measured cost per episode, pooled over both arms, × 320 (at R2's $0.0437 per episode, about $14, plus up to about half again for the chain derivations). It runs under block `1-pilots` if the forecast fits the remaining limit after the check; otherwise Claude asks first.
3. G1 is scored and the researcher decides; only a passing G1 PR sets `G1_PASSED`. The sol main sweep (block `3-persistgym`) needs its own approval, at the validity run's measured cost.

**Spend to date:** $23.54 billed of block 1's $70, unchanged ($46.46 left); this entry's pull request is $0.

## 2026-10-03: R3 engagement check: NOT ENGAGED; hard stop, H2 on sol ends
- **Runs** (PREREG §17.3; block `1-pilots`; each launched as a process with a console of its own): `20261003T055240Z-F-r-gpt-6.1-sol` and `20261003T060120Z-F-0-gpt-6.1-sol`, sol at effort high on the `sol-chain` variant (generator config `b0d0b020…`), pilot templates 0-1 × the 4 far task cells. Both `COMPLETED`.
- **Verdict** (`uv run python -m harnesses reasoning-check 20261003T055240Z-F-r-gpt-6.1-sol 20261003T060120Z-F-0-gpt-6.1-sol --reference 20261002T173710Z-F-r-gpt-6.1-sol 20261002T180358Z-F-0-gpt-6.1-sol`; `results/persistgym_pilot/reasoning-check-20261003T061000Z/reasoning_check.json`): **E = 6/20 = 0.30 < 0.50, NOT_ENGAGED.** All 8 derived-far episodes ended normally, so the check is scorable.
- **Descriptive, pooled over both arms:**

  | | R3 check: `sol-chain`, high | R2 check: default config, high (reference) |
  |---|---|---|
  | Episodes; calls | 16; 360 | 16; 360 |
  | Evidence-step calls with ≥ 32 reasoning tokens | 6 of 20 | 0 of 20 |
  | Step calls before the need step | 336 | 336 |
  | Reasoning tokens per such call: mean; median | 2.652; 0 | 0.432; 0 |
  | Share of such calls with any reasoning | 12.2% | 3.3% |
  | Output tokens, all calls | 5,274 | 4,398 |
  | Billed cost; per episode | $0.890; $0.0556 | $0.699; $0.0437 |
  | Errors | none (16 `DONE`, 0 excluded) | none |
  | Echo match: `reasoning.context`; `reasoning.effort` | 360/360; 360/360 | 360/360; 360/360 |
  | Evidence-step replies showing a hidden value | 0 of 20 | not counted |

- **Consequence: R3's hard stop applies.** H2 on sol ends for good. It is reported as **not testable in this task family**, with both engagement checks as descriptive findings. No further variant, effort or check is tried, and the guard now refuses every non-pilot sol run for H2, every sol pilot above medium effort and any further scoring (checked: a `persistgym_validity` command on `sol-chain` refuses, citing this file).
- **What it means:** told to work the value out at each clue and keep it private, sol at high effort reasoned more than before (6 of 20 evidence-step calls reached 32 tokens, against 0 of 20), but most evidence steps still drew little or no reasoning. Replay would have little to carry in most episodes.
- **What it does not show:** anything about either arm, about success, or about reasoning at the need step. Token counts do not show content. It is about this task family, sol, and the two framings tried, not about reasoning replay in general.
- **Open, the researcher's decision** (§17.3): whether H1 and H3 are adjusted as a Holm family of 4 (conservative) or of 2, recorded before any H1 or H3 test is computed.
- **Unaffected:** luna's runs (H1, H3), the ARC path study (H4, H5), StateCarry and G0 (Oct 7). Amendment R4, a pre-registered sol replication of H1 on the default config at medium effort, is being prepared at the researcher's request.
- **Spend:** the check cost $0.890 billed for both runs. Block 1: **$24.43 billed of $70** (phase 0 $20.57, phase 1a $3.87), 23 rows in `results/costs.csv`.
