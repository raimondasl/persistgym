"""Pull (or re-use from cache) the Gemini 3.8 Flash public-set runs.

    PERSISTGYM_RAW_DIR=... uv run python -m arc.public.pull [--offline]

1. Results page -> 6 variants x 25 games of session GUIDs (``discover.py``).
2. Every session JSON (``GET /api/sessions/<guid>``).
3. Recording NDJSON (``GET /api/recordings/<game_id>/<guid>``) only for the high-effort
   Standard and Provider Adapter runs of ``RECORDING_GAMES`` (2 per game, 20 recordings).

Everything goes through ``PoliteClient`` (one request at a time, >= 2 s apart, cached, never
re-downloaded). Nothing here needs an API key.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from arc.public.client import PoliteClient
from arc.public.discover import PublishedRun, published_runs

RESULTS_SLUG = "google-gemini-3-8-flash"
# The six eligible games (PLAN §8.3), the two third-held-out candidates (PLAN §9), and the
# other two held-out games of decision D14 option A (held out: SP80, VC33, TN36), so that every
# option-A game's cost comes from its recordings, not from the premise table.
RECORDING_GAMES = ("FT09", "SB26", "R11L", "LP85", "SC25", "CD82", "VC33", "RE86", "SP80", "TN36")


@dataclass
class PulledRun:
    run: PublishedRun
    session: dict
    game_id: str


def discover(client: PoliteClient) -> list[PublishedRun]:
    html = client.results_page(RESULTS_SLUG).read_text(encoding="utf-8")
    return published_runs(html)


def session_game_id(session: dict) -> str:
    envs = session.get("environments") or []
    if len(envs) != 1:
        raise ValueError(f"expected one environment per session, got {len(envs)}")
    return envs[0]["id"]


def wants_recording(run: PublishedRun) -> bool:
    return run.effort == "high" and run.game.upper() in RECORDING_GAMES


def pull_all(client: PoliteClient, with_recordings: bool = True) -> list[PulledRun]:
    runs = discover(client)
    pulled: list[PulledRun] = []
    for i, run in enumerate(runs, 1):
        session = client.session(run.guid)
        pulled.append(PulledRun(run=run, session=session, game_id=session_game_id(session)))
        if i % 25 == 0:
            print(f"sessions: {i}/{len(runs)} (requests {client.n_requests}, "
                  f"cache hits {client.n_cache_hits})", flush=True)
    if with_recordings:
        for p in pulled:
            if wants_recording(p.run):
                client.recording(p.game_id, p.run.guid)
    return pulled


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true", help="use the cache only; never fetch")
    ap.add_argument("--no-recordings", action="store_true")
    args = ap.parse_args(argv)
    with PoliteClient(offline=args.offline) as client:
        pulled = pull_all(client, with_recordings=not args.no_recordings)
        print(f"done: {len(pulled)} sessions; requests {client.n_requests}, "
              f"cache hits {client.n_cache_hits}, retries {client.n_retries}; cache {client.root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
