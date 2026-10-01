"""The paid CLI paths end to end, with no network: the real guarded transport is built with
a stub client whose `responses.create` is answered by the fake model. This checks that a paid
run would write its results, meta.json and exactly one costs.csv row per run, before any
money is spent on finding out."""

from __future__ import annotations

import gzip
import json

import pytest

from common import costs, runmeta
from harnesses import cli
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
    prereg_repo(tmp_path)
    costs_csv = tmp_path / "costs.csv"
    costs_csv.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    monkeypatch.setenv(ALLOW_ENV, "1")
    monkeypatch.setattr(cli, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(cli, "RAW", tmp_path / "raw")
    fakes = []

    def turn(payload):  # 0-based turn within one probe conversation
        return sum(1 for i in payload["input"] if i.get("role") == "user") - 1

    def guarded(a, model, experiment, planned_usd):
        fake = FakeModel(lambda p, i: ["ready", "Paris", "427"][min(turn(p), 2)],
                         reasoning_summary_fn=lambda p, tag: "Picked 427." if turn(p) == 0
                         else "")
        fakes.append(fake)
        return OpenAIResponsesTransport(
            model=model, approved_block=a.approved_block, experiment=experiment,
            planned_usd=planned_usd, costs_path=costs_csv, repo=tmp_path,
            client_factory=lambda timeout: _FakeBackedClient(fake))
    monkeypatch.setattr(cli, "_guarded_transport", guarded)
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

    def spy(a, model, experiment, planned_usd):
        planned.append(planned_usd)
        return real(a, model, experiment, planned_usd)
    monkeypatch.setattr(cli, "_guarded_transport", spy)
    assert cli.main(["probe-echo", "--approved-block", "1-pilots", "--planned-usd", "0.5",
                     "--run-id", "e"]) == 0
    first = float(costs.read_rows(costs_csv)[0]["cost_usd_billed_est"])
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
