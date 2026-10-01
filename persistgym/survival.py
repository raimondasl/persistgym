"""Survival calculator (PLAN §4 "Survives (S)", §5, amendment §16.5).

S = whether the fact (observed) or all of its components (derived: every clue and the rule)
are still in the context the harness sends at the need step.

* Window cells: S follows from token positions. `designed_survival` computes it before any
  run from observation token counts and an assumed maximum reply length;
  `survival_from_payload` recomputes it from the payload a harness actually sent.
* Summary and notes cells: S depends on what the model wrote, so `carried_in_text` string-
  matches logged summaries and notes (whole-word regex of PREREG §2.8, D6).

Window model ("drop oldest", as ARC's Standard harness): the history is a list of turns
(observation, reply). Before sending observation m, the harness keeps the longest suffix of
whole turns whose tokens fit in W; the current observation is always kept. With
`window_counts_system_prompt` (default true, PREREG D5) W also holds the episode's system
prompt, `Episode.system_tokens`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from persistgym import tokens

if TYPE_CHECKING:
    from persistgym.episode import Episode


# ---------------------------------------------------------------------------
# Token-position survival (window cells)
# ---------------------------------------------------------------------------

def window_keep_start(obs_tokens: Sequence[int], reply_tokens: Sequence[int], W: int,
                      system_tokens: int = 0) -> int:
    """First kept turn index when sending observation m = len(obs_tokens) - 1.

    `reply_tokens[i]` is the reply to observation i (len >= m). Turn i < m costs
    obs_tokens[i] + reply_tokens[i]; the current observation costs obs_tokens[m]. Returns the
    smallest s with system_tokens + sum(turns s..m) <= W, or m if even the current
    observation does not fit.
    """
    m = len(obs_tokens) - 1
    if m < 0:
        raise ValueError("no observations")
    if len(reply_tokens) < m:
        raise ValueError("need one reply length per earlier observation")
    total = system_tokens + obs_tokens[m]
    s = m
    while s > 0:
        add = obs_tokens[s - 1] + reply_tokens[s - 1]
        if total + add > W:
            break
        total += add
        s -= 1
    return s


def designed_survival(obs_tokens: Sequence[int], need_step: int,
                      component_steps: dict[str, int | None], W: int, reply_tokens: int,
                      system_tokens: int = 0) -> dict[str, Any]:
    """Designed S at the need step for a scripted episode (no lookups), assuming every reply
    has `reply_tokens` tokens. Components with step None (rule in the system prompt) always
    survive."""
    obs = list(obs_tokens[: need_step + 1])
    keep = window_keep_start(obs, [reply_tokens] * need_step, W, system_tokens)
    per = {cid: (st is None or st >= keep) for cid, st in component_steps.items()}
    return {"keep_start": keep, "components": per,
            "S": bool(per) and all(per.values()) if per else None}


def episode_design(ep_obs_tokens: Sequence[int], need_step: int,
                   component_steps: dict[str, int | None], *, W: int, v: int,
                   far_margin_tokens: int, assumed_reply_tokens: int, system_tokens: int,
                   count_system: bool) -> dict[str, Any]:
    """Designed distances and survival recorded in `Episode.design`."""
    sys_t = system_tokens if count_system else 0
    steps = [s for s in component_steps.values() if s is not None]
    d: dict[str, Any] = {
        "W": W, "v": v, "far_margin_tokens": far_margin_tokens,
        "assumed_reply_tokens": assumed_reply_tokens, "window_counts_system_prompt": count_system,
        "need_step": need_step, "component_steps": dict(component_steps),
        "context_obs_tokens_at_need": system_tokens + sum(ep_obs_tokens[: need_step + 1]),
        "context_tokens_at_need_assumed_replies":
            system_tokens + sum(ep_obs_tokens[: need_step + 1]) + need_step * assumed_reply_tokens,
    }
    if not steps:
        d.update(gap_steps_latest=None, gap_steps_earliest=None, obs_tokens_latest_to_need=None,
                 obs_tokens_earliest_to_need=None, far_by_obs_tokens=None,
                 S_window_obs_only=None, S_window_assumed_replies=None)
        return d
    latest, earliest = max(steps), min(steps)
    obs_latest = sum(ep_obs_tokens[latest: need_step + 1])
    d.update(
        gap_steps_latest=need_step - latest,
        gap_steps_earliest=need_step - earliest,
        obs_tokens_latest_to_need=obs_latest,
        obs_tokens_earliest_to_need=sum(ep_obs_tokens[earliest: need_step + 1]),
        far_by_obs_tokens=obs_latest > W + far_margin_tokens,
        S_window_obs_only=designed_survival(ep_obs_tokens, need_step, component_steps, W, 0,
                                            sys_t)["S"],
        S_window_assumed_replies=designed_survival(ep_obs_tokens, need_step, component_steps, W,
                                                   assumed_reply_tokens, sys_t)["S"],
    )
    return d


def max_reply_tokens_for_survival(episode: Episode, W: int | None = None,
                                  count_system: bool | None = None) -> int | None:
    """Largest uniform reply length at which every component still survives at the need
    step under the window model (None if none survives even with empty replies)."""
    W = W or episode.config["W_tokens"]
    if count_system is None:
        count_system = episode.config["window_counts_system_prompt"]
    sys_t = episode.system_tokens if count_system else 0
    steps = {c.comp_id: c.step for c in episode.components}
    if not steps:
        return None
    obs = episode.obs_tokens
    n = episode.need_step

    def ok(r: int) -> bool:
        return bool(designed_survival(obs, n, steps, W, r, sys_t)["S"])

    if not ok(0):
        return None
    lo, hi = 0, W
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if ok(mid):
            lo = mid
        else:
            hi = mid - 1
    return lo


# ---------------------------------------------------------------------------
# Payload survival
# ---------------------------------------------------------------------------

def _texts(content: Any) -> list[str]:
    if content is None:
        return []
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        out: list[str] = []
        for part in content:
            out.extend(_texts(part))
        return out
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return [content["text"]]
        for key in ("content", "parts"):
            if key in content:
                return _texts(content[key])
    return []


def flatten_payload(messages: Sequence[dict]) -> list[tuple[str, str]]:
    """(role, text) pairs from chat-style, Responses-style or Gemini-style messages.

    Items without a role (e.g. reasoning items with encrypted content) get role 'opaque'
    and contribute no text. Gemini's 'model' role maps to 'assistant'."""
    out = []
    for m in messages:
        role = m.get("role")
        if role is None:
            out.append(("opaque", ""))
            continue
        role = "assistant" if role == "model" else role
        text = "\n".join(_texts(m.get("content", m.get("parts"))))
        out.append((role, text))
    return out


def survival_from_payload(episode: Episode, messages: Sequence[dict],
                          system: str | None = None,
                          observation_roles: tuple[str, ...] = ("user", "system", "developer"),
                          exclude_indices: Sequence[int] = (),
                          ) -> dict[str, Any]:
    """S recomputed from the payload actually sent at the need step.

    A component survives if its displayed sentence appears verbatim in a message of an
    observation role (or in `system`, for APIs that send instructions separately). Text the
    model wrote (assistant turns) is checked separately with `carried_in_text`, so S stays
    the environment-side quantity. Summary cells insert a model-written summary as a user
    message: pass its index in `exclude_indices` and string-match it with `carried_in_text`.

    Use the payload of the need step's first presentation. After a lookup the payload holds
    the lookup result (records re-shown, so S=1 by construction) and the model's own lookup
    reply, which may quote the options next to the entity name; neither says whether the
    fact was carried.
    """
    pairs = flatten_payload(messages)
    skip = set(exclude_indices)
    env_text = "\n".join(t for i, (r, t) in enumerate(pairs)
                         if r in observation_roles and i not in skip)
    if system:
        env_text = system + "\n" + env_text
    assistant_text = "\n".join(t for r, t in pairs if r == "assistant")
    per = {c.comp_id: c.sentence in env_text for c in episode.components}
    return {
        "S": (all(per.values()) if per else None),
        "components": per,
        "assistant_carried": carried_in_text(assistant_text, episode),
        "n_messages": len(pairs),
        "n_opaque_items": sum(1 for r, _ in pairs if r == "opaque"),
        "payload_text_tokens": tokens.count("\n".join(t for _, t in pairs) + (system or ""),
                                            episode.config["tokenizer"]),
    }


def reference_window_payload(episode: Episode, replies: Sequence[str], W: int | None = None,
                             count_system: bool | None = None) -> list[dict]:
    """Reference drop-oldest window payload at observation m = len(replies), for a scripted
    run without lookups. For cross-checking harness implementations; not a harness."""
    W = W or episode.config["W_tokens"]
    if count_system is None:
        count_system = episode.config["window_counts_system_prompt"]
    m = len(replies)
    obs = episode.obs_tokens[: m + 1]
    rep = [tokens.count(r, episode.config["tokenizer"]) for r in replies]
    keep = window_keep_start(obs, rep, W, episode.system_tokens if count_system else 0)
    msgs = [{"role": "system", "content": episode.system_prompt}]
    for i in range(keep, m):
        msgs.append({"role": "user", "content": episode.steps[i].observation})
        msgs.append({"role": "assistant", "content": replies[i]})
    msgs.append({"role": "user", "content": episode.steps[m].observation})
    return msgs


# ---------------------------------------------------------------------------
# String match for summaries and notes
# ---------------------------------------------------------------------------

def whole_word_regex(value: int | str) -> re.Pattern:
    """PREREG §2.8 (D6): `(?<![0-9A-Za-z])VALUE(?![0-9A-Za-z])`."""
    return re.compile(rf"(?<![0-9A-Za-z]){re.escape(str(value))}(?![0-9A-Za-z])")


def carried_in_text(text: str, episode: Episode) -> dict[str, Any]:
    """Whether text the model wrote (a summary bridge, retained replies or notes) carries the
    fact: S_carried of PREREG §2.8 (D6), behind P(carried) (PLAN §4, §10).

    Whole-word match anywhere in the text with `whole_word_regex`: the target value, or for
    a derived fact every clue value. The rule need not be carried. Pass only model-written
    text: lookup responses and the need observation are excluded by the caller. Distractor
    values never equal the target or a clue value, so a carried distractor never counts.
    `entity_mentioned` is reported for diagnostics only; it does not enter `carried`.
    """
    text = text or ""

    def present(value: int) -> bool:
        return whole_word_regex(value).search(text) is not None

    final = present(episode.target_value)
    clues = {c.comp_id: present(c.value) for c in episode.components if c.role == "clue"}
    all_clues = bool(clues) and all(clues.values())
    derived = episode.cell.fact == "derived"
    carried = final or (derived and all_clues)
    entity = re.search(rf"(?<![A-Za-z]){re.escape(episode.entity)}(?![A-Za-z])", text,
                       re.IGNORECASE)
    return {"carried": bool(carried), "final_value": final, "clues": clues,
            "all_clues": all_clues, "entity_mentioned": entity is not None}
