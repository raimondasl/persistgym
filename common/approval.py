"""The paid-call guard: the researcher's approval of a spending block (PLAN §16.2) and the
checks every paid launcher runs before it may spend. Shared so that the harness transport
(harnesses/openai_transport.py) and, later, the ARC launcher read approvals the same way.

**The approval line.** The researcher approves block <name> by adding one line to
results/decisions.md, with exactly this spacing:

    approved_block: <name> | experiments: <exp1>,<exp2>,... | max_usd: <amount>

- The line starts at column 0: no list marker, indentation, quote or backticks. Only trailing
  whitespace (Markdown spaces, the CR of a CRLF file) is ignored. Lines are split on "\\n"
  only.
- <name> matches [A-Za-z0-9._-]+ (ASCII).
- The experiments are a comma-separated list without spaces, at least one and no repeats.
  Each is a key of common.costs.EXPERIMENT_PHASE or starts with "ext_".
- <amount> is a positive, finite decimal number of US dollars: ASCII digits with an optional
  fractional part ("76", "0.50"). No sign, exponent, currency symbol or thousands separator.
- The line is not inside a fenced code block (``` or ~~~) or an HTML comment. A proposed or
  example line shown in a code block, or a line commented out, never counts (`shown_lines`).

A line that breaks any of these rules never counts. The refusal message names look-alike
lines (malformed, or in a code block or comment) so a typo is easy to find.

**Where the line must be.** The same line (compared after removing trailing whitespace)
must be in results/decisions.md in all three of:
1. origin/main, fetched fresh (`git fetch origin main`) from the configured `origin` remote.
   If no such remote is configured or the fetch fails, the guard refuses. An approval
   therefore reaches the guard only through the researcher's merge;
2. the HEAD commit;
3. the working-tree file.
Removing or changing the line in any of the three counts as a revocation, and so does
moving it into a code block or an HTML comment. Two different valid lines for one block
name are ambiguous and refuse. git replace refs are ignored, so a local object cannot stand
in for the fetched file.

**PREREG.md must be frozen.** PREREG.md must be committed (tracked, in HEAD, no uncommitted
changes) and identical in HEAD and on origin/main, read after the same fetch as the approval
line. A PREREG committed on a branch but not merged, or a HEAD that lacks an amendment
merged to main, refuses: only the merged (frozen) PREREG unlocks paid calls (PLAN §16.3).
`require_paid_approval` stops there; `require_paid_run`, which both paid launchers call,
also requires that merged text to be frozen (`prereg_not_frozen`: the rule of
common/prereg.py), so a draft merged to main does not unlock paid calls either.

**One paid run at a time per stream** (PREREG §0.3 line 15, §12). `require_paid_run` also
refuses unless the run holds its stream's paid-run lock (common/paidlock.py: ARC or
PersistGym), taken before these checks so that two runs of a stream cannot both pass them,
unless the run's experiment belongs to that stream, and unless this checkout's costs.csv
holds the row of each stream's last paid run.

**Runs of both streams at once: spend reservations** (PREREG §12, "Operational"). One ARC
run and one PersistGym run may go at the same time, and they may share a block (block 1
lists experiments of both streams) and a phase (phases 0 and 2). So the last check, under
an operating-system lock that both streams take (`paidlock.budget_mutex`), counts the
planned spend of every other running run as already spent: a run is refused if block spend
+ the planned spend reserved by other running runs of the block + its own planned spend >
max_usd, and likewise for the phase cap. If it passes, it writes its own reservation, which
counts against the others until its costs.csv row is written. Two runs that overlap cannot
both use the same room.

**No paid run while a hold stands** (PREREG §0.3 line 12, §7.7, §12). A paid run that ends
`COST_CAP`, or whose spend passed its run guard before the guard could stop it, places a
hold (common/hold.py, a record next to the lock). `require_paid_run` refuses while any hold
in that record is not cleared, naming each run and the line that clears it, and while a
paid-run lock of either stream is kept by a run that may have placed a hold the record does
not show (`paidlock.unrecorded_hold`). The researcher clears the hold of run <run_id> with
one line in results/decisions.md:

    cleared_hold: <run_id>

It follows the rules of the approval line: exactly this spacing, at column 0 (only trailing
whitespace is ignored), <run_id> matching [A-Za-z0-9._-]+, not in a fenced code block or an
HTML comment, and in all three of origin/main (fetched fresh), HEAD and the working tree.
Removing it, or hiding it in a code block or comment, in any of the three puts the hold
back. The refusal names look-alike lines. A run may not reuse the run ID of a run that
placed a hold, so a clearing line names one run only.

**What it allows.** The run's experiment must be in the line's list. Spend is measured one
way everywhere (`spend_usd`, defined in common/costs.py): the billed estimate, or the list
cost where a row has no billed estimate. Every cap and estimate for PersistGym in PLAN §12,
§16 and §17 is in Flex-billed dollars, and D23 makes the billed estimate the primary cost
basis; counting Flex at list would trip the caps at about half the real spend. Block spend
is the sum of `spend_usd` over results/costs.csv rows whose `notes` contain
"approved_block=<name>;". The run is refused if block spend + planned spend (+ the planned
spend other running runs of the block have reserved) > max_usd, and a run stops before a
call (or, for ARC, before an action) once its own spend reaches its planned spend. The
phase-cap check (`common.costs.headroom`) uses the same measure. The list cost is still
logged in every row and reported. Every costs.csv row must be readable for either check: a
cost that is not empty or a finite, non-negative number, a row with neither cost, or an
experiment with no budget phase, refuses. The billed estimate
comes from our price table; the provider-side hard spend limits, which the researcher sets
in real billed dollars, remain the backstop against under-estimation.

The guard protects against mistakes (an example line, a stale or unmerged approval, a
corrupt ledger), not against someone who edits this code or the repository's git config.

The guard never writes an approval. The only things it changes are the remote-tracking ref
(refs/remotes/origin/main), by fetching, and the run's own spend reservation next to its
lock.
"""

from __future__ import annotations

import math
import os
import re
import subprocess
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path

from common import costs, hold, paidlock, runmeta
from common.costs import spend_usd  # the one spend measure, re-exported for the launchers
from common.prereg import prereg_state

ALLOW_ENV = "PERSISTGYM_ALLOW_PAID"
DECISIONS_MD = "results/decisions.md"  # relative to the repo root, as git paths are
FETCH_TIMEOUT_S = 60.0

_TOKEN = r"[A-Za-z0-9._-]+"
NAME_RE = re.compile(_TOKEN, re.ASCII)
LINE_RE = re.compile(
    rf"approved_block: (?P<name>{_TOKEN})"
    rf" \| experiments: (?P<experiments>{_TOKEN}(?:,{_TOKEN})*)"
    r" \| max_usd: (?P<max_usd>[0-9]+(?:\.[0-9]+)?)",
    re.ASCII)
CLEAR_RE = re.compile(rf"cleared_hold: (?P<run_id>{_TOKEN})", re.ASCII)


class PaidCallsNotAllowed(RuntimeError):
    pass


@dataclass(frozen=True)
class Approval:
    """One valid approval line."""
    name: str
    experiments: tuple[str, ...]
    max_usd: Decimal
    line: str  # as written, trailing whitespace removed


@dataclass(frozen=True)
class RemoteRef:
    """The branch an approval must have reached: `remote`/`branch` (origin/main). Tests point
    `remote` at a local bare repository."""
    remote: str = "origin"
    branch: str = "main"

    @property
    def tracking(self) -> str:
        return f"refs/remotes/{self.remote}/{self.branch}"

    @property
    def label(self) -> str:
        return f"{self.remote}/{self.branch}"


MAIN = RemoteRef()


@dataclass(frozen=True)
class PaidApproval:
    approved_block: str
    experiment: str
    phase: str
    planned_usd: float
    headroom_usd: float  # phase cap - phase spend - planned
    prereg_version: str
    costs_path: Path
    experiments: tuple[str, ...] = ()
    max_usd: float = 0.0
    block_spent_usd: float = 0.0
    block_headroom_usd: float = 0.0  # max_usd - block spend - planned (- reserved by others)
    # Set by `require_paid_run` once the run's spend is reserved (`reserve_spend`):
    stream: str = ""
    reservation_id: str = ""         # the run's reservation, released after its costs row
    reserved_block_usd: float = 0.0  # planned spend other running runs hold in the block
    reserved_phase_usd: float = 0.0  # ... and in the phase


def known_experiment(name: str) -> bool:
    return name in costs.EXPERIMENT_PHASE or name.startswith("ext_")


def format_line(name: str, experiments, max_usd) -> str:
    """The approval line for these values (no check that they are valid)."""
    return f"approved_block: {name} | experiments: {','.join(experiments)} | max_usd: {max_usd}"


def parse_line(line: str) -> Approval | None:
    """The approval on `line`, or None if the line is not a valid approval line."""
    text = line.rstrip()
    m = LINE_RE.fullmatch(text)
    if m is None:
        return None
    experiments = tuple(m["experiments"].split(","))
    if len(set(experiments)) != len(experiments):
        return None
    if not all(known_experiment(e) for e in experiments):
        return None
    amount = Decimal(m["max_usd"])
    if amount <= 0 or not math.isfinite(float(amount)):
        return None
    return Approval(m["name"], experiments, amount, text)


def _lines(text: str) -> list[str]:
    # Only "\n" separates lines, as for git and editors. str.splitlines would also split on
    # form feeds, U+2028 and others, which can hide a line start inside what looks like one
    # line.
    return text.split("\n")


_FENCE_OPEN = re.compile(r" {0,3}(?P<run>`{3,}|~{3,})(?P<info>.*)")
_FENCE_CLOSE = re.compile(r" {0,3}(?P<run>`{3,}|~{3,})[ \t]*")
_CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`).+?(?<!`)\1(?!`)")


def _advance(segment: str, fence: tuple[str, int] | None,
             comment: bool) -> tuple[tuple[str, int] | None, bool]:
    """The (open fence, inside an HTML comment) state after one Markdown line."""
    if fence is not None:
        m = _FENCE_CLOSE.fullmatch(segment)
        if m and m["run"][0] == fence[0] and len(m["run"]) >= fence[1]:
            return None, False
        return fence, False
    if not comment:
        m = _FENCE_OPEN.fullmatch(segment)
        if m and not (m["run"][0] == "`" and "`" in m["info"]):
            return (m["run"][0], len(m["run"])), False
        segment = _CODE_SPAN.sub("", segment)  # `<!--` inside a code span is literal text
    pos = 0
    while True:
        if comment:
            end = segment.find("-->", pos)
            if end < 0:
                return None, True
            comment, pos = False, end + 3
        else:
            start = segment.find("<!--", pos)
            if start < 0:
                return None, False
            comment, pos = True, start + 4


def shown_lines(lines: list[str]) -> list[bool]:
    """For each line, whether it starts outside every fenced code block and HTML comment, so
    that Markdown shows it as text. A fence is ``` or ~~~ (up to 3 spaces of indent) and runs
    to a closing fence of the same character at least as long, or to the end of the file; a
    comment runs from <!-- to the next -->. A lone CR also ends a line here, as in CommonMark,
    so it cannot hide a fence. A line holding a fence or comment marker cannot be a valid
    approval line anyway. Where this simplifies CommonMark it errs toward 'not shown', which
    can only refuse."""
    out: list[bool] = []
    fence: tuple[str, int] | None = None
    comment = False
    for line in lines:
        out.append(fence is None and not comment)
        for segment in line.split("\r"):
            fence, comment = _advance(segment, fence, comment)
    return out


def approvals_in(text: str, name: str) -> set[Approval]:
    """The distinct valid approval lines for block `name` in `text`, outside code blocks and
    HTML comments."""
    lines = _lines(text)
    return {a for a, shown in zip(map(parse_line, lines), shown_lines(lines), strict=True)
            if shown and a is not None and a.name == name}


def look_alikes(text: str, name: str) -> list[int]:
    """1-based numbers of lines that mention approved_block and `name` but do not count: they
    do not parse, or they are in a code block or an HTML comment."""
    return _look_alikes(text, "approved_block", name, parse_line)


def _look_alikes(text: str, keyword: str, name: str, parse) -> list[int]:
    mention = re.compile(rf"(?<![A-Za-z0-9._-]){re.escape(name)}(?![A-Za-z0-9._-])")
    lines = _lines(text)
    return [i for i, (x, shown) in enumerate(zip(lines, shown_lines(lines), strict=True), 1)
            if keyword in x.lower() and mention.search(x)
            and (not shown or parse(x) is None)]


# --- clearing a hold -----------------------------------------------------------------------

def format_clear_line(run_id: str) -> str:
    """The line that clears the hold of run `run_id` (no check that it is valid)."""
    return f"cleared_hold: {run_id}"


def parse_clear_line(line: str) -> str | None:
    """The run ID whose hold `line` clears, or None if it is not a valid clearing line."""
    m = CLEAR_RE.fullmatch(line.rstrip())
    return None if m is None else m["run_id"]


def clearances_in(text: str) -> set[str]:
    """The run IDs that valid clearing lines in `text` name, outside code blocks and HTML
    comments."""
    lines = _lines(text)
    return {r for r, shown in zip(map(parse_clear_line, lines), shown_lines(lines), strict=True)
            if shown and r is not None}


def clear_look_alikes(text: str, run_id: str) -> list[int]:
    """1-based numbers of lines that mention cleared_hold and `run_id` but do not count."""
    return _look_alikes(text, "cleared_hold", run_id, parse_clear_line)


def spend_tag(name: str) -> str:
    """The marker a paid launcher puts in its costs.csv row's notes for block `name`."""
    return f"approved_block={name};"


COST_COLUMNS = ("cost_usd_list", "cost_usd_billed_est")


def _usd(value, where: str) -> Decimal | None:
    """The amount in one cost cell, or None if it is empty."""
    s = (value or "").strip()
    if not s:
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"{where}: {s!r} is not a number") from None
    if not d.is_finite() or d < 0:
        raise ValueError(f"{where}: {s!r} is not a finite, non-negative amount")
    return d


def row_spend(row: dict, line: int) -> Decimal:
    """`spend_usd` of one costs.csv row (line `line` of the file): its billed estimate, or its
    list cost if the billed estimate is empty. Both cells are checked even when only one is
    counted. Raises ValueError if a cell is not empty or a finite, non-negative number, or if
    both are empty."""
    listed, billed = (_usd(row.get(k), f"costs.csv line {line} {k}") for k in COST_COLUMNS)
    if listed is None and billed is None:
        raise ValueError(f"costs.csv line {line}: no cost (cost_usd_billed_est and "
                         "cost_usd_list are both empty)")
    return spend_usd(listed, billed)


def check_ledger(rows: list[dict]) -> None:
    """Raise ValueError unless every costs.csv row can be counted: each cost is empty or a
    finite, non-negative number, at least one of the two is filled in, and the experiment
    has a budget phase (or starts with ext_). A NaN would make every budget comparison pass,
    a negative cost would add headroom, a row with no cost would count as free, and a row
    with no phase would count toward no cap."""
    for i, r in enumerate(rows, 2):  # line 1 is the header
        row_spend(r, i)
        experiment = r.get("experiment") or ""
        if not known_experiment(experiment):
            raise ValueError(f"costs.csv line {i}: experiment {experiment!r} has no budget "
                             "phase in common/costs.py")


def block_spend(name: str, rows: list[dict]) -> Decimal:
    """Sum of `spend_usd` (billed estimate, list where there is none) over costs.csv rows
    tagged with `spend_tag(name)`. Raises ValueError if a tagged row's cost cannot be read."""
    tag = spend_tag(name)
    total = Decimal(0)
    for i, r in enumerate(rows, 2):  # line 1 is the header
        if tag in (r.get("notes") or ""):
            total += row_spend(r, i)
    return total


# --- reading the three copies of results/decisions.md --------------------------------------

def _git(repo: Path, *args: str, timeout: float | None = None) -> subprocess.CompletedProcess:
    # GIT_NO_REPLACE_OBJECTS: a local `git replace` ref could otherwise make `git show` print
    # another blob in place of the fetched decisions.md.
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never",
           "GIT_NO_REPLACE_OBJECTS": "1"}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          encoding="utf-8", errors="replace", check=False, env=env,
                          timeout=timeout)


def fetch_remote(repo: Path, ref: RemoteRef = MAIN,
                 timeout_s: float = FETCH_TIMEOUT_S) -> str | None:
    """`git fetch <remote> <branch>`, written with an explicit destination so the
    remote-tracking ref is updated whatever the remote's fetch config says. None on success,
    otherwise why it failed. The remote must be configured: given a name that is not a
    configured remote, git would fetch from a path of that name instead."""
    for part in (ref.remote, ref.branch):
        if not NAME_RE.fullmatch(part) or part.startswith("-"):
            return f"invalid remote ref {ref.label!r}"
    try:
        if _git(repo, "remote", "get-url", ref.remote).returncode != 0:
            return (f"git fetch {ref.remote} {ref.branch} failed: no git remote named "
                    f"{ref.remote!r} is configured")
        r = _git(repo, "fetch", "--quiet", "--no-tags", ref.remote,
                 f"+refs/heads/{ref.branch}:{ref.tracking}", timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return f"git fetch {ref.remote} {ref.branch} timed out after {timeout_s:.0f} s"
    except OSError as e:
        return f"git is not available ({e})"
    if r.returncode != 0:
        detail = (r.stderr or "").strip().splitlines()
        return (f"git fetch {ref.remote} {ref.branch} failed"
                + (f": {detail[-1]}" if detail else ""))
    return None


def _show(repo: Path, rev: str) -> str | None:
    try:
        r = _git(repo, "show", f"{rev}:./{DECISIONS_MD}")
    except OSError:
        return None
    return r.stdout if r.returncode == 0 else None


WORKING_TREE = "the working tree"


def _decisions_copies(repo: Path, remote: RemoteRef) -> dict[str, str | None]:
    """results/decisions.md on `remote` (the remote-tracking ref, so fetch first), in HEAD
    and in the working tree; None where it is missing."""
    try:
        # decoded like the git copies, so an invalid byte elsewhere cannot crash the check
        working = (repo / DECISIONS_MD).read_text(encoding="utf-8", errors="replace")
    except OSError:
        working = None
    return {remote.label: _show(repo, remote.tracking), "HEAD": _show(repo, "HEAD"),
            WORKING_TREE: working}


def find_approval(repo: Path, name: str, remote: RemoteRef = MAIN) -> Approval:
    """The approval of block `name`, present and identical in `remote` (fetched now), HEAD
    and the working tree. Raises PaidCallsNotAllowed with the reason otherwise."""
    if not NAME_RE.fullmatch(name):
        raise PaidCallsNotAllowed(f"block name {name!r} must match {_TOKEN}")
    reason = fetch_remote(repo, remote)
    if reason is not None:
        raise PaidCallsNotAllowed(f"cannot check that the approval of block {name!r} is on "
                                  f"{remote.label}: {reason}")
    texts = _decisions_copies(repo, remote)
    working = texts[WORKING_TREE]
    found = {where: approvals_in(text or "", name) for where, text in texts.items()}
    for where, lines in found.items():
        if len(lines) > 1:
            raise PaidCallsNotAllowed(
                f"{len(lines)} different approval lines for block {name!r} in {DECISIONS_MD} "
                f"({where}); keep exactly one")
    missing = [w for w, lines in found.items() if not lines]
    if missing:
        present = [w for w in found if w not in missing]
        absent_file = [w for w in missing if texts[w] is None]
        hint = look_alikes(working or "", name)
        raise PaidCallsNotAllowed(
            f"no valid approval line for block {name!r} in {DECISIONS_MD} on "
            f"{', '.join(missing)}"
            + (f" (file missing on {', '.join(absent_file)})" if absent_file else "")
            + (f"; present on {', '.join(present)}" if present else "")
            + (f"; malformed or hidden (code block, HTML comment) look-alike lines in the "
               f"working tree: {', '.join(map(str, hint[:5]))}" if hint else "")
            + ". Removing the line anywhere revokes the approval")
    (a,) = found[remote.label]
    changed = [w for w, (b,) in found.items() if b != a]
    if changed:
        raise PaidCallsNotAllowed(
            f"the approval line for block {name!r} differs between {remote.label} and "
            f"{', '.join(changed)} (a changed line counts as a revocation until the same line "
            f"is on {remote.label}, HEAD and the working tree)")
    return a


def prereg_not_committed(repo: Path) -> str | None:
    """None if PREREG.md is tracked by git, present in HEAD and has no uncommitted changes;
    otherwise the reason it does not count as committed (PLAN §16.3)."""
    def ok(*args: str) -> bool:
        try:
            return _git(repo, *args).returncode == 0
        except OSError:
            return False
    if not ok("ls-files", "--error-unmatch", "--", "PREREG.md"):
        return "PREREG.md is not tracked by git"
    if not ok("cat-file", "-e", "HEAD:PREREG.md"):
        return "PREREG.md is not in the HEAD commit"
    if not ok("diff", "--quiet", "HEAD", "--", "PREREG.md"):
        return "PREREG.md has uncommitted changes"
    return None


def prereg_not_on_remote(repo: Path, remote: RemoteRef = MAIN) -> str | None:
    """None if PREREG.md in HEAD is identical (the same blob) to PREREG.md on `remote`;
    otherwise why not. So only the merged, frozen PREREG unlocks paid calls: one committed on
    a branch but not merged, or a HEAD missing an amendment merged to main, does not.

    It does not fetch. It reads the remote-tracking ref, so call it right after
    `fetch_remote` (`find_approval` fetches), as `require_paid_approval` does. Replace refs
    are ignored, as for decisions.md."""
    return _merged_prereg_blob(repo, remote)[1]


def _merged_prereg_blob(repo: Path, remote: RemoteRef) -> tuple[str | None, str | None]:
    """(the blob id of PREREG.md in HEAD, None) if it is the same blob as on `remote`;
    otherwise (None, why not)."""
    def blob(rev: str) -> str | None:
        try:
            r = _git(repo, "rev-parse", "--verify", "--quiet", f"{rev}:PREREG.md")
        except OSError:
            return None
        return r.stdout.strip() if r.returncode == 0 else None
    head = blob("HEAD")
    if head is None:
        return None, "PREREG.md is not in the HEAD commit"
    merged = blob(remote.tracking)
    if merged is None:
        return None, f"PREREG.md is not on {remote.label}"
    if head != merged:
        return None, f"PREREG.md in HEAD differs from PREREG.md on {remote.label}"
    return head, None


def prereg_not_frozen(repo: Path, remote: RemoteRef = MAIN) -> str | None:
    """None if PREREG.md in HEAD is the same blob as on `remote` (`prereg_not_on_remote`) and
    that text is frozen (`common.prereg.prereg_state`: a release version of at least 0.2 with
    no suffix such as -draft, and a status line starting "Frozen"); otherwise why not. The
    draft says no paid call may be made under it, and a draft merged to main passes
    `prereg_not_on_remote`, so `require_paid_run` checks this too. Like
    `prereg_not_on_remote`, it reads the remote-tracking ref without fetching: call it after
    `fetch_remote`."""
    head, reason = _merged_prereg_blob(repo, remote)
    if reason is not None:
        return reason
    try:
        r = _git(repo, "cat-file", "blob", head)
    except OSError as e:
        return f"cannot read PREREG.md in HEAD: {e}"
    if r.returncode != 0:
        return "cannot read PREREG.md in HEAD"
    state = prereg_state(r.stdout)
    return None if state.frozen else f"PREREG.md is not frozen: {state.why_not}"


def holds_not_cleared(repo: Path, lock_path: Path, *, run_id: str | None = None,
                      remote: RemoteRef = MAIN) -> str | None:
    """None if no hold stands; otherwise why a paid run may not start (PREREG §0.3 line 12,
    §7.7). A hold stands for every run in the record next to `lock_path` (common/hold.py)
    whose clearing line `cleared_hold: <run_id>` is not in results/decisions.md on `remote`
    (fetched now), in HEAD and in the working tree, under the rules of the approval line. A
    record that cannot be read refuses, and so does a run whose `run_id` is that of a run
    that placed a hold. Fetches only when a hold is recorded."""
    path = hold.holds_path(lock_path)
    try:
        holds = hold.read_holds(lock_path)
    except hold.HoldRecordError as e:
        return (f"{e}. While it cannot be read, every hold in it stands: no paid run starts "
                f"(PREREG §7.7)")
    if run_id is not None and any(h.run_id == run_id for h in holds):
        return (f"run ID {run_id!r} is that of a run that placed a hold ({path}): give this "
                f"run a new run ID, so that 'cleared_hold: {run_id}' names one run only")
    first: dict[str, hold.Hold] = {}
    for h in holds:  # in the order placed; one clearing line clears a run's every record
        first.setdefault(h.run_id, h)
    runs = list(first.values())
    if not runs:
        return None
    reason = fetch_remote(repo, remote)
    if reason is not None:
        return (f"cannot check whether the researcher has cleared the hold of "
                f"{', '.join(h.run_id for h in runs)} on {remote.label}: {reason}")
    texts = _decisions_copies(repo, remote)
    cleared = {where: clearances_in(text or "") for where, text in texts.items()}
    standing = []
    for h in runs:
        missing = [w for w in texts if h.run_id not in cleared[w]]
        if not missing:
            continue
        present = [w for w in texts if w not in missing]
        absent_file = [w for w in missing if texts[w] is None]
        hint = clear_look_alikes(texts[WORKING_TREE] or "", h.run_id)
        standing.append(
            (h, f"run {h.run_id} ({h.describe()}): '{format_clear_line(h.run_id)}' is not on "
                f"{', '.join(missing)}"
                + (f" (file missing on {', '.join(absent_file)})" if absent_file else "")
                + (f"; present on {', '.join(present)}" if present else "")
                + (f"; malformed or hidden (code block, HTML comment) look-alike lines in "
                   f"the working tree: {', '.join(map(str, hint[:5]))}" if hint else "")))
    if not standing:
        return None
    many = len(standing) > 1
    lines = "; ".join(f"'{format_clear_line(h.run_id)}'" for h, _ in standing)
    return (f"{len(standing)} hold{'s' if many else ''} stand{'' if many else 's'}: "
            + "; ".join(why for _, why in standing)
            + f". A paid run that ends COST_CAP, or whose spend passed its run guard, places a "
            f"hold, and no further paid run starts in either stream, ARC or PersistGym, "
            f"until the researcher clears it (PREREG "
            f"§0.3 line 12, §7.7). The researcher clears {'them' if many else 'it'} by "
            f"merging {'one line per run' if many else 'this line'} into {DECISIONS_MD} on "
            f"{remote.label}, at column 0 and outside any code block or HTML comment: "
            f"{lines}. Each line must also be in HEAD and the working tree; removing it "
            f"anywhere puts the hold back. Hold record: {path}")


def require_paid_approval(*, approved_block: str | None, experiment: str, planned_usd: float,
                          costs_path: Path = costs.COSTS_CSV, repo: Path = runmeta.REPO_ROOT,
                          remote: RemoteRef = MAIN) -> PaidApproval:
    """Every check a paid launcher runs before it may spend. Raises PaidCallsNotAllowed with
    the first reason it may not:
    1. the environment variable PERSISTGYM_ALLOW_PAID is exactly "1";
    2. a block name is given;
    3. the experiment maps to a budget phase in common/costs.py;
    4. the planned spend is a positive, finite number of dollars;
    5. PREREG.md is committed (PLAN §16.3);
    6. the block's approval line is on `remote` (fetched now), in HEAD and in the working
       tree, identical in all three (`find_approval`);
    7. PREREG.md in HEAD is identical to PREREG.md on `remote`, after that same fetch
       (`prereg_not_on_remote`): only a merged (frozen) PREREG unlocks paid calls;
    8. the experiment is in the line's list;
    9. every costs.csv row can be counted (`check_ledger`);
    10. block spend + planned spend <= max_usd;
    11. phase cap - phase spend - planned spend >= 0 (`common.costs.headroom`).
    Spend and planned spend are in the unit of `spend_usd` (the billed estimate, list only
    where a row has none), which is how the transport measures a run's spend."""
    if os.environ.get(ALLOW_ENV) != "1":
        raise PaidCallsNotAllowed(f"paid calls are off: set {ALLOW_ENV}=1 for an approved block")
    if not approved_block or not str(approved_block).strip():
        raise PaidCallsNotAllowed("paid calls need --approved-block <name> (PLAN §16.2)")
    phase = costs.phase_of(experiment)
    if phase not in costs.PHASE_CAPS:
        raise PaidCallsNotAllowed(f"experiment {experiment!r} has no budget phase in "
                                  "common/costs.py")
    # NaN would pass `<= 0` and every later budget comparison, so require a finite number.
    if (planned_usd is None or not math.isfinite(float(planned_usd))
            or float(planned_usd) <= 0):
        raise PaidCallsNotAllowed("paid calls need a positive, finite planned spend "
                                  "(--planned-usd)")
    prereg = runmeta.prereg_version(repo)
    if prereg is None:
        raise PaidCallsNotAllowed("PREREG.md must be committed before any paid call "
                                  "(PLAN §16.3)")
    reason = prereg_not_committed(repo)
    if reason is not None:
        raise PaidCallsNotAllowed(f"PREREG.md must be committed before any paid call "
                                  f"(PLAN §16.3): {reason}")
    block = str(approved_block).strip()
    try:
        approval = find_approval(repo, block, remote)
    except PaidCallsNotAllowed as e:
        raise PaidCallsNotAllowed(
            f"block {block!r} is not approved: {e}. The researcher approves a block by "
            f"merging a line 'approved_block: {block} | experiments: <exp1>,<exp2>,... | "
            f"max_usd: <amount>' into {DECISIONS_MD} on {remote.label} (PLAN §16.2)") from None
    reason = prereg_not_on_remote(repo, remote)  # reads what find_approval just fetched
    if reason is not None:
        raise PaidCallsNotAllowed(f"PREREG.md must be merged to {remote.label} before any "
                                  f"paid call; only the frozen PREREG counts (PLAN §16.3): "
                                  f"{reason}")
    if experiment not in approval.experiments:
        raise PaidCallsNotAllowed(
            f"block {block!r} is approved for {', '.join(approval.experiments)}, not for "
            f"experiment {experiment!r}")
    rows = costs.read_rows(costs_path)
    try:
        check_ledger(rows)
        spent = block_spend(block, rows)
        room = costs.headroom(planned_usd, phase, rows)
    except ValueError as e:
        raise PaidCallsNotAllowed(f"cannot read the spend of block {block!r} and of phase "
                                  f"{phase}: {e}") from None
    planned = Decimal(repr(float(planned_usd)))
    block_room = approval.max_usd - spent - planned
    if block_room < 0:
        raise PaidCallsNotAllowed(
            f"block {block!r} has spent ${float(spent):.2f} of its max_usd "
            f"${approval.max_usd}; planned ${float(planned_usd):.2f} would exceed it by "
            f"${float(-block_room):.2f}: stop and ask the researcher")
    if room < 0:
        raise PaidCallsNotAllowed(
            f"planned ${planned_usd:.2f} would exceed the phase {phase} cap of "
            f"${costs.PHASE_CAPS[phase]:.0f} by ${-room:.2f}: stop and ask the researcher")
    return PaidApproval(block, experiment, phase, float(planned_usd), room, prereg,
                        Path(costs_path), approval.experiments, float(approval.max_usd),
                        float(spent), float(block_room))


def require_paid_run(*, lock: paidlock.HeldLock | None, approved_block: str | None,
                     experiment: str, planned_usd: float, costs_path: Path = costs.COSTS_CSV,
                     repo: Path = runmeta.REPO_ROOT, remote: RemoteRef = MAIN) -> PaidApproval:
    """Every check a paid launcher runs before it may spend, in this order, and the run's
    spend reservation. Both launchers call it: the ARC launcher (arc/run_path.py) and the
    PersistGym transport (harnesses/openai_transport.py, built by harnesses/cli.py). Raises
    PaidCallsNotAllowed with the first reason it may not:
    1. the run holds its stream's paid-run lock `lock` (common/paidlock.py): one paid run at
       a time per stream. The launcher takes it before these checks, so two runs of a stream
       cannot both pass them;
    2. the run's experiment belongs to that stream (`paidlock.stream_of`): an ARC experiment
       under the ARC lock, a PersistGym one under the PersistGym lock;
    3. this checkout's costs.csv can be read and holds the row of each stream's last paid
       run (`paidlock.last_run_missing`): the locks are shared by every checkout, the
       ledger is not, so a run elsewhere would undercount the block and phase spend;
    4. no hold stands: no paid-run lock of either stream is kept by a run that may have
       placed a hold the record does not show (`paidlock.unrecorded_hold`), and every run
       in the hold record next to the lock has its line `cleared_hold: <run_id>` on
       `remote` (fetched now if a hold is recorded), HEAD and the working tree
       (`holds_not_cleared`), and this run does not reuse the run ID (the lock's `run_id`)
       of a run that placed a hold;
    5. `require_paid_approval`: the paid switch, the block's approval line on `remote`
       (fetched now), HEAD and the working tree, PREREG.md committed and the same blob as on
       `remote`, the experiment listed, block and phase room;
    6. that PREREG.md is frozen (`prereg_not_frozen`), read after 5's fetch;
    7. `reserve_spend`: under the budget mutex both streams take, block and phase room
       counting the planned spend that the other stream's running run has reserved, then
       this run's own reservation. The returned approval names it (`reservation_id`); the
       launcher releases it once the run's costs.csv row is written
       (`paidlock.release_reservation`), and releasing the lock releases it too."""
    if lock is None:
        raise PaidCallsNotAllowed(
            "paid calls need the paid-run lock (common/paidlock.py), taken by the launcher "
            "before the spend checks: one paid run at a time per stream. Start PersistGym "
            "runs with `python -m harnesses` and ARC runs with `python -m arc.run_path`")
    if not lock.holds():
        raise PaidCallsNotAllowed(
            f"this run does not hold the paid-run lock {lock.path}: it is gone or another "
            f"run's (one paid run at a time per stream)")
    stream = lock.stream
    if stream is None:
        raise PaidCallsNotAllowed(
            f"the paid-run lock {lock.path} names no stream ({', '.join(paidlock.STREAMS)}); "
            f"take it with common.paidlock.paid_run_lock")
    wanted = paidlock.stream_of(experiment)
    if wanted is None:   # the budget experiments and the streams' have the same keys
        raise PaidCallsNotAllowed(f"experiment {experiment!r} has no budget phase in "
                                  f"common/costs.py, so no paid-run stream either")
    if wanted != stream:
        raise PaidCallsNotAllowed(
            f"experiment {experiment!r} runs in the {wanted} stream, but this run holds the "
            f"{stream} stream's lock: start ARC runs with `python -m arc.run_path` and "
            f"PersistGym runs with `python -m harnesses`")
    try:
        rows = costs.read_rows(costs_path)
    except (OSError, ValueError) as e:
        raise PaidCallsNotAllowed(f"cannot read {costs_path}: {e}") from None
    try:
        with paidlock.budget_mutex(lock.path):
            reason = paidlock.last_run_missing(lock.path, rows)
    except OSError as e:
        raise PaidCallsNotAllowed(f"cannot read the last paid runs next to {lock.path}: "
                                  f"{e}") from None
    if reason is not None:
        raise PaidCallsNotAllowed(reason)
    run_id = lock.info.get("run_id") if isinstance(lock.info, dict) else None
    reason = paidlock.unrecorded_hold(lock.path)   # a hold that could not be recorded
    if reason is not None:
        raise PaidCallsNotAllowed(reason)
    try:  # the holds this check sees; one placed after it refuses in reserve_spend
        holds_seen = {h.run_id for h in hold.read_holds(lock.path)}
    except hold.HoldRecordError:
        holds_seen = set()                  # holds_not_cleared refuses it
    reason = holds_not_cleared(repo, lock.path, run_id=run_id if isinstance(run_id, str)
                               else None, remote=remote)
    if reason is not None:
        raise PaidCallsNotAllowed(reason)
    granted = require_paid_approval(approved_block=approved_block, experiment=experiment,
                                    planned_usd=planned_usd, costs_path=costs_path, repo=repo,
                                    remote=remote)
    reason = prereg_not_frozen(repo, remote)  # reads what require_paid_approval fetched
    if reason is not None:
        raise PaidCallsNotAllowed(f"paid runs need the frozen, merged PREREG.md "
                                  f"(PLAN §16.3): {reason}")
    return reserve_spend(lock, granted, holds_seen=holds_seen)


def _listed(reservations: list[paidlock.Reservation]) -> str:
    return "; ".join(r.describe() for r in reservations)


_WAIT = ("wait for that run to end, or stop and ask the researcher. If no run of the other "
         "stream is going, its reservation is left over from a run that did not end "
         "cleanly: check that results/costs.csv has its row, then delete the reservation "
         "file by hand")


def reserve_spend(lock: paidlock.HeldLock, granted: PaidApproval, *,
                  holds_seen: set[str] | frozenset[str] = frozenset()) -> PaidApproval:
    """The last step of `require_paid_run` (PREREG §12, "Operational"): count the planned
    spend of the other stream's running run against the block and phase this run would
    spend in, and reserve this run's own. All of it under `paidlock.budget_mutex`, which both
    streams take, so two runs going at once cannot both pass on the same room. Under the
    mutex it reads, in this order:
    1. the spend reservations next to the lock (`paidlock.read_reservations`). One of this
       run's stream that this run did not write is left over from a run that did not end
       cleanly, and refuses until the operator has deleted it by hand;
    2. the hold record: a hold placed since `require_paid_run` checked it (`holds_seen`; by
       a run of the other stream that ended meanwhile) refuses, and so does a lock kept
       meanwhile by a run whose hold could not be recorded (`paidlock.unrecorded_hold`);
    3. costs.csv and the last-run records, after the reservations, because a run that ends
       writes its row and its record before it removes its reservation: what this reads
       counts that run's spend once or twice, never not at all;
    then it checks block spend + the planned spend reserved by other runs of the block +
    this run's planned spend <= max_usd, and the same for the phase cap. If both hold it
    writes this run's reservation (replacing an earlier one of this same run, as when a
    probe moves to its next model) and returns `granted` with the room left after it."""
    block, phase = granted.approved_block, granted.phase
    try:
        with paidlock.budget_mutex(lock.path):
            try:
                reservations = paidlock.read_reservations(lock.path)
            except paidlock.ReservationError as e:
                raise PaidCallsNotAllowed(
                    f"{e}. While it cannot be read, its run's planned spend cannot be "
                    f"counted, so no paid run starts: check that no paid run is going and "
                    f"that results/costs.csv has its row, then fix or delete it by hand "
                    f"(PREREG §12)") from None
            for r in reservations:
                if r.stream == lock.stream and r.token != lock.token:
                    raise PaidCallsNotAllowed(
                        f"a spend reservation of the {r.stream} stream is left over: "
                        f"{r.describe()}. This run holds the {r.stream} stream's lock, so "
                        f"the run that wrote it is not going: it did not end cleanly (it "
                        f"crashed, or it kept its lock, which was then deleted by hand). It "
                        f"would keep counting ${float(r.planned_usd):.2f} against block "
                        f"{r.approved_block} and phase {r.phase}. Check that "
                        f"results/costs.csv has that run's row (tagged "
                        f"{spend_tag(r.approved_block)}) and, if it ended COST_CAP or passed "
                        f"its run guard, that its hold is in {hold.holds_path(lock.path)}, "
                        f"then delete {r.path} by hand")
            others = [r for r in reservations if r.stream != lock.stream]
            try:
                new_holds = sorted({h.run_id for h in hold.read_holds(lock.path)}
                                   - set(holds_seen))
            except hold.HoldRecordError as e:
                raise PaidCallsNotAllowed(f"{e}. While it cannot be read, every hold in it "
                                          f"stands: no paid run starts (PREREG §7.7)") from None
            if new_holds:
                raise PaidCallsNotAllowed(
                    f"a hold was placed while this run was being checked, by "
                    f"{', '.join(new_holds)} (in {hold.holds_path(lock.path)}): no further "
                    f"paid run starts in either stream until the researcher clears it "
                    f"(PREREG §0.3 line 12, §7.7). Run again to see the line that clears it")
            reason = paidlock.unrecorded_hold(lock.path)   # a lock kept meanwhile
            if reason is not None:
                raise PaidCallsNotAllowed(reason)
            try:
                rows = costs.read_rows(granted.costs_path)
            except (OSError, ValueError) as e:
                raise PaidCallsNotAllowed(f"cannot read {granted.costs_path}: {e}") from None
            reason = paidlock.last_run_missing(lock.path, rows)
            if reason is not None:
                raise PaidCallsNotAllowed(reason)
            try:
                check_ledger(rows)
                spent = block_spend(block, rows)
                phase_spent = costs.spend_by_phase(rows).get(phase, 0.0)
            except ValueError as e:
                raise PaidCallsNotAllowed(f"cannot read the spend of block {block!r} and of "
                                          f"phase {phase}: {e}") from None
            in_block = [r for r in others if r.approved_block == block]
            in_phase = [r for r in others if r.phase == phase]
            block_reserved = sum((r.planned_usd for r in in_block), Decimal(0))
            phase_reserved = sum((r.planned_usd for r in in_phase), Decimal(0))
            planned = Decimal(repr(float(granted.planned_usd)))
            max_usd = Decimal(repr(float(granted.max_usd)))
            block_room = max_usd - spent - block_reserved - planned
            if block_room < 0:
                raise PaidCallsNotAllowed(
                    f"block {block!r} has spent ${float(spent):.2f} of its max_usd "
                    f"${float(max_usd):g}"
                    + (f", and the other stream's running run has reserved "
                       f"${float(block_reserved):.2f} of it until its costs row is written "
                       f"({_listed(in_block)})" if in_block else "")
                    + f"; planned ${float(planned):.2f} would exceed it by "
                    f"${float(-block_room):.2f}: "
                    + (_WAIT if in_block else "stop and ask the researcher"))
            cap = costs.PHASE_CAPS[phase]
            room = cap - phase_spent - float(phase_reserved) - float(planned)
            if room < 0:
                raise PaidCallsNotAllowed(
                    f"planned ${float(planned):.2f} would exceed the phase {phase} cap of "
                    f"${cap:.0f} by ${-room:.2f}, counting phase spend ${phase_spent:.2f}"
                    + (f" and ${float(phase_reserved):.2f} reserved by the other stream's "
                       f"running run until its costs row is written ({_listed(in_phase)})"
                       if in_phase else "")
                    + ": " + (_WAIT if in_phase else "stop and ask the researcher"))
            mine = paidlock.write_reservation(lock, approved_block=block,
                                              experiment=granted.experiment, phase=phase,
                                              planned_usd=planned)
    except OSError as e:
        raise PaidCallsNotAllowed(f"cannot reserve this run's planned spend next to "
                                  f"{lock.path}: {e}") from None
    return replace(granted, headroom_usd=room, block_spent_usd=float(spent),
                   block_headroom_usd=float(block_room), stream=mine.stream,
                   reservation_id=mine.reservation_id,
                   reserved_block_usd=float(block_reserved),
                   reserved_phase_usd=float(phase_reserved))
