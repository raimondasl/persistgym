"""The repeat of PREREG §2.9 (D7; §0.3 line 10) end to end, with no network: `run
--repeat-index 1` plays, of its matrix, only the main templates whose seed is divisible by 10,
in the same task cells and variant: the same episodes and payloads as the repeat-0 run, played
again. Its run id, run plan, meta.json, episode records and costs-row notes say repeat_index
1; a repeat-0 run writes what it wrote before the option existed. `account-run` rebuilds a
repeat-1 run as one. The real guarded transport is built with a stub client answered by the
fake model, as in test_cli_end_to_end.py; every lock, ledger and run folder is temporary.

luna's main sweep plays the default config (registered.luna_refusal); these runs play the
small volume, so the tests record luna's G1 on the small config instead."""

from __future__ import annotations

import gzip
import json

import pytest

from common import costs, paidlock, runmeta
from common.tests.gitrepo import FROZEN_PREREG, decisions_text, guarded_repo
from harnesses import cli, registered, runner
from harnesses.fake import FakeModel
from harnesses.openai_transport import ALLOW_ENV, OpenAIResponsesTransport
from harnesses.tests.test_account_run import (
    RID,
    VOLATILE_META,
    Env,
    _account,
    _incident,
    _normal,
)
from harnesses.tests.test_cli_end_to_end import _FakeBackedClient

LUNA = "gpt-6-luna"
SMALL = ["--gen-set", "W_tokens=6400", "--gen-set", "v_tokens=400",
         "--gen-set", "assumed_max_reply_tokens=200"]
MAIN = ["run", "--cell", "F-0", "--model", LUNA, "--split", "main", "--start", "0", "--n",
        "11", "--task-cell", "observed-nonrec-far", *SMALL, "--experiment", "persistgym",
        "--approved-block", "3-persistgym", "--planned-usd", "1"]
REPEATED = ["main-000000/observed-nonrec-far/base", "main-000010/observed-nonrec-far/base"]


def _luna_g1_on_the_small_config(monkeypatch) -> str:
    """luna's guard (registered.luna_refusal) with its config and G1 on the small volume."""
    small = runmeta.config_hash(cli._gen_config("default", SMALL[1::2]).to_dict())
    monkeypatch.setattr(registered, "LUNA_GENERATOR_HASH", small)
    monkeypatch.setitem(registered.G1_PASSED, LUNA, small)
    return small


@pytest.fixture
def main_env(tmp_path, monkeypatch):
    """A paid-run setup approving block 3-persistgym for experiment persistgym, whose fake
    answers by payload (so an episode's calls do not depend on the episodes before it) and
    whose call clock is fixed."""
    guarded_repo(tmp_path, prereg=FROZEN_PREREG,
                 decisions=decisions_text("3-persistgym", experiments=("persistgym",)))
    costs_csv = tmp_path / "costs.csv"
    costs_csv.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    monkeypatch.setenv(ALLOW_ENV, "1")
    monkeypatch.setattr(cli, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(cli, "RAW", tmp_path / "raw")
    (tmp_path / "lock").mkdir()
    monkeypatch.setattr(cli, "LOCK_PATH", tmp_path / "lock" / paidlock.lock_name(cli.STREAM))
    monkeypatch.setattr(runner, "CLOCK", lambda: 0.0)
    fakes = []

    def transport(**kw):
        fakes.append(FakeModel(ids="payload"))
        return OpenAIResponsesTransport(
            **kw, costs_path=costs_csv, repo=tmp_path,
            client_factory=lambda timeout, fake=fakes[-1]: _FakeBackedClient(fake))
    monkeypatch.setattr(cli, "OpenAIResponsesTransport", transport)
    _luna_g1_on_the_small_config(monkeypatch)
    return tmp_path, costs_csv


def _jsonl(path) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def test_a_repeat_run_replays_its_repeat_0_episodes(main_env):
    tmp, costs_csv = main_env
    assert cli.main([*MAIN, "--run-id", "r0"]) == 0
    assert cli.main([*MAIN, "--repeat-index", "1", "--run-id", "r1"]) == 0
    assert cli.main([*MAIN, "--repeat-index", "1", "--parallel", "2", "--run-id", "r1p"]) == 0
    out, raw = tmp / "results" / "persistgym", tmp / "raw" / "persistgym"

    # episode records: repeat 0 unchanged (no field); repeat 1 the same records plus
    # repeat_index last, for templates 0 and 10 only
    r0 = {r["episode_id"]: r for r in _jsonl(out / "r0" / "episodes.jsonl")}
    assert len(r0) == 11 and not [r for r in r0.values() if "repeat_index" in r]
    r1 = _jsonl(out / "r1" / "episodes.jsonl")
    assert [r["episode_id"] for r in r1] == REPEATED
    for rec in r1:
        assert list(rec)[-1] == "repeat_index" and rec == {**r0[rec["episode_id"]],
                                                           "repeat_index": 1}
    # parallel play writes the same, byte for byte
    assert (out / "r1p" / "episodes.jsonl").read_bytes() == (
        out / "r1" / "episodes.jsonl").read_bytes()
    assert (out / "r1p" / "summary.json").read_bytes() == (
        out / "r1" / "summary.json").read_bytes()

    # the same episodes: every request of a repeated episode is its repeat-0 request
    calls0, calls1 = _jsonl(raw / "r0" / "transcript.jsonl.gz"), _jsonl(
        raw / "r1" / "transcript.jsonl.gz")
    assert [c["payload"] for c in calls1] == [c["payload"] for c in calls0
                                              if c["episode_id"] in REPEATED]

    # meta.json and the run plan
    meta0, meta1 = (json.loads((out / r / "meta.json").read_text(encoding="utf-8"))
                    for r in ("r0", "r1"))
    assert (meta0["repeat_index"], meta1["repeat_index"]) == (0, 1)
    assert meta0["config"]["run_matrix"] == {
        "name": "full", "templates_per_task_cell": {"observed-nonrec-far": 11},
        "n_templates": 11, "n_episodes": 11}
    assert meta1["config"]["run_matrix"] == {
        **meta0["config"]["run_matrix"], "n_episodes": 2, "repeat_index": 1,
        "repeat_every": 10, "template_offsets": [0, 10]}
    assert meta1["config"]["episode_ids"] == REPEATED and meta1["n_episodes_run"] == 2
    assert meta1["template_id"] == ["main-000000", "main-000010"]
    assert meta1["seeds"] == {"template_seeds": [0, 10]}
    assert meta1["config_hash"] != meta0["config_hash"]
    plan0, plan1 = (json.loads((raw / r / runner.RUN_PLAN).read_text(encoding="utf-8"))
                    for r in ("r0", "r1"))
    assert (plan0["repeat_index"], plan1["repeat_index"]) == (0, 1)
    assert "repeat_index" not in plan0["run_args"] and plan1["run_args"]["repeat_index"] == 1
    assert plan1["run_matrix"] == meta1["config"]["run_matrix"]
    assert plan1["episode_ids"] == REPEATED

    # the costs rows' notes
    rows = {r["run_id"]: r for r in costs.read_rows(costs_csv)}
    assert rows["r0"]["notes"].endswith("; main 0-10 matrix=full")
    assert "repeat" not in rows["r0"]["notes"]
    assert rows["r1"]["notes"].endswith("; main 0-10 matrix=full repeat_index=1")
    assert rows["r1p"]["notes"].endswith("; main 0-10 matrix=full repeat_index=1 parallel=2")
    assert rows["r1"]["n_calls"] == str(len(calls1))


@pytest.mark.parametrize(("args", "message"), [
    (["--split", "validity", "--experiment", "persistgym_validity"], "main templates only"),
    (["--start", "1", "--n", "9"], "would play nothing"),
    (["--start", "41", "--n", "5"], "would play nothing")])
def test_a_repeat_refuses_before_the_lock(main_env, monkeypatch, capsys, args, message):
    def no_lock(*a, **k):
        raise AssertionError("must not take the paid-run lock")
    monkeypatch.setattr(paidlock, "paid_run_lock", no_lock)
    assert cli.main([*MAIN, "--repeat-index", "1", *args]) == 2
    err = capsys.readouterr().err
    assert err.startswith("refused:") and message in err


def test_a_pilot_has_no_repeat(main_env, monkeypatch, capsys):
    """Pilot templates are pilot data and have no repeat; nor is there a repeat 2."""
    def no_lock(*a, **k):
        raise AssertionError("must not take the paid-run lock")
    monkeypatch.setattr(paidlock, "paid_run_lock", no_lock)
    assert cli.main(["run", "--cell", "F-0", "--model", LUNA, "--n", "1", *SMALL,
                     "--approved-block", "1-pilots", "--planned-usd", "1",
                     "--repeat-index", "1"]) == 2
    assert "main templates only" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        cli.parse_args([*MAIN, "--repeat-index", "2"])
    assert cli.parse_args(MAIN).repeat_index == 0


@pytest.mark.parametrize("with_plan", [True, False], ids=["run-plan", "no-run-plan"])
def test_account_run_rebuilds_a_repeat_run(tmp_path, monkeypatch, capsys, with_plan):
    """A repeat-1 run whose costs row could not be written: account-run rebuilds its repeat
    episodes, row, summary.json and meta.json as the same run writes them when nothing
    fails. Its plan says repeat 1, so --repeat-index 0 differs from it; without the plan the
    arguments are given again, --repeat-index 1 included (without it they describe the 11
    repeat-0 episodes, not the run's 2)."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    monkeypatch.setattr(runner, "CLOCK", lambda: 0.0)
    monkeypatch.setattr(paidlock, "holder_alive", lambda info: None)
    env = Env(tmp_path, monkeypatch, experiments=("persistgym_pilot", "persistgym"))
    _luna_g1_on_the_small_config(monkeypatch)
    # Env approves block 1-pilots for the experiments it is given
    main = [a if a != "3-persistgym" else "1-pilots" for a in MAIN[1:]]
    args = [*main, "--repeat-index", "1"]
    normal = _normal(env, args, experiment="persistgym")
    world = _incident(env, monkeypatch, args)
    out, raw = env.dirs(experiment="persistgym")
    plan = json.loads((raw / runner.RUN_PLAN).read_text(encoding="utf-8"))
    assert plan["repeat_index"] == 1 and plan["episode_ids"] == REPEATED
    capsys.readouterr()
    if with_plan:
        assert _account("--repeat-index", "0", "--check") == 2
        assert "--repeat-index differ from the run's run_plan.json" in capsys.readouterr().err
        given = []
    else:
        (raw / runner.RUN_PLAN).unlink()
        git = runmeta.git_state()
        given = ["--git-commit", git["git_commit"], "--git-dirty", str(git["git_dirty"]).lower()]
        assert _account(*main, *given, "--check") == 2              # no --repeat-index 1
        err = capsys.readouterr().err
        assert (f"{LUNA}, 11 episodes', the lock 'persistgym: F-0 on {LUNA}, 2 episodes at "
                "repeat 1'") in err
        given = [*args, *given]
    assert _account(*given) == 0
    (row,) = world.rows()
    assert row["run_id"] == RID
    for k in costs.COLUMNS:
        if k not in ("timestamp_utc", "latency_s", "notes"):
            assert row[k] == normal["row"][k], k
    assert row["notes"].startswith(normal["row"]["notes"])
    assert "; main 0-10 matrix=full repeat_index=1; added by account-run" in row["notes"]
    assert (out / "summary.json").read_bytes() == normal["summary"]
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert ({k: v for k, v in meta.items() if k not in VOLATILE_META}
            == {k: v for k, v in normal["meta"].items() if k not in VOLATILE_META})
    assert meta["repeat_index"] == 1 and meta["config"]["episode_ids"] == REPEATED
    assert [r["repeat_index"] for r in _jsonl(out / "episodes.jsonl")] == [1, 1]
    assert not world.lock.exists()
