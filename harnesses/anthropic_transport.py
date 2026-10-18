"""Paid calls to Anthropic's Messages API (claude-haiku-5-5; PREREG §17.8, amendment R8, not
yet merged). Guarded exactly as the OpenAI transport is.

`AnthropicMessagesTransport` is a `harnesses.paid_transport.PaidTransport`: the same guard
before any client exists (the paid-run lock, PERSISTGYM_ALLOW_PAID=1, the approval line on
origin/main, the frozen PREREG, the caps and the spend reservation;
harnesses/openai_transport.py's module docstring), the same git state, ledger, stop at the
planned spend, costs row, `finalize` and kept lock. It differs in:

* **Credentials** (CLAUDE.md: reported runs use API keys, never subscriptions). Before the
  guard it refuses (`credential_refusal`) unless `ANTHROPIC_API_KEY` is set and
  `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_PROFILE` and `ANTHROPIC_BASE_URL` are not: the SDK falls
  back from an API key to an OAuth token and to a stored profile, and a base URL would send
  the calls elsewhere. It checks only that the key's variable is set and not empty; the SDK
  reads the key from the environment itself, and this module never keeps, prints, logs or
  passes on its value.
* **The request-side check.** Before each call the body must pass
  `harnesses.wire.MessagesWire.check_payload` with the model's registered effort and D13's
  32,000 cap: adaptive thinking, exactly the fields the wire sends, no thinking block in the
  history. A body that fails raises `RequestCheckFailed` and is never sent. The Messages API
  echoes neither the effort nor a reasoning context, so this check stands in for the echo
  checks; the echo log records both as None and the costs row's mismatch counts as `n/a`.
* **The call.** `client.messages.stream(**payload).get_final_message()`: the SDK refuses a
  non-streaming request with `max_tokens` 32,000 at its default timeout. The client is built
  with `max_retries=0` and the transport's timeout, so every attempt is visible.
* **Retries.** 429 (after its `retry-after` seconds when the header gives them, else the
  backoff), 500, 502, 503, 504 and 529 (overloaded), the same errors arriving as an error
  event inside a stream, timeouts and dropped connections, with the transport's exponential
  backoff; never another 4xx. Two errors stop the run instead (`ProviderHardStop`, which the
  runner does not catch): a 429 with `error_code` `enforced_spend_limit_reached` (the
  organization's monthly spend cap; retries fail until the next month) and a 400 for a usage
  limit set in the Console. A timed-out or dropped call, or a stream that failed part way,
  may still have been billed; such attempts are not in the ledger.
* **What it logs** per response: the returned model, `stop_reason`, the tier served
  (`usage.service_tier`, with a warning if it is not `standard`, which is what the prices
  assume), the prompt size (with a warning above the price's 100,000-token threshold, whose
  card is five times dearer), and a warning for an incomplete response (`max_tokens`, a
  refusal with its category, an unexpected stop reason). For a blinded pilot (PREREG §11)
  neither the status nor `stop_reason` is logged.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import anthropic

from harnesses.config import DEFAULT_MAX_OUTPUT_TOKENS
from harnesses.paid_transport import (
    NOT_ECHOED,
    BudgetExceeded,
    PaidCallsNotAllowed,
    PaidTransport,
    ProviderHardStop,
)
from harnesses.pricing import price_for
from harnesses.registered import registered_effort
from harnesses.wire import MESSAGES, MESSAGES_SERVICE_TIER

__all__ = ["AnthropicMessagesTransport", "BudgetExceeded", "ProviderHardStop",
           "credential_refusal", "retry_decision"]

log = logging.getLogger("harnesses.anthropic")

KEY_ENV = "ANTHROPIC_API_KEY"
"""The only credential a Messages run may use: an API key, read by the SDK itself."""
REFUSED_ENV = ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE", "ANTHROPIC_BASE_URL")
"""Set, any of these would make the SDK authenticate otherwise (an OAuth token, a stored
profile) or send the calls elsewhere (a base URL): each refuses."""
RETRY_STATUSES = (429, 500, 502, 503, 504, 529)
STREAM_ERROR_STATUS = {"rate_limit_error": 429, "api_error": 500, "timeout_error": 504,
                       "overloaded_error": 529}
"""An error event inside a stream (an `APIStatusError` on the stream's 200 response) by its
error type, read as the status it stands for."""
SPEND_LIMIT_CODE = "enforced_spend_limit_reached"


def credential_refusal(environ: Mapping[str, str] | None = None) -> str | None:
    """Why the environment's credentials refuse a Messages call, or None: an API key must be
    set (a non-empty `ANTHROPIC_API_KEY`) and none of `REFUSED_ENV` may be. The reason names
    variables only: no value is returned, printed or kept."""
    env = os.environ if environ is None else environ
    if not env.get(KEY_ENV):
        return (f"{KEY_ENV} is not set: a paid Messages run uses an API key from the "
                f"environment (CLAUDE.md; load it with `uv run --env-file .env ...`)")
    found = [name for name in REFUSED_ENV if name in env]
    if found:
        return (f"{', '.join(found)} {'is' if len(found) == 1 else 'are'} set: a paid "
                f"Messages run authenticates with {KEY_ENV} only, never an OAuth token or a "
                "stored profile (CLAUDE.md: API keys, never subscriptions), and calls the API's "
                "own address; unset them for this command")
    return None


def _error_code(error: anthropic.APIStatusError) -> str | None:
    body = error.body if isinstance(error.body, dict) else {}
    err = body.get("error") if isinstance(body.get("error"), dict) else {}
    details = err.get("details") if isinstance(err.get("details"), dict) else {}
    return details.get("error_code") or err.get("error_code") or body.get("error_code")


def _retry_after(error: anthropic.APIStatusError) -> float | None:
    try:
        seconds = float(error.response.headers.get("retry-after"))
    except (TypeError, ValueError):
        return None
    return max(seconds, 0.0)


def retry_decision(error: Exception) -> tuple[str, float | None]:
    """How the transport treats one failed attempt: ("retry", the `retry-after` seconds or
    None for the backoff), ("raise", None) to raise it now, or ("hard_stop", None) for a
    provider-side spend or usage limit (module docstring)."""
    if isinstance(error, anthropic.APIConnectionError):  # timeouts included
        return "retry", None
    if not isinstance(error, anthropic.APIStatusError):
        return "raise", None
    status = error.status_code
    if status == 200:  # an error event inside a stream
        status = STREAM_ERROR_STATUS.get(error.type or "", 200)
    if status == 429 and (_error_code(error) == SPEND_LIMIT_CODE
                          or SPEND_LIMIT_CODE in str(error)):
        return "hard_stop", None
    if status == 400 and "usage limit" in str(error).lower():
        return "hard_stop", None
    if status in RETRY_STATUSES:
        return "retry", _retry_after(error) if status == 429 else None
    return "raise", None


@dataclass
class AnthropicMessagesTransport(PaidTransport):
    """Paid calls to Anthropic's Messages API (module docstring)."""

    log = log

    def _preflight(self) -> None:
        why = credential_refusal()
        if why:
            raise PaidCallsNotAllowed(f"{why}; no paid call was made")

    def _default_client(self, timeout_s: float) -> Any:
        # max_retries=0: retries are handled by the transport so that every attempt is visible.
        return anthropic.Anthropic(max_retries=0, timeout=timeout_s)

    def _check_request(self, payload: dict) -> None:
        MESSAGES.check_payload(payload, effort=registered_effort(self.model),
                               max_tokens=DEFAULT_MAX_OUTPUT_TOKENS)

    def _call(self, client: Any, payload: dict) -> dict:
        with client.messages.stream(**payload) as stream:
            message = stream.get_final_message()
        # to_dict: the keys the API returned (exclude_unset), JSON types only.
        return message.to_dict(mode="json")

    def _retry_wait(self, error: Exception, attempt: int) -> float | None:
        what, after = retry_decision(error)
        if what == "hard_stop":
            raise ProviderHardStop(
                f"the provider refuses further spend ({type(error).__name__}: {error}); the "
                "run stops here, and no call is retried") from error
        if what != "retry":
            return None
        return after if after is not None else self.backoff_s * 2 ** (attempt - 1)

    def _echo_record(self, payload: dict, data: dict) -> dict:
        status, reason = MESSAGES.status(data)
        return {
            "requested_context": None, "echoed_context": None,
            "requested_effort": (payload.get("output_config") or {}).get("effort"),
            "echoed_effort": None,
            "model_returned": data.get("model"),
            "service_tier_requested": MESSAGES_SERVICE_TIER,
            "service_tier_returned": MESSAGES.served_tier(data),
            "status": status,
            "incomplete_reason": reason,
            "stop_reason": data.get("stop_reason"),
            "prompt_tokens": MESSAGES.usage(data)["input_tokens"],
        }

    def _mismatches(self) -> tuple[int | str, int | str]:
        return NOT_ECHOED, NOT_ECHOED

    def _log_response(self, echo: dict, payload: dict, blinded: bool) -> None:
        log.info("model=%s tier=%s prompt_tokens=%s stop_reason=%s status=%s",
                 echo["model_returned"], echo["service_tier_returned"], echo["prompt_tokens"],
                 "withheld" if blinded else echo["stop_reason"],
                 "withheld" if blinded else echo["status"])
        if echo["service_tier_returned"] != MESSAGES_SERVICE_TIER:
            log.warning("served on tier %s, not %s: priced at the standard tier's prices",
                        echo["service_tier_returned"], MESSAGES_SERVICE_TIER)
        threshold = price_for(self.model).long_threshold
        if threshold is not None and echo["prompt_tokens"] > threshold:
            log.warning("prompt of %d tokens is over %d: priced at the dearer card",
                        echo["prompt_tokens"], threshold)
        if echo["status"] == "incomplete" and not blinded:
            # D13: the caller scores it as an invalid action
            log.warning("incomplete response (reason=%s, max_tokens=%s)",
                        echo["incomplete_reason"], payload.get("max_tokens"))
