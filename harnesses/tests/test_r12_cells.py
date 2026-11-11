"""Payload snapshot tests of R12's cells and of claude-sonnet-5-5 (harnesses/cells.py
`R12_CELLS`, harnesses/pricing.py; PREREG §17.12, amendment R12), on the Messages wire, hand-
derived as in test_messages_wire.py.

* The notes cells: W-nd-0 is W-n-0 with the disclosure sentence after the notes instruction,
  and W-nx-0 with a neutral sentence of the provenance sentence's length (32 project tokens)
  that says nothing about notes, sources or history. Their text is asserted literally. Their
  bodies keep W-n-0's turns (the notes text never counts toward W, D5) and differ from W-n-0's
  in `system` only.
* The block window (W-b-0): W-0's bodies but for which turns are kept. The start stays put
  until the kept context passes W, then drops to W // 2 (`persistgym.survival.block_keep_start`),
  so between drops each request's messages begin with the previous request's. The sequences
  are hand-derived, the boundaries checked on both sides, and a brute-force reference agrees on
  random lengths. The kept context never passes W, so a far fact never survives.
* claude-sonnet-5-5: its bodies equal Haiku's but for `model`, pass the wire's payload check at
  medium effort, and are priced at the card checked on 2026-11-11.
"""

from __future__ import annotations

import random

import pytest

from harnesses.cells import (
    CELLS,
    DISCLOSURE_SENTENCE,
    NEUTRAL_SENTENCE,
    NOTES_VARIANT_CELLS,
    PROVENANCE_SENTENCE,
    R12_CELLS,
    REPLAY_OFF_CELLS,
    REPLAY_PAIRS,
    CellSpec,
    get_cell,
)
from harnesses.config import HarnessConfig
from harnesses.fake import FakeModel
from harnesses.items import item_text
from harnesses.pricing import CACHE_WRITE_MULTIPLIER, PRICES, cost_usd, price_for
from harnesses.runner import run_episode
from harnesses.tests.conftest import SYSTEM, run_synthetic
from harnesses.tests.test_messages_wire import (
    CFG,
    HAIKU,
    WINDOW_KEEP,
    _assert_wire_invariants,
    _body,
    _turns,
    labels,
    no_reasoning_turns,
)
from harnesses.tests.test_notes_variant_cells import ARC_SENTENCE, DISCLOSURE, PROVENANCE
from harnesses.wire import MESSAGES
from persistgym import tokens
from persistgym.survival import block_keep_start, block_keep_starts, window_keep_start

SONNET = "claude-sonnet-5-5"
SONNET_CFG = HarnessConfig(model=SONNET, reasoning_effort="medium", service_tier="standard")
NEUTRAL = ("For each action you choose, also check how it is written: the verb that the EVENT "
           "asks for, and its argument in the syntax that the EVENT shows.")
NOTES_TEXT = {"W-nd-0": ARC_SENTENCE + " " + DISCLOSURE, "W-nx-0": ARC_SENTENCE + " " + NEUTRAL}
NOTES_CELLS = ("W-nd-0", "W-nx-0")
# Hand-derived (module docstring): 200-token observations, 50-token replies, W = 1000. A turn
# costs 250 and the current observation 200: the context passes W at steps 4 and 7, and the
# start drops to the first turn that fits in 500 (one earlier turn plus the observation).
BLOCK_KEEP = [0, 0, 0, 0, 3, 3, 3, 6, 6]


# --- the cells -----------------------------------------------------------------------------

def test_the_sentences_are_r12s_literally():
    assert NEUTRAL_SENTENCE == NEUTRAL
    assert DISCLOSURE_SENTENCE == DISCLOSURE and PROVENANCE_SENTENCE == PROVENANCE
    for cid, text in NOTES_TEXT.items():
        assert get_cell(cid).notes_instruction == text, cid
    assert get_cell("W-b-0").notes_instruction is None


def test_the_neutral_sentence_matches_the_provenance_sentence_in_length_only():
    assert tokens.count(NEUTRAL) == tokens.count(PROVENANCE) == 32
    assert (tokens.count(NOTES_TEXT["W-nx-0"])
            == tokens.count(ARC_SENTENCE + " " + PROVENANCE) == 53)
    low = NEUTRAL.lower()
    for word in ("memory", "remember", "note", "source", "record", "history", "earlier",
                 "previous", "carry", "fact", "came from", "drop", "log", "context"):
        assert word not in low, word


def test_the_cells_are_w_n_0_or_w_0_but_for_their_one_change():
    for cid in NOTES_CELLS:
        c, base = get_cell(cid), CELLS["W-n-0"]
        assert c is R12_CELLS[cid] and c.truncation == "slide" and c.notes_extra
        assert (c.history, c.notes, c.replay, c.reasoning_context, c.optional) == (
            base.history, base.notes, base.replay, base.reasoning_context, base.optional)
    c, base = get_cell("W-b-0"), CELLS["W-0"]
    assert c is R12_CELLS["W-b-0"] and c.truncation == "block" and not c.notes_extra
    assert (c.history, c.notes, c.replay, c.reasoning_context, c.optional) == (
        base.history, base.notes, base.replay, base.reasoning_context, base.optional)
    assert list(R12_CELLS) == ["W-nd-0", "W-nx-0", "W-b-0"]
    assert all(c.truncation == "slide" for c in (*CELLS.values(), *NOTES_VARIANT_CELLS.values()))


def test_they_stay_out_of_plans_table():
    for cid in R12_CELLS:
        assert cid not in CELLS and cid not in NOTES_VARIANT_CELLS
        assert cid not in REPLAY_OFF_CELLS and all(cid not in pair for pair in REPLAY_PAIRS)


def test_a_bad_truncation_raises():
    with pytest.raises(ValueError, match="bad truncation"):
        CellSpec("W-y-0", "window", notes=False, replay=False, truncation="sometimes")
    with pytest.raises(ValueError, match="block truncation needs a window cell"):
        CellSpec("F-y-0", "full", notes=False, replay=False, truncation="block")


# --- the notes cells' bodies ---------------------------------------------------------------

@pytest.mark.parametrize("cell_id", NOTES_CELLS)
def test_notes_cell_payloads_exactly(cell_id):
    system = SYSTEM + "\n" + NOTES_TEXT[cell_id]
    _, model, requests = run_synthetic(get_cell(cell_id), cfg=CFG)
    assert [labels(p) for p in model.calls] == [no_reasoning_turns(k, m)
                                                for m, k in enumerate(WINDOW_KEEP)]
    for m, (k, p) in enumerate(zip(WINDOW_KEEP, model.calls, strict=True)):
        assert p == _body(system, _turns(k, m))
        _assert_wire_invariants(p)
    assert all("truncation" not in r.info for r in requests)


@pytest.mark.parametrize("cell_id", NOTES_CELLS)
def test_they_differ_from_w_n_0_in_system_only(cell_id):
    for W, count_system in ((1000, False), (965, True), (949, False)):
        _, mv, rv = run_synthetic(get_cell(cell_id), cfg=CFG, W=W, count_system=count_system)
        _, mn, rn = run_synthetic(CELLS["W-n-0"], cfg=CFG, W=W, count_system=count_system)
        assert [r.info for r in rv] == [r.info for r in rn]
        for pv, pn in zip(mv.calls, mn.calls, strict=True):
            assert pv["system"] == SYSTEM + "\n" + NOTES_TEXT[cell_id]
            assert {**pv, "system": pn["system"]} == pn


# --- the block window ----------------------------------------------------------------------

def test_block_keep_start_by_hand():
    obs, rep = [200] * 9, [50] * 8
    assert block_keep_starts(obs, rep, 1000) == BLOCK_KEEP
    # one step at a time, from the previous start
    start = 0
    for m, want in enumerate(BLOCK_KEEP):
        start = block_keep_start(obs[: m + 1], rep[:m], 1000, start=start)
        assert start == want
    # the sliding window drops one turn at every step instead
    assert [window_keep_start(obs[: m + 1], rep[:m], 1000) for m in range(9)] == WINDOW_KEEP


@pytest.mark.parametrize("W, system, replies, want", [
    (950, 0, {}, [0, 0, 0, 0, 3, 3, 3, 6, 6]),       # 950 fits exactly: no drop at step 3
    (949, 0, {}, [0, 0, 0, 2, 2, 4, 4, 6, 6]),       # one token less: drop at step 3
    (900, 0, {}, [0, 0, 0, 2, 2, 4, 4, 6, 6]),       # refill to 450 fits exactly
    (899, 0, {}, [0, 0, 0, 3, 3, 3, 6, 6, 6]),       # refill to 449: one turn fewer kept
    (901, 0, {}, [0, 0, 0, 2, 2, 4, 4, 6, 6]),       # W // 2 is 450, as at 900
    (1000, 0, {1: 300}, [0, 0, 0, 2, 2, 2, 5, 5, 5]),  # a long reply counts
    (964, 14, {}, [0, 0, 0, 0, 3, 3, 3, 6, 6]),      # 14 system tokens + 950 fit exactly
    (964, 15, {}, [0, 0, 0, 2, 2, 4, 4, 6, 6]),      # one more system token: drop at step 3
])
def test_block_boundaries(W, system, replies, want):
    rep = [replies.get(i, 50) for i in range(8)]
    assert block_keep_starts([200] * 9, rep, W, system) == want


def _reference_block(obs, rep, W, sys_t):
    """Brute force: keep the start while the kept context fits in W, else move it to the
    earliest turn whose context fits in W // 2 (or to the current one)."""
    out, start = [], 0
    for m in range(len(obs)):
        def ctx(a, m=m):
            return sys_t + obs[m] + sum(obs[a:m]) + sum(rep[a:m])
        if ctx(start) > W:
            start = next((a for a in range(start, m + 1) if ctx(a) <= W // 2), m)
        out.append(start)
    return out


def test_block_agrees_with_a_brute_force_reference():
    rng = random.Random(12)
    for _ in range(400):
        n = rng.randint(1, 30)
        obs = [rng.randint(1, 400) for _ in range(n)]
        rep = [rng.randint(0, 300) for _ in range(n - 1)]
        W, sys_t = rng.randint(200, 3000), rng.choice((0, rng.randint(0, 150)))
        got = block_keep_starts(obs, rep, W, sys_t)
        assert got == _reference_block(obs, rep, W, sys_t)
        assert got == sorted(got)  # the start never moves back
        slide = [window_keep_start(obs[: m + 1], rep[:m], W, sys_t) for m in range(n)]
        assert all(b >= s for b, s in zip(got, slide, strict=True))  # keeps no more than W


def test_block_cell_payloads_exactly():
    _, model, requests = run_synthetic(get_cell("W-b-0"), cfg=CFG)
    assert [labels(p) for p in model.calls] == [no_reasoning_turns(k, m)
                                                for m, k in enumerate(BLOCK_KEEP)]
    for m, (k, p) in enumerate(zip(BLOCK_KEEP, model.calls, strict=True)):
        assert p == _body(SYSTEM, _turns(k, m))
        _assert_wire_invariants(p)
    assert [r.info["keep_start"] for r in requests] == BLOCK_KEEP
    assert [r.info["block_drop"] for r in requests] == [m in (4, 7) for m in range(9)]
    assert all(r.info["truncation"] == "block" and not r.info["over_W"] for r in requests)


def test_block_keeps_the_prefix_between_drops():
    _, model, _ = run_synthetic(get_cell("W-b-0"), cfg=CFG)
    for m in range(1, 9):
        prev, cur = model.calls[m - 1]["messages"], model.calls[m]["messages"]
        assert (cur[: len(prev) - 1] == prev[:-1]) is (m not in (4, 7)), m
        if m not in (4, 7):  # the previous request, its reply, then the new observation
            assert cur[: len(prev)] == prev


def test_block_counts_replies_and_the_system_prompt_as_w_0_does():
    for W, cs, reps in ((1000, False, {1: 300}), (964, True, 50), (1000, True, 50)):
        _, _, rb = run_synthetic(get_cell("W-b-0"), cfg=CFG, W=W, count_system=cs,
                                 reply_tokens=reps)
        _, _, rw = run_synthetic(CELLS["W-0"], cfg=CFG, W=W, count_system=cs, reply_tokens=reps)
        assert [r.info["system_tokens_counted"] for r in rb] == [
            r.info["system_tokens_counted"] for r in rw]
        assert all(r.info["context_tokens"] <= W for r in rb)


def test_block_on_real_episodes_never_keeps_a_far_fact(small_eps):
    """On real episodes the kept turns are a subset of the sliding window's, so a far fact,
    which the sliding window has dropped by the need step, is dropped under blocks too."""
    for ep in small_eps:
        events = []
        run_episode(ep, get_cell("W-b-0"), CFG, FakeModel(), recorder=events.append)
        slide = []
        run_episode(ep, CELLS["W-0"], CFG, FakeModel(), recorder=slide.append)
        for e, s in zip(events, slide, strict=False):
            texts = [item_text(x) for x in e["payload"]["messages"]]
            stexts = [item_text(x) for x in s["payload"]["messages"]]
            assert set(texts) <= set(stexts) | set(texts[-1:])
            _assert_wire_invariants(e["payload"])


# --- claude-sonnet-5-5 ---------------------------------------------------------------------

@pytest.mark.parametrize("cell_id", ["W-n-0", "W-np-0", "F-0"])
def test_sonnet_bodies_are_haikus_but_for_the_model(cell_id):
    _, mh, _ = run_synthetic(get_cell(cell_id), cfg=CFG)
    _, ms, _ = run_synthetic(get_cell(cell_id), cfg=SONNET_CFG)
    for ph, ps in zip(mh.calls, ms.calls, strict=True):
        assert ph["model"] == HAIKU and ps["model"] == SONNET
        assert {**ps, "model": HAIKU} == ph
        MESSAGES.check_payload(ps, effort="medium", max_tokens=32000)
        assert ps["thinking"] == {"type": "adaptive"} and "fallbacks" not in ps
        assert not any(b.get("type") == "thinking" for x in ps["messages"]
                       for b in x["content"])


def test_sonnet_price_record():
    p = price_for(SONNET)
    assert p is PRICES[SONNET]
    assert (p.input, p.cached, p.output) == (2.00, 0.10, 10.00)
    assert (p.provider, p.api, p.source_date) == ("anthropic", "messages", "2026-11-11")
    assert p.long is None and p.long_threshold is None
    assert dict(p.geo_multipliers) == {"global": 1.0, "us": 1.1}
    assert p.worst_card() == pytest.approx((2.2, 0.11, 11.0))
    with pytest.raises(KeyError):
        price_for("claude-sonnet-5")
    # one window-shaped call: 1,000 plain input, 2,000 cache reads, 10,000 cache writes,
    # 500 output tokens, served in the global geo
    usage = {"input_tokens": 1000, "cache_read_input_tokens": 2000,
             "cache_creation_input_tokens": 10000, "output_tokens": 500,
             "inference_geo": "global"}
    want = (1000 * 2.00 + 2000 * 0.10 + 10000 * 2.00 * CACHE_WRITE_MULTIPLIER
            + 500 * 10.00) / 1e6
    assert cost_usd(SONNET, usage, "standard") == pytest.approx((want, want))
