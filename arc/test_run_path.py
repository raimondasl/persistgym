"""The guarded ARC launcher (arc/run_path.py). Everything that could spend is mocked: the
patched harness is never built (apply_patches functions are replaced), the inner process
is a fake that writes the files the harness would, and the approval checks run against a
throwaway git repository whose origin is a local bare repository (file transport only).
Nothing here calls a model, ARC or the network."""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from arc import apply_patches as ap
from arc import config_hash as freeze
from arc import prereg_freeze, pricing
from arc import run_path as rp
from arc import run_path_inner as inner
from arc import run_path_offline as rpo
from arc.test_prereg_freeze import HEADER as FROZEN_HEADER
from arc.test_prereg_freeze import prereg_text
from common import approval, costs, hold, paidlock, runmeta
from common.tests.gitrepo import (
    DRAFT_PREREG,
    decisions_text,
    git_in,
    guarded_repo,
    push_main,
    write_decisions,
)

RECORD = freeze.load_record()
RECORD_BYTES = freeze.FREEZE_PATH.read_bytes()
PATCHES = ap.patch_files()           # the files the launcher applies (arc/patches)
# A frozen PREREG.md whose §7.1 config freeze table gives the committed record's values.
FROZEN = prereg_text(RECORD)
DRAFT = "Version: 0.2-draft\n\n**Status: DRAFT. Not yet frozen.**\n"
BLOCK = "1-pilots"
EXPERIMENTS = ("arc_pilot", "gemini_probe", "arc_path")
STEP_USAGE = {"prompt_tokens": 1_000, "completion_tokens": 300, "total_tokens": 1_300,
              "reasoning_tokens": 250, "cached_tokens": 400, "cache_write_tokens": 0,
              "cost": 0.0, "cost_details": {}}


def _commit_file(repo: Path, rel: str, data: bytes, message: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    git_in(repo, "add", rel)
    git_in(repo, "commit", "-q", "-m", message)


def _repo(tmp_path: Path, *, record: bytes | None = RECORD_BYTES,
          patches: list[Path] | None = PATCHES, **kwargs) -> Path:
    """A guarded repo (common.tests.gitrepo) whose HEAD and origin/main also hold
    arc/config_freeze.json (`record`) and arc/patches (copies of `patches`); None leaves
    either out."""
    (tmp_path / "repo").mkdir()
    repo = guarded_repo(tmp_path / "repo", push=False, **kwargs)
    added = []
    if record is not None:
        (repo / rp.FREEZE_GIT_PATH).parent.mkdir(parents=True, exist_ok=True)
        (repo / rp.FREEZE_GIT_PATH).write_bytes(record)
        added.append(rp.FREEZE_GIT_PATH)
    if patches:
        (repo / rp.PATCHES_GIT_PATH).mkdir(parents=True)
        for patch in patches:
            (repo / rp.PATCHES_GIT_PATH / patch.name).write_bytes(patch.read_bytes())
        added.append(rp.PATCHES_GIT_PATH)
    if added:
        git_in(repo, "add", *added)
        git_in(repo, "commit", "-q", "-m", "freeze record and patch series")
    push_main(repo)
    return repo


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
        self.inner_kwargs: list[dict] = []
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
        self.inner_kwargs.append(kwargs)
        self.envs.append(dict(env))
        return self.inner(command, Path(cwd))


def _world(tmp_path, monkeypatch, **repo_kwargs):
    repo = _repo(tmp_path, prereg=FROZEN,
                 decisions=decisions_text(BLOCK, experiments=EXPERIMENTS, max_usd="500"),
                 **repo_kwargs)
    costs_csv = tmp_path / "costs.csv"
    costs_csv.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    paths = rp.Paths(repo=repo, costs=costs_csv, results=tmp_path / "results",
                     raw=tmp_path / "raw", lock=tmp_path / "paid.lock")
    return paths, FakeHarness(monkeypatch, tmp_path)


@pytest.fixture
def world(tmp_path, monkeypatch):
    return _world(tmp_path, monkeypatch)


# ── What the fake inner process writes ────────────────────────────────


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def fake_game(cwd: Path, *, exit_reason="GAME_WIN", steps=2, tiers=("standard",) * 2,
              total_extra=None, result=True, calls=((200, 1.0), (503, 0.1), (200, 3.0)),
              agent_exit_reason=None):
    agent_exit_reason = agent_exit_reason or exit_reason
    run = cwd / "recordings" / "ft09.benchmarkingagent.0123"
    total = {k: v * steps if isinstance(v, int) else v for k, v in STEP_USAGE.items()}
    for k, v in (total_extra or {}).items():
        total[k] += v
    for i in range(1, steps + 1):
        _write(run / f"step_{i:03d}.json",
               {"step": i, "usage": STEP_USAGE, "retries": 0,
                **({"service_tier": tiers[i - 1]} if tiers[i - 1] else {})})
    _write(run / "run_meta.json", {
        "exit_reason": exit_reason, "agent_exit_reason": agent_exit_reason,
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
    assert meta["rerun_of"] is None and meta["r7_replaces"] is None
    assert "rerun_of=" not in row["notes"] and "r7_replaces=" not in row["notes"]
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


def test_a_pilots_harness_output_goes_only_to_its_raw_log(world):
    """PREREG §11: the harness logs the final scorecard (level progress), so a blinded pilot
    must not print it; an unblinded counted run still shows its output live."""
    paths, h = world
    h.inner = lambda command, cwd: fake_game(cwd, exit_reason="GAME_WIN")
    assert rp.main(PILOT_ARGS, paths=paths) == 0
    log = h.inner_kwargs[-1]["log_path"]
    assert log.name == rp.BLINDED_LOG
    assert log.parent.parent == paths.raw / "arc_pilot"
    h.inner = lambda command, cwd: fake_game(cwd)
    assert rp.main(GAME_ARGS, paths=paths) == 0
    assert h.inner_kwargs[-1]["log_path"] is None


def test_run_inner_writes_a_blinded_runs_output_only_to_its_log(tmp_path, capfd):
    # The marker is computed by the child, so it never appears in the echoed command line.
    child = [sys.executable, "-c", "print('levels_completed=' + str(1 + 2))"]
    log = tmp_path / "raw" / "inner_output.log"
    assert rp.run_inner(child, tmp_path, dict(os.environ), log_path=log) == 0
    shown = capfd.readouterr()
    assert "levels_completed=3" not in shown.out + shown.err
    assert "levels_completed=3" in log.read_text(encoding="utf-8")
    assert rp.run_inner(child, tmp_path, dict(os.environ)) == 0
    assert "levels_completed=3" in capfd.readouterr().out


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


def test_the_git_state_is_read_once_before_the_harness_runs(world, monkeypatch):
    """common/runmeta.py: the costs row and meta.json record the git state read before the
    harness makes any model call. A git that fails after that (on 2026-10-02 a PersistGym
    run's process lost its console, so git could not start, exit 0xC0000142) stops neither."""
    paths, h = world
    h.inner = lambda command, cwd: fake_game(cwd)
    real, reads = runmeta.git_state, []

    def git_state(repo=runmeta.REPO_ROOT):
        if reads:
            raise subprocess.CalledProcessError(3221225794, ["git", "rev-parse", "HEAD"])
        reads.append(list(h.calls))
        return real(repo)
    monkeypatch.setattr(runmeta, "git_state", git_state)

    assert rp.main(GAME_ARGS, paths=paths) == 0
    assert len(reads) == 1 and "inner" not in reads[0]
    git = real(paths.repo)
    (row,) = _rows(paths)
    meta = _meta(paths, "arc_path")
    assert row["git_commit"] == meta["git_commit"] == git["git_commit"]
    assert f"git_dirty={git['git_dirty']}" in row["notes"]
    assert meta["git_dirty"] == git["git_dirty"] and not paths.lock.exists()


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
    # its reservation stays, counting against PersistGym runs, and the reason names it
    reservation = paidlock.reservation_path(paths.lock, rp.STREAM)
    assert reservation.exists() and str(reservation) in held["kept_because"]

    h.inner = lambda command, cwd: fake_game(cwd)
    assert rp.main(GAME_ARGS, paths=paths) == 2
    assert "add its row by hand" in capsys.readouterr().err
    assert h.calls.count("inner") == 1

    # the operator deletes the lock but forgets the reservation: the next ARC run refuses
    paths.lock.unlink()
    assert rp.main(GAME_ARGS, paths=paths) == 2
    err = capsys.readouterr().err
    assert "spend reservation of the arc stream is left over" in err and str(reservation) in err
    assert h.calls.count("inner") == 1 and not paths.lock.exists()
    reservation.unlink()
    assert rp.main(GAME_ARGS, paths=paths) == 0 and h.calls.count("inner") == 2


def test_a_run_reserves_its_planned_spend_until_its_row_is_written(world):
    """PREREG §12, "Operational": while an ARC run goes, its planned spend is reserved next
    to the lock, so a PersistGym run that starts meanwhile counts it. Once the costs row is
    written, the run is recorded as the ARC stream's last run and the reservation goes."""
    paths, h = world
    seen = []

    def game(command, cwd):
        with paidlock.budget_mutex(paths.lock):
            seen.extend(paidlock.read_reservations(paths.lock))
        return fake_game(cwd)
    h.inner = game
    assert rp.main(GAME_ARGS, paths=paths) == 0
    (r,) = seen
    assert (r.stream, r.experiment, r.approved_block, r.phase) == ("arc", "arc_path", BLOCK,
                                                                   "1b")
    assert r.planned_usd == Decimal(125)
    assert not r.path.exists() and not paths.lock.exists()
    (row,) = _rows(paths)
    assert row["run_id"] == r.run_id
    last = json.loads(paidlock.last_run_path(paths.lock, rp.STREAM).read_text(encoding="utf-8"))
    assert last["run_id"] == r.run_id and last["stream"] == "arc"


def test_a_running_persistgym_runs_reservation_counts_against_the_block(world, capsys):
    """Block 1 lists experiments of both streams: a PersistGym run going in the same block
    holds its planned spend against max_usd until its row is written, so an ARC run that
    would need that room is refused before anything is spent."""
    paths, h = world                                 # BLOCK's max_usd is 500
    h.inner = lambda command, cwd: fake_game(cwd)
    pg_lock = paths.lock.with_name(paidlock.lock_name(paidlock.PERSISTGYM))
    with paidlock.paid_run_lock(pg_lock, run_id="luna-pilot", what="persistgym_pilot",
                                stream=paidlock.PERSISTGYM) as info:
        with paidlock.budget_mutex(pg_lock):
            paidlock.write_reservation(paidlock.HeldLock(pg_lock, info), approved_block=BLOCK,
                                       experiment="persistgym_pilot", phase="1a",
                                       planned_usd=Decimal(400))
        assert rp.main(GAME_ARGS, paths=paths) == 2
        err = capsys.readouterr().err
        assert "reserved $400.00 of it" in err and "run luna-pilot (persistgym stream" in err
        assert "would exceed it by $25.00" in err
        assert h.calls.count("inner") == 0 and _rows(paths) == []
        assert not paths.lock.exists()
        assert not paidlock.reservation_path(paths.lock, rp.STREAM).exists()
    # the PersistGym run has ended (here: spent nothing): the room is back
    assert rp.main(GAME_ARGS, paths=paths) == 0 and h.calls.count("inner") == 1


def test_the_last_run_must_be_in_this_checkouts_ledger(world, tmp_path, capsys):
    """The lock is shared by all checkouts, the ledger is not: a run started from another
    checkout must not miss the spend the last run wrote to this one's costs.csv."""
    paths, h = world
    h.inner = lambda command, cwd: fake_game(cwd)
    assert rp.main(GAME_ARGS, paths=paths) == 0
    (row,) = _rows(paths)
    last = json.loads(paidlock.last_run_path(paths.lock, rp.STREAM).read_text(encoding="utf-8"))
    assert last["run_id"] == row["run_id"]
    assert last["row_timestamp_utc"] == row["timestamp_utc"]   # the row, not just its ID

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


# ── The hold after COST_CAP (PREREG §0.3 line 12, §7.7) ───────────────
# The hold record is next to the test's own lock (tmp_path), never next to the real one.

# Later runs use seed 2: run IDs carry the start time to the second, and a run may not reuse
# the run ID of a run that placed a hold.
GAME_ARGS_2 = [*GAME_ARGS[:GAME_ARGS.index("--seed") + 1], "2",
               *GAME_ARGS[GAME_ARGS.index("--seed") + 2:]]


def _holds(paths: rp.Paths) -> list[hold.Hold]:
    return hold.read_holds(paths.lock)


def _clear(paths: rp.Paths, run_id: str) -> None:
    """The researcher's merge of the line that clears run `run_id`'s hold."""
    text = (paths.repo / "results" / "decisions.md").read_text(encoding="utf-8")
    write_decisions(paths.repo, text + approval.format_clear_line(run_id) + "\n")
    git_in(paths.repo, "commit", "-q", "-am", f"clear the hold of {run_id}")
    push_main(paths.repo)


def test_a_counted_run_that_ends_cost_cap_places_a_hold_until_cleared(world, capsys):
    paths, h = world
    h.inner = lambda command, cwd: fake_game(cwd, exit_reason="COST_CAP")
    assert rp.main(GAME_ARGS, paths=paths) == 0

    meta = _meta(paths, "arc_path")
    run_id = meta["run_id"]
    (placed,) = _holds(paths)
    r = placed.record
    assert placed.run_id == run_id and r["what"] == "arc_path: S0 on ft09, seed 1"
    assert (r["experiment"], r["approved_block"], r["cost_cap_usd"]) == ("arc_path", BLOCK,
                                                                         120.0)
    assert r["exit_reason"] == r["agent_exit_reason"] == "COST_CAP" and r["placed_utc"]
    assert r["reason"] == ("ended COST_CAP at its harness cost guard of $120.00 list (D22's "
                           "run guard)")
    assert meta["hold_placed"] is True and meta["exit_reason"] == "COST_CAP"
    (row,) = _rows(paths)                                  # accounted as usual (D22: final)
    assert "exit_reason=COST_CAP" in row["notes"]
    out = capsys.readouterr()
    assert f"HOLD: run {run_id} ended COST_CAP" in out.err
    assert f"HOLD placed: no paid run starts until the researcher merges 'cleared_hold: " \
           f"{run_id}'" in out.out
    assert not paths.lock.exists()                         # released; the hold stops runs

    h.inner = lambda command, cwd: fake_game(cwd)
    assert rp.main(GAME_ARGS_2, paths=paths) == 2          # refused before anything runs
    err = capsys.readouterr().err
    assert f"1 hold stands: run {run_id} (arc_path; arc_path: S0 on ft09" in err
    assert f"'cleared_hold: {run_id}'" in err and "either stream, ARC or PersistGym" in err
    assert h.calls.count("inner") == 1 and not paths.lock.exists()

    _clear(paths, run_id)
    assert rp.main(GAME_ARGS_2, paths=paths) == 0
    assert h.calls.count("inner") == 2 and len(_holds(paths)) == 1   # the record stays


@pytest.mark.parametrize("exit_reason, agent_exit_reason", [
    ("SCORECARD_CLOSED", "COST_CAP"),       # ARC rewrote the ending after the game
    ("COST_CAP", "AGENT_ERROR"),
])
def test_either_ending_field_places_the_hold(world, exit_reason, agent_exit_reason):
    paths, h = world
    h.inner = lambda command, cwd: fake_game(cwd, exit_reason=exit_reason,
                                             agent_exit_reason=agent_exit_reason)
    assert rp.main(GAME_ARGS, paths=paths) == 0
    (placed,) = _holds(paths)
    assert (placed.record["exit_reason"], placed.record["agent_exit_reason"]) == (
        exit_reason, agent_exit_reason)


@pytest.mark.parametrize("ending", ["GAME_WIN", "ACTION_BUDGET", "AGENT_ERROR",
                                    "TIME_BUDGET", "UNKNOWN"])
def test_other_endings_place_no_hold(world, ending):
    paths, h = world
    h.inner = lambda command, cwd: fake_game(cwd, exit_reason=ending)
    rp.main(GAME_ARGS, paths=paths)
    assert not hold.holds_path(paths.lock).exists()
    assert _meta(paths, "arc_path")["hold_placed"] is False
    h.inner = lambda command, cwd: fake_game(cwd)
    assert rp.main(GAME_ARGS_2, paths=paths) == 0


def test_a_blinded_pilot_that_ends_cost_cap_places_a_blinded_hold(world, capsys):
    """Pilots and checks place a hold too (their guard is their planned spend). The record
    and the refusal show no game outcome (PREREG §11)."""
    paths, h = world
    h.inner = lambda command, cwd: fake_game(cwd, exit_reason="GAME_WIN",
                                             agent_exit_reason="COST_CAP")
    assert rp.main(PILOT_ARGS, paths=paths) == 0
    (placed,) = _holds(paths)
    assert placed.record["experiment"] == "arc_pilot"
    assert placed.record["exit_reason"] == rp.BLINDED_ENDING
    assert placed.record["agent_exit_reason"] == "COST_CAP"
    assert placed.record["reason"] == ("ended COST_CAP at its harness cost guard of $15.00 "
                                       "list (set at its planned spend)")
    assert "GAME_WIN" not in hold.holds_path(paths.lock).read_text(encoding="utf-8")
    assert "GAME_WIN" not in capsys.readouterr().err
    assert rp.main(GAME_ARGS, paths=paths) == 2
    err = capsys.readouterr().err
    assert f"1 hold stands: run {placed.run_id} (arc_pilot;" in err and "GAME_WIN" not in err


def test_the_hold_is_placed_even_when_the_accounting_fails(world, capsys):
    """The hold is written before the accounting: a run whose costs row cannot be written
    keeps the lock and has placed its hold, so clearing the lock alone starts nothing."""
    paths, h = world
    bad = {**STEP_USAGE, "cached_tokens": STEP_USAGE["prompt_tokens"] + 1}  # unpriceable

    def odd_usage(command, cwd):
        fake_game(cwd, exit_reason="COST_CAP")
        _write(cwd / "recordings" / "ft09.benchmarkingagent.0123" / "step_002.json",
               {"step": 2, "usage": bad})
        return 0

    h.inner = odd_usage
    with pytest.raises(pricing.PriceError):
        rp.main(GAME_ARGS, paths=paths)
    assert _rows(paths) == []
    (placed,) = _holds(paths)
    assert "add its row by hand" in json.loads(paths.lock.read_text())["kept_because"]
    assert f"HOLD: run {placed.run_id}" in capsys.readouterr().err

    paths.lock.unlink()                # the operator adds the row by hand and frees the lock
    h.inner = lambda command, cwd: fake_game(cwd)
    assert rp.main(GAME_ARGS_2, paths=paths) == 2
    assert f"1 hold stands: run {placed.run_id}" in capsys.readouterr().err
    assert h.calls.count("inner") == 1


def test_the_hold_is_placed_even_when_collecting_the_outputs_fails(world, monkeypatch):
    paths, h = world
    h.inner = lambda command, cwd: fake_game(cwd, exit_reason="COST_CAP")

    def disk_full(scratch, raw_dir):
        raise OSError("disk full")
    monkeypatch.setattr(rp, "collect_outputs", disk_full)
    with pytest.raises(OSError, match="disk full"):
        rp.main(GAME_ARGS, paths=paths)
    assert len(_holds(paths)) == 1 and paths.lock.exists()


def test_the_accounting_places_the_hold_if_the_first_check_missed_it(world, monkeypatch):
    paths, h = world
    h.inner = lambda command, cwd: fake_game(cwd, exit_reason="COST_CAP")
    monkeypatch.setattr(rp, "cost_cap_ending", lambda scratch: None)
    assert rp.main(GAME_ARGS, paths=paths) == 0
    (placed,) = _holds(paths)
    assert placed.record["exit_reason"] == "COST_CAP"
    assert _meta(paths, "arc_path")["hold_placed"] is True


def test_a_hold_that_cannot_be_written_keeps_the_lock(world, monkeypatch, capsys):
    paths, h = world
    h.inner = lambda command, cwd: fake_game(cwd, exit_reason="COST_CAP")

    def read_only(*a, **k):
        raise PermissionError("read-only folder")
    monkeypatch.setattr(hold, "place_hold", read_only)
    assert rp.main(GAME_ARGS, paths=paths) == 0
    assert len(_rows(paths)) == 1                          # the run is still accounted
    meta = _meta(paths, "arc_path")
    assert meta["hold_placed"] is False
    kept = json.loads(paths.lock.read_text(encoding="utf-8"))["kept_because"]
    assert "its hold could not be written" in kept and meta["run_id"] in kept
    assert f"'cleared_hold: {meta['run_id']}'" in kept
    assert "its hold could not be written" in capsys.readouterr().err
    h.inner = lambda command, cwd: fake_game(cwd)
    assert rp.main(GAME_ARGS_2, paths=paths) == 2          # the kept lock stops the next run
    assert "its hold could not be written" in capsys.readouterr().err


def _bad_step(cwd: Path) -> None:
    """A step record the accounting cannot price, so that the accounting fails."""
    bad = {**STEP_USAGE, "cached_tokens": STEP_USAGE["prompt_tokens"] + 1}
    _write(cwd / "recordings" / "ft09.benchmarkingagent.0123" / "step_002.json",
           {"step": 2, "usage": bad})


@pytest.mark.parametrize("where", ["checking the ending", "writing the hold"])
def test_a_ctrl_c_during_the_hold_step_keeps_the_lock(world, monkeypatch, where):
    """The hold step runs inside the accounting's guard: a Ctrl+C (the operator stopping a
    run) or an error while the ending is read or the hold is written must not release the
    lock with the run's spend missing from costs.csv and no hold placed."""
    paths, h = world
    h.inner = lambda command, cwd: fake_game(cwd, exit_reason="COST_CAP")

    def interrupted(*a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(*((rp, "cost_cap_ending") if where == "checking the ending"
                          else (hold, "place_hold")), interrupted)
    with pytest.raises(KeyboardInterrupt):
        rp.main(GAME_ARGS, paths=paths)
    assert _rows(paths) == [] and paths.lock.exists()
    kept = json.loads(paths.lock.read_text(encoding="utf-8"))["kept_because"]
    assert "add its row by hand" in kept
    assert "add its hold to" in kept and hold.HOLDS_NAME in kept   # no hold was written
    h.inner = lambda command, cwd: fake_game(cwd)
    assert rp.main(GAME_ARGS_2, paths=paths) == 2


def test_a_hold_that_cannot_be_written_and_a_failed_accounting_keep_both_reasons(
        world, monkeypatch):
    """Two problems, two reasons in the kept lock: the operator who follows the file must
    add the hold and the missing costs row, not only the first."""
    paths, h = world

    def cost_cap_odd_usage(command, cwd):
        fake_game(cwd, exit_reason="COST_CAP")
        _bad_step(cwd)
        return 0
    h.inner = cost_cap_odd_usage

    def read_only(*a, **k):
        raise PermissionError("read-only folder")
    monkeypatch.setattr(hold, "place_hold", read_only)
    with pytest.raises(pricing.PriceError):
        rp.main(GAME_ARGS, paths=paths)
    kept = json.loads(paths.lock.read_text(encoding="utf-8"))["kept_because"]
    assert "its hold could not be written" in kept and "add its row by hand" in kept


def test_an_accounting_failure_without_a_known_ending_says_to_check_for_a_hold(world):
    paths, h = world

    def unknown_odd_usage(command, cwd):
        fake_game(cwd, exit_reason="UNKNOWN")
        _bad_step(cwd)
        return 0
    h.inner = unknown_odd_usage
    with pytest.raises(pricing.PriceError):
        rp.main(GAME_ARGS, paths=paths)
    kept = json.loads(paths.lock.read_text(encoding="utf-8"))["kept_because"]
    assert "add its row by hand" in kept
    assert "if it ended COST_CAP or its list cost passed its harness cost guard of $120.00" \
        in kept and str(hold.holds_path(paths.lock)) in kept
    assert not hold.holds_path(paths.lock).exists()


PAST_THE_GUARD = {"prompt_tokens": 200_000_000}    # $150 list at $0.75 per million input


@pytest.mark.parametrize("ending", ["AGENT_ERROR", "UNKNOWN", "TIME_BUDGET", "API_ERROR",
                                    "GAME_WIN"])
def test_a_run_whose_spend_passed_its_guard_places_a_hold_whatever_its_ending(
        world, capsys, ending):
    """The guard is checked before each action, so a run can pass it and end otherwise: the
    step that crossed it failed (AGENT_ERROR), the inner process died before the agent
    recorded COST_CAP (UNKNOWN), or a win came first. That run still reached its run guard
    (PREREG §7.7), and an AGENT_ERROR or UNKNOWN ending is otherwise re-run (§7.5) without
    the researcher being asked."""
    paths, h = world
    h.inner = lambda command, cwd: fake_game(cwd, exit_reason=ending,
                                             total_extra=PAST_THE_GUARD)
    rp.main(GAME_ARGS, paths=paths)
    (row,) = _rows(paths)
    spent = float(row["cost_usd_list"])
    assert spent > 120
    (placed,) = _holds(paths)
    r = placed.record
    assert (r["exit_reason"], r["agent_exit_reason"]) == (ending, ending)
    assert r["spent_list_usd"] == pytest.approx(spent, abs=1e-6)
    assert r["reason"] == (f"spent ${spent:.2f} list, past its harness cost guard of $120.00 "
                           f"list (D22's run guard), and ended {ending} before the guard "
                           f"stopped it")
    assert _meta(paths, "arc_path")["hold_placed"] is True
    assert f"HOLD: run {placed.run_id} spent ${spent:.2f}" in capsys.readouterr().err
    h.inner = lambda command, cwd: fake_game(cwd)
    assert rp.main(GAME_ARGS_2, paths=paths) == 2


def test_a_blinded_pilot_past_its_guard_places_a_blinded_hold(world, capsys):
    paths, h = world
    h.inner = lambda command, cwd: fake_game(cwd, exit_reason="GAME_WIN",
                                             total_extra={"prompt_tokens": 30_000_000})
    rp.main(PILOT_ARGS, paths=paths)
    (placed,) = _holds(paths)
    assert placed.record["exit_reason"] == placed.record["agent_exit_reason"] \
        == rp.BLINDED_ENDING
    assert "past its harness cost guard of $15.00 list (set at its planned spend)" \
        in placed.record["reason"]
    assert "GAME_WIN" not in hold.holds_path(paths.lock).read_text(encoding="utf-8")
    assert "GAME_WIN" not in capsys.readouterr().err


def test_a_spend_at_the_guard_or_below_places_no_hold(world):
    """The guard stops a run once its spend exceeds the limit, so a spend equal to it is not
    past it."""
    paths, h = world
    exactly = int(120 / 0.75 * 1e6) - 2_000 - int(600 * 3.75 / 0.75)   # $120.00 list
    h.inner = lambda command, cwd: fake_game(cwd, exit_reason="AGENT_ERROR",
                                             total_extra={"prompt_tokens": exactly})
    rp.main(GAME_ARGS, paths=paths)
    (row,) = _rows(paths)
    assert float(row["cost_usd_list"]) == pytest.approx(120.0)
    assert not hold.holds_path(paths.lock).exists()


def test_the_harness_guard_record_places_the_hold_even_when_the_accounting_fails(world):
    """run_meta.json's cost_guard (patch 0010) shows a run past its guard before the
    accounting runs, so a run whose accounting fails still places its hold."""
    paths, h = world

    def past_guard_odd_usage(command, cwd):
        fake_game(cwd, exit_reason="AGENT_ERROR")
        meta = cwd / "recordings" / "ft09.benchmarkingagent.0123" / "run_meta.json"
        data = json.loads(meta.read_text(encoding="utf-8"))
        data["cost_guard"] = {"max_usd": 120.0, "estimated_cost_usd": 120.5}
        _write(meta, data)
        _bad_step(cwd)
        return 0
    h.inner = past_guard_odd_usage
    with pytest.raises(pricing.PriceError):
        rp.main(GAME_ARGS, paths=paths)
    (placed,) = _holds(paths)
    assert placed.record["spent_list_usd"] == 120.5
    assert placed.record["reason"].startswith("spent $120.50 list, past its harness cost guard "
                                              "of $120.00 list (D22's run guard)")
    kept = json.loads(paths.lock.read_text(encoding="utf-8"))["kept_because"]
    assert "add its row by hand" in kept and "add its hold to" not in kept


# ── A hold the ARC run could not record stops the PersistGym stream too ───
# With one lock per stream, the kept ARC lock alone would stop only ARC runs, while a hold
# stops paid runs of both streams (PREREG §0.3 line 12, §7.7). The kept lock is marked, and
# the guard of a PersistGym run refuses while it stands.

def _two_stream_world(tmp_path, monkeypatch):
    """`world` with the ARC lock under its real name, where the PersistGym lock goes too (as
    in the git common directory), and block 1 listing a PersistGym experiment too."""
    repo = _repo(tmp_path, prereg=FROZEN, decisions=decisions_text(
        BLOCK, experiments=(*EXPERIMENTS, "persistgym_pilot"), max_usd="500"))
    costs_csv = tmp_path / "costs.csv"
    costs_csv.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    paths = rp.Paths(repo=repo, costs=costs_csv, results=tmp_path / "results",
                     raw=tmp_path / "raw", lock=tmp_path / paidlock.lock_name(paidlock.ARC))
    return paths, FakeHarness(monkeypatch, tmp_path)


def _persistgym_guard(paths: rp.Paths) -> approval.PaidApproval:
    """What a PersistGym paid command runs before it may spend, beside the ARC lock."""
    pg_lock = paths.lock.with_name(paidlock.lock_name(paidlock.PERSISTGYM))
    with paidlock.paid_run_lock(pg_lock, run_id="luna-pilot", what="persistgym_pilot",
                                stream=paidlock.PERSISTGYM) as info:
        return approval.require_paid_run(
            lock=paidlock.HeldLock(pg_lock, info), approved_block=BLOCK,
            experiment="persistgym_pilot", planned_usd=1.0, costs_path=paths.costs,
            repo=paths.repo)


def test_a_hold_that_cannot_be_written_stops_persistgym_runs_too(tmp_path, monkeypatch):
    paths, h = _two_stream_world(tmp_path, monkeypatch)
    h.inner = lambda command, cwd: fake_game(cwd, exit_reason="COST_CAP")

    def read_only(*a, **k):
        raise PermissionError("read-only folder")
    with monkeypatch.context() as m:
        m.setattr(hold, "place_hold", read_only)
        assert rp.main(GAME_ARGS, paths=paths) == 0
    (row,) = _rows(paths)                                  # accounted; reservation gone
    assert not paidlock.reservation_path(paths.lock, rp.STREAM).exists()
    kept = json.loads(paths.lock.read_text(encoding="utf-8"))
    assert kept[paidlock.HOLD_NOT_RECORDED] is True
    with pytest.raises(approval.PaidCallsNotAllowed) as e:
        _persistgym_guard(paths)
    msg = str(e.value)
    assert f"the arc stream's paid-run lock {paths.lock} is kept by a run" in msg
    assert "its hold could not be written" in msg and row["run_id"] in msg
    assert "no paid run starts in either stream" in msg
    assert str(hold.holds_path(paths.lock)) in msg

    # The operator adds the hold by hand and deletes the lock: the hold itself now refuses.
    hold.place_hold(paths.lock, run_id=row["run_id"], experiment="arc_path",
                    reason="ended COST_CAP (added by hand)")
    paths.lock.unlink()
    with pytest.raises(approval.PaidCallsNotAllowed, match=f"1 hold stands: run "
                                                           f"{row['run_id']}"):
        _persistgym_guard(paths)


def test_an_unsettled_hold_stops_persistgym_runs_too(tmp_path, monkeypatch):
    """A Ctrl+C before the ending was checked: whether a hold stands is not known, so the
    kept lock stops both streams until the operator has checked."""
    paths, h = _two_stream_world(tmp_path, monkeypatch)
    h.inner = lambda command, cwd: fake_game(cwd, exit_reason="COST_CAP")

    def interrupted(*a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(rp, "cost_cap_ending", interrupted)
    with pytest.raises(KeyboardInterrupt):
        rp.main(GAME_ARGS, paths=paths)
    kept = json.loads(paths.lock.read_text(encoding="utf-8"))
    assert kept[paidlock.HOLD_NOT_RECORDED] is True and "add its hold to" in kept["kept_because"]
    with pytest.raises(approval.PaidCallsNotAllowed, match="no paid run starts in either "
                                                           "stream"):
        _persistgym_guard(paths)


def test_a_failed_costs_row_with_the_hold_settled_lets_persistgym_runs_go(tmp_path,
                                                                         monkeypatch):
    """A run that ended normally and whose costs row could not be written keeps the ARC lock
    (no ARC run starts) and its reservation, which a PersistGym run counts: no hold can
    stand, so the other stream goes on (PREREG §12, "Operational")."""
    paths, h = _two_stream_world(tmp_path, monkeypatch)
    h.inner = lambda command, cwd: fake_game(cwd)

    def disk_full(row, path):
        raise OSError("disk full")
    with monkeypatch.context() as m, pytest.raises(OSError, match="disk full"):
        m.setattr(costs, "append_row", disk_full)
        rp.main(GAME_ARGS, paths=paths)
    kept = json.loads(paths.lock.read_text(encoding="utf-8"))
    assert "add its row by hand" in kept["kept_because"]
    assert paidlock.HOLD_NOT_RECORDED not in kept
    granted = _persistgym_guard(paths)
    assert granted.reserved_block_usd == 125.0              # the ARC run's planned spend


def test_cost_cap_ending_reads_the_harness_files(tmp_path):
    assert rp.cost_cap_ending(tmp_path) is None            # nothing written
    fake_game(tmp_path, exit_reason="ACTION_BUDGET")
    assert rp.cost_cap_ending(tmp_path) is None
    _write(tmp_path / "out" / inner.RESULT_FILE, {"exit_reason": "COST_CAP"})
    assert rp.cost_cap_ending(tmp_path) == {"exit_reason": "ACTION_BUDGET",
                                            "agent_exit_reason": "ACTION_BUDGET"}
    (tmp_path / "recordings" / "ft09.benchmarkingagent.0123" / "run_meta.json").write_text(
        "garbage", encoding="utf-8")
    assert rp.cost_cap_ending(tmp_path) == {"exit_reason": "COST_CAP",
                                            "agent_exit_reason": None}


@pytest.mark.parametrize("guard, past", [
    ({"max_usd": 120.0, "estimated_cost_usd": 120.01}, True),
    ({"max_usd": 120, "estimated_cost_usd": 150}, True),
    ({"max_usd": 120.0, "estimated_cost_usd": 120.0}, False),   # the guard needs "exceeds"
    ({"max_usd": 120.0, "estimated_cost_usd": 3.5}, False),
    ({"max_usd": 120.0}, False), (None, False), ("garbage", False),
    ({"max_usd": True, "estimated_cost_usd": 5}, False),
    ({"max_usd": "120", "estimated_cost_usd": "150"}, False),
])
def test_cost_cap_ending_reads_the_harness_guard_record(tmp_path, guard, past):
    fake_game(tmp_path, exit_reason="UNKNOWN")
    meta = tmp_path / "recordings" / "ft09.benchmarkingagent.0123" / "run_meta.json"
    data = json.loads(meta.read_text(encoding="utf-8"))
    data["cost_guard"] = guard
    _write(meta, data)
    found = rp.cost_cap_ending(tmp_path)
    if past:
        assert found == {"exit_reason": "UNKNOWN", "agent_exit_reason": "UNKNOWN",
                         "spent_list_usd": float(guard["estimated_cost_usd"])}
    else:
        assert found is None


def test_no_model_call_means_no_costs_row(world):
    paths, h = world
    h.inner = lambda command, cwd: 1

    assert rp.main(GAME_ARGS, paths=paths) == 1

    assert _rows(paths) == []
    meta = _meta(paths, "arc_path")
    assert meta["cost_usd"]["costs_csv_row_appended"] is False and meta["n_calls"] == 0
    # nothing spent: the reservation goes, and no last run is recorded
    assert not paidlock.reservation_path(paths.lock, rp.STREAM).exists()
    assert not paidlock.last_run_path(paths.lock, rp.STREAM).exists()


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


def _refusal(paths, h, capsys, argv=GAME_ARGS) -> str:
    capsys.readouterr()
    _refused(paths, h, argv)
    assert not paths.lock.exists()
    return capsys.readouterr().err


def test_refused_when_a_merged_draft_gives_the_records_table(world, capsys):
    """A draft PREREG.md merged to main whose §7.1 gives the record's values (as the
    v0.3-draft's did on 2026-10-01) passes the §7.1 check, so only require_paid_run's
    frozen-PREREG check stands between it and a paid run. The draft in
    test_refused_when_prereg_is_not_frozen has no table, which the §7.1 check refuses on
    its own: that test still passes with the frozen check removed."""
    paths, h = world
    draft = prereg_text(RECORD, header=DRAFT_PREREG + "\n")
    assert prereg_freeze.problems(draft, RECORD) == []
    _commit_file(paths.repo, "PREREG.md", draft.encode(), "a draft with the record's table")
    push_main(paths.repo)

    err = _refusal(paths, h, capsys)

    assert "frozen, merged PREREG.md (PLAN §16.3): PREREG.md is not frozen" in err

    _commit_file(paths.repo, "PREREG.md", FROZEN.encode(), "the freeze")
    push_main(paths.repo)
    h.inner = lambda command, cwd: fake_game(cwd)
    assert rp.main(GAME_ARGS, paths=paths) == 0          # the draft was the only refusal


def test_freeze_git_path_is_the_record_the_launcher_loads():
    assert freeze.FREEZE_PATH.relative_to(runmeta.REPO_ROOT).as_posix() == rp.FREEZE_GIT_PATH


def test_refused_when_the_freeze_record_in_head_is_not_the_merged_one(world, capsys):
    paths, h = world
    _commit_file(paths.repo, rp.FREEZE_GIT_PATH, RECORD_BYTES + b"\n", "unmerged record")

    err = _refusal(paths, h, capsys)

    assert ("arc/config_freeze.json in HEAD differs from arc/config_freeze.json on "
            "origin/main") in err


def test_refused_when_the_freeze_record_is_not_committed_or_not_merged(tmp_path, monkeypatch,
                                                                       capsys):
    repo = _repo(tmp_path, prereg=FROZEN, record=None,
                 decisions=decisions_text(BLOCK, experiments=EXPERIMENTS, max_usd="500"))
    costs_csv = tmp_path / "costs.csv"
    costs_csv.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    paths = rp.Paths(repo=repo, costs=costs_csv, results=tmp_path / "results",
                     raw=tmp_path / "raw", lock=tmp_path / "paid.lock")
    h = FakeHarness(monkeypatch, tmp_path)

    assert "arc/config_freeze.json is not in the HEAD commit" in _refusal(paths, h, capsys)

    _commit_file(repo, rp.FREEZE_GIT_PATH, RECORD_BYTES, "record, not merged")
    assert "arc/config_freeze.json is not on origin/main" in _refusal(paths, h, capsys)

    push_main(repo)
    h.inner = lambda command, cwd: fake_game(cwd)
    assert rp.main(GAME_ARGS, paths=paths) == 0


def test_refused_when_the_loaded_record_is_not_the_committed_one(world, tmp_path, capsys):
    """make_plan reads only the profiles, so a record that differs elsewhere would plan the
    run; the launcher still uses only the merged file."""
    paths, h = world
    record = json.loads(json.dumps(RECORD))
    record["patched_tree"] = "f" * 40
    edited = tmp_path / "edited.json"
    edited.write_text(freeze.render(record), encoding="utf-8")
    paths = rp.Paths(**{**vars(paths), "freeze": edited})

    err = _refusal(paths, h, capsys)

    assert "differs from arc/config_freeze.json in HEAD and on origin/main" in err


S2_MISMATCH = (f"S2 config hash is {RECORD['profiles']['S2']['sha256']} in the freeze record "
               f"but {'0' * 64} in §7.1")


@pytest.mark.parametrize("argv, values, message", [
    (GAME_ARGS, {"S2": "0" * 64}, S2_MISMATCH),
    (PILOT_ARGS, {"S2": "0" * 64}, S2_MISMATCH),
    (ACCEPT_ARGS, {"S2": "0" * 64}, S2_MISMATCH),
    (GAME_ARGS, {"series": "1" * 64}, "patch-series SHA-256 is"),
    (GAME_ARGS, {"pin": "2" * 40}, "upstream pin is"),
    (GAME_ARGS, {"commit": "3" * 40}, "patched commit is"),
    (GAME_ARGS, {"S0": "TBD"}, "§7.1 gives no S0 config hash"),
])
def test_refused_when_the_prereg_table_differs_from_the_record(world, capsys, argv, values,
                                                               message):
    paths, h = world
    _commit_file(paths.repo, "PREREG.md", prereg_text(RECORD, **values).encode(), "table")
    push_main(paths.repo)

    err = _refusal(paths, h, capsys, argv)

    assert "does not match the config freeze table in the frozen PREREG.md §7.1" in err
    assert message in err


@pytest.mark.parametrize("prereg, message", [
    (FROZEN_HEADER, "PREREG.md has no section 7.1"),
    (prereg_text(RECORD, **dict.fromkeys(("S0", "S1", "S2", "S4", "series", "pin", "pin7",
                                          "commit", "tree"), "TBD")),
     "PREREG.md §7.1 has no filled config freeze table"),
])
def test_refused_when_the_frozen_prereg_has_no_filled_table(world, capsys, prereg, message):
    paths, h = world
    _commit_file(paths.repo, "PREREG.md", prereg.encode(), "frozen without a table")
    push_main(paths.repo)

    assert message in _refusal(paths, h, capsys)


def test_the_table_is_read_from_the_merged_prereg_not_the_working_tree(world):
    paths, _ = world
    git_in(paths.repo, "fetch", "-q", "origin")
    assert rp.freeze_record_not_preregistered(paths.repo, RECORD) is None
    (paths.repo / "PREREG.md").write_text(prereg_text(RECORD, S1="0" * 64), encoding="utf-8")
    assert rp.freeze_record_not_preregistered(paths.repo, RECORD) is None    # uncommitted

    _commit_file(paths.repo, "PREREG.md", prereg_text(RECORD, S1="0" * 64).encode(), "local")
    assert rp.freeze_record_not_preregistered(paths.repo, RECORD) == (
        "PREREG.md in HEAD differs from PREREG.md on origin/main")


def test_refused_when_the_patch_files_changed_since_the_freeze(world, monkeypatch, capsys):
    """A merged series the record was not regenerated for: prepare_harness's own check."""
    paths, h = world
    git_in(paths.repo, "rm", "-q", f"{rp.PATCHES_GIT_PATH}/{PATCHES[-1].name}")
    git_in(paths.repo, "commit", "-q", "-m", "drop the last patch")
    push_main(paths.repo)
    monkeypatch.setattr(ap, "patch_files", lambda *a: PATCHES[:-1])

    err = _refusal(paths, h, capsys)

    assert "does not match arc/patches" in err and h.calls == ["pin"]


def test_patches_git_path_is_the_series_the_launcher_applies():
    assert ap.PATCH_DIR.relative_to(runmeta.REPO_ROOT).as_posix() == rp.PATCHES_GIT_PATH


@pytest.mark.parametrize("argv", [GAME_ARGS, PILOT_ARGS, ACCEPT_ARGS])
def test_refused_when_a_patch_was_left_out_of_the_merged_commit(tmp_path, monkeypatch,
                                                               capsys, argv):
    """The merged record and §7.1 name the whole series (its SHA-256 binds the bytes), but
    one patch file is not committed: untracked here, so not even git_dirty. Refused before
    the harness is built."""
    paths, h = _world(tmp_path, monkeypatch, patches=PATCHES[:-1])

    err = _refusal(paths, h, capsys, argv)

    assert "paid ARC runs need the merged patch series" in err
    assert "are not the .patch files committed in arc/patches" in err
    assert h.calls == []


def test_refused_when_a_patch_change_is_committed_but_not_merged(world, capsys):
    paths, h = world
    first = PATCHES[0]
    _commit_file(paths.repo, f"{rp.PATCHES_GIT_PATH}/{first.name}",
                 first.read_bytes() + b"\n", "patch change, not merged")

    err = _refusal(paths, h, capsys)

    assert ("arc/patches in HEAD differs from arc/patches on origin/main (an unmerged "
            "patch?)") in err
    assert h.calls == []


def test_refused_when_a_patch_file_is_not_the_committed_one(world, capsys):
    """The file this run would apply is not the merged blob (an uncommitted edit)."""
    paths, h = world
    last = PATCHES[-1]
    _commit_file(paths.repo, f"{rp.PATCHES_GIT_PATH}/{last.name}", b"other bytes\n",
                 "merged bytes differ from the file on disk")
    push_main(paths.repo)

    err = _refusal(paths, h, capsys)

    assert f"arc/patches/{last.name} differs from the committed file" in err
    assert h.calls == []


def test_refused_when_the_patch_series_is_not_committed(tmp_path, monkeypatch, capsys):
    paths, h = _world(tmp_path, monkeypatch, patches=None)
    assert "arc/patches is not in the HEAD commit" in _refusal(paths, h, capsys)


def test_refused_when_the_patch_series_is_committed_but_not_merged(tmp_path, monkeypatch,
                                                                   capsys):
    paths, h = _world(tmp_path, monkeypatch, patches=None)
    (paths.repo / rp.PATCHES_GIT_PATH).mkdir(parents=True)
    for patch in PATCHES:
        (paths.repo / rp.PATCHES_GIT_PATH / patch.name).write_bytes(patch.read_bytes())
    git_in(paths.repo, "add", rp.PATCHES_GIT_PATH)
    git_in(paths.repo, "commit", "-q", "-m", "patch series, not merged")

    assert "arc/patches is not on origin/main" in _refusal(paths, h, capsys)

    push_main(paths.repo)
    h.inner = lambda command, cwd: fake_game(cwd)
    assert rp.main(GAME_ARGS, paths=paths) == 0


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


# ── Amendment R7: replacing a run ended by the summarizer failure ──────

R7_REPLACED = "20261010T030159Z-S2-ft09-s101"      # a D19 re-run, the unit's counted run
R7_REPLACEMENT = "20261011T000000Z-S2-ft09-s201"


def _game_args(config: str, game: str, seed: int, *extra: str,
               experiment: str = "arc_path") -> list[str]:
    return ["--approved-block", BLOCK, "--experiment", experiment, "--config", config,
            "--game", game, "--seed", str(seed), "--planned-usd", "125", *extra]


R7_ARGS = _game_args("S2", "ft09", 201, "--r7-replaces", R7_REPLACED)
R7_RERUN_ARGS = _game_args("S2", "ft09", 301, "--rerun-of", R7_REPLACEMENT)


def test_the_frozen_s1_and_s2_profiles_have_r7s_summary_budget():
    """Patch 0018 (R7): S1 and S2 summarize with the action requests' output budget; S0
    has no summary and S4 keeps 8,192."""
    budgets = {lb: rp._summary_budget(e["config"]) for lb, e in RECORD["profiles"].items()}
    assert budgets == {"S0": None, "S1": rp.R7_SUMMARY_BUDGET, "S2": rp.R7_SUMMARY_BUDGET,
                       "S4": rp.PRE_R7_SUMMARY_BUDGET}
    for lb in rp.R7_CONFIGS:
        request = RECORD["profiles"][lb]["config"]["request"]
        assert request["generation_config"]["max_output_tokens"] == rp.R7_SUMMARY_BUDGET


@pytest.mark.parametrize("argv, replaced", [
    (R7_ARGS, R7_REPLACED),
    (_game_args("S2", "ft09", 201, "--r7-replaces", "20261010T020247Z-S2-ft09-s1"),
     "20261010T020247Z-S2-ft09-s1"),                                   # an original
    (_game_args("S1", "cd82", 202, "--r7-replaces", "20261012T010203Z-S1-cd82-s102"),
     "20261012T010203Z-S1-cd82-s102"),
    (_game_args("S2", "ft09-0d8bbf25", 201, "--r7-replaces", R7_REPLACED), R7_REPLACED),
])
def test_plan_of_an_r7_replacement(argv, replaced):
    plan = _plan(argv)

    assert plan.r7_replaces == replaced and plan.rerun_of is None
    assert plan.run_id.endswith(f"-{argv[5]}-{argv[7][:4]}-s{argv[9]}")
    assert plan.experiment == "arc_path" and plan.cost_cap_usd == 120.0


def test_plan_of_an_r7_replacements_d19_rerun():
    plan = _plan(R7_RERUN_ARGS)
    assert (plan.rerun_of, plan.r7_replaces, plan.seed) == (R7_REPLACEMENT, None, 301)


@pytest.mark.parametrize("argv, message", [
    ([*R7_ARGS, "--rerun-of", "20261010T020247Z-S2-ft09-s1"], "do not go together"),
    (_game_args("S2", "ft09", 201, "--max-actions", "50", "--r7-replaces", R7_REPLACED,
                experiment="arc_pilot"), "counted arc_path runs only"),
    (_game_args("S0", "ft09", 201, "--r7-replaces", "20261010T030159Z-S0-ft09-s101"),
     "S1 and S2 only"),
    (_game_args("S4", "ft09", 201, "--r7-replaces", "20261010T030159Z-S4-ft09-s1"),
     "S1 and S2 only"),
    (_game_args("S2", "ft09", 1, "--r7-replaces", R7_REPLACED), "seed r \\+ 200"),
    (_game_args("S2", "ft09", 101, "--r7-replaces", R7_REPLACED), "seed r \\+ 200"),
    (_game_args("S2", "ft09", 301, "--r7-replaces", R7_REPLACED), "seed r \\+ 200"),
    (_game_args("S2", "ft09", 202, "--r7-replaces", R7_REPLACED), "not a run of this unit"),
    (_game_args("S1", "ft09", 201, "--r7-replaces", R7_REPLACED), "not a run of this unit"),
    (_game_args("S2", "r11l", 201, "--r7-replaces", R7_REPLACED), "not a run of this unit"),
    (_game_args("S2", "ft09", 201, "--r7-replaces", "20261011T000000Z-S2-ft09-s201"),
     "not a run of this unit"),                          # a replacement is never replaced
    (_game_args("S2", "ft09", 201, "--r7-replaces", "ft09-s2-run"), "not a run of this unit"),
    (_game_args("S2", "ft09", 201, "--r7-replaces", "../x"), "--r7-replaces must be a run_id"),
    ([*ACCEPT_ARGS, "--r7-replaces", R7_REPLACED], "plays no game"),
    (_game_args("S2", "ft09", 201), "labels an R7 replacement"),
    (_game_args("S1", "cd82", 202), "labels an R7 replacement"),
    # The D19 re-run of an R7 replacement: seed 301/302, --rerun-of that replacement.
    (_game_args("S2", "ft09", 301), "D19 re-run of an R7"),
    (_game_args("S2", "ft09", 301, "--rerun-of", R7_REPLACED), "D19 re-run of an R7"),
    (_game_args("S2", "ft09", 302, "--rerun-of", R7_REPLACEMENT), "D19 re-run of an R7"),
    (_game_args("S1", "ft09", 301, "--rerun-of", R7_REPLACEMENT), "D19 re-run of an R7"),
    (_game_args("S2", "ft09", 101, "--rerun-of", R7_REPLACEMENT), "D19 re-run of an R7"),
    (_game_args("S2", "ft09", 401, "--rerun-of", "20261012T000000Z-S2-ft09-s301"),
     "no further run"),
])
def test_plan_refuses_what_r7_does_not_allow(argv, message):
    with pytest.raises(rp.Refused, match=message):
        _plan(argv)


def test_plan_refuses_an_r7_replacement_under_the_pre_r7_profile():
    record = json.loads(json.dumps(RECORD))
    record["profiles"]["S2"]["config"]["runtime"]["compaction"][
        "summary_max_output_tokens"] = rp.PRE_R7_SUMMARY_BUDGET
    with pytest.raises(rp.Refused, match="not R7's 65536"):
        _plan(R7_ARGS, record=record)


def test_r7_seeds_are_free_outside_counted_runs():
    plan = _plan(_game_args("S2", "ft09", 201, "--max-actions", "50", experiment="arc_pilot"))
    assert plan.seed == 201 and plan.r7_replaces is None


def _past_run(paths: rp.Paths, run_id: str, *, agent_exit_reason: str = "AGENT_ERROR",
              budget: int = rp.PRE_R7_SUMMARY_BUDGET, log: str | None = rp.SUMMARIZER_FAILURE,
              **fields) -> None:
    """A committed counted run's meta.json and, unless `log` is None, its raw harness.log
    (`log` "" writes one without the summarizer failure)."""
    label, game, seed = rp.run_id_parts(run_id)
    config = json.loads(json.dumps(RECORD["profiles"][label]["config"]))
    if label in rp.R7_CONFIGS:
        config["runtime"]["compaction"]["summary_max_output_tokens"] = budget
    _write(paths.results / "arc_path" / run_id / "meta.json", {
        "experiment": "arc_path", "run_id": run_id, "cell_or_config": label,
        "game_requested": game, "seeds": {"replicate_seed": seed},
        "exit_reason": agent_exit_reason, "agent_exit_reason": agent_exit_reason,
        "rerun_of": None, "r7_replaces": None, "config": config, **fields})
    if log is not None:
        path = paths.raw / "arc_path" / run_id / "harness.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("2026-10-10 03:02:20,001 | INFO | step 1\n" + (
            f"2026-10-10 03:10:54,389 | ERROR | Harness summary compaction failed before step "
            f"113 after 209.360s: {log} after 4 response failures.\n" if log else ""),
            encoding="utf-8")


def test_an_r7_replacement_is_accounted_and_recorded(world):
    paths, h = world
    _past_run(paths, "20261010T020247Z-S2-ft09-s1")
    _past_run(paths, R7_REPLACED, rerun_of="20261010T020247Z-S2-ft09-s1")
    h.inner = lambda command, cwd: fake_game(cwd)

    assert rp.main(R7_ARGS, paths=paths) == 0

    assert h.calls == ["pin", "create", "apply", "sync", "resolve", "inner", "remove"]
    (command,) = h.commands
    s2 = RECORD["profiles"]["S2"]
    assert command[command.index("--config") + 1] == s2["config_id"]
    assert command[command.index("--expect-config-hash") + 1] == s2["sha256"]
    tags = command[command.index("--tags") + 1].split(",")
    assert tags[:4] == ["persistgym", "arc_path", "S2", "seed-201"]
    (row,) = _rows(paths)
    assert f"r7_replaces={R7_REPLACED}" in row["notes"] and "rerun_of=" not in row["notes"]
    assert row["run_id"].endswith("-S2-ft09-s201")
    meta = json.loads((paths.results / "arc_path" / row["run_id"] / "meta.json").read_text(
        encoding="utf-8"))
    assert (meta["r7_replaces"], meta["rerun_of"]) == (R7_REPLACED, None)
    assert meta["seeds"]["replicate_seed"] == 201 and meta["config_hash"] == s2["sha256"]
    assert rp._summary_budget(meta["config"]) == rp.R7_SUMMARY_BUDGET
    assert not paths.lock.exists()


def test_an_r7_replacements_d19_rerun_is_recorded(world):
    paths, h = world
    _past_run(paths, R7_REPLACEMENT, budget=rp.R7_SUMMARY_BUDGET, log=None,
              r7_replaces=R7_REPLACED)
    h.inner = lambda command, cwd: fake_game(cwd)

    assert rp.main(R7_RERUN_ARGS, paths=paths) == 0

    (row,) = _rows(paths)
    assert f"rerun_of={R7_REPLACEMENT}" in row["notes"] and "r7_replaces=" not in row["notes"]
    meta = json.loads((paths.results / "arc_path" / row["run_id"] / "meta.json").read_text(
        encoding="utf-8"))
    assert (meta["rerun_of"], meta["r7_replaces"]) == (R7_REPLACEMENT, None)


def test_refused_when_the_d19_rerun_target_is_not_an_r7_replacement(world, capsys):
    paths, h = world
    _past_run(paths, R7_REPLACEMENT, budget=rp.R7_SUMMARY_BUDGET, log=None)  # no r7_replaces

    assert rp.main(R7_RERUN_ARGS, paths=paths) == 2

    assert "has no meta.json of an R7 replacement" in capsys.readouterr().err
    assert h.calls == [] and not paths.lock.exists()


@pytest.mark.parametrize("setup, message", [
    (lambda p: None, "no meta.json of that run"),
    (lambda p: _past_run(p, R7_REPLACED, agent_exit_reason="ACTION_BUDGET"),
     "agent_exit_reason is ACTION_BUDGET, not AGENT_ERROR"),
    (lambda p: _past_run(p, R7_REPLACED, budget=rp.R7_SUMMARY_BUDGET),
     "summary_max_output_tokens 65536, not the pre-R7 8192"),
    (lambda p: _past_run(p, R7_REPLACED, log=None), "cannot be read"),
    (lambda p: _past_run(p, R7_REPLACED, log=""), "does not show the summarizer failure"),
    (lambda p: _past_run(p, R7_REPLACED, game_requested="r11l"), "not this unit"),
    (lambda p: _past_run(p, R7_REPLACED, seeds={"replicate_seed": 102}), "not this unit"),
    (lambda p: _past_run(p, R7_REPLACED, experiment="arc_pilot"), "not this unit"),
    (lambda p: [_past_run(p, R7_REPLACED),
                _past_run(p, "20261010T050000Z-S2-ft09-s1", rerun_of=R7_REPLACED)],
     "re-runs it \\(D19\\)"),
    (lambda p: [_past_run(p, R7_REPLACED),
                _past_run(p, R7_REPLACEMENT, budget=rp.R7_SUMMARY_BUDGET,
                          r7_replaces="20261010T020247Z-S2-ft09-s1")],
     "already has an R7 replacement"),
])
def test_refused_unless_the_replaced_run_ended_by_the_summarizer_failure(world, capsys, setup,
                                                                         message):
    paths, h = world
    setup(paths)

    assert rp.main(R7_ARGS, paths=paths) == 2

    err = capsys.readouterr().err
    assert re.search(message, err), err
    assert h.calls == [] and not paths.lock.exists() and _rows(paths) == []


def test_check_r7_files_leaves_other_runs_alone(world):
    paths, _ = world          # no results at all: only R7 runs and S1/S2 re-runs need them
    for argv in (GAME_ARGS, PILOT_ARGS, ACCEPT_ARGS,
                 _game_args("S0", "ft09", 101, "--rerun-of", "20261010T020247Z-S0-ft09-s1"),
                 _game_args("S4", "ft09", 101, "--rerun-of", "20261010T020247Z-S4-ft09-s1"),
                 _game_args("S2", "ft09", 101, "--rerun-of", "20261010T020247Z-S2-ft09-s1",
                            "--max-actions", "50", experiment="arc_pilot")):
        rp.check_r7_files(_plan(argv), paths)


# ── D19 re-runs under R7: a run already replaced; a pre-R7 S1/S2 run ──────

S2_ORIGINAL = "20261010T084933Z-S2-r11l-s1"
S2_RERUN_ARGS = _game_args("S2", "r11l", 101, "--rerun-of", S2_ORIGINAL)


def _refused_with(paths, h, capsys, argv, message) -> str:
    assert rp.main(argv, paths=paths) == 2
    err = capsys.readouterr().err
    assert re.search(message, err), err
    assert h.calls == [] and not paths.lock.exists() and _rows(paths) == []
    assert not paidlock.reservation_path(paths.lock, rp.STREAM).exists()
    return err


@pytest.mark.parametrize("setup, argv, message", [
    # a plain D19 re-run of an S0 run that already has its re-run
    (lambda p: [_past_run(p, "20261010T000000Z-S0-ft09-s1", agent_exit_reason="API_ERROR"),
                _past_run(p, "20261010T010000Z-S0-ft09-s101",
                          rerun_of="20261010T000000Z-S0-ft09-s1")],
     _game_args("S0", "ft09", 101, "--rerun-of", "20261010T000000Z-S0-ft09-s1"),
     "already replaced: 20261010T010000Z-S0-ft09-s101 re-runs it \\(D19 allows one"),
    # a D19 re-run of a run an R7 replacement replaced (the late re-run R7 rules out)
    (lambda p: [_past_run(p, S2_ORIGINAL),
                _past_run(p, "20261011T000000Z-S2-r11l-s201", budget=rp.R7_SUMMARY_BUDGET,
                          r7_replaces=S2_ORIGINAL)],
     S2_RERUN_ARGS,
     "already replaced: 20261011T000000Z-S2-r11l-s201 replaces it under R7"),
    # a second D19 re-run of an R7 replacement: its one re-run is the unit's last run
    (lambda p: [_past_run(p, R7_REPLACEMENT, budget=rp.R7_SUMMARY_BUDGET, log=None,
                          r7_replaces=R7_REPLACED),
                _past_run(p, "20261012T000000Z-S2-ft09-s301", budget=rp.R7_SUMMARY_BUDGET,
                          log=None, rerun_of=R7_REPLACEMENT)],
     R7_RERUN_ARGS,
     "already replaced: 20261012T000000Z-S2-ft09-s301 re-runs it"),
])
def test_refused_when_the_rerun_target_is_already_replaced(world, capsys, setup, argv,
                                                           message):
    paths, h = world
    setup(paths)
    _refused_with(paths, h, capsys, argv, message)


@pytest.mark.parametrize("config, budget, message", [
    ("S2", rp.PRE_R7_SUMMARY_BUDGET, "it played under summary_max_output_tokens 8192"),
    ("S1", rp.PRE_R7_SUMMARY_BUDGET, "it played under summary_max_output_tokens 8192"),
    ("S2", None, "no meta.json of it in .*, so the summary budget it played under is unknown"),
])
def test_a_plain_d19_rerun_of_a_pre_r7_s1_or_s2_run_is_refused(world, capsys, config, budget,
                                                               message):
    """Under R7's frozen profile a D19 re-run of a run that played under 8,192 would play
    under 65,536 without being marked as an R7 replacement: refused, with the R7 replacement
    named as the way to go if the run ended by the summarizer failure."""
    paths, h = world
    original = f"20261010T084933Z-{config}-r11l-s1"
    if budget is not None:
        _past_run(paths, original, budget=budget)
    argv = _game_args(config, "r11l", 101, "--rerun-of", original)
    err = _refused_with(paths, h, capsys, argv, message)
    assert "would play under R7's config without being an R7 replacement" in err
    assert f"--r7-replaces {original} --seed 201" in err


def test_a_plain_d19_rerun_of_an_s2_run_under_r7s_budget_is_recorded(world):
    paths, h = world
    _past_run(paths, S2_ORIGINAL, agent_exit_reason="API_ERROR", budget=rp.R7_SUMMARY_BUDGET,
              log=None)
    h.inner = lambda command, cwd: fake_game(cwd)

    assert rp.main(S2_RERUN_ARGS, paths=paths) == 0

    (row,) = _rows(paths)
    assert f"rerun_of={S2_ORIGINAL}" in row["notes"] and row["run_id"].endswith("-s101")


def test_a_plain_d19_rerun_of_s0_or_s4_needs_no_files(world):
    """S0's and S4's profiles did not change under R7: a re-run of either reads only the other
    runs' links (none here)."""
    paths, h = world
    h.inner = lambda command, cwd: fake_game(cwd)
    argv = _game_args("S4", "ft09", 101, "--rerun-of", "20261010T000000Z-S4-ft09-s1")
    assert rp.main(argv, paths=paths) == 0


@pytest.mark.parametrize("argv, before, landed, message", [
    (_game_args("S0", "ft09", 101, "--rerun-of", "20261010T000000Z-S0-ft09-s1"),
     lambda p: _past_run(p, "20261010T000000Z-S0-ft09-s1", agent_exit_reason="API_ERROR"),
     lambda p: _past_run(p, "20261010T010000Z-S0-ft09-s101",
                         rerun_of="20261010T000000Z-S0-ft09-s1"),
     "already replaced: 20261010T010000Z-S0-ft09-s101 re-runs it"),
    (R7_ARGS,
     lambda p: _past_run(p, R7_REPLACED),
     lambda p: _past_run(p, "20261010T235959Z-S2-ft09-s201", budget=rp.R7_SUMMARY_BUDGET,
                         log=None, r7_replaces=R7_REPLACED),
     "already has an R7 replacement, 20261010T235959Z-S2-ft09-s201"),
])
def test_the_file_checks_run_again_under_the_lock(world, monkeypatch, capsys, argv, before,
                                                  landed, message):
    """A run that lands between the first file check and the lock (here: while check_paid
    runs) is seen by the second check, under the lock: refused before the harness is built,
    and the lock and the spend reservation are released."""
    paths, h = world
    before(paths)
    check_paid = rp.check_paid

    def check_paid_then_a_run_lands(plan, paths_, lock, record):
        granted = check_paid(plan, paths_, lock, record)
        assert paidlock.reservation_path(paths.lock, rp.STREAM).exists()
        landed(paths)
        return granted
    monkeypatch.setattr(rp, "check_paid", check_paid_then_a_run_lands)

    _refused_with(paths, h, capsys, argv, message)


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
