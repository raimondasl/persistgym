"""R12's run driver (harnesses/r12_rounds.py) and its committed forecast
(analysis/r12_forecast.py; PREREG §17.12).

* Every command the driver builds from the committed forecast passes R12's guard and block
  rule, as `harnesses run` would check it, and parses as a `harnesses run` command.
* Experiment 1 rotates its 4 arms over 4 rounds of 25 templates: each round plays every arm, and
  each arm goes first in one round.
* The forecast's block limit fits phase 1a's cap, and the decisions log's approval line names it.
* The driver stops at the first run that does not exit 0 and end COMPLETED.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from common import costs
from harnesses import cli, r12_rounds, registered

REPO = Path(__file__).resolve().parents[2]
FORECAST = r12_rounds.latest_forecast(REPO)


def _parse(args):
    return cli.build_parser().parse_args(args)


@pytest.mark.parametrize("part, n", [("pilots", 6), ("notes", 16), ("sonnet", 3), ("block", 4)])
def test_every_command_passes_r12s_guard(tmp_path, part, n):
    cmds = r12_rounds.commands(part, FORECAST)
    assert len(cmds) == n
    for args in cmds:
        a = _parse(args)
        templates = (a.start, a.start + a.n)
        why = registered.check_run_settings(
            a.experiment, a.model, a.effort or registered.registered_effort(a.model), a.cell,
            registered.HAIKU_GENERATOR_HASH, tmp_path, split=a.split, variant="base",
            task_cells=tuple(a.task_cell), templates=templates,
            request={"mode": "standard", "service_tier": "standard", "W": None},
            matrix="full")
        assert why is None, (args, why)
        assert registered.r12_block_refusal(a.approved_block, a.cell, a.experiment,
                                            a.model) is None
        assert a.parallel == 2 and a.planned_usd > 0


def test_experiment_1_rotates_its_arms_over_four_rounds():
    cmds = r12_rounds.commands("notes", FORECAST)
    rounds = [cmds[i:i + 4] for i in range(0, 16, 4)]
    arms = registered.R12_SPECS[registered.R12_NOTES_EXPERIMENT]["cells"]
    firsts = []
    for k, rnd in enumerate(rounds):
        parsed = [_parse(a) for a in rnd]
        assert sorted(p.cell for p in parsed) == sorted(arms)
        assert {(p.start, p.n) for p in parsed} == {(200 + 25 * k, 25)}
        firsts.append(parsed[0].cell)
    assert sorted(firsts) == sorted(arms)


def test_the_block_fits_the_cap_and_the_approval_line_names_it():
    t = FORECAST["totals"]
    spent = costs.spend_by_phase(costs.read_rows())["1a"]
    assert spent + t["block_max_usd"] <= costs.PHASE_CAPS["1a"]
    assert t["block_max_usd"] >= t["high"] + t["pilots"]
    text = (REPO / "results" / "decisions.md").read_text(encoding="utf-8")
    (line,) = [x for x in text.splitlines()
               if x.startswith(f"approved_block: {registered.R12_BLOCK} ")]
    assert line == (f"approved_block: {registered.R12_BLOCK} | experiments: "
                    f"{registered.PILOT_EXPERIMENT},{','.join(registered.R12_EXPERIMENTS)} | "
                    f"max_usd: {t['block_max_usd']}")


def _out(reason):
    """What `harnesses run` prints (harnesses/cli.py cmd_run): an indented JSON object whose
    `cost_usd` is a nested object and `model_returned` a list, after other output."""
    return "episode 3/50 done\n" + json.dumps(
        {"run_id": "x", "exit_reason": reason, "reasoning_context_echoed": None,
         "model_returned": ["claude-haiku-5-5"],
         "cost_usd": {"list": 1.2, "billed_est": 1.2, "costs_csv_row_appended": True}},
        indent=2) + "\n"


def test_exit_reason_reads_the_top_level_object():
    assert r12_rounds.exit_reason(_out("COMPLETED")) == "COMPLETED"
    assert r12_rounds.exit_reason(_out("SPEND_RESERVATION")) == "SPEND_RESERVATION"
    assert r12_rounds.exit_reason(_out("COMPLETED").split("\n", 1)[1]) == "COMPLETED"
    assert r12_rounds.exit_reason("no json here") is None
    assert r12_rounds.exit_reason("") is None


def test_the_driver_stops_at_the_first_run_that_does_not_complete(capsys):
    seen = []
    replies = iter([(0, _out("COMPLETED")), (0, _out("SPEND_RESERVATION")),
                    (0, _out("COMPLETED"))])

    def fake(args):
        seen.append(args)
        return next(replies)

    done, code = r12_rounds.drive([["a"], ["b"], ["c"]], fake)
    assert (done, code) == (1, 2) and seen == [["a"], ["b"]]
    err = capsys.readouterr().err
    assert "tell the researcher" in err and "--from 3" in err
    replies2 = iter([(2, "refused: x"), (0, _out("COMPLETED"))])
    assert r12_rounds.drive([["a"], ["b"]], lambda args: next(replies2)) == (0, 2)
    assert r12_rounds.drive([["a"], ["b"]], lambda args: (0, _out("COMPLETED"))) == (2, 0)


def test_the_driver_resumes_from_a_run():
    seen = []
    done, code = r12_rounds.drive([["a"], ["b"], ["c"]],
                                  lambda args: (seen.append(args), (0, _out("COMPLETED")))[1],
                                  first=2)
    assert (done, code) == (2, 0) and seen == [["b"], ["c"]]


def test_the_driver_never_arms_paid_calls(monkeypatch, capsys):
    """Without PERSISTGYM_ALLOW_PAID the driver refuses before running anything, and it never
    adds the switch to a child's environment."""
    monkeypatch.delenv("PERSISTGYM_ALLOW_PAID", raising=False)
    calls = []
    monkeypatch.setattr(r12_rounds, "drive", lambda *a, **k: calls.append(a) or (0, 0))
    assert r12_rounds.main(["--part", "pilots"]) == 2
    assert calls == [] and "PERSISTGYM_ALLOW_PAID=1" in capsys.readouterr().err
    assert r12_rounds.main(["--part", "pilots", "--from", "7"]) == 2
    envs = []

    def fake_run(argv, **kw):
        envs.append(kw["env"])
        return SimpleNamespace(returncode=0, stdout=_out("COMPLETED"))

    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://example.invalid")
    monkeypatch.setattr(r12_rounds.subprocess, "run", fake_run)
    r12_rounds._paid_subprocess(["run"])
    assert "PERSISTGYM_ALLOW_PAID" not in envs[0] and "ANTHROPIC_BASE_URL" not in envs[0]
