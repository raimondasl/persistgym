"""G0 gate metrics (PREREG §10.1), computed from committed files.

Run: `uv run python -m analysis.g0` ($0). It writes `results/gates/g0-<UTC>/g0.json` and
`summary.md`, and prints the summary. The researcher makes the go/no-go call (CLAUDE.md).

What it computes, per PREREG §10.1:

* **Cost rule** (D27 rule 1, D28). F = Σ over the 4 path games g and the configs
  c ∈ {S0, S1, S2, S4} of 2 × L(g, c) × b(c). L(g, c) is the published list cost of game g:
  the Standard recording for S0, the Adapter recording for S4, and their midpoint for S1 and
  S2 (`analysis.cost_model.OptionAModel`, basis `list_nocache`). b(c) is the billed/list cost
  ratio of config c measured in the truncated ARC pilot (`results/costs.csv`, experiment
  `arc_pilot`). Go on cost iff F × (1 + reserve) ≤ the phase-1b cap.
* **Toggle rule** (D29 as amended by R1, §17.1): per model, from the fork probe's committed
  `fork_report.json`: 20 scorable trials per arm, the `all_turns` arm's forks agree in ≥ 15
  and the `current_turn` arm's in ≤ 5, and every echoed `reasoning.context` matches.
* **Gemini S0-S2 run** (D37): each truncated pilot config reached its truncation point
  (`NORMAL_ENDING_BLINDED`), on the standard tier, at `thinking_level: high`, and S1 compacted
  at least once. Only fields §11 allows for ARC pilots are read: exit status, compaction
  occurrence, tier, model and settings; never level progress.

"Snapshot tests pass" is a test run, recorded with its command in `results/decisions.md`,
not computed here.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from analysis.cost_model import OptionAModel
from common import runmeta

REPO_ROOT = runmeta.REPO_ROOT
CONFIGS = ("S0", "S1", "S2", "S4")
FORK_RUNS = {"gpt-6.1-sol": "20261002T060546Z-replay-fork-gpt-6.1-sol",
             "gpt-6-luna": "20261002T061101Z-replay-fork-gpt-6-luna"}
FORK_TRIALS, FORK_ALL_MIN, FORK_CURRENT_MAX = 20, 15, 5  # PREREG §17.1


def pilot_ratios(costs_csv: Path) -> dict[str, dict[str, float]]:
    """b(c): billed/list cost of each ARC pilot config, from its results/costs.csv row."""
    out: dict[str, dict[str, float]] = {}
    with costs_csv.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["experiment"] != "arc_pilot":
                continue
            c = row["cell_or_config"]
            if c in out:
                raise ValueError(f"more than one arc_pilot row for {c}")
            listed, billed = float(row["cost_usd_list"]), float(row["cost_usd_billed_est"])
            out[c] = {"run_id": row["run_id"], "list": listed, "billed": billed,
                      "b": billed / listed}
    missing = [c for c in CONFIGS if c not in out]
    if missing:
        raise ValueError(f"no arc_pilot row for {missing}")
    return out


def cost_rule(model: OptionAModel, ratios: dict[str, dict[str, float]]) -> dict:
    """D27 rule 1 with measured b(c), against the 1b cap with D28's reserve."""
    games = model.arc_rows("list_nocache", "path")
    per_game, F = [], 0.0
    for g in games.itertuples():
        L = {"S0": g.S0, "S1": g.midpoint, "S2": g.midpoint, "S4": g.S4}
        cost = sum(2 * L[c] * ratios[c]["b"] for c in CONFIGS)
        per_game.append({"game": g.game, "L_S0": g.S0, "L_S4": g.S4, "L_midpoint": g.midpoint,
                         "F_game": cost})
        F += cost
    reserve, cap = model.reserve, model.caps["1b"]
    with_reserve = F * (1 + reserve)
    return {"rule": "PREREG §10.1 D27 rule 1 with D28's reserve; b(c) measured in the pilot",
            "b": {c: ratios[c]["b"] for c in CONFIGS},
            "pilot_rows": {c: ratios[c]["run_id"] for c in CONFIGS},
            "games": per_game, "F_billed": F, "reserve": reserve,
            "F_with_reserve": with_reserve, "cap_1b": cap, "headroom": cap - with_reserve,
            "go": with_reserve <= cap}


def toggle(results: Path) -> dict:
    out = {}
    for model, run_id in FORK_RUNS.items():
        rep = json.loads((results / "replay_probe" / run_id / "fork_report.json")
                         .read_text(encoding="utf-8"))
        a, c = rep["arms"]["all_turns"], rep["arms"]["current_turn"]
        echo_ok = a["echo_mismatched_responses"] == 0 and c["echo_mismatched_responses"] == 0
        verified = (a["scorable"] >= FORK_TRIALS and c["scorable"] >= FORK_TRIALS and echo_ok
                    and a["agreements"] >= FORK_ALL_MIN and c["agreements"] <= FORK_CURRENT_MAX)
        out[model] = {"run_id": run_id, "all_turns_agreements": a["agreements"],
                      "current_turn_agreements": c["agreements"],
                      "scorable": [a["scorable"], c["scorable"]], "echo_ok": echo_ok,
                      "verified": verified}
    return out


def gemini(results: Path) -> dict:
    """The truncated pilot's allowed fields (PREREG §11), per config."""
    out = {}
    for d in sorted((results / "arc_pilot").iterdir()):
        m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        c = m["cell_or_config"]
        tiers = m.get("service_tiers_served") or {}
        out[c] = {"run_id": m["run_id"], "exit_reason": m["exit_reason"],
                  "truncation_limits": m.get("truncation_limits"),
                  "n_compactions": m.get("n_compactions"), "service_tiers_served": tiers,
                  "model_returned": m.get("model_returned"),
                  "reasoning_effort": m.get("reasoning_effort")}
    ok = {}
    for c in ("S0", "S1", "S2"):
        r = out.get(c)
        ok[c] = bool(r and r["exit_reason"] == "NORMAL_ENDING_BLINDED"
                     and set(r["service_tiers_served"]) == {"standard"}
                     and (r["reasoning_effort"] or {}).get("thinking_level") == "high"
                     and (c != "S1" or (r["n_compactions"] or 0) >= 1))
    return {"configs": out, "reached": ok, "go": all(ok.values())}


def summary_lines(g0: dict) -> list[str]:
    cr, tg, gm = g0["cost"], g0["toggle"], g0["gemini"]
    L = ["# G0 gate metrics (PREREG §10.1)", "",
         (f"Computed {g0['generated_utc']} at commit {g0['git_commit'][:7]} "
          f"(dirty: {g0['git_dirty']}) by `uv run python -m analysis.g0`."), "",
         "## Cost rule (D27 rule 1, D28)", "",
         "| Config | b(c) = billed/list in the pilot |", "|---|---|"]
    L += [f"| {c} | {cr['b'][c]:.3f} |" for c in CONFIGS]
    L += ["", "| Game | L(S0) | L(S4) | L(S1) = L(S2) | F(game), billed |", "|---|---|---|---|---|"]
    L += [f"| {g['game']} | {g['L_S0']:.2f} | {g['L_S4']:.2f} | {g['L_midpoint']:.2f} | "
          f"{g['F_game']:.2f} |" for g in cr["games"]]
    L += ["", (f"- F = **${cr['F_billed']:.2f}** billed; with the {cr['reserve']:.0%} reserve "
               f"**${cr['F_with_reserve']:.2f}** against the ${cr['cap_1b']:.0f} phase-1b cap "
               f"(headroom ${cr['headroom']:.2f}): **{'met' if cr['go'] else 'NOT met'}**."), "",
          "## Toggle rule (D29 as amended by R1)", ""]
    for model, t in tg.items():
        L.append(f"- {model}: forks agree {t['all_turns_agreements']}/20 (`all_turns`) and "
                 f"{t['current_turn_agreements']}/20 (`current_turn`), echo "
                 f"{'all matched' if t['echo_ok'] else 'MISMATCH'}: "
                 f"**{'verified' if t['verified'] else 'not verified'}**.")
    L += ["", "## Gemini S0-S2 run (D37)", ""]
    for c, r in gm["configs"].items():
        L.append(f"- {c}: {r['exit_reason']}, limits {r['truncation_limits']}, compactions "
                 f"{r['n_compactions']}, tiers {r['service_tiers_served']}"
                 + (f": **{'reached' if gm['reached'][c] else 'NOT reached'}**"
                    if c in gm["reached"] else " (S4: not a G0 condition)"))
    L += ["", "Snapshot tests: a test run, recorded in `results/decisions.md`.",
          "", "The researcher makes the go/no-go call."]
    return L


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    results = REPO_ROOT / "results"
    now = datetime.now(UTC)
    g0 = {"generated_utc": now.isoformat(timespec="seconds"), **runmeta.git_state(),
          "prereg_version": runmeta.prereg_version(),
          "cost": cost_rule(OptionAModel(), pilot_ratios(results / "costs.csv")),
          "toggle": toggle(results), "gemini": gemini(results)}
    text = "\n".join(summary_lines(g0)) + "\n"
    print(text)
    if not a.no_write:
        out = a.out_dir or results / "gates" / f"g0-{now.strftime('%Y%m%dT%H%M%SZ')}"
        out.mkdir(parents=True, exist_ok=True)
        (out / "g0.json").write_text(json.dumps(g0, indent=2, ensure_ascii=False) + "\n",
                                     encoding="utf-8", newline="\n")
        (out / "summary.md").write_text(text, encoding="utf-8", newline="\n")
        print(f"written: {out.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
