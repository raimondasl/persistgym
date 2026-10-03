"""Programmatic oracles and the policy runner (PLAN §5 validity gate: the oracle scores 100%).

* `KeyOracle` replies with the answer key. It checks scoring and the runner.
* `TextOracle` reads only the text an agent sees (system prompt and observations) and
  answers by parsing it. With memory it must score 100% on base and restated episodes of
  every cell: this checks that the information needed is actually in the text, that routine
  steps are answerable from the current observation alone, and that derived facts are
  computable from the shown clues and rule.
* `TextOracle(memory=False, use_lookup=True)` forgets every earlier observation and uses
  lookup at the need step. It must score 100% on recoverable cells (checks lookup).

A policy is any object with `reset(system_prompt)` and `act(observation, info) -> reply`.
`info` is runner bookkeeping (pending step index) used only by `KeyOracle`.
"""

from __future__ import annotations

import re
from typing import Protocol

from persistgym.env import EpisodeEnv, EpisodeResult
from persistgym.episode import Episode

FACT_RE = re.compile(r"For ([a-z]+) ([A-Z][A-Z]+), the ([a-z ]+?) is (\d+)\.")
RELATION_RE = re.compile(r"For ([a-z]+) ([A-Z][A-Z]+), the ([a-z ]+?) is (\d+) (more|less) "
                         r"than for \1 ([A-Z][A-Z]+)\.")
"""Chain form (PREREG §17.3; `render.relation_sentence`): entity's value is the other
entity's value plus or minus a difference."""
MAX_RELATION_DEPTH = 4
RULE_RE = re.compile(r"Rule: for every ([a-z]+), ([a-z ]+?) = ([a-z ]+(?: \+ [a-z ]+)+)\.")
NEED_RE = re.compile(r"([A-Z][a-z]+) ([A-Z][A-Z]+) needs its ([a-z ]+?) now\. Options:")
OPTION_RE = re.compile(r"^([A-Z])\) (\d+)$", re.MULTILINE)
NEED_VERB_RE = re.compile(r"Reply ([a-z_]+)\(<letter>\)")
ROUTE_RE = re.compile(r"with tag '([^']+)'\. Route it")
SENSOR_RE = re.compile(r"Sensor (\S+) reports .+? (\d+) [^;]*; the limit is (\d+) ")
ACK_RE = re.compile(r"Reply ack\(([^)<>]+)\)")
EVENT_MARK = "\n--- end of log ---\nEVENT: "
PENDING_MARK = "Pending request (repeated): "


class Policy(Protocol):
    def reset(self, system_prompt: str) -> None: ...

    def act(self, observation: str, info: dict) -> str: ...


def run_episode(ep: Episode, policy: Policy, max_turns: int = 1000) -> EpisodeResult:
    env = EpisodeEnv(ep)
    policy.reset(ep.system_prompt)
    obs, done = env.observation, False
    for _ in range(max_turns):
        obs, done = env.step(policy.act(obs, env.info))
        if done:
            break
    if not done:
        raise RuntimeError("episode did not finish")
    return env.result()


class KeyOracle:
    def __init__(self, ep: Episode):
        self.ep = ep

    def reset(self, system_prompt: str) -> None:
        pass

    def act(self, observation: str, info: dict) -> str:
        return f"ACTION: {self.ep.steps[info['pending_step']].expected_action}"


class TextOracle:
    def __init__(self, memory: bool = True, use_lookup: bool = False):
        self.memory = memory
        self.use_lookup = use_lookup

    def reset(self, system_prompt: str) -> None:
        self.lookup_allowed = "lookup(<" in system_prompt
        self.base_rules = self._rules(system_prompt)
        self.facts: dict[tuple[str, str], int] = {}
        # chain form: (entity, quantity) -> (signed difference, other entity)
        self.relations: dict[tuple[str, str], tuple[int, str]] = {}
        self.rules: dict[str, list[str]] = dict(self.base_rules)
        self.looked_up = False

    @staticmethod
    def _rules(text: str) -> dict[str, list[str]]:
        return {m.group(2): m.group(3).split(" + ") for m in RULE_RE.finditer(text)}

    def remember(self, text: str) -> None:
        """Parse the bindings, relations and rules in `text` into memory."""
        for m in FACT_RE.finditer(text):
            self.facts[(m.group(2), m.group(3))] = int(m.group(4))
        for m in RELATION_RE.finditer(text):
            sign = 1 if m.group(5) == "more" else -1
            self.relations[(m.group(2), m.group(3))] = (sign * int(m.group(4)), m.group(6))
        self.rules.update(self._rules(text))

    def _resolve(self, entity: str, name: str, seen: frozenset) -> int | None:
        """A value given directly, or through relations at most `MAX_RELATION_DEPTH` hops
        long; None for a cycle or a value that is not given."""
        key = (entity, name)
        if key in self.facts:
            return self.facts[key]
        if key not in self.relations or key in seen or len(seen) >= MAX_RELATION_DEPTH:
            return None
        delta, other = self.relations[key]
        base = self._resolve(other, name, seen | {key})
        return None if base is None else base + delta

    def value_of(self, entity: str, quantity: str) -> int | None:
        direct = self._resolve(entity, quantity, frozenset())
        if direct is not None:
            return direct
        parts = self.rules.get(quantity)
        if not parts:
            return None
        vals = [self._resolve(entity, p, frozenset()) for p in parts]
        return None if None in vals else sum(vals)

    def act(self, observation: str, info: dict) -> str:
        if not self.memory:
            self.facts, self.relations, self.rules = {}, {}, dict(self.base_rules)
        event = observation.split(EVENT_MARK, 1)[1] if EVENT_MARK in observation else ""
        self.remember(event)
        request = event.split(PENDING_MARK, 1)[1] if PENDING_MARK in event else event

        need = NEED_RE.search(request)
        if need:
            _, entity, quantity = need.groups()
            options = [(lab, int(v)) for lab, v in OPTION_RE.findall(request)]
            verb = NEED_VERB_RE.search(request).group(1)
            value = self.value_of(entity, quantity)
            if value is None and self.use_lookup and self.lookup_allowed and not self.looked_up:
                self.looked_up = True
                return f"I need the earlier record.\nACTION: lookup({entity})"
            self.looked_up = False
            label = next((lab for lab, v in options if v == value), options[0][0])
            return f"ACTION: {verb}({label})"
        if m := ROUTE_RE.search(request):
            return f"ACTION: route({m.group(1)})"
        if m := SENSOR_RE.search(request):
            sensor, x, limit = m.group(1), int(m.group(2)), int(m.group(3))
            return f"ACTION: {'alert' if x > limit else 'ok'}({sensor})"
        if m := ACK_RE.search(request):
            return f"ACTION: ack({m.group(1)})"
        return "ACTION: none()"
