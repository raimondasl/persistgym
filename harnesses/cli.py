"""Command line for the harness cells.

$0 commands (fake model, no network):
    uv run python -m harnesses cells
    uv run python -m harnesses dry-run --cell W-n-0 --task-cell observed-nonrec-far

Paid commands (refuse unless PERSISTGYM_ALLOW_PAID=1, --approved-block and --planned-usd are
given, PREREG.md exists and the phase cap in common/costs.py has room; see
harnesses/openai_transport.py). The OpenAI SDK reads the key from the environment:
    PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses probe-echo \
        --approved-block "1-pilots" --planned-usd 0.5
    PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses run --cell F-0 \
        --model gpt-6-luna --n 1 --approved-block "1-pilots" --planned-usd 1
"""

from __future__ import annotations

import argparse
import dataclasses
import gzip
import json
import sys
from datetime import UTC, datetime

import openai

from common import runmeta
from harnesses import probes
from harnesses.cells import CELLS, get_cell
from harnesses.config import HarnessConfig
from harnesses.fake import FakeModel
from harnesses.openai_transport import (
    BudgetExceeded,
    OpenAIResponsesTransport,
    PaidCallsNotAllowed,
)
from harnesses.runner import RAW, RESULTS, run_batch, run_episode
from persistgym.config import GeneratorConfig
from persistgym.episode import ALL_CELLS, TaskCell
from persistgym.render import generate

PILOT_MAX_EPISODES = 10  # CLAUDE.md: a pilot is <= 10 episodes


def _run_id(tag: str) -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + tag


def _gen_config(sets: list[str]) -> GeneratorConfig:
    changes = {}
    for s in sets or []:
        key, _, raw = s.partition("=")
        val = json.loads(raw)
        changes[key] = tuple(val) if isinstance(val, list) else val
    return GeneratorConfig().replace(**changes)


def _harness_config(a) -> HarnessConfig:
    return HarnessConfig(model=a.model, reasoning_effort=a.effort, reasoning_mode=a.mode,
                         service_tier=a.service_tier, W_tokens=a.W)


def _episodes(a, gen: GeneratorConfig):
    cells = ALL_CELLS if a.task_cell == ["all"] else [TaskCell.from_id(c) for c in a.task_cell]
    out = []
    for _, eps in generate(a.split, range(a.start, a.start + a.n), gen, cells, (a.variant,)):
        out.extend(eps)
    return out


def cmd_cells(a) -> int:
    print(f"{'cell':<8}{'ascii':<12}{'history':<9}{'notes':<7}{'reasoning.context':<19}role")
    for c in CELLS.values():
        print(f"{c.cell_id:<8}{c.ascii_id:<12}{c.history:<9}{c.notes!s:<7}"
              f"{c.reasoning_context:<19}{c.role}{' (optional)' if c.optional else ''}")
    return 0


def cmd_dry_run(a) -> int:
    """Run one generated episode with the fake model and print what every request sends."""
    cell = get_cell(a.cell)
    gen = _gen_config(a.gen_set)
    ep = next(e for _, eps in generate(a.split, [a.start], gen, [TaskCell.from_id(a.task_cell)],
                                       (a.variant,)) for e in eps)
    events: list[dict] = []
    run = run_episode(ep, cell, _harness_config(a), FakeModel(), recorder=events.append)
    print(f"{ep.episode_id} under {cell.cell_id}: need step {ep.need_step}, "
          f"{run.n_requests} requests, exit {run.exit_reason}")
    print("  labels: U<t> observation of turn t, R<t>/A<t> its reasoning item and reply, "
          "B<k> summary bridge k, Q summary request")
    for e in events:
        print(f"  #{e['request_index']:02d} {e['kind']:<7} step={e['pending_step']:>2} "
              f"reasoning.context={e['payload']['reasoning']['context']} "
              f"{' '.join(e['trace'])}")
    print(f"payload S at need: {run.need_payload and run.need_payload['S']}; designed S "
          f"(obs only): {run.designed['S_window_obs_only']}")
    return 0


def _guarded_transport(a, model: str, experiment: str):
    try:
        return OpenAIResponsesTransport(model=model, approved_block=a.approved_block,
                                        experiment=experiment, planned_usd=a.planned_usd)
    except PaidCallsNotAllowed as e:
        print(f"refused: {e}", file=sys.stderr)
        return None


def cmd_run(a) -> int:
    cell = get_cell(a.cell)
    gen = _gen_config(a.gen_set)
    episodes = _episodes(a, gen)
    if a.experiment == "persistgym_pilot" and len(episodes) > PILOT_MAX_EPISODES:
        print(f"refused: a pilot is at most {PILOT_MAX_EPISODES} episodes, got "
              f"{len(episodes)}", file=sys.stderr)
        return 2
    transport = _guarded_transport(a, a.model, a.experiment)
    if transport is None:
        return 2
    run_id = a.run_id or _run_id(f"{cell.ascii_id}-{a.model}")
    meta = run_batch(episodes, cell, _harness_config(a), transport, experiment=a.experiment,
                     run_id=run_id, milestone=a.milestone,
                     notes=f"{a.split} {a.start}-{a.start + a.n - 1}")
    print(json.dumps({k: meta[k] for k in ("run_id", "exit_reason", "reasoning_context_echoed",
                                           "model_returned", "cost_usd")}, indent=2))
    return 0


def _probe_run(a, kind: str) -> int:
    experiment = "toggle_pilot" if kind == "echo" else "replay_probe"
    status = 0
    for model in a.model:
        transport = _guarded_transport(a, model, experiment)
        if transport is None:
            return 2
        run_id = a.run_id or _run_id(f"{kind}-{model}")
        out_dir, raw_dir = RESULTS / experiment / run_id, RAW / experiment / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        started, trials = runmeta.utc_now(), []
        cfg = probes.ECHO_CONFIG if kind == "echo" else probes.REPLAY_CONFIG
        cfg = dataclasses.replace(cfg, reasoning_effort=a.effort, reasoning_mode=a.mode,
                                  service_tier=a.service_tier)
        exit_reason = "INCOMPLETE"
        try:
            with gzip.open(raw_dir / "transcript.jsonl.gz", "at", encoding="utf-8") as raw:
                for rep in range(a.n):
                    for ctx in a.contexts:
                        t = (probes.run_echo_check(model, ctx, transport, cfg) if kind == "echo"
                             else probes.run_replay_probe(model, ctx, transport, cfg))
                        raw.write(json.dumps({"repeat": rep, **t}, ensure_ascii=False) + "\n")
                        trials.append({"repeat": rep, "context_requested": ctx,
                                       "echoes": t["echoes"], "outputs": t["outputs"],
                                       **({"score": t["score"]} if "score" in t else {})})
            exit_reason = "COMPLETED"
        except (openai.OpenAIError, BudgetExceeded) as e:
            exit_reason, status = f"ERROR:{type(e).__name__}: {e}", 1
        finally:
            row = transport.finalize(run_id=run_id, milestone=a.milestone,
                                     cell_or_config=f"{kind}-probe")
            with (out_dir / "trials.jsonl").open("a", encoding="utf-8") as f:
                for t in trials:
                    f.write(json.dumps(t, ensure_ascii=False) + "\n")
            echoed = {}
            for t in trials:
                for e in t["echoes"]:
                    echoed[str(e["context_echoed"])] = echoed.get(str(e["context_echoed"]), 0) + 1
            runmeta.write_meta(
                out_dir, experiment=experiment, run_id=run_id, cell_or_config=f"{kind}-probe",
                config={"probe": kind, "probe_config": dataclasses.asdict(cfg),
                        "contexts": a.contexts, "n_per_context": a.n},
                model_requested=model,
                model_returned=sorted({str(e["model_returned"]) for t in trials
                                       for e in t["echoes"]}),
                reasoning_effort=cfg.reasoning_effort, reasoning_context_requested=a.contexts,
                reasoning_context_echoed=echoed, template_id=None, repeat_index=None,
                seeds=None, started_utc=started, finished_utc=runmeta.utc_now(),
                exit_reason=exit_reason, tokens=transport.ledger.totals(),
                cost_usd={"list": transport.ledger.cost_usd_list,
                          "billed_est": transport.ledger.cost_usd_billed_est,
                          "costs_csv_row_appended": row is not None},
                raw_transcript_path=(raw_dir / "transcript.jsonl.gz").relative_to(
                    runmeta.REPO_ROOT).as_posix())
        print(f"{model}: {exit_reason}; echoed {echoed}; results in {out_dir}")
    return status


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="python -m harnesses")
    sub = p.add_subparsers(dest="cmd", required=True)

    def request_args(sp, model_default="gpt-6-luna", multi_model=False):
        if multi_model:
            sp.add_argument("--model", action="append", default=None)
        else:
            sp.add_argument("--model", default=model_default)
        sp.add_argument("--effort", default="medium")
        sp.add_argument("--mode", default="standard")
        sp.add_argument("--service-tier", default="flex")
        sp.add_argument("--milestone", default="M0")
        sp.add_argument("--run-id", default=None)

    def episode_args(sp):
        sp.add_argument("--cell", required=True)
        sp.add_argument("--split", default="pilot")
        sp.add_argument("--start", type=int, default=0)
        sp.add_argument("--variant", default="base")
        sp.add_argument("--W", type=int, default=None, help="default: the episode's W")
        sp.add_argument("--gen-set", action="append", default=[], metavar="FIELD=JSON")

    def paid_args(sp):
        sp.add_argument("--approved-block", default=None,
                        help="name of the researcher-approved spending block (PLAN §16.2)")
        sp.add_argument("--planned-usd", type=float, default=None)

    sub.add_parser("cells", help="list the harness cells").set_defaults(fn=cmd_cells)

    d = sub.add_parser("dry-run", help="one episode with the fake model ($0)")
    episode_args(d)
    request_args(d)
    d.add_argument("--task-cell", default="observed-nonrec-far")
    d.set_defaults(fn=cmd_dry_run)

    r = sub.add_parser("run", help="paid run of one harness cell (guarded)")
    episode_args(r)
    request_args(r)
    paid_args(r)
    r.add_argument("--n", type=int, default=1, help="templates")
    r.add_argument("--task-cell", nargs="+", default=["all"])
    r.add_argument("--experiment", default="persistgym_pilot")
    r.set_defaults(fn=cmd_run)

    for kind in ("echo", "replay"):
        sp = sub.add_parser(f"probe-{kind}", help=f"paid {kind} probe (guarded)")
        request_args(sp, multi_model=True)
        paid_args(sp)
        sp.add_argument("--contexts", nargs="+", default=list(probes.CONTEXTS))
        sp.add_argument("--n", type=int, default=1 if kind == "echo" else 10,
                        help="trials per context")
        sp.set_defaults(fn=lambda a, k=kind: _probe_run(a, k))

    a = p.parse_args(argv)
    if a.cmd.startswith("probe-") and not a.model:
        a.model = list(probes.ECHO_CHECK_MODELS)
    return a.fn(a)
