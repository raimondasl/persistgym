"""Whether a PREREG.md text is frozen (PREREG §0.4): the one rule that the game draw
(arc/draw_games.py) and every paid launcher (`common.approval.prereg_not_frozen`) use.

Frozen means a ``Version: x.y`` line with x.y >= 0.2 and no suffix such as ``-draft``, and a
``Status:`` line whose text starts with "Frozen" (any case). The freeze commit changes only
those two lines and the sign-off table (PREREG §0.4), so a draft can never pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MIN_PREREG_VERSION = (0, 2)

_VERSION_RE = re.compile(r"^\**Version:?\**:?\s*(\S+)", re.MULTILINE)
_STATUS_RE = re.compile(r"^\**Status:?\**:?\s*(.*)$", re.MULTILINE)
_RELEASE_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


@dataclass(frozen=True)
class PreregState:
    version: str | None
    status: str | None
    frozen: bool
    why_not: str = ""


def prereg_state(text: str | None) -> PreregState:
    """Frozen iff ``Version: x.y`` (x.y >= 0.2, no suffix) and a status line starting "Frozen"."""
    if text is None:
        return PreregState(None, None, False, "PREREG.md does not exist at this commit")
    vm, sm = _VERSION_RE.search(text), _STATUS_RE.search(text)
    version = vm.group(1) if vm else None
    status = sm.group(1).strip().strip("*").strip() if sm else None
    rel = _RELEASE_RE.fullmatch(version or "")
    if rel is None:
        why = (f"version {version!r} is not a release version x.y" if version
               else "PREREG.md has no 'Version:' line")
        return PreregState(version, status, False, why)
    if (int(rel.group(1)), int(rel.group(2))) < MIN_PREREG_VERSION:
        return PreregState(version, status, False,
                           f"version {version} is below {'.'.join(map(str, MIN_PREREG_VERSION))}")
    if not (status or "").lower().startswith("frozen"):
        return PreregState(version, status, False,
                           f"status line does not start with 'Frozen': {status!r}")
    return PreregState(version, status, True)
