"""Cost forecast for amendment R4 (PREREG §17.4): a sol replication of H1, from measured rows.

R4 runs gpt-6.1-sol at `reasoning.effort: medium` on the default generator config in the
harness cells F-0, W-0 and W-n-0, on the 4 observed task cells. This script forecasts its
billed cost (the spend measure of every cap, `common.costs.spend_usd`) from block 1's
measured `results/costs.csv` rows, each run's episode count read from its committed
`meta.json`:

* **pilot:** W-0 and W-n-0, one run each, pilot templates 0 and 1 × the 4 observed task
  cells (8 episodes per run); W cells have never run on sol (CLAUDE.md: pilot every new
  harness cell on a model);
* **validity:** F-0, validity templates 0-19 × the 4 observed task cells, restated and
  withheld (160 episodes);
* **main:** F-0, W-0 and W-n-0, each on T templates × the 4 observed task cells plus the
  §2.9 repeat subset (seeds divisible by 10 get repeat 1): 4 × (T + T/10) episodes per
  harness cell, at T = 100 and, for comparison, T = 50.

Two scenarios (`SCENARIOS`):

* **low**: the bases first proposed. sol's F-0 cost per episode from its block-1 pilot row
  (`SOL_F0_PILOT`), and each W cell at luna's measured billed cost ratio to F-0 per episode
  (`LUNA_PILOT`).
* **central**: the same rows, corrected for two things the low basis misses.
  - *Cache:* sol's F-0 pilot run played its 8 episodes right after the F-r run had played
    the same 8, with nearly the same input (within 28 tokens of 3.24M), so almost all of its
    input, each call's new suffix included, was read from the cache: 3,030 cache-write
    tokens against the F-r run's 252,326. A main-sweep run plays episodes no other run has
    just played, so its calls write their new suffix to the cache, at 1.25 times the input
    price. The central basis is therefore the F-r row of the same pilot (`SOL_FR_PILOT`),
    the first run of those episodes: at medium effort sol reasoned almost not at all there
    (115 reasoning tokens over 360 calls, pooled over both arms; PREREG §17.2), so the F-r
    run's payloads stand in for a cold F-0 run's.
  - *Price:* window cells lose about half of their prompt caching (luna's pilot read about
    half of the W cells' input from the cache, against 94% in F-0; `Run.cached_share`), so
    their extra cost is mostly cache writes and uncached input in place of cached reads.
    sol's cached input costs 1/20 of its input price and luna's 1/10 (`harnesses.pricing`),
    so luna's cost ratio understates sol's. The central ratio prices luna's measured token
    counts of each W cell and of F-0 at sol's prices (Flex, cache writes at 1.25).
  - *Validity:* restated and withheld episodes at luna's measured validity cost per episode
    over its base F-0 pilot cost per episode (`LUNA_VALIDITY`).

The phase-1a picture adds the ledger's phase-1a spend (R3's engagement check included) and,
as rough context at measured block-1 costs, the other phase-1a row that will run: luna's
main sweep and controls. sol's H2 core and its validity run on `sol-chain` are not counted:
R3's check found NOT_ENGAGED on 2026-10-03, and R3's hard stop ended H2 on sol
(`results/decisions.md`).

Blinding (PREREG §11): pilot rows are read for their cost and token counts. Their
reasoning tokens are never read (pilot rows leave them empty). luna's output tokens per run
enter the repricing of its W cells, as one row's cost already does (§11, known limit). Only
forecast outputs are printed or written.

Limits (also in the summary): sol's W cells are unmeasured (luna's token mix stands in);
near and far episodes are assumed to cost the same (they share their skeleton, PREREG §2.7);
each basis is one run of 8 episodes (sol: 2 pilot templates on the 4 far task cells; luna:
1 pilot template on the 8 task cells); prices are those of 2026-09-30.

Run: ``uv run python -m analysis.sol_h1_forecast`` (``--no-write`` only prints). It writes
``results/cost_model/<UTC>/sol_h1_forecast.csv``, ``sol_h1_phase_1a.csv``, ``summary.md``
and ``meta.json``.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from common import costs
from harnesses import pricing

REPO_ROOT = Path(__file__).resolve().parent.parent
SOL, LUNA = "gpt-6.1-sol", "gpt-6-luna"

# --- measured block-1 runs (results/costs.csv rows; episode counts from meta.json) ----------
SOL_F0_PILOT = "20261002T083706Z-F-0-gpt-6.1-sol"
"""sol F-0 at medium, default config, pilot templates 0-1 × the 4 far task cells (8
episodes): the low basis; played right after `SOL_FR_PILOT`, so its cache was warm."""
SOL_FR_PILOT = "20261002T083238Z-F-r-gpt-6.1-sol"
"""sol F-r at medium on the same 8 episodes, the first run of them: the cold-cache basis."""
LUNA_PILOT = {"F-0": "20261002T081803Z-F-0-gpt-6-luna",
              "W-0": "20261002T082913Z-W-0-gpt-6-luna",
              "W-n-0": "20261002T082140Z-W-n-0-gpt-6-luna",
              "Σ-n-0": "20261002T082532Z-sigma-n-0-gpt-6-luna"}
"""luna at medium, default config, pilot template 0 × the 8 task cells (8 episodes each)."""
LUNA_VALIDITY = ("20261002T084243Z-F-0-gpt-6-luna", "20261002T095135Z-F-0-gpt-6-luna")
"""luna's validity runs, F-0, restated and withheld, validity templates 0-19 × 8 task cells."""

# --- design (PREREG §17.4; §2.9, §4.2, §17.2, §17.3) --------------------------------------
R4_CELLS = ("F-0", "W-0", "W-n-0")
OBSERVED_TASK_CELLS = 4
PILOT_EPISODES = 8              # pilot templates 0-1 × the 4 observed task cells, per run
VALIDITY_EPISODES = 160         # validity templates 0-19 × 4 observed cells × 2 variants
T_VALUES = (100, 50)            # 100: about luna's count (§4.2); 50 for comparison
LUNA_T = 100                    # context: luna's main sweep (§4.2: about 100)
LUNA_SWEEP_CELLS = ("F-0", "W-n-0", "Σ-n-0", "W-0")   # §4.6, replay-off
LUNA_TASK_CELLS = 8
LUNA_NONREC_TASK_CELLS = 4      # single-turn control (D36)


def main_episodes(T: int) -> int:
    """Episodes per harness cell at T templates: the 4 observed task cells on T templates,
    plus repeat 1 on the templates whose seed is divisible by 10 (§2.9; T a multiple of 10)."""
    if T <= 0 or T % 10:
        raise ValueError(f"T must be a positive multiple of 10 (D7), got {T}")
    return OBSERVED_TASK_CELLS * (T + T // 10)


@dataclass(frozen=True)
class Run:
    """One measured run: billed cost, input-side token counts and episodes."""

    run_id: str
    model: str
    billed_usd: float
    input_tokens: int
    cached_input_tokens: int
    cache_write_tokens: int
    output_tokens: int
    episodes: int

    @property
    def per_episode(self) -> float:
        return self.billed_usd / self.episodes

    @property
    def cached_share(self) -> float:
        """The share of this run's input tokens read from the cache."""
        return self.cached_input_tokens / self.input_tokens

    def billed_at(self, model: str) -> float:
        """This run's token counts priced at `model`'s prices on Flex
        (`harnesses.pricing.cost_usd`, the formula of every costs row)."""
        usage = {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                 "input_tokens_details": {"cached_tokens": self.cached_input_tokens,
                                          "cache_write_tokens": self.cache_write_tokens}}
        return pricing.cost_usd(model, usage, "flex")[1]


def load_runs(costs_path: Path = costs.COSTS_CSV, results_root: Path = REPO_ROOT / "results",
              run_ids: tuple[str, ...] | None = None) -> dict[str, Run]:
    """The measured runs this forecast reads: their costs.csv rows and the episode counts
    of their committed meta.json (`n_episodes_run`)."""
    wanted = run_ids or (SOL_F0_PILOT, SOL_FR_PILOT, *LUNA_PILOT.values(), *LUNA_VALIDITY)
    rows = {r["run_id"]: r for r in costs.read_rows(costs_path)}
    out = {}
    for run_id in wanted:
        if run_id not in rows:
            raise KeyError(f"run {run_id} has no row in {costs_path}")
        r = rows[run_id]
        meta_paths = list(results_root.glob(f"*/{run_id}/meta.json"))
        if len(meta_paths) != 1:
            raise FileNotFoundError(f"expected one meta.json of run {run_id} under "
                                    f"{results_root}, found {len(meta_paths)}")
        meta = json.loads(meta_paths[0].read_text(encoding="utf-8"))
        episodes = int(meta["n_episodes_run"])
        if episodes <= 0 or meta["run_id"] != run_id:
            raise ValueError(f"{meta_paths[0]}: not a run with episodes")
        out[run_id] = Run(run_id=run_id, model=r["model_requested"],
                          billed_usd=float(r["cost_usd_billed_est"]),
                          input_tokens=int(r["input_tokens"]),
                          cached_input_tokens=int(r["cached_input_tokens"]),
                          cache_write_tokens=int(r["cache_write_tokens"] or 0),
                          output_tokens=int(r["output_tokens"]), episodes=episodes)
    return out


@dataclass(frozen=True)
class Scenario:
    """Per-episode forecast bases on sol: F-0's cost per episode, each cell's ratio to it,
    and the validity factor."""

    name: str
    label: str
    f0_per_episode: float
    ratio: dict[str, float]
    validity_factor: float

    def per_episode(self, cell: str) -> float:
        return self.f0_per_episode * self.ratio[cell]


def luna_validity_factor(runs: dict[str, Run]) -> float:
    """luna's validity cost per episode (both runs) over its base F-0 pilot cost per episode."""
    val = [runs[r] for r in LUNA_VALIDITY]
    per_val = sum(r.billed_usd for r in val) / sum(r.episodes for r in val)
    return per_val / runs[LUNA_PILOT["F-0"]].per_episode


def scenarios(runs: dict[str, Run]) -> dict[str, Scenario]:
    luna = {c: runs[LUNA_PILOT[c]] for c in R4_CELLS}
    cost_ratio = {c: luna[c].per_episode / luna["F-0"].per_episode for c in R4_CELLS}
    sol_priced = {c: (luna[c].billed_at(SOL) / luna[c].episodes)
                  / (luna["F-0"].billed_at(SOL) / luna["F-0"].episodes) for c in R4_CELLS}
    return {
        "low": Scenario("low", "low: sol's F-0 pilot row (warm cache); luna's measured W/F-0 "
                        "cost ratios", runs[SOL_F0_PILOT].per_episode, cost_ratio, 1.0),
        "central": Scenario("central", "central: sol's F-r pilot row (cold cache, the same "
                            "episodes); luna's W/F-0 token mix priced at sol's prices; luna's "
                            "validity/base factor", runs[SOL_FR_PILOT].per_episode,
                            sol_priced, luna_validity_factor(runs)),
    }


def forecast_rows(sc: Scenario) -> list[dict]:
    """R4's forecast lines in one scenario: the pilot, the validity run and the main runs at
    each T, one row per harness cell, then a total row per item."""
    rows: list[dict] = []

    def add(item: str, cell: str, episodes: int, per_episode: float) -> None:
        rows.append({"scenario": sc.name, "item": item, "harness_cell": cell,
                     "episodes": episodes, "usd_per_episode": per_episode,
                     "usd": episodes * per_episode})

    for cell in ("W-0", "W-n-0"):
        add("pilot", cell, PILOT_EPISODES, sc.per_episode(cell))
    add("validity", "F-0", VALIDITY_EPISODES, sc.per_episode("F-0") * sc.validity_factor)
    for T in T_VALUES:
        for cell in R4_CELLS:
            add(f"main_T{T}", cell, main_episodes(T), sc.per_episode(cell))
    totals: dict[str, list[float]] = {}
    for r in rows:
        t = totals.setdefault(r["item"], [0, 0.0])
        t[0] += r["episodes"]
        t[1] += r["usd"]
    for item, (n, usd) in totals.items():
        rows.append({"scenario": sc.name, "item": item, "harness_cell": "all", "episodes": n,
                     "usd_per_episode": usd / n, "usd": usd})
    return rows


def item_total(rows: list[dict], scenario: str, item: str) -> float:
    (row,) = [r for r in rows if r["scenario"] == scenario and r["item"] == item
              and r["harness_cell"] == "all"]
    return row["usd"]


def r4_total(rows: list[dict], scenario: str, T: int) -> float:
    """Pilot, validity and main runs at T."""
    return sum(item_total(rows, scenario, i) for i in ("pilot", "validity", f"main_T{T}"))


def context_rows(runs: dict[str, Run]) -> dict[str, float]:
    """Rough forecasts, at measured block-1 costs, of the other phase-1a rows that will run
    (not R4's): luna's main sweep at T = `LUNA_T` and its controls."""
    per = {c: runs[LUNA_PILOT[c]].per_episode for c in LUNA_SWEEP_CELLS}
    luna_n = LUNA_TASK_CELLS * (LUNA_T + LUNA_T // 10)
    single_n = LUNA_NONREC_TASK_CELLS * (LUNA_T + LUNA_T // 10)
    return {
        "luna_main_sweep": luna_n * sum(per.values()),
        # restated-at-need as F-0 episodes; each single-turn prompt bounded by one F-0 episode
        "luna_controls": (luna_n * per["F-0"] * luna_validity_factor(runs)
                          + single_n * per["F-0"]),
    }


def phase_1a_rows(rows: list[dict], runs: dict[str, Run],
                  costs_path: Path = costs.COSTS_CSV) -> list[dict]:
    """The phase-1a picture against the cap: spend to date (R3's check included), the
    context rows, R4 (both scenarios, each T) and the totals. sol's H2 runs are not counted:
    R3's hard stop ended them."""
    ledger = costs.read_rows(costs_path)
    spent = costs.spend_by_phase(ledger)["1a"]
    n_rows = sum(costs.phase_of(r["experiment"]) == "1a" for r in ledger)
    ctx = context_rows(runs)
    luna = ctx["luna_main_sweep"] + ctx["luna_controls"]
    out = [
        {"line": "spent", "usd": spent,
         "note": f"phase 1a in results/costs.csv ({n_rows} rows), billed (common.costs)"},
        {"line": "luna_main_sweep_and_controls", "usd": luna,
         "note": f"context, rough: T = {LUNA_T}, luna's block-1 pilot costs per episode"},
        {"line": "sol_h2", "usd": 0.0,
         "note": "not run: R3's hard stop ended H2 on sol (results/decisions.md, 2026-10-03)"},
    ]
    base = spent + luna
    for sc in ("central", "low"):
        for T in T_VALUES:
            r4 = r4_total(rows, sc, T)
            out.append({"line": f"r4_{sc}_T{T}", "usd": r4,
                        "note": "R4: pilot + validity + main runs"})
            total = base + r4
            out.append({"line": f"total_{sc}_T{T}", "usd": total,
                        "note": f"headroom under the 1a cap: "
                                f"{costs.PHASE_CAPS['1a'] - total:.2f}"})
    out.append({"line": "cap_1a", "usd": costs.PHASE_CAPS["1a"], "note": "common.costs"})
    return out


def _fmt(x: float) -> str:
    return f"{x:,.2f}"


def summary_lines(rows: list[dict], p1a: list[dict], scs: dict[str, Scenario],
                  runs: dict[str, Run]) -> list[str]:
    def p(line: str) -> float:
        (r,) = [x for x in p1a if x["line"] == line]
        return r["usd"]

    cap = costs.PHASE_CAPS["1a"]
    warm, cold = runs[SOL_F0_PILOT], runs[SOL_FR_PILOT]
    luna_runs = {c: runs[LUNA_PILOT[c]] for c in R4_CELLS}
    lines = [
        "# sol H1 replication (PREREG §17.4, amendment R4): cost forecast",
        "",
        ("Billed estimate (Flex, cache writes at 1.25 times the input price), from block 1's "
         "measured `results/costs.csv` rows, by `uv run python -m analysis.sol_h1_forecast`. "
         "Forecasts, not measurements. Per-cell lines are in `sol_h1_forecast.csv`, the "
         "phase-1a lines in `sol_h1_phase_1a.csv`."),
        "",
        "## R4 (sol, medium effort, default generator config, 4 observed task cells)",
        "",
        "| Item | Episodes | Central (USD) | Low (USD) |",
        "|---|---|---|---|",
    ]
    for item, label in (("pilot", "Pilot, W-0 and W-n-0 (pilot templates 0-1)"),
                        ("validity", "Validity, F-0, restated and withheld (G1)"),
                        *((f"main_T{T}", f"Main runs at T = {T}, F-0 + W-0 + W-n-0")
                          for T in T_VALUES)):
        (n,) = {r["episodes"] for r in rows if r["item"] == item and r["harness_cell"] == "all"}
        lines.append(f"| {label} | {n:,} | {_fmt(item_total(rows, 'central', item))} | "
                     f"{_fmt(item_total(rows, 'low', item))} |")
    for T in T_VALUES:
        lines.append(f"| **R4 in all, T = {T}** | | **{_fmt(r4_total(rows, 'central', T))}** | "
                     f"{_fmt(r4_total(rows, 'low', T))} |")
    per_cell = "; ".join(f"{r['harness_cell']} {_fmt(r['usd'])}" for r in rows
                         if r["scenario"] == "central" and r["item"] == "main_T100"
                         and r["harness_cell"] != "all")
    lines += ["", f"Main runs per harness cell at T = 100 (central): {per_cell}.", "",
              "**Scenarios.**"]
    for sc in scs.values():
        per = "; ".join(f"{c} {sc.per_episode(c):.4f}" for c in R4_CELLS)
        lines.append(f"- {sc.label}. Forecast per episode on sol (USD): {per}; validity "
                     f"{sc.per_episode('F-0') * sc.validity_factor:.4f}.")
    lines += [
        ("- Why the central basis: sol's F-0 pilot run played its 8 episodes right after the "
         "F-r run had played the same 8 with nearly the same input, so almost all of its "
         f"input came from the cache ({warm.cache_write_tokens:,} cache-write tokens against "
         f"the F-r run's {cold.cache_write_tokens:,}). A main-sweep run plays episodes no "
         "other run has just played, so each call writes its new suffix to the cache, at 1.25 "
         "times the input price; at medium effort sol hardly reasons, so the F-r run's "
         "payloads stand in for a cold F-0 run's. Window cells lose about half of their "
         "prompt caching (luna's pilot read from the cache "
         f"{luna_runs['F-0'].cached_share:.0%} of its input in F-0, "
         f"{luna_runs['W-0'].cached_share:.0%} in W-0 and "
         f"{luna_runs['W-n-0'].cached_share:.0%} in W-n-0), and sol's cached input costs "
         "1/20 of its input price against luna's 1/10, so luna's W/F-0 token mix is priced "
         "at sol's prices."),
        "",
        f"## Phase 1a against its ${cap:,.0f} cap",
        "",
        "| Line | USD |",
        "|---|---|",
        (f"| Spent in phase 1a (`results/costs.csv`, R3's engagement check included) | "
         f"{_fmt(p('spent'))} |"),
        (f"| luna's main sweep (T = {LUNA_T}, 4 replay-off cells) and controls, rough | "
         f"{_fmt(p('luna_main_sweep_and_controls'))} |"),
        (f"| sol's H2 core and validity on `sol-chain`: not run (R3's hard stop) | "
         f"{_fmt(p('sol_h2'))} |"),
    ]
    for T in T_VALUES:
        lines.append(f"| R4 at T = {T}, central (low) | {_fmt(p(f'r4_central_T{T}'))} "
                     f"({_fmt(p(f'r4_low_T{T}'))}) |")
    for T in T_VALUES:
        lines.append(f"| **Total at T = {T}, central (low)** | "
                     f"**{_fmt(p(f'total_central_T{T}'))}** "
                     f"({_fmt(p(f'total_low_T{T}'))}) |")
    lines += [
        "",
        (f"Headroom under the cap, central: {_fmt(cap - p('total_central_T100'))} at T = 100, "
         f"{_fmt(cap - p('total_central_T50'))} at T = 50. Every main-run line scales with "
         "T, which §4.2's rule sets at M1 for luna."),
        "",
        ("Context row (rough, not R4's forecast): luna's lines use its block-1 pilot cost "
         "per episode per cell; its restated control as F-0 episodes at luna's validity/base "
         "factor; each single-turn prompt bounded by one F-0 episode. sol's H2 runs are not "
         "counted: R3's engagement check found NOT_ENGAGED on 2026-10-03, and R3's hard stop "
         "ended H2 on sol (`results/decisions.md`)."),
        "",
        "## Limits",
        "",
        ("- sol's W-0 and W-n-0 have never run: their cost is luna's measured token mix "
         "priced at sol's prices. R4's pilot measures them, and block 3's approval uses that."),
        ("- Near and far episodes are assumed to cost the same per episode: they share their "
         "skeleton (PREREG §2.7). sol's basis ran on far cells only, observed and derived."),
        ("- Small bases: sol's is one run of 8 episodes (2 pilot templates × the 4 far task "
         "cells), luna's one run of 8 per cell (1 pilot template × the 8 task cells)."),
        ("- Lookups add calls in recoverable cells, more in W cells; the luna pilot's 8 "
         "episodes include 4 recoverable ones, so its ratios include some of this."),
        ("- luna's W-0 pilot ran minutes after its F-0 pilot on the same episodes, so some of "
         "its early calls may have been read from F-0's cache; its ratio may be a little low."),
        "- Prices of 2026-09-30 (`harnesses/pricing.py`); Flex assumed served throughout.",
    ]
    return lines


def _csv(rows: list[dict], fields: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: (f"{v:.6g}" if isinstance(v, float) else v) for k, v in r.items()})
    return buf.getvalue()


def build(costs_path: Path = costs.COSTS_CSV, results_root: Path = REPO_ROOT / "results"):
    runs = load_runs(costs_path, results_root)
    scs = scenarios(runs)
    rows = [r for sc in scs.values() for r in forecast_rows(sc)]
    p1a = phase_1a_rows(rows, runs, costs_path)
    return runs, scs, rows, p1a


def write(out_dir: Path, run_id: str, started: str, runs: dict[str, Run], rows: list[dict],
          p1a: list[dict], scs: dict[str, Scenario],
          costs_path: Path = costs.COSTS_CSV) -> Path:
    from common import runmeta

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "sol_h1_forecast.csv").write_text(
        _csv(rows, ["scenario", "item", "harness_cell", "episodes", "usd_per_episode", "usd"]),
        encoding="utf-8", newline="")
    (out_dir / "sol_h1_phase_1a.csv").write_text(_csv(p1a, ["line", "usd", "note"]),
                                                 encoding="utf-8", newline="")
    (out_dir / "summary.md").write_text("\n".join(summary_lines(rows, p1a, scs, runs)) + "\n",
                                        encoding="utf-8", newline="\n")
    config = {"prereg": "PREREG.md §17.4 (amendment R4)",
              "inputs": {"costs_csv": str(costs_path.relative_to(REPO_ROOT))
                         if costs_path.is_relative_to(REPO_ROOT) else str(costs_path),
                         "sol_f0_pilot": SOL_F0_PILOT, "sol_fr_pilot": SOL_FR_PILOT,
                         "luna_pilot": LUNA_PILOT, "luna_validity": list(LUNA_VALIDITY)},
              "design": {"cells": list(R4_CELLS), "observed_task_cells": OBSERVED_TASK_CELLS,
                         "pilot_episodes_per_run": PILOT_EPISODES,
                         "validity_episodes": VALIDITY_EPISODES, "T_values": list(T_VALUES)},
              "context": {"luna_T": LUNA_T,
                          "sol_h2": "not counted: ended by R3's hard stop (2026-10-03)"},
              "price_source_date": pricing.PRICE_SOURCE_DATE,
              "scenarios": {k: sc.label for k, sc in scs.items()}}
    return runmeta.write_meta(
        out_dir, experiment="cost_model", run_id=run_id, cell_or_config="sol_h1_forecast",
        config=config, model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
        repeat_index=None, seeds=None, started_utc=started, finished_utc=runmeta.utc_now(),
        exit_reason="completed", tokens=None, cost_usd=0.0, raw_transcript_path=None,
        outputs=["sol_h1_forecast.csv", "sol_h1_phase_1a.csv", "summary.md"], paid_calls=0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="default: results/cost_model/<UTC>/")
    ap.add_argument("--no-write", action="store_true", help="print only")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    started = datetime.now(UTC)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    runs, scs, rows, p1a = build()
    print("\n".join(summary_lines(rows, p1a, scs, runs)))
    if not args.no_write:
        out = args.out_dir or REPO_ROOT / "results" / "cost_model" / run_id
        meta = write(out, run_id, started.isoformat(timespec="seconds"), runs, rows, p1a,
                     scs)
        print(f"\nwrote {out} ({meta.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
