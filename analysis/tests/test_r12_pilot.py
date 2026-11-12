"""analysis.r12_pilot (R12's check between its pilots and its main runs), on synthetic pilot runs:
the six registered pairs, each condition failing on its own, the newest pilot of a pair, the
pairs left out or named twice, and that no outcome reaches the output."""

from __future__ import annotations

import csv
import gzip
import json
import shutil
from datetime import UTC, datetime, timedelta

import pytest

from analysis import r12_pilot as rp
from common import costs
from harnesses import registered
from harnesses.cells import get_cell

ROOT = rp.REPO_ROOT
FORECAST = "results/r12_forecast/20261111T060105Z"
PILOT = registered.PILOT_EXPERIMENT
CLOCK = datetime(2026, 11, 12, 7, 0, tzinfo=UTC)
BLOCK_STARTS = [0, 0, 0, 2, 2, 4]
"""The kept start of a made-up W-b-0 pilot episode's six step requests."""


class Pilots:
    """A results root with the committed forecast, to which pilot runs are written: meta.json
    committed, the episodes and the transcript under raw (blinded), one costs.csv row each."""

    def __init__(self, path):
        self.path = path
        self.results = path / "results"
        shutil.copytree(ROOT / FORECAST, path / FORECAST)
        self.rows: list[dict] = []
        self.n = 0

    def run(self, model, cell, *, ending="COMPLETED", episodes=None, endings=None, system=None,
            block=None, per_episode=None, returned=None, tier="standard", geos="global:90",
            rows=1, name=None) -> str:
        self.n += 1
        started = CLOCK + timedelta(minutes=5 * self.n)
        run_id = name or f"{started:%Y%m%dT%H%M%SZ}-{cell}-{model}"
        folder = self.results / PILOT / run_id
        folder.mkdir(parents=True)
        (folder / "meta.json").write_text(json.dumps({
            "experiment": PILOT, "run_id": run_id, "cell_or_config": cell,
            "model_requested": model, "model_returned": returned or [model],
            "exit_reason": ending, "started_utc": started.isoformat(),
            "config": {"harness": {"notes_separator": "\n"}}}), encoding="utf-8")
        if episodes is None:   # a pair off R12's plays R10's pilot episodes
            episodes = (rp.registered_episodes(model, cell)
                        if (model, cell) in registered.R12_PILOTS else
                        [f"pilot-{t:06d}/{tc}/base" for t in (0, 1)
                         for tc in registered.HAIKU_CONTROL_TASK_CELLS])
        ids = episodes
        raw = self.results / "raw" / PILOT / run_id
        raw.mkdir(parents=True)
        (raw / "episodes.jsonl").write_text("".join(
            json.dumps({"episode_id": e, "exit_reason": (endings or {}).get(e, "DONE"),
                        "need_correct": True, "need_outcome": "correct"}) + "\n" for e in ids),
            encoding="utf-8")
        spec = get_cell(cell)
        default_system = "Sys." + ("\n" + spec.notes_instruction if spec.notes else "")
        with gzip.open(raw / "transcript.jsonl.gz", "wt", encoding="utf-8") as fh:
            for e in ids:
                for i, keep in enumerate(BLOCK_STARTS):
                    info = {"keep_start": keep}
                    if cell == rp.BLOCK_CELL:
                        info.update(truncation="block", over_W=False,
                                    block_drop=i > 0 and keep != BLOCK_STARTS[i - 1])
                        if block:
                            block(e, i, info)
                    fh.write(json.dumps({"episode_id": e, "kind": "step", "turn": i,
                                         "info": info,
                                         "payload": {"system": system or default_system}}) + "\n")
        high = json.loads((self.path / FORECAST / "forecast.json").read_text(
            encoding="utf-8"))["per_episode_usd"][f"{model} {cell}"][1]
        spend = (high if per_episode is None else per_episode) * len(ids)
        for _ in range(rows):
            self.rows.append({**{c: "" for c in costs.COLUMNS}, "run_id": run_id,
                              "experiment": PILOT, "cost_usd_list": f"{spend:.6f}",
                              "cost_usd_billed_est": f"{spend:.6f}",
                              "service_tier_served": tier,
                              "notes": f"approved_block=8-r12; inference_geos={geos}; pilot"})
        self._write_costs()
        return run_id

    def _write_costs(self):
        with open(self.results / "costs.csv", "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=costs.COLUMNS)
            w.writeheader()
            w.writerows(self.rows)

    def all(self, over: dict | None = None) -> dict:
        return {(m, c): self.run(m, c, **(over or {}).get((m, c), {}))
                for m, c in registered.R12_PILOTS}

    def check(self, runs=None) -> dict:
        return rp.check(self.results, self.results / "raw", self.results / "costs.csv", runs)


@pytest.fixture
def pilots(tmp_path):
    return Pilots(tmp_path)


def _run(c, cell, model=registered.HAIKU_MODEL):
    return next(r for r in c["runs"] if (r["model"], r["cell"]) == (model, cell))


def test_the_registered_pilots():
    assert rp.registered_episodes(registered.HAIKU_MODEL, "W-nd-0") == sorted(
        f"pilot-{t:06d}/{tc}/base" for t in (0, 1) for tc in registered.HAIKU_CONTROL_TASK_CELLS)
    assert rp.registered_episodes(registered.HAIKU_MODEL, "W-b-0") == sorted(
        f"pilot-000000/{tc}/base" for tc in registered.HAIKU_TASK_CELLS)
    assert len(rp.registered_episodes(registered.SONNET_MODEL, "F-0")) == 4
    assert rp.FACTOR == 1.10


def test_six_passing_pilots_are_go(pilots):
    pilots.all()
    c = pilots.check()
    assert c["go"] and len(c["runs"]) == 6 and c["pairs_without_a_pilot"] == []
    assert c["forecast"] == FORECAST
    nd = _run(c, "W-nd-0")
    assert (nd["requests"], nd["requests_without_the_notes_text"]) == (24, 0)
    assert nd["conditions"]["block_rule_info_consistent"] is None
    b = _run(c, "W-b-0")
    assert b["block_rule"] == {"step_requests": 48, "inconsistent": 0, "over_W": 0, "drops": 16}
    assert b["conditions"]["notes_text_on_every_request"] is None and b["requests"] is None
    f0 = _run(c, "F-0", registered.SONNET_MODEL)
    assert f0["cost_per_episode_usd"] == pytest.approx(f0["high_forecast_per_episode_usd"],
                                                       rel=1e-5)
    assert f0["cost_limit_usd"] == pytest.approx(1.10 * f0["high_forecast_per_episode_usd"])
    assert "GO" in rp.summary(c).splitlines()[0]


def test_no_outcome_reaches_the_output(pilots):
    pilots.all()
    text = json.dumps(pilots.check())
    assert "need_correct" not in text and "need_outcome" not in text and "correct" not in text


@pytest.mark.parametrize("over, failed", [
    ({"ending": "SPEND_RESERVATION"}, "completed"),
    ({"ending": "ERROR:RequestCheckFailed"}, "completed"),
    ({"endings": {"pilot-000001/derived-nonrec-far/base": "API_ERROR"}}, "no_api_error"),
    ({"episodes": ["pilot-000000/observed-nonrec-far/base"]}, "registered_episodes"),
    ({"episodes": [f"pilot-{t:06d}/{tc}/base" for t in (0, 1, 2)
                   for tc in registered.HAIKU_CONTROL_TASK_CELLS]}, "registered_episodes"),
    ({"system": "Sys.\nInclude any context you want to carry forward."},
     "notes_text_on_every_request"),
    ({"per_episode": 1.11 * 0.05456290400000001}, "cost_per_episode_within_limit"),
    ({"returned": ["claude-haiku-5-5", "claude-haiku-5-5-other"]}, "model_string"),
    ({"tier": "priority"}, "standard_tier_global_geo"),
    ({"geos": "global:80;us:10"}, "standard_tier_global_geo"),
])
def test_each_condition_stops_on_its_own(pilots, over, failed):
    pilots.all({(registered.HAIKU_MODEL, "W-nd-0"): over})
    c = pilots.check()
    r = _run(c, "W-nd-0")
    assert not c["go"] and not r["passed"]
    assert [k for k, v in r["conditions"].items() if v is False] == [failed]
    assert all(x["passed"] for x in c["runs"] if x is not r)
    assert f"{failed} NO" in rp.summary(c)


def test_a_cost_at_the_limit_passes(pilots):
    pilots.all({(registered.HAIKU_MODEL, "W-nd-0"): {"per_episode": 1.0999 * 0.05456290400000001}})
    assert pilots.check()["go"]


@pytest.mark.parametrize("change", [
    lambda e, i, info: info.update(block_drop=i == 4),            # a drop flagged where none was
    lambda e, i, info: info.update(block_drop=False),              # drops not flagged
    lambda e, i, info: info.update(keep_start=1) if i == 5 else None,  # the start moved back
    lambda e, i, info: info.update(truncation=None) if i == 2 else None,
    lambda e, i, info: info.update(over_W=True) if i == 1 else None,
])
def test_inconsistent_block_info_stops(pilots, change):
    pilots.all({(registered.HAIKU_MODEL, "W-b-0"): {"block": change}})
    c = pilots.check()
    r = _run(c, "W-b-0")
    assert not c["go"]
    assert [k for k, v in r["conditions"].items() if v is False] == ["block_rule_info_consistent"]


def test_a_costs_row_missing_or_twice_is_a_problem(pilots):
    pilots.all({(registered.SONNET_MODEL, "W-n-0"): {"rows": 2}})
    c = pilots.check()
    r = _run(c, "W-n-0", registered.SONNET_MODEL)
    assert not c["go"] and r["problems"] == ["2 costs.csv rows for the run, not 1"]


def test_the_newest_pilot_of_each_pair_is_checked(pilots):
    old = pilots.run(registered.HAIKU_MODEL, "W-nx-0", ending="ERROR:KeyboardInterrupt")
    pilots.run(registered.HAIKU_MODEL, "W-np-0")   # R10's Haiku W-np-0 pilot: not R12's
    ids = pilots.all()
    c = pilots.check()
    assert c["go"] and old not in {r["run_id"] for r in c["runs"]}
    assert _run(c, "W-nx-0")["run_id"] == ids[(registered.HAIKU_MODEL, "W-nx-0")]
    assert len(c["runs"]) == 6


def test_a_pair_without_a_pilot_stops(pilots):
    for m, cell in list(registered.R12_PILOTS)[:-1]:
        pilots.run(m, cell)
    c = pilots.check()
    assert not c["go"] and c["pairs_without_a_pilot"] == [f"{registered.SONNET_MODEL} F-0"]
    assert "no pilot of claude-sonnet-5-5 F-0" in rp.summary(c)


def test_named_runs_are_checked_and_a_pair_named_twice_stops(pilots):
    ids = pilots.all()
    again = pilots.run(registered.HAIKU_MODEL, "W-b-0")
    named = list(ids.values())
    assert pilots.check(named)["go"]
    c = pilots.check([*named, again])
    assert not c["go"] and c["pairs_checked_twice"] == [f"{registered.HAIKU_MODEL} W-b-0"]


def test_a_run_off_r12s_pairs_is_a_problem(pilots):
    pilots.all()
    other = pilots.run(registered.HAIKU_MODEL, "W-np-0")
    c = pilots.check([other])
    (r,) = c["runs"]
    assert not r["passed"] and any("not one of R12's pilot pairs" in p for p in r["problems"])
    assert r["conditions"]["registered_episodes"] is False


def test_main_writes_the_check_and_its_meta(pilots):
    pilots.all()
    assert rp.main(["--results-root", str(pilots.path)]) == 0
    (out,) = (pilots.results / "r12_pilot").iterdir()
    assert {p.name for p in out.iterdir()} == set(rp.OUTPUTS)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["paid_calls"] == 0 and meta["config"]["go"] is True
    assert json.loads((out / "check.json").read_text(encoding="utf-8"))["go"] is True


def test_main_returns_1_on_stop_and_no_write_writes_nothing(pilots):
    pilots.all({(registered.HAIKU_MODEL, "W-b-0"): {"ending": "COST_CAP"}})
    assert rp.main(["--results-root", str(pilots.path), "--no-write"]) == 1
    assert not (pilots.results / "r12_pilot").exists()


def test_no_forecast_refuses(tmp_path):
    (tmp_path / "results").mkdir()
    with pytest.raises(SystemExit, match="no forecast"):
        rp.check(tmp_path / "results", tmp_path / "raw", tmp_path / "costs.csv", [])
