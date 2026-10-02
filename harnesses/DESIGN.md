# PersistGym harness cells: design

_Track: M0 harness cells (PLAN.md §6, §7; amendment A1 §16.3, §16.5). Built on the generator in `persistgym/` (generator 0.3.0, episode schema 3). Everything here is $0: no API call has been made. The paid transport exists but has never run._

A harness cell decides what the model sees at every turn of a PersistGym episode. This package turns each new observation into the exact JSON body of an OpenAI Responses API request (`POST /v1/responses`) and asserts, with payload snapshot tests, exactly which turns, reasoning items and instructions every cell sends. PLAN §6 calls these tests the single most important correctness check, and no paid run may happen until they pass.

## 1. Quick start
```
uv run pytest -q harnesses && uv run ruff check harnesses       # snapshot tests and lint
uv run python -m harnesses cells                                 # the cell table
uv run python -m harnesses dry-run --cell W-n-0 --task-cell observed-nonrec-far   # $0, fake model
uv run python -m harnesses summary-timing --n 20                 # $0, Σ compaction timing (§4.3)
uv run python -m harnesses pilot-report                          # $0, pooled pilot report (§7.4)
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
| `max_output_tokens` | 32,000 (PREREG D13) on every request: step requests send `HarnessConfig.max_output_tokens`, summary requests `summary_max_output_tokens` (§4.3). Always sent; a config cannot omit it |

Added only when configured: `prompt_cache_key`, `reasoning.summary`. No tools and no server-side `context_management` are sent.

- **Output cap (D13).** On OpenAI `max_output_tokens` counts reasoning and visible tokens together. A response that reaches it comes back with status `incomplete` and `incomplete_details.reason` = `max_output_tokens`, possibly before any visible text, with only a reasoning item ([reasoning guide](https://developers.openai.com/api/docs/guides/reasoning), "Allocating space for reasoning"). The runner scores such a step as an invalid action (§7.5).

- **Input items.** An observation, the bridge and the summary request are user messages: `{"type": "message", "role": "user", "content": [{"type": "input_text", "text": ...}]}`. An earlier turn is its observation followed by that response's output items, sent back as returned (reasoning items with `encrypted_content`, then the assistant message), with null fields dropped. This follows OpenAI's stateless pattern `context += response.output` ([reasoning items cookbook](https://developers.openai.com/cookbook/examples/responses_api/reasoning_items)). Output items of any other type are left out and logged; none are expected because no tools are offered.
- **Reasoning settings.** `effort` defaults to `medium`, the documented default for GPT-6.1 Sol, GPT-6 Sol and GPT-6 Luna. `mode` defaults to `standard`, the documented default ([reasoning guide](https://developers.openai.com/api/docs/guides/reasoning)). Both are configurable.
- **The reply** the environment scores is the concatenated `output_text` of the assistant message items (the SDK's `response.output_text`).

## 4. History policies
Besides the hand-derived snapshots, `tests/test_payload_reference.py` checks every cell over 100 random episodes (per-turn observation and reply lengths, W, whether the system prompt counts and `summary_keep_recent_tokens` all varied) against a brute-force reference that recomputes the kept turns and the compaction points from token counts alone. Every harness test runs with outbound network connections and DNS blocked (`tests/conftest.py::no_network`), so a test that would reach an API fails.

All token accounting uses the generator's tokenizer (tiktoken `o200k_base`) on **visible text only**: observation text, the reply's output text and the bridge text. There is no per-message overhead. Encrypted reasoning items are opaque and are not counted. Because of this, the window boundary and the summary trigger fall on the same steps in the r and 0 arms of a pair whenever the replies are the same. The cost is that an r arm's real context is larger than W by the rendered reasoning (§10).

The episode's system prompt counts toward W if `window_counts_system_prompt` is set; the default is the episode's generator setting, true since generator 0.2.0 (PREREG D5: sys counts toward W, as in the PREREG formulas). **The notes sentence is never counted.** What counts is the episode's own system prompt (`Episode.system_tokens`, 95-150 tokens at the defaults), the same in a notes cell and its no-notes partner. Counting the full instructions would make the two cells of a notes pair (W-n-0/W-0, Σ-n-r/Σ-0-r) evict and compact at different steps whenever a turn boundary falls within the sentence's 21 tokens of W, so the notes contrast would also carry a loss-policy difference. The visible request still sends the sentence; W is just the generator's design budget.

W defaults to the episode's generator `W_tokens`, so the harness evicts exactly where the generator designed near and far.

### 4.1 Full (F)
Every earlier turn, verbatim, in order.

### 4.2 Window (W)
Before sending observation m, keep the longest suffix of whole earlier turns (observation and output items) such that kept turns + observation m (+ the episode's system prompt, if counted; never the notes sentence, §4) ≤ W tokens. This is `persistgym.survival.window_keep_start`, the same function the generator used to design near and far. Dropped turns never come back. The boundary is inclusive: a context of exactly W is kept whole. A test checks that at every step the W cells' visible messages equal `persistgym.survival.reference_window_payload` for the same replies.

### 4.3 Summary at W (Σ)
Before sending observation m, compute the visible context that the step request would hold: bridge + turns since the last compaction + observation m (+ the episode's system prompt, if counted; never the notes sentence, §4). If it exceeds W (strictly) and at least one turn can be compacted, the harness first sends a **summary request**:
- `instructions`: ARC's summary system prompt, verbatim;
- `input`: the current bridge (if any), the turns to compact with their reasoning items, then ARC's `SUMMARY_REQUEST_PROMPT` as a user message;
- the same `reasoning` settings as the cell, including its `reasoning.context`;
- `max_output_tokens` 32,000, as every luna and sol request (PREREG §6, D13). ARC's summary cap of 8,192 applies to the ARC leg's Gemini configs only.

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

**Near cells.** The generator's DESIGN.md §8 warns that a summary cell which compacts the whole history can compact a near reveal. With the default `summary_keep_recent_tokens` = 0, near-cell S in Σ cells is therefore **measured, not designed**. The runner records payload S at every need step, and `compacted_between` (§7.2) for every Σ episode.

`uv run python -m harnesses summary-timing --n 20` ($0, fake model) measures this. It runs the non-recoverable near cells of main templates 0-19 (40 episodes) at the default generator config (0.3.0, with the system prompt counted toward W, PREREG D5; 0.2.0 gave the same numbers), with every reply at the assumed 1,000 tokens and a 300-token summary:

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

Per episode it also records:
- `need_phase`: the need-phase tokens (§7.1);
- `compacted_between` in Σ cells, and the step of every compaction and whether it fired during a lookup round-trip (§7.2);
- `call_latency_s`: wall-clock seconds of every call, retries and backoff included;
- `n_unparsed_routine`: unparsed replies at routine steps (a format-error count; the need step is left out because it is an outcome);
- `need_outcome`: the need step's outcome from the environment (`correct`, `wrong`, `unparsed`, `invalid_lookup` or `incomplete`; `None` if it was never scored);
- `incomplete` and `n_incomplete_routine`: every step response with status `incomplete`, and how many of them were at routine steps (§7.5);
- `n_lookups` (lookups served, at most the cap) and next to it `n_lookups_unavailable` (lookups past the cap that got one "lookup unavailable" turn; generator 0.2.0, D3). Each costs one turn, so `n_turns` = steps + `n_lookups` + `n_lookups_unavailable` for an episode that finishes;
- `model` (requested) and `designed.evidence_steps`.

**Exit reasons:**

| Exit reason | When |
|---|---|
| `DONE` | the episode finished |
| `REASONING_CONTEXT_MISMATCH` | an echoed `reasoning.context` differed from the request (the episode is excluded) |
| `AGENT_ERROR` | one compaction's summary failed `summary_max_attempts` times (each compaction gets its own attempts) |
| `API_ERROR` | an OpenAI error after retries |
| `COST_CAP` | the run's spend reached the planned amount (the transport's stop at `--planned-usd`, not a per-run cost guard: it places no hold, §8) |
| `MAX_TURNS` | the episode passed `max_turns` |
| `RUN_STOPPED` | parallel play only (§7.6): the run stopped while the episode was in flight, and it made no further call |

The run's own exit reason (`meta.json`) is `COMPLETED`, or the stop rule's (`runner._stop_reason`, checked after each episode): `COST_CAP` when the transport stopped an episode at the planned spend, `ABORTED_CONTEXT_MISMATCH` after 2 excluded episodes (§6), `ABORTED_API_ERRORS` after 2 episodes that ended `API_ERROR`. An exception the runner does not handle, Ctrl+C included, gives `ERROR:<type>` and is raised. Parallel play adds `SPEND_RESERVATION` (§7.6).

`run_batch` writes:
- `results/<experiment>/<run_id>/meta.json`, with the fields required by CLAUDE.md, via `common.runmeta.write_meta`. Its `config` holds the run matrix (§7.3) when the CLI passes one;
- `results/<experiment>/<run_id>/summary.json`: errors, latency, cost and the echo-match rate, built from an allowlist (§7.4);
- `episodes.jsonl`, one line per episode, next to `meta.json`. For a pilot-blinded experiment it goes to `results/raw/<experiment>/<run_id>/` instead (§7.4);
- `results/raw/<experiment>/<run_id>/transcript.jsonl.gz` (gitignored).

For a paid transport, `run_batch` also calls `finalize` in a `finally` block, which appends exactly one `results/costs.csv` row.

### 7.1 Need-phase tokens (D8)
The researcher chose need-phase tokens as H1's primary token reading (D8, 2026-10-01): R_need = [N(W-0, far) / N(F-0, far)] / [N(W-0, near) / N(F-0, near)] ≥ 1.30. `need_phase` holds one episode's N:

| Field | Meaning |
|---|---|
| `tokens` | **N**: provider-reported `input_tokens` + `output_tokens`, summed over every call made while the need step is pending. OpenAI's `input_tokens` includes cached tokens and `output_tokens` includes reasoning tokens, so this is "input incl. cached + output incl. reasoning" |
| `input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_tokens` | The same sum by component |
| `n_calls`, `n_step_calls`, `n_lookup_result_calls`, `n_summary_calls` | Calls in the phase. Each lookup adds one step call that answers the lookup result; a "lookup unavailable" turn counts here too |
| `summary_tokens` | The part of `tokens` spent on summary calls fired while the need step was pending |
| `first_step_call` | Usage of the need step's first step call: H2's `usage[n]` (D9), for TE |
| `complete` | The call that returns the scored action was made. False when the episode stopped inside the phase (error, cost cap, echo mismatch) |

The phase runs from the first call at the need step through the call that returns the scored action (a non-lookup reply, or a lookup the environment scores as an invalid action), with every lookup round-trip in between. A "lookup unavailable" turn is not scored, so it is one more round-trip inside the phase. It is the run of calls whose pending step is the need step. `need_phase` is `None` when the episode never reached the need step.

A summary call that fires while the need step is pending is a call at the need step, so it is included, and `tokens − summary_tokens` gives the reading without it. H1's cells (W-0, F-0) never summarize, so for H1 the two readings are the same.

### 7.2 `compacted_between` (D12)
In Σ cells, `compacted_between` = 1 iff a summary fired **after the first reveal step and before the agent first saw the need-step observation**; otherwise 0. Here r_first = min(`evidence_steps`) and n = `need_step`. In terms of the step s pending when a summary fired, it counts when r_first < s < n, or when s = n and the summary fired before the need step's first call, so that it was applied to that call's payload. Details:
- **Lookup round-trips at the need step do not count.** A summary that fires while a lookup result at step n is pending comes after the agent saw the need-step observation, so it does not set `compacted_between`. Its entry in `compactions` has `at_lookup_result` = 1. A summary during a lookup at an earlier step s with r_first < s < n counts, because it is still before the need step.
- A summary that fires at step r_first itself (before the reveal observation, or during a lookup at r_first, whose result re-shows the evidence) does not count.
- Only successful compactions count. A failed summary attempt changes nothing in the session.
- s is the environment step pending when the summary fired, not the turn. Lookups add turns, so after a lookup `at_turn` = `at_step` + 1. Every entry of `compactions` carries `at_step` and `at_lookup_result` (0 or 1).
- `None` in W and F cells, for the withheld variant (no evidence), and when the need step was never presented (for example a summary that failed every attempt).

The runner counts the compactions applied before it sends the need step's first call, so the value does not depend on the at_step bookkeeping. Tests recompute it from the transcript in every Σ cell, with and without lookups at the need step. With the fake model's short replies, near cells give 0; with 150-token replies they give both 0 and 1. One test covers the case that separates the two readings: template 0's recoverable near episodes, with 150-token replies and 3 lookups at the need step, compact at step 11 and during a lookup at the need step 20. That gives `compacted_between` = 0, and the need payload still shows the evidence verbatim.

Σ results are reported split by `compacted_between`, and Σ cells enter no confirmatory test (D12).

The earlier version of this branch counted every summary at a step in (r_first, n], including those during lookups at n. The #13 review flagged that reading, and it was changed to the one above (§10).

### 7.3 Run matrix (D11)
`harnesses/matrix.py`. A `RunMatrix` maps each task cell to a template count n. The cell runs on the first n templates from `--start`, so a cell with fewer templates uses a prefix of another cell's templates and every contrast stays within-template. Episodes come out template by template, so a run stopped by its cost cap leaves whole templates plus at most one partial template, the one in progress. The r and 0 arms are separate runs, so their pairs are the episode ids both arms finished. `meta.json` records the matrix.

| CLI | Matrix |
|---|---|
| `--n N [--task-cell ...]` (default `--matrix full`) | the chosen task cells (default all 8) on N templates, as before |
| `--matrix d11 --n T_d [--n-observed T_o]` | the researcher's D11 option A for sol (2026-10-01): derived-far cells (R and NR) on T_d templates, observed-far cells (R and NR) on the first T_o of them (default T_d / 3), no near cells |
| `--cell-templates CELL=N ...` | a custom matrix |

Central case: `--matrix d11 --n 120` is 320 episodes per harness cell, 640 over F-r and F-0. On the main split the CLI prints a note when the start or a count is not a multiple of 10, since D7 wants whole 10-template balance blocks (T_d a multiple of 30). The pilot limit of 10 episodes counts the matrix's episodes. A test checks that every matrix episode is identical to the fully crossed generation's episode for that template and cell.

### 7.4 Pilot blinding (PREREG §11)
> Pilots report only validity levels, pooled tokens, errors, latency and cost; never per-arm success, per-arm reasoning tokens (H2's token outcome) or per-config ARC level progress. (PLAN §16.5)

`harnesses/blinding.py` implements this for every experiment in `BLINDED_EXPERIMENTS` (`persistgym_pilot`):
- `episodes.jsonl`, which holds `need_correct`, the need-phase tokens, per-episode usage and lookups, is written only to `results/raw/<experiment>/<run_id>/` (gitignored).
- The committed `results/<experiment>/<run_id>/` holds only `meta.json` and `summary.json`:
  - `meta.json`'s `tokens` sets `reasoning_tokens` to null. A `blinding` field names the rules and the raw paths. One run is one harness cell, so its reasoning total would be a per-arm number;
  - `meta.json`'s `parallel` (§7.6) keeps only the fields in `blinding.PARALLEL_FIELDS`, and the whole block goes to `results/raw/<experiment>/<run_id>/parallel.json`, next to the reservation log, for a sequential run too. If that file cannot be written, the run warns and `blinding.parallel_path` is null. Pilots report cost, but nothing finer than the run's total, which the costs row already holds. So the committed block leaves out the per-episode spend estimate (`spend_reservation.last_estimate_usd`, twice the largest finished episode's spend), the peak of episodes in flight (under a spend plan it bounds that estimate) and the per-call gate's waits and peak of calls in flight (they depend on the spend as it went and on each call's payload size, which in the replay arms grows with the reasoning replayed). It keeps the planned spend, the estimate rule and factor, the counts of episodes and calls, the stop reason and the abandoned episodes. Whether the plan held is in those: the stop reason (`SPEND_RESERVATION` or `COST_CAP`), the episodes not started, and the run's `cost_usd` against `planned_usd`;
  - `summary.json` holds errors (exit reasons, exclusions, summary failures, unparsed routine replies), latency (median, p90, max seconds per call), cost (list, billed estimate) and the echo-match rate per cell. The echo-match rate is a toggle check and exempt (PREREG §11, D29). Both summaries and the committed `parallel` block are built from an allowlist, so a field added to `EpisodeRun` or to the `parallel` block later cannot leak into a committed pilot file.
- The paid transport's `results/costs.csv` row leaves `reasoning_tokens` empty and says so in `notes`. The per-call values stay in the raw transcript.
- `python -m harnesses pilot-report` ($0) is the committed script that produces the pilot report. It reads every raw pilot run and writes `results/persistgym_pilot/pooled-<time>/pilot_report.json`. Per model it reports:
  - tokens pooled over the harness cells run. Reasoning tokens are shown only when at least 2 cells are pooled, so a pool never equals one arm;
  - validity levels: the need-correct rate of the restated and withheld variants, pooled over cells and arms, counting finished, non-excluded episodes. The base variant's success is never reported;
  - errors, latency, cost and the per-cell echo-match rate.

The echo and replay probes (`toggle_pilot`, `replay_probe`) and validity runs (`persistgym_validity`) are not blinded.

Two CLI checks keep pilot data inside this path:
- `--split pilot` runs only under `--experiment persistgym_pilot`, the reverse of the older check. Pilot templates are pilot data, and `run` defaults to `--split pilot`, so `--experiment persistgym` without `--split main` would otherwise commit per-arm outcomes on pilot templates.
- `run_batch` and the CLI refuse a run id or experiment that is not one plain folder name. A run id like `../../x` would otherwise put a blinded run's `episodes.jsonl` at `results/x/`.

`summary.json`'s errors also count `n_incomplete_routine`, the step responses that stopped at the output cap at routine steps (§7.5). One at the need step scores 0, so it is an outcome: the per-step `incomplete` records and `need_outcome` stay in `episodes.jsonl`, under `results/raw/` for a pilot.

What this does not blind (§11): the per-run `costs.csv` row (one per run, required by CLAUDE.md) still holds that run's input and output tokens, calls and cost, and so does the run's `meta.json` (`tokens` without `reasoning_tokens`, as CLAUDE.md asks for token totals). `summary.json`'s `latency.n_calls` is the run's call count. Output tokens are mostly reasoning tokens, and calls minus steps counts lookups and summaries, so these approximate the withheld numbers for one arm. Only the explicit `reasoning_tokens` fields are withheld. For a parallel pilot, `summary.json`'s exit reasons count the episodes that ended `RUN_STOPPED`, and a stop by Ctrl+C or an error prints how many episodes were in flight. Each says roughly how many episodes were in flight when the run stopped, which under a spend plan bounds the per-episode estimate, as the withheld peak does, though more loosely.

### 7.5 Incomplete responses (D13)
> A response with status `incomplete` at the need step (for example, hitting `max_output_tokens`) counts as a content failure and scores 0. (PREREG §6; §13: content failures score 0 and are not re-run)

Every request, step or summary, carries `max_output_tokens` 32,000 (§3). When a **step** response comes back with status `incomplete`, for whatever reason:
- **It is scored as an invalid action.** The runner calls `EpisodeEnv.step(reply, invalid="incomplete")`: the pending step's outcome is `incomplete`, with no action and no option label, even if the partial text holds the correct answer. Nothing in the partial text is parsed, so a `lookup(...)` in it is not served and adds no turn.
  - At the need step this is the scored action and scores 0 (`need_outcome` = `incomplete`). That includes an incomplete answer to a lookup result at the need step. The need phase (§7.1) ends with that call, and `need_phase.complete` is true.
  - At a routine step it counts against `routine_accuracy`, like any wrong action, and the episode goes on.
  - The episode is not excluded and not re-run, and the exit reason stays `DONE`.
- **It is logged.**
  - The episode record gets one `incomplete` entry: `turn`, `pending_step`, `at_need` (0 or 1), `is_lookup_result`, `reason` (`incomplete_details.reason`), the `max_output_tokens` requested, the `output_tokens` used and `reply_chars` (length of the partial text).
  - `n_incomplete_routine` counts the routine-step entries, and `summary.json` sums it (§7.4).
  - The raw transcript's `echo` holds `status` and `incomplete_reason` for every call, and the paid transport logs a warning with the reason. For a pilot (§7.4) it logs no warning and no call's status: the warnings, less the routine ones `summary.json` counts, would count those at the need step.
- **The history keeps the turn as returned.** The session sends its output items back on later turns like any other turn (§3): the reasoning item, and the partial message if there is one. A response that stopped while reasoning therefore leaves a turn with no reply, and its visible reply counts 0 tokens toward W. The r and 0 arms of a pair do the same, so they still differ only in `reasoning.context` (tested). OpenAI's stateless pattern says to preserve every output item and replay the complete history ([reasoning guide](https://developers.openai.com/api/docs/guides/reasoning), "Preserve reasoning without stored responses"); whether the API accepts a reasoning item replayed without a following message has not been checked (§11).

Summary responses are not scored. An incomplete summary is retried, as before (§4.3), and is counted in `n_summary_failures`, not in `incomplete`.

The probes send the same 32,000 cap (§9). They record each trial's `incomplete_turns`.

### 7.6 Parallel episodes (PREREG §4.6; §0.3 line 15)
> PersistGym runs go one at a time, but a run may play up to 16 episodes in parallel. This changes no payload and no cost. The run reserves spend for the episodes in flight, so it never exceeds its planned spend. (PREREG §0.3, line 15, changed by the researcher on 2026-10-01)

`run --parallel N` (1 to 16, default 1; `run_batch(..., parallel=N)`, `harnesses/parallel.py`) plays up to N episodes of the run at once, each in a worker thread. N = 1 is the sequential loop, unchanged. The CLI refuses any other N before it takes the paid-run lock. One run is still one harness cell, one costs.csv row and one paid-run lock; only the episodes inside it overlap.

**What stays as in sequential play.**
- *Payloads, cell assignment and seeds.* Each episode has its own session and environment and sends what it sends when played alone; the transport is the only thing the episodes share. Episodes start in the run's order (template by template, `ALL_CELLS` order within a template, §7.3), so the episodes started are always a prefix of that order, and a stopped run still leaves whole templates plus the partial ones in progress.
- *Outputs, in the run's order.* While an episode plays, its transcript goes to its own file, `results/raw/<experiment>/<run_id>/inflight/<index>.jsonl`. Once it and every earlier episode have finished, its line is appended to `episodes.jsonl` and its file to `transcript.jsonl.gz`, and the file is deleted; the folder is removed at the end. `episodes.jsonl`, the decompressed transcript and `summary.json` are then byte for byte those of sequential play with the same responses, apart from each call's wall-clock seconds (`call_latency_s`, which a test fixes). `meta.json` differs only in the run's ID, timestamps and paths and its `parallel` field, which is outside `config`, so the config hash is the same. A pilot stays blinded: every per-episode file is under the gitignored `results/raw/` (§7.4).
- *The stop rules.* `COST_CAP`, the abort after 2 excluded episodes and the abort after 2 API errors are checked as each episode finishes, in the order they finish. When the run stops, for one of these, an exception or a Ctrl+C, it starts no more episodes, and each episode in flight makes no call after the one it has in flight: its next call raises `RunStopped`, it ends `RUN_STOPPED`, and its record and transcript are written in their place. So an abort with N episodes in flight costs at most one more call per episode.

**Spend reservations** (`SpendPlan`; paid transport only, since the fake model has no planned spend). The run does not start an episode unless *spent + reserved + estimate ≤ planned spend*:
- *spent* is the run's spend so far, the transport's `spent_usd` (the billed estimate, the measure of block spend, §8);
- *reserved* is, over the episodes in flight, what each reserved at its start and has not spent yet;
- *estimate* is twice the largest spend of a finished episode of the run, once one has finished `DONE` (a whole episode). Before that it is all that the planned spend leaves, an upper bound because the transport stops the run there, so episodes play one at a time until one has finished `DONE`. Episodes differ in length (21 to 27 steps over the first 120 main-split templates, plus lookup turns) and a full-history episode's input grows with about the square of its length, hence the factor of 2 (`ESTIMATE_FACTOR`).

If the next episode does not fit, the run waits for one in flight to finish and checks again. With none in flight it starts no more episodes and ends `SPEND_RESERVATION`, with the rest of the matrix not started (`episodes_not_started` in `meta.json`). Every start is logged with the four numbers to `results/raw/<experiment>/<run_id>/spend_reservations.jsonl`. So a parallel run cannot use the last part of its planned spend, up to about twice its largest episode's spend, which a sequential run would spend on its last episodes (ending `COST_CAP` inside one): a run meant to finish its matrix needs `--planned-usd` with that margin above its forecast.

**The transport's stop stays exact** (§8). `send` may be called from several threads; the stop check, the ledger and the echo log change under one lock, so the check before each call sees every call recorded so far, and each thread gets its own client from the factory. The stop ends an episode `COST_CAP`, which stops the run, but the calls already in flight when it fires still complete and are recorded. On its own it would therefore let a parallel run whose estimate was too low end above its planned spend by up to one call per episode in flight (in one trial of `test_overlapping_calls_never_take_the_run_past_its_planned_spend` with the gate removed, 16 episodes in flight that were all far dearer than estimated ended about 12 calls over).

**Per-call gate** (`CallGate`; paid transport only, with the reservations). Every call of a parallel paid run therefore first passes a gate. With no other call in flight it goes ahead, and the transport's stop applies as in sequential play. With others in flight it goes only if *spent + the most the calls in flight can cost + the most this call can cost ≤ planned spend*; otherwise it waits until a call returns, or ends `RUN_STOPPED` if the run stops meanwhile. The most a call can cost (`CallGate.bound_usd`) is its `max_output_tokens` (32,000 on every request, D13) at the output price plus one input token per byte of its JSON body at the cache-write price, at list prices (no Flex discount). A request without a cap counts as unbounded and goes only alone. So calls that overlap can never take the run past its planned spend, and a parallel run ends above it by at most the one call that went alone, as a sequential run can. The bound assumes that a request has no more input tokens than its JSON body has bytes. That holds for text, since an o200k_base token is at least one byte, and is assumed for replayed reasoning items, whose `encrypted_content` carries their tokens. The gate waits only once the planned spend has less room left than the bounds of the calls that would overlap. With the payloads of default-volume episodes (about 50-110 kB of JSON each with the fake model; more with real replayed reasoning), a bound is about $0.02-0.03 on gpt-6-luna and $0.45-0.60 on gpt-6.1-sol, so 16 calls overlap freely until roughly the last $0.50 of a luna run and the last $10 of a sol run. It changes when calls are sent near the end of a run, never a payload. `meta.json` `parallel.spend_reservation.call_gate` counts the calls, those that waited and the peak of calls in flight (for a pilot, the calls only; §7.4).

**Ctrl+C.** The first one stops the run and waits for the call each episode has in flight, so that it is recorded; then everything is written as above and the run ends `ERROR:KeyboardInterrupt`, like a sequential run, with its costs row and the lock released. A second Ctrl+C stops the wait: the episodes still in flight are abandoned (`meta.json` `parallel.abandoned_episode_ids`; their transcript files stay under `inflight/`), the worker threads are daemons, so the process can exit, and the transport, finalized with calls in flight, writes the row of the calls it recorded and keeps the paid-run lock and the spend reservation with the reason (`abandoned_calls`), since the abandoned calls' usage is recorded nowhere.

`meta.json`'s `parallel` holds `max_episodes_in_flight` (N; 1 for a sequential run) and, for parallel play, the peak in flight, episodes started and not started, the stop reason, abandoned episodes and the reservation summary. For a pilot it holds the allowlisted part, without the per-episode spend estimate, the gate's waits or the peaks in flight, and the whole block is in `results/raw/<experiment>/<run_id>/parallel.json` (§7.4). The costs row's notes end their run description with `parallel=N` when N > 1.

## 8. Paid calls (`openai_transport.py`)
`OpenAIResponsesTransport` is the only code here that can spend money. Its constructor refuses (`PaidCallsNotAllowed`) **before building any client** unless every check passes. The checks are `common.approval.require_paid_run`, which the ARC launcher (`arc/run_path.py`) runs too. First:
- the run holds the PersistGym stream's **paid-run lock** (below), which `cli.py` takes before any of these checks, so two PersistGym runs cannot both pass them, and the run's experiment is a PersistGym one (`common.paidlock.EXPERIMENT_STREAM`);
- this checkout's `results/costs.csv` can be read and holds the **row of each stream's last paid run** (below);
- **no hold stands** (below): every paid run that ended `COST_CAP` at its run guard, or whose spend passed that guard before it could stop the run, has been cleared by the researcher.

Then come the checks of the shared guard, `common.approval.require_paid_approval`. It lives in `common/` so that the ARC launcher can reuse it, and `harnesses.openai_transport` re-exports its names. The checks:
1. `PERSISTGYM_ALLOW_PAID=1` is set;
2. `--approved-block <name>` is given. This is the researcher's approved spending block from PLAN §16.2;
3. the experiment has a budget phase in `common/costs.py`;
4. `--planned-usd` is a positive, finite number (`nan` would otherwise pass every budget comparison);
5. `PREREG.md` is **committed** (§16.3: PREREG committed before any paid call): tracked by git, present in `HEAD`, and with no uncommitted changes. A draft in the working tree does not count;
6. the block's **approval line** is in `results/decisions.md` on `origin/main`, in `HEAD` and in the working tree (below);
7. `PREREG.md` in `HEAD` is **identical to `PREREG.md` on `origin/main`**, read after the same fetch as check 6 (`common.approval.prereg_not_on_remote`, which compares the two blobs with replace refs off). Only the merged, frozen PREREG unlocks paid calls: a PREREG or amendment committed on a branch but not merged refuses, and so does a `HEAD` that lacks an amendment already merged to `main`;
8. the run's experiment is in the line's `experiments` list;
9. every `results/costs.csv` row can be counted (`common.approval.check_ledger`): each cost is empty or a finite, non-negative number, at least one of the two is filled in, and each experiment has a budget phase. A `nan` cost would otherwise make the phase-cap comparison pass, a negative one would add headroom, a row with no cost would count as free, and a row with no phase would count toward no cap;
10. block spend + `--planned-usd` ≤ the line's `max_usd`;
11. `common.costs.headroom(planned_usd, phase, rows)` ≥ 0: the phase cap still applies.

Last, `PREREG.md` (the blob check 7 compared) must be **frozen**: a `Version:` line of at least 0.2 with no suffix such as `-draft`, and a `Status:` line starting "Frozen" (`common.approval.prereg_not_frozen`; the rule is `common/prereg.py`, which `arc/draw_games.py` and the ARC launcher use too). Check 7 alone accepts a draft that has been merged to `main`, and the draft says no paid call may be made under it. Then the run's **spend reservation** (below): checks 10 and 11 again, counting the planned spend of an ARC run that is going.

**One paid run at a time per stream: the locks** (PREREG §0.3 line 15, §12). `run`, `probe-echo` and `probe-replay` take the PersistGym stream's paid-run lock (`common/paidlock.py`): `persistgym-paid-run-persistgym.lock` in the git common directory, shared by every checkout. The ARC launcher takes `persistgym-paid-run-arc.lock` next to it, so one ARC run may go beside one PersistGym run. They take it after their argument checks and before the transport's checks, and hold it for the whole command (all models of a probe). A command refuses (exit 2) while another PersistGym run holds it, and while the old single lock `persistgym-paid-run.lock` of a launcher from before the per-stream locks exists. With `PERSISTGYM_ALLOW_PAID` unset the command refuses before it touches the lock.
- *The last runs' rows.* After appending its costs.csv row, `finalize` records the run in `persistgym-paid-last-run-persistgym.json` next to the lock (the ARC launcher writes `persistgym-paid-last-run-arc.json`): its run ID and the row's `timestamp_utc`, because a `--run-id` can be given again and an older row with the same ID must not stand in for the newest one. A paid run of either stream whose own `results/costs.csv` lacks the row of either stream's last run (or of the run in the old `persistgym-paid-last-run.json`) refuses: each checkout has its own ledger, so a run started in another checkout would undercount the block and phase spend. Run both streams from one checkout, or bring the rows over first. Rows of the other stream before, between and after those rows do not matter.
- *Spend reservations* (PREREG §12, "Operational"; `common.approval.reserve_spend`). A run's planned spend counts against its block and phase from its start until its costs row is written, so a PersistGym run and an ARC run going at once cannot both use the same room (block 1 lists experiments of both streams; phases 0 and 2 have runs of both). After the other checks, under an operating-system lock both launchers take (`persistgym-paid-budget.mutex`), the transport reads the ARC stream's reservation, the ledger and the last-run records, refuses if the block or phase would go over once the ARC run's planned spend is counted, and otherwise writes `persistgym-paid-reservation-persistgym.json`. `finalize` removes it after the row and the last-run record are written (or at once if the run made no call), and releasing the lock removes it too; each model of a probe reserves what the earlier ones left. A run that keeps its lock keeps its reservation. A reservation of the PersistGym stream found by the next PersistGym run is left over from a run that did not end cleanly, and refuses until the operator deletes it.
- *Spend the ledger does not show.* If a run made calls whose row is not in costs.csv, the lock stays held, with the reason and the run's usage totals in the file (`keep_lock_if_unaccounted`; reasoning tokens left out for a blinded pilot, §7.4). That covers a row that cannot be built or written (`finalize` keeps the lock and raises) and a run whose `finalize` never ran (the CLI checks every transport after its run). Every later PersistGym run refuses and prints the reason until the operator has added the row by hand and deleted the lock file and the reservation it names. A process that is killed leaves the lock and its reservation behind too.
- *Two writers of costs.csv.* An ARC run and a PersistGym run may append their rows at the same moment: `common.costs.append_row` holds an operating-system lock on the ledger for the append and `read_rows` takes it too (`common/oslock.py`), so rows never interleave and a check never reads half a row.
- *Tests.* Every harness test points `cli.LOCK_PATH` into a folder that does not exist (`conftest.no_shared_paid_lock`), so a test cannot take the shared lock, write its last-run record, write a reservation or read or write the hold record next to it; the paid-path tests use a temporary lock of their own.

**No paid run while a hold stands** (PREREG §0.3 line 12, §7.7, §12; `common/hold.py`). A paid run that ends `COST_CAP` at its run guard, or whose spend passed that guard before it could stop the run (the step that crossed it failed, or the process died first), places a hold: a line in `persistgym-paid-holds.jsonl`, next to the lock, naming the run ID, the experiment, the reason and the time. While any hold stands, `require_paid_run` refuses every paid command, ARC or PersistGym (exit 2, before the transport builds a client), naming each run and the exact line that clears it. It also refuses while a paid-run lock of either stream is kept by a run that may have placed a hold the record does not show (the ARC launcher could not write it, or its accounting stopped before it could rule one out): such a lock is marked `hold_not_recorded`, since the ARC lock alone would stop only ARC runs (`common.paidlock.unrecorded_hold`). Only the researcher clears a hold, by merging this line into `results/decisions.md`:

```
    cleared_hold: <run_id>
```

It follows the rules of the approval line below: exactly this spacing, at column 0, `<run_id>` matching `[A-Za-z0-9._-]+`, outside any fenced code block or HTML comment, and on `origin/main` (fetched first; the fetch runs only when a hold is recorded), in `HEAD` and in the working tree. Removing it from any of the three, or hiding it in a code block or comment, puts the hold back, and the refusal names look-alike lines. One line clears one run's hold. A record line that cannot be read as a hold refuses until fixed by hand, and a run may not reuse the run ID (the lock's `run_id`) of a run that placed a hold, so a clearing line never clears a later run.
- *Who places holds.* Today only the ARC launcher (`arc/run_path.py`): its harness cost guard is D22's $120 run guard for a counted run and the planned spend for a pilot or check. The PersistGym transport has no per-run cost guard. It stops a run before a call once the run's spend reaches `--planned-usd`, which the runner records as the exit reason `COST_CAP` (§7), but that is the planned spend, not a run guard in the sense of PREREG §7.7, so it places no hold. A PersistGym per-run guard, if one is ever added, must call `common.hold.place_hold` when it ends a run.

**The approval line.** One line, with exactly this spacing:

```
    approved_block: <name> | experiments: <exp1>,<exp2>,... | max_usd: <amount>
```

- `<name>` matches `[A-Za-z0-9._-]+`.
- The experiments are a comma-separated list with no spaces, at least one and no repeats. Each is a key of `common.costs.EXPERIMENT_PHASE` or starts with `ext_`.
- `<amount>` is a positive, finite decimal number of US dollars made of ASCII digits with an optional fractional part (`76`, `2.50`). A sign, exponent, `$`, thousands separator or non-ASCII digit makes the line malformed.
- The line starts at column 0. Only trailing whitespace (a CR, Markdown spaces) is ignored. A list marker, indentation, backticks, other spacing or another case makes the line malformed, and a malformed line never counts. The refusal names the working-tree lines that look like an approval of the block but do not parse.
- Lines are split on `\n` only. A form feed or U+2028 cannot start a line.
- The line is not inside a fenced code block (```` ``` ```` or `~~~`, open to the end of the file if never closed) or an HTML comment. A proposed or example line that a gate entry shows in a code block, or a line commented out, never counts, and the refusal names it with the look-alikes (`common.approval.shown_lines`). Where this check simplifies CommonMark, it errs toward ignoring a line, which can only refuse.

**Where it must be.** The guard first runs `git fetch origin main`, written as `+refs/heads/main:refs/remotes/origin/main` so that the remote-tracking ref is updated whatever the remote's fetch config says. Prompts are off and there is a 60 s timeout. `origin` must be a configured remote: given a name that is not one, git would fetch from a directory of that name instead. If it is not configured or the fetch fails, the guard refuses. The same line, compared after trailing whitespace is removed, must then be in all three copies of `results/decisions.md`: `origin/main`, `HEAD` and the working tree. git reads them with replace refs off (`GIT_NO_REPLACE_OBJECTS=1`), so a local `git replace` cannot stand in for the fetched file.
- An approval reaches the guard only through the researcher's merge. A line committed on a feature branch is refused until it is on `main`.
- Removing the line from any of the three, changing it, or moving it into a code block or HTML comment counts as a revocation: a revocation merged to `main`, a committed one not yet pushed, or an uncommitted one.
- A changed line (for example a raised `max_usd`) counts only once the new line is on all three.
- Two different valid lines for one name are ambiguous and refuse. The same line twice is not ambiguous.
- The remote and branch are injectable (`common.approval.RemoteRef`, the transport's `approval_remote`). Tests use a local bare repository as `origin`, with `GIT_ALLOW_PROTOCOL=file`, so they never reach a network.

**One spend measure: the billed estimate.** Spend is a row's `cost_usd_billed_est`, or its `cost_usd_list` only when the billed estimate is empty (`common.costs.spend_usd`, re-exported as `common.approval.spend_usd`). A row with neither cannot be counted and refuses (check 9). Block spend against `max_usd`, the phase-cap check (`common.costs.headroom`), a run's own stop at `--planned-usd` (the transport's `spent_usd`) and the split of `--planned-usd` over a probe's models all use this one function, so a run planned at $x adds at most $x, plus its last call, to its block's spend.
- *Why billed.* Every cap and estimate for PersistGym in PLAN §12, §16 and §17 is in Flex-billed dollars, and D23 makes the billed estimate the primary cost basis. On Flex the list cost is twice the billed estimate, so counting list, or the larger of the two as the guard did before, would trip the caps at about half the real spend. The billed estimate is what the researcher pays: the Flex price for Flex runs, with cached input and cache writes at their own prices (`pricing.py`).
- *List is still kept.* Every costs.csv row holds both `cost_usd_list` and `cost_usd_billed_est`, and `python -m common.costs` prints both sums next to the spend the caps count.
- *The backstop.* The billed estimate comes from our price table. The provider-side hard spend limits, which the researcher sets in real billed dollars, remain the backstop against under-estimation (§11).

**Block spend** is the sum, over `results/costs.csv` rows whose `notes` contain `approved_block=<name>;`, of that spend. Every costs row the transport writes starts its notes with that tag (`common.approval.spend_tag`). A row whose cost cannot be read, or that has no cost at all, refuses (check 9).

The approval line records the researcher's decision. It is added only on the researcher's explicit instruction, under that day's entry, and reaches `main` through the researcher's merge like every change. `results/decisions.md` explains the grammar near its top. Its examples are in a code block, indented and use `<placeholder>` names, so none of the three lets them count. A test checks this, and that every other line of the file is shown text, so no unclosed fence or comment hides later entries.

`--planned-usd` is the planned spend of the whole command, in that measure: for `probe-echo` and `probe-replay` with several models, each model's transport gets only what the earlier models left. `run` refuses a `persistgym_pilot` run on any split other than `pilot` (§16.5: pilot templates use a disjoint seed range).

While running, it:
- stops before a call once the run's spend (the measure above) reaches `--planned-usd` (`COST_CAP`). The call that crosses it is not cut short, so a run can end above its planned spend by up to one call; with `--parallel N` too, since the run's per-call gate sends calls that overlap only while even their most expensive outcome fits (§7.6);
- retries 429s, timeouts and 5xx errors with exponential backoff, but never `insufficient_quota`. Flex 429s are not charged ([Flex guide](https://developers.openai.com/api/docs/guides/flex-processing)). A timed-out or dropped connection may still have been processed and billed; such attempts are not in the ledger;
- logs the echoed `reasoning.context`, the returned model string, the served service tier and the status of every response, with a warning and `incomplete_details.reason` for an `incomplete` one (§7.5);
- appends one costs.csv row per run. Its `notes` start with `approved_block=<name>;` (what block spend sums) and hold the number of context mismatches and the git dirty flag. For a pilot-blinded experiment `reasoning_tokens` is left empty (§7.4). `service_tier` is the requested tier. The served tier, cache-write tokens and median seconds per call go into the `service_tier_served`, `cache_write_tokens` and `latency_s` columns when `common/costs.py` has them (schema of 2026-10-01 on `main`), and into `notes` otherwise. A response whose returned model string has no price is priced as the requested model and flagged in `notes` rather than dropped from the log.

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
PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses run --cell F-r \
    --model gpt-6.1-sol --split main --matrix d11 --n 120 --experiment persistgym \
    --approved-block "<block>" --planned-usd <usd> --parallel 16  # D11 (§7.3), §7.6
```
`run` defaults to the pilot split, which has a disjoint seed range, and the `persistgym_pilot` experiment. It refuses more than 10 episodes for a pilot.

`tests/test_cli_end_to_end.py` runs all three commands, and a D11 matrix run, through the real guarded transport with a stub client answered by the fake model. It checks that each run writes its results, `meta.json` and exactly one costs.csv row, so a bookkeeping crash cannot happen for the first time after paid calls. It also checks that a pilot run commits only `meta.json` and `summary.json` and leaves `reasoning_tokens` empty in its costs row, that a parallel pilot's `meta.json` holds no per-episode spend estimate while its raw `parallel.json` does, and that the commands hold the paid-run lock while they run, refuse while another run holds it, while a hold stands (until its clearing line is merged), under a merged draft PREREG or when the last run's row is missing, and keep it held when a run's row cannot be written or `finalize` never ran. It also checks that a run stopped at its planned spend (`COST_CAP`) places no hold, and that `run --parallel 4` writes the episodes, transcript, summary and costs-row totals of `--parallel 1` through the guarded transport. `tests/test_parallel.py` covers parallel play with the fake model (§7.6), and `tests/test_paid_guard.py` the transport's sends from 16 threads, its stop across threads and `finalize` with calls in flight.

## 9. Probes (`probes.py`)
The probes are excluded from every analysis (§16.3). Their snapshot tests show that the two arms send identical payloads except `reasoning.context`, at every turn. Every probe request carries `max_output_tokens` 32,000, as the harness cells (`ProbeConfig.max_output_tokens`, D13), and every trial records its `incomplete_turns` (the turns whose response came back `incomplete`).

### 9.1 Echo check
For gpt-6.1-sol and gpt-6-luna, each in both contexts, the probe runs a two-turn stateless conversation ("Reply with only the word: ready", then "...: done"). It passes when every response echoes the requested `reasoning.context`. The second turn carries the first turn's reasoning item, so the echo is observed with earlier reasoning present.

### 9.2 Private-choice replay-use probe
The probe has three turns:
1. "Privately pick a random three-digit number. Do not write the number or any hint about it. Reply with only the word: ready";
2. a filler question;
3. "What is the three-digit number you privately picked at the start of this conversation? Reply with only the number."

The prompts contain no digits. Under `all_turns`, the turn-3 sample can see the turn-1 reasoning; under `current_turn`, it cannot.

**Scoring.** The picked number exists only inside the encrypted reasoning, so both arms request `reasoning.summary: "auto"`, identically. A trial is scored as follows:
- *scorable*: the turn-1 summary names exactly one three-digit number, no visible reply leaks one, every echo matches, and the turn-1 and turn-2 responses completed (an incomplete one leaves the set-up unclear, so the trial is replaced, like a leak);
- *match*: the turn-3 answer equals that number. An incomplete turn-3 response is an invalid answer (`answer` = `None`, a miss), whatever its partial text says (D13).

The summary text is stripped from the reasoning items sent back (`summary: []`), so the only channel for the number is the encrypted reasoning.

**Chance.** Chance is 1/900 (100-999; §16.3 says 1/1000) only for uniform guesses. Models pick "random" numbers unevenly, so a no-replay arm can match by sharing number preferences. Report `chance_agreement(picks, answers)` next to the two match rates, and also the share of turn-3 answers that are not a number at all (e.g. "I cannot recall").

**Block 1 (2026-10-02).** This design could not score: sol's turn-1 summaries were empty in 40 of 40 trials and luna's named exactly one number in 2 of 40, so 0 and 2 trials were scorable. It stays available, unchanged, as `probe-replay` (the default `--design original`). PREREG §17.1 (amendment R1) replaces it for D29 with §9.3. The per-arm block-1 numbers there come from `probes.replay_report`, which the $0 command `uv run python -m harnesses probe-summary <run_id> ...` prints from a run's `trials.jsonl` (and its raw transcript when present: empty summaries, turn-1 reasoning tokens, the echoed summary setting). For a fork run it prints `fork_report` again.

### 9.3 Fork-consistency replay-use probe (PREREG §17.1)
`probe-replay --design fork`. It needs no summary to know the pick: it asks the same question twice from the same state and checks that the answers agree.
1. Turn 1 shows a fresh list of L = 20 distinct three-digit numbers and asks the model to privately pick one at random, write neither the number nor a hint, and reply only "ready". The list comes from `random.Random(seed)` (`sample` from 100-999, then `shuffle`), with seed = 290,000 + the attempt index (0-39): a dedicated stream outside every template range. Attempt *i* shows the same list in both arms and for both models.
2. Turn 2 is the original filler.
3. Turn 3 asks which number from the list it picked, with the number only, in K = 2 forks: two API calls whose requests are copies of one built request (the same history, the same stripped reasoning items as §9.2, the same settings). Each trial records the SHA-256 of each fork's request body.

Both arms send identical payloads except `reasoning.context`, with the settings of §9.2: medium effort, standard mode, Flex, `max_output_tokens` 32,000 and `reasoning.summary: "auto"`. The summary setting each response echoes is recorded too; all 240 responses of the block-1 replay probe (§9.2) echoed `"detailed"`. These are the registered settings: `run_fork_arms` (`check_fork_config`) and the CLI refuse any other `--effort`, `--mode` or `--service-tier`, before the paid-run lock, so a fork report can read condition (b) as met only at those settings.

**Scoring** (`score_fork_probe`):
- *scorable*: the turn-1 and turn-2 responses completed, neither visible reply contains a three-digit number, and every echoed `reasoning.context` (four per trial) equals the request. Unscorable trials are replaced, up to 40 attempts per arm per model (`run_fork_arms`; an arm stops once it has 20 scorable trials).
- *fork answer*: the first three-digit number in the turn-3 reply, if it is in the list; otherwise `None`. A refusal, a number outside the list and an incomplete turn-3 response (D13) all give `None`, and the trial stays scorable.
- *agree*: both fork answers are not `None` and are equal.

**Report** (`fork_report.json` next to `meta.json`, one per model): per arm, the attempts, scorable trials and why the others were not; agreements; for each fork the counts answered in the list, out of the list, with no number and incomplete; the distribution of answers and of list positions answered (1 = first shown), to expose value or position preferences; the position-coincidence rate; and echo mismatches. The `current_turn` arm's agreement rate is the chance baseline; 1/20 is the uniform reference. `condition_b` applies the registered thresholds (all_turns ≥ 15 of 20, current_turn ≤ 5 of 20, with 20 scorable per arm) and is `met: false` unless the run used 20 scorable trials and 40 attempts. Condition (a), D29's echo condition, also covers the block-1 echo check, so the verdict is the researcher's, from both reports.

```
PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses probe-replay \
    --design fork --approved-block "<block>" --planned-usd 1      # sol and luna
```

## 10. Researcher decisions
Each item is a `HarnessConfig` field or a fixed behaviour, listed in `config.RESEARCHER_DECISIONS`. Each needs the researcher's confirmation in PREREG.md.
- [RESEARCHER DECISION] `reasoning_effort` = `medium` (§16.5 proposes the documented default), sent explicitly.
- [RESEARCHER DECISION] `reasoning_mode` = `standard`, sent explicitly.
- [RESEARCHER DECISION] `reasoning_summary` = off in harness cells. Summaries would help failure labelling but add a field to every request; whether summary text in replayed items is rendered is undocumented.
- [RESEARCHER DECISION] `service_tier` = `flex` for every cell, never switched per episode.
- [RESEARCHER DECISION] `max_output_tokens` = 32,000 on every step request, sent explicitly (decided: PREREG D13, 2026-10-01). It bounds a runaway reply's cost; a step response that reaches it is `incomplete` and is scored as an invalid action (§7.5). Before D13 this was "none" (the field omitted).
- [RESEARCHER DECISION] `W_tokens` = the episode's generator W, so eviction matches the near/far design.
- [RESEARCHER DECISION] `window_counts_system_prompt` = the episode's generator setting (true since generator 0.2.0, PREREG D5). The episode's system prompt counts toward W; the notes sentence does not, so notes pairs evict at the same steps (§4).
- [RESEARCHER DECISION] `token_accounting`: visible text only (observations, replies, bridge), tiktoken `o200k_base`, no per-message overhead; reasoning items not counted.
- [RESEARCHER DECISION] `summary_trigger`: pre-send visible context > W, rather than ARC's post-hoc provider `total_tokens` ≥ 175k.
- [RESEARCHER DECISION] `summary_keep_recent_tokens` = 0: compact everything, as ARC. Near-cell S in Σ cells is then measured, not designed (§4.3).
- [RESEARCHER DECISION] `summary_system_prompt` = ARC's summary system prompt, which replaces the task instructions in the summary call, as ARC does. The summarizer then does not see "Some requests depend on records shown in earlier updates." Set it to `None` to keep the task instructions.
- [RESEARCHER DECISION] `summary_request_reasoning`: the summary call uses the arm's `reasoning.context` and includes the compacted turns' reasoning items, as ARC's Adapter state does. In r arms the summarizer may therefore draw on earlier reasoning.
- [RESEARCHER DECISION] `summary_max_output_tokens` = 32,000 (decided: PREREG D13, 2026-10-01; PREREG §6 sets `max_output_tokens: 32000` on luna and sol requests and makes no exception for summary calls). On OpenAI this cap includes reasoning tokens. Before D13 this was 8,192, as ARC.
- [RESEARCHER DECISION] `notes_placement`: the last line of the instructions.
- [RESEARCHER DECISION] `stop_on_context_mismatch` = true: stop and exclude the episode; abort the run after 2 such episodes.
- [RESEARCHER DECISION] `output_items_replay`: output items are sent back verbatim with null fields dropped. The pilot confirms that the API accepts this with `store: false`.

**Decided by the researcher on 2026-10-01 and implemented here** (decision-sheet items for the PREREG; D12 and the last two came with the researcher's acceptance of the technical recommendations):
- D8, need-phase tokens as H1's primary token reading (§7.1);
- D11 option A, sol on derived-far × T_d plus observed-far × T_d/3 (§7.3);
- D12, `compacted_between` logged in Σ cells (§7.2);
- pilot outcomes only under `results/raw/` (§7.4);
- the paid guard requires the researcher's approval line in `results/decisions.md` (§8);
- D13, `max_output_tokens` 32,000 on every step, summary and probe request, with an `incomplete` response at the need step scored 0 (PREREG §6, §13; §3, §7.5).

**Changed after the #13 review** (2026-10-01; its four open items):
- An approval is specific, so the researcher decides at every spending point. The line names the block, the experiments it may run and a dollar limit (`approved_block: <name> | experiments: ... | max_usd: ...`). It must be on `origin/main` as well as in `HEAD` and the working tree (§8). The guard moved to `common/approval.py`.
- D12: a summary fired during a lookup round-trip at the need step no longer sets `compacted_between`. It is marked `at_lookup_result` = 1 (§7.2).
- Pilot blinding stays as it is: per-run costs rows keep output tokens and leave `reasoning_tokens` empty (§7.4, §11).

**Changed after the second #13 review** (2026-10-01; defects in the new guard, §8):
- A run stops on the same spend measure as block spend and the phase caps, the larger of list and billed. It used to stop on billed alone, so on Flex one run could log twice its planned spend against `max_usd`.
- A line in a fenced code block or an HTML comment no longer counts.
- Any `costs.csv` row with a cost that is not empty or a finite, non-negative number, or with an experiment that has no phase, refuses. Before, a `nan` or negative cost in any row of the run's phase (not only the block's own rows) switched off or loosened the phase-cap check, and a row with no phase counted toward no cap.
- `origin` must be a configured remote, and git reads with replace refs off.

**Changed on 2026-10-01 after #13: spend basis and a frozen PREREG** (§8; for the researcher's review; it settles the open item "How the guard measures spend" of PLAN §17.4, amendment A2, if merged):
- Spend is the billed estimate, with list only where a row has no billed estimate. It was the larger of list and billed, which on Flex is the list cost. Block `max_usd`, the phase caps, a run's stop at `--planned-usd` and the probe split all moved together, since they share `spend_usd`. On Flex a block or phase now holds about twice the calls it did. The run still stops on the same measure the guard counts, so the fix from the second review holds.
- A costs.csv row with both costs empty no longer counts as $0. It refuses, like any other unreadable row.
- `PREREG.md` in `HEAD` must be identical to `PREREG.md` on `origin/main` (check 7). Before, a PREREG committed on any branch unlocked paid calls.

**Changed on 2026-10-01: the paid-run lock and a frozen PREREG for PersistGym runs** (§8; PREREG draft v0.3 §0.3, line 14, whose recommendation "add both before block 1" the researcher accepted on 2026-10-01):
- The paid commands take the paid-run lock the ARC launcher takes (`common/paidlock.py`), before the spend checks, and hold it for the whole command. Before, one paid run at a time was an operator rule for PersistGym runs.
- A paid run refuses unless this checkout's costs.csv holds the last paid run's row, and the lock stays held, with the reason, when a run's spend is not in costs.csv.
- The merged `PREREG.md` must be frozen. Before, check 7 accepted any PREREG that was the same blob in `HEAD` and on `origin/main`, a merged draft included.
- These checks and the ARC launcher's are one function, `common.approval.require_paid_run`, and the freeze rule moved from `arc/draw_games.py` to `common/prereg.py`.

**Changed on 2026-10-02: per-stream locks and spend reservations** (§8; PREREG §0.3 line 15 and §12, as changed by the researcher on 2026-10-01: "Until the per-stream locks land, one paid run at a time overall"; this is that code, a $0 change before block 3):
- The paid commands take the PersistGym stream's lock, `persistgym-paid-run-persistgym.lock`; the ARC launcher takes `persistgym-paid-run-arc.lock`. One run of each stream may go at once. While the old single lock exists, neither starts.
- A run's experiment must belong to the stream of the lock it holds (`common.paidlock.EXPERIMENT_STREAM`): `--experiment arc_path` under the PersistGym lock refuses.
- Each stream has its own last-run record, and a run of either stream needs both rows (and the old record's) in its ledger.
- A run reserves its planned spend until its costs row is written, and a run of the other stream counts that reservation against the block and phase they share. The check and the reservation happen under one operating-system lock, so two runs cannot both pass on the same room.
- `common.costs.append_row` and `read_rows` hold an operating-system lock on the ledger, so two processes can append at once without interleaving rows. The hold record is appended and read the same way.
- The hold stays global: a hold placed by either stream stops paid runs of both, and a hold placed while a run's checks are under way refuses that run too. So does an ARC lock kept by a run whose hold could not be recorded (marked `hold_not_recorded`): it stops PersistGym runs too, as the hold would.

**Changed on 2026-10-02: parallel episodes** (§7.6; PREREG §4.6 and §0.3 line 15, as changed by the researcher on 2026-10-01: "a run may play up to 16 episodes in parallel"; the second $0 change due before block 3):
- `run --parallel N`, 1 to 16, default 1. Episodes start in the run's order and are written in it, so `episodes.jsonl`, the transcript and `summary.json` are those of sequential play; the default is the sequential loop as before.
- A paid run reserves an estimate for each episode in flight against its planned spend and does not start an episode that does not fit (`SPEND_RESERVATION`). Before this, a run's only stop was the transport's, before each call.
- A paid run's calls pass a per-call gate (`CallGate`): calls overlap only while the most they can all cost fits in the planned spend, so a parallel run ends at most one call above it, as a sequential run can (added in review: without it, a fake-model run with 16 episodes in flight, all far dearer than their reservations, ended several calls over, about 12 in one trial).
- The stop rules stop the episodes in flight (`RUN_STOPPED`) after the call each has in flight.
- The transport's `send` is safe across threads, with a client per thread. `finalize` with calls still in flight (after a second Ctrl+C) writes the row of the calls recorded and keeps the lock and the reservation.
- `FakeModel(ids="payload")` answers each payload the same whatever the order of the calls, and `runner.CLOCK` times calls, so the tests can compare parallel and sequential outputs byte for byte.
- Pilot blinding (follow-up, PREREG §11): a pilot's `meta.json` commits only the allowlisted part of `parallel` (`blinding.PARALLEL_FIELDS`), without the per-episode spend estimate, the gate's waits or the peaks in flight; the whole block goes to `parallel.json` in the run's raw folder (§7.4). Before, a pilot played in parallel committed `spend_reservation.last_estimate_usd`, twice its largest episode's spend. No pilot committed so far was played in parallel, so no committed file had it. Other experiments' `meta.json` is unchanged.
- Pilot blinding (found in that follow-up's review, PREREG §11): for a pilot, the paid transport no longer logs a warning per incomplete response, or any call's status (§7.5). The warning went to stderr while the pilot ran, and the warnings, less the routine ones `summary.json` counts, counted the incomplete responses at the need step, which score 0 (D13). Pilots run before this change printed the warning whenever a response came back incomplete. Other experiments still log it.

**Technical choices made here** (not D-items; open to the researcher's review):
- Summary calls fired while the need step is pending count in the need phase, and are also reported apart (§7.1).
- The pooled pilot report shows reasoning tokens only for pools of at least 2 harness cells (§7.4).
- An approval line is compared as text across the three copies: changing its `max_usd` or experiments revokes it until the new line is on all three (§8).
- Spend is measured in one place, `common.costs.spend_usd` (re-exported as `common.approval.spend_usd`): block spend, the phase caps, a run's stop and the probe split all call it (§8).
- D13 as implemented (§7.5):
  - an `incomplete` step response is invalid at **every** step, not only at the need step. PREREG §6 names the need step; at a routine step it is scored wrong in `routine_accuracy` and the episode goes on, as PREREG §2.5 treats an invalid lookup there;
  - any `incomplete` status counts, whatever `incomplete_details.reason` says (the cap, or for example a content filter), and the reason is logged;
  - the incomplete turn stays in the history as returned (reasoning item, partial message if any), rather than being dropped or stripped;
  - an incomplete summary is retried as before (§4.3), never scored. Summary requests carry 32,000 too: the first version of this change kept ARC's 8,192 there, but PREREG §6 sets 32,000 on every luna and sol request, and §5 only freezes the summary cap with the snapshot tests, which now assert 32,000;
  - committed run summaries count incomplete responses at routine steps only (`n_incomplete_routine`), since one at the need step is an outcome;
  - in the replay probe an incomplete turn-3 response is a miss, and an incomplete turn 1 or 2 makes the trial unscorable (§9.2).

## 11. Known limitations and what this does not show
- **No payload has been sent to the API.** The tests show that the payloads are what the design says. They do not show that the API accepts them, for example:
  - replayed message items with ids under `store: false`;
  - stripped summaries in the replay probe;
  - `reasoning.mode` on luna;
  - a turn whose response stopped at `max_output_tokens` while reasoning, replayed as a reasoning item with no message after it (§7.5). A pilot reaches this only if a response hits the 32,000 cap. If the API rejects it, the next call fails with `API_ERROR`, so the episode is lost rather than scored, and the run aborts after 2 such episodes.

  The first paid pilot checks this. A 400 error is not billed.
- **The echo check shows the reported mode, not use.** That the API reports `all_turns` does not show that the model uses earlier reasoning. The replay-use probe tests that, and its scoring depends on reasoning summaries naming the picked number. If they rarely do, most trials are unscorable and the probe needs a redesign. In block 1 they almost never did, and §9.3 is that redesign.
- **The fork probe shows consistency, not recall of a known pick.** Agreement under `all_turns` well above the `current_turn` baseline shows that the forks share something from the turn-1 reasoning. It does not show what the model "picked", that the model reads every replayed item, or that replay carries larger or older state in the harness cells.
- **The r arms see more than W.** Under `all_turns`, rendered reasoning adds tokens that W does not count. The r and 0 arms then share eviction points, but the r arms' real contexts are larger.
- **Tokens are tiktoken's.** Provider counts differ by per-message overhead and rendered reasoning. Both are logged.
- **The fake model's usage numbers are not realistic.** Fake runs check structure, not cost.
- **Σ cells depend on what the model writes.** Their S is measured, and `carried_in_text` is the intended accounting (generator DESIGN.md §8, §12).
- **Pilot blinding is partial, and was kept that way after the #13 review.** CLAUDE.md asks for one costs.csv row per run. Each pilot run's row keeps its input and output tokens, calls and cost, and leaves `reasoning_tokens` empty. The run's `meta.json` does the same (§7.4). Output tokens are mostly reasoning tokens, so these rows approximate one arm's withheld reasoning tokens and lookups. Running `pilot-report` before and after a run also gives that run's numbers by difference. Fully closing this would mean pooling the pilot arms into one ledger row, which departs from one row per run. The rule (PREREG §11) is that nobody computes per-arm outcomes from pilot data. The code makes them hard to see, not impossible.
- **The guard trusts `origin/main`.** It checks that the approval line and `PREREG.md` were merged. It cannot check who merged them, so its strength is the branch protection and review on `main`. A paid command needs network access to GitHub at launch, because a failed fetch refuses.
- **The guard catches mistakes, not a hostile operator.** Anyone who can edit this code, point `origin` at another repository or edit `costs.csv` can get past it. A merged line that the reviewer did not read as an approval still counts: a gate entry should show a proposed line only in a code block, which the guard ignores.
- **The guard checks once, at launch.** A run continues if its approval is revoked while it runs. Two paid commands of one stream cannot both pass the checks, since each takes its stream's paid-run lock first, and a run of each stream cannot both use the same room, since each counts the other's reservation under one operating-system lock (§8). The locks catch mistakes: deleting a lock or reservation file while a run is going, starting a run from a script that takes the lock itself, or launching from a checkout older than the per-stream locks (which knows only the old single lock) gets past them.
- **Block spend is the logged estimate.** It sums the billed estimates of the costs.csv rows tagged with the block, so it is only as good as the price table in `pricing.py` and the served tier the response reports. A response reported as Flex but billed at the standard rate would count at half its real cost. It does not see spend the provider billed that was never logged. That includes a timed-out attempt the provider still processed, and a process killed before `finalize` wrote its row (such a process leaves the paid-run lock behind, so the next paid run refuses until the operator has checked costs.csv and deleted the lock). The provider-side spend limits (decisions.md, 2026-10-01), which the researcher sets in real billed dollars, remain the backstop against under-estimation. Only launchers that tag their rows `approved_block=<name>;` are counted, so the ARC launcher must use `common.approval.spend_tag` too.
- **Need-phase tokens are provider counts.** They include rendered reasoning in r arms and per-message overhead, unlike W's tiktoken counts (§4).
- **Parallel play is tested with the fake model only** (§7.6). The tests show that it sends the same payloads and writes the same files as sequential play when the responses are the same. They do not show:
  - that the provider answers 16 concurrent Flex requests as it answers one at a time. More of them may come back 429 ("resource unavailable"); each call retries with backoff on its own, and an episode whose call still fails ends `API_ERROR`, which counts toward the abort after 2;
  - that latency is unchanged. `call_latency_s`, the summary's latency and the costs row's `latency_s` are wall-clock seconds per call, which concurrent load can change, so latency from a parallel run is not comparable with a sequential one (the costs row says `parallel=N`);
  - that cache hits are unchanged. Episodes of one template share their early payloads, and played together their calls may hit or miss the provider's prompt cache differently than one after another, which changes `cached_input_tokens` and the billed estimate, not the payloads.
- **A spend estimate is an estimate.** Twice the largest finished episode can still be short, for example when reasoning tokens jump. The transport's stop then ends the run, with the episodes in flight cut short (`RUN_STOPPED`). The per-call gate keeps the spend within one call of the planned spend, as sequentially (§7.6), on its assumption that a request has no more input tokens than its JSON body has bytes. That is checked for text, not for replayed reasoning items.
