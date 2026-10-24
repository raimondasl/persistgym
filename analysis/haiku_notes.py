"""R9's descriptive analysis: claude-haiku-5-5's exploratory W-n-0 run (PREREG §17.9; $0, no test).

R9 registers one exploratory run of Haiku in W-n-0, the notes cell R8's size rule dropped, in
its own experiment `persistgym_haiku_notes`. Its analysis is descriptive. This script reads the
run's counted records exactly as `analysis.persistgym_h1h3` reads Haiku's (discovery, re-run
links and §7.8's first-final-record rule through `persistgym_h1h3.resolve`, R8's request-check
stops, no echo exclusion), at repeat 0, and reports:

1. **Success per task cell,** with a 90% template-cluster bootstrap interval: 10,000 resamples
   of the templates, drawn by `persistgym_h1h3.resample_indices` with §9.1's seed (SEED + 10,
   SEED from the committed draw, as for luna's and R8's analyses), the
   percentile interval of each cell's success rate. Refusals and empty replies score 0 at the
   need step (R8), and each cell's step responses that stopped short are counted by reason.
2. **§2.8's accounting** per task cell, `persistgym_h1h3.accounting` as for luna's W-n-0: S
   verbatim, the share of episodes whose notes carried the fact at the need step (P(carried), a
   lower bound: the string match misses paraphrase), success among those (used given carried),
   and success among the rest.
3. **Choices with the fact evicted:** in the 2 not-recoverable far cells, the episodes that chose
   one of the 10 options at the need step (`need_label` set) and how many were correct, as
   `analysis.replication_readings` reports for Haiku's W-0.
4. **Within Haiku, against R8's runs,** as luna's W-n-0 was reported (§3 H1, "alongside"): the
   cell's penalty against Haiku's F-0 on the observed far cells, not recoverable (NR) and
   recoverable (R), their difference, and the cell's lift over Haiku's W-0 in NR, all in
   percentage points on the same templates at repeat 0, with the same template resamples. R8's
   records are those its cited analysis output counted (`R8_OUTPUT`: its run list and re-run
   links), read as `analysis.replication_readings` reads them.
5. **Model strings:** the strings the cell's runs and R8's runs report, to compare.

The answering policy matters for reading these: in W-0, Haiku chose no option once the fact was
evicted (0 of 400), where luna guessed. So success here is not comparable with luna's.
P(carried) and success given carried do not depend on answering policy, but P(carried) is a
lower bound whose gap can differ between the models (paraphrase is not measured). They are
described side by side, never compared.

**Before any reading,** as `analysis.persistgym_h1h3` does for R8 (R8's "Exclusions and errors";
§13, §2.8):
- the repeat-0 sweep must be complete (`persistgym_h1h3.completeness`), or closed with
  ``--sweep-closed``. Otherwise the script refuses, unless ``--allow-incomplete`` is passed,
  and the output is then PROVISIONAL;
- §2.8's accounting check (`persistgym_h1h3.accounting_check`): condition 1 on the records,
  and condition 2's drop-oldest replay from the raw transcripts under ``--raw-root``
  (default ``results/raw``). A bug stops the analysis (`AccountingBug`). Missing transcripts
  refuse likewise, or make the output PROVISIONAL with ``--allow-incomplete``;
- the per-cell exclusion counts (`persistgym_h1h3.exclusion_table`) are reported.

Nothing here is a test. It ranks nothing, and differences from luna's W-n-0 are described, not
tested. Apart from the replay of §2.8, which reads the raw transcripts' message lengths as the
H1/H3 analysis does, it reads committed run folders only (meta.json, episodes.jsonl).

Run: ``uv run python -m analysis.haiku_notes [--rerun RUN=ORIGINAL ...] [--sweep-closed]``. It
writes ``results/haiku_notes/<UTC>/notes.json``, ``summary.md`` and ``meta.json``. With
``--no-write`` it only prints. ``--experiment`` and ``--cell`` read another Haiku experiment and cell with the
same code (the tests read R8's W-0 runs, whose readings are known).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from analysis import persistgym_h1h3 as hh
from common import runmeta
from harnesses import registered

REPO_ROOT = Path(__file__).resolve().parent.parent
R8_OUTPUT = "results/persistgym_h1h3_haiku/20261019T003254Z"
"""R8's cited analysis output (FINAL, the preprint's): its meta.json lists the runs and re-run
links that it counted."""
NR_FAR = ("observed-nonrec-far", "derived-nonrec-far")
OBS_NR_FAR, OBS_R_FAR = "observed-nonrec-far", "observed-rec-far"
BOOT = 10_000
OUTPUTS = ("notes.json", "summary.md", "meta.json")


def counted(root: Path, experiment: str, cell: str, links: dict[str, str],
            sweep_closed: bool) -> tuple[list, dict, list[str]]:
    """The runs, every key's resolution and the warnings, for Haiku's `cell` in `experiment`."""
    # discovery accepts R8's main-run cells and `cell`. Only `cell`'s records are read.
    cells = tuple(dict.fromkeys((*registered.HAIKU_CELLS, cell)))
    prof = replace(hh.profile(registered.HAIKU_MODEL), experiment=experiment, cells=cells)
    runs, skipped = hh.discover(root / "results", prof=prof)
    if skipped:
        raise SystemExit(f"runs skipped under {experiment}: {skipped}")
    if not runs:
        raise SystemExit(f"no {cell} run under results/{experiment}/")
    resolved, warn = hh.resolve(runs, links, sweep_closed=sweep_closed, echo=False,
                                stopped=hh.request_check_stops(runs))
    return runs, resolved, warn


def r8_counted(root: Path) -> tuple[list, dict]:
    """R8's runs and resolution, as its cited output counted them."""
    meta = json.loads((root / R8_OUTPUT / "meta.json").read_text(encoding="utf-8"))
    inputs = meta["config"]["inputs"]
    runs, skipped = hh.discover(root / "results", declared=list(inputs["input_list"]),
                                prof=hh.profile(registered.HAIKU_MODEL))
    if skipped:
        raise SystemExit(f"R8 runs skipped: {skipped}")
    resolved, _ = hh.resolve(runs, dict(inputs["rerun_links"]), sweep_closed=True, echo=False,
                             stopped=hh.request_check_stops(runs))
    return runs, resolved


def by_template(resolved: dict, cell: str, task_cell: str, T: int) -> np.ndarray:
    """Success by template index (NaN where no counted repeat-0 base episode) of one cell."""
    s = np.full(T, np.nan)
    for r in resolved.values():
        rec = r.record
        if (r.status != "counted" or rec is None or r.key[0] != cell or r.key[2] != 0
                or rec["task_cell"] != task_cell or (rec.get("variant") or hh.BASE) != hh.BASE):
            continue
        t = hh.template_index(rec["template_id"])
        if t < T:
            s[t] = float(bool(rec.get("need_correct")))
    return s


def contrast(a: np.ndarray, b: np.ndarray, idx: np.ndarray) -> dict:
    """mean(a) - mean(b) in percentage points, with its 90% percentile interval over the
    template resamples `idx`, the same resamples for both sides. Each side's mean is over its
    own templates with a counted episode, as in R8's analysis."""
    if np.all(np.isnan(a)) or np.all(np.isnan(b)):
        return {"pp": None, "ci90": None}
    point = 100 * (np.nanmean(a) - np.nanmean(b))
    d = 100 * (np.nanmean(a[idx], axis=1) - np.nanmean(b[idx], axis=1))
    return {"pp": float(point),
            "ci90": [float(np.nanpercentile(d, 5)), float(np.nanpercentile(d, 95))]}


def within_haiku(resolved: dict, r8_resolved: dict, cell: str, T: int, idx: np.ndarray) -> dict:
    """The cell against R8's F-0 and W-0 (item 4)."""
    f = {tc: by_template(r8_resolved, "F-0", tc, T) for tc in (OBS_NR_FAR, OBS_R_FAR)}
    w = {tc: by_template(r8_resolved, "W-0", tc, T) for tc in (OBS_NR_FAR, OBS_R_FAR)}
    c = {tc: by_template(resolved, cell, tc, T) for tc in (OBS_NR_FAR, OBS_R_FAR)}
    pen_nr = contrast(f[OBS_NR_FAR], c[OBS_NR_FAR], idx)
    pen_r = contrast(f[OBS_R_FAR], c[OBS_R_FAR], idx)
    diff = {"pp": None, "ci90": None}
    if pen_nr["pp"] is not None and pen_r["pp"] is not None:
        d = (100 * (np.nanmean(f[OBS_NR_FAR][idx], axis=1) - np.nanmean(c[OBS_NR_FAR][idx], axis=1))
             - 100 * (np.nanmean(f[OBS_R_FAR][idx], axis=1) - np.nanmean(c[OBS_R_FAR][idx], axis=1)))
        diff = {"pp": pen_nr["pp"] - pen_r["pp"],
                "ci90": [float(np.nanpercentile(d, 5)), float(np.nanpercentile(d, 95))]}
    return {"penalty_against_f0_nr": pen_nr, "penalty_against_f0_r": pen_r,
            "difference": diff, "lift_over_w0_nr": contrast(c[OBS_NR_FAR], w[OBS_NR_FAR], idx),
            "note": "observed far cells, repeat 0, the same templates; described, not tested"}


def interval(success_by_template: np.ndarray, idx: np.ndarray) -> list[float] | None:
    """The 90% percentile interval of the success rate over template resamples `idx` (rows of
    template indices); templates with no counted episode (NaN) are left out of each mean."""
    if np.all(np.isnan(success_by_template)):
        return None
    means = np.nanmean(success_by_template[idx], axis=1)
    return [float(np.nanpercentile(means, 5)), float(np.nanpercentile(means, 95))]


def readings(root: Path, experiment: str, cell: str, links: dict[str, str],
             sweep_closed: bool, *, raw_root: Path | None = None,
             allow_incomplete: bool = False) -> dict:
    runs, resolved, warn = counted(root, experiment, cell, links, sweep_closed)
    T = registered.HAIKU_T
    kinds = ((cell, hh.BASE),)
    incomplete, deviations = hh.completeness(resolved, T, sweep_closed, kinds)
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
                          + f" under {raw}: §2.8's replay cannot be made")
        if not allow_incomplete:
            raise hh.Refusal(incomplete[-1] + "\nPass --raw-root, or --allow-incomplete "
                             "(PROVISIONAL).")
    table, warn2 = hh.episode_table(resolved, api=hh.MESSAGES_API)
    prim = table[(table.repeat == 0) & (table.status == "counted") & (table.cell == cell)
                 & (table.variant == hh.BASE) & (table.template < T)].reset_index(drop=True)
    seed, _ = hh.read_seed(root / "results")
    boot_seed = seed + hh.BOOT_SEED_OFFSET  # §9.1's bootstrap seed, as for luna's and R8's
    idx = hh.resample_indices(T, boot_seed, BOOT)
    cells = hh.cell_table(prim, kinds=((cell, hh.BASE),), stopped=True)
    for row in cells:
        sub = prim[prim.task_cell == row["task_cell"]]
        s = np.full(T, np.nan)
        s[sub.template.to_numpy()] = sub.success.to_numpy()
        row["interval_90"] = interval(s, idx)
    choices = {}
    for tc in NR_FAR:
        recs = [r.record for r in resolved.values()
                if r.status == "counted" and r.key[0] == cell and r.key[2] == 0
                and r.record is not None and r.record["task_cell"] == tc
                and (r.record.get("variant") or hh.BASE) == hh.BASE]
        chose = [r for r in recs if r.get("need_label") not in (None, "")]
        choices[tc] = {"episodes": len(recs), "chose_an_option": len(chose),
                       "correct": sum(bool(r.get("need_correct")) for r in chose)}
    pending = sorted(f"{k[0]} {k[1]} r{k[2]}" for k, r in resolved.items()
                     if r.status not in ("counted",) and r.record is None)
    r8_runs, r8_resolved = r8_counted(root)
    models = {"this_cell": sorted({str(m) for run in runs for m in run.model_returned}),
              "r8": sorted({str(m) for run in r8_runs for m in run.model_returned})}
    return {"experiment": experiment, "cell": cell, "model": registered.HAIKU_MODEL,
            "prereg": registered.R9_REF, "T": T,
            "status": hh.PROVISIONAL if incomplete else hh.FINAL,
            "incomplete": incomplete, "deviations": deviations,
            "accounting_check": {"checked": check["checked"], "bugs": check["bugs"],
                                 "missing_transcripts": check["missing_transcripts"]},
            "exclusions": hh.exclusion_table(resolved, T, kinds=kinds, echo=False),
            "bootstrap": {
                "resamples": BOOT, "seed": boot_seed,
                "interval": "90% percentile, template-cluster"},
            "runs": [hh.run_row(r, resolved) for r in runs],
            "rerun_links": links, "sweep_closed": sweep_closed,
            "counted_repeat_0": len(prim), "not_counted": pending,
            "cells": cells, "accounting": hh.accounting(prim, cells=(cell,)),
            "choices_nr_far": choices,
            "within_haiku": within_haiku(resolved, r8_resolved, cell, T, idx),
            "model_strings": models, "warnings": [*warn, *warn2, *check["warnings"]]}


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _frac(k: int | None, n: int | None) -> str:
    return "n/a" if not n else f"{k}/{n} ({_pct(k / n)})"


def _frac_rate(d: dict | None) -> str:
    return "n/a" if not d or d.get("rate") is None else _frac(d["successes"], d["n"])


def summary(r: dict) -> str:
    lines = [f"# {r['model']} {r['cell']} ({r['experiment']}): R9's descriptive readings",
             "",
             (f"**{r['status']}.** {r['prereg']}. Exploratory: no test, no label. Repeat 0, "
              f"{r['counted_repeat_0']} counted episodes. Not a model comparison. §2.8's "
              f"accounting check: {r['accounting_check']['checked']} need steps replayed, "
              f"{len(r['accounting_check']['bugs'])} bugs."),
             "",
             "| Task cell | Success | 90% interval | Refused episodes | Stopped responses |",
             "|---|---|---|---|---|"]
    for c in r["cells"]:
        iv = c.get("interval_90")
        lines.append(f"| {c['task_cell']} | {c['successes']}/{c['n']} ({_pct(c['rate'])}) | "
                     f"{'n/a' if iv is None else f'{_pct(iv[0])} to {_pct(iv[1])}'} | "
                     f"{c.get('episodes_with_a_refusal', 0)} | "
                     f"{c.get('stopped_responses') or '-'} |")
    lines += ["", "**§2.8 accounting** (P(carried) is a lower bound):", "",
              ("| Task cell | S verbatim 0 | Near losses | P(carried) | Used given carried | "
               "Not carried: success, no lookup | Not carried: success, lookup |"),
              "|---|---|---|---|---|---|---|"]
    for a in r["accounting"]:
        pc = a.get("P_carried") or {}
        near = a.get("near_losses")
        lines.append(f"| {a['task_cell']} | {a['S_verbatim_0']} | "
                     f"{'-' if near is None else near} | "
                     f"{_frac(pc.get('carried'), pc.get('n'))} | "
                     f"{_frac_rate(a.get('used_given_carried'))} | "
                     f"{_frac_rate(a.get('rescued_without_lookup'))} | "
                     f"{_frac_rate(a.get('rescued_with_lookup'))} |")
    lines += ["", "**Choices with the fact evicted** (not-recoverable far cells):", ""]
    for tc, c in r["choices_nr_far"].items():
        lines.append(f"- {tc}: chose an option in {c['chose_an_option']} of {c['episodes']}, "
                     f"{c['correct']} correct.")
    wh = r["within_haiku"]
    lines += ["", ("**Within Haiku, against R8's runs** (observed far cells, repeat 0, the "
                   "same templates; described, not tested):"), ""]
    for key, label in (("penalty_against_f0_nr", "penalty against F-0, not recoverable"),
                       ("penalty_against_f0_r", "penalty against F-0, recoverable"),
                       ("difference", "difference of the two penalties"),
                       ("lift_over_w0_nr", "lift over W-0, not recoverable")):
        v = wh[key]
        lines.append(f"- {label}: " + ("n/a" if v["pp"] is None else
                                       f"{v['pp']:+.1f} pp [{v['ci90'][0]:+.1f}, "
                                       f"{v['ci90'][1]:+.1f}]"))
    ms = r["model_strings"]
    lines += ["", f"Model strings: this cell {ms['this_cell']}, R8's runs {ms['r8']}."]
    lines += ["", "**Exclusions** (per task cell, repeat 0; §13):", ""]
    for e in r["exclusions"]:
        rest = {k: v for k, v in e.items() if k not in ("kind", "cell", "variant", "task_cell")
                and v not in (0, None, {}, [])}
        lines.append(f"- {e.get('task_cell')}: {rest or 'none'}")
    for x in r["incomplete"]:
        lines.append(f"- incomplete: {x}")
    for x in r["deviations"]:
        lines.append(f"- deviation: {x}")
    if r["not_counted"]:
        lines += ["", f"Keys not counted (pending or excluded): {len(r['not_counted'])}."]
    for w in r["warnings"]:
        lines.append(f"- warning: {w}")
    return "\n".join(lines) + "\n"


def _links(pairs: list[str]) -> dict[str, str]:
    out = {}
    for p in pairs:
        run, sep, orig = p.partition("=")
        if not sep or not run or not orig or run in out:
            raise SystemExit(f"--rerun {p!r}: give RUN=ORIGINAL, each run once")
        out[run] = orig
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results-root", type=Path, default=REPO_ROOT)
    ap.add_argument("--experiment", default=registered.HAIKU_NOTES_EXPERIMENT)
    ap.add_argument("--cell", default=registered.HAIKU_NOTES_CELL)
    ap.add_argument("--rerun", action="append", default=[], metavar="RUN=ORIGINAL")
    ap.add_argument("--sweep-closed", action="store_true")
    ap.add_argument("--allow-incomplete", action="store_true")
    ap.add_argument("--raw-root", type=Path, default=None)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--out-dir", type=Path, default=None)
    a = ap.parse_args(argv)
    now = datetime.now(UTC)
    r = readings(a.results_root, a.experiment, a.cell, _links(a.rerun), a.sweep_closed,
                 raw_root=a.raw_root, allow_incomplete=a.allow_incomplete)
    text = summary(r)
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    if a.no_write:
        return 0
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    out = a.out_dir or a.results_root / "results" / "haiku_notes" / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "notes.json").write_text(json.dumps(r, indent=2, default=str), encoding="utf-8",
                                    newline="\n")
    (out / "summary.md").write_text(text, encoding="utf-8", newline="\n")
    runmeta.write_meta(
        out, git=runmeta.git_state(), experiment="haiku_notes", run_id=run_id,
        cell_or_config=a.cell, config={"experiment": a.experiment, "cell": a.cell,
                                       "rerun_links": r["rerun_links"],
                                       "sweep_closed": a.sweep_closed,
                                       "allow_incomplete": a.allow_incomplete,
                                       "status": r["status"]},
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
