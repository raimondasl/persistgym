# Decisions log

Gate decisions, approvals and the numbers behind them (CLAUDE.md "Milestone and gate discipline"). Newest at the bottom. The researcher makes every go/no-go and spending call; Claude proposes.

## How approvals are recorded
A paid block (PLAN.md §16.2) can spend only after the researcher adds one approval line to this file, under that day's entry. The paid guard (`common/approval.py`) reads the line; it never writes one. The grammar, with this exact spacing:

```
# grammar only: indented here and with <placeholders>, so it never counts as an approval
    approved_block: <name> | experiments: <exp1>,<exp2>,... | max_usd: <amount>
# example only, never counts for the same reasons
    approved_block: <example-block> | experiments: toggle_pilot,replay_probe | max_usd: 2.50
```

- A real line starts at column 0: no list marker, indentation, quote or backticks. Only trailing whitespace is ignored. A line inside a fenced code block or an HTML comment never counts, so a gate entry can show a proposed line in a code block without approving anything.
- `<name>` matches `[A-Za-z0-9._-]+`. Each experiment is a key of `EXPERIMENT_PHASE` in `common/costs.py`, or starts with `ext_`. The list is comma-separated with no spaces. `<amount>` is a positive number of US dollars such as `76` or `2.50`, with no `$`, sign, exponent or thousands separator. A line that breaks a rule never counts.
- The line counts only when the same line is in this file on `origin/main` (the guard runs `git fetch origin main` first and refuses if the fetch fails), in the checked-out `HEAD` and in the working tree. Removing or changing it in any of the three revokes the approval. Keep one line per block: two different lines for one block are refused. To change a limit, edit the line; the new line counts once it is merged.
- A run is allowed only for an experiment in the list, and only while the block's spend plus the run's planned spend is at most `max_usd`. Block spend is the sum, over `results/costs.csv` rows whose notes contain `approved_block=<name>;`, of `cost_usd_billed_est`, or of `cost_usd_list` for a row with no billed estimate. So `max_usd` is in billed dollars, like the caps and forecasts in PLAN.md (D23): on Flex, the Flex price. A run measures its own spend the same way and stops at its planned spend. The phase caps (PLAN.md §12) still apply, measured the same way. Paid calls also need `PREREG.md` in `HEAD` to be the one on `origin/main`.

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
