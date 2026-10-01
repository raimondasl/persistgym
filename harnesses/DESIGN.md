# PersistGym harness cells: design

_Track: M0 harness cells (PLAN.md §6, §7; amendment A1 §16.3, §16.5). Built on the generator in `persistgym/` (episode schema 1). Everything here is $0: no API call has been made. The paid transport exists but has never run._

A harness cell decides what the model sees at every turn of a PersistGym episode. This package turns each new observation into the exact JSON body of an OpenAI Responses API request (`POST /v1/responses`) and asserts, with payload snapshot tests, exactly which turns, reasoning items and instructions every cell sends. PLAN §6 calls these tests the single most important correctness check, and no paid run may happen until they pass.

## 1. Quick start
```
uv run pytest -q harnesses && uv run ruff check harnesses       # snapshot tests and lint
uv run python -m harnesses cells                                 # the cell table
uv run python -m harnesses dry-run --cell W-n-0 --task-cell observed-nonrec-far   # $0, fake model
uv run python -m harnesses summary-timing --n 20                 # $0, Σ compaction timing (§4.3)
```
`dry-run` prints, for every request, its kind, the pending step, `reasoning.context` and the provenance of every input item (`U<t>` observation of turn t, `R<t>` its reasoning item, `A<t>` its reply, `B<k>` summary bridge k, `Q` the summary request).

Paid commands are in §8. They refuse to run without explicit approval.

## 2. Cells
| Cell | History / loss policy | Notes instruction | `reasoning.context` | Role (PLAN §6) |
|---|---|---|---|---|
| F-r | full history | off | `all_turns` | ceiling |
| F-0 | full history | off | `current_turn` | H1/H3 comparator |
| W-n-r | token window W, drop oldest | on | `all_turns` | |
| W-n-0 | token window W, drop oldest | on | `current_turn` | ≈ ARC Standard |
| Σ-n-r | summary at W | on | `all_turns` | |
| Σ-n-0 | summary at W | on | `current_turn` | |
| W-0 | token window W | off | `current_turn` | isolates notes |
| Σ-0-r (optional) | summary at W | off | `all_turns` | ≈ ARC Adapter |

ASCII ids for file names and the CLI: `sigma-n-r` etc. (`S-n-r` is also accepted). `REPLAY_OFF_CELLS` (F-0, W-n-0, Σ-n-0, W-0) is the set to run on a model whose echo check fails (PLAN §7). The pairs that differ only in replay are F-r/F-0, W-n-r/W-n-0 and Σ-n-r/Σ-n-0.

## 3. The request body
Every request of every cell has exactly these fields:

| Field | Value |
|---|---|
| `model` | `HarnessConfig.model` (default `gpt-6-luna`) |
| `instructions` | the episode's system prompt; in notes cells plus `"\n"` and the notes sentence (§5) |
| `input` | the history items (§4) and the current observation as a user message |
| `reasoning` | `{"effort", "mode", "context"}`, always all three, set explicitly |
| `store` | `false` (stateless: nothing is kept server-side) |
| `include` | `["reasoning.encrypted_content"]` |
| `service_tier` | `HarnessConfig.service_tier` (default `flex`) |
| `truncation` | `"disabled"`, so the API never drops items on its own |

Added only when configured: `max_output_tokens`, `prompt_cache_key`, `reasoning.summary`. Summary requests also carry `max_output_tokens` (§4.3). No tools and no server-side `context_management` are sent.

- **Input items.** An observation, the bridge and the summary request are user messages: `{"type": "message", "role": "user", "content": [{"type": "input_text", "text": ...}]}`. An earlier turn is its observation followed by that response's output items, sent back as returned (reasoning items with `encrypted_content`, then the assistant message), with null fields dropped. This follows OpenAI's stateless pattern `context += response.output` ([reasoning items cookbook](https://developers.openai.com/cookbook/examples/responses_api/reasoning_items)). Output items of any other type are left out and logged; none are expected because no tools are offered.
- **Reasoning settings.** `effort` defaults to `medium`, the documented default for GPT-6.1 Sol, GPT-6 Sol and GPT-6 Luna. `mode` defaults to `standard`, the documented default ([reasoning guide](https://developers.openai.com/api/docs/guides/reasoning)). Both are configurable.
- **The reply** the environment scores is the concatenated `output_text` of the assistant message items (the SDK's `response.output_text`).

## 4. History policies
Besides the hand-derived snapshots, `tests/test_payload_reference.py` checks every cell over 100 random episodes (per-turn observation and reply lengths, W, counted instructions and `summary_keep_recent_tokens` all varied) against a brute-force reference that recomputes the kept turns and the compaction points from token counts alone. Every harness test runs with outbound network connections and DNS blocked (`tests/conftest.py::no_network`), so a test that would reach an API fails.

All token accounting uses the generator's tokenizer (tiktoken `o200k_base`) on **visible text only**: observation text, the reply's output text and the bridge text. There is no per-message overhead. Encrypted reasoning items are opaque and are not counted. Because of this, the window boundary and the summary trigger fall on the same steps in the r and 0 arms of a pair whenever the replies are the same. The cost is that an r arm's real context is larger than W by the rendered reasoning (§10).

The episode's system prompt counts toward W if `window_counts_system_prompt` is set; the default is the episode's generator setting, true since generator 0.2.0 (PREREG D5: sys counts toward W, as in the PREREG formulas). **The notes sentence is never counted.** What counts is the episode's own system prompt (`Episode.system_tokens`, 95-150 tokens at the defaults), the same in a notes cell and its no-notes partner. Counting the full instructions would make the two cells of a notes pair (W-n-0/W-0, Σ-n-r/Σ-0-r) evict and compact at different steps whenever a turn boundary falls within the sentence's 21 tokens of W, so the notes contrast would also carry a loss-policy difference. The visible request still sends the sentence; W is just the generator's design budget.

W defaults to the episode's generator `W_tokens`, so the harness evicts exactly where the generator designed near and far.

### 4.1 Full (F)
Every earlier turn, verbatim, in order.

### 4.2 Window (W)
Before sending observation m, keep the longest suffix of whole earlier turns (observation and output items) such that kept turns + observation m (+ instructions, if counted) ≤ W tokens. This is `persistgym.survival.window_keep_start`, the same function the generator used to design near and far. Dropped turns never come back. The boundary is inclusive: a context of exactly W is kept whole. A test checks that at every step the W cells' visible messages equal `persistgym.survival.reference_window_payload` for the same replies.

### 4.3 Summary at W (Σ)
Before sending observation m, compute the visible context that the step request would hold: bridge + turns since the last compaction + observation m (+ instructions, if counted). If it exceeds W (strictly) and at least one turn can be compacted, the harness first sends a **summary request**:
- `instructions`: ARC's summary system prompt, verbatim;
- `input`: the current bridge (if any), the turns to compact with their reasoning items, then ARC's `SUMMARY_REQUEST_PROMPT` as a user message;
- the same `reasoning` settings as the cell, including its `reasoning.context`;
- `max_output_tokens` 8,192, as ARC.

The summary text then replaces the compacted turns with **one user-role bridge message** in ARC's bridge template. The summary call's own reasoning and message items are discarded. The step request follows: bridge, any turns kept, observation m.

ARC's prompts are used verbatim, from `benchmarking/compaction.py` at `4ca00e6` ([source](https://github.com/arcprize/arc-agi-3-benchmarking/blob/4ca00e6/benchmarking/compaction.py)). They are already domain-neutral. On 2026-10-01 they were checked character for character against the pinned file.
- System: "You create concise conversation summaries for reliable continuation. Return only the requested summary."
- Request: "Summarize the conversation so you can continue making progress on the task in a future context. The conversation history will be replaced by this summary and will no longer be available.\nUse your judgment about what matters for this task."
- Bridge: "Earlier conversation history was compacted. Use the following summary as prior context. If it conflicts with newer input, prefer the newer input.\n\n{summary}"

**What gets compacted** (`summary_keep_recent_tokens`):
- 0 (the default, as ARC) compacts every turn since the last compaction, and the step request is bridge + observation m.
- A value > 0 keeps the newest whole turns that fit in that many tokens together with the observation, and compacts the rest (at least one turn).

The snapshot tests cover both settings.

**Empty or incomplete summaries.** If a summary comes back empty or with a status other than `completed`, the same summary request is retried, up to `summary_max_attempts` = 4 (ARC: `MAX_RETRIES` + 1). After that the episode ends with `AGENT_ERROR`.

**Differences from ARC's Gemini Adapter compaction**, all deliberate:
- ARC triggers after a response whose *provider-reported* `total_tokens` reach 175k. That total includes reasoning tokens, so in our design it would differ between r and 0 arms. Here the trigger is the pre-send visible count.
- The threshold is W, not 175k.

**Near cells.** The generator's DESIGN.md §8 warns that a summary cell which compacts the whole history can compact a near reveal. With the default `summary_keep_recent_tokens` = 0, near-cell S in Σ cells is therefore **measured, not designed**. The runner records payload S at every need step.

`uv run python -m harnesses summary-timing --n 20` ($0, fake model) measures this. It runs the non-recoverable near cells of main templates 0-19 (40 episodes) at the default generator config (0.2.0, with the system prompt counted toward W, PREREG D5), with every reply at the assumed 1,000 tokens and a 300-token summary:

| `summary_keep_recent_tokens` | Compactions at turn | Near episodes with S = 0 at need | Summary calls per episode (input tokens each) | Input tokens per episode: summary / step requests |
|---|---|---|---|---|
| 0 (ARC-like) | 9 and 18 in all 40 | 19 of 40 | 2.0 (22,554-22,885) | 45,439 / 267,887 |
| 16,650 (the near span: system prompt of at most 150 tokens + 6 turns + 1 observation) | every 3 turns from 9 (4-6 per episode) | 0 of 40 | 5.35 (7,557-7,887) | 41,862 / 396,489 |

Token counts are the fake model's: visible text only (tiktoken, no per-message overhead, no rendered reasoning), so they size the comparison, not the bill. An independent re-derivation from token counts alone (not through the harness) also gives 19 of 40. With the system prompt counted, 9 turns of 2,500 tokens plus the next observation (24,000) no longer fit, so compaction comes one turn earlier than at generator 0.1.1 (10 and 19, 25 of 40); a keep budget of 16,500 no longer holds the near span (4 of 40 near episodes then lose a reveal), hence 16,650.

So under the ARC-like default, about half of the near Σ episodes reach the need step with the reveal summarized rather than verbatim, and the near/far contrast in Σ cells becomes "carried by the summary or not". Keeping the near span verbatim restores designed near S. The price:
- about 2.7 times as many summary calls. Each holds about 8k input tokens instead of about W, so summary-call input per episode is similar (about 42k vs 45k); the extra summary calls cost mainly their output and reasoning tokens;
- step requests that stay between about 17k and 24k tokens instead of dropping to a few thousand after each compaction: about 1.48 times the step-request input per episode (396k vs 268k), and a cached prefix that breaks at each of the 2.7 times as many compactions;
- a departure from ARC.

Both settings are tested.

## 5. Notes instruction
ARC Standard's sentence, verbatim: "Include any context you want to carry forward in your reply, along with the action you want to take." In ARC it sits inside the system prompt (`benchmarking/agent.py::_build_system_prompt` at `4ca00e6`; checked on 2026-10-01). Here notes cells append it to the episode's system prompt as its last line, joined with `"\n"`. The episode's prompt is one instruction per line. It never appears in the input items or in summary requests. Tests check that notes cells and their no-notes partners (W-n-0/W-0, Σ-n-r/Σ-0-r) differ only in the step requests' `instructions`.

## 6. Reasoning replay
Every turn sent verbatim carries its reasoning items with `encrypted_content`, in **every** cell. Only `reasoning.context` differs between the arms:
- `all_turns` in r arms, which "renders available, compatible reasoning items from earlier turns into the next sample";
- `current_turn` in 0 arms, which "does not render reasoning from earlier turns into the next sample" ([reasoning guide](https://developers.openai.com/api/docs/guides/reasoning)).

Every environment step is a new user message, so under `current_turn` no earlier reasoning is rendered.

The tests assert that, for each pair, every request is identical after removing `reasoning.context`, summary requests included. They also assert that the 0 arm sends one reasoning item per verbatim earlier turn.

**The echo check.** The response's `reasoning.context` "contains the effective mode... Check this field on each response" (same guide). The runner compares it on every response:
- On a mismatch, the episode is excluded and, by default, stopped.
- After 2 excluded episodes, the run is aborted (CLAUDE.md: log mismatches and exclude those episodes).

The docs list `all_turns` support for the GPT-5.6 family and GPT-6.1 Sol, not for GPT-6 Luna, so the luna r arms depend on the echo check (PLAN §7, §16.6).

**Relation to ARC.**
- ARC Standard sends no reasoning items at all. W-n-0 sends them but asks for `current_turn`, so the model should see the same thing.
- ARC's OpenAI Adapter requires `reasoning.context = "auto"` (`openai_runtime.py` at `4ca00e6`). Σ-0-r asks for `all_turns` explicitly instead.

## 7. Runner (`runner.py`)
`run_episode(episode, cell, cfg, transport)` drives a `persistgym.EpisodeEnv`. It never replays `steps` directly, so a lookup inserts a turn like any other observation.

Per request it logs to the raw transcript:
- the payload and the full response;
- the session's provenance trace and loss-policy bookkeeping;
- the requested vs echoed `reasoning.context`, effort and mode;
- the returned model string and service tier.

At the need step's **first** presentation (not a lookup result) it records:
- `survival_from_payload` on the payload actually sent, with `system` = instructions and the bridge excluded (lookup responses from earlier steps are always left out, PREREG §2.8);
- `carried_in_text` on the bridge (summary cells);
- the window or compaction bookkeeping.

`assistant_carried` in the payload result covers notes kept in earlier replies.

**Exit reasons:**

| Exit reason | When |
|---|---|
| `DONE` | the episode finished |
| `REASONING_CONTEXT_MISMATCH` | an echoed `reasoning.context` differed from the request (the episode is excluded) |
| `AGENT_ERROR` | one compaction's summary failed `summary_max_attempts` times (each compaction gets its own attempts) |
| `API_ERROR` | an OpenAI error after retries |
| `COST_CAP` | the run's spend reached the planned amount |
| `MAX_TURNS` | the episode passed `max_turns` |

`run_batch` writes:
- `results/<experiment>/<run_id>/meta.json`, with the fields required by CLAUDE.md, via `common.runmeta.write_meta`;
- `episodes.jsonl`, one line per episode;
- `results/raw/<experiment>/<run_id>/transcript.jsonl.gz` (gitignored).

For a paid transport, `run_batch` also calls `finalize` in a `finally` block, which appends exactly one `results/costs.csv` row.

## 8. Paid calls (`openai_transport.py`)
`OpenAIResponsesTransport` is the only code here that can spend money. Its constructor refuses (`PaidCallsNotAllowed`) **before building any client** unless all of these hold:
1. `PERSISTGYM_ALLOW_PAID=1` is set;
2. `--approved-block <name>` is given. This is the researcher's approved spending block from PLAN §16.2; the approval itself is recorded in `results/decisions.md`;
3. `PREREG.md` is **committed** (§16.3: PREREG committed before any paid call): tracked by git, present in `HEAD`, and with no uncommitted changes. A draft in the working tree does not count;
4. `--planned-usd` is a positive, finite number (`nan` would otherwise pass every budget comparison);
5. the experiment has a budget phase in `common/costs.py`, and `common.costs.headroom(planned_usd, phase, rows)` ≥ 0.

`--planned-usd` is the planned spend of the whole command: for `probe-echo` and `probe-replay` with several models, each model's transport gets only what the earlier models left. `run` refuses a `persistgym_pilot` run on any split other than `pilot` (§16.5: pilot templates use a disjoint seed range).

While running, it:
- stops before a call once the run's estimated billed cost reaches `--planned-usd` (`COST_CAP`);
- retries 429s, timeouts and 5xx errors with exponential backoff, but never `insufficient_quota`. Flex 429s are not charged ([Flex guide](https://developers.openai.com/api/docs/guides/flex-processing)). A timed-out or dropped connection may still have been processed and billed; such attempts are not in the ledger;
- logs the echoed `reasoning.context`, the returned model string and the served service tier of every response;
- appends one costs.csv row per run, with `approved_block`, the number of context mismatches and the git dirty flag in `notes`. `service_tier` is the requested tier. The served tier, cache-write tokens and median seconds per call go into the `service_tier_served`, `cache_write_tokens` and `latency_s` columns when `common/costs.py` has them (schema of 2026-10-01 on `main`), and into `notes` otherwise. A response whose returned model string has no price is priced as the requested model and flagged in `notes` rather than dropped from the log.

It never switches service tier. The API can still serve a request on a different tier than requested; the response says so and the row records it.

**Arming paid calls for one command only.** In Git Bash, `PERSISTGYM_ALLOW_PAID=1 uv run ...` sets the variable for that command only. In PowerShell, `$env:PERSISTGYM_ALLOW_PAID = "1"` stays set for the rest of the session, so remove it right after (`Remove-Item Env:PERSISTGYM_ALLOW_PAID`). Never put it in `.env`: `uv run --env-file .env` would then arm every command.

Prices are in `pricing.py`, with sources: luna $0.10/$0.01/$0.50, sol $2/$0.10/$10 per M tokens, cache writes 1.25× input, Flex 50% off; checked 2026-09-30. The code never reads or names an API key. The OpenAI SDK reads it from the environment, so load it with `uv run --env-file .env`.

```
PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses probe-echo \
    --approved-block "<block>" --planned-usd 0.5            # sol and luna, both contexts
PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses probe-replay \
    --model gpt-6.1-sol --n 10 --approved-block "<block>" --planned-usd 2
PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses run --cell F-0 \
    --model gpt-6-luna --split pilot --n 1 --approved-block "<block>" --planned-usd 1
```
`run` defaults to the pilot split, which has a disjoint seed range, and the `persistgym_pilot` experiment. It refuses more than 10 episodes for a pilot.

`tests/test_cli_end_to_end.py` runs all three commands through the real guarded transport with a stub client answered by the fake model. It checks that each run writes its results, `meta.json` and exactly one costs.csv row, so a bookkeeping crash cannot happen for the first time after paid calls.

## 9. Probes (`probes.py`)
Both probes are excluded from every analysis (§16.3). Their snapshot tests show that the two arms send identical payloads except `reasoning.context`, at every turn.

### 9.1 Echo check
For gpt-6.1-sol and gpt-6-luna, each in both contexts, the probe runs a two-turn stateless conversation ("Reply with only the word: ready", then "...: done"). It passes when every response echoes the requested `reasoning.context`. The second turn carries the first turn's reasoning item, so the echo is observed with earlier reasoning present.

### 9.2 Private-choice replay-use probe
The probe has three turns:
1. "Privately pick a random three-digit number. Do not write the number or any hint about it. Reply with only the word: ready";
2. a filler question;
3. "What is the three-digit number you privately picked at the start of this conversation? Reply with only the number."

The prompts contain no digits. Under `all_turns`, the turn-3 sample can see the turn-1 reasoning; under `current_turn`, it cannot.

**Scoring.** The picked number exists only inside the encrypted reasoning, so both arms request `reasoning.summary: "auto"`, identically. A trial is scored as follows:
- *scorable*: the turn-1 summary names exactly one three-digit number, no visible reply leaks one, and every echo matches;
- *match*: the turn-3 answer equals that number.

The summary text is stripped from the reasoning items sent back (`summary: []`), so the only channel for the number is the encrypted reasoning.

**Chance.** Chance is 1/900 (100-999; §16.3 says 1/1000) only for uniform guesses. Models pick "random" numbers unevenly, so a no-replay arm can match by sharing number preferences. Report `chance_agreement(picks, answers)` next to the two match rates, and also the share of turn-3 answers that are not a number at all (e.g. "I cannot recall").

## 10. Researcher decisions
Each item is a `HarnessConfig` field or a fixed behaviour, listed in `config.RESEARCHER_DECISIONS`. Each needs the researcher's confirmation in PREREG.md.
- [RESEARCHER DECISION] `reasoning_effort` = `medium` (§16.5 proposes the documented default), sent explicitly.
- [RESEARCHER DECISION] `reasoning_mode` = `standard`, sent explicitly.
- [RESEARCHER DECISION] `reasoning_summary` = off in harness cells. Summaries would help failure labelling but add a field to every request; whether summary text in replayed items is rendered is undocumented.
- [RESEARCHER DECISION] `service_tier` = `flex` for every cell, never switched per episode.
- [RESEARCHER DECISION] `max_output_tokens` = none. A cap bounds runaway cost but truncates long reasoning and yields `incomplete` replies.
- [RESEARCHER DECISION] `W_tokens` = the episode's generator W, so eviction matches the near/far design.
- [RESEARCHER DECISION] `window_counts_system_prompt` = the episode's generator setting (true since generator 0.2.0, PREREG D5). The episode's system prompt counts toward W; the notes sentence does not, so notes pairs evict at the same steps (§4).
- [RESEARCHER DECISION] `token_accounting`: visible text only (observations, replies, bridge), tiktoken `o200k_base`, no per-message overhead; reasoning items not counted.
- [RESEARCHER DECISION] `summary_trigger`: pre-send visible context > W, rather than ARC's post-hoc provider `total_tokens` ≥ 175k.
- [RESEARCHER DECISION] `summary_keep_recent_tokens` = 0: compact everything, as ARC. Near-cell S in Σ cells is then measured, not designed (§4.3).
- [RESEARCHER DECISION] `summary_system_prompt` = ARC's summary system prompt, which replaces the task instructions in the summary call, as ARC does. The summarizer then does not see "Some requests depend on records shown in earlier updates." Set it to `None` to keep the task instructions.
- [RESEARCHER DECISION] `summary_request_reasoning`: the summary call uses the arm's `reasoning.context` and includes the compacted turns' reasoning items, as ARC's Adapter state does. In r arms the summarizer may therefore draw on earlier reasoning.
- [RESEARCHER DECISION] `summary_max_output_tokens` = 8,192, as ARC. On OpenAI this cap includes reasoning tokens.
- [RESEARCHER DECISION] `notes_placement`: the last line of the instructions.
- [RESEARCHER DECISION] `stop_on_context_mismatch` = true: stop and exclude the episode; abort the run after 2 such episodes.
- [RESEARCHER DECISION] `output_items_replay`: output items are sent back verbatim with null fields dropped. The pilot confirms that the API accepts this with `store: false`.

## 11. Known limitations and what this does not show
- **No payload has been sent to the API.** The tests show that the payloads are what the design says. They do not show that the API accepts them, for example:
  - replayed message items with ids under `store: false`;
  - stripped summaries in the replay probe;
  - `reasoning.mode` on luna.

  The first paid pilot checks this. A 400 error is not billed.
- **The echo check shows the reported mode, not use.** That the API reports `all_turns` does not show that the model uses earlier reasoning. The replay-use probe tests that, and its scoring depends on reasoning summaries naming the picked number. If they rarely do, most trials are unscorable and the probe needs a redesign.
- **The r arms see more than W.** Under `all_turns`, rendered reasoning adds tokens that W does not count. The r and 0 arms then share eviction points, but the r arms' real contexts are larger.
- **Tokens are tiktoken's.** Provider counts differ by per-message overhead and rendered reasoning. Both are logged.
- **The fake model's usage numbers are not realistic.** Fake runs check structure, not cost.
- **Σ cells depend on what the model writes.** Their S is measured, and `carried_in_text` is the intended accounting (generator DESIGN.md §8, §12).
