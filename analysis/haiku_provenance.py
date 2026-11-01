"""R10's descriptive analysis: claude-haiku-5-5's two notes-instruction variants (PREREG §17.10; $0, no test).

R10 registers two exploratory cells, run on Haiku in their own experiment
`persistgym_haiku_provenance` on the 4 far task cells, main templates 0-199 at repeat 0:
W-np-0, W-n-0 with a sentence asking for each carried fact's source (`PROVENANCE_SENTENCE`),
and W-npd-0, which also says that older messages may be dropped (`DISCLOSURE_SENTENCE`). Its
analysis is descriptive. This script reads the runs' counted records as `analysis.haiku_notes`
reads R9's (discovery, re-run links and §7.8's first-final-record rule through
`persistgym_h1h3.resolve`, R8's request-check stops, no echo exclusion), and R9's W-n-0 run as
its cited output counted it (`R9_OUTPUT`), on the same far episodes. It reports:

1. **Success per arm and far task cell,** with a 90% template-cluster bootstrap interval:
   10,000 resamples of the templates with §9.1's seed (SEED + 10), the resamples of R8's and
   R9's analyses. Refusals and empty replies score 0 at the need step (R8), and each cell's
   step responses that stopped short are counted by reason.
2. **§2.8's accounting** per arm and far task cell (`persistgym_h1h3.accounting`): S verbatim,
   P(carried) (a lower bound: the string match misses paraphrase), success given carried, and
   success among the rest.
3. **Choices with the fact evicted:** in the 2 not-recoverable far cells, the episodes that
   chose one of the 10 options at the need step, and how many were correct.
4. **Contrasts,** in percentage points with a 90% interval over the same template resamples,
   per far task cell: each arm minus R9's W-n-0, and W-npd-0 minus W-np-0. R9 ran about a week
   earlier (2026-10-24), so arm minus W-n-0 mixes the instruction with any change in serving.
5. **Replies** in the 2 not-recoverable far cells, by whether the notes carried the fact, with
   `analysis.haiku_notes_replies`'s text patterns unchanged (`DISOWN`, `episode_reading`,
   `tally`): failed episodes that declined, whose need-step reply disowns an earlier figure,
   and that retracted it before the need step. The patterns undercount (R9's hand checks), so
   these are pointers, set beside R9's pattern counts from the same code (`R9_REPLIES`).
6. **Cost per episode** (billed estimate) and output tokens per episode, per arm and far task
   cell, beside R9's W-n-0 on the same cells.
7. **Model strings:** those the arms' runs report, against R9's run.

Nothing here is a test. It ranks nothing, and differences are described, not tested. Success
differences between the arms and W-n-0 can come from answering policy as well as from carried
notes: P(carried) and success given carried separate the two only as far as the lower bound
allows.

**Before any reading,** as `analysis.haiku_notes` does:
- the repeat-0 sweep of both arms must be complete on the far task cells
  (`persistgym_h1h3.completeness`), or closed with ``--sweep-closed``. Otherwise the script
  refuses, unless ``--allow-incomplete`` is passed, and the output is then PROVISIONAL;
- every record of the arms' runs must be on a far task cell;
- §2.8's accounting check (`persistgym_h1h3.accounting_check`), with each cell's notes text
  taken off the system prompt as the session leaves it out of W, on the raw transcripts under
  ``--raw-root`` (default ``results/raw``). A bug stops the analysis (`AccountingBug`). Missing
  transcripts refuse likewise (reading 5 needs them too), or make the output PROVISIONAL with
  ``--allow-incomplete``;
- the per-cell exclusion counts (`persistgym_h1h3.exclusion_table`) are reported.

Run: ``uv run python -m analysis.haiku_provenance [--rerun RUN=ORIGINAL ...] [--sweep-closed]``.
It writes ``results/haiku_provenance/<UTC>/provenance.json``, ``summary.md`` and ``meta.json``.
With ``--no-write`` it only prints. ``--experiment`` and ``--cells`` read other Haiku cells with
the same code (the tests read R9's W-n-0 run, whose readings are known).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from analysis import haiku_notes as hn
from analysis import haiku_notes_replies as hnr
from analysis import persistgym_h1h3 as hh
from common import runmeta
from harnesses import registered

REPO_ROOT = Path(__file__).resolve().parent.parent
R9_OUTPUT = "results/haiku_notes/20261024T073307Z"
"""R9's cited readings (FINAL): its meta.json lists the run and re-run links that it counted."""
R9_REPLIES = "results/haiku_notes_replies/20261024T234538Z/replies.json"
"""R9's text-pattern reading of the same replies, with the same patterns."""
R9_EXPERIMENT, R9_CELL = registered.HAIKU_NOTES_EXPERIMENT, registered.HAIKU_NOTES_CELL
FAR = registered.HAIKU_PROVENANCE_TASK_CELLS
NR_FAR = hn.NR_FAR
BOOT = hn.BOOT
OUTPUTS = ("provenance.json", "summary.md", "meta.json")


def read(root: Path, experiment: str, cells: tuple[str, ...], links: dict[str, str],
         sweep_closed: bool, declared: list[str] | None = None) -> tuple[list, dict, list[str]]:
    """The runs, every key's resolution and the warnings, for Haiku's `cells` in
    `experiment` (only the runs in `declared` when given)."""
    prof = replace(hh.profile(registered.HAIKU_MODEL), experiment=experiment,
                   cells=tuple(dict.fromkeys((*registered.HAIKU_CELLS, *cells))))
    runs, skipped = hh.discover(root / "results", declared=declared, prof=prof)
    if skipped and declared is None:
        raise SystemExit(f"runs skipped under {experiment}: {skipped}")
    runs = [r for r in runs if r.cell in cells]
    if not runs:
        raise hh.Refusal(f"no run of {', '.join(cells)} under results/{experiment}/")
    resolved, warn = hh.resolve(runs, links, sweep_closed=sweep_closed, echo=False,
                                stopped=hh.request_check_stops(runs))
    return runs, resolved, warn


def r9_read(root: Path) -> tuple[list, dict]:
    """R9's W-n-0 run and resolution, as its cited output counted them."""
    meta = json.loads((root / R9_OUTPUT / "meta.json").read_text(encoding="utf-8"))
    runs, resolved, _ = read(root, R9_EXPERIMENT, (R9_CELL,),
                             dict(meta["config"]["rerun_links"]),
                             bool(meta["config"]["sweep_closed"]), declared=list(meta["runs"]))
    return runs, resolved


def _counted(resolved: dict, cell: str, T: int, task_cells=FAR) -> list:
    return [r for r in resolved.values()
            if r.status == "counted" and r.record is not None and r.key[0] == cell
            and r.key[2] == 0 and r.record["task_cell"] in task_cells
            and (r.record.get("variant") or hh.BASE) == hh.BASE
            and hh.template_index(r.record["template_id"]) < T]


def replies(resolved: dict, cell: str, T: int, raw: Path,
            experiment: str) -> tuple[dict | None, list[str]]:
    """Reading 5 for one cell: `haiku_notes_replies`'s pattern tally over its counted NR-far
    episodes, each read from the transcript of the run that holds its counted record, and the
    runs holding such records whose transcript is missing. The tally is None when any is."""
    by_run: dict[str, dict[str, dict]] = {}
    for r in _counted(resolved, cell, T, NR_FAR):
        by_run.setdefault(r.run_id, {})[r.record["episode_id"]] = r.record
    missing = sorted(run_id for run_id in by_run
                     if not (raw / experiment / run_id / "transcript.jsonl.gz").is_file())
    if missing:
        return None, missing
    rows = []
    for run_id, recs in sorted(by_run.items()):
        trails = hnr.steps(raw, set(recs), path=raw / experiment / run_id / "transcript.jsonl.gz")
        rows += [hnr.episode_reading(rec, trails[eid]) for eid, rec in sorted(recs.items())]
    return hnr.tally(rows), []


def _mean(values: list) -> tuple[float | None, int]:
    """The mean of `values` and how many are missing (None); the mean is None when any is,
    so a missing value never counts as 0."""
    missing = sum(v is None for v in values)
    if missing or not values:
        return None, missing
    return sum(float(v) for v in values) / len(values), 0


def costs_per_episode(resolved: dict, cell: str, T: int) -> dict:
    """Reading 6: mean billed cost and mean output tokens per counted episode, by far task
    cell, with the number of records missing each (a returned model string the price table
    does not know leaves the cost missing)."""
    out = {}
    for tc in FAR:
        recs = [r.record for r in _counted(resolved, cell, T, (tc,))]
        cost, cost_missing = _mean([x.get("cost_usd_billed_est") for x in recs])
        tokens, tokens_missing = _mean([(x.get("usage") or {}).get("output_tokens")
                                        for x in recs])
        out[tc] = {"n": len(recs), "cost_usd_billed_mean": cost, "cost_missing": cost_missing,
                   "output_tokens_mean": tokens, "output_tokens_missing": tokens_missing}
    return out


def choices(resolved: dict, cell: str, T: int) -> dict:
    """Reading 3 for one cell."""
    out = {}
    for tc in NR_FAR:
        recs = [r.record for r in _counted(resolved, cell, T, (tc,))]
        chose = [x for x in recs if x.get("need_label") not in (None, "")]
        out[tc] = {"episodes": len(recs), "chose_an_option": len(chose),
                   "correct": sum(bool(x.get("need_correct")) for x in chose)}
    return out


def arm(resolved: dict, prim, cell: str, T: int, idx: np.ndarray) -> dict:
    """Readings 1-3 and 6 for one cell."""
    sub = prim[prim.cell == cell]
    cells = hh.cell_table(sub, kinds=((cell, hh.BASE),), stopped=True, task_cells=FAR)
    for row in cells:
        s = np.full(T, np.nan)
        t = sub[sub.task_cell == row["task_cell"]]
        s[t.template.to_numpy()] = t.success.to_numpy()
        row["interval_90"] = hn.interval(s, idx)
    return {"cell": cell, "counted_repeat_0": len(sub), "cells": cells,
            "accounting": hh.accounting(sub, cells=(cell,), task_cells=FAR),
            "choices_nr_far": choices(resolved, cell, T),
            "costs": costs_per_episode(resolved, cell, T)}


def contrasts(resolved: dict, r9_resolved: dict, cells: tuple[str, ...], T: int,
              idx: np.ndarray) -> dict:
    """Reading 4: each arm minus R9's W-n-0, and the second arm minus the first, per far task
    cell (`haiku_notes.contrast`: the same template resamples for both sides)."""
    out = {}
    ref = {tc: hn.by_template(r9_resolved, R9_CELL, tc, T) for tc in FAR}
    mine = {(c, tc): hn.by_template(resolved, c, tc, T) for c in cells for tc in FAR}
    for c in cells:
        out[f"{c} - {R9_CELL} (R9)"] = {tc: hn.contrast(mine[c, tc], ref[tc], idx) for tc in FAR}
    if len(cells) == 2:
        a, b = cells
        out[f"{b} - {a}"] = {tc: hn.contrast(mine[b, tc], mine[a, tc], idx) for tc in FAR}
    return out


def readings(root: Path, experiment: str, cells: tuple[str, ...], links: dict[str, str],
             sweep_closed: bool, *, raw_root: Path | None = None,
             allow_incomplete: bool = False) -> dict:
    runs, resolved, warn = read(root, experiment, cells, links, sweep_closed)
    T = registered.HAIKU_T
    kinds = tuple((c, hh.BASE) for c in cells)
    if experiment == registered.HAIKU_PROVENANCE_EXPERIMENT:
        off = sorted({rec["task_cell"] for run in runs for rec in run.records} - set(FAR))
        if off:
            raise hh.Refusal(f"R10's runs play the far task cells only, but records hold "
                             f"{', '.join(off)}")
    incomplete, deviations = hh.completeness(resolved, T, sweep_closed, kinds, task_cells=FAR)
    if incomplete and not allow_incomplete:
        raise hh.Refusal("the repeat-0 sweep is incomplete:\n" + "\n".join(
            f"  - {x}" for x in incomplete) + "\nWait for the runs (a transport failure needs "
            "its §13 re-run), pass --sweep-closed once the researcher has closed the sweep, or "
            "pass --allow-incomplete to see what exists (PROVISIONAL).")
    raw = raw_root or root / "results" / "raw"
    check = hh.accounting_check(runs, raw, experiment, hh.MESSAGES_API)
    if check["bugs"]:
        raise hh.AccountingBug(
            "PREREG §2.8's bug stop: window-accounting bug(s), so no result is reported until "
            "they are found:\n" + "\n".join(f"  - {b}" for b in check["bugs"]))
    if check["missing_transcripts"]:
        incomplete.append("no raw transcript for run(s) "
                          + ", ".join(check["missing_transcripts"])
                          + f" under {raw}: §2.8's replay and the replies reading cannot be "
                          "made")
        if not allow_incomplete:
            raise hh.Refusal(incomplete[-1] + "\nPass --raw-root, or --allow-incomplete "
                             "(PROVISIONAL).")
    table, warn2 = hh.episode_table(resolved, api=hh.MESSAGES_API)
    prim = table[(table.repeat == 0) & (table.status == "counted") & table.cell.isin(cells)
                 & (table.variant == hh.BASE) & (table.template < T)
                 & table.task_cell.isin(FAR)].reset_index(drop=True)
    seed, _ = hh.read_seed(root / "results")
    boot_seed = seed + hh.BOOT_SEED_OFFSET  # §9.1's bootstrap seed, as for R8's and R9's
    idx = hh.resample_indices(T, boot_seed, BOOT)
    r9_runs, r9_resolved = r9_read(root)
    r9_table, _ = hh.episode_table(r9_resolved, api=hh.MESSAGES_API)
    r9_prim = r9_table[(r9_table.repeat == 0) & (r9_table.status == "counted")
                       & (r9_table.cell == R9_CELL) & (r9_table.variant == hh.BASE)
                       & (r9_table.template < T)
                       & r9_table.task_cell.isin(FAR)].reset_index(drop=True)
    r9_replies = json.loads((root / R9_REPLIES).read_text(encoding="utf-8"))["tally"]
    arms = []
    for c in cells:
        a = arm(resolved, prim, c, T, idx)
        a["replies_nr_far"], missing = replies(resolved, c, T, raw, experiment)
        if missing and not check["missing_transcripts"]:
            incomplete.append(f"no raw transcript for run(s) {', '.join(missing)} under {raw}, "
                              f"which hold counted not-recoverable far records of {c}: the "
                              "replies reading cannot be made")
            if not allow_incomplete:
                raise hh.Refusal(incomplete[-1] + "\nPass --raw-root, or --allow-incomplete "
                                 "(PROVISIONAL).")
        arms.append(a)
    pending = sorted(f"{k[0]} {k[1]} r{k[2]}" for k, r in resolved.items()
                     if r.status != "counted" and r.record is None)
    models = {"arms": sorted({str(m) for run in runs for m in run.model_returned}),
              "r9": sorted({str(m) for run in r9_runs for m in run.model_returned})}
    return {"experiment": experiment, "cells": list(cells), "model": registered.HAIKU_MODEL,
            "prereg": registered.R10_REF, "T": T, "task_cells": list(FAR),
            "status": hh.PROVISIONAL if incomplete else hh.FINAL,
            "incomplete": incomplete, "deviations": deviations,
            "accounting_check": {"checked": check["checked"], "bugs": check["bugs"],
                                 "missing_transcripts": check["missing_transcripts"]},
            "exclusions": hh.exclusion_table(resolved, T, kinds=kinds, echo=False,
                                             task_cells=FAR),
            "bootstrap": {"resamples": BOOT, "seed": boot_seed,
                          "interval": "90% percentile, template-cluster"},
            "runs": [hh.run_row(r, resolved) for r in runs],
            "rerun_links": links, "sweep_closed": sweep_closed, "not_counted": pending,
            "arms": arms,
            "r9": {"output": R9_OUTPUT, "runs": [r.run_id for r in r9_runs],
                   **arm(r9_resolved, r9_prim, R9_CELL, T, idx),
                   "replies_nr_far": r9_replies, "replies_source": R9_REPLIES},
            "contrasts": contrasts(resolved, r9_resolved, cells, T, idx),
            "model_strings": models, "warnings": [*warn, *warn2, *check["warnings"]]}


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _frac(k: int | None, n: int | None) -> str:
    return "n/a" if not n else f"{k}/{n} ({_pct(k / n)})"


def _frac_rate(d: dict | None) -> str:
    return "n/a" if not d or d.get("rate") is None else _frac(d["successes"], d["n"])


def _pp(v: dict) -> str:
    return ("n/a" if v["pp"] is None else
            f"{v['pp']:+.1f} pp [{v['ci90'][0]:+.1f}, {v['ci90'][1]:+.1f}]")


def summary(r: dict) -> str:
    blocks = [*r["arms"], {**r["r9"], "cell": f"{R9_CELL} (R9, {r['r9']['output']})"}]
    lines = [f"# {r['model']}: R10's notes-instruction variants ({r['experiment']})", "",
             (f"**{r['status']}.** {r['prereg']}. Exploratory: no test, no label. Repeat 0, "
              f"the 4 far task cells, main templates 0-{r['T'] - 1}. Not a model comparison. "
              f"§2.8's accounting check: {r['accounting_check']['checked']} need steps "
              f"replayed, {len(r['accounting_check']['bugs'])} bugs. R9's W-n-0 ran on "
              "2026-10-24, so differences from it mix the instruction with any change in "
              "serving."), "",
             "| Arm | Task cell | Success | 90% interval | Refused episodes | Stopped responses |",
             "|---|---|---|---|---|---|"]
    for b in blocks:
        for c in b["cells"]:
            iv = c.get("interval_90")
            lines.append(f"| {b['cell']} | {c['task_cell']} | {c['successes']}/{c['n']} "
                         f"({_pct(c['rate'])}) | "
                         f"{'n/a' if iv is None else f'{_pct(iv[0])} to {_pct(iv[1])}'} | "
                         f"{c.get('episodes_with_a_refusal', 0)} | "
                         f"{c.get('stopped_responses') or '-'} |")
    lines += ["", "**§2.8 accounting** (P(carried) is a lower bound):", "",
              ("| Arm | Task cell | S verbatim 0 | P(carried) | Used given carried | "
               "Not carried: success, no lookup | Not carried: success, lookup |"),
              "|---|---|---|---|---|---|---|"]
    for b in blocks:
        for a in b["accounting"]:
            pc = a.get("P_carried") or {}
            lines.append(f"| {b['cell']} | {a['task_cell']} | {a['S_verbatim_0']} | "
                         f"{_frac(pc.get('carried'), pc.get('n'))} | "
                         f"{_frac_rate(a.get('used_given_carried'))} | "
                         f"{_frac_rate(a.get('rescued_without_lookup'))} | "
                         f"{_frac_rate(a.get('rescued_with_lookup'))} |")
    lines += ["", "**Choices with the fact evicted** (not-recoverable far cells):", ""]
    for b in blocks:
        for tc, c in b["choices_nr_far"].items():
            lines.append(f"- {b['cell']}, {tc}: chose an option in {c['chose_an_option']} of "
                         f"{c['episodes']}, {c['correct']} correct.")
    lines += ["", ("**Contrasts** (percentage points, 90% interval over the same template "
                   "resamples; described, not tested):"), ""]
    for name, by_tc in r["contrasts"].items():
        for tc, v in by_tc.items():
            lines.append(f"- {name}, {tc}: {_pp(v)}")
    lines += ["", ("**Replies** (not-recoverable far cells; R9's text patterns, which "
                   "undercount; pointers, not a coding):"), "",
              ("| Arm | Cell, notes carried the fact | Episodes | Correct | Failed | "
               "Failed: declined | Failed: need reply disowns its figure | "
               "Failed: retracted before the need step |"),
              "|---|---|---|---|---|---|---|---|"]
    for b in blocks:
        t = b.get("replies_nr_far")
        if t is None:
            lines.append(f"| {b['cell']} | (no transcripts) | | | | | | |")
            continue
        for k, v in t.items():
            lines.append(f"| {b['cell']} | {k} | {v['episodes']} | {v['correct']} | "
                         f"{v['failed']} | {v['failed_declined']} | "
                         f"{v['failed_need_reply_disowns']} | "
                         f"{v['failed_retracted_before_need']} |")
    lines += ["", "**Cost per episode** (billed estimate, USD; output tokens):", "",
              "| Arm | Task cell | Episodes | Cost per episode | Output tokens per episode |",
              "|---|---|---|---|---|"]
    for b in blocks:
        for tc, c in b["costs"].items():
            cost, out = c["cost_usd_billed_mean"], c["output_tokens_mean"]
            gone = {k: c.get(k) for k in ("cost_missing", "output_tokens_missing") if c.get(k)}
            lines.append(f"| {b['cell']} | {tc} | {c['n']} | "
                         f"{'n/a' if cost is None else f'{cost:.5f}'} | "
                         f"{'n/a' if out is None else f'{out:.0f}'} |"
                         + (f" missing: {gone}" if gone else ""))
    ms = r["model_strings"]
    lines += ["", f"Model strings: the arms {ms['arms']}, R9's run {ms['r9']}."]
    lines += ["", "**Exclusions** (per arm and task cell, repeat 0; §13):", ""]
    for e in r["exclusions"]:
        rest = {k: v for k, v in e.items() if k not in ("kind", "cell", "variant", "task_cell")
                and v not in (0, None, {}, [])}
        lines.append(f"- {e['cell']}, {e.get('task_cell')}: {rest or 'none'}")
    for x in r["incomplete"]:
        lines.append(f"- incomplete: {x}")
    for x in r["deviations"]:
        lines.append(f"- deviation: {x}")
    if r["not_counted"]:
        lines += ["", f"Keys not counted (pending or excluded): {len(r['not_counted'])}."]
    for w in r["warnings"]:
        lines.append(f"- warning: {w}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results-root", type=Path, default=REPO_ROOT)
    ap.add_argument("--experiment", default=registered.HAIKU_PROVENANCE_EXPERIMENT)
    ap.add_argument("--cells", nargs="+", default=list(registered.HAIKU_PROVENANCE_CELLS))
    ap.add_argument("--rerun", action="append", default=[], metavar="RUN=ORIGINAL")
    ap.add_argument("--sweep-closed", action="store_true")
    ap.add_argument("--allow-incomplete", action="store_true")
    ap.add_argument("--raw-root", type=Path, default=None)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--out-dir", type=Path, default=None)
    a = ap.parse_args(argv)
    now = datetime.now(UTC)
    cells = tuple(a.cells)
    r = readings(a.results_root, a.experiment, cells, hn._links(a.rerun), a.sweep_closed,
                 raw_root=a.raw_root, allow_incomplete=a.allow_incomplete)
    text = summary(r)
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    if a.no_write:
        return 0
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    out = a.out_dir or a.results_root / "results" / "haiku_provenance" / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "provenance.json").write_text(json.dumps(r, indent=2, default=str),
                                         encoding="utf-8", newline="\n")
    (out / "summary.md").write_text(text, encoding="utf-8", newline="\n")
    runmeta.write_meta(
        out, git=runmeta.git_state(), experiment="haiku_provenance", run_id=run_id,
        cell_or_config=",".join(cells), config={"experiment": a.experiment, "cells": list(cells),
                                                "rerun_links": r["rerun_links"],
                                                "sweep_closed": a.sweep_closed,
                                                "allow_incomplete": a.allow_incomplete,
                                                "status": r["status"], "r9_output": R9_OUTPUT},
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
