import math

import pandas as pd
import pytest

from arc.public import ops, sessions
from arc.public.discover import PublishedRun

LP85_LIKE = {
    "config": "google-gemini-3-8-flash-high", "model": "gemini-3.8-flash",
    "open_at": "2026-09-10T15:43:25.771774Z", "last_update": "2026-09-10T17:39:45.192226Z",
    "environments": [{"id": "lp85-305b61c3", "level_count": 8, "runs": [{
        "guid": "a", "score": 77.77777777777779, "levels_completed": 7, "actions": 132,
        "resets": 3, "state": "NOT_FINISHED",
        "level_actions": [8, 8, 17, 29, 22, 23, 9, 16],
        "level_baseline_actions": [17, 38, 31, 16, 41, 60, 26, 159]}]}],
}


def session(guid, config, state, levels_completed, level_actions, baselines, score, hours=2.0):
    return {
        "config": config, "model": "gemini-3.8-flash",
        "open_at": "2026-09-10T00:00:00Z",
        "last_update": f"2026-09-10T{int(hours):02d}:{int(hours % 1 * 60):02d}:00Z",
        "environments": [{"id": "zz99-0123abcd", "level_count": len(baselines), "runs": [{
            "guid": guid, "score": score, "levels_completed": levels_completed,
            "actions": sum(level_actions), "resets": 0, "state": state,
            "level_actions": level_actions, "level_baseline_actions": baselines}]}],
    }


def pr(game, harness, effort, guid, score):
    vid = effort if harness == "standard" else f"provider-adapter-{effort}"
    return PublishedRun(game=game, variant_id=vid, variant_label=vid, harness=harness,
                        effort=effort, page_score=score / 100, guid=guid)


@pytest.fixture
def runs():
    pairs = [
        (pr("LP85", "standard", "high", "a", 77.77777777777779), LP85_LIKE),
        (pr("LP85", "provider_adapter", "high", "b", 100.0),
         session("b", "google-gemini-3-8-flash-high-provider-adapter", "WIN", 2, [5, 6],
                 [10, 10], 100.0)),
        (pr("ZZ99", "standard", "high", "c", 10.0),
         session("c", "google-gemini-3-8-flash-high", "GAME_OVER", 1, [10, 50], [10, 10],
                 10.0)),
        (pr("ZZ99", "provider_adapter", "high", "d", 40.0),
         session("d", "google-gemini-3-8-flash-high-provider-adapter", "NOT_FINISHED", 1,
                 [10, 20], [10, 10], 40.0, hours=11.95)),
    ]
    return ops.runs_frame(pairs)


def test_runs_frame_checks_and_endings(runs):
    assert runs.config_matches_variant.all() and runs.score_matches_page.all()
    assert list(runs.inferred_ending) == [sessions.ERROR_OR_CLOSED, sessions.GAME_WIN,
                                          sessions.ACTION_BUDGET, sessions.TIME_BUDGET]
    t = ops.endings_table(runs)
    hi_std = t[(t.harness == "standard") & (t.effort == "high")].iloc[0]
    assert (hi_std.early_no_win, hi_std.n_runs) == (1, 2)
    hi_pa = t[(t.harness == "provider_adapter") & (t.effort == "high")].iloc[0]
    assert (hi_pa[sessions.TIME_BUDGET], hi_pa.early_no_win) == (1, 1)


def test_lp85_example(runs):
    ex = ops.lp85_example(runs)
    assert ex["stopped_on_level"] == 8 and ex["actions_on_stopping_level"] == 16
    assert ex["allowed_actions_on_stopping_level"] == 795
    assert ex["duration"] == "1 h 56 min 19 s" and ex["matches_plan_claim"]


def rec_frame(rows):
    return pd.DataFrame([{"game": g, "harness": h, "guid": guid, "cost_total_usd": cost,
                          "plateau_cost_per_step_mean": plateau, "s_per_step_mean": spa,
                          "n_steps": 1, "n_compactions": 0}
                         for g, h, guid, cost, plateau, spa in rows])


def test_clean_run_bounds(runs):
    rec = rec_frame([("LP85", "standard", "a", 24.33, 0.2, 50.0),
                     ("ZZ99", "standard", "c", 10.0, 0.1, 30.0)])
    b = ops.clean_run_bounds(runs, rec).set_index("game")
    lp = b.loc["LP85"]
    assert lp.remaining_stop_level_actions == 779
    assert lp.bound_stop_level_usd == pytest.approx(24.33 + 779 * 0.2)
    assert lp.bound_full_game_usd == pytest.approx(lp.bound_stop_level_usd)  # last level
    assert lp.bound_stop_level_wallclock_h == pytest.approx(911 * 50 / 3600)
    assert not lp.fits_12h_at_stop_level_bound
    fit = math.floor((12 * 3600 - 6979.420452) / 50)
    assert lp.bound_stop_level_12h_usd == pytest.approx(24.33 + min(779, fit) * 0.2)
    zz = b.loc["ZZ99"]   # ACTION_BUDGET on level 2 of 2: nothing remains
    assert zz.remaining_stop_level_actions == 0 and zz.bound_stop_level_usd == 10.0
    assert zz.bound_full_game_usd == 10.0


def test_eligibility_uses_recording_costs_then_premise(runs):
    rec = rec_frame([("LP85", "standard", "a", 24.33, 0.2, 50.0),
                     ("LP85", "provider_adapter", "b", 11.34, 0.1, 5.0)])
    prem = [{"game": "LP85", "gap": 22.2, "std_cost": 24.33, "pa_cost": 11.34,
             "std_actions": 132.0, "pa_actions": 11.0},
            {"game": "ZZ99", "gap": 30.0, "std_cost": 70.0, "pa_cost": 10.0,
             "std_actions": 60.0, "pa_actions": 30.0}]
    e = ops.eligibility_table(runs, rec, prem).set_index("game")
    assert e.loc["LP85", "cost_source"] == "recordings" and e.loc["LP85", "eligible"]
    assert e.loc["LP85", "premise_cost_match"] and e.loc["LP85", "premise_gap_match"]
    assert e.loc["ZZ99", "cost_source"] == "premise" and not e.loc["ZZ99", "eligible"]
    assert e.loc["ZZ99", "gap"] == pytest.approx(30.0)
