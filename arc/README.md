# arc/: the pinned ARC-AGI-3 harness and our patches

ARC Prize's harness, [arcprize/arc-agi-3-benchmarking](https://github.com/arcprize/arc-agi-3-benchmarking) (MIT), is a git submodule at `arc/upstream`, pinned at commit `4ca00e607e3364a501fcbf7d1b7537dd2729cec3` (2026-09-21). Our changes are not committed inside the submodule. They live as numbered `git format-patch` files in `arc/patches/`, one concern each, so they can be reviewed, re-applied and offered upstream.

| Path | What it is |
|---|---|
| `upstream/` | The submodule. Its checkout should stay at `4ca00e6`. |
| `patches/NNNN-*.patch` | Our patch series, applied in order with `git am`. |
| `apply_patches.py` | Applies the series in a scratch worktree under `arc/.work/` and runs the upstream unit tests there. |
| `no_dotenv_plugin.py` | pytest plugin that turns `load_dotenv()` into a no-op during harness tests (see Safety). |
| `test_apply_patches.py` | Root-suite tests: the pin, patch numbering, test coverage per patch, env sanitizing, a clean apply. |
| `conftest.py`, `.gitignore`, `.gitattributes` | Keep the submodule and `arc/.work/` out of the root test run and out of git; keep patch files byte-exact. |

Nothing here calls a model API or needs a key. All harness tests use mocked HTTP.

## Setup
```bash
git submodule update --init arc/upstream     # checks out exactly 4ca00e6
uv run arc/apply_patches.py                  # apply all patches, run upstream unit tests
uv run arc/apply_patches.py --each           # ...and test after every patch
uv run arc/apply_patches.py --no-tests       # only check that the series applies (~1 s)
uv run arc/apply_patches.py --keep           # keep arc/.work/patched for inspection
```

`apply_patches.py` creates `git worktree add --detach arc/.work/<name> 4ca00e6` from the submodule, runs `git am --committer-date-is-author-date` on every patch with a fixed committer, runs `uv sync --locked` and `pytest tests/unit` there, then removes the worktree unless `--keep` is given. It prints the patch-series SHA-256 and the patched commit and tree IDs. The same series always gives the same IDs. On 2026-09-30 these were series `82580ebc…`, commit `b464c55d…`, tree `93573770…`.

### Test results (Windows, Python 3.12.13, no keys set)
| Tree | Result |
|---|---|
| Upstream at `4ca00e6`, `uv sync --locked && uv run pytest -q` in `arc/upstream` | 634 passed, 10 skipped. The 10 skipped are the paid live tests in `tests/integration`, which skip unless `RUN_*_LIVE_TESTS=1`. |
| After 0001 / 0002 / 0003 / 0004 / 0005 (`apply_patches.py --each`, `tests/unit` only) | 642 / 654 / 695 / 700 / 721 passed |

The pin already has 2 ruff findings (`I001` in `benchmarking/model_config.py`) and 21 strict-mypy errors in `benchmarking/`. The patches add none of either.

## Patch series (part A)
Line numbers refer to the pinned `4ca00e6`.

| # | Patch | Concern | Upstream code it changes | New tests |
|---|---|---|---|---|
| 0001 | Record exit reason in run_meta.json for every ending | `ExitReason` was only logged by `Swarm`. `Agent.main` sets `API_ERROR`/`AGENT_ERROR` and re-raises without `cleanup()` (`base.py:112-114`), and `Swarm.close_scorecard` can rewrite reasons after agents have finished (`swarm.py:143-160`). | `RunRecord` gains `exit_reason` (`recording.py:132`). `_write_run_meta` (`agent.py:493`) syncs it. `BenchmarkingAgent.main` persists it before an error propagates. `cleanup()` (`agent.py:1146`) rewrites it after swarm reclassification. | `test_exit_reason_run_meta.py` (8) |
| 0002 | Add `agent.carry_forward_instruction` flag | The notes sentence is hard-coded in `_build_system_prompt` (`agent.py:281-298`; the sentence is at :292 and :297) and is re-added by the `analysis_mode` branch (:290). | New optional boolean, default `true`. `false` removes the sentence in `manual_rolling` and `previous_response_id`, including under `analysis_mode`. Prompts with the flag on are byte-identical to before. `continuous_conversation` rejects `true`. | `test_carry_forward_instruction.py` (12) |
| 0003 | Validate and record `request.service_tier` | Request-block keys already reach the SDK as kwargs: Google Interactions `_build_call_kwargs` (`runtime_adapters.py:443`) and OpenAI Responses/Chat (`:108`, `:95`). Nothing checked the value or recorded the tier actually served. | Config validation against the pinned SDK literals. `ModelResponse.service_tier` (`runtime_models.py:61`) is filled from Interactions/Responses/Chat responses. Step records store the reported tier and `run_meta.json` stores `requested_service_tier`; both are omitted when unset. A tier mismatch is logged. | `test_service_tier.py` (41) |
| 0004 | Add Gemini 3.8 Flash high profiles for both harnesses | Only the low Provider Adapter profile is checked in (`model_configs.yaml:269-294`). | S0 and S4 config entries (below). Adds one README sentence. | `test_gemini_path_configs.py` (5) |
| 0005 | Add payload snapshot tests | (tests only) | Full JSON request bodies per config and step (below). | `test_gemini_path_payloads.py` (21) |

`service_tier` values: google-genai 2.4.0 Interactions accepts `flex | standard | priority` (`google/genai/_interactions/types/interaction_create_params.py:93`, echoed on `Interaction.service_tier`). openai 2.41.1 Responses and Chat accept `auto | default | flex | scale | priority` (`openai/types/responses/response_create_params.py:192`, `openai/types/chat/completion_create_params.py:257`). Unset sends no field, so the provider's default tier applies, as in every checked-in upstream config. Harness-summary compaction deep-copies the action request settings (`compaction.py:74-87`), so summary calls request the same tier; snapshot test 0005 checks this. The xAI adapter and the Anthropic and generate_content runtimes are not validated.

## Path configs
| Config | ID | Where it comes from |
|---|---|---|
| S0 = Standard | `google-gemini-3-8-flash-high` | Patch 0004. `manual_rolling` on the Interactions API (`google-genai`/`interactions`), `MAX_CONTEXT_LENGTH` 175,000 (chars at 1 char/token; drop-oldest), notes sentence on (default), `thinking_level: high`. |
| S1 | (part B) | `SummaryCompactor` wired into `manual_rolling`; `MAX_CONTEXT_LENGTH` raised so drop-oldest never fires. |
| S2 | (part B adds the config entry) | S1 plus `agent.carry_forward_instruction: false` (patch 0002). |
| S4 = Provider Adapter | `google-gemini-3-8-flash-high-provider-adapter` | Patch 0004. The checked-in `google-gemini-3-8-flash-low-provider-adapter` with only `thinking_level: high` changed: `continuous_conversation`, `harness_summary` compaction at 175,000 provider tokens, 8,192-token summary cap, 8,192 headroom, `MAX_CONTEXT_LENGTH` 1,048,576. |

S0 and S4 share the client, pricing ($0.75/$3.75 per M, valid through 2026-12-31) and the whole request block: `store: false`, `max_output_tokens: 65536`, `thinking_level: high`, `thinking_summaries: auto`. Two settings are our choices, not ARC's:
- **`thinking_summaries: auto` in S0.** It keeps the request identical across the path, so S2→S4 changes only state and replay. In S0-S2 the summaries are written to local step files and ARC's action metadata but are never sent back to the model; snapshot 0005 checks this. The published Standard recordings carry no reasoning summary (`docs/background.md` §4), so ARC's Standard-high run probably did not request summaries. The researcher can drop the setting from S0 before the config hashes are frozen.
- **`store: false` in S0**, matching S4.

`service_tier` is unset in both profiles. Per PLAN §16.4, one tier is chosen for all ARC configs by the pre-registered latency rule, and the frozen configs then get `request.service_tier` set (patch 0003 makes that value validated and recorded).

### What the snapshot tests pin down (patch 0005)
The tests run `BenchmarkingAgent.main()` on a scripted 2×2 game through the real google-genai SDK over `httpx.MockTransport`. The mock provider answers every call with a signed thought step plus visible text, so a leak would show. The tests compare each request's full JSON body:
- **S0:** the system instruction contains the notes sentence. `input` holds only `user_input` and `model_output` text items, never `thought` items, signatures or summaries. The oldest user/assistant pair is dropped once the estimate exceeds `MAX_CONTEXT_LENGTH`. Provider usage ≥ 175k never triggers compaction.
- **Notes-off (part A's stand-in for S2):** the S0 profile with `carry_forward_instruction: false`. Requests are identical to S0 except the system instruction, which then equals S4's. The flag also wins over `analysis_mode`. When part B checks in S1/S2, this test should switch to the checked-in S2 entry and add its compaction steps.
- **S4:** every earlier `thought` step (with its `signature`) and `model_output` is replayed as the SDK parsed it. The SDK adds `"annotations": null` to text parts. At the 175k trigger the harness sends one summary request with system prompt `SUMMARY_SYSTEM_PROMPT`, the full native history including thoughts, and `max_output_tokens` 8,192. Later turns restart from a user-role bridge message, and the summary call's own thought is not carried forward.
- **All configs:** every request has `thinking_level: high`, `thinking_summaries: auto` and `store: false`. Without `service_tier` the field is absent. With it, it is present on every request, including summary requests, and the bodies are otherwise unchanged.

## Confirming S4 against ARC's published runs
ARC did not check in a Gemini high Provider Adapter profile, so S4 is a reconstruction. What can be checked from public data:
1. **Config tag and model.** `GET https://arcprize.org/api/sessions/{guid}` returns `"config"` and a `config_…` tag. The published Gemini high Adapter sessions report `"config": "google-gemini-3-8-flash-high-provider-adapter"` and `"model": "gemini-3.8-flash"`; the Standard sessions report `google-gemini-3-8-flash-high`. (Read from session JSON already cached under `results/raw/arc_public/sessions/` in the main checkout, e.g. `0b43e4ff-…` and `484de130-…`.) Our IDs match these tags exactly. The session record carries no request settings.
2. **Per-step metadata in the recordings.** `GET https://arcprize.org/api/recordings/{game_id}/{guid}` holds the action metadata the harness sends with each step: usage, cost and reasoning, plus a `state` block on Provider Adapter runs (`input_items_sent`, history sizes, `harness_compaction` usage and cost). A committed script in the free-analysis track should check, on the published high Adapter runs:
   - **Trigger.** A step's metadata sums its retries, and on the step after a compaction it also includes the summary call. So compute each step's action total as `usage.total_tokens` minus `state.harness_compaction.usage.total_tokens`, when the latter is present. Every compaction should follow a step whose action total is ≥ 175,000. The converse can only be expected on steps without retries, and the metadata does not mark retries.
   - **Summary cap.** `harness_compaction` output tokens never exceed 8,192, and the cap is sometimes hit.
   - **Pricing.** Each step's cost equals `input × 0.75 / 1e6 + output × 3.75 / 1e6`.
   - **Thought summaries.** `reasoning` is non-empty on most steps, which fits `thinking_summaries: auto`.
   - **Native replay.** Between compactions, `input_items_sent` grows by at least 3 per turn (user input, thought, output).
   - **Output cap.** No step exceeds 65,536 output tokens. This is a weak check: it fails only if ARC used a different cap and a step hit it.
3. **Thinking level.** `thinking_level` is not visible anywhere. Indirect check: reasoning tokens per action in our S4 pilot should be in the published high-Adapter range (about 6.1k mean, `docs/background.md` §4) and clearly above the low-Adapter runs.
4. **If any check disagrees,** record the difference in `results/decisions.md`. Either fix S4 before the config hashes are frozen in PREREG, or ask ARC Prize for the exact profile; contacting ARC is the researcher's call.

Steps 1-3 do not show that ARC used `MAX_CONTEXT_LENGTH` 1,048,576, the 8,192 headroom or `max_output_tokens` 65,536. These come from the low profile and are assumed.

## Exit reasons in this harness
`run_meta.json` now always has `exit_reason`. The names are upstream's (`base.py:18-25`). Their meaning in this code, which matters for the PLAN §8.3 re-run rule:
- `GAME_WIN` (`agent.py:736`), `ACTION_BUDGET` (per-level budget at `agent.py:749`, or the total-action fallback at `base.py:117`), `TIME_BUDGET` (12 h wall clock, `base.py:97`).
- `API_ERROR` means an exception while submitting the action to the **ARC** environment (`take_action`). It does not mean a model API error (`base.py:113`).
- `AGENT_ERROR` means any other exception in the loop. This includes the **model** call failing after `MAX_RETRIES` (`agent.py:1098`) and compaction failures.
- `SCORECARD_CLOSED` means an `API_ERROR` agent whose scorecard was closed server-side (404 on close while the card exists; `swarm.py:153-156`). If closing the scorecard fails any other way, upstream marks every agent `API_ERROR`, even winners (`swarm.py:157-160`). With 0001 that is now visible in `run_meta.json`; `outcome` and the per-level results still show the win.
- `UNKNOWN` means the run is still in progress, or the process died before recording an ending.

## Changing or adding patches
```bash
cd arc/upstream
git checkout -b dev 4ca00e6
git am ../patches/*.patch                 # recreate the series as commits
# edit; amend the commit for the concern you are changing, or add a new commit
uv run pytest -q tests/unit               # upstream tests (no keys; see Safety)
rm ../patches/*.patch
git format-patch 4ca00e6..HEAD -o ../patches
git checkout --detach 4ca00e6             # leave the submodule at the pin
cd ../.. && uv run arc/apply_patches.py --each
```
Use one commit per concern, each with tests in `tests/unit/` (`arc/test_apply_patches.py` enforces this). End each commit message with the Co-Authored-By line. Edit files with LF line endings. Part B continues the numbering from 0006.

## Safety
- **No paid calls.** Every test uses fake adapters or `httpx.MockTransport`. Live tests skip unless `RUN_*_LIVE_TESTS=1` is already set.
- **No `.env` loading.** The upstream `tests/conftest.py` and live tests call `load_dotenv()` with no path. python-dotenv 1.1.1 (pinned upstream) then searches the calling file's directory and its parents, so from `arc/upstream/tests` it would find a `.env` at the repository root. This was checked offline with a throwaway `.env`. `apply_patches.py` therefore loads `no_dotenv_plugin.py` (`-p no_dotenv_plugin`). It also drops every variable that looks like a credential, every provider-prefixed variable (`OPENAI_`, `GOOGLE_`, `GEMINI_`, `ARC_`, …), and `RUN_*_LIVE_TESTS`. If you run `pytest` inside `arc/upstream` by hand, do it only when no `.env` exists above it.

## Not in part A
- **S1** (`SummaryCompactor` in `manual_rolling`; `model_config.py:345-352` currently rejects `runtime.compaction` outside `continuous_conversation`) and the **S1/S2 config entries.** These are part B.
- Other patches listed in PLAN §16.3: offline/local-server play, transport-level 429/503 backoff that does not use up `MAX_RETRIES`, and an optional per-run cost guard.
- **Upstream since the pin.** `main` is at `09a307b` (DeepSeek and Grok adapters); it is not pulled. Its 6-line `compaction.py` change only matters for adapters that implement the new `PendingCompactionInputs` protocol, and only `deepseek_runtime.py` does. `google_runtime.py` and `agent.py` are unchanged between `4ca00e6` and `09a307b`. So the change is a no-op for S4. Part B's S1 compactor can decide separately whether to keep unpresented observations out of summaries.
- **Flex timeouts (read from code).** `runtime_clients.py:75` builds `google_genai.Client(api_key=...)` with no HTTP options. The resulting Interactions client has no client-side timeout and 3 SDK-level retries (checked offline). The OpenAI client defaults to a 600 s read timeout and 2 retries. Flex targets 1-15 min per call ([Gemini Flex](https://ai.google.dev/gemini-api/docs/flex-inference)), so wall-clock time, not client timeouts, is the binding limit for Gemini.
