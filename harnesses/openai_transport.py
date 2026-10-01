"""The only code in harnesses/ that can make a paid API call. It is guarded.

`OpenAIResponsesTransport` refuses to exist unless ALL of these hold (`require_paid_approval`):
1. the environment variable PERSISTGYM_ALLOW_PAID is exactly "1";
2. an approved spending block name is given (`--approved-block <name>`; the researcher's
   approval is recorded in results/decisions.md, PLAN §16.2);
3. PREREG.md exists (PLAN §16.3: PREREG before any paid call);
4. the experiment maps to a budget phase in common/costs.py and the phase cap minus the
   spend logged in results/costs.csv minus the planned spend of this run is >= 0
   (`common.costs.headroom`).

While running it stops before a call once the run's estimated billed cost reaches the planned
spend, logs every response's echoed `reasoning.context` and returned model string, and
`finalize` appends exactly one results/costs.csv row via `common.costs.append_row`.

The OpenAI SDK reads its API key from the environment itself; this module never reads, prints
or stores a key. Load keys with `uv run --env-file .env ...`.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openai

from common import costs, runmeta
from harnesses.pricing import UsageLedger, price_for

ALLOW_ENV = "PERSISTGYM_ALLOW_PAID"
log = logging.getLogger("harnesses.openai")


class PaidCallsNotAllowed(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class PaidApproval:
    approved_block: str
    experiment: str
    phase: str
    planned_usd: float
    headroom_usd: float
    prereg_version: str
    costs_path: Path


def require_paid_approval(*, approved_block: str | None, experiment: str, planned_usd: float,
                          costs_path: Path = costs.COSTS_CSV,
                          repo: Path = runmeta.REPO_ROOT) -> PaidApproval:
    if os.environ.get(ALLOW_ENV) != "1":
        raise PaidCallsNotAllowed(f"paid calls are off: set {ALLOW_ENV}=1 for an approved block")
    if not approved_block or not str(approved_block).strip():
        raise PaidCallsNotAllowed("paid calls need --approved-block <name> (PLAN §16.2)")
    phase = costs.phase_of(experiment)
    if phase not in costs.PHASE_CAPS:
        raise PaidCallsNotAllowed(f"experiment {experiment!r} has no budget phase in "
                                  "common/costs.py")
    if not planned_usd or planned_usd <= 0:
        raise PaidCallsNotAllowed("paid calls need a positive planned spend (--planned-usd)")
    prereg = runmeta.prereg_version(repo)
    if prereg is None:
        raise PaidCallsNotAllowed("PREREG.md must be committed before any paid call "
                                  "(PLAN §16.3)")
    room = costs.headroom(planned_usd, phase, costs.read_rows(costs_path))
    if room < 0:
        raise PaidCallsNotAllowed(
            f"planned ${planned_usd:.2f} would exceed the phase {phase} cap of "
            f"${costs.PHASE_CAPS[phase]:.0f} by ${-room:.2f}: stop and ask the researcher")
    return PaidApproval(str(approved_block).strip(), experiment, phase, float(planned_usd),
                        room, prereg, Path(costs_path))


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
    paid: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        # Guard first: nothing below runs without approval.
        self.approval = require_paid_approval(
            approved_block=self.approved_block, experiment=self.experiment,
            planned_usd=self.planned_usd, costs_path=self.costs_path, repo=self.repo)
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
        listed, billed = self.ledger.add(data)
        echo = {
            "requested_context": (payload.get("reasoning") or {}).get("context"),
            "echoed_context": (data.get("reasoning") or {}).get("context"),
            "model_returned": data.get("model"),
            "service_tier_returned": data.get("service_tier"),
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
            notes=(f"approved_block={self.approval.approved_block}; "
                   f"context_mismatches={mismatches}; git_dirty={git['git_dirty']}"
                   + (f"; {notes}" if notes else "")))
        costs.append_row(row, self.approval.costs_path)
        return row
