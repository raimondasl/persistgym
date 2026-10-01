"""Payload builder: what one harness cell sends at every request of one episode.

A `HarnessSession` holds the client-side history of one episode (stateless Responses API:
`store: false`, nothing kept server-side) and turns each new observation into the exact JSON
body of `POST /v1/responses`. It does not talk to any API; a transport sends the payload and
hands the response back to `record`.

Flow per environment observation (see runner.run_episode):

    session.observe(obs)
    while True:
        req = session.next_request()      # a summary request first, if compaction is due
        resp = transport.send(req.payload)
        reply = session.record(req, resp)  # None after a summary request
        if req.kind == "step": break

History (PLAN §6):
* full: every earlier turn, verbatim.
* window: drop oldest whole turns (observation + the model's output items) so that the
  visible tokens of the kept turns plus the current observation (plus the episode's system
  prompt, if it counts; never the notes sentence) are at most W. This is
  `persistgym.survival.window_keep_start`, the model the generator used to design near and
  far. Dropped turns never come back.
* summary: when the same visible context would exceed W, first send a summary request (the
  history to compact, then ARC's summary request prompt), then replace the compacted turns
  with ONE user-role bridge message holding the summary (ARC's bridge template). With
  `summary_keep_recent_tokens` = 0 (default, as ARC) every earlier turn is compacted.

Token accounting is visible text only, counted with the generator's tokenizer: observation
text, the reply's output text and the bridge text. Encrypted reasoning items are opaque and
are not counted, so the window boundary and the summary trigger fall on the same steps in the
r and 0 arms of a pair (given the same replies).

Reasoning replay: every kept turn is sent with its reasoning items (`encrypted_content`) in
every cell. Only `reasoning.context` differs between r (`all_turns`) and 0 (`current_turn`).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from harnesses.cells import NOTES_INSTRUCTION, CellSpec
from harnesses.config import ENCRYPTED_REASONING, HarnessConfig
from harnesses.items import output_text, replay_items, user_message
from persistgym import tokens
from persistgym.survival import window_keep_start


class EmptySummaryError(RuntimeError):
    """The summary call returned no text or did not complete; the session is unchanged and
    the same summary request can be sent again."""


@dataclass
class Turn:
    index: int  # turn number in the episode (lookups add turns, so this is not the step)
    observation: str
    obs_tokens: int
    items: list[dict]  # the response's output items, sent back on later turns
    reply: str  # visible output text (what the environment scores)
    reply_tokens: int
    dropped_output_types: list[str] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return self.obs_tokens + self.reply_tokens


@dataclass
class Request:
    kind: str  # "step" | "summary"
    turn: int  # index of the pending turn (the observation being answered)
    payload: dict  # exact JSON body of POST /v1/responses
    trace: list[str]  # provenance of each payload["input"] item: U<t>, R<t>, A<t>, B<k>, Q
    info: dict  # loss-policy bookkeeping (never sent)


class HarnessSession:
    def __init__(self, cell: CellSpec, system_prompt: str, cfg: HarnessConfig, *,
                 W_tokens: int | None, count_system: bool):
        if cell.history != "full" and not W_tokens:
            raise ValueError(f"cell {cell.cell_id} needs W_tokens")
        if (cell.history == "summary" and W_tokens
                and cfg.summary_keep_recent_tokens >= W_tokens):
            raise ValueError("summary_keep_recent_tokens must be smaller than W")
        self.cell = cell
        self.cfg = cfg
        self.W = W_tokens
        self.count_system = count_system
        self.system_prompt = system_prompt
        self.instructions = (system_prompt + cfg.notes_separator + NOTES_INSTRUCTION
                             if cell.notes else system_prompt)
        # W counts the episode's system prompt only, never the notes sentence: the two cells
        # of a notes pair (W-n-0/W-0, Σ-n-r/Σ-0-r) then evict and compact at the same steps,
        # and the count equals the generator's Episode.system_tokens (PREREG D5).
        self.system_tokens = self._count(system_prompt) if count_system else 0
        self.turns: list[Turn] = []
        self.start = 0  # first turn still sent verbatim
        self.bridge: str | None = None
        self.bridge_no = 0
        self.bridge_tokens = 0
        self.compactions: list[dict] = []
        self.pending: str | None = None
        self.pending_tokens = 0

    @classmethod
    def for_episode(cls, cell: CellSpec, episode, cfg: HarnessConfig) -> HarnessSession:
        """Session for a persistgym Episode. W and whether the episode's system prompt counts
        (never the notes sentence) default to the episode's generator config, so eviction
        happens where near and far were designed."""
        ecfg = episode.config
        if cfg.tokenizer != ecfg["tokenizer"]:
            raise ValueError(f"harness tokenizer {cfg.tokenizer!r} differs from the "
                             f"generator's {ecfg['tokenizer']!r}")
        W = cfg.W_tokens if cfg.W_tokens is not None else ecfg["W_tokens"]
        count_system = (cfg.window_counts_system_prompt
                        if cfg.window_counts_system_prompt is not None
                        else ecfg["window_counts_system_prompt"])
        return cls(cell, episode.system_prompt, cfg, W_tokens=W, count_system=count_system)

    # ------------------------------------------------------------------
    def _count(self, text: str) -> int:
        return tokens.count(text, self.cfg.tokenizer)

    def context_tokens(self, start: int | None = None) -> int:
        """Visible tokens the next step request would hold if it sent turns[start:]."""
        start = self.start if start is None else start
        bridge = self.bridge_tokens if self.cell.history == "summary" else 0
        return (self.system_tokens + bridge + sum(t.tokens for t in self.turns[start:])
                + self.pending_tokens)

    def observe(self, observation: str) -> None:
        """Start a turn: the next environment observation (a new user message)."""
        if self.pending is not None:
            raise RuntimeError("the previous observation has not been answered")
        self.pending = observation
        self.pending_tokens = self._count(observation)

    # ------------------------------------------------------------------
    def next_request(self) -> Request:
        if self.pending is None:
            raise RuntimeError("observe() an observation first")
        if self.cell.history == "summary":
            plan = self._compaction_plan()
            if plan is not None:
                return self._summary_request(*plan)
            return self._step_request(self.start)
        if self.cell.history == "window":
            return self._step_request(max(self.start, self._window_start()))
        return self._step_request(0)

    def _window_start(self) -> int:
        obs = [t.obs_tokens for t in self.turns] + [self.pending_tokens]
        rep = [t.reply_tokens for t in self.turns]
        return window_keep_start(obs, rep, self.W, self.system_tokens)

    def _compaction_plan(self) -> tuple[int, int, int] | None:
        """(first, end, context tokens) of the turns to compact, or None if no compaction is
        due. Due when the visible context (bridge + turns since the last compaction + the
        current observation) exceeds W and at least one turn can be compacted."""
        total = self.context_tokens()
        n = len(self.turns)
        if total <= self.W or self.start >= n:
            return None
        keep = self.cfg.summary_keep_recent_tokens
        if keep == 0:
            return self.start, n, total
        obs = [t.obs_tokens for t in self.turns[self.start:]] + [self.pending_tokens]
        rep = [t.reply_tokens for t in self.turns[self.start:]]
        end = self.start + window_keep_start(obs, rep, keep, self.system_tokens)
        return self.start, max(end, self.start + 1), total

    # ------------------------------------------------------------------
    def _base_payload(self, instructions: str, input_items: list[dict],
                      max_output_tokens: int | None) -> dict:
        cfg = self.cfg
        reasoning = {"effort": cfg.reasoning_effort, "mode": cfg.reasoning_mode,
                     "context": self.cell.reasoning_context}
        if cfg.reasoning_summary is not None:
            reasoning["summary"] = cfg.reasoning_summary
        payload = {
            "model": cfg.model,
            "instructions": instructions,
            "input": copy.deepcopy(input_items),
            "reasoning": reasoning,
            "store": False,
            "include": [ENCRYPTED_REASONING],
            "service_tier": cfg.service_tier,
            "truncation": "disabled",
        }
        if max_output_tokens is not None:
            payload["max_output_tokens"] = max_output_tokens
        if cfg.prompt_cache_key is not None:
            payload["prompt_cache_key"] = cfg.prompt_cache_key
        return payload

    def _history(self, first: int, end: int) -> tuple[list[dict], list[str]]:
        items: list[dict] = []
        trace: list[str] = []
        if self.cell.history == "summary" and self.bridge is not None:
            items.append(user_message(self.bridge))
            trace.append(f"B{self.bridge_no}")
        for t in self.turns[first:end]:
            items.append(user_message(t.observation))
            trace.append(f"U{t.index}")
            for it in t.items:
                items.append(it)
                trace.append(f"R{t.index}" if it.get("type") == "reasoning" else f"A{t.index}")
        return items, trace

    def _step_request(self, start: int) -> Request:
        items, trace = self._history(start, len(self.turns))
        bridge_index = 0 if trace and trace[0].startswith("B") else None
        items.append(user_message(self.pending))
        trace.append(f"U{len(self.turns)}")
        ctx = self.context_tokens(start)
        info = {
            "history": self.cell.history, "W": self.W, "keep_start": start,
            "turns_not_verbatim": start, "context_tokens": ctx,
            "system_tokens_counted": self.system_tokens,
            "bridge_index": bridge_index, "bridge_no": self.bridge_no if bridge_index == 0 else 0,
            "over_W": bool(self.W) and ctx > self.W,
        }
        return Request("step", len(self.turns),
                       self._base_payload(self.instructions, items, self.cfg.max_output_tokens),
                       trace, info)

    def _summary_request(self, first: int, end: int, total: int) -> Request:
        items, trace = self._history(first, end)
        items.append(user_message(self.cfg.summary_request_prompt))
        trace.append("Q")
        instructions = (self.cfg.summary_system_prompt
                        if self.cfg.summary_system_prompt is not None else self.instructions)
        info = {
            "history": "summary", "W": self.W, "context_tokens": total,
            "compact_turns": [first, end], "bridge_in": self.bridge_no,
            "bridge_out": self.bridge_no + 1,
        }
        return Request("summary", len(self.turns),
                       self._base_payload(instructions, items,
                                          self.cfg.summary_max_output_tokens),
                       trace, info)

    # ------------------------------------------------------------------
    def record(self, request: Request, response: dict) -> str | None:
        """Take the response to `request`. Returns the visible reply for a step request and
        None for a summary request (after which `next_request` gives the step request)."""
        if request.turn != len(self.turns) or self.pending is None:
            raise RuntimeError("response does not belong to the pending request")
        if request.kind == "summary":
            text = output_text(response).strip()
            status = response.get("status")
            if not text or (status is not None and status != "completed"):
                raise EmptySummaryError(f"summary status={status!r}, {len(text)} chars")
            first, end = request.info["compact_turns"]
            self.bridge = self.cfg.summary_bridge_template.format(summary=text)
            self.bridge_no += 1
            self.bridge_tokens = self._count(self.bridge)
            self.start = end
            self.compactions.append({
                "at_turn": request.turn, "compacted_turns": [first, end],
                "bridge_no": self.bridge_no, "bridge_tokens": self.bridge_tokens,
                "context_tokens_before": request.info["context_tokens"],
                "summary_text": text,
            })
            return None
        items, dropped = replay_items(response)
        reply = output_text(response)
        self.turns.append(Turn(len(self.turns), self.pending, self.pending_tokens, items, reply,
                               self._count(reply), dropped))
        if self.cell.history == "window":
            self.start = request.info["keep_start"]
        self.pending = None
        self.pending_tokens = 0
        return reply
