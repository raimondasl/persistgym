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
"""

from __future__ import annotations

import gzip
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

import openai

from common import runmeta
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
    exit_reason: str = "DONE"
    error: str | None = None
    excluded: bool = False
    exclusion_reason: str | None = None
    need_correct: bool = False
    need_label: str | None = None
    routine_accuracy: float | None = None
    n_lookups: int = 0
    n_turns: int = 0
    n_requests: int = 0
    n_summary_requests: int = 0
    n_summary_failures: int = 0
    compactions: list[dict] = field(default_factory=list)
    need_payload: dict | None = None  # survival_from_payload at the need step
    need_bridge_carried: dict | None = None  # carried_in_text on the bridge, summary cells
    need_info: dict | None = None  # loss-policy bookkeeping of the need request
    designed: dict | None = None  # episode.design survival for reference
    echo: dict = field(default_factory=dict)
    usage: dict = field(default_factory=dict)
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


def run_episode(episode: Episode, cell: CellSpec, cfg: HarnessConfig, transport: Transport,
                recorder=None) -> EpisodeRun:
    env = EpisodeEnv(episode)
    session = HarnessSession.for_episode(cell, episode, cfg)
    run = EpisodeRun(episode.episode_id, episode.template_id, episode.cell.id, episode.variant,
                     cell.cell_id)
    run.designed = {k: episode.design.get(k) for k in (
        "S_window_obs_only", "S_window_assumed_replies", "far_by_obs_tokens",
        "gap_steps_latest", "gap_steps_earliest")}
    echoed: Counter = Counter()
    models: Counter = Counter()
    tiers: Counter = Counter()
    obs = env.observation
    done = False
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
                              and info["pending_step"] == episode.need_step
                              and not info["is_lookup_result"])
                if first_need:
                    bridge = req.info["bridge_index"]
                    run.need_payload = survival_from_payload(
                        episode, req.payload["input"], system=req.payload["instructions"],
                        exclude_indices=[bridge] if bridge is not None else [])
                    run.need_info = dict(req.info)
                    if bridge is not None:
                        run.need_bridge_carried = carried_in_text(
                            item_text(req.payload["input"][bridge]), episode)
                response = transport.send(req.payload)
                run.n_requests += 1
                run.n_summary_requests += req.kind == "summary"
                echo = check_echo(req.payload, response)
                echoed[str(echo["context_echoed"])] += 1
                models[str(echo["model_returned"])] += 1
                tiers[str(echo["service_tier_returned"])] += 1
                _add_usage(run, response)
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
        run.n_turns = res.n_turns
        run.compactions = [{k: v for k, v in c.items() if k != "summary_text"}
                           for c in session.compactions]
        run.echo = {"context_requested": cell.reasoning_context,
                    "context_echoed": dict(echoed), "models_returned": dict(models),
                    "service_tiers_returned": dict(tiers)}
    return run


def run_batch(episodes: list[Episode], cell: CellSpec, cfg: HarnessConfig,
              transport: Transport, *, experiment: str, run_id: str, milestone: str = "M0",
              results_root: Path = RESULTS, raw_root: Path = RAW, repeat_index: int = 0,
              notes: str = "", abort_after_api_errors: int = 2) -> dict[str, Any]:
    """Run episodes in order; write results/<experiment>/<run_id>/{meta.json,episodes.jsonl}
    and the raw transcript under results/raw/. Paid transports get their costs.csv row
    appended in `finally`, whatever happens."""
    out_dir = results_root / experiment / run_id
    raw_path = raw_root / experiment / run_id / "transcript.jsonl.gz"
    out_dir.mkdir(parents=True, exist_ok=True)
    recorder = JsonlRecorder(raw_path)
    started = runmeta.utc_now()
    runs: list[EpisodeRun] = []
    exit_reason = "COMPLETED"
    try:
        with (out_dir / "episodes.jsonl").open("a", encoding="utf-8") as f:
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
        meta = _write_meta(out_dir, raw_path, episodes, runs, cell, cfg, transport,
                           experiment=experiment, run_id=run_id, started=started,
                           exit_reason=exit_reason, repeat_index=repeat_index,
                           cost_row=cost_row)
    return meta


def _write_meta(out_dir, raw_path, episodes, runs, cell, cfg, transport, *, experiment, run_id,
                started, exit_reason, repeat_index, cost_row) -> dict:
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
    try:
        raw_rel = str(raw_path.relative_to(runmeta.REPO_ROOT).as_posix())
    except ValueError:
        raw_rel = str(raw_path)
    path = runmeta.write_meta(
        out_dir, experiment=experiment, run_id=run_id, cell_or_config=cell.cell_id,
        config=config, model_requested=cfg.model, model_returned=sorted(models),
        reasoning_effort=cfg.reasoning_effort, reasoning_mode=cfg.reasoning_mode,
        reasoning_context_requested=cell.reasoning_context,
        reasoning_context_echoed=dict(echoed), service_tier_requested=cfg.service_tier,
        template_id=sorted({e.template_id for e in episodes}), repeat_index=repeat_index,
        seeds={"template_seeds": sorted({e.template_seed for e in episodes})},
        started_utc=started, finished_utc=runmeta.utc_now(), exit_reason=exit_reason,
        tokens=dict(usage),
        cost_usd={"list": sum(listed) if None not in listed else None,
                  "billed_est": sum(billed) if None not in billed else None,
                  "costs_csv_row_appended": cost_row is not None},
        raw_transcript_path=raw_rel, paid=bool(getattr(transport, "paid", False)),
        n_episodes_run=len(runs), n_excluded=sum(r.excluded for r in runs))
    return json.loads(path.read_text(encoding="utf-8"))
