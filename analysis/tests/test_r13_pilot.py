"""analysis.r13_pilot (R13's check between its pilots and its main runs), on pilot runs whose
transcripts come from the real harness with the fake model: the two registered pairs, each
condition failing on its own, the newest pilot of a pair, the pairs left out or named twice, and
that no outcome reaches the output."""

from __future__ import annotations

import csv
import dataclasses
import gzip
import json
from datetime import UTC, datetime, timedelta

import pytest

from analysis import r13_pilot as rp
from common import costs
from harnesses import registered
from harnesses.cells import get_cell
from harnesses.config import HarnessConfig
from harnesses.fake import FakeModel
from harnesses.runner import run_episode
from persistgym.config import DEFAULT_CONFIG
from persistgym.episode import TaskCell
from persistgym.render import generate

HAIKU = registered.HAIKU_MODEL
PILOT = registered.PILOT_EXPERIMENT
CLOCK = datetime(2026, 11, 20, 7, 0, tzinfo=UTC)
HIGH = {f"{HAIKU} Σ-n-0": [0.010, 0.020], f"{HAIKU} W-nk-0": [0.040, 0.080]}
CFG = HarnessConfig(model=HAIKU, reasoning_effort="medium", service_tier="standard")
OUTCOME_KEYS = ("need_correct", "need_outcome", "success")


@pytest.fixture(scope="module")
def transcripts():
    """Each pair's registered pilot episodes, played by the real session and runner with the
    fake model: (episode records, transcript lines)."""
    out = {}
    for model, cell in registered.R13_PILOTS:
        ids = rp.registered_episodes(model, cell)
        templates = sorted({int(i.split("/")[0].split("-")[1]) for i in ids})
        task_cells = [TaskCell.from_id(t) for t in registered.R13_PILOTS[(model, cell)]]
        records, lines = [], []
        for _, eps in generate("pilot", templates, DEFAULT_CONFIG, task_cells, ("base",)):
            for ep in eps:
                events = []
                run = run_episode(ep, get_cell(cell), CFG, FakeModel(), recorder=events.append)
                records.append({"episode_id": run.episode_id, "exit_reason": run.exit_reason,
                                "need_correct": run.need_correct,
                                "need_outcome": run.need_outcome})
                lines += [{"episode_id": e["episode_id"], "kind": e["kind"], "turn": e["turn"],
                           "info": e["info"], "trace": e["trace"], "payload": e["payload"]}
                          for e in events]
        out[(model, cell)] = (records, lines)
    return out


class Pilots:
    """A results root with a forecast, to which pilot runs are written: meta.json committed, the
    episodes and the transcript under raw (blinded), one costs.csv row each."""

    def __init__(self, path, transcripts):
        self.results = path / "results"
        self.transcripts = transcripts
        f = self.results / "r13_forecast" / "20261116T000000Z"
        f.mkdir(parents=True)
        (f / "forecast.json").write_text(json.dumps({"per_episode_usd": HIGH}), encoding="utf-8")
        self.rows: list[dict] = []
        self.n = 0

    def run(self, model, cell, *, ending="COMPLETED", endings=None, edit=None, per_episode=None,
            returned=None, tier="standard", geos="global:90", rows=1, name=None,
            summary_system=None, drop=0) -> str:
        self.n += 1
        started = CLOCK + timedelta(minutes=5 * self.n)
        run_id = name or f"{started:%Y%m%dT%H%M%SZ}-{get_cell(cell).ascii_id}-{model}"
        folder = self.results / PILOT / run_id
        folder.mkdir(parents=True)
        harness = dataclasses.asdict(CFG)
        if summary_system is not None:
            harness["summary_system_prompt"] = summary_system
        (folder / "meta.json").write_text(json.dumps({
            "experiment": PILOT, "run_id": run_id, "cell_or_config": cell,
            "model_requested": model, "model_returned": returned or [model],
            "exit_reason": ending, "started_utc": started.isoformat(),
            "config": {"harness": harness}}, ensure_ascii=False), encoding="utf-8")
        records, lines = self.transcripts[(model, cell)]
        records = records[: len(records) - drop]
        raw = self.results / "raw" / PILOT / run_id
        raw.mkdir(parents=True)
        (raw / "episodes.jsonl").write_text("".join(
            json.dumps({**r, "exit_reason": (endings or {}).get(r["episode_id"],
                                                                r["exit_reason"])}) + "\n"
            for r in records), encoding="utf-8")
        with gzip.open(raw / "transcript.jsonl.gz", "wt", encoding="utf-8") as fh:
            for i, line in enumerate(lines):
                line = json.loads(json.dumps(line))
                if edit:
                    edit(i, line)
                fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        high = HIGH[f"{model} {cell}"][1]
        spend = (high if per_episode is None else per_episode) * len(records)
        for _ in range(rows):
            self.rows.append({**{c: "" for c in costs.COLUMNS}, "run_id": run_id,
                              "experiment": PILOT, "cost_usd_list": f"{spend:.6f}",
                              "cost_usd_billed_est": f"{spend:.6f}",
                              "service_tier_served": tier,
                              "notes": f"approved_block=9-r13; inference_geos={geos}; pilot"})
        with open(self.results / "costs.csv", "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=costs.COLUMNS)
            w.writeheader()
            w.writerows(self.rows)
        return run_id

    def all(self, over: dict | None = None) -> dict:
        return {(m, c): self.run(m, c, **(over or {}).get((m, c), {}))
                for m, c in registered.R13_PILOTS}

    def check(self, runs=None) -> dict:
        return rp.check(self.results, self.results / "raw", self.results / "costs.csv", runs)


@pytest.fixture
def pilots(tmp_path, transcripts):
    return Pilots(tmp_path, transcripts)


def _run(c, cell):
    return next(r for r in c["runs"] if r["cell"] == cell)


def test_the_registered_pilots():
    assert rp.registered_episodes(HAIKU, "Σ-n-0") == sorted(
        f"pilot-000000/{tc}/base" for tc in registered.HAIKU_TASK_CELLS)
    assert rp.registered_episodes(HAIKU, "W-nk-0") == sorted(
        f"pilot-{t:06d}/{tc}/base" for t in (0, 1) for tc in registered.HAIKU_CONTROL_TASK_CELLS)
    assert rp.FACTOR == 1.10
    assert set(registered.R13_PILOTS) == {(HAIKU, "Σ-n-0"), (HAIKU, "W-nk-0")}


def test_clean_pilots_go(pilots):
    pilots.all()
    c = pilots.check()
    assert c["go"] and not c["pairs_without_a_pilot"] and not c["pairs_checked_twice"]
    s, k = _run(c, "Σ-n-0"), _run(c, "W-nk-0")
    assert all(v is not False for r in (s, k) for v in r["conditions"].values())
    assert s["transcript"]["summary_requests"] > 0
    assert s["transcript"]["summaries"]["episodes_with_a_summary"] == 8
    assert s["conditions"]["pinned_block_info_consistent"] is None
    assert k["transcript"]["pinned"]["with_block"] > 0
    assert k["conditions"]["summaries_seen"] is None
    assert "GO" in rp.summary(c).splitlines()[0]


def test_no_outcome_reaches_the_output(pilots):
    pilots.all()
    text = json.dumps(pilots.check()) + rp.summary(pilots.check())
    for key in OUTCOME_KEYS:
        assert key not in text


@pytest.mark.parametrize("cell, over, condition", [
    ("Σ-n-0", {"ending": "COST_CAP"}, "completed"),
    ("Σ-n-0", {"endings": {"pilot-000000/derived-rec-far/base": "AGENT_ERROR"}},
     "no_api_or_agent_error"),
    ("W-nk-0", {"endings": {"pilot-000001/derived-nonrec-far/base": "API_ERROR"}},
     "no_api_or_agent_error"),
    ("W-nk-0", {"drop": 1}, "registered_episodes"),
    ("Σ-n-0", {"summary_system": "Summarize."}, "instructions_on_every_request"),
    ("Σ-n-0", {"per_episode": 0.0221}, "cost_per_episode_within_limit"),
    ("W-nk-0", {"per_episode": 0.0881}, "cost_per_episode_within_limit"),
    ("W-nk-0", {"returned": ["claude-haiku-5-5-20261101"]}, "model_string"),
    ("Σ-n-0", {"tier": "priority"}, "standard_tier_global_geo"),
    ("W-nk-0", {"geos": "global:80;us:10"}, "standard_tier_global_geo"),
])
def test_each_condition_fails_on_its_own(pilots, cell, over, condition):
    pilots.all({(HAIKU, cell): over})
    c = pilots.check()
    r = _run(c, cell)
    assert not c["go"] and not r["passed"]
    assert r["conditions"][condition] is False
    assert [k for k, v in r["conditions"].items() if v is False] == [condition]
    assert _run(c, "W-nk-0" if cell == "Σ-n-0" else "Σ-n-0")["passed"]


def test_a_cost_at_the_limit_passes(pilots):
    pilots.all({(HAIKU, "W-nk-0"): {"per_episode": 0.088}})
    assert pilots.check()["go"]


def _system_edit(i, line):
    if line["kind"] == "step" and i == 3:
        line["payload"]["system"] += " (edited)"


def test_a_step_without_the_notes_text_fails(pilots):
    pilots.all({(HAIKU, "W-nk-0"): {"edit": _system_edit}})
    r = _run(pilots.check(), "W-nk-0")
    assert r["transcript"]["steps_without_the_notes_text"] == 1
    assert r["conditions"]["instructions_on_every_request"] is False


def _repeat_user(i, line):
    if i == 5:  # an observation sent twice: two user messages, the first no harness message
        msgs = line["payload"]["messages"]
        msgs.insert(len(msgs) - 1, json.loads(json.dumps(msgs[-1])))


@pytest.mark.parametrize("cell", ["Σ-n-0", "W-nk-0"])
def test_a_body_the_request_check_refuses_fails(pilots, cell):
    pilots.all({(HAIKU, cell): {"edit": _repeat_user}})
    r = _run(pilots.check(), cell)
    assert r["transcript"]["bodies_refused_by_the_request_check"] == 1
    assert r["conditions"]["every_body_passes_the_request_check"] is False


@pytest.mark.parametrize("change", [
    lambda info: info.pop("pinned_turns"),
    lambda info: info.update(pinned_index=None),
    lambda info: info.update(keep_start=0),
    lambda info: info.update(pinned_turns=[info["keep_start"]]),
    lambda info: info.update(over_W=True),
])
def test_inconsistent_pinned_info_fails(pilots, transcripts, change):
    # the first step request that sends the block
    _, lines = transcripts[(HAIKU, "W-nk-0")]
    target = next(i for i, x in enumerate(lines)
                  if x["kind"] == "step" and x["info"].get("pinned_index") == 0
                  and x["info"]["keep_start"] > 1)

    def edit(i, line):
        if i == target:
            change(line["info"])

    pilots.all({(HAIKU, "W-nk-0"): {"edit": edit}})
    r = _run(pilots.check(), "W-nk-0")
    assert r["conditions"]["pinned_block_info_consistent"] is False


def test_a_sigma_pilot_without_summaries_fails(pilots):
    def edit(i, line):
        if line["kind"] == "summary":
            line["kind"] = "step_without_summary"

    pilots.all({(HAIKU, "Σ-n-0"): {"edit": edit}})
    r = _run(pilots.check(), "Σ-n-0")
    assert r["conditions"]["summaries_seen"] is False


def test_two_costs_rows_are_a_problem(pilots):
    pilots.all({(HAIKU, "Σ-n-0"): {"rows": 2}})
    r = _run(pilots.check(), "Σ-n-0")
    assert "2 costs.csv rows for the run, not 1" in r["problems"] and not r["passed"]


def test_the_newest_pilot_of_a_pair_is_checked(pilots):
    first = pilots.run(HAIKU, "W-nk-0", ending="COST_CAP")
    pilots.run(HAIKU, "Σ-n-0")
    newest = pilots.run(HAIKU, "W-nk-0")
    c = pilots.check()
    assert c["go"] and _run(c, "W-nk-0")["run_id"] == newest != first


def test_a_pair_without_a_pilot_and_a_pair_named_twice(pilots):
    a = pilots.run(HAIKU, "W-nk-0")
    b = pilots.run(HAIKU, "W-nk-0")
    c = pilots.check([a, b])
    assert c["pairs_without_a_pilot"] == [f"{HAIKU} Σ-n-0"]
    assert c["pairs_checked_twice"] == [f"{HAIKU} W-nk-0"] and not c["go"]


def test_luna_pilots_and_other_pairs_are_not_r13s(pilots):
    pilots.all()
    folder = pilots.results / PILOT / "20261120T090000Z-sigma-n-0-gpt-6-luna"
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({
        "experiment": PILOT, "run_id": folder.name, "cell_or_config": "Σ-n-0",
        "model_requested": "gpt-6-luna", "started_utc": "2026-11-20T09:00:00+00:00"},
        ensure_ascii=False), encoding="utf-8")
    assert set(rp.newest_pilots(pilots.results)) == set(registered.R13_PILOTS)


def test_no_forecast_refuses(tmp_path):
    with pytest.raises(SystemExit, match="no forecast"):
        rp.check(tmp_path / "results", tmp_path / "raw", tmp_path / "costs.csv", None)
