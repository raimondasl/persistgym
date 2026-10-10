"""H1 and H3 on luna's sweep (analysis/persistgym_h1h3.py; PREREG §3 H1, §3 H3, §2.8, §9.1-§9.5,
§13): every estimand on hand-computed toy data, the bootstrap (its seed, determinism, and its
agreement with power_sim's per-template contrasts), Holm and "supported", the kill and
prediction readings at their boundaries, DESIGN §7.8's dedup rule, §13's exclusions, the refusal
of an incomplete sweep, and §2.8's bug stop, the last both on synthetic transcripts and on real
episodes played by the harness with the fake model.

Every run here is synthetic, in a results root under tmp_path: no test reads luna's real sweep.
"""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from functools import cache

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm
import statsmodels.formula.api as smf

from analysis import persistgym_h1h3 as hh
from analysis import power_sim as ps
from harnesses import registered
from harnesses.cells import CELLS, NOTES_INSTRUCTION
from harnesses.fake import padded_text
from persistgym.survival import window_keep_start

SEED = 4086943125952605534
GIT = {"git_commit": "0" * 40, "git_dirty": False}
HASH = registered.LUNA_GENERATOR_HASH
T = 10
BASE, RESTATED, ST = hh.BASE, hh.RESTATED, hh.SINGLE_TURN
ONR, OR, DNR = "observed-nonrec-far", "observed-rec-far", "derived-nonrec-far"

# The synthetic window: W = 60 project tokens, a 5-token system prompt, 10-token observations
# and 2-token replies, need step 10. At the need step the window keeps turns 7-10, so near
# evidence (steps 7-8) survives and far evidence (steps 1-2) does not. With 20-token replies
# it keeps turns 9-10 only, and near evidence is lost (an expected near loss, §2.8).
W_SMALL, SYS_TOKENS, OBS_TOKENS, NEED = 60, 5, 10, 10
EVIDENCE = {("observed", "near"): [8], ("observed", "far"): [2],
            ("derived", "near"): [7, 8], ("derived", "far"): [1, 2]}


@cache
def _text(prefix: str, n: int) -> str:
    return padded_text(prefix, n)


def _keep(reply_tokens: int, turn: int) -> int:
    obs, rep = [OBS_TOKENS] * (turn + 1), [reply_tokens] * turn
    return max(window_keep_start(obs[: j + 1], rep[:j], W_SMALL, SYS_TOKENS)
               for j in range(turn + 1))


def _user(text):
    return {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}


def _reply(text):
    return {"type": "message", "role": "assistant",
            "content": [{"type": "output_text", "text": text}]}


def transcript_lines(eid: str, cell: str, reply_tokens: int = 2, turns: int = NEED + 2):
    """The step requests of one window-cell episode, turns 0 to NEED + 1, as the runner's
    recorder writes them (no lookups)."""
    instr = _text("System prompt.", SYS_TOKENS)
    if CELLS[cell].notes:
        instr += "\n" + NOTES_INSTRUCTION
    reply = _text("ok", reply_tokens)
    for i in range(turns):
        keep = _keep(reply_tokens, i)
        items = []
        for t in range(keep, i):
            items += [_user(_text(f"Observation {t}.", OBS_TOKENS)), _reply(reply)]
        items.append(_user(_text(f"Observation {i}.", OBS_TOKENS)))
        yield {"episode_id": eid, "harness_cell": cell, "request_index": i, "kind": "step",
               "turn": i, "pending_step": i, "is_lookup_result": False,
               "info": {"keep_start": keep},
               "payload": {"instructions": instr, "input": items},
               "response": {"output": [_reply(reply)]}}


def record(cell, variant, tc, t, success, repeat=0, **over) -> dict:
    """One synthetic record, shaped as the runner (or the single-turn control) writes it."""
    fact, _, dist = tc.split("-")
    ev = EVIDENCE[(fact, dist)]
    eid = hh.episode_id_of(cell, variant, t, tc)
    echo = {"context_requested": "current_turn", "context_echoed": {"current_turn": 12},
            "effort_requested": "medium", "effort_echoed": {"medium": 12},
            "models_returned": {"gpt-6-luna": 12}, "service_tiers_returned": {"flex": 12}}
    r = {"episode_id": eid, "template_id": f"main-{t:06d}", "task_cell": tc,
         "variant": variant, "harness_cell": cell, "model": "gpt-6-luna",
         "exit_reason": "DONE", "error": None, "excluded": False, "exclusion_reason": None,
         "echo_mismatches": [], "need_correct": bool(success),
         "need_outcome": "correct" if success else "wrong", "echo": echo,
         "usage": {"input_tokens": 10_000, "output_tokens": 300, "reasoning_tokens": 100,
                   "cached_input_tokens": 0, "cache_write_tokens": 0},
         "cost_usd_list": 0.01, "cost_usd_billed_est": 0.005,
         "generator_config_hash": HASH}
    if cell == ST:
        r.update({"base_episode_id": hh.episode_id_of("F-0", BASE, t, tc), "template_seed": t,
                  "repeat_index": repeat, "control": "single_turn", "settings_cell": "F-0",
                  "need_step": NEED})
    else:
        window = CELLS[cell].history == "window"
        r.update({"n_lookups": 0, "n_lookups_unavailable": 0,
                  "need_payload": {"S": cell == "F-0" or dist == "near",
                                   "assistant_carried": {"carried": False}},
                  "need_bridge_carried": ({"carried": False}
                                          if CELLS[cell].history == "summary" else None),
                  "need_info": {"keep_start": _keep(2, NEED) if window else 0},
                  "designed": {"evidence_steps": ev, "gap_steps_latest": NEED - max(ev)},
                  "need_phase": {"tokens": 1000, "complete": True},
                  "compacted_between": 0 if CELLS[cell].history == "summary" else None})
        if repeat:
            r["repeat_index"] = repeat
    r.update(over)
    return r


def default_success(cell, variant, tc) -> int:
    if cell in ("W-0", "W-n-0", "Σ-n-0") and tc.endswith("-far"):
        return 0
    return 1


class Sweep:
    """A results root holding a synthetic luna sweep on templates 0..T-1."""

    def __init__(self, tmp_path, templates: int = T):
        self.root = tmp_path / "results"
        self.raw = self.root / "raw"
        self.T = templates
        self.clock = datetime(2026, 10, 10, tzinfo=UTC)
        draw = self.root / "draw" / "20261002T033145Z"
        draw.mkdir(parents=True)
        (draw / "draw.json").write_text(json.dumps({"seed": {"source": "nist", "seed": SEED}}),
                                        encoding="utf-8")
        self.success: dict[tuple, list[int]] = {}
        self.over: dict[tuple, dict] = {}
        self.long_replies: set[tuple[str, str]] = set()  # (cell, episode_id)
        self.turns: dict[tuple[str, str], int] = {}       # (cell, episode_id): turns written
        self.n = 0

    def outcome(self, cell, tc, values, variant=BASE):
        assert len(values) == self.T
        self.success[(cell, variant, tc)] = list(values)

    def fields(self, cell, tc, t, variant=BASE, **over):
        self.over.setdefault((cell, variant, tc, t), {}).update(over)

    def records(self, cell, variant=BASE, templates=None, repeat=0, task_cells=None):
        cells = task_cells or (hh.NR_TASK_CELLS if cell == ST else hh.TASK_CELLS)
        out = []
        for t in templates if templates is not None else range(self.T):
            for tc in cells:
                vals = self.success.get((cell, variant, tc))
                s = vals[t] if vals is not None else default_success(cell, variant, tc)
                out.append(record(cell, variant, tc, t, s, repeat,
                                  **self.over.get((cell, variant, tc, t), {})))
        return out

    def run(self, cell, variant=BASE, records=None, repeat=0, transcript=True, minutes=None):
        self.n += 1
        started = self.clock + timedelta(minutes=minutes if minutes is not None else self.n)
        name = cell.replace("Σ", "sigma")
        run_id = f"{started:%Y%m%dT%H%M%SZ}-{name}-gpt-6-luna" + (
            "-repeat1" if repeat else "") + ("" if variant == BASE else f"-{variant}")
        recs = records if records is not None else self.records(cell, variant, repeat=repeat)
        folder = self.root / "persistgym" / run_id
        folder.mkdir(parents=True)
        meta = {"experiment": "persistgym", "run_id": run_id, "cell_or_config": cell,
                "model_requested": "gpt-6-luna", "repeat_index": repeat,
                "started_utc": started.isoformat(), "exit_reason": "COMPLETED",
                "model_returned": ["gpt-6-luna"],
                "config": {"harness_cell": cell,
                           "harness": {"W_tokens": None, "window_counts_system_prompt": None,
                                       "notes_separator": "\n", "tokenizer": "o200k_base"},
                           "generator_config_hashes": [HASH],
                           "generator_config": {"W_tokens": W_SMALL,
                                                "window_counts_system_prompt": True,
                                                "tokenizer": "o200k_base"}}}
        (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        with open(folder / "episodes.jsonl", "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in recs)
        if transcript and cell in hh.WINDOW_CELLS:
            path = self.raw / "persistgym" / run_id / "transcript.jsonl.gz"
            path.parent.mkdir(parents=True)
            with gzip.open(path, "wt", encoding="utf-8") as fh:
                for r in recs:
                    tokens_ = 20 if (cell, r["episode_id"]) in self.long_replies else 2
                    turns = self.turns.get((cell, r["episode_id"]), NEED + 2)
                    for line in transcript_lines(r["episode_id"], cell, tokens_, turns):
                        fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        return run_id

    def standard(self, skip=(), repeat1=False):
        ids = {}
        for cell, variant in hh.KINDS:
            if (cell, variant) not in skip:
                ids[(cell, variant)] = self.run(cell, variant)
        if repeat1:
            for cell, variant in hh.KINDS:
                tmpl = [t for t in range(self.T) if t % 10 == 0]
                ids[(cell, variant, 1)] = self.run(
                    cell, variant, self.records(cell, variant, templates=tmpl, repeat=1),
                    repeat=1)
        return ids

    def compute(self, **kw):
        return hh.compute(self.root, "now", GIT, templates=self.T, **kw)

    def main(self, *args, monkeypatch):
        monkeypatch.setattr(hh, "T_REGISTERED", self.T)
        return hh.main(["--results-root", str(self.root), *args])


# The toy H1/H3 sweep (T = 10), hand-computed:
#   F-0 obs-NR-far 9/10, W-0 obs-NR-far 1/10    -> Penalty_NR = 0.8
#   F-0 obs-R-far 10/10, W-0 obs-R-far 8/10     -> Penalty_R  = 0.2, Delta_H1 = 0.6
#   single-turn obs-NR-far 10/10, der-NR-far 8/10 (18/20); F-0 9/10 and 9/10 (18/20)
#                                               -> Delta_H3 = 0
#   lookups (obs-R-far): F-0 1 in 10, W-0 5 in 10 -> ratio 5
#   need tokens (obs-R): F-0 1000 near and far, W-0 2000 far, 1250 near -> R_need = 1.6
#   total tokens (obs-R): F-0 10,300; W-0 6,180 far, 5,150 near -> R_tok = 1.2, literal 0.6
F0_ONR = [1] * 9 + [0]
W0_ONR = [1] + [0] * 9
W0_OR = [1] * 8 + [0] * 2
ST_ONR = [1] * 10
ST_DNR = [1] * 8 + [0] * 2
F0_DNR = [0] + [1] * 9


def toy(tmp_path) -> Sweep:
    sw = Sweep(tmp_path)
    sw.outcome("F-0", ONR, F0_ONR)
    sw.outcome("W-0", ONR, W0_ONR)
    sw.outcome("F-0", OR, [1] * 10)
    sw.outcome("W-0", OR, W0_OR)
    sw.outcome(ST, ONR, ST_ONR)
    sw.outcome(ST, DNR, ST_DNR)
    sw.outcome("F-0", DNR, F0_DNR)
    for t in range(T):
        sw.fields("F-0", OR, t, n_lookups=int(t == 9))
        sw.fields("W-0", OR, t, n_lookups=int(t < 5),
                  need_phase={"tokens": 2000, "complete": True},
                  usage={"input_tokens": 6000, "output_tokens": 180, "reasoning_tokens": 60})
        sw.fields("W-0", "observed-rec-near", t, need_phase={"tokens": 1250, "complete": True},
                  usage={"input_tokens": 5000, "output_tokens": 150, "reasoning_tokens": 50})
    return sw


# --- estimands on hand-computed toy data -----------------------------------------------------

def test_h1_and_h3_estimands_on_the_toy_sweep(tmp_path):
    sw = toy(tmp_path)
    sw.standard()
    h = sw.compute()
    assert h["status"] == hh.FINAL and h["provisional_reasons"] == []
    h1 = h["h1"]
    assert h1["cells"]["F-0 NR"] == {"n": 10, "successes": 9, "rate": 0.9, "exact": "9/10"}
    assert h1["penalty_nr"]["exact"] == "4/5"
    assert h1["penalty_r"]["exact"] == "1/5"
    assert h1["delta_h1"]["exact"] == "3/5"
    assert h1["manipulation_check"] is True and h1["recoverable_within_5pp"] is False
    h3 = h["h3"]
    assert h3["cells"]["single-turn"]["exact"] == "9/10" and h3["cells"]["F-0"]["exact"] == "9/10"
    assert h3["delta_h3"]["exact"] == "0"
    assert h3["per_cell"][ONR]["difference"]["exact"] == "1/10"
    assert h3["per_cell"][DNR]["difference"]["exact"] == "-1/10"
    lk = h["h1_lookups"]
    assert (lk["lookups_F0"], lk["lookups_W0"]) == (1, 5)
    assert lk["ratio"]["exact"] == "5" and lk["met"] is True
    tok = h["h1_tokens"]
    assert tok["R_need"]["ratio"]["exact"] == "8/5" and tok["R_need"]["prediction_met"] is True
    assert tok["R_tok"]["ratio"]["exact"] == "6/5" and tok["R_tok"]["at_least_1_30"] is False
    assert tok["literal"]["ratio"]["exact"] == "3/5"
    assert h["h1_predictions"]["all_met"] is False   # |Penalty_R| = 0.2 > 5pp
    # W-n-0 (all far 0, by default): penalties 0.9 and 1.0
    assert h1["w_n_0_alongside"]["penalty_nr"]["exact"] == "9/10"
    assert h1["w_n_0_alongside"]["penalty_r"]["exact"] == "1"
    assert h["primary_episodes"] == T * (4 * 8 + 8 + 4)


def test_exact_fractions_judge_a_threshold_that_floats_miss(tmp_path):
    """7/20 - 2/20 is 0.2499... in floats; the manipulation check needs >= 25pp exactly."""
    sw = Sweep(tmp_path, templates=20)
    sw.outcome("F-0", ONR, [1] * 7 + [0] * 13)
    sw.outcome("W-0", ONR, [1] * 2 + [0] * 18)
    sw.standard()
    h = sw.compute()
    assert 7 / 20 - 2 / 20 < 0.25
    assert h["h1"]["penalty_nr"]["exact"] == "1/4"
    assert h["h1"]["manipulation_check"] is True


def test_bootstrap_uses_seed_plus_10_and_matches_power_sim(tmp_path):
    sw = toy(tmp_path)
    sw.standard()
    h = sw.compute(boot=2000)
    assert h["bootstrap"]["seed"] == SEED + 10 and h["status"] == hh.PROVISIONAL
    idx = np.random.default_rng(SEED + 10).integers(0, T, size=(2000, T))
    y = {"f0_onr": np.array(F0_ONR, float), "w0_onr": np.array(W0_ONR, float),
         "f0_or": np.ones(T), "w0_or": np.array(W0_OR, float), "f0_dnr": np.array(F0_DNR, float),
         "st_onr": np.array(ST_ONR, float), "st_dnr": np.array(ST_DNR, float)}
    rows = ps.luna_per_template(y)                    # power_sim's integer contributions
    d1 = rows[idx, 0].sum(axis=1) / T
    d3 = rows[idx, 1].sum(axis=1) / (2 * T)
    np.testing.assert_allclose(h["h1"]["delta_h1"]["ci90"], np.quantile(d1, [0.05, 0.95]))
    np.testing.assert_allclose(h["h1"]["delta_h1"]["ci95"], np.quantile(d1, [0.025, 0.975]))
    np.testing.assert_allclose(h["h3"]["delta_h3"]["ci90"], np.quantile(d3, [0.05, 0.95]))
    assert h["h1"]["p_one_sided"] == pytest.approx(np.mean(d1 <= 0))
    assert h["h3"]["p_one_sided"] == pytest.approx(np.mean(d3 >= 0.05 - 1e-9))
    # determinism: the same inputs give the same numbers
    again = sw.compute(boot=2000)
    assert again["h1"] == h["h1"] and again["h3"] == h["h3"]


def test_bootstrap_ratio_of_sums_handles_unequal_cells():
    """With an excluded episode the resampled contrast is a ratio of sums, not a mean of
    per-template differences."""
    df = pd.DataFrame({"template": [0, 0, 1], "success": [1, 0, 1]})
    s = hh.Sample(df, 2)
    idx = np.array([[0, 0], [1, 1], [0, 1]])
    np.testing.assert_allclose(s.boot(idx), [1 / 2, 1.0, 2 / 3])
    assert s.point() == Fraction(2, 3)


def test_holm_and_the_family_of_4():
    two = hh.holm([0.01, 0.04])
    assert two["reject"] == [True, True]
    assert two["adjusted"] == pytest.approx([0.02, 0.04])
    assert hh.holm([0.03, 0.04])["reject"] == [False, False]   # 0.03 > 0.05 / 2
    assert hh.holm([0.02, 0.06])["reject"] == [True, False]
    assert hh.holm([0.025, 0.05])["reject"] == [True, True]    # boundaries included
    four = hh.holm([0.02, 0.03, 1.0, 1.0])
    assert four["reject"] == [False] * 4                       # 0.02 > 0.05 / 4
    assert hh.holm([0.01, 0.0125, 1.0, 1.0])["reject"] == [True, True, False, False]
    assert hh.holm([None, 0.01])["pvalues"] == [1.0, 0.01]


def test_supported_needs_holm_and_the_model_check():
    h1 = {"p_one_sided": 0.001, "model_check": {"agrees": True}, "kill": False}
    h3 = {"p_one_sided": 0.001, "model_check": {"agrees": False}}
    fam = hh.family_readings(h1, h3)
    assert fam["H1"]["supported"] and fam["H1"]["verdict"] == "supported"
    assert not fam["H3"]["supported"] and fam["H3"]["verdict"] == "inconclusive"
    h1["model_check"]["agrees"] = False
    assert hh.family_readings(h1, h3)["H1"]["supported"] is False
    h1 = {"p_one_sided": 0.04, "model_check": {"agrees": True}, "kill": True}
    fam = hh.family_readings(h1, {"p_one_sided": 0.001, "model_check": {"agrees": True}})
    # 0.001 <= 0.025, then 0.04 <= 0.05: both reject in the family of 2, not in the family of 4
    assert fam["H1"]["supported"] and fam["H3"]["supported"]
    assert not fam["H1"]["supported_family_of_4"] and fam["H3"]["supported_family_of_4"]
    assert fam["H1"]["verdict"] == "supported (Δ_H1 > 0), and the kill rule fires"


def test_readings_at_their_boundaries():
    assert hh.manipulation_met(Fraction(1, 4)) and not hh.manipulation_met(Fraction(249, 1000))
    assert hh.recoverable_within(Fraction(1, 20)) and hh.recoverable_within(Fraction(-1, 20))
    assert not hh.recoverable_within(Fraction(51, 1000))
    assert hh.ratio_met(Fraction(13, 10)) and not hh.ratio_met(Fraction(129, 100))
    # kill: Delta_H1 < 10pp and the 90% upper bound < 15pp
    assert not hh.h1_kill(Fraction(1, 10), 0.10)
    assert hh.h1_kill(Fraction(9, 100), 0.1499)
    assert not hh.h1_kill(Fraction(9, 100), 0.15)
    assert not hh.h1_kill(Fraction(9, 100), 0.15 - 1e-12)   # equal within the tolerance
    # H3: the 90% upper bound <= 5pp
    assert hh.h3_holds(0.05) and hh.h3_holds(0.05 + 1e-12) and not hh.h3_holds(0.0501)
    # one-sided p-values count ties (within the tolerance) on the null side
    assert hh.p_null_le(np.array([0.0, 1e-12, 0.1, 0.2]), 0.0) == 0.5
    assert hh.p_null_ge(np.array([0.05 - 1e-12, 0.04, 0.06, np.nan]), 0.05) == pytest.approx(2 / 3)


def test_the_kill_rule_fires_on_a_null_sweep(tmp_path):
    """Equal penalties: Delta_H1 = 0 with a degenerate interval, so the kill fires and H1 is
    not supported."""
    sw = Sweep(tmp_path)
    for cell in ("W-0",):
        sw.outcome(cell, ONR, [0] * T)
        sw.outcome(cell, OR, [0] * T)
    sw.standard()
    h = sw.compute()
    assert h["h1"]["delta_h1"]["exact"] == "0" and h["h1"]["delta_h1"]["ci90"] == [0.0, 0.0]
    assert h["h1"]["kill"] is True and h["h1"]["p_one_sided"] == 1.0
    assert h["family"]["H1"]["verdict"] == "kill rule fires"


def test_lookups_zero_rule(tmp_path):
    sw = Sweep(tmp_path)
    for t in range(T):
        sw.fields("W-0", OR, t, n_lookups=1)
    sw.standard()
    lk = sw.compute()["h1_lookups"]
    assert lk["ratio"] is None and lk["lookups_F0"] == 0
    assert lk["difference"]["exact"] == "1" and lk["difference"]["ci90"] == [1.0, 1.0]
    assert lk["met"] is True and "undefined" in lk["rule"]


def test_r_need_leaves_out_incomplete_need_phases(tmp_path):
    sw = Sweep(tmp_path)
    sw.fields("F-0", OR, 0, need_phase={"tokens": 999_999, "complete": False})
    sw.standard()
    tok = sw.compute()["h1_tokens"]
    assert tok["R_need"]["n"]["F-0 far"] == T - 1
    assert tok["R_need"]["episodes_left_out_need_phase_incomplete"] == 1
    assert tok["R_need"]["ratio"]["exact"] == "1"


# --- GLMs --------------------------------------------------------------------------------------

def _random_sweep(templates=60, seed=1):
    """F-0 and W-0 on the 8 task cells with moderate success rates, no separation."""
    rng = np.random.default_rng(seed)
    rows = []
    u = rng.normal(0, 0.5, templates)
    for t in range(templates):
        for cell in ("F-0", "W-0"):
            for tc in hh.TASK_CELLS:
                fact, rec_word, dist = tc.split("-")
                eta = (0.3 + u[t] - 0.8 * (cell == "W-0") + 0.4 * (rec_word == "rec")
                       + 0.9 * (cell == "W-0") * (rec_word == "rec") - 0.3 * (fact == "derived")
                       + 0.2 * (dist == "near"))
                rows.append({"cell": cell, "variant": BASE, "task_cell": tc, "fact": fact,
                             "recoverable": rec_word == "rec", "distance": dist, "template": t,
                             "success": int(rng.random() < 1 / (1 + np.exp(-eta)))})
    return pd.DataFrame(rows)


def test_glm_9_1_target_is_the_formula_fits_w_by_r_coefficient():
    df = _random_sweep()
    g = hh.glm_91(df)
    keep, _, _ = hh.informative(df.success.to_numpy(float), df.template.to_numpy())
    d = df[keep].assign(W=lambda x: (x.cell == "W-0").astype(float),
                        R=lambda x: x.recoverable.astype(float),
                        D=lambda x: (x.fact == "derived").astype(float),
                        N=lambda x: (x.distance == "near").astype(float))
    fit = smf.glm("success ~ C(template) + W*R*D*N", d, family=sm.families.Binomial()).fit()
    assert g["estimate"] == pytest.approx(fit.params["W:R"], abs=1e-6)
    assert g["coefficients"]["W-0"] == pytest.approx(fit.params["W"], abs=1e-6)
    assert g["se_available"] and g["se"] > 0
    # the logit penalties follow from the coefficients
    assert g["penalty_nr_logit"] == pytest.approx(-fit.params["W"], abs=1e-6)
    assert g["penalty_r_logit"] == pytest.approx(-(fit.params["W"] + fit.params["W:R"]),
                                                 abs=1e-6)


def test_model_checks_equal_power_sims_on_complete_data():
    rng = np.random.default_rng(3)
    t = 80
    y = {c: (rng.random(t) < p).astype(float) for c, p in
         (("f0_onr", 0.85), ("w0_onr", 0.2), ("f0_or", 0.9), ("w0_or", 0.6), ("f0_dnr", 0.8),
          ("st_onr", 0.8), ("st_dnr", 0.75))}
    rows = []
    for name, (cell, tc) in {"f0_onr": ("F-0", ONR), "w0_onr": ("W-0", ONR),
                             "f0_or": ("F-0", OR), "w0_or": ("W-0", OR),
                             "f0_dnr": ("F-0", DNR), "st_onr": (ST, ONR),
                             "st_dnr": (ST, DNR)}.items():
        fact, rec_word, dist = tc.split("-")
        rows += [{"cell": cell, "variant": BASE, "task_cell": tc, "fact": fact,
                  "recoverable": rec_word == "rec", "distance": dist, "template": i,
                  "success": int(v)} for i, v in enumerate(y[name])]
    df = pd.DataFrame(rows)
    assert hh.h1_standin(df)["estimate"] == pytest.approx(ps.h1_glm(y), abs=1e-9)
    assert hh.h3_glm(df)["ame"] == pytest.approx(ps.h3_glm_ame(y), abs=1e-9)
    lit = hh.h3_glm(df, with_derived=False)
    assert lit["ame"] is not None and lit["coefficients"].keys() == {"arm"}


def test_informative_selection_is_power_sims():
    y = np.array([1, 1, 0, 1, 0, 0, 1, 0], float)
    g = np.array([5, 5, 7, 7, 9, 9, 3, 3])
    z = np.arange(8, dtype=float)[:, None]
    keep, codes, labels = hh.informative(y, g)
    yk, ck, _, n = ps._informative(y, g, z)
    np.testing.assert_array_equal(y[keep], yk)
    np.testing.assert_array_equal(codes, ck)
    assert n == 2 and labels.tolist() == [7, 3]


def test_fe_poisson_ratio():
    """W-0 spends exactly twice F-0's tokens in every template: ratio 2, no spread."""
    rng = np.random.default_rng(0)
    base = rng.integers(1000, 5000, 30).astype(float)
    y = np.concatenate([base, 2 * base])
    groups = np.tile(np.arange(30), 2)
    x = np.concatenate([np.zeros(30), np.ones(30)])[:, None]
    fit = hh.fe_poisson(y, groups, x, ["W-0"])
    assert fit["ratios"]["W-0"]["ratio"] == pytest.approx(2.0)
    assert fit["ratios"]["W-0"]["se"] is None or fit["ratios"]["W-0"]["se"] < 1e-6
    # against statsmodels with a noisy outcome
    y2 = np.concatenate([base, base * rng.uniform(1.2, 1.8, 30)]).round()
    fit2 = hh.fe_poisson(y2, groups, x, ["W-0"])
    d = pd.DataFrame({"y": y2, "g": groups, "w": x[:, 0]})
    ref = smf.glm("y ~ C(g) + w", d, family=sm.families.Poisson()).fit(
        cov_type="cluster", cov_kwds={"groups": d.g, "use_correction": False})
    assert fit2["ratios"]["W-0"]["beta"] == pytest.approx(ref.params["w"], abs=1e-8)
    # statsmodels without correction, times G/(G-1) on the variance
    assert fit2["ratios"]["W-0"]["se"] == pytest.approx(ref.bse["w"] * np.sqrt(30 / 29),
                                                        rel=1e-6)
    # no events in W-0: ratio 0, no interval, and the fit runs without it
    y3 = np.concatenate([base, np.zeros(30)])
    fit3 = hh.fe_poisson(y3, groups, x, ["W-0"])
    assert fit3["ratios"]["W-0"]["ratio"] == 0.0 and fit3["ratios"]["W-0"]["ratio_ci95"] is None
    # no events in the reference cell (F-0): no finite ratio
    y4 = np.concatenate([np.zeros(30), base])
    fit4 = hh.fe_poisson(y4, groups, x, ["W-0"])
    assert fit4["ratios"] == {} and "reference" in fit4["note"]
    # a template whose outcome is 0 everywhere is dropped from the fit
    y5 = y2.copy()
    y5[[0, 30]] = 0
    fit5 = hh.fe_poisson(y5, groups, x, ["W-0"])
    assert fit5["n_templates_all_zero"] == 1 and fit5["ratios"]["W-0"]["ratio"] > 1


def test_cost_outcomes_and_glms_in_the_toy_sweep(tmp_path):
    sw = toy(tmp_path)
    sw.standard()
    h = sw.compute()
    row = next(r for r in h["cost_outcomes"]
               if r["task_cell"] == OR and r["outcome"] == "tokens_total")
    assert row["ratios"]["W-0"]["ratio"] == pytest.approx(6180 / 10300)
    assert row["ratios"]["W-n-0"]["ratio"] == pytest.approx(1.0)
    look = next(r for r in h["cost_outcomes"]
                if r["task_cell"] == OR and r["outcome"] == "n_lookups")
    assert look["ratios"]["W-0"]["ratio"] == pytest.approx(5.0)
    assert look["ratios"]["W-n-0"]["ratio"] == 0.0 and look["ratios"]["W-n-0"]["note"]
    assert h["glm_9_1"]["estimate"] is not None
    # F-0 obs-R-far is 10/10: the logit-scale Delta_H1 is not finite, and that is flagged
    mc = h["h1"]["model_check"]
    assert mc["logit_delta_h1_finite"] is False
    assert mc["h1_cells_no_variation"] == ["F-0 observed-rec-far: all 1 (10 episodes)"]
    assert h["bayesian_glmm"].startswith("not run")


# --- keys, re-runs and exclusions (DESIGN §7.8, §13) ------------------------------------------

def test_a_declared_rerun_replaces_a_transport_failure(tmp_path):
    sw = Sweep(tmp_path)
    recs = sw.records("W-0")
    eid = hh.episode_id_of("W-0", BASE, 3, ONR)
    for r in recs:
        if r["episode_id"] == eid:
            r.update(exit_reason="API_ERROR", need_correct=False, need_outcome=None)
    sw.standard(skip={("W-0", BASE)})
    first = sw.run("W-0", records=recs)
    sw.outcome("W-0", ONR, [0, 0, 0, 1, 0, 0, 0, 0, 0, 0])
    rerun = sw.run("W-0", records=sw.records("W-0", templates=[3]))
    with pytest.raises(hh.Refusal, match="not declared"):
        sw.compute()
    h = sw.compute(links={rerun: first})
    assert h["h1"]["cells"]["W-0 NR"] == {"n": 10, "successes": 1, "rate": 0.1,
                                          "exact": "1/10"}
    dropped = {(d["episode_id"], d["kept_from"]) for d in h["dropped_records"]}
    # the re-run's other 7 records of template 3 are dropped; the original's count
    assert len(dropped) == 7 and all(k == first for _, k in dropped)
    assert (eid, first) not in dropped


def test_two_transport_failures_exclude_and_one_is_pending(tmp_path):
    sw = Sweep(tmp_path)
    eid = hh.episode_id_of("F-0", BASE, 2, ONR)
    recs = sw.records("F-0")
    for r in recs:
        if r["episode_id"] == eid:
            r["exit_reason"] = "API_ERROR"
    sw.standard(skip={("F-0", BASE)})
    first = sw.run("F-0", records=recs)
    with pytest.raises(hh.Refusal, match="pending"):
        sw.compute()
    h = sw.compute(allow_incomplete=True)
    assert h["status"] == hh.PROVISIONAL and any("pending" in x for x in h["provisional_reasons"])
    again = [dict(r, exit_reason="API_ERROR") for r in sw.records("F-0", templates=[2])]
    rerun = sw.run("F-0", records=again)
    h = sw.compute(links={rerun: first})
    assert h["status"] == hh.FINAL
    row = next(e for e in h["exclusions"] if e["kind"] == "F-0" and e["task_cell"] == ONR)
    assert row["excluded_transport"] == 1 and row["pending"] == 0
    assert h["h1"]["cells"]["F-0 NR"]["n"] == T - 1


def test_a_continuation_keeps_the_first_final_record(tmp_path):
    sw = Sweep(tmp_path)
    recs = sw.records("W-n-0")
    for r in recs:
        if r["template_id"] == "main-000009":
            r["exit_reason"] = "COST_CAP"
    sw.standard(skip={("W-n-0", BASE)})
    first = sw.run("W-n-0", records=recs)
    sw.outcome("W-n-0", ONR, [0] * 9 + [1])
    cont = sw.run("W-n-0", records=sw.records("W-n-0", templates=[8, 9]))
    h = sw.compute(links={cont: first})
    assert h["h1"]["cells"]["W-n-0 NR"]["successes"] == 1      # template 9 from the continuation
    kept = {d["episode_id"]: d["kept_from"] for d in h["dropped_records"]}
    assert len(kept) == 8 and set(kept.values()) == {first}     # template 8 was final already


def test_echo_exclusions_are_counted_and_flagged(tmp_path):
    sw = Sweep(tmp_path)
    sw.fields("W-0", ONR, 4, exit_reason="REASONING_CONTEXT_MISMATCH", excluded=True,
              exclusion_reason="reasoning.context requested 'current_turn', echoed None")
    sw.fields("F-0", OR, 5, echo={"context_requested": "current_turn",
                                  "context_echoed": {"current_turn": 11, "all_turns": 1},
                                  "effort_requested": "medium", "effort_echoed": {"medium": 12},
                                  "models_returned": {"gpt-6-luna": 12}})
    sw.standard()
    h = sw.compute()
    ex = {(e["kind"], e["task_cell"]): e for e in h["exclusions"]}
    assert ex[("W-0", ONR)]["excluded_echo"] == 1 and ex[("W-0", ONR)]["echo_over_5pct"]
    assert ex[("F-0", OR)]["excluded_echo"] == 1          # the defensive echo check
    assert "W-0 observed-nonrec-far" in h["echo_cells_over_5pct"]
    assert h["h1"]["cells"]["W-0 NR"]["n"] == T - 1 and h["h1"]["cells"]["F-0 R"]["n"] == T - 1


def test_resolve_rule_details():
    def run(run_id, minutes, recs, cell="F-0"):
        return hh.Run(run_id=run_id, folder=None, cell=cell, variants=(BASE,), repeat_index=0,
                      started=datetime(2026, 10, 10, tzinfo=UTC) + timedelta(minutes=minutes),
                      exit_reason="COMPLETED", model_returned=[], records=recs, window={})

    def rec(ending):
        return {"episode_id": "main-000000/observed-nonrec-far/base", "exit_reason": ending}

    a = run("a", 1, [rec("DONE")])
    b = run("b", 2, [rec("DONE")])
    res, _ = hh.resolve([b, a], {"b": "a"})
    (r,) = res.values()
    assert r.run_id == "a" and r.dropped == [{"run_id": "b", "exit_reason": "DONE"}]
    # two API errors before a final record: excluded, the final record dropped
    c = run("c", 3, [rec("API_ERROR")])
    d = run("d", 4, [rec("API_ERROR")])
    e = run("e", 5, [rec("DONE")])
    res, _ = hh.resolve([c, d, e], {"d": "c", "e": "d"})
    (r,) = res.values()
    assert r.status == "excluded" and r.record is None and len(r.dropped) == 1
    # RUN_STOPPED and ERROR:* are not final; MAX_TURNS and AGENT_ERROR are
    for ending, final in (("RUN_STOPPED", False), ("ERROR:KeyboardInterrupt", False),
                          ("COST_CAP", False), ("MAX_TURNS", True), ("AGENT_ERROR", True),
                          ("REASONING_EFFORT_MISMATCH", True)):
        assert hh.is_final(ending) is final
    res, warn = hh.resolve([run("f", 6, [rec("WEIRD")])], {})
    assert next(iter(res.values())).status == "pending" and "WEIRD" in warn[0]
    with pytest.raises(hh.Refusal, match="earlier run of the same cell"):
        hh.resolve([a, b], {"a": "b"})
    with pytest.raises(hh.Refusal, match="twice in one run"):
        hh.resolve([run("g", 7, [rec("DONE"), rec("DONE")])], {})


def test_repeat_one_stays_out_of_primary_and_its_agreement_is_reported(tmp_path):
    sw = Sweep(tmp_path, templates=20)
    sw.standard(repeat1=True)
    base = sw.compute()
    # repeat 1 disagrees on template 10 of F-0 obs-NR-far; primary results do not change
    sw2 = Sweep(tmp_path / "b", templates=20)
    sw2.standard()
    recs = sw2.records("F-0", templates=[0, 10], repeat=1)
    for r in recs:
        if r["episode_id"] == hh.episode_id_of("F-0", BASE, 10, ONR):
            r.update(need_correct=False, need_outcome="wrong")
    sw2.run("F-0", records=recs, repeat=1)
    h = sw2.compute()
    assert h["h1"] == base["h1"] and h["h3"] == base["h3"]
    rep = next(r for r in h["repeats"] if r["kind"] == "F-0")
    assert rep["pairs"] == 16 and rep["agree"] == 15 and rep["repeat0_only_success"] == 1
    full = next(r for r in base["repeats"] if r["kind"] == "single-turn control")
    assert full["pairs"] == 8 and full["agreement"] == 1.0


# --- refusal ------------------------------------------------------------------------------------

def test_refuses_an_incomplete_sweep(tmp_path, monkeypatch, capsys):
    sw = Sweep(tmp_path)
    sw.standard(skip={(ST, BASE)})
    sw.run(ST, records=sw.records(ST, templates=range(T - 1)))
    assert sw.main("--no-write", monkeypatch=monkeypatch) == 2
    err = capsys.readouterr().err
    assert "single-turn control: 4 of 40 repeat-0 episodes have no record" in err
    assert sw.main("--no-write", "--allow-incomplete", monkeypatch=monkeypatch) == 0
    assert "**Status: PROVISIONAL.**" in capsys.readouterr().out


def test_refuses_without_transcripts_unless_allowed(tmp_path):
    sw = Sweep(tmp_path)
    for cell, variant in hh.KINDS:
        sw.run(cell, variant, transcript=False)
    with pytest.raises(hh.Refusal, match="no raw transcript"):
        sw.compute()
    h = sw.compute(allow_incomplete=True)
    assert h["status"] == hh.PROVISIONAL and len(h["accounting_check"]["missing_transcripts"]) == 2


def test_other_runs_are_skipped_and_bad_records_refused(tmp_path):
    sw = Sweep(tmp_path)
    sw.standard()
    other = sw.root / "persistgym" / "x-sol"
    other.mkdir()
    (other / "meta.json").write_text(json.dumps({"experiment": "persistgym",
                                                 "model_requested": "gpt-6.1-sol"}))
    h = sw.compute()
    assert {"folder": "x-sol", "reason": "model 'gpt-6.1-sol', not gpt-6-luna"} in \
        h["inputs"]["skipped"]
    bad = sw.records("F-0", templates=[0])
    bad[0]["harness_cell"] = "W-0"
    sw.run("F-0", records=bad)
    with pytest.raises(hh.Refusal, match="has harness cell 'W-0'"):
        sw.compute()


# --- §2.8: the bug stop and the accounting -------------------------------------------------------

def test_bug_stop_far_window_survival(tmp_path, monkeypatch, capsys):
    sw = Sweep(tmp_path)
    sw.fields("W-n-0", ONR, 6, need_payload={"S": True, "assistant_carried": {"carried": False}})
    sw.standard()
    with pytest.raises(hh.AccountingBug, match="S_verbatim = 1 at far distance"):
        sw.compute(allow_incomplete=True)
    assert sw.main("--no-write", monkeypatch=monkeypatch) == 2
    assert "bug stop" in capsys.readouterr().err


def test_bug_stop_replay_disagrees(tmp_path):
    """A near W-0 record says the evidence was lost, but the turns sent kept it."""
    sw = Sweep(tmp_path)
    sw.fields("W-0", "derived-rec-near", 1,
              need_payload={"S": False, "assistant_carried": {"carried": False}})
    sw.standard()
    with pytest.raises(hh.AccountingBug, match="the drop-oldest replay gives 1"):
        sw.compute()


def test_expected_near_loss_is_not_a_bug(tmp_path):
    """Longer replies pushed the near evidence out: S_verbatim = 0 agrees with the replay."""
    sw = Sweep(tmp_path)
    eid = hh.episode_id_of("W-0", BASE, 1, "observed-nonrec-near")
    sw.long_replies.add(("W-0", eid))
    assert _keep(20, NEED) == 9
    sw.fields("W-0", "observed-nonrec-near", 1,
              need_payload={"S": False, "assistant_carried": {"carried": False}},
              need_info={"keep_start": 9}, need_correct=False, need_outcome="wrong")
    sw.standard()
    h = sw.compute()
    assert h["accounting_check"]["checked"] == 2 * T * 8
    row = next(r for r in h["accounting"]
               if r["cell"] == "W-0" and r["task_cell"] == "observed-nonrec-near")
    assert row["near_losses"] == 1 and row["near_loss_share"] == pytest.approx(0.1)
    assert row["planned_vs_verbatim_mismatch"] == 1
    assert row["success_given_S0"] == {"n": 1, "successes": 0, "rate": 0.0}
    assert row["residual_at_S1"] == {"n": 9, "successes": 9, "rate": 1.0}


def test_an_episode_stopped_at_its_need_call_is_not_a_bug(tmp_path):
    """The runner records need_payload before the need step's first call and the transcript
    after it: an API error at that call leaves no recorded need request. That is skipped (and
    re-run under §13); the same gap in a finished episode is a bug."""
    sw = Sweep(tmp_path)
    eid = hh.episode_id_of("W-0", BASE, 2, ONR)
    sw.turns[("W-0", eid)] = NEED                     # turns 0..NEED-1 only
    sw.fields("W-0", ONR, 2, exit_reason="API_ERROR", need_correct=False, need_outcome=None)
    sw.standard(skip={("W-0", BASE)})
    first = sw.run("W-0")
    sw.turns.clear()
    sw.over.clear()
    rerun = sw.run("W-0", records=sw.records("W-0", templates=[2]))
    h = sw.compute(links={rerun: first})
    assert any("stopped at their need step's first call" in w for w in h["warnings"])
    sw2 = Sweep(tmp_path / "b")
    sw2.turns[("W-0", eid)] = NEED
    sw2.standard()
    with pytest.raises(hh.AccountingBug, match="need step's first request is not in"):
        sw2.compute()


def test_keep_start_disagreement_is_a_warning(tmp_path):
    sw = Sweep(tmp_path)
    sw.fields("W-0", ONR, 0, need_info={"keep_start": 3})
    sw.standard()
    h = sw.compute()
    assert any("keep_start in 1 episode" in w for w in h["warnings"])


def test_accounting_carried_used_rescued(tmp_path):
    """W-n-0 observed-nonrec-far (S_verbatim = 0 by design): 3 carried (2 used), 7 not
    carried, of which 2 looked something up (1 rescued) and 5 did not (1 rescued)."""
    sw = Sweep(tmp_path)
    succ = [1, 1, 0, 1, 0, 0, 0, 0, 0, 1]
    sw.outcome("W-n-0", ONR, succ)
    for t in range(T):
        sw.fields("W-n-0", ONR, t, n_lookups=int(t in (3, 4)),
                  need_payload={"S": False, "assistant_carried": {"carried": t < 3}})
    for t in (0, 1):   # Σ-n-0 near: compacted between, and the bridge carried the fact
        sw.fields("Σ-n-0", "observed-nonrec-near", t, compacted_between=1,
                  need_payload={"S": False, "assistant_carried": {"carried": False}},
                  need_bridge_carried={"carried": True})
    sw.standard()
    h = sw.compute()
    row = next(r for r in h["accounting"] if r["cell"] == "W-n-0" and r["task_cell"] == ONR)
    assert row["P_carried"] == {"n": 10, "carried": 3, "rate": 0.3}
    assert row["used_given_carried"] == {"n": 3, "successes": 2, "rate": pytest.approx(2 / 3)}
    assert row["rescued_with_lookup"] == {"n": 2, "successes": 1, "rate": 0.5}
    assert row["rescued_without_lookup"] == {"n": 5, "successes": 1, "rate": 0.2}
    assert row["S_1"] == 3 and row["S_planned"] == 0 and row["near_losses"] is None
    sig = next(r for r in h["accounting"]
               if r["cell"] == "Σ-n-0" and r["task_cell"] == "observed-nonrec-near")
    assert sig["S_planned"] is None and sig["exploratory"]
    assert sig["P_carried"] == {"n": 2, "carried": 2, "rate": 1.0}
    assert sig["by_compacted_between"]["1"]["n"] == 2
    assert sig["by_compacted_between"]["0"]["S_verbatim_1"] == T - 2
    w0 = next(r for r in h["accounting"] if r["cell"] == "W-0" and r["task_cell"] == ONR)
    assert w0["P_carried"] is None and w0["S_1"] == 0      # no notes: S = S_verbatim


def test_replay_matches_the_harness_on_real_episodes(tmp_path, monkeypatch):
    """Real episodes (generator, small volume) played by the harness's W-0 and W-n-0 cells with
    the fake model: long replies push near evidence out, and lookups shift turns. The replay
    agrees with the runner's S_verbatim, window start and payload in every episode; a flipped
    S is caught."""
    from harnesses.config import HarnessConfig
    from harnesses.fake import FakeModel
    from harnesses.runner import run_batch
    from persistgym.config import GeneratorConfig
    from persistgym.episode import ALL_CELLS
    from persistgym.render import generate

    small = GeneratorConfig(W_tokens=6_400, v_tokens=400, assumed_max_reply_tokens=200)
    eps = [ep for _, e in generate("main", range(2), small, ALL_CELLS, ("base",)) for ep in e]
    long_reply = _text("Notes:", 5_000) + "\nACTION: ack(none)"
    short = _text("Notes:", 150) + "\nACTION: ack(none)"

    def reply(payload, i):
        if i % 6 == 4:
            return "ACTION: lookup(record)"
        return long_reply if i % 7 == 0 else short

    results = tmp_path / "results"
    for cell in ("W-0", "W-n-0"):
        run_batch(eps, CELLS[cell], HarnessConfig(), FakeModel(reply), experiment="persistgym",
                  run_id=f"r-{cell}", results_root=results, raw_root=results / "raw")
    monkeypatch.setattr(hh, "GENERATOR_HASH", eps[0].config_hash)
    runs, skipped = hh.discover(results)
    assert len(runs) == 2 and skipped == []
    check = hh.accounting_check(runs, results / "raw")
    assert check["bugs"] == [] and check["warnings"] == []
    assert check["checked"] == 2 * len(eps)
    recs = [r for run in runs for r in run.records]
    near = [r["need_payload"]["S"] for r in recs if r["task_cell"].endswith("-near")]
    assert True in near and False in near                  # both outcomes are exercised
    assert any(r["n_lookups"] for r in recs)               # and lookups shifted turns
    # flip one near episode's S: the replay catches it
    run = next(r for r in runs if r.cell == "W-0")
    path = run.folder / "episodes.jsonl"
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    target = next(x for x in lines if x["task_cell"].endswith("-near")
                  and x["need_payload"]["S"] is True)
    target["need_payload"]["S"] = False
    path.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    runs, _ = hh.discover(results)
    bugs = hh.accounting_check(runs, results / "raw")["bugs"]
    assert len(bugs) == 1 and target["episode_id"] in bugs[0]


# --- output --------------------------------------------------------------------------------------

def test_main_writes_the_outputs(tmp_path, monkeypatch):
    sw = toy(tmp_path)
    sw.standard()
    out = tmp_path / "out"
    assert sw.main("--out-dir", str(out), monkeypatch=monkeypatch) == 0
    h = json.loads((out / "h1h3.json").read_text(encoding="utf-8"))
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    text = (out / "summary.md").read_text(encoding="utf-8")
    assert h["status"] == hh.FINAL and h["h1"]["delta_h1"]["exact"] == "3/5"
    assert meta["experiment"] == "persistgym_h1h3" and meta["paid_calls"] == 0
    assert meta["seeds"] == {"bootstrap": SEED + 10} and meta["exit_reason"] == "completed"
    assert "git_commit" in meta and len(meta["runs"]) == 6
    for needle in ("## What it does not show", "Not a model comparison", "**Δ_H1 = ",
                   "Holm", "Bayesian GLMM sensitivity (§9.1): not run", "## Repeats",
                   "§2.8 accounting check: passed on 160 window-cell episodes"):
        assert needle in text


def test_model_string_split_and_achieved_power(tmp_path):
    sw = Sweep(tmp_path)
    for tc in (ONR, OR):
        sw.fields("W-0", tc, 0, echo={"context_requested": "current_turn",
                                      "context_echoed": {"current_turn": 12},
                                      "effort_requested": "medium",
                                      "effort_echoed": {"medium": 12},
                                      "models_returned": {"gpt-6-luna-2026-10-20": 12}})
    sw.standard()
    h = sw.compute()
    assert set(h["model_strings"]["strings"]) == {"gpt-6-luna", "gpt-6-luna-2026-10-20"}
    assert h["model_strings"]["split"]["gpt-6-luna-2026-10-20"]["episodes"] == 2
    power = {p["scenario"]: p for p in h["achieved_power"]}
    assert power["primary"]["T_set"] == 200
    assert (power["primary"]["power_h1"], power["primary"]["power_h3"]) == (0.647, 0.781)


def test_bayesian_status(monkeypatch):
    monkeypatch.setattr(hh.importlib.util, "find_spec", lambda name: None)
    assert hh.bayesian_status() == "not run (bambi not installed)"
    monkeypatch.setattr(hh.importlib.util, "find_spec", lambda name: object())
    assert "no fit for it" in hh.bayesian_status()
