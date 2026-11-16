"""R13's check between its pilots and its main runs (PREREG §17.13; $0, blinded).

R13 pilots each of `registered.R13_PILOTS`' (model, cell) pairs in `persistgym_pilot`: Haiku's
Σ-n-0 and W-nk-0. If a pilot ends other than COMPLETED, or costs more than 1.10 times its high
forecast per episode, Claude stops and tells the researcher before any main run (§17.13, What
it changes, 3). Per pilot run, it checks:

1. The run ended `COMPLETED` (meta.json), so no request-side check stopped it.
2. No episode ended `API_ERROR` or `AGENT_ERROR` (four failed summaries end an episode
   `AGENT_ERROR`), read from the raw episodes for their endings and ids only.
3. The run played exactly the registered pilot: pilot templates from `R13_PILOT_TEMPLATES` on
   the pair's task cells, base episodes, at most `R13_PILOT_MAX_EPISODES` episodes, as
   `harnesses.r13_rounds` plays it (`registered_episodes`).
4. The instructions: every step request's system prompt ends with the notes separator and the
   cell's notes text (`CellSpec.notes_instruction`), and every summary request's is the run's
   summary system prompt (meta.json's harness config), read from the raw transcript.
5. The request-side check, again: every recorded body passes
   `harnesses.wire.MESSAGES.check_payload` at the registered effort and the 32,000 cap, so the
   leading bridge or pinned block is the only repeated role.
6. Σ-n-0: the summaries, counted per episode from the transcript (summary requests, and the
   step requests that start with a bridge). W-nk-0: the pinned block's bookkeeping on every step
   request: the info keys are there, the kept start never moves back, the block is the first
   message exactly when `pinned_index` is 0 (it then starts with the block's fixed opening, and
   `pinned_turns` are dropped turns), and no request is over W.
7. The cost per episode (the run's costs.csv row, billed estimate, over the episodes run) is at
   most `FACTOR` (1.10) times the high per-episode cost of the latest committed forecast
   (`results/r13_forecast/<UTC>/forecast.json`, ``per_episode_usd``).
8. The serving path: the returned model string is exactly the pair's model (meta.json), and the
   costs row reports the standard tier served and the global inference geo only, in one row.

It reports those and nothing else: no outcome, no per-episode token count, nothing PREREG §11
withholds from a pilot. With no ``--run``, it checks the newest pilot of each pair. It is GO
when every pair has a pilot and every pilot checked passes.

Run: ``uv run python -m analysis.r13_pilot [--run RUN_ID ...]``. It writes
``results/r13_pilot/<UTC>/check.json`` and ``meta.json``. ``--no-write`` only prints.
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
from harnesses.cells import PINNED_REPLIES_TEMPLATE, get_cell
from harnesses.config import ARC_SUMMARY_BRIDGE_TEMPLATE, DEFAULT_MAX_OUTPUT_TOKENS
from harnesses.wire import MESSAGES, RequestCheckFailed

REPO_ROOT = Path(__file__).resolve().parent.parent
PILOT = registered.PILOT_EXPERIMENT
FACTOR = 1.10
"""§17.13: a pilot above 1.10 times its high forecast per episode stops R13 before any main run."""
OUT_NAME = "r13_pilot"
OUTPUTS = ("check.json", "meta.json")
SIGMA_CELL, PINNED_CELL = "Σ-n-0", "W-nk-0"
PINNED_KEYS = ("pinned_index", "pinned_turns", "pinned_reply_tokens", "pinned_tokens",
               "pinned_over_cap", "pinned_left_out")
PINNED_PREFIX = PINNED_REPLIES_TEMPLATE.split("{replies}")[0]
BRIDGE_PREFIX = ARC_SUMMARY_BRIDGE_TEMPLATE.split("{summary}")[0]


def latest_forecast(results: Path) -> tuple[str, dict]:
    """The latest committed R13 forecast: its folder name and its content."""
    folder = results / "r13_forecast"
    found = sorted(p for p in folder.iterdir() if (p / "forecast.json").is_file()) \
        if folder.is_dir() else []
    if not found:
        raise SystemExit(f"refused: no forecast under {folder}")
    return found[-1].name, json.loads((found[-1] / "forecast.json").read_text(encoding="utf-8"))


def registered_episodes(model: str, cell: str) -> list[str]:
    """The episode ids of the pair's registered pilot, as `harnesses.r13_rounds` plays it: the
    first pilot templates that fit in `R13_PILOT_MAX_EPISODES` on the pair's task cells."""
    task_cells = registered.R13_PILOTS[(model, cell)]
    first, stop = registered.R13_PILOT_TEMPLATES
    n = min(stop - first, registered.R13_PILOT_MAX_EPISODES // len(task_cells))
    return sorted(f"pilot-{t:06d}/{tc}/base" for t in range(first, first + n) for tc in task_cells)


def newest_pilots(results: Path) -> dict[tuple[str, str], str]:
    """The newest `persistgym_pilot` run of each R13 pilot pair, by its start time."""
    found: dict[tuple[str, str], tuple[str, str]] = {}
    base = results / PILOT
    for d in sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []:
        path = d / "meta.json"
        if not path.is_file():
            continue
        m = json.loads(path.read_text(encoding="utf-8"))
        key = (str(m.get("model_requested")), str(m.get("cell_or_config")))
        if key not in registered.R13_PILOTS:
            continue
        order = (str(m.get("started_utc") or ""), str(m.get("run_id") or d.name))
        if key not in found or order > found[key]:
            found[key] = order
    return {key: order[1] for key, order in found.items()}


def _first_text(payload: dict) -> str:
    msgs = payload.get("messages") or []
    if not msgs or not isinstance(msgs[0], dict):
        return ""
    return "".join(str(b.get("text") or "") for b in msgs[0].get("content") or []
                   if isinstance(b, dict))


def transcript_info(path: Path, cell: str, notes_suffix: str, summary_system: str | None,
                    effort: str) -> dict:
    """Conditions 4 to 6 on a pilot's raw transcript (the module docstring)."""
    out = {"requests": 0, "step_requests": 0, "summary_requests": 0,
           "steps_without_the_notes_text": 0, "summaries_without_the_summary_prompt": 0,
           "bodies_refused_by_the_request_check": 0}
    summaries: Counter = Counter()
    bridged: Counter = Counter()
    starts: dict[str, int] = {}
    pinned = {"step_requests": 0, "inconsistent": 0, "over_W": 0, "with_block": 0}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            d = json.loads(line)
            payload = d.get("payload") or {}
            eid = str(d.get("episode_id"))
            out["requests"] += 1
            try:
                MESSAGES.check_payload(payload, effort=effort,
                                       max_tokens=DEFAULT_MAX_OUTPUT_TOKENS)
            except RequestCheckFailed:
                out["bodies_refused_by_the_request_check"] += 1
            system = str(payload.get("system") or "")
            if d.get("kind") == "summary":
                out["summary_requests"] += 1
                summaries[eid] += 1
                out["summaries_without_the_summary_prompt"] += system != (summary_system or "")
                continue
            out["step_requests"] += 1
            out["steps_without_the_notes_text"] += not system.endswith(notes_suffix)
            first = _first_text(payload)
            if first.startswith(BRIDGE_PREFIX):
                bridged[eid] += 1
            if cell != PINNED_CELL:
                continue
            info = d.get("info") or {}
            pinned["step_requests"] += 1
            keep, prev = info.get("keep_start"), starts.get(eid, 0)
            index = info.get("pinned_index")
            turns = info.get("pinned_turns")
            lead = first.startswith(PINNED_PREFIX)
            bad = (any(k not in info for k in PINNED_KEYS) or not isinstance(keep, int)
                   or keep < prev or index not in (0, None) or (index == 0) != lead
                   or not isinstance(turns, list) or (index == 0) != bool(turns)
                   or any(not isinstance(t, int) or not 0 <= t < keep for t in turns))
            pinned["inconsistent"] += bool(bad)
            pinned["over_W"] += bool(info.get("over_W"))
            pinned["with_block"] += lead
            if isinstance(keep, int):
                starts[eid] = keep
    if cell == SIGMA_CELL:
        out["summaries"] = {"episodes_with_a_summary": len(summaries),
                            "summary_requests_per_episode": dict(sorted(summaries.items())),
                            "step_requests_with_a_bridge": sum(bridged.values())}
    if cell == PINNED_CELL:
        out["pinned"] = pinned
    return out


def check_run(results: Path, raw: Path, rows: list[dict], forecast: dict, run_id: str) -> dict:
    """The conditions for one pilot run (the module docstring)."""
    meta = json.loads((results / PILOT / run_id / "meta.json").read_text(encoding="utf-8"))
    model, cell = str(meta.get("model_requested")), str(meta.get("cell_or_config"))
    problems = []
    if meta.get("experiment") != PILOT:
        problems.append(f"experiment {meta.get('experiment')!r}")
    pair = (model, cell) in registered.R13_PILOTS
    if not pair:
        problems.append(f"({model}, {cell}) is not one of R13's pilot pairs")
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
    harness = (meta.get("config") or {}).get("harness") or {}
    suffix = str(harness.get("notes_separator", "\n")) + (spec.notes_instruction or "")
    info = transcript_info(raw / PILOT / run_id / "transcript.jsonl.gz", cell, suffix,
                           harness.get("summary_system_prompt"),
                           registered.registered_effort(model))
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
    sums = info.get("summaries")
    pin = info.get("pinned")
    conditions = {
        "completed": meta.get("exit_reason") == "COMPLETED",
        "no_api_or_agent_error": (endings.get("API_ERROR", 0) == 0
                                  and endings.get("AGENT_ERROR", 0) == 0 and episodes > 0),
        "registered_episodes": pair and sorted(ids) == registered_episodes(model, cell),
        "instructions_on_every_request": (
            info["requests"] > 0 and info["steps_without_the_notes_text"] == 0
            and info["summaries_without_the_summary_prompt"] == 0),
        "every_body_passes_the_request_check": (
            info["requests"] > 0 and info["bodies_refused_by_the_request_check"] == 0),
        "summaries_seen": (sums["episodes_with_a_summary"] > 0) if sums is not None else None,
        "pinned_block_info_consistent": (
            pin["step_requests"] > 0 and pin["inconsistent"] == 0 and pin["over_W"] == 0)
        if pin is not None else None,
        "cost_per_episode_within_limit": (per_episode is not None and limit is not None
                                          and per_episode <= limit),
        "model_string": models == [model],
        "standard_tier_global_geo": tier == "standard" and bool(geos) and set(geos) == {"global"},
    }
    return {"run_id": run_id, "model": model, "cell": cell, "exit_reason": meta.get("exit_reason"),
            "episodes": episodes, "episode_endings": dict(sorted(endings.items())),
            "transcript": info, "cost_per_episode_usd": per_episode,
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
    missing = [f"{m} {c}" for m, c in registered.R13_PILOTS if (m, c) not in seen]
    dup = sorted(f"{m} {c}" for (m, c), n in Counter((r["model"], r["cell"]) for r in runs).items()
                 if n > 1)
    return {"prereg": registered.R13_REF, "forecast": f"results/r13_forecast/{folder}",
            "factor": FACTOR, "runs": runs, "pairs_without_a_pilot": missing,
            "pairs_checked_twice": dup,
            "go": not missing and not dup and all(r["passed"] for r in runs)}


def summary(c: dict) -> str:
    lines = [(f"R13 pilot check ({c['prereg']}, forecast {c['forecast']}, limit {c['factor']}x "
              f"its high per-episode cost): {'GO' if c['go'] else 'STOP'}")]
    for r in c["runs"]:
        cost, limit, t = r["cost_per_episode_usd"], r["cost_limit_usd"], r["transcript"]
        extra = (f", {t['requests']} requests ({t['summary_requests']} summary), "
                 f"{t['steps_without_the_notes_text']} steps without the notes text, "
                 f"{t['summaries_without_the_summary_prompt']} summaries without the summary "
                 f"prompt, {t['bodies_refused_by_the_request_check']} bodies the request check "
                 "refuses")
        if t.get("summaries") is not None:
            s = t["summaries"]
            extra += (f", {s['episodes_with_a_summary']} episodes with a summary, "
                      f"{s['step_requests_with_a_bridge']} step requests with a bridge")
        if t.get("pinned") is not None:
            p = t["pinned"]
            extra += (f", {p['step_requests']} step requests, {p['with_block']} with the block, "
                      f"{p['inconsistent']} with inconsistent block info, {p['over_W']} over W")
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
    (out / "check.json").write_text(json.dumps(c, indent=2, ensure_ascii=False),
                                    encoding="utf-8", newline="\n")
    runmeta.write_meta(
        out, git=runmeta.git_state(), experiment=OUT_NAME, run_id=run_id,
        cell_or_config=",".join(f"{m} {cell}" for m, cell in registered.R13_PILOTS),
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
