"""Descriptive readings behind the preprint's report of R8's replication ($0; not tests).

`analysis.persistgym_h1h3` computes every registered H1 and H3 quantity. The preprint's §4
also states three descriptive readings that its output does not print. This script computes
them from each model's counted records at repeat 0. It reads exactly the records each model's
cited H1/H3 output counted: the runs and re-run links recorded in that output's meta.json,
resolved by `persistgym_h1h3.resolve` (harnesses/DESIGN.md §7.8).

1. **Choices with the fact evicted.** In W-0's two not-recoverable far cells, it counts how many
   episodes chose one of the K = 10 options at the need step (`need_label` set) and how many of
   those were correct. It also gives the need outcomes of the episodes that chose none.
2. **Refusals.** For each run kind (harness cell and variant, and the single-turn control), it
   counts the episodes with at least one step stopped by a refusal (an `incomplete` item whose
   reason starts with ``refusal``), by category, and the need-step refusals (``at_need``; a
   single-turn prompt is itself the need step).
3. **Where the refusals are.** It lists the templates that hold a refused episode, each with
   its skin, the setting `persistgym.template.sample_template` draws for it.

It reads only committed run folders (episodes.jsonl, meta.json), never the raw transcripts or
any model text.

Run: ``uv run python -m analysis.replication_readings``. It writes
``results/replication_readings/<UTC>/readings.json``, ``summary.md`` and ``meta.json``;
``--no-write`` only prints.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from analysis import persistgym_h1h3 as hh
from common import runmeta
from persistgym.config import PRESETS
from persistgym.template import sample_template

REPO_ROOT = Path(__file__).resolve().parent.parent
CITED = {
    "gpt-6-luna": "results/persistgym_h1h3/20261010T232227Z",
    "claude-haiku-5-5": "results/persistgym_h1h3_haiku/20261019T003254Z",
}
NR_FAR = ("observed-nonrec-far", "derived-nonrec-far")


def counted_records(model: str, root: Path) -> list[tuple[str, dict]]:
    """(run kind, record) of every counted repeat-0 key, as the model's cited output counted
    them."""
    meta = json.loads((root / CITED[model] / "meta.json").read_text(encoding="utf-8"))
    inputs = meta["config"]["inputs"]
    prof = hh.profile(model)
    runs, skipped = hh.discover(root / "results", declared=list(inputs["input_list"]), prof=prof)
    if skipped:
        raise SystemExit(f"{model}: runs skipped: {skipped}")
    stopped = hh.request_check_stops(runs) if model != hh.MODEL else None
    resolved, _ = hh.resolve(runs, dict(inputs["rerun_links"]), sweep_closed=True,
                             echo=model == hh.MODEL, stopped=stopped)
    out = []
    for (cell, _eid, rep), res in sorted(resolved.items()):
        if res.status != "counted" or rep != 0:
            continue
        variant = res.record.get("variant") or "base"
        kind = cell if variant == "base" else f"{cell} {variant}"
        out.append((kind, res.record))
    return out


def refusals(rec: dict) -> list[dict]:
    return [x for x in rec.get("incomplete") or [] if str(x.get("reason", "")).startswith("refusal")]


def readings(model: str, root: Path) -> dict:
    recs = counted_records(model, root)
    choices = {}
    for tc in NR_FAR:
        eps = [r for k, r in recs if k == "W-0" and r["task_cell"] == tc]
        chose = [r for r in eps if r.get("need_label") not in (None, "")]
        choices[tc] = {
            "episodes": len(eps), "chose_an_option": len(chose),
            "correct": sum(1 for r in chose if r.get("need_correct")),
            "chose_none_by_need_outcome": dict(Counter(r.get("need_outcome") for r in eps
                                                       if r.get("need_label") in (None, ""))),
        }
    by_kind: dict[str, dict] = defaultdict(lambda: {"episodes": 0, "with_refusal": 0,
                                                    "need_step_refusals": 0,
                                                    "categories": Counter()})
    templates: Counter = Counter()
    for kind, r in recs:
        k = by_kind[kind]
        k["episodes"] += 1
        refs = refusals(r)
        if refs:
            k["with_refusal"] += 1
            templates[r["template_id"]] += 1
            # a single-turn prompt is its need step (one request, no `at_need` field)
            k["need_step_refusals"] += sum(1 for x in refs
                                           if x.get("at_need") or kind == "single-turn")
            k["categories"].update(x["reason"] for x in refs)
    cfg = PRESETS["default"]
    skins = {}
    for tid in sorted(templates):
        split, index = tid.split("-")
        skins[tid] = sample_template(split, int(index), cfg).skin
    return {
        "model": model, "cited_output": CITED[model], "counted_repeat0_records": len(recs),
        "w0_nonrec_far_choices": choices,
        "refusals_by_run_kind": {k: {**v, "categories": dict(v["categories"])}
                                 for k, v in sorted(by_kind.items())},
        "refusal_templates": {t: {"episodes": n, "skin": skins[t]}
                              for t, n in sorted(templates.items())},
        "refusal_templates_by_skin": dict(Counter(skins.values())),
    }


def summary(rs: list[dict]) -> str:
    L = ["# Descriptive readings behind the replication's report (not tests)", "",
         ("Counted records at repeat 0, as each model's cited H1/H3 output counted them "
          "(DESIGN §7.8). Descriptive only: no contrast between the models is tested (§15, R8)."),
         ""]
    for r in rs:
        L += [f"## {r['model']} (`{r['cited_output']}`)", "",
              "| W-0 cell | Episodes | Chose an option | Correct | Chose none: need outcomes |",
              "|---|---|---|---|---|"]
        for tc, c in r["w0_nonrec_far_choices"].items():
            none = ", ".join(f"{k} {v}" for k, v in sorted(c["chose_none_by_need_outcome"].items(),
                                                            key=lambda kv: str(kv[0])))
            L.append(f"| {tc} | {c['episodes']} | {c['chose_an_option']} | {c['correct']} | "
                     f"{none or '-'} |")
        L += ["", "| Run kind | Episodes | With a refusal | Need-step refusals | Categories |",
              "|---|---|---|---|---|"]
        for kind, k in r["refusals_by_run_kind"].items():
            share = f"{k['with_refusal']} ({100 * k['with_refusal'] / k['episodes']:.2f}%)"
            cats = ", ".join(f"{c} {n}" for c, n in sorted(k["categories"].items())) or "-"
            L.append(f"| {kind} | {k['episodes']} | {share} | {k['need_step_refusals']} | {cats} |")
        t = r["refusal_templates"]
        L += ["", f"Templates with a refused episode: {len(t)}; by skin: "
              + (", ".join(f"{s} {n}" for s, n in sorted(r["refusal_templates_by_skin"].items()))
                 or "none") + ".", ""]
        if t:
            L.append("; ".join(f"`{tid}` {v['skin']} ({v['episodes']})" for tid, v in t.items())
                     + ".")
            L.append("")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=REPO_ROOT, help="the repository root")
    ap.add_argument("--no-write", action="store_true", help="print only")
    args = ap.parse_args(argv)
    started = runmeta.utc_now()
    rs = [readings(m, args.root) for m in CITED]
    text = summary(rs)
    sys.stdout.write(text)
    if args.no_write:
        return 0
    run_id = started.replace("-", "").replace(":", "").split("+")[0].split(".")[0] + "Z"
    out = args.root / "results" / "replication_readings" / run_id
    out.mkdir(parents=True, exist_ok=False)
    (out / "readings.json").write_text(json.dumps(rs, indent=2) + "\n", encoding="utf-8",
                                       newline="\n")
    (out / "summary.md").write_text(text, encoding="utf-8", newline="\n")
    runmeta.write_meta(
        out, experiment="replication_readings", run_id=run_id, cell_or_config="descriptive",
        config={"cited_outputs": CITED, "repeat": 0, "nr_far_cells": list(NR_FAR)},
        model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
        repeat_index=0, seeds=None, started_utc=started, finished_utc=runmeta.utc_now(),
        exit_reason="completed", tokens=None, cost_usd=0.0, raw_transcript_path=None,
        outputs=["readings.json", "summary.md"], paid_calls=0)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
