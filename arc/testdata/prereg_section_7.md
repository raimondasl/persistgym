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
- **Cost guard:** the D22 guard ($120 per counted run, §7.7) is not in the profiles. The paid launcher sets it at run time (patch 0010's `MAX_RUN_COST_USD`), so the config hashes below do not cover it; each run's `meta.json` (`cost_cap_usd`) and `run_meta.json` (`cost_guard`) record it (§0.3, line 12).

**Config freeze record** (PR #21; `arc/config_freeze.json`, written by `uv run python -m arc.config_hash`). For each profile, the patched harness's own `get_model_config` resolves the config, and `config_hash` is the SHA-256 of its canonical JSON (`common.runmeta.config_hash`, the same hash every run's `meta.json` carries). A separate script (not committed) that parses the patched `model_configs.yaml` with PyYAML, not the harness's loader, re-derived all four hashes, and they match (`arc/README.md`). If the block-1 pilot forces a config change, the change is made by amendment "A-cfg" (§17), merged before the first block-2 run.

| Config | Config entry name | `config_hash` (SHA-256) |
|---|---|---|
| S0 | `google-gemini-3-8-flash-high` | `{S0}` |
| S1 | `google-gemini-3-8-flash-high-rolling-summary` | `{S1}` |
| S2 | `google-gemini-3-8-flash-high-rolling-summary-notes-off` | `{S2}` |
| S4 | `google-gemini-3-8-flash-high-provider-adapter` | `{S4}` |
| S3 (optional) | none: no profile is built or frozen | none; S3 runs only if an amendment first adds and freezes its profile (§0.3, line 13) |

Shared by all four configs:

| Item | Value |
|---|---|
| Upstream harness | `arcprize/arc-agi-3-benchmarking`, pinned at `{pin}` (`{pin7}`) |
| Patch series | `arc/patches/0001-*.patch` to `0017-*.patch`, the 17 files listed in `arc/config_freeze.json` |
| Patch-series SHA-256 | `{series}` |
| Patched commit | `{commit}` |
| Patched tree | `{tree}` |

**Checks behind the record** (PR #21, `arc/README.md`): `apply_patches.py --each` ran the upstream unit tests after every patch: 872 passed after 0017. The only failure was the known flaky upstream test `test_recorder::test_concurrent_recording`, once after 0015 in that run and once in another full-suite run after 0017, both with other test runs loading the machine. It passes on its own, and no patch touches the recorder. The $0 offline runs with a stub model passed for S0, S1, S2 and S4 (`offline_smoke.py --toy`), and so did the launcher's inner modes (`run_path_offline.py`). The paid launcher refuses any run whose patch files, patched commit or tree, or resolved profile hash differ from this record (§12).

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
