"""Every text file our code writes uses LF line ends on every platform (2026-10-19).

Git stores the repository's text files with LF (`.gitattributes`: `* text=auto eol=lf`), and
runs record sha256 hashes of files they read (costs.csv, meta.json). On Windows, Python's text
mode turns "\\n" into "\\r\\n" unless told otherwise, so a hash taken there would not match a
clone's. This test fails on any non-test write that leaves the line end to the platform:
`<path>.write_text(...)`, or `open`/`<path>.open`/`gzip.open`/`os.fdopen` in a text write
mode, without `newline=`. Byte writes (`write_bytes`, binary modes) are not affected; the G1
spot-check CSVs are written as bytes and keep their RFC 4180 CRLF on purpose.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ("common", "harnesses", "analysis", "persistgym", "arc", "statecarry")


def _is_test(p: Path) -> bool:
    return "tests" in p.parts or p.name.startswith("test_") or "upstream" in p.parts


def _mode(call: ast.Call, pos: int):
    for kw in call.keywords:
        if kw.arg == "mode":
            return kw.value.value if isinstance(kw.value, ast.Constant) else None
    if len(call.args) > pos and isinstance(call.args[pos], ast.Constant):
        return call.args[pos].value
    return None


def _platform_line_ends(call: ast.Call) -> bool:
    if any(kw.arg == "newline" for kw in call.keywords):
        return False
    f = call.func
    if isinstance(f, ast.Attribute) and f.attr == "write_text":
        return True
    if (isinstance(f, ast.Name) and f.id == "open") or (
            isinstance(f, ast.Attribute) and f.attr == "fdopen"):
        pos = 1
    elif isinstance(f, ast.Attribute) and f.attr == "open":
        base = f.value
        if isinstance(base, ast.Name) and base.id in ("os", "io", "tarfile", "zipfile"):
            return False
        pos = 1 if isinstance(base, ast.Name) and base.id in ("gzip", "bz2", "lzma") else 0
    else:
        return False
    m = _mode(call, pos)
    if not isinstance(m, str) or "b" in m or not any(c in m for c in "wax+"):
        return False
    gz = isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "gzip"
    return not (gz and "t" not in m)


def test_every_text_write_sets_its_line_end():
    found = []
    for pkg in PACKAGES:
        for p in sorted((ROOT / pkg).rglob("*.py")):
            if _is_test(p.relative_to(ROOT)):
                continue
            tree = ast.parse(p.read_text(encoding="utf-8"))
            found += [f"{p.relative_to(ROOT)}:{n.lineno}" for n in ast.walk(tree)
                      if isinstance(n, ast.Call) and _platform_line_ends(n)]
    assert found == [], "text writes without newline= (they write CRLF on Windows): " + ", ".join(found)


def test_the_ledger_and_run_metadata_are_written_with_lf(tmp_path):
    from common import costs, runmeta
    fields = {k: "x" for k in runmeta.REQUIRED} | {"config": {"a": 1}, "note": "two\nlines"}
    out = runmeta.write_meta(tmp_path / "run", git={"git_commit": "0" * 40, "git_dirty": False},
                             **fields)
    assert out.read_bytes().count(b"\n") > 3 and b"\r" not in out.read_bytes()
    ledger = tmp_path / "costs.csv"
    row = {c: "" for c in costs.COLUMNS}
    row.update(timestamp_utc="2026-10-19T00:00:00+00:00", run_id="r", milestone="M0",
               experiment=next(iter(costs.EXPERIMENT_PHASE)), cost_usd_list="0", n_calls="0")
    costs.append_row(row, ledger)
    assert b"\r" not in ledger.read_bytes()
