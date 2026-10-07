# Background: verified facts and related work

_Compiled 2026-09-30 from three independent premise checks (see `premise-check.md`) plus spot re-checks the same day. Every outside claim carries a URL. Where a claim comes from our own processing of public data, the method is stated._

**Changes on 2026-09-30 (second pass).** A later check the same day added or corrected the facts below. Sources are inline. Items marked _(low confidence)_ or _(medium confidence)_ rest on third-party reports, ambiguous docs, or our reading of code that we have not run. Most provider pages were read through a summarizing fetch tool, so re-open the page before any number from it goes public. `PLAN.md` §16 (Amendment A1) draws the budget and schedule consequences.
- **§1:** the ARC API is free during its research preview (600 requests per minute). A registered key unlocks all 25 public games. The official `arc-agi` toolkit can run them offline. Added the scoring formula.
- **§2:** harness `main` moved to `09a307b`; our pin stays at `4ca00e6`, and code links now point to the pin. The harness hard-codes online play and has no mock or offline agent. Exit reasons never reach ARC; a rule infers them from per-level budgets.
- **§4:** the "11 of 25 early endings" count and the cheap-run eligibility filter need re-checking against per-level budgets.
- **§5:** OpenAI and Microsoft Azure docs disagree on `all_turns` for gpt-6-luna. Added effort values and defaults, `reasoning.mode`, and the lack of dated snapshots.
- **§6:** OpenAI bills cache writes at 1.25×. Added OpenAI usage tiers, Gemini tier spend caps and the pause rule, Gemini Flex latency (no fallback), Gemini free-tier limits and data use, and 3.8 Flash's medium default thinking. The $300 Google Cloud credit does not cover the AI Studio Gemini API on accounts opened after Mar 2, 2026.
- **§8:** added "how each published run ended" to the open questions for ARC.

**Changes on 2026-10-07.** §1: ARC's methodology page, how resets count as actions, and where the 12 h clock is set, for `PREREG.md` §17.5 (amendment R5). The methodology page was read through a summarizing fetch tool; the toolkit and harness code were read directly.

## 1. ARC-AGI-3 basics
- **Game sets:** 25 public (demo) games, 55 Semi-Private and 55 fully private. Public games have 6-10 levels ([ARC-AGI-3 technical report](https://arxiv.org/html/2603.24621v1); the [harness README](https://github.com/arcprize/arc-agi-3-benchmarking/blob/main/README.md) says "there should be 25").
- **Action budget:** the harness allows 5× the human-baseline actions per level. Human-baseline actions per public game (summed over levels) range from 171 to 1,843, median 638. The baselines come from the session API, see §4.
  - The budget is enforced per level. A run stops when the current level's action count reaches ceil(5 × that level's baseline), not when total actions reach the summed budget (`is_done` and `_level_action_budgets` in [agent.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/benchmarking/agent.py)).
- **Scoring:** RHAE per game, which weights later levels more heavily ([technical report](https://arxiv.org/html/2603.24621)).
  - In the toolkit's code, a cleared level scores min((baseline / actions)² × 100, 115) and an uncleared level scores 0. The game score is the mean weighted by level index, capped at the weighted share of cleared levels × 100 ([scorecard.py](https://github.com/arcprize/ARC-AGI/blob/main/arc_agi/scorecard.py), read 2026-09-30). Local and server scoring use the same formula.
  - Check (2026-09-30, from the cached LP85 Standard-high session in §4): its `level_scores` give a weighted mean of 80.05. Seven of eight levels were cleared, so the cap is 28/36 × 100 = 77.78, which is the published score.
  - ARC's methodology page states the squared ratio, the per-level cap at 1.15 times the baseline and the weighted average with the 1-indexed level number as the weight; it says an action is an interaction that affects the game state, and does not mention resets ([methodology](https://docs.arcprize.org/methodology), checked 2026-10-07).
  - **Resets count as actions** (arc-agi 0.9.8, the version the pinned harness's `uv.lock` resolves, read 2026-10-07). The opening RESET, which the toolkit sends when the game is made, starts the play and is not counted. Every later RESET adds 1 to both `resets` and `actions` (`Card.inc_reset_count`, `Scorecard.update_scorecard` in scorecard.py), and `level_actions` counts it on the level being played, so `actions` = Σ `level_actions`. Our block-2 run 1 agrees: 206 actions with 4 resets, Σ `level_actions` = 206, and the harness's own action counter, which counts every action it submits, is also 206 (`results/arc_path/20261006T144656Z-S4-cd82-s1/`). `analysis/arc_action_matched.py` reproduces its score exactly with the rule above.
  - **The 12 h clock is the harness's, not the server's:** `MAX_RUNTIME_SECONDS` is 12 h by default and can be set per model config; no checked-in profile sets it ([base.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/benchmarking/base.py), `agent.py` at the pin, read 2026-10-07).
- **Cost of access:** "The ARC-AGI API is currently free to use during its research preview", supported on a best-effort basis ([rate limits](https://docs.arcprize.org/rate_limits)). No paid tier is documented. No terms promise that the preview stays free.
  - ARC Prize receives no money from this project. Every ARC line in `PLAN.md` §12 is model-provider tokens (Gemini, billed by Google) spent while playing ARC games.
- **API key:** `ARC_API_KEY` comes from [arcprize.org/platform](https://arcprize.org/platform). Log in with Google or GitHub, then open the profile, then API Keys, then generate ([API keys](https://docs.arcprize.org/api-keys)). The researcher creates it; Claude does not.
  - Without a key, the toolkit fetches an anonymous key, and anonymous users get three games by default (ls20, ft09 and vc33 are the examples). A registered key unlocks the rest of the 25 public games ([available games](https://docs.arcprize.org/available-games), [local vs online](https://docs.arcprize.org/local-vs-online)).
  - Log hygiene: when `ARC_API_KEY` is empty outside OFFLINE mode, the toolkit logs the anonymous key at INFO level (`Got anonymous API key: ...` in [base.py](https://github.com/arcprize/ARC-AGI/blob/main/arc_agi/base.py)). Always set `ARC_API_KEY` or use OFFLINE mode, so no key reaches our logs.
- **Rate limits:** 600 requests per minute. Above that the API returns HTTP 429, and clients should back off exponentially. More can be requested from team@arcprize.org ([rate limits](https://docs.arcprize.org/rate_limits)).
  - The docs do not say whether the limit is per key, IP or account. They document no daily or per-game quota.
  - LLM latency keeps a run to a few actions per minute, so this limit does not bind.
- **Scorecards:** "Scorecards auto close after 15 minutes" ([scorecards](https://docs.arcprize.org/scorecards)). Since the April 2026 changelog, a scorecard lasts at most 24 hours ([changelog](https://docs.arcprize.org/changelog)).
  - We read the 15 minutes as an idle timeout _(low confidence)_. The harness comment says "closed due to idle/total time limit" ([swarm.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/benchmarking/swarm.py)), and the published LP85 Standard run stayed open about 2 h.
- **Offline play at $0:** ARC's official toolkit is PyPI `arc-agi` (MIT, v0.9.9 of 2026-06-10). The harness already depends on `arc-agi>=0.9.8`. It has four modes: NORMAL, ONLINE, OFFLINE and COMPETITION ([toolkit](https://docs.arcprize.org/toolkit/arc_agi), [local vs online](https://docs.arcprize.org/local-vs-online), [repo](https://github.com/arcprize/ARC-AGI)).
  - In NORMAL mode, `make('lp85')` downloads the game's metadata (including `baseline_actions`) and its Python source into `environment_files/{id}/{version}/`, then runs the game locally ([base.py](https://github.com/arcprize/ARC-AGI/blob/main/arc_agi/base.py)).
  - After that, OFFLINE mode needs no network and no key. The docs claim about 2,000 FPS and no rate limits, with no online scorecards or shareable replays.
  - `Arcade.listen_and_serve(port=8001)` runs a local Flask server with the same REST routes: `/api/games`, `/api/scorecard/open|close|<id>`, `/api/cmd/RESET` and `ACTION1`-`ACTION7`. Its `scorecard_timeout` is configurable ([listen_and_serve](https://docs.arcprize.org/toolkit/listen_and_serve), [server.py](https://github.com/arcprize/ARC-AGI/blob/main/arc_agi/server.py)).
  - Versioned game IDs such as `lp85-305b61c3` (the version in the published session) should let us pin the exact versions the published runs used _(low confidence: read from the code, not tested)_.
  - A third-party offline runner documents the same pattern: a key once to fetch the 25 games, then fully offline ([Prime Intellect](https://github.com/PrimeIntellect-ai/arc-agi-3-prime-agent)).
  - Local play executes game Python code downloaded from arcprize.org, the same code ARC runs on its side for online play. Approving that is the researcher's call. Downloading the games is ARC API use, so throttle and cache it.

## 2. The two ARC harnesses, in code
Source: [arcprize/arc-agi-3-benchmarking](https://github.com/arcprize/arc-agi-3-benchmarking) at commit `4ca00e6` (2026-09-21, MIT). Our pin stays at `4ca00e6`, and the code links in this section point to it. ARC's own description is in [docs/runtime-state.md](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/docs/runtime-state.md).

**Pin status (checked 2026-09-30).** `main` moved past the pin later on 2026-09-30, to `09a307b` ([commits](https://github.com/arcprize/arc-agi-3-benchmarking/commits/main), [diff](https://github.com/arcprize/arc-agi-3-benchmarking/compare/4ca00e6...09a307b)):
- `f6ec31f` (19:30 UTC): "Add streaming support and enable Grok 4.7 provider adapter (#45)".
- `09a307b` (19:46 UTC): "Add DeepSeek Provider Adapter with tool-based reasoning replay (#44)". [PR #44](https://github.com/arcprize/arc-agi-3-benchmarking/pull/44) is now merged.
- The diff does not touch `agent.py`, `base.py`, `swarm.py`, `google_runtime.py` or `openai_runtime.py`.
- It adds 6 lines to `compaction.py`: buffering of pending inputs during harness-summary compaction, used by adapters that implement `PendingCompactionInputs`. It also adds streaming for chat completions in `runtime_adapters.py`.
- `main` still has no Gemini 3.8 Flash high or Standard config and no `gpt-6-astra` config.
- Neither commit is a per-component ablation (no scoop).
- Decision: keep the pin at `4ca00e6`. Check whether S1 (wiring `SummaryCompactor` into `manual_rolling`) needs the `compaction.py` change.

| Aspect | Standard (`manual_rolling`) | Provider Adapter (`continuous_conversation`) |
|---|---|---|
| State | Client-owned plain-text transcript | Replays provider-native items: OpenAI Responses reasoning items with `encrypted_content` (`store:false`); Gemini Interactions thought steps with signatures; Anthropic thinking and signature blocks; xAI encrypted reasoning |
| Reasoning | Only each assistant turn's visible `output_text` is sent back, so reasoning is dropped ([agent.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/benchmarking/agent.py)). Exception: `analysis_mode: true` inlines readable reasoning summaries as `<reasoning_summary>` text and also changes the system prompt ([analysis_mode.md](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/docs/analysis_mode.md)) | Native replay |
| Overflow | Drops the oldest user/assistant pair when the estimated size (chars / 1.0) exceeds `MAX_CONTEXT_LENGTH`, which is 175k in all checked-in Standard configs | Compacts when the previous response's provider-reported `total_tokens` reaches 175k ([compaction.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/benchmarking/compaction.py)). Native compaction for OpenAI, Anthropic and xAI. For Gemini it is a harness summary: a domain-neutral prompt capped at 8,192 output tokens, inserted as one user-role "bridge" message in a fresh state. This ends opaque reasoning continuity for the summarized prefix ([PR #35](https://github.com/arcprize/arc-agi-3-benchmarking/pull/35)) |
| Notes instruction | System prompt includes "Include any context you want to carry forward in your reply, along with the action you want to take." | Removed automatically. runtime-state.md says this "is not a configurable model setting" |
| API surface | Checked-in Standard configs use chat completions (OpenAI; Gemini 3.1 Pro via the OpenAI-compatible endpoint) | Responses (OpenAI, xAI), Interactions (Gemini), Messages (Anthropic) |
| Same in both | Action budget 5× human baseline per level; `MAX_RETRIES=3`; 12h wall clock; up to 7 animation frames per observation; no tool calling (free-text "last action mentioned" or strict JSON `{actions:[...]}`); same scoring. Only the Anthropic Adapter profile enables prompt caching. Published costs are reconstructed from configured prices without cache discounts. | |

**What can be toggled without code changes, and what cannot:**
- **Configurable:** `MAX_CONTEXT_LENGTH`; compaction `trigger_tokens` and summary caps; native vs `harness_summary` compaction (`harness_summary` only for OpenAI and Google); `analysis_mode`; budget multiplier; retries; animation frames.
- **Also available:** `manual_rolling` runs on the google-genai Interactions API and on OpenAI Responses ([runtime_adapters.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/benchmarking/runtime_adapters.py)), so the API surface can be held fixed across harnesses.
- **Not toggleable on its own:**
  - **Replay** is tied to the state strategy. The OpenAI validator requires `reasoning.context='auto'` ([openai_runtime.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/benchmarking/openai_runtime.py)). The Google validator requires `thinking_summaries='auto'` ([google_runtime.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/benchmarking/google_runtime.py)).
  - **The notes instruction** is hard-coded to `provides_continuous_conversation` (`agent.py::_build_system_prompt`).
  - **Compaction** exists only in `continuous_conversation`, and rolling truncation only in `manual_rolling`.
- **Small patches needed:**
  - a notes flag (about one line);
  - wiring `SummaryCompactor` into `manual_rolling`;
  - (not planned) dropping thought or reasoning items before replay.
- **Published configs are not in the repo** (also true at `09a307b`):
  - No `gpt-6-astra` config is checked in, and no Gemini 3.8 Flash Standard config at any effort.
  - The only Gemini Adapter config is `google-gemini-3-8-flash-low-provider-adapter`: `thinking_level: low`, `MAX_CONTEXT_LENGTH` 1,048,576, `harness_summary` at 175k ([model_configs.yaml](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/benchmarking/model_configs.yaml)).
  - Session metadata names the published configs `google-gemini-3-8-flash-high` and `google-gemini-3-8-flash-high-provider-adapter` ([example session](https://arcprize.org/api/sessions/484de130-939a-4773-b771-d0108ed46a56)).
  - Which API surface the published Standard Gemini runs used is unknown.
- **Exit reasons** in the harness: `GAME_WIN`, `ACTION_BUDGET`, `TIME_BUDGET`, `SCORECARD_CLOSED`, `API_ERROR`, `AGENT_ERROR`, `UNKNOWN` ([base.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/benchmarking/base.py)).
  - They are never sent to ARC. Locally they reach only `logs.log`, through the "AGENT EXIT REASON" line in [swarm.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/benchmarking/swarm.py).
  - `run_meta.json` stores only a coarser `outcome` (WIN / GAME_OVER / TIMEOUT / MAX_ACTIONS). It stays null for per-level budget stops and for errors ([recording.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/benchmarking/recording.py)).
  - So our runs need a small patch that writes `exit_reason` into `run_meta.json`, or must parse `logs.log`.
- **Published runs carry no exit reason.** The documented scorecard schema gives each run only a game `state` (NOT_PLAYED / NOT_FINISHED / WIN / GAME_OVER). It also gives `level_scores`, `level_actions`, `level_baseline_actions`, `actions`, `resets` and `completed`. The card has `open_at`, `last_update` and `published_at` ([arc3v1.yaml](https://docs.arcprize.org/arc3v1.yaml), [scorecards](https://docs.arcprize.org/scorecards)).
  - The undocumented session endpoint (§4) returns the same fields plus config tags. One session was checked. Recordings were not checked for end-of-run metadata.
  - **Inference rule** (uses the per-level budget in §1):
    - state `WIN` means `GAME_WIN`;
    - actions on the final level ≥ ceil(5 × that level's baseline) means `ACTION_BUDGET`;
    - `last_update − open_at` ≈ 12 h means `TIME_BUDGET`;
    - anything else is an error or a scorecard close. `API_ERROR`, `AGENT_ERROR` and `SCORECARD_CLOSED` cannot be told apart.
  - **Example:** the published LP85 Standard-high run ([session](https://arcprize.org/api/sessions/484de130-939a-4773-b771-d0108ed46a56)) cleared 7 levels. It then stopped on level 8 after 16 of 795 allowed actions, about 1 h 56 min after opening, with state `NOT_FINISHED`. That is an error- or close-type ending.
    - Level 8 carries 8/36 of the score, so this ending accounts for LP85's whole 22.2-point gap (`PLAN.md` §16.4).
    - Oddity: the session shows `completed: true` while `state` is `NOT_FINISHED`.
- **No mock, random or offline mode.** The CLI ([main.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/main.py)) has only `--game`, `--tags`, `--config`, `--list-games` and `--list-configs`. There is no random or mock agent and no replay of recorded responses. The [README](https://github.com/arcprize/arc-agi-3-benchmarking/blob/main/README.md) and [docs](https://docs.arcprize.org/benchmarking-agent) never mention offline use. What exists for $0 work:
  - **Unit tests** (`uv run pytest`) use synthetic responses and mocked HTTP through the pinned SDKs. Paid live tests are skipped unless flags such as `RUN_GOOGLE_LIVE_TESTS=1` are set, and "Live tests ... do not launch an ARC benchmark" ([tests/README.md](https://github.com/arcprize/arc-agi-3-benchmarking/blob/main/tests/README.md)). These are the template for our payload snapshot tests.
  - **Per-step recordings** store `messages_sent`, `request_record`, the assistant response, reasoning and usage ([recording.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/benchmarking/recording.py)), so exact payloads can be asserted.
  - **A random agent** lives in ARC's separate [ARC-AGI-3-Agents](https://github.com/arcprize/ARC-AGI-3-Agents) repo (`uv run main.py --agent=random --game=ls20`). It uses `Arcade()`, so it honours `OPERATION_MODE`.
- **Online play is hard-coded** _(medium confidence: read from the code, not run)_. `swarm.py` constructs `Arcade(operation_mode=OperationMode.ONLINE)` ([swarm.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/benchmarking/swarm.py)). In the toolkit, that argument beats the `OPERATION_MODE` env var; only COMPETITION overrides it ([base.py](https://github.com/arcprize/ARC-AGI/blob/main/arc_agi/base.py)). So the harness always plays through ARC's remote API. Two $0 routes to local play:
  - **(a) Patch:** change one line to `Arcade()`, which honours `OPERATION_MODE`, or to OFFLINE. OFFLINE is the default in ARC's sibling ARC-AGI-3-Agents repo ([swarm.py there](https://github.com/arcprize/ARC-AGI-3-Agents/blob/main/agents/swarm.py)).
  - **(b) No patch:** serve the games with `Arcade(operation_mode=OFFLINE).listen_and_serve(port=8001)` and set `ARC_BASE_URL=http://localhost:8001`. Both `main.py::build_root_url` and the toolkit read `ARC_BASE_URL` ([main.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/main.py), [.env.example](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/.env.example)). Not run.
  - Known gap for (b): swarm's `_scorecard_exists` calls `/api/v3/scorecards/{id}`, which the local server does not serve. It runs only after a failed close.
  - Each model config takes a `base_url` ([model_configs.yaml](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/benchmarking/model_configs.yaml)), so chat-completions configs can point at a local stub model server. With a local game server, that allows full games end to end with canned responses at $0.
  - Not checked: whether the google-genai Interactions client can be redirected the same way.
- **Recent activity:** adapters were added on Sep 15 (Gemini), Sep 19 (xAI) and Sep 21 (Anthropic). #45 (streaming, Grok 4.7) and #44 (DeepSeek) were merged on Sep 30 (see Pin status).

## 3. Published ARC-AGI-3 numbers (Semi-Private set, 55 games)
**GPT-6 Astra** ([results page](https://arcprize.org/results/openai-gpt-6-astra); [blog, Sep 3 2026](https://arcprize.org/blog/astra)). Exact values come from the JSON embedded in the results page.

| Reasoning effort | Standard | Provider Adapter |
|---|---|---|
| max | 62.71% ($26,098, ~$475/game) | 98.55% ($17,332) |
| xhigh | 59.34% | 98.44% |
| high | 54.82% | 99.95% ($18,817, ~$342/game) |
| medium | 38.59% | 98.44% |
| low | 17.45% | 98.03% |
| "none" | 35.18% | 96.72% |

- The headline "62.7% vs 99.9%" compares different efforts (max vs high). At matched effort the gap is 35.8pp at max and 45.1pp at high.
- The blog reports no ablation.
- The "none" label is ambiguous. [OpenAI's reasoning docs](https://developers.openai.com/api/docs/guides/reasoning) say GPT-6 Astra does not support `none` effort. Do not read that row as "the Adapter wins without reasoning" until ARC clarifies it.

**Gemini 3.8 Flash** ([results page](https://arcprize.org/results/google-gemini-3-8-flash)). Cost per game is ARC's no-cache list accounting.

| Effort | Standard | Provider Adapter | Gap |
|---|---|---|---|
| high | 10.37% (~$80/game) | 35.00% (~$82/game) | +24.6pp |
| medium | 3.99% (~$50/game) | 24.20% (~$70/game) | +20.2pp |
| low | 5.99% (~$49/game) | 15.07% (~$57/game) | +9.1pp |

The gap grows with reasoning effort.

**Other cheap models:**
- **GPT-6 Luna** is at the floor under both harnesses: Standard 0.03-0.19%, Adapter 0.05-0.59%, about $4/game ([results](https://arcprize.org/results/openai-gpt-6-luna)). Luna on ARC would measure noise.
- **GPT-6 Sol** reaches 4.62% vs 23.03% only at max, for $101-159/game ([results](https://arcprize.org/results/openai-gpt-6-sol)).
- **No ARC-AGI-3 score:** DeepSeek V4 Flash-0731, Kimi K3, GLM-5.3 Flash and Gemini 3.5-3.7 Flash have results pages but no ARC-AGI-3 score ([results index](https://arcprize.org/results)).

**OpenAI's own attribution** ([OpenAI, "How enabling two settings tripled our scores on the ARC-AGI-3 benchmark", Jul 29 2026](https://openai.com/index/how-two-settings-tripled-our-arc-agi-3-scores/)):
- GPT-5.6 Sol went from 13.3% with the official harness to 38.3% on the public set with **retained reasoning** plus **compaction** in place of rolling truncation, using about 6× fewer output tokens.
- Only the combined number is given.
- Our fetcher got HTTP 403 on 2026-09-30. The content was confirmed through search results and secondary coverage, e.g. [ai-tldr](https://ai-tldr.dev/releases/openai-arc-agi-3-two-settings-jul29/).

## 4. Public-set runs you can download for free
arcprize.org serves every public-set run shown on its results pages from unauthenticated endpoints:
- `GET https://arcprize.org/api/sessions/{guid}`: config tag, `level_actions`, `level_baseline_actions`.
- `GET https://arcprize.org/api/recordings/{game_id}/{guid}`: NDJSON, one record per step. Each has the frame, the model's visible output, the reasoning summary (Adapter only), usage (input, cached, output and reasoning tokens) and cost.
- Example: [session](https://arcprize.org/api/sessions/484de130-939a-4773-b771-d0108ed46a56), [recording](https://arcprize.org/api/recordings/lp85-305b61c3/484de130-939a-4773-b771-d0108ed46a56), [replay viewer](https://arcprize.org/replay/484de130-939a-4773-b771-d0108ed46a56).
- The session GUIDs are linked from the [results page](https://arcprize.org/results/google-gemini-3-8-flash).

**Gemini 3.8 Flash, high effort, public set: one published run per game and harness.**
- Pulled and aggregated by the premise check on 2026-09-30.
- Score = per-game RHAE.
- Cost is ARC's no-cache list accounting.
- Sorted by gap.

| Game | Std score | PA score | Gap | Std $ | PA $ | Std actions | PA actions | Human baseline actions |
|---|---|---|---|---|---|---|---|---|
| SB26 | 2.8 | 100 | 97.2 | 29.32 | 17.01 | 156 | 126 | 213 |
| FT09 | 14.3 | 100 | 85.7 | 28.73 | 8.01 | 126 | 83 | 208 |
| VC33 | 21.2 | 100 | 78.8 | 86.99 | 39.70 | 367 | 370 | 447 |
| SU15 | 12.1 | 89.5 | 77.4 | 100.03 | 48.47 | 477 | 232 | 361 |
| RE86 | 27.8 | 100 | 72.2 | 48.73 | 86.50 | 264 | 840 | 1255 |
| R11L | 22.6 | 89.7 | 67.1 | 54.75 | 34.99 | 232 | 234 | 233 |
| G50T | 0 | 62.7 | 62.7 | 73.30 | 181.49 | 390 | 929 | 879 |
| AR25 | 45.9 | 100 | 54.1 | 144.75 | 26.03 | 717 | 275 | 748 |
| TN36 | 10.7 | 64.3 | 53.6 | 42.87 | 90.89 | 168 | 567 | 317 |
| M0R0 | 7.7 | 59.9 | 52.2 | 161.07 | 165.49 | 1268 | 1346 | 1107 |
| SC25 | 24.7 | 71.4 | 46.7 | 39.95 | 46.73 | 222 | 394 | 350 |
| CD82 | 4.8 | 39.9 | 35.2 | 11.68 | 29.01 | 60 | 207 | 171 |
| SP80 | 14.3 | 47.6 | 33.3 | 29.21 | 66.72 | 150 | 577 | 518 |
| TU93 | 4.4 | 33.3 | 29.0 | 38.84 | 112.39 | 212 | 522 | 462 |
| WA30 | 16.1 | 43.3 | 27.2 | 294.71 | 241.41 | 2172 | 2556 | 1843 |
| LP85 | 77.8 | 100 | 22.2 | 24.33 | 11.34 | 132 | 108 | 388 |
| S5I5 | 77.8 | 100 | 22.2 | 101.75 | 33.63 | 643 | 330 | 638 |
| SK48 | 2.8 | 15.1 | 12.4 | 122.93 | 196.50 | 549 | 1493 | 1070 |
| KA59 | 3.6 | 14.9 | 11.3 | 68.01 | 88.12 | 571 | 811 | 730 |
| DC22 | 47.6 | 54.6 | 7.0 | 212.33 | 209.23 | 1324 | 1820 | 1228 |
| TR87 | 0 | 4.8 | 4.8 | 68.20 | 36.59 | 270 | 321 | 414 |
| CN04 | 30.3 | 34.2 | 3.9 | 128.67 | 194.76 | 589 | 1698 | 789 |
| BP35 | 0 | 0.1 | 0.1 | 21.86 | 70.98 | 105 | 334 | 651 |
| LF52 | 1.8 | 1.8 | 0.0 | 85.41 | 77.37 | 413 | 413 | 1339 |
| LS20 | 10.7 | 5.4 | −5.3 | 43.70 | 63.11 | 271 | 629 | 776 |

**Observations from the same pull (high effort unless noted):**
- **Scores and cost:**
  - Mean per-game score is 19.3 (Standard) vs 57.3 (Adapter). At low effort it is 10.1 vs 28.1.
  - Mean cost per game is about $83 (Standard) vs $87 (Adapter); medians are about $68 and $67.
  - Costs range from $8 to $295 per run.
- **Selection:** games where both runs cost ≤ $60 and the gap is ≥ 20 are FT09, SB26, R11L, LP85, SC25 and CD82. These are the eligible pool for the path study (PLAN §8.3).
  - Caveat (added 2026-09-30): the cost filter can select Standard runs that were cheap because they ended early. LP85's Standard run stopped on level 8 after 16 actions (§2); a complete run could cost up to about $168 (`PLAN.md` §16.4).
- **Tokens per action:**
  - Standard averages about 148k input, 15.9k reasoning and 907 visible output tokens per action.
  - The Adapter averages about 137k input, 6.1k reasoning and 200 visible tokens.
  - With replay, the model thinks about 2.6× less per turn and writes much shorter visible "notes".
- **Context size:**
  - The Standard input window plateaus near 165k tokens after about 12 turns. One 64×64 frame is about 12.8k tokens.
  - Example: LP85 Standard runs 12,769 → 25,787 → … → 166,539 input tokens, then stays flat around 165k.
  - Occasional single steps report about double that, e.g. the last LP85 step at 331,668. This may be a retry summed into one usage record, so check before using per-step token numbers.
- **Compaction:** the Adapter compacted 2,611 times in 17,215 actions, about every 6.6 actions.
- **Early endings:** 11 of 25 Standard-high runs ended before exhausting the action budget without a win, vs 5 of 25 for the Adapter.
  - Possible causes are `AGENT_ERROR` after failed parses, API errors, or the time budget.
  - This confound in the published gap has to be logged via exit reason in any rerun.
  - Added 2026-09-30: this count predates the per-level budget rule (§1, §2). It must be recomputed with that rule (`PLAN.md` §16.3).
- **Tokens per game:**
  - Standard-high: about 70M input and 8M output.
  - Adapter-high: about 95M input and 4.3M output.
  - Standard-low: about 56M input and 0.4M output.
  - Adapter-low: about 98M input and 1.0M output.
  - Input dominates because every call re-sends a window of about 130-150k tokens.
- **Caching:** measured cached shares are about 17% (Standard) and 53% (Adapter). At the $0.075 cached price, that would put real per-game cost at about $74 (Standard) and $53 (Adapter) at high. Flex would roughly halve these, if its latency fits ARC's 12 h clock (§6.2).

## 5. How each API handles earlier-turn reasoning
| API / model | Behaviour | Source |
|---|---|---|
| OpenAI Responses | `reasoning.context` ∈ {`auto`, `current_turn`, `all_turns`}; omitting it = `auto`. "The GPT-5.6 model family supports `all_turns` and uses it by default." The values table says "GPT-5.6 models and GPT-6.1 Sol support this value." "Earlier models default to `current_turn`." The guide does not say which mode GPT-6.1 Sol uses by default. The response's `reasoning.context` field reports the effective mode. `all_turns` has an effect only when earlier items can be reached (`previous_response_id`, a conversation, or a full-history replay that includes `encrypted_content`), and it "increases the tokens billed for a request". With `store:false`, reasoning items carry `encrypted_content` you can pass back. **gpt-6-luna:** OpenAI's docs do not list it; Microsoft's Azure docs do (§5.1). | [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning), [reasoning items cookbook](https://developers.openai.com/cookbook/examples/responses_api/reasoning_items) |
| Gemini 3.x | Docs say to always resend thought blocks exactly as received, with no documented bypass. Thought signatures are validated strictly for function calls in the current turn (400 error). A `skip_thought_signature_validator` sentinel exists. Signatures are opaque, so what the model sees can't be inspected. Thinking levels and the 3.8 Flash default: §6.2. | [thinking](https://ai.google.dev/gemini-api/docs/thinking), [thought signatures](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/thought-signatures) |
| DeepSeek thinking mode | Without `tools`, earlier `reasoning_content` is "ignored and will not be concatenated into the context". With `tools` it must be passed back, otherwise the API returns 400. There is no clean on/off within one mode. | [thinking mode](https://api-docs.deepseek.com/guides/thinking_mode) |
| Qwen3.6-27B | `preserve_thinking` via `chat_template_kwargs` (vLLM/SGLang), **off by default**. The card says the model "has been additionally trained to preserve and leverage thinking traces from historical messages." | [model card](https://huggingface.co/Qwen/Qwen3.6-27B) |
| Qwen3.8-27B | `preserve_thinking` is **on by default**. | [model card](https://huggingface.co/Qwen/Qwen3.8-27B) |
| gpt-oss (harmony) | Guidance: drop earlier-turn CoT once a turn ends in a final message; keep it only around tool calls. | [harmony guide](https://developers.openai.com/cookbook/articles/openai-harmony) |
| OpenRouter | Accepts `reasoning` / `reasoning_details` on assistant messages; does not document which providers render them into the template. | [reasoning tokens](https://openrouter.ai/docs/use-cases/reasoning-tokens) |

### 5.1 OpenAI reasoning settings for gpt-6-luna and gpt-6.1-sol (checked 2026-09-30)
| Setting | gpt-6-luna | gpt-6.1-sol | Source |
|---|---|---|---|
| `all_turns`, per OpenAI | Not listed. The reasoning guide mentions Luna only for its effort default. The model page never mentions `reasoning.context` or `all_turns`. | Supported. Default not stated. | [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning), [luna page](https://developers.openai.com/api/docs/models/gpt-6-luna) |
| `all_turns`, per Microsoft Azure OpenAI | Supported and the default. Azure says `all_turns` works with GPT-5.4, GPT-5.5, GPT-5.6 and GPT-6 models, and that GPT-5.6 and GPT-6 models use it by default. | Same | [Azure reasoning](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning) (ms.date 2026-09-21, updated 2026-09-29) |
| `reasoning.effort` values | none, low, medium, high, xhigh, max | low, medium, high, xhigh, max. "GPT-6.1 Sol does not support `none` or `minimal`." | [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning), [luna page](https://developers.openai.com/api/docs/models/gpt-6-luna), [sol page](https://developers.openai.com/api/docs/models/gpt-6.1-sol) |
| Default effort | medium | medium | [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning): "GPT-6.1 Sol, GPT-6 Sol, and GPT-6 Luna also default to `medium` reasoning effort." |
| `reasoning.mode` | `standard` or `pro`, on the Responses API, for GPT-5.6 and GPT-6 models. `pro` uses more tokens, so pin `standard`. | Same | [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning) |
| Dated snapshot ID | None. The model page lists only the alias `gpt-6-luna`. | None: "Use the identifier gpt-6.1-sol". | [luna page](https://developers.openai.com/api/docs/models/gpt-6-luna), [sol page](https://developers.openai.com/api/docs/models/gpt-6.1-sol) |
| Azure version date | 2026-09-22 | 2026-09-29 | [Azure reasoning](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reasoning) |

- **The two vendors' docs disagree.** Azure lists all GPT-6 models, including luna, for `all_turns`; OpenAI's guide lists only GPT-5.6 models and GPT-6.1 Sol. They also disagree on GPT-5.4 and GPT-5.5, which only Azure lists. Azure's docs describe Azure OpenAI, not the OpenAI API.
  - The earlier search-snippet claim that all GPT-6 models default to `all_turns` appears to be a synthesized search answer with no OpenAI page behind it.
  - The pilot's check of the echoed `reasoning.context` decides. The harness should always set `reasoning.context` explicitly, because the guide gives no default for GPT-6.1 Sol.
- **Other Azure differences:** Azure says `max` effort works only on the Responses API. Azure's GPT-6 feature table marks gpt-6.1-sol as supporting `none`, which contradicts OpenAI's docs. For the OpenAI API, follow OpenAI's docs.
- **Reasoning tokens** are billed as output tokens and reported under `usage.output_tokens_details.reasoning_tokens` ([reasoning guide](https://developers.openai.com/api/docs/guides/reasoning)). The guide suggests reserving at least 25,000 tokens for reasoning plus output at first. A response that hits `max_output_tokens` returns status `incomplete`.
- **No dated snapshots:** the returned model string is the only pin, so `meta.json` must record it. TechCrunch dates the GPT-6 Sol and Luna launch to 2026-09-22 ([TechCrunch](https://techcrunch.com/2026/09/22/openai-launches-gpt-6-sol-and-luna/)). By Azure's version date, gpt-6.1-sol was one day old on 2026-09-30.

## 6. Prices and account rules (prices checked 2026-09-29/30; §6.1-6.2 checked 2026-09-30)
| Model / resource | Price | Source |
|---|---|---|
| Gemini 3.8 Flash | $0.75 in / $3.75 out per M "through December 31, 2026", then $1.50 / $7.50; cached $0.075 (then $0.15). The output price includes thinking tokens. Batch and Flex 50% off: $0.375 / $1.875 / cached $0.0375 through 2026-12-31. Explicit-cache storage $0.50 per M tokens per hour ($1.00 in 2027). Free tier: §6.2. | [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [thinking](https://ai.google.dev/gemini-api/docs/thinking) |
| gpt-6-luna | Per M tokens, up to 272K input: $0.10 in / $0.01 cached / $0.125 cache write / $0.50 out. Flex and Batch 50% off: $0.05 / $0.005 / $0.0625 / $0.25. Above 272K input: 2× the input and cache prices, 1.5× output. | [OpenAI pricing (Flex tab)](https://developers.openai.com/api/docs/pricing?latest-pricing=flex), [model page](https://developers.openai.com/api/docs/models/gpt-6-luna) |
| gpt-6.1-sol | $2.00 / $0.10 cached / $2.50 cache write / $10.00. Flex and Batch 50% off: $1.00 / $0.05 / $1.25 / $5.00 | [OpenAI pricing (Flex tab)](https://developers.openai.com/api/docs/pricing?latest-pricing=flex), [Flex](https://developers.openai.com/api/docs/guides/flex-processing) |
| DeepSeek V4.1 Flash (`deepseek-flash`) | Off-peak: $0.15 cache miss / $0.003 hit / $0.60 out; peak (01-04 and 06-10 UTC, weekdays) double | [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing) |
| DeepSeek V4.1 Flash on Fireworks | $0.30 / $0.006 / $1.20 | [Fireworks](https://docs.fireworks.ai/serverless/pricing) |
| RunPod GPUs | A100 PCIe 80GB $1.19 (community) / $1.59 (secure) per h; H100 PCIe $1.99 / $2.89 | [RunPod](https://www.runpod.io/pricing) |
| Modal | $30/month free compute on Starter | [Modal](https://modal.com/pricing) |
| Kaggle notebooks | Free GPUs; required for ARC Prize submissions | [Kaggle](https://www.kaggle.com/docs/notebooks) |

### 6.1 OpenAI caching, Flex and usage tiers
- **Cache writes cost extra.** GPT-5.6 and later models bill cache writes at 1.25× the uncached input rate. Cached reads cost 0.1× on most of these models and 0.05× on GPT-6.1 Sol ([prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)). This was not in the original `PLAN.md` §12 cost model.
  - It is "not an additive fee". Each input token is billed at exactly one of three rates: uncached, cached or cache write.
  - Caching is automatic. In the default implicit mode (`prompt_cache_options.mode='implicit'`), "OpenAI places a breakpoint at the end of the latest eligible message", so newly appended context is normally written at 1.25×. Explicit mode lets the caller place breakpoints. The docs describe no way to turn caching off.
  - Minimum 1,024 tokens. The only TTL is `prompt_cache_options.ttl='30m'`, which is also the default. `prompt_cache_key` is optional.
  - Usage reports `input_tokens_details.cached_tokens` and `input_tokens_details.cache_write_tokens`. The `results/costs.csv` columns in `CLAUDE.md` have no cache-write column yet.
  - Effect: small where the cache holds; where it keeps breaking (ARC-style trimming, PersistGym window cells), nearly all input could bill at 1.25×.
- **Flex** works on the Responses and Chat Completions endpoints. Tokens are "priced at Batch API rates, with additional discounts from prompt caching" ([Flex](https://developers.openai.com/api/docs/guides/flex-processing)).
  - Flex "is in beta with limited model availability"; the pricing page lists the supported models.
  - A 429 "resource unavailable" response is not charged. The default timeout is 10 minutes.
- **Usage tiers** ([rate limits](https://developers.openai.com/api/docs/guides/rate-limits)):
  - The Free tier requires an allowed geography and has a $100/month usage limit. That is a cap, not a credit.
  - gpt-6-luna's rate-limit table starts at Tier 1 (500 RPM / 500K TPM) and has no Free row, so luna appears to need a paid account ([luna page](https://developers.openai.com/api/docs/models/gpt-6-luna)).
  - Tier 3 ("$100 paid") has a $1,000/month usage limit. Hard spend limits make requests return 429.
- **Free tokens** _(low confidence; OpenAI's help and form pages returned 403)_: nothing found would reduce this budget materially.
  - Data sharing: a third-party tracker reports up to 1M free tokens a day for eligible organizations that share inputs and outputs, 250K on usage tiers 1 and 2 ([aitokenprice](https://aitokenprice.com/news/gpt-6-pricing)). It does not confirm gpt-6.1-sol. 1M tokens is about one PersistGym episode. Opting in sends all of that project's traffic to OpenAI for training.
  - Researcher Access Program: up to $1,000 in credits, reviewed quarterly, per a third-party listing ([grantedai](https://grantedai.com/grants/openai-researcher-access-program-api-credits-openai-group-c2fd0099)). The next review is in December, after the October gates.
  - "Sign in with ChatGPT" bills a user's ChatGPT plan ([siwc](https://developers.openai.com/siwc/token-sharing-open-source)). That is a consumer subscription, which `CLAUDE.md` bans for reported runs.

### 6.2 Gemini API tiers, Flex, thinking and free tier
- **Spend caps per tier:** Tier 1 $250, Tier 2 $2,000, Tier 3 $20,000-100,000 ([billing](https://ai.google.dev/gemini-api/docs/billing)).
  - At the cap, service pauses for all projects linked to that billing account until the next billing cycle starts, on the 1st of the month.
  - Tier 1 needs a linked billing account. Tier 2 needs "Paid $100 + 3 days from first successful payment". Tier 3 needs "Paid $1,000 + 30 days".
  - Prepay exists ($5 minimum), and projects can set their own spend caps. Not confirmed: whether a prepay purchase counts as "paid".
  - Consequence: the 1b ARC path ($319-527 at Flex, $638-1,054 at no-cache list; `PLAN.md` §16.1) cannot run within one month on Tier 1. Reach Tier 2 at least 3 days before the first ARC sweep.
- **Flex:** Gemini 3.8 Flash is supported. Set `service_tier` to `flex` in generateContent (`config={"service_tier": "flex"}`, streaming included) or in the Interactions API (`client.interactions.create(..., service_tier='flex')`) ([Flex](https://ai.google.dev/gemini-api/docs/flex-inference), [Flex for generateContent](https://ai.google.dev/gemini-api/docs/generate-content/flex-inference), [Flex for Interactions](https://ai.google.dev/gemini-api/docs/interactions/flex-inference)). The OpenAI-compatible endpoint "matches OpenAI's `service_tier` parameter" ([OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai)), which covers ARC's chat-completions Standard path.
  - Paid tiers only; the pricing page lists Flex as "Not available" on the free tier.
  - Latency: "Minutes (1–15 min target)", best-effort and sheddable. Requests "may sit in a queue", and Google recommends client timeouts of at least 10 minutes.
  - When capacity is short, the API returns 503 or 429. There is no automatic fallback to the standard tier; clients retry with exponential backoff. Flex counts toward the general rate limits.
  - Google's launch blog (2026-04-02) says responses report which tier served the request ([blog](https://blog.google/innovation-and-ai/technology/developers-tools/introducing-flex-and-priority-inference/)). The response field was not found in the docs, so the pilot should log it.
  - Not checked: whether Flex 503/429 errors are billed.
  - **Fit with ARC** _(unmeasured; Google's latency is a target, not a measurement)_: the harness calls the model once per step, one call at a time, under a 12 h wall clock. At 3-5 min per call, a game of 150-230 steps takes 7.5-19 h, so Flex can cause `TIME_BUDGET` endings. One slow call could also trigger the 15-minute scorecard close online (§1). Both would be artifacts of the billing tier, not of the harness. A local game server removes the scorecard risk but not the 12 h cap. The pilot measures Flex latency (`PLAN.md` §16.2).
- **Thinking:** Gemini 3.8 Flash supports `thinking_level` `low`, `medium` and `high`. The default is medium ("On (medium)" in [thinking](https://ai.google.dev/gemini-api/docs/thinking)), not high. `minimal` is not supported and returns an error, unlike 3.5 and 3.6 Flash ([model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)).
  - ARC configs and pilots must set `thinking_level: high` explicitly. Through the OpenAI-compatible endpoint, `reasoning_effort: high` maps to `thinking_level: high` ([OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai)).
  - Thinking tokens bill at the output rate and are reported as `total_thought_tokens`.
- **Caching** _(stacking: medium confidence)_: implicit caching is on by default, with a 4,096-token minimum for 3.8 Flash and "no cost saving guarantee". Hits show in `usage.total_cached_tokens`. The Interactions API supports only implicit caching; explicit caching needs generateContent ([caching](https://ai.google.dev/gemini-api/docs/caching)).
  - The pricing page lists cached input under Flex and Batch at $0.0375, half the standard cached price. That suggests the discounts stack on the Developer API. Check it on the pilot invoice.
- **Free tier:** for `gemini-3.8-flash`, input, output (including thinking) and context caching are "Free of charge". Batch and Flex are not available ([pricing](https://ai.google.dev/gemini-api/docs/pricing)).
  - The API is a Paid Service when called through a Cloud project with an active billing account ([terms](https://ai.google.dev/gemini-api/terms)). Rate limits are "applied per project, not per API key" ([rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)). So free-tier testing needs its own project with no billing account linked.
  - **Limits** _(low confidence)_: Google does not publish them; the rate-limits page defers to AI Studio, which needs a login. A developer-forum post dated 2026-09-03 reports 20 requests per day for 3.8 Flash ([forum](https://discuss.ai.google.dev/t/gemini-3-8-flash-free-tier-20-rpd-is-too-limited-for-practical-evaluation/180609)). A DEV post dated 2026-09-02 read 5 RPM and 20 RPD for 3.5-3.7 Flash out of 429 error bodies ([DEV](https://dev.to/romeroyang/geminis-free-tier-measured-20-requests-a-day-and-google-no-longer-publishes-the-number-4gf2)). Daily limits reset at midnight Pacific.
  - About 20 calls a day is enough for payload and smoke tests, far too few for an ARC game.
  - Not verified: whether `thinking_level: high` and the Interactions API work on the free tier. One free call would confirm it.
- **Free-tier data use:** the pricing table says "Used to improve our products: Yes" for the free tier and "No" for paid ([pricing](https://ai.google.dev/gemini-api/docs/pricing), [terms](https://ai.google.dev/gemini-api/terms), last modified 2026-04-28).
  - Unpaid Services: Google uses submitted content and responses to provide, improve and develop its products. Human reviewers may read and annotate inputs and outputs after disconnecting them from the account. The terms say not to submit sensitive, confidential or personal information.
  - Paid Services: prompts and responses are not used to improve products. They are logged for a limited period for abuse detection.
  - The terms' EEA, Switzerland and UK clause applies when making API clients available to users in those regions. It is not about where the developer is.
  - Only public data may go to the free tier. ARC public games and synthetic PersistGym data qualify.
- **Credits:** new Cloud Billing accounts may get a $300 Welcome credit for 90 days. Accounts opened after March 2, 2026 cannot use it for Gemini API and AI Studio usage ([billing](https://ai.google.dev/gemini-api/docs/billing), updated 2026-09-28; [Cloud free trial](https://docs.cloud.google.com/free/docs/free-cloud-features)). No AI Studio credit is offered.
  - _(Low confidence)_ A third-party blog dated 2026-09-11 says the credit still covers Gemini on Vertex AI, now the Gemini Enterprise Agent Platform ([blog](https://klymentiev.com/blog/gemini-free-credits)). But free-trial accounts cannot request quota increases, and the ARC fork's Google runtime would need the Vertex backend, which we have not checked.
  - The Gemini Academic Program gives API credits only to researchers affiliated with an academic institution ([Gemini for research](https://ai.google.dev/gemini-api/docs/gemini-for-research)).

## 7. Related work (as of 2026-09-30)
"Does not" is relative to this project. Coverage caveat: arXiv's API and search were rate-limited during the prior-art check, so a paper posted in the last few days could be missing.

| Work | What it does | What it does not do |
|---|---|---|
| [LOCA-bench (2602.07962)](https://arxiv.org/abs/2602.07962), Feb 2026 | Crosses a context-length dial (8K-256K) with context strategies: tool-result clearing, thinking-block clearing, compaction, memory tools. Scores fall from >70% to 14.7-21.3%. | State size and length move together; no distance-at-fixed-volume, no recoverability × derivedness, no harness-spread analysis. The natural "why not LOCA?" reviewer question. |
| [When Can Agents Forget Their Reasoning? (2609.29875)](https://arxiv.org/abs/2609.29875), Sep 24 | When historical reasoning can be dropped; reasoning is "more replaceable once task relevant derived state has been reliably externalized" (behavioral risk 67.3% vs 36.2%). | One acting model (DeepSeek V4 Flash), one benchmark; no distance dial, no volume control, no harness spread, no ARC. Closest on the replay mechanism; likely scooper of a dial study. |
| [StateComp (2609.27298)](https://arxiv.org/abs/2609.27298), Sep 23 | Same group; learns when history can be compressed (−52% tokens). | Not a controlled dial study. |
| [Harness-Bench (2605.27922)](https://arxiv.org/abs/2605.27922) | 106 tasks, 6 harnesses × 8 backends; cross-harness variance is largest where success depends on "intermediate-state tracking". | Post-hoc and correlational; no manipulated state variable, no mechanism isolation. We are the causal test of its observation. |
| [HarnessTax (Arena/Berkeley, Sep 16)](https://arena.ai/blog/coding-agents-harness-tax) | 7 models × 3 harnesses on SWE-bench Lite and Terminal-Bench 2.0; harness moves cost up to 5×, success ±2-5pp. | No state manipulation; no explanation of why. |
| [Stop Comparing LLM Agents Without Disclosing the Harness (2605.23950)](https://arxiv.org/abs/2605.23950) | "Binding Constraint Thesis": harness variance exceeds model variance for long-horizon tasks; 3×3 factorial on 100 SWE-bench Verified tasks; defines context drift δt = D_KL(p_t‖p_0). | No dial; no prediction about state or distance; no replay. Cite as motivation (by the thesis's correct name). |
| [GSM-Infinite (2502.05252)](https://arxiv.org/abs/2502.05252), [Verbose ListOps (2506.04907)](https://arxiv.org/abs/2506.04907) | Separate reasoning demand / state tracking from context length. | Not agents or harnesses. Cite as the design precedent. |
| [ConstraintRot (2606.22528)](https://arxiv.org/abs/2606.22528) | Constraints under compaction: violations 0% → 30%; strategies compared; summary budget sweep. | No distance sweep; no volume control. |
| [Plans Don't Persist (2606.22953)](https://arxiv.org/abs/2606.22953) | Evicting the plan costs 34.7pp on ALFWorld. | One state type. |
| [Cue-anchored working memory (2607.20972)](https://arxiv.org/abs/2607.20972), [PM-Bench (2607.12385)](https://arxiv.org/html/2607.12385v1), [Constraint-preserving relay (2607.18265)](https://arxiv.org/abs/2607.18265) | Facts or intentions surviving compaction; harness-injected memory; JSON vs narrative relay (0.96 vs 0.48). | No recoverability × derivedness design; no replay arm. |
| [MiniMax-M2 interleaved thinking](https://www.minimax.io/news/why-is-interleaved-thinking-important-for-m2), [MiniMax-M2 series (2605.26494)](https://arxiv.org/abs/2605.26494) | Keeping prior-turn thinking: Tau² 87 vs 64, BrowseComp 44.0 vs 31.4. | Grouped by task type, not by a manipulated state property. |
| [2606.00135](https://arxiv.org/abs/2606.00135) | Retaining thinking history: +2-5% for Qwen3-4B/8B on BFCL multi-turn. | No turn-depth or state breakdown. |
| [OpenAI reasoning-items cookbook](https://developers.openai.com/cookbook/examples/responses_api/reasoning_items) | About +3% on SWE-bench from passing reasoning items. | Single aggregate. |
| [OpenAI ARC post (Jul 29)](https://openai.com/index/how-two-settings-tripled-our-arc-agi-3-scores/) | Names retained reasoning + compaction; 13.3% → 38.3% (GPT-5.6 Sol, public set). | No per-component numbers, no notes instruction, no other provider. |
| [Empirical Study of Harness Design (2609.20804)](https://arxiv.org/abs/2609.20804) | 176 settings; context management matters as the budget tightens, mostly by preventing overflow; masking ≈ summarization at about half the cost. | Conditions on budget, not state type or recoverability. |
| [Beyond the Model (2609.32459)](https://arxiv.org/abs/2609.32459), [HM-Router (2609.32213)](https://arxiv.org/abs/2609.32213) | Component ablations of SWE-agent harnesses on 10 open models; routing across 73 models × 25 harnesses. | No state manipulation. |
| [Scaffold Effect (2607.22585)](https://arxiv.org/abs/2607.22585), [Harness or Model? (2609.11987)](https://arxiv.org/abs/2609.11987), [Scaffold effects on GAIA (2606.08529)](https://arxiv.org/abs/2606.08529), [Non-monotone harness sensitivity (2605.26731)](https://arxiv.org/abs/2605.26731) | Observational harness-sensitivity measurements (0-28pp). | None conditions on a manipulated state variable. |
| [2608.16370](https://arxiv.org/abs/2608.16370) | Compression left completion unchanged while retrieval calls rose from 21.0 to 63.9 (GPT-5.5, 5× compression). | Supports H1's "cost, not success" prediction for recoverable state; no explicit recoverability manipulation. |
| [Complexity Trap (2508.21433)](https://arxiv.org/abs/2508.21433), [Masking Stale Observations (2606.00408)](https://arxiv.org/abs/2606.00408), [CliffCompaction (2609.26779)](https://arxiv.org/abs/2609.26779), [ContextRender (2609.37743)](https://arxiv.org/abs/2609.37743), [TRACE (2608.06503)](https://arxiv.org/abs/2608.06503), [CWL (2606.11213)](https://arxiv.org/abs/2606.11213), [ACM (2607.23809)](https://arxiv.org/abs/2607.23809), [VISTA (2606.30005)](https://arxiv.org/abs/2606.30005), [Scroll (2608.21690)](https://arxiv.org/abs/2608.21690), [Anthropic context management](https://www.anthropic.com/news/context-management) | Compare or propose context-management mechanisms. | No distance-at-fixed-volume or recoverability dial. |
| [World-Model Collapse (2606.31399)](https://arxiv.org/abs/2606.31399), [HORIZON (2604.11978)](https://arxiv.org/abs/2604.11978), [StateMemBench (2608.19652)](https://arxiv.org/abs/2608.19652), [MINTEval (2605.18565)](https://arxiv.org/abs/2605.18565), [MemoryAgentBench (2507.05257)](https://arxiv.org/abs/2507.05257), [Sinha et al. (2509.09677)](https://arxiv.org/abs/2509.09677) | Vary state demand or horizon (dependency density, depth, update-to-query distance). | Harness fixed, or distance confounded with length, or not an agent-harness study. |
| [Ledger (2608.00808)](https://arxiv.org/abs/2608.00808) | Structured state for coding agents: SWE-bench Verified GPT-5 mini 56.2 → 64.2, cost −29-32%. | Coding only. A coding *success* win for StateCarry would not be new. |
| [PRO-LONG (2607.20064)](https://arxiv.org/abs/2607.20064), [Rodionov (2607.15439)](https://arxiv.org/abs/2607.15439), [Prime Agent (2608.23552)](https://arxiv.org/abs/2608.23552), [Tycho (2607.28287)](https://arxiv.org/abs/2607.28287), [Twin (2608.14490)](https://arxiv.org/abs/2608.14490), [Explore Before You Solve (2605.25931)](https://arxiv.org/abs/2605.25931), [Test-Time Communication (2609.21032)](https://arxiv.org/abs/2609.21032) | Own ARC-AGI-3 harnesses (PRO-LONG: queryable log, 76.1% pass@1 with 4.2-5.8× fewer tokens). | Ablate their own designs, not ARC's two official harnesses. |
| [labyrinthbench](https://github.com/owl-fleet/labyrinthbench), [compactbench](https://github.com/compactbench/compactbench), [compactionbench](https://github.com/t46/compactionbench), [ctxbench](https://github.com/geunwoobaek/ctxbench) | Hobby benchmarks with reach-back tasks × swappable context policies. | No replay arm, no volume control, no recoverability × derivedness analysis. PersistGym's artifact novelty is modest; its value is the design and analysis. |
| [JoaquinRuiz/agi-tests](https://github.com/JoaquinRuiz/agi-tests) | YouTube demo toggling "persistent" vs "amnesiac" harness on one ARC game (ls20) via OpenRouter. | No seeds, no statistics. Nearest thing to an ARC ablation found. |
| [andrew.ooo](https://andrew.ooo/answers/arc-agi-3-standard-harness-vs-provider-adapter-2026/), [metallab.ai](https://metallab.ai/en/2026/9/gpt-6-astra-arc-agi-3-harness) blogs | Speculate that reasoning-state preservation drives the gap. | No ablation. |

## 8. What remains open
1. **Per-component ARC numbers** with seeds, including the notes instruction, on a non-OpenAI model (Gemini 3.8 Flash). OpenAI named the mechanisms but published only the combined effect.
2. **A manipulated test** of whether harness effects on success depend on state being derived and non-recoverable, with volume and position controls. The literature is observational (Harness-Bench, HarnessTax) or crosses length rather than recoverability (LOCA-bench).
3. **When replay matters:** for which state types, and whether a visible, provider-neutral mechanism can replace opaque replay.
4. **A provider-neutral fix** for ARC's Standard harness, evaluated under ARC's own rules on held-out games.
5. **Clarifications from ARC:** what the "None" effort row means for Astra, which API surface the published Standard Gemini runs used, and how each published run ended (exit reasons are not published; §2 gives a partial inference rule).
