"""The Anthropic Messages transport (harnesses/anthropic_transport.py; PREREG §17.8, amendment
R8, not yet merged): its credentials, model and approval refusals, its request-side check,
its retries and hard stops (a stream that fails part way included), and its ledger, echo log
and costs row (inference geo, refusals, failed attempts). No test here touches the network:
the client is a stub factory (`messages.stream` only; `messages.create` fails the test), or
the real SDK client on an in-process `httpx2.MockTransport` that serves server-sent events,
and the guard, the same as the OpenAI transport's (test_paid_guard.py), runs before the
factory is called. The environment's API key is a dummy name check: no test sets a real key
or reads one."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import anthropic
import httpx2
import pytest

from common import costs, paidlock
from common.tests.gitrepo import FROZEN_PREREG, approval_line, decisions_text, guarded_repo
from harnesses import anthropic_transport, paid_transport
from harnesses.anthropic_transport import (
    AnthropicMessagesTransport,
    client_header_refusal,
    credential_refusal,
    retry_decision,
)
from harnesses.openai_transport import ALLOW_ENV, PaidCallsNotAllowed
from harnesses.paid_transport import BudgetExceeded, ProviderHardStop
from harnesses.tests.conftest import SYSTEM, obs_text
from harnesses.wire import RequestCheckFailed

HAIKU = "claude-haiku-5-5"
HARNESS_DIR = Path(__file__).resolve().parent.parent
REQ = httpx2.Request("POST", "https://example.invalid/v1/messages")
HAIKU_BLOCK = "4-haiku"
"""The test repo's approval line for the Haiku replication: it lists persistgym_haiku (the
transport refuses a block that does not), and toggle_pilot for an unblinded run."""
HAIKU_BLOCK_EXPERIMENTS = ("toggle_pilot", "persistgym_pilot", "persistgym_validity",
                           "persistgym_haiku")


def _payload(**change):
    p = {"model": HAIKU, "system": SYSTEM,
         "messages": [{"role": "user", "content": [{"type": "text", "text": obs_text(0)}]}],
         "max_tokens": 32000, "thinking": {"type": "adaptive"},
         "output_config": {"effort": "medium"}, "cache_control": {"type": "ephemeral"}}
    p.update(change)
    return p


def _response(stop="end_turn", plain=1_000, read=0, write=0, out=200, thinking=150,
              tier="standard", geo="global"):
    usage = {"input_tokens": plain, "cache_read_input_tokens": read,
             "cache_creation_input_tokens": write, "output_tokens": out, "service_tier": tier,
             "inference_geo": geo}
    if geo is None:
        del usage["inference_geo"]
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
    """A frozen PREREG and three approval lines: blocks 1-pilots (toggle_pilot, replay_probe,
    persistgym_pilot) and 3-persistgym (persistgym, persistgym_pilot), approved before the
    Haiku replication, as results/decisions.md's are, and `HAIKU_BLOCK`."""
    guarded_repo(tmp_path, prereg=FROZEN_PREREG, decisions=decisions_text("1-pilots")
                 + approval_line("3-persistgym", ("persistgym", "persistgym_pilot")) + "\n"
                 + approval_line(HAIKU_BLOCK, HAIKU_BLOCK_EXPERIMENTS) + "\n")
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
    args = {"model": HAIKU, "approved_block": HAIKU_BLOCK, "experiment": "persistgym_pilot",
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
    ({"ANTHROPIC_API_KEY": SECRET, "ANTHROPIC_CUSTOM_HEADERS": f"Authorization: Bearer {SECRET}"},
     "ANTHROPIC_CUSTOM_HEADERS is set"),
    ({"ANTHROPIC_API_KEY": SECRET, "ANTHROPIC_CUSTOM_HEADERS": ""},
     "ANTHROPIC_CUSTOM_HEADERS is set"),
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


@pytest.mark.parametrize("env", [{}, {"ANTHROPIC_AUTH_TOKEN": "t"}, {"ANTHROPIC_PROFILE": "p"},
                                 {"ANTHROPIC_CUSTOM_HEADERS": "anthropic-beta: b"}])
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
                                    '"ANTHROPIC_PROFILE"', '"ANTHROPIC_BASE_URL"',
                                    '"ANTHROPIC_CUSTOM_HEADERS"']
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


def test_a_client_that_holds_custom_headers_refuses(monkeypatch, repo, key):
    """The backstop behind ANTHROPIC_CUSTOM_HEADERS's refusal: the SDK sends its custom
    headers after its auth headers, so they could replace the key or add an OAuth or beta
    header. A built client that holds any refuses, naming the headers, never their values;
    the refusal comes after the guard, which then releases the spend reservation."""
    assert client_header_refusal(anthropic.Anthropic(max_retries=0)) is None
    monkeypatch.setenv("ANTHROPIC_CUSTOM_HEADERS",
                       f"X-Api-Key: {SECRET}\nAuthorization: Bearer {SECRET}\nanthropic-beta: b")
    why = client_header_refusal(anthropic.Anthropic(max_retries=0))
    assert "Authorization, X-Api-Key, anthropic-beta" in why and SECRET not in why
    monkeypatch.setenv(ALLOW_ENV, "1")
    monkeypatch.setattr(anthropic_transport, "credential_refusal", lambda: None)
    with pytest.raises(PaidCallsNotAllowed, match="custom headers .*no paid call was made"):
        _make(repo, None)
    reservation = paidlock.reservation_path(_held(repo).path, paidlock.PERSISTGYM)
    assert not reservation.exists()
    monkeypatch.delenv("ANTHROPIC_CUSTOM_HEADERS")
    factory, _ = _factory([_response()])
    _make(repo, factory).send(_payload())  # no reservation left behind to refuse it


@pytest.mark.parametrize("model", ["claude-haiku-5-5-latest", "claude-sonnet-5",
                                   "claude-haiku-4-5"])
def test_the_transport_sends_haiku_only_and_refuses_before_the_guard(repo, monkeypatch, key,
                                                                     model):
    """R8 registers claude-haiku-5-5 only; any other claude-* string, priced by prefix or
    not at all, refuses before the guard reserves anything."""
    monkeypatch.setenv(ALLOW_ENV, "1")

    def no_guard(**kw):
        raise AssertionError("the guard must not run")
    monkeypatch.setattr(paid_transport, "require_paid_run", no_guard)
    factory, built = _factory()
    with pytest.raises(PaidCallsNotAllowed, match=f"claude-haiku-5-5 only .*got model {model}"):
        _make(repo, factory, model=model)
    assert built == []


@pytest.mark.parametrize("block, listed", [
    ("1-pilots", "toggle_pilot, replay_probe, persistgym_pilot"),
    ("3-persistgym", "persistgym, persistgym_pilot")])
def test_a_block_that_does_not_list_persistgym_haiku_refuses(repo, monkeypatch, key, block,
                                                             listed):
    """A Haiku run, its pilots included, needs an approval line written for the Haiku
    replication (it lists persistgym_haiku), never a block approved before Anthropic was in
    the plan (both list persistgym_pilot, so the guard alone lets the pilot through). The
    refusal comes after the guard, before any client, and releases the spend reservation,
    so the next run is not refused for it."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, built = _factory([_response()])
    with pytest.raises(PaidCallsNotAllowed, match=f"block '{block}' lists {listed}, not "
                                                  "persistgym_haiku.*no paid call was made"):
        _make(repo, factory, approved_block=block)
    assert built == []
    assert not paidlock.reservation_path(_held(repo).path, paidlock.PERSISTGYM).exists()
    _make(repo, factory).send(_payload())
    assert len(built) == 1


def test_an_unpriced_model_releases_the_reservation(repo, monkeypatch, key):
    """Any failure after the guard and before the first call releases the reservation (the
    OpenAI transport shares this code; an unpriced model raises KeyError there)."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    monkeypatch.setattr(AnthropicMessagesTransport, "_preflight", lambda self: None)
    factory, built = _factory([_response()])
    with pytest.raises(KeyError):
        _make(repo, factory, model="claude-sonnet-5")
    assert built == []
    assert not paidlock.reservation_path(_held(repo).path, paidlock.PERSISTGYM).exists()


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
    assert row["notes"].startswith(f"approved_block={HAIKU_BLOCK}; context_mismatches=n/a; "
                                   "effort_mismatches=n/a; git_dirty=")
    assert "max_prompt_tokens=100001; calls_over_100000=1" in row["notes"]
    assert "inference_geos=global:2" in row["notes"]
    assert "unbilled_refusals" not in row["notes"] and "failed_attempts" not in row["notes"]
    assert costs.read_rows(repo / "costs.csv")[0]["api"] == "messages"


def test_a_call_not_served_in_the_global_geo_costs_more_and_warns(repo, monkeypatch, key,
                                                                 caplog):
    """US-only inference costs 1.1x every price; a geo not reported is priced so too (the
    estimate errs high). Each such call warns, and the costs row counts the calls per geo."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, _ = _factory([_response(geo="us"), _response(geo=None), _response()])
    t = _make(repo, factory, experiment="toggle_pilot")
    with caplog.at_level("INFO", logger="harnesses.anthropic"):
        for _ in range(3):
            t.send(_payload())
    one = (1_000 * 0.10 + 200 * 0.50) / 1e6
    assert [e["cost_usd_list"] for e in t.echo_log] == pytest.approx([one * 1.1, one * 1.1, one])
    assert [e["inference_geo"] for e in t.echo_log] == ["us", None, "global"]
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert warnings == ["served in inference geo us, not global: priced at 1.1x",
                        "served in inference geo None, not global: priced at 1.1x"]
    assert t.spent_usd == pytest.approx(one * 3.2)
    row = t.finalize(run_id="r1", milestone="M1", cell_or_config="F-0")
    assert "inference_geos=None:1;global:1;us:1" in row["notes"]


def _refusal(category):
    """A refusal before any output, as documented (empty content, no output_tokens_details;
    https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback)."""
    return {"id": "msg_r", "type": "message", "role": "assistant", "model": HAIKU,
            "content": [], "stop_reason": "refusal",
            "stop_details": {"type": "refusal", "category": category, "explanation": "x"},
            "usage": {"input_tokens": 412, "output_tokens": 0, "service_tier": "standard",
                      "inference_geo": "global"}}


def test_refusals_before_any_output_keep_reasoning_tokens_and_bill_by_category(repo,
                                                                                monkeypatch,
                                                                                key):
    """A refusal before any output has 0 thinking tokens (not unknown: the run's total
    stays), and only the billed categories count toward the spend; the list cost keeps
    every one."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, _ = _factory([_response(), _refusal("cyber"), _refusal("bio"), _refusal(None)])
    t = _make(repo, factory, experiment="toggle_pilot")
    for _ in range(4):
        t.send(_payload())
    one, refused = (1_000 * 0.10 + 200 * 0.50) / 1e6, 412 * 0.10 / 1e6
    assert t.ledger.reasoning_tokens == 150
    assert t.ledger.cost_usd_list == pytest.approx(one + 3 * refused)
    assert t.ledger.cost_usd_billed_est == pytest.approx(one + refused) == t.spent_usd
    assert t.ledger.unbilled_refusals == 2
    row = t.finalize(run_id="r1", milestone="M1", cell_or_config="F-0")
    assert row["reasoning_tokens"] == 150 and "not reported" not in row["notes"]
    assert "unbilled_refusals=2" in row["notes"]
    assert float(row["cost_usd_billed_est"]) < float(row["cost_usd_list"])


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


# --- a stream that fails part way: the real SDK on an in-process mock transport -------------

def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def _start(plain=30_000, geo="global"):
    """message_start: the attempt's input usage, known before any output."""
    return _sse("message_start", {"type": "message_start", "message": {
        "id": "msg_1", "type": "message", "role": "assistant", "model": HAIKU, "content": [],
        "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": plain, "cache_read_input_tokens": 0,
                  "cache_creation_input_tokens": 0, "output_tokens": 1,
                  "service_tier": "standard", "inference_geo": geo}}})


TEXT = [_sse("content_block_start", {"type": "content_block_start", "index": 0,
                                     "content_block": {"type": "text", "text": ""}}),
        _sse("content_block_delta", {"type": "content_block_delta", "index": 0,
                                     "delta": {"type": "text_delta",
                                               "text": "ACTION: ack(none)"}}),
        _sse("content_block_stop", {"type": "content_block_stop", "index": 0})]
END = [_sse("message_delta", {"type": "message_delta",
                              "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                              "usage": {"output_tokens": 20,
                                        "output_tokens_details": {"thinking_tokens": 0}}}),
       _sse("message_stop", {"type": "message_stop"})]
OVERLOADED = _sse("error", {"type": "error", "error": {"type": "overloaded_error",
                                                       "message": "Overloaded"}})


def _whole(plain=30_000):
    return [_start(plain), *TEXT, *END]


class _Body(httpx2.SyncByteStream):
    """A 200 event stream's body: its chunks, then optionally an error, as a connection that
    drops (RemoteProtocolError, ReadError) or stalls (ReadTimeout) part way raises it."""

    def __init__(self, chunks, drop=None):
        self.chunks, self.drop = chunks, drop

    def __iter__(self):
        yield from self.chunks
        if self.drop is not None:
            raise self.drop


def _sdk_factory(bodies):
    """The real SDK client, built as the transport builds it, on an in-process mock transport
    (no network): each request gets the next body as a 200 `text/event-stream`."""
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx2.Response(200, headers={"content-type": "text/event-stream"},
                               stream=bodies.pop(0))

    def factory(timeout):
        return anthropic.Anthropic(max_retries=0, timeout=timeout, http_client=httpx2.Client(
            transport=httpx2.MockTransport(handler)))
    return factory, sent


DROPS = [httpx2.RemoteProtocolError("peer closed connection without sending complete message "
                                    "body"),
         httpx2.ReadError("connection reset"), httpx2.ReadTimeout("read timed out")]


@pytest.mark.parametrize("drop", DROPS, ids=lambda e: type(e).__name__)
def test_a_stream_that_drops_part_way_is_retried_and_its_usage_recorded(repo, monkeypatch, key,
                                                                        drop):
    """After the 200 headers the SDK raises the raw httpx2 error, which the transport raises
    as anthropic.APIConnectionError: retried with the backoff. The failed attempt's input,
    reported by message_start, is in the ledger as a failed attempt (not in n_calls)."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    waits = []
    factory, sent = _sdk_factory([_Body([_start(30_000), TEXT[0]], drop=drop),
                                  _Body(_whole(30_000))])
    t = _make(repo, factory, sleep=waits.append, backoff_s=5.0)
    data = t.send(_payload())
    assert data["stop_reason"] == "end_turn" and len(sent) == 2 and waits == [5.0]
    assert sent[0] == sent[1] == {**_payload(), "stream": True}  # the same body, resent
    assert (t.ledger.n_calls, t.ledger.failed_attempts) == (1, 1)
    assert t.ledger.input_tokens == 60_000 and t.ledger.output_tokens == 21
    assert t.ledger.reasoning_tokens == 0  # the failed attempt adds none, nor blanks them
    assert t.spent_usd == pytest.approx((60_000 * 0.10 + 21 * 0.50) / 1e6)
    row = t.finalize(run_id="r1", milestone="M1", cell_or_config="F-0")
    assert row["n_calls"] == 1 and row["input_tokens"] == 60_000
    assert "failed_attempts_with_usage=1" in row["notes"]


def test_a_stream_that_keeps_dropping_ends_the_episode_api_error(repo, monkeypatch, key,
                                                                 small_eps):
    """After the last attempt a dropped stream is the episode's API_ERROR, as any other API
    error after the retries: it never escapes run_episode to stop the whole run."""
    from harnesses.cells import CELLS
    from harnesses.config import HarnessConfig
    from harnesses.runner import API_ERRORS, run_episode

    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, sent = _sdk_factory([_Body([_start()], drop=httpx2.RemoteProtocolError("drop"))
                                  for _ in range(3)])
    t = _make(repo, factory, max_attempts=3)
    run = run_episode(small_eps[0], CELLS["F-0"], HarnessConfig(model=HAIKU,
                                                                service_tier="standard"), t)
    assert run.exit_reason == "API_ERROR" and run.error.startswith("APIConnectionError")
    assert "RemoteProtocolError" in run.error and len(sent) == 3
    assert (t.ledger.n_calls, t.ledger.failed_attempts) == (0, 3) and t.spent_usd > 0
    assert issubclass(anthropic.APIConnectionError, API_ERRORS)


def test_a_stream_that_ends_before_its_message_delta_is_retried_not_scored(repo, monkeypatch,
                                                                         key):
    """A clean end of the body without message_delta gives a message with no stop_reason:
    a transport truncation, not the model's invalid action. It is raised and retried."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, sent = _sdk_factory([_Body([_start(), *TEXT]), _Body(_whole())])
    t = _make(repo, factory)
    assert t.send(_payload())["stop_reason"] == "end_turn" and len(sent) == 2
    assert (t.ledger.n_calls, t.ledger.failed_attempts) == (1, 1)
    factory, _ = _sdk_factory([_Body([_start(), *TEXT])])
    t = _make(repo, factory, max_attempts=1)
    with pytest.raises(anthropic.APIConnectionError, match="before its message_delta"):
        t.send(_payload())
    assert t.ledger.n_calls == 0 and t.ledger.failed_attempts == 1


def test_error_events_after_message_start_are_retried_and_each_attempts_input_counted(
        repo, monkeypatch, key):
    """Two overloaded_error events inside the stream, then a whole message: three prompts'
    input are in the spend, the stop at the planned spend and the costs row."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, sent = _sdk_factory([_Body([_start(30_000), OVERLOADED]),
                                  _Body([_start(30_000), TEXT[0], OVERLOADED]),
                                  _Body(_whole(30_000))])
    t = _make(repo, factory)
    assert t.send(_payload())["stop_reason"] == "end_turn" and len(sent) == 3
    assert (t.ledger.n_calls, t.ledger.failed_attempts) == (1, 2)
    assert t.ledger.input_tokens == 90_000
    assert t.ledger.cost_usd_list == pytest.approx((90_000 * 0.10 + 22 * 0.50) / 1e6)
    row = t.finalize(run_id="r1", milestone="M1", cell_or_config="F-0")
    assert "failed_attempts_with_usage=2" in row["notes"] and row["input_tokens"] == 90_000


def test_an_error_before_message_start_records_no_usage(repo, monkeypatch, key):
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, sent = _sdk_factory([_Body([], drop=httpx2.RemoteProtocolError("drop")),
                                  _Body(_whole(1_000))])
    t = _make(repo, factory)
    t.send(_payload())
    assert len(sent) == 2 and t.ledger.failed_attempts == 0 and t.ledger.input_tokens == 1_000


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
