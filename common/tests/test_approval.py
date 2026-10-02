"""The approval line grammar, where the line must be (origin/main, HEAD, working tree), that
PREREG.md is the merged one, and the per-block spend limit (common/approval.py). No network:
each test repo's origin is a local bare repository and git may use only the file transport
(conftest)."""

from __future__ import annotations

import csv
import math
import random
import re
import string
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from common import approval, costs, paidlock
from common.approval import (
    ALLOW_ENV,
    PaidCallsNotAllowed,
    RemoteRef,
    block_spend,
    parse_line,
    require_paid_approval,
)
from common.tests.gitrepo import (
    DRAFT_PREREG,
    FROZEN_PREREG,
    add_origin,
    approval_line,
    commit_on_origin_only,
    decisions_text,
    git_in,
    git_out,
    guarded_repo,
    push_main,
    write_decisions,
)

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = "approved_block: <name> | experiments: <exp1>,<exp2>,... | max_usd: <amount>"
VALID = "approved_block: 1-pilots | experiments: toggle_pilot,replay_probe | max_usd: 76"


# --- grammar --------------------------------------------------------------------------------

@pytest.mark.parametrize("line, expected", [
    (VALID, ("1-pilots", ("toggle_pilot", "replay_probe"), "76")),
    ("approved_block: 2-seed1 | experiments: arc_path | max_usd: 0.50",
     ("2-seed1", ("arc_path",), "0.50")),
    ("approved_block: seed1.S0_S4 | experiments: ext_gemini_flex | max_usd: 132",
     ("seed1.S0_S4", ("ext_gemini_flex",), "132")),
    (VALID + "  ", ("1-pilots", ("toggle_pilot", "replay_probe"), "76")),   # Markdown spaces
    (VALID + "\r", ("1-pilots", ("toggle_pilot", "replay_probe"), "76")),   # CRLF file
    (VALID + " \t\r", ("1-pilots", ("toggle_pilot", "replay_probe"), "76")),
])
def test_valid_lines(line, expected):
    a = parse_line(line)
    assert a is not None and a.line == line.rstrip()
    assert (a.name, a.experiments, a.max_usd) == (expected[0], expected[1],
                                                  Decimal(expected[2]))


MALFORMED = [
    "",
    "approved_block: 1-pilots",                                       # the old grammar
    "approved_block: 1-pilots | experiments: toggle_pilot",           # no max_usd
    "approved_block: 1-pilots | max_usd: 76",                         # no experiments
    "approved_block: 1-pilots | max_usd: 76 | experiments: toggle_pilot",  # wrong order
    VALID + " | note: ok",                                            # an extra field
    VALID + " |",
    VALID + " (pending)",
    " " + VALID,                                                      # indented
    "    " + VALID,                                                   # code-block indent
    "\t" + VALID,
    "- " + VALID,                                                     # list item
    "* " + VALID,
    "> " + VALID,                                                     # quote
    "`" + VALID + "`",                                                # backticks
    "**" + VALID + "**",
    "\ufeff" + VALID,                                                 # BOM
    "\u200b" + VALID,                                                 # zero-width space
    VALID + "\u200b",                                                 # not whitespace
    VALID.replace("approved_block: ", "approved_block:  "),           # double spaces
    VALID.replace(" | ", "  | ", 1),
    VALID.replace(" | ", " |  ", 1),
    VALID.replace(" | ", "|", 1),
    VALID.replace(" | ", "\t|\t", 1),
    VALID.replace(" | ", " \u00a6 ", 1),                              # broken bar
    VALID.replace("approved_block: ", "approved_block:"),
    VALID.replace("approved_block: ", "approved_block:\u00a0"),       # no-break space
    VALID.replace("approved_block", "Approved_block"),                # case matters
    VALID.replace("experiments", "Experiments"),
    VALID.replace("max_usd", "MAX_USD"),
    VALID.replace("approved_block", "approved-block"),
    VALID.replace("experiments:", "experiment:"),
    VALID.replace("1-pilots", ""),                                    # name
    VALID.replace("1-pilots", "1 pilots"),
    VALID.replace("1-pilots", "1/pilots"),
    VALID.replace("1-pilots", "<name>"),
    VALID.replace("1-pilots", "pilots!"),
    VALID.replace("1-pilots", "pil\u00f8ts"),
    VALID.replace("1-pilots", "1-pilots;"),
    VALID.replace("toggle_pilot,replay_probe", ""),                   # experiments
    VALID.replace("toggle_pilot,replay_probe", "toggle_pilot,"),
    VALID.replace("toggle_pilot,replay_probe", ",toggle_pilot"),
    VALID.replace("toggle_pilot,replay_probe", "toggle_pilot,,replay_probe"),
    VALID.replace("toggle_pilot,replay_probe", "toggle_pilot, replay_probe"),
    VALID.replace("toggle_pilot,replay_probe", "toggle_pilot;replay_probe"),
    VALID.replace("toggle_pilot,replay_probe", "toggle_pilot,toggle_pilot"),  # a repeat
    VALID.replace("toggle_pilot,replay_probe", "mystery"),            # not an experiment
    VALID.replace("toggle_pilot,replay_probe", "Toggle_pilot"),
    VALID.replace("toggle_pilot,replay_probe", "ext"),
    VALID.replace("toggle_pilot,replay_probe", "*"),
    VALID.replace("toggle_pilot,replay_probe", "<exp1>,<exp2>,..."),
    *[VALID.replace("max_usd: 76", f"max_usd: {x}") for x in (     # amounts
        "", "0", "0.0", "00", "0.000", "-5", "+5", "5.", ".5", "1e3", "1E3", "inf", "nan",
        "Infinity", "$76", "76$", "76 USD", "1,000", "1_000", "76.5.1", "0x10", "7 6",
        "\uff17\uff16",            # fullwidth digits
        "\u0667\u0666",            # Arabic-Indic digits
        "9" * 400,                 # finite as a decimal, not as a float
        "<amount>",
    )],
]


@pytest.mark.parametrize("line", MALFORMED)
def test_malformed_lines_never_count(line):
    assert parse_line(line) is None


def _reference(line: str):
    """An independent reading of the grammar (string splitting, no regex)."""
    s = line.rstrip()
    parts = s.split(" | ")
    if len(parts) != 3:
        return None
    values = []
    for part, prefix in zip(parts, ("approved_block: ", "experiments: ", "max_usd: "),
                            strict=True):
        if not part.startswith(prefix):
            return None
        values.append(part[len(prefix):])
    name, exps, amount = values
    token = set(string.ascii_letters + string.digits + "._-")
    if not name or set(name) - token:
        return None
    exps = exps.split(",")
    if any(not e or set(e) - token for e in exps) or len(set(exps)) != len(exps):
        return None
    if not all(e in costs.EXPERIMENT_PHASE or e.startswith("ext_") for e in exps):
        return None
    whole, dot, frac = amount.partition(".")
    if not whole or set(whole) - set(string.digits):
        return None
    if dot and (not frac or set(frac) - set(string.digits)):
        return None
    value = Decimal(amount)
    if value <= 0 or not math.isfinite(float(value)):
        return None
    return name, tuple(exps), value


def test_grammar_fuzz_against_an_independent_reading():
    """Random edits of valid lines: the parser accepts exactly what the string-splitting
    reference accepts, with the same values, and a parsed line is the line as written."""
    rng = random.Random(20261001)
    pool = (string.ascii_letters + string.digits + " ._-,|:;$+*`>\t\r"
            + "\u00a0\u200b\u2028\uff10\u0661\ufeff")
    seeds = [VALID, approval_line("2-seed1", ("arc_path",), "0.5"),
             approval_line("x", ("ext_a", "persistgym"), "1000"),
             approval_line("a", ("arc_pilot",), "1")]
    accepted = rejected = 0
    for _ in range(4000):
        line = list(rng.choice(seeds))
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
        got, want = parse_line(line), _reference(line)
        assert (got and (got.name, got.experiments, got.max_usd)) == (want or None), line
        if got is not None:
            accepted += 1
            assert got.line == line.rstrip() and not line[:1].isspace()
        else:
            rejected += 1
    assert accepted > 100 and rejected > 1000  # both branches were exercised


def test_lines_split_only_on_newline():
    """A form feed or U+2028 inside a line must not start a new approval line."""
    for sep in ("\x0c", "\u2028", "\x1e", "\x85"):
        text = f"# log\nnote{sep}{VALID}\n"
        assert approval.approvals_in(text, "1-pilots") == set()
    assert len(approval.approvals_in(f"# log\r\n{VALID}\r\n", "1-pilots")) == 1


# --- code blocks and HTML comments ----------------------------------------------------------

HIDDEN = {
    "backtick fence": f"Proposed (not approved):\n```\n{VALID}\n```\n",
    "fence with info": f"```text\n{VALID}\n```\n",
    "tilde fence": f"~~~\n{VALID}\n~~~\n",
    "indented fence": f"   ```\n{VALID}\n   ```\n",
    "unclosed fence": f"```\n{VALID}\n",
    "a shorter fence does not close": f"````\n```\n{VALID}\n````\n",
    "the other fence character does not close": f"```\n~~~\n{VALID}\n```\n",
    "CRLF fence": f"```\r\n{VALID}\r\n```\r\n",
    "fence after a lone CR": f"note\r```\n{VALID}\n```\n",
    "HTML comment": f"<!--\n{VALID}\n-->\n",
    "comment opened mid-line": f"Draft <!-- not yet\n{VALID}\n-->\n",
    "unclosed comment": f"<!--\n{VALID}\n",
}

SHOWN = {
    "after a closed fence": f"```\nx\n```\n{VALID}\n",
    "after a closed comment": f"<!--\nx\n-->\n{VALID}\n",
    "one-line comment": f"<!-- note -->\n{VALID}\n",
    "comment marker in a code span": f"Write `<!--` as words.\n{VALID}\n",
    "backticks with a backtick info string are inline code": f"``` a`b\n{VALID}\n",
    "comment marker inside a fence": f"```\n<!--\n```\n{VALID}\n",
    "fence marker inside a comment": f"<!--\n```\n-->\n{VALID}\n",
    "4-space indent is not a fence": f"    ```\n{VALID}\n",
}


@pytest.mark.parametrize("body", HIDDEN.values(), ids=HIDDEN.keys())
def test_lines_in_code_blocks_or_html_comments_never_count(body):
    """A proposed or example line shown in a code block, or a line commented out, is not an
    approval; the refusal names it."""
    text = "# Decisions log\n\n" + body
    assert parse_line(VALID) is not None
    assert approval.approvals_in(text, "1-pilots") == set()
    n = text.split("\n").index(next(x for x in text.split("\n") if x.rstrip() == VALID)) + 1
    assert n in approval.look_alikes(text, "1-pilots")


@pytest.mark.parametrize("body", SHOWN.values(), ids=SHOWN.keys())
def test_lines_outside_code_blocks_and_comments_count(body):
    text = "# Decisions log\n\n" + body
    assert len(approval.approvals_in(text, "1-pilots")) == 1
    assert approval.look_alikes(text, "1-pilots") == []


# --- the docs never approve anything by example -------------------------------------------

def _fenced(text: str) -> list[str]:
    out, inside = [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            inside = not inside
        elif inside:
            out.append(line)
    return out


def test_decisions_md_documents_the_grammar_with_examples_that_cannot_parse():
    text = (REPO / "results" / "decisions.md").read_text(encoding="utf-8")
    # a note near the top, before the first dated entry
    assert text.index("How approvals are recorded") < text.index("\n## 2026-")
    examples = [x for x in _fenced(text) if "approved_block" in x]
    assert examples and any(x.strip() == TEMPLATE for x in examples)
    for x in examples:
        assert parse_line(x) is None
        assert parse_line(x.strip()) is None  # not even if someone removes the indent
    # The guard sees every line outside that code block: no unclosed fence or HTML comment
    # in the log hides the entries below it, where approval lines go.
    lines = text.split("\n")
    shown = approval.shown_lines(lines)
    fence = [i for i, x in enumerate(lines) if x.startswith("```")]
    assert len(fence) == 2
    hidden = [i + 1 for i, s in enumerate(shown) if not s]
    assert hidden == list(range(fence[0] + 2, fence[1] + 2))


@pytest.mark.parametrize("doc", ["common/approval.py", "harnesses/DESIGN.md",
                                 "results/decisions.md"])
def test_docs_state_the_same_grammar(doc):
    text = (REPO / doc).read_text(encoding="utf-8")
    assert TEMPLATE in text
    assert "[A-Za-z0-9._-]+" in text and "ext_" in text


# --- block spend ---------------------------------------------------------------------------

def _row(notes, listed="", billed="", experiment="toggle_pilot"):
    return {**{c: "" for c in costs.COLUMNS}, "experiment": experiment, "notes": notes,
            "cost_usd_list": listed, "cost_usd_billed_est": billed}


def test_block_spend_sums_billed_over_tagged_rows():
    """Block spend counts each tagged row's billed estimate. It used to count the larger of
    list and billed, which on Flex is the list cost, twice what is billed; PLAN's caps and
    forecasts are in billed dollars (D23), so max_usd is now read in billed dollars too."""
    rows = [
        _row("approved_block=1-pilots; context_mismatches=0", "0.30", "0.15"),  # Flex
        _row("approved_block=1-pilots; pilot", "1.00", "1.20"),   # billed above list
        _row("approved_block=1-pilots; arc", "0.40", ""),          # no billed: list
        _row("approved_block=1-pilots-extra; x", "50", "50"),      # another block
        _row("approved_block=2-seed1; x", "50", "50"),
        _row("approved_block=1-pilots", "50", "50"),               # no ';': not the tag
        _row("", "50", "50"),
    ]
    assert block_spend("1-pilots", rows) == Decimal("1.75")
    assert block_spend("pilots", rows) == 0
    assert block_spend("2-seed1", rows) == 50
    assert block_spend("1-pilots", [_row("approved_block=1-pilots;", "1.5e-05", "")]) == (
        Decimal("0.000015"))


def test_a_flex_row_counts_at_its_billed_estimate():
    """The transport's Flex row: list $0.30, billed $0.15. The block has spent $0.15."""
    row = _row("approved_block=1-pilots; context_mismatches=0", "0.300000", "0.150000")
    assert block_spend("1-pilots", [row]) == Decimal("0.15")
    assert approval.row_spend(row, 2) == Decimal("0.15")
    assert approval.spend_usd is costs.spend_usd  # one measure for the guard and the caps


def test_a_missing_billed_estimate_falls_back_to_list():
    row = _row("approved_block=1-pilots;", "0.40", "")
    assert block_spend("1-pilots", [row]) == Decimal("0.40")
    assert block_spend("1-pilots", [_row("approved_block=1-pilots;", "0.40", " ")]) == (
        Decimal("0.40"))  # whitespace is empty
    # 0 is an estimate, not a missing one: no fallback
    assert block_spend("1-pilots", [_row("approved_block=1-pilots;", "0.40", "0")]) == 0


def test_a_row_with_neither_cost_cannot_be_counted():
    """Before, a row with both costs empty counted as $0. Now it is unreadable: a run that
    logged no cost must not look free."""
    row = _row("approved_block=1-pilots;", "", "")
    with pytest.raises(ValueError, match="costs.csv line 2: no cost"):
        block_spend("1-pilots", [row])
    with pytest.raises(ValueError, match="costs.csv line 2: no cost"):
        approval.check_ledger([row])


@pytest.mark.parametrize("bad", ["abc", "nan", "inf", "-1", "1,5"])
def test_block_spend_refuses_unreadable_costs(bad):
    """The list cost is checked even though the billed estimate is what counts."""
    with pytest.raises(ValueError, match="costs.csv line 2"):
        block_spend("1-pilots", [_row("approved_block=1-pilots;", bad, "0")])
    with pytest.raises(ValueError, match="costs.csv line 2"):
        block_spend("1-pilots", [_row("approved_block=1-pilots;", "0", bad)])


# --- where the line must be ----------------------------------------------------------------

@pytest.fixture
def armed(monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")


def _costs(tmp: Path, *rows) -> Path:
    p = tmp / "costs.csv"
    p.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    for r in rows:
        costs.append_row(r, p)
    return p


def _require(repo: Path, costs_path: Path, **kw):
    args = {"approved_block": "1-pilots", "experiment": "toggle_pilot", "planned_usd": 1.0,
            "costs_path": costs_path, "repo": repo}
    args.update(kw)
    return require_paid_approval(**args)


@pytest.fixture
def repo(tmp_path, armed):
    r = tmp_path / "repo"
    r.mkdir()
    guarded_repo(r)
    return r


def test_accepted_on_main_head_and_working_tree(repo):
    a = _require(repo, _costs(repo.parent))
    assert (a.approved_block, a.experiments, a.max_usd) == (
        "1-pilots", ("toggle_pilot", "replay_probe", "persistgym_pilot"), 1000.0)
    assert a.block_spent_usd == 0 and a.block_headroom_usd == pytest.approx(999.0)


def test_missing_on_origin_main(tmp_path, armed):
    """Committed on the checked-out branch but never merged: refused."""
    repo = tmp_path / "repo"
    repo.mkdir()
    guarded_repo(repo, decisions=decisions_text(), push=True)   # main: no approval
    write_decisions(repo, decisions_text("1-pilots"))
    git_in(repo, "commit", "-q", "-am", "approve on a feature branch")
    with pytest.raises(PaidCallsNotAllowed, match=r"on origin/main; present on HEAD, the "
                                                  r"working tree"):
        _require(repo, _costs(tmp_path))
    push_main(repo)  # the researcher's merge
    assert _require(repo, _costs(tmp_path)).approved_block == "1-pilots"


def test_only_in_the_working_tree(tmp_path, armed):
    repo = tmp_path / "repo"
    repo.mkdir()
    guarded_repo(repo, decisions=decisions_text())
    write_decisions(repo, decisions_text("1-pilots"))
    with pytest.raises(PaidCallsNotAllowed, match="on origin/main, HEAD; present on the "
                                                  "working tree"):
        _require(repo, _costs(tmp_path))


@pytest.mark.parametrize("where", ["origin/main", "HEAD", "working tree"])
def test_removing_the_line_anywhere_revokes(repo, where):
    c = _costs(repo.parent)
    assert _require(repo, c)  # approved before the removal
    if where == "origin/main":
        # merged elsewhere; the local origin/main ref is stale until the guard fetches
        commit_on_origin_only(repo, decisions_text(), "revoke 1-pilots")
    elif where == "HEAD":
        write_decisions(repo, decisions_text())
        git_in(repo, "commit", "-q", "-am", "revoke locally")
        write_decisions(repo, decisions_text("1-pilots"))  # working tree still has it
    else:
        write_decisions(repo, decisions_text())
    with pytest.raises(PaidCallsNotAllowed, match=f"no valid approval line .* on .*{where}"):
        _require(repo, c)


def test_deleting_the_file_revokes(repo):
    (repo / "results" / "decisions.md").unlink()
    with pytest.raises(PaidCallsNotAllowed, match="file missing on the working tree"):
        _require(repo, _costs(repo.parent))


def test_a_changed_line_is_a_revocation_until_merged(repo):
    write_decisions(repo, decisions_text("1-pilots", max_usd="2000"))
    with pytest.raises(PaidCallsNotAllowed, match="differs between origin/main and the "
                                                  "working tree"):
        _require(repo, _costs(repo.parent))
    git_in(repo, "commit", "-q", "-am", "raise the limit")
    with pytest.raises(PaidCallsNotAllowed, match="differs between origin/main and HEAD, "
                                                  "the working tree"):
        _require(repo, _costs(repo.parent))
    push_main(repo)
    assert _require(repo, _costs(repo.parent)).max_usd == 2000.0


def test_two_different_lines_for_one_block_are_ambiguous(tmp_path, armed):
    repo = tmp_path / "repo"
    repo.mkdir()
    text = decisions_text("1-pilots") + approval_line("1-pilots", ("toggle_pilot",), "5") + "\n"
    guarded_repo(repo, decisions=text)
    with pytest.raises(PaidCallsNotAllowed, match="2 different approval lines"):
        _require(repo, _costs(tmp_path))
    # the same line twice is not ambiguous
    repo2 = tmp_path / "repo2"
    repo2.mkdir()
    guarded_repo(repo2, decisions=decisions_text("1-pilots", "1-pilots"))
    assert _require(repo2, _costs(tmp_path)).approved_block == "1-pilots"


def test_malformed_lines_refuse_and_are_named(tmp_path, armed):
    repo = tmp_path / "repo"
    repo.mkdir()
    bad = approval_line("1-pilots", ("toggle_pilot",), "$76")
    guarded_repo(repo, decisions=f"# Decisions log\n\n- {VALID}\n{bad}\n")
    with pytest.raises(PaidCallsNotAllowed, match="look-alike lines in the working tree: 3, 4"):
        _require(repo, _costs(tmp_path))


def test_a_proposed_line_in_a_code_block_is_not_an_approval(tmp_path, armed):
    """A gate entry that shows the proposed line in a code block, merged as a proposal, does
    not approve the block."""
    repo = tmp_path / "repo"
    repo.mkdir()
    text = ("# Decisions log\n\n## G0 proposal\nProposed approval line:\n\n```\n"
            + approval_line("1-pilots") + "\n```\n")
    guarded_repo(repo, decisions=text)
    with pytest.raises(PaidCallsNotAllowed, match=r"no valid approval line .* on origin/main, "
                                                  r"HEAD, the working tree; malformed or "
                                                  r"hidden .* working tree: 7"):
        _require(repo, _costs(tmp_path))


def test_commenting_the_line_out_revokes(repo):
    c = _costs(repo.parent)
    assert _require(repo, c)
    write_decisions(repo, "# Decisions log\n\n<!-- revoked\n" + approval_line("1-pilots")
                    + "\n-->\n")
    with pytest.raises(PaidCallsNotAllowed, match="no valid approval line .* on the working "
                                                  "tree; present on origin/main, HEAD"):
        _require(repo, c)


def test_block_name_must_match_the_grammar(repo):
    with pytest.raises(PaidCallsNotAllowed, match="must match"):
        _require(repo, _costs(repo.parent), approved_block="1 pilots")


# --- fetch ---------------------------------------------------------------------------------

def test_fetch_failure_refuses(repo):
    c = _costs(repo.parent)
    assert _require(repo, c)
    bare = repo.parent / "repo-origin.git"
    bare.rename(bare.with_name("moved.git"))  # origin unreachable
    with pytest.raises(PaidCallsNotAllowed, match="git fetch origin main failed"):
        _require(repo, c)


def test_no_origin_remote_refuses(repo):
    """The local origin/main ref is still there, but without a fetch it may be stale."""
    git_in(repo, "remote", "remove", "origin")
    git_in(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    with pytest.raises(PaidCallsNotAllowed, match="cannot check .* on origin/main"):
        _require(repo, _costs(repo.parent))


def test_origin_must_be_a_configured_remote(tmp_path, armed):
    """Given a name that is not a configured remote, `git fetch origin` reads a directory
    called origin. A local repository there must not stand in for origin/main."""
    repo = tmp_path / "repo"
    repo.mkdir()
    guarded_repo(repo, decisions=decisions_text())  # main: no approval
    write_decisions(repo, decisions_text("1-pilots"))
    git_in(repo, "commit", "-q", "-am", "approve on a branch")
    git_in(repo, "remote", "remove", "origin")
    fake = repo / "origin"
    fake.mkdir()
    git_in(fake, "init", "-q")
    write_decisions(fake, decisions_text("1-pilots"))
    git_in(fake, "add", ".")
    git_in(fake, "commit", "-q", "-m", "fake main")
    git_in(fake, "branch", "-M", "main")
    with pytest.raises(PaidCallsNotAllowed, match="no git remote named 'origin' is configured"):
        _require(repo, _costs(tmp_path))


def test_replace_refs_cannot_stand_in_for_main(tmp_path, armed):
    """A local `git replace` of origin/main's decisions.md blob is ignored."""
    repo = tmp_path / "repo"
    repo.mkdir()
    guarded_repo(repo, decisions=decisions_text())  # main: no approval
    old = git_out(repo, "rev-parse", "refs/remotes/origin/main:results/decisions.md").strip()
    write_decisions(repo, decisions_text("1-pilots"))
    git_in(repo, "add", "results/decisions.md")
    new = git_out(repo, "rev-parse", ":results/decisions.md").strip()
    git_in(repo, "replace", old, new)
    git_in(repo, "commit", "-q", "-m", "approve locally")
    shown = git_out(repo, "show", "refs/remotes/origin/main:results/decisions.md")
    assert approval.approvals_in(shown, "1-pilots")  # plain git shows the replacement
    with pytest.raises(PaidCallsNotAllowed, match="on origin/main; present on HEAD"):
        _require(repo, _costs(tmp_path))


def test_network_transports_are_off_in_tests(repo):
    git_in(repo, "remote", "set-url", "origin", "https://example.invalid/persistgym.git")
    with pytest.raises(PaidCallsNotAllowed, match="git fetch origin main failed"):
        _require(repo, _costs(repo.parent))


def test_remote_ref_is_injectable(repo):
    """The ARC launcher and tests can name another remote and branch."""
    c = _costs(repo.parent)
    other = RemoteRef("upstream", "release")
    with pytest.raises(PaidCallsNotAllowed, match="git fetch upstream release failed"):
        _require(repo, c, remote=other)
    git_in(repo, "remote", "add", "upstream", str(repo.parent / "repo-origin.git"))
    git_in(repo, "push", "-q", "upstream", "HEAD:refs/heads/release")
    assert _require(repo, c, remote=other).approved_block == "1-pilots"
    with pytest.raises(PaidCallsNotAllowed, match="invalid remote ref"):
        _require(repo, c, remote=RemoteRef("--upload-pack=x", "main"))


def test_fetch_timeout_refuses(repo, monkeypatch):
    real = approval._git

    def slow(r, *args, timeout=None):
        if args[:1] == ("fetch",):
            raise subprocess.TimeoutExpired(["git", "fetch"], timeout)
        return real(r, *args, timeout=timeout)
    monkeypatch.setattr(approval, "_git", slow)
    with pytest.raises(PaidCallsNotAllowed, match="timed out"):
        _require(repo, _costs(repo.parent))


# --- PREREG.md must be the merged (frozen) one ---------------------------------------------

PREREG_DIFFERS = "PREREG.md in HEAD differs from PREREG.md on origin/main"


def _commit_prereg(repo: Path, text: str, message: str = "amend prereg") -> None:
    (repo / "PREREG.md").write_text(text, encoding="utf-8")
    git_in(repo, "commit", "-q", "-am", message)


def test_prereg_committed_but_not_merged_refuses(repo):
    """A PREREG committed on a branch is not frozen until it is on origin/main."""
    c = _costs(repo.parent)
    assert _require(repo, c).prereg_version == "0.1"
    _commit_prereg(repo, "Version: 0.2\n")
    with pytest.raises(PaidCallsNotAllowed, match=f"merged to origin/main.*{PREREG_DIFFERS}"):
        _require(repo, c)
    push_main(repo)  # the researcher's merge
    assert _require(repo, c).prereg_version == "0.2"


def test_prereg_amended_on_main_but_not_in_head_refuses(repo):
    """An amendment merged elsewhere: HEAD's PREREG is stale. The guard compares with the
    freshly fetched origin/main, not the local ref from before."""
    c = _costs(repo.parent)
    assert _require(repo, c)
    commit_on_origin_only(repo, "Version: 0.2\n", "amend prereg on main", path="PREREG.md")
    with pytest.raises(PaidCallsNotAllowed, match=PREREG_DIFFERS):
        _require(repo, c)
    git_in(repo, "merge", "-q", "--ff-only", "origin/main")  # bring HEAD up to date
    assert _require(repo, c).prereg_version == "0.2"


def test_prereg_missing_on_main_refuses(tmp_path, armed):
    repo = tmp_path / "repo"
    repo.mkdir()
    git_in(repo, "init", "-q")
    write_decisions(repo, decisions_text("1-pilots"))
    git_in(repo, "add", "results/decisions.md")
    git_in(repo, "commit", "-q", "-m", "approve")
    add_origin(repo)
    push_main(repo)  # main: the approval, no PREREG
    (repo / "PREREG.md").write_text("Version: 0.1\n", encoding="utf-8")
    git_in(repo, "add", "PREREG.md")
    git_in(repo, "commit", "-q", "-m", "prereg on a branch")
    with pytest.raises(PaidCallsNotAllowed, match="PREREG.md is not on origin/main"):
        _require(repo, _costs(tmp_path))
    push_main(repo)
    assert _require(repo, _costs(tmp_path)).prereg_version == "0.1"


def test_prereg_differing_from_main_only_in_line_endings_refuses(repo):
    """The check compares blobs byte for byte: a PREREG committed with other line endings
    (CRLF for LF, or LF for CRLF) is not the one merged to main, even though it reads the
    same and records the same version. Normalising line endings before comparing would let
    it through."""
    c = _costs(repo.parent)
    p = repo / "PREREG.md"
    merged = p.read_bytes()  # as committed and pushed (write_text gives CRLF on Windows)
    flipped = (merged.replace(b"\r\n", b"\n") if b"\r\n" in merged
               else merged.replace(b"\n", b"\r\n"))
    assert flipped != merged and flipped.replace(b"\r", b"") == merged.replace(b"\r", b"")
    p.write_bytes(flipped)
    git_in(repo, "-c", "core.autocrlf=false", "commit", "-q", "-am", "line endings only")
    assert git_out(repo, "rev-parse", "HEAD:PREREG.md") != git_out(
        repo, "rev-parse", "refs/remotes/origin/main:PREREG.md")  # the blob keeps the bytes
    with pytest.raises(PaidCallsNotAllowed, match=PREREG_DIFFERS):
        _require(repo, c)
    push_main(repo)  # the CRLF file merged: now it is the frozen one
    assert _require(repo, c).prereg_version == "0.1"


def test_prereg_check_ignores_replace_refs(repo):
    """A local `git replace` of origin/main's commit cannot make HEAD's PREREG look merged."""
    c = _costs(repo.parent)
    _commit_prereg(repo, "Version: 0.2\n")
    main = git_out(repo, "rev-parse", "refs/remotes/origin/main").strip()
    git_in(repo, "replace", main, git_out(repo, "rev-parse", "HEAD").strip())
    assert git_out(repo, "rev-parse", "refs/remotes/origin/main:PREREG.md") == git_out(
        repo, "rev-parse", "HEAD:PREREG.md")  # plain git sees the replacement
    with pytest.raises(PaidCallsNotAllowed, match=PREREG_DIFFERS):
        _require(repo, c)


def test_prereg_check_reads_the_injected_remote(repo):
    c = _costs(repo.parent)
    other = RemoteRef("upstream", "release")
    git_in(repo, "remote", "add", "upstream", str(repo.parent / "repo-origin.git"))
    git_in(repo, "push", "-q", "upstream", "HEAD:refs/heads/release")
    _commit_prereg(repo, "Version: 0.2\n")
    push_main(repo)  # origin/main has 0.2; upstream/release still has 0.1
    assert _require(repo, c).prereg_version == "0.2"
    with pytest.raises(PaidCallsNotAllowed, match="differs from PREREG.md on upstream/release"):
        _require(repo, c, remote=other)


# --- require_paid_run: the lock, the last run's row and a frozen PREREG ----------------------

def test_prereg_not_frozen_reads_the_merged_text(repo):
    """The merged PREREG.md must be frozen too: the guard's own PREREG check accepts the
    fixture's 'Version: 0.1', which is not."""
    git_in(repo, "fetch", "-q", "origin")
    assert "PREREG.md is not frozen: version 0.1 is below 0.2" == (
        approval.prereg_not_frozen(repo))
    _commit_prereg(repo, FROZEN_PREREG)
    assert approval.prereg_not_frozen(repo) == PREREG_DIFFERS     # frozen, not merged yet
    push_main(repo)
    git_in(repo, "fetch", "-q", "origin")
    assert approval.prereg_not_frozen(repo) is None
    _commit_prereg(repo, DRAFT_PREREG)                               # a draft, merged
    push_main(repo)
    git_in(repo, "fetch", "-q", "origin")
    assert "not a release version" in approval.prereg_not_frozen(repo)


def test_require_paid_run_checks_the_lock_the_ledger_the_guard_and_a_frozen_prereg(
        tmp_path, armed):
    """In that order: no lock refuses before the ledger is read, a missing last-run row
    before the approval is looked up, and a draft only after the guard has passed."""
    repo = tmp_path / "repo"
    repo.mkdir()
    guarded_repo(repo, prereg=DRAFT_PREREG)
    c = _costs(tmp_path)
    lock = tmp_path / "lock" / paidlock.lock_name(paidlock.PERSISTGYM)
    lock.parent.mkdir()

    def run(held, block="1-pilots"):
        return approval.require_paid_run(lock=held, approved_block=block,
                                         experiment="toggle_pilot", planned_usd=1.0,
                                         costs_path=c, repo=repo)
    with pytest.raises(PaidCallsNotAllowed, match="need the paid-run lock"):
        run(None)
    with paidlock.paid_run_lock(lock, run_id="r", what="test",
                                stream=paidlock.PERSISTGYM) as info:
        held = paidlock.HeldLock(lock, info)
        with pytest.raises(PaidCallsNotAllowed, match="does not hold the paid-run lock"):
            run(paidlock.HeldLock(lock, {"token": "another run's"}))
        with pytest.raises(PaidCallsNotAllowed, match="not approved"):
            run(held, block="2-seed1")
        with pytest.raises(PaidCallsNotAllowed, match=r"frozen, merged PREREG.md \(PLAN "
                                                      r"§16.3\): PREREG.md is not frozen"):
            run(held)
        _commit_prereg(repo, FROZEN_PREREG)
        push_main(repo)
        assert run(held).prereg_version == "1.0"

        paidlock.record_last_run(lock, stream=paidlock.ARC, run_id="elsewhere-1",
                                 costs_csv=tmp_path / "x.csv")
        with pytest.raises(PaidCallsNotAllowed, match="elsewhere-1.*not in this checkout"):
            run(held, block="2-seed1")      # before the approval is even looked up
        c.write_text("timestamp_utc,run_id\n", encoding="utf-8")
        with pytest.raises(PaidCallsNotAllowed, match="cannot read .*costs.csv"):
            run(held)


# --- what the approval allows --------------------------------------------------------------

def test_experiment_must_be_listed(repo):
    with pytest.raises(PaidCallsNotAllowed, match="not for experiment 'persistgym'"):
        _require(repo, _costs(repo.parent), experiment="persistgym")
    assert _require(repo, _costs(repo.parent), experiment="persistgym_pilot")


def test_block_spend_limit(tmp_path, armed):
    """A Flex row (list $6, billed $3) uses $3 of the block's max_usd. Under the old measure,
    the larger of the two, it used $6 and the limit fell at planned $4."""
    repo = tmp_path / "repo"
    repo.mkdir()
    guarded_repo(repo, decisions=decisions_text("1-pilots", max_usd="10"))
    c = _costs(tmp_path,
               _row("approved_block=1-pilots; context_mismatches=0", "6.00", "3.00"),
               _row("approved_block=2-seed1; context_mismatches=0", "500", "500",
                    experiment="arc_path"))  # another block's spend does not count
    a = _require(repo, c, planned_usd=7.0)  # 3 + 7 = 10: exactly the limit
    assert a.block_spent_usd == 3.0 and a.block_headroom_usd == 0.0
    with pytest.raises(PaidCallsNotAllowed, match=r"spent \$3.00 of its max_usd \$10; "
                                                  r"planned \$7.01 would exceed it by \$0.01"):
        _require(repo, c, planned_usd=7.01)
    costs.append_row(_row("approved_block=1-pilots; x", "0.5", "0.6"), c)
    with pytest.raises(PaidCallsNotAllowed, match="exceed it"):
        _require(repo, c, planned_usd=7.0)
    assert _require(repo, c, planned_usd=6.4).block_spent_usd == pytest.approx(3.6)


@pytest.mark.parametrize("listed, billed, experiment, msg", [
    ("nan", "nan", "replay_probe", "is not a finite"),       # would switch off the cap
    ("99", "nan", "replay_probe", "is not a finite"),
    ("nan", "99", "replay_probe", "is not a finite"),
    ("-1000", "-1000", "replay_probe", "is not a finite"),   # would add headroom
    ("inf", "", "replay_probe", "is not a finite"),
    ("1,5", "", "replay_probe", "is not a number"),
    ("nan", "1", "replay_probe", "is not a finite"),         # list is checked, not counted
    ("", "", "replay_probe", "no cost"),                     # would count as free
    # finite as a Decimal, so check_ledger passes it, but infinite as the float the phase
    # cap sums: headroom raises, and the guard must turn that into a refusal
    ("", "1e400", "replay_probe", "is not a finite"),
    ("99", "99", "", "has no budget phase"),                 # would count toward no cap
    ("99", "99", "mystery", "has no budget phase"),
])
def test_every_costs_row_must_be_readable(tmp_path, armed, listed, billed, experiment, msg):
    """Rows of other blocks feed the phase-cap check: one unreadable row refuses, so it can
    neither switch the check off nor loosen it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    guarded_repo(repo)
    c = tmp_path / "costs.csv"
    c.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    with c.open("a", newline="", encoding="utf-8") as f:  # raw rows, as a hand edit would be
        csv.DictWriter(f, fieldnames=costs.COLUMNS).writerow(
            _row("approved_block=other;", listed, billed, experiment=experiment))
    with pytest.raises(PaidCallsNotAllowed, match=f"costs.csv line 2.*{msg}"):
        _require(repo, c, planned_usd=50.0)


def test_ext_rows_are_readable(tmp_path, armed):
    repo = tmp_path / "repo"
    repo.mkdir()
    guarded_repo(repo)
    c = _costs(tmp_path, _row("", "5", "5", experiment="ext_gemini_flex"))
    assert _require(repo, c).headroom_usd == pytest.approx(99.0)


def test_phase_cap_still_applies(tmp_path, armed):
    """A block limit above the phase cap does not lift the cap."""
    repo = tmp_path / "repo"
    repo.mkdir()
    guarded_repo(repo)  # max_usd 1000; phase 0 cap is $100
    with pytest.raises(PaidCallsNotAllowed, match="phase 0 cap"):
        _require(repo, _costs(tmp_path), planned_usd=100.01)


def test_refusal_message_shows_how_to_approve(tmp_path, armed):
    repo = tmp_path / "repo"
    repo.mkdir()
    guarded_repo(repo, decisions=decisions_text())
    with pytest.raises(PaidCallsNotAllowed) as e:
        _require(repo, _costs(tmp_path))
    assert re.search(r"merging a line 'approved_block: 1-pilots \| experiments: "
                     r"<exp1>,<exp2>,\.\.\. \| max_usd: <amount>'", str(e.value))
