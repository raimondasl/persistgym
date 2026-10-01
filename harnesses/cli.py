"""Command line for the harness cells.

$0 commands (fake model or local files, no network):
    uv run python -m harnesses cells
    uv run python -m harnesses dry-run --cell W-n-0 --task-cell observed-nonrec-far
    uv run python -m harnesses pilot-report      # pooled pilot report (PREREG §11)

Paid commands refuse unless PERSISTGYM_ALLOW_PAID=1, --approved-block and --planned-usd are
given, PREREG.md is committed, and results/decisions.md holds the researcher's line
"approved_block: <name> | experiments: <exp1>,<exp2>,... | max_usd: <amount>" on origin/main,
in HEAD and in the working tree, listing the experiment, with room under max_usd and the
phase cap (common/approval.py). The OpenAI SDK reads the key from the environment:
    PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses probe-echo \
        --approved-block "1-pilots" --planned-usd 0.5
    PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses run --cell F-0 \
        --model gpt-6-luna --n 1 --approved-block "1-pilots" --planned-usd 1
    # D11: sol on derived-far x T_d templates plus observed-far x T_d/3 of them
    ... python -m harnesses run --cell F-r --model gpt-6.1-sol --split main --matrix d11 \
        --n 120 --experiment persistgym --approved-block "<block>" --planned-usd <usd>
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
from harnesses import blinding, diagnostics, probes
from harnesses.cells import CELLS, get_cell
from harnesses.config import HarnessConfig
from harnesses.fake import FakeModel
from harnesses.matrix import RunMatrix
from harnesses.openai_transport import (
    BudgetExceeded,
    OpenAIResponsesTransport,
    PaidCallsNotAllowed,
)
from harnesses.runner import RAW, RESULTS, require_plain_name, run_batch, run_episode
from persistgym.config import GeneratorConfig
from persistgym.episode import TaskCell
from persistgym.render import generate

PILOT_MAX_EPISODES = 10  # CLAUDE.md: a pilot is <= 10 episodes
PILOT_EXPERIMENT = "persistgym_pilot"
PILOT_SPLIT = "pilot"


def _run_id(tag: str) -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + tag


def _rel(path) -> str:
    try:
        return path.relative_to(runmeta.REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


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


def _run_matrix(a) -> RunMatrix:
    """--matrix full (default: --task-cell on --n templates), --matrix d11 (D11: derived-far
    on --n = T_d templates, observed-far on the first --n-observed = T_o of them, default
    T_d / 3) or --cell-templates TASK_CELL=N ... (a custom matrix)."""
    if a.cell_templates:
        if a.matrix != "full" or a.task_cell != ["all"] or a.n_observed is not None:
            raise ValueError("--cell-templates replaces --matrix, --task-cell and "
                             "--n-observed")
        return RunMatrix.parse(a.cell_templates)
    if a.matrix == "d11":
        if a.task_cell != ["all"]:
            raise ValueError("--matrix d11 fixes the task cells; leave out --task-cell")
        return RunMatrix.d11(a.n, a.n_observed)
    if a.n_observed is not None:
        raise ValueError("--n-observed applies to --matrix d11 only")
    return RunMatrix.full(a.n, None if a.task_cell == ["all"] else a.task_cell)


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


def _guarded_transport(a, model: str, experiment: str, planned_usd: float | None):
    try:
        return OpenAIResponsesTransport(model=model, approved_block=a.approved_block,
                                        experiment=experiment, planned_usd=planned_usd)
    except PaidCallsNotAllowed as e:
        print(f"refused: {e}", file=sys.stderr)
        return None


def cmd_run(a) -> int:
    cell = get_cell(a.cell)
    if a.experiment == PILOT_EXPERIMENT and a.split != PILOT_SPLIT:
        # PLAN §16.5: pilot templates use a disjoint seed range, so a pilot never sees (or
        # reports outcomes on) the templates of the main sweep.
        print(f"refused: {PILOT_EXPERIMENT} runs use --split {PILOT_SPLIT} only, got "
              f"{a.split!r}", file=sys.stderr)
        return 2
    if a.split == PILOT_SPLIT and a.experiment != PILOT_EXPERIMENT:
        # The reverse: pilot templates are pilot data (PREREG §11), so they run only under
        # the blinded experiment. Without this, `--experiment persistgym` with the default
        # --split pilot would commit per-arm outcomes on pilot templates to results/.
        print(f"refused: --split {PILOT_SPLIT} templates are pilot data and run only with "
              f"--experiment {PILOT_EXPERIMENT} (blinded, PREREG §11), got "
              f"{a.experiment!r}; a main-sweep run needs --split main", file=sys.stderr)
        return 2
    gen = _gen_config(a.gen_set)
    try:
        matrix = _run_matrix(a)
    except ValueError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    if a.split == "main":
        for w in matrix.block_warnings(a.start):
            print(f"note (D7, incomplete balance block): {w}", file=sys.stderr)
    episodes = matrix.episodes(a.split, a.start, gen, a.variant)
    if a.experiment == PILOT_EXPERIMENT and len(episodes) > PILOT_MAX_EPISODES:
        print(f"refused: a pilot is at most {PILOT_MAX_EPISODES} episodes, got "
              f"{len(episodes)}", file=sys.stderr)
        return 2
    run_id = a.run_id or _run_id(f"{cell.ascii_id}-{a.model}")
    try:
        require_plain_name("--run-id", run_id)
    except ValueError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    transport = _guarded_transport(a, a.model, a.experiment, a.planned_usd)
    if transport is None:
        return 2
    meta = run_batch(episodes, cell, _harness_config(a), transport, experiment=a.experiment,
                     run_id=run_id, milestone=a.milestone, results_root=RESULTS,
                     raw_root=RAW, run_matrix=matrix.to_dict(),
                     notes=(f"{a.split} {a.start}-{a.start + matrix.n_templates - 1}"
                            f" matrix={matrix.name}"))
    print(json.dumps({k: meta[k] for k in ("run_id", "exit_reason", "reasoning_context_echoed",
                                           "model_returned", "cost_usd")}, indent=2))
    return 0


def _probe_run(a, kind: str) -> int:
    experiment = "toggle_pilot" if kind == "echo" else "replay_probe"
    status = 0
    # --planned-usd is the total for the whole command: each model's transport may spend only
    # what the earlier models left, measured like block spend (transport.spent_usd).
    spent = 0.0
    for model in a.model:
        remaining = None if a.planned_usd is None else a.planned_usd - spent
        if remaining is not None and remaining <= 0:
            print(f"refused: --planned-usd {a.planned_usd} is the total for all models and "
                  f"was used up before {model}", file=sys.stderr)
            return 2
        transport = _guarded_transport(a, model, experiment, remaining)
        if transport is None:
            return 2
        run_id = (f"{a.run_id}-{model}" if a.run_id and len(a.model) > 1
                  else a.run_id or _run_id(f"{kind}-{model}"))
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
            spent += transport.spent_usd
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
                raw_transcript_path=_rel(raw_dir / "transcript.jsonl.gz"))
        print(f"{model}: {exit_reason}; echoed {echoed}; results in {out_dir}")
    return status


def cmd_pilot_report(a) -> int:
    """$0: pool every raw pilot run into the allowed pilot report (PREREG §11) and write it to
    results/<experiment>/pooled-<time>/pilot_report.json."""
    runs = blinding.load_raw_runs(RAW, a.experiment)
    if not runs:
        print(f"no raw runs under {_rel(RAW / a.experiment)}", file=sys.stderr)
        return 1
    report = blinding.pooled_report(runs, experiment=a.experiment)
    report.update(generated_utc=runmeta.utc_now(), prereg_version=runmeta.prereg_version(),
                  **runmeta.git_state())
    out = RESULTS / a.experiment / ("pooled-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "pilot_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False)
                                           + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"written: {_rel(out / 'pilot_report.json')}", file=sys.stderr)
    return 0


def cmd_summary_timing(a) -> int:
    print(json.dumps(diagnostics.summary_timing(
        a.n, split=a.split, summary_tokens=a.summary_tokens,
        keep_recent=tuple(a.keep_recent)), indent=2))
    return 0


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
                        help="name of the researcher-approved spending block (PLAN §16.2); "
                             "its approval line in results/decisions.md must list the "
                             "experiment and leave room under its max_usd")
        sp.add_argument("--planned-usd", type=float, default=None,
                        help="planned spend of the whole command in USD, measured like block "
                             "spend and the phase caps: the larger of the list and billed "
                             "estimates, so on Flex the list cost (for probes, the total "
                             "over all --model values)")

    sub.add_parser("cells", help="list the harness cells").set_defaults(fn=cmd_cells)

    st = sub.add_parser("summary-timing", help="where Σ cells compact at the default volume ($0)")
    st.add_argument("--n", type=int, default=20)
    st.add_argument("--split", default="main")
    st.add_argument("--summary-tokens", type=int, default=300)
    st.add_argument("--keep-recent", type=int, nargs="+", default=[0, 16_650])
    st.set_defaults(fn=cmd_summary_timing)

    d = sub.add_parser("dry-run", help="one episode with the fake model ($0)")
    episode_args(d)
    request_args(d)
    d.add_argument("--task-cell", default="observed-nonrec-far")
    d.set_defaults(fn=cmd_dry_run)

    r = sub.add_parser("run", help="paid run of one harness cell (guarded)")
    episode_args(r)
    request_args(r)
    paid_args(r)
    r.add_argument("--n", type=int, default=1,
                   help="templates per task cell (--matrix d11: T_d, the derived-far count)")
    r.add_argument("--task-cell", nargs="+", default=["all"])
    r.add_argument("--matrix", choices=("full", "d11"), default="full",
                   help="full: --task-cell on --n templates; d11: derived-far cells on --n "
                        "templates and observed-far cells on the first --n-observed (D11)")
    r.add_argument("--n-observed", type=int, default=None,
                   help="--matrix d11: observed-far templates T_o (default --n / 3)")
    r.add_argument("--cell-templates", nargs="+", default=None, metavar="TASK_CELL=N",
                   help="custom matrix: each task cell on its first N templates from --start")
    r.add_argument("--experiment", default="persistgym_pilot")
    r.set_defaults(fn=cmd_run)

    pr = sub.add_parser("pilot-report",
                        help="pooled pilot report from the raw pilot runs ($0, PREREG §11)")
    pr.add_argument("--experiment", default=PILOT_EXPERIMENT)
    pr.set_defaults(fn=cmd_pilot_report)

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
