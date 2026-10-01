"""The only code in harnesses/ that can make a paid API call. It is guarded.

`OpenAIResponsesTransport` refuses to exist, before it builds any client, unless every check
of the shared guard passes (`common.approval.require_paid_approval`, which documents them):
PERSISTGYM_ALLOW_PAID=1; `--approved-block <name>`; PREREG.md committed (PLAN §16.3); a
positive, finite planned spend; and the researcher's approval line

    approved_block: <name> | experiments: <exp1>,<exp2>,... | max_usd: <amount>

in results/decisions.md on origin/main (fetched now), in HEAD and in the working tree,
listing this run's experiment, with block spend + planned spend <= max_usd and room under
the phase cap (PLAN §12, §16.2).

The costs.csv row's notes start with `common.approval.spend_tag(<name>)`
("approved_block=<name>;"), which is how the guard sums a block's spend.

While running it stops before a call once the run's estimated billed cost reaches the planned
spend, logs every response's echoed `reasoning.context`, returned model string and served
service tier, and `finalize` appends exactly one results/costs.csv row via
`common.costs.append_row`. A response whose returned model string has no price is still
logged, priced as the requested model and flagged in the row's notes. For a pilot-blinded
experiment (`harnesses.blinding`, PREREG §11) the row's `reasoning_tokens` is left empty; the
per-call values stay in the raw transcript under results/raw/.

The OpenAI SDK reads its API key from the environment itself; this module never reads, prints
or stores a key. Load keys with `uv run --env-file .env ...`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openai

from common import costs, runmeta
from common.approval import (
    ALLOW_ENV,
    MAIN,
    PaidApproval,
    PaidCallsNotAllowed,
    RemoteRef,
    require_paid_approval,
    spend_tag,
)
from harnesses import blinding
from harnesses.pricing import UsageLedger, price_for

# The guard lives in common/approval.py; its names are re-exported here for the CLI and tests.
__all__ = ["ALLOW_ENV", "BudgetExceeded", "OpenAIResponsesTransport", "PaidApproval",
           "PaidCallsNotAllowed", "require_paid_approval"]

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
        self.approval = require_paid_approval(
            approved_block=self.approved_block, experiment=self.experiment,
            planned_usd=self.planned_usd, costs_path=self.costs_path, repo=self.repo,
            remote=self.approval_remote)
        price_for(self.model)  # refuse a model we cannot cost
        self.ledger = UsageLedger(self.model)
        self.echo_log: list[dict] = []
        self._finalized = False
        self._client = (self.client_factory or _default_client)(self.timeout_s)

    # ------------------------------------------------------------------
    def send(self, payload: dict) -> dict:
        if self._finalized:
            raise RuntimeError("transport already finalized")
        if payload.get("model") != self.model:
            raise ValueError(f"payload model {payload.get('model')!r} != {self.model!r}")
        if self.ledger.cost_usd_billed_est >= self.approval.planned_usd:
            raise BudgetExceeded(
                f"run spend ${self.ledger.cost_usd_billed_est:.4f} reached the planned "
                f"${self.approval.planned_usd:.2f}")
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
        """Append this run's costs.csv row (once). Returns the row, or None if no call was
        made."""
        if self._finalized:
            return None
        self._finalized = True
        if self.ledger.n_calls == 0:
            return None
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
        return row
