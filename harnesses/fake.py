"""A fake Responses API for tests and $0 dry runs. It never touches the network.

`FakeModel.send(payload)` returns a response dict shaped like the Responses API's JSON:
one reasoning item with fake `encrypted_content` and an assistant message, plus echoed
`reasoning` settings, `service_tier`, a returned model string and usage. Ids name the call:
step call i (counted over step calls only, so it equals the turn index when nothing is
retried) gets `rs_t<i>` / `msg_t<i>`; summary call j gets `rs_s<j>` / `msg_s<j>`.
"""

from __future__ import annotations

import copy
from collections.abc import Callable

from harnesses.config import ARC_SUMMARY_REQUEST_PROMPT
from harnesses.items import item_text
from persistgym import tokens

ReplyFn = Callable[[dict, int], str]


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
                 model_suffix: str = "-fake-2026-10-01",
                 reasoning_tokens: int = 37,
                 summary_request_prompt: str = ARC_SUMMARY_REQUEST_PROMPT,
                 status_fn: Callable[[dict, str], str] | None = None):
        self.reply_fn = reply_fn or _default_reply
        self.summary_fn = summary_fn or _default_summary
        self.reasoning_summary_fn = reasoning_summary_fn
        self.echo_context = echo_context
        self.model_suffix = model_suffix
        self.reasoning_tokens = reasoning_tokens
        self.summary_request_prompt = summary_request_prompt
        self.status_fn = status_fn
        self.calls: list[dict] = []  # deep copies of every payload received
        self.n_step = 0
        self.n_summary = 0

    def is_summary(self, payload: dict) -> bool:
        last = payload["input"][-1] if payload.get("input") else {}
        return last.get("role") == "user" and item_text(last) == self.summary_request_prompt

    def send(self, payload: dict) -> dict:
        k = len(self.calls)
        self.calls.append(copy.deepcopy(payload))
        if self.is_summary(payload):
            self.n_summary += 1
            tag = f"s{self.n_summary}"
            text = self.summary_fn(payload, self.n_summary)
        else:
            tag = f"t{self.n_step}"
            text = self.reply_fn(payload, self.n_step)
            self.n_step += 1
        req = payload.get("reasoning") or {}
        echo = (self.echo_context(payload, k) if callable(self.echo_context)
                else req.get("context") if self.echo_context == "request" else self.echo_context)
        summary = []
        if req.get("summary") and self.reasoning_summary_fn:
            summary = [{"type": "summary_text", "text": self.reasoning_summary_fn(payload, tag)}]
        visible = tokens.count((payload.get("instructions") or "") + "".join(
            item_text(i) for i in payload.get("input") or []))
        replayed = sum(1 for i in payload.get("input") or [] if i.get("type") == "reasoning")
        rendered = replayed * self.reasoning_tokens if echo == "all_turns" else 0
        out_tokens = tokens.count(text) + self.reasoning_tokens
        return {
            "id": f"resp_{tag}",
            "object": "response",
            "status": self.status_fn(payload, tag) if self.status_fn else "completed",
            "model": payload.get("model", "") + self.model_suffix,
            "output": [
                {"type": "reasoning", "id": f"rs_{tag}", "summary": summary,
                 "encrypted_content": f"gAAAAB-fake-encrypted-{tag}"},
                {"type": "message", "id": f"msg_{tag}", "role": "assistant",
                 "status": "completed",
                 "content": [{"type": "output_text", "text": text, "annotations": []}]},
            ],
            "reasoning": {"effort": req.get("effort"), "mode": req.get("mode"), "context": echo,
                          "summary": req.get("summary")},
            "service_tier": payload.get("service_tier"),
            "store": payload.get("store"),
            "usage": {
                "input_tokens": visible + rendered,
                "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                "output_tokens": out_tokens,
                "output_tokens_details": {"reasoning_tokens": self.reasoning_tokens},
                "total_tokens": visible + rendered + out_tokens,
            },
        }
