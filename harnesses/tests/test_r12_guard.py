"""R12's guard (harnesses/registered.py `_r12_refusal`, `r12_block_refusal`; PREREG §17.12,
amendment R12): fail closed.

* The repository: `R12_IN_EFFECT` is True, R12's three experiments are in phase 1a (capped at
  $620 since A14) and the PersistGym stream, claude-sonnet-5-5 is registered at medium.
* The rules: each experiment runs exactly its spec (model, cells, the full matrix on its task
  cells, main templates within its range, repeat 0, base episodes, R8's effort, config and
  request settings), Haiku's after `HAIKU_G1_PASSED`. R12's pilots are exactly its (model,
  cell) pairs on pilot templates 0-1, at most 8 episodes. Everything else refuses, naming §17.12.
* Routing: R12's W-np-0 runs are not judged by R10's rule, R10's W-np-0 pilot still is, and
  Sonnet runs nowhere else.
* The kill switches: with `R12_IN_EFFECT` False every R12 run refuses and R11's still passes;
  with `R8_IN_EFFECT` False R12's refuse too.
* The block rule: R12's runs need block 8-r12, which funds nothing else. The Anthropic
  transport sends Sonnet only in R12's experiment and pilots, and admits R12's runs under a
  block that lists an R12 experiment.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from common import costs, paidlock
from harnesses import registered
from harnesses.anthropic_transport import AnthropicMessagesTransport
from harnesses.paid_transport import PaidCallsNotAllowed
from harnesses.tests.test_haiku_guard import ALL8, DEFAULT, HAIKU, REQUEST, guard

SONNET = "claude-sonnet-5-5"
NOTES = "persistgym_haiku_r12_notes"
SONNET_X = "persistgym_sonnet_r12"
BLOCKWIN = "persistgym_haiku_r12_block"
PILOT = "persistgym_pilot"
TWO = ("observed-nonrec-far", "derived-nonrec-far")
BLOCK = "8-r12"
REF = "PREREG.md §17.12 (amendment R12)"


# --- the repository ------------------------------------------------------------------------------

def test_the_repository_has_r12_in_effect():
    assert registered.R12_IN_EFFECT is True and registered.R8_IN_EFFECT is True
    assert registered.R12_REF == REF and registered.R12_BLOCK == BLOCK
    assert registered.R12_EXPERIMENTS == (NOTES, SONNET_X, BLOCKWIN)
    assert registered.SONNET_MODEL == SONNET
    assert registered.REGISTERED_EFFORT[SONNET] == "medium"
    assert costs.PHASE_CAPS["1a"] == 620.0
    for e in registered.R12_EXPERIMENTS:
        assert costs.EXPERIMENT_PHASE[e] == "1a"
        assert paidlock.EXPERIMENT_STREAM[e] == paidlock.PERSISTGYM
    specs = registered.R12_SPECS
    assert specs[NOTES] == {"model": HAIKU, "cells": ("W-n-0", "W-np-0", "W-nd-0", "W-nx-0"),
                            "task_cells": TWO, "templates": (200, 300), "g1": True}
    assert specs[SONNET_X] == {"model": SONNET, "cells": ("W-n-0", "W-np-0", "F-0"),
                               "task_cells": TWO, "templates": (200, 225), "g1": False}
    assert specs[BLOCKWIN] == {"model": HAIKU, "cells": ("W-b-0",), "task_cells": ALL8,
                               "templates": (0, 200), "g1": True}


# --- the rules -----------------------------------------------------------------------------------

PASSES = [
    (NOTES, HAIKU, cell, TWO, t) for cell in ("W-n-0", "W-np-0", "W-nd-0", "W-nx-0")
    for t in ((200, 225), (275, 300), (200, 300))
] + [
    (SONNET_X, SONNET, cell, TWO, (200, 225)) for cell in ("W-n-0", "W-np-0", "F-0")
] + [
    (BLOCKWIN, HAIKU, "W-b-0", ALL8, t) for t in ((0, 25), (0, 200), (175, 200))
]


@pytest.mark.parametrize("experiment, model, cell, task_cells, templates", PASSES)
def test_r12s_runs_pass(tmp_path, experiment, model, cell, task_cells, templates):
    assert guard(experiment, cell, tmp_path, model=model, task_cells=task_cells,
                 templates=templates) is None


@pytest.mark.parametrize("experiment, kw, wrong", [
    (NOTES, {"templates": (199, 225)}, "main templates 199-224"),
    (NOTES, {"templates": (0, 200)}, "main templates 0-199"),
    (NOTES, {"templates": (290, 301)}, "main templates 290-300"),
    (NOTES, {"cell": "W-0"}, "cell W-0"),
    (NOTES, {"cell": "W-b-0"}, "cell W-b-0"),
    (NOTES, {"task_cells": ALL8}, "task cells"),
    (NOTES, {"model": SONNET}, f"model {SONNET}"),
    (NOTES, {"model": HAIKU + "-2026-11-01"}, "model claude-haiku-5-5-2026-11-01"),
    (NOTES, {"effort": "high"}, "--effort high"),
    (NOTES, {"split": "validity"}, "--split validity"),
    (NOTES, {"variant": "restated"}, "--variant restated"),
    (NOTES, {"matrix": "d11"}, "--matrix d11"),
    (NOTES, {"matrix": None}, "run matrix (not given)"),
    (NOTES, {"request": {**REQUEST, "W": 12000}}, "--W 12000"),
    (NOTES, {"gen": "0" * 64}, "generator config 000000000000"),
    (SONNET_X, {"templates": (200, 226)}, "main templates 200-225"),
    (SONNET_X, {"cell": "W-nd-0"}, "cell W-nd-0"),
    (SONNET_X, {"model": HAIKU}, f"model {HAIKU}"),
    (SONNET_X, {"effort": "high"}, "--effort high"),
    (BLOCKWIN, {"templates": (200, 210)}, "main templates 200-209"),
    (BLOCKWIN, {"task_cells": TWO}, "task cells"),
    (BLOCKWIN, {"cell": "W-0"}, "cell W-0"),
])
def test_anything_else_refuses(tmp_path, experiment, kw, wrong):
    base = {NOTES: {"model": HAIKU, "cell": "W-n-0", "task_cells": TWO, "templates": (200, 300)},
            SONNET_X: {"model": SONNET, "cell": "W-n-0", "task_cells": TWO,
                       "templates": (200, 225)},
            BLOCKWIN: {"model": HAIKU, "cell": "W-b-0", "task_cells": ALL8,
                       "templates": (0, 200)}}[experiment]
    args = {**base, **kw}
    cell = args.pop("cell")
    why = guard(experiment, cell, tmp_path, **args)
    assert why is not None and wrong in why, why
    # R12's rule names §17.12. A model outside an experiment's spec may already stop at R6's
    # hard stop, which lets each model into its own R12 experiments only.
    assert REF in why or registered.R6_REF in why, why


def test_repeat_1_refuses(tmp_path):
    why = registered.check_run_settings(
        NOTES, HAIKU, "medium", "W-np-0", DEFAULT, tmp_path, split="main", variant="base",
        task_cells=TWO, request=REQUEST, templates=(200, 300), matrix="full", repeat_index=1)
    assert why is not None and "--repeat-index 1" in why and REF in why


def test_haikus_runs_need_its_g1_and_sonnets_do_not(tmp_path, monkeypatch):
    monkeypatch.delitem(registered.HAIKU_G1_PASSED, HAIKU)
    for experiment, cell, tc, t in ((NOTES, "W-nd-0", TWO, (200, 300)),
                                    (BLOCKWIN, "W-b-0", ALL8, (0, 200))):
        why = guard(experiment, cell, tmp_path, task_cells=tc, templates=t)
        assert why is not None and "G1" in why and REF in why
    assert guard(SONNET_X, "F-0", tmp_path, model=SONNET, task_cells=TWO,
                 templates=(200, 225)) is None


# --- the pilots ----------------------------------------------------------------------------------

@pytest.mark.parametrize("model, cell, task_cells, templates", [
    (HAIKU, "W-nd-0", TWO, (0, 2)),
    (HAIKU, "W-nx-0", TWO, (0, 1)),
    (HAIKU, "W-b-0", ALL8, (0, 1)),
    (HAIKU, "W-b-0", ("observed-nonrec-near", "derived-nonrec-far"), (0, 2)),
    (SONNET, "W-n-0", TWO, (0, 2)),
    (SONNET, "W-np-0", TWO, (1, 2)),
    (SONNET, "F-0", TWO, (0, 2)),
])
def test_r12s_pilots_pass(tmp_path, model, cell, task_cells, templates):
    assert guard(PILOT, cell, tmp_path, model=model, task_cells=task_cells,
                 templates=templates, split="pilot") is None


@pytest.mark.parametrize("model, cell, kw, wrong", [
    (HAIKU, "W-b-0", {"task_cells": ALL8, "templates": (0, 2)}, "16 pilot episodes"),
    (HAIKU, "W-nd-0", {"task_cells": ALL8}, "task cells"),
    (HAIKU, "W-nd-0", {"templates": (0, 3)}, "pilot templates 0-2"),
    (HAIKU, "W-nd-0", {"split": "main"}, "--split main"),
    (SONNET, "W-0", {}, f"pilot of model {SONNET}, cell W-0"),
    (SONNET, "W-nd-0", {}, f"pilot of model {SONNET}, cell W-nd-0"),
    (SONNET, "F-0", {"effort": "high"}, "--effort high"),
])
def test_other_pilots_refuse(tmp_path, model, cell, kw, wrong):
    args = {"task_cells": TWO, "templates": (0, 2), "split": "pilot", **kw}
    why = guard(PILOT, cell, tmp_path, model=model, **args)
    assert why is not None and wrong in why and REF in why, why


def test_r10s_w_np_0_pilot_is_still_r10s(tmp_path):
    """A Haiku W-np-0 pilot is not R12's: R10's rule judges it, as before."""
    why = guard(PILOT, "W-np-0", tmp_path, task_cells=TWO, templates=(0, 2), split="pilot")
    assert why is None or registered.R10_REF in why
    assert not registered._is_r12_run(PILOT, HAIKU, "W-np-0")


# --- Sonnet elsewhere, and the kill switches -----------------------------------------------------

@pytest.mark.parametrize("experiment, cell", [
    ("persistgym_haiku", "F-0"), ("persistgym_haiku_control", "W-n-0"),
    ("persistgym_haiku_provenance", "W-np-0"), ("persistgym_haiku_notes", "W-n-0"),
    (NOTES, "W-n-0"), (BLOCKWIN, "W-b-0"), ("persistgym", "F-0"),
    ("persistgym_validity", "F-0"),
])
def test_sonnet_runs_nowhere_else(tmp_path, experiment, cell):
    tc = ALL8 if experiment in ("persistgym_haiku", BLOCKWIN, "persistgym") else TWO
    assert guard(experiment, cell, tmp_path, model=SONNET, task_cells=tc,
                 templates=(200, 225)) is not None


def test_r12_off_refuses_every_r12_run_and_not_r11s(tmp_path, monkeypatch):
    monkeypatch.setattr(registered, "R12_IN_EFFECT", False)
    for experiment, model, cell, tc, t in PASSES[:1] + PASSES[12:13] + PASSES[-1:]:
        why = guard(experiment, cell, tmp_path, model=model, task_cells=tc, templates=t)
        assert why is not None and why.startswith(registered.R12_STOP)
    why = guard(PILOT, "W-b-0", tmp_path, task_cells=ALL8, templates=(0, 1), split="pilot")
    assert why is not None and why.startswith(registered.R12_STOP)
    assert guard("persistgym_haiku_control", "W-n-0", tmp_path, task_cells=TWO) is None


def test_r8_off_refuses_r12s_runs_too(tmp_path, monkeypatch):
    monkeypatch.setattr(registered, "R8_IN_EFFECT", False)
    for experiment, model, cell, tc, t in PASSES[:1] + PASSES[12:13] + PASSES[-1:]:
        why = guard(experiment, cell, tmp_path, model=model, task_cells=tc, templates=t)
        assert why is not None and registered.R8_STOP in why


# --- the block rule and the transport --------------------------------------------------------------

@pytest.mark.parametrize("block, experiment, cell, model, ok", [
    (BLOCK, NOTES, "W-np-0", HAIKU, True),
    (BLOCK, SONNET_X, "W-np-0", SONNET, True),
    (BLOCK, BLOCKWIN, "W-b-0", HAIKU, True),
    (BLOCK, PILOT, "W-nd-0", HAIKU, True),
    (BLOCK, PILOT, "F-0", SONNET, True),
    (f"  {BLOCK} ", NOTES, "W-n-0", HAIKU, True),
    ("6-haiku-provenance", NOTES, "W-np-0", HAIKU, False),
    ("7-haiku-control", SONNET_X, "W-n-0", SONNET, False),
    ("4-haiku", PILOT, "W-b-0", HAIKU, False),
    (None, BLOCKWIN, "W-b-0", HAIKU, False),
    (BLOCK, PILOT, "W-np-0", HAIKU, False),  # R10's pilot
    (BLOCK, PILOT, "W-0", HAIKU, False),  # R8's pilot
    (BLOCK, "persistgym_haiku_control", "W-n-0", HAIKU, False),
])
def test_the_block_rule(block, experiment, cell, model, ok):
    why = registered.r12_block_refusal(block, cell, experiment, model)
    assert (why is None) is ok, why
    # R10's block rule leaves R12's W-np-0 runs to R12's
    if ok and cell == "W-np-0":
        assert registered.provenance_block_refusal(block, cell, experiment=experiment,
                                                   model=model) is None
    assert registered.provenance_block_refusal("6-haiku-provenance", "W-np-0") is None
    assert registered.provenance_block_refusal(BLOCK, "W-np-0") is not None  # R10's default


def _transport(model, experiment, experiments, block=BLOCK):
    return SimpleNamespace(model=model, experiment=experiment, approval=SimpleNamespace(
        approved_block=block, experiment=experiment, experiments=experiments))


@pytest.mark.parametrize("model, experiment, experiments, ok", [
    (HAIKU, NOTES, (NOTES,), True),
    (HAIKU, BLOCKWIN, (PILOT, NOTES, SONNET_X, BLOCKWIN), True),
    (HAIKU, PILOT, (PILOT, NOTES, SONNET_X, BLOCKWIN), True),
    (SONNET, SONNET_X, (PILOT, NOTES, SONNET_X, BLOCKWIN), True),
    (SONNET, PILOT, (PILOT, NOTES, SONNET_X, BLOCKWIN), True),
    (SONNET, PILOT, (PILOT, "persistgym_haiku"), False),
    (SONNET, "persistgym_haiku", ("persistgym_haiku",), False),
    (HAIKU, "persistgym_haiku_control", ("persistgym_haiku_control",), True),  # R11, as before
])
def test_the_transport_admits_r12s_runs_under_its_block(model, experiment, experiments, ok):
    why = AnthropicMessagesTransport._approval_refusal(_transport(model, experiment, experiments))
    assert (why is None) is ok, why


@pytest.mark.parametrize("model, experiment, ok", [
    (SONNET, SONNET_X, True), (SONNET, PILOT, True), (HAIKU, NOTES, True),
    (SONNET, NOTES, False), (SONNET, "persistgym_haiku", False),
    (SONNET + "-2026-11-01", SONNET_X, False), ("claude-opus-5-5", SONNET_X, False),
])
def test_the_transport_sends_sonnet_only_in_r12(monkeypatch, model, experiment, ok):
    monkeypatch.setattr("harnesses.anthropic_transport.credential_refusal", lambda: None)
    t = SimpleNamespace(model=model, experiment=experiment)
    if ok:
        AnthropicMessagesTransport._preflight(t)
    else:
        with pytest.raises(PaidCallsNotAllowed, match="Messages transport sends"):
            AnthropicMessagesTransport._preflight(t)
