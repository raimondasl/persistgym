"""Registered request settings (PREREG §6 as amended by R2, §17.2, and R3, §17.3;
harnesses/registered.py): `run` and `dry-run` default to the model's registered effort, `run`
refuses any other effort outside pilots, a non-pilot sol run off its `sol-chain` config or
cells, or without an ENGAGED engagement check on that config (and, outside its validity run,
without G1), a sol pilot at high effort off `sol-chain` or after R3's hard stop, and the probes
keep their own registered settings. Also: the command examples in the CLI docstring and in
PREREG §17.2 and §17.3 parse, and the check's runs play block 1's sol pilot templates."""

from __future__ import annotations

import dataclasses
import json
import re
import shlex
import shutil
from pathlib import Path

import pytest

from common import paidlock, runmeta
from harnesses import cli, probes, registered
from harnesses.config import HarnessConfig
from harnesses.openai_transport import ALLOW_ENV
from harnesses.tests.conftest import SMALL
from persistgym.config import PRESET_HASHES

SOL, LUNA = "gpt-6.1-sol", "gpt-6-luna"
VARIANT, DEFAULT = PRESET_HASHES["sol-chain"], PRESET_HASHES["default"]
SMALL_SETS = ["--gen-set", f"W_tokens={SMALL.W_tokens}", "--gen-set",
              f"v_tokens={SMALL.v_tokens}", "--gen-set",
              f"assumed_max_reply_tokens={SMALL.assumed_max_reply_tokens}"]
# block 1's sol pilot at medium effort (committed meta.json; PREREG §17.2)
MEDIUM_PILOT = ("20261002T083238Z-F-r-gpt-6.1-sol", "20261002T083706Z-F-0-gpt-6.1-sol")
# R2's check runs and its NOT_ENGAGED check file (committed; PREREG §17.2, §17.3)
R2_CHECK = ("20261002T173710Z-F-r-gpt-6.1-sol", "20261002T180358Z-F-0-gpt-6.1-sol")
R2_FILE = "reasoning-check-20261002T225917Z"
RESULTS = runmeta.REPO_ROOT / "results"


def guard(experiment: str, model: str, effort: str, root: Path, cell: str = "F-0",
          gen: str = VARIANT, split: str = "validity", variant: str = "restated") -> str | None:
    """The guard on these settings; the split and variant are a validity run's unless given."""
    return registered.check_run_settings(experiment, model, effort, cell, gen, root,
                                         split=split, variant=variant)


def test_the_registered_settings():
    assert registered.REGISTERED_EFFORT == {LUNA: "medium", SOL: "high"}
    assert registered.registered_effort(LUNA) == "medium"
    assert registered.registered_effort(SOL) == "high"
    assert registered.registered_effort("gpt-unknown") == "medium"   # not in the table
    assert registered.ENGAGEMENT_REQUIRED == {SOL}
    assert registered.REGISTERED_GENERATOR == {SOL: "sol-chain"}       # luna not covered
    assert registered.REGISTERED_CELLS == {SOL: ("F-r", "F-0")}
    assert registered.G1_PASSED == {}                                   # fails closed
    assert registered.VARIANT_GENERATOR_HASH == VARIANT
    assert registered.rule() == {
        "prereg": "PREREG.md §17.3 (amendment R3)", "model": SOL, "effort": "high",
        "reasoning_token_floor": 32, "e_threshold": 0.5, "derived_far_episodes": 8,
        "min_derived_far_ended_normally": 6, "generator_config_hash": VARIANT}
    # R2's file records R2's rule, without a generator config: it belongs to the default
    r2 = json.loads((RESULTS / "persistgym_pilot" / R2_FILE / registered.CHECK_FILE)
                    .read_text(encoding="utf-8"))
    assert r2["rule"] == registered._r2_rule() and r2["verdict"] == "NOT_ENGAGED"
    assert registered._file_hash(r2) == DEFAULT


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
    assert a.gen_preset == "default"
    assert cli.parse_args([cmd, "--cell", "F-r", "--gen-preset", "sol-chain"]).gen_preset == (
        "sol-chain")
    with pytest.raises(SystemExit):
        cli.parse_args([cmd, "--cell", "F-r", "--gen-preset", "nope"])


def test_gen_preset_and_gen_set_give_the_config():
    assert runmeta.config_hash(cli._gen_config("sol-chain", []).to_dict()) == VARIANT
    assert runmeta.config_hash(cli._gen_config("default", []).to_dict()) == DEFAULT
    small = cli._gen_config("sol-chain", SMALL_SETS[1::2])
    assert (small.clue_form, small.evidence_notice, small.v_tokens) == ("chain", True, 400)
    assert "gen_preset" in cli.RUN_ARGS and cli._run_defaults()["gen_preset"] == "default"


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

FIRST, SECOND = (list(t) for t in registered.CHECK_TEMPLATES)


def _write_check(results: Path, name: str, **changes) -> Path:
    """A check file under R3's rule (on sol-chain) unless `changes` say otherwise."""
    doc = {"verdict": "ENGAGED", "model": SOL, "effort": "high", "rule": registered.rule(),
           "check_run_ids": [f"{name}-F-r", f"{name}-F-0"], "check_templates": FIRST,
           **changes}
    path = results / "persistgym_pilot" / name / registered.CHECK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _r2_file(results: Path) -> Path:
    """R2's committed NOT_ENGAGED check file, copied under `results`."""
    src = RESULTS / "persistgym_pilot" / R2_FILE / registered.CHECK_FILE
    dst = results / "persistgym_pilot" / R2_FILE / registered.CHECK_FILE
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return dst


def test_a_snapshot_or_alias_of_a_model_is_that_model(tmp_path):
    """A dated snapshot or alias of sol (as harnesses.pricing prices it) is sol: it defaults
    to high, cannot run outside pilots at medium, and needs the engagement check."""
    alias = f"{SOL}-2026-10-01"
    assert registered.model_family(alias) == SOL and registered.model_family(LUNA) == LUNA
    assert registered.model_family("gpt-6.1-solar") == "gpt-6.1-solar"   # not a hyphen
    assert registered.registered_effort(alias) == "high"
    assert cli.parse_args(["run", "--cell", "F-0", "--model", alias]).effort == "high"
    assert "registered reasoning effort 'high'" in guard("persistgym_validity", alias,
                                                         "medium", tmp_path)
    assert "need an ENGAGED engagement check" in guard("persistgym_validity", alias, "high",
                                                       tmp_path)
    assert "preset 'sol-chain' only" in guard("persistgym_validity", alias, "high", tmp_path,
                                              gen=DEFAULT)
    assert "preset 'sol-chain' only" in guard("persistgym_pilot", alias, "high", tmp_path,
                                              gen=DEFAULT)
    _write_check(tmp_path, "c", model=alias)
    assert guard("persistgym_validity", SOL, "high", tmp_path) is None
    assert guard("persistgym_validity", alias, "high", tmp_path) is None
    assert guard("persistgym_validity", f"{LUNA}-x", "high", tmp_path) is not None


def test_pilots_may_use_any_settings_but_sol_at_high_effort(tmp_path):
    """R3: pilots stay free, except that a sol pilot at high effort is R3's engagement check:
    sol-chain in F-r or F-0 only; and after R3's hard stop no sol pilot runs above medium
    effort ("no further variant or effort")."""
    for model, effort in ((LUNA, "high"), (LUNA, "medium"), (LUNA, "xhigh"), (SOL, "medium"),
                          (SOL, "low"), (SOL, "xhigh"), (SOL, "max")):
        for gen in (DEFAULT, VARIANT, "0" * 64):
            for cell in ("F-r", "W-n-0", "Σ-n-r"):
                assert guard("persistgym_pilot", model, effort, tmp_path, cell, gen,
                             "pilot", "base") is None
    assert guard("persistgym_pilot", SOL, "high", tmp_path) is None
    assert guard("persistgym_pilot", SOL, "high", tmp_path, "F-r") is None
    why = guard("persistgym_pilot", SOL, "high", tmp_path, gen=DEFAULT)
    assert "is PREREG.md §17.3 (amendment R3)'s engagement check" in why
    assert "--gen-preset sol-chain" in why
    for cell in ("W-n-r", "W-n-0", "Σ-n-r", "W-0"):
        why = guard("persistgym_pilot", SOL, "high", tmp_path, cell)
        assert "engagement check: it runs in the harness cells F-r, F-0 only" in why
    _r2_file(tmp_path)                                  # R2's NOT_ENGAGED binds the default
    assert guard("persistgym_pilot", SOL, "high", tmp_path) is None
    _write_check(tmp_path, "r3", verdict="NOT_ENGAGED")
    for effort in ("high", "xhigh", "max"):                            # R3's hard stop
        for gen in (DEFAULT, VARIANT, "0" * 64):
            why = guard("persistgym_pilot", SOL, effort, tmp_path, "F-0", gen) or ""
            assert registered.HARD_STOP in why or "--gen-preset sol-chain" in why
        assert registered.HARD_STOP in guard("persistgym_pilot", SOL, effort, tmp_path)
    for effort in ("none", "minimal", "low", "medium"):                # not above medium
        assert guard("persistgym_pilot", SOL, effort, tmp_path, "W-n-r", DEFAULT) is None
    assert guard("persistgym_pilot", LUNA, "xhigh", tmp_path) is None  # luna not covered
    assert registered.ABOVE_DEFAULT_EFFORT == ("high", "xhigh", "max")


@pytest.mark.parametrize("experiment", ["persistgym", "persistgym_validity",
                                        "statecarry_persistgym"])
def test_outside_pilots_only_the_registered_effort(tmp_path, experiment, monkeypatch):
    for gen in (DEFAULT, VARIANT, "0" * 64):
        for cell in ("F-r", "W-n-0"):                   # luna: any config and cell
            assert guard(experiment, LUNA, "medium", tmp_path, cell, gen) is None
    why = guard(experiment, LUNA, "high", tmp_path)
    assert "registered reasoning effort 'medium'" in why and "got 'high'" in why
    _write_check(tmp_path, "c1")
    monkeypatch.setitem(registered.G1_PASSED, SOL, VARIANT)
    assert guard(experiment, SOL, "high", tmp_path) is None
    why = guard(experiment, SOL, "medium", tmp_path)
    assert "registered reasoning effort 'high'" in why                # engaged or not
    assert guard(experiment, "gpt-unknown", "medium", tmp_path, "W-n-r", "0" * 64) is None


def test_sol_outside_pilots_plays_sol_chain_in_f_r_and_f_0_only(tmp_path, monkeypatch):
    _write_check(tmp_path, "c1")
    monkeypatch.setitem(registered.G1_PASSED, SOL, VARIANT)
    assert guard("persistgym", SOL, "high", tmp_path, "F-r", split="main",
                 variant="base") is None
    assert guard("persistgym", SOL, "high", tmp_path, "F-0", split="main",
                 variant="base") is None
    assert guard("persistgym_validity", SOL, "high", tmp_path, "F-0") is None
    for experiment in ("persistgym_validity", "persistgym"):
        for gen in (DEFAULT, "0" * 64):
            why = guard(experiment, SOL, "high", tmp_path, gen=gen)
            assert "on the generator preset 'sol-chain' only" in why
        for cell in ("W-n-r", "W-n-0", "Σ-n-r", "Σ-n-0", "W-0", "Σ-0-r"):
            why = guard(experiment, SOL, "high", tmp_path, cell)
            assert "in the harness cells F-r, F-0 only" in why and cell in why


def test_the_main_sweep_needs_g1_on_the_variant(tmp_path, monkeypatch):
    """R2's NOT_ENGAGED (default config) plus an ENGAGED R3 check: sol's validity run goes;
    its main sweep refuses until the G1 decision PR records the variant's hash."""
    _r2_file(tmp_path)
    _write_check(tmp_path, "r3")
    assert guard("persistgym_validity", SOL, "high", tmp_path) is None
    why = guard("persistgym", SOL, "high", tmp_path)
    assert "G1" in why and "G1_PASSED" in why
    monkeypatch.setitem(registered.G1_PASSED, SOL, "0" * 64)            # another config
    assert "G1_PASSED" in guard("persistgym", SOL, "high", tmp_path)
    monkeypatch.setitem(registered.G1_PASSED, SOL, VARIANT)
    assert guard("persistgym", SOL, "high", tmp_path) is None
    assert guard("statecarry_persistgym", SOL, "high", tmp_path) is None


def test_sols_validity_experiment_holds_its_validity_run_only(tmp_path):
    """PREREG §4.4, §17.3: sol's validity run needs no G1, so `persistgym_validity` lets sol
    run exactly that, F-0 on the validity split, restated or withheld. A base-variant or F-r
    run there (H2's contrast), or one on the main split, would bypass G1: it refuses."""
    _write_check(tmp_path, "r3")
    for variant in ("restated", "withheld"):
        assert guard("persistgym_validity", SOL, "high", tmp_path, "F-0",
                     variant=variant) is None
    for cell, split, variant in (("F-r", "validity", "restated"), ("F-0", "validity", "base"),
                                 ("F-r", "validity", "base"), ("F-0", "main", "restated"),
                                 ("F-r", "main", "base")):
        why = guard("persistgym_validity", SOL, "high", tmp_path, cell, split=split,
                    variant=variant)
        assert "as its validity run only" in why and f"got cell {cell}" in why
        assert f"--split {split}, --variant {variant}" in why
    # luna is not covered; sol's main sweep still waits for G1
    assert guard("persistgym_validity", LUNA, "medium", tmp_path, "F-r", DEFAULT, "main",
                 "base") is None
    assert "G1_PASSED" in guard("persistgym", SOL, "high", tmp_path, "F-r", split="validity",
                                variant="base")


def test_checks_are_keyed_by_generator_config(tmp_path):
    """A check file decides only for its own generator config: R2's NOT_ENGAGED (no hash,
    so the default config) refuses the default config for good and says nothing about the
    variant; a file on another config does not count for either."""
    _r2_file(tmp_path)
    assert "does not engage" in registered.engagement_refusal(tmp_path, SOL, DEFAULT)
    why = registered.engagement_refusal(tmp_path, SOL, VARIANT)
    assert "need an ENGAGED engagement check" in why and "does not engage" not in why
    _write_check(tmp_path, "elsewhere", rule={**registered.rule(),
                                              "generator_config_hash": "1" * 64})
    assert "need an ENGAGED engagement check" in registered.engagement_refusal(
        tmp_path, SOL, VARIANT)
    _write_check(tmp_path, "r3")
    assert registered.engagement_refusal(tmp_path, SOL, VARIANT) is None
    assert "does not engage" in registered.engagement_refusal(tmp_path, SOL, DEFAULT)
    assert registered.engagement_refusal(tmp_path, LUNA, DEFAULT) is None
    # a file under R2's rule but naming the variant, or under R3's rule naming the default,
    # does not count
    _write_check(tmp_path, "mixed", rule={**registered._r2_rule(),
                                          "generator_config_hash": VARIANT},
                 check_templates=SECOND)
    assert registered.engagement_refusal(tmp_path, SOL, VARIANT) is None


def test_the_r3_hard_stop(tmp_path, monkeypatch):
    """R3: a NOT_ENGAGED check on the variant refuses every non-pilot sol run for good, even
    next to an ENGAGED file and with G1 recorded; so does an UNSCORABLE check there twice."""
    monkeypatch.setitem(registered.G1_PASSED, SOL, VARIANT)
    _write_check(tmp_path, "a")
    _write_check(tmp_path, "z-not", verdict="NOT_ENGAGED", check_templates=SECOND)
    for experiment in ("persistgym_validity", "persistgym"):
        why = guard(experiment, SOL, "high", tmp_path)
        assert registered.HARD_STOP in why and "not testable in this task family" in why
    assert registered.hard_stop(tmp_path) is not None
    assert guard("persistgym_validity", LUNA, "medium", tmp_path, gen=DEFAULT) is None
    for p in (tmp_path / "persistgym_pilot").glob(f"*/{registered.CHECK_FILE}"):
        p.unlink()
    _write_check(tmp_path, "a", verdict="UNSCORABLE")
    assert registered.hard_stop(tmp_path) is None
    assert "runs once more on" in guard("persistgym_validity", SOL, "high", tmp_path)
    assert guard("persistgym_pilot", SOL, "high", tmp_path) is None   # the second check
    _write_check(tmp_path, "b", verdict="ENGAGED", check_templates=SECOND)
    assert guard("persistgym_validity", SOL, "high", tmp_path) is None  # UNSCORABLE, ENGAGED
    _write_check(tmp_path, "b", verdict="UNSCORABLE", check_templates=SECOND)
    why = guard("persistgym_validity", SOL, "high", tmp_path)
    assert "UNSCORABLE on pilot-000000, pilot-000001 and again" in why
    assert registered.HARD_STOP in why
    assert registered.HARD_STOP in guard("persistgym_pilot", SOL, "high", tmp_path)


def test_sol_outside_pilots_needs_an_engaged_check(tmp_path):
    def why():
        return guard("persistgym_validity", SOL, "high", tmp_path)
    assert "need an ENGAGED engagement check" in why()               # none at all
    _write_check(tmp_path, "unscorable", verdict="UNSCORABLE")
    _write_check(tmp_path, "luna", model=LUNA)                       # another model
    _write_check(tmp_path, "medium", effort="medium")                # another effort
    _write_check(tmp_path, "rule", rule={**registered.rule(), "reasoning_token_floor": 16})
    _write_check(tmp_path, "other", check_templates=["pilot-000004", "pilot-000005"])
    w = why()
    assert "need an ENGAGED engagement check" in w and "runs once more on" in w
    assert "under another rule or on other templates and do not count" in w
    assert "rule" in w and "other" in w
    (tmp_path / "persistgym_pilot" / "unscorable" / registered.CHECK_FILE).unlink()
    _write_check(tmp_path, "engaged")
    assert why() is None
    # a NOT_ENGAGED check refuses, whatever else is there (R3's hard stop)
    not_engaged = _write_check(tmp_path, "zz-not", verdict="NOT_ENGAGED")
    assert registered.HARD_STOP in why() and str(not_engaged) in why()
    not_engaged.unlink()
    assert why() is None
    # an unreadable check refuses until fixed, and stops sol's pilots at high too
    bad = tmp_path / "persistgym_pilot" / "bad" / registered.CHECK_FILE
    bad.parent.mkdir()
    bad.write_text("{not json", encoding="utf-8")
    assert "cannot read the engagement check" in why()
    assert "cannot read the engagement check" in guard("persistgym_pilot", SOL, "high",
                                                       tmp_path)
    bad.write_text(json.dumps({"verdict": "ENGAGED", "model": SOL, "effort": "high",
                               "rule": "R3", "check_run_ids": [], "check_templates": []}),
                   encoding="utf-8")
    assert "cannot read the engagement check" in why()               # rule not an object


def test_the_check_decides_in_r2s_order(tmp_path):
    """R2's order, on the variant (R3): the check on pilot templates 0 and 1 decides; only
    if it is UNSCORABLE does a second one on 2 and 3, and if that is UNSCORABLE too, R3's
    hard stop. A check is run once on its templates (a re-scoring of the same runs is the
    same check)."""
    def why():
        return guard("persistgym_validity", SOL, "high", tmp_path)

    def clear():
        for p in (tmp_path / "persistgym_pilot").glob(f"*/{registered.CHECK_FILE}"):
            p.unlink()
    _write_check(tmp_path, "b", check_templates=SECOND)                 # 2 and 3 first
    assert "counts only after an UNSCORABLE one on" in why()
    _write_check(tmp_path, "a", verdict="UNSCORABLE")
    assert why() is None                                                 # UNSCORABLE, ENGAGED
    _write_check(tmp_path, "b", verdict="UNSCORABLE", check_templates=SECOND)
    assert "UNSCORABLE on pilot-000000, pilot-000001 and again" in why()
    clear()
    _write_check(tmp_path, "a")
    _write_check(tmp_path, "a-again", check_run_ids=["a-F-r", "a-F-0"])  # the same runs
    assert why() is None
    _write_check(tmp_path, "a-wrong", verdict="UNSCORABLE", check_run_ids=["a-F-r", "a-F-0"])
    assert "disagree" in why()
    clear()
    _write_check(tmp_path, "a", verdict="UNSCORABLE")
    _write_check(tmp_path, "c")                                          # 0 and 1 again
    assert "more than one engagement check on pilot-000000, pilot-000001" in why()
    clear()
    _write_check(tmp_path, "a")
    _write_check(tmp_path, "b", verdict="UNSCORABLE", check_templates=SECOND)
    assert "so none was due on" in why()


def test_the_repositorys_own_state_after_r3s_hard_stop():
    """With this checkout's results/ (R2's NOT_ENGAGED file on the default config, and R3's
    NOT_ENGAGED file on the variant, 2026-10-03: R3's hard stop): no further check run, no
    sol pilot above medium and no H2 run of sol, on either config; sol pilots at medium and
    luna's runs are unaffected."""
    assert registered.HARD_STOP in registered.hard_stop(RESULTS)
    for cell in ("F-r", "F-0"):
        assert registered.HARD_STOP in guard("persistgym_pilot", SOL, "high", RESULTS, cell)
    assert registered.HARD_STOP in guard("persistgym_pilot", SOL, "xhigh", RESULTS)
    assert "preset 'sol-chain' only" in guard("persistgym_pilot", SOL, "high", RESULTS,
                                              gen=DEFAULT)
    assert guard("persistgym_pilot", SOL, "medium", RESULTS, gen=DEFAULT) is None
    assert registered.HARD_STOP in guard("persistgym_validity", SOL, "high", RESULTS)
    assert registered.HARD_STOP in guard("persistgym", SOL, "high", RESULTS, "F-r",
                                         split="main", variant="base")
    assert "does not engage" in registered.engagement_refusal(RESULTS, SOL, DEFAULT)
    assert guard("persistgym_validity", LUNA, "medium", RESULTS, gen=DEFAULT) is None


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


VALIDITY = ["run", "--split", "validity", "--variant", "restated", "--experiment",
            "persistgym_validity", "--n", "1", "--task-cell", "derived-rec-far",
            "--approved-block", "1-pilots", "--planned-usd", "1"]


@pytest.mark.parametrize(("args", "message"), [
    (["--cell", "F-0", "--model", SOL, "--gen-preset", "sol-chain"],
     "need an ENGAGED engagement check"),
    (["--cell", "F-0", "--model", SOL], "generator preset 'sol-chain' only"),
    (["--cell", "F-0", "--model", SOL, "--gen-preset", "sol-chain", *SMALL_SETS],
     "generator preset 'sol-chain' only"),
    (["--cell", "W-n-r", "--model", SOL, "--gen-preset", "sol-chain"],
     "harness cells F-r, F-0 only"),
    (["--cell", "F-0", "--model", SOL, "--effort", "medium"],
     "registered reasoning effort 'high'"),
    (["--cell", "F-0", "--model", LUNA, "--effort", "high"],
     "registered reasoning effort 'medium'"),
    (["--cell", "F-r", "--model", SOL, "--split", "pilot", "--experiment", "persistgym_pilot",
      *SMALL_SETS], "generator preset 'sol-chain' only"),
    (["--cell", "W-n-r", "--model", SOL, "--split", "pilot", "--experiment",
      "persistgym_pilot", "--gen-preset", "sol-chain"], "harness cells F-r, F-0 only"),
    (["--cell", "F-r", "--model", SOL, "--gen-preset", "sol-chain"],
     "as its validity run only"),
    (["--cell", "F-0", "--model", SOL, "--gen-preset", "sol-chain", "--variant", "base"],
     "as its validity run only"),
    (["--cell", "F-0", "--model", SOL, "--gen-preset", "sol-chain", "--split", "main"],
     "as its validity run only"),
    (["--cell", "F-0", "--model", LUNA, "--gen-set", "nope=1"], "--gen-set")])
def test_run_refuses_unregistered_settings_before_the_lock(armed, capsys, args, message):
    assert cli.main([*VALIDITY, *args]) == 2
    err = capsys.readouterr().err
    assert err.startswith("refused:") and message in err


@pytest.mark.parametrize(("args", "engaged"), [
    (["--model", LUNA, *SMALL_SETS], False),
    (["--model", SOL, "--gen-preset", "sol-chain"], True),
    (["--model", SOL, "--split", "pilot", "--experiment", "persistgym_pilot", "--effort",
      "low", *SMALL_SETS], False),
    (["--model", SOL, "--split", "pilot", "--experiment", "persistgym_pilot",
      "--gen-preset", "sol-chain"], False)])
def test_run_passes_registered_settings_on_to_the_paid_path(armed, monkeypatch, args, engaged):
    if engaged:
        _write_check(armed, "check")
    reached = []

    def paid_path(run_id, what, body):
        reached.append(what)
        return 0
    monkeypatch.setattr(cli, "_with_paid_lock", paid_path)
    assert cli.main([*VALIDITY, "--cell", "F-0", *args]) == 0
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


def _pilot_runs(run_ids) -> tuple[list[str], list[str]]:
    """Two committed sol pilot runs: their episode ids and generator config hashes."""
    seen = []
    for run_id in run_ids:
        meta = json.loads((RESULTS / "persistgym_pilot" / run_id / "meta.json")
                          .read_text(encoding="utf-8"))
        assert meta["model_requested"] == SOL
        seen.append((meta["config"]["episode_ids"], meta["config"]["generator_config_hashes"]))
    assert seen[0] == seen[1] and len(seen[0][0]) == 8
    return seen[0]


def _medium_pilot() -> tuple[list[str], list[str]]:
    """Block 1's sol pilot: its episode ids and generator config hashes (both runs)."""
    for run_id in MEDIUM_PILOT:
        meta = json.loads((RESULTS / "persistgym_pilot" / run_id / "meta.json")
                          .read_text(encoding="utf-8"))
        assert meta["reasoning_effort"] == "medium"
    return _pilot_runs(MEDIUM_PILOT)


def _check_run(argv: list[str], *, gen: str = VARIANT, allowed: bool = True):
    """A check run's parsed command: (cell, episode ids), after checking its settings and that
    it generates block 1's sol pilot episode ids under the config `gen`, and whether the
    guard lets it go (with this checkout's results/)."""
    a = cli.parse_args(argv)
    assert (a.cmd, a.model, a.effort, a.experiment) == ("run", SOL, "high", "persistgym_pilot")
    assert (a.approved_block, a.planned_usd, a.split, a.start) == ("1-pilots", 6.0, "pilot", 0)
    cfg = cli._gen_config(a.gen_preset, a.gen_set)
    eps = cli._run_matrix(a).episodes(a.split, a.start, cfg, a.variant)
    assert len(eps) <= cli.PILOT_MAX_EPISODES
    why = guard(a.experiment, a.model, a.effort, RESULTS, a.cell,
                runmeta.config_hash(cfg.to_dict()), a.split, a.variant)
    assert (why is None) is allowed, why
    ids, _ = _medium_pilot()
    assert [ep.episode_id for ep in eps] == ids
    assert sorted({ep.config_hash for ep in eps}) == [gen]
    return a.cell, [ep.episode_id for ep in eps]


def test_cli_docstring_examples_parse():
    commands = _commands(cli.__doc__)
    assert {c[0] for c in commands} >= {"cells", "dry-run", "pilot-report", "probe-summary",
                                        "echo-count", "reasoning-check", "probe-echo",
                                        "probe-replay", "run"}
    for argv in commands:
        a = cli.parse_args(argv)
        assert a.cmd == argv[0]
    # R3's engagement check run plays block 1's sol pilot templates, on sol-chain, at high;
    # it ran, found NOT_ENGAGED, and R3's hard stop refuses it now
    (check,) = [c for c in commands if c[0] == "run" and "gpt-6.1-sol" in c
                and "persistgym_pilot" in c and "sol-chain" in c]
    cell, ids = _check_run(check, allowed=False)
    assert cell == "F-r" and ids == _medium_pilot()[0]
    # sol's validity run (R3): F-0 on sol-chain, all 8 task cells, restated and withheld
    (validity,) = [c for c in commands if c[0] == "run" and "persistgym_validity" in c]
    a = cli.parse_args(validity)
    assert (a.cell, a.model, a.effort, a.gen_preset, a.split, a.start, a.n) == (
        "F-0", SOL, "high", "sol-chain", "validity", 0, 20)
    assert a.task_cell == ["all"] and a.variant == "restated"
    # sol's main sweep: D11 at T_d = 210, T_o = 70, at sol's registered effort, on sol-chain
    (sweep,) = [c for c in commands if c[0] == "run" and "persistgym" in c]
    a = cli.parse_args(sweep)
    assert a.effort == "high" and a.parallel == 16 and a.gen_preset == "sol-chain"
    m = cli._run_matrix(a).to_dict()
    assert m["templates_per_task_cell"] == {"observed-nonrec-far": 70, "observed-rec-far": 70,
                                            "derived-nonrec-far": 210, "derived-rec-far": 210}
    assert 2 * m["n_episodes"] == 1_120                     # F-r and F-0 (PREREG §17.2)


def _prereg_section(heading: str) -> str:
    text = (RESULTS.parent / "PREREG.md").read_text(encoding="utf-8")
    start = text.index(heading)
    end = text.find("\n### ", start + 1)
    return text[start:] if end < 0 else text[start:end]


def test_the_r2_check_commands_ran_the_default_config_and_r3_refuses_them_now():
    """PREREG §17.2's two check runs were F-r and F-0, sol at high effort, on the 16 episodes
    of block 1's medium-effort sol pilot (default config), under block 1 with $6 planned
    each; R2's check runs played exactly those (committed meta.json). Under R3 a sol pilot
    at high effort plays sol-chain only, so the guard refuses those commands now."""
    commands = _commands(_prereg_section("### 17.2 Amendment R2"))
    runs = [c for c in commands if c[0] == "run"]
    assert sorted(_check_run(c, gen=DEFAULT, allowed=False)[0] for c in runs) == ["F-0", "F-r"]
    assert _pilot_runs(R2_CHECK) == _medium_pilot()
    (rc,) = [c for c in commands if c[0] == "reasoning-check"]
    a = cli.parse_args(rc)
    assert a.reference == list(MEDIUM_PILOT)


def test_the_r3_check_commands_run_block_1s_sol_pilot_templates_on_sol_chain():
    """PREREG §17.3's two check runs are R2's with --gen-preset sol-chain: F-r and F-0, sol at
    high effort, the same 16 episode ids on sol-chain, under block 1 with $6 planned each;
    its reasoning-check command names R2's check runs as the reference. They ran on
    2026-10-03 and found NOT_ENGAGED, so R3's hard stop refuses them now."""
    commands = _commands(_prereg_section("### 17.3 Amendment R3"))
    runs = [c for c in commands if c[0] == "run" and "persistgym_pilot" in c]
    assert sorted(_check_run(c, allowed=False)[0] for c in runs) == ["F-0", "F-r"]
    assert [c for c in runs if "F-r" in c] == [runs[0]]                 # F-r first
    (rc,) = [c for c in commands if c[0] == "reasoning-check"]
    a = cli.parse_args(rc)
    assert a.reference == list(R2_CHECK)
    (validity,) = [c for c in commands if c[0] == "run" and "persistgym_validity" in c]
    a = cli.parse_args(validity)
    assert (a.cell, a.gen_preset, a.split, a.n, a.task_cell) == (
        "F-0", "sol-chain", "validity", 20, ["all"])


def test_the_check_files_rule_is_the_one_prereg_states():
    for heading in ("### 17.2 Amendment R2", "### 17.3 Amendment R3"):
        text = _prereg_section(heading)
        assert "E ≥ 0.50" in text and "32" in text
    text = _prereg_section("### 17.2 Amendment R2")
    assert "**Rule: reasoning engages iff E ≥ 0.50.**" in text
    assert "at least 32" in text and "fewer than 6 of the 8 derived-far episodes" in text
    r = registered.rule()
    assert (r["e_threshold"], r["reasoning_token_floor"], r["min_derived_far_ended_normally"],
            r["derived_far_episodes"]) == (0.5, 32, 6, 8)
    assert r["generator_config_hash"] in _prereg_section("### 17.3 Amendment R3")


def test_harness_config_effort_is_still_validated():
    with pytest.raises(ValueError, match="reasoning_effort"):
        HarnessConfig(reasoning_effort="extreme")
    assert dataclasses.replace(HarnessConfig(), reasoning_effort="high").reasoning_effort == \
        "high"
