"""H5 on ARC: the Adapter advantage by level depth (PREREG §3 H5, D35; §17.6 change 4; §17.5).

Run: ``uv run python -m analysis.arc_h5 [--results-root DIR] [--published DIR]
[--data {both,published,ours}] [--boot N] [--no-exploratory] [--out-dir DIR] [--no-write]
[--allow-incomplete]`` ($0: it reads committed files only). It writes
``<results root>/arc_h5/<UTC>/h5.json``, ``summary.md`` and ``meta.json``, and prints the
summary. Everything here is descriptive: H5 is outside the Holm family (§9.4, PLAN §10 [A7]),
and no significance claim is made.

**The hypothesis** (§3 H5): the Adapter's advantage in P(clear level ℓ | reached ℓ) is larger
at levels ≥ 4 than at levels 1-2. Tested on the published runs first, then on ours.

**Inputs** (all under the results root, default ``results/``, except ``--published``):

* **Published runs (data a):** ``<published>/per_run.csv`` and ``<published>/meta.json``, by
  default ``<results root>/arc_public_ops/20261001T185155Z`` (`PUBLISHED_SLICE`: PR #17's
  slice, cited by PREREG §7.6-§7.8; its ``per_run.csv`` is byte-identical to the
  ``20261001T035436Z`` slice's). Only the columns in `PUBLISHED_FIELDS` are read. The file's
  sha256 is pinned (`PUBLISHED_SHA256`); another file is read, and the output is PROVISIONAL.
  The slice's ``meta.json`` must be an ``arc_public_ops`` run whose ``slice`` says "no H5
  quantities". The registered selection is effort ``high``, harness ``standard`` and
  ``provider_adapter``: exactly 25 games and one run per (game, harness), every run's
  ``config_matches_variant`` true. Nothing is read from ``results/raw/``.
* **Our runs (data b):** the 8 seed-1 counted S0 and S4 runs on the 4 path games (§17.6 change
  4), found from the ``arc_path`` folders with ``analysis.checkpoint_c``'s code (imported, not
  copied), as ``analysis.arc_h4.load`` does but restricted to `CONFIGS` = S0, S4 so that S2's
  state cannot block H5: ``discover``, ``check_links`` (inconsistent chains anywhere refuse, S1
  and S2 included; a pilot folder is refused), ``d20_check``, ``rerun_eligible`` and
  ``resolve_unit``. A seed-101 re-run replaces its original (FT09 S0's counted run is its
  re-run). S1 and S2 runs are not in H5 (R6 change 4) and are listed. ``costs.csv``: the ARC
  pilot rows' ``latency_s`` only (D20's yardsticks). ``draw/*/draw.json``: the 4 path games (in
  draw order) and SEED (D15); it is read for SEED even with ``--data published``.

**Units, rows and definitions** (§3 H5 Operational, D35). One row per (run, level ℓ) reached:
reached(ℓ) iff ``level_actions[ℓ] > 0`` (RESETs included, as ARC's scorecard counts them);
cleared(ℓ) iff ℓ ≤ ``levels_completed``. Bands: early = levels 1-2, deep = levels ≥ 4 (4-10
pooled); level 3 is reported in the raw tables only. The level a run ended on is
``levels_completed + 1`` if the run did not win, and it is a row only if it was reached. The
level in play when the action budget or the 12 h clock ended a run counts as reached and not
cleared if the run took at least one action on it (D35; R5, "Not H5"); with none it is not a
row. Published ``final_level`` is never used (for a WIN it is the last, cleared, level).

**The model** (§3 H5, PLAN §10, §9.9): ``cleared ~ harness × band + game fixed effects`` on the
early and deep rows, written as one indicator per game cluster and three cell indicators
(Adapter-early, Standard-deep, Adapter-deep; Standard-early is the reference). A_b, the
Adapter-minus-Standard difference in P(clear | reached) in band b, is the average marginal
effect over every reached row of the band, both harnesses: A_b = Σ_g (n_gb / n_b) Δ_gb with
Δ_gb = p̂(g, Adapter, b) − p̂(g, Standard, b), so a game weighs by its reached level-rows in the
band. C = A_deep − A_early. A band in which one harness has no row is not estimable, and its
A_b, C and the verdict are undefined. The logit-scale interaction γ_Ad − γ_Sd − γ_Ae is
reported too (§9.3), and no reading rests on it.

**Estimators** (separation is expected here, not exceptional). Both are computed on every
registered reading and resample and both are reported; the rule `PRIMARY_ESTIMATOR` decides
the verdict and the headline interval.

* ``firth``: Firth's penalized logit, ``analysis.persistgym_h1h3.firth_fe_logit`` (the fit
  H1's model check reads where its ordinary fit is not finite), on every game's early and deep
  rows; where it returns None, `firth_line_search` maximizes the same penalized
  log-likelihood (below, "where this differs from the spec"). Undefined if the design is not
  of full rank or neither converges. The penalty moves every estimate, also where the ordinary
  fit is finite and unique.
* ``ml_limit``: the limit of the maximum-likelihood fit (Geyer 2009's limiting conditional
  model). An LP (``scipy.optimize.linprog``, HiGHS) finds the maximal set of rows separated by
  a recession direction; their fitted values go to their outcomes; damped Newton (pinv steps)
  fits the rest. Each prediction an AME needs is the observed pattern's value, or, for a
  counterfactual pattern (a harness that never reached the band in that game), the LCM's value
  if the pattern lies in the LCM's row space, else 0 or 1 if its linear predictor goes to
  ∓∞ along every likelihood-maximizing sequence, else "not identified" (the limit depends on
  the path). statsmodels' stopping point (``persistgym_h1h3.sm_fe_logit``) is a cross-check
  on the point estimate: a difference above 1e-6 where the limit is identified is a warning.
* Rule ``ml_limit_or_firth`` (the proposed rule in force; RULING, below): the ML limit where
  C is identified (or a band is not estimable, so no estimator gives C), else Firth for both
  bands of that reading or resample (counted, by the ML limit's reason: "not identified in
  the ML limit", or a failed ML fit). Rule ``firth`` (the alternative, not in force unless
  ruled): Firth everywhere.

**Bootstrap:** game-cluster, `N_BOOT` = 10,000 resamples, ``numpy.random.default_rng(SEED +
40)``, ``integers(0, n, size=(boot, n))``, a fresh generator for every reading (so the
primary and its error sensitivity use the same draws). Each drawn game is its own cluster with
its own fixed effect (``"<game>#<j>"``). Percentile 90% intervals (``numpy.quantile`` at 0.05
and 0.95), each over the resamples where its quantity is defined; the others are counted by
reason. Also reported: the fraction of defined resamples with C ≤ 0 (exploratory: descriptive,
not a test; H5 registers no such fraction), and the distinct possible resamples,
C(2n − 1, n) (35 for our 4 games), and drawn.

**Readings.** Registered: the published runs at high effort and our S0/S4 runs, each with the
error-ending sensitivity (§3 H5: the reached level a run ended on, when its ending is an
error, is dropped; budget endings keep theirs). Exploratory (§9.10), skipped with
``--no-exploratory``: the published runs at medium and low effort, and a common-support
reading (the games where both harnesses reached a deep level). Other models: not computed.

**Status.** FINAL with 10,000 resamples, the pinned published file and complete units for
the data sets read; PROVISIONAL otherwise (``provisional_reasons``). **Refusals** (exit 2,
``H5 refused: <reason>``): a missing or unreadable slice, the wrong slice, missing columns, a
registered selection that is not 25 games × 2 harnesses × 1 run, ``config_matches_variant``
false, a failed consistency check at the registered effort (at an exploratory effort the
effort is skipped with a warning); for ours, a draw that is not one file of 4 games, no
``costs.csv``, inconsistent chains, a pilot folder, a failed consistency check, an ending
outside the maps, and (without ``--allow-incomplete``) a unit without a counted run it can
use. With ``--allow-incomplete`` our reading is PROVISIONAL: raw tables only, a pending
re-run's original standing in (flagged), no model, contrast or bootstrap.

**Outputs** are built from allowlists (`TOP_FIELDS`, `READING_FIELDS`, `OURS_RUN_FIELDS`,
`OUTPUTS`): no transcript path, key, token count or other ``meta.json`` field is copied.

**As implemented.** Claude's readings of PREREG, for the researcher's review; none changes a
hypothesis, prediction or threshold.

*Readings of PREREG made here:*

1. **Estimators under separation** (RULING, below). Both are computed and reported; the
   proposed rule in force is ``ml_limit_or_firth``.
2. **The AME is bounded under separation.** A_early's ML limit is unique whenever both runs
   of every game reached level 1 (their early patterns are then observed); only a
   counterfactual deep prediction can be not identified, and then A_deep's ML limit is
   reported as not identified. statsmodels' stopping point is a cross-check, never the
   estimate.
3. **No game is dropped** and there is no D25-style rule (D25 is §9.1's, for PersistGym).
   Under the ML limit, and so under the rule in force wherever C is identified, a game whose
   reached rows are all cleared, or none, adds exactly 0 wherever its counterfactual is
   identified (H3 reading 15's "adds 0", without a special rule). Firth keeps every game,
   finite, and gives such a game a small non-zero Δ (the penalty's pull towards 1/2).
4. **Structural absence:** a band in which one harness has no reached row in the reading or
   resample is not estimable; its A_b and C are undefined ("Standard reached no deep level")
   and the verdict reads "cannot be computed". A_early is still reported.
5. **The AME's rows:** every reached (run, level) row of band b, both harnesses; a game's
   weight is its number of reached level-rows in the band. Per-game contributions and weights
   are reported, with the share of A_deep's weight in games where only one harness reached
   deep (`extrapolated_share_deep`).
6. **Games where one harness never reached deep** stay in the primary A_deep through the
   model's counterfactual for the absent harness (the literal model-based AME). A
   common-support reading (both harnesses reached a deep level) is added as exploratory, and is
   not computed with fewer than 2 such games.
7. **Undefined resamples** are left out of that quantity's interval and counted by reason
   (H1/H3 reading 9; H4's G = 0 rule); the summary says each interval is conditional on the
   quantity being defined. "C ≤ 0" in the fraction reported (exploratory, descriptive, not a
   test) uses the verdict's tolerance (C ≤ 1e-9).
8. **Bootstrap mechanics** as above. Each resample's drawn games are taken in sorted order
   (the estimates do not depend on the clusters' order), so a resample's result is a function of
   its sorted index tuple and is memoized. Games: alphabetical for the published runs, draw
   order for ours.
9. **Seed** (RULING, below): SEED + 40.
10. **Level 3** is in the raw band and per-level tables only; its rows are left out of the
    model fit, whose registered band variable has only early and deep (a three-band fit,
    not chosen, would change the game intercepts slightly).
11. **Raw rates:** P(clear | reached) by harness, per band and per level (the per-level table
    is the registered "hypothesis slice" output, PLAN §8.1, §16.3; PREREG §7.8, printed for
    every effort read), and the raw pooled contrast (r_Ad − r_Sd) − (r_Ae − r_Se) with the
    same bootstrap, labelled "exploratory: no game adjustment, not the registered model".
12. **Cleared for a won run:** cleared(ℓ) iff ℓ ≤ ``levels_completed``; a won run cleared every
    level and ended on no uncleared level. Published: state WIN iff ``levels_completed`` =
    ``level_count`` (refused otherwise); ours: GAME_WIN iff every level cleared (a flag only).
13. **Reached** is ``level_actions[ℓ] > 0`` exactly (D35), RESETs included: a level whose only
    action was a RESET counts as reached.
14. **Error-ending sensitivity:** only the reached level a run ended on, and only if its ending
    is an error: published ``ERROR_OR_CLOSED`` (inferred); ours ``API_ERROR``, ``AGENT_ERROR``,
    ``UNKNOWN``, ``SCORECARD_CLOSED`` (``checkpoint_c.ERROR_ENDINGS``). Kept as budget endings:
    ``ACTION_BUDGET``, ``TIME_BUDGET`` (also a D20-incident ``TIME_BUDGET`` counted as is: D20
    is a re-run rule, not an H5 rule) and ``COST_CAP`` (the $120 guard; flagged). Same seed,
    so the resamples are paired.
15. **Published input:** the pinned slice above; another file marks the output PROVISIONAL.
16. **Other efforts and models:** medium and low are exploratory (§9.10): the rule in force
    (with the estimators it needs), raw band and per-level tables and bootstrap, sign only, no
    verdict sentence, no error sensitivity; a data problem at an exploratory effort skips it
    with a warning. Other models: not computed (the committed pull has Gemini 3.8 Flash only).
17. **Our runs:** the counted S0 and S4 run of each path game at replicate 1 (above). No
    reading on FT09 S0's replaced seed-1 original: H5 registers no originals analysis, and
    H4's is H4's own. It is listed in the run table, which gives every run's
    ``agent_exit_reason`` and ``exit_reason`` next to its D19 ending (§9.9).
18. **Verdict:** on the primary estimator's point estimate: C > 1e-9 "positive ... as H5
    predicts (descriptive)"; C ≤ 1e-9, ties included, "not positive ... against H5's
    prediction (descriptive)"; undefined "cannot be computed". The other estimator's sign is
    shown and a disagreement flagged. Exploratory readings give the sign only.
19. **Logit scale:** the interaction for each estimator with its bootstrap interval (§9.3), "not
    finite in the ML limit" where applicable; a sign disagreement with C is flagged.
20. **Status and refusals** follow ``analysis.arc_h4`` (above).
21. **Real-data tests** assert counts and run IDs only (the blind rule): the pinned hash, 25
    games × 2 harnesses × 1 run per effort (read with ``csv`` on the effort, game and harness
    columns), and the 8 counted run IDs (resolved with ``checkpoint_c`` directly, so no code
    of this module that reads levels runs on real data).
22. **Runtime:** about 2 minutes per published-size reading at 10,000 resamples with both
    estimators on synthetic data (1.9 minutes in the statistics review). Under
    ``ml_limit_or_firth`` the exploratory readings compute both estimators too, so a full run
    (5 readings of the published size, the common-support readings and ours) should take
    about 10-15 minutes (an estimate, not measured); progress goes to stderr.

*Where this differs from the spec it was written from* (Claude's, for the researcher's
review; neither changes the spec's reference values in its §12):

A. **Which ML-limit counterfactuals are identified.** The spec's test for a counterfactual
   prediction outside the LCM's row space accepted only x − x_s in the row space for one
   separated pattern x_s, and called everything else "not identified". That test is
   sufficient, not necessary: a linear predictor also has a path-independent infinite limit
   when x = u + Σ λ_j s_j x_j with u in the LCM's row space, λ ≥ 0 and s_j the separated
   patterns' signs (then x·θ → +∞ along every maximizing sequence; by Farkas' lemma, when
   neither x nor −x has such a form, two maximizing sequences give different limits). The
   module keeps the spec's test as a fast path and adds this one (an LP feasibility check,
   `MLLimit.limit`). On random synthetic sets it identifies band AMEs that the spec's test
   leaves "not identified", and statsmodels' stopping point agrees with each identified value
   (tests: one hand-checked case, and the 200-set property test). So the spec's simulation
   figures for how often the ML limit is not identified overstate it under this test.
B. **Firth when firth_fe_logit does not converge.** On some synthetic sets
   ``persistgym_h1h3.firth_fe_logit`` returns None although Firth's estimate exists (the
   penalized log-likelihood of a full-rank logit has a finite maximum): its full scoring steps
   settle into a 2-cycle around the maximum, and "does not decrease" accepts every step (on
   the 2-game set of the tests the penalized log-likelihood is already at its maximum). The
   spec reads None as "Firth did not converge", which would leave such resamples out of the
   proposed primary's intervals for a reason unrelated to the data. The module calls
   firth_fe_logit first, as the spec says, and where it returns None runs
   `firth_line_search`: the same objective and the same steps with an Armijo line search,
   checked against an independent maximization in the tests. Each use is counted
   (``optimizer`` on the point estimate, ``n_line_search`` in the bootstrap). firth_fe_logit
   itself is not changed (H1's FINAL output used it, and there it converged, checked against
   an independent maximization). It is not rare under the heavy separation expected in H5's
   data: in uncommitted synthetic checks made while building this module, a large share of
   the Firth fits on heavily separated 25-game sets came from `firth_line_search`, and on
   milder synthetic data it was rarely used. Its agreement with an independent maximization
   is what the tests check; the output counts its uses on the real data.

*For the researcher's ruling* (proposed by Claude, not yet ruled; the ``results/decisions.md``
entry "H5 analysis: two rulings proposed before any H5 quantity is computed" of 2026-10-10
states both, and the researcher's merge of the pull request that adds it adopts them):

1. **The primary estimator** (`PRIMARY_ESTIMATOR`): proposed ``"ml_limit_or_firth"``. PREREG
   §3 H5 registers a logistic regression, whose reading is maximum likelihood; the ML limit is
   that fit's value wherever C is identified, also under separation (reading 2), and H1's
   ruling of 2026-10-10 is of this form: "When the logit-scale Δ_H1 is finite, the ordinary
   fit decides as before", with Firth only where it is not. Here Firth decides only a
   reading or resample whose C the ML limit does not identify (or whose ML fit fails), and
   each such resample is counted by reason. Its cost: the percentile interval mixes the two
   estimators across resamples (it is the interval of the rule, a statistic of its own), and
   the ML limit puts separated cells at exactly 0 or 1. The alternative, ``"firth"``, is
   implemented and switchable: always finite where the band is estimable (with
   `firth_line_search` where firth_fe_logit cycles, item B above) and one estimator in the
   point estimate and every resample; but it is not H1's rule, it changes the registered ML
   estimate even on data without separation, and it gives a game with no outcome variation a
   non-zero Δ (reading 3). With 4 games the choice can change C's size and sign (tests: on
   design SIX_SEP A_deep is +0.200 under Firth and +0.282 in the ML limit; on design FLIP, 4
   games without separation, so that the ML limit is the ordinary ML fit, C is +0.001 under
   Firth and −0.008 in the ML limit). The rule in force is named in the summary and
   ``meta.json``, and both estimators are always reported.
2. **The bootstrap seed:** SEED + 40, the next free offset (used: +2, +3 run orders; +10 the
   H1/H3 bootstrap; +11 the Bayesian GLMM; +20 the failure labels; +30 H4). A reading, not an
   amendment, fixed before any real H5 run.

It never prints an outcome unless it is run; it was written and tested on synthetic data only,
before any H5 quantity was computed on real data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from scipy import linalg, optimize, special

from analysis import arc_action_matched as am
from analysis import checkpoint_c as cc
from analysis import persistgym_h1h3 as h13
from arc.public import sessions
from common import costs, runmeta

REPO_ROOT = runmeta.REPO_ROOT
RESULTS = REPO_ROOT / "results"
EXPERIMENT = "arc_h5"
REGISTERED_EFFORT = "high"                 # §3 H5, D35, §7.8
EXPLORATORY_EFFORTS = ("medium", "low")    # §9.10
HARNESSES = ("standard", "provider_adapter")
HARNESS_NAME = {"standard": "Standard", "provider_adapter": "Adapter"}
EARLY = (1, 2)                             # §3 H5: early = levels 1-2
LEVEL_3 = 3                                # reported, left out of the contrast
DEEP_MIN = 4                               # deep = levels >= 4
BANDS = ("early", "level_3", "deep")
MODEL_BANDS = ("early", "deep")
CELLS = ("Se", "Ae", "Sd", "Ad")           # index 2 × deep + adapter; Se is the reference
N_BOOT = 10_000
BOOT_SEED_OFFSET = 40                      # SEED + 40 (RULING; module docstring)
LEVEL = 0.90
QUANTILES = (0.05, 0.95)                   # percentile 90% interval
POSITIVE_TOL = 1e-9                        # C > 1e-9 reads "positive"
SM_TOL = 1e-6                              # statsmodels vs the ML limit: warn above
PUBLISHED_SLICE = "arc_public_ops/20261001T185155Z"
PUBLISHED_SHA256 = "ad34bec8bb88de5283e9c823fd75743393a03d961c8766d305201633d6b24d44"
PUBLISHED_EXPERIMENT = "arc_public_ops"
PUBLISHED_SLICE_MARK = "no H5 quantities"
N_PUBLISHED_GAMES = 25
N_PATH_GAMES = 4
ESTIMATORS = ("firth", "ml_limit_or_firth")
PRIMARY_ESTIMATOR = "ml_limit_or_firth"    # RULING: proposed (module docstring)
RULE_TEXT = {"ml_limit_or_firth": ("the maximum-likelihood limit where C is identified, else "
                                   "Firth's penalized logit for that reading or resample"),
             "firth": "Firth's penalized logit throughout"}
RULING_ENTRY = "H5 analysis: two rulings proposed before any H5 quantity is computed"
CONFIGS = ("S0", "S4")                     # R6 change 4: S1 and S2 do not enter H5
HARNESS_OF_CONFIG = {"S0": "standard", "S4": "provider_adapter"}
REPLICATE = 1
COST_CAP = "COST_CAP"
QUANTITIES = ("A_early", "A_deep", "contrast", "logit_interaction")
DATA_CHOICES = ("both", "published", "ours")
FINAL, PROVISIONAL = cc.FINAL, cc.PROVISIONAL
OTHER_MODELS = ("not computed: the committed pull has Gemini 3.8 Flash only (results slug "
                "google-gemini-3-8-flash, 150 sessions)")

# numerical settings of the ML limit (module docstring)
SV_REL_TOL = 1e-9          # singular values kept for a row-space basis, relative to the largest
ROWSPACE_TOL = 1e-8        # residual norm < 1e-8 × max(1, |x|): x is in the row space
NEWTON_TOL = 1e-10         # LCM fit: stop when max |step| < 1e-10
NEWTON_MAX_ITER = 200
PINV_RCOND = 1e-12
LP_SEPARATED = 0.5         # t_i > 0.5: row i is separated
FIRTH_MAX_ITER = 1000      # `firth_line_search`, as firth_fe_logit's cap
FIRTH_TOL = 1e-7           # `firth_line_search`: converged when max |full step| < 1e-7
FIRTH_ARMIJO = 1e-4        # `firth_line_search`: sufficient increase
FIRTH_FLOOR = 1e-10        # `firth_line_search`: gain left below 1e-10 × |value| is converged
FIRTH_OPTIMIZERS = ("persistgym_h1h3.firth_fe_logit", "firth_line_search")

PUBLISHED_ENDING_KIND = {sessions.GAME_WIN: "win", sessions.ACTION_BUDGET: "budget",
                         sessions.TIME_BUDGET: "budget", sessions.ERROR_OR_CLOSED: "error"}
OURS_ENDING_KIND = {"GAME_WIN": "win", "ACTION_BUDGET": "budget", "TIME_BUDGET": "budget",
                    COST_CAP: "budget", **dict.fromkeys(cc.ERROR_ENDINGS, "error")}

VERDICT_POSITIVE = ("positive: A_deep − A_early > 0 on the point estimate, as H5 predicts "
                    "(descriptive)")
VERDICT_NOT_POSITIVE = ("not positive: A_deep − A_early ≤ 0 on the point estimate, against "
                        "H5's prediction (descriptive)")
CANNOT = "cannot be computed"
RAW_LABEL = "exploratory: no game adjustment, not the registered model"
FRACTION_LABEL = "Fraction C ≤ 0 (descriptive, not a test)"

PUBLISHED_FIELDS = ("game", "game_id", "harness", "effort", "config", "config_matches_variant",
                    "guid", "state", "levels_completed", "level_count", "total_actions",
                    "final_level", "final_level_actions", "final_level_baseline",
                    "final_level_budget", "duration_h", "level_actions", "level_baselines",
                    "inferred_ending")
"""The only per_run.csv columns read."""

TOP_FIELDS = ("generated_utc", "git_commit", "git_dirty", "prereg_version", "status",
              "provisional_reasons", "warnings", "inputs", "settings", "seed", "bootstrap_seed",
              "primary_estimator", "published", "published_exploratory", "ours", "ours_runs",
              "skipped")
READING_FIELDS = ("label", "data", "registered", "effort", "harnesses", "games", "n_games",
                  "n_runs", "n_rows", "raw", "per_level", "per_game", "deep_support",
                  "extrapolated_share_deep", "estimates", "primary",
                  "other_estimator_sign_agrees", "bootstrap", "sensitivity_error_endings",
                  "common_support")
SENSITIVITY_FIELDS = (*READING_FIELDS, "dropped_rows")
ESTIMATE_FIELDS = ("A_early", "A_deep", "contrast", "logit_interaction", "defined",
                   "why_undefined")
OURS_RUN_FIELDS = ("run_id", "game", "config", "harness", "replicate", "seed", "rerun_of",
                   "replaced_by", "counted", "in_reading", "agent_exit_reason", "exit_reason",
                   "d19_ending", "ending_kind", "rerun_eligible", "level_count",
                   "levels_completed", "level_actions", "last_reached_level", "ended_level",
                   "dropped_in_sensitivity", "flags")
OUTPUTS = ("h5.json", "summary.md")

Progress = Callable[[str, int, int], None]


class Refusal(ValueError):
    """Inputs H5 cannot be computed from (exit 2)."""


# --- runs and rows ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RunLevels:
    """One run's per-level record, from either data set."""
    source: str                    # "published" or "ours"
    run_id: str                    # the session guid, or our run ID
    game: str
    harness: str                   # "standard" or "provider_adapter"
    label: str                     # the config tag, or S0/S4
    effort: str | None
    level_count: int
    levels_completed: int
    level_actions: tuple[int, ...]
    ending: str
    ending_kind: str               # "win", "budget" or "error"
    total_actions: int

    @property
    def ended_level(self) -> int | None:
        """The level the run ended on: the one after its last cleared level, or None for a won
        run (it cleared every level)."""
        return self.levels_completed + 1 if self.levels_completed < self.level_count else None

    @property
    def last_reached_level(self) -> int | None:
        reached = [i + 1 for i, a in enumerate(self.level_actions) if a > 0]
        return reached[-1] if reached else None


@dataclass(frozen=True)
class Row:
    """One reached (run, level)."""
    game: str
    harness: str
    adapter: int
    level: int
    band: str
    cleared: int
    run_id: str
    ended_here: bool
    ended_by_error: bool


def band_of(level: int) -> str:
    if level in EARLY:
        return "early"
    return "level_3" if level == LEVEL_3 else "deep"


def level_rows(run: RunLevels) -> list[Row]:
    """One row per reached level (D35: at least one action on it)."""
    out = []
    ended = run.ended_level
    for level in range(1, run.level_count + 1):
        if run.level_actions[level - 1] <= 0:
            continue
        here = level == ended
        out.append(Row(game=run.game, harness=run.harness,
                       adapter=int(run.harness == "provider_adapter"), level=level,
                       band=band_of(level), cleared=int(level <= run.levels_completed),
                       run_id=run.run_id, ended_here=here,
                       ended_by_error=here and run.ending_kind == "error"))
    return out


def _consistency(level_actions: tuple[int, ...], baselines_len: int, level_count: int,
                 total: int, levels_completed: int) -> str | None:
    """§1.1's checks 1-5 (shared by both data sets): the first that fails, or None."""
    if not (len(level_actions) == baselines_len == level_count) or level_count < 1:
        return (f"check 1: {len(level_actions)} level actions and {baselines_len} baselines "
                f"against level_count {level_count}")
    if sum(level_actions) != total:
        return f"check 2: the level actions sum to {sum(level_actions)}, not {total}"
    if not 0 <= levels_completed <= level_count:
        return f"check 3: levels_completed {levels_completed} outside 0..{level_count}"
    if any(a <= 0 for a in level_actions[:levels_completed]):
        return "check 4: a cleared level has no action"
    if any(a != 0 for a in level_actions[levels_completed + 1:]):
        return "check 5: actions after the level in play"
    return None


# --- the published runs (data a) ---------------------------------------------------------------

@dataclass
class Published:
    slice_dir: Path
    per_run: Path
    sha256: str
    pinned: bool
    runs: dict[str, list[RunLevels]]     # effort -> runs in reading order
    skipped: dict[str, str]              # exploratory effort -> why it was skipped
    warnings: list[str]


def read_slice(slice_dir: Path) -> tuple[list[dict], str]:
    """The allowlisted rows of the slice's per_run.csv and the file's sha256. Refuses a missing
    or unreadable file, the wrong slice and missing columns."""
    per_run, meta_path = slice_dir / "per_run.csv", slice_dir / "meta.json"
    for p in (per_run, meta_path):
        if not p.is_file():
            raise Refusal(f"no {p.name} in {slice_dir}")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Refusal(f"cannot read {meta_path}: {e}") from None
    if not isinstance(meta, dict) or meta.get("experiment") != PUBLISHED_EXPERIMENT:
        got = meta.get("experiment") if isinstance(meta, dict) else None
        raise Refusal(f"{meta_path}: experiment {got!r}, not {PUBLISHED_EXPERIMENT!r}")
    if PUBLISHED_SLICE_MARK not in str(meta.get("slice") or ""):
        raise Refusal(f"{meta_path}: slice {meta.get('slice')!r} does not say "
                      f"{PUBLISHED_SLICE_MARK!r}")
    try:
        data = per_run.read_bytes()
        text = data.decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise Refusal(f"cannot read {per_run}: {e}") from None
    reader = csv.DictReader(io.StringIO(text, newline=""))
    missing = [f for f in PUBLISHED_FIELDS if f not in (reader.fieldnames or [])]
    if missing:
        raise Refusal(f"{per_run} lacks the columns {', '.join(missing)}")
    rows = [{k: (r[k] or "").strip() for k in PUBLISHED_FIELDS} for r in reader]
    return rows, hashlib.sha256(data).hexdigest()


def _truth(v: str) -> bool | None:
    return {"true": True, "1": True, "false": False, "0": False}.get(v.strip().lower())


def published_run(r: dict) -> RunLevels:
    """One published run, after §1.1's checks 1-7. Raises Refusal naming the run."""
    who = f"run {r['guid']} ({r['game']} {r['harness']}, effort {r['effort']})"
    try:
        la = tuple(int(x) for x in r["level_actions"].split())
        lb = tuple(int(x) for x in r["level_baselines"].split())
        n, lc, total = int(r["level_count"]), int(r["levels_completed"]), int(r["total_actions"])
        duration_s = float(r["duration_h"]) * 3600
    except ValueError as e:
        raise Refusal(f"{who}: cannot parse its levels ({e})") from None
    bad = _consistency(la, len(lb), n, total, lc)
    if bad is None and (r["state"] == "WIN") != (lc == n):
        bad = f"check 6: state {r['state']} with {lc} of {n} levels completed"
    ending = r["inferred_ending"]
    if bad is None:
        if ending not in PUBLISHED_ENDING_KIND:
            raise Refusal(f"{who}: inferred_ending {ending!r} is outside the ending map")
        i = min(lc, n - 1)
        again = sessions.infer_ending(r["state"], la[i], sessions.level_budget(lb[i]),
                                      duration_s)
        if again != ending:
            bad = f"check 7: inferred_ending {ending}, re-derived {again}"
    if bad is not None:
        raise Refusal(f"{who}: {bad}")
    return RunLevels(source="published", run_id=r["guid"], game=r["game"], harness=r["harness"],
                     label=r["config"], effort=r["effort"], level_count=n, levels_completed=lc,
                     level_actions=la, ending=ending, ending_kind=PUBLISHED_ENDING_KIND[ending],
                     total_actions=total)


def select_published(rows: list[dict], effort: str) -> tuple[list[RunLevels], list[str]]:
    """The runs of one effort, checked (selection and per-run checks), in reading order (games
    alphabetical, Standard first); and flags. Raises Refusal on a failed check."""
    sel = [r for r in rows if r["effort"] == effort and r["harness"] in HARNESSES]
    games = sorted({r["game"] for r in sel})
    pairs = Counter((r["game"], r["harness"]) for r in sel)
    problems = []
    if len(games) != N_PUBLISHED_GAMES:
        problems.append(f"{len(games)} games, not {N_PUBLISHED_GAMES}")
    dup = sorted(k for k, v in pairs.items() if v > 1)
    if dup:
        problems.append("more than one run of " + ", ".join(f"{g} {h}" for g, h in dup))
    gap = [(g, h) for g in games for h in HARNESSES if (g, h) not in pairs]
    if gap:
        problems.append("no run of " + ", ".join(f"{g} {h}" for g, h in gap))
    off = [r["guid"] for r in sel if _truth(r["config_matches_variant"]) is not True]
    if off:
        problems.append("config_matches_variant is not true for " + ", ".join(off))
    if problems:
        raise Refusal(f"effort {effort}: " + "; ".join(problems))
    runs = [published_run(r) for r in sorted(sel, key=lambda r: (r["game"],
                                                                   HARNESSES.index(r["harness"])))]
    flags = [f"run {x.run_id} ({x.game} {x.harness}, effort {effort}) took no action: it "
             "contributes no rows" for x in runs if x.total_actions == 0]
    return runs, flags


def load_published(slice_dir: Path, exploratory: bool) -> Published:
    rows, sha = read_slice(slice_dir)
    runs, skipped, warnings = {}, {}, []
    runs[REGISTERED_EFFORT], flags = select_published(rows, REGISTERED_EFFORT)
    warnings += flags
    for effort in EXPLORATORY_EFFORTS if exploratory else ():
        try:
            runs[effort], flags = select_published(rows, effort)
            warnings += flags
        except Refusal as e:
            skipped[effort] = str(e)
            warnings.append(f"exploratory effort {effort} skipped: {e}")
    return Published(slice_dir=slice_dir, per_run=slice_dir / "per_run.csv", sha256=sha,
                     pinned=sha == PUBLISHED_SHA256, runs=runs, skipped=skipped,
                     warnings=warnings)


# --- our runs (data b) -------------------------------------------------------------------------

@dataclass
class Ours:
    draw_path: Path
    costs_csv: Path
    games: list[str]
    seed: int
    entries: list[cc.Entry]
    units: dict[tuple[str, str], cc.Unit]
    eligible: dict[str, bool | None]
    incomplete: list[str]
    warnings: list[str]
    bare: list[tuple[str, str]]
    runs: list[RunLevels]                  # in the reading: draw order, S0 before S4
    counted: list[str]                     # the counted runs among them (not stand-ins)
    flags: dict[str, list[str]] = field(default_factory=dict)


def read_draw(root: Path) -> tuple[Path, list[str], int]:
    """draw.json's path, path games (upper case, draw order) and SEED (D15)."""
    path = cc.the_draw(root)
    try:
        draw = json.loads(path.read_text(encoding="utf-8"))
        return path, [str(g).upper() for g in draw["games"]], int(draw["seed"]["seed"])
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise Refusal(f"cannot read the games and SEED from {path}: {e}") from None


def ours_run(e: cc.Entry) -> tuple[RunLevels, list[str]]:
    """Our counted run's levels after §1.2's checks (1-5 refuse; 6 flags)."""
    r = e.run
    who = f"run {e.run_id} ({e.game} {e.config})"
    la = tuple(int(a) for a in r.level_actions)
    bad = _consistency(la, len(r.level_baseline_actions), r.level_count, r.actions,
                       r.levels_completed)
    if bad is not None:
        raise Refusal(f"{who}: {bad}")
    ending = e.d19_ending
    if ending not in OURS_ENDING_KIND:
        raise Refusal(f"{who}: ending {ending!r} is outside the ending map")
    flags = []
    if (r.levels_completed == r.level_count) != (ending == "GAME_WIN"):
        flags.append(f"check 6: {r.levels_completed} of {r.level_count} levels completed with "
                     f"ending {ending} (flag only: the ending does not change what was cleared)")
    return RunLevels(source="ours", run_id=e.run_id, game=e.game,
                     harness=HARNESS_OF_CONFIG[e.config], label=e.config, effort=None,
                     level_count=r.level_count, levels_completed=r.levels_completed,
                     level_actions=la, ending=ending, ending_kind=OURS_ENDING_KIND[ending],
                     total_actions=r.actions), flags


def load_ours(root: Path) -> Ours:
    """The path games, SEED and each (game, S0/S4) unit's counted run, resolved as
    ``analysis.arc_h4.load`` does (restricted to S0 and S4). Raises Refusal, cc.Refusal or
    am.Refused."""
    draw_path, games, seed = read_draw(root)
    if len(games) != N_PATH_GAMES:
        raise Refusal(f"draw.json names {len(games)} path games, not {N_PATH_GAMES} (§7.2)")
    costs_csv = root / "costs.csv"
    if not costs_csv.is_file():
        raise Refusal(f"no costs.csv under {root} (the pilots' latency_s, for D20)")
    try:
        pilots = cc.pilot_latency(costs.read_rows(costs_csv))
    except ValueError as e:
        raise Refusal(f"cannot read {costs_csv}: {e}") from None
    entries, bare = cc.discover(root / cc.EXPERIMENT)
    cc.check_links(entries)
    d20 = {e.run_id: cc.d20_check(e, entries, pilots) for e in entries if not e.truncated}
    eligible = {e.run_id: cc.rerun_eligible(e, d20[e.run_id])
                for e in entries if not e.truncated}
    units: dict[tuple[str, str], cc.Unit] = {}
    incomplete: list[str] = []
    warnings: list[str] = [f"{name}: {why}" for name, why in bare]
    runs: list[RunLevels] = []
    counted: list[str] = []
    flags: dict[str, list[str]] = {}
    for g in games:
        for c in CONFIGS:
            u = cc.resolve_unit(entries, g, c, eligible, REPLICATE)
            units[(g, c)] = u
            if u.original is None:
                incomplete.append(f"{g} {c}: no seed-{REPLICATE} run yet")
                continue
            o = u.head
            gap = False
            if u.pending:
                gap = True
                incomplete.append(f"{g} {c}: {o.run_id} ended "
                                  f"{cc.why_ending(o, d20[o.run_id], eligible[o.run_id])}; "
                                  "its one re-run has not landed")
            elif u.head_rerun is None and eligible[o.run_id] is None:
                gap = True
                incomplete.append(f"{g} {c}: {o.run_id} ended TIME_BUDGET and its D20 check "
                                  "cannot be computed, so whether it is re-run is unknown")
            x, y = u.original, u.rerun
            if y is not None and eligible[x.run_id] is False:
                warnings.append(f"{g} {c}: {x.run_id} was re-run although its ending "
                                f"({cc.why_ending(x, d20[x.run_id], False)}) is final under "
                                "D19/D20 as computed here; the re-run still replaces it (§7.5)")
            e = u.counted
            if e.run is None:
                incomplete.append(f"{g} {c}: counted run {e.run_id} cannot be scored "
                                  f"({e.skip_reason})")
                continue
            if not e.run.checks_passed:
                warnings.append(f"{e.run_id}: fails analysis.arc_action_matched's checks (H5 "
                                "reads its levels only; flagged)")
            r = u.head_rerun
            if r is not None and eligible[r.run_id]:
                warnings.append(f"{g} {c}: re-run {r.run_id} also ended {r.d19_ending}, "
                                "re-run-eligible: it is counted as is, flagged (D19 allows no "
                                "second re-run)")
            run, f = ours_run(e)
            runs.append(run)
            flags[e.run_id] = f
            if gap:
                flags[e.run_id].append("stand-in: the unit lacks a counted run (PROVISIONAL)")
            else:
                counted.append(e.run_id)
    others = [e.run_id for e in entries if e.config not in CONFIGS and not e.truncated]
    if others:
        warnings.append(f"S1/S2 runs present ({', '.join(others)}): not in H5 (R6 change 4)")
    for e in entries:
        dd = d20.get(e.run_id)
        if e.config in CONFIGS and dd and not dd["readings_agree"]:
            warnings.append(f"{e.run_id}: D20 readings disagree (as of its start: incident "
                            f"{dd['as_of_start']['incident']}; on the final counted set: "
                            f"{dd['final_counted_set']['incident']}); the as-of reading is "
                            "used")
    return Ours(draw_path=draw_path, costs_csv=costs_csv, games=games, seed=seed,
                entries=entries, units=units, eligible=eligible, incomplete=incomplete,
                warnings=warnings, bare=bare, runs=runs, counted=counted, flags=flags)


# --- the model: design, Firth and the maximum-likelihood limit ----------------------------------

@dataclass(frozen=True)
class ModelRows:
    """The early and deep rows of a reading or resample, as arrays."""
    codes: np.ndarray        # cluster code 0..G-1 of each row
    cell: np.ndarray         # CELLS index of each row
    y: np.ndarray            # cleared (0.0 or 1.0)
    clusters: tuple[str, ...]

    @property
    def n_clusters(self) -> int:
        return len(self.clusters)


def cell_index(adapter: int, band: str) -> int:
    return 2 * MODEL_BANDS.index(band) + adapter


def model_rows(clusters: list[str], cells: list[int], ys: list[float]) -> ModelRows:
    """Cluster codes in the order the clusters first appear."""
    labels: dict[str, int] = {}
    codes = [labels.setdefault(c, len(labels)) for c in clusters]
    return ModelRows(np.asarray(codes, dtype=int), np.asarray(cells, dtype=int),
                     np.asarray(ys, dtype=float), tuple(labels))


def rows_to_model(rows: list[Row]) -> ModelRows:
    keep = [r for r in rows if r.band in MODEL_BANDS]
    return model_rows([r.game for r in keep], [cell_index(r.adapter, r.band) for r in keep],
                      [float(r.cleared) for r in keep])


class Design:
    """η(g, cell) = α_g + γ_cell: one column per cluster, one per cell present other than the
    reference (Standard-early, or the first cell present when it has no row)."""

    def __init__(self, m: ModelRows):
        self.m = m
        self.present = sorted(set(m.cell.tolist()))
        self.col = {c: m.n_clusters + i for i, c in enumerate(self.present[1:])}
        self.p = m.n_clusters + len(self.col)

    def x(self, g: int, c: int) -> np.ndarray:
        v = np.zeros(self.p)
        v[g] = 1.0
        if c in self.col:
            v[self.col[c]] = 1.0
        return v

    def z(self) -> np.ndarray:
        """The cell columns, row by row (the slopes of `firth_fe_logit` and `sm_fe_logit`)."""
        cols = sorted(self.col, key=self.col.get)
        if not cols:
            return np.zeros((len(self.m.y), 0))
        return np.column_stack([(self.m.cell == c).astype(float) for c in cols])

    def interaction(self) -> np.ndarray | None:
        """γ_Ad − γ_Sd − γ_Ae + γ_Se as a contrast of the coefficients; None without all four
        cells."""
        if len(self.present) < len(CELLS):
            return None
        v = np.zeros(self.p)
        for c, w in ((3, 1.0), (2, -1.0), (1, -1.0), (0, 1.0)):
            if c in self.col:
                v[self.col[c]] += w
        return v

    def patterns(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """The distinct (cluster, cell) patterns: keys (4g + cell), design rows, successes and
        counts."""
        key = self.m.codes * len(CELLS) + self.m.cell
        uniq, inv = np.unique(key, return_inverse=True)
        k = np.bincount(inv, weights=self.m.y, minlength=len(uniq))
        n = np.bincount(inv, minlength=len(uniq)).astype(float)
        x = np.array([self.x(int(u) // len(CELLS), int(u) % len(CELLS)) for u in uniq])
        return uniq, x.reshape(len(uniq), self.p), k, n


def separated_patterns(x: np.ndarray, k: np.ndarray, n: np.ndarray) -> np.ndarray | None:
    """The maximal set of patterns (rows grouped by design row) separated by a recession
    direction, from one LP: maximize Σ t_j subject to t_j ≤ s_j x_j·d and t_j in [0, 1] for
    the patterns whose rows all have one outcome (s_j = +1 if cleared, else −1), and x_j·d = 0
    for the patterns with both outcomes (each of their rows gives t ≤ ±x·d with t ≥ 0). None
    if the LP fails."""
    m, p = x.shape
    pure = (k == 0) | (k == n)
    ip, im = np.nonzero(pure)[0], np.nonzero(~pure)[0]
    out = np.zeros(m, dtype=bool)
    if len(ip) == 0:
        return out
    s = np.where(k[ip] == n[ip], 1.0, -1.0)
    q = len(ip)
    res = optimize.linprog(
        np.concatenate([np.zeros(p), -np.ones(q)]),
        A_ub=np.hstack([-(s[:, None] * x[ip]), np.eye(q)]), b_ub=np.zeros(q),
        A_eq=np.hstack([x[im], np.zeros((len(im), q))]) if len(im) else None,
        b_eq=np.zeros(len(im)) if len(im) else None,
        bounds=[(None, None)] * p + [(0, 1)] * q, method="highs")
    if res.status != 0:
        return None
    out[ip] = res.x[p:] > LP_SEPARATED
    return out


def separated_rows(x: np.ndarray, y: np.ndarray) -> np.ndarray | None:
    """`separated_patterns` on rows (each row its own pattern of one): the rows of the maximal
    separated set."""
    y = np.asarray(y, dtype=float)
    return separated_patterns(np.asarray(x, dtype=float), y, np.ones(len(y)))


def lcm_fit(x: np.ndarray, k: np.ndarray, n: np.ndarray, p: int) -> np.ndarray | None:
    """Binomial ML on the patterns that are not separated, by damped Newton from 0: step =
    pinv(X'WX) X'(k − nμ), halved until the log-likelihood does not decrease; stops when
    max |step| < 1e-10, after at most 200 steps (None otherwise)."""
    theta = np.zeros(p)
    if len(x) == 0:
        return theta

    def loglik(th: np.ndarray) -> float:
        eta = x @ th
        return float(np.sum(k * eta - n * np.logaddexp(0.0, eta)))

    value = loglik(theta)
    for _ in range(NEWTON_MAX_ITER):
        mu = special.expit(x @ theta)
        info = x.T @ (x * (n * mu * (1 - mu))[:, None])
        step = np.linalg.pinv(info, rcond=PINV_RCOND) @ (x.T @ (k - n * mu))
        if np.max(np.abs(step)) < NEWTON_TOL:
            return theta
        t = 1.0
        while True:
            new = loglik(theta + t * step)
            if new >= value - 1e-10 or t < 1e-10:
                break
            t /= 2
        theta = theta + t * step
        value = new
    return None


def _basis(x: np.ndarray, p: int) -> np.ndarray:
    """An orthonormal basis of the row space of x (singular values > 1e-9 × the largest)."""
    if len(x) == 0:
        return np.zeros((0, p))
    _, sv, vt = np.linalg.svd(x, full_matrices=False)
    if sv.size == 0 or sv.max() <= 0:
        return np.zeros((0, p))
    return vt[sv > SV_REL_TOL * sv.max()]


class MLLimit:
    """The limit of the maximum-likelihood fit (module docstring, estimator ``ml_limit``)."""

    PREDICTIONS = ("lcm", "separated", "lcm-extrapolated", "separated-extrapolated",
                   "not identified")

    def __init__(self, m: ModelRows):
        self.design = d = Design(m)
        self.failed: str | None = None
        self.n_separated_rows = 0
        uniq, x, k, n = d.patterns()
        sep = separated_patterns(x, k, n)
        if sep is None:
            self.failed = "separation LP failed"
            return
        self.n_separated_rows = int(n[sep].sum())
        self.lcm = x[~sep]
        self.sep_x = x[sep]
        self.sep_sign = np.where(k[sep] == n[sep], 1.0, -1.0)
        theta = lcm_fit(x[~sep], k[~sep], n[~sep], d.p)
        if theta is None:
            self.failed = "LCM fit did not converge"
            return
        self.theta = theta
        self.basis = _basis(self.lcm, d.p)
        self.observed = {int(u): (bool(sep[i]), float(k[i] / n[i])) for i, u in enumerate(uniq)}
        self._cache: dict[int, tuple[float | None, str]] = {}

    def in_rowspace(self, v: np.ndarray) -> bool:
        r = v - self.basis.T @ (self.basis @ v)
        return float(np.linalg.norm(r)) < ROWSPACE_TOL * max(1.0, float(np.linalg.norm(v)))

    def _cone(self, v: np.ndarray) -> bool:
        """Is v = u + Σ λ_j s_j x_j with u in the LCM's row space and λ ≥ 0 (an LP feasibility
        check on the LCM's and the separated patterns)?"""
        if len(self.sep_x) == 0:
            return False
        signed = (self.sep_sign[:, None] * self.sep_x).T
        a = np.hstack([self.lcm.T, signed]) if len(self.lcm) else signed
        res = optimize.linprog(np.zeros(a.shape[1]), A_eq=a, b_eq=v,
                               bounds=[(None, None)] * len(self.lcm)
                               + [(0, None)] * len(self.sep_x), method="highs")
        return res.status == 0

    def limit(self, v: np.ndarray) -> tuple[str, float | None]:
        """The limit of v·θ along the likelihood-maximizing sequences: ("finite", value),
        ("+inf", None), ("-inf", None) or ("path-dependent", None)."""
        if self.in_rowspace(v):
            return "finite", float(v @ self.theta)
        for xs, s in zip(self.sep_x, self.sep_sign, strict=True):   # the spec's test
            if self.in_rowspace(v - xs):
                return ("+inf" if s > 0 else "-inf"), None
        for sign, word in ((1.0, "+inf"), (-1.0, "-inf")):          # the exact test
            if self._cone(sign * v):
                return word, None
        return "path-dependent", None

    def predict(self, g: int, c: int) -> tuple[float | None, str]:
        key = g * len(CELLS) + c
        if key in self.observed:
            separated, rate = self.observed[key]
            if separated:
                return rate, "separated"
            return float(special.expit(self.design.x(g, c) @ self.theta)), "lcm"
        if key not in self._cache:
            kind, value = self.limit(self.design.x(g, c))
            self._cache[key] = (
                (float(special.expit(value)), "lcm-extrapolated") if kind == "finite"
                else (None, "not identified") if kind == "path-dependent"
                else (1.0 if kind == "+inf" else 0.0, "separated-extrapolated"))
        return self._cache[key]


def estimability(m: ModelRows) -> dict[str, str | None]:
    """Why each band is not estimable (a harness has no row in it), or None."""
    out = {}
    for b, band in enumerate(MODEL_BANDS):
        has = [bool((m.cell == 2 * b + a).any()) for a in (0, 1)]
        out[band] = (None if all(has) else f"no reached row in the {band} band" if not any(has)
                     else f"{'Standard' if not has[0] else 'Adapter'} reached no {band} level")
    return out


def band_ames(m: ModelRows, predict) -> dict[str, dict]:
    """A_b for each model band: Σ_g n_gb Δ_gb / n_b over the clusters with rows in the band,
    and how each prediction was obtained; `predict(g, cell)` gives (p or None, how)."""
    why_not = estimability(m)
    out = {}
    for b, band in enumerate(MODEL_BANDS):
        res = {"value": None, "why": why_not[band], "how": Counter(), "delta": {}, "weight": {}}
        out[band] = res
        if why_not[band]:
            continue
        w = np.bincount(m.codes[m.cell // 2 == b], minlength=m.n_clusters)
        total, ok = 0.0, True
        for g in np.nonzero(w)[0].tolist():
            pa, how_a = predict(g, 2 * b + 1)
            ps, how_s = predict(g, 2 * b)
            res["how"][how_a] += 1
            res["how"][how_s] += 1
            res["weight"][g] = int(w[g])
            if pa is None or ps is None:
                ok = False
                res["delta"][g] = None
                continue
            res["delta"][g] = pa - ps
            total += w[g] * (pa - ps)
        if ok:
            res["value"] = total / float(w.sum())
        else:
            res["why"] = "not identified in the ML limit"
    return out


def _finish(bands: dict[str, dict], interaction: float | None, why_interaction: str | None,
            estimable: bool) -> dict:
    ae, ad = bands["early"]["value"], bands["deep"]["value"]
    why = {}
    if ae is None:
        why["A_early"] = bands["early"]["why"]
    if ad is None:
        why["A_deep"] = bands["deep"]["why"]
    contrast = None if ae is None or ad is None else ad - ae
    if contrast is None:
        why["contrast"] = why.get("A_deep") or why.get("A_early")
    if interaction is None:
        why["logit_interaction"] = why_interaction
    return {"A_early": ae, "A_deep": ad, "contrast": contrast,
            "logit_interaction": interaction, "defined": contrast is not None,
            "why_undefined": why, "estimable": estimable, "bands": bands}


def _failed(m: ModelRows, reason: str) -> dict:
    """Every quantity undefined: a band that is not estimable keeps that reason."""
    why_not = estimability(m)
    bands = {b: {"value": None, "why": why_not[b] or reason, "how": Counter(), "delta": {},
                 "weight": {}} for b in MODEL_BANDS}
    interaction_why = next((w for w in why_not.values() if w), None) or reason
    return _finish(bands, None, interaction_why, not any(why_not.values()))


def _gamma(design: Design, beta: np.ndarray) -> dict[int, float]:
    out = {design.present[0]: 0.0}
    for c, j in design.col.items():
        out[c] = float(beta[j - design.m.n_clusters])
    return out


def _from_coefficients(m: ModelRows, design: Design, alpha: np.ndarray, beta: np.ndarray,
                       how: str) -> dict:
    gamma = _gamma(design, beta)
    bands = band_ames(m, lambda g, c: (float(special.expit(alpha[g] + gamma[c])), how))
    v = design.interaction()
    interaction = None if v is None else float(v[m.n_clusters:] @ beta)
    why = next((w for w in estimability(m).values() if w), None)
    return _finish(bands, interaction, why, why is None)


def firth_line_search(y: np.ndarray, codes: np.ndarray, z: np.ndarray,
                      max_iter: int = FIRTH_MAX_ITER,
                      tol: float = FIRTH_TOL) -> tuple[np.ndarray, np.ndarray] | None:
    """Firth's estimate when `persistgym_h1h3.firth_fe_logit` returns None: the same penalized
    log-likelihood (the log-likelihood plus half the log-determinant of the Fisher information)
    and the same scoring steps (the Fisher information's inverse times the modified score), with
    an Armijo line search (a step must raise the penalized log-likelihood by at least 1e-4 × t ×
    the score's slope) in place of "does not decrease". That stops the 2-cycle around the
    maximum in which firth_fe_logit's full steps can be caught (module docstring). Converged
    when the full step's largest element is below `tol`, or when the slope (about twice the gain
    a full step would bring near the maximum) is below 1e-10 × the penalized log-likelihood,
    where rounding decides the line search; None if the line search finds no step or the cap is
    reached."""
    y = np.asarray(y, dtype=float)
    g = int(codes.max()) + 1
    x = np.column_stack([np.eye(g)[codes], np.asarray(z, dtype=float)])

    def penalized(theta):
        eta = x @ theta
        mu = special.expit(eta)
        w = mu * (1 - mu)
        ll = -float(np.sum(y * np.logaddexp(0.0, -eta) + (1 - y) * np.logaddexp(0.0, eta)))
        try:
            chol = linalg.cho_factor(x.T @ (x * w[:, None]), lower=True)
        except np.linalg.LinAlgError:
            return -np.inf, None, mu, w
        return ll + float(np.sum(np.log(np.diag(chol[0])))), chol, mu, w

    theta = np.zeros(x.shape[1])
    value, chol, mu, w = penalized(theta)
    for _ in range(max_iter):
        if chol is None:
            return None
        v = linalg.solve_triangular(chol[0], x.T, lower=True)
        h = w * np.sum(v * v, axis=0)
        score = x.T @ (y - mu + h * (0.5 - mu))
        step = linalg.cho_solve(chol, score)
        if np.max(np.abs(step)) < tol:
            return (theta[:g], theta[g:]) if np.isfinite(theta).all() else None
        slope = float(score @ step)
        if slope <= FIRTH_FLOOR * max(1.0, abs(value)):
            # what is left to gain is at the penalized log-likelihood's resolution
            return (theta[:g], theta[g:]) if np.isfinite(theta).all() else None
        t = 1.0
        while True:
            new = penalized(theta + t * step)
            if new[0] >= value + FIRTH_ARMIJO * t * slope:
                break
            if t < 1e-10:
                return None
            t /= 2
        theta = theta + t * step
        value, chol, mu, w = new
    return None


def fit_firth(m: ModelRows) -> dict:
    """Estimator ``firth``: `persistgym_h1h3.firth_fe_logit` on the cluster codes and the cell
    columns present; where it returns None, `firth_line_search` on the same design (counted in
    ``optimizer``)."""
    if len(m.y) == 0:
        return {**_failed(m, "no reached row"), "optimizer": None}
    design = Design(m)
    _, x, _, _ = design.patterns()
    if np.linalg.matrix_rank(x) < design.p:
        return {**_failed(m, "design not of full rank"), "optimizer": None}
    z = design.z()
    fit, optimizer = h13.firth_fe_logit(m.y, m.codes, z), FIRTH_OPTIMIZERS[0]
    if fit is None:
        fit, optimizer = firth_line_search(m.y, m.codes, z), FIRTH_OPTIMIZERS[1]
    if fit is None:
        return {**_failed(m, "Firth did not converge"), "optimizer": None}
    return {**_from_coefficients(m, design, fit[0], fit[1], "firth"), "optimizer": optimizer}


def fit_ml_limit(m: ModelRows) -> dict:
    """Estimator ``ml_limit``: the AMEs in the maximum-likelihood limit (`MLLimit`), with the
    count of each kind of prediction per band and the separated rows."""
    if len(m.y) == 0:
        out = _failed(m, "no reached row")
        return {**out, "n_separated_rows": 0, "interaction_limit": None}
    e = MLLimit(m)
    if e.failed:
        return {**_failed(m, e.failed), "n_separated_rows": 0, "interaction_limit": None}
    bands = band_ames(m, e.predict)
    v = e.design.interaction()
    why_not = next((w for w in estimability(m).values() if w), None)
    interaction, why, kind = None, why_not, None
    if v is not None:
        kind, value = e.limit(v)
        if kind == "finite":
            interaction, why = value, None
        else:
            why = "not finite in the ML limit"
    out = _finish(bands, interaction, why, why_not is None)
    return {**out, "n_separated_rows": e.n_separated_rows, "interaction_limit": kind}


def fit_statsmodels(m: ModelRows) -> dict | None:
    """statsmodels' stopping point (`persistgym_h1h3.sm_fe_logit`), its AMEs; None if it
    fails."""
    if len(m.y) == 0:
        return None
    design = Design(m)
    fit = h13.sm_fe_logit(m.y, m.codes, design.z())
    if fit is None:
        return None
    return _from_coefficients(m, design, fit["alpha"], fit["beta"], "statsmodels")


def raw_rates(rows: list[Row]) -> dict:
    """Reached, cleared and P(clear | reached) per band and harness, pooled over games, and the
    raw contrast (r_Ad − r_Sd) − (r_Ae − r_Se)."""
    bands = {}
    for band in BANDS:
        bands[band] = {}
        for h in HARNESSES:
            sel = [r for r in rows if r.band == band and r.harness == h]
            cleared = sum(r.cleared for r in sel)
            bands[band][h] = {"reached": len(sel), "cleared": cleared,
                              "rate": cleared / len(sel) if sel else None}
    contrast, why = _raw_contrast(bands)
    return {"bands": bands, "contrast": contrast, "contrast_why_undefined": why,
            "contrast_label": RAW_LABEL}


def _raw_contrast(bands: dict) -> tuple[float | None, str | None]:
    r = {(b, h): bands[b][h]["rate"] for b in MODEL_BANDS for h in HARNESSES}
    empty = [f"{HARNESS_NAME[h]} reached no {b} level" for (b, h), v in r.items() if v is None]
    if empty:
        return None, empty[0]
    return ((r[("deep", "provider_adapter")] - r[("deep", "standard")])
            - (r[("early", "provider_adapter")] - r[("early", "standard")])), None


def _raw_contrast_arrays(m: ModelRows) -> tuple[float | None, str | None]:
    rate = {}
    for c in range(len(CELLS)):
        sel = m.y[m.cell == c]
        rate[c] = float(sel.mean()) if len(sel) else None
    empty = [c for c, v in rate.items() if v is None]
    if empty:
        c = empty[0]
        return None, (f"{'Adapter' if c % 2 else 'Standard'} reached no "
                      f"{MODEL_BANDS[c // 2]} level")
    return (rate[3] - rate[2]) - (rate[1] - rate[0]), None


def primary_of(firth: dict, ml: dict | None, rule: str) -> tuple[dict, str]:
    """The estimate that decides (`PRIMARY_ESTIMATOR`) and its source: ``firth``; or, under
    ``ml_limit_or_firth``, the ML limit where C is identified (or no band choice is possible:
    a band is not estimable) and Firth for both bands otherwise."""
    if rule == "firth":
        return firth, "firth"
    if rule != "ml_limit_or_firth":
        raise Refusal(f"unknown primary estimator rule {rule!r} (one of {', '.join(ESTIMATORS)})")
    if ml is not None and (ml["defined"] or not ml["estimable"]):
        return ml, "ml_limit"
    return firth, "firth"


def fallback_reason(ml: dict | None, rule: str, source: str) -> str | None:
    """Why the rule `ml_limit_or_firth` fell back to Firth: the ML limit's reason for leaving C
    undefined ("not identified in the ML limit", or a failed ML fit); None otherwise."""
    if rule != "ml_limit_or_firth" or source != "firth":
        return None
    if ml is None:
        return "ML limit not computed"
    return ml["why_undefined"].get("contrast") or "undefined"


def estimators_needed(rule: str, registered: bool) -> tuple[str, ...]:
    """The estimators a bootstrap computes: both for a registered reading; for an exploratory
    one only those the rule in force needs."""
    if registered or rule == "ml_limit_or_firth":
        return ("firth", "ml_limit")
    return ("firth",)


# --- bootstrap -----------------------------------------------------------------------------------

def game_arrays(rows: list[Row], games: list[str]) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Each game's early and deep rows (cells, outcomes), both harnesses."""
    per: dict[str, tuple[list[int], list[float]]] = {g: ([], []) for g in games}
    for r in rows:
        if r.band in MODEL_BANDS:
            per[r.game][0].append(cell_index(r.adapter, r.band))
            per[r.game][1].append(float(r.cleared))
    return {g: (np.asarray(c, dtype=int), np.asarray(y, dtype=float)) for g, (c, y) in per.items()}


def cluster_labels(games: list[str], draw) -> list[str]:
    """The clusters of one resample: the game drawn at position j becomes ``<game>#<j>``."""
    return [f"{games[int(i)]}#{j}" for j, i in enumerate(draw)]


def resample_rows(per: dict[str, tuple[np.ndarray, np.ndarray]], games: list[str],
                  draw) -> ModelRows:
    """A resample's rows: each drawn game a cluster of its own, with all its rows (a game with
    no rows adds no cluster)."""
    labels, codes, cells, ys = [], [], [], []
    for label, i in zip(cluster_labels(games, draw), draw, strict=True):
        c, y = per[games[int(i)]]
        if len(c) == 0:
            continue
        codes.append(np.full(len(c), len(labels)))
        labels.append(label)
        cells.append(c)
        ys.append(y)
    if not labels:
        return ModelRows(np.zeros(0, int), np.zeros(0, int), np.zeros(0), ())
    return ModelRows(np.concatenate(codes), np.concatenate(cells), np.concatenate(ys),
                     tuple(labels))


def _quantities(est: dict) -> dict:
    return {q: (est[q], est["why_undefined"].get(q)) for q in QUANTITIES}


def resample_estimates(m: ModelRows, estimators: tuple[str, ...], rule: str) -> dict:
    """One resample's quantities under each estimator and the primary rule, and the raw
    contrast."""
    fits = {}
    if "firth" in estimators:
        fits["firth"] = fit_firth(m)
    if "ml_limit" in estimators:
        fits["ml_limit"] = fit_ml_limit(m)
    est, source = primary_of(fits["firth"], fits.get("ml_limit"), rule)
    out = {name: _quantities(f) for name, f in fits.items()}
    out["primary"] = _quantities(est)
    out["primary_source"] = source
    out["fallback_reason"] = fallback_reason(fits.get("ml_limit"), rule, source)
    out["firth_optimizer"] = fits["firth"]["optimizer"]
    out["raw_contrast"] = _raw_contrast_arrays(m)
    return out


def _interval(x: list[float]) -> list[float] | None:
    if not x:
        return None
    lo, hi = np.quantile(np.asarray(x, dtype=float), QUANTILES)
    return [float(lo), float(hi)]


def _summarise(values: list[tuple[float | None, str | None]]) -> dict:
    ok = [v for v, _ in values if v is not None]
    reasons = Counter(w or "undefined" for v, w in values if v is None)
    return {"interval": _interval(ok), "n_defined": len(ok), "n_undefined": len(values) - len(ok),
            "undefined_reasons": dict(sorted(reasons.items()))}


def bootstrap(per: dict[str, tuple[np.ndarray, np.ndarray]], games: list[str], seed: int,
              boot: int, estimators: tuple[str, ...], rule: str,
              progress: Progress | None = None, label: str = "") -> dict:
    """Game-cluster bootstrap: `boot` resamples from a fresh ``default_rng(seed)``; each
    resample's games are taken in sorted order and its result memoized by that tuple."""
    n = len(games)
    idx = np.random.default_rng(seed).integers(0, n, size=(boot, n))
    memo: dict[tuple[int, ...], dict] = {}
    results = []
    for k in range(boot):
        key = tuple(sorted(int(i) for i in idx[k]))
        if key not in memo:
            memo[key] = resample_estimates(resample_rows(per, games, key), estimators, rule)
        results.append(memo[key])
        if progress is not None and (k + 1) % 2000 == 0:
            progress(label, k + 1, boot)
    out = {"resamples": boot, "rng_seed": seed, "level": LEVEL, "method": "percentile",
           "quantiles": list(QUANTILES), "clusters": "games (each drawn game its own cluster)",
           "n_games": n, "distinct_possible": math.comb(2 * n - 1, n) if n else 0,
           "distinct_drawn": len(memo), "estimators": {}, "primary": None,
           "raw_contrast": _summarise([r["raw_contrast"] for r in results])}
    for name in (*estimators, "primary"):
        s = {q: _summarise([r[name][q] for r in results]) for q in QUANTITIES}
        cs = [r[name]["contrast"][0] for r in results if r[name]["contrast"][0] is not None]
        s["fraction_contrast_le_0"] = (float(np.mean([c <= POSITIVE_TOL for c in cs]))
                                       if cs else None)
        if name == "primary":
            s["rule"] = rule
            fell = [r["fallback_reason"] for r in results if r["fallback_reason"] is not None]
            on = rule == "ml_limit_or_firth"
            s["n_firth_fallback"] = len(fell) if on else None
            s["firth_fallback_reasons"] = dict(sorted(Counter(fell).items())) if on else None
            out["primary"] = s
        else:
            if name == "firth":
                s["n_line_search"] = sum(r["firth_optimizer"] == FIRTH_OPTIMIZERS[1]
                                         for r in results)
            out["estimators"][name] = s
    return out


# --- readings ------------------------------------------------------------------------------------

def _sign_word(c: float | None) -> str:
    return CANNOT if c is None else "positive" if c > POSITIVE_TOL else "not positive"


def verdict(contrast: float | None, why: str | None, registered: bool) -> str:
    """§3 H5's reading of C on the point estimate (exploratory readings: the sign only)."""
    if contrast is None:
        return f"{CANNOT}: {why}" if registered and why else CANNOT
    if not registered:
        return _sign_word(contrast)
    return VERDICT_POSITIVE if contrast > POSITIVE_TOL else VERDICT_NOT_POSITIVE


def _public(est: dict | None, with_ml: bool = False) -> dict | None:
    """An estimate's reported fields (no per-band internals)."""
    if est is None:
        return None
    out = {k: est[k] for k in ESTIMATE_FIELDS}
    if "optimizer" in est:
        out["optimizer"] = est["optimizer"]
    if with_ml:
        out["predictions"] = {b: {h: est["bands"][b]["how"].get(h, 0)
                                  for h in MLLimit.PREDICTIONS} for b in MODEL_BANDS}
        out["n_separated_rows"] = est["n_separated_rows"]
        out["interaction_limit"] = est["interaction_limit"]
    return out


def _statsmodels_check(sm: dict | None, ml: dict) -> tuple[dict, list[str]]:
    """statsmodels' stopping point against the ML limit (point estimate only)."""
    if sm is None:
        return {**dict.fromkeys(ESTIMATE_FIELDS), "path_dependent": [],
                "max_abs_diff_vs_ml_limit": None, "agrees_with_ml_limit": None,
                "note": "statsmodels returned no fit"}, []
    out = _public(sm)
    path, diffs = [], []
    for b, q in (("early", "A_early"), ("deep", "A_deep")):
        if ml[q] is not None and sm[q] is not None:
            diffs.append((q, abs(ml[q] - sm[q])))
        elif ml["bands"][b]["why"] == "not identified in the ML limit":
            path.append(q)
    worst = max((d for _, d in diffs), default=None)
    out.update({"path_dependent": path, "max_abs_diff_vs_ml_limit": worst,
                "agrees_with_ml_limit": None if worst is None else worst <= SM_TOL,
                "note": (f"{', '.join(path)}: the ML limit is not identified there, so this is "
                         "the stopping point: path-dependent; not an estimate") if path
                else None})
    warn = [f"statsmodels' stopping point differs from the ML limit by {d:.2g} in {q} "
            f"(above {SM_TOL:g})" for q, d in diffs if d > SM_TOL]
    return out, warn


def per_game_table(runs: list[RunLevels], rows: list[Row], games: list[str], m: ModelRows,
                   fits: dict[str, dict]) -> tuple[list[dict], dict[str, str]]:
    """Per game: level count; each harness's levels completed, last reached level and ending;
    deep support; each estimator's Δ_g and weight per band."""
    code = {label: i for i, label in enumerate(m.clusters)}
    by = {(r.game, r.harness): r for r in runs}
    support = {}
    out = []
    for g in games:
        deep = {h: any(r.game == g and r.harness == h and r.band == "deep" for r in rows)
                for h in HARNESSES}
        support[g] = ("both" if all(deep.values()) else "adapter only"
                      if deep["provider_adapter"] else "standard only" if deep["standard"]
                      else "neither")
        row = {"game": g, "level_count": next((r.level_count for r in runs if r.game == g),
                                              None), "deep_support": support[g]}
        for h in HARNESSES:
            r = by.get((g, h))
            row[h] = None if r is None else {
                "run_id": r.run_id, "label": r.label, "levels_completed": r.levels_completed,
                "last_reached_level": r.last_reached_level, "ending": r.ending,
                "ending_kind": r.ending_kind}
        row["estimators"] = {}
        for name, f in fits.items():
            cell = {}
            for b in MODEL_BANDS:
                band = f["bands"][b]
                i = code.get(g)
                cell[b] = {"delta": band["delta"].get(i), "weight": band["weight"].get(i, 0)}
            row["estimators"][name] = cell
        out.append(row)
    return out, support


def per_level_table(runs: list[RunLevels], rows: list[Row]) -> list[dict]:
    top = max((r.level_count for r in runs), default=0)
    out = []
    for level in range(1, top + 1):
        row = {"level": level, "band": band_of(level)}
        for h in HARNESSES:
            sel = [r for r in rows if r.level == level and r.harness == h]
            cleared = sum(r.cleared for r in sel)
            row[h] = {"n_runs": sum(r.harness == h and r.level_count >= level for r in runs),
                      "reached": len(sel), "cleared": cleared,
                      "rate": cleared / len(sel) if sel else None}
        out.append(row)
    return out


@dataclass
class Spec:
    """What one reading is computed on."""
    label: str
    data: str
    registered: bool
    effort: str | None
    harnesses: dict[str, str]
    games: list[str]
    runs: list[RunLevels]


def _n_rows(rows: list[Row]) -> dict:
    out = {b: {h: sum(r.band == b and r.harness == h for r in rows) for h in HARNESSES}
           for b in BANDS}
    out["in_model"] = sum(r.band in MODEL_BANDS for r in rows)
    return out


def _sign_agrees(a: float | None, b: float | None) -> bool | None:
    if a is None or b is None:
        return None
    return bool((a > POSITIVE_TOL) == (b > POSITIVE_TOL))


def compute_reading(spec: Spec, rows: list[Row], seed: int, boot: int, rule: str,
                    warnings: list[str], *, model: bool = True,
                    progress: Progress | None = None) -> dict:
    """One reading (`READING_FIELDS`), its sensitivity and common support left None."""
    runs, games = spec.runs, spec.games
    m = rows_to_model([r for r in rows if r.game in games])
    deep_rows = [r for r in rows if r.band == "deep"]
    out = {"label": spec.label, "data": spec.data, "registered": spec.registered,
           "effort": spec.effort, "harnesses": spec.harnesses, "games": list(games),
           "n_games": len(games), "n_runs": len(runs), "n_rows": _n_rows(rows),
           "raw": raw_rates(rows), "per_level": per_level_table(runs, rows),
           "per_game": None, "deep_support": None, "extrapolated_share_deep": None,
           "estimates": None, "primary": None, "other_estimator_sign_agrees": None,
           "bootstrap": None, "sensitivity_error_endings": None, "common_support": None}
    fits = {}
    if model:
        fits = {"firth": fit_firth(m), "ml_limit": fit_ml_limit(m)}
    out["per_game"], support = per_game_table(runs, rows, games, m, fits)
    out["deep_support"] = {k: sum(v == k for v in support.values())
                           for k in ("both", "adapter only", "standard only", "neither")}
    one_sided = {g for g, v in support.items() if v in ("adapter only", "standard only")}
    out["extrapolated_share_deep"] = (sum(r.game in one_sided for r in deep_rows)
                                      / len(deep_rows) if deep_rows else None)
    if not model:
        out["primary"] = {**dict.fromkeys(ESTIMATE_FIELDS), "source": None, "rule": rule,
                          "fallback_reason": None,
                          "verdict": "not computed: a unit lacks a counted run (PROVISIONAL)",
                          "logit_sign_disagrees": None}
        return out
    sm, warn = _statsmodels_check(fit_statsmodels(m), fits["ml_limit"])
    warnings += [f"{spec.label}: {w}" for w in warn]
    out["estimates"] = {"firth": _public(fits["firth"]),
                        "ml_limit": _public(fits["ml_limit"], with_ml=True),
                        "statsmodels_stop": sm}
    est, source = primary_of(fits["firth"], fits["ml_limit"], rule)
    other = fits["ml_limit" if source == "firth" else "firth"]
    c, li = est["contrast"], est["logit_interaction"]
    out["primary"] = {**_public(est), "source": source, "rule": rule,
                      "fallback_reason": fallback_reason(fits["ml_limit"], rule, source),
                      "verdict": verdict(c, est["why_undefined"].get("contrast"),
                                         spec.registered),
                      "logit_sign_disagrees": (None if c is None or li is None
                                               else bool((c > POSITIVE_TOL)
                                                         != (li > POSITIVE_TOL)))}
    out["other_estimator_sign_agrees"] = _sign_agrees(c, other["contrast"])
    out["bootstrap"] = bootstrap(game_arrays(rows, games), games, seed, boot,
                                 estimators_needed(rule, spec.registered), rule,
                                 progress=progress, label=spec.label)
    return out


def full_reading(spec: Spec, seed: int, boot: int, rule: str, warnings: list[str], *,
                 sensitivity: bool, common_support: bool,
                 progress: Progress | None = None) -> dict:
    """A reading with, as asked, its error-ending sensitivity (same seed: paired resamples)
    and its exploratory common-support reading."""
    rows = [x for r in spec.runs for x in level_rows(r)]
    out = compute_reading(spec, rows, seed, boot, rule, warnings, progress=progress)
    if sensitivity:
        dropped = [r for r in rows if r.ended_by_error]
        kept = [r for r in rows if not r.ended_by_error]
        sens_spec = Spec(label=f"{spec.label}: error-ending sensitivity", data=spec.data,
                         registered=spec.registered, effort=spec.effort,
                         harnesses=spec.harnesses, games=spec.games, runs=spec.runs)
        sens = compute_reading(sens_spec, kept, seed, boot, rule, warnings, progress=progress)
        ending = {r.run_id: r.ending for r in spec.runs}
        sens["dropped_rows"] = [{"game": r.game, "harness": r.harness, "level": r.level,
                                 "ending": ending[r.run_id], "run_id": r.run_id}
                                for r in dropped]
        assert tuple(sens) == SENSITIVITY_FIELDS
        out["sensitivity_error_endings"] = sens
    if common_support:
        both = [g["game"] for g in out["per_game"] if g["deep_support"] == "both"]
        cs = {"computed": len(both) >= 2, "games": both, "why_not": None, "reading": None}
        if len(both) < 2:
            cs["why_not"] = (f"{len(both)} game(s) where both harnesses reached a deep level; "
                             "at least 2 are needed")
        else:
            cs_spec = Spec(label=f"{spec.label}: common support (exploratory)", data=spec.data,
                           registered=False, effort=spec.effort, harnesses=spec.harnesses,
                           games=both, runs=[r for r in spec.runs if r.game in both])
            cs["reading"] = compute_reading(cs_spec, [r for r in rows if r.game in both], seed,
                                            boot, rule, warnings, progress=progress)
        out["common_support"] = cs
    assert tuple(out) == READING_FIELDS
    return out


# --- compute -------------------------------------------------------------------------------------

def _rel(p: Path | None) -> str | None:
    if p is None:
        return None
    p = p.resolve()
    return p.relative_to(REPO_ROOT).as_posix() if p.is_relative_to(REPO_ROOT) else str(p)


def _run_row(e: cc.Entry, ours: Ours, in_reading: set[str],
             dropped: dict[str, int]) -> dict:
    u = ours.units.get((e.game, e.config))
    r = e.run
    run = None
    if r is not None:
        la = tuple(int(a) for a in r.level_actions)
        ending = e.d19_ending
        run = RunLevels(source="ours", run_id=e.run_id, game=e.game,
                        harness=HARNESS_OF_CONFIG[e.config], label=e.config, effort=None,
                        level_count=r.level_count, levels_completed=r.levels_completed,
                        level_actions=la, ending=ending,
                        ending_kind=OURS_ENDING_KIND.get(ending, "unknown"),
                        total_actions=r.actions)
    flags = list(ours.flags.get(e.run_id, []))
    if e.truncated:
        flags.append("truncated (not a counted run)")
    if e.replaced_by:
        flags.append(f"replaced by {', '.join(e.replaced_by)}, not in H5")
    if e.rerun_of:
        flags.append(f"re-run of {e.rerun_of} (D19)")
        if ours.eligible.get(e.run_id) and not e.replaced_by:
            flags.append("re-run also ended re-run-eligible: counted as is (D19)")
    if u is not None and u.pending and u.head is e:
        flags.append("re-run-eligible; its re-run has not landed")
    if e.d19_ending == COST_CAP:
        flags.append("COST_CAP: kept as a budget ending (the $120 guard)")
    if r is not None and not r.checks_passed:
        flags.append("fails analysis.arc_action_matched's checks")
    if e.run_id in dropped:
        flags.append(f"error ending: level {dropped[e.run_id]} dropped in the sensitivity "
                     "reading")
    row = {"run_id": e.run_id, "game": e.game, "config": e.config,
           "harness": HARNESS_OF_CONFIG[e.config], "replicate": e.replicate, "seed": e.seed,
           "rerun_of": e.rerun_of, "replaced_by": list(e.replaced_by),
           "counted": not e.replaced_by and not e.truncated,
           "in_reading": e.run_id in in_reading, "agent_exit_reason": e.agent_exit_reason,
           "exit_reason": e.exit_reason, "d19_ending": e.d19_ending,
           "ending_kind": OURS_ENDING_KIND.get(e.d19_ending),
           "rerun_eligible": ours.eligible.get(e.run_id),
           "level_count": r and r.level_count, "levels_completed": r and r.levels_completed,
           "level_actions": None if r is None else [int(a) for a in r.level_actions],
           "last_reached_level": run and run.last_reached_level,
           "ended_level": run and run.ended_level,
           "dropped_in_sensitivity": dropped.get(e.run_id), "flags": flags}
    assert tuple(row) == OURS_RUN_FIELDS
    return row


def _settings(boot: int, rule: str, command: str, data: str, exploratory: bool) -> dict:
    return {"command": command, "data": data, "exploratory": exploratory,
            "bands": {"early": list(EARLY), "level_3": [LEVEL_3],
                      "deep": f"levels >= {DEEP_MIN}"},
            "registered_effort": REGISTERED_EFFORT,
            "exploratory_efforts": list(EXPLORATORY_EFFORTS), "n_boot": boot,
            "n_boot_registered": N_BOOT, "level": LEVEL, "quantiles": list(QUANTILES),
            "positive_tol": POSITIVE_TOL, "statsmodels_tol": SM_TOL,
            "ame_rows": "every reached (run, level) row of the band, both harnesses; a game "
                        "weighs by its reached level-rows in the band",
            "ending_kind_published": dict(PUBLISHED_ENDING_KIND),
            "ending_kind_ours": dict(OURS_ENDING_KIND),
            "primary_estimator": rule,
            "alternative_rule": next(x for x in ESTIMATORS if x != rule)
            if rule in ESTIMATORS else None,
            "published_sha256_pinned": PUBLISHED_SHA256}


def compute(root: Path, generated: str, git: dict, *, published_dir: Path | None = None,
            data: str = "both", boot: int = N_BOOT, exploratory: bool = True,
            allow_incomplete: bool = False, progress: Progress | None = None,
            command: str = "uv run python -m analysis.arc_h5") -> dict:
    """H5's readings from the files under `root`. Raises Refusal, cc.Refusal or am.Refused."""
    if data not in DATA_CHOICES:
        raise Refusal(f"--data {data!r} is not one of {', '.join(DATA_CHOICES)}")
    rule = PRIMARY_ESTIMATOR
    if rule not in ESTIMATORS:
        raise Refusal(f"PRIMARY_ESTIMATOR {rule!r} is not one of {', '.join(ESTIMATORS)}")
    published_dir = published_dir or root / PUBLISHED_SLICE
    warnings: list[str] = []
    reasons: list[str] = []
    if boot != N_BOOT:
        reasons.append(f"--boot {boot}, not {N_BOOT:,}: not the registered analysis")
    ours = load_ours(root) if data in ("both", "ours") else None
    draw_path, _, seed = (ours.draw_path, ours.games, ours.seed) if ours else read_draw(root)
    pub = load_published(published_dir, exploratory) if data in ("both", "published") else None
    if pub is not None:
        warnings += pub.warnings
        if not pub.pinned:
            reasons.append(f"published per_run.csv has sha256 {pub.sha256}, not the pinned "
                           f"{PUBLISHED_SHA256}: not the registered input")
    if ours is not None:
        warnings += ours.warnings
        if ours.incomplete and not allow_incomplete:
            raise Refusal("a unit lacks a counted run it can use:\n"
                          + "\n".join(f"  - {x}" for x in ours.incomplete)
                          + "\nWait for the runs, or pass --allow-incomplete to see the raw "
                            "tables (PROVISIONAL, no model).")
        reasons += ours.incomplete
    boot_seed = seed + BOOT_SEED_OFFSET
    published = published_x = None
    if pub is not None:
        runs = pub.runs[REGISTERED_EFFORT]
        spec = Spec(label="published, effort high (registered)", data="published",
                    registered=True, effort=REGISTERED_EFFORT,
                    harnesses={"standard": "Standard", "provider_adapter": "Provider Adapter"},
                    games=sorted({r.game for r in runs}), runs=runs)
        published = full_reading(spec, boot_seed, boot, rule, warnings, sensitivity=True,
                                 common_support=exploratory, progress=progress)
        if exploratory:
            efforts = {}
            for effort in EXPLORATORY_EFFORTS:
                if effort not in pub.runs:
                    efforts[effort] = None
                    continue
                runs = pub.runs[effort]
                spec = Spec(label=f"published, effort {effort} (exploratory)", data="published",
                            registered=False, effort=effort, harnesses=published["harnesses"],
                            games=sorted({r.game for r in runs}), runs=runs)
                efforts[effort] = full_reading(spec, boot_seed, boot, rule, warnings,
                                               sensitivity=False, common_support=False,
                                               progress=progress)
            published_x = {"efforts": efforts, "skipped": dict(pub.skipped),
                           "other_models": OTHER_MODELS}
    ours_reading, ours_runs, skipped = None, [], []
    if ours is not None:
        complete = not ours.incomplete
        spec = Spec(label="ours, S0 vs S4 on the 4 path games (registered)", data="ours",
                    registered=True, effort=None,
                    harnesses={"standard": "S0", "provider_adapter": "S4"},
                    games=list(ours.games), runs=list(ours.runs))
        if complete:
            ours_reading = full_reading(spec, boot_seed, boot, rule, warnings, sensitivity=True,
                                        common_support=exploratory, progress=progress)
        else:
            rows = [x for r in spec.runs for x in level_rows(r)]
            ours_reading = compute_reading(spec, rows, boot_seed, boot, rule, warnings,
                                           model=False)
        dropped = {r.run_id: r.level for x in ours.runs for r in level_rows(x)
                   if r.ended_by_error}
        in_reading = {r.run_id for r in ours.runs}
        ours_runs = [_run_row(e, ours, in_reading, dropped)
                     for e in sorted(ours.entries, key=lambda x: x.started)
                     if e.config in CONFIGS]
        skipped = ([{"folder": n, "reason": w} for n, w in ours.bare]
                   + [{"folder": e.folder.name, "reason": e.skip_reason}
                      for e in ours.entries if e.skip_reason])
    out = {"generated_utc": generated, **git, "prereg_version": runmeta.prereg_version(),
           "status": PROVISIONAL if reasons else FINAL, "provisional_reasons": reasons,
           "warnings": warnings,
           "inputs": {"results_root": _rel(root),
                      "published_slice": _rel(published_dir) if pub else None,
                      "published_per_run_sha256": pub and pub.sha256,
                      "published_sha256_matches_pinned": pub and pub.pinned,
                      "draw_json": _rel(draw_path),
                      "costs_csv": _rel(ours.costs_csv) if ours else None,
                      "arc_path_folders": [_rel(e.folder) for e in ours.entries] if ours
                      else []},
           "settings": _settings(boot, rule, command, data, exploratory), "seed": seed,
           "bootstrap_seed": boot_seed,
           "primary_estimator": rule, "published": published,
           "published_exploratory": published_x, "ours": ours_reading, "ours_runs": ours_runs,
           "skipped": skipped}
    assert tuple(out) == TOP_FIELDS
    return out


# --- summary -------------------------------------------------------------------------------------

ESTIMATOR_NAME = {"firth": "Firth (`firth`)", "ml_limit": "ML limit (`ml_limit`)",
                  "primary": "Rule in force", "statsmodels_stop": "statsmodels stopping point"}


def _f(v, digits: int = 3, signed: bool = True) -> str:
    if v is None:
        return "n/a"
    return f"{v:+.{digits}f}" if signed else f"{v:.{digits}f}"


def _iv(iv, digits: int = 3) -> str:
    return "n/a" if iv is None else f"[{iv[0]:+.{digits}f}, {iv[1]:+.{digits}f}]"


def _rate(c: dict) -> str:
    return f"{c['cleared']}/{c['reached']} = {_f(c['rate'], signed=False)}"


def _pct(v) -> str:
    return "n/a" if v is None else f"{v:.1%}"


def _value(est: dict, q: str) -> str:
    v = est.get(q)
    if v is not None:
        return _f(v)
    why = (est.get("why_undefined") or {}).get(q)
    return f"undefined ({why})" if why else "n/a"


def _left_out(s: dict | None) -> str:
    if s is None:
        return "not bootstrapped"
    if not s["n_undefined"]:
        return "0"
    return f"{s['n_undefined']:,} (" + "; ".join(
        f"{why}: {n:,}" for why, n in s["undefined_reasons"].items()) + ")"


def _other(source: str) -> str:
    return "ml_limit" if source == "firth" else "firth"


def raw_lines(r: dict) -> list[str]:
    raw = r["raw"]
    h = r["harnesses"]
    L = [(f"| Band | {h['standard']}: cleared/reached = P(clear \\| reached) | "
         f"{h['provider_adapter']}: cleared/reached = P | Adapter − Standard |"),
         "|---|---|---|---|"]
    for band in BANDS:
        s, a = raw["bands"][band]["standard"], raw["bands"][band]["provider_adapter"]
        diff = None if s["rate"] is None or a["rate"] is None else a["rate"] - s["rate"]
        name = {"early": "early (1-2)", "level_3": "level 3 (not in the contrast)",
                "deep": f"deep (≥ {DEEP_MIN})"}[band]
        L.append(f"| {name} | {_rate(s)} | {_rate(a)} | {_f(diff)} |")
    bs = r["bootstrap"]
    iv = "" if bs is None else (f"; 90% interval {_iv(bs['raw_contrast']['interval'])} over "
                                f"{bs['raw_contrast']['n_defined']:,} defined resamples")
    raw_c = (_f(raw["contrast"]) if raw["contrast"] is not None
             else f"undefined ({raw['contrast_why_undefined']})")
    L += ["", f"Raw contrast (r_Ad − r_Sd) − (r_Ae − r_Se) = {raw_c} ({RAW_LABEL}{iv})."]
    return L


def model_lines(r: dict) -> list[str]:
    est, bs = r["estimates"], r["bootstrap"]
    L = [("| Estimator | A_early | A_deep | C = A_deep − A_early | 90% interval of C | "
         f"{FRACTION_LABEL} | Resamples left out of C (reasons) |"),
         "|---|---|---|---|---|---|---|"]
    rows = [("firth", est["firth"], bs["estimators"].get("firth")),
            ("ml_limit", est["ml_limit"], bs["estimators"].get("ml_limit"))]
    if r["primary"]["rule"] == "ml_limit_or_firth":
        rows.append(("primary", r["primary"], bs["primary"]))
    for name, e, s in rows:
        label = ESTIMATOR_NAME[name] + (f" (`{r['primary']['rule']}`)" if name == "primary"
                                        else "")
        c = None if s is None else s["contrast"]
        L.append(f"| {label} | {_value(e, 'A_early')} | {_value(e, 'A_deep')} | "
                 f"{_value(e, 'contrast')} | {_iv(c and c['interval'])} | "
                 f"{_pct(s and s['fraction_contrast_le_0'])} | {_left_out(c)} |")
    sm = est["statsmodels_stop"]
    L.append(f"| {ESTIMATOR_NAME['statsmodels_stop']} (point only) | {_value(sm, 'A_early')} | "
             f"{_value(sm, 'A_deep')} | {_value(sm, 'contrast')} | not bootstrapped | n/a | "
             "n/a |")
    return L


def _bootstrap_line(r: dict) -> str:
    bs = r["bootstrap"]
    p = bs["primary"]["contrast"]
    line = (f"Intervals: {bs['resamples']:,} game-cluster resamples, percentile "
            f"{bs['level']:.0%}, RNG seed SEED + {BOOT_SEED_OFFSET} = {bs['rng_seed']}. Each "
            "interval is over the resamples where its quantity is defined, so it is conditional "
            f"on that: C under the rule in force was defined in {p['n_defined']:,} of "
            f"{bs['resamples']:,}. With {bs['n_games']} games there are "
            f"{bs['distinct_possible']:,} distinct resamples ({bs['distinct_drawn']:,} drawn).")
    if bs["primary"]["n_firth_fallback"] is not None:
        why = bs["primary"]["firth_fallback_reasons"]
        line += (f" Under `ml_limit_or_firth`, {bs['primary']['n_firth_fallback']:,} resamples "
                 "used Firth because C was undefined in the ML limit"
                 + (" (" + "; ".join(f"{k}: {v:,}" for k, v in why.items()) + ")." if why
                    else "."))
    line += (f" \"{FRACTION_LABEL}\" is the share of the defined resamples with C ≤ 1e-9 "
             "(exploratory; H5 registers no such fraction).")
    fs = bs["estimators"].get("firth")
    if fs and fs["n_line_search"]:
        line += (f" Firth: `persistgym_h1h3.firth_fe_logit` returned no fit in "
                 f"{fs['n_line_search']:,} resamples, and `firth_line_search` gave their "
                 "estimate (the same penalized likelihood).")
    return line


def verdict_lines(r: dict) -> list[str]:
    p, est = r["primary"], r["estimates"]
    other = _other(p["source"])
    L = []
    if r["registered"]:
        L.append(f"**Verdict** (rule in force `{p['rule']}`, estimate from `{p['source']}`): "
                 f"**{p['verdict']}**.")
    else:
        L.append(f"Sign of C (rule in force `{p['rule']}`; exploratory, no verdict): "
                 f"**{p['verdict']}**.")
    if p.get("fallback_reason"):
        L.append(f"- Firth decides this reading: C is undefined in the ML limit "
                 f"({p['fallback_reason']}).")
    agrees = r["other_estimator_sign_agrees"]
    L.append(f"- The other estimator (`{other}`): C = {_value(est[other], 'contrast')}, sign "
             f"{_sign_word(est[other]['contrast'])}"
             + ("." if agrees is not False else ": **its sign differs (flagged)**."))
    sm = est["statsmodels_stop"]
    if sm["note"] == "statsmodels returned no fit":
        L.append("- statsmodels check: statsmodels returned no fit.")
    else:
        d = sm["max_abs_diff_vs_ml_limit"]
        L.append("- statsmodels check (point estimate): "
                 + ("no identified ML-limit AME to compare" if d is None else
                    f"largest difference from the ML limit {d:.2g}"
                    + (" (within 1e-6)" if d <= SM_TOL else " (**above 1e-6, flagged**)"))
                 + (f"; {sm['note']}: A_early {_value(sm, 'A_early')}, A_deep "
                    f"{_value(sm, 'A_deep')}" if sm["note"] else "") + ".")
    if est["firth"].get("optimizer") == FIRTH_OPTIMIZERS[1]:
        L.append("- Firth's point estimate comes from `firth_line_search`: "
                 "`persistgym_h1h3.firth_fe_logit` returned no fit (the same penalized "
                 "likelihood).")
    bs = r["bootstrap"]["estimators"]
    parts = []
    for name in ("firth", "ml_limit"):
        iv = bs[name]["logit_interaction"]["interval"] if name in bs else None
        parts.append(f"{name} {_value(est[name], 'logit_interaction')}"
                     + (f" (90% {_iv(iv)})" if name in bs else ""))
    L.append("- Logit-scale interaction γ_Ad − γ_Sd − γ_Ae (§9.3; no reading rests on it): "
             + "; ".join(parts)
             + (". **Its sign differs from C's (flagged).**" if p["logit_sign_disagrees"]
                else "."))
    ml = est["ml_limit"]
    how = "; ".join(f"{b}: " + (", ".join(f"{k} {v}" for k, v in ml["predictions"][b].items()
                                         if v) or "none") for b in MODEL_BANDS)
    L.append(f"- ML limit: {ml['n_separated_rows']} separated rows; predictions {how}.")
    ds = r["deep_support"]
    L.append(f"- Games by deep support: both {ds['both']}, Adapter only {ds['adapter only']}, "
             f"Standard only {ds['standard only']}, neither {ds['neither']}. Share of A_deep's "
             "rows in games where only one harness reached deep (an extrapolated "
             f"counterfactual): {_pct(r['extrapolated_share_deep'])}.")
    return L


def per_level_lines(r: dict) -> list[str]:
    h = r["harnesses"]
    L = [(f"| Level | Band | {h['standard']}: runs with the level, cleared/reached = P | "
         f"{h['provider_adapter']}: runs, cleared/reached = P |"), "|---|---|---|---|"]
    for x in r["per_level"]:
        s, a = x["standard"], x["provider_adapter"]
        L.append(f"| {x['level']} | {x['band']} | {s['n_runs']}, {_rate(s)} | "
                 f"{a['n_runs']}, {_rate(a)} |")
    return L


def _who(x: dict | None) -> str:
    if x is None:
        return "no run"
    last = "none" if x["last_reached_level"] is None else str(x["last_reached_level"])
    return f"{x['levels_completed']} / {last} / {x['ending']}"


def per_game_lines(r: dict) -> list[str]:
    h = r["harnesses"]
    names = [n for n in ("firth", "ml_limit")
             if r["per_game"] and n in r["per_game"][0]["estimators"]]
    head = (["Game", "Levels", f"{h['standard']}: completed / last reached / ending",
             f"{h['provider_adapter']}: same", "Deep support", "Rows early, deep"]
            + [f"Δ_{b} ({n})" for n in names for b in MODEL_BANDS])
    L = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for g in r["per_game"]:
        w = g["estimators"].get(names[0]) if names else None
        weights = ", ".join(str(w[b]["weight"]) for b in MODEL_BANDS) if w else "n/a"
        cells = [g["game"], str(g["level_count"]), _who(g["standard"]),
                 _who(g["provider_adapter"]), g["deep_support"], weights]
        cells += [_f(g["estimators"][n][b]["delta"]) for n in names for b in MODEL_BANDS]
        L.append("| " + " | ".join(cells) + " |")
    return L


def sensitivity_lines(s: dict) -> list[str]:
    L = [("Same rows minus each reached level a run ended on by an error ending (published "
         "ERROR_OR_CLOSED; ours API_ERROR, AGENT_ERROR, UNKNOWN, SCORECARD_CLOSED); budget "
         "endings keep theirs. Same seed, so the resamples are paired with the primary's."), ""]
    L += ["Dropped rows: " + ("; ".join(f"{x['game']} {x['harness']} level {x['level']} "
                                        f"({x['ending']})" for x in s["dropped_rows"])
                              if s["dropped_rows"] else "none") + "."]
    L += [""] + model_lines(s) + [""]
    L.append(f"Verdict on this sensitivity reading: **{s['primary']['verdict']}**.")
    return L


def reading_lines(r: dict, ours: bool = False) -> list[str]:
    L = raw_lines(r)
    if r["estimates"] is None:
        L += ["", ("**PROVISIONAL:** a unit lacks a counted run, so the model, the contrast and "
                  "the bootstrap are withheld; the raw tables above use the runs that exist (a "
                  "stand-in for a pending re-run is flagged in the run table).")]
        L += ["", "Per level:", ""] + per_level_lines(r)
        return L
    L += ["", ("Model: `cleared ~ harness × band + game fixed effects` on the early and deep "
              "rows; A_b the average marginal effect over the band's reached rows."), ""]
    L += model_lines(r) + ["", _bootstrap_line(r)]
    if ours:
        bs = r["bootstrap"]
        L.append(f"{bs['n_games']} games give only {bs['distinct_possible']} distinct "
                 f"resamples ({bs['distinct_drawn']} drawn).")
    L += [""] + verdict_lines(r)
    L += ["", "Per level (the registered descriptive table):", ""] + per_level_lines(r)
    L += ["", "Per game:", ""] + per_game_lines(r)
    if r["sensitivity_error_endings"] is not None:
        L += ["", "**Error-ending sensitivity** (§3 H5):", ""]
        L += sensitivity_lines(r["sensitivity_error_endings"])
    return L


def exploratory_lines(r: dict) -> list[str]:
    L = raw_lines(r)
    if r["estimates"] is None:
        return L
    L += [""] + model_lines(r) + ["", _bootstrap_line(r), ""]
    p = r["primary"]
    other = r["estimates"][_other(p["source"])]["contrast"]
    L.append(f"Sign of C (rule in force `{p['rule']}`; exploratory, no verdict): "
             f"**{p['verdict']}**; the other estimator's sign: {_sign_word(other)}.")
    if p.get("fallback_reason"):
        L.append(f"Firth decides this reading: C is undefined in the ML limit "
                 f"({p['fallback_reason']}).")
    ds = r["deep_support"]
    L.append(f"Games by deep support: both {ds['both']}, Adapter only {ds['adapter only']}, "
             f"Standard only {ds['standard only']}, neither {ds['neither']}.")
    L += ["", "Per level (exploratory):", ""] + per_level_lines(r)
    return L


def _common_support_lines(name: str, cs: dict | None) -> list[str]:
    if cs is None:
        return []
    L = ["", f"### Common support, {name} (exploratory)", ""]
    if not cs["computed"]:
        return L + [f"Not computed: {cs['why_not']}."]
    return L + [f"Games where both harnesses reached a deep level: {', '.join(cs['games'])}.",
                ""] + exploratory_lines(cs["reading"])


def _definitions(h: dict) -> list[str]:
    rule = h["primary_estimator"]
    other = h["settings"]["alternative_rule"]
    return [("> **Definitions.** Reached(ℓ): at least one action on ℓ (`level_actions[ℓ] > 0`, "
            "RESETs included; D35). Cleared(ℓ): ℓ ≤ levels completed. Bands: early = levels "
            f"1-2, deep = levels ≥ {DEEP_MIN} (pooled); level 3 is reported, not in the "
            "contrast. The level in play when the action budget or the 12 h clock ended a run "
            "counts as reached and not cleared if the run took at least one action on it "
            "(D35; R5)."),
            ">",
            ("> A_b: the Adapter-minus-Standard difference in P(clear | reached) in band b, the "
            "average marginal effect over every reached row of the band from both harnesses "
            "(a game weighs by its reached level-rows in the band); C = A_deep − A_early."),
            ">",
            (f"> Estimator in force: `{rule}` ({RULE_TEXT.get(rule, rule)}; the ruling: "
            f"`results/decisions.md`, 2026-10-10, \"{RULING_ENTRY}\"); the other rule is "
            f"`{other}`. Both estimators "
            "(Firth's penalized logit and the maximum-likelihood limit) are shown. "
            f"Bootstrap: games resampled with replacement, RNG SEED + {BOOT_SEED_OFFSET} = "
            f"{h['bootstrap_seed']}, {h['settings']['n_boot']:,} resamples, percentile 90%.")]


def _run_table(h: dict) -> list[str]:
    L = [("| Run | Game | Config | Counted | In reading | Exit reasons (agent; launcher) | "
          "Ending (D19) | Kind | Levels completed | Last reached | Ended on | "
          "Dropped in sensitivity | Flags |"),
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in h["ours_runs"]:
        levels = "n/a" if r["levels_completed"] is None else \
            f"{r['levels_completed']} of {r['level_count']}"
        L.append(f"| `{r['run_id']}` | {r['game']} | {r['config']} | {r['counted']} | "
                 f"{r['in_reading']} | {r['agent_exit_reason']}; {r['exit_reason']} | "
                 f"{r['d19_ending']} | {r['ending_kind']} | {levels} | "
                 f"{r['last_reached_level']} | {r['ended_level']} | "
                 f"{r['dropped_in_sensitivity'] or '-'} | {'; '.join(r['flags']) or '-'} |")
    return L


def not_shown_lines(h: dict) -> list[str]:
    """The caveats; those about one data set are printed only when it was read."""
    pub, ours = h["published"] is not None, h["ours"] is not None
    shares = []
    for name, r in (("published", h["published"]), ("ours", h["ours"])):
        if r is not None and r["extrapolated_share_deep"] is not None:
            shares.append(f"{name} {_pct(r['extrapolated_share_deep'])}")
    blind = []
    if pub:
        blind.append("On the published data, the per-game scores, LP85's ending and the "
                     "inferred endings were seen, and the operational slice revealed each run's "
                     "last level.")
    if ours:
        blind.append("Our S0 and S4 runs were seen before R6 (§17.6 change 4).")
    L = ["## What it does not show", ""]
    if blind:
        L.append("- **Not blind.** " + " ".join(blind))
    L += [("- **Observational, one run per game and harness.** Depth is confounded with game "
           "difficulty beyond the game fixed effects and with level difficulty within a game, "
           "and run-to-run variation is not separated from the harness."),
          ("- **Conditioning on reached is selection by the harness.** The harness that gets "
           "further reaches deep levels more often, so A_deep compares harnesses over "
           "different selections of runs. It is not the harness's effect on clearing a fixed "
           "level."),
          ("- **Extrapolation.** Part of A_deep rests on games where only one harness reached "
           "deep (share of the deep rows: " + ("; ".join(shares) or "n/a") + "), through the "
           "model's counterfactual for the other harness; the common-support reading is "
           "exploratory."),
          ("- **The estimator matters at this size.** Firth's estimate and the "
           "maximum-likelihood limit can differ in size and in sign; both are shown, and the "
           "rule in force is named."),
          ("- **Endings.** Published endings are inferred, and ERROR_OR_CLOSED pools errors "
           "with stops from outside the harness. The clock and the action budget leave the "
           "last level in play reached and not cleared when it had an action, so a slower "
           "pace lowers P(clear | reached) at the last level reached (R5).")]
    if ours:
        L.append("- **Our 4 games are selected, so our reading is conditional.** The path games "
                 "were chosen by D14's rule (§7.2): published high-effort gap ≥ 20, both "
                 "published runs ≤ $60, and a normal Standard-high ending. They are games where "
                 "the Adapter is known to help, so H5 on our runs is conditional on \"games "
                 "where the Adapter helps\" (§7.2, PLAN §8.3), and the Adapter's advantage there "
                 "may be larger than on the public set. Our S0 also differs from ARC's Standard "
                 "(thought summaries, API surface, period; §15).")
    if pub and ours:
        L.append("- **The data sets overlap.** The 4 path games are among the 25 published "
                 "games, so the two readings are not independent.")
    L.append("- **Descriptive only.** Percentile intervals"
             + (", 35 distinct resamples for our 4 games" if ours else "")
             + ", and no claim of statistical significance (H5 is outside the Holm family); "
             f"\"{FRACTION_LABEL}\" and the raw pooled contrast are exploratory.")
    L.append("- **Narrow.** One model at high effort; other efforts are exploratory; no other "
             "model was pulled; nothing here compares models.")
    return L


def summary_lines(h: dict) -> list[str]:
    L = ["# H5 on ARC: the Adapter advantage by level depth (PREREG §3 H5, D35; R6 change 4)",
         "",
         (f"Computed {h['generated_utc']} at commit {h['git_commit'][:7]} (dirty: "
          f"{h['git_dirty']}) by `{h['settings']['command']}`, from "
          f"`{h['inputs']['results_root']}`."), "",
         "Descriptive only; H5 is outside the Holm family (§9.4).", "",
         f"**Status: {h['status']}.**"]
    if h["provisional_reasons"]:
        L += [""] + [f"- {x}" for x in h["provisional_reasons"]]
    L += [""] + _definitions(h)
    p = h["published"]
    if p is not None:
        pinned = h["inputs"]["published_sha256_matches_pinned"]
        L += ["", "## Published runs, high effort (registered; not blind)", "",
              (f"{p['n_games']} games, {p['n_runs']} runs (one per game and harness), Standard "
               "vs Provider Adapter; per_run.csv sha256 "
               f"`{h['inputs']['published_per_run_sha256']}`"
               + (" (the pinned file)." if pinned else
                  " (**not the pinned file: PROVISIONAL**).")), ""]
        L += reading_lines(p)
    o = h["ours"]
    if o is not None:
        L += ["", ("## Our runs, S0 vs S4 on the 4 path games (registered; not blind, R6 change "
                  "4)"), "",
              (f"Games in draw order: {', '.join(o['games'])}; the counted seed-1 run of each "
               "(game, config), a re-run replacing its original (§7.5)."), ""]
        L += reading_lines(o, ours=True)
        L += ["", "Runs (S0 and S4; a replaced original is listed and is not in H5):", ""]
        L += _run_table(h)
    L += ["", "## Exploratory (§9.10)"]
    x = h["published_exploratory"]
    if x is None and (p is None or p["common_support"] is None) and \
            (o is None or o["common_support"] is None):
        L += ["", "Not computed (`--no-exploratory`, or no data set read)."]
    if x is not None:
        for effort, r in x["efforts"].items():
            L += ["", f"### Published runs, effort {effort} (exploratory)", ""]
            L += (exploratory_lines(r) if r is not None else
                  [("Skipped (a data problem; the registered reading stands): "
                   f"{x['skipped'].get(effort, 'not read')}.")])
        L += ["", f"Other models: {x['other_models']}."]
    if p is not None:
        L += _common_support_lines("published runs, high effort", p["common_support"])
    if o is not None:
        L += _common_support_lines("our runs", o["common_support"])
    L += ["", "## Checks", ""]
    L += [f"- {w}" for w in h["warnings"]] or ["- No warnings."]
    L += [f"- skipped `{s['folder']}`: {s['reason']}" for s in h["skipped"]]
    L += [""] + not_shown_lines(h)
    L += ["", ("This script was written and tested on synthetic data only before its first real "
              "run.")]
    return L


# --- main ----------------------------------------------------------------------------------------

def _json_default(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


def counted_runs(h: dict) -> list[str]:
    """Our counted runs in the reading (stand-ins excluded)."""
    return [r["run_id"] for r in h["ours_runs"] if r["in_reading"] and r["counted"]
            and not any(f.startswith("stand-in") for f in r["flags"])]


def write(out_dir: Path, run_id: str, h: dict, text: str, git: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "h5.json").write_text(
        json.dumps(h, indent=2, ensure_ascii=False, default=_json_default) + "\n",
        encoding="utf-8", newline="\n")
    (out_dir / "summary.md").write_text(text, encoding="utf-8", newline="\n")
    s = h["settings"]
    config = {"prereg": "PREREG.md §3 H5, D35, §17.6 change 4, §17.5 'Not H5'",
              "bands": s["bands"], "registered_effort": REGISTERED_EFFORT, "n_boot": s["n_boot"],
              "level": LEVEL, "bootstrap_seed": h["bootstrap_seed"],
              "primary_estimator": h["primary_estimator"],
              "alternative_rule": s["alternative_rule"],
              "published_per_run_sha256": h["inputs"]["published_per_run_sha256"],
              "data_sets": [k for k in ("published", "ours") if h[k] is not None],
              "exploratory": s["exploratory"], "status": h["status"], "inputs": h["inputs"]}
    return runmeta.write_meta(
        out_dir, git=git, experiment=EXPERIMENT, run_id=run_id, cell_or_config="h5",
        config=config, model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
        repeat_index=None, seeds={"bootstrap": h["bootstrap_seed"]},
        started_utc=h["generated_utc"], finished_utc=runmeta.utc_now(),
        exit_reason="completed" if h["status"] == FINAL else "completed_provisional",
        tokens=None, cost_usd=0.0, raw_transcript_path=None, outputs=list(OUTPUTS),
        paid_calls=0, runs=counted_runs(h))


def _progress(label: str, k: int, n: int) -> None:
    print(f"  {label}: {k:,} of {n:,} resamples", file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--results-root", type=Path, default=RESULTS,
                    help="the results folder: arc_path/, draw/, costs.csv and the default "
                         "output (default: this checkout's results/)")
    ap.add_argument("--published", type=Path, default=None,
                    help=f"the published slice folder (default: <results root>/{PUBLISHED_SLICE})")
    ap.add_argument("--data", choices=DATA_CHOICES, default="both",
                    help="which registered data sets to read (default: both)")
    ap.add_argument("--boot", type=int, default=N_BOOT,
                    help=f"bootstrap resamples (default {N_BOOT:,}; any other value is "
                         "PROVISIONAL)")
    ap.add_argument("--no-exploratory", action="store_true",
                    help="skip the exploratory readings (other efforts, common support)")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="default: <results root>/arc_h5/<UTC>/")
    ap.add_argument("--no-write", action="store_true", help="print only")
    ap.add_argument("--allow-incomplete", action="store_true",
                    help="our runs: report the raw tables (PROVISIONAL, no model) while a unit "
                         "lacks a counted run")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    now = datetime.now(UTC)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = a.results_root.resolve()
    args = sys.argv[1:] if argv is None else argv
    command = " ".join(["uv run python -m analysis.arc_h5", *args])
    git = runmeta.git_state()
    try:
        h = compute(root, now.isoformat(timespec="seconds"), git,
                    published_dir=a.published.resolve() if a.published else None, data=a.data,
                    boot=a.boot, exploratory=not a.no_exploratory,
                    allow_incomplete=a.allow_incomplete, progress=_progress, command=command)
    except (Refusal, cc.Refusal, am.Refused) as e:
        print(f"H5 refused: {e}", file=sys.stderr)
        return 2
    text = "\n".join(summary_lines(h)) + "\n"
    print(text)
    if not a.no_write:
        out = a.out_dir or root / EXPERIMENT / run_id
        write(out, run_id, h, text, git)
        print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
