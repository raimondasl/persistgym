"""R13's guard (harnesses/registered.py `_r13_refusal`, `r13_block_refusal`; PREREG §17.13,
amendment R13): fail closed. R13 is prepared, not run.

* The repository: `R13_IN_EFFECT` is True, R13's two experiments are in phase 1a (its cap still
  $620: PLAN A15 raises it when the researcher says go) and the PersistGym stream, and
  results/decisions.md holds no approval line for block 9-r13, so the paid guard refuses every
  R13 run until the researcher merges one.
* The rules: each experiment runs exactly its spec (claude-haiku-5-5, its cells, the full matrix
  on its task cells, main templates within its range, repeat 0, base episodes, R8's effort,
  config and request settings), after `HAIKU_G1_PASSED`. R13's pilots are exactly Haiku's
  Σ-n-0 on the 8 task cells and W-nk-0 on the 2 not-recoverable far ones, on pilot templates
  0-1, at most 8 episodes. Everything else refuses, naming §17.13.
* Routing: R13 judges its runs first, so W-n-0 in its pinned experiment is held to R13's rules
  alone (R9's to R12's kill switches do not reach it). luna's Σ-n-0 is not R13's: its pilot
  and main runs are judged as before. Haiku's Σ-n-0 and W-nk-0 run nowhere else (R8's
  experiments, R9's to R12's), and W-nk-0 goes to `haiku_refusal` whatever the model.
* The kill switches: with `R13_IN_EFFECT` False every R13 run refuses and R12's, R11's and
  luna's still pass. With `R8_IN_EFFECT` False R13's refuse too.
* The block rule: R13's runs need block 9-r13, which funds nothing else. R10's and R12's
  block rules leave R13's runs to it, and `harnesses run` and `single-turn` check it before
  the lock.
  The Anthropic transport admits R13's Haiku runs under a block that lists an R13 experiment.
  Haiku's new pilots are left out of the pooled report, as every Haiku pilot is.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from common import approval, costs, paidlock
from common.tests.gitrepo import FROZEN_PREREG, approval_line, decisions_text, guarded_repo
from harnesses import blinding, cli, registered
from harnesses.anthropic_transport import AnthropicMessagesTransport
from harnesses.paid_transport import PaidCallsNotAllowed
from harnesses.tests.test_haiku_guard import ALL8, DEFAULT, HAIKU, REQUEST, guard

LUNA, SOL, SONNET = "gpt-6-luna", "gpt-6.1-sol", "claude-sonnet-5-5"
LUNA_REQUEST = {"mode": "standard", "service_tier": "flex", "W": None}
SIGMA_X = "persistgym_haiku_r13_sigma"
PINNED_X = "persistgym_haiku_r13_pinned"
PILOT = "persistgym_pilot"
TWO = ("observed-nonrec-far", "derived-nonrec-far")
BLOCK = "9-r13"
REF = "PREREG.md §17.13 (amendment R13)"
R12_NOTES, R12_SONNET, R12_BLOCKWIN = ("persistgym_haiku_r12_notes", "persistgym_sonnet_r12",
                                       "persistgym_haiku_r12_block")


# --- the repository ------------------------------------------------------------------------------

def test_the_repository_has_r13_in_effect():
    assert registered.R13_IN_EFFECT is True and registered.R8_IN_EFFECT is True
    assert registered.R13_REF == REF and registered.R13_BLOCK == BLOCK
    assert registered.R13_EXPERIMENTS == (SIGMA_X, PINNED_X)
    assert registered.R13_NEW_CELLS == ("Σ-n-0", "W-nk-0")
    assert registered.R13_PILOTS == {(HAIKU, "Σ-n-0"): ALL8, (HAIKU, "W-nk-0"): TWO}
    assert registered.R13_PILOT_TEMPLATES == (0, 2) and registered.R13_PILOT_MAX_EPISODES == 8
    assert registered.R13_SIGMA_RUN_TEMPLATES == 50 and registered.R13_ROUND_TEMPLATES == 25
    assert [registered.r13_round_arms(k) for k in range(4)] == [
        ("W-nk-0", "W-n-0"), ("W-n-0", "W-nk-0"), ("W-nk-0", "W-n-0"), ("W-n-0", "W-nk-0")]
    # A15 raises phase 1a's cap when the researcher says go; until then it stays at A14's
    assert costs.PHASE_CAPS["1a"] == 620.0
    for e in registered.R13_EXPERIMENTS:
        assert costs.EXPERIMENT_PHASE[e] == "1a"
        assert paidlock.EXPERIMENT_STREAM[e] == paidlock.PERSISTGYM
    specs = registered.R13_SPECS
    assert specs[SIGMA_X] == {"model": HAIKU, "cells": ("Σ-n-0",), "task_cells": ALL8,
                              "templates": (0, 200), "g1": True}
    assert specs[PINNED_X] == {"model": HAIKU, "cells": ("W-nk-0", "W-n-0"),
                               "task_cells": TWO, "templates": (200, 300), "g1": True}


def test_the_repository_approves_no_r13_spending():
    """Prepared, not run: no approval line for block 9-r13 counts in results/decisions.md (R13's
    entry describes the line without writing it out). The researcher's approval pull request
    adds one, and updates this test with it."""
    text = (costs.REPO_ROOT / approval.DECISIONS_MD).read_text(encoding="utf-8")
    assert approval.approvals_in(text, BLOCK) == set()


def test_without_its_approval_line_the_paid_guard_refuses_r13s_runs(tmp_path, monkeypatch):
    """The general paid guard (common/approval.py `find_approval`, step 6 of
    `require_paid_approval`) finds no approval for block 9-r13 while results/decisions.md has
    none, beside other blocks' lines and a proposed line shown as a code block."""
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
    proposed = approval_line(BLOCK, (PILOT, *registered.R13_EXPERIMENTS), "100")
    guarded_repo(tmp_path, prereg=FROZEN_PREREG, decisions=decisions_text(
        "8-r12", experiments=(PILOT, *registered.R12_EXPERIMENTS))
        + "\nProposed, not approved:\n\n    " + proposed + "\n")
    with pytest.raises(PaidCallsNotAllowed, match="no valid approval line for block '9-r13'"):
        approval.find_approval(tmp_path, BLOCK)
    assert approval.find_approval(tmp_path, "8-r12").experiments == (
        PILOT, *registered.R12_EXPERIMENTS)


# --- the rules -----------------------------------------------------------------------------------

PASSES = [
    (SIGMA_X, "Σ-n-0", ALL8, t) for t in ((0, 50), (150, 200), (0, 200))
] + [
    (PINNED_X, cell, TWO, t) for cell in ("W-nk-0", "W-n-0")
    for t in ((200, 225), (275, 300), (200, 300))
]


@pytest.mark.parametrize("experiment, cell, task_cells, templates", PASSES)
def test_r13s_runs_pass(tmp_path, experiment, cell, task_cells, templates):
    assert guard(experiment, cell, tmp_path, task_cells=task_cells, templates=templates) is None


@pytest.mark.parametrize("experiment, kw, wrong", [
    (SIGMA_X, {"templates": (0, 201)}, "main templates 0-200"),
    (SIGMA_X, {"templates": (200, 225)}, "main templates 200-224"),
    (SIGMA_X, {"templates": None}, "main templates (not given)"),
    (SIGMA_X, {"cell": "W-nk-0"}, "cell W-nk-0"),
    (SIGMA_X, {"cell": "W-n-0"}, "cell W-n-0"),
    (SIGMA_X, {"cell": "Σ-n-r"}, "cell Σ-n-r"),
    (SIGMA_X, {"task_cells": TWO}, "task cells"),
    (SIGMA_X, {"task_cells": None}, "task cells (not given)"),
    (SIGMA_X, {"model": HAIKU + "-2026-11-01"}, "model claude-haiku-5-5-2026-11-01"),
    (SIGMA_X, {"model": SONNET}, f"model {SONNET}"),
    (SIGMA_X, {"model": LUNA, "request": LUNA_REQUEST}, f"model {LUNA}"),
    (SIGMA_X, {"effort": "high"}, "--effort high"),
    (SIGMA_X, {"split": "validity"}, "--split validity"),
    (SIGMA_X, {"variant": "restated"}, "--variant restated"),
    (SIGMA_X, {"matrix": "d11"}, "--matrix d11"),
    (SIGMA_X, {"matrix": None}, "run matrix (not given)"),
    (SIGMA_X, {"request": {**REQUEST, "W": 12000}}, "--W 12000"),
    (SIGMA_X, {"request": {**REQUEST, "service_tier": "flex"}}, "--service-tier flex"),
    (SIGMA_X, {"gen": "0" * 64}, "generator config 000000000000"),
    (PINNED_X, {"templates": (199, 225)}, "main templates 199-224"),
    (PINNED_X, {"templates": (0, 200)}, "main templates 0-199"),
    (PINNED_X, {"templates": (290, 301)}, "main templates 290-300"),
    (PINNED_X, {"cell": "Σ-n-0"}, "cell Σ-n-0"),
    (PINNED_X, {"cell": "W-np-0"}, "cell W-np-0"),
    (PINNED_X, {"cell": "W-0"}, "cell W-0"),
    (PINNED_X, {"task_cells": ALL8}, "task cells"),
    (PINNED_X, {"model": HAIKU + "-2026-11-01"}, "model claude-haiku-5-5-2026-11-01"),
    (PINNED_X, {"effort": "low"}, "--effort low"),
    (PINNED_X, {"split": "pilot"}, "--split pilot"),
])
def test_anything_else_refuses(tmp_path, experiment, kw, wrong):
    base = {SIGMA_X: {"cell": "Σ-n-0", "task_cells": ALL8, "templates": (0, 200)},
            PINNED_X: {"cell": "W-nk-0", "task_cells": TWO, "templates": (200, 300)}}[experiment]
    args = {**base, **kw}
    cell = args.pop("cell")
    why = guard(experiment, cell, tmp_path, **args)
    assert why is not None and wrong in why, why
    # R13's rule names §17.13. A model outside the spec may already stop at R6's hard stop,
    # which lets Haiku alone into R13's experiments.
    assert REF in why or registered.R6_REF in why, why


def test_repeat_1_refuses(tmp_path):
    why = registered.check_run_settings(
        PINNED_X, HAIKU, "medium", "W-nk-0", DEFAULT, tmp_path, split="main", variant="base",
        task_cells=TWO, request=REQUEST, templates=(200, 300), matrix="full", repeat_index=1)
    assert why is not None and "--repeat-index 1" in why and REF in why


def test_r13s_runs_need_haikus_g1(tmp_path, monkeypatch):
    monkeypatch.delitem(registered.HAIKU_G1_PASSED, HAIKU)
    for experiment, cell, tc, t in ((SIGMA_X, "Σ-n-0", ALL8, (0, 200)),
                                    (PINNED_X, "W-nk-0", TWO, (200, 300)),
                                    (PINNED_X, "W-n-0", TWO, (200, 300))):
        why = guard(experiment, cell, tmp_path, task_cells=tc, templates=t)
        assert why is not None and "G1" in why and REF in why
    # the pilots need no G1, as every pilot
    assert guard(PILOT, "W-nk-0", tmp_path, task_cells=TWO, templates=(0, 2),
                 split="pilot") is None


# --- the pilots ----------------------------------------------------------------------------------

@pytest.mark.parametrize("cell, task_cells, templates", [
    ("Σ-n-0", ALL8, (0, 1)),
    ("Σ-n-0", ALL8, (1, 2)),
    ("Σ-n-0", ("observed-nonrec-far", "derived-rec-near"), (0, 2)),
    ("W-nk-0", TWO, (0, 2)),
    ("W-nk-0", TWO[:1], (1, 2)),
])
def test_r13s_pilots_pass(tmp_path, cell, task_cells, templates):
    assert registered._is_r13_run(PILOT, HAIKU, cell)
    assert guard(PILOT, cell, tmp_path, task_cells=task_cells, templates=templates,
                 split="pilot") is None


@pytest.mark.parametrize("model, cell, kw, wrong", [
    (HAIKU, "Σ-n-0", {"task_cells": ALL8}, "16 pilot episodes"),
    (HAIKU, "W-nk-0", {"task_cells": ALL8}, "task cells"),
    (HAIKU, "W-nk-0", {"task_cells": ()}, "task cells (none)"),
    (HAIKU, "W-nk-0", {"task_cells": (TWO[0], TWO[0])}, "task cells"),
    (HAIKU, "W-nk-0", {"task_cells": None}, "task cells (not given)"),
    (HAIKU, "W-nk-0", {"templates": (0, 3)}, "pilot templates 0-2"),
    (HAIKU, "W-nk-0", {"templates": None}, "pilot templates (not given)"),
    (HAIKU, "W-nk-0", {"split": "main"}, "--split main"),
    (HAIKU, "W-nk-0", {"effort": "high"}, "--effort high"),
    (HAIKU, "W-nk-0", {"variant": "restated"}, "--variant restated"),
    (HAIKU, "Σ-n-0", {"request": {**REQUEST, "service_tier": "flex"}}, "--service-tier flex"),
    (HAIKU, "Σ-n-0", {"gen": "0" * 64}, "generator config 000000000000"),
    (HAIKU + "-2026-11-01", "W-nk-0", {},
     "pilot of model claude-haiku-5-5-2026-11-01, cell W-nk-0"),
])
def test_other_r13_pilots_refuse(tmp_path, model, cell, kw, wrong):
    args = {"task_cells": TWO, "templates": (0, 2), "split": "pilot", **kw}
    why = guard(PILOT, cell, tmp_path, model=model, **args)
    assert why is not None and wrong in why and REF in why, why


def test_haikus_w_n_0_pilot_is_still_r8s(tmp_path):
    """R13 gives W-n-0 no pilot (it has run on Haiku): a Haiku W-n-0 pilot is R8's, as before."""
    assert not registered._is_r13_run(PILOT, HAIKU, "W-n-0")
    assert guard(PILOT, "W-n-0", tmp_path, task_cells=TWO, templates=(0, 1),
                 split="pilot") is None


def test_haikus_new_pilots_are_never_pooled():
    for cell in registered.R13_NEW_CELLS:
        assert blinding.is_left_out({"model": HAIKU, "harness_cell": cell, "variant": "base"})


# --- luna's Σ-n-0 is not R13's -------------------------------------------------------------------

def test_lunas_sigma_n_0_is_not_r13s(tmp_path, monkeypatch):
    for model in (LUNA, LUNA + "-2026-10-01", SOL, SONNET):
        assert not registered._is_r13_run(PILOT, model, "Σ-n-0")
    assert not registered._is_r13_run(PILOT, SONNET, "W-nk-0")
    assert not registered._is_r13_run("persistgym", LUNA, "Σ-n-0")
    # luna's main sweep cell, judged by luna's rule as before, with R13 on or off
    for on in (True, False):
        monkeypatch.setattr(registered, "R13_IN_EFFECT", on)
        assert guard("persistgym", "Σ-n-0", tmp_path, model=LUNA, request=LUNA_REQUEST) is None
        why = guard("persistgym", "Σ-n-0", tmp_path, model=LUNA, request=REQUEST)
        assert "outside persistgym_pilot" in why and REF not in why
        # its pilot: R6's hard stop refuses it, as before; with the stop off it passes
        why = guard(PILOT, "Σ-n-0", tmp_path, model=LUNA, request=LUNA_REQUEST, split="pilot",
                    templates=(0, 1))
        assert why is not None and why.startswith("R6's hard stop") and REF not in why
    monkeypatch.setattr(registered, "R6_HARD_STOP", False)
    for on in (True, False):
        monkeypatch.setattr(registered, "R13_IN_EFFECT", on)
        assert guard(PILOT, "Σ-n-0", tmp_path, model=LUNA, request=LUNA_REQUEST,
                     split="pilot", templates=(0, 1)) is None
    # its block: any but 9-r13
    assert registered.r13_block_refusal("3-persistgym", "Σ-n-0", PILOT, LUNA) is None
    assert registered.r13_block_refusal("3-persistgym", "Σ-n-0", "persistgym", LUNA) is None
    assert "funds R13's runs only" in registered.r13_block_refusal(BLOCK, "Σ-n-0", PILOT, LUNA)


# --- Haiku's new cells elsewhere, and W-nk-0 on other models --------------------------------------

@pytest.mark.parametrize("cell", ["Σ-n-0", "W-nk-0"])
@pytest.mark.parametrize("experiment, kw", [
    ("persistgym_haiku", {}),
    ("persistgym_validity", {"split": "validity", "variant": "restated", "templates": (0, 20)}),
    ("persistgym_haiku_notes", {}),
    ("persistgym_haiku_provenance", {"task_cells": ("observed-rec-far", "observed-nonrec-far",
                                                    "derived-rec-far", "derived-nonrec-far")}),
    ("persistgym_haiku_control", {"task_cells": TWO}),
    (R12_NOTES, {"task_cells": TWO, "templates": (200, 300)}),
    (R12_SONNET, {"task_cells": TWO, "templates": (200, 225)}),
    (R12_BLOCKWIN, {}),
])
def test_haikus_new_cells_run_nowhere_else(tmp_path, experiment, cell, kw):
    assert not registered._is_r13_run(experiment, HAIKU, cell)
    why = guard(experiment, cell, tmp_path, **kw)
    assert why is not None and f"cell {cell}" in why and REF not in why, why


@pytest.mark.parametrize("r6_on", [True, False])
@pytest.mark.parametrize("model, experiment", [
    (LUNA, "persistgym"), (LUNA, PILOT), (SOL, PILOT), (SONNET, PILOT), (LUNA, PINNED_X),
    (SOL, SIGMA_X),
])
def test_other_models_never_run_w_nk_0_or_in_r13s_experiments(tmp_path, monkeypatch, r6_on,
                                                              model, experiment):
    """W-nk-0 and R13's experiments go to `haiku_refusal` whatever the model, so with R6's
    hard stop off too no other model runs them."""
    monkeypatch.setattr(registered, "R6_HARD_STOP", r6_on)
    cell = "Σ-n-0" if experiment == SIGMA_X else "W-nk-0"
    split = "pilot" if experiment == PILOT else "main"
    templates = (200, 300) if experiment == PINNED_X else (0, 1)
    why = guard(experiment, cell, tmp_path, model=model, split=split, templates=templates,
                task_cells=TWO, effort=registered.registered_effort(model))
    assert why is not None, (model, experiment)
    # with R6's hard stop off, Haiku's rules refuse them (R13's, R12's for a Sonnet pilot, or
    # R8's), never the old pilot rules
    assert r6_on or any(ref in why for ref in (REF, registered.R12_REF, registered.R8_REF)), why


# --- W-n-0 in the pinned experiment is R13's alone -----------------------------------------------

def test_w_n_0_in_the_pinned_experiment_is_judged_by_r13_alone(tmp_path, monkeypatch):
    assert registered._is_r13_run(PINNED_X, HAIKU, "W-n-0")
    assert not registered._is_r12_run(PINNED_X, HAIKU, "W-n-0")
    for switch in ("R9_IN_EFFECT", "R10_IN_EFFECT", "R11_IN_EFFECT", "R12_IN_EFFECT"):
        monkeypatch.setattr(registered, switch, False)
    assert guard(PINNED_X, "W-n-0", tmp_path, task_cells=TWO, templates=(200, 300)) is None
    why = guard(PINNED_X, "W-n-0", tmp_path, task_cells=ALL8, templates=(200, 300))
    assert why is not None and REF in why
    assert not any(ref in why for ref in (registered.R9_REF, registered.R10_REF,
                                          registered.R11_REF, registered.R12_REF)), why
    monkeypatch.setattr(registered, "R13_IN_EFFECT", False)
    why = guard(PINNED_X, "W-n-0", tmp_path, task_cells=TWO, templates=(200, 300))
    assert why is not None and why.startswith(registered.R13_STOP)
    # R11's W-n-0 is R11's, as before
    monkeypatch.setattr(registered, "R11_IN_EFFECT", True)
    assert guard("persistgym_haiku_control", "W-n-0", tmp_path, task_cells=TWO) is None


# --- the kill switches ---------------------------------------------------------------------------

PILOTS = [("Σ-n-0", ALL8, (0, 1)), ("W-nk-0", TWO, (0, 2))]


def test_r13_off_refuses_every_r13_run_and_not_the_others(tmp_path, monkeypatch):
    monkeypatch.setattr(registered, "R13_IN_EFFECT", False)
    for experiment, cell, tc, t in PASSES:
        why = guard(experiment, cell, tmp_path, task_cells=tc, templates=t)
        assert why is not None and why.startswith(registered.R13_STOP)
    for cell, tc, t in PILOTS:
        why = guard(PILOT, cell, tmp_path, task_cells=tc, templates=t, split="pilot")
        assert why is not None and why.startswith(registered.R13_STOP)
    assert guard(R12_BLOCKWIN, "W-b-0", tmp_path) is None
    assert guard(R12_NOTES, "W-nd-0", tmp_path, task_cells=TWO, templates=(200, 300)) is None
    assert guard("persistgym_haiku_control", "W-n-0", tmp_path, task_cells=TWO) is None
    assert guard(PILOT, "W-0", tmp_path, split="pilot", templates=(0, 1)) is None


def test_r12_off_leaves_r13s_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(registered, "R12_IN_EFFECT", False)
    monkeypatch.setattr(registered, "R10_IN_EFFECT", False)
    for experiment, cell, tc, t in PASSES:
        assert guard(experiment, cell, tmp_path, task_cells=tc, templates=t) is None
    for cell, tc, t in PILOTS:
        assert guard(PILOT, cell, tmp_path, task_cells=tc, templates=t, split="pilot") is None


def test_r8_off_refuses_r13s_runs_too(tmp_path, monkeypatch):
    monkeypatch.setattr(registered, "R8_IN_EFFECT", False)
    for experiment, cell, tc, t in PASSES[:1] + PASSES[-1:]:
        why = guard(experiment, cell, tmp_path, task_cells=tc, templates=t)
        assert why is not None and registered.R8_STOP in why
    for cell, tc, t in PILOTS:
        why = guard(PILOT, cell, tmp_path, task_cells=tc, templates=t, split="pilot")
        assert why is not None and registered.R8_STOP in why


# --- the block rule, the CLI and the transport -----------------------------------------------------

@pytest.mark.parametrize("block, experiment, cell, model, ok", [
    (BLOCK, SIGMA_X, "Σ-n-0", HAIKU, True),
    (BLOCK, PINNED_X, "W-nk-0", HAIKU, True),
    (BLOCK, PINNED_X, "W-n-0", HAIKU, True),
    (BLOCK, PILOT, "Σ-n-0", HAIKU, True),
    (BLOCK, PILOT, "W-nk-0", HAIKU, True),
    (f"  {BLOCK} ", SIGMA_X, "Σ-n-0", HAIKU, True),
    ("8-r12", PINNED_X, "W-n-0", HAIKU, False),
    ("8-r12", PILOT, "Σ-n-0", HAIKU, False),
    ("7-haiku-control", PINNED_X, "W-n-0", HAIKU, False),
    ("6-haiku-provenance", SIGMA_X, "Σ-n-0", HAIKU, False),
    ("5-haiku-notes", PINNED_X, "W-n-0", HAIKU, False),
    ("4-haiku", PILOT, "W-nk-0", HAIKU, False),
    ("1-pilots", PILOT, "Σ-n-0", HAIKU, False),
    (None, SIGMA_X, "Σ-n-0", HAIKU, False),
    (BLOCK, PILOT, "Σ-n-0", LUNA, False),  # luna's pilot
    (BLOCK, "persistgym", "Σ-n-0", LUNA, False),  # luna's main sweep
    (BLOCK, PILOT, "W-n-0", HAIKU, False),  # R8's pilot
    (BLOCK, PILOT, "W-np-0", HAIKU, False),  # R10's pilot
    (BLOCK, PILOT, "W-nd-0", HAIKU, False),  # R12's pilot
    (BLOCK, PILOT, "W-nk-0", SONNET, False),  # not a Haiku pilot
    (BLOCK, PILOT, "single-turn", HAIKU, False),
    (BLOCK, "persistgym_haiku", "F-0", HAIKU, False),
    (BLOCK, "persistgym_haiku_notes", "W-n-0", HAIKU, False),
    (BLOCK, "persistgym_haiku_control", "W-n-0", HAIKU, False),
    (BLOCK, R12_NOTES, "W-n-0", HAIKU, False),
    (BLOCK, R12_BLOCKWIN, "W-b-0", HAIKU, False),
])
def test_the_block_rule(block, experiment, cell, model, ok):
    why = registered.r13_block_refusal(block, cell, experiment, model)
    assert (why is None) is ok, why
    mine = registered._is_r13_run(experiment, model, cell)
    if mine and not ok:
        assert why.startswith(f"R13's runs ({REF}) run under block {BLOCK} only")
    if not mine:
        assert why.startswith(f"block {BLOCK} funds R13's runs only ({REF})")
    # R10's and R12's block rules leave R13's runs to R13's, whatever the block
    if mine:
        assert registered.r12_block_refusal(block, cell, experiment, model) is None
        assert registered.provenance_block_refusal(block, cell, experiment=experiment,
                                                   model=model) is None


def test_r12s_block_still_binds_r12s_runs():
    assert registered.r12_block_refusal("8-r12", "W-nd-0", R12_NOTES, HAIKU) is None
    assert "funds R12's runs only" in registered.r12_block_refusal("8-r12", "W-n-0",
                                                                   "persistgym_haiku_notes",
                                                                   HAIKU)
    assert "run under block 8-r12 only" in registered.r12_block_refusal(BLOCK, "W-b-0",
                                                                        R12_BLOCKWIN, HAIKU)


@pytest.fixture
def no_lock_or_transport(monkeypatch, tmp_path):
    """The CLI must refuse before the paid-run lock and before building any transport; its
    results/ is empty (no earlier single-turn pilot counts). PERSISTGYM_ALLOW_PAID stays as
    the environment has it: these refusals come before the paid guard reads it."""
    def no_transport(*a, **k):
        raise AssertionError("must refuse before the lock and any transport")
    monkeypatch.setattr(cli, "_guarded_transport", no_transport)
    monkeypatch.setattr(cli, "_with_paid_lock", no_transport)
    monkeypatch.setattr(cli, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(cli, "RAW", tmp_path / "raw")


@pytest.mark.parametrize("argv, block, wanted", [
    (["run", "--cell", "sigma-n-0", "--split", "main", "--n", "50", "--experiment", SIGMA_X],
     "8-r12", f"R13's runs ({REF}) run under block {BLOCK} only, got --approved-block 8-r12"),
    (["run", "--cell", "W-n-0", "--split", "main", "--start", "200", "--n", "25",
      "--task-cell", *TWO, "--experiment", PINNED_X],
     "7-haiku-control", "run under block 9-r13 only, got --approved-block 7-haiku-control"),
    (["run", "--cell", "W-nk-0", "--split", "pilot", "--n", "2", "--task-cell", *TWO],
     "4-haiku", "run under block 9-r13 only, got --approved-block 4-haiku"),
    (["run", "--cell", "W-0", "--split", "pilot", "--n", "1"],
     BLOCK, f"block {BLOCK} funds R13's runs only"),
    (["run", "--cell", "W-b-0", "--split", "main", "--n", "50", "--experiment", R12_BLOCKWIN],
     BLOCK, "R12's runs (PREREG.md §17.12 (amendment R12)) run under block 8-r12 only"),
    (["single-turn", "--split", "pilot", "--n", "1"], BLOCK, f"block {BLOCK} funds R13's runs"),
])
def test_the_cli_checks_r13s_block_rule_before_the_lock(no_lock_or_transport, capsys, argv,
                                                        block, wanted):
    assert cli.main([*argv[:1], "--model", HAIKU, *argv[1:], "--approved-block", block,
                     "--planned-usd", "1"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("refused:") and wanted in err, err


def test_r13s_runs_take_a_new_run_id(no_lock_or_transport, tmp_path):
    (tmp_path / "results" / SIGMA_X / "used").mkdir(parents=True)
    assert cli._run_id_refusal("used", SIGMA_X, "Σ-n-0") is not None
    assert REF in cli._run_id_refusal("used", SIGMA_X, "Σ-n-0")
    assert cli._run_id_refusal("new", SIGMA_X, "Σ-n-0") is None
    (tmp_path / "raw" / PINNED_X / "used").mkdir(parents=True)
    assert cli._run_id_refusal("used", PINNED_X, "W-n-0") is not None


def _transport(model, experiment, experiments, block=BLOCK):
    return SimpleNamespace(model=model, experiment=experiment, approval=SimpleNamespace(
        approved_block=block, experiment=experiment, experiments=experiments))


R13_LINE = (PILOT, SIGMA_X, PINNED_X)


@pytest.mark.parametrize("model, experiment, experiments, ok", [
    (HAIKU, SIGMA_X, R13_LINE, True),
    (HAIKU, PINNED_X, R13_LINE, True),
    (HAIKU, PILOT, R13_LINE, True),
    (HAIKU, PINNED_X, (PINNED_X,), True),
    (SONNET, PILOT, R13_LINE, False),  # a Sonnet run needs R12's line
    (HAIKU, PILOT, (PILOT, "persistgym_validity"), False),  # as before
    (HAIKU, "persistgym_haiku_control", ("persistgym_haiku_control",), True),  # R11, as before
    (HAIKU, R12_NOTES, (PILOT, R12_NOTES, R12_SONNET, R12_BLOCKWIN), True),  # R12, as before
])
def test_the_transport_admits_r13s_runs_under_its_block(model, experiment, experiments, ok):
    why = AnthropicMessagesTransport._approval_refusal(_transport(model, experiment, experiments))
    assert (why is None) is ok, why


@pytest.mark.parametrize("model, experiment, ok", [
    (HAIKU, SIGMA_X, True), (HAIKU, PINNED_X, True), (HAIKU, PILOT, True),
    (SONNET, SIGMA_X, False), (SONNET, PINNED_X, False), ("claude-opus-5-5", PINNED_X, False),
])
def test_the_transport_sends_haiku_only_in_r13(monkeypatch, model, experiment, ok):
    monkeypatch.setattr("harnesses.anthropic_transport.credential_refusal", lambda: None)
    t = SimpleNamespace(model=model, experiment=experiment)
    if ok:
        AnthropicMessagesTransport._preflight(t)
    else:
        with pytest.raises(PaidCallsNotAllowed, match="Messages transport sends"):
            AnthropicMessagesTransport._preflight(t)
