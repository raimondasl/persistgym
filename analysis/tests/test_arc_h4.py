"""H4 on the ARC path runs (analysis/arc_h4.py; PREREG §3 H4 as amended by §17.6 change 3):
shares and predictions on hand-computed values, the wording without S1, D34's G ≥ 10, the
bootstrap (its seed, its determinism and the 35 distinct resamples of 4 units), the refusal of
incomplete units, the --with-s1 path, the sensitivity analyses, R7's replacement chain (its
counted runs, the originals analysis on each chain's first run and R7's on the run the R7
replacement replaced, the config hash and summary budget per run, its flags, and σ_replay's
note: computed from synthetic S4 compaction records, or quoted when they are missing), the
readings at K = 150 with censoring, the context_trims check and the output allowlist.

Every run here is synthetic, in a results root built under tmp_path (checkpoint_c's test
fixture, whose RHAE values follow from its level lists), except the last two tests: one runs
the script on this checkout's results/ with --allow-incomplete, the other on a copy of block
2's folders with synthetic S2 runs added."""

from __future__ import annotations

import json
import math
import shutil
from fractions import Fraction

import numpy as np
import pytest

from analysis import arc_action_matched as am
from analysis import arc_h4 as h4
from analysis import checkpoint_c as cc
from analysis.tests.test_checkpoint_c import GAMES, GIT, Fixture, _card

SEED = 4086943125952605534
RHAE = {0: 0.0, 1: 100 / 6, 2: 50.0, 3: 100.0}
"""RHAE of a play that clears the first n levels at baseline (baselines 10, 20, 30)."""


def play(levels: int, ending: str | None = None) -> dict:
    return {"ending": ending or ("GAME_WIN" if levels == 3 else "ACTION_BUDGET"),
            "level_actions": (10, 20, 30), "levels_completed": levels}


class H4Fixture(Fixture):
    """checkpoint_c's results root, with SEED in draw.json."""

    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        path = next((self.root / "draw").glob("*/draw.json"))
        draw = json.loads(path.read_text(encoding="utf-8"))
        draw["seed"] = {"source": "nist", "seed": SEED}
        path.write_text(json.dumps(draw), encoding="utf-8")

    def grid(self, levels: dict[str, dict[str, int]], skip=()) -> dict:
        """One seed-1 run per game and config, clearing `levels[game][config]` levels: block
        2's S4 and S0 first, then S1 and S2. Returns {(game, config): run_id}."""
        ids = {}
        for configs in (("S4", "S0"), ("S1", "S2")):
            for g, per in levels.items():
                for c in configs:
                    if c in per and (g, c) not in skip:
                        ids[(g, c)] = self.run(g, c, **play(per[c]))
        return ids

    def compute(self, with_s1=False):
        return h4.compute(self.root, "now", GIT, with_s1=with_s1)

    def main(self, *args):
        return h4.main(["--results-root", str(self.root), *args])


# FT09 (0, 50, 100), SB26 (0, 0, 100), R11L (50, 50, 100), CD82 (0, 100, 100) for S0, S2, S4:
# R̄ = 12.5, 50, 100; G = 87.5; σ_pn = 37.5 / 87.5 = 3/7; σ_replay = 50 / 87.5 = 4/7.
MIXED = {"FT09": {"S0": 0, "S2": 2, "S4": 3}, "SB26": {"S0": 0, "S2": 0, "S4": 3},
         "R11L": {"S0": 2, "S2": 2, "S4": 3}, "CD82": {"S0": 0, "S2": 3, "S4": 3}}


def _same(s0, s2, s4, s1=None):
    per = {"S0": s0, "S2": s2, "S4": s4, **({} if s1 is None else {"S1": s1})}
    return {g: dict(per) for g in GAMES}


# --- shares and predictions ----------------------------------------------------------------

def test_shares_and_predictions_on_hand_computed_values(tmp_path):
    fx = H4Fixture(tmp_path)
    fx.grid(MIXED)
    h = fx.compute()
    assert h["status"] == h4.FINAL and h["configs"] == ["S0", "S2", "S4"]
    p = h["primary"]
    assert p["n_units"] == 4 and p["units"] == GAMES
    assert p["means"] == pytest.approx({"S0": 12.5, "S2": 50.0, "S4": 100.0})
    assert p["G"] == pytest.approx(87.5) and p["shares_reported"] is True
    assert p["shares"] == pytest.approx({"sigma_pn": 3 / 7, "sigma_replay": 4 / 7})
    assert sum(p["shares"].values()) == pytest.approx(1.0)
    assert p["predictions"]["B"]["holds"] is True
    assert p["predictions"]["A"]["reading"] == h4.A_CONTRADICTED
    assert p["d30_dominated"] is False                      # 4/7 < 2/3
    # per-game steps
    steps = {r["game"]: (r["S2_minus_S0"], r["S4_minus_S2"], r["S4_minus_S0"])
             for r in p["per_game"]}
    assert steps == {"FT09": (50, 50, 100), "SB26": (0, 100, 100), "R11L": (0, 50, 50),
                     "CD82": (100, 0, 100)}
    # leave one game out: σ_replay over the other three
    loo = {x["left_out"]: x for x in p["leave_one_out"]}
    assert {g: x["sigma_replay"] for g, x in loo.items()} == pytest.approx(
        {"FT09": 0.6, "SB26": 0.4, "R11L": 0.5, "CD82": 0.8})
    assert loo["R11L"]["G"] == pytest.approx(100.0) and not loo["R11L"]["G_below_10"]
    # the counted runs of every unit are named
    assert set(p["runs"]) == set(GAMES) and p["left_out"] == []


@pytest.mark.parametrize("s2,replay,b,a", [
    (2, Fraction(1, 2), True, h4.A_REPLAY_HOLDS),    # exactly 1/2: B holds, A not contradicted
    (0, Fraction(1), True, h4.A_CONTRADICTED),
    (3, Fraction(0), False, h4.A_REPLAY_HOLDS),
])
def test_the_predictions_without_s1_use_r6s_wording(tmp_path, s2, replay, b, a):
    fx = H4Fixture(tmp_path)
    fx.grid(_same(0, s2, 3))
    h = fx.compute()
    p = h["primary"]
    assert p["shares"]["sigma_replay"] == float(replay)
    assert p["predictions"]["B"]["holds"] is b and p["predictions"]["A"]["reading"] == a
    assert p["d30_dominated"] is (replay >= Fraction(2, 3))
    text = "\n".join(h4.summary_lines(h))
    assert "A holds" not in text and "A does hold" not in text
    assert f"**{a}**" in text
    assert "σ_loss and σ_notes are not identified" in text


def test_a_share_on_a_threshold_is_judged_exactly():
    """The point estimates are exact fractions of the scorecards' values as written: with
    0.3, 10.4 and 20.5, σ_replay = 10.1 / 20.2 = 1/2 exactly, so B holds (and so does A's
    replay clause, the one case where both can), although the binary floats' own values
    put it just below 1/2."""
    s0, s2, s4 = 0.3, 10.4, 20.5
    assert (Fraction(s4) - Fraction(s2)) / (Fraction(s4) - Fraction(s0)) < Fraction(1, 2)
    values = {g: {"S0": s0, "S2": s2, "S4": s4} for g in GAMES}
    r = h4.reading(values, h4.CONFIGS, False, SEED, boot=10)
    assert r["predictions"]["B"]["holds"] is True
    assert r["predictions"]["A"]["reading"] == h4.A_REPLAY_HOLDS
    assert r["shares"]["sigma_replay"] == 0.5


def test_shares_are_withheld_when_g_is_below_10(tmp_path):
    """S4 clears level 1 on FT09 and SB26 only: G = 2 × (100/6) / 4 = 8.33 < 10."""
    fx = H4Fixture(tmp_path)
    fx.grid({g: {"S0": 0, "S2": 0, "S4": 1 if g in ("FT09", "SB26") else 0} for g in GAMES})
    h = fx.compute()
    p = h["primary"]
    assert p["G"] == pytest.approx(100 / 12) and p["shares_reported"] is False
    assert p["shares"] is None and p["predictions"] is None and p["d30_dominated"] is None
    assert p["leave_one_out"] is None and p["bootstrap"]["shares"] is None
    assert p["bootstrap"]["G"] is not None                  # levels and G are still reported
    text = "\n".join(h4.summary_lines(h))
    assert "G < 10: the shares are withheld (D34)" in text and "kill criterion 4" in text


# --- the bootstrap -------------------------------------------------------------------------

def test_the_bootstrap_uses_seed_plus_30_and_is_deterministic(tmp_path):
    fx = H4Fixture(tmp_path)
    fx.grid(MIXED)
    h = fx.compute()
    assert h["seed"] == SEED and h["bootstrap_seed"] == SEED + 30
    bs = h["primary"]["bootstrap"]
    assert bs["rng_seed"] == SEED + 30 and bs["resamples"] == 10_000
    # an independent resampling with the same generator gives the same intervals
    vals = {g: {c: RHAE[MIXED[g][c]] for c in ("S0", "S2", "S4")} for g in GAMES}
    mat = np.array([[vals[g][c] for c in ("S0", "S2", "S4")] for g in GAMES])
    idx = np.random.default_rng(SEED + 30).integers(0, 4, size=(10_000, 4))
    m = mat[idx].mean(axis=1)
    gap = m[:, 2] - m[:, 0]
    assert bs["G"] == pytest.approx(list(np.quantile(gap, [0.05, 0.95])))
    assert bs["fraction_G_le_0"] == float(np.mean(gap <= 0)) == 0.0   # every unit's gap > 0
    ok = gap != 0
    assert bs["shares"]["sigma_replay"] == pytest.approx(
        list(np.quantile((m[ok, 2] - m[ok, 1]) / gap[ok], [0.05, 0.95])))
    assert bs["shares_undefined"] == int((~ok).sum())
    # determinism: the same files give the same numbers
    assert fx.compute()["primary"]["bootstrap"] == bs


def test_four_units_give_only_35_distinct_resamples():
    assert math.comb(7, 4) == 35
    values = {g: {"S0": 0.0, "S2": float(i), "S4": 100.0} for i, g in enumerate(GAMES)}
    bs = h4.bootstrap(values, h4.CONFIGS, False, SEED + 30)
    assert bs["distinct_possible"] == 35 and bs["distinct_drawn"] == 35
    assert h4.bootstrap(values, h4.CONFIGS, False, SEED + 30) == bs
    assert h4.bootstrap(values, h4.CONFIGS, False, SEED + 31) != bs
    three = {g: values[g] for g in GAMES[:3]}
    assert h4.bootstrap(three, h4.CONFIGS, False, SEED + 30)["distinct_possible"] == 10


def test_the_fraction_of_resamples_with_g_at_most_0(tmp_path):
    """Gaps of +100 on FT09 and −50 on the other three: a resample's G is above 0 exactly
    when FT09 is drawn at least twice (2 × 100 − 2 × 50 = 100 > 0; 100 − 3 × 50 < 0)."""
    values = {g: {"S0": 0.0 if g == "FT09" else 50.0, "S2": 0.0,
                  "S4": 100.0 if g == "FT09" else 0.0} for g in GAMES}
    bs = h4.bootstrap(values, h4.CONFIGS, False, SEED + 30, with_shares=False)
    idx = np.random.default_rng(SEED + 30).integers(0, 4, size=(10_000, 4))
    assert bs["fraction_G_le_0"] == float(np.mean((idx == 0).sum(axis=1) < 2))
    # and the exact probability over the 4^4 equally likely draws is 1 - P(FT09 >= 2 times)
    p_le_0 = sum(math.comb(4, k) * 3 ** (4 - k) for k in (0, 1)) / 4 ** 4
    assert bs["fraction_G_le_0"] == pytest.approx(p_le_0, abs=0.02)


# --- incomplete units ----------------------------------------------------------------------

def test_a_missing_unit_refuses_unless_allowed(tmp_path, capsys):
    fx = H4Fixture(tmp_path)
    fx.grid(MIXED, skip={("CD82", "S2")})
    out_dir = tmp_path / "out"
    assert fx.main("--out-dir", str(out_dir)) == 2
    err = capsys.readouterr().err
    assert "CD82 S2: no seed-1 run yet" in err and "--allow-incomplete" in err
    assert not out_dir.exists()
    assert fx.main("--out-dir", str(out_dir), "--allow-incomplete") == 0
    h = json.loads((out_dir / "h4.json").read_text(encoding="utf-8"))
    assert h["status"] == h4.PROVISIONAL
    assert h["primary"] is h["sensitivity"] is h["at_k"] is None
    p = h["partial"]
    assert p["means"]["S2"] == {"n_units": 3, "mean": pytest.approx(100 / 3)}
    assert p["G"] == pytest.approx(87.5)                    # S0 and S4 are complete
    summary = (out_dir / "summary.md").read_text(encoding="utf-8")
    assert "**Status: PROVISIONAL.**" in summary and "σ_replay (S2" not in summary
    meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["exit_reason"] == "completed_provisional"


def test_a_pending_rerun_or_an_unscorable_run_refuses(tmp_path, capsys):
    fx = H4Fixture(tmp_path)
    fx.grid(MIXED, skip={("CD82", "S2"), ("SB26", "S2")})
    err_run = fx.run("CD82", "S2", ending="AGENT_ERROR", level_actions=(10, 20, 30),
                     levels_completed=0)
    lost = fx.run("SB26", "S2", card=False, **play(0))     # final ending, no scorecard: UNKNOWN
    assert fx.main("--no-write") == 2
    err = capsys.readouterr().err
    assert err_run in err and lost in err and "re-run has not landed" in err
    fx.run("CD82", "S2", seed=101, rerun_of=err_run, **play(3))
    fx.run("SB26", "S2", seed=101, rerun_of=lost, **play(0))
    h = fx.compute()
    assert h["status"] == h4.FINAL
    assert h["primary"]["shares"] == pytest.approx({"sigma_pn": 3 / 7, "sigma_replay": 4 / 7})


def test_a_rerun_that_also_errs_is_counted_as_is_and_flagged(tmp_path):
    fx = H4Fixture(tmp_path)
    fx.grid(MIXED, skip={("CD82", "S2")})
    orig = fx.run("CD82", "S2", ending="API_ERROR", level_actions=(10, 20, 30),
                  levels_completed=3)
    re = fx.run("CD82", "S2", seed=101, rerun_of=orig, ending="AGENT_ERROR",
                level_actions=(10, 20, 30), levels_completed=0)
    h = fx.compute()
    assert h["status"] == h4.FINAL and h["units"]["CD82 S2"]["counted"] == re
    assert any(re in w and "counted as is" in w for w in h["warnings"])
    row = next(r for r in h["runs"] if r["run_id"] == re)
    assert row["in_reading"] and any("counted as is" in f for f in row["flags"])


# --- with S1 -------------------------------------------------------------------------------

@pytest.mark.parametrize("s1,s2,which", [
    (2, 2, "both"),          # σ_loss 1/2, σ_notes 0, σ_replay 1/2
    (3, 3, "A only"),        # σ_loss 1, σ_notes 0, σ_replay 0
    (0, 0, "B only"),        # σ_loss 0: A fails; σ_replay 1
    (2, 3, "neither"),       # σ_notes 1/2: A fails; σ_replay 0
])
def test_with_s1_the_frozen_shares_and_predictions(tmp_path, s1, s2, which):
    fx = H4Fixture(tmp_path)
    fx.grid(_same(0, s2, 3, s1=s1))
    h = fx.compute(with_s1=True)
    assert h["configs"] == ["S0", "S1", "S2", "S4"] and h["with_s1"] is True
    p = h["primary"]
    want = {"sigma_loss": RHAE[s1] / 100, "sigma_notes": (RHAE[s2] - RHAE[s1]) / 100,
            "sigma_replay": (100 - RHAE[s2]) / 100}
    assert p["shares"] == pytest.approx(want)
    assert p["predictions"]["which"] == which
    assert p["predictions"]["A"]["holds"] is (which in ("both", "A only"))
    assert p["bootstrap"]["shares"].keys() == want.keys()
    text = "\n".join(h4.summary_lines(h))
    assert f"Which hold: **{which}**" in text and "--with-s1" in text


def test_s1_runs_stay_out_without_with_s1_and_with_s1_needs_them(tmp_path, capsys):
    fx = H4Fixture(tmp_path)
    ids = fx.grid(_same(0, 2, 3, s1=2))
    h = fx.compute()
    assert h["configs"] == ["S0", "S2", "S4"] and "sigma_loss" not in h["primary"]["shares"]
    assert any("--with-s1 was not passed" in w for w in h["warnings"])
    s1 = next(r for r in h["runs"] if r["run_id"] == ids[("FT09", "S1")])
    assert s1["in_reading"] is False and any("exploratory" in f for f in s1["flags"])
    # --with-s1 without every S1 run refuses
    fx2 = H4Fixture(tmp_path / "two")
    fx2.grid(_same(0, 2, 3, s1=2), skip={("R11L", "S1")})
    assert fx2.main("--no-write", "--with-s1") == 2
    assert "R11L S1: no seed-1 run yet" in capsys.readouterr().err


# --- sensitivity analyses ------------------------------------------------------------------

def test_the_originals_and_cost_cap_sensitivity_analyses(tmp_path):
    """FT09 S0's original (TIME_BUDGET at 200 s per call against the earlier S0 runs' 50 s: a
    D20 incident) cleared 2 levels (50) and its re-run none (0); SB26 S2 ends COST_CAP
    (final)."""
    fx = H4Fixture(tmp_path)
    fx.grid(MIXED, skip={("FT09", "S0"), ("SB26", "S2")})
    orig = fx.run("FT09", "S0", median=200.0, **play(2, "TIME_BUDGET"))
    re = fx.run("FT09", "S0", seed=101, rerun_of=orig, **play(0))
    fx.run("SB26", "S2", **play(0, "COST_CAP"))
    h = fx.compute()
    assert h["status"] == h4.FINAL and h["units"]["FT09 S0"]["counted"] == re
    assert h["primary"]["means"]["S0"] == pytest.approx(12.5)
    o = h["sensitivity"]["originals"]
    assert o["runs"]["FT09"]["S0"] == orig and o["means"]["S0"] == pytest.approx(25.0)
    assert o["G"] == pytest.approx(75.0)
    assert o["substituted"] == [{"game": "FT09", "config": "S0", "original": orig,
                                 "rhae_original": 50.0, "counted": re, "rhae_counted": 0.0}]
    c = h["sensitivity"]["without_cost_cap"]
    assert c["units"] == ["FT09", "R11L", "CD82"]
    assert [x["game"] for x in c["left_out"]] == ["SB26"] and "COST_CAP" in c["left_out"][0]["why"]
    # FT09 (0, 50, 100), R11L (50, 50, 100), CD82 (0, 100, 100)
    assert c["means"] == pytest.approx({"S0": 50 / 3, "S2": 200 / 3, "S4": 100.0})
    assert c["shares"]["sigma_replay"] == pytest.approx((100 - 200 / 3) / (100 - 50 / 3))
    text = "\n".join(h4.summary_lines(h))
    assert "Original runs instead of re-runs" in text
    assert f"`{orig}` (RHAE 50.00) for the counted run `{re}` (0.00)" in text
    assert h["sigma_replay_note"] is None and h4.SIGMA_REPLAY_R7_LABEL not in text


def test_an_unscorable_original_is_left_out_of_the_originals_reading(tmp_path):
    fx = H4Fixture(tmp_path)
    fx.grid(MIXED, skip={("R11L", "S2")})
    orig = fx.run("R11L", "S2", card=False, **play(2))
    fx.run("R11L", "S2", seed=101, rerun_of=orig, **play(2))
    h = fx.compute()
    o = h["sensitivity"]["originals"]
    assert o["n_units"] == 3 and [x["game"] for x in o["left_out"]] == ["R11L"]
    assert "cannot be scored" in o["left_out"][0]["why"]
    assert h["primary"]["n_units"] == 4


# --- R7 ------------------------------------------------------------------------------------

OLD_HASH, NEW_HASH = "a" * 64, "b" * 64


def budget(tokens: int, digest: str) -> dict:
    """meta.json's config hash and the profile's summary budget (all R7 reads of `config`)."""
    return {"config_hash": digest,
            "config": {"runtime": {"compaction": {"summary_max_output_tokens": tokens}}}}


OLD, NEW = budget(8192, OLD_HASH), budget(65536, NEW_HASH)


def test_an_r7_replacement_is_counted_and_r7s_sensitivity_puts_back_the_run_it_replaced(
        tmp_path):
    """FT09 S2: the original (0 levels) and its re-run (1 level, RHAE 16.67) end AGENT_ERROR
    under the 8,192 budget; the R7 replacement (65,536) clears 2 (RHAE 50), as in MIXED."""
    fx = H4Fixture(tmp_path)
    fx.grid(MIXED, skip={("FT09", "S2")})
    orig = fx.run("FT09", "S2", meta_extra=OLD, **play(0, "AGENT_ERROR"))
    re = fx.run("FT09", "S2", seed=101, rerun_of=orig, meta_extra=OLD, **play(1, "AGENT_ERROR"))
    r7 = fx.run("FT09", "S2", seed=201, r7_replaces=re, meta_extra=NEW, **play(2))
    h = fx.compute()
    assert h["status"] == h4.FINAL
    assert h["units"]["FT09 S2"] == {"counted": r7, "original": orig, "rerun": re,
                                     "r7_replacement": r7, "r7_rerun": None, "pending": False}
    p = h["primary"]
    assert p["runs"]["FT09"]["S2"] == r7
    assert p["shares"] == pytest.approx({"sigma_pn": 3 / 7, "sigma_replay": 4 / 7})
    pre = h["sensitivity"]["pre_r7"]
    s2 = (RHAE[1] + 0 + 50 + 100) / 4
    assert pre["runs"]["FT09"]["S2"] == re and pre["n_units"] == 4
    assert pre["means"]["S2"] == pytest.approx(s2) and pre["G"] == pytest.approx(87.5)
    assert pre["shares"]["sigma_replay"] == pytest.approx((100 - s2) / 87.5)
    assert pre["substituted"] == [{"game": "FT09", "config": "S2", "replaced": re,
                                   "rhae_replaced": pytest.approx(RHAE[1]),
                                   "summary_budget_replaced": 8192, "counted": r7,
                                   "rhae_counted": 50.0, "summary_budget_counted": 65536}]
    # the frozen originals reading uses each chain's first run (§17.7 change 4 (i)): FT09
    # S2's seed-1 original, which cleared nothing
    o = h["sensitivity"]["originals"]
    assert o["runs"]["FT09"]["S2"] == orig and o["means"]["S2"] == pytest.approx(37.5)
    assert o["substituted"] == [{"game": "FT09", "config": "S2", "original": orig,
                                 "rhae_original": 0.0, "counted": r7, "rhae_counted": 50.0}]
    assert h["at_k"]["pre_r7"]["runs"]["FT09"]["S2"] == re
    assert h["at_k"]["originals"]["runs"]["FT09"]["S2"] == orig
    # every replaced run is in one of the two sensitivity readings
    assert {o["runs"]["FT09"]["S2"], pre["runs"]["FT09"]["S2"]} == {orig, re}
    rows = {r["run_id"]: r for r in h["runs"]}
    assert rows[r7]["r7_replaces"] == re and rows[r7]["counted"] and rows[r7]["in_reading"]
    assert (rows[r7]["config_hash"], rows[r7]["summary_max_output_tokens"]) == (NEW_HASH, 65536)
    assert (rows[re]["config_hash"], rows[re]["summary_max_output_tokens"]) == (OLD_HASH, 8192)
    assert rows[re]["counted"] is False and rows[re]["replicate"] == rows[r7]["replicate"] == 1
    assert f"R7 replacement of {re}" in rows[r7]["flags"]
    assert any("(the R7 sensitivity analysis only)" in f for f in rows[re]["flags"])
    assert not any("counted as is" in f for f in rows[re]["flags"])
    assert (f"replaced by {re} (the originals sensitivity analysis only)"
            in rows[orig]["flags"])
    s0 = rows[h["units"]["FT09 S0"]["counted"]]
    assert s0["config_hash"] is None and s0["summary_max_output_tokens"] is None
    assert not any("R7" in w for w in h["warnings"])
    text = "\n".join(h4.summary_lines(h))
    assert h4.PRE_R7_LABEL in text
    assert (f"FT09 S2: `{re}` (RHAE 16.67, summary budget 8,192) for `{r7}` (50.00, 65,536)"
            in text)
    assert f"`{NEW_HASH[:12]}` (65,536)" in text and f"`{OLD_HASH[:12]}` (8,192)" in text
    assert "not recorded (none)" in text                     # the synthetic S0 runs
    assert "**R7 changed S1's and S2's summary budget mid-block**" in text
    assert ("of the 4 counted S2 runs, 1 played under 65,536 and 0 "
            "under 8,192 (3 with no budget recorded)") in text
    assert f"FT09 S2: `{orig}` (RHAE 0.00) for the counted run `{r7}` (50.00)" in text
    assert ("**D20's yardsticks pool both versions** (§17.7 change 5): D20 judges each S2 "
            "run's seconds per model call against its config's earlier counted runs, whether "
            "they played under 8,192 or 65,536") in text
    # σ_replay's note: no compaction records under this results root, so it is quoted
    note = h["sigma_replay_note"]
    assert note["s2_runs_at_r7_budget"] == [r7] and note["n_counted_s2"] == 4
    assert note["computed"] is False and note["budget_bound"] is False
    assert (note["summaries"], note["retries"], note["max_output_tokens_per_attempt"]) == (
        132, 0, 3073)
    assert h4.SIGMA_REPLAY_R7_LABEL in text and note["text"] in text
    assert ("In every S4 run of block 2 the 8,192 budget never bound: 132 summaries, 0 "
            "retries, at most 3,073 output tokens per attempt (as recorded in "
            "results/decisions.md (2026-10-10, amendment R7)") in note["text"]
    assert "quoted, not recomputed" in note["text"]


def test_an_r7_replacements_own_re_run_is_pending_then_counted(tmp_path):
    fx = H4Fixture(tmp_path)
    fx.grid(MIXED, skip={("FT09", "S2")})
    orig = fx.run("FT09", "S2", meta_extra=OLD, **play(0, "AGENT_ERROR"))
    re = fx.run("FT09", "S2", seed=101, rerun_of=orig, meta_extra=OLD, **play(1, "AGENT_ERROR"))
    r7 = fx.run("FT09", "S2", seed=201, r7_replaces=re, meta_extra=NEW, **play(0, "API_ERROR"))
    h = fx.compute()
    assert h["status"] == h4.PROVISIONAL and h["units"]["FT09 S2"]["pending"]
    assert any(r7 in x and "re-run has not landed" in x for x in h["provisional_reasons"])
    row = next(r for r in h["runs"] if r["run_id"] == r7)
    assert "re-run-eligible; its re-run has not landed" in row["flags"]
    r7_re = fx.run("FT09", "S2", seed=301, rerun_of=r7, meta_extra=NEW, **play(2))
    h = fx.compute()
    assert h["status"] == h4.FINAL
    assert h["units"]["FT09 S2"]["counted"] == h["units"]["FT09 S2"]["r7_rerun"] == r7_re
    assert h["primary"]["shares"] == pytest.approx({"sigma_pn": 3 / 7, "sigma_replay": 4 / 7})
    o = h["sensitivity"]["originals"]
    assert o["runs"]["FT09"]["S2"] == orig
    assert o["substituted"] == [{"game": "FT09", "config": "S2", "original": orig,
                                 "rhae_original": 0.0, "counted": r7_re, "rhae_counted": 50.0}]
    assert h["sensitivity"]["pre_r7"]["runs"]["FT09"]["S2"] == re
    rows = {r["run_id"]: r for r in h["runs"]}
    # the R7 replacement replaced by its own re-run is the one replaced run in no reading
    assert (f"replaced by {r7_re} (in no reading: the originals sensitivity analysis uses the "
            f"chain's first run, {orig}, and R7's the run the R7 replacement replaced, {re})"
            in rows[r7]["flags"])
    assert [rows[x]["replicate"] for x in (orig, re, r7, r7_re)] == [1, 1, 1, 1]


def test_an_r7_replacement_of_an_original_with_s1(tmp_path):
    """CD82 S1's original ends AGENT_ERROR and is replaced by R7 directly (no D19 re-run):
    not pending; R7's sensitivity puts the original back."""
    fx = H4Fixture(tmp_path)
    fx.grid(_same(0, 2, 3, s1=2), skip={("CD82", "S1")})
    orig = fx.run("CD82", "S1", meta_extra=OLD, **play(1, "AGENT_ERROR"))
    r7 = fx.run("CD82", "S1", seed=201, r7_replaces=orig, meta_extra=NEW, **play(2))
    h = fx.compute(with_s1=True)
    assert h["status"] == h4.FINAL and h["units"]["CD82 S1"]["counted"] == r7
    assert h["primary"]["shares"]["sigma_loss"] == pytest.approx(0.5)
    pre = h["sensitivity"]["pre_r7"]
    assert pre["runs"]["CD82"]["S1"] == orig
    assert pre["shares"]["sigma_loss"] == pytest.approx((3 * 50 + RHAE[1]) / 4 / 100)
    row = next(r for r in h["runs"] if r["run_id"] == orig)
    assert (f"replaced by its R7 replacement {r7} (the originals and R7 sensitivity analyses "
            "only)" in row["flags"])
    assert h["sensitivity"]["originals"]["runs"]["CD82"]["S1"] == orig


@pytest.mark.parametrize("case,warning", [
    ("r7_under_the_old_budget", "has summary budget 8,192, not R7's 65,536"),
    ("r7_of_a_final_run", "which ended TIME_BUDGET, not AGENT_ERROR"),
    ("no_r7_yet", "has no R7 replacement"),
])
def test_r7_is_checked_and_flagged_not_refused(tmp_path, case, warning):
    fx = H4Fixture(tmp_path)
    fx.grid(MIXED, skip={("SB26", "S2")})
    if case == "r7_under_the_old_budget":
        orig = fx.run("SB26", "S2", meta_extra=OLD, **play(0, "AGENT_ERROR"))
        fx.run("SB26", "S2", seed=201, r7_replaces=orig, meta_extra=OLD, **play(0))
    elif case == "r7_of_a_final_run":
        orig = fx.run("SB26", "S2", meta_extra=OLD, **play(0, "TIME_BUDGET"))
        fx.run("SB26", "S2", seed=201, r7_replaces=orig, meta_extra=NEW, **play(0))
    else:
        orig = fx.run("SB26", "S2", meta_extra=OLD, **play(0, "AGENT_ERROR"))
        fx.run("SB26", "S2", seed=101, rerun_of=orig, meta_extra=OLD, **play(0, "AGENT_ERROR"))
    h = fx.compute()
    assert h["status"] == h4.FINAL
    assert any(warning in w for w in h["warnings"])
    assert any(warning in line for line in h4.summary_lines(h))


def _compaction_records(root, run_id, records):
    """A run's raw harness compaction records: (attempts, output tokens) each, plus a prompt
    and a summary the script must not read."""
    folder = root / "raw" / "arc_path" / run_id / "harness"
    folder.mkdir(parents=True)
    for i, (attempts, out) in enumerate(records, 1):
        (folder / f"compaction_{i:03d}.json").write_text(json.dumps(
            {"compaction": i, "mechanism": "harness_summary", "attempts": attempts,
             "prompt": {"system_prompt": "SECRET-PROMPT"}, "summary": "SECRET-SUMMARY",
             "usage": {"completion_tokens": out, "reasoning_tokens": out // 2}}),
            encoding="utf-8")


def _r7_grid(fx):
    """MIXED with every S2 run under R7's budget (65,536)."""
    ids = fx.grid(MIXED, skip={(g, "S2") for g in GAMES})
    for g in GAMES:
        ids[(g, "S2")] = fx.run(g, "S2", meta_extra=NEW, **play(MIXED[g]["S2"]))
    return ids


NEVER = {"FT09": [(1, 1508), (1, 3073)], "SB26": [(1, 900)], "R11L": [], "CD82": [(1, 2000)]}


@pytest.mark.parametrize("records, bound, facts", [
    (NEVER, False,
     ("In every S4 run of block 2 the 8,192 budget never bound: 4 summaries, 0 retries, at "
      "most 3,073 output tokens per attempt (from those runs' harness compaction records). So "
      "for the counted S4 runs the step still differs only by native replay and its item "
      "format.")),
    ({**NEVER, "SB26": [(1, 900), (2, 9000)]}, True,
     ("In block 2's S4 runs the 8,192 budget may have bound: 5 summaries, 1 retry, at most "
      "3,073 output tokens per single-attempt summary (1 summary whose largest attempt is not "
      "known) (from those runs' harness compaction records), so the step may also differ by "
      "the summary budget.")),
    ({**NEVER, "CD82": [(1, 8192)]}, True,
     "may have bound: 4 summaries, 0 retries, at most 8,192 output tokens per attempt"),
])
def test_sigma_replays_note_is_computed_from_block_2s_s4_compaction_records(tmp_path, records,
                                                                            bound, facts):
    """Every counted S2 run under 65,536: σ_replay is labelled, and whether S4's 8,192 bound
    is computed from block 2's S4 runs' compaction records (attempts and output tokens only)."""
    fx = H4Fixture(tmp_path)
    ids = _r7_grid(fx)
    for g, recs in records.items():
        _compaction_records(fx.root, ids[(g, "S4")], recs)
    h = fx.compute()
    note = h["sigma_replay_note"]
    assert note["computed"] is True and note["budget_bound"] is bound
    assert note["source"] == "harness compaction records"
    assert sorted(note["s4_runs"]) == sorted(ids[(g, "S4")] for g in GAMES)
    assert sorted(note["s2_runs_at_r7_budget"]) == sorted(ids[(g, "S2")] for g in GAMES)
    assert facts in note["text"]
    assert note["text"].startswith("S2→S4 also changes the summary budget, from S2's 65,536 to "
                                   "S4's 8,192 output tokens (4 of the 4 counted S2 runs "
                                   "played under 65,536). ")
    text = "\n".join(h4.summary_lines(h))
    assert h4.SIGMA_REPLAY_R7_LABEL in text and note["text"] in text
    assert "σ_replay here: in a reading whose S2 runs include one under 65,536" in text
    assert "SECRET" not in text and "SECRET" not in json.dumps(h)


def test_sigma_replays_note_is_quoted_when_an_s4_runs_records_are_missing(tmp_path):
    fx = H4Fixture(tmp_path)
    ids = _r7_grid(fx)
    for g in ("FT09", "SB26", "R11L"):                     # CD82 S4's are not here
        _compaction_records(fx.root, ids[(g, "S4")], NEVER[g])
    note = fx.compute()["sigma_replay_note"]
    assert note["computed"] is False and note["s4_runs"] is None
    assert note["source"] == h4.RECORDED_S4_SOURCE
    assert (note["summaries"], note["retries"], note["max_output_tokens_per_attempt"]) == (
        132, 0, 3073)
    assert "quoted, not recomputed" in note["text"]


# --- at K = 150 ----------------------------------------------------------------------------

def test_the_readings_at_k_with_censoring(tmp_path):
    """R11L S2 ends TIME_BUDGET (not an incident) after 60 actions: censored at K = 150, its
    final value a lower bound. CD82 S4 takes 190 actions and clears level 1 at action 100 and
    level 2 at 160: RHAE 53.87 on its scorecard, but only level 1 (score 1) within 150."""
    fx = H4Fixture(tmp_path)
    fx.grid(MIXED, skip={("R11L", "S2"), ("CD82", "S4")})
    fx.run("R11L", "S2", **play(2, "TIME_BUDGET"))
    slow = {"ending": "GAME_WIN", "level_actions": (100, 60, 30), "levels_completed": 3}
    cd82 = fx.run("CD82", "S4", **slow)
    h = fx.compute()
    k = h["at_k"]
    assert k["K"] == 150 and k["K_role"] == "registered"
    lb = k["lower_bounds"]
    assert lb["censored"] == {"S0": 0, "S2": 1, "S4": 0} and lb["n_units"] == 4
    full = am.score_within([10, 20, 30], [100, 60, 30], 3, 10_000)
    at150 = am.score_within([10, 20, 30], [100, 60, 30], 3, 150)
    assert at150 == pytest.approx(1 / 6) and full == pytest.approx((1 + 200 / 9 + 300) / 6)
    assert h["primary"]["per_game"][3]["rhae"]["S4"] == pytest.approx(full)
    assert lb["per_game"][3]["rhae"]["S4"] == pytest.approx(at150)
    assert lb["means"]["S4"] == pytest.approx((300 + at150) / 4)
    assert lb["levels_cleared_mean"] == pytest.approx({"S0": 0.5, "S2": 1.75, "S4": 2.5})
    assert lb["levels_cleared_S4_minus_S0"] == pytest.approx(2.0)
    wc = k["without_censored"]
    assert [x["game"] for x in wc["left_out"]] == ["R11L"] and wc["n_units"] == 3
    assert wc["censored"] == {"S0": 0, "S2": 0, "S4": 0}
    row = next(r for r in h["runs"] if r["run_id"] == cd82)
    assert row["status_at_K"] == am.OBSERVED and row["rhae_at_K"] == pytest.approx(at150)
    assert lb["shares_reported"] and lb["predictions"] is not None
    text = "\n".join(h4.summary_lines(h))
    assert "(condition at K, reported only)" in text


def test_a_run_without_matched_values_leaves_its_unit_out_at_k_only(tmp_path):
    fx = H4Fixture(tmp_path)
    ids = fx.grid(MIXED)
    path = fx.root / "arc_path" / ids[("SB26", "S2")] / "scorecard.json"
    card = json.loads(path.read_text(encoding="utf-8"))
    card["environments"][0]["runs"][0]["score"] = 7.0       # not ARC's score of its levels
    path.write_text(json.dumps(card), encoding="utf-8")
    h = fx.compute()
    assert h["primary"]["n_units"] == 4
    assert h["primary"]["per_game"][1]["rhae"]["S2"] == 7.0  # the primary reads the scorecard
    lb = h["at_k"]["lower_bounds"]
    assert lb["n_units"] == 3 and [x["game"] for x in lb["left_out"]] == ["SB26"]
    assert "fails analysis.arc_action_matched's checks" in lb["left_out"][0]["why"]
    assert any("fails analysis.arc_action_matched's checks" in w for w in h["warnings"])


# --- checks and outputs --------------------------------------------------------------------

def test_the_context_trims_check(tmp_path):
    fx = H4Fixture(tmp_path)
    fx.grid(MIXED, skip={(g, "S2") for g in GAMES})
    zero = fx.run("FT09", "S2", meta_extra={"context_trims": 0}, **play(2))
    two = fx.run("SB26", "S2", meta_extra={"context_trims": 2}, **play(0))
    none = fx.run("R11L", "S2", **play(2))                  # not recorded
    fx.run("CD82", "S2", meta_extra={"context_trims": 0}, **play(3))
    h = fx.compute()
    t = h["context_trims"]
    assert t["n_runs"] == 4 and zero in t["zero"] and len(t["zero"]) == 2
    assert t["nonzero"] == {two: 2} and t["not_recorded"] == [none]
    row = next(r for r in h["runs"] if r["run_id"] == two)
    assert "context_trims 2, not 0" in row["flags"]
    text = "\n".join(h4.summary_lines(h))
    assert f"**not 0 in {two} (2)**" in text


def test_the_output_is_exactly_the_allowlist(tmp_path):
    fx = H4Fixture(tmp_path)
    secret = "SECRET-VALUE-123"
    extra = {"api_key": secret, "raw_transcript_path": f"results/raw/{secret}",
             "tokens": {"reasoning_tokens": 777_777_777}, "notes": secret,
             "model_returned": ["gemini-3.8-flash"], "config_hash": "c" * 64,
             "config": {"client": {"api_key_env": secret}, "pricing": {"input": 0.123456},
                        "runtime": {"compaction": {"summary_max_output_tokens": 8192}}}}
    for g, per in MIXED.items():
        for c in ("S4", "S0", "S2"):
            fx.run(g, c, meta_extra=extra, card_extra={"opaque": secret}, **play(per[c]))
    out = tmp_path / "out"
    assert fx.main("--out-dir", str(out)) == 0
    assert sorted(p.name for p in out.iterdir()) == sorted([*h4.OUTPUTS, "meta.json"])
    h = json.loads((out / "h4.json").read_text(encoding="utf-8"))
    assert tuple(h) == h4.TOP_FIELDS and all(tuple(r) == h4.RUN_FIELDS for r in h["runs"])
    text = "\n".join(p.read_text(encoding="utf-8") for p in out.iterdir())
    assert secret not in text and "777777777" not in text and "results/raw" not in text
    assert "gemini-3.8-flash" in text                       # the returned model string
    assert "0.123456" not in text                           # of config, only the budget
    assert all((r["config_hash"], r["summary_max_output_tokens"]) == ("c" * 64, 8192)
               for r in h["runs"])
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["experiment"] == "arc_h4" and meta["paid_calls"] == 0
    assert meta["cost_usd"] == 0.0 and meta["outputs"] == list(h4.OUTPUTS)
    assert meta["exit_reason"] == "completed" and meta["config"]["bootstrap_seed"] == SEED + 30
    assert len(meta["runs"]) == 12
    summary = (out / "summary.md").read_text(encoding="utf-8")
    for line in ("## What it does not show", "**One seed per game and config.**",
                 "**A time confound.**", "**Without S1,**", "**No StateCarry evidence,**",
                 "35 distinct", "Descriptive only"):
        assert line in summary
    # every budget is 8,192: no R7 lines, and no note on σ_replay
    assert "R7 changed" not in summary and "D20's yardsticks pool" not in summary
    assert h["sigma_replay_note"] is None and "σ_replay under R7" not in summary


def test_the_default_output_folder_is_under_the_results_root(tmp_path):
    fx = H4Fixture(tmp_path)
    fx.grid(MIXED)
    assert fx.main() == 0
    (folder,) = (fx.root / "arc_h4").iterdir()
    assert sorted(p.name for p in folder.iterdir()) == sorted([*h4.OUTPUTS, "meta.json"])


def test_a_pilot_folder_is_refused(tmp_path, capsys):
    fx = H4Fixture(tmp_path)
    fx.grid(MIXED)
    fx.run("R11L", "S2", experiment="arc_pilot", row=False, **play(0))
    assert fx.main("--no-write", "--allow-incomplete") == 2
    assert "arc_pilot" in capsys.readouterr().err


# --- this checkout's data ------------------------------------------------------------------

def test_this_checkouts_results_give_a_reading_without_crashing(capsys):
    """Whatever S2 folders exist here: with --allow-incomplete the script prints a reading,
    FINAL or PROVISIONAL, and writes nothing. Block 2's gap is 62.59 either way."""
    before = sorted(p.name for p in (h4.RESULTS / "arc_h4").glob("*")) if (
        h4.RESULTS / "arc_h4").is_dir() else []
    assert h4.main(["--no-write", "--allow-incomplete"]) == 0
    text = capsys.readouterr().out
    assert "# H4 on the ARC path runs" in text and "**Status: " in text
    after = sorted(p.name for p in (h4.RESULTS / "arc_h4").glob("*")) if (
        h4.RESULTS / "arc_h4").is_dir() else []
    assert before == after
    h = h4.compute(h4.RESULTS, "now", GIT)
    gap = h["partial"]["G"] if h["primary"] is None else h["primary"]["G"]
    assert gap == pytest.approx(62.5889, abs=1e-4)


BLOCK2 = ("20261006T144656Z-S4-cd82-s1", "20261006T171726Z-S0-ft09-s1",
          "20261007T133444Z-S4-sb26-s1", "20261007T143700Z-S0-sb26-s1",
          "20261008T013832Z-S0-cd82-s1", "20261008T134155Z-S0-r11l-s1",
          "20261008T212807Z-S4-r11l-s1", "20261009T020602Z-S4-ft09-s1",
          "20261009T030646Z-S0-ft09-s101")


def test_block_2s_data_with_synthetic_s2_runs(tmp_path):
    """Block 2's folders with 4 synthetic S2 runs (not data): G = 62.59 (§17.6 change 3) and,
    with the FT09 S0 original (58.17) in place of its re-run (18.11), 52.57. (R6's text says
    52.58, from rounded inputs: 62.59 − (58.17 − 18.11) / 4 = 52.575.)"""
    root = tmp_path / "results"
    for run_id in BLOCK2:
        shutil.copytree(h4.RESULTS / "arc_path" / run_id, root / "arc_path" / run_id)
    shutil.copy(h4.RESULTS / "costs.csv", root / "costs.csv")
    shutil.copytree(cc.the_draw(h4.RESULTS).parent, root / "draw" / "20261002T033145Z")
    for i, g in enumerate(("ft09", "r11l", "sb26", "cd82")):
        run_id = f"2026101{i}T000000Z-S2-{g}-s1"
        d = root / "arc_path" / run_id
        d.mkdir()
        meta = {"experiment": "arc_path", "run_id": run_id, "cell_or_config": "S2",
                "game_requested": g, "seeds": {"replicate_seed": 1}, "rerun_of": None,
                "agent_exit_reason": "ACTION_BUDGET", "exit_reason": "ACTION_BUDGET",
                "started_utc": f"2026-10-1{i}T00:00:00+00:00", "n_calls": 100,
                "latency": {"median_s": 200.0}, "cost_usd": {},
                "truncation_limits": {"max_actions": None}, "context_trims": 0}
        (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        (d / "scorecard.json").write_text(json.dumps(_card((10, 20, 30), 2)), encoding="utf-8")
    h = h4.compute(root, "now", GIT)
    assert h["status"] == h4.FINAL and h["bootstrap_seed"] == SEED + 30
    assert h["units"]["FT09 S0"]["counted"] == "20261009T030646Z-S0-ft09-s101"
    p = h["primary"]
    assert p["G"] == pytest.approx(62.5889, abs=1e-4) and p["shares_reported"]
    assert p["means"]["S2"] == 50.0
    assert sum(p["shares"].values()) == pytest.approx(1.0)
    o = h["sensitivity"]["originals"]
    assert o["G"] == pytest.approx(52.5743, abs=1e-4)
    assert o["substituted"][0]["rhae_original"] == pytest.approx(58.1703, abs=1e-4)
    assert h["sensitivity"]["without_cost_cap"]["n_units"] == 4      # no COST_CAP ending
    assert h["context_trims"]["zero"] and not h["context_trims"]["nonzero"]
