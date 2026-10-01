import pytest

from arc.public import sessions as S


def session(level_actions, baselines, state="NOT_FINISHED", levels_completed=None,
            open_at="2026-09-10T15:43:25.771774Z", last_update="2026-09-10T17:39:45.192226Z",
            config="google-gemini-3-8-flash-high", resets=3):
    if levels_completed is None:
        levels_completed = sum(1 for a in level_actions if a) - (0 if state == "WIN" else 1)
    return {
        "config": config, "model": "gemini-3.8-flash",
        "open_at": open_at, "last_update": last_update,
        "environments": [{
            "id": "zz99-0123abcd", "level_count": len(baselines),
            "runs": [{"guid": "g", "score": 50.0, "levels_completed": levels_completed,
                      "actions": sum(level_actions), "resets": resets, "state": state,
                      "level_actions": level_actions,
                      "level_baseline_actions": baselines}],
        }],
    }


def test_level_budget_matches_harness_ceil():
    assert S.level_budget(159) == 795
    assert S.level_budget(17) == 85
    assert S.level_budget(10, multiplier=2.5) == 25
    assert S.level_budget(3, multiplier=1.5) == 5  # ceil(4.5)


def test_lp85_like_early_stop_is_error_or_closed():
    # cleared 7 levels, stopped on level 8 after 16 of 795 actions, ~1 h 56 min
    s = S.parse_session(session([8, 8, 17, 29, 22, 23, 9, 16],
                                [17, 38, 31, 16, 41, 60, 26, 159], levels_completed=7))
    assert s.final_level_index == 7
    assert (s.final_level_actions, s.final_level_budget) == (16, 795)
    assert s.duration_s == pytest.approx(1 * 3600 + 56 * 60 + 19.42, abs=0.01)
    assert s.inferred_ending == S.ERROR_OR_CLOSED
    assert s.budget_margin == 779 and not s.margin_within_resets


def test_action_budget_when_final_level_reaches_ceil_5x():
    s = S.parse_session(session([10, 50], [10, 10], levels_completed=1))
    assert s.final_level_index == 1 and s.final_level_budget == 50
    assert s.inferred_ending == S.ACTION_BUDGET and s.budget_margin == 0


def test_borderline_margin_flagged_against_resets():
    s = S.parse_session(session([10, 48], [10, 10], levels_completed=1, resets=3))
    assert s.inferred_ending == S.ERROR_OR_CLOSED
    assert s.budget_margin == 2 and s.margin_within_resets


def test_win_beats_everything():
    s = S.parse_session(session([10, 60], [10, 10], state="WIN", levels_completed=2))
    assert s.final_level_index == 1  # a won game stops on its last level
    assert s.inferred_ending == S.GAME_WIN


def test_time_budget_after_11_9_hours():
    s = S.parse_session(session([10, 5], [10, 10], levels_completed=1,
                                open_at="2026-09-10T00:00:00Z",
                                last_update="2026-09-10T11:55:00Z"))
    assert s.inferred_ending == S.TIME_BUDGET
    s2 = S.parse_session(session([10, 5], [10, 10], levels_completed=1,
                                 open_at="2026-09-10T00:00:00Z",
                                 last_update="2026-09-10T11:50:00Z"))
    assert s2.inferred_ending == S.ERROR_OR_CLOSED


def test_action_budget_takes_precedence_over_time():
    assert S.infer_ending("NOT_FINISHED", 50, 50, 12 * 3600) == S.ACTION_BUDGET
    assert S.infer_ending("GAME_OVER", 49, 50, 12 * 3600) == S.TIME_BUDGET


def test_first_level_stop_and_unreached_levels():
    s = S.parse_session(session([7, 0, 0], [5, 6, 7], levels_completed=0))
    assert s.final_level_index == 0 and s.final_level_budget == 25
    assert s.inferred_ending == S.ERROR_OR_CLOSED


def test_inconsistent_sessions_raise():
    bad = session([1, 2], [3, 4], levels_completed=1)
    bad["environments"][0]["runs"][0]["actions"] = 99
    with pytest.raises(ValueError):
        S.parse_session(bad)
    bad = session([1, 2], [3, 4], levels_completed=1)
    bad["environments"][0]["runs"][0]["level_baseline_actions"] = [3]
    with pytest.raises(ValueError):
        S.parse_session(bad)
    bad = session([1, 2], [3, 4], levels_completed=2)
    with pytest.raises(ValueError):
        S.parse_session(bad)  # all levels done but not WIN


def test_config_matches():
    assert S.config_matches("google-gemini-3-8-flash-high", "standard", "high")
    assert S.config_matches("google-gemini-3-8-flash-low-provider-adapter",
                            "provider_adapter", "low")
    assert not S.config_matches("google-gemini-3-8-flash-high", "provider_adapter", "high")
    assert not S.config_matches("google-gemini-3-8-flash-medium", "standard", "high")
