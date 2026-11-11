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
    return json.dumps({"run_id": "x", "exit_reason": reason}, indent=2)


def test_the_driver_stops_at_the_first_run_that_does_not_complete(capsys):
    seen = []
    replies = iter([(0, _out("COMPLETED")), (0, _out("SPEND_RESERVATION")), (0, _out("COMPLETED"))])

    def fake(args):
        seen.append(args)
        return next(replies)

    done, code = r12_rounds.drive([["a"], ["b"], ["c"]], fake)
    assert (done, code) == (1, 2) and seen == [["a"], ["b"]]
    assert "tell the researcher" in capsys.readouterr().err
    replies2 = iter([(2, "refused: x"), (0, _out("COMPLETED"))])
    assert r12_rounds.drive([["a"], ["b"]], lambda args: next(replies2)) == (0, 2)
    assert r12_rounds.drive([["a"], ["b"]], lambda args: (0, _out("COMPLETED"))) == (2, 0)


def test_exit_reason_reads_the_last_json():
    assert r12_rounds.exit_reason("noise\n" + _out("COMPLETED")) == "COMPLETED"
    assert r12_rounds.exit_reason("no json here") is None
