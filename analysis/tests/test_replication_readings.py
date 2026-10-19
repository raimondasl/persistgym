"""analysis.replication_readings on the committed sweeps ($0): the descriptive readings the
preprint's §4 states about R8's replication."""

from analysis import replication_readings as rr


def test_the_readings_the_preprint_states():
    luna, haiku = (rr.readings(m, rr.REPO_ROOT) for m in rr.CITED)
    assert luna["counted_repeat0_records"] == 8800 and haiku["counted_repeat0_records"] == 5600
    lc, hc = luna["w0_nonrec_far_choices"], haiku["w0_nonrec_far_choices"]
    assert sum(c["chose_an_option"] for c in lc.values()) == 387
    assert sum(c["correct"] for c in lc.values()) == 31
    assert all(c["episodes"] == 200 and c["chose_an_option"] == 0 for c in hc.values())
    refused = {k: (v["with_refusal"], v["need_step_refusals"])
               for k, v in haiku["refusals_by_run_kind"].items()}
    assert refused == {"F-0": (22, 10), "F-0 restated": (17, 6), "W-0": (26, 2),
                       "single-turn": (1, 1)}
    assert haiku["refusal_templates_by_skin"] == {"biobank": 13, "archive": 1}
    assert all(v["with_refusal"] == 0 for v in luna["refusals_by_run_kind"].values())
