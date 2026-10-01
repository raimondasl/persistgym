"""Shared helpers for the harness tests.

The snapshot tests drive a `HarnessSession` over a synthetic episode whose observations,
replies and summaries have exact token counts, so the window boundary and the summary trigger
fall on known steps. Labels are derived from payload *content* (`label_payload`), never from
the session's own bookkeeping, so a bookkeeping bug cannot hide a payload bug.
"""

from __future__ import annotations

import re

import pytest

from harnesses.config import ARC_SUMMARY_REQUEST_PROMPT, HarnessConfig
from harnesses.fake import FakeModel
from harnesses.session import HarnessSession
from persistgym import tokens
from persistgym.config import GeneratorConfig
from persistgym.episode import ALL_CELLS
from persistgym.render import generate

SYSTEM = "You are the operator.\nReply with one action.\nACTION: <action>"
BRIDGE_PREFIX = "Earlier conversation history was compacted."


def text_with_tokens(prefix: str, n: int) -> str:
    """`prefix` padded with ' x' words to exactly n o200k_base tokens."""
    text = prefix
    while tokens.count(text) < n:
        text += " x"
    if tokens.count(text) != n:
        raise AssertionError(f"cannot hit {n} tokens with prefix {prefix!r}")
    return text


def obs_text(i: int, n: int = 200) -> str:
    return text_with_tokens(f"OBS[{i}]", n)


def reply_text(i: int, n: int = 50) -> str:
    return text_with_tokens(f"REPLY[{i}]", n)


def summary_text(j: int) -> str:
    return text_with_tokens(f"SUMMARY s{j}", 60)


def run_synthetic(cell, *, n_steps: int = 9, W: int = 1000, obs_tokens: int = 200,
                  reply_tokens: int | dict = 50, count_system: bool = False,
                  cfg: HarnessConfig | None = None, fake: FakeModel | None = None):
    """Drive a session over `n_steps` synthetic observations. Returns (session, model,
    requests) where requests is the list of Request objects in send order."""
    cfg = cfg or HarnessConfig()

    def reply_fn(payload, i):
        n = reply_tokens.get(i, 50) if isinstance(reply_tokens, dict) else reply_tokens
        return reply_text(i, n)

    model = fake or FakeModel(reply_fn, summary_fn=lambda p, j: summary_text(j))
    session = HarnessSession(cell, SYSTEM, cfg, W_tokens=W, count_system=count_system)
    requests = []
    for i in range(n_steps):
        session.observe(obs_text(i, obs_tokens))
        while True:
            req = session.next_request()
            requests.append(req)
            session.record(req, model.send(req.payload))
            if req.kind == "step":
                break
    return session, model, requests


_OBS = re.compile(r"^OBS\[(\d+)\]")
_SUM = re.compile(r"SUMMARY s(\d+)")


def label_item(item: dict) -> str:
    """Content-derived label of one input item (independent of the session's trace)."""
    if item.get("type") == "reasoning":
        m = re.fullmatch(r"rs_t(\d+)", item["id"])
        assert item["encrypted_content"] == f"gAAAAB-fake-encrypted-{item['id'][3:]}"
        return f"R{m.group(1)}" if m else f"BAD-{item['id']}"
    role = item.get("role")
    text = "".join(p["text"] for p in item["content"])
    if role == "assistant":
        m = re.fullmatch(r"msg_t(\d+)", item["id"])
        assert text.startswith(f"REPLY[{m.group(1)}]") if m else True
        return f"A{m.group(1)}" if m else f"BAD-{item['id']}"
    if role == "user":
        if text == ARC_SUMMARY_REQUEST_PROMPT:
            return "Q"
        if text.startswith(BRIDGE_PREFIX):
            return f"B{_SUM.search(text).group(1)}"
        m = _OBS.match(text)
        return f"U{m.group(1)}" if m else "BAD-user"
    return "BAD"


def label_payload(payload: dict) -> list[str]:
    return [label_item(i) for i in payload["input"]]


def turns(a: int, b: int) -> list[str]:
    """Expected labels of turns a..b-1 sent verbatim (observation, reasoning item, reply)."""
    out = []
    for t in range(a, b):
        out += [f"U{t}", f"R{t}", f"A{t}"]
    return out


def step(keep: int, m: int, bridge: int | None = None) -> list[str]:
    """Expected labels of the step request for observation m keeping turns keep..m-1."""
    return ([f"B{bridge}"] if bridge else []) + turns(keep, m) + [f"U{m}"]


# Small generator volume for real-episode tests (same W/v ratio as the defaults).
SMALL = GeneratorConfig(W_tokens=6_400, v_tokens=400, assumed_max_reply_tokens=200)


@pytest.fixture(scope="session")
def small_eps():
    """3 templates x 8 task cells, base variant, at the small volume."""
    return [ep for _, eps in generate("main", range(3), SMALL, ALL_CELLS, ("base",))
            for ep in eps]
