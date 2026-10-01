"""Discover published public-set session GUIDs from an arcprize.org results page.

The results page (a Next.js app) embeds its data in ``self.__next_f.push([1, "<chunk>"])``
script tags (React Server Components "flight" data). Concatenating the chunks gives a text
stream that contains one plain JSON object ``{"group": {...}, "comparisons": [...]}``. In it:

- ``group.variants``: the harness configurations, in column order, e.g.
  ``{"id": "provider-adapter-high", "label": "High (Provider Adapter)", "reasoningLevel": "high"}``;
- ``group.tasks.v3``: one entry per ARC-AGI-3 public game,
  ``{"name": "LP85", "scores": [...], "replays": ["https://arcprize.org/replay/<guid>", ...]}``,
  with ``scores`` and ``replays`` aligned to ``group.variants``.

The config tag of each run (e.g. ``google-gemini-3-8-flash-high-provider-adapter``) is not on
the page; it comes from the session JSON (``config``) and is cross-checked in ``ops.py``.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

_PUSH_RE = re.compile(r"self\.__next_f\.push\((\[.*?\])\)</script>", re.DOTALL)
_REPLAY_RE = re.compile(r"/replay/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")


@dataclass(frozen=True)
class PublishedRun:
    game: str            # upper-case display name, e.g. "LP85"
    variant_id: str      # e.g. "high", "provider-adapter-low"
    variant_label: str   # e.g. "High (Provider Adapter)"
    harness: str         # "standard" | "provider_adapter"
    effort: str          # "low" | "medium" | "high" (page's reasoningLevel)
    page_score: float | None  # per-game score on the page, 0..1
    guid: str

    def as_dict(self) -> dict:
        return asdict(self)


def flight_text(html: str) -> str:
    """Concatenate the string payloads of all ``self.__next_f.push`` calls."""
    parts = []
    for m in _PUSH_RE.finditer(html):
        arr = json.loads(m.group(1))
        if len(arr) > 1 and isinstance(arr[1], str):
            parts.append(arr[1])
    if not parts:
        raise ValueError("no Next.js flight chunks found in page")
    return "".join(parts)


def group_object(html: str) -> dict:
    """The ``group`` JSON object embedded in a results page."""
    text = flight_text(html)
    start = text.find('{"group":')
    if start < 0:
        raise ValueError('no {"group": ...} object in flight data')
    obj, _ = json.JSONDecoder().raw_decode(text, start)
    return obj["group"]


def harness_of_variant(variant_id: str) -> str:
    return "provider_adapter" if variant_id.startswith("provider-adapter") else "standard"


def published_runs(html: str, track: str = "v3") -> list[PublishedRun]:
    """All (game, variant) runs with a replay link, in page order."""
    group = group_object(html)
    variants = group["variants"]
    runs: list[PublishedRun] = []
    for task in group["tasks"][track]:
        replays = task.get("replays") or []
        scores = task.get("scores") or []
        if len(replays) != len(variants):
            raise ValueError(f"{task.get('name')}: {len(replays)} replays for {len(variants)} variants")
        for i, (variant, url) in enumerate(zip(variants, replays, strict=True)):
            if not url:
                continue
            m = _REPLAY_RE.search(url)
            if not m:
                raise ValueError(f"unexpected replay url {url!r}")
            score = scores[i] if i < len(scores) else None
            runs.append(PublishedRun(
                game=task["name"],
                variant_id=variant["id"],
                variant_label=variant["label"],
                harness=harness_of_variant(variant["id"]),
                effort=variant.get("reasoningLevel") or variant["id"].split("-")[-1],
                page_score=None if score is None else float(score),
                guid=m.group(1),
            ))
    return runs
