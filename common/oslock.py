"""An operating-system lock on a file, for the moments two processes may touch one file at
once: appends to and reads of results/costs.csv (common/costs.py), and the spend
reservations, last-run records and hold record next to the paid-run locks
(common/paidlock.py, common/approval.py).

Unlike the paid-run lock files (created with O_EXCL, left behind by a run that dies), this
lock belongs to an open file descriptor: it is released when the holder unlocks, closes the
file or dies, so nothing is ever left to clean up. It is exclusive and short: callers hold
it for one read or one append, never across a model call.

- POSIX: `flock` on the whole file.
- Windows: `msvcrt.locking` on one byte at `LOCK_OFFSET`, far past the end of any file it
  guards. Windows byte-range locks are mandatory, so a lock on the file's data would make
  every other program's reads of it fail (an editor, git); a lock on a byte past the end
  blocks no read or write, only another lock on that byte. The offset is below 2**31 so that
  it also works where the C runtime seeks with 32-bit offsets.

Every process that touches a guarded file must take the lock for it to help. Code from
before this module (a launcher in an older checkout) does not, which is one reason every
checkout used for paid runs must be up to date.
"""

from __future__ import annotations

import errno
import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DEFAULT_TIMEOUT_S = 120.0
POLL_S = 0.01
LOCK_OFFSET = 0x7FFF_FFF0      # Windows only: one byte here, past the end of any guarded file
_BINARY = getattr(os, "O_BINARY", 0)   # Windows: no newline translation on the descriptor


class LockTimeout(TimeoutError):
    """Another process held the lock for longer than the timeout."""


if sys.platform == "win32":
    import msvcrt

    # LK_NBLCK fails with EACCES (or EDEADLOCK) when another descriptor holds the byte.
    _BUSY = {errno.EACCES, errno.EDEADLK, getattr(errno, "EDEADLOCK", errno.EDEADLK)}

    def _try_lock(fd: int) -> bool:
        os.lseek(fd, LOCK_OFFSET, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as e:
            if e.errno in _BUSY:
                return False
            raise
        return True

    def _unlock(fd: int) -> None:
        os.lseek(fd, LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def locked(path: Path, flags: int = os.O_RDONLY, *,
           timeout_s: float = DEFAULT_TIMEOUT_S) -> Iterator[int]:
    """Open `path` with `flags` (binary on Windows) and hold the lock on it for the block,
    yielding the descriptor. Its position is undefined: seek before reading or writing.
    Raises the open's OSError (FileNotFoundError for a missing file without O_CREAT), or
    LockTimeout if another process holds the lock for `timeout_s` seconds. The lock is not
    re-entrant: a process that takes it twice, even through two descriptors, waits for
    itself until the timeout."""
    fd = os.open(path, flags | _BINARY)
    try:
        deadline = time.monotonic() + timeout_s
        while not _try_lock(fd):
            if time.monotonic() >= deadline:
                raise LockTimeout(f"{path} stayed locked by another process for "
                                  f"{timeout_s:.0f} s")
            time.sleep(POLL_S)
        try:
            yield fd
        finally:
            _unlock(fd)
    finally:
        os.close(fd)


def read_all(fd: int) -> bytes:
    """Everything in the file from its start."""
    os.lseek(fd, 0, os.SEEK_SET)
    chunks = []
    while chunk := os.read(fd, 1 << 20):
        chunks.append(chunk)
    return b"".join(chunks)


def write_all(fd: int, data: bytes) -> None:
    """Write all of `data` at the descriptor's position (the end, for O_APPEND)."""
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]
