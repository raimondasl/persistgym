"""Small synthetic fixtures shaped like arcprize.org recordings (schema checked 2026-09-30)."""

import json
from datetime import UTC, datetime, timedelta

T0 = datetime(2026, 9, 9, 14, 0, 0, tzinfo=UTC)


def line(i, action, levels, *, secs, meta=None, state="NOT_FINISHED", frames=1):
    return {
        "timestamp": (T0 + timedelta(seconds=secs)).isoformat(),
        "data": {
            "game_id": "zz99-0123abcd", "guid": "g", "state": state,
            "levels_completed": levels, "win_levels": 3, "full_reset": i == 0,
            "available_actions": [1, 2], "frame": [[[0]]] * frames,
            "action_input": {"id": action, "data": {"game_id": "zz99-0123abcd"},
                             "reasoning": None if meta is None else json.dumps(meta)},
        },
    }


def meta(inp, cached, out, rsn, *, compaction_input=None, adapter=False):
    """ActionMetadata as the pinned harness builds it (list prices $0.75 / $3.75 per M)."""
    m = {
        "output": "ACTION1", "reasoning": "",
        "usage": {"input_tokens": inp, "input_tokens_details": {"cached_tokens": cached},
                  "output_tokens": out, "output_tokens_details": {"reasoning_tokens": rsn},
                  "total_tokens": inp + out},
        "cost": {"input_cost": inp * 0.75e-6, "output_cost": out * 3.75e-6,
                 "total_cost": inp * 0.75e-6 + out * 3.75e-6},
    }
    if adapter:
        m["state"] = {"input_items_sent": 1, "history_items_before_prune": 3,
                      "history_items_after_prune": 3}
        if compaction_input is not None:
            m["state"]["harness_compaction"] = {
                "usage": {"input_tokens": compaction_input,
                          "input_tokens_details": {"cached_tokens": 0},
                          "output_tokens": 1000,
                          "output_tokens_details": {"reasoning_tokens": 0},
                          "total_tokens": compaction_input + 1000},
                "cost": {"input_cost": compaction_input * 0.75e-6, "output_cost": 0.00375,
                         "total_cost": compaction_input * 0.75e-6 + 0.00375}}
    return m


def standard_recording():
    """Opening RESET, 6 model steps over 2 levels, a forced RESET, a doubled-usage retry step."""
    return [
        line(0, "RESET", 0, secs=0),
        line(1, "ACTION1", 0, secs=60, meta=meta(12_000, 0, 20_100, 20_000)),
        line(2, "ACTION2", 0, secs=120, meta=meta(40_000, 10_000, 15_100, 15_000)),
        line(3, "ACTION1", 1, secs=180, meta=meta(60_000, 20_000, 10_200, 10_000)),  # level up
        line(4, "RESET", 1, secs=181, state="NOT_FINISHED"),                         # forced
        line(5, "ACTION2", 1, secs=241, meta=meta(70_000, 30_000, 10_100, 10_000)),
        line(6, "ACTION1", 1, secs=301, meta=meta(200_000, 60_000, 20_200, 20_000)),  # 2 tries
        line(7, "ACTION2", 1, secs=361, meta=meta(80_000, 40_000, 10_100, 10_000)),
    ]


def adapter_recording():
    """Adapter-style: growth by replayed thinking, then a compaction step."""
    return [
        line(0, "RESET", 0, secs=0),
        line(1, "ACTION1", 0, secs=10, meta=meta(12_000, 0, 30_000, 29_900, adapter=True)),
        line(2, "ACTION1", 0, secs=20, meta=meta(55_000, 0, 500, 450, adapter=True)),
        line(3, "ACTION1", 0, secs=30, meta=meta(70_000, 50_000, 500, 450, adapter=True),
             frames=5),
        line(4, "ACTION1", 0, secs=40, meta=meta(140_000, 65_000, 500, 450, adapter=True)),
        line(5, "ACTION1", 1, secs=80, meta=meta(14_000 + 150_000, 0, 2_000, 1_000,
                                                 compaction_input=150_000, adapter=True)),
        line(6, "ACTION1", 1, secs=90, meta=meta(30_000, 0, 300, 250, adapter=True)),
    ]
