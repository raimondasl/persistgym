"""analysis.arc_compaction on a hand-written raw folder (synthetic; no real run is read)."""

from __future__ import annotations

import json

from analysis import arc_compaction as ac

LOG = """\
x | INFO | g - ACTION6: count 0, levels completed 0, avg fps 0.0)
x | INFO | Saved step 1 to recordings/step_001.json
x | INFO | g - ACTION6: count 1, levels completed 0, avg fps 0.01)
x | INFO | Saved step 2 to recordings/step_002.json
x | INFO | g - ACTION6: count 2, levels completed 1, avg fps 0.01)
x | INFO | Saved harness summary compaction 1 before step 3
x | INFO | Saved step 3 to recordings/step_003.json
x | INFO | g - ACTION6: count 3, levels completed 1, avg fps 0.01)
x | WARNING | Could not parse action from response (attempt 1/4).
x | INFO | Saved step 4 to recordings/step_004.json
x | INFO | g - ACTION6: count 4, levels completed 2, avg fps 0.01)
x | INFO | Saved step 5 to recordings/step_005.json
x | INFO | g - ACTION6: count 5, levels completed 2, avg fps 0.01)
x | INFO | Saved step 6 to recordings/step_006.json
x | INFO | g - ACTION6: count 6, levels completed 2, avg fps 0.01)
x | WARNING | Unusable API response (attempt 1/4).
x | WARNING | Unusable API response (attempt 2/4).
"""


def _raw(tmp_path, befores=(3,)):
    raw = tmp_path / "run"
    (raw / "harness").mkdir(parents=True)
    (raw / "harness.log").write_text(LOG, encoding="utf-8")
    for i, b in enumerate(befores, 1):
        (raw / "harness" / f"compaction_{i:03d}.json").write_text(
            json.dumps({"compaction": i, "before_step": b}), encoding="utf-8")
    return raw


def test_parse_run_reads_steps_clears_levels_and_unusable_replies(tmp_path):
    p = ac.parse_run(_raw(tmp_path))
    assert p["compactions"] == [3] and p["last_step"] == 6 and p["levels_completed"] == 2
    assert [s for s, v in sorted(p["steps"].items()) if v["cleared"]] == [2, 4]
    assert {s: v["level"] for s, v in p["steps"].items()} == {1: 1, 2: 1, 3: 2, 4: 2, 5: 3,
                                                               6: 3}
    assert p["unusable"] == {4: 1, 7: 2} and p["summary_failure"] is False


def test_windows_and_rates(tmp_path):
    assert ac.since_compaction(2, [3]) is None
    assert [ac.since_compaction(s, [3]) for s in (3, 4, 7)] == [1, 2, 5]
    run = {"parsed": ac.parse_run(_raw(tmp_path))}
    t = ac.tally([run], k=2)["all"]
    # window = steps 3-4 (step 3: no clear, step 4: a clear and 1 unusable call before it)
    assert (t["window"]["steps"], t["window"]["clears"]) == (2, 1)
    assert (t["window"]["calls"], t["window"]["unusable"]) == (3, 1)
    # other = steps 1-2 (one clear) and 5-6, plus step 7's two unusable calls (since 5 > K = 2)
    assert (t["other"]["steps"], t["other"]["clears"]) == (4, 1)
    assert (t["other"]["calls"], t["other"]["unusable"]) == (6, 2)
    assert t["window"]["clears_per_step"] == 0.5 and t["other"]["unusable_per_call"] == 2 / 6
    by = ac.tally([run], k=2)
    # levels 1-2 (early) are played at steps 1-4, level 3 at steps 5-7
    assert (by["early"]["window"]["steps"], by["early"]["other"]["steps"]) == (2, 2)
    assert (by["level 3"]["window"]["steps"], by["level 3"]["other"]["steps"]) == (0, 2)
    assert by["level 3"]["other"]["unusable"] == 2 and by["deep"]["other"]["calls"] == 0
    e = ac.ending({"run_id": "r", "game": "G", "config": "S1", "counted": True,
                   "agent_exit_reason": "AGENT_ERROR", **run})
    assert e["steps_since_last_compaction"] == 5 and e["unusable_replies"] == 3
