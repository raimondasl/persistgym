"""G1 gate metrics (PREREG §4.4, §10.2), computed from committed files and $0 audits.

Run: `uv run python -m analysis.g1 [--audit-n 1000] [--no-write]` ($0: no API call). It writes
`results/gates/g1-<UTC>/` with `g1.json`, `summary.md` and the two audit outputs, and prints
the summary. The researcher makes the go/no-go call (CLAUDE.md, PREREG §10.2).

What it computes, per PREREG §4.4 (as amended by R3 and R6) for gpt-6-luna on the default
generator config (hash `3d6bc648…`, the config of luna's validity runs and main sweep):

* **The LLM rates.** From luna's committed validity runs (`results/persistgym_validity/
  *-gpt-6-luna/episodes.jsonl`, harness cell F-0, validity templates 0-19 × 8 task cells):
  restated-at-need correct ≥ 85% and fact-withheld correct ≤ 20%, each pooled over the 8 task
  cells (D39); per-cell rates are reported, not gated. Excluded episodes are left out and
  counted.
* **The programmatic oracle and the $0 audits.** `persistgym audit` (default preset) on the
  validity templates 0-19 (the spot-checked and LLM-played ones) and on main templates
  0..n-1 (n = 1,000 by default: PREREG §4.4's 1,000 generated episodes per task cell for the
  heuristic baselines). Each audit must pass as a whole (`pass`); the key and text oracles
  must score 1.00 on the base and restated renderings.
* **The researcher's spot-check.** `results/spotcheck/g1-validity-0-20-3d6bc648/findings.csv`,
  read and checked against its manifest by `persistgym.spotcheck`: verdict counts per task
  cell and every flagged episode. PREREG sets no numeric rule; the counts inform the call.
* **Spend to date** by phase, from `results/costs.csv`.
* **Reported only:** gpt-6.1-sol's default-config validity runs (R4), whose main runs R6 drops.

Under R6 change 7 there is no redesign pass: if G1 fails, PersistGym stops and the paper
reports the ARC leg alone (kill criterion 3).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from common import costs, runmeta
from persistgym import cli as pg_cli
from persistgym import spotcheck

REPO_ROOT = runmeta.REPO_ROOT
MODEL = "gpt-6-luna"
CONFIG_HASH = "3d6bc648eaa9b9e843fe6e70060495cd197630b0f2d585e66b3cd280b7a3968b"
SPOTCHECK_ID = "g1-validity-0-20-3d6bc648"
RESTATED_MIN, WITHHELD_MAX = 0.85, 0.20          # PREREG §4.4, pooled over the 8 task cells
VALIDITY_N = 20                                   # validity templates 0-19
ORACLE_VIEWS = ("key/base/nonrec", "key/base/rec", "key/restated/nonrec", "key/restated/rec",
                "text/base/nonrec", "text/base/rec", "text/restated/nonrec", "text/restated/rec")


def validity_runs(results: Path, model: str) -> dict[str, dict]:
    """Per variant (restated, withheld): the model's committed validity runs on the default
    config, with correct/n pooled and per task cell over the non-excluded episodes."""
    out: dict[str, dict] = {}
    for d in sorted((results / "persistgym_validity").glob(f"*-{model}")):
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        if meta["config"]["generator_config_hashes"] != [CONFIG_HASH]:
            continue
        eps = [json.loads(line) for line in
               (d / "episodes.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        variants = {e["variant"] for e in eps}
        if len(variants) != 1:
            raise ValueError(f"{d.name}: more than one variant {sorted(variants)}")
        v = variants.pop()
        if v in out:
            raise ValueError(f"more than one {model} validity run of variant {v}")
        kept = [e for e in eps if not e["excluded"]]
        cells: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for e in kept:
            cells[e["task_cell"]][0] += bool(e["need_correct"])
            cells[e["task_cell"]][1] += 1
        correct = sum(c for c, _ in cells.values())
        out[v] = {"run_id": d.name, "n_episodes": len(eps), "n_excluded": len(eps) - len(kept),
                  "exit_reasons": sorted({e["exit_reason"] for e in eps}),
                  "correct": correct, "n": len(kept), "rate": correct / len(kept),
                  "per_cell": {c: {"correct": k, "n": n, "rate": k / n}
                               for c, (k, n) in sorted(cells.items())},
                  "billed_usd": meta["cost_usd"]["billed_est"]}
    return out


def llm_rule(runs: dict[str, dict]) -> dict:
    r, w = runs.get("restated"), runs.get("withheld")
    ok_r = bool(r) and r["rate"] >= RESTATED_MIN
    ok_w = bool(w) and w["rate"] <= WITHHELD_MAX
    return {"restated_min": RESTATED_MIN, "withheld_max": WITHHELD_MAX,
            "restated_ok": ok_r, "withheld_ok": ok_w, "pass": ok_r and ok_w}


def run_audit(split: str, n: int, out_path: Path) -> dict:
    """`persistgym audit --preset default` on templates 0..n-1 of a split; its JSON output."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = pg_cli.main(["audit", "--split", split, "--n", str(n), "--preset", "default",
                          "--out", str(out_path)])
    a = json.loads(out_path.read_text(encoding="utf-8"))
    if a["config_hash"] != CONFIG_HASH:
        raise ValueError(f"audit ran on config {a['config_hash'][:8]}, not {CONFIG_HASH[:8]}")
    oracles = {k: a["oracles"][k]["accuracy"] for k in ORACLE_VIEWS}
    return {"split": split, "n_templates": a["n_templates"], "n_episodes": a["n_episodes"],
            "rc": rc, "pass": bool(a["pass"]) and rc == 0,
            "failed_checks": sorted(k for k, c in a["checks"].items() if not c["pass"]),
            "oracles": oracles, "oracles_ok": all(v == 1.0 for v in oracles.values()),
            "baselines_max": max(b["accuracy"] for b in a["baselines"].values()),
            "partial_memory_pass": all(p["pass"] for p in a["partial_memory"].values()),
            "file": out_path.name}


def spot_check(spot_root: Path) -> dict:
    pkg = spot_root / SPOTCHECK_ID
    manifest = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
    rows = spotcheck.read_findings(pkg / "findings.csv", manifest)
    s = spotcheck.summarize_findings(rows, manifest)
    return {"package": SPOTCHECK_ID, "cells": s["cells"], "totals": s["totals"],
            "flagged": s["flagged"], "complete": s["complete"]}


def summary_lines(g: dict) -> list[str]:
    L = ["# G1 gate metrics (PREREG §4.4, §10.2)", "",
         (f"Computed {g['generated_utc']} at commit {g['git_commit'][:7]} "
          f"(dirty: {g['git_dirty']}) by `uv run python -m analysis.g1`. "
          f"Model {MODEL}, generator config `{CONFIG_HASH[:8]}…` (default)."), "",
         "## LLM validity rates (F-0, validity templates 0-19 × 8 task cells)", ""]
    runs, rule = g["luna"]["runs"], g["luna"]["rule"]
    for v, gate, ok in (("restated", f"≥ {RESTATED_MIN:.0%}", rule["restated_ok"]),
                        ("withheld", f"≤ {WITHHELD_MAX:.0%}", rule["withheld_ok"])):
        r = runs.get(v)
        if not r:
            L.append(f"- {v}: **no run**")
            continue
        L.append(f"- {v} (`{r['run_id']}`): **{r['correct']}/{r['n']} = {r['rate']:.1%}** "
                 f"(gate {gate}): **{'met' if ok else 'NOT met'}**; {r['n_excluded']} "
                 f"excluded; endings {', '.join(r['exit_reasons'])}.")
    cells = sorted({c for r in runs.values() for c in r["per_cell"]})
    L += ["", "| Task cell | restated | withheld |", "|---|---|---|"]
    for c in cells:
        cols = []
        for v in ("restated", "withheld"):
            pc = runs.get(v, {}).get("per_cell", {}).get(c)
            cols.append(f"{pc['correct']}/{pc['n']}" if pc else "n/a")
        L.append(f"| {c} | {cols[0]} | {cols[1]} |")
    L += ["", "Per-cell rates are reported, not gated (D39).", "",
          "## Oracle and $0 audits (`persistgym audit`, default preset)", ""]
    for a in g["audits"]:
        L.append(f"- {a['split']} templates 0-{a['n_templates'] - 1} ({a['n_episodes']:,} "
                 f"episodes): **{'pass' if a['pass'] else 'FAIL'}**; failed checks: "
                 f"{', '.join(a['failed_checks']) or 'none'}; key and text oracles on base "
                 f"and restated {'all 1.00' if a['oracles_ok'] else 'NOT all 1.00'}; highest "
                 f"no-memory baseline {a['baselines_max']:.3f} (gate ≤ 0.20); partial memory "
                 f"{'pass' if a['partial_memory_pass'] else 'FAIL'} (`{a['file']}`).")
    sc = g["spotcheck"]
    L += ["", f"## Researcher spot-check (`results/spotcheck/{sc['package']}/findings.csv`)", "",
          "| Task cell | no shortcut | possible | shortcut | unreviewed |", "|---|---|---|---|---|"]
    for c, k in sc["cells"].items():
        L.append(f"| {c} | {k['no_shortcut']} | {k['possible_shortcut']} | {k['shortcut']} | "
                 f"{k['unreviewed']} |")
    t = sc["totals"]
    L.append(f"| all | {t['no_shortcut']} | {t['possible_shortcut']} | {t['shortcut']} | "
             f"{t['unreviewed']} |")
    L += ["", f"Complete: {sc['complete']}. Flagged episodes: {len(sc['flagged'])}."]
    L += [f"- {r['verdict']}: {r['episode_id']}: {r['notes']}" for r in sc["flagged"]]
    L += ["", "## Reported only: gpt-6.1-sol on the default config (R4; main runs dropped by R6)", ""]
    for v, r in g["sol_r4"].items():
        L.append(f"- {v}: {r['correct']}/{r['n']} = {r['rate']:.1%} (`{r['run_id']}`)")
    sp = g["spend_by_phase"]
    L += ["", "## Spend to date (billed estimate; list where a row has none)", "",
          "- " + ", ".join(f"phase {p} ${v:.2f}" for p, v in sp.items())
          + f"; all ${sum(sp.values()):.2f}.", "",
          "## Reading", "",
          (f"- LLM rule: **{'met' if rule['pass'] else 'NOT met'}**. Audits and oracle: "
           f"**{'pass' if g['audits_pass'] else 'FAIL'}**. Spot-check: {t['no_shortcut']} no "
           f"shortcut, {t['possible_shortcut']} possible, {t['shortcut']} shortcut, "
           f"{t['unreviewed']} unreviewed."),
          ("- PREREG sets no numeric rule for the spot-check; under R6 change 7 there is no "
           "redesign pass. **The researcher makes the go/no-go call.**")]
    return L


def compute(results: Path, audit_dir: Path, audit_n: int, spot_root: Path) -> dict:
    now = datetime.now(UTC)
    luna = validity_runs(results, MODEL)
    audits = [run_audit("validity", VALIDITY_N, audit_dir / "audit_validity.json"),
              run_audit("main", audit_n, audit_dir / "audit_main.json")]
    return {"generated_utc": now.isoformat(timespec="seconds"), **runmeta.git_state(),
            "prereg_version": runmeta.prereg_version(), "model": MODEL,
            "config_hash": CONFIG_HASH,
            "luna": {"runs": luna, "rule": llm_rule(luna)},
            "audits": audits, "audits_pass": all(a["pass"] and a["oracles_ok"] for a in audits),
            "spotcheck": spot_check(spot_root),
            "sol_r4": validity_runs(results, "gpt-6.1-sol"),
            "spend_by_phase": costs.spend_by_phase(costs.read_rows(results / "costs.csv"))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--audit-n", type=int, default=1000,
                    help="main templates for the $0 audit (a multiple of 10; default 1,000)")
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    results = REPO_ROOT / "results"
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    with tempfile.TemporaryDirectory() as tmp:
        audit_dir = Path(tmp)
        g = compute(results, audit_dir, a.audit_n, spotcheck.RESULTS_ROOT)
        text = "\n".join(summary_lines(g)) + "\n"
        print(text)
        if not a.no_write:
            out = a.out_dir or results / "gates" / f"g1-{stamp}"
            out.mkdir(parents=True, exist_ok=True)
            for f in audit_dir.glob("audit_*.json"):
                (out / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            (out / "g1.json").write_text(json.dumps(g, indent=2, ensure_ascii=False) + "\n",
                                         encoding="utf-8")
            (out / "summary.md").write_text(text, encoding="utf-8")
            print(f"written: {out.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
