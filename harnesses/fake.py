"""A fake Responses API for tests and $0 dry runs. It never touches the network.

`FakeModel.send(payload)` returns a response dict shaped like the Responses API's JSON:
one reasoning item with fake `encrypted_content` and an assistant message, plus echoed
`reasoning` settings, `service_tier`, a returned model string and usage. Ids name the call:
step call i (counted over step calls only, so it equals the turn index when nothing is
retried) gets `rs_t<i>` / `msg_t<i>`; summary call j gets `rs_s<j>` / `msg_s<j>`.

The echoed `reasoning.context` and `reasoning.effort` are the requested ones unless
`echo_context` or `echo_effort` say otherwise (a value, or a function of the payload and the
call's 0-based arrival index). Every response reports `reasoning_tokens` reasoning tokens, or
`reasoning_tokens_fn(payload, n)` with the index n that `reply_fn` gets; each replayed
reasoning item that an `all_turns` request renders adds the constant `reasoning_tokens` to the
input tokens.

`status_fn(payload, tag)` sets a response's status. An `incomplete` response looks like one
that stopped at `max_output_tokens` (`incomplete_details.reason`, the whole cap in
`output_tokens`); if its text is empty it has no message item, as when the cap is hit while
reasoning.

`ids="payload"` makes every response a function of its payload alone, as an API's response
does not depend on the other episodes' calls: the tag is `t` (step) or `s` (summary) plus the
first 16 hex digits of the payload's SHA-256, and the index passed to `reply_fn` and
`summary_fn` is the number of user messages in the payload minus one. Episodes played in
parallel (harnesses/parallel.py) then get the responses they get when played one at a time,
whatever the order of the calls. The default, `ids="call_order"`, numbers calls in the order
they arrive, which the payload snapshot tests label. `send` may be called from several
threads at once.

For a `claude-*` model (the Messages wire, `harnesses.wire`) the response is shaped like the
Messages API's JSON instead, and the payload must first pass the wire's request-side check
(`MessagesWire.check_payload`, with any of its efforts and caps; the paid transport pins
both): a thinking block with empty text and a fake signature (`fake-sig-<tag>`, as Haiku 5.5
returns thinking by default, display omitted), then a text block holding the reply (none if
the reply is empty), `stop_reason`, the returned model string and usage with the cache fields
and `output_tokens_details.thinking_tokens` (left out with
`report_thinking_tokens=False`). No reasoning setting is echoed. `status_fn` may return
`completed` (`end_turn`), `incomplete` (`max_tokens`, the whole cap in `output_tokens`) or
`refusal` (`stop_details.category` `refusal_category`). Prompt caching is faked from the
payload alone: with `cache_control`, everything before the last assistant turn and the
observation is a cache read and the rest a cache write; without it, all is uncached input.
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
from collections.abc import Callable

from harnesses.config import ARC_SUMMARY_REQUEST_PROMPT
from harnesses.items import item_text
from harnesses.wire import MESSAGES, visible_text, wire_for
from persistgym import tokens

ReplyFn = Callable[[dict, int], str]


def padded_text(prefix: str, n: int, tokenizer: str = "o200k_base") -> str:
    """`prefix` padded with ' x' words to exactly n tokens (for scripted replies)."""
    text = prefix + " x" * max(n - tokens.count(prefix, tokenizer), 0)
    while tokens.count(text, tokenizer) > n and text.endswith(" x"):
        text = text[:-2]
    while tokens.count(text, tokenizer) < n:
        text += " x"
    if tokens.count(text, tokenizer) != n:
        raise ValueError(f"cannot hit {n} tokens with prefix {prefix!r}")
    return text


def _default_reply(payload: dict, i: int) -> str:
    return f"Fake reply to turn {i}.\nACTION: ack(none)"


def _default_summary(payload: dict, j: int) -> str:
    return f"SUMMARY s{j}: fake summary of {len(payload['input']) - 1} items."


class FakeModel:
    paid = False

    def __init__(self, reply_fn: ReplyFn | None = None, *,
                 summary_fn: ReplyFn | None = None,
                 reasoning_summary_fn: Callable[[dict, str], str] | None = None,
                 echo_context: str | Callable[[dict, int], str] = "request",
                 echo_effort: str | Callable[[dict, int], str] = "request",
                 model_suffix: str = "-fake-2026-10-01",
                 reasoning_tokens: int = 37,
                 reasoning_tokens_fn: Callable[[dict, int], int] | None = None,
                 summary_request_prompt: str = ARC_SUMMARY_REQUEST_PROMPT,
                 status_fn: Callable[[dict, str], str] | None = None,
                 ids: str = "call_order",
                 report_thinking_tokens: bool = True,
                 refusal_category: str | None = "general_harms"):
        if ids not in ("call_order", "payload"):
            raise ValueError(f"ids must be 'call_order' or 'payload', got {ids!r}")
        self.ids = ids
        self._lock = threading.Lock()
        self.reply_fn = reply_fn or _default_reply
        self.summary_fn = summary_fn or _default_summary
        self.reasoning_summary_fn = reasoning_summary_fn
        self.echo_context = echo_context
        self.echo_effort = echo_effort
        self.model_suffix = model_suffix
        self.reasoning_tokens = reasoning_tokens
        self.reasoning_tokens_fn = reasoning_tokens_fn
        self.summary_request_prompt = summary_request_prompt
        self.status_fn = status_fn
        self.report_thinking_tokens = report_thinking_tokens
        self.refusal_category = refusal_category
        self.calls: list[dict] = []  # deep copies of every payload received
        self.n_step = 0
        self.n_summary = 0

    @staticmethod
    def _messages(payload: dict) -> list[dict]:
        """The payload's input items (`input`; `messages` on the Messages wire)."""
        key = "messages" if wire_for(payload.get("model")) is MESSAGES else "input"
        return payload.get(key) or []

    def is_summary(self, payload: dict) -> bool:
        items = self._messages(payload)
        last = items[-1] if items else {}
        return last.get("role") == "user" and item_text(last) == self.summary_request_prompt

    def send(self, payload: dict) -> dict:
        if wire_for(payload.get("model")) is MESSAGES:
            # the request-side check every Messages body passes before the paid transport
            # sends it (that one also pins the registered effort and the 32,000 cap)
            MESSAGES.check_payload(payload)
        summary = self.is_summary(payload)
        snapshot = copy.deepcopy(payload)
        with self._lock:
            k = len(self.calls)
            self.calls.append(snapshot)
            if summary:
                self.n_summary += 1
                n = self.n_summary
            else:
                n = self.n_step
                self.n_step += 1
        kind = "s" if summary else "t"
        if self.ids == "payload":
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False)
                                    .encode("utf-8")).hexdigest()[:16]
            tag = f"{kind}{digest}"
            n = sum(1 for i in self._messages(payload) if i.get("role") == "user") - 1
        else:
            tag = f"{kind}{n}"
        text = self.summary_fn(payload, n) if summary else self.reply_fn(payload, n)
        if wire_for(payload.get("model")) is MESSAGES:
            return self._messages_response(payload, tag, n, text)
        req = payload.get("reasoning") or {}
        echo = (self.echo_context(payload, k) if callable(self.echo_context)
                else req.get("context") if self.echo_context == "request" else self.echo_context)
        effort = (self.echo_effort(payload, k) if callable(self.echo_effort)
                  else req.get("effort") if self.echo_effort == "request" else self.echo_effort)
        summary = []
        if req.get("summary") and self.reasoning_summary_fn:
            summary = [{"type": "summary_text", "text": self.reasoning_summary_fn(payload, tag)}]
        visible = tokens.count((payload.get("instructions") or "") + "".join(
            item_text(i) for i in payload.get("input") or []))
        replayed = sum(1 for i in payload.get("input") or [] if i.get("type") == "reasoning")
        rendered = replayed * self.reasoning_tokens if echo == "all_turns" else 0
        status = self.status_fn(payload, tag) if self.status_fn else "completed"
        reasoning_tokens = (self.reasoning_tokens_fn(payload, n) if self.reasoning_tokens_fn
                            else self.reasoning_tokens)
        output = [{"type": "reasoning", "id": f"rs_{tag}", "summary": summary,
                   "encrypted_content": f"gAAAAB-fake-encrypted-{tag}"}]
        if status == "incomplete":
            # Stopped at the output cap, as the API reports it: the whole cap is used, and an
            # empty text means it stopped while reasoning (no message item at all).
            details = {"reason": "max_output_tokens"}
            cap = payload.get("max_output_tokens")
            if cap is not None:
                reasoning_tokens = max(cap - tokens.count(text), 0)
            message_status = "incomplete"
        else:
            details, message_status = None, "completed"
        if text or status != "incomplete":
            output.append({"type": "message", "id": f"msg_{tag}", "role": "assistant",
                           "status": message_status,
                           "content": [{"type": "output_text", "text": text,
                                        "annotations": []}]})
        out_tokens = tokens.count(text) + reasoning_tokens
        return {
            "id": f"resp_{tag}",
            "object": "response",
            "status": status,
            "incomplete_details": details,
            "model": payload.get("model", "") + self.model_suffix,
            "output": output,
            "reasoning": {"effort": effort, "mode": req.get("mode"), "context": echo,
                          "summary": req.get("summary")},
            "service_tier": payload.get("service_tier"),
            "store": payload.get("store"),
            "usage": {
                "input_tokens": visible + rendered,
                "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                "output_tokens": out_tokens,
                "output_tokens_details": {"reasoning_tokens": reasoning_tokens},
                "total_tokens": visible + rendered + out_tokens,
            },
        }

    def _messages_response(self, payload: dict, tag: str, n: int, text: str) -> dict:
        """A Messages API response (module docstring)."""
        status = self.status_fn(payload, tag) if self.status_fn else "completed"
        thinking = (self.reasoning_tokens_fn(payload, n) if self.reasoning_tokens_fn
                    else self.reasoning_tokens)
        details = None
        if status == "incomplete":
            # stopped at max_tokens: the whole cap is used, thinking included; an empty text
            # means it stopped while thinking (no text block at all)
            stop = "max_tokens"
            cap = payload.get("max_tokens")
            if cap is not None:
                thinking = max(cap - tokens.count(text), 0)
        elif status == "refusal":
            stop = "refusal"
            details = {"type": "refusal", "category": self.refusal_category,
                       "explanation": None}
        else:
            stop = "end_turn"
        content = [{"type": "thinking", "thinking": "", "signature": f"fake-sig-{tag}"}]
        if text:
            content.append({"type": "text", "text": text})
        msgs = payload["messages"]
        visible = tokens.count(visible_text(payload))
        if "cache_control" not in payload:
            plain, read, write = visible, 0, 0
        else:
            prefix = (tokens.count(payload["system"] + "".join(item_text(m) for m in msgs[:-2]))
                      if len(msgs) > 2 else 0)
            plain, read, write = 0, prefix, max(visible - prefix, 0)
        out_tokens = tokens.count(text) + thinking
        usage = {"input_tokens": plain, "cache_creation_input_tokens": write,
                 "cache_read_input_tokens": read,
                 "cache_creation": {"ephemeral_5m_input_tokens": write,
                                    "ephemeral_1h_input_tokens": 0},
                 "output_tokens": out_tokens, "service_tier": "standard",
                 "inference_geo": "global"}
        if self.report_thinking_tokens:
            usage["output_tokens_details"] = {"thinking_tokens": thinking}
        return {
            "id": f"msg_{tag}",
            "type": "message",
            "role": "assistant",
            "model": payload.get("model", "") + self.model_suffix,
            "content": content,
            "stop_reason": stop,
            "stop_sequence": None,
            "stop_details": details,
            "usage": usage,
        }
