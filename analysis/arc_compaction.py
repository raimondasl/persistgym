"""An exploratory look at failures after a history compaction (PLAN §24, A9; PREREG §9.10).

Run: ``uv run python -m analysis.arc_compaction [--results-root DIR] [--raw-root DIR]
[--out-dir DIR] [--no-write]`` ($0: it reads files only). It writes
``<results root>/arc_compaction/<UTC>/compaction.json``, ``summary.md`` and ``meta.json``.

Exploratory: no test, no verdict; it enters no hypothesis, gate or kill rule (PLAN A9).

**Runs.** Each path game's counted S1, S2 and S4 run at replicate 1, found as H4 finds them
(``analysis.arc_h4.load``: D19 re-runs and R7 replacements replace what they replace). The runs
they replaced are read too and reported apart. S0 drops old turns and never compacts.

**Per run,** from ``<raw root>/arc_path/<run>/``, read from the checkout that holds
``results/raw/`` (gitignored):

* compactions: ``harness/compaction_*.json``, each with ``before_step`` S (the summary was made
  before step S, so step S is the first step after it);
* steps and levels: ``harness.log``'s "Saved step s" lines and its "count n, levels completed L"
  lines; a level is cleared at step s when L rises after step s was saved, and the level in play
  at step s is L + 1 as it stood before step s;
* unusable replies: ``harness.log``'s "Could not parse action from response" and "Unusable API
  response" lines, each one call with no usable action, counted against the step being tried
  (the last saved step + 1).

**Readings** (PLAN A9), by config and by band (early = levels 1-2, level 3, deep = levels ≥ 4):

* steps in the window (the first K steps after a compaction, K = 5; K = 10 a sensitivity
  reading) against the other steps, including those before the first compaction: level clears
  per step in each;
* unusable replies per call in each, a call being a saved step or a failed attempt;
* where each run ended: its last step and the steps since its last compaction.

Summarizer failures (the R7 cause) happen at a compaction by definition; the counted runs have
none (R7), and a replaced run that ended by one is marked so.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from analysis import arc_h4
from analysis import checkpoint_c as cc
from common import runmeta

CONFIGS = ("S1", "S2", "S4")
K_PRIMARY, K_SENSITIVITY = 5, 10
BANDS = ("early", "level 3", "deep")
OUTPUTS = ("compaction.json", "summary.md", "meta.json")
RESULTS = Path(__file__).resolve().parents[1] / "results"

SAVED = re.compile(r"Saved step (\d+) to")
LEVELS = re.compile(r": count (\d+), levels completed (\d+)")
UNUSABLE = re.compile(r"(Could not parse action from response|Unusable API response) "
                      r"\(attempt \d+/\d+\)")
SUMMARY_FAIL = re.compile(r"Harness summary compaction failed")


def band_of(level: int) -> str:
    return "early" if level <= 2 else "level 3" if level == 3 else "deep"


def parse_run(raw: Path) -> dict:
    """Compactions, steps (with the level in play and whether it cleared one), unusable replies
    and the ending, from one run's raw folder."""
    befores = sorted(int(json.loads(p.read_text(encoding="utf-8"))["before_step"])
                     for p in (raw / "harness").glob("compaction_*.json"))
    steps: dict[int, dict] = {}
    unusable: dict[int, int] = {}
    last, level_done, summary_fail = 0, 0, False
    for line in (raw / "harness.log").read_text(encoding="utf-8", errors="replace").splitlines():
        if m := SAVED.search(line):
            last = int(m.group(1))
            steps[last] = {"level": level_done + 1, "cleared": False}
        elif m := LEVELS.search(line):
            done = int(m.group(2))
            if done > level_done and last in steps:
                steps[last]["cleared"] = True
            level_done = max(level_done, done)
        elif UNUSABLE.search(line):
            unusable[last + 1] = unusable.get(last + 1, 0) + 1
        elif SUMMARY_FAIL.search(line):
            summary_fail = True
    return {"compactions": befores, "steps": steps, "unusable": unusable,
            "levels_completed": level_done, "last_step": last, "summary_failure": summary_fail}


def since_compaction(step: int, befores: list[int]) -> int | None:
    """1 for the first step after a compaction, 2 for the next, ...; None before the first."""
    prior = [s for s in befores if s <= step]
    return step - prior[-1] + 1 if prior else None


def tally(runs: list[dict], k: int) -> dict:
    """Clears per step and unusable replies per call, in the window and outside, by band and in
    all bands."""
    keys = (*BANDS, "all")
    out = {b: {w: {"steps": 0, "clears": 0, "calls": 0, "unusable": 0}
               for w in ("window", "other")} for b in keys}
    for r in runs:
        p = r["parsed"]
        tried = set(p["steps"]) | set(p["unusable"])
        level_at = {}
        level = 1
        for s in range(1, max(tried, default=0) + 1):
            if s in p["steps"]:
                level = p["steps"][s]["level"]
            level_at[s] = level
        for s in sorted(tried):
            d = since_compaction(s, p["compactions"])
            w = "window" if d is not None and d <= k else "other"
            for b in (band_of(level_at[s]), "all"):
                c = out[b][w]
                if s in p["steps"]:
                    c["steps"] += 1
                    c["clears"] += int(p["steps"][s]["cleared"])
                    c["calls"] += 1
                bad = p["unusable"].get(s, 0)
                c["calls"] += bad
                c["unusable"] += bad
    for b in keys:
        for w in ("window", "other"):
            c = out[b][w]
            c["clears_per_step"] = c["clears"] / c["steps"] if c["steps"] else None
            c["unusable_per_call"] = c["unusable"] / c["calls"] if c["calls"] else None
    return out


def ending(r: dict) -> dict:
    p = r["parsed"]
    last_tried = max([p["last_step"], *p["unusable"]]) if p["unusable"] else p["last_step"]
    return {"run_id": r["run_id"], "game": r["game"], "config": r["config"],
            "counted": r["counted"], "agent_exit_reason": r["agent_exit_reason"],
            "levels_completed": p["levels_completed"], "last_step": p["last_step"],
            "compactions": len(p["compactions"]),
            "steps_since_last_compaction": since_compaction(last_tried, p["compactions"]),
            "unusable_replies": sum(p["unusable"].values()),
            "summary_failure": p["summary_failure"]}


def compute(root: Path, raw_root: Path, generated: str, git: dict) -> dict:
    d = arc_h4.load(root, with_s1=True)
    if d.incomplete:
        raise cc.Refusal("a unit lacks a counted run: " + "; ".join(d.incomplete))
    runs, missing = [], []
    for (g, c), u in d.units.items():
        if c not in CONFIGS:
            continue
        chain = [e for e in (u.original, u.rerun, u.r7, u.r7_rerun) if e is not None]
        for e in chain:
            raw = raw_root / cc.EXPERIMENT / e.run_id
            if not (raw / "harness.log").is_file():
                missing.append(e.run_id)
                continue
            runs.append({"run_id": e.run_id, "game": g, "config": c,
                         "counted": e is u.counted, "agent_exit_reason": e.agent_exit_reason,
                         "parsed": parse_run(raw)})
    if missing:
        raise cc.Refusal("no raw harness.log for " + ", ".join(missing) + f" under {raw_root}")
    out = {"generated_utc": generated, **git, "status": "EXPLORATORY",
           "plan": "PLAN §24 (A9); PREREG §9.10", "k": K_PRIMARY, "k_sensitivity": K_SENSITIVITY,
           "path_games": d.games, "readings": {}, "replaced": {}, "endings": []}
    for c in CONFIGS:
        counted = [r for r in runs if r["config"] == c and r["counted"]]
        out["readings"][c] = {"runs": [r["run_id"] for r in counted],
                              "compactions": sum(len(r["parsed"]["compactions"]) for r in counted),
                              "steps": sum(len(r["parsed"]["steps"]) for r in counted),
                              f"k{K_PRIMARY}": tally(counted, K_PRIMARY),
                              f"k{K_SENSITIVITY}": tally(counted, K_SENSITIVITY)}
        rep = [r for r in runs if r["config"] == c and not r["counted"]]
        if rep:
            out["replaced"][c] = {"runs": [r["run_id"] for r in rep],
                                  f"k{K_PRIMARY}": tally(rep, K_PRIMARY)}
    out["endings"] = [ending(r) for r in sorted(runs, key=lambda r: r["run_id"])]
    return out


def _rate(x) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def summary_lines(h: dict) -> list[str]:
    k, k2 = h["k"], h["k_sensitivity"]
    L = ["# Failures after a history compaction (exploratory; PLAN A9)", "",
         (f"Computed {h['generated_utc']} at commit {h['git_commit'][:7]} (dirty: "
          f"{h['git_dirty']}). **Exploratory** (PREREG §9.10): no test, no verdict; it enters "
          "no hypothesis, gate or kill rule."), "",
         (f"Window: the first {k} steps after a compaction (K = {k2} as a sensitivity reading); "
          "\"other\": every other step, including those before the first compaction. Counted "
          "runs of each config on the 4 path games; replaced runs below."), ""]
    for c, rd in h["readings"].items():
        every = rd["steps"] / rd["compactions"] if rd["compactions"] else None
        L += [f"## {c} (counted runs: {len(rd['runs'])})", "",
              (f"Compactions: {rd['compactions']} over {rd['steps']} steps"
               + (f", one every {every:.1f} steps." if every else ".")), "",
              ("| Band | Steps in window / other | Clears per step, window / other | Unusable "
               "replies per call, window / other |"), "|---|---|---|---|"]
        for kk, label in ((f"k{k}", f"K = {k}"), (f"k{k2}", f"K = {k2}")):
            for b in (*BANDS, "all"):
                t = rd[kk][b]
                w, o = t["window"], t["other"]
                if not (w["steps"] or o["steps"]):
                    continue
                L.append(f"| {b} ({label}) | {w['steps']} / {o['steps']} | "
                         f"{_rate(w['clears_per_step'])} ({w['clears']}) / "
                         f"{_rate(o['clears_per_step'])} ({o['clears']}) | "
                         f"{_rate(w['unusable_per_call'])} ({w['unusable']}) / "
                         f"{_rate(o['unusable_per_call'])} ({o['unusable']}) |")
        L.append("")
    if h["replaced"]:
        L += ["## Replaced runs (D19 originals and R7-replaced runs; not counted)", ""]
        for c, rd in h["replaced"].items():
            a = rd[f"k{k}"]["all"]
            L.append(f"- {c} ({', '.join(rd['runs'])}), all bands, K = {k}: clears per step "
                     f"{_rate(a['window']['clears_per_step'])} / "
                     f"{_rate(a['other']['clears_per_step'])}; unusable per call "
                     f"{_rate(a['window']['unusable_per_call'])} / "
                     f"{_rate(a['other']['unusable_per_call'])} (window / other).")
        L.append("")
    L += ["## Where each run ended", "",
          ("| Run | Config | Counted | Ending | Levels | Last step | Compactions | Steps since "
           "last compaction | Unusable replies | Summarizer failure |"),
          "|---|---|---|---|---|---|---|---|---|---|"]
    for e in h["endings"]:
        L.append(f"| `{e['run_id']}` | {e['config']} | {e['counted']} | {e['agent_exit_reason']} "
                 f"| {e['levels_completed']} | {e['last_step']} | {e['compactions']} | "
                 f"{e['steps_since_last_compaction']} | {e['unusable_replies']} | "
                 f"{e['summary_failure']} |")
    L += ["", "## What it does not show", "",
          ("- **No causal effect of compaction.** Compactions come at fixed context sizes, the "
           "points where play has run longest, so time into the run is confounded with time "
           "since a compaction; the window and the other steps also differ in level and band."),
          ("- **Compactions are frequent** (the rate per config above), so the window covers "
           "most steps and the \"other\" group is small, especially at K = 10: the comparison "
           "is between the steps right after a compaction and a minority of steps further "
           "from one."),
          ("- **Few runs.** One counted run per game and config (4 per config); counts per cell "
           "are small, and the rates are descriptive."),
          ("- **Not blind.** The endings, levels and some log lines around them were seen before "
           "PLAN A9 was written (its list)."),
          ("- **Exploratory only** (PREREG §9.10); nothing here is a test or enters a decision.")]
    return L


def write(out_dir: Path, run_id: str, h: dict, text: str, git: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "compaction.json").write_text(json.dumps(h, indent=2) + "\n", encoding="utf-8",
                                             newline="\n")
    (out_dir / "summary.md").write_text(text, encoding="utf-8", newline="\n")
    config = {"plan": h["plan"], "k": h["k"], "k_sensitivity": h["k_sensitivity"],
              "configs": list(CONFIGS), "path_games": h["path_games"]}
    return runmeta.write_meta(
        out_dir, git=git, experiment="arc_compaction", run_id=run_id,
        cell_or_config="a9", config=config, model_requested=None, model_returned=None,
        reasoning_effort=None, reasoning_context_requested=None,
        reasoning_context_echoed=None, template_id=None, repeat_index=None, seeds=None,
        started_utc=h["generated_utc"], finished_utc=runmeta.utc_now(),
        exit_reason="completed", tokens=None, cost_usd=0.0, raw_transcript_path=None,
        outputs=list(OUTPUTS), paid_calls=0, runs=[e["run_id"] for e in h["endings"]])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--results-root", type=Path, default=RESULTS)
    ap.add_argument("--raw-root", type=Path, default=None,
                    help="the folder holding raw/ runs (default: <results root>/raw)")
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = a.results_root
    now = datetime.now(UTC)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    git = runmeta.git_state()
    try:
        h = compute(root, a.raw_root or root / "raw", now.isoformat(timespec="seconds"), git)
    except cc.Refusal as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    text = "\n".join(summary_lines(h)) + "\n"
    print(text)
    if not a.no_write:
        out = a.out_dir or root / "arc_compaction" / run_id
        write(out, run_id, h, text, git)
        print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
