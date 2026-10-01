import pytest

from arc.public import premise

TEXT = """Some text.

| Game | Std score | PA score | Gap | Std $ | PA $ | Std actions | PA actions | Human baseline actions |
|---|---|---|---|---|---|---|---|---|
| SB26 | 2.8 | 100 | 97.2 | 29.32 | 17.01 | 156 | 126 | 213 |
| WA30 | 16.1 | 43.3 | 27.2 | 294.71 | 241.41 | 2172 | 2556 | 1843 |
| LS20 | 10.7 | 5.4 | −5.3 | 43.70 | 63.11 | 271 | 629 | 776 |

**Observations**
"""


def test_parse_premise_table():
    rows = premise.parse_premise_table(TEXT)
    assert [r["game"] for r in rows] == ["SB26", "WA30", "LS20"]
    assert rows[2]["gap"] == pytest.approx(-5.3)   # unicode minus
    assert rows[1]["std_actions"] == 2172


def test_missing_header_raises():
    with pytest.raises(ValueError):
        premise.parse_premise_table("no table here")


def test_committed_background_table_has_25_games():
    rows = premise.load_premise_table()
    assert len(rows) == 25 and len({r["game"] for r in rows}) == 25
