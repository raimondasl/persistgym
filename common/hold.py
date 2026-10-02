"""The hold after a COST_CAP ending (PREREG §0.3 line 12, §7.7, §12): the record of runs that
placed one.

A paid run that ends `COST_CAP` at its run guard, or whose spend passed that guard before it
could stop the run, places a hold. While a hold stands, no further paid run starts in either
stream, ARC or PersistGym, until the researcher clears it by merging the line
`cleared_hold: <run_id>` into results/decisions.md. The clearing grammar, and the check that
refuses a paid run while a hold stands, are in common/approval.py (`require_paid_run`). This
module only writes and reads the record.

**The record.** `persistgym-paid-holds.jsonl`, in the same folder as the paid-run lock
(common/paidlock.py): the git common directory, shared by every worktree of the clone, so a
hold placed by a run in one worktree stops paid runs in all of them. It is keyed by that
folder, not by the lock's file name, so per-stream locks in the same folder share it. Each
line is one hold, a JSON object naming the run (`run_id`), its `experiment`, the `reason`
and the time it was placed (`placed_utc`), plus details. Lines are only ever appended, under
an operating-system lock on the file that reading takes too (common/oslock.py), since runs of
both streams may place a hold at the same moment: code never removes or edits a hold. A hold
is cleared by the researcher's merged line, not by deleting the record, and removing that
line again puts the hold back.

**Who writes it.** The ARC launcher (arc/run_path.py), whenever a run's `exit_reason` or
`agent_exit_reason` is `COST_CAP`, or a game run's no-cache list spend passed its harness
cost guard whatever its ending (the guard is checked only before each action, so the step
that crosses it can still end in an error, or the process can die before the agent records
COST_CAP; such a run has reached its guard, and an AGENT_ERROR or UNKNOWN ending would
otherwise be re-run without the researcher being asked). It writes the hold before it
accounts for the run, so a run whose accounting fails still places its hold. It writes one
for a pilot too, whose harness guard is its planned spend rather than D22's $120 (stricter
than §7.7, which names the $120 guard). The acceptance check never ends COST_CAP: once its
guard is reached it skips the profiles left and ends NOT_ALL_ACCEPTED, with no hold. The
PersistGym transport writes none: it stops a run before a call once the run's spend reaches
`--planned-usd`, a stop its runner labels `COST_CAP`, but that is the planned spend, not a
per-run cost guard. A PersistGym per-run guard, if one is ever added, must call `place_hold`
when it ends a run.

**Reading it** never ignores a line. A line that is not a JSON object, or whose `run_id` is
not a run ID that a clearing line can name (`[A-Za-z0-9._-]+`), raises `HoldRecordError`,
and the guard refuses until the file is fixed by hand. `place_hold` itself writes whatever
run ID it is given, so a hold is never skipped; an unclearable one then refuses until fixed.

The record protects against mistakes, not against someone who deletes the file. A separate
clone of the repository has its own git directory and does not see it, as for the lock.
"""

from __future__ import annotations

import json
import os
import re
import socket
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from common import oslock

HOLDS_NAME = "persistgym-paid-holds.jsonl"
COST_CAP = "COST_CAP"
# The run IDs a clearing line can name: the block-name token of common/approval.py.
RUN_ID_RE = re.compile(r"[A-Za-z0-9._-]+", re.ASCII)


class HoldRecordError(ValueError):
    pass


@dataclass(frozen=True)
class Hold:
    """One line of the record."""
    run_id: str
    line: int                              # 1-based line number in the record
    record: dict = field(compare=False)

    def describe(self) -> str:
        """The run, its experiment, why it placed the hold and when, from the record."""
        r = self.record
        parts = [str(r[k]) for k in ("experiment", "what") if r.get(k)]
        if r.get("reason"):
            parts.append(str(r["reason"]))
        if r.get("placed_utc"):
            parts.append(f"placed {r['placed_utc']}")
        return "; ".join(parts) or "no details recorded"


def holds_path(lock: Path) -> Path:
    """The hold record next to the paid-run lock `lock`."""
    return Path(lock).with_name(HOLDS_NAME)


def place_hold(lock: Path, *, run_id: str, experiment: str, reason: str,
               **details) -> dict:
    """Append a hold for run `run_id` to the record next to `lock` and return it. Raises
    OSError if it cannot be written; the caller must then stop paid runs another way."""
    record = {"run_id": run_id, "experiment": experiment, "reason": reason,
              "placed_utc": datetime.now(UTC).isoformat(timespec="seconds"),
              "host": socket.gethostname(), **details}
    data = (json.dumps(record, ensure_ascii=True) + "\n").encode("ascii")
    path = holds_path(lock)
    # Under the record's operating-system lock (common/oslock.py), which `read_holds` takes
    # too: runs of both streams may place a hold at the same moment.
    with oslock.locked(path, os.O_RDWR | os.O_CREAT | os.O_APPEND) as fd:
        size = os.lseek(fd, 0, os.SEEK_END)
        if size > 0:
            os.lseek(fd, size - 1, os.SEEK_SET)
            if os.read(fd, 1) != b"\n":   # a torn last line must not swallow this hold
                data = b"\n" + data
            os.lseek(fd, 0, os.SEEK_END)
        oslock.write_all(fd, data)
        os.fsync(fd)
    return record


def read_holds(lock: Path) -> list[Hold]:
    """Every hold in the record next to `lock`, in the order placed (cleared or not); [] if
    there is no record. Raises HoldRecordError if a line cannot be read as a hold."""
    path = holds_path(lock)
    try:
        with oslock.locked(path) as fd:
            text = oslock.read_all(fd).decode("utf-8", errors="replace")
    except FileNotFoundError:
        return []
    except OSError as e:
        raise HoldRecordError(f"cannot read the hold record {path}: {e}") from None
    holds = []
    for n, line in enumerate(text.split("\n"), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            record = None
        if not isinstance(record, dict):
            raise HoldRecordError(
                f"line {n} of the hold record {path} is not a hold (one JSON object per "
                f"line): fix it by hand, keeping every hold it records")
        run_id = record.get("run_id")
        if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
            raise HoldRecordError(
                f"line {n} of the hold record {path} names run {run_id!r}, which a "
                f"'cleared_hold: <run_id>' line cannot name ([A-Za-z0-9._-]+): fix it by "
                f"hand, keeping the hold")
        holds.append(Hold(run_id, n, record))
    return holds
