"""Paid-run locks: one paid run at a time in each of two streams, ARC and PersistGym (PREREG
§0.3 lines 14 and 15, §12).

**Streams.** The ARC stream (Gemini, `arc/run_path.py`) and the PersistGym stream (OpenAI,
`harnesses/cli.py`) each have their own lock, so one ARC run and one PersistGym run may go at
the same time, while within a stream one paid run goes at a time. `EXPERIMENT_STREAM` says
which stream each budget experiment belongs to; the paid guard refuses a run whose
experiment is not in the stream of the lock it holds (`common.approval.require_paid_run`).

**The locks.** `persistgym-paid-run-arc.lock` and `persistgym-paid-run-persistgym.lock` in
the git common directory (`git rev-parse --git-common-dir`), which the main checkout and all
of its worktrees share, so a paid run started in a worktree also blocks one of its stream
started in the main checkout. Each is created with O_CREAT | O_EXCL and holds JSON naming the
run (run id, stream, what it does, pid, host, start time and a random token). The holder
removes it when the run ends, and only if the file still holds its own token.

A run that dies without cleaning up (power loss, a killed terminal) leaves the file behind.
The next paid run of that stream then refuses and prints the file's contents. Nothing
removes a lock automatically: the operator checks that no paid run of that stream is still
going and deletes the file by hand. This is the operator rule "one paid run at a time per
stream" (arc/README.md) in code; it protects against mistakes, not against someone deleting
the file while a run is going. A run whose spend could not be written to results/costs.csv
leaves the lock held on purpose (`keep`), with the reason, so no paid run of its stream
starts on an incomplete ledger (and its reservation, below, keeps counting for the other).
A lock kept by a run that may have placed a hold the hold record does not show is marked,
and stops paid runs of both streams (`unrecorded_hold`), as the hold would. A PersistGym
lock kept because a run's row could not be written is released by `harnesses account-run`
once it has written that row from the run's raw files (`release_kept`), and only if the
process that took it has ended (`holder_alive`).

**The old single lock.** Before the per-stream locks, both launchers took one lock,
`persistgym-paid-run.lock` (`LEGACY_LOCK_NAME`). While that file exists (a run started by
code from before this change, or a lock such a run kept), no paid run of either stream
starts. A launcher from before this change knows only that file and does not see the
per-stream locks, so every checkout used for paid runs must be up to date.

**Spend reservations** (PREREG §12, "Operational": where both streams spend under one cap,
a run's planned spend counts against that cap from its start until its costs.csv row is
written). A paid run that passes the paid guard writes `persistgym-paid-reservation-
<stream>.json` next to its lock: its run, block, experiment, phase and planned spend. Until
the run's costs.csv row is written (or the run ends having spent nothing), the guard of
every other paid run counts that planned spend against the block and phase it shares with
it, so two runs going at once cannot together exceed a block's max_usd or a phase cap. The
check and the write happen under one operating-system lock (`budget_mutex`, the file
`persistgym-paid-budget.mutex`; common/oslock.py), so two runs cannot both pass on the same
room. A run removes its reservation after its row is written (`release_reservation`), and
when its lock is released. A run that keeps its lock keeps its reservation too. A
reservation of a stream whose lock the next run of that stream could take is left over from
a run that did not end cleanly: that run refuses until the operator has checked costs.csv
and deleted the file by hand.

**The last paid run of each stream.** Next to the locks, `persistgym-paid-last-run-
<stream>.json` names the last paid run of the stream that appended a costs.csv row (its run
ID and the row's timestamp) and the ledger it went to; a paid run of either stream refuses
unless the row of each stream's last run (and of the run in the old single record,
`persistgym-paid-last-run.json`, if there is one) is in its own ledger (`last_run_missing`),
since each checkout has its own results/costs.csv. The records are written and read under
`budget_mutex`, and a run's record is written before its reservation is removed, so a run
that starts in between counts that spend one way or the other.

Also next to the locks, `persistgym-paid-holds.jsonl` records the holds placed by paid runs
that ended COST_CAP or passed their run guard (common/hold.py). It is shared by both
streams: a paid run of either stream refuses while one is not cleared.

Both paid launchers take their stream's lock before their spend checks: the ARC launcher
(arc/run_path.py) and the PersistGym launcher (harnesses/cli.py), whose transport refuses to
spend unless it is handed a lock this run holds (`HeldLock`). The checks themselves are
`common.approval.require_paid_run`.
"""

from __future__ import annotations

import json
import math
import os
import socket
import subprocess
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from common import oslock
from common.hold import HOLDS_NAME

ARC = "arc"
PERSISTGYM = "persistgym"
STREAMS = (ARC, PERSISTGYM)

# Which stream each budget experiment (common.costs.EXPERIMENT_PHASE) runs in: the ARC
# launcher on Gemini, or the PersistGym launcher on OpenAI or, for claude-haiku-5-5's
# replication (PREREG §17.8, amendment R8), on Anthropic (PREREG §0.3 line 15). StateCarry
# on PersistGym is an OpenAI run; StateCarry on ARC games a Gemini run. tests/test_common.py
# checks that every budget experiment has a stream. `ext_` experiments have none: they have
# no budget phase either, so the paid guard refuses them.
EXPERIMENT_STREAM = {
    "toggle_pilot": PERSISTGYM,
    "replay_probe": PERSISTGYM,
    "gemini_probe": ARC,
    "arc_pilot": ARC,
    "persistgym_pilot": PERSISTGYM,
    "persistgym_validity": PERSISTGYM,
    "persistgym": PERSISTGYM,
    "persistgym_sol_h1": PERSISTGYM,
    "persistgym_haiku": PERSISTGYM,
    "arc_path": ARC,
    "statecarry_persistgym": PERSISTGYM,
    "statecarry_arc_dev": ARC,
    "statecarry_heldout": ARC,
}

LEGACY_LOCK_NAME = "persistgym-paid-run.lock"
LEGACY_LAST_RUN_NAME = "persistgym-paid-last-run.json"
RESERVATION_PREFIX = "persistgym-paid-reservation-"
MUTEX_NAME = "persistgym-paid-budget.mutex"


class LockHeld(RuntimeError):
    pass


def stream_of(experiment: str) -> str | None:
    """The stream budget experiment `experiment` runs in, or None if it has none."""
    return EXPERIMENT_STREAM.get(experiment)


def _check_stream(stream: str) -> str:
    if stream not in STREAMS:
        raise ValueError(f"unknown paid-run stream {stream!r}; one of {', '.join(STREAMS)}")
    return stream


def lock_name(stream: str) -> str:
    """The file name of stream `stream`'s lock."""
    return f"persistgym-paid-run-{_check_stream(stream)}.lock"


@dataclass(frozen=True)
class HeldLock:
    """A paid-run lock this run holds: the lock file and what `paid_run_lock` wrote into it
    (with the token and the stream). Code that spends takes one and refuses unless
    `holds()`."""
    path: Path
    info: dict

    def holds(self) -> bool:
        """Whether the lock file still holds this run's token. False once the file is gone,
        replaced, or `keep` has given it a new token."""
        token = self.token
        if not token:
            return False
        try:
            held = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return isinstance(held, dict) and held.get("token") == token

    @property
    def token(self) -> str | None:
        token = self.info.get("token") if isinstance(self.info, dict) else None
        return token if isinstance(token, str) and token else None

    @property
    def stream(self) -> str | None:
        """The stream whose lock this is, or None if the lock names no known stream."""
        stream = self.info.get("stream") if isinstance(self.info, dict) else None
        return stream if stream in STREAMS else None


def lock_path(repo: Path, stream: str) -> Path:
    """Stream `stream`'s lock file in `repo`'s git common directory."""
    name = lock_name(stream)
    try:
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-common-dir"],
                           capture_output=True, encoding="utf-8", errors="replace",
                           check=False)
    except OSError as e:
        raise LockHeld(f"cannot find the git common directory of {repo}: {e}") from None
    if r.returncode != 0 or not r.stdout.strip():
        raise LockHeld(f"cannot find the git common directory of {repo}: "
                       f"{(r.stderr or '').strip()}")
    common = Path(r.stdout.strip())
    if not common.is_absolute():
        common = repo / common
    return common.resolve() / name


def _held_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip() or "(empty)"
    except OSError:
        return "(unreadable)"


@contextmanager
def paid_run_lock(path: Path, *, run_id: str, what: str, stream: str) -> Iterator[dict]:
    """Hold stream `stream`'s lock at `path` for the duration of the block, or raise
    LockHeld: when another run of the stream holds it, or when the old single lock
    (`LEGACY_LOCK_NAME`, next to `path`) exists. On the way out, if the file still holds
    this run's token (it was not kept), removes this run's spend reservation, if any, and
    the file."""
    _check_stream(stream)
    legacy = path.with_name(LEGACY_LOCK_NAME)
    if legacy != path and legacy.exists():
        raise LockHeld(
            f"the old single paid-run lock {legacy} exists: {_held_text(legacy)}. It was "
            f"taken by a launcher from before the per-stream locks, and while it exists no "
            f"paid run of either stream starts. Wait for that run to end. If no paid run is "
            f"going (it crashed, or its lock was kept), check that results/costs.csv has its "
            f"row and, if it ended COST_CAP or passed its run guard, that its hold is in "
            f"{path.with_name(HOLDS_NAME)} (common/hold.py), then delete that file by hand. "
            f"Run every paid launcher from an up-to-date checkout")
    info = {"run_id": run_id, "stream": stream, "what": what, "pid": os.getpid(),
            "host": socket.gethostname(),
            "started_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "token": uuid.uuid4().hex}
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise LockHeld(
            f"another paid run of the {stream} stream holds {path}: {_held_text(path)}. One "
            f"paid run at a time per stream: wait for it to end. If no paid run of this "
            f"stream is going (it crashed), check that results/costs.csv has its row and, if "
            f"it ended COST_CAP or passed its run guard (its run_meta.json), that its hold is "
            f"in {path.with_name(HOLDS_NAME)} (common/hold.py), then delete that file by "
            f"hand, and its spend reservation {reservation_path(path, stream)} if it is "
            f"there") from None
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(info, f)
    try:
        yield info
    finally:
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("token") == info["token"]:
                if reservation_path(path, stream).exists():   # only this run writes it
                    try:
                        release_reservation(path, stream=stream, token=info["token"])
                    except OSError:
                        pass    # left behind: the next run of this stream refuses, saying why
                path.unlink()
        except (OSError, ValueError, AttributeError):
            pass


ALSO = " ALSO: "   # joins the reasons of a lock kept for more than one problem
# In a kept lock: the run may have placed a hold that the hold record does not show.
HOLD_NOT_RECORDED = "hold_not_recorded"


def keep(path: Path, info: dict, reason: str, *,
         hold_not_recorded: bool = False) -> dict | None:
    """Leave the lock held after the run ends, with `reason`: for a run that may have spent
    money that results/costs.csv does not show. The file (if it is still ours) gets the
    reason and a new token, so `paid_run_lock` does not remove it (nor the run's spend
    reservation) and every later paid run of the stream refuses, printing the reason, until
    the operator has added the missing row and deleted the file by hand.

    `hold_not_recorded`: the run may have placed a hold (PREREG §0.3 line 12, §7.7) that the
    hold record does not show, because it could not be written or the run's accounting
    stopped before it could rule one out. The file is then marked (`HOLD_NOT_RECORDED`, never unmarked by
    a later keep), and paid runs of the other stream refuse too while it stands
    (`unrecorded_hold`): a hold stops both streams, and the lock stands in for it.

    Returns the file's new contents (with the new token), or None if the file is not this
    run's and was left alone. A run that finds a second problem passes that return value as
    `info`: the second reason is then added to the first, not lost, so the operator who
    follows the file fixes both."""
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(held, dict) or held.get("token") != info["token"]:
            return None
        earlier = held.get("kept_because")
        if isinstance(earlier, str) and earlier:
            reason = (earlier if reason in earlier.split(ALSO)
                      else f"{earlier}{ALSO}{reason}")
        held.update(token=uuid.uuid4().hex, kept_because=reason)
        if hold_not_recorded:
            held[HOLD_NOT_RECORDED] = True
        path.write_text(json.dumps(held), encoding="utf-8")
        return held
    except (OSError, ValueError):
        return None


def release_kept(path: Path, *, run_id: str, token: str) -> None:
    """Delete the lock at `path`, kept (`keep`) by run `run_id`, once that run's spend is in
    results/costs.csv: `harnesses account-run` calls it after writing the run's row. Raises
    LockHeld, leaving the file alone, unless it still holds what account-run read before it
    wrote anything: run `run_id`, a reason it was kept, and lock token `token`. So a lock of
    another run, or one changed meanwhile, is never removed."""
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise LockHeld(f"cannot read the paid-run lock {path} ({e}); left alone") from None
    if not isinstance(held, dict) or held.get("run_id") != run_id:
        raise LockHeld(f"the paid-run lock {path} is not run {run_id}'s: "
                       f"{_held_text(path)}; left alone")
    if not held.get("kept_because"):
        raise LockHeld(f"the paid-run lock {path} of run {run_id} is not kept (no "
                       f"kept_because): the run may still be going; left alone")
    if held.get("token") != token:
        raise LockHeld(f"the paid-run lock {path} of run {run_id} changed after it was read; "
                       f"left alone")
    path.unlink()


# Windows (kernel32): OpenProcess access right, its error for a process id that names no
# process, and GetExitCodeProcess's code for a process that has not exited
_QUERY_LIMITED_INFORMATION = 0x1000
_ERROR_INVALID_PARAMETER = 87
_STILL_ACTIVE = 259
# FILETIME counts 100 ns intervals from 1601-01-01 UTC
_FILETIME_EPOCH_S = 11_644_473_600
# A lock is written by its run's process after that process started, to the second
_STARTED_SLACK_S = 2


def _windows_process(pid: int) -> tuple[str, float | None]:
    """("gone", None) if process `pid` does not exist or has exited; ("running", creation
    time in seconds since the epoch) if it runs; ("unknown", None) if it cannot be
    queried (access denied, say)."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    filetime = ctypes.POINTER(wintypes.FILETIME)
    kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE, filetime, filetime, filetime,
                                         filetime]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ("gone" if ctypes.get_last_error() == _ERROR_INVALID_PARAMETER
                else "unknown"), None
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return "unknown", None
        if code.value != _STILL_ACTIVE:
            return "gone", None
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel32.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            return "running", None
        created = times[0].dwHighDateTime << 32 | times[0].dwLowDateTime
        return "running", created / 1e7 - _FILETIME_EPOCH_S
    finally:
        kernel32.CloseHandle(handle)


def holder_alive(info: dict) -> str | None:
    """None if the process that took the lock whose contents are `info` has ended; otherwise
    why it may still be running. Checked on this host only: a lock taken on another host,
    or naming no process id, may be held. On Windows a process with that id that started
    after the lock was taken is another process (ids are reused), so the holder has ended;
    a process that cannot be queried counts as running."""
    pid, host = info.get("pid"), info.get("host")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return f"the lock names no process id ({pid!r})"
    if host != socket.gethostname():
        return (f"the lock was taken on host {host!r}, not this one "
                f"({socket.gethostname()!r}): check there that process {pid} has ended")
    if sys.platform == "win32":
        state, created = _windows_process(pid)
        if state == "gone":
            return None
        try:
            taken = datetime.fromisoformat(str(info.get("started_utc"))).timestamp()
        except ValueError:
            taken = None
        if (state == "running" and created is not None and taken is not None
                and created > taken + _STARTED_SLACK_S):
            return None
        return (f"process {pid}, which took the lock, is still running"
                + ("" if state == "running" else " or cannot be queried"))
    try:
        os.kill(pid, 0)  # signal 0: no signal, only the check (POSIX)
    except ProcessLookupError:
        return None
    except PermissionError:
        pass
    return f"process {pid}, which took the lock, is still running"


def unrecorded_hold(lock: Path) -> str | None:
    """None unless a paid-run lock next to `lock`, of either stream, was kept by a run that
    may have placed a hold the hold record does not show (`keep(..., hold_not_recorded=
    True)`); otherwise why no paid run of either stream may start. With one lock per stream,
    the kept lock alone would stop only its own stream's runs, while a hold stops both
    (PREREG §0.3 line 12, §7.7). A lock file that cannot be read is skipped here: it stops
    its own stream, and one being written is a run starting or being kept at this moment."""
    for stream in STREAMS:
        path = lock.with_name(lock_name(stream))
        try:
            held = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(held, dict) or held.get(HOLD_NOT_RECORDED) is not True:
            continue
        return (f"the {stream} stream's paid-run lock {path} is kept by a run that may have "
                f"placed a hold that {path.with_name(HOLDS_NAME)} does not show: "
                f"{held.get('kept_because') or '(no reason recorded)'}. A hold stops paid "
                f"runs of both streams, so no paid run starts in either stream until the "
                f"operator has added that run's hold to the record (or checked that it "
                f"placed none) and deleted the lock file (PREREG §0.3 line 12, §7.7)")
    return None


# ── The budget mutex ───────────────────────────────────────────────────

@contextmanager
def budget_mutex(lock: Path, *, timeout_s: float = oslock.DEFAULT_TIMEOUT_S) -> Iterator[None]:
    """Hold the operating-system lock that guards the spend reservations and the last-run
    records next to `lock` (common/oslock.py). It is not re-entrant: `record_last_run` and
    `release_reservation` take it themselves, so call them without it; `last_run_missing`,
    `read_reservations` and `write_reservation` do not, so call them under it. Raises
    LockTimeout (an OSError) after `timeout_s`."""
    with oslock.locked(lock.with_name(MUTEX_NAME), os.O_RDWR | os.O_CREAT,
                       timeout_s=timeout_s):
        yield


# ── The last paid run of each stream ───────────────────────────────────
# The locks are shared by every checkout, but each checkout has its own results/costs.csv.
# A paid run started in another checkout would not see the spend the last run wrote to
# this one's ledger, so the block and phase checks would undercount. Each paid run that
# appends a costs.csv row records its run ID and the row's timestamp here, one record per
# stream, and the next paid run of either stream refuses unless every recorded row is in its
# own ledger. One record per stream, because with both streams going a single record would
# name only whichever run ended last. The timestamp matters because a run ID need not be
# unique: a PersistGym `--run-id` can be given again, and an older row with the same ID must
# not stand in for the newest one.

def last_run_path(lock: Path, stream: str) -> Path:
    """Stream `stream`'s last-run record next to `lock`."""
    return lock.with_name(f"persistgym-paid-last-run-{_check_stream(stream)}.json")


def record_last_run(lock: Path, *, stream: str, run_id: str, costs_csv: Path,
                    timestamp_utc: str | None = None) -> None:
    """Note that run `run_id` of stream `stream` appended its costs row, whose
    `timestamp_utc` column is `timestamp_utc`, to `costs_csv`. Both launchers pass the
    timestamp. Writes under `budget_mutex`, and before the run's reservation is released."""
    record = {"run_id": run_id, "stream": _check_stream(stream),
              "costs_csv": str(Path(costs_csv).resolve()),
              "finished_utc": datetime.now(UTC).isoformat(timespec="seconds")}
    if timestamp_utc:
        record["row_timestamp_utc"] = str(timestamp_utc)
    with budget_mutex(lock):
        last_run_path(lock, stream).write_text(json.dumps(record), encoding="utf-8")


def _last_run_records(lock: Path) -> list[Path]:
    return [lock.with_name(LEGACY_LAST_RUN_NAME), *(last_run_path(lock, s) for s in STREAMS)]


def last_run_missing(lock: Path, rows: list[dict]) -> str | None:
    """None if the costs row of the last paid run of each stream (and of the run in the old
    single record, if any) is among `rows`, or no such run is recorded: a row with its run ID
    and, if the record has one, its row timestamp. Otherwise why not. The rows of the other
    stream's later runs, between and after them, do not matter. Reads the records without
    taking `budget_mutex`; the guard reads them under it (`common.approval`)."""
    for path in _last_run_records(lock):
        if not path.exists():
            continue
        try:
            last = json.loads(path.read_text(encoding="utf-8"))
            run_id = last["run_id"]
            stamp = last.get("row_timestamp_utc")
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return f"{path} is unreadable; check results/costs.csv by hand, then delete it"
        if any(r.get("run_id") == run_id and (not stamp or r.get("timestamp_utc") == stamp)
               for r in rows):
            continue
        return ("the last paid run"
                + (f" of the {last['stream']} stream" if last.get("stream") in STREAMS
                   else "")
                + f", {run_id}, appended its costs row"
                + (f" (timestamp_utc {stamp})" if stamp else "")
                + f" to {last.get('costs_csv')}, and that row is not in this checkout's "
                f"results/costs.csv, so the block and phase spend would be undercounted. Run "
                f"from that checkout, or bring that row here first (recorded in {path})")
    return None


# ── Spend reservations ─────────────────────────────────────────────────

class ReservationError(ValueError):
    pass


@dataclass(frozen=True)
class Reservation:
    """One running run's spend reservation."""
    path: Path
    stream: str
    run_id: str
    token: str                 # the lock token of the run that wrote it
    reservation_id: str
    approved_block: str
    experiment: str
    phase: str
    planned_usd: Decimal
    record: dict = field(compare=False)

    def describe(self) -> str:
        r = self.record
        return (f"run {self.run_id} ({self.stream} stream, {self.experiment}, block "
                f"{self.approved_block}, phase {self.phase}, ${float(self.planned_usd):.2f} "
                f"planned" + (f", reserved {r['reserved_utc']}" if r.get("reserved_utc") else "")
                + f"; {self.path})")


def reservation_path(lock: Path, stream: str) -> Path:
    """Stream `stream`'s reservation file next to `lock`."""
    return lock.with_name(f"{RESERVATION_PREFIX}{_check_stream(stream)}.json")


def _parse_reservation(path: Path, stream: str) -> Reservation:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ReservationError(f"the spend reservation {path} is unreadable ({e})") from None
    bad = None
    if not isinstance(record, dict):
        bad = "is not a JSON object"
    else:
        for key in ("run_id", "token", "reservation_id", "approved_block", "experiment",
                    "phase", "planned_usd"):
            if not isinstance(record.get(key), str) or not record[key]:
                bad = f"has no {key}"
                break
        else:
            if record.get("stream") != stream:
                bad = f"names stream {record.get('stream')!r}, not {stream!r}"
    if bad is None:
        try:
            planned = Decimal(record["planned_usd"])
        except InvalidOperation:
            planned = None
        if planned is None or not planned.is_finite() or planned < 0:
            bad = f"has planned_usd {record['planned_usd']!r}, not a finite amount"
    if bad is not None:
        raise ReservationError(f"the spend reservation {path} {bad}")
    return Reservation(path, stream, record["run_id"], record["token"],
                       record["reservation_id"], record["approved_block"],
                       record["experiment"], record["phase"], planned, record)


def read_reservations(lock: Path) -> list[Reservation]:
    """Every spend reservation next to `lock`, one per stream at most. Call it under
    `budget_mutex`. Raises ReservationError for a file that cannot be read as one, or a
    reservation-like file of no known stream: while it cannot be read, no paid run
    starts."""
    known = {reservation_path(lock, s).name: s for s in STREAMS}
    out = []
    try:
        names = sorted(p.name for p in lock.parent.glob(f"{RESERVATION_PREFIX}*"))
    except OSError as e:
        raise ReservationError(f"cannot list the spend reservations in {lock.parent}: "
                               f"{e}") from None
    for name in names:
        if name not in known:
            raise ReservationError(f"{lock.parent / name} is not a spend reservation of a "
                                   f"known stream ({', '.join(STREAMS)})")
        out.append(_parse_reservation(lock.with_name(name), known[name]))
    return out


def write_reservation(held: HeldLock, *, approved_block: str, experiment: str, phase: str,
                      planned_usd: Decimal) -> Reservation:
    """Write the reservation of the run holding `held` (replacing any earlier one of its
    stream: the caller has checked that it was this run's). Call it under `budget_mutex`,
    after the checks that count the other stream's reservation."""
    stream = held.stream
    if stream is None or not held.token:
        raise ValueError("a spend reservation needs a lock with a stream and a token")
    planned = Decimal(planned_usd)
    if not planned.is_finite() or planned < 0 or not math.isfinite(float(planned)):
        raise ValueError(f"planned spend {planned_usd!r} is not a finite amount")
    record = {"run_id": str(held.info.get("run_id")), "stream": stream, "token": held.token,
              "reservation_id": uuid.uuid4().hex, "approved_block": approved_block,
              "experiment": experiment, "phase": phase, "planned_usd": str(planned),
              "what": held.info.get("what"), "pid": os.getpid(), "host": socket.gethostname(),
              "reserved_utc": datetime.now(UTC).isoformat(timespec="seconds")}
    path = reservation_path(held.path, stream)
    with path.open("wb") as f:
        f.write(json.dumps(record).encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())
    return _parse_reservation(path, stream)


def release_reservation(lock: Path, *, stream: str, reservation_id: str | None = None,
                        token: str | None = None) -> bool:
    """Remove stream `stream`'s reservation next to `lock` if it is the one named: by its
    `reservation_id` (after the run's costs row is written, or when it made no call) or by
    the `token` of the lock that wrote it (when that lock is released). True if it was
    removed. A reservation that cannot be read is left for the operator. Takes
    `budget_mutex`; raises its OSError if the mutex cannot be had."""
    if reservation_id is None and token is None:
        raise ValueError("name the reservation to release: reservation_id or token")
    with budget_mutex(lock):
        path = reservation_path(lock, stream)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(record, dict):
            return False
        if reservation_id is not None and record.get("reservation_id") != reservation_id:
            return False
        if token is not None and record.get("token") != token:
            return False
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True
