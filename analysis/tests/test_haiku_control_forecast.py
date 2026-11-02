"""analysis.haiku_control_forecast: the spend-reservation rule, on made-up costs and R9's. $0."""

from __future__ import annotations

import pytest

from analysis import haiku_control_forecast as hf


def test_room_to_spare_starts_every_episode():
    assert hf.episodes_started([1.0] * 10, planned=100.0, parallel=2) == (10, pytest.approx(10.0))


def test_the_first_episode_plays_alone_with_the_whole_planned_spend_reserved():
    # it fits exactly; nothing else starts until it has finished, and then 2 x 4 leaves 6 - 8 < 0
    assert hf.episodes_started([4.0] * 5, planned=10.0, parallel=2) == (1, pytest.approx(4.0))


def test_the_last_part_of_the_planned_spend_goes_unused():
    # 1 each, estimate 2: an episode starts while spent + reserved + 2 <= 10
    n, spent = hf.episodes_started([1.0] * 20, planned=10.0, parallel=1)
    assert (n, spent) == (9, pytest.approx(9.0))


def test_parallel_episodes_reserve_more_of_it():
    assert hf.episodes_started([1.0] * 20, planned=10.0, parallel=2)[0] <= 9


def test_r9s_costs_are_the_400_episodes_of_17_38():
    costs = hf.r9_costs(hf.REPO_ROOT)
    assert len(costs) == 400 and sum(costs) == pytest.approx(17.38, abs=0.005)


def test_the_forecast_stops_short_of_200_templates_and_within_the_planned_spend():
    r = hf.forecast(hf.REPO_ROOT)
    at_r9, at_r10 = r["cases"].values()
    assert (at_r9["whole_templates"], at_r10["whole_templates"]) == (197, 154)
    assert at_r9["spent_usd"] <= r["planned_usd"] and at_r10["spent_usd"] <= r["planned_usd"]


def test_one_send_is_six_attempts_at_the_largest_prompt_and_the_output_cap():
    # cache write $0.125, output $0.50 per million; 6 attempts; the US geo's 1.1
    assert hf.most_one_send(33_765) == pytest.approx(
        (33_765 * 0.125 + 32_000 * 0.50) / 1e6 * 6 * 1.1)
