import pytest

from arc.public import recordings as R
from arc.public.tests.fixtures import adapter_recording, standard_recording


def test_parse_lines_levels_frames_and_metadata():
    steps = R.parse_lines(standard_recording())
    assert [s.level_before for s in steps] == [None, 0, 0, 0, 1, 1, 1, 1]
    assert [s.model_call for s in steps] == [False, True, True, True, False, True, True, True]
    assert steps[1].input_tokens == 12_000 and steps[1].reasoning_tokens == 20_000
    assert steps[2].cached_tokens == 10_000
    assert steps[1].timestamp.tzinfo is not None


def test_level_action_counts_exclude_opening_reset_include_forced_reset():
    steps = R.parse_lines(standard_recording())
    assert R.level_action_counts(steps, 2) == [3, 4]


def test_summary_standard():
    s = R.summarize(R.parse_lines(standard_recording()))
    assert (s.n_steps, s.n_model_steps, s.n_forced_resets) == (7, 6, 1)
    assert s.duration_s == 361 and s.s_per_step_median == 60
    assert s.s_per_step_mean == pytest.approx(361 / 7)
    assert s.cost_total_usd == pytest.approx(462_000 * 0.75e-6 + 85_800 * 3.75e-6)
    assert s.cached_share == pytest.approx(160_000 / 462_000)
    assert s.cost_cached_price_usd == pytest.approx(s.cost_total_usd - 160_000 * 0.675e-6)
    assert s.visible_out_per_step_mean == pytest.approx(800 / 6)
    assert s.reasoning_per_step_mean == pytest.approx(85_000 / 6)
    assert s.n_compactions == 0 and s.steps_per_compaction is None
    # the doubled-usage step (line 6) is the only multi-attempt step
    assert s.n_multi_attempt_steps == 1 and not s.last_step_multi_attempt
    assert s.input_max == 200_000


def test_multi_attempt_detection_uses_frames_and_replayed_output():
    steps = R.parse_lines(standard_recording())
    assert R.multi_attempt_steps([x for x in steps if x.model_call]) == [6]
    # Adapter step 4 grows 70k -> 140k, explained by a 5-frame animation: not flagged
    a = R.parse_lines(adapter_recording())
    assert a[4].frames_seen == 5
    assert R.multi_attempt_steps([x for x in a if x.model_call]) == []
    # the same jump after a single-frame observation would be flagged
    a[4].frames_seen = 1
    assert R.multi_attempt_steps([x for x in a if x.model_call]) == [4]


def test_summary_adapter_compaction_counted_once():
    steps = R.parse_lines(adapter_recording())
    assert steps[5].compaction and steps[5].action_input_tokens == 14_000
    s = R.summarize(steps)
    assert s.n_compactions == 1 and s.steps_per_compaction == 6
    assert s.compaction_cost_usd == pytest.approx(150_000 * 0.75e-6 + 0.00375)
    # top-level usage already includes the compaction call; it is not added again
    assert s.cost_total_usd == pytest.approx(471_000 * 0.75e-6 + 33_800 * 3.75e-6)


def test_warmup_and_plateau():
    model = [x for x in R.parse_lines(standard_recording()) if x.model_call]
    assert R.warmup_end(model) == 4      # first step at >= 90% of the p95 input
    s = R.summarize(R.parse_lines(standard_recording()))
    assert s.warmup_steps == 4
    assert s.input_plateau_median == pytest.approx((200_000 + 80_000) / 2)


def test_summarize_rejects_empty():
    with pytest.raises(ValueError):
        R.summarize(R.parse_lines(standard_recording()[:1]))
