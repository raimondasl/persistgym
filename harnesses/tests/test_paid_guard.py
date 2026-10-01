"""The paid transport refuses to run without explicit approval, and logs what it spends.
No test here touches the network: the OpenAI client is replaced by a stub factory, and the
guard is checked to run before the factory is ever called."""

from __future__ import annotations

import csv
import os
from pathlib import Path

import httpx
import openai
import pytest

from common import approval, costs
from common.tests.gitrepo import (
    add_origin,
    approval_line,
    commit_on_origin_only,
    decisions_text,
    git_in,
    push_main,
    write_decisions,
)
from harnesses import cli
from harnesses.openai_transport import (
    ALLOW_ENV,
    BudgetExceeded,
    OpenAIResponsesTransport,
    PaidCallsNotAllowed,
)
from harnesses.pricing import UsageLedger, cost_usd
from harnesses.tests.conftest import prereg_repo

HARNESS_DIR = Path(__file__).resolve().parent.parent

# common/costs.py COLUMNS on main after the 2026-10-01 schema change (PR #9).
COLUMNS_2026_10_01 = [
    "timestamp_utc", "run_id", "milestone", "experiment", "cell_or_config",
    "model_requested", "model_returned", "provider", "api", "service_tier", "service_tier_served",
    "n_calls", "input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens",
    "reasoning_tokens", "latency_s",
    "cost_usd_list", "cost_usd_billed_est", "price_source_date", "git_commit", "notes",
]


class _Resp:
    def __init__(self, data):
        self.data = data

    def to_dict(self, mode="python"):
        return self.data


class _StubClient:
    def __init__(self, responses):
        self.sent, self._responses = [], list(responses)
        self.responses = self

    def create(self, **payload):
        self.sent.append(payload)
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return _Resp(r)


def _response(context="all_turns", tier="flex", inp=1_000_000, out=100_000):
    return {"model": "gpt-6-luna-2026-09-01", "service_tier": tier, "status": "completed",
            "reasoning": {"context": context, "effort": "medium", "mode": "standard"},
            "output": [], "usage": {"input_tokens": inp, "output_tokens": out,
                                    "input_tokens_details": {"cached_tokens": 0},
                                    "output_tokens_details": {"reasoning_tokens": 50_000}}}


@pytest.fixture
def repo(tmp_path):
    prereg_repo(tmp_path)
    p = tmp_path / "costs.csv"
    p.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    return tmp_path


def _make(repo, factory, **kw):
    args = {"model": "gpt-6-luna", "approved_block": "1-pilots", "experiment": "toggle_pilot",
            "planned_usd": 1.0, "costs_path": repo / "costs.csv", "repo": repo,
            "client_factory": factory, "sleep": lambda s: None}
    args.update(kw)
    return OpenAIResponsesTransport(**args)


def _factory(responses=()):
    built = []

    def factory(timeout):
        built.append(_StubClient(responses))
        return built[-1]
    return factory, built


@pytest.mark.parametrize("env, kw, msg", [
    (None, {}, ALLOW_ENV),
    ("0", {}, ALLOW_ENV),
    ("1", {"approved_block": None}, "approved-block"),
    ("1", {"approved_block": "  "}, "approved-block"),
    ("1", {"planned_usd": 0}, "planned"),
    ("1", {"planned_usd": -1}, "planned"),
    ("1", {"planned_usd": float("nan")}, "planned"),  # nan passes every `<` comparison
    ("1", {"planned_usd": float("inf")}, "planned"),
    ("1", {"planned_usd": None}, "planned"),
    ("1", {"experiment": "mystery"}, "budget phase"),
    ("1", {"planned_usd": 100.01}, "cap"),  # phase 0 cap is $100
])
def test_guard_refuses_before_building_a_client(repo, monkeypatch, env, kw, msg):
    if env is None:
        monkeypatch.delenv(ALLOW_ENV, raising=False)
    else:
        monkeypatch.setenv(ALLOW_ENV, env)
    factory, built = _factory()
    with pytest.raises(PaidCallsNotAllowed, match=msg):
        _make(repo, factory, **kw)
    assert built == []


def test_guard_requires_prereg(repo, monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")
    (repo / "PREREG.md").unlink()
    factory, built = _factory()
    with pytest.raises(PaidCallsNotAllowed, match="PREREG"):
        _make(repo, factory)
    assert built == []


def test_guard_requires_prereg_committed(tmp_path, monkeypatch):
    """PLAN §16.3: PREREG.md committed before any paid call. A draft in the working tree, a
    staged-but-uncommitted file or local edits to the committed file do not count. Nor does
    a commit that is not on origin/main: only the merged (frozen) PREREG unlocks paid calls.
    (This test used to accept the PREREG as soon as it was committed locally.)"""
    monkeypatch.setenv(ALLOW_ENV, "1")
    (tmp_path / "costs.csv").write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    factory, built = _factory()
    # not a git repo at all
    (tmp_path / "PREREG.md").write_text("Version: 0.1\n", encoding="utf-8")
    with pytest.raises(PaidCallsNotAllowed, match="not tracked"):
        _make(tmp_path, factory)
    # untracked draft in a repo (whose HEAD and origin/main approve the block)
    git_in(tmp_path, "init", "-q")
    write_decisions(tmp_path, decisions_text("1-pilots"))
    git_in(tmp_path, "add", "results/decisions.md")
    git_in(tmp_path, "commit", "-q", "-m", "approve")
    add_origin(tmp_path)
    push_main(tmp_path)
    with pytest.raises(PaidCallsNotAllowed, match="not tracked"):
        _make(tmp_path, factory)
    # staged, not committed
    git_in(tmp_path, "add", "PREREG.md")
    with pytest.raises(PaidCallsNotAllowed, match="not in the HEAD commit"):
        _make(tmp_path, factory)
    # committed but not merged: origin/main has no PREREG.md
    git_in(tmp_path, "commit", "-q", "-m", "prereg")
    with pytest.raises(PaidCallsNotAllowed, match="PREREG.md is not on origin/main"):
        _make(tmp_path, factory)
    # merged: accepted
    push_main(tmp_path)
    assert _make(tmp_path, factory).approval.prereg_version == "0.1"
    # committed, then edited locally
    (tmp_path / "PREREG.md").write_text("Version: 0.2\n", encoding="utf-8")
    with pytest.raises(PaidCallsNotAllowed, match="uncommitted changes"):
        _make(tmp_path, factory)
    assert len(built) == 1  # only the accepted transport built a client


def test_guard_requires_prereg_identical_to_origin_main(repo, monkeypatch):
    """PREREG.md in HEAD must be the one on origin/main. A committed amendment that is not
    merged refuses before any client is built, even with a valid approval."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, built = _factory()
    (repo / "PREREG.md").write_text("Version: 0.2\n", encoding="utf-8")
    git_in(repo, "commit", "-q", "-am", "amend prereg, not merged")
    with pytest.raises(PaidCallsNotAllowed, match="PREREG.md in HEAD differs from PREREG.md "
                                                  "on origin/main"):
        _make(repo, factory)
    assert built == []
    push_main(repo)
    assert _make(repo, factory).approval.prereg_version == "0.2"
    assert len(built) == 1


def test_guard_requires_merged_block_approval(repo, monkeypatch):
    """PLAN §16.2: a block spends only after the researcher's approval line is on origin/main,
    in HEAD and in the working tree. A line only in the working tree, one committed on a
    branch but not merged, a look-alike line or another block's line does not count, and
    removing the line anywhere revokes it. (The grammar and every place are covered in
    common/tests/test_approval.py; this checks that the transport builds no client.)"""
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, built = _factory()
    assert _make(repo, factory).approval.approved_block == "1-pilots"  # fixture approves it
    # another block's approval does not carry over
    with pytest.raises(PaidCallsNotAllowed, match="'2-seed1' is not approved"):
        _make(repo, factory, approved_block="2-seed1")
    # added to the working tree but not committed
    write_decisions(repo, decisions_text("1-pilots", "2-seed1"))
    with pytest.raises(PaidCallsNotAllowed, match="on origin/main, HEAD; present on the "
                                                  "working tree"):
        _make(repo, factory, approved_block="2-seed1")
    # committed on the checked-out branch, not merged to main
    git_in(repo, "add", "results/decisions.md")
    git_in(repo, "commit", "-q", "-m", "approve block 2")
    with pytest.raises(PaidCallsNotAllowed, match="on origin/main; present on HEAD"):
        _make(repo, factory, approved_block="2-seed1")
    # merged: accepted (the name is stripped like the CLI's)
    push_main(repo)
    assert _make(repo, factory, approved_block=" 2-seed1 ").approval.approved_block == "2-seed1"
    # deleted locally: an uncommitted revocation counts
    write_decisions(repo, decisions_text("1-pilots"))
    with pytest.raises(PaidCallsNotAllowed, match="on the working tree"):
        _make(repo, factory, approved_block="2-seed1")
    # revoked on main by a merge elsewhere, still in HEAD and the working tree
    write_decisions(repo, decisions_text("1-pilots", "2-seed1"))
    commit_on_origin_only(repo, decisions_text("1-pilots"), "revoke block 2")
    with pytest.raises(PaidCallsNotAllowed, match="on origin/main; present on HEAD"):
        _make(repo, factory, approved_block="2-seed1")
    (repo / "results" / "decisions.md").unlink()
    with pytest.raises(PaidCallsNotAllowed, match="file missing on the working tree"):
        _make(repo, factory)
    assert len(built) == 2  # only the two accepted transports built a client


@pytest.mark.parametrize("line", [
    "approved_block: 1-pilots",                      # the old grammar
    "- " + approval_line("1-pilots"),                # a list item is not the line
    approval_line("1-pilots-extra"),                 # a longer name
    approval_line("1-pilot"),                        # a prefix of the name
    approval_line("1-pilots").replace("approved_block: ", "approved_block:"),  # no space
    approval_line("1-pilots").replace(" | ", "|"),   # spacing
    approval_line("1-pilots").replace("approved_block", "Approved_block"),     # case
    approval_line("1-pilots") + " (pending)",
    "  " + approval_line("1-pilots"),                # indented
    "`" + approval_line("1-pilots") + "`",
    approval_line("1-pilots", max_usd="$1000"),
    approval_line("1-pilots", max_usd="0"),
    approval_line("1-pilots", ("toggle_pilot", "mystery")),
    approval_line("1-pilots", ("toggle_pilot", "toggle_pilot")),
])
def test_guard_approval_line_must_match_exactly(tmp_path, monkeypatch, line):
    monkeypatch.setenv(ALLOW_ENV, "1")
    prereg_repo(tmp_path, approved_blocks=())
    (tmp_path / "costs.csv").write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    write_decisions(tmp_path, f"# Decisions log\n\n{line}\n")
    git_in(tmp_path, "commit", "-q", "-am", "look-alike")
    push_main(tmp_path)
    factory, built = _factory()
    with pytest.raises(PaidCallsNotAllowed, match="no valid approval line"):
        _make(tmp_path, factory)
    assert built == []


def test_guard_approval_line_tolerates_crlf_and_trailing_spaces(tmp_path, monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")
    prereg_repo(tmp_path, approved_blocks=())
    (tmp_path / "costs.csv").write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    (tmp_path / "results" / "decisions.md").write_bytes(
        f"# Decisions — log\r\n\r\n{approval_line('1-pilots')}  \r\n".encode())
    git_in(tmp_path, "commit", "-q", "-am", "crlf")
    push_main(tmp_path)
    factory, _ = _factory()
    assert _make(tmp_path, factory).approval.approved_block == "1-pilots"


def test_guard_approval_needs_decisions_in_head(tmp_path, monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")
    prereg_repo(tmp_path)
    (tmp_path / "costs.csv").write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    git_in(tmp_path, "rm", "-q", "--cached", "results/decisions.md")
    git_in(tmp_path, "commit", "-q", "-m", "untrack decisions")
    factory, built = _factory()
    with pytest.raises(PaidCallsNotAllowed, match="file missing on HEAD"):
        _make(tmp_path, factory)
    assert built == []


def test_guard_refuses_when_main_cannot_be_fetched(repo, monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, built = _factory()
    git_in(repo, "remote", "set-url", "origin", str(repo.parent / "nowhere.git"))
    with pytest.raises(PaidCallsNotAllowed, match="git fetch origin main failed"):
        _make(repo, factory)
    # the remote ref is injectable (the default is origin/main)
    with pytest.raises(PaidCallsNotAllowed, match="git fetch backup main failed"):
        _make(repo, factory, approval_remote=approval.RemoteRef("backup", "main"))
    assert built == []


def test_guard_refuses_an_experiment_the_block_does_not_list(tmp_path, monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")
    prereg_repo(tmp_path, approved_blocks=())
    (tmp_path / "costs.csv").write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    write_decisions(tmp_path, decisions_text("1-pilots", experiments=("toggle_pilot",)))
    git_in(tmp_path, "commit", "-q", "-am", "approve the echo probe only")
    push_main(tmp_path)
    factory, built = _factory()
    with pytest.raises(PaidCallsNotAllowed, match="not for experiment 'replay_probe'"):
        _make(tmp_path, factory, experiment="replay_probe")
    assert built == []
    assert _make(tmp_path, factory).approval.experiments == ("toggle_pilot",)


def test_guard_counts_the_blocks_own_logged_spend(tmp_path, monkeypatch):
    """Block spend comes from the costs.csv rows the transport itself writes: after a run,
    the block has less room, and a run that would pass max_usd is refused."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    prereg_repo(tmp_path, approved_blocks=())
    (tmp_path / "costs.csv").write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    write_decisions(tmp_path, decisions_text("1-pilots", max_usd="1"))
    git_in(tmp_path, "commit", "-q", "-am", "approve $1")
    push_main(tmp_path)
    factory, built = _factory([_response()])
    t = _make(tmp_path, factory, planned_usd=1.0)
    t.send({"model": "gpt-6-luna", "input": [], "reasoning": {"context": "all_turns"}})
    row = t.finalize(run_id="r1", milestone="M0", cell_or_config="c")
    assert row["notes"].startswith(approval.spend_tag("1-pilots"))
    # list $0.15, billed (Flex) $0.075: the block has spent the billed $0.075 (it used to
    # count the larger, the list cost; PLAN's caps are in billed dollars, D23). The row keeps
    # both.
    rows = costs.read_rows(tmp_path / "costs.csv")
    assert float(rows[0]["cost_usd_list"]) == pytest.approx(0.15)
    assert float(rows[0]["cost_usd_billed_est"]) == pytest.approx(0.075)
    assert float(approval.block_spend("1-pilots", rows)) == pytest.approx(0.075)
    assert _make(tmp_path, factory, planned_usd=0.925).approval.block_spent_usd == (
        pytest.approx(0.075))
    with pytest.raises(PaidCallsNotAllowed, match="would exceed it by"):
        _make(tmp_path, factory, planned_usd=0.93)
    assert len(built) == 2


def test_guard_counts_logged_spend(repo, monkeypatch):
    """The phase cap counts billed spend: a Flex row (list $99.5, billed $49.75) leaves $50.25
    of phase 0's $100. Under the old measure, the larger of the two, it left $0.50."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    row = {c: "" for c in costs.COLUMNS}
    row.update(experiment="replay_probe", cost_usd_list="99.5", cost_usd_billed_est="49.75")
    costs.append_row(row, repo / "costs.csv")
    factory, _ = _factory()
    with pytest.raises(PaidCallsNotAllowed, match="cap"):
        _make(repo, factory, planned_usd=50.26)  # 100 - 49.75 - 50.26 < 0
    assert _make(repo, factory, planned_usd=50.25).approval.headroom_usd == pytest.approx(0)
    assert _make(repo, factory, planned_usd=0.6).approval.headroom_usd == pytest.approx(49.65)


def test_guard_counts_list_where_a_row_has_no_billed_estimate(repo, monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")
    row = {c: "" for c in costs.COLUMNS}
    row.update(experiment="replay_probe", cost_usd_list="99.5", cost_usd_billed_est="",
               notes="approved_block=1-pilots;")
    costs.append_row(row, repo / "costs.csv")
    factory, _ = _factory()
    with pytest.raises(PaidCallsNotAllowed, match="cap"):
        _make(repo, factory, planned_usd=0.6)  # 100 - 99.5 - 0.6 < 0
    a = _make(repo, factory, planned_usd=0.4).approval
    assert a.headroom_usd == pytest.approx(0.1) and a.block_spent_usd == pytest.approx(99.5)


def test_guard_refuses_a_row_with_no_cost(repo, monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")
    row = {c: "" for c in costs.COLUMNS}
    row.update(experiment="replay_probe", notes="approved_block=other;")
    costs.append_row(row, repo / "costs.csv")
    factory, built = _factory()
    with pytest.raises(PaidCallsNotAllowed, match="costs.csv line 2: no cost"):
        _make(repo, factory)
    assert built == []


def test_sends_logs_echo_and_appends_one_costs_row(repo, monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, built = _factory([_response(), _response(context="current_turn")])
    t = _make(repo, factory)
    payload = {"model": "gpt-6-luna", "input": [], "reasoning": {"context": "all_turns"}}
    t.send(payload)
    t.send(payload)
    assert built[0].sent == [payload, payload]
    assert [e["echoed_context"] for e in t.echo_log] == ["all_turns", "current_turn"]
    assert t.echo_log[0]["model_returned"] == "gpt-6-luna-2026-09-01"
    row = t.finalize(run_id="r1", milestone="M0", cell_or_config="echo-probe")
    assert t.finalize(run_id="r1", milestone="M0", cell_or_config="echo-probe") is None
    rows = costs.read_rows(repo / "costs.csv")
    assert len(rows) == 1 and rows[0]["run_id"] == "r1"
    assert rows[0]["model_returned"] == "gpt-6-luna-2026-09-01"
    assert rows[0]["service_tier"] == "flex" and rows[0]["n_calls"] == "2"
    assert "approved_block=1-pilots" in rows[0]["notes"]
    assert "context_mismatches=1" in rows[0]["notes"]
    # 1M input at $0.10 + 100k output at $0.50 = $0.15 list per call; flex halves it
    assert float(rows[0]["cost_usd_list"]) == pytest.approx(0.30)
    assert float(rows[0]["cost_usd_billed_est"]) == pytest.approx(0.15)
    assert row["experiment"] == "toggle_pilot"
    with (repo / "costs.csv").open(newline="", encoding="utf-8") as f:
        assert next(csv.reader(f)) == costs.COLUMNS


def test_stops_at_planned_spend(repo, monkeypatch):
    """The run stops before a call once its spend reaches the planned spend. Spend is measured
    like block spend and the phase caps: the billed estimate, on Flex half the list cost.
    (The larger of list and billed, the old measure, stopped this run after 2 calls.)"""
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, built = _factory([_response(inp=10_000_000)] * 5)  # $1.05 list, $0.525 billed
    t = _make(repo, factory, planned_usd=2.0)
    p = {"model": "gpt-6-luna", "input": [], "reasoning": {"context": "all_turns"}}
    for _ in range(4):
        t.send(p)
    with pytest.raises(BudgetExceeded, match=r"run spend \$2.1000 \(billed estimate\) "
                                             r"reached the planned \$2.00"):
        t.send(p)
    assert len(built[0].sent) == 4
    assert t.spent_usd == pytest.approx(2.10) and t.ledger.cost_usd_billed_est == (
        pytest.approx(2.10))
    assert t.ledger.cost_usd_list == pytest.approx(4.20)  # still logged


def test_a_run_cannot_spend_past_its_blocks_max_usd(tmp_path, monkeypatch):
    """A run planned at the block's whole max_usd stops when the block's spend, as the guard
    counts it (billed), reaches max_usd, plus at most the last call. The run stops on the
    same measure the guard counts, so a Flex run cannot log more than that against the
    block."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    prereg_repo(tmp_path, approved_blocks=())
    (tmp_path / "costs.csv").write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    write_decisions(tmp_path, decisions_text("1-pilots", max_usd="1"))
    git_in(tmp_path, "commit", "-q", "-am", "approve $1")
    push_main(tmp_path)
    factory, built = _factory([_response()] * 20)  # $0.15 list, $0.075 billed per call
    t = _make(tmp_path, factory, planned_usd=1.0)
    p = {"model": "gpt-6-luna", "input": [], "reasoning": {"context": "all_turns"}}
    with pytest.raises(BudgetExceeded):
        for _ in range(20):
            t.send(p)
    t.finalize(run_id="r1", milestone="M0", cell_or_config="c")
    spent = approval.block_spend("1-pilots", costs.read_rows(tmp_path / "costs.csv"))
    # 14 calls at $0.075 billed: $1.05, less than one call over the $1 (the old measure, the
    # list cost, stopped after 7)
    assert len(built[0].sent) == 14 and float(spent) == pytest.approx(1.05)
    with pytest.raises(PaidCallsNotAllowed, match="would exceed it"):
        _make(tmp_path, factory, planned_usd=0.01)


def test_retries_rate_limits_then_gives_up(repo, monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")
    req = httpx.Request("POST", "https://example.invalid/v1/responses")
    err = openai.RateLimitError("busy", response=httpx.Response(429, request=req), body=None)
    factory, built = _factory([err, err, _response()])
    t = _make(repo, factory, max_attempts=3)
    p = {"model": "gpt-6-luna", "input": [], "reasoning": {"context": "all_turns"}}
    assert t.send(p)["model"] == "gpt-6-luna-2026-09-01"
    assert len(built[0].sent) == 3 and t.ledger.n_calls == 1  # 429s are not billed
    factory, _ = _factory([err, err])
    t = _make(repo, factory, max_attempts=2)
    with pytest.raises(openai.RateLimitError):
        t.send(p)
    assert t.ledger.n_calls == 0


def test_refuses_unknown_model_and_wrong_payload_model(repo, monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")
    factory, _ = _factory([_response()])
    with pytest.raises(KeyError):
        _make(repo, factory, model="some-other-model")
    t = _make(repo, factory)
    with pytest.raises(ValueError):
        t.send({"model": "gpt-6.1-sol", "input": []})


def test_cli_refuses_without_env(monkeypatch, capsys):
    monkeypatch.delenv(ALLOW_ENV, raising=False)

    def no_client(*a, **k):
        raise AssertionError("must not build a client")
    monkeypatch.setattr(openai, "OpenAI", no_client)
    assert cli.main(["probe-echo", "--approved-block", "x", "--planned-usd", "1"]) == 2
    assert cli.main(["run", "--cell", "F-0", "--approved-block", "x", "--planned-usd", "1"]) == 2
    assert "refused" in capsys.readouterr().err


def test_cli_pilot_size_limit(monkeypatch, capsys):
    monkeypatch.setenv(ALLOW_ENV, "1")
    assert cli.main(["run", "--cell", "F-0", "--n", "2", "--approved-block", "x",
                     "--planned-usd", "1"]) == 2  # 2 templates x 8 task cells = 16 > 10
    assert "at most 10" in capsys.readouterr().err


def test_cli_pilot_must_use_pilot_split(monkeypatch, capsys):
    """PLAN §16.5: pilot templates come from a disjoint seed range, never the main split."""
    monkeypatch.setenv(ALLOW_ENV, "1")

    def no_transport(*a, **k):
        raise AssertionError("must refuse before building a transport")
    monkeypatch.setattr(cli, "_guarded_transport", no_transport)
    assert cli.main(["run", "--cell", "F-0", "--split", "main", "--task-cell",
                     "observed-nonrec-far", "--approved-block", "x", "--planned-usd", "1"]) == 2
    assert "--split pilot" in capsys.readouterr().err


@pytest.mark.parametrize("experiment", ["persistgym", "persistgym_validity"])
def test_cli_pilot_split_only_under_the_blinded_pilot_experiment(monkeypatch, capsys,
                                                                 experiment):
    """The reverse (PREREG §11): pilot templates are pilot data, so a run under another
    experiment (here with the default --split pilot) would commit per-arm outcomes on them
    unblinded. It is refused before any transport exists."""
    monkeypatch.setenv(ALLOW_ENV, "1")

    def no_transport(*a, **k):
        raise AssertionError("must refuse before building a transport")
    monkeypatch.setattr(cli, "_guarded_transport", no_transport)
    assert cli.main(["run", "--cell", "F-r", "--experiment", experiment, "--matrix", "d11",
                     "--n", "3", "--approved-block", "x", "--planned-usd", "1"]) == 2
    assert "pilot data" in capsys.readouterr().err


def test_costs_row_records_requested_and_served_tier(repo, monkeypatch):
    """`service_tier` is the requested tier; the served tier, cache writes and latency go
    into their own columns if common/costs.py has them, else into notes."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    resp = _response(tier="default")
    resp["usage"]["input_tokens_details"]["cache_write_tokens"] = 1000
    factory, _ = _factory([resp])
    t = _make(repo, factory)
    t.send({"model": "gpt-6-luna", "input": [], "service_tier": "flex",
            "reasoning": {"context": "all_turns"}})
    assert t.echo_log[0]["service_tier_requested"] == "flex"
    assert t.echo_log[0]["service_tier_returned"] == "default"
    row = t.finalize(run_id="r", milestone="M0", cell_or_config="c")
    assert row["service_tier"] == "flex"
    if "service_tier_served" in costs.COLUMNS:
        assert row["service_tier_served"] == "default" and row["cache_write_tokens"] == 1000
        assert row["latency_s"] != ""
    else:
        assert "service_tier_served=default" in row["notes"]
        assert "cache_write_tokens=1000" in row["notes"] and "latency_s=" in row["notes"]
    assert costs.read_rows(repo / "costs.csv")[0]["service_tier"] == "flex"
    # billed at the served (standard) tier: no flex discount
    assert float(row["cost_usd_billed_est"]) == pytest.approx(float(row["cost_usd_list"]))


def test_costs_row_fills_the_2026_10_01_columns_when_present(monkeypatch):
    monkeypatch.setattr(costs, "COLUMNS", COLUMNS_2026_10_01)
    ledger = UsageLedger("gpt-6-luna")
    resp = _response(tier="flex")
    resp["usage"]["input_tokens_details"]["cache_write_tokens"] = 7
    ledger.add(resp, requested_tier="flex", latency_s=2.0)
    ledger.add(resp, requested_tier="flex", latency_s=4.0)
    row = ledger.costs_row(timestamp_utc="t", run_id="r", milestone="M0",
                           experiment="toggle_pilot", cell_or_config="c", git_commit="g",
                           notes="approved_block=b")
    assert set(row) == set(COLUMNS_2026_10_01)
    assert (row["service_tier"], row["service_tier_served"]) == ("flex", "flex")
    assert row["cache_write_tokens"] == 14 and row["latency_s"] == "3.000"
    assert row["notes"] == "approved_block=b"


def test_unpriced_returned_model_is_still_logged(repo, monkeypatch):
    """A paid call whose returned model string has no price must not vanish from costs.csv
    (it used to raise KeyError after the call was made)."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    resp = {**_response(), "model": "gpt-6-luna"}
    odd = {**_response(), "model": "luna-experimental-2026"}
    factory, _ = _factory([resp, odd])
    t = _make(repo, factory, planned_usd=5.0)
    p = {"model": "gpt-6-luna", "input": [], "reasoning": {"context": "all_turns"}}
    t.send(p)
    t.send(p)
    assert t.ledger.n_calls == 2
    assert t.ledger.cost_usd_list == pytest.approx(0.30)  # both priced as gpt-6-luna
    row = t.finalize(run_id="r", milestone="M0", cell_or_config="c")
    assert "priced_as_requested=luna-experimental-2026x1" in row["notes"]
    assert costs.read_rows(repo / "costs.csv")[0]["n_calls"] == "2"


def test_harness_tests_cannot_reach_the_network():
    """conftest.no_network blocks outbound connections and DNS for every harness test."""
    import socket

    from harnesses.tests.conftest import NetworkBlocked
    with pytest.raises(NetworkBlocked):
        socket.create_connection(("api.openai.com", 443), timeout=1)
    with pytest.raises(NetworkBlocked):
        socket.getaddrinfo("api.openai.com", 443)
    with socket.socket() as s, pytest.raises(NetworkBlocked):
        s.connect(("203.0.113.1", 443))
    # the guard's `git fetch` runs in a subprocess: git itself may use only local paths
    assert os.environ["GIT_ALLOW_PROTOCOL"] == "file"


def test_no_key_handling_in_harness_code():
    """The SDK reads the key from the environment; our code never names or loads it."""
    for path in HARNESS_DIR.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert "OPENAI_API_KEY" not in src and "dotenv" not in src, path.name
        assert "api_key" not in src, path.name


def test_pricing():
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000,
             "input_tokens_details": {"cached_tokens": 400_000, "cache_write_tokens": 100_000}}
    # sol: 500k plain x $2 + 400k cached x $0.10 + 100k writes x $2 x 1.25 + 1M out x $10
    listed, billed = cost_usd("gpt-6.1-sol", usage, "flex")
    assert listed == pytest.approx(1.0 + 0.04 + 0.25 + 10.0)
    assert billed == pytest.approx(listed / 2)
    assert cost_usd("gpt-6.1-sol-2026-10-01", usage, "default")[1] == pytest.approx(listed)
    with pytest.raises(KeyError):
        cost_usd("gpt-6", usage, "flex")
