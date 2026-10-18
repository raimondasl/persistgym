"""What every paid transport of the PersistGym stream shares: the guard, the git state, the
ledger, the stop at the planned spend, the retries, the costs row and the paid-run lock.

`PaidTransport` is `OpenAIResponsesTransport`'s code (harnesses/openai_transport.py, whose
module docstring documents the guard and the accounting), made provider-neutral. Each
provider's transport fills in the hooks:
* `_preflight()`: checks that run before the guard, with no side effect (Anthropic: the
  credentials in the environment);
* `_default_client(timeout_s)`: the provider's SDK client, with the SDK's own retries off;
* `_check_request(payload)`: a check of each body before it is sent (Anthropic: the
  Messages wire's request-side check, `harnesses.wire.MessagesWire.check_payload`);
* `_call(client, payload) -> dict`: one attempt, the response as JSON types;
* `_retry_wait(error, attempt) -> float | None`: the seconds to wait before the next
  attempt, or None to raise the error now (a provider-side spend limit raises
  `ProviderHardStop` instead);
* `_echo_record(payload, data)` and `_log_response(echo, payload, blinded)`: what is logged
  per response;
* `_mismatches()`: the echo mismatches the costs row's notes count.

The guard runs in `__post_init__` before any client exists, as in sequential play, and every
`send` may be called from several threads at once (harnesses/parallel.py).
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common import costs, paidlock, runmeta
from common.approval import (
    MAIN,
    PaidCallsNotAllowed,
    RemoteRef,
    require_paid_run,
    spend_tag,
    spend_usd,
)
from harnesses import blinding
from harnesses.pricing import UsageLedger, price_for
from harnesses.wire import wire_for

NOT_ECHOED = "n/a"
"""A costs row's mismatch count for an echo the provider does not give (the Messages API)."""


class BudgetExceeded(RuntimeError):
    pass


class ProviderHardStop(RuntimeError):
    """The provider refuses further spend (Anthropic: the organization's spend limit, a 429
    `enforced_spend_limit_reached`, or a usage limit set in the Console, a 400). Never retried
    and never an episode's API_ERROR: the runner does not catch it, so the run stops at once
    (`ERROR:ProviderHardStop`), with its costs row written as usual."""


def build_costs_row(ledger: UsageLedger, *, timestamp_utc: str, run_id: str, milestone: str,
                    approved_block: str, experiment: str, cell_or_config: str, git: dict,
                    context_mismatches: int | str, effort_mismatches: int | str,
                    notes: str = "") -> dict:
    """The run's results/costs.csv row as `finalize` appends it: the ledger's totals, notes that
    start with the block's spend tag and count the `reasoning.context` and `reasoning.effort`
    echo mismatches (`NOT_ECHOED` for a provider that echoes neither), the git state the run
    read at its start, and, for a pilot-blinded experiment, `reasoning_tokens` left empty
    (PREREG §11). `harnesses account-run` builds the row of a run whose `finalize` could not
    write it with this function too."""
    row = ledger.costs_row(
        timestamp_utc=timestamp_utc, run_id=run_id, milestone=milestone,
        experiment=experiment, cell_or_config=cell_or_config, git_commit=git["git_commit"],
        notes=(f"{spend_tag(approved_block)} context_mismatches={context_mismatches}; "
               f"effort_mismatches={effort_mismatches}; git_dirty={git['git_dirty']}"
               + (f"; {notes}" if notes else "")))
    if blinding.is_blinded(experiment):
        # PREREG §11: no per-arm reasoning tokens from pilot data in committed files. The
        # per-call values stay in the raw transcript (results/raw/, gitignored).
        row["reasoning_tokens"] = ""
        row["notes"] = f"{row['notes']}; {blinding.WITHHELD_NOTE}"
    return row


@dataclass
class PaidTransport:
    model: str
    approved_block: str | None
    experiment: str
    planned_usd: float
    # the paid-run lock this run holds (harnesses/cli.py takes it); None refuses
    paid_lock: paidlock.HeldLock | None = None
    costs_path: Path = costs.COSTS_CSV
    repo: Path = runmeta.REPO_ROOT
    timeout_s: float = 900.0  # Flex guide's examples use 15 minutes
    max_attempts: int = 6
    backoff_s: float = 5.0
    client_factory: Callable[[float], Any] | None = None
    sleep: Callable[[float], None] = time.sleep
    # where an approval must have been merged (origin/main); tests use a local bare repo
    approval_remote: RemoteRef = MAIN
    # the git state of the code that makes the calls; None: read once the guard has passed
    git: dict | None = None
    paid: bool = field(default=True, init=False)

    log = logging.getLogger("harnesses.paid")
    """The logger; each provider's transport has its own."""

    @property
    def wire(self):
        """The model's wire (`harnesses.wire.wire_for`)."""
        return wire_for(self.model)

    def __post_init__(self) -> None:
        self._preflight()
        # Guard first: nothing below runs without approval.
        self.approval = require_paid_run(
            lock=self.paid_lock, approved_block=self.approved_block,
            experiment=self.experiment, planned_usd=self.planned_usd,
            costs_path=self.costs_path, repo=self.repo, remote=self.approval_remote)
        price_for(self.model)  # refuse a model we cannot cost
        if self.git is None:
            # Once, before any call: `finalize` and the runner's meta.json use this value,
            # so no process is started after the calls (common/runmeta.py).
            try:
                self.git = runmeta.git_state()
            except (OSError, subprocess.CalledProcessError) as e:
                raise PaidCallsNotAllowed(f"cannot read the git state of the code ({e}); no "
                                          f"paid call was made") from None
        self.git = runmeta.check_git_state(dict(self.git))
        self.ledger = UsageLedger(self.model)
        self.echo_log: list[dict] = []
        self._finalized = False
        self.costs_row: dict | None = None  # the row `finalize` appended
        self.kept_because: str | None = None  # why the lock was kept held, if it was
        # Parallel play (harnesses/parallel.py) sends from several threads at once: the
        # budget check, the ledger and the echo log change under this lock, and each thread
        # gets its own client from the factory. `_in_flight` counts calls sent and not yet
        # recorded; `abandoned_calls` those still in flight when `finalize` ran.
        self._lock = threading.RLock()
        self._in_flight = 0
        self.abandoned_calls = 0
        self._client = (self.client_factory or self._default_client)(self.timeout_s)
        self._clients = threading.local()
        self._clients.client = self._client

    # --- hooks -----------------------------------------------------------------------------
    def _preflight(self) -> None:
        """Checks before the guard, with no side effect; raise `PaidCallsNotAllowed`."""

    def _default_client(self, timeout_s: float) -> Any:
        raise NotImplementedError

    def _check_request(self, payload: dict) -> None:
        """A check of each body before it is sent; raises to refuse it."""

    def _call(self, client: Any, payload: dict) -> dict:
        raise NotImplementedError

    def _retry_wait(self, error: Exception, attempt: int) -> float | None:
        """Seconds to wait before attempt `attempt` + 1, or None: raise `error` now."""
        return None

    def _echo_record(self, payload: dict, data: dict) -> dict:
        raise NotImplementedError

    def _log_response(self, echo: dict, payload: dict, blinded: bool) -> None:
        """Log one recorded response."""

    def _mismatches(self) -> tuple[int | str, int | str]:
        """(reasoning.context, reasoning.effort) echo mismatches over the run, for the costs
        row's notes."""
        return (sum(1 for e in self.echo_log if e["requested_context"] != e["echoed_context"]),
                sum(1 for e in self.echo_log if e["requested_effort"] != e["echoed_effort"]))

    # ---------------------------------------------------------------------------------------
    @property
    def spent_usd(self) -> float:
        """This run's spend so far, measured as block spend and the phase caps measure it
        (`common.approval.spend_usd`: the billed estimate, the Flex price on Flex). The run
        stops before a call once it reaches the planned spend, so the guard's check `block
        spend + planned <= max_usd` holds after the run too, up to the last call's cost (with
        episodes played in parallel too, through their per-call gate,
        `harnesses.parallel.CallGate`)."""
        with self._lock:
            return spend_usd(self.ledger.cost_usd_list, self.ledger.cost_usd_billed_est)

    def _thread_client(self) -> Any:
        client = getattr(self._clients, "client", None)
        if client is None:
            client = self._clients.client = (self.client_factory
                                             or self._default_client)(self.timeout_s)
        return client

    def send(self, payload: dict) -> dict:
        """One call, with retries. Safe to call from several threads at once: the stop at the
        planned spend is checked, under the lock, on the spend of every call recorded so
        far, so it stays exact; calls already sent when it fires still complete and are
        recorded."""
        counted = False
        try:
            self._check_request(payload)
            with self._lock:
                if self._finalized:
                    raise RuntimeError("transport already finalized")
                if payload.get("model") != self.model:
                    raise ValueError(f"payload model {payload.get('model')!r} != "
                                     f"{self.model!r}")
                if self.spent_usd >= self.approval.planned_usd:
                    raise BudgetExceeded(
                        f"run spend ${self.spent_usd:.4f} (billed estimate) "
                        f"reached the planned ${self.approval.planned_usd:.2f}")
                self._in_flight += 1
                counted = True
            client = self._thread_client()
            started = time.monotonic()
            for attempt in range(1, self.max_attempts + 1):
                try:
                    data = self._call(client, payload)
                    break
                except Exception as e:
                    wait = self._retry_wait(e, attempt)
                    if wait is None or attempt == self.max_attempts:
                        raise
                    self.log.warning("attempt %d failed (%s); retrying in %.0fs", attempt,
                                     type(e).__name__, wait)
                    self.sleep(wait)
            latency = time.monotonic() - started
        except BaseException:
            if counted:
                with self._lock:
                    self._in_flight -= 1
            raise
        with self._lock:
            self._in_flight -= 1
            if self._finalized:
                # `finalize` ran while this call was in flight (a parallel run stopped
                # without waiting for it): it counted the call in `abandoned_calls`, kept the
                # lock, and the call's usage goes nowhere.
                raise RuntimeError("transport finalized while this call was in flight; its "
                                   "usage is not recorded")
            listed, billed = self.ledger.add(data,
                                             requested_tier=self.wire.requested_tier(payload),
                                             latency_s=latency)
            echo = {**self._echo_record(payload, data), "latency_s": latency,
                    "cost_usd_list": listed, "cost_usd_billed_est": billed}
            self.echo_log.append(echo)
        # PREREG §11: a blinded pilot logs no call's status. A warning per incomplete
        # response, less the routine ones its summary.json counts, would count those at the
        # need step, which score 0 (D13); the raw transcript holds every call's status.
        self._log_response(echo, payload, blinding.is_blinded(self.approval.experiment))
        return data

    def finalize(self, *, run_id: str, milestone: str, cell_or_config: str,
                 notes: str = "") -> dict | None:
        """Append this run's costs.csv row (once) and record the run next to the paid-run
        lock as the last paid run. Returns the row, or None if no call was made. If the row
        cannot be built or written, keeps the lock held with the reason
        (`keep_lock_if_unaccounted`) and raises.

        Calls still in flight (episodes played in parallel, abandoned by a second Ctrl+C;
        harnesses/parallel.py) are counted in `abandoned_calls` and never recorded: the row,
        if any, is written without them, and the lock and the spend reservation stay held,
        with the reason, as for a row that could not be written."""
        with self._lock:
            if self._finalized:
                return None
            self._finalized = True
            self.abandoned_calls = self._in_flight
        if self.abandoned_calls:
            self.log.warning("%d calls were still in flight when the run was finalized; their "
                             "usage is not recorded", self.abandoned_calls)
        if self.ledger.n_calls == 0:
            if self.abandoned_calls:
                self.keep_lock_if_unaccounted(run_id)
            else:
                self._release_reservation()      # spent nothing
            return None
        try:
            context_mismatches, effort_mismatches = self._mismatches()
            row = build_costs_row(
                self.ledger, timestamp_utc=runmeta.utc_now(), run_id=run_id,
                milestone=milestone, approved_block=self.approval.approved_block,
                experiment=self.approval.experiment, cell_or_config=cell_or_config,
                git=self.git,  # read before the first call: the code that made the calls
                context_mismatches=context_mismatches, effort_mismatches=effort_mismatches,
                notes=notes)
            costs.append_row(row, self.approval.costs_path)
        except BaseException as e:
            self.keep_lock_if_unaccounted(run_id, cause=f"{type(e).__name__}: {e}")
            raise
        self.costs_row = row
        try:
            paidlock.record_last_run(self.paid_lock.path, stream=self.paid_lock.stream,
                                     run_id=run_id, costs_csv=self.approval.costs_path,
                                     timestamp_utc=row["timestamp_utc"])
        except OSError as e:
            self.log.warning("could not record the last paid run next to %s: %s",
                             self.paid_lock.path, e)
        if self.abandoned_calls:
            # Some of the spend is not in the row: the lock and the reservation stay.
            self.keep_lock_if_unaccounted(run_id)
            return row
        # The spend is in costs.csv now: the reservation stops counting against the ARC
        # stream (PREREG §12). After the record, so a run starting in between counts this
        # spend twice, not never.
        self._release_reservation()
        return row

    def _release_reservation(self) -> None:
        """Remove this transport's spend reservation (`common.approval.reserve_spend`). If
        that fails it stays, counting against the ARC stream until the operator deletes it,
        and the next PersistGym run refuses and says so."""
        rid = getattr(self.approval, "reservation_id", "")
        if not rid:
            return
        try:
            paidlock.release_reservation(self.paid_lock.path, stream=self.paid_lock.stream,
                                         reservation_id=rid)
        except OSError as e:
            self.log.warning("could not remove the spend reservation %s: %s; delete it by "
                             "hand, its spend is in costs.csv",
                             paidlock.reservation_path(self.paid_lock.path,
                                                       self.paid_lock.stream), e)

    @property
    def unaccounted(self) -> bool:
        """Whether this run made calls whose costs.csv row has not been appended, or calls
        that were still in flight when it was finalized (`abandoned_calls`)."""
        return (self.ledger.n_calls > 0 and self.costs_row is None) or self.abandoned_calls > 0

    def keep_lock_if_unaccounted(self, run_id: str, cause: str = "") -> str | None:
        """If this run made calls that results/costs.csv does not show, keep the paid-run
        lock held with the reason (`common.paidlock.keep`), so that no paid run starts on an
        incomplete ledger, and return the reason; otherwise None. `finalize` calls it when
        the row cannot be written or calls were still in flight, and the CLI after every
        run, which also catches a run whose `finalize` never ran. The reason holds the run's
        usage totals (reasoning tokens withheld for a pilot-blinded experiment, PREREG §11),
        for the row to add by hand."""
        if not self.unaccounted:
            return None
        if self.kept_because is None:
            totals = self.ledger.totals()
            if blinding.is_blinded(self.approval.experiment):
                totals = blinding.blinded_tokens(totals)
            tag = spend_tag(self.approval.approved_block)
            what, todo = [], []
            if self.ledger.n_calls > 0 and self.costs_row is None:
                what.append(f"made {self.ledger.n_calls} paid calls that "
                            f"{self.approval.costs_path} does not show"
                            + (f" ({cause})" if cause else ""))
                todo.append(f"add its row by hand, with {tag} at the start of its notes and "
                            f"these totals: {json.dumps(totals)}")
            if self.abandoned_calls:
                what.append(f"still had {self.abandoned_calls} paid calls in flight when it "
                            "ended (episodes played in parallel, stopped without waiting "
                            "for them), whose usage is in neither costs.csv nor the raw "
                            "transcript")
                todo.append("append a row by hand for those calls, from the provider's "
                            f"usage page, with {tag} at the start of its notes")
            self.kept_because = (
                f"run {run_id} ({self.approval.experiment}, {self.model}) "
                + " and ".join(what) + ": " + "; ".join(todo)
                + "; the run's files are under results/ and results/raw/. Then delete this "
                f"lock file and the run's spend reservation "
                f"{paidlock.reservation_path(self.paid_lock.path, self.paid_lock.stream)}")
            paidlock.keep(self.paid_lock.path, self.paid_lock.info, self.kept_because)
        return self.kept_because
