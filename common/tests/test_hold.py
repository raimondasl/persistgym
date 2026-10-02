"""The hold after a COST_CAP ending (PREREG §0.3 line 12, §7.7): the record (common/hold.py),
the clearing line `cleared_hold: <run_id>` and the check that refuses a paid run while a hold
stands (common/approval.py). No network: each test repo's origin is a local bare repository
and git may use only the file transport (conftest). Every hold record here is in a temporary
folder, never next to the real paid-run lock."""

from __future__ import annotations

import json
import random
import re
import string
from pathlib import Path

import pytest

from common import approval, costs, hold, paidlock
from common.approval import (
    ALLOW_ENV,
    PaidCallsNotAllowed,
    clear_look_alikes,
    clearances_in,
    format_clear_line,
    holds_not_cleared,
    parse_clear_line,
)
from common.tests.gitrepo import (
    FROZEN_PREREG,
    commit_on_origin_only,
    decisions_text,
    git_in,
    guarded_repo,
    push_main,
    write_decisions,
)

REPO = Path(__file__).resolve().parents[2]
RUN = "20261009T120000Z-S0-ft09-s1"
OTHER = "20261009T150000Z-S4-sb26-s1"
VALID = f"cleared_hold: {RUN}"
CLEAR_TEMPLATE = "cleared_hold: <run_id>"


# --- the record ----------------------------------------------------------------------------

def _lock(tmp_path: Path) -> Path:
    folder = tmp_path / "gitdir"
    folder.mkdir(exist_ok=True)
    return folder / paidlock.lock_name(paidlock.PERSISTGYM)


def _place(lock: Path, run_id: str = RUN, **kw) -> dict:
    args = {"experiment": "arc_path", "reason": "ended COST_CAP at its harness cost guard "
            "of $120.00 list (D22's run guard)"}
    args.update(kw)
    return hold.place_hold(lock, run_id=run_id, **args)


def test_the_record_is_next_to_the_lock_and_names_run_experiment_reason_and_time(tmp_path):
    lock = _lock(tmp_path)
    assert hold.holds_path(lock) == lock.parent / hold.HOLDS_NAME
    assert hold.read_holds(lock) == []                     # no record: no hold
    record = _place(lock, what="arc_path: S0 on ft09, seed 1", approved_block="2-seed1")
    (line,) = hold.holds_path(lock).read_text(encoding="utf-8").splitlines()
    assert json.loads(line) == record
    assert {"run_id", "experiment", "reason", "placed_utc"} <= set(record)
    assert (record["run_id"], record["experiment"]) == (RUN, "arc_path")
    (h,) = hold.read_holds(lock)
    assert (h.run_id, h.line, h.record) == (RUN, 1, record)
    text = h.describe()
    assert "arc_path" in text and "S0 on ft09" in text and "COST_CAP" in text
    assert record["placed_utc"] in text
    assert not lock.exists()                               # the lock itself is untouched


def test_holds_are_only_appended(tmp_path):
    lock = _lock(tmp_path)
    _place(lock)
    _place(lock, OTHER, experiment="arc_pilot")
    _place(lock)                                           # the same run twice
    assert [h.run_id for h in hold.read_holds(lock)] == [RUN, OTHER, RUN]
    assert [h.line for h in hold.read_holds(lock)] == [1, 2, 3]


def test_a_torn_last_line_does_not_swallow_the_next_hold(tmp_path):
    lock = _lock(tmp_path)
    path = hold.holds_path(lock)
    path.write_text('{"run_id": "torn"', encoding="utf-8")   # no newline: a crash mid-write
    _place(lock)
    lines = path.read_text(encoding="utf-8").split("\n")
    assert lines[0] == '{"run_id": "torn"' and json.loads(lines[1])["run_id"] == RUN
    with pytest.raises(hold.HoldRecordError, match="line 1 .* is not a hold"):
        hold.read_holds(lock)                              # the torn line still refuses


@pytest.mark.parametrize("text, message", [
    ("garbage\n", "line 1 .* is not a hold"),
    ("[]\n", "line 1 .* is not a hold"),
    ('"run"\n', "line 1 .* is not a hold"),
    (f'{{"run_id": "{RUN}"}}\nnot json\n', "line 2 .* is not a hold"),
    ('{"experiment": "arc_path"}\n', "names run None"),
    ('{"run_id": 7}\n', "names run 7"),
    ('{"run_id": ""}\n', "names run ''"),
    ('{"run_id": "a run"}\n', "names run 'a run'"),
    ('{"run_id": "r/../x"}\n', "names run"),
    ('{"run_id": "r\\u00f8"}\n', "names run"),
])
def test_a_line_that_is_not_a_clearable_hold_refuses(tmp_path, text, message):
    """Reading never skips a line: a hold that cannot be read or cleared by a line stands
    until the record is fixed by hand."""
    lock = _lock(tmp_path)
    hold.holds_path(lock).write_text(text, encoding="utf-8")
    with pytest.raises(hold.HoldRecordError, match=message):
        hold.read_holds(lock)


def test_blank_lines_and_crlf_are_not_holds(tmp_path):
    lock = _lock(tmp_path)
    hold.holds_path(lock).write_bytes(
        b"\n" + json.dumps({"run_id": RUN}).encode() + b"\r\n\r\n  \n")
    assert [h.run_id for h in hold.read_holds(lock)] == [RUN]


def test_place_hold_writes_even_a_run_id_no_line_can_clear(tmp_path):
    """A hold is never skipped; one that no clearing line can name refuses until fixed."""
    lock = _lock(tmp_path)
    _place(lock, "a run id")
    with pytest.raises(hold.HoldRecordError, match="cannot name"):
        hold.read_holds(lock)


def test_the_run_id_rule_is_the_clearing_lines():
    assert hold.RUN_ID_RE.pattern == approval._TOKEN
    assert hold.COST_CAP == "COST_CAP"


# --- the clearing line ---------------------------------------------------------------------

@pytest.mark.parametrize("line", [VALID, VALID + "  ", VALID + "\r", VALID + " \t\r",
                                  "cleared_hold: a", "cleared_hold: x.y_z-1"])
def test_valid_clearing_lines(line):
    assert parse_clear_line(line) == line.rstrip()[len("cleared_hold: "):]
    assert format_clear_line(parse_clear_line(line)) == line.rstrip()


MALFORMED = [
    "", "cleared_hold:", "cleared_hold: ", CLEAR_TEMPLATE,
    " " + VALID, "    " + VALID, "\t" + VALID, "- " + VALID, "* " + VALID, "> " + VALID,
    "`" + VALID + "`", "**" + VALID + "**", "\ufeff" + VALID, "\u200b" + VALID,
    VALID + "\u200b", VALID + " | reason: ok", VALID + " (pending)", VALID + ",",
    VALID + " " + OTHER, VALID + "," + OTHER,
    VALID.replace("cleared_hold: ", "cleared_hold:"),
    VALID.replace("cleared_hold: ", "cleared_hold:  "),
    VALID.replace("cleared_hold: ", "cleared_hold:\t"),
    VALID.replace("cleared_hold: ", "cleared_hold:\u00a0"),
    VALID.replace("cleared_hold", "Cleared_hold"),
    VALID.replace("cleared_hold", "CLEARED_HOLD"),
    VALID.replace("cleared_hold", "cleared-hold"),
    VALID.replace("cleared_hold", "clear_hold"),
    VALID.replace("cleared_hold", "cleared_holds"),
    VALID.replace("cleared_hold", "approved_block"),
    VALID.replace(": ", " : "),
    VALID.replace(RUN, RUN.replace("-", " ")),
    VALID.replace(RUN, RUN + "/x"),
    VALID.replace(RUN, RUN + ";"),
    VALID.replace(RUN, "r\u00f8"),
    VALID.replace(RUN, "<" + RUN + ">"),
    VALID.replace(RUN, "'" + RUN + "'"),
]


@pytest.mark.parametrize("line", MALFORMED)
def test_malformed_clearing_lines_never_count(line):
    assert parse_clear_line(line) is None
    assert clearances_in(f"# log\n{line}\n") == set()


def _reference(line: str) -> str | None:
    """An independent reading of the clearing grammar (no regex)."""
    s = line.rstrip()
    prefix = "cleared_hold: "
    if not s.startswith(prefix):
        return None
    run_id = s[len(prefix):]
    token = set(string.ascii_letters + string.digits + "._-")
    return run_id if run_id and not set(run_id) - token else None


def test_clearing_grammar_fuzz_against_an_independent_reading():
    rng = random.Random(20261002)
    pool = (string.ascii_letters + string.digits + " ._-,|:;$+*`>\t\r"
            + "\u00a0\u200b\u2028\uff10\u0661\ufeff")
    accepted = rejected = 0
    for _ in range(4000):
        line = list(rng.choice([VALID, f"cleared_hold: {OTHER}", "cleared_hold: r"]))
        for _ in range(rng.randint(1, 3)):
            op, i = rng.randrange(3), rng.randrange(len(line) + 1)
            if op == 0:
                line.insert(i, rng.choice(pool))
            elif line and i < len(line):
                if op == 1:
                    del line[i]
                else:
                    line[i] = rng.choice(pool)
        line = "".join(line)
        got = parse_clear_line(line)
        assert got == _reference(line), line
        if got is None:
            rejected += 1
        else:
            accepted += 1
            assert not line[:1].isspace()
    assert accepted > 100 and rejected > 1000


HIDDEN = {
    "backtick fence": f"Proposed (not cleared):\n```\n{VALID}\n```\n",
    "tilde fence": f"~~~\n{VALID}\n~~~\n",
    "unclosed fence": f"```\n{VALID}\n",
    "HTML comment": f"<!--\n{VALID}\n-->\n",
    "comment opened mid-line": f"Draft <!-- not yet\n{VALID}\n-->\n",
    "after a lone CR that opens a fence": f"note\r```\n{VALID}\n```\n",
}


@pytest.mark.parametrize("body", HIDDEN.values(), ids=HIDDEN.keys())
def test_clearing_lines_in_code_blocks_or_comments_never_count(body):
    text = "# Decisions log\n\n" + body
    assert clearances_in(text) == set()
    n = text.split("\n").index(VALID) + 1
    assert n in clear_look_alikes(text, RUN)


def test_look_alikes_name_only_lines_about_that_run():
    text = "\n".join(["# log", f"- {VALID}", f"cleared_hold:{RUN}", VALID,
                      f"cleared_hold: {RUN}.2", f"cleared_hold: x{RUN}",
                      f"Note: {RUN} ended COST_CAP", f"approved_block: {RUN}"])
    assert clear_look_alikes(text, RUN) == [2, 3]
    assert clearances_in(text) == {RUN, f"{RUN}.2", f"x{RUN}"}
    assert approval.look_alikes(text, RUN) == [8]          # approvals keep their own keyword


def test_lines_split_only_on_newline():
    for sep in ("\x0c", "\u2028", "\x85"):
        assert clearances_in(f"# log\nnote{sep}{VALID}\n") == set()


# --- the check: holds_not_cleared ----------------------------------------------------------

@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")
    r = tmp_path / "repo"
    r.mkdir()
    guarded_repo(r, prereg=FROZEN_PREREG)
    return r


def _clear(repo: Path, *run_ids: str, push: bool = True, extra: str = "") -> None:
    """The researcher's merge of clearing lines for `run_ids` (with block 1-pilots kept)."""
    write_decisions(repo, decisions_text("1-pilots") + extra
                    + "".join(format_clear_line(r) + "\n" for r in run_ids))
    git_in(repo, "commit", "-q", "-am", f"clear {' '.join(run_ids) or 'nothing'}")
    if push:
        push_main(repo)


def test_no_hold_needs_no_fetch(repo, tmp_path, monkeypatch):
    def no_fetch(*a, **k):
        raise AssertionError("fetched with no hold recorded")
    monkeypatch.setattr(approval, "fetch_remote", no_fetch)
    assert holds_not_cleared(repo, _lock(tmp_path)) is None
    assert holds_not_cleared(repo, _lock(tmp_path), run_id=RUN) is None


def test_a_hold_refuses_naming_the_run_and_the_exact_line(repo, tmp_path):
    lock = _lock(tmp_path)
    _place(lock, what="arc_path: S0 on ft09, seed 1")
    why = holds_not_cleared(repo, lock)
    assert why.startswith(f"1 hold stands: run {RUN} (arc_path; arc_path: S0 on ft09")
    assert f"'cleared_hold: {RUN}' is not on origin/main, HEAD, the working tree" in why
    assert "merging this line into results/decisions.md on origin/main" in why
    assert "either stream, ARC or PersistGym" in why and "§7.7" in why
    assert str(hold.holds_path(lock)) in why
    _clear(repo, RUN)
    assert holds_not_cleared(repo, lock) is None


@pytest.mark.parametrize("where, missing", [
    ("working tree only", "origin/main, HEAD; present on the working tree"),
    ("committed, not merged", "origin/main; present on HEAD, the working tree"),
])
def test_a_clearing_line_counts_only_once_merged(repo, tmp_path, where, missing):
    lock = _lock(tmp_path)
    _place(lock)
    if where == "working tree only":
        write_decisions(repo, decisions_text("1-pilots") + VALID + "\n")
    else:
        _clear(repo, RUN, push=False)
    assert f"is not on {missing}" in holds_not_cleared(repo, lock)
    if where == "working tree only":
        git_in(repo, "commit", "-q", "-am", "clear")
    push_main(repo)
    assert holds_not_cleared(repo, lock) is None


@pytest.mark.parametrize("where", ["origin/main", "HEAD", "the working tree"])
def test_removing_the_clearing_line_anywhere_puts_the_hold_back(repo, tmp_path, where):
    lock = _lock(tmp_path)
    _place(lock)
    _clear(repo, RUN)
    assert holds_not_cleared(repo, lock) is None
    if where == "origin/main":     # a revocation merged elsewhere: seen after the fetch
        commit_on_origin_only(repo, decisions_text("1-pilots"), "revoke the clearance")
    elif where == "HEAD":
        write_decisions(repo, decisions_text("1-pilots"))
        git_in(repo, "commit", "-q", "-am", "revoke locally")
        write_decisions(repo, decisions_text("1-pilots") + VALID + "\n")
    else:
        write_decisions(repo, decisions_text("1-pilots"))
    why = holds_not_cleared(repo, lock)
    assert why is not None and re.search(f"is not on [^;]*{where}", why)


@pytest.mark.parametrize("hide", [lambda x: f"<!-- revoked\n{x}\n-->\n",
                                  lambda x: f"```\n{x}\n```\n",
                                  lambda x: f"- {x}\n"], ids=["comment", "fence", "list"])
def test_hiding_the_clearing_line_puts_the_hold_back_and_is_named(repo, tmp_path, hide):
    lock = _lock(tmp_path)
    _place(lock)
    _clear(repo, RUN)
    write_decisions(repo, decisions_text("1-pilots") + hide(VALID))
    why = holds_not_cleared(repo, lock)
    assert "is not on the working tree; present on origin/main, HEAD" in why
    assert "look-alike lines in the working tree: " in why


def test_two_holds_need_two_lines(repo, tmp_path):
    lock = _lock(tmp_path)
    _place(lock)
    _place(lock, OTHER, experiment="arc_pilot", reason="ended COST_CAP at its harness cost "
           "guard of $15.00 list (set at its planned spend)")
    why = holds_not_cleared(repo, lock)
    assert why.startswith(f"2 holds stand: run {RUN} (")
    assert f"; run {OTHER} (arc_pilot;" in why
    assert "one line per run" in why
    assert f"'cleared_hold: {RUN}'; 'cleared_hold: {OTHER}'. Each line" in why
    _clear(repo, OTHER)                                    # one cleared, one stands
    why = holds_not_cleared(repo, lock)
    assert why.startswith(f"1 hold stands: run {RUN} (") and OTHER not in why
    _clear(repo, OTHER, RUN)
    assert holds_not_cleared(repo, lock) is None


def test_one_line_clears_every_record_of_its_run_and_no_other(repo, tmp_path):
    lock = _lock(tmp_path)
    _place(lock)
    _place(lock)
    _clear(repo, f"{RUN}.2", f"x{RUN}", RUN.upper())       # look-alike run IDs
    assert f"run {RUN} (" in holds_not_cleared(repo, lock)
    _clear(repo, RUN)
    assert holds_not_cleared(repo, lock) is None


def test_a_run_may_not_reuse_the_run_id_of_a_run_that_placed_a_hold(repo, tmp_path):
    """Even once cleared: otherwise the old clearing line would clear the new run's hold."""
    lock = _lock(tmp_path)
    _place(lock)
    _clear(repo, RUN)
    assert holds_not_cleared(repo, lock, run_id=OTHER) is None
    why = holds_not_cleared(repo, lock, run_id=RUN)
    assert f"run ID '{RUN}' is that of a run that placed a hold" in why


def test_an_unreadable_record_refuses(repo, tmp_path):
    lock = _lock(tmp_path)
    hold.holds_path(lock).write_text("garbage\n", encoding="utf-8")
    assert "is not a hold" in holds_not_cleared(repo, lock)


def test_a_failed_fetch_refuses_while_a_hold_is_recorded(repo, tmp_path):
    lock = _lock(tmp_path)
    _place(lock)
    _clear(repo, RUN)
    assert holds_not_cleared(repo, lock) is None
    bare = repo.parent / "repo-origin.git"
    bare.rename(bare.with_name("moved.git"))
    why = holds_not_cleared(repo, lock)
    assert f"cannot check whether the researcher has cleared the hold of {RUN}" in why
    assert "git fetch origin main failed" in why


def test_a_missing_decisions_file_is_named(repo, tmp_path):
    lock = _lock(tmp_path)
    _place(lock)
    (repo / "results" / "decisions.md").unlink()
    assert "(file missing on the working tree)" in holds_not_cleared(repo, lock)


# --- require_paid_run: both launchers refuse while a hold stands ---------------------------

def _costs(tmp: Path) -> Path:
    p = tmp / "costs.csv"
    p.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    return p


def test_require_paid_run_refuses_while_a_hold_stands(repo, tmp_path):
    lock = _lock(tmp_path)
    c = _costs(tmp_path)

    def run(held, block="1-pilots"):
        return approval.require_paid_run(lock=held, approved_block=block,
                                         experiment="toggle_pilot", planned_usd=1.0,
                                         costs_path=c, repo=repo)
    with paidlock.paid_run_lock(lock, run_id="next-run", what="test",
                                stream=paidlock.PERSISTGYM) as info:
        held = paidlock.HeldLock(lock, info)
        assert run(held).approved_block == "1-pilots"
        _place(lock)
        with pytest.raises(PaidCallsNotAllowed, match=f"1 hold stands: run {RUN} .* "
                                                      f"'cleared_hold: {RUN}'"):
            run(held)
        with pytest.raises(PaidCallsNotAllowed, match="1 hold stands"):
            run(held, block="2-seed1")        # before the approval is even looked up
        _clear(repo, RUN)
        assert run(held).approved_block == "1-pilots"
    with (paidlock.paid_run_lock(lock, run_id=RUN, what="reused id",
                                 stream=paidlock.PERSISTGYM) as info,
          pytest.raises(PaidCallsNotAllowed, match="is that of a run that placed a hold")):
        run(paidlock.HeldLock(lock, info))


# --- the docs ------------------------------------------------------------------------------

def _fenced(text: str) -> list[str]:
    out, inside = [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            inside = not inside
        elif inside:
            out.append(line)
    return out


def test_decisions_md_documents_the_clearing_grammar_with_examples_that_cannot_parse():
    text = (REPO / "results" / "decisions.md").read_text(encoding="utf-8")
    head = text[:text.index("\n## 2026-")]                 # the note before the first entry
    assert "cleared_hold" in head
    examples = [x for x in _fenced(head) if "cleared_hold" in x]
    assert any(x.strip() == CLEAR_TEMPLATE for x in examples)
    for x in examples:
        assert parse_clear_line(x) is None
        assert parse_clear_line(x.strip()) is None         # not even without the indent


@pytest.mark.parametrize("doc", ["common/approval.py", "common/hold.py", "harnesses/DESIGN.md",
                                 "results/decisions.md", "arc/README.md"])
def test_docs_state_the_clearing_grammar(doc):
    text = (REPO / doc).read_text(encoding="utf-8")
    assert CLEAR_TEMPLATE in text and "COST_CAP" in text
