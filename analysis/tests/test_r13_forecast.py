"""analysis.r13_forecast (R13's cost forecast, PREREG §17.13; $0).

* The cache rule on hand-made payloads (reads only where an earlier request's prompt ended,
  the 20-block lookback), and on synthetic replays of W-n-0, W-nk-0 and Σ-n-0 whose every
  request's size, read and write are derived by hand (200-token observations, 50-token
  replies, W = 1000, 60-token summaries, as test_r13_cells).
* The replay on real episodes: the pinned block is written at every request it is in, and
  Σ-n-0's summary request writes its whole prompt; the sums do not depend on the workers.
* R12's schema, the run order and round arms, the stop and block rules and the pilots, on
  made-up per-episode costs, and the calibration on the forecast of two templates of each range
  (the committed forecast replays all of them, so no number here is the forecast's).
* The specs it uses are `registered.R13_SPECS`'.
"""

from __future__ import annotations

import csv
import dataclasses
import json
import math
import shutil
from dataclasses import replace

import pytest

from analysis import r12_forecast as r12
from analysis import r13_forecast as rf
from common import costs
from harnesses import registered
from harnesses.cells import CELLS, R13_CELLS, R13_PINNED_TOKENS
from harnesses.config import (
    ARC_SUMMARY_BRIDGE_TEMPLATE,
    ARC_SUMMARY_REQUEST_PROMPT,
    ARC_SUMMARY_SYSTEM_PROMPT,
)
from harnesses.fake import padded_text
from harnesses.paid_transport import PaidTransport
from harnesses.session import HarnessSession
from harnesses.tests.conftest import reply_text, run_synthetic, summary_text
from harnesses.tests.test_messages_wire import CFG, NOTES_SYSTEM, WINDOW_KEEP
from harnesses.tests.test_r13_cells import pinned_text
from harnesses.wire import MESSAGES
from persistgym import tokens
from persistgym.config import DEFAULT_CONFIG
from persistgym.episode import ALL_CELLS
from persistgym.render import generate

ROOT = rf.REPO_ROOT
HAIKU = registered.HAIKU_MODEL
SIGMA, PINNED = registered.R13_SIGMA_EXPERIMENT, registered.R13_PINNED_EXPERIMENT
R12_FORECAST = ROOT / "results" / "r12_forecast" / "20261111T060105Z"
NR_FAR = registered.HAIKU_CONTROL_TASK_CELLS


def _payload(system: str, *texts: str) -> dict:
    """A Messages body's system and messages: user and assistant in turn, from a user."""
    return {"system": system,
            "messages": [{"role": "assistant" if i % 2 else "user",
                          "content": [{"type": "text", "text": t}]}
                         for i, t in enumerate(texts)]}


def _episode(template: int, task_cell: str):
    (_, eps), = generate("main", [template], DEFAULT_CONFIG, ALL_CELLS, ("base",))
    return next(e for e in eps if e.cell.id == task_cell)


@pytest.fixture(scope="module")
def small():
    """The forecast with every replay on the first 2 templates of its range: (the forecast,
    the replay's sums)."""
    real = rf.replay
    seen: dict = {}

    def two(plans, workers=1):
        sims = real([replace(p, templates=(p.templates[0], p.templates[0] + 2)) for p in plans])
        seen.update(sims)
        return sims

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(rf, "replay", two)
        out = rf.forecast(ROOT)
    return out, seen


# --- the cache rule ------------------------------------------------------------------------

def test_a_request_reads_only_where_an_earlier_prompt_ended():
    sys_, other = padded_text("SYS", 100), padded_text("SUMMARY SYS", 40)
    u = [padded_text(f"OBS[{i}]", 200) for i in range(4)]
    a = [padded_text(f"REPLY[{i}]", 50) for i in range(4)]
    led = rf.CacheLedger()
    assert led.add("step", _payload(sys_, u[0])) == {"size": 300, "read": 0, "write": 300}
    # the previous prompt is this one's prefix: read it, write the reply and observation
    assert led.add("step", _payload(sys_, u[0], a[0], u[1])) == {
        "size": 550, "read": 300, "write": 250}
    # the first turn dropped: only the system prompt is shared, and no entry ends there
    assert led.add("step", _payload(sys_, u[1], a[1], u[2])) == {
        "size": 550, "read": 0, "write": 550}
    # another system prompt (a summary request) shares nothing
    summary = _payload(other, u[1], a[1], u[2], a[2])
    assert led.add("summary", summary) == {"size": 540, "read": 0, "write": 540}
    # the same prompt again (a retried summary) reads all of it
    assert led.add("summary", summary) == {"size": 540, "read": 540, "write": 0}
    # an entry older than the previous request still counts
    assert led.add("step", _payload(sys_, u[1], a[1], u[2], a[2], u[3])) == {
        "size": 800, "read": 550, "write": 250}
    assert {k: led.totals[k] for k in ("requests", "step_requests", "summary_requests",
                                        "input", "read", "write", "max_prompt", "min_prompt")} == {
        "requests": 6, "step_requests": 4, "summary_requests": 2, "input": 3280,
        "read": 1390, "write": 1890, "max_prompt": 800, "min_prompt": 300}


@pytest.mark.parametrize(("n_messages", "read"), [(20, True), (21, False)])
def test_the_lookback_is_20_blocks(n_messages, read):
    # the earlier entry ends at its first message: 19 blocks back from the 20th message (the
    # breakpoint counts as the first of the 20 positions checked), 20 back from the 21st
    sys_ = padded_text("SYS", 100)
    texts = [padded_text(f"M[{i}]", 10) for i in range(n_messages)]
    led = rf.CacheLedger()
    led.add("step", _payload(sys_, texts[0]))
    assert led.add("step", _payload(sys_, *texts))["read"] == (110 if read else 0)
    assert rf.LOOKBACK_BLOCKS == 20


def _ledger_rows(cell):
    _, _, requests = run_synthetic(cell, cfg=CFG)
    led = rf.CacheLedger()
    return [(r.kind, led.add(r.kind, r.payload, r.info)) for r in requests], led


def test_w_n_0_reads_until_its_first_drop_and_then_writes_every_prompt():
    rows_, _ = _ledger_rows(CELLS["W-n-0"])
    s = tokens.count(NOTES_SYSTEM)
    want = [(s + 200, 0), (s + 450, s + 200), (s + 700, s + 450), (s + 950, s + 700)]
    want += [(s + 950, 0)] * 5  # the window drops a turn at every step from step 4 on
    assert [k for k, _ in rows_] == ["step"] * 9
    assert [(r["size"], r["read"]) for _, r in rows_] == want
    assert all(r["write"] == r["size"] - r["read"] for _, r in rows_)
    assert WINDOW_KEEP == [0, 0, 0, 0, 1, 2, 3, 4, 5]


def test_w_nk_0_adds_its_block_and_writes_it_at_every_request_it_is_in():
    rows_, led = _ledger_rows(R13_CELLS["W-nk-0"])
    s = tokens.count(NOTES_SYSTEM)
    blocks = [tokens.count(pinned_text([reply_text(t) for t in range(start)]))
              for start in WINDOW_KEEP[4:]]  # every dropped 50-token reply fits the cap
    want = [(s + 200, 0), (s + 450, s + 200), (s + 700, s + 450), (s + 950, s + 700)]
    want += [(s + 950 + b, 0) for b in blocks]
    assert [(r["size"], r["read"]) for _, r in rows_] == want
    assert led.totals["pinned"] == sum(blocks)
    _, base = _ledger_rows(CELLS["W-n-0"])
    assert led.totals["read"] == base.totals["read"]
    assert led.totals["write"] - base.totals["write"] == sum(blocks)


def test_sigma_n_0_writes_each_summary_request_and_the_step_after_it_whole():
    rows_, _ = _ledger_rows(CELLS["Σ-n-0"])
    s, a = tokens.count(NOTES_SYSTEM), tokens.count(ARC_SUMMARY_SYSTEM_PROMPT)
    q = tokens.count(ARC_SUMMARY_REQUEST_PROMPT)
    b1, b2 = (tokens.count(ARC_SUMMARY_BRIDGE_TEMPLATE.format(summary=summary_text(j)))
              for j in (1, 2))
    want = [("step", s + 200, 0), ("step", s + 450, s + 200), ("step", s + 700, s + 450),
            ("step", s + 950, s + 700),
            ("summary", a + 4 * 250 + q, 0),           # turns 0-3, ARC's system prompt
            ("step", s + b1 + 200, 0),                 # the bridge, then the new observation
            ("step", s + b1 + 450, s + b1 + 200), ("step", s + b1 + 700, s + b1 + 450),
            ("summary", a + b1 + 3 * 250 + q, 0),      # the bridge and turns 4-6
            ("step", s + b2 + 200, 0), ("step", s + b2 + 450, s + b2 + 200)]
    assert [(k, r["size"], r["read"]) for k, r in rows_] == want
    assert b1 == 87


# --- the replay on real episodes ----------------------------------------------------------

def test_the_pinned_block_is_written_at_every_request_it_is_in_on_a_real_episode():
    ep = _episode(200, NR_FAR[0])
    n = rf.replay_episode(ep, "W-n-0", 57)
    k = rf.replay_episode(ep, "W-nk-0", 57)
    assert k["requests"] == n["requests"] == ep.n_steps
    assert k["read"] == n["read"] > 0
    assert k["write"] - n["write"] == k["pinned"] > 0 and n["pinned"] == 0
    high = rf.replay_episode(ep, "W-nk-0", rf.PINNED_HIGH_REPLY_TOKENS)
    assert high["pinned"] > k["pinned"]


def test_a_real_sigma_episode_summarizes_once_and_steps_as_f_0():
    ep = _episode(0, "observed-nonrec-far")
    s = rf.replay_episode(ep, "Σ-n-0", 29, 143)
    f = rf.replay_episode(ep, "F-0", 29)
    assert (s["summary_requests"], s["compactions"]) == (1, 1)
    assert s["step_requests"] == f["step_requests"] == f["requests"] == ep.n_steps
    assert s["read"] + s["write"] == s["input"] < f["input"]
    assert s["write"] > f["write"]  # the summary request and the step after it are written


def test_the_replay_model_pads_replies_and_summaries_and_reports_no_usage():
    m = rf.ReplayModel(57, 143)
    assert m.paid is False
    session = HarnessSession(CELLS["Σ-n-0"], "Sys.", CFG, W_tokens=1000, count_system=False)
    session.observe(padded_text("OBS[0]", 200))
    req = session.next_request()
    resp = m.send(req.payload)
    assert tokens.count(MESSAGES.text(resp)) == 57
    assert MESSAGES.usage(resp)["input_tokens"] == MESSAGES.usage(resp)["output_tokens"] == 0
    summary = _payload("Sys.", "OBS", "REPLY", ARC_SUMMARY_REQUEST_PROMPT)
    summary.update({k: v for k, v in req.payload.items() if k not in ("system", "messages")})
    assert tokens.count(MESSAGES.text(m.send(summary))) == 143


def test_the_replay_does_not_depend_on_the_workers():
    plan = rf.Plan("W-n-0", "W-n-0", (200, 202), NR_FAR, {c: 57 for c in NR_FAR})
    one = rf.replay([plan], 1)
    assert rf.replay([plan], 2) == one
    assert {c: one["W-n-0"][c]["episodes"] for c in NR_FAR} == {c: 2 for c in NR_FAR}


# --- runs, pilots, stops and the block ----------------------------------------------------

def test_the_run_order_and_the_round_arms():
    sig = [(SIGMA, "Σ-n-0", (a, a + 50)) for a in (0, 50, 100, 150)]
    rounds = [("W-nk-0", "W-n-0"), ("W-n-0", "W-nk-0"), ("W-nk-0", "W-n-0"),
              ("W-n-0", "W-nk-0")]
    pin = [(PINNED, cell, (200 + 25 * k, 225 + 25 * k)) for k, arms in enumerate(rounds)
           for cell in arms]
    assert rf.run_order() == sig + pin
    assert [registered.r13_round_arms(k) for k in range(4)] == rounds


def test_the_pilots_play_as_the_driver_plays_them():
    assert [(m, c) for m, c in registered.R13_PILOTS] == [(HAIKU, "Σ-n-0"), (HAIKU, "W-nk-0")]
    assert rf.pilot_episodes("Σ-n-0") == 8   # pilot template 0 on all 8 task cells
    assert rf.pilot_episodes("W-nk-0") == 4  # pilot templates 0-1 on the 2 far cells


def test_the_stops_the_block_and_the_pilots_on_made_up_costs():
    per = {(HAIKU, "Σ-n-0"): (0.014, 0.016543), (HAIKU, "W-nk-0"): (0.044, 0.048888),
           (HAIKU, "W-n-0"): (0.043604, 0.043604)}
    s = rf.schedule(per, spent=500.0, one_send=0.1386)
    stops = {"Σ-n-0": 8.28,    # 400 x 0.016543 x 1.25 = 8.2715, up to the next cent
             "W-nk-0": 3.06,   # 50 x 0.048888 x 1.25 = 3.0555
             "W-n-0": 2.73}    # 50 x 0.043604 x 1.25 = 2.72525
    assert [(r["cell"], r["episodes"], r["planned_usd"]) for r in s["runs"]] == [
        (r[1], 400 if r[0] == SIGMA else 50, stops[r[1]]) for r in rf.run_order()]
    assert all(r["high_usd"] == pytest.approx(r["episodes"] * per[(HAIKU, r["cell"])][1])
               and r["most_one_send_usd"] == 0.1386 for r in s["runs"])
    # pilots: 8 x 0.016543 x 1.25 = 0.165 -> 0.17, 4 x 0.048888 x 1.25 = 0.244 -> 0.25, + 0.5
    assert [(p["cell"], p["episodes"], p["planned_usd"]) for p in s["pilots"]] == [
        ("Σ-n-0", 8, pytest.approx(0.67)), ("W-nk-0", 4, pytest.approx(0.75))]
    t = s["totals"]
    assert t["high"] == pytest.approx(4 * 6.6172 + 4 * 2.4444 + 4 * 2.1802)  # 44.9672
    assert t["stops"] == pytest.approx(4 * (8.28 + 3.06 + 2.73))
    assert t["pilots"] == pytest.approx(1.42)
    assert t["block_max_usd"] == 51  # ceil(44.9672 x 1.10 + 1.42) = ceil(50.884)
    assert (s["phase_1a_spent_usd"], s["phase_1a_after_block_usd"]) == (500.0, 551.0)


def test_phase_1a_spend_is_read_as_r12_reads_it(tmp_path):
    assert rf.phase_1a_spent(ROOT) == pytest.approx(sum(
        float(r["cost_usd_billed_est"] or r["cost_usd_list"] or 0)
        for r in r12._ledger(ROOT) if r12._phase(r["experiment"]) == "1a"))
    (tmp_path / "results").mkdir()
    blank = {c: "" for c in costs.COLUMNS}
    with open(tmp_path / "results" / "costs.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=costs.COLUMNS)
        w.writeheader()
        w.writerow({**blank, "experiment": SIGMA, "cost_usd_list": "2.0",
                    "cost_usd_billed_est": "1.5"})
        w.writerow({**blank, "experiment": PINNED, "cost_usd_list": "0.25"})  # no billed est.
        w.writerow({**blank, "experiment": "arc_path", "cost_usd_billed_est": "9.0"})  # 1b
    assert rf.phase_1a_spent(tmp_path) == pytest.approx(1.75)


def test_the_margins_and_one_send_are_r12s():
    assert (rf.STOP_MARGIN, rf.BLOCK_MARGIN) == (r12.STOP_MARGIN, r12.BLOCK_MARGIN) == (1.25, 1.10)
    fields = {f.name: f.default for f in dataclasses.fields(PaidTransport)}
    assert rf.MAX_ATTEMPTS == fields["max_attempts"] == 6
    # cache write $0.125, output $0.50 per million; 6 attempts; the US geo's 1.1
    assert r12.most_one_send(HAIKU, rf.MAX_PROMPT_TOKENS) == pytest.approx(
        (40_000 * 0.125 + 32_000 * 0.50) / 1e6 * 6 * 1.1)


def test_check_prompts_refuses_a_prompt_outside_the_prices():
    ok = {"max_prompt_billed": 30_000, "min_prompt": 1_600}
    rf.check_prompts({"by_task_cell": {"c": {"low": ok, "high": ok}}})
    with pytest.raises(SystemExit, match="passes 40000"):
        rf.check_prompts({"by_task_cell": {"c": {"low": ok,
                                                 "high": {**ok, "max_prompt_billed": 40_001}}}})
    with pytest.raises(SystemExit, match="below 512"):
        rf.check_prompts({"by_task_cell": {"c": {"low": {**ok, "min_prompt": 511},
                                                 "high": ok}}})


# --- the forecast on two templates of each range --------------------------------------------

def test_the_forecast_has_r12s_schema(small):
    out, _ = small
    old = json.loads((R12_FORECAST / "forecast.json").read_text(encoding="utf-8"))
    assert list(out) == [k for k in old if k != "block_window"]  # R12's own replay detail
    assert out["prereg"] == registered.R13_REF
    assert all(set(r) == set(old["runs"][0]) for r in out["runs"])
    assert all(set(p) == set(old["pilots"][0]) for p in out["pilots"])
    assert set(out["totals"]) == set(old["totals"])
    assert set(out["profiles"]["W-n-0"]) == set(old["profiles"]["W-n-0"])
    assert set(out["per_episode_usd"]) == {f"{HAIKU} {c}" for c in ("Σ-n-0", "W-nk-0", "W-n-0")}
    assert [(r["experiment"], r["cell"], tuple(r["templates"])) for r in out["runs"]] == \
        rf.run_order()
    for r in out["runs"]:
        lo, hi = out["per_episode_usd"][f"{r['model']} {r['cell']}"]
        assert lo <= hi and r["planned_usd"] == rf.stop_usd(r["episodes"], hi)
    t = out["totals"]
    assert t["block_max_usd"] == math.ceil(t["high"] * rf.BLOCK_MARGIN + t["pilots"])
    assert out["phase_1a_after_block_usd"] == pytest.approx(
        out["phase_1a_spent_usd"] + t["block_max_usd"])


def test_the_calibration_scales_each_task_cell_to_its_measured_input(small):
    out, sims = small
    sig, pin = out["profiles"]["Σ-n-0"]["by_task_cell"], out["profiles"]["W-nk-0"]["by_task_cell"]
    for c in registered.HAIKU_TASK_CELLS:
        measured = rf.profile(rf.rows(ROOT, "R8 F-0", (c,), (0, 200)))["input_tokens"]
        assert sig[c]["scale"] == pytest.approx(
            measured / rf.per_episode(sims["F-0"][c])["input"])
        assert 1.2 < sig[c]["scale"] < 1.7
    for c in NR_FAR:
        measured = rf.profile(rf.rows(ROOT, "R12 W-n-0", (c,), (200, 300)))
        assert pin[c]["scale"] == pytest.approx(
            measured["input_tokens"] / rf.per_episode(sims["W-n-0"][c])["input"])
        assert pin[c]["w_n_0_usd"] == pytest.approx(r12.price(measured, HAIKU))
        # the block is only ever written in the low case: W-nk-0 reads what W-n-0 reads
        assert pin[c]["low"]["added_read"] == 0 < pin[c]["low"]["added_write"]


def test_w_n_0s_forecast_is_r12_experiment_1s_measured_cost(small):
    out, _ = small
    p = out["profiles"]["W-n-0"]
    assert p["episodes"] == 200  # 100 templates x the 2 far cells, every one finished
    lo, hi = out["per_episode_usd"][f"{HAIKU} W-n-0"]
    assert lo == hi == pytest.approx(r12.price(p, HAIKU))


def test_main_writes_the_forecast_and_its_meta(small, tmp_path, monkeypatch):
    monkeypatch.setattr(rf, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(rf, "forecast", lambda root, workers=1: small[0])
    assert rf.main([]) == 0
    (out,) = (tmp_path / "results" / "r13_forecast").iterdir()
    assert sorted(p.name for p in out.iterdir()) == ["forecast.json", "meta.json"]
    assert json.loads((out / "forecast.json").read_text(encoding="utf-8")) == json.loads(
        json.dumps(small[0]))
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    old = json.loads((R12_FORECAST / "meta.json").read_text(encoding="utf-8"))
    assert set(meta) == set(old)
    assert (meta["experiment"], meta["cell_or_config"], meta["paid_calls"],
            meta["cost_usd"]) == ("r13_forecast", "R13", 0, 0.0)
    assert meta["config"]["sources"] == {k: list(v[1]) for k, v in rf.SOURCES.items()}


def test_main_with_no_write_writes_nothing(small, tmp_path, monkeypatch):
    monkeypatch.setattr(rf, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(rf, "forecast", lambda root, workers=1: small[0])
    assert rf.main(["--no-write"]) == 0
    assert not (tmp_path / "results").exists()


# --- the records and the specs ---------------------------------------------------------------

def test_lunas_summary_length_is_its_bridge_less_the_template():
    assert rf.BRIDGE_TOKENS == 27
    rows_ = [json.loads(line) for line in (
        ROOT / "results" / "persistgym" / "20261010T100804Z-sigma-n-0-gpt-6-luna"
        / "episodes.jsonl").read_text(encoding="utf-8").splitlines()]
    bridges = [c["bridge_tokens"] for r in rows_ if r["task_cell"] == "derived-nonrec-far"
               for c in r["compactions"]]
    assert len(bridges) == 200
    assert rf.luna_summary_tokens(ROOT, "derived-nonrec-far") == pytest.approx(
        sum(bridges) / 200 - 27)


def test_a_record_from_another_generator_config_refuses(tmp_path):
    experiment, runs = rf.SOURCES["R12 W-n-0"]
    for run in runs:
        dst = tmp_path / "results" / experiment / run
        dst.mkdir(parents=True)
        shutil.copy(ROOT / "results" / experiment / run / "episodes.jsonl", dst)
    path = tmp_path / "results" / experiment / runs[0] / "episodes.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["generator_config_hash"] = "0" * 64
    path.write_text("\n".join([json.dumps(first), *lines[1:]]) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="another generator config"):
        rf.rows(tmp_path, "R12 W-n-0", NR_FAR, (200, 300))


def test_the_specs_are_registered_r13s():
    assert rf.SPECS is registered.R13_SPECS
    assert (rf.SIGMA, rf.PINNED) == registered.R13_EXPERIMENTS
    assert rf.ALL8 == registered.HAIKU_TASK_CELLS == registered.R13_SPECS[SIGMA]["task_cells"]
    assert rf.TWO == registered.HAIKU_CONTROL_TASK_CELLS == registered.R13_SPECS[PINNED][
        "task_cells"]
    assert {c for spec in registered.R13_SPECS.values() for c in spec["cells"]} == {
        "Σ-n-0", "W-nk-0", "W-n-0"}
    assert all(spec["model"] == HAIKU for spec in registered.R13_SPECS.values())
    assert rf.CFG.model == HAIKU and rf.CFG.reasoning_effort == "medium"
    plans, _ = rf.plans(ROOT)
    for p in plans:
        exp = SIGMA if p.templates == registered.R13_SPECS[SIGMA]["templates"] else PINNED
        assert p.templates == registered.R13_SPECS[exp]["templates"]
        assert p.task_cells == registered.R13_SPECS[exp]["task_cells"]
    assert {p.cell for p in plans if p.templates == (200, 300)} == {"W-n-0", "W-nk-0"}
    assert {costs.EXPERIMENT_PHASE[e] for e in registered.R13_EXPERIMENTS} == {"1a"}
    assert rf.PINNED_HIGH_REPLY_TOKENS * 4 == R13_PINNED_TOKENS  # four fill the cap
