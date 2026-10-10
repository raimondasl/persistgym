"""Position-matched single-turn control (PLAN §5, H3; PREREG §3 H3, D10).

PREREG §3 H3 (Operational): "the system prompt is unchanged. One user message holds o_1..o_n
in order. Each observation is followed by the oracle's correct routine action, written as a
plain "Agent: ..." line, and the message ends with the need-step question." So the prompt is
exactly the observations of steps 0..need of the multi-turn episode, each before the need
step followed by its reply line, with one newline (`SEP`) between pieces:

    o_1 \\n Agent: <a_1> \\n o_2 \\n Agent: <a_2> \\n ... \\n o_need

with no preamble and no marks, and nothing after o_need, whose EVENT is the need question.
One newline is the minimal separator that keeps every line distinct: every observation starts
with its own "=== console update HH:MM:SS ===" line and ends with its EVENT line, and every
reply line starts with `AGENT_PREFIX`. The restated-at-need control is an Episode variant
(`variant="restated"`, see render.py).

Reply lines: by default ('oracle') each step's reply is the oracle's correct routine action,
the step's `expected_action` (e.g. "Agent: route(loans)"). To yoke the control to a real
multi-turn run, pass that run's replies; each non-empty one is written after `AGENT_PREFIX`
in the same place. Mode 'none' (or an empty reply) writes no reply line.

Offsets (`component_offsets`, per evidence component). The observation-token offset of the
evidence from the need question is the same as in the multi-turn episode: the observations
are the episode's, byte for byte and in order, and the offset is counted with the project
tokenizer on each observation on its own, as `obs_tokens` and every planned distance count
them (PREREG §2.1). It is recorded twice: `obs_tokens_to_need`, measured on the observation
spans of the prompt, and `multi_turn_obs_tokens_to_need`, from the episode's observations and
`obs_tokens`; the two must be equal (persistgym/tests). The prompt's own encoding differs
from that count only between pieces: the reply lines and newlines between the evidence and
the need question add their tokens (`single_turn_to_need` counts everything), and BPE may
join an observation's last characters with the newline after it (an observation ending in
")." gains one token that way in o200k_base). Reply tokens differ from a real run's, since the
control uses oracle-length replies (§3 H3).

The control is built from non-recoverable base episodes only. A recoverable cell has the
same observations, and its system prompt offers `lookup`, which a single prompt cannot
serve (there is no next update), so its control would differ only by offering an action
that cannot work. `score_single_turn` scores a reply exactly as `EpisodeEnv` scores the
need step, with the same known verbs for the non-strict parse. `reply_action_class` names
the kind of action that parse reads in a reply (the need verb, a routine or lookup verb,
another verb, or none) by its verb alone: a format diagnostic that says nothing of the option
chosen.
"""

from __future__ import annotations

from collections.abc import Sequence

from persistgym import tokens
from persistgym.env import OTHER_VERBS, known_verbs, need_label, parse_action
from persistgym.episode import Episode

SEP = "\n"
"""Between the pieces of the prompt (observations and reply lines)."""
AGENT_PREFIX = "Agent: "
"""What starts a reply line (PREREG §3 H3: a plain "Agent: ..." line)."""


def control_replies(ep: Episode, mode: str | None = None) -> list[str]:
    """The reply after each step before the need step: the oracle's correct routine action
    ('oracle', the step's `expected_action`), or none ('none', empty)."""
    mode = mode or ep.config["single_turn_reply_mode"]
    if mode == "oracle":
        return [ep.steps[i].expected_action for i in range(ep.need_step)]
    if mode == "none":
        return [""] * ep.need_step
    raise ValueError(f"unknown reply mode {mode!r}")


def obs_tokens_to_need(observations: Sequence[str], step: int, at: int, question: int,
                       enc: str = "o200k_base", counts: Sequence[int] | None = None) -> int:
    """Observation tokens from character `at` of observation `step` to character `question`
    of the last observation (the need question), each observation counted on its own with
    the project tokenizer (PREREG §2.1): the rest of observation `step` from the token that
    holds `at`, the observations after it whole (`counts[i]`, or counted here), and the last
    one up to the token that holds `question`."""
    last = len(observations) - 1
    if step == last:
        idx = tokens.TokenIndex(observations[last], enc)
        return idx.token_at(question) - idx.token_at(at)
    first = tokens.TokenIndex(observations[step], enc)
    whole = (counts[i] if counts is not None else tokens.count(observations[i], enc)
             for i in range(step + 1, last))
    return (first.n_tokens - first.token_at(at) + sum(whole)
            + tokens.TokenIndex(observations[last], enc).token_at(question))


def single_turn_control(ep: Episode, replies: Sequence[str] | None = None,
                        mode: str | None = None) -> dict:
    """Flatten steps 0..need of `ep` into one prompt (module docstring) and record each
    component's offsets."""
    if ep.variant != "base":
        raise ValueError("the single-turn control is built from base episodes")
    if ep.cell.recoverable:
        raise ValueError("the single-turn control is built from non-recoverable cells: a "
                         "single prompt cannot serve the lookup the recoverable system prompt "
                         "offers (the observations are identical)")
    n = ep.need_step
    reply_mode = "given" if replies is not None else (mode or ep.config["single_turn_reply_mode"])
    replies = list(replies) if replies is not None else control_replies(ep, mode)
    if len(replies) != n:
        raise ValueError(f"need {n} replies (one per step before need), got {len(replies)}")
    enc = ep.config["tokenizer"]

    pieces: list[str] = []
    spans: list[tuple[int, int]] = []  # each observation's characters in the prompt
    pos = 0
    for i in range(n + 1):
        obs = ep.steps[i].observation
        spans.append((pos, pos + len(obs)))
        pieces.append(obs)
        pos += len(obs) + len(SEP)
        if i < n and replies[i]:
            line = AGENT_PREFIX + replies[i]
            pieces.append(line)
            pos += len(line) + len(SEP)
    prompt = SEP.join(pieces)

    index = tokens.TokenIndex(prompt, enc)
    in_prompt = [prompt[a:b] for a, b in spans]
    question = ep.steps[n].event_start  # the need question, in the need observation
    need_token = index.token_at(spans[n][0] + question)
    episode_obs = [ep.steps[i].observation for i in range(n + 1)]
    counts = [ep.steps[i].obs_tokens for i in range(n + 1)]
    offsets = {}
    for c in ep.components:
        if c.step is None:
            continue
        k = ep.steps[c.step].observation.index(c.sentence)
        single = index.token_at(spans[c.step][0] + k)
        offsets[c.comp_id] = {
            "single_turn": single, "single_turn_from_end": index.n_tokens - single,
            "single_turn_to_need": need_token - single,
            "obs_tokens_to_need": obs_tokens_to_need(in_prompt, c.step, k, question, enc),
            "multi_turn_obs_tokens_to_need": obs_tokens_to_need(episode_obs, c.step, k,
                                                                question, enc, counts),
        }
    return {
        "control_id": f"{ep.episode_id.rsplit('/', 1)[0]}/single_turn",
        "base_episode_id": ep.episode_id, "template_id": ep.template_id, "cell": ep.cell.id,
        "reply_mode": reply_mode, "replies": replies, "system_prompt": ep.system_prompt,
        "prompt": prompt, "prompt_tokens": index.n_tokens,
        "need_verb": ep.need_verb, "options": [{"label": o.label, "value": o.value}
                                              for o in ep.options],
        "correct_label": ep.correct_label, "component_offsets": offsets,
        "strict_action_parse": ep.config["strict_action_parse"],
        "accept_value_answers": ep.config["accept_value_answers"],
    }


def _parse(control: dict, reply: str):
    """The action `EpisodeEnv` reads in a need-step reply: the last `ACTION: verb(arg)` line,
    or, unless strict, the last call with a known verb (`env.known_verbs`: the need verb, the
    routine steps' verbs and `lookup`, PREREG D4) anywhere in the reply."""
    return parse_action(reply, known_verbs(control["need_verb"]),
                        control["strict_action_parse"])


def score_single_turn(control: dict, reply: str) -> dict:
    """Score a model reply to a single-turn control the way `EpisodeEnv` scores the need
    step: the action `_parse` reads, whose verb must be the need verb and whose argument the
    letter or, if allowed, the option value. A lookup scores `wrong` here (`EpisodeEnv`:
    `invalid_lookup`, which a non-recoverable cell scores 0 too)."""
    verb = control["need_verb"]
    parsed = _parse(control, reply)
    options = [(o["label"], o["value"]) for o in control["options"]]
    label = need_label(parsed, verb, options, control["accept_value_answers"])
    if parsed is None or parsed.verb is None:
        outcome = "unparsed"
    else:
        outcome = "correct" if label == control["correct_label"] else "wrong"
    return {"correct": outcome == "correct", "outcome": outcome, "label": label,
            "action": parsed.raw if parsed else None}


REPLY_ACTION_CLASSES = ("need_verb", "routine_verb", "other_verb", "none")
"""The kinds of action `reply_action_class` tells apart."""


def reply_action_class(control: dict, reply: str) -> str:
    """The kind of the action the scorer reads in a reply (`_parse`, as `score_single_turn`
    reads it), by its verb alone, never its argument, so it says nothing of the option chosen
    or whether it is right: `need_verb` (the episode's need verb, e.g. store), `routine_verb`
    (a routine step's verb or lookup, `env.OTHER_VERBS`: e.g. a reply to an earlier EVENT of
    the flattened prompt, which scores 0), `other_verb` (an `ACTION:` line with any other
    verb) or `none` (no action read: `score_single_turn`'s `unparsed`)."""
    parsed = _parse(control, reply)
    if parsed is None or parsed.verb is None:
        return "none"
    if parsed.verb == control["need_verb"].lower():
        return "need_verb"
    return "routine_verb" if parsed.verb in OTHER_VERBS else "other_verb"
