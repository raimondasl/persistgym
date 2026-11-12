"""Account by hand for R12's Sonnet F-0 run killed by a session restart ($0).

`harnesses account-run` cannot do it: it rebuilds Responses API runs only, and refuses a run
interrupted for a reason its files do not show. This script follows its steps with the repo's
own code, from the run's raw files:

1. The run as `harnesses account-run` builds it from run_plan.json (`cli` helpers).
2. The costs row: `pricing.UsageLedger` fed every recorded response in call order (the 177
   complete transcript lines, with the runner's per-call timings), the one call whose
   transcript line was cut off (its usage and cost from its episode's totals in episodes.jsonl,
   less the episode's other calls), and the 24 calls of the 2 abandoned in-flight episodes.
   Checked: each other finished episode's ledger totals equal its episodes.jsonl totals.
   Built by `paid_transport.build_costs_row`, as `finalize` builds it, plus a note.
3. summary.json (`blinding.run_summary`) and meta.json (`runner._write_meta`, exit reason
   ERROR:ProcessKilled, with a `recovered` field).
4. The raw transcript: the cut-off gzip is kept as transcript.jsonl.gz.cut, and
   transcript.jsonl.gz is rewritten with its 177 complete lines, so readers can open it.
5. The last-run record, the spend reservation (by its id), and the lock (deleted by hand, as
   paidlock's message says for a crashed run, after checking it is this run's and its process
   is gone).

Run from the repo root: `uv run python drafts/r12_ops/account_killed_f0.py` (dry run), then
with `--write`.

**Provenance.** It ran once with `--write` on 2026-11-12 at about 22:25 UTC, from
drafts/r12_ops/account_killed_f0.py (gitignored), and its notes and `recovered` text name that
path. It is committed here so that the row and files it wrote come from a committed script. It
differs from what ran only by lint fixes, with no change in behaviour: an unused import and
unused `noqa` comments removed, and the `dict(...)` call in `build` written as a literal. It
must not be run again: the run is accounted for, and it refuses once the row exists. The
`meta.json` cost note was added by hand after it ran (results/decisions.md, 2026-11-12).
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys
import types
import zlib
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

REPO = Path.cwd()
sys.path.insert(0, str(REPO))

from common import costs, paidlock, runmeta
from harnesses import account, blinding, cli, registered, runner
from harnesses.cells import get_cell
from harnesses.paid_transport import build_costs_row
from harnesses.pricing import UsageLedger

RUN_ID = "20261112T205954Z-F-0-claude-sonnet-5-5"
EXP = registered.R12_SONNET_EXPERIMENT
STREAM = "persistgym"
EXIT = "ERROR:ProcessKilled"
CAUSE = ("the process was killed at about 21:02 UTC on 2026-11-12, when the Claude Code session "
         "that had started it as a background task restarted (the researcher thinks an "
         "application update caused it), so finalize never ran")
RESULTS = REPO / "results"
OUT = RESULTS / EXP / RUN_ID
RAW = RESULTS / "raw" / EXP / RUN_ID
LOCK = paidlock.lock_path(runmeta.REPO_ROOT, STREAM)


def gunzip_partial(data: bytes) -> tuple[list[str], str]:
    out, rest = [], data
    while rest:
        d = zlib.decompressobj(31)
        out.append(d.decompress(rest))
        if not d.eof:
            break
        rest = d.unused_data
    lines = b"".join(out).decode("utf-8").split("\n")
    return [x for x in lines[:-1] if x.strip()], lines[-1]


def build():
    plan_path, plan = account.find_plan(RESULTS / "raw", RUN_ID, EXP)
    args = argparse.Namespace(**account.run_arguments(plan, {}, cli._run_defaults()))
    if args.effort is None:
        args.effort = registered.registered_effort(args.model)
    cell = get_cell(args.cell)
    matrix = cli._run_matrix(args)
    episodes = matrix.episodes(args.split, args.start,
                               cli._gen_config(args.gen_preset, args.gen_set), args.variant)
    run = account.Run(run_id=RUN_ID, args=args, cell=cell, cfg=cli._harness_config(args),
                      matrix=matrix, episodes=episodes, notes=cli._run_notes(args, matrix),
                      what=cli._run_what(args, cell, len(episodes)))

    records = [json.loads(x) for x in (OUT / "episodes.jsonl").read_text(
        encoding="utf-8").splitlines() if x.strip()]
    runs = [runner.EpisodeRun(**{k: v for k, v in r.items() if k != "repeat_index"})
            for r in records]
    raw_path = RAW / "transcript.jsonl.gz"
    cut_path = RAW / "transcript.jsonl.gz.cut"
    source = cut_path if cut_path.exists() else raw_path
    lines, tail = gunzip_partial(source.read_bytes())
    transcript = [json.loads(x) for x in lines]
    inflight = []
    for p in sorted((RAW / "inflight").glob("*.jsonl")):
        inflight += [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()
                     if x.strip()]

    # Per episode: the ledger over its transcript lines against its episodes.jsonl totals.
    by_ep = defaultdict(list)
    for c in transcript:
        by_ep[c["episode_id"]].append(c)
    keys = ("input_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens")
    ledger = UsageLedger(args.model)
    checks, missing = [], None
    for rec in records:
        calls = by_ep[rec["episode_id"]]
        lat = list(rec.get("call_latency_s") or [])
        ep = UsageLedger(args.model)
        for i, c in enumerate(calls):
            ep.add(c["response"], requested_tier=c["payload"].get("service_tier"),
                   latency_s=lat[i] if i < len(lat) else None)
            ledger.add(c["response"], requested_tier=c["payload"].get("service_tier"),
                       latency_s=lat[i] if i < len(lat) else None)
        want = {k: int(rec["usage"][k] or 0) for k in keys}
        got = {"input_tokens": ep.input_tokens, "cached_input_tokens": ep.cached_input_tokens,
               "cache_write_tokens": ep.cache_write_tokens, "output_tokens": ep.output_tokens}
        if len(calls) == rec["n_requests"]:
            ok = got == want and abs(ep.cost_usd_billed_est - rec["cost_usd_billed_est"]) < 1e-9
            checks.append((rec["episode_id"], len(calls), ok))
            if not ok:
                raise SystemExit(f"ledger and episodes.jsonl differ for {rec['episode_id']}: "
                                 f"{got} {ep.cost_usd_billed_est} vs {want} "
                                 f"{rec['cost_usd_billed_est']}")
        else:
            if missing is not None or rec["n_requests"] - len(calls) != 1:
                raise SystemExit(f"unexpected gap in {rec['episode_id']}")
            missing = {k: want[k] - got[k] for k in keys}
            missing["cost_list"] = rec["cost_usd_list"] - ep.cost_usd_list
            missing["cost_billed"] = rec["cost_usd_billed_est"] - ep.cost_usd_billed_est
            missing["latency_s"] = lat[len(calls)] if len(lat) > len(calls) else None
            missing["episode_id"] = rec["episode_id"]
            missing["request_index"] = len(calls)
    if missing is None or any(missing[k] < 0 for k in keys) or missing["cost_billed"] <= 0:
        raise SystemExit(f"the cut-off call cannot be rebuilt: {missing}")
    # The cut-off call: its usage from its episode's totals (its response is not on disk).
    ledger.n_calls += 1
    for k in keys:
        setattr(ledger, k, getattr(ledger, k) + missing[k])
    ledger.cost_usd_list += missing["cost_list"]
    ledger.cost_usd_billed_est += missing["cost_billed"]
    if missing["latency_s"] is not None:
        ledger.latencies_s.append(missing["latency_s"])
    # The abandoned in-flight episodes' recorded calls (no per-call timings on disk).
    for c in inflight:
        ledger.add(c["response"], requested_tier=c["payload"].get("service_tier"))

    raw_mtimes = [raw_path.stat().st_mtime, *(p.stat().st_mtime
                                             for p in (RAW / "inflight").glob("*.jsonl"))]
    if cut_path.exists():
        raw_mtimes.append(cut_path.stat().st_mtime)
    end = datetime.fromtimestamp(max(raw_mtimes), UTC).isoformat(timespec="seconds")
    git = plan["git"]
    row = build_costs_row(
        ledger, timestamp_utc=end, run_id=RUN_ID, milestone=args.milestone,
        approved_block=str(args.approved_block), experiment=EXP, cell_or_config=cell.ascii_id,
        git=git, context_mismatches="n/a", effort_mismatches="n/a", notes=run.notes)
    abandoned = sorted({c["episode_id"] for c in inflight})
    row["notes"] += (
        f"; added by hand on {runmeta.utc_now()[:10]} (drafts/r12_ops/account_killed_f0.py), "
        f"after the run: {CAUSE}. 7 of 50 episodes finished. 2 in-flight episodes were "
        f"abandoned ({', '.join(abandoned)}), and their {len(inflight)} recorded calls are "
        f"counted. The call {missing['episode_id']} request {missing['request_index']} is "
        f"counted from its episode's totals, since its transcript line was cut off, so "
        f"inference_geos omits it. At most 2 calls in flight when the process died are "
        f"recorded nowhere. timestamp_utc is the raw files' last write. latency_s is the "
        f"median of the finished episodes' per-call timings")
    summary = blinding.run_summary(records, blinded=False)
    recovered = {
        "by": "hand, drafts/r12_ops/account_killed_f0.py (harnesses account-run cannot "
              "rebuild a Messages API run or an interrupted one)",
        "accounted_utc": runmeta.utc_now(),
        "cause": CAUSE,
        "what": ("the run's process was killed, so run_batch wrote neither summary.json nor "
                 "meta.json and finalize wrote no costs row. The row and both files were "
                 "rebuilt from run_plan.json, episodes.jsonl and the raw transcript with the "
                 "repo's own code. The raw transcript's last line (the cut-off call) was "
                 "incomplete: the cut-off file is kept as transcript.jsonl.gz.cut and "
                 "transcript.jsonl.gz holds its 177 complete lines"),
        "abandoned_episode_ids": abandoned,
        "missing_transcript_line": {"episode_id": missing["episode_id"],
                                    "request_index": missing["request_index"]},
        "approximate": {
            "finished_utc": "the raw files' last write",
            "costs_row_timestamp_utc": "the raw files' last write",
            "costs_row_latency_s": "the median of the finished episodes' per-call timings"},
        "settings_from": "run_plan.json", "run_plan": runner._rel(plan_path),
    }
    parallel = {"max_episodes_in_flight": int(args.parallel), "episodes_started": 9,
                "abandoned_episode_ids": abandoned, "stop_reason": EXIT}
    return {"plan": plan, "run": run, "records": records, "runs": runs, "row": row,
            "summary": summary, "recovered": recovered, "parallel": parallel, "end": end,
            "git": git, "checks": checks, "missing": missing, "lines": lines, "tail": tail,
            "raw_path": raw_path, "cut_path": cut_path, "ledger": ledger,
            "inflight": len(inflight)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    b = build()
    sys.stdout.reconfigure(encoding="utf-8")
    print("episode checks (ledger == episodes.jsonl):", b["checks"])
    print("cut-off call:", {k: v for k, v in b["missing"].items()})
    print("row:", json.dumps(b["row"], indent=1))
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    res = paidlock.read_reservations(LOCK)
    print("lock:", lock)
    print("reservations:", res)
    alive = paidlock.holder_alive(lock)
    print("lock holder alive:", alive)
    if any(r.get("run_id") == RUN_ID for r in costs.read_rows()):
        raise SystemExit("costs.csv already has this run's row")
    if lock.get("run_id") != RUN_ID or alive:
        raise SystemExit("the lock is not this dead run's")
    if not a.write:
        print("dry run: nothing written")
        return 0

    with paidlock.budget_mutex(LOCK):
        if any(r.get("run_id") == RUN_ID for r in costs.read_rows()):
            raise SystemExit("costs.csv already has this run's row")
        costs.append_row(b["row"])
    print("appended the costs row")
    if not b["cut_path"].exists():
        shutil.copy2(b["raw_path"], b["cut_path"])
        with gzip.open(b["raw_path"], "wt", encoding="utf-8", newline="\n") as f:
            f.write("".join(x + "\n" for x in b["lines"]))
    print("raw transcript: cut-off file kept as", b["cut_path"].name, "and rewritten complete")
    (OUT / "summary.json").write_text(json.dumps(b["summary"], indent=2) + "\n",
                                      encoding="utf-8", newline="\n")
    print("wrote summary.json")
    run = b["run"]
    runner._write_meta(
        OUT, b["raw_path"], run.episodes, b["runs"], run.cell, run.cfg,
        types.SimpleNamespace(paid=True), experiment=EXP, run_id=RUN_ID,
        started=b["plan"]["started_utc"], exit_reason=EXIT,
        repeat_index=run.matrix.repeat_index, cost_row=b["row"], blinded=False,
        episodes_path=OUT / "episodes.jsonl", run_matrix=run.matrix.to_dict(),
        parallel=b["parallel"], parallel_path=None, git=b["git"], finished=b["end"],
        recorded={"recovered": b["recovered"], "prereg_version": b["plan"]["prereg_version"],
                  "sdk_versions": b["plan"]["sdk_versions"]})
    print("wrote meta.json")
    paidlock.record_last_run(LOCK, stream=STREAM, run_id=RUN_ID, costs_csv=costs.COSTS_CSV,
                             timestamp_utc=b["row"]["timestamp_utc"])
    print("recorded the last paid run")
    rid = next((r.reservation_id for r in paidlock.read_reservations(LOCK)
                if r.run_id == RUN_ID), None)
    if rid is not None:
        print("released reservation:", paidlock.release_reservation(
            LOCK, stream=STREAM, reservation_id=rid))
    held = json.loads(LOCK.read_text(encoding="utf-8"))
    if held.get("run_id") == RUN_ID and held.get("token") == lock.get("token"):
        LOCK.unlink()
        print("deleted the dead run's lock")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
