"""OpenAI Responses API input and output items (plain dicts, as sent and received as JSON).

Input items the harness builds:
* `user_message(text)`: an observation, the summary bridge or the summary request;
* earlier turns' output items, sent back as returned (reasoning items with
  `encrypted_content`, then the assistant message), following OpenAI's stateless pattern
  `context += response.output`
  (https://developers.openai.com/cookbook/examples/responses_api/reasoning_items).
"""

from __future__ import annotations

from typing import Any

REPLAYED_OUTPUT_TYPES = ("reasoning", "message")


def user_message(text: str) -> dict:
    return {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}


def _drop_none(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _drop_none(v) for k, v in x.items() if v is not None}
    if isinstance(x, list):
        return [_drop_none(v) for v in x]
    return x


def replay_items(response: dict) -> tuple[list[dict], list[str]]:
    """The response's output items to send back on later turns, and the types left out.

    Reasoning and message items are kept in their returned order, verbatim except that keys
    whose value is null are dropped. Any other item type (none is expected: no tools are
    offered) is left out and reported."""
    kept, dropped = [], []
    for item in response.get("output") or []:
        if item.get("type") in REPLAYED_OUTPUT_TYPES:
            kept.append(_drop_none(item))
        else:
            dropped.append(str(item.get("type")))
    return kept, dropped


def output_text(response: dict) -> str:
    """Concatenated `output_text` parts of the assistant message items (the SDK's
    `response.output_text`). This is the visible reply the environment scores."""
    parts = []
    for item in response.get("output") or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if part.get("type") == "output_text":
                parts.append(part.get("text") or "")
    return "".join(parts)


def reasoning_summary_text(response: dict) -> str:
    """Readable reasoning summaries of a response (empty unless summaries were requested)."""
    out = []
    for item in response.get("output") or []:
        if item.get("type") == "reasoning":
            for s in item.get("summary") or []:
                if s.get("text"):
                    out.append(s["text"])
    return "\n".join(out)


def n_reasoning_items(items: list[dict]) -> int:
    return sum(1 for i in items if i.get("type") == "reasoning")


def item_text(item: dict) -> str:
    """Visible text of one input item ('' for reasoning items)."""
    if item.get("type") == "reasoning":
        return ""
    content = item.get("content")
    if isinstance(content, str):
        return content
    return "".join(p.get("text") or "" for p in content or [] if isinstance(p, dict))
