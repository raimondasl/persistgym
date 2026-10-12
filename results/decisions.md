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

## 2026-10-03: Researcher request: a pre-registered sol replication of H1 (PREREG amendment R4)
**Request (researcher, 2026-10-03, after PR #41 merged):** a small amendment that pre-registers a replication of H1 on gpt-6.1-sol now, before any H1 data exists, whatever happens to H2 ("please draft small amendment and I can approve it"). R3's check was scored NOT_ENGAGED the same morning, before R4's first commit (entry above), so H2 on sol has ended under R3's hard stop; without the replication PersistGym has no evidence on a second model, gpt-6.1-sol. H1 concerns eviction and lookup, not reasoning. R4's design does not depend on R3's verdict.

**What the merge adopts** (amendment R4, PREREG §17.4; it adds no spending approval):
- **The replication:** gpt-6.1-sol at `reasoning.effort: medium` (D13 as frozen, luna's effort) on the default generator config (luna's episodes, hash `3d6bc648…`, not `sol-chain`; if §4.2's rule changes luna's config at M1, the replication follows it), harness cells F-0, W-0 and W-n-0 on the 4 observed task cells, so every H1 quantity can be computed (Δ_H1, the manipulation check, recoverable success, lookups, R_need and its secondary readings). T is luna's main-sweep template count for these cells (§4.2, set at M1, about 100), main seeds from 0, with the §2.9 repeats: 440 episodes per harness cell and 1,320 in all at T = 100. The repeat-1 runs, like luna's, need a repeat option in `harnesses run`, still to be built as a $0 pull request before block 3. T is not lowered to fit the cap; if it does not fit, Claude asks.
- **Its pilot:** W-0 and W-n-0 have never run on sol, so one pilot run of each (sol at medium, default config, pilot templates 0 and 1 × the 4 observed task cells, 8 episodes each, `persistgym_pilot`, blinded), read from its costs rows and blinded `summary.json` files only. The pooled pilot report leaves both runs out (`blinding.is_left_out`): in block 1's sol pool they would show their reasoning tokens by difference.
- **Its validity gate (the replication's G1):** F-0 at medium, validity templates 0-19 × the 4 observed task cells, restated and withheld (160 episodes, `persistgym_validity`); restated ≥ 85% and withheld ≤ 20%, pooled over those 4 cells; the default config's $0 audits (which pass); the researcher's spot-check of package `g1-validity-0-20-3d6bc648` covers these templates and task cells, so there is no extra spot-check; its findings are not yet recorded, and the replication's G1 waits for them as luna's does. If sol fails, the replication does not run and is reported as not run; no redesign pass.
- **Its status:** a replication reported next to luna's primary H1 result, with the same estimands, predictions and thresholds, outside the Holm family; it adds no test to it and does not change its size, which stays the researcher's open decision (4 or 2, entry above). It neither confirms nor kills H1; luna stays primary, and H1's kill rule and kill criterion 5 read luna only. If the two disagree, both are reported.
- **Independence from H2:** R2's and R3's sol rules (high effort, `sol-chain`, F-r and F-0 only, the engagement verdicts and the hard stop) concern H2's runs and do not block the replication, whose runs cannot run H2's contrast (no F-r, no `sol-chain`, no derived task cell, no effort above medium).
- **The code** (`harnesses/registered.py`): `run` allows, and only allows, the replication's validity run (sol at medium on the default config in `persistgym_validity`, F-0 on the validity split, restated or withheld, validity templates 0-19, observed task cells) and its main runs (new experiment `persistgym_sol_h1`, phase 1a, PersistGym stream; F-0, W-0 or W-n-0, main split, base variant, observed task cells), both with D13's `--mode standard`, `--service-tier flex` and no `--W`, the main runs only once `REPLICATION_G1_PASSED` records the replication's G1 (empty until the researcher's G1 decision PR for it). Every R2 and R3 refusal of sol's other runs stays.

**Forecast** (`uv run python -m analysis.sol_h1_forecast`; `results/cost_model/20261003T071449Z/summary.md`; billed, from block 1's measured `results/costs.csv` rows):
- **Central, T = 100: $279.49** (pilot $4.34, validity $10.28, main runs $264.87: F-0 $26.17, W-0 $115.55, W-n-0 $123.15); at T = 50, $147.06. On the lower basis first proposed (sol's F-0 pilot row and luna's W/F-0 cost ratios): $81.06 at T = 100.
- **Why the central basis is higher:** sol's F-0 pilot row played its 8 episodes right after the F-r run had played the same 8, so almost all of its input was read from the cache (3,030 cache-write tokens against 252,326); main-sweep episodes run cold, so the central basis is the F-r row of the same episodes. Window cells lose about half of their caching (luna's pilot read 52% of W-0's input and 49% of W-n-0's from the cache, against 94% of F-0's), and sol's cached input costs 1/20 of its input price against luna's 1/10, so luna's measured token mix is priced at sol's prices (W-0 4.42 and W-n-0 4.71 times F-0, against 3.33 and 3.53 at luna's prices). sol's window cells are unmeasured: the pilot measures them before block 3 is approved.
- **Phase 1a** (cap $500): $3.87 spent (R3's check, $0.89, included), roughly $35.52 for luna's main sweep and controls, nothing for sol's H2 runs (R3's hard stop), and the replication: **$318.87 at T = 100** ($181.13 under the cap), $186.44 at T = 50.

**Blocks.** The replication's pilot and validity runs go under block 1 (`1-pilots`) if block 1's remaining limit covers them ($14.62 central; $45.57 is left); otherwise in block 3, whose approval line must then list `persistgym_pilot` and `persistgym_validity`. Its main runs go in block 3 (`3-persistgym`) after the confirmatory rows (luna's replay-off cells and controls; sol's H2 core will not run; PREREG §0.3, line 9); block 3's approval line must list `persistgym_sol_h1`, and its forecast uses the pilot's measured costs.

**Next** (each paid run local, in a console of its own, after the merge and once no other PersistGym run holds the lock): the replication's pilot and validity runs, an entry here with the validity rates, the researcher's spot-check findings on `g1-validity-0-20-3d6bc648`, and the researcher's G1 decision for the replication.

**Spend to date:** $24.43 billed of block 1's $70 ($45.57 left), R3's check included (this branch holds its commit, `d82898b`). This entry's pull request is $0.

## 2026-10-06: Researcher decisions: R4's template count; the Holm family after H2's stop
- **R4's template count (§17.4):** T = luna's main-sweep template count, as drafted (about 100). The researcher chose this over T = 50 on 2026-10-06.
- **Holm family (§9.4, §17.3):** H2 on sol stopped under R3's hard stop (2026-10-03), so the confirmatory family becomes **H1 and H3, 2 one-sided tests**. The family-of-4 result, with H2's two tests counted as not rejected, is reported alongside as a sensitivity analysis. Decided by the researcher on 2026-10-06, before any H1 or H3 test is computed: no main-split episode of any model has run.

## 2026-10-06: G0 gate (PREREG §10.1): Claude proposes GO
Gate metrics from `uv run python -m analysis.g0` at commit `a255e05`, clean tree (`results/gates/g0-20261006T133152Z/`).
- **Snapshot tests pass** at every commit block 1's paid runs used:
  - PersistGym: `uv run pytest -q harnesses/tests/test_payload_snapshots.py` in a detached worktree of each commit, `b9f3d8e` (47 passed), `0ed61f0` (47 passed), `9c53512` (53 passed) and `4638fc0` (53 passed).
  - ARC configs S0-S4: `uv run python arc/apply_patches.py` applied patches 0001-0017 to the pinned harness (series `14e25cc7…`, commit `67f6dd0d…`, tree `5206d039…`, equal to `arc/config_freeze.json`) and its unit tests, the payload snapshot tests of patches 0005, 0008 and 0013 included, passed. `arc/patches` and `arc/config_freeze.json` are unchanged since `b9f3d8e`.
- **Toggle rule (D29 as amended by R1): sol verified** (forks agree 20/20 with `all_turns`, 0/20 with `current_turn`; every echo matched). luna not verified (13/20 and 6/20). Kill criterion 1 does not fire. H2 on sol later ended for another reason, R3's engagement hard stop (2026-10-03).
- **Gemini S0-S2 run (D37):** in the truncated ARC pilot on R11L, S0 reached 50 actions, S1 its first compaction plus 5 turns, and S2 30 actions. All three ended `NORMAL_ENDING_BLINDED`, on the standard tier, at `thinking_level` high, returned model `gemini-3.8-flash`. Only exit status, compaction occurrence, tier and settings were read (§11).
- **Cost rule (D27 rule 1, D28):** b(c), the billed/list ratio measured in the pilot, is S0 0.832, S1 0.790, S2 0.786 and S4 0.763. With the published list costs of the 4 path games, F = **$679.30** billed, and **$815.15** with the 20% reserve, against the $900 phase-1b cap (headroom $84.85): **met**.
- **Scoop search** (2026-10-06):
  - [ARC harness repo](https://github.com/arcprize/arc-agi-3-benchmarking): the branch `feature/continuous-conversation-carry-forward-ablation` has had no commit since `fecf46b` (2026-08-29). No PR is a per-component ablation. #48 (open) adds compaction diagnostics. #46 and #47 (merged 2026-10-02) add Gemini continuation handling upstream of our pin `4ca00e6`; our runs stay on the pinned fork.
  - [ARC Prize blog](https://arcprize.org/blog): no post since Sep 3 (GPT-6 Astra).
  - Web and arXiv search: no new per-component ablation. OpenAI's Jul 29 post and the Astra results are already in `docs/background.md` and report combined effects only.
  - **D31's trigger does not fire.**
- **Proposal: GO.** G0 releases block 2: seed-1 S0 and S4 on the 4 path games in the beacon order, forecast $169.14 billed without the reserve and $202.97 with it (`results/cost_model/20261001T203318Z/`). Block 2 needs its own approval line, which Claude drafts only when the researcher asks. Before block 2, the Gemini project's provider spend limit ($100) must be raised above the block's limit.
- **Spend to date:** $24.43 billed (phase 0 $20.57, phase 1a $3.87, phase 1b $0), 23 rows in `results/costs.csv`. Block 1: $24.43 of $70.
- **The researcher makes the go/no-go call.**

## 2026-10-06: G0: GO (researcher)
The researcher's call on 2026-10-06, after the merge of PR #44 with the G0 metrics: **GO**. G0 releases block 2 (§12), which needs its own approval line.

## 2026-10-06: Block 2 (seed-1 S0+S4) — proposed by Claude, approved when the researcher merges the PR that adds this entry
- **What it buys** (PREREG §12 block 2, §7.4): the 8 counted seed-1 runs, S0 (Standard) and S4 (Adapter) on the 4 path games, Gemini 3.8 Flash at `thinking_level` high on the standard tier (`arc_path`). They run one at a time, back to back, in the D18 order (SEED + 2): 1. CD82 S4, 2. FT09 S0, 3. SB26 S4, 4. SB26 S0, 5. CD82 S0, 6. R11L S0, 7. R11L S4, 8. FT09 S4. Each run is launched as a process with a console of its own. Error re-runs follow §7.5 (D19).
- **Forecast:** **$171.46 billed**, or $205.75 with the 20% re-run reserve. This is the published list cost of each run × b(c) measured in the pilot (`results/gates/g0-20261006T133152Z/g0.json`). By run: CD82 S4 $22.13, FT09 S0 $23.90, SB26 S4 $12.98, SB26 S0 $24.39, CD82 S0 $9.71, R11L S0 $45.54, R11L S4 $26.69, FT09 S4 $6.11.
- **Limit: $330 billed.** Every counted run needs $120 of room under the limit when it starts (§12). At the forecast, the last run starts at about $165 of block spend, so it needs a limit of at least $285. The rest leaves room for one re-run or a moderate overrun. If a run would pass the limit, it does not start, and Claude asks. Phase 1b: $0 spent of its $900 cap.
- **Run guard and hold:** each run stops at $120 at list (D22). A run that reaches it places a hold: nothing paid starts in either stream until the researcher merges a `cleared_hold:` line (§12).
- **12 h warning (D21):** checked before this block. No planned run's 1.5 × published actions × published seconds per action exceeds 12 h (Claude told the researcher in chat).
- **Before the first run:** the researcher raises the Gemini project's provider spend limit from $100 to at least the block limit. It is the backstop.
- **Stop rules:** Claude stops and reports before the next run on payload rejections, a hold, an error rate above PREREG §7.5's re-run rule, or a run whose billed cost passes 1.5× its forecast.
- **Blinding:** none. These are counted runs, not pilots. Their level progress is the data H4 needs.
- **Decides:** Checkpoint C (§10.3): the first fresh-seed gap, the real per-run cost and how runs end, then block 3.

approved_block: 2-arc-seed1 | experiments: arc_path | max_usd: 400

## 2026-10-06: R4 step 1 (block 1): sol's window-cell pilots and default-config validity
Approved by the researcher in chat on 2026-10-06 ("Yes on R4's first paid step"), under block `1-pilots`. Each run was launched as a process with a console of its own.
- **OpenAI Flex outage:** from about 10:26 to 13:10 ET, sol's Flex requests returned 429 `flex_unavailable` ("Flex processing is temporarily unavailable"; status.openai.com listed no incident).
  - Five W-0 attempts and one W-n-0 attempt aborted (`ABORTED_API_ERRORS`), costing $0.85 billed in all. Every one is in `results/costs.csv`, and its folder is committed.
  - D13 keeps OpenAI on Flex, so a retry driver waited 30 min between attempts. Flex was available again from 13:40.
  - At the researcher's request (2026-10-06), a night fallback, from 23:00 with retries until 07:00, was armed in case the day failed. It was not needed.
- **Pilots** (`persistgym_pilot`; allowed fields only, §11), sol at medium on the default config, pilot templates 0-1 × the 4 observed task cells:

  | Run | Episodes | Exits | Echo match (context; effort) | Median latency | Billed |
  |---|---|---|---|---|---|
  | `20261006T174041Z-W-0-gpt-6.1-sol` | 8 | 7 `DONE`, 1 `API_ERROR` (Flex) | 161/161; 161/161 | 9.0 s | $1.28 |
  | `20261006T181348Z-W-n-0-gpt-6.1-sol` | 8 | 8 `DONE` | 181/181; 181/181 | 5.1 s | $1.93 |

  Per episode, $0.16 (W-0) and $0.24 (W-n-0) billed, below R4's central forecast for these cells ($0.263 and $0.280, `results/cost_model/20261003T071449Z/`). The block-3 forecast will be redone from these rows.
- **sol's default-config validity** (`persistgym_validity`, F-0, validity templates 0-19 × the 4 observed task cells; §17.4):
  - **restated-at-need 80/80 = 100%** (gate ≥ 85%), 20/20 in each cell (`20261006T182920Z-F-0-gpt-6.1-sol`);
  - **fact-withheld 9/80 = 11.25%** (gate ≤ 20%), per cell 1-4 of 20 (`20261006T200237Z-F-0-gpt-6.1-sol`);
  - all 160 episodes `DONE`, 0 excluded; $10.21 billed, $0.064 per episode.
- **The replication's G1 waits for the researcher's spot-check** of package `g1-validity-0-20-3d6bc648` (§4.4, §17.4). The oracle and the $0 audits pass on the default config. `REPLICATION_G1_PASSED` stays empty until the researcher's G1 decision.
- **Spend:** R4 step 1 cost $14.30 billed ($3.21 pilots, $0.85 aborted attempts, $10.21 validity), against the $14.62 central forecast. Block 1: $38.72 of $70. Block 2 so far: $16.87 (run 1, CD82 S4). All phases: $55.59.

## 2026-10-07: Block 2 after run 2: a D20 latency incident, option (a); action-matched readings (PREREG amendment R5)
**Block 2's first two runs** (`arc_path`, block `2-arc-seed1`, in the D18 order; each launched as a process with a console of its own):

| | Run 1 | Run 2 |
|---|---|---|
| Run | `20261006T144656Z-S4-cd82-s1` | `20261006T171726Z-S0-ft09-s1` |
| Game, config, seed | CD82, S4, 1 | FT09, S0, 1 |
| Ending (`agent_exit_reason`) | `GAME_WIN` | `TIME_BUDGET` (the 12 h clock) |
| Actions (resets); levels | 206 (4); 6 of 6 | 236 (4); 5 of 6 |
| Score (ARC's scorecard) | 73.02 | 58.17 |
| Wall clock; seconds per action | 2.49 h; 44 | about 12 h; about 184 |
| Median seconds per model call | 17.36 | 181.25 |
| Billed (forecast) | $16.87 ($22.13) | $50.15 ($23.90, 2.10×) |

- **Run 2's pace:** about 132 s per action over its first 50 actions and about 290 s near the end. It reached action 126, where ARC's published FT09 Standard-high run ended, at 5.2 h against that run's 3.0 h, and action 150 at about 5.6 h. Over the run it averaged about 184 s per action against the published run's 86 s: run 2 was about twice as slow per action as ARC's published Standard run on FT09, and about 4 times as slow as run 1 (S4, on CD82). Run 1 averaged 44 s per action against 36 s in ARC's published CD82 Adapter run (`results/arc_public_ops/20261001T185155Z/recordings_per_action.csv`).
- **Run 2's levels:** level actions 4, 7, 108, 33, 37 and 47 against human baselines 43, 12, 23, 28, 65 and 37; level scores 115, 115, 4.54, 71.99, 115 and 0.
- Sources: run 1's committed `meta.json`, `scorecard.json` and `results/costs.csv` row. Run 2's figures are those Claude reported to the researcher from its files on 2026-10-07; run 2's folder and costs row are not yet on `main` as this entry is written.

**Decisions (researcher):**
- **(i) Block 2 resumes after a cost overrun alone (2026-10-06).** Block 2's stop rules include a run whose billed cost passes 1.5× its forecast. The researcher decided on 2026-10-06 that block 2 resumes after a stop for a cost overrun alone: Claude reports the overrun, and the next run follows. Run 2's cost, 2.10× its forecast, would therefore only have been reported; its `TIME_BUDGET` ending under D20 needed decision (ii).
- **(ii) Run 2 is a D20 latency incident; option (a) (2026-10-07).** D20 makes a `TIME_BUDGET` ending final unless the run's median seconds per model call exceeds 2× the median of its config's earlier counted runs, or the pilot's median if there is none (PREREG §7.5; §0.3 line 3). Run 2 is S0's first block-2 run, so S0 has no earlier counted run and the yardstick is the S0 pilot's 73.30 s (`20261002T035726Z-S0-r11l-s1`, `results/costs.csv`). Run 2's 181.25 s is 2.47× that, so run 2 is a latency incident by the rule as written, and D19 re-runs it once. The researcher chose option (a): re-run it once, with seed 101 (`--seed 101 --rerun-of 20261006T171726Z-S0-ft09-s1`). The re-run replaces run 2 in every primary analysis; both are reported, and H4's sensitivity analysis scores the original (§7.5).
  - **Deviation (PREREG §13): when the re-run starts.** D19 and §0.3 line 16 start a re-run right after the run it replaces. As Claude proposed, the researcher scheduled it after run 8, last in block 2. Reason: the run was paused overnight while the researcher weighed options (a) and (b) for this ruling, and a re-run right away would have held the remaining 6 runs back by up to 12 hours. Starting it last also means it starts with the block's real spend in view, under the $120-of-room rule (§12). Recorded here as a deviation; R5 does not change D19.
- **(iii) Block 2 resumes at run 3 (2026-10-07)**, in the D18 order: 3. SB26 S4, 4. SB26 S0, 5. CD82 S0, 6. R11L S0, 7. R11L S4, 8. FT09 S4, then the re-run of run 2 (FT09 S0, seed 101).
- **(iv) Phase 1b is sized at Checkpoint C (2026-10-07).** How much of phase 1b to run, and any change to its cap, is decided at Checkpoint C (PREREG §10.3), from block 2's measured costs and endings.
- **(v) Amendment R5 (PREREG §17.5), drafted at the researcher's request (2026-10-07).** The clock bound run 2 (S0) but not run 1 (S4), and it is likely to bind S1 and S2 too, which were slower per call than S0 in the pilot (medians 104.1 s and 96.7 s against 73.3 s). Where it binds some configs and not others, the clock-based readings of H4 mix what a config does with each action and how fast its actions come. R5 adds secondary readings of H4 at a matched number of actions; nothing else changes (H4's and H5's primary readings, predictions and thresholds, every gate and kill rule, the clock, the budgets, the run plan, D19 and D20).
  - **Readings:** for each counted run, ARC's game score and the levels cleared within its first K actions (RHAE_K), with a curve at 50, 100, 150 and 200 actions; H4's path quantities computed again from RHAE_K; at Checkpoint C, the seed-1 gap at K next to the frozen one, descriptively. No rule reads them.
  - **K = 150:** the largest multiple of 50 that every config should reach inside 12 h at run 2's pace, with S1 and S2 slowed by their pilot latency ratios (150 actions take about 7.7 h for S0, 10.9 h for S1 and 10.1 h for S2).
  - **Censoring:** a run that stopped before K actions other than by `GAME_WIN` or `ACTION_BUDGET` is censored: reported at its final values as lower bounds and, in a sensitivity analysis, left out with its unit. A counted run whose scorecard the script cannot score, or whose score it does not reproduce, has no matched values, and its unit is left out.
  - **Code:** `analysis/arc_action_matched.py`. Its committed run, `results/arc_action_matched/20261007T134853Z/`, covers run 1 only, since run 2's folder is not on `main` yet.
  - **Later runs:** Claude will not read the scorecards, logs or `meta.json` files of run 3 or later until R5 is merged.

**Approval.** The researcher's merge of the pull request that adds this entry adopts amendment R5 and records decisions (i)-(iv) and the deviation. It adds no spending approval.

**Spend** (billed): block 2 $67.02 of $330 (run 1 $16.87, run 2 $50.15). Every remaining counted run needs $120 of room under $330 when it starts (§12), so the re-run, scheduled last, starts only if block 2's spend is at most $210 by then; otherwise it does not start, and Claude asks. Phase 1b: $67.02 of $900. All phases: $105.74. This entry's pull request is $0.

## 2026-10-08: Block 2 limit raised from $330 to $400 (proposed by Claude; approved when the researcher merges the PR that changes the approval line)
- **Why:** each counted ARC run needs $120 of room under the block limit when it starts (§12). Block 2 has spent $165.07 billed after 5 runs (runs 1-5 in the D18 order), against $93.11 forecast for them.
- **Spend by run:**

  | Run | Ending | Billed | Forecast |
  |---|---|---|---|
  | CD82 S4 | `GAME_WIN` | $16.87 | $22.13 |
  | FT09 S0 | `TIME_BUDGET` | $50.15 | $23.90 |
  | SB26 S4 | `GAME_WIN` | $13.81 | $12.98 |
  | SB26 S0 | `ACTION_BUDGET` | $38.51 | $24.39 |
  | CD82 S0 | `TIME_BUDGET` | $45.73 | $9.71 |

  At today's Gemini pace, S0 runs reach the 12 h clock or a deep level's action budget, at about $40-50 billed each.
- **What is left:**
  - run 6 (R11L S0), in progress, likely about $50 (its published run took 6.7 h at ARC's faster pace);
  - run 7 (R11L S4), about $25;
  - run 8 (FT09 S4), about $6;
  - the D20 re-run of FT09 S0 (option (a), last), about $50.
- **The arithmetic:** after run 6 the block would stand at about $215, so run 7 could not start under $330 ($215 + $120 > $330). Before the re-run, at about $246, it needs a limit of at least $366. **$400** leaves a margin for one more overrun. Expected final block spend: about $300.
- **D20 check for run 5** (CD82 S0, `TIME_BUDGET`): its median was 170.06 s per model call. The median of the earlier counted S0 runs' medians (181.25 s and 156.68 s) is 168.97 s, so the threshold is 337.9 s. Not a latency incident: the ending is final and flagged.
- **Run 6's first launch** (2026-10-08 09:40 ET) was refused before any spend: `uv sync --locked` in the scratch harness worktree failed with "Access is denied" on a temporary uv helper `.exe` (Windows file lock). It was relaunched at 09:41.
- **Phase 1b:** $165.07 spent of its $900 cap; this raise changes no cap. The phase-1b sizing (3 vs 4 games, or a cap raise) is decided at Checkpoint C, as agreed on 2026-10-07.

## 2026-10-09: Checkpoint C (PREREG §10.3): the cost rule fires; Claude proposes the 3-game fallback with a phase-1b cap raise (the researcher decides)
- **Block 2 is complete.** The FT09 S0 re-run (`20261009T030646Z-S0-ft09-s101`, seed 101) ended `TIME_BUDGET` at $48.84 billed. Its median was 175.95 s per model call against a threshold of 2 × 156.68 s (the median of the earlier counted S0 runs). It is not a latency incident, so the ending is final (D20). It replaces the original run 2 in every primary analysis. Block 2 spent **$290.22 of its $400 limit** across 9 runs; nothing is left running.
- **Metrics:** `uv run python -m analysis.checkpoint_c` at `660bc56` (clean tree), in `results/checkpoint_c/20261009T151039Z/` (status FINAL).

  | Rule | 4 games (FT09, SB26, R11L, CD82) | 3 games (D32 drops CD82) | Fires if |
  |---|---|---|---|
  | Gap, seed-1 mean S4 − S0 (RHAE) | 62.59 | 61.43 | < 5 |
  | Gap at K = 150 (R5, descriptive) | 53.95 | 61.43 | no rule |
  | Errors after re-runs | 0 of 8 | 0 of 6 | > 3 |
  | Cost forecast for the remaining runs (D27) | $1,045.23 (24 runs, ρ = 0.125) | $804.55 (18 runs, ρ = 0.167) | > remaining $609.78 |
  | Headroom with D27's ~$170 raise | −$265.46 | −$24.77 | |
  | Phase-1b cap the forecast needs | $1,335.46 (+$435.46) | $1,094.77 (+$194.77) | |

  Per-game gaps: FT09 81.89, SB26 94.56, R11L 7.83, CD82 66.08. The FT09 S0 original, a D20 incident, scored 58.17 against the re-run's 18.11; H4's sensitivity analysis scores the original (§7.5).
- **The cost rule fires under both game sets**, so Claude proposes a re-scope and the researcher decides (§10.3). The options:
  - **(A) 4 games, full design:** 24 runs; raise the 1b cap to about $1,340. This is $435 over $900, beyond the ~$170 D27 lets Claude request.
  - **(B) 3-game fallback (D32, pre-registered):** drop CD82 (`perm[3]` of the draw); 18 runs; raise the 1b cap to about $1,100. That is $195 over $900, $25 beyond D27's ~$170.
  - **(C) Seed 1 only:** S1 and S2 on seed 1, with no seed 2. This fits under $900 with no raise. It needs a PREREG amendment, since H4 and kill criterion 4 are defined over 8 units with 2 seeds. The FT09 S0 pair (58.17 vs 18.11 on two seeds) shows how noisy one seed is.
  - **(D) Stop the ARC path leg after block 2:** report the seed-1 S0-vs-S4 gap and skip the decomposition (H4 untested).
- **Claude's proposal: (B).** It keeps the pre-registered design (all four configs, two seeds) and uses the pre-registered fallback, so it involves no choice of game by us. It needs the smallest raise that keeps that design. At block 2's pace (S0, and likely S1 and S2, near the 12 h clock) it also finishes before G2 (Oct 21) with some margin, back to back in the SEED + 3 order. (A) buys a third game with a sizeable gap (CD82, 66.08) for the decomposition, at about $240 more and about 2.5 more days.
- **What this does not show:** see the summary's own section. In short: one seed per config and game; games chosen for a large published gap; no decomposition yet; and the S1/S2 cost is priced from S0's cost per call, not measured.

**Approval.** This entry's pull request is $0 and adds no spending approval. The researcher's choice, and any change to the 1b cap (`common/costs.py` `PHASE_CAPS`, PLAN §17.3, by dated amendment) and block 3's approval line, go in a follow-up pull request.

**Spend** (billed): block 2 $290.22 of $400 (closed). Phase 1b: $290.22 of $900. Phase 0: $20.57. Phase 1a: $18.15. All phases: $328.94.

## 2026-10-09: Researcher decision after Checkpoint C: the minimal path (PREREG amendment R6, PLAN A7); block 3-arc (S2 on seed 1) proposed by Claude, approved when the researcher merges the PR that adds this entry
**Decision (researcher, 2026-10-09).** The researcher asked for a frank assessment first: what phase 2 is and whether it is needed; the odds of a NeurIPS or ICML paper; what the remaining runs cost and buy. Claude's answer in chat drew on three independent reviewer agents, a venue check and a scoop search. Then the researcher decided, in their words: "Go with the minimal path: luna plus S2 on seed 1, possibly S1, aim at arXiv ahead of Kaggle and TMLR or Agent 2027 short paper. Aim at $560 or so total costs (can overrun a bit)".

**What the merge adopts:**
- **Amendment R6** (`PREREG.md` §17.6) and **A7** (`PLAN.md` §22). They set:
  - **Paid runs left:** gpt-6-luna's replay-off sweep with its controls (block `3-persistgym`, not yet approved), and ARC S2 at replicate 1 on the 4 path games (block `3-arc`, below).
  - **S1** runs only if the researcher records "S1: yes" here, merged to `main`, before the first block-3 ARC run starts. The researcher has recorded it: see "S1: yes" below.
  - **Dropped:** seed 2; sol's H1 replication main runs; phase 2 (StateCarry); the failure labels; the extensions; luna's G1 redesign pass.
  - **H4** is read on the 4 seed-1 units, with S2 alone giving σ_replay.
  - **D20** uses a scaled pilot yardstick for a config's first counted run. The first counted S2 run is an incident only above 431.1 s per call.
  - **luna's T** follows the frozen power rule, capped at 200.
  - **Hard stop** after these runs.
- **Code:** `analysis/arc_h4.py` (H4 per R6) and `analysis/checkpoint_c.py` (R6's D20 yardstick, plus `--d20-run <run_id>`). The block-3 driver calls `--d20-run` after every run.
- **Phase caps** stay as in PLAN §17.3: they remain stop-and-ask ceilings. The ~$560 target is kept through the block limits.

**S1: yes.** In the researcher's words, 2026-10-09, after asking what S1 adds for publishing: "Yes, include S1 on all 4 games." This is recorded before any block-3 ARC run, so S1 at replicate 1 is in the registered readings (PREREG §17.6 changes 1 and 3), and `analysis.arc_h4` runs with `--with-s1`.

**Block `3-arc`: S1 and S2 at replicate 1** (`arc_path`; PREREG §17.6 changes 1, 2 and 5).
- **Order** (the SEED + 3 order with the dropped units deleted, R6 change 2): 1. SB26 S1, 2. FT09 S2, 3. FT09 S1, 4. R11L S2, 5. SB26 S2, 6. CD82 S1, 7. CD82 S2, 8. R11L S1. Each run is `--seed 1`, launched as a process with a console of its own, back to back.
  - After every run the driver calls `uv run python -m analysis.checkpoint_c --d20-run <run_id>`. It starts the re-run right away (`--seed 101 --rerun-of <run_id>`), ahead of the next run, only on `"rerun_allowed": true`. That covers `API_ERROR`, `AGENT_ERROR`, `UNKNOWN`, a final ending whose scorecard cannot be read, and a `TIME_BUDGET` that D20 rules an incident; D19 allows no second re-run.
  - It stops and reports on a hold, a refusal, a missing `meta.json`, too little room, or a `--d20-run` answer of `null`, a non-zero exit or output it cannot parse.
- **Forecast** (D27's rule, the same for S1 and S2: S0's billed cost per call × the larger of the S0 and S4 action counts; `results/checkpoint_c/20261009T151039Z/checkpoint_c.json`): per run, FT09 $47.08, R11L $43.70, SB26 $37.26 and CD82 $44.22. For the 8 runs that is **$344.51 billed**, or $387.57 with block 2's re-run rate (ρ = 0.125). S1 and S2 are likely to reach the 12 h clock, as S0 did on 3 of 4 games.
- **Limit: $470 billed.** Every counted run needs $120 of room under the limit when it starts (§12). At the forecast, the eighth run starts at about $301 of block spend, so it needs at least $421. The rest leaves room for one re-run of about $45. If a run would start with less room, the block stops, and Claude asks.
- **Run guard and hold** as in block 2: $120 at list per run (D22). A run that reaches the guard places a hold.
- **Phase 1b:** $290.22 spent of its $900 cap; the cap is unchanged.
- **Gemini spend limit:** the provider-side limit and the prepaid balance must cover about $470 more. The researcher checks this before the first run.
- **Blinding:** none. These are counted runs.

approved_block: 3-arc | experiments: arc_path | max_usd: 470

**Block `3-persistgym`** is proposed in a later entry, after three things:
- the researcher's G1 spot-check (`results/spotcheck/g1-validity-0-20-3d6bc648/`) and G1 decision;
- the power re-simulation that sets T;
- the $0 code that luna's sweep still needs: a repeat-1 option for `harnesses run`, a runner for the single-turn control with its payload snapshot test, a luna guard in `harnesses/registered.py`, and a G1 metrics script.

Forecast: about $35.52 billed at T = 100 (`results/cost_model/20261003T071449Z/`), and about $71 at T = 200.

**Scoop note** (search of 2026-10-09; done at a checkpoint, not at a gate). VISTA ([arXiv 2610.02200](https://arxiv.org/abs/2610.02200), submitted 2026-10-01, by Han, Hu, Qiu, Wu and He) reports a cumulative harness ladder on ARC-AGI-3 with GPT-5.6 Sol at max effort. Its Figure 5, checked by Claude on arxiv.org on 2026-10-09, gives RHAE:
- sliding window, as in ARC's official harness, with raised action and time limits: 51.66;
- continuous conversation with native compaction: 65.82;
- plus notes files: 70.05.

It reports one model and no seeds, and does not run in ARC's harness. Its compaction step also keeps the conversation, which we read as keeping reasoning, so it does not separate replay from compaction. That makes it a partial overlap, and D31 does not fire. The paper will position against it.

Also new since the 2026-10-06 check:
- [arcprize/arc-agi-3-benchmarking PR #50](https://github.com/arcprize/arc-agi-3-benchmarking/pull/50) (open), a generic Provider Adapter that replays readable reasoning for open models. It makes replay on/off ablations easy for ARC itself.
- [arXiv 2610.12061](https://arxiv.org/abs/2610.12061) (RACE), which ties the value of past reasoning to whether later actions are recoverable. It is a training method, not a harness ablation.

**Approval.** The researcher's merge of the pull request that adds this entry adopts R6 and A7 and the code above, records "S1: yes", and approves block `3-arc` up to $470 billed. It approves nothing for `3-persistgym`.

**Spend** (billed): $328.94 in all (phase 0 $20.57, 1a $18.15, 1b $290.22). The researcher's target was about $560. With S1 added (the researcher, 2026-10-09, told it adds about $172), S1 and S2 at the forecast bring the total to about $673-717, and luna to about $709-787. This entry's pull request is $0.

## 2026-10-09: G1 gate for gpt-6-luna (PREREG §4.4, §10.2): Claude proposes GO
Gate metrics from `uv run python -m analysis.g1` at commit `aeb6d7c` on a clean tree (`results/gates/g1-20261010T001658Z/`). That run includes both $0 audits. The researcher's spot-check findings are committed in the same branch (`results/spotcheck/g1-validity-0-20-3d6bc648/findings.csv`).
- **LLM rates.** luna's validity runs: F-0, validity templates 0-19 × 8 task cells, default config `3d6bc648…`, medium effort, Flex.
  - **Restated-at-need:** 160/160 = 100% (gate ≥ 85%): **met**.
  - **Fact withheld:** 19/160 = 11.9% (gate ≤ 20%, pooled over the 8 task cells; D39): **met**.
  - No episode was excluded, and every episode ended `DONE`.
- **Per-cell withheld rates** are reported, not gated (D39): 0-6 of 20 per cell.
  - derived-nonrec-far stands at 6/20 (30%). Under chance (10%), a single cell reaches 6 or more of 20 with probability 0.011. At least one of 8 cells does so with probability 0.087.
  - The audits and the spot-check found no shortcut in that cell.
  - Noted as a descriptive point for the paper, which reports the withheld rate per cell. It changes no rule.
- **Programmatic oracle and $0 audits** (`persistgym audit`, default preset), on the validity templates 0-19 (480 episodes) and on main templates 0-999 (24,000 episodes):
  - every check passes;
  - the key and text oracles score 1.00 on the base and restated renderings;
  - the highest no-memory baseline is 0.100 (gate ≤ 0.20);
  - the partial-memory gates pass, with 0 narrowing templates.
- **Researcher spot-check:** 160 of 160 episodes reviewed, all `no_shortcut`, with 0 possible shortcuts, 0 shortcuts and no notes. PREREG sets no numeric rule here.
- **Reported only:** gpt-6.1-sol on the default config (R4; its main runs are dropped by R6): restated 80/80, withheld 9/80.
- **Scoop search:** the search of 2026-10-09, recorded in the R6 entry above. VISTA (arXiv 2610.02200) overlaps partially, so D31 does not fire. A per-component ablation under ARC's harness has not appeared.
- **Spend to date:** $328.94 billed (phase 0 $20.57, 1a $18.15, 1b $290.22).
- **Proposal: GO.**
  - G1 releases luna's main sweep: the replay-off cells and controls, block `3-persistgym`.
  - Before that block's approval:
    - the power re-simulation that sets T (R6 change 6: the frozen rule, capped at 200), with W, v and T recorded here;
    - the $0 code: the repeat-1 option, the single-turn control runner with its payload snapshot test, and a luna guard in `harnesses/registered.py`.
  - Under R6 change 7, a NO-GO would stop PersistGym, and the paper would report the ARC leg alone.
- **The researcher makes the go/no-go call.**

## 2026-10-09: G1: GO (researcher)
In the researcher's words, 2026-10-09, after the G1 metrics above: "G1 - go". The researcher made the call after reviewing the 160 spot-check episodes themself and reading the metrics (PR #53).
- **Released:** luna's main sweep (block `3-persistgym`), once these are in place:
  - the power re-simulation sets T (R6 change 6), and W, v and T are recorded here;
  - the $0 runner code is merged;
  - the block's own approval line is merged.
- **Not released:** sol's H1 replication main runs (R6). `REPLICATION_G1_PASSED` stays empty, so those runs still fail closed.

## 2026-10-10: luna's sweep: W, v and T (PREREG §4.2, R6 change 6); near losses (§2.8); the single-turn control's pilot; block 3-persistgym proposed by Claude, approved when the researcher merges the PR that adds this entry
**Values set by the pre-registered rule** (§4.2, as capped by R6 change 6). They are recorded here before any main-split episode of any model.
- **W, v and R_plan:** W = 24,000 tokens and v = 1,500 tokens, from the default generator config `3d6bc648…` (`persistgym/config.py`); R_plan = 1,000 (D5).
- **T = 200.** The frozen rule asks for power ≥ 0.80 for H1 at Δ_H1 = 10pp and for H3 at Δ_H3 = 0, at the worst Holm step of the family of 2 (one-sided 0.025). No T ≤ 200 meets that under either scenario, so R6's cap sets T.
  - Source: `results/power_sim/20261010T030442Z/` (`uv run python -m analysis.power_sim --part luna --reps 2000`). Each of the 2,000 simulated sweeps is analysed per T as §9.1 and §9.4 will analyse the real one, with 10,000 template-cluster bootstrap resamples.
- **Achieved power at T = 200** (P(supported) at the worst Holm step):

  | Scenario | H1 | H3 |
  |---|---|---|
  | Primary | 0.647 | 0.781 |
  | Pessimistic | 0.438 | 0.443 |

  Without the cap, the simulated rule would need T = 290 in the primary scenario. In the pessimistic one, no T up to 300 reaches it.
- **Assumptions** (the researcher's merge approves them; none comes from a pilot outcome or a main-split episode):

  | Parameter | Primary | Pessimistic | Basis |
  |---|---|---|---|
  | F-0 success, observed-far | 0.95 | 0.85 | luna's restated-at-need validity run: 160/160 |
  | F-0 success, derived-NR-far | 0.90 | 0.80 | 5pp below observed |
  | W-0 success, observed-far-NR | 0.12 | 0.18 | luna's withheld validity run: 19/160; 0.18 is its 95% Wilson upper end |
  | Template SD, logit | 0.92 | 0 | ML estimate from luna's withheld validity run (95% interval 0-2.17) |
  | Δ_H1 / Δ_H3 / Holm family | 10pp / 0 / 2 | same | §4.2; the decision of 2026-10-06 |

- **What it means.** H1 has about 0.65 power at its 10pp kill boundary. H1's own prediction is much larger: a non-recoverable penalty ≥ 25pp against a recoverable one ≤ 5pp. The report gives the achieved power, and an H1 or H3 result that is neither supported nor killed is called inconclusive.

**Expected near losses** (§2.8, before the main sweep). Computed with `uv run python -m analysis.near_loss`, committed in this PR. It reads only the survival flag `need_payload.S`, never correctness, and prints only the pooled count (pilot blinding, §11).
- In luna's block-1 window pilots (W-0, W-n-0), 0 of the 8 near episodes lost their evidence.
- So every near window cell is at 0%, under the 2% rule. R_plan and W are not re-tuned.

**The single-turn control** (§3 H3, §4.3).
- **Its prompt now follows §3 H3's frozen text:** each observation is followed by a plain "Agent: <action>" line, with no preamble or marks.
  - The code written before the freeze used a different format. No single-turn prompt had ever been sent, so this brings the code into line with the registered text; it is not a deviation.
  - The control's scorer now recognises the same action verbs as the multi-turn scorer (D4).
- **Its pilot.** CLAUDE.md requires a pilot of at most 10 prompts before a new request type's sweep. R6 change 1 does not list it, so it runs under CLAUDE.md's pilot rule, and the approval line below lists `persistgym_pilot` for it.
  - Shape: luna, pilot split, 2 pilot templates × the 4 non-recoverable task cells = 8 prompts.
  - It sends exactly the sweep's request. About $0.05.
- **Technical choice for the researcher** (§11, like PR #13's): the pilot's committed `summary.json` holds `reply_action_classes`, which says, per reply, whether its action uses the need verb, a routine verb, another verb or none.
  - This bounds the arm's pilot success from above. For example, 0 need-verb replies would mean 0 correct.
  - It is committed because the pilot's purpose is to check the control's validity: does luna answer the need EVENT in a prompt that holds about 24 EVENTs?
  - If it answers an earlier one instead, the control scores 0 for a reason unrelated to memory, which would bias H3 toward "supported".
  - Pilot data are excluded from all analyses.
- **Rule after the pilot.** The single-turn main runs proceed only if all 8 replies are in the need-verb class. Otherwise Claude stops before them, and the researcher decides, for example by amending the control's format. The harness-cell runs do not depend on the pilot.

**Block `3-persistgym`.**
- **Runs** (PersistGym stream, one at a time, each launched as a process with a console of its own; OpenAI Flex; luna at medium effort; main split, templates 0-199, all 8 task cells):
  1. the single-turn pilot (8 prompts);
  2. F-0, W-0, W-n-0 and Σ-n-0, and F-0 restated: 1,600 episodes each;
  3. the single-turn control: 800 prompts;
  4. each of these again at repeat 1, on templates 0, 10, …, 190: 160 episodes each, or 80 prompts for the single-turn control.
- **Forecast:** about **$71 billed**. These are the block-1 pilot costs per episode at Flex (`results/costs.csv`), scaled to T = 200:

  | Run | Forecast |
  |---|---|
  | F-0 | $6.9 |
  | W-0 | $22.9 |
  | W-n-0 | $24.3 |
  | Σ-n-0 | $6.1 |
  | F-0 restated | $7.4 |
  | Single-turn | ≤ $3.4 |

  The window cells' pilot rows played warm caches, so cold runs may cost more.
- **Limit: $100 billed.** Each run's `--planned-usd` is about 1.5× its forecast, and each run stops at it. The ARC stream runs alongside under its own lock.
- **Flex:** when Flex is unavailable, the driver waits 30 min and retries, with a night fallback, as in block 1.
- **Phase 1a:** $18.15 spent of its $500 cap.

approved_block: 3-persistgym | experiments: persistgym,persistgym_pilot | max_usd: 100

**Approval.** The researcher's merge of the pull request that adds this entry adopts W, v, T and the assumptions above, the near-loss result, the single-turn prompt, the technical choice and the pilot rule. It also approves block `3-persistgym` up to $100 billed.

**Spend** (billed): $328.94 before block 3. Block `3-arc` so far: $16.60 (SB26 S1 $13.12, FT09 S2 $3.47), with the FT09 S2 re-run in progress. This entry's pull request is $0.

## 2026-10-10: luna's sweep closed; the H1/H3 analysis and the researcher's rulings, made before any result is read
**Block `3-persistgym` is complete.** All 13 runs ended `COMPLETED` with 0 excluded episodes or prompts. The block cost $73.71 billed of its $100 limit (`results/costs.csv`).
- **The single-turn pilot** (`persistgym_pilot`): `20261010T055627Z-single-turn-gpt-6-luna`. 8 prompts, all 8 replies of the need-verb class, so the pilot rule passed.
- **Repeat 0:** 1,600 episodes per harness run and 800 single-turn prompts.

  | Run | Run ID |
  |---|---|
  | F-0 | `20261010T055742Z-F-0-gpt-6-luna` |
  | W-0 | `20261010T073840Z-W-0-gpt-6-luna` |
  | W-n-0 | `20261010T084438Z-W-n-0-gpt-6-luna` |
  | Σ-n-0 | `20261010T100804Z-sigma-n-0-gpt-6-luna` |
  | F-0 restated | `20261010T113553Z-F-0-gpt-6-luna` |
  | Single-turn | `20261010T125241Z-single-turn-gpt-6-luna` |

- **Repeat 1:** 160 episodes per harness run and 80 single-turn prompts.

  | Run | Run ID |
  |---|---|
  | F-0 | `20261010T125444Z-F-0-gpt-6-luna-repeat1` |
  | W-0 | `20261010T130303Z-W-0-gpt-6-luna-repeat1` |
  | W-n-0 | `20261010T131136Z-W-n-0-gpt-6-luna-repeat1` |
  | Σ-n-0 | `20261010T132132Z-sigma-n-0-gpt-6-luna-repeat1` |
  | F-0 restated | `20261010T133022Z-F-0-gpt-6-luna-repeat1` |
  | Single-turn | `20261010T133738Z-single-turn-gpt-6-luna-repeat1` |

- **The sweep is closed.** No continuation (harnesses/DESIGN.md §7.9) and no §13 re-run is pending or will be made. This entry is the sweep's closing entry: the `--sweep-closed` reference of `analysis.persistgym_h1h3`.

**The analysis:** `analysis/persistgym_h1h3.py` in this PR, the pre-registered H1/H3 analysis.
- It was written and tested on synthetic data only.
- Two independent reviews checked it, one for fidelity to PREREG and one for the statistics, and their findings were applied.
- No one has read any result of the sweep. The luna driver logged only endings, counts and cost. The builders read only `meta.json` files and the field names of one record per run.
- Its readings of points PREREG leaves open are listed in the module docstring ("As implemented").

**The researcher's rulings** (2026-10-10, before any result is read):
1. **H1's model check when the logit-scale Δ_H1 is not finite.** This happens when an H1 cell has no outcome variation, which is likely, since F-0 scored 160/160 on restated-at-need. The model check reads the W-0 × R coefficient of a **Firth-penalized fit** of the same §9.1 model on the same rows (`H1_SEPARATION_RULE = "firth"`). In the researcher's words: "Firth for H1".
   - When the logit-scale Δ_H1 is finite, the ordinary fit decides as before.
   - Not in force: "literal" (the sign of the limit) and "probability-scale". The summary reports what each would have said, labelled as sensitivity lines.
2. **The §9.1 GLM's harness levels:** F-0 and W-0 on all 8 task cells, as H1 defines its comparison. The fit with W-n-0 as a third level is a sensitivity analysis. This was proposed by Claude, and the researcher's merge confirms it.

**The Bayesian sensitivity model** (§9.1) runs with `bambi`, added to `pyproject.toml` and `uv.lock` in this PR: bambi's default priors, 4 chains × 1,000 draws after 1,000 tuning steps, seed SEED + 11.

**Next:**
- Once this PR is merged, Claude runs the analysis once on the sweep (FINAL: the 13 runs listed above, with this entry as the closing reference). It commits the output to `results/persistgym_h1h3/<UTC>/` and reports to the researcher.
- The sweep's run folders and costs rows are committed after block `3-arc` ends. Committing them now would change files the live ARC runs read.

**Approval.** The researcher's merge of the pull request that adds this entry adopts the rulings above and closes the sweep. It adds no spending approval. This entry's pull request is $0.

## 2026-10-10: Block 3-arc paused; the researcher's option B: the S1/S2 summary budget (PREREG amendment R7, PLAN A8)
**What happened.** Three S2 runs of block `3-arc` ended `AGENT_ERROR` because ARC's harness summary came back empty 4 times in a row:
- FT09 S2 `20261010T020247Z-S2-ft09-s1`, at action 49;
- its D19 re-run `20261010T030159Z-S2-ft09-s101`, at action 112, with 5 levels cleared; it is counted as is under D19;
- R11L S2 `20261010T084933Z-S2-r11l-s1`, at action 29.

Each summary request has an 8,192-token output budget, and the model's reasoning at high thinking counts against it. The largest output per attempt reached 8,183 tokens.
- **S1:** SB26 S1 made 33 summaries, all on the first try. FT09 S1 made 7, one of which needed a retry. Both won.
- **S4 in block 2:** 132 summaries, none needing a retry, at most 3,073 output tokens per attempt.

Claude put two options to the researcher:
- **A:** continue as registered.
- **B:** raise the budget by amendment, and replace the runs lost to it.

**Decision (researcher, 2026-10-10):** "go with B for ARC". Claude stopped the block-3 driver between runs at 14:01 ET, without stopping the run in progress. The R11L S2 D19 re-run, seed 101, was left to finish under the pre-R7 config.

**What the merge adopts** (PREREG §17.7, R7; PLAN §23, A8):
- **Patch 0018:** S1's and S2's `summary_max_output_tokens` goes to 65,536. S0 and S4 are unchanged. The freeze record and §7.1's tables are regenerated:
  - S1 `cd475ca0…`, S2 `c41dc494…`;
  - series `40ec95ec…`, patched commit `b716253e…`, tree `ca0a64fe…`.
- **The replacement rule:** a unit whose counted S1/S2 run ended by the summarizer failure gets one R7 replacement, with seed label replicate + 200 and `--r7-replaces`. Its own D19 re-run, if needed, uses replicate + 300.
- **Runs, under the R7 config, back to back:**
  1. FT09 S2, replacing `20261010T030159Z-S2-ft09-s101`;
  2. R11L S2, only if its seed-101 re-run also ends by the summarizer failure;
  3. CD82 S1, CD82 S2 and R11L S1, in R6's order.
- **Waiver:** the paid pilot of the two re-frozen configs is waived (R7 change 6).
- **The driver procedure:** after every run, the driver calls `analysis.checkpoint_c --d20-run`. It starts a re-run only on `rerun_allowed: true`, with the `rerun_seed` that call gives. Otherwise the procedure is as in the block-3 entry above.

**Update, 2026-10-10 15:51 ET:** the R11L S2 D19 re-run `20261010T103451Z-S2-r11l-s101` ended `ACTION_BUDGET`, with no summarizer failure in its log, billed $35.00. It stands as R11L S2's counted run, so R11L S2 gets no R7 replacement. The R7 runs are therefore FT09 S2 (the replacement), CD82 S1, CD82 S2 and R11L S1.

**Cost.** Block `3-arc` has spent $77.94: SB26 S1 $13.12, FT09 S2 $3.47 and $13.79, FT09 S1 $6.13, R11L S2 $6.43 and $35.00. The 4 R7 runs are forecast at about $45 each at D27's rule, about $180. That fits the $470 limit; the limit is unchanged.

**Approval.** The researcher's merge of the pull request that adds this entry adopts R7 and A8, patch 0018 and the regenerated freeze record, the run list and the pilot waiver. It adds no spending approval beyond block `3-arc`'s existing $470. This entry's pull request is $0.

## 2026-10-10: Correction to the closing entry of luna's sweep: one §13 re-run
**The error.** The entry "luna's sweep closed; the H1/H3 analysis and the researcher's rulings" (merged in PR #55) said that no §13 re-run was pending. That was wrong. Claude had checked only the runs' endings (`COMPLETED`) and exclusion counts (0), not each episode's ending.
- One episode of the 9,680 had ended `API_ERROR`: `main-000138/derived-nonrec-far/base` in the F-0 run `20261010T055742Z-F-0-gpt-6-luna`.
- The cause was a Flex 429: "Flex processing is temporarily unavailable".
- `analysis.persistgym_h1h3` found it on its first run and refused, before computing anything: "1 of 1600 repeat-0 episodes are pending ... §13 re-runs it once". No result of the sweep was read.

**The re-run** (researcher's go-ahead, 2026-10-10: "go ahead"). PREREG §13 re-runs a transport failure once.
- The run, under block `3-persistgym`: `harnesses run --cell F-0 --model gpt-6-luna --split main --start 138 --n 1 --experiment persistgym --approved-block 3-persistgym --planned-usd 0.5`.
- Template 138's F-0 episodes in all 8 task cells, the whole template as the luna guard requires: run `20261010T202127Z-F-0-gpt-6-luna`, `COMPLETED`, $0.04 billed.
- Under harnesses/DESIGN.md §7.8 the first final record of each key counts. So this run supplies only the record of `main-000138/derived-nonrec-far/base`, and its 7 other episodes are duplicates that are dropped.

**The analysis declares it:** `--rerun 20261010T202127Z-F-0-gpt-6-luna=20261010T055742Z-F-0-gpt-6-luna`, with this entry and the closing entry as the `--sweep-closed` reference. The sweep is now closed with this re-run, and nothing else is pending.

**Spend:** block `3-persistgym` $73.75 of $100. This entry's pull request is $0.

## 2026-10-10: H1's model check: the Firth fit's iteration cap, a code defect found after the result was read; both outputs reported (the researcher's decision)
**What happened.** The FINAL analysis of luna's sweep, `results/persistgym_h1h3/20261010T205230Z/` (commit 313d57d), labelled H1 "inconclusive". The Holm test rejected, but the model check did not agree.
- Under the ruling of 2026-10-10 ("Firth for H1"), the check reads the W-0 × R coefficient of a Firth-penalized fit of the §9.1 GLM, because the ordinary fit's coefficient is not finite.
- `firth_fe_logit` returned "the Firth fit did not converge", and the module reads a failed fit as "does not agree".

**The cause: the iteration cap.** The fit's steps use the likelihood's Fisher information, not the Hessian of the penalized log-likelihood, so they converge linearly, not quadratically.
- On luna's sweep, with 12 of the 16 cells of the GLM at 100%, the fit needed **103 steps** to reach its tolerance (the largest step under 1e-8). The cap was 100.
- After 100 steps the W-0 × R coefficient was already 7.0862 (7.08616 at convergence), and its last step was 1.4e-8 against the 1e-8 tolerance. Every step was a full step: the fit moved steadily to the same point and never needed step halving. (The fix commit's message says 102 steps; it counted from zero.)
- On synthetic sweeps of the same shape at 200 templates, the fit needed between 65 and 150 steps in the draws checked.

**Seen before the fix:** everything in the FINAL output, among it H1's and H3's results, the Bayesian GLMM and the sensitivity lines. The fix was made after the result was read, and every report says so.

**Decision (researcher, 2026-10-10):** "fix Firth and report both".

**The fix** (commit 0dbff43, in this PR).
- `firth_fe_logit`'s `max_iter` goes from 100 to **1,000**. The tolerance, the steps, the rows, the model and the rule are unchanged.
- A new test, `test_firth_converges_on_a_sweep_at_its_ceiling`, reproduces the failure on a synthetic sweep of luna's shape: the old cap returns None (that case needs 108 steps), and the new one converges to a stationary point of the penalized log-likelihood, written afresh in the test, that no direction tried increases.
- The analysis tests pass (317).
- **Independent check** (a separate agent, on the real rows, with no code from `firth_fe_logit`): an exact Newton and trust-region maximisation, with its own analytic gradient and Hessian and the log-determinant by `slogdet`, gave W-0 × R = **7.086161**, against `firth_fe_logit`'s 7.086161 (a difference of 2e-7).
  - Its penalized log-likelihood at the optimum, -177.5840163, is the same, and its largest gradient there is 4e-13.
  - The Hessian of minus the penalized log-likelihood is positive definite there (smallest eigenvalue 0.0044), so the point is a strict local maximum. A second start, from a random point, reached the same point.
  - A third check (L-BFGS-B) reached the same penalized log-likelihood, with slopes within 8e-6.

**The two outputs.** The second, `results/persistgym_h1h3/20261010T214137Z/` (commit 0dbff43), ran with the same inputs, arguments and seeds.

| Output | Firth W-0 × R | H1's model check | H1 | H3 |
|---|---|---|---|---|
| `20261010T205230Z`, as computed | did not converge | does not agree | inconclusive | inconclusive |
| `20261010T214137Z`, with the fix | +7.086 | agrees | **supported** | inconclusive |

- **Everything else is the same**, field by field in `h1h3.json`: Δ_H1, Δ_H3, every interval, the Holm tests, the predictions, the sensitivity lines and the exploratory results. The one exception is the Bayesian GLMM.
- **The Bayesian GLMM did not reproduce the FINAL's digits.** Its code, seed and data are unchanged.
  - The FINAL run gave a W-0 × R posterior median of 5.280 (90% [2.980, 7.457]); the corrected run gave 5.253 (90% [2.857, 7.523]). P(> 0) = 1.000 both times.
  - Four later fits gave 5.253 to every digit: the corrected run, an audit agent's fit and two fits in one scratch process. So the fit is deterministic now, and the cause of the FINAL's different digits was not found.
  - Each later fit logged 2 divergent transitions after tuning, out of 4,000 draws. The module does not record divergences.
  - It is a sensitivity model that decides nothing, and it agrees in sign either way.
- **H3 is unchanged by this fix:** "inconclusive" in both outputs, with its non-inferiority prediction holding. Its model check returned no estimate for a different reason, which Claude has put to the researcher separately: only 1 of the 200 templates has any failure in H3's cells, and the module fits nothing with fewer than 2 such templates.

**Which output counts.** Claude proposes:
- The corrected output gives H1's confirmatory label: **supported**. The ruling chose Firth's estimate, and the corrected run computes it; the as-computed label came from the iteration cap, not from the data or the rule.
- Every report of H1 also gives the as-computed label, the cause and that the fix came after the result was read.
- H3 is not part of this decision.

**Reporting defects found in the review, not fixed here.** None changes a number or a label.
- When the Firth fit fails, `summary.md` prints "n/a" without the reason; the reason was only in `h1h3.json`.
- `summary.md` prints "the same sign as the model check" even when the check has no sign. In the FINAL output it says this of the stand-in, the W-n-0 fit and the Bayesian GLMM, when the model check had no sign.
- The "power_sim emulation" cross-check of the §9.1 GLM did not run independently: power_sim's Newton fit diverged and fell back silently to statsmodels, so it compares statsmodels with itself.
- The Bayesian GLMM's divergences are not recorded.

Claude proposes fixing these together with H3's question.

**What it does not show.** The fix does not change H1's evidence. The effect, its interval and the Holm test are the same in both outputs; only the label's second condition changes. A reader who discounts any change made after seeing the data should read H1 as in the first output: "inconclusive, the model check failed to converge", with the same effect.

**Approval.** The researcher's merge of the pull request that adds this entry adopts the fix and the proposal above. The researcher may instead keep the as-computed label as H1's confirmatory one, with the corrected run as a labelled sensitivity line. It adds no spending approval. This entry's pull request is $0.

## 2026-10-10: H3's model check with one template with outcome variation, a code limit found after the result was read; both outputs reported (the researcher's decision); the summary's wording
**What happened.** H3 read "inconclusive" in the FINAL output and in the Firth-fixed output (`20261010T205230Z`, `20261010T214137Z`). Its Holm test rejected, but its model check had no estimate, which reads as "does not agree".
- **The check, as §9.4 registers it:** a binomial GLM with template fixed effects and the arm (single-turn vs F-0) on the H3 cells, whose probability-scale Δ_H3 must be below 5pp. That Δ_H3 is the arm's average marginal effect (AME), reading 15.
- **The data:** the single-turn control scored 400/400 and F-0 399/400. Only template 145 has outcome variation: its F-0 derived-nonrec-far episode failed.
- **The fit:** `fe_logit_fit` refused any fit with fewer than 2 templates with outcome variation. So no model was fitted, and the check had no estimate.

**The cause.** The two-template minimum is not in PREREG.
- It came from power_sim's `h3_glm_ame`, where it serves the cluster-robust standard error, whose G/(G − 1) factor needs two clusters.
- The check reads only the point estimate. §9.1 says only the GLM's sign and point estimate enter a decision.
- With two or more templates the module already reads statsmodels' point estimate, including its stopping point under separation.
- With no template varying, the old code gave an AME of 0, which agrees. So the old rule agreed with zero failing templates and did not agree with one.
- Claude's earlier statement to the researcher, that the model "can't be fitted at all" at the ceiling, was wrong. An audit agent found the guard.

**Seen before the fix:** everything in both earlier outputs. The fix was made after the result was read, and every report says so.

**Decision (researcher, 2026-10-10):** "At the very least H3 should be treated as H1: fix the rule and report both. It is nonsense to report "inconclusive" when the prediction clearly holds."

**The fix** (commit bb188ce, with the review's fixes in 5c41d3e, in this PR).
- **One template is enough to fit the model** in `fe_logit_fit` and `h3_glm_powersim`. The model, rows, rule and threshold are unchanged.
- **Still two templates** for the cluster-robust Wald quantities, which are absent with one, and for the Firth fit and the H1 stand-in. Neither of those arises on luna's sweep, where H1's GLM has 194 templates with outcome variation.
- **New tests:** H3 at the ceiling with one failing template; the emulation's route; a failed Firth fit's summary text; the one-template summary text; and the Bayesian divergences. The new tests fail on the old code. The analysis tests pass (319).
- **Reviews:** a fidelity review against PREREG and a code review found no blocker. Their findings are applied in 5c41d3e.
- **Independent check:** a separate agent selected the rows itself and refitted the model three ways: statsmodels through a formula, its own Newton fit, and the analytic limit. With no code from the module, it got:
  - the AME over all 400 pairs: **1/400 = +0.25pp**, equal to the observed Δ_H3;
  - the AME over the 2 pairs of template 145: 0.5;
  - the arm's logit: +∞. statsmodels stops at 20.57; the AME is within 1e-11 of its limit once the logit passes 20.
  - power_sim's model (with a derived-cell term) gives the same 1/400 in the limit.
  - The module's values agree to 6e-12.
- **Sensitivity:** a Firth fit of the same H3 model gives an arm logit of 1.61 (logit of 2.5/3, Firth's add-a-half on the saturated template) and an AME of +0.17pp. So the label does not depend on reading statsmodels' stopping point.

**The summary's wording** (bb188ce and 5c41d3e; the reporting defects listed in the entry above). No number changes.
- The summary now gives the reason when a fit has no estimate.
- It says "no sign to compare" where an estimate has no sign. In both earlier outputs the W-n-0 sensitivity fit's line said "the same sign as the model check", although that fit's limit is undefined (∞ − ∞). In the FINAL output the stand-in's and the Bayesian GLMM's lines said the same, although the model check had no sign.
- It says that power_sim's emulation of the §9.1 GLM fell back to statsmodels, so it is no independent check.
- It records the Bayesian GLMM's divergent transitions: 2 after tuning, out of 4,000 draws.
- It says that H3's check is saturated with one template (below), and that power_sim's own H3 check gives no estimate there.
- The achieved-power caveat no longer claims a direction (it said "may overstate").
- Its header lists the changes made after the FINAL output was read.

**The three outputs**, with the same inputs, arguments and seeds:

| Output | Commit | H1's model check | H3's model check | H1 | H3 |
|---|---|---|---|---|---|
| `20261010T205230Z`, as computed | 313d57d | Firth did not converge | no estimate | inconclusive | inconclusive |
| `20261010T214137Z`, Firth fix | 0dbff43 | Firth +7.086, agrees | no estimate | **supported** | inconclusive |
| `20261010T232227Z`, both fixes | 5c41d3e | Firth +7.086, agrees | **+0.25pp**, below 5pp | **supported** | **supported** |

- **Field by field in `h1h3.json`,** the third output differs from the second only in H3's model check and verdict, the new fields and the wording. Δ_H1, Δ_H3, every interval, the Holm tests and the exploratory results are the same in all three. The Bayesian GLMM reproduced the second output's digits.
- **An intermediate run at bb188ce** (`20261010T223420Z`) had every number of the third and the older wording. It was superseded by the review's wording fixes and is not kept.

**Which output counts.** Claude proposes:
- The third output, `20261010T232227Z`, gives both confirmatory labels: H1 supported, H3 supported.
- Every report also gives the as-computed labels ("inconclusive" for both), the two causes and that both fixes came after the result was read.
- This replaces the proposal in the entry above, which named the second output.

**What it does not show.**
- **The evidence is unchanged.** Δ_H3 = +0.25pp (1/400), 90% CI [0.0, 0.75]pp, and the Holm test are the same in all three outputs; the summary rounds these to +0.2 and +0.7. Only the label's second condition changes.
- **H3's model check adds nothing here.** With one template varying, the model is saturated in it, so its AME is the observed Δ_H3 by construction. The check cannot disagree with the bootstrap's point estimate. Its agreement rests on reading 15, made blind, which averages over all 400 pairs; averaged over the informative pairs only, the AME is +50pp.
- **The quoted achieved power** describes the design's scenarios, not this sweep, and supports neither label.
  - In power_sim's own scenarios, a review agent's re-simulation (4,000 sweeps per scenario) found no sweep with one or fewer templates varying in H3's cells.
  - power_sim's own H3 check gives no estimate on luna's data, so the simulated rule would reproduce the as-computed "inconclusive".
- **Both arms are at the ceiling.** H3 bounds the cost of multi-turn structure at luna's level on these tasks. It cannot see a cost that would appear on harder tasks.
- **Changes made after seeing the data.** A reader who discounts them should read H1 and H3 as in the first output: "inconclusive", with the same effects.

**Approval.** The researcher's merge of the pull request that adds this entry adopts the fix, the wording changes and the proposal above. It adds no spending approval. This entry's pull request is $0.

## 2026-10-10: H5 analysis: two rulings proposed before any H5 quantity is computed
**The analysis:** `analysis/arc_h5.py` in this PR, the pre-registered H5 analysis (PREREG §3 H5, D35, §17.6 change 4), on the published high-effort runs and on our 8 seed-1 counted S0 and S4 runs.
- It was written and tested on synthetic data only. No H5 quantity has been computed on real data: its real-data tests check the pinned file's hash, count rows per effort, game and harness, and match the 8 counted run IDs.
- Two independent reviews checked it, one for fidelity to PREREG and one for the statistics, and their findings were applied.
- Its readings of points PREREG leaves open, and the two places where it differs from the spec it was written from, are listed in the module docstring ("As implemented").

**Proposed rulings** (Claude's, for the researcher):
1. **The estimator that decides H5** (`PRIMARY_ESTIMATOR = "ml_limit_or_firth"`). PREREG §3 H5 registers a logistic regression, read by maximum likelihood. With one run per game and harness, separation is expected: a game's harness will often have cleared every reached level of a band, or none.
   - The rule reads the average marginal effects in the limit of the maximum-likelihood fit wherever C = A_deep − A_early is identified there, also under separation. Where C is not identified (or the ML fit fails), that reading or bootstrap resample uses Firth's penalized fit, and each such resample is counted by reason.
   - This has the form of H1's ruling of 2026-10-10: "When the logit-scale Δ_H1 is finite, the ordinary fit decides as before", with Firth only where it is not.
   - **The alternative, `"firth"`**, applies Firth's penalty everywhere. It uses one estimator in the point estimate and every resample. But it changes the registered ML estimate even on data without separation, and it gives a game with no outcome variation a non-zero difference. On small synthetic designs of 4 games, the two estimators can give C opposite signs.
   - Both estimators are reported in every output, and the summary and `meta.json` name the rule in force.
2. **The bootstrap seed:** SEED + 40, the next free offset (used: +2 and +3 the run orders; +10 the H1/H3 bootstrap; +11 the Bayesian GLMM; +20 the failure labels; +30 H4).

**Next:** once this PR is merged, Claude runs the analysis once. The output is FINAL with 10,000 resamples, the pinned published file and the 8 counted runs. Claude commits it to `results/arc_h5/<UTC>/` and reports to the researcher.

**Approval.** The researcher's merge of the pull request that adds this entry adopts the two rulings above. The researcher may instead choose `"firth"` before the first run (one constant in the module). It adds no spending approval. This entry's pull request is $0.

## 2026-10-11: H5 results (FINAL), the independent check, and the summary's wording after it
**The run.** Claude ran `analysis.arc_h5` once on the merged code (PR #58), with the researcher's rulings: `ml_limit_or_firth`, and SEED + 40. The researcher confirmed them in chat ("Rulings are fine").
- The output is `results/arc_h5/20261011T041028Z/` (commit 93d34f0), FINAL: 10,000 resamples, the pinned published file and the 8 counted seed-1 S0/S4 runs. $0.
- H5 is descriptive (§9.4). Every verdict is on the point estimate.

**Results** (A_b: the Adapter-minus-Standard average marginal effect in P(clear | reached) in band b; C = A_deep − A_early; 90% game-cluster bootstrap intervals):

| Reading | A_early | A_deep | C | 90% interval of C | Decided by |
|---|---|---|---|---|---|
| Published, high effort (registered) | +0.136 | +0.439 | **+0.304** | [+0.164, +0.458] | ML limit (Firth: C = +0.264) |
| Same, error endings dropped (sensitivity) | +0.136 | +0.357 | **+0.221** | [+0.051, +0.409] | ML limit (Firth: +0.194) |
| Ours, S0 vs S4, 4 games (registered) | +0.000 | +0.749 | **+0.749** | [+0.667, +1.000] | Firth (ML limit not identified) |

- **Both registered readings are positive, as H5 predicts.** The published reading is positive under both estimators. The verdict is descriptive.
- **Published raw rates** (cleared/reached):
  - early: Standard 39/47, Adapter 47/50;
  - level 3: Standard 11/17, Adapter 21/22;
  - deep: Standard 15/26, Adapter 63/75.
- **Ours:** early 8/8 for both. Deep: S0 0/2, S4 11/11.
- **Ours, the ML limit:** C is not identified there because of CD82. CD82's S0 never reached a deep level, all its other rows were cleared, and S0's only deep rows (FT09 and SB26, level 4) were not. The ML-limit C lies between +0.769 and +1.000 depending on the path, so it is positive on every path.
- **Exploratory** (§9.10; sign only, no verdict):
  - published medium effort: C = +0.317 (Firth);
  - published low effort: C = +0.255 (Firth);
  - common support, the published games where both harnesses reached a deep level: C = +0.396 (11 games).
  - All are positive.

**The independent check.** Two separate agents recomputed the readings from the raw files without the module's code: the published `per_run.csv`, and our runs' scorecards.
- The band and per-level tables agree exactly.
- Both estimators' A_early, A_deep and C agree to about 1e-7.
- With the same seed and draw procedure, every bootstrap interval agrees to 8 decimals: the rule in force, Firth's, and the ML limit's over the resamples where it is identified.
- The count of resamples where the ML limit is not identified agrees: 263 published and 6,255 ours. The error-ending sensitivity's dropped rows and C agree too.

**The summary's wording after the FINAL output.**
- **What happened:** a wording review of `summary.md` found no overclaim but several omissions.
- **The change** (commit 5cdc2c4): the module now states these as caveats computed from the data, with tests.
- **The second output:** `results/arc_h5/20261011T055415Z/` has the same numbers field by field (only metadata and three new fact fields differ: `facts`, `contrast_by_source`, `defined_drawing_game`) and the revised text.
- **Proposal:** Claude proposes the second output as the one to cite. The first is kept.

**What it does not show** (both outputs; the second states it in its summary):
- **At most one uncleared row per run.** Levels are played in order, so a run's only uncleared row is the level it stopped on.
  - In the published runs, all 25 Standard runs stopped on a reached level; 9 Adapter runs won.
  - So the band rates largely restate where runs stopped and which runs won. The rows are not independent trials.
- **The logit scale.** On the published runs the logit-scale interaction's 90% intervals include 0 under both estimators: Firth [−0.73, +1.94], ML limit [−0.55, +2.71].
  - Standard's early-band rate (0.830) leaves less room than its deep-band rate (0.577).
  - So the published result does not separate "the advantage grows with depth" from "a constant logit-scale advantage, compressed where rates are high".
- **Not blind.** The published reading is in effect computed on seen data: the operational slice revealed each run's last level, and these are the runs whose gap motivated the study and selected the path games. Our runs were seen before R6.
- **Our runs are thin and selected.**
  - C rests on 2 S0 deep rows: FT09 and SB26, level 4, both budget endings.
  - The replaced FT09 S0 original cleared levels 4 and 5.
  - The 4 games were chosen as ones where the Adapter helps.
  - With 4 games there are only 35 distinct resamples.
- **Extrapolation.** 29% (published) and 23% (ours) of the deep rows are in games where only one harness reached a deep level, through the model's counterfactual.
- **Error endings.** Four of Standard's 11 published deep failures are inferred error or close endings. Without them C is +0.221.
- **Conditioning on reached** compares the harnesses over different runs. A_deep is not the effect on clearing a fixed level.

**Approval.** The researcher's merge of the pull request that adds this entry adopts the second output's wording as the one to cite. No number changes. It adds no spending approval. This entry's pull request is $0.

## 2026-10-11: H5 discussed; an exploratory compaction analysis added to the plan (PLAN A9)
**Decision (researcher, 2026-10-11):** "let's do an exploratory look at whether S1/S2 runs fail soon after a history compaction ... At least put it into the plan." PLAN §24 (A9) defines it before its data are tabulated: the windows, the readings and what has been seen. It is exploratory (§9.10), $0, and runs after block `3-arc` ends, with H4. It changes no hypothesis, run, gate or budget.

**Approval.** The researcher's merge of the pull request that adds this entry adopts PLAN A9. It adds no spending approval. This entry's pull request is $0.

## 2026-10-12: Block 3-arc complete; the sweep and block data committed
**The R7 runs, in order:**

| Run | Run ID | Ending | Levels | Billed | D19 |
|---|---|---|---|---|---|
| FT09 S2, the R7 replacement | `20261010T202129Z-S2-ft09-s201` | `ACTION_BUDGET` | 3 of 6 | $21.46 | no re-run |
| CD82 S1 | `20261011T030015Z-S1-cd82-s1` | `AGENT_ERROR` | 2 of 6 | $9.62 | re-run |
| CD82 S1, its D19 re-run | `20261011T053855Z-S1-cd82-s101` | `AGENT_ERROR` | 4 of 6 | $21.90 | none further |
| CD82 S2 | `20261011T105637Z-S2-cd82-s1` | `ACTION_BUDGET` | 2 of 6 | $30.76 | no re-run |
| R11L S1 | `20261011T205715Z-S1-r11l-s1` | `ACTION_BUDGET` | 2 of 6 | $36.57 | no re-run |

- **No summarizer failure** occurred under the R7 budget.
- **Both CD82 S1 runs ended `AGENT_ERROR`** because the model returned 4 unusable replies in a row:
  - the first run: empty text;
  - the re-run: empty text, or function calls the harness never offered (`developer/display_pixel_diff`, `google.thought`).
  - This is not the R7 cause, so the re-run is counted as is under D19.
- **The researcher's pause for a computer restart** (option B, 2026-10-11): Claude stopped the driver while CD82 S2 played, without stopping the run, and resumed it for R11L S1 after the restart.

**Cost.** Block `3-arc`: $198.26 billed of $470 (11 `costs.csv` rows). Project total: $600.94 billed.

**Committed in this PR:**
- the 13 luna run folders (`results/persistgym/`) and the single-turn pilot;
- the 11 block-3 ARC run folders (`results/arc_path/`);
- their `costs.csv` rows.

Raw transcripts stay in `results/raw/` (gitignored).

**Next ($0):** H4's FINAL analysis with S1 (`analysis.arc_h4 --with-s1`), the PLAN A9 compaction analysis, and the G2 entry (Oct 21).

**Approval.** No spending; the block is closed. This entry's pull request is $0.
