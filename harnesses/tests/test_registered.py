"""Registered request settings (PREREG §6 as amended by R2, §17.2, and R3, §17.3;
harnesses/registered.py): `run` and `dry-run` default to the model's registered effort, `run`
refuses any other effort outside pilots, a non-pilot sol run off its `sol-chain` config or
cells, or without an ENGAGED engagement check on that config (and, outside its validity run,
without G1), a sol pilot at high effort off `sol-chain` or after R3's hard stop, a luna run
outside its pilots other than its main sweep and controls (PREREG §4.6, §17.6; its validity
runs are finished) or before its G1, and the probes keep their own registered settings. Also: the
command examples in the CLI docstring and in PREREG §17.2 and §17.3 parse, and the check's
runs play block 1's sol pilot templates."""

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
from persistgym.episode import ALL_CELLS

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
ALL_TASK_CELLS = tuple(c.id for c in ALL_CELLS)            # luna's sweep
NONREC = tuple(c.id for c in ALL_CELLS if not c.recoverable)  # the single-turn control


def guard(experiment: str, model: str, effort: str, root: Path, cell: str = "F-0",
          gen: str = VARIANT, split: str = "validity", variant: str = "restated",
          request: dict | None = None, templates: tuple[int, int] | None = None,
          task_cells: tuple[str, ...] | None = None, matrix: str | None = None) -> str | None:
    """The guard on these settings; the split and variant are a validity run's unless given,
    and the request settings, templates, task cells and matrix are not given unless given."""
    return registered.check_run_settings(experiment, model, effort, cell, gen, root,
                                         split=split, variant=variant, request=request,
                                         templates=templates, task_cells=task_cells,
                                         matrix=matrix)


def test_the_registered_settings():
    # claude-haiku-5-5 is registered for R8 (PREREG §17.8, not yet merged), whose guard
    # refuses every Haiku run until it is in effect (tests/test_haiku_guard.py)
    assert registered.REGISTERED_EFFORT == {LUNA: "medium", SOL: "high",
                                            "claude-haiku-5-5": "medium"}
    assert registered.registered_effort(LUNA) == "medium"
    assert registered.registered_effort(SOL) == "high"
    assert registered.registered_effort("gpt-unknown") == "medium"   # not in the table
    assert registered.ENGAGEMENT_REQUIRED == {SOL}
    assert registered.REGISTERED_GENERATOR == {SOL: "sol-chain"}       # luna: luna_refusal
    assert registered.REGISTERED_CELLS == {SOL: ("F-r", "F-0")}
    # luna's G1 GO (researcher, 2026-10-09) on the default config; none for sol (fail closed)
    assert registered.G1_PASSED == {LUNA: DEFAULT}
    assert DEFAULT == "3d6bc648eaa9b9e843fe6e70060495cd197630b0f2d585e66b3cd280b7a3968b"
    assert registered.LUNA_GENERATOR_HASH == DEFAULT
    assert registered.LUNA_CELLS == ("F-0", "W-0", "W-n-0", "Σ-n-0")
    assert registered.LUNA_SINGLE_TURN_CELL == "single-turn"
    assert registered.LUNA_RUN == {"split": ("main",), "variant": ("base", "restated")}
    # D13's request settings as frozen, as R4 registers them for sol's replication
    assert registered.LUNA_REQUEST == registered.H1_REPLICATION_REQUEST == {
        "mode": "standard", "service_tier": "flex", "W": None}
    assert registered.LUNA_T == 200                     # §4.2's rule, capped by R6 change 6
    assert (registered.LUNA_MODEL, registered.LUNA_EXPERIMENT) == (LUNA, "persistgym")
    # §4.6, D36: the full matrix on the 8 task cells; the single-turn control on its 4
    assert registered.LUNA_MATRIX == "full" and registered.LUNA_TASK_CELLS == ALL_TASK_CELLS
    assert len(ALL_TASK_CELLS) == 8 and registered.LUNA_SINGLE_TURN_TASK_CELLS == NONREC
    assert NONREC == ("observed-nonrec-near", "observed-nonrec-far", "derived-nonrec-near",
                      "derived-nonrec-far")
    # R6 change 1: the hard stop is on; the single-turn pilot, which R6 change 1 does not
    # list, goes under CLAUDE.md's pilot rule, with its allowance of 10
    assert registered.R6_HARD_STOP is True and registered.LUNA_SINGLE_TURN_PILOT_MAX == 10
    assert registered.R6_STOP.startswith("R6's hard stop (PREREG.md §17.6 (amendment R6) "
                                         "change 1)")
    assert "under CLAUDE.md's pilot rule (R6 change 1 does not list it)" in registered.R6_STOP
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


def test_model_family_is_the_model_or_a_dated_snapshot_of_it():
    """A model string names a registered model only as that model or a dated snapshot of it,
    "-YYYY-MM-DD" with a real date; any other suffix names no registered model (R6 then
    refuses it). The strings the API returned on every committed run are the bare names, and
    they map to themselves."""
    for name in (LUNA, SOL):
        for snapshot in (f"{name}-2026-10-01", f"{name}-2027-02-28", f"{name}-2028-02-29"):
            assert registered.model_family(snapshot) == name
        assert registered.model_family(name) == name
        for other in (f"{name}-x", f"{name}-latest", f"{name}-mini", f"{name}-2026-10",
                      f"{name}-20261001", f"{name}-2026-13-01", f"{name}-2026-02-30",
                      f"{name}-2026-10-01-x", f"{name}-2026-10-01T00", f"{name}--2026-10-01",
                      f"{name}2026-10-01", f"x-{name}", f"{name.upper()}"):
            assert registered.model_family(other) == other, other
            assert registered.registered_effort(other) == "medium"
    assert registered.model_family("gpt-6.1-solar") == "gpt-6.1-solar"
    # every model string the API returned, and every one requested, in the committed
    # meta.json files under results/ (a list for runs of several calls); results/raw/ is
    # never read
    seen = set()
    for path in (p for d in RESULTS.iterdir() if d.is_dir() and d.name != "raw"
                 for p in d.rglob("meta.json")):
        meta = json.loads(path.read_text(encoding="utf-8"))
        returned = meta.get("model_returned")
        for m in [meta.get("model_requested"),
                  *(returned if isinstance(returned, list) else [returned])]:
            if isinstance(m, str) and m.startswith("gpt-"):
                seen.add(m)
    assert seen == {LUNA, SOL}
    assert {registered.model_family(m) for m in seen} == {LUNA, SOL}


def test_a_snapshot_or_alias_of_a_model_is_that_model(tmp_path, pre_r6):
    """A dated snapshot of sol is sol: it defaults to high, cannot run outside pilots at
    medium, and needs the engagement check (with R6's hard stop off: the rules as before)."""
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


def test_pilots_may_use_any_settings_but_sol_at_high_effort(tmp_path, pre_r6):
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
    assert guard("persistgym_pilot", LUNA, "xhigh", tmp_path) is None  # luna's pilots: free
    assert registered.ABOVE_DEFAULT_EFFORT == ("high", "xhigh", "max")


@pytest.mark.parametrize("experiment", ["persistgym", "persistgym_validity",
                                        "statecarry_persistgym"])
def test_outside_pilots_only_the_registered_effort(tmp_path, experiment, monkeypatch, pre_r6):
    if experiment == "persistgym_validity":
        for gen in (DEFAULT, VARIANT, "0" * 64):
            for cell in ("F-0", "F-r", "W-n-0"):        # luna's validity runs: finished (R6)
                why = guard(experiment, LUNA, "medium", tmp_path, cell, gen)
                assert "luna's validity runs are finished" in why
    else:                                               # luna's main sweep only (luna_refusal)
        why = luna(experiment, "W-n-0", root=tmp_path)
        assert (why is None) is (experiment == "persistgym"), why
    why = guard(experiment, LUNA, "high", tmp_path)
    assert "registered reasoning effort 'medium'" in why and "got 'high'" in why
    _write_check(tmp_path, "c1")
    monkeypatch.setitem(registered.G1_PASSED, SOL, VARIANT)
    assert guard(experiment, SOL, "high", tmp_path) is None
    why = guard(experiment, SOL, "medium", tmp_path)
    assert "registered reasoning effort 'high'" in why                # engaged or not
    assert guard(experiment, "gpt-unknown", "medium", tmp_path, "W-n-r", "0" * 64) is None


def test_sol_outside_pilots_plays_sol_chain_in_f_r_and_f_0_only(tmp_path, monkeypatch, pre_r6):
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


def test_the_main_sweep_needs_g1_on_the_variant(tmp_path, monkeypatch, pre_r6):
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


def test_sols_validity_experiment_holds_its_validity_run_only(tmp_path, pre_r6):
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
    # luna's validity runs refuse (finished: G1 recorded; R6); sol's main sweep still waits
    # for G1
    assert "luna's validity runs are finished" in guard(
        "persistgym_validity", LUNA, "medium", tmp_path, "F-r", DEFAULT, "main", "base")
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


def test_the_r3_hard_stop(tmp_path, monkeypatch, pre_r6):
    """R3: a NOT_ENGAGED check on the variant refuses every non-pilot sol run for good, even
    next to an ENGAGED file and with G1 recorded; so does an UNSCORABLE check there twice."""
    monkeypatch.setitem(registered.G1_PASSED, SOL, VARIANT)
    _write_check(tmp_path, "a")
    _write_check(tmp_path, "z-not", verdict="NOT_ENGAGED", check_templates=SECOND)
    for experiment in ("persistgym_validity", "persistgym"):
        why = guard(experiment, SOL, "high", tmp_path)
        assert registered.HARD_STOP in why and "not testable in this task family" in why
    assert registered.hard_stop(tmp_path) is not None
    assert luna(root=tmp_path) is None                                  # luna's: not sol's stop
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


def test_sol_outside_pilots_needs_an_engaged_check(tmp_path, pre_r6):
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


def test_the_check_decides_in_r2s_order(tmp_path, pre_r6):
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


def test_the_repositorys_own_state_after_r3s_hard_stop(pre_r6):
    """With this checkout's results/ (R2's NOT_ENGAGED file on the default config, and R3's
    NOT_ENGAGED file on the variant, 2026-10-03: R3's hard stop) and R6's hard stop off: no
    further check run, no sol pilot above medium and no H2 run of sol, on either config; sol
    pilots at medium and luna's main sweep (G1 recorded) are unaffected, and luna's validity
    runs are finished. With R6 on, see test_r6_the_repositorys_own_state."""
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
    assert "luna's validity runs are finished" in guard("persistgym_validity", LUNA, "medium",
                                                         RESULTS, gen=DEFAULT)
    for cell in registered.LUNA_CELLS:
        assert luna(cell=cell) is None


# --- R6's hard stop (PREREG §17.6 change 1; registered.r6_refusal) ------------------------------

def _r6(why: str | None) -> bool:
    return why is not None and why.startswith(registered.R6_STOP)


def _single_turn_pilot(n: int = 2, cells: tuple[str, ...] = NONREC, root: Path = RESULTS,
                       split: str = "pilot", model: str = LUNA, gen: str = DEFAULT,
                       effort: str = "medium") -> str | None:
    """The guard on luna's single-turn pilot: `n` pilot templates x `cells`."""
    return guard("persistgym_pilot", model, effort, root, registered.LUNA_SINGLE_TURN_CELL,
                 gen, split, "base", registered.LUNA_REQUEST, (0, n), cells)


@pytest.mark.parametrize(("experiment", "model", "effort", "cell", "split", "variant"), [
    ("persistgym_validity", LUNA, "medium", "F-0", "validity", "restated"),
    ("persistgym_validity", LUNA, "medium", "F-0", "validity", "withheld"),
    ("persistgym_validity", SOL, "high", "F-0", "validity", "restated"),
    ("persistgym_validity", SOL, "medium", "F-0", "validity", "restated"),   # R4's
    ("persistgym_sol_h1", SOL, "medium", "F-0", "main", "base"),
    ("persistgym_sol_h1", LUNA, "medium", "F-0", "main", "base"),
    ("persistgym_pilot", LUNA, "medium", "F-0", "pilot", "base"),
    ("persistgym_pilot", LUNA, "medium", "W-n-0", "pilot", "base"),
    ("persistgym_pilot", LUNA, "medium", "F-r", "pilot", "restated"),
    ("persistgym_pilot", SOL, "medium", "W-0", "pilot", "base"),            # R4's pilot
    ("persistgym_pilot", SOL, "high", "F-r", "pilot", "base"),              # R3's check
    ("persistgym_pilot", SOL, "medium", "single-turn", "pilot", "base"),
    ("persistgym", SOL, "high", "F-r", "main", "base"),
    ("persistgym", SOL, "medium", "F-0", "main", "base"),
    ("statecarry_persistgym", LUNA, "medium", "F-0", "main", "base"),
    ("toggle_pilot", LUNA, "medium", None, "main", "base"),
    ("replay_probe", SOL, "medium", None, "main", "base")])
def test_r6_refuses_every_other_paid_run(tmp_path, monkeypatch, experiment, model, effort,
                                         cell, split, variant):
    """R6 change 1: outside luna's sweep and controls and the single-turn pilot, every paid
    run of the stream refuses, citing §17.6 change 1, whatever else would let it go (an
    ENGAGED check and G1 for sol, R4's replication G1) and for a dated snapshot too; with the
    hard stop off, the run is judged by the rules from before (it may pass or refuse)."""
    _write_check(tmp_path, "engaged")
    monkeypatch.setitem(registered.G1_PASSED, SOL, VARIANT)
    monkeypatch.setitem(registered.REPLICATION_G1_PASSED, SOL, DEFAULT)
    for m in (model, f"{model}-2026-10-01"):
        why = registered.r6_refusal(experiment, m, cell, tmp_path, split=split,
                                    task_cells=ALL_TASK_CELLS, templates=(0, 1))
        assert _r6(why) and f"got --experiment {experiment}, model {m}" in why
        assert "§17.6 (amendment R6) change 1" in why
        if cell is not None:
            for gen in (DEFAULT, VARIANT):
                assert guard(experiment, m, effort, tmp_path, cell, gen, split, variant,
                             registered.LUNA_REQUEST, (0, 1), ALL_TASK_CELLS, "full") == why
    monkeypatch.setattr(registered, "R6_HARD_STOP", False)
    assert registered.r6_refusal(experiment, model, cell, tmp_path, split=split) is None


@pytest.mark.parametrize("model", ["gpt-unknown", f"{LUNA}-x", f"{LUNA}-latest",
                                   f"{SOL}-2026-02-30", "gpt-6-luna2026-10-01"])
def test_r6_refuses_a_model_that_is_not_registered_everywhere(tmp_path, model):
    """Fail closed: a model string that names no registered model refuses in every
    experiment, the single-turn pilot and luna's sweep included; with R6 off such a model
    was let through at medium."""
    for experiment, cell, split in (("persistgym", "F-0", "main"),
                                    ("persistgym_pilot", "single-turn", "pilot"),
                                    ("persistgym_pilot", "F-0", "pilot"),
                                    ("persistgym_validity", "F-0", "validity"),
                                    ("toggle_pilot", None, "main")):
        why = registered.r6_refusal(experiment, model, cell, tmp_path, split=split,
                                    task_cells=NONREC, templates=(0, 1))
        assert _r6(why) and f"got model {model}, which is not a registered model" in why
    assert _r6(_single_turn_pilot(1, root=tmp_path, model=model))
    assert _r6(luna(model=model, root=tmp_path))


def test_r6_lets_lunas_sweep_controls_and_single_turn_pilot_through(tmp_path):
    """What R6 change 1 keeps: luna's main sweep and controls in persistgym (judged then by
    luna_refusal), and the single-turn control's pilot of at most 10 prompts (templates x task
    cells): on the pilot split, with the request the sweep sends (luna's registered effort,
    D13's settings, the default config), so that no pilot of another request uses up the
    allowance."""
    for cell in (*registered.LUNA_CELLS, registered.LUNA_SINGLE_TURN_CELL):
        assert luna(cell=cell, root=tmp_path) is None
        assert registered.r6_refusal("persistgym", LUNA, cell, tmp_path) is None
    assert luna(variant="restated", root=tmp_path) is None
    for n, cells in ((1, NONREC), (2, NONREC), (5, NONREC[:2]), (10, NONREC[:1])):
        assert _single_turn_pilot(n, cells, tmp_path) is None, (n, cells)
    for kw, got in (({"gen": "0" * 64}, "generator config 000000000000"),
                    ({"gen": VARIANT}, f"generator config {VARIANT[:12]}"),
                    ({"effort": "high"}, "--effort high"),
                    ({"effort": "low"}, "--effort low")):
        why = _single_turn_pilot(2, NONREC, tmp_path, **kw)
        assert _r6(why) and why.endswith(f"got a single-turn pilot with {got}")
    for request, got in (({**registered.LUNA_REQUEST, "service_tier": "default"},
                          "--service-tier default"),
                         ({**registered.LUNA_REQUEST, "mode": "pro"}, "--mode pro"),
                         (None, "--mode, --service-tier and --W (not given)")):
        why = guard("persistgym_pilot", LUNA, "medium", tmp_path,
                    registered.LUNA_SINGLE_TURN_CELL, DEFAULT, "pilot", "base", request,
                    (0, 2), NONREC)
        assert _r6(why) and why.endswith(f"got a single-turn pilot with {got}")
    for n, cells, prompts in ((3, NONREC, 12), (11, NONREC[:1], 11), (6, NONREC[:2], 12)):
        why = _single_turn_pilot(n, cells, tmp_path)
        assert _r6(why) and why.endswith(f"got a single-turn pilot with {prompts} prompts")
    why = _single_turn_pilot(2, NONREC, tmp_path, split="main")
    assert _r6(why) and "got a single-turn pilot with --split main" in why
    for templates, cells in ((None, NONREC), ((0, 2), None)):
        why = guard("persistgym_pilot", LUNA, "medium", tmp_path,
                    registered.LUNA_SINGLE_TURN_CELL, DEFAULT, "pilot", "base",
                    registered.LUNA_REQUEST, templates, cells)
        assert _r6(why) and "its prompts (templates and task cells not given)" in why


def test_r6_the_single_turn_pilot_plays_a_template_range_on_the_controls_cells(tmp_path):
    """The pilot's prompts: a non-empty range of pilot templates from index 0 up (first index
    < last index + 1) on a non-empty subset of the 4 non-recoverable task cells, none given
    twice. Anything else refuses, fail closed, though the CLI refuses most of it first."""
    def pilot(templates, cells):
        return guard("persistgym_pilot", LUNA, "medium", tmp_path,
                     registered.LUNA_SINGLE_TURN_CELL, DEFAULT, "pilot", "base",
                     registered.LUNA_REQUEST, templates, cells)

    assert pilot((0, 1), NONREC) is None
    assert pilot((3, 5), NONREC[1:3]) is None
    for templates in ((2, 2), (3, 1), (-1, 1)):
        why = pilot(templates, NONREC[:1])
        start, stop = templates
        assert _r6(why) and why.endswith(f"got a single-turn pilot with pilot templates "
                                         f"[{start}, {stop}) (an empty range or a negative "
                                         "index)")
    rec = next(c for c in ALL_TASK_CELLS if c not in NONREC)
    for cells in ((), (NONREC[0], NONREC[0]), (NONREC[1], rec), ("no-such-cell",),
                  ALL_TASK_CELLS):
        why = pilot((0, 1), cells)
        assert _r6(why) and why.endswith(
            f"got a single-turn pilot with task cells {', '.join(cells) or '(none)'} (the "
            f"control's are {', '.join(NONREC)}, each at most once)")


def _pilot_meta(results: Path, name: str, **fields) -> Path:
    """A committed pilot meta.json under `results`: a single-turn pilot of luna unless
    `fields` say otherwise."""
    meta = {"experiment": "persistgym_pilot", "run_id": name, "cell_or_config": "single-turn",
            "model_requested": LUNA, "n_episodes_run": 8, **fields}
    path = results / "persistgym_pilot" / name / "meta.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta), encoding="utf-8")
    return path


def test_r6_counts_the_prompts_of_earlier_single_turn_pilots(tmp_path):
    """At most 10 prompts in all: a single-turn pilot of luna that ran (its committed
    meta.json's n_episodes_run) counts against the next one; other pilots' meta.json do not
    count; an unreadable one refuses until fixed."""
    _pilot_meta(tmp_path, "harness", cell_or_config="F-0", n_episodes_run=8)
    _pilot_meta(tmp_path, "sol", model_requested=SOL)
    assert registered._single_turn_pilot_prompts(tmp_path) == (0, None)
    assert _single_turn_pilot(2, NONREC, tmp_path) is None                  # 8 prompts
    _pilot_meta(tmp_path, "first", model_requested=f"{LUNA}-2026-10-01")
    assert registered._single_turn_pilot_prompts(tmp_path) == (8, None)
    why = _single_turn_pilot(1, NONREC, tmp_path)                          # 8 + 4 > 10
    assert _r6(why) and why.endswith("got a single-turn pilot with 4 prompts after 8 in "
                                     "earlier single-turn pilots")
    assert _single_turn_pilot(1, NONREC[:2], tmp_path) is None             # 8 + 2 = 10
    _pilot_meta(tmp_path, "second", n_episodes_run=2)
    assert _r6(_single_turn_pilot(1, NONREC[:1], tmp_path))                # 10 + 1 > 10
    assert luna(root=tmp_path) is None                         # the sweep does not count them
    bad = _pilot_meta(tmp_path, "broken")
    bad.write_text("{not json", encoding="utf-8")
    why = _single_turn_pilot(1, NONREC[:1], tmp_path)
    assert _r6(why) and "cannot count the prompts of earlier single-turn pilots" in why
    bad.write_text(json.dumps({"cell_or_config": "single-turn", "model_requested": LUNA}),
                   encoding="utf-8")                                       # no n_episodes_run
    assert "cannot count the prompts" in _single_turn_pilot(1, NONREC[:1], tmp_path)


def test_r6_an_earlier_pilot_counts_the_prompts_it_planned(tmp_path):
    """An earlier single-turn pilot counts the larger of the prompts it played
    (`n_episodes_run`) and those it planned (its meta.json's `config.episode_ids`), so one
    that stopped early counts in full. A count that is negative or not an integer, or
    episode_ids that is not a list, refuses until fixed."""
    ids = [f"pilot-{i:06d}/single_turn" for i in range(8)]
    _pilot_meta(tmp_path, "stopped", n_episodes_run=1, config={"episode_ids": ids})
    assert registered._single_turn_pilot_prompts(tmp_path) == (8, None)    # planned > played
    why = _single_turn_pilot(1, NONREC[:3], tmp_path)                      # 8 + 3 > 10
    assert _r6(why) and why.endswith("got a single-turn pilot with 3 prompts after 8 in "
                                     "earlier single-turn pilots")
    assert _single_turn_pilot(1, NONREC[:2], tmp_path) is None             # 8 + 2 = 10
    _pilot_meta(tmp_path, "stopped", n_episodes_run=3, config={"episode_ids": ids[:2]})
    assert registered._single_turn_pilot_prompts(tmp_path) == (3, None)    # played > planned
    _pilot_meta(tmp_path, "stopped", n_episodes_run=3, config={})
    assert registered._single_turn_pilot_prompts(tmp_path) == (3, None)    # no episode_ids
    for fields, says in (({"n_episodes_run": -1}, "n_episodes_run -1 is negative"),
                         ({"n_episodes_run": "8"}, "n_episodes_run '8' is not an integer"),
                         ({"n_episodes_run": True}, "n_episodes_run True is not an integer"),
                         ({"n_episodes_run": 2.0}, "n_episodes_run 2.0 is not an integer"),
                         ({"config": {"episode_ids": "abc"}},
                          "config.episode_ids is not a list")):
        _pilot_meta(tmp_path, "stopped", **fields)
        _, why = registered._single_turn_pilot_prompts(tmp_path)
        assert why is not None and why.startswith("cannot count the prompts") and says in why
        why = _single_turn_pilot(1, NONREC[:1], tmp_path)
        assert _r6(why) and says in why


def test_r6_the_repositorys_own_state():
    """With this checkout's results/ and R6 on, as it is: luna's sweep and controls and its
    single-turn pilot go (no single-turn pilot has run yet); every sol run, every other luna
    pilot and every validity run refuses with R6's message, whatever R3's hard stop says."""
    assert registered.R6_HARD_STOP
    for cell in (*registered.LUNA_CELLS, registered.LUNA_SINGLE_TURN_CELL):
        assert luna(cell=cell) is None
    earlier, why = registered._single_turn_pilot_prompts(RESULTS)
    assert why is None
    assert (_single_turn_pilot(2) is None) is (earlier + 8 <= 10)  # once it has run: refused
    for experiment, model, effort, cell, split in (
            ("persistgym_pilot", SOL, "high", "F-r", "pilot"),
            ("persistgym_pilot", SOL, "medium", "W-0", "pilot"),
            ("persistgym_pilot", LUNA, "medium", "F-0", "pilot"),
            ("persistgym_validity", LUNA, "medium", "F-0", "validity"),
            ("persistgym_validity", SOL, "medium", "F-0", "validity"),
            ("persistgym_sol_h1", SOL, "medium", "F-0", "main"),
            ("persistgym", SOL, "high", "F-r", "main")):
        assert _r6(guard(experiment, model, effort, RESULTS, cell, DEFAULT, split, "base"))


# --- luna's main sweep (PREREG §4.6, §17.6 change 1; registered.luna_refusal) ------------------

SWEEP = object()  # luna()'s task cells and matrix: the main sweep's own


def luna(experiment: str = "persistgym", cell: str = "F-0", gen: str = DEFAULT,
         split: str = "main", variant: str = "base", model: str = LUNA,
         root: Path = RESULTS, request: dict | None = registered.LUNA_REQUEST,
         templates: tuple[int, int] | None = (0, registered.LUNA_T),
         task_cells=SWEEP, matrix=SWEEP) -> str | None:
    """The guard on a luna run; its main sweep's settings unless given: the full matrix on
    the 8 task cells, or for the single-turn control its 4 non-recoverable ones."""
    single = cell == registered.LUNA_SINGLE_TURN_CELL
    if task_cells is SWEEP:
        task_cells = NONREC if single else ALL_TASK_CELLS
    if matrix is SWEEP:
        matrix = None if single else "full"
    return guard(experiment, model, "medium", root, cell, gen, split, variant, request,
                 templates, task_cells, matrix)


def test_lunas_main_sweep_and_controls_go():
    """Experiment persistgym: the 4 replay-off cells on main base episodes, the restated-at-
    need control as full F-0 episodes, and the single-turn control's cell, on the default
    config (G1 recorded on it); a dated snapshot of luna is luna."""
    for cell in ("F-0", "W-0", "W-n-0", "Σ-n-0", registered.LUNA_SINGLE_TURN_CELL):
        assert luna(cell=cell) is None
    assert luna(variant="restated") is None
    assert luna(model=f"{LUNA}-2026-10-01") is None
    # any part of main templates 0-199 (T = registered.LUNA_T)
    for templates in ((0, 1), (0, 100), (100, 200), (190, 200), (199, 200)):
        assert luna(templates=templates) is None


@pytest.mark.parametrize(("changes", "got"), [
    ({"cell": "F-r"}, "got cell F-r"),                       # replay-on: toggle not verified
    ({"cell": "W-n-r"}, "got cell W-n-r"),
    ({"cell": "Σ-n-r"}, "got cell Σ-n-r"),
    ({"cell": "Σ-0-r"}, "got cell Σ-0-r"),
    ({"cell": "sigma-n-0"}, "got cell sigma-n-0"),           # the CLI gives the cell id
    ({"variant": "withheld"}, "got --variant withheld"),
    ({"variant": "restated", "cell": "W-0"}, "got --variant restated in cell W-0"),
    ({"variant": "restated", "cell": "single-turn"}, "--variant restated in cell single-turn"),
    ({"split": "validity"}, "got --split validity"),
    ({"split": "pilot"}, "got --split pilot"),
    ({"gen": VARIANT}, f"got generator config {VARIANT[:12]}"),
    ({"gen": "0" * 64}, "got generator config 000000000000"),
    ({"experiment": "statecarry_persistgym"}, "got --experiment statecarry_persistgym"),
    ({"experiment": "toggle_pilot"}, "got --experiment toggle_pilot"),
    ({"experiment": "replay_probe", "cell": "F-r", "variant": "withheld"},
     "got --experiment replay_probe; cell F-r; --variant withheld"),
    # D13's request settings (registered.LUNA_REQUEST); not given refuses (fail closed)
    ({"request": {**registered.LUNA_REQUEST, "service_tier": "default"}},
     "got --service-tier default"),
    ({"request": {**registered.LUNA_REQUEST, "mode": "pro"}}, "got --mode pro"),
    ({"request": {**registered.LUNA_REQUEST, "W": 30_000}}, "got --W 30000"),
    ({"request": None}, "got --mode, --service-tier and --W (not given)"),
    # main templates 0 to LUNA_T - 1 only (T = 200); not given refuses (fail closed)
    ({"templates": (0, 201)}, "got main templates 0-200"),
    ({"templates": (195, 205)}, "got main templates 195-204"),
    ({"templates": (200, 210)}, "got main templates 200-209"),
    ({"templates": None}, "got main templates (not given)"),
    ({"cell": "W-0", "request": {"mode": "pro", "service_tier": "flex", "W": 1000}},
     "got --mode pro; --W 1000"),
    # the full matrix on the 8 task cells (§4.6, D36); not given refuses (fail closed)
    ({"task_cells": ALL_TASK_CELLS[:7]}, f"got task cells {', '.join(ALL_TASK_CELLS[:7])}"),
    ({"task_cells": ("observed-nonrec-far",)}, "got task cells observed-nonrec-far"),
    ({"task_cells": ()}, "got task cells (none)"),
    ({"task_cells": None}, "got task cells (not given)"),
    ({"matrix": "d11"}, "got --matrix d11"),
    ({"matrix": "custom"}, "got --cell-templates"),
    ({"matrix": None}, "got run matrix (not given)"),
    ({"cell": "W-n-0", "matrix": "d11", "task_cells": NONREC},
     f"got --matrix d11; task cells {', '.join(NONREC)}"),
    # the single-turn control: its 4 non-recoverable task cells exactly
    ({"cell": "single-turn", "task_cells": NONREC[:2]},
     f"got task cells {', '.join(NONREC[:2])}"),
    ({"cell": "single-turn", "task_cells": ALL_TASK_CELLS},
     f"got task cells {', '.join(ALL_TASK_CELLS)}"),
    ({"cell": "single-turn", "task_cells": None}, "got task cells (not given)")])
def test_lunas_main_sweep_refuses_anything_else(changes, got, pre_r6, monkeypatch):
    """luna_refusal's own message (with R6's hard stop off, so that runs R6 refuses first,
    in other experiments, reach it too; with it on they refuse as R6's: test_r6_*)."""
    why = luna(**changes)
    assert why.startswith("outside persistgym_pilot, gpt-6-luna runs its main sweep and "
                          "controls only (PREREG.md §17.6 (amendment R6)")
    assert got in why and "3d6bc648eaa9" in why
    assert "with --mode standard, --service-tier flex and no --W (D13)" in why
    assert "main templates 0-199 (T = 200: PREREG §4.2's rule, capped by R6 change 6)" in why
    assert ("on all 8 task cells (the full matrix: --task-cell all, no --matrix d11 or "
            "--cell-templates) or the single-turn control on its 4 non-recoverable task "
            "cells") in why
    assert luna(model=f"{LUNA}-2026-10-01", **changes) is not None
    monkeypatch.setattr(registered, "R6_HARD_STOP", True)   # with R6 on: refused too
    assert luna(**changes) is not None


def test_lunas_main_sweep_needs_g1_on_its_config(monkeypatch, tmp_path):
    """Fail closed: without G1_PASSED on the default config, luna's main sweep and controls
    refuse; its single-turn pilot needs no G1. The pilot is judged against an empty results
    root, so the real pilot already run (which counts toward the 10-prompt limit) is not read."""
    monkeypatch.delitem(registered.G1_PASSED, LUNA)
    why = luna()
    assert "only after the researcher has recorded G1" in why and "G1_PASSED" in why
    assert "G1_PASSED" in luna(cell=registered.LUNA_SINGLE_TURN_CELL)
    monkeypatch.setitem(registered.G1_PASSED, LUNA, VARIANT)            # another config
    assert "G1_PASSED" in luna()
    assert _single_turn_pilot(2, root=tmp_path) is None
    monkeypatch.setitem(registered.G1_PASSED, LUNA, DEFAULT)
    assert luna() is None


def test_lunas_validity_runs_are_finished_and_sols_rules_unchanged(tmp_path, monkeypatch,
                                                                    pre_r6):
    """luna's validity runs are finished, with G1 recorded on them, and R6 change 1 allows no
    other paid runs: persistgym_validity refuses every luna run, whatever its cell, config,
    split, variant or request settings, and with G1 recorded or not; its pilots stay open.
    A luna run in persistgym_sol_h1 is judged by R4 (sol only); sol in persistgym still needs
    its check and G1 on sol-chain, and luna's G1 is not sol's."""
    for args in (("F-0", DEFAULT, "validity", "restated"),
                 ("F-0", DEFAULT, "validity", "withheld"),
                 ("W-n-r", "0" * 64, "main", "base"), ("F-0", DEFAULT, "main", "base")):
        why = luna("persistgym_validity", *args, root=tmp_path)
        assert why.startswith("persistgym_validity runs no gpt-6-luna run any more: luna's "
                              "validity runs are finished and G1 is recorded on them")
        assert "PREREG.md §17.6 (amendment R6) change 1 allows no other paid runs" in why
        assert luna("persistgym_validity", *args, model=f"{LUNA}-2026-10-01",
                    root=tmp_path) == why
    monkeypatch.delitem(registered.G1_PASSED, LUNA)
    assert "validity runs are finished" in luna("persistgym_validity", split="validity",
                                                variant="restated", root=tmp_path)
    assert luna("persistgym_pilot", "F-0", DEFAULT, "pilot", root=tmp_path) is None
    assert "persistgym_sol_h1 runs sol's H1 replication" in luna("persistgym_sol_h1",
                                                                 root=tmp_path)
    _write_check(tmp_path, "c1")
    assert SOL not in registered.G1_PASSED
    assert "G1_PASSED" in guard("persistgym", SOL, "high", tmp_path, "F-r", split="main",
                                variant="base")
    monkeypatch.setitem(registered.G1_PASSED, SOL, VARIANT)
    assert guard("persistgym", SOL, "high", tmp_path, "F-r", split="main",
                 variant="base") is None


LUNA_MAIN = ["run", "--model", LUNA, "--split", "main", "--n", "10", "--experiment",
             "persistgym", "--approved-block", "3-persistgym", "--planned-usd", "1"]


@pytest.mark.parametrize(("args", "message"), [
    (["--cell", "F-r"], "got cell F-r"),
    (["--cell", "W-n-r"], "got cell W-n-r"),
    (["--cell", "W-0", "--variant", "restated"], "--variant restated in cell W-0"),
    (["--cell", "F-0", "--variant", "withheld"], "got --variant withheld"),
    (["--cell", "F-0", *SMALL_SETS], "got generator config"),
    (["--cell", "F-0", "--gen-preset", "sol-chain"], "got generator config"),
    (["--cell", "F-0", "--split", "validity"], "got --split validity"),
    (["--cell", "F-0", "--experiment", "statecarry_persistgym"],
     "got --experiment statecarry_persistgym"),
    (["--cell", "F-0", "--effort", "high"], "registered reasoning effort 'medium'"),
    (["--cell", "F-0", "--service-tier", "default"], "got --service-tier default"),
    (["--cell", "F-0", "--mode", "pro"], "got --mode pro"),
    (["--cell", "W-0", "--W", "30000"], "got --W 30000"),
    (["--cell", "F-0", "--start", "190", "--n", "20"], "got main templates 190-209"),
    (["--cell", "F-0", "--start", "200"], "got main templates 200-209"),
    (["--cell", "F-0", "--n", "210", "--repeat-index", "1"], "got main templates 0-209"),
    # the full matrix on the 8 task cells (registered.LUNA_MATRIX, LUNA_TASK_CELLS)
    (["--cell", "F-0", "--task-cell", "observed-nonrec-far"],
     "got task cells observed-nonrec-far"),
    (["--cell", "W-0", "--task-cell", *ALL_TASK_CELLS[1:]],
     f"got task cells {', '.join(ALL_TASK_CELLS[1:])}"),
    (["--cell", "F-0", "--matrix", "d11", "--n", "30"],
     ("got --matrix d11; task cells observed-nonrec-far, observed-rec-far, "
      "derived-nonrec-far, derived-rec-far")),
    (["--cell", "F-0", "--cell-templates", *(f"{c}=10" for c in ALL_TASK_CELLS)],
     "got --cell-templates"),
    (["--cell", "F-0", "--variant", "restated", "--task-cell", "derived-rec-far"],
     "got task cells derived-rec-far"),
    # R6's hard stop: luna's other experiments
    (["--cell", "F-0", "--split", "validity", "--experiment", "persistgym_validity"],
     "R6's hard stop (PREREG.md §17.6 (amendment R6) change 1)"),
    (["--cell", "F-0", "--experiment", "persistgym_sol_h1"], "R6's hard stop"),
    (["--cell", "F-0", "--model", "gpt-unknown"], "which is not a registered model")])
def test_run_refuses_lunas_unregistered_main_runs_before_the_lock(armed, capsys, args,
                                                                  message):
    assert cli.main([*LUNA_MAIN, *args]) == 2
    err = capsys.readouterr().err
    assert err.startswith("refused:") and message in err


def test_run_passes_lunas_main_sweep_on_to_the_paid_path(armed, monkeypatch, capsys):
    """Each replay-off cell (Σ-n-0 by its ASCII id too), the restated-at-need control and the
    repeat go on to the paid path; without luna's G1 each refuses before the lock."""
    reached = []

    def paid_path(run_id, what, body):
        reached.append((run_id, what))
        return 0
    monkeypatch.setattr(cli, "_with_paid_lock", paid_path)
    for cell in ("F-0", "W-0", "W-n-0", "sigma-n-0", "Σ-n-0"):
        assert cli.main([*LUNA_MAIN, "--cell", cell]) == 0
    assert cli.main([*LUNA_MAIN, "--cell", "F-0", "--variant", "restated"]) == 0
    assert cli.main([*LUNA_MAIN, "--cell", "F-0", "--repeat-index", "1"]) == 0
    assert [w for _, w in reached] == [
        f"persistgym: {c} on {LUNA}, 80 episodes" for c in ("F-0", "W-0", "W-n-0", "Σ-n-0",
                                                             "Σ-n-0", "F-0")] + [
        f"persistgym: F-0 on {LUNA}, 8 episodes at repeat 1"]
    assert reached[3][0].endswith(f"-sigma-n-0-{LUNA}")
    assert reached[-1][0].endswith(f"-F-0-{LUNA}-repeat1")
    assert not reached[0][0].endswith("repeat1")
    monkeypatch.delitem(registered.G1_PASSED, LUNA)
    capsys.readouterr()
    assert cli.main([*LUNA_MAIN, "--cell", "F-0"]) == 2
    assert "G1_PASSED" in capsys.readouterr().err and len(reached) == 7


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
    (["--cell", "F-0", "--model", SOL, "--gen-preset", "sol-chain", "--effort", "medium"],
     "registered reasoning effort 'high'"),
    # R4 (§17.4): sol at medium on the default config in persistgym_validity is the H1
    # replication's validity run, on the observed task cells only
    (["--cell", "F-0", "--model", SOL, "--effort", "medium"],
     "got task cells derived-rec-far"),
    (["--cell", "F-0", "--model", LUNA, "--effort", "high"],
     "registered reasoning effort 'medium'"),
    (["--cell", "F-0", "--model", LUNA], "luna's validity runs are finished"),
    (["--cell", "F-0", "--model", LUNA, *SMALL_SETS], "luna's validity runs are finished"),
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
def test_run_refuses_unregistered_settings_before_the_lock(armed, capsys, args, message,
                                                            pre_r6):
    assert cli.main([*VALIDITY, *args]) == 2
    err = capsys.readouterr().err
    assert err.startswith("refused:") and message in err


@pytest.mark.parametrize(("args", "engaged"), [
    (["--model", SOL, "--gen-preset", "sol-chain"], True),
    (["--model", SOL, "--split", "pilot", "--experiment", "persistgym_pilot", "--effort",
      "low", *SMALL_SETS], False),
    (["--model", SOL, "--split", "pilot", "--experiment", "persistgym_pilot",
      "--gen-preset", "sol-chain"], False)])
def test_run_passes_registered_settings_on_to_the_paid_path(armed, monkeypatch, args, engaged,
                                                             pre_r6):
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


@pytest.mark.parametrize("args", [
    ["--cell", "F-0", "--model", SOL, "--gen-preset", "sol-chain"],
    ["--cell", "F-0", "--model", SOL, "--effort", "medium", "--task-cell", "observed-rec-far"],
    ["--cell", "F-0", "--model", LUNA],
    ["--cell", "F-0", "--model", SOL, "--split", "pilot", "--experiment", "persistgym_pilot",
     "--effort", "low", *SMALL_SETS],
    ["--cell", "F-0", "--model", SOL, "--split", "pilot", "--experiment", "persistgym_pilot",
     "--gen-preset", "sol-chain"],
    ["--cell", "W-n-0", "--model", LUNA, "--split", "pilot", "--experiment",
     "persistgym_pilot", *SMALL_SETS]])
def test_r6_refuses_the_runs_the_rules_above_judge_before_the_lock(armed, monkeypatch, capsys,
                                                                   args):
    """With R6 on (as it is), the validity runs, sol's runs and luna's harness-cell pilots
    that the tests above judge by the earlier rules refuse with R6's message, before the
    paid-run lock and even with an ENGAGED check and sol's G1 recorded."""
    _write_check(armed, "check")
    monkeypatch.setitem(registered.G1_PASSED, SOL, VARIANT)
    assert cli.main([*VALIDITY, *args]) == 2
    err = capsys.readouterr().err
    assert err.startswith(f"refused: {registered.R6_STOP}")


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
    (validity,) = [c for c in commands if c[0] == "run" and "persistgym_validity" in c
                   and "sol-chain" in c]
    a = cli.parse_args(validity)
    assert (a.cell, a.model, a.effort, a.gen_preset, a.split, a.start, a.n) == (
        "F-0", SOL, "high", "sol-chain", "validity", 0, 20)
    assert a.task_cell == ["all"] and a.variant == "restated"
    # sol's main sweep: D11 at T_d = 210, T_o = 70, at sol's registered effort, on sol-chain
    (sweep,) = [c for c in commands if c[0] == "run" and "persistgym" in c and SOL in c]
    a = cli.parse_args(sweep)
    assert a.effort == "high" and a.parallel == 16 and a.gen_preset == "sol-chain"
    m = cli._run_matrix(a).to_dict()
    assert m["templates_per_task_cell"] == {"observed-nonrec-far": 70, "observed-rec-far": 70,
                                            "derived-nonrec-far": 210, "derived-rec-far": 210}
    assert 2 * m["n_episodes"] == 1_120                     # F-r and F-0 (PREREG §17.2)
    # luna's main sweep (PREREG §4.6, §17.6): F-0 at T = 200 on the 8 task cells, at its
    # registered effort on the default config, and its repeat on templates 0, 10, ..., 190;
    # the guard lets both go (G1 recorded)
    luna_runs = [cli.parse_args(c) for c in commands
                 if c[0] == "run" and "persistgym" in c and LUNA in c]
    assert [a.repeat_index for a in luna_runs] == [0, 1]
    for a in luna_runs:
        assert (a.cell, a.effort, a.gen_preset, a.gen_set, a.split, a.start, a.n) == (
            "F-0", "medium", "default", [], "main", 0, registered.LUNA_T)
        assert (a.task_cell, a.variant, a.parallel, a.approved_block, a.milestone) == (
            ["all"], "base", 16, "3-persistgym", "M2")
        assert (a.mode, a.service_tier, a.W) == ("standard", "flex", None)
        gen = runmeta.config_hash(cli._gen_config(a.gen_preset, a.gen_set).to_dict())
        m = cli._run_matrix(a)
        cells = tuple(c for c, n in m.templates if n)
        assert m.name == "full" and cells == ALL_TASK_CELLS
        assert luna(cell=a.cell, gen=gen, request={"mode": a.mode, "service_tier":
                                                   a.service_tier, "W": a.W},
                    templates=(a.start, a.start + a.n), task_cells=cells,
                    matrix=m.name) is None
        assert m.n_episodes == (1600 if a.repeat_index == 0 else 160)
    assert cli._run_matrix(luna_runs[1]).played == tuple(range(0, 200, 10))


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
