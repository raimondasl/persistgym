"""R10's guard for claude-haiku-5-5's two notes-instruction variants (harnesses/registered.py
`_haiku_provenance_refusal`, `provenance_block_refusal`; PREREG §17.10, amendment R10): fail
closed.

* The repository: `R10_IN_EFFECT` is True, the experiment `persistgym_haiku_provenance` is in
  phase 1a and the PersistGym stream, and R8's and R9's values are unchanged.
* The rules: W-np-0 and W-npd-0, each as a pilot (`persistgym_pilot`, pilot templates 0-1 on
  the 4 far task cells, at most 2 per cell counting unfinished runs, each under a new run id,
  none once the cell's newest pilot has passed any pilot check) or a main run in R10's
  experiment (the full matrix on the 4 far task cells, main templates within 0-199 at repeat
  0), base episodes, on exactly claude-haiku-5-5 with R8's effort, config and request
  settings, the main runs after `HAIKU_G1_PASSED` and after a GO pilot check that names each
  cell's newest pilot, which passed. Anything else refuses, naming §17.10: another cell in
  R10's experiment, R10's cells in R8's or R9's experiments, another pilot shape, near task
  cells, another split, variant, matrix, template range, repeat, effort, config or request,
  and every other model, with R6's hard stop on or off.
* The kill switches: with `R10_IN_EFFECT` False every run of the two cells and every run in
  the experiment refuses, and R8's and R9's runs still pass. With `R8_IN_EFFECT` False they
  refuse too.
* The blocks: R10's cells run under block `6-haiku-provenance` only, and that block funds
  them only (`provenance_block_refusal`), whatever padding the block name carries, and the CLI
  refuses a padded block name. The transport admits a pilot or a main run under a
  block that lists R10's experiment. End to end, through the real guarded transport with a
  fake-backed client: a blinded W-np-0 pilot and a W-npd-0 main run under block 6, each
  request carrying its cell's notes text; and the cross-funding runs refuse with no call.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from common import costs, paidlock
from common.tests.gitrepo import FROZEN_PREREG, approval_line, decisions_text, guarded_repo
from harnesses import anthropic_transport, cli, registered
from harnesses.anthropic_transport import AnthropicMessagesTransport
from harnesses.cells import DISCLOSURE_SENTENCE, PROVENANCE_SENTENCE
from harnesses.fake import FakeModel
from harnesses.openai_transport import ALLOW_ENV
from harnesses.tests.test_haiku_guard import (
    ALL8,
    DEFAULT,
    HAIKU,
    MAIN,
    NONREC,
    OTHER,
    OTHER_CLAUDE,
    PILOT,
    RUNS,
    VALIDITY,
    _FakeBackedClient,
    guard,
)

PROV = "persistgym_haiku_provenance"
NOTES = "persistgym_haiku_notes"
BLOCK = "6-haiku-provenance"
FAR = ("observed-nonrec-far", "observed-rec-far", "derived-nonrec-far", "derived-rec-far")
CELLS = ("W-np-0", "W-npd-0")


def main_guard(cell, root, repeat_index=0, **kw):
    """R10's main run of `cell`, with any setting replaced by `kw`."""
    kw.setdefault("task_cells", FAR)
    kw.setdefault("templates", (0, 200))
    return registered.check_run_settings(
        kw.pop("experiment", PROV), kw.pop("model", HAIKU), kw.pop("effort", "medium"), cell,
        kw.pop("gen", DEFAULT), root, split=kw.pop("split", "main"),
        variant=kw.pop("variant", "base"), task_cells=kw.pop("task_cells"),
        request=kw.pop("request", {"mode": "standard", "service_tier": "standard", "W": None}),
        templates=kw.pop("templates"), matrix=kw.pop("matrix", "full"),
        repeat_index=repeat_index, **kw)


def pilot_guard(cell, root, **kw):
    """R10's pilot of `cell` on pilot templates 0-1 and the far task cells."""
    kw.setdefault("templates", (0, 2))
    return main_guard(cell, root, experiment=PILOT, split="pilot", **kw)


@pytest.fixture
def no_g1(monkeypatch):
    monkeypatch.setattr(registered, "HAIKU_G1_PASSED", {})


def write_pilot_meta(results_root, run_id, cell, started="2026-11-01T00:00:00+00:00",
                     model=HAIKU, experiment=PILOT):
    folder = results_root / PILOT / run_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "meta.json").write_text(json.dumps(
        {"run_id": run_id, "cell_or_config": cell, "model_requested": model,
         "experiment": experiment, "started_utc": started}), encoding="utf-8")


def write_pilot_go(results_root, *, go=True, cells=CELLS, stamp="20261101T000000Z",
                   metas=True, passed=True, runs=None):
    """A pilot check under results_root/haiku_provenance_pilot/<stamp>/ naming one pilot run
    per cell of `cells` (or `runs` as given), and (with `metas`) those runs' meta.json under
    persistgym_pilot/."""
    if runs is None:
        runs = [{"run_id": f"pilot-{cell}", "cell": cell, "passed": passed} for cell in cells]
        if metas:
            for r in runs:
                write_pilot_meta(results_root, r["run_id"], r["cell"])
    folder = results_root / registered.PROVENANCE_PILOT_CHECK / stamp
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "check.json").write_text(json.dumps({"go": go, "runs": runs}), encoding="utf-8")


@pytest.fixture
def pilot_go(tmp_path):
    """Both R10 pilots passed their check (the main runs' gate)."""
    write_pilot_go(tmp_path)


# --- the repository ------------------------------------------------------------------------------

def test_the_repository_has_r10_in_effect_beside_r8s_and_r9s_values():
    assert registered.R10_IN_EFFECT is True
    assert registered.R9_IN_EFFECT is True and registered.R8_IN_EFFECT is True
    assert registered.R10_REF == "PREREG.md §17.10 (amendment R10)"
    assert registered.HAIKU_PROVENANCE_EXPERIMENT == PROV
    assert registered.HAIKU_PROVENANCE_CELLS == CELLS
    assert registered.HAIKU_PROVENANCE_TASK_CELLS == FAR
    assert registered.HAIKU_PROVENANCE_BLOCK == BLOCK
    assert costs.EXPERIMENT_PHASE[PROV] == "1a"
    assert paidlock.EXPERIMENT_STREAM[PROV] == paidlock.PERSISTGYM
    assert registered.HAIKU_CELLS == ("F-0", "W-0") and registered.HAIKU_T == 200
    assert registered.HAIKU_NOTES_CELL == "W-n-0"
    assert PROV not in registered.HAIKU_EXPERIMENTS
    assert not set(CELLS) & set(registered.HAIKU_PILOT_CELLS)


# --- the rules -----------------------------------------------------------------------------------

@pytest.mark.parametrize("cell", CELLS)
@pytest.mark.parametrize("templates", [(0, 200), (0, 1), (100, 200), (199, 200)])
def test_r10s_main_runs_pass(tmp_path, pilot_go, cell, templates):
    assert main_guard(cell, tmp_path, templates=templates) is None


@pytest.mark.parametrize("cell", CELLS)
def test_r10s_pilots_pass_without_g1_or_a_check(tmp_path, no_g1, cell):
    assert pilot_guard(cell, tmp_path) is None


@pytest.mark.parametrize("kw, wrong", [
    ({"task_cells": FAR[:1]}, "task cells"),
    ({"task_cells": ("derived-rec-far", "observed-rec-far")}, "task cells"),
    ({"templates": (0, 1)}, "pilot templates 0-0"),
    ({"templates": (2, 4)}, "pilot templates 2-3"),
    ({"templates": (0, 3)}, "pilot templates 0-2"),
    ({"templates": None}, "pilot templates (not given)"),
    ({"matrix": "d11"}, "--matrix d11"),
    ({"matrix": None}, "run matrix (not given)"),
])
def test_a_pilot_plays_the_registered_shape_only(tmp_path, kw, wrong):
    why = pilot_guard("W-np-0", tmp_path, **kw)
    assert why is not None and wrong in why and registered.R10_REF in why, why


def test_at_most_two_pilots_per_cell(tmp_path):
    for n in range(2):
        write_pilot_meta(tmp_path, f"earlier-{n}", "W-np-0", started=f"2026-11-01T0{n}:00:00")
        if n == 0:
            assert pilot_guard("W-np-0", tmp_path) is None
    why = pilot_guard("W-np-0", tmp_path)
    assert why is not None and "2 pilot runs" in why and "pull request" in why
    assert pilot_guard("W-npd-0", tmp_path) is None  # the other cell's count is its own


def test_a_main_run_needs_a_go_pilot_check(tmp_path):
    why = main_guard("W-np-0", tmp_path)
    assert why is not None and "no check under" in why and registered.R10_REF in why


@pytest.mark.parametrize("kw, wrong", [
    ({"go": False}, "says STOP"),
    ({"cells": ("W-np-0",)}, "not one pilot of each"),
    ({"cells": ("W-np-0", "W-np-0")}, "not one pilot of each"),
    ({"cells": ()}, "covers no run"),
    ({"metas": False}, "no readable"),
    ({"passed": False}, "did not pass"),
    ({"runs": [{"run_id": "../persistgym_haiku_provenance/m1", "cell": "W-np-0", "passed": True},
               {"run_id": "pilot-W-npd-0", "cell": "W-npd-0", "passed": True}]},
     "not a run's name"),
    ({"runs": [{"run_id": "..", "cell": "W-np-0", "passed": True},
               {"run_id": "pilot-W-npd-0", "cell": "W-npd-0", "passed": True}]},
     "not a run's name"),
])
def test_a_main_run_refuses_a_check_that_is_not_a_go_for_both(tmp_path, kw, wrong):
    write_pilot_go(tmp_path, **kw)
    why = main_guard("W-npd-0", tmp_path)
    assert why is not None and wrong in why and registered.R10_REF in why, why


def test_the_latest_pilot_check_decides(tmp_path):
    write_pilot_go(tmp_path, stamp="20261101T000000Z")
    write_pilot_go(tmp_path, go=False, stamp="20261101T010000Z")
    assert "says STOP" in main_guard("W-np-0", tmp_path)
    write_pilot_go(tmp_path, stamp="20261101T020000Z")
    assert main_guard("W-np-0", tmp_path) is None


@pytest.mark.parametrize("text", ["[]", '"go"', '{"go": true, "runs": null}',
                                  '{"go": true, "runs": ["p1", "p2"]}', "not json"])
def test_a_malformed_check_refuses_and_does_not_raise(tmp_path, text):
    folder = tmp_path / registered.PROVENANCE_PILOT_CHECK / "20261101T000000Z"
    folder.mkdir(parents=True)
    (folder / "check.json").write_text(text, encoding="utf-8")
    why = main_guard("W-np-0", tmp_path)
    assert why is not None and registered.R10_REF in why
    assert pilot_guard("W-np-0", tmp_path) is not None


def test_a_folder_not_named_by_a_check_time_is_not_a_check(tmp_path):
    write_pilot_go(tmp_path)
    write_pilot_go(tmp_path, go=False, stamp="manual")
    assert main_guard("W-np-0", tmp_path) is None


def test_a_check_naming_a_non_haiku_or_non_pilot_run_refuses(tmp_path):
    write_pilot_go(tmp_path)
    write_pilot_meta(tmp_path, "pilot-W-np-0", "W-np-0", model="gpt-6-luna")
    assert "not a claude-haiku-5-5 pilot" in main_guard("W-np-0", tmp_path)
    write_pilot_meta(tmp_path, "pilot-W-np-0", "W-np-0", experiment=PROV)
    assert "not a claude-haiku-5-5 pilot" in main_guard("W-np-0", tmp_path)


def test_a_later_pilot_makes_the_check_stale(tmp_path):
    """A GO check vouches for the pilots it names: a later pilot of a cell, which no check has
    read, refuses the main runs until the check is run again."""
    write_pilot_go(tmp_path)
    assert main_guard("W-npd-0", tmp_path) is None
    write_pilot_meta(tmp_path, "pilot-W-np-0-again", "W-np-0", started="2026-11-01T05:00:00")
    why = main_guard("W-npd-0", tmp_path)
    assert why is not None and "newest pilot is pilot-W-np-0-again" in why
    write_pilot_go(tmp_path, stamp="20261101T060000Z", runs=[
        {"run_id": "pilot-W-np-0-again", "cell": "W-np-0", "passed": True},
        {"run_id": "pilot-W-npd-0", "cell": "W-npd-0", "passed": True}])
    assert main_guard("W-npd-0", tmp_path) is None


def test_no_further_pilot_of_a_cell_that_passed(tmp_path):
    """The second pilot run is a re-run after a failure only: once a cell's newest pilot has
    passed the latest check, another pilot of it refuses, and a cell that failed may re-run."""
    write_pilot_go(tmp_path, go=False, runs=[
        {"run_id": "pilot-W-np-0", "cell": "W-np-0", "passed": True},
        {"run_id": "pilot-W-npd-0", "cell": "W-npd-0", "passed": False}])
    write_pilot_meta(tmp_path, "pilot-W-np-0", "W-np-0")
    write_pilot_meta(tmp_path, "pilot-W-npd-0", "W-npd-0")
    why = pilot_guard("W-np-0", tmp_path)
    assert why is not None and "passed R10's pilot check" in why and "pull request" in why
    assert pilot_guard("W-npd-0", tmp_path) is None
    assert "says STOP" in main_guard("W-np-0", tmp_path)


def test_a_check_whose_run_is_another_cell_refuses(tmp_path):
    write_pilot_go(tmp_path)
    meta = tmp_path / PILOT / "pilot-W-np-0" / "meta.json"
    meta.write_text(json.dumps({"run_id": "pilot-W-np-0", "cell_or_config": "W-0",
                                "model_requested": HAIKU}), encoding="utf-8")
    why = main_guard("W-np-0", tmp_path)
    assert why is not None and "but its meta.json says 'W-0'" in why


@pytest.mark.parametrize("cell", CELLS)
def test_main_runs_need_g1(tmp_path, no_g1, cell):
    why = main_guard(cell, tmp_path)
    assert why is not None and "HAIKU_G1_PASSED" in why and registered.R10_REF in why


def test_repeat_1_refuses(tmp_path):
    why = main_guard("W-np-0", tmp_path, repeat_index=1)
    assert why is not None and "--repeat-index 1" in why and registered.R10_REF in why


def test_r10_runs_exactly_the_id_r9_ran(tmp_path, pilot_go):
    """R10 pins the requested model to claude-haiku-5-5, the ID R9 ran and the pilot check
    pins the served string to, so a dated snapshot refuses."""
    for why in (main_guard("W-npd-0", tmp_path, model=f"{HAIKU}-2026-10-01"),
                pilot_guard("W-np-0", tmp_path, model=f"{HAIKU}-2026-10-01")):
        assert why is not None and f"model {HAIKU}-2026-10-01" in why and registered.R10_REF in why


@pytest.mark.parametrize("cell, kw, wrong", [
    ("W-n-0", {}, "cell W-n-0"),
    ("W-0", {}, "cell W-0"),
    ("F-0", {}, "cell F-0"),
    ("Σ-n-0", {}, "cell Σ-n-0"),
    ("single-turn", {"task_cells": NONREC, "matrix": None}, "cell single-turn"),
    ("W-np-0", {"task_cells": ALL8}, "task cells"),
    ("W-np-0", {"task_cells": FAR[:3]}, "task cells"),
    ("W-np-0", {"task_cells": NONREC}, "task cells"),
    ("W-np-0", {"task_cells": None}, "task cells (not given)"),
    ("W-np-0", {"split": "pilot", "templates": (0, 1)}, "--split pilot"),
    ("W-np-0", {"split": "validity", "templates": (0, 20)}, "--split validity"),
    ("W-npd-0", {"variant": "restated"}, "--variant restated"),
    ("W-npd-0", {"matrix": "d11"}, "--matrix d11"),
    ("W-npd-0", {"matrix": "custom"}, "--cell-templates"),
    ("W-npd-0", {"matrix": None}, "run matrix (not given)"),
    ("W-npd-0", {"templates": (0, 201)}, "main templates 0-200"),
    ("W-npd-0", {"templates": (200, 210)}, "main templates 200-209"),
    ("W-npd-0", {"templates": None}, "main templates (not given)"),
    ("W-np-0", {"effort": "high"}, "--effort high"),
    ("W-np-0", {"gen": OTHER}, "generator config 000000000000"),
    ("W-np-0", {"request": {"mode": "standard", "service_tier": "standard", "W": 24000}},
     "--W 24000"),
    ("W-np-0", {"request": None}, "--W (not given)"),
])
def test_anything_else_in_r10s_experiment_refuses(tmp_path, cell, kw, wrong):
    why = main_guard(cell, tmp_path, **kw)
    assert why is not None and wrong in why and registered.R10_REF in why, why


@pytest.mark.parametrize("cell", CELLS)
@pytest.mark.parametrize("experiment, kw, wrong", [
    (MAIN, {"task_cells": ALL8}, f"--experiment {MAIN}"),
    (NOTES, {"task_cells": ALL8}, f"--experiment {NOTES}"),
    (VALIDITY, {"split": "validity", "templates": (0, 20)}, f"--experiment {VALIDITY}"),
    (PILOT, {"split": "pilot", "templates": (0, 2), "task_cells": ("observed-nonrec-near",)},
     "task cells"),
    (PILOT, {"split": "pilot", "templates": (0, 2), "task_cells": ()}, "task cells (none)"),
    (PILOT, {"split": "main"}, "--split main"),
    (PILOT, {"split": "pilot", "templates": (0, 2), "variant": "withheld"}, "--variant withheld"),
    (PILOT, {"split": "pilot", "templates": (0, 2), "effort": "low"}, "--effort low"),
])
def test_r10s_cells_refuse_anywhere_else(tmp_path, cell, experiment, kw, wrong):
    why = main_guard(cell, tmp_path, experiment=experiment, **kw)
    assert why is not None and wrong in why and registered.R10_REF in why, why


@pytest.mark.parametrize("model", OTHER_CLAUDE)
def test_every_other_claude_model_refuses(tmp_path, model):
    why = main_guard("W-np-0", tmp_path, model=model)
    assert why is not None and model in why


@pytest.mark.parametrize("model", OTHER_CLAUDE)
def test_with_r6_off_every_other_claude_model_refuses_under_r10(tmp_path, monkeypatch, model):
    monkeypatch.setattr(registered, "R6_HARD_STOP", False)
    why = main_guard("W-np-0", tmp_path, model=model)
    assert why is not None and f"model {model}" in why and registered.R10_REF in why


@pytest.mark.parametrize("r6_on", [True, False])
@pytest.mark.parametrize("r10_on", [True, False])
@pytest.mark.parametrize("model", ["gpt-6-luna", "gpt-6.1-sol", "gpt-6-luna-mini"])
@pytest.mark.parametrize("cell", CELLS)
def test_openai_models_never_run_r10s_cells(tmp_path, pilot_go, monkeypatch, model, cell,
                                            r6_on, r10_on):
    """With R6's hard stop off too, and with R10 on or off: any run of R10's cells goes to
    the Haiku guard, which refuses every other model."""
    monkeypatch.setattr(registered, "R6_HARD_STOP", r6_on)
    monkeypatch.setattr(registered, "R10_IN_EFFECT", r10_on)
    for why in (main_guard(cell, tmp_path, model=model),
                pilot_guard(cell, tmp_path, model=model),
                main_guard(cell, tmp_path, model=model, task_cells=ALL8)):
        assert why is not None, (model, cell, r6_on, r10_on)
        if not r6_on:
            assert registered.R10_REF in why, why


@pytest.mark.parametrize("model", ["gpt-6-luna", "gpt-6.1-sol", "gpt-6-luna-mini",
                                   "gemini-3.8-flash"])
@pytest.mark.parametrize("experiment, cell", [(PROV, "W-n-0"), (PROV, "F-0"),
                                              (NOTES, "W-n-0"), (MAIN, "F-0"), (MAIN, "W-0")])
def test_with_r6_off_openai_models_never_run_in_r9s_or_r10s_experiment(tmp_path, monkeypatch,
                                                                        model, experiment, cell):
    monkeypatch.setattr(registered, "R6_HARD_STOP", False)
    why = guard(experiment, cell, tmp_path, model=model)
    assert why is not None and f"model {model}" in why, why


def test_r8s_and_r9s_runs_are_unchanged(tmp_path):
    for experiment, cell, kw in RUNS:
        assert guard(experiment, cell, tmp_path, **kw) is None, (experiment, cell, kw)
    assert guard(NOTES, "W-n-0", tmp_path) is None
    assert guard(MAIN, "W-n-0", tmp_path) is not None


# --- the kill switches ---------------------------------------------------------------------------

def test_with_r10_off_its_runs_refuse_and_r8s_and_r9s_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(registered, "R10_IN_EFFECT", False)
    for why in (main_guard("W-np-0", tmp_path), pilot_guard("W-npd-0", tmp_path),
                main_guard("W-0", tmp_path)):
        assert why is not None and registered.R10_REF in why and "R10_IN_EFFECT" in why
    for experiment, cell, kw in RUNS:
        assert guard(experiment, cell, tmp_path, **kw) is None
    assert guard(NOTES, "W-n-0", tmp_path) is None


@pytest.mark.parametrize("r6_on", [True, False])
def test_with_r8_off_r10s_runs_refuse_too(tmp_path, monkeypatch, r6_on):
    monkeypatch.setattr(registered, "R8_IN_EFFECT", False)
    monkeypatch.setattr(registered, "R6_HARD_STOP", r6_on)
    for why in (main_guard("W-np-0", tmp_path), pilot_guard("W-np-0", tmp_path)):
        assert why is not None and registered.R8_REF in why


def test_with_r6_off_r10s_runs_are_still_held_to_r10(tmp_path, monkeypatch, pilot_go):
    monkeypatch.setattr(registered, "R6_HARD_STOP", False)
    assert main_guard("W-npd-0", tmp_path) is None
    assert registered.R10_REF in main_guard("W-n-0", tmp_path)


# --- the blocks ----------------------------------------------------------------------------------

@pytest.mark.parametrize("block, cell, refused", [
    (BLOCK, "W-np-0", False),
    (BLOCK, "W-npd-0", False),
    ("4-haiku", "W-np-0", True),        # R8's block funds no R10 cell, its pilots included
    ("5-haiku-notes", "W-npd-0", True),
    (None, "W-np-0", True),
    (BLOCK, "W-n-0", True),             # R10's block funds no other cell
    (BLOCK, "W-0", True),
    (BLOCK, "single-turn", True),
    ("4-haiku", "W-0", False),          # other blocks and cells as before
    ("5-haiku-notes", "W-n-0", False),
    ("6-haiku-provenance ", "W-0", True),   # padding: the paid guard strips the name
    (" 6-haiku-provenance", "W-n-0", True),
    ("6-haiku-provenance\t", "F-0", True),
    ("6-haiku-provenance\xa0", "W-0", True),
    (" 6-haiku-provenance ", "W-np-0", False),
])
def test_the_block_rule(block, cell, refused):
    why = registered.provenance_block_refusal(block, cell)
    assert (why is not None) == refused, why
    if refused:
        assert registered.R10_REF in why


def _approval_refusal(experiment: str, *experiments: str) -> str | None:
    """The transport's block check for a run in `experiment` under a block that lists
    `experiments` (the general guard has already required `experiment` among them)."""
    fake_self = SimpleNamespace(approval=SimpleNamespace(
        approved_block="b", experiment=experiment, experiments=experiments))
    return AnthropicMessagesTransport._approval_refusal(fake_self)


def test_the_transport_admits_r10s_runs_under_its_block():
    assert _approval_refusal(PROV, PILOT, PROV) is None
    assert _approval_refusal(PILOT, PILOT, PROV) is None


def test_the_transport_judges_r8s_and_r9s_runs_as_before():
    for experiment in (PILOT, VALIDITY, MAIN):
        assert _approval_refusal(experiment, PILOT, VALIDITY, MAIN) is None
    assert _approval_refusal(NOTES, NOTES) is None
    # a block that lists R10's experiment beside a validity one funds no validity run
    why = _approval_refusal(VALIDITY, VALIDITY, PROV)
    assert why is not None and "§17.10" in why


FAKE_MODEL = HAIKU + "-fake-2026-10-01"
"""The model string the fake model returns (harnesses/fake.py); the real pilot check wants
exactly claude-haiku-5-5, so the tests that run it read the fake's string instead."""


@pytest.fixture
def prov_paid_env(tmp_path, monkeypatch):
    """A repo whose frozen PREREG and decisions hold block 6-haiku-provenance (the pilot and
    R10's experiment) beside block 4-haiku (R8's three) and 5-haiku-notes (R9's); the CLI's
    own guarded transport builds the real Anthropic transport with a fake-backed client; a
    dummy key's variable; a lock of its own."""
    guarded_repo(tmp_path, prereg=FROZEN_PREREG, decisions=decisions_text(
        "4-haiku", experiments=(PILOT, VALIDITY, MAIN))
        + approval_line("5-haiku-notes", (NOTES,)) + "\n"
        + approval_line(BLOCK, (PILOT, PROV)) + "\n")
    costs_csv = tmp_path / "costs.csv"
    costs_csv.write_text(",".join(costs.COLUMNS) + "\n", encoding="utf-8")
    monkeypatch.setenv(ALLOW_ENV, "1")
    monkeypatch.setenv(anthropic_transport.KEY_ENV, "dummy-not-a-key")
    for name in anthropic_transport.REFUSED_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(cli, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(cli, "RAW", tmp_path / "raw")
    (tmp_path / "lock").mkdir()
    monkeypatch.setattr(cli, "LOCK_PATH", tmp_path / "lock" / paidlock.lock_name(cli.STREAM))
    fakes = []

    def transport(**kw):
        fake = FakeModel(ids="payload")
        fakes.append(fake)
        return AnthropicMessagesTransport(
            **kw, costs_path=costs_csv, repo=tmp_path,
            client_factory=lambda timeout: _FakeBackedClient(fake))
    monkeypatch.setattr(cli, "AnthropicMessagesTransport", transport)

    def not_openai(**kw):
        raise AssertionError("a claude-* model gets the Anthropic transport")
    monkeypatch.setattr(cli, "OpenAIResponsesTransport", not_openai)
    from analysis import haiku_provenance_pilot as hpp
    monkeypatch.setattr(hpp, "MODEL_RETURNED", [FAKE_MODEL])
    return tmp_path, costs_csv, fakes


def test_an_end_to_end_r10_pilot_is_blinded(prov_paid_env, capsys):
    """W-np-0 on pilot templates 0-1 x the 4 far task cells (8 episodes) under block 6: the
    provenance sentence in every request's system prompt, the disclosure sentence in none,
    and the episodes kept under results/raw/ (PREREG §11)."""
    tmp, costs_csv, fakes = prov_paid_env
    assert cli.main(["run", "--cell", "W-np-0", "--model", HAIKU, "--split", "pilot", "--n", "2",
                     "--task-cell", *FAR, "--experiment", PILOT, "--approved-block", BLOCK,
                     "--planned-usd", "1", "--run-id", "pp"]) == 0
    capsys.readouterr()
    (row,) = costs.read_rows(costs_csv)
    (fake,) = fakes
    assert (row["run_id"], row["experiment"], row["cell_or_config"]) == ("pp", PILOT, "W-np-0")
    assert row["notes"].startswith(f"approved_block={BLOCK};")
    systems = [p["system"] for p in fake.calls]
    assert systems and all(s.endswith(PROVENANCE_SENTENCE) for s in systems)
    assert not any(DISCLOSURE_SENTENCE in s for s in systems)
    folder = tmp / "results" / PILOT / "pp"
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["exit_reason"] == "COMPLETED" and meta["n_episodes_run"] == 8
    assert not (folder / "episodes.jsonl").exists()
    assert (tmp / "raw" / PILOT / "pp" / "episodes.jsonl").is_file()
    assert not (tmp / "lock" / paidlock.lock_name(cli.STREAM)).exists()


def _pilots_and_check(tmp, costs_csv, capsys) -> None:
    """Both R10 pilots under block 6, then the real pilot check, which writes its GO."""
    from analysis import haiku_provenance_pilot as hpp
    assert cli.main(_pilot("W-np-0", "p1")) == 0 and cli.main(_pilot("W-npd-0", "p2")) == 0
    assert hpp.main(["--results-root", str(tmp), "--raw-root", str(tmp / "raw"),
                     "--costs", str(costs_csv), "--run", "p1", "--run", "p2"]) == 0
    capsys.readouterr()


def _main(cell: str, run_id: str) -> list[str]:
    return ["run", "--cell", cell, "--model", HAIKU, "--split", "main", "--n", "1",
            "--task-cell", *FAR, "--experiment", PROV, "--approved-block", BLOCK,
            "--planned-usd", "1", "--run-id", run_id, "--parallel", "4"]


def test_a_main_run_refuses_before_the_pilots(prov_paid_env, capsys):
    _, costs_csv, fakes = prov_paid_env
    assert cli.main(_main("W-npd-0", "pm")) == 2
    err = capsys.readouterr().err
    assert "refused:" in err and "no check under" in err, err
    assert costs.read_rows(costs_csv) == [] and all(not f.calls for f in fakes)


def test_an_end_to_end_r10_main_run(prov_paid_env, capsys):
    """After both pilots and their GO check: W-npd-0 on main template 0 x the 4 far task cells
    under block 6, with both sentences in every request's system prompt."""
    tmp, costs_csv, fakes = prov_paid_env
    _pilots_and_check(tmp, costs_csv, capsys)
    assert cli.main(_main("W-npd-0", "pm")) == 0
    capsys.readouterr()
    row = next(r for r in costs.read_rows(costs_csv) if r["run_id"] == "pm")
    fake = fakes[-1]
    assert (row["run_id"], row["experiment"], row["cell_or_config"]) == ("pm", PROV, "W-npd-0")
    systems = [p["system"] for p in fake.calls]
    assert systems and all(
        s.endswith(PROVENANCE_SENTENCE + " " + DISCLOSURE_SENTENCE) for s in systems)
    meta = json.loads((tmp / "results" / PROV / "pm" / "meta.json").read_text(encoding="utf-8"))
    assert meta["exit_reason"] == "COMPLETED" and meta["n_episodes_run"] == 4
    recs = [json.loads(x) for x in (tmp / "results" / PROV / "pm" / "episodes.jsonl")
            .read_text(encoding="utf-8").splitlines() if x.strip()]
    assert sorted(r["task_cell"] for r in recs) == sorted(FAR)


@pytest.mark.parametrize("argv, block, why", [
    # R8's block, an R10 pilot: the general guard and the transport admit it, the cell does not
    (["--cell", "W-np-0", "--split", "pilot", "--n", "2", "--task-cell", *FAR,
      "--experiment", PILOT], "4-haiku", "runs under block 6-haiku-provenance only"),
    # R10's block, an R8 pilot
    (["--cell", "W-0", "--split", "pilot", "--n", "1", "--task-cell", *FAR,
      "--experiment", PILOT], BLOCK, "funds W-np-0, W-npd-0 only"),
    # R9's block, an R10 main run
    (["--cell", "W-np-0", "--split", "main", "--n", "1", "--task-cell", *FAR,
      "--experiment", PROV], "5-haiku-notes", "runs under block 6-haiku-provenance only"),
])
def test_no_other_block_funds_r10_and_r10s_funds_nothing_else(prov_paid_env, capsys, argv,
                                                              block, why):
    tmp, costs_csv, fakes = prov_paid_env
    if PROV in argv:
        write_pilot_go(tmp / "results")  # so an R10 main run reaches the block rule
    assert cli.main(["run", "--model", HAIKU, *argv, "--approved-block", block,
                     "--planned-usd", "1", "--run-id", "x"]) == 2
    err = capsys.readouterr().err
    assert "refused:" in err and why in err and "§17.10" in err, err
    assert costs.read_rows(costs_csv) == [] and all(not f.calls for f in fakes)


def test_r10s_block_funds_no_r9_run(prov_paid_env, capsys):
    """The general guard: block 6 does not list R9's experiment."""
    _, costs_csv, fakes = prov_paid_env
    assert cli.main(["run", "--cell", "W-n-0", "--model", HAIKU, "--split", "main", "--n", "1",
                     "--experiment", NOTES, "--approved-block", BLOCK, "--planned-usd", "1",
                     "--run-id", "x"]) == 2
    err = capsys.readouterr().err
    assert "refused:" in err, err
    assert costs.read_rows(costs_csv) == [] and all(not f.calls for f in fakes)


# --- the check between the pilots and the main runs (analysis.haiku_provenance_pilot) -----------

def _pilot(cell: str, run_id: str) -> list[str]:
    return ["run", "--cell", cell, "--model", HAIKU, "--split", "pilot", "--n", "2",
            "--task-cell", *FAR, "--experiment", PILOT, "--approved-block", BLOCK,
            "--planned-usd", "1", "--run-id", run_id]


def test_the_pilot_check_passes_both_pilots_and_reports_no_outcome(prov_paid_env, capsys):
    from analysis import haiku_provenance_pilot as hpp
    tmp, costs_csv, _ = prov_paid_env
    assert cli.main(_pilot("W-np-0", "p1")) == 0 and cli.main(_pilot("W-npd-0", "p2")) == 0
    capsys.readouterr()
    c = hpp.check(tmp / "results", tmp / "raw", costs_csv, ["p1", "p2"])
    assert c["go"] and c["both_cells_piloted"], hpp.summary(c)
    for r in c["runs"]:
        assert r["episodes"] == 8 and r["requests"] > 0
        assert r["requests_without_the_notes_text"] == 0 and r["problems"] == []
        assert r["cost_per_episode_usd"] <= hpp.COST_LIMIT
    text = json.dumps(c)
    assert "need_correct" not in text and "success" not in text  # blinded (PREREG §11)
    # one pilot alone is not enough
    assert not hpp.check(tmp / "results", tmp / "raw", costs_csv, ["p1"])["go"]


def test_the_pilot_check_stops_on_a_wrong_system_prompt_or_cost(prov_paid_env, capsys,
                                                                  monkeypatch):
    from analysis import haiku_provenance_pilot as hpp
    tmp, costs_csv, _ = prov_paid_env
    assert cli.main(_pilot("W-np-0", "p1")) == 0 and cli.main(_pilot("W-npd-0", "p2")) == 0
    capsys.readouterr()
    monkeypatch.setattr(hpp, "COST_LIMIT", 0.0)
    c = hpp.check(tmp / "results", tmp / "raw", costs_csv, ["p1", "p2"])
    assert not c["go"]
    assert all(not r["conditions"]["cost_per_episode_within_limit"] for r in c["runs"])
    monkeypatch.setattr(hpp, "COST_LIMIT", 1.0)
    # the W-np-0 run read as if it were W-npd-0: its system prompts lack the disclosure sentence
    meta_path = tmp / "results" / PILOT / "p1" / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta_path.write_text(json.dumps({**meta, "cell_or_config": "W-npd-0"}), encoding="utf-8")
    r = hpp.check_run(tmp / "results", tmp / "raw", costs_csv, "p1")
    assert not r["passed"] and r["requests_without_the_notes_text"] == r["requests"] > 0


@pytest.mark.parametrize("block", ["6-haiku-provenance ", " 6-haiku-provenance",
                                   "6-haiku-provenance\t", "4-haiku "])
@pytest.mark.parametrize("cell", ["W-0", "W-np-0"])
def test_a_padded_block_name_refuses_before_the_lock(prov_paid_env, capsys, block, cell):
    _, costs_csv, fakes = prov_paid_env
    assert cli.main(["run", "--cell", cell, "--model", HAIKU, "--split", "pilot", "--n", "2",
                     "--task-cell", *FAR, "--experiment", PILOT, "--approved-block", block,
                     "--planned-usd", "1", "--run-id", "x"]) == 2
    err = capsys.readouterr().err
    assert "is not a block name" in err, err
    assert costs.read_rows(costs_csv) == [] and all(not f.calls for f in fakes)


def test_the_section_2_8_replay_reads_r10s_transcripts(prov_paid_env, capsys):
    """§2.8's replay (analysis.persistgym_h1h3.accounting_check) on real R10 transcripts, made
    with the fake model: no bug, need steps checked, so the notes text comes off the system
    prompt as the session leaves it out of W. Read with the other cell's notes text, every
    need step is a bug."""
    from dataclasses import replace

    from analysis import persistgym_h1h3 as hh
    tmp, costs_csv, _ = prov_paid_env
    _pilots_and_check(tmp, costs_csv, capsys)
    assert cli.main(_main("W-np-0", "m1")) == 0 and cli.main(_main("W-npd-0", "m2")) == 0
    capsys.readouterr()
    prof = replace(hh.profile(HAIKU), experiment=PROV,
                   cells=(*registered.HAIKU_CELLS, *CELLS))
    runs, _ = hh.discover(tmp / "results", prof=prof)
    assert sorted(r.cell for r in runs) == ["W-np-0", "W-npd-0"]
    check = hh.accounting_check(runs, tmp / "raw", PROV, hh.MESSAGES_API)
    assert check["bugs"] == [] and check["missing_transcripts"] == []
    assert check["checked"] == 8
    swapped = [replace(r, cell={"W-np-0": "W-npd-0", "W-npd-0": "W-np-0"}[r.cell]) for r in runs]
    bad = hh.accounting_check(swapped, tmp / "raw", PROV, hh.MESSAGES_API)
    assert len(bad["bugs"]) == 8
    assert all("do not end with the notes sentence" in b for b in bad["bugs"])


def test_the_pilot_check_stops_on_another_model_string_tier_or_geo(prov_paid_env, capsys,
                                                                    monkeypatch):
    from analysis import haiku_provenance_pilot as hpp
    tmp, costs_csv, _ = prov_paid_env
    assert cli.main(_pilot("W-np-0", "p1")) == 0
    capsys.readouterr()
    assert hpp.check_run(tmp / "results", tmp / "raw", costs_csv, "p1")["passed"]
    monkeypatch.setattr(hpp, "MODEL_RETURNED", [HAIKU])  # the real check: the fake's string fails
    r = hpp.check_run(tmp / "results", tmp / "raw", costs_csv, "p1")
    assert not r["passed"] and not r["conditions"]["model_string"]
    monkeypatch.setattr(hpp, "MODEL_RETURNED", [FAKE_MODEL])
    rows = costs.read_rows(costs_csv)
    for change in ({"service_tier_served": "priority"},
                   {"notes": rows[0]["notes"].replace("inference_geos=global:",
                                                      "inference_geos=us:1;global:")}):
        bad = costs_csv.with_name("bad.csv")
        with open(bad, "w", encoding="utf-8", newline="") as fh:
            import csv
            w = csv.DictWriter(fh, fieldnames=list(costs.COLUMNS))
            w.writeheader()
            w.writerow({**rows[0], **change})
        r = hpp.check_run(tmp / "results", tmp / "raw", bad, "p1")
        assert not r["passed"] and not r["conditions"]["standard_tier_global_geo"], change


def test_served_geos_reads_the_notes_field():
    from analysis import haiku_provenance_pilot as hpp
    assert hpp.served_geos("approved_block=b; inference_geos=global:3;us:1; x=1") == {
        "global": 3, "us": 1}
    assert hpp.served_geos("approved_block=b; inference_geos=global:180") == {"global": 180}
    assert hpp.served_geos("approved_block=b") is None
    assert hpp.registered_episodes()[:2] == ["pilot-000000/derived-nonrec-far/base",
                                             "pilot-000000/derived-rec-far/base"]
    assert len(hpp.registered_episodes()) == 8


def test_the_not_haiku_note_names_the_messages_api_for_claude_models_only(tmp_path,
                                                                         monkeypatch):
    monkeypatch.setattr(registered, "R6_HARD_STOP", False)
    monkeypatch.setattr(registered, "R10_IN_EFFECT", False)
    why = pilot_guard("W-np-0", tmp_path, model="gpt-6-luna")
    assert "gpt-6-luna" in why and "Messages API" not in why
    why = pilot_guard("W-np-0", tmp_path, model="claude-sonnet-5")
    assert "claude-sonnet-5" in why and "Messages API" in why


def test_a_run_of_r10s_cells_never_reuses_a_run_id(prov_paid_env, capsys):
    """The pilot count and the pilot check read one folder per run: a second run under a used
    run id refuses before the lock, and costs nothing."""
    _, costs_csv, fakes = prov_paid_env
    assert cli.main(_pilot("W-np-0", "p1")) == 0
    capsys.readouterr()
    rows = len(costs.read_rows(costs_csv))
    calls = sum(len(f.calls) for f in fakes)
    assert cli.main(_pilot("W-np-0", "p1")) == 2
    err = capsys.readouterr().err
    assert "--run-id p1 is already used" in err and "§17.10" in err, err
    assert len(costs.read_rows(costs_csv)) == rows and sum(len(f.calls) for f in fakes) == calls


@pytest.mark.parametrize("block", ["6-haiku-provenance ", " 6-haiku-provenance"])
def test_single_turn_refuses_a_padded_block_name_before_the_lock(prov_paid_env, capsys, block):
    _, costs_csv, fakes = prov_paid_env
    assert cli.main(["single-turn", "--model", HAIKU, "--split", "pilot", "--n", "1",
                     "--experiment", PILOT, "--approved-block", block, "--planned-usd", "1",
                     "--run-id", "x"]) == 2
    err = capsys.readouterr().err
    assert "is not a block name" in err, err
    assert costs.read_rows(costs_csv) == [] and all(not f.calls for f in fakes)


def write_unfinished_pilot(results_root, run_id, cell, started="2026-11-01T09:00:00+00:00"):
    """A paid pilot that wrote its raw run plan but no meta.json (a costs row it could not
    append, a killed process)."""
    folder = results_root / "raw" / PILOT / run_id
    folder.mkdir(parents=True)
    (folder / "run_plan.json").write_text(json.dumps(
        {"run_id": run_id, "harness_cell": cell, "harness_config": {"model": HAIKU},
         "started_utc": started}), encoding="utf-8")


def test_an_unfinished_pilot_counts_and_holds_the_main_runs(tmp_path):
    write_pilot_go(tmp_path)
    assert main_guard("W-np-0", tmp_path) is None
    write_unfinished_pilot(tmp_path, "crashed-np", "W-np-0")
    why = main_guard("W-np-0", tmp_path)
    assert why is not None and "unfinished" in why and "crashed-np" in why
    # it counts toward the 2 pilots of its cell, and another cell's count is its own
    pilots, _ = registered._provenance_pilots(tmp_path, "W-np-0")
    assert [r["run_id"] for r in pilots] == ["pilot-W-np-0", "crashed-np"]
    assert "2 pilot runs" in pilot_guard("W-np-0", tmp_path)
    # folders with neither file (reports, logs) are not runs
    (tmp_path / PILOT / "pooled-20261002T084145Z").mkdir()
    (tmp_path / "raw" / PILOT / "check_logs").mkdir()
    assert [r["run_id"] for r in registered._provenance_pilots(tmp_path, "W-npd-0")[0]] == [
        "pilot-W-npd-0"]


def test_any_check_with_a_pass_blocks_a_further_pilot_of_that_cell(tmp_path):
    """A later check that leaves a cell out (one --run forgotten) does not hide its pass."""
    write_pilot_meta(tmp_path, "np1", "W-np-0", started="2026-11-01T01:00:00")
    write_pilot_meta(tmp_path, "npd1", "W-npd-0", started="2026-11-01T01:10:00")
    write_pilot_go(tmp_path, go=False, stamp="20261101T020000Z", runs=[
        {"run_id": "np1", "cell": "W-np-0", "passed": True},
        {"run_id": "npd1", "cell": "W-npd-0", "passed": False}])
    write_pilot_meta(tmp_path, "npd2", "W-npd-0", started="2026-11-01T03:00:00")
    write_pilot_go(tmp_path, go=False, stamp="20261101T040000Z", runs=[
        {"run_id": "npd2", "cell": "W-npd-0", "passed": True}])
    why = pilot_guard("W-np-0", tmp_path)
    assert why is not None and "np1 passed R10's pilot check 20261101T020000Z" in why
    write_pilot_go(tmp_path, stamp="20261101T050000Z", runs=[
        {"run_id": "np1", "cell": "W-np-0", "passed": True},
        {"run_id": "npd2", "cell": "W-npd-0", "passed": True}])
    assert main_guard("W-npd-0", tmp_path) is None


def test_no_pilot_reuses_a_run_id_of_another_pilot(prov_paid_env, capsys):
    """An R8 pilot under R8's block may not take an R10 pilot's run id: it would replace that
    pilot's meta.json and drop it from the count."""
    tmp, costs_csv, _ = prov_paid_env
    assert cli.main(_pilot("W-np-0", "p1")) == 0
    capsys.readouterr()
    rows = len(costs.read_rows(costs_csv))
    assert cli.main(["run", "--cell", "W-0", "--model", HAIKU, "--split", "pilot", "--n", "1",
                     "--task-cell", *FAR, "--experiment", PILOT, "--approved-block", "4-haiku",
                     "--planned-usd", "1", "--run-id", "p1"]) == 2
    err = capsys.readouterr().err
    assert "--run-id p1 is already used" in err, err
    assert len(costs.read_rows(costs_csv)) == rows
    assert json.loads((tmp / "results" / PILOT / "p1" / "meta.json").read_text(
        encoding="utf-8"))["cell_or_config"] == "W-np-0"


@pytest.mark.parametrize("run_id", ["np+1", "np~1", "np1."])
def test_an_r10_run_id_must_be_a_plain_name(prov_paid_env, capsys, run_id):
    _, costs_csv, fakes = prov_paid_env
    code = cli.main(_pilot("W-np-0", run_id))
    err = capsys.readouterr().err
    assert code == 2 and "refused:" in err, err
    assert costs.read_rows(costs_csv) == [] and all(not f.calls for f in fakes)


def test_the_pilot_check_never_writes_a_go_the_gate_rejects(prov_paid_env, capsys):
    """Given a cell's older pilot while a newer one exists, the check fails that run, as the
    gate would."""
    from analysis import haiku_provenance_pilot as hpp
    tmp, costs_csv, _ = prov_paid_env
    assert cli.main(_pilot("W-np-0", "p1")) == 0 and cli.main(_pilot("W-npd-0", "p2")) == 0
    assert cli.main(_pilot("W-np-0", "p3")) == 0
    capsys.readouterr()
    c = hpp.check(tmp / "results", tmp / "raw", costs_csv, ["p1", "p2"])
    assert not c["go"]
    (r1,) = [r for r in c["runs"] if r["run_id"] == "p1"]
    assert not r1["passed"] and any("newest pilot is p3" in x for x in r1["problems"])
    assert hpp.check(tmp / "results", tmp / "raw", costs_csv, ["p3", "p2"])["go"]
