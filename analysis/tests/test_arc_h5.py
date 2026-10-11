"""H5 on ARC (analysis/arc_h5.py; PREREG §3 H5, D35, §17.6 change 4): the per-level rows and
their definitions, the published runs' selection and consistency refusals, the average
marginal effects under both estimators (Firth's and the maximum-likelihood limit) on the
spec's synthetic reference designs, recomputed here independently (direct maximization with
scipy, a reduced fit, statsmodels), the separation LP, the game-cluster bootstrap (seed,
determinism, pairing, duplicated games, undefined resamples), our counted runs (with
checkpoint_c's synthetic folders), the error-ending sensitivity, the wording and the outputs.

Every input here is synthetic, in a results root under tmp_path, except the last three tests:
one checks that the results/decisions.md entry the module cites exists, and two assert counts
and run IDs only on this checkout's committed files (the blind rule: no level is parsed and
nothing about reached or cleared is read)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from collections import Counter

import numpy as np
import pytest
from scipy import optimize, special

from analysis import arc_h5 as h5
from analysis import checkpoint_c as cc
from analysis.tests.test_checkpoint_c import GAMES, GIT, Fixture, _card
from arc.public import sessions
from common import costs

SEED = 4086943125952605534
BOOT = 200
N = 6
SIX = {"G1": (1, 4), "G2": (3, 2), "G3": (4, 0), "G4": (0, 6), "G5": (5, 3), "G6": (2, 5)}
"""The spec's design SIX (§12): {game: (Standard's levels completed, Adapter's)}, 6 levels."""
SIX_G7 = {**SIX, "G7": (6, 6)}
SIX_SEP = {**SIX, "G3": (4, 2)}
AMB = {**SIX, "G3": (3, 0), "G5": (3, 3), "G8": ((2, False), 6)}
STRUCTURAL = {"G1": (2, 5), "G2": (1, 3)}


# --- synthetic runs ------------------------------------------------------------------------------

def acts(lc: int, n: int = N, next_reached: bool = True) -> tuple[int, ...]:
    """5 actions per cleared level, 7 on the level in play (or 0), 0 after it."""
    return tuple(5 if lv <= lc else 7 if lv == lc + 1 and next_reached else 0
                 for lv in range(1, n + 1))


def _lc(v) -> tuple[int, bool]:
    return v if isinstance(v, tuple) else (v, True)


def run_levels(game: str, harness: str, lc: int, *, n: int = N, next_reached: bool = True,
               ending: str | None = None, source: str = "published",
               run_id: str | None = None) -> h5.RunLevels:
    la = acts(lc, n, next_reached)
    ending = ending or ("GAME_WIN" if lc == n else "ACTION_BUDGET")
    kinds = {**h5.PUBLISHED_ENDING_KIND, **h5.OURS_ENDING_KIND}
    return h5.RunLevels(source=source, run_id=run_id or f"{game}-{harness}", game=game,
                        harness=harness, label=harness, effort="high", level_count=n,
                        levels_completed=lc, level_actions=la, ending=ending,
                        ending_kind=kinds[ending], total_actions=sum(la))


def runs_of(design: dict, n: int = N) -> list[h5.RunLevels]:
    out = []
    for g, (s, a) in design.items():
        for h, v in zip(h5.HARNESSES, (s, a), strict=True):
            lc, nxt = _lc(v)
            out.append(run_levels(g, h, lc, n=n, next_reached=nxt))
    return out


def model_of(design: dict, n: int = N) -> h5.ModelRows:
    return h5.rows_to_model([x for r in runs_of(design, n) for x in h5.level_rows(r)])


def independent_rows(design: dict, n: int = N) -> list[tuple[str, int, int, int]]:
    """(game, adapter, deep, cleared) of the early and deep reached levels, written afresh."""
    out = []
    for g, (s, a) in design.items():
        for adapter, v in ((0, s), (1, a)):
            lc, nxt = _lc(v)
            for lv in range(1, n + 1):
                reached = lv <= lc or (lv == lc + 1 and nxt)
                if reached and lv != 3:
                    out.append((g, adapter, int(lv >= 4), int(lv <= lc)))
    return out


def spec_of(design: dict, registered: bool = True) -> h5.Spec:
    runs = runs_of(design)
    return h5.Spec(label="synthetic", data="published", registered=registered, effort="high",
                   harnesses={"standard": "Standard", "provider_adapter": "Adapter"},
                   games=list(design), runs=runs)


# --- an independent fit and AME ------------------------------------------------------------------

def _x(rows, games, cells=(1, 2, 3)):
    """Game dummies and cell indicators (Adapter-early, Standard-deep, Adapter-deep)."""
    cell = [2 * d + a for _, a, d, _ in rows]
    x = [[float(g == gg) for gg in games] + [float(c == k) for k in cells]
         for (g, *_), c in zip(rows, cell, strict=True)]
    return np.array(x), np.array([r[3] for r in rows], float)


def _ml(x, y):
    """ML by scipy's trust-region Newton with the exact gradient and Hessian."""
    def f(b):
        eta = x @ b
        return -float(np.sum(y * eta - np.logaddexp(0.0, eta)))

    def g(b):
        return -(x.T @ (y - special.expit(x @ b)))

    def hess(b):
        p = special.expit(x @ b)
        return x.T @ (x * (p * (1 - p))[:, None])

    res = optimize.minimize(f, np.zeros(x.shape[1]), jac=g, hess=hess, method="trust-exact",
                            options={"gtol": 1e-12})
    return res.x


def _ame(rows, games, alpha: dict, gamma: dict) -> dict:
    """A_b as the mean over the band's rows of p(game, Adapter, b) − p(game, Standard, b), one
    row at a time (no weights)."""
    out = {}
    for d, band in ((0, "early"), (1, "deep")):
        vals = [special.expit(alpha[g] + gamma[2 * d + 1]) - special.expit(alpha[g] + gamma[2 * d])
                for g, _, dd, _ in rows if dd == d]
        out[band] = float(np.mean(vals))
    return out


def _ml_ames(design: dict) -> dict:
    rows = independent_rows(design)
    games = list(design)
    x, y = _x(rows, games)
    b = _ml(x, y)
    alpha = dict(zip(games, b[:len(games)], strict=True))
    gamma = {0: 0.0, 1: b[-3], 2: b[-2], 3: b[-1]}
    return _ame(rows, games, alpha, gamma)


# --- A. rows and definitions ---------------------------------------------------------------------

def test_rows_of_a_run_that_ended_on_level_4():
    r = h5.RunLevels("published", "r", "G", "standard", "x", "high", 6, 3, (4, 7, 9, 12, 0, 0),
                     "ERROR_OR_CLOSED", "error", 32)
    rows = h5.level_rows(r)
    assert [x.level for x in rows] == [1, 2, 3, 4]
    assert [x.cleared for x in rows] == [1, 1, 1, 0]
    assert [x.band for x in rows] == ["early", "early", "level_3", "deep"]
    assert r.ended_level == 4 and r.last_reached_level == 4
    assert [x.ended_here for x in rows] == [False, False, False, True]
    assert [x.ended_by_error for x in rows] == [False, False, False, True]


def test_a_level_in_play_with_no_action_is_not_a_row_and_nothing_is_dropped():
    r = run_levels("G", "standard", 2, next_reached=False, ending="ERROR_OR_CLOSED")
    rows = h5.level_rows(r)
    assert [x.level for x in rows] == [1, 2] and all(x.cleared for x in rows)
    assert r.ended_level == 3 and not any(x.ended_here or x.ended_by_error for x in rows)


def test_a_won_run_cleared_every_level_and_ended_on_none():
    r = run_levels("G", "provider_adapter", 6)
    rows = h5.level_rows(r)
    assert [x.level for x in rows] == [1, 2, 3, 4, 5, 6] and all(x.cleared for x in rows)
    assert r.ended_level is None and not any(x.ended_here for x in rows)


def test_level_3_is_in_the_raw_tables_but_not_in_the_model():
    r = h5.compute_reading(spec_of(SIX), [x for r in runs_of(SIX) for x in h5.level_rows(r)],
                           SEED, 20, "firth", [])
    n = r["n_rows"]
    level_3 = n["level_3"]["standard"] + n["level_3"]["provider_adapter"]
    assert level_3 > 0
    assert n["in_model"] == 37 == sum(n[b][h] for b in h5.MODEL_BANDS for h in h5.HARNESSES)
    assert r["raw"]["bands"]["level_3"]["standard"]["reached"] == n["level_3"]["standard"]
    assert {x["level"]: x["band"] for x in r["per_level"]}[3] == "level_3"
    assert len(model_of(SIX).y) == 37


def test_the_deep_band_pools_levels_4_to_10():
    r = run_levels("G", "standard", 9, n=10)
    rows = h5.level_rows(r)
    assert [x.level for x in rows if x.band == "deep"] == [4, 5, 6, 7, 8, 9, 10]
    m = h5.rows_to_model(rows)
    assert int((m.cell == 2).sum()) == 7


# --- the published slice -------------------------------------------------------------------------

REAL_COLUMNS = ["variant_id", "page_score", "game", "game_id", "harness", "effort", "config",
                "config_matches_variant", "guid", "score", "state", "levels_completed",
                "level_count", "total_actions", "resets", "final_level", "final_level_actions",
                "final_level_baseline", "final_level_budget", "budget_margin", "open_at",
                "last_update", "duration_h", "level_actions", "level_baselines",
                "inferred_ending"]


def pub_row(game: str, harness: str, lc: int, *, effort: str = "high", n: int = N,
            next_reached: bool = True, duration_h: float = 1.0, in_play: int | None = None,
            guid: str | None = None) -> dict:
    la = list(acts(lc, n, next_reached))
    if in_play is not None and lc < n:
        la[lc] = in_play
    lb = [10] * n
    state = "WIN" if lc == n else "NOT_FINISHED"
    i = min(lc, n - 1)
    ending = sessions.infer_ending(state, la[i], sessions.level_budget(lb[i]), duration_h * 3600)
    pa = harness == "provider_adapter"
    return {"variant_id": "v", "page_score": "0", "game": game, "game_id": game.lower(),
            "harness": harness, "effort": effort,
            "config": f"google-gemini-3-8-flash-{effort}" + ("-provider-adapter" if pa else ""),
            "config_matches_variant": "True", "guid": guid or f"{game}-{harness}-{effort}",
            "score": "0", "state": state, "levels_completed": str(lc), "level_count": str(n),
            "total_actions": str(sum(la)), "resets": "0", "final_level": str(i + 1),
            "final_level_actions": str(la[i]), "final_level_baseline": str(lb[i]),
            "final_level_budget": str(sessions.level_budget(lb[i])), "budget_margin": "0",
            "open_at": "2026-09-10T00:00:00+00:00", "last_update": "2026-09-10T01:00:00+00:00",
            "duration_h": f"{duration_h:.6g}", "level_actions": " ".join(map(str, la)),
            "level_baselines": " ".join(map(str, lb)), "inferred_ending": ending}


def pub_games(n_games: int = 25) -> list[str]:
    return [f"A{i:02d}" for i in range(1, n_games + 1)]


def pub_rows(seed: int = 5, efforts=("high", "medium", "low")) -> list[dict]:
    """25 games × 2 harnesses per effort, levels completed drawn from a fixed generator; level
    counts 6 to 8; endings mixed (ACTION_BUDGET, TIME_BUDGET, ERROR_OR_CLOSED, GAME_WIN)."""
    rng = np.random.default_rng(seed)
    rows = []
    for effort in efforts:
        for g in pub_games():
            n = int(rng.integers(6, 9))
            for h in h5.HARNESSES:
                lc = int(rng.integers(0, n + 1))
                kind = int(rng.integers(0, 3))
                rows.append(pub_row(g, h, lc, effort=effort, n=n,
                                    duration_h=12.0 if kind == 1 else 1.0,
                                    in_play=50 if kind == 2 else None))
    return rows


def write_slice(root, rows: list[dict], columns=REAL_COLUMNS, meta: dict | None = None):
    d = root / h5.PUBLISHED_SLICE
    d.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    (d / "per_run.csv").write_bytes(buf.getvalue().encode("utf-8"))
    m = meta or {"experiment": "arc_public_ops", "slice": "operational (PLAN §16.3); no H5 "
                                                          "quantities"}
    (d / "meta.json").write_text(json.dumps(m), encoding="utf-8")
    return d


def sha(d) -> str:
    return hashlib.sha256((d / "per_run.csv").read_bytes()).hexdigest()


class H5Fixture(Fixture):
    """checkpoint_c's results root, with SEED in draw.json, 6-level scorecards and, if asked, a
    synthetic published slice."""

    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        path = next((self.root / "draw").glob("*/draw.json"))
        draw = json.loads(path.read_text(encoding="utf-8"))
        draw["seed"] = {"source": "nist", "seed": SEED}
        path.write_text(json.dumps(draw), encoding="utf-8")

    def run6(self, game, config, lc, ending="ACTION_BUDGET", *, n=N, seed=1, rerun_of=None,
             next_reached=True, **kw):
        la = acts(lc, n, next_reached)
        kw.setdefault("median", 50.0 if config == "S0" else 10.0)
        run_id = self.run(game, config, ending=ending, level_actions=la, levels_completed=lc,
                          seed=seed, rerun_of=rerun_of, card=False, **kw)
        self._json(self.root / "arc_path" / run_id / "scorecard.json",
                   _card(la, lc, baselines=(10,) * n))
        return run_id

    def block6(self, design: dict | None = None, endings: dict | None = None) -> dict:
        """One seed-1 run per path game and S0/S4: {game: (S0's levels, S4's)}."""
        design = design or {"FT09": (1, 4), "SB26": (3, 5), "R11L": (4, 3), "CD82": (2, 6)}
        ids = {}
        for g, (s0, s4) in design.items():
            for c, lc in (("S4", s4), ("S0", s0)):
                e = (endings or {}).get((g, c)) or ("GAME_WIN" if lc == N else "ACTION_BUDGET")
                ids[(g, c)] = self.run6(g, c, lc, e)
        return ids

    def compute(self, **kw):
        kw.setdefault("data", "ours")
        kw.setdefault("boot", BOOT)
        return h5.compute(self.root, "now", GIT, **kw)

    def main(self, *args):
        return h5.main(["--results-root", str(self.root), *args])


@pytest.fixture
def pinned(monkeypatch):
    """Pin the synthetic slice's hash as the registered one."""
    def pin(d):
        monkeypatch.setattr(h5, "PUBLISHED_SHA256", sha(d))
        return d
    return pin


# --- B. the published runs: selection and consistency ---------------------------------------------

def _first_high(rows):
    return next(i for i, r in enumerate(rows) if r["effort"] == "high")


def _cleared_zero(rows):
    i = next(i for i, r in enumerate(rows) if r["effort"] == "high"
             and int(r["levels_completed"]) >= 2)
    la = [int(a) for a in rows[i]["level_actions"].split()]
    la[0], la[1] = 0, la[1] + la[0]
    rows[i]["level_actions"] = " ".join(map(str, la))


def _after_play(rows):
    i = next(i for i, r in enumerate(rows) if r["effort"] == "high"
             and int(r["levels_completed"]) + 2 < int(r["level_count"]))
    la = [int(a) for a in rows[i]["level_actions"].split()]
    la[int(rows[i]["levels_completed"]) + 2] = 3
    rows[i]["level_actions"] = " ".join(map(str, la))
    rows[i]["total_actions"] = str(sum(la))


def _set(field, value, cond=lambda r: True):
    def f(rows):
        i = next(i for i, r in enumerate(rows) if r["effort"] == "high" and cond(r))
        rows[i][field] = value(rows[i]) if callable(value) else value
    return f


def _drop_game(rows):
    rows[:] = [r for r in rows if not (r["effort"] == "high" and r["game"] == "A07")]


def _duplicate(rows):
    i = _first_high(rows)
    rows.append({**rows[i], "guid": "another"})


DEFECTS = {
    "a cleared level with no action": (_cleared_zero, "check 4"),
    "actions after the level in play": (_after_play, "check 5"),
    "the level actions do not sum to the total": (
        _set("total_actions", lambda r: str(int(r["total_actions"]) + 1)), "check 2"),
    "wrong list lengths": (
        _set("level_baselines", lambda r: " ".join(r["level_baselines"].split()[:-1])),
        "check 1"),
    "levels completed above the level count": (
        _set("levels_completed", lambda r: str(int(r["level_count"]) + 1)), "check "),
    "WIN without every level": (
        _set("state", "WIN", lambda r: int(r["levels_completed"]) < int(r["level_count"])),
        "check 6"),
    "an inferred ending that contradicts its re-derivation": (
        _set("inferred_ending", "TIME_BUDGET",
             lambda r: r["inferred_ending"] == "ERROR_OR_CLOSED"), "check 7"),
    "config_matches_variant false": (_set("config_matches_variant", "False"),
                                     "config_matches_variant"),
    "24 games": (_drop_game, "24 games"),
    "a duplicate (game, harness)": (_duplicate, "more than one run"),
}


@pytest.mark.parametrize("name", list(DEFECTS))
def test_a_defect_at_high_effort_refuses(tmp_path, pinned, name):
    fx = H5Fixture(tmp_path)
    rows = pub_rows()
    DEFECTS[name][0](rows)
    pinned(write_slice(fx.root, rows))
    with pytest.raises(h5.Refusal, match=DEFECTS[name][1]):
        fx.compute(data="published", exploratory=False)
    assert fx.main("--data", "published", "--no-write", "--boot", "5") == 2


def test_a_missing_column_or_the_wrong_slice_refuses(tmp_path, pinned):
    fx = H5Fixture(tmp_path)
    pinned(write_slice(fx.root, pub_rows(), columns=[c for c in REAL_COLUMNS
                                                     if c != "inferred_ending"]))
    with pytest.raises(h5.Refusal, match="lacks the columns inferred_ending"):
        fx.compute(data="published")
    write_slice(fx.root, pub_rows(), meta={"experiment": "arc_path", "slice": "no H5 "
                                                                              "quantities"})
    with pytest.raises(h5.Refusal, match="experiment 'arc_path'"):
        fx.compute(data="published")
    write_slice(fx.root, pub_rows(), meta={"experiment": "arc_public_ops", "slice": "full"})
    with pytest.raises(h5.Refusal, match="does not say"):
        fx.compute(data="published")


def test_a_defect_at_an_exploratory_effort_skips_it_and_the_high_reading_stands(tmp_path,
                                                                                 pinned):
    fx = H5Fixture(tmp_path)
    rows = pub_rows()
    i = next(i for i, r in enumerate(rows) if r["effort"] == "medium")
    rows[i]["total_actions"] = str(int(rows[i]["total_actions"]) + 1)
    pinned(write_slice(fx.root, rows))
    h = fx.compute(data="published", boot=20)
    x = h["published_exploratory"]
    assert x["efforts"]["medium"] is None and "check 2" in x["skipped"]["medium"]
    assert x["efforts"]["low"] is not None and "low" not in x["skipped"]
    assert any(w.startswith("exploratory effort medium skipped") for w in h["warnings"])
    assert h["published"]["n_games"] == 25 and h["published"]["n_runs"] == 50
    text = "\n".join(h5.summary_lines(h))
    assert "Skipped (a data problem; the registered reading stands): run " in text


def test_another_published_file_is_read_and_marks_the_output_provisional(tmp_path):
    fx = H5Fixture(tmp_path)
    write_slice(fx.root, pub_rows())          # not pinned: PUBLISHED_SHA256 is the real hash
    h = fx.compute(data="published", boot=10, exploratory=False)
    assert h["status"] == h5.PROVISIONAL
    assert h["inputs"]["published_sha256_matches_pinned"] is False
    assert [x for x in h["provisional_reasons"] if "not the registered input" in x] == [
        (f"published per_run.csv has sha256 {h['inputs']['published_per_run_sha256']}, not the "
        f"pinned {h5.PUBLISHED_SHA256}: not the registered input")]
    assert h["published"]["primary"]["contrast"] is not None
    assert "(**not the pinned file: PROVISIONAL**)" in "\n".join(h5.summary_lines(h))


# --- C. AMEs and estimators ----------------------------------------------------------------------

def test_the_ame_on_given_coefficients_weighs_games_by_their_band_rows():
    """Two games; G2's Standard run reached no deep level, so its Standard-deep prediction is
    the counterfactual α_G2 + γ_Sd, weighted by G2's 3 Adapter deep rows."""
    rows = ([("G1", 0, 0, 1)] * 2 + [("G1", 1, 0, 1)] * 2 + [("G1", 0, 1, 0)]
            + [("G1", 1, 1, 1)] * 2 + [("G2", 0, 0, 1)] * 2 + [("G2", 1, 0, 1)] * 2
            + [("G2", 1, 1, 0)] * 3)
    m = h5.model_rows([r[0] for r in rows], [2 * r[2] + r[1] for r in rows],
                      [r[3] for r in rows])
    alpha, gamma = {0: 0.0, 1: 1.0}, {0: 0.0, 1: 0.5, 2: -1.0, 3: 0.2}
    got = h5.band_ames(m, lambda g, c: (float(special.expit(alpha[g] + gamma[c])), "given"))
    e = special.expit
    early = (4 * (e(0.5) - e(0.0)) + 4 * (e(1.5) - e(1.0))) / 8
    deep = (3 * (e(0.2) - e(-1.0)) + 3 * (e(1.2) - e(0.0))) / 6
    assert got["early"]["value"] == pytest.approx(early, abs=1e-15)
    assert got["deep"]["value"] == pytest.approx(deep, abs=1e-15)
    assert got["deep"]["weight"] == {0: 3, 1: 3}
    assert got["deep"]["delta"][1] == pytest.approx(e(1.2) - e(0.0))


def test_six_the_ml_limit_is_ordinary_ml():
    m = model_of(SIX)
    assert len(m.y) == 37 and int((m.cell < 2).sum()) == 22 and int((m.cell >= 2).sum()) == 15
    ml = h5.fit_ml_limit(m)
    assert ml["n_separated_rows"] == 0
    assert ml["A_early"] == pytest.approx(0.077590351, abs=1e-9)
    assert ml["A_deep"] == pytest.approx(0.068322589, abs=1e-9)
    assert ml["contrast"] == pytest.approx(-0.009267762, abs=1e-9)
    ind = _ml_ames(SIX)                                    # scipy, written afresh
    assert ml["A_early"] == pytest.approx(ind["early"], abs=1e-8)
    assert ml["A_deep"] == pytest.approx(ind["deep"], abs=1e-8)
    stop = h5.fit_statsmodels(m)
    assert stop["A_early"] == pytest.approx(ml["A_early"], abs=1e-8)
    assert stop["A_deep"] == pytest.approx(ml["A_deep"], abs=1e-8)
    assert ml["logit_interaction"] == pytest.approx(-1.205826 + 1.510446 - 0.705541, abs=1e-5)


def test_six_with_a_game_both_runs_won_adds_zero():
    m = model_of(SIX_G7)
    ml = h5.fit_ml_limit(m)
    assert ml["n_separated_rows"] == 10                    # G7's 4 early and 6 deep rows
    code = m.clusters.index("G7")
    for b in h5.MODEL_BANDS:
        assert ml["bands"][b]["delta"][code] == 0.0
    six = h5.fit_ml_limit(model_of(SIX))
    assert ml["A_early"] == pytest.approx(six["A_early"] * 22 / 26, abs=1e-12)
    assert ml["A_deep"] == pytest.approx(six["A_deep"] * 15 / 21, abs=1e-12)
    assert ml["A_early"] == pytest.approx(0.065653374, abs=1e-9)
    assert ml["A_deep"] == pytest.approx(0.048801849, abs=1e-9)


def test_six_sep_separates_the_adapter_early_rows_and_equals_a_reduced_fit():
    m = model_of(SIX_SEP)
    d = h5.Design(m)
    uniq, x, k, n = d.patterns()
    sep = h5.separated_patterns(x, k, n)
    assert set((uniq[sep] % 4).tolist()) == {1}            # every Adapter-early pattern
    assert int(n[sep].sum()) == 12 == int((m.cell == 1).sum())
    ml = h5.fit_ml_limit(m)
    assert ml["n_separated_rows"] == 12
    # the reduced fit: Adapter-early rows fixed at 1, the rest fitted without their column
    rows = independent_rows(SIX_SEP)
    games = list(SIX_SEP)
    rest = [r for r in rows if not (r[1] == 1 and r[2] == 0)]
    xr, yr = _x(rest, games, cells=(2, 3))
    b = _ml(xr, yr)
    alpha = dict(zip(games, b[:len(games)], strict=True))
    early = np.mean([1.0 - special.expit(alpha[g]) for g, _, d_, _ in rows if d_ == 0])
    deep = np.mean([special.expit(alpha[g] + b[-1]) - special.expit(alpha[g] + b[-2])
                    for g, _, d_, _ in rows if d_ == 1])
    assert ml["A_early"] == pytest.approx(early, abs=1e-8)
    assert ml["A_deep"] == pytest.approx(deep, abs=1e-8)
    assert ml["A_early"] == pytest.approx(0.180607074, abs=1e-9)
    assert ml["A_deep"] == pytest.approx(0.281579606, abs=1e-9)
    stop = h5.fit_statsmodels(m)
    assert abs(stop["A_early"] - ml["A_early"]) < 1e-6 and abs(stop["A_deep"] - ml["A_deep"]) < 1e-6
    firth = h5.fit_firth(m)
    assert firth["A_early"] == pytest.approx(0.187274424, abs=1e-8)
    assert firth["A_deep"] == pytest.approx(0.199631563, abs=1e-8)
    r = h5.full_reading(spec_of(SIX_SEP), SEED, 20, "firth", [], sensitivity=False,
                        common_support=False)
    text = "\n".join(h5.reading_lines(r))
    assert "Firth (`firth`) | +0.187 | +0.200" in text
    assert "ML limit (`ml_limit`) | +0.181 | +0.282" in text


def test_amb_the_ml_limit_of_a_deep_is_not_identified_and_the_rule_falls_back_to_firth():
    m = model_of(AMB)
    ml = h5.fit_ml_limit(m)
    assert ml["A_early"] is not None and ml["A_deep"] is None
    assert ml["why_undefined"]["A_deep"] == "not identified in the ML limit"
    assert ml["bands"]["deep"]["how"]["not identified"] >= 1
    firth = h5.fit_firth(m)
    assert firth["defined"] and firth["A_deep"] is not None
    r = h5.full_reading(spec_of(AMB), SEED, 30, "ml_limit_or_firth", [], sensitivity=False,
                        common_support=False)
    assert r["primary"]["source"] == "firth" and r["primary"]["rule"] == "ml_limit_or_firth"
    assert r["primary"]["fallback_reason"] == "not identified in the ML limit"
    assert r["primary"]["contrast"] == pytest.approx(firth["contrast"])
    assert r["bootstrap"]["primary"]["n_firth_fallback"] >= 1
    text = "\n".join(h5.reading_lines(r))
    assert "rule in force `ml_limit_or_firth`, estimate from `firth`" in text
    assert "Rule in force (`ml_limit_or_firth`)" in text
    assert ("- Firth decides this reading: C is undefined in the ML limit (not identified in "
            "the ML limit).") in text
    r2 = h5.full_reading(spec_of(AMB), SEED, 30, "firth", [], sensitivity=False,
                         common_support=False)
    assert r2["primary"]["source"] == "firth" and r2["other_estimator_sign_agrees"] is None
    assert r2["primary"]["fallback_reason"] is None


FLIP = {"G1": (6, 0), "G2": (3, 0), "G3": (1, 3), "G4": (5, 5)}
"""4 games, no separation: Firth's C and the ML fit's C differ in sign."""
LOGIT = {"G1": (5, 0), "G2": (1, 3), "G3": (5, 0), "G4": (4, 5)}
"""4 games, no separation: the ML fit's C and its logit-scale interaction differ in sign."""


def test_firth_and_the_ml_fit_can_give_c_opposite_signs_without_separation():
    """The module docstring's ruling cites this design."""
    m = model_of(FLIP)
    ml, f = h5.fit_ml_limit(m), h5.fit_firth(m)
    assert ml["n_separated_rows"] == 0
    ind_ml, ind_f = _ml_ames(FLIP), _firth_direct(FLIP)
    assert ml["contrast"] == pytest.approx(ind_ml["deep"] - ind_ml["early"], abs=1e-8)
    assert f["contrast"] == pytest.approx(ind_f["deep"] - ind_f["early"], abs=1e-6)
    assert ml["contrast"] == pytest.approx(-0.0077155, abs=1e-6)
    assert f["contrast"] == pytest.approx(+0.0013348, abs=1e-6)
    r = h5.full_reading(spec_of(FLIP), SEED, 10, "ml_limit_or_firth", [], sensitivity=False,
                        common_support=False)
    assert r["primary"]["source"] == "ml_limit" and r["other_estimator_sign_agrees"] is False
    assert r["primary"]["verdict"] == h5.VERDICT_NOT_POSITIVE
    assert "C = +0.001, sign positive: **its sign differs (flagged)**." in "\n".join(
        h5.reading_lines(r))


def test_a_logit_interaction_of_the_other_sign_is_flagged():
    m = model_of(LOGIT)
    ml = h5.fit_ml_limit(m)
    assert ml["n_separated_rows"] == 0
    rows = independent_rows(LOGIT)
    b = _ml(*_x(rows, list(LOGIT)))
    assert ml["logit_interaction"] == pytest.approx(b[-1] - b[-2] - b[-3], abs=1e-6)
    assert ml["contrast"] < 0 < ml["logit_interaction"]
    r = h5.full_reading(spec_of(LOGIT), SEED, 10, "ml_limit_or_firth", [], sensitivity=False,
                        common_support=False)
    assert r["primary"]["source"] == "ml_limit" and r["primary"]["logit_sign_disagrees"] is True
    assert "**Its sign differs from C's (flagged).**" in "\n".join(h5.reading_lines(r))
    six = h5.full_reading(spec_of(SIX), SEED, 10, "ml_limit_or_firth", [], sensitivity=False,
                          common_support=False)
    assert six["primary"]["contrast"] < 0 and six["primary"]["logit_interaction"] < 0
    assert six["primary"]["logit_sign_disagrees"] is False


SIX7 = {**SIX, "G7": (4, 5)}
"""SIX with a second game where both harnesses reached a deep level."""


def test_the_tables_by_hand():
    """Per level, deep support, the extrapolated share and the common-support selection,
    against a hand count. SIX per level (reached, cleared): Standard (6, 5), (5, 4), (4, 3),
    (3, 2), (2, 1), (1, 0); Adapter (6, 5), (5, 5), (5, 4), (4, 3), (3, 2), (2, 1). Deep
    support: G5 both; G1, G4, G6 Adapter only; G2, G3 Standard only. SIX7 adds G7 (both)."""
    r = h5.full_reading(spec_of(SIX), SEED, 10, "ml_limit_or_firth", [], sensitivity=False,
                        common_support=True)
    want = {"standard": [(6, 5), (5, 4), (4, 3), (3, 2), (2, 1), (1, 0)],
            "provider_adapter": [(6, 5), (5, 5), (5, 4), (4, 3), (3, 2), (2, 1)]}
    assert [x["level"] for x in r["per_level"]] == [1, 2, 3, 4, 5, 6]
    for h, cells in want.items():
        assert [(x[h]["reached"], x[h]["cleared"]) for x in r["per_level"]] == cells
        assert all(x[h]["n_runs"] == 6 for x in r["per_level"])
    assert r["deep_support"] == {"both": 1, "adapter only": 3, "standard only": 2, "neither": 0}
    assert {g["game"]: g["deep_support"] for g in r["per_game"]} == {
        "G1": "adapter only", "G2": "standard only", "G3": "standard only",
        "G4": "adapter only", "G5": "both", "G6": "adapter only"}
    # deep rows 15; G5's 3 Standard and 1 Adapter rows are the only two-sided ones
    assert r["extrapolated_share_deep"] == pytest.approx(11 / 15, abs=1e-12)
    cs = r["common_support"]
    assert cs["computed"] is False and cs["games"] == ["G5"] and cs["reading"] is None
    assert cs["why_not"].startswith("1 game(s) where both harnesses reached a deep level")

    r7 = h5.full_reading(spec_of(SIX7), SEED, 10, "ml_limit_or_firth", [], sensitivity=False,
                         common_support=True)
    assert r7["deep_support"] == {"both": 2, "adapter only": 3, "standard only": 2,
                                  "neither": 0}
    # G7 adds 2 Standard and 3 Adapter deep rows, both sides
    assert r7["extrapolated_share_deep"] == pytest.approx(11 / 20, abs=1e-12)
    cs = r7["common_support"]
    assert cs["computed"] is True and cs["games"] == ["G5", "G7"]
    x = cs["reading"]
    assert x["registered"] is False and x["games"] == ["G5", "G7"] and x["n_runs"] == 4
    assert {g["game"] for g in x["per_game"]} == {"G5", "G7"}
    raw = x["raw"]["bands"]
    assert (raw["early"]["standard"]["reached"], raw["early"]["standard"]["cleared"]) == (4, 4)
    assert (raw["deep"]["standard"]["reached"], raw["deep"]["standard"]["cleared"]) == (5, 3)
    assert (raw["early"]["provider_adapter"]["reached"],
            raw["early"]["provider_adapter"]["cleared"]) == (4, 4)
    assert (raw["deep"]["provider_adapter"]["reached"],
            raw["deep"]["provider_adapter"]["cleared"]) == (4, 2)
    alone = {"G5": SIX["G5"], "G7": SIX7["G7"]}
    for name, fit in (("firth", h5.fit_firth), ("ml_limit", h5.fit_ml_limit)):
        assert x["estimates"][name]["contrast"] == pytest.approx(
            fit(model_of(alone))["contrast"], abs=1e-12)
    assert x["bootstrap"]["n_games"] == 2


def test_structural_absence_leaves_a_deep_and_c_undefined():
    m = model_of(STRUCTURAL)
    for est in (h5.fit_firth(m), h5.fit_ml_limit(m)):
        assert est["A_deep"] is None and est["contrast"] is None
        assert est["why_undefined"]["A_deep"] == "Standard reached no deep level"
        assert est["A_early"] is not None
    r = h5.full_reading(spec_of(STRUCTURAL), SEED, 20, "firth", [], sensitivity=False,
                        common_support=False)
    assert r["primary"]["verdict"] == "cannot be computed: Standard reached no deep level"
    assert r["primary"]["A_early"] is not None
    assert r["bootstrap"]["primary"]["contrast"]["n_defined"] == 0


def test_the_separation_lp_on_textbook_cases():
    t = np.array([-2.0, -1.0, 1.0, 2.0])
    x = np.column_stack([np.ones(4), t])
    assert h5.separated_rows(x, [0, 0, 1, 1]).tolist() == [True] * 4         # complete
    x = np.column_stack([np.ones(4), [0.0, 0.0, 1.0, 1.0]])
    assert h5.separated_rows(x, [0, 0, 0, 1]).tolist() == [True, True, False, False]  # quasi
    assert h5.separated_rows(x, [0, 1, 0, 1]).tolist() == [False] * 4        # overlap


def _minus_penalized(b, x, y):
    """Minus Firth's penalized log-likelihood, written afresh (slogdet)."""
    eta = x @ b
    p = 1.0 / (1.0 + np.exp(-eta))
    sign, logdet = np.linalg.slogdet(x.T @ (x * (p * (1.0 - p))[:, None]))
    assert sign > 0
    return -(float(np.sum(y * eta - np.logaddexp(0.0, eta))) + 0.5 * logdet)


def _firth_direct(design):
    rows = independent_rows(design)
    games = list(design)
    x, y = _x(rows, games)
    res = optimize.minimize(_minus_penalized, np.zeros(x.shape[1]), args=(x, y), method="BFGS",
                            options={"gtol": 1e-10})
    b = res.x
    alpha = dict(zip(games, b[:len(games)], strict=True))
    return _ame(rows, games, alpha, {0: 0.0, 1: b[-3], 2: b[-2], 3: b[-1]})


def test_firth_gets_the_design_and_matches_a_direct_maximization():
    f = h5.fit_firth(model_of(SIX))
    assert f["optimizer"] == h5.FIRTH_OPTIMIZERS[0]
    ind = _firth_direct(SIX)
    assert f["A_early"] == pytest.approx(ind["early"], abs=1e-6)
    assert f["A_deep"] == pytest.approx(ind["deep"], abs=1e-6)
    assert f["A_early"] == pytest.approx(0.070648154, abs=1e-8)
    assert f["A_deep"] == pytest.approx(0.059026240, abs=1e-8)


def test_where_firth_fe_logit_cycles_the_line_search_finds_the_same_maximum():
    """firth_fe_logit's full scoring steps settle into a 2-cycle around the maximum on this
    design and it returns None; the line search converges to the maximum found directly."""
    design = {"G1": (0, 3), "G2": (3, 4)}
    m = model_of(design)
    d = h5.Design(m)
    assert h5.h13.firth_fe_logit(m.y, m.codes, d.z()) is None
    f = h5.fit_firth(m)
    assert f["optimizer"] == h5.FIRTH_OPTIMIZERS[1] and f["defined"]
    ind = _firth_direct(design)
    assert f["A_early"] == pytest.approx(ind["early"], abs=1e-6)
    assert f["A_deep"] == pytest.approx(ind["deep"], abs=1e-6)


def _firth_bfgs(m: h5.ModelRows) -> dict:
    """Firth's AMEs by BFGS from 0 with the penalized log-likelihood's exact gradient, written
    afresh (hat values from an explicit inverse)."""
    d = h5.Design(m)
    x = np.column_stack([np.eye(m.n_clusters)[m.codes], d.z()])
    y = m.y

    def grad(b):
        mu = special.expit(x @ b)
        w = mu * (1 - mu)
        h = w * np.einsum("ij,jk,ik->i", x, np.linalg.inv(x.T @ (x * w[:, None])), x)
        return -(x.T @ (y - mu + h * (0.5 - mu)))

    res = optimize.minimize(lambda b: _minus_penalized(b, x, y), np.zeros(x.shape[1]),
                            jac=grad, method="BFGS",
                            options={"gtol": 1e-12, "maxiter": 10_000})
    g = m.n_clusters
    return h5._from_coefficients(m, d, res.x[:g], res.x[g:], "bfgs")


def test_the_line_search_matches_an_independent_maximization_where_firth_fe_logit_fails():
    rng = np.random.default_rng(3)
    found = 0
    for _ in range(400):
        m = model_of(_random_design(rng, 4))
        f = h5.fit_firth(m)
        if f["optimizer"] != h5.FIRTH_OPTIMIZERS[1]:
            continue
        found += 1
        ref = _firth_bfgs(m)
        for q in ("A_early", "A_deep"):
            assert (f[q] is None) == (ref[q] is None)
            if f[q] is not None:
                assert abs(f[q] - ref[q]) < 1e-6
        if found == 6:
            break
    assert found == 6


def test_the_exact_identification_test_adds_identified_ames_that_statsmodels_confirms(
        monkeypatch):
    """The spec's single-pattern test is `MLLimit.limit` without its LP (`_cone`); the AMEs
    only the LP identifies agree with statsmodels' stopping point."""
    rng = np.random.default_rng(29)
    designs = [model_of(_random_design(rng, int(rng.integers(2, 8)))) for _ in range(120)]
    exact = [h5.fit_ml_limit(m) for m in designs]
    monkeypatch.setattr(h5.MLLimit, "_cone", lambda self, v: False)
    single = [h5.fit_ml_limit(m) for m in designs]
    extra = 0
    for m, a, b in zip(designs, exact, single, strict=True):
        for q in ("A_early", "A_deep"):
            if b[q] is not None:
                assert a[q] == pytest.approx(b[q], abs=1e-12)
            elif a[q] is not None:
                extra += 1
                assert abs(h5.fit_statsmodels(m)[q] - a[q]) < 1e-5
    assert extra > 0


def _random_design(rng, n_games):
    design = {}
    for g in range(n_games):
        design[f"G{g:02d}"] = tuple((int(rng.integers(0, N + 1)), bool(rng.random() < 0.85))
                                    for _ in range(2))
    return design


def test_statsmodels_stopping_point_agrees_wherever_the_ml_limit_is_identified():
    rng = np.random.default_rng(17)
    compared = 0
    for _ in range(200):
        m = model_of(_random_design(rng, int(rng.integers(3, 26))))
        ml, stop = h5.fit_ml_limit(m), h5.fit_statsmodels(m)
        for q in ("A_early", "A_deep"):
            if ml[q] is not None and stop is not None and stop[q] is not None:
                assert abs(ml[q] - stop[q]) < 1e-5
                compared += 1
    assert compared > 300


def test_an_infinite_limit_through_several_separated_patterns_is_identified():
    """G1: Standard cleared nothing; Adapter cleared levels 1-3 and failed level 4. G2:
    Standard cleared 1-3 and failed level 4; Adapter cleared 1-4 and failed level 5. G1's
    Standard-deep counterfactual x = x(G1, S, e) + x(G2, S, d) − x(G2, S, e) goes to −∞ along
    every maximizing sequence, although x − x_s is in the LCM's row space for no single
    separated pattern x_s (the spec's test): A_deep = (1 × 0 + 3 × 1/2) / 4."""
    m = model_of({"G1": (0, 3), "G2": (3, 4)})
    e = h5.MLLimit(m)
    x = e.design.x(0, 2)
    assert not e.in_rowspace(x)
    assert not any(e.in_rowspace(x - xs) for xs in e.sep_x)
    assert e.limit(x) == ("-inf", None)
    assert e.predict(0, 2) == (0.0, "separated-extrapolated")
    ml = h5.fit_ml_limit(m)
    assert ml["A_deep"] == pytest.approx(0.375, abs=1e-12)
    assert abs(h5.fit_statsmodels(m)["A_deep"] - 0.375) < 1e-6


# --- D. bootstrap --------------------------------------------------------------------------------

def test_the_bootstrap_is_deterministic_under_its_seed(tmp_path):
    fx = H5Fixture(tmp_path)
    fx.block6()
    a, b = fx.compute(boot=h5.N_BOOT), fx.compute(boot=h5.N_BOOT)
    assert a["ours"]["bootstrap"] == b["ours"]["bootstrap"]
    assert a["bootstrap_seed"] == SEED + 40 == a["ours"]["bootstrap"]["rng_seed"]
    assert a["status"] == h5.FINAL
    per = h5.game_arrays([x for r in runs_of(SIX) for x in h5.level_rows(r)], list(SIX))
    one = h5.bootstrap(per, list(SIX), SEED + 40, 100, ("firth", "ml_limit"), "firth")
    two = h5.bootstrap(per, list(SIX), SEED + 41, 100, ("firth", "ml_limit"), "firth")
    assert one["primary"]["contrast"]["interval"] != two["primary"]["contrast"]["interval"]


def test_the_primary_and_its_error_sensitivity_use_the_same_draws(tmp_path, monkeypatch):
    calls = []
    real = h5.bootstrap

    def spy(per, games, seed, boot, *a, **k):
        calls.append((list(games), seed, boot))
        return real(per, games, seed, boot, *a, **k)

    monkeypatch.setattr(h5, "bootstrap", spy)
    r = h5.full_reading(spec_of(SIX), SEED, 30, "firth", [], sensitivity=True,
                        common_support=False)
    assert len(calls) == 2 and calls[0] == calls[1]
    # no run of SIX ended by an error, so the sensitivity reading is the primary's
    assert r["sensitivity_error_endings"]["dropped_rows"] == []
    assert r["sensitivity_error_endings"]["bootstrap"] == r["bootstrap"]


def test_duplicated_games_are_separate_clusters():
    rows = [x for r in runs_of(SIX) for x in h5.level_rows(r)]
    games = list(SIX)
    per = h5.game_arrays(rows, games)
    labels = h5.cluster_labels(games, (0, 0, 1))
    assert labels == ["G1#0", "G1#1", "G2#2"] and len(set(labels)) == 3
    m = h5.resample_rows(per, games, (0, 0, 1))
    assert m.clusters == ("G1#0", "G1#1", "G2#2")
    by_hand = [(f"G1#{j}", c, y) for j in (0, 1) for c, y in zip(*per["G1"], strict=True)]
    by_hand += [("G2#2", c, y) for c, y in zip(*per["G2"], strict=True)]
    twice = h5.model_rows(*zip(*by_hand, strict=True))
    got, want = h5.fit_ml_limit(m), h5.fit_ml_limit(twice)
    merged = [(label.split("#")[0], c, y) for label, c, y in by_hand]
    same = h5.fit_ml_limit(h5.model_rows(*zip(*merged, strict=True)))
    for q in ("A_early", "A_deep"):
        assert got[q] == pytest.approx(want[q], abs=1e-12)
        assert got[q] == pytest.approx(same[q], abs=1e-8)


def test_undefined_resamples_are_left_out_and_counted():
    """Only G1's Standard run reached a deep level: every resample without G1 has no
    Standard-deep row."""
    design = {"G1": (4, 5), "G2": (1, 4), "G3": (2, 5), "G4": (0, 3)}
    rows = [x for r in runs_of(design) for x in h5.level_rows(r)]
    games = list(design)
    boot, seed = 150, SEED + 40
    bs = h5.bootstrap(h5.game_arrays(rows, games), games, seed, boot, ("firth", "ml_limit"),
                      "firth")
    idx = np.random.default_rng(seed).integers(0, 4, size=(boot, 4))
    without = int(sum(0 not in row for row in idx))
    assert 0 < without < boot
    for name in ("firth", "ml_limit"):
        reasons = bs["estimators"][name]["A_deep"]["undefined_reasons"]
        assert reasons.get("Standard reached no deep level") == without
    c = bs["primary"]["contrast"]
    assert c["n_defined"] + c["n_undefined"] == boot


def test_four_games_give_35_distinct_resamples():
    games = ["FT09", "SB26", "R11L", "CD82"]
    design = dict(zip(games, [(1, 4), (3, 5), (4, 3), (2, 6)], strict=True))
    rows = [x for r in runs_of(design) for x in h5.level_rows(r)]
    bs = h5.bootstrap(h5.game_arrays(rows, games), games, SEED + 40, 500, ("firth",), "firth")
    assert bs["distinct_possible"] == 35 == math.comb(7, 4)
    assert bs["distinct_drawn"] <= 35


def _raw_by_hand(design: dict, draw) -> float | None:
    """(r_Ad − r_Sd) − (r_Ae − r_Se) over the drawn games' rows (with repeats), from
    `independent_rows`."""
    rows = independent_rows(design)
    names = list(design)
    k, n = Counter(), Counter()
    for i in draw:
        for g, adapter, deep, cleared in rows:
            if g == names[int(i)]:
                k[(deep, adapter)] += cleared
                n[(deep, adapter)] += 1
    if any(n[c] == 0 for c in ((0, 0), (0, 1), (1, 0), (1, 1))):
        return None
    r = {c: k[c] / n[c] for c in n}
    return (r[(1, 1)] - r[(1, 0)]) - (r[(0, 1)] - r[(0, 0)])


def test_the_fraction_of_resamples_with_c_at_most_0_and_the_90_percent_intervals():
    """Each resample recomputed here in drawn (unsorted) order; the intervals are the 5% and
    95% quantiles of the defined values (written as numbers, not read from the module)."""
    games = list(SIX)
    per = h5.game_arrays([x for r in runs_of(SIX) for x in h5.level_rows(r)], games)
    boot, seed = 60, SEED + 40
    bs = h5.bootstrap(per, games, seed, boot, ("firth",), "firth")
    idx = np.random.default_rng(seed).integers(0, len(games), size=(boot, len(games)))
    fits = [h5.fit_firth(h5.resample_rows(per, games, row)) for row in idx]
    cs = [f["contrast"] for f in fits if f["contrast"] is not None]
    ads = [f["A_deep"] for f in fits if f["A_deep"] is not None]
    assert bs["primary"]["fraction_contrast_le_0"] == pytest.approx(
        np.mean([c <= 1e-9 for c in cs]), abs=1e-12)
    assert bs["primary"]["contrast"]["n_defined"] == len(cs)
    assert bs["level"] == 0.90 and bs["quantiles"] == [0.05, 0.95]
    for got in (bs["primary"]["contrast"]["interval"],
                bs["estimators"]["firth"]["contrast"]["interval"]):
        assert got == pytest.approx(list(np.quantile(cs, (0.05, 0.95))), abs=1e-12)
    assert bs["estimators"]["firth"]["A_deep"]["interval"] == pytest.approx(
        list(np.quantile(ads, (0.05, 0.95))), abs=1e-12)
    raw = [_raw_by_hand(SIX, row) for row in idx]
    ok = [x for x in raw if x is not None]
    assert bs["raw_contrast"]["n_defined"] == len(ok)
    assert bs["raw_contrast"]["interval"] == pytest.approx(
        list(np.quantile(ok, (0.05, 0.95))), abs=1e-12)


def test_the_rules_interval_and_its_firth_fallbacks_by_reason():
    """Under `ml_limit_or_firth` each resample's C is the ML limit's where defined, else
    Firth's; recomputed here in drawn order, with the fallbacks counted by reason."""
    games = list(AMB)
    per = h5.game_arrays([x for r in runs_of(AMB) for x in h5.level_rows(r)], games)
    boot, seed = 60, SEED + 40
    bs = h5.bootstrap(per, games, seed, boot, ("firth", "ml_limit"), "ml_limit_or_firth")
    idx = np.random.default_rng(seed).integers(0, len(games), size=(boot, len(games)))
    cs, reasons = [], Counter()
    for row in idx:
        m = h5.resample_rows(per, games, row)
        ml = h5.fit_ml_limit(m)
        if ml["contrast"] is not None or not ml["estimable"]:
            c = ml["contrast"]
        else:
            c = h5.fit_firth(m)["contrast"]
            reasons[ml["why_undefined"]["contrast"]] += 1
        if c is not None:
            cs.append(c)
    p = bs["primary"]
    assert p["rule"] == "ml_limit_or_firth" and p["contrast"]["n_defined"] == len(cs)
    assert p["contrast"]["interval"] == pytest.approx(list(np.quantile(cs, (0.05, 0.95))),
                                                      abs=1e-12)
    assert p["n_firth_fallback"] == sum(reasons.values()) > 0
    assert p["firth_fallback_reasons"] == dict(reasons) == {
        "not identified in the ML limit": p["n_firth_fallback"]}
    assert h5.bootstrap(per, games, seed, 5, ("firth",), "firth")["primary"][
        "firth_fallback_reasons"] is None


def test_a_failed_ml_fit_falls_back_to_firth_and_is_named(monkeypatch):
    """A failed ML-limit fit is counted as such, not as "not identified"."""
    monkeypatch.setattr(h5, "lcm_fit", lambda *a, **k: None)
    r = h5.full_reading(spec_of(SIX), SEED, 12, "ml_limit_or_firth", [], sensitivity=False,
                        common_support=False)
    assert r["primary"]["source"] == "firth"
    assert r["primary"]["fallback_reason"] == "LCM fit did not converge"
    p = r["bootstrap"]["primary"]
    assert p["firth_fallback_reasons"] == {"LCM fit did not converge": p["n_firth_fallback"]}
    assert 0 < p["n_firth_fallback"] <= r["bootstrap"]["resamples"]
    text = "\n".join(h5.reading_lines(r))
    assert "- Firth decides this reading: C is undefined in the ML limit (LCM fit did not " \
           "converge)." in text
    assert (f"used Firth because C was undefined in the ML limit (LCM fit did not converge: "
            f"{p['n_firth_fallback']:,}).") in text


def test_raw_rates_and_the_raw_contrast_on_six_by_hand():
    """SIX by hand: Standard early 9/11, level 3 3/4, deep 3/6; Adapter early 10/11, level 3
    4/5, deep 6/9; the raw contrast (6/9 − 3/6) − (10/11 − 9/11) = 5/66."""
    rows = [x for r in runs_of(SIX) for x in h5.level_rows(r)]
    raw = h5.raw_rates(rows)
    want = {"early": {"standard": (11, 9), "provider_adapter": (11, 10)},
            "level_3": {"standard": (4, 3), "provider_adapter": (5, 4)},
            "deep": {"standard": (6, 3), "provider_adapter": (9, 6)}}
    for band, by in want.items():
        for h, (reached, cleared) in by.items():
            c = raw["bands"][band][h]
            assert (c["reached"], c["cleared"]) == (reached, cleared)
            assert c["rate"] == pytest.approx(cleared / reached, abs=1e-15)
    assert raw["contrast"] == pytest.approx(5 / 66, abs=1e-12)
    assert raw["contrast_why_undefined"] is None
    c, why = h5._raw_contrast_arrays(model_of(SIX))
    assert c == pytest.approx(5 / 66, abs=1e-12) and why is None
    assert _raw_by_hand(SIX, range(len(SIX))) == pytest.approx(5 / 66, abs=1e-12)
    rows = [x for r in runs_of(STRUCTURAL) for x in h5.level_rows(r)]
    assert (h5.raw_rates(rows)["contrast"], h5.raw_rates(rows)["contrast_why_undefined"]) == (
        None, "Standard reached no deep level")
    assert h5._raw_contrast_arrays(model_of(STRUCTURAL)) == (
        None, "Standard reached no deep level")


def test_another_number_of_resamples_is_provisional(tmp_path):
    fx = H5Fixture(tmp_path)
    fx.block6()
    h = fx.compute(boot=300)
    assert h["status"] == h5.PROVISIONAL
    assert h["provisional_reasons"] == ["--boot 300, not 10,000: not the registered analysis"]
    assert fx.compute(boot=h5.N_BOOT)["status"] == h5.FINAL


# --- E. our counted runs -------------------------------------------------------------------------

EXPECTED_ORDER = [(g, c) for g in GAMES for c in ("S0", "S4")]


def test_the_eight_counted_runs_are_read_and_s1_s2_are_listed(tmp_path):
    fx = H5Fixture(tmp_path)
    ids = fx.block6()
    s2 = fx.run6("FT09", "S2", 3)
    s1 = fx.run6("SB26", "S1", 2)
    h = fx.compute()
    o = h["ours"]
    assert o["games"] == GAMES and o["n_runs"] == 8
    assert sorted(h5.counted_runs(h)) == sorted(ids[k] for k in EXPECTED_ORDER)
    assert [r["run_id"] for r in h["ours_runs"]] == sorted(ids.values())
    assert s1 not in {r["run_id"] for r in h["ours_runs"]}
    warn = [w for w in h["warnings"] if "not in H5 (R6 change 4)" in w]
    assert len(warn) == 1 and s2 in warn[0] and s1 in warn[0]
    assert {g["game"]: (g["standard"]["levels_completed"],
                        g["provider_adapter"]["levels_completed"]) for g in o["per_game"]} == {
        "FT09": (1, 4), "SB26": (3, 5), "R11L": (4, 3), "CD82": (2, 6)}


def test_ft09_s0s_re_run_is_counted_and_its_original_is_listed_as_replaced(tmp_path):
    fx = H5Fixture(tmp_path)
    orig = fx.run6("FT09", "S0", 0, "TIME_BUDGET", median=500.0)     # a D20 incident
    rerun = fx.run6("FT09", "S0", 2, seed=101, rerun_of=orig)
    for g, (s0, s4) in {"SB26": (3, 5), "R11L": (4, 3), "CD82": (2, 6)}.items():
        fx.run6(g, "S0", s0)
        fx.run6(g, "S4", s4)
    fx.run6("FT09", "S4", 4)
    h = fx.compute()
    assert h["status"] == h5.PROVISIONAL and h["provisional_reasons"] == [
        "--boot 200, not 10,000: not the registered analysis"]
    rows = {r["run_id"]: r for r in h["ours_runs"]}
    assert rows[rerun]["in_reading"] and rows[rerun]["counted"]
    assert not rows[orig]["in_reading"] and not rows[orig]["counted"]
    assert rows[orig]["replaced_by"] == [rerun]
    assert any(f.startswith(f"replaced by {rerun}") for f in rows[orig]["flags"])
    ft09 = next(g for g in h["ours"]["per_game"] if g["game"] == "FT09")
    assert ft09["standard"]["run_id"] == rerun and ft09["standard"]["levels_completed"] == 2
    assert rerun in h5.counted_runs(h) and orig not in h5.counted_runs(h)


def test_a_missing_or_pending_unit_refuses_and_allow_incomplete_gives_raw_tables(tmp_path):
    fx = H5Fixture(tmp_path)
    fx.block6(endings={("CD82", "S0"): "API_ERROR"})             # its re-run has not landed
    with pytest.raises(h5.Refusal, match="CD82 S0: .* its one re-run has not landed"):
        fx.compute()
    assert fx.main("--data", "ours", "--no-write") == 2
    h = fx.compute(allow_incomplete=True)
    assert h["status"] == h5.PROVISIONAL
    assert any("re-run has not landed" in x for x in h["provisional_reasons"])
    o = h["ours"]
    assert o["estimates"] is None and o["bootstrap"] is None
    assert o["primary"]["verdict"].startswith("not computed")
    assert o["raw"]["bands"]["early"]["standard"]["reached"] > 0
    cd82 = next(r for r in h["ours_runs"] if r["game"] == "CD82" and r["config"] == "S0")
    assert any(f.startswith("stand-in") for f in cd82["flags"])
    assert cd82["run_id"] not in h5.counted_runs(h)
    text = "\n".join(h5.summary_lines(h))
    assert "**PROVISIONAL:** a unit lacks a counted run" in text


def test_a_missing_unit_refuses(tmp_path):
    fx = H5Fixture(tmp_path)
    ids = fx.block6()
    import shutil
    shutil.rmtree(fx.root / "arc_path" / ids[("SB26", "S4")])
    with pytest.raises(h5.Refusal, match="SB26 S4: no seed-1 run yet"):
        fx.compute()


def test_a_pilot_folder_is_refused(tmp_path):
    fx = H5Fixture(tmp_path)
    fx.block6()
    fx.run6("FT09", "S0", 1, experiment="arc_pilot", row=False)
    with pytest.raises(h5.am.Refused, match="experiment 'arc_pilot'"):
        fx.compute()
    assert fx.main("--data", "ours", "--no-write") == 2


def test_a_re_run_that_also_errs_is_counted_as_is_and_flagged(tmp_path):
    fx = H5Fixture(tmp_path)
    ids = fx.block6(endings={("R11L", "S4"): "AGENT_ERROR"})
    rerun = fx.run6("R11L", "S4", 2, "API_ERROR", seed=101, rerun_of=ids[("R11L", "S4")])
    h = fx.compute()
    assert rerun in h5.counted_runs(h)
    assert any(f"re-run {rerun} also ended API_ERROR" in w for w in h["warnings"])
    row = next(r for r in h["ours_runs"] if r["run_id"] == rerun)
    assert "re-run also ended re-run-eligible: counted as is (D19)" in row["flags"]
    assert row["dropped_in_sensitivity"] == 3


# --- F. the error-ending sensitivity -------------------------------------------------------------

def test_published_error_endings_drop_only_their_ended_level(tmp_path, pinned):
    fx = H5Fixture(tmp_path)
    rows = pub_rows(efforts=("high",))
    pinned(write_slice(fx.root, rows))
    h = fx.compute(data="published", boot=10, exploratory=False)
    dropped = h["published"]["sensitivity_error_endings"]["dropped_rows"]
    want = []
    for r in rows:
        lc, n = int(r["levels_completed"]), int(r["level_count"])
        if r["inferred_ending"] == "ERROR_OR_CLOSED" and lc < n:
            want.append((r["game"], r["harness"], lc + 1))
    assert sorted((x["game"], x["harness"], x["level"]) for x in dropped) == sorted(want)
    assert want and all(x["ending"] == "ERROR_OR_CLOSED" for x in dropped)
    kept = h["published"]["sensitivity_error_endings"]["n_rows"]["in_model"]
    lost = sum(1 for x in dropped if x["level"] != 3)
    assert kept == h["published"]["n_rows"]["in_model"] - lost


@pytest.mark.parametrize("ending", ["API_ERROR", "AGENT_ERROR", "SCORECARD_CLOSED", None])
def test_our_error_endings_drop_only_their_ended_level(tmp_path, ending):
    """An error ending is re-run-eligible, so the counted run is a re-run that also erred."""
    fx = H5Fixture(tmp_path)
    ids = fx.block6()
    rerun = fx.run6("SB26", "S4", 4, ending, seed=101, rerun_of=ids[("SB26", "S4")])
    # block6's SB26 S4 ended ACTION_BUDGET (final): the re-run still replaces it (§7.5)
    h = fx.compute()
    s = h["ours"]["sensitivity_error_endings"]
    assert [(x["game"], x["harness"], x["level"], x["ending"]) for x in s["dropped_rows"]] == [
        ("SB26", "provider_adapter", 5, ending or "UNKNOWN")]
    row = next(r for r in h["ours_runs"] if r["run_id"] == rerun)
    assert row["dropped_in_sensitivity"] == 5 and row["ending_kind"] == "error"


@pytest.mark.parametrize("ending", ["ACTION_BUDGET", "TIME_BUDGET", "COST_CAP", "GAME_WIN"])
def test_budget_endings_and_wins_drop_nothing(tmp_path, ending):
    fx = H5Fixture(tmp_path)
    lc = N if ending == "GAME_WIN" else 2
    fx.block6(design={"FT09": (lc, 4), "SB26": (3, 5), "R11L": (4, 3), "CD82": (2, 6)},
              endings={("FT09", "S0"): ending})
    h = fx.compute()
    assert h["ours"]["sensitivity_error_endings"]["dropped_rows"] == []
    row = next(r for r in h["ours_runs"] if r["game"] == "FT09" and r["config"] == "S0")
    assert row["dropped_in_sensitivity"] is None and row["in_reading"]
    if ending == "COST_CAP":
        assert "COST_CAP: kept as a budget ending (the $120 guard)" in row["flags"]


def test_an_error_run_with_no_action_on_its_level_in_play_drops_nothing():
    runs = runs_of(SIX)
    runs[0] = run_levels("G1", "standard", 1, next_reached=False, ending="ERROR_OR_CLOSED")
    spec = h5.Spec("s", "published", True, "high", {"standard": "S", "provider_adapter": "A"},
                   list(SIX), runs)
    r = h5.full_reading(spec, SEED, 10, "firth", [], sensitivity=True, common_support=False)
    assert r["sensitivity_error_endings"]["dropped_rows"] == []


# --- G. wording ----------------------------------------------------------------------------------

def test_the_verdict_thresholds():
    assert h5.verdict(0.0, None, True) == h5.VERDICT_NOT_POSITIVE
    assert h5.verdict(1e-9, None, True) == h5.VERDICT_NOT_POSITIVE
    assert h5.verdict(1e-6, None, True) == h5.VERDICT_POSITIVE
    assert h5.verdict(-0.2, None, True) == h5.VERDICT_NOT_POSITIVE
    assert h5.verdict(None, "Standard reached no deep level", True) == \
        "cannot be computed: Standard reached no deep level"
    assert h5.verdict(0.3, None, False) == "positive"
    assert h5.verdict(None, "x", False) == "cannot be computed"
    assert "as H5 predicts" in h5.VERDICT_POSITIVE
    assert "against H5's prediction" in h5.VERDICT_NOT_POSITIVE


@pytest.fixture(scope="module")
def full_run(tmp_path_factory):
    """One full run of the script on synthetic data: both data sets, exploratory readings,
    written to an output folder (the slow part of these tests, done once)."""
    tmp = tmp_path_factory.mktemp("full")
    fx = H5Fixture(tmp)
    fx.block6(endings={("CD82", "S4"): "GAME_WIN"})
    d = write_slice(fx.root, pub_rows())
    mp = pytest.MonkeyPatch()
    mp.setattr(h5, "PUBLISHED_SHA256", sha(d))
    out = tmp / "out"
    try:
        code = fx.main("--boot", "40", "--out-dir", str(out))
    finally:
        mp.undo()
    h = json.loads((out / "h5.json").read_text(encoding="utf-8"))
    return {"code": code, "out": out, "h": h, "fx": fx,
            "text": (out / "summary.md").read_text(encoding="utf-8"),
            "meta": json.loads((out / "meta.json").read_text(encoding="utf-8"))}


def test_the_summary_never_claims_support_significance_or_confirmation(full_run):
    text = full_run["text"].lower()
    for word in ("supported", "significant", "confirmed"):
        assert word not in text
    assert full_run["code"] == 0


def test_exploratory_readings_are_labelled_and_carry_no_verdict_sentence(full_run):
    h, text = full_run["h"], full_run["text"]
    x = h["published_exploratory"]
    for effort in ("medium", "low"):
        r = x["efforts"][effort]
        assert r["registered"] is False and "exploratory" in r["label"]
        assert r["primary"]["verdict"] in ("positive", "not positive", "cannot be computed")
        assert r["sensitivity_error_endings"] is None
    part = text.split("## Exploratory (§9.10)")[1].split("## Checks")[0]
    assert "as H5 predicts" not in part and "against H5's prediction" not in part
    assert "### Published runs, effort medium (exploratory)" in part
    assert "Other models: not computed" in part
    assert h["published"]["common_support"] is not None


# --- H. outputs ----------------------------------------------------------------------------------

def test_the_output_follows_its_allowlists(full_run):
    h = full_run["h"]
    assert tuple(h) == h5.TOP_FIELDS
    for r in (h["published"], h["ours"], *h["published_exploratory"]["efforts"].values()):
        assert tuple(r) == h5.READING_FIELDS
    assert tuple(h["published"]["sensitivity_error_endings"]) == h5.SENSITIVITY_FIELDS
    assert all(tuple(r) == h5.OURS_RUN_FIELDS for r in h["ours_runs"])
    assert h["primary_estimator"] == h5.PRIMARY_ESTIMATOR == "ml_limit_or_firth"
    assert h["settings"]["alternative_rule"] == "firth"
    assert h["seed"] == SEED and h["bootstrap_seed"] == SEED + 40
    assert h["inputs"]["published_sha256_matches_pinned"] is True


def test_meta_json(full_run):
    meta = full_run["meta"]
    assert meta["experiment"] == "arc_h5" and meta["cell_or_config"] == "h5"
    assert meta["seeds"] == {"bootstrap": SEED + 40}
    assert meta["paid_calls"] == 0 and meta["cost_usd"] == 0.0
    assert meta["outputs"] == ["h5.json", "summary.md"]
    assert meta["exit_reason"] == "completed_provisional"            # --boot 40
    assert meta["config"]["primary_estimator"] == "ml_limit_or_firth"
    assert meta["config"]["n_boot"] == 40 and len(meta["runs"]) == 8
    assert meta["raw_transcript_path"] is None and meta["tokens"] is None


def test_the_summary_sections(full_run):
    text = full_run["text"]
    order = ["# H5 on ARC: the Adapter advantage by level depth",
             "Descriptive only; H5 is outside the Holm family (§9.4).", "**Status: PROVISIONAL.**",
             "> **Definitions.**", "## Published runs, high effort (registered; not blind)",
             "## Our runs, S0 vs S4 on the 4 path games", "## Exploratory (§9.10)",
             "## Checks", "## What it does not show",
             "written and tested on synthetic data only before its first real run"]
    at = [text.index(s) for s in order]
    assert at == sorted(at)
    assert "RNG SEED + 40 = " in text and "4 games give only 35 distinct resamples" in text
    assert "**Verdict** (rule in force `ml_limit_or_firth`" in text
    assert ("> Estimator in force: `ml_limit_or_firth` (the maximum-likelihood limit where C is "
            "identified, else Firth's penalized logit for that reading or resample; the ruling: "
            "`results/decisions.md`, 2026-10-10, \"H5 analysis: two rulings proposed before any "
            "H5 quantity is computed\"); the other rule is `firth`.") in text
    assert ("counts as reached and not cleared if the run took at least one action on it "
            "(D35; R5)") in text
    for point in ("**Not blind.**", "**Observational, one run per game and harness.**",
                  "**Conditioning on reached is selection by the harness.**",
                  "**Extrapolation.**", "**The estimator matters at this size.**",
                  "**Endings.**", "**Our 4 games are selected, so our reading is conditional.**",
                  "**The data sets overlap.**", "**Descriptive only.**", "**Narrow.**"):
        assert point in text
    shown = text.split("## What it does not show")[1]
    assert "published high-effort gap ≥ 20, both published runs ≤ $60, and a normal " \
           "Standard-high ending" in shown
    assert "conditional on \"games where the Adapter helps\"" in shown
    assert "Our S0 and S4 runs were seen before R6" in shown and "35 distinct resamples" in shown


def test_unregistered_quantities_are_labelled_exploratory(full_run):
    """The raw pooled contrast and the fraction of resamples with C ≤ 0 are not registered for
    H5 (§9.10): both carry an exploratory label wherever they are printed."""
    text = full_run["text"]
    raw = [x for x in text.splitlines() if x.startswith("Raw contrast (r_Ad − r_Sd)")]
    assert raw and all("(exploratory: no game adjustment, not the registered model" in x
                       for x in raw)
    heads = [x for x in text.splitlines() if x.startswith("| Estimator | A_early")]
    assert heads and all("| Fraction C ≤ 0 (descriptive, not a test) |" in x for x in heads)
    assert "(exploratory; H5 registers no such fraction)" in text
    assert full_run["h"]["published"]["raw"]["contrast_label"] == h5.RAW_LABEL
    assert h5.RAW_LABEL.startswith("exploratory")


def test_exploratory_efforts_print_their_per_level_tables(full_run):
    text = full_run["text"]
    part = text.split("## Exploratory (§9.10)")[1].split("## Checks")[0]
    for effort in ("medium", "low"):
        sec = part.split(f"### Published runs, effort {effort} (exploratory)")[1].split("###")[0]
        assert "Per level (exploratory):" in sec
        levels = [x["level"] for x in full_run["h"]["published_exploratory"]["efforts"][effort][
            "per_level"]]
        for lv in levels:
            assert f"\n| {lv} | {h5.band_of(lv)} | " in sec


def test_the_run_table_gives_both_exit_reasons(tmp_path):
    """§9.9: `agent_exit_reason` and `exit_reason` per run, next to the D19 ending (which reads
    `agent_exit_reason` only)."""
    fx = H5Fixture(tmp_path)
    ids = fx.block6({"FT09": (1, 4), "SB26": (3, 5), "R11L": (4, 3)})
    odd = fx.run6("CD82", "S0", 2, meta_extra={"exit_reason": "launcher_stopped"})
    fx.run6("CD82", "S4", 6, "GAME_WIN")
    h = fx.compute(boot=20)
    text = "\n".join(h5.summary_lines(h))
    assert ("| Run | Game | Config | Counted | In reading | Exit reasons (agent; launcher) | "
            "Ending (D19) | Kind |") in text
    line = next(x for x in text.splitlines() if x.startswith(f"| `{odd}` |"))
    assert "| ACTION_BUDGET; launcher_stopped | ACTION_BUDGET | budget |" in line
    for run_id in ids.values():
        line = next(x for x in text.splitlines() if x.startswith(f"| `{run_id}` |"))
        assert "| ACTION_BUDGET; ACTION_BUDGET | ACTION_BUDGET |" in line


def test_published_only_output_omits_the_caveats_about_our_runs(tmp_path, pinned):
    fx = H5Fixture(tmp_path)
    pinned(write_slice(fx.root, pub_rows(efforts=("high",))))
    h = fx.compute(data="published", boot=10, exploratory=False)
    shown = "\n".join(h5.not_shown_lines(h))
    assert "**Not blind.** On the published data" in shown
    for ours_only in ("Our S0 and S4 runs were seen", "35 distinct resamples",
                      "**Our 4 games are selected", "**The data sets overlap.**"):
        assert ours_only not in shown
    h_ours = H5Fixture(tmp_path / "ours")
    h_ours.block6()
    shown = "\n".join(h5.not_shown_lines(h_ours.compute(boot=10, exploratory=False)))
    assert "On the published data" not in shown and "**The data sets overlap.**" not in shown
    assert "**Our 4 games are selected" in shown and "35 distinct resamples" in shown


def test_the_default_output_folder_and_no_write(tmp_path):
    fx = H5Fixture(tmp_path)
    fx.block6()
    assert fx.main("--data", "ours", "--boot", "20", "--no-write") == 0
    assert not (fx.root / "arc_h5").exists()
    assert fx.main("--data", "ours", "--boot", "20") == 0
    out = list((fx.root / "arc_h5").iterdir())
    assert len(out) == 1 and {p.name for p in out[0].iterdir()} == {"h5.json", "summary.md",
                                                                    "meta.json"}


# --- I. this checkout's files: counts and run IDs only (the blind rule) --------------------------

REAL_SLICE = h5.RESULTS / h5.PUBLISHED_SLICE


def test_the_rulings_entry_the_module_cites_exists():
    """The summary and the docstring name the decisions.md entry that states the two rulings
    (the estimator rule and the seed)."""
    text = (h5.RESULTS / "decisions.md").read_text(encoding="utf-8")
    head = f"## 2026-10-10: {h5.RULING_ENTRY}\n"
    assert text.count(head) == 1
    entry = text.split(head)[1].split("\n## ")[0]
    assert f'`PRIMARY_ESTIMATOR = "{h5.PRIMARY_ESTIMATOR}"`' in entry
    assert f"SEED + {h5.BOOT_SEED_OFFSET}" in entry
    assert h5.RULING_ENTRY in h5.__doc__.replace("\n", " ")


@pytest.mark.skipif(not (REAL_SLICE / "per_run.csv").is_file(), reason="no committed slice")
def test_the_committed_slice_is_the_pinned_file_with_25_games_x_2_harnesses_per_effort():
    data = (REAL_SLICE / "per_run.csv").read_bytes()
    assert hashlib.sha256(data).hexdigest() == h5.PUBLISHED_SHA256
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
    assert set(h5.PUBLISHED_FIELDS) <= set(reader.fieldnames)
    keys = Counter((r["effort"], r["game"], r["harness"]) for r in reader)   # no level read
    for effort in ("high", "medium", "low"):
        mine = {k: v for k, v in keys.items() if k[0] == effort}
        assert len({k[1] for k in mine}) == 25 and len(mine) == 50
        assert set(mine.values()) == {1}


COUNTED = {("FT09", "S0"): "20261009T030646Z-S0-ft09-s101",
           ("FT09", "S4"): "20261009T020602Z-S4-ft09-s1",
           ("SB26", "S0"): "20261007T143700Z-S0-sb26-s1",
           ("SB26", "S4"): "20261007T133444Z-S4-sb26-s1",
           ("R11L", "S0"): "20261008T134155Z-S0-r11l-s1",
           ("R11L", "S4"): "20261008T212807Z-S4-r11l-s1",
           ("CD82", "S0"): "20261008T013832Z-S0-cd82-s1",
           ("CD82", "S4"): "20261006T144656Z-S4-cd82-s1"}


@pytest.mark.skipif(not (h5.RESULTS / "arc_path").is_dir(), reason="no committed arc_path")
def test_this_checkouts_arc_path_resolves_the_8_counted_run_ids():
    """checkpoint_c's resolution, as load_ours uses it, on this checkout's folders: the run IDs
    only (no H5 code that reads levels is run on real data)."""
    root = h5.RESULTS
    draw = json.loads(cc.the_draw(root).read_text(encoding="utf-8"))
    games = [g.upper() for g in draw["games"]]
    pilots = cc.pilot_latency(costs.read_rows(root / "costs.csv"))
    entries, _ = cc.discover(root / cc.EXPERIMENT)
    cc.check_links(entries)
    d20 = {e.run_id: cc.d20_check(e, entries, pilots) for e in entries if not e.truncated}
    eligible = {e.run_id: cc.rerun_eligible(e, d20[e.run_id]) for e in entries
                if not e.truncated}
    got = {(g, c): cc.resolve_unit(entries, g, c, eligible, h5.REPLICATE).counted.run_id
           for g in games for c in h5.CONFIGS}
    assert got == COUNTED
