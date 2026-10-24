"""Paid calls to Anthropic's Messages API (claude-haiku-5-5; PREREG §17.8, amendment R8).
Guarded exactly as the OpenAI transport is.

`AnthropicMessagesTransport` is a `harnesses.paid_transport.PaidTransport`: the same guard
before any client exists (the paid-run lock, PERSISTGYM_ALLOW_PAID=1, the approval line on
origin/main, the frozen PREREG, the caps and the spend reservation;
harnesses/openai_transport.py's module docstring), the same git state, ledger, stop at the
planned spend, costs row, `finalize` and kept lock. It differs in:

* **Credentials** (CLAUDE.md: reported runs use API keys, never subscriptions). Before the
  guard it refuses (`credential_refusal`) unless `ANTHROPIC_API_KEY` is set and
  `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_PROFILE`, `ANTHROPIC_BASE_URL` and
  `ANTHROPIC_CUSTOM_HEADERS` are not: the SDK falls back from an API key to an OAuth token
  and to a stored profile, a base URL would send the calls elsewhere, and custom headers
  (which the SDK sends after its auth headers) could replace the key, add an OAuth
  `Authorization` header or an `anthropic-beta` flag the request-side check never sees. Once
  built, a client that holds any custom header refuses too (`client_header_refusal`). It
  checks only that the key's variable is set and not empty; the SDK reads the key from the
  environment itself, and this module never keeps, prints, logs or passes on its value.
* **The model and the approval** (R8, PREREG §17.8). Before the guard it refuses a
  model other than claude-haiku-5-5 (or a dated snapshot of it; `registered.model_family`).
  After the guard it refuses unless the approved block lists R8's experiment
  `persistgym_haiku` (`registered.HAIKU_EXPERIMENT`): only an approval line written for the
  Haiku replication covers its pilots and validity run too, never a block approved before
  it; the refusal releases the spend reservation. A run in R9's `persistgym_haiku_notes`
  (`registered.HAIKU_NOTES_EXPERIMENT`, PREREG §17.9) passes this check too. The general
  guard admits a run only in its block's own experiments, so R9's block funds that run alone,
  and a block approved for R9 never funds a run of R8's.
* **The request-side check.** Before each call the body must pass
  `harnesses.wire.MessagesWire.check_payload` with the model's registered effort and D13's
  32,000 cap: adaptive thinking, exactly the fields the wire sends, no thinking block in the
  history. A body that fails raises `RequestCheckFailed` and is never sent. The Messages API
  echoes neither the effort nor a reasoning context, so this check stands in for the echo
  checks; the echo log records both as None and the costs row's mismatch counts as `n/a`.
* **The call.** `client.messages.stream(**payload).get_final_message()`: the SDK refuses a
  non-streaming request with `max_tokens` 32,000 at its default timeout. The client is built
  with `max_retries=0` and the transport's timeout, so every attempt is visible. Once the
  200 headers have arrived the SDK reads the stream's body without wrapping its errors: a
  connection that drops or stalls part way raises an `httpx2.TransportError`
  (`RemoteProtocolError`, `ReadError`, `ReadTimeout`), which `_call` raises as an
  `anthropic.APIConnectionError`, and so does a stream that ended before its
  `message_delta` (a final message with no `stop_reason`), which would otherwise be scored
  as the model's invalid action. Both are then retried and, after the last attempt, end the
  episode `API_ERROR`, as any other API error; neither stops the run.
* **Retries.** 429 (after its `retry-after` seconds when the header gives them, else the
  backoff), 500, 502, 503, 504 and 529 (overloaded), the same errors arriving as an error
  event inside a stream, timeouts and dropped connections, with the transport's exponential
  backoff; never another 4xx. Two errors stop the run instead (`ProviderHardStop`, which the
  runner does not catch): a 429 with `error_code` `enforced_spend_limit_reached` (the
  organization's monthly spend cap; retries fail until the next month) and a 400 for a usage
  limit set in the Console. A stream that failed after `message_start` has already reported
  its usage (its input, cache reads and writes, and the output so far): the error carries
  the message so far (`paid_transport.PARTIAL_RESPONSE`) and the ledger records it as a
  failed attempt, in the spend and the costs row's totals (not in `n_calls`). A call that
  failed before `message_start` (a timeout, a connection error, an HTTP error) may still
  have been billed and is not in the ledger.
* **What it logs** per response: the returned model, `stop_reason`, the tier served
  (`usage.service_tier`, with a warning if it is not `standard`, which is what the prices
  assume), the inference geo served (`usage.inference_geo`, with a warning if it is not
  `global`: "us" costs 1.1x, and a geo not reported is priced so too), the prompt size
  (with a warning above the price's 100,000-token threshold, whose card is five times
  dearer), and a warning for an incomplete response (`max_tokens`, a refusal with its
  category, an unexpected stop reason). For a blinded pilot (PREREG §11) neither the status
  nor `stop_reason` is logged.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import anthropic
import httpx2

from harnesses import registered
from harnesses.config import DEFAULT_MAX_OUTPUT_TOKENS
from harnesses.paid_transport import (
    NOT_ECHOED,
    PARTIAL_RESPONSE,
    BudgetExceeded,
    PaidCallsNotAllowed,
    PaidTransport,
    ProviderHardStop,
)
from harnesses.pricing import price_for
from harnesses.registered import registered_effort
from harnesses.wire import MESSAGES, MESSAGES_SERVICE_TIER

__all__ = ["AnthropicMessagesTransport", "BudgetExceeded", "ProviderHardStop",
           "client_header_refusal", "credential_refusal", "retry_decision"]

log = logging.getLogger("harnesses.anthropic")

KEY_ENV = "ANTHROPIC_API_KEY"
"""The only credential a Messages run may use: an API key, read by the SDK itself."""
REFUSED_ENV = ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE", "ANTHROPIC_BASE_URL",
               "ANTHROPIC_CUSTOM_HEADERS")
"""Set, any of these would make the SDK authenticate otherwise (an OAuth token, a stored
profile, a custom header that replaces the key), send the calls elsewhere (a base URL) or
send headers the request-side check never sees (an `anthropic-beta` flag): each refuses."""
SERVED_GEO = "global"
"""The `usage.inference_geo` the listed prices assume ("us" costs 1.1x; `pricing.Price`)."""
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
                "stored profile (CLAUDE.md: API keys, never subscriptions), with the SDK's own "
                "headers only, and calls the API's own address; unset them for this command")
    return None


def client_header_refusal(client: Any) -> str | None:
    """Why a built SDK client refuses, or None: it must hold no custom header (the SDK's
    `_custom_headers`, sent after its auth headers on every request). The harness passes
    none, so any came from outside it (`ANTHROPIC_CUSTOM_HEADERS`, a stored profile) and
    could replace the API key or add headers the request-side check never sees. The reason
    names the headers only, never their values."""
    custom = getattr(client, "_custom_headers", None) or {}
    if not custom:
        return None
    return (f"the Anthropic client holds custom headers ({', '.join(sorted(custom))}): a paid "
            "Messages call sends the SDK's own headers only, with the API key")


def _partial(stream: Any) -> dict | None:
    """The message so far of a stream that failed, as JSON types, once `message_start` has
    reported its usage; None before (`paid_transport.PARTIAL_RESPONSE`)."""
    snapshot = getattr(stream, "_current_snapshot_or_none", lambda: None)()
    return None if snapshot is None else snapshot.to_dict(mode="json")


def _with_partial(error: Exception, partial: dict | None) -> Exception:
    if partial is not None:
        setattr(error, PARTIAL_RESPONSE, partial)
    return error


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
        if why is None and registered.model_family(self.model) != registered.HAIKU_MODEL:
            why = (f"the Messages transport sends {registered.HAIKU_MODEL} only (R8, "
                   f"{registered.R8_REF}), got model {self.model}")
        if why:
            raise PaidCallsNotAllowed(f"{why}; no paid call was made")

    def _approval_refusal(self) -> str | None:
        if registered.HAIKU_EXPERIMENT in self.approval.experiments:
            return None
        # R9 (PREREG §17.9): its own run only (the general guard has checked that the block
        # lists the run's experiment)
        if self.approval.experiment == registered.HAIKU_NOTES_EXPERIMENT:
            return None
        return (f"block {self.approval.approved_block!r} lists "
                f"{', '.join(self.approval.experiments)}, not {registered.HAIKU_EXPERIMENT}: "
                f"a {registered.HAIKU_MODEL} run, its pilots and validity run included, needs "
                f"an approval line written for the Haiku replication ({registered.R8_REF}), "
                f"which lists it, or for R9's notes run ({registered.R9_REF}), which lists "
                f"{registered.HAIKU_NOTES_EXPERIMENT}")

    def _default_client(self, timeout_s: float) -> Any:
        # max_retries=0: retries are handled by the transport so that every attempt is visible.
        client = anthropic.Anthropic(max_retries=0, timeout=timeout_s)
        why = client_header_refusal(client)
        if why:
            raise PaidCallsNotAllowed(f"{why}; no paid call was made")
        return client

    def _check_request(self, payload: dict) -> None:
        MESSAGES.check_payload(payload, effort=registered_effort(self.model),
                               max_tokens=DEFAULT_MAX_OUTPUT_TOKENS)

    def _call(self, client: Any, payload: dict) -> dict:
        """One attempt (module docstring). A stream that drops or stalls after its 200
        headers, or ends before its `message_delta`, raises `anthropic.APIConnectionError`
        (retried); an error, or an error event inside the stream, after `message_start`
        carries the message so far (`PARTIAL_RESPONSE`), whose usage the ledger records."""
        with client.messages.stream(**payload) as stream:
            try:
                message = stream.get_final_message()
            except httpx2.TransportError as e:
                raise _with_partial(anthropic.APIConnectionError(
                    message=f"the stream failed part way ({type(e).__name__}: {e})",
                    request=stream.response.request), _partial(stream)) from e
            except anthropic.APIStatusError as e:  # an error event inside the stream
                raise _with_partial(e, _partial(stream))
            # to_dict: the keys the API returned (exclude_unset), JSON types only.
            data = message.to_dict(mode="json")
            if data.get("stop_reason") is None:
                raise _with_partial(anthropic.APIConnectionError(
                    message="the stream ended before its message_delta (no stop_reason)",
                    request=stream.response.request), data)
        return data

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
            "inference_geo": (data.get("usage") or {}).get("inference_geo"),
            "status": status,
            "incomplete_reason": reason,
            "stop_reason": data.get("stop_reason"),
            "prompt_tokens": MESSAGES.usage(data)["input_tokens"],
        }

    def _mismatches(self) -> tuple[int | str, int | str]:
        return NOT_ECHOED, NOT_ECHOED

    def _log_response(self, echo: dict, payload: dict, blinded: bool) -> None:
        log.info("model=%s tier=%s geo=%s prompt_tokens=%s stop_reason=%s status=%s",
                 echo["model_returned"], echo["service_tier_returned"], echo["inference_geo"],
                 echo["prompt_tokens"], "withheld" if blinded else echo["stop_reason"],
                 "withheld" if blinded else echo["status"])
        if echo["service_tier_returned"] != MESSAGES_SERVICE_TIER:
            log.warning("served on tier %s, not %s: priced at the standard tier's prices",
                        echo["service_tier_returned"], MESSAGES_SERVICE_TIER)
        if echo["inference_geo"] != SERVED_GEO:
            log.warning("served in inference geo %s, not %s: priced at %.1fx",
                        echo["inference_geo"], SERVED_GEO,
                        price_for(self.model).geo_multiplier(echo["inference_geo"]))
        threshold = price_for(self.model).long_threshold
        if threshold is not None and echo["prompt_tokens"] > threshold:
            log.warning("prompt of %d tokens is over %d: priced at the dearer card",
                        echo["prompt_tokens"], threshold)
        if echo["status"] == "incomplete" and not blinded:
            # D13: the caller scores it as an invalid action
            log.warning("incomplete response (reason=%s, max_tokens=%s)",
                        echo["incomplete_reason"], payload.get("max_tokens"))
