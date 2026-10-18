"""The Anthropic Messages transport (harnesses/anthropic_transport.py; PREREG §17.8, amendment
R8, not yet merged): its credentials refusal, its request-side check, its retries and hard
stops, and its ledger, echo log and costs row. No test here touches the network: the client
is a stub factory (`messages.stream` only; `messages.create` fails the test), and the guard,
the same as the OpenAI transport's (test_paid_guard.py), runs before the factory is called.
The environment's API key is a dummy name check: no test sets a real key or reads one."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import anthropic
import httpx2
import pytest

from common import costs, paidlock
from harnesses import anthropic_transport, paid_transport
from harnesses.anthropic_transport import (
    AnthropicMessagesTransport,
    credential_refusal,
    retry_decision,
)
from harnesses.openai_transport import ALLOW_ENV, PaidCallsNotAllowed
from harnesses.paid_transport import BudgetExceeded, ProviderHardStop
from harnesses.tests.conftest import SYSTEM, obs_text, prereg_repo
from harnesses.wire import RequestCheckFailed

HAIKU = "claude-haiku-5-5"
HARNESS_DIR = Path(__file__).resolve().parent.parent
REQ = httpx2.Request("POST", "https://example.invalid/v1/messages")


def _payload(**change):
    p = {"model": HAIKU, "system": SYSTEM,
         "messages": [{"role": "user", "content": [{"type": "text", "text": obs_text(0)}]}],
         "max_tokens": 32000, "thinking": {"type": "adaptive"},
         "output_config": {"effort": "medium"}, "cache_control": {"type": "ephemeral"}}
    p.update(change)
    return p


def _response(stop="end_turn", plain=1_000, read=0, write=0, out=200, thinking=150,
              tier="standard"):
    usage = {"input_tokens": plain, "cache_read_input_tokens": read,
             "cache_creation_input_tokens": write, "output_tokens": out, "service_tier": tier}
    if thinking is not None:
        usage["output_tokens_details"] = {"thinking_tokens": thinking}
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": HAIKU,
            "content": [{"type": "thinking", "thinking": "", "signature": "s"},
                        {"type": "text", "text": "ACTION: ack(none)"}],
            "stop_reason": stop, "stop_details": None, "usage": usage}


class _Message:
    def __init__(self, data):
        self.data = data

    def to_dict(self, mode="python"):
        assert mode == "json"
        return self.data


class _Stream:
    def __init__(self, outcome):
        self.outcome = outcome

    def __enter__(self):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return _Message(self.outcome)


class _StubClient:
    """`messages.stream(**payload)` returns the next outcome (a response or an error);
    `messages.create` fails the test."""

    def __init__(self, outcomes):
        self.sent, self._outcomes = [], list(outcomes)
        self.messages = self

    def stream(self, **payload):
        self.sent.append(payload)
        return _Stream(self._outcomes.pop(0))

    def create(self, **payload):
        raise AssertionError("the transport streams: the SDK refuses a non-streaming call at "
                             "max_tokens 32,000")


def _factory(outcomes=()):
    built = []

    def factory(timeout):
        built.append(_StubClient(outcomes))
        return built[-1]
    return factory, built


@pytest.fixture
def repo(tmp_path):
    prereg_repo(tmp_path)
    p = tmp_path / "costs.csv"
    p.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def key(monkeypatch):
    """An API key's variable set to a dummy (never a real key), the others unset."""
    monkeypatch.setenv(anthropic_transport.KEY_ENV, "dummy-not-a-key")
    for name in anthropic_transport.REFUSED_ENV:
        monkeypatch.delenv(name, raising=False)


def _held(repo) -> paidlock.HeldLock:
    path = repo.parent / f"{repo.name}-lock" / paidlock.lock_name(paidlock.PERSISTGYM)
    if not path.exists():
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"run_id": "test-run", "stream": paidlock.PERSISTGYM,
                                    "token": "test-token"}), encoding="utf-8")
    return paidlock.HeldLock(path, json.loads(path.read_text(encoding="utf-8")))


def _make(repo, factory, **kw):
    args = {"model": HAIKU, "approved_block": "1-pilots", "experiment": "persistgym_pilot",
            "planned_usd": 1.0, "costs_path": repo / "costs.csv", "repo": repo,
            "client_factory": factory, "sleep": lambda s: None, "paid_lock": _held(repo)}
    args.update(kw)
    return AnthropicMessagesTransport(**args)


def _status_error(cls, status, body=None, headers=None, message="error"):
    return cls(message, response=httpx2.Response(status, request=REQ, headers=headers or {}),
               body=body)


# --- credentials -----------------------------------------------------------------------------

SECRET = "value-never-shown"


@pytest.mark.parametrize("env, refused", [
    ({}, "ANTHROPIC_API_KEY is not set"),
    ({"ANTHROPIC_API_KEY": ""}, "ANTHROPIC_API_KEY is not set"),
    ({"ANTHROPIC_API_KEY": SECRET, "ANTHROPIC_AUTH_TOKEN": SECRET},
     "ANTHROPIC_AUTH_TOKEN is set"),
    ({"ANTHROPIC_API_KEY": SECRET, "ANTHROPIC_PROFILE": SECRET}, "ANTHROPIC_PROFILE is set"),
    ({"ANTHROPIC_API_KEY": SECRET, "ANTHROPIC_AUTH_TOKEN": ""}, "ANTHROPIC_AUTH_TOKEN is set"),
    ({"ANTHROPIC_API_KEY": SECRET, "ANTHROPIC_BASE_URL": SECRET}, "ANTHROPIC_BASE_URL is set"),
    ({"ANTHROPIC_API_KEY": SECRET, "ANTHROPIC_AUTH_TOKEN": SECRET, "ANTHROPIC_PROFILE": SECRET},
     "ANTHROPIC_AUTH_TOKEN, ANTHROPIC_PROFILE are set"),
    ({"ANTHROPIC_API_KEY": SECRET, "OPENAI_API_KEY": SECRET}, None)])
def test_credential_refusal(env, refused):
    """An API key only (CLAUDE.md), named, never shown."""
    why = credential_refusal(env)
    if refused is None:
        assert why is None
    else:
        assert refused in why and SECRET not in why


@pytest.mark.parametrize("env", [{}, {"ANTHROPIC_AUTH_TOKEN": "t"}, {"ANTHROPIC_PROFILE": "p"}])
def test_the_transport_refuses_on_credentials_before_the_guard_and_any_client(repo, monkeypatch,
                                                                               env):
    """CLAUDE.md: API keys only, never subscriptions or OAuth. The refusal comes before the
    guard, so it reserves no spend, and before any client exists."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    for name in (anthropic_transport.KEY_ENV, *anthropic_transport.REFUSED_ENV):
        monkeypatch.delenv(name, raising=False)
    if env:
        monkeypatch.setenv(anthropic_transport.KEY_ENV, "dummy-not-a-key")
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    def no_guard(**kw):
        raise AssertionError("the guard must not run")
    monkeypatch.setattr(paid_transport, "require_paid_run", no_guard)
    factory, built = _factory()
    with pytest.raises(PaidCallsNotAllowed, match="no paid call was made"):
        _make(repo, factory)
    assert built == []


def test_the_guard_still_refuses_with_a_key(repo, monkeypatch, key):
    monkeypatch.delenv(ALLOW_ENV, raising=False)
    factory, built = _factory()
    with pytest.raises(PaidCallsNotAllowed, match=ALLOW_ENV):
        _make(repo, factory)
    assert built == []


def test_no_key_value_is_handled_in_harness_code():
    """The SDK reads the key from the environment; harness code names the variable only to
    check that it is set, in the Anthropic transport, and never passes a key to a client."""
    literal = re.compile(r"""["']ANTHROPIC_[A-Z_]+["']""")
    for path in HARNESS_DIR.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert "api_key" not in src and "auth_token" not in src, path.name
        if path.name != "anthropic_transport.py":
            assert not literal.search(src), path.name  # docstrings may name it, code not
    src = (HARNESS_DIR / "anthropic_transport.py").read_text(encoding="utf-8")
    assert literal.findall(src) == ['"ANTHROPIC_API_KEY"', '"ANTHROPIC_AUTH_TOKEN"',
                                    '"ANTHROPIC_PROFILE"', '"ANTHROPIC_BASE_URL"']
    assert "env.get(KEY_ENV)" in src and src.count("KEY_ENV") == 4  # one presence check


def test_the_default_client_streams_with_the_sdks_retries_off(monkeypatch, repo, key):
    """anthropic.Anthropic(max_retries=0, timeout=<the transport's>); no key is passed."""
    built = []

    def fake_anthropic(**kw):
        built.append(kw)
        return _StubClient([_response()])
    monkeypatch.setenv(ALLOW_ENV, "1")
    monkeypatch.setattr(anthropic, "Anthropic", fake_anthropic)
    t = _make(repo, None, timeout_s=900.0)
    assert built == [{"max_retries": 0, "timeout": 900.0}]
    t.send(_payload())
    assert t.ledger.n_calls == 1


# --- the request-side check ------------------------------------------------------------------

@pytest.mark.parametrize("payload, problem", [
    (_payload(output_config={"effort": "high"}), "output_config"),
    (_payload(max_tokens=16000), "max_tokens 16000"),
    (_payload(thinking={"type": "disabled"}), "thinking"),
    (_payload(temperature=1.0), "temperature"),
    (_payload(messages=[{"role": "user", "content": [{"type": "text", "text": "a"}]},
                        {"role": "assistant", "content": [
                            {"type": "thinking", "thinking": "", "signature": "s"},
                            {"type": "text", "text": "b"}]},
                        {"role": "user", "content": [{"type": "text", "text": "c"}]}]),
     "1 thinking blocks")])
def test_a_payload_that_fails_the_request_side_check_is_never_sent(repo, monkeypatch, key,
                                                                   payload, problem):
    """The registered effort (medium), D13's 32,000 cap, adaptive thinking and no thinking
    block in the history, on every call: the substitute for the echo checks."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, built = _factory([_response()])
    t = _make(repo, factory)
    with pytest.raises(RequestCheckFailed, match=problem):
        t.send(payload)
    assert built[0].sent == [] and t.ledger.n_calls == 0 and t._in_flight == 0
    t.send(_payload())
    assert len(built[0].sent) == 1


# --- one call: ledger, echo log, costs row -----------------------------------------------------

def test_send_records_usage_echo_and_the_costs_row(repo, monkeypatch, key, caplog):
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, built = _factory([_response(plain=10, read=90_000, write=9_990, out=500),
                               _response(stop="max_tokens", plain=11, read=90_000, write=9_990,
                                         out=32_000, thinking=None, tier="priority")])
    t = _make(repo, factory, experiment="toggle_pilot")
    with caplog.at_level("INFO", logger="harnesses.anthropic"):
        assert t.send(_payload())["stop_reason"] == "end_turn"
        t.send(_payload())
    assert built[0].sent == [_payload(), _payload()]
    first, second = t.echo_log
    assert {k: first[k] for k in ("requested_context", "echoed_context", "requested_effort",
                                  "echoed_effort", "service_tier_requested",
                                  "service_tier_returned", "status", "stop_reason",
                                  "prompt_tokens")} == {
        "requested_context": None, "echoed_context": None, "requested_effort": "medium",
        "echoed_effort": None, "service_tier_requested": "standard",
        "service_tier_returned": "standard", "status": "completed", "stop_reason": "end_turn",
        "prompt_tokens": 100_000}
    assert (second["status"], second["incomplete_reason"]) == ("incomplete",
                                                               "max_output_tokens")
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert warnings == [
        "served on tier priority, not standard: priced at the standard tier's prices",
        "prompt of 100001 tokens is over 100000: priced at the dearer card",
        "incomplete response (reason=max_output_tokens, max_tokens=32000)"]
    # 100,000 tokens at the <= 100k card, 100,001 at the > 100k card
    low = (10 * 0.10 + 90_000 * 0.01 + 9_990 * 0.125 + 500 * 0.50) / 1e6
    high = (11 * 0.50 + 90_000 * 0.05 + 9_990 * 0.625 + 32_000 * 2.50) / 1e6
    assert t.ledger.cost_usd_list == pytest.approx(low + high) == t.spent_usd
    row = t.finalize(run_id="r1", milestone="M1", cell_or_config="F-0")
    assert (row["provider"], row["api"], row["service_tier"], row["service_tier_served"]) == (
        "anthropic", "messages", "standard", "priority;standard")
    assert row["price_source_date"] == "2026-10-17" and row["reasoning_tokens"] == ""
    assert row["input_tokens"] == 200_001 and row["cached_input_tokens"] == 180_000
    assert row["cache_write_tokens"] == 19_980 and row["output_tokens"] == 32_500
    assert row["cost_usd_list"] == row["cost_usd_billed_est"]
    assert row["notes"].startswith("approved_block=1-pilots; context_mismatches=n/a; "
                                   "effort_mismatches=n/a; git_dirty=")
    assert "max_prompt_tokens=100001; calls_over_100000=1" in row["notes"]
    assert costs.read_rows(repo / "costs.csv")[0]["api"] == "messages"


def test_a_blinded_pilot_logs_no_status_or_stop_reason(repo, monkeypatch, key, caplog):
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, _ = _factory([_response(stop="refusal"), _response()])
    t = _make(repo, factory, experiment="persistgym_pilot")
    with caplog.at_level("INFO", logger="harnesses.anthropic"):
        t.send(_payload())
        t.send(_payload())
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "refusal" not in text and "end_turn" not in text and "incomplete" not in text
    assert text.count("stop_reason=withheld status=withheld") == 2
    row = t.finalize(run_id="r1", milestone="M1", cell_or_config="F-0")
    assert row["reasoning_tokens"] == ""  # PREREG §11


def test_the_stop_at_the_planned_spend(repo, monkeypatch, key):
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, built = _factory([_response(plain=0, out=1_000_000)] * 5)  # $0.50 each
    t = _make(repo, factory, planned_usd=1.0)
    t.send(_payload())
    t.send(_payload())
    with pytest.raises(BudgetExceeded):
        t.send(_payload())
    assert len(built[0].sent) == 2


# --- retries and hard stops ---------------------------------------------------------------------

SPEND_LIMIT = {"type": "error", "error": {"type": "rate_limit_error", "message": "spend",
                                          "details": {"error_code":
                                                      "enforced_spend_limit_reached"}}}


@pytest.mark.parametrize("error, decision", [
    (_status_error(anthropic.RateLimitError, 429), ("retry", None)),
    (_status_error(anthropic.RateLimitError, 429, headers={"retry-after": "7"}), ("retry", 7.0)),
    (_status_error(anthropic.RateLimitError, 429, body=SPEND_LIMIT), ("hard_stop", None)),
    (_status_error(anthropic.InternalServerError, 500), ("retry", None)),
    (_status_error(anthropic.InternalServerError, 502), ("retry", None)),
    (_status_error(anthropic.InternalServerError, 503), ("retry", None)),
    (_status_error(anthropic.InternalServerError, 504), ("retry", None)),
    (_status_error(anthropic.OverloadedError, 529), ("retry", None)),
    (_status_error(anthropic.OverloadedError, 529, headers={"retry-after": "3"}),
     ("retry", None)),
    (anthropic.APITimeoutError(request=REQ), ("retry", None)),
    (anthropic.APIConnectionError(request=REQ), ("retry", None)),
    (_status_error(anthropic.APIStatusError, 200,
                   body={"type": "error", "error": {"type": "overloaded_error"}}),
     ("retry", None)),
    (_status_error(anthropic.APIStatusError, 200,
                   body={"type": "error", "error": {"type": "invalid_request_error"}}),
     ("raise", None)),
    (_status_error(anthropic.BadRequestError, 400), ("raise", None)),
    (_status_error(anthropic.BadRequestError, 400,
                   message="You have reached your specified API usage limits."),
     ("hard_stop", None)),
    (_status_error(anthropic.AuthenticationError, 401), ("raise", None)),
    (_status_error(anthropic.PermissionDeniedError, 403), ("raise", None)),
    (_status_error(anthropic.NotFoundError, 404), ("raise", None)),
    (_status_error(anthropic.RequestTooLargeError, 413), ("raise", None)),
    (ValueError("not an API error"), ("raise", None))])
def test_retry_decision(error, decision):
    assert retry_decision(error) == decision


def test_retries_then_gives_up_and_429s_respect_retry_after(repo, monkeypatch, key):
    monkeypatch.setenv(ALLOW_ENV, "1")
    waits = []
    busy = _status_error(anthropic.RateLimitError, 429, headers={"retry-after": "7"})
    over = _status_error(anthropic.OverloadedError, 529)
    factory, built = _factory([busy, over, _response()])
    t = _make(repo, factory, max_attempts=3, sleep=waits.append, backoff_s=5.0)
    assert t.send(_payload())["model"] == HAIKU
    assert len(built[0].sent) == 3 and t.ledger.n_calls == 1 and waits == [7.0, 10.0]
    factory, _ = _factory([over, over])
    t = _make(repo, factory, max_attempts=2)
    with pytest.raises(anthropic.OverloadedError):
        t.send(_payload())
    assert t.ledger.n_calls == 0


@pytest.mark.parametrize("error", [_status_error(anthropic.BadRequestError, 400),
                                   _status_error(anthropic.NotFoundError, 404)])
def test_other_4xx_are_never_retried(repo, monkeypatch, key, error):
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, built = _factory([error, _response()])
    t = _make(repo, factory)
    with pytest.raises(type(error)):
        t.send(_payload())
    assert len(built[0].sent) == 1


@pytest.mark.parametrize("error", [
    _status_error(anthropic.RateLimitError, 429, body=SPEND_LIMIT),
    _status_error(anthropic.BadRequestError, 400,
                  message="You have reached your specified API usage limits.")])
def test_spend_and_usage_limits_are_hard_stops(repo, monkeypatch, key, error, small_eps,
                                               tmp_path):
    """Never retried, and not an episode's API_ERROR: the run stops at once."""
    from harnesses.cells import CELLS
    from harnesses.config import HarnessConfig
    from harnesses.runner import run_batch

    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, built = _factory([error, _response()])
    t = _make(repo, factory)
    with pytest.raises(ProviderHardStop, match="refuses further spend"):
        t.send(_payload())
    assert len(built[0].sent) == 1 and t._in_flight == 0
    assert not isinstance(ProviderHardStop("x"), anthropic.AnthropicError)
    t.finalize(run_id="r0", milestone="M1", cell_or_config="F-0")
    factory, built = _factory([error])
    t = _make(repo, factory)
    cfg = HarnessConfig(model=HAIKU, service_tier="standard")
    with pytest.raises(ProviderHardStop):
        run_batch(small_eps[:2], CELLS["F-0"], cfg, t, experiment="persistgym_pilot",
                  run_id="hard", results_root=tmp_path / "r", raw_root=tmp_path / "raw")
    meta = json.loads((tmp_path / "r" / "persistgym_pilot" / "hard" / "meta.json")
                      .read_text(encoding="utf-8"))
    assert meta["exit_reason"] == "ERROR:ProviderHardStop" and len(built[0].sent) == 1


def test_an_api_error_after_retries_is_the_episodes_api_error(repo, monkeypatch, key,
                                                             small_eps, tmp_path):
    from harnesses.cells import CELLS
    from harnesses.config import HarnessConfig
    from harnesses.runner import run_episode

    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, _ = _factory([_status_error(anthropic.BadRequestError, 400)])
    t = _make(repo, factory)
    run = run_episode(small_eps[0], CELLS["F-0"], HarnessConfig(model=HAIKU,
                                                                service_tier="standard"), t)
    assert run.exit_reason == "API_ERROR" and run.error.startswith("BadRequestError")
    assert logging.getLogger("harnesses.anthropic") is anthropic_transport.log


def test_harness_tests_cannot_reach_anthropic():
    """conftest.no_network blocks Anthropic's API as it blocks OpenAI's."""
    import socket

    from harnesses.tests.conftest import NetworkBlocked
    with pytest.raises(NetworkBlocked):
        socket.getaddrinfo("api.anthropic.com", 443)
    with pytest.raises(NetworkBlocked):
        socket.create_connection(("api.anthropic.com", 443), timeout=1)
