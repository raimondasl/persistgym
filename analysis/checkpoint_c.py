"""Checkpoint C metrics (PREREG §10.3), computed from the ARC path run folders and costs.csv.

Run: ``uv run python -m analysis.checkpoint_c [--results-root DIR] [--no-write]
[--allow-incomplete]`` ($0: it reads files only). It writes
``<results root>/checkpoint_c/<UTC>/checkpoint_c.json``, ``summary.md`` and ``meta.json``,
and prints the summary. Claude proposes; **the researcher makes the go/no-go call**
(PREREG §10.3, CLAUDE.md).

``--d20-run RUN_ID`` instead prints one JSON line for that one ``arc_path`` run and exits 0:
``{"run_id", "config", "game", "agent_exit_reason", "median_s_per_call", "threshold_s",
"incident", "rerun_eligible", "rerun_of", "replaced_by", "rerun_allowed"}`` (exit 2, with the
reason on stderr, if no run folder with a ``meta.json`` holds that run, the run is truncated, or
the folders are inconsistent; any other failure exits non-zero too). The block-3 driver calls it
after every run and starts a re-run right away only on ``"rerun_allowed": true`` (PREREG §17.6
changes 2 and 5); ``null``, a non-zero exit or output it cannot parse stops the block. It reads only ``costs.csv`` (the pilots' ``latency_s``) and
the ``arc_path`` folders, so block 2's completeness, the G0 record and the draw do not matter.
``threshold_s`` is 2 × the as-of-start yardstick below, whatever the ending; ``incident`` is
D20's verdict, ``null`` unless the run ended ``TIME_BUDGET`` (D20 reads only those);
``rerun_eligible`` is D19's verdict on the ending alone, and ``null`` means it cannot be computed
(a ``TIME_BUDGET`` without a median or a yardstick). ``rerun_allowed`` adds D19's "no second
re-run": it is ``rerun_eligible`` for an original that has no re-run yet, ``false`` for a
re-run or an already replaced original, and ``null`` when ``rerun_eligible`` is.

**Inputs**, all under the results root (default ``results/``):

* every folder in ``arc_path/`` (its ``scorecard.json`` and allowlisted ``meta.json`` fields,
  `META_FIELDS`); a folder whose ``meta.json`` is not an ``arc_path`` run is refused, so a
  pilot folder (blinded, PREREG §11) is never read;
* ``costs.csv``: each run's row (billed and list cost, model calls, median seconds per call,
  the block tag ``approved_block=2-arc-seed1;``), the phase-1b spend, and the ARC pilot rows'
  ``latency_s`` only (D20's fallback yardstick and, for S1 and S2, R6's scaled one; latency is
  a field §11 allows);
* the latest ``gates/g0-*/g0.json`` (each run's G0 forecast: published list cost × b(c));
* ``draw/*/draw.json`` (the path games and D32's dropped game, which must be perm[3] of the
  beacon order; otherwise the script refuses).

**Block 2** is the 8 seed-1 runs, S0 and S4 on each path game. Run IDs are not hard-coded:
the runs are found from the folders, and each (game, config) must have exactly one counted
run. **Counted run** (PREREG §7.5): a re-run (``rerun_of`` in its ``meta.json``, seed label
1 + 100 = 101, PREREG §7.4) replaces its original in every reading; both are listed. A re-run
whose original is missing, of another game or config, with another seed label, of a re-run,
or a second re-run of one run, is refused (exit 2), as are two seed-1 originals of one unit.

**Incomplete block.** Without ``--allow-incomplete`` the script refuses (exit 2) while block 2
is incomplete: a unit has no run; its run's ending is re-run-eligible under D19 and its one
re-run has not landed (so no FINAL reading exists before the re-run ends); its counted run has no
scorecard the script can score, no ``costs.csv`` row, no model-call count, or a ``TIME_BUDGET``
whose D20 check cannot be computed. With ``--allow-incomplete`` it marks every output
**PROVISIONAL** and lists why; a run whose re-run is pending stands in for it (flagged), and the
pending re-run counts in ρ. A rule whose inputs are partial (a unit without a run) reads
"undetermined" unless the part present already decides it: a game without a gap could have any
gap in [-100, 100], so the gap rule is decided only if the mean over all games would fall on
the same side of 5 for every such value; a partial cost forecast is a lower bound; the error
count is undetermined while missing or pending runs could take it past 3. A pending re-run
is not yet in ``costs.csv``, so the spend to date leaves it out: a PROVISIONAL sensitivity
reading prices it at its original's billed cost (not the rule).

**Endings and D19/D20** (PREREG §7.5; §0.3 lines 1-3). The ending is ``agent_exit_reason``;
a missing one is ``UNKNOWN``, and a run with no ``scorecard.json`` whose ending is final counts
as ``UNKNOWN`` (§0.3 line 2). Re-run-eligible: ``API_ERROR``, ``AGENT_ERROR``, ``UNKNOWN`` (and
``SCORECARD_CLOSED``, which reaches the agent's field as ``API_ERROR``), and a ``TIME_BUDGET``
that is a D20 latency incident. Final: ``GAME_WIN``, ``ACTION_BUDGET``, ``COST_CAP`` and every
other ``TIME_BUDGET``. **D20 check**, for every run that ended ``TIME_BUDGET``: an incident iff
its median seconds per model call (``meta.json`` ``latency.median_s``) exceeds 2 × the median of
the per-run medians of its config's earlier counted runs, over all games, or 2 × the config's
pilot median if there is no earlier counted run. "Earlier counted runs" is read **as of the
run's start** (the reading applied in ``results/decisions.md`` on 2026-10-08 for CD82 S0):
the same config's ``arc_path`` runs that started before it and had not been replaced by a
re-run started by then (a re-run's own original never counts in its yardstick). The reading
on the final counted set (replaced runs left out) is reported next to it, flagged where the
two disagree.

**R6's yardstick for a config's first counted run** (PREREG §17.6 change 5): for S1 and S2
only (`SCALED_CONFIGS`, whose first counted runs are in block 3), the fallback is the config's
pilot median × S0's drift, where the drift is the median of the per-run medians of S0's
block-2 counted runs (read the same two ways, as of the run's start and on the final counted
set) divided by S0's pilot median. On this checkout's data: 163.37 s / 73.30 s = 2.229, so
S2's yardstick is 215.54 s (threshold 431.09 s) and S1's 232.05 s (464.10 s). S0 and S4 keep
the plain pilot fallback, so block 2's rulings are unchanged; a config's later runs use D20
as frozen.

**Gap rule.** Mean over the path games of RHAE(S4, s = 1) − RHAE(S0, s = 1) on counted runs,
RHAE being the score on the run's scorecard (``analysis.arc_action_matched``). Fires if < 5.
**At K = 150** (PREREG §17.5, change 3; descriptive, fires no rule): the same mean with RHAE_K,
computed in process by ``analysis.arc_action_matched`` (`Run.at_k`, the code that writes its
``runs.csv``; §17.5 says "from runs.csv", and the values are that file's), with the number of
censored counted runs per config and §17.5's sensitivity analysis (the games that contain a
censored counted run left out). A game whose counted S0 or S4 run has
no matched values (unscorable, or failing the score or action check) is left out and listed.

**Error rule.** The number of the 8 counted seed-1 runs whose final ending is re-run-eligible
after their one re-run (a re-run that ends re-run-eligible is counted as is: D19 allows no
second re-run). A re-run that ends ``TIME_BUDGET`` is an error only if it is itself a D20
incident by its own check; **a final ``TIME_BUDGET`` (not an incident) is not an error**, nor is
``COST_CAP``. Fires if > 3. In a PROVISIONAL reading a stand-in for a pending re-run is not
counted as an error but listed (``pending``; ``errors_upper`` adds them).

**Cost rule (D27, PREREG §10.1 and §10.3).** ρ = (block-2 re-runs) / 8. Forecast for the
remaining 24 runs = [Σ over games of the counted seed-1 runs' billed cost of S0 and of S4]
(seed 2) + [Σ over games of 2 × 2 × (S0 billed cost per model call) × max(S0 actions, S4
actions)] (S1 and S2, both seeds), all × (1 + ρ). Billed cost: the run's ``costs.csv`` billed
estimate; model calls: ``meta.json`` ``n_calls``; actions: the scorecard's. Remaining = the
phase-1b cap (``common.costs.PHASE_CAPS``; a warning if it is not §10.3's $900) − the phase-1b
spend to date in ``costs.csv`` (every ``arc_path`` row, re-runs included;
``common.costs.spend_by_phase``). Fires if forecast > remaining. Also reported: the headroom
with D27's allowed raise of about $170, the cap the forecast needs (spend to date +
forecast), and, **descriptive and not the pre-registered rule**,
a measured-cost reading that prices each S1 and S2 run at S0's measured billed cost per run.

**3-game fallback (D32, PREREG §7.3, §10.6).** The game dropped is perm[3] of the beacon draw
(``draw.json``: CD82). The same three rules are computed on the 3 remaining games: the gap over
3 games, errors over 6 runs, and the cost of 18 remaining runs with ρ over those 6 runs (D32:
"Checkpoint C then uses the 3 remaining path games"); ρ over all 8 block-2 runs is shown too.
The thresholds are unchanged.

**Per run**: both endings, RHAE, actions, billed cost against its G0 forecast, seconds per
action, model calls, median seconds per call, and the D20 check where one applies, so that
every D20 decision is documented.

**What is written** is built from allowlists (`RUN_FIELDS`, `TOP_FIELDS`, `OUTPUTS`): no
transcript path, key, note text, token count or other ``meta.json`` field is copied.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from analysis import arc_action_matched as am
from common import approval, costs, runmeta

REPO_ROOT = runmeta.REPO_ROOT
RESULTS = REPO_ROOT / "results"
EXPERIMENT = "arc_path"
BLOCK = "2-arc-seed1"
BLOCK_CONFIGS = ("S0", "S4")
REPLICATE = 1
RERUN_SEED_OFFSET = 100            # PREREG §7.4: a re-run of replicate s gets seed s + 100
PHASE = "1b"
GAP_MIN = 5.0                      # §10.3: fires if the mean gap is < 5
MAX_ERRORS = 3                     # §10.3: fires if more than 3 runs end in an error
D27_RAISE_USD = 170.0              # §10.1 D27: "up to about $170"
D20_FACTOR = 2.0                   # §7.5 D20
SCALED_CONFIGS = ("S1", "S2")      # §17.6 change 5: first counted run in block 3
DRIFT_CONFIG = "S0"                # §17.6 change 5: the drift block 2 measured on S0
CAP_1B_FROZEN = 900.0              # §10.3: "Remaining is $900 minus ..."
RHAE_MAX = 100.0                   # ARC's game score is in [0, 100] (arc_action_matched)
K = am.REGISTERED_K                # §17.5
ERROR_ENDINGS = ("API_ERROR", "AGENT_ERROR", "UNKNOWN", "SCORECARD_CLOSED")
FINAL_ENDINGS = ("GAME_WIN", "ACTION_BUDGET", "COST_CAP")
TIME_BUDGET = "TIME_BUDGET"
NO_SCORECARD = "no scorecard.json"

META_FIELDS = (*am.META_FIELDS, "started_utc", "n_calls", "latency")
"""The only meta.json fields read (`latency`: only its `median_s`)."""

RUN_FIELDS = ("run_id", "game", "config", "replicate", "seed", "rerun_of", "replaced_by",
              "counted", "rerun_pending", "block2", "started_utc", "agent_exit_reason",
              "exit_reason", "d19_ending", "rerun_eligible", "scorecard", "rhae",
              "levels_completed", "level_count", "actions", "wall_clock_s",
              "seconds_per_action", "n_calls", "median_s_per_call", "billed_usd", "list_usd", "g0_forecast_usd",
              "billed_over_forecast", "costs_row", "costs_row_block_tag", "d20")
TOP_FIELDS = ("generated_utc", "git_commit", "git_dirty", "prereg_version", "status",
              "provisional_reasons", "warnings", "inputs", "path_games", "fallback_drop_game",
              "phase_1b", "readings", "runs", "skipped")
OUTPUTS = ("checkpoint_c.json", "summary.md")
FINAL, PROVISIONAL = "FINAL", "PROVISIONAL"


class Refusal(ValueError):
    """Inputs Checkpoint C cannot be computed from (exit 2)."""


# --- runs ----------------------------------------------------------------------------------

@dataclass
class Entry:
    """One arc_path run folder: its allowlisted meta.json fields, its scored run (or why it
    has none) and its costs.csv row."""
    folder: Path
    run_id: str
    game: str
    config: str
    seed: int | None
    rerun_of: str | None
    agent_exit_reason: str | None
    exit_reason: str | None
    started_utc: str | None
    started: datetime
    truncated: bool
    n_calls: int | None
    median_s_per_call: float | None
    meta_billed: float | None
    meta_list: float | None
    run: am.Run | None
    skip_reason: str | None
    replaced_by: list[str] = field(default_factory=list)
    billed: float | None = None
    listed: float | None = None
    costs_row: str = "missing"
    costs_tagged: bool = False
    costs_n_calls: int | None = None

    @property
    def replicate(self) -> int | None:
        if self.seed is None:
            return None
        return self.seed - RERUN_SEED_OFFSET if self.rerun_of else self.seed

    @property
    def block2(self) -> bool:
        return (not self.truncated and self.replicate == REPLICATE
                and self.config in BLOCK_CONFIGS)

    @property
    def d19_ending(self) -> str:
        """The ending D19 reads: `agent_exit_reason`, UNKNOWN if missing, and UNKNOWN for a
        final ending whose scorecard cannot be read (§0.3 lines 1-2)."""
        ending = self.agent_exit_reason or "UNKNOWN"
        if self.skip_reason == NO_SCORECARD and ending in (*FINAL_ENDINGS, TIME_BUDGET):
            return "UNKNOWN"
        return ending

    @property
    def rhae(self) -> float | None:
        return None if self.run is None else self.run.score_scorecard

    @property
    def actions(self) -> int | None:
        return None if self.run is None else self.run.actions


def _number(v) -> float | None:
    return None if v in (None, "") else float(v)


def _int(v) -> int | None:
    return None if v in (None, "") else int(v)


def _started(run_id: str, started_utc: str | None) -> datetime:
    if started_utc:
        t = datetime.fromisoformat(started_utc)
        return t if t.tzinfo else t.replace(tzinfo=UTC)
    try:
        return datetime.strptime(run_id[:16], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        raise Refusal(f"run {run_id}: no started_utc in its meta.json and no time in its "
                      "run ID, so its place in the run order is unknown (D20)") from None


def load_entry(folder: Path) -> Entry:
    """The run in `folder`. Raises `am.Refused` unless its meta.json is an arc_path run."""
    folder = Path(folder)
    got = am.load_run(folder)                  # refuses pilots and other experiments
    raw = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    meta = {k: raw.get(k) for k in META_FIELDS}
    seeds, latency, cost = (meta["seeds"] or {}), (meta["latency"] or {}), (meta["cost_usd"]
                                                                             or {})
    run_id = str(meta["run_id"])
    return Entry(folder=folder, run_id=run_id, game=str(meta["game_requested"]).upper(),
                 config=str(meta["cell_or_config"]), seed=_int(seeds.get("replicate_seed")),
                 rerun_of=meta["rerun_of"], agent_exit_reason=meta["agent_exit_reason"],
                 exit_reason=meta["exit_reason"], started_utc=meta["started_utc"],
                 started=_started(run_id, meta["started_utc"]),
                 truncated=any(v is not None
                               for v in (meta["truncation_limits"] or {}).values()),
                 n_calls=_int(meta["n_calls"]),
                 median_s_per_call=_number(latency.get("median_s")),
                 meta_billed=_number(cost.get("billed_est")),
                 meta_list=_number(cost.get("list")),
                 run=got if isinstance(got, am.Run) else None,
                 skip_reason=got if isinstance(got, str) else None)


def discover(arc_path: Path) -> tuple[list[Entry], list[tuple[str, str]]]:
    """Every run folder in `arc_path`, linked to its re-run, and the folders without a
    meta.json (not a finished run). Refuses two folders with one run ID."""
    if not arc_path.is_dir():
        return [], []
    entries, bare = [], []
    for d in sorted(p for p in arc_path.iterdir() if p.is_dir()):
        if not (d / "meta.json").is_file():
            bare.append((d.name, "no meta.json (not a finished run)"))
            continue
        entries.append(load_entry(d))
    by_id: dict[str, Entry] = {}
    for e in entries:
        if e.run_id in by_id:
            raise Refusal(f"two folders hold run {e.run_id}")
        by_id[e.run_id] = e
    for e in entries:
        if e.rerun_of in by_id:
            by_id[e.rerun_of].replaced_by.append(e.run_id)
    return entries, bare


def check_links(entries: list[Entry]) -> None:
    """A re-run must name an original of the same game and config, with seed label original +
    100; there is no re-run of a re-run and no second re-run (PREREG §7.4, §7.5)."""
    by_id = {e.run_id: e for e in entries}
    for e in entries:
        if not e.rerun_of:
            continue
        orig = by_id.get(e.rerun_of)
        if orig is None:
            raise Refusal(f"re-run {e.run_id} names {e.rerun_of}, which is not among the "
                          "arc_path folders")
        if orig.rerun_of:
            raise Refusal(f"re-run {e.run_id} re-runs {orig.run_id}, itself a re-run: D19 "
                          "allows no second re-run")
        if (e.game, e.config) != (orig.game, orig.config):
            raise Refusal(f"re-run {e.run_id} ({e.game} {e.config}) does not match its "
                          f"original {orig.run_id} ({orig.game} {orig.config})")
        if orig.seed is None or e.seed != orig.seed + RERUN_SEED_OFFSET:
            raise Refusal(f"re-run {e.run_id} has seed label {e.seed}; its original "
                          f"{orig.run_id} has {orig.seed}, so it should be "
                          f"{None if orig.seed is None else orig.seed + RERUN_SEED_OFFSET}")
        if len(orig.replaced_by) > 1:
            raise Refusal(f"{orig.run_id} has {len(orig.replaced_by)} re-runs "
                          f"({', '.join(orig.replaced_by)}): D19 allows one")


def attach_costs(entries: list[Entry], rows: list[dict]) -> None:
    """Each run's costs.csv row: billed and list cost, model calls, and whether it matches
    meta.json and carries block 2's tag."""
    by_id: dict[str, dict] = {}
    for r in rows:
        if r["experiment"] != EXPERIMENT:
            continue
        if r["run_id"] in by_id:
            raise Refusal(f"two costs.csv rows for run {r['run_id']}")
        by_id[r["run_id"]] = r
    tag = approval.spend_tag(BLOCK)
    for e in entries:
        row = by_id.get(e.run_id)
        if row is None:
            continue
        e.billed, e.listed = _number(row["cost_usd_billed_est"]), _number(row["cost_usd_list"])
        e.costs_n_calls = _int(row["n_calls"])
        e.costs_tagged = tag in (row.get("notes") or "")
        same = all(a is not None and b is not None
                   and abs(a - b) <= am.COST_TOLERANCE_USD
                   for a, b in ((e.billed, e.meta_billed), (e.listed, e.meta_list)))
        e.costs_row = "match" if same else "mismatch"


def pilot_latency(rows: list[dict]) -> dict[str, dict]:
    """D20's fallback yardstick: each config's ARC pilot median seconds per call
    (`latency_s` only; PREREG §11 allows latency)."""
    out: dict[str, dict] = {}
    for r in rows:
        if r["experiment"] != "arc_pilot":
            continue
        c = r["cell_or_config"]
        if c in out:
            raise Refusal(f"more than one arc_pilot row for {c} in costs.csv")
        out[c] = {"run_id": r["run_id"], "latency_s": _number(r["latency_s"])}
    return out


# --- D20 and D19 ---------------------------------------------------------------------------

def _drift(group: list[Entry], pilots: dict[str, dict]) -> dict | None:
    """S0's drift (§17.6 change 5): the median of its block-2 counted runs' per-run medians
    over its pilot median; None without either."""
    p = pilots.get(DRIFT_CONFIG) or {}
    if not group or not p.get("latency_s"):
        return None
    m = statistics.median(x.median_s_per_call for x in group)
    return {"s0_runs": [x.run_id for x in group], "s0_median_s": m,
            "s0_pilot": p["run_id"], "s0_pilot_s": p["latency_s"],
            "factor": m / p["latency_s"]}


def _yardstick(e: Entry, group: list[Entry], pilots: dict[str, dict],
               drift: dict | None = None) -> dict:
    """D20's yardstick from the config's earlier counted runs `group`; without any, the
    config's pilot median, scaled by S0's `drift` for S1 and S2 (§17.6 change 5)."""
    used = None
    if group:
        y = statistics.median(x.median_s_per_call for x in group)
        source: str | list[str] = [x.run_id for x in group]
    else:
        p = pilots.get(e.config) or {}
        if p.get("latency_s") is None:
            return {"yardstick_s": None, "yardstick_from": "no earlier counted run and no "
                    "pilot latency", "threshold_s": None, "ratio": None, "incident": None,
                    "drift": None}
        if e.config in SCALED_CONFIGS:
            if drift is None:
                return {"yardstick_s": None, "yardstick_from": "no earlier counted run, and no "
                        f"{DRIFT_CONFIG} drift to scale the pilot median by (§17.6 change 5)",
                        "threshold_s": None, "ratio": None, "incident": None, "drift": None}
            used = drift
            y = p["latency_s"] * drift["factor"]
            source = (f"pilot {p['run_id']} × {DRIFT_CONFIG} drift {drift['factor']:.4f} "
                      "(§17.6 change 5)")
        else:
            y, source = p["latency_s"], f"pilot {p['run_id']}"
    m = e.median_s_per_call
    return {"yardstick_s": y, "yardstick_from": source, "threshold_s": D20_FACTOR * y,
            "ratio": None if m is None or y <= 0 else m / y,
            "incident": None if m is None else m > D20_FACTOR * y, "drift": used}


def d20_readings(e: Entry, entries: list[Entry], pilots: dict[str, dict]) -> dict:
    """D20's two readings for run `e`, whatever its ending (module docstring): the
    as-of-start reading decides; the final-counted-set reading is reported next to it."""
    starts = {x.run_id: x.started for x in entries}

    def earlier(config: str, pool: list[Entry]) -> tuple[list[Entry], list[Entry]]:
        same = [x for x in pool
                if x is not e and not x.truncated and x.config == config
                and x.started < e.started and x.median_s_per_call is not None]
        return ([x for x in same if not any(starts[r] <= e.started for r in x.replaced_by)],
                [x for x in same if not x.replaced_by])

    as_of, final = earlier(e.config, entries)
    drift_a = drift_f = None
    if e.config in SCALED_CONFIGS:
        s0_a, s0_f = earlier(DRIFT_CONFIG, [x for x in entries if x.block2])
        drift_a, drift_f = _drift(s0_a, pilots), _drift(s0_f, pilots)
    a = _yardstick(e, as_of, pilots, drift_a)
    f = _yardstick(e, final, pilots, drift_f)
    return {"median_s_per_call": e.median_s_per_call, "as_of_start": a, "final_counted_set": f,
            "incident": a["incident"], "readings_agree": a["incident"] == f["incident"]}


def d20_check(e: Entry, entries: list[Entry], pilots: dict[str, dict]) -> dict | None:
    """D20 for a run that ended TIME_BUDGET; None for any other ending."""
    if e.agent_exit_reason != TIME_BUDGET:
        return None
    return d20_readings(e, entries, pilots)


def rerun_eligible(e: Entry, d20: dict | None) -> bool | None:
    """D19 on the run's ending; None if a TIME_BUDGET's D20 check cannot be computed."""
    ending = e.d19_ending
    if ending in ERROR_ENDINGS:
        return True
    if ending == TIME_BUDGET:
        return None if d20 is None else d20["incident"]
    if ending in FINAL_ENDINGS:
        return False
    raise Refusal(f"run {e.run_id}: agent_exit_reason {ending!r} is not an ending D19 "
                  "classifies (PREREG §7.4, §7.5)")


def why_ending(e: Entry, d20: dict | None, eligible: bool | None) -> str:
    ending = e.d19_ending
    if ending != (e.agent_exit_reason or "UNKNOWN"):
        return f"{e.agent_exit_reason} with no readable scorecard: UNKNOWN, re-run-eligible"
    if ending in ERROR_ENDINGS:
        return f"{ending}: re-run-eligible (D19)"
    if ending == TIME_BUDGET:
        if eligible is None:
            return "TIME_BUDGET: D20 check cannot be computed"
        a = d20["as_of_start"]
        verdict = ("a latency incident: re-run-eligible" if eligible
                   else "not a latency incident: final, not an error")
        return (f"TIME_BUDGET, {d20['median_s_per_call']:.2f} s per call against "
                f"2 × {a['yardstick_s']:.2f} s: {verdict} (D20)")
    return f"{ending}: final (D19)"


# --- block 2 -------------------------------------------------------------------------------

@dataclass
class Unit:
    game: str
    config: str
    original: Entry | None = None
    rerun: Entry | None = None
    pending: bool = False          # the original is re-run-eligible and its re-run is missing

    @property
    def counted(self) -> Entry | None:
        return self.rerun or self.original


@dataclass
class Block:
    games: list[str]
    drop: str
    entries: list[Entry]
    units: dict[tuple[str, str], Unit]
    d20: dict[str, dict | None]
    eligible: dict[str, bool | None]
    incomplete: list[str]
    warnings: list[str]
    bare: list[tuple[str, str]]

    def unit(self, game: str, config: str) -> Unit:
        return self.units[(game, config)]


def resolve_unit(entries: list[Entry], game: str, config: str,
                 eligible: dict[str, bool | None], replicate: int = REPLICATE) -> Unit:
    """The (game, config) unit at `replicate` (PREREG §7.5): its original, its re-run, which
    replaces it, and whether a re-run is pending (the original is re-run-eligible and its
    re-run has not landed). Refuses two originals. Call `check_links` first."""
    mine = [e for e in entries if not e.truncated and e.replicate == replicate
            and (e.game, e.config) == (game, config)]
    originals = [e for e in mine if not e.rerun_of]
    reruns = [e for e in mine if e.rerun_of]
    if len(originals) > 1:
        raise Refusal(f"{game} {config}: {len(originals)} seed-{replicate} runs that are not "
                      f"re-runs ({', '.join(e.run_id for e in originals)}); exactly one may "
                      "be counted")
    u = Unit(game, config, originals[0] if originals else None, reruns[0] if reruns else None)
    u.pending = bool(u.original is not None and u.rerun is None
                     and eligible[u.original.run_id])
    return u


def build_block(entries: list[Entry], bare: list[tuple[str, str]], games: list[str],
                drop: str, pilots: dict[str, dict]) -> Block:
    check_links(entries)
    d20 = {e.run_id: d20_check(e, entries, pilots) for e in entries if not e.truncated}
    eligible = {e.run_id: rerun_eligible(e, d20[e.run_id]) for e in entries if not e.truncated}
    incomplete: list[str] = []
    warnings: list[str] = [f"{name}: {why}" for name, why in bare]
    units: dict[tuple[str, str], Unit] = {}
    for g in games:
        for c in BLOCK_CONFIGS:
            u = resolve_unit(entries, g, c, eligible)
            units[(g, c)] = u
            if u.original is None:
                incomplete.append(f"{g} {c}: no seed-{REPLICATE} run yet")
                continue
            elig = eligible[u.original.run_id]
            if u.pending:
                incomplete.append(f"{g} {c}: {u.original.run_id} ended "
                                  f"{why_ending(u.original, d20[u.original.run_id], elig)}; "
                                  "its one re-run has not landed (it stands in, flagged)")
            if u.rerun is not None and elig is False:
                warnings.append(f"{g} {c}: {u.original.run_id} was re-run although its ending "
                                f"({why_ending(u.original, d20[u.original.run_id], elig)}) "
                                "is final under D19/D20 as computed here; the re-run still "
                                "replaces it (§7.5)")
            e = u.counted
            if eligible[e.run_id] is None:
                incomplete.append(f"{g} {c}: {e.run_id} ended TIME_BUDGET and its D20 check "
                                  "cannot be computed (no median seconds per call or "
                                  "yardstick)")
            if e.run is None:
                incomplete.append(f"{g} {c}: counted run {e.run_id} has no score here "
                                  f"({e.skip_reason})")
            if e.costs_row == "missing":
                incomplete.append(f"{g} {c}: counted run {e.run_id} has no costs.csv row")
            if e.n_calls is None:
                incomplete.append(f"{g} {c}: counted run {e.run_id} has no n_calls in its "
                                  "meta.json")
            for x in (u.original, u.rerun):
                if x is None:
                    continue
                if x.costs_row == "mismatch":
                    warnings.append(f"{x.run_id}: costs.csv row differs from meta.json")
                if x.costs_row != "missing" and not x.costs_tagged:
                    warnings.append(f"{x.run_id}: costs.csv row is not tagged "
                                    f"{approval.spend_tag(BLOCK)}")
                if x.costs_n_calls is not None and x.costs_n_calls != x.n_calls:
                    warnings.append(f"{x.run_id}: n_calls {x.n_calls} in meta.json, "
                                    f"{x.costs_n_calls} in costs.csv")
                if x.run is not None and not x.run.checks_passed:
                    warnings.append(f"{x.run_id}: fails analysis.arc_action_matched's checks "
                                    "(no matched values, §17.5)")
    for e in entries:
        if not e.truncated and e.median_s_per_call is None:
            warnings.append(f"{e.run_id}: no median seconds per call in meta.json; left out "
                            "of D20 yardsticks")
        dd = d20.get(e.run_id)
        if dd and not dd["readings_agree"]:
            warnings.append(f"{e.run_id}: D20 readings disagree (as of its start: incident "
                            f"{dd['as_of_start']['incident']}; on the final counted set: "
                            f"{dd['final_counted_set']['incident']}); the as-of reading is "
                            "used")
    return Block(games=list(games), drop=drop, entries=entries, units=units, d20=d20,
                 eligible=eligible, incomplete=incomplete, warnings=warnings, bare=bare)


# --- readings ------------------------------------------------------------------------------

def gap_reading(b: Block, games: list[str]) -> dict:
    rows = []
    for g in games:
        s0, s4 = b.unit(g, "S0"), b.unit(g, "S4")
        r0 = None if s0.counted is None else s0.counted.rhae
        r4 = None if s4.counted is None else s4.counted.rhae
        rows.append({"game": g, "S0_run": s0.counted and s0.counted.run_id,
                     "S4_run": s4.counted and s4.counted.run_id, "rhae_S0": r0, "rhae_S4": r4,
                     "gap": None if r0 is None or r4 is None else r4 - r0,
                     "stand_in": s0.pending or s4.pending})
    gaps = [r["gap"] for r in rows if r["gap"] is not None]
    mean = sum(gaps) / len(gaps) if gaps else None
    # A game without a gap could still have any gap in [-RHAE_MAX, RHAE_MAX] (ARC's game score
    # is in [0, 100]), so a partial mean decides the rule only if every such value would.
    n_missing = len(games) - len(gaps)
    low = (sum(gaps) - RHAE_MAX * n_missing) / len(games)
    high = (sum(gaps) + RHAE_MAX * n_missing) / len(games)
    fires = True if high < GAP_MIN else False if low >= GAP_MIN else None
    return {"rule": "mean over the path games of RHAE(S4, s=1) - RHAE(S0, s=1), counted runs; "
                    f"fires if < {GAP_MIN:g}", "threshold": GAP_MIN, "games": rows,
            "n_games": len(gaps), "complete": n_missing == 0, "mean_gap": mean,
            "mean_gap_bounds": None if n_missing == 0 else [low, high], "fires": fires}


def gap_at_k_reading(b: Block, games: list[str], k: int = K) -> dict:
    rows, left_out = [], []
    censored = dict.fromkeys(BLOCK_CONFIGS, 0)
    for g in games:
        runs = {c: b.unit(g, c).counted for c in BLOCK_CONFIGS}
        missing = [f"{c}: " + ("no run" if e is None else
                               f"{e.run_id} {e.skip_reason}" if e.run is None else
                               f"{e.run_id} fails the checks")
                   for c, e in runs.items()
                   if e is None or e.run is None or not e.run.checks_passed]
        if missing:
            left_out.append({"game": g, "why": "; ".join(missing)})
            continue
        at = {c: runs[c].run.at_k(k) for c in BLOCK_CONFIGS}
        for c in BLOCK_CONFIGS:
            censored[c] += at[c]["status"] == am.CENSORED
        rows.append({"game": g, **{f"{f}_{c}": at[c][f] for c in BLOCK_CONFIGS
                                   for f in ("score", "status", "levels_cleared")},
                     "gap": at["S4"]["score"] - at["S0"]["score"],
                     "stand_in": any(b.unit(g, c).pending for c in BLOCK_CONFIGS)})
    gaps = [r["gap"] for r in rows]
    # §17.5's censoring sensitivity analysis: every game whose counted S0 or S4 run is
    # censored at K left out, its two configs together
    whole = [r["gap"] for r in rows
             if am.CENSORED not in (r["status_S0"], r["status_S4"])]
    return {"rule": f"PREREG §17.5 change 3: the same mean with RHAE_K at K = {k}; "
                    "descriptive, fires no rule", "K": k, "K_role": am.k_role(k),
            "games": rows, "left_out": left_out, "n_games": len(rows),
            "mean_gap": sum(gaps) / len(gaps) if gaps else None, "censored": censored,
            "without_censored": {"n_games": len(whole),
                                 "mean_gap": sum(whole) / len(whole) if whole else None}}


def error_reading(b: Block, games: list[str]) -> dict:
    rows = []
    for g in games:
        for c in BLOCK_CONFIGS:
            u = b.unit(g, c)
            e = u.counted
            if e is None:
                rows.append({"game": g, "config": c, "run_id": None, "rerun": False,
                             "ending": None, "rerun_eligible": None, "pending": False,
                             "why": "no run yet"})
                continue
            elig = b.eligible[e.run_id]
            rows.append({"game": g, "config": c, "run_id": e.run_id,
                         "rerun": u.rerun is not None, "ending": e.d19_ending,
                         "rerun_eligible": elig, "pending": u.pending,
                         "why": why_ending(e, b.d20[e.run_id], elig)
                         + ("; its re-run is pending, so this is not final" if u.pending
                            else "")})
    errors = sum(1 for r in rows if r["rerun_eligible"] is True and not r["pending"])
    pending = sum(1 for r in rows if r["pending"])
    undetermined = sum(1 for r in rows if r["rerun_eligible"] is None)   # no run, or no D20
    return {"rule": f"counted seed-1 runs whose final ending is re-run-eligible under D19 "
                    f"after their one re-run; fires if > {MAX_ERRORS}",
            "time_budget": "a TIME_BUDGET is an error only if the counted run is itself a D20 "
                           "latency incident; a final TIME_BUDGET (not an incident) is not an "
                           "error, nor is COST_CAP",
            "threshold": MAX_ERRORS, "n_runs": len(rows), "runs": rows, "errors": errors,
            "pending": pending, "errors_upper": errors + pending,
            "undetermined": undetermined,
            "fires": (True if errors > MAX_ERRORS
                      else None if errors + pending + undetermined > MAX_ERRORS else False)}


def _fires_at(forecast: float, room: float, complete: bool) -> bool | None:
    """Whether a forecast exceeds the room. A partial forecast (a game lacks inputs) is a
    lower bound: it fires if it already exceeds the room, and is undetermined otherwise."""
    if forecast > room:
        return True
    return False if complete else None


def cost_reading(b: Block, games: list[str], spent: float, cap: float) -> dict:
    rows = []
    for g in games:
        s0, s4 = b.unit(g, "S0").counted, b.unit(g, "S4").counted
        row = {"game": g, "S0_run": s0 and s0.run_id, "S4_run": s4 and s4.run_id,
               "billed_S0": s0 and s0.billed, "billed_S4": s4 and s4.billed,
               "n_calls_S0": s0 and s0.n_calls, "actions_S0": s0 and s0.actions,
               "actions_S4": s4 and s4.actions, "S0_usd_per_call": None, "max_actions": None,
               "seed2": None, "s1_s2": None, "s1_s2_measured": None}
        if s0 and s0.billed is not None and s0.n_calls:
            row["S0_usd_per_call"] = s0.billed / s0.n_calls
            row["s1_s2_measured"] = 2 * 2 * s0.billed
        if s0 and s4 and s0.billed is not None and s4.billed is not None:
            row["seed2"] = s0.billed + s4.billed
        if row["S0_usd_per_call"] is not None and None not in (row["actions_S0"],
                                                                 row["actions_S4"]):
            row["max_actions"] = max(row["actions_S0"], row["actions_S4"])
            row["s1_s2"] = 2 * 2 * row["S0_usd_per_call"] * row["max_actions"]
        rows.append(row)
    n_block = len(BLOCK_CONFIGS) * len(games)
    reruns = sum(b.unit(g, c).rerun is not None for g in games for c in BLOCK_CONFIGS)
    pending = sum(b.unit(g, c).pending for g in games for c in BLOCK_CONFIGS)
    rho = (reruns + pending) / n_block
    complete = all(r[k] is not None for r in rows for k in ("seed2", "s1_s2"))
    seed2 = sum(r["seed2"] or 0.0 for r in rows)
    s12 = sum(r["s1_s2"] or 0.0 for r in rows)
    s12_measured = sum(r["s1_s2_measured"] or 0.0 for r in rows)
    forecast = (seed2 + s12) * (1 + rho)
    remaining = cap - spent
    # A pending re-run (on any path game: phase-1b spend is not split by game) has not been
    # paid yet, so the spend to date leaves it out. Priced at its original's billed cost, as a
    # PROVISIONAL sensitivity reading only; the rule reads the spend in costs.csv.
    stand_ins = [u.original for u in b.units.values() if u.pending]
    pending_spend = sum(e.billed or 0.0 for e in stand_ins)
    after = remaining - pending_spend
    return {"rule": "D27 at Checkpoint C: ([seed 2: S0 + S4 billed per game] + [S1, S2 in both "
                    "seeds: 2 x 2 x S0 billed per call x max(S0, S4 actions) per game]) x "
                    "(1 + rho); fires if > remaining",
            "games": rows, "complete": complete, "n_block2_runs": n_block,
            "n_remaining_runs": 3 * n_block, "reruns": reruns, "pending_reruns": pending,
            "rho": rho, "seed2_usd": seed2, "s1_s2_usd": s12, "forecast_usd": forecast,
            "spent_1b_usd": spent, "cap_1b_usd": cap, "remaining_usd": remaining,
            "headroom_usd": remaining - forecast, "fires": _fires_at(forecast, remaining,
                                                                   complete),
            "raise_allowed_usd": D27_RAISE_USD,
            "headroom_with_raise_usd": remaining + D27_RAISE_USD - forecast,
            "fires_with_raise": _fires_at(forecast, remaining + D27_RAISE_USD, complete),
            "cap_needed_usd": spent + forecast,
            "raise_needed_usd": max(0.0, spent + forecast - cap),
            "pending_spend": None if not stand_ins else {
                "note": "PROVISIONAL sensitivity, not the rule: the pending re-runs are not yet "
                        "in costs.csv; each priced at its original's billed cost",
                "runs": [e.run_id for e in stand_ins], "est_usd": pending_spend,
                "remaining_usd": after, "headroom_usd": after - forecast,
                "fires": _fires_at(forecast, after, complete),
                "headroom_with_raise_usd": after + D27_RAISE_USD - forecast,
                "fires_with_raise": _fires_at(forecast, after + D27_RAISE_USD, complete)},
            "measured_cost_reading": {
                "note": "descriptive, NOT the pre-registered rule: each S1 and S2 run priced "
                        "at S0's measured billed cost per run on its game",
                "s1_s2_usd": s12_measured,
                "forecast_usd": (seed2 + s12_measured) * (1 + rho),
                "headroom_usd": remaining - (seed2 + s12_measured) * (1 + rho),
                "cap_needed_usd": spent + (seed2 + s12_measured) * (1 + rho)}}


def readings(b: Block, games: list[str], spent: float, cap: float) -> dict:
    return {"games": list(games), "gap": gap_reading(b, games),
            "gap_at_k": gap_at_k_reading(b, games), "errors": error_reading(b, games),
            "cost": cost_reading(b, games, spent, cap)}


# --- per run -------------------------------------------------------------------------------

def g0_forecasts(g0: dict) -> dict[tuple[str, str], float]:
    """Each (game, config)'s G0 forecast: published list cost × b(c) (§10.1)."""
    cost = g0["cost"]
    out = {}
    for g in cost["games"]:
        for c in ("S0", "S1", "S2", "S4"):
            listed = {"S0": g["L_S0"], "S4": g["L_S4"]}.get(c, g["L_midpoint"])
            out[(g["game"].upper(), c)] = listed * cost["b"][c]
    return out


def run_row(e: Entry, b: Block, forecasts: dict[tuple[str, str], float]) -> dict:
    r = e.run
    fc = forecasts.get((e.game, e.config))
    row = {"run_id": e.run_id, "game": e.game, "config": e.config, "replicate": e.replicate,
           "seed": e.seed, "rerun_of": e.rerun_of, "replaced_by": list(e.replaced_by),
           "counted": not e.replaced_by and not e.truncated,
           "rerun_pending": any(u.pending and u.original is e for u in b.units.values()),
           "block2": e.block2,
           "started_utc": e.started_utc, "agent_exit_reason": e.agent_exit_reason,
           "exit_reason": e.exit_reason, "d19_ending": e.d19_ending,
           "rerun_eligible": b.eligible.get(e.run_id),
           "scorecard": "truncated (not a counted run)" if e.truncated
           else e.skip_reason or "scored",
           "rhae": e.rhae, "levels_completed": r and r.levels_completed,
           "level_count": r and r.level_count, "actions": e.actions,
           "wall_clock_s": r and r.wall_clock_s,
           "seconds_per_action": r and r.per_action(r.wall_clock_s), "n_calls": e.n_calls,
           "median_s_per_call": e.median_s_per_call, "billed_usd": e.billed,
           "list_usd": e.listed, "g0_forecast_usd": fc,
           "billed_over_forecast": None if fc is None or e.billed is None else e.billed / fc,
           "costs_row": e.costs_row, "costs_row_block_tag": e.costs_tagged,
           "d20": b.d20.get(e.run_id)}
    assert tuple(row) == RUN_FIELDS
    return row


# --- inputs --------------------------------------------------------------------------------

def latest_g0(root: Path) -> Path:
    found = sorted((root / "gates").glob("g0-*/g0.json"))
    if not found:
        raise Refusal(f"no gates/g0-*/g0.json under {root} (the G0 forecasts)")
    return found[-1]


def the_draw(root: Path) -> Path:
    found = sorted((root / "draw").glob("*/draw.json"))
    if len(found) != 1:
        raise Refusal(f"expected exactly one draw/*/draw.json under {root}, found {len(found)}")
    return found[0]


def _incident_word(incident: bool | None) -> str:
    return {True: "incident", False: "not an incident"}.get(incident, "undetermined")


D20_RUN_FIELDS = ("run_id", "config", "game", "agent_exit_reason", "median_s_per_call",
                  "threshold_s", "incident", "rerun_eligible", "rerun_of", "replaced_by",
                  "rerun_allowed")


def d20_run(root: Path, run_id: str) -> dict:
    """D20 and D19 for one arc_path run (``--d20-run``; module docstring). Needs only
    costs.csv and the arc_path folders. Raises Refusal or am.Refused."""
    costs_csv = root / "costs.csv"
    if not costs_csv.is_file():
        raise Refusal(f"no costs.csv under {root} (the pilots' latency_s)")
    try:
        rows = costs.read_rows(costs_csv)
    except ValueError as e:
        raise Refusal(f"cannot read {costs_csv}: {e}") from None
    entries, _ = discover(root / EXPERIMENT)
    check_links(entries)
    e = next((x for x in entries if run_id in (x.run_id, x.folder.name)), None)
    if e is None:
        raise Refusal(f"unknown run {run_id}: no folder in {root / EXPERIMENT} with a "
                      "meta.json holds it")
    if e.truncated:
        raise Refusal(f"run {e.run_id} is truncated (not a counted run): D20 does not apply")
    pilots = pilot_latency(rows)
    d20 = d20_check(e, entries, pilots)
    out = {"run_id": e.run_id, "config": e.config, "game": e.game,
           "agent_exit_reason": e.agent_exit_reason, "median_s_per_call": e.median_s_per_call,
           "threshold_s": d20_readings(e, entries, pilots)["as_of_start"]["threshold_s"],
           "incident": None if d20 is None else d20["incident"],
           "rerun_eligible": rerun_eligible(e, d20),
           "rerun_of": e.rerun_of, "replaced_by": list(e.replaced_by)}
    # D19 allows one re-run: never for a re-run, nor for an original that already has one
    out["rerun_allowed"] = (None if out["rerun_eligible"] is None
                            else bool(out["rerun_eligible"]) and not e.rerun_of
                            and not e.replaced_by)
    assert tuple(out) == D20_RUN_FIELDS
    return out


def compute(root: Path, generated: str, git: dict) -> tuple[dict, Block]:
    """Checkpoint C's numbers from the files under `root`. Raises Refusal or am.Refused."""
    draw_path = the_draw(root)
    draw = json.loads(draw_path.read_text(encoding="utf-8"))
    games = [str(g).upper() for g in draw["games"]]
    perm = [str(g).upper() for g in draw["derived"]["perm"]]
    drop = str(draw["derived"]["fallback_drop_game_d32"]).upper()
    if sorted(perm) != sorted(games) or len(perm) != 4 or drop != perm[3]:
        raise Refusal(f"draw.json: D32's dropped game {drop} is not perm[3] of the beacon "
                      f"order {perm} of the path games {games} (PREREG §7.3, §10.6)")
    costs_csv = root / "costs.csv"
    if not costs_csv.is_file():
        raise Refusal(f"no costs.csv under {root}")
    try:
        rows = costs.read_rows(costs_csv)
        spent = costs.spend_by_phase(rows).get(PHASE, 0.0)
    except ValueError as e:
        raise Refusal(f"cannot read or sum {costs_csv}: {e}") from None
    cap = costs.PHASE_CAPS[PHASE]
    entries, bare = discover(root / EXPERIMENT)
    attach_costs(entries, rows)
    g0_path = latest_g0(root)
    forecasts = g0_forecasts(json.loads(g0_path.read_text(encoding="utf-8")))
    b = build_block(entries, bare, games, drop, pilot_latency(rows))
    if cap != CAP_1B_FROZEN:
        b.warnings.append(f"the phase-1b cap in common.costs.PHASE_CAPS is {_usd(cap)}, not "
                          f"the {_usd(CAP_1B_FROZEN)} §10.3 names; remaining uses "
                          f"{_usd(cap)}, and D27's raise of about {_usd(D27_RAISE_USD)} may "
                          "already be in it")
    three = [g for g in games if g != drop]
    four_r, three_r = readings(b, games, spent, cap), readings(b, three, spent, cap)
    three_r["cost"]["rho_over_all_block2"] = {
        "n_block2_runs": four_r["cost"]["n_block2_runs"], "rho": four_r["cost"]["rho"],
        "forecast_usd": (three_r["cost"]["seed2_usd"] + three_r["cost"]["s1_s2_usd"])
        * (1 + four_r["cost"]["rho"])}

    def rel(p: Path) -> str:
        p = p.resolve()
        return p.relative_to(REPO_ROOT).as_posix() if p.is_relative_to(REPO_ROOT) else str(p)

    out = {"generated_utc": generated, **git, "prereg_version": runmeta.prereg_version(),
           "status": PROVISIONAL if b.incomplete else FINAL,
           "provisional_reasons": list(b.incomplete), "warnings": list(b.warnings),
           "inputs": {"results_root": rel(root), "costs_csv": rel(costs_csv),
                      "g0_json": rel(g0_path), "draw_json": rel(draw_path),
                      "arc_path_folders": [rel(e.folder) for e in entries]},
           "path_games": games, "fallback_drop_game": drop,
           "phase_1b": {"spent_usd": spent, "cap_usd": cap, "remaining_usd": cap - spent},
           "readings": {"four_games": four_r, "three_games_d32": three_r},
           "runs": [run_row(e, b, forecasts) for e in sorted(entries,
                                                             key=lambda x: x.started)],
           "skipped": [{"folder": n, "reason": w} for n, w in b.bare]
           + [{"folder": e.folder.name, "reason": e.skip_reason}
              for e in entries if e.skip_reason]}
    assert tuple(out) == TOP_FIELDS
    return out, b


# --- summary -------------------------------------------------------------------------------

def _f(v, digits: int = 2, prefix: str = "") -> str:
    return "n/a" if v is None else f"{prefix}{v:,.{digits}f}"


def _usd(v, digits: int = 2) -> str:
    if v is None:
        return "n/a"
    return f"{'-' if v < 0 else ''}${abs(v):,.{digits}f}"


def _fires(v) -> str:
    return "undetermined" if v is None else ("**FIRES**" if v else "does not fire")


def _id(run_id: str | None) -> str:
    return "none" if run_id is None else f"`{run_id}`"


def _section(r: dict, title: str) -> list[str]:
    gap, gk, err, cost = r["gap"], r["gap_at_k"], r["errors"], r["cost"]
    L = [f"## {title}", "",
         f"### Gap rule: {_fires(gap['fires'])}", "",
         "| Game | S0 run | S4 run | RHAE S0 | RHAE S4 | Gap |", "|---|---|---|---|---|---|"]
    L += [f"| {g['game']} | {_id(g['S0_run'])} | {_id(g['S4_run'])} | {_f(g['rhae_S0'])} | "
          f"{_f(g['rhae_S4'])} | {_f(g['gap'])}{' (stand-in)' if g['stand_in'] else ''} |"
          for g in gap["games"]]
    L += ["", (f"Mean gap over {gap['n_games']} of {len(r['games'])} games: "
               f"**{_f(gap['mean_gap'])}** RHAE (fires if < {GAP_MIN:g}): "
               f"{_fires(gap['fires'])}"
               + ("" if gap["mean_gap_bounds"] is None else
                  " (the mean over all {} games is between {} and {} whatever the missing "
                  "games' gaps)".format(len(r["games"]), *map(_f, gap["mean_gap_bounds"])))
               + "."), "",
          f"At K = {gk['K']} (PREREG §17.5, descriptive; fires no rule):", "",
          "| Game | RHAE_K S0 (status, levels) | RHAE_K S4 (status, levels) | Gap at K |",
          "|---|---|---|---|"]
    L += [f"| {g['game']} | {_f(g['score_S0'])} ({g['status_S0']}, {g['levels_cleared_S0']}) | "
          f"{_f(g['score_S4'])} ({g['status_S4']}, {g['levels_cleared_S4']}) | "
          f"{_f(g['gap'])}{' (stand-in)' if g['stand_in'] else ''} |" for g in gk["games"]]
    L += ["", (f"Mean gap at K = {gk['K']} over {gk['n_games']} games: "
               f"**{_f(gk['mean_gap'])}**; censored counted runs (their values are lower "
               f"bounds): S0 {gk['censored']['S0']}, S4 {gk['censored']['S4']}. Without the "
               f"games that contain a censored run (§17.5's sensitivity analysis): "
               f"{_f(gk['without_censored']['mean_gap'])} over "
               f"{gk['without_censored']['n_games']} games.")]
    if gk["left_out"]:
        L.append("Left out (no matched values): "
                 + "; ".join(f"{x['game']} ({x['why']})" for x in gk["left_out"]) + ".")
    L += ["", f"### Error rule: {_fires(err['fires'])}", "",
          "| Game | Config | Counted run | Re-run? | Ending (D19) | Re-run-eligible | Why |",
          "|---|---|---|---|---|---|---|"]
    L += [f"| {x['game']} | {x['config']} | {_id(x['run_id'])} | {'yes' if x['rerun'] else 'no'} | "
          f"{x['ending']} | {x['rerun_eligible']} | {x['why']} |" for x in err["runs"]]
    L += ["", (f"Errors: **{err['errors']} of {err['n_runs']}** (fires if > {MAX_ERRORS}): "
               f"{_fires(err['fires'])}. Pending re-runs: {err['pending']} (up to "
               f"{err['errors_upper']} if each pending re-run also ends re-run-eligible)."),
          f"TIME_BUDGET: {err['time_budget']}.", "",
          f"### Cost rule (D27): {_fires(cost['fires'])}", "",
          ("| Game | S0 billed | S4 billed | S0 calls | S0 $/call | S0 actions | S4 actions | "
           "Seed 2 (S0 + S4) | S1 + S2, both seeds |"), "|---|---|---|---|---|---|---|---|---|"]
    L += [f"| {g['game']} | {_usd(g['billed_S0'])} | {_usd(g['billed_S4'])} | "
          f"{g['n_calls_S0']} | {_usd(g['S0_usd_per_call'], 4)} | {g['actions_S0']} | "
          f"{g['actions_S4']} | {_usd(g['seed2'])} | {_usd(g['s1_s2'])} |" for g in cost["games"]]
    m = cost["measured_cost_reading"]
    L += ["", (f"- ρ = ({cost['reruns']} re-runs"
               + (f" + {cost['pending_reruns']} pending" if cost["pending_reruns"] else "")
               + f") / {cost['n_block2_runs']} = {cost['rho']:.3f}."),
          (f"- Forecast for the remaining {cost['n_remaining_runs']} runs: "
           f"({_usd(cost['seed2_usd'])} + {_usd(cost['s1_s2_usd'])}) × (1 + ρ) = "
           f"**{_usd(cost['forecast_usd'])}** billed"
           + ("" if cost["complete"] else " (PARTIAL: a game lacks inputs)") + "."),
          (f"- Remaining 1b: {_usd(cost['cap_1b_usd'])} cap − {_usd(cost['spent_1b_usd'])} "
           f"spent = **{_usd(cost['remaining_usd'])}**; headroom "
           f"{_usd(cost['headroom_usd'])}: {_fires(cost['fires'])}."),
          (f"- With D27's raise of about {_usd(cost['raise_allowed_usd'])}: headroom "
           f"{_usd(cost['headroom_with_raise_usd'])} ("
           + {True: "still fires", False: "fits", None: "undetermined"}[
               cost["fires_with_raise"]] + ")."),
          (f"- Cap the forecast needs: {_usd(cost['cap_needed_usd'])} (a raise of "
           f"{_usd(cost['raise_needed_usd'])} over {_usd(cost['cap_1b_usd'])})."),
          *_pending_spend_lines(cost),
          (f"- *Descriptive, not the pre-registered rule:* with S1 and S2 at S0's measured "
           f"billed cost per run, S1 + S2 = {_usd(m['s1_s2_usd'])}, forecast "
           f"{_usd(m['forecast_usd'])}, headroom {_usd(m['headroom_usd'])}, cap needed "
           f"{_usd(m['cap_needed_usd'])}.")]
    if "rho_over_all_block2" in cost:
        alt = cost["rho_over_all_block2"]
        L.append(f"- With ρ over all {alt['n_block2_runs']} block-2 runs ({alt['rho']:.3f}) "
                 f"instead: forecast {_usd(alt['forecast_usd'])}.")
    return L


def _pending_spend_lines(cost: dict) -> list[str]:
    p = cost["pending_spend"]
    if p is None:
        return []
    word = {True: "fires", False: "fits", None: "undetermined"}
    return [(f"- *PROVISIONAL sensitivity, not the rule:* the spend to date leaves out "
             f"{len(p['runs'])} pending re-run(s), not yet paid. If each costs what its "
             f"original did ({_usd(p['est_usd'])} in all), remaining falls to "
             f"{_usd(p['remaining_usd'])}: headroom {_usd(p['headroom_usd'])} "
             f"({word[p['fires']]}), and {_usd(p['headroom_with_raise_usd'])} with the raise "
             f"({word[p['fires_with_raise']]}). The re-run's own cost, calls and actions will "
             "also replace its original's in the forecast.")]


def summary_lines(c: dict) -> list[str]:
    status = c["status"]
    L = ["# Checkpoint C metrics (PREREG §10.3)", "",
         (f"Computed {c['generated_utc']} at commit {c['git_commit'][:7]} (dirty: "
          f"{c['git_dirty']}) by `uv run python -m analysis.checkpoint_c`, from "
          f"`{c['inputs']['results_root']}`."), "",
         f"**Status: {status}.**"]
    if c["provisional_reasons"]:
        L += ["", "Block 2 is not complete, so these numbers are provisional:"]
        L += [f"- {x}" for x in c["provisional_reasons"]]
    four = c["readings"]["four_games"]
    L += ["", "| Rule | Reading | Fires |", "|---|---|---|",
          (f"| Gap | mean {_f(four['gap']['mean_gap'])} RHAE over {four['gap']['n_games']} "
           f"games (< {GAP_MIN:g}) | {_fires(four['gap']['fires'])} |"),
          (f"| Errors | {four['errors']['errors']} of {four['errors']['n_runs']} "
           f"(> {MAX_ERRORS}) | {_fires(four['errors']['fires'])} |"),
          (f"| Cost | forecast {_usd(four['cost']['forecast_usd'])} against remaining "
           f"{_usd(four['cost']['remaining_usd'])} | {_fires(four['cost']['fires'])} |"), ""]
    L += _section(four, f"The 4 path games ({', '.join(four['games'])})")
    three = c["readings"]["three_games_d32"]
    L += ["", (f"Under the 3-game fallback (D32), {c['fallback_drop_game']} (perm[3]) leaves "
               "block 3; its block-2 runs are reported as exploratory, and Checkpoint C uses "
               "the 3 other games with the same thresholds (6 seed-1 runs, 18 remaining runs).")]
    L += [""] + _section(three, f"3-game fallback, D32 ({', '.join(three['games'])})")
    L += ["", "## Per run", "",
          ("| Run | Game | Config | Rep. | Counted | Ending: agent; exit | RHAE | Actions | "
           "Billed (G0 forecast, ratio) | s per action | Model calls | Median s per call | "
           "D20 |"), "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in c["runs"]:
        d = r["d20"]
        if d is None:
            d20 = "n/a (not TIME_BUDGET)"
        else:
            a = d["as_of_start"]
            src = a["yardstick_from"]
            src = ", ".join(f"`{x}`" for x in src) if isinstance(src, list) else src
            d20 = (f"{_f(d['median_s_per_call'])} s vs 2 × {_f(a['yardstick_s'])} s "
                   f"(from {src}): **{_incident_word(a['incident'])}**"
                   + ("" if d["readings_agree"] else
                      " (final-set reading disagrees: "
                      f"{d['final_counted_set']['incident']})"))
        L.append(f"| `{r['run_id']}` | {r['game']} | {r['config']} | {r['replicate']} | "
                 f"{'stand-in, re-run pending' if r['rerun_pending'] else r['counted']} | "
                 f"{r['agent_exit_reason']}; {r['exit_reason']} | "
                 f"{_f(r['rhae'])} | {r['actions']} | {_usd(r['billed_usd'])} "
                 f"({_usd(r['g0_forecast_usd'])}, {_f(r['billed_over_forecast'])}×) | "
                 f"{_f(r['seconds_per_action'], 1)} | {r['n_calls']} | "
                 f"{_f(r['median_s_per_call'])} | {d20} |")
    L += ["", (f"Phase 1b: {_usd(c['phase_1b']['spent_usd'])} spent of "
               f"{_usd(c['phase_1b']['cap_usd'])} (`costs.csv`, every phase-1b row, billed "
               "estimate, list where a row has none).")]
    if c["warnings"] or c["skipped"]:
        L += ["", "## Checks", ""]
        L += [f"- {w}" for w in c["warnings"]]
        L += [f"- skipped `{s['folder']}`: {s['reason']}" for s in c["skipped"]]
    L += ["", "## What this does not show", "",
          ("- One seed per config and game: the gap is noisy, which is why its threshold (5) "
           "is looser than G2's kill at 10 (§10.3)."),
          ("- Four games (three under D32), chosen because ARC's published Standard-to-Adapter "
           "gap on them was at least 20 (§7.2): the gap is conditional on games where the "
           "Adapter helped, and says nothing about other games, models or efforts."),
          ("- It does not decompose the gap: S1 and S2 have not run, so nothing here says which "
           "step (loss policy, notes, replay) accounts for it (H4)."),
          ("- The cost forecast prices S1 and S2 from S0's measured cost per call. S1 and S2 "
           "keep their history until a summary at 175k tokens, where S0 drops its oldest "
           "turns above 175k characters, and they were slower per call than S0 in the pilot, "
           "so their cost per call may be higher; it is not measured here."),
          ("- The gap at K is descriptive (§17.5): it fires no rule, and its censored runs "
           "are lower bounds."),
          "- Nothing here compares models; it describes one model's runs under two configs.",
          "", "The researcher makes the go/no-go call."]
    return L


# --- main ----------------------------------------------------------------------------------

def write(out_dir: Path, run_id: str, c: dict, text: str, git: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "checkpoint_c.json").write_text(
        json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (out_dir / "summary.md").write_text(text, encoding="utf-8", newline="\n")
    config = {"prereg": "PREREG.md §10.3 (with §7.5 D19/D20, §10.1 D27, §10.6 D32, §17.5, "
                        "§17.6 change 5)",
              "gap_min": GAP_MIN, "max_errors": MAX_ERRORS, "d27_raise_usd": D27_RAISE_USD,
              "d20_factor": D20_FACTOR, "d20_scaled_configs": list(SCALED_CONFIGS),
              "K": K, "block": BLOCK,
              "path_games": c["path_games"], "fallback_drop_game": c["fallback_drop_game"],
              "status": c["status"], "inputs": c["inputs"]}
    return runmeta.write_meta(
        out_dir, git=git, experiment="checkpoint_c", run_id=run_id,
        cell_or_config="checkpoint_c", config=config, model_requested=None,
        model_returned=None, reasoning_effort=None, reasoning_context_requested=None,
        reasoning_context_echoed=None, template_id=None, repeat_index=None, seeds=None,
        started_utc=c["generated_utc"], finished_utc=runmeta.utc_now(),
        exit_reason="completed" if c["status"] == FINAL else "completed_provisional",
        tokens=None, cost_usd=0.0, raw_transcript_path=None, outputs=list(OUTPUTS),
        paid_calls=0, runs=[r["run_id"] for r in c["runs"]])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--results-root", type=Path, default=RESULTS,
                    help="the results folder to read (default: this checkout's results/)")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="default: <results root>/checkpoint_c/<UTC>/")
    ap.add_argument("--no-write", action="store_true", help="print only")
    ap.add_argument("--allow-incomplete", action="store_true",
                    help="compute a PROVISIONAL reading while block 2 is incomplete")
    ap.add_argument("--d20-run", metavar="RUN_ID", default=None,
                    help="print one JSON line with D20's threshold and verdict and D19's "
                         "re-run eligibility for this arc_path run, and exit (the block-3 "
                         "driver's check; PREREG §17.6 change 5)")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    if a.d20_run is not None:
        try:
            print(json.dumps(d20_run(a.results_root.resolve(), a.d20_run), ensure_ascii=False))
        except (Refusal, am.Refused) as e:
            print(f"D20 check refused: {e}", file=sys.stderr)
            return 2
        return 0
    now = datetime.now(UTC)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    git = runmeta.git_state()
    root = a.results_root.resolve()
    try:
        c, _ = compute(root, now.isoformat(timespec="seconds"), git)
    except (Refusal, am.Refused) as e:
        print(f"Checkpoint C refused: {e}", file=sys.stderr)
        return 2
    if c["status"] != FINAL and not a.allow_incomplete:
        print("Checkpoint C refused: block 2 is incomplete:\n"
              + "\n".join(f"  - {x}" for x in c["provisional_reasons"])
              + "\nWait for block 2 to end, or pass --allow-incomplete for a PROVISIONAL "
              "reading.", file=sys.stderr)
        return 2
    text = "\n".join(summary_lines(c)) + "\n"
    print(text)
    if not a.no_write:
        out = a.out_dir or root / "checkpoint_c" / run_id
        write(out, run_id, c, text, git)
        print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
