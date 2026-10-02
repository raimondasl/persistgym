"""The only code in harnesses/ that can make a paid API call. It is guarded.

`OpenAIResponsesTransport` refuses to exist, before it builds any client, unless every check
of the shared guard passes (`common.approval.require_paid_run`, which the ARC launcher runs
too, and `require_paid_approval`, which document them): it holds the PersistGym stream's
paid-run lock (`common.paidlock`, taken by harnesses/cli.py before these checks: one
PersistGym paid run at a time, beside at most one ARC run; PREREG §0.3 line 15) and its
experiment is a PersistGym one; this checkout's results/costs.csv holds the row of each
stream's last paid run; no hold stands (a paid run,
ARC or PersistGym, that ended COST_CAP or passed its run guard and that the researcher has
not cleared with a merged line `cleared_hold: <run_id>`, common/hold.py);
PERSISTGYM_ALLOW_PAID=1;
`--approved-block <name>`; PREREG.md committed, identical to PREREG.md on origin/main and
frozen (PLAN §16.3; a release version of at least 0.2 and a "Frozen" status line,
common/prereg.py); a positive, finite planned spend; and the researcher's approval line

    approved_block: <name> | experiments: <exp1>,<exp2>,... | max_usd: <amount>

in results/decisions.md on origin/main (fetched now), in HEAD and in the working tree,
listing this run's experiment, with block spend + planned spend <= max_usd and room under
the phase cap (PLAN §12, §16.2), counting the planned spend a running ARC run has reserved in
the same block or phase. Its own planned spend is then reserved, so an ARC run that starts
while it runs counts it too (`common.approval.reserve_spend`, PREREG §12).

The costs.csv row's notes start with `common.approval.spend_tag(<name>)`
("approved_block=<name>;"), which is how the guard sums a block's spend.

While running it stops before a call once the run's spend reaches the planned spend. Spend is
measured as block spend and the phase caps measure it (`common.approval.spend_usd`: the
billed estimate, so the Flex price on Flex; PLAN's caps are in billed dollars, D23). `send`
may be called from several threads at once, by a run playing episodes in parallel
(harnesses/parallel.py, PREREG §4.6): the check, the ledger and the echo log change under one
lock, so the stop stays exact on the spend recorded so far, and each thread gets its own
client from the factory. The calls already sent when the stop fires still complete, so on its
own the stop would let such a run end above its planned spend by up to one call per episode
in flight; the parallel run's per-call gate (`harnesses.parallel.CallGate`) lets calls
overlap only while the most they can all cost fits, so it ends at most one call above, as a
sequential run can. The
runner records that stop as `COST_CAP`, but it is the planned spend, not a per-run cost guard
(PREREG §7.7's hold is about the ARC run guard), so it places no hold; a per-run guard, if
one is ever added here, must place one (`common.hold.place_hold`). It logs
every response's echoed `reasoning.context` and `reasoning.effort` (the row's notes count the
mismatches of each), returned model string and served service tier,
and `finalize` appends exactly one results/costs.csv row via `common.costs.append_row`, with
both the list cost and the billed estimate. A response whose returned model string has no
price is still logged, priced as the requested model and flagged in the row's notes. For a
pilot-blinded experiment (`harnesses.blinding`, PREREG §11) the row's `reasoning_tokens` is
left empty; the per-call values stay in the raw transcript under results/raw/.

After appending the row, `finalize` records the run next to the lock as the PersistGym
stream's last paid run (`common.paidlock.record_last_run`), then removes its spend
reservation (as it does for a run that made no call). A run that made calls whose row is not
in costs.csv (the row could not be built or written, or `finalize` never ran) keeps the lock
held with the reason and its usage totals (`keep_lock_if_unaccounted`; the CLI calls it after
every run), so no PersistGym paid run starts on an incomplete ledger until the row is added
by hand, and keeps its reservation, which goes on counting against ARC runs until it is
deleted by hand. So does a run finalized while calls were still in flight (a parallel run
whose episodes were abandoned by a second Ctrl+C): those calls are never recorded.

The OpenAI SDK reads its API key from the environment itself; this module never reads, prints
or stores a key. Load keys with `uv run --env-file .env ...`.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openai

from common import costs, paidlock, runmeta
from common.approval import (
    ALLOW_ENV,
    MAIN,
    PaidApproval,
    PaidCallsNotAllowed,
    RemoteRef,
    require_paid_approval,
    require_paid_run,
    spend_tag,
    spend_usd,
)
from harnesses import blinding
from harnesses.pricing import UsageLedger, price_for

# The guard lives in common/approval.py; its names are re-exported here for the CLI and tests.
__all__ = ["ALLOW_ENV", "BudgetExceeded", "OpenAIResponsesTransport", "PaidApproval",
           "PaidCallsNotAllowed", "require_paid_approval", "require_paid_run"]

log = logging.getLogger("harnesses.openai")


class BudgetExceeded(RuntimeError):
    pass


def _default_client(timeout_s: float) -> Any:
    # max_retries=0: retries are handled below so that every attempt is visible.
    return openai.OpenAI(timeout=timeout_s, max_retries=0)


RETRYABLE = (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError,
             openai.InternalServerError)


@dataclass
class OpenAIResponsesTransport:
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
    paid: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        # Guard first: nothing below runs without approval.
        self.approval = require_paid_run(
            lock=self.paid_lock, approved_block=self.approved_block,
            experiment=self.experiment, planned_usd=self.planned_usd,
            costs_path=self.costs_path, repo=self.repo, remote=self.approval_remote)
        price_for(self.model)  # refuse a model we cannot cost
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
        self._client = (self.client_factory or _default_client)(self.timeout_s)
        self._clients = threading.local()
        self._clients.client = self._client

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
                                             or _default_client)(self.timeout_s)
        return client

    # ------------------------------------------------------------------
    def send(self, payload: dict) -> dict:
        """One call, with retries. Safe to call from several threads at once: the stop at the
        planned spend is checked, under the lock, on the spend of every call recorded so
        far, so it stays exact; calls already sent when it fires still complete and are
        recorded."""
        counted = False
        try:
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
                    # to_dict: the keys the API returned (exclude_unset), JSON types only.
                    data = client.responses.create(**payload).to_dict(mode="json")
                    break
                except RETRYABLE as e:
                    if (getattr(e, "code", None) == "insufficient_quota"
                            or attempt == self.max_attempts):
                        raise
                    wait = self.backoff_s * 2 ** (attempt - 1)
                    log.warning("attempt %d failed (%s); retrying in %.0fs", attempt,
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
            listed, billed = self.ledger.add(data, requested_tier=payload.get("service_tier"),
                                             latency_s=latency)
            echo = {
                "requested_context": (payload.get("reasoning") or {}).get("context"),
                "echoed_context": (data.get("reasoning") or {}).get("context"),
                "requested_effort": (payload.get("reasoning") or {}).get("effort"),
                "echoed_effort": (data.get("reasoning") or {}).get("effort"),
                "model_returned": data.get("model"),
                "service_tier_requested": payload.get("service_tier"),
                "service_tier_returned": data.get("service_tier"),
                "status": data.get("status"),
                "incomplete_reason": (data.get("incomplete_details") or {}).get("reason"),
                "latency_s": latency,
                "cost_usd_list": listed, "cost_usd_billed_est": billed,
            }
            self.echo_log.append(echo)
        log.info("model=%s reasoning.context requested=%s echoed=%s reasoning.effort "
                 "requested=%s echoed=%s tier=%s status=%s", echo["model_returned"],
                 echo["requested_context"], echo["echoed_context"], echo["requested_effort"],
                 echo["echoed_effort"], echo["service_tier_returned"], echo["status"])
        if echo["status"] == "incomplete":
            # D13: the caller scores it (an invalid action at a step; a retry for a summary)
            log.warning("incomplete response (reason=%s, max_output_tokens=%s)",
                        echo["incomplete_reason"], payload.get("max_output_tokens"))
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
            log.warning("%d calls were still in flight when the run was finalized; their "
                        "usage is not recorded", self.abandoned_calls)
        if self.ledger.n_calls == 0:
            if self.abandoned_calls:
                self.keep_lock_if_unaccounted(run_id)
            else:
                self._release_reservation()      # spent nothing
            return None
        try:
            mismatches = sum(1 for e in self.echo_log
                             if e["requested_context"] != e["echoed_context"])
            effort_mismatches = sum(1 for e in self.echo_log
                                    if e["requested_effort"] != e["echoed_effort"])
            git = runmeta.git_state()  # the commit of the code that made the calls
            row = self.ledger.costs_row(
                timestamp_utc=runmeta.utc_now(), run_id=run_id, milestone=milestone,
                experiment=self.approval.experiment, cell_or_config=cell_or_config,
                git_commit=git["git_commit"],
                notes=(f"{spend_tag(self.approval.approved_block)} "
                       f"context_mismatches={mismatches}; "
                       f"effort_mismatches={effort_mismatches}; git_dirty={git['git_dirty']}"
                       + (f"; {notes}" if notes else "")))
            if blinding.is_blinded(self.approval.experiment):
                # PREREG §11: no per-arm reasoning tokens from pilot data in committed files.
                # The per-call values stay in the raw transcript (results/raw/, gitignored).
                row["reasoning_tokens"] = ""
                row["notes"] = f"{row['notes']}; {blinding.WITHHELD_NOTE}"
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
            log.warning("could not record the last paid run next to %s: %s",
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
            log.warning("could not remove the spend reservation %s: %s; delete it by hand, "
                        "its spend is in costs.csv",
                        paidlock.reservation_path(self.paid_lock.path, self.paid_lock.stream),
                        e)

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
