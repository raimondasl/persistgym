"""Shared helpers for the harness tests.

The snapshot tests drive a `HarnessSession` over a synthetic episode whose observations,
replies and summaries have exact token counts, so the window boundary and the summary trigger
fall on known steps. Labels are derived from payload *content* (`label_payload`), never from
the session's own bookkeeping, so a bookkeeping bug cannot hide a payload bug.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from pathlib import Path

import pytest

from common import paidlock
from common.tests.gitrepo import FROZEN_PREREG, decisions_text, guarded_repo
from harnesses import cli
from harnesses.config import ARC_SUMMARY_REQUEST_PROMPT, HarnessConfig
from harnesses.fake import FakeModel, padded_text
from harnesses.session import HarnessSession
from persistgym import tokens
from persistgym.config import GeneratorConfig
from persistgym.episode import ALL_CELLS
from persistgym.render import generate

SYSTEM = "You are the operator.\nReply with one action.\nACTION: <action>"
BRIDGE_PREFIX = "Earlier conversation history was compacted."


# --- no network in harness tests ----------------------------------------------------------

class NetworkBlocked(RuntimeError):
    pass


def _is_loopback(address) -> bool:
    host = address[0] if isinstance(address, tuple) else address
    if not isinstance(host, str):
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False


@pytest.fixture(scope="module", autouse=True)
def no_network():
    """Every harness test runs with outbound connections blocked, so a test that would reach
    an API (paid or not) fails loudly instead. Module scope (not session) so the patch is
    undone after each harness test module and never leaks into other suites' tests. Loopback stays open (asyncio uses it on
    Windows). The tokenizer is loaded first: tiktoken downloads o200k_base once if it is not
    cached yet, a free public file, never an API call."""
    tokens.encoding("o200k_base")
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def connect(self, address):
        if not _is_loopback(address):
            raise NetworkBlocked(f"network access in a harness test: {address!r}")
        return real_connect(self, address)

    def connect_ex(self, address):
        if not _is_loopback(address):
            raise NetworkBlocked(f"network access in a harness test: {address!r}")
        return real_connect_ex(self, address)

    def getaddrinfo(host, *args, **kwargs):
        if not _is_loopback((host,)):
            raise NetworkBlocked(f"DNS lookup in a harness test: {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)

    mp = pytest.MonkeyPatch()
    mp.setattr(socket.socket, "connect", connect)
    mp.setattr(socket.socket, "connect_ex", connect_ex)
    mp.setattr(socket, "getaddrinfo", getaddrinfo)
    # The paid guard runs `git fetch origin main` in a subprocess, which the socket patch
    # cannot see. Tests point origin at a local bare repo; this makes git refuse any other
    # transport (https, ssh, git) outright.
    mp.setenv("GIT_ALLOW_PROTOCOL", "file")
    yield
    mp.undo()


@pytest.fixture(autouse=True)
def no_shared_paid_lock(monkeypatch, tmp_path_factory):
    """The paid CLI's lock and its last-run record live in the git common directory that
    every checkout shares (common/paidlock.py). No harness test may take that lock or write
    that record: one would block a real paid run, the other would make it refuse. Here the
    CLI's lock points into a directory that does not exist, so a test that reaches the lock
    without naming its own (`cli.LOCK_PATH`) fails instead. `account-run`'s ledger
    (`cli.COSTS_PATH`) points there too, so that no test appends to this checkout's
    results/costs.csv."""
    monkeypatch.setattr(cli, "LOCK_PATH", tmp_path_factory.getbasetemp()
                        / "no-shared-paid-lock" / paidlock.lock_name(cli.STREAM))
    monkeypatch.setattr(cli, "COSTS_PATH", tmp_path_factory.getbasetemp()
                        / "no-shared-paid-lock" / "costs.csv")


# --- a throwaway git repo with a committed PREREG.md (paid-guard tests) --------------------
# The helpers live in common/tests/gitrepo.py (shared with the common/approval.py tests).

def prereg_repo(path: Path, text: str = FROZEN_PREREG,
                approved_blocks: tuple[str, ...] = ("1-pilots",)) -> Path:
    """`path` as a git repo whose HEAD holds PREREG.md (default: frozen) and a
    results/decisions.md approving `approved_blocks`, with a local bare `origin` whose main
    equals HEAD (what the paid guard requires)."""
    return guarded_repo(path, prereg=text, decisions=decisions_text(*approved_blocks))


def text_with_tokens(prefix: str, n: int) -> str:
    """`prefix` padded with ' x' words to exactly n o200k_base tokens."""
    return padded_text(prefix, n)


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
