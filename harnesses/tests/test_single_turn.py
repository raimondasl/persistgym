"""H3's single-turn control runner (harnesses/single_turn.py, CLI `single-turn`) with the fake
model and no network: which prompts a run plays (the 4 non-recoverable task cells, PREREG
§2.9's repeat subset), how a reply is scored or excluded, the files a run writes (blinded for
a pilot), parallel play, and the paid CLI path through the real guarded transport with a
fake-backed client: its refusals before the paid-run lock, its one costs row, meta.json, run
plan and lock.

luna's guard (registered.luna_refusal) holds its main runs to the default config, on which
G1 is recorded; these runs play the small volume, so the paid tests record luna's G1 on the
small config instead, as test_repeat.py does."""

from __future__ import annotations

import gzip
import json

import httpx
import openai
import pytest

from common import costs, hold, paidlock, runmeta
from common.tests.gitrepo import FROZEN_PREREG, decisions_text, guarded_repo
from harnesses import blinding, cli, registered, runner, single_turn
from harnesses.config import HarnessConfig
from harnesses.fake import FakeModel
from harnesses.items import item_text
from harnesses.openai_transport import ALLOW_ENV, OpenAIResponsesTransport
from harnesses.tests.conftest import SMALL
from harnesses.tests.test_registered import _commands
from harnesses.tests.test_repeat import _luna_g1_on_the_small_config
from persistgym.controls import single_turn_control

CFG = HarnessConfig()
NONREC = list(single_turn.NONREC_TASK_CELLS)
PILOT = "persistgym_pilot"
SMALL_ARGS = ["--gen-set", f"W_tokens={SMALL.W_tokens}", "--gen-set",
              f"v_tokens={SMALL.v_tokens}", "--gen-set",
              f"assumed_max_reply_tokens={SMALL.assumed_max_reply_tokens}"]


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    """Calls are timed with `runner.CLOCK`; fixed, so that outputs compare byte for byte."""
    monkeypatch.setattr(runner, "CLOCK", lambda: 0.0)


@pytest.fixture(scope="module")
def prompts():
    """Main templates 0 and 1 x the 4 non-recoverable task cells, at the small volume."""
    return single_turn.build_prompts("main", [0, 1], SMALL, NONREC)


def _prompt_text(payload: dict) -> str:
    (item,) = payload["input"]
    return item_text(item)


def _replies(prompts, how: list[str]):
    """A fake reply function: prompt k (in run order, cycling) gets the reply kind how[k]:
    the correct letter, the correct value, a wrong letter, or no action at all."""
    replies = {}
    for k, p in enumerate(prompts):
        c = p.control
        verb, right = c["need_verb"], c["correct_label"]
        value = next(o["value"] for o in c["options"] if o["label"] == right)
        wrong = next(o["label"] for o in c["options"] if o["label"] != right)
        replies[c["prompt"]] = {
            "letter": f"Checking.\nACTION: {verb}({right})",
            "value": f"ACTION: {verb}({value})",
            "wrong": f"ACTION: {verb}({wrong})",
            "none": "I cannot tell from these records.",
        }[how[k % len(how)]]
    return lambda payload, i: replies[_prompt_text(payload)]


def _run(prompts, transport, root, **kw):
    return single_turn.run_controls(prompts, kw.pop("cfg", CFG), transport,
                                    experiment=kw.pop("experiment", "persistgym"),
                                    run_id=kw.pop("run_id", "st"),
                                    results_root=root / "results", raw_root=root / "raw", **kw)


def _lines(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def _transcript(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(x) for x in f]


# --- which prompts a run plays ------------------------------------------------------------

def test_template_indices_and_the_repeat_subset():
    """§2.9: repeat 1 plays the main templates of [start, start + n) whose seed is divisible
    by 10 (main seeds are the indices), and nothing off the main split."""
    assert single_turn.template_indices("main", 0, 30) == list(range(30))
    assert single_turn.template_indices("main", 0, 30, 1) == [0, 10, 20]
    assert single_turn.template_indices("main", 5, 20, 1) == [10, 20]
    assert single_turn.template_indices("pilot", 0, 2) == [0, 1]
    for args in (("pilot", 0, 10, 1), ("validity", 0, 10, 1), ("main", 0, 10, 2),
                 ("main", 0, 0, 0), ("main", -1, 5, 0), ("main", 49_995, 10, 0)):
        with pytest.raises(ValueError):
            single_turn.template_indices(*args)
    # a repeat-1 range with no seed divisible by 10 plays nothing: refused in `run`'s words
    with pytest.raises(ValueError, match=r"main 1-9 has a seed divisible by 10: --repeat-index "
                                         r"1 would play nothing \(PREREG §2.9\)"):
        single_turn.template_indices("main", 1, 9, 1)


def test_task_cells_are_the_nonrecoverable_ones_in_cell_order():
    assert single_turn.task_cells(None) == single_turn.task_cells(["all"]) == NONREC == [
        "observed-nonrec-near", "observed-nonrec-far", "derived-nonrec-near",
        "derived-nonrec-far"]
    assert single_turn.task_cells(["derived-nonrec-far", "observed-nonrec-far"]) == [
        "observed-nonrec-far", "derived-nonrec-far"]
    for bad in (["observed-rec-far"], ["observed-nonrec-far", "observed-nonrec-far"],
                ["observed-x-far"], ["far"]):
        with pytest.raises(ValueError):
            single_turn.task_cells(bad)


def test_prompts_are_the_controls_of_the_base_episodes_in_run_order(prompts, small_eps):
    """Template by template, ALL_CELLS order within a template, as a harness run's episodes:
    each prompt is `single_turn_control` of that base episode (oracle replies)."""
    want = [e for e in small_eps if not e.cell.recoverable and e.template_id in (
        "main-000000", "main-000001")]
    assert [p.episode_id for p in prompts] == [
        f"{e.episode_id.rsplit('/', 1)[0]}/single_turn" for e in want]
    for p, ep in zip(prompts, want, strict=True):
        assert p.control == single_turn_control(ep)
        assert p.control["reply_mode"] == "oracle" and p.need_step == ep.need_step
        assert (p.template_seed, p.generator_config_hash) == (ep.template_seed, ep.config_hash)


# --- scoring one prompt ---------------------------------------------------------------------

def test_a_run_scores_each_prompt_as_the_need_step_and_writes_its_files(prompts, tmp_path):
    fake = FakeModel(_replies(prompts, ["letter", "value", "wrong", "none"]))
    meta = _run(prompts, fake, tmp_path, notes="main 0-1 control=single_turn repeat_index=0")
    out = tmp_path / "results" / "persistgym" / "st"
    lines = _lines(out / "episodes.jsonl")
    assert [x["episode_id"] for x in lines] == [p.episode_id for p in prompts]
    assert [x["need_outcome"] for x in lines] == ["correct", "correct", "wrong", "unparsed"] * 2
    assert [x["need_correct"] for x in lines] == [True, True, False, False] * 2
    assert [x["need_label"] for x in lines[:2]] == [p.control["correct_label"]
                                                    for p in prompts[:2]]
    for x, p in zip(lines, prompts, strict=True):
        assert x["exit_reason"] == "DONE" and not x["excluded"] and x["n_requests"] == 1
        assert (x["control"], x["harness_cell"], x["settings_cell"]) == (
            "single_turn", "single-turn", "F-0")
        assert x["task_cell"] == p.control["cell"] and x["repeat_index"] == 0
        assert x["base_episode_id"] == p.control["base_episode_id"]
        assert x["prompt_tokens"] == p.control["prompt_tokens"]
        assert x["echo"]["context_echoed"] == {"current_turn": 1}
        assert x["echo"]["effort_echoed"] == {"medium": 1}
        assert x["usage"]["output_tokens"] > 0 and x["cost_usd_billed_est"] > 0
    # the transcript: one record per prompt, each the request build_request makes
    events = _transcript(tmp_path / "raw" / "persistgym" / "st" / "transcript.jsonl.gz")
    assert [e["episode_id"] for e in events] == [p.episode_id for p in prompts]
    assert [e["payload"] for e in events] == [
        single_turn.build_request(p.control, CFG).payload for p in prompts] == fake.calls
    # meta.json: every required field; the control, its settings cell and the templates
    assert set(runmeta.REQUIRED) <= set(meta)
    assert meta["exit_reason"] == "COMPLETED" and meta["cell_or_config"] == "single-turn"
    assert meta["config"]["control"] == "single_turn"
    assert meta["config"]["settings_cell"] == "F-0"
    assert meta["config"]["task_cells"] == NONREC
    assert meta["config"]["episode_ids"] == [p.episode_id for p in prompts]
    assert meta["reasoning_context_requested"] == "current_turn"
    assert meta["reasoning_context_echoed"] == {"current_turn": 8}
    assert meta["reasoning_effort"] == "medium" and meta["reasoning_effort_echoed"] == {
        "medium": 8}
    assert meta["template_id"] == ["main-000000", "main-000001"]
    assert meta["seeds"] == {"template_seeds": [0, 1]} and meta["repeat_index"] == 0
    assert meta["n_episodes_run"] == 8 and meta["n_excluded"] == 0 and meta["paid"] is False
    assert meta["tokens"]["reasoning_tokens"] == 8 * 37
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["n_episodes"] == 8 and summary["errors"]["exit_reasons"] == {"DONE": 8}
    assert summary["echo_match"] == {"single-turn": {"requests": 8, "matched": 8,
                                                     "effort_matched": 8}}
    assert "need_correct" not in json.dumps(summary)
    # not a paid transport: no run plan
    assert not (tmp_path / "raw" / "persistgym" / "st" / runner.RUN_PLAN).exists()


def test_an_incomplete_response_scores_zero(prompts, tmp_path):
    """D13, PREREG §6: a response that stopped at the output cap is an invalid answer, even
    when its partial text holds the right one; the prompt is not excluded."""
    fake = FakeModel(_replies(prompts, ["letter"]),
                     status_fn=lambda p, tag: "incomplete")
    meta = _run(prompts[:2], fake, tmp_path)
    lines = _lines(tmp_path / "results" / "persistgym" / "st" / "episodes.jsonl")
    for x in lines:
        assert x["need_outcome"] == "incomplete" and not x["need_correct"]
        assert x["need_label"] is None and not x["excluded"] and x["exit_reason"] == "DONE"
        (inc,) = x["incomplete"]
        assert inc["reason"] == "max_output_tokens" and inc["max_output_tokens"] == 32_000
        assert inc["reply_chars"] > 0
    assert meta["exit_reason"] == "COMPLETED"


@pytest.mark.parametrize("kind, fake_kw, exit_reason, run_exit", [
    ("context", {"echo_context": "all_turns"}, "REASONING_CONTEXT_MISMATCH",
     "ABORTED_CONTEXT_MISMATCH"),
    ("effort", {"echo_effort": "high"}, "REASONING_EFFORT_MISMATCH",
     "ABORTED_EFFORT_MISMATCH")])
def test_an_echo_mismatch_excludes_the_prompt_and_two_abort_the_run(prompts, tmp_path, kind,
                                                                    fake_kw, exit_reason,
                                                                    run_exit):
    """CLAUDE.md, PREREG §13, §17.2: a differing echo excludes the prompt, unscored, and the
    run aborts after 2 excluded prompts."""
    fake = FakeModel(_replies(prompts, ["letter"]), **fake_kw)
    meta = _run(prompts, fake, tmp_path)
    lines = _lines(tmp_path / "results" / "persistgym" / "st" / "episodes.jsonl")
    assert len(lines) == len(fake.calls) == 2 and meta["exit_reason"] == run_exit
    for x in lines:
        assert x["excluded"] and x["exit_reason"] == exit_reason
        assert x["echo_mismatches"] == [kind] and x["need_outcome"] is None
        assert f"reasoning.{kind} requested" in x["exclusion_reason"]
    assert meta["n_excluded"] == 2


def test_api_errors_end_the_prompt_and_two_abort_the_run(prompts, tmp_path):
    class Failing:
        paid = False
        calls = 0

        def send(self, payload):
            self.calls += 1
            raise openai.APIConnectionError(
                request=httpx.Request("POST", "https://example.invalid/v1/responses"))
    transport = Failing()
    meta = _run(prompts, transport, tmp_path)
    lines = _lines(tmp_path / "results" / "persistgym" / "st" / "episodes.jsonl")
    assert [x["exit_reason"] for x in lines] == ["API_ERROR", "API_ERROR"]
    assert all(x["n_requests"] == 0 and x["need_outcome"] is None for x in lines)
    assert meta["exit_reason"] == "ABORTED_API_ERRORS" and transport.calls == 2


def test_parallel_play_writes_what_sequential_play_writes(prompts, tmp_path):
    """PREREG §4.6: the same records, transcript and summary, in the run's order."""
    how = ["letter", "wrong", "none", "value"]
    seq = _run(prompts, FakeModel(_replies(prompts, how), ids="payload"), tmp_path,
               run_id="seq")
    par = _run(prompts, FakeModel(_replies(prompts, how), ids="payload"), tmp_path,
               run_id="par", parallel=4)
    out, raw = tmp_path / "results" / "persistgym", tmp_path / "raw" / "persistgym"
    for name in ("episodes.jsonl", "summary.json"):
        assert (out / "par" / name).read_bytes() == (out / "seq" / name).read_bytes()
    with (gzip.open(raw / "par" / "transcript.jsonl.gz", "rb") as p,
          gzip.open(raw / "seq" / "transcript.jsonl.gz", "rb") as s):
        assert p.read() == s.read()
    assert par["config_hash"] == seq["config_hash"]
    assert par["parallel"]["max_episodes_in_flight"] == 4
    assert par["parallel"]["episodes_started"] == 8
    assert not (raw / "par" / runner.INFLIGHT_DIR).exists()


def test_a_pilot_is_blinded_and_never_pooled(prompts, tmp_path):
    """PREREG §11: a pilot's prompt records stay under results/raw/, its committed files are
    meta.json (no reasoning tokens) and the allowlisted summary.json, and the pooled pilot
    report leaves the run out."""
    pilot = single_turn.build_prompts("pilot", [0], SMALL, NONREC[:2])
    meta = _run(pilot, FakeModel(), tmp_path, experiment=PILOT, run_id="p")
    committed = sorted(p.name for p in (tmp_path / "results").rglob("*") if p.is_file())
    assert committed == ["meta.json", "summary.json"]
    assert len(_lines(tmp_path / "raw" / PILOT / "p" / "episodes.jsonl")) == 2
    assert meta["tokens"]["reasoning_tokens"] is None and "blinding" in meta
    report = blinding.pooled_report(blinding.load_raw_runs(tmp_path / "raw", PILOT),
                                    experiment=PILOT)
    assert report["models"] == {} and report["runs_left_out"]["run_ids"] == ["p"]
    assert "single-turn" in report["runs_left_out"]["why"]


# --- the paid CLI path ---------------------------------------------------------------------

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
    repo (frozen PREREG; block 3-persistgym approves persistgym and persistgym_pilot) and
    costs.csv, with a fake-backed client; the paid-run lock is a file of its own."""
    guarded_repo(tmp_path, prereg=FROZEN_PREREG, decisions=decisions_text(
        "3-persistgym", experiments=("persistgym", PILOT)))
    costs_csv = tmp_path / "costs.csv"
    costs_csv.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    monkeypatch.setenv(ALLOW_ENV, "1")
    monkeypatch.setattr(cli, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(cli, "RAW", tmp_path / "raw")
    (tmp_path / "lock").mkdir()
    monkeypatch.setattr(cli, "LOCK_PATH", tmp_path / "lock" / paidlock.lock_name(cli.STREAM))
    # luna's G1 on the small volume these runs play (the default config's G1 is the real one)
    assert _luna_g1_on_the_small_config(monkeypatch) == runmeta.config_hash(SMALL.to_dict())
    fakes = []

    def transport(**kw):
        fake = FakeModel(ids="payload")
        fakes.append(fake)
        return OpenAIResponsesTransport(
            **kw, costs_path=costs_csv, repo=tmp_path,
            client_factory=lambda timeout: _FakeBackedClient(fake))
    monkeypatch.setattr(cli, "OpenAIResponsesTransport", transport)
    return tmp_path, costs_csv, fakes


MAIN = ["single-turn", "--split", "main", "--start", "0", "--n", "2", *SMALL_ARGS,
        "--experiment", "persistgym", "--approved-block", "3-persistgym", "--planned-usd", "1",
        "--milestone", "M2"]


def test_single_turn_cli_main_run(paid_env, capsys):
    tmp, costs_csv, fakes = paid_env
    assert cli.main([*MAIN, "--run-id", "st"]) == 0
    assert '"run_id": "st"' in capsys.readouterr().out
    (row,) = costs.read_rows(costs_csv)
    assert (row["run_id"], row["experiment"], row["cell_or_config"], row["milestone"]) == (
        "st", "persistgym", "single-turn", "M2")
    assert row["model_requested"] == "gpt-6-luna" and row["n_calls"] == "8"
    assert row["service_tier"] == "flex" and int(row["reasoning_tokens"]) == 8 * 37
    assert row["notes"].startswith("approved_block=3-persistgym; context_mismatches=0; "
                                   "effort_mismatches=0;")
    assert row["notes"].endswith("; main 0-1 control=single_turn repeat_index=0")
    # every request is the control's, at luna's registered settings (F-0's)
    (fake,) = fakes
    want = [single_turn.build_request(p.control, CFG).payload
            for p in single_turn.build_prompts("main", [0, 1], SMALL, NONREC)]
    assert fake.calls == want
    assert {json.dumps(p["reasoning"], sort_keys=True) for p in fake.calls} == {
        '{"context": "current_turn", "effort": "medium", "mode": "standard"}'}
    out = tmp / "results" / "persistgym" / "st"
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert set(runmeta.REQUIRED) <= set(meta) and meta["paid"] is True
    assert meta["exit_reason"] == "COMPLETED" and meta["cost_usd"]["costs_csv_row_appended"]
    assert meta["config"]["templates"] == {"split": "main", "start": 0, "n": 2,
                                           "repeat_index": 0, "indices": [0, 1]}
    assert meta["git_commit"] == row["git_commit"]
    assert len(_lines(out / "episodes.jsonl")) == 8
    # the run plan, written before the first call; account-run refuses it
    plan = json.loads((tmp / "raw" / "persistgym" / "st" / runner.RUN_PLAN)
                      .read_text(encoding="utf-8"))
    assert plan["command"] == "single-turn" and plan["repeat_index"] == 0
    assert plan["run_args"]["task_cell"] == ["all"] and plan["run_args"]["n"] == 2
    assert plan["episode_ids"] == meta["config"]["episode_ids"]
    # the lock is released, the last run recorded, the reservation gone
    assert not cli.LOCK_PATH.exists()
    last = json.loads(paidlock.last_run_path(cli.LOCK_PATH, cli.STREAM).read_text(
        encoding="utf-8"))
    assert last["run_id"] == "st"
    assert not paidlock.reservation_path(cli.LOCK_PATH, cli.STREAM).exists()
    assert cli.main(["account-run", "st", "--check"]) == 2
    assert "is a `single-turn` run" in capsys.readouterr().err


def test_single_turn_cli_repeat_1_plays_the_seeds_divisible_by_10(paid_env):
    tmp, costs_csv, _ = paid_env
    args = [*MAIN, "--n", "20", "--repeat-index", "1", "--task-cell", "derived-nonrec-far",
            "observed-nonrec-far"]
    assert cli.main(args) == 0
    (run_dir,) = (tmp / "results" / "persistgym").iterdir()
    assert run_dir.name.endswith("-single-turn-rep1-gpt-6-luna")
    lines = _lines(run_dir / "episodes.jsonl")
    assert [x["episode_id"] for x in lines] == [
        "main-000000/observed-nonrec-far/single_turn",
        "main-000000/derived-nonrec-far/single_turn",
        "main-000010/observed-nonrec-far/single_turn",
        "main-000010/derived-nonrec-far/single_turn"]
    assert {x["repeat_index"] for x in lines} == {1}
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["repeat_index"] == 1 and meta["seeds"] == {"template_seeds": [0, 10]}
    (row,) = costs.read_rows(costs_csv)
    assert row["n_calls"] == "4" and row["notes"].endswith("main 0-19 control=single_turn "
                                                           "repeat_index=1")


def test_single_turn_cli_parallel(paid_env):
    tmp, costs_csv, _ = paid_env
    assert cli.main([*MAIN, "--run-id", "par", "--parallel", "4"]) == 0
    meta = json.loads((tmp / "results" / "persistgym" / "par" / "meta.json")
                      .read_text(encoding="utf-8"))
    assert meta["parallel"]["max_episodes_in_flight"] == 4
    assert meta["parallel"]["spend_reservation"]["planned_usd"] == 1.0
    (row,) = costs.read_rows(costs_csv)
    assert row["n_calls"] == "8" and row["notes"].endswith(" parallel=4")
    assert not cli.LOCK_PATH.exists()


def test_single_turn_cli_pilot_is_blinded(paid_env):
    tmp, costs_csv, _ = paid_env
    assert cli.main(["single-turn", "--n", "2", *SMALL_ARGS, "--task-cell",
                     "observed-nonrec-far", "--approved-block", "3-persistgym",
                     "--planned-usd", "1", "--run-id", "p"]) == 0
    (row,) = costs.read_rows(costs_csv)
    assert row["experiment"] == PILOT and row["n_calls"] == "2"
    assert row["reasoning_tokens"] == "" and blinding.WITHHELD_NOTE in row["notes"]
    committed = sorted(p.name for p in (tmp / "results" / PILOT).rglob("*") if p.is_file())
    assert committed == ["meta.json", "summary.json"]
    assert (tmp / "raw" / PILOT / "p" / "episodes.jsonl").exists()


def test_single_turn_stops_at_its_planned_spend_and_places_no_hold(paid_env):
    tmp, _, fakes = paid_env
    assert cli.main([*MAIN[:MAIN.index("--planned-usd") + 1], "0.0000001", "--run-id",
                     "tiny"]) == 0
    meta = json.loads((tmp / "results" / "persistgym" / "tiny" / "meta.json")
                      .read_text(encoding="utf-8"))
    assert meta["exit_reason"] == "COST_CAP" and len(fakes[0].calls) == 1
    assert not hold.holds_path(cli.LOCK_PATH).exists()


PILOT_RUN = ["single-turn", "--n", "1", *SMALL_ARGS, "--approved-block", "3-persistgym",
             "--planned-usd", "1"]


@pytest.mark.parametrize("args, says", [
    ([*PILOT_RUN, "--task-cell", "observed-rec-far"], "non-recoverable"),
    ([*PILOT_RUN, "--repeat-index", "1"], "main templates only"),
    ([*PILOT_RUN, "--n", "3"], "a pilot is at most 10 prompts, got 12"),
    ([*PILOT_RUN, "--split", "main"], "--split pilot only"),
    ([*PILOT_RUN, "--experiment", "persistgym"], "pilot data"),
    ([*PILOT_RUN, "--experiment", "persistgym_validity", "--split", "validity"],
     "persistgym or persistgym_pilot only"),
    ([*PILOT_RUN, "--parallel", "17"], "--parallel is 1 to 16"),
    ([*PILOT_RUN, "--gen-set", "W_tokens"], "--gen-set"),
    ([*PILOT_RUN, "--run-id", "../x"], "plain folder name"),
    ([*PILOT_RUN, "--mode", "fast"], "reasoning_mode must be one of"),
    ([*MAIN, "--model", "gpt-6.1-sol"], "gpt-6-luna only"),
    ([*MAIN, "--model", "gpt-6.1-sol", "--effort", "medium"], "gpt-6-luna only"),
    ([*MAIN, "--mode", "pro"], "--mode pro"),
    ([*MAIN, "--service-tier", "default"], "--service-tier default"),
    ([*MAIN, "--effort", "high"], "registered reasoning effort 'medium'"),
    ([*MAIN, "--start", "1", "--n", "9", "--repeat-index", "1"], "would play nothing"),
    # luna's guard (registered.luna_refusal): its main sweep and controls only
    ([*MAIN, "--split", "validity"], "got --split validity"),
    ([*MAIN, "--gen-preset", "sol-chain"], "got generator config"),
    ([*MAIN, "--start", "49999", "--n", "2"], "outside the main range"),
])
def test_single_turn_refuses_before_the_lock(paid_env, monkeypatch, capsys, args, says):
    _, costs_csv, fakes = paid_env

    def no_lock(*a, **k):
        raise AssertionError("must not take the paid-run lock")
    monkeypatch.setattr(paidlock, "paid_run_lock", no_lock)
    assert cli.main(args) == 2
    err = capsys.readouterr().err
    assert "refused" in err and says in err
    assert fakes == [] and costs.read_rows(costs_csv) == []


def test_single_turn_needs_lunas_g1_on_the_config_it_plays(paid_env, monkeypatch, capsys):
    """luna's guard holds the control to the config its G1 is recorded on: back on the real
    one (the default config), the small volume is an unregistered config; and a G1 recorded
    on another config than the one played refuses (fail closed). Both before the lock."""
    _, costs_csv, fakes = paid_env
    small = registered.LUNA_GENERATOR_HASH

    def no_lock(*a, **k):
        raise AssertionError("must not take the paid-run lock")
    monkeypatch.setattr(paidlock, "paid_run_lock", no_lock)
    monkeypatch.setattr(registered, "LUNA_GENERATOR_HASH", registered.DEFAULT_GENERATOR_HASH)
    assert cli.main(MAIN) == 2
    err = capsys.readouterr().err
    assert err.startswith("refused:") and f"got generator config {small[:12]}" in err
    monkeypatch.setattr(registered, "LUNA_GENERATOR_HASH", small)
    monkeypatch.setitem(registered.G1_PASSED, "gpt-6-luna", registered.DEFAULT_GENERATOR_HASH)
    assert cli.main(MAIN) == 2
    err = capsys.readouterr().err
    assert "only after the researcher has recorded G1" in err and "G1_PASSED" in err
    assert fakes == [] and costs.read_rows(costs_csv) == []


def test_paid_calls_off_never_touch_the_lock(monkeypatch, capsys):
    monkeypatch.delenv(ALLOW_ENV, raising=False)

    def no_lock(*a, **k):
        raise AssertionError("must not take the paid-run lock")
    monkeypatch.setattr(paidlock, "paid_run_lock", no_lock)
    monkeypatch.setattr(paidlock, "lock_path", no_lock)
    assert cli.main([*PILOT_RUN]) == 2
    assert "paid calls are off" in capsys.readouterr().err


def test_single_turn_sends_the_models_registered_effort_by_default():
    assert cli.parse_args(["single-turn"]).effort == "medium"
    assert cli.parse_args(["single-turn", "--model", "gpt-6.1-sol"]).effort == "high"
    assert cli.parse_args(["single-turn", "--effort", "low"]).effort == "low"


def test_the_docstring_command_is_lunas_registered_control():
    """harnesses/cli.py's single-turn command: luna at its registered effort and D13's
    settings, the main split from template 0, the 4 non-recoverable task cells, persistgym,
    repeat 0, and it passes the settings guard."""
    (argv,) = [c for c in _commands(cli.__doc__) if c[0] == "single-turn"]
    a = cli.parse_args(argv)
    assert (a.model, a.effort, a.mode, a.service_tier) == ("gpt-6-luna", "medium", "standard",
                                                           "flex")
    assert (a.split, a.start, a.n, a.experiment) == ("main", 0, 100, "persistgym")
    assert a.task_cell == ["all"] and a.repeat_index == 0 and a.parallel == 16
    assert single_turn.settings_refusal(
        experiment=a.experiment, model=a.model, mode=a.mode, service_tier=a.service_tier,
        split=a.split, repeat_index=1) is None
    assert single_turn.task_cells(a.task_cell) == NONREC
    assert single_turn.template_indices(a.split, a.start, a.n, 1) == list(range(0, 100, 10))
