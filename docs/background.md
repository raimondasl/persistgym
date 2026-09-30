# Background: verified facts and related work

_Compiled 2026-09-30 from three independent premise checks (see `premise-check.md`) plus spot re-checks the same day. Every outside claim carries a URL. Where a claim comes from our own processing of public data, the method is stated._

## 1. ARC-AGI-3 basics
- **Game sets:** 25 public (demo) games, 55 Semi-Private and 55 fully private. Public games have 6-10 levels ([ARC-AGI-3 technical report](https://arxiv.org/html/2603.24621v1); the [harness README](https://github.com/arcprize/arc-agi-3-benchmarking/blob/main/README.md) says "there should be 25").
- **Action budget:** the harness allows 5× the human-baseline actions per level. Human-baseline actions per public game (summed over levels) range from 171 to 1,843, median 638. The baselines come from the session API, see §4.
- **Scoring:** RHAE per game, which weights later levels more heavily ([technical report](https://arxiv.org/html/2603.24621)).
- **Getting access:** playing games needs an ARC API key (`ARC_API_KEY`) from [arcprize.org](https://arcprize.org/), per the harness README.

## 2. The two ARC harnesses, in code
Source: [arcprize/arc-agi-3-benchmarking](https://github.com/arcprize/arc-agi-3-benchmarking) at commit `4ca00e6` (2026-09-21, MIT; still the HEAD of `main` on 2026-09-30). ARC's own description is in [docs/runtime-state.md](https://github.com/arcprize/arc-agi-3-benchmarking/blob/main/docs/runtime-state.md).

| Aspect | Standard (`manual_rolling`) | Provider Adapter (`continuous_conversation`) |
|---|---|---|
| State | Client-owned plain-text transcript | Replays provider-native items: OpenAI Responses reasoning items with `encrypted_content` (`store:false`); Gemini Interactions thought steps with signatures; Anthropic thinking and signature blocks; xAI encrypted reasoning |
| Reasoning | Only each assistant turn's visible `output_text` is sent back, so reasoning is dropped ([agent.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/main/benchmarking/agent.py)). Exception: `analysis_mode: true` inlines readable reasoning summaries as `<reasoning_summary>` text and also changes the system prompt ([analysis_mode.md](https://github.com/arcprize/arc-agi-3-benchmarking/blob/main/docs/analysis_mode.md)) | Native replay |
| Overflow | Drops the oldest user/assistant pair when the estimated size (chars / 1.0) exceeds `MAX_CONTEXT_LENGTH`, which is 175k in all checked-in Standard configs | Compacts when the previous response's provider-reported `total_tokens` reaches 175k ([compaction.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/main/benchmarking/compaction.py)). Native compaction for OpenAI, Anthropic and xAI. For Gemini it is a harness summary: a domain-neutral prompt capped at 8,192 output tokens, inserted as one user-role "bridge" message in a fresh state. This ends opaque reasoning continuity for the summarized prefix ([PR #35](https://github.com/arcprize/arc-agi-3-benchmarking/pull/35)) |
| Notes instruction | System prompt includes "Include any context you want to carry forward in your reply, along with the action you want to take." | Removed automatically. runtime-state.md says this "is not a configurable model setting" |
| API surface | Checked-in Standard configs use chat completions (OpenAI; Gemini 3.1 Pro via the OpenAI-compatible endpoint) | Responses (OpenAI, xAI), Interactions (Gemini), Messages (Anthropic) |
| Same in both | Action budget 5× human baseline per level; `MAX_RETRIES=3`; 12h wall clock; up to 7 animation frames per observation; no tool calling (free-text "last action mentioned" or strict JSON `{actions:[...]}`); same scoring. Only the Anthropic Adapter profile enables prompt caching. Published costs are reconstructed from configured prices without cache discounts. | |

**What can be toggled without code changes, and what cannot:**
- **Configurable:** `MAX_CONTEXT_LENGTH`; compaction `trigger_tokens` and summary caps; native vs `harness_summary` compaction (`harness_summary` only for OpenAI and Google); `analysis_mode`; budget multiplier; retries; animation frames.
- **Also available:** `manual_rolling` runs on the google-genai Interactions API and on OpenAI Responses ([runtime_adapters.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/main/benchmarking/runtime_adapters.py)), so the API surface can be held fixed across harnesses.
- **Not toggleable on its own:**
  - **Replay** is tied to the state strategy. The OpenAI validator requires `reasoning.context='auto'` ([openai_runtime.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/main/benchmarking/openai_runtime.py)). The Google validator requires `thinking_summaries='auto'` ([google_runtime.py](https://github.com/arcprize/arc-agi-3-benchmarking/blob/main/benchmarking/google_runtime.py)).
  - **The notes instruction** is hard-coded to `provides_continuous_conversation` (`agent.py::_build_system_prompt`).
  - **Compaction** exists only in `continuous_conversation`, and rolling truncation only in `manual_rolling`.
- **Small patches needed:**
  - a notes flag (about one line);
  - wiring `SummaryCompactor` into `manual_rolling`;
  - (not planned) dropping thought or reasoning items before replay.
- **Published configs are not in the repo:**
  - No `gpt-6-astra` config is checked in, and no Gemini 3.8 Flash Standard config at any effort.
  - The only Gemini Adapter config is `google-gemini-3-8-flash-low-provider-adapter`: `thinking_level: low`, `MAX_CONTEXT_LENGTH` 1,048,576, `harness_summary` at 175k ([model_configs.yaml](https://github.com/arcprize/arc-agi-3-benchmarking/blob/main/benchmarking/model_configs.yaml)).
  - Session metadata names the published configs `google-gemini-3-8-flash-high` and `google-gemini-3-8-flash-high-provider-adapter` ([example session](https://arcprize.org/api/sessions/484de130-939a-4773-b771-d0108ed46a56)).
  - Which API surface the published Standard Gemini runs used is unknown.
- **Exit reasons** in the harness: `GAME_WIN`, `ACTION_BUDGET`, `TIME_BUDGET`, `SCORECARD_CLOSED`, `API_ERROR`, `AGENT_ERROR`, `UNKNOWN` (`benchmarking/base.py`).
- **Recent activity:** open PRs include [#44](https://github.com/arcprize/arc-agi-3-benchmarking/pull/44), a DeepSeek Provider Adapter with tool-based reasoning replay (Sep 25). Adapters were added on Sep 15 (Gemini), Sep 19 (xAI) and Sep 21 (Anthropic).

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
- **Tokens per game:**
  - Standard-high: about 70M input and 8M output.
  - Adapter-high: about 95M input and 4.3M output.
  - Standard-low: about 56M input and 0.4M output.
  - Adapter-low: about 98M input and 1.0M output.
  - Input dominates because every call re-sends a window of about 130-150k tokens.
- **Caching:** measured cached shares are about 17% (Standard) and 53% (Adapter). At the $0.075 cached price, that would put real per-game cost at about $74 (Standard) and $53 (Adapter) at high. Flex would roughly halve these.

## 5. How each API handles earlier-turn reasoning
| API / model | Behaviour | Source |
|---|---|---|
| OpenAI Responses | `reasoning.context` ∈ {`auto`, `current_turn`, `all_turns`}; omitting it = `auto`. "The GPT-5.6 model family supports `all_turns` and uses it by default." "GPT-6.1 Sol also supports `all_turns`." "Earlier models default to `current_turn`." The response's `reasoning.context` field reports the effective mode. With `store:false`, reasoning items carry `encrypted_content` you can pass back. **gpt-6-luna is not mentioned**; a search snippet seen by one check claims all GPT-6 models default to `all_turns`. Unverified; the pilot must check. | [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning), [reasoning items cookbook](https://developers.openai.com/cookbook/examples/responses_api/reasoning_items) |
| Gemini 3.x | Docs say to always resend thought blocks exactly as received, with no documented bypass. Thought signatures are validated strictly for function calls in the current turn (400 error). A `skip_thought_signature_validator` sentinel exists. Signatures are opaque, so what the model sees can't be inspected. | [thinking](https://ai.google.dev/gemini-api/docs/thinking), [thought signatures](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/thought-signatures) |
| DeepSeek thinking mode | Without `tools`, earlier `reasoning_content` is "ignored and will not be concatenated into the context". With `tools` it must be passed back, otherwise the API returns 400. There is no clean on/off within one mode. | [thinking mode](https://api-docs.deepseek.com/guides/thinking_mode) |
| Qwen3.6-27B | `preserve_thinking` via `chat_template_kwargs` (vLLM/SGLang), **off by default**. The card says the model "has been additionally trained to preserve and leverage thinking traces from historical messages." | [model card](https://huggingface.co/Qwen/Qwen3.6-27B) |
| Qwen3.8-27B | `preserve_thinking` is **on by default**. | [model card](https://huggingface.co/Qwen/Qwen3.8-27B) |
| gpt-oss (harmony) | Guidance: drop earlier-turn CoT once a turn ends in a final message; keep it only around tool calls. | [harmony guide](https://developers.openai.com/cookbook/articles/openai-harmony) |
| OpenRouter | Accepts `reasoning` / `reasoning_details` on assistant messages; does not document which providers render them into the template. | [reasoning tokens](https://openrouter.ai/docs/use-cases/reasoning-tokens) |

## 6. Prices (checked 2026-09-29/30)
| Model / resource | Price | Source |
|---|---|---|
| Gemini 3.8 Flash | $0.75 in / $3.75 out per M "through December 31, 2026", then $1.50 / $7.50; cached $0.075; Batch and Flex 50% off; a free tier exists (content may be used to improve products — public data only) | [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| gpt-6-luna | $0.10 in / $0.01 cached / $0.50 out (up to 272k tokens); Flex and Batch 50% off | [OpenAI pricing](https://developers.openai.com/api/docs/pricing), [model page](https://developers.openai.com/api/docs/models/gpt-6-luna) |
| gpt-6.1-sol | $2 / $0.10 / $10; Flex 50% off | [OpenAI pricing](https://developers.openai.com/api/docs/pricing), [Flex](https://developers.openai.com/api/docs/guides/flex-processing) |
| DeepSeek V4.1 Flash (`deepseek-flash`) | Off-peak: $0.15 cache miss / $0.003 hit / $0.60 out; peak (01-04 and 06-10 UTC, weekdays) double | [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing) |
| DeepSeek V4.1 Flash on Fireworks | $0.30 / $0.006 / $1.20 | [Fireworks](https://docs.fireworks.ai/serverless/pricing) |
| RunPod GPUs | A100 PCIe 80GB $1.19 (community) / $1.59 (secure) per h; H100 PCIe $1.99 / $2.89 | [RunPod](https://www.runpod.io/pricing) |
| Modal | $30/month free compute on Starter | [Modal](https://modal.com/pricing) |
| Kaggle notebooks | Free GPUs; required for ARC Prize submissions | [Kaggle](https://www.kaggle.com/docs/notebooks) |

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
5. **Clarifications from ARC:** what the "None" effort row means for Astra, and which API surface the published Standard Gemini runs used.
