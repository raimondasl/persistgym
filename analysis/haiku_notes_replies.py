"""Exploratory: what claude-haiku-5-5 wrote when its notes carried a fact it did not use (R9; $0).

**Not registered.** R9 (PREREG §17.9) registers descriptive readings that cannot say why, in
the not-recoverable far cells of Haiku's W-n-0 run, episodes whose notes carried the fact
still failed (`results/decisions.md`, 2026-10-24). The researcher approved reading the model's
replies on 2026-10-24, after those readings were seen. Everything here is exploratory, and the
categories are text patterns, checked against a hand-read sample (`summary.md`), not a
validated coding scheme.

For every W-n-0 episode of the 2 not-recoverable far cells (`results/persistgym_haiku_notes/`,
repeat 0), it reads the raw transcript (``results/raw/persistgym_haiku_notes/<run>/``) and
reports:

1. **Declines at the need step:** the need-step reply resolved to no option (`need_label`
   unset), split by whether the notes carried the fact (§2.8's `assistant_carried`).
2. **Disowns its earlier figure at the need step:** the need-step reply matches `DISOWN`. It
   calls an earlier figure of its own retracted, invented, made up, unsupported or
   unverifiable.
3. **Retracts before the need step:** some routine-step reply after the last evidence step
   names the need's entity and matches `DISOWN`. This is an unprompted correction of its own
   note. The first such step is reported relative to the step at which the window first
   dropped an evidence step (`info.keep_start` above the first evidence step).

It prints and writes counts with a few short excerpts. It never reads luna's transcripts, and
it compares nothing across models.

Run: ``uv run python -m analysis.haiku_notes_replies [--raw-root DIR]``. It writes
``results/haiku_notes_replies/<UTC>/replies.json``, ``summary.md`` and ``meta.json``. With
``--no-write`` it only prints.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from common import runmeta

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT = "persistgym_haiku_notes"
RUN = "20261024T060051Z-W-n-0-claude-haiku-5-5"
NR_FAR = ("observed-nonrec-far", "derived-nonrec-far")
DISOWN = re.compile(
    r"\b(retract\w*|invent(?:ed|ing)?|made[- ]up|fabricat\w*|unsupported|"
    r"no (?:source|basis)|(?:can'?t|cannot|couldn'?t) (?:verify|source|trace|confirm)|"
    r"never (?:saw|verified)|not (?:verified|supported|sourced))\b", re.I)
"""Self-disowning language: the reply calls an earlier figure of its own retracted, invented,
made up, unsupported or unverifiable."""
ENTITY = re.compile(r"EVENT: \S+ (\S+) needs")
OUTPUTS = ("replies.json", "summary.md", "meta.json")


def reply_text(response: dict | None) -> str:
    return "\n".join(b.get("text", "") for b in (response or {}).get("content") or []
                     if b.get("type") == "text")


def need_step(rec: dict) -> int:
    d = rec["designed"]
    return int(max(d["evidence_steps"])) + int(d["gap_steps_latest"])


def carried(rec: dict) -> bool:
    return bool(((rec.get("need_payload") or {}).get("assistant_carried") or {}).get("carried"))


def episodes(root: Path) -> dict[str, dict]:
    path = root / "results" / EXPERIMENT / RUN / "episodes.jsonl"
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if rec["task_cell"] in NR_FAR and (rec.get("variant") or "base") == "base":
            out[rec["episode_id"]] = rec
    return out


def steps(raw_root: Path, wanted: set[str]) -> dict[str, list[dict]]:
    """Each wanted episode's step requests in order: step, keep_start and reply text (the first
    request at a step only)."""
    out: dict[str, list[dict]] = {e: [] for e in wanted}
    seen = set()
    path = raw_root / EXPERIMENT / RUN / "transcript.jsonl.gz"
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            eid = d.get("episode_id")
            if eid not in out or d.get("kind") != "step":
                continue
            key = (eid, int(d["pending_step"]))
            if key in seen:
                continue
            seen.add(key)
            msgs = d["payload"]["messages"]
            user = next((m for m in reversed(msgs) if m["role"] == "user"), None)
            prompt = user["content"] if user and isinstance(user["content"], str) else (
                "\n".join(b.get("text", "") for b in (user or {}).get("content") or []
                          if isinstance(b, dict)))
            out[eid].append({"step": key[1], "keep_start": (d.get("info") or {}).get("keep_start"),
                             "reply": reply_text(d.get("response")), "prompt": prompt})
    return out


def episode_reading(rec: dict, trail: list[dict]) -> dict:
    ns, ev = need_step(rec), rec["designed"]["evidence_steps"]
    need = next((s for s in trail if s["step"] == ns), None)
    m = ENTITY.search(need["prompt"]) if need else None
    entity = m.group(1) if m else None
    dropped_at = next((s["step"] for s in sorted(trail, key=lambda s: s["step"])
                       if s["keep_start"] is not None and int(s["keep_start"]) > min(ev)), None)
    retract = [s["step"] for s in trail
               if max(ev) < s["step"] < ns and entity and entity in s["reply"]
               and DISOWN.search(s["reply"])]
    return {"episode_id": rec["episode_id"], "task_cell": rec["task_cell"],
            "outcome": rec["need_outcome"], "chose_option": rec.get("need_label") not in (None, ""),
            "carried": carried(rec), "entity": entity, "need_step": ns,
            "first_evidence_dropped_at": dropped_at,
            "need_reply_disowns": bool(need and DISOWN.search(need["reply"])),
            "retraction_steps": retract,
            "first_retraction_after_drop": (retract[0] - dropped_at
                                            if retract and dropped_at is not None else None),
            "need_reply_excerpt": (need["reply"][:240] if need else None)}


def tally(rows: list[dict]) -> dict:
    out = {}
    for tc in NR_FAR:
        for c in (True, False):
            sub = [r for r in rows if r["task_cell"] == tc and r["carried"] == c]
            failed = [r for r in sub if r["outcome"] != "correct"]
            lags = [r["first_retraction_after_drop"] for r in failed
                    if r["first_retraction_after_drop"] is not None]
            out[f"{tc} carried={c}"] = {
                "episodes": len(sub), "correct": len(sub) - len(failed),
                "failed": len(failed),
                "failed_declined": sum(not r["chose_option"] for r in failed),
                "failed_need_reply_disowns": sum(r["need_reply_disowns"] for r in failed),
                "failed_retracted_before_need": sum(bool(r["retraction_steps"]) for r in failed),
                "retraction_lag_steps": dict(sorted(Counter(lags).items())),
                "correct_need_reply_disowns": sum(r["need_reply_disowns"] for r in sub
                                                  if r["outcome"] == "correct"),
            }
    return out


def summary(t: dict, rows: list[dict]) -> str:
    lines = ["# claude-haiku-5-5 W-n-0: the replies behind unused notes (exploratory)", "",
             "Not registered (R9 registers descriptive readings only). Approved by the researcher "
             "on 2026-10-24 after those readings were seen. Text-pattern categories, not a "
             "validated coding. Not a model comparison.", "",
             "| Cell, notes carried the fact | Episodes | Correct | Failed | Failed: declined | "
             "Failed: need reply disowns its figure | Failed: retracted before the need step |",
             "|---|---|---|---|---|---|---|"]
    for k, v in t.items():
        lines.append(f"| {k} | {v['episodes']} | {v['correct']} | {v['failed']} | "
                     f"{v['failed_declined']} | {v['failed_need_reply_disowns']} | "
                     f"{v['failed_retracted_before_need']} |")
    lines += ["", "Retraction lag (steps from the first dropped evidence step to the first "
              "retraction), failed episodes:", ""]
    lines += [f"- {k}: {v['retraction_lag_steps'] or '-'}" for k, v in t.items()]
    lines += ["", "Excerpts (need-step replies, failed carried episodes, first 3 per cell):", ""]
    for tc in NR_FAR:
        ex = [r for r in rows if r["task_cell"] == tc and r["carried"]
              and r["outcome"] != "correct"][:3]
        lines += [f"- {r['episode_id']}: \"{(r['need_reply_excerpt'] or '').strip()}\"" for r in ex]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results-root", type=Path, default=REPO_ROOT)
    ap.add_argument("--raw-root", type=Path, default=None)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--out-dir", type=Path, default=None)
    a = ap.parse_args(argv)
    now = datetime.now(UTC)
    recs = episodes(a.results_root)
    trails = steps(a.raw_root or a.results_root / "results" / "raw", set(recs))
    rows = [episode_reading(recs[e], trails[e]) for e in sorted(recs)]
    t = tally(rows)
    text = summary(t, rows)
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    if a.no_write:
        return 0
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    out = a.out_dir or a.results_root / "results" / "haiku_notes_replies" / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "replies.json").write_text(json.dumps({"tally": t, "episodes": rows}, indent=2,
                                                 ensure_ascii=False), encoding="utf-8",
                                      newline="\n")
    (out / "summary.md").write_text(text, encoding="utf-8", newline="\n")
    runmeta.write_meta(
        out, git=runmeta.git_state(), experiment="haiku_notes_replies", run_id=run_id,
        cell_or_config="W-n-0", config={"run": RUN, "pattern": DISOWN.pattern,
                                        "exploratory": True},
        model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
        repeat_index=0, seeds=None, started_utc=now.isoformat(timespec="seconds"),
        finished_utc=runmeta.utc_now(), exit_reason="completed", tokens=None, cost_usd=0.0,
        raw_transcript_path=f"results/raw/{EXPERIMENT}/{RUN}/transcript.jsonl.gz",
        outputs=list(OUTPUTS), paid_calls=0, runs=[RUN])
    print(f"written: {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
