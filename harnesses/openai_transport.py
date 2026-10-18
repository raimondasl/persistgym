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
left empty, and no call's status is logged (no warning per incomplete response); the per-call
values stay in the raw transcript under results/raw/.

The git state of the code is read once, when the transport is built, after the guard and
before any call (`git`, `common.runmeta.git_state`), and `finalize` uses that value: no process
is started between the first paid call and the row (common/runmeta.py says why). The runner
uses it for meta.json too.

After appending the row, `finalize` records the run next to the lock as the PersistGym
stream's last paid run (`common.paidlock.record_last_run`), then removes its spend
reservation (as it does for a run that made no call). A run that made calls whose row is not
in costs.csv (the row could not be built or written, or `finalize` never ran) keeps the lock
held with the reason and its usage totals (`keep_lock_if_unaccounted`; the CLI calls it after
every run), so no PersistGym paid run starts on an incomplete ledger until the row is added
by hand, and keeps its reservation, which goes on counting against ARC runs until it is
deleted by hand. So does a run finalized while calls were still in flight (a parallel run
whose episodes were abandoned by a second Ctrl+C): those calls are never recorded. For a
`run` whose row could not be written, `harnesses account-run` (harnesses/account.py) adds the
row from the run's raw files, as `finalize` would have written it (`build_costs_row`), and
releases the lock and the reservation.

The shared machinery (the guard, the ledger, the stop, the retry loop, `finalize` and the
kept lock) is `harnesses.paid_transport.PaidTransport`, which the Anthropic transport
(harnesses/anthropic_transport.py) shares; this module fills in OpenAI's client, call,
retries and echo log.

The OpenAI SDK reads its API key from the environment itself; this module never reads, prints
or stores a key. Load keys with `uv run --env-file .env ...`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import openai

from common.approval import (
    ALLOW_ENV,
    PaidApproval,
    PaidCallsNotAllowed,
    require_paid_approval,
    require_paid_run,
)
from harnesses.paid_transport import BudgetExceeded, PaidTransport, build_costs_row

# The guard lives in common/approval.py; its names are re-exported here for the CLI and tests.
__all__ = ["ALLOW_ENV", "BudgetExceeded", "OpenAIResponsesTransport", "PaidApproval",
           "PaidCallsNotAllowed", "build_costs_row", "require_paid_approval",
           "require_paid_run"]

log = logging.getLogger("harnesses.openai")


def _default_client(timeout_s: float) -> Any:
    # max_retries=0: retries are handled by the transport so that every attempt is visible.
    return openai.OpenAI(timeout=timeout_s, max_retries=0)


RETRYABLE = (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError,
             openai.InternalServerError)


@dataclass
class OpenAIResponsesTransport(PaidTransport):
    """Paid calls to OpenAI's Responses API (module docstring)."""

    log = log

    def _default_client(self, timeout_s: float) -> Any:
        return _default_client(timeout_s)

    def _call(self, client: Any, payload: dict) -> dict:
        # to_dict: the keys the API returned (exclude_unset), JSON types only.
        return client.responses.create(**payload).to_dict(mode="json")

    def _retry_wait(self, error: Exception, attempt: int) -> float | None:
        """429s, timeouts, dropped connections and 5xx errors, with exponential backoff;
        never `insufficient_quota`."""
        if not isinstance(error, RETRYABLE) or getattr(error, "code", None) == "insufficient_quota":
            return None
        return self.backoff_s * 2 ** (attempt - 1)

    def _echo_record(self, payload: dict, data: dict) -> dict:
        return {
            "requested_context": (payload.get("reasoning") or {}).get("context"),
            "echoed_context": (data.get("reasoning") or {}).get("context"),
            "requested_effort": (payload.get("reasoning") or {}).get("effort"),
            "echoed_effort": (data.get("reasoning") or {}).get("effort"),
            "model_returned": data.get("model"),
            "service_tier_requested": payload.get("service_tier"),
            "service_tier_returned": data.get("service_tier"),
            "status": data.get("status"),
            "incomplete_reason": (data.get("incomplete_details") or {}).get("reason"),
        }

    def _log_response(self, echo: dict, payload: dict, blinded: bool) -> None:
        log.info("model=%s reasoning.context requested=%s echoed=%s reasoning.effort "
                 "requested=%s echoed=%s tier=%s status=%s", echo["model_returned"],
                 echo["requested_context"], echo["echoed_context"], echo["requested_effort"],
                 echo["echoed_effort"], echo["service_tier_returned"],
                 "withheld" if blinded else echo["status"])
        if echo["status"] == "incomplete" and not blinded:
            # D13: the caller scores it (an invalid action at a step; a retry for a summary)
            log.warning("incomplete response (reason=%s, max_output_tokens=%s)",
                        echo["incomplete_reason"], payload.get("max_output_tokens"))
