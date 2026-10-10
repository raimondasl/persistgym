"""PREREG §17.4 (amendment R4): the guard lets sol's H1 replication run, and only it.

The replication is gpt-6.1-sol at medium effort on the default generator config, in F-0, W-0
and W-n-0 on the 4 observed task cells: its validity run (`persistgym_validity`, F-0 on the
validity split, restated or withheld; no G1 needed) and its main runs (`persistgym_sol_h1`,
main split, base variant; only after `REPLICATION_G1_PASSED`). R2's and R3's engagement
verdicts and R3's hard stop do not block it, and none of its cases can run F-r, `sol-chain`,
a derived task cell or an effort above medium. Every R2/R3 refusal of sol's H2 runs stays.
Also: the R4 commands in the CLI docstring and in PREREG §17.4 parse, and the guard treats
them as registered."""

from __future__ import annotations

import pytest

from common import costs, paidlock
from harnesses import cli, registered
from harnesses.matrix import RunMatrix
from harnesses.tests.test_registered import (
    DEFAULT,
    LUNA,
    RESULTS,
    SECOND,
    SOL,
    VARIANT,
    _commands,
    _prereg_section,
    _r2_file,
    _write_check,
    armed,  # noqa: F401  (a fixture)
)
from persistgym.episode import ALL_CELLS

OBSERVED = ("observed-nonrec-near", "observed-nonrec-far", "observed-rec-near",
            "observed-rec-far")
DERIVED = tuple(c.id for c in ALL_CELLS if c.fact == "derived")
H1 = "persistgym_sol_h1"
VAL = "persistgym_validity"


REQUEST = {"mode": "standard", "service_tier": "flex", "W": None}       # D13 (§6)


def r4(experiment: str, model: str = SOL, effort: str = "medium", cell: str = "F-0",
       gen: str = DEFAULT, root=None, *, split: str | None = None, variant: str | None = None,
       task_cells=OBSERVED, request=REQUEST, templates=(0, 20)) -> str | None:
    """The guard on an R4 run: the validity run's split and variant in persistgym_validity,
    the main runs' elsewhere, unless given; D13's request settings and templates 0-19."""
    validity = experiment == VAL
    return registered.check_run_settings(
        experiment, model, effort, cell, gen, root if root is not None else RESULTS,
        split=split or ("validity" if validity else "main"),
        variant=variant or ("restated" if validity else "base"),
        task_cells=task_cells, request=request, templates=templates)


def _stop_everything(root) -> None:
    """R2's NOT_ENGAGED file (default config) and an R3 NOT_ENGAGED file on the variant
    (R3's hard stop) under `root`."""
    _r2_file(root)
    _write_check(root, "r3-not", verdict="NOT_ENGAGED")


def test_the_replications_registered_settings():
    assert registered.R4_REF == "PREREG.md §17.4 (amendment R4)"
    assert registered.H1_REPLICATION_EXPERIMENT == H1
    assert (registered.H1_REPLICATION_MODEL, registered.H1_REPLICATION_EFFORT) == (SOL,
                                                                                    "medium")
    assert registered.H1_REPLICATION_GENERATOR_HASH == DEFAULT != VARIANT
    assert registered.H1_REPLICATION_RUN == {"cell": ("F-0", "W-0", "W-n-0"),
                                             "split": ("main",), "variant": ("base",)}
    assert registered.OBSERVED_TASK_CELLS == OBSERVED
    assert registered.H1_REPLICATION_REQUEST == REQUEST
    assert registered.H1_REPLICATION_VALIDITY_TEMPLATES == 20
    assert registered.H1_REPLICATION_PILOT_CELLS == ("W-0", "W-n-0")
    assert registered.REPLICATION_G1_PASSED == {}                       # fails closed
    assert SOL not in registered.G1_PASSED                              # R3's, unchanged
    # its own budget experiment: phase 1a, the PersistGym stream
    assert costs.EXPERIMENT_PHASE[H1] == "1a"
    assert paidlock.EXPERIMENT_STREAM[H1] == paidlock.PERSISTGYM


def test_the_validity_run_needs_no_check_no_g1_and_ignores_the_hard_stop(tmp_path):
    """The replication's validity run goes with no engagement check, with R2's NOT_ENGAGED
    file, after R3's hard stop and with an unreadable check file: none of them concern it."""
    for root_state in ("empty", "stopped", "unreadable"):
        if root_state == "stopped":
            _stop_everything(tmp_path)
            assert registered.hard_stop(tmp_path) is not None
        if root_state == "unreadable":
            bad = tmp_path / "persistgym_pilot" / "bad" / registered.CHECK_FILE
            bad.parent.mkdir(parents=True)
            bad.write_text("{not json", encoding="utf-8")
        for variant in ("restated", "withheld"):
            assert r4(VAL, root=tmp_path, variant=variant) is None
            assert r4(VAL, f"{SOL}-2026-10-01", root=tmp_path, variant=variant) is None
        assert r4(VAL, root=tmp_path, task_cells=OBSERVED[2:]) is None   # a subset
    # while sol's H2 runs stay refused there: the unreadable file, then R3's hard stop
    assert "cannot read the engagement check" in r4(VAL, effort="high", gen=VARIANT,
                                                    root=tmp_path)
    bad.unlink()
    assert registered.HARD_STOP in r4(VAL, effort="high", gen=VARIANT, root=tmp_path)


def test_the_validity_run_is_exactly_registered(tmp_path):
    """In persistgym_validity, sol at medium on the default config is the replication's
    validity run: F-0 on the validity split, restated or withheld, observed task cells."""
    for kwargs in ({"cell": "F-r"}, {"cell": "W-0"}, {"cell": "W-n-0"},
                   {"variant": "base"}, {"split": "main"}, {"split": "pilot"},
                   {"task_cells": OBSERVED + DERIVED}, {"task_cells": DERIVED[:1]},
                   {"task_cells": ()}, {"task_cells": None}):
        why = r4(VAL, root=tmp_path, **kwargs)
        assert "runs sol's H1 replication's validity run only" in why, kwargs
        assert registered.R4_REF in why
    why = r4(VAL, root=tmp_path, task_cells=OBSERVED + DERIVED)
    assert "got task cells observed-nonrec-near" in why and "derived-rec-far" in why
    assert "(none given)" in r4(VAL, root=tmp_path, task_cells=None)
    # other sol validity runs are R3's, with R3's messages (and a pointer to R4's)
    why = r4(VAL, effort="high", root=tmp_path)                          # default at high
    assert "on the generator preset 'sol-chain' only" in why and registered.R4_REF in why
    why = r4(VAL, gen=VARIANT, root=tmp_path)                            # variant at medium
    assert "registered reasoning effort 'high'" in why
    for effort in ("low", "xhigh"):
        assert "registered reasoning effort 'high'" in r4(VAL, effort=effort, root=tmp_path)
    # luna's validity runs are not R4's: luna's own guard refuses them (finished; R6)
    why = r4(VAL, LUNA, root=tmp_path, task_cells=OBSERVED + DERIVED)
    assert "luna's validity runs are finished" in why and registered.R4_REF not in why


def test_the_main_runs_need_the_replications_g1(tmp_path, monkeypatch):
    for cell in ("F-0", "W-0", "W-n-0"):
        why = r4(H1, cell=cell, root=tmp_path)
        assert "REPLICATION_G1_PASSED" in why and registered.R4_REF in why
    monkeypatch.setitem(registered.G1_PASSED, SOL, DEFAULT)              # R3's G1: not it
    assert "REPLICATION_G1_PASSED" in r4(H1, root=tmp_path)
    monkeypatch.setitem(registered.REPLICATION_G1_PASSED, SOL, VARIANT)  # another config
    assert "REPLICATION_G1_PASSED" in r4(H1, root=tmp_path)
    monkeypatch.setitem(registered.REPLICATION_G1_PASSED, SOL, DEFAULT)
    for cell in ("F-0", "W-0", "W-n-0"):
        assert r4(H1, cell=cell, root=tmp_path) is None
        assert r4(H1, f"{SOL}-2026-10-01", cell=cell, root=tmp_path) is None
    assert r4(H1, root=tmp_path, task_cells=OBSERVED[:1]) is None
    # R2's and R3's verdicts and R3's hard stop do not block it
    _stop_everything(tmp_path)
    for cell in ("F-0", "W-0", "W-n-0"):
        assert r4(H1, cell=cell, root=tmp_path) is None


def test_the_main_runs_cannot_run_h2s_contrast_or_anything_else(tmp_path, monkeypatch):
    """With the replication's G1 recorded, persistgym_sol_h1 still refuses F-r, sol-chain,
    derived task cells, efforts above medium, other models, splits and variants."""
    monkeypatch.setitem(registered.REPLICATION_G1_PASSED, SOL, DEFAULT)
    cases = [{"cell": c} for c in ("F-r", "W-n-r", "Σ-n-0", "Σ-n-r", "Σ-0-r")]
    cases += [{"gen": VARIANT}, {"gen": "0" * 64}]
    cases += [{"effort": e} for e in ("high", "xhigh", "max", "low", "minimal", "none")]
    cases += [{"model": m} for m in (LUNA, "gpt-unknown", "gpt-6.1-solar")]
    cases += [{"split": s} for s in ("validity", "pilot")]
    cases += [{"variant": v} for v in ("restated", "withheld", "single_turn")]
    cases += [{"task_cells": t} for t in (DERIVED, OBSERVED + DERIVED, ("derived-rec-far",),
                                           (), None)]
    for kwargs in cases:
        why = r4(H1, root=tmp_path, **kwargs)
        assert why and "runs sol's H1 replication's main runs only" in why, kwargs
    why = r4(H1, cell="F-r", gen=VARIANT, effort="high", root=tmp_path, task_cells=DERIVED)
    for part in ("cell F-r", "--effort high", f"generator config {VARIANT[:12]}",
                 "task cells derived-nonrec-near"):
        assert part in why


def test_the_replications_request_settings_and_validity_templates(tmp_path, monkeypatch):
    """D13's other request settings as frozen (§6: --mode standard, Flex, the episode's own
    W) in both kinds of run, and validity templates 0-19 in the validity run; a guard call
    that does not give them refuses (fail closed)."""
    monkeypatch.setitem(registered.REPLICATION_G1_PASSED, SOL, DEFAULT)
    for experiment, part in ((VAL, "validity run only"), (H1, "main runs only")):
        assert r4(experiment, root=tmp_path) is None
        for request, got in (({**REQUEST, "mode": "pro"}, "--mode pro"),
                             ({**REQUEST, "service_tier": "priority"},
                              "--service-tier priority"),
                             ({**REQUEST, "W": 4000}, "--W 4000"),
                             (None, "(not given)")):
            why = r4(experiment, root=tmp_path, request=request)
            assert part in why and got in why, (experiment, request)
    for templates in ((0, 20), (0, 1), (10, 20), (19, 20)):
        assert r4(VAL, root=tmp_path, templates=templates) is None
    for templates, got in (((0, 21), "templates 0-20"), ((20, 40), "templates 20-39"),
                           ((30, 50), "templates 30-49"), (None, "(not given)")):
        why = r4(VAL, root=tmp_path, templates=templates)
        assert "validity run only" in why and got in why, templates
    assert r4(H1, root=tmp_path, templates=(100, 200)) is None   # main templates: any (T)
    assert r4(H1, root=tmp_path, templates=None) is None


def test_the_replication_opens_nothing_of_h2(tmp_path, monkeypatch):
    """Recording the replication's G1 lets no H2 run of sol go: `persistgym` on the default
    config at medium or high, or on the variant without R3's own check and G1, refuses as
    before; and R3's G1 never lets the replication go."""
    monkeypatch.setitem(registered.REPLICATION_G1_PASSED, SOL, DEFAULT)
    for experiment in ("persistgym", "statecarry_persistgym"):
        why = r4(experiment, root=tmp_path)
        assert "registered reasoning effort 'high'" in why and registered.R4_REF in why
        assert "preset 'sol-chain' only" in r4(experiment, effort="high", root=tmp_path)
        assert "need an ENGAGED engagement check" in r4(
            experiment, effort="high", gen=VARIANT, root=tmp_path, cell="F-r")
    _write_check(tmp_path, "r3")                                         # R3: ENGAGED
    assert "G1_PASSED" in r4("persistgym", effort="high", gen=VARIANT, root=tmp_path,
                             cell="F-r")
    monkeypatch.setitem(registered.G1_PASSED, SOL, VARIANT)
    assert r4("persistgym", effort="high", gen=VARIANT, root=tmp_path, cell="F-r") is None
    # an UNSCORABLE R3 check twice is the hard stop for H2, not for the replication
    for p in (tmp_path / "persistgym_pilot").glob(f"*/{registered.CHECK_FILE}"):
        p.unlink()
    _write_check(tmp_path, "a", verdict="UNSCORABLE")
    _write_check(tmp_path, "b", verdict="UNSCORABLE", check_templates=SECOND)
    assert registered.HARD_STOP in r4("persistgym", effort="high", gen=VARIANT, root=tmp_path,
                                      cell="F-r")
    assert r4(H1, root=tmp_path) is None and r4(VAL, root=tmp_path) is None


def test_the_repositorys_own_state():
    """With this checkout's results/ (R2's NOT_ENGAGED file on the default config, and R3's
    NOT_ENGAGED file on the variant: R3's hard stop): the replication's validity run may go,
    its main runs wait for its G1, and sol's H2 runs stay refused on both configs."""
    assert registered.HARD_STOP in registered.hard_stop(RESULTS)
    assert r4(VAL) is None
    assert "REPLICATION_G1_PASSED" in r4(H1)
    assert "does not engage" in registered.engagement_refusal(RESULTS, SOL, DEFAULT)
    assert registered.HARD_STOP in r4(VAL, effort="high", gen=VARIANT)
    assert registered.HARD_STOP in r4("persistgym", effort="high", gen=VARIANT, cell="F-r",
                                      split="main", variant="base")


# --- the run command ------------------------------------------------------------------------

def test_run_passes_the_matrix_task_cells_to_the_guard(armed, capsys, monkeypatch):  # noqa: F811
    """`run` gives the guard the task cells its matrix plays (with at least one template):
    the default --task-cell all refuses for the replication, the observed cells go on to the
    paid path, and a --cell-templates matrix counts only its cells with templates."""
    reached = []

    def paid_path(run_id, what, body):
        reached.append(what)
        return 0
    monkeypatch.setattr(cli, "_with_paid_lock", paid_path)
    base = ["run", "--cell", "F-0", "--model", SOL, "--effort", "medium", "--split",
            "validity", "--variant", "restated", "--experiment", VAL, "--approved-block",
            "1-pilots", "--planned-usd", "1"]
    assert cli.main([*base, "--n", "1"]) == 2                            # all 8 task cells
    assert "got task cells observed-nonrec-near" in capsys.readouterr().err
    assert cli.main([*base, "--n", "1", "--task-cell", *OBSERVED]) == 0
    assert reached == [f"{VAL}: F-0 on {SOL}, 4 episodes"]
    custom = [f"{c}=1" for c in OBSERVED] + [f"{c}=0" for c in DERIVED]
    assert cli.main([*base, "--cell-templates", *custom]) == 0           # 0 templates: none
    assert cli.main([*base, "--cell-templates", *custom[:-1], f"{DERIVED[-1]}=1"]) == 2
    assert "derived-rec-far" in capsys.readouterr().err
    main = ["run", "--cell", "W-n-0", "--model", SOL, "--effort", "medium", "--split", "main",
            "--n", "10", "--task-cell", *OBSERVED, "--experiment", H1, "--approved-block",
            "3-persistgym", "--planned-usd", "1"]
    assert cli.main(main) == 2
    assert "REPLICATION_G1_PASSED" in capsys.readouterr().err
    monkeypatch.setitem(registered.REPLICATION_G1_PASSED, SOL, DEFAULT)
    assert cli.main(main) == 0
    assert reached[-1] == f"{H1}: W-n-0 on {SOL}, 40 episodes"
    # without --effort medium, sol's registered effort (high) is sent, and it refuses
    no_effort = [a for a in main if a not in ("--effort", "medium")]
    assert cli.main(no_effort) == 2
    assert "--effort high" in capsys.readouterr().err
    # the request settings `run` sends, and the validity run's templates, reach the guard
    for extra, got in ((["--mode", "pro"], "--mode pro"),
                       (["--service-tier", "priority"], "--service-tier priority"),
                       (["--W", "4000"], "--W 4000")):
        assert cli.main([*main, *extra]) == 2
        assert got in capsys.readouterr().err
    validity = [*base, "--task-cell", *OBSERVED]
    assert cli.main([*validity, "--n", "20"]) == 0
    assert cli.main([*validity, "--start", "19", "--n", "1"]) == 0
    for extra, got in ((["--n", "21"], "templates 0-20"),
                       (["--start", "30", "--n", "20"], "templates 30-49")):
        assert cli.main([*validity, *extra]) == 2
        assert got in capsys.readouterr().err


@pytest.mark.parametrize(("args", "message"), [
    (["--experiment", VAL, "--split", "validity", "--variant", "restated", "--cell", "F-0"],
     "got task cells observed-nonrec-near"),                           # --task-cell all
    (["--experiment", VAL, "--split", "validity", "--variant", "restated", "--cell", "F-r",
      "--task-cell", *OBSERVED], "got cell F-r"),
    (["--experiment", H1, "--split", "main", "--cell", "W-0", "--task-cell", *OBSERVED,
      "--gen-preset", "sol-chain"], "got generator config"),
    (["--experiment", H1, "--split", "main", "--cell", "W-0", "--task-cell", *DERIVED],
     "got task cells derived-nonrec-near"),
    (["--experiment", H1, "--split", "main", "--cell", "F-0", "--task-cell", *OBSERVED],
     "REPLICATION_G1_PASSED")])
def test_r4_refuses_before_the_lock(armed, capsys, args, message):  # noqa: F811
    assert cli.main(["run", "--model", SOL, "--effort", "medium", "--n", "1",
                     "--approved-block", "1-pilots", "--planned-usd", "1", *args]) == 2
    err = capsys.readouterr().err
    assert err.startswith("refused:") and message in err


# --- command examples ---------------------------------------------------------------------------

def _r4_commands(text: str) -> dict[str, list[str]]:
    """The R4 `run` commands in `text` (sol at --effort medium on the default config), by
    experiment."""
    out: dict[str, list[list[str]]] = {}
    for argv in _commands(text):
        if argv[0] == "run" and SOL in argv and "medium" in argv and "sol-chain" not in argv:
            out.setdefault(cli.parse_args(argv).experiment, []).append(argv)
    return out


def _check_r4_commands(commands: dict[str, list[list[str]]], monkeypatch) -> None:
    """The pilot, validity and main commands: their settings, their episodes, and the guard
    (with this checkout's results/): the pilot and validity runs go, the main run waits for
    the replication's G1 and then goes."""
    (pilot,) = commands["persistgym_pilot"]
    (validity,) = commands[VAL]
    (main,) = commands[H1]
    expected = {"persistgym_pilot": ("W-0", "pilot", 0, 2, "base", "1-pilots"),
                VAL: ("F-0", "validity", 0, 20, "restated", "1-pilots"),
                H1: ("F-0", "main", 0, 100, "base", "3-persistgym")}
    for argv in (pilot, validity, main):
        a = cli.parse_args(argv)
        assert (a.cell, a.split, a.start, a.n, a.variant, a.approved_block) == expected[
            a.experiment]
        assert (a.model, a.effort, a.gen_preset, a.gen_set) == (SOL, "medium", "default", [])
        assert sorted(a.task_cell) == sorted(OBSERVED)
        matrix = cli._run_matrix(a)
        cfg = cli._gen_config(a.gen_preset, a.gen_set)
        eps = matrix.episodes(a.split, a.start, cfg, a.variant) if a.n <= 20 else None
        n = {"persistgym_pilot": 8, VAL: 80, H1: 400}[a.experiment]
        assert matrix.n_episodes == n
        if eps is not None:
            assert {e.config_hash for e in eps} == {DEFAULT}
            assert {e.cell.id for e in eps} == set(OBSERVED)
        assert matrix == RunMatrix.full(a.n, list(OBSERVED))
        assert (a.mode, a.service_tier, a.W) == ("standard", "flex", None)
        why = registered.check_run_settings(
            a.experiment, a.model, a.effort, a.cell, DEFAULT, RESULTS, split=a.split,
            variant=a.variant, task_cells=tuple(c for c, k in matrix.templates if k),
            request={"mode": a.mode, "service_tier": a.service_tier, "W": a.W},
            templates=(a.start, a.start + matrix.n_templates))
        if a.experiment == H1:
            assert "REPLICATION_G1_PASSED" in why
        else:
            assert why is None, why
    assert cli.parse_args(main).parallel == 16
    monkeypatch.setitem(registered.REPLICATION_G1_PASSED, SOL, DEFAULT)
    a = cli.parse_args(main)
    assert registered.check_run_settings(
        a.experiment, a.model, a.effort, a.cell, DEFAULT, RESULTS, split=a.split,
        variant=a.variant, task_cells=OBSERVED, request=REQUEST) is None


def test_the_cli_docstrings_r4_commands(monkeypatch):
    _check_r4_commands(_r4_commands(cli.__doc__), monkeypatch)


def test_prereg_r4s_commands(monkeypatch):
    text = _prereg_section("### 17.4 Amendment R4")
    _check_r4_commands(_r4_commands(text), monkeypatch)
    # its other commands parse too, and none of them runs H2's contrast
    for argv in _commands(text):
        a = cli.parse_args(argv)
        if a.cmd == "run":
            assert a.cell in ("F-0", "W-0", "W-n-0") and a.gen_preset == "default"


@pytest.mark.parametrize("heading", ["### 17.2 Amendment R2", "### 17.3 Amendment R3"])
def test_r2_and_r3_sections_are_unchanged_in_what_they_register(heading):
    """R4 adds a section; R2's and R3's rules stay as their sections state them."""
    text = _prereg_section(heading)
    assert "E ≥ 0.50" in text and "persistgym_sol_h1" not in text
