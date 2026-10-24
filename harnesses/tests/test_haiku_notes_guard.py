"""R9's guard for claude-haiku-5-5's exploratory W-n-0 run (harnesses/registered.py
`_haiku_notes_refusal`; PREREG §17.9, amendment R9): fail closed.

* The repository: `R9_IN_EFFECT` is True, the run's experiment `persistgym_haiku_notes` is in
  phase 1a and the PersistGym stream, and R8's values stay as R8's size record set them
  (`HAIKU_CELLS` F-0 and W-0: W-n-0 still refuses in `persistgym_haiku`).
* The rules: W-n-0 on all 8 task cells as the full matrix, main templates within 0-199, base
  episodes, R8's effort, config and request settings, after `HAIKU_G1_PASSED`. Every other
  cell, split, variant, matrix, task-cell set, template range, effort, config, request or
  claude-* model refuses, naming §17.9.
* The kill switches: with `R9_IN_EFFECT` False every run in the experiment refuses and R8's
  runs still pass; with `R8_IN_EFFECT` False it refuses too.
* The blocks: the Anthropic transport admits a block that lists the experiment. Block
  `5-haiku-notes` cannot fund R8's runs, and block `4-haiku` cannot fund R9's. An end-to-end
  W-n-0 run goes through the real guarded transport with a fake-backed client.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from common import costs, paidlock
from common.tests.gitrepo import FROZEN_PREREG, approval_line, decisions_text, guarded_repo
from harnesses import anthropic_transport, cli, registered
from harnesses.anthropic_transport import AnthropicMessagesTransport
from harnesses.fake import FakeModel
from harnesses.openai_transport import ALLOW_ENV
from harnesses.tests.test_haiku_guard import (
    ALL8,
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

NOTES = "persistgym_haiku_notes"


@pytest.fixture
def no_g1(monkeypatch):
    monkeypatch.setattr(registered, "HAIKU_G1_PASSED", {})


# --- the repository ------------------------------------------------------------------------------

def test_the_repository_has_r9_in_effect_beside_r8s_values():
    assert registered.R9_IN_EFFECT is True and registered.R8_IN_EFFECT is True
    assert registered.R9_REF == "PREREG.md §17.9 (amendment R9)"
    assert registered.HAIKU_NOTES_EXPERIMENT == NOTES and registered.HAIKU_NOTES_CELL == "W-n-0"
    assert costs.EXPERIMENT_PHASE[NOTES] == "1a"
    assert paidlock.EXPERIMENT_STREAM[NOTES] == paidlock.PERSISTGYM
    # R8's size record is untouched: W-n-0 is not one of R8's main-run cells
    assert registered.HAIKU_CELLS == ("F-0", "W-0") and registered.HAIKU_T == 200
    assert NOTES not in registered.HAIKU_EXPERIMENTS


# --- the rules -----------------------------------------------------------------------------------

@pytest.mark.parametrize("templates", [(0, 200), (0, 1), (120, 200), (199, 200)])
def test_r9s_run_passes(tmp_path, templates):
    assert guard(NOTES, "W-n-0", tmp_path, templates=templates) is None


def test_a_dated_haiku_snapshot_is_haiku(tmp_path):
    assert guard(NOTES, "W-n-0", tmp_path, model=f"{HAIKU}-2026-10-01") is None


def test_w_n_0_still_refuses_in_r8s_experiment(tmp_path):
    why = guard(MAIN, "W-n-0", tmp_path)
    assert why is not None and "cell W-n-0" in why and registered.R8_REF in why


def test_r8s_runs_are_unchanged(tmp_path):
    for experiment, cell, kw in RUNS:
        assert guard(experiment, cell, tmp_path, **kw) is None, (experiment, cell, kw)


@pytest.mark.parametrize("cell, kw, wrong", [
    ("F-0", {}, "cell F-0"),
    ("W-0", {}, "cell W-0"),
    ("Σ-n-0", {}, "cell Σ-n-0"),
    ("single-turn", {"task_cells": NONREC, "matrix": None}, "cell single-turn"),
    ("W-n-0", {"split": "pilot", "templates": (0, 1)}, "--split pilot"),
    ("W-n-0", {"split": "validity", "templates": (0, 20)}, "--split validity"),
    ("W-n-0", {"variant": "restated"}, "--variant restated"),
    ("W-n-0", {"variant": "withheld"}, "--variant withheld"),
    ("W-n-0", {"matrix": "d11"}, "--matrix d11"),
    ("W-n-0", {"matrix": "custom"}, "--cell-templates"),
    ("W-n-0", {"matrix": None}, "run matrix (not given)"),
    ("W-n-0", {"task_cells": NONREC}, "task cells"),
    ("W-n-0", {"task_cells": ALL8[:-1]}, "task cells"),
    ("W-n-0", {"task_cells": None}, "task cells (not given)"),
    ("W-n-0", {"templates": (0, 201)}, "main templates 0-200"),
    ("W-n-0", {"templates": (200, 210)}, "main templates 200-209"),
    ("W-n-0", {"templates": None}, "main templates (not given)"),
    ("W-n-0", {"effort": "high"}, "--effort high"),
    ("W-n-0", {"gen": OTHER}, "generator config 000000000000"),
    ("W-n-0", {"request": {"mode": "standard", "service_tier": "standard", "W": 24000}}, "--W 24000"),
    ("W-n-0", {"request": None}, "--W (not given)"),
])
def test_anything_else_refuses(tmp_path, cell, kw, wrong):
    why = guard(NOTES, cell, tmp_path, **kw)
    assert why is not None and wrong in why and registered.R9_REF in why, why


@pytest.mark.parametrize("model", OTHER_CLAUDE)
def test_every_other_claude_model_refuses(tmp_path, model):
    why = guard(NOTES, "W-n-0", tmp_path, model=model)
    assert why is not None and model in why


@pytest.mark.parametrize("model", ["gpt-6-luna", "gpt-6.1-sol"])
def test_openai_models_never_run_in_r9s_experiment(tmp_path, model):
    assert guard(NOTES, "W-n-0", tmp_path, model=model) is not None


def test_without_g1_it_refuses(tmp_path, no_g1):
    why = guard(NOTES, "W-n-0", tmp_path)
    assert why is not None and "HAIKU_G1_PASSED" in why and registered.R9_REF in why


# --- the kill switches ---------------------------------------------------------------------------

def test_with_r9_off_its_runs_refuse_and_r8s_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(registered, "R9_IN_EFFECT", False)
    why = guard(NOTES, "W-n-0", tmp_path)
    assert why is not None and registered.R9_REF in why and "R9_IN_EFFECT" in why
    for experiment, cell, kw in RUNS:
        assert guard(experiment, cell, tmp_path, **kw) is None


@pytest.mark.parametrize("r6_on", [True, False])
def test_with_r8_off_r9s_run_refuses_too(tmp_path, monkeypatch, r6_on):
    monkeypatch.setattr(registered, "R8_IN_EFFECT", False)
    monkeypatch.setattr(registered, "R6_HARD_STOP", r6_on)
    why = guard(NOTES, "W-n-0", tmp_path)
    assert why is not None and registered.R8_REF in why


def test_with_r6_off_r9s_run_is_still_held_to_r9(tmp_path, monkeypatch):
    monkeypatch.setattr(registered, "R6_HARD_STOP", False)
    assert guard(NOTES, "W-n-0", tmp_path) is None
    assert registered.R9_REF in guard(NOTES, "W-0", tmp_path)


# --- the blocks ----------------------------------------------------------------------------------

def _approval_refusal(*experiments: str) -> str | None:
    fake_self = SimpleNamespace(approval=SimpleNamespace(approved_block="b",
                                                         experiments=experiments))
    return AnthropicMessagesTransport._approval_refusal(fake_self)


def test_the_transport_admits_a_block_that_lists_either_haiku_experiment():
    assert _approval_refusal(NOTES) is None
    assert _approval_refusal(PILOT, VALIDITY, MAIN) is None
    why = _approval_refusal(PILOT, VALIDITY)
    assert why is not None and MAIN in why and NOTES in why and "§17.9" in why


@pytest.fixture
def notes_paid_env(tmp_path, monkeypatch):
    """A repo whose frozen PREREG and decisions hold block 5-haiku-notes (R9's experiment
    only) beside block 4-haiku (R8's three); the CLI's own guarded transport builds the real
    Anthropic transport with a fake-backed client; a dummy key's variable; a lock of its own."""
    guarded_repo(tmp_path, prereg=FROZEN_PREREG, decisions=decisions_text(
        "4-haiku", experiments=(PILOT, VALIDITY, MAIN))
        + approval_line("5-haiku-notes", (NOTES,)) + "\n")
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
    return tmp_path, costs_csv, fakes


def test_an_end_to_end_r9_run(notes_paid_env, capsys):
    """W-n-0 on main template 0 x the 8 task cells under block 5-haiku-notes: through the
    settings guard, the paid guard and the Anthropic transport, with the notes instruction in
    every request's system prompt."""
    tmp, costs_csv, fakes = notes_paid_env
    assert cli.main(["run", "--cell", "W-n-0", "--model", HAIKU, "--split", "main", "--n", "1",
                     "--experiment", NOTES, "--approved-block", "5-haiku-notes",
                     "--planned-usd", "1", "--run-id", "hn", "--parallel", "4"]) == 0
    capsys.readouterr()
    (row,) = costs.read_rows(costs_csv)
    (fake,) = fakes
    assert (row["run_id"], row["experiment"], row["cell_or_config"]) == ("hn", NOTES, "W-n-0")
    assert row["notes"].startswith("approved_block=5-haiku-notes;")
    assert int(row["n_calls"]) == len(fake.calls) > 0
    system = json.dumps([p["system"] for p in fake.calls])
    assert "carry forward" in system  # the note-taking instruction (W-n-0)
    meta = json.loads((tmp / "results" / NOTES / "hn" / "meta.json").read_text(encoding="utf-8"))
    assert meta["exit_reason"] == "COMPLETED" and meta["n_episodes_run"] == 8
    assert not (tmp / "lock" / paidlock.lock_name(cli.STREAM)).exists()


@pytest.mark.parametrize("argv, block", [
    (["--cell", "F-0", "--experiment", MAIN], "5-haiku-notes"),     # R9's block, R8's run
    (["--cell", "W-n-0", "--experiment", NOTES], "4-haiku"),         # R8's block, R9's run
])
def test_neither_block_funds_the_others_runs(notes_paid_env, capsys, argv, block):
    _, costs_csv, fakes = notes_paid_env
    assert cli.main(["run", "--model", HAIKU, "--split", "main", "--n", "1", *argv,
                     "--approved-block", block, "--planned-usd", "1", "--run-id", "x"]) == 2
    experiment = argv[argv.index("--experiment") + 1]
    assert (f"refused: block '{block}' is approved for" in (err := capsys.readouterr().err)
            and f"not for experiment '{experiment}'" in err), err
    assert costs.read_rows(costs_csv) == [] and all(not f.calls for f in fakes)
