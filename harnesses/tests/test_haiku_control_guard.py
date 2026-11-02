"""R11's guard for claude-haiku-5-5's later W-n-0 control (harnesses/registered.py
`_haiku_control_refusal`; PREREG §17.11, amendment R11): fail closed.

* The repository: `R11_IN_EFFECT` is True, the run's experiment `persistgym_haiku_control` is in
  phase 1a and the PersistGym stream, and R9's and R10's experiments keep their rules.
* The rules: W-n-0 on the 2 not-recoverable far task cells as the full matrix, main templates
  within 0-199 at repeat 0, base episodes, exactly claude-haiku-5-5, R8's effort, config and
  request settings, after `HAIKU_G1_PASSED`. Every other cell, split, variant, matrix, task-cell
  set, template range, repeat, effort, config, request or model refuses, naming §17.11.
* The kill switches: with `R11_IN_EFFECT` False every run in the experiment refuses and R9's
  run still passes. With `R8_IN_EFFECT` False it refuses too.
* The block: the Anthropic transport admits the run under a block that lists its experiment.
  R9's and R10's blocks cannot fund it, and its block funds none of theirs. An end-to-end run
  goes through the real guarded transport with a fake-backed client, at the registered $17.24,
  with the notes instruction and none of R10's sentences in every system prompt.
* The stop: the planned spend sits below the block's $17.38 by at least what one send can add,
  and the decisions log's command uses it.
* `org-check`: reads the organization's digest from the free endpoint's header, never prints or
  writes the ID, an API error's text included, and exits 3 for an organization other than the
  one R10's error names.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import anthropic
import pytest

from analysis import haiku_control as hc
from analysis import haiku_control_forecast as hf
from common import costs, paidlock
from common.tests.gitrepo import FROZEN_PREREG, approval_line, decisions_text, guarded_repo
from harnesses import anthropic_transport, cli, org_check, registered
from harnesses.anthropic_transport import AnthropicMessagesTransport
from harnesses.cells import DISCLOSURE_SENTENCE, PROVENANCE_SENTENCE
from harnesses.fake import FakeModel
from harnesses.openai_transport import ALLOW_ENV
from harnesses.tests.test_haiku_guard import (
    ALL8,
    DEFAULT,
    HAIKU,
    MAIN,
    OTHER,
    OTHER_CLAUDE,
    PILOT,
    RUNS,
    VALIDITY,
    _FakeBackedClient,
    guard,
)

CONTROL = "persistgym_haiku_control"
NOTES = "persistgym_haiku_notes"
PROV = "persistgym_haiku_provenance"
TWO = ("observed-nonrec-far", "derived-nonrec-far")
BLOCK = "7-haiku-control"
REPO = Path(__file__).resolve().parents[2]


def control_guard(root, *, cell="W-n-0", task_cells=TWO, **kw):
    return guard(CONTROL, cell, root, task_cells=task_cells, **kw)


# --- the repository ------------------------------------------------------------------------------

def test_the_repository_has_r11_in_effect():
    assert registered.R11_IN_EFFECT is True and registered.R8_IN_EFFECT is True
    assert registered.R11_REF == "PREREG.md §17.11 (amendment R11)"
    assert registered.HAIKU_CONTROL_EXPERIMENT == CONTROL
    assert registered.HAIKU_CONTROL_CELL == "W-n-0"
    assert registered.HAIKU_CONTROL_TASK_CELLS == TWO
    assert costs.EXPERIMENT_PHASE[CONTROL] == "1a"
    assert paidlock.EXPERIMENT_STREAM[CONTROL] == paidlock.PERSISTGYM
    assert CONTROL not in registered.HAIKU_EXPERIMENTS


def test_the_decisions_log_approves_exactly_the_researchers_amount():
    text = (REPO / "results" / "decisions.md").read_text(encoding="utf-8")
    (line,) = [x for x in text.splitlines() if x.startswith(f"approved_block: {BLOCK} ")]
    assert line == f"approved_block: {BLOCK} | experiments: {CONTROL} | max_usd: 17.38"
    assert registered.HAIKU_CONTROL_MAX_USD == 17.38


def test_the_planned_spend_leaves_room_for_one_send_and_the_command_uses_it():
    forecast = hf.forecast(REPO)
    assert forecast["most_one_send_usd"] == pytest.approx(0.1335, abs=0.001)
    room = registered.HAIKU_CONTROL_MAX_USD - registered.HAIKU_CONTROL_PLANNED_USD
    assert room >= forecast["most_one_send_usd"]
    text = (REPO / "results" / "decisions.md").read_text(encoding="utf-8")
    line = next(x for x in text.splitlines()
                if f"--experiment {CONTROL}" in x and "--start 0 --n 200" in x)
    assert f"--planned-usd {registered.HAIKU_CONTROL_PLANNED_USD} " in line
    assert "--parallel 2" in line and all(c in line for c in TWO)


# --- the rules -----------------------------------------------------------------------------------

@pytest.mark.parametrize("templates", [(0, 200), (0, 1), (120, 200), (199, 200)])
def test_r11s_run_passes(tmp_path, templates):
    assert control_guard(tmp_path, templates=templates) is None


def test_repeat_1_refuses(tmp_path):
    why = registered.check_run_settings(
        CONTROL, HAIKU, "medium", "W-n-0", DEFAULT, tmp_path, split="main", variant="base",
        task_cells=TWO, request={"mode": "standard", "service_tier": "standard", "W": None},
        templates=(0, 200), matrix="full", repeat_index=1)
    assert why is not None and "--repeat-index 1" in why and registered.R11_REF in why


@pytest.mark.parametrize("kw, wrong", [
    ({"cell": "F-0"}, "cell F-0"),
    ({"cell": "W-0"}, "cell W-0"),
    ({"cell": "Σ-n-0"}, "cell Σ-n-0"),
    ({"split": "pilot", "templates": (0, 1)}, "--split pilot"),
    ({"split": "validity", "templates": (0, 20)}, "--split validity"),
    ({"variant": "restated"}, "--variant restated"),
    ({"variant": "withheld"}, "--variant withheld"),
    ({"matrix": "d11"}, "--matrix d11"),
    ({"matrix": "custom"}, "--cell-templates"),
    ({"matrix": None}, "run matrix (not given)"),
    ({"task_cells": ALL8}, "task cells"),
    ({"task_cells": TWO[:1]}, "task cells"),
    ({"task_cells": ("observed-rec-far", "derived-rec-far")}, "task cells"),
    ({"task_cells": None}, "task cells (not given)"),
    ({"templates": (0, 201)}, "main templates 0-200"),
    ({"templates": (200, 210)}, "main templates 200-209"),
    ({"templates": None}, "main templates (not given)"),
    ({"effort": "high"}, "--effort high"),
    ({"gen": OTHER}, "generator config 000000000000"),
    ({"request": {"mode": "standard", "service_tier": "standard", "W": 24000}}, "--W 24000"),
    ({"request": None}, "--W (not given)"),
    ({"model": f"{HAIKU}-2026-10-01"}, f"model {HAIKU}-2026-10-01"),
])
def test_anything_else_refuses(tmp_path, kw, wrong):
    why = control_guard(tmp_path, **kw)
    assert why is not None and wrong in why and registered.R11_REF in why, why


@pytest.mark.parametrize("cell", registered.HAIKU_PROVENANCE_CELLS)
def test_r10s_cells_never_run_in_r11s_experiment(tmp_path, cell):
    assert control_guard(tmp_path, cell=cell) is not None


@pytest.mark.parametrize("model", OTHER_CLAUDE)
def test_every_other_claude_model_refuses(tmp_path, model):
    why = control_guard(tmp_path, model=model)
    assert why is not None and model in why


@pytest.mark.parametrize("model", ["gpt-6-luna", "gpt-6.1-sol"])
@pytest.mark.parametrize("r6_on", [True, False])
def test_openai_models_never_run_in_r11s_experiment(tmp_path, monkeypatch, model, r6_on):
    monkeypatch.setattr(registered, "R6_HARD_STOP", r6_on)
    assert control_guard(tmp_path, model=model) is not None


@pytest.mark.parametrize("model", ["gpt-6-luna", "gpt-6.1-sol"])
def test_with_r6_off_an_openai_model_is_refused_by_r11s_rule(tmp_path, monkeypatch, model):
    monkeypatch.setattr(registered, "R6_HARD_STOP", False)
    why = control_guard(tmp_path, model=model)
    assert registered.R11_REF in why, why


def test_without_g1_it_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(registered, "HAIKU_G1_PASSED", {})
    why = control_guard(tmp_path)
    assert why is not None and "HAIKU_G1_PASSED" in why and registered.R11_REF in why


def test_r9s_run_is_unchanged(tmp_path):
    assert guard(NOTES, "W-n-0", tmp_path) is None
    assert guard(NOTES, "W-n-0", tmp_path, task_cells=TWO) is not None


def test_r8s_runs_are_unchanged(tmp_path):
    for experiment, cell, kw in RUNS:
        assert guard(experiment, cell, tmp_path, **kw) is None, (experiment, cell, kw)


# --- the kill switches ---------------------------------------------------------------------------

def test_with_r11_off_its_run_refuses_and_r9s_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(registered, "R11_IN_EFFECT", False)
    why = control_guard(tmp_path)
    assert why is not None and registered.R11_REF in why and "R11_IN_EFFECT" in why
    assert guard(NOTES, "W-n-0", tmp_path) is None


@pytest.mark.parametrize("r6_on", [True, False])
def test_with_r8_off_r11s_run_refuses_too(tmp_path, monkeypatch, r6_on):
    monkeypatch.setattr(registered, "R8_IN_EFFECT", False)
    monkeypatch.setattr(registered, "R6_HARD_STOP", r6_on)
    why = control_guard(tmp_path)
    assert why is not None and registered.R8_REF in why


def test_with_r6_off_r11s_run_is_still_held_to_r11(tmp_path, monkeypatch):
    monkeypatch.setattr(registered, "R6_HARD_STOP", False)
    assert control_guard(tmp_path) is None
    assert registered.R11_REF in control_guard(tmp_path, cell="W-0")


# --- the block -----------------------------------------------------------------------------------

def _approval_refusal(experiment: str, *experiments: str) -> str | None:
    """The transport's block check for a run in `experiment` under a block that lists
    `experiments` (the general guard has already required `experiment` among them)."""
    fake_self = SimpleNamespace(approval=SimpleNamespace(
        approved_block="b", experiment=experiment, experiments=experiments))
    return AnthropicMessagesTransport._approval_refusal(fake_self)


def test_the_transport_admits_r11s_run_under_its_block():
    assert _approval_refusal(CONTROL, CONTROL) is None


def test_a_block_that_lists_r11s_experiment_funds_no_other_haiku_run():
    why = _approval_refusal(PILOT, CONTROL, PILOT, VALIDITY)
    assert why is not None and CONTROL in why and "§17.11" in why


@pytest.fixture
def control_paid_env(tmp_path, monkeypatch):
    """A repo whose frozen PREREG and decisions hold block 7-haiku-control (R11's experiment only,
    at the researcher's $17.38) beside R8's, R9's and R10's. The CLI's own guarded transport
    builds the real Anthropic transport with a fake-backed client, with a dummy key's variable
    and a lock of its own."""
    guarded_repo(tmp_path, prereg=FROZEN_PREREG, decisions=decisions_text(
        "4-haiku", experiments=(PILOT, VALIDITY, MAIN))
        + approval_line("5-haiku-notes", (NOTES,)) + "\n"
        + approval_line("6-haiku-provenance", (PILOT, PROV)) + "\n"
        + f"approved_block: {BLOCK} | experiments: {CONTROL} | max_usd: 17.38\n")
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


RUN = ["run", "--cell", "W-n-0", "--model", HAIKU, "--split", "main", "--task-cell", *TWO,
       "--experiment", CONTROL]


def test_an_end_to_end_r11_run(control_paid_env, capsys):
    """W-n-0 on main template 0 x the 2 task cells under block 7-haiku-control, at the registered
    $17.24: through the settings guard, the paid guard and the Anthropic transport, with the
    notes instruction and neither of R10's sentences in every request's system prompt."""
    tmp, costs_csv, fakes = control_paid_env
    assert cli.main([*RUN, "--n", "1", "--approved-block", BLOCK, "--planned-usd",
                     str(registered.HAIKU_CONTROL_PLANNED_USD), "--run-id", "hc",
                     "--parallel", "2"]) == 0
    capsys.readouterr()
    (row,) = costs.read_rows(costs_csv)
    (fake,) = fakes
    assert (row["run_id"], row["experiment"], row["cell_or_config"]) == ("hc", CONTROL, "W-n-0")
    assert row["notes"].startswith(f"approved_block={BLOCK};")
    assert int(row["n_calls"]) == len(fake.calls) > 0
    system = json.dumps([p["system"] for p in fake.calls], ensure_ascii=False)
    assert "carry forward" in system
    assert PROVENANCE_SENTENCE not in system and DISCLOSURE_SENTENCE not in system
    meta = json.loads((tmp / "results" / CONTROL / "hc" / "meta.json").read_text(encoding="utf-8"))
    assert meta["exit_reason"] == "COMPLETED" and meta["n_episodes_run"] == 2
    assert not (tmp / "lock" / paidlock.lock_name(cli.STREAM)).exists()


def test_the_whole_block_can_be_planned_and_no_more(control_paid_env, capsys):
    _, costs_csv, fakes = control_paid_env
    assert cli.main([*RUN, "--n", "1", "--approved-block", BLOCK, "--planned-usd", "17.39",
                     "--run-id", "over"]) == 2
    assert "refused:" in capsys.readouterr().err
    assert costs.read_rows(costs_csv) == [] and all(not f.calls for f in fakes)


@pytest.mark.parametrize("argv, block", [
    (["--cell", "W-n-0", "--experiment", CONTROL, "--task-cell", *TWO], "5-haiku-notes"),
    (["--cell", "W-n-0", "--experiment", CONTROL, "--task-cell", *TWO], "6-haiku-provenance"),
    (["--cell", "W-n-0", "--experiment", NOTES], BLOCK),
])
def test_no_other_block_funds_it_and_its_block_funds_nothing_else(control_paid_env, capsys, argv,
                                                                  block):
    _, costs_csv, fakes = control_paid_env
    assert cli.main(["run", "--model", HAIKU, "--split", "main", "--n", "1", *argv,
                     "--approved-block", block, "--planned-usd", "1", "--run-id", "x"]) == 2
    assert "refused:" in capsys.readouterr().err
    assert costs.read_rows(costs_csv) == [] and all(not f.calls for f in fakes)


def test_a_wrong_task_cell_refuses_before_the_lock(monkeypatch, capsys):
    monkeypatch.setenv(ALLOW_ENV, "1")

    def no_transport(*a, **k):
        raise AssertionError("must refuse before the lock and any transport")
    monkeypatch.setattr(cli, "_guarded_transport", no_transport)
    monkeypatch.setattr(cli, "_with_paid_lock", no_transport)
    assert cli.main(["run", "--cell", "W-n-0", "--model", HAIKU, "--split", "main", "--n", "200",
                     "--experiment", CONTROL, "--approved-block", BLOCK,
                     "--planned-usd", "17.38"]) == 2
    err = capsys.readouterr().err
    assert "refused:" in err and "task cells" in err and "§17.11" in err


# --- org-check -----------------------------------------------------------------------------------

class _Stub:
    """Answers the free endpoint's raw call with one header. It holds no custom header."""

    def __init__(self, org):
        self.org, self.calls, self.messages = org, [], self
        self.with_raw_response = self
        self.default_headers = {}
        self._custom_headers = {}
        self.error = None

    def count_tokens(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        headers = {org_check.ORG_HEADER: self.org} if self.org else {}
        return SimpleNamespace(headers=headers)

    def stream(self, **kw):
        raise AssertionError("org-check never calls the model")

    create = stream


@pytest.fixture
def org_env(monkeypatch):
    monkeypatch.setenv(anthropic_transport.KEY_ENV, "dummy-not-a-key")
    for name in anthropic_transport.REFUSED_ENV:
        monkeypatch.delenv(name, raising=False)


ORG = "00000000-1111-2222-3333-444444444444"


def _run_check(monkeypatch, tmp_path, org, error=None):
    stub = _Stub(org)
    stub.error = error
    monkeypatch.setattr(cli, "ORG_CHECK_CLIENT", lambda: stub)
    out = tmp_path / "o" / "org_check.json"
    return cli.main(["org-check", "--out", str(out)]), out, stub


def test_the_digests_are_of_the_ids_the_committed_records_name():
    for run, digest in (
            ("persistgym_haiku_provenance/20261101T184553Z-W-np-0-claude-haiku-5-5",
             org_check.R10_ORG_SHA256),
            ("persistgym_haiku/20261018T144829Z-W-0-claude-haiku-5-5", org_check.R8_ORG_SHA256)):
        text = (REPO / "results" / run / "episodes.jsonl").read_text(encoding="utf-8")
        ids = set(re.findall(r"\(org: ([0-9a-f-]{36})", text))
        assert {org_check.org_digest(i) for i in ids} == {digest}
    assert org_check.R10_ORG_SHA256 != org_check.R8_ORG_SHA256


def test_another_organization_exits_3_and_the_id_is_never_written(org_env, monkeypatch, tmp_path,
                                                                  capsys):
    code, out, stub = _run_check(monkeypatch, tmp_path, ORG)
    printed = capsys.readouterr()
    assert code == 3 and "not the one R10's rate-limit error names" in printed.err
    text = out.read_text(encoding="utf-8")
    report = json.loads(text)
    assert report["same_org_as_r10_error"] is False and report["same_org_as_r8_error"] is False
    assert report["org_sha256"] == org_check.org_digest(ORG)
    assert ORG not in text and ORG not in printed.out and ORG not in printed.err
    (call,) = stub.calls
    assert call["model"] == HAIKU


def test_r10s_organization_exits_0(org_env, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(org_check, "R10_ORG_SHA256", org_check.org_digest(ORG))
    code, out, _ = _run_check(monkeypatch, tmp_path, ORG)
    capsys.readouterr()
    report = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0 and report["same_org_as_r10_error"] is True


def test_an_api_error_refuses_and_its_text_is_not_printed(org_env, monkeypatch, tmp_path, capsys):
    error = anthropic.APIConnectionError(
        message=f"rate limit (org: {ORG}, model: {HAIKU})", request=None)
    code, out, _ = _run_check(monkeypatch, tmp_path, ORG, error=error)
    printed = capsys.readouterr()
    assert code == 2 and "APIConnectionError" in printed.err and not out.exists()
    assert ORG not in printed.err and ORG not in printed.out


def test_the_sdks_debug_log_refuses_before_any_call(org_env, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv(org_check.LOG_ENV, "debug")
    code, out, stub = _run_check(monkeypatch, tmp_path, ORG)
    assert code == 2 and "ANTHROPIC_LOG=debug" in capsys.readouterr().err
    assert stub.calls == [] and not out.exists()


def test_a_client_with_a_custom_header_refuses_before_any_call(org_env, monkeypatch, tmp_path,
                                                               capsys):
    stub = _Stub(ORG)
    stub._custom_headers = {"x-made-up": "1"}
    monkeypatch.setattr(cli, "ORG_CHECK_CLIENT", lambda: stub)
    out = tmp_path / "o.json"
    assert cli.main(["org-check", "--out", str(out)]) == 2
    assert "custom headers" in capsys.readouterr().err and stub.calls == [] and not out.exists()


def test_r8s_organization_is_named_as_such(org_env, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(org_check, "R8_ORG_SHA256", org_check.org_digest(ORG))
    code, out, _ = _run_check(monkeypatch, tmp_path, ORG)
    capsys.readouterr()
    assert code == 3
    assert json.loads(out.read_text(encoding="utf-8"))["same_org_as_r8_error"] is True


def test_the_default_folder_is_the_one_the_analysis_reads(org_env, monkeypatch, tmp_path, capsys):
    assert registered.HAIKU_CONTROL_ORG_CHECK == "haiku_control_org"
    stub = _Stub(ORG)
    monkeypatch.setattr(cli, "ORG_CHECK_CLIENT", lambda: stub)
    monkeypatch.setattr(cli, "RESULTS", tmp_path / "results")
    assert cli.main(["org-check"]) == 3
    capsys.readouterr()
    (found,) = (tmp_path / "results" / "haiku_control_org").glob("*/org_check.json")
    assert hc.org_checks(tmp_path)[0]["same_org_as_r10_error"] is False and found.is_file()


def test_no_header_refuses(org_env, monkeypatch, tmp_path, capsys):
    code, out, _ = _run_check(monkeypatch, tmp_path, None)
    assert code == 2 and "no anthropic-organization-id header" in capsys.readouterr().err
    assert not out.exists()


def test_no_key_refuses_before_any_call(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv(anthropic_transport.KEY_ENV, raising=False)
    code, out, stub = _run_check(monkeypatch, tmp_path, ORG)
    assert code == 2 and "refused:" in capsys.readouterr().err
    assert stub.calls == [] and not out.exists()
