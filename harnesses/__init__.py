"""PersistGym harness cells (PLAN.md §6, §7): payload builders for the OpenAI Responses API,
a fake model, a runner skeleton, a guarded paid transport and the replay-toggle probes.
See harnesses/DESIGN.md.

    from harnesses import CELLS, HarnessConfig, HarnessSession, FakeModel, run_episode
"""

from harnesses.cells import CELLS, NOTES_INSTRUCTION, REPLAY_PAIRS, CellSpec, get_cell
from harnesses.config import HarnessConfig
from harnesses.fake import FakeModel
from harnesses.runner import check_echo, run_batch, run_episode
from harnesses.session import HarnessSession, Request

__all__ = [
    "CELLS",
    "NOTES_INSTRUCTION",
    "REPLAY_PAIRS",
    "CellSpec",
    "FakeModel",
    "HarnessConfig",
    "HarnessSession",
    "Request",
    "check_echo",
    "get_cell",
    "run_batch",
    "run_episode",
]
