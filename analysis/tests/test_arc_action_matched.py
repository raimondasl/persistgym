"""Action-matched ARC readings (analysis/arc_action_matched.py; PREREG §17.5, amendment R5):
ARC's score rule against block 2's runs 1 and 2, matching at K actions and censoring on
synthetic scorecards, reset handling, re-run links, refusals and the output allowlist.

Of block 2's runs, only runs 1 and 2 are read from the repository (both were seen before
R5); every other ARC path run here is synthetic. The checks of PREREG §17.5's numbers also
read the ARC pilot rows of results/costs.csv (latency only) and the published recordings'
per-action file."""

from __future__ import annotations

import csv
import io
import itertools
import json
import math
import random
import re

import pytest

from analysis import arc_action_matched as am
from common import costs

ARC_PATH = am.ARC_PATH
RUN1 = "20261006T144656Z-S4-cd82-s1"        # CD82 S4, GAME_WIN (committed with PR #47)
RUN2 = "20261006T171726Z-S0-ft09-s1"        # FT09 S0, TIME_BUDGET

# Run 2 as reported to the researcher on 2026-10-07 (PREREG §17.5): its folder is not on
# main as this test is written, so these are the stated values.
RUN2_STATED = {"actions": 236, "resets": 4, "levels_completed": 5, "level_count": 6,
               "level_actions": [4, 7, 108, 33, 37, 47],
               "level_baseline_actions": [43, 12, 23, 28, 65, 37],
               "level_scores_2dp": [115.0, 115.0, 4.54, 71.99, 115.0, 0.0],
               "score_2dp": 58.17}


# --- synthetic run folders -----------------------------------------------------------------

def _scorecard(level_actions, baselines, levels_completed, *, actions=None, resets=0,
               score=None, plays=1, extra=None):
    scores = [am.level_score(b, a, i < levels_completed)
              for i, (b, a) in enumerate(zip(baselines, level_actions, strict=True))]
    play = {"id": None, "guid": "g", "score": am.game_score(scores) if score is None else score,
            "levels_completed": levels_completed,
            "actions": sum(level_actions) if actions is None else actions, "resets": resets,
            "state": "WIN" if levels_completed == len(baselines) else "NOT_FINISHED",
            "completed": levels_completed == len(baselines), "level_scores": scores,
            "level_actions": list(level_actions), "level_baseline_actions": list(baselines),
            "number_of_levels": None, "number_of_environments": 0, "message": None}
    env = {"id": "game-x", "runs": [play] * plays, "score": play["score"],
           "actions": play["actions"], "levels_completed": levels_completed,
           "completed": play["completed"], "level_count": len(baselines), "resets": resets}
    return {"card_id": "card-1", "score": play["score"], "environments": [env], **(extra or {})}


def _folder(root, run_id, *, ending="GAME_WIN", level_actions=(10, 20, 30),
            baselines=(10, 20, 30), levels_completed=None, config="S0", game="ft09", seed=1,
            rerun_of=None, wall=3600.0, billed=10.0, listed=12.0, experiment="arc_path",
            card=None, meta_extra=None, truncation=None, exit_reason=None):
    d = root / run_id
    d.mkdir(parents=True)
    if levels_completed is None:
        levels_completed = len(baselines) if ending == "GAME_WIN" else len(baselines) - 1
    meta = {"experiment": experiment, "run_id": run_id, "cell_or_config": config,
            "game_requested": game, "seeds": {"replicate_seed": seed}, "rerun_of": rerun_of,
            "agent_exit_reason": ending, "exit_reason": exit_reason or ending,
            "wall_clock_s": wall, "cost_usd": {"list": listed, "billed_est": billed},
            "truncation_limits": truncation or {"max_actions": None,
                                                "after_summary_turns": None},
            **(meta_extra or {})}
    (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    if card is not False:
        card = card or _scorecard(level_actions, baselines, levels_completed)
        (d / "scorecard.json").write_text(json.dumps(card), encoding="utf-8")
    return d


def _costs_csv(path, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=costs.COLUMNS, lineterminator="\n")
    w.writeheader()
    for run_id, billed, listed in rows:
        w.writerow({**dict.fromkeys(costs.COLUMNS, ""), "run_id": run_id,
                    "experiment": "arc_path", "cost_usd_billed_est": billed,
                    "cost_usd_list": listed})
    path.write_text(buf.getvalue(), encoding="utf-8")
    return path


def _independent_score(baselines, level_actions, levels_completed):
    """ARC's rule written again from docs.arcprize.org/methodology and the toolkit, apart from
    the module: weights 1..n, squared ratio capped at 1.15 × baseline, uncleared levels 0,
    capped at the weight share of levels that scored."""
    n = len(baselines)
    s = [0.0] * n
    for i in range(levels_completed):
        if level_actions[i] > 0:
            s[i] = 100 * min((baselines[i] / level_actions[i]) ** 2, 1.15)
    w = list(range(1, n + 1))
    mean = sum(x * y for x, y in zip(s, w, strict=True)) / sum(w)
    share = 100 * sum(y for x, y in zip(s, w, strict=True) if x > 0) / sum(w)
    return min(mean, share)


def _stopped_at(level_actions, levels_completed, k):
    """The play cut after k actions, as ARC would record a run that stopped there: the levels
    completed by then keep their actions, the level in play gets the rest, later levels 0."""
    cut, used, done = [], 0, 0
    for i, a in enumerate(level_actions):
        if i < levels_completed and used + a <= k:
            cut.append(a)
            used += a
            done += 1
        else:
            cut.append(max(0, min(k, sum(level_actions)) - used))
            used = min(k, sum(level_actions))
    return cut, done


# --- ARC's score against runs 1 and 2 ------------------------------------------------------

def test_the_score_rule_reproduces_run_1_exactly():
    card = json.loads((ARC_PATH / RUN1 / "scorecard.json").read_text(encoding="utf-8"))
    play = card["environments"][0]["runs"][0]
    run = am.load_run(ARC_PATH / RUN1)
    assert run.recomputed_level_scores == play["level_scores"]       # bit for bit
    assert run.score_recomputed == play["score"] == 73.02044380603104
    assert run.score_reproduced
    assert _independent_score(run.level_baseline_actions, run.level_actions,
                              run.levels_completed) == pytest.approx(play["score"], abs=1e-12)
    assert (run.game, run.config, run.replicate, run.agent_exit_reason) == (
        "CD82", "S4", 1, "GAME_WIN")


def test_the_score_rule_reproduces_run_2_as_reported():
    s = RUN2_STATED
    scores = [am.level_score(b, a, i < s["levels_completed"])
              for i, (b, a) in enumerate(zip(s["level_baseline_actions"], s["level_actions"],
                                             strict=True))]
    assert [round(x, 2) for x in scores] == s["level_scores_2dp"]
    assert round(am.game_score(scores), 2) == s["score_2dp"]
    # 1,221.58 / 21 with the stated two-decimal level scores; the cap (15/21 × 100) does not bind
    assert sum(x * (i + 1) for i, x in enumerate(s["level_scores_2dp"])) / 21 == pytest.approx(
        58.17, abs=0.005)
    assert sum(s["level_actions"]) == s["actions"]


def test_run_2_committed_scorecard_reproduces_exactly():
    folder = ARC_PATH / RUN2
    if not (folder / "scorecard.json").is_file():
        pytest.skip("run 2's folder is not committed in this checkout yet")
    run = am.load_run(folder)
    assert run.score_reproduced
    assert run.score_recomputed == run.score_scorecard
    s = RUN2_STATED
    assert (run.actions, run.resets, run.levels_completed, run.level_count) == (
        s["actions"], s["resets"], s["levels_completed"], s["level_count"])
    assert run.level_actions == s["level_actions"]
    assert run.level_baseline_actions == s["level_baseline_actions"]
    assert round(run.score_scorecard, 2) == s["score_2dp"]
    assert run.agent_exit_reason == "TIME_BUDGET"


def test_the_cap_at_the_weight_share_of_scored_levels_binds():
    """Two easy levels of six at 115 each: the weighted mean 345/21 = 16.43 is capped at
    3/21 × 100 = 14.29 (run 1 at K = 50 is this case)."""
    assert am.game_score([115.0, 115.0, 0, 0, 0, 0]) == pytest.approx(300 / 21)
    run = am.load_run(ARC_PATH / RUN1)
    at = run.at_k(50)
    assert at["levels_cleared"] == 2 and at["score"] == pytest.approx(300 / 21)


def test_a_cleared_level_with_no_actions_scores_zero_as_in_the_toolkit():
    assert am.level_score(10, 0, True) == 0.0
    assert am.level_score(10, 5, False) == 0.0
    assert am.level_score(10, 5, True) == 115.0                    # (10/5)² × 100 capped
    assert am.level_score(10, 20, True) == 25.0


# --- matching at K -------------------------------------------------------------------------

def test_levels_cleared_within_k_use_cumulative_actions():
    la, done = [4, 7, 108, 33, 37, 47], 5                         # run 2's stated lists
    assert [am.cleared_within(la, done, k) for k in (0, 3, 4, 10, 11, 118, 119, 150, 152,
                                                     188, 189, 236, 10_000)] == [
        0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 5]
    # the level in play never counts, even when its actions so far fit inside K
    assert am.cleared_within([5, 5, 5], 1, 100) == 1


def test_run_2_at_the_registered_count():
    s = RUN2_STATED
    score = am.score_within(s["level_baseline_actions"], s["level_actions"],
                            s["levels_completed"], am.REGISTERED_K)
    assert am.cleared_within(s["level_actions"], s["levels_completed"], 150) == 3
    expected = (115 + 2 * 115 + 3 * 100 * (23 / 108) ** 2) / 21
    assert score == pytest.approx(expected)
    assert am.status_at(s["actions"], "TIME_BUDGET", 150) == am.OBSERVED


def test_rhae_k_is_the_score_of_the_play_cut_after_k_actions():
    """Independent re-derivation: cut the play after K actions as ARC would record a run that
    stopped there, and score the cut play with the independent rule."""
    rng = random.Random(20261007)
    for _ in range(300):
        n = rng.randint(1, 8)
        baselines = [rng.randint(5, 80) for _ in range(n)]
        level_actions = [rng.randint(1, 120) for _ in range(n)]
        done = rng.randint(0, n)
        if done < n:                                    # levels after the one in play: 0
            level_actions = level_actions[: done + 1] + [0] * (n - done - 1)
        total = sum(level_actions)
        for k in sorted({0, 1, total, total + 50, *(rng.randint(0, total + 10)
                                                    for _ in range(5))}):
            cut, cleared = _stopped_at(level_actions, done, k)
            assert am.cleared_within(level_actions, done, k) == cleared
            assert am.score_within(baselines, level_actions, done, k) == pytest.approx(
                _independent_score(baselines, cut, cleared), abs=1e-9)
        assert am.score_within(baselines, level_actions, done, total) == pytest.approx(
            _independent_score(baselines, level_actions, done), abs=1e-9)


def test_rhae_k_never_decreases_with_k():
    rng = random.Random(7)
    for _ in range(100):
        n = rng.randint(1, 8)
        b = [rng.randint(5, 80) for _ in range(n)]
        la = [rng.randint(1, 120) for _ in range(n)]
        done = rng.randint(0, n)
        values = [am.score_within(b, la, done, k) for k in range(sum(la) + 20)]
        assert all(x <= y + 1e-12 for x, y in itertools.pairwise(values))


@pytest.mark.parametrize("ending,status", [
    ("GAME_WIN", am.COMPLETE), ("ACTION_BUDGET", am.COMPLETE),
    ("TIME_BUDGET", am.CENSORED), ("COST_CAP", am.CENSORED), ("API_ERROR", am.CENSORED),
    ("AGENT_ERROR", am.CENSORED), ("SCORECARD_CLOSED", am.CENSORED), ("UNKNOWN", am.CENSORED),
    (None, am.CENSORED)])
def test_censoring_before_k_follows_the_agents_own_ending(ending, status):
    assert am.status_at(120, ending, 150) == status
    assert am.status_at(150, ending, 150) == am.OBSERVED          # reached K: exact
    assert am.status_at(236, ending, 150) == am.OBSERVED


def test_censoring_reads_agent_exit_reason_not_exit_reason(tmp_path):
    """A GAME_WIN whose scorecard close failed (exit_reason API_ERROR, PREREG §7.5) is
    complete, and a missing agent ending counts as UNKNOWN."""
    won = am.load_run(_folder(tmp_path, "won", ending="GAME_WIN", exit_reason="API_ERROR"))
    assert won.at_k(1000)["status"] == am.COMPLETE
    died = am.load_run(_folder(tmp_path, "died", ending=None, exit_reason="UNKNOWN"))
    assert died.agent_exit_reason == "UNKNOWN" and died.at_k(1000)["status"] == am.CENSORED


def test_final_values_carry_to_larger_k(tmp_path):
    run = am.load_run(_folder(tmp_path, "t", ending="TIME_BUDGET", level_actions=(4, 7, 108),
                              baselines=(43, 12, 23), levels_completed=2))
    at = run.at_k(1000)
    assert at["status"] == am.CENSORED and at["levels_cleared"] == 2
    assert at["score"] == pytest.approx(run.score_scorecard)      # a lower bound at K = 1000
    win = am.load_run(_folder(tmp_path, "w"))
    assert win.at_k(10_000) == {"status": am.COMPLETE, "levels_cleared": 3,
                                "score": pytest.approx(win.score_scorecard)}


# --- resets ----------------------------------------------------------------------------------

def test_resets_count_as_actions_in_run_1():
    """Run 1: 4 resets; scorecard actions = Σ level_actions = the harness's action counter,
    which counts every action it submits after the opening RESET, resets included."""
    run = am.load_run(ARC_PATH / RUN1)
    meta = json.loads((ARC_PATH / RUN1 / "meta.json").read_text(encoding="utf-8"))
    assert run.resets == 4
    assert run.actions == run.sum_level_actions == meta["outcome"]["action_counter"] == 206
    assert run.cleared_at_actions == [22, 28, 78, 104, 190, 206]


def test_a_run_whose_actions_differ_from_its_level_actions_is_flagged(tmp_path):
    card = _scorecard([10, 20, 30], [10, 20, 30], 3, actions=61, resets=1)
    run = am.load_run(_folder(tmp_path, "odd", card=card))
    assert run.sum_level_actions == 60 and run.actions == 61
    text = "\n".join(am.summary_lines([run], [], 150, "now", {"git_commit": "0" * 40,
                                                                "git_dirty": False}))
    assert "Σ level_actions = actions: **fails for odd**" in text


def test_a_scorecard_with_a_second_play_is_skipped(tmp_path):
    card = _scorecard([10, 20, 30], [10, 20, 30], 3, plays=2)
    _folder(tmp_path, "two", card=card)
    runs, skipped = am.collect([tmp_path / "two"])
    assert runs == [] and skipped[0][0] == "two" and "2 plays" in skipped[0][1]


def test_a_score_that_does_not_reproduce_is_flagged(tmp_path):
    card = _scorecard([10, 20, 30], [10, 20, 30], 3, score=99.0)
    run = am.load_run(_folder(tmp_path, "off", card=card))
    assert not run.score_reproduced
    text = "\n".join(am.summary_lines([run], [], 150, "now", {"git_commit": "0" * 40,
                                                                "git_dirty": False}))
    assert "**not for off**" in text


# --- runs, re-runs and refusals ------------------------------------------------------------

def test_a_rerun_replaces_its_original(tmp_path):
    _folder(tmp_path, "orig", ending="TIME_BUDGET", seed=1)
    _folder(tmp_path, "re", ending="GAME_WIN", seed=101, rerun_of="orig")
    runs, _ = am.collect([tmp_path / "orig", tmp_path / "re"])
    by = {r.run_id: r for r in runs}
    assert not by["orig"].counted and by["orig"].replaced_by == ["re"]
    assert by["re"].counted and by["re"].replicate == 1 and by["re"].seed == 101
    assert am.run_row(by["orig"], 150)["replaced_by"] == "re"


def test_pilot_and_foreign_folders_are_refused(tmp_path):
    _folder(tmp_path, "pilot", experiment="arc_pilot", card=False)
    with pytest.raises(am.Refused, match="arc_pilot"):
        am.collect([tmp_path / "pilot"])
    (tmp_path / "bare").mkdir()
    with pytest.raises(am.Refused, match="no meta.json"):
        am.load_run(tmp_path / "bare")


def test_truncated_and_scorecardless_runs_are_skipped(tmp_path):
    _folder(tmp_path, "trunc", truncation={"max_actions": 50, "after_summary_turns": None})
    _folder(tmp_path, "nocard", card=False)
    runs, skipped = am.collect([tmp_path / "trunc", tmp_path / "nocard"])
    assert runs == []
    assert dict(skipped) == {"trunc": "truncated (not a counted run)",
                             "nocard": "no scorecard.json"}


def test_costs_rows_are_checked(tmp_path):
    runs, _ = am.collect([_folder(tmp_path, "a", billed=10.0, listed=12.0),
                          _folder(tmp_path, "b", billed=5.0, listed=6.0),
                          _folder(tmp_path, "c")])
    am.check_costs(runs, _costs_csv(tmp_path / "costs.csv",
                                    [("a", "10.0", "12.0"), ("b", "5.5", "6.0")]))
    assert [r.costs_row for r in runs] == ["match", "mismatch", "missing"]


def test_pace_and_cost_per_action(tmp_path):
    run = am.load_run(_folder(tmp_path, "p", level_actions=(100, 100), baselines=(50, 50),
                              wall=20_000.0, billed=40.0, listed=50.0))
    row = am.run_row(run, 150)
    assert row["seconds_per_action"] == 100.0
    assert row["billed_usd_per_action"] == 0.2 and row["list_usd_per_action"] == 0.25


def test_run_1_pace_and_cost():
    run = am.load_run(ARC_PATH / RUN1)
    assert run.per_action(run.wall_clock_s) == pytest.approx(8979.372 / 206)
    assert run.per_action(run.cost_billed_usd) == pytest.approx(16.872417 / 206)
    assert math.isclose(run.wall_clock_s / 3600, 2.494, abs_tol=0.001)


# --- outputs -------------------------------------------------------------------------------

def _all_text(out):
    return "\n".join(p.read_text(encoding="utf-8") for p in out.iterdir())


def test_the_output_is_exactly_the_allowlist(tmp_path):
    root = tmp_path / "arc_path"
    secret = "SECRET-VALUE-123"
    extra_meta = {"api_key": secret, "raw_transcript_path": f"results/raw/{secret}",
                  "tokens": {"reasoning_tokens": 777_777_777}, "notes": secret}
    folders = [_folder(root, "r1", meta_extra=extra_meta,
                       card=_scorecard([10, 20, 30], [10, 20, 30], 3,
                                       extra={"api_key": secret, "opaque": secret})),
               _folder(root, "r2", ending="TIME_BUDGET", meta_extra=extra_meta)]
    out = tmp_path / "out"
    costs_csv = _costs_csv(tmp_path / "costs.csv", [("r1", "10.0", "12.0")])
    assert am.main([str(f) for f in folders] + ["--out-dir", str(out), "--costs-csv",
                                                str(costs_csv)]) == 0
    assert sorted(p.name for p in out.iterdir()) == sorted([*am.OUTPUTS, "meta.json"])
    runs = list(csv.DictReader((out / "runs.csv").open(encoding="utf-8")))
    curve = list(csv.DictReader((out / "curve.csv").open(encoding="utf-8")))
    assert tuple(runs[0]) == am.RUN_FIELDS and tuple(curve[0]) == am.CURVE_FIELDS
    assert len(runs) == 2 and len(curve) == 2 * len(am.CURVE_K)
    assert {r["K"] for r in runs} == {"150"} and {r["K_role"] for r in runs} == {"registered"}
    text = _all_text(out)
    assert secret not in text and "777777777" not in text and "results/raw" not in text
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["experiment"] == "arc_action_matched" and meta["paid_calls"] == 0
    assert meta["outputs"] == list(am.OUTPUTS) and meta["runs"] == ["r1", "r2"]
    assert meta["config"]["K"] == 150 and meta["config"]["registered_K"] == 150


def test_another_k_is_labelled_exploratory(tmp_path):
    f = _folder(tmp_path / "arc_path", "r1")
    out = tmp_path / "out"
    am.main([str(f), "--k", "120", "--out-dir", str(out), "--costs-csv",
             str(_costs_csv(tmp_path / "c.csv", []))])
    runs = list(csv.DictReader((out / "runs.csv").open(encoding="utf-8")))
    curve = list(csv.DictReader((out / "curve.csv").open(encoding="utf-8")))
    assert runs[0]["K"] == "120" and runs[0]["K_role"] == "exploratory"
    assert [int(r["K"]) for r in curve] == [50, 100, 120, 150, 200]
    assert "readings at this K are exploratory" in (out / "summary.md").read_text("utf-8")


def test_k_must_be_positive(tmp_path):
    with pytest.raises(SystemExit):
        am.main(["--k", "0", "--no-write"])


def test_the_committed_outputs_agree_with_the_code():
    """Every committed output's rows for runs 1 and 2 re-derive from their scorecards."""
    for out in sorted(am.OUT_ROOT.glob("*/runs.csv")):
        for row in csv.DictReader(out.open(encoding="utf-8")):
            if row["run_id"] not in (RUN1, RUN2) or not (ARC_PATH / row["run_id"]).is_dir():
                continue
            run = am.load_run(ARC_PATH / row["run_id"])
            at = run.at_k(int(row["K"]))
            assert row["status_at_K"] == at["status"]
            assert int(row["levels_cleared_at_K"]) == at["levels_cleared"]
            assert float(row["score_at_K"]) == at["score"]
            assert row["score_reproduced"] == "True"


# --- the numbers PREREG §17.5 states ---------------------------------------------------------

RUN2_SECONDS_PER_ACTION = 184           # stated for run 2 (about 12 h / 236 actions)


def _r5_section() -> str:
    text = (am.REPO_ROOT / "PREREG.md").read_text(encoding="utf-8")
    return text[text.index("### 17.5 Amendment R5"):]


def test_prereg_r5_cites_the_committed_run_of_the_script():
    section = _r5_section()
    (folder,) = set(re.findall(r"results/arc_action_matched/(\d{8}T\d{6}Z)/", section))
    meta = json.loads((am.OUT_ROOT / folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["git_dirty"] is False and meta["config"]["K"] == am.REGISTERED_K == 150
    assert meta["runs"] == [RUN1]                    # run 1 only, as §17.5 says
    assert "73.02044380603104" in section and "2.49 h" in section


def test_prereg_r5_k_follows_its_pace_rule():
    """K is the largest multiple of 50 every config reaches inside 12 h at run 2's pace, with
    S1 and S2 slowed by their pilot median seconds per call relative to S0's (costs.csv)."""
    section = _r5_section()
    latency = {r["cell_or_config"]: float(r["latency_s"])
               for r in costs.read_rows() if r["experiment"] == "arc_pilot"}
    for c in ("S0", "S1", "S2", "S4"):
        assert f"{latency[c]:.1f} s" in section, c
    pace = {c: RUN2_SECONDS_PER_ACTION * latency[c] / latency["S0"] for c in ("S0", "S1", "S2")}
    assert f"{latency['S1'] / latency['S0']:.2f} times" in section
    assert f"{latency['S2'] / latency['S0']:.2f} times" in section
    for k in (150, 200):
        for c in ("S0", "S1", "S2"):
            assert f"{k * pace[c] / 3600:.1f} h" in section, (k, c)
    clock = 12 * 3600
    k = max(k for k in range(50, 1001, 50) if all(k * p <= clock for p in pace.values()))
    assert k == am.REGISTERED_K


def test_prereg_r5_published_pace_comparisons():
    """ARC's published FT09 Standard-high run ended at action 126 after 3.0 h (86 s per
    action); its CD82 Adapter run took 36 s per action (the operational slice's file)."""
    path = (am.REPO_ROOT / "results" / "arc_public_ops" / "20261001T185155Z"
            / "recordings_per_action.csv")
    rows = {(r["game"], r["harness"]): r for r in csv.DictReader(path.open(encoding="utf-8"))}
    ft09, cd82 = rows[("FT09", "standard")], rows[("CD82", "provider_adapter")]
    section = _r5_section()
    assert int(ft09["session_actions"]) == 126 and "action 126" in section
    assert f"{float(ft09['duration_s']) / 3600:.1f} h" == "3.0 h" and "3.0 h" in section
    per_action = float(ft09["duration_s"]) / int(ft09["session_actions"])
    assert f"its {per_action:.0f} s" in section
    cd82_pace = float(cd82["duration_s"]) / int(cd82["session_actions"])
    assert f"against {cd82_pace:.0f} s in ARC's published CD82 Adapter run" in section
    run1 = am.load_run(ARC_PATH / RUN1)
    assert f"Run 1 averaged {run1.per_action(run1.wall_clock_s):.0f} s per action" in section
