"""The paid transport refuses to run without explicit approval, and logs what it spends.
No test here touches the network: the OpenAI client is replaced by a stub factory, and the
guard is checked to run before the factory is ever called."""

from __future__ import annotations

import csv
from pathlib import Path

import httpx
import openai
import pytest

from common import costs
from harnesses import cli
from harnesses.openai_transport import (
    ALLOW_ENV,
    BudgetExceeded,
    OpenAIResponsesTransport,
    PaidCallsNotAllowed,
)
from harnesses.pricing import cost_usd

HARNESS_DIR = Path(__file__).resolve().parent.parent


class _Resp:
    def __init__(self, data):
        self.data = data

    def to_dict(self, mode="python"):
        return self.data


class _StubClient:
    def __init__(self, responses):
        self.sent, self._responses = [], list(responses)
        self.responses = self

    def create(self, **payload):
        self.sent.append(payload)
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return _Resp(r)


def _response(context="all_turns", tier="flex", inp=1_000_000, out=100_000):
    return {"model": "gpt-6-luna-2026-09-01", "service_tier": tier, "status": "completed",
            "reasoning": {"context": context, "effort": "medium", "mode": "standard"},
            "output": [], "usage": {"input_tokens": inp, "output_tokens": out,
                                    "input_tokens_details": {"cached_tokens": 0},
                                    "output_tokens_details": {"reasoning_tokens": 50_000}}}


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "PREREG.md").write_text("Version: 0.1\n", encoding="utf-8")
    p = tmp_path / "costs.csv"
    p.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    return tmp_path


def _make(repo, factory, **kw):
    args = {"model": "gpt-6-luna", "approved_block": "1-pilots", "experiment": "toggle_pilot",
            "planned_usd": 1.0, "costs_path": repo / "costs.csv", "repo": repo,
            "client_factory": factory, "sleep": lambda s: None}
    args.update(kw)
    return OpenAIResponsesTransport(**args)


def _factory(responses=()):
    built = []

    def factory(timeout):
        built.append(_StubClient(responses))
        return built[-1]
    return factory, built


@pytest.mark.parametrize("env, kw, msg", [
    (None, {}, ALLOW_ENV),
    ("0", {}, ALLOW_ENV),
    ("1", {"approved_block": None}, "approved-block"),
    ("1", {"approved_block": "  "}, "approved-block"),
    ("1", {"planned_usd": 0}, "planned"),
    ("1", {"experiment": "mystery"}, "budget phase"),
    ("1", {"planned_usd": 100.01}, "cap"),  # phase 0 cap is $100
])
def test_guard_refuses_before_building_a_client(repo, monkeypatch, env, kw, msg):
    if env is None:
        monkeypatch.delenv(ALLOW_ENV, raising=False)
    else:
        monkeypatch.setenv(ALLOW_ENV, env)
    factory, built = _factory()
    with pytest.raises(PaidCallsNotAllowed, match=msg):
        _make(repo, factory, **kw)
    assert built == []


def test_guard_requires_prereg(repo, monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")
    (repo / "PREREG.md").unlink()
    factory, built = _factory()
    with pytest.raises(PaidCallsNotAllowed, match="PREREG"):
        _make(repo, factory)
    assert built == []


def test_guard_counts_logged_spend(repo, monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")
    row = {c: "" for c in costs.COLUMNS}
    row.update(experiment="replay_probe", cost_usd_list="99.5", cost_usd_billed_est="49.75")
    costs.append_row(row, repo / "costs.csv")
    factory, _ = _factory()
    with pytest.raises(PaidCallsNotAllowed, match="cap"):
        _make(repo, factory, planned_usd=0.6)  # 100 - 99.5 - 0.6 < 0
    assert _make(repo, factory, planned_usd=0.4).approval.headroom_usd == pytest.approx(0.1)


def test_sends_logs_echo_and_appends_one_costs_row(repo, monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, built = _factory([_response(), _response(context="current_turn")])
    t = _make(repo, factory)
    payload = {"model": "gpt-6-luna", "input": [], "reasoning": {"context": "all_turns"}}
    t.send(payload)
    t.send(payload)
    assert built[0].sent == [payload, payload]
    assert [e["echoed_context"] for e in t.echo_log] == ["all_turns", "current_turn"]
    assert t.echo_log[0]["model_returned"] == "gpt-6-luna-2026-09-01"
    row = t.finalize(run_id="r1", milestone="M0", cell_or_config="echo-probe")
    assert t.finalize(run_id="r1", milestone="M0", cell_or_config="echo-probe") is None
    rows = costs.read_rows(repo / "costs.csv")
    assert len(rows) == 1 and rows[0]["run_id"] == "r1"
    assert rows[0]["model_returned"] == "gpt-6-luna-2026-09-01"
    assert rows[0]["service_tier"] == "flex" and rows[0]["n_calls"] == "2"
    assert "approved_block=1-pilots" in rows[0]["notes"]
    assert "context_mismatches=1" in rows[0]["notes"]
    # 1M input at $0.10 + 100k output at $0.50 = $0.15 list per call; flex halves it
    assert float(rows[0]["cost_usd_list"]) == pytest.approx(0.30)
    assert float(rows[0]["cost_usd_billed_est"]) == pytest.approx(0.15)
    assert row["experiment"] == "toggle_pilot"
    with (repo / "costs.csv").open(newline="", encoding="utf-8") as f:
        assert next(csv.reader(f)) == costs.COLUMNS


def test_stops_at_planned_spend(repo, monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, built = _factory([_response(inp=10_000_000)] * 3)  # $0.525 billed each
    t = _make(repo, factory, planned_usd=1.0)
    p = {"model": "gpt-6-luna", "input": [], "reasoning": {"context": "all_turns"}}
    t.send(p)
    t.send(p)
    with pytest.raises(BudgetExceeded):
        t.send(p)
    assert len(built[0].sent) == 2


def test_retries_rate_limits_then_gives_up(repo, monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")
    req = httpx.Request("POST", "https://example.invalid/v1/responses")
    err = openai.RateLimitError("busy", response=httpx.Response(429, request=req), body=None)
    factory, built = _factory([err, err, _response()])
    t = _make(repo, factory, max_attempts=3)
    p = {"model": "gpt-6-luna", "input": [], "reasoning": {"context": "all_turns"}}
    assert t.send(p)["model"] == "gpt-6-luna-2026-09-01"
    assert len(built[0].sent) == 3 and t.ledger.n_calls == 1  # 429s are not billed
    factory, _ = _factory([err, err])
    t = _make(repo, factory, max_attempts=2)
    with pytest.raises(openai.RateLimitError):
        t.send(p)
    assert t.ledger.n_calls == 0


def test_refuses_unknown_model_and_wrong_payload_model(repo, monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, _ = _factory([_response()])
    with pytest.raises(KeyError):
        _make(repo, factory, model="some-other-model")
    t = _make(repo, factory)
    with pytest.raises(ValueError):
        t.send({"model": "gpt-6.1-sol", "input": []})


def test_cli_refuses_without_env(monkeypatch, capsys):
    monkeypatch.delenv(ALLOW_ENV, raising=False)

    def no_client(*a, **k):
        raise AssertionError("must not build a client")
    monkeypatch.setattr(openai, "OpenAI", no_client)
    assert cli.main(["probe-echo", "--approved-block", "x", "--planned-usd", "1"]) == 2
    assert cli.main(["run", "--cell", "F-0", "--approved-block", "x", "--planned-usd", "1"]) == 2
    assert "refused" in capsys.readouterr().err


def test_cli_pilot_size_limit(monkeypatch, capsys):
    monkeypatch.setenv(ALLOW_ENV, "1")
    assert cli.main(["run", "--cell", "F-0", "--n", "2", "--approved-block", "x",
                     "--planned-usd", "1"]) == 2  # 2 templates x 8 task cells = 16 > 10
    assert "at most 10" in capsys.readouterr().err


def test_no_key_handling_in_harness_code():
    """The SDK reads the key from the environment; our code never names or loads it."""
    for path in HARNESS_DIR.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert "OPENAI_API_KEY" not in src and "dotenv" not in src, path.name
        assert "api_key" not in src, path.name


def test_pricing():
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000,
             "input_tokens_details": {"cached_tokens": 400_000, "cache_write_tokens": 100_000}}
    # sol: 500k plain x $2 + 400k cached x $0.10 + 100k writes x $2 x 1.25 + 1M out x $10
    listed, billed = cost_usd("gpt-6.1-sol", usage, "flex")
    assert listed == pytest.approx(1.0 + 0.04 + 0.25 + 10.0)
    assert billed == pytest.approx(listed / 2)
    assert cost_usd("gpt-6.1-sol-2026-10-01", usage, "default")[1] == pytest.approx(listed)
    with pytest.raises(KeyError):
        cost_usd("gpt-6", usage, "flex")
