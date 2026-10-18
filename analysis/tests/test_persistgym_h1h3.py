"""H1 and H3 on luna's sweep (analysis/persistgym_h1h3.py; PREREG §3 H1, §3 H3, §2.8, §9.1-§9.5,
§13): every estimand on hand-computed toy data, the bootstrap (its seed, determinism, and its
agreement with power_sim's per-template contrasts), Holm and "supported", the kill and
prediction readings at their boundaries, DESIGN §7.8's dedup rule, §13's exclusions, the refusal
of an incomplete sweep and a closed one, §2.8's bug stop (on synthetic transcripts and on real
episodes played by the harness with the fake model), the model checks under separation (H1's
rules, the Firth fit, H3's registered model), the input list, and the Bayesian sensitivity fit
(once for real on a small sweep; stubbed elsewhere, since it takes seconds per fit). And R8's
replication on claude-haiku-5-5 (PREREG §17.8): its profile and discovery, the optional W-n-0,
no echo exclusion, the exclusion of an episode the request-side check stopped, its usage
(unreported reasoning counts: unavailable per task cell and harness cell), §2.8's replay on
Messages transcripts (synthetic, and real episodes played on the Messages wire with the fake
model), its labels (never "supported"), its power (and the power table's provenance), its
output folder; and that luna's profile, output keys and null reasoning counts are unchanged.

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
from scipy import optimize

from analysis import persistgym_h1h3 as hh
from analysis import power_sim as ps
from harnesses import registered
from harnesses.cells import CELLS, NOTES_INSTRUCTION
from harnesses.fake import padded_text
from harnesses.wire import EMPTY_REPLY_PLACEHOLDER
from persistgym.survival import window_keep_start

SEED = 4086943125952605534
BAYES_STUB = {"status": "not run", "note": "stubbed in tests"}
BAYES_REAL = hh.bayesian_glmm
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


@pytest.fixture(autouse=True)
def _no_bayes_fit(monkeypatch):
    """The Bayesian sensitivity fit takes seconds; every test but its own stubs it."""
    monkeypatch.setattr(hh, "bayesian_glmm", lambda prim, seed, settings=None: dict(BAYES_STUB))


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
    MODEL, EXPERIMENT = "gpt-6-luna", "persistgym"

    def make_record(self, *args, **over) -> dict:
        return record(*args, **over)

    def transcript(self, eid: str, cell: str, reply_tokens: int, turns: int):
        return transcript_lines(eid, cell, reply_tokens, turns)

    def kinds(self):
        return hh.KINDS

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
        self.ids: list[str] = []                          # every run written, the input list

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
                out.append(self.make_record(cell, variant, tc, t, s, repeat,
                                            **self.over.get((cell, variant, tc, t), {})))
        return out

    def run(self, cell, variant=BASE, records=None, repeat=0, transcript=True, minutes=None,
            exit_reason="COMPLETED", episode_ids=None, parallel=None):
        self.n += 1
        started = self.clock + timedelta(minutes=minutes if minutes is not None else self.n)
        name = cell.replace("Σ", "sigma")
        run_id = f"{started:%Y%m%dT%H%M%SZ}-{name}-{self.MODEL}" + (
            "-repeat1" if repeat else "") + ("" if variant == BASE else f"-{variant}")
        recs = records if records is not None else self.records(cell, variant, repeat=repeat)
        self.ids.append(run_id)
        folder = self.root / self.EXPERIMENT / run_id
        folder.mkdir(parents=True)
        meta = {"experiment": self.EXPERIMENT, "run_id": run_id, "cell_or_config": cell,
                "model_requested": self.MODEL, "repeat_index": repeat,
                "started_utc": started.isoformat(), "exit_reason": exit_reason,
                "model_returned": [self.MODEL],
                "config": {"harness_cell": cell,
                           "harness": {"W_tokens": None, "window_counts_system_prompt": None,
                                       "notes_separator": "\n", "tokenizer": "o200k_base"},
                           "generator_config_hashes": [HASH],
                           "generator_config": {"W_tokens": W_SMALL,
                                                "window_counts_system_prompt": True,
                                                "tokenizer": "o200k_base"}}}
        if episode_ids is not None:                   # the run's plan, in order (runner)
            meta["config"]["episode_ids"] = list(episode_ids)
        if parallel is not None:                      # how parallel play went (runner)
            meta["parallel"] = parallel
        (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        with open(folder / "episodes.jsonl", "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in recs)
        if transcript and cell in hh.WINDOW_CELLS:
            path = self.raw / self.EXPERIMENT / run_id / "transcript.jsonl.gz"
            path.parent.mkdir(parents=True)
            with gzip.open(path, "wt", encoding="utf-8") as fh:
                for r in recs:
                    tokens_ = 20 if (cell, r["episode_id"]) in self.long_replies else 2
                    turns = self.turns.get((cell, r["episode_id"]), NEED + 2)
                    for line in self.transcript(r["episode_id"], cell, tokens_, turns):
                        fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        return run_id

    def standard(self, skip=(), repeat1=False):
        ids = {}
        for cell, variant in self.kinds():
            if (cell, variant) not in skip:
                ids[(cell, variant)] = self.run(cell, variant)
        if repeat1:
            for cell, variant in self.kinds():
                tmpl = [t for t in range(self.T) if t % 10 == 0]
                ids[(cell, variant, 1)] = self.run(
                    cell, variant, self.records(cell, variant, templates=tmpl, repeat=1),
                    repeat=1)
        return ids

    def compute(self, **kw):
        kw.setdefault("runs", list(self.ids))
        return hh.compute(self.root, "now", GIT, templates=self.T, **kw)

    def main(self, *args, monkeypatch, named=True):
        monkeypatch.setattr(hh, "T_REGISTERED", self.T)
        runs = [x for r in self.ids for x in ("--run", r)] if named else []
        return hh.main(["--results-root", str(self.root), *runs, *args])


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
    assert not fam["H3"]["supported"] and fam["H3"]["verdict"] == hh.MODEL_DISAGREES
    h3_weak = {"p_one_sided": 0.2, "model_check": {"agrees": True}}
    assert hh.family_readings(h1, h3_weak)["H3"]["verdict"] == "inconclusive"
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
    assert g["fitted_by"].startswith("statsmodels") and g["logit_status"] == hh.FINITE
    keep, _, _ = hh.informative(df.success.to_numpy(float), df.template.to_numpy())
    d = df[keep].assign(W=lambda x: (x.cell == "W-0").astype(float),
                        R=lambda x: x.recoverable.astype(float),
                        D=lambda x: (x.fact == "derived").astype(float),
                        N=lambda x: (x.distance == "near").astype(float))
    fit = smf.glm("success ~ C(template) + W*R*D*N", d, family=sm.families.Binomial()).fit()
    assert g["estimate"] == pytest.approx(fit.params["W:R"], abs=1e-6)
    assert g["coefficients"]["W-0"] == pytest.approx(fit.params["W"], abs=1e-6)
    assert g["se_available"] and g["se"] > 0
    # the SE is the cluster-robust one with the G/(G - 1) factor only: power_sim's 'clusters'
    sub, z, names = hh._glm_91_rows(df, ("W-0",))
    ref = ps.fe_logit(sub.success.to_numpy(float), sub.template.to_numpy(), z, "fast",
                      "clusters")
    assert g["se"] == pytest.approx(float(ref[1][-1]), rel=1e-5)
    assert g["estimate_emulated"] == pytest.approx(g["estimate"], abs=1e-6)
    assert not g["emulated_sign_disagrees"]
    # the logit penalties follow from the coefficients, with their own Wald intervals
    con = g["contrasts"]
    assert con["penalty_nr_logit"]["estimate"] == pytest.approx(-fit.params["W"], abs=1e-6)
    assert con["penalty_r_logit"]["estimate"] == pytest.approx(
        -(fit.params["W"] + fit.params["W:R"]), abs=1e-6)
    assert con["penalty_nr_logit"]["se"] == pytest.approx(float(ref[1][names.index("W-0")]),
                                                          rel=1e-5)
    assert con["penalty_r_logit"]["ci90"] is not None


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
    assert hh.h3_glm_powersim(df)["ame"] == pytest.approx(ps.h3_glm_ame(y), abs=1e-9)
    lit = hh.h3_glm_literal(df)
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
    # no rows in the reference cell (every F-0 outcome missing): the template effects and the
    # W-0 indicator are collinear, so no ratio is identified and none is fitted
    y6 = np.concatenate([np.full(30, np.nan), base])
    fit6 = hh.fe_poisson(y6, groups, x, ["W-0"])
    assert fit6["ratios"] == {} and fit6["note"] == "no rows in the reference cell (F-0): no ratio"
    assert fit6["n_rows"] == 30
    # a template whose outcome is 0 everywhere is dropped from the fit
    y5 = y2.copy()
    y5[[0, 30]] = 0
    fit5 = hh.fe_poisson(y5, groups, x, ["W-0"])
    assert fit5["n_templates_all_zero"] == 1 and fit5["ratios"]["W-0"]["ratio"] > 1


def test_cost_outcomes_and_glms_in_the_toy_sweep(tmp_path, monkeypatch):
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
    # F-0 obs-R-far is 10/10: the logit-scale Delta_H1 is -inf (statsmodels stops far below
    # 0). The rule in force, Firth's (ruled item 1, 2026-10-10), reads a finite penalized
    # estimate, which is positive here and so agrees
    mc = h["h1"]["model_check"]
    assert mc["logit_status"] == hh.MINUS_INF and mc["rule"] == "firth"
    assert mc["estimate"] < -5                                  # the stopping point
    assert mc["h1_cells_no_variation"] == ["F-0 observed-rec-far: all 1 (10 episodes)"]
    firth = h["glm_9_1_firth"]
    assert firth["note"] is None and 0 < firth["estimate"] < 10
    assert mc["firth_estimate"] == firth["estimate"]
    assert mc["agrees"] is True and mc["sign"] == 1
    assert not h["h1"]["scales_disagree_in_sign"]
    assert h["bayesian_glmm"] == BAYES_STUB
    # the literal rule (not in force) reads the limit's sign: -inf does not agree, whatever
    # statsmodels' stopping point says, and the scales then disagree in sign
    monkeypatch.setattr(hh, "H1_SEPARATION_RULE", "literal")
    h = sw.compute()
    mc = h["h1"]["model_check"]
    assert mc["logit_status"] == hh.MINUS_INF and mc["rule"] == "literal"
    assert mc["agrees"] is False and mc["sign"] == -1
    assert h["h1"]["scales_disagree_in_sign"]
    # a Firth fit that fails: the model check has no sign, and the summary says why and makes
    # no sign comparison with it (changed C, 2026-10-10)
    monkeypatch.setattr(hh, "H1_SEPARATION_RULE", "firth")
    monkeypatch.setattr(hh, "firth_fe_logit", lambda *a, **k: None)
    h = sw.compute()
    assert h["h1"]["model_check"]["sign"] is None and h["h1"]["model_check"]["agrees"] is False
    text = "\n".join(hh.summary_lines(h))
    assert "decides: no estimate (the Firth fit did not converge)." in text
    assert "no sign to compare with the model check" in text
    assert "the same sign as the model check" not in text
    # H3 with one template with outcome variation (changed B): the summary says the check is
    # saturated in it, that power_sim's own check gives no estimate, and that the quoted power
    # did not simulate this case
    one = hh.h3_glm_literal(_h3_one_failure())
    h["glm_h3"] = {k: v for k, v in one.items() if not k.startswith("_")}
    h["glm_h3_powersim"] = hh.h3_glm_powersim(_h3_one_failure())
    h["h3"]["model_check"].update(ame=one["ame"], agrees=True,
                                  ame_informative=one["ame_informative"],
                                  n_pairs_informative=one["n_pairs_informative"])
    text = "\n".join(hh.summary_lines(h))
    assert "With one, the model is saturated in it, so its AME is the observed Δ_H3" in text
    assert "`ps.h3_glm_ame`), which the simulation used, needs two templates" in text
    assert "own H3 check gives no estimate" in text
    assert "may overstate" not in text


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
    assert meta["seeds"] == {"bootstrap": SEED + 10, "bayesian_glmm": SEED + 11}
    assert meta["exit_reason"] == "completed" and meta["config"]["h1_separation_rule"] == "firth"
    assert "git_commit" in meta and len(meta["runs"]) == 6
    for needle in ("## What it does not show", "Not a model comparison", "**Δ_H1 = ",
                   "Holm", "Bayesian GLMM sensitivity (§9.1): not run", "## Repeats",
                   "§2.8 accounting check: passed on 160 window-cell episodes",
                   "W-n-0 as a third harness level", "Logit scale (§9.3): Penalty_NR",
                   "The rule in force is `firth`",
                   "**Changed after the FINAL output of 2026-10-10 was read**",
                   "a Firth-penalized fit of the same model decides: ",
                   "- Sensitivity lines (the rules not in force, ruling of 2026-10-10",
                   "is read by the rule in force (`firth`)", "the arm coefficient",
                   "power_sim's model (template fixed effects + derived term + arm)",
                   "reading 11 (as implemented, not registered)",
                   "## Success by cell (repeat 0; descriptive)", "with no dated snapshot",
                   "(the runs named with --run)"):
        assert needle in text, needle


def test_model_string_split_and_achieved_power(tmp_path):
    sw = Sweep(tmp_path)
    for tc in (ONR, OR):
        sw.fields("W-0", tc, 0, echo={"context_requested": "current_turn",
                                      "context_echoed": {"current_turn": 12},
                                      "effort_requested": "medium",
                                      "effort_echoed": {"medium": 12},
                                      "models_returned": {"gpt-6-luna-2026-10-20": 12}})
    sw.fields("F-0", ONR, 1, echo={"context_requested": "current_turn",
                                   "context_echoed": {"current_turn": 12},
                                   "effort_requested": "medium", "effort_echoed": {"medium": 12},
                                   "models_returned": {"gpt-6-luna": 6,
                                                       "gpt-6-luna-2026-10-20": 6}})
    sw.standard()
    h = sw.compute()
    ms = h["model_strings"]
    assert set(ms["strings"]) == {"gpt-6-luna", "gpt-6-luna-2026-10-20",
                                  "gpt-6-luna|gpt-6-luna-2026-10-20"}
    assert ms["records_with_more_than_one_string"] == 1
    # one group per single string, and the mixed record as a group of its own (reading 12)
    assert ms["split"]["gpt-6-luna-2026-10-20"]["episodes"] == 2
    assert ms["split"][hh.MIXED]["episodes"] == 1
    main = ms["split"]["gpt-6-luna"]
    assert main["episodes"] == h["primary_episodes"] - 3
    assert main["delta_h1"]["ci90"] is not None and main["delta_h3"]["ci90"] is not None
    power = {p["scenario"]: p for p in h["achieved_power"]}
    assert power["primary"]["T_set"] == 200
    assert (power["primary"]["power_h1"], power["primary"]["power_h3"]) == (0.647, 0.781)
    assert (power["pessimistic"]["power_h1"], power["pessimistic"]["power_h3"]) == (0.4375,
                                                                                    0.443)
    assert (power["primary"]["p_f0_observed_far"], power["pessimistic"]["p_f0_observed_far"]) \
        == (0.95, 0.85)
    text = "\n".join(hh.summary_lines(h))
    for needle in ("Achieved power at T = 200", "pessimistic: H1 0.438, H3 0.443",
                   "F-0 observed-far success at 0.95 (primary) and 0.85 (pessimistic)",
                   "a dated snapshot among the strings returned", "| `more than one string` | 1 |"):
        assert needle in text, needle


# --- the Bayesian sensitivity model (§9.1) -------------------------------------------------------

def test_bayesian_glmm_fits_the_9_1_design():
    """A real, small bambi fit (the fixture stubs it elsewhere): the W-0 x R posterior with its
    diagnostics, on the §9.1 GLM's rows, every template kept, with the seed given."""
    df = _random_sweep(templates=12, seed=5)
    out = BAYES_REAL(df, SEED + 11, {"chains": 2, "draws": 150, "tune": 150})
    assert out["status"] == "fitted", out.get("note")
    assert out["n_rows"] == 12 * 2 * 8 and out["n_templates"] == 12
    assert out["seed"] == SEED + 11 and out["model"] == hh.BAYES_FORMULA
    assert out["ci90"][0] < out["median"] < out["ci90"][1]
    assert out["ci95"][0] <= out["ci90"][0] and 0 <= out["p_positive"] <= 1
    assert out["rhat"] > 0 and out["ess_bulk"] > 0 and isinstance(out["converged"], bool)
    assert isinstance(out["divergences"], int) and out["divergences"] >= 0
    assert set(out["versions"]) == {"bambi", "pymc", "arviz"}
    # no outcome variation: nothing to fit
    flat = df.assign(success=1)
    assert BAYES_REAL(flat, 1, {"chains": 1, "draws": 10, "tune": 10})["status"] == "not run"


def test_skipping_the_bayesian_fit_is_provisional(tmp_path, monkeypatch, capsys):
    sw = Sweep(tmp_path)
    sw.standard()
    h = sw.compute(bayes=False)
    assert h["status"] == hh.PROVISIONAL and h["bayesian_glmm"]["status"] == "not run"
    assert any("--no-bayes" in x for x in h["provisional_reasons"])
    assert sw.main("--no-write", "--no-bayes", monkeypatch=monkeypatch) == 0
    assert "**Status: PROVISIONAL.**" in capsys.readouterr().out


# --- H1's model check when the logit-scale Delta_H1 is not finite (ruled item 1: Firth) ----------

def _h1_frame(templates: int, given: dict, seed: int = 0) -> pd.DataFrame:
    """F-0 and W-0 on the 8 task cells: H1's cells from `given` ({(cell, task cell): outcomes}),
    every other cell drawn at 0.7, so templates keep their outcome variation."""
    rng = np.random.default_rng(seed)
    rows = []
    for t in range(templates):
        for cell in ("F-0", "W-0"):
            for tc in hh.TASK_CELLS:
                fact, rec_word, dist = tc.split("-")
                v = given.get((cell, tc))
                rows.append({"cell": cell, "variant": BASE, "task_cell": tc, "fact": fact,
                             "recoverable": rec_word == "rec", "distance": dist, "template": t,
                             "success": int(v[t]) if v is not None else int(rng.random() < 0.7)})
    return pd.DataFrame(rows)


def _spread(k: int, n: int, seed: int) -> list[int]:
    """k ones among n, at random places."""
    out = np.zeros(n, int)
    out[np.random.default_rng(seed).choice(n, k, replace=False)] = 1
    return out.tolist()


def test_h1_model_check_rules_when_f0_recoverable_is_at_its_ceiling():
    """F-0 observed-rec-far all 1 and a large positive Delta_H1 (0.9 - 0.1 - (1 - 0.9) = 0.7):
    the logit-scale Delta_H1 is -inf, so the literal rule does not agree; the Firth and the
    probability-scale rules do."""
    n = 40
    df = _h1_frame(n, {("F-0", ONR): _spread(36, n, 1), ("W-0", ONR): _spread(4, n, 2),
                       ("F-0", OR): [1] * n, ("W-0", OR): _spread(36, n, 3)})
    g = hh.glm_91(df)
    assert g["logit_status"] == hh.MINUS_INF and g["estimate"] < -5     # the stopping point
    assert g["h1_cells_no_variation"] == [f"F-0 {OR}: all 1 ({n} episodes)"]
    delta = Fraction(7, 10)
    lit = hh.h1_model_check(g, delta, "literal")
    assert lit["agrees"] is False and lit["sign"] == -1
    firth = hh.glm_91_firth(df)
    assert firth["estimate"] is not None and 0 < firth["estimate"] < 10
    fm = hh.h1_model_check(g, delta, "firth", firth)
    assert fm["agrees"] is True and fm["firth_estimate"] == firth["estimate"]
    assert hh.h1_model_check(g, delta, firth=firth) == fm   # Firth's is the default (ruling)
    # without a Firth fit (none given, or it did not converge) the Firth rule does not agree
    none = hh.h1_model_check(g, delta, "firth", {"estimate": None, "note": "no"})
    assert none["agrees"] is False and none["sign"] is None
    pm = hh.h1_model_check(g, delta, "probability-scale")
    assert pm["agrees"] is True and pm["sign"] is None
    with pytest.raises(ValueError, match="unknown H1 separation rule"):
        hh.h1_model_check(g, delta, "lenient")


def test_h1_logit_status_plus_inf_and_undefined():
    n = 40
    # W-0 observed-nonrec-far all 0: +inf, which agrees under the literal rule
    df = _h1_frame(n, {("F-0", ONR): _spread(36, n, 1), ("W-0", ONR): [0] * n,
                       ("F-0", OR): _spread(36, n, 4), ("W-0", OR): _spread(30, n, 3)})
    g = hh.glm_91(df)
    assert g["logit_status"] == hh.PLUS_INF and g["estimate"] > 0
    assert hh.h1_model_check(g, Fraction(1, 2), "literal")["agrees"] is True
    # F-0 all 1 in both observed-far cells: inf - inf, an undefined sign, which never agrees
    df = _h1_frame(n, {("F-0", ONR): [1] * n, ("W-0", ONR): _spread(4, n, 2),
                       ("F-0", OR): [1] * n, ("W-0", OR): _spread(36, n, 3)})
    g = hh.glm_91(df)
    assert g["logit_status"] == hh.UNDEFINED
    lit = hh.h1_model_check(g, Fraction(7, 10), "literal")
    assert lit["agrees"] is False and lit["sign"] is None
    # with every H1 cell varying, the estimate's own sign decides, whatever the rule
    g = hh.glm_91(_random_sweep())
    for rule in hh.H1_SEPARATION_RULES:
        mc = hh.h1_model_check(g, Fraction(1, 5), rule)
        assert mc["agrees"] is (g["estimate"] > 0) and mc["basis"].startswith("the §9.1 GLM")


def test_the_rule_in_force_decides_supported_on_the_toy_sweep(tmp_path, monkeypatch):
    """The toy sweep's F-0 observed-rec-far is 10/10 and its Holm test rejects: H1 is supported
    under the rule in force (Firth's, the researcher's ruling of 2026-10-10) and under the
    probability-scale rule, and inconclusive under the literal rule. The rules not in force are
    reported as sensitivity lines (the ruling), which change no decision."""
    assert hh.H1_SEPARATION_RULE == "firth"               # the ruling, by commit
    sw = toy(tmp_path)
    sw.standard()
    h = sw.compute()
    assert h["h1_separation_rule"] == "firth" and h["h1"]["model_check"]["rule"] == "firth"
    fe = h["glm_9_1_firth"]["estimate"]
    assert fe > 0 and h["h1"]["model_check"]["firth_estimate"] == fe
    assert h["family"]["H1"]["holm_rejects"] and h["family"]["H1"]["model_agrees"]
    assert h["family"]["H1"]["supported"] and h["family"]["H1"]["verdict"] == "supported"
    sens = h["h1"]["model_check_sensitivity"]
    assert set(sens) == {"literal", "probability-scale"}
    assert sens["literal"]["agrees"] is False and sens["literal"]["sign"] == -1
    assert sens["probability-scale"]["agrees"] is True
    assert h["family"]["H1"]["sensitivity_rules"] == {
        "literal": {"model_agrees": False, "supported": False, "verdict": hh.MODEL_DISAGREES},
        "probability-scale": {"model_agrees": True, "supported": True, "verdict": "supported"}}
    text = "\n".join(hh.summary_lines(h))
    assert "The rule in force is `firth`" in text
    assert ("- Sensitivity lines (the rules not in force, ruling of 2026-10-10; they enter no "
            "decision): rule `literal`: the model check would agree: no, and H1 would be: "
            f"{hh.MODEL_DISAGREES}; rule `probability-scale`: the model check would agree: yes, "
            "and H1 would be: supported.") in text
    monkeypatch.setattr(hh, "H1_SEPARATION_RULE", "literal")
    h = sw.compute()
    assert h["h1_separation_rule"] == "literal" and h["h1"]["model_check"]["rule"] == "literal"
    assert h["family"]["H1"]["holm_rejects"] and not h["family"]["H1"]["supported"]
    assert h["family"]["H1"]["verdict"] == hh.MODEL_DISAGREES
    # the Firth fit is made whenever the logit-scale Delta_H1 is not finite: here its
    # sensitivity line reads it
    assert h["glm_9_1_firth"]["estimate"] == fe
    assert set(h["h1"]["model_check_sensitivity"]) == {"firth", "probability-scale"}
    assert h["h1"]["model_check_sensitivity"]["firth"]["firth_estimate"] == fe
    assert h["family"]["H1"]["sensitivity_rules"]["firth"]["verdict"] == "supported"
    text = "\n".join(hh.summary_lines(h))
    assert "The rule in force is `literal`" in text and "rule `firth` (Firth's W-0 × R " in text
    monkeypatch.setattr(hh, "H1_SEPARATION_RULE", "probability-scale")
    h = sw.compute()
    assert h["h1"]["model_check"]["rule"] == "probability-scale"
    assert h["family"]["H1"]["supported"] and h["family"]["H1"]["verdict"] == "supported"
    assert set(h["family"]["H1"]["sensitivity_rules"]) == {"literal", "firth"}
    assert "The rule in force is `probability-scale`" in "\n".join(hh.summary_lines(h))


def test_no_firth_fit_and_no_sensitivity_lines_when_delta_h1_is_finite(tmp_path):
    """With every H1 cell varying (the toy sweep with F-0 observed-rec-far at 9/10) the
    ordinary fit decides under every rule: no Firth fit, no sensitivity line."""
    sw = toy(tmp_path)
    sw.outcome("F-0", OR, [0] + [1] * 9)
    sw.standard()
    h = sw.compute()
    mc = h["h1"]["model_check"]
    assert mc["logit_status"] == hh.FINITE and mc["basis"] == "the §9.1 GLM's W-0 x R coefficient"
    assert h["glm_9_1_firth"] is None and h["h1"]["model_check_sensitivity"] == {}
    assert h["family"]["H1"]["sensitivity_rules"] == {}
    assert "Sensitivity lines" not in "\n".join(hh.summary_lines(h))
    g = hh.glm_91(_random_sweep())
    assert all(hh.h1_rule_sensitivity(g, Fraction(1, 5), rule) == {}
               for rule in hh.H1_SEPARATION_RULES)


def test_firth_is_add_a_half_on_a_saturated_model():
    """On a saturated model Firth's estimate is the logit of (successes + 1/2) / (n + 1) in each
    cell (Firth 1993), finite even for a cell at 10/10."""
    cells = {(0, 0): (9, 10), (1, 0): (1, 10), (0, 1): (10, 10), (1, 1): (8, 10)}
    y, w, r = [], [], []
    for (wi, ri), (s, n) in cells.items():
        y += [1] * s + [0] * (n - s)
        w += [wi] * n
        r += [ri] * n
    y, w, r = (np.array(v, float) for v in (y, w, r))
    alpha, beta = hh.firth_fe_logit(y, np.zeros(len(y), int), np.column_stack([w, r, w * r]))
    lg = {k: np.log((s + 0.5) / (n - s + 0.5)) for k, (s, n) in cells.items()}
    assert alpha[0] == pytest.approx(lg[(0, 0)], abs=1e-6)
    assert beta[0] == pytest.approx(lg[(1, 0)] - lg[(0, 0)], abs=1e-6)
    assert beta[1] == pytest.approx(lg[(0, 1)] - lg[(0, 0)], abs=1e-6)
    assert beta[2] == pytest.approx(lg[(1, 1)] - lg[(1, 0)] - lg[(0, 1)] + lg[(0, 0)], abs=1e-6)


# --- an independent check of firth_fe_logit ------------------------------------------------------

def _minus_penalized(b: np.ndarray, x: np.ndarray, y: np.ndarray) -> float:
    """Minus Firth's penalized log-likelihood, -(l(b) + 1/2 log det X'WX), written afresh: l as
    sum(y eta - log(1 + e^eta)) and the determinant by slogdet (firth_fe_logit uses neither)."""
    eta = x @ b
    p = 1.0 / (1.0 + np.exp(-eta))
    sign, logdet = np.linalg.slogdet(x.T @ (x * (p * (1.0 - p))[:, None]))
    assert sign > 0
    return -(float(np.sum(y * eta - np.logaddexp(0.0, eta))) + 0.5 * logdet)


def _num_grad(f, b: np.ndarray, h: float = 1e-5) -> np.ndarray:
    e = np.eye(len(b)) * h
    return np.array([(f(b + e[j]) - f(b - e[j])) / (2 * h) for j in range(len(b))])


def _num_hess(f, b: np.ndarray, h: float = 1e-4) -> np.ndarray:
    k, e = len(b), np.eye(len(b)) * h
    out = np.empty((k, k))
    for i in range(k):
        for j in range(i, k):
            out[i, j] = out[j, i] = (f(b + e[i] + e[j]) - f(b + e[i] - e[j])
                                     - f(b - e[i] + e[j]) + f(b - e[i] - e[j])) / (4 * h * h)
    return out


def _firth_direct(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Firth's estimate found by maximising the penalized log-likelihood directly, with no part
    of firth_fe_logit (no modified score, hat values or Cholesky factor): L-BFGS from 0 on
    central-difference gradients, then Newton steps on central-difference gradients and
    Hessians to settle the last digits (L-BFGS alone stops near 1e-7)."""
    def f(b):
        return _minus_penalized(b, x, y)
    res = optimize.minimize(f, np.zeros(x.shape[1]), jac=lambda b: _num_grad(f, b),
                            method="L-BFGS-B",
                            options={"maxiter": 5000, "gtol": 1e-10, "ftol": 1e-15})
    b = res.x
    for _ in range(3):
        b = b - np.linalg.solve(_num_hess(f, b), _num_grad(f, b))
    return b


def _firth_case(templates: int, reps: int, eight_cells: bool, separated: bool, seed: int):
    """y, template codes and slopes for F-0/W-0 x R (x D x N with `eight_cells`), `reps`
    episodes per template and cell, drawn from a logit with template effects; with `separated`,
    F-0's recoverable (observed, far) cell is all 1 in every template, as at F-0's ceiling, so
    the maximum-likelihood W-0 x R coefficient is -inf."""
    rng = np.random.default_rng(seed)
    u = rng.normal(0, 0.7, templates)
    rows = []
    for t in range(templates):
        for w in (0, 1):
            for r in (0, 1):
                for d, n in ((0, 0), (0, 1), (1, 0), (1, 1)) if eight_cells else ((0, 0),):
                    eta = 0.8 + u[t] - 1.2 * w + 0.4 * r - 0.3 * d + 0.3 * n + 1.0 * w * r
                    for _ in range(reps):
                        f0_r = (w, r, d, n) == (0, 1, 0, 0)
                        y = 1 if separated and f0_r else int(rng.random() < 1 / (1 + np.exp(-eta)))
                        rows.append((y, t, w, r, d, n, f0_r))
    y, codes, w, r, d, n, f0_r = (np.array(c, float) for c in zip(*rows, strict=True))
    if eight_cells:
        z, names = hh.factorial_design({"W-0": w}, r, d, n, target="W-0:R")
    else:
        z, names = np.column_stack([w, r, w * r]), ["W-0", "R", "W-0:R"]
    assert names[-1] == "W-0:R"
    return y, codes.astype(int), z, f0_r.astype(bool)


FIRTH_CASES = {"4 cells": (4, 6, False, False, 1), "4 cells, separated": (4, 6, False, True, 2),
               "8 cells": (3, 5, True, False, 3), "8 cells, separated": (3, 5, True, True, 4)}


@pytest.mark.parametrize("case", FIRTH_CASES)
def test_firth_fe_logit_matches_a_direct_maximisation(case):
    """firth_fe_logit's Newton fit equals a direct numerical maximisation of l(b) + 1/2 log
    det(X'WX) on every coefficient, with and without separation; and its estimate is a
    stationary point and a maximum of the penalized log-likelihood (numerical derivatives)."""
    y, codes, z, f0_r = _firth_case(*FIRTH_CASES[case])
    keep, _, _ = hh.informative(y, codes)
    assert keep.all()                                   # every template has outcome variation
    fit = hh.firth_fe_logit(y, codes, z)
    assert fit is not None
    ours = np.concatenate(fit)
    x = np.column_stack([np.eye(codes.max() + 1)[codes], z])
    direct = _firth_direct(y, x)
    np.testing.assert_allclose(ours, direct, rtol=0, atol=1e-7)
    assert abs(ours[-1] - direct[-1]) < 1e-7            # the W-0 x R coefficient
    def f(b):
        return _minus_penalized(b, x, y)
    assert np.max(np.abs(_num_grad(f, ours))) < 1e-6
    assert np.linalg.eigvalsh(_num_hess(f, ours)).min() > 0
    if "separated" in case:
        # F-0's recoverable cell is all 1, so the ML W-0 x R coefficient is -inf; Firth's is
        # finite and moderate
        assert f0_r.any() and y[f0_r].min() == 1
        assert hh.logit_status(pd.DataFrame({"success": y}),
                               [("F-0 R", pd.Series(f0_r), -1)])["status"] == hh.MINUS_INF
        assert np.isfinite(ours).all() and abs(ours[-1]) < 10


def test_glm_91_firth_matches_a_direct_maximisation_on_the_formula_design():
    """glm_91_firth (the rows, the template dropping and the §9.1 design) against the direct
    maximisation on statsmodels' formula design of success ~ C(template) + W*R*D*N, on the
    templates with outcome variation. Firth's estimate is equivariant under a change of basis of
    the template columns, so the W:R coefficients must agree; F-0 observed-rec-far is all 1."""
    n = 8
    df = _h1_frame(n, {("F-0", OR): [1] * n}, seed=5)
    assert hh.glm_91(df)["logit_status"] == hh.MINUS_INF
    ours = hh.glm_91_firth(df)
    assert ours["note"] is None
    varies = df.groupby("template")["success"].transform("nunique") > 1
    d = df[varies].assign(W=lambda x: (x.cell == "W-0").astype(float),
                          R=lambda x: x.recoverable.astype(float),
                          D=lambda x: (x.fact == "derived").astype(float),
                          N=lambda x: (x.distance == "near").astype(float))
    model = smf.glm("success ~ C(template) + W*R*D*N", d, family=sm.families.Binomial())
    direct = _firth_direct(d["success"].to_numpy(float), np.asarray(model.exog))
    assert ours["estimate"] == pytest.approx(direct[model.exog_names.index("W:R")], abs=1e-7)


def test_firth_approaches_ml_as_n_grows():
    """Without separation Firth's estimate differs from the ML estimate by O(1/n) (Firth 1993):
    with the same success shares and k times the episodes, k (Firth - ML) settles to a
    constant, and at 1,000 episodes a cell the two are within 0.002."""
    shares = {0: [(7, 10), (3, 10), (8, 10), (6, 10)], 1: [(5, 10), (2, 10), (7, 10), (4, 10)],
              2: [(9, 10), (4, 10), (9, 10), (8, 10)]}           # (w, r) = 00, 10, 01, 11
    diffs = {}
    for k in (1, 10, 100):
        y, codes, w, r = [], [], [], []
        for t, cells in shares.items():
            for (wi, ri), (s, m) in zip(((0, 0), (1, 0), (0, 1), (1, 1)), cells, strict=True):
                y += [1.0] * (s * k) + [0.0] * ((m - s) * k)
                codes += [t] * (m * k)
                w += [wi] * (m * k)
                r += [ri] * (m * k)
        w, r = np.array(w, float), np.array(r, float)
        z = np.column_stack([w, r, w * r])
        alpha, beta = hh.firth_fe_logit(np.array(y), np.array(codes), z)
        x = np.column_stack([np.eye(3)[codes], z])
        ml = sm.GLM(np.array(y), x, family=sm.families.Binomial()).fit(tol=1e-12)
        diffs[k] = np.concatenate([alpha, beta]) - np.asarray(ml.params)
    assert np.abs(diffs[1]).max() > np.abs(diffs[10]).max() > np.abs(diffs[100]).max()
    assert np.abs(diffs[100]).max() < 0.002
    np.testing.assert_allclose(10 * diffs[10], 100 * diffs[100], rtol=0.05, atol=1e-3)


def _ceiling_case(templates: int = 200, seed: int = 0):
    """y, template codes and the §9.1 design (F-0/W-0 x R x D x N, one episode per template and
    cell), shaped like a sweep at its ceiling: every cell is all 1 except W-0's
    not-recoverable far cells (about 7.5% success) and one failure each in F-0
    derived-nonrec-far and W-0 derived-nonrec-near. Only the templates with outcome variation
    are kept, as glm_91_firth keeps them."""
    rng = np.random.default_rng(seed)
    rows = np.array([(t, w, r, d, n) for t in range(templates) for w in (0, 1) for r in (0, 1)
                     for d in (0, 1) for n in (0, 1)], float)
    _, w, r, d, n = rows.T
    y = np.ones(len(rows))
    lost = (w == 1) & (r == 0) & (n == 0)
    y[lost] = (rng.random(int(lost.sum())) > 0.925).astype(float)
    for one in ((w == 0) & (r == 0) & (d == 1) & (n == 0),
                (w == 1) & (r == 0) & (d == 1) & (n == 1)):
        y[rng.choice(np.flatnonzero(one))] = 0.0
    z, names = hh.factorial_design({"W-0": w}, r, d, n, target="W-0:R")
    assert names[-1] == "W-0:R"
    keep, codes, _ = hh.informative(y, rows[:, 0].astype(int))
    return y[keep], codes, z[keep]


def test_firth_converges_on_a_sweep_at_its_ceiling():
    """The fit's steps converge linearly, and on a sweep with most cells at 100% (luna's shape)
    they can need more than 100 steps: this seed's case needs 108, so the old cap of 100 returns
    None ("did not converge") here, as it did on luna's sweep (103 steps). Under the cap of
    1,000 the fit converges, to a stationary point of the penalized log-likelihood written
    afresh (numerical gradient) that no direction tried increases."""
    y, codes, z = _ceiling_case()
    assert hh.firth_fe_logit(y, codes, z, max_iter=100) is None
    fit = hh.firth_fe_logit(y, codes, z)
    assert fit is not None
    b = np.concatenate(fit)
    assert np.isfinite(b).all() and 0 < b[-1] < 15                 # W-0 x R: finite, positive
    x = np.column_stack([np.eye(codes.max() + 1)[codes], z])
    def f(v):
        return _minus_penalized(v, x, y)
    assert np.max(np.abs(_num_grad(f, b))) < 1e-5
    rng = np.random.default_rng(1)
    for _ in range(20):
        u = rng.normal(size=len(b))
        assert f(b + 1e-3 * u / np.linalg.norm(u)) > f(b)


# --- H3's model check: the registered model decides (B1) ----------------------------------------

def _h3_frame(templates: int = 60, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    u = rng.normal(0, 0.8, templates)
    rows = []
    for t in range(templates):
        for cell in ("F-0", ST):
            for tc in (ONR, DNR):
                fact, _, dist = tc.split("-")
                eta = 1.4 + u[t] + 0.3 * (cell == ST) - 0.5 * (fact == "derived")
                rows.append({"cell": cell, "variant": BASE, "task_cell": tc, "fact": fact,
                             "recoverable": False, "distance": dist, "template": t,
                             "success": int(rng.random() < 1 / (1 + np.exp(-eta)))})
    return pd.DataFrame(rows)


def test_h3_model_check_is_the_registered_model():
    df = _h3_frame()
    lit = hh.h3_glm_literal(df)
    assert lit["coefficients"].keys() == {"arm"} and lit["logit_status"] == hh.FINITE
    # statsmodels' formula fit of template FE + arm on the informative templates
    keep, _, _ = hh.informative(df.success.to_numpy(float), df.template.to_numpy())
    d = df[keep].assign(arm=lambda x: (x.cell == ST).astype(float))
    fit = smf.glm("success ~ C(template) + arm", d, family=sm.families.Binomial()).fit()
    assert lit["estimate"] == pytest.approx(fit.params["arm"], abs=1e-6)
    # the AME over every (template, task cell) pair, a template without variation adding 0
    pairs = df[["template", "task_cell"]].drop_duplicates()
    fitted = pairs[pairs.template.isin(set(d.template))]
    eff = (fit.predict(fitted.assign(arm=1.0)) - fit.predict(fitted.assign(arm=0.0))).sum()
    assert lit["ame"] == pytest.approx(eff / len(pairs), abs=1e-6)
    assert lit["ame_informative"] == pytest.approx(eff / len(fitted), abs=1e-6)
    assert lit["n_pairs"] == len(pairs) and lit["n_pairs_informative"] == len(fitted)
    # h3_reading: the registered model decides; power_sim's is reported, and a disagreement
    # about the 5pp bound is flagged
    an = hh.Analysis(df, 60, hh.resample_indices(60, 1, 200))
    r = hh.h3_reading(an, {"ame": 0.07, "estimate": 0.5, "model": "registered"},
                      {"ame": 0.01, "model": "power_sim's"})
    mc = r["model_check"]
    assert mc["agrees"] is False and mc["powersim_agrees"] is True and mc["powersim_disagrees"]
    ps_model = hh.h3_glm_powersim(df)
    assert ps_model["ame"] is not None and ps_model["arm_logit"] is not None


def _h3_one_failure(templates: int = 200, failing: int = 145) -> pd.DataFrame:
    """H3's cells at the ceiling, as on luna's sweep: every episode succeeds except F-0's
    derived-nonrec-far episode of template `failing`."""
    rows = []
    for t in range(templates):
        for cell in ("F-0", ST):
            for tc in (ONR, DNR):
                fact, _, dist = tc.split("-")
                rows.append({"cell": cell, "variant": BASE, "task_cell": tc, "fact": fact,
                             "recoverable": False, "distance": dist, "template": t,
                             "success": int(not (cell == "F-0" and tc == DNR
                                                 and t == failing))})
    return pd.DataFrame(rows)


def test_h3_model_check_with_one_template_with_outcome_variation():
    """One template with outcome variation is enough for the model's point estimate (changed
    B, 2026-10-10; it used to need two, and H3's check then had no estimate). The arm's logit
    runs off to +inf (statsmodels' stopping point), and the AME is that template's two pairs'
    effect over all 2T pairs: 1/(2T), the observed Delta_H3. The Wald quantities need two
    templates and are absent. With no template varying there is no fit, and the AME is 0."""
    df = _h3_one_failure()
    lit = hh.h3_glm_literal(df)
    assert lit["n_templates_informative"] == 1 and lit["n_pairs_informative"] == 2
    assert lit["logit_status"] == hh.PLUS_INF and lit["estimate"] > 10
    assert lit["se"] is None and "point estimates only" in lit["note"]
    assert lit["ame"] == pytest.approx(1 / 400, abs=1e-7)
    assert lit["ame_informative"] == pytest.approx(0.5, abs=1e-7)
    ps_model = hh.h3_glm_powersim(df)
    assert ps_model["n_templates_informative"] == 1
    assert ps_model["ame"] == pytest.approx(1 / 400, abs=1e-7)
    an = hh.Analysis(df, 200, hh.resample_indices(200, 1, 200))
    mc = hh.h3_reading(an, lit, ps_model)["model_check"]
    assert mc["agrees"] is True and mc["powersim_agrees"] is True
    assert mc["n_pairs_informative"] == 2
    flat = df.assign(success=1)
    lit0 = hh.h3_glm_literal(flat)
    assert lit0["coefficients"] is None and lit0["ame"] == 0.0
    assert lit0["n_pairs_informative"] == 0
    assert lit0["note"] == "no template with outcome variation: no fit"
    assert hh.h3_glm_powersim(flat)["ame"] == 0.0


def test_emulate_reports_the_route_power_sims_fit_took():
    """power_sim's emulation (`ps._fe_logit_mle`) falls back to statsmodels when its Newton
    steps fail, as on a sweep at its ceiling; `emulate` returns the same fit and says which
    route gave it (changed C, 2026-10-10)."""
    y, codes, z, _ = _firth_case(*FIRTH_CASES["8 cells"])
    fit, route = hh.emulate(y, codes, z)
    assert route == "newton"
    np.testing.assert_array_equal(fit[1], ps._fe_logit_mle(y, codes, z)[1])
    y, codes, z = _ceiling_case()
    fit, route = hh.emulate(y, codes, z)
    assert route == "statsmodels"
    np.testing.assert_array_equal(fit[1], ps._fe_logit_mle(y, codes, z)[1])


def test_h3_verdict_when_the_ci_lies_above_the_bound():
    assert hh.h3_verdict(False, 0.15).startswith("not supported: the whole 90% CI")
    assert hh.h3_verdict(False, 0.05) == "inconclusive"          # on the bound, not above it
    assert hh.h3_verdict(False, 0.05 + 1e-12) == "inconclusive"
    assert hh.h3_verdict(False, -0.2, holm_rejects=True) == hh.MODEL_DISAGREES
    assert hh.h3_verdict(True, 0.2) == "supported"
    h1 = {"p_one_sided": 0.5, "model_check": {"agrees": True}, "kill": False}
    h3 = {"p_one_sided": 1.0, "model_check": {"agrees": False},
          "delta_h3": {"ci90": [0.15, 0.25]}}
    assert hh.family_readings(h1, h3)["H3"]["verdict"].startswith("not supported")
    assert hh.h1_verdict(False, False) == "inconclusive"
    assert hh.h1_verdict(False, False, holm_rejects=True) == hh.MODEL_DISAGREES


# --- a closed sweep (DESIGN §7.8) and the input list -------------------------------------------

def test_a_closed_sweep_excludes_keys_without_a_final_record(tmp_path):
    sw = Sweep(tmp_path)
    recs = sw.records("W-n-0", templates=range(T - 2))       # templates 8 and 9 never played
    for r in recs:
        if r["template_id"] == "main-000007":
            r["exit_reason"] = "COST_CAP"
    sw.standard(skip={("W-n-0", BASE)})
    sw.run("W-n-0", records=recs)
    with pytest.raises(hh.Refusal, match="pending"):
        sw.compute()
    h = sw.compute(sweep_closed="decisions.md 2026-10-12")
    assert h["status"] == hh.FINAL and h["sweep_closed"] == "decisions.md 2026-10-12"
    row = next(e for e in h["exclusions"] if e["kind"] == "W-n-0" and e["task_cell"] == ONR)
    assert (row["keys"], row["never_played"], row["excluded_no_final"]) == (T - 2, 2, 1)
    assert any("never played" in d for d in h["deviations"])
    assert any("last endings: COST_CAP 8" in d for d in h["deviations"])
    assert h["h1"]["cells"]["W-n-0 NR"]["n"] == T - 3
    text = "\n".join(hh.summary_lines(h))
    assert "## Deviations (§13" in text and "decisions.md 2026-10-12" in text


def test_a_closed_sweep_still_needs_a_transport_failures_rerun(tmp_path):
    sw = Sweep(tmp_path)
    recs = sw.records("F-0")
    recs[5]["exit_reason"] = "API_ERROR"
    sw.standard(skip={("F-0", BASE)})
    sw.run("F-0", records=recs)
    with pytest.raises(hh.Refusal, match="§13 re-runs it once"):
        sw.compute(sweep_closed="decisions.md 2026-10-12")
    # a run kind with no record at all is a missing run, not a closed sweep
    sw2 = Sweep(tmp_path / "b")
    sw2.standard(skip={(ST, BASE)})
    with pytest.raises(hh.Refusal, match="a run is missing"):
        sw2.compute(sweep_closed="decisions.md 2026-10-12")
    with pytest.raises(hh.Refusal, match="needs the results/decisions.md entry"):
        sw2.compute(sweep_closed=" ")


def test_the_input_list(tmp_path, monkeypatch, capsys):
    sw = Sweep(tmp_path)
    sw.standard()
    h = sw.compute(runs=None)
    assert h["status"] == hh.PROVISIONAL
    assert any("no input list" in x for x in h["provisional_reasons"])
    assert sw.main("--no-write", monkeypatch=monkeypatch, named=False) == 0
    assert "**Status: PROVISIONAL.**" in capsys.readouterr().out
    with pytest.raises(hh.Refusal, match="--run names run"):
        sw.compute(runs=[*sw.ids, "20261010T235900Z-F-0-gpt-6-luna"])
    # a run left out of the list is skipped, visibly; read, it would be an undeclared duplicate
    named = list(sw.ids)
    extra = sw.run("F-0", records=sw.records("F-0", templates=[0]))
    h = sw.compute(runs=named)
    assert h["status"] == hh.FINAL
    assert {"folder": extra, "reason": "a gpt-6-luna sweep run not in the input list (--run)"} \
        in h["inputs"]["skipped"]
    assert any("not in the input list" in w for w in h["warnings"])
    with pytest.raises(hh.Refusal, match="not declared"):
        sw.compute()


# --- unreadable records, missing values and the bootstrap cache ---------------------------------

def test_unreadable_records_refuse(tmp_path, monkeypatch, capsys):
    sw = Sweep(tmp_path)
    ids = sw.standard()
    path = sw.root / "persistgym" / ids[("F-0", BASE)] / "episodes.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + '{"episode_id": "main-0000',
                    encoding="utf-8")
    with pytest.raises(hh.Refusal, match="line 81 is not valid JSON"):
        sw.compute()
    assert sw.main("--no-write", monkeypatch=monkeypatch) == 2
    assert "not valid JSON" in capsys.readouterr().err
    sw2 = Sweep(tmp_path / "b")
    sw2.fields("F-0", ONR, 0, repeat_index=None)
    sw2.standard()
    with pytest.raises(hh.Refusal, match="repeat_index None, not an integer"):
        sw2.compute()


def test_a_complete_need_phase_without_tokens_is_left_out(tmp_path):
    sw = Sweep(tmp_path)
    sw.fields("F-0", OR, 0, need_phase={"complete": True})
    sw.standard()
    h = sw.compute()
    assert h["h1_tokens"]["R_need"]["n"]["F-0 far"] == T - 1
    assert h["h1_tokens"]["R_need"]["episodes_left_out_no_tokens"] == 1
    assert any("without need_phase.tokens" in w for w in h["warnings"])


def test_sample_boot_is_cached_per_resample_set():
    s = hh.Sample(pd.DataFrame({"template": [0, 1], "success": [1, 0]}), 2)
    assert s.boot(np.array([[0, 0]])).tolist() == [1.0]
    assert s.boot(np.array([[1, 1]])).tolist() == [0.0]
    nan = hh.Sample(pd.DataFrame({"template": [0, 1], "need_tokens": [5.0, np.nan]}), 2,
                    "need_tokens")
    assert nan.count == 1 and nan.n_missing == 1 and nan.point() == 5


def test_a_finished_window_episode_without_a_need_payload_is_a_bug(tmp_path):
    sw = Sweep(tmp_path)
    sw.fields("W-0", ONR, 3, need_payload=None)
    sw.standard()
    with pytest.raises(hh.AccountingBug, match="ended DONE with no need_payload"):
        sw.compute()
    sw2 = Sweep(tmp_path / "b")
    sw2.fields("W-0", ONR, 3, need_payload=None, exit_reason="MAX_TURNS")
    sw2.standard()
    h = sw2.compute()
    assert any("never reached their need step" in w and "MAX_TURNS 1" in w
               for w in h["warnings"])


# --- R8: claude-haiku-5-5's replication (PREREG §17.8; "A second model") -------------------------

HAIKU = registered.HAIKU_MODEL
HAIKU_ECHO = {"context_requested": None, "context_echoed": None, "effort_requested": "medium",
              "effort_echoed": None, "models_returned": {HAIKU: 12},
              "service_tiers_returned": {"standard": 12}}
"""An episode's echo record on the Messages wire (runner.episode_echo): nothing echoed."""
HAIKU_USAGE = {"input_tokens": 10_000, "cached_input_tokens": 9_000, "cache_write_tokens": 500,
               "output_tokens": 300, "reasoning_tokens": None}
"""Usage as the runner records it on the Messages wire (pricing.messages_usage_numbers): input
already holds the cache reads and writes; thinking tokens not reported, so null."""


def _keep_seq(reps: list[int], turn: int) -> int:
    """The window start at `turn` with per-turn reply tokens `reps` (dropped turns stay out)."""
    obs = [OBS_TOKENS] * (turn + 1)
    return max(window_keep_start(obs[: j + 1], reps[:j], W_SMALL, SYS_TOKENS)
               for j in range(turn + 1))


def _m(role: str, text: str) -> dict:
    return {"role": role, "content": [{"type": "text", "text": text}]}


def messages_transcript_lines(eid: str, cell: str, reply_tokens: int = 2, turns: int = NEED + 2,
                              silent: dict | None = None):
    """The step requests of one window-cell Haiku episode as the runner's recorder writes them
    on the Messages wire (harnesses/wire.py): `system` and `messages` (text blocks), and a
    response of a thinking block, its text block and `stop_reason`. `silent` ({turn:
    (stop_reason, partial text)}) marks turns with no visible reply as the session keeps it:
    thinking only at end_turn (partial ""), or a refusal, whose partial text is discarded.
    Each went back as the placeholder and counts 0 tokens toward W."""
    silent = silent or {}
    system = _text("System prompt.", SYS_TOKENS)
    if CELLS[cell].notes:
        system += "\n" + NOTES_INSTRUCTION
    reply = _text("ok", reply_tokens)
    reps = [0 if i in silent else reply_tokens for i in range(turns)]
    for i in range(turns):
        keep = _keep_seq(reps, i)
        msgs = []
        for t in range(keep, i):
            msgs += [_m("user", _text(f"Observation {t}.", OBS_TOKENS)),
                     _m("assistant", EMPTY_REPLY_PLACEHOLDER if t in silent else reply)]
        msgs.append(_m("user", _text(f"Observation {i}.", OBS_TOKENS)))
        stop, partial = silent.get(i, ("end_turn", reply))
        content = [{"type": "thinking", "thinking": "", "signature": f"sig-{i}"}]
        if partial:
            content.append({"type": "text", "text": partial})
        yield {"episode_id": eid, "harness_cell": cell, "request_index": i, "kind": "step",
               "turn": i, "pending_step": i, "is_lookup_result": False,
               "info": {"keep_start": keep},
               "payload": {"model": HAIKU, "system": system, "messages": msgs,
                           "max_tokens": 32_000, "thinking": {"type": "adaptive"},
                           "output_config": {"effort": "medium"},
                           "cache_control": {"type": "ephemeral"}},
               "response": {"model": HAIKU, "content": content, "stop_reason": stop,
                            "stop_details": ({"category": "general_harms"}
                                             if stop == "refusal" else None)}}


class HaikuSweep(Sweep):
    """A results root holding a synthetic claude-haiku-5-5 sweep (R8) on templates 0..T-1, in
    experiment persistgym_haiku: records as the runner writes them on the Messages wire (no
    echo; usage in the Responses meanings, reasoning tokens unreported) and Messages
    transcripts."""
    MODEL, EXPERIMENT = HAIKU, registered.HAIKU_EXPERIMENT

    def __init__(self, tmp_path, templates: int = T):
        super().__init__(tmp_path, templates)
        self.silent: dict[tuple[str, str], dict] = {}     # (cell, episode_id): silent turns

    def make_record(self, cell, variant, tc, t, success, repeat=0, **over) -> dict:
        r = record(cell, variant, tc, t, success, repeat)
        r.update(model=HAIKU, echo=dict(HAIKU_ECHO), usage=dict(HAIKU_USAGE))
        r.update(over)
        return r

    def transcript(self, eid, cell, reply_tokens, turns):
        return messages_transcript_lines(eid, cell, reply_tokens, turns,
                                         self.silent.get((cell, eid)))

    def kinds(self):
        return hh.profile(HAIKU).kinds

    def compute(self, **kw):
        kw.setdefault("model", HAIKU)
        return super().compute(**kw)

    def main(self, *args, monkeypatch, named=True):
        monkeypatch.setattr(registered, "HAIKU_T", self.T)
        runs = [x for r in self.ids for x in ("--run", r)] if named else []
        return hh.main(["--model", HAIKU, "--results-root", str(self.root), *runs, *args])


def haiku_toy(tmp_path) -> HaikuSweep:
    """The toy sweep's outcomes and fields (above), played by Haiku, its usage in the Messages
    wire's shape (reasoning tokens unreported)."""
    sw = HaikuSweep(tmp_path)
    luna = toy(tmp_path / "luna")
    sw.success, sw.over = luna.success, luna.over
    for t in range(T):
        for tc in (OR, "observed-rec-near"):
            sw.over[("W-0", BASE, tc, t)]["usage"].update(
                cached_input_tokens=0, cache_write_tokens=0, reasoning_tokens=None)
    return sw


def _json(x) -> str:
    """An output as the module writes it (NaN as null), for exact comparisons."""
    return json.dumps(hh._clean(x), ensure_ascii=False, default=hh._json_default)


def _words(h: dict) -> str:
    """Every label and line of an output: its JSON and its summary."""
    return json.dumps(h, ensure_ascii=False, default=str) + "\n".join(hh.summary_lines(h))


def test_luna_profile_is_the_module_constants():
    """luna's profile is the analysis of its sweep as it was: the module's constants, its 6 run
    kinds in order, the echo checks, Holm, its power run and its output folder."""
    p = hh.profile()
    assert hh.profile(hh.MODEL) == p
    assert (p.model, p.experiment, p.out_name, p.T, p.generator_hash) == (
        "gpt-6-luna", "persistgym", "persistgym_h1h3", registered.LUNA_T,
        registered.LUNA_GENERATOR_HASH)
    assert p.cells == registered.LUNA_CELLS and p.kinds == hh.KINDS and p.not_run == ()
    assert p.echo and not p.replication and p.api == hh.RESPONSES_API
    assert p.power_path == hh.POWER_DECISION
    with pytest.raises(hh.Refusal, match="covers gpt-6-luna"):
        hh.profile("gpt-6.1-sol")


def test_luna_output_keys_are_its_cited_outputs(tmp_path):
    """luna's output has the keys, in order, of its cited output (committed, written by the
    code before the second model): no Haiku field reaches it. The numbers and labels of the
    cited output itself are re-derived from luna's real sweep outside the tests (its raw
    transcripts are gitignored)."""
    cited = json.loads((hh.REPO_ROOT / hh.LUNA_CITED_OUTPUT / "h1h3.json")
                       .read_text(encoding="utf-8"))
    sw = toy(tmp_path)
    sw.standard()
    h = json.loads(json.dumps(hh._clean(sw.compute()), default=hh._json_default))
    assert list(h) == list(cited)
    for key in ("inputs", "bootstrap", "h1", "h1_lookups", "h1_tokens", "h1_predictions", "h3",
                "family", "accounting_check", "model_strings"):
        assert list(h[key]) == list(cited[key]), key
    for key in ("cells", "exclusions", "accounting", "repeats"):
        assert list(h[key][0]) == list(cited[key][0]), key
    assert list(h["h1"]["model_check"]) == list(cited["h1"]["model_check"])
    assert list(h["family"]["H1"]) == list(cited["family"]["H1"])
    assert _json(sw.compute(model=hh.MODEL)) == _json(sw.compute())


def test_lunas_null_reasoning_count_reads_as_before(tmp_path):
    """On luna's wire a null reasoning count is 0, as before the second model: the rule that a
    null count is missing (R8) is the Messages wire's only, so luna's cost outcomes keep no
    missing count and no unavailable cell. On Haiku's wire the same record's count is
    missing."""
    sw = Sweep(tmp_path)
    sw.fields("F-0", OR, 0, usage={"input_tokens": 10_000, "output_tokens": 300,
                                   "reasoning_tokens": None})
    sw.standard()
    h = sw.compute()
    row = next(r for r in h["cost_outcomes"]
               if r["task_cell"] == OR and r["outcome"] == "reasoning_tokens")
    assert row["means"]["F-0"] == 90.0                       # (0 + 9 x 100) / 10
    assert "unavailable" not in row and "n_missing" not in row
    assert set(row["ratios"]) == {"W-0", "W-n-0", "Σ-n-0"}
    r = hh.Resolved(key=("F-0", "e", 0), status="counted", run_id="x", reason=None,
                    record=record("F-0", BASE, OR, 0, 1, usage={"reasoning_tokens": None}))
    assert hh.episode_row(r)["reasoning_tokens"] == 0.0
    assert np.isnan(hh.episode_row(r, hh.MESSAGES_API)["reasoning_tokens"])
    assert hh.episode_row(r, hh.MESSAGES_API)["tiers"] == (("flex", 12),)


def test_haiku_profile_reads_r8s_registered_values(monkeypatch):
    p = hh.profile(HAIKU)
    assert (p.model, p.experiment, p.out_name, p.T, p.generator_hash) == (
        "claude-haiku-5-5", "persistgym_haiku", "persistgym_h1h3_haiku", registered.HAIKU_T,
        registered.LUNA_GENERATOR_HASH)                     # luna's episodes
    assert p.cells == ("F-0", "W-0", "W-n-0") and "Σ-n-0" not in p.cells
    assert p.kinds == (("F-0", BASE), ("W-0", BASE), ("W-n-0", BASE), ("F-0", RESTATED),
                       (ST, BASE))
    assert not p.echo and p.replication and p.api == hh.MESSAGES_API and p.power_path is None
    assert p.task_cells == hh.TASK_CELLS and p.nr_task_cells == hh.NR_TASK_CELLS
    # R8's size record sets HAIKU_T and HAIKU_CELLS; both are read at call time
    monkeypatch.setattr(registered, "HAIKU_T", 150)
    monkeypatch.setattr(registered, "HAIKU_CELLS", ("F-0", "W-0"))
    p = hh.profile(HAIKU)
    assert p.T == 150 and p.not_run == ("W-n-0",) and ("W-n-0", BASE) not in p.kinds
    monkeypatch.setattr(registered, "HAIKU_CELLS", ("F-0", "W-0", "Σ-n-0"))
    with pytest.raises(hh.Refusal, match="R8 registers F-0 and W-0"):
        hh.profile(HAIKU)
    monkeypatch.setattr(registered, "HAIKU_CELLS", ("F-0", "W-n-0"))
    with pytest.raises(hh.Refusal, match="R8 registers F-0 and W-0"):
        hh.profile(HAIKU)
    monkeypatch.setattr(registered, "HAIKU_CELLS", hh.R8_CELLS)
    p = hh.profile(HAIKU, "persistgym_validity")
    assert p.experiment == "persistgym_validity" and p.cells == hh.R8_CELLS
    assert p.registered_experiment == "persistgym_haiku"
    # the completeness, cost, accounting, cell and exclusion tables run over luna's task
    # cells, so Haiku's must be luna's (R8), in their order
    monkeypatch.setattr(registered, "HAIKU_TASK_CELLS", hh.TASK_CELLS[:4])
    with pytest.raises(hh.Refusal, match=r"HAIKU_TASK_CELLS is .*, not luna's"):
        hh.profile(HAIKU)
    monkeypatch.setattr(registered, "HAIKU_TASK_CELLS", hh.TASK_CELLS)
    monkeypatch.setattr(registered, "HAIKU_SINGLE_TURN_TASK_CELLS", hh.NR_TASK_CELLS[::-1])
    with pytest.raises(hh.Refusal, match=r"HAIKU_SINGLE_TURN_TASK_CELLS is .*, not luna's"):
        hh.profile(HAIKU)
    monkeypatch.setattr(registered, "HAIKU_SINGLE_TURN_TASK_CELLS", hh.NR_TASK_CELLS)
    assert hh.profile(HAIKU).task_cells == hh.TASK_CELLS


def test_haiku_runs_are_discovered_in_their_own_experiment(tmp_path):
    sw = HaikuSweep(tmp_path)
    sw.standard()
    luna = Sweep(tmp_path / "luna")                 # luna's sweep in the same results root
    luna.root, luna.raw = sw.root, sw.raw
    luna.clock = sw.clock + timedelta(days=1)
    luna.standard()
    h = sw.compute(runs=list(sw.ids))
    assert h["status"] == hh.FINAL and h["model"] == HAIKU
    assert [r["cell"] for r in h["inputs"]["runs"]] == ["F-0", "W-0", "W-n-0", "F-0", ST]
    assert h["profile"]["experiment"] == "persistgym_haiku" and h["profile"]["replication"]
    assert h["primary_episodes"] == T * (3 * 8 + 8 + 4)
    assert h["inputs"]["skipped"] == []             # luna's folder is not even looked at
    lh = luna.compute(runs=list(luna.ids))          # and luna's analysis reads luna's only
    assert lh["model"] == "gpt-6-luna" and "profile" not in lh
    assert {r["cell"] for r in lh["inputs"]["runs"]} == set(registered.LUNA_CELLS) | {ST}
    # a run of another model in Haiku's folder is skipped, with the reason
    other = sw.root / "persistgym_haiku" / "x-luna"
    other.mkdir()
    (other / "meta.json").write_text(json.dumps({"experiment": "persistgym_haiku",
                                                 "model_requested": "gpt-6-luna"}))
    h = sw.compute(runs=list(sw.ids))
    assert {"folder": "x-luna", "reason": "model 'gpt-6-luna', not claude-haiku-5-5"} in \
        h["inputs"]["skipped"]
    with pytest.raises(hh.Refusal, match="no persistgym_pilot/ folder"):
        sw.compute(experiment="persistgym_pilot")


def test_another_experiment_is_provisional(tmp_path):
    sw = HaikuSweep(tmp_path)
    sw.EXPERIMENT = "persistgym_haiku_copy"
    sw.standard()
    h = sw.compute(experiment="persistgym_haiku_copy")
    assert h["status"] == hh.PROVISIONAL and h["profile"]["experiment"] == "persistgym_haiku_copy"
    assert any("not Haiku's registered experiment (persistgym_haiku)" in x
               for x in h["provisional_reasons"])


def test_haiku_has_no_sigma_cell(tmp_path):
    sw = HaikuSweep(tmp_path)
    sw.standard()
    sw.run("Σ-n-0", records=sw.records("Σ-n-0"))
    with pytest.raises(hh.Refusal, match="'Σ-n-0' is not one of Haiku's sweep cells"):
        sw.compute()


def test_haiku_estimands_equal_lunas_on_the_same_outcomes(tmp_path):
    """The same outcomes give the same H1 and H3 quantities, intervals, p-values and model
    checks on both models (the same code, and luna's seeds, R8); only the labels differ."""
    luna = toy(tmp_path / "a")
    luna.standard()
    lh = luna.compute()
    sw = haiku_toy(tmp_path / "b")
    sw.standard()
    h = sw.compute()
    assert h["status"] == hh.FINAL and h["bootstrap"]["seed"] == SEED + 10
    for key in ("h1", "h3", "h1_lookups", "h1_predictions", "glm_9_1", "glm_9_1_firth",
                "glm_h3", "glm_h3_powersim", "glm_9_1_with_w_n_0"):
        assert _json(h[key]) == _json(lh[key]), key
    assert _json(h["h1_tokens"]) == _json(lh["h1_tokens"])
    luna_rows = [r for r in lh["accounting"] if r["cell"] != "Σ-n-0"]
    assert _json(h["accounting"]) == _json(luna_rows)
    assert h["h1"]["delta_h1"]["exact"] == "3/5" and h["h3"]["delta_h3"]["exact"] == "0"
    rp = h["replication"]
    assert rp["H1"]["p_one_sided"] == lh["h1"]["p_one_sided"]
    assert rp["H3"]["p_one_sided"] == lh["h3"]["p_one_sided"]
    assert rp["H1"]["rejects_unadjusted"] and rp["H1"]["model_agrees"]
    assert rp["H1"]["label"] == "the unadjusted test rejects, and the model check agrees"
    assert rp["H1"]["kill_reading"] is False and "reads luna only" in rp["H1"]["kill_note"]
    # at T = 10, H3's 90% CI reaches past 5pp: its test does not reject, as on luna
    assert rp["H3"]["p_one_sided"] > 0.05 and not lh["family"]["H3"]["holm_rejects"]
    assert rp["H3"]["label"] == "the unadjusted test does not reject, and the model check agrees"
    # F-0 observed-rec-far is 10/10: the rules not in force are sensitivity lines, labelled
    assert set(rp["H1"]["sensitivity_rules"]) == {"literal", "probability-scale"}
    assert rp["H1"]["sensitivity_rules"]["literal"]["label"] == (
        "the unadjusted test rejects, and the model check does not agree")
    assert "family" not in h and "achieved_power" not in h and "changed_after_final" not in h
    assert h["pre_specified"] == list(hh.PRE_SPECIFIED)


def test_haiku_labels_never_say_supported(tmp_path):
    """R8: the replication's tests are never called "supported", whatever the outcome: here an
    H1 whose test rejects (the toy), and a null one whose kill reading fires."""
    sw = haiku_toy(tmp_path / "a")
    sw.standard()
    h = sw.compute()
    assert "support" not in _words(h).lower()
    text = "\n".join(hh.summary_lines(h))
    for needle in ("# H1 and H3 on claude-haiku-5-5's PersistGym runs: R8's replication",
                   "**A replication** (PREREG §17.8, amendment R8)",
                   "**Pre-specified rules** (fixed for luna on 2026-10-10",
                   "## Replication (R8; outside luna's Holm family)",
                   "Unadjusted at one-sided 0.05 (outside luna's Holm family, R8): rejects.",
                   ("- **H1, replication (R8): the unadjusted test rejects, and the model check "
                    "agrees.**"),
                   "- **Kill reading** (computed as on luna",
                   "on Haiku this reading neither kills nor confirms H1",
                   ("- **H3, replication (R8): the unadjusted test does not reject, and the "
                    "model check agrees.** Outside luna's Holm family"),
                   "### Multiplicity (§9.4; R8)", "luna's family stays H1 and H3 on luna",
                   "the replication's label would be: the unadjusted test rejects",
                   "pre-specified for Haiku by R8", f"`{hh.LUNA_CITED_OUTPUT}`",
                   "Power at T = 10 (R8: one-sided 0.05",
                   "unavailable (no power table given (--power-path))",
                   "No echo exclusion (R8)", "**One model per provider.**",
                   "**Not blind to luna.**", "**Thinking is not inspected.**",
                   "Σ-n-0 and every replay-on cell (R8)",
                   "The replay read the Messages transcripts",
                   ("a whitespace-only reply also went back as `(no reply)`, but counts its "
                    "whitespace's tokens"),
                   "| Run kind | Task cell | Success | Content failures | Stopped responses |",
                   "All four met: ",
                   f"with a pinned snapshot ID without a date suffix (R8) (returned: `{HAIKU}`)",
                   "with no Flex discount; the standard tier on every response)",
                   ("This output holds Haiku's results only, not luna's "
                    f"(`{hh.LUNA_CITED_OUTPUT}`) and no agreement statement: where the two "
                    "disagree, both are to be reported side by side")):
        assert needle in text, needle
    for luna_only in ("Holm (family of 2)", "Changed after the FINAL", "Flex tier",
                      "## Confirmatory", "Echo excluded", "Σ-n-0 (expl.)", "no dated snapshot",
                      "disagreement is stated, both results are reported side by side",
                      "so a turn sent back as `(no reply)` counts 0 tokens."):
        assert luna_only not in text, luna_only
    assert h["service_tiers_served"] == {"standard": 12 * h["primary_episodes"]}
    # the tiers are read from the records, not assumed
    for tiers, words in (({"priority": 3, "standard": 9},
                          "tiers served: priority (3 responses), standard (9 responses))"),
                         ({}, "no service tier reported)")):
        assert words in "\n".join(hh.not_shown_r8_lines({**h, "service_tiers_served": tiers}))
    null = HaikuSweep(tmp_path / "b")                 # equal penalties: the kill reading fires
    null.outcome("W-0", ONR, [0] * T)
    null.outcome("W-0", OR, [0] * T)
    null.standard()
    h = null.compute()
    assert h["h1"]["kill"] is True and h["replication"]["H1"]["kill_reading"] is True
    assert h["replication"]["H1"]["label"].startswith("the unadjusted test does not reject")
    text = "\n".join(hh.summary_lines(h))
    assert "(computed as on luna: Δ_H1 < 10pp and the 90% upper bound < 15pp): **fires**" in text
    assert "drop the" not in text and "support" not in _words(h).lower()


def test_replication_labels_at_their_boundaries():
    assert hh.replication_label(0.05, True) == (
        "the unadjusted test rejects, and the model check agrees")
    assert hh.replication_label(0.0501, True) == (
        "the unadjusted test does not reject, and the model check agrees")
    assert hh.replication_label(0.01, False) == (
        "the unadjusted test rejects, and the model check does not agree")
    assert hh.replication_label(None, True).startswith("not computable")
    h1 = {"p_one_sided": 0.5, "model_check": {"agrees": True}, "kill": False}
    h3 = {"p_one_sided": 1.0, "model_check": {"agrees": False},
          "delta_h3": {"ci90": [0.15, 0.25]}}
    rp = hh.replication_readings(h1, h3)
    assert rp["H3"]["ci90_above_margin"] is True
    assert rp["H3"]["label"] == ("the unadjusted test does not reject, and the model check does "
                                 f"not agree; {hh.H3_AGAINST}")
    assert not rp["H1"]["rejects_unadjusted"] and rp["H1"]["sensitivity_rules"] == {}
    assert "support" not in json.dumps(rp, ensure_ascii=False).lower()


def test_haiku_without_w_n_0(tmp_path, monkeypatch):
    """R8's size rule can drop W-n-0 (registered.HAIKU_CELLS then lacks it): the analysis needs
    no W-n-0 run, refuses one, and reports W-n-0 as pre-registered, not run (budget)."""
    monkeypatch.setattr(registered, "HAIKU_CELLS", ("F-0", "W-0"))
    sw = HaikuSweep(tmp_path)
    sw.standard()
    assert all(c != "W-n-0" for c, _ in sw.kinds())
    h = sw.compute()
    assert h["status"] == hh.FINAL and h["profile"]["cells_not_run"] == ["W-n-0"]
    assert set(h["h1"]["cells"]) == {"F-0 NR", "W-0 NR", "F-0 R", "W-0 R"}
    assert h["h1"]["w_n_0_alongside"]["status"] == hh.NOT_RUN_BUDGET
    assert h["glm_9_1_with_w_n_0"]["status"] == hh.NOT_RUN_BUDGET
    assert {r["cell"] for r in h["accounting"]} == {"F-0", "W-0"}
    assert all(set(r["means"]) == {"F-0", "W-0"} for r in h["cost_outcomes"])
    assert all(r["kind"] != "W-n-0" for r in h["cells"] + h["exclusions"] + h["repeats"])
    assert "support" not in _words(h).lower()
    text = "\n".join(hh.summary_lines(h))
    for needle in ("**W-n-0: pre-registered, not run (budget)** (R8's size rule",
                   "W-n-0 alongside: pre-registered, not run (budget) (R8's size rule).",
                   "| not recoverable | 1.000 (10/10) | 0.000 (0/10) | not run |",
                   ("W-n-0 as a third harness level (a sensitivity analysis, ruling of "
                    "2026-10-10): not fitted, W-n-0 being pre-registered, not run (budget)."),
                   "| Task cell | Outcome | W-0 |\n|---|---|---|",
                   ("Σ-n-0 and every replay-on cell (R8); W-n-0 (pre-registered, not run "
                    "(budget))")):
        assert needle in text, needle
    sw.run("W-n-0")
    with pytest.raises(hh.Refusal, match="'W-n-0' is not one of Haiku's sweep cells"):
        sw.compute()
    # with W-n-0 registered, its runs are required like the others
    monkeypatch.setattr(registered, "HAIKU_CELLS", ("F-0", "W-0", "W-n-0"))
    sw2 = HaikuSweep(tmp_path / "b")
    sw2.standard(skip={("W-n-0", BASE)})
    with pytest.raises(hh.Refusal, match="W-n-0: 80 of 80 repeat-0 episodes have no record"):
        sw2.compute()


def test_haiku_records_are_never_excluded_for_an_echo(tmp_path):
    """The Messages API echoes nothing (R8): echo fields that luna's defensive check would read
    as a mismatch exclude no Haiku record. A record the runner marked excluded (never on the
    Messages wire) is still excluded, as the runner's."""
    odd = {**HAIKU_ECHO, "context_requested": "current_turn",
           "context_echoed": {"all_turns": 1}, "effort_echoed": {"high": 2}}
    for kind in (Sweep, HaikuSweep):
        sw = kind(tmp_path / kind.__name__)
        sw.fields("F-0", OR, 5, echo=odd)
        sw.fields("W-0", ONR, 4, excluded=True, exclusion_reason="marked by the runner")
        sw.standard()
        h = sw.compute()
        ex = {(e["kind"], e["task_cell"]): e for e in h["exclusions"]}
        if kind is Sweep:
            assert ex[("F-0", OR)]["excluded_echo"] == 1 and h["h1"]["cells"]["F-0 R"]["n"] == 9
            continue
        assert h["h1"]["cells"]["F-0 R"]["n"] == T          # not excluded
        assert ex[("F-0", OR)]["excluded_by_runner"] == 0
        assert ex[("W-0", ONR)]["excluded_by_runner"] == 1
        assert h["h1"]["cells"]["W-0 NR"]["n"] == T - 1
        assert "excluded_echo" not in ex[("F-0", OR)] and "echo_share" not in ex[("F-0", OR)]
        assert "echo_cells_over_5pct" not in h
        text = "\n".join(hh.summary_lines(h))
        assert "| Excluded by the runner |" in text and "(**over 5%**)" not in text


def test_haiku_usage_and_reasoning_tokens(tmp_path):
    """Usage is in the Responses meanings (the runner added the cache reads and writes to
    input_tokens): total tokens are input + output, nothing added twice. Reasoning tokens the
    provider did not report are null: missing, never 0, and §9.5's outcome is then reported as
    unavailable (R8), decided per task cell and harness cell: a cell with any unreported
    episode has no mean and no ratio; where it is F-0, the reference, no ratio is reported;
    and no cell is fitted on part of its episodes."""
    DR, DNR_ = "derived-rec-far", DNR
    sw = HaikuSweep(tmp_path)
    sw.fields("F-0", OR, 0, usage={**HAIKU_USAGE, "reasoning_tokens": 40})   # 1 of 10 reported
    w0 = [50 + 10 * (t % 3) for t in range(T)]
    for t in range(T):
        # derived-rec-far: F-0 and W-0 report every count, W-n-0 none (a whole cell missing)
        sw.fields("F-0", DR, t, usage={**HAIKU_USAGE, "reasoning_tokens": 100})
        sw.fields("W-0", DR, t, usage={**HAIKU_USAGE, "reasoning_tokens": w0[t]})
        # derived-nonrec-far: W-0 and W-n-0 report every count, F-0 none (the reference)
        for cell in ("W-0", "W-n-0"):
            sw.fields(cell, DNR_, t, usage={**HAIKU_USAGE, "reasoning_tokens": 70})
    sw.standard()
    h = sw.compute()
    row = {(r["task_cell"], r["outcome"]): r for r in h["cost_outcomes"]}
    assert row[(OR, "tokens_total")]["means"]["F-0"] == 10_300          # not 19,800
    assert "unavailable" not in row[(OR, "tokens_total")]
    every = {c: {"missing": T, "of": T} for c in ("F-0", "W-0", "W-n-0")}
    # nothing reported
    none_ = row[(ONR, "reasoning_tokens")]
    assert none_["unavailable"] == every and none_["ratios"] == {}
    assert none_["means"] == {"F-0": None, "W-0": None, "W-n-0": None}
    assert none_["note"] == hh.REFERENCE_UNAVAILABLE
    # F-0 reports 1 of its 10: unavailable, not fitted on the one, so no ratio at all
    partly = row[(OR, "reasoning_tokens")]
    assert partly["unavailable"] == {**every, "F-0": {"missing": T - 1, "of": T}}
    assert partly["ratios"] == {} and partly["means"]["F-0"] is None
    # the reference missing everywhere while W-0 and W-n-0 report: no ratio (none would be
    # identified), though their means are reported
    ref = row[(DNR_, "reasoning_tokens")]
    assert ref["unavailable"] == {"F-0": {"missing": T, "of": T}} and ref["ratios"] == {}
    assert ref["means"] == {"F-0": None, "W-0": 70.0, "W-n-0": 70.0}
    # a whole compared cell missing: its ratio is unavailable, and W-0's is fitted on F-0 and
    # W-0 alone (a complete two-cell table: the ratio of the sums)
    whole = row[(DR, "reasoning_tokens")]
    assert whole["unavailable"] == {"W-n-0": {"missing": T, "of": T}}
    assert set(whole["ratios"]) == {"W-0"} and whole["means"]["W-n-0"] is None
    assert whole["ratios"]["W-0"]["ratio"] == pytest.approx(sum(w0) / (100 * T))
    assert whole["n_rows"] == 2 * T
    text = "\n".join(hh.summary_lines(h))
    na = "unavailable (not reported)"
    for tc in (ONR, OR, DNR_):
        assert f"| {tc} | reasoning tokens | {na} | {na} |" in text, tc
    dr = next(x for x in text.splitlines() if x.startswith(f"| {DR} | reasoning tokens |"))
    assert dr.startswith(f"| {DR} | reasoning tokens | {sum(w0) / (100 * T):.3f} [")
    assert dr.endswith(f"| {na} |")
    line = next(x for x in text.splitlines() if x.startswith("Unavailable (R8"))
    assert ("observed-rec-far reasoning tokens, F-0 9 of 10 episodes not reported, W-0 10 of "
            "10 episodes not reported, W-n-0 10 of 10 episodes not reported (F-0 is the "
            "reference, so no ratio);") in line
    assert line.endswith("derived-rec-far reasoning tokens, W-n-0 10 of 10 episodes not "
                         "reported.")
    assert "Fitted on the episodes" not in text


def test_haiku_replay_reads_messages_transcripts(tmp_path, monkeypatch):
    """§2.8's replay on Messages transcripts: the observation is the last message's text
    blocks, the reply the response's text blocks as the session kept them. Turns with no
    visible reply (thinking only, or a refusal whose partial text the session discarded) went
    back as `(no reply)` and count 0 tokens: here three such turns before a near need step keep
    its evidence in the window. Counting the refusals' partial text instead (the visible text,
    not what the session kept) would drop it, and the replay would disagree with the runner."""
    sw = HaikuSweep(tmp_path)
    partial = _text("I can't help with", 20)
    silent = {7: ("refusal", partial), 8: ("end_turn", ""), 9: ("refusal", partial)}
    reps = [0 if i in silent else 2 for i in range(NEED + 2)]
    # counted as kept, the window starts at turn 6; with the refusals' 20 tokens, at turn 8,
    # which drops derived-rec-near's first evidence step (7)
    assert _keep_seq(reps, NEED) == 6 and _keep_seq([2] * 7 + [20, 0, 20, 2, 2], NEED) == 8
    for tc in ("observed-nonrec-near", "derived-rec-near"):
        eid = hh.episode_id_of("W-0", BASE, 1, tc)
        sw.silent[("W-0", eid)] = silent
        sw.fields("W-0", tc, 1, need_info={"keep_start": 6},
                  incomplete=[{"reason": "refusal:general_harms", "pending_step": 7},
                              {"reason": "refusal:general_harms", "pending_step": 9}])
    sw.standard()
    h = sw.compute()
    assert h["accounting_check"]["checked"] == 2 * T * 8 and h["warnings"] == []
    cells = {(r["kind"], r["task_cell"]): r for r in h["cells"]}
    near = cells[("W-0", "observed-nonrec-near")]
    assert near["stopped_responses"] == {"refusal:general_harms": 2}
    assert near["episodes_with_a_refusal"] == 1
    assert "refusal:general_harms 2 (1 episode(s) with a refusal)" in "\n".join(
        hh.summary_lines(h))
    # the visible text of a refusal is not what W counted
    monkeypatch.setattr(hh, "reply_counted",
                        lambda response, api=hh.RESPONSES_API: hh.MESSAGES.text(response))
    with pytest.raises(hh.AccountingBug, match=r"derived-rec-near/base': S_verbatim = 1, but "
                                               r"the drop-oldest replay gives 0 \(window start 8"):
        sw.compute()


def test_transcripts_read_on_the_wrong_wire_are_a_bug(tmp_path):
    """The replay reads a run's transcript on its own wire: a Responses-shaped transcript under
    Haiku's profile has no request to replay, and a Messages one under luna's neither."""
    sw = HaikuSweep(tmp_path)
    sw.transcript = lambda eid, cell, n, turns: transcript_lines(eid, cell, n, turns)
    sw.standard()
    with pytest.raises(hh.AccountingBug, match="does not end with a user message"):
        sw.compute()
    runs, _ = hh.discover(sw.root, prof=hh.profile(HAIKU))
    assert hh.accounting_check(runs, sw.raw, "persistgym_haiku", hh.RESPONSES_API)["bugs"] == []
    good = HaikuSweep(tmp_path / "b")
    good.standard()
    runs, _ = hh.discover(good.root, prof=hh.profile(HAIKU))
    assert hh.accounting_check(runs, good.raw, "persistgym_haiku", hh.MESSAGES_API)["bugs"] == []
    assert hh.accounting_check(runs, good.raw, "persistgym_haiku")["bugs"]


def test_haiku_replay_matches_the_harness_on_real_episodes(tmp_path, monkeypatch):
    """Real episodes (generator, small volume) played on the Messages wire by Haiku's W-0 and
    W-n-0 cells with the fake model: long replies push near evidence out, lookups shift turns,
    some replies are empty (thinking only) and some calls are refusals after a long partial
    text. The replay agrees with the runner's S_verbatim, window start and payload in every
    episode; counting the refusals' partial text (the visible text, not what the session kept)
    breaks it, and so does reading the transcripts on the Responses wire."""
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
        if i % 5 == 2:
            return long_reply           # the partial text of a refusal (status below)
        if i % 6 == 4:
            return "ACTION: lookup(record)"
        if i % 11 == 3:
            return ""                   # thinking only: no visible reply
        if i % 13 == 8:
            return "\n\n"               # whitespace only: sent back as the placeholder too
        return long_reply if i % 7 == 0 else short

    def status(payload, tag):
        return "refusal" if int(tag[1:]) % 5 == 2 else "completed"

    cfg = HarnessConfig(model=HAIKU, reasoning_effort="medium", service_tier="standard")
    results = tmp_path / "results"
    for cell in ("W-0", "W-n-0"):
        run_batch(eps, CELLS[cell], cfg,
                  FakeModel(reply, status_fn=status, report_thinking_tokens=False),
                  experiment="persistgym_haiku", run_id=f"r-{cell}", results_root=results,
                  raw_root=results / "raw")
    monkeypatch.setattr(registered, "HAIKU_GENERATOR_HASH", eps[0].config_hash)
    prof = hh.profile(HAIKU)
    runs, skipped = hh.discover(results, prof=prof)
    assert len(runs) == 2 and skipped == []
    check = hh.accounting_check(runs, results / "raw", prof.experiment, prof.api)
    assert check["bugs"] == [] and check["warnings"] == []
    assert check["checked"] == 2 * len(eps)
    recs = [r for run in runs for r in run.records]
    near = [r["need_payload"]["S"] for r in recs if r["task_cell"].endswith("-near")]
    assert True in near and False in near                  # both outcomes are exercised
    assert any(r["n_lookups"] for r in recs)
    assert any(x["reason"] == "refusal:general_harms" for r in recs for x in r["incomplete"])
    assert all(r["usage"]["reasoning_tokens"] is None for r in recs)
    with gzip.open(results / "raw" / "persistgym_haiku" / "r-W-0" / "transcript.jsonl.gz",
                   "rt", encoding="utf-8") as fh:
        lines = [json.loads(line) for line in fh]
    sent = [m for x in lines for m in x["payload"]["messages"]]
    assert any(m["content"][0]["text"] == EMPTY_REPLY_PLACEHOLDER for m in sent
               if m["role"] == "assistant")
    # whitespace-only replies were played, went back as the placeholder, and the session
    # counted their whitespace toward W: the replay counts them so, and agrees (above)
    ws = [x for x in lines if x["kind"] == "step" and hh.MESSAGES.text(x["response"]) == "\n\n"]
    assert ws and hh.reply_counted(ws[0]["response"], hh.MESSAGES_API) == "\n\n"
    assert all(m["content"][0]["text"].strip() for m in sent)
    wrong_wire = hh.accounting_check(runs, results / "raw", prof.experiment, hh.RESPONSES_API)
    assert wrong_wire["bugs"] and all("does not end with a user message" in b
                                      for b in wrong_wire["bugs"])
    monkeypatch.setattr(hh, "reply_counted",
                        lambda response, api=hh.RESPONSES_API: hh.MESSAGES.text(response))
    naive = hh.accounting_check(runs, results / "raw", prof.experiment, prof.api)
    assert naive["bugs"] or naive["warnings"]


HAIKU_VALIDITY_GLOB = "results/persistgym_validity/*-F-0-claude-haiku-5-5/episodes.jsonl"


def _power_meta(folder, part="luna", glob=HAIKU_VALIDITY_GLOB) -> None:
    """A power run's meta.json, as power_sim writes it (its config: the arguments)."""
    (folder / "meta.json").write_text(json.dumps(
        {"experiment": "power_sim", "config": {"part": part, "luna_validity_glob": glob}}),
        encoding="utf-8")


def test_haiku_power_from_a_power_table(tmp_path):
    """R8's power at the chosen T comes from a per-T power table of power_sim's luna part,
    simulated from Haiku's validity runs (its meta.json shows them); P(it rejects and the
    model check agrees) is P(it rejects) less the model check's vetoes."""
    sw = HaikuSweep(tmp_path)
    sw.standard()
    (tmp_path / "power").mkdir()
    table = tmp_path / "power" / "luna_power.csv"
    cols = ["scenario", "templates", "reps", "p_f0_onr", "p_f0_or", "P_h1_unadjusted",
            "P_h3_unadjusted", "P_h1_glm_veto", "P_h3_glm_veto", "P_h1_supported_worst_step"]
    rows = [["primary", "10", "200", "0.95", "0.9", "0.70", "0.80", "0.05", "0.0", "0.6"],
            ["primary", "20", "200", "0.95", "0.9", "0.90", "0.95", "0.01", "0.0", "0.8"],
            ["pessimistic", "10", "200", "0.85", "0.8", "0.40", "0.45", "0.10", "0.02", "0.3"]]
    table.write_text("\n".join(",".join(r) for r in [cols, *rows]) + "\n", encoding="utf-8")
    _power_meta(table.parent)
    h = sw.compute(power_path=table)
    pw = h["power"]
    assert pw["available"] and pw["T"] == T and pw["validity_glob"] == HAIKU_VALIDITY_GLOB
    assert [r["scenario"] for r in pw["rows"]] == ["primary", "pessimistic"]
    p = pw["rows"][0]
    assert (p["power_h1_rejects"], p["power_h3_rejects"]) == (0.70, 0.80)
    assert p["power_h1_rejects_and_model_agrees"] == pytest.approx(0.65)
    assert p["power_h3_rejects_and_model_agrees"] == pytest.approx(0.80)
    assert pw["rows"][1]["power_h3_rejects_and_model_agrees"] == pytest.approx(0.43)
    text = "\n".join(hh.summary_lines(h))
    assert ("primary, F-0 observed-far at 0.95 (NR) and 0.90 (R): the unadjusted test "
            "rejects, H1 0.700 and H3 0.800; it rejects and the model check agrees, H1 0.650 "
            "and H3 0.800") in text
    assert "did not set T (R8)" in text and "support" not in _words(h).lower()
    assert f"whose run measured the template SD on `{HAIKU_VALIDITY_GLOB}`" in text
    none = hh.replication_power(table, 30)
    assert not none["available"] and none["note"] == "the power table has no row at T = 30"
    bad = tmp_path / "power" / "decision.csv"
    bad.write_text("scenario,reading\nprimary,x\n", encoding="utf-8")
    assert "not a per-T power table" in hh.replication_power(bad, T)["note"]
    assert hh.replication_power(tmp_path / "missing.csv", T)["note"].startswith("no power table")
    # its provenance (R8: "re-estimated from Haiku's validity runs"): a table whose run does not
    # show Haiku's validity runs is not the replication's power
    for part, glob, why in (
            ("luna", "results/persistgym_validity/*-F-0-gpt-6-luna/episodes.jsonl",
             "does not name claude-haiku-5-5's validity runs"),
            ("luna", "results/persistgym_validity/*/episodes.jsonl",
             "does not name claude-haiku-5-5's validity runs"),
            ("luna", "", "does not name claude-haiku-5-5's validity runs"),
            ("all", HAIKU_VALIDITY_GLOB, "not a run of power_sim's luna part")):
        _power_meta(table.parent, part, glob)
        pw = hh.replication_power(table, T)
        assert not pw["available"] and pw["rows"] == [] and why in pw["note"], (part, glob)
        assert pw["note"].startswith("not simulated from Haiku's validity runs (R8)")
    (table.parent / "meta.json").unlink()
    assert "no meta.json next to the power table" in hh.replication_power(table, T)["note"]
    # luna's own committed power table has rows at T = 200, and is refused
    lunas = hh.REPO_ROOT / "results" / "power_sim" / "20261010T030442Z" / "luna_power.csv"
    pw = hh.replication_power(lunas, 200)
    assert not pw["available"] and "gpt-6-luna" in pw["note"]
    assert pw["validity_glob"] == "results/persistgym_validity/*-F-0-gpt-6-luna/episodes.jsonl"
    text = "\n".join(hh.summary_lines({**h, "power": pw}))
    assert "Power at T = 200 (R8: one-sided 0.05, simulated with" in text
    assert "unavailable (not simulated from Haiku's validity runs (R8)" in text


def test_haiku_main_writes_its_own_folder(tmp_path, monkeypatch, capsys):
    sw = haiku_toy(tmp_path)
    sw.standard()
    assert sw.main(monkeypatch=monkeypatch) == 0
    (out,) = (sw.root / "persistgym_h1h3_haiku").iterdir()
    assert not (sw.root / "persistgym_h1h3").exists()
    h = json.loads((out / "h1h3.json").read_text(encoding="utf-8"))
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    text = (out / "summary.md").read_text(encoding="utf-8")
    assert h["status"] == hh.FINAL and h["model"] == HAIKU and h["templates"] == T
    assert meta["experiment"] == "persistgym_h1h3_haiku" and meta["paid_calls"] == 0
    assert meta["seeds"] == {"bootstrap": SEED + 10, "bayesian_glmm": SEED + 11}
    assert meta["config"]["prereg"] == hh.R8_PREREG and meta["config"]["model"] == HAIKU
    assert meta["config"]["cells"] == ["F-0", "W-0", "W-n-0"]
    assert meta["config"]["power_source"] is None
    assert "support" not in text.lower() and "--model claude-haiku-5-5`" in text
    # luna's default is unchanged: it reads luna's folder only, and there is none here
    capsys.readouterr()
    assert hh.main(["--results-root", str(sw.root), "--no-write"]) == 2
    assert "no persistgym/ folder" in capsys.readouterr().err


def test_the_request_side_checks_episode_is_excluded(tmp_path):
    """R8: "A violation is a harness bug: the episode is excluded and the run stops". The check
    raises before the request is sent, and the runner writes no record of the episode: it is
    found from the run's meta.json (sequential play: the first planned episode without a
    record), excluded with the record its continuation holds (DESIGN §7.9 replays it), counted
    per cell and listed in the Deviations, in an open sweep and in a closed one."""
    STOP = hh.REQUEST_CHECK_STOP
    sw = HaikuSweep(tmp_path)
    sw.standard(skip={("W-0", BASE)})
    recs = sw.records("W-0")
    ids = [r["episode_id"] for r in recs]
    k = ids.index(hh.episode_id_of("W-0", BASE, 1, OR))
    stopped = sw.run("W-0", records=recs[:k], exit_reason=STOP, episode_ids=ids)
    # open sweep, no continuation yet: the episodes after it are missing, not it
    with pytest.raises(hh.Refusal) as e:
        sw.compute()
    assert f"W-0: {len(ids) - k - 1} of {len(ids)} repeat-0 episodes have no record" in str(e.value)
    assert f"(first: {ids[k + 1]})" in str(e.value)
    # a closed sweep: the stopped episode is excluded by the check, the rest never played
    h = sw.compute(sweep_closed="decisions.md, a test entry")
    ex = {(e["kind"], e["task_cell"]): e for e in h["exclusions"]}
    assert ex[("W-0", OR)]["excluded_request_check"] == 1
    assert sum(e["excluded_request_check"] for e in h["exclusions"]) == 1
    assert h["h1"]["cells"]["W-0 R"]["n"] == 1 and h["h1"]["cells"]["F-0 R"]["n"] == T
    assert any(d.startswith("W-0: 1 of 80 repeat-0 episodes are excluded because the "
                            "request-side check stopped their run") and d.endswith(ids[k])
               for d in h["deviations"])
    # the continuation replays from the stopped episode (DESIGN §7.9): its record is dropped
    cont = sw.run("W-0", records=recs[k:], episode_ids=ids[k:])
    h = sw.compute(links={cont: stopped})
    assert h["status"] == hh.FINAL
    assert h["h1"]["cells"]["W-0 R"]["n"] == T - 1 and h["h1"]["cells"]["W-0 NR"]["n"] == T
    ex = {(e["kind"], e["task_cell"]): e for e in h["exclusions"]}
    assert ex[("W-0", OR)]["excluded_request_check"] == 1
    assert ex[("W-0", OR)]["dropped_duplicates"] == 1
    assert sum(e["excluded_request_check"] for e in h["exclusions"]) == 1
    assert {"cell": "W-0", "episode_id": ids[k], "repeat": 0, "kept_from": None,
            "dropped": [{"run_id": cont, "exit_reason": "DONE"}]} in h["dropped_records"]
    assert any(d.endswith(ids[k]) and "request-side check" in d for d in h["deviations"])
    assert any(stopped in w and f"{ids[k]} (repeat 0)" in w for w in h["warnings"])
    text = "\n".join(hh.summary_lines(h))
    assert "| Excluded by the runner | Request-side check (R8) | Transport excluded |" in text
    assert "## Deviations (§13: listed in every write-up)" in text
    # the check's rule is R8's, on the Messages wire: luna's analysis reads no such stop
    luna = Sweep(tmp_path / "luna")
    luna.standard(skip={("W-0", BASE)})
    lrecs = luna.records("W-0")
    luna.run("W-0", records=lrecs, exit_reason=STOP, episode_ids=[])
    lh = luna.compute()
    assert all("excluded_request_check" not in e for e in lh["exclusions"])
    assert lh["deviations"] == [] and lh["status"] == hh.FINAL
    assert not any("request-side check" in w for w in lh["warnings"])


def test_the_request_side_check_in_parallel_play(tmp_path):
    """In parallel play the run's stop reason names the episode the check stopped; every other
    episode the run started and left with no record raised too (the run names only the first)
    and is excluded with it; those in flight that ended RUN_STOPPED wait for the continuation;
    an abandoned one is not counted. A stopped run whose episode cannot be found refuses."""
    STOP = hh.REQUEST_CHECK_STOP
    sw = HaikuSweep(tmp_path)
    sw.standard(skip={("F-0", BASE)})
    recs = sw.records("F-0")
    ids = [r["episode_id"] for r in recs]
    k = ids.index(hh.episode_id_of("F-0", BASE, 2, ONR))
    played = recs[:k] + [dict(r, exit_reason="RUN_STOPPED") for r in recs[k + 1:k + 3]]
    stopped = sw.run("F-0", records=played, exit_reason=STOP, episode_ids=ids,
                     parallel={"max_episodes_in_flight": 16, "episodes_started": k + 5,
                               "stop_reason": f"{STOP} in episode {ids[k]}",
                               "abandoned_episode_ids": [ids[k + 4]]})
    runs, _ = hh.discover(sw.root, prof=hh.profile(HAIKU))
    found = hh.request_check_stops(runs)
    assert set(found) == {("F-0", ids[k], 0), ("F-0", ids[k + 3], 0)}
    assert found[("F-0", ids[k], 0)] == (stopped, (
        f"request-side check (R8): {stopped} stopped in this episode; a harness bug, so the "
        "episode is excluded, whatever a later run holds"))
    assert found[("F-0", ids[k + 3], 0)][1].startswith(
        f"request-side check (R8): started in {stopped}, which the check stopped, and left no "
        "record")
    cont = sw.run("F-0", records=recs[k:], episode_ids=ids[k:])
    h = sw.compute(links={cont: stopped})
    assert h["status"] == hh.FINAL
    assert sum(e["excluded_request_check"] for e in h["exclusions"]) == 2
    assert h["h1"]["cells"]["F-0 NR"]["n"] == T - 1
    # the RUN_STOPPED keys and the abandoned one count their continuation's final record
    runs_ = {r["run_id"]: r["records_counted"] for r in h["inputs"]["runs"]}
    assert runs_[stopped] == k and runs_[cont] == len(ids) - k - 2
    assert all(e["pending"] == 0 for e in h["exclusions"])
    # not to be found: every planned episode has a record, or no plan was recorded
    for over in ({"episode_ids": ids}, {"episode_ids": None}):
        bad = HaikuSweep(tmp_path / f"bad{len(over['episode_ids'] or [])}")
        bad.standard(skip={("F-0", BASE)})
        bad.run("F-0", exit_reason=STOP, **over)
        with pytest.raises(hh.Refusal, match="the episode it stopped at cannot be found"):
            bad.compute()
    # the named episode has a record: the run's meta.json and records disagree
    odd = HaikuSweep(tmp_path / "odd")
    odd.standard(skip={("F-0", BASE)})
    odd.run("F-0", records=recs[:k + 1], exit_reason=STOP, episode_ids=ids,
            parallel={"episodes_started": k + 2, "stop_reason": f"{STOP} in episode {ids[k]}"})
    with pytest.raises(hh.Refusal, match="cannot be found"):
        odd.compute()
