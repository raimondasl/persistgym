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

A line that breaks any of these rules is malformed and never counts. The refusal message
names look-alike lines so a typo is easy to find.

**Where the line must be.** The same line (compared after removing trailing whitespace)
must be in results/decisions.md in all three of:
1. origin/main, fetched fresh (`git fetch origin main`). If the fetch fails, the guard
   refuses. An approval therefore reaches the guard only through the researcher's merge;
2. the HEAD commit;
3. the working-tree file.
Removing or changing the line in any of the three counts as a revocation. Two different
valid lines for one block name are ambiguous and refuse.

**What it allows.** The run's experiment must be in the line's list. Block spend is the sum,
over results/costs.csv rows whose `notes` contain "approved_block=<name>;", of
max(cost_usd_list, cost_usd_billed_est). The run is refused if block spend + planned spend
> max_usd. The phase-cap check (`common.costs.headroom`) applies as well.

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


def approvals_in(text: str, name: str) -> set[Approval]:
    """The distinct valid approval lines for block `name` in `text`."""
    return {a for a in map(parse_line, _lines(text)) if a is not None and a.name == name}


def look_alikes(text: str, name: str) -> list[int]:
    """1-based numbers of lines that mention approved_block and `name` but do not parse."""
    mention = re.compile(rf"(?<![A-Za-z0-9._-]){re.escape(name)}(?![A-Za-z0-9._-])")
    return [i for i, x in enumerate(_lines(text), 1)
            if "approved_block" in x.lower() and mention.search(x) and parse_line(x) is None]


def spend_tag(name: str) -> str:
    """The marker a paid launcher puts in its costs.csv row's notes for block `name`."""
    return f"approved_block={name};"


def _usd(value, where: str) -> Decimal:
    s = (value or "").strip()
    if not s:
        return Decimal(0)
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"{where}: {s!r} is not a number") from None
    if not d.is_finite() or d < 0:
        raise ValueError(f"{where}: {s!r} is not a finite, non-negative amount")
    return d


def block_spend(name: str, rows: list[dict]) -> Decimal:
    """Sum of max(cost_usd_list, cost_usd_billed_est) over costs.csv rows tagged with
    `spend_tag(name)`. Raises ValueError if a tagged row's cost cannot be read."""
    tag = spend_tag(name)
    total = Decimal(0)
    for i, r in enumerate(rows, 2):  # line 1 is the header
        if tag in (r.get("notes") or ""):
            total += max(_usd(r.get(k), f"costs.csv line {i} {k}")
                         for k in ("cost_usd_list", "cost_usd_billed_est"))
    return total


# --- reading the three copies of results/decisions.md --------------------------------------

def _git(repo: Path, *args: str, timeout: float | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          encoding="utf-8", errors="replace", check=False, env=env,
                          timeout=timeout)


def fetch_remote(repo: Path, ref: RemoteRef = MAIN,
                 timeout_s: float = FETCH_TIMEOUT_S) -> str | None:
    """`git fetch <remote> <branch>`, written with an explicit destination so the
    remote-tracking ref is updated whatever the remote's fetch config says. None on success,
    otherwise why it failed."""
    for part in (ref.remote, ref.branch):
        if not NAME_RE.fullmatch(part) or part.startswith("-"):
            return f"invalid remote ref {ref.label!r}"
    try:
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
        working = (repo / DECISIONS_MD).read_text(encoding="utf-8")
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
            + (f"; malformed look-alike lines in the working tree: "
               f"{', '.join(map(str, hint[:5]))}" if hint else "")
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
    7. the experiment is in the line's list;
    8. block spend + planned spend <= max_usd;
    9. phase cap - phase spend - planned spend >= 0 (`common.costs.headroom`)."""
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
    if experiment not in approval.experiments:
        raise PaidCallsNotAllowed(
            f"block {block!r} is approved for {', '.join(approval.experiments)}, not for "
            f"experiment {experiment!r}")
    rows = costs.read_rows(costs_path)
    try:
        spent = block_spend(block, rows)
    except ValueError as e:
        raise PaidCallsNotAllowed(f"cannot read the spend of block {block!r}: {e}") from None
    planned = Decimal(repr(float(planned_usd)))
    block_room = approval.max_usd - spent - planned
    if block_room < 0:
        raise PaidCallsNotAllowed(
            f"block {block!r} has spent ${float(spent):.2f} of its max_usd "
            f"${approval.max_usd}; planned ${float(planned_usd):.2f} would exceed it by "
            f"${float(-block_room):.2f}: stop and ask the researcher")
    room = costs.headroom(planned_usd, phase, rows)
    if room < 0:
        raise PaidCallsNotAllowed(
            f"planned ${planned_usd:.2f} would exceed the phase {phase} cap of "
            f"${costs.PHASE_CAPS[phase]:.0f} by ${-room:.2f}: stop and ask the researcher")
    return PaidApproval(block, experiment, phase, float(planned_usd), room, prereg,
                        Path(costs_path), approval.experiments, float(approval.max_usd),
                        float(spent), float(block_room))
