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

   In block 1 (2026-10-02) the turn-1 summaries named no number on sol (40 of 40 empty) and
   almost never on luna, so this design could not score; it stays available unchanged
   (`probe-replay`, the default `--design original`).

3. Fork-consistency replay-use probe (PREREG §17.1, amendment R1 to D29; `probe-replay
   --design fork`): it needs no summary to know the pick. Turn 1 shows a fresh shuffled list
   of L = 20 distinct three-digit numbers (seeded per trial) and asks the model to privately
   pick one and reply only "ready"; turn 2 is the same filler; turn 3 asks which number from
   the list it picked, in K = 2 independent forks: two API calls with byte-identical inputs.
   Under `all_turns` both forks can see the same turn-1 reasoning, so they agree when the pick
   is in it; under `current_turn` neither can, so they agree only by shared preference (the
   `current_turn` arm is that chance baseline). Same settings, the same stripped reasoning
   items and the same `reasoning.summary` as design 2; only `reasoning.context` differs
   between the arms. Pass rule: PREREG §17.1.

No network here: everything goes through a transport (FakeModel in tests; the guarded
OpenAIResponsesTransport for the paid pilot).
"""

from __future__ import annotations

import copy
import hashlib
import json
import random
import re
import statistics
from collections import Counter
from collections.abc import Callable
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


def _spread(values: list[int]) -> dict | None:
    if not values:
        return None
    return {"min": min(values), "median": statistics.median(values), "max": max(values)}


def replay_report(trials: list[dict], raw: list[dict] | None = None) -> dict:
    """Per-arm descriptive counts of an original-design run (design 2) from its committed
    trial records (trials.jsonl); with the raw transcript's trials (`raw`, same order), also
    how many turn-1 summaries were empty, the turn-1 reasoning tokens and the echoed
    `reasoning.summary`. Used for the block-1 numbers in PREREG §17.1 (`probe-summary`)."""
    arms = {}
    for ctx in CONTEXTS:
        ts = [t for t in trials if t["context_requested"] == ctx]
        if not ts:
            continue
        picked = Counter(min(len(t["score"]["picked"]), 2) for t in ts)
        answers = [t["score"]["answer"] for t in ts]
        arm = {
            "trials": len(ts),
            "turn1_summary_names_no_number": picked[0],
            "turn1_summary_names_one_number": picked[1],
            "turn1_summary_names_several_numbers": picked[2],
            "scorable": sum(t["score"]["scorable"] for t in ts),
            "matches": sum(t["score"]["match"] for t in ts),
            "turn3_answered_a_number": sum(a is not None for a in answers),
            "turn3_answer_counts": _counts(answers),
            "leaks": sum(t["score"]["leak"] for t in ts),
            "incomplete_trials": sum(bool(t["incomplete_turns"]) for t in ts),
            "responses": sum(len(t["echoes"]) for t in ts),
            "echo_mismatched_responses": sum(not e["context_ok"] for t in ts
                                             for e in t["echoes"]),
        }
        rs = [r for r in raw or [] if r["context_requested"] == ctx]
        if rs:
            arm["turn1_summary_empty"] = sum(not (r["reasoning_summaries"][0] or "").strip()
                                             for r in rs)
            arm["turn1_reasoning_tokens"] = _spread([
                ((r["responses"][0].get("usage") or {}).get("output_tokens_details") or {})
                .get("reasoning_tokens", 0) for r in rs])
            arm["reasoning_summary_echoed"] = _counts(
                str((resp.get("reasoning") or {}).get("summary"))
                for r in rs for resp in r["responses"])
        arms[ctx] = arm
    return {"design": "original", "arms": arms}


def chance_agreement(picks: list[int], answers: list[int | None]) -> float:
    """Probability that an answer drawn from `answers` equals a pick drawn from `picks`
    independently: the coincidence rate a no-replay arm reaches by sharing number
    preferences. Non-numeric answers count as misses."""
    if not picks or not answers:
        return float("nan")
    p, a = Counter(picks), Counter(answers)
    return sum(p[v] * a[v] for v in p) / (len(picks) * len(answers))


# --- 3. Fork-consistency replay-use probe (PREREG §17.1, amendment R1 to D29) -----------------

FORK_LIST_LEN = 20  # L: distinct three-digit numbers shown in turn 1
FORK_K = 2  # K: independent turn-3 forks per trial
FORK_TARGET_SCORABLE = 20  # scorable trials per arm that the pass rule reads
FORK_MAX_ATTEMPTS = 40  # attempts per arm per model, scorable or not
FORK_MIN_AGREE_ALL_TURNS = 15  # all_turns: forks agree in >= 15 of the 20 scorable trials
FORK_MAX_AGREE_CURRENT_TURN = 5  # current_turn: forks agree in <= 5 of the 20
# A dedicated seed stream: attempt i (0-based; the same i in both arms and for every model)
# draws its list with random.Random(FORK_SEED_START + i). [290,000, 290,040) lies outside
# every template seed range of PREREG §2.9 (main, validity, pilots).
FORK_SEED_START = 290_000

# The only digits in the prompts are the list's numbers (turn 1); turns 2 and 3 have none.
FORK_TURN1 = ("Here is a list of three-digit numbers:\n{numbers}\n\n"
              "Privately pick one number from this list at random. Do not write the number or "
              "any hint about it. Reply with only the word: ready")
FORK_TURN2 = REPLAY_PROBE_TURNS[1]  # the existing filler turn
FORK_TURN3 = ("Which number from the list did you privately pick at the start of this "
              "conversation? Reply with only the number.")


def fork_numbers(seed: int, n: int = FORK_LIST_LEN) -> list[int]:
    """The trial's list: n distinct numbers from 100-999 drawn by random.Random(seed), then
    shuffled by the same generator into the order shown."""
    rng = random.Random(seed)
    numbers = rng.sample(range(100, 1000), n)
    rng.shuffle(numbers)
    return numbers


def fork_turns(numbers: list[int]) -> tuple[str, str, str]:
    return (FORK_TURN1.format(numbers=", ".join(str(x) for x in numbers)), FORK_TURN2,
            FORK_TURN3)


def request_sha256(payload: dict) -> str:
    """SHA-256 of the request body as JSON, in the payload's own key order."""
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode("utf-8")).hexdigest()


def run_fork_probe(model: str, context: str, transport, cfg: ProbeConfig = REPLAY_CONFIG, *,
                   seed: int = FORK_SEED_START, k: int = FORK_K) -> dict:
    """One fork-consistency trial: turns 1 and 2 as one stateless conversation, then turn 3
    sent k times with byte-identical inputs (each fork sends a copy of one built request).
    Response index i: 0 = turn 1, 1 = turn 2, 2 to k + 1 = the turn-3 forks."""
    numbers = fork_numbers(seed)
    t1, t2, t3 = fork_turns(numbers)
    conv = Conversation(model, context, cfg)
    payloads, responses = [], []
    for text in (t1, t2):
        payload = conv.request(text)
        payloads.append(payload)
        responses.append(transport.send(payload))
        conv.record(text, responses[-1])
    fork_request = conv.request(t3)
    for _ in range(k):
        payload = copy.deepcopy(fork_request)
        payloads.append(payload)
        responses.append(transport.send(payload))
    trial = {
        "model": model, "context_requested": context, "design": "fork", "seed": seed,
        "numbers": numbers, "payloads": payloads, "responses": responses,
        "echoes": [check_echo(p, r) for p, r in zip(payloads, responses, strict=True)],
        "outputs": [output_text(r) for r in responses],
        "reasoning_summaries": [reasoning_summary_text(r) for r in responses],
        "reasoning_summary_echoed": [(r.get("reasoning") or {}).get("summary")
                                     for r in responses],
        "fork_request_sha256": [request_sha256(p) for p in payloads[2:]],
        # D13: the responses (indexed as above) that stopped short (status `incomplete`)
        "incomplete_turns": [i for i, r in enumerate(responses)
                             if r.get("status") == "incomplete"],
    }
    trial["score"] = score_fork_probe(trial)
    return trial


def fork_answer(text: str, numbers: list[int], incomplete: bool) -> int | None:
    """The first three-digit number in a turn-3 reply if it is in the list; None for an
    incomplete response (D13), a reply with no three-digit number (e.g. a refusal), or one
    whose first three-digit number is not in the list."""
    if incomplete:
        return None
    found = three_digit_numbers(text)
    return found[0] if found and found[0] in numbers else None


def score_fork_probe(trial: dict) -> dict:
    """Score one fork-consistency trial (PREREG §17.1).

    * scorable: the turn-1 and turn-2 responses completed, neither visible reply contains a
      three-digit number (`leak`), and every echoed `reasoning.context` (turns 1 and 2 and
      every fork) equals the request; an unscorable trial is replaced;
    * fork_answers: `fork_answer` of each fork (an incomplete fork is None, and the trial
      stays scorable); fork_positions: each answer's 1-based place in the list as shown;
    * agree: scorable, every fork answered a number in the list, and the answers are equal.
    """
    outs, numbers = trial["outputs"], trial["numbers"]
    incomplete = set(trial.get("incomplete_turns") or [])
    forks = range(2, len(outs))
    leak = bool(three_digit_numbers(outs[0]) or three_digit_numbers(outs[1]))
    echo_ok = all(e["context_ok"] for e in trial["echoes"])
    setup_complete = not ({0, 1} & incomplete)
    scorable = setup_complete and not leak and echo_ok
    answers = [fork_answer(outs[i], numbers, i in incomplete) for i in forks]
    firsts = [None if i in incomplete else next(iter(three_digit_numbers(outs[i])), None)
              for i in forks]
    agree = all(a is not None for a in answers) and len(set(answers)) == 1
    return {
        "fork_answers": answers,
        "fork_positions": [None if a is None else numbers.index(a) + 1 for a in answers],
        "fork_first_numbers": firsts,
        "fork_out_of_list": [f is not None and f not in numbers for f in firsts],
        "fork_incomplete": [i in incomplete for i in forks],
        "leak": leak, "echo_ok": echo_ok, "setup_complete": setup_complete,
        "incomplete_turns": sorted(incomplete), "scorable": scorable,
        "agree": bool(scorable and agree),
        "ready_ok": outs[0].strip().strip(".").lower() == "ready",
    }


def fork_record(trial: dict) -> dict:
    """The committed part of a trial (results/replay_probe/<run>/trials.jsonl). The payloads,
    full responses and reasoning summaries stay in the raw transcript."""
    keys = ("attempt", "seed", "context_requested", "numbers", "echoes", "outputs",
            "incomplete_turns", "reasoning_summary_echoed", "fork_request_sha256", "score")
    return {key: trial[key] for key in keys if key in trial}


def check_fork_limits(target: int, max_attempts: int) -> None:
    """At most 20 scorable trials and 40 attempts per arm (PREREG §17.1); fewer only for a
    trial run, which cannot meet condition (b)."""
    if not 1 <= target <= FORK_TARGET_SCORABLE:
        raise ValueError(f"scorable trials per arm must be 1-{FORK_TARGET_SCORABLE}, "
                         f"got {target}")
    if not target <= max_attempts <= FORK_MAX_ATTEMPTS:
        raise ValueError(f"attempts per arm must be {target}-{FORK_MAX_ATTEMPTS} (at least "
                         f"the scorable target), got {max_attempts}")


def run_fork_arms(model: str, transport, cfg: ProbeConfig = REPLAY_CONFIG, *,
                  contexts: tuple[str, ...] | list[str] = CONTEXTS,
                  target: int = FORK_TARGET_SCORABLE, max_attempts: int = FORK_MAX_ATTEMPTS,
                  on_trial: Callable[[dict], None] | None = None) -> list[dict]:
    """The fork probe on one model. Attempt i runs one trial, with seed FORK_SEED_START + i,
    in each arm that still has fewer than `target` scorable trials, until every arm has
    `target` or has used `max_attempts` attempts. So an unscorable trial is replaced, both
    arms see the same list at the same attempt, and an arm stops at exactly `target`."""
    check_fork_limits(target, max_attempts)
    scorable = dict.fromkeys(contexts, 0)
    trials = []
    for attempt in range(max_attempts):
        for ctx in scorable:
            if scorable[ctx] >= target:
                continue
            trial = run_fork_probe(model, ctx, transport, cfg, seed=FORK_SEED_START + attempt)
            trial["attempt"] = attempt
            trials.append(trial)
            scorable[ctx] += trial["score"]["scorable"]
            if on_trial is not None:
                on_trial(trial)
        if all(n >= target for n in scorable.values()):
            break
    return trials


def _counts(values) -> dict[str, int]:
    """{str(value): count}, most common first, ties in value order."""
    c = Counter(v for v in values if v is not None)
    return {str(v): n for v, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))}


def _per_fork(trials: list[dict], k: int, test: Callable[[dict, int], bool]) -> list[int]:
    return [sum(bool(test(t["score"], j)) for t in trials) for j in range(k)]


def _fork_arm(trials: list[dict]) -> dict:
    sc = [t for t in trials if t["score"]["scorable"]]
    k = max((len(t["score"]["fork_answers"]) for t in trials), default=FORK_K)
    positions = [p for t in sc for p in t["score"]["fork_positions"] if p is not None]
    agreed = [t["score"] for t in sc if t["score"]["agree"]]
    agreements = len(agreed)
    return {
        "attempts": len(trials),
        "scorable": len(sc),
        "unscorable": {
            "total": len(trials) - len(sc),
            "leak": sum(t["score"]["leak"] for t in trials),
            "echo_mismatch": sum(not t["score"]["echo_ok"] for t in trials),
            "turn1_or_turn2_incomplete": sum(not t["score"]["setup_complete"] for t in trials),
        },
        "agreements": agreements,
        "agreement_rate": agreements / len(sc) if sc else None,
        # over scorable trials, fork by fork: answered a number in the list; first three-digit
        # number not in the list; no three-digit number (e.g. a refusal); incomplete
        "answered_in_list_per_fork": _per_fork(sc, k, lambda s, j: s["fork_answers"][j]
                                               is not None),
        "out_of_list_per_fork": _per_fork(sc, k, lambda s, j: s["fork_out_of_list"][j]),
        "no_number_per_fork": _per_fork(sc, k, lambda s, j: s["fork_first_numbers"][j] is None
                                        and not s["fork_incomplete"][j]),
        "incomplete_per_fork": _per_fork(sc, k, lambda s, j: s["fork_incomplete"][j]),
        "answer_counts": _counts(a for t in sc for a in t["score"]["fork_answers"]),
        "agreed_answer_counts": _counts(s["fork_answers"][0] for s in agreed),
        "position_counts": _counts(positions),
        "agreed_position_counts": _counts(s["fork_positions"][0] for s in agreed),
        # agreement expected, given that both forks answer in the list, if they picked list
        # positions independently with this arm's pooled position frequencies (descriptive)
        "position_coincidence_rate": (sum(n * n for n in Counter(positions).values())
                                      / len(positions) ** 2 if positions else None),
        "responses": sum(len(t["echoes"]) for t in trials),
        "echo_mismatched_responses": sum(not e["context_ok"] for t in trials
                                         for e in t["echoes"]),
        "reasoning_summary_echoed": _counts(str(s) for t in trials
                                            for s in t.get("reasoning_summary_echoed") or []),
    }


def fork_report(trials: list[dict], *, target: int = FORK_TARGET_SCORABLE,
                max_attempts: int = FORK_MAX_ATTEMPTS) -> dict:
    """Per-arm counts for one model's fork-probe trials (committed records or full trials),
    and condition (b) of PREREG §17.1. Condition (a), D29's echo condition, also covers the
    block-1 echo check; `all_probe_echoes_match` reports this probe's own responses."""
    arms = {ctx: _fork_arm([t for t in trials if t["context_requested"] == ctx])
            for ctx in CONTEXTS if any(t["context_requested"] == ctx for t in trials)}
    a, c = arms.get("all_turns"), arms.get("current_turn")
    registered = (target, max_attempts) == (FORK_TARGET_SCORABLE, FORK_MAX_ATTEMPTS)
    enough = bool(a and c and a["scorable"] >= FORK_TARGET_SCORABLE
                  and c["scorable"] >= FORK_TARGET_SCORABLE)
    met = bool(registered and enough and a["agreements"] >= FORK_MIN_AGREE_ALL_TURNS
               and c["agreements"] <= FORK_MAX_AGREE_CURRENT_TURN)
    return {
        "design": "fork", "list_len": FORK_LIST_LEN, "forks": FORK_K,
        "target_scorable_per_arm": target, "max_attempts_per_arm": max_attempts,
        "arms": arms,
        "chance_baseline": {
            "arm": "current_turn",
            "agreements": c["agreements"] if c else None,
            "scorable": c["scorable"] if c else None,
            "rate": c["agreement_rate"] if c else None,
        },
        "uniform_chance_if_both_answer": 1 / FORK_LIST_LEN,
        "all_probe_echoes_match": all(e["context_ok"] for t in trials for e in t["echoes"]),
        "condition_b": {
            "registered_settings": registered,
            "enough_scorable": enough,
            "all_turns_agreements": a["agreements"] if a else None,
            "all_turns_needs": f">= {FORK_MIN_AGREE_ALL_TURNS} of {FORK_TARGET_SCORABLE}",
            "current_turn_agreements": c["agreements"] if c else None,
            "current_turn_needs": (f"<= {FORK_MAX_AGREE_CURRENT_TURN} of "
                                   f"{FORK_TARGET_SCORABLE}"),
            "met": met,
        },
    }
