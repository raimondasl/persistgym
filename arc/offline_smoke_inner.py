"""One offline game with a stub model, run inside the patched harness environment.

offline_smoke.py starts this file once per (config, game) with the patched
worktree's interpreter:

    uv run --no-sync --project arc/.work/offline-smoke python arc/offline_smoke_inner.py \
        --config google-gemini-3-8-flash-high --game toyg --out <run dir>

It needs OPERATION_MODE=offline and ENVIRONMENTS_DIR in the environment, and
the worktree plus arc/ on PYTHONPATH. The model is ``StubModel``: an httpx
transport that answers Gemini Interactions or OpenAI chat-completions requests
with canned actions through the real SDK client. A socket guard blocks every
non-loopback connection, so nothing can reach a model provider or ARC.

The helpers above ``main`` need only the standard library and httpx, so the
root test suite can test them without the harness.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import random
import re
import shutil
import socket
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

# Must equal benchmarking.compaction.SUMMARY_SYSTEM_PROMPT; main() checks it.
SUMMARY_SYSTEM_PROMPT = (
    "You create concise conversation summaries for reliable continuation. "
    "Return only the requested summary."
)
STUB_API_KEY = "offline-stub-key"
DEFAULT_TRIGGER_TOKENS = 180_000
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_ACTION_LINE = re.compile(r"^- (RESET|ACTION[1-7])\b", re.MULTILINE)


# ── Stub model ─────────────────────────────────────────────────────────


def available_actions(observation: str) -> list[str]:
    """Action names listed under the last 'Available actions:' heading."""
    _, _, tail = observation.rpartition("Available actions:")
    return _ACTION_LINE.findall(tail)


class StubPolicy:
    """Canned actions: a fixed script, else a seeded choice of available actions.

    The script's last entry repeats when it runs out. Without a script the
    policy never chooses RESET (the harness resets after a lost life), and
    ACTION6 gets seeded coordinates.
    """

    def __init__(self, seed: int = 0, script: list[str] | None = None) -> None:
        self.rng = random.Random(seed)
        self.script = list(script or [])
        self.turn = 0

    def next_action(self, observation: str) -> str:
        self.turn += 1
        if self.script:
            name = self.script[min(self.turn, len(self.script)) - 1]
        else:
            options = [name for name in available_actions(observation) if name != "RESET"]
            name = self.rng.choice(options or ["ACTION1"])
        if name == "ACTION6":
            return f"ACTION6 {self.rng.randint(0, 63)} {self.rng.randint(0, 63)}"
        return name


class StubUsage:
    """Provider-reported total tokens for an action turn.

    ``fixed``: 120 tokens, or ``trigger_tokens`` on ``trigger_turns``.
    ``chars``: one token per character of request text, so the 175k summary
    trigger and Standard's 175k-character trimming are reached as in a long
    real game.
    """

    def __init__(
        self,
        mode: str = "fixed",
        trigger_turns: set[int] | None = None,
        trigger_tokens: int = DEFAULT_TRIGGER_TOKENS,
    ) -> None:
        if mode not in {"fixed", "chars"}:
            raise ValueError(f"Unknown usage mode {mode!r}.")
        self.mode = mode
        self.trigger_turns = set(trigger_turns or ())
        self.trigger_tokens = trigger_tokens

    def total_tokens(self, turn: int, request_chars: int) -> int:
        if self.mode == "chars":
            return request_chars + 20
        return self.trigger_tokens if turn in self.trigger_turns else 120


def request_texts(body: dict[str, Any]) -> tuple[str, list[str]]:
    """System prompt and every message text of an Interactions or chat body."""
    if "messages" in body:
        messages = body["messages"]
        system = messages[0]["content"] if messages and messages[0]["role"] == "system" else ""
        rest = messages[1:] if system else messages
        return system, [str(message["content"]) for message in rest]
    texts = [
        part.get("text", "")
        for item in body.get("input", [])
        for part in item.get("content", []) or []
        if isinstance(part, dict)
    ]
    return str(body.get("system_instruction", "")), texts


def last_user_text(body: dict[str, Any]) -> str:
    if "messages" in body:
        users = [m["content"] for m in body["messages"] if m["role"] == "user"]
        return str(users[-1]) if users else ""
    users = [item for item in body.get("input", []) if item.get("type") == "user_input"]
    if not users:
        return ""
    return "".join(part.get("text", "") for part in users[-1].get("content", []))


def interactions_response(index: int, text: str, total: int) -> dict[str, Any]:
    return {
        "id": f"stub-interaction-{index}",
        "created": "2026-10-01T00:00:00Z",
        "updated": "2026-10-01T00:00:00Z",
        "status": "completed",
        "steps": [
            {
                "type": "thought",
                "signature": f"stub-signature-{index}",
                "summary": [{"type": "text", "text": f"stub thinking {index}"}],
            },
            {"type": "model_output", "content": [{"type": "text", "text": text}]},
        ],
        "usage": {
            "total_input_tokens": max(total - 20, 0),
            "total_output_tokens": 10,
            "total_thought_tokens": 10,
            "total_tokens": total,
        },
    }


def chat_response(index: int, model: str, text: str, total: int) -> dict[str, Any]:
    return {
        "id": f"stub-chat-{index}",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": text},
            }
        ],
        "usage": {
            "prompt_tokens": max(total - 10, 0),
            "completion_tokens": 10,
            "total_tokens": total,
        },
    }


class StubModel:
    """httpx handler answering model requests with canned actions."""

    def __init__(self, policy: StubPolicy, usage: StubUsage) -> None:
        self.policy = policy
        self.usage = usage
        self.bodies: list[dict[str, Any]] = []
        self.reported_totals: list[int] = []
        self.summaries = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        system, texts = request_texts(body)
        if system == SUMMARY_SYSTEM_PROMPT:
            self.summaries += 1
            text, total = f"summary {self.summaries}: offline stub summary", 1_000
        else:
            turn = len(self.reported_totals) + 1
            action = self.policy.next_action(last_user_text(body))
            text = f"turn {turn}: {action}"
            total = self.usage.total_tokens(turn, len(system) + sum(map(len, texts)))
            self.reported_totals.append(total)
        index = len(self.bodies)
        if "messages" in body:
            payload = chat_response(index, str(body.get("model", "stub")), text, total)
        else:
            payload = interactions_response(index, text, total)
        return httpx.Response(200, request=request, json=payload)


# ── Safety ─────────────────────────────────────────────────────────────


def guard_network() -> None:
    """Make every non-loopback socket connection raise."""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def _check(address: Any) -> None:
        host = address[0] if isinstance(address, tuple) else address
        if host not in LOOPBACK_HOSTS:
            raise RuntimeError(f"offline smoke run blocked a connection to {address!r}")

    def connect(sock: socket.socket, address: Any) -> None:
        _check(address)
        real_connect(sock, address)

    def connect_ex(sock: socket.socket, address: Any) -> int:
        _check(address)
        return real_connect_ex(sock, address)

    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", required=True)
    parser.add_argument("--game", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--usage", choices=["fixed", "chars"], default="fixed")
    parser.add_argument("--trigger-turns", default="", help="comma-separated turns")
    parser.add_argument("--script", default="", help="comma-separated actions")
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args(argv)


def _csv(value: str, convert: Callable[[str], Any] = str) -> list[Any]:
    return [convert(item.strip()) for item in value.split(",") if item.strip()]


# ── Harness run (patched harness environment only) ─────────────────────


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if os.environ.get("OPERATION_MODE", "").strip().lower() != "offline":
        print("offline_smoke_inner.py requires OPERATION_MODE=offline", file=sys.stderr)
        return 2
    guard_network()
    # Disable python-dotenv before arc_agi (imported by the harness) loads.
    importlib.import_module("no_dotenv_plugin")
    import benchmarking.agent as agent_module
    from arc_agi import OperationMode
    from benchmarking import compaction, runtime_clients
    from benchmarking.model_config import get_model_config
    from benchmarking.swarm import Swarm

    if compaction.SUMMARY_SYSTEM_PROMPT != SUMMARY_SYSTEM_PROMPT:
        print("SUMMARY_SYSTEM_PROMPT differs from the harness", file=sys.stderr)
        return 2
    config = get_model_config(args.config)
    os.environ[config["client"].get("api_key_env", "GOOGLE_API_KEY")] = STUB_API_KEY

    stub = StubModel(
        StubPolicy(seed=args.seed, script=_csv(args.script)),
        StubUsage(args.usage, set(_csv(args.trigger_turns, int))),
    )
    real_builder = runtime_clients.build_model_runtime_client

    def build_client(**kwargs: Any) -> Any:
        # The configured transport_retry wrapper, if any, wraps the stub.
        if kwargs.get("http_transport") is None:
            kwargs["http_transport"] = httpx.MockTransport(stub)
        return real_builder(**kwargs)

    agent_module.default_http_transport = lambda: httpx.MockTransport(stub)
    agent_module.build_model_runtime_client = build_client

    swarm = Swarm(
        ROOT_URL="http://offline.invalid",
        games=[args.game],
        tags=["offline-smoke"],
        config=args.config,
        operation_mode=OperationMode.OFFLINE,
    )
    swarm.main()

    agent = swarm.agents[0]
    # Copy the harness files under short names: the harness's own run
    # directory name is long, and Windows paths stop at 260 characters.
    args.out.mkdir(parents=True, exist_ok=True)
    run_dir = args.out / "run"
    shutil.copytree(Path(agent.run_dir), run_dir, dirs_exist_ok=True)
    recorder = getattr(agent, "recorder", None)
    if recorder is not None and Path(recorder.filename).exists():
        shutil.copyfile(recorder.filename, run_dir / "recording.jsonl")
    (args.out / "bodies.json").write_text(json.dumps(stub.bodies, indent=1))
    result = {
        "config": args.config,
        "game": args.game,
        "run_dir": str(run_dir),
        "run_meta": json.loads((run_dir / "run_meta.json").read_text()),
        "steps": len(list(run_dir.glob("step_*.json"))),
        "compactions": len(list(run_dir.glob("compaction_*.json"))),
        "reported_totals": stub.reported_totals,
        "summaries": stub.summaries,
        "usage_mode": args.usage,
    }
    (args.out / "result.json").write_text(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
