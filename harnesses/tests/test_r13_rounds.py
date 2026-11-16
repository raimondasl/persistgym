"""R13's run driver (harnesses/r13_rounds.py; PREREG §17.13), on a fake forecast in R12's
forecast schema: R13 is prepared, not run, so no forecast of it need be committed yet.

* Every command the driver builds passes R13's guard and block rule, as `harnesses run` would
  check it, and parses as a `harnesses run` command, in plain ASCII (Σ-n-0 as sigma-n-0).
* The pilots play Σ-n-0 on 1 template of the 8 task cells and W-nk-0 on 2 templates of the 2
  not-recoverable far ones; experiment 4 plays 4 runs of 50 templates; experiment 5 plays 4
  rounds of 25 templates, both arms a round, W-nk-0 first in rounds 1 and 3 and W-n-0 first in
  rounds 2 and 4. A forecast whose runs differ from these, or come in another order, refuses.
* The driver stops at the first run that does not exit 0 and end COMPLETED, resumes with
  --from, refuses without PERSISTGYM_ALLOW_PAID before running anything, and never sets it.
"""

from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from harnesses import cli, r13_rounds, registered
from harnesses.cells import get_cell

HAIKU = "claude-haiku-5-5"
SIGMA_X = "persistgym_haiku_r13_sigma"
PINNED_X = "persistgym_haiku_r13_pinned"
ALL8 = registered.HAIKU_TASK_CELLS
TWO = ("observed-nonrec-far", "derived-nonrec-far")
REQUEST = {"mode": "standard", "service_tier": "standard", "W": None}


def _run(experiment, cell, start, n, planned):
    return {"experiment": experiment, "model": HAIKU, "cell": cell,
            "templates": [start, start + n], "episodes": n * (8 if experiment == SIGMA_X else 2),
            "low_usd": planned / 1.5, "high_usd": planned / 1.25, "planned_usd": planned,
            "most_one_send_usd": 0.14}


FORECAST = {
    "prereg": "PREREG.md §17.13 (amendment R13)",
    "pilots": [{"model": HAIKU, "cell": "Σ-n-0", "episodes": 8, "planned_usd": 1.17},
               {"model": HAIKU, "cell": "W-nk-0", "episodes": 4, "planned_usd": 0.83}],
    # in run order, written out here rather than from registered.r13_round_arms
    "runs": [_run(SIGMA_X, "Σ-n-0", s, 50, 6.0 + s / 100) for s in (0, 50, 100, 150)] + [
        _run(PINNED_X, cell, 200 + 25 * k, 25, round(2.5 + k / 10 + (cell == "W-nk-0") / 100, 2))
        for k, arms in enumerate((("W-nk-0", "W-n-0"), ("W-n-0", "W-nk-0"),
                                  ("W-nk-0", "W-n-0"), ("W-n-0", "W-nk-0")))
        for cell in arms],
    "totals": {"low": 30.0, "high": 40.0, "stops": 50.0, "one_send": 0.5, "pilots": 2.0,
               "block_max_usd": 46},
}


def _parse(args):
    return cli.build_parser().parse_args(args)


@pytest.mark.parametrize("part, n", [("pilots", 2), ("sigma", 4), ("pinned", 8)])
def test_every_command_passes_r13s_guard(tmp_path, part, n):
    cmds = r13_rounds.commands(part, FORECAST)
    assert len(cmds) == n
    for args in cmds:
        assert all(x.isascii() for x in args), args
        a = _parse(args)
        cell = get_cell(a.cell).cell_id
        why = registered.check_run_settings(
            a.experiment, a.model, a.effort or registered.registered_effort(a.model), cell,
            registered.HAIKU_GENERATOR_HASH, tmp_path, split=a.split, variant="base",
            task_cells=tuple(a.task_cell), templates=(a.start, a.start + a.n),
            request=REQUEST, matrix="full")
        assert why is None, (args, why)
        assert a.approved_block == registered.R13_BLOCK == "9-r13"
        assert registered.r13_block_refusal(a.approved_block, cell, a.experiment, a.model) is None
        assert registered.r12_block_refusal(a.approved_block, cell, a.experiment, a.model) is None
        assert registered.provenance_block_refusal(a.approved_block, cell,
                                                   experiment=a.experiment,
                                                   model=a.model) is None
        assert a.parallel == 2 and a.planned_usd > 0


def test_the_pilots_play_their_registered_sizes():
    sigma, pinned = (_parse(a) for a in r13_rounds.commands("pilots", FORECAST))
    assert (sigma.cell, sigma.experiment, sigma.split, sigma.start, sigma.n) == (
        "sigma-n-0", "persistgym_pilot", "pilot", 0, 1)
    assert tuple(sigma.task_cell) == ALL8 and sigma.planned_usd == 1.17
    assert (pinned.cell, pinned.split, pinned.start, pinned.n) == ("W-nk-0", "pilot", 0, 2)
    assert tuple(pinned.task_cell) == TWO and pinned.planned_usd == 0.83


def test_experiment_4_plays_four_runs_of_50_templates():
    parsed = [_parse(a) for a in r13_rounds.commands("sigma", FORECAST)]
    assert [(p.cell, p.start, p.n) for p in parsed] == [
        ("sigma-n-0", 0, 50), ("sigma-n-0", 50, 50), ("sigma-n-0", 100, 50),
        ("sigma-n-0", 150, 50)]
    assert all(tuple(p.task_cell) == ALL8 and p.experiment == SIGMA_X for p in parsed)
    assert [p.planned_usd for p in parsed] == [6.0, 6.5, 7.0, 7.5]


def test_experiment_5_alternates_its_arms_over_four_rounds():
    parsed = [_parse(a) for a in r13_rounds.commands("pinned", FORECAST)]
    rounds = [parsed[i:i + 2] for i in range(0, 8, 2)]
    for k, rnd in enumerate(rounds):
        assert {(p.start, p.n) for p in rnd} == {(200 + 25 * k, 25)}
        assert all(tuple(p.task_cell) == TWO and p.experiment == PINNED_X for p in rnd)
    assert [[p.cell for p in rnd] for rnd in rounds] == [
        ["W-nk-0", "W-n-0"], ["W-n-0", "W-nk-0"], ["W-nk-0", "W-n-0"], ["W-n-0", "W-nk-0"]]
    # each run's stop is the forecast's, run by run
    assert [p.planned_usd for p in parsed] == [r["planned_usd"] for r in FORECAST["runs"][4:]]


def test_the_planned_runs_are_r13s():
    assert r13_rounds.planned_runs("sigma") == [("Σ-n-0", s, 50) for s in (0, 50, 100, 150)]
    assert r13_rounds.planned_runs("pinned") == [
        ("W-nk-0", 200, 25), ("W-n-0", 200, 25), ("W-n-0", 225, 25), ("W-nk-0", 225, 25),
        ("W-nk-0", 250, 25), ("W-n-0", 250, 25), ("W-n-0", 275, 25), ("W-nk-0", 275, 25)]


def _swap_runs(f, i, j):
    f["runs"][i], f["runs"][j] = f["runs"][j], f["runs"][i]


@pytest.mark.parametrize("part, change, wrong", [
    ("pinned", lambda f: _swap_runs(f, 6, 7), "not R13's"),  # round 4 out of turn
    ("pinned", lambda f: _swap_runs(f, 4, 6), "not R13's"),  # two rounds swapped
    ("pinned", lambda f: f["runs"].pop(), "not R13's"),  # a round short
    ("pinned", lambda f: f["runs"][5].update(templates=[225, 251]), "not R13's"),
    ("pinned", lambda f: f["runs"][5].update(cell="W-np-0"), "not R13's"),
    ("sigma", lambda f: _swap_runs(f, 0, 1), "not R13's"),
    ("sigma", lambda f: f["runs"].append(_run(SIGMA_X, "Σ-n-0", 0, 50, 6.0)), "not R13's"),
    ("pilots", lambda f: f["pilots"].pop(), "not R13's"),
    ("pilots", lambda f: f["pilots"].append({"model": HAIKU, "cell": "W-n-0", "episodes": 4,
                                             "planned_usd": 0.8}), "not R13's"),
    ("pilots", lambda f: f["pilots"][0].update(episodes=16), "prices 16 episodes"),
])
def test_a_forecast_that_is_not_r13s_refuses(monkeypatch, capsys, part, change, wrong):
    f = copy.deepcopy(FORECAST)
    change(f)
    with pytest.raises(ValueError, match=wrong):
        r13_rounds.commands(part, f)
    monkeypatch.setattr(r13_rounds, "latest_forecast", lambda root=None: f)
    assert r13_rounds.main(["--part", part, "--dry-run"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("refused:") and "nothing was run" in err


def test_the_dry_run_prints_the_commands_from_a_run(monkeypatch, capsys):
    monkeypatch.setattr(r13_rounds, "latest_forecast", lambda root=None: FORECAST)
    assert r13_rounds.main(["--part", "pinned", "--dry-run"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [x.split("]")[0] for x in lines] == [f"[{i}/8" for i in range(1, 9)]
    assert all("--approved-block 9-r13 " in x and x.isascii() for x in lines)
    assert r13_rounds.main(["--part", "pinned", "--dry-run", "--from", "7"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2 and lines[0].startswith("[7/8] harnesses run --cell W-n-0 ")
    for bad in ("0", "9"):
        assert r13_rounds.main(["--part", "pinned", "--dry-run", "--from", bad]) == 2
        assert "--from is 1 to 8 for part pinned" in capsys.readouterr().err


def test_the_latest_forecast(tmp_path):
    with pytest.raises(SystemExit, match="no forecast under"):
        r13_rounds.latest_forecast(tmp_path)
    folder = tmp_path / "results" / "r13_forecast"
    for name, doc in (("20261116T000000Z", {"n": 1}), ("20261117T000000Z", {"n": 2})):
        (folder / name).mkdir(parents=True)
        (folder / name / "forecast.json").write_text(json.dumps(doc), encoding="utf-8")
    (folder / "20261118T000000Z").mkdir()  # no forecast.json: not a forecast
    assert r13_rounds.latest_forecast(tmp_path) == {"n": 2}


def _out(reason):
    """What `harnesses run` prints (harnesses/cli.py cmd_run): an indented JSON object whose
    `cost_usd` is a nested object and `model_returned` a list, after other output."""
    return "episode 3/50 done\n" + json.dumps(
        {"run_id": "x", "exit_reason": reason, "reasoning_context_echoed": None,
         "model_returned": ["claude-haiku-5-5"],
         "cost_usd": {"list": 1.2, "billed_est": 1.2, "costs_csv_row_appended": True}},
        indent=2) + "\n"


def test_exit_reason_reads_the_top_level_object():
    assert r13_rounds.exit_reason(_out("COMPLETED")) == "COMPLETED"
    assert r13_rounds.exit_reason(_out("SPEND_RESERVATION")) == "SPEND_RESERVATION"
    assert r13_rounds.exit_reason(_out("COMPLETED").split("\n", 1)[1]) == "COMPLETED"
    assert r13_rounds.exit_reason("no json here") is None
    assert r13_rounds.exit_reason("") is None


def test_the_driver_stops_at_the_first_run_that_does_not_complete(capsys):
    seen = []
    replies = iter([(0, _out("COMPLETED")), (0, _out("SPEND_RESERVATION")),
                    (0, _out("COMPLETED"))])

    def fake(args):
        seen.append(args)
        return next(replies)

    done, code = r13_rounds.drive([["a"], ["b"], ["c"]], fake)
    assert (done, code) == (1, 2) and seen == [["a"], ["b"]]
    err = capsys.readouterr().err
    assert "tell the researcher" in err and "--from 3" in err
    replies2 = iter([(2, "refused: x"), (0, _out("COMPLETED"))])
    assert r13_rounds.drive([["a"], ["b"]], lambda args: next(replies2)) == (0, 2)
    assert r13_rounds.drive([["a"], ["b"]], lambda args: (0, _out("COMPLETED"))) == (2, 0)


def test_the_driver_resumes_from_a_run():
    seen = []
    done, code = r13_rounds.drive([["a"], ["b"], ["c"]],
                                  lambda args: (seen.append(args), (0, _out("COMPLETED")))[1],
                                  first=2)
    assert (done, code) == (2, 0) and seen == [["b"], ["c"]]


def test_the_driver_never_arms_paid_calls(monkeypatch, capsys):
    """Without PERSISTGYM_ALLOW_PAID the driver refuses before running anything, and it never
    adds the switch to a child's environment or its own."""
    monkeypatch.delenv("PERSISTGYM_ALLOW_PAID", raising=False)
    monkeypatch.setattr(r13_rounds, "latest_forecast", lambda root=None: FORECAST)
    calls = []
    monkeypatch.setattr(r13_rounds, "drive", lambda *a, **k: calls.append(a) or (0, 0))
    for part in r13_rounds.PARTS:
        assert r13_rounds.main(["--part", part]) == 2
        assert r13_rounds.main(["--part", part, "--from", "2"]) == 2
    assert calls == [] and "PERSISTGYM_ALLOW_PAID=1" in capsys.readouterr().err
    assert r13_rounds.main(["--part", "pilots", "--from", "3"]) == 2
    envs = []

    def fake_run(argv, **kw):
        envs.append(kw["env"])
        return SimpleNamespace(returncode=0, stdout=_out("COMPLETED"))

    monkeypatch.setattr(r13_rounds.subprocess, "run", fake_run)
    r13_rounds._paid_subprocess(["run"])
    assert "PERSISTGYM_ALLOW_PAID" not in envs[0] and "PERSISTGYM_ALLOW_PAID" not in os.environ
    assert {k: v for k, v in envs[0].items() if k != "PYTHONIOENCODING"} == {
        k: v for k, v in os.environ.items() if k != "PYTHONIOENCODING"}
    # the source reads the switch and writes no environment variable
    src = Path(r13_rounds.__file__).read_text(encoding="utf-8")
    assert not re.search(r"environ\[[^\]]*\]\s*=|putenv|setdefault|environ\.update", src)
    assert src.count("ALLOW_ENV") == 3  # the import, the read and the refusal's text


# --- the cap: a part starts only if the stops of all its runs left fit ----------------------

def _ledger(spent_1a: float) -> list[dict]:
    """A ledger whose only row puts `spent_1a` in phase 1a (R8's experiment)."""
    from common import costs
    return [{**{c: "" for c in costs.COLUMNS}, "experiment": "persistgym_haiku",
             "cost_usd_list": f"{spent_1a:.2f}", "cost_usd_billed_est": f"{spent_1a:.2f}"}]


# The fake forecast's stops: pilots $2.00, experiment 4 $27.00 (6.0 + 6.5 + 7.0 + 7.5) and
# experiment 5 $21.24 (rounds 1-2: 2.51 + 2.50 + 2.60 + 2.61; rounds 3-4: 2.71 + 2.70 + 2.80
# + 2.81, so $11.02 from its 5th run on). A $600 ledger leaves $20.00 of the $620 cap.
@pytest.mark.parametrize("part, first, refused", [
    ("pilots", 1, False), ("sigma", 1, True), ("sigma", 3, False), ("pinned", 1, True),
    ("pinned", 5, False)])
def test_a_part_whose_stops_do_not_fit_in_the_cap_refuses(part, first, refused):
    from common import costs
    assert costs.PHASE_CAPS["1a"] == 620.0
    cmds = r13_rounds.commands(part, FORECAST)[first - 1:]
    why = r13_rounds.cap_refusal(cmds, _ledger(600.0))
    if refused:
        need = {"sigma": 27.0, "pinned": 21.24}[part]
        assert why == (f"the part's {len(cmds)} runs left need ${need:.2f} by their stops and "
                       "phase 1a's cap ($620.00, common/costs.py) leaves $20.00: the pull "
                       "request that approves block 9-r13 also raises the cap (PREREG §17.13, "
                       "Budget)")
    else:
        assert why is None
    # every part fits in an empty phase, and nothing fits in a full one
    assert r13_rounds.cap_refusal(cmds, _ledger(0.0)) is None
    assert r13_rounds.cap_refusal(cmds, _ledger(620.0)) is not None


def test_a_stop_exactly_at_the_cap_fits():
    cmds = r13_rounds.commands("pinned", FORECAST)[4:]  # $11.02
    assert r13_rounds.cap_refusal(cmds, _ledger(608.98)) is None
    assert r13_rounds.cap_refusal(cmds, _ledger(608.99)) is not None


def test_an_experiment_with_no_phase_refuses():
    args = r13_rounds.commands("pilots", FORECAST)[0]
    bad = list(args)
    bad[bad.index("--experiment") + 1] = "persistgym_unknown"
    assert "has no phase cap" in r13_rounds.cap_refusal([bad], _ledger(0.0))


def test_main_checks_the_cap_after_the_switch_and_before_any_run(monkeypatch, capsys):
    """With a test-only switch name (the real PERSISTGYM_ALLOW_PAID is never set), a part
    whose stops do not fit refuses before `drive`, and one that fits reaches it."""
    monkeypatch.setattr(r13_rounds, "ALLOW_ENV", "R13_ROUNDS_TEST_SWITCH")
    monkeypatch.setenv("R13_ROUNDS_TEST_SWITCH", "1")
    monkeypatch.setattr(r13_rounds, "latest_forecast", lambda root=None: FORECAST)
    monkeypatch.setattr(r13_rounds.costs, "read_rows", lambda *a, **k: _ledger(600.0))
    calls = []
    monkeypatch.setattr(r13_rounds, "drive",
                        lambda cmds, first=1: calls.append((len(cmds), first)) or (0, 0))
    assert r13_rounds.main(["--part", "pinned"]) == 2
    err = capsys.readouterr().err
    assert "the part's 8 runs left need $21.24" in err and "nothing was run" in err
    assert calls == []
    assert r13_rounds.main(["--part", "pinned", "--from", "5"]) == 0
    assert calls == [(8, 5)]
    assert "PERSISTGYM_ALLOW_PAID" not in os.environ
