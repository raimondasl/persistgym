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

**What it allows.** The run's experiment must be in the line's list. Spend is measured one
way everywhere (`spend_usd`, defined in common/costs.py): the billed estimate, or the list
cost where a row has no billed estimate. Every cap and estimate for PersistGym in PLAN §12,
§16 and §17 is in Flex-billed dollars, and D23 makes the billed estimate the primary cost
basis; counting Flex at list would trip the caps at about half the real spend. Block spend
is the sum of `spend_usd` over results/costs.csv rows whose `notes` contain
"approved_block=<name>;". The run is refused if block spend + planned spend > max_usd, and
the transport stops a run before a call once the run's own spend, measured the same way,
reaches the planned spend. The phase-cap check (`common.costs.headroom`) uses the same
measure. The list cost is still logged in every row and reported. Every costs.csv row must
be readable for either check: a cost that is not empty or a finite, non-negative number, a
row with neither cost, or an experiment with no budget phase, refuses. The billed estimate
comes from our price table; the provider-side hard spend limits, which the researcher sets
in real billed dollars, remain the backstop against under-estimation.

The guard protects against mistakes (an example line, a stale or unmerged approval, a
corrupt ledger), not against someone who edits this code or the repository's git config.

The guard never writes an approval. The only thing it changes is the remote-tracking ref
(refs/remotes/origin/main), by fetching.
"""

from __future__ import annotations

import math
import os
import re
import subprocess
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from common import costs, runmeta
from common.costs import spend_usd  # the one spend measure, re-exported for the launchers

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
    block_headroom_usd: float = 0.0  # max_usd - block spend - planned


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
    mention = re.compile(rf"(?<![A-Za-z0-9._-]){re.escape(name)}(?![A-Za-z0-9._-])")
    lines = _lines(text)
    return [i for i, (x, shown) in enumerate(zip(lines, shown_lines(lines), strict=True), 1)
            if "approved_block" in x.lower() and mention.search(x)
            and (not shown or parse_line(x) is None)]


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


def find_approval(repo: Path, name: str, remote: RemoteRef = MAIN) -> Approval:
    """The approval of block `name`, present and identical in `remote` (fetched now), HEAD
    and the working tree. Raises PaidCallsNotAllowed with the reason otherwise."""
    if not NAME_RE.fullmatch(name):
        raise PaidCallsNotAllowed(f"block name {name!r} must match {_TOKEN}")
    reason = fetch_remote(repo, remote)
    if reason is not None:
        raise PaidCallsNotAllowed(f"cannot check that the approval of block {name!r} is on "
                                  f"{remote.label}: {reason}")
    try:
        # decoded like the git copies, so an invalid byte elsewhere cannot crash the check
        working = (repo / DECISIONS_MD).read_text(encoding="utf-8", errors="replace")
    except OSError:
        working = None
    texts = {remote.label: _show(repo, remote.tracking), "HEAD": _show(repo, "HEAD"),
             "the working tree": working}
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
    def blob(rev: str) -> str | None:
        try:
            r = _git(repo, "rev-parse", "--verify", "--quiet", f"{rev}:PREREG.md")
        except OSError:
            return None
        return r.stdout.strip() if r.returncode == 0 else None
    head = blob("HEAD")
    if head is None:
        return "PREREG.md is not in the HEAD commit"
    merged = blob(remote.tracking)
    if merged is None:
        return f"PREREG.md is not on {remote.label}"
    if head != merged:
        return f"PREREG.md in HEAD differs from PREREG.md on {remote.label}"
    return None


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
