"""Position-matched single-turn control (PLAN §5, H3).

The same token sequence as the multi-turn episode up to the need step (observations and the
replies between them) is flattened into one user message, so each component sits at the
same position relative to the need question but no turn structure is left. The restated-at-
need control is an Episode variant (`variant="restated"`, see render.py).

Reply positions: by default ('oracle') each earlier reply is the minimal correct reply
"ACTION: <expected action>". To yoke the control to a real multi-turn run, pass that run's
replies so every offset matches the run's actual transcript.
"""

from __future__ import annotations

from collections.abc import Sequence

from persistgym import tokens
from persistgym.episode import Episode

PREAMBLE = ("Console session transcript. Each earlier update is followed by the operator's "
            "reply. The last update is the current one and has no reply yet.\n")
UPDATE_MARK = "\n<<< update >>>\n"
REPLY_MARK = "\n<<< operator reply >>>\n"


def control_replies(ep: Episode, mode: str | None = None) -> list[str]:
    mode = mode or ep.config["single_turn_reply_mode"]
    if mode == "oracle":
        return [f"ACTION: {ep.steps[i].expected_action}" for i in range(ep.need_step)]
    if mode == "none":
        return [""] * ep.need_step
    raise ValueError(f"unknown reply mode {mode!r}")


def single_turn_control(ep: Episode, replies: Sequence[str] | None = None,
                        mode: str | None = None) -> dict:
    """Flatten steps 0..need of `ep` into one prompt and record component token offsets."""
    if ep.variant != "base":
        raise ValueError("the single-turn control is built from base episodes")
    n = ep.need_step
    reply_mode = "given" if replies is not None else (mode or ep.config["single_turn_reply_mode"])
    replies = list(replies) if replies is not None else control_replies(ep, mode)
    if len(replies) != n:
        raise ValueError(f"need {n} replies (one per step before need), got {len(replies)}")
    enc = ep.config["tokenizer"]

    pieces = [PREAMBLE]
    obs_char_start: dict[int, int] = {}
    pos = len(PREAMBLE)
    for i in range(n + 1):
        pieces.append(UPDATE_MARK)
        pos += len(UPDATE_MARK)
        obs_char_start[i] = pos
        pieces.append(ep.steps[i].observation)
        pos += len(ep.steps[i].observation)
        if i < n and (replies[i] or reply_mode == "oracle"):
            pieces.append(REPLY_MARK + replies[i])
            pos += len(REPLY_MARK) + len(replies[i])
    prompt = "".join(pieces)

    reply_tokens = [tokens.count(r, enc) for r in replies]
    index = tokens.TokenIndex(prompt, enc)
    offsets = {}
    for c in ep.components:
        if c.step is None:
            continue
        obs = ep.steps[c.step].observation
        k = obs.index(c.sentence)
        in_obs = tokens.TokenIndex(obs, enc).token_at(k)
        multi = sum(ep.steps[i].obs_tokens + reply_tokens[i] for i in range(c.step)) + in_obs
        single = index.token_at(obs_char_start[c.step] + k)
        offsets[c.comp_id] = {
            "single_turn": single, "multi_turn_content": multi,
            "single_turn_from_end": index.n_tokens - single,
        }
    return {
        "control_id": f"{ep.episode_id.rsplit('/', 1)[0]}/single_turn",
        "base_episode_id": ep.episode_id, "template_id": ep.template_id, "cell": ep.cell.id,
        "reply_mode": reply_mode, "replies": replies, "system_prompt": ep.system_prompt,
        "prompt": prompt, "prompt_tokens": index.n_tokens,
        "need_verb": ep.need_verb, "options": [{"label": o.label, "value": o.value}
                                              for o in ep.options],
        "correct_label": ep.correct_label, "component_offsets": offsets,
    }
