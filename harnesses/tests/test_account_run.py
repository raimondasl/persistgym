"""`account-run` (harnesses/account.py) and the root-cause fix of the 2026-10-02 incident, end to
end with no network: the real guarded transport with a stub client answered by the fake
model, as in test_cli_end_to_end.py. Every lock, reservation, ledger and run folder is
temporary.

The incident: a blinded pilot run played all its episodes and wrote its raw transcript and
episodes.jsonl, then its `finalize` failed (`git rev-parse HEAD` could not start, exit
3221225794), so it kept the paid-run lock with the reason and its totals, kept its spend
reservation, and wrote no costs row, summary.json or meta.json. Since the fix `finalize`
starts no process, so these tests raise the incident's exception where `finalize` can still
fail, at the row's write: the lock then holds the reason the incident's held."""

from __future__ import annotations

import csv
import gzip
import io
import json
import os
import re
import shutil
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from common import costs, paidlock, runmeta
from common.tests.gitrepo import FROZEN_PREREG, decisions_text, guarded_repo
from harnesses import account, blinding, cli, registered, runner
from harnesses.fake import FakeModel
from harnesses.openai_transport import ALLOW_ENV, OpenAIResponsesTransport
from harnesses.pricing import usage_numbers

RID = "20261002T180358Z-F-0-gpt-6-luna"
SMALL = ["--gen-set", "W_tokens=6400", "--gen-set", "v_tokens=400",
         "--gen-set", "assumed_max_reply_tokens=200"]
RUN_ARGS = ["--cell", "F-0", "--model", "gpt-6-luna", "--n", "1",
            "--task-cell", "observed-nonrec-far", "derived-rec-far", *SMALL,
            "--approved-block", "1-pilots", "--planned-usd", "1"]
VALIDITY_ARGS = ["--cell", "F-0", "--model", "gpt-6-luna", "--split", "validity", "--n", "1",
                 "--task-cell", "observed-nonrec-far", "derived-rec-far", *SMALL,
                 "--experiment", "persistgym_validity", "--approved-block", "1-pilots",
                 "--planned-usd", "1"]
INCIDENT_EXIT = 3221225794  # 0xC0000142, STATUS_DLL_INIT_FAILED
VOLATILE_META = {"started_utc", "finished_utc", "recovered"}
REAL_HOLDER_ALIVE = paidlock.holder_alive  # the fixture replaces it


class _Obj:
    def __init__(self, data):
        self.data = data

    def to_dict(self, mode="python"):
        return self.data


class _Client:
    """`responses.create` answered by the fake model; counts the calls."""

    def __init__(self, fake, calls, on_call=None):
        self.fake, self.calls, self.on_call = fake, calls, on_call
        self.responses = self

    def create(self, **payload):
        if self.on_call is not None:
            self.on_call(len(self.calls))
        self.calls.append(payload)
        return _Obj(self.fake.send(payload))


class World:
    """One ledger and one paid-run lock folder (its last-run record and reservation go next to
    the lock)."""

    def __init__(self, tmp: Path, name: str):
        self.costs = tmp / f"costs-{name}.csv"
        self.costs.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
        (tmp / f"lock-{name}").mkdir()
        self.lock = tmp / f"lock-{name}" / paidlock.lock_name(cli.STREAM)

    @property
    def reservation(self) -> Path:
        return paidlock.reservation_path(self.lock, cli.STREAM)

    def rows(self) -> list[dict]:
        return costs.read_rows(self.costs)


class Env:
    def __init__(self, tmp: Path, monkeypatch, experiments=None):
        self.tmp, self.mp = tmp, monkeypatch
        (tmp / "repo").mkdir()
        decisions = (decisions_text("1-pilots") if experiments is None
                     else decisions_text("1-pilots", experiments=experiments))
        self.repo = guarded_repo(tmp / "repo", prereg=FROZEN_PREREG, decisions=decisions)
        self.results, self.raw = tmp / "results", tmp / "raw"
        monkeypatch.setattr(cli, "RESULTS", self.results)
        monkeypatch.setattr(cli, "RAW", self.raw)
        self.calls: list[dict] = []
        self.on_call = None
        self.world: World | None = None

        def transport(**kw):
            fake = FakeModel()
            return OpenAIResponsesTransport(
                **kw, costs_path=self.world.costs, repo=self.repo,
                client_factory=lambda timeout: _Client(fake, self.calls, self.on_call))
        monkeypatch.setattr(cli, "OpenAIResponsesTransport", transport)

    def use(self, world: World) -> World:
        self.world = world
        self.mp.setattr(cli, "LOCK_PATH", world.lock)
        self.mp.setattr(cli, "COSTS_PATH", world.costs)
        return world

    def dirs(self, rid=RID, experiment="persistgym_pilot") -> tuple[Path, Path]:
        return self.results / experiment / rid, self.raw / experiment / rid


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A paid-run setup whose call clock is fixed (so that `call_latency_s` and summary.json
    are the same in every run), and in which the process that took a kept lock counts as
    ended (it is this test's own process)."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    monkeypatch.setattr(runner, "CLOCK", lambda: 0.0)
    monkeypatch.setattr(paidlock, "holder_alive", lambda info: None)
    return Env(tmp_path, monkeypatch)


def _run(args, rid=RID) -> int:
    return cli.main(["run", *args, "--run-id", rid])


def _incident(env: Env, monkeypatch, args=RUN_ARGS, rid=RID,
              world: World | None = None) -> World:
    """The 2026-10-02 incident in world "incident" (or `world`): the costs row cannot be
    written after the run's calls, with the exception the real run got."""
    world = env.use(world or World(env.tmp, "incident"))
    real = costs.append_row

    def git_could_not_start(row, path):
        raise subprocess.CalledProcessError(INCIDENT_EXIT, ["git", "rev-parse", "HEAD"])
    monkeypatch.setattr(costs, "append_row", git_could_not_start)
    with pytest.raises(subprocess.CalledProcessError):
        _run(args, rid)
    monkeypatch.setattr(costs, "append_row", real)
    return world


def _normal(env: Env, args=RUN_ARGS, experiment="persistgym_pilot") -> dict:
    """The same run with nothing failing, in world "normal": what it wrote. Its run folders
    are then moved away, so that the incident's run, with the same run id, writes the same
    paths."""
    world = env.use(World(env.tmp, "normal"))
    assert _run(args) == 0
    out, raw = env.dirs(experiment=experiment)
    (row,) = world.rows()
    written = {"row": row, "summary": (out / "summary.json").read_bytes(),
               "meta": json.loads((out / "meta.json").read_text(encoding="utf-8"))}
    shutil.rmtree(out)
    shutil.rmtree(raw)
    return written


def _account(*args) -> int:
    return cli.main(["account-run", RID, *args])


def _files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and "repo" not in p.relative_to(root).parts[:1]}


def _transcript(raw: Path) -> list[dict]:
    with gzip.open(raw / "transcript.jsonl.gz", "rt", encoding="utf-8") as f:
        return [json.loads(x) for x in f]


def _write_transcript(raw: Path, records: list[dict]) -> None:
    with gzip.open(raw / "transcript.jsonl.gz", "wt", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _token_totals(raw: Path) -> list[str]:
    """The run's token totals, summed here from its raw transcript: values account-run must
    not print for a blinded run (and its reasoning total for any run)."""
    totals = {}
    for rec in _transcript(raw):
        for k, v in usage_numbers(rec["response"]["usage"]).items():
            totals[k] = totals.get(k, 0) + v
    return [str(v) for v in totals.values() if v]


def _printed(env: Env, text: str, value: str) -> bool:
    """Whether `value` is printed as a number of its own in `text`, outside the temporary
    paths (whose pytest folder number could be any number)."""
    for tmp in (str(env.tmp), env.tmp.as_posix()):
        text = text.replace(tmp, "<tmp>")
    return re.search(rf"(?<![\w.]){re.escape(value)}(?![\w])", text) is not None


# --- the incident and its recovery ------------------------------------------------------------

def test_the_incident_leaves_the_lock_kept_and_no_row(env, monkeypatch, capsys):
    world = _incident(env, monkeypatch)
    out, raw = env.dirs()
    held = json.loads(world.lock.read_text(encoding="utf-8"))
    why = held["kept_because"]
    assert held["run_id"] == RID and f"run {RID} (persistgym_pilot, gpt-6-luna) made" in why
    assert f"returned non-zero exit status {INCIDENT_EXIT}" in why
    assert '"reasoning_tokens": null' in why                 # blinded pilot (PREREG §11)
    assert world.rows() == [] and world.reservation.exists()
    assert not (out / "summary.json").exists() and not (out / "meta.json").exists()
    assert sorted(p.name for p in raw.iterdir()) == ["episodes.jsonl", runner.RUN_PLAN,
                                                     "transcript.jsonl.gz"]
    assert "ERROR: could not account for the run" in capsys.readouterr().err


@pytest.mark.parametrize("with_plan", [True, False], ids=["run-plan", "no-run-plan"])
def test_account_run_writes_what_the_run_would_have_written(env, monkeypatch, capsys,
                                                            with_plan):
    """The rebuilt costs row is the one the same run writes when nothing fails, but for its
    timestamp, its latency and the note that says it was added afterwards; summary.json is
    byte for byte the same; meta.json the same but for its times and `recovered`. Then the
    lock and the reservation are released, the run is the last paid run, and the next paid
    run may start. A run without run_plan.json (as the incident's) is accounted for with its
    `run` arguments and git state given again."""
    normal = _normal(env)
    world = _incident(env, monkeypatch)
    out, raw = env.dirs()
    git = runmeta.git_state()
    lock_started = json.loads(world.lock.read_text(encoding="utf-8"))["started_utc"]
    args = []
    if not with_plan:
        (raw / runner.RUN_PLAN).unlink()
        args = [*RUN_ARGS, "--git-commit", git["git_commit"],
                "--git-dirty", str(git["git_dirty"]).lower()]
    capsys.readouterr()
    assert _account(*args) == 0
    printed = capsys.readouterr()

    (row,) = world.rows()
    for k in costs.COLUMNS:
        if k not in ("timestamp_utc", "latency_s", "notes"):
            assert row[k] == normal["row"][k], k
    assert row["reasoning_tokens"] == "" and blinding.WITHHELD_NOTE in row["notes"]
    suffix = row["notes"][len(normal["row"]["notes"]):]
    assert row["notes"].startswith(normal["row"]["notes"])
    assert suffix.startswith("; added by account-run on ")
    assert f"returned non-zero exit status {INCIDENT_EXIT}" in suffix
    assert "timestamp_utc is the raw transcript's last write" in suffix
    mtime = os.path.getmtime(raw / "transcript.jsonl.gz")
    assert row["timestamp_utc"] == datetime.fromtimestamp(mtime, UTC).isoformat(
        timespec="seconds")
    assert row["latency_s"] == "0.000"  # the runner's timings (fixed clock)

    assert (out / "summary.json").read_bytes() == normal["summary"]
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert ({k: v for k, v in meta.items() if k not in VOLATILE_META}
            == {k: v for k, v in normal["meta"].items() if k not in VOLATILE_META})
    assert meta["git_commit"] == git["git_commit"] and meta["finished_utc"] == (
        row["timestamp_utc"])
    recovered = meta["recovered"]
    assert recovered["by"] == "harnesses account-run"
    assert recovered["settings_from"] == ("run_plan.json" if with_plan else "the command line")
    assert set(recovered["approximate"]) >= {"finished_utc", "costs_row_timestamp_utc",
                                             "costs_row_latency_s"}
    assert ("started_utc" in recovered["approximate"]) is not with_plan
    if with_plan:
        plan = json.loads((raw / runner.RUN_PLAN).read_text(encoding="utf-8"))
        assert meta["started_utc"] == plan["started_utc"]
    else:  # the lock's start time, taken a moment before run_batch's
        assert meta["started_utc"] == lock_started
    assert json.loads((raw / runner.PARALLEL_INFO).read_text(encoding="utf-8")) == (
        meta["parallel"]) == {"max_episodes_in_flight": 1}

    assert not world.lock.exists() and not world.reservation.exists()
    last = json.loads(paidlock.last_run_path(world.lock, cli.STREAM).read_text(
        encoding="utf-8"))
    assert last["run_id"] == RID and last["row_timestamp_utc"] == row["timestamp_utc"]
    for line in ("done: append the costs row", "done: release the kept lock"):
        assert line in printed.out
    # pilot blinding (PREREG §11): no token or cost value printed, but the number of calls
    text = printed.out + printed.err
    for value in [*_token_totals(raw), row["cost_usd_list"], row["cost_usd_billed_est"]]:
        assert not _printed(env, text, value), value
    assert f"{row['n_calls']} calls" in text

    # the next paid run's guard passes: the run is accounted for
    assert _run(RUN_ARGS, "after") == 0
    assert [r["run_id"] for r in world.rows()] == [RID, "after"]


def test_a_plan_from_before_gen_preset_rebuilds_with_the_default_config(env, monkeypatch,
                                                                         capsys):
    """A run plan written before --gen-preset existed (PREREG §17.3) has no `gen_preset` in
    its run arguments: account-run takes `run`'s default for it, "default", and rebuilds the
    run's episodes with the default config. A plan that names sol-chain rebuilds those."""
    world = _incident(env, monkeypatch)
    _, raw = env.dirs()
    plan = json.loads((raw / runner.RUN_PLAN).read_text(encoding="utf-8"))
    assert plan["run_args"]["gen_preset"] == "default"
    del plan["run_args"]["gen_preset"]
    _edit_json(raw / runner.RUN_PLAN, run_args=plan["run_args"])
    capsys.readouterr()
    assert _account("--check") == 0
    assert "--check: nothing written" in capsys.readouterr().out
    assert _account("--gen-preset", "sol-chain", "--check") == 2   # differs from the plan's
    assert "--gen-preset" in capsys.readouterr().err
    assert _account() == 0 and len(world.rows()) == 1


def test_check_writes_nothing(env, monkeypatch, capsys):
    world = _incident(env, monkeypatch)
    before = _files(env.tmp)
    capsys.readouterr()
    assert _account("--check") == 0
    printed = capsys.readouterr()
    assert _files(env.tmp) == before
    assert printed.out.rstrip().endswith("--check: nothing written")
    out, raw = env.dirs()
    for line in (f"run {RID}: persistgym_pilot: F-0 on gpt-6-luna, 2 episodes; 2 in episodes",
                 'exit reason: COMPLETED; episode exit reasons: {"DONE": 2}; excluded: 0',
                 str(world.costs), str(out / "meta.json"), str(raw / runner.PARALLEL_INFO),
                 "cost_usd_billed_est=<withheld>", "n_calls match", "reasoning_tokens match",
                 "the transcript, episodes.jsonl and the run's settings agree call by call"):
        assert line in printed.out, line
    for value in _token_totals(raw):
        assert not _printed(env, printed.out + printed.err, value), value
    # and it is repeatable, then the real thing goes through
    assert _account("--check") == 0 and _account() == 0 and len(world.rows()) == 1


def test_a_non_blinded_run(tmp_path, monkeypatch, capsys):
    """A validity run commits episodes.jsonl and keeps reasoning tokens in its row and
    meta.json; account-run rebuilds those too, writes no raw parallel.json (run_batch writes
    it for pilots only) and still prints no reasoning-token value."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    monkeypatch.setattr(runner, "CLOCK", lambda: 0.0)
    monkeypatch.setattr(paidlock, "holder_alive", lambda info: None)
    # luna's validity runs ran before R6's guard refused new ones (registered.luna_refusal);
    # account-run applies no guard
    monkeypatch.setattr(registered, "check_run_settings", lambda *a, **k: None)
    env = Env(tmp_path, monkeypatch,
              experiments=("persistgym_pilot", "persistgym_validity"))
    normal = _normal(env, VALIDITY_ARGS, experiment="persistgym_validity")
    world = _incident(env, monkeypatch, VALIDITY_ARGS)
    out, raw = env.dirs(experiment="persistgym_validity")
    assert (out / "episodes.jsonl").exists() and not (raw / "episodes.jsonl").exists()
    capsys.readouterr()
    assert _account() == 0
    printed = capsys.readouterr()
    (row,) = world.rows()
    assert int(row["reasoning_tokens"]) > 0
    for k in costs.COLUMNS:
        if k not in ("timestamp_utc", "latency_s", "notes"):
            assert row[k] == normal["row"][k], k
    assert (out / "summary.json").read_bytes() == normal["summary"]
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert ({k: v for k, v in meta.items() if k not in VOLATILE_META}
            == {k: v for k, v in normal["meta"].items() if k not in VOLATILE_META})
    assert meta["tokens"]["reasoning_tokens"] == int(row["reasoning_tokens"])
    assert not (raw / runner.PARALLEL_INFO).exists() and "blinding" not in meta
    assert not _printed(env, printed.out + printed.err, row["reasoning_tokens"])
    assert f"output_tokens={row['output_tokens']}" in printed.out  # not blinded
    assert not world.lock.exists()


def test_a_failure_after_the_row_says_what_remains_and_keeps_the_lock(env, monkeypatch,
                                                                      capsys):
    world = _incident(env, monkeypatch)
    real_write_meta = runner._write_meta

    def disk_full(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(runner, "_write_meta", disk_full)
    capsys.readouterr()
    assert _account() == 1
    err = capsys.readouterr().err
    assert [r["run_id"] for r in world.rows()] == [RID]
    assert "  done: append the costs row" in err and "  done: write " in err
    assert "  NOT done: write " in err and "meta.json" in err.split("NOT done:")[1]
    assert "NOT done: release the kept lock" in err and "do not add it again" in err
    held = json.loads(world.lock.read_text(encoding="utf-8"))
    assert "account-run appended run" in held["kept_because"]
    assert "do not add it again" in held["kept_because"] and world.reservation.exists()
    # a second try refuses: the row is there
    monkeypatch.setattr(runner, "_write_meta", real_write_meta)
    assert _account() == 2
    assert "already has a row" in capsys.readouterr().err
    assert len(world.rows()) == 1


def test_a_row_that_cannot_be_appended_leaves_everything_as_it_was(env, monkeypatch, capsys):
    """The first write fails (the ledger open in another program, say): nothing is written,
    and the lock and the reservation are left as they were, so account-run can run again."""
    world = _incident(env, monkeypatch)
    real = costs.append_row

    def locked(row, path):
        raise PermissionError("the ledger is open in another program")
    monkeypatch.setattr(costs, "append_row", locked)
    before = _files(env.tmp)
    capsys.readouterr()
    assert _account() == 1
    err = capsys.readouterr().err
    assert "NOT done: append the costs row" in err and "nothing was written" in err
    assert _files(env.tmp) == before
    monkeypatch.setattr(costs, "append_row", real)
    assert _account() == 0 and len(world.rows()) == 1 and not world.lock.exists()


# --- refusals: nothing written ----------------------------------------------------------------

def _edit_json(path: Path, **changes) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    for k, v in changes.items():
        if v is None:
            doc.pop(k, None)
        else:
            doc[k] = v
    path.write_text(json.dumps(doc), encoding="utf-8")


def _kept(world: World) -> str:
    return json.loads(world.lock.read_text(encoding="utf-8"))["kept_because"]


def _episodes_lines(env: Env) -> list[str]:
    return (env.dirs()[1] / "episodes.jsonl").read_text(encoding="utf-8").splitlines(True)


def _set_episodes(env: Env, lines: list[str]) -> None:
    (env.dirs()[1] / "episodes.jsonl").write_text("".join(lines), encoding="utf-8")


def _totals_off(world: World) -> None:
    why = _kept(world)
    i = why.index("these totals: ") + len("these totals: ")
    totals, end = json.JSONDecoder().raw_decode(why, i)
    totals["input_tokens"] += 1
    _edit_json(world.lock, kept_because=why[:i] + json.dumps(totals) + why[end:])


def _echo_off(env: Env) -> None:
    records = _transcript(env.dirs()[1])
    records[3]["echo"]["context_echoed"] = "all_turns"
    _write_transcript(env.dirs()[1], records)


def _written_after_the_lock(env: Env, world: World) -> None:
    later = world.lock.stat().st_mtime + 60
    os.utime(env.dirs()[1] / "transcript.jsonl.gz", (later, later))


def _usage_off(env: Env) -> None:
    lines = _episodes_lines(env)
    rec = json.loads(lines[1])
    rec["usage"]["input_tokens"] += 1
    _set_episodes(env, [lines[0], json.dumps(rec) + "\n", *lines[2:]])


REFUSALS = {
    "row already in costs.csv": (
        lambda env, w, mp: costs.append_row(
            {**{c: "" for c in costs.COLUMNS}, "run_id": RID, "experiment": "persistgym_pilot",
             "cost_usd_list": "0.1", "cost_usd_billed_est": "0.05"}, w.costs),
        "already has a row of run"),
    "lock of another run": (lambda env, w, mp: _edit_json(w.lock, run_id="other-run"),
                            "is held by run 'other-run'"),
    "no lock": (lambda env, w, mp: w.lock.unlink(), "no PersistGym paid-run lock"),
    "lock not kept": (lambda env, w, mp: _edit_json(w.lock, kept_because=None),
                      "but not kept"),
    "lock marked hold_not_recorded": (
        lambda env, w, mp: _edit_json(w.lock, **{paidlock.HOLD_NOT_RECORDED: True}),
        paidlock.HOLD_NOT_RECORDED),
    "calls abandoned in flight": (
        lambda env, w, mp: _edit_json(w.lock, kept_because=_kept(w).replace(
            " does not show", " does not show and still had 2 paid calls in flight")),
        "paid calls in flight when it ended"),
    "rebuilt totals differ": (lambda env, w, mp: _totals_off(w),
                              ("rebuilt totals differ from those the run kept in its paid-run "
                               "lock in input_tokens")),
    "reservation of another run": (
        lambda env, w, mp: _edit_json(w.reservation, run_id="other-run"),
        "is not this run's (run_id differ)"),
    "ledger of another checkout": (
        lambda env, w, mp: mp.setattr(cli, "COSTS_PATH", World(env.tmp, "other").costs),
        "run account-run from the checkout the run was started from"),
    "transcript missing": (lambda env, w, mp: (env.dirs()[1] / "transcript.jsonl.gz").unlink(),
                           "transcript.jsonl.gz is missing"),
    "episodes.jsonl missing": (lambda env, w, mp: (env.dirs()[1] / "episodes.jsonl").unlink(),
                               "episodes.jsonl is missing"),
    "summary.json written already": (
        lambda env, w, mp: (env.dirs()[0] / "summary.json").write_text("{}", encoding="utf-8"),
        "exist already"),
    "in-flight spool folder": (
        lambda env, w, mp: (env.dirs()[1] / runner.INFLIGHT_DIR).mkdir(),
        "in-flight spool folder"),
    "an episode twice": (lambda env, w, mp: _set_episodes(env, _episodes_lines(env)[:1] * 2),
                         "more than once"),
    "episodes out of order": (
        lambda env, w, mp: _set_episodes(env, _episodes_lines(env)[::-1]),
        "not the run's, in its order"),
    "a recorded echo that is not the response's": (lambda env, w, mp: _echo_off(env),
                                                   "the recorded echo is not the response's"),
    "an episode's usage that is not its calls'": (lambda env, w, mp: _usage_off(env),
                                                  "its usage is not the sum"),
    "a transcript written after the lock was kept": (
        lambda env, w, mp: _written_after_the_lock(env, w), "after the paid-run lock was kept"),
    "run plan holds no arguments and none given": (
        lambda env, w, mp: (env.dirs()[1] / runner.RUN_PLAN).unlink(),
        "the run has no run_plan.json with its arguments"),
}


@pytest.mark.parametrize("case", list(REFUSALS))
def test_refusals_write_nothing(env, monkeypatch, capsys, case):
    world = _incident(env, monkeypatch)
    change, message = REFUSALS[case]
    change(env, world, monkeypatch)
    before = _files(env.tmp)
    capsys.readouterr()
    assert _account() == 2
    err = capsys.readouterr().err
    assert err.startswith("refused: ") and message in err, err
    assert _files(env.tmp) == before


def test_refused_while_the_holder_may_still_run(env, monkeypatch, capsys):
    """The real check: the lock names this test's own process, which is running."""
    world = _incident(env, monkeypatch)
    _edit_json(world.lock, pid=os.getpid(), host=socket.gethostname(),
               started_utc=runmeta.utc_now())
    monkeypatch.setattr(paidlock, "holder_alive", REAL_HOLDER_ALIVE)
    before = _files(env.tmp)
    assert _account() == 2
    assert f"process {os.getpid()}, which took the lock, is still running" in (
        capsys.readouterr().err)
    assert _files(env.tmp) == before


@pytest.mark.parametrize("args, message", [
    (["--n", "2"], "--n differ from the run's run_plan.json"),
    (["--git-commit", "0" * 40, "--git-dirty", "false"],
     "differ from the git state the run read at its start"),
    (["--git-commit", "0" * 40], "give --git-commit and --git-dirty together"),
])
def test_arguments_that_differ_from_the_run_plan_refuse(env, monkeypatch, capsys, args,
                                                        message):
    _incident(env, monkeypatch)
    before = _files(env.tmp)
    assert _account(*args) == 2
    assert message in capsys.readouterr().err
    assert _files(env.tmp) == before


@pytest.mark.parametrize("args, message", [
    (RUN_ARGS, "give the git state it read, --git-commit"),
    ([a for a in RUN_ARGS if a != "derived-rec-far"] + ["--git-commit", "GIT", "--git-dirty",
                                                        "true"],
     "the run arguments describe 'persistgym_pilot: F-0 on gpt-6-luna, 1 episodes'"),
    (RUN_ARGS + ["--effort", "high", "--git-commit", "GIT", "--git-dirty", "true"],
     "the request's effort differ from the run's settings"),
    (RUN_ARGS + ["--git-commit", "f" * 40, "--git-dirty", "true"],
     "is not a commit of this repository"),
    (RUN_ARGS + ["--git-commit", "GIT", "--git-dirty", "true",
                 "--started-utc", "2099-01-01T00:00:00+00:00"],
     "before the run started (2099-01-01T00:00:00+00:00)"),
])
def test_a_run_without_its_plan_needs_its_arguments(env, monkeypatch, capsys, args, message):
    """Given the arguments the run was started with, the episodes, settings and git state are
    checked against the run's own files; wrong ones refuse."""
    _incident(env, monkeypatch)
    (env.dirs()[1] / runner.RUN_PLAN).unlink()
    args = [runmeta.git_state()["git_commit"] if a == "GIT" else a for a in args]
    before = _files(env.tmp)
    assert _account(*args) == 2
    assert message in capsys.readouterr().err
    assert _files(env.tmp) == before


EARLIER = "2026-01-01T00:00:00+00:00"


def test_git_dirty_false_after_an_uncommitted_costs_row_refuses(env, monkeypatch, capsys):
    """The incident's F-0 run started seconds after the F-r run had appended its row to
    results/costs.csv, uncommitted: a tracked file differed from the commit, so the git
    state it would have read says dirty, as for every run started after an uncommitted row.
    Given --git-dirty false, account-run sees the earlier row in the ledger, which the
    commit's results/costs.csv lacks, and refuses; --git-dirty true goes through."""
    world = env.use(World(env.tmp, "incident"))
    assert _run(RUN_ARGS, "before") == 0   # the F-r run: its row, not in any commit
    # its row was written before the incident run started (whole seconds: set it earlier)
    text = world.costs.read_text(encoding="utf-8")
    (stamp,) = [r["timestamp_utc"] for r in world.rows()]
    world.costs.write_text(text.replace(stamp, EARLIER), encoding="utf-8")
    _edit_json(paidlock.last_run_path(world.lock, cli.STREAM), row_timestamp_utc=EARLIER)
    _incident(env, monkeypatch, world=world)
    out, raw = env.dirs()
    (raw / runner.RUN_PLAN).unlink()
    args = [*RUN_ARGS, "--git-commit", runmeta.git_state()["git_commit"], "--git-dirty"]
    before = _files(env.tmp)
    capsys.readouterr()
    assert _account(*args, "false") == 2
    err = capsys.readouterr().err
    assert "--git-dirty false, but when the run started" in err and "(before)" in err, err
    assert _files(env.tmp) == before
    assert _account(*args, "true") == 0
    row = world.rows()[-1]
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert row["run_id"] == RID and "git_dirty=True" in row["notes"]
    assert meta["git_dirty"] is True and not world.lock.exists()


SOL_RID = "20261002T180358Z-F-0-gpt-6.1-sol"
CHECK_ARGS = ["--model", "gpt-6.1-sol", "--effort", "high", "--split", "pilot", "--start", "0",
              "--n", "2", "--task-cell", "observed-nonrec-far", "observed-rec-far",
              "derived-nonrec-far", "derived-rec-far", "--experiment", "persistgym_pilot",
              "--approved-block", "1-pilots", "--planned-usd", "6"]
# The order of the incident run's episodes.jsonl (episode ids only, read from its raw file),
# which is that of the F-r run's committed meta.json
CHECK_EPISODES = [f"pilot-00000{t}/{c}/base" for t in (0, 1) for c in (
    "observed-nonrec-far", "observed-rec-far", "derived-nonrec-far", "derived-rec-far")]


def test_the_incident_command(env, monkeypatch, capsys):
    """The 2026-10-02 incident as it happened, with the fake model: the engagement check's
    F-r run writes its row (left uncommitted), then the F-0 run's row cannot be written.
    The account-run command for the real run (harnesses/DESIGN.md §8.1) parses, rebuilds
    the 8 episodes in the run's order, refuses --git-dirty false (the F-r row was in the
    ledger, uncommitted, when F-0 started) and goes through with --git-dirty true."""
    world = env.use(World(env.tmp, "incident"))
    # the incident's runs played the default config, before R3's guard sent every sol pilot
    # at high effort to sol-chain (PREREG §17.3); account-run applies no guard
    monkeypatch.setattr(registered, "check_run_settings", lambda *a, **k: None)
    assert _run(["--cell", "F-r", *CHECK_ARGS], "20261002T173710Z-F-r-gpt-6.1-sol") == 0
    # the F-r row was written seconds before F-0 started (whole seconds: set it earlier)
    text = world.costs.read_text(encoding="utf-8")
    (stamp,) = [r["timestamp_utc"] for r in world.rows()]
    world.costs.write_text(text.replace(stamp, EARLIER), encoding="utf-8")
    _edit_json(paidlock.last_run_path(world.lock, cli.STREAM), row_timestamp_utc=EARLIER)
    _incident(env, monkeypatch, ["--cell", "F-0", *CHECK_ARGS], rid=SOL_RID, world=world)
    out, raw = env.dirs(rid=SOL_RID)
    (raw / runner.RUN_PLAN).unlink()   # the incident's run predates run plans
    command = ["account-run", SOL_RID, "--check", "--cell", "F-0", *CHECK_ARGS,
               "--git-commit", runmeta.git_state()["git_commit"], "--git-dirty"]
    before = _files(env.tmp)
    capsys.readouterr()
    assert cli.main([*command, "false"]) == 2
    assert "--git-dirty false, but when the run started" in capsys.readouterr().err
    assert cli.main([*command, "true"]) == 0
    printed = capsys.readouterr().out
    assert _files(env.tmp) == before
    assert (f"run {SOL_RID}: persistgym_pilot: F-0 on gpt-6.1-sol, 8 episodes; 8 in "
            "episodes.jsonl") in printed and "gpt-6.1-sol at effort high" in printed
    assert cli.main([c for c in command if c != "--check"] + ["true"]) == 0
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["config"]["episode_ids"] == CHECK_EPISODES and meta["git_dirty"] is True
    assert meta["reasoning_effort"] == "high" and meta["exit_reason"] == "COMPLETED"
    rows = world.rows()
    assert [r["run_id"] for r in rows] == ["20261002T173710Z-F-r-gpt-6.1-sol", SOL_RID]
    assert rows[1]["notes"].startswith("approved_block=1-pilots; context_mismatches=0; "
                                       "effort_mismatches=0; git_dirty=True; pilot 0-1 "
                                       "matrix=full; " + blinding.WITHHELD_NOTE)
    assert rows[1]["reasoning_tokens"] == "" and not world.lock.exists()
    assert not world.reservation.exists()


def test_uncommitted_rows_are_the_ledger_rows_the_commit_lacks():
    """`_uncommitted_rows`: rows written before the start that the commit's
    results/costs.csv does not hold, by run id and timestamp. A committed row, a row written
    after the start and a row with no time zone do not count."""
    head = runmeta.git_state()["git_commit"]
    committed = list(csv.DictReader(io.StringIO(runmeta.run_git(
        "show", f"{head}:results/costs.csv"))))
    assert committed, "this repository's results/costs.csv has rows"
    rows = [committed[0],
            {"run_id": "uncommitted", "timestamp_utc": EARLIER},
            {"run_id": "after", "timestamp_utc": "2099-01-01T00:00:01+00:00"},
            {"run_id": "no-zone", "timestamp_utc": "2026-01-01T00:00:00"},
            {"run_id": "no-time", "timestamp_utc": ""},
            {**committed[0], "timestamp_utc": EARLIER}]   # same run id, another row
    assert account._uncommitted_rows(rows, head, "2099-01-01T00:00:00+00:00") == [
        "uncommitted", committed[0]["run_id"]]
    # a tree without results/costs.csv (here git's empty tree): nothing to compare with
    assert account._uncommitted_rows(rows, "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
                                     "2099-01-01T00:00:00+00:00") == []


def test_a_parallel_run_is_not_supported(env, monkeypatch, capsys):
    _incident(env, monkeypatch, [*RUN_ARGS, "--parallel", "2"])
    before = _files(env.tmp)
    assert _account() == 2
    assert "accounting for a run played in parallel is not supported" in (
        capsys.readouterr().err)
    assert _files(env.tmp) == before


# --- the root cause: the git state is read at the start, the run plan written before -------

def test_no_process_starts_after_the_first_paid_call(env, monkeypatch):
    """The incident's process could start no child after its calls. Now the git state is read
    once, before the first call, and nothing after the calls starts a process: with every
    process start failing from the first call on, the run still writes its row and meta.json
    and releases its lock."""
    world = env.use(World(env.tmp, "w"))
    reads = []
    real_git_state = runmeta.git_state

    def git_state(repo=runmeta.REPO_ROOT):
        reads.append(len(env.calls))
        return real_git_state(repo)
    monkeypatch.setattr(runmeta, "git_state", git_state)

    class NoConsole(subprocess.Popen):
        def __init__(self, *a, **k):
            if env.calls:
                raise OSError(f"[WinError {INCIDENT_EXIT}] a process started after the first "
                              "paid call")
            super().__init__(*a, **k)
    monkeypatch.setattr(subprocess, "Popen", NoConsole)
    assert _run(RUN_ARGS) == 0
    assert reads == [0] and env.calls
    (row,) = world.rows()
    meta = json.loads((env.dirs()[0] / "meta.json").read_text(encoding="utf-8"))
    with pytest.raises(OSError, match="after the first paid call"):  # the patch holds
        subprocess.run(["git", "--version"], capture_output=True, check=False)
    monkeypatch.setattr(subprocess, "Popen", NoConsole.__mro__[1])
    git = real_git_state()
    assert row["git_commit"] == meta["git_commit"] == git["git_commit"]
    assert meta["git_dirty"] == git["git_dirty"]
    assert f"git_dirty={git['git_dirty']}" in row["notes"]
    assert not world.lock.exists() and not world.reservation.exists()


def test_the_run_plan_is_written_before_the_first_call(env, monkeypatch):
    world = env.use(World(env.tmp, "w"))
    seen = []

    def first_call(n):
        if n == 0:
            raw = env.dirs()[1]
            seen.append(json.loads((raw / runner.RUN_PLAN).read_text(encoding="utf-8")))
            seen.append(json.loads(world.reservation.read_text(encoding="utf-8")))
            seen.append(sorted(p.name for p in raw.iterdir()))
    env.on_call = first_call
    assert _run(RUN_ARGS) == 0
    plan, reservation, files = seen
    # nothing else yet: the transcript and episodes.jsonl are open, still empty
    assert files == ["episodes.jsonl", runner.RUN_PLAN, "transcript.jsonl.gz"]
    assert sorted(plan) == sorted([
        "plan_version", "run_id", "experiment", "milestone", "run_args", "harness_cell",
        "harness_config", "run_matrix", "episode_ids", "repeat_index", "notes",
        "abort_after_api_errors", "parallel", "git", "started_utc", "reservation_id",
        "prereg_version", "sdk_versions", "code_version"])
    assert plan["run_id"] == RID and plan["reservation_id"] == reservation["reservation_id"]
    assert plan["git"] == runmeta.git_state() and plan["notes"] == "pilot 0-0 matrix=full"
    assert plan["run_args"] == {
        "cell": "F-0", "split": "pilot", "start": 0, "variant": "base", "W": None,
        "gen_preset": "default", "gen_set": SMALL[1::2], "model": "gpt-6-luna",
        "effort": "medium",
        "mode": "standard", "service_tier": "flex", "milestone": "M0",
        "approved_block": "1-pilots", "planned_usd": 1.0, "n": 1,
        "task_cell": ["observed-nonrec-far", "derived-rec-far"], "matrix": "full",
        "n_observed": None, "cell_templates": None, "experiment": "persistgym_pilot",
        "parallel": 1}
    meta = json.loads((env.dirs()[0] / "meta.json").read_text(encoding="utf-8"))
    assert plan["episode_ids"] == meta["config"]["episode_ids"]
    assert plan["started_utc"] == meta["started_utc"]
    assert plan["harness_config"] == meta["config"]["harness"]
    # no outcome: nothing in it names a result of an episode
    text = json.dumps(plan)
    for word in ("need_correct", "need_phase", "exit_reason", '"usage"', "reasoning_tokens",
                 "cost_usd"):
        assert word not in text, word


def test_a_run_whose_git_state_cannot_be_read_spends_nothing(env, monkeypatch, capsys):
    world = env.use(World(env.tmp, "w"))

    def fails(repo=runmeta.REPO_ROOT):
        raise subprocess.CalledProcessError(INCIDENT_EXIT, ["git", "rev-parse", "HEAD"])
    monkeypatch.setattr(runmeta, "git_state", fails)
    assert _run(RUN_ARGS) == 2
    assert "cannot read the git state of the code" in capsys.readouterr().err
    assert env.calls == [] and world.rows() == []
    assert not world.lock.exists() and not world.reservation.exists()
