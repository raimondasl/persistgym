"""The Claude token count of the largest Haiku requests, before any paid call (CLI
`count-tokens`; PREREG §17.8, amendment R8).

Every window and token rule of the harness is in project tokens (tiktoken `o200k_base`), and
stays so on the Messages wire, so that W evicts where the generator designed near and far.
What changes with Claude's tokenizer is cost: claude-haiku-5-5 bills a request at five times
the price once its prompt is over 100,000 tokens (`harnesses.pricing`), and the generator
bounds F-0's full history at the need step at 64,000 project tokens with 1,000-token replies
(`GeneratorConfig.max_context_tokens`; with luna's short replies it is about half that). This
command measures, for free, how close the sweep's largest requests come:

1. it regenerates, from the generator alone, the episodes of main templates
   [--start, --start + --n) in every task cell, plays each in F-0, W-0 and W-n-0 with the fake
   model (`harnesses.fake.FakeModel`, $0: its default replies are about 12 project tokens,
   about luna's visible reply length) and keeps each cell's and task cell's largest Messages
   request by project tokens; and builds the single-turn control's requests on the 4
   non-recoverable task cells, keeping the largest per task cell;
2. it sends each kept request's `model`, `system`, `messages` and `thinking` to Anthropic's
   free token-counting endpoint, `POST /v1/messages/count_tokens`
   (https://platform.claude.com/docs/en/build-with-claude/token-counting), one at a time;
3. it reports, per request, the project and Claude counts and their ratio, and over all of
   them the ratio's range and the largest Claude count against the 100,000 threshold.

It never calls `messages.create` or `messages.stream`, takes no paid-run lock and needs no
approval: the endpoint is free. It needs an API key: it refuses (`credential_refusal`) unless
`ANTHROPIC_API_KEY` is set and no other credential, base URL or custom header is, and a built
client that holds a custom header (`client_header_refusal`). The Claude counts are estimates, as
the endpoint says (they can include tokens the API adds and does not bill), of requests whose
replies are the fake model's: real replies that are longer, and lookup turns, make the
requests larger. Writes results/token_count/<time>/token_count.json (or --out) and prints it.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from typing import Any

from common import runmeta
from harnesses import registered, single_turn
from harnesses.anthropic_transport import client_header_refusal, credential_refusal
from harnesses.cells import get_cell
from harnesses.config import HarnessConfig
from harnesses.fake import FakeModel
from harnesses.pricing import HAIKU_LONG_THRESHOLD
from harnesses.runner import run_episode
from harnesses.wire import MESSAGES, MESSAGES_SERVICE_TIER, visible_text, wire_for
from persistgym import tokens
from persistgym.config import GeneratorConfig
from persistgym.episode import ALL_CELLS
from persistgym.render import generate

COUNTED_FIELDS = ("model", "system", "messages", "thinking")
"""The fields of a request sent to the counting endpoint: everything that is input. Its
`max_tokens`, `output_config` and `cache_control` change no input token."""
REPLY_NOTE = ("replies are harnesses.fake.FakeModel's defaults (about 12 o200k_base tokens, "
              "about luna's visible reply length) and no lookup is taken: real replies that "
              "are longer, and lookup turns, make the requests larger")


class Refused(ValueError):
    """count-tokens will not run, for the reason given."""


def _cfg(model: str) -> HarnessConfig:
    return HarnessConfig(model=model, reasoning_effort=registered.registered_effort(model),
                         service_tier=MESSAGES_SERVICE_TIER)


def largest_requests(model: str, gen: GeneratorConfig, *, start: int = 0, n: int = 10,
                     split: str = "main") -> list[dict]:
    """The largest request, by project tokens of its visible text, of each harness cell R8
    runs (`registered.HAIKU_CELLS`) and task cell over templates [start, start + n), played
    with the fake model, and of the single-turn control on each of its task cells; each with
    its cell, task cell, episode id, request index, project tokens and payload. $0: no API
    is called."""
    cfg = _cfg(model)
    best: dict[tuple[str, str], dict] = {}

    def keep(cell: str, task_cell: str, episode_id: str, index: int, payload: dict) -> None:
        n_tokens = tokens.count(visible_text(payload))
        key = (cell, task_cell)
        if key not in best or n_tokens > best[key]["o200k_tokens"]:
            best[key] = {"cell": cell, "task_cell": task_cell, "episode_id": episode_id,
                         "request_index": index, "o200k_tokens": n_tokens, "payload": payload}

    indices = list(range(start, start + n))
    for _, eps in generate(split, indices, gen, ALL_CELLS, ("base",)):
        for ep in eps:
            for cell_id in registered.HAIKU_CELLS:
                fake = FakeModel()
                run_episode(ep, get_cell(cell_id), cfg, fake)
                for i, payload in enumerate(fake.calls):
                    keep(cell_id, ep.cell.id, ep.episode_id, i, payload)
    for prompt in single_turn.build_prompts(split, indices, gen,
                                            list(single_turn.NONREC_TASK_CELLS)):
        payload = single_turn.build_request(prompt.control, cfg).payload
        keep(registered.HAIKU_SINGLE_TURN_CELL, prompt.control["cell"], prompt.episode_id, 0,
             payload)
    order = [*registered.HAIKU_CELLS, registered.HAIKU_SINGLE_TURN_CELL]
    cells = [c.id for c in ALL_CELLS]
    return sorted(best.values(), key=lambda r: (order.index(r["cell"]),
                                                cells.index(r["task_cell"])))


def _input_tokens(result: Any) -> int:
    """The endpoint's `input_tokens` (an SDK object or its dict)."""
    value = result["input_tokens"] if isinstance(result, dict) else result.input_tokens
    return int(value)


def count(requests: list[dict], client: Any) -> dict:
    """Send each request's input to the counting endpoint (`client.messages.count_tokens`
    only) and report the counts (module docstring)."""
    rows = []
    for r in requests:
        payload = r["payload"]
        MESSAGES.check_payload(payload)  # what would be sent is a valid Messages body
        claude = _input_tokens(client.messages.count_tokens(
            **{k: payload[k] for k in COUNTED_FIELDS}))
        rows.append({k: r[k] for k in ("cell", "task_cell", "episode_id", "request_index",
                                       "o200k_tokens")}
                    | {"claude_tokens": claude,
                       "ratio": round(claude / r["o200k_tokens"], 4) if r["o200k_tokens"]
                       else None})
    ratios = [x["ratio"] for x in rows if x["ratio"] is not None]
    largest = max(rows, key=lambda x: x["claude_tokens"]) if rows else None
    return {
        "threshold": HAIKU_LONG_THRESHOLD,
        "requests": rows,
        "ratio": ({"min": min(ratios), "median": round(statistics.median(ratios), 4),
                   "max": max(ratios)} if ratios else None),
        "max_claude_tokens": largest["claude_tokens"] if largest else None,
        "max_request": ({k: largest[k] for k in ("cell", "task_cell", "episode_id",
                                                  "request_index")} if largest else None),
        "over_threshold": [x for x in rows if x["claude_tokens"] > HAIKU_LONG_THRESHOLD],
    }


def _default_client() -> Any:
    import anthropic  # here, so that the $0 parts of this module never build a client

    return anthropic.Anthropic(max_retries=2, timeout=120.0)


def token_count(model: str, gen: GeneratorConfig, *, start: int = 0, n: int = 10,
                client_factory: Callable[[], Any] | None = None) -> dict:
    """The command (module docstring), as a dict to write and print. Refuses (`Refused`)
    before any request is generated or any client built: a model off the Messages wire, a
    model R8 does not register, --n below 1, or the credentials (`credential_refusal`); and
    before any request is sent, a client that holds a custom header
    (`client_header_refusal`)."""
    if wire_for(model) is not MESSAGES:
        raise Refused(f"count-tokens counts Claude tokens of Messages requests: {model} is not "
                      "a claude-* model")
    if registered.model_family(model) != registered.HAIKU_MODEL:
        raise Refused(f"count-tokens counts the requests of {registered.HAIKU_MODEL} (R8), "
                      f"got {model}")
    if n < 1 or start < 0:
        raise Refused(f"need --start >= 0 and --n >= 1, got --start {start} --n {n}")
    why = credential_refusal()
    if why:
        raise Refused(why)
    requests = largest_requests(model, gen, start=start, n=n)
    client = (client_factory or _default_client)()
    why = client_header_refusal(client)
    if why:
        raise Refused(why)
    report = count(requests, client)
    return {"model": model, "endpoint": "POST /v1/messages/count_tokens (free)",
            "generator_config_hash": runmeta.config_hash(gen.to_dict()),
            "templates": {"split": "main", "start": start, "n": n},
            "cells": [*registered.HAIKU_CELLS, registered.HAIKU_SINGLE_TURN_CELL],
            "counted_fields": list(COUNTED_FIELDS), "reply_note": REPLY_NOTE, **report,
            "generated_utc": runmeta.utc_now(), "prereg_version": runmeta.prereg_version(),
            "sdk_versions": runmeta.sdk_versions(), **runmeta.git_state()}
