"""`count-tokens` (harnesses/token_count.py; PREREG §17.8, pending): the largest requests of
each R8 cell and task cell, rebuilt with the fake model, sent to the free token-counting
endpoint only. The client is a stub that counts characters; `messages.create` and
`messages.stream` fail the test, and no test sets a real key. The volume is the small one, so
the tests are quick; the command itself plays the default config by default."""

from __future__ import annotations

import json

import pytest

from harnesses import anthropic_transport, cli, registered, token_count
from harnesses.tests.conftest import SMALL
from harnesses.wire import MESSAGES, visible_text
from persistgym import tokens

HAIKU = "claude-haiku-5-5"
SMALL_ARGS = ["--gen-set", f"W_tokens={SMALL.W_tokens}", "--gen-set",
              f"v_tokens={SMALL.v_tokens}", "--gen-set",
              f"assumed_max_reply_tokens={SMALL.assumed_max_reply_tokens}"]


class _CountingClient:
    """`messages.count_tokens(**kw)` answers `factor` x the project tokens of the input it is
    given (as a dict, as the SDK's object or its JSON would hold it); nothing else exists."""

    def __init__(self, factor=1.3, extra=0):
        self.factor, self.extra = factor, extra
        self.counted: list[dict] = []
        self.messages = self

    def count_tokens(self, **kw):
        self.counted.append(kw)
        n = tokens.count(kw["system"] + "".join(
            b["text"] for m in kw["messages"] for b in m["content"]))
        return {"input_tokens": round(n * self.factor) + self.extra}

    def create(self, **kw):
        raise AssertionError("count-tokens never calls the model")

    stream = create


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv(anthropic_transport.KEY_ENV, "dummy-not-a-key")
    for name in anthropic_transport.REFUSED_ENV:
        monkeypatch.delenv(name, raising=False)


def test_the_largest_requests_are_rebuilt_at_0(key):
    reqs = token_count.largest_requests(HAIKU, SMALL, n=2)
    assert [(r["cell"], r["task_cell"]) for r in reqs] == (
        [(c, t) for c in registered.HAIKU_CELLS for t in registered.HAIKU_TASK_CELLS]
        + [("single-turn", t) for t in registered.HAIKU_SINGLE_TURN_TASK_CELLS])
    for r in reqs:
        MESSAGES.check_payload(r["payload"], effort="medium", max_tokens=32000)
        assert r["o200k_tokens"] == tokens.count(visible_text(r["payload"]))
        assert ("cache_control" in r["payload"]) is (r["cell"] != "single-turn")
    by = {(r["cell"], r["task_cell"]): r for r in reqs}
    # F-0's largest request is an episode's last one, with the whole history; W's stay
    # within about W (visible text, project tokens), F-0's go past it
    f0 = by[("F-0", "observed-nonrec-far")]
    assert f0["request_index"] > 0 and f0["o200k_tokens"] > SMALL.W_tokens
    assert all(by[("W-0", t)]["o200k_tokens"] <= SMALL.W_tokens + 200
               for t in registered.HAIKU_TASK_CELLS)


def test_count_tokens_counts_with_the_endpoint_only(key):
    client = _CountingClient(factor=1.25)
    report = token_count.token_count(HAIKU, SMALL, n=1, client_factory=lambda: client)
    assert len(client.counted) == len(report["requests"]) == 3 * 8 + 4
    assert all(set(kw) == {"model", "system", "messages", "thinking"} for kw in client.counted)
    assert all(kw["model"] == HAIKU and kw["thinking"] == {"type": "adaptive"}
               for kw in client.counted)
    for row in report["requests"]:
        assert row["claude_tokens"] == round(row["o200k_tokens"] * 1.25)
        assert row["ratio"] == pytest.approx(1.25, abs=0.01)
    assert report["ratio"]["min"] <= report["ratio"]["median"] <= report["ratio"]["max"]
    assert report["max_claude_tokens"] == max(r["claude_tokens"] for r in report["requests"])
    assert report["threshold"] == 100_000 and report["over_threshold"] == []
    assert report["model"] == HAIKU and report["templates"] == {"split": "main", "start": 0,
                                                                "n": 1}
    big = token_count.token_count(HAIKU, SMALL, n=1,
                                  client_factory=lambda: _CountingClient(extra=100_000))
    assert len(big["over_threshold"]) == 28 and big["max_claude_tokens"] > 100_000


@pytest.mark.parametrize("env, why", [
    ({}, "ANTHROPIC_API_KEY is not set"),
    ({"ANTHROPIC_API_KEY": "dummy", "ANTHROPIC_AUTH_TOKEN": "x"}, "ANTHROPIC_AUTH_TOKEN"),
    ({"ANTHROPIC_API_KEY": "dummy", "ANTHROPIC_PROFILE": "x"}, "ANTHROPIC_PROFILE"),
    ({"ANTHROPIC_API_KEY": "dummy", "ANTHROPIC_CUSTOM_HEADERS": "x-api-key: y"},
     "ANTHROPIC_CUSTOM_HEADERS")])
def test_count_tokens_refuses_without_an_api_key(monkeypatch, env, why):
    for name in (anthropic_transport.KEY_ENV, *anthropic_transport.REFUSED_ENV):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    def no_client():
        raise AssertionError("must refuse before building a client")
    with pytest.raises(token_count.Refused, match=why):
        token_count.token_count(HAIKU, SMALL, n=1, client_factory=no_client)


def test_count_tokens_refuses_a_client_with_custom_headers(key):
    """The backstop behind ANTHROPIC_CUSTOM_HEADERS's refusal: a built client that holds any
    custom header (which the SDK sends after its auth headers) refuses before any request."""
    client = _CountingClient()
    client._custom_headers = {"Authorization": "dummy-value"}
    with pytest.raises(token_count.Refused, match=r"custom headers \(Authorization\)") as e:
        token_count.token_count(HAIKU, SMALL, n=1, client_factory=lambda: client)
    assert client.counted == [] and "dummy-value" not in str(e.value)


@pytest.mark.parametrize("model, why", [("gpt-6-luna", r"not a claude-\* model"),
                                        ("claude-sonnet-5-5", "counts the requests of")])
def test_count_tokens_refuses_other_models(key, model, why):
    with pytest.raises(token_count.Refused, match=why):
        token_count.token_count(model, SMALL, n=1, client_factory=_CountingClient)


def test_the_cli_command(key, monkeypatch, tmp_path, capsys):
    client = _CountingClient()
    monkeypatch.setattr(cli, "TOKEN_COUNT_CLIENT", lambda: client)
    out = tmp_path / "tc.json"
    assert cli.main(["count-tokens", "--model", HAIKU, "--n", "1", *SMALL_ARGS,
                     "--out", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert json.loads(capsys.readouterr().out) == report
    assert len(client.counted) == 28 and report["endpoint"].endswith("(free)")
    assert set(report) >= {"git_commit", "git_dirty", "sdk_versions", "prereg_version",
                           "generator_config_hash", "reply_note"}
    monkeypatch.delenv(anthropic_transport.KEY_ENV)
    assert cli.main(["count-tokens", "--model", HAIKU, "--n", "1", "--out", str(out)]) == 2
    assert "refused: ANTHROPIC_API_KEY is not set" in capsys.readouterr().err
    assert cli.main(["count-tokens", "--model", HAIKU, "--n", "0"]) == 2
