"""R12's check between its pilots and its main runs (PREREG §17.12; results/decisions.md, 2026-11-11; $0, blinded).

The committed form of the check Claude ran on 2026-11-12 before R12's main runs. R12 pilots each
of `registered.R12_PILOTS`' (model, cell) pairs in `persistgym_pilot`. If a pilot ends other
than COMPLETED, or costs more than 1.10 times its high forecast per episode, Claude stops and
tells the researcher before any main run (§17.12, What it changes, 3). Per pilot run, it checks:

1. The run ended `COMPLETED` (meta.json), so no request-side check stopped it.
2. No episode ended `API_ERROR` (the raw episodes, read for their endings and ids only).
3. The run played exactly the registered pilot: pilot templates from `R12_PILOT_TEMPLATES` on
   the pair's task cells, base episodes, at most `R12_PILOT_MAX_EPISODES` episodes, as
   `harnesses.r12_rounds` plays it (`registered_episodes`).
4. Notes cells: every request's system prompt ends with the notes separator and the cell's notes
   text (`CellSpec.notes_instruction`), read from the raw transcript.
5. W-b-0: every step request's info names the block rule, its kept start never moves back, it
   moves exactly when the info says ``block_drop``, and no request is over W.
6. The cost per episode (the run's costs.csv row, billed estimate, over the episodes run) is at
   most `FACTOR` (1.10) times the high per-episode cost of the latest committed forecast
   (`results/r12_forecast/<UTC>/forecast.json`, ``per_episode_usd``).
7. The serving path: the returned model string is exactly the pair's model (meta.json), and the
   costs row reports the standard tier served and the global inference geo only, in one row.

It reports those and nothing else: no outcome, no per-episode token count, nothing PREREG §11
withholds from a pilot. With no ``--run``, it checks the newest pilot of each pair. It is GO
when every pair has a pilot and every pilot checked passes.

Run: ``uv run python -m analysis.r12_pilot [--run RUN_ID ...]``. It writes
``results/r12_pilot/<UTC>/check.json`` and ``meta.json``. ``--no-write`` only prints.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from analysis.haiku_provenance_pilot import served_geos
from common import costs, runmeta
from harnesses import registered
from harnesses.cells import get_cell

REPO_ROOT = Path(__file__).resolve().parent.parent
PILOT = registered.PILOT_EXPERIMENT
FACTOR = 1.10
"""§17.12: a pilot above 1.10 times its high forecast per episode stops R12 before any main run."""
OUT_NAME = "r12_pilot"
OUTPUTS = ("check.json", "meta.json")
BLOCK_CELL = "W-b-0"


def latest_forecast(results: Path) -> tuple[str, dict]:
    """The latest committed R12 forecast: its folder name and its content."""
    folder = results / "r12_forecast"
    found = sorted(p for p in folder.iterdir() if (p / "forecast.json").is_file()) \
        if folder.is_dir() else []
    if not found:
        raise SystemExit(f"refused: no forecast under {folder}")
    return found[-1].name, json.loads((found[-1] / "forecast.json").read_text(encoding="utf-8"))


def registered_episodes(model: str, cell: str) -> list[str]:
    """The episode ids of the pair's registered pilot, as `harnesses.r12_rounds` plays it: the
    first pilot templates that fit in `R12_PILOT_MAX_EPISODES` on the pair's task cells."""
    task_cells = registered.R12_PILOTS[(model, cell)]
    first, stop = registered.R12_PILOT_TEMPLATES
    n = min(stop - first, registered.R12_PILOT_MAX_EPISODES // len(task_cells))
    return sorted(f"pilot-{t:06d}/{tc}/base" for t in range(first, first + n) for tc in task_cells)


def newest_pilots(results: Path) -> dict[tuple[str, str], str]:
    """The newest `persistgym_pilot` run of each R12 pilot pair, by its start time."""
    found: dict[tuple[str, str], tuple[str, str]] = {}
    base = results / PILOT
    for d in sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []:
        path = d / "meta.json"
        if not path.is_file():
            continue
        m = json.loads(path.read_text(encoding="utf-8"))
        key = (str(m.get("model_requested")), str(m.get("cell_or_config")))
        if key not in registered.R12_PILOTS:
            continue
        order = (str(m.get("started_utc") or ""), str(m.get("run_id") or d.name))
        if key not in found or order > found[key]:
            found[key] = order
    return {key: order[1] for key, order in found.items()}


def block_info(path: Path) -> dict:
    """Condition 5 on a W-b-0 pilot's transcript: the step requests read, those whose info
    breaks the block rule's bookkeeping, those over W, and the drops."""
    starts: dict[str, int] = {}
    steps = bad = over = drops = 0
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("kind") != "step":
                continue
            info = d.get("info") or {}
            steps += 1
            eid, keep = d.get("episode_id"), info.get("keep_start")
            prev = starts.get(eid, 0)
            bad += (info.get("truncation") != "block" or not isinstance(keep, int) or keep < prev
                    or bool(info.get("block_drop")) != (keep != prev))
            drops += bool(info.get("block_drop"))
            over += bool(info.get("over_W"))
            if isinstance(keep, int):
                starts[eid] = keep
    return {"step_requests": steps, "inconsistent": bad, "over_W": over, "drops": drops}


def check_run(results: Path, raw: Path, rows: list[dict], forecast: dict, run_id: str) -> dict:
    """The conditions for one pilot run (the module docstring)."""
    meta = json.loads((results / PILOT / run_id / "meta.json").read_text(encoding="utf-8"))
    model, cell = str(meta.get("model_requested")), str(meta.get("cell_or_config"))
    problems = []
    if meta.get("experiment") != PILOT:
        problems.append(f"experiment {meta.get('experiment')!r}")
    pair = (model, cell) in registered.R12_PILOTS
    if not pair:
        problems.append(f"({model}, {cell}) is not one of R12's pilot pairs")
    endings: Counter = Counter()
    ids = []
    for line in (raw / PILOT / run_id / "episodes.jsonl").read_text(
            encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            endings[str(rec.get("exit_reason"))] += 1
            ids.append(str(rec.get("episode_id")))
    episodes = sum(endings.values())
    spec = get_cell(cell)
    transcript = raw / PILOT / run_id / "transcript.jsonl.gz"
    requests = bad_system = 0
    if spec.notes:
        suffix = meta["config"]["harness"]["notes_separator"] + spec.notes_instruction
        with gzip.open(transcript, "rt", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                payload = json.loads(line).get("payload") or {}
                requests += 1
                if not str(payload.get("system") or "").endswith(suffix):
                    bad_system += 1
    block = block_info(transcript) if cell == BLOCK_CELL else None
    mine = [r for r in rows if r["run_id"] == run_id]
    per_episode = tier = geos = None
    if len(mine) == 1:
        row = mine[0]
        spend = costs.spend_usd(*(None if row[k] in (None, "") else float(row[k])
                                  for k in ("cost_usd_list", "cost_usd_billed_est")))
        per_episode = spend / episodes if episodes else None
        tier = row.get("service_tier_served") or None
        geos = served_geos(row.get("notes") or "")
    else:
        problems.append(f"{len(mine)} costs.csv rows for the run, not 1")
    high = (forecast.get("per_episode_usd") or {}).get(f"{model} {cell}")
    limit = None if high is None else FACTOR * float(high[1])
    if limit is None:
        problems.append(f"the forecast has no per-episode cost for {model} {cell}")
    models = list(meta.get("model_returned") or [])
    conditions = {
        "completed": meta.get("exit_reason") == "COMPLETED",
        "no_api_error": endings.get("API_ERROR", 0) == 0 and episodes > 0,
        "registered_episodes": pair and sorted(ids) == registered_episodes(model, cell),
        "notes_text_on_every_request": (requests > 0 and bad_system == 0) if spec.notes else None,
        "block_rule_info_consistent": (block["step_requests"] > 0 and block["inconsistent"] == 0
                                       and block["over_W"] == 0) if block else None,
        "cost_per_episode_within_limit": (per_episode is not None and limit is not None
                                          and per_episode <= limit),
        "model_string": models == [model],
        "standard_tier_global_geo": tier == "standard" and bool(geos) and set(geos) == {"global"},
    }
    return {"run_id": run_id, "model": model, "cell": cell, "exit_reason": meta.get("exit_reason"),
            "episodes": episodes, "episode_endings": dict(sorted(endings.items())),
            "requests": requests if spec.notes else None,
            "requests_without_the_notes_text": bad_system if spec.notes else None,
            "block_rule": block, "cost_per_episode_usd": per_episode,
            "high_forecast_per_episode_usd": None if high is None else float(high[1]),
            "cost_limit_usd": limit, "model_returned": models, "service_tier_served": tier,
            "inference_geos": geos, "conditions": conditions, "problems": problems,
            "passed": all(v is not False for v in conditions.values()) and not problems}


def check(results: Path, raw: Path, costs_path: Path, run_ids: list[str] | None) -> dict:
    """Every pilot's conditions, and GO when every pair has a pilot that passed."""
    folder, forecast = latest_forecast(results)
    chosen = list(run_ids) if run_ids else list(newest_pilots(results).values())
    rows = costs.read_rows(costs_path)
    runs = [check_run(results, raw, rows, forecast, r) for r in chosen]
    seen = {(r["model"], r["cell"]) for r in runs}
    missing = [f"{m} {c}" for m, c in registered.R12_PILOTS if (m, c) not in seen]
    dup = sorted(f"{m} {c}" for (m, c), n in Counter((r["model"], r["cell"]) for r in runs).items()
                 if n > 1)
    return {"prereg": registered.R12_REF, "forecast": f"results/r12_forecast/{folder}",
            "factor": FACTOR, "runs": runs, "pairs_without_a_pilot": missing,
            "pairs_checked_twice": dup,
            "go": not missing and not dup and all(r["passed"] for r in runs)}


def summary(c: dict) -> str:
    lines = [(f"R12 pilot check ({c['prereg']}, forecast {c['forecast']}, limit {c['factor']}x "
              f"its high per-episode cost): {'GO' if c['go'] else 'STOP'}")]
    for r in c["runs"]:
        cost, limit = r["cost_per_episode_usd"], r["cost_limit_usd"]
        extra = ""
        if r["requests"] is not None:
            extra += (f", {r['requests']} requests, {r['requests_without_the_notes_text']} "
                      "without the notes text")
        if r["block_rule"] is not None:
            b = r["block_rule"]
            extra += (f", {b['step_requests']} step requests, {b['inconsistent']} with "
                      f"inconsistent block info, {b['over_W']} over W, {b['drops']} drops")
        lines.append(
            f"- {r['run_id']} ({r['model']} {r['cell']}): {r['exit_reason']}, {r['episodes']} "
            f"episodes {r['episode_endings']}{extra}, cost per episode "
            f"{'n/a' if cost is None else f'${cost:.5f}'} (limit "
            f"{'n/a' if limit is None else f'${limit:.5f}'}), model {r['model_returned']}, tier "
            f"{r['service_tier_served']}, geos {r['inference_geos']}: "
            + ", ".join(f"{k} {'yes' if v else 'NO'}" for k, v in r["conditions"].items()
                        if v is not None)
            + (f". Problems: {'; '.join(r['problems'])}" if r["problems"] else ""))
    for p in c["pairs_without_a_pilot"]:
        lines.append(f"- no pilot of {p}")
    for p in c["pairs_checked_twice"]:
        lines.append(f"- {p} is checked more than once")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results-root", type=Path, default=REPO_ROOT)
    ap.add_argument("--raw-root", type=Path, default=None)
    ap.add_argument("--costs", type=Path, default=None)
    ap.add_argument("--run", action="append", default=[], metavar="RUN_ID")
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
    out = results / OUT_NAME / run_id
    try:
        out.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        print(f"refused: a check was already written at {run_id}. Run it again.",
              file=sys.stderr)
        return 2
    (out / "check.json").write_text(json.dumps(c, indent=2), encoding="utf-8", newline="\n")
    runmeta.write_meta(
        out, git=runmeta.git_state(), experiment=OUT_NAME, run_id=run_id,
        cell_or_config=",".join(f"{m} {cell}" for m, cell in registered.R12_PILOTS),
        config={"runs": [r["run_id"] for r in c["runs"]], "named": bool(a.run),
                "forecast": c["forecast"], "factor": FACTOR, "go": c["go"]},
        model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
        repeat_index=0, seeds={}, started_utc=now.isoformat(timespec="seconds"),
        finished_utc=runmeta.utc_now(), exit_reason="completed", tokens=None, cost_usd=0.0,
        raw_transcript_path=None, outputs=list(OUTPUTS), paid_calls=0,
        runs=[r["run_id"] for r in c["runs"]])
    print(f"written: {out}", file=sys.stderr)
    return 0 if c["go"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
