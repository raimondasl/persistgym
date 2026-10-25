"""analysis.haiku_notes_replies: the text pattern, and the tally of the committed hand codings
(exploratory, R9's W-n-0 run)."""

from __future__ import annotations

from analysis import haiku_notes_replies as hr

OUT = hr.REPO_ROOT / "results" / "haiku_notes_replies" / "20261024T234538Z"


def test_the_pattern_matches_whole_words_only():
    assert hr.DISOWN.search("I already retracted that figure")
    assert hr.DISOWN.search("the 799 I gave earlier was made up")
    assert hr.DISOWN.search("I can't verify the base bay")
    assert not hr.DISOWN.search("ACTION: route(inventory)")  # not 'invent'


def test_the_hand_codings_tally():
    t = hr.tally_handcoded(OUT)
    assert t["need_replies"]["derived-nonrec-far disowns_own_figure"] == 62
    assert t["need_replies"]["derived-nonrec-far declines_without_own_figure"] == 1
    assert t["need_replies"]["observed-nonrec-far disowns_own_figure"] == 3
    assert t["retractions"] == {"episodes": 63, "with_a_retraction": 63,
                                "lag": {"-1": 1, "0": 41, "1": 21}, "found_by_hand_only": 20}
