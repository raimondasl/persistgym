"""The paid CLI paths end to end, with no network: the real guarded transport is built with
a stub client whose `responses.create` is answered by the fake model. This checks that a paid
run would write its results, meta.json and exactly one costs.csv row per run, before any
money is spent on finding out, and that it holds the paid-run lock (a temporary file here,
never the shared one) and leaves it held when its spend is not in costs.csv."""

from __future__ import annotations

import gzip
import json
from collections import Counter
from decimal import Decimal

import pytest

from common import costs, hold, paidlock, runmeta
from common.tests.gitrepo import DRAFT_PREREG, git_in, push_main, write_decisions
from harnesses import blinding, cli, probes, runner
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
    monkeypatch.setattr(cli, "LOCK_PATH", tmp_path / "lock" / paidlock.lock_name(cli.STREAM))
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


def test_probe_replay_original_design_is_the_default(paid_env):
    """`probe-replay` without --design runs the original D29 probe, 10 trials per context."""
    tmp, costs_csv, _ = paid_env
    assert cli.main(["probe-replay", "--model", "gpt-6-luna", "--approved-block", "1-pilots",
                     "--planned-usd", "2", "--run-id", "orig"]) == 0
    out = tmp / "results" / "replay_probe" / "orig"
    trials = [json.loads(x) for x in (out / "trials.jsonl").read_text(encoding="utf-8")
              .splitlines()]
    assert len(trials) == 20 and {t["repeat"] for t in trials} == set(range(10))
    assert all("picked" in t["score"] and "numbers" not in t for t in trials)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["cell_or_config"] == "replay-probe" and meta["seeds"] is None
    assert "fork" not in meta["config"] and meta["config"]["n_per_context"] == 10
    assert not (out / "fork_report.json").exists()
    (row,) = costs.read_rows(costs_csv)
    assert row["cell_or_config"] == "replay-probe" and row["n_calls"] == "60"


def test_probe_summary_of_an_original_design_run(paid_env, capsys):
    """$0 `probe-summary`: the per-arm counts behind PREREG §17.1's block-1 table, from the
    committed trials.jsonl and, when present, the raw transcript."""
    tmp, _, _ = paid_env
    assert cli.main(["probe-replay", "--model", "gpt-6-luna", "--n", "3", "--approved-block",
                     "1-pilots", "--planned-usd", "2", "--run-id", "orig"]) == 0
    capsys.readouterr()
    args = ["probe-summary", "orig", "--results-root", str(tmp / "results")]
    assert cli.main([*args, "--raw-root", str(tmp / "raw")]) == 0
    (arms,) = [r["arms"] for r in json.loads(capsys.readouterr().out).values()]
    assert arms["all_turns"] == arms["current_turn"] == {
        "trials": 3, "turn1_summary_names_no_number": 0, "turn1_summary_names_one_number": 3,
        "turn1_summary_names_several_numbers": 0, "scorable": 3, "matches": 3,
        "turn3_answered_a_number": 3, "turn3_answer_counts": {"427": 3}, "leaks": 0,
        "incomplete_trials": 0, "responses": 9, "echo_mismatched_responses": 0,
        "turn1_summary_empty": 0,
        "turn1_reasoning_tokens": {"min": 37, "median": 37, "max": 37},
        "reasoning_summary_echoed": {"auto": 9}}
    # without the raw transcript: the committed counts only
    assert cli.main([*args, "--raw-root", str(tmp / "elsewhere")]) == 0
    (run,) = json.loads(capsys.readouterr().out).values()
    assert not run["raw_transcript_read"] and "turn1_summary_empty" not in run["arms"]["all_turns"]
    assert cli.main([*args[:1], "../orig", *args[2:]]) == 2
    assert cli.main([*args[:1], "missing", *args[2:]]) == 1


def _fork_fake(p, i):
    """turn 1 "ready", turn 2 "Paris"; turn 3: all_turns names the list's 5th number,
    current_turn says it has no record."""
    turn = sum(1 for x in p["input"] if x.get("role") == "user") - 1
    if turn < 2:
        return ["ready", "Paris"][turn]
    if p["reasoning"]["context"] == "current_turn":
        return "I don't have a record of that number."
    return str(probes.three_digit_numbers(p["input"][0]["content"][0]["text"])[4])


def test_probe_replay_fork_cli(paid_env, monkeypatch, capsys):
    """PREREG §17.1: 20 scorable trials per arm, two byte-identical forks per trial, one
    costs.csv row per model under replay_probe, and fork_report.json next to meta.json."""
    tmp, costs_csv, _ = paid_env
    fakes = []

    def transport(**kw):
        fakes.append(FakeModel(_fork_fake))
        return OpenAIResponsesTransport(
            **kw, costs_path=costs_csv, repo=tmp,
            client_factory=lambda timeout, fake=fakes[-1]: _FakeBackedClient(fake))
    monkeypatch.setattr(cli, "OpenAIResponsesTransport", transport)
    assert cli.main(["probe-replay", "--design", "fork", "--approved-block", "1-pilots",
                     "--planned-usd", "2", "--run-id", "fk"]) == 0
    assert "condition (b) met: True" in capsys.readouterr().out
    rows = costs.read_rows(costs_csv)
    assert [r["run_id"] for r in rows] == ["fk-gpt-6.1-sol", "fk-gpt-6-luna"]
    assert all(r["experiment"] == "replay_probe" and r["cell_or_config"] == "replay-fork-probe"
               and r["n_calls"] == "160" for r in rows)
    out = tmp / "results" / "replay_probe" / "fk-gpt-6.1-sol"
    trials = [json.loads(x) for x in (out / "trials.jsonl").read_text(encoding="utf-8")
              .splitlines()]
    assert len(trials) == 40 and all(t["score"]["scorable"] for t in trials)
    assert sorted({t["seed"] for t in trials}) == list(
        range(probes.FORK_SEED_START, probes.FORK_SEED_START + 20))
    assert all(t["fork_request_sha256"][0] == t["fork_request_sha256"][1] for t in trials)
    assert "payloads" not in trials[0] and "reasoning_summaries" not in trials[0]
    calls = fakes[0].calls
    assert len(calls) == 160 and all(calls[i + 2] == calls[i + 3] for i in range(0, 160, 4))
    report = json.loads((out / "fork_report.json").read_text(encoding="utf-8"))
    assert report["run_id"] == "fk-gpt-6.1-sol" and report["exit_reason"] == "COMPLETED"
    assert report["condition_b"] == {
        "registered_settings": True, "enough_scorable": True,
        "all_turns_agreements": 20, "all_turns_needs": ">= 15 of 20",
        "current_turn_agreements": 0, "current_turn_needs": "<= 5 of 20", "met": True}
    assert report["arms"]["all_turns"]["position_counts"] == {"5": 40}
    assert report["all_probe_echoes_match"]
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert set(runmeta.REQUIRED) <= set(meta) and meta["exit_reason"] == "COMPLETED"
    assert meta["cell_or_config"] == "replay-fork-probe"
    assert meta["config"]["fork"]["design"] == "fork"
    assert meta["config"]["fork"]["target_scorable_per_arm"] == 20
    assert meta["config"]["fork"]["max_attempts_per_arm"] == 40
    assert meta["config"]["probe_config"]["reasoning_summary"] == "auto"
    assert meta["seeds"]["seed_start"] == probes.FORK_SEED_START
    assert meta["reasoning_context_echoed"] == {"all_turns": 80, "current_turn": 80}
    with gzip.open(tmp / "raw" / "replay_probe" / "fk-gpt-6.1-sol" / "transcript.jsonl.gz",
                   "rt", encoding="utf-8") as f:
        raw = [json.loads(x) for x in f]
    assert len(raw) == 40 and all(len(r["payloads"]) == 4 for r in raw)
    # probe-summary re-derives the report from the committed files
    capsys.readouterr()
    assert cli.main(["probe-summary", "fk-gpt-6.1-sol", "fk-gpt-6-luna",
                     "--results-root", str(tmp / "results")]) == 0
    summary = json.loads(capsys.readouterr().out)
    for run_id, run in summary.items():
        written = json.loads((tmp / "results" / "replay_probe" / run_id / "fork_report.json")
                             .read_text(encoding="utf-8"))
        assert run["raw_transcript_read"] and written.pop("run_id") == run_id
        assert {k: v for k, v in run.items() if k != "raw_transcript_read"} == written


@pytest.mark.parametrize("args", [["--design", "fork", "--n", "21"],
                                  ["--design", "fork", "--max-attempts", "41"],
                                  ["--design", "fork", "--n", "10", "--max-attempts", "9"],
                                  ["--design", "fork", "--n", "0"],
                                  ["--max-attempts", "40"],
                                  ["--design", "fork", "--effort", "high"],
                                  ["--design", "fork", "--mode", "pro"],
                                  ["--design", "fork", "--service-tier", "default"]])
def test_probe_replay_fork_refuses_bad_limits_or_settings_before_the_lock(paid_env, monkeypatch,
                                                                          capsys, args):
    _, costs_csv, fakes = paid_env

    def no_lock(*a, **k):
        raise AssertionError("must not take the paid-run lock")
    monkeypatch.setattr(paidlock, "paid_run_lock", no_lock)
    assert cli.main(["probe-replay", *args, "--approved-block", "1-pilots",
                     "--planned-usd", "1"]) == 2
    assert "refused" in capsys.readouterr().err
    assert fakes == [] and costs.read_rows(costs_csv) == []


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
    assert "context_mismatches=0; effort_mismatches=0;" in row["notes"]
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
    # sol's registered effort (PREREG §17.2) is the default, on every request it sent
    n = int(row["n_calls"])
    assert meta["reasoning_effort"] == "high" and meta["reasoning_effort_echoed"] == {"high": n}
    assert "effort_mismatches=0;" in row["notes"]


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


# --- parallel episodes (PREREG §4.6, §0.3 line 15; harnesses/parallel.py) ------------------

PILOT_RUN = ["run", "--cell", "F-r", "--model", "gpt-6-luna", "--n", "1",
             "--gen-set", "W_tokens=6400", "--gen-set", "v_tokens=400",
             "--gen-set", "assumed_max_reply_tokens=200",
             "--approved-block", "1-pilots", "--planned-usd", "1"]


def test_run_cli_parallel_writes_what_sequential_play_writes(paid_env, monkeypatch):
    """Through the real guarded transport: `--parallel 4` writes the episodes, transcript and
    summary that `--parallel 1` writes, byte for byte (the fake answers by payload, the call
    clock is fixed), one costs row with the same calls, tokens and cost, reserves spend
    episode by episode, and releases the lock and its reservation like any run."""
    tmp, costs_csv, _ = paid_env
    monkeypatch.setattr(runner, "CLOCK", lambda: 0.0)
    fakes = []

    def transport(**kw):
        fakes.append(FakeModel(ids="payload"))
        return OpenAIResponsesTransport(
            **kw, costs_path=costs_csv, repo=tmp,
            client_factory=lambda timeout, fake=fakes[-1]: _FakeBackedClient(fake))
    monkeypatch.setattr(cli, "OpenAIResponsesTransport", transport)
    held, real = [], cli.run_batch

    def spy(*args, **kw):
        held.append(_lock())
        return real(*args, **kw)
    monkeypatch.setattr(cli, "run_batch", spy)
    assert cli.main([*PILOT_RUN, "--run-id", "seq"]) == 0
    assert cli.main([*PILOT_RUN, "--run-id", "par", "--parallel", "4"]) == 0

    raw, out = tmp / "raw" / "persistgym_pilot", tmp / "results" / "persistgym_pilot"
    assert (raw / "par" / "episodes.jsonl").read_bytes() == (
        raw / "seq" / "episodes.jsonl").read_bytes()
    with (gzip.open(raw / "par" / "transcript.jsonl.gz", "rb") as p,
          gzip.open(raw / "seq" / "transcript.jsonl.gz", "rb") as s):
        assert p.read() == s.read()
    assert (out / "par" / "summary.json").read_bytes() == (
        out / "seq" / "summary.json").read_bytes()
    assert ([Counter(json.dumps(c, sort_keys=True) for c in f.calls) for f in fakes[1:]]
            == [Counter(json.dumps(c, sort_keys=True) for c in fakes[0].calls)])
    seq_row, par_row = costs.read_rows(costs_csv)
    for k in ("n_calls", "input_tokens", "cached_input_tokens", "output_tokens",
              "reasoning_tokens", "model_returned", "service_tier", "cell_or_config"):
        assert par_row[k] == seq_row[k], k
    for k in ("cost_usd_list", "cost_usd_billed_est"):
        assert float(par_row[k]) == pytest.approx(float(seq_row[k]), abs=2e-6)
    assert " matrix=full parallel=4;" in par_row["notes"] and "parallel" not in seq_row["notes"]
    assert held[1]["what"] == "persistgym_pilot: F-r on gpt-6-luna, 8 episodes, 4 at once"
    # one lock, released; the reservation of the run's planned spend is gone
    assert not cli.LOCK_PATH.exists() and _last_run()["run_id"] == "par"
    assert not paidlock.reservation_path(cli.LOCK_PATH, cli.STREAM).exists()
    meta = json.loads((out / "par" / "meta.json").read_text(encoding="utf-8"))
    seq_meta = json.loads((out / "seq" / "meta.json").read_text(encoding="utf-8"))
    assert meta["config_hash"] == seq_meta["config_hash"] and meta["paid"] is True
    info = meta["parallel"]
    assert info["max_episodes_in_flight"] == 4 and info["episodes_started"] == 8
    assert info["peak_episodes_in_flight"] == 4 and info["stop_reason"] is None
    assert info["spend_reservation"]["planned_usd"] == 1.0
    assert seq_meta["parallel"] == {"max_episodes_in_flight": 1}
    # pilot blinding: the reservation log and the transcripts stay under raw/
    assert sorted(p.name for p in (raw / "par").iterdir()) == [
        "episodes.jsonl", runner.RESERVATIONS_LOG, "transcript.jsonl.gz"]
    assert sorted(p.name for p in out.rglob("*") if p.is_file()) == [
        "meta.json", "meta.json", "summary.json", "summary.json"]


@pytest.mark.parametrize("n", ["0", "17", "-2"])
def test_run_cli_refuses_a_bad_parallel_before_the_lock(paid_env, monkeypatch, capsys, n):
    _, costs_csv, fakes = paid_env

    def no_lock(*a, **k):
        raise AssertionError("must not take the paid-run lock")
    monkeypatch.setattr(paidlock, "paid_run_lock", no_lock)
    assert cli.main([*PILOT_RUN, "--parallel", n]) == 2
    assert f"--parallel is 1 to 16 episodes at once (PREREG §4.6), got {n}" in (
        capsys.readouterr().err)
    assert fakes == [] and costs.read_rows(costs_csv) == []


# --- the paid-run lock (common/paidlock.py; PREREG §12) ---------------------------------------

RUN = ["run", "--cell", "W-n-0", "--model", "gpt-6-luna", "--n", "1",
       "--task-cell", "observed-nonrec-far", "derived-rec-near",
       "--gen-set", "W_tokens=6400", "--gen-set", "v_tokens=400",
       "--gen-set", "assumed_max_reply_tokens=200",
       "--approved-block", "1-pilots", "--planned-usd", "1", "--run-id", "r"]


def _lock() -> dict:
    return json.loads(cli.LOCK_PATH.read_text(encoding="utf-8"))


def _last_run() -> dict:
    return json.loads(paidlock.last_run_path(cli.LOCK_PATH, cli.STREAM).read_text(
        encoding="utf-8"))


def test_run_holds_the_lock_and_records_the_last_run(paid_env, monkeypatch):
    _, costs_csv, _ = paid_env
    seen, real = [], cli.run_batch

    def spy(*args, **kw):
        seen.append(_lock())
        return real(*args, **kw)
    monkeypatch.setattr(cli, "run_batch", spy)
    assert cli.main(RUN) == 0
    (held,) = seen
    assert held["run_id"] == "r" and held["stream"] == "persistgym"
    assert held["what"] == "persistgym_pilot: W-n-0 on gpt-6-luna, 2 episodes"
    assert not cli.LOCK_PATH.exists()                        # released after the run
    # its spend is in costs.csv: its reservation no longer counts against ARC runs
    assert not paidlock.reservation_path(cli.LOCK_PATH, cli.STREAM).exists()
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
    """One PersistGym paid run at a time: refused before the transport is built."""
    _, costs_csv, fakes = paid_env
    cli.LOCK_PATH.write_text('{"run_id": "luna-pilot-0"}', encoding="utf-8")
    assert cli.main(RUN) == 2
    err = capsys.readouterr().err
    assert "luna-pilot-0" in err and "One paid run at a time per stream" in err
    assert fakes == [] and costs.read_rows(costs_csv) == []
    assert _lock() == {"run_id": "luna-pilot-0"}             # left alone


def test_an_arc_run_does_not_block_a_persistgym_run(paid_env, monkeypatch):
    """PREREG §0.3 line 15: the ARC stream has its own lock, so a PersistGym run may go
    beside an ARC run; the ARC run's lock is left alone. Its reservation, in another block
    and phase, takes no room from this run."""
    _, costs_csv, _ = paid_env
    arc_lock = cli.LOCK_PATH.with_name(paidlock.lock_name(paidlock.ARC))
    with paidlock.paid_run_lock(arc_lock, run_id="arc-path-ft09", what="arc_path",
                                stream=paidlock.ARC) as info:
        with paidlock.budget_mutex(arc_lock):
            paidlock.write_reservation(paidlock.HeldLock(arc_lock, info),
                                       approved_block="2-seed1", experiment="arc_path",
                                       phase="1b", planned_usd=Decimal(120))
        seen, real = [], cli._guarded_transport

        def spy(a, model, experiment, planned_usd, held):
            t = real(a, model, experiment, planned_usd, held)
            seen.append(t.approval)
            return t
        monkeypatch.setattr(cli, "_guarded_transport", spy)
        assert cli.main(RUN) == 0
        assert json.loads(arc_lock.read_text(encoding="utf-8"))["token"] == info["token"]
        assert paidlock.reservation_path(arc_lock, paidlock.ARC).exists()
    (granted,) = seen
    assert granted.stream == "persistgym" and granted.reserved_block_usd == 0
    assert granted.reserved_phase_usd == 0
    assert costs.read_rows(costs_csv)[0]["run_id"] == "r"
    assert not arc_lock.exists() and not paidlock.reservation_path(arc_lock,
                                                                   paidlock.ARC).exists()


def test_refused_while_the_old_single_lock_exists(paid_env, capsys):
    """A launcher from before the per-stream locks takes `persistgym-paid-run.lock`; while
    it exists, no paid run of either stream starts."""
    _, costs_csv, fakes = paid_env
    legacy = cli.LOCK_PATH.with_name(paidlock.LEGACY_LOCK_NAME)
    legacy.write_text('{"run_id": "old-arc-pilot"}', encoding="utf-8")
    assert cli.main(RUN) == 2
    err = capsys.readouterr().err
    assert "old-arc-pilot" in err and "old single paid-run lock" in err
    assert fakes == [] and costs.read_rows(costs_csv) == [] and not cli.LOCK_PATH.exists()
    assert legacy.read_text(encoding="utf-8") == '{"run_id": "old-arc-pilot"}'


def test_refused_when_the_last_runs_row_is_not_in_this_ledger(paid_env, capsys):
    """The ARC stream's last run counts too: its row must be in this checkout's ledger."""
    tmp, costs_csv, fakes = paid_env
    paidlock.record_last_run(cli.LOCK_PATH, stream=paidlock.ARC, run_id="arc-pilot-ft09",
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
    assert not paidlock.last_run_path(cli.LOCK_PATH, cli.STREAM).exists()
    # its reservation stays too, counting against ARC runs, and the reason names it
    reservation = paidlock.reservation_path(cli.LOCK_PATH, cli.STREAM)
    assert reservation.exists() and str(reservation) in held["kept_because"]

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


# --- the hold after COST_CAP (common/hold.py; PREREG §0.3 line 12, §7.7) ------------------

ARC_RUN = "20261009T120000Z-S0-ft09-s1"


def test_refused_while_a_hold_stands_until_the_researcher_clears_it(paid_env, capsys):
    """A hold placed by an ARC run that ended COST_CAP stops PersistGym runs too (either
    stream), before the transport builds a client, until its clearing line is merged."""
    tmp, costs_csv, fakes = paid_env
    hold.place_hold(cli.LOCK_PATH, run_id=ARC_RUN, experiment="arc_path",
                    reason="ended COST_CAP at its harness cost guard of $120.00 list")
    assert cli.main(RUN) == 2
    err = capsys.readouterr().err
    assert f"1 hold stands: run {ARC_RUN} (arc_path;" in err
    assert f"'cleared_hold: {ARC_RUN}'" in err
    assert [f.calls for f in fakes] == [[]]                  # no client call
    assert costs.read_rows(costs_csv) == [] and not cli.LOCK_PATH.exists()

    text = (tmp / "results" / "decisions.md").read_text(encoding="utf-8")
    write_decisions(tmp, text + f"cleared_hold: {ARC_RUN}\n")
    git_in(tmp, "commit", "-q", "-am", "clear the hold")
    push_main(tmp)                                           # the researcher's merge
    assert cli.main([*RUN[:-1], "r2"]) == 0
    assert [r["run_id"] for r in costs.read_rows(costs_csv)] == ["r2"]


def test_a_run_stopped_at_its_planned_spend_places_no_hold(paid_env):
    """The transport's stop at --planned-usd is recorded as COST_CAP, but it is the planned
    spend, not a per-run cost guard (PREREG §7.7): it places no hold."""
    tmp, _, fakes = paid_env
    tiny = [*RUN[:RUN.index("--planned-usd") + 1], "0.0000001", "--run-id", "tiny"]
    assert cli.main(tiny) == 0
    meta = json.loads((tmp / "results" / "persistgym_pilot" / "tiny" / "meta.json")
                      .read_text(encoding="utf-8"))
    assert meta["exit_reason"] == "COST_CAP" and len(fakes[0].calls) == 1
    assert not hold.holds_path(cli.LOCK_PATH).exists()
    assert cli.main([*RUN[:-1], "r2"]) == 0                  # the next run is not held


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
    """With no test override, the CLI takes the PersistGym stream's lock in this checkout's
    git common directory (`paidlock.lock_path`); the ARC launcher takes the ARC stream's lock
    next to it."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    monkeypatch.setattr(cli, "LOCK_PATH", None)
    asked, seen = [], []
    name = paidlock.lock_name(paidlock.PERSISTGYM)

    def lock_path(repo, stream):
        asked.append((repo, stream))
        return tmp_path / name
    monkeypatch.setattr(paidlock, "lock_path", lock_path)

    def refuse(a, model, experiment, planned_usd, held):  # as when the guard refuses: None
        seen.append((held.path, held.holds(), held.stream))
    monkeypatch.setattr(cli, "_guarded_transport", refuse)
    assert cli.main(["probe-echo", "--model", "gpt-6-luna", "--approved-block", "1-pilots",
                     "--planned-usd", "1"]) == 2
    assert asked == [(runmeta.REPO_ROOT, "persistgym")]
    assert seen == [(tmp_path / name, True, "persistgym")]
    assert not (tmp_path / name).exists()
