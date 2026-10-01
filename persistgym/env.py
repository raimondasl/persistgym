"""Episode runner: action parsing, scoring and lookup semantics.

The scripted observations come from the Episode. The runner adds one dynamic behaviour:

Lookup (recoverable cells only; PREREG D3). If the reply's action is `lookup(<key>)` and the
episode still has lookups left, the pending step is NOT scored and does not advance. The next
observation is a lookup result (padded to v tokens like every observation) that re-shows
every record displayed at or before the pending step about an entity named in the key (the
target or a distractor; whole word, ignoring case: `render.lookup_key_matches`), then repeats
the pending EVENT. So a lookup costs exactly one extra turn. A key with no such record shown
yet returns "no such record" and also costs the turn.

Once `lookup_max_per_episode` lookups are used, the next lookup at a pending step returns
"lookup unavailable" and the pending EVENT again: it costs one turn, is not counted as a
lookup and is not an answer, so the step is still scored on the agent's next action. A
second over-cap lookup at the same pending step is an invalid action (this keeps episodes
finite). In non-recoverable cells `lookup` is not offered, and a lookup is an invalid action:
the pending step is scored wrong and the episode advances (no extra turn).

Any other reply is scored against the pending step and the episode advances. A reply with no
parseable action is scored wrong (no re-prompt).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from persistgym.episode import Episode

ACTION_LINE = re.compile(r"ACTION:\s*(.+)", re.IGNORECASE)
CALL = re.compile(r"([A-Za-z_]+)\s*\(\s*([^()]*?)\s*\)")


@dataclass
class ParsedAction:
    verb: str | None
    arg: str | None
    raw: str


def parse_action(reply: str, known_verbs: set[str], strict: bool = False) -> ParsedAction | None:
    """The reply's action: the last 'ACTION: verb(arg)' line; if there is none and not strict,
    the last call 'verb(arg)' with a known verb anywhere in the reply."""
    lines = ACTION_LINE.findall(reply or "")
    if lines:
        cand = lines[-1].strip()
        m = CALL.search(cand)
        if m:
            return ParsedAction(m.group(1).lower(), _clean_arg(m.group(2)), cand)
        return ParsedAction(None, None, cand)
    if strict:
        return None
    calls = [m for m in CALL.finditer(reply or "") if m.group(1).lower() in known_verbs]
    if not calls:
        return None
    m = calls[-1]
    return ParsedAction(m.group(1).lower(), _clean_arg(m.group(2)), m.group(0))


def _clean_arg(arg: str) -> str:
    return arg.strip().strip("'\"<>` ").strip()


def need_label(parsed: ParsedAction | None, need_verb: str, options: list[tuple[str, int]],
               accept_values: bool) -> str | None:
    """Option letter a need-step action resolves to (None if it resolves to none). Shared by
    `EpisodeEnv` and the single-turn control scorer, so both score the same way."""
    if parsed is None or parsed.verb != need_verb.lower() or not parsed.arg:
        return None
    arg = parsed.arg.strip().upper().rstrip(")")
    if arg in {label for label, _ in options}:
        return arg
    if accept_values and arg.isdigit():
        for label, value in options:
            if value == int(arg):
                return label
    return None


def canonical(action: str) -> str:
    m = CALL.fullmatch(action.strip())
    if not m:
        return action.strip().lower()
    return f"{m.group(1).lower()}({_clean_arg(m.group(2)).lower()})"


@dataclass
class Turn:
    turn: int
    pending_step: int
    is_lookup_result: bool  # this observation answers a lookup (served or unavailable)
    observation_tokens: int
    reply: str | None = None
    action: str | None = None
    outcome: str | None = None
    """correct | wrong | unparsed | lookup | lookup_unavailable | invalid_lookup"""
    is_lookup_unavailable: bool = False  # this observation is a "lookup unavailable" response


@dataclass
class EpisodeResult:
    episode_id: str
    cell: str
    variant: str
    need_correct: bool
    need_action: str | None
    need_label: str | None  # option letter the need action resolved to, if any
    routine_correct: int
    routine_total: int
    n_lookups: int  # lookups served (at most lookup_max_per_episode)
    lookup_steps: list[int]
    n_turns: int
    step_outcomes: dict[int, str]
    turns: list[Turn] = field(default_factory=list)
    n_lookups_unavailable: int = 0  # over-cap lookups answered "lookup unavailable"
    lookup_unavailable_steps: list[int] = field(default_factory=list)

    @property
    def routine_accuracy(self) -> float:
        return self.routine_correct / self.routine_total if self.routine_total else float("nan")


class EpisodeEnv:
    def __init__(self, episode: Episode):
        from persistgym.render import renderer_for  # local import: render imports episode

        self.ep = episode
        self.cfg = episode.config
        self._renderer = renderer_for(episode) if episode.lookup.available else None
        self.known_verbs = {"route", "alert", "ok", "ack", "lookup", episode.need_verb}
        self.reset()

    # ------------------------------------------------------------------
    def reset(self) -> str:
        self.pending = 0
        self.lookups_used = 0
        self.lookup_steps: list[int] = []
        self.unavailable_steps: list[int] = []
        self.outcomes: dict[int, str] = {}
        self.actions: dict[int, str | None] = {}
        self.turns: list[Turn] = []
        self.done = False
        self._current_obs = self.ep.steps[0].observation
        self._current_tokens = self.ep.steps[0].obs_tokens
        self._current_is_lookup = False
        self._current_unavailable = False
        self._new_turn()
        return self._current_obs

    @property
    def observation(self) -> str:
        return self._current_obs

    @property
    def info(self) -> dict:
        """Bookkeeping for oracles and logs. Never shown to an agent."""
        return {"turn": len(self.turns) - 1, "pending_step": self.pending,
                "is_lookup_result": self._current_is_lookup,
                "is_lookup_unavailable": self._current_unavailable,
                "observation_tokens": self._current_tokens}

    def _new_turn(self) -> None:
        self.turns.append(Turn(len(self.turns), self.pending, self._current_is_lookup,
                               self._current_tokens,
                               is_lookup_unavailable=self._current_unavailable))

    def _lookup_turn(self, turn: Turn, outcome: str, text: str, ntok: int,
                     unavailable: bool) -> tuple[str, bool]:
        turn.outcome = outcome
        self._current_obs, self._current_tokens = text, ntok
        self._current_is_lookup = True
        self._current_unavailable = unavailable
        self._new_turn()
        return self._current_obs, False

    # ------------------------------------------------------------------
    def step(self, reply: str) -> tuple[str | None, bool]:
        """Submit a reply to the current observation. Returns (next observation, done)."""
        if self.done:
            raise RuntimeError("episode is done")
        turn = self.turns[-1]
        turn.reply = reply
        parsed = parse_action(reply, self.known_verbs, self.cfg["strict_action_parse"])
        turn.action = parsed.raw if parsed else None
        step = self.ep.steps[self.pending]

        if parsed and parsed.verb == "lookup":
            if self.ep.lookup.available and self.lookups_used < self.ep.lookup.max_per_episode:
                text, ntok, _ = self._renderer.lookup_observation(
                    self.ep, self.pending, self.lookups_used, parsed.arg or "")
                self.lookups_used += 1
                self.lookup_steps.append(self.pending)
                return self._lookup_turn(turn, "lookup", text, ntok, unavailable=False)
            if self.ep.lookup.available and self.pending not in self.unavailable_steps:
                # Over the cap: "lookup unavailable", one turn, the step is asked again.
                text, ntok, _ = self._renderer.lookup_unavailable_observation(self.ep,
                                                                              self.pending)
                self.unavailable_steps.append(self.pending)
                return self._lookup_turn(turn, "lookup_unavailable", text, ntok,
                                         unavailable=True)
            outcome = "invalid_lookup"
        elif parsed is None or parsed.verb is None:
            outcome = "unparsed"
        else:
            outcome = "correct" if self._is_correct(step.index, parsed) else "wrong"

        turn.outcome = outcome
        self.outcomes[step.index] = outcome
        self.actions[step.index] = turn.action
        self.pending += 1
        if self.pending >= self.ep.n_steps:
            self.done = True
            return None, True
        nxt = self.ep.steps[self.pending]
        self._current_obs, self._current_tokens = nxt.observation, nxt.obs_tokens
        self._current_is_lookup = False
        self._current_unavailable = False
        self._new_turn()
        return self._current_obs, False

    def _is_correct(self, step_index: int, parsed: ParsedAction) -> bool:
        if step_index == self.ep.need_step:
            return self.resolve_need_label(parsed) == self.ep.correct_label
        got = f"{parsed.verb}({(parsed.arg or '').lower()})"
        return got == canonical(self.ep.steps[step_index].expected_action)

    def resolve_need_label(self, parsed: ParsedAction | None) -> str | None:
        return need_label(parsed, self.ep.need_verb,
                          [(o.label, o.value) for o in self.ep.options],
                          self.cfg["accept_value_answers"])

    # ------------------------------------------------------------------
    def result(self) -> EpisodeResult:
        n = self.ep.need_step
        routine = [i for i in self.outcomes if i != n]
        need_action = self.actions.get(n)
        need_parsed = (parse_action(f"ACTION: {need_action}", self.known_verbs)
                       if need_action else None)
        return EpisodeResult(
            episode_id=self.ep.episode_id, cell=self.ep.cell.id, variant=self.ep.variant,
            need_correct=self.outcomes.get(n) == "correct", need_action=need_action,
            need_label=self.resolve_need_label(need_parsed),
            routine_correct=sum(self.outcomes[i] == "correct" for i in routine),
            routine_total=len(routine), n_lookups=self.lookups_used,
            lookup_steps=list(self.lookup_steps), n_turns=len(self.turns),
            step_outcomes=dict(self.outcomes), turns=list(self.turns),
            n_lookups_unavailable=len(self.unavailable_steps),
            lookup_unavailable_steps=list(self.unavailable_steps))
