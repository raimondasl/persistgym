"""Runner skeleton: drive persistgym episodes through a harness cell and a transport.

A transport is any object with `paid: bool` and `send(payload) -> response dict`:
* `harnesses.fake.FakeModel` for tests and $0 dry runs;
* `harnesses.openai_transport.OpenAIResponsesTransport` and
  `harnesses.anthropic_transport.AnthropicMessagesTransport` for paid runs (guarded;
  `harnesses.paid_transport.PaidTransport`). A paid one also has `git`, `approval`,
  `planned_usd`, `spent_usd`, `ledger`, `finalize`, `keep_lock_if_unaccounted` and
  `paid_lock`, which `run_batch`, `harnesses.parallel` and the CLI read.
The payloads and responses are those of the model's wire (`harnesses.wire.wire_for`):
OpenAI's Responses API, or Anthropic's Messages API for `claude-*` models.

Per request the runner logs the payload, the response, the echoed `reasoning.context` and the
returned model string to the raw transcript (results/raw/, gitignored). At the need step's
first presentation it records survival from the payload actually sent
(`persistgym.survival.survival_from_payload`, with the summary bridge excluded and
string-matched separately with `carried_in_text`).

An episode whose echoed `reasoning.context` differs from the request on any response is
excluded (CLAUDE.md); by default it stops at that response. So is an episode whose echoed
`reasoning.effort` differs (PREREG §17.2, amendment R2), in the same way: exit reason
`REASONING_EFFORT_MISMATCH`, and both kinds count toward the run's abort after
`abort_after_mismatched_episodes` excluded episodes. A setting the provider does not echo
(the Messages API echoes neither) is None in the echo record: never a mismatch, never an
exclusion; the Messages wire checks every request before it is sent instead
(`harnesses.wire.MessagesWire.check_payload`).

Per episode it also logs (harnesses/DESIGN.md §7):
* `need_phase` (D8): provider-reported tokens summed over every call made while the need step
  is pending, from its first call through the call that returns the scored action, lookup
  round-trips included;
* `compacted_between` (D12, summary cells): 1 iff a compaction fired after the first evidence
  step r_first and before the agent first saw the need-step observation (a compaction
  applied to the payload of the need step's first call counts; one fired during a lookup
  round-trip at the need step does not, and is marked `at_lookup_result` = 1);
* the wall-clock seconds of every call (`call_latency_s`);
* every step response with status `incomplete` (`incomplete`, D13; e.g. one that hit
  `max_output_tokens`). Its step is scored as an invalid action (PREREG §6, §13: at the need
  step a content failure that scores 0) and the episode goes on.

Pilot-blinded experiments (`harnesses.blinding`, PREREG §11) keep `episodes.jsonl` under the
gitignored results/raw/ only, and commit an allowlisted part of meta.json's `parallel` block,
with the whole block under results/raw/.

`run_batch(..., parallel=N)` plays up to N <= 16 episodes at once (PREREG §4.6; §0.3 line 15;
`harnesses.parallel`): the same payloads, cell assignment, seeds and per-episode outputs,
written in the same order, with spend reserved for the episodes in flight. N = 1, the
default, is the sequential loop.

`run_batch` reads the git state once, at its start (a paid transport's, read when it was
built), and meta.json records that value, so no process is started after a paid run's calls
(common/runmeta.py). With a paid transport it also writes the run's plan,
results/raw/<experiment>/<run_id>/run_plan.json (`RUN_PLAN`), before the first call:
everything `harnesses account-run` needs to rebuild the run's accounting from its raw files
if its costs.csv row cannot be written, and no outcome.
"""

from __future__ import annotations

import gzip
import json
import shutil
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

import anthropic
import openai

from common import runmeta
from harnesses import blinding
from harnesses.cells import CellSpec
from harnesses.config import HarnessConfig
from harnesses.items import item_text
from harnesses.paid_transport import BudgetExceeded
from harnesses.parallel import RUN_STOPPED, ParallelPlay, RunStopped, check_parallel
from harnesses.pricing import add_counts, cost_usd
from harnesses.session import EmptySummaryError, HarnessSession
from harnesses.wire import wire_for
from persistgym.config import GENERATOR_VERSION, SCHEMA_VERSION
from persistgym.env import EpisodeEnv
from persistgym.episode import Episode
from persistgym.survival import carried_in_text, survival_from_payload

RESULTS = runmeta.REPO_ROOT / "results"
RAW = RESULTS / "raw"
INFLIGHT_DIR = "inflight"
"""Under results/raw/<experiment>/<run_id>/: the transcript of each episode playing in
parallel, until it is appended to the run's transcript in the run's order."""
RESERVATIONS_LOG = "spend_reservations.jsonl"
"""Under results/raw/<experiment>/<run_id>/: a parallel paid run's reservation at each
episode start (`harnesses.parallel.SpendPlan.log`)."""
PARALLEL_INFO = "parallel.json"
"""Under results/raw/<experiment>/<run_id>/: a pilot-blinded run's whole `parallel` block,
sequential runs included; its meta.json holds the allowlisted part
(`blinding.blinded_parallel`, PREREG §11) and names this file in `blinding.parallel_path`,
or null if it could not be written."""
RUN_PLAN = "run_plan.json"
"""Under results/raw/<experiment>/<run_id>/: a paid run's plan (`run_plan`), written before its
first call."""
RUN_PLAN_VERSION = 1
CLOCK = time.monotonic
"""Times each call (`call_latency_s`). Tests fix it to compare outputs byte for byte."""
ABORT_AFTER_API_ERRORS = 2
"""`run_batch`'s default: abort the run after this many episodes ended API_ERROR."""


class Transport(Protocol):
    paid: bool

    def send(self, payload: dict) -> dict: ...


ECHO_MISMATCH_EXITS = {"context": "REASONING_CONTEXT_MISMATCH",
                       "effort": "REASONING_EFFORT_MISMATCH"}
"""An episode's exit reason when it stops at a response whose echoed `reasoning.<kind>`
differs from the request (CLAUDE.md; PREREG §13, §17.2)."""
ECHO_ABORTS = ("ABORTED_CONTEXT_MISMATCH", "ABORTED_EFFORT_MISMATCH", "ABORTED_ECHO_MISMATCH")
"""A run's exit reason after `abort_after_mismatched_episodes` excluded episodes: all for a
context mismatch, all for an effort mismatch, or both kinds (`_stop_reason`)."""


API_ERRORS = (openai.OpenAIError, anthropic.AnthropicError)
"""Errors a transport raises after its retries, or for a rejected payload: the episode ends
`API_ERROR`."""


def check_echo(payload: dict, response: dict) -> dict:
    """Requested vs echoed reasoning settings, the returned model and service tier, as the
    payload's wire reads them (`harnesses.wire`): on the Messages API, which echoes neither
    effort nor a reasoning context, `context_ok` and `effort_ok` are None (not echoed)."""
    return wire_for(payload.get("model")).echo(payload, response)


class JsonlRecorder:
    """Raw transcript writer (one JSON object per request/response pair)."""

    def __init__(self, path: Path, *, flush_each: bool = False):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.flush_each = flush_each  # a parallel episode's file: on disk after every call
        # kept open across requests and closed by close(), so no context manager here
        if path.suffix == ".gz":
            self._f = gzip.open(path, "at", encoding="utf-8")  # noqa: SIM115
        else:
            self._f = path.open("a", encoding="utf-8")

    def __call__(self, event: dict) -> None:
        self._f.write(json.dumps(event, ensure_ascii=False) + "\n")
        if self.flush_each:
            self._f.flush()

    def append_file(self, path: Path) -> None:
        """Append, unchanged, the lines another recorder wrote to `path` (the transcript of
        one episode played in parallel)."""
        with path.open("r", encoding="utf-8") as src:
            shutil.copyfileobj(src, self._f)

    def close(self) -> None:
        self._f.close()


@dataclass
class EpisodeRun:
    episode_id: str
    template_id: str
    task_cell: str
    variant: str
    harness_cell: str
    model: str = ""  # requested
    exit_reason: str = "DONE"
    error: str | None = None
    excluded: bool = False
    exclusion_reason: str | None = None
    # the echoes that differed from the request ("context", "effort"), in the order seen;
    # each excludes the episode (ECHO_MISMATCH_EXITS)
    echo_mismatches: list[str] = field(default_factory=list)
    need_correct: bool = False
    need_label: str | None = None
    # the need step's outcome (persistgym.env: correct, wrong, unparsed, invalid_lookup,
    # incomplete); None if it was never scored
    need_outcome: str | None = None
    routine_accuracy: float | None = None
    n_lookups: int = 0
    n_lookups_unavailable: int = 0  # over-cap lookups answered "lookup unavailable" (D3)
    n_turns: int = 0
    n_requests: int = 0
    n_summary_requests: int = 0
    n_summary_failures: int = 0
    n_unparsed_routine: int = 0  # unparsed replies at routine (non-need) steps
    # step responses with status `incomplete` (D13), each scored as an invalid action; see
    # _incomplete_record. Summary responses are not here: they are retried (n_summary_failures)
    incomplete: list[dict] = field(default_factory=list)
    n_incomplete_routine: int = 0  # those at routine (non-need) steps
    # each with at_step and at_lookup_result (D12)
    compactions: list[dict] = field(default_factory=list)
    compacted_between: int | None = None  # D12; summary cells only, see run_episode
    need_payload: dict | None = None  # survival_from_payload at the need step
    need_bridge_carried: dict | None = None  # carried_in_text on the bridge, summary cells
    need_info: dict | None = None  # loss-policy bookkeeping of the need request
    designed: dict | None = None  # episode.design survival for reference
    need_phase: dict | None = None  # D8 need-phase tokens, see _need_phase_add
    echo: dict = field(default_factory=dict)
    usage: dict = field(default_factory=dict)
    call_latency_s: list[float] = field(default_factory=list)  # wall clock per call
    cost_usd_list: float | None = 0.0
    cost_usd_billed_est: float | None = 0.0
    # the episode's generator config hash (PREREG §17.3: luna and sol play different configs;
    # the pooled pilot report keeps them apart, `blinding.pool_key`). None in records written
    # before it was logged
    generator_config_hash: str | None = None


def _add_usage(run: EpisodeRun, response: dict) -> None:
    """Add one response's usage (read by the requested model's wire, in one meaning on both
    APIs: `harnesses.pricing`) and cost to the episode's (or prompt's) totals. A count the
    provider did not report makes its total None (`pricing.add_counts`)."""
    wire = wire_for(run.model)
    add_counts(run.usage, wire.usage(response))
    try:
        listed, billed = cost_usd(response.get("model") or "", response.get("usage"),
                                  wire.served_tier(response))
    except KeyError:
        run.cost_usd_list = run.cost_usd_billed_est = None
        return
    if run.cost_usd_list is not None:
        run.cost_usd_list += listed
        run.cost_usd_billed_est += billed


def _need_phase_add(run: EpisodeRun, req, info: dict, response: dict) -> None:
    """D8: add one call made while the need step is pending. `tokens` is the D8 quantity:
    provider-reported input tokens (cached included: OpenAI's `input_tokens` counts cached
    tokens; on the Messages API cache reads and writes are added back,
    `pricing.messages_usage_numbers`) plus output tokens (reasoning included: `output_tokens`
    counts reasoning tokens). Summary calls fired while the need step is pending are calls at
    the need step and are included; they are also totalled apart (`summary_tokens`) for the
    reading that leaves them out. H1's cells (F-0, W-0) never summarize. Reasoning tokens a
    provider does not report make `reasoning_tokens` None."""
    u = wire_for(run.model).usage(response)
    if run.need_phase is None:
        run.need_phase = {"n_calls": 0, "n_step_calls": 0, "n_lookup_result_calls": 0,
                          "n_summary_calls": 0, "input_tokens": 0, "cached_input_tokens": 0,
                          "output_tokens": 0, "reasoning_tokens": 0, "tokens": 0,
                          "summary_tokens": 0, "first_step_call": None, "complete": False}
    n = run.need_phase
    n["n_calls"] += 1
    add_counts(n, {k: u[k] for k in ("input_tokens", "cached_input_tokens", "output_tokens",
                                     "reasoning_tokens")})
    n["tokens"] += u["input_tokens"] + u["output_tokens"]
    if req.kind == "summary":
        n["n_summary_calls"] += 1
        n["summary_tokens"] += u["input_tokens"] + u["output_tokens"]
    else:
        n["n_step_calls"] += 1
        n["n_lookup_result_calls"] += bool(info["is_lookup_result"])
        if n["first_step_call"] is None:  # H2's usage[n]: the need step's first step call
            n["first_step_call"] = u


def _incomplete_record(info: dict, need: int, payload: dict, response: dict,
                       reply: str) -> dict:
    """One step response with status `incomplete` (D13): where it happened, why, and whether
    it used the whole output cap. Its step is scored as an invalid action. On the Messages
    wire `reason` is `max_output_tokens`, `refusal:<category>` or
    `unexpected_stop_reason:<stop_reason>` (`MessagesWire.status`), and `max_output_tokens`
    holds the request's `max_tokens`."""
    wire = wire_for(payload.get("model"))
    return {"turn": info["turn"], "pending_step": info["pending_step"],
            "at_need": int(info["pending_step"] == need),
            "is_lookup_result": int(info["is_lookup_result"]),
            "reason": wire.status(response)[1],
            "max_output_tokens": wire.cap(payload),
            "output_tokens": wire.usage(response)["output_tokens"],
            "reply_chars": len(reply or "")}


def run_episode(episode: Episode, cell: CellSpec, cfg: HarnessConfig, transport: Transport,
                recorder=None) -> EpisodeRun:
    env = EpisodeEnv(episode)
    session = HarnessSession.for_episode(cell, episode, cfg)
    wire = session.wire
    run = EpisodeRun(episode.episode_id, episode.template_id, episode.cell.id, episode.variant,
                     cell.cell_id, model=cfg.model,
                     generator_config_hash=episode.config_hash)
    run.designed = {k: episode.design.get(k) for k in (
        "S_window_obs_only", "S_window_assumed_replies", "far_by_obs_tokens",
        "gap_steps_latest", "gap_steps_earliest")}
    run.designed["evidence_steps"] = episode.reveal_steps
    need = episode.need_step
    echoed: Counter = Counter()
    efforts: Counter = Counter()
    models: Counter = Counter()
    tiers: Counter = Counter()
    stop_on = {"context": cfg.stop_on_context_mismatch, "effort": cfg.stop_on_effort_mismatch}
    obs = env.observation
    done = False
    n_compactions_seen_at_need = 0  # compactions applied before the need step's first call
    try:
        while not done:
            if len(env.turns) > cfg.max_turns:
                run.exit_reason = "MAX_TURNS"
                break
            info = env.info
            session.observe(obs)
            failures = 0
            reply = None
            while True:
                req = session.next_request()
                first_need = (req.kind == "step" and run.need_payload is None
                              and info["pending_step"] == need
                              and not info["is_lookup_result"])
                if first_need:
                    bridge = req.info["bridge_index"]
                    run.need_payload = survival_from_payload(
                        episode, wire.messages(req.payload), system=wire.system(req.payload),
                        exclude_indices=[bridge] if bridge is not None else [])
                    run.need_info = dict(req.info)
                    # every compaction so far is applied to this payload (D12)
                    n_compactions_seen_at_need = len(session.compactions)
                    if bridge is not None:
                        run.need_bridge_carried = carried_in_text(
                            item_text(wire.messages(req.payload)[bridge]), episode)
                started = CLOCK()
                response = transport.send(req.payload)
                run.call_latency_s.append(round(CLOCK() - started, 3))
                run.n_requests += 1
                run.n_summary_requests += req.kind == "summary"
                echo = check_echo(req.payload, response)
                echoed[str(echo["context_echoed"])] += 1
                efforts[str(echo["effort_echoed"])] += 1
                models[str(echo["model_returned"])] += 1
                tiers[str(echo["service_tier_returned"])] += 1
                _add_usage(run, response)
                if info["pending_step"] == need:
                    _need_phase_add(run, req, info, response)
                if recorder is not None:
                    recorder({"episode_id": episode.episode_id, "harness_cell": cell.cell_id,
                              "request_index": run.n_requests - 1, "kind": req.kind,
                              "turn": req.turn, "pending_step": info["pending_step"],
                              "is_lookup_result": info["is_lookup_result"],
                              "trace": req.trace, "info": req.info, "echo": echo,
                              "payload": req.payload, "response": response})
                # CLAUDE.md (context) and PREREG §17.2 (effort): an echo that differs from the
                # request excludes the episode, and by default stops it there. Both kinds are
                # recorded before it stops, so a response that differs in both counts as both.
                # A setting the provider does not echo (None: the Messages API) never does.
                mismatched = [k for k in ECHO_MISMATCH_EXITS if echo[f"{k}_ok"] is False]
                if mismatched:
                    run.excluded = True
                    run.exclusion_reason = "; ".join(
                        f"reasoning.{k} requested {echo[f'{k}_requested']!r}, echoed "
                        f"{echo[f'{k}_echoed']!r}" for k in mismatched)
                    run.echo_mismatches += [k for k in mismatched
                                            if k not in run.echo_mismatches]
                    stop = next((k for k in mismatched if stop_on[k]), None)
                    if stop is not None:
                        run.exit_reason = ECHO_MISMATCH_EXITS[stop]
                        return run
                try:
                    reply = session.record(req, response)
                except EmptySummaryError as e:
                    failures += 1
                    run.n_summary_failures += 1
                    if failures >= cfg.summary_max_attempts:
                        run.exit_reason = "AGENT_ERROR"
                        run.error = f"summary failed {failures} times: {e}"
                        return run
                    continue
                if req.kind == "step":
                    break
                failures = 0  # a compaction succeeded; the next one gets its own attempts
            # PREREG §6, §13 (D13): a step response that stopped short (status `incomplete`,
            # e.g. at max_output_tokens; on the Messages API also a refusal) is a content
            # failure. Its step is scored as an invalid action whatever its partial text
            # says, and the episode goes on. The session keeps the turn's output items as
            # returned (on the Messages wire, its visible text or the empty-reply placeholder).
            invalid = None
            if wire.status(response)[0] == "incomplete":
                invalid = "incomplete"
                run.incomplete.append(_incomplete_record(info, need, req.payload, response,
                                                         reply))
            obs, done = env.step(reply, invalid=invalid)
    except BudgetExceeded as e:
        run.exit_reason, run.error = "COST_CAP", str(e)
    except API_ERRORS as e:  # API errors after retries, rejected payloads
        run.exit_reason, run.error = "API_ERROR", f"{type(e).__name__}: {e}"
    except RunStopped as e:  # parallel play: the run stopped while this episode was in flight
        run.exit_reason, run.error = RUN_STOPPED, str(e)
    finally:
        res = env.result()
        run.need_correct = res.need_correct
        run.need_label = res.need_label
        run.routine_accuracy = (res.routine_accuracy if res.routine_total else None)
        run.n_lookups = res.n_lookups
        run.n_lookups_unavailable = res.n_lookups_unavailable
        run.n_turns = res.n_turns
        run.need_outcome = res.step_outcomes.get(need)
        run.n_unparsed_routine = sum(o == "unparsed" for s, o in res.step_outcomes.items()
                                     if s != need)
        run.n_incomplete_routine = sum(not r["at_need"] for r in run.incomplete)
        if run.need_phase is not None:
            run.need_phase["complete"] = need in res.step_outcomes
        # Session turn t is environment turn t (one observation each), so env.turns maps a
        # compaction's turn to the step that was pending when it fired, and to whether that
        # turn's observation was a lookup result.
        run.compactions = [{**{k: v for k, v in c.items() if k != "summary_text"},
                            "at_step": env.turns[c["at_turn"]].pending_step,
                            "at_lookup_result": int(env.turns[c["at_turn"]].is_lookup_result)}
                           for c in session.compactions]
        if (cell.history == "summary" and episode.reveal_steps
                and run.need_payload is not None):
            # D12: did a summary fire after the first evidence step and before the agent
            # first saw the need-step observation? The compactions applied to the payload of
            # the need step's first call count; later ones (lookup round-trips at the need
            # step, at_lookup_result = 1) do not. Successful compactions only (a failed
            # summary attempt changes nothing). None when there is no evidence (withheld
            # variant) or the need step was never presented.
            r_first = min(episode.reveal_steps)
            run.compacted_between = int(any(
                c["at_step"] > r_first
                for c in run.compactions[:n_compactions_seen_at_need]))
        run.echo = episode_echo(wire, cell, cfg, echoed, efforts, models, tiers)
    return run


def episode_echo(wire, cell: CellSpec, cfg: HarnessConfig, echoed: Counter, efforts: Counter,
                 models: Counter, tiers: Counter) -> dict:
    """An episode's (or prompt's) `echo` record: the requested reasoning.context and effort
    and the counts of what the responses echoed, returned and were served on. On a wire that
    echoes no reasoning settings (the Messages API) the context is not requested and neither
    is echoed: `context_requested`, `context_echoed` and `effort_echoed` are None, and
    `effort_requested` is the effort sent (`output_config.effort`)."""
    if not wire.echoes_reasoning:
        return {"context_requested": None, "context_echoed": None,
                "effort_requested": cfg.reasoning_effort, "effort_echoed": None,
                "models_returned": dict(models), "service_tiers_returned": dict(tiers)}
    return {"context_requested": cell.reasoning_context, "context_echoed": dict(echoed),
            "effort_requested": cfg.reasoning_effort, "effort_echoed": dict(efforts),
            "models_returned": dict(models), "service_tiers_returned": dict(tiers)}


def _stop_reason(runs: list[EpisodeRun], last: EpisodeRun, cfg: HarnessConfig,
                 abort_after_api_errors: int) -> str | None:
    """The run's stop rule, checked after each episode finishes (`runs`: those finished so
    far, `last` the one that just did): the run's exit reason if it must stop, else None.
    COST_CAP when the transport stopped `last` at the planned spend; an abort after
    `cfg.abort_after_mismatched_episodes` excluded (echo-mismatched) episodes (CLAUDE.md;
    PREREG §17.2 counts effort mismatches with context mismatches), named by the kinds of
    mismatch among them (`ECHO_ABORTS`); or `abort_after_api_errors` episodes that ended
    API_ERROR."""
    if last.exit_reason == "COST_CAP":
        return "COST_CAP"
    excluded = [x for x in runs if x.excluded]
    if len(excluded) >= cfg.abort_after_mismatched_episodes:
        kinds = {k for x in excluded for k in x.echo_mismatches}
        if kinds == {"effort"}:
            return "ABORTED_EFFORT_MISMATCH"
        return "ABORTED_CONTEXT_MISMATCH" if kinds <= {"context"} else "ABORTED_ECHO_MISMATCH"
    if sum(x.exit_reason == "API_ERROR" for x in runs) >= abort_after_api_errors:
        return "ABORTED_API_ERRORS"
    return None


def episode_record(run: EpisodeRun, repeat_index: int = 0) -> dict:
    """An episode's line in episodes.jsonl: its `EpisodeRun` fields and, at repeat_index 1
    (PREREG §2.9), `repeat_index` after them. A repeat replays its repeat-0 episode, with the
    same episode_id, so the record says which play it is. A record without the field is
    repeat 0: every record written before repeats existed, and every repeat-0 record since,
    byte for byte."""
    rec = asdict(run)
    if repeat_index:
        rec["repeat_index"] = repeat_index
    return rec


def run_plan(*, run_id: str, experiment: str, milestone: str, cell: CellSpec,
             cfg: HarnessConfig, episodes: list[Episode], run_matrix: dict | None,
             repeat_index: int, notes: str, abort_after_api_errors: int, parallel: int,
             git: dict, started: str, reservation_id: str | None,
             run_args: dict | None) -> dict:
    """A paid run's plan (`RUN_PLAN`): what `harnesses account-run` needs to rebuild the run's
    costs row, summary.json and meta.json from its raw files, written before the first call.
    `run_args` are the arguments of the `run` command (None when the runner is called
    otherwise); the rest is what `run_batch` was given, the git state read at the start, the
    start time, the spend reservation's id and the code's versions. It holds no outcome."""
    return {
        "plan_version": RUN_PLAN_VERSION,
        "run_id": run_id, "experiment": experiment, "milestone": milestone,
        "run_args": run_args,
        "harness_cell": cell.cell_id, "harness_config": cfg.to_dict(),
        "run_matrix": run_matrix, "episode_ids": [e.episode_id for e in episodes],
        "repeat_index": repeat_index, "notes": notes,
        "abort_after_api_errors": abort_after_api_errors, "parallel": parallel,
        "git": git, "started_utc": started, "reservation_id": reservation_id,
        "prereg_version": runmeta.prereg_version(), "sdk_versions": runmeta.sdk_versions(),
        "code_version": {"generator_version": GENERATOR_VERSION,
                         "episode_schema_version": SCHEMA_VERSION},
    }


def run_batch(episodes: list[Episode], cell: CellSpec, cfg: HarnessConfig,
              transport: Transport, *, experiment: str, run_id: str, milestone: str = "M0",
              results_root: Path = RESULTS, raw_root: Path = RAW, repeat_index: int = 0,
              notes: str = "", abort_after_api_errors: int = ABORT_AFTER_API_ERRORS,
              run_matrix: dict | None = None, parallel: int = 1,
              run_args: dict | None = None) -> dict[str, Any]:
    """Run episodes in order; write results/<experiment>/<run_id>/{meta.json,summary.json,
    episodes.jsonl} and the raw transcript under results/raw/. For a pilot-blinded
    experiment (`blinding.BLINDED_EXPERIMENTS`) episodes.jsonl goes to
    results/raw/<experiment>/<run_id>/ instead, meta.json leaves out reasoning tokens, and
    its `parallel` keeps the allowlisted fields only (`blinding.blinded_parallel`), with the
    whole block in results/raw/<experiment>/<run_id>/parallel.json (`PARALLEL_INFO`).
    Paid transports get their costs.csv row appended in `finally`, whatever happens.
    `run_matrix` (harnesses.matrix.RunMatrix.to_dict) is recorded in meta.json's config.
    `repeat_index` (PREREG §2.9) goes into the run plan and meta.json, and at 1 into each
    episode record too (`episode_record`); the episodes themselves are the caller's (a
    repeat-1 run plays `RunMatrix.repeat`'s).

    `parallel` (1 to 16, PREREG §4.6): episodes played at once (`harnesses.parallel`). With
    more than 1, episodes.jsonl and the transcript are still written in the order of
    `episodes`, the stop rule (`_stop_reason`) stops the episodes in flight too, and a paid
    transport's planned spend is reserved episode by episode and guarded call by call
    (`harnesses.parallel.CallGate`); meta.json's `parallel` says
    how it went (outside `config`, so the config hash is that of sequential play).

    The git state is read once, here at the start (a paid transport's `git`, read before its
    first call), and meta.json records it. With a paid transport, the run's plan
    (`run_plan`, with the `run` command's arguments `run_args`) is written to
    results/raw/<experiment>/<run_id>/run_plan.json before the first call; if it cannot be
    written the run raises before any call."""
    for what, name in (("experiment", experiment), ("run_id", run_id)):
        require_plain_name(what, name)
    if repeat_index not in (0, 1):
        raise ValueError(f"repeat_index is 0 or 1 (PREREG §2.9), got {repeat_index!r}")
    parallel = check_parallel(parallel)
    blinded = blinding.is_blinded(experiment)
    out_dir = results_root / experiment / run_id
    raw_dir = raw_root / experiment / run_id
    raw_path = raw_dir / "transcript.jsonl.gz"
    inflight_dir = raw_dir / INFLIGHT_DIR
    episodes_path = (raw_dir if blinded else out_dir) / "episodes.jsonl"
    if parallel > 1 and inflight_dir.exists() and any(inflight_dir.iterdir()):
        raise ValueError(f"{inflight_dir} holds episode transcripts left by an earlier "
                         "parallel run with this run id; move them before reusing the id")
    out_dir.mkdir(parents=True, exist_ok=True)
    episodes_path.parent.mkdir(parents=True, exist_ok=True)
    # Once, before any call (common/runmeta.py): a paid transport read it when it was built.
    git = getattr(transport, "git", None) or runmeta.git_state()
    started = runmeta.utc_now()
    if getattr(transport, "paid", False):
        approval = getattr(transport, "approval", None)
        plan = run_plan(run_id=run_id, experiment=experiment, milestone=milestone, cell=cell,
                        cfg=cfg, episodes=episodes, run_matrix=run_matrix,
                        repeat_index=repeat_index, notes=notes,
                        abort_after_api_errors=abort_after_api_errors, parallel=parallel,
                        git=git, started=started,
                        reservation_id=getattr(approval, "reservation_id", None) or None,
                        run_args=run_args)
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / RUN_PLAN).write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8")
    recorder = JsonlRecorder(raw_path)
    runs: list[EpisodeRun] = []
    play: ParallelPlay | None = None
    exit_reason = "COMPLETED"
    try:
        with episodes_path.open("a", encoding="utf-8") as f:
            def write(r: EpisodeRun) -> None:
                f.write(json.dumps(episode_record(r, repeat_index), ensure_ascii=False) + "\n")
                f.flush()

            if parallel == 1:
                for ep in episodes:
                    r = run_episode(ep, cell, cfg, transport, recorder)
                    runs.append(r)
                    write(r)
                    reason = _stop_reason(runs, r, cfg, abort_after_api_errors)
                    if reason:
                        exit_reason = reason
                        break
            else:
                def spool(i: int) -> Path:
                    return inflight_dir / f"{i:06d}.jsonl"

                def play_one(i: int, ep: Episode, channel) -> EpisodeRun:
                    rec = JsonlRecorder(spool(i), flush_each=True)
                    try:
                        return run_episode(ep, cell, cfg, channel, rec)
                    finally:
                        rec.close()

                def emit(i: int, r: EpisodeRun | None) -> None:
                    if r is not None:
                        write(r)
                    if spool(i).exists():
                        recorder.append_file(spool(i))
                        spool(i).unlink()

                play = ParallelPlay(
                    episodes, parallel=parallel, transport=transport, model=cfg.model,
                    play_one=play_one, emit=emit,
                    stop_rule=lambda done, last: _stop_reason(done, last, cfg,
                                                              abort_after_api_errors))
                runs = play.runs  # filled in the run's order as episodes are written
                try:
                    play.run()
                finally:
                    try:
                        inflight_dir.rmdir()  # kept if an abandoned episode's file is there
                    except OSError:
                        pass
                exit_reason = play.exit_reason
    except BaseException as e:
        exit_reason = f"ERROR:{type(e).__name__}"
        raise
    finally:
        recorder.close()
        cost_row = None
        if hasattr(transport, "finalize"):
            cost_row = transport.finalize(run_id=run_id, milestone=milestone,
                                          cell_or_config=cell.ascii_id, notes=notes)
        if play is not None and play.plan is not None:
            _write_raw(raw_dir / RESERVATIONS_LOG,
                       "".join(json.dumps(x) + "\n" for x in play.plan.log))
        summary = blinding.run_summary([asdict(r) for r in runs], blinded=blinded)
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n",
                                              encoding="utf-8")
        parallel_info = (play.info() if play is not None
                         else {"max_episodes_in_flight": parallel})
        if play is not None and play.abandoned:
            parallel_info["abandoned_transcripts"] = _rel(inflight_dir)
        # PREREG §11: a blinded run's meta.json gets the allowlisted part of `parallel` and
        # the whole block goes to raw; if it cannot be written, meta.json names no raw copy.
        parallel_path = raw_dir / PARALLEL_INFO if blinded else None
        if parallel_path is not None and not _write_raw(
                parallel_path, json.dumps(parallel_info, indent=2) + "\n"):
            parallel_path = None
        meta = _write_meta(out_dir, raw_path, episodes, runs, cell, cfg, transport,
                           experiment=experiment, run_id=run_id, started=started,
                           exit_reason=exit_reason, repeat_index=repeat_index,
                           cost_row=cost_row, blinded=blinded, episodes_path=episodes_path,
                           run_matrix=run_matrix, parallel=parallel_info,
                           parallel_path=parallel_path, git=git)
    return meta


def _write_raw(path: Path, text: str) -> bool:
    """A raw (gitignored) file written once the run has ended: a parallel paid run's
    reservation log, or a blinded run's whole `parallel` block. A failure to write it is
    reported (the path, never the content), not raised: it must not stop the run's
    accounting. Returns whether it was written."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as e:
        print(f"warning: could not write {path}: {e}", file=sys.stderr)
        return False
    return True


def require_plain_name(what: str, name: str) -> None:
    """`name` must be one plain path component. A run id such as '../../x' would otherwise
    move a blinded run's episodes.jsonl out of the gitignored results/raw/ (PREREG §11)."""
    if (not name or name in (".", "..") or name != name.strip()
            or any(ch in name for ch in '/\\:\0')):
        raise ValueError(f"{what} must be a plain folder name (no path separators, ':' or "
                         f"'..'), got {name!r}")


def _rel(path: Path) -> str:
    try:
        return path.relative_to(runmeta.REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _write_meta(out_dir, raw_path, episodes, runs, cell, cfg, transport, *, experiment, run_id,
                started, exit_reason, repeat_index, cost_row, blinded=False,
                episodes_path=None, run_matrix=None, parallel=None,
                parallel_path=None, git=None, finished=None, recorded=None) -> dict:
    """Write meta.json. `git`: the git state read at the run's start (None: read now);
    `finished`: the finish time (None: now). `recorded` adds fields: `harnesses account-run`
    gives `recovered` and the run's own `prereg_version` and `sdk_versions`. A run on the
    Messages wire records no reasoning.context and no echo (None) and adds `wire_meta`'s
    fields."""
    wire = wire_for(cfg.model)
    echoed: Counter = Counter()
    efforts: Counter = Counter()
    models: Counter = Counter()
    usage: dict = {}
    for r in runs:
        echoed.update(r.echo.get("context_echoed") or {})
        efforts.update(r.echo.get("effort_echoed") or {})
        models.update(r.echo.get("models_returned", {}))
        add_counts(usage, r.usage)
    echo = meta_echo(wire, cell.reasoning_context, echoed, efforts)
    listed = [r.cost_usd_list for r in runs]
    billed = [r.cost_usd_billed_est for r in runs]
    gen_cfgs = {e.config_hash: e.config for e in episodes}
    config = {"harness_cell": cell.cell_id, "harness": cfg.to_dict(),
              "generator_config_hashes": sorted(gen_cfgs),
              "generator_config": next(iter(gen_cfgs.values())) if len(gen_cfgs) == 1 else None,
              "episode_ids": [e.episode_id for e in episodes]}
    if run_matrix is not None:
        config["run_matrix"] = run_matrix
    tokens = dict(usage)
    parallel = parallel or {"max_episodes_in_flight": 1}
    extra = wire_meta(wire, transport)
    if blinded:
        # PREREG §11: one run is one arm, so its reasoning-token total is a per-arm number,
        # and pilots report cost no finer than the run's total (blinding.blinded_parallel).
        tokens = blinding.blinded_tokens(tokens)
        parallel = blinding.blinded_parallel(parallel)
        extra["blinding"] = {"rule": blinding.WITHHELD_NOTE,
                             "episodes_path": _rel(episodes_path) if episodes_path else None,
                             "parallel_rule": blinding.PARALLEL_WITHHELD_NOTE,
                             "parallel_path": _rel(parallel_path) if parallel_path else None}
    path = runmeta.write_meta(
        out_dir, experiment=experiment, run_id=run_id, cell_or_config=cell.cell_id,
        config=config, model_requested=cfg.model, model_returned=sorted(models),
        reasoning_effort=cfg.reasoning_effort,
        reasoning_effort_echoed=echo["reasoning_effort_echoed"],
        reasoning_mode=cfg.reasoning_mode,
        reasoning_context_requested=echo["reasoning_context_requested"],
        reasoning_context_echoed=echo["reasoning_context_echoed"],
        service_tier_requested=cfg.service_tier,
        template_id=sorted({e.template_id for e in episodes}), repeat_index=repeat_index,
        seeds={"template_seeds": sorted({e.template_seed for e in episodes})},
        started_utc=started, finished_utc=finished or runmeta.utc_now(),
        exit_reason=exit_reason, tokens=tokens,
        cost_usd={"list": sum(listed) if None not in listed else None,
                  "billed_est": sum(billed) if None not in billed else None,
                  "costs_csv_row_appended": cost_row is not None},
        raw_transcript_path=_rel(raw_path), paid=bool(getattr(transport, "paid", False)),
        n_episodes_run=len(runs), n_excluded=sum(r.excluded for r in runs),
        parallel=parallel, git=git, **extra, **(recorded or {}))
    return json.loads(path.read_text(encoding="utf-8"))


MESSAGES_ECHO_NOTE = (
    "the Messages API echoes neither the effort nor a reasoning context: "
    "reasoning_context_requested, reasoning_context_echoed and reasoning_effort_echoed are "
    "null (not echoed, never a mismatch); instead every request passed the request-side check "
    "before it was sent (harnesses/wire.py MessagesWire.check_payload: adaptive thinking, the "
    "effort, max_tokens, no thinking block), PREREG §17.8 (amendment R8, pending)")


def meta_echo(wire, context_requested: str, echoed: Counter, efforts: Counter) -> dict:
    """meta.json's reasoning.context requested and echoed and effort echoed: the counts, or
    None on a wire that echoes no reasoning settings (the Messages API; `MESSAGES_ECHO_NOTE`)."""
    if wire.echoes_reasoning:
        return {"reasoning_context_requested": context_requested,
                "reasoning_context_echoed": dict(echoed),
                "reasoning_effort_echoed": dict(efforts)}
    return {"reasoning_context_requested": None, "reasoning_context_echoed": None,
            "reasoning_effort_echoed": None}


def wire_meta(wire, transport) -> dict:
    """The meta.json fields a run on the Messages wire adds (none on the Responses wire, so
    those runs' meta.json is as before): its `api`, the `echo_note`, and `prompt_size`, the
    largest prompt (input + cache reads + cache writes) of its calls and how many passed the
    price's 100,000-token threshold, from the paid transport's ledger (None without one: a
    fake run)."""
    if wire.echoes_reasoning:
        return {}
    ledger = getattr(transport, "ledger", None)
    return {"api": f"{wire.provider}.{wire.api}", "echo_note": MESSAGES_ECHO_NOTE,
            "prompt_size": ledger.prompt_size() if ledger is not None else None}
