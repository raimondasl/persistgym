"""One paid run at a time per stream (common/paidlock.py): the locks, the last-run records
and the spend reservations. Every lock here is in a temporary folder."""

from __future__ import annotations

import json
import subprocess
from decimal import Decimal

import pytest

from common import costs, hold, paidlock
from common.paidlock import ARC, PERSISTGYM
from common.tests.gitrepo import git_in


def _lock(tmp_path, stream=ARC):
    return tmp_path / paidlock.lock_name(stream)


def test_lock_is_exclusive_and_released(tmp_path):
    path = _lock(tmp_path)
    with paidlock.paid_run_lock(path, run_id="run-1", what="arc_pilot: S0 on ft09",
                                stream=ARC) as info:
        held = json.loads(path.read_text(encoding="utf-8"))
        assert held["run_id"] == "run-1" and held["token"] == info["token"]
        assert held["stream"] == "arc" == paidlock.HeldLock(path, info).stream
        with (pytest.raises(paidlock.LockHeld, match="run-1") as e,
              paidlock.paid_run_lock(path, run_id="run-2", what="second", stream=ARC)):
            pytest.fail("a second paid run got the lock")
        assert "delete that file by hand" in str(e.value)
        assert "One paid run at a time per stream" in str(e.value)
        # a crashed run may have reached its run guard: the operator checks for its hold too
        assert "if it ended COST_CAP or passed its run guard" in str(e.value)
        assert str(path.with_name(hold.HOLDS_NAME)) in str(e.value)
        # and deletes its spend reservation, which would otherwise keep counting
        assert str(paidlock.reservation_path(path, ARC)) in str(e.value)
        assert path.exists()                       # the refused run left it alone
    assert not path.exists()

    with paidlock.paid_run_lock(path, run_id="run-3", what="later", stream=ARC):
        assert path.exists()


def test_the_streams_have_their_own_locks(tmp_path):
    """PREREG §0.3 line 15: one ARC run and one PersistGym run may go at the same time; a
    second run of either stream is refused."""
    arc, pg = _lock(tmp_path, ARC), _lock(tmp_path, PERSISTGYM)
    assert arc != pg and arc.parent == pg.parent
    with (paidlock.paid_run_lock(arc, run_id="arc-1", what="x", stream=ARC),
          paidlock.paid_run_lock(pg, run_id="pg-1", what="y", stream=PERSISTGYM)):
        assert arc.exists() and pg.exists()
        for path, stream in ((arc, ARC), (pg, PERSISTGYM)):
            with (pytest.raises(paidlock.LockHeld, match=f"of the {stream} stream"),
                  paidlock.paid_run_lock(path, run_id="second", what="z", stream=stream)):
                pass
    assert not arc.exists() and not pg.exists()


def test_the_old_single_lock_blocks_both_streams(tmp_path):
    """A launcher from before the per-stream locks takes persistgym-paid-run.lock and knows
    nothing of the new ones: while that file exists, no paid run of either stream starts."""
    legacy = tmp_path / paidlock.LEGACY_LOCK_NAME
    legacy.write_text('{"run_id": "old-pilot"}', encoding="utf-8")
    for stream in paidlock.STREAMS:
        with (pytest.raises(paidlock.LockHeld, match="old single paid-run lock.*old-pilot"),
              paidlock.paid_run_lock(_lock(tmp_path, stream), run_id="r", what="x",
                                     stream=stream)):
            pass
        assert not _lock(tmp_path, stream).exists()
    assert legacy.read_text(encoding="utf-8") == '{"run_id": "old-pilot"}'   # left alone
    legacy.unlink()
    with paidlock.paid_run_lock(_lock(tmp_path), run_id="r", what="x", stream=ARC):
        pass


def test_an_unknown_stream_is_refused(tmp_path):
    with (pytest.raises(ValueError, match="unknown paid-run stream"),
          paidlock.paid_run_lock(tmp_path / "x.lock", run_id="r", what="x", stream="gemini")):
        pass
    with pytest.raises(ValueError, match="unknown paid-run stream"):
        paidlock.lock_name("openai")
    assert not (tmp_path / "x.lock").exists()


def test_every_budget_experiment_has_a_stream():
    """Each experiment that can spend (common.costs.EXPERIMENT_PHASE) runs in exactly one
    stream: Gemini ARC experiments in the ARC stream, OpenAI ones in the PersistGym stream."""
    assert set(paidlock.EXPERIMENT_STREAM) == set(costs.EXPERIMENT_PHASE)
    assert set(paidlock.EXPERIMENT_STREAM.values()) == set(paidlock.STREAMS)
    for e in ("gemini_probe", "arc_pilot", "arc_path", "statecarry_arc_dev",
              "statecarry_heldout"):
        assert paidlock.stream_of(e) == ARC
    for e in ("toggle_pilot", "replay_probe", "persistgym_pilot", "persistgym_validity",
              "persistgym", "statecarry_persistgym"):
        assert paidlock.stream_of(e) == PERSISTGYM
    assert paidlock.stream_of("ext_gemini_flex") is None


def test_lock_is_released_when_the_run_raises(tmp_path):
    path = _lock(tmp_path)
    with (pytest.raises(KeyboardInterrupt),
          paidlock.paid_run_lock(path, run_id="run-1", what="x", stream=ARC)):
        raise KeyboardInterrupt
    assert not path.exists()


def test_a_lock_that_is_not_ours_is_not_removed(tmp_path):
    path = _lock(tmp_path)
    with paidlock.paid_run_lock(path, run_id="run-1", what="x", stream=ARC):
        path.write_text(json.dumps({"run_id": "other", "token": "someone-else"}),
                        encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8"))["token"] == "someone-else"


def test_a_stale_lock_refuses_until_deleted(tmp_path):
    path = _lock(tmp_path)
    path.write_text("garbage", encoding="utf-8")
    with (pytest.raises(paidlock.LockHeld, match="garbage"),
          paidlock.paid_run_lock(path, run_id="run-1", what="x", stream=ARC)):
        pass
    path.unlink()
    with paidlock.paid_run_lock(path, run_id="run-1", what="x", stream=ARC):
        pass


def test_lock_path_is_shared_by_worktrees(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git_in(repo, "init", "-q")
    (repo / "f").write_text("x", encoding="utf-8")
    git_in(repo, "add", "f")
    git_in(repo, "commit", "-q", "-m", "x")
    git_in(repo, "worktree", "add", "-q", str(tmp_path / "wt"))

    for stream in paidlock.STREAMS:
        main_lock = paidlock.lock_path(repo, stream)
        assert main_lock == (repo / ".git" / paidlock.lock_name(stream)).resolve()
        assert paidlock.lock_path(tmp_path / "wt", stream) == main_lock
    assert paidlock.lock_name(ARC) == "persistgym-paid-run-arc.lock"
    assert paidlock.lock_name(PERSISTGYM) == "persistgym-paid-run-persistgym.lock"


def test_lock_path_outside_a_repository(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    with pytest.raises(paidlock.LockHeld, match="git common directory"):
        paidlock.lock_path(tmp_path, ARC)


def test_git_missing(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(paidlock.LockHeld, match="git common directory"):
        paidlock.lock_path(tmp_path, ARC)


def test_keep_leaves_the_lock_held_with_the_reason(tmp_path):
    path = _lock(tmp_path)
    with paidlock.paid_run_lock(path, run_id="run-1", what="x", stream=ARC) as info:
        paidlock.keep(path, info, "run-1 spent money costs.csv does not show")
    held = json.loads(path.read_text(encoding="utf-8"))
    assert held["run_id"] == "run-1" and held["token"] != info["token"]
    with (pytest.raises(paidlock.LockHeld, match="costs.csv does not show"),
          paidlock.paid_run_lock(path, run_id="run-2", what="y", stream=ARC)):
        pass


def test_a_second_keep_adds_its_reason_to_the_first(tmp_path):
    """A run with two problems (say, a hold that could not be written and a costs row that
    could not be written) keeps both reasons, so the operator who follows the file fixes
    both. The second keep passes what the first returned; the run's own token no longer
    matches after the first."""
    path = _lock(tmp_path)
    with paidlock.paid_run_lock(path, run_id="run-1", what="x", stream=ARC) as info:
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
          paidlock.paid_run_lock(path, run_id="run-2", what="y", stream=ARC)):
        pass


def test_keep_leaves_a_lock_that_is_not_ours_alone(tmp_path):
    path = _lock(tmp_path)
    with paidlock.paid_run_lock(path, run_id="run-1", what="x", stream=ARC) as info:
        path.write_text(json.dumps({"run_id": "other", "token": "someone-else"}),
                        encoding="utf-8")
        paidlock.keep(path, info, "why")
    assert json.loads(path.read_text(encoding="utf-8")) == {"run_id": "other",
                                                            "token": "someone-else"}


def test_a_held_lock_holds_only_its_own_token(tmp_path):
    """What the code that spends checks (`common.approval.require_paid_run`): the lock file
    still holds this run's token."""
    path = _lock(tmp_path)
    with paidlock.paid_run_lock(path, run_id="run-1", what="x", stream=ARC) as info:
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
    assert paidlock.HeldLock(path, {"stream": "gemini"}).stream is None
    assert paidlock.HeldLock(path, {}).stream is None


# ── The last paid run of each stream ───────────────────────────────────

def test_the_last_runs_row_must_be_in_the_ledger(tmp_path):
    lock = _lock(tmp_path)
    assert paidlock.last_run_missing(lock, []) is None        # no paid run recorded yet

    paidlock.record_last_run(lock, stream=ARC, run_id="run-1",
                             costs_csv=tmp_path / "a" / "costs.csv")
    assert json.loads(paidlock.last_run_path(lock, ARC).read_text(encoding="utf-8"))[
        "stream"] == "arc"
    assert paidlock.last_run_missing(lock, [{"run_id": "run-1"}]) is None
    reason = paidlock.last_run_missing(lock, [{"run_id": "run-0"}])
    assert "the last paid run of the arc stream, run-1" in reason
    assert "not in this checkout" in reason

    paidlock.last_run_path(lock, ARC).write_text("garbage", encoding="utf-8")
    assert "unreadable" in paidlock.last_run_missing(lock, [{"run_id": "run-1"}])
    for text in ("[]", '"run-1"', "{}"):
        paidlock.last_run_path(lock, ARC).write_text(text, encoding="utf-8")
        assert "unreadable" in paidlock.last_run_missing(lock, [{"run_id": "run-1"}])


def test_each_streams_last_run_must_be_in_the_ledger(tmp_path):
    """With both streams going, one record would name only whichever run ended last, and a
    checkout lacking the other stream's row would undercount a shared block or phase. So each
    stream has its own record, and a run of either stream needs both rows (and the row of
    the old single record, written by a launcher from before the per-stream locks). Rows of
    the other stream before, between and after them do not matter."""
    lock = _lock(tmp_path)
    arc_row = {"run_id": "arc-1", "timestamp_utc": "2026-10-03T10:00:00+00:00"}
    pg_row = {"run_id": "pg-1", "timestamp_utc": "2026-10-03T10:05:00+00:00"}
    old_row = {"run_id": "old-1", "timestamp_utc": "2026-10-02T09:00:00+00:00"}
    paidlock.record_last_run(lock, stream=ARC, run_id="arc-1", costs_csv=tmp_path / "c.csv",
                             timestamp_utc=arc_row["timestamp_utc"])
    paidlock.record_last_run(lock, stream=PERSISTGYM, run_id="pg-1",
                             costs_csv=tmp_path / "c.csv",
                             timestamp_utc=pg_row["timestamp_utc"])
    other = {"run_id": "pg-2", "timestamp_utc": "2026-10-03T11:00:00+00:00"}
    assert paidlock.last_run_missing(lock, [pg_row, other, arc_row, other]) is None
    assert "persistgym stream, pg-1" in paidlock.last_run_missing(lock, [arc_row, other])
    assert "arc stream, arc-1" in paidlock.last_run_missing(lock, [pg_row])

    lock.with_name(paidlock.LEGACY_LAST_RUN_NAME).write_text(json.dumps(
        {"run_id": "old-1", "costs_csv": "elsewhere", "row_timestamp_utc":
         old_row["timestamp_utc"]}), encoding="utf-8")
    reason = paidlock.last_run_missing(lock, [arc_row, pg_row])
    assert "the last paid run, old-1" in reason and "elsewhere" in reason
    assert paidlock.last_run_missing(lock, [old_row, arc_row, pg_row]) is None


def test_a_reused_run_id_needs_the_newest_row(tmp_path):
    """A run ID need not be unique (a PersistGym `--run-id` can be given again): an older
    row with the same ID must not stand in for the last run's row, so the record names the
    row's timestamp too."""
    lock = _lock(tmp_path, PERSISTGYM)
    old = {"run_id": "probe", "timestamp_utc": "2026-10-02T10:00:00+00:00"}
    new = {"run_id": "probe", "timestamp_utc": "2026-10-02T11:00:00+00:00"}
    paidlock.record_last_run(lock, stream=PERSISTGYM, run_id="probe",
                             costs_csv=tmp_path / "costs.csv",
                             timestamp_utc=new["timestamp_utc"])
    record = json.loads(paidlock.last_run_path(lock, PERSISTGYM).read_text(encoding="utf-8"))
    assert record["row_timestamp_utc"] == new["timestamp_utc"]
    reason = paidlock.last_run_missing(lock, [old])          # another checkout's ledger
    assert "probe" in reason and new["timestamp_utc"] in reason
    assert "not in this checkout" in reason
    assert paidlock.last_run_missing(lock, [old, new]) is None

    # a record written without a timestamp matches on the run ID alone
    paidlock.record_last_run(lock, stream=PERSISTGYM, run_id="probe",
                             costs_csv=tmp_path / "costs.csv")
    assert "row_timestamp_utc" not in json.loads(
        paidlock.last_run_path(lock, PERSISTGYM).read_text(encoding="utf-8"))
    assert paidlock.last_run_missing(lock, [old]) is None


# ── Spend reservations ─────────────────────────────────────────────────

def _reserve(held, planned="5", block="1-pilots", experiment="arc_pilot", phase="0"):
    with paidlock.budget_mutex(held.path):
        return paidlock.write_reservation(held, approved_block=block, experiment=experiment,
                                          phase=phase, planned_usd=Decimal(planned))


def test_a_reservation_names_the_run_and_is_released_with_the_lock(tmp_path):
    path = _lock(tmp_path)
    with paidlock.paid_run_lock(path, run_id="arc-1", what="arc_pilot: S0 on ft09",
                                stream=ARC) as info:
        held = paidlock.HeldLock(path, info)
        mine = _reserve(held, planned="12.5")
        assert mine.path == paidlock.reservation_path(path, ARC) == tmp_path / (
            "persistgym-paid-reservation-arc.json")
        assert (mine.run_id, mine.stream, mine.token) == ("arc-1", "arc", info["token"])
        assert (mine.approved_block, mine.experiment, mine.phase, mine.planned_usd) == (
            "1-pilots", "arc_pilot", "0", Decimal("12.5"))
        with paidlock.budget_mutex(path):
            assert paidlock.read_reservations(path) == [mine]
        assert "run arc-1 (arc stream, arc_pilot, block 1-pilots, phase 0, $12.50" in (
            mine.describe())
    assert not path.exists() and not mine.path.exists()


def test_release_names_the_reservation(tmp_path):
    """After its costs row, a run removes the reservation it wrote (by its ID), not a newer
    one of the same run; releasing the lock removes the run's reservation by its token."""
    path = _lock(tmp_path, PERSISTGYM)
    with paidlock.paid_run_lock(path, run_id="probe", what="x", stream=PERSISTGYM) as info:
        held = paidlock.HeldLock(path, info)
        first = _reserve(held, experiment="toggle_pilot")
        second = _reserve(held, experiment="toggle_pilot")       # the probe's next model
        assert first.reservation_id != second.reservation_id
        assert not paidlock.release_reservation(path, stream=PERSISTGYM,
                                                reservation_id=first.reservation_id)
        assert second.path.exists()
        assert not paidlock.release_reservation(path, stream=PERSISTGYM, token="other")
        assert paidlock.release_reservation(path, stream=PERSISTGYM,
                                            reservation_id=second.reservation_id)
        assert not second.path.exists()
        assert not paidlock.release_reservation(path, stream=PERSISTGYM,
                                                reservation_id=second.reservation_id)
        third = _reserve(held, experiment="toggle_pilot")
    assert not third.path.exists()                              # gone with the lock
    with pytest.raises(ValueError, match="name the reservation"):
        paidlock.release_reservation(path, stream=PERSISTGYM)


def test_a_kept_lock_keeps_its_reservation(tmp_path):
    """A run whose spend is not in costs.csv keeps its lock, and its reservation keeps
    counting against the other stream until the operator deletes both."""
    path = _lock(tmp_path)
    with paidlock.paid_run_lock(path, run_id="arc-1", what="x", stream=ARC) as info:
        mine = _reserve(paidlock.HeldLock(path, info))
        paidlock.keep(path, info, "add its row by hand")
    assert path.exists() and mine.path.exists()


@pytest.mark.parametrize("text, msg", [
    ("garbage", "unreadable"),
    ("[]", "is not a JSON object"),
    ('{"run_id": "r"}', "has no token"),
    (None, "has planned_usd 'nan'"),
    (None, "names stream 'persistgym', not 'arc'"),
])
def test_an_unreadable_reservation_is_an_error(tmp_path, text, msg):
    """A reservation that cannot be read cannot be counted: the guard refuses on it."""
    path = _lock(tmp_path)
    good = {"run_id": "r", "stream": "arc", "token": "t", "reservation_id": "i",
            "approved_block": "b", "experiment": "arc_pilot", "phase": "0",
            "planned_usd": "5"}
    if text is None:
        bad = ({**good, "planned_usd": "nan"} if "nan" in msg
               else {**good, "stream": "persistgym"})
        text = json.dumps(bad)
    paidlock.reservation_path(path, ARC).write_text(text, encoding="utf-8")
    with pytest.raises(paidlock.ReservationError, match=msg):
        paidlock.read_reservations(path)


def test_a_reservation_of_no_known_stream_is_an_error(tmp_path):
    path = _lock(tmp_path)
    (tmp_path / f"{paidlock.RESERVATION_PREFIX}gemini.json").write_text("{}", encoding="utf-8")
    with pytest.raises(paidlock.ReservationError, match="not a spend reservation of a known"):
        paidlock.read_reservations(path)


def test_the_budget_mutex_is_exclusive(tmp_path):
    """One holder at a time, even within one process; the second waits, then times out."""
    path = _lock(tmp_path)
    with paidlock.budget_mutex(path):
        assert (tmp_path / paidlock.MUTEX_NAME).exists()
        with (pytest.raises(TimeoutError, match="stayed locked"),
              paidlock.budget_mutex(path, timeout_s=0.2)):
            pytest.fail("got the mutex twice")
    with paidlock.budget_mutex(path, timeout_s=0.2):
        pass
