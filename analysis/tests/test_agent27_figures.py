"""analysis.agent27_figures: labels, the cell table it reads, and a run on the committed outputs."""

from __future__ import annotations

import json

from analysis import agent27_figures as af


def test_label_drops_the_decimal_only_for_whole_percentages():
    assert [af.label(v) for v in (1.0, 0.075, 0.285, 0.0)] == ["100", "7.5", "28.5", "0"]


def test_rates_reads_the_base_variant_only():
    h = {"cells": [{"kind": "W-0", "task_cell": "observed-nonrec-far", "variant": "base", "rate": 0.075},
                   {"kind": "W-0", "task_cell": "observed-nonrec-far", "variant": "restated", "rate": 1.0}]}
    assert af.rates(h) == {("W-0", "observed-nonrec-far"): 0.075}


def test_run_on_committed_outputs(tmp_path):
    assert af.main(["--out-dir", str(tmp_path)]) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(af.OUTPUTS)
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert meta["config"] == {"h1h3_output": af.H1H3_OUTPUT, "h1h3_haiku_output": af.H1H3_HAIKU_OUTPUT,
                              "haiku_notes_output": af.HAIKU_NOTES_OUTPUT}


def test_the_figure_shows_the_counted_rates():
    luna = af.rates(json.loads((af.RESULTS / "persistgym_h1h3" / af.H1H3_OUTPUT / "h1h3.json")
                               .read_text(encoding="utf-8")))
    haiku = af.rates(json.loads((af.RESULTS / "persistgym_h1h3_haiku" / af.H1H3_HAIKU_OUTPUT / "h1h3.json")
                                .read_text(encoding="utf-8")))
    assert luna[("W-0", "observed-nonrec-far")] == 0.075      # 15 of 200 (paper, Table I)
    assert haiku[("W-0", "observed-nonrec-far")] == 0.0       # 0 of 200
    assert luna[("W-n-0", "observed-nonrec-far")] == 0.285    # 28.5% (paper, §IV)
    assert not any(k == "W-n-0" for k, _ in haiku)            # R8 dropped W-n-0
    notes = af.notes_rates(json.loads((af.RESULTS / "haiku_notes" / af.HAIKU_NOTES_OUTPUT
                                       / "notes.json").read_text(encoding="utf-8")))
    assert notes[("W-n-0", "observed-nonrec-far")] == 0.02    # R9: 4 of 200 (exploratory)
    assert notes[("W-n-0", "derived-nonrec-far")] == 0.045    # 9 of 200
    assert len(notes) == 8
