"""Randomised cross-check of every cell's payloads against a brute-force reference.

The snapshot tests use uniform turn sizes. Here observation and reply lengths vary per turn,
W varies, the instructions count toward W in half the trials, and Σ cells run with
`summary_keep_recent_tokens` 0 or > 0. The reference recomputes, from token counts alone and
without `persistgym.survival.window_keep_start`, which turns every request must carry:
* window: the earliest start whose kept turns + observation (+ instructions) fit in W, never
  moving backwards;
* summary: a summary request exactly when bridge + turns since the last compaction +
  observation (+ instructions) exceed W, compacting everything (keep 0) or everything but the
  newest turns that fit in the keep budget (at least one turn);
* full: every turn.
It then checks the visible texts of the payload item by item, one reasoning item per turn
sent verbatim, and at most one bridge.
"""

from __future__ import annotations

import random

import pytest

from harnesses.cells import CELLS
from harnesses.config import ARC_SUMMARY_BRIDGE_TEMPLATE, HarnessConfig
from harnesses.fake import FakeModel, padded_text
from harnesses.items import item_text
from harnesses.session import HarnessSession
from harnesses.tests.conftest import BRIDGE_PREFIX
from persistgym import tokens

SYSTEM = "You are the operator.\nReply with one action."


def _summary(j: int) -> str:
    return padded_text(f"SUMMARY s{j}", 40)


def _check_trial(seed: int) -> None:
    rng = random.Random(seed)
    n = rng.randint(3, 14)
    W = rng.randint(300, 2000)
    count_system = rng.random() < 0.5
    keep = rng.choice([0, rng.randint(1, W - 1)])
    cell = CELLS[rng.choice(list(CELLS))]
    obs = [padded_text(f"OBS[{i}]", rng.randint(10, 400)) for i in range(n)]
    reps = [padded_text(f"REPLY[{i}]", rng.randint(10, 300)) for i in range(n)]
    fake = FakeModel(lambda p, i: reps[i], summary_fn=lambda p, j: _summary(j))
    s = HarnessSession(cell, SYSTEM, HarnessConfig(summary_keep_recent_tokens=keep),
                       W_tokens=W, count_system=count_system)
    sys_t = tokens.count(s.instructions) if count_system else 0
    ot = [tokens.count(o) for o in obs]
    rt = [tokens.count(r) for r in reps]

    def span(a: int, m: int) -> int:  # turns a..m-1 plus observation m
        return sum(ot[i] + rt[i] for i in range(a, m)) + ot[m]

    start, bridge_t, n_summ = 0, 0, 0
    for m in range(n):
        s.observe(obs[m])
        while True:
            req = s.next_request()
            resp = fake.send(req.payload)
            due = (cell.history == "summary" and start < m
                   and sys_t + bridge_t + span(start, m) > W)
            assert (req.kind == "summary") == due, (seed, m)
            if req.kind == "summary":
                end = m
                if keep:
                    fits = [e for e in range(start + 1, m + 1) if sys_t + span(e, m) <= keep]
                    end = fits[0] if fits else m
                assert req.info["compact_turns"] == [start, end], (seed, m)
                texts = [item_text(i) for i in req.payload["input"]
                         if i.get("type") != "reasoning"]
                expected = ([ARC_SUMMARY_BRIDGE_TEMPLATE.format(summary=_summary(n_summ))]
                            if n_summ else [])
                for i in range(start, end):
                    expected += [obs[i], reps[i]]
                assert texts[:-1] == expected, (seed, m)
                s.record(req, resp)
                n_summ += 1
                start = end
                bridge_t = tokens.count(ARC_SUMMARY_BRIDGE_TEMPLATE.format(summary=_summary(n_summ)))
                continue
            if cell.history == "window":
                start = max(start, next(a for a in range(m + 1)
                                        if a == m or sys_t + span(a, m) <= W))
            elif cell.history == "full":
                start = 0
            expected = ([ARC_SUMMARY_BRIDGE_TEMPLATE.format(summary=_summary(n_summ))]
                        if cell.history == "summary" and n_summ else [])
            for i in range(start, m):
                expected += [obs[i], reps[i]]
            expected.append(obs[m])
            items = req.payload["input"]
            assert [item_text(i) for i in items if i.get("type") != "reasoning"] == expected, \
                (seed, cell.cell_id, m)
            assert sum(i.get("type") == "reasoning" for i in items) == m - start
            assert sum(item_text(i).startswith(BRIDGE_PREFIX) for i in items) <= 1
            s.record(req, resp)
            break


@pytest.mark.parametrize("block", range(4))
def test_payloads_match_brute_force_reference(block):
    for seed in range(block * 25, (block + 1) * 25):
        _check_trial(seed)
