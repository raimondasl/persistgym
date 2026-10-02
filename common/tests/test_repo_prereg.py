"""The repository's own PREREG.md reads as frozen (PREREG §0.4) after its amendments.

Amendment R1 (§17.1, 2026-10-02) has a line starting "**Status.**" at the end of the file;
`common.prereg` and `runmeta.prereg_version` read the first Version and Status lines, so the
frozen ones at the top still decide. Every paid launcher refuses an unfrozen PREREG.md."""

from __future__ import annotations

from common import runmeta
from common.prereg import prereg_state


def test_the_repository_prereg_reads_as_frozen():
    text = (runmeta.REPO_ROOT / "PREREG.md").read_text(encoding="utf-8")
    state = prereg_state(text)
    assert state.frozen, state.why_not
    assert state.status.lower().startswith("frozen")
    assert runmeta.prereg_version() == state.version
