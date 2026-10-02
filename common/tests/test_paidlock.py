"""One paid run at a time (common/paidlock.py)."""

from __future__ import annotations

import json
import subprocess

import pytest

from common import hold, paidlock
from common.tests.gitrepo import git_in


def test_lock_is_exclusive_and_released(tmp_path):
    path = tmp_path / paidlock.LOCK_NAME
    with paidlock.paid_run_lock(path, run_id="run-1", what="arc_pilot: S0 on ft09") as info:
        held = json.loads(path.read_text(encoding="utf-8"))
        assert held["run_id"] == "run-1" and held["token"] == info["token"]
        with (pytest.raises(paidlock.LockHeld, match="run-1") as e,
              paidlock.paid_run_lock(path, run_id="run-2", what="second")):
            pytest.fail("a second paid run got the lock")
        assert "delete that file by hand" in str(e.value)
        # a crashed run may have reached its run guard: the operator checks for its hold too
        assert "if it ended COST_CAP or passed its run guard" in str(e.value)
        assert str(path.with_name(hold.HOLDS_NAME)) in str(e.value)
        assert path.exists()                       # the refused run left it alone
    assert not path.exists()

    with paidlock.paid_run_lock(path, run_id="run-3", what="later"):
        assert path.exists()


def test_lock_is_released_when_the_run_raises(tmp_path):
    path = tmp_path / paidlock.LOCK_NAME
    with (pytest.raises(KeyboardInterrupt),
          paidlock.paid_run_lock(path, run_id="run-1", what="x")):
        raise KeyboardInterrupt
    assert not path.exists()


def test_a_lock_that_is_not_ours_is_not_removed(tmp_path):
    path = tmp_path / paidlock.LOCK_NAME
    with paidlock.paid_run_lock(path, run_id="run-1", what="x"):
        path.write_text(json.dumps({"run_id": "other", "token": "someone-else"}),
                        encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8"))["token"] == "someone-else"


def test_a_stale_lock_refuses_until_deleted(tmp_path):
    path = tmp_path / paidlock.LOCK_NAME
    path.write_text("garbage", encoding="utf-8")
    with (pytest.raises(paidlock.LockHeld, match="garbage"),
          paidlock.paid_run_lock(path, run_id="run-1", what="x")):
        pass
    path.unlink()
    with paidlock.paid_run_lock(path, run_id="run-1", what="x"):
        pass


def test_lock_path_is_shared_by_worktrees(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git_in(repo, "init", "-q")
    (repo / "f").write_text("x", encoding="utf-8")
    git_in(repo, "add", "f")
    git_in(repo, "commit", "-q", "-m", "x")
    git_in(repo, "worktree", "add", "-q", str(tmp_path / "wt"))

    main_lock = paidlock.lock_path(repo)
    assert main_lock == (repo / ".git" / paidlock.LOCK_NAME).resolve()
    assert paidlock.lock_path(tmp_path / "wt") == main_lock


def test_lock_path_outside_a_repository(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    with pytest.raises(paidlock.LockHeld, match="git common directory"):
        paidlock.lock_path(tmp_path)


def test_git_missing(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(paidlock.LockHeld, match="git common directory"):
        paidlock.lock_path(tmp_path)


def test_keep_leaves_the_lock_held_with_the_reason(tmp_path):
    path = tmp_path / paidlock.LOCK_NAME
    with paidlock.paid_run_lock(path, run_id="run-1", what="x") as info:
        paidlock.keep(path, info, "run-1 spent money costs.csv does not show")
    held = json.loads(path.read_text(encoding="utf-8"))
    assert held["run_id"] == "run-1" and held["token"] != info["token"]
    with (pytest.raises(paidlock.LockHeld, match="costs.csv does not show"),
          paidlock.paid_run_lock(path, run_id="run-2", what="y")):
        pass


def test_a_second_keep_adds_its_reason_to_the_first(tmp_path):
    """A run with two problems (say, a hold that could not be written and a costs row that
    could not be written) keeps both reasons, so the operator who follows the file fixes
    both. The second keep passes what the first returned; the run's own token no longer
    matches after the first."""
    path = tmp_path / paidlock.LOCK_NAME
    with paidlock.paid_run_lock(path, run_id="run-1", what="x") as info:
        first = paidlock.keep(path, info, "add the hold by hand")
        assert first is not None and first["token"] != info["token"]
        assert paidlock.keep(path, info, "lost") is None           # the old token: left alone
        second = paidlock.keep(path, first, "add the costs row by hand")
        assert second is not None and second["token"] != first["token"]
        assert paidlock.keep(path, second, "add the costs row by hand") is not None  # no repeat
    held = json.loads(path.read_text(encoding="utf-8"))
    assert held["kept_because"] == "add the hold by hand ALSO: add the costs row by hand"
    assert held["run_id"] == "run-1"
    with (pytest.raises(paidlock.LockHeld, match="hold by hand ALSO: add the costs row"),
          paidlock.paid_run_lock(path, run_id="run-2", what="y")):
        pass


def test_keep_leaves_a_lock_that_is_not_ours_alone(tmp_path):
    path = tmp_path / paidlock.LOCK_NAME
    with paidlock.paid_run_lock(path, run_id="run-1", what="x") as info:
        path.write_text(json.dumps({"run_id": "other", "token": "someone-else"}),
                        encoding="utf-8")
        paidlock.keep(path, info, "why")
    assert json.loads(path.read_text(encoding="utf-8")) == {"run_id": "other",
                                                            "token": "someone-else"}


def test_a_held_lock_holds_only_its_own_token(tmp_path):
    """What the code that spends checks (`common.approval.require_paid_run`): the lock file
    still holds this run's token."""
    path = tmp_path / paidlock.LOCK_NAME
    with paidlock.paid_run_lock(path, run_id="run-1", what="x") as info:
        held = paidlock.HeldLock(path, info)
        assert held.holds()
        assert not paidlock.HeldLock(path, {**info, "token": "someone-else"}).holds()
        assert not paidlock.HeldLock(path, {"run_id": "run-1"}).holds()   # no token
        paidlock.keep(path, info, "spend not in costs.csv")
        assert not held.holds()                    # keep gave the file a new token
    path.write_text(json.dumps({"run_id": "run-2"}), encoding="utf-8")
    assert not paidlock.HeldLock(path, {"run_id": "run-2"}).holds()      # neither has one
    for text in ("[]", "garbage", ""):
        path.write_text(text, encoding="utf-8")
        assert not held.holds()
    path.unlink()
    assert not held.holds()


def test_the_last_runs_row_must_be_in_the_ledger(tmp_path):
    lock = tmp_path / paidlock.LOCK_NAME
    assert paidlock.last_run_missing(lock, []) is None        # no paid run recorded yet

    paidlock.record_last_run(lock, run_id="run-1", costs_csv=tmp_path / "a" / "costs.csv")
    assert paidlock.last_run_missing(lock, [{"run_id": "run-1"}]) is None
    reason = paidlock.last_run_missing(lock, [{"run_id": "run-0"}])
    assert "run-1" in reason and "not in this checkout" in reason

    paidlock.last_run_path(lock).write_text("garbage", encoding="utf-8")
    assert "unreadable" in paidlock.last_run_missing(lock, [{"run_id": "run-1"}])
    for text in ("[]", '"run-1"', "{}"):
        paidlock.last_run_path(lock).write_text(text, encoding="utf-8")
        assert "unreadable" in paidlock.last_run_missing(lock, [{"run_id": "run-1"}])


def test_a_reused_run_id_needs_the_newest_row(tmp_path):
    """A run ID need not be unique (a PersistGym `--run-id` can be given again): an older
    row with the same ID must not stand in for the last run's row, so the record names the
    row's timestamp too."""
    lock = tmp_path / paidlock.LOCK_NAME
    old = {"run_id": "probe", "timestamp_utc": "2026-10-02T10:00:00+00:00"}
    new = {"run_id": "probe", "timestamp_utc": "2026-10-02T11:00:00+00:00"}
    paidlock.record_last_run(lock, run_id="probe", costs_csv=tmp_path / "costs.csv",
                             timestamp_utc=new["timestamp_utc"])
    record = json.loads(paidlock.last_run_path(lock).read_text(encoding="utf-8"))
    assert record["row_timestamp_utc"] == new["timestamp_utc"]
    reason = paidlock.last_run_missing(lock, [old])          # another checkout's ledger
    assert "probe" in reason and new["timestamp_utc"] in reason
    assert "not in this checkout" in reason
    assert paidlock.last_run_missing(lock, [old, new]) is None

    # a record written without a timestamp matches on the run ID alone
    paidlock.record_last_run(lock, run_id="probe", costs_csv=tmp_path / "costs.csv")
    assert "row_timestamp_utc" not in json.loads(
        paidlock.last_run_path(lock).read_text(encoding="utf-8"))
    assert paidlock.last_run_missing(lock, [old]) is None
