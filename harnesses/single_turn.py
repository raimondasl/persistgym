"""The position-matched single-turn control of H3, sent to the API (PREREG §3 H3, §4.3, D36).

`persistgym.controls.single_turn_control` flattens a non-recoverable base episode, from its
first step through the need step, into one prompt, as PREREG §3 H3 states it (D10): the
observations in order, each before the need step followed by the oracle's routine action as
a plain "Agent: <expected action>" line, one newline between pieces, ending with the need
observation and its question. `score_single_turn` scores a reply as `EpisodeEnv` scores the
need step. This module sends each such prompt to the model once and scores the reply. CLI:
`python -m harnesses single-turn` (harnesses/cli.py), guarded as `run` is.

**The request** (`build_request`) is the request F-0, H3's multi-turn arm, sends at an
episode's first step, with the flattened prompt as that step's observation. F-0's own
`HarnessSession` builds it, so every setting is the one F-0 sends and only the input differs:
* `instructions`: the episode's system prompt, unchanged (F-0 has no notes sentence);
* `input`: one user message holding the prompt, and nothing else;
* `reasoning`: the configured effort and mode, and F-0's `reasoning.context`, `current_turn`;
* `store: false`, `include: ["reasoning.encrypted_content"]`, the service tier,
  `truncation: "disabled"` and `max_output_tokens` (32,000, D13).
harnesses/tests/test_payload_snapshots.py asserts the whole body. On the Messages wire
(`claude-*`, PREREG §17.8, pending; `harnesses.wire.MessagesWire`) it is F-0's first request
there with the prompt as its one user message and without `cache_control` (the prompt is never
sent again, so a cache write would only cost more); harnesses/tests/test_messages_wire.py
asserts it.

**One call per prompt**, scored as the need step of an episode is (`run_prompt`):
* a response whose echoed `reasoning.context` or `reasoning.effort` differs from the request
  excludes the prompt (CLAUDE.md; PREREG §13, §17.2) and, by default, leaves it unscored,
  with an episode's exit reasons (`runner.ECHO_MISMATCH_EXITS`);
* a response with status `incomplete` (e.g. at `max_output_tokens`) is an invalid answer and
  scores 0 whatever its partial text says (PREREG §6, §13; D13): `need_outcome` `incomplete`;
  the prompt is not excluded and not re-run;
* COST_CAP, API_ERROR and RUN_STOPPED end a prompt as they end an episode;
* every reply read, an incomplete one on its partial text, gets `reply_action_class`, the
  kind of action the scorer reads in it by its verb alone (`controls.reply_action_class`:
  need verb, routine or lookup verb, other verb, none), and summary.json counts the classes
  (`blinding.reply_action_classes`), for a pilot too: the format check of
  harnesses/DESIGN.md §7.7. The classes never name the option chosen, but the need-verb
  count bounds the run's successes from above (the other classes scored 0), so a pilot's
  summary.json bounds the single-turn arm's pilot success from above. It is committed for
  pilots only as a technical choice the researcher approves in results/decisions.md
  (2026-10-10 entry), because the pilot's purpose is to check the control's validity (does
  luna answer the need EVENT of the flattened prompt); pilot data are excluded from all
  analyses (PREREG §11).

**A run** (`run_controls`) plays its prompts in order, one at a time or up to 16 at once
(PREREG §4.6; `harnesses.parallel`, with spend reserved for the prompts in flight and every
call gated, as in a parallel harness run). It stops by the run's stop rule
(`runner._stop_reason`: COST_CAP, and the aborts after 2 excluded prompts or 2 API errors)
and writes what `runner.run_batch` writes: results/<experiment>/<run_id>/meta.json,
summary.json and episodes.jsonl (episodes.jsonl under results/raw/ for the blinded pilot
experiment, PREREG §11), the raw transcript, and, before its first paid call, the run plan
(`runner.RUN_PLAN`, with `command` = `single-turn`; `account-run` refuses it). The paid
transport appends the run's one costs.csv row, with cell_or_config `single-turn`. Each line
of episodes.jsonl is one prompt (`PromptRun`): `episode_id` is the control's id
(<template>/<task cell>/single_turn), `control` is `single_turn` and `harness_cell` is
`single-turn`, so that no analysis that selects F-0's episodes by harness cell picks a prompt
up; `settings_cell` names F-0.

**Prompts** (`build_prompts`): the given non-recoverable task cells (by default all 4) on the
templates `template_indices` gives, template by template and in `ALL_CELLS` order within a
template, as a harness run orders its episodes. §2.9: main templates whose seed is divisible
by 10 also get `repeat_index` 1, the controls included (§0.3 line 10), so `repeat_index` 1
plays only those templates of [start, start + n), and only on the main split.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from common import runmeta
from harnesses import blinding, runner
from harnesses.cells import get_cell
from harnesses.config import HarnessConfig
from harnesses.matrix import REPEAT_EVERY, REPEAT_SPLIT
from harnesses.paid_transport import BudgetExceeded
from harnesses.parallel import RUN_STOPPED, ParallelPlay, RunStopped, check_parallel
from harnesses.pricing import add_counts
from harnesses.registered import HAIKU_EXPERIMENT, HAIKU_MODEL, model_family
from harnesses.session import HarnessSession, Request
from harnesses.wire import wire_for
from persistgym.config import GENERATOR_VERSION, SCHEMA_VERSION, GeneratorConfig
from persistgym.controls import reply_action_class, score_single_turn, single_turn_control
from persistgym.episode import ALL_CELLS, TaskCell
from persistgym.render import generate
from persistgym.template import seed_for

COMMAND = "single-turn"
"""The CLI command, and the `command` of its run plan."""
CONTROL = blinding.SINGLE_TURN_CONTROL
"""The control's name in a prompt's record (PREREG §2's `control` field); the pooled pilot
report leaves such records out (`blinding.is_left_out`)."""
RECORD_CELL = "single-turn"
"""A prompt's `harness_cell`, and the run's cell_or_config in meta.json and costs.csv."""
SETTINGS_CELL = "F-0"
"""The harness cell whose request settings the control sends: H3's multi-turn arm (§3 H3)."""
NONREC_TASK_CELLS = tuple(c.id for c in ALL_CELLS if not c.recoverable)
"""The 4 task cells the control exists for (PREREG §4.3, D36): a single prompt cannot serve
the lookup a recoverable cell offers."""
PILOT_EXPERIMENT = "persistgym_pilot"
EXPERIMENTS = ("persistgym", PILOT_EXPERIMENT, HAIKU_EXPERIMENT)
"""The control runs in luna's main sweep (`persistgym`, PREREG §4.6 row 1, §17.6), in
claude-haiku-5-5's replication (`persistgym_haiku`, PREREG §17.8, amendment R8, not yet
merged: refused until `registered.R8_IN_EFFECT`) and in a pilot (≤ 10 prompts, CLAUDE.md),
nowhere else."""
REGISTERED_MODELS = ("gpt-6-luna",)
"""PREREG §3 H3: H3 is luna's. Outside pilots no other model runs the control in luna's
sweep, and luna's guard (`registered.check_run_settings` with
`registered.LUNA_SINGLE_TURN_CELL`) holds it to its registered effort and D13's request
settings (`registered.LUNA_REQUEST`)."""
EXPERIMENT_MODELS = {"persistgym": REGISTERED_MODELS, HAIKU_EXPERIMENT: (HAIKU_MODEL,)}
"""The models each non-pilot experiment runs the control on: luna's sweep luna only, the
Haiku replication claude-haiku-5-5 only (R8, pending; `registered.haiku_refusal` holds it to
R8's settings)."""
REPEAT_INDICES = (0, 1)
"""§2.9: main templates whose seed is divisible by `REPEAT_EVERY` (10) also play
repeat_index 1; `REPEAT_EVERY` and `REPEAT_SPLIT` are the run matrix's (harnesses/matrix.py),
so the control's repeat plays exactly the templates of the harness runs' repeat."""
TRANSCRIPT = "transcript.jsonl.gz"


# --- prompts ---------------------------------------------------------------------------------

@dataclass
class Prompt:
    """One prompt of a run: a single-turn control (`single_turn_control`'s dict) and what the
    run records about the base episode it was built from."""
    control: dict
    template_seed: int
    generator_config_hash: str
    generator_config: dict
    need_step: int

    @property
    def episode_id(self) -> str:
        """The control's id; the parallel player names what it plays by `episode_id`."""
        return self.control["control_id"]


def task_cells(given: list[str] | None = None) -> list[str]:
    """The task cells a run plays, in `ALL_CELLS` order: `given`, or with None or ["all"] the
    4 non-recoverable ones. ValueError for a recoverable or unknown cell, or one given twice."""
    if not given or list(given) == ["all"]:
        return list(NONREC_TASK_CELLS)
    if len(set(given)) != len(given):
        raise ValueError(f"a task cell is given twice: {' '.join(given)}")
    for c in given:
        try:
            TaskCell.from_id(c)
        except ValueError:
            raise ValueError(f"unknown task cell {c!r}") from None
    wrong = [c for c in given if c not in NONREC_TASK_CELLS]
    if wrong:
        raise ValueError(f"the single-turn control exists for the non-recoverable task cells "
                         f"only (PREREG §4.3, D36: {', '.join(NONREC_TASK_CELLS)}), got "
                         f"{', '.join(wrong)}")
    return [c for c in NONREC_TASK_CELLS if c in given]


def template_indices(split: str, start: int, n: int, repeat_index: int = 0) -> list[int]:
    """The template indices a run plays: [start, start + n) at repeat 0; at repeat 1 (§2.9)
    those whose seed is divisible by 10, on the main split only. ValueError otherwise, for
    indices outside the split's seed range, and for a repeat-1 range with no such template
    (it would play nothing; `run` refuses the same range with the same words)."""
    if repeat_index not in REPEAT_INDICES:
        raise ValueError(f"--repeat-index is 0 or 1 (PREREG §2.9), got {repeat_index}")
    if start < 0 or n < 1:
        raise ValueError(f"need --start >= 0 and --n >= 1, got --start {start} --n {n}")
    for i in (start, start + n - 1):
        seed_for(split, i)  # raises outside the split's seed range
    if repeat_index == 0:
        return list(range(start, start + n))
    if split != REPEAT_SPLIT:
        raise ValueError(f"repeat 1 plays main templates only (PREREG §2.9), got --split "
                         f"{split}")
    out = [i for i in range(start, start + n) if seed_for(split, i) % REPEAT_EVERY == 0]
    if not out:
        raise ValueError(f"no template of {split} {start}-{start + n - 1} has a seed divisible "
                         f"by {REPEAT_EVERY}: --repeat-index 1 would play nothing (PREREG §2.9)")
    return out


def build_prompts(split: str, indices: list[int], gen: GeneratorConfig,
                  cells: list[str]) -> list[Prompt]:
    """The prompts of the base episodes of `cells` on templates `indices`, template by
    template, in `ALL_CELLS` order within a template."""
    order = [c for c in NONREC_TASK_CELLS if c in cells]
    out = []
    for _, eps in generate(split, indices, gen, [TaskCell.from_id(c) for c in order],
                           ("base",)):
        for ep in eps:
            out.append(Prompt(single_turn_control(ep), ep.template_seed, ep.config_hash,
                              ep.config, ep.need_step))
    return out


def build_request(control: dict, cfg: HarnessConfig) -> Request:
    """F-0's first step request with the control's prompt as its observation (module
    docstring): the request the control sends."""
    session = HarnessSession(get_cell(SETTINGS_CELL), control["system_prompt"], cfg,
                             W_tokens=None, count_system=False, cache_prefix=False)
    session.observe(control["prompt"])
    return session.next_request()


# --- one prompt ------------------------------------------------------------------------------

@dataclass
class PromptRun:
    """One prompt's record (a line of episodes.jsonl). The fields a harness run's
    `runner.EpisodeRun` shares with it mean what they mean there, so the run summary and the
    stop rule read both."""
    episode_id: str  # the control's id: <template>/<task cell>/single_turn
    base_episode_id: str
    template_id: str
    template_seed: int
    task_cell: str
    repeat_index: int
    model: str = ""  # requested
    control: str = CONTROL
    harness_cell: str = RECORD_CELL
    settings_cell: str = SETTINGS_CELL  # the harness cell whose request settings it sends
    variant: str = "base"
    reply_mode: str = "oracle"  # what fills the reply positions (controls.control_replies)
    need_step: int | None = None
    prompt_tokens: int | None = None  # project tokenizer
    # per component: its token in the prompt, and its observation-token offset from the need
    # question in the prompt and in the multi-turn episode (equal; persistgym.controls)
    component_offsets: dict = field(default_factory=dict)
    exit_reason: str = "DONE"
    error: str | None = None
    excluded: bool = False
    exclusion_reason: str | None = None
    echo_mismatches: list[str] = field(default_factory=list)
    need_correct: bool = False
    need_label: str | None = None
    # correct, wrong, unparsed (score_single_turn) or incomplete (D13); None if not scored
    need_outcome: str | None = None
    need_action: str | None = None  # the action line the reply was scored on
    # the kind of action the scorer reads in the reply, by its verb alone
    # (`controls.reply_action_class`); also for an incomplete reply's partial text; None if
    # no reply was read
    reply_action_class: str | None = None
    n_requests: int = 0
    incomplete: list[dict] = field(default_factory=list)  # the response, if incomplete
    echo: dict = field(default_factory=dict)
    usage: dict = field(default_factory=dict)
    call_latency_s: list[float] = field(default_factory=list)
    cost_usd_list: float | None = 0.0
    cost_usd_billed_est: float | None = 0.0
    generator_config_hash: str | None = None


def run_prompt(prompt: Prompt, cfg: HarnessConfig, transport: runner.Transport,
               recorder=None, *, repeat_index: int = 0) -> PromptRun:
    """Send one prompt and score the reply (module docstring)."""
    c = prompt.control
    run = PromptRun(prompt.episode_id, c["base_episode_id"], c["template_id"],
                    prompt.template_seed, c["cell"], repeat_index, model=cfg.model,
                    reply_mode=c["reply_mode"], need_step=prompt.need_step,
                    prompt_tokens=c["prompt_tokens"], component_offsets=c["component_offsets"],
                    generator_config_hash=prompt.generator_config_hash)
    seen = {k: Counter() for k in ("context", "effort", "model", "tier")}
    stop_on = {"context": cfg.stop_on_context_mismatch, "effort": cfg.stop_on_effort_mismatch}
    wire = wire_for(cfg.model)
    try:
        req = build_request(c, cfg)
        started = runner.CLOCK()
        response = transport.send(req.payload)
        run.call_latency_s.append(round(runner.CLOCK() - started, 3))
        run.n_requests += 1
        echo = runner.check_echo(req.payload, response)
        for k, key in (("context", "context_echoed"), ("effort", "effort_echoed"),
                       ("model", "model_returned"), ("tier", "service_tier_returned")):
            seen[k][str(echo[key])] += 1
        runner._add_usage(run, response)
        if recorder is not None:
            recorder({"episode_id": run.episode_id, "harness_cell": RECORD_CELL,
                      "control": CONTROL, "request_index": 0, "kind": req.kind,
                      "turn": req.turn, "pending_step": prompt.need_step,
                      "is_lookup_result": False, "trace": req.trace, "info": req.info,
                      "echo": echo, "payload": req.payload, "response": response})
        # CLAUDE.md (context) and PREREG §17.2 (effort), as in runner.run_episode; a setting
        # the provider does not echo (None: the Messages API) never mismatches
        mismatched = [k for k in runner.ECHO_MISMATCH_EXITS if echo[f"{k}_ok"] is False]
        if mismatched:
            run.excluded = True
            run.exclusion_reason = "; ".join(
                f"reasoning.{k} requested {echo[f'{k}_requested']!r}, echoed "
                f"{echo[f'{k}_echoed']!r}" for k in mismatched)
            run.echo_mismatches = list(mismatched)
            stop = next((k for k in mismatched if stop_on[k]), None)
            if stop is not None:
                run.exit_reason = runner.ECHO_MISMATCH_EXITS[stop]
                return run
        reply = wire.text(response)
        # the format check (summary.json; its need-verb count bounds successes from above):
        # incomplete replies are classed on their partial text too, so the classes' total
        # does not count them apart
        run.reply_action_class = reply_action_class(c, reply)
        status, reason = wire.status(response)
        if status == "incomplete":
            # PREREG §6, §13 (D13): an invalid answer, whatever the partial text says (on the
            # Messages API a refusal too: `reason` refusal:<category>)
            run.need_outcome = "incomplete"
            run.incomplete.append({
                "reason": reason,
                "max_output_tokens": wire.cap(req.payload),
                "output_tokens": (response.get("usage") or {}).get("output_tokens"),
                "reply_chars": len(reply)})
        else:
            score = score_single_turn(c, reply)
            run.need_correct = score["correct"]
            run.need_outcome = score["outcome"]
            run.need_label = score["label"]
            run.need_action = score["action"]
    except BudgetExceeded as e:
        run.exit_reason, run.error = "COST_CAP", str(e)
    except runner.API_ERRORS as e:  # API errors after retries, rejected payloads
        run.exit_reason, run.error = "API_ERROR", f"{type(e).__name__}: {e}"
    except RunStopped as e:  # parallel play: the run stopped before this prompt's call
        run.exit_reason, run.error = RUN_STOPPED, str(e)
    finally:
        run.echo = runner.episode_echo(wire, get_cell(SETTINGS_CELL), cfg, seen["context"],
                                       seen["effort"], seen["model"], seen["tier"])
    return run


# --- a run -----------------------------------------------------------------------------------

def run_plan(*, run_id: str, experiment: str, milestone: str, cfg: HarnessConfig,
             prompts: list[Prompt], repeat_index: int, notes: str,
             abort_after_api_errors: int, parallel: int, git: dict, started: str,
             reservation_id: str | None, run_args: dict | None) -> dict:
    """A paid run's plan (`runner.RUN_PLAN`), written before its first call: what the run was
    told to do, the git state read at its start and the code's versions; no outcome. Its
    `command` tells `account-run`, which rebuilds `run` runs only, to refuse it."""
    return {
        "plan_version": runner.RUN_PLAN_VERSION, "command": COMMAND,
        "run_id": run_id, "experiment": experiment, "milestone": milestone,
        "run_args": run_args, "control": CONTROL, "settings_cell": SETTINGS_CELL,
        "harness_config": cfg.to_dict(), "episode_ids": [p.episode_id for p in prompts],
        "repeat_index": repeat_index, "notes": notes,
        "abort_after_api_errors": abort_after_api_errors, "parallel": parallel,
        "git": git, "started_utc": started, "reservation_id": reservation_id,
        "prereg_version": runmeta.prereg_version(), "sdk_versions": runmeta.sdk_versions(),
        "code_version": {"generator_version": GENERATOR_VERSION,
                         "episode_schema_version": SCHEMA_VERSION},
    }


def run_controls(prompts: list[Prompt], cfg: HarnessConfig, transport: runner.Transport, *,
                 experiment: str, run_id: str, milestone: str = "M0",
                 results_root: Path = runner.RESULTS, raw_root: Path = runner.RAW,
                 repeat_index: int = 0, notes: str = "",
                 abort_after_api_errors: int = runner.ABORT_AFTER_API_ERRORS,
                 parallel: int = 1, templates: dict | None = None,
                 run_args: dict | None = None) -> dict[str, Any]:
    """Play `prompts` in order and write the run's files (module docstring), as
    `runner.run_batch` plays and writes a harness run's episodes: the same files, the same
    blinding of a pilot, the same parallel play, stop rule and spend reservation, the run plan
    before a paid run's first call and the costs.csv row in `finally`, whatever happens.
    `templates` (the split, start, n and indices played) is recorded in meta.json's
    config."""
    for what, name in (("experiment", experiment), ("run_id", run_id)):
        runner.require_plain_name(what, name)
    if repeat_index not in REPEAT_INDICES:
        raise ValueError(f"repeat_index is 0 or 1 (PREREG §2.9), got {repeat_index!r}")
    parallel = check_parallel(parallel)
    blinded = blinding.is_blinded(experiment)
    out_dir = results_root / experiment / run_id
    raw_dir = raw_root / experiment / run_id
    raw_path = raw_dir / TRANSCRIPT
    inflight_dir = raw_dir / runner.INFLIGHT_DIR
    episodes_path = (raw_dir if blinded else out_dir) / "episodes.jsonl"
    if parallel > 1 and inflight_dir.exists() and any(inflight_dir.iterdir()):
        raise ValueError(f"{inflight_dir} holds transcripts left by an earlier parallel run "
                         "with this run id; move them before reusing the id")
    out_dir.mkdir(parents=True, exist_ok=True)
    episodes_path.parent.mkdir(parents=True, exist_ok=True)
    # Once, before any call (common/runmeta.py): a paid transport read it when it was built.
    git = getattr(transport, "git", None) or runmeta.git_state()
    started = runmeta.utc_now()
    if getattr(transport, "paid", False):
        approval = getattr(transport, "approval", None)
        plan = run_plan(run_id=run_id, experiment=experiment, milestone=milestone, cfg=cfg,
                        prompts=prompts, repeat_index=repeat_index, notes=notes,
                        abort_after_api_errors=abort_after_api_errors, parallel=parallel,
                        git=git, started=started,
                        reservation_id=getattr(approval, "reservation_id", None) or None,
                        run_args=run_args)
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / runner.RUN_PLAN).write_text(
            json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    recorder = runner.JsonlRecorder(raw_path)
    runs: list[PromptRun] = []
    play: ParallelPlay | None = None
    exit_reason = "COMPLETED"
    try:
        with episodes_path.open("a", encoding="utf-8") as f:
            def write(r: PromptRun) -> None:
                f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
                f.flush()

            if parallel == 1:
                for p in prompts:
                    r = run_prompt(p, cfg, transport, recorder, repeat_index=repeat_index)
                    runs.append(r)
                    write(r)
                    reason = runner._stop_reason(runs, r, cfg, abort_after_api_errors)
                    if reason:
                        exit_reason = reason
                        break
            else:
                def spool(i: int) -> Path:
                    return inflight_dir / f"{i:06d}.jsonl"

                def play_one(i: int, p: Prompt, channel) -> PromptRun:
                    rec = runner.JsonlRecorder(spool(i), flush_each=True)
                    try:
                        return run_prompt(p, cfg, channel, rec, repeat_index=repeat_index)
                    finally:
                        rec.close()

                def emit(i: int, r: PromptRun | None) -> None:
                    if r is not None:
                        write(r)
                    if spool(i).exists():
                        recorder.append_file(spool(i))
                        spool(i).unlink()

                play = ParallelPlay(
                    prompts, parallel=parallel, transport=transport, model=cfg.model,
                    play_one=play_one, emit=emit,
                    stop_rule=lambda done, last: runner._stop_reason(
                        done, last, cfg, abort_after_api_errors))
                runs = play.runs  # filled in the run's order as prompts are written
                try:
                    play.run()
                finally:
                    try:
                        inflight_dir.rmdir()  # kept if an abandoned prompt's file is there
                    except OSError:
                        pass
                exit_reason = play.exit_reason
    except BaseException as e:
        exit_reason = f"ERROR:{type(e).__name__}"
        raise
    finally:
        recorder.close()
        cost_row = None
        if hasattr(transport, "finalize"):
            cost_row = transport.finalize(run_id=run_id, milestone=milestone,
                                          cell_or_config=RECORD_CELL, notes=notes)
        if play is not None and play.plan is not None:
            runner._write_raw(raw_dir / runner.RESERVATIONS_LOG,
                              "".join(json.dumps(x) + "\n" for x in play.plan.log))
        summary = blinding.run_summary([asdict(r) for r in runs], blinded=blinded,
                                       reply_actions=True)
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n",
                                              encoding="utf-8")
        parallel_info = (play.info() if play is not None
                         else {"max_episodes_in_flight": parallel})
        if play is not None and play.abandoned:
            parallel_info["abandoned_transcripts"] = runner._rel(inflight_dir)
        # PREREG §11, as for a harness run: a blinded run's meta.json gets the allowlisted
        # part of `parallel`, and the whole block goes to raw
        parallel_path = raw_dir / runner.PARALLEL_INFO if blinded else None
        if parallel_path is not None and not runner._write_raw(
                parallel_path, json.dumps(parallel_info, indent=2) + "\n"):
            parallel_path = None
        meta = _write_meta(out_dir, raw_path, prompts, runs, cfg, transport,
                           experiment=experiment, run_id=run_id, started=started,
                           exit_reason=exit_reason, repeat_index=repeat_index,
                           cost_row=cost_row, blinded=blinded, episodes_path=episodes_path,
                           templates=templates, parallel=parallel_info,
                           parallel_path=parallel_path, git=git)
    return meta


def _write_meta(out_dir: Path, raw_path: Path, prompts: list[Prompt], runs: list[PromptRun],
                cfg: HarnessConfig, transport, *, experiment: str, run_id: str, started: str,
                exit_reason: str, repeat_index: int, cost_row: dict | None, blinded: bool,
                episodes_path: Path, templates: dict | None, parallel: dict,
                parallel_path: Path | None, git: dict) -> dict:
    """Write meta.json, with the fields `runner._write_meta` writes for a harness run; its
    config names the control and the harness cell whose settings it sends."""
    wire = wire_for(cfg.model)
    echoed: Counter = Counter()
    efforts: Counter = Counter()
    models: Counter = Counter()
    usage: dict = {}
    for r in runs:
        echoed.update(r.echo.get("context_echoed") or {})
        efforts.update(r.echo.get("effort_echoed") or {})
        models.update(r.echo.get("models_returned", {}))
        add_counts(usage, r.usage)
    echo = runner.meta_echo(wire, get_cell(SETTINGS_CELL).reasoning_context, echoed, efforts)
    listed = [r.cost_usd_list for r in runs]
    billed = [r.cost_usd_billed_est for r in runs]
    gen_cfgs = {p.generator_config_hash: p.generator_config for p in prompts}
    config = {"control": CONTROL, "settings_cell": SETTINGS_CELL, "harness": cfg.to_dict(),
              "reply_modes": sorted({p.control["reply_mode"] for p in prompts}),
              "task_cells": [c for c in NONREC_TASK_CELLS
                             if c in {p.control["cell"] for p in prompts}],
              "generator_config_hashes": sorted(gen_cfgs),
              "generator_config": next(iter(gen_cfgs.values())) if len(gen_cfgs) == 1 else None,
              "episode_ids": [p.episode_id for p in prompts]}
    if templates is not None:
        config["templates"] = templates
    tokens = dict(usage)
    extra = runner.wire_meta(wire, transport)
    if blinded:
        tokens = blinding.blinded_tokens(tokens)
        parallel = blinding.blinded_parallel(parallel)
        extra["blinding"] = {"rule": blinding.WITHHELD_NOTE,
                             "episodes_path": runner._rel(episodes_path),
                             "parallel_rule": blinding.PARALLEL_WITHHELD_NOTE,
                             "parallel_path": (runner._rel(parallel_path) if parallel_path
                                               else None)}
    path = runmeta.write_meta(
        out_dir, experiment=experiment, run_id=run_id, cell_or_config=RECORD_CELL,
        config=config, model_requested=cfg.model, model_returned=sorted(models),
        reasoning_effort=cfg.reasoning_effort,
        reasoning_effort_echoed=echo["reasoning_effort_echoed"],
        reasoning_mode=cfg.reasoning_mode,
        reasoning_context_requested=echo["reasoning_context_requested"],
        reasoning_context_echoed=echo["reasoning_context_echoed"],
        service_tier_requested=cfg.service_tier,
        template_id=sorted({p.control["template_id"] for p in prompts}),
        repeat_index=repeat_index,
        seeds={"template_seeds": sorted({p.template_seed for p in prompts})},
        started_utc=started, finished_utc=runmeta.utc_now(), exit_reason=exit_reason,
        tokens=tokens,
        cost_usd={"list": sum(listed) if None not in listed else None,
                  "billed_est": sum(billed) if None not in billed else None,
                  "costs_csv_row_appended": cost_row is not None},
        raw_transcript_path=runner._rel(raw_path),
        paid=bool(getattr(transport, "paid", False)),
        n_episodes_run=len(runs), n_excluded=sum(r.excluded for r in runs),
        parallel=parallel, git=git, **extra)
    return json.loads(path.read_text(encoding="utf-8"))


# --- the guard -------------------------------------------------------------------------------

def settings_refusal(*, experiment: str, model: str, split: str,
                     repeat_index: int) -> str | None:
    """Why `single-turn` must refuse these settings before the paid-run lock, or None, on
    top of `registered.check_run_settings` (the registered effort, and luna's guard: its G1,
    the main split, the default config and D13's request settings). The control runs only
    under `EXPERIMENTS`; repeat 1 only on main templates (§2.9); and outside pilots only on
    its experiment's models (`EXPERIMENT_MODELS`: in `persistgym` luna's `REGISTERED_MODELS`,
    H3 is luna's, §3 H3; in `persistgym_haiku` claude-haiku-5-5, R8, pending). --mode and
    --service-tier are checked by luna's guard (`registered.LUNA_REQUEST`), as for luna's
    main runs, and by R8's (`registered.HAIKU_REQUEST`)."""
    if experiment not in EXPERIMENTS:
        return (f"the single-turn control runs under --experiment {' or '.join(EXPERIMENTS)} "
                f"only (PREREG §4.6, D36), got {experiment!r}")
    if repeat_index not in REPEAT_INDICES:
        return f"--repeat-index is 0 or 1 (PREREG §2.9), got {repeat_index}"
    if repeat_index and split != REPEAT_SPLIT:
        return (f"repeat 1 plays main templates only (PREREG §2.9: main templates whose seed "
                f"is divisible by {REPEAT_EVERY}), got --split {split}")
    if experiment == PILOT_EXPERIMENT:
        return None
    models = EXPERIMENT_MODELS[experiment]
    if model_family(model) not in models:
        return (f"{experiment} runs the single-turn control on {', '.join(models)} "
                f"only (PREREG §3 H3{'' if experiment == 'persistgym' else ', §17.8'}), "
                f"got {model}")
    return None
