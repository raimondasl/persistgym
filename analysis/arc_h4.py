"""H4 on the ARC path runs, as amended by R6 (PREREG §3 H4, §17.6 change 3; §17.5 at K = 150).

Run: ``uv run python -m analysis.arc_h4 [--results-root DIR] [--no-write]
[--allow-incomplete] [--with-s1]`` ($0: it reads files only). It writes
``<results root>/arc_h4/<UTC>/h4.json``, ``summary.md`` and ``meta.json``, and prints the
summary. Everything here is descriptive: 4 units, no significance claims (§3 H4, D34).

**Inputs**, all under the results root (default ``results/``), read with
``analysis.checkpoint_c``'s code (imported, not copied):

* every folder in ``arc_path/`` (`checkpoint_c.discover`: the allowlisted ``meta.json`` fields
  and the scored ``scorecard.json``; a folder whose ``meta.json`` is not an ``arc_path`` run is
  refused, so a pilot folder, blinded under PREREG §11, is never read). More ``meta.json``
  fields are read for the run table (`EXTRA_META`): ``model_returned``, ``context_trims``,
  ``config_hash`` and, of ``config``, only ``runtime.compaction.summary_max_output_tokens``
  (the summary budget: 8,192 before R7 and 65,536 under it for S1 and S2; none for S0 and S4);
* ``costs.csv``: the ARC pilot rows' ``latency_s`` only, for D20's yardsticks (R6's scaled one
  for S1 and S2 included, `checkpoint_c.d20_check`);
* ``draw/*/draw.json``: the 4 path games (their order is the units' order) and SEED (D15);
* if they are under the results root (``raw/arc_path/<run_id>/harness/compaction_*.json``,
  gitignored, so only in the checkout that ran them), block 2's S4 runs' harness compaction
  records, and of each only ``attempts`` and ``usage.completion_tokens``: for the note on
  σ_replay under R7 (below).

**Units and counted runs** (§17.6 change 3, §7.5). A unit is one path game at replicate 1, so
there are 4. Each (game, config) uses its counted run (`checkpoint_c.resolve_unit`): a re-run
(seed 101) replaces its original; FT09's S0 is its seed-101 re-run. A re-run that also ends
re-run-eligible is counted as is and flagged (D19).

**R7** (the researcher's decision of 2026-10-10, option B; `checkpoint_c`'s module docstring):
a unit whose counted S1 or S2 run ended by the summarizer failure gets one R7 replacement
(seed 201, ``r7_replaces`` that run) under R7's summary budget of 65,536 output tokens; it is
the unit's counted run, and its own one D19 re-run (seed 301) replaces it in turn, so the chain
is original → (re-run) → (R7 replacement) → (its re-run). An R7 replacement whose re-run has not
landed while it ended re-run-eligible is pending, as an original is. ``meta.json`` does not say
which ``AGENT_ERROR`` was the summarizer failure, so the script cannot tell whether a unit is
due an R7 replacement: it flags a counted S1 or S2 run that ended ``AGENT_ERROR`` under the
8,192 budget without one, and an R7 replacement of a run that did not end ``AGENT_ERROR`` or
that does not have the 65,536 budget.

**Configs.** S0, S2 and S4. S1 enters only with ``--with-s1``. The analyst passes it only if
``results/decisions.md`` records "S1: yes", merged to ``main`` before the first block-3 ARC
run started (§17.6 change 1); the script does not check this. Without it, S1 runs are
exploratory (§9.10) and stay out of every reading here; they are listed and flagged.

**Refusal.** Without ``--allow-incomplete`` the script refuses (exit 2) while any unit lacks a
counted run of a needed config that it can score: there is no run; the run is
re-run-eligible and its re-run has not landed; it ended ``TIME_BUDGET`` and its D20 check
cannot be computed; or its scorecard cannot be scored. Inconsistent folders (checkpoint_c's
link checks) are refused in any case. With ``--allow-incomplete`` it marks the output
**PROVISIONAL**, reports what exists (RHAE per game and config, each config's mean over the
units it has, and G if S0 and S4 are complete), and withholds the shares, the predictions,
the intervals and the sensitivity analyses.

**The reading** (`reading`), on the scorecard's RHAE (`arc_action_matched.Run.score_scorecard`):

* R̄_c is the mean RHAE over the 4 units, and G = R̄_S4 − R̄_S0.
* **Without S1:** σ_pn = (R̄_S2 − R̄_S0)/G, the loss-policy change and the notes removal
  together, and σ_replay = (R̄_S4 − R̄_S2)/G; they sum to 1. σ_loss and σ_notes are not
  identified. Prediction B holds iff σ_replay ≥ 1/2. Prediction A is tested in its replay
  clause only: "A contradicted" iff σ_replay > 1/2, otherwise "A's replay clause holds; A is
  not tested in full". The report never says that A holds.
* **With S1:** the frozen shares σ_loss = (R̄_S1 − R̄_S0)/G, σ_notes = (R̄_S2 − R̄_S1)/G
  and σ_replay, and the frozen predictions: A holds iff σ_loss ≥ 1/3, σ_replay ≤ 1/2 and
  −0.10 ≤ σ_notes ≤ 0.10; B holds iff σ_replay ≥ 1/2. The report says which hold.
* The shares, the predictions and everything built on the shares are reported only if
  G ≥ 10 (D34). Point estimates are computed in exact rational arithmetic from the
  scorecards' values (`fractions.Fraction` of each value's decimal as written), so a share
  that sits on a threshold is judged exactly.
* **Intervals:** 10,000 resamples of the units with replacement, a unit's configs kept
  together; percentile 90% intervals (``numpy.quantile`` at 0.05 and 0.95, its default linear
  method); RNG ``numpy.random.default_rng(SEED + 30)``, a fresh generator for each reading, so
  readings over the same units use the same resamples. Reported next to them: the fraction of
  resamples with G ≤ 0, and that n units give only C(2n − 1, n) distinct resamples (35 for
  4 units). A resample whose G is exactly 0 has no shares: it is left out of the shares'
  intervals and counted.
* **Also registered:** the per-game step differences (RHAE_S2 − RHAE_S0 and RHAE_S4 − RHAE_S2,
  plus S1's steps); the 4 leave-one-game-out values of σ_replay, each over the other 3 games
  and shown with its G (flagged where that G is below 10); and D30's σ_replay ≥ 2/3,
  descriptive.

**Sensitivity analyses** (§3 H4, as frozen, on the same units): the original runs instead of
their re-runs, where the original is each chain's first run (§17.7 change 4 (i)): in a unit
with an R7 replacement it is the seed-1 original, so this reading undoes D19 and R7 together
(a unit whose original cannot be scored is left out and listed); and every unit that contains
a counted run ending ``COST_CAP`` left out, its configs together. **R7's** (§17.7 change 4
(ii)): the counted runs without R7, that is each R7 replacement (or its re-run) swapped for
the run it replaced, the old config's counted run that ended in the summarizer failure
(`checkpoint_c.Unit.before_r7`, for FT09 S2 its seed-101 re-run); the replaced runs are listed
with both values. Every replaced run is in one of the two, except an R7 replacement that has
its own D19 re-run: neither reading uses it, and its row says so.

**σ_replay under R7** (§17.7 change 4). Once a counted S2 run played under R7's 65,536, the
S2→S4 step also lowers the summary budget to S4's 8,192, so σ_replay is labelled with a note
(`sigma_replay_note`): whether the 8,192 budget bound in any S4 run of block 2 (its summaries,
retries and largest output per attempt), computed from those runs' harness compaction records
when they are under the results root, and otherwise quoted from ``results/decisions.md``
(2026-10-10, amendment R7) and said to be quoted.

**At K = 150** (§17.5 change 1). The same reading with RHAE_K (`arc_action_matched.Run.at_k`)
in place of RHAE, secondary and descriptive: the predictions are judged on the primary
reading only, so their conditions at K are reported, not judged. A unit is left out (and
listed) if any of its counted runs has no matched values: it cannot be scored, or it fails
``analysis.arc_action_matched``'s checks. Censored runs enter at their final values, which are
lower bounds, with the number of censored counted runs per config; as sensitivity analyses,
the units that contain a censored counted run left out, the original runs, the counted runs
without R7, and the ``COST_CAP`` units left out. Next to them: the mean number of levels
cleared within K per config, and its S0→S4 difference.

**Per run**: both endings, D19's reading, RHAE, levels, actions, median seconds per model call,
the returned model string, the config hash and summary budget (which config a run played under,
before or under R7) and, for S1 and S2 runs, ``context_trims`` (patch 0016: the summary
backstop never drops turns, so it should be 0; "not recorded" if ``meta.json`` has no value).

**What is written** is built from allowlists (`TOP_FIELDS`, `RUN_FIELDS`, `OUTPUTS`): no
transcript path, key, token count or other ``meta.json`` field is copied.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path

import numpy as np

from analysis import arc_action_matched as am
from analysis import checkpoint_c as cc
from common import costs, runmeta

REPO_ROOT = runmeta.REPO_ROOT
RESULTS = REPO_ROOT / "results"
REPLICATE = 1
CONFIGS = ("S0", "S2", "S4")               # §17.6 change 3, without S1
CONFIGS_S1 = ("S0", "S1", "S2", "S4")      # with --with-s1
G_MIN = Fraction(10)                       # D34: shares only if G >= 10
HALF = Fraction(1, 2)                      # Predictions A (replay clause) and B
LOSS_MIN = Fraction(1, 3)                  # Prediction A: sigma_loss >= 1/3
NOTES_BAND = Fraction(1, 10)               # Prediction A: -0.10 <= sigma_notes <= 0.10
D30_DOMINATED = Fraction(2, 3)             # D30, descriptive
N_BOOT = 10_000
BOOT_SEED_OFFSET = 30                      # §17.6 change 3: SEED + 30
LEVEL = 0.90
QUANTILES = (0.05, 0.95)                   # percentile 90% interval
K = am.REGISTERED_K                        # §17.5
COST_CAP = "COST_CAP"
TRIM_CONFIGS = ("S1", "S2")                # summary compaction: context_trims should be 0
OLD_SUMMARY_BUDGET = 8_192                  # S1 and S2 before R7
R7_SUMMARY_BUDGET = 65_536                 # R7: the step requests' max_output_tokens
S4_SUMMARY_BUDGET = 8_192                  # S4's, unchanged by R7
SUMMARIZER_FAILURE_ENDING = "AGENT_ERROR"  # how the summarizer failure ends a run (R7)
# Block 2's S4 summaries as recorded in results/decisions.md (2026-10-10, amendment R7) and
# PREREG §17.7 change 4, quoted only where the raw compaction records are not under the
# results root (`s4_summaries`).
RECORDED_S4_SUMMARIES = {"summaries": 132, "retries": 0, "max_output_tokens_per_attempt": 3_073}
RECORDED_S4_SOURCE = ("results/decisions.md (2026-10-10, amendment R7) and PREREG §17.7 "
                      "change 4")
A_CONTRADICTED = "A contradicted"
A_REPLAY_HOLDS = "A's replay clause holds; A is not tested in full"

EXTRA_META = ("model_returned", "context_trims", "config_hash", "config")
"""The meta.json fields read here beyond checkpoint_c's `META_FIELDS` (`config`: only its
`runtime.compaction.summary_max_output_tokens`)."""

RUN_FIELDS = ("run_id", "game", "config", "replicate", "seed", "rerun_of", "r7_replaces",
              "replaced_by", "counted", "in_reading", "started_utc", "agent_exit_reason",
              "exit_reason", "d19_ending", "rerun_eligible", "rhae", "levels_completed",
              "level_count", "actions", "median_s_per_call", "model_returned", "config_hash",
              "summary_max_output_tokens", "context_trims", "checks_passed", "status_at_K",
              "rhae_at_K", "levels_cleared_at_K", "flags")
TOP_FIELDS = ("generated_utc", "git_commit", "git_dirty", "prereg_version", "status",
              "provisional_reasons", "warnings", "inputs", "path_games", "configs", "with_s1",
              "seed", "bootstrap_seed", "units", "primary", "sensitivity", "at_k", "partial",
              "sigma_replay_note", "run_dates", "context_trims", "runs", "skipped")
OUTPUTS = ("h4.json", "summary.md")
FINAL, PROVISIONAL = cc.FINAL, cc.PROVISIONAL


# --- the shares and predictions ------------------------------------------------------------

def _exact(v: float) -> Fraction:
    """The decimal the scorecard wrote, as a fraction: ``repr`` of a float is the shortest
    decimal that reads back to it, so 0.3 is 3/10 and not the binary float's value."""
    return Fraction(repr(v)) if isinstance(v, float) else Fraction(v)


def _means(values: dict[str, dict[str, Fraction]], games: list[str],
           configs: tuple[str, ...]) -> dict[str, Fraction]:
    return {c: sum((values[g][c] for g in games), Fraction(0)) / len(games) for c in configs}


def _step_names(with_s1: bool) -> dict[str, tuple[str, str]]:
    """Each share's step (from config, to config)."""
    if with_s1:
        return {"sigma_loss": ("S0", "S1"), "sigma_notes": ("S1", "S2"),
                "sigma_replay": ("S2", "S4")}
    return {"sigma_pn": ("S0", "S2"), "sigma_replay": ("S2", "S4")}


def shares(m: dict, with_s1: bool) -> dict | None:
    """The step shares from the config means `m`; None when G = 0."""
    g = m["S4"] - m["S0"]
    if g == 0:
        return None
    return {name: (m[b] - m[a]) / g for name, (a, b) in _step_names(with_s1).items()}


def predictions(sh: dict[str, Fraction], with_s1: bool) -> dict:
    """Predictions A and B on point-estimate shares (§3 H4; §17.6 change 3 without S1)."""
    replay = sh["sigma_replay"]
    b = {"rule": "sigma_replay >= 1/2", "holds": replay >= HALF}
    if not with_s1:
        return {"B": b,
                "A": {"rule": "replay clause only: A is contradicted iff sigma_replay > 1/2; "
                              "its sigma_loss and sigma_notes conditions need S1",
                      "reading": A_CONTRADICTED if replay > HALF else A_REPLAY_HOLDS}}
    conditions = {"sigma_loss >= 1/3": sh["sigma_loss"] >= LOSS_MIN,
                  "sigma_replay <= 1/2": replay <= HALF,
                  "-0.10 <= sigma_notes <= 0.10": -NOTES_BAND <= sh["sigma_notes"] <= NOTES_BAND}
    a = all(conditions.values())
    which = "both" if a and b["holds"] else "A only" if a else "B only" if b["holds"] else \
        "neither"
    return {"A": {"rule": "sigma_loss >= 1/3 and sigma_replay <= 1/2 and "
                          "-0.10 <= sigma_notes <= 0.10", "conditions": conditions, "holds": a},
            "B": b, "which": which}


def _interval(x: np.ndarray) -> list[float] | None:
    if len(x) == 0:
        return None
    lo, hi = np.quantile(x, QUANTILES)
    return [float(lo), float(hi)]


def bootstrap(values: dict[str, dict[str, float]], configs: tuple[str, ...], with_s1: bool,
              seed: int, boot: int = N_BOOT, with_shares: bool = True) -> dict:
    """Resample the units (a unit's configs together) `boot` times from a fresh generator
    seeded `seed`; percentile intervals of each R̄_c, G and, if `with_shares`, each share."""
    games = list(values)
    n = len(games)
    mat = np.array([[float(values[g][c]) for c in configs] for g in games])
    idx = np.random.default_rng(seed).integers(0, n, size=(boot, n))
    m = mat[idx].mean(axis=1)
    col = {c: m[:, i] for i, c in enumerate(configs)}
    gap = col["S4"] - col["S0"]
    out = {"resamples": boot, "rng_seed": seed, "level": LEVEL, "method": "percentile",
           "distinct_possible": math.comb(2 * n - 1, n),
           "distinct_drawn": len(np.unique(np.sort(idx, axis=1), axis=0)),
           "fraction_G_le_0": float(np.mean(gap <= 0)),
           "means": {c: _interval(col[c]) for c in configs}, "G": _interval(gap),
           "shares": None, "shares_undefined": None}
    if with_shares:
        ok = gap != 0
        out["shares"] = {name: _interval((col[b] - col[a])[ok] / gap[ok])
                         for name, (a, b) in _step_names(with_s1).items()}
        out["shares_undefined"] = int((~ok).sum())
    return out


def reading(values: dict[str, dict[str, float]], configs: tuple[str, ...], with_s1: bool,
            boot_seed: int, boot: int = N_BOOT) -> dict:
    """H4's quantities over the units in `values` ({game: {config: RHAE}})."""
    games = list(values)
    out = {"n_units": len(games), "units": games, "means": None, "G": None,
           "shares_reported": False, "shares": None, "predictions": None,
           "d30_dominated": None, "per_game": [], "leave_one_out": None, "bootstrap": None}
    if not games:
        return out
    exact = {g: {c: _exact(values[g][c]) for c in configs} for g in games}
    m = _means(exact, games, configs)
    gap = m["S4"] - m["S0"]
    out["means"] = {c: float(v) for c, v in m.items()}
    out["G"] = float(gap)
    out["shares_reported"] = gap >= G_MIN
    steps = _step_names(with_s1)
    out["per_game"] = [{"game": g, "rhae": dict(values[g]),
                        **{f"{b}_minus_{a}": values[g][b] - values[g][a]
                           for a, b in steps.values()},
                        "S2_minus_S0": values[g]["S2"] - values[g]["S0"],
                        "S4_minus_S0": values[g]["S4"] - values[g]["S0"]} for g in games]
    if out["shares_reported"]:
        sh = shares(m, with_s1)
        out["shares"] = {k: float(v) for k, v in sh.items()}
        out["predictions"] = predictions(sh, with_s1)
        out["d30_dominated"] = sh["sigma_replay"] >= D30_DOMINATED
        if len(games) > 1:
            loo = []
            for g in games:
                rest = [x for x in games if x != g]
                mr = _means(exact, rest, configs)
                g_rest = mr["S4"] - mr["S0"]
                sr = shares(mr, with_s1)
                loo.append({"left_out": g, "n_units": len(rest), "G": float(g_rest),
                            "G_below_10": g_rest < G_MIN,
                            "sigma_replay": None if sr is None else float(sr["sigma_replay"])})
            out["leave_one_out"] = loo
    out["bootstrap"] = bootstrap(values, configs, with_s1, boot_seed, boot,
                                 with_shares=out["shares_reported"])
    return out


# --- runs and units ------------------------------------------------------------------------

@dataclass
class Data:
    root: Path
    draw_path: Path
    costs_csv: Path
    games: list[str]
    seed: int
    configs: tuple[str, ...]
    with_s1: bool
    entries: list[cc.Entry]
    units: dict[tuple[str, str], cc.Unit]
    d20: dict[str, dict | None]
    eligible: dict[str, bool | None]
    extra: dict[str, dict]
    incomplete: list[str]
    warnings: list[str]
    bare: list[tuple[str, str]]


def _summary_budget(config) -> int | None:
    """The profile's summary budget (`runtime.compaction.summary_max_output_tokens`), or None
    for a profile without summary compaction (S0, S4)."""
    runtime = config.get("runtime") if isinstance(config, dict) else None
    compaction = runtime.get("compaction") if isinstance(runtime, dict) else None
    v = compaction.get("summary_max_output_tokens") if isinstance(compaction, dict) else None
    return None if v is None else int(v)


def _extra(e: cc.Entry) -> dict:
    raw = json.loads((e.folder / "meta.json").read_text(encoding="utf-8"))
    return {"model_returned": raw.get("model_returned"),
            "context_trims": raw.get("context_trims"), "config_hash": raw.get("config_hash"),
            "summary_max_output_tokens": _summary_budget(raw.get("config"))}


def _budget_word(v: int | None) -> str:
    return "none" if v is None else f"{v:,}"


def load(root: Path, with_s1: bool) -> Data:
    """The path games, SEED and every unit's counted run. Raises cc.Refusal or am.Refused."""
    draw_path = cc.the_draw(root)
    draw = json.loads(draw_path.read_text(encoding="utf-8"))
    games = [str(g).upper() for g in draw["games"]]
    if len(games) != 4:
        raise cc.Refusal(f"draw.json names {len(games)} path games, not 4 (§7.2)")
    seed = int(draw["seed"]["seed"])
    costs_csv = root / "costs.csv"
    if not costs_csv.is_file():
        raise cc.Refusal(f"no costs.csv under {root} (the pilots' latency_s, for D20)")
    try:
        pilots = cc.pilot_latency(costs.read_rows(costs_csv))
    except ValueError as e:
        raise cc.Refusal(f"cannot read {costs_csv}: {e}") from None
    entries, bare = cc.discover(root / cc.EXPERIMENT)
    cc.check_links(entries)
    d20 = {e.run_id: cc.d20_check(e, entries, pilots) for e in entries if not e.truncated}
    eligible = {e.run_id: cc.rerun_eligible(e, d20[e.run_id])
                for e in entries if not e.truncated}
    extra = {e.run_id: _extra(e) for e in entries}
    configs = CONFIGS_S1 if with_s1 else CONFIGS
    units: dict[tuple[str, str], cc.Unit] = {}
    incomplete: list[str] = []
    warnings: list[str] = [f"{name}: {why}" for name, why in bare]
    for g in games:
        for c in configs:
            u = cc.resolve_unit(entries, g, c, eligible, REPLICATE)
            units[(g, c)] = u
            if u.original is None:
                incomplete.append(f"{g} {c}: no seed-{REPLICATE} run yet")
                continue
            o = u.head                         # the original, or the R7 replacement
            if u.pending:
                incomplete.append(f"{g} {c}: {o.run_id} ended "
                                  f"{cc.why_ending(o, d20[o.run_id], eligible[o.run_id])}; "
                                  "its one re-run has not landed")
            elif u.head_rerun is None and eligible[o.run_id] is None:
                incomplete.append(f"{g} {c}: {o.run_id} ended TIME_BUDGET and its D20 check "
                                  "cannot be computed, so whether it is re-run is unknown")
            for x, y in ((u.original, u.rerun), (u.r7, u.r7_rerun)):
                if x is not None and y is not None and eligible[x.run_id] is False:
                    warnings.append(f"{g} {c}: {x.run_id} was re-run although its ending "
                                    f"({cc.why_ending(x, d20[x.run_id], False)}) is final "
                                    "under D19/D20 as computed here; the re-run still replaces "
                                    "it (§7.5)")
            e = u.counted
            if e.run is None:
                incomplete.append(f"{g} {c}: counted run {e.run_id} cannot be scored "
                                  f"({e.skip_reason})")
            elif not e.run.checks_passed:
                warnings.append(f"{e.run_id}: fails analysis.arc_action_matched's checks "
                                "(no matched values, §17.5)")
            r = u.head_rerun
            if r is not None and eligible[r.run_id]:
                warnings.append(f"{g} {c}: re-run {r.run_id} also ended "
                                f"{r.d19_ending}, re-run-eligible: it is counted as is, "
                                "flagged (D19 allows no second re-run)")
            warnings += _r7_warnings(u, extra, pending=u.pending)
    if not with_s1:
        s1 = [e.run_id for e in entries if e.config == "S1" and not e.truncated]
        if s1:
            warnings.append(f"S1 runs exist ({', '.join(s1)}) but --with-s1 was not passed: "
                            "they stay out of this reading. Pass --with-s1 only if "
                            "results/decisions.md records \"S1: yes\", merged to main before "
                            "the first block-3 ARC run (§17.6 change 1)")
    for e in entries:
        dd = d20.get(e.run_id)
        if dd and not dd["readings_agree"]:
            warnings.append(f"{e.run_id}: D20 readings disagree (as of its start: incident "
                            f"{dd['as_of_start']['incident']}; on the final counted set: "
                            f"{dd['final_counted_set']['incident']}); the as-of reading is "
                            "used")
    return Data(root=root, draw_path=draw_path, costs_csv=costs_csv, games=games, seed=seed,
                configs=configs, with_s1=with_s1, entries=entries, units=units, d20=d20,
                eligible=eligible, extra=extra, incomplete=incomplete, warnings=warnings,
                bare=bare)


def _r7_warnings(u: cc.Unit, extra: dict[str, dict], pending: bool) -> list[str]:
    """R7's checks on one unit (module docstring): flags, never refusals."""
    budget = {k: v["summary_max_output_tokens"] for k, v in extra.items()}
    out = []
    if u.r7 is not None:
        for x in (u.r7, u.r7_rerun):
            if x is not None and budget[x.run_id] != R7_SUMMARY_BUDGET:
                out.append(f"{u.game} {u.config}: R7 replacement chain run {x.run_id} has "
                           f"summary budget {_budget_word(budget[x.run_id])}, not R7's "
                           f"{R7_SUMMARY_BUDGET:,}")
        b = u.before_r7
        if b.d19_ending != SUMMARIZER_FAILURE_ENDING:
            out.append(f"{u.game} {u.config}: R7 replacement {u.r7.run_id} replaces "
                       f"{b.run_id}, which ended {b.d19_ending}, not "
                       f"{SUMMARIZER_FAILURE_ENDING}: R7 is for a run that ended by the "
                       "summarizer failure")
        return out
    e = u.counted
    if (e is not None and not pending and u.config in cc.R7_CONFIGS
            and e.d19_ending == SUMMARIZER_FAILURE_ENDING
            and budget[e.run_id] == OLD_SUMMARY_BUDGET):
        out.append(f"{u.game} {u.config}: counted run {e.run_id} ended "
                   f"{SUMMARIZER_FAILURE_ENDING} under the {OLD_SUMMARY_BUDGET:,} summary "
                   "budget and has no R7 replacement: if it ended by the summarizer failure, "
                   "R7 gives the unit one (meta.json does not say which failure it was)")
    return out


def _counted(u: cc.Unit) -> cc.Entry:
    return u.counted


def _original(u: cc.Unit) -> cc.Entry:
    """The chain's first run (§17.7 change 4 (i)): the seed-1 original, also in a unit with an
    R7 replacement."""
    return u.original


def _before_r7(u: cc.Unit) -> cc.Entry:
    return u.before_r7


def _rhae(e: cc.Entry) -> tuple[float | None, str | None]:
    if e.run is None:
        return None, f"{e.run_id} cannot be scored ({e.skip_reason})"
    return e.rhae, None


def _rhae_k(e: cc.Entry) -> tuple[float | None, str | None]:
    if e.run is None:
        return None, f"{e.run_id} cannot be scored ({e.skip_reason})"
    if not e.run.checks_passed:
        return None, f"{e.run_id} fails analysis.arc_action_matched's checks"
    return e.run.at_k(K)["score"], None


def _cost_capped(e: cc.Entry) -> str | None:
    # the launcher treats either field as a COST_CAP ending (arc/run_path.py)
    hit = COST_CAP in (e.agent_exit_reason, e.exit_reason)
    return f"{e.run_id} ended {COST_CAP}" if hit else None


def _censored(e: cc.Entry) -> str | None:
    return (f"{e.run_id} is censored at K = {K}"
            if e.run.at_k(K)["status"] == am.CENSORED else None)


def select(d: Data, run_of, value_of, leave_out_if=None) -> dict:
    """{game: {config: value}} over the units whose chosen runs all have a value and none of
    which `leave_out_if` names; the other units are left out with the reason, their configs
    together. Also the run each value comes from."""
    values, runs, left_out = {}, {}, []
    for g in d.games:
        chosen = {c: run_of(d.units[(g, c)]) for c in d.configs}
        got = {c: value_of(e) for c, e in chosen.items()}
        why = [f"{c}: {w}" for c, (v, w) in got.items() if v is None]
        if not why and leave_out_if is not None:
            why = [f"{c}: {w}" for c, e in chosen.items() if (w := leave_out_if(e))]
        if why:
            left_out.append({"game": g, "why": "; ".join(why)})
            continue
        values[g] = {c: v for c, (v, _) in got.items()}
        runs[g] = {c: e.run_id for c, e in chosen.items()}
    return {"values": values, "runs": runs, "left_out": left_out}


def _reading(d: Data, sel: dict) -> dict:
    return {**reading(sel["values"], d.configs, d.with_s1, d.seed + BOOT_SEED_OFFSET),
            "runs": sel["runs"], "left_out": sel["left_out"]}


def _at_k_extras(d: Data, sel: dict) -> dict:
    """Censored counted runs per config and the mean levels cleared within K."""
    censored = dict.fromkeys(d.configs, 0)
    levels = {c: [] for c in d.configs}
    for runs in sel["runs"].values():
        for c, run_id in runs.items():
            at = next(e for e in d.entries if e.run_id == run_id).run.at_k(K)
            censored[c] += at["status"] == am.CENSORED
            levels[c].append(at["levels_cleared"])
    mean = {c: sum(v) / len(v) if v else None for c, v in levels.items()}
    return {"censored": censored, "levels_cleared_mean": mean,
            "levels_cleared_S4_minus_S0": None if mean["S0"] is None
            else mean["S4"] - mean["S0"]}


def substitutions(d: Data) -> list[dict]:
    """The units whose chain's first run differs from the counted run (a D19 re-run, an R7
    replacement or its re-run)."""
    out = []
    for (g, c), u in d.units.items():
        if u.original is not None and u.counted is not u.original:
            out.append({"game": g, "config": c, "original": u.original.run_id,
                        "rhae_original": u.original.rhae, "counted": u.counted.run_id,
                        "rhae_counted": u.counted.rhae})
    return out


def r7_substitutions(d: Data) -> list[dict]:
    """The units with an R7 replacement: the run it replaced and the counted run."""
    out = []
    for (g, c), u in d.units.items():
        if u.r7 is not None:
            b, e = u.before_r7, u.counted
            out.append({"game": g, "config": c, "replaced": b.run_id, "rhae_replaced": b.rhae,
                        "summary_budget_replaced":
                            d.extra[b.run_id]["summary_max_output_tokens"],
                        "counted": e.run_id, "rhae_counted": e.rhae,
                        "summary_budget_counted":
                            d.extra[e.run_id]["summary_max_output_tokens"]})
    return out


def full_readings(d: Data) -> tuple[dict, dict, dict]:
    primary = _reading(d, select(d, _counted, _rhae))
    subs = substitutions(d)
    sensitivity = {
        "originals": {**_reading(d, select(d, _original, _rhae)),
                      "note": "the original runs instead of their re-runs (§3 H4, §7.5): each "
                              "chain's first run (§17.7 change 4 (i)), so in a unit with an R7 "
                              "replacement the seed-1 original, with neither D19 nor R7",
                      "substituted": subs},
        "pre_r7": {**_reading(d, select(d, _before_r7, _rhae)),
                   "note": "the counted runs without R7: each R7 replacement (or its re-run) "
                           "swapped for the run it replaced, which ended in the summarizer "
                           "failure under the 8,192 summary budget",
                   "substituted": r7_substitutions(d)},
        "without_cost_cap": {**_reading(d, select(d, _counted, _rhae, _cost_capped)),
                             "note": f"units with a counted run ending {COST_CAP} left out, "
                                     "their configs together (§3 H4, §7.7 D22)"}}

    def at(sel: dict, note: str) -> dict:
        return {**_reading(d, sel), **_at_k_extras(d, sel), "note": note}

    at_k = {"K": K, "K_role": am.k_role(K),
            "note": "PREREG §17.5: secondary and descriptive; the predictions are judged on the "
                    "primary reading only, so their conditions at K are reported, not judged",
            "lower_bounds": at(select(d, _counted, _rhae_k),
                               "censored runs at their final values, lower bounds"),
            "without_censored": at(select(d, _counted, _rhae_k, _censored),
                                   "units that contain a censored counted run left out"),
            "originals": at(select(d, _original, _rhae_k),
                            "the original runs (each chain's first run) instead of their "
                            "re-runs; censored runs at their final values"),
            "pre_r7": at(select(d, _before_r7, _rhae_k),
                         "the counted runs without R7 (the runs the R7 replacements replaced); "
                         "censored runs at their final values"),
            "without_cost_cap": at(select(d, _counted, _rhae_k, _cost_capped),
                                   f"units with a counted run ending {COST_CAP} left out; "
                                   "censored runs at their final values")}
    return primary, sensitivity, at_k


def partial_reading(d: Data) -> dict:
    """What exists while a unit lacks a counted run: RHAE per game and config (a stand-in for
    a pending re-run flagged, and left out of the means), each config's mean over the units
    it has, and G if S0 and S4 are complete. No shares."""
    rows = []
    for g in d.games:
        row = {"game": g}
        for c in d.configs:
            u = d.units[(g, c)]
            e = u.counted
            row[c] = {"run_id": e and e.run_id, "rhae": e and e.rhae, "stand_in": u.pending}
        rows.append(row)
    final = {c: [r[c]["rhae"] for r in rows
                 if r[c]["rhae"] is not None and not r[c]["stand_in"]] for c in d.configs}
    means = {c: {"n_units": len(v), "mean": sum(v) / len(v) if v else None}
             for c, v in final.items()}
    complete = all(means[c]["n_units"] == len(d.games) for c in ("S0", "S4"))
    return {"games": rows, "means": means,
            "G": means["S4"]["mean"] - means["S0"]["mean"] if complete else None,
            "note": "PROVISIONAL: a unit lacks a counted run, so the shares, predictions, "
                    "intervals and sensitivity analyses are withheld"}


def _replaced_flag(e: cc.Entry, unit: cc.Unit | None) -> str:
    """Which sensitivity analysis a replaced run is in (§17.7 change 4): the originals one
    uses each chain's first run, R7's the run an R7 replacement replaced."""
    by = ", ".join(e.replaced_by)
    how = f"its R7 replacement {by}" if e.r7_by else by
    if unit is None or not any(e is x for x in (unit.original, unit.rerun, unit.r7)):
        return f"replaced by {how}"
    uses = []
    if unit.original is e:
        uses.append("originals")
    if unit.r7 is not None and unit.before_r7 is e:
        uses.append("R7")
    if not uses:
        return (f"replaced by {how} (in no reading: the originals sensitivity analysis uses "
                f"the chain's first run, {unit.original.run_id}, and R7's the run the R7 "
                f"replacement replaced, {unit.before_r7.run_id})")
    which = ("the originals and R7 sensitivity analyses" if len(uses) == 2
             else f"the {uses[0]} sensitivity analysis")
    return f"replaced by {how} ({which} only)"


def run_row(e: cc.Entry, d: Data) -> dict:
    r = e.run
    unit = d.units.get((e.game, e.config))
    in_reading = (unit is not None and unit.counted is e and e.config in d.configs
                  and not unit.pending)
    x = d.extra[e.run_id]
    trims = x["context_trims"]
    flags = []
    if e.truncated:
        flags.append("truncated (not a counted run)")
    if e.r7_replaces:
        flags.append(f"R7 replacement of {e.r7_replaces}")
    if e.replaced_by:
        flags.append(_replaced_flag(e, unit))
    if unit is not None and unit.pending and unit.head is e:
        flags.append("re-run-eligible; its re-run has not landed")
    if e.rerun_of and d.eligible.get(e.run_id) and not e.replaced_by:
        flags.append("re-run also ended re-run-eligible: counted as is (D19)")
    if e.config == "S1" and not d.with_s1:
        flags.append("S1 without --with-s1: exploratory, not in this reading")
    if r is not None and not r.checks_passed:
        flags.append("fails analysis.arc_action_matched's checks: no matched values")
    if e.config in TRIM_CONFIGS and trims not in (None, 0):
        flags.append(f"context_trims {trims}, not 0")
    at = r.at_k(K) if r is not None and r.checks_passed else None
    row = {"run_id": e.run_id, "game": e.game, "config": e.config, "replicate": e.replicate,
           "seed": e.seed, "rerun_of": e.rerun_of, "r7_replaces": e.r7_replaces,
           "replaced_by": list(e.replaced_by),
           "counted": not e.replaced_by and not e.truncated, "in_reading": in_reading,
           "started_utc": e.started_utc, "agent_exit_reason": e.agent_exit_reason,
           "exit_reason": e.exit_reason, "d19_ending": e.d19_ending,
           "rerun_eligible": d.eligible.get(e.run_id), "rhae": e.rhae,
           "levels_completed": r and r.levels_completed, "level_count": r and r.level_count,
           "actions": e.actions, "median_s_per_call": e.median_s_per_call,
           "model_returned": x["model_returned"], "config_hash": x["config_hash"],
           "summary_max_output_tokens": x["summary_max_output_tokens"], "context_trims": trims,
           "checks_passed": None if r is None else r.checks_passed,
           "status_at_K": at and at["status"], "rhae_at_K": at and at["score"],
           "levels_cleared_at_K": at and at["levels_cleared"], "flags": flags}
    assert tuple(row) == RUN_FIELDS
    return row


def trims_check(d: Data) -> dict:
    """context_trims of every S1 and S2 run (patch 0016: it should stay 0)."""
    runs = [e for e in d.entries if e.config in TRIM_CONFIGS and not e.truncated]
    value = {e.run_id: d.extra[e.run_id]["context_trims"] for e in runs}
    return {"configs": list(TRIM_CONFIGS), "n_runs": len(runs),
            "zero": [k for k, v in value.items() if v == 0],
            "not_recorded": [k for k, v in value.items() if v is None],
            "nonzero": {k: v for k, v in value.items() if v not in (None, 0)}}


def s4_summaries(d: Data) -> dict | None:
    """Block 2's S4 summaries from those runs' harness compaction records under the results
    root (``raw/arc_path/<run_id>/harness/compaction_*.json``; of each record only
    ``attempts`` and ``usage.completion_tokens``, the output tokens of its attempts, thinking
    included); None if any of those runs has no harness folder there. A record with several
    attempts sums their output, so its largest attempt is not known (`attempts_not_known`)."""
    runs = sorted((e for e in d.entries if e.config == "S4" and e.block2),
                  key=lambda x: x.started)
    if not runs:
        return None
    n = retries = unknown = 0
    peak: int | None = None
    for e in runs:
        folder = d.root / "raw" / cc.EXPERIMENT / e.run_id / "harness"
        if not folder.is_dir():
            return None
        for path in sorted(folder.glob("compaction_*.json")):
            n += 1
            try:
                rec = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                unknown += 1
                continue
            attempts = rec.get("attempts") if isinstance(rec, dict) else None
            usage = rec.get("usage") if isinstance(rec, dict) else None
            out = usage.get("completion_tokens") if isinstance(usage, dict) else None
            if not isinstance(attempts, int) or attempts < 1:
                unknown += 1
                continue
            retries += attempts - 1
            if attempts == 1 and isinstance(out, int):
                peak = out if peak is None else max(peak, out)
            else:
                unknown += 1
    return {"runs": [e.run_id for e in runs], "summaries": n, "retries": retries,
            "max_output_tokens_per_attempt": peak, "attempts_not_known": unknown}


def _count(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


def sigma_replay_note(d: Data) -> dict | None:
    """σ_replay's note under R7 (§17.7 change 4), or None while no counted S2 run played under
    R7's budget: S2→S4 then also lowers the summary budget from 65,536 to S4's 8,192, and the
    note says whether that budget bound in block 2's S4 runs (`s4_summaries`; quoted from
    `RECORDED_S4_SOURCE`, and said to be, when their records are not under the results
    root)."""
    s2 = [u.counted for g in d.games for u in [d.units.get((g, "S2"))]
          if u is not None and u.counted is not None]
    r7 = [e.run_id for e in s2
          if d.extra[e.run_id]["summary_max_output_tokens"] == R7_SUMMARY_BUDGET]
    if not r7:
        return None
    got = s4_summaries(d)
    s = got or {"runs": None, **RECORDED_S4_SUMMARIES, "attempts_not_known": 0}
    peak = s["max_output_tokens_per_attempt"]
    bound = not (s["retries"] == 0 and s["attempts_not_known"] == 0
                 and (peak is None or peak < S4_SUMMARY_BUDGET))
    facts = (f"{_count(s['summaries'], 'summary', 'summaries')}, "
             f"{_count(s['retries'], 'retry', 'retries')}, at most "
             f"{'no' if peak is None else f'{peak:,}'} output tokens per "
             + ("attempt" if not s["attempts_not_known"] else
                "single-attempt summary ("
                + _count(s["attempts_not_known"], "summary", "summaries")
                + " whose largest attempt is not known)"))
    source = ("from those runs' harness compaction records" if got is not None else
              f"as recorded in {RECORDED_S4_SOURCE}; the runs' harness compaction records are "
              "not under this results root, so this is quoted, not recomputed")
    text = (f"S2→S4 also changes the summary budget, from S2's {R7_SUMMARY_BUDGET:,} to S4's "
            f"{S4_SUMMARY_BUDGET:,} output tokens ({len(r7)} of the {len(s2)} counted S2 runs "
            f"played under {R7_SUMMARY_BUDGET:,}). ")
    if bound:
        text += (f"In block 2's S4 runs the {S4_SUMMARY_BUDGET:,} budget may have bound: "
                 f"{facts} ({source}), so the step may also differ by the summary budget.")
    else:
        text += (f"In every S4 run of block 2 the {S4_SUMMARY_BUDGET:,} budget never bound: "
                 f"{facts} ({source}). So for the counted S4 runs the step still differs only "
                 "by native replay and its item format.")
    return {"s2_runs_at_r7_budget": r7, "n_counted_s2": len(s2),
            "s2_summary_budget": R7_SUMMARY_BUDGET, "s4_summary_budget": S4_SUMMARY_BUDGET,
            "s4_runs": s["runs"], "summaries": s["summaries"], "retries": s["retries"],
            "max_output_tokens_per_attempt": peak,
            "attempts_not_known": s["attempts_not_known"], "budget_bound": bound,
            "computed": got is not None,
            "source": "harness compaction records" if got is not None else RECORDED_S4_SOURCE,
            "text": text}


def run_dates(d: Data) -> dict:
    """The first and last start date of each config's counted runs in the reading (the time
    confound, §17.6)."""
    out = {}
    for c in d.configs:
        days = sorted(e.started.date().isoformat() for g in d.games
                      for e in [d.units[(g, c)].counted] if e is not None)
        out[c] = [days[0], days[-1]] if days else None
    return out


# --- compute -------------------------------------------------------------------------------

def _rel(p: Path) -> str:
    p = p.resolve()
    return p.relative_to(REPO_ROOT).as_posix() if p.is_relative_to(REPO_ROOT) else str(p)


def compute(root: Path, generated: str, git: dict, with_s1: bool = False) -> dict:
    """H4's numbers from the files under `root`. Raises cc.Refusal or am.Refused."""
    d = load(root, with_s1)
    status = PROVISIONAL if d.incomplete else FINAL
    primary = sensitivity = at_k = partial = None
    if status == FINAL:
        primary, sensitivity, at_k = full_readings(d)
    else:
        partial = partial_reading(d)
    out = {"generated_utc": generated, **git, "prereg_version": runmeta.prereg_version(),
           "status": status, "provisional_reasons": list(d.incomplete),
           "warnings": list(d.warnings),
           "inputs": {"results_root": _rel(root), "costs_csv": _rel(d.costs_csv),
                      "draw_json": _rel(d.draw_path),
                      "arc_path_folders": [_rel(e.folder) for e in d.entries]},
           "path_games": d.games, "configs": list(d.configs), "with_s1": with_s1,
           "seed": d.seed, "bootstrap_seed": d.seed + BOOT_SEED_OFFSET,
           "units": {f"{g} {c}": {"counted": u.counted and u.counted.run_id,
                                  "original": u.original and u.original.run_id,
                                  "rerun": u.rerun and u.rerun.run_id,
                                  "r7_replacement": u.r7 and u.r7.run_id,
                                  "r7_rerun": u.r7_rerun and u.r7_rerun.run_id,
                                  "pending": u.pending}
                     for (g, c), u in d.units.items()},
           "primary": primary, "sensitivity": sensitivity, "at_k": at_k, "partial": partial,
           "sigma_replay_note": sigma_replay_note(d),
           "run_dates": run_dates(d), "context_trims": trims_check(d),
           "runs": [run_row(e, d) for e in sorted(d.entries, key=lambda x: x.started)],
           "skipped": [{"folder": n, "reason": w} for n, w in d.bare]
           + [{"folder": e.folder.name, "reason": e.skip_reason}
              for e in d.entries if e.skip_reason]}
    assert tuple(out) == TOP_FIELDS
    return out


# --- summary -------------------------------------------------------------------------------

PRE_R7_LABEL = "Counted runs without R7 (replaced runs back)"
SHARE_LABELS = {"sigma_pn": "σ_pn (S0→S2: loss policy and notes removal together)",
                "sigma_loss": "σ_loss (S0→S1: loss policy)",
                "sigma_notes": "σ_notes (S1→S2: notes removal)",
                "sigma_replay": "σ_replay (S2→S4: native replay and its item format)"}


def _n(v, digits: int = 2) -> str:
    return "n/a" if v is None else f"{v:,.{digits}f}"


def _iv(iv, digits: int = 2) -> str:
    return "n/a" if iv is None else f"[{iv[0]:.{digits}f}, {iv[1]:.{digits}f}]"


def _id(run_id) -> str:
    return "none" if run_id is None else f"`{run_id}`"


def _prediction_lines(r: dict, with_s1: bool, judged: bool) -> list[str]:
    p = r["predictions"]
    verb = "" if judged else " (condition at K, reported only)"
    if not with_s1:
        return [f"- **Prediction B** (σ_replay ≥ 1/2){verb}: "
                + ("**holds**." if p["B"]["holds"] else "**does not hold**."),
                f"- **Prediction A**, its replay clause only{verb}: **{p['A']['reading']}**"
                + (" (σ_replay > 1/2)." if p["A"]["reading"] == A_CONTRADICTED else
                   " (σ_replay ≤ 1/2; A's σ_loss and σ_notes conditions need S1).")]
    cond = "; ".join(f"{k}: {'met' if v else 'not met'}"
                     for k, v in p["A"]["conditions"].items())
    return [("- **Prediction A** (σ_loss ≥ 1/3, σ_replay ≤ 1/2, −0.10 ≤ σ_notes ≤ 0.10)"
             f"{verb}: " + ("**holds**" if p["A"]["holds"] else "**does not hold**")
             + f" ({cond})."),
            f"- **Prediction B** (σ_replay ≥ 1/2){verb}: "
            + ("**holds**." if p["B"]["holds"] else "**does not hold**."),
            f"- Which hold: **{p['which']}**."]


def _game_table(r: dict, configs: list[str], with_s1: bool, label: str) -> list[str]:
    steps = list(_step_names(with_s1).values())
    head = (["Game"] + [f"{label} {c}" for c in configs]
            + [f"{b} − {a}" for a, b in steps] + ["S4 − S0"])
    L = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for row in r["per_game"]:
        L.append("| " + " | ".join([row["game"], *(_n(row["rhae"][c]) for c in configs),
                                    *(_n(row[f"{b}_minus_{a}"]) for a, b in steps),
                                    _n(row["S4_minus_S0"])]) + " |")
    m = r["means"]
    L.append("| " + " | ".join(["**Mean (R̄_c)**", *(f"**{_n(m[c])}**" for c in configs),
                                *(_n(m[b] - m[a]) for a, b in steps),
                                f"**{_n(r['G'])}**"]) + " |")
    return L


SIGMA_REPLAY_R7_LABEL = ("σ_replay (S2→S4: native replay and its item format; under R7 also "
                         "the summary budget, see the note on R7)")


def _reading_lines(r: dict, configs: list[str], with_s1: bool, judged: bool,
                   note: dict | None = None, note_given: bool = False) -> list[str]:
    """One reading's table, G, shares and predictions; `note` is σ_replay's note under R7
    (`sigma_replay_note`), which labels σ_replay when given, in full unless `note_given`
    (the summary gave it above)."""
    bs = r["bootstrap"]
    n = r["n_units"]
    L = _game_table(r, configs, with_s1, "RHAE" if judged else f"RHAE_{K}")
    L += ["", (f"G = R̄_S4 − R̄_S0 = **{_n(r['G'])}** RHAE over {n} units (90% interval "
               f"{_iv(bs['G'])}; resamples with G ≤ 0: {bs['fraction_G_le_0']:.2%}). ")
          + ("Shares are reported because G ≥ 10 (D34)." if r["shares_reported"] else
             "**G < 10: the shares are withheld (D34)**" + (
                 "; kill criterion 4 would fire (§10.4)." if judged else "."))]
    if r["shares_reported"]:
        labels = {**SHARE_LABELS, **({"sigma_replay": SIGMA_REPLAY_R7_LABEL} if note else {})}
        L += ["", "| Share | Point estimate | 90% interval |", "|---|---|---|"]
        L += [f"| {labels[k]} | {v:.3f} | {_iv(bs['shares'][k], 3)} |"
              for k, v in r["shares"].items()]
        if note:
            L += ["", "σ_replay under R7: see the note above." if note_given
                  else f"**σ_replay under R7** (§17.7 change 4): {note['text']}"]
        L += [""] + _prediction_lines(r, with_s1, judged)
        L.append("- D30, descriptive: σ_replay ≥ 2/3: "
                 + ("**yes** (dominated by the replay step, the step with no provider-neutral "
                    "analogue)." if r["d30_dominated"] else "**no**."))
        if bs["shares_undefined"]:
            L.append(f"- Resamples with G = 0 have no shares: {bs['shares_undefined']}, left "
                     "out of the shares' intervals.")
    L += ["", (f"Intervals: {bs['resamples']:,} resamples of the {n} units with replacement, a "
               f"unit's configs kept together; percentile {bs['level']:.0%} intervals; RNG seed "
               f"SEED + {BOOT_SEED_OFFSET} = {bs['rng_seed']}. With {n} units there are only "
               f"{bs['distinct_possible']} distinct resamples ({bs['distinct_drawn']} drawn "
               "here), so the intervals are coarse. Descriptive only.")]
    if r["leave_one_out"]:
        L += ["", "Leave one game out:", "", "| Game left out | G over the others | σ_replay |",
              "|---|---|---|"]
        L += [f"| {x['left_out']} | {_n(x['G'])}{' (below 10)' if x['G_below_10'] else ''} | "
              f"{_n(x['sigma_replay'], 3)} |" for x in r["leave_one_out"]]
    return L


def _compact_header(configs: list[str], with_s1: bool) -> list[str]:
    names = list(_step_names(with_s1))
    head = (["Reading", "Units"] + [f"R̄_{c}" for c in configs] + ["G"]
            + [SHARE_LABELS[k].split(" ")[0] for k in names] + ["σ_replay 90%", "B", "A"])
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]


def _compact_row(name: str, r: dict, configs: list[str], with_s1: bool) -> str:
    names = list(_step_names(with_s1))
    if r["n_units"] == 0:
        cells = [name, "0"] + ["n/a"] * (len(configs) + len(names) + 4)
        return "| " + " | ".join(cells) + " |"
    sh, p = r["shares"], r["predictions"]
    if p is None:
        b = a = "withheld (G < 10)"
    elif with_s1:
        b, a = ("holds" if p["B"]["holds"] else "no"), ("holds" if p["A"]["holds"] else "no")
    else:
        b, a = ("holds" if p["B"]["holds"] else "no"), p["A"]["reading"]
    cells = ([name, str(r["n_units"])] + [_n(r["means"][c]) for c in configs] + [_n(r["G"])]
             + [_n(sh[k], 3) if sh else "withheld" for k in names]
             + [_iv(r["bootstrap"]["shares"]["sigma_replay"], 3) if sh else "n/a", b, a])
    return "| " + " | ".join(cells) + " |"


def _left_out_lines(r: dict) -> list[str]:
    if not r["left_out"]:
        return []
    return ["Left out: " + "; ".join(f"{x['game']} ({x['why']})" for x in r["left_out"]) + "."]


def summary_lines(h: dict) -> list[str]:
    configs, with_s1 = h["configs"], h["with_s1"]
    cmd = "uv run python -m analysis.arc_h4" + (" --with-s1" if with_s1 else "")
    L = ["# H4 on the ARC path runs (PREREG §3 H4, as amended by R6, §17.6 change 3)", "",
         (f"Computed {h['generated_utc']} at commit {h['git_commit'][:7]} (dirty: "
          f"{h['git_dirty']}) by `{cmd}`, from `{h['inputs']['results_root']}`. Descriptive "
          "only: 4 units, no significance claims (§3 H4, D34)."), "",
         f"**Status: {h['status']}.**"]
    if h["provisional_reasons"]:
        L += ["", ("A unit lacks a counted run, so the shares, predictions, intervals and "
                   "sensitivity analyses are withheld:")]
        L += [f"- {x}" for x in h["provisional_reasons"]]
    L += ["", (f"**Units:** the {len(h['path_games'])} path games ({', '.join(h['path_games'])}) "
               f"at replicate {REPLICATE}, each config's counted run (§7.5: a re-run replaces its "
               "original; R7: an R7 replacement replaces an S1 or S2 run that ended by the "
               "summarizer failure, and its own re-run replaces it).")]
    if with_s1:
        L.append(f"**Configs:** {', '.join(configs)}, with `--with-s1`: the analyst passes it "
                 "only if `results/decisions.md` records \"S1: yes\", merged to `main` before "
                 "the first block-3 ARC run (§17.6 change 1).")
    else:
        L.append(f"**Configs:** {', '.join(configs)}. S1 is not in this reading: σ_loss and "
                 "σ_notes are not identified, and σ_pn bundles the loss-policy change with the "
                 "notes removal.")
    if h["primary"] is None:
        p = h["partial"]
        L += ["", "## What exists (PROVISIONAL)", "",
              "| Game | " + " | ".join(f"RHAE {c}" for c in configs) + " |",
              "|---|" + "---|" * len(configs)]
        for row in p["games"]:
            L.append(f"| {row['game']} | " + " | ".join(
                _n(row[c]["rhae"]) + (" (stand-in, re-run pending)" if row[c]["stand_in"] else "")
                for c in configs) + " |")
        L.append("| **Mean (units)** | " + " | ".join(
            f"{_n(p['means'][c]['mean'])} ({p['means'][c]['n_units']})" for c in configs) + " |")
        L += ["", (f"G = R̄_S4 − R̄_S0 = {_n(p['G'])} (S0 and S4 complete: "
                   f"{'yes' if p['G'] is not None else 'no'}). No shares while a unit lacks a "
                   "counted run.")]
    else:
        pr = h["primary"]
        note = h["sigma_replay_note"]
        L += ["", "## Primary reading: the scorecard's RHAE", ""]
        L += _reading_lines(pr, configs, with_s1, judged=True, note=note)
        sens = h["sensitivity"]
        L += ["", "## Sensitivity analyses (§3 H4, as frozen)", ""]
        L += _compact_header(configs, with_s1)
        L += [_compact_row("Primary (for reference)", pr, configs, with_s1),
              _compact_row("Original runs instead of re-runs", sens["originals"], configs,
                           with_s1),
              _compact_row(PRE_R7_LABEL, sens["pre_r7"], configs, with_s1),
              _compact_row(f"Units with a {COST_CAP} ending left out",
                           sens["without_cost_cap"], configs, with_s1)]
        if note:
            L += ["", "σ_replay here: in a reading whose S2 runs include one under "
                      f"{R7_SUMMARY_BUDGET:,}, S2→S4 also lowers the summary budget (the note "
                      "on R7 under the primary reading)." if pr["shares_reported"]
                  else f"**σ_replay under R7** (§17.7 change 4): {note['text']}"]
        subs = sens["originals"]["substituted"]
        L += ["", "Original runs used (each chain's first run): " + ("; ".join(
            f"{x['game']} {x['config']}: {_id(x['original'])} (RHAE {_n(x['rhae_original'])}) "
            f"for the counted run {_id(x['counted'])} ({_n(x['rhae_counted'])})" for x in subs)
            if subs else "none (no unit has a re-run or an R7 replacement)") + "."]
        r7 = sens["pre_r7"]["substituted"]
        L += ["", "Runs without R7 used: " + ("; ".join(
            f"{x['game']} {x['config']}: {_id(x['replaced'])} (RHAE {_n(x['rhae_replaced'])}, "
            f"summary budget {_budget_word(x['summary_budget_replaced'])}) for "
            f"{_id(x['counted'])} ({_n(x['rhae_counted'])}, "
            f"{_budget_word(x['summary_budget_counted'])})" for x in r7)
            if r7 else "none (no unit has an R7 replacement), so this reading is the "
                       "primary") + "."]
        L += (_left_out_lines(sens["originals"]) + _left_out_lines(sens["pre_r7"])
              + _left_out_lines(sens["without_cost_cap"]))
        k = h["at_k"]
        lb = k["lower_bounds"]
        L += ["", f"## At K = {k['K']} actions (PREREG §17.5; secondary, descriptive)", "",
              ("The predictions are judged on the primary reading only; their conditions at K "
               "are reported, not judged. Censored runs enter at their final values, which "
               "are lower bounds."), ""]
        if lb["n_units"]:
            L += _reading_lines(lb, configs, with_s1, judged=False, note=note, note_given=True)
        L += ["", ("Censored counted runs (lower bounds): "
                   + ", ".join(f"{c} {lb['censored'][c]}" for c in configs) + ". Mean levels "
                   "cleared within K: " + ", ".join(
                       f"{c} {_n(lb['levels_cleared_mean'][c])}" for c in configs)
                   + f"; S4 − S0: {_n(lb['levels_cleared_S4_minus_S0'])}.")]
        L += _left_out_lines(lb)
        rows = (("Lower bounds", lb), ("Censored units left out", k["without_censored"]),
                ("Original runs instead of re-runs", k["originals"]),
                (PRE_R7_LABEL, k["pre_r7"]),
                (f"Units with a {COST_CAP} ending left out", k["without_cost_cap"]))
        L += [""] + _compact_header(configs, with_s1)
        L += [_compact_row(name, r, configs, with_s1) for name, r in rows]
        L += ["", "Censored counted runs per reading: " + "; ".join(
            f"{name[0].lower()}{name[1:]}: " + ", ".join(f"{c} {r['censored'][c]}" for c in configs)
            for name, r in rows) + "."]
        L += _left_out_lines(k["without_censored"])
    L += ["", "## Runs", "",
          ("| Run | Game | Config | Rep. | Counted | In reading | Ending: agent; exit | D19 | "
           "RHAE | Levels | Actions | Median s per call | Model returned | Config hash "
           "(summary budget) | context_trims | Flags |"),
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in h["runs"]:
        levels = "n/a" if r["levels_completed"] is None else \
            f"{r['levels_completed']} of {r['level_count']}"
        model = ", ".join(r["model_returned"]) if isinstance(r["model_returned"], list) \
            else str(r["model_returned"])
        trims = "n/a" if r["config"] not in TRIM_CONFIGS else (
            "not recorded" if r["context_trims"] is None else str(r["context_trims"]))
        cfg = ("not recorded" if r["config_hash"] is None else f"`{r['config_hash'][:12]}`") + (
            f" ({_budget_word(r['summary_max_output_tokens'])})")
        L.append(f"| `{r['run_id']}` | {r['game']} | {r['config']} | {r['replicate']} | "
                 f"{r['counted']} | {r['in_reading']} | {r['agent_exit_reason']}; "
                 f"{r['exit_reason']} | {r['d19_ending']} | {_n(r['rhae'])} | {levels} | "
                 f"{r['actions']} | {_n(r['median_s_per_call'])} | {model} | {cfg} | {trims} | "
                 f"{'; '.join(r['flags']) or '-'} |")
    t = h["context_trims"]
    L += ["", "## Checks", "",
          ("- context_trims of the S1 and S2 runs (patch 0016: should be 0): "
           + ("no S1 or S2 run yet." if not t["n_runs"] else
              f"0 in {len(t['zero'])} of {t['n_runs']}"
              + (f"; not recorded in {', '.join(t['not_recorded'])}" if t["not_recorded"]
                 else "")
              + (f"; **not 0 in {', '.join(f'{k} ({v})' for k, v in t['nonzero'].items())}**"
                 if t["nonzero"] else "") + "."))]
    L += [f"- {w}" for w in h["warnings"]]
    L += [f"- skipped `{s['folder']}`: {s['reason']}" for s in h["skipped"]]
    L += [""] + not_shown_lines(h)
    return L


def not_shown_lines(h: dict) -> list[str]:
    """"What it does not show", in substance from §17.6, with this reading's numbers."""
    pairs = [r for r in h["runs"] if r["replaced_by"] and r["config"] in h["configs"]]
    by = {r["run_id"]: r for r in h["runs"]}
    # an original and its D19 re-run (same config); an R7 pair plays two configs
    swings = [(r, by[x]) for r in pairs for x in r["replaced_by"]
              if x in by and by[x]["rerun_of"] == r["run_id"]]
    swing = "; ".join(f"{a['game']} {a['config']}: {_n(a['rhae'])} vs {_n(b['rhae'])}, "
                      f"{_n(abs(a['rhae'] - b['rhae']))} RHAE apart" for a, b in swings
                      if a["rhae"] is not None and b["rhae"] is not None)
    dates = h["run_dates"]
    when = "; ".join(f"{c} {v[0]} to {v[1]}" for c, v in dates.items() if v)
    L = ["## What it does not show", "",
         ("- **One seed per game and config.** "
          + (f"An original and its re-run of one unit show how far two runs can differ ({swing}). "
             if swing else "")
          + "Shares from 4 units are descriptive and coarse: 4 units give only 35 distinct "
            "bootstrap resamples."),
         ("- **A time confound.** The configs ran on different days (" + (when or "none yet")
          + "). Gemini 3.8 Flash has no dated snapshot, and its latency drifted (§17.6 change "
            "5). The run table gives the returned model string and the median seconds per "
            "call for every run.")]
    if not h["with_s1"]:
        L.append("- **Without S1,** σ_pn bundles the loss policy with the notes removal, and "
                 "the notes instruction's own role is not measured.")
    L += r7_not_shown_lines(h)
    L += [("- **No StateCarry evidence,** no sol replication of H1, no failure labels and no "
           "open-weights run: each was planned and not run (§17.6 change 1)."),
          "- **H5 on our runs is not blind** (§17.6 change 4); it is not computed here.",
          ("- **The readings at K are secondary.** The slow configs are the ones censored, so "
           "neither the lower bounds nor leaving censored units out is unbiased (§17.5)."),
          ("- **Narrow.** One model at high thinking, two harness configs and the steps between "
           "them, on 4 games chosen for a large published Standard-to-Adapter gap (§7.2). "
           "Nothing here compares models.")]
    return L


def r7_not_shown_lines(h: dict) -> list[str]:
    """R7's lines of "what it does not show" (mixed budgets; D20's pooled yardsticks), when a
    counted S1 or S2 run of the reading's configs played under R7's budget or a unit has an
    R7 replacement."""
    rows = [r for r in h["runs"] if r["counted"] and r["config"] in cc.R7_CONFIGS
            and r["config"] in h["configs"]]
    new = sum(r["summary_max_output_tokens"] == R7_SUMMARY_BUDGET for r in rows)
    old = sum(r["summary_max_output_tokens"] == OLD_SUMMARY_BUDGET for r in rows)
    if not new and not any(r["r7_replaces"] for r in rows):
        return []
    other = len(rows) - new - old
    names = " and ".join(c for c in h["configs"] if c in cc.R7_CONFIGS)
    return [(f"- **R7 changed S1's and S2's summary budget mid-block** ({OLD_SUMMARY_BUDGET:,} "
             f"to {R7_SUMMARY_BUDGET:,} output tokens): of the {len(rows)} counted {names} "
             f"runs, {new} played under {R7_SUMMARY_BUDGET:,} and {old} under "
             f"{OLD_SUMMARY_BUDGET:,}" + (f" ({other} with no budget recorded)" if other else "")
             + ", so a mean over units can mix two versions of a config. The R7 sensitivity "
             "analysis puts back the runs the R7 replacements replaced, and the originals "
             "analysis each chain's first run; the value of a run that ended in the summarizer "
             "failure is a lower bound of what it would have scored had it gone on, not what "
             "the old config scores when its summary succeeds."),
            (f"- **D20's yardsticks pool both versions** (§17.7 change 5): D20 judges each "
             f"{' or '.join(c for c in h['configs'] if c in cc.R7_CONFIGS)} run's seconds per "
             "model call against its config's earlier counted runs, whether they played under "
             f"{OLD_SUMMARY_BUDGET:,} or {R7_SUMMARY_BUDGET:,}, so a run can be judged against "
             "runs of the other version; whether the budget changes the seconds per call is not "
             "measured here.")]


# --- main ----------------------------------------------------------------------------------

def write(out_dir: Path, run_id: str, h: dict, text: str, git: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "h4.json").write_text(json.dumps(h, indent=2, ensure_ascii=False) + "\n",
                                     encoding="utf-8", newline="\n")
    (out_dir / "summary.md").write_text(text, encoding="utf-8", newline="\n")
    config = {"prereg": "PREREG.md §3 H4 as amended by §17.6 change 3 (R6), with §17.5 (R5), "
                        "§7.5 D19/D20, §17.6 change 5 and R7 (S1 and S2's summary budget)",
              "r7_summary_budget": R7_SUMMARY_BUDGET,
              "configs": h["configs"], "with_s1": h["with_s1"], "replicate": REPLICATE,
              "g_min": float(G_MIN), "n_boot": N_BOOT, "level": LEVEL,
              "bootstrap_seed": h["bootstrap_seed"], "K": K, "path_games": h["path_games"],
              "status": h["status"], "inputs": h["inputs"]}
    return runmeta.write_meta(
        out_dir, git=git, experiment="arc_h4", run_id=run_id,
        cell_or_config="h4+S1" if h["with_s1"] else "h4", config=config,
        model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
        repeat_index=None, seeds={"bootstrap": h["bootstrap_seed"]},
        started_utc=h["generated_utc"], finished_utc=runmeta.utc_now(),
        exit_reason="completed" if h["status"] == FINAL else "completed_provisional",
        tokens=None, cost_usd=0.0, raw_transcript_path=None, outputs=list(OUTPUTS),
        paid_calls=0, runs=[r["run_id"] for r in h["runs"] if r["in_reading"]])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--results-root", type=Path, default=RESULTS,
                    help="the results folder to read (default: this checkout's results/)")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="default: <results root>/arc_h4/<UTC>/")
    ap.add_argument("--no-write", action="store_true", help="print only")
    ap.add_argument("--allow-incomplete", action="store_true",
                    help="report what exists (PROVISIONAL, no shares) while a unit lacks a "
                         "counted run")
    ap.add_argument("--with-s1", action="store_true",
                    help="include S1; pass it only if results/decisions.md records "
                         "\"S1: yes\", merged to main before the first block-3 ARC run "
                         "(PREREG §17.6 change 1)")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    now = datetime.now(UTC)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    git = runmeta.git_state()
    root = a.results_root.resolve()
    try:
        h = compute(root, now.isoformat(timespec="seconds"), git, with_s1=a.with_s1)
    except (cc.Refusal, am.Refused) as e:
        print(f"H4 refused: {e}", file=sys.stderr)
        return 2
    if h["status"] != FINAL and not a.allow_incomplete:
        print("H4 refused: a unit lacks a counted run it can score:\n"
              + "\n".join(f"  - {x}" for x in h["provisional_reasons"])
              + "\nWait for the runs, or pass --allow-incomplete to see what exists "
              "(PROVISIONAL, no shares).", file=sys.stderr)
        return 2
    text = "\n".join(summary_lines(h)) + "\n"
    print(text)
    if not a.no_write:
        out = a.out_dir or root / "arc_h4" / run_id
        write(out, run_id, h, text, git)
        print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
