"""Exploratory: the numbers in R10's results entry that R10 does not register (PREREG §17.10; $0).

**Not registered.** `analysis.haiku_provenance` holds R10's registered readings. This script
was written after they were read, to give the entry's other numbers a committed source, and
everything here is descriptive. It tests nothing and ranks nothing.

It reads the same counted records as the registered analysis (`haiku_provenance.read` and
`r9_read`), on the 4 far task cells of W-np-0, W-npd-0 and R9's W-n-0, and each run's raw
transcript under ``--raw-root`` (default ``results/raw``). It reports, per arm:

1. **Refusals:** responses, refused responses and their share, and refused responses by turn.
2. **Failures in the 2 not-recoverable far cells,** by whether the notes carried the fact and
   whether the response at the need step was a refusal, and success by whether a step before
   the need step was refused.
3. **Thinking blocks:** the share of responses holding one (only the block's presence: its text
   is empty in every response), over all responses and by turn on each step's first request.
4. **What the model kept at the need step,** on its first request there: the retained replies,
   how many and how long, and from the last evidence step to the step before the need step, how
   many replies hold the fact's value (whole-word match, `survival.whole_word_regex`; refused
   responses left out).
5. **Where the fact's value appears** in that first request (the leak check), against the values
   the generator gives for the episode: in the system prompt, in user messages before the need
   observation, in the need observation in and out of the correct option's own line. Clue
   values likewise, outside the model's replies. Also the later requests at the need step.
6. **Identical user messages:** the last user message of each step's first request against R9's
   at the same episode and step.
7. **Input rates:** uncached input tokens per minute of each run (meta.json's input tokens less
   cached ones, over its duration).

Run: ``uv run python -m analysis.haiku_provenance_extras [--rerun RUN=ORIGINAL ...]``. It writes
``results/haiku_provenance_extras/<UTC>/extras.json``, ``summary.md`` and ``meta.json``. With
``--no-write`` it only prints. It refuses when a run's transcript is missing, or when the
responses it reads differ from the records' request counts.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import statistics
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from analysis import haiku_notes as hn
from analysis import haiku_notes_replies as hnr
from analysis import haiku_provenance as hp
from common import runmeta
from harnesses import registered
from persistgym.config import PRESETS
from persistgym.episode import TaskCell
from persistgym.render import generate
from persistgym.survival import flatten_payload, whole_word_regex

REPO_ROOT = Path(__file__).resolve().parent.parent
FAR = hp.FAR
NR_FAR = hp.NR_FAR
TURN_BINS = ((0, 4, "0-4"), (5, 9, "5-9"), (10, 14, "10-14"), (15, None, "15 on"))
R9_ARM = "W-n-0 (R9)"
OUTPUTS = ("extras.json", "summary.md", "meta.json")


def turn_bin(turn: int) -> str:
    return next(name for low, high, name in TURN_BINS
                if turn >= low and (high is None or turn <= high))


def _refusals(rec: dict) -> list[dict]:
    return [i for i in rec.get("incomplete") or [] if str(i.get("reason", "")).startswith("refusal")]


def record_readings(records: list[dict]) -> dict:
    """Readings 1 and 2, from the counted records alone."""
    refused = [i for rec in records for i in _refusals(rec)]
    responses = sum(int(rec["n_requests"]) for rec in records)
    by_turn = Counter(turn_bin(int(i["turn"])) for i in refused)
    split: dict[str, Counter] = {}
    before: dict[str, Counter] = {}
    for cell in (*NR_FAR, "both"):
        split[cell], before[cell] = Counter(), Counter()
    for rec in records:
        if rec["task_cell"] not in NR_FAR:
            continue
        refusals = _refusals(rec)
        at_need = any(i.get("at_need") for i in refusals)
        group = ("refused at the need step" if at_need
                 else "refused before the need step only" if refusals
                 else "no refused step")
        for cell in (rec["task_cell"], "both"):
            before[cell][f"{group}: episodes"] += 1
            before[cell][f"{group}: success"] += bool(rec["need_correct"])
            if not rec["need_correct"]:
                split[cell]["failed"] += 1
                split[cell][("carried" if hnr.carried(rec) else "not carried")
                            + (", refused at the need step" if at_need
                               else ", no refusal at the need step")] += 1
    return {"responses": responses, "refused_responses": len(refused),
            "refused_share": len(refused) / responses if responses else None,
            "refused_by_turn": {name: by_turn[name] for _, _, name in TURN_BINS},
            "refusal_categories": dict(Counter(i["reason"] for i in refused)),
            "failures": {cell: dict(sorted(c.items())) for cell, c in split.items()},
            "success_by_refusal": {cell: dict(sorted(c.items())) for cell, c in before.items()}}


def episode_facts() -> dict[str, dict]:
    """What the generator gives for each far episode of main templates 0-199."""
    cells = [TaskCell.from_id(c) for c in FAR]
    out = {}
    for _, eps in generate("main", range(registered.HAIKU_T), PRESETS["default"], cells, ("base",)):
        for e in eps:
            out[e.episode_id] = {"target": e.target_value, "label": e.correct_label,
                                 "clues": sorted({c.value for c in e.components
                                                  if c.role == "clue"})}
    return out


def _has_thinking(response: dict) -> bool:
    return any(b.get("type") == "thinking" for b in response.get("content") or [])


def need_request_reading(payload: dict, fact: dict) -> dict:
    """Reading 5 on one need step's first request, and its retained replies (reading 4)."""
    pairs = flatten_payload(payload["messages"])
    system = payload.get("system")
    system = system if isinstance(system, str) else "\n".join(
        b.get("text", "") for b in system or [] if isinstance(b, dict))
    users = [text for role, text in pairs if role == "user"]
    replies = [text for role, text in pairs if role == "assistant"]
    need_obs = users[-1] if users else ""
    target = whole_word_regex(fact["target"])
    option_line = f"{fact['label']}) {fact['target']}"
    in_option = 0
    for m in target.finditer(need_obs):
        start, end = need_obs.rfind("\n", 0, m.start()) + 1, need_obs.find("\n", m.end())
        in_option += need_obs[start:end if end >= 0 else None] == option_line
    in_need = len(target.findall(need_obs))
    env = "\n".join([system, *users])
    return {"target_in_system": len(target.findall(system)),
            "target_in_earlier_user": len(target.findall("\n".join(users[:-1]))),
            "target_in_need_option_line": in_option,
            "target_in_need_elsewhere": in_need - in_option,
            "clue_outside_replies": sum(len(whole_word_regex(v).findall(env))
                                        for v in fact["clues"]),
            "n_replies": len(replies), "reply_chars": sum(len(t) for t in replies)}


def transcript_readings(path: Path, records: dict[str, dict],
                        facts: dict[str, dict]) -> dict:
    """Readings 3 to 6, from one run's transcript, for the episodes whose counted record it holds.
    Returns plain tallies, added up over an arm's runs by `merge`."""
    tally = {"responses": 0, "thinking": 0, "turn_first": Counter(), "turn_thinking": Counter(),
             "later_need_requests": Counter(), "need": {}, "held": {}, "user_hash": {}}
    seen = set()
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            eid = d.get("episode_id")
            if eid not in records or d.get("kind") != "step":
                continue
            rec, step = records[eid], int(d["pending_step"])
            response = d.get("response") or {}
            ns = hnr.need_step(rec)
            tally["responses"] += 1
            tally["thinking"] += _has_thinking(response)
            first = (eid, step) not in seen
            seen.add((eid, step))
            if not first:
                if step == ns:
                    tally["later_need_requests"][rec["task_cell"]] += 1
                continue
            tally["turn_first"][step] += 1
            tally["turn_thinking"][step] += _has_thinking(response)
            pairs = flatten_payload(d["payload"]["messages"])
            user = next((t for role, t in reversed(pairs) if role == "user"), "")
            tally["user_hash"][f"{eid}#{step}"] = hashlib.sha256(
                user.encode("utf-8")).hexdigest()
            if step == ns:
                tally["need"][eid] = need_request_reading(d["payload"], facts[eid])
            if (max(rec["designed"]["evidence_steps"]) <= step < ns
                    and response.get("stop_reason") != "refusal"):
                reply = hnr.reply_text(response)
                held = tally["held"].setdefault(eid, [0, 0])
                held[0] += whole_word_regex(facts[eid]["target"]).search(reply) is not None
                held[1] += 1
    return tally


def merge(tallies: list[dict]) -> dict:
    out = {"responses": 0, "thinking": 0, "turn_first": Counter(), "turn_thinking": Counter(),
           "later_need_requests": Counter(), "need": {}, "held": {}, "user_hash": {}}
    for t in tallies:
        for k in ("responses", "thinking"):
            out[k] += t[k]
        for k in ("turn_first", "turn_thinking", "later_need_requests"):
            out[k].update(t[k])
        for k in ("need", "held", "user_hash"):
            out[k].update(t[k])
    return out


def _pool(values: dict[str, dict], key: str, ids: list[str]) -> int:
    return sum(values[e][key] for e in ids if e in values)


def _quartiles(xs: list[int]) -> list[float]:
    return [float(q) for q in statistics.quantiles(xs, n=4, method="inclusive")] if len(xs) > 1 else [
        float(x) for x in xs * 3]


def arm_transcript_summary(t: dict, records: dict[str, dict]) -> dict:
    """Readings 3 to 5 for one arm."""
    pooled = sorted(t["turn_first"])
    bins = {name: [0, 0] for _, _, name in TURN_BINS}
    for step in pooled:
        bins[turn_bin(step)][0] += t["turn_thinking"][step]
        bins[turn_bin(step)][1] += t["turn_first"][step]
    held, kept, need = {}, {}, {}
    for cell in (*FAR,):
        ids = sorted(e for e, r in records.items() if r["task_cell"] == cell)
        pairs = [t["held"][e] for e in ids if e in t["held"] and t["held"][e][1]]
        held[cell] = {"replies_holding_value": sum(a for a, _ in pairs),
                      "replies": sum(b for _, b in pairs),
                      "per_episode_median": (statistics.median(a / b for a, b in pairs)
                                             if pairs else None)}
        reads = [t["need"][e] for e in ids if e in t["need"]]
        kept[cell] = {"episodes": len(reads),
                      "retained_replies_median": (statistics.median(r["n_replies"] for r in reads)
                                                  if reads else None),
                      "reply_chars_quartiles": _quartiles([r["reply_chars"] for r in reads])}
        need[cell] = {k: _pool(t["need"], k, ids)
                      for k in ("target_in_system", "target_in_earlier_user",
                                "target_in_need_option_line", "target_in_need_elsewhere",
                                "clue_outside_replies")}
    return {"responses_in_transcript": t["responses"], "with_thinking": t["thinking"],
            "thinking_share": t["thinking"] / t["responses"] if t["responses"] else None,
            "first_requests_by_turn": {str(s): [t["turn_thinking"][s], t["turn_first"][s]]
                                       for s in pooled},
            "first_requests_by_turn_bin": bins,
            "fact_value_in_replies": held, "at_need": kept, "leak_check": need,
            "later_need_requests": dict(sorted(t["later_need_requests"].items()))}


def input_rate(root: Path, experiment: str, run_id: str) -> dict:
    meta = json.loads((root / "results" / experiment / run_id / "meta.json")
                      .read_text(encoding="utf-8"))
    tokens = meta["tokens"]
    minutes = (datetime.fromisoformat(meta["finished_utc"])
               - datetime.fromisoformat(meta["started_utc"])).total_seconds() / 60
    uncached = int(tokens["input_tokens"]) - int(tokens["cached_input_tokens"])
    return {"run_id": run_id, "minutes": minutes, "uncached_input_tokens": uncached,
            "uncached_per_minute": uncached / minutes,
            "max_in_flight": (meta.get("parallel") or {}).get("max_episodes_in_flight")}


def readings(root: Path, links: dict[str, str], raw_root: Path | None = None) -> dict:
    raw = raw_root or root / "results" / "raw"
    T = registered.HAIKU_T
    r10_runs, r10, _ = hp.read(root, registered.HAIKU_PROVENANCE_EXPERIMENT,
                               tuple(registered.HAIKU_PROVENANCE_CELLS), links, False)
    r9_runs, r9 = hp.r9_read(root)
    arms = [(R9_ARM, registered.HAIKU_NOTES_EXPERIMENT, hp.R9_CELL, r9, r9_runs)]
    arms += [(cell, registered.HAIKU_PROVENANCE_EXPERIMENT, cell, r10, r10_runs)
             for cell in registered.HAIKU_PROVENANCE_CELLS]
    facts = episode_facts()
    out, hashes = {"arms": {}}, {}
    for name, experiment, cell, resolved, runs in arms:
        counted = hp._counted(resolved, cell, T)
        by_run: dict[str, dict[str, dict]] = {}
        for r in counted:
            by_run.setdefault(r.run_id, {})[r.record["episode_id"]] = r.record
        missing = sorted(run_id for run_id in by_run
                         if not (raw / experiment / run_id / "transcript.jsonl.gz").is_file())
        if missing:
            raise SystemExit(f"refused: no raw transcript for {', '.join(missing)}")
        records = {e: rec for recs in by_run.values() for e, rec in recs.items()}
        t = merge([transcript_readings(raw / experiment / run_id / "transcript.jsonl.gz",
                                       recs, facts)
                   for run_id, recs in sorted(by_run.items())])
        from_records = record_readings(list(records.values()))
        if t["responses"] != from_records["responses"]:
            raise SystemExit(f"refused: {name}'s transcripts hold {t['responses']} responses, "
                             f"its records {from_records['responses']}")
        hashes[name] = t["user_hash"]
        out["arms"][name] = {**from_records, **arm_transcript_summary(t, records),
                             "episodes": len(records),
                             "runs": sorted(by_run),
                             "input_rates": [input_rate(root, experiment, x.run_id) for x in runs
                                             if x.cell == cell]}
    ref = hashes[R9_ARM]
    out["user_messages_against_r9"] = {
        name: {"common": len(ref.keys() & h),
               "identical": sum(ref[k] == h[k] for k in ref.keys() & h)}
        for name, h in hashes.items() if name != R9_ARM}
    return out


def _pct(a: int, b: int) -> str:
    return f"{a}/{b} = {100 * a / b:.1f}%" if b else f"{a}/{b}"


def summary(r: dict) -> str:
    lines = ["# R10's unregistered numbers (exploratory)", "",
             ("**Not registered.** Written after R10's registered readings were read, as the source "
              "of the results entry's other numbers. Descriptive only: nothing is tested. "
              "`analysis.haiku_provenance` holds the registered readings."), ""]
    names = list(r["arms"])
    lines += ["## Refusals (4 far cells)", "",
              "| Arm | Refused responses | By turn 0-4, 5-9, 10-14, 15 on | Categories |",
              "|---|---|---|---|"]
    for n in names:
        a = r["arms"][n]
        lines.append(f"| {n} | {a['refused_responses']} of {a['responses']} "
                     f"({100 * a['refused_share']:.2f}%) | "
                     f"{', '.join(str(v) for v in a['refused_by_turn'].values())} | "
                     f"{a['refusal_categories']} |")
    lines += ["", "## Not-recoverable far cells: failures and refusals", ""]
    for n in names:
        a = r["arms"][n]
        lines.append(f"- **{n},** both cells: {a['failures']['both']}. "
                     f"By refusal: {a['success_by_refusal']['both']}.")
    lines += ["", "## Thinking blocks (only their presence is read)", "",
              "| Arm | All responses | First request of turn 0 | Turns 0-4 | 5-9 | 10-14 | 15 on |",
              "|---|---|---|---|---|---|---|"]
    for n in names:
        a = r["arms"][n]
        bins = a["first_requests_by_turn_bin"]
        t0 = a["first_requests_by_turn"]["0"]
        lines.append(f"| {n} | {_pct(a['with_thinking'], a['responses_in_transcript'])} | "
                     f"{_pct(*t0)} | "
                     + " | ".join(_pct(*bins[name]) for _, _, name in TURN_BINS) + " |")
    lines += ["", "First requests by turn, share with a thinking block:", ""]
    for n in names:
        by = r["arms"][n]["first_requests_by_turn"]
        lines.append(f"- {n}: " + ", ".join(f"{s}: {100 * v[0] / v[1]:.1f}" for s, v in by.items()
                                            if int(s) <= 24))
    lines += ["", "## At the need step's first request", "",
              ("| Arm | Task cell | Retained replies (median) | Their characters (quartiles) | "
               "Replies holding the value, last evidence step to before the need step | "
               "Per-episode median |"), "|---|---|---|---|---|---|"]
    for n in names:
        a = r["arms"][n]
        for cell in FAR:
            k, h = a["at_need"][cell], a["fact_value_in_replies"][cell]
            q = ", ".join(f"{x:.0f}" for x in k["reply_chars_quartiles"])
            lines.append(f"| {n} | {cell} | {k['retained_replies_median']} | {q} | "
                         f"{_pct(h['replies_holding_value'], h['replies'])} | "
                         f"{h['per_episode_median']:.2f} |")
    lines += ["", "## Where the fact's value appears in that request", "",
              ("| Arm | Task cell | Episodes | In system prompt | In earlier user messages | "
               "In the need observation's option line | Elsewhere in it | Clue values outside "
               "replies |"), "|---|---|---|---|---|---|---|---|"]
    for n in names:
        a = r["arms"][n]
        for cell in FAR:
            k = a["leak_check"][cell]
            lines.append(f"| {n} | {cell} | {a['at_need'][cell]['episodes']} | "
                         f"{k['target_in_system']} | {k['target_in_earlier_user']} | "
                         f"{k['target_in_need_option_line']} | {k['target_in_need_elsewhere']} | "
                         f"{k['clue_outside_replies']} |")
    lines += ["", "Later requests at the need step, per arm: "
              + "; ".join(f"{n} {r['arms'][n]['later_need_requests']}" for n in names) + ".", ""]
    lines += ["## User messages against R9's, and input rates", ""]
    for n, v in r["user_messages_against_r9"].items():
        lines.append(f"- {n}: {v['identical']} of {v['common']} common messages identical.")
    for n in names:
        for x in r["arms"][n]["input_rates"]:
            lines.append(f"- {x['run_id']}: {x['uncached_per_minute'] / 1e6:.2f} million uncached "
                         f"input tokens a minute over {x['minutes']:.1f} min, "
                         f"at most {x['max_in_flight']} in flight.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results-root", type=Path, default=REPO_ROOT)
    ap.add_argument("--rerun", action="append", default=[], metavar="RUN=ORIGINAL")
    ap.add_argument("--raw-root", type=Path, default=None)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    now = datetime.now(UTC)
    links = hn._links(a.rerun)
    r = readings(a.results_root, links, raw_root=a.raw_root)
    text = summary(r)
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    if a.no_write:
        return 0
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    out = a.results_root / "results" / "haiku_provenance_extras" / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "extras.json").write_text(json.dumps(r, indent=2, default=str), encoding="utf-8",
                                     newline="\n")
    (out / "summary.md").write_text(text, encoding="utf-8", newline="\n")
    runmeta.write_meta(
        out, git=runmeta.git_state(), experiment="haiku_provenance_extras", run_id=run_id,
        cell_or_config=",".join(registered.HAIKU_PROVENANCE_CELLS),
        config={"rerun_links": links, "r9_output": hp.R9_OUTPUT, "registered": False},
        model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
        repeat_index=0, seeds=None, started_utc=now.isoformat(timespec="seconds"),
        finished_utc=runmeta.utc_now(), exit_reason="completed", tokens=None, cost_usd=0.0,
        raw_transcript_path=None, outputs=list(OUTPUTS), paid_calls=0,
        runs=[x for arm in r["arms"].values() for x in arm["runs"]])
    print(f"written: {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
