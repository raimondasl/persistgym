"""The guarded ARC launcher (arc/run_path.py). Everything that could spend is mocked: the
patched harness is never built (apply_patches functions are replaced), the inner process
is a fake that writes the files the harness would, and the approval checks run against a
throwaway git repository whose origin is a local bare repository (file transport only).
Nothing here calls a model, ARC or the network."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from arc import apply_patches as ap
from arc import config_hash as freeze
from arc import pricing
from arc import run_path as rp
from arc import run_path_inner as inner
from arc import run_path_offline as rpo
from common import approval, costs, runmeta
from common.tests.gitrepo import decisions_text, git_in, guarded_repo, push_main

FROZEN = "Version: 1.0\n\n**Status: Frozen on 2026-10-03 by the researcher.**\n"
DRAFT = "Version: 0.2-draft\n\n**Status: DRAFT. Not yet frozen.**\n"
BLOCK = "1-pilots"
EXPERIMENTS = ("arc_pilot", "gemini_probe", "arc_path")
RECORD = freeze.load_record()
STEP_USAGE = {"prompt_tokens": 1_000, "completion_tokens": 300, "total_tokens": 1_300,
              "reasoning_tokens": 250, "cached_tokens": 400, "cache_write_tokens": 0,
              "cost": 0.0, "cost_details": {}}


def _repo(tmp_path: Path, **kwargs) -> Path:
    (tmp_path / "repo").mkdir()
    return guarded_repo(tmp_path / "repo", **kwargs)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
    monkeypatch.setenv(approval.ALLOW_ENV, "1")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    monkeypatch.setenv("ARC_API_KEY", "test-arc-key")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-the-harness")
    for name in ("OPERATION_MODE", "ARC_BASE_URL", "ENVIRONMENTS_DIR"):
        monkeypatch.delenv(name, raising=False)


class FakeHarness:
    """Stands in for apply_patches and the inner process; records what the launcher did."""

    def __init__(self, monkeypatch, tmp_path: Path) -> None:
        self.calls: list[str] = []
        self.commands: list[list[str]] = []
        self.envs: list[dict] = []
        self.tree = RECORD["patched_tree"]
        self.resolved = {e["config_id"]: e["config"] for e in RECORD["profiles"].values()}
        self.inner: Callable[[list[str], Path], int] = lambda command, cwd: 0
        monkeypatch.setattr(ap, "WORK_DIR", tmp_path / "work")
        monkeypatch.setattr(ap, "check_pin", lambda env: self.calls.append("pin"))
        monkeypatch.setattr(ap, "create_worktree", lambda path, env: self.calls.append("create"))
        monkeypatch.setattr(ap, "apply_series",
                            lambda path, patches, env: self.calls.append("apply"))
        monkeypatch.setattr(ap, "sync_environment", lambda path, env: self.calls.append("sync"))
        monkeypatch.setattr(ap, "remove_worktree", lambda path, env: self.calls.append("remove"))
        monkeypatch.setattr(ap, "_git", self._git)
        monkeypatch.setattr(freeze, "resolve_profiles", self._resolve)
        monkeypatch.setattr(rp, "run_inner", self._run_inner)

    def _git(self, args, cwd, env):
        return RECORD["patched_commit"] if args == ["rev-parse", "HEAD"] else self.tree

    def _resolve(self, worktree, env, ids):
        self.calls.append("resolve")
        assert not any(k in env for k in ("GOOGLE_API_KEY", "ARC_API_KEY"))
        return {cid: self.resolved[cid] for cid in ids}

    def _run_inner(self, command, cwd, env, **kwargs):
        self.calls.append("inner")
        self.commands.append(command)
        self.envs.append(dict(env))
        return self.inner(command, Path(cwd))


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo = _repo(tmp_path, prereg=FROZEN,
                        decisions=decisions_text(BLOCK, experiments=EXPERIMENTS,
                                                 max_usd="500"))
    costs_csv = tmp_path / "costs.csv"
    costs_csv.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    paths = rp.Paths(repo=repo, costs=costs_csv, results=tmp_path / "results",
                     raw=tmp_path / "raw", lock=tmp_path / "paid.lock")
    return paths, FakeHarness(monkeypatch, tmp_path)


# ── What the fake inner process writes ────────────────────────────────


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def fake_game(cwd: Path, *, exit_reason="GAME_WIN", steps=2, tiers=("standard",) * 2,
              total_extra=None, result=True, calls=((200, 1.0), (503, 0.1), (200, 3.0))):
    run = cwd / "recordings" / "ft09.benchmarkingagent.0123"
    total = {k: v * steps if isinstance(v, int) else v for k, v in STEP_USAGE.items()}
    for k, v in (total_extra or {}).items():
        total[k] += v
    for i in range(1, steps + 1):
        _write(run / f"step_{i:03d}.json",
               {"step": i, "usage": STEP_USAGE, "retries": 0,
                **({"service_tier": tiers[i - 1]} if tiers[i - 1] else {})})
    _write(run / "run_meta.json", {
        "exit_reason": exit_reason, "agent_exit_reason": exit_reason,
        "requested_service_tier": "standard", "reported_models": ["gemini-3.8-flash"],
        "total_usage": total, "duration_seconds": 12.5,
        "arc_environment": {"kind": "remote", "base_url": "https://three.arcprize.org"},
        "cost_guard": {"max_usd": 15.0, "estimated_cost_usd": 0.004}})
    (cwd / "rec").mkdir(exist_ok=True)
    (cwd / "rec" / "ft09.benchmarkingagent.x.recording.jsonl").write_text("{}\n")
    out = cwd / "out"
    out.mkdir(exist_ok=True)
    (out / inner.CALLS_FILE).write_text("".join(
        json.dumps({"started_utc": "t", "method": "POST", "path": "/v1beta/interactions",
                    "status": s, "duration_s": d}) + "\n" for s, d in calls))
    if result:
        _write(out / inner.RESULT_FILE, {
            "card_id": "card-123",
            "scorecard": {"score": 42.0, "won": 1, "api_key": "test-arc-key",
                          "environments": [{"id": "ft09", "session_token": "x"}]},
            "exit_reason": exit_reason, "game_id_served": "ft09-abcd1234",
            "action_counter": steps, "error": None, "interrupted": False,
            "truncation": {"truncated": False}})
    return 0


def fake_accept(cwd: Path, *, rejected=()):
    out = cwd / "out"
    out.mkdir(exist_ok=True)
    records = []
    for label, cid in freeze.PROFILES.items():
        ok = label not in rejected
        records.append({"config_id": cid, "accepted": ok,
                        "error": None if ok else "ClientError: 400 bad request",
                        "reported_model": "gemini-3.8-flash", "service_tier": "standard",
                        "latency_s": 2.0, "usage": STEP_USAGE if ok else None,
                        "request_settings": {"model": "gemini-3.8-flash"}})
    _write(out / inner.ACCEPT_FILE, records)
    (out / inner.CALLS_FILE).write_text("".join(
        json.dumps({"status": 200 if lb not in rejected else 400, "duration_s": 2.0}) + "\n"
        for lb in freeze.PROFILES))
    return 0 if not rejected else 1


def _rows(paths: rp.Paths) -> list[dict]:
    with paths.costs.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _meta(paths: rp.Paths, experiment: str) -> dict:
    (path,) = (paths.results / experiment).glob("*/meta.json")
    return json.loads(path.read_text(encoding="utf-8"))


GAME_ARGS = ["--approved-block", BLOCK, "--experiment", "arc_path", "--config", "S0",
             "--game", "ft09", "--seed", "1", "--planned-usd", "125"]
PILOT_ARGS = ["--approved-block", BLOCK, "--experiment", "arc_pilot", "--config", "S1",
              "--game", "FT09", "--seed", "1", "--planned-usd", "15", "--max-actions", "60",
              "--after-summary-turns", "5"]
ACCEPT_ARGS = ["--approved-block", BLOCK, "--experiment", "gemini_probe",
               "--acceptance-check", "--planned-usd", "1"]

LIST = (2_000 * 0.75 + 600 * 3.75) / 1e6
BILLED = (1_200 * 0.75 + 800 * 0.075 + 600 * 3.75) / 1e6


# ── Full runs with the harness mocked ─────────────────────────────────


def test_counted_run_is_accounted_and_recorded(world):
    paths, h = world
    h.inner = lambda command, cwd: fake_game(cwd)

    assert rp.main(GAME_ARGS, paths=paths) == 0

    assert h.calls == ["pin", "create", "apply", "sync", "resolve", "inner", "remove"]
    (command,) = h.commands
    s0 = RECORD["profiles"]["S0"]
    assert command[6:9] == [str(freeze.INNER), "play", "--config"]
    assert command[command.index("--config") + 1] == s0["config_id"]
    assert command[command.index("--expect-config-hash") + 1] == s0["sha256"]
    assert float(command[command.index("--cost-cap-usd") + 1]) == 120.0   # D22
    assert "--max-actions" not in command
    tags = command[command.index("--tags") + 1].split(",")
    assert tags[:4] == ["persistgym", "arc_path", "S0", "seed-1"]
    (env,) = h.envs
    assert env["GOOGLE_API_KEY"] == "test-google-key" and env["ARC_API_KEY"] == "test-arc-key"
    assert "OPENAI_API_KEY" not in env and "OPERATION_MODE" not in env
    assert env["ARC_HARNESS_COMMIT_SHA"] == RECORD["patched_commit"]

    (row,) = _rows(paths)
    assert row["notes"].startswith(approval.spend_tag(BLOCK))
    assert "exit_reason=GAME_WIN" in row["notes"]
    assert (row["experiment"], row["cell_or_config"], row["milestone"]) == ("arc_path", "S0",
                                                                           "M1")
    assert (row["provider"], row["api"], row["service_tier"], row["service_tier_served"]) == (
        "google", "interactions", "standard", "standard")
    assert (row["n_calls"], row["latency_s"]) == ("2", "2.000")   # median of the 2xx calls
    assert (row["input_tokens"], row["cached_input_tokens"], row["output_tokens"],
            row["reasoning_tokens"]) == ("2000", "800", "600", "500")
    assert float(row["cost_usd_list"]) == pytest.approx(LIST)
    assert float(row["cost_usd_billed_est"]) == pytest.approx(BILLED)
    assert row["price_source_date"] == pricing.PRICE_SOURCE_DATE
    assert row["model_returned"] == "gemini-3.8-flash"

    meta = _meta(paths, "arc_path")
    assert meta["config_hash"] == s0["sha256"] == meta["config_freeze"]["sha256"]["S0"]
    assert meta["config_freeze"]["patched_tree"] == RECORD["patched_tree"]
    assert (meta["exit_reason"], meta["agent_exit_reason"]) == ("GAME_WIN", "GAME_WIN")
    assert meta["outcome"]["scorecard_id"] == "card-123"
    assert meta["service_tier"] == {"requested": "standard", "served": {"standard": 2}}
    assert meta["latency"]["median_s"] == 2.0 and meta["n_http_requests"] == 3
    assert meta["cost_usd"]["billed_est"] == pytest.approx(BILLED, abs=1e-6)
    assert meta["tokens"]["reasoning_tokens"] == 500
    assert meta["approved_block"] == BLOCK and meta["phase"] == "1b"
    assert meta["seeds"]["replicate_seed"] == 1 and meta["cost_cap_usd"] == 120.0
    run_dir = Path(meta["raw_transcript_path"])
    if not run_dir.is_absolute():
        run_dir = runmeta.REPO_ROOT / run_dir
    assert (run_dir / "harness" / "step_001.json").exists()
    assert (run_dir / "recording.jsonl").exists() and (run_dir / "calls.jsonl").exists()
    scorecard = paths.results / "arc_path" / meta["run_id"] / "scorecard.json"
    assert json.loads(scorecard.read_text()) == {"score": 42.0, "won": 1,
                                                 "environments": [{"id": "ft09"}]}
    for committed in (scorecard, scorecard.parent / "meta.json", paths.costs):
        text = committed.read_text(encoding="utf-8")
        assert "test-arc-key" not in text and "test-google-key" not in text
    assert not paths.lock.exists()


def test_pilot_outcome_stays_in_raw(world):
    paths, h = world
    h.inner = lambda command, cwd: fake_game(cwd, exit_reason="GAME_WIN")

    assert rp.main(PILOT_ARGS, paths=paths) == 0

    (command,) = h.commands
    assert command[command.index("--max-actions") + 1] == "60"
    assert command[command.index("--after-summary-turns") + 1] == "5"
    assert float(command[command.index("--cost-cap-usd") + 1]) == 15.0
    assert command[command.index("--game") + 1] == "ft09"
    (row,) = _rows(paths)
    assert row["reasoning_tokens"] == ""
    assert f"exit_reason={rp.BLINDED_ENDING}" in row["notes"]
    assert "GAME_WIN" not in row["notes"] and rp.WITHHELD_NOTE in row["notes"]
    meta_path = next((paths.results / "arc_pilot").glob("*/meta.json"))
    text = meta_path.read_text(encoding="utf-8")
    assert "GAME_WIN" not in text and "card-123" not in text and "score" not in text
    meta = json.loads(text)
    assert meta["exit_reason"] == meta["agent_exit_reason"] == rp.BLINDED_ENDING
    assert meta["tokens"]["reasoning_tokens"] is None
    assert "outcome" not in meta and meta["blinding"]["rule"] == rp.WITHHELD_NOTE
    assert meta["truncation_limits"] == {"max_actions": 60, "after_summary_turns": 5}
    assert not (meta_path.parent / "scorecard.json").exists()
    raw = json.loads((paths.raw / "arc_pilot" / meta["run_id"] / "result.json").read_text())
    assert raw["exit_reason"] == "GAME_WIN"                 # the outcome is kept, in raw only


def test_pilot_errors_are_not_blinded(world):
    paths, h = world
    h.inner = lambda command, cwd: fake_game(cwd, exit_reason="AGENT_ERROR")

    rp.main(PILOT_ARGS, paths=paths)

    assert _meta(paths, "arc_pilot")["exit_reason"] == "AGENT_ERROR"
    assert "exit_reason=AGENT_ERROR" in _rows(paths)[0]["notes"]


def test_a_crashed_run_is_still_accounted(world):
    paths, h = world

    def crash(command, cwd):
        fake_game(cwd, exit_reason="UNKNOWN", steps=1, tiers=("standard",), result=False,
                  calls=((200, 4.0),))
        return 1

    h.inner = crash

    assert rp.main(GAME_ARGS, paths=paths) == 1

    (row,) = _rows(paths)
    assert row["n_calls"] == "1" and float(row["cost_usd_list"]) == pytest.approx(LIST / 2)
    meta = _meta(paths, "arc_path")
    assert meta["exit_reason"] == "UNKNOWN" and meta["cost_usd"]["costs_csv_row_appended"]
    assert h.calls[-1] == "remove" and not paths.lock.exists()


def test_usage_only_in_the_run_total_is_priced_and_noted(world):
    paths, h = world
    extra = {"prompt_tokens": 1_000, "completion_tokens": 100}    # e.g. a failed summary
    h.inner = lambda command, cwd: fake_game(cwd, total_extra=extra)

    rp.main(GAME_ARGS, paths=paths)

    (row,) = _rows(paths)
    assert row["input_tokens"] == "3000" and row["output_tokens"] == "700"
    assert float(row["cost_usd_list"]) == pytest.approx(LIST + (750 + 375) / 1e6)
    assert "run_meta total_usage" in row["notes"]


def test_a_different_served_tier_is_flagged(world):
    paths, h = world
    h.inner = lambda command, cwd: fake_game(cwd, tiers=("standard", "flex"))

    rp.main(GAME_ARGS, paths=paths)

    (row,) = _rows(paths)
    assert row["service_tier_served"] == "flex;standard"
    assert "served tier differs" in row["notes"]


def test_a_run_that_cannot_be_accounted_keeps_the_lock(world, capsys):
    """Spend the ledger does not show must stop the next paid run until it is added."""
    paths, h = world
    bad = {**STEP_USAGE, "cached_tokens": STEP_USAGE["prompt_tokens"] + 1}  # unpriceable

    def odd_usage(command, cwd):
        fake_game(cwd)
        run = cwd / "recordings" / "ft09.benchmarkingagent.0123"
        _write(run / "step_002.json", {"step": 2, "usage": bad})
        return 0

    h.inner = odd_usage
    with pytest.raises(pricing.PriceError):
        rp.main(GAME_ARGS, paths=paths)

    assert _rows(paths) == []
    held = json.loads(paths.lock.read_text(encoding="utf-8"))
    assert "add its row by hand" in held["kept_because"]
    assert "could not account" in capsys.readouterr().err

    h.inner = lambda command, cwd: fake_game(cwd)
    assert rp.main(GAME_ARGS, paths=paths) == 2
    assert "add its row by hand" in capsys.readouterr().err
    assert h.calls.count("inner") == 1


def test_the_last_run_must_be_in_this_checkouts_ledger(world, tmp_path, capsys):
    """The lock is shared by all checkouts, the ledger is not: a run started from another
    checkout must not miss the spend the last run wrote to this one's costs.csv."""
    paths, h = world
    h.inner = lambda command, cwd: fake_game(cwd)
    assert rp.main(GAME_ARGS, paths=paths) == 0
    (row,) = _rows(paths)

    other = tmp_path / "other-costs.csv"
    other.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    elsewhere = rp.Paths(**{**vars(paths), "costs": other})
    assert rp.main(GAME_ARGS, paths=elsewhere) == 2
    err = capsys.readouterr().err
    assert row["run_id"] in err and "not in this checkout" in err
    assert h.calls.count("inner") == 1

    assert rp.main(GAME_ARGS, paths=paths) == 0      # the ledger that has the row
    assert h.calls.count("inner") == 2


def test_an_unreadable_ledger_refuses(world):
    paths, h = world
    paths.costs.write_text("timestamp_utc,run_id\n", encoding="utf-8")
    assert rp.main(GAME_ARGS, paths=paths) == 2
    assert "create" not in h.calls and not paths.lock.exists()


def test_no_model_call_means_no_costs_row(world):
    paths, h = world
    h.inner = lambda command, cwd: 1

    assert rp.main(GAME_ARGS, paths=paths) == 1

    assert _rows(paths) == []
    meta = _meta(paths, "arc_path")
    assert meta["cost_usd"]["costs_csv_row_appended"] is False and meta["n_calls"] == 0


def test_acceptance_check(world):
    paths, h = world
    h.inner = lambda command, cwd: fake_accept(cwd)

    assert rp.main(ACCEPT_ARGS, paths=paths) == 0

    (command,) = h.commands
    assert command[7] == "accept"
    hashes = json.loads(command[command.index("--expect-config-hashes") + 1])
    assert hashes == {e["config_id"]: e["sha256"] for e in RECORD["profiles"].values()}
    assert float(command[command.index("--cost-cap-usd") + 1]) == 1.0
    (env,) = h.envs
    assert "ARC_API_KEY" not in env and env["GOOGLE_API_KEY"] == "test-google-key"
    (row,) = _rows(paths)
    assert (row["experiment"], row["cell_or_config"], row["n_calls"]) == (
        "gemini_probe", "S0+S1+S2+S4", "4")
    assert float(row["cost_usd_billed_est"]) == pytest.approx(BILLED * 2)
    meta = _meta(paths, "gemini_probe")
    assert meta["exit_reason"] == "ALL_ACCEPTED"
    assert set(meta["acceptance"]) == {"S0", "S1", "S2", "S4"}
    assert all(r["accepted"] and r["service_tier"] == "standard"
               for r in meta["acceptance"].values())
    assert set(meta["config"]) == {"S0", "S1", "S2", "S4"}


def test_acceptance_check_reports_a_rejected_payload(world):
    paths, h = world
    h.inner = lambda command, cwd: fake_accept(cwd, rejected=("S4",))

    assert rp.main(ACCEPT_ARGS, paths=paths) == 1

    meta = _meta(paths, "gemini_probe")
    assert meta["exit_reason"] == "NOT_ALL_ACCEPTED"
    assert meta["acceptance"]["S4"]["accepted"] is False
    assert "400" in meta["acceptance"]["S4"]["error"]


# ── Refusals: nothing is built or spent ───────────────────────────────


def _refused(paths, h, argv=GAME_ARGS) -> None:
    assert rp.main(argv, paths=paths) == 2
    assert "create" not in h.calls and "inner" not in h.calls
    assert _rows(paths) == []
    assert not paths.results.exists()


def test_refused_without_the_paid_switch(world, monkeypatch):
    paths, h = world
    monkeypatch.delenv(approval.ALLOW_ENV)
    _refused(paths, h)
    assert not paths.lock.exists()


def test_refused_without_an_approval_for_the_block(world):
    paths, h = world
    _refused(paths, h, [*GAME_ARGS[:1], "2-seed1", *GAME_ARGS[2:]])


def test_refused_for_an_experiment_the_block_does_not_list(world):
    paths, h = world
    decisions = decisions_text(BLOCK, experiments=("gemini_probe",), max_usd="500")
    (paths.repo / "results" / "decisions.md").write_text(decisions, encoding="utf-8")
    git_in(paths.repo, "commit", "-q", "-am", "narrow the block")
    push_main(paths.repo)
    _refused(paths, h)


def test_refused_when_the_block_is_spent(world):
    paths, h = world
    costs.append_row({c: "" for c in costs.COLUMNS} | {
        "experiment": "arc_path", "cost_usd_list": "400", "cost_usd_billed_est": "400",
        "notes": approval.spend_tag(BLOCK)}, paths.costs)
    assert rp.main(GAME_ARGS, paths=paths) == 2
    assert "create" not in h.calls and len(_rows(paths)) == 1


def test_refused_when_prereg_is_not_frozen(tmp_path, monkeypatch):
    repo = _repo(tmp_path, prereg=DRAFT,
                        decisions=decisions_text(BLOCK, experiments=EXPERIMENTS))
    costs_csv = tmp_path / "costs.csv"
    costs_csv.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    paths = rp.Paths(repo=repo, costs=costs_csv, results=tmp_path / "results",
                     raw=tmp_path / "raw", lock=tmp_path / "paid.lock")
    _refused(paths, FakeHarness(monkeypatch, tmp_path))


def test_refused_when_head_prereg_is_not_the_merged_one(world):
    paths, h = world
    (paths.repo / "PREREG.md").write_text(FROZEN + "\nAn unmerged amendment.\n",
                                          encoding="utf-8")
    git_in(paths.repo, "commit", "-q", "-am", "local amendment, not merged")
    _refused(paths, h)


def test_refused_while_another_paid_run_holds_the_lock(world):
    paths, h = world
    paths.lock.write_text('{"run_id": "other-run"}', encoding="utf-8")
    _refused(paths, h)
    assert "other-run" in paths.lock.read_text()


def test_refused_when_the_patches_differ_from_the_freeze_record(world, tmp_path):
    paths, h = world
    record = json.loads(json.dumps(RECORD))
    record["patch_series"]["sha256"] = "0" * 64
    stale = tmp_path / "stale.json"
    stale.write_text(json.dumps(record), encoding="utf-8")
    paths = rp.Paths(**{**vars(paths), "freeze": stale})
    _refused(paths, h)
    assert not paths.lock.exists()


def test_refused_when_the_patched_tree_differs(world):
    paths, h = world
    h.tree = "f" * 40
    assert rp.main(GAME_ARGS, paths=paths) == 2
    assert "inner" not in h.calls and h.calls[-1] == "remove" and _rows(paths) == []


def test_refused_when_a_profile_resolves_differently(world):
    paths, h = world
    cid = RECORD["profiles"]["S0"]["config_id"]
    h.resolved = {**h.resolved, cid: {**h.resolved[cid], "pricing": {}}}
    assert rp.main(GAME_ARGS, paths=paths) == 2
    assert "inner" not in h.calls and h.calls[-1] == "remove" and _rows(paths) == []


# ── The plan: argument rules ──────────────────────────────────────────


def _plan(argv, *, record=RECORD, today=date(2026, 10, 3), environ=None):
    env = {"GOOGLE_API_KEY": "k", "ARC_API_KEY": "k"} if environ is None else environ
    return rp.make_plan(rp.parse_args(argv), record, today=today, environ=env,
                        now=datetime(2026, 10, 3, 12, 0, 0, tzinfo=UTC))


def test_plan_of_a_counted_run():
    plan = _plan(GAME_ARGS)

    assert (plan.run_id, plan.labels, plan.game, plan.seed) == (
        "20261003T120000Z-S0-ft09-s1", ("S0",), "ft09", 1)
    assert plan.cost_cap_usd == 120.0 and plan.key_names == ("GOOGLE_API_KEY", "ARC_API_KEY")
    assert not plan.blinded and plan.milestone == "M1"


def test_plan_keeps_a_game_version():
    plan = _plan([*GAME_ARGS[:6], "--game", "ft09-0d8bbf25", *GAME_ARGS[8:]])
    assert plan.game == "ft09-0d8bbf25"


@pytest.mark.parametrize("change, message", [
    (["--game", "sp80"], "held-out game"),
    (["--game", "vc33"], "held-out game"),
    (["--game", "ls20"], "not a path game"),
    (["--game", "ft09/../x"], "not a game ID"),
    (["--config", "S3"], "unknown profile"),
    (["--seed", "-1"], "--seed"),
    (["--planned-usd", "119"], "D22 cost guard"),
    (["--planned-usd", "nan"], "positive, finite"),
    (["--planned-usd", "0"], "positive, finite"),
    (["--max-actions", "50"], "never truncated"),
    (["--after-summary-turns", "5"], "never truncated"),
    (["--rerun-of", "../x"], "--rerun-of"),
    # The guard strips the name, but the costs row is tagged with it as given: a padded
    # name would pass the guard and then be missing from the block's spend.
    (["--approved-block", " 1-pilots"], "not a block name"),
    (["--approved-block", "1-pilots "], "not a block name"),
    (["--approved-block", "1-pilots;x"], "not a block name"),
])
def test_plan_refuses_counted_runs(change, message):
    argv = list(GAME_ARGS)
    for flag, value in zip(change[::2], change[1::2], strict=True):
        if flag in argv:
            argv[argv.index(flag) + 1] = value
        else:
            argv += [flag, value]
    with pytest.raises(rp.Refused, match=message):
        _plan(argv)


@pytest.mark.parametrize("argv, message", [
    ([*PILOT_ARGS[:-4], "--after-summary-turns", "5"], "needs --max-actions"),
    ([*PILOT_ARGS[:-2], "--after-summary-turns", "0"], ">= 1"),
    ([*ACCEPT_ARGS, "--config", "S0"], "plays no game"),
    ([*ACCEPT_ARGS, "--configs", ""], "names no profile"),
    ([a for a in ACCEPT_ARGS if a != "--acceptance-check"], "goes with"),
    ([*PILOT_ARGS, "--acceptance-check"], "goes with"),
    (["--approved-block", BLOCK, "--experiment", "arc_pilot", "--planned-usd", "5"],
     "needs --config, --game and --seed"),
])
def test_plan_refuses_other_combinations(argv, message):
    with pytest.raises(rp.Refused, match=message):
        _plan(argv)


def test_plan_refuses_unknown_experiments():
    with pytest.raises(SystemExit):
        rp.parse_args([*GAME_ARGS[:2], "--experiment", "statecarry_heldout", *GAME_ARGS[4:]])


def test_plan_needs_the_keys_and_never_prints_them():
    with pytest.raises(rp.Refused, match="ARC_API_KEY not set") as e:
        _plan(GAME_ARGS, environ={"GOOGLE_API_KEY": "secret-value"})
    assert "secret-value" not in str(e.value)
    plan = _plan(ACCEPT_ARGS, environ={"GOOGLE_API_KEY": "k"})
    assert plan.key_names == ("GOOGLE_API_KEY",) and plan.labels == ("S0", "S1", "S2", "S4")


def test_plan_refuses_after_the_price_table_expires():
    with pytest.raises(rp.Refused, match="valid through 2026-12-31"):
        _plan(GAME_ARGS, today=date(2027, 1, 1))


@pytest.mark.parametrize("change, message", [
    (lambda c: c["request"].update(service_tier="flex"), "not 'standard'"),
    (lambda c: c["request"].pop("service_tier"), "not 'standard'"),
    (lambda c: c.update(pricing={"input": 0.75, "output": 4.0}), "configured pricing"),
])
def test_plan_refuses_a_profile_off_the_standard_tier(change, message):
    record = json.loads(json.dumps(RECORD))
    change(record["profiles"]["S0"]["config"])
    with pytest.raises(rp.Refused, match=message):
        _plan(GAME_ARGS, record=record)


def test_pilot_plan_is_blinded_and_capped_at_its_planned_spend():
    plan = _plan(PILOT_ARGS)
    assert plan.blinded and plan.cost_cap_usd == 15.0 and plan.milestone == "M0"
    assert (plan.max_actions, plan.after_summary_turns) == (60, 5)


# ── Pieces ─────────────────────────────────────────────────────────────


def test_prereg_not_frozen_reads_head_and_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
    repo = _repo(tmp_path, prereg=FROZEN)
    git_in(repo, "fetch", "-q", "origin")
    assert rp.prereg_not_frozen(repo) is None

    (repo / "PREREG.md").write_text(DRAFT, encoding="utf-8")
    git_in(repo, "commit", "-q", "-am", "draft")
    assert "differs" in rp.prereg_not_frozen(repo)
    push_main(repo)
    git_in(repo, "fetch", "-q", "origin")
    assert "not frozen" in rp.prereg_not_frozen(repo)


class _Proc:
    def __init__(self, waits):
        self.waits = list(waits)
        self.killed = False

    def wait(self, timeout=None):
        outcome = self.waits.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def kill(self):
        self.killed = True


def test_run_inner_lets_the_run_close_its_scorecard_on_ctrl_c(monkeypatch, tmp_path):
    proc = _Proc([KeyboardInterrupt(), 1])
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: proc)

    assert rp.run_inner(["x"], tmp_path, {}) == 1
    assert not proc.killed


def _fake_kill_tree(proc):
    proc.kill()
    return proc.wait()


def test_run_inner_kills_a_run_that_does_not_stop(monkeypatch, tmp_path):
    proc = _Proc([KeyboardInterrupt(), subprocess.TimeoutExpired("x", 1), -9])
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(rp, "kill_tree", _fake_kill_tree)

    assert rp.run_inner(["x"], tmp_path, {}, grace_s=1) == -9
    assert proc.killed


def test_a_second_ctrl_c_kills_the_run_before_it_is_accounted(monkeypatch, tmp_path):
    proc = _Proc([KeyboardInterrupt(), KeyboardInterrupt(), -9])
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(rp, "kill_tree", _fake_kill_tree)

    with pytest.raises(KeyboardInterrupt):
        rp.run_inner(["x"], tmp_path, {}, grace_s=1)
    assert proc.killed


def _alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True, check=False).stdout
    return f'"{pid}"' in out


@pytest.mark.skipif(os.name != "nt", reason="the uv-leaves-its-child problem is Windows'")
def test_kill_tree_also_ends_the_process_the_inner_process_started(tmp_path):
    """The inner process is `uv run`, whose python child survives a kill of uv alone on
    Windows. Here a python parent stands in for uv."""
    pid_file = tmp_path / "child.pid"
    child = (f"import os, time; open(r'{pid_file}', 'w').write(str(os.getpid())); "
             "time.sleep(60)")
    parent = (f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', "
              f"{child!r}]); time.sleep(60)")
    proc = subprocess.Popen([sys.executable, "-c", parent])
    try:
        deadline = time.monotonic() + 30
        while not (pid_file.exists() and pid_file.read_text()):
            assert time.monotonic() < deadline, "the child never started"
            time.sleep(0.1)
        pid = int(pid_file.read_text())
        assert _alive(pid)

        rp.kill_tree(proc)

        deadline = time.monotonic() + 10
        while _alive(pid) and time.monotonic() < deadline:
            time.sleep(0.2)
        assert not _alive(pid)
    finally:
        if proc.poll() is None:
            proc.kill()
        if pid_file.exists() and pid_file.read_text() and _alive(int(pid_file.read_text())):
            subprocess.run(["taskkill", "/F", "/PID", pid_file.read_text()],
                           capture_output=True, check=False)


def test_inner_env_keeps_only_the_needed_keys(tmp_path):
    plan = _plan(ACCEPT_ARGS, environ={"GOOGLE_API_KEY": "g"})
    harness = rp.Harness(tmp_path / "wt", "c" * 40, "t" * 40, "s" * 64)
    environ = {"PATH": "/bin", "GOOGLE_API_KEY": "g", "ARC_API_KEY": "a",
               "OPENAI_API_KEY": "o", "OPERATION_MODE": "offline", "ARC_BASE_URL": "http://x",
               "ENVIRONMENTS_DIR": "/games", "RUN_GOOGLE_LIVE_TESTS": "1"}

    env = rp.inner_env(plan, harness, tmp_path, environ)

    assert env["GOOGLE_API_KEY"] == "g" and env["PATH"] == "/bin"
    for name in ("ARC_API_KEY", "OPENAI_API_KEY", "OPERATION_MODE", "ARC_BASE_URL",
                 "ENVIRONMENTS_DIR", "RUN_GOOGLE_LIVE_TESTS"):
        assert name not in env
    assert env["RECORDINGS_DIR"] == str(tmp_path / "rec")


def test_redact_keys_is_a_last_line_of_defence(tmp_path, capsys):
    path = tmp_path / "meta.json"
    path.write_text('{"x": "abcdefgh-secret", "y": "short"}', encoding="utf-8")

    assert rp.redact_keys(path, ["abcdefgh-secret", "short", ""]) is True
    assert path.read_text(encoding="utf-8") == '{"x": "[REDACTED]", "y": "short"}'
    assert "redacted" in capsys.readouterr().err
    assert rp.redact_keys(path, ["not-in-the-file"]) is False


# ── The $0 end-to-end check of the inner modes (arc/run_path_offline.py) ──


def test_offline_check_flags_deviations():
    acct = SimpleNamespace(n_http_requests=2, n_calls=1, exit_reason="NOT_ALL_ACCEPTED")
    bodies = [{"service_tier": "flex", "generation_config": {"thinking_level": "high"}},
              {"generation_config": {"thinking_level": "low"}, "service_tier": "standard"}]

    problems = rpo.check_case({"mode": "accept", "labels": ("S0", "S1")}, 1, acct, bodies)

    assert any("exited 1" in p for p in problems)
    assert any("service_tier 'flex'" in p for p in problems)
    assert any("thinking_level" in p for p in problems)
    assert any("meter saw 2 requests (1 ok)" in p for p in problems)
    assert any("NOT_ALL_ACCEPTED" in p for p in problems)


@pytest.mark.skipif(
    os.environ.get("RUN_OFFLINE_SMOKE") != "1" or not (ap.UPSTREAM_DIR / ".git").exists(),
    reason="set RUN_OFFLINE_SMOKE=1 to build the patched harness and run the inner modes",
)
def test_inner_modes_end_to_end_offline(tmp_path):
    assert rpo.main(["--out", str(tmp_path)]) == 0
