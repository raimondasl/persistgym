"""Where R11's stop ends its run, by a simulation of the spend reservations, and why the stop sits
below the block's limit (PREREG §17.11; $0).

R11's block allows at most $17.38, the researcher's condition. Two things follow.

1. **The margin.** The transport reads its stop once per send, before a send's attempts
   (`harnesses/paid_transport.py`), and a lone call passes the gate, so a run can end above its
   planned spend by one send. `most_one_send` bounds that: `MAX_ATTEMPTS` attempts, each at R9's
   largest prompt, all of it a cache write, and at the 32,000-token output cap, in the dearest
   geo. The run's planned spend, `registered.HAIKU_CONTROL_PLANNED_USD`, sits at least that far
   below the block's limit.
2. **The stop.** A parallel run cannot use the last part of its planned spend
   (`harnesses/DESIGN.md` §7.6): it starts an episode only if spent + reserved + estimate <=
   planned, where the estimate is `ESTIMATE_FACTOR` times the largest spend of a finished episode,
   and all that the planned spend leaves until one has finished, so episodes play one at a time
   until then. This script plays that rule on R9's own per-episode costs on the 2 task cells, in
   the run's order, and at another mean cost by scaling them. Each episode's cost accrues evenly
   over its play, whose length is its cost. That is a simplification, so the results are
   approximate, and the run's own records replace them.

Run: ``uv run python -m analysis.haiku_control_forecast``. It writes
``results/haiku_control_forecast/<UTC>/forecast.json`` and ``meta.json``, and prints the forecast.
With ``--no-write`` it only prints.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from analysis import persistgym_h1h3 as hh
from common import runmeta
from harnesses import pricing, registered
from harnesses.config import DEFAULT_MAX_OUTPUT_TOKENS
from harnesses.parallel import ESTIMATE_FACTOR
from persistgym.episode import ALL_CELLS

REPO_ROOT = Path(__file__).resolve().parent.parent
R9_RUN = "20261024T060051Z-W-n-0-claude-haiku-5-5"
PARALLEL = 2
MAX_ATTEMPTS = 6
"""`harnesses.paid_transport`: the attempts one send can make, each recorded in the ledger."""
R10_COST = 0.0552
"""R10's W-np-0 continuation: its cost per episode ($43.26 for 784 episodes)."""


def most_one_send(max_prompt_tokens: int) -> float:
    """The most one send can add to the ledger after the stop has passed it (module docstring)."""
    price = pricing.price_for(registered.HAIKU_MODEL)
    worst_geo = max(dict(price.geo_multipliers).values())
    one = (max_prompt_tokens * price.input * pricing.CACHE_WRITE_MULTIPLIER
           + DEFAULT_MAX_OUTPUT_TOKENS * price.output) / 1_000_000
    return one * MAX_ATTEMPTS * worst_geo


def episodes_started(costs: list[float], planned: float, parallel: int,
                     factor: float = ESTIMATE_FACTOR) -> tuple[int, float]:
    """How many of `costs` start, in order, under §7.6's rule, and what they spend."""
    spent, biggest, started, clock = 0.0, 0.0, 0, 0.0
    flight: list[tuple[float, float, float]] = []  # start, cost, reservation

    def spent_now() -> float:
        return spent + sum(min(clock - s, c) for s, c, _ in flight)

    def reserved_now() -> float:
        return sum(max(r - min(clock - s, c), 0.0) for s, c, r in flight)

    while True:
        while started < len(costs) and len(flight) < parallel:
            if biggest == 0.0 and flight:
                break
            estimate = planned - spent_now() if biggest == 0.0 else factor * biggest
            if spent_now() + reserved_now() + estimate > planned:
                break
            flight.append((clock, costs[started], estimate))
            started += 1
        if not flight:
            return started, spent
        first = min(flight, key=lambda f: f[0] + f[1])
        clock = first[0] + first[1]
        flight.remove(first)
        spent += first[1]
        biggest = max(biggest, first[1])


def r9_costs(root: Path) -> list[float]:
    """R9's billed cost per episode on R11's task cells, in the run's order."""
    path = root / "results" / registered.HAIKU_NOTES_EXPERIMENT / R9_RUN / "episodes.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    cost = {(hh.template_index(r["template_id"]), r["task_cell"]): float(r["cost_usd_billed_est"])
            for r in rows if r["task_cell"] in registered.HAIKU_CONTROL_TASK_CELLS}
    order = [c.id for c in ALL_CELLS if c.id in registered.HAIKU_CONTROL_TASK_CELLS]
    return [cost[t, c] for t in range(registered.HAIKU_T) for c in order]


def forecast(root: Path) -> dict:
    costs = r9_costs(root)
    total = sum(costs)
    meta = json.loads((root / "results" / registered.HAIKU_NOTES_EXPERIMENT / R9_RUN
                       / "meta.json").read_text(encoding="utf-8"))
    largest = int(meta["prompt_size"]["max_prompt_tokens"])
    planned = registered.HAIKU_CONTROL_PLANNED_USD
    out = {"prereg": registered.R11_REF, "max_usd": registered.HAIKU_CONTROL_MAX_USD,
           "planned_usd": planned, "parallel": PARALLEL, "source": R9_RUN,
           "episodes": len(costs), "r9_spend_usd": total,
           "r9_cost_per_episode": total / len(costs), "r9_max_prompt_tokens": largest,
           "most_one_send_usd": most_one_send(largest), "cases": {}}
    for name, mean in (("at R9's cost per episode", total / len(costs)),
                       ("at R10's W-np-0 continuation's cost per episode", R10_COST)):
        n, spent = episodes_started([c * mean / (total / len(costs)) for c in costs], planned,
                                    PARALLEL)
        out["cases"][name] = {"cost_per_episode": mean, "episodes_started": n,
                              "whole_templates": n // len(registered.HAIKU_CONTROL_TASK_CELLS),
                              "spent_usd": spent}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    now = datetime.now(UTC)
    r = forecast(REPO_ROOT)
    print(json.dumps(r, indent=2))
    if a.no_write:
        return 0
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    out = REPO_ROOT / "results" / "haiku_control_forecast" / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "forecast.json").write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8",
                                       newline="\n")
    runmeta.write_meta(
        out, git=runmeta.git_state(), experiment="haiku_control_forecast", run_id=run_id,
        cell_or_config=registered.HAIKU_CONTROL_CELL,
        config={"planned_usd": r["planned_usd"], "max_usd": r["max_usd"], "parallel": PARALLEL,
                "source": R9_RUN, "r10_cost": R10_COST, "max_attempts": MAX_ATTEMPTS},
        model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
        repeat_index=0, seeds={}, started_utc=now.isoformat(timespec="seconds"),
        finished_utc=runmeta.utc_now(), exit_reason="completed", tokens=None, cost_usd=0.0,
        raw_transcript_path=None, outputs=["forecast.json", "meta.json"], paid_calls=0)
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
