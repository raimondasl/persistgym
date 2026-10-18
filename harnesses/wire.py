"""Wire formats: how one harness request is written for a provider's API, and how its
response is read back.

A harness cell decides what the model sees (harnesses/cells.py, harnesses/session.py); a
wire decides how that is written as the JSON body of one API request, and how the response is
read. Two wires exist, and the model string alone chooses one (`wire_for`), so
`HarnessConfig`, and with it every config hash written so far, is unchanged:

* `ResponsesWire` (every model but `claude-*`): OpenAI's Responses API, `POST /v1/responses`.
  It is the harness's original code, moved here unchanged; the payload snapshot tests
  (harnesses/tests/test_payload_snapshots.py) hold its bodies byte for byte.
* `MessagesWire` (`claude-*`): Anthropic's Messages API, `POST /v1/messages`, for the
  replay-off cells F-0, W-0 and W-n-0 and the single-turn control only (PREREG §17.8,
  amendment R8, not yet merged; harnesses/DESIGN.md §13). It refuses every cell that replays
  reasoning and every summary cell (`check_cell`).

Provider-neutral, and the same on both wires: the history and loss policies, the notes
sentence, and every token count the policies use (tiktoken `o200k_base` on visible text,
persistgym/tokens.py), so the window W evicts where the generator designed near and far on
either API. Only the extraction of the visible reply changes per wire.

The Messages body (`MessagesWire.build`): `model`; `system`, the instructions (in W-n-0 the
episode's system prompt, "\\n" and the notes sentence, as on OpenAI); `messages`, alternating
user and assistant, every earlier assistant turn as its visible text only (never a thinking
or redacted_thinking block: replay off), the last message always the user observation;
`max_tokens` (32,000, PREREG D13; it includes thinking); `thinking` `{"type": "adaptive"}`,
its display left at the model's default; `output_config` `{"effort": <effort>}`; and, in the
multi-turn cells only, a top-level `cache_control` `{"type": "ephemeral"}` (5 minutes; never a
1-hour TTL). Never sent: sampling parameters, tools, a prefill, fallbacks, a service tier.
`MessagesWire.check_payload` asserts all of this on a body before it is sent.

A turn whose visible reply is empty (thinking only, a refusal, or a stop at `max_tokens`
while thinking) cannot be sent back as an empty assistant message: the API rejects an empty
or whitespace-only text block. It goes back as one text block holding
`EMPTY_REPLY_PLACEHOLDER`; its visible reply, the one W counts and the environment scores,
is still the empty text (0 tokens toward W), as on OpenAI, where such a turn is a reasoning
item with no message.

Echoes: the Responses API echoes the reasoning settings it applied and the runner checks them
on every response. The Messages API echoes neither effort nor a reasoning context, so
`MessagesWire.echo` reports them as not echoed (None): never a mismatch, never an
exclusion. Its substitute is the request-side check above, on every body before it is sent
(PREREG §17.8, pending).
"""

from __future__ import annotations

import copy
from typing import Any, Protocol

from harnesses.cells import CellSpec
from harnesses.config import ENCRYPTED_REASONING, HarnessConfig
from harnesses.items import item_text, output_text, replay_items, user_message
from harnesses.pricing import messages_usage_numbers, usage_numbers

RESPONSES_API = "responses"
MESSAGES_API = "messages"

EMPTY_REPLY_PLACEHOLDER = "(no reply)"
"""The text an earlier assistant turn with no visible reply is sent back as on the Messages
wire (module docstring). Not counted toward W: the turn's visible reply is the empty text."""
MESSAGES_EFFORTS = ("low", "medium", "high", "xhigh", "max")
"""`output_config.effort` values of the Messages API (all five on claude-haiku-5-5)."""
MESSAGES_SERVICE_TIER = "standard"
"""The tier a Messages run records as requested (`HarnessConfig.service_tier`, the costs row's
`service_tier`). No `service_tier` field is sent; the tier served is read from
`usage.service_tier` and recorded beside it."""
MESSAGES_MODE = "standard"
"""`HarnessConfig.reasoning_mode` of a Messages run: recorded, never sent (the Messages API
has no reasoning mode)."""
MESSAGES_FIELDS = ("model", "system", "messages", "max_tokens", "thinking", "output_config")
"""The fields of every Messages body; a multi-turn cell's also has `cache_control`."""
CACHE_CONTROL = {"type": "ephemeral"}
"""Top-level automatic prompt caching with the default 5-minute TTL (never `ttl: 1h`)."""
ADAPTIVE_THINKING = {"type": "adaptive"}
THINKING_BLOCKS = ("thinking", "redacted_thinking")


class UnsupportedOnWire(ValueError):
    """A cell or a request setting this wire does not send."""


class RequestCheckFailed(ValueError):
    """A Messages body failed the request-side check (`MessagesWire.check_payload`) and was
    not sent: a harness bug, never a model outcome."""


class Wire(Protocol):
    api: str
    provider: str
    echoes_reasoning: bool

    def check_cell(self, cell: CellSpec) -> None: ...
    def check_config(self, cfg: HarnessConfig) -> None: ...
    def user_message(self, text: str) -> dict: ...
    def build(self, cfg: HarnessConfig, cell: CellSpec, instructions: str,
              items: list[dict], cap: int, *, cache: bool) -> dict: ...
    def turn_items(self, response: dict) -> tuple[list[dict], list[str]]: ...
    def is_reasoning_item(self, item: dict) -> bool: ...
    def text(self, response: dict) -> str: ...
    def status(self, response: dict) -> tuple[str | None, str | None]: ...
    def usage(self, response: dict) -> dict: ...
    def served_tier(self, response: dict) -> str | None: ...
    def requested_tier(self, payload: dict) -> str | None: ...
    def echo(self, payload: dict, response: dict) -> dict: ...
    def messages(self, payload: dict) -> list[dict]: ...
    def system(self, payload: dict) -> str | None: ...
    def cap(self, payload: dict) -> Any: ...


class ResponsesWire:
    """OpenAI's Responses API: the harness's original request body and response reading,
    unchanged (harnesses/DESIGN.md §3)."""

    api = RESPONSES_API
    provider = "openai"
    echoes_reasoning = True

    def check_cell(self, cell: CellSpec) -> None:
        """Every cell runs on the Responses wire."""

    def check_config(self, cfg: HarnessConfig) -> None:
        if cfg.service_tier == MESSAGES_SERVICE_TIER:
            raise UnsupportedOnWire(f"service tier {cfg.service_tier!r} is the Messages API's; "
                                    f"{cfg.model} runs on OpenAI's Responses API")

    def user_message(self, text: str) -> dict:
        return user_message(text)

    def build(self, cfg: HarnessConfig, cell: CellSpec, instructions: str,
              items: list[dict], cap: int, *, cache: bool = True) -> dict:
        """The Responses body. `max_output_tokens` is always sent: the step cap or the summary
        cap, both 32,000 under PREREG D13. `cache` changes nothing here: OpenAI caches
        prefixes automatically (`prompt_cache_key` only when configured)."""
        reasoning = {"effort": cfg.reasoning_effort, "mode": cfg.reasoning_mode,
                     "context": cell.reasoning_context}
        if cfg.reasoning_summary is not None:
            reasoning["summary"] = cfg.reasoning_summary
        payload = {
            "model": cfg.model,
            "instructions": instructions,
            "input": copy.deepcopy(items),
            "reasoning": reasoning,
            "store": False,
            "include": [ENCRYPTED_REASONING],
            "service_tier": cfg.service_tier,
            "truncation": "disabled",
            "max_output_tokens": cap,
        }
        if cfg.prompt_cache_key is not None:
            payload["prompt_cache_key"] = cfg.prompt_cache_key
        return payload

    def turn_items(self, response: dict) -> tuple[list[dict], list[str]]:
        return replay_items(response)

    def is_reasoning_item(self, item: dict) -> bool:
        return item.get("type") == "reasoning"

    def text(self, response: dict) -> str:
        return output_text(response)

    def status(self, response: dict) -> tuple[str | None, str | None]:
        return (response.get("status"),
                (response.get("incomplete_details") or {}).get("reason"))

    def usage(self, response: dict) -> dict:
        return usage_numbers(response.get("usage"))

    def served_tier(self, response: dict) -> str | None:
        return response.get("service_tier")

    def requested_tier(self, payload: dict) -> str | None:
        return payload.get("service_tier")

    def echo(self, payload: dict, response: dict) -> dict:
        """Requested vs echoed reasoning settings, the returned model and service tier."""
        req = payload.get("reasoning") or {}
        got = response.get("reasoning") or {}
        return {
            "context_requested": req.get("context"), "context_echoed": got.get("context"),
            "context_ok": req.get("context") == got.get("context"),
            "effort_requested": req.get("effort"), "effort_echoed": got.get("effort"),
            "effort_ok": req.get("effort") == got.get("effort"),
            "mode_requested": req.get("mode"), "mode_echoed": got.get("mode"),
            "model_requested": payload.get("model"), "model_returned": response.get("model"),
            "service_tier_requested": payload.get("service_tier"),
            "service_tier_returned": response.get("service_tier"),
            "status": response.get("status"),
            "incomplete_reason": (response.get("incomplete_details") or {}).get("reason"),
        }

    def messages(self, payload: dict) -> list[dict]:
        return payload["input"]

    def system(self, payload: dict) -> str | None:
        return payload["instructions"]

    def cap(self, payload: dict) -> Any:
        return payload.get("max_output_tokens")


class MessagesWire:
    """Anthropic's Messages API, for the replay-off cells and the single-turn control only
    (module docstring; PREREG §17.8, pending)."""

    api = MESSAGES_API
    provider = "anthropic"
    echoes_reasoning = False

    def check_cell(self, cell: CellSpec) -> None:
        """Replay-off, non-summary cells only: F-0, W-0, W-n-0 (and the single-turn control,
        which sends F-0's request). A cell that replays reasoning would have to send earlier
        thinking blocks, and a summary cell's summary request would need two user turns in a
        row; neither is built."""
        if cell.replay:
            raise UnsupportedOnWire(f"cell {cell.cell_id} replays reasoning: the Messages wire "
                                    "runs replay-off cells only (F-0, W-0, W-n-0)")
        if cell.history == "summary":
            raise UnsupportedOnWire(f"cell {cell.cell_id} summarizes at W: the Messages wire "
                                    "runs no summary cell (F-0, W-0, W-n-0 only)")

    def check_config(self, cfg: HarnessConfig) -> None:
        wrong = [what for what, bad in (
            ((f"effort {cfg.reasoning_effort!r} (the Messages API's: "
              f"{', '.join(MESSAGES_EFFORTS)})"), cfg.reasoning_effort not in MESSAGES_EFFORTS),
            ((f"reasoning mode {cfg.reasoning_mode!r} ({MESSAGES_MODE!r} only: recorded, not "
              "sent)"), cfg.reasoning_mode != MESSAGES_MODE),
            (f"service tier {cfg.service_tier!r} ({MESSAGES_SERVICE_TIER!r} only)",
             cfg.service_tier != MESSAGES_SERVICE_TIER),
            ("reasoning summaries (not sent)", cfg.reasoning_summary is not None),
            ("a prompt_cache_key (not sent)", cfg.prompt_cache_key is not None)) if bad]
        if wrong:
            raise UnsupportedOnWire(f"{cfg.model} runs on the Messages API, which does not take "
                                    + "; ".join(wrong))

    def user_message(self, text: str) -> dict:
        return {"role": "user", "content": [{"type": "text", "text": text}]}

    def build(self, cfg: HarnessConfig, cell: CellSpec, instructions: str,
              items: list[dict], cap: int, *, cache: bool = True) -> dict:
        """The Messages body (module docstring). `cache`: a multi-turn cell's requests carry
        a top-level `cache_control` (5-minute automatic prompt caching); the single-turn
        control's request has none (its prompt is never sent again)."""
        payload = {
            "model": cfg.model,
            "system": instructions,
            "messages": copy.deepcopy(items),
            "max_tokens": cap,
            "thinking": dict(ADAPTIVE_THINKING),
            "output_config": {"effort": cfg.reasoning_effort},
        }
        if cache:
            payload["cache_control"] = dict(CACHE_CONTROL)
        return payload

    def turn_items(self, response: dict) -> tuple[list[dict], list[str]]:
        """What a turn sends back on later requests: one assistant message holding its
        visible reply as one text block, or `EMPTY_REPLY_PLACEHOLDER` when the reply is empty
        or whitespace only. Thinking blocks are never sent back (replay off); any block type
        other than text and thinking (none is expected: no tools are offered) is reported."""
        reply = self.text(response)
        dropped = [str(b.get("type")) for b in response.get("content") or []
                   if b.get("type") not in ("text", *THINKING_BLOCKS)]
        sent = reply if reply.strip() else EMPTY_REPLY_PLACEHOLDER
        return [{"role": "assistant", "content": [{"type": "text", "text": sent}]}], dropped

    def is_reasoning_item(self, item: dict) -> bool:
        return any(isinstance(b, dict) and b.get("type") in THINKING_BLOCKS
                   for b in item.get("content") or [])

    def text(self, response: dict) -> str:
        """The visible reply: the response's text blocks, concatenated; thinking never."""
        return "".join(b.get("text") or "" for b in response.get("content") or []
                       if b.get("type") == "text")

    def status(self, response: dict) -> tuple[str | None, str | None]:
        """`stop_reason` as a Responses-style status and reason: `end_turn` completed;
        `max_tokens` incomplete (`max_output_tokens`, D13); `refusal` incomplete
        (`refusal:<stop_details.category>`, `null` when the category is null); anything else
        incomplete (`unexpected_stop_reason:<stop_reason>`), which the paid transport logs."""
        stop = response.get("stop_reason")
        if stop == "end_turn":
            return "completed", None
        if stop == "max_tokens":
            return "incomplete", "max_output_tokens"
        if stop == "refusal":
            category = (response.get("stop_details") or {}).get("category")
            return "incomplete", f"refusal:{'null' if category is None else category}"
        return "incomplete", f"unexpected_stop_reason:{stop}"

    def usage(self, response: dict) -> dict:
        return messages_usage_numbers(response.get("usage"))

    def served_tier(self, response: dict) -> str | None:
        return (response.get("usage") or {}).get("service_tier")

    def requested_tier(self, payload: dict) -> str | None:
        return MESSAGES_SERVICE_TIER

    def echo(self, payload: dict, response: dict) -> dict:
        """The same fields as `ResponsesWire.echo`, with the settings the Messages API does
        not echo as None (`*_ok` None: never a mismatch); the requested effort, the returned
        model, the served tier (`usage.service_tier`), the status from `stop_reason` and
        `stop_reason` itself."""
        status, reason = self.status(response)
        return {
            "context_requested": None, "context_echoed": None, "context_ok": None,
            "effort_requested": (payload.get("output_config") or {}).get("effort"),
            "effort_echoed": None, "effort_ok": None,
            "mode_requested": None, "mode_echoed": None,
            "model_requested": payload.get("model"), "model_returned": response.get("model"),
            "service_tier_requested": self.requested_tier(payload),
            "service_tier_returned": self.served_tier(response),
            "status": status, "incomplete_reason": reason,
            "stop_reason": response.get("stop_reason"),
        }

    def messages(self, payload: dict) -> list[dict]:
        return payload["messages"]

    def system(self, payload: dict) -> str | None:
        return payload["system"]

    def cap(self, payload: dict) -> Any:
        return payload.get("max_tokens")

    def check_payload(self, payload: dict, *, effort: str | None = None,
                      max_tokens: int | None = None) -> None:
        """The request-side check, on every Messages body before it is sent (the substitute
        for the echo checks the Messages API cannot give): exactly `MESSAGES_FIELDS` (plus a
        top-level `cache_control` of exactly `CACHE_CONTROL`); adaptive thinking; an
        `output_config` of exactly one effort, `effort` if given (the registered one, from
        the paid transport); `max_tokens` equal to `max_tokens` if given, else a positive
        int; a non-empty system prompt; messages that alternate user and assistant from a
        user message to a user message (no prefill), each content a list of non-empty text
        blocks; and no thinking or redacted_thinking block anywhere. Raises
        `RequestCheckFailed` naming every problem."""
        problems = []
        keys = set(payload)
        extra = sorted(keys - set(MESSAGES_FIELDS) - {"cache_control"})
        missing = [k for k in MESSAGES_FIELDS if k not in keys]
        if extra:
            problems.append(f"fields not sent on the Messages wire: {', '.join(extra)}")
        if missing:
            problems.append(f"missing fields: {', '.join(missing)}")
        if "cache_control" in payload and payload["cache_control"] != CACHE_CONTROL:
            problems.append(f"cache_control {payload['cache_control']!r} (only "
                            f"{CACHE_CONTROL!r}: 5 minutes)")
        if payload.get("thinking") != ADAPTIVE_THINKING:
            problems.append(f"thinking {payload.get('thinking')!r} (must be "
                            f"{ADAPTIVE_THINKING!r})")
        oc = payload.get("output_config")
        got_effort = oc.get("effort") if isinstance(oc, dict) else None
        if (not isinstance(oc, dict) or set(oc) != {"effort"}
                or got_effort not in MESSAGES_EFFORTS
                or (effort is not None and got_effort != effort)):
            want = repr(effort) if effort is not None else "one of " + ", ".join(MESSAGES_EFFORTS)
            problems.append(f"output_config {oc!r} (must be exactly an effort, {want})")
        cap = payload.get("max_tokens")
        if (isinstance(cap, bool) or not isinstance(cap, int) or cap < 1
                or (max_tokens is not None and cap != max_tokens)):
            problems.append(f"max_tokens {cap!r} (must be "
                            f"{max_tokens if max_tokens is not None else 'a positive int'})")
        if not isinstance(payload.get("system"), str) or not payload["system"].strip():
            problems.append("no system prompt")
        problems += _messages_problems(payload.get("messages"))
        if problems:
            raise RequestCheckFailed("Messages request refused before sending: "
                                     + "; ".join(problems))


def _messages_problems(messages: Any) -> list[str]:
    """What is wrong with a Messages body's `messages` (`MessagesWire.check_payload`)."""
    if not isinstance(messages, list) or not messages:
        return ["no messages"]
    problems = []
    n_thinking = 0
    for i, m in enumerate(messages):
        want = "user" if i % 2 == 0 else "assistant"
        if not isinstance(m, dict) or set(m) != {"role", "content"} or m.get("role") != want:
            problems.append(f"message {i} is not a {want} message of role and content only")
            continue
        content = m["content"]
        if not isinstance(content, list) or not content:
            problems.append(f"message {i} has no content blocks")
            continue
        for b in content:
            if isinstance(b, dict) and b.get("type") in THINKING_BLOCKS:
                n_thinking += 1
            elif (not isinstance(b, dict) or set(b) != {"type", "text"} or b["type"] != "text"
                  or not isinstance(b["text"], str) or not b["text"].strip()):
                problems.append(f"message {i} has a block that is not a non-empty text block")
    if n_thinking:
        problems.append(f"{n_thinking} thinking blocks in messages (replay is off on the "
                        "Messages wire: earlier turns go back as visible text only)")
    if len(messages) % 2 == 0:
        problems.append("the last message is not the user's (a prefill)")
    return problems


RESPONSES = ResponsesWire()
MESSAGES = MessagesWire()


def wire_for(model: str | None) -> ResponsesWire | MessagesWire:
    """The wire of a model string: `MESSAGES` for `claude-*`, `RESPONSES` for every other
    (OpenAI) model."""
    return MESSAGES if str(model or "").startswith("claude-") else RESPONSES


def visible_text(payload: dict) -> str:
    """Every visible text a body sends, system prompt first, on either wire (thinking and
    reasoning items give none): what the project tokenizer counts for it."""
    wire = wire_for(payload.get("model"))
    return (wire.system(payload) or "") + "".join(item_text(i) for i in wire.messages(payload))
