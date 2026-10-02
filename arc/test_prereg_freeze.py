"""The PREREG §7.1 config freeze table (arc/prereg_freeze.py). The fixture
arc/testdata/prereg_section_7.md is §7 of PREREG v0.3-draft (all of §7.1 and §7.2 up to its
game table) as written on 2026-10-01, with the frozen values replaced by placeholders.
Nothing here reads git, the network or a key."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from arc import config_hash as freeze
from arc import prereg_freeze as pf

TEMPLATE = Path(__file__).resolve().parent / "testdata" / "prereg_section_7.md"
HEADER = "Version: 1.0\n\n**Status: Frozen on 2026-10-03 by the researcher.**\n\n"
OTHER64 = "9" * 64
OTHER40 = "8" * 40


def table_values(record) -> dict[str, str]:
    pin = record["upstream"]["pinned_commit"]
    return {**{label: e["sha256"] for label, e in record["profiles"].items()},
            "series": record["patch_series"]["sha256"], "pin": pin, "pin7": pin[:7],
            "commit": record["patched_commit"], "tree": record["patched_tree"]}


def prereg_text(record, *, header: str = HEADER, **values: str) -> str:
    """A PREREG.md whose §7 is the fixture, filled with `record`'s values or `values`."""
    template = TEMPLATE.read_text(encoding="utf-8")
    return header + template.format_map({**table_values(record), **values})


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


SAMPLE = {
    "upstream": {"pinned_commit": "a" * 40},
    "patch_series": {"sha256": _sha("series")},
    "patched_commit": "c" * 40,
    "patched_tree": "d" * 40,
    "profiles": {label: {"config_id": cid, "sha256": _sha(label)}
                 for label, cid in freeze.PROFILES.items()},
}


def _without_row(text: str, label: str) -> str:
    lines = text.split("\n")
    kept = [ln for ln in lines if not ln.startswith(f"| {label} |")]
    assert len(kept) == len(lines) - 1, label
    return "\n".join(kept)


# ── The draft's layout ─────────────────────────────────────────────────


def test_the_draft_layout_gives_every_value_once():
    table = pf.read_table(prereg_text(SAMPLE))

    assert table.values == {
        **{label: {_sha(label)} for label in ("S0", "S1", "S2", "S4")},
        "S3": set(),                         # "none: no profile is built or frozen"
        "pin": {"a" * 40}, "series": {_sha("series")},
        "patched_commit": {"c" * 40}, "patched_tree": {"d" * 40},
    }
    assert pf.problems(prereg_text(SAMPLE), SAMPLE) == []


def test_the_committed_record_in_the_draft_layout_agrees():
    record = freeze.load_record()
    assert pf.problems(prereg_text(record), record) == []


@pytest.mark.parametrize("key, value, message", [
    ("S0", OTHER64, f"S0 config hash is {_sha('S0')} in the freeze record but {OTHER64}"),
    ("S2", OTHER64.upper(), "S2 config hash is"),
    ("S4", OTHER64, "S4 config hash is"),
    ("series", OTHER64, "patch-series SHA-256 is"),
    ("pin", OTHER40, "upstream pin is"),
    ("commit", OTHER40, "patched commit is"),
    ("tree", OTHER40, "patched tree is"),
])
def test_a_different_value_is_named(key, value, message):
    (problem,) = pf.problems(prereg_text(SAMPLE, **{key: value}), SAMPLE)
    assert message in problem


def test_hex_case_does_not_matter():
    text = prereg_text(SAMPLE, S1=_sha("S1").upper(), pin=("a" * 40).upper())
    assert pf.problems(text, SAMPLE) == []


# ── Not filled ────────────────────────────────────────────────────────


@pytest.mark.parametrize("values, message", [
    ({"S1": "TBD"}, "§7.1 gives no S1 config hash"),
    ({"S1": _sha("S1")[:12]}, "§7.1 gives no S1 config hash"),      # a short prefix
    ({"series": ""}, "§7.1 gives no patch-series SHA-256"),
    ({"pin": "4ca00e6"}, "§7.1 gives no upstream pin"),
    ({"tree": "to be filled"}, "§7.1 gives no patched tree"),       # listed, so required
])
def test_an_unfilled_value_is_refused(values, message):
    assert message in pf.problems(prereg_text(SAMPLE, **values), SAMPLE)


def test_a_table_with_nothing_filled_is_refused():
    values = dict.fromkeys(table_values(SAMPLE), "TBD")
    assert pf.problems(prereg_text(SAMPLE, **values), SAMPLE) == [
        ("PREREG.md §7.1 has no filled config freeze table: it gives no config hash, "
         "patch-series SHA-256 or pin")]


@pytest.mark.parametrize("label, message", [
    ("S4", "§7.1 gives no S4 config hash"),
    ("Upstream harness", "§7.1 gives no upstream pin"),
    ("Patch-series SHA-256", "§7.1 gives no patch-series SHA-256"),
])
def test_a_missing_required_row_is_refused(label, message):
    text = _without_row(prereg_text(SAMPLE), label)
    assert pf.problems(text, SAMPLE) == [message]


def test_the_patched_commit_and_tree_are_compared_only_when_listed():
    text = _without_row(_without_row(prereg_text(SAMPLE), "Patched commit"), "Patched tree")
    assert pf.problems(text, SAMPLE) == []


@pytest.mark.parametrize("text, message", [
    (HEADER + "## 7. ARC path study\n\n| S0 | `" + "0" * 64 + "` |\n", "no section 7.1"),
    (HEADER + "### 7.10 Other\n\n| A | B |\n|---|---|\n| S0 | x |\n", "no section 7.1"),
    (HEADER + "### 7.1 Path configs\n\nNo table yet.\n\n### 7.2 Next\n", "has no table"),
    (HEADER + "### 7.1 Path configs\n\n> | Config | Hash |\n> |---|---|\n> | S0 | `"
     + _sha("S0") + "` |\n", "has no table"),
    (HEADER + "### 7.1 A\n\n| A | B |\n|---|---|\n### 7.1 B\n", "2 headings numbered 7.1"),
])
def test_no_single_table_in_section_7_1_is_refused(text, message):
    (problem,) = pf.problems(text, SAMPLE)
    assert message in problem


# ── What does not count ───────────────────────────────────────────────


IGNORED = f"""
> | Config | Hash |
> |---|---|
> | S0 | `{OTHER64}` |

```text
| Config | Hash |
|---|---|
| S1 | `{OTHER64}` |
### 7.2 A heading inside a code block ends nothing
```

<!--
| Config | Hash |
|---|---|
| S2 | `{OTHER64}` |
-->

~~~~
```
| Config | Hash |
|---|---|
| S4 | `{OTHER64}` |
~~~
## 8. Still inside the code block: a shorter fence does not close it
~~~~

"""

AFTER = f"""
| Config | Hash |
|---|---|
| S4 | `{OTHER64}` |
| Upstream harness | `{OTHER40}` |

## 8. StateCarry

| Config | Hash |
|---|---|
| S0 | `{OTHER64}` |
"""


def test_quotes_code_comments_and_other_sections_are_ignored():
    text = prereg_text(SAMPLE)
    marker = "Shared by all four configs:"
    assert text.count(marker) == 1
    text = text.replace(marker, IGNORED + marker) + AFTER

    assert pf.problems(text, SAMPLE) == []


UNFILLED = dict.fromkeys(("S0", "S1", "S2", "S4", "series", "pin", "pin7", "commit", "tree"),
                         "TBD")


def _filled_tables() -> str:
    """The fixture's two §7.1 tables with SAMPLE's values, as one block of lines."""
    text = prereg_text(SAMPLE)
    return text[text.index("| Config | Config entry name"):text.index("**Checks behind")]


def _unfilled_plus(old: str, new: str) -> str:
    """The fixture with §7.1's tables unfilled ("TBD"), and `old` replaced by `new`."""
    text = prereg_text(SAMPLE, **UNFILLED)
    assert text.count(old) == 1, old
    return text.replace(old, new)


def _indented(block: str) -> str:
    return "\n".join("    " + ln for ln in block.splitlines()) + "\n"


CHECKS = "**Checks behind"
GITHUB_SHOWS_NO_TABLE = {
    "setext heading ends 7.1": (
        ("### 7.2 Eligibility rule",
         "7.2 Eligibility rule\n--------------------\n\n" + _filled_tables()),
        "a line underlined with '=' or '-'"),
    "indented code block": (
        (CHECKS, "Filled, for example:\n\n" + _indented(_filled_tables()) + "\n" + CHECKS),
        "indented 4 or more spaces"),
    "lazy blockquote continuation": (
        ("(PLAN §16.4)\n\n**Operational**", "(PLAN §16.4)\n" + _filled_tables()
         + "\n**Operational**"),
        "directly after a blockquote"),
    "raw HTML block": (
        (CHECKS, "<pre>\n" + _filled_tables() + "</pre>\n\n" + CHECKS),
        "raw HTML"),
    "header and delimiter cell counts differ": (
        (CHECKS, _filled_tables().replace("|---|---|---|", "|---|---|") + "\n" + CHECKS),
        "header row has 3 cells but its delimiter row 2"),
    "a cell beyond the header": (
        ("| S0 | `google-gemini-3-8-flash-high` | `TBD` |",
         f"| S0 | `google-gemini-3-8-flash-high` | `TBD` | `{_sha('S0')}` |"),
        "more cells than its header (4 > 3"),
    "a paragraph line continues the table": (
        ("| Patched tree | `TBD` |\n", "| Patched tree | `TBD` |\nfilled below:\n"
         + _filled_tables().split("\n", 2)[2]),
        "a line directly after a table that is not a row"),
}


@pytest.mark.parametrize("edit, message", GITHUB_SHOWS_NO_TABLE.values(),
                         ids=GITHUB_SHOWS_NO_TABLE.keys())
def test_values_github_would_not_show_in_the_table_are_refused(edit, message):
    """Each edit puts the record's values where the reader would once have found them, but
    GitHub shows the unfilled table: refused, never read as a filled table."""
    (problem,) = pf.problems(_unfilled_plus(*edit), SAMPLE)
    assert message in problem


def test_an_html_comment_that_is_never_closed_is_refused():
    (problem,) = pf.problems(prereg_text(SAMPLE) + "\n<!-- a note\n", SAMPLE)
    assert "never closed" in problem


def test_backticks_in_a_backtick_fence_info_string_make_inline_code():
    """```` ```S0``` ```` is inline code: it opens no code block, so it cannot hide the
    unfilled table and expose a fenced example in its place."""
    text = _unfilled_plus("| Config | Config entry name",
                          "```S0``` is Standard.\n\n| Config | Config entry name")
    text = text.replace(CHECKS, "Not the values:\n\n```\n" + _filled_tables() + "```\n\n"
                        + CHECKS)
    assert pf.problems(text, SAMPLE) == [
        ("PREREG.md §7.1 has no filled config freeze table: it gives no config hash, "
         "patch-series SHA-256 or pin")]


def test_comment_markers_in_code_and_empty_comments():
    text = prereg_text(SAMPLE).replace(CHECKS, "```\n<!-- in code\n```\n\n<!-->\n\n" + CHECKS)
    assert pf.problems(text + "\n-->\n", SAMPLE) == []


def test_formatting_variations_are_read():
    h = {label: _sha(label) for label in ("S0", "S1", "S2", "S4")}
    text = "\r\n".join([
        "Version: 1.0", "",
        "## §7.1. Frozen configs", "",
        "Profile | SHA-256 | Config entry name",          # no outer pipes
        ":--- | :---: | ---:",
        f"**S0** | `{h['S0'].upper()}` | `google-gemini-3-8-flash-high`",
        f"`S1` | sha256: {h['S1']} | x",
        f"S2 | {h['S2']} \\| also given below | x",
        "S3 (optional) | none | none",
        "",
        "#### 7.1.1 Shared values",                       # a subsection stays in §7.1
        "",
        "|Item|Value|",
        "|-|-|",
        f"|Pinned commit|{'a' * 40} (`aaaaaaa`)|",
        f"|*Patch series* SHA-256|`{_sha('series')}`|",
        f"|Patched commit|`{'c' * 40}`|",
        "",
        "| More | Rows |",
        "|---|---|",
        f"| S2 (again, same value) | `{h['S2']}` |",
        f"| S4 = Provider Adapter | `{h['S4']}` |",
        "",
        "## 7.2 Next", "",
    ])

    assert pf.problems(text, SAMPLE) == []


# ── Ambiguity and extra profiles ──────────────────────────────────────


def test_two_values_for_one_label_are_ambiguous():
    text = prereg_text(SAMPLE).replace(
        "Shared by all four configs:",
        f"| Config | Hash |\n|---|---|\n| S1 | `{OTHER64}` |\n\nShared by all four configs:")

    (problem,) = pf.problems(text, SAMPLE)
    assert "more than one S1 config hash" in problem and OTHER64 in problem


def test_a_row_with_two_values_is_ambiguous():
    (problem,) = pf.problems(prereg_text(SAMPLE, pin=f"{'a' * 40}` or `{OTHER40}"), SAMPLE)
    assert "more than one upstream pin" in problem


def test_a_hash_for_a_profile_the_record_lacks_is_refused():
    text = prereg_text(SAMPLE).replace("| none; S3 runs only", f"| `{OTHER64}`; S3 runs only")

    assert pf.problems(text, SAMPLE) == [
        "§7.1 gives a config hash for S3, but the freeze record has no profile S3"]


def test_a_record_without_a_value_is_refused():
    record = json.loads(json.dumps(SAMPLE))
    del record["patch_series"]["sha256"]
    assert pf.problems(prereg_text(SAMPLE), record) == [
        "the freeze record has no patch-series SHA-256"]


# ── Command line ──────────────────────────────────────────────────────


def _record_file(tmp_path: Path) -> Path:
    path = tmp_path / "record.json"
    path.write_text(json.dumps(SAMPLE), encoding="utf-8")
    return path


def test_cli_agrees(tmp_path, capsys):
    prereg = tmp_path / "PREREG.md"
    prereg.write_text(_without_row(prereg_text(SAMPLE), "Patched tree"), encoding="utf-8")

    assert pf.main(["--prereg", str(prereg), "--record", str(_record_file(tmp_path))]) == 0

    out = capsys.readouterr().out
    assert "matches" in out and _sha("S4") in out
    assert "patched tree  " + "d" * 40 + "  (not listed in §7.1, so not compared)" in out


def test_cli_lists_the_disagreements(tmp_path, capsys):
    prereg = tmp_path / "PREREG.md"
    prereg.write_text(prereg_text(SAMPLE, S0=OTHER64, series="TBD"), encoding="utf-8")

    assert pf.main(["--prereg", str(prereg), "--record", str(_record_file(tmp_path))]) == 1

    err = capsys.readouterr().err
    assert "does not match" in err
    assert "S0 config hash is" in err and "gives no patch-series SHA-256" in err


def test_cli_refuses_a_missing_file(tmp_path, capsys):
    missing = tmp_path / "PREREG.md"
    assert pf.main(["--prereg", str(missing), "--record", str(_record_file(tmp_path))]) == 1
    assert "ERROR" in capsys.readouterr().err


# ── The repository's own PREREG.md ────────────────────────────────────


@pytest.mark.skipif(not pf.PREREG_PATH.exists(), reason="PREREG.md is not merged yet")
def test_the_repository_prereg_table_matches_the_committed_record():
    """Once PREREG.md is in the repository, its §7.1 table and arc/config_freeze.json change
    together (amendment A-cfg), or the paid launcher refuses every ARC run."""
    text = pf.PREREG_PATH.read_text(encoding="utf-8")
    assert pf.problems(text, freeze.load_record()) == []
