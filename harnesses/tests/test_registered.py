"""Registered request settings (PREREG §6 as amended by R2, §17.2; harnesses/registered.py):
`run` and `dry-run` default to the model's registered effort, `run` refuses any other effort
outside pilots and a non-pilot sol run without an ENGAGED engagement check, and the probes
keep their own registered settings. Also: the command examples in the CLI docstring and in
PREREG §17.2 parse, and the check's runs play block 1's sol pilot episodes."""

from __future__ import annotations

import dataclasses
import json
import re
import shlex
from pathlib import Path

import pytest

from common import paidlock, runmeta
from harnesses import cli, probes, registered
from harnesses.config import HarnessConfig
from harnesses.openai_transport import ALLOW_ENV
from harnesses.tests.conftest import SMALL

SOL, LUNA = "gpt-6.1-sol", "gpt-6-luna"
SMALL_SETS = ["--gen-set", f"W_tokens={SMALL.W_tokens}", "--gen-set",
              f"v_tokens={SMALL.v_tokens}", "--gen-set",
              f"assumed_max_reply_tokens={SMALL.assumed_max_reply_tokens}"]
# block 1's sol pilot at medium effort (committed meta.json; PREREG §17.2)
MEDIUM_PILOT = ("20261002T083238Z-F-r-gpt-6.1-sol", "20261002T083706Z-F-0-gpt-6.1-sol")


def test_the_registered_efforts():
    assert registered.REGISTERED_EFFORT == {LUNA: "medium", SOL: "high"}
    assert registered.registered_effort(LUNA) == "medium"
    assert registered.registered_effort(SOL) == "high"
    assert registered.registered_effort("gpt-unknown") == "medium"   # not in the table
    assert registered.ENGAGEMENT_REQUIRED == {SOL}
    assert registered.rule() == {
        "prereg": "PREREG.md §17.2 (amendment R2)", "model": SOL, "effort": "high",
        "reasoning_token_floor": 32, "e_threshold": 0.5, "derived_far_episodes": 8,
        "min_derived_far_ended_normally": 6}


# --- defaults ----------------------------------------------------------------------------------

@pytest.mark.parametrize("cmd", ["run", "dry-run"])
@pytest.mark.parametrize(("model", "effort"), [(SOL, "high"), (LUNA, "medium"),
                                               ("gpt-unknown", "medium")])
def test_run_and_dry_run_default_to_the_registered_effort(cmd, model, effort):
    a = cli.parse_args([cmd, "--cell", "F-r", "--model", model])
    assert a.effort == effort
    assert cli._harness_config(a).reasoning_effort == effort
    assert cli.parse_args([cmd, "--cell", "F-r", "--model", model,
                           "--effort", "low"]).effort == "low"     # an explicit effort stays
    assert cli.parse_args([cmd, "--cell", "F-r"]).effort == "medium"  # default model: luna


def test_dry_run_shows_sols_registered_effort(capsys):
    assert cli.main(["dry-run", "--cell", "F-0", "--model", SOL, "--task-cell",
                     "derived-rec-far", *SMALL_SETS]) == 0
    lines = [x for x in capsys.readouterr().out.splitlines() if x.startswith("  #")]
    assert lines and all("reasoning.effort=high" in x for x in lines)


@pytest.mark.parametrize("model", [SOL, LUNA])
def test_the_probes_keep_their_registered_settings(model):
    """PREREG §17.1: the echo and replay probes run at medium on both models, whatever the
    model's registered effort for harness runs; the fork probe's check is unchanged."""
    for cmd, cfg in (("probe-echo", probes.ECHO_CONFIG), ("probe-replay", probes.REPLAY_CONFIG)):
        a = cli.parse_args([cmd, "--model", model])
        assert a.effort == "medium"
        kind = cmd.removeprefix("probe-")
        assert cli._probe_cfg(a, kind) == cfg
    a = cli.parse_args(["probe-replay", "--model", model, "--design", "fork"])
    assert cli._probe_args(a, "replay") is None                       # registered: passes
    a = cli.parse_args(["probe-replay", "--model", model, "--design", "fork",
                        "--effort", "high"])
    assert "registered settings" in cli._probe_args(a, "replay")      # still refused
    assert cli.parse_args(["probe-echo"]).model == list(probes.ECHO_CHECK_MODELS)


# --- the guard -------------------------------------------------------------------------------

def _write_check(results: Path, name: str, **changes) -> Path:
    doc = {"verdict": "ENGAGED", "model": SOL, "effort": "high", "rule": registered.rule(),
           **changes}
    path = results / "persistgym_pilot" / name / registered.CHECK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


@pytest.mark.parametrize(("model", "effort"), [(SOL, "medium"), (SOL, "low"), (SOL, "high"),
                                               (LUNA, "high"), (LUNA, "medium")])
def test_pilots_may_use_any_effort(tmp_path, model, effort):
    assert registered.check_run_settings("persistgym_pilot", model, effort, tmp_path) is None


@pytest.mark.parametrize("experiment", ["persistgym", "persistgym_validity",
                                        "statecarry_persistgym"])
def test_outside_pilots_only_the_registered_effort(tmp_path, experiment):
    assert registered.check_run_settings(experiment, LUNA, "medium", tmp_path) is None
    why = registered.check_run_settings(experiment, LUNA, "high", tmp_path)
    assert "registered reasoning effort 'medium'" in why and "got 'high'" in why
    _write_check(tmp_path, "c1")
    assert registered.check_run_settings(experiment, SOL, "high", tmp_path) is None
    why = registered.check_run_settings(experiment, SOL, "medium", tmp_path)
    assert "registered reasoning effort 'high'" in why                # engaged or not
    assert registered.check_run_settings(experiment, "gpt-unknown", "medium", tmp_path) is None


def test_sol_outside_pilots_needs_an_engaged_check(tmp_path):
    def why():
        return registered.check_run_settings("persistgym_validity", SOL, "high", tmp_path)
    assert "need an ENGAGED engagement check" in why()               # none at all
    _write_check(tmp_path, "unscorable", verdict="UNSCORABLE")
    _write_check(tmp_path, "luna", model=LUNA)                       # another model
    _write_check(tmp_path, "medium", effort="medium")                # another effort
    _write_check(tmp_path, "rule", rule={**registered.rule(), "reasoning_token_floor": 16})
    w = why()
    assert "need an ENGAGED engagement check" in w
    assert "under another rule and do not count" in w and "rule" in w
    _write_check(tmp_path, "engaged")
    assert why() is None
    # a NOT_ENGAGED check refuses, whatever else is there (R2: no sol validity or main sweep)
    not_engaged = _write_check(tmp_path, "zz-not", verdict="NOT_ENGAGED")
    assert "does not engage" in why() and str(not_engaged) in why()
    not_engaged.unlink()
    assert why() is None
    # an unreadable check refuses until fixed
    bad = tmp_path / "persistgym_pilot" / "bad" / registered.CHECK_FILE
    bad.parent.mkdir()
    bad.write_text("{not json", encoding="utf-8")
    assert "cannot read the engagement check" in why()


@pytest.fixture
def armed(monkeypatch, tmp_path):
    """Paid calls armed, the CLI's results under tmp_path, and the paid-run lock out of
    reach: a refusal must come before it."""
    monkeypatch.setenv(ALLOW_ENV, "1")
    monkeypatch.setattr(cli, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(cli, "RAW", tmp_path / "raw")

    def no_lock(*a, **k):
        raise AssertionError("must not take the paid-run lock")
    monkeypatch.setattr(paidlock, "paid_run_lock", no_lock)
    return tmp_path / "results"


VALIDITY = ["run", "--cell", "F-0", "--split", "validity", "--experiment",
            "persistgym_validity", "--n", "1", "--task-cell", "derived-rec-far", *SMALL_SETS,
            "--approved-block", "1-pilots", "--planned-usd", "1"]


@pytest.mark.parametrize(("args", "message"), [
    (["--model", SOL], "need an ENGAGED engagement check"),
    (["--model", SOL, "--effort", "medium"], "registered reasoning effort 'high'"),
    (["--model", LUNA, "--effort", "high"], "registered reasoning effort 'medium'")])
def test_run_refuses_unregistered_settings_before_the_lock(armed, capsys, args, message):
    assert cli.main([*VALIDITY, *args]) == 2
    err = capsys.readouterr().err
    assert err.startswith("refused:") and message in err


@pytest.mark.parametrize(("args", "engaged"), [(["--model", LUNA], False),
                                               (["--model", SOL], True),
                                               (["--model", SOL, "--split", "pilot",
                                                 "--experiment", "persistgym_pilot",
                                                 "--effort", "low"], False)])
def test_run_passes_registered_settings_on_to_the_paid_path(armed, monkeypatch, args, engaged):
    if engaged:
        _write_check(armed, "check")
    reached = []

    def paid_path(run_id, what, body):
        reached.append(what)
        return 0
    monkeypatch.setattr(cli, "_with_paid_lock", paid_path)
    assert cli.main([*VALIDITY, *args]) == 0
    (what,) = reached
    model = args[1]
    assert f"F-0 on {model}" in what


# --- command examples ---------------------------------------------------------------------------

_COMMAND = re.compile(r"^(?:PERSISTGYM_ALLOW_PAID=1 )?uv run (?:--env-file \.env )?"
                      r"python -m harnesses (.*)$")


def _commands(text: str) -> list[list[str]]:
    """The `python -m harnesses` commands in `text`, on lines of their own or in inline code
    spans: continuation lines joined, trailing comments dropped, `<usd>` read as 1 and other
    `<placeholders>` as one argument."""
    text = re.sub(r"\\\n\s*", " ", text)
    out = []
    for line in [*text.splitlines(), *re.findall(r"`([^`\n]*uv run [^`\n]*)`", text)]:
        m = _COMMAND.match(line.strip())
        if m:
            cmd = re.sub(r"<usd>", "1", m.group(1).split("#")[0])
            out.append(shlex.split(re.sub(r"<[^>]*>", "PLACEHOLDER", cmd)))
    return out


def _medium_pilot() -> tuple[list[str], list[str]]:
    """Block 1's sol pilot: its episode ids and generator config hashes (both runs)."""
    seen = []
    for run_id in MEDIUM_PILOT:
        meta = json.loads((runmeta.REPO_ROOT / "results" / "persistgym_pilot" / run_id
                           / "meta.json").read_text(encoding="utf-8"))
        assert meta["reasoning_effort"] == "medium" and meta["model_requested"] == SOL
        seen.append((meta["config"]["episode_ids"], meta["config"]["generator_config_hashes"]))
    assert seen[0] == seen[1] and len(seen[0][0]) == 8
    return seen[0]


def _check_run(argv: list[str]):
    """A check run's parsed command: (cell, episode ids), after checking its settings and that
    it generates the episodes of block 1's sol pilot under the same generator config."""
    a = cli.parse_args(argv)
    assert (a.cmd, a.model, a.effort, a.experiment) == ("run", SOL, "high", "persistgym_pilot")
    assert (a.approved_block, a.planned_usd, a.split, a.start) == ("1-pilots", 3.0, "pilot", 0)
    eps = cli._run_matrix(a).episodes(a.split, a.start, cli._gen_config(a.gen_set), a.variant)
    assert len(eps) <= cli.PILOT_MAX_EPISODES
    assert registered.check_run_settings(a.experiment, a.model, a.effort, Path("nowhere")) \
        is None
    ids, hashes = _medium_pilot()
    assert [ep.episode_id for ep in eps] == ids
    assert sorted({ep.config_hash for ep in eps}) == hashes
    return a.cell, [ep.episode_id for ep in eps]


def test_cli_docstring_examples_parse():
    commands = _commands(cli.__doc__)
    assert {c[0] for c in commands} >= {"cells", "dry-run", "pilot-report", "probe-summary",
                                        "echo-count", "reasoning-check", "probe-echo",
                                        "probe-replay", "run"}
    for argv in commands:
        a = cli.parse_args(argv)
        assert a.cmd == argv[0]
    # the engagement check's run plays block 1's sol pilot episodes at high effort
    (check,) = [c for c in commands if c[0] == "run" and "gpt-6.1-sol" in c
                and "persistgym_pilot" in c]
    cell, ids = _check_run(check)
    assert cell == "F-r" and ids == _medium_pilot()[0]
    # sol's main sweep: D11 at T_d = 210, T_o = 70, at sol's registered effort (high)
    (sweep,) = [c for c in commands if c[0] == "run" and "persistgym" in c]
    a = cli.parse_args(sweep)
    assert a.effort == "high" and a.parallel == 16
    m = cli._run_matrix(a).to_dict()
    assert m["templates_per_task_cell"] == {"observed-nonrec-far": 70, "observed-rec-far": 70,
                                            "derived-nonrec-far": 210, "derived-rec-far": 210}
    assert 2 * m["n_episodes"] == 1_120                     # F-r and F-0 (PREREG §17.2)


def _prereg_17_2() -> str:
    text = (runmeta.REPO_ROOT / "PREREG.md").read_text(encoding="utf-8")
    start = text.index("### 17.2 Amendment R2")
    end = text.find("\n### ", start + 1)
    return text[start:] if end < 0 else text[start:end]


def test_the_prereg_check_commands_run_block_1s_sol_pilot_episodes_at_high_effort():
    """PREREG §17.2's two check runs are F-r and F-0, sol at high effort, on the 16 episodes
    of block 1's medium-effort sol pilot, under block 1 with $3 planned each; its
    reasoning-check command names that pilot as the reference."""
    commands = _commands(_prereg_17_2())
    runs = [c for c in commands if c[0] == "run"]
    assert sorted(_check_run(c)[0] for c in runs) == ["F-0", "F-r"]
    (rc,) = [c for c in commands if c[0] == "reasoning-check"]
    a = cli.parse_args(rc)
    assert a.reference == list(MEDIUM_PILOT)


def test_the_check_files_rule_is_the_one_prereg_states():
    text = _prereg_17_2()
    assert "**Rule: reasoning engages iff E ≥ 0.50.**" in text
    assert "at least 32" in text and "fewer than 6 of the 8 derived-far episodes" in text
    r = registered.rule()
    assert (r["e_threshold"], r["reasoning_token_floor"], r["min_derived_far_ended_normally"],
            r["derived_far_episodes"]) == (0.5, 32, 6, 8)


def test_harness_config_effort_is_still_validated():
    with pytest.raises(ValueError, match="reasoning_effort"):
        HarnessConfig(reasoning_effort="extreme")
    assert dataclasses.replace(HarnessConfig(), reasoning_effort="high").reasoning_effort == \
        "high"
