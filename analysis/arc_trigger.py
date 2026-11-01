"""Exploratory: does S1 keep more history than S0 because its limit counts tokens, not characters?

Run: ``uv run python -m analysis.arc_trigger [--results-root DIR] [--raw-root DIR]
[--out-dir DIR] [--no-write]`` ($0: it reads files only). It writes
``<results root>/arc_trigger/<UTC>/trigger.json``, ``summary.md`` and ``meta.json``.

Exploratory: no test, no verdict. It was written after the ARC path results were read, and it
enters no hypothesis, gate or kill rule.

**The question.** S0 drops its oldest user/assistant pair once the harness's estimate of the
request (characters at ``ESTIMATED_CHARS_PER_TOKEN`` 1.0, the system prompt included) exceeds
``MAX_CONTEXT_LENGTH`` 175,000. S1 summarizes once a request *reports* 175,000 provider tokens.
So the S0→S1 step changes the limit's unit as well as the loss policy. How much more history
does the unit difference let S1 keep?

**Runs.** Each path game's counted S0, S1, S2 and S4 run, found as H4 finds them
(``analysis.arc_h4.load``), read from ``<raw root>/arc_path/<run>/harness/`` (gitignored):
``step_NNN.json`` (``messages_sent``, ``assistant_response``, ``usage``, ``retries``) and
``compaction_NNN.json`` (``before_step``, ``trigger_tokens``), plus ``harness.log`` for S0's trims.

**Readings** (definitions in ``summary_lines``):

* provider tokens per character of request text, by config and game;
* 175,000 provider tokens expressed in characters, at each game's S0 rate;
* the step before which each run first lost history (S0's first trim, the others' first summary);
* a replay of S0's own histories: rebuilt from its step files, trimmed at 175,000 characters
  (which must reproduce the recorded request of every S0 call step, or the script refuses), then
  trimmed as if the harness estimated tokens at the game's median S0 rate (and, as a
  sensitivity reading, its lower-quartile rate): S0's windows with its limit in tokens, on S0's
  own moves;
* the share of each request's characters that are the model's earlier replies;
* the verbatim history each config showed per call step, pooled and per game;
* S1's trigger: whether the request alone was under 175,000 tokens (the trigger also counts the
  reply), and the request's size against S0's limit;
* the counted runs' S1 − S0 RHAE per game.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics as st
import sys
from datetime import UTC, datetime
from pathlib import Path

from analysis import arc_h4
from analysis import checkpoint_c as cc
from common import runmeta

CONFIGS = ("S0", "S1", "S2", "S4")
RATE_CONFIGS = ("S0", "S1", "S2")  # S4's request also carries replayed reasoning: no text rate
LIMIT = 175_000
BRIDGE = "Earlier conversation history was compacted."
OUTPUTS = ("trigger.json", "summary.md", "meta.json")
RESULTS = Path(__file__).resolve().parents[1] / "results"

SAVED = re.compile(r"Saved step (\d+) to")
TRIMMED = re.compile(r"Trimmed oldest turn")


# --- reading one run ------------------------------------------------------------------------

def load_steps(raw: Path) -> list[dict]:
    steps = [json.loads(p.read_text(encoding="utf-8"))
             for p in (raw / "harness").glob("step_*.json")]
    return sorted(steps, key=lambda d: d["step"])


def load_compactions(raw: Path) -> list[dict]:
    cs = [json.loads(p.read_text(encoding="utf-8"))
          for p in (raw / "harness").glob("compaction_*.json")]
    return sorted(cs, key=lambda c: c["before_step"])


def first_trim_before(raw: Path) -> int | None:
    """The step whose request was the first to be trimmed: a trim logged after step s was
    saved happened while step s + 1's request was prepared."""
    last = 0
    for line in (raw / "harness.log").read_text(encoding="utf-8", errors="replace").splitlines():
        if m := SAVED.search(line):
            last = int(m.group(1))
        elif TRIMMED.search(line):
            return last + 1
    return None


def is_call(d: dict) -> bool:
    """A step with a model reply (forced RESET steps have no call and no usage)."""
    u = d.get("usage") or {}
    return d.get("assistant_response") is not None and (u.get("total_tokens") or 0) > 0


def chars(messages) -> int:
    return sum(len(m["content"] if isinstance(m, dict) else m[1]) for m in messages)


def tokens_per_char(steps: list[dict], after_compaction: set[int]) -> list[float]:
    """prompt_tokens / request characters on clean call steps: no retries (a step's usage
    sums its attempts) and not the first step after a summary. That second exclusion is a
    conservative choice: a step file's usage does not include the summary call (that is in
    compaction_NNN.json; only ARC's action metadata adds it)."""
    return [d["usage"]["prompt_tokens"] / chars(d["messages_sent"]) for d in steps
            if is_call(d) and d["retries"] == 0 and d["step"] not in after_compaction]


def verbatim(messages: list[dict]) -> tuple[int, int]:
    """Characters and replies of the earlier history shown verbatim: every message but the
    system prompt, the summary bridge and the current observation (the last message)."""
    kept = [m for m in messages[1:-1] if not m["content"].startswith(BRIDGE)]
    return chars(kept), sum(1 for m in kept if m["role"] == "assistant")


def reply_shares(steps: list[dict], after_compaction: set[int]) -> list[float]:
    """The share of request characters that are the model's earlier replies, on the clean
    call steps ``tokens_per_char`` reads (the summary bridge is a user message)."""
    return [sum(len(m["content"]) for m in d["messages_sent"] if m["role"] == "assistant")
            / chars(d["messages_sent"]) for d in steps
            if is_call(d) and d["retries"] == 0 and d["step"] not in after_compaction]


# --- the S0 replay --------------------------------------------------------------------------

def rebuild(steps: list[dict]) -> list[tuple[dict, list[tuple[str, str]]]]:
    """S0's untrimmed conversation before each step: the first request, then each later
    request's new message, then the step's reply. Refuses unless each later request, after its
    system prompt, is a suffix of the history plus exactly one new user message (the
    observation, or a forced RESET's GAME_OVER frame)."""
    full: list[tuple[str, str]] | None = None
    out = []
    for d in steps:
        sent = [(m["role"], m["content"]) for m in d.get("messages_sent") or []]
        if full is None:
            full = sent[:]
        else:
            body, new = sent[1:], None
            for k in range(len(full)):
                tail = full[1 + k:]
                if len(tail) <= len(body) and body[:len(tail)] == tail:
                    new = body[len(tail):]
                    break
            if new is None or len(new) != 1 or new[0][0] != "user":
                raise cc.Refusal(f"step {d['step']}: its request is not the history's suffix "
                                 "plus one new user message")
            full = full + new
        out.append((d, full[:]))
        if d.get("assistant_response") is not None:
            full = full + [("assistant", d["assistant_response"])]
    return out


def trim(conv: list[tuple[str, str]], over) -> list[tuple[str, str]]:
    """The harness's ``_trim_oldest_turn`` loop: while ``over(conv)``, drop the first user
    message after the system prompt and the reply after it, keeping at least 2 messages."""
    conv = conv[:]
    while over(conv):
        i = next((j for j in range(1, len(conv)) if conv[j][0] == "user"), None)
        if i is None:
            break
        end = i + 2 if i + 1 < len(conv) and conv[i + 1][0] == "assistant" else i + 1
        if len(conv) - (end - i) < 2:
            break
        conv = conv[:i] + conv[end:]
    return conv


def replies(conv) -> int:
    return sum(1 for role, _ in conv if role == "assistant")


def replay(steps: list[dict], rate: float) -> dict:
    """S0's windows at 175,000 characters (checked against what was sent) and at 175,000
    estimated tokens (characters × rate)."""
    rows = [(d, full) for d, full in rebuild(steps) if is_call(d)]

    def by_chars(c):  # the harness's estimate: characters at 1 character per token
        return math.ceil(chars(c)) > LIMIT

    def by_tokens(c):  # the same with the estimate in tokens at the game's rate
        return math.ceil(chars(c) * rate) > LIMIT

    reproduced, extra, changed = 0, [], 0
    for d, full in rows:
        w0, w1 = trim(full, by_chars), trim(full, by_tokens)
        reproduced += w0 == [(m["role"], m["content"]) for m in d["messages_sent"]]
        extra.append(replies(w1) - replies(w0))
        changed += w1 != w0
    if reproduced != len(rows):
        raise cc.Refusal(f"the replay at {LIMIT:,} characters reproduces {reproduced} of "
                         f"{len(rows)} requests S0 sent")
    return {"call_steps": len(rows), "reproduced": reproduced, "steps_changed": changed,
            "extra_replies_mean": st.mean(extra) if extra else 0.0,
            "replies_mean_at_chars": st.mean(replies(trim(f, by_chars)) for _, f in rows),
            "limit_chars_equivalent": LIMIT / rate}


# --- per run and pooled -----------------------------------------------------------------------

def read_run(raw: Path, config: str) -> dict:
    steps = load_steps(raw)
    comps = load_compactions(raw)
    after = {c["before_step"] for c in comps}
    calls = [d for d in steps if is_call(d)]
    v = [verbatim(d["messages_sent"]) for d in calls]
    run = {"call_steps": len(calls), "rates": tokens_per_char(steps, after),
           "reply_shares": reply_shares(steps, after),
           "verbatim_chars": [c for c, _ in v], "verbatim_replies": [r for _, r in v],
           "compactions": len(comps)}
    if config == "S0":
        run["first_loss_before"] = first_trim_before(raw)
    else:
        run["first_loss_before"] = comps[0]["before_step"] if comps else None
        triggers = []
        for c in comps:
            prior = [d for d in calls if d["step"] < c["before_step"]]
            if prior and prior[-1]["retries"] == 0:
                d = prior[-1]
                triggers.append({"prompt_tokens": d["usage"]["prompt_tokens"],
                                 "trigger_tokens": c.get("trigger_tokens"),
                                 "request_chars": chars(d["messages_sent"])})
        run["triggers"] = triggers
    return run


def _q(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0}
    s = sorted(xs)
    return {"n": len(s), "median": st.median(s), "q1": s[len(s) // 4], "q3": s[(3 * len(s)) // 4],
            "min": s[0], "max": s[-1], "mean": st.mean(s)}


def compute(root: Path, raw_root: Path, generated: str, git: dict) -> dict:
    d = arc_h4.load(root, with_s1=True)
    if d.incomplete:
        raise cc.Refusal("a unit lacks a counted run: " + "; ".join(d.incomplete))
    runs: dict[tuple[str, str], dict] = {}
    for (g, c), u in d.units.items():
        if c not in CONFIGS:
            continue
        raw = raw_root / cc.EXPERIMENT / u.counted.run_id
        if not (raw / "harness.log").is_file():
            raise cc.Refusal(f"no raw harness.log for {u.counted.run_id} under {raw_root}")
        r = read_run(raw, c)
        r.update(run_id=u.counted.run_id, rhae=u.counted.rhae)
        if c == "S0":
            steps = load_steps(raw)
            r["replay"] = replay(steps, st.median(r["rates"]))
            r["replay_q1"] = replay(steps, _q(r["rates"])["q1"])
        runs[(g, c)] = r
    games = list(d.games)
    out = {"generated_utc": generated, **git, "status": "EXPLORATORY", "limit": LIMIT,
           "path_games": games, "per_game": {}, "pooled": {}}
    for g in games:
        row = {}
        for c in CONFIGS:
            r = runs[(g, c)]
            row[c] = {"run_id": r["run_id"], "rhae": r["rhae"], "call_steps": r["call_steps"],
                      "first_loss_before": r["first_loss_before"],
                      "compactions": r["compactions"],
                      "verbatim_chars_mean": st.mean(r["verbatim_chars"]),
                      "verbatim_replies_mean": st.mean(r["verbatim_replies"])}
            if c in RATE_CONFIGS:
                row[c]["tokens_per_char"] = _q(r["rates"])
                row[c]["reply_share"] = _q(r["reply_shares"])
        for c in CONFIGS[1:]:
            row[c]["verbatim_chars_vs_S0"] = (row[c]["verbatim_chars_mean"]
                                              / row["S0"]["verbatim_chars_mean"])
            row[c]["verbatim_replies_vs_S0"] = (row[c]["verbatim_replies_mean"]
                                                / row["S0"]["verbatim_replies_mean"])
        s0 = row["S0"]
        s0["replay"] = runs[(g, "S0")]["replay"]
        s0["replay_q1"] = runs[(g, "S0")]["replay_q1"]
        s0["limit_ratio"] = s0["replay"]["limit_chars_equivalent"] / LIMIT
        row["delta_S1_minus_S0"] = row["S1"]["rhae"] - s0["rhae"]
        out["per_game"][g] = row
    for c in CONFIGS:
        rs = [runs[(g, c)] for g in games]
        p = {"verbatim_chars_per_step": st.mean(x for r in rs for x in r["verbatim_chars"]),
             "verbatim_replies_per_step": st.mean(x for r in rs for x in r["verbatim_replies"])}
        if c in RATE_CONFIGS:
            p["tokens_per_char"] = _q([x for r in rs for x in r["rates"]])
        if c != "S0":
            t = [x for r in rs for x in r["triggers"]]
            p["triggers"] = len(t)
            p["triggers_prompt_under_limit"] = sum(x["prompt_tokens"] < LIMIT for x in t)
            p["trigger_request_chars_over_limit"] = _q([x["request_chars"] / LIMIT for x in t])
        out["pooled"][c] = p
    base = out["pooled"]["S0"]
    for c in CONFIGS[1:]:
        q = out["pooled"][c]
        q["verbatim_chars_vs_S0"] = q["verbatim_chars_per_step"] / base["verbatim_chars_per_step"]
        q["verbatim_replies_vs_S0"] = (q["verbatim_replies_per_step"]
                                       / base["verbatim_replies_per_step"])
    deltas = {g: out["per_game"][g]["delta_S1_minus_S0"] for g in games}
    unchanged = [g for g in games if out["per_game"][g]["S0"]["replay"]["steps_changed"] == 0]
    out["delta_sum"] = sum(deltas.values())
    out["games_replay_unchanged"] = unchanged
    out["delta_share_replay_unchanged"] = (sum(deltas[g] for g in unchanged) / out["delta_sum"]
                                           if out["delta_sum"] else None)
    return out


# --- output -----------------------------------------------------------------------------------

def _f(x, nd=3) -> str:
    return "n/a" if x is None else f"{x:,.{nd}f}"


def summary_lines(h: dict) -> list[str]:
    games, lim = h["path_games"], h["limit"]
    pg = h["per_game"]
    unchanged = h["games_replay_unchanged"]
    changed = [g for g in games if g not in unchanged]
    L = ["# S0's character limit against S1's token trigger (exploratory)", "",
         (f"Computed {h['generated_utc']} at commit {h['git_commit'][:7]} (dirty: "
          f"{h['git_dirty']}). **Exploratory:** written after the ARC path results were read. "
          "No test, no verdict. It enters no hypothesis, gate or kill rule."), "",
         (f"S0 drops its oldest user/assistant pair while the request's characters (system "
          f"prompt included, at 1 character per token) exceed {lim:,}. S1 summarizes once a call "
          f"reports {lim:,} provider tokens, its reply and thinking included. Counted runs of "
          f"each config on the {len(games)} path games."), "",
         "## Provider tokens per character of request text", "",
         ("Clean call steps only: no retries (a step's usage sums its attempts) and not the "
          "first step after a summary. Median [quartiles]. Reply share: the median share of "
          "request characters that are the model's earlier replies."), "",
         ("| Game | " + " | ".join(RATE_CONFIGS) + " | S0 reply share | 175k tokens in "
          "characters (S0 median rate) |"),
         "|---|" + "---|" * (len(RATE_CONFIGS) + 2)]
    for g in games:
        row = pg[g]
        cells = [f"{_f(row[c]['tokens_per_char']['median'])} "
                 f"[{_f(row[c]['tokens_per_char']['q1'])}, "
                 f"{_f(row[c]['tokens_per_char']['q3'])}]" for c in RATE_CONFIGS]
        s0 = row["S0"]
        L.append(f"| {g} | " + " | ".join(cells)
                 + f" | {_f(s0['reply_share']['median'])} | "
                 f"{s0['replay']['limit_chars_equivalent']:,.0f} "
                 f"({s0['limit_ratio']:.3f}× S0's limit) |")
    L += ["", "## When each run first lost history", "",
          ("The step whose request was the first to have lost history: S0's first trim, the "
           "others' first summary."), "",
          "| Game | " + " | ".join(CONFIGS) + " |", "|---|" + "---|" * len(CONFIGS)]
    for g in games:
        L.append(f"| {g} | " + " | ".join(str(pg[g][c]["first_loss_before"])
                                         for c in CONFIGS) + " |")
    L += ["", "## S0's windows with its limit in tokens (a replay of S0's own histories)", "",
          (f"S0's untrimmed history before each call step is rebuilt from its step files. "
           f"Trimmed at {lim:,} characters it reproduces the recorded request of every S0 call "
           f"step (checked: the script refuses otherwise). It is then trimmed as the harness "
           f"would with its estimate in tokens: characters × the game's median S0 rate, "
           f"against {lim:,}. That approximates S0's windows with its limit in tokens, on S0's "
           "own moves. The last column repeats it at the game's lower-quartile S0 rate. "
           "Earlier replies kept = assistant messages in the window."), "",
          ("| Game | Call steps | Reproduced at 175k characters | Steps whose window changes | "
           "Earlier replies kept, at 175k characters | Extra replies kept per step | Steps "
           "changed at the lower-quartile rate |"),
          "|---|---|---|---|---|---|---|"]
    for g in games:
        rp, rq = pg[g]["S0"]["replay"], pg[g]["S0"]["replay_q1"]
        L.append(f"| {g} | {rp['call_steps']} | {rp['reproduced']} | {rp['steps_changed']} | "
                 f"{_f(rp['replies_mean_at_chars'], 2)} | {_f(rp['extra_replies_mean'], 2)} | "
                 f"{rq['steps_changed']} |")
    share = h["delta_share_replay_unchanged"]
    L += ["", (f"At the median rate the window never changes on {', '.join(unchanged) or 'no game'}"
               f". Those games hold {_f(share * 100 if share is not None else None, 1)}% of the "
               f"summed S1 − S0 RHAE ({_f(h['delta_sum'], 2)} points over the {len(games)} "
               "games)."), "",
          "| Game | S0 RHAE | S1 RHAE | S1 − S0 |", "|---|---|---|---|"]
    for g in games:
        row = pg[g]
        L.append(f"| {g} | {_f(row['S0']['rhae'], 2)} | {_f(row['S1']['rhae'], 2)} | "
                 f"{_f(row['delta_S1_minus_S0'], 2)} |")
    L += ["", "## Verbatim history per call step", "",
          ("The earlier history the model saw verbatim: every message but the system prompt, "
           "the summary bridge and the current observation. Pooled: means over all call steps "
           "of the counted runs, so each game weighs by its steps, and the step mix differs by "
           "config. Per game below."), "",
          "| Config | Characters | Earlier replies | Characters vs S0 | Replies vs S0 |",
          "|---|---|---|---|---|"]
    for c in CONFIGS:
        p = h["pooled"][c]
        L.append(f"| {c} | {p['verbatim_chars_per_step']:,.0f} | "
                 f"{_f(p['verbatim_replies_per_step'], 2)} | "
                 f"{_f(p.get('verbatim_chars_vs_S0'))} | {_f(p.get('verbatim_replies_vs_S0'))} |")
    L += ["", "Per game, each config against S0 (characters / earlier replies):", "",
          "| Game | S0 characters / replies | " + " | ".join(CONFIGS[1:]) + " |",
          "|---|---|" + "---|" * len(CONFIGS[1:])]
    for g in games:
        s0 = pg[g]["S0"]
        L.append(f"| {g} | {s0['verbatim_chars_mean']:,.0f} / "
                 f"{_f(s0['verbatim_replies_mean'], 2)} | "
                 + " | ".join(f"{_f(pg[g][c]['verbatim_chars_vs_S0'])} / "
                              f"{_f(pg[g][c]['verbatim_replies_vs_S0'])}" for c in CONFIGS[1:])
                 + " |")
    L += ["", ("S4's characters are the readable projection the harness logs (`messages_sent`). "
               "It leaves out the replayed reasoning items that the provider counts as prompt "
               "tokens. So S4's characters undercount what it sent, and they are not "
               "like-for-like with S0-S2."), "",
          "## The summary trigger", "",
          ("For each summary, the last call before it, when it had no retries. The trigger is "
           "the call's `total_tokens`, so it counts the reply and its thinking too. It is "
           "checked after the request is sent, so the request that trips it can be past the "
           "limit."), "",
          ("| Config | Triggers read | Request alone under 175k tokens | Request characters ÷ "
           "175k: median [min, max] |"), "|---|---|---|---|"]
    for c in CONFIGS[1:]:
        p = h["pooled"][c]
        q = p["trigger_request_chars_over_limit"]
        L.append(f"| {c} | {p['triggers']} | {p['triggers_prompt_under_limit']} | "
                 f"{_f(q.get('median'))} [{_f(q.get('min'))}, {_f(q.get('max'))}] |")
    L += ["", "For S4 the characters are the readable projection only (above).", ""]
    extra = "".join(f". On {g} it changes {pg[g]['S0']['replay']['steps_changed']} of "
                    f"{pg[g]['S0']['replay']['call_steps']} windows and keeps "
                    f"{pg[g]['S0']['replay']['extra_replies_mean']:.2f} more earlier replies per "
                    "step" for g in changed)
    low = min(games, key=lambda g: pg[g]["S0"]["tokens_per_char"]["median"])
    margins = [(pg[g]["S0"]["limit_ratio"] - 1) * 100 for g in unchanged]
    margin = (f"{min(margins):.1f}-{max(margins):.1f}%" if margins else "n/a")
    others = [pg[g]["S0"]["reply_share"]["median"] for g in games if g != low]
    L += ["## What it does not show", "",
          ("- **Which part of the loss policy does the work.** S0→S1 also replaces dropped turns "
           "by a summary, resets the history at each summary, checks its trigger after the "
           "request is sent and counts the reply. This script shows only that a limit in "
           "tokens, replayed on S0's own histories at each game's median S0 rate, changes no "
           f"window on {', '.join(unchanged) or 'no game'}{extra}. It measures S0's histories, "
           "not S1's."),
          ("- **Stochastic runs.** One counted run per config and game. The replay holds S0's "
           "own moves, observations and replies fixed. A run with the token limit would make "
           "different moves."),
          ("- **One rate per game.** Where the window never changes, the token limit sits only "
           f"{margin} above S0's character limit, so a rate a little below the median can change "
           "a few windows (the last replay column). The lowest S0 rate is "
           f"{low}'s ({_f(pg[low]['S0']['tokens_per_char']['median'])}), where earlier replies "
           f"are a median {_f(pg[low]['S0']['reply_share']['median'])} of the request's "
           f"characters, against at most {_f(max(others) if others else None)} on the other "
           "games. That is an association, not a measured cause."),
          ("- **Exploratory, after the results were read.** Nothing here is a test or enters a "
           "decision.")]
    return L


def write(out_dir: Path, run_id: str, h: dict, text: str, git: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "trigger.json").write_text(json.dumps(h, indent=2) + "\n", encoding="utf-8",
                                          newline="\n")
    (out_dir / "summary.md").write_text(text, encoding="utf-8", newline="\n")
    config = {"limit": h["limit"], "configs": list(CONFIGS), "path_games": h["path_games"]}
    runs = [h["per_game"][g][c]["run_id"] for g in h["path_games"] for c in CONFIGS]
    return runmeta.write_meta(
        out_dir, git=git, experiment="arc_trigger", run_id=run_id,
        cell_or_config="s0-limit-unit", config=config, model_requested=None,
        model_returned=None, reasoning_effort=None, reasoning_context_requested=None,
        reasoning_context_echoed=None, template_id=None, repeat_index=None, seeds=None,
        started_utc=h["generated_utc"], finished_utc=runmeta.utc_now(),
        exit_reason="completed", tokens=None, cost_usd=0.0, raw_transcript_path=None,
        outputs=list(OUTPUTS), paid_calls=0, runs=runs)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--results-root", type=Path, default=RESULTS)
    ap.add_argument("--raw-root", type=Path, default=None,
                    help="the folder holding raw/ runs (default: <results root>/raw)")
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = a.results_root
    now = datetime.now(UTC)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    git = runmeta.git_state()
    try:
        h = compute(root, a.raw_root or root / "raw", now.isoformat(timespec="seconds"), git)
    except cc.Refusal as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    text = "\n".join(summary_lines(h)) + "\n"
    print(text)
    if not a.no_write:
        out = a.out_dir or root / "arc_trigger" / run_id
        write(out, run_id, h, text, git)
        print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
