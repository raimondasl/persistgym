"""Command line for the harness cells.

$0 commands (fake model or local files, no network):
    uv run python -m harnesses cells
    uv run python -m harnesses dry-run --cell W-n-0 --task-cell observed-nonrec-far
    uv run python -m harnesses pilot-report      # pooled pilot report (PREREG §11)
    uv run python -m harnesses probe-summary <run_id>       # replay-probe counts per arm
    uv run python -m harnesses echo-count        # context and effort echoes of raw runs
    # a paid run whose costs.csv row could not be written (its lock is kept, naming it):
    # rebuild the row, summary.json and meta.json from its raw files, then release the lock
    # and its spend reservation; --check verifies and prints the plan, writing nothing
    uv run python -m harnesses account-run <run_id> --check
    # PREREG §17.3 (amendment R3): score sol's engagement check on its derived-fact variant
    # from its two pilot runs, with R2's two check runs (default config) as the descriptive
    # reference
    uv run python -m harnesses reasoning-check <F-r run_id> <F-0 run_id> \
        --reference 20261002T173710Z-F-r-gpt-6.1-sol 20261002T180358Z-F-0-gpt-6.1-sol

Request settings. `run` and `dry-run` send the model's registered reasoning effort unless
--effort says otherwise (harnesses/registered.py; PREREG §6 as amended by R2, §17.2): medium
on gpt-6-luna, high on gpt-6.1-sol (and on a dated snapshot or alias of each). They play the
generator config of --gen-preset (persistgym/config.py PRESETS; "default" unless given) with
each --gen-set FIELD=JSON applied. Before the paid-run lock, `run` refuses
(`registered.check_run_settings`; PREREG §17.3, amendment R3):
* outside persistgym_pilot, any effort but the model's registered one;
* outside persistgym_pilot, a gpt-6.1-sol run off the generator preset sol-chain (exactly: a
  --gen-set changes its config hash) or in a harness cell other than F-r and F-0;
* in persistgym_validity, a gpt-6.1-sol run other than its validity run: F-0 on --split
  validity, --variant restated or withheld (`registered.VALIDITY_RUN`; it needs no G1);
* outside persistgym_pilot, a gpt-6.1-sol run unless the reasoning_check.json files on
  sol-chain's config under results/persistgym_pilot/ say ENGAGED in R2's order and none says
  NOT_ENGAGED (`registered.engagement_refusal`; a check file decides only for the config its
  runs played, so R2's NOT_ENGAGED file binds the default config only), and outside
  persistgym_validity unless `registered.G1_PASSED` records G1 on sol-chain;
* a gpt-6.1-sol pilot at effort high (R3's engagement check) off sol-chain or in a harness
  cell other than F-r and F-0, and any gpt-6.1-sol pilot above medium effort after R3's hard
  stop (a NOT_ENGAGED check on sol-chain, or an UNSCORABLE one twice).
PREREG §17.4 (amendment R4), sol's replication of H1, is judged apart from the rules above
(`registered.replication_refusal`; the engagement checks and R3's hard stop concern H2 and
are not read). `run` refuses:
* in persistgym_sol_h1 (its main runs), anything but gpt-6.1-sol at --effort medium on the
  default generator config, in F-0, W-0 or W-n-0, on --split main, --variant base, on the 4
  observed task cells only, with --mode standard, --service-tier flex and no --W (D13), and
  every such run until `registered.REPLICATION_G1_PASSED` records the replication's G1 on the
  default config;
* in persistgym_validity, a gpt-6.1-sol run at --effort medium on the default config other
  than the replication's validity run: F-0 on --split validity, --variant restated or
  withheld, validity templates 0-19, on the 4 observed task cells only, with D13's request
  settings as above (it needs no G1).
PREREG §4.6 and §17.6 (amendment R6), gpt-6-luna's main sweep (`registered.luna_refusal`):
outside persistgym_pilot, `run` refuses a gpt-6-luna run in persistgym_validity (luna's
validity runs are finished: G1 is recorded on them, and R6 allows no other paid runs) and
any other run than experiment persistgym, in F-0, W-0, W-n-0 or Σ-n-0 (sigma-n-0), on
--split main, main templates 0-199 (--start + --n at most T = `registered.LUNA_T` = 200:
§4.2's rule, capped by R6 change 6), --variant base (or restated in F-0: the
restated-at-need control), on the default generator config, with --mode standard,
--service-tier flex and no --W (D13, `registered.LUNA_REQUEST`), and any such run until
`registered.G1_PASSED` records luna's G1 on that config (recorded: the researcher's G1 GO of
2026-10-09).
R3's engagement check found NOT_ENGAGED on 2026-10-03 (results/decisions.md), so R3's hard
stop refuses its check, validity and main-sweep commands below; they are kept as the record
of what was registered.
The probes keep their registered settings (medium on both models; PREREG §17.1).

Repeats (PREREG §2.9; §0.3 line 10): `run --repeat-index 1` plays, of the run's matrix, only
the main templates whose seed is divisible by 10, in the same task cells, --variant and
harness cell (`RunMatrix.repeat`): the same episodes as the repeat-0 run, played again. Its
run id ends -repeat1, and its run plan, meta.json, episode records and costs-row notes say
repeat_index 1; a repeat-0 run writes what it wrote before the option existed.

Paid commands refuse unless PERSISTGYM_ALLOW_PAID=1, no other PersistGym paid run holds the
PersistGym stream's paid-run lock (an ARC run, with its own lock, may go beside it; PREREG
§0.3 line 15), the experiment is a PersistGym one, this checkout's results/costs.csv holds
the row of each stream's last paid run, no hold stands (a paid run that ended COST_CAP or
passed its run guard, until the researcher merges "cleared_hold: <run_id>" into
results/decisions.md; common/hold.py), --approved-block and --planned-usd are given,
PREREG.md is committed, merged to origin/main and frozen, and results/decisions.md holds the
researcher's line
"approved_block: <name> | experiments: <exp1>,<exp2>,... | max_usd: <amount>" on origin/main,
in HEAD and in the working tree, listing the experiment, with room under max_usd and the
phase cap, counting the planned spend a running ARC run has reserved (common/approval.py).
The lock (common/paidlock.py, in the git common directory) is taken before those checks and
held until the command ends; a run whose costs.csv row could not be written leaves it held,
with the reason, until `account-run` (harnesses/account.py) accounts for it. A paid run reads
its git state once, before its first call, and `run` writes its plan,
results/raw/<experiment>/<run_id>/run_plan.json, before its first call too; a run without
one (started before account-run existed) is accounted for with its `run` arguments and git
state given again (--git-dirty true if any tracked file differed from the commit when it
started, results/costs.csv with an earlier run's uncommitted row included):
    uv run python -m harnesses account-run <run_id> --cell F-0 --model gpt-6.1-sol \
        --effort high --split pilot --start 0 --n 2 --task-cell observed-nonrec-far \
        observed-rec-far derived-nonrec-far derived-rec-far --experiment persistgym_pilot \
        --approved-block "1-pilots" --planned-usd 6 --git-commit <commit> --git-dirty true
Launch every paid run as a process of its own, with its own console (not from a shell that a
time limit can stop): a process that has lost its console cannot start git or any other
console program. The OpenAI SDK reads the key from the environment:
    PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses probe-echo \
        --approved-block "1-pilots" --planned-usd 0.5
    # D29 as amended by R1 (PREREG §17.1): sol and luna, 20 scorable trials per arm
    PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses probe-replay \
        --design fork --approved-block "1-pilots" --planned-usd 1
    PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses run --cell F-0 \
        --model gpt-6-luna --n 1 --approved-block "1-pilots" --planned-usd 1
    # PREREG §17.3 (amendment R3): the engagement check's two runs, this one and the same
    # with --cell F-0: sol at high effort on its derived-fact variant (sol-chain), on the 4
    # D11 far task cells of pilot templates 0 and 1 (the episode ids of R2's check)
    PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses run --cell F-r \
        --model gpt-6.1-sol --effort high --gen-preset sol-chain --split pilot --start 0 \
        --n 2 --task-cell observed-nonrec-far observed-rec-far derived-nonrec-far \
        derived-rec-far --experiment persistgym_pilot --approved-block "1-pilots" \
        --planned-usd 6
    # R3, only after an ENGAGED check: sol's validity run (§4.4) on sol-chain, F-0 on
    # validity templates 0-19 x the 8 task cells, restated (then the same with withheld)
    PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses run --cell F-0 \
        --model gpt-6.1-sol --gen-preset sol-chain --split validity --start 0 --n 20 \
        --variant restated --experiment persistgym_validity --approved-block "1-pilots" \
        --planned-usd <usd>
    # D11 as amended by R2 and R3: sol on derived-far x T_d = 210 templates plus observed-far
    # x T_o = 70 of them, at sol's registered effort (high) on sol-chain, only after an
    # ENGAGED check and G1 (registered.G1_PASSED); PREREG §4.6: up to 16 episodes at once,
    # with the same payloads and outputs and spend reserved for the episodes in flight
    # (harnesses/parallel.py)
    PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses run --cell F-r \
        --model gpt-6.1-sol --gen-preset sol-chain --split main --matrix d11 --n 210 \
        --experiment persistgym --approved-block "<block>" --planned-usd <usd> --parallel 16
    # PREREG §17.4 (amendment R4): sol's H1 replication, at --effort medium (give it: sol's
    # registered effort is high) on the default config, on the 4 observed task cells.
    # 1. Its pilot (W-0 and W-n-0 are new on sol): this run, then the same with
    #    --cell W-n-0; pilot templates 0 and 1, 8 episodes each; `pilot-report` leaves both
    #    runs out (blinding.is_left_out), so read them from their costs rows and summary.json
    PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses run --cell W-0 \
        --model gpt-6.1-sol --effort medium --split pilot --start 0 --n 2 \
        --task-cell observed-nonrec-near observed-nonrec-far observed-rec-near \
        observed-rec-far --experiment persistgym_pilot --approved-block "1-pilots" \
        --planned-usd <usd>
    # 2. Its validity run (the replication's G1): F-0 on validity templates 0-19 x the 4
    #    observed task cells, restated, then the same with --variant withheld
    PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses run --cell F-0 \
        --model gpt-6.1-sol --effort medium --split validity --start 0 --n 20 \
        --task-cell observed-nonrec-near observed-nonrec-far observed-rec-near \
        observed-rec-far --variant restated --experiment persistgym_validity \
        --approved-block "1-pilots" --planned-usd <usd>
    # 3. Its main runs, only once registered.REPLICATION_G1_PASSED records its G1: this run,
    #    then the same with --cell W-0 and --cell W-n-0; T templates from 0 (--n; T is
    #    luna's main-sweep count, set at M1; 100 shown) x the 4 observed task cells; then
    #    each again with --repeat-index 1 (§2.9). R6 (§17.6) drops these main runs; they are
    #    kept as the record of what was registered
    PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses run --cell F-0 \
        --model gpt-6.1-sol --effort medium --split main --start 0 --n 100 \
        --task-cell observed-nonrec-near observed-nonrec-far observed-rec-near \
        observed-rec-far --experiment persistgym_sol_h1 --approved-block "3-persistgym" \
        --planned-usd <usd> --parallel 16
    # PREREG §4.6 and §17.6 (amendment R6): luna's main sweep, block 3-persistgym, after G1
    # (registered.G1_PASSED), on T = registered.LUNA_T = 200 templates from 0 (§4.2's rule,
    # capped by R6 change 6): this run, then the same with --cell W-0, W-n-0 and sigma-n-0,
    # and with --variant restated (the restated-at-need control, in F-0); at luna's
    # registered effort (medium), on the default config and the 8 task cells
    PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses run --cell F-0 \
        --model gpt-6-luna --split main --start 0 --n 200 --experiment persistgym \
        --approved-block "3-persistgym" --planned-usd <usd> --parallel 16 --milestone M2
    # §2.9: each of those five runs again at repeat 1, on the templates whose seed is
    # divisible by 10 (0, 10, ..., 190 at T = 200: 160 episodes a run)
    PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses run --cell F-0 \
        --model gpt-6-luna --split main --start 0 --n 200 --repeat-index 1 \
        --experiment persistgym --approved-block "3-persistgym" --planned-usd <usd> \
        --parallel 16 --milestone M2
    # PREREG §3 H3, §4.3 (D36): luna's position-matched single-turn control, one prompt per
    # template on the 4 non-recoverable task cells (the default --task-cell), sent with F-0's
    # request settings (harnesses/single_turn.py), on the T = 200 templates from 0 (--n,
    # registered.LUNA_T); then the same with --repeat-index 1 (§2.9: the templates whose seed
    # is divisible by 10, under their own run id). Its pilot (CLAUDE.md: at most 10 prompts,
    # blinded) is the same command with --experiment persistgym_pilot, --split pilot and --n
    # 2 or fewer
    PERSISTGYM_ALLOW_PAID=1 uv run --env-file .env python -m harnesses single-turn \
        --model gpt-6-luna --split main --start 0 --n 200 --experiment persistgym \
        --approved-block "3-persistgym" --planned-usd <usd> --parallel 16 --milestone M2

`single-turn` refuses, before the paid-run lock (`single_turn.settings_refusal`, then
`registered.check_run_settings` with the control's cell, `registered.LUNA_SINGLE_TURN_CELL`):
any experiment but persistgym and persistgym_pilot; a recoverable task cell; repeat 1 off the
main split; and outside persistgym_pilot, any model but gpt-6-luna and any request settings
but its registered effort and D13's --mode standard and --service-tier flex, and whatever
luna's guard refuses for its main runs (above: the main split, main templates 0-199, the
default config, G1).
"""

from __future__ import annotations

import argparse
import dataclasses
import gzip
import json
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import openai

from common import costs, paidlock, runmeta
from harnesses import (
    account,
    blinding,
    diagnostics,
    probes,
    reasoning_check,
    registered,
    single_turn,
)
from harnesses.cells import CELLS, get_cell
from harnesses.config import HarnessConfig
from harnesses.fake import FakeModel
from harnesses.matrix import RunMatrix
from harnesses.openai_transport import (
    ALLOW_ENV,
    BudgetExceeded,
    OpenAIResponsesTransport,
    PaidCallsNotAllowed,
)
from harnesses.parallel import MAX_PARALLEL
from harnesses.runner import RAW, RESULTS, require_plain_name, run_batch, run_episode
from persistgym.config import PRESETS, GeneratorConfig
from persistgym.episode import TaskCell
from persistgym.render import generate

PILOT_MAX_EPISODES = 10  # CLAUDE.md: a pilot is <= 10 episodes
PILOT_EXPERIMENT = "persistgym_pilot"
PILOT_SPLIT = "pilot"
# The PersistGym stream's paid-run lock. None: persistgym-paid-run-persistgym.lock in the git
# common directory of this checkout, shared with every other checkout; the ARC launcher has
# its own lock next to it. Tests point it at a temporary file, so that they never take the
# real lock or write the last-run records, reservations or holds next to it.
STREAM = paidlock.PERSISTGYM
LOCK_PATH: Path | None = None
# The ledger `account-run` appends to. None: this checkout's results/costs.csv. Tests point it
# at a temporary file.
COSTS_PATH: Path | None = None
RUN_ARGS = ("cell", "split", "start", "variant", "W", "gen_preset", "gen_set", "model",
            "effort", "mode", "service_tier", "milestone", "approved_block", "planned_usd", "n",
            "task_cell", "matrix", "n_observed", "cell_templates", "experiment", "parallel",
            "repeat_index")
"""The arguments of `run` that decide what it runs and how it is accounted for (all but
--run-id): its run plan records them (`_run_args`), and `account-run` takes them."""


def _run_id(tag: str) -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + tag


def _run_args(a) -> dict:
    """`run`'s arguments as its run plan records them (RUN_ARGS): --repeat-index only at 1,
    so that a repeat-0 run's plan is the one `run` wrote before the option existed (and
    `account-run` reads a plan without it as repeat 0)."""
    return {k: getattr(a, k) for k in RUN_ARGS if k != "repeat_index" or a.repeat_index}


def _rel(path) -> str:
    try:
        return path.relative_to(runmeta.REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _gen_config(preset: str, sets: list[str]) -> GeneratorConfig:
    """The generator config of --gen-preset (`persistgym.config.PRESETS`) with each --gen-set
    FIELD=JSON applied."""
    changes = {}
    for s in sets or []:
        key, _, raw = s.partition("=")
        val = json.loads(raw)
        changes[key] = tuple(val) if isinstance(val, list) else val
    return PRESETS[preset].replace(**changes)


def _harness_config(a) -> HarnessConfig:
    return HarnessConfig(model=a.model, reasoning_effort=a.effort, reasoning_mode=a.mode,
                         service_tier=a.service_tier, W_tokens=a.W)


def _run_matrix(a) -> RunMatrix:
    """--matrix full (default: --task-cell on --n templates), --matrix d11 (D11: derived-far
    on --n = T_d templates, observed-far on the first --n-observed = T_o of them, default
    T_d / 3) or --cell-templates TASK_CELL=N ... (a custom matrix); with --repeat-index 1,
    that matrix's repeat (PREREG §2.9: its main templates whose seed is divisible by 10,
    `RunMatrix.repeat`)."""
    if a.cell_templates:
        if a.matrix != "full" or a.task_cell != ["all"] or a.n_observed is not None:
            raise ValueError("--cell-templates replaces --matrix, --task-cell and "
                             "--n-observed")
        matrix = RunMatrix.parse(a.cell_templates)
    elif a.matrix == "d11":
        if a.task_cell != ["all"]:
            raise ValueError("--matrix d11 fixes the task cells; leave out --task-cell")
        matrix = RunMatrix.d11(a.n, a.n_observed)
    else:
        if a.n_observed is not None:
            raise ValueError("--n-observed applies to --matrix d11 only")
        matrix = RunMatrix.full(a.n, None if a.task_cell == ["all"] else a.task_cell)
    return matrix.repeat(a.split, a.start) if a.repeat_index else matrix


def _run_notes(a, matrix: RunMatrix) -> str:
    """The run's notes in its costs row: the split, the templates, the matrix, the repeat
    (at 1 only) and the parallel."""
    return (f"{a.split} {a.start}-{a.start + matrix.n_templates - 1} matrix={matrix.name}"
            + (f" repeat_index={matrix.repeat_index}" if matrix.repeat_index else "")
            + (f" parallel={a.parallel}" if a.parallel > 1 else ""))


def _run_what(a, cell, n_episodes: int) -> str:
    """What the run's paid-run lock says it does."""
    return (f"{a.experiment}: {cell.cell_id} on {a.model}, {n_episodes} episodes"
            + (f" at repeat {a.repeat_index}" if a.repeat_index else "")
            + (f", {a.parallel} at once" if a.parallel > 1 else ""))


def cmd_cells(a) -> int:
    print(f"{'cell':<8}{'ascii':<12}{'history':<9}{'notes':<7}{'reasoning.context':<19}role")
    for c in CELLS.values():
        print(f"{c.cell_id:<8}{c.ascii_id:<12}{c.history:<9}{c.notes!s:<7}"
              f"{c.reasoning_context:<19}{c.role}{' (optional)' if c.optional else ''}")
    return 0


def cmd_dry_run(a) -> int:
    """Run one generated episode with the fake model and print what every request sends."""
    cell = get_cell(a.cell)
    gen = _gen_config(a.gen_preset, a.gen_set)
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
              f"reasoning.effort={e['payload']['reasoning']['effort']} "
              f"{' '.join(e['trace'])}")
    print(f"payload S at need: {run.need_payload and run.need_payload['S']}; designed S "
          f"(obs only): {run.designed['S_window_obs_only']}")
    return 0


def _guarded_transport(a, model: str, experiment: str, planned_usd: float | None,
                       held: paidlock.HeldLock):
    try:
        return OpenAIResponsesTransport(model=model, approved_block=a.approved_block,
                                        experiment=experiment, planned_usd=planned_usd,
                                        paid_lock=held)
    except PaidCallsNotAllowed as e:
        print(f"refused: {e}", file=sys.stderr)
        return None


def _with_paid_lock(run_id: str, what: str, body: Callable[[paidlock.HeldLock], int]) -> int:
    """`body(held)` while this command holds the PersistGym stream's paid-run lock: one
    PersistGym paid run at a time, beside at most one ARC run, which has its own lock
    (PREREG §0.3 line 15, §12). The lock is taken before the transport's spend checks, so
    two PersistGym runs cannot both pass them. Refuses (2) when paid calls are off, which the
    transport would refuse anyway, so a command that cannot spend never touches the shared
    lock, or when another PersistGym run holds it or kept it after an unaccounted run, or
    while the old single lock of a launcher from before the per-stream locks exists."""
    if os.environ.get(ALLOW_ENV) != "1":
        print(f"refused: paid calls are off: set {ALLOW_ENV}=1 for an approved block",
              file=sys.stderr)
        return 2
    try:
        lock = LOCK_PATH or paidlock.lock_path(runmeta.REPO_ROOT, STREAM)
        with paidlock.paid_run_lock(lock, run_id=run_id, what=what, stream=STREAM) as info:
            return body(paidlock.HeldLock(lock, info))
    except paidlock.LockHeld as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2


def _check_accounted(transport: OpenAIResponsesTransport, run_id: str) -> None:
    """After a paid run: if it made calls whose costs.csv row was not appended, the lock
    stays held with the reason (the transport's `keep_lock_if_unaccounted`), and the operator
    is told."""
    why = transport.keep_lock_if_unaccounted(run_id)
    if why:
        print(f"ERROR: could not account for the run. {why}. The paid-run lock stays held: "
              f"{transport.paid_lock.path}", file=sys.stderr)


def cmd_run(a) -> int:
    cell = get_cell(a.cell)
    if not 1 <= a.parallel <= MAX_PARALLEL:
        print(f"refused: --parallel is 1 to {MAX_PARALLEL} episodes at once (PREREG §4.6), "
              f"got {a.parallel}", file=sys.stderr)
        return 2
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
    # PREREG §6 as amended by R2 (§17.2) and R3 (§17.3): outside pilots, the model's
    # registered effort, generator preset and cells only, and sol only after an ENGAGED
    # engagement check on that config (and outside its validity run, after G1); a sol pilot
    # at high effort is R3's check, on sol-chain only, and none runs after R3's hard stop.
    # R4 (§17.4): sol's H1 replication, at medium on the default config, exactly as
    # registered, its main runs after the replication's G1
    try:
        gen = _gen_config(a.gen_preset, a.gen_set)
    except (TypeError, ValueError) as e:
        print(f"refused: --gen-set: {e}", file=sys.stderr)
        return 2
    try:
        matrix = _run_matrix(a)
    except ValueError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    # R4 (§17.4): sol's H1 replication runs on the observed task cells only, with D13's
    # request settings, and its validity run on validity templates 0-19, so the guard gets
    # the task cells and templates the matrix plays and the request settings
    why = registered.check_run_settings(
        a.experiment, a.model, a.effort, cell.cell_id, runmeta.config_hash(gen.to_dict()),
        RESULTS, split=a.split, variant=a.variant,
        task_cells=tuple(c for c, n in matrix.templates if n),
        request={"mode": a.mode, "service_tier": a.service_tier, "W": a.W},
        templates=(a.start, a.start + matrix.n_templates))
    if why:
        print(f"refused: {why}", file=sys.stderr)
        return 2
    if a.split == "main":
        for w in matrix.block_warnings(a.start):
            print(f"note (D7, incomplete balance block): {w}", file=sys.stderr)
    episodes = matrix.episodes(a.split, a.start, gen, a.variant)
    if a.experiment == PILOT_EXPERIMENT and len(episodes) > PILOT_MAX_EPISODES:
        print(f"refused: a pilot is at most {PILOT_MAX_EPISODES} episodes, got "
              f"{len(episodes)}", file=sys.stderr)
        return 2
    # a repeat-1 run's id says so (PREREG §2.9): its episodes are its repeat-0 run's
    run_id = a.run_id or _run_id(f"{cell.ascii_id}-{a.model}"
                                 + (f"-repeat{a.repeat_index}" if a.repeat_index else ""))
    try:
        require_plain_name("--run-id", run_id)
    except ValueError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2

    def paid(held: paidlock.HeldLock) -> int:
        transport = _guarded_transport(a, a.model, a.experiment, a.planned_usd, held)
        if transport is None:
            return 2
        try:
            meta = run_batch(episodes, cell, _harness_config(a), transport,
                             experiment=a.experiment, run_id=run_id, milestone=a.milestone,
                             results_root=RESULTS, raw_root=RAW,
                             repeat_index=matrix.repeat_index, run_matrix=matrix.to_dict(),
                             notes=_run_notes(a, matrix), parallel=a.parallel,
                             run_args=_run_args(a))
        finally:
            _check_accounted(transport, run_id)
        print(json.dumps({k: meta[k] for k in ("run_id", "exit_reason",
                                               "reasoning_context_echoed", "model_returned",
                                               "cost_usd")}, indent=2))
        return 0

    return _with_paid_lock(run_id, _run_what(a, cell, len(episodes)), paid)


def _fork_design(a, kind: str) -> bool:
    return kind == "replay" and a.design == "fork"


def _probe_cfg(a, kind: str) -> probes.ProbeConfig:
    """The probe's request settings: the echo or replay config with --effort, --mode and
    --service-tier."""
    cfg = probes.ECHO_CONFIG if kind == "echo" else probes.REPLAY_CONFIG
    return dataclasses.replace(cfg, reasoning_effort=a.effort, reasoning_mode=a.mode,
                               service_tier=a.service_tier)


def _probe_args(a, kind: str) -> str | None:
    """Fill the design-dependent defaults of a probe command; why it refuses, or None.
    `probe-replay --design fork` (PREREG §17.1): --n is the scorable trials per arm (default
    and at most 20) and --max-attempts the attempts per arm (default and at most 40), and the
    request settings must be the registered ones (the --effort, --mode and --service-tier
    defaults). The other probes keep --n as trials per context (echo 1, original replay
    design 10)."""
    if not _fork_design(a, kind):
        if getattr(a, "max_attempts", None) is not None:
            return "--max-attempts applies to probe-replay --design fork only"
        if a.n is None:
            a.n = 10
        return None
    a.n = probes.FORK_TARGET_SCORABLE if a.n is None else a.n
    a.max_attempts = probes.FORK_MAX_ATTEMPTS if a.max_attempts is None else a.max_attempts
    try:
        probes.check_fork_limits(a.n, a.max_attempts)
        probes.check_fork_config(_probe_cfg(a, kind))
    except ValueError as e:
        return str(e)
    return None


def _probe_run(a, kind: str) -> int:
    experiment = "toggle_pilot" if kind == "echo" else "replay_probe"
    why = _probe_args(a, kind)
    if why:
        print(f"refused: {why}", file=sys.stderr)
        return 2
    tag = "replay-fork" if _fork_design(a, kind) else kind
    return _with_paid_lock(a.run_id or _run_id(f"{tag}-probe"),
                           f"{experiment}: {tag} probe on {', '.join(a.model)}",
                           lambda held: _probe_locked(a, kind, experiment, held))


def _fork_config(a) -> dict:
    """What the fork design adds to meta.json's config (PREREG §17.1)."""
    return {"design": "fork", "target_scorable_per_arm": a.n,
            "max_attempts_per_arm": a.max_attempts, "list_len": probes.FORK_LIST_LEN,
            "forks": probes.FORK_K, "seed_start": probes.FORK_SEED_START,
            "turns": [probes.FORK_TURN1, probes.FORK_TURN2, probes.FORK_TURN3],
            "pass_rule": {"min_agree_all_turns": probes.FORK_MIN_AGREE_ALL_TURNS,
                          "max_agree_current_turn": probes.FORK_MAX_AGREE_CURRENT_TURN,
                          "of_scorable": probes.FORK_TARGET_SCORABLE}}


def _probe_locked(a, kind: str, experiment: str, held: paidlock.HeldLock) -> int:
    """The probe on each --model in turn, under the paid-run lock `held`."""
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
        transport = _guarded_transport(a, model, experiment, remaining, held)
        if transport is None:
            return 2
        fork = _fork_design(a, kind)
        tag = "replay-fork" if fork else kind
        run_id = (f"{a.run_id}-{model}" if a.run_id and len(a.model) > 1
                  else a.run_id or _run_id(f"{tag}-{model}"))
        out_dir, raw_dir = RESULTS / experiment / run_id, RAW / experiment / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)
        started, trials = runmeta.utc_now(), []
        cfg = _probe_cfg(a, kind)
        exit_reason = "INCOMPLETE"
        try:
            with gzip.open(raw_dir / "transcript.jsonl.gz", "at", encoding="utf-8") as raw:
                if fork:
                    def keep(t, raw=raw, trials=trials):
                        raw.write(json.dumps(t, ensure_ascii=False) + "\n")
                        trials.append(probes.fork_record(t))
                    probes.run_fork_arms(model, transport, cfg, contexts=a.contexts,
                                         target=a.n, max_attempts=a.max_attempts,
                                         on_trial=keep)
                else:
                    for rep in range(a.n):
                        for ctx in a.contexts:
                            t = (probes.run_echo_check(model, ctx, transport, cfg)
                                 if kind == "echo"
                                 else probes.run_replay_probe(model, ctx, transport, cfg))
                            raw.write(json.dumps({"repeat": rep, **t}, ensure_ascii=False)
                                      + "\n")
                            trials.append({"repeat": rep, "context_requested": ctx,
                                           "echoes": t["echoes"], "outputs": t["outputs"],
                                           "incomplete_turns": t["incomplete_turns"],
                                           **({"score": t["score"]} if "score" in t else {})})
            exit_reason = "COMPLETED"
        except (openai.OpenAIError, BudgetExceeded) as e:
            exit_reason, status = f"ERROR:{type(e).__name__}: {e}", 1
        finally:
            spent += transport.spent_usd
            try:
                row = transport.finalize(run_id=run_id, milestone=a.milestone,
                                         cell_or_config=f"{tag}-probe")
            finally:
                _check_accounted(transport, run_id)
            with (out_dir / "trials.jsonl").open("a", encoding="utf-8") as f:
                for t in trials:
                    f.write(json.dumps(t, ensure_ascii=False) + "\n")
            echoed = {}
            for t in trials:
                for e in t["echoes"]:
                    echoed[str(e["context_echoed"])] = echoed.get(str(e["context_echoed"]), 0) + 1
            config = {"probe": kind, "probe_config": dataclasses.asdict(cfg),
                      "contexts": a.contexts, "n_per_context": a.n}
            if fork:
                config["fork"] = _fork_config(a)
            runmeta.write_meta(
                out_dir, experiment=experiment, run_id=run_id, cell_or_config=f"{tag}-probe",
                config=config,
                model_requested=model,
                model_returned=sorted({str(e["model_returned"]) for t in trials
                                       for e in t["echoes"]}),
                reasoning_effort=cfg.reasoning_effort, reasoning_context_requested=a.contexts,
                reasoning_context_echoed=echoed, template_id=None, repeat_index=None,
                seeds=({"seed_start": probes.FORK_SEED_START,
                        "seeds": sorted({t["seed"] for t in trials})} if fork else None),
                started_utc=started, finished_utc=runmeta.utc_now(),
                exit_reason=exit_reason, tokens=transport.ledger.totals(),
                cost_usd={"list": transport.ledger.cost_usd_list,
                          "billed_est": transport.ledger.cost_usd_billed_est,
                          "costs_csv_row_appended": row is not None},
                raw_transcript_path=_rel(raw_dir / "transcript.jsonl.gz"),
                git=transport.git)  # read before the first call (common/runmeta.py)
            if fork:
                report = probes.fork_report(trials, target=a.n, max_attempts=a.max_attempts)
                report = {"run_id": run_id, "model_requested": model,
                          "exit_reason": exit_reason, **report}
                (out_dir / "fork_report.json").write_text(
                    json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{model}: {exit_reason}; echoed {echoed}; results in {out_dir}")
        if fork:
            b = report["condition_b"]
            print(f"{model}: forks agree in {b['all_turns_agreements']} (all_turns) and "
                  f"{b['current_turn_agreements']} (current_turn) scorable trials; "
                  f"scorable {[arm['scorable'] for arm in report['arms'].values()]}; "
                  f"condition (b) met: {b['met']} (fork_report.json)")
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


def _read_jsonl(path: Path) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def cmd_probe_summary(a) -> int:
    """$0: per-arm counts of finished replay-probe runs, from their trials.jsonl (and the raw
    transcript under the raw root, when it is there), printed as JSON. The original design
    gets `probes.replay_report`; the fork design `probes.fork_report`, as in its
    fork_report.json."""
    results_root = Path(a.results_root) if a.results_root else RESULTS
    raw_root = Path(a.raw_root) if a.raw_root else RAW
    out = {}
    for run_id in a.run_id:
        try:
            require_plain_name("run id", run_id)
            require_plain_name("--experiment", a.experiment)
        except ValueError as e:
            print(f"refused: {e}", file=sys.stderr)
            return 2
        run_dir = results_root / a.experiment / run_id
        if not (run_dir / "trials.jsonl").exists():
            print(f"no trials.jsonl in {run_dir}", file=sys.stderr)
            return 1
        trials = _read_jsonl(run_dir / "trials.jsonl")
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
        fork = (meta.get("config") or {}).get("fork")
        raw_path = raw_root / a.experiment / run_id / "transcript.jsonl.gz"
        raw = _read_jsonl(raw_path) if raw_path.exists() else None
        if fork:
            report = probes.fork_report(trials, target=fork["target_scorable_per_arm"],
                                        max_attempts=fork["max_attempts_per_arm"])
        else:
            report = probes.replay_report(trials, raw)
        out[run_id] = {"model_requested": meta.get("model_requested"),
                       "exit_reason": meta.get("exit_reason"),
                       "raw_transcript_read": raw is not None, **report}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_reasoning_check(a) -> int:
    """$0: the engagement check of PREREG §17.2 (amendment R2), as amended by R3 (§17.3), on
    two sol pilot runs at high effort on the sol-chain config, F-r and F-0
    (`harnesses.reasoning_check`). Writes
    results/persistgym_pilot/reasoning-check-<time>/reasoning_check.json and prints it: the
    verdict and quantities pooled over both arms, nothing per arm. After R3's hard stop
    (`registered.hard_stop`) it scores nothing more."""
    results_root = Path(a.results_root) if a.results_root else RESULTS
    raw_root = Path(a.raw_root) if a.raw_root else RAW
    stopped = registered.hard_stop(results_root)
    if stopped:
        print(f"refused: {stopped}; no further engagement check is scored", file=sys.stderr)
        return 2
    try:
        for run_id in [*a.run_id, *a.reference]:
            require_plain_name("run id", run_id)
        report = reasoning_check.check(a.run_id, a.reference, results_root=results_root,
                                       raw_root=raw_root)
    except ValueError as e:  # reasoning_check.CheckError included
        print(f"refused: {e}", file=sys.stderr)
        return 2
    name = "reasoning-check-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out, k = results_root / PILOT_EXPERIMENT / name, 1
    while out.exists():  # a second check within the same second gets its own folder
        k += 1
        out = results_root / PILOT_EXPERIMENT / f"{name}-{k}"
    out.mkdir(parents=True)
    path = out / registered.CHECK_FILE
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"verdict: {report['verdict']} ({report['verdict_reason']})", file=sys.stderr)
    print(f"written: {_rel(path)}", file=sys.stderr)
    return 0


def cmd_echo_count(a) -> int:
    """$0: per raw run of the PersistGym stream (or of --experiment), the responses and how
    many echoed the requested reasoning.context and reasoning.effort, from the transcripts'
    echo fields only. Prints JSON; writes nothing."""
    raw_root = Path(a.raw_root) if a.raw_root else RAW
    try:
        for exp in a.experiment or []:
            require_plain_name("--experiment", exp)
    except ValueError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    print(json.dumps(reasoning_check.echo_counts(
        raw_root, a.experiment or reasoning_check.PERSISTGYM_EXPERIMENTS), indent=2))
    return 0


def _run_defaults() -> dict:
    """`run`'s default for every argument in RUN_ARGS but --cell (--effort: None, the
    model's registered effort)."""
    d = vars(build_parser().parse_args(["run", "--cell", "F-0"]))
    return {k: d[k] for k in RUN_ARGS if k != "cell"}


def cmd_account_run(a) -> int:
    """$0: account for a PersistGym paid run whose costs.csv row could not be written
    (`harnesses.account`): rebuild the row, summary.json and meta.json from the run's raw
    files, then record the last paid run and release the run's spend reservation and kept
    lock. --check verifies everything and prints the plan, writing nothing."""
    given = {k: getattr(a, k) for k in RUN_ARGS if hasattr(a, k)}
    git = (None if a.git_commit is None and a.git_dirty is None
           else {"git_commit": a.git_commit, "git_dirty": a.git_dirty == "true"})
    try:
        if (a.git_commit is None) != (a.git_dirty is None):
            raise account.Refused("give --git-commit and --git-dirty together")
        plan_path, plan = account.find_plan(RAW, a.run_id, given.get("experiment"))
        args = argparse.Namespace(**account.run_arguments(plan, given, _run_defaults()))
        if args.effort is None:
            args.effort = registered.registered_effort(args.model)
        cell = get_cell(args.cell)
        matrix = _run_matrix(args)
        episodes = matrix.episodes(args.split, args.start,
                                   _gen_config(args.gen_preset, args.gen_set), args.variant)
        run = account.Run(run_id=a.run_id, args=args, cell=cell, cfg=_harness_config(args),
                          matrix=matrix, episodes=episodes, notes=_run_notes(args, matrix),
                          what=_run_what(args, cell, len(episodes)))
        lock = LOCK_PATH or paidlock.lock_path(runmeta.REPO_ROOT, STREAM)
        rec = account.prepare(run, plan=plan, plan_path=plan_path, git=git,
                              started=a.started_utc, lock_path=lock,
                              costs_path=COSTS_PATH or costs.COSTS_CSV, results_root=RESULTS,
                              raw_root=RAW)
    except (ValueError, KeyError, paidlock.LockHeld) as e:  # account.Refused included
        print(f"refused: {e}", file=sys.stderr)
        return 2
    print("\n".join(rec.describe()))
    if a.check:
        print("--check: nothing written")
        return 0
    try:
        done = account.write(rec)
    except account.Refused as e:
        print(f"refused: {e}; nothing written", file=sys.stderr)
        return 2
    except account.Incomplete as e:
        print(f"ERROR: account-run stopped: {e}", file=sys.stderr)
        for what in e.done:
            print(f"  done: {what}", file=sys.stderr)
        for what in e.remaining:
            print(f"  NOT done: {what}", file=sys.stderr)
        if not e.done:
            print("  nothing was written: the lock and the reservation are as they were",
                  file=sys.stderr)
        elif e.lock_noted:
            print(f"  the costs row is in {rec.costs_path}: do not add it again. The lock "
                  f"{rec.lock_path} stays kept, with this in its reason: do what is not done "
                  f"by hand, then delete it", file=sys.stderr)
        else:
            print(f"  the costs row is in {rec.costs_path}: do not add it again. This could "
                  f"not be added to the reason of the lock {rec.lock_path} (changed or "
                  f"gone): do what is not done by hand", file=sys.stderr)
        return 1
    for what in done:
        print(f"done: {what}")
    return 0


def cmd_summary_timing(a) -> int:
    print(json.dumps(diagnostics.summary_timing(
        a.n, split=a.split, summary_tokens=a.summary_tokens,
        keep_recent=tuple(a.keep_recent)), indent=2))
    return 0


SINGLE_TURN_ARGS = ("split", "start", "n", "task_cell", "gen_preset", "gen_set", "model",
                    "effort", "mode", "service_tier", "milestone", "approved_block",
                    "planned_usd", "experiment", "repeat_index", "parallel")
"""The arguments of `single-turn` that decide what it runs and how it is accounted for (all
but --run-id): its run plan records them."""


def _split_refusal(experiment: str, split: str) -> str | None:
    """`run`'s split rules (PLAN §16.5, PREREG §11): pilot templates run only under the
    blinded pilot experiment, and the pilot experiment runs pilot templates only."""
    if experiment == PILOT_EXPERIMENT and split != PILOT_SPLIT:
        return f"{PILOT_EXPERIMENT} runs use --split {PILOT_SPLIT} only, got {split!r}"
    if split == PILOT_SPLIT and experiment != PILOT_EXPERIMENT:
        return (f"--split {PILOT_SPLIT} templates are pilot data and run only with "
                f"--experiment {PILOT_EXPERIMENT} (blinded, PREREG §11), got {experiment!r}; "
                "a main-sweep run needs --split main")
    return None


def cmd_single_turn(a) -> int:
    """Paid run of H3's position-matched single-turn control (PREREG §3 H3, §4.3, D36;
    `harnesses.single_turn`): one prompt per template on the non-recoverable task cells, sent
    with F-0's request settings and scored as the need step. Guarded as `run` is: the
    settings checks below before the paid-run lock, then the lock and the transport's checks
    (`_with_paid_lock`, `_guarded_transport`), and the run stops before a call once its
    spend reaches --planned-usd."""
    def refuse(why: str) -> int:
        print(f"refused: {why}", file=sys.stderr)
        return 2

    if not 1 <= a.parallel <= MAX_PARALLEL:
        return refuse(f"--parallel is 1 to {MAX_PARALLEL} prompts at once (PREREG §4.6), got "
                      f"{a.parallel}")
    why = _split_refusal(a.experiment, a.split) or single_turn.settings_refusal(
        experiment=a.experiment, model=a.model, split=a.split, repeat_index=a.repeat_index)
    if why:
        return refuse(why)
    try:
        gen = _gen_config(a.gen_preset, a.gen_set)
    except (TypeError, ValueError) as e:
        return refuse(f"--gen-set: {e}")
    # what the arguments play, as `run` builds its matrix before its guard: a repeat-1 range
    # with no seed divisible by 10 refuses here, with `run`'s words
    try:
        cells = single_turn.task_cells(a.task_cell)
        indices = single_turn.template_indices(a.split, a.start, a.n, a.repeat_index)
        cfg = HarnessConfig(model=a.model, reasoning_effort=a.effort, reasoning_mode=a.mode,
                            service_tier=a.service_tier)
    except ValueError as e:
        return refuse(str(e))
    # `run`'s guard, given the control's cell (registered.LUNA_SINGLE_TURN_CELL, the prompts'
    # harness_cell): outside pilots, the model's registered effort and luna's guard, so the
    # control plays luna's main split on the config its G1 is recorded on (sol's rules too,
    # which settings_refusal already refuses outside pilots)
    why = registered.check_run_settings(
        a.experiment, a.model, a.effort, registered.LUNA_SINGLE_TURN_CELL,
        runmeta.config_hash(gen.to_dict()), RESULTS, split=a.split, variant="base",
        task_cells=tuple(cells),
        request={"mode": a.mode, "service_tier": a.service_tier, "W": None},
        templates=(a.start, a.start + a.n))
    if why:
        return refuse(why)
    if a.split == "main":
        for w in RunMatrix.full(a.n, cells).block_warnings(a.start):
            print(f"note (D7, incomplete balance block): {w}", file=sys.stderr)
    prompts = single_turn.build_prompts(a.split, indices, gen, cells)
    if a.experiment == PILOT_EXPERIMENT and len(prompts) > PILOT_MAX_EPISODES:
        return refuse(f"a pilot is at most {PILOT_MAX_EPISODES} prompts, got {len(prompts)}")
    # a repeat-1 run's id says so, as `run` names one (PREREG §2.9)
    run_id = a.run_id or _run_id(f"{single_turn.COMMAND}-{a.model}"
                                 + (f"-repeat{a.repeat_index}" if a.repeat_index else ""))
    try:
        require_plain_name("--run-id", run_id)
    except ValueError as e:
        return refuse(str(e))
    notes = (f"{a.split} {a.start}-{a.start + a.n - 1} control={single_turn.CONTROL} "
             f"repeat_index={a.repeat_index}"
             + (f" parallel={a.parallel}" if a.parallel > 1 else ""))
    templates = {"split": a.split, "start": a.start, "n": a.n,
                 "repeat_index": a.repeat_index, "indices": indices}

    def paid(held: paidlock.HeldLock) -> int:
        transport = _guarded_transport(a, a.model, a.experiment, a.planned_usd, held)
        if transport is None:
            return 2
        try:
            meta = single_turn.run_controls(
                prompts, cfg, transport, experiment=a.experiment, run_id=run_id,
                milestone=a.milestone, results_root=RESULTS, raw_root=RAW,
                repeat_index=a.repeat_index, notes=notes, parallel=a.parallel,
                templates=templates, run_args={k: getattr(a, k) for k in SINGLE_TURN_ARGS})
        finally:
            _check_accounted(transport, run_id)
        print(json.dumps({k: meta[k] for k in ("run_id", "exit_reason",
                                               "reasoning_context_echoed", "model_returned",
                                               "cost_usd")}, indent=2))
        return 0

    what = (f"{a.experiment}: single-turn control on {a.model}, {len(prompts)} prompts"
            + (f", {a.parallel} at once" if a.parallel > 1 else ""))
    return _with_paid_lock(run_id, what, paid)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m harnesses")
    sub = p.add_subparsers(dest="cmd", required=True)

    def adder(sp, account: bool):
        """`sp.add_argument`, or for `account-run` (account=True) the same argument with no
        default and never required, so that the arguments given can be told from the rest
        (which come from the run plan, or are `run`'s defaults)."""
        def add(*names, **kw):
            if account:
                kw.update(default=argparse.SUPPRESS, required=False)
            sp.add_argument(*names, **kw)
        return add

    def request_args(sp, model_default="gpt-6-luna", multi_model=False,
                     effort_default: str | None = None, account=False):
        add = adder(sp, account)
        if multi_model:
            add("--model", action="append", default=None)
        else:
            add("--model", default=model_default)
        add("--effort", default=effort_default,
            help=("default: the model's registered effort (harnesses/registered.py; PREREG §6 "
                  "as amended by R2, §17.2)" if effort_default is None
                  else f"default: {effort_default}"))
        add("--mode", default="standard")
        add("--service-tier", default="flex")
        add("--milestone", default="M0")
        if not account:
            add("--run-id", default=None)

    def episode_args(sp, account=False):
        add = adder(sp, account)
        add("--cell", required=True)
        add("--split", default="pilot")
        add("--start", type=int, default=0)
        add("--variant", default="base")
        add("--W", type=int, default=None, help="default: the episode's W")
        add("--gen-preset", choices=sorted(PRESETS), default="default",
            help="generator config (persistgym/config.py PRESETS): default, or sol-chain, "
                 "gpt-6.1-sol's derived-fact variant (PREREG §17.3), which every non-pilot "
                 "sol run and sol's engagement check at high effort use")
        add("--gen-set", action="append", default=[], metavar="FIELD=JSON",
            help="override one field of the --gen-preset config")

    def paid_args(sp, account=False):
        add = adder(sp, account)
        add("--approved-block", default=None,
            help="name of the researcher-approved spending block (PLAN §16.2); its approval "
                 "line in results/decisions.md must list the experiment and leave room under "
                 "its max_usd")
        add("--planned-usd", type=float, default=None,
            help="planned spend of the whole command in USD, measured like block spend and "
                 "the phase caps: the billed estimate, so on Flex the Flex price (for probes, "
                 "the total over all --model values)")

    def run_args(sp, account=False):
        """The arguments of `run` besides episode_args, request_args and paid_args."""
        add = adder(sp, account)
        add("--n", type=int, default=1,
            help="templates per task cell (--matrix d11: T_d, the derived-far count)")
        add("--task-cell", nargs="+", default=["all"])
        add("--matrix", choices=("full", "d11"), default="full",
            help="full: --task-cell on --n templates; d11: derived-far cells on --n templates "
                 "and observed-far cells on the first --n-observed (D11)")
        add("--n-observed", type=int, default=None,
            help="--matrix d11: observed-far templates T_o (default --n / 3)")
        add("--cell-templates", nargs="+", default=None, metavar="TASK_CELL=N",
            help="custom matrix: each task cell on its first N templates from --start")
        add("--experiment", default="persistgym_pilot")
        add("--repeat-index", type=int, choices=(0, 1), default=0,
            help="1: the repeat of PREREG §2.9: of the matrix's templates, only those whose "
                 "seed is divisible by 10 (--split main only), in the same task cells and "
                 "--variant, with repeat_index 1 in the run plan, meta.json, episodes.jsonl and "
                 "the costs row's notes, and a run id ending -repeat1")
        add("--parallel", type=int, default=1, metavar="N",
            help=f"episodes played at once, 1 to {MAX_PARALLEL} (PREREG §4.6): the same "
                 "payloads, cell assignment, seeds and per-episode outputs as one at a time, "
                 "written in the same order; the run reserves spend for the episodes in "
                 "flight, so that it stays within --planned-usd")

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
    run_args(r)
    r.set_defaults(fn=cmd_run)

    ac = sub.add_parser("account-run",
                        help="account for a paid run whose costs.csv row could not be written: "
                             "its row, summary.json and meta.json from its raw files ($0)")
    ac.add_argument("run_id", metavar="RUN_ID")
    ac.add_argument("--check", action="store_true",
                    help="verify everything and print what would be written; write nothing")
    ac.add_argument("--git-commit", default=None,
                    help="a run without run_plan.json: the commit it ran (its launch "
                         "checkout's HEAD)")
    ac.add_argument("--git-dirty", choices=("true", "false"), default=None,
                    help="a run without run_plan.json: whether tracked files differed from "
                         "that commit when it started (true if results/costs.csv held an "
                         "earlier run's uncommitted row; false is refused when the ledger "
                         "shows one)")
    ac.add_argument("--started-utc", default=None,
                    help="a run without run_plan.json: when it started (default: its "
                         "paid-run lock's started_utc)")
    # `run`'s arguments, for a run without run_plan.json, with no defaults here, so that the
    # ones given can be checked against the plan's (RUN_ARGS)
    episode_args(ac, account=True)
    request_args(ac, account=True)
    paid_args(ac, account=True)
    run_args(ac, account=True)
    ac.set_defaults(fn=cmd_account_run)

    pr = sub.add_parser("pilot-report",
                        help="pooled pilot report from the raw pilot runs ($0, PREREG §11)")
    pr.add_argument("--experiment", default=PILOT_EXPERIMENT)
    pr.set_defaults(fn=cmd_pilot_report)

    ps = sub.add_parser("probe-summary",
                        help="per-arm counts of finished replay-probe runs ($0)")
    ps.add_argument("run_id", nargs="+")
    ps.add_argument("--experiment", default="replay_probe")
    ps.add_argument("--results-root", default=None, help="default: this checkout's results/")
    ps.add_argument("--raw-root", default=None, help="default: this checkout's results/raw/")
    ps.set_defaults(fn=cmd_probe_summary)

    rc = sub.add_parser("reasoning-check",
                        help="the engagement check of PREREG §17.2 and §17.3 on two sol "
                             "pilot runs at high effort on sol-chain, F-r and F-0 ($0)")
    rc.add_argument("run_id", nargs=2, metavar="RUN_ID",
                    help="the check runs: one F-r and one F-0 persistgym_pilot run")
    rc.add_argument("--reference", nargs="+", action="extend", default=[], metavar="RUN_ID",
                    help="runs reported alongside, descriptive only: one F-r and one F-0 sol "
                         "pilot run, on any config (e.g. R2's check runs)")
    rc.add_argument("--results-root", default=None, help="default: this checkout's results/")
    rc.add_argument("--raw-root", default=None, help="default: this checkout's results/raw/")
    rc.set_defaults(fn=cmd_reasoning_check)

    ec = sub.add_parser("echo-count",
                        help="responses and reasoning.context / reasoning.effort echo matches "
                             "per raw run ($0)")
    ec.add_argument("--experiment", action="append", default=None,
                    help="default: every PersistGym-stream experiment")
    ec.add_argument("--raw-root", default=None, help="default: this checkout's results/raw/")
    ec.set_defaults(fn=cmd_echo_count)

    for kind in ("echo", "replay"):
        sp = sub.add_parser(f"probe-{kind}", help=f"paid {kind} probe (guarded)")
        # the probes' registered effort (PREREG §17.1: medium on both models), whatever the
        # model's registered effort for harness runs
        request_args(sp, multi_model=True, effort_default=probes.REPLAY_CONFIG.reasoning_effort)
        paid_args(sp)
        sp.add_argument("--contexts", nargs="+", default=list(probes.CONTEXTS))
        sp.add_argument("--n", type=int, default=1 if kind == "echo" else None,
                        help="trials per context (default 1 for echo, 10 for the original "
                             "replay design); --design fork: scorable trials per arm "
                             "(default and at most 20)")
        if kind == "replay":
            sp.add_argument("--design", choices=("original", "fork"), default="original",
                            help="original: the summary-scored probe of D29 as frozen; fork: "
                                 "the fork-consistency probe of amendment R1 (PREREG §17.1)")
            sp.add_argument("--max-attempts", type=int, default=None,
                            help="--design fork: attempts per arm per model, scorable or not "
                                 "(default and at most 40)")
        sp.set_defaults(fn=lambda a, k=kind: _probe_run(a, k))

    s1 = sub.add_parser("single-turn",
                        help="paid run of H3's position-matched single-turn control (guarded)")
    request_args(s1)
    paid_args(s1)
    s1.add_argument("--split", default="pilot")
    s1.add_argument("--start", type=int, default=0)
    s1.add_argument("--n", type=int, default=1, help="templates per task cell, from --start")
    s1.add_argument("--task-cell", nargs="+", default=["all"],
                    help="non-recoverable task cells only; all (default): the 4 of them")
    s1.add_argument("--gen-preset", choices=sorted(PRESETS), default="default",
                    help="generator config (persistgym/config.py PRESETS)")
    s1.add_argument("--gen-set", action="append", default=[], metavar="FIELD=JSON",
                    help="override one field of the --gen-preset config")
    s1.add_argument("--experiment", default=PILOT_EXPERIMENT)
    s1.add_argument("--repeat-index", type=int, choices=single_turn.REPEAT_INDICES, default=0,
                    help="1: PREREG §2.9's repeat, on the main templates of [--start, --start "
                         "+ --n) whose seed is divisible by 10 only, with a run id ending "
                         "-repeat1")
    s1.add_argument("--parallel", type=int, default=1, metavar="N",
                    help=f"prompts sent at once, 1 to {MAX_PARALLEL} (PREREG §4.6), with spend "
                         "reserved for the prompts in flight, as `run --parallel`")
    s1.set_defaults(fn=cmd_single_turn)
    return p


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """The parsed command line, with the defaults that depend on other arguments filled in:
    the probes' models, and the registered effort of `run`, `dry-run` and `single-turn`'s
    --model."""
    a = build_parser().parse_args(argv)
    if a.cmd in ("probe-echo", "probe-replay") and not a.model:
        a.model = list(probes.ECHO_CHECK_MODELS)
    if a.cmd in ("run", "dry-run", "single-turn") and a.effort is None:
        a.effort = registered.registered_effort(a.model)
    return a


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    a = parse_args(argv)
    return a.fn(a)
