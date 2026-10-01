"""$0 diagnostics of the loss policies on generated episodes (fake model, no network).

`summary_timing`: where Σ cells compact, and whether a near reveal is still verbatim at the
need step, when every reply has the generator's assumed reply length. This sizes the
`summary_keep_recent_tokens` decision (harnesses/DESIGN.md §4.3):

    uv run python -m harnesses summary-timing --n 20
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache

from harnesses.cells import CELLS
from harnesses.config import HarnessConfig
from harnesses.fake import FakeModel, padded_text
from harnesses.runner import run_episode
from persistgym.config import GeneratorConfig
from persistgym.episode import TaskCell
from persistgym.render import generate


def summary_timing(n: int = 20, *, split: str = "main", gen: GeneratorConfig | None = None,
                   reply_tokens: int | None = None, summary_tokens: int = 300,
                   keep_recent: tuple[int, ...] = (0, 16_500),
                   cell_id: str = "Σ-n-0") -> dict:
    """For the non-recoverable near cells of templates 0..n-1: the turns at which the Σ cell
    compacts, and how many episodes reach the need step with S = 0 (a reveal compacted),
    for each `summary_keep_recent_tokens` value. Replies default to the generator's
    `assumed_max_reply_tokens`; the summary has `summary_tokens` tokens."""
    gen = gen or GeneratorConfig()
    reply_tokens = reply_tokens or gen.assumed_max_reply_tokens
    reply = lru_cache(None)(lambda i: padded_text(f"REPLY {i}", reply_tokens, gen.tokenizer))
    summ = lru_cache(None)(lambda j: padded_text(f"SUMMARY {j}", summary_tokens, gen.tokenizer))
    cells = [TaskCell(f, False, "near") for f in ("observed", "derived")]
    out: dict = {"n_episodes": 0, "reply_tokens": reply_tokens,
                 "summary_tokens": summary_tokens, "W": gen.W_tokens, "v": gen.v_tokens,
                 "per_keep_recent": {}}
    per = {k: {"compaction_turns": Counter(), "need_S0": 0} for k in keep_recent}
    for _, eps in generate(split, range(n), gen, cells, ("base",)):
        for ep in eps:
            out["n_episodes"] += 1
            for k in keep_recent:
                run = run_episode(ep, CELLS[cell_id],
                                  HarnessConfig(summary_keep_recent_tokens=k),
                                  FakeModel(lambda p, i: reply(i),
                                            summary_fn=lambda p, j: summ(j)))
                per[k]["compaction_turns"][tuple(c["at_turn"] for c in run.compactions)] += 1
                per[k]["need_S0"] += run.need_payload["S"] is False
    for k, d in per.items():
        out["per_keep_recent"][k] = {
            "compaction_turns": {",".join(map(str, t)): c
                                 for t, c in sorted(d["compaction_turns"].items())},
            "need_S0": d["need_S0"]}
    return out
