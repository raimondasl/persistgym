"""Checkpoint C metrics (analysis/checkpoint_c.py; PREREG §10.3): each rule firing and not
firing, re-run replacement, D19/D20 and TIME_BUDGET, the refusals of an incomplete or
inconsistent block 2, the 3-game fallback (D32) and the output allowlist.

Every run here is synthetic, in a results root built under tmp_path, except the last test,
which runs the script on this checkout's own results/ (whatever block-2 folders are committed)
to check that a PROVISIONAL reading does not crash."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime, timedelta

import pytest

from analysis import arc_action_matched as am
from analysis import checkpoint_c as cc
from common import costs

GAMES = ["FT09", "SB26", "R11L", "CD82"]
DROP = "CD82"
GIT = {"git_commit": "0" * 40, "git_dirty": False}
BASELINES = (10, 20, 30)
PILOT = {"S0": 80.0, "S1": 100.0, "S2": 95.0, "S4": 20.0}
G0_B = {"S0": 0.5, "S1": 0.6, "S2": 0.7, "S4": 0.8}
G0_L = {"L_S0": 20.0, "L_S4": 10.0, "L_midpoint": 15.0}


def _card(level_actions, levels_completed, baselines=BASELINES, extra=None):
    scores = [am.level_score(b, a, i < levels_completed)
              for i, (b, a) in enumerate(zip(baselines, level_actions, strict=True))]
    play = {"score": am.game_score(scores), "levels_completed": levels_completed,
            "actions": sum(level_actions), "resets": 0, "level_scores": scores,
            "level_actions": list(level_actions), "level_baseline_actions": list(baselines)}
    env = {"id": "g", "runs": [play], "level_count": len(baselines)}
    return {"score": play["score"], "environments": [env], **(extra or {})}


# S4 wins every level at the baseline (RHAE 100, 60 actions); S0 clears level 1 in twice its
# baseline and stops (RHAE 25 × 1/6 = 4.1667, 120 actions).
WIN = {"ending": "GAME_WIN", "level_actions": (10, 20, 30), "levels_completed": 3}
BUDGET = {"ending": "ACTION_BUDGET", "level_actions": (20, 40, 60), "levels_completed": 1}
RHAE_WIN, RHAE_BUDGET = 100.0, 25 / 6


class Fixture:
    """A results root: arc_path run folders, costs.csv, a G0 record and a draw."""

    def __init__(self, tmp_path, games=GAMES, drop=DROP):
        self.root = tmp_path / "results"
        (self.root / "arc_path").mkdir(parents=True)
        self.clock = datetime(2026, 10, 6, tzinfo=UTC)
        self.rows: list[dict] = [
            {"run_id": f"pilot-{c}", "experiment": "arc_pilot", "cell_or_config": c,
             "latency_s": str(v), "cost_usd_list": "1.0", "cost_usd_billed_est": "0.8",
             "notes": "approved_block=1-pilots;"} for c, v in PILOT.items()]
        perm = [g for g in games if g != drop] + [drop]          # D32: drop = perm[3]
        draw = {"games": games, "derived": {"perm": perm, "fallback_drop_game_d32": drop}}
        self._json(self.root / "draw" / "20261002T033145Z" / "draw.json", draw)
        g0 = {"cost": {"b": G0_B, "games": [{"game": g, **G0_L} for g in games]}}
        self._json(self.root / "gates" / "g0-20261006T133152Z" / "g0.json", g0)
        self.write_costs()

    @staticmethod
    def _json(path, obj):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj), encoding="utf-8")

    def write_costs(self):
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=costs.COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in self.rows:
            w.writerow({**dict.fromkeys(costs.COLUMNS, ""), **r})
        (self.root / "costs.csv").write_text(buf.getvalue(), encoding="utf-8")

    def run(self, game, config, *, ending, level_actions, levels_completed, seed=1,
            rerun_of=None, billed=10.0, n_calls=100, median=50.0, wall=3600.0, card=True,
            experiment="arc_path", meta_extra=None, card_extra=None, row=True, tag=True):
        self.clock += timedelta(hours=1)
        run_id = f"{self.clock:%Y%m%dT%H%M%SZ}-{config}-{game.lower()}-s{seed}"
        d = self.root / "arc_path" / run_id
        d.mkdir()
        meta = {"experiment": experiment, "run_id": run_id, "cell_or_config": config,
                "game_requested": game.lower(), "seeds": {"replicate_seed": seed},
                "rerun_of": rerun_of, "agent_exit_reason": ending, "exit_reason": ending,
                "started_utc": self.clock.isoformat(timespec="seconds"),
                "wall_clock_s": wall, "n_calls": n_calls,
                "latency": {"n_ok_calls": n_calls, "median_s": median},
                "cost_usd": {"list": billed * 1.2, "billed_est": billed},
                "truncation_limits": {"max_actions": None, "after_summary_turns": None},
                **(meta_extra or {})}
        self._json(d / "meta.json", meta)
        if card:
            self._json(d / "scorecard.json", _card(level_actions, levels_completed,
                                                   extra=card_extra))
        if row:
            self.rows.append({"run_id": run_id, "experiment": experiment,
                              "cell_or_config": config, "n_calls": str(n_calls),
                              "latency_s": str(median), "cost_usd_list": str(billed * 1.2),
                              "cost_usd_billed_est": str(billed),
                              "notes": (f"approved_block={cc.BLOCK};" if tag else "x;")
                              + " arc_run=..."})
            self.write_costs()
        return run_id

    def block(self, games=GAMES, s0=BUDGET, s4=WIN, s0_billed=10.0, s4_billed=5.0,
              s0_median=50.0, s4_median=10.0):
        """The 8 seed-1 runs, S4 then S0 per game; returns {(game, config): run_id}."""
        ids = {}
        for g in games:
            ids[(g, "S4")] = self.run(g, "S4", billed=s4_billed, median=s4_median, **s4)
            ids[(g, "S0")] = self.run(g, "S0", billed=s0_billed, median=s0_median, **s0)
        return ids

    def compute(self):
        return cc.compute(self.root, "now", GIT)

    def main(self, *args):
        return cc.main(["--results-root", str(self.root), *args])


# --- the gap rule --------------------------------------------------------------------------

def test_a_complete_block_does_not_fire_and_is_final(tmp_path):
    fx = Fixture(tmp_path)
    fx.block()
    out, _ = fx.compute()
    four = out["readings"]["four_games"]
    assert out["status"] == cc.FINAL and out["provisional_reasons"] == []
    assert four["gap"]["mean_gap"] == pytest.approx(RHAE_WIN - RHAE_BUDGET)
    assert [g["gap"] for g in four["gap"]["games"]] == pytest.approx(
        [RHAE_WIN - RHAE_BUDGET] * 4)
    assert four["gap"]["fires"] is False and four["gap"]["complete"]
    assert four["errors"]["errors"] == 0 and four["errors"]["fires"] is False
    assert four["cost"]["fires"] is False


def test_the_gap_rule_fires_below_5(tmp_path):
    """S0 also wins: three games tie, and on R11L S0 takes 32 actions on level 3 (baseline
    30), so its gap is 100 − (100 + 200 + 3 × 87.89) / 6 = 6.05 and the mean is 1.51 < 5."""
    fx = Fixture(tmp_path)
    slow = {"ending": "GAME_WIN", "level_actions": (10, 20, 32), "levels_completed": 3}
    for g in GAMES:
        fx.run(g, "S4", **WIN)
        fx.run(g, "S0", **(slow if g == "R11L" else WIN))
    gap = fx.compute()[0]["readings"]["four_games"]["gap"]
    r11l = 100 - am.game_score([100.0, 100.0, 100 * (30 / 32) ** 2])
    assert r11l == pytest.approx(6.0547, abs=1e-4)
    assert [x["gap"] for x in gap["games"]] == pytest.approx([0, 0, r11l, 0])
    assert gap["mean_gap"] == pytest.approx(r11l / 4)
    assert gap["fires"] is True


def test_the_gap_rule_at_exactly_5_does_not_fire(tmp_path):
    fx = Fixture(tmp_path)
    fx.block()
    _, b = fx.compute()
    # every gap exactly 5: the rule is "< 5"
    for g in GAMES:
        b.unit(g, "S0").counted.run.score_scorecard = 10.0
        b.unit(g, "S4").counted.run.score_scorecard = 15.0
    gap = cc.gap_reading(b, GAMES)
    assert gap["mean_gap"] == 5.0 and gap["fires"] is False


@pytest.mark.parametrize("s0,s4,fires", [
    (BUDGET, WIN, False),     # 3 gaps of 95.8: at least (287.5 - 100) / 4 = 46.9 >= 5
    (WIN, WIN, None),         # 3 gaps of 0: anywhere in [-25, 25] with the missing game
    (WIN, BUDGET, True),      # 3 gaps of -95.8: at most (-287.5 + 100) / 4 = -46.9 < 5
])
def test_a_partial_gap_decides_the_rule_only_if_every_missing_gap_would(tmp_path, s0, s4,
                                                                        fires):
    fx = Fixture(tmp_path)
    fx.block(games=["FT09", "SB26", "R11L"], s0=s0, s4=s4)
    fx.run("CD82", "S4", **s4)
    gap = fx.compute()[0]["readings"]["four_games"]["gap"]
    assert gap["complete"] is False and gap["n_games"] == 3 and gap["fires"] is fires
    low, high = gap["mean_gap_bounds"]
    assert low == pytest.approx((3 * gap["mean_gap"] - 100) / 4)
    assert high == pytest.approx((3 * gap["mean_gap"] + 100) / 4)
    # the 3-game fallback drops CD82, so its reading is complete and decided
    three = fx.compute()[0]["readings"]["three_games_d32"]["gap"]
    assert three["complete"] and three["mean_gap_bounds"] is None
    assert three["fires"] is (three["mean_gap"] < 5)


def test_the_gap_at_k_is_reported_with_censoring_and_fires_no_rule(tmp_path):
    """S0 ends TIME_BUDGET (not an incident) at 60 actions < 150: censored, its RHAE_K is
    its final value; S4 wins in 60: complete."""
    fx = Fixture(tmp_path)
    tb = {"ending": "TIME_BUDGET", "level_actions": (10, 20, 30), "levels_completed": 1}
    for g in GAMES:
        fx.run(g, "S4", **WIN)
        fx.run(g, "S0", median=60.0, **tb)               # 60 ≤ 2 × 80 (pilot): not an incident
    gk = fx.compute()[0]["readings"]["four_games"]["gap_at_k"]
    assert gk["K"] == am.REGISTERED_K == 150 and gk["K_role"] == "registered"
    assert gk["censored"] == {"S0": 4, "S4": 0}
    assert {x["status_S0"] for x in gk["games"]} == {am.CENSORED}
    assert {x["status_S4"] for x in gk["games"]} == {am.COMPLETE}
    assert gk["mean_gap"] == pytest.approx(100 - 100 / 6)
    assert "fires" not in gk
    # §17.5's sensitivity analysis leaves out every game with a censored counted run
    assert gk["without_censored"] == {"n_games": 0, "mean_gap": None}


def test_the_censoring_sensitivity_keeps_the_uncensored_games(tmp_path):
    """Only FT09's S0 is censored at K = 150 (TIME_BUDGET, not an incident, at 60 actions):
    the sensitivity reading is the mean over the other 3 games."""
    fx = Fixture(tmp_path)
    tb = {"ending": "TIME_BUDGET", "level_actions": (10, 20, 30), "levels_completed": 1}
    for g in GAMES:
        fx.run(g, "S4", **WIN)
        fx.run(g, "S0", median=60.0, **(tb if g == "FT09" else BUDGET))
    gk = fx.compute()[0]["readings"]["four_games"]["gap_at_k"]
    assert gk["censored"] == {"S0": 1, "S4": 0}
    assert gk["without_censored"]["n_games"] == 3
    assert gk["without_censored"]["mean_gap"] == pytest.approx(RHAE_WIN - RHAE_BUDGET)


def test_a_run_failing_the_score_check_is_left_out_of_the_gap_at_k(tmp_path):
    fx = Fixture(tmp_path)
    ids = fx.block()
    path = fx.root / "arc_path" / ids[("SB26", "S0")] / "scorecard.json"
    card = json.loads(path.read_text(encoding="utf-8"))
    card["environments"][0]["runs"][0]["score"] = 50.0      # not ARC's score of its levels
    path.write_text(json.dumps(card), encoding="utf-8")
    out, _ = fx.compute()
    four = out["readings"]["four_games"]
    assert four["gap"]["n_games"] == 4                      # the primary reads the scorecard
    assert [x["game"] for x in four["gap_at_k"]["left_out"]] == ["SB26"]
    assert four["gap_at_k"]["n_games"] == 3
    assert any("fails analysis.arc_action_matched's checks" in w for w in out["warnings"])


# --- re-runs, D19 and D20 ------------------------------------------------------------------

def test_a_rerun_replaces_its_original_everywhere(tmp_path):
    """FT09 S0 ends TIME_BUDGET at 2.5 × the pilot median (a D20 incident); its re-run (seed
    101) wins. The re-run's score, cost, calls and actions are the counted ones; ρ = 1/8."""
    fx = Fixture(tmp_path)
    fx.run("FT09", "S4", billed=5.0, **WIN)
    orig = fx.run("FT09", "S0", ending="TIME_BUDGET", level_actions=(20, 40, 60),
                  levels_completed=1, median=200.0, billed=30.0)
    fx.block(games=["SB26", "R11L", "CD82"])
    re = fx.run("FT09", "S0", seed=101, rerun_of=orig, billed=12.0, n_calls=80, **WIN)
    out, b = fx.compute()
    u = b.unit("FT09", "S0")
    assert u.original.run_id == orig and u.rerun.run_id == re and u.counted.run_id == re
    assert out["status"] == cc.FINAL
    four = out["readings"]["four_games"]
    ft09 = four["gap"]["games"][[g["game"] for g in four["gap"]["games"]].index("FT09")]
    assert ft09["S0_run"] == re and ft09["gap"] == pytest.approx(0.0)
    cost = four["cost"]
    assert cost["reruns"] == 1 and cost["pending_reruns"] == 0 and cost["rho"] == 1 / 8
    row = cost["games"][[g["game"] for g in cost["games"]].index("FT09")]
    assert row["billed_S0"] == 12.0 and row["n_calls_S0"] == 80 and row["actions_S0"] == 60
    by_id = {r["run_id"]: r for r in out["runs"]}
    assert by_id[orig]["counted"] is False and by_id[orig]["replaced_by"] == [re]
    assert by_id[re]["counted"] is True and by_id[re]["replicate"] == 1
    assert by_id[orig]["d20"]["incident"] is True
    assert by_id[orig]["d20"]["as_of_start"]["yardstick_from"] == "pilot pilot-S0"
    assert by_id[orig]["d20"]["as_of_start"]["threshold_s"] == 2 * PILOT["S0"]
    # the phase-1b spend includes the replaced original
    assert out["phase_1b"]["spent_usd"] == pytest.approx(3 * 15.0 + 5.0 + 30.0 + 12.0)


def test_a_pending_rerun_refuses_unless_allowed(tmp_path, capsys):
    fx = Fixture(tmp_path)
    fx.block(games=["SB26", "R11L", "CD82"])
    fx.run("FT09", "S4", **WIN)
    orig = fx.run("FT09", "S0", ending="TIME_BUDGET", level_actions=(20, 40, 60),
                  levels_completed=1, median=200.0, billed=30.0)
    out_dir = tmp_path / "out"
    assert fx.main("--out-dir", str(out_dir)) == 2
    err = capsys.readouterr().err
    assert "block 2 is incomplete" in err and orig in err and "--allow-incomplete" in err
    assert not out_dir.exists()                             # refused before anything is written
    assert fx.main("--out-dir", str(out_dir), "--allow-incomplete") == 0
    c = json.loads((out_dir / "checkpoint_c.json").read_text(encoding="utf-8"))
    assert c["status"] == cc.PROVISIONAL and any(orig in x for x in c["provisional_reasons"])
    four = c["readings"]["four_games"]
    # the original stands in, flagged; it is not counted as an error but as pending
    assert four["errors"]["errors"] == 0 and four["errors"]["pending"] == 1
    assert four["errors"]["errors_upper"] == 1
    assert four["cost"]["pending_reruns"] == 1 and four["cost"]["rho"] == 1 / 8
    ft09 = next(g for g in four["gap"]["games"] if g["game"] == "FT09")
    assert ft09["S0_run"] == orig and ft09["stand_in"] is True
    summary = (out_dir / "summary.md").read_text(encoding="utf-8")
    assert "**Status: PROVISIONAL.**" in summary
    # the pending re-run is not yet paid: a sensitivity reading prices it at its original's
    # billed cost, in both readings (phase-1b spend is not split by game)
    for r in (four, c["readings"]["three_games_d32"]):
        p = r["cost"]["pending_spend"]
        assert p["runs"] == [orig] and p["est_usd"] == 30.0
        assert p["remaining_usd"] == pytest.approx(r["cost"]["remaining_usd"] - 30.0)
        assert p["headroom_with_raise_usd"] == pytest.approx(
            r["cost"]["headroom_with_raise_usd"] - 30.0)
    assert "PROVISIONAL sensitivity, not the rule" in summary
    row = next(r for r in c["runs"] if r["run_id"] == orig)
    assert row["rerun_pending"] is True and row["counted"] is True
    assert "stand-in, re-run pending" in summary


def test_a_pending_rerun_in_the_dropped_game_still_counts_in_the_3_game_spend(tmp_path):
    fx = Fixture(tmp_path)
    fx.block(games=["FT09", "SB26", "R11L"])
    fx.run("CD82", "S4", **WIN)
    orig = fx.run("CD82", "S0", ending="AGENT_ERROR", level_actions=(20, 40, 60),
                  levels_completed=1, billed=7.0)
    out, _ = fx.compute()
    three = out["readings"]["three_games_d32"]["cost"]
    assert three["pending_reruns"] == 0 and three["rho"] == 0.0     # ρ: the 3 games' runs
    assert three["pending_spend"]["runs"] == [orig]                  # spend: the whole phase
    assert three["pending_spend"]["est_usd"] == 7.0


def test_no_pending_spend_reading_when_nothing_is_pending(tmp_path):
    fx = Fixture(tmp_path)
    fx.block()
    out, _ = fx.compute()
    assert out["readings"]["four_games"]["cost"]["pending_spend"] is None
    assert not any(r["rerun_pending"] for r in out["runs"])


def test_a_missing_unit_refuses_and_a_provisional_reading_survives_it(tmp_path, capsys):
    fx = Fixture(tmp_path)
    fx.block(games=["FT09", "SB26", "R11L"])
    fx.run("CD82", "S4", **WIN)
    assert fx.main("--no-write") == 2
    assert "CD82 S0: no seed-1 run yet" in capsys.readouterr().err
    assert fx.main("--no-write", "--allow-incomplete") == 0
    out, _ = fx.compute()
    four = out["readings"]["four_games"]
    assert four["gap"]["n_games"] == 3 and four["gap"]["complete"] is False
    assert four["gap"]["fires"] is False                    # decided whatever CD82's gap is
    # a partial forecast is a lower bound: undetermined unless it already exceeds the room
    assert four["cost"]["complete"] is False and four["cost"]["fires"] is None
    assert four["errors"]["undetermined"] == 1 and four["errors"]["fires"] is False
    assert next(x for x in four["errors"]["runs"]
                if (x["game"], x["config"]) == ("CD82", "S0"))["why"] == "no run yet"
    # the 3-game fallback drops CD82, so its reading is complete
    three = out["readings"]["three_games_d32"]
    assert three["gap"]["complete"] and three["cost"]["complete"]


def test_an_unreadable_scorecard_is_unknown_and_needs_its_rerun(tmp_path):
    """§0.3 line 2: a finished run whose scorecard cannot be read is re-run once, as
    UNKNOWN."""
    fx = Fixture(tmp_path)
    fx.block(games=["FT09", "SB26", "R11L"])
    fx.run("CD82", "S4", **WIN)
    lost = fx.run("CD82", "S0", card=False, **BUDGET)
    out, b = fx.compute()
    assert b.unit("CD82", "S0").pending
    assert any(lost in x for x in out["provisional_reasons"])
    row = next(r for r in out["runs"] if r["run_id"] == lost)
    assert row["d19_ending"] == "UNKNOWN" and row["rerun_eligible"] is True
    assert row["scorecard"] == cc.NO_SCORECARD
    fx.run("CD82", "S0", seed=101, rerun_of=lost, **BUDGET)
    out, _ = fx.compute()
    assert out["status"] == cc.FINAL


def test_d20_yardstick_is_read_as_of_each_runs_start(tmp_path):
    """S0 runs in order: A (TIME_BUDGET, 200 s: incident against the 80 s pilot), B (100 s),
    C (TIME_BUDGET, 290 s), then A's re-run. As of C's start A was not yet replaced, so C's
    yardstick is median(200, 100) = 150 and C is not an incident (290 ≤ 300), as
    results/decisions.md read CD82 S0 on 2026-10-08. On the final counted set (A left out)
    the yardstick is 100 and C would be one: the two readings are reported and flagged."""
    fx = Fixture(tmp_path)
    tb = {"ending": "TIME_BUDGET", "level_actions": (20, 40, 60), "levels_completed": 1}
    for g in GAMES:
        fx.run(g, "S4", **WIN)
    a = fx.run("FT09", "S0", median=200.0, **tb)
    b_id = fx.run("SB26", "S0", median=100.0, **BUDGET)
    c = fx.run("CD82", "S0", median=290.0, **tb)
    fx.run("R11L", "S0", median=100.0, **BUDGET)
    re = fx.run("FT09", "S0", seed=101, rerun_of=a, median=250.0, **tb)
    out, b = fx.compute()
    d_c = b.d20[c]
    assert d_c["as_of_start"]["yardstick_from"] == [a, b_id]
    assert b.d20[a]["as_of_start"]["yardstick_from"] == "pilot pilot-S0"
    assert d_c["as_of_start"]["yardstick_s"] == 150.0 and d_c["incident"] is False
    assert d_c["final_counted_set"]["yardstick_s"] == 100.0
    assert d_c["final_counted_set"]["incident"] is True and d_c["readings_agree"] is False
    assert any(c in w and "readings disagree" in w for w in out["warnings"])
    # the re-run's own original never counts in its yardstick: median(100, 290, 100) = 100
    d_re = b.d20[re]
    assert a not in d_re["as_of_start"]["yardstick_from"]
    assert d_re["as_of_start"]["yardstick_s"] == 100.0 and d_re["incident"] is True
    # C is final (not an error); the re-run is an incident again: counted as is, an error
    err = out["readings"]["four_games"]["errors"]
    by = {(x["game"], x["config"]): x for x in err["runs"]}
    assert by[("CD82", "S0")]["rerun_eligible"] is False
    assert by[("FT09", "S0")]["run_id"] == re and by[("FT09", "S0")]["rerun_eligible"] is True
    assert err["errors"] == 1 and out["status"] == cc.FINAL


def test_a_final_time_budget_is_not_an_error(tmp_path):
    fx = Fixture(tmp_path)
    tb = {"ending": "TIME_BUDGET", "level_actions": (20, 40, 60), "levels_completed": 1}
    for g in GAMES:
        fx.run(g, "S4", **WIN)
        fx.run(g, "S0", median=70.0, **tb)                  # below 2 × 80: never an incident
    out, _ = fx.compute()
    err = out["readings"]["four_games"]["errors"]
    assert err["errors"] == 0 and err["fires"] is False and out["status"] == cc.FINAL
    assert {x["ending"] for x in err["runs"] if x["config"] == "S0"} == {"TIME_BUDGET"}
    assert all("final, not an error" in x["why"] for x in err["runs"] if x["config"] == "S0")
    assert "a final TIME_BUDGET (not an incident) is not an error" in err["time_budget"]


def test_a_rerun_of_an_incident_ending_time_budget_without_an_incident_is_not_an_error(
        tmp_path):
    fx = Fixture(tmp_path)
    tb = {"ending": "TIME_BUDGET", "level_actions": (20, 40, 60), "levels_completed": 1}
    fx.block(games=["SB26", "R11L", "CD82"], s0_median=100.0)
    fx.run("FT09", "S4", **WIN)
    a = fx.run("FT09", "S0", median=500.0, **tb)           # 500 > 2 × 100: incident
    fx.run("FT09", "S0", seed=101, rerun_of=a, median=150.0, **tb)   # 150 ≤ 200: final
    err = fx.compute()[0]["readings"]["four_games"]["errors"]
    assert err["errors"] == 0


@pytest.mark.parametrize("n_errors,fires", [(3, False), (4, True)])
def test_the_error_rule_fires_above_3(tmp_path, n_errors, fires):
    """n units whose original ends API_ERROR and whose re-run ends AGENT_ERROR (counted as
    is: no second re-run); COST_CAP is final, not an error."""
    fx = Fixture(tmp_path)
    err_run = {"ending": "API_ERROR", "level_actions": (20, 40, 60), "levels_completed": 1}
    agent = {"ending": "AGENT_ERROR", "level_actions": (20, 40, 60), "levels_completed": 1}
    cap = {"ending": "COST_CAP", "level_actions": (20, 40, 60), "levels_completed": 1}
    units = [(g, c) for g in GAMES for c in ("S0", "S4")]
    for i, (g, c) in enumerate(units):
        if i < n_errors:
            orig = fx.run(g, c, **err_run)
            fx.run(g, c, seed=101, rerun_of=orig, **agent)
        else:
            fx.run(g, c, **(cap if i == n_errors else WIN))
    out, _ = fx.compute()
    err = out["readings"]["four_games"]["errors"]
    assert err["errors"] == n_errors and err["fires"] is fires and out["status"] == cc.FINAL
    assert out["readings"]["four_games"]["cost"]["rho"] == n_errors / 8


def test_a_rerun_of_a_final_run_is_flagged_but_still_replaces_it(tmp_path):
    fx = Fixture(tmp_path)
    fx.block(games=["SB26", "R11L", "CD82"])
    fx.run("FT09", "S4", **WIN)
    a = fx.run("FT09", "S0", **BUDGET)
    re = fx.run("FT09", "S0", seed=101, rerun_of=a, **WIN)
    out, b = fx.compute()
    assert b.unit("FT09", "S0").counted.run_id == re
    assert any(a in w and "final under D19/D20" in w for w in out["warnings"])


# --- the cost rule -------------------------------------------------------------------------

def _forecast(games, s0_billed, s4_billed, s0_calls, s0_actions, s4_actions, rho):
    seed2 = len(games) * (s0_billed + s4_billed)
    s12 = len(games) * 2 * 2 * (s0_billed / s0_calls) * max(s0_actions, s4_actions)
    return (seed2 + s12) * (1 + rho)


def test_the_cost_rule_is_d27_at_checkpoint_c(tmp_path):
    fx = Fixture(tmp_path)
    fx.block(s0_billed=10.0, s4_billed=5.0)
    fx.rows.append({"run_id": "other-1b", "experiment": "arc_path", "cost_usd_list": "40",
                    "cost_usd_billed_est": "", "notes": "approved_block=3-arc;"})
    fx.rows.append({"run_id": "p1a", "experiment": "persistgym", "cost_usd_list": "9",
                    "cost_usd_billed_est": "7", "notes": ""})
    fx.write_costs()
    cost = fx.compute()[0]["readings"]["four_games"]["cost"]
    want = _forecast(GAMES, 10.0, 5.0, 100, 120, 60, 0.0)
    assert cost["forecast_usd"] == pytest.approx(want) == pytest.approx(4 * (15 + 48))
    assert cost["seed2_usd"] == pytest.approx(60.0) and cost["s1_s2_usd"] == pytest.approx(192)
    # spend: every phase-1b row at its billed estimate, list where none; phase 1a not counted
    assert cost["spent_1b_usd"] == pytest.approx(60.0 + 40.0)
    assert cost["remaining_usd"] == pytest.approx(900 - 100.0)
    assert cost["fires"] is False and cost["n_remaining_runs"] == 24
    assert cost["cap_needed_usd"] == pytest.approx(100.0 + want)
    assert cost["raise_needed_usd"] == 0.0
    m = cost["measured_cost_reading"]
    assert "NOT the pre-registered rule" in m["note"]
    assert m["s1_s2_usd"] == pytest.approx(4 * 2 * 2 * 10.0)


@pytest.mark.parametrize("s0_billed,fires,fires_with_raise", [
    (30.0, False, False), (35.0, True, False), (40.0, True, True)])
def test_the_cost_rule_fires_when_the_forecast_exceeds_what_remains(tmp_path, s0_billed, fires,
                                                                     fires_with_raise):
    """Forecast 4 × (s0 + 5 + 2 × 2 × s0 / 100 calls × 120 actions) = 23.2 s0 + 20 against
    900 − 4 (s0 + 5): it fires above s0 = 31.62, and above 37.87 with the $170 raise."""
    fx = Fixture(tmp_path)
    fx.block(s0_billed=s0_billed, s4_billed=5.0)
    cost = fx.compute()[0]["readings"]["four_games"]["cost"]
    want = _forecast(GAMES, s0_billed, 5.0, 100, 120, 60, 0.0)
    spent = 4 * (s0_billed + 5.0)
    assert cost["forecast_usd"] == pytest.approx(want)
    assert cost["remaining_usd"] == pytest.approx(900 - spent)
    assert cost["fires"] is fires and cost["fires_with_raise"] is fires_with_raise
    assert cost["headroom_with_raise_usd"] == pytest.approx(900 - spent + 170 - want)
    assert cost["raise_needed_usd"] == pytest.approx(max(0.0, spent + want - 900))


def test_rho_counts_block_2_reruns_only(tmp_path):
    """A re-run of a seed-2 run (block 3) is not a block-2 re-run."""
    fx = Fixture(tmp_path)
    fx.block()
    a = fx.run("FT09", "S0", seed=2, ending="API_ERROR", level_actions=(1, 1, 1),
               levels_completed=0)
    fx.run("FT09", "S0", seed=102, rerun_of=a, **BUDGET)
    out, _ = fx.compute()
    assert out["readings"]["four_games"]["cost"]["rho"] == 0.0
    assert out["status"] == cc.FINAL


# --- the 3-game fallback (D32) -------------------------------------------------------------

def test_the_three_game_fallback_drops_perm_3(tmp_path):
    fx = Fixture(tmp_path, drop="SB26")                     # whatever draw.json names
    ids = fx.block()
    # one block-2 re-run, in FT09 (flagged: its original is final): ρ is 1/6 over the 3 games'
    # 6 runs, 1/8 over all 8
    fx.run("FT09", "S0", seed=101, rerun_of=ids[("FT09", "S0")], **BUDGET)
    out, _ = fx.compute()
    three = out["readings"]["three_games_d32"]
    assert out["fallback_drop_game"] == "SB26" and three["games"] == ["FT09", "R11L", "CD82"]
    assert three["errors"]["n_runs"] == 6 and three["cost"]["n_remaining_runs"] == 18
    assert three["cost"]["n_block2_runs"] == 6 and three["cost"]["rho"] == 1 / 6
    games3 = ["FT09", "R11L", "CD82"]
    assert three["cost"]["forecast_usd"] == pytest.approx(
        _forecast(games3, 10.0, 5.0, 100, 120, 60, 1 / 6))
    assert three["cost"]["rho_over_all_block2"]["rho"] == 1 / 8
    assert three["cost"]["rho_over_all_block2"]["forecast_usd"] == pytest.approx(
        _forecast(games3, 10.0, 5.0, 100, 120, 60, 1 / 8))
    assert three["gap"]["n_games"] == 3
    # remaining is the same phase-1b room; the cap needed is spend + the 3-game forecast
    assert three["cost"]["remaining_usd"] == out["readings"]["four_games"]["cost"][
        "remaining_usd"]


def test_the_three_game_fallback_can_fit_where_four_games_do_not(tmp_path):
    """FT09, SB26, R11L cheap, CD82 dear: 4 games fire, 3 fit."""
    fx = Fixture(tmp_path)
    for g in GAMES:
        s0 = 120.0 if g == "CD82" else 10.0
        fx.run(g, "S4", billed=5.0, **WIN)
        fx.run(g, "S0", billed=s0, **BUDGET)
    out, _ = fx.compute()
    assert out["readings"]["four_games"]["cost"]["fires"] is True
    assert out["readings"]["three_games_d32"]["cost"]["fires"] is False


# --- refusals ------------------------------------------------------------------------------

def test_a_drop_that_is_not_perm_3_is_refused(tmp_path, capsys):
    fx = Fixture(tmp_path)
    fx.block()
    path = next((fx.root / "draw").glob("*/draw.json"))
    draw = json.loads(path.read_text(encoding="utf-8"))
    draw["derived"]["perm"] = ["CD82", "FT09", "SB26", "R11L"]      # perm[3] = R11L, not CD82
    path.write_text(json.dumps(draw), encoding="utf-8")
    assert fx.main("--no-write", "--allow-incomplete") == 2
    assert "is not perm[3]" in capsys.readouterr().err


def test_a_phase_cap_other_than_900_is_flagged(tmp_path, monkeypatch):
    fx = Fixture(tmp_path)
    fx.block()
    monkeypatch.setitem(costs.PHASE_CAPS, "1b", 1070.0)
    out, _ = fx.compute()
    assert out["readings"]["four_games"]["cost"]["cap_1b_usd"] == 1070.0
    assert any("not the $900.00 §10.3 names" in w for w in out["warnings"])


def test_a_pilot_folder_is_refused(tmp_path, capsys):
    fx = Fixture(tmp_path)
    fx.block()
    fx.run("R11L", "S0", experiment="arc_pilot", row=False, **BUDGET)
    assert fx.main("--no-write", "--allow-incomplete") == 2
    assert "arc_pilot" in capsys.readouterr().err


@pytest.mark.parametrize("case,match", [
    ("two_originals", "2 seed-1 runs"),
    ("wrong_seed", "seed label 1"),
    ("rerun_of_rerun", "itself a re-run"),
    ("missing_original", "not among the arc_path folders"),
    ("other_config", "does not match its original"),
    ("two_reruns", "2 re-runs"),
    ("unknown_ending", "not an ending D19 classifies"),
])
def test_inconsistent_block_2_is_refused_even_when_incomplete_is_allowed(tmp_path, capsys,
                                                                         case, match):
    fx = Fixture(tmp_path)
    ids = fx.block()
    a = ids[("FT09", "S0")]
    if case == "two_originals":
        fx.run("FT09", "S0", **BUDGET)
    elif case == "wrong_seed":
        fx.run("FT09", "S0", seed=1, rerun_of=a, **BUDGET)
    elif case == "rerun_of_rerun":
        r = fx.run("FT09", "S0", seed=101, rerun_of=a, **BUDGET)
        fx.run("FT09", "S0", seed=201, rerun_of=r, **BUDGET)
    elif case == "missing_original":
        fx.run("FT09", "S0", seed=101, rerun_of="20261001T000000Z-S0-ft09-s1", **BUDGET)
    elif case == "other_config":
        fx.run("FT09", "S4", seed=101, rerun_of=a, **WIN)
    elif case == "two_reruns":
        fx.run("FT09", "S0", seed=101, rerun_of=a, **BUDGET)
        fx.run("FT09", "S0", seed=101, rerun_of=a, **BUDGET)
    elif case == "unknown_ending":
        fx.run("SB26", "S1", ending="NORMAL_ENDING_BLINDED", level_actions=(1, 1, 1),
               levels_completed=0)
    assert fx.main("--no-write", "--allow-incomplete") == 2
    assert match in capsys.readouterr().err


def test_a_counted_run_without_a_costs_row_is_incomplete(tmp_path):
    fx = Fixture(tmp_path)
    fx.block(games=["FT09", "SB26", "R11L"])
    fx.run("CD82", "S4", **WIN)
    r = fx.run("CD82", "S0", row=False, **BUDGET)
    out, _ = fx.compute()
    assert any(r in x and "no costs.csv row" in x for x in out["provisional_reasons"])


def test_an_untagged_or_mismatched_costs_row_is_flagged(tmp_path):
    fx = Fixture(tmp_path)
    fx.block(games=["FT09", "SB26", "R11L"])
    fx.run("CD82", "S4", **WIN)
    r = fx.run("CD82", "S0", tag=False, **BUDGET)
    fx.rows[-1]["cost_usd_billed_est"] = "11.5"
    fx.write_costs()
    out, _ = fx.compute()
    assert out["status"] == cc.FINAL
    assert any(r in w and "not tagged" in w for w in out["warnings"])
    assert any(r in w and "differs from meta.json" in w for w in out["warnings"])
    assert out["readings"]["four_games"]["cost"]["games"][3]["billed_S0"] == 11.5


# --- per run and outputs -------------------------------------------------------------------

def test_per_run_rows_carry_the_g0_forecast_pace_and_d20(tmp_path):
    fx = Fixture(tmp_path)
    ids = fx.block()
    out, _ = fx.compute()
    by = {r["run_id"]: r for r in out["runs"]}
    s0, s4 = by[ids[("FT09", "S0")]], by[ids[("FT09", "S4")]]
    assert s0["g0_forecast_usd"] == pytest.approx(G0_L["L_S0"] * G0_B["S0"])
    assert s4["g0_forecast_usd"] == pytest.approx(G0_L["L_S4"] * G0_B["S4"])
    assert s0["billed_over_forecast"] == pytest.approx(10.0 / 10.0)
    assert s0["seconds_per_action"] == pytest.approx(3600 / 120)
    assert s0["n_calls"] == 100 and s0["median_s_per_call"] == 50.0 and s0["d20"] is None
    assert [r["run_id"] for r in out["runs"]] == sorted(by)   # in start order


def test_the_output_is_exactly_the_allowlist(tmp_path):
    fx = Fixture(tmp_path)
    secret = "SECRET-VALUE-123"
    extra = {"api_key": secret, "raw_transcript_path": f"results/raw/{secret}",
             "tokens": {"reasoning_tokens": 777_777_777}, "notes": secret}
    for g in GAMES:
        fx.run(g, "S4", meta_extra=extra, card_extra={"opaque": secret}, **WIN)
        fx.run(g, "S0", meta_extra=extra, **BUDGET)
    out = tmp_path / "out"
    assert fx.main("--out-dir", str(out)) == 0
    assert sorted(p.name for p in out.iterdir()) == sorted([*cc.OUTPUTS, "meta.json"])
    c = json.loads((out / "checkpoint_c.json").read_text(encoding="utf-8"))
    assert tuple(c) == cc.TOP_FIELDS
    assert all(tuple(r) == cc.RUN_FIELDS for r in c["runs"])
    text = "\n".join(p.read_text(encoding="utf-8") for p in out.iterdir())
    assert secret not in text and "777777777" not in text and "results/raw" not in text
    assert "arc_run=" not in text                           # costs.csv notes are not copied
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["experiment"] == "checkpoint_c" and meta["paid_calls"] == 0
    assert meta["cost_usd"] == 0.0 and meta["outputs"] == list(cc.OUTPUTS)
    assert meta["config"]["status"] == cc.FINAL and meta["exit_reason"] == "completed"
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "The researcher makes the go/no-go call." in summary
    assert "not the pre-registered rule" in summary


def test_the_default_output_folder_is_under_the_results_root(tmp_path):
    fx = Fixture(tmp_path)
    fx.block()
    assert fx.main() == 0
    (folder,) = (fx.root / "checkpoint_c").iterdir()
    assert sorted(p.name for p in folder.iterdir()) == sorted([*cc.OUTPUTS, "meta.json"])


def test_this_checkouts_results_give_a_reading_without_crashing(capsys):
    """Whatever block-2 folders are committed here (all, some or none of them): with
    --allow-incomplete the script prints a reading, FINAL or PROVISIONAL, and writes
    nothing."""
    before = sorted(p.name for p in (cc.RESULTS / "checkpoint_c").glob("*")) if (
        cc.RESULTS / "checkpoint_c").is_dir() else []
    assert cc.main(["--no-write", "--allow-incomplete"]) == 0
    text = capsys.readouterr().out
    assert "# Checkpoint C metrics (PREREG §10.3)" in text and "**Status: " in text
    after = sorted(p.name for p in (cc.RESULTS / "checkpoint_c").glob("*")) if (
        cc.RESULTS / "checkpoint_c").is_dir() else []
    assert before == after


def test_partial_readings_fire_only_on_a_bound_that_already_fires():
    assert cc._fires_at(100.0, 50.0, complete=False) is True
    assert cc._fires_at(10.0, 50.0, complete=False) is None
    assert cc._fires_at(10.0, 50.0, complete=True) is False


def test_the_error_rule_is_undetermined_while_missing_runs_could_make_it_fire(tmp_path):
    """3 counted errors and a unit without a run: a fourth error is still possible."""
    fx = Fixture(tmp_path)
    err_run = {"ending": "API_ERROR", "level_actions": (20, 40, 60), "levels_completed": 1}
    agent = {"ending": "AGENT_ERROR", "level_actions": (20, 40, 60), "levels_completed": 1}
    units = [(g, c) for g in GAMES for c in ("S0", "S4")]
    for i, (g, c) in enumerate(units[:-1]):
        if i < 3:
            fx.run(g, c, seed=101, rerun_of=fx.run(g, c, **err_run), **agent)
        else:
            fx.run(g, c, **WIN)
    err = fx.compute()[0]["readings"]["four_games"]["errors"]
    assert err["errors"] == 3 and err["undetermined"] == 1 and err["fires"] is None
