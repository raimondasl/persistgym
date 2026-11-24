"""R13's descriptive analysis: Σ-n-0 on Haiku, and W-nk-0 beside a concurrent W-n-0 (PREREG §17.13; $0, no test).

R13 registers two experiments, numbered after R12's three, each in its own folder and played
under block `9-r13`:

4. `persistgym_haiku_r13_sigma`: claude-haiku-5-5 ("Haiku") in Σ-n-0, luna's summary cell on
   the Messages wire, on all 8 task cells, main templates 0-199 (R8's episodes), in 4 runs of 50
   templates. Its comparators are read on its templates and resamples as arms beside it: R8's
   W-0 and F-0 of 2026-10-18 as R8's cited output counted them (`analysis.haiku_notes.
   R8_OUTPUT`) and R12's W-b-0 as R12's cited output counted it (`R12_OUTPUT`). On the 2
   not-recoverable far cells R9's W-n-0, as its cited output counted it (`analysis.
   haiku_provenance.R9_OUTPUT`), is a fourth comparator. luna's Σ-n-0 (`persistgym_h1h3.
   LUNA_CITED_OUTPUT`) is set beside it, described only.
5. `persistgym_haiku_r13_pinned`: Haiku in W-nk-0 (W-n-0 with a pinned block of its own dropped
   replies) and a concurrent W-n-0 on the 2 not-recoverable far task cells, main templates
   200-299, in 4 rounds of 25 templates. Each round plays both arms, one run each, W-nk-0 first
   in rounds 1 and 3 and W-n-0 first in rounds 2 and 4 (`registered.r13_round_arms`). R12
   experiment 1's four arms on the same templates, as R12's cited output counted them, are set
   beside it, described only.

This script implements the readings of PREREG §17.13 (amendment R13) as written. Nothing here
is a test. It ranks nothing, and differences are described, not tested.

**Exclusions and errors,** R8's (§17.8) as R9 to R12 apply them (`analysis.r12`). Each
experiment's records are read through `persistgym_h1h3.discover` and `resolve`: DESIGN §7.8's
first-final-record rule with the re-run links of ``--rerun``, §13's exclusions on the Messages
API (no echo exclusion), the episodes a request-side check stopped excluded
(`request_check_stops`). Refusals and empty replies score 0 at the need step, as the runner
records them. A Σ-n-0 episode that ended ``AGENT_ERROR`` after 4 failed summaries is final and
counted (`persistgym_h1h3`, ruled item 2). Before any reading:
- Every record must be on its experiment's registered cells, task cells and templates, base
  episodes at repeat 0, and every run folder under an experiment must be one of its runs, on
  one of its registered cells, on Haiku.
- An API error awaiting its §13 re-run refuses, whether or not the sweep is closed.
- Each experiment's sweep must be complete over its registered templates
  (`persistgym_h1h3.completeness`), or closed by the researcher with ``--sweep-closed`` for that
  experiment. As in R12, no registered stop closes a sweep. Otherwise the script refuses,
  unless ``--allow-incomplete`` is passed, and the output is then PROVISIONAL.
- §2.8's accounting check (`persistgym_h1h3.accounting_check`) on each experiment's raw
  transcripts under ``--raw-root`` (default ``results/raw``). It replays W-n-0 and W-nk-0 by the
  sliding window, with W-nk-0's pinned block taken off first (the block is not counted toward
  W), so W-nk-0 is checked exactly as W-n-0. Σ-n-0 is not a window cell and is not replayed. A
  bug stops the analysis (`AccountingBug`), even as PROVISIONAL. Missing transcripts refuse, or
  make the output PROVISIONAL with ``--allow-incomplete``. The comparators passed their own
  analyses' checks and are not replayed again. Their readings here come from their records.
- With no run in any experiment read, the script names the missing experiments and refuses,
  with or without ``--allow-incomplete``: before R13's runs there is nothing to read.

**A reading of some experiments.** ``--experiment`` (sigma, pinned; repeatable) limits a
reading to the experiments it names, as in R12.

**The templates read.** Within each experiment, every arm is read on the templates that it and
every other arm finished in every task cell (`templates_read`), and each key that leaves a
template out is named, with its status and reason (`left_out`). In experiment 4 the arms are
Σ-n-0, R8's W-0 and F-0 and R12's W-b-0. R9's W-n-0 plays only in the contrast on the 2
not-recoverable far cells, on the templates read that it also finished in both, and the keys of
its that leave one out are named. The arms set beside an experiment (luna's Σ-n-0, R12
experiment 1's) are read on its templates read that they finished, naming the keys left out.

**Intervals.** 90% template-cluster bootstrap percentiles with 10,000 resamples, seed SEED + 10
(`BOOT_SEED_OFFSET`, §9.1's, as for R8's to R12's; SEED from the committed draw), the same
resamples for every arm of an experiment. Experiment 4 uses the resamples of R8 to R12 (T = 200),
indexed by template number, as R12's experiment 3 did, with the templates not read left out of
each mean (NaN). Experiment 5's resamples are over the templates read, mapped to 0..n-1 in
ascending order. In R9's contrast a template it did not finish is left out of each mean on both
sides (NaN), with the same resamples.

**The readings** (§17.13's, numbered as there). Experiment 4 (Σ-n-0):
1. Success per arm and task cell, with its interval, and each cell's step responses that
   stopped short, by reason.
2. Contrasts in percentage points per task cell, on the same templates and resamples: Σ-n-0
   minus R8's W-0, minus R8's F-0 and minus R12's W-b-0, and on the 2 not-recoverable far cells
   minus R9's W-n-0.
3. §2.8's accounting in the bridge, per task cell (`carried`): among the episodes whose need
   request held no evidence (S verbatim 0), P(carried) in the bridge (``need_bridge_carried``, a
   string match, so a lower bound) and success given carried. The retained replies and "either"
   (§2.8's S_carried, `persistgym_h1h3.accounting`) are given beside it.
4. Compaction and near cells: compactions per episode, ``compacted_between`` (D12) per task cell
   with S and success in each group, and per near cell the episodes whose evidence was not in
   the need step's request (``need_payload.S`` false), with their success.
5. Summary calls, per task cell and over all 8: summary requests and failed attempts per
   episode, the summary responses that stopped short by reason (refusals by category), the
   episodes that ended ``AGENT_ERROR`` after 4 failed summaries, the median bridge tokens
   (every compaction's bridge, and the bridge in the need step's request), and the summary
   calls' output tokens (median per call, mean per episode).
6. Choices with the fact evicted: on the 2 not-recoverable far cells, per arm but F-0, the
   episodes that chose one of the 10 options at the need step, and how many were correct.
7. Responses: Σ-n-0's step responses that were refused (by category) and those with a thinking
   block (presence only, a ``redacted_thinking`` block counting as one), its summary responses
   with one apart, and per arm the output tokens, cost (billed estimate) and input tokens per
   episode and the cache-read share of input.
8. Beside luna's Σ-n-0 on the same task cells and templates: success, P(carried) in the bridge
   and either, success given carried, and ``compacted_between``. Described only: no contrast
   between the models is computed or tested.

Experiment 5 (W-nk-0 and W-n-0):
1. Success per arm and task cell, with its interval, and the step responses that stopped short.
2. Contrast W-nk-0 minus W-n-0 per task cell, on the same templates and resamples.
3. §2.8's accounting per arm and task cell (`carried`): P(carried) in the pinned block
   (``need_pinned_carried``) and in the retained replies (``need_payload.assistant_carried``),
   each apart, and in either (§2.8's S_carried), each with success given carried.
4. The block at the need step's first request (``need_info``): how often it was there, its
   median tokens and replies, how often the newest reply alone passed the cap
   (``pinned_over_cap``: the newest is always kept whole, so the block passes the cap only so),
   and the replies left out.
5. Declines: per arm and task cell, the failed episodes whose carried notes held the fact (either
   source), and among them those whose need-step reply declines (resolved to no option) or
   disowns an earlier figure, with R9's text pattern (`analysis.haiku_notes_replies`'s
   `DISOWN` and `episode_reading`, which `analysis.haiku_provenance` reads), from the
   transcripts. `haiku_notes_replies.tally` of the same rows is given too, by carried.
6. Choices with the fact evicted, per arm.
7. Responses per arm: refusals by category and responses with a thinking block (as in
   experiment 4), the retained replies' median length at the need step (one reply's length,
   pooled per arm and task cell, as R12 gave it: `analysis.r12.retained`), output tokens and
   cost per episode, and the cache-read share of input.
8. Rounds: success per arm and round on the templates read, pooled over the 2 task cells (task
   cell "all") and then per task cell, and each run's start and finish (UTC). The arm that
   started each round is read from the runs' start times (`first_arm`) and given beside the
   registered order, and a round started by another arm is a warning. Described only.
9. Beside R12 experiment 1's four arms on the same templates: success, P(carried) and success
   given carried. Described only. They ran on 2026-11-12, not at the same time.

The summary and readings.json also state what the readings do not show (`DOES_NOT_SHOW`), and
the summary repeats its caveats next to the readings they bear on.

Run: ``uv run python -m analysis.r13 [--rerun RUN=ORIGINAL ...] [--sweep-closed sigma|pinned
...] [--experiment sigma|pinned ...]``. It writes ``results/r13/<UTC>/readings.json``,
``summary.md`` and ``meta.json``. With ``--no-write`` it only prints. ``--comparators-root``
reads the comparators from another results root (default: the results root).
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import numpy as np

from analysis import haiku_notes as hn
from analysis import haiku_notes_replies as hnr
from analysis import haiku_provenance as hp
from analysis import haiku_provenance_extras as hpe
from analysis import persistgym_h1h3 as hh
from analysis import r12
from common import runmeta
from harnesses import registered
from harnesses.wire import MESSAGES
from persistgym.episode import TaskCell

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_NAME = "r13"
OUTPUTS = ("readings.json", "summary.md", "meta.json")
SIGMA = registered.R13_SIGMA_EXPERIMENT
PINNED = registered.R13_PINNED_EXPERIMENT
EXPERIMENTS = registered.R13_EXPERIMENTS
SHORT = {"sigma": SIGMA, "pinned": PINNED}
"""``--sweep-closed`` and ``--experiment`` name an experiment by these short names."""
LABEL = {SIGMA: "Experiment 4", PINNED: "Experiment 5"}
BOOT = hn.BOOT
BOOT_SEED_OFFSET = hh.BOOT_SEED_OFFSET
"""§9.1's bootstrap seed offset (SEED + 10), as for R8's to R12's (PREREG §17.13)."""
ROUND = registered.R13_ROUND_TEMPLATES
NR_FAR = registered.HAIKU_CONTROL_TASK_CELLS
HAIKU = registered.HAIKU_MODEL
R12_OUTPUT = "results/r12/20261113T065503Z"
"""R12's cited readings (FINAL): its meta.json lists the runs and re-run links that it counted.
Experiment 4 reads R12's W-b-0 and experiment 5 R12 experiment 1's arms as it counted them."""
R8_ARMS = ("W-0", "F-0")
R12_NOTES_CELLS = tuple(registered.R12_SPECS[registered.R12_NOTES_EXPERIMENT]["cells"])
SIGMA_CELL = "Σ-n-0"
PINNED_CELL = "W-nk-0"


def r8_name(cell: str) -> str:
    return f"{cell} (R8)"


W0_R8, F0_R8 = r8_name("W-0"), r8_name("F-0")
WB_R12 = "W-b-0 (R12)"
WN_R9 = "W-n-0 (R9)"
LUNA_ARM = "Σ-n-0 (luna)"
CONTRASTS = {
    SIGMA: ((SIGMA_CELL, W0_R8), (SIGMA_CELL, F0_R8), (SIGMA_CELL, WB_R12)),
    PINNED: ((PINNED_CELL, "W-n-0"),),
}
"""Reading 2: (minuend arm, subtrahend arm) per experiment, on every task cell, in the
order of §17.13. Experiment 4's contrast with R9's W-n-0 (`R9_CONTRAST`) is on the 2
not-recoverable far cells only."""
R9_CONTRAST = (SIGMA_CELL, WN_R9)
DOES_NOT_SHOW = (
    ("Everything R8 to R12 say they do not show also holds here: one model per provider in the "
     "confirmatory sense, the same synthetic task family, thinking text not inspected."),
    ("Experiment 4 is not concurrent with its comparators. R8's W-0 and F-0 ran on 2026-10-18, "
     "R9's W-n-0 on 2026-10-24 and R12's W-b-0 on 2026-11-12 and 2026-11-13. Success "
     "differences against them mix the summary with any change in serving since."),
    ("One summary rule is run: ARC's summary prompts, with every earlier turn compacted when the "
     "context passes W. Other summary prompts, or summaries that keep recent turns, are not run."),
    ("In experiment 5 the pinned block differs from W-n-0's scrolling history in two ways at "
     "once. The replies are kept outside the window, and the block carries its own label. A "
     "difference between the arms does not separate the two. One cap (600 reply tokens) is "
     "run."),
    ("No model comparison. luna's Σ-n-0 is another model of another provider, on another API. "
     "Setting it beside Haiku's describes how each behaved on these episodes. It does not rank "
     "them."),
    ("R12 experiment 1's arms ran on 2026-11-12, not at the same time as experiment 5, and are "
     "set beside it, described only."),
    ("Coarse intervals: every arm plays each template once. P(carried) is a string match, so a "
     "lower bound, and the decline and disown counts are text patterns, not a validated coding."),
)
"""What R13's readings do not show, as the summary and readings.json state it."""
NOTE_NOT_CONCURRENT = ("The comparators ran on 2026-10-18 (R8), 2026-10-24 (R9) and 2026-11-12 "
                       "to 13 (R12), so these differences mix the cell with any change in "
                       "serving (see What it does not show).")
NOTE_LOWER_BOUND = "P(carried) is a string match on the need step's first request: a lower bound."
NOTE_LABEL = ("W-nk-0's block keeps the replies outside the window and labels them, so the "
              "contrast does not separate the two (see What it does not show).")
NOTE_LUNA = ("luna's Σ-n-0 is another model on another API: set beside Haiku's, described only, "
             "with no contrast between the models.")
NOTE_R12 = "R12 experiment 1 ran on 2026-11-12, not at the same time as experiment 5."
NOTE_PATTERN = ("Declines and disowns are R9's text patterns (`analysis.haiku_notes_replies`), "
                "which R9's hand checks found to undercount (40 of 62 declines, 45 of 63 "
                "retractions): pointers rather than a validated coding.")
"""The caveats the summary repeats next to the readings they bear on."""


# --- reading the experiments ---------------------------------------------------------------

def spec(experiment: str) -> dict:
    return registered.R13_SPECS[experiment]


def templates_of(experiment: str) -> range:
    first, stop = spec(experiment)["templates"]
    return range(first, stop)


def profile(experiment: str) -> hh.Profile:
    """What `persistgym_h1h3.discover` reads for one R13 experiment: R8's settings (the default
    generator config, the Messages API) with the experiment's model and cells."""
    s = spec(experiment)
    return replace(hh.profile(HAIKU), model=s["model"], name=experiment, experiment=experiment,
                   registered_experiment=experiment, cells=tuple(s["cells"]),
                   registered_cells=tuple(s["cells"]), replication=False)


def discover(root: Path, experiment: str) -> list:
    """The experiment's runs (none if its folder does not exist). A folder that is not one of
    its runs (another model's, a pilot's config), a run off its registered cells, or a record
    off its registered task cells, templates, variant or repeat, refuses."""
    if not (root / "results" / experiment).is_dir():
        return []
    runs, skipped = hh.discover(root / "results", prof=profile(experiment))
    if skipped:
        raise hh.Refusal(f"run folders under results/{experiment}/ that are not R13's runs of "
                         "it: " + "; ".join(f"{x['folder']}: {x['reason']}" for x in skipped))
    s, registered_templates = spec(experiment), templates_of(experiment)
    off_cells = [f"{run.run_id}: cell {run.cell!r} is not one of R13's {experiment} cells "
                 f"({', '.join(s['cells'])})" for run in runs if run.cell not in s["cells"]]
    if off_cells:
        raise hh.Refusal("\n".join(off_cells))
    records = [rec for run in runs for rec in run.records]
    off = sorted({rec["task_cell"] for rec in records} - set(s["task_cells"]))
    if off:
        raise hh.Refusal(f"R13's {experiment} plays {', '.join(s['task_cells'])} only, but "
                         f"records hold {', '.join(off)}")
    outside = sorted({hh.template_index(rec["template_id"]) for rec in records}
                     - set(registered_templates))
    if outside:
        raise hh.Refusal(f"R13's {experiment} plays main templates {registered_templates.start}-"
                         f"{registered_templates.stop - 1} only, but records hold template(s) "
                         + ", ".join(str(t) for t in outside[:5]))
    odd = sorted({str(rec.get("episode_id")) for rec in records
                  if (rec.get("variant") or hh.BASE) != hh.BASE
                  or rec.get("repeat_index", 0) != 0})
    if odd:
        raise hh.Refusal(f"R13's {experiment} plays base episodes at repeat 0 only, but records "
                         f"hold {', '.join(odd[:5])}")
    return runs


def split_links(links: dict[str, str], runs: dict[str, list]) -> dict[str, dict[str, str]]:
    """``--rerun`` links by the experiment that holds the re-run or continuation."""
    where = {r.run_id: e for e, rs in runs.items() for r in rs}
    out: dict[str, dict[str, str]] = {e: {} for e in runs}
    for run, orig in links.items():
        if run not in where:
            raise hh.Refusal(f"--rerun {run}={orig}: {run} is not a run of R13's experiments")
        out[where[run]][run] = orig
    return out


# --- the comparators, as their cited outputs counted them -------------------------------------

@lru_cache(maxsize=2)
def r8_arms(root: Path) -> tuple[r12.Arm, ...]:
    """R8's W-0 and F-0 of 2026-10-18 (`haiku_notes.r8_counted`)."""
    runs, resolved = hn.r8_counted(root)
    return tuple(r12.Arm(r8_name(c), c, HAIKU, registered.HAIKU_EXPERIMENT, resolved,
                         [r for r in runs if r.cell == c and r.repeat_index == 0
                          and hh.BASE in r.variants]) for c in R8_ARMS)


@lru_cache(maxsize=4)
def r12_counted(root: Path, experiment: str) -> tuple[list, dict]:
    """One R12 experiment's runs and resolution, as R12's cited output counted them (the runs
    its readings.json lists for the experiment, its re-run links and closed sweeps). Runs that
    differ from those it lists refuse."""
    out = root / R12_OUTPUT
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    cited = json.loads((out / "readings.json").read_text(encoding="utf-8"))["experiments"]
    runs = r12.discover(root, experiment)
    found = {r.run_id for r in runs}
    listed = {x["run_id"] for x in (cited.get(experiment) or {}).get("runs", [])}
    if not runs or found != listed:
        raise hh.Refusal(f"R12's {experiment} runs under results/ ({', '.join(sorted(found))}) "
                         f"are not those {R12_OUTPUT} counted ({', '.join(sorted(listed))})")
    links = {a: b for a, b in meta["config"]["rerun_links"].items() if a in found}
    resolved, _ = hh.resolve(runs, links,
                             sweep_closed=experiment in meta["config"]["sweep_closed"],
                             echo=False, stopped=hh.request_check_stops(runs))
    return runs, resolved


def r12_arm(root: Path, experiment: str, cell: str) -> r12.Arm:
    runs, resolved = r12_counted(root, experiment)
    return r12.Arm(f"{cell} (R12)", cell, HAIKU, experiment, resolved,
                   [r for r in runs if r.cell == cell])


@lru_cache(maxsize=2)
def r9_arm(root: Path) -> r12.Arm:
    """R9's W-n-0 run of 2026-10-24 (`haiku_provenance.r9_read`)."""
    runs, resolved = hp.r9_read(root)
    return r12.Arm(WN_R9, hp.R9_CELL, HAIKU, registered.HAIKU_NOTES_EXPERIMENT, resolved,
                   [r for r in runs if r.cell == hp.R9_CELL])


@lru_cache(maxsize=2)
def luna_arm(root: Path) -> r12.Arm:
    """luna's Σ-n-0, as its cited output counted it (its input list, re-run links and closed
    sweep), on the Responses API."""
    cfg = json.loads((root / hh.LUNA_CITED_OUTPUT / "meta.json").read_text(
        encoding="utf-8"))["config"]
    prof = hh.profile()
    runs, _ = hh.discover(root / "results", cfg["inputs"]["input_list"], prof)
    resolved, _ = hh.resolve(runs, cfg["rerun_links"], sweep_closed=cfg["sweep_closed"] is not None,
                             echo=prof.echo, stopped={})
    return r12.Arm(LUNA_ARM, SIGMA_CELL, registered.LUNA_MODEL, registered.LUNA_EXPERIMENT,
                   resolved, [r for r in runs if r.cell == SIGMA_CELL])


# --- the templates read and the resamples ------------------------------------------------------

def positions(experiment: str, read: list[int]) -> tuple[dict[int, int], int]:
    """Where each template read sits in the bootstrap's arrays, and their length. Experiment 4:
    R8 to R12's (T = 200), by template number. Experiment 5: the templates read, mapped to
    0..n-1 in ascending order."""
    if experiment == SIGMA:
        return {t: t for t in read}, registered.HAIKU_T
    return {t: i for i, t in enumerate(sorted(read))}, len(read)


def side_read(arm: r12.Arm, read: list[int],
              task_cells: tuple[str, ...]) -> tuple[list[int], list[dict]]:
    """The templates read that an arm outside the experiment's intersection (R9's W-n-0 in its
    contrast, an arm set beside the experiment) finished in every task cell of `task_cells`, and
    the keys that leave a template read out, each with its status and reason."""
    keep, rows = [], []
    for t in read:
        gaps = []
        for tc in task_cells:
            key = r12._key(arm.cell, t, tc)
            r = arm.resolved.get(key)
            if r is None:
                gaps.append({"template": t, "arm": arm.name, "task_cell": tc,
                             "episode_id": key[1], "status": "no record",
                             "reason": "no run of the arm holds it"})
            elif r.status != "counted" or r.record is None:
                gaps.append({"template": t, "arm": arm.name, "task_cell": tc,
                             "episode_id": key[1], "status": r.status, "reason": r.reason})
        rows += gaps
        if not gaps:
            keep.append(t)
    return keep, rows


def by_template(a: r12.Arm, restricted: dict, task_cell: str, pos: dict[int, int],
                size: int) -> np.ndarray:
    return r12.by_template(restricted, a.cell, task_cell, pos, size)


# --- readings per arm ------------------------------------------------------------------------

def _rate(recs: list[dict]) -> dict:
    return r12._rate([float(bool(x.get("need_correct"))) for x in recs])


def _records(restricted: dict, cell: str, stop: int, task_cells: tuple[str, ...]) -> list[dict]:
    return [r.record for r in hp._counted(restricted, cell, stop, task_cells)]


def _src(rec: dict, source: str) -> bool:
    if source == "retained":
        return bool(((rec.get("need_payload") or {}).get("assistant_carried") or {})
                    .get("carried"))
    return bool((rec.get(f"need_{source}_carried") or {}).get("carried"))


def sources(cell: str) -> tuple[str, ...]:
    """Where a carry cell's carried fact is read at the need step: the retained replies, and in
    Σ-n-0 the bridge, in W-nk-0 the pinned block."""
    if cell in hh.SUMMARY_CELLS:
        return ("retained", "bridge")
    if cell in hh.PINNED_CELLS:
        return ("retained", "pinned")
    return ("retained",)


def carried(records: list[dict], cell: str) -> dict | None:
    """Reading 3 in one task cell: among the counted episodes whose need request held no
    evidence (``need_payload.S`` false, where §2.8 defines S_carried), how many carried the fact
    in each of the cell's sources (`sources`) apart and in either (§2.8's S_carried,
    `persistgym_h1h3._carried`), each with its success, and in the bridge or block, how many
    had one at the need step. None for a cell that carries nothing."""
    if cell not in hh.CARRY_CELLS:
        return None
    lost = [x for x in records if (x.get("need_payload") or {}).get("S") is False]
    srcs = sources(cell)
    out: dict = {"n": len(records), "S_verbatim_0": len(lost)}
    for s in (*srcs, "either"):
        hit = [x for x in lost if (any(_src(x, y) for y in srcs) if s == "either"
                                   else _src(x, s))]
        out[s] = {"carried": len(hit), "rate": len(hit) / len(lost) if lost else None,
                  "success_given_carried": _rate(hit)}
        if s in ("bridge", "pinned"):
            out[s]["present_at_need"] = sum(x.get(f"need_{s}_carried") is not None
                                            for x in lost)
    return out


def near_s_false(records: list[dict]) -> dict:
    """Readings 4 (experiment 4): per near cell, the episodes whose evidence was not in the need
    step's request (``need_payload.S`` false), and their success."""
    out = {}
    for tc in sorted({x["task_cell"] for x in records}):
        if TaskCell.from_id(tc).distance != "near":
            continue
        sub = [x for x in records if x["task_cell"] == tc]
        lost = [x for x in sub if (x.get("need_payload") or {}).get("S") is False]
        out[tc] = {"n": len(sub), "S_false": len(lost), "success_given_S_false": _rate(lost)}
    return out


def arm_reading(a: r12.Arm, restricted: dict, task_cells: tuple[str, ...], stop: int,
                pos: dict[int, int], size: int, idx: np.ndarray) -> tuple[dict, list[str]]:
    """Readings 1, 3 and 6 and the record part of 7 for one arm, from its restricted resolution,
    and the warnings. Choices are read in every cell that evicts (all but a full-history one)."""
    sub, warn = r12.primary(restricted, a.cell, task_cells)
    cells = hh.cell_table(sub, kinds=((a.cell, hh.BASE),), stopped=True, task_cells=task_cells)
    for row in cells:
        row["interval_90"] = hn.interval(by_template(a, restricted, row["task_cell"], pos, size),
                                         idx)
    recs = {tc: _records(restricted, a.cell, stop, (tc,)) for tc in task_cells}
    evicts = hh.SPECS[a.cell].history != "full"
    return ({"arm": a.name, "cell": a.cell, "model": a.model, "experiment": a.experiment,
             "counted_repeat_0": len(sub), "cells": cells,
             "accounting": hh.accounting(sub, cells=(a.cell,), task_cells=task_cells),
             "carried": ({tc: carried(recs[tc], a.cell) for tc in task_cells}
                         if a.cell in hh.CARRY_CELLS else None),
             "choices_nr_far": hp.choices(restricted, a.cell, stop) if evicts else None,
             "costs": r12.costs(restricted, a.cell, task_cells, stop, pooled=True),
             "near_need_payload_S_false": near_s_false(
                 [x for tc in task_cells for x in recs[tc]])}, warn)


def contrast_both(a: np.ndarray, b: np.ndarray, idx: np.ndarray) -> dict:
    """`haiku_notes.contrast` on the templates both sides finished: a template either lacks is
    left out of both sides' means (NaN), over the same resamples."""
    both = ~np.isnan(a) & ~np.isnan(b)
    return hn.contrast(np.where(both, a, np.nan), np.where(both, b, np.nan), idx)


def contrasts(e: str, arms: dict[str, r12.Arm], restricted: dict[str, dict],
              task_cells: tuple[str, ...], pos: dict[int, int], size: int, idx: np.ndarray,
              r9: tuple[r12.Arm, dict] | None = None) -> dict:
    """Reading 2 (`haiku_notes.contrast`: the same template resamples for both sides), and in
    experiment 4 the contrast with R9's W-n-0 on the not-recoverable far cells (`r9`: its arm
    and its resolution restricted to the templates read that it finished in both)."""
    def s(name: str, tc: str) -> np.ndarray:
        return by_template(arms[name], restricted[name], tc, pos, size)
    out = {f"{a} - {b}": {tc: hn.contrast(s(a, tc), s(b, tc), idx) for tc in task_cells}
           for a, b in CONTRASTS[e]}
    if r9 is not None:
        arm, res = r9
        out[f"{R9_CONTRAST[0]} - {R9_CONTRAST[1]}"] = {
            tc: contrast_both(s(SIGMA_CELL, tc), by_template(arm, res, tc, pos, size), idx)
            for tc in NR_FAR}
    return out


# --- experiment 4: compactions and summary calls -----------------------------------------------

def _mean(xs: list) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _dist(xs: list[int]) -> dict[str, int]:
    return {str(k): v for k, v in sorted(Counter(xs).items())}


def compaction(accounting: list[dict], records: dict[str, list[dict]]) -> dict:
    """Reading 4 for Σ-n-0, per task cell: compactions per episode (the successful ones,
    ``compactions``), and ``compacted_between`` (D12) with S and success in each group
    (`persistgym_h1h3.accounting`'s ``by_compacted_between``)."""
    acc = {x["task_cell"]: x for x in accounting}
    out = {}
    for tc, recs in records.items():
        n = [len(x.get("compactions") or []) for x in recs]
        out[tc] = {"episodes": len(recs), "compactions_per_episode": _mean(n),
                   "compactions_distribution": _dist(n),
                   "compacted_between": acc[tc].get("by_compacted_between")}
    return out


def summary_transcript(path: Path, records: dict[str, dict]) -> dict:
    """Reading 5's transcript part from one run: per episode whose counted record it holds, its
    summary responses (``kind`` "summary"): how many, their output tokens, those that stopped
    short by reason (`MessagesWire.status`: ``refusal:<category>``, ``max_output_tokens``, ...;
    ``empty`` for a completed one with no text), and those with a thinking block."""
    per = {e: {"calls": 0, "output_tokens": [], "stopped": Counter(), "thinking": 0}
           for e in records}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            d = json.loads(line)
            eid = d.get("episode_id")
            if eid not in per or d.get("kind") != "summary":
                continue
            response = d.get("response") or {}
            x = per[eid]
            x["calls"] += 1
            x["output_tokens"].append(MESSAGES.usage(response)["output_tokens"])
            status, reason = MESSAGES.status(response)
            if status != "completed":
                x["stopped"][str(reason)] += 1
            elif not MESSAGES.text(response).strip():
                x["stopped"]["empty"] += 1
            x["thinking"] += hpe._has_thinking(response)
    return per


def _bridge_at_need(rec: dict) -> int | None:
    """The tokens of the bridge in the need step's first request (``need_info.bridge_no``), or
    None when it held none."""
    info = rec.get("need_info") or {}
    if info.get("bridge_index") is None or not info.get("bridge_no"):
        return None
    comps = rec.get("compactions") or []
    k = int(info["bridge_no"]) - 1
    return comps[k].get("bridge_tokens") if 0 <= k < len(comps) else None


def summary_calls(records: dict[str, dict], task_cells: tuple[str, ...],
                  calls: dict[str, dict] | None) -> dict:
    """Reading 5 per task cell and over all of them ("all"): from the records, summary requests
    and failed attempts per episode, the episodes that ended AGENT_ERROR (the runner's ending
    after `summary_max_attempts`, 4, failed summaries), and the median bridge tokens; from the
    transcripts (`calls`, `summary_transcript`; None when any is missing), the summary
    responses that stopped short by reason and their output tokens."""
    out = {}
    for tc in (*task_cells, "all"):
        ids = sorted(e for e, x in records.items() if tc == "all" or x["task_cell"] == tc)
        recs = [records[e] for e in ids]
        bridges = [c.get("bridge_tokens") for x in recs for c in x.get("compactions") or []]
        at_need = [b for b in (_bridge_at_need(x) for x in recs) if b is not None]
        row = {"episodes": len(recs),
               "summary_requests_per_episode": _mean([int(x.get("n_summary_requests") or 0)
                                                      for x in recs]),
               "failed_attempts_per_episode": _mean([int(x.get("n_summary_failures") or 0)
                                                     for x in recs]),
               "failed_attempts": sum(int(x.get("n_summary_failures") or 0) for x in recs),
               "agent_error_episodes": sorted(x["episode_id"] for x in recs
                                              if x.get("exit_reason") == hh.AGENT_ERROR),
               "bridges": len(bridges),
               "bridge_tokens_median": r12._median([b for b in bridges if b is not None]),
               "need_bridge_episodes": len(at_need),
               "need_bridge_tokens_median": r12._median(at_need)}
        if calls is None:
            row.update(summary_responses=None, summary_stopped=None,
                       summary_output_tokens_median_per_call=None,
                       summary_output_tokens_mean_per_episode=None)
        else:
            per = [calls[e] for e in ids if e in calls]
            stopped: Counter = Counter()
            for x in per:
                stopped.update(x["stopped"])
            tokens = [t for x in per for t in x["output_tokens"]]
            row.update(summary_responses=sum(x["calls"] for x in per),
                       summary_stopped=dict(sorted(stopped.items())),
                       summary_refusals=dict(sorted((k, v) for k, v in stopped.items()
                                                    if k.startswith("refusal"))),
                       summary_with_thinking=sum(x["thinking"] for x in per),
                       summary_output_tokens_median_per_call=r12._median(tokens),
                       summary_output_tokens_mean_per_episode=_mean(
                           [sum(x["output_tokens"]) for x in per]))
        out[tc] = row
    return out


# --- experiment 5: the block at the need step, declines, rounds ------------------------------

def block_at_need(records: dict[str, list[dict]]) -> dict:
    """Reading 4 for W-nk-0, per task cell, from each record's need step's first request
    (``need_info``): the episodes that reached it, those whose request held the block
    (``pinned_index`` 0), the block's median tokens (``pinned_tokens``) and replies
    (``pinned_turns``), how often the newest reply alone passed the cap (``pinned_over_cap``),
    and the dropped replies the cap left out (``pinned_left_out``)."""
    out = {}
    for tc, recs in records.items():
        infos = [x["need_info"] for x in recs if x.get("need_info")]
        block = [i for i in infos if i.get("pinned_index") == 0]
        left = [int(i.get("pinned_left_out") or 0) for i in block]
        out[tc] = {"episodes": len(recs), "reached_need": len(infos), "with_block": len(block),
                   "block_tokens_median": r12._median([int(i["pinned_tokens"]) for i in block]),
                   "block_replies_median": r12._median([len(i.get("pinned_turns") or [])
                                                        for i in block]),
                   "newest_reply_over_cap": sum(bool(i.get("pinned_over_cap")) for i in block),
                   "replies_left_out": sum(left), "left_out_median": r12._median(left),
                   "episodes_with_replies_left_out": sum(x > 0 for x in left)}
    return out


def declines(a: r12.Arm, restricted: dict, stop: int, raw: Path) -> tuple[dict | None, list[str]]:
    """Reading 5 for one arm: R9's text pattern (`haiku_notes_replies.steps` and
    `episode_reading`, unchanged) on its counted not-recoverable far episodes, each read from
    the transcript of the run that holds its counted record, with an episode's "carried" read
    as §2.8's S_carried in either source (`persistgym_h1h3._carried`: the retained replies, or
    W-nk-0's pinned block). Per task cell: the failed episodes whose carried notes held the
    fact, and among them those whose need-step reply declines (no option), disowns an earlier
    figure (`DISOWN`), or either. Also `haiku_notes_replies.tally` of the same rows. None, with
    the runs, when a transcript is missing."""
    by_run = r12._by_run(restricted, a.cell, NR_FAR, stop)
    missing = sorted(run_id for run_id in by_run
                     if not r12._transcript(raw, a.experiment, run_id).is_file())
    if missing:
        return None, missing
    rows = []
    for run_id, recs in sorted(by_run.items()):
        trails = hnr.steps(raw, set(recs), path=r12._transcript(raw, a.experiment, run_id))
        for eid, rec in sorted(recs.items()):
            row = hnr.episode_reading(rec, trails[eid])
            row["carried"] = bool(hh._carried(a.cell, rec))
            rows.append(row)
    out: dict = {}
    for tc in (*NR_FAR, "both"):
        mine = [r for r in rows if tc == "both" or r["task_cell"] == tc]
        failed = [r for r in mine if r["carried"] and r["outcome"] != "correct"]
        out[tc] = {"episodes": len(mine), "carried": sum(r["carried"] for r in mine),
                   "failed_carried": len(failed),
                   "declined": sum(not r["chose_option"] for r in failed),
                   "disowns": sum(r["need_reply_disowns"] for r in failed),
                   "declined_or_disowns": sum(not r["chose_option"] or r["need_reply_disowns"]
                                              for r in failed),
                   "declined_or_disowns_ids": [r["episode_id"] for r in failed
                                               if not r["chose_option"]
                                               or r["need_reply_disowns"]]}
    return {"by_task_cell": out, "tally": hnr.tally(rows)}, []


def _round_bounds(k: int) -> tuple[int, int]:
    """Round `k`'s templates (0-based round, ``lo`` to ``hi - 1``)."""
    first = templates_of(PINNED).start
    return first + k * ROUND, first + (k + 1) * ROUND


def first_arm(arms: list[r12.Arm], times: list[dict], k: int) -> str | None:
    """Reading 8: the arm that started round `k` (0-based), read from the runs: the arm of the
    run that started first (``started_utc`` from `analysis.r12.run_times`, then the run id)
    among those holding a record of one of the round's templates. None when no such run has a
    start time. The registered order (`registered.r13_round_arms`) is given beside it."""
    lo, hi = _round_bounds(k)
    started = {x["run_id"]: x["started_utc"] for x in times}
    starts = sorted((started[run.run_id], run.run_id, a.name) for a in arms for run in a.runs
                    if started.get(run.run_id)
                    and any(lo <= hh.template_index(rec["template_id"]) < hi
                            for rec in run.records))
    return starts[0][2] if starts else None


def rounds(arms: list[r12.Arm], read: list[int], task_cells: tuple[str, ...],
           times: list[dict]) -> tuple[list[dict], list[str]]:
    """Reading 8's success per arm and round on the templates read: pooled over the task cells
    (task cell "all", n = the task cells times the templates read in the round), then per task
    cell as extra detail. Each row gives the arm that started the round, read from the runs'
    start times (`first_arm`, from `times`), beside the registered first arm, and a round
    started by another arm than the registered one is a warning."""
    rows, warnings = [], []
    for k in range(len(templates_of(PINNED)) // ROUND):
        lo, hi = _round_bounds(k)
        ts = [t for t in read if lo <= t < hi]
        played, planned = first_arm(arms, times, k), registered.r13_round_arms(k)[0]
        if played is not None and played != planned:
            warnings.append(f"round {k + 1} ({lo}-{hi - 1}) started with {played}, but the "
                            f"registered order has {planned} first (the runs' start times are "
                            "in reading 8)")
        for a in arms:
            per = {tc: [float(bool(a.resolved[r12._key(a.cell, t, tc)].record.get(
                "need_correct"))) for t in ts] for tc in task_cells}
            for tc, vals in (("all", [v for c in task_cells for v in per[c]]), *per.items()):
                rows.append({"round": k + 1, "templates": f"{lo}-{hi - 1}",
                             "templates_read": len(ts), "arm": a.name, "task_cell": tc,
                             "first_arm": played, "registered_first_arm": planned,
                             **r12._rate(vals)})
    return rows, warnings


# --- the transcripts: responses ----------------------------------------------------------------

def responses(a: r12.Arm, restricted: dict, task_cells: tuple[str, ...], stop: int, raw: Path,
              facts: dict[str, dict] | None = None
              ) -> tuple[dict | None, list[str], dict[str, dict] | None]:
    """Reading 7's transcript part for one of R13's own arms, from its restricted resolution,
    as `analysis.r12.responses` reads it, the runs with no transcript (the reading is then
    None), and each episode's summary responses (`summary_transcript`, for reading 5). Step
    responses are the records' requests less their summary requests, so that a Σ-n-0
    episode's summary calls, which the transcripts log as ``kind`` "summary", are read apart.
    Refusals come from the records' step responses that stopped short (``incomplete``).
    `facts` defaults to the generator's for the arm's templates and task cells. Transcript
    lines a recovered run declares missing are allowed for and named."""
    by_run = r12._by_run(restricted, a.cell, task_cells, stop)
    missing = sorted(run_id for run_id in by_run
                     if not r12._transcript(raw, a.experiment, run_id).is_file())
    if missing:
        return None, missing, None
    records = {e: rec for recs in by_run.values() for e, rec in recs.items()}
    if facts is None:
        ts = sorted(hh.template_index(rec["template_id"]) for rec in records.values())
        facts = r12._facts(ts[0], ts[-1] + 1, task_cells) if ts else {}
    t = hpe.merge([hpe.transcript_readings(r12._transcript(raw, a.experiment, run_id), recs,
                                           facts) for run_id, recs in sorted(by_run.items())])
    calls: dict[str, dict] = {}
    for run_id, recs in sorted(by_run.items()):
        calls.update(summary_transcript(r12._transcript(raw, a.experiment, run_id), recs))
    from_records = hpe.record_readings(list(records.values()))
    n_summary = sum(int(rec.get("n_summary_requests") or 0) for rec in records.values())
    steps = from_records["responses"] - n_summary
    in_summary = sum(x["calls"] for x in calls.values())
    gaps = r12.declared_missing(a, by_run)
    if (t["responses"] + in_summary != from_records["responses"] - len(gaps)
            or (not gaps and in_summary != n_summary)):
        raise hh.Refusal(f"{a.name}'s transcripts in {a.experiment} hold {t['responses']} step "
                         f"and {in_summary} summary responses, its records {steps} and "
                         f"{n_summary}" + (f", less {len(gaps)} line(s) a recovered run "
                                           "declares missing" if gaps else ""))
    s = hpe.arm_transcript_summary(t, records, task_cells)
    refused = from_records["refused_responses"]
    return ({"episodes": len(records), "runs": sorted(by_run),
             "step_responses": steps, "summary_responses": n_summary,
             "responses_not_in_transcript": gaps,
             "refused_responses": refused,
             "refused_share": refused / steps if steps else None,
             "refusal_categories": dict(sorted(from_records["refusal_categories"].items())),
             "step_responses_in_transcript": s["responses_in_transcript"],
             "with_thinking": s["with_thinking"], "thinking_share": s["thinking_share"],
             "with_redacted_thinking": t["redacted_thinking"],
             "summary_responses_in_transcript": in_summary,
             "summary_with_thinking": sum(x["thinking"] for x in calls.values()),
             "at_need": {tc: r12.retained(t["need_reply_chars"], records, tc)
                         for tc in task_cells}}, [], calls)


# --- the arms set beside an experiment ---------------------------------------------------------

def beside(arm: r12.Arm, read: list[int], task_cells: tuple[str, ...], stop: int,
           api: str) -> dict:
    """An arm set beside an experiment (reading 8 of experiment 4, 9 of experiment 5) on its
    templates read that the arm finished in every task cell: success, §2.8's accounting
    (P(carried) and success given carried), its sources apart (`carried`) and, for a summary
    cell, ``compacted_between``. Described only: no contrast."""
    common, left = side_read(arm, read, task_cells)
    restricted = r12.restrict(arm, common)
    table, _ = hh.episode_table(restricted, api=api)
    sub = table[(table.repeat == 0) & (table.status == "counted") & (table.cell == arm.cell)
                & (table.variant == hh.BASE) & table.task_cell.isin(task_cells)
                ].reset_index(drop=True)
    cells = hh.cell_table(sub, kinds=((arm.cell, hh.BASE),), task_cells=task_cells)
    acc = hh.accounting(sub, cells=(arm.cell,), task_cells=task_cells)
    out = {"arm": arm.name, "model": arm.model, "experiment": arm.experiment,
           "templates": r12._ranges(common), "n_templates": len(common), "left_out": left,
           "cells": [{k: c[k] for k in ("task_cell", "n", "successes", "rate")} for c in cells],
           "accounting": [{"task_cell": x["task_cell"], "S_verbatim_0": x["S_verbatim_0"],
                           "P_carried": x["P_carried"],
                           "used_given_carried": x["used_given_carried"]} for x in acc],
           "carried": {tc: carried(_records(restricted, arm.cell, stop, (tc,)), arm.cell)
                       for tc in task_cells}}
    if arm.cell in hh.SUMMARY_CELLS:
        out["compacted_between"] = {x["task_cell"]: x.get("by_compacted_between") for x in acc}
    return out


# --- the whole reading ----------------------------------------------------------------------

def readings(root: Path, links: dict[str, str], sweep_closed: set[str] | frozenset = frozenset(),
             *, raw_root: Path | None = None, allow_incomplete: bool = False,
             facts: dict[str, dict] | None = None,
             experiments: tuple[str, ...] | None = None,
             comparators_root: Path | None = None) -> dict:
    """R13's readings. `sweep_closed` holds the experiments the researcher closed.
    `experiments` limits the reading to those experiments (both when None). `facts` (for
    tests) replaces the generator's facts for reading 7. `comparators_root` (default `root`)
    holds the comparators' committed records and cited outputs."""
    unknown = set(sweep_closed) - set(EXPERIMENTS)
    if unknown:
        raise hh.Refusal(f"--sweep-closed names no R13 experiment: {', '.join(sorted(unknown))}")
    named = set(EXPERIMENTS if experiments is None else experiments)
    if not named or named - set(EXPERIMENTS):
        raise hh.Refusal("--experiment names no R13 experiment: "
                         + (", ".join(sorted(named - set(EXPERIMENTS))) or "none named"))
    chosen = tuple(e for e in EXPERIMENTS if e in named)  # in the registered order
    outside = set(sweep_closed) - named
    if outside:
        raise hh.Refusal("--sweep-closed names an experiment this reading leaves out: "
                         + ", ".join(sorted(outside)))
    raw = raw_root or root / "results" / "raw"
    comp = comparators_root or root
    runs = {e: discover(root, e) for e in chosen}
    if not any(runs.values()):
        raise hh.Refusal("no R13 run to read, so nothing is written:\n" + "\n".join(
            f"  - {LABEL[e]} ({e}): no run under results/{e}/" for e in chosen)
            + f"\nR13 ({registered.R13_REF}) has no run to read yet.")
    by_exp = split_links(links, runs)
    seed, _ = hh.read_seed(root / "results")
    boot_seed = seed + BOOT_SEED_OFFSET
    incomplete: list[str] = []
    warnings: list[str] = []
    state: dict[str, dict] = {}
    for e in chosen:
        s, templates = spec(e), templates_of(e)
        task_cells = tuple(s["task_cells"])
        if not runs[e]:
            incomplete.append(f"{LABEL[e]} ({e}): no run under results/{e}/")
            continue
        resolved, warn = hh.resolve(runs[e], by_exp[e], sweep_closed=e in sweep_closed,
                                    echo=False, stopped=hh.request_check_stops(runs[e]))
        warnings += [f"{LABEL[e]}: {w}" for w in warn]
        own = [r12.Arm(c, c, s["model"], e, resolved, [r for r in runs[e] if r.cell == c])
               for c in s["cells"]]
        arms = list(own)
        if e == SIGMA:
            arms += [*r8_arms(comp), r12_arm(comp, registered.R12_BLOCK_EXPERIMENT, "W-b-0")]
        read = r12.templates_read(arms, task_cells, templates)
        left, never = r12.left_out(arms, own, task_cells, templates, read)
        gaps, deviations = r12.sweep_gaps(resolved, tuple(s["cells"]), task_cells, templates,
                                          e in sweep_closed)
        incomplete += [f"{LABEL[e]}: {x}" for x in gaps]
        if not read:
            incomplete.append(f"{LABEL[e]} ({e}): no template finished in every task cell of "
                              "every arm")
        state[e] = {"runs": runs[e], "resolved": resolved, "own": own, "arms": arms,
                    "read": read, "left_out": left, "never": never,
                    "deviations": deviations, "task_cells": task_cells,
                    "templates": templates}
    if incomplete and not allow_incomplete:
        raise hh.Refusal("R13's sweeps are incomplete:\n" + "\n".join(
            f"  - {x}" for x in incomplete) + "\nWait for the runs (a transport failure needs "
            "its §13 re-run), pass --sweep-closed for an experiment once the researcher has "
            "closed its sweep, or pass --allow-incomplete to see what exists (PROVISIONAL).")
    checks = {}
    for e, st in state.items():
        check = hh.accounting_check(st["runs"], raw, e, hh.MESSAGES_API)
        if check["bugs"]:
            raise hh.AccountingBug(
                f"PREREG §2.8's bug stop in {e}: window-accounting bug(s), so no result is "
                "reported until they are found:\n" + "\n".join(f"  - {b}" for b in check["bugs"]))
        if check["missing_transcripts"]:
            incomplete.append(f"{LABEL[e]}: no raw transcript for run(s) "
                              + ", ".join(check["missing_transcripts"])
                              + f" under {raw}: §2.8's replay cannot be made")
        warnings += [f"{LABEL[e]}: {w}" for w in check["warnings"]]
        checks[e] = check
    out: dict[str, dict | None] = {}
    for e in chosen:
        st = state.get(e)
        if st is None or not st["read"]:
            out[e] = None if st is None else _unread(e, st, checks[e])
            continue
        out[e] = _experiment(e, st, checks[e], raw, boot_seed, facts, incomplete, warnings,
                             comp)
    if incomplete and not allow_incomplete:
        raise hh.Refusal("\n".join(incomplete) + "\nPass --raw-root, or --allow-incomplete "
                         "(PROVISIONAL).")
    return {"prereg": registered.R13_REF, "block": registered.R13_BLOCK,
            "status": hh.PROVISIONAL if incomplete else hh.FINAL,
            "experiments_in_reading": list(chosen),
            "incomplete": incomplete, "rerun_links": links,
            "sweep_closed": sorted(sweep_closed),
            "bootstrap": {"resamples": BOOT, "seed": boot_seed, "seed_offset": BOOT_SEED_OFFSET,
                          "interval": "90% percentile, template-cluster",
                          "experiment_4": "R8 to R12's resamples (T = 200), by template number",
                          "experiment_5": "over the templates read, mapped to 0..n-1"},
            "comparators": {"r8_output": hn.R8_OUTPUT, "r9_output": hp.R9_OUTPUT,
                            "r12_output": R12_OUTPUT, "luna_output": hh.LUNA_CITED_OUTPUT},
            "experiments": out,
            "does_not_show": list(DOES_NOT_SHOW),
            "warnings": [*warnings, *missing_values(out)]}


def _unread(e: str, st: dict, check: dict) -> dict:
    """An experiment with runs but no template read (PROVISIONAL only)."""
    return {"label": LABEL[e], "experiment": e, "model": spec(e)["model"],
            "templates_read": 0, "templates": "none", "left_out": st["left_out"],
            "templates_never_played": st["never"], "deviations": st["deviations"],
            "accounting_check": r12._check_out(check), "exclusions": _exclusions(e, st),
            "runs": [hh.run_row(r, st["resolved"]) for r in st["runs"]]}


def _exclusions(e: str, st: dict) -> list[dict]:
    """§13's counts per arm and task cell over the experiment's registered templates."""
    return hh.exclusion_table(st["resolved"], st["templates"].stop,
                              kinds=tuple((c, hh.BASE) for c in spec(e)["cells"]), echo=False,
                              task_cells=st["task_cells"], first=st["templates"].start)


def _experiment(e: str, st: dict, check: dict, raw: Path, boot_seed: int, facts: dict | None,
                incomplete: list[str], warnings: list[str], comp: Path) -> dict:
    """Every reading of one experiment."""
    read, task_cells, stop = st["read"], st["task_cells"], st["templates"].stop
    pos, size = positions(e, read)
    idx = hh.resample_indices(size, boot_seed, BOOT)
    restricted = {a.name: r12.restrict(a, read) for a in st["arms"]}
    arms_by_name = {a.name: a for a in st["arms"]}
    own = {a.name for a in st["own"]}
    arms, calls = [], {}
    for a in st["arms"]:
        reading, warn = arm_reading(a, restricted[a.name], task_cells, stop, pos, size, idx)
        warnings += [f"{LABEL[e]}, {a.name}: {w}" for w in warn]
        if a.name in own:
            reading["responses"], missing, calls[a.name] = responses(
                a, restricted[a.name], task_cells, stop, raw, facts)
            redacted = (reading["responses"] or {}).get("with_redacted_thinking")
            if redacted:
                warnings.append(f"{LABEL[e]}, {a.name}: {redacted} response(s) hold a "
                                "redacted_thinking block, counted among those with a "
                                "thinking block in reading 7")
            for run_id in missing:
                incomplete.append(f"{LABEL[e]}: no raw transcript for {run_id} under {raw} "
                                  f"({a.name}): reading 7 cannot be made")
        arms.append(reading)
    result = {"label": LABEL[e], "experiment": e, "model": spec(e)["model"],
              "cells": list(spec(e)["cells"]), "task_cells": list(task_cells),
              "templates_registered": f"{st['templates'].start}-{stop - 1}",
              "templates_read": len(read), "templates": r12._ranges(read),
              "left_out": st["left_out"], "templates_never_played": st["never"],
              "resamples_over": size, "deviations": st["deviations"],
              "accounting_check": r12._check_out(check), "exclusions": _exclusions(e, st),
              "runs": [hh.run_row(r, st["resolved"]) for r in st["runs"]],
              "arms": arms}
    if e == SIGMA:
        r9 = r9_arm(comp)
        r9_read, r9_left = side_read(r9, read, NR_FAR)
        r9_res = r12.restrict(r9, r9_read)
        result["contrasts"] = contrasts(e, arms_by_name, restricted, task_cells, pos, size,
                                        idx, r9=(r9, r9_res))
        result["r9_contrast"] = {"runs": sorted(r.run_id for r in r9.runs),
                                 "templates": r12._ranges(r9_read),
                                 "n_templates": len(r9_read), "left_out": r9_left}
        result["comparators"] = {
            "r8_runs": sorted({r.run_id for a in st["arms"] if a.name in (W0_R8, F0_R8)
                               for r in a.runs}),
            "r12_runs": sorted({r.run_id for a in st["arms"] if a.name == WB_R12
                                for r in a.runs})}
        sig = next(a for a in st["own"] if a.cell == SIGMA_CELL)
        recs = {tc: _records(restricted[sig.name], sig.cell, stop, (tc,)) for tc in task_cells}
        reading = next(x for x in arms if x["arm"] == sig.name)
        result["compaction"] = compaction(reading["accounting"], recs)
        result["summary_calls"] = summary_calls(
            {x["episode_id"]: x for rs in recs.values() for x in rs}, task_cells,
            calls.get(sig.name))
        result["beside_luna"] = beside(luna_arm(comp), read, task_cells, stop, hh.RESPONSES_API)
    else:
        result["contrasts"] = contrasts(e, arms_by_name, restricted, task_cells, pos, size, idx)
        for a in st["own"]:
            reading = next(x for x in arms if x["arm"] == a.name)
            if a.cell in hh.PINNED_CELLS:
                reading["block_at_need"] = block_at_need(
                    {tc: _records(restricted[a.name], a.cell, stop, (tc,)) for tc in task_cells})
            reading["declines"], missing = declines(a, restricted[a.name], stop, raw)
            for run_id in missing:
                incomplete.append(f"{LABEL[e]}: no raw transcript for {run_id} under {raw} "
                                  f"({a.name}): reading 5 cannot be made")
        times = r12.run_times(st["own"])
        success, warn = rounds(st["own"], read, task_cells, times)
        warnings += [f"{LABEL[e]}: {w}" for w in warn]
        result["rounds"] = {"success": success, "runs": times}
        result["beside_r12"] = [beside(r12_arm(comp, registered.R12_NOTES_EXPERIMENT, c), read,
                                       task_cells, stop, hh.MESSAGES_API)
                                for c in R12_NOTES_CELLS]
    return result


def missing_values(experiments: dict) -> list[str]:
    """A warning per arm and task cell whose costs have records with no value (their mean is
    then not given)."""
    out = []
    for e, x in experiments.items():
        for a in (x or {}).get("arms", []):
            for tc, c in a["costs"].items():
                for key, what in (("cost_missing", "billed cost"),
                                  ("output_tokens_missing", "output-token count"),
                                  ("input_tokens_missing", "input-token count"),
                                  ("cache_read_share_missing", "cache-read count")):
                    if c.get(key):
                        out.append(f"{LABEL[e]}, {a['arm']}, {tc}: {c[key]} of {c['n']} counted "
                                   f"records have no {what}, so its mean is not given")
    return out


# --- the summary ----------------------------------------------------------------------------

_pct, _iv, _share, _num = r12._pct, r12._iv, r12._share, r12._num


def _head_lines(x: dict) -> list[str]:
    lines = [f"## {x['label']}: {x['model']}, `{x['experiment']}`", ""]
    if "arms" not in x:
        return lines + [(f"Not read: no template finished in every task cell of every arm "
                         f"({len(x['runs'])} run(s))."), ""]
    lines += [(f"Main templates {x['templates']} in every arm ({x['templates_read']} of the "
               f"registered {x['templates_registered']}), resamples over "
               f"{x['resamples_over']} positions. §2.8's accounting check: "
               f"{x['accounting_check']['checked']} need steps replayed, "
               f"{len(x['accounting_check']['bugs'])} bugs."), ""]
    if x["left_out"] or x["templates_never_played"]:
        lines += [(f"**Left out of every arm:** {x['templates_never_played']} registered "
                   "template(s) never played"
                   + (", and the templates of these keys:" if x["left_out"] else ".")), ""]
        lines += [f"- template {r['template']}, {r['arm']}, {r['task_cell']}: {r['status']}: "
                  f"{r['reason']}" for r in x["left_out"]]
        lines += [""] if x["left_out"] else []
    lines += ["**1. Success:**", "",
              "| Arm | Task cell | Success | 90% interval | Refused episodes | Stopped responses |",
              "|---|---|---|---|---|---|"]
    for a in x["arms"]:
        for c in a["cells"]:
            lines.append(f"| {a['arm']} | {c['task_cell']} | {c['successes']}/{c['n']} "
                         f"({_pct(c['rate'])}) | {_iv(c.get('interval_90'))} | "
                         f"{c.get('episodes_with_a_refusal', 0)} | "
                         f"{c.get('stopped_responses') or '-'} |")
    lines += ["", ("**2. Contrasts** (percentage points, 90% interval over the same template "
                   "resamples, described, not tested):"), ""]
    lines += [NOTE_NOT_CONCURRENT if x["experiment"] == SIGMA else NOTE_LABEL, ""]
    for name, by_tc in x["contrasts"].items():
        for tc, v in by_tc.items():
            lines.append(f"- {name}, {tc}: {hp._pp(v)}")
    if x["experiment"] == SIGMA:
        rc = x["r9_contrast"]
        lines += ["", (f"R9's W-n-0 in its contrast: templates {rc['templates']} "
                       f"({rc['n_templates']}), the templates read that it finished in both "
                       "not-recoverable far cells.")]
        lines += [f"- left out: template {r['template']}, {r['task_cell']}: {r['status']}: "
                  f"{r['reason']}" for r in rc["left_out"]]
    return lines + [""]


def _carried_lines(x: dict, title: str) -> list[str]:
    first = "bridge" if x["experiment"] == SIGMA else "pinned block"
    lines = [title, "", NOTE_LOWER_BOUND + (" Each cell gives P(carried), then the success "
                                            "given carried."), "",
             (f"| Arm | Task cell | S verbatim 0 | In the {first} | In the retained replies | "
              "In either |"), "|---|---|---|---|---|---|"]
    for a in x["arms"]:
        for tc, c in (a.get("carried") or {}).items():
            def cell(s: str, c: dict = c) -> str:
                if s not in c:
                    return "-"
                return (f"{hp._frac(c[s]['carried'], c['S_verbatim_0'])}, "
                        f"{hp._frac_rate(c[s]['success_given_carried'])}")
            lines.append(f"| {a['arm']} | {tc} | {c['S_verbatim_0']} | "
                         f"{cell('bridge' if x['experiment'] == SIGMA else 'pinned')} | "
                         f"{cell('retained')} | {cell('either')} |")
    return lines + [""]


def _choices_lines(x: dict, n: int) -> list[str]:
    lines = [f"**{n}. Choices with the fact evicted** (not-recoverable far cells):", ""]
    for a in x["arms"]:
        for tc, c in (a["choices_nr_far"] or {}).items():
            lines.append(f"- {a['arm']}, {tc}: chose an option in {c['chose_an_option']} of "
                         f"{c['episodes']}, {c['correct']} correct.")
    return lines + [""]


def _responses_lines(x: dict, n: int) -> list[str]:
    lines = [f"**{n}. Responses:**", "", r12.NOTE_THINKING, "",
             ("| Arm | Refused step responses | Categories | Step responses with a thinking "
              "block | Summary responses with one |"), "|---|---|---|---|---|"]
    for a in x["arms"]:
        if "responses" not in a:
            continue
        s = a["responses"]
        if s is None:
            lines.append(f"| {a['arm']} | (no transcripts) | | | |")
            continue
        lines.append(f"| {a['arm']} | {_share(s['refused_responses'], s['step_responses'])} | "
                     f"{s['refusal_categories'] or '-'} | "
                     f"{_share(s['with_thinking'], s['step_responses_in_transcript'])}"
                     + (f", {s['with_redacted_thinking']} redacted"
                        if s.get("with_redacted_thinking") else "") + " | "
                     + (_share(s['summary_with_thinking'], s['summary_responses_in_transcript'])
                        if s["summary_responses_in_transcript"] else "-") + " |")
    if x["experiment"] == PINNED:
        lines += ["", ("The retained replies at the need step's first request: one reply's "
                       "length, the median over the replies pooled in the task cell."), "",
                  ("| Arm | Task cell | Retained replies (median per episode) | One retained "
                   "reply's length (median characters) |"), "|---|---|---|---|"]
        for a in x["arms"]:
            for tc in x["task_cells"]:
                k = (a.get("responses") or {}).get("at_need", {}).get(tc)
                lines.append(f"| {a['arm']} | {tc} | "
                             f"{'n/a' if k is None else k['retained_replies_median']} | "
                             f"{'n/a' if k is None else _num(k['reply_chars_median'], '.0f')} |")
    lines += ["", ("| Arm | Task cell | Episodes | Output tokens | Cost (USD) | Input tokens | "
                   "Cache-read share of input |"), "|---|---|---|---|---|---|---|"]
    for a in x["arms"]:
        for tc, c in a["costs"].items():
            lines.append(f"| {a['arm']} | {tc} | {c['n']} | "
                         f"{_num(c['output_tokens_mean'], '.0f')} | "
                         f"{_num(c['cost_usd_billed_mean'], '.5f')} | "
                         f"{_num(c['input_tokens_mean'], ',.0f')} | "
                         f"{_pct(c['cache_read_share'])} |")
    for a in x["arms"]:
        for g in (a.get("responses") or {}).get("responses_not_in_transcript") or []:
            lines += ["", (f"{a['arm']}: request {g['request_index']} of {g['episode_id']} in "
                           f"run {g['run_id']} is not in its transcript. The episode's record, "
                           "usage and cost are counted.")]
    return lines + [""]


def _beside_lines(b: dict) -> list[str]:
    lines = [f"{b['arm']} ({b['model']}): templates {b['templates']} ({b['n_templates']}).", ""]
    lines += [f"- left out: template {r['template']}, {r['task_cell']}: {r['status']}: "
              f"{r['reason']}" for r in b["left_out"]]
    lines += [""] if b["left_out"] else []
    lines += ["| Task cell | Success | P(carried), either | Success given carried |",
              "|---|---|---|---|"]
    acc = {x["task_cell"]: x for x in b["accounting"]}
    for c in b["cells"]:
        a = acc[c["task_cell"]]
        pc = a["P_carried"] or {}
        lines.append(f"| {c['task_cell']} | {c['successes']}/{c['n']} ({_pct(c['rate'])}) | "
                     f"{hp._frac(pc.get('carried'), pc.get('n'))} | "
                     f"{hp._frac_rate(a['used_given_carried'])} |")
    return lines + [""]


def _sigma_lines(x: dict) -> list[str]:
    lines = _head_lines(x)
    if "arms" not in x:
        return lines
    lines += _carried_lines(x, "**3. §2.8 accounting in the bridge** (Σ-n-0):")
    lines += ["**4. Compaction and near cells:**", "",
              ("| Task cell | Episodes | Compactions per episode | compacted_between: n, S = 1, "
               "success |"), "|---|---|---|---|"]
    for tc, c in x["compaction"].items():
        groups = "; ".join(f"{k}: {v['n']}, {v['S_1']}, {v['success']['successes']}"
                           for k, v in (c["compacted_between"] or {}).items())
        lines.append(f"| {tc} | {c['episodes']} | {_num(c['compactions_per_episode'], '.2f')} | "
                     f"{groups or '-'} |")
    lines += ["", ("Near-cell episodes whose evidence was not in the need step's request "
                   "(need_payload.S false), and their success:"), ""]
    for a in x["arms"]:
        lines.append(f"- {a['arm']}: " + ", ".join(
            f"{tc} {v['S_false']} of {v['n']} ({hp._frac_rate(v['success_given_S_false'])})"
            for tc, v in a["near_need_payload_S_false"].items()) + ".")
    lines += ["", "**5. Summary calls** (Σ-n-0):", "",
              ("| Task cell | Summary requests per episode | Failed attempts per episode | "
               "Stopped summary responses | AGENT_ERROR episodes | Bridge tokens (median) | At "
               "the need step (median) | Summary output tokens (median per call, mean per "
               "episode) |"), "|---|---|---|---|---|---|---|---|"]
    for tc, c in x["summary_calls"].items():
        lines.append(f"| {tc} | {_num(c['summary_requests_per_episode'], '.2f')} | "
                     f"{_num(c['failed_attempts_per_episode'], '.3f')} | "
                     f"{'n/a' if c['summary_stopped'] is None else c['summary_stopped'] or '-'} | "
                     f"{len(c['agent_error_episodes'])} | "
                     f"{_num(c['bridge_tokens_median'], '.0f')} | "
                     f"{_num(c['need_bridge_tokens_median'], '.0f')} | "
                     f"{_num(c['summary_output_tokens_median_per_call'], '.0f')}, "
                     f"{_num(c['summary_output_tokens_mean_per_episode'], '.0f')} |")
    lines += [""]
    lines += _choices_lines(x, 6)
    lines += _responses_lines(x, 7)
    b = x["beside_luna"]
    lines += ["**8. Beside luna's Σ-n-0** (described only, no contrast between the models):", "",
              NOTE_LUNA, ""]
    lines += _beside_lines(b)
    lines += ["| Task cell | P(carried) in the bridge | compacted_between: n, S = 1, success |",
              "|---|---|---|"]
    for tc, c in b["carried"].items():
        groups = "; ".join(f"{k}: {v['n']}, {v['S_1']}, {v['success']['successes']}"
                           for k, v in (b["compacted_between"].get(tc) or {}).items())
        lines.append(f"| {tc} | {hp._frac(c['bridge']['carried'], c['S_verbatim_0'])} | "
                     f"{groups or '-'} |")
    return lines + [""] + _tail_lines(x)


def _pinned_lines(x: dict) -> list[str]:
    lines = _head_lines(x)
    if "arms" not in x:
        return lines
    lines += _carried_lines(x, "**3. §2.8 accounting** (each source apart, and either):")
    lines += ["**4. The block at the need step** (W-nk-0's first request there):", "",
              ("| Task cell | Reached the need step | With the block | Block tokens (median) | "
               "Replies in it (median) | Newest reply alone over the cap | Replies left out "
               "(episodes) |"), "|---|---|---|---|---|---|---|"]
    for a in x["arms"]:
        for tc, c in (a.get("block_at_need") or {}).items():
            lines.append(f"| {tc} | {c['reached_need']} | {c['with_block']} | "
                         f"{_num(c['block_tokens_median'], '.0f')} | "
                         f"{_num(c['block_replies_median'], '.1f')} | "
                         f"{c['newest_reply_over_cap']} | {c['replies_left_out']} "
                         f"({c['episodes_with_replies_left_out']}) |")
    lines += ["", "**5. Declines** (failed episodes whose carried notes held the fact):", "",
              NOTE_PATTERN, "",
              ("| Arm | Task cell | Carried | Failed, carried | Declined | Disowns its figure | "
               "Either |"), "|---|---|---|---|---|---|---|"]
    for a in x["arms"]:
        d = a.get("declines")
        if d is None:
            lines.append(f"| {a['arm']} | (no transcripts) | | | | | |")
            continue
        for tc, c in d["by_task_cell"].items():
            lines.append(f"| {a['arm']} | {tc} | {c['carried']} of {c['episodes']} | "
                         f"{c['failed_carried']} | {c['declined']} | {c['disowns']} | "
                         f"{c['declined_or_disowns']} |")
    lines += [""]
    lines += _choices_lines(x, 6)
    lines += _responses_lines(x, 7)
    lines += ["**8. Rounds** (described only):", "",
              ("Task cell \"all\" pools the task cells: success per arm and round. The rows per "
               "task cell are extra detail."), "",
              ("\"First arm\" is the arm whose run started the round, read from the runs' start "
               "times below. \"Registered\" is the order §17.13 registers."), "",
              ("| Round | Templates | Read | First arm | Registered first arm | Arm | Task cell | "
               "Success |"), "|---|---|---|---|---|---|---|---|"]
    for r in x["rounds"]["success"]:
        lines.append(f"| {r['round']} | {r['templates']} | {r['templates_read']} | "
                     f"{r['first_arm'] or '-'} | {r['registered_first_arm']} | {r['arm']} | "
                     f"{r['task_cell']} | {r['successes']}/{r['n']} ({_pct(r['rate'])}) |")
    lines += ["", "| Run | Arm | Templates | Ending | Started (UTC) | Finished (UTC) |",
              "|---|---|---|---|---|---|"]
    for r in x["rounds"]["runs"]:
        lines.append(f"| {r['run_id']} | {r['arm']} | {r['templates']} | {r['exit_reason']} | "
                     f"{r['started_utc']} | {r['finished_utc']} |")
    lines += ["", "**9. Beside R12 experiment 1's arms** (described only):", "", NOTE_R12, ""]
    for b in x["beside_r12"]:
        lines += _beside_lines(b)
    return lines + _tail_lines(x)


def _tail_lines(x: dict) -> list[str]:
    lines = ["**Exclusions** (per arm and task cell, repeat 0, §13):", ""]
    for r in x.get("exclusions", []):
        rest = {k: v for k, v in r.items() if k not in ("kind", "cell", "variant", "task_cell")
                and v not in (0, None, {}, [])}
        lines.append(f"- {r['cell']}, {r['task_cell']}: {rest or 'none'}")
    lines += [f"- deviation: {d}" for d in x["deviations"]]
    return lines + [""]


def summary(r: dict) -> str:
    lines = ["# R13: Σ-n-0 on Haiku, and W-nk-0 beside a concurrent W-n-0", "",
             (f"**{r['status']}.** {r['prereg']}. Exploratory: no test, no label. Repeat 0, base "
              "episodes. Not a model comparison, and nothing is ranked. Intervals: "
              f"{r['bootstrap']['resamples']:,} template resamples, seed SEED + "
              f"{r['bootstrap']['seed_offset']}."), "",
             "## What it does not show", "",
             *(f"- {x}" for x in r["does_not_show"]), ""]
    for e in EXPERIMENTS:
        if e not in r["experiments"]:
            lines += [f"## {LABEL[e]}: `{e}`", "",
                      "Not part of this reading (`--experiment` leaves it out).", ""]
            continue
        x = r["experiments"][e]
        if x is None:
            lines += [f"## {LABEL[e]}: `{e}`", "", "Not read: no run.", ""]
            continue
        lines += _sigma_lines(x) if e == SIGMA else _pinned_lines(x)
    lines += [f"- incomplete: {x}" for x in r["incomplete"]]
    lines += [f"- warning: {w}" for w in r["warnings"]]
    return "\n".join(lines) + "\n"


# --- main -----------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results-root", type=Path, default=REPO_ROOT)
    ap.add_argument("--comparators-root", type=Path, default=None,
                    help="the results root of the comparators' records (default: --results-root)")
    ap.add_argument("--rerun", action="append", default=[], metavar="RUN=ORIGINAL")
    ap.add_argument("--sweep-closed", action="append", default=[], choices=sorted(SHORT),
                    help="an experiment whose sweep the researcher closed (repeatable)")
    ap.add_argument("--experiment", action="append", default=[], choices=sorted(SHORT),
                    help="read only this experiment (repeatable; default: both)")
    ap.add_argument("--allow-incomplete", action="store_true")
    ap.add_argument("--raw-root", type=Path, default=None)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--out-dir", type=Path, default=None)
    a = ap.parse_args(argv)
    now = datetime.now(UTC)
    closed = {SHORT[x] for x in a.sweep_closed}
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        r = readings(a.results_root, hn._links(a.rerun), closed, raw_root=a.raw_root,
                     allow_incomplete=a.allow_incomplete,
                     experiments=tuple(SHORT[x] for x in a.experiment) or None,
                     comparators_root=a.comparators_root)
    except hh.AccountingBug as e:
        print(f"refused (§2.8's bug stop): {e}", file=sys.stderr)
        return 2
    except hh.Refusal as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    text = summary(r)
    print(text)
    if a.no_write:
        return 0
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    out = a.out_dir or a.results_root / "results" / OUT_NAME / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "readings.json").write_text(
        json.dumps(hh._clean(r), indent=2, ensure_ascii=False, default=hh._json_default) + "\n",
        encoding="utf-8", newline="\n")
    (out / "summary.md").write_text(text, encoding="utf-8", newline="\n")
    runs = [x["run_id"] for e in r["experiments"].values() if e for x in e["runs"]]
    runmeta.write_meta(
        out, git=runmeta.git_state(), experiment=OUT_NAME, run_id=run_id,
        cell_or_config=",".join(r["experiments_in_reading"]),
        config={"experiments": r["experiments_in_reading"], "rerun_links": r["rerun_links"],
                "sweep_closed": r["sweep_closed"], "allow_incomplete": a.allow_incomplete,
                "status": r["status"],
                "inputs": {"results_root": hh._rel(a.results_root),
                           "comparators_root": hh._rel(a.comparators_root or a.results_root),
                           "raw_root": hh._rel(a.raw_root or a.results_root / "results" / "raw"),
                           "runs": {e: [x["run_id"] for x in (v or {}).get("runs", [])]
                                    for e, v in r["experiments"].items()},
                           "comparators": r["comparators"]},
                "templates": {e: (x or {}).get("templates") for e, x in r["experiments"].items()}},
        model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
        repeat_index=0, seeds={"bootstrap": r["bootstrap"]["seed"]},
        started_utc=now.isoformat(timespec="seconds"), finished_utc=runmeta.utc_now(),
        exit_reason="completed", tokens=None, cost_usd=0.0, raw_transcript_path=None,
        outputs=list(OUTPUTS), paid_calls=0, runs=runs)
    print(f"written: {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
