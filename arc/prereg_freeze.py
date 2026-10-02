"""The config freeze table in PREREG.md §7.1, read and compared with arc/config_freeze.json.

    uv run python -m arc.prereg_freeze                  # PREREG.md vs arc/config_freeze.json
    uv run python -m arc.prereg_freeze --prereg <file> --record <file>

The frozen PREREG.md lists in §7.1 the values the ARC path runs are bound to: each path
profile's config hash, the patch-series SHA-256 and the upstream pin (and the patched commit
and tree). The paid launcher (arc/run_path.py) refuses unless the freeze record it uses gives
exactly these values, so a record regenerated after the freeze cannot be used until §7.1
says so. The command above runs the same comparison on two files, with no git, network or
key: run it on a PREREG draft before it is frozen. Exit code 0 when they agree, 1 otherwise.

How the table is read (GitHub Markdown; nothing in the file is executed):
* Only the section whose heading is numbered 7.1 counts ("### 7.1 Path configs", "## §7.1"),
  up to the next heading of the same or a higher level. Exactly one such heading must exist.
* Fenced code blocks, HTML comments and blockquotes (PLAN quoted as written) are skipped. A
  table is a header row, a delimiter row (`|---|`) and its body rows; header rows give no
  values, and the outer pipes are optional.
* A body row's first cell says what the row gives, read without Markdown, case or
  punctuation: a profile label (`S0`, `**S3** (optional)`), "upstream" or "pin" for the pin,
  "patch series" for the series SHA-256, "patched commit" or "patched tree". The value is the
  hex string of the right length (64 digits for a hash, 40 for a commit or tree), in either
  case, anywhere in the row's other cells; shorter hex such as `4ca00e6` is not a value. Rows
  and tables may come in any order, or as one table.
* A row without such a string ("TBD", "none") gives no value; a row whose label is given two
  different values is ambiguous. Both are refusals for anything the record holds.

The record agrees with the table when every profile in the record has its hash there, no
profile the record lacks has one, and the series SHA-256 and the pin are given and equal.
The patched commit and tree are compared when the table lists them.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arc import apply_patches as ap
from arc import config_hash as freeze

SECTION = "7.1"
PREREG_PATH = ap.REPO_ROOT / "PREREG.md"
# Shared values a row can give: key -> (name in messages, hex digits, required).
ITEMS = {
    "series": ("patch-series SHA-256", 64, True),
    "pin": ("upstream pin", 40, True),
    "patched_commit": ("patched commit", 40, False),
    "patched_tree": ("patched tree", 40, False),
}

_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
_NUMBER_RE = re.compile(r"(?:section\s+)?§?\s*(\d+(?:\.\d+)*)\.?(?=\s|$)", re.IGNORECASE)
_DELIMITER_CELL_RE = re.compile(r":?-+:?")
_PROFILE_RE = re.compile(r"s\d+")
_HEX = {n: re.compile(rf"(?<![0-9a-fA-F])[0-9a-fA-F]{{{n}}}(?![0-9a-fA-F])") for n in (40, 64)}


class TableError(ValueError):
    pass


@dataclass
class FreezeTable:
    """What §7.1's tables give: per key (a profile label such as "S0", or a key of ITEMS) the
    distinct values its rows give, lowercased; an empty set for a row with no value."""
    values: dict[str, set[str]] = field(default_factory=dict)
    n_rows: int = 0


# ── Markdown ───────────────────────────────────────────────────────────


def _markdown_lines(text: str) -> list[str]:
    """The lines of `text`, with HTML comments and fenced code blocks blanked out (the line
    count stays, so blanked lines still separate what was around them)."""
    text = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text,
                  flags=re.DOTALL)
    out: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        m = _FENCE_RE.match(line)
        if fence is None:
            if m:
                fence = m.group(1)            # opens a code block
            out.append("" if m else line)
            continue
        if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence)
                and not line.strip().strip(fence[0])):
            fence = None                      # closes it: the same character, as long, alone
        out.append("")
    return out


def _heading(line: str) -> tuple[int, str | None] | None:
    """(level, section number or None) if `line` is an ATX heading."""
    m = _HEADING_RE.match(line)
    if m is None:
        return None
    title = re.sub(r"[*_`]", "", m.group(2) or "").strip()
    number = _NUMBER_RE.match(title)
    return len(m.group(1)), number.group(1) if number else None


def _section(text: str, number: str = SECTION) -> list[str]:
    """The lines of the one section numbered `number`, without its heading."""
    lines = _markdown_lines(text)
    starts = [(i, h[0]) for i, line in enumerate(lines)
              if (h := _heading(line)) is not None and h[1] == number]
    if not starts:
        raise TableError(f"PREREG.md has no section {number}")
    if len(starts) > 1:
        raise TableError(f"PREREG.md has {len(starts)} headings numbered {number}")
    ((start, level),) = starts
    body = []
    for line in lines[start + 1:]:
        h = _heading(line)
        if h is not None and h[0] <= level:
            break
        body.append(line)
    return body


def _cells(line: str) -> list[str]:
    s = line.strip().removeprefix("|")
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def _is_delimiter(line: str) -> bool:
    return "|" in line and all(_DELIMITER_CELL_RE.fullmatch(c) for c in _cells(line))


def _body_rows(lines: list[str]) -> Iterator[list[str]]:
    """The body rows of every table in `lines`, outside blockquotes, as lists of cells."""
    lines = ["" if ln.lstrip().startswith(">") else ln for ln in lines]
    i = 0
    while i + 1 < len(lines):
        if "|" in lines[i] and _is_delimiter(lines[i + 1]):
            i += 2
            while i < len(lines) and lines[i].strip() and "|" in lines[i]:
                yield _cells(lines[i])
                i += 1
        else:
            i += 1


# ── The table ──────────────────────────────────────────────────────────


def _key(label: str) -> str | None:
    """What a row whose first cell is `label` gives: a profile label, an ITEMS key or None."""
    words = re.findall(r"[a-z0-9]+", label.lower())
    if not words:
        return None
    if _PROFILE_RE.fullmatch(words[0]):
        return words[0].upper()
    ws = set(words)
    if "patched" in ws and "commit" in ws:
        return "patched_commit"
    if "patched" in ws and "tree" in ws:
        return "patched_tree"
    if ws & {"patch", "patches"} and "series" in ws:
        return "series"
    if ws & {"upstream", "pin", "pinned"}:
        return "pin"
    return None


def read_table(text: str) -> FreezeTable:
    """The values the tables of PREREG.md §7.1 give. Raises TableError when there is no single
    §7.1 or it has no table."""
    table = FreezeTable()
    for cells in _body_rows(_section(text)):
        table.n_rows += 1
        key = _key(cells[0])
        if key is None:
            continue
        digits = ITEMS[key][1] if key in ITEMS else 64
        found = {h.lower() for cell in cells[1:] for h in _HEX[digits].findall(cell)}
        table.values.setdefault(key, set()).update(found)
    if table.n_rows == 0:
        raise TableError(f"PREREG.md §{SECTION} has no table (quoted and code blocks do not "
                         "count)")
    return table


def _record_value(record: Mapping[str, Any], key: str) -> Any:
    if key == "series":
        return (record.get("patch_series") or {}).get("sha256")
    if key == "pin":
        return (record.get("upstream") or {}).get("pinned_commit")
    return record.get(key)


def _compare(name: str, want: Any, got: set[str] | None, *, required: bool) -> list[str]:
    """`got` is None when no row names the value, empty when a row names it without one."""
    if not got:
        return [f"§{SECTION} gives no {name}"] if required or got is not None else []
    if len(got) > 1:
        return [f"§{SECTION} gives more than one {name}: {', '.join(sorted(got))}"]
    if not isinstance(want, str) or not want:
        return [f"the freeze record has no {name}"]
    (value,) = got
    if value != want.lower():
        return [f"{name} is {want} in the freeze record but {value} in §{SECTION}"]
    return []


def problems(text: str, record: Mapping[str, Any]) -> list[str]:
    """How the freeze `record` disagrees with the config freeze table in PREREG.md §7.1
    (`text`); empty when they agree."""
    try:
        table = read_table(text)
    except TableError as e:
        return [str(e)]
    if not any(table.values.values()):
        return [(f"PREREG.md §{SECTION} has no filled config freeze table: it gives no "
                 "config hash, patch-series SHA-256 or pin")]
    out: list[str] = []
    profiles = record.get("profiles") or {}
    hashed = {k for k, v in table.values.items() if v and k not in ITEMS}
    for label in sorted({*profiles, *hashed}, key=lambda s: (len(s), s)):
        name = f"{label} config hash"
        if label not in profiles:
            out.append(f"§{SECTION} gives a config hash for {label}, but the freeze record "
                       f"has no profile {label}")
            continue
        out += _compare(name, (profiles[label] or {}).get("sha256"), table.values.get(label),
                        required=True)
    for key, (name, _, required) in ITEMS.items():
        out += _compare(name, _record_value(record, key), table.values.get(key),
                        required=required)
    return out


# ── Command line ───────────────────────────────────────────────────────


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--prereg", type=Path, default=PREREG_PATH)
    parser.add_argument("--record", type=Path, default=freeze.FREEZE_PATH)
    args = parser.parse_args(argv)
    try:
        text = args.prereg.read_text(encoding="utf-8")
        record = freeze.load_record(args.record)
    except (OSError, freeze.FreezeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    found = problems(text, record)
    if found:
        print(f"{args.prereg} §{SECTION} does not match {args.record}:", file=sys.stderr)
        for problem in found:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    listed = read_table(text).values
    print(f"{args.prereg} §{SECTION} matches {args.record}:")
    for label, entry in record["profiles"].items():
        print(f"  {label} config hash  {entry['sha256']}")
    for key, (name, _, _) in ITEMS.items():
        note = "" if listed.get(key) else "  (not listed in §7.1, so not compared)"
        print(f"  {name}  {_record_value(record, key)}{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
