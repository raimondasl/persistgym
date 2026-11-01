"""R10's check between its pilots and its main runs (PREREG §17.10; $0, blinded).

R10 starts its two main runs only after both pilots, W-np-0 and W-npd-0 in `persistgym_pilot`,
pass these conditions:
1. the run ended `COMPLETED` (meta.json), so no request-side check stop;
2. no episode ended `API_ERROR` (the raw episodes, read for their endings and ids only);
3. the run played exactly the registered pilot: pilot templates 0-1 on the 4 far task cells,
   base episodes, 8 episodes (`registered_episodes`);
4. every request's system prompt ends with the notes separator and the cell's notes text
   (`CellSpec.notes_instruction`), read from the raw transcript;
5. the cost per episode (the run's costs.csv row, billed estimate, over the episodes run) is at
   most `COST_LIMIT`, 1.25 times the forecast's $0.045408;
6. the serving path is R9's: the returned model string is exactly claude-haiku-5-5 (meta.json),
   and the costs row reports the standard tier served and the global inference geo only.

It reports those and nothing else: no outcome, no per-episode token count, nothing PREREG §11
withholds from a pilot. A failed condition means Claude stops and tells the researcher before
any main run. The guard reads the latest check this script writes: R10's main runs refuse
until it says GO for both cells (`harnesses.registered._provenance_pilot_go`).

Run: ``uv run python -m analysis.haiku_provenance_pilot --run RUN_ID --run RUN_ID``. It writes
``results/haiku_provenance_pilot/<UTC>/check.json`` and ``meta.json``; ``--no-write`` only
prints.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from common import costs, runmeta
from harnesses import registered
from harnesses.cells import get_cell

REPO_ROOT = Path(__file__).resolve().parent.parent
PILOT = registered.PILOT_EXPERIMENT
FORECAST_PER_EPISODE = 0.045408
"""R9's billed cost per episode on the 4 far task cells (PREREG §17.10, Budget)."""
COST_LIMIT = 1.25 * FORECAST_PER_EPISODE
OUTPUTS = ("check.json", "meta.json")
MODEL_RETURNED = [registered.HAIKU_MODEL]
"""The model string R9's run returned (results/haiku_notes/20261024T073307Z/)."""


def registered_episodes() -> list[str]:
    """The episode ids of R10's registered pilot: pilot templates 0-1 x the 4 far task cells,
    base episodes."""
    start, stop = registered.HAIKU_PROVENANCE_PILOT_TEMPLATES
    return sorted(f"pilot-{t:06d}/{tc}/base" for t in range(start, stop)
                  for tc in registered.HAIKU_PROVENANCE_TASK_CELLS)


def served_geos(notes: str) -> dict[str, int] | None:
    """The `inference_geos=<geo>:<calls>;...` field of a costs row's notes, or None."""
    for part in notes.split("; "):
        if part.startswith("inference_geos="):
            out = {}
            for entry in part.removeprefix("inference_geos=").split(";"):
                geo, _, n = entry.partition(":")
                out[geo] = int(n) if n.isdigit() else 0
            return out
    return None


def check_run(results: Path, raw: Path, costs_path: Path, run_id: str) -> dict:
    """The conditions for one pilot run of an R10 cell (the module docstring)."""
    meta = json.loads((results / PILOT / run_id / "meta.json").read_text(encoding="utf-8"))
    cell = meta.get("cell_or_config")
    problems = []
    if cell not in registered.HAIKU_PROVENANCE_CELLS:
        problems.append(f"cell {cell!r} is not one of R10's")
    if meta.get("experiment") != PILOT:
        problems.append(f"experiment {meta.get('experiment')!r}")
    if registered.model_family(str(meta.get("model_requested"))) != registered.HAIKU_MODEL:
        problems.append(f"model {meta.get('model_requested')!r}")
    completed = meta.get("exit_reason") == "COMPLETED"
    endings: Counter = Counter()
    ids = []
    for line in (raw / PILOT / run_id / "episodes.jsonl").read_text(
            encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            endings[str(rec.get("exit_reason"))] += 1
            ids.append(str(rec.get("episode_id")))
    episodes = sum(endings.values())
    suffix = None
    requests = bad_system = 0
    if cell in registered.HAIKU_PROVENANCE_CELLS:
        suffix = meta["config"]["harness"]["notes_separator"] + get_cell(cell).notes_instruction
        with gzip.open(raw / PILOT / run_id / "transcript.jsonl.gz", "rt", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                payload = json.loads(line).get("payload") or {}
                requests += 1
                if not str(payload.get("system") or "").endswith(suffix):
                    bad_system += 1
    rows = [r for r in costs.read_rows(costs_path) if r["run_id"] == run_id]
    tier = geos = None
    if len(rows) != 1:
        problems.append(f"{len(rows)} costs.csv rows for the run, not 1")
        per_episode = None
    else:
        row = rows[0]
        spend = costs.spend_usd(*(None if row[k] in (None, "") else float(row[k])
                                  for k in ("cost_usd_list", "cost_usd_billed_est")))
        per_episode = spend / episodes if episodes else None
        tier = row.get("service_tier_served") or None
        geos = served_geos(row.get("notes") or "")
    models = list(meta.get("model_returned") or [])
    conditions = {
        "completed": completed,
        "no_api_error": endings.get("API_ERROR", 0) == 0 and episodes > 0,
        "registered_episodes": sorted(ids) == registered_episodes(),
        "system_prompts_end_with_notes_text": requests > 0 and bad_system == 0,
        "cost_per_episode_within_limit": per_episode is not None and per_episode <= COST_LIMIT,
        "model_string": models == MODEL_RETURNED,
        "standard_tier_global_geo": tier == "standard" and bool(geos) and set(geos) == {"global"},
    }
    return {"run_id": run_id, "cell": cell, "exit_reason": meta.get("exit_reason"),
            "episodes": episodes, "episode_endings": dict(sorted(endings.items())),
            "requests": requests, "requests_without_the_notes_text": bad_system,
            "cost_per_episode_usd": per_episode, "cost_limit_usd": COST_LIMIT,
            "model_returned": models, "service_tier_served": tier, "inference_geos": geos,
            "conditions": conditions, "problems": problems,
            "passed": all(conditions.values()) and not problems}


def check(results: Path, raw: Path, costs_path: Path, run_ids: list[str]) -> dict:
    runs = [check_run(results, raw, costs_path, r) for r in run_ids]
    cells = sorted(r["cell"] for r in runs if r["cell"])
    both = cells == sorted(registered.HAIKU_PROVENANCE_CELLS)
    return {"prereg": registered.R10_REF, "runs": runs, "both_cells_piloted": both,
            "go": both and all(r["passed"] for r in runs)}


def summary(c: dict) -> str:
    lines = [f"R10 pilot check ({c['prereg']}): {'GO' if c['go'] else 'STOP'}"]
    for r in c["runs"]:
        cost = r["cost_per_episode_usd"]
        lines.append(
            f"- {r['run_id']} ({r['cell']}): {r['exit_reason']}, {r['episodes']} episodes "
            f"{r['episode_endings']}, {r['requests']} requests, "
            f"{r['requests_without_the_notes_text']} without the notes text, cost per episode "
            f"{'n/a' if cost is None else f'${cost:.5f}'} (limit ${r['cost_limit_usd']:.5f}), "
            f"model {r['model_returned']}, tier {r['service_tier_served']}, geos "
            f"{r['inference_geos']}; "
            + ", ".join(f"{k} {'yes' if v else 'NO'}" for k, v in r["conditions"].items())
            + (f"; problems: {'; '.join(r['problems'])}" if r["problems"] else ""))
    if not c["both_cells_piloted"]:
        lines.append("- the runs do not pilot both R10 cells once each")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results-root", type=Path, default=REPO_ROOT)
    ap.add_argument("--raw-root", type=Path, default=None)
    ap.add_argument("--costs", type=Path, default=None)
    ap.add_argument("--run", action="append", required=True, metavar="RUN_ID")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    now = datetime.now(UTC)
    results = a.results_root / "results"
    c = check(results, a.raw_root or results / "raw", a.costs or results / "costs.csv", a.run)
    sys.stdout.reconfigure(encoding="utf-8")
    print(summary(c), end="")
    if a.no_write:
        return 0 if c["go"] else 1
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    out = results / "haiku_provenance_pilot" / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "check.json").write_text(json.dumps(c, indent=2), encoding="utf-8", newline="\n")
    runmeta.write_meta(
        out, git=runmeta.git_state(), experiment="haiku_provenance_pilot", run_id=run_id,
        cell_or_config=",".join(registered.HAIKU_PROVENANCE_CELLS),
        config={"runs": a.run, "cost_limit_usd": COST_LIMIT, "go": c["go"]},
        model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
        repeat_index=0, seeds={}, started_utc=now.isoformat(timespec="seconds"),
        finished_utc=runmeta.utc_now(), exit_reason="completed", tokens=None, cost_usd=0.0,
        raw_transcript_path=None, outputs=list(OUTPUTS), paid_calls=0, runs=a.run)
    print(f"written: {out}", file=sys.stderr)
    return 0 if c["go"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
