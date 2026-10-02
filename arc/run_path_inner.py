"""The part of the ARC launcher that runs inside the patched harness environment.

arc/run_path.py (the guarded launcher) and arc/config_hash.py start this file with the
patched worktree's interpreter, never directly:

    uv run --no-sync --project arc/.work/<name> python arc/run_path_inner.py <mode> ...

Modes:

* ``resolve`` writes the named profiles as the harness's own ``get_model_config`` returns
  them (validated). It makes no network call and needs no key.
* ``play`` plays ONE game under one profile online through ARC's scorecard, exactly as the
  harness's ``main.py`` would (``Swarm`` with ``https://arcprize.org``), with three
  additions that change no request body: every model HTTP call is timed into
  ``calls.jsonl``; the harness cost guard (patch 0010) is set to ``--cost-cap-usd``; and an
  optional truncation (``--max-actions``, ``--after-summary-turns``) for the block-1 pilot
  ends the run with ``ACTION_BUDGET`` and records why in ``result.json``. It refuses before
  any network call if the resolved profile's hash differs from ``--expect-config-hash``.
* ``accept`` sends ONE minimal action request per profile (the harness's own adapter,
  request settings and system prompt, with a one-line user message) to confirm the
  provider accepts the payload, and writes ``accept.json``. It plays no game.

The launcher has already run every paid-call check and holds the paid-run lock; this file
never reads ``.env`` (python-dotenv is disabled before the harness imports it). The helpers
above the mode functions need only the standard library and httpx, so the root test suite
tests them without the harness.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import logging
import os
import re
import sys
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx

ARC_ROOT_URL = "https://arcprize.org"
ACCEPT_PROMPT = "This is a connectivity check, not a game. Reply with one word: ready."
RESULT_FILE = "result.json"
ACCEPT_FILE = "accept.json"
CALLS_FILE = "calls.jsonl"
CONFIG_FILE = "config.json"
LOG_FILE = "harness.log"
CONFIG_MISMATCH_EXIT = 3


# ── Helpers (standard library and httpx only) ─────────────────────────


def config_hash(config: dict) -> str:
    """SHA-256 of the canonical JSON config; must equal common.runmeta.config_hash."""
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class MeteringTransport(httpx.BaseTransport):
    """Times every HTTP request of the model client and appends one JSON line per request
    to ``path``: start time, method, URL path, status (or exception type) and seconds until
    the response headers arrived. Bodies, headers and query strings are never written, so
    neither a prompt nor a key reaches the file. The request and response pass unchanged."""

    def __init__(self, inner: httpx.BaseTransport, path: Path,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._inner = inner
        self._path = path
        self._clock = clock
        self._lock = threading.Lock()

    def _write(self, record: dict[str, Any]) -> None:
        with self._lock, self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        started_utc, started = utc_now(), self._clock()
        record: dict[str, Any] = {"started_utc": started_utc, "method": request.method,
                                  "path": request.url.path}
        try:
            response = self._inner.handle_request(request)
        except BaseException as e:
            record.update(status=None, error=type(e).__name__,
                          duration_s=round(self._clock() - started, 3))
            self._write(record)
            raise
        record.update(status=response.status_code, duration_s=round(self._clock() - started, 3))
        self._write(record)
        return response

    def close(self) -> None:
        self._inner.close()


class Truncation:
    """When the block-1 pilot stops early (PLAN §16.3): after ``max_actions`` actions, or
    ``after_summary_turns`` saved steps from the first harness summary on (S1: "to its first
    compaction plus 5 turns"). ``None`` disables a rule. Counted runs use neither."""

    def __init__(self, max_actions: int | None = None,
                 after_summary_turns: int | None = None) -> None:
        self.max_actions = max_actions
        self.after_summary_turns = after_summary_turns
        self.first_summary_before_step: int | None = None
        self.reason: str | None = None

    def note_summary(self, before_step: int) -> None:
        if self.first_summary_before_step is None:
            self.first_summary_before_step = before_step

    def check(self, *, actions: int, steps_saved: int) -> str | None:
        """The reason to stop now, or None. Remembers the first reason given."""
        if self.max_actions is not None and actions >= self.max_actions:
            self.reason = self.reason or f"max_actions={self.max_actions}"
        elif (self.after_summary_turns is not None
              and self.first_summary_before_step is not None
              and steps_saved - self.first_summary_before_step + 1 >= self.after_summary_turns):
            self.reason = self.reason or (f"after_summary_turns={self.after_summary_turns} "
                                          f"(first summary before step "
                                          f"{self.first_summary_before_step})")
        return self.reason

    def to_dict(self) -> dict[str, Any]:
        return {"max_actions": self.max_actions,
                "after_summary_turns": self.after_summary_turns,
                "first_summary_before_step": self.first_summary_before_step,
                "truncated": self.reason is not None, "reason": self.reason}


def run_interruptibly(target: Callable[[], Any], *, poll_s: float = 1.0) -> Any:
    """`target()` in a daemon thread while the main thread polls it, as the harness's
    main.py runs ``Swarm.main``. Called directly, ``Swarm.main`` waits in a plain
    ``Thread.join()``, which Ctrl+C cannot interrupt on Windows (Python 3.12: the
    KeyboardInterrupt is raised only when the joined thread ends), so the game would play
    on to its end. Returns target's result or re-raises its exception. A KeyboardInterrupt
    raised in the main thread propagates at once; the daemon thread ends with the
    process."""
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["result"] = target()
        except BaseException as e:  # noqa: BLE001 - re-raised in the main thread
            box["error"] = e

    thread = threading.Thread(target=run, name="swarm-main", daemon=True)
    thread.start()
    while thread.is_alive():
        thread.join(timeout=poll_s)
    if "error" in box:
        raise box["error"]
    return box.get("result")


def _log_to(path: Path) -> None:
    """The harness's INFO log to the console and `path`, as main.py logs to logs.log."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    for handler in (logging.StreamHandler(sys.stdout),
                    logging.FileHandler(path, encoding="utf-8")):
        handler.setFormatter(formatter)
        root.addHandler(handler)


SECRET_FIELD = re.compile(r"api_?key|token|secret|password|credential|cookie", re.IGNORECASE)


def scrub(data: Any) -> Any:
    """`data` without any mapping entry whose name looks like a credential, at any depth.
    ARC's scorecard model has an ``api_key`` field that the API response could fill."""
    if isinstance(data, dict):
        return {k: scrub(v) for k, v in data.items() if not SECRET_FIELD.search(str(k))}
    if isinstance(data, list):
        return [scrub(v) for v in data]
    return data


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    r = sub.add_parser("resolve")
    r.add_argument("--configs", required=True)
    r.add_argument("--out", required=True, type=Path)
    p = sub.add_parser("play")
    p.add_argument("--config", required=True)
    p.add_argument("--game", required=True)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--expect-config-hash", required=True)
    p.add_argument("--cost-cap-usd", required=True, type=float)
    p.add_argument("--tags", default="")
    p.add_argument("--max-actions", type=int, default=None)
    p.add_argument("--after-summary-turns", type=int, default=None)
    a = sub.add_parser("accept")
    a.add_argument("--configs", required=True)
    a.add_argument("--out", required=True, type=Path)
    a.add_argument("--expect-config-hashes", required=True, help="JSON {config_id: sha256}")
    a.add_argument("--cost-cap-usd", required=True, type=float)
    return parser.parse_args(argv)


def _online_only() -> str | None:
    """Why this process must not run online, or None."""
    mode = os.environ.get("OPERATION_MODE", "").strip().lower()
    if mode not in ("", "online"):
        return f"OPERATION_MODE={mode!r}; paid runs use ARC's online scorecard"
    if os.environ.get("ARC_BASE_URL"):
        return "ARC_BASE_URL is set; paid runs use ARC's hosted API"
    return None


# ── Modes (patched harness environment only) ──────────────────────────


def _harness() -> SimpleNamespace:
    # Disable python-dotenv before arc_agi (imported by the harness) loads.
    importlib.import_module("no_dotenv_plugin")
    import benchmarking.agent as agent_module
    from benchmarking.base import ExitReason
    from benchmarking.model_config import get_model_config

    return SimpleNamespace(agent_module=agent_module, ExitReason=ExitReason,
                           get_model_config=get_model_config)


def resolve(args: argparse.Namespace) -> int:
    h = _harness()
    write_json(args.out, {cid: h.get_model_config(cid) for cid in _csv(args.configs)})
    return 0


def _meter(h: SimpleNamespace, calls_path: Path) -> None:
    """Route every model client's HTTP through MeteringTransport (below transport_retry)."""
    agent_module = h.agent_module
    real_default = agent_module.default_http_transport
    real_builder = agent_module.build_model_runtime_client
    agent_module.default_http_transport = lambda: MeteringTransport(real_default(), calls_path)

    def build_client(**kwargs: Any) -> Any:
        if kwargs.get("http_transport") is None:  # a profile without transport_retry
            kwargs["http_transport"] = MeteringTransport(real_default(), calls_path)
        return real_builder(**kwargs)

    agent_module.build_model_runtime_client = build_client


def play(args: argparse.Namespace) -> int:
    reason = _online_only()
    if reason:
        print(f"run_path_inner: {reason}", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    _log_to(args.out / LOG_FILE)
    h = _harness()
    config = h.get_model_config(args.config)
    write_json(args.out / CONFIG_FILE, config)
    if config_hash(config) != args.expect_config_hash:
        print(f"run_path_inner: {args.config} hashes to {config_hash(config)}, not the frozen "
              f"{args.expect_config_hash}", file=sys.stderr)
        return CONFIG_MISMATCH_EXIT

    from arc_agi import OperationMode
    from benchmarking.swarm import Swarm

    _meter(h, args.out / CALLS_FILE)
    agent_cls = h.agent_module.BenchmarkingAgent
    truncation = Truncation(args.max_actions, args.after_summary_turns)
    state: dict[str, Any] = {"card_ids": []}
    real_init, real_is_done = agent_cls.__init__, agent_cls.is_done
    real_save_compaction = agent_cls._save_compaction

    def __init__(self: Any, *a: Any, **k: Any) -> None:
        real_init(self, *a, **k)
        own = getattr(self, "MAX_RUN_COST_USD", None)  # a profile's own guard, if any
        self.MAX_RUN_COST_USD = args.cost_cap_usd if own is None else min(own,
                                                                          args.cost_cap_usd)
        state["agent"] = self
        self._write_run_meta()

    def is_done(self: Any, frames: Any, latest_frame: Any) -> bool:
        if real_is_done(self, frames, latest_frame):
            return True
        if truncation.check(actions=self.action_counter, steps_saved=self.step_counter):
            self.exit_reason = h.ExitReason.ACTION_BUDGET
            return True
        return False

    def _save_compaction(self: Any, compaction: Any) -> None:
        truncation.note_summary(compaction.before_step)
        real_save_compaction(self, compaction)

    agent_cls.__init__ = __init__
    agent_cls.is_done = is_done
    agent_cls._save_compaction = _save_compaction

    swarm = Swarm(ROOT_URL=ARC_ROOT_URL, games=[args.game], tags=_csv(args.tags),
                  config=args.config, operation_mode=OperationMode.ONLINE)
    real_open = swarm.open_scorecard

    def open_scorecard() -> str:
        card_id = real_open()
        state["card_ids"].append(card_id)
        return card_id

    swarm.open_scorecard = open_scorecard  # type: ignore[method-assign]
    result: dict[str, Any] = {"config": args.config, "game": args.game,
                              "started_utc": utc_now(), "error": None, "interrupted": False}
    scorecard = None
    try:
        scorecard = run_interruptibly(swarm.main)
    except KeyboardInterrupt:
        result["interrupted"] = True
        if swarm.card_id:  # close the scorecard as main.py's SIGINT handler does
            try:
                scorecard = swarm.close_scorecard(swarm.card_id)
            except Exception as e:  # noqa: BLE001 - recorded, the run is over anyway
                result["error"] = f"closing the scorecard failed: {type(e).__name__}"
    except Exception as e:  # noqa: BLE001 - recorded for the launcher
        result["error"] = f"{type(e).__name__}: {e}"[:500]
    finally:
        agent = state.get("agent")
        result.update(
            finished_utc=utc_now(),
            card_id=(state["card_ids"] or [None])[-1],
            run_dir=str(Path(agent.run_dir).resolve()) if agent is not None else None,
            recording=(str(Path(agent.recorder.filename).resolve())
                       if agent is not None and getattr(agent, "recorder", None) else None),
            game_id_served=getattr(getattr(getattr(agent, "arc_env", None), "info", None),
                                   "game_id", None),
            action_counter=getattr(agent, "action_counter", None),
            exit_reason=(getattr(getattr(agent, "exit_reason", None), "value", None)),
            truncation=truncation.to_dict(),
            scorecard=(scrub(scorecard.model_dump(mode="json", exclude={"api_key"}))
                       if scorecard is not None else None),
        )
        write_json(args.out / RESULT_FILE, result)
    return 0 if result["error"] is None and not result["interrupted"] else 1


def accept(args: argparse.Namespace) -> int:
    args.out.mkdir(parents=True, exist_ok=True)
    expected = json.loads(args.expect_config_hashes)
    h = _harness()
    from benchmarking.runtime_models import Message, ModelRequest

    configs = {cid: h.get_model_config(cid) for cid in _csv(args.configs)}
    write_json(args.out / CONFIG_FILE, configs)
    wrong = {cid: config_hash(c) for cid, c in configs.items()
             if config_hash(c) != expected.get(cid)}
    if wrong:
        print(f"run_path_inner: profiles differ from the freeze record: {wrong}",
              file=sys.stderr)
        return CONFIG_MISMATCH_EXIT
    _meter(h, args.out / CALLS_FILE)
    results: list[dict[str, Any]] = []
    spent_list = 0.0
    for cid, config in configs.items():
        pricing = config.get("pricing") or {}
        if spent_list >= args.cost_cap_usd:
            results.append({"config_id": cid, "skipped": "cost cap reached"})
            continue
        agent = h.agent_module.BenchmarkingAgent(
            card_id="acceptance-check", game_id="acceptance", agent_name="acceptance",
            ROOT_URL=ARC_ROOT_URL, record=False,
            arc_env=SimpleNamespace(info=SimpleNamespace(baseline_actions=[])), config=cid)
        request = ModelRequest(
            messages=[Message(role="system", content=agent._build_system_prompt()),
                      Message(role="user", content=ACCEPT_PROMPT)],
            request_config=dict(agent._request_kwargs))
        record: dict[str, Any] = {"config_id": cid, "started_utc": utc_now(),
                                  "request_settings": {k: v for k, v in
                                                       agent._request_kwargs.items()}}
        started = time.monotonic()
        try:
            response = agent._adapter.invoke(request)
        except Exception as e:  # noqa: BLE001 - the check reports it
            usage = getattr(e, "usage", None)
            record.update(accepted=False, error=f"{type(e).__name__}: {e}"[:500],
                          usage=_usage_dict(usage) if usage is not None else None)
        else:
            record.update(accepted=True, output_text=response.output_text[:200],
                          reported_model=response.reported_model,
                          service_tier=response.service_tier,
                          usage=_usage_dict(response.usage))
        record["latency_s"] = round(time.monotonic() - started, 3)
        u = record.get("usage") or {}
        spent_list += (u.get("prompt_tokens", 0) * pricing.get("input", 0)
                       + u.get("completion_tokens", 0) * pricing.get("output", 0)) / 1e6
        results.append(record)
        write_json(args.out / ACCEPT_FILE, results)
    write_json(args.out / ACCEPT_FILE, results)
    return 0 if all(r.get("accepted") for r in results) else 1


def _usage_dict(usage: Any) -> dict[str, int]:
    """NormalizedUsage in the harness's step-record names (StepUsage)."""
    return {"prompt_tokens": int(usage.input_tokens or 0),
            "completion_tokens": int(usage.output_tokens or 0),
            "reasoning_tokens": int(usage.reasoning_tokens or 0),
            "cached_tokens": int(usage.cached_tokens or 0)}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return {"resolve": resolve, "play": play, "accept": accept}[args.mode](args)


if __name__ == "__main__":
    raise SystemExit(main())
