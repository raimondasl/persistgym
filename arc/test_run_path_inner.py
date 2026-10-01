"""The helpers of arc/run_path_inner.py that need no harness: the call meter, truncation,
the config hash and the online-only check. The modes themselves run only inside the
patched harness and are exercised by the launcher tests with the inner process mocked."""

from __future__ import annotations

import json

import httpx
import pytest

from arc import run_path_inner as inner
from common import runmeta


def test_config_hash_equals_the_run_metadata_hash():
    config = {"b": [1, 2.0, "é"], "a": {"z": None, "y": True}, "c": 1_800.0}

    assert inner.config_hash(config) == runmeta.config_hash(config)


def test_metering_transport_logs_status_and_timing_but_no_bodies(tmp_path):
    secret = "body-and-header-text-that-must-not-be-logged"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/fail"):
            raise httpx.ConnectError("boom")
        status = 503 if request.url.path.endswith("/busy") else 200
        return httpx.Response(status, json={"echo": secret})

    ticks = iter([0.0, 1.5, 10.0, 10.25, 20.0, 20.5])
    path = tmp_path / "calls.jsonl"
    meter = inner.MeteringTransport(httpx.MockTransport(handler), path,
                                    clock=lambda: next(ticks))
    with httpx.Client(transport=meter) as client:
        ok = client.post("https://example.test/v1/interactions?key=" + secret,
                         headers={"x-goog-api-key": secret}, json={"input": secret})
        assert ok.json() == {"echo": secret}          # the response passes unchanged
        assert client.post("https://example.test/busy").status_code == 503
        with pytest.raises(httpx.ConnectError):
            client.post("https://example.test/fail")

    text = path.read_text(encoding="utf-8")
    assert secret not in text
    records = [json.loads(line) for line in text.splitlines()]
    assert [(r["path"], r["status"], r["duration_s"]) for r in records] == [
        ("/v1/interactions", 200, 1.5), ("/busy", 503, 0.25), ("/fail", None, 0.5)]
    assert records[2]["error"] == "ConnectError"
    assert all(r["method"] == "POST" and r["started_utc"] for r in records)


def test_scrub_drops_credential_like_fields_at_any_depth():
    scorecard = {"card_id": "c", "api_key": "k", "score": 1.5,
                 "environments": [{"id": "ft09", "apiKey": "k", "runs": [{"Token": "t",
                                                                          "levels": 2}]}],
                 "opaque": {"cookie": "x", "password": "p", "secret_x": 1, "credentials": 2}}

    assert inner.scrub(scorecard) == {"card_id": "c", "score": 1.5, "opaque": {},
                                      "environments": [{"id": "ft09",
                                                        "runs": [{"levels": 2}]}]}


def test_truncation_after_max_actions():
    t = inner.Truncation(max_actions=50)

    assert t.check(actions=49, steps_saved=49) is None
    assert t.check(actions=50, steps_saved=50) == "max_actions=50"
    assert t.to_dict()["truncated"] is True


def test_truncation_after_turns_from_the_first_summary():
    t = inner.Truncation(max_actions=200, after_summary_turns=5)

    assert t.check(actions=30, steps_saved=30) is None     # no summary yet
    t.note_summary(before_step=31)
    t.note_summary(before_step=60)                        # only the first one counts
    assert t.check(actions=31, steps_saved=31) is None    # 1 turn after the summary
    assert t.check(actions=34, steps_saved=34) is None    # 4 turns
    assert t.check(actions=35, steps_saved=35).startswith("after_summary_turns=5")
    assert t.to_dict()["first_summary_before_step"] == 31


def test_truncation_off_never_stops():
    t = inner.Truncation()
    t.note_summary(before_step=1)

    assert t.check(actions=10_000, steps_saved=10_000) is None
    assert t.to_dict() == {"max_actions": None, "after_summary_turns": None,
                           "first_summary_before_step": 1, "truncated": False,
                           "reason": None}


@pytest.mark.parametrize("env, ok", [
    ({}, True), ({"OPERATION_MODE": "online"}, True), ({"OPERATION_MODE": "offline"}, False),
    ({"OPERATION_MODE": "normal"}, False), ({"ARC_BASE_URL": "http://127.0.0.1:8001"}, False),
])
def test_play_runs_online_only(monkeypatch, env, ok):
    for name in ("OPERATION_MODE", "ARC_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    assert (inner._online_only() is None) is ok


def test_play_refuses_offline_before_importing_the_harness(monkeypatch, tmp_path):
    monkeypatch.setenv("OPERATION_MODE", "offline")
    monkeypatch.setattr(inner, "_harness", lambda: pytest.fail("imported the harness"))

    code = inner.main(["play", "--config", "x", "--game", "ft09", "--out", str(tmp_path),
                       "--expect-config-hash", "0" * 64, "--cost-cap-usd", "1"])

    assert code == 2
