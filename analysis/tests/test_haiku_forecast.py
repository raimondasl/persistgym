"""R8's size rule (analysis/haiku_forecast.py; PREREG §17.8): synthetic block-4-haiku ledgers
through each branch of the rule and its boundary at exactly 0.85 R, the rows it ignores and
refuses, its outputs, and the luna figures its docstring cites, re-derived from
results/costs.csv."""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
from decimal import Decimal as D

import pytest

from analysis import haiku_forecast as f
from common import approval, costs
from harnesses import registered

MODEL = registered.HAIKU_MODEL
TAG = ("approved_block=4-haiku; context_mismatches=n/a; effort_mismatches=n/a; "
       "git_dirty=False; max_prompt_tokens=50000; calls_over_100000=0")
RUNS = {
    # key: experiment, cell, variant, episodes (R8: the pilots, then the validity runs)
    "F-0": (f.PILOT, "F-0", "base", 8),
    "W-0": (f.PILOT, "W-0", "base", 8),
    "W-n-0": (f.PILOT, "W-n-0", "base", 8),
    "single-turn": (f.PILOT, "single-turn", "single_turn", 8),
    "restated": (f.VALIDITY, "F-0", "restated", 160),
    "withheld": (f.VALIDITY, "F-0", "withheld", 160),
}
PILOTS = {"F-0": "0.1", "W-0": "0.2", "W-n-0": "0.2", "single-turn": "0.04"}
REASONING = "987654321"
"""Every synthetic row's reasoning_tokens: no output may hold it (pilot blinding, §11)."""


def _row(run_id: str, experiment: str, cell: str, usd: str, notes: str,
         model: str = MODEL) -> dict:
    row = {c: "" for c in costs.COLUMNS}
    row.update(timestamp_utc="2026-10-18T05:00:00+00:00", run_id=run_id, milestone="M0",
               experiment=experiment, cell_or_config=cell, model_requested=model,
               model_returned=model, provider="anthropic", api="messages",
               service_tier="standard", service_tier_served="standard", n_calls="10",
               input_tokens="1000", cached_input_tokens="600", cache_write_tokens="300",
               output_tokens="40", reasoning_tokens=REASONING, latency_s="0.8",
               cost_usd_list=usd, cost_usd_billed_est=usd, price_source_date="2026-10-17",
               git_commit="0" * 40, notes=notes)
    return row


def _meta(run_id: str, experiment: str, cell: str, variant: str, planned: int,
          n: int) -> dict:
    """A run's meta.json as far as the forecast reads it: its `planned` episode ids (the run
    matrix's) and the `n` episodes it ran."""
    split = "pilot" if experiment == f.PILOT else "validity"
    return {"experiment": experiment, "run_id": run_id, "cell_or_config": cell,
            "model_requested": MODEL,
            "config": {"generator_config_hashes": [registered.HAIKU_GENERATOR_HASH],
                       "episode_ids": [f"{split}-{k // 8:06d}/cell-{k % 8}/{variant}"
                                       for k in range(planned)]},
            "n_episodes_run": n}


def _ledger(tmp_path, runs, extra_rows=()):
    """tmp_path/results: costs.csv with a block-4-haiku row per run of `runs` ((key, usd) or
    (key, usd, episodes)), then `extra_rows`; and each run's meta.json next to it."""
    root = tmp_path / "results"
    path = root / "costs.csv"
    for i, (key, usd, *n) in enumerate(runs):
        experiment, cell, variant, episodes = RUNS[key]
        run_id = f"20261018T05{i:02d}00Z-{cell}-{MODEL}"
        d = root / experiment / run_id
        d.mkdir(parents=True)
        meta = _meta(run_id, experiment, cell, variant, episodes, n[0] if n else episodes)
        (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        costs.append_row(_row(run_id, experiment, cell, usd, f"{TAG}; {key}"), path)
    for r in extra_rows:
        costs.append_row(r, path)
    return path


def _F(b: dict, with_w_n_0: bool, T: int = 200) -> D:
    """F by hand (R8): 8 x 1.1T episodes per multi-turn run (F-0, W-0, W-n-0 when counted,
    the restated control), 4 x 1.1T single-turn prompts; F-0 and the restated control at the
    restated validity run's cost per episode when it is in, else at F-0's pilot's."""
    per_cell, prompts = D(8) * T * D("1.1"), D(4) * T * D("1.1")
    f0 = D(b["restated"]) / 160 if "restated" in b else D(b["F-0"]) / 8
    cells = 2 * f0 + D(b["W-0"]) / 8 + (D(b["W-n-0"]) / 8 if with_w_n_0 else 0)
    return per_cell * cells + prompts * D(b["single-turn"]) / 8


def _withheld_for(b: dict, F: D) -> D:
    """The withheld run's cost (it feeds no line) that puts 0.85 R at exactly F."""
    R = F / D("0.85")
    assert R * D("0.85") == F                         # an exact decimal, so a true boundary
    usd = D(180) - R - sum(D(v) for v in b.values())
    assert usd >= 0
    return usd


def test_the_design_counts():
    assert f.episodes("F-0", 200, 0) == 1600 and f.episodes("F-0", 200, 1) == 160
    assert f.episodes(f.RESTATED, 150, 0) == 1200 and f.episodes("W-0", 150, 1) == 120
    assert f.episodes(f.SINGLE_TURN, 200, 0) == 800 and f.episodes(f.SINGLE_TURN, 200, 1) == 80
    for bad in (0, 95, -10, 205):
        with pytest.raises(ValueError):
            f.episodes("F-0", bad, 0)
    with pytest.raises(ValueError):
        f.episodes("F-0", 200, 2)
    assert f.T_VALUES == tuple(range(200, 0, -10)) and len(f.T_VALUES) == 20
    assert (f.TASK_CELLS, f.SINGLE_TURN_TASK_CELLS, f.T_MAX) == (8, 4, 200)
    assert f.LINES == ("F-0", "W-0", "W-n-0", "F-0-restated", "single-turn")
    assert set(f.PILOT_VARIANT) == set(registered.HAIKU_PILOT_CELLS)
    assert (f.FIT_SHARE, f.SENSITIVITY_FACTOR) == (D("0.85"), D("1.25"))


def test_the_limit_is_block_4_haikus_approval_line():
    text = (f.REPO_ROOT / "results" / "decisions.md").read_text(encoding="utf-8")
    (line,) = approval.approvals_in(text, f.BLOCK)
    assert line.max_usd == f.BLOCK_MAX_USD == 180
    assert {f.PILOT, f.VALIDITY, f.MAIN} <= set(line.experiments)


@pytest.mark.parametrize("restated, T, with_w, nudge, want", [
    ("2.6", 200, True, "0", (True, 200, 1)),         # F(200, with) = 0.85 R exactly: runs
    ("2.6", 200, True, "0.000001", (False, 200, 2)),
    ("2.9", 200, False, "0", (False, 200, 2)),       # F(200, without) = 0.85 R exactly
    ("2.9", 200, False, "0.000001", (False, 190, 3)),
    ("2.9", 150, False, "0", (False, 150, 3)),       # F(150, without) = 0.85 R exactly
    ("2.9", 150, False, "0.000001", (False, 140, 3)),
])
def test_each_branch_of_the_rule_at_its_boundary(tmp_path, restated, T, with_w, nudge, want):
    b = {**PILOTS, "restated": restated}
    F = _F(b, with_w, T)
    withheld = _withheld_for(b, F) + D(nudge)
    fc = f.build(_ledger(tmp_path, [*b.items(), ("withheld", str(withheld))]))
    o = fc.outcome
    assert (o.w_n_0, o.T, o.step, o.stop) == (*want, False)
    assert fc.spent_usd == sum(D(v) for v in b.values()) + withheld
    assert fc.R_usd == 180 - fc.spent_usd and fc.limit_usd == D("0.85") * fc.R_usd
    assert f.total(fc.bases, T, with_w) == F
    assert o.F_usd == _F(b, o.w_n_0, o.T) <= fc.limit_usd
    if nudge == "0":
        assert o.F_usd == fc.limit_usd and o.margin == 1
    else:
        assert f.total(fc.bases, T, with_w) > fc.limit_usd
    # the comparisons, in the rule's order, up to the one that fits
    made = [(c["T"], c["w_n_0"], c["fits"]) for c in o.comparisons]
    expect = [(200, True)] + ([(200, False)] if o.step > 1 else []) + [
        (t, False) for t in f.T_VALUES[1:] if o.step == 3 and t >= o.T]
    assert [(t, w) for t, w, _ in made] == expect
    assert [ok for *_, ok in made] == [False] * (len(made) - 1) + [True]


@pytest.mark.parametrize("withheld", ["175", "200"])
def test_no_T_fits_stops_and_asks(tmp_path, withheld):
    b = {**PILOTS, "restated": "2.9"}
    fc = f.build(_ledger(tmp_path, [*b.items(), ("withheld", withheld)]))
    o = fc.outcome
    assert (o.w_n_0, o.T, o.step, o.stop, o.F_usd, o.margin) == (False, None, 4, True, None,
                                                                  None)
    assert len(o.comparisons) == 21 and not any(c["fits"] for c in o.comparisons)
    assert f.total(fc.bases, 10, False) == _F(b, False, 10) > fc.limit_usd
    text = "\n".join(f.summary_lines(fc))
    assert "No T ≥ 10 fits: no main run starts, and Claude asks the researcher" in text
    assert f.to_json(fc)["outcome"]["runs"] == {}


def test_the_bases_and_their_rows(tmp_path):
    """F-0 and the restated control rest on the restated validity run once it is in; W-0,
    W-n-0 and the single-turn control on their pilots; the withheld run feeds no line."""
    b = {**PILOTS, "restated": "2.6", "withheld": "0.86"}
    fc = f.build(_ledger(tmp_path, list(b.items())))
    per = {k: x.usd_per_episode for k, x in fc.bases.items()}
    assert per == {"F-0": D("2.6") / 160, "W-0": D("0.025"), "W-n-0": D("0.025"),
                   "F-0-restated": D("2.6") / 160, "single-turn": D("0.005")}
    assert {k: x.source for k, x in fc.bases.items()} == {
        "F-0": "validity, restated", "W-0": "pilot", "W-n-0": "pilot",
        "F-0-restated": "validity, restated", "single-turn": "pilot"}
    assert fc.bases["F-0"].episodes == 160 and fc.bases["W-0"].episodes == 8
    j = f.to_json(fc)
    assert j["status"] == "complete" and j["provisional_reasons"] == []
    feeds = {(r["experiment"], r["cell"], r["variant"]): r["feeds"] for r in j["inputs"]["runs"]}
    assert feeds[(f.VALIDITY, "F-0", "withheld")] == []
    assert feeds[(f.PILOT, "F-0", "base")] == []
    assert feeds[(f.VALIDITY, "F-0", "restated")] == ["F-0", "F-0-restated"]
    assert j["checks"]["template"]["validity_over_pilot"] == pytest.approx(
        (2.6 / 160) / (0.1 / 8))
    assert j["checks"]["withheld_usd_per_episode"] == pytest.approx(0.86 / 160)
    assert fc.runs[0].cached_share == pytest.approx(0.6)
    assert {r.calls_over_100000 for r in fc.runs} == {0}
    assert {r.price_source_date for r in fc.runs} == {"2026-10-17"}


def test_calls_over_the_price_threshold_are_read_from_the_notes():
    assert f._calls_over_100000("max_prompt_tokens=120000; calls_over_100000=3; x=1") == 3
    assert f._calls_over_100000("a=1; calls_over_100000=12") == 12
    assert f._calls_over_100000("approved_block=4-haiku; git_dirty=False") is None
    assert f._calls_over_100000("xcalls_over_100000=5;") is None


def test_before_the_validity_runs_the_reading_is_provisional(tmp_path):
    fc = f.build(_ledger(tmp_path, list(PILOTS.items())))
    assert fc.bases["F-0"].source == fc.bases[f.RESTATED].source == "pilot"
    assert fc.bases["F-0"].usd_per_episode == D("0.0125")
    assert f.total(fc.bases, 200, True) == _F(PILOTS, True) == D("136.4")
    assert fc.R_usd == D("179.46") and len(fc.provisional) == 2
    assert f.to_json(fc)["status"] == "provisional"
    assert f.template_check(fc) is None and f.withheld_per_episode(fc) is None
    assert "**Provisional, not the rule's record.**" in "\n".join(f.summary_lines(fc))
    # with the restated run in, only the withheld run is missing
    fc2 = f.build(_ledger(tmp_path / "2", [*PILOTS.items(), ("restated", "2.6")]))
    assert fc2.bases["F-0"].source == "validity, restated"
    assert len(fc2.provisional) == 1 and "withheld" in fc2.provisional[0]


def test_rows_of_other_blocks_are_ignored(tmp_path):
    """At the exact boundary, any row of another block that leaked into R or into a basis
    would flip the outcome (or fail on its missing meta.json)."""
    b = {**PILOTS, "restated": "2.6"}
    withheld = _withheld_for(b, _F(b, True))
    other = [
        _row("20261010T055742Z-F-0-gpt-6-luna", "persistgym", "F-0", "50",
             "approved_block=3-persistgym; context_mismatches=0", model="gpt-6-luna"),
        _row(f"20261017T000000Z-W-0-{MODEL}", f.PILOT, "W-0", "99",
             "approved_block=1-pilots; git_dirty=False"),
        _row(f"20261017T000100Z-F-0-{MODEL}", f.PILOT, "F-0", "7",
             "approved_block=14-haiku; git_dirty=False"),
        _row(f"20261017T000200Z-W-n-0-{MODEL}", f.VALIDITY, "F-0", "3",
             "approved_block=4-haiku-b; git_dirty=False"),
        _row(f"20261017T000300Z-F-0-{MODEL}", f.MAIN, "F-0", "11", "no block tag"),
    ]
    path = _ledger(tmp_path, [*b.items(), ("withheld", str(withheld))], extra_rows=other)
    fc = f.build(path)
    o = fc.outcome
    assert (o.w_n_0, o.T, o.step) == (True, 200, 1) and o.F_usd == fc.limit_usd
    assert fc.block_rows == 6 and len(fc.runs) == 6
    assert fc.spent_usd == approval.block_spend(f.BLOCK, costs.read_rows(path))
    assert fc.R_usd == 176
    assert all(r.run_id.startswith("20261018T05") for r in fc.runs)


def test_rows_of_one_cell_are_pooled(tmp_path):
    """A second W-0 pilot run (a short one) pools with the first: billed over episodes."""
    runs = [*PILOTS.items(), ("W-0", "0.1", 4), ("W-0", "0.05", 0)]
    fc = f.build(_ledger(tmp_path, runs))
    assert fc.bases["W-0"].usd_per_episode == D("0.35") / 12
    assert fc.bases["W-0"].episodes == 12 and len(fc.bases["W-0"].runs) == 3


def test_it_refuses(tmp_path):
    with pytest.raises(ValueError, match="before any main episode"):
        f.build(_ledger(tmp_path / "a", list(PILOTS.items()), extra_rows=[
            _row(f"20261019T000000Z-F-0-{MODEL}", f.MAIN, "F-0", "1", TAG)]))
    with pytest.raises(ValueError, match="no pilot row of W-n-0"):
        f.build(_ledger(tmp_path / "b", [(k, v) for k, v in PILOTS.items() if k != "W-n-0"]))
    with pytest.raises(ValueError, match="is not claude-haiku-5-5"):
        f.build(_ledger(tmp_path / "c", list(PILOTS.items()), extra_rows=[
            _row("20261018T060000Z-F-0-gpt-6-luna", f.PILOT, "F-0", "1", TAG,
                 model="gpt-6-luna")]))
    with pytest.raises(FileNotFoundError, match="no meta.json"):
        f.build(_ledger(tmp_path / "d", list(PILOTS.items()), extra_rows=[
            _row(f"20261018T060000Z-W-0-{MODEL}", f.PILOT, "W-0", "1", TAG)]))
    path = _ledger(tmp_path / "e", list(PILOTS.items()))
    (meta_path,) = (path.parent / f.PILOT).glob("*-W-0-*/meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["config"]["generator_config_hashes"] = ["0" * 64]
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ValueError, match="default generator config"):
        f.build(path)
    meta["config"]["generator_config_hashes"] = [registered.HAIKU_GENERATOR_HASH]
    meta["config"]["episode_ids"][0] = "pilot-000000/cell-0/restated"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ValueError, match="one variant"):
        f.build(path)
    meta["config"]["episode_ids"][0] = "pilot-000000/cell-0/base"
    meta["run_id"] = "another-run"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ValueError, match="not its row's"):
        f.build(path)


def test_the_sensitivity_reading_never_changes_the_outcome(tmp_path):
    b = {**PILOTS, "restated": "2.6"}
    fc = f.build(_ledger(tmp_path, [*b.items(), ("withheld", str(_withheld_for(b, _F(b, True))))]))
    assert (fc.outcome.w_n_0, fc.outcome.T, fc.outcome.step) == (True, 200, 1)
    s = fc.sensitivity                                 # x 1.25: 187.0 with, 132.0 without
    assert (s.w_n_0, s.T, s.step) == (False, 200, 2)
    assert f.total(fc.bases, 200, True, f.SENSITIVITY_FACTOR) == D("187.000")
    j = f.to_json(fc)
    assert j["outcome"]["w_n_0_runs"] is True and j["outcome"]["T"] == 200
    assert j["sensitivity"]["applied"] is False
    assert j["sensitivity"]["rule_would_give"]["step"] == 2
    assert j["sensitivity"]["F_200_with_w_n_0_usd"] == pytest.approx(187.0)
    text = "\n".join(f.summary_lines(fc))
    assert "## Sensitivity (reported only: it does not change the outcome)" in text
    assert "The outcome stays the rule's, above." in text
    assert ("**W-n-0 runs, T = 200** (step 1 of the rule: F(T = 200, with W-n-0) = "
            "149.600000 ≤ 149.600000)." in text)


def test_it_never_reads_reasoning_tokens():
    """Pilot blinding (PREREG §11): the forecast keeps no reasoning-token field."""
    assert not any("reasoning" in x.name for x in dataclasses.fields(f.Run))


def test_main_writes_the_forecast(tmp_path, capsys):
    b = {**PILOTS, "restated": "2.9"}
    withheld = _withheld_for(b, _F(b, False, 150))
    path = _ledger(tmp_path, [*b.items(), ("withheld", str(withheld))])
    out = tmp_path / "out"
    assert f.main(["--costs", str(path), "--out-dir", str(out)]) == 0
    printed = capsys.readouterr().out
    assert ("**W-n-0 does not run, T = 150** (step 3 of the rule: F(T = 160, without W-n-0) "
            "= 89.760000 > 84.150000; F(T = 150, without W-n-0) = 84.150000 ≤ 84.150000)."
            in printed)
    assert sorted(p.name for p in out.iterdir()) == [
        "forecast.csv", "forecast.json", "meta.json", "summary.md"]
    with (out / "forecast.csv").open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == f.CSV_FIELDS
        rows = list(reader)
    assert len(rows) == 2 * 20 * 2
    (r150,) = [r for r in rows if (r["basis"], r["T"], r["w_n_0"]) == ("rule", "150", "False")]
    assert (r150["usd_total"], r150["limit_usd"], r150["fits"]) == ("84.150000", "84.150000",
                                                                    "True")
    assert r150["usd_W-n-0"] == "0.000000" and r150["episodes_per_harness_cell"] == "1320"
    j = json.loads((out / "forecast.json").read_text(encoding="utf-8"))
    assert (j["outcome"]["w_n_0_runs"], j["outcome"]["T"], j["outcome"]["step"]) == (False,
                                                                                   150, 3)
    assert set(j["outcome"]["runs"]) == {"F-0", "W-0", "F-0-restated", "single-turn"}
    assert j["outcome"]["runs"]["single-turn"]["episodes_repeat_1"] == 60
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "`HAIKU_T` = 150, and `HAIKU_CELLS` without W-n-0" in summary
    assert "## Limits" in summary and "## What it does not show" in summary
    assert "the block's rows report 0 such calls." in summary
    assert "Prices as the rows were priced (2026-10-17)" in summary
    assert "reasoning tokens" not in summary
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["experiment"] == "haiku_forecast" and meta["paid_calls"] == 0
    assert meta["cell_or_config"] == "r8_size_rule" and meta["status"] == "complete"
    assert meta["outcome"] == {"w_n_0_runs": False, "T": 150, "stop_and_ask": False, "step": 3}
    inputs = meta["config"]["inputs"]
    assert inputs["costs_csv_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(inputs["meta_json"]) == 6
    for run in j["inputs"]["runs"]:
        meta_path = path.parent / run["experiment"] / run["run_id"] / "meta.json"
        assert run["meta_json_sha256"] == hashlib.sha256(meta_path.read_bytes()).hexdigest()
    for name in ("forecast.csv", "forecast.json", "summary.md", "meta.json"):
        assert REASONING not in (out / name).read_text(encoding="utf-8"), name
    # the results root can be given apart from the costs file
    assert f.build(path, path.parent).outcome == f.build(path).outcome
    assert f.main(["--costs", str(path), "--no-write"]) == 0


# --- the luna figures the module docstring cites (block-1 and block-3 rows) ---------------
LUNA_PILOT = {"F-0": "persistgym_pilot/20261002T081803Z-F-0-gpt-6-luna",
              "W-0": "persistgym_pilot/20261002T082913Z-W-0-gpt-6-luna",
              "W-n-0": "persistgym_pilot/20261002T082140Z-W-n-0-gpt-6-luna",
              "single-turn": "persistgym_pilot/20261010T055627Z-single-turn-gpt-6-luna"}
LUNA_MAIN = {"F-0": "persistgym/20261010T055742Z-F-0-gpt-6-luna",
             "W-0": "persistgym/20261010T073840Z-W-0-gpt-6-luna",
             "W-n-0": "persistgym/20261010T084438Z-W-n-0-gpt-6-luna",
             "single-turn": "persistgym/20261010T125241Z-single-turn-gpt-6-luna",
             "F-0-restated": "persistgym/20261010T113553Z-F-0-gpt-6-luna"}
LUNA_VALIDITY = {"restated": "persistgym_validity/20261002T084243Z-F-0-gpt-6-luna",
                 "withheld": "persistgym_validity/20261002T095135Z-F-0-gpt-6-luna"}


def _luna_per_episode(run: str, rows: dict[str, dict]) -> tuple[float, str]:
    """A committed luna run's billed cost per episode (costs.csv over its meta.json's
    n_episodes_run) and its variant."""
    experiment, run_id = run.split("/")
    meta = json.loads((f.REPO_ROOT / "results" / run / "meta.json").read_text(encoding="utf-8"))
    assert meta["run_id"] == run_id and rows[run_id]["experiment"] == experiment
    return (float(rows[run_id]["cost_usd_billed_est"]) / meta["n_episodes_run"],
            f._variant(meta, run_id))


def test_the_luna_figures_the_docstring_cites():
    doc = " ".join(f.__doc__.split())
    rows = {r["run_id"]: r for r in costs.read_rows()}
    pilot = {k: _luna_per_episode(v, rows) for k, v in LUNA_PILOT.items()}
    main = {k: _luna_per_episode(v, rows) for k, v in LUNA_MAIN.items()}
    val = {k: _luna_per_episode(v, rows) for k, v in LUNA_VALIDITY.items()}
    assert {k: v for k, (_, v) in main.items()} == {
        "F-0": "base", "W-0": "base", "W-n-0": "base", "single-turn": "single_turn",
        "F-0-restated": "restated"}
    assert (val["restated"][1], val["withheld"][1]) == ("restated", "withheld")
    misses = {}
    for cell, label in (("F-0", "F-0"), ("W-0", "W-0"), ("W-n-0", "W-n-0"),
                        ("single-turn", "single-turn")):
        misses[cell] = main[cell][0] / pilot[cell][0] - 1
        assert f"{100 * misses[cell]:.1f}% ({label})" in doc, cell
    assert all(m > 0 for m in misses.values())
    f0_vs_val = abs(main["F-0"][0] / val["restated"][0] - 1)
    restated_vs_val = abs(main["F-0-restated"][0] / val["restated"][0] - 1)
    withheld_vs_f0 = val["withheld"][0] / main["F-0"][0] - 1
    assert f"within {100 * f0_vs_val:.1f}% of the main F-0 run" in doc
    assert f"{100 * restated_vs_val:.1f}% of the main restated control" in doc
    assert f"it cost {100 * withheld_vs_f0:.0f}% more per episode than the main F-0 run" in doc
    # "1.25 is about three times the largest of these misses"
    assert 2.5 < 0.25 / max(misses.values()) < 3.5
