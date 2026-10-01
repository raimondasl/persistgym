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
A run whose spend could not be written to results/costs.csv leaves the lock held on
purpose (`keep`), with the reason, so no paid run starts on an incomplete ledger.

Next to the lock, `persistgym-paid-last-run.json` names the last paid run that appended a
costs.csv row and the ledger it went to; a paid run refuses unless that row is in its own
ledger (`last_run_missing`), since each checkout has its own results/costs.csv.
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


def keep(path: Path, info: dict, reason: str) -> None:
    """Leave the lock held after the run ends, with `reason`: for a run that may have spent
    money that results/costs.csv does not show. The file (if it is still ours) gets the
    reason and a new token, so `paid_run_lock` does not remove it and every later paid run
    refuses, printing the reason, until the operator has added the missing row and deleted
    the file by hand."""
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
        if held.get("token") != info["token"]:
            return
        held.update(token=uuid.uuid4().hex, kept_because=reason)
        path.write_text(json.dumps(held), encoding="utf-8")
    except (OSError, ValueError):
        pass


# ── The last paid run's ledger ─────────────────────────────────────────
# The lock is shared by every checkout, but each checkout has its own results/costs.csv.
# A paid run started in another checkout would not see the spend the last run wrote to
# this one's ledger, so the block and phase checks would undercount. Each paid run that
# appends a costs.csv row records its run ID here, and the next one refuses unless that
# row is in its own ledger.

LAST_RUN_NAME = "persistgym-paid-last-run.json"


def last_run_path(lock: Path) -> Path:
    return lock.with_name(LAST_RUN_NAME)


def record_last_run(lock: Path, *, run_id: str, costs_csv: Path) -> None:
    """Note that run `run_id` appended its costs row to `costs_csv`."""
    last_run_path(lock).write_text(
        json.dumps({"run_id": run_id, "costs_csv": str(Path(costs_csv).resolve()),
                    "finished_utc": datetime.now(UTC).isoformat(timespec="seconds")}),
        encoding="utf-8")


def last_run_missing(lock: Path, rows: list[dict]) -> str | None:
    """None if the last paid run's costs row is among `rows` (or no run is recorded);
    otherwise why not."""
    path = last_run_path(lock)
    if not path.exists():
        return None
    try:
        last = json.loads(path.read_text(encoding="utf-8"))
        run_id = last["run_id"]
    except (OSError, ValueError, KeyError, TypeError):
        return f"{path} is unreadable; check results/costs.csv by hand, then delete it"
    if any(r.get("run_id") == run_id for r in rows):
        return None
    return (f"the last paid run, {run_id}, appended its costs row to {last.get('costs_csv')}, "
            f"and that row is not in this checkout's results/costs.csv, so the block and "
            f"phase spend would be undercounted. Run from that checkout, or bring that row "
            f"here first (recorded in {path})")
