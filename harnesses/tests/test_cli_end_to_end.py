"""The paid CLI paths end to end, with no network: the real guarded transport is built with
a stub client whose `responses.create` is answered by the fake model. This checks that a paid
run would write its results, meta.json and exactly one costs.csv row per run, before any
money is spent on finding out, and that it holds the paid-run lock (a temporary file here,
never the shared one) and leaves it held when its spend is not in costs.csv."""

from __future__ import annotations

import gzip
import json

import pytest

from common import costs, paidlock, runmeta
from common.tests.gitrepo import DRAFT_PREREG, git_in, push_main
from harnesses import blinding, cli, runner
from harnesses.fake import FakeModel
from harnesses.openai_transport import ALLOW_ENV, OpenAIResponsesTransport
from harnesses.tests.conftest import prereg_repo


class _Obj:
    def __init__(self, data):
        self.data = data

    def to_dict(self, mode="python"):
        return self.data


class _FakeBackedClient:
    def __init__(self, fake):
        self.fake = fake
        self.responses = self

    def create(self, **payload):
        return _Obj(self.fake.send(payload))


@pytest.fixture
def paid_env(tmp_path, monkeypatch):
    """The CLI's own `_guarded_transport` builds the real transport, pointed at this test's
    repo and costs.csv, with a fake-backed client. The paid-run lock is `cli.LOCK_PATH`, a
    file in its own folder (the last-run record goes next to it)."""
    prereg_repo(tmp_path)
    costs_csv = tmp_path / "costs.csv"
    costs_csv.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    monkeypatch.setenv(ALLOW_ENV, "1")
    monkeypatch.setattr(cli, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(cli, "RAW", tmp_path / "raw")
    (tmp_path / "lock").mkdir()
    monkeypatch.setattr(cli, "LOCK_PATH", tmp_path / "lock" / paidlock.LOCK_NAME)
    fakes = []

    def turn(payload):  # 0-based turn within one probe conversation
        return sum(1 for i in payload["input"] if i.get("role") == "user") - 1

    def transport(**kw):
        fake = FakeModel(lambda p, i: ["ready", "Paris", "427"][min(turn(p), 2)],
                         reasoning_summary_fn=lambda p, tag: "Picked 427." if turn(p) == 0
                         else "")
        fakes.append(fake)
        return OpenAIResponsesTransport(
            **kw, costs_path=costs_csv, repo=tmp_path,
            client_factory=lambda timeout: _FakeBackedClient(fake))
    monkeypatch.setattr(cli, "OpenAIResponsesTransport", transport)
    return tmp_path, costs_csv, fakes


def test_probe_echo_cli(paid_env):
    tmp, costs_csv, fakes = paid_env
    assert cli.main(["probe-echo", "--approved-block", "1-pilots", "--planned-usd", "0.5",
                     "--run-id", "echo"]) == 0
    rows = costs.read_rows(costs_csv)
    assert [r["run_id"] for r in rows] == ["echo-gpt-6.1-sol", "echo-gpt-6-luna"]
    assert all(r["experiment"] == "toggle_pilot" and r["n_calls"] == "4" for r in rows)
    meta = json.loads((tmp / "results" / "toggle_pilot" / "echo-gpt-6-luna" / "meta.json")
                      .read_text(encoding="utf-8"))
    assert set(runmeta.REQUIRED) <= set(meta)
    assert meta["exit_reason"] == "COMPLETED"
    assert meta["reasoning_context_echoed"] == {"all_turns": 2, "current_turn": 2}
    assert meta["cost_usd"]["costs_csv_row_appended"] is True
    assert len(fakes) == 2 and len(fakes[0].calls) == 4


def test_probe_planned_usd_is_a_total_over_models(paid_env, monkeypatch, capsys):
    """--planned-usd caps the whole command: the second model gets what the first left, and
    is refused once the total is used up (it used to get the full amount again)."""
    _, costs_csv, _ = paid_env
    planned, real = [], cli._guarded_transport

    def spy(a, model, experiment, planned_usd, held):
        planned.append(planned_usd)
        return real(a, model, experiment, planned_usd, held)
    monkeypatch.setattr(cli, "_guarded_transport", spy)
    assert cli.main(["probe-echo", "--approved-block", "1-pilots", "--planned-usd", "0.5",
                     "--run-id", "e"]) == 0
    # spend is measured like block spend: the billed estimate (Flex: half the list cost; the
    # split used to subtract the list cost, the larger of the two)
    row = costs.read_rows(costs_csv)[0]
    first = float(row["cost_usd_billed_est"])
    assert float(row["cost_usd_list"]) > first  # Flex: list would over-count the spend
    assert first > 0 and planned == [0.5, pytest.approx(0.5 - first)]
    # a total smaller than one model's spend: the first model stops at the cap
    # (BudgetExceeded) and the second is refused
    planned.clear()
    tiny = first / 10
    assert cli.main(["probe-echo", "--approved-block", "1-pilots", "--planned-usd",
                     str(tiny), "--run-id", "t"]) == 2
    assert planned == [tiny] and "used up" in capsys.readouterr().err


def test_probe_replay_cli(paid_env):
    tmp, costs_csv, _ = paid_env
    assert cli.main(["probe-replay", "--model", "gpt-6.1-sol", "--n", "2", "--approved-block",
                     "1-pilots", "--planned-usd", "2", "--run-id", "rp"]) == 0
    trials = [json.loads(x) for x in (tmp / "results" / "replay_probe" / "rp" / "trials.jsonl")
              .read_text(encoding="utf-8").splitlines()]
    assert len(trials) == 4 and all(t["score"]["match"] for t in trials)
    with gzip.open(tmp / "raw" / "replay_probe" / "rp" / "transcript.jsonl.gz", "rt",
                   encoding="utf-8") as f:
        assert len(f.readlines()) == 4
    assert costs.read_rows(costs_csv)[0]["n_calls"] == "12"


def test_run_cli(paid_env):
    tmp, costs_csv, fakes = paid_env
    assert cli.main(["run", "--cell", "W-n-0", "--model", "gpt-6-luna", "--n", "1",
                     "--task-cell", "observed-nonrec-far", "derived-rec-near",
                     "--gen-set", "W_tokens=6400", "--gen-set", "v_tokens=400",
                     "--gen-set", "assumed_max_reply_tokens=200",
                     "--approved-block", "1-pilots", "--planned-usd", "1", "--run-id", "r"]) == 0
    meta = json.loads((tmp / "results" / "persistgym_pilot" / "r" / "meta.json")
                      .read_text(encoding="utf-8"))
    assert meta["exit_reason"] == "COMPLETED" and meta["paid"] is True
    assert meta["n_episodes_run"] == 2 and meta["cost_usd"]["costs_csv_row_appended"]
    (row,) = costs.read_rows(costs_csv)
    assert row["cell_or_config"] == "W-n-0" and row["experiment"] == "persistgym_pilot"
    assert int(row["n_calls"]) == len(fakes[0].calls) > 0
    assert "context_mismatches=0" in row["notes"]
    # pilot blinding (PREREG §11): no per-arm reasoning tokens in committed files
    assert row["reasoning_tokens"] == "" and blinding.WITHHELD_NOTE in row["notes"]
    assert int(row["output_tokens"]) > 0 and float(row["cost_usd_billed_est"]) > 0
    assert meta["tokens"]["reasoning_tokens"] is None
    committed = sorted(p.name for p in (tmp / "results" / "persistgym_pilot").rglob("*")
                       if p.is_file())
    assert committed == ["meta.json", "summary.json"]
    assert (tmp / "raw" / "persistgym_pilot" / "r" / "episodes.jsonl").exists()
    assert meta["config"]["run_matrix"]["name"] == "full"


def test_probe_rows_keep_reasoning_tokens(paid_env):
    """The echo and replay probes are toggle checks, exempt from pilot blinding (D29)."""
    _, costs_csv, _ = paid_env
    assert cli.main(["probe-echo", "--model", "gpt-6-luna", "--approved-block", "1-pilots",
                     "--planned-usd", "0.5", "--run-id", "e"]) == 0
    (row,) = costs.read_rows(costs_csv)
    assert int(row["reasoning_tokens"]) > 0 and blinding.WITHHELD_NOTE not in row["notes"]


def test_run_cli_d11_matrix(paid_env):
    """D11: derived-far on T_d templates, observed-far on the first T_o of them."""
    tmp, costs_csv, _ = paid_env
    small = ["--gen-set", "W_tokens=6400", "--gen-set", "v_tokens=400",
             "--gen-set", "assumed_max_reply_tokens=200"]
    assert cli.main(["run", "--cell", "F-r", "--model", "gpt-6.1-sol", "--matrix", "d11",
                     "--n", "3", *small, "--approved-block", "1-pilots", "--planned-usd", "5",
                     "--run-id", "d11"]) == 0
    meta = json.loads((tmp / "results" / "persistgym_pilot" / "d11" / "meta.json")
                      .read_text(encoding="utf-8"))
    assert meta["config"]["run_matrix"] == {
        "name": "d11", "n_templates": 3, "n_episodes": 8,
        "templates_per_task_cell": {"observed-nonrec-far": 1, "observed-rec-far": 1,
                                    "derived-nonrec-far": 3, "derived-rec-far": 3}}
    ids = meta["config"]["episode_ids"]
    assert len(ids) == 8 and not [i for i in ids if "near" in i]
    assert sum("observed" in i for i in ids) == 2
    (row,) = costs.read_rows(costs_csv)
    assert row["model_requested"] == "gpt-6.1-sol" and "matrix=d11" in row["notes"]


def test_run_cli_refuses_bad_matrix_options(paid_env, capsys):
    base = ["run", "--cell", "F-r", "--approved-block", "1-pilots", "--planned-usd", "1"]
    assert cli.main([*base, "--matrix", "d11", "--n", "4"]) == 2  # 4 / 3 is not whole
    assert "T_d = 4" in capsys.readouterr().err
    assert cli.main([*base, "--matrix", "d11", "--task-cell", "derived-rec-far"]) == 2
    assert cli.main([*base, "--n-observed", "1"]) == 2
    assert cli.main([*base, "--cell-templates", "derived-rec-near=1", "--matrix", "d11"]) == 2
    assert cli.main([*base, "--cell-templates", "derived-rec-near=1", "--n-observed", "1"]) == 2
    assert cli.main([*base, "--matrix", "d11", "--n", "33"]) == 2  # 88 episodes > 10
    assert "at most 10" in capsys.readouterr().err


# --- the paid-run lock (common/paidlock.py; PREREG §12) ---------------------------------------

RUN = ["run", "--cell", "W-n-0", "--model", "gpt-6-luna", "--n", "1",
       "--task-cell", "observed-nonrec-far", "derived-rec-near",
       "--gen-set", "W_tokens=6400", "--gen-set", "v_tokens=400",
       "--gen-set", "assumed_max_reply_tokens=200",
       "--approved-block", "1-pilots", "--planned-usd", "1", "--run-id", "r"]


def _lock() -> dict:
    return json.loads(cli.LOCK_PATH.read_text(encoding="utf-8"))


def _last_run() -> dict:
    return json.loads(paidlock.last_run_path(cli.LOCK_PATH).read_text(encoding="utf-8"))


def test_run_holds_the_lock_and_records_the_last_run(paid_env, monkeypatch):
    _, costs_csv, _ = paid_env
    seen, real = [], cli.run_batch

    def spy(*args, **kw):
        seen.append(_lock())
        return real(*args, **kw)
    monkeypatch.setattr(cli, "run_batch", spy)
    assert cli.main(RUN) == 0
    (held,) = seen
    assert held["run_id"] == "r"
    assert held["what"] == "persistgym_pilot: W-n-0 on gpt-6-luna, 2 episodes"
    assert not cli.LOCK_PATH.exists()                        # released after the run
    assert _last_run()["run_id"] == "r" == costs.read_rows(costs_csv)[0]["run_id"]
    assert cli.main([*RUN[:-1], "r2"]) == 0                  # the next run may start
    assert _last_run()["run_id"] == "r2"


def test_probe_holds_one_lock_for_all_its_models(paid_env, monkeypatch):
    _, costs_csv, _ = paid_env
    tokens, real = [], cli._guarded_transport

    def spy(a, model, experiment, planned_usd, held):
        tokens.append(_lock()["token"])
        assert held.holds()
        return real(a, model, experiment, planned_usd, held)
    monkeypatch.setattr(cli, "_guarded_transport", spy)
    assert cli.main(["probe-echo", "--approved-block", "1-pilots", "--planned-usd", "0.5",
                     "--run-id", "echo"]) == 0
    assert len(tokens) == 2 and len(set(tokens)) == 1
    assert not cli.LOCK_PATH.exists()
    assert _last_run()["run_id"] == "echo-gpt-6-luna" == costs.read_rows(costs_csv)[-1]["run_id"]


def test_refused_while_another_paid_run_holds_the_lock(paid_env, capsys):
    """One paid run at a time, ARC or PersistGym: refused before the transport is built."""
    _, costs_csv, fakes = paid_env
    cli.LOCK_PATH.write_text('{"run_id": "arc-pilot-ft09"}', encoding="utf-8")
    assert cli.main(RUN) == 2
    err = capsys.readouterr().err
    assert "arc-pilot-ft09" in err and "One paid run at a time" in err
    assert fakes == [] and costs.read_rows(costs_csv) == []
    assert _lock() == {"run_id": "arc-pilot-ft09"}           # left alone


def test_refused_when_the_last_runs_row_is_not_in_this_ledger(paid_env, capsys):
    tmp, costs_csv, fakes = paid_env
    paidlock.record_last_run(cli.LOCK_PATH, run_id="arc-pilot-ft09",
                             costs_csv=tmp / "elsewhere" / "costs.csv")
    assert cli.main(RUN) == 2
    err = capsys.readouterr().err
    assert "arc-pilot-ft09" in err and "not in this checkout" in err
    assert [f.calls for f in fakes] == [[]]                  # no client call
    assert costs.read_rows(costs_csv) == [] and not cli.LOCK_PATH.exists()


def test_refused_under_a_merged_draft_prereg(paid_env, capsys):
    """PREREG §0.4: a draft merged to main does not unlock paid calls (before, the guard
    checked only that HEAD and origin/main hold the same PREREG.md)."""
    tmp, costs_csv, fakes = paid_env
    (tmp / "PREREG.md").write_text(DRAFT_PREREG, encoding="utf-8")
    git_in(tmp, "commit", "-q", "-am", "a draft, merged")
    push_main(tmp)
    assert cli.main(RUN) == 2
    assert "PREREG.md is not frozen" in capsys.readouterr().err
    assert [f.calls for f in fakes] == [[]]
    assert costs.read_rows(costs_csv) == [] and not cli.LOCK_PATH.exists()


def test_a_run_whose_row_cannot_be_written_keeps_the_lock(paid_env, monkeypatch, capsys):
    """Spend the ledger does not show stops every later paid run until the row is added by
    hand and the lock deleted."""
    _, costs_csv, fakes = paid_env
    real_append = costs.append_row

    def locked_file(row, path):
        raise PermissionError("costs.csv is open in another program")
    monkeypatch.setattr(costs, "append_row", locked_file)
    with pytest.raises(PermissionError):
        cli.main(RUN)
    err = capsys.readouterr().err
    assert "ERROR: could not account for the run" in err and str(cli.LOCK_PATH) in err
    held = _lock()
    assert held["run_id"] == "r" and "add its row by hand" in held["kept_because"]
    assert f"made {len(fakes[0].calls)} paid calls" in held["kept_because"]
    assert not paidlock.last_run_path(cli.LOCK_PATH).exists()

    monkeypatch.setattr(costs, "append_row", real_append)
    assert cli.main([*RUN[:-1], "r2"]) == 2
    assert "add its row by hand" in capsys.readouterr().err
    assert len(fakes) == 1 and costs.read_rows(costs_csv) == []


def test_a_run_whose_finalize_never_ran_keeps_the_lock(paid_env, monkeypatch, capsys):
    """run_batch closes its transcript before it calls finalize; if closing fails, the CLI's
    check after the run still sees calls with no costs row and keeps the lock."""
    _, costs_csv, fakes = paid_env
    real_close = runner.JsonlRecorder.close

    def close_fails(self):
        real_close(self)
        raise OSError("disk full")
    monkeypatch.setattr(runner.JsonlRecorder, "close", close_fails)
    with pytest.raises(OSError, match="disk full"):
        cli.main(RUN)
    assert costs.read_rows(costs_csv) == []
    reason = _lock()["kept_because"]
    assert f"run r (persistgym_pilot, gpt-6-luna) made {len(fakes[0].calls)} paid calls" in (
        reason)
    assert '"reasoning_tokens": null' in reason               # blinded pilot (PREREG §11)
    assert "ERROR: could not account for the run" in capsys.readouterr().err


def test_paid_calls_off_never_touch_the_lock(monkeypatch, capsys):
    monkeypatch.delenv(ALLOW_ENV, raising=False)

    def no_lock(*a, **k):
        raise AssertionError("must not take the paid-run lock")
    monkeypatch.setattr(paidlock, "paid_run_lock", no_lock)
    monkeypatch.setattr(paidlock, "lock_path", no_lock)
    assert cli.main(["probe-echo", "--approved-block", "1-pilots", "--planned-usd", "1"]) == 2
    assert cli.main(RUN) == 2
    assert capsys.readouterr().err.count("paid calls are off") == 2


def test_the_default_lock_is_the_shared_one(monkeypatch, tmp_path):
    """With no test override, the CLI takes the lock in this checkout's git common directory
    (`paidlock.lock_path`), the one the ARC launcher takes."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    monkeypatch.setattr(cli, "LOCK_PATH", None)
    asked, seen = [], []

    def lock_path(repo):
        asked.append(repo)
        return tmp_path / paidlock.LOCK_NAME
    monkeypatch.setattr(paidlock, "lock_path", lock_path)

    def refuse(a, model, experiment, planned_usd, held):  # as when the guard refuses: None
        seen.append((held.path, held.holds()))
    monkeypatch.setattr(cli, "_guarded_transport", refuse)
    assert cli.main(["probe-echo", "--model", "gpt-6-luna", "--approved-block", "1-pilots",
                     "--planned-usd", "1"]) == 2
    assert asked == [runmeta.REPO_ROOT] and seen == [(tmp_path / paidlock.LOCK_NAME, True)]
    assert not (tmp_path / paidlock.LOCK_NAME).exists()
