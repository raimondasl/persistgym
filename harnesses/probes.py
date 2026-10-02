"""Pilot probes for the reasoning-replay toggle (PLAN §7, §11 G0; amendment §16.3).

1. Echo check (~$0.35 in PLAN §16.2): for gpt-6.1-sol and gpt-6-luna, a two-turn stateless
   conversation with `reasoning.context` = `all_turns` or `current_turn`. The Responses API
   reports the effective mode in the response's `reasoning.context`
   (https://developers.openai.com/api/docs/guides/reasoning: "Check this field on each
   response to confirm which mode the model used"). Pass = every response echoes the request.

2. Private-choice replay-use probe (~$2, §16.3): turn 1 asks the model to privately pick a
   random three-digit number and reply only "ready"; turn 2 is filler; turn 3 asks for the
   number. Both arms send identical payloads except `reasoning.context`. Under `all_turns`
   the turn-3 sample can see the turn-1 reasoning; under `current_turn` it cannot.

   Scoring needs the picked number, which lives only in the encrypted reasoning. Both arms
   therefore request reasoning summaries (`reasoning.summary`, identical in both arms) and a
   trial is scorable when the turn-1 summary names exactly one three-digit number and no
   visible reply leaks one. The summary text is stripped from the reasoning items sent back
   (`strip_summaries_on_replay`), so the only channel for the number is the encrypted
   reasoning. Chance is 1/900 only for uniform guesses: models pick "random" numbers
   unevenly, so report the coincidence rate `chance_agreement(picks, answers)` next to the
   match rates. The probe is excluded from every analysis.

No network here: everything goes through a transport (FakeModel in tests; the guarded
OpenAIResponsesTransport for the paid pilot).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from harnesses.config import DEFAULT_MAX_OUTPUT_TOKENS, ENCRYPTED_REASONING, require_output_cap
from harnesses.items import output_text, reasoning_summary_text, replay_items, user_message
from harnesses.runner import check_echo

ECHO_CHECK_MODELS = ("gpt-6.1-sol", "gpt-6-luna")
CONTEXTS = ("all_turns", "current_turn")

ECHO_CHECK_TURNS = (
    "This is a short connectivity check. Reply with only the word: ready",
    "Reply with only the word: done",
)

# No digits in the prompts, so any three-digit number in a summary or reply came from the model.
REPLAY_PROBE_TURNS = (
    ("Privately pick a random three-digit number. Do not write the number or any hint about "
     "it. Reply with only the word: ready"),
    "Unrelated question: what is the capital of France? Reply with only the city name.",
    ("What is the three-digit number you privately picked at the start of this conversation? "
     "Reply with only the number."),
)

THREE_DIGITS = re.compile(r"(?<![0-9])([1-9][0-9]{2})(?![0-9])")


@dataclass(frozen=True)
class ProbeConfig:
    reasoning_effort: str = "medium"
    reasoning_mode: str = "standard"
    reasoning_summary: str | None = None
    service_tier: str = "flex"
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    """Sent on every probe request (PREREG D13: 32,000, as in the harness cells)."""
    instructions: str | None = None
    strip_summaries_on_replay: bool = True

    def __post_init__(self) -> None:
        require_output_cap("max_output_tokens", self.max_output_tokens)


ECHO_CONFIG = ProbeConfig()
REPLAY_CONFIG = ProbeConfig(reasoning_summary="auto")


class Conversation:
    """A stateless multi-turn conversation: every request re-sends the earlier turns (user
    message, then the response's reasoning and message items)."""

    def __init__(self, model: str, context: str, cfg: ProbeConfig):
        if context not in CONTEXTS:
            raise ValueError(f"context must be one of {CONTEXTS}")
        self.model, self.context, self.cfg = model, context, cfg
        self.history: list[dict] = []

    def request(self, user_text: str) -> dict:
        cfg = self.cfg
        reasoning = {"effort": cfg.reasoning_effort, "mode": cfg.reasoning_mode,
                     "context": self.context}
        if cfg.reasoning_summary is not None:
            reasoning["summary"] = cfg.reasoning_summary
        payload = {"model": self.model}
        if cfg.instructions is not None:
            payload["instructions"] = cfg.instructions
        payload.update({
            "input": [*self.history, user_message(user_text)],
            "reasoning": reasoning,
            "store": False,
            "include": [ENCRYPTED_REASONING],
            "service_tier": cfg.service_tier,
            "truncation": "disabled",
            "max_output_tokens": cfg.max_output_tokens,
        })
        return payload

    def record(self, user_text: str, response: dict) -> None:
        items, _ = replay_items(response)
        if self.cfg.strip_summaries_on_replay:
            items = [{**i, "summary": []} if i.get("type") == "reasoning" else i for i in items]
        self.history += [user_message(user_text), *items]


def _converse(model: str, context: str, turns: tuple[str, ...], transport,
              cfg: ProbeConfig) -> dict:
    conv = Conversation(model, context, cfg)
    payloads, responses, echoes = [], [], []
    for text in turns:
        payload = conv.request(text)
        response = transport.send(payload)
        payloads.append(payload)
        responses.append(response)
        echoes.append(check_echo(payload, response))
        conv.record(text, response)
    return {"model": model, "context_requested": context, "payloads": payloads,
            "responses": responses, "echoes": echoes,
            "outputs": [output_text(r) for r in responses],
            "reasoning_summaries": [reasoning_summary_text(r) for r in responses],
            # D13: the turns (0-based) whose response stopped short (status `incomplete`)
            "incomplete_turns": [i for i, r in enumerate(responses)
                                 if r.get("status") == "incomplete"]}


def run_echo_check(model: str, context: str, transport, cfg: ProbeConfig = ECHO_CONFIG) -> dict:
    trial = _converse(model, context, ECHO_CHECK_TURNS, transport, cfg)
    trial["echo_ok"] = all(e["context_ok"] for e in trial["echoes"])
    trial["context_echoed"] = [e["context_echoed"] for e in trial["echoes"]]
    trial["model_returned"] = [e["model_returned"] for e in trial["echoes"]]
    return trial


def run_replay_probe(model: str, context: str, transport,
                     cfg: ProbeConfig = REPLAY_CONFIG) -> dict:
    trial = _converse(model, context, REPLAY_PROBE_TURNS, transport, cfg)
    trial["score"] = score_replay_probe(trial)
    return trial


def three_digit_numbers(text: str) -> list[int]:
    return [int(m) for m in THREE_DIGITS.findall(text or "")]


def score_replay_probe(trial: dict) -> dict:
    """Score one replay-probe trial.

    * picked: the distinct three-digit numbers in the turn-1 reasoning summary;
    * leak: a three-digit number in the visible turn-1 or turn-2 reply;
    * answer: the first three-digit number in the turn-3 reply (None if there is none, e.g.
      the model says it cannot recall, or if the turn-3 response is incomplete: an invalid
      answer whatever its partial text says, D13);
    * scorable: exactly one picked number, no leak, every echo matches the request, and the
      turn-1 and turn-2 responses completed (an incomplete one leaves the set-up unclear,
      so the trial is replaced like a leak);
    * match: scorable and answer == picked.
    """
    outs = trial["outputs"]
    incomplete = trial.get("incomplete_turns") or []
    picked = sorted(set(three_digit_numbers(trial["reasoning_summaries"][0])))
    leak = bool(three_digit_numbers(outs[0]) or three_digit_numbers(outs[1]))
    answers = [] if 2 in incomplete else three_digit_numbers(outs[2])
    answer = answers[0] if answers else None
    echo_ok = all(e["context_ok"] for e in trial["echoes"])
    setup_complete = not ({0, 1} & set(incomplete))
    scorable = len(picked) == 1 and not leak and echo_ok and setup_complete
    return {
        "picked": picked, "answer": answer, "answered_a_number": answer is not None,
        "leak": leak, "echo_ok": echo_ok, "incomplete_turns": list(incomplete),
        "scorable": scorable, "match": bool(scorable and answer == picked[0]),
        "ready_ok": outs[0].strip().strip(".").lower() == "ready",
    }


def chance_agreement(picks: list[int], answers: list[int | None]) -> float:
    """Probability that an answer drawn from `answers` equals a pick drawn from `picks`
    independently: the coincidence rate a no-replay arm reaches by sharing number
    preferences. Non-numeric answers count as misses."""
    if not picks or not answers:
        return float("nan")
    p, a = Counter(picks), Counter(answers)
    return sum(p[v] * a[v] for v in p) / (len(picks) * len(answers))
