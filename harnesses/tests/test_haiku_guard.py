"""R8's guard for claude-haiku-5-5 (harnesses/registered.py `haiku_refusal`; PREREG §17.8,
amendment R8, not yet written or merged): fail closed.

* `R8_IN_EFFECT` is False in the repository, and then every Haiku paid run refuses, naming
  §17.8: pilots, the validity run, main runs and the single-turn control, with R6's hard stop
  on or off, through `run`, `single-turn` and the probes, before the paid-run lock; and so
  does every other claude-* string, which goes to the Messages API too.
* With it monkeypatched True (as the R8 pull request will set it), the rules in R4's pattern:
  pilots, the validity run with no G1, main runs only after `HAIKU_G1_PASSED`; luna's and
  sol's runs are judged as before, and neither runs in `persistgym_haiku`.
* The CLI: `dry-run` works at $0 on the Messages wire, --service-tier defaults per wire, the
  docstring's R8 commands parse, an end-to-end Haiku pilot (R8 on) goes through the real
  guarded transport with a fake-backed client (and refuses under a block that does not
  list persistgym_haiku), and `account-run` refuses a Haiku run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from common import costs, paidlock, runmeta
from common.tests.gitrepo import FROZEN_PREREG, approval_line, decisions_text, guarded_repo
from harnesses import account, anthropic_transport, blinding, cli, registered
from harnesses.anthropic_transport import AnthropicMessagesTransport
from harnesses.fake import FakeModel
from harnesses.openai_transport import ALLOW_ENV
from harnesses.tests.test_registered import _commands
from persistgym.episode import ALL_CELLS

HAIKU, LUNA, SOL = "claude-haiku-5-5", "gpt-6-luna", "gpt-6.1-sol"
DEFAULT = registered.DEFAULT_GENERATOR_HASH
OTHER = "0" * 64
REQUEST = {"mode": "standard", "service_tier": "standard", "W": None}
ALL8 = tuple(c.id for c in ALL_CELLS)
NONREC = tuple(c.id for c in ALL_CELLS if not c.recoverable)
PILOT, VALIDITY, MAIN = "persistgym_pilot", "persistgym_validity", "persistgym_haiku"
OTHER_CLAUDE = ("claude-haiku-5-5-latest", "claude-sonnet-5", "claude-haiku-4-5")
"""claude-* strings that are not claude-haiku-5-5 or a dated snapshot of it: the wire sends
them to the Messages API and the price matches some of them by prefix, so R8 holds them too."""


def guard(experiment, cell, root, *, model=HAIKU, effort="medium", gen=DEFAULT, split="main",
          variant="base", task_cells=ALL8, request=REQUEST, templates=(0, 200),
          matrix="full"):
    return registered.check_run_settings(experiment, model, effort, cell, gen, root,
                                         split=split, variant=variant, task_cells=task_cells,
                                         request=request, templates=templates, matrix=matrix)


@pytest.fixture
def r8(monkeypatch):
    """R8 in effect, as its pull request will set it (`registered.R8_IN_EFFECT`)."""
    monkeypatch.setattr(registered, "R8_IN_EFFECT", True)


@pytest.fixture
def g1(monkeypatch):
    """The researcher's G1 GO for the Haiku replication on the default config."""
    monkeypatch.setitem(registered.HAIKU_G1_PASSED, HAIKU, DEFAULT)


def _haiku_pilot_meta(results: Path, name: str, n: int, model: str = HAIKU) -> None:
    meta = {"experiment": PILOT, "run_id": name, "cell_or_config": "single-turn",
            "model_requested": model, "n_episodes_run": n}
    path = results / PILOT / name / "meta.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta), encoding="utf-8")


# The runs R8 registers, each as (experiment, cell, guard settings); all pass once R8 is in
# effect (main runs after G1)
RUNS = [
    (PILOT, "W-0", {"split": "pilot", "templates": (0, 1)}),
    (PILOT, "F-0", {"split": "pilot", "templates": (0, 1), "task_cells": ("observed-rec-far",)}),
    (PILOT, "single-turn", {"split": "pilot", "templates": (0, 2), "task_cells": NONREC,
                            "matrix": None}),
    (VALIDITY, "F-0", {"split": "validity", "variant": "restated", "templates": (0, 20)}),
    (VALIDITY, "F-0", {"split": "validity", "variant": "withheld", "templates": (0, 20)}),
    (MAIN, "F-0", {}),
    (MAIN, "F-0", {"variant": "restated"}),
    (MAIN, "W-0", {}),
    (MAIN, "W-n-0", {"templates": (190, 200)}),
    (MAIN, "single-turn", {"task_cells": NONREC, "matrix": None}),
]


# --- R8 not in effect: every Haiku run refuses ------------------------------------------------

def test_the_repository_has_r8_off_and_no_haiku_g1():
    assert registered.R8_IN_EFFECT is False and registered.HAIKU_G1_PASSED == {}
    assert registered.REGISTERED_EFFORT[HAIKU] == "medium" == registered.HAIKU_EFFORT
    assert registered.HAIKU_CELLS == ("F-0", "W-0", "W-n-0")
    assert registered.HAIKU_TASK_CELLS == ALL8 and registered.HAIKU_T == 200
    assert registered.HAIKU_REQUEST == REQUEST and registered.HAIKU_GENERATOR_HASH == DEFAULT
    assert registered.HAIKU_EXPERIMENT == MAIN
    assert costs.EXPERIMENT_PHASE[MAIN] == "1a"
    assert paidlock.EXPERIMENT_STREAM[MAIN] == paidlock.PERSISTGYM
    assert "anthropic" in runmeta.SDKS
    env = (runmeta.REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    assert "ANTHROPIC_API_KEY=" in env  # the name only, no value


@pytest.mark.parametrize("model", [HAIKU, "claude-haiku-5-5-2026-10-01", *OTHER_CLAUDE])
@pytest.mark.parametrize("r6_on", [True, False])
@pytest.mark.parametrize("experiment, cell, kw", RUNS)
def test_without_r8_every_haiku_run_refuses(tmp_path, monkeypatch, g1, r6_on, experiment,
                                            cell, kw, model):
    """Every claude-* string, not only claude-haiku-5-5: with R6's hard stop off, a string
    outside Haiku's exact or dated family used to skip R8 and pass the old pilot rules."""
    monkeypatch.setattr(registered, "R6_HARD_STOP", r6_on)
    why = guard(experiment, cell, tmp_path, model=model, **kw)
    assert why is not None and registered.R8_REF in why and "R8_IN_EFFECT" in why
    assert (f"got model {model}, which is not {HAIKU}" in why) is (model in OTHER_CLAUDE)


def test_without_r8_the_probes_refuse_haiku(tmp_path):
    for experiment in ("toggle_pilot", "replay_probe"):
        assert registered.R8_REF in registered.r6_refusal(experiment, HAIKU, None, tmp_path)


@pytest.mark.parametrize("argv", [
    ["run", "--cell", "W-0", "--model", HAIKU, "--split", "pilot", "--n", "1"],
    ["run", "--cell", "F-0", "--model", HAIKU, "--split", "validity", "--n", "20",
     "--variant", "restated", "--experiment", VALIDITY],
    ["run", "--cell", "F-0", "--model", HAIKU, "--split", "main", "--n", "200",
     "--experiment", MAIN],
    ["single-turn", "--model", HAIKU, "--split", "pilot", "--n", "2"],
    ["single-turn", "--model", HAIKU, "--split", "main", "--n", "200", "--experiment", MAIN],
    ["probe-echo", "--model", HAIKU]])
def test_the_cli_refuses_haiku_before_the_lock(monkeypatch, capsys, argv):
    monkeypatch.setenv(ALLOW_ENV, "1")

    def no_transport(*a, **k):
        raise AssertionError("must refuse before the lock and any transport")
    monkeypatch.setattr(cli, "_guarded_transport", no_transport)
    monkeypatch.setattr(cli, "_with_paid_lock", no_transport)
    assert cli.main([*argv, "--approved-block", "4-haiku", "--planned-usd", "1"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("refused:") and "§17.8" in err


# --- R8 in effect: the rules -------------------------------------------------------------------

@pytest.mark.parametrize("experiment, cell, kw", RUNS)
def test_with_r8_its_runs_pass(tmp_path, r8, g1, experiment, cell, kw):
    assert guard(experiment, cell, tmp_path, **kw) is None


def test_with_r8_the_validity_run_and_pilots_need_no_g1_and_main_runs_do(tmp_path, r8):
    for experiment, cell, kw in RUNS:
        why = guard(experiment, cell, tmp_path, **kw)
        if experiment == MAIN:
            assert "HAIKU_G1_PASSED" in why
        else:
            assert why is None


def test_with_r8_luna_g1_never_counts_for_haiku(tmp_path, r8, monkeypatch):
    monkeypatch.setitem(registered.HAIKU_G1_PASSED, HAIKU, OTHER)
    assert "HAIKU_G1_PASSED" in guard(MAIN, "F-0", tmp_path)
    assert registered.G1_PASSED[LUNA] == DEFAULT  # luna's G1 is on the default config


@pytest.mark.parametrize("experiment, cell, kw, wrong", [
    (PILOT, "W-0", {"split": "pilot", "templates": (0, 1), "effort": "high"}, "--effort high"),
    (PILOT, "W-0", {"split": "pilot", "templates": (0, 1),
                    "request": {**REQUEST, "service_tier": "flex"}}, "--service-tier flex"),
    (PILOT, "W-0", {"split": "pilot", "templates": (0, 1),
                    "request": {**REQUEST, "mode": "pro"}}, "--mode pro"),
    (PILOT, "W-0", {"split": "pilot", "templates": (0, 1),
                    "request": {**REQUEST, "W": 1000}}, "--W 1000"),
    (PILOT, "W-0", {"split": "pilot", "templates": (0, 1), "request": None}, "not given"),
    (PILOT, "W-0", {"split": "pilot", "templates": (0, 1), "gen": OTHER}, "generator config"),
    (PILOT, "Σ-n-0", {"split": "pilot", "templates": (0, 1)}, "cell Σ-n-0"),
    (PILOT, "F-r", {"split": "pilot", "templates": (0, 1)}, "cell F-r"),
    (PILOT, "F-0", {"split": "pilot", "templates": (0, 1), "variant": "restated"},
     "--variant restated"),
    (PILOT, "F-0", {"split": "pilot", "templates": (0, 1), "task_cells": ()}, "task cells"),
    (PILOT, "single-turn", {"split": "pilot", "templates": (0, 3), "task_cells": NONREC},
     "12 prompts"),
    (PILOT, "single-turn", {"split": "pilot", "templates": (0, 1),
                            "task_cells": ("observed-rec-far",)}, "task cells"),
    (VALIDITY, "F-0", {"split": "validity", "variant": "restated", "templates": (0, 21)},
     "validity templates 0-20"),
    (VALIDITY, "W-0", {"split": "validity", "variant": "restated", "templates": (0, 20)},
     "cell W-0"),
    (VALIDITY, "F-0", {"split": "validity", "variant": "base", "templates": (0, 20)},
     "--variant base"),
    (VALIDITY, "F-0", {"split": "validity", "variant": "restated", "templates": (0, 20),
                       "effort": "low"}, "--effort low"),
    (MAIN, "W-0", {"variant": "restated"}, "--variant restated in cell W-0"),
    (MAIN, "Σ-n-0", {}, "cell Σ-n-0"),
    (MAIN, "F-r", {}, "cell F-r"),
    (MAIN, "F-0", {"matrix": "d11"}, "--matrix d11"),
    (MAIN, "F-0", {"matrix": "custom"}, "--cell-templates"),
    (MAIN, "F-0", {"templates": (0, 201)}, "main templates 0-200"),
    (MAIN, "F-0", {"task_cells": ALL8[:4]}, "task cells"),
    (MAIN, "F-0", {"split": "validity"}, "--split validity"),
    (MAIN, "F-0", {"variant": "withheld"}, "--variant withheld"),
    (MAIN, "F-0", {"gen": OTHER}, "generator config"),
    (MAIN, "single-turn", {"task_cells": NONREC[:2], "matrix": None}, "task cells"),
    (MAIN, "F-0", {"request": {**REQUEST, "service_tier": "flex"}}, "--service-tier flex"),
    ("persistgym", "F-0", {}, "R6's hard stop"),
    ("persistgym_sol_h1", "F-0", {}, "R6's hard stop")])
def test_with_r8_anything_else_refuses(tmp_path, r8, g1, experiment, cell, kw, wrong):
    why = guard(experiment, cell, tmp_path, **kw)
    assert why is not None and wrong in why, why


def test_with_r8_and_r6_off_haiku_is_still_held_to_r8(tmp_path, r8, g1, monkeypatch):
    monkeypatch.setattr(registered, "R6_HARD_STOP", False)
    why = guard("persistgym", "F-0", tmp_path)
    assert registered.R8_REF in why and why.endswith("got --experiment persistgym")
    assert guard(MAIN, "F-0", tmp_path) is None
    # every other claude-* string is held to R8 too, which registers none of them
    for model in OTHER_CLAUDE:
        for experiment, cell, kw in RUNS:
            why = guard(experiment, cell, tmp_path, model=model, **kw)
            assert why is not None and f"model {model}" in why, (model, experiment, cell)


def test_with_r8_other_models_never_run_in_its_experiment(tmp_path, r8, g1):
    assert "R6's hard stop" in guard(MAIN, "F-0", tmp_path, model=LUNA)
    assert "R6's hard stop" in guard(MAIN, "F-0", tmp_path, model=SOL, effort="medium")
    for model in ("claude-haiku-4-5", "claude-sonnet-5-5", "claude-haiku-5-5-x"):
        assert "not a registered model" in guard(MAIN, "F-0", tmp_path, model=model)


def test_with_r8_the_probes_still_refuse_haiku(tmp_path, r8):
    for experiment in ("toggle_pilot", "replay_probe"):
        assert "R6's hard stop" in registered.r6_refusal(experiment, HAIKU, None, tmp_path)


def test_haiku_and_luna_single_turn_pilots_are_counted_apart(tmp_path, r8, monkeypatch):
    """At most 10 prompts each, counted over that model's single-turn pilots only."""
    _haiku_pilot_meta(tmp_path, "haiku-st", 8)
    st = {"split": "pilot", "task_cells": NONREC, "matrix": None}
    assert "4 prompts after 8 in earlier single-turn pilots of Haiku" in guard(
        PILOT, "single-turn", tmp_path, templates=(0, 1), **st)
    assert guard(PILOT, "single-turn", tmp_path, templates=(0, 1),
                 **{**st, "task_cells": NONREC[:2]}) is None
    assert registered._single_turn_pilot_prompts(tmp_path) == (0, None)        # luna's: none
    assert registered._single_turn_pilot_prompts(tmp_path, HAIKU) == (8, None)
    _haiku_pilot_meta(tmp_path, "luna-st", 8, model=LUNA)
    assert registered._single_turn_pilot_prompts(tmp_path, HAIKU) == (8, None)
    # luna's single-turn pilot rule is unchanged: its own 8 count against it, Haiku's do not
    assert registered.r6_refusal(PILOT, LUNA, "single-turn", tmp_path, split="pilot",
                                 task_cells=NONREC[:2], templates=(0, 1), effort="medium",
                                 generator_hash=DEFAULT,
                                 request=registered.LUNA_REQUEST) is None
    assert "4 prompts after 8" in registered.r6_refusal(
        PILOT, LUNA, "single-turn", tmp_path, split="pilot", task_cells=NONREC,
        templates=(0, 1), effort="medium", generator_hash=DEFAULT,
        request=registered.LUNA_REQUEST)


def test_lunas_main_sweep_is_unchanged_with_r8(tmp_path, r8):
    luna_request = {"mode": "standard", "service_tier": "flex", "W": None}
    assert guard("persistgym", "F-0", tmp_path, model=LUNA, request=luna_request) is None
    assert "outside persistgym_pilot" in guard("persistgym", "F-0", tmp_path, model=LUNA,
                                               request=REQUEST)


def test_haiku_pilot_episodes_are_never_pooled():
    assert blinding.is_left_out({"model": HAIKU, "harness_cell": "W-0", "variant": "base"})
    assert not blinding.is_left_out({"model": LUNA, "harness_cell": "W-0", "variant": "base"})


# --- the CLI -------------------------------------------------------------------------------------

def test_dry_run_on_the_messages_wire(capsys):
    assert cli.main(["dry-run", "--model", HAIKU, "--cell", "W-0",
                     "--task-cell", "observed-nonrec-far"]) == 0
    out = capsys.readouterr().out
    assert "exit DONE" in out and "reasoning.context" not in out
    assert "thinking=adaptive output_config.effort=medium max_tokens=32000 " \
           "cache_control=ephemeral" in out
    sent = out.split("labels:")[1].split("\n", 1)[1]
    assert re.search(r"\bA\d+\b", sent) and not re.search(r"\bR\d+\b", sent)  # no reasoning


def test_dry_run_refuses_a_cell_the_messages_wire_does_not_send(capsys):
    assert cli.main(["dry-run", "--model", HAIKU, "--cell", "sigma-n-0"]) == 2
    assert "refused: cell Σ-n-0 summarizes at W" in capsys.readouterr().err


def test_service_tier_defaults_per_wire():
    assert cli.parse_args(["run", "--cell", "F-0", "--model", HAIKU]).service_tier == "standard"
    assert cli.parse_args(["run", "--cell", "F-0"]).service_tier == "flex"
    assert cli.parse_args(["single-turn", "--model", HAIKU]).service_tier == "standard"
    assert cli.parse_args(["probe-echo"]).service_tier == "flex"
    assert cli.parse_args(["run", "--cell", "F-0", "--model", HAIKU, "--service-tier",
                           "flex"]).service_tier == "flex"
    assert cli._run_defaults()["service_tier"] == "flex"


def _r8_commands() -> list[list[str]]:
    return [c for c in _commands(cli.__doc__) if HAIKU in c]


def test_the_cli_docstrings_r8_commands_parse_and_wait_for_r8(tmp_path, monkeypatch):
    commands = _r8_commands()
    assert {c[0] for c in commands} == {"dry-run", "count-tokens", "run", "single-turn"}
    paid = [c for c in commands if c[0] in ("run", "single-turn")]
    assert len(paid) == 4
    for argv in commands:
        assert cli.parse_args(argv).cmd == argv[0]

    def guard_of(argv):
        a = cli.parse_args(argv)
        gen = runmeta.config_hash(cli._gen_config(a.gen_preset, a.gen_set).to_dict())
        if a.cmd == "single-turn":
            return registered.check_run_settings(
                a.experiment, a.model, a.effort, "single-turn", gen, tmp_path, split=a.split,
                variant="base", task_cells=NONREC,
                request={"mode": a.mode, "service_tier": a.service_tier, "W": None},
                templates=(a.start, a.start + a.n))
        m = cli._run_matrix(a)
        return registered.check_run_settings(
            a.experiment, a.model, a.effort, a.cell, gen, tmp_path, split=a.split,
            variant=a.variant, task_cells=tuple(c for c, n in m.templates if n),
            request={"mode": a.mode, "service_tier": a.service_tier, "W": a.W},
            templates=(a.start, a.start + m.n_templates), matrix=m.name)
    assert all(registered.R8_REF in guard_of(c) for c in paid)
    monkeypatch.setattr(registered, "R8_IN_EFFECT", True)
    monkeypatch.setitem(registered.HAIKU_G1_PASSED, HAIKU, DEFAULT)
    assert [guard_of(c) for c in paid] == [None] * 4


def test_account_run_refuses_a_haiku_run(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "RAW", tmp_path / "raw")
    assert cli.main(["account-run", "haiku-run", "--cell", "F-0", "--model", HAIKU,
                     "--service-tier", "standard", "--split", "main", "--n", "1",
                     "--experiment", MAIN, "--approved-block", "4-haiku", "--planned-usd", "1",
                     "--git-commit", "0" * 40, "--git-dirty", "false"]) == 2
    assert "account-run rebuilds runs on OpenAI's Responses API only" in capsys.readouterr().err
    with pytest.raises(account.Refused, match="Responses API only"):
        account._check_settings(account.Run(
            run_id="r", args=cli.parse_args(["run", "--cell", "F-0", "--model", HAIKU]),
            cell=None, cfg=None, matrix=None, episodes=[], notes="", what=""), None)


# --- an end-to-end Haiku pilot through the real guarded transport (R8 on) ------------------------

class _Message:
    def __init__(self, data):
        self.data = data

    def to_dict(self, mode="python"):
        return self.data


class _FakeBackedStream:
    def __init__(self, fake, payload):
        self.fake, self.payload = fake, payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return _Message(self.fake.send(self.payload))


class _FakeBackedClient:
    def __init__(self, fake):
        self.fake = fake
        self.messages = self

    def stream(self, **payload):
        return _FakeBackedStream(self.fake, payload)

    def create(self, **payload):
        raise AssertionError("the transport streams")


@pytest.fixture
def haiku_paid_env(tmp_path, monkeypatch, r8):
    """R8 in effect; a repo whose frozen PREREG and approval line for block 4-haiku list R8's
    experiments, beside block 1-pilots, approved before the Haiku replication (it lists the
    pilot and validity experiments, not persistgym_haiku); the CLI's own `_guarded_transport`
    building the real Anthropic transport with a fake-backed client; a dummy API key's
    variable; a lock file of its own."""
    guarded_repo(tmp_path, prereg=FROZEN_PREREG, decisions=decisions_text(
        "4-haiku", experiments=(PILOT, VALIDITY, MAIN))
        + approval_line("1-pilots", (PILOT, VALIDITY)) + "\n")
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


def test_an_end_to_end_haiku_pilot(haiku_paid_env, capsys):
    tmp, costs_csv, fakes = haiku_paid_env
    assert cli.main(["run", "--cell", "W-0", "--model", HAIKU, "--split", "pilot", "--n", "1",
                     "--approved-block", "4-haiku", "--planned-usd", "1", "--run-id", "hp",
                     "--parallel", "4"]) == 0
    capsys.readouterr()
    (row,) = costs.read_rows(costs_csv)
    (fake,) = fakes
    assert (row["run_id"], row["experiment"], row["model_requested"]) == ("hp", PILOT, HAIKU)
    assert (row["provider"], row["api"], row["service_tier"], row["service_tier_served"]) == (
        "anthropic", "messages", "standard", "standard")
    assert int(row["n_calls"]) == len(fake.calls) and row["reasoning_tokens"] == ""  # blinded
    assert row["notes"].startswith("approved_block=4-haiku; context_mismatches=n/a; "
                                   "effort_mismatches=n/a;")
    assert "max_prompt_tokens=" in row["notes"] and "parallel=4" in row["notes"]
    assert row["price_source_date"] == "2026-10-17"
    assert all(p["thinking"] == {"type": "adaptive"} and "cache_control" in p
               for p in fake.calls)
    meta = json.loads((tmp / "results" / PILOT / "hp" / "meta.json").read_text(encoding="utf-8"))
    assert meta["exit_reason"] == "COMPLETED" and meta["n_episodes_run"] == 8
    assert meta["api"] == "anthropic.messages"
    assert meta["prompt_size"]["threshold"] == 100_000
    assert 0 < meta["prompt_size"]["max_prompt_tokens"] < 100_000
    assert meta["inference_geos"] == {"global": len(fake.calls)}  # the fake reports global
    assert f"inference_geos=global:{len(fake.calls)}" in row["notes"]
    assert meta["reasoning_context_requested"] is None and meta["tokens"]["reasoning_tokens"] \
        is None
    plan = json.loads((tmp / "raw" / PILOT / "hp" / "run_plan.json").read_text(encoding="utf-8"))
    assert plan["harness_config"]["service_tier"] == "standard"
    assert not (tmp / "lock" / paidlock.lock_name(cli.STREAM)).exists()  # released


def test_a_haiku_pilot_under_a_block_approved_before_r8_refuses(haiku_paid_env, capsys):
    """The guard alone would let it through (block 1-pilots lists persistgym_pilot); the
    Anthropic transport refuses a block that does not list persistgym_haiku, before any
    call, and releases the spend reservation and the lock."""
    tmp, costs_csv, fakes = haiku_paid_env
    assert cli.main(["run", "--cell", "W-0", "--model", HAIKU, "--split", "pilot", "--n", "1",
                     "--approved-block", "1-pilots", "--planned-usd", "1",
                     "--run-id", "hp1"]) == 2
    err = capsys.readouterr().err
    assert "refused: block '1-pilots' lists persistgym_pilot, persistgym_validity, not " \
           "persistgym_haiku" in err
    assert costs.read_rows(costs_csv) == [] and all(not f.calls for f in fakes)
    lock = tmp / "lock" / paidlock.lock_name(cli.STREAM)
    assert not lock.exists()
    assert not paidlock.reservation_path(lock, cli.STREAM).exists()
