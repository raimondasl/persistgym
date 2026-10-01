"""One paid run at a time: an exclusive lock file shared by every checkout of the repository.

The lock is `persistgym-paid-run.lock` in the git common directory (`git rev-parse
--git-common-dir`), which the main checkout and all of its worktrees share, so a paid run
started in a worktree also blocks one started in the main checkout. It is created with
O_CREAT | O_EXCL and holds JSON naming the run (run id, what it does, pid, host, start
time and a random token). The holder removes it when the run ends, and only if the file
still holds its own token.

A run that dies without cleaning up (power loss, a killed terminal) leaves the file behind.
The next paid run then refuses and prints the file's contents. Nothing removes a lock
automatically: the operator checks that no paid run is still going and deletes the file
by hand. This is the operator rule "one paid run at a time" (arc/README.md) in code; it
protects against mistakes, not against someone deleting the file while a run is going.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

LOCK_NAME = "persistgym-paid-run.lock"


class LockHeld(RuntimeError):
    pass


def lock_path(repo: Path) -> Path:
    """The lock file in `repo`'s git common directory."""
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
    return common.resolve() / LOCK_NAME


@contextmanager
def paid_run_lock(path: Path, *, run_id: str, what: str) -> Iterator[dict]:
    """Hold the lock at `path` for the duration of the block, or raise LockHeld."""
    info = {"run_id": run_id, "what": what, "pid": os.getpid(), "host": socket.gethostname(),
            "started_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "token": uuid.uuid4().hex}
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            held = path.read_text(encoding="utf-8").strip() or "(empty)"
        except OSError:
            held = "(unreadable)"
        raise LockHeld(
            f"another paid run holds {path}: {held}. One paid run at a time: wait for it to "
            "end. If no paid run is going (it crashed), delete that file by hand.") from None
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(info, f)
    try:
        yield info
    finally:
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("token") == info["token"]:
                path.unlink()
        except (OSError, ValueError):
            pass
