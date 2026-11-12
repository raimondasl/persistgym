"""R12's descriptive analysis: Haiku's notes sentences on new templates, claude-sonnet-5-5, and a block-truncation window (PREREG §17.12; $0, no test).

R12 registers three experiments, each in its own folder, played under block `8-r12`:

1. `persistgym_haiku_r12_notes`: claude-haiku-5-5 ("Haiku") in W-n-0, W-np-0, W-nd-0 and
   W-nx-0 on the 2 not-recoverable far task cells, main templates 200-299, in 4 rounds of 25
   templates with the arms' order rotated.
2. `persistgym_sonnet_r12`: claude-sonnet-5-5 ("Sonnet") in W-n-0, W-np-0 and F-0 on the same
   2 cells, main templates 200-224.
3. `persistgym_haiku_r12_block`: Haiku in W-b-0 (block truncation) on all 8 task cells, main
   templates 0-199, R8's episodes. Its comparators are R8's W-0 and F-0 of 2026-10-18, as R8's
   cited output counted them (`analysis.haiku_notes.R8_OUTPUT`). They are this experiment's
   arms beside W-b-0 in every reading.

This script implements §17.12's "Analysis (descriptive only)" as written. Nothing here is a
test. It ranks nothing, and differences are described, not tested.

**Exclusions and errors,** R8's (§17.8) as R9 to R11 apply them. Each experiment's records are
read through `persistgym_h1h3.discover` and `resolve`: DESIGN §7.8's first-final-record rule
with the re-run links of ``--rerun``, §13's exclusions on the Messages API (no echo exclusion),
the episodes a request-side check stopped excluded (`request_check_stops`). Refusals and empty
replies score 0 at the need step, as the runner records them. Before any reading:
- Every record must be on its experiment's registered cells, task cells and templates, base
  episodes at repeat 0, and every run folder under an experiment must be one of its runs, on
  one of its registered cells (a single-turn run too).
- An API error awaiting its §13 re-run refuses, whether or not the sweep is closed.
- Each experiment's sweep must be complete over its registered templates
  (`persistgym_h1h3.completeness`), or closed by the researcher with ``--sweep-closed`` for that
  experiment. R12 registers no stop that closes a sweep: a run that ends early is continued
  under DESIGN §7.9, and a block that runs out goes to the researcher. Otherwise the script
  refuses, unless ``--allow-incomplete`` is passed, and the output is then PROVISIONAL. An
  experiment with no run, or with no template finished in every arm, is then reported as not
  read.
- §2.8's accounting check (`persistgym_h1h3.accounting_check`) on each experiment's raw
  transcripts under ``--raw-root`` (default ``results/raw``), with the block rule replayed for
  W-b-0 (`persistgym.survival.block_keep_starts`). A bug stops the analysis (`AccountingBug`),
  even as PROVISIONAL. Missing transcripts refuse, or make the output PROVISIONAL with
  ``--allow-incomplete``. R8's comparators passed R8's own check and are not replayed again.

**A reading of some experiments.** ``--experiment`` (repeatable: notes, sonnet, block) limits a
reading to the experiments it names, for instance experiments 1 and 2 while experiment 3 has
not run. The others are neither read nor required, the status covers only the experiments
named, and the output lists them (`experiments_in_reading`). Without it, all three are read.

**The templates read.** Within each experiment, every arm is read on the templates that it and
every other arm finished in every task cell (`templates_read`), and each key that leaves a
template out is named, with its status and reason (`left_out`).

**Intervals.** 90% template-cluster bootstrap percentiles with 10,000 resamples, seed SEED + 10
(SEED from the committed draw), the same resamples for every arm of an experiment. In
experiments 1 and 2 the resamples are over the templates read, mapped to 0..n-1 in ascending
order. Experiment 3 uses the resamples of R8 to R11 (T = 200), indexed by template number, with
the templates not read left out of each mean (NaN).

**The readings** (§17.12, numbered as there):
1. Success per arm and task cell, with its interval, and each cell's step responses that stopped
   short, by reason.
2. §2.8's accounting per arm and task cell (`persistgym_h1h3.accounting`): S verbatim, P(carried)
   (a string match, so a lower bound) and success given carried. The summary prints them for the
   not-recoverable far cells.
3. Choices with the fact evicted: per window arm and not-recoverable far cell, the episodes that
   chose one of the 10 options at the need step, and how many were correct.
4. Contrasts in percentage points on the same templates and resamples. Experiment 1: W-np-0,
   W-nd-0 and W-nx-0 each minus W-n-0, W-np-0 minus W-nx-0, and W-np-0 minus W-nd-0.
   Experiment 2: W-np-0 minus W-n-0, and F-0 minus W-n-0. Experiment 3, per task cell: W-b-0
   minus R8's W-0, and minus R8's F-0.
5. Responses per arm, from the raw transcripts (`analysis.haiku_provenance_extras`'s code):
   refusals by category, responses with a thinking block (presence only, a ``redacted_thinking``
   block counting as one, and also counted apart with a warning), the retained replies at the
   need step's first request, and output tokens and cost per episode (billed estimate) from the
   records. For the retained replies, §17.12's "median length" is one reply's length: the
   median over the replies pooled per arm and task cell (`retained`). Beside it, how many an
   episode retains (median over episodes), and as extra detail each episode's total characters
   (median over episodes), the figure R10 and R11 gave.
6. Experiment 1's rounds: success per arm and round (200-224, 225-249, 250-274, 275-299) on the
   templates read, pooled over the 2 task cells (task cell "all"), then per task cell as extra
   detail, and each run's start and finish (UTC). Described only.
7. Experiment 2 beside Haiku: Sonnet's arms and Haiku's experiment-1 arms on the templates of
   200-224 that both experiments read, success, P(carried) and success given carried. Described
   only. No contrast between the models is computed or tested.
8. Experiment 3's cost and context, per arm (W-b-0, R8's W-0 and F-0) and task cell, and over
   all 8: cost per episode, input tokens per episode (cache reads and writes included), and the
   cache-read share of input (the arm's cache-read tokens over its input tokens). Also W-b-0's
   block drops per episode (step requests whose info says ``block_drop``, from its
   transcripts), and the near-cell episodes whose evidence was not in the need step's request
   (``need_payload.S`` false).

The summary and readings.json also state §17.12's "What it does not show" (`DOES_NOT_SHOW`),
and the summary repeats its caveats next to readings 4 (experiment 1), 5, 7 and 8.

Run: ``uv run python -m analysis.r12 [--rerun RUN=ORIGINAL ...] [--sweep-closed notes|sonnet|block
...]``. It writes ``results/r12/<UTC>/readings.json``, ``summary.md`` and ``meta.json``. With
``--no-write`` it only prints.
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import numpy as np

from analysis import haiku_control as hc
from analysis import haiku_notes as hn
from analysis import haiku_provenance as hp
from analysis import haiku_provenance_extras as hpe
from analysis import persistgym_h1h3 as hh
from common import runmeta
from harnesses import registered
from persistgym.episode import TaskCell

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_NAME = "r12"
OUTPUTS = ("readings.json", "summary.md", "meta.json")
NOTES = registered.R12_NOTES_EXPERIMENT
SONNET = registered.R12_SONNET_EXPERIMENT
BLOCK = registered.R12_BLOCK_EXPERIMENT
EXPERIMENTS = registered.R12_EXPERIMENTS
SHORT = {"notes": NOTES, "sonnet": SONNET, "block": BLOCK}
"""``--sweep-closed`` names an experiment by these short names."""
LABEL = {NOTES: "Experiment 1", SONNET: "Experiment 2", BLOCK: "Experiment 3"}
BOOT = hn.BOOT
ROUND = 25
"""Experiment 1 plays rounds of 25 templates (§17.12, What it changes, 3)."""
R8_EXPERIMENT = registered.HAIKU_EXPERIMENT
R8_ARMS = ("W-0", "F-0")
"""Experiment 3's comparators, R8's runs of 2026-10-18."""
NR_FAR = hn.NR_FAR
CONTRASTS = {
    NOTES: (("W-np-0", "W-n-0"), ("W-nd-0", "W-n-0"), ("W-nx-0", "W-n-0"),
            ("W-np-0", "W-nx-0"), ("W-np-0", "W-nd-0")),
    SONNET: (("W-np-0", "W-n-0"), ("F-0", "W-n-0")),
    BLOCK: (("W-b-0", "W-0 (R8)"), ("W-b-0", "F-0 (R8)")),
}
"""Reading 4: (minuend arm, subtrahend arm) per experiment, in §17.12's order."""
DOES_NOT_SHOW = (
    ("Everything R8 to R11 say they do not show also holds here: one model per provider in the "
     "confirmatory sense, the same synthetic task family, thinking text not inspected."),
    ("No model comparison. Experiment 2 is one run per arm on 25 templates of one larger model "
     "of the same provider, at effort medium, whose levels on Sonnet 5.5 are recalibrated and "
     "not matched to Haiku's medium ([effort](https://platform.claude.com/docs/en/build-with-"
     "claude/effort), checked 2026-11-11). Setting its arms beside Haiku's describes how each "
     "behaved on these episodes. It does not rank them."),
    ("The sentences. Three wordings beside R10's two, one run each. Other wordings, other models "
     "and other tasks are not run. The neutral sentence is a length-matched control, not a "
     "no-effect control: it points attention at the action's format and may change replies by "
     "itself."),
    ("Experiment 3 is not concurrent with R8's W-0 and F-0, its comparators, which ran on "
     "2026-10-18. Cost comes mostly from caching mechanics, but success differences against "
     "them mix the rule with any change in serving since. One block size (W // 2) is run, on "
     "Haiku's short replies, without notes."),
    ("Coarse intervals. Experiment 2 bootstraps over at most 25 templates. Experiment 1's arms "
     "play each template once."),
)
"""§17.12's "What it does not show", as the summary and readings.json state it."""
NOTE_NEUTRAL = ("W-nx-0 is a length-matched control, not a no-effect control (see What it does "
                "not show).")
NOTE_THINKING = ("Thinking blocks by their presence only, so the thinking text is not inspected. "
                 "A redacted_thinking block counts as one.")
NOTE_EFFORT = ("Sonnet runs at effort medium, whose levels on Sonnet 5.5 are recalibrated, so it "
               "is not matched to Haiku's medium.")
NOTE_BLOCK = "W-b-0 runs one block size, W // 2, on Haiku's short replies, without notes."
"""The caveats the summary repeats next to readings 4 (experiment 1), 5, 7 and 8."""


def r8_name(cell: str) -> str:
    return f"{cell} (R8)"


@dataclass
class Arm:
    """One arm of an experiment: a harness cell's counted episodes."""
    name: str            # the arm's label: the cell, or "W-0 (R8)" for a comparator
    cell: str
    model: str
    experiment: str      # the folder that holds its runs, and their transcripts under raw
    resolved: dict       # every key's resolution in that folder
    runs: list           # its runs (`persistgym_h1h3.Run`)


# --- reading the experiments ---------------------------------------------------------------

def spec(experiment: str) -> dict:
    return registered.R12_SPECS[experiment]


def templates_of(experiment: str) -> range:
    first, stop = spec(experiment)["templates"]
    return range(first, stop)


def profile(experiment: str) -> hh.Profile:
    """What `persistgym_h1h3.discover` reads for one R12 experiment: R8's settings (the default
    generator config, the Messages API) with the experiment's model and cells."""
    s = spec(experiment)
    return replace(hh.profile(registered.HAIKU_MODEL), model=s["model"], name=experiment,
                   experiment=experiment, registered_experiment=experiment,
                   cells=tuple(s["cells"]), registered_cells=tuple(s["cells"]),
                   replication=False)


def discover(root: Path, experiment: str) -> list:
    """The experiment's runs (none if its folder does not exist). A folder that is not one of
    its runs, a run off its registered cells, or a record off its registered task cells,
    templates, variant or repeat, refuses. `persistgym_h1h3.discover` admits a single-turn run
    beside any profile's cells, so the cells are checked here too."""
    if not (root / "results" / experiment).is_dir():
        return []
    runs, skipped = hh.discover(root / "results", prof=profile(experiment))
    if skipped:
        raise hh.Refusal(f"run folders under results/{experiment}/ that are not R12's runs of "
                         "it: " + "; ".join(f"{x['folder']}: {x['reason']}" for x in skipped))
    s, registered_templates = spec(experiment), templates_of(experiment)
    off_cells = [f"{run.run_id}: cell {run.cell!r} is not one of R12's {experiment} cells "
                 f"({', '.join(s['cells'])})" for run in runs if run.cell not in s["cells"]]
    if off_cells:
        raise hh.Refusal("\n".join(off_cells))
    records = [rec for run in runs for rec in run.records]
    off = sorted({rec["task_cell"] for rec in records} - set(s["task_cells"]))
    if off:
        raise hh.Refusal(f"R12's {experiment} plays {', '.join(s['task_cells'])} only, but "
                         f"records hold {', '.join(off)}")
    outside = sorted({hh.template_index(rec["template_id"]) for rec in records}
                     - set(registered_templates))
    if outside:
        raise hh.Refusal(f"R12's {experiment} plays main templates {registered_templates.start}-"
                         f"{registered_templates.stop - 1} only, but records hold template(s) "
                         + ", ".join(str(t) for t in outside[:5]))
    odd = sorted({str(rec.get("episode_id")) for rec in records
                  if (rec.get("variant") or hh.BASE) != hh.BASE
                  or rec.get("repeat_index", 0) != 0})
    if odd:
        raise hh.Refusal(f"R12's {experiment} plays base episodes at repeat 0 only, but records "
                         f"hold {', '.join(odd[:5])}")
    return runs


def split_links(links: dict[str, str], runs: dict[str, list]) -> dict[str, dict[str, str]]:
    """``--rerun`` links by the experiment that holds the re-run or continuation."""
    where = {r.run_id: e for e, rs in runs.items() for r in rs}
    out: dict[str, dict[str, str]] = {e: {} for e in runs}
    for run, orig in links.items():
        if run not in where:
            raise hh.Refusal(f"--rerun {run}={orig}: {run} is not a run of R12's experiments")
        out[where[run]][run] = orig
    return out


def _key(cell: str, t: int, task_cell: str) -> tuple[str, str, int]:
    return (cell, hh.episode_id_of(cell, hh.BASE, t, task_cell), 0)


def _counted(resolved: dict, cell: str, t: int, task_cell: str) -> bool:
    r = resolved.get(_key(cell, t, task_cell))
    return r is not None and r.status == "counted" and r.record is not None


def templates_read(arms: list[Arm], task_cells: tuple[str, ...], templates: range) -> list[int]:
    """The templates every arm finished in every task cell: every arm is read on these."""
    return [t for t in templates
            if all(_counted(a.resolved, a.cell, t, tc) for a in arms for tc in task_cells)]


def left_out(arms: list[Arm], own: list[Arm], task_cells: tuple[str, ...], templates: range,
             read: list[int]) -> tuple[list[dict], int]:
    """The keys that keep a template out of the reading, up to the last template any of the
    experiment's own arms played, each with its arm, status and reason, and how many registered
    templates after that were never played."""
    played = [t for t in templates
              if any(_key(a.cell, t, tc) in a.resolved for a in own for tc in task_cells)]
    last = played[-1] if played else templates.start - 1
    rows = []
    for t in sorted(set(range(templates.start, last + 1)) - set(read)):
        for a in arms:
            for tc in task_cells:
                key = _key(a.cell, t, tc)
                r = a.resolved.get(key)
                if r is None:
                    rows.append({"template": t, "arm": a.name, "task_cell": tc,
                                 "episode_id": key[1], "status": "no record",
                                 "reason": "no run of the arm holds it"})
                elif r.status != "counted" or r.record is None:
                    rows.append({"template": t, "arm": a.name, "task_cell": tc,
                                 "episode_id": key[1], "status": r.status, "reason": r.reason})
    return rows, templates.stop - last - 1


def sweep_gaps(resolved: dict, cells: tuple[str, ...], task_cells: tuple[str, ...],
               templates: range, sweep_closed: bool) -> tuple[list[str], list[str]]:
    """Why an experiment's sweep cannot be read as final (empty when it can), and its
    deviations. An API error awaiting its §13 re-run counts whether or not the sweep is closed.
    R12 registers no stop that closes a sweep, so a short one needs the researcher's close."""
    waiting = sorted(f"{key[0]} {key[1]}" for key, r in resolved.items() if r.awaiting_rerun)
    out = ([f"{len(waiting)} episode(s) await their §13 re-run: " + ", ".join(waiting[:5])]
           if waiting else [])
    reasons, deviations = hh.completeness(resolved, templates.stop, sweep_closed,
                                          tuple((c, hh.BASE) for c in cells),
                                          task_cells=task_cells, first=templates.start)
    return [*out, *reasons], deviations


# --- readings 1 to 5 and 8, per arm ----------------------------------------------------------

def positions(experiment: str, read: list[int]) -> tuple[dict[int, int], int]:
    """Where each template read sits in the bootstrap's arrays, and their length. Experiments 1
    and 2: the templates read, mapped to 0..n-1. Experiment 3: R8 to R11's (T = 200), by
    template number."""
    if experiment == BLOCK:
        return {t: t for t in read}, registered.HAIKU_T
    return {t: i for i, t in enumerate(sorted(read))}, len(read)


def by_template(resolved: dict, cell: str, task_cell: str, pos: dict[int, int],
                size: int) -> np.ndarray:
    """Success at each template's position (`positions`), NaN where none is counted."""
    s = np.full(size, np.nan)
    for t, i in pos.items():
        r = resolved.get(_key(cell, t, task_cell))
        if r is not None and r.status == "counted" and r.record is not None:
            s[i] = float(bool(r.record.get("need_correct")))
    return s


def restrict(a: Arm, read: list[int]) -> dict:
    """The arm's counted keys on the templates read."""
    return hc.restrict({k: r for k, r in a.resolved.items() if k[0] == a.cell}, read)


def primary(restricted: dict, cell: str, task_cells: tuple[str, ...]) -> tuple:
    table, warn = hh.episode_table(restricted, api=hh.MESSAGES_API)
    sub = table[(table.repeat == 0) & (table.status == "counted") & (table.cell == cell)
                & (table.variant == hh.BASE) & table.task_cell.isin(task_cells)
                ].reset_index(drop=True)
    return sub, warn


def _usage(rec: dict, key: str):
    return (rec.get("usage") or {}).get(key)


def cost_row(records: list[dict]) -> dict:
    """Readings 5 and 8 over some counted records: the mean billed cost, output tokens and input
    tokens per episode, and the cache-read share of input, each with the records missing it (a
    mean with any missing is not given, so a missing value never counts as 0)."""
    cost, cost_missing = hp._mean([x.get("cost_usd_billed_est") for x in records])
    out, out_missing = hp._mean([_usage(x, "output_tokens") for x in records])
    inp, inp_missing = hp._mean([_usage(x, "input_tokens") for x in records])
    cached = [_usage(x, "cached_input_tokens") for x in records]
    inputs = [_usage(x, "input_tokens") for x in records]
    share_missing = sum(c is None or i is None for c, i in zip(cached, inputs, strict=True))
    total = sum(int(i) for i in inputs if i is not None)
    share = (None if share_missing or not total
             else sum(int(c) for c in cached) / total)
    return {"n": len(records), "cost_usd_billed_mean": cost, "cost_missing": cost_missing,
            "output_tokens_mean": out, "output_tokens_missing": out_missing,
            "input_tokens_mean": inp, "input_tokens_missing": inp_missing,
            "cache_read_share": share, "cache_read_share_missing": share_missing}


def costs(restricted: dict, cell: str, task_cells: tuple[str, ...], stop: int,
          pooled: bool = False) -> dict:
    """`cost_row` per task cell (and over all of them, with `pooled`)."""
    out = {tc: cost_row([r.record for r in hp._counted(restricted, cell, stop, (tc,))])
           for tc in task_cells}
    if pooled:
        out["all"] = cost_row([r.record for r in hp._counted(restricted, cell, stop, task_cells)])
    return out


def arm_reading(a: Arm, restricted: dict, task_cells: tuple[str, ...], stop: int,
                pos: dict[int, int], size: int, idx: np.ndarray,
                pooled: bool = False) -> tuple[dict, list[str]]:
    """Readings 1-3 and the cost part of 5 for one arm, from its restricted resolution, and the
    warnings."""
    sub, warn = primary(restricted, a.cell, task_cells)
    cells = hh.cell_table(sub, kinds=((a.cell, hh.BASE),), stopped=True, task_cells=task_cells)
    for row in cells:
        row["interval_90"] = hn.interval(by_template(restricted, a.cell, row["task_cell"], pos,
                                                     size), idx)
    window = hh.SPECS[a.cell].history == "window"
    return ({"arm": a.name, "cell": a.cell, "model": a.model, "experiment": a.experiment,
             "counted_repeat_0": len(sub), "cells": cells,
             "accounting": hh.accounting(sub, cells=(a.cell,), task_cells=task_cells),
             "choices_nr_far": hp.choices(restricted, a.cell, stop) if window else None,
             "costs": costs(restricted, a.cell, task_cells, stop, pooled)}, warn)


def contrasts(experiment: str, arms: dict[str, Arm], restricted: dict[str, dict],
              task_cells: tuple[str, ...], pos: dict[int, int], size: int,
              idx: np.ndarray) -> dict:
    """Reading 4 (`haiku_notes.contrast`: the same template resamples for both sides)."""
    def s(name: str, tc: str) -> np.ndarray:
        return by_template(restricted[name], arms[name].cell, tc, pos, size)
    return {f"{a} - {b}": {tc: hn.contrast(s(a, tc), s(b, tc), idx) for tc in task_cells}
            for a, b in CONTRASTS[experiment]}


@lru_cache(maxsize=3)
def _facts(start: int, stop: int, task_cells: tuple[str, ...]) -> dict[str, dict]:
    """What the generator gives for each episode (slow to build, and needed only with
    transcripts)."""
    return hpe.episode_facts(range(start, stop), task_cells)


def _by_run(restricted: dict, cell: str, task_cells: tuple[str, ...],
            stop: int) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for r in hp._counted(restricted, cell, stop, task_cells):
        out.setdefault(r.run_id, {})[r.record["episode_id"]] = r.record
    return out


def _transcript(raw: Path, experiment: str, run_id: str) -> Path:
    return raw / experiment / run_id / "transcript.jsonl.gz"


def declared_missing(a: Arm, by_run: dict[str, dict[str, dict]]) -> list[dict]:
    """The transcript lines that a recovered run's meta.json declares missing
    (`recovered.missing_transcript_line`), for the episodes this reading counts. A run whose
    process was killed can lose the line it was writing: R12's first Sonnet F-0 run lost the
    last request of one episode, whose record, usage and cost episodes.jsonl holds
    (results/decisions.md, 2026-11-12). The responses read from the transcripts are then
    that many fewer than the records count, and the output names each such line."""
    out = []
    for run in a.runs:
        if run.run_id not in by_run:
            continue
        meta = json.loads((run.folder / "meta.json").read_text(encoding="utf-8"))
        line = (meta.get("recovered") or {}).get("missing_transcript_line")
        if line and line.get("episode_id") in by_run[run.run_id]:
            out.append({"run_id": run.run_id, "episode_id": line["episode_id"],
                        "request_index": line.get("request_index")})
    return out


def responses(a: Arm, restricted: dict, task_cells: tuple[str, ...], stop: int, raw: Path,
              facts: dict[str, dict] | None = None) -> tuple[dict | None, list[str]]:
    """Reading 5's transcript part for one arm, from its restricted resolution, and the runs
    with no transcript. The reading is None when any is missing. `facts` defaults to the
    generator's for the arm's templates and task cells. Transcript lines a recovered run
    declares missing (`declared_missing`) are allowed for and named in the output."""
    by_run = _by_run(restricted, a.cell, task_cells, stop)
    missing = sorted(run_id for run_id in by_run
                     if not _transcript(raw, a.experiment, run_id).is_file())
    if missing:
        return None, missing
    records = {e: rec for recs in by_run.values() for e, rec in recs.items()}
    if facts is None:
        ts = sorted(hh.template_index(rec["template_id"]) for rec in records.values())
        facts = _facts(ts[0], ts[-1] + 1, task_cells) if ts else {}
    t = hpe.merge([hpe.transcript_readings(_transcript(raw, a.experiment, run_id), recs, facts)
                   for run_id, recs in sorted(by_run.items())])
    from_records = hpe.record_readings(list(records.values()))
    gaps = declared_missing(a, by_run)
    if t["responses"] != from_records["responses"] - len(gaps):
        raise hh.Refusal(f"{a.name}'s transcripts in {a.experiment} hold {t['responses']} "
                         f"responses, its records {from_records['responses']}"
                         + (f", less {len(gaps)} line(s) a recovered run declares missing"
                            if gaps else ""))
    s = hpe.arm_transcript_summary(t, records, task_cells)
    return ({"episodes": len(records), "runs": sorted(by_run),
             "responses": from_records["responses"],
             "responses_not_in_transcript": gaps,
             "refused_responses": from_records["refused_responses"],
             "refused_share": from_records["refused_share"],
             "refusal_categories": dict(sorted(from_records["refusal_categories"].items())),
             "responses_in_transcript": s["responses_in_transcript"],
             "with_thinking": s["with_thinking"], "thinking_share": s["thinking_share"],
             "with_redacted_thinking": t["redacted_thinking"],
             "at_need": {tc: retained(t["need_reply_chars"], records, tc)
                         for tc in task_cells}}, [])


def _median(xs: list[int]) -> float | None:
    return float(statistics.median(xs)) if xs else None


def retained(lengths: dict[str, list[int]], records: dict[str, dict], task_cell: str) -> dict:
    """Reading 5's retained replies at the need step's first request, in one task cell, from
    each episode's reply lengths (`haiku_provenance_extras.transcript_readings`). §17.12's
    "median length" is the median over the replies, pooled over the arm's episodes in the cell,
    so it is one reply's length. Also how many an episode retains (median over episodes), how
    many are pooled, and each episode's total characters (median over episodes: the count times
    the length, as R10 and R11 gave it), which is extra detail."""
    per = [lengths[e] for e, rec in sorted(records.items())
           if rec["task_cell"] == task_cell and e in lengths]
    pooled = [n for xs in per for n in xs]
    return {"episodes": len(per),
            "retained_replies_median": statistics.median(len(xs) for xs in per) if per else None,
            "retained_replies_pooled": len(pooled), "reply_chars_median": _median(pooled),
            "chars_per_episode_median": _median([sum(xs) for xs in per])}


def block_drops(a: Arm, restricted: dict, task_cells: tuple[str, ...], stop: int,
                raw: Path) -> tuple[dict | None, list[str], list[str]]:
    """Reading 8's drops for W-b-0, from the transcripts. Returns three things: per task cell, the
    step requests per episode whose info says the block rule dropped turns (``block_drop``), the
    runs with no transcript (the reading is then None), and the step requests whose info does
    not name the block rule."""
    by_run = _by_run(restricted, a.cell, task_cells, stop)
    missing = sorted(run_id for run_id in by_run
                     if not _transcript(raw, a.experiment, run_id).is_file())
    if missing:
        return None, missing, []
    drops: Counter = Counter()
    odd: list[str] = []
    for run_id, recs in sorted(by_run.items()):
        with gzip.open(_transcript(raw, a.experiment, run_id), "rt", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                d = json.loads(line)
                eid = d.get("episode_id")
                if eid not in recs or d.get("kind") != "step":
                    continue
                info = d.get("info") or {}
                if info.get("truncation") != "block":
                    odd.append(f"{run_id}: {eid} turn {d.get('turn')}")
                drops[eid] += bool(info.get("block_drop"))
    out = {}
    records = {e: rec for recs in by_run.values() for e, rec in recs.items()}
    for tc in (*task_cells, "all"):
        ids = [e for e, rec in records.items() if tc == "all" or rec["task_cell"] == tc]
        n = [drops[e] for e in ids]
        out[tc] = {"episodes": len(ids),
                   "drops_per_episode": sum(n) / len(n) if n else None,
                   "episodes_with_a_drop": sum(x > 0 for x in n),
                   "distribution": {str(k): v for k, v in sorted(Counter(n).items())}}
    return out, [], odd


def near_s_false(accounting: list[dict]) -> dict:
    """Reading 8's near-cell episodes whose evidence was not in the need step's request."""
    return {x["task_cell"]: {"n": x["n"], "S_false": x["S_verbatim_0"]}
            for x in accounting if TaskCell.from_id(x["task_cell"]).distance == "near"}


# --- readings 6 and 7 ------------------------------------------------------------------------

def _rate(values: list[float]) -> dict:
    k, n = int(sum(values)), len(values)
    return {"n": n, "successes": k, "rate": k / n if n else None}


def rounds(arms: list[Arm], read: list[int], task_cells: tuple[str, ...]) -> list[dict]:
    """Reading 6's success per arm and round on the templates read: §17.12's reading pools the
    task cells (task cell "all", n = the task cells times the templates read in the round).
    The rows per task cell that follow it are extra detail."""
    first = templates_of(NOTES).start
    n_rounds = len(templates_of(NOTES)) // ROUND
    rows = []
    for k in range(n_rounds):
        lo, hi = first + k * ROUND, first + (k + 1) * ROUND
        ts = [t for t in read if lo <= t < hi]
        for a in arms:
            per = {tc: [float(bool(a.resolved[_key(a.cell, t, tc)].record.get("need_correct")))
                        for t in ts] for tc in task_cells}
            for tc, vals in (("all", [v for c in task_cells for v in per[c]]), *per.items()):
                rows.append({"round": k + 1, "templates": f"{lo}-{hi - 1}",
                             "templates_read": len(ts), "arm": a.name, "task_cell": tc,
                             **_rate(vals)})
    return rows


def run_times(arms: list[Arm]) -> list[dict]:
    """Reading 6's runs: each one's cell, templates, ending, start and finish (UTC)."""
    rows = []
    for a in arms:
        for run in a.runs:
            meta = json.loads((run.folder / "meta.json").read_text(encoding="utf-8"))
            ts = sorted({hh.template_index(rec["template_id"]) for rec in run.records})
            rows.append({"run_id": run.run_id, "arm": a.name,
                         "templates": f"{ts[0]}-{ts[-1]}" if ts else None,
                         "exit_reason": run.exit_reason, "records": len(run.records),
                         "started_utc": _utc(meta.get("started_utc")),
                         "finished_utc": _utc(meta.get("finished_utc"))})
    return sorted(rows, key=lambda x: (x["started_utc"] or "", x["run_id"]))


def _utc(stamp: str | None) -> str | None:
    if not stamp:
        return None
    return datetime.fromisoformat(stamp).astimezone(UTC).isoformat(timespec="seconds")


def beside(notes: dict, sonnet: dict) -> dict | None:
    """Reading 7: Sonnet's arms and Haiku's experiment-1 arms on the templates of 200-224 that
    both experiments read. Described only: no contrast between the models."""
    if notes is None or sonnet is None:
        return None
    window = set(templates_of(SONNET))
    common = sorted(set(notes["read"]) & set(sonnet["read"]) & window)
    out = {"templates": _ranges(common), "n_templates": len(common), "arms": []}
    for model, exp in ((spec(SONNET)["model"], sonnet), (spec(NOTES)["model"], notes)):
        for a in exp["arms"]:
            sub, _ = primary(restrict(a, common), a.cell, NR_FAR)
            cells = hh.cell_table(sub, kinds=((a.cell, hh.BASE),), task_cells=NR_FAR)
            acc = hh.accounting(sub, cells=(a.cell,), task_cells=NR_FAR)
            out["arms"].append({
                "model": model, "arm": a.name,
                "cells": [{k: c[k] for k in ("task_cell", "n", "successes", "rate")}
                          for c in cells],
                "accounting": [{"task_cell": x["task_cell"], "P_carried": x["P_carried"],
                                "used_given_carried": x["used_given_carried"]} for x in acc]})
    return out


# --- the whole reading ----------------------------------------------------------------------

def _ranges(read: list[int]) -> str:
    return hc._ranges(read) if read else "none"


def readings(root: Path, links: dict[str, str], sweep_closed: set[str] | frozenset = frozenset(),
             *, raw_root: Path | None = None, allow_incomplete: bool = False,
             facts: dict[str, dict] | None = None,
             experiments: tuple[str, ...] | None = None) -> dict:
    """§17.12's readings. `sweep_closed` holds the experiments the researcher closed.
    `experiments` limits the reading to those experiments (all three when None). `facts` (for
    tests) replaces the generator's facts for reading 5."""
    unknown = set(sweep_closed) - set(EXPERIMENTS)
    if unknown:
        raise hh.Refusal(f"--sweep-closed names no R12 experiment: {', '.join(sorted(unknown))}")
    named = set(EXPERIMENTS if experiments is None else experiments)
    if not named or named - set(EXPERIMENTS):
        raise hh.Refusal("--experiment names no R12 experiment: "
                         + (", ".join(sorted(named - set(EXPERIMENTS))) or "none named"))
    chosen = tuple(e for e in EXPERIMENTS if e in named)  # in the registered order
    outside = set(sweep_closed) - named
    if outside:
        raise hh.Refusal("--sweep-closed names an experiment this reading leaves out: "
                         + ", ".join(sorted(outside)))
    raw = raw_root or root / "results" / "raw"
    runs = {e: discover(root, e) for e in chosen}
    by_exp = split_links(links, runs)
    seed, _ = hh.read_seed(root / "results")
    boot_seed = seed + hh.BOOT_SEED_OFFSET  # §9.1's bootstrap seed, as for R8's to R11's
    incomplete: list[str] = []
    warnings: list[str] = []
    state: dict[str, dict] = {}
    r8 = None
    for e in chosen:
        s, templates = spec(e), templates_of(e)
        task_cells = tuple(s["task_cells"])
        if not runs[e]:
            incomplete.append(f"{LABEL[e]} ({e}): no run under results/{e}/")
            continue
        resolved, warn = hh.resolve(runs[e], by_exp[e], sweep_closed=e in sweep_closed,
                                    echo=False, stopped=hh.request_check_stops(runs[e]))
        warnings += [f"{LABEL[e]}: {w}" for w in warn]
        own = [Arm(c, c, s["model"], e, resolved, [r for r in runs[e] if r.cell == c])
               for c in s["cells"]]
        arms = list(own)
        if e == BLOCK:
            if r8 is None:
                r8 = hn.r8_counted(root)
            r8_runs, r8_resolved = r8
            arms += [Arm(r8_name(c), c, registered.HAIKU_MODEL, R8_EXPERIMENT, r8_resolved,
                         [r for r in r8_runs if r.cell == c and r.repeat_index == 0
                          and hh.BASE in r.variants]) for c in R8_ARMS]
        read = templates_read(arms, task_cells, templates)
        left, never = left_out(arms, own, task_cells, templates, read)
        gaps, deviations = sweep_gaps(resolved, tuple(s["cells"]), task_cells, templates,
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
        raise hh.Refusal("R12's sweeps are incomplete:\n" + "\n".join(
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
        out[e] = _experiment(e, st, checks[e], raw, boot_seed, facts, incomplete, warnings)
    if incomplete and not allow_incomplete:
        raise hh.Refusal("\n".join(incomplete) + "\nPass --raw-root, or --allow-incomplete "
                         "(PROVISIONAL).")
    readable = {e: ({"read": state[e]["read"], "arms": state[e]["own"]}
                    if out.get(e) and "arms" in out[e] else None) for e in (NOTES, SONNET)}
    return {"prereg": registered.R12_REF, "block": registered.R12_BLOCK,
            "status": hh.PROVISIONAL if incomplete else hh.FINAL,
            "experiments_in_reading": list(chosen),
            "incomplete": incomplete, "rerun_links": links,
            "sweep_closed": sorted(sweep_closed),
            "bootstrap": {"resamples": BOOT, "seed": boot_seed,
                          "interval": "90% percentile, template-cluster",
                          "experiments_1_2": "over the templates read, mapped to 0..n-1",
                          "experiment_3": "R8 to R11's resamples (T = 200), by template number"},
            "experiments": out,
            "beside": beside(readable[NOTES], readable[SONNET]),
            "does_not_show": list(DOES_NOT_SHOW),
            "warnings": [*warnings, *missing_values(out)]}


def _unread(e: str, st: dict, check: dict) -> dict:
    """An experiment with runs but no template read (PROVISIONAL only)."""
    return {"label": LABEL[e], "experiment": e, "model": spec(e)["model"],
            "templates_read": 0, "templates": "none", "left_out": st["left_out"],
            "templates_never_played": st["never"], "deviations": st["deviations"],
            "accounting_check": _check_out(check), "exclusions": _exclusions(e, st),
            "runs": [hh.run_row(r, st["resolved"]) for r in st["runs"]]}


def _check_out(check: dict) -> dict:
    return {"checked": check["checked"], "bugs": check["bugs"],
            "missing_transcripts": check["missing_transcripts"]}


def _exclusions(e: str, st: dict) -> list[dict]:
    """§13's counts per arm and task cell over the experiment's registered templates."""
    return hh.exclusion_table(st["resolved"], st["templates"].stop,
                              kinds=tuple((c, hh.BASE) for c in spec(e)["cells"]), echo=False,
                              task_cells=st["task_cells"], first=st["templates"].start)


def _experiment(e: str, st: dict, check: dict, raw: Path, boot_seed: int,
                facts: dict | None, incomplete: list[str], warnings: list[str]) -> dict:
    """Readings 1-5 for one experiment, with 6 (experiment 1) and 8 (experiment 3)."""
    read, task_cells, stop = st["read"], st["task_cells"], st["templates"].stop
    pos, size = positions(e, read)
    idx = hh.resample_indices(size, boot_seed, BOOT)
    restricted = {a.name: restrict(a, read) for a in st["arms"]}
    arms_by_name = {a.name: a for a in st["arms"]}
    arms = []
    for a in st["arms"]:
        reading, warn = arm_reading(a, restricted[a.name], task_cells, stop, pos, size, idx,
                                    pooled=e == BLOCK)
        warnings += [f"{LABEL[e]}, {a.name}: {w}" for w in warn]
        reading["responses"], missing = responses(a, restricted[a.name], task_cells, stop, raw,
                                                  facts)
        redacted = (reading["responses"] or {}).get("with_redacted_thinking")
        if redacted:
            warnings.append(f"{LABEL[e]}, {a.name}: {redacted} response(s) hold a "
                            "redacted_thinking block, counted among those with a thinking "
                            "block in reading 5")
        for run_id in missing:
            incomplete.append(f"{LABEL[e]}: no raw transcript for {run_id} under {raw} "
                              f"({a.name}): reading 5 cannot be made")
        arms.append(reading)
    result = {"label": LABEL[e], "experiment": e, "model": spec(e)["model"],
              "cells": list(spec(e)["cells"]), "task_cells": list(task_cells),
              "templates_registered": f"{st['templates'].start}-{stop - 1}",
              "templates_read": len(read), "templates": _ranges(read),
              "left_out": st["left_out"], "templates_never_played": st["never"],
              "resamples_over": size, "deviations": st["deviations"],
              "accounting_check": _check_out(check), "exclusions": _exclusions(e, st),
              "runs": [hh.run_row(r, st["resolved"]) for r in st["runs"]],
              "arms": arms,
              "contrasts": contrasts(e, arms_by_name, restricted, task_cells, pos, size, idx)}
    if e == BLOCK:
        result["comparators"] = {"output": hn.R8_OUTPUT,
                                 "runs": sorted({r.run_id for a in st["arms"]
                                                 if a.experiment == R8_EXPERIMENT
                                                 for r in a.runs})}
        result["cost_and_context"] = _cost_and_context(st, arms, restricted, raw, incomplete,
                                                       warnings)
    if e == NOTES:
        result["rounds"] = {"success": rounds(st["own"], read, task_cells),
                            "runs": run_times(st["own"])}
    return result


def _cost_and_context(st: dict, arms: list[dict], restricted: dict, raw: Path,
                      incomplete: list[str], warnings: list[str]) -> dict:
    """Reading 8."""
    task_cells, stop = st["task_cells"], st["templates"].stop
    block = next(a for a in st["arms"] if a.cell == "W-b-0")
    drops, missing, odd = block_drops(block, restricted[block.name], task_cells, stop, raw)
    for run_id in missing:
        incomplete.append(f"Experiment 3: no raw transcript for {run_id} under {raw} "
                          f"({block.name}): reading 8's drops cannot be made")
    if odd:
        warnings.append(f"Experiment 3: {len(odd)} W-b-0 step request(s) whose info does not "
                        f"name the block rule (first: {odd[0]})")
    return {"arms": [{"arm": a["arm"], "costs": a["costs"],
                      "near_need_payload_S_false": near_s_false(a["accounting"])}
                     for a in arms],
            "block_drops": drops}


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

def _pct(x: float | None) -> str:
    return hp._pct(x)


def _iv(iv) -> str:
    return "n/a" if iv is None else f"{_pct(iv[0])} to {_pct(iv[1])}"


def _share(a: int | None, b: int | None) -> str:
    return "n/a" if not b else f"{a}/{b} ({100 * a / b:.1f}%)"


def _num(x: float | None, fmt: str) -> str:
    return "n/a" if x is None else format(x, fmt)


def _experiment_lines(x: dict) -> list[str]:
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
    lines += ["", ("**2. §2.8 accounting** (not-recoverable far cells, where P(carried) is a "
                   "lower bound):"), "",
              "| Arm | Task cell | S verbatim 0 | P(carried) | Success given carried |",
              "|---|---|---|---|---|"]
    for a in x["arms"]:
        for r in a["accounting"]:
            if r["task_cell"] not in NR_FAR:
                continue
            pc = r.get("P_carried") or {}
            lines.append(f"| {a['arm']} | {r['task_cell']} | {r['S_verbatim_0']} | "
                         f"{hp._frac(pc.get('carried'), pc.get('n'))} | "
                         f"{hp._frac_rate(r.get('used_given_carried'))} |")
    lines += ["", "**3. Choices with the fact evicted** (window arms):", ""]
    for a in x["arms"]:
        for tc, c in (a["choices_nr_far"] or {}).items():
            lines.append(f"- {a['arm']}, {tc}: chose an option in {c['chose_an_option']} of "
                         f"{c['episodes']}, {c['correct']} correct.")
    lines += ["", ("**4. Contrasts** (percentage points, 90% interval over the same template "
                   "resamples, described, not tested):"), ""]
    if x["experiment"] == NOTES:
        lines += [NOTE_NEUTRAL, ""]
    for name, by_tc in x["contrasts"].items():
        for tc, v in by_tc.items():
            lines.append(f"- {name}, {tc}: {hp._pp(v)}")
    lines += ["", "**5. Responses:**", "", NOTE_THINKING + (
                  " The retained replies are those in the need step's first request. Their "
                  "length is one reply's, the median over the replies pooled in the task cell."),
              "",
              ("| Arm | Refused responses | Categories | With a thinking block | Task cell | "
               "Retained replies at the need step (median per episode) | One retained reply's "
               "length (median characters) | Output tokens per episode | Cost per episode "
               "(USD) |"),
              "|---|---|---|---|---|---|---|---|---|"]
    for a in x["arms"]:
        s = a.get("responses")
        for tc in x["task_cells"]:
            c = a["costs"][tc]
            head = (f"| {a['arm']} | (no transcripts) | | | " if s is None else
                    f"| {a['arm']} | {_share(s['refused_responses'], s['responses'])} | "
                    f"{s['refusal_categories'] or '-'} | "
                    f"{_share(s['with_thinking'], s['responses_in_transcript'])}"
                    + (f", {s['with_redacted_thinking']} redacted"
                       if s.get("with_redacted_thinking") else "") + " | ")
            n = None if s is None else s["at_need"][tc]
            lines.append(head + f"{tc} | "
                         f"{'n/a' if n is None else n['retained_replies_median']} | "
                         f"{'n/a' if n is None else _num(n['reply_chars_median'], '.0f')} | "
                         f"{_num(c['output_tokens_mean'], '.0f')} | "
                         f"{_num(c['cost_usd_billed_mean'], '.5f')} |")
    for a in x["arms"]:
        for g in (a.get("responses") or {}).get("responses_not_in_transcript") or []:
            lines += ["", (f"{a['arm']}: request {g['request_index']} of {g['episode_id']} in "
                           f"run {g['run_id']} is not in its transcript, whose process was "
                           "killed while writing it. The episode's record, usage and cost are "
                           "counted. The thinking-block share is out of the responses in the "
                           "transcripts, and the need-step columns leave the episode out if "
                           "that request was its need step.")]
    if "rounds" in x:
        lines += ["", "**6. Rounds** (described only):", "",
                  ("Task cell \"all\" pools the task cells: success per arm and round, as §17.12 "
                   "registers it. The rows per task cell are extra detail."), "",
                  "| Round | Templates | Read | Arm | Task cell | Success |",
                  "|---|---|---|---|---|---|"]
        for r in x["rounds"]["success"]:
            lines.append(f"| {r['round']} | {r['templates']} | {r['templates_read']} | "
                         f"{r['arm']} | {r['task_cell']} | {r['successes']}/{r['n']} "
                         f"({_pct(r['rate'])}) |")
        lines += ["", "| Run | Arm | Templates | Ending | Started (UTC) | Finished (UTC) |",
                  "|---|---|---|---|---|---|"]
        for r in x["rounds"]["runs"]:
            lines.append(f"| {r['run_id']} | {r['arm']} | {r['templates']} | {r['exit_reason']} | "
                         f"{r['started_utc']} | {r['finished_utc']} |")
    if "cost_and_context" in x:
        cc = x["cost_and_context"]
        lines += ["", "**8. Cost and context** (per episode, with R8's arms run on 2026-10-18):",
                  "", NOTE_BLOCK, "",
                  ("| Arm | Task cell | Episodes | Cost (USD) | Input tokens | Cache-read share "
                   "of input |"), "|---|---|---|---|---|---|"]
        for a in cc["arms"]:
            for tc, c in a["costs"].items():
                lines.append(f"| {a['arm']} | {tc} | {c['n']} | "
                             f"{_num(c['cost_usd_billed_mean'], '.5f')} | "
                             f"{_num(c['input_tokens_mean'], ',.0f')} | "
                             f"{_pct(c['cache_read_share'])} |")
        lines += ["", ("Near-cell episodes whose evidence was not in the need step's request "
                       "(need_payload.S false):"), ""]
        for a in cc["arms"]:
            lines.append(f"- {a['arm']}: " + ", ".join(
                f"{tc} {v['S_false']} of {v['n']}"
                for tc, v in a["near_need_payload_S_false"].items()) + ".")
        lines += ["", "W-b-0's block drops per episode:", ""]
        if cc["block_drops"] is None:
            lines.append("- (no transcripts)")
        else:
            for tc, v in cc["block_drops"].items():
                lines.append(f"- {tc}: {_num(v['drops_per_episode'], '.2f')} over "
                             f"{v['episodes']} episodes, {v['episodes_with_a_drop']} with a drop, "
                             f"distribution {v['distribution']}.")
    lines += ["", "**Exclusions** (per arm and task cell, repeat 0, §13):", ""]
    for r in x.get("exclusions", []):
        rest = {k: v for k, v in r.items() if k not in ("kind", "cell", "variant", "task_cell")
                and v not in (0, None, {}, [])}
        lines.append(f"- {r['cell']}, {r['task_cell']}: {rest or 'none'}")
    lines += [f"- deviation: {d}" for d in x["deviations"]]
    return lines + [""]


def summary(r: dict) -> str:
    lines = ["# R12: Haiku's notes sentences, claude-sonnet-5-5, and a block-truncation window",
             "",
             (f"**{r['status']}.** {r['prereg']}. Exploratory: no test, no label. Repeat 0, base "
              "episodes. Not a model comparison, and nothing is ranked."), "",
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
        lines += _experiment_lines(x)
    b = r["beside"]
    lines += ["## 7. Experiment 2 beside Haiku (described only, no contrast between the models)",
              "", NOTE_EFFORT, ""]
    if b is None:
        lines += ["Not read: experiment 1 or 2 has no template read.", ""]
    else:
        lines += [f"Templates {b['templates']} ({b['n_templates']}), both experiments.", "",
                  "| Model | Arm | Task cell | Success | P(carried) | Success given carried |",
                  "|---|---|---|---|---|---|"]
        for a in b["arms"]:
            acc = {x["task_cell"]: x for x in a["accounting"]}
            for c in a["cells"]:
                pc = acc[c["task_cell"]]["P_carried"] or {}
                lines.append(f"| {a['model']} | {a['arm']} | {c['task_cell']} | "
                             f"{c['successes']}/{c['n']} ({_pct(c['rate'])}) | "
                             f"{hp._frac(pc.get('carried'), pc.get('n'))} | "
                             f"{hp._frac_rate(acc[c['task_cell']]['used_given_carried'])} |")
        lines.append("")
    lines += [f"- incomplete: {x}" for x in r["incomplete"]]
    lines += [f"- warning: {w}" for w in r["warnings"]]
    return "\n".join(lines) + "\n"


# --- main -----------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results-root", type=Path, default=REPO_ROOT)
    ap.add_argument("--rerun", action="append", default=[], metavar="RUN=ORIGINAL")
    ap.add_argument("--sweep-closed", action="append", default=[], choices=sorted(SHORT),
                    help="an experiment whose sweep the researcher closed (repeatable)")
    ap.add_argument("--experiment", action="append", default=[], choices=sorted(SHORT),
                    help="read only this experiment (repeatable; default: all three)")
    ap.add_argument("--allow-incomplete", action="store_true")
    ap.add_argument("--raw-root", type=Path, default=None)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--out-dir", type=Path, default=None)
    a = ap.parse_args(argv)
    now = datetime.now(UTC)
    closed = {SHORT[x] for x in a.sweep_closed}
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        r = readings(a.results_root, hn._links(a.rerun), closed, raw_root=a.raw_root,
                     allow_incomplete=a.allow_incomplete,
                     experiments=tuple(SHORT[x] for x in a.experiment) or None)
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
                "status": r["status"], "r8_output": hn.R8_OUTPUT,
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
