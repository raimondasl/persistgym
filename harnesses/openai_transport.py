"""The only code in harnesses/ that can make a paid API call. It is guarded.

`OpenAIResponsesTransport` refuses to exist, before it builds any client, unless every check
of the shared guard passes (`common.approval.require_paid_run`, which the ARC launcher runs
too, and `require_paid_approval`, which document them): it holds the paid-run lock
(`common.paidlock`, taken by harnesses/cli.py before these checks: one paid run at a time);
this checkout's results/costs.csv holds the last paid run's row; PERSISTGYM_ALLOW_PAID=1;
`--approved-block <name>`; PREREG.md committed, identical to PREREG.md on origin/main and
frozen (PLAN §16.3; a release version of at least 0.2 and a "Frozen" status line,
common/prereg.py); a positive, finite planned spend; and the researcher's approval line

    approved_block: <name> | experiments: <exp1>,<exp2>,... | max_usd: <amount>

in results/decisions.md on origin/main (fetched now), in HEAD and in the working tree,
listing this run's experiment, with block spend + planned spend <= max_usd and room under
the phase cap (PLAN §12, §16.2).

The costs.csv row's notes start with `common.approval.spend_tag(<name>)`
("approved_block=<name>;"), which is how the guard sums a block's spend.

While running it stops before a call once the run's spend reaches the planned spend. Spend is
measured as block spend and the phase caps measure it (`common.approval.spend_usd`: the
billed estimate, so the Flex price on Flex; PLAN's caps are in billed dollars, D23). It logs
every response's echoed `reasoning.context`, returned model string and served service tier,
and `finalize` appends exactly one results/costs.csv row via `common.costs.append_row`, with
both the list cost and the billed estimate. A response whose returned model string has no
price is still logged, priced as the requested model and flagged in the row's notes. For a
pilot-blinded experiment (`harnesses.blinding`, PREREG §11) the row's `reasoning_tokens` is
left empty; the per-call values stay in the raw transcript under results/raw/.

After appending the row, `finalize` records the run next to the lock as the last paid run
(`common.paidlock.record_last_run`). A run that made calls whose row is not in costs.csv
(the row could not be built or written, or `finalize` never ran) keeps the lock held with the
reason and its usage totals (`keep_lock_if_unaccounted`; the CLI calls it after every run),
so no paid run starts on an incomplete ledger until the row is added by hand.

The OpenAI SDK reads its API key from the environment itself; this module never reads, prints
or stores a key. Load keys with `uv run --env-file .env ...`.
"""

from __future__ import annotations

import json
import logging
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
        self._client = (self.client_factory or _default_client)(self.timeout_s)

    @property
    def spent_usd(self) -> float:
        """This run's spend so far, measured as block spend and the phase caps measure it
        (`common.approval.spend_usd`: the billed estimate, the Flex price on Flex). The run
        stops before a call once it reaches the planned spend, so the guard's check `block
        spend + planned <= max_usd` holds after the run too, up to the last call's cost."""
        return spend_usd(self.ledger.cost_usd_list, self.ledger.cost_usd_billed_est)

    # ------------------------------------------------------------------
    def send(self, payload: dict) -> dict:
        if self._finalized:
            raise RuntimeError("transport already finalized")
        if payload.get("model") != self.model:
            raise ValueError(f"payload model {payload.get('model')!r} != {self.model!r}")
        if self.spent_usd >= self.approval.planned_usd:
            raise BudgetExceeded(
                f"run spend ${self.spent_usd:.4f} (billed estimate) "
                f"reached the planned ${self.approval.planned_usd:.2f}")
        started = time.monotonic()
        for attempt in range(1, self.max_attempts + 1):
            try:
                # to_dict: the keys the API returned (exclude_unset), JSON types only.
                data = self._client.responses.create(**payload).to_dict(mode="json")
                break
            except RETRYABLE as e:
                if getattr(e, "code", None) == "insufficient_quota" or attempt == self.max_attempts:
                    raise
                wait = self.backoff_s * 2 ** (attempt - 1)
                log.warning("attempt %d failed (%s); retrying in %.0fs", attempt,
                            type(e).__name__, wait)
                self.sleep(wait)
        latency = time.monotonic() - started
        listed, billed = self.ledger.add(data, requested_tier=payload.get("service_tier"),
                                         latency_s=latency)
        echo = {
            "requested_context": (payload.get("reasoning") or {}).get("context"),
            "echoed_context": (data.get("reasoning") or {}).get("context"),
            "model_returned": data.get("model"),
            "service_tier_requested": payload.get("service_tier"),
            "service_tier_returned": data.get("service_tier"),
            "latency_s": latency,
            "cost_usd_list": listed, "cost_usd_billed_est": billed,
        }
        self.echo_log.append(echo)
        log.info("model=%s reasoning.context requested=%s echoed=%s tier=%s",
                 echo["model_returned"], echo["requested_context"], echo["echoed_context"],
                 echo["service_tier_returned"])
        return data

    def finalize(self, *, run_id: str, milestone: str, cell_or_config: str,
                 notes: str = "") -> dict | None:
        """Append this run's costs.csv row (once) and record the run next to the paid-run
        lock as the last paid run. Returns the row, or None if no call was made. If the row
        cannot be built or written, keeps the lock held with the reason
        (`keep_lock_if_unaccounted`) and raises."""
        if self._finalized:
            return None
        self._finalized = True
        if self.ledger.n_calls == 0:
            return None
        try:
            mismatches = sum(1 for e in self.echo_log
                             if e["requested_context"] != e["echoed_context"])
            git = runmeta.git_state()  # the commit of the code that made the calls
            row = self.ledger.costs_row(
                timestamp_utc=runmeta.utc_now(), run_id=run_id, milestone=milestone,
                experiment=self.approval.experiment, cell_or_config=cell_or_config,
                git_commit=git["git_commit"],
                notes=(f"{spend_tag(self.approval.approved_block)} "
                       f"context_mismatches={mismatches}; git_dirty={git['git_dirty']}"
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
            paidlock.record_last_run(self.paid_lock.path, run_id=run_id,
                                     costs_csv=self.approval.costs_path,
                                     timestamp_utc=row["timestamp_utc"])
        except OSError as e:
            log.warning("could not record the last paid run next to %s: %s",
                        self.paid_lock.path, e)
        return row

    @property
    def unaccounted(self) -> bool:
        """Whether this run made calls whose costs.csv row has not been appended."""
        return self.ledger.n_calls > 0 and self.costs_row is None

    def keep_lock_if_unaccounted(self, run_id: str, cause: str = "") -> str | None:
        """If this run made calls that results/costs.csv does not show, keep the paid-run
        lock held with the reason (`common.paidlock.keep`), so that no paid run starts on an
        incomplete ledger, and return the reason; otherwise None. `finalize` calls it when
        the row cannot be written, and the CLI after every run, which also catches a run
        whose `finalize` never ran. The reason holds the run's usage totals (reasoning tokens
        withheld for a pilot-blinded experiment, PREREG §11), for the row to add by hand."""
        if not self.unaccounted:
            return None
        if self.kept_because is None:
            totals = self.ledger.totals()
            if blinding.is_blinded(self.approval.experiment):
                totals = blinding.blinded_tokens(totals)
            self.kept_because = (
                f"run {run_id} ({self.approval.experiment}, {self.model}) made "
                f"{self.ledger.n_calls} paid calls that {self.approval.costs_path} does not "
                f"show" + (f" ({cause})" if cause else "")
                + f": add its row by hand, with {spend_tag(self.approval.approved_block)} at "
                f"the start of its notes and these totals: {json.dumps(totals)}; the run's "
                f"files are under results/ and results/raw/. Then delete this lock file")
            paidlock.keep(self.paid_lock.path, self.paid_lock.info, self.kept_because)
        return self.kept_because
