"""R11's descriptive analysis: a later W-n-0 control for R10's two cells (PREREG §17.11; $0, no test).

R11 registers one run of claude-haiku-5-5's W-n-0 in its own experiment
`persistgym_haiku_control`, on the 2 not-recoverable far task cells, main templates 0-199 at
repeat 0, stopped at the block's $17.38, under the organization of R10's runs. This script reads
its counted records as `analysis.haiku_provenance` reads R10's, and sets beside them R9's W-n-0
(as `analysis.haiku_provenance.R9_OUTPUT` counted it) and R10's W-np-0 and W-npd-0 (as
`R10_OUTPUT` counted them), on the same episodes.

**The templates read.** The run is expected to stop a little short of template 199, because a
parallel run cannot use the last part of its planned spend (`harnesses/DESIGN.md` §7.6). So every
arm is read on the first k templates, where k is the number of leading templates the control
finished in both task cells (`templates_read`). At k = 200 the resamples are those of R8's, R9's
and R10's analyses.

It reports, per arm and task cell on those templates:

1. **Success,** with a 90% template-cluster bootstrap interval (10,000 resamples with §9.1's
   seed, SEED + 10). Refusals and empty replies score 0 at the need step (R8), and each cell's
   step responses that stopped short are counted by reason.
2. **§2.8's accounting** (`persistgym_h1h3.accounting`): S verbatim, P(carried) (a lower bound:
   the string match misses paraphrase), success given carried, and success among the rest.
3. **Choices with the fact evicted:** the episodes that chose one of the 10 options at the need
   step, and how many were correct.
4. **Contrasts,** in percentage points with a 90% interval over the same template resamples:
   the control minus R9's W-n-0, W-np-0 minus the control, and W-npd-0 minus the control.
5. **Replies,** for the control and R9's W-n-0, which have the same instruction, by whether the
   notes carried the fact, with `analysis.haiku_notes_replies`'s text patterns unchanged. These
   patterns undercount on W-n-0's replies (R9's hand checks). They are pointers.
6. **Responses,** per arm, by `analysis.haiku_provenance_extras`'s code: refusals, by category
   and by turn; the share of responses with a thinking block (presence only), by turn, with and
   without the need steps; the replies holding the fact's value; the replies retained at the
   need step; where the fact's value appears in the need step's first request (the leak check);
   and whether each user message matches R9's at the same episode and step.
7. **Cost and output tokens per episode,** per arm and task cell.
8. **Run conditions,** per arm's runs: the returned model strings, the geos served, uncached
   input tokens per minute, `--parallel`, the dates, and for the control `org-check`'s results.

Nothing here is a test. It ranks nothing, and differences are described, not tested.

**Before any reading:**
- every record of the control's runs must be on the 2 task cells;
- the control's sweep must be complete, or have stopped at its planned spend
  (`SPEND_RESERVATION` or `COST_CAP`) with no API error awaiting its §13 re-run, or be closed
  with ``--sweep-closed``. Otherwise the script refuses, unless ``--allow-incomplete`` is passed,
  and the output is then PROVISIONAL;
- §2.8's accounting check (`persistgym_h1h3.accounting_check`) on the control's raw transcripts
  under ``--raw-root`` (default ``results/raw``). A bug stops the analysis (`AccountingBug`).
  Missing transcripts of any arm refuse likewise, or make the output PROVISIONAL with
  ``--allow-incomplete``.

Run: ``uv run python -m analysis.haiku_control [--rerun RUN=ORIGINAL ...] [--sweep-closed]``. It
writes ``results/haiku_control/<UTC>/control.json``, ``summary.md`` and ``meta.json``. With
``--no-write`` it only prints.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import numpy as np

from analysis import haiku_notes as hn
from analysis import haiku_provenance as hp
from analysis import haiku_provenance_extras as hpe
from analysis import persistgym_h1h3 as hh
from common import runmeta
from harnesses import registered

REPO_ROOT = Path(__file__).resolve().parent.parent
R10_OUTPUT = "results/haiku_provenance/20261102T045643Z"
"""R10's cited readings (FINAL): its meta.json lists the runs and re-run links that it counted."""
EXPERIMENT = registered.HAIKU_CONTROL_EXPERIMENT
CELL = registered.HAIKU_CONTROL_CELL
TASK_CELLS = registered.HAIKU_CONTROL_TASK_CELLS
T = registered.HAIKU_T
CONTROL_ARM = "W-n-0 (R11)"
R9_ARM = "W-n-0 (R9)"
SPEND_STOPS = ("SPEND_RESERVATION", "COST_CAP")
"""The endings of a run stopped at its planned spend, which R11 registers as closing the sweep."""
OUTPUTS = ("control.json", "summary.md", "meta.json")
_episode_facts = lru_cache(maxsize=1)(hpe.episode_facts)
"""What the generator gives for each far episode: slow to build, and needed only with transcripts."""


def r10_read(root: Path) -> tuple[list, dict]:
    """R10's runs and resolution, as its cited output counted them."""
    meta = json.loads((root / R10_OUTPUT / "meta.json").read_text(encoding="utf-8"))
    runs, resolved, _ = hp.read(root, registered.HAIKU_PROVENANCE_EXPERIMENT,
                                tuple(registered.HAIKU_PROVENANCE_CELLS),
                                dict(meta["config"]["rerun_links"]),
                                bool(meta["config"]["sweep_closed"]),
                                declared=list(meta["runs"]))
    return runs, resolved


def templates_read(resolved: dict) -> int:
    """How many leading main templates the control finished in both task cells: k, so that every
    arm can be read on templates 0 to k - 1."""
    for t in range(T):
        for tc in TASK_CELLS:
            r = resolved.get((CELL, hh.episode_id_of(CELL, hh.BASE, t, tc), 0))
            if r is None or r.status != "counted" or r.record is None:
                return t
    return T


def primary(resolved: dict, cell: str, k: int) -> tuple:
    """The counted repeat-0 base episodes of `cell` on the task cells and templates read."""
    table, warn = hh.episode_table(resolved, api=hh.MESSAGES_API)
    sub = table[(table.repeat == 0) & (table.status == "counted") & (table.cell == cell)
                & (table.variant == hh.BASE) & (table.template < k)
                & table.task_cell.isin(TASK_CELLS)].reset_index(drop=True)
    return sub, warn


def arm(name: str, resolved: dict, cell: str, k: int, idx: np.ndarray) -> tuple[dict, list]:
    """Readings 1-3 and 7 for one arm, and the warnings."""
    sub, warn = primary(resolved, cell, k)
    cells = hh.cell_table(sub, kinds=((cell, hh.BASE),), stopped=True, task_cells=TASK_CELLS)
    for row in cells:
        row["interval_90"] = hn.interval(hn.by_template(resolved, cell, row["task_cell"], k), idx)
    costs = hp.costs_per_episode(resolved, cell, k)
    return ({"arm": name, "cell": cell, "counted_repeat_0": len(sub), "cells": cells,
             "accounting": hh.accounting(sub, cells=(cell,), task_cells=TASK_CELLS),
             "choices_nr_far": hp.choices(resolved, cell, k),
             "costs": {tc: costs[tc] for tc in TASK_CELLS}}, warn)


def contrasts(control: dict, r9: dict, r10: dict, k: int, idx: np.ndarray) -> dict:
    """Reading 4 (`haiku_notes.contrast`: the same template resamples for both sides)."""
    ctl = {tc: hn.by_template(control, CELL, tc, k) for tc in TASK_CELLS}
    out = {f"{CONTROL_ARM} - {R9_ARM}": {
        tc: hn.contrast(ctl[tc], hn.by_template(r9, hp.R9_CELL, tc, k), idx)
        for tc in TASK_CELLS}}
    for c in registered.HAIKU_PROVENANCE_CELLS:
        out[f"{c} - {CONTROL_ARM}"] = {
            tc: hn.contrast(hn.by_template(r10, c, tc, k), ctl[tc], idx) for tc in TASK_CELLS}
    return out


def responses(resolved: dict, experiment: str, cell: str, k: int, raw: Path,
              facts: dict[str, dict] | None = None) -> tuple[dict | None, dict, list[str]]:
    """Reading 6 for one arm, its user-message digests, and the runs with no transcript. The
    reading is None when any is missing. `facts` defaults to the generator's."""
    by_run: dict[str, dict[str, dict]] = {}
    for r in hp._counted(resolved, cell, k, TASK_CELLS):
        by_run.setdefault(r.run_id, {})[r.record["episode_id"]] = r.record
    missing = sorted(run_id for run_id in by_run
                     if not (raw / experiment / run_id / "transcript.jsonl.gz").is_file())
    if missing:
        return None, {}, missing
    records = {e: rec for recs in by_run.values() for e, rec in recs.items()}
    facts = _episode_facts() if facts is None else facts
    t = hpe.merge([hpe.transcript_readings(raw / experiment / run_id / "transcript.jsonl.gz",
                                           recs, facts)
                   for run_id, recs in sorted(by_run.items())])
    from_records = hpe.record_readings(list(records.values()))
    if t["responses"] != from_records["responses"]:
        raise hh.Refusal(f"{cell}'s transcripts in {experiment} hold {t['responses']} responses, "
                         f"its records {from_records['responses']}")
    summary_ = hpe.arm_transcript_summary(t, records)
    for key in ("fact_value_in_replies", "at_need", "leak_check"):
        summary_[key] = {tc: summary_[key][tc] for tc in TASK_CELLS}
    return {**from_records, **summary_, "episodes": len(records), "runs": sorted(by_run)}, \
        t["user_hash"], []


def run_conditions(root: Path, experiment: str, cell: str, runs: list, raw: Path) -> list[dict]:
    """Reading 8 for one arm's runs."""
    out = []
    for run in runs:
        if run.cell != cell:
            continue
        meta = json.loads((run.folder / "meta.json").read_text(encoding="utf-8"))
        out.append({"run_id": run.run_id, "exit_reason": run.exit_reason,
                    "started_utc": meta.get("started_utc"), "finished_utc": meta.get("finished_utc"),
                    "model_returned": [str(m) for m in run.model_returned],
                    "inference_geos": meta.get("inference_geos"),
                    "cost_usd": meta.get("cost_usd"),
                    **hpe.input_rate(root, experiment, run.run_id, raw)})
    return out


def org_checks(root: Path) -> list[dict]:
    """`harnesses org-check`'s committed results, oldest first."""
    folder = root / "results" / registered.HAIKU_CONTROL_ORG_CHECK
    rows = []
    for path in sorted(folder.glob("*/org_check.json")) if folder.is_dir() else []:
        d = json.loads(path.read_text(encoding="utf-8"))
        rows.append({"folder": path.parent.name, "checked_utc": d.get("checked_utc"),
                     "same_org_as_r10": d.get("same_org_as_r10"),
                     "same_org_as_r8": d.get("same_org_as_r8")})
    return rows


def readings(root: Path, links: dict[str, str], sweep_closed: bool, *,
             raw_root: Path | None = None, allow_incomplete: bool = False) -> dict:
    runs, control, warn = hp.read(root, EXPERIMENT, (CELL,), links, sweep_closed)
    off = sorted({rec["task_cell"] for run in runs for rec in run.records} - set(TASK_CELLS))
    if off:
        raise hh.Refusal(f"R11's run plays {', '.join(TASK_CELLS)} only, but records hold "
                         f"{', '.join(off)}")
    k = templates_read(control)
    if k == 0:
        raise hh.Refusal("the control finished no template in both task cells")
    kinds = ((CELL, hh.BASE),)
    incomplete, deviations = hh.completeness(control, k, sweep_closed, kinds, task_cells=TASK_CELLS)
    ended = [r.exit_reason for r in runs]
    waiting = sorted(key[1] for key, r in control.items() if r.awaiting_rerun)
    if waiting and not sweep_closed:
        incomplete.append(f"{len(waiting)} episode(s) await their §13 re-run: "
                          + ", ".join(waiting[:5]))
    if k < T and not sweep_closed and not any(e in SPEND_STOPS for e in ended):
        incomplete.append(f"the control finished {k} of {T} templates, and no run stopped at its "
                          f"planned spend (endings: {', '.join(map(str, ended))})")
    if incomplete and not allow_incomplete:
        raise hh.Refusal("the control's sweep is incomplete:\n" + "\n".join(
            f"  - {x}" for x in incomplete) + "\nWait for the runs, pass --sweep-closed once the "
            "researcher has closed the sweep, or pass --allow-incomplete to see what exists "
            "(PROVISIONAL).")
    raw = raw_root or root / "results" / "raw"
    check = hh.accounting_check(runs, raw, EXPERIMENT, hh.MESSAGES_API)
    if check["bugs"]:
        raise hh.AccountingBug(
            "PREREG §2.8's bug stop: window-accounting bug(s), so no result is reported until "
            "they are found:\n" + "\n".join(f"  - {b}" for b in check["bugs"]))
    r9_runs, r9 = hp.r9_read(root)
    r10_runs, r10 = r10_read(root)
    seed, _ = hh.read_seed(root / "results")
    boot_seed = seed + hh.BOOT_SEED_OFFSET  # §9.1's bootstrap seed, as for R8's to R10's
    idx = hh.resample_indices(k, boot_seed, hp.BOOT)
    prov = registered.HAIKU_PROVENANCE_EXPERIMENT
    plan = [(CONTROL_ARM, control, EXPERIMENT, CELL, runs),
            (R9_ARM, r9, registered.HAIKU_NOTES_EXPERIMENT, hp.R9_CELL, r9_runs),
            *((c, r10, prov, c, r10_runs) for c in registered.HAIKU_PROVENANCE_CELLS)]
    arms, hashes, warnings = [], {}, list(warn)
    for name, resolved, experiment, cell, arm_runs in plan:
        a, w = arm(name, resolved, cell, k, idx)
        warnings += w
        a["responses"], hashes[name], missing = responses(resolved, experiment, cell, k, raw)
        a["replies_nr_far"], gone = (hp.replies(resolved, cell, k, raw, experiment)
                                     if name in (CONTROL_ARM, R9_ARM) else (None, []))
        a["conditions"] = run_conditions(root, experiment, cell, arm_runs, raw)
        for run_id in sorted({*missing, *gone}):
            incomplete.append(f"no raw transcript for {run_id} under {raw} ({name}): reading 5 or "
                              "6 cannot be made")
        arms.append(a)
    if incomplete and not allow_incomplete:
        raise hh.Refusal("\n".join(incomplete) + "\nPass --raw-root, or --allow-incomplete "
                         "(PROVISIONAL).")
    ref = hashes[R9_ARM]
    orgs = org_checks(root)
    if not orgs:
        warnings.append("no org-check result is committed for the control")
    elif not all(o["same_org_as_r10"] for o in orgs):
        warnings.append("an org-check result names another organization than R10's")
    return {"experiment": EXPERIMENT, "cell": CELL, "model": registered.HAIKU_MODEL,
            "prereg": registered.R11_REF, "T": T, "templates_read": k,
            "task_cells": list(TASK_CELLS),
            "status": hh.PROVISIONAL if incomplete else hh.FINAL,
            "incomplete": incomplete, "deviations": deviations,
            "accounting_check": {"checked": check["checked"], "bugs": check["bugs"],
                                 "missing_transcripts": check["missing_transcripts"]},
            "exclusions": hh.exclusion_table(control, k, kinds=kinds, echo=False,
                                             task_cells=TASK_CELLS),
            "bootstrap": {"resamples": hp.BOOT, "seed": boot_seed,
                          "interval": "90% percentile, template-cluster"},
            "runs": [hh.run_row(r, control) for r in runs], "rerun_links": links,
            "sweep_closed": sweep_closed, "arms": arms,
            "sources": {"r9": hp.R9_OUTPUT, "r10": R10_OUTPUT},
            "contrasts": contrasts(control, r9, r10, k, idx),
            "user_messages_against_r9": {
                name: {"common": len(ref.keys() & h),
                       "identical": sum(ref[x] == h[x] for x in ref.keys() & h)}
                for name, h in hashes.items() if name != R9_ARM},
            "org_checks": orgs,
            "warnings": [*warnings, *check["warnings"], *hp.missing_values(arms)]}


def _share(pair: list | None) -> str:
    return "n/a" if not pair or not pair[1] else f"{pair[0]}/{pair[1]} ({100 * pair[0] / pair[1]:.1f}%)"


def summary(r: dict) -> str:
    k = r["templates_read"]
    lines = [f"# {r['model']}: R11's later W-n-0 control ({r['experiment']})", "",
             (f"**{r['status']}.** {r['prereg']}. Exploratory: no test, no label. Repeat 0, the 2 "
              f"not-recoverable far task cells, main templates 0-{k - 1} in every arm. Not a model "
              f"comparison. §2.8's accounting check: {r['accounting_check']['checked']} need steps "
              f"replayed, {len(r['accounting_check']['bugs'])} bugs. R11's run came after R10's "
              "arms, not alongside them."), "",
             "| Arm | Task cell | Success | 90% interval | Refused episodes | Stopped responses |",
             "|---|---|---|---|---|---|"]
    for a in r["arms"]:
        for c in a["cells"]:
            iv = c.get("interval_90")
            lines.append(f"| {a['arm']} | {c['task_cell']} | {c['successes']}/{c['n']} "
                         f"({hp._pct(c['rate'])}) | "
                         f"{'n/a' if iv is None else f'{hp._pct(iv[0])} to {hp._pct(iv[1])}'} | "
                         f"{c.get('episodes_with_a_refusal', 0)} | "
                         f"{c.get('stopped_responses') or '-'} |")
    lines += ["", "**§2.8 accounting** (P(carried) is a lower bound):", "",
              ("| Arm | Task cell | S verbatim 0 | P(carried) | Used given carried | "
               "Not carried: success, no lookup | Not carried: success, lookup |"),
              "|---|---|---|---|---|---|---|"]
    for a in r["arms"]:
        for x in a["accounting"]:
            pc = x.get("P_carried") or {}
            lines.append(f"| {a['arm']} | {x['task_cell']} | {x['S_verbatim_0']} | "
                         f"{hp._frac(pc.get('carried'), pc.get('n'))} | "
                         f"{hp._frac_rate(x.get('used_given_carried'))} | "
                         f"{hp._frac_rate(x.get('rescued_without_lookup'))} | "
                         f"{hp._frac_rate(x.get('rescued_with_lookup'))} |")
    lines += ["", "**Choices with the fact evicted:**", ""]
    for a in r["arms"]:
        for tc, c in a["choices_nr_far"].items():
            lines.append(f"- {a['arm']}, {tc}: chose an option in {c['chose_an_option']} of "
                         f"{c['episodes']}, {c['correct']} correct.")
    lines += ["", ("**Contrasts** (percentage points, 90% interval over the same template "
                   "resamples; described, not tested):"), ""]
    for name, by_tc in r["contrasts"].items():
        for tc, v in by_tc.items():
            lines.append(f"- {name}, {tc}: {hp._pp(v)}")
    lines += ["", ("**Replies** (R9's text patterns, which undercount on W-n-0's replies; pointers, "
                   "not a coding):"), "",
              ("| Arm | Cell, notes carried the fact | Episodes | Correct | Failed | "
               "Failed: declined | Failed: need reply disowns its figure | "
               "Failed: retracted before the need step |"),
              "|---|---|---|---|---|---|---|---|"]
    for a in r["arms"]:
        if a["arm"] not in (CONTROL_ARM, R9_ARM):
            continue
        t = a.get("replies_nr_far")
        if t is None:
            lines.append(f"| {a['arm']} | (no transcripts) | | | | | | |")
            continue
        for key, v in t.items():
            lines.append(f"| {a['arm']} | {key} | {v['episodes']} | {v['correct']} | "
                         f"{v['failed']} | {v['failed_declined']} | "
                         f"{v['failed_need_reply_disowns']} | "
                         f"{v['failed_retracted_before_need']} |")
    lines += ["", "**Responses:**", "",
              ("| Arm | Refused responses | By turn (0-4, 5-9, 10-14, 15 on) | With a thinking block "
               "| By turn (first requests; 0-4, 5-9, 10-14, 15 on) | Need step's first request |"),
              "|---|---|---|---|---|---|"]
    for a in r["arms"]:
        s = a.get("responses")
        if s is None:
            lines.append(f"| {a['arm']} | (no transcripts) | | | | |")
            continue
        turns = ", ".join(str(v) for v in s["refused_by_turn"].values())
        bins = ", ".join(_share(v) for v in s["first_requests_by_turn_bin"].values())
        lines.append(f"| {a['arm']} | {_share([s['refused_responses'], s['responses']])} | {turns} "
                     f"| {_share([s['with_thinking'], s['responses_in_transcript']])} | {bins} | "
                     f"{_share(s['need_first_request_thinking'])} |")
    lines += ["", ("**The notes** (from the last evidence step to the step before the need step: "
                   "replies holding the fact's value; at the need step: replies retained, and "
                   "their median length in characters):"), ""]
    for a in r["arms"]:
        s = a.get("responses")
        if s is None:
            continue
        for tc in r["task_cells"]:
            h, n = s["fact_value_in_replies"][tc], s["at_need"][tc]
            q = n["reply_chars_quartiles"]
            lines.append(f"- {a['arm']}, {tc}: "
                         f"{_share([h['replies_holding_value'], h['replies']])}; "
                         f"{n['retained_replies_median']} replies, "
                         f"{q[1] if len(q) == 3 else 'n/a'} characters.")
    lines += ["", ("**The leak check** (the fact's value in the need step's first request: in the "
                   "system prompt, in earlier user messages, in its option line, elsewhere in the "
                   "need observation; clue values outside the replies):"), ""]
    for a in r["arms"]:
        s = a.get("responses")
        if s is None:
            continue
        for tc in r["task_cells"]:
            lines.append(f"- {a['arm']}, {tc}: {s['leak_check'][tc]}")
    lines += ["", "User messages at a common episode and step, against R9's: " + "; ".join(
        f"{name} {v['identical']} of {v['common']} identical"
        for name, v in r["user_messages_against_r9"].items()) + ".",
              "", "**Cost per episode** (billed estimate, USD; output tokens):", "",
              "| Arm | Task cell | Episodes | Cost per episode | Output tokens per episode |",
              "|---|---|---|---|---|"]
    for a in r["arms"]:
        for tc, c in a["costs"].items():
            cost, out = c["cost_usd_billed_mean"], c["output_tokens_mean"]
            lines.append(f"| {a['arm']} | {tc} | {c['n']} | "
                         f"{'n/a' if cost is None else f'{cost:.5f}'} | "
                         f"{'n/a' if out is None else f'{out:.0f}'} |")
    lines += ["", "**Run conditions:**", "",
              ("| Arm | Run | Ending | Started | Parallel | Uncached input tokens a minute | "
               "Model strings | Geos |"), "|---|---|---|---|---|---|---|---|"]
    for a in r["arms"]:
        for c in a["conditions"]:
            rate = c["uncached_per_minute"]
            lines.append(f"| {a['arm']} | {c['run_id']} | {c['exit_reason']} | {c['started_utc']} | "
                         f"{c['max_in_flight']} | {rate:,.0f} | "
                         f"{', '.join(c['model_returned'])} | {c['inference_geos']} |")
    lines += ["", "**Organization** (`harnesses org-check`):", ""]
    lines += [f"- {o['checked_utc']}: same as R10's {o['same_org_as_r10']}, same as R8's "
              f"{o['same_org_as_r8']}." for o in r["org_checks"]] or ["- no result committed."]
    lines += ["", "**Exclusions** (the control, per task cell, repeat 0; §13):", ""]
    for e in r["exclusions"]:
        rest = {x: v for x, v in e.items() if x not in ("kind", "cell", "variant", "task_cell")
                and v not in (0, None, {}, [])}
        lines.append(f"- {e['cell']}, {e.get('task_cell')}: {rest or 'none'}")
    for x in r["incomplete"]:
        lines.append(f"- incomplete: {x}")
    for x in r["deviations"]:
        lines.append(f"- deviation: {x}")
    for w in r["warnings"]:
        lines.append(f"- warning: {w}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results-root", type=Path, default=REPO_ROOT)
    ap.add_argument("--rerun", action="append", default=[], metavar="RUN=ORIGINAL")
    ap.add_argument("--sweep-closed", action="store_true")
    ap.add_argument("--allow-incomplete", action="store_true")
    ap.add_argument("--raw-root", type=Path, default=None)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--out-dir", type=Path, default=None)
    a = ap.parse_args(argv)
    now = datetime.now(UTC)
    r = readings(a.results_root, hn._links(a.rerun), a.sweep_closed, raw_root=a.raw_root,
                 allow_incomplete=a.allow_incomplete)
    text = summary(r)
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    if a.no_write:
        return 0
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    out = a.out_dir or a.results_root / "results" / "haiku_control" / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "control.json").write_text(json.dumps(r, indent=2, default=str), encoding="utf-8",
                                      newline="\n")
    (out / "summary.md").write_text(text, encoding="utf-8", newline="\n")
    runmeta.write_meta(
        out, git=runmeta.git_state(), experiment="haiku_control", run_id=run_id,
        cell_or_config=CELL, config={"experiment": EXPERIMENT, "rerun_links": r["rerun_links"],
                                     "sweep_closed": a.sweep_closed,
                                     "allow_incomplete": a.allow_incomplete,
                                     "status": r["status"], "templates_read": r["templates_read"],
                                     "r9_output": hp.R9_OUTPUT, "r10_output": R10_OUTPUT},
        model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
        repeat_index=0, seeds={"bootstrap": r["bootstrap"]["seed"]},
        started_utc=now.isoformat(timespec="seconds"), finished_utc=runmeta.utc_now(),
        exit_reason="completed", tokens=None, cost_usd=0.0, raw_transcript_path=None,
        outputs=list(OUTPUTS), paid_calls=0, runs=[x["run_id"] for x in r["runs"]])
    print(f"written: {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
