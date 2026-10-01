"""Runner skeleton: drive persistgym episodes through a harness cell and a transport.

A transport is any object with `paid: bool` and `send(payload) -> response dict`:
* `harnesses.fake.FakeModel` for tests and $0 dry runs;
* `harnesses.openai_transport.OpenAIResponsesTransport` for paid runs (guarded).

Per request the runner logs the payload, the response, the echoed `reasoning.context` and the
returned model string to the raw transcript (results/raw/, gitignored). At the need step's
first presentation it records survival from the payload actually sent
(`persistgym.survival.survival_from_payload`, with the summary bridge excluded and
string-matched separately with `carried_in_text`).

An episode whose echoed `reasoning.context` differs from the request on any response is
excluded (CLAUDE.md); by default it stops at that response.

Per episode it also logs (harnesses/DESIGN.md §7):
* `need_phase` (D8): provider-reported tokens summed over every call made while the need step
  is pending, from its first call through the call that returns the scored action, lookup
  round-trips included;
* `compacted_between` (D12, summary cells): 1 iff a compaction fired after the first evidence
  step r_first and before the agent first saw the need-step observation (a compaction
  applied to the payload of the need step's first call counts; one fired during a lookup
  round-trip at the need step does not, and is marked `at_lookup_result` = 1);
* the wall-clock seconds of every call (`call_latency_s`).

Pilot-blinded experiments (`harnesses.blinding`, PREREG §11) keep `episodes.jsonl` under the
gitignored results/raw/ only.
"""

from __future__ import annotations

import gzip
import json
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

import openai

from common import runmeta
from harnesses import blinding
from harnesses.cells import CellSpec
from harnesses.config import HarnessConfig
from harnesses.items import item_text
from harnesses.openai_transport import BudgetExceeded
from harnesses.pricing import cost_usd, usage_numbers
from harnesses.session import EmptySummaryError, HarnessSession
from persistgym.env import EpisodeEnv
from persistgym.episode import Episode
from persistgym.survival import carried_in_text, survival_from_payload

RESULTS = runmeta.REPO_ROOT / "results"
RAW = RESULTS / "raw"


class Transport(Protocol):
    paid: bool

    def send(self, payload: dict) -> dict: ...


def check_echo(payload: dict, response: dict) -> dict:
    """Requested vs echoed reasoning settings, the returned model and service tier."""
    req = payload.get("reasoning") or {}
    got = response.get("reasoning") or {}
    return {
        "context_requested": req.get("context"), "context_echoed": got.get("context"),
        "context_ok": req.get("context") == got.get("context"),
        "effort_requested": req.get("effort"), "effort_echoed": got.get("effort"),
        "mode_requested": req.get("mode"), "mode_echoed": got.get("mode"),
        "model_requested": payload.get("model"), "model_returned": response.get("model"),
        "service_tier_requested": payload.get("service_tier"),
        "service_tier_returned": response.get("service_tier"),
        "status": response.get("status"),
    }


class JsonlRecorder:
    """Raw transcript writer (one JSON object per request/response pair)."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        # kept open across requests and closed by close(), so no context manager here
        if path.suffix == ".gz":
            self._f = gzip.open(path, "at", encoding="utf-8")  # noqa: SIM115
        else:
            self._f = path.open("a", encoding="utf-8")

    def __call__(self, event: dict) -> None:
        self._f.write(json.dumps(event, ensure_ascii=False) + "\n")

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
    need_correct: bool = False
    need_label: str | None = None
    routine_accuracy: float | None = None
    n_lookups: int = 0
    n_lookups_unavailable: int = 0  # over-cap lookups answered "lookup unavailable" (D3)
    n_turns: int = 0
    n_requests: int = 0
    n_summary_requests: int = 0
    n_summary_failures: int = 0
    n_unparsed_routine: int = 0  # unparsed replies at routine (non-need) steps
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


def _add_usage(run: EpisodeRun, response: dict) -> None:
    for k, v in usage_numbers(response.get("usage")).items():
        run.usage[k] = run.usage.get(k, 0) + v
    try:
        listed, billed = cost_usd(response.get("model") or "", response.get("usage"),
                                  response.get("service_tier"))
    except KeyError:
        run.cost_usd_list = run.cost_usd_billed_est = None
        return
    if run.cost_usd_list is not None:
        run.cost_usd_list += listed
        run.cost_usd_billed_est += billed


def _need_phase_add(run: EpisodeRun, req, info: dict, response: dict) -> None:
    """D8: add one call made while the need step is pending. `tokens` is the D8 quantity:
    provider-reported input tokens (cached included: OpenAI's `input_tokens` counts cached
    tokens) plus output tokens (reasoning included: `output_tokens` counts reasoning
    tokens). Summary calls fired while the need step is pending are calls at the need step
    and are included; they are also totalled apart (`summary_tokens`) for the reading that
    leaves them out. H1's cells (F-0, W-0) never summarize."""
    u = usage_numbers(response.get("usage"))
    if run.need_phase is None:
        run.need_phase = {"n_calls": 0, "n_step_calls": 0, "n_lookup_result_calls": 0,
                          "n_summary_calls": 0, "input_tokens": 0, "cached_input_tokens": 0,
                          "output_tokens": 0, "reasoning_tokens": 0, "tokens": 0,
                          "summary_tokens": 0, "first_step_call": None, "complete": False}
    n = run.need_phase
    n["n_calls"] += 1
    for k in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens"):
        n[k] += u[k]
    n["tokens"] += u["input_tokens"] + u["output_tokens"]
    if req.kind == "summary":
        n["n_summary_calls"] += 1
        n["summary_tokens"] += u["input_tokens"] + u["output_tokens"]
    else:
        n["n_step_calls"] += 1
        n["n_lookup_result_calls"] += bool(info["is_lookup_result"])
        if n["first_step_call"] is None:  # H2's usage[n]: the need step's first step call
            n["first_step_call"] = u


def run_episode(episode: Episode, cell: CellSpec, cfg: HarnessConfig, transport: Transport,
                recorder=None) -> EpisodeRun:
    env = EpisodeEnv(episode)
    session = HarnessSession.for_episode(cell, episode, cfg)
    run = EpisodeRun(episode.episode_id, episode.template_id, episode.cell.id, episode.variant,
                     cell.cell_id, model=cfg.model)
    run.designed = {k: episode.design.get(k) for k in (
        "S_window_obs_only", "S_window_assumed_replies", "far_by_obs_tokens",
        "gap_steps_latest", "gap_steps_earliest")}
    run.designed["evidence_steps"] = episode.reveal_steps
    need = episode.need_step
    echoed: Counter = Counter()
    models: Counter = Counter()
    tiers: Counter = Counter()
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
                        episode, req.payload["input"], system=req.payload["instructions"],
                        exclude_indices=[bridge] if bridge is not None else [])
                    run.need_info = dict(req.info)
                    # every compaction so far is applied to this payload (D12)
                    n_compactions_seen_at_need = len(session.compactions)
                    if bridge is not None:
                        run.need_bridge_carried = carried_in_text(
                            item_text(req.payload["input"][bridge]), episode)
                started = time.monotonic()
                response = transport.send(req.payload)
                run.call_latency_s.append(round(time.monotonic() - started, 3))
                run.n_requests += 1
                run.n_summary_requests += req.kind == "summary"
                echo = check_echo(req.payload, response)
                echoed[str(echo["context_echoed"])] += 1
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
                if not echo["context_ok"]:
                    run.excluded = True
                    run.exclusion_reason = (f"reasoning.context requested "
                                            f"{echo['context_requested']!r}, echoed "
                                            f"{echo['context_echoed']!r}")
                    if cfg.stop_on_context_mismatch:
                        run.exit_reason = "REASONING_CONTEXT_MISMATCH"
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
            obs, done = env.step(reply)
    except BudgetExceeded as e:
        run.exit_reason, run.error = "COST_CAP", str(e)
    except openai.OpenAIError as e:  # API errors after retries, rejected payloads
        run.exit_reason, run.error = "API_ERROR", f"{type(e).__name__}: {e}"
    finally:
        res = env.result()
        run.need_correct = res.need_correct
        run.need_label = res.need_label
        run.routine_accuracy = (res.routine_accuracy if res.routine_total else None)
        run.n_lookups = res.n_lookups
        run.n_lookups_unavailable = res.n_lookups_unavailable
        run.n_turns = res.n_turns
        run.n_unparsed_routine = sum(o == "unparsed" for s, o in res.step_outcomes.items()
                                     if s != need)
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
        run.echo = {"context_requested": cell.reasoning_context,
                    "context_echoed": dict(echoed), "models_returned": dict(models),
                    "service_tiers_returned": dict(tiers)}
    return run


def run_batch(episodes: list[Episode], cell: CellSpec, cfg: HarnessConfig,
              transport: Transport, *, experiment: str, run_id: str, milestone: str = "M0",
              results_root: Path = RESULTS, raw_root: Path = RAW, repeat_index: int = 0,
              notes: str = "", abort_after_api_errors: int = 2,
              run_matrix: dict | None = None) -> dict[str, Any]:
    """Run episodes in order; write results/<experiment>/<run_id>/{meta.json,summary.json,
    episodes.jsonl} and the raw transcript under results/raw/. For a pilot-blinded
    experiment (`blinding.BLINDED_EXPERIMENTS`) episodes.jsonl goes to
    results/raw/<experiment>/<run_id>/ instead, and meta.json leaves out reasoning tokens.
    Paid transports get their costs.csv row appended in `finally`, whatever happens.
    `run_matrix` (harnesses.matrix.RunMatrix.to_dict) is recorded in meta.json's config."""
    for what, name in (("experiment", experiment), ("run_id", run_id)):
        require_plain_name(what, name)
    blinded = blinding.is_blinded(experiment)
    out_dir = results_root / experiment / run_id
    raw_dir = raw_root / experiment / run_id
    raw_path = raw_dir / "transcript.jsonl.gz"
    episodes_path = (raw_dir if blinded else out_dir) / "episodes.jsonl"
    out_dir.mkdir(parents=True, exist_ok=True)
    episodes_path.parent.mkdir(parents=True, exist_ok=True)
    recorder = JsonlRecorder(raw_path)
    started = runmeta.utc_now()
    runs: list[EpisodeRun] = []
    exit_reason = "COMPLETED"
    try:
        with episodes_path.open("a", encoding="utf-8") as f:
            for ep in episodes:
                r = run_episode(ep, cell, cfg, transport, recorder)
                runs.append(r)
                f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
                f.flush()
                if r.exit_reason == "COST_CAP":
                    exit_reason = "COST_CAP"
                    break
                if sum(x.excluded for x in runs) >= cfg.abort_after_mismatched_episodes:
                    exit_reason = "ABORTED_CONTEXT_MISMATCH"
                    break
                if sum(x.exit_reason == "API_ERROR" for x in runs) >= abort_after_api_errors:
                    exit_reason = "ABORTED_API_ERRORS"
                    break
    except BaseException as e:
        exit_reason = f"ERROR:{type(e).__name__}"
        raise
    finally:
        recorder.close()
        cost_row = None
        if hasattr(transport, "finalize"):
            cost_row = transport.finalize(run_id=run_id, milestone=milestone,
                                          cell_or_config=cell.ascii_id, notes=notes)
        summary = blinding.run_summary([asdict(r) for r in runs], blinded=blinded)
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n",
                                              encoding="utf-8")
        meta = _write_meta(out_dir, raw_path, episodes, runs, cell, cfg, transport,
                           experiment=experiment, run_id=run_id, started=started,
                           exit_reason=exit_reason, repeat_index=repeat_index,
                           cost_row=cost_row, blinded=blinded, episodes_path=episodes_path,
                           run_matrix=run_matrix)
    return meta


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
                episodes_path=None, run_matrix=None) -> dict:
    echoed: Counter = Counter()
    models: Counter = Counter()
    usage: Counter = Counter()
    for r in runs:
        echoed.update(r.echo.get("context_echoed", {}))
        models.update(r.echo.get("models_returned", {}))
        usage.update(r.usage)
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
    extra = {}
    if blinded:
        # PREREG §11: one run is one arm, so its reasoning-token total is a per-arm number.
        tokens = blinding.blinded_tokens(tokens)
        extra["blinding"] = {"rule": blinding.WITHHELD_NOTE,
                             "episodes_path": _rel(episodes_path) if episodes_path else None}
    path = runmeta.write_meta(
        out_dir, experiment=experiment, run_id=run_id, cell_or_config=cell.cell_id,
        config=config, model_requested=cfg.model, model_returned=sorted(models),
        reasoning_effort=cfg.reasoning_effort, reasoning_mode=cfg.reasoning_mode,
        reasoning_context_requested=cell.reasoning_context,
        reasoning_context_echoed=dict(echoed), service_tier_requested=cfg.service_tier,
        template_id=sorted({e.template_id for e in episodes}), repeat_index=repeat_index,
        seeds={"template_seeds": sorted({e.template_seed for e in episodes})},
        started_utc=started, finished_utc=runmeta.utc_now(), exit_reason=exit_reason,
        tokens=tokens,
        cost_usd={"list": sum(listed) if None not in listed else None,
                  "billed_est": sum(billed) if None not in billed else None,
                  "costs_csv_row_appended": cost_row is not None},
        raw_transcript_path=_rel(raw_path), paid=bool(getattr(transport, "paid", False)),
        n_episodes_run=len(runs), n_excluded=sum(r.excluded for r in runs), **extra)
    return json.loads(path.read_text(encoding="utf-8"))
