"""One paid run at a time (common/paidlock.py)."""

from __future__ import annotations

import json
import subprocess

import pytest

from common import paidlock
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
