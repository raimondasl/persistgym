"""Polite, cached client for arcprize.org's public pages and unauthenticated run endpoints.

Rules (CLAUDE.md "arcprize.org public API"):
- one request at a time (a process-wide lock), at least ``MIN_INTERVAL_S`` seconds between
  the end of one request and the start of the next;
- a descriptive User-Agent;
- retries with exponential backoff on 429, 5xx and transport errors (``Retry-After`` honoured);
- an on-disk cache that is never re-downloaded: if the cache file exists it is returned as is.

Cache layout, under ``$PERSISTGYM_RAW_DIR`` (default ``<repo>/results/raw``, gitignored)::

    arc_public/pages/<slug>.html
    arc_public/sessions/<guid>.json
    arc_public/recordings/<game_id>/<guid>.ndjson

No API key is used or needed; these endpoints are public.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Self

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_URL = "https://arcprize.org"
USER_AGENT = (
    "persistgym-arc-public/0.1 (one-off research analysis of published ARC-AGI-3 runs; "
    "one request at a time, >=2 s apart, cached on disk, never re-downloaded)"
)
MIN_INTERVAL_S = 2.5
MAX_ATTEMPTS = 6
BACKOFF_BASE_S = 5.0
BACKOFF_CAP_S = 300.0
TIMEOUT = httpx.Timeout(connect=20.0, read=180.0, write=20.0, pool=20.0)

_GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_GAME_RE = re.compile(r"^[a-z0-9]{2,8}-[0-9a-f]{4,16}$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")

# Process-wide: one request at a time, and the time the last one finished.
_LOCK = threading.Lock()
_LAST_DONE = [float("-inf")]


class CacheMiss(RuntimeError):
    """Raised in offline mode when a file is not in the cache."""


class FetchError(RuntimeError):
    """Raised when a URL still fails after all retries, or returns a non-retryable status."""


def raw_dir() -> Path:
    env = os.environ.get("PERSISTGYM_RAW_DIR")
    return Path(env) if env else REPO_ROOT / "results" / "raw"


def cache_root(base: Path | None = None) -> Path:
    return (base if base is not None else raw_dir()) / "arc_public"


def _check(pattern: re.Pattern, value: str, what: str) -> str:
    if not pattern.match(value):
        raise ValueError(f"unexpected {what}: {value!r}")
    return value


def _retry_after_seconds(resp: httpx.Response) -> float | None:
    value = resp.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(value)
        return max(0.0, dt.timestamp() - time.time())
    except (TypeError, ValueError):
        return None


class PoliteClient:
    """Throttled, retrying, caching GET client. Use one per process; it is cheap to create."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        *,
        offline: bool = False,
        min_interval_s: float = MIN_INTERVAL_S,
        max_attempts: int = MAX_ATTEMPTS,
        backoff_base_s: float = BACKOFF_BASE_S,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        log: Callable[[str], None] | None = print,
    ) -> None:
        if min_interval_s < 2.0:
            raise ValueError("min_interval_s must be at least 2 seconds (politeness rule)")
        self.root = cache_root(cache_dir)
        self.offline = offline
        self.min_interval_s = min_interval_s
        self.max_attempts = max_attempts
        self.backoff_base_s = backoff_base_s
        self._sleep = sleep
        self._clock = clock
        self._log = log or (lambda _msg: None)
        self._http = httpx.Client(
            base_url=BASE_URL,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            timeout=TIMEOUT,
            follow_redirects=True,
            transport=transport,
        )
        self.n_requests = 0
        self.n_cache_hits = 0
        self.n_retries = 0

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ── paths ────────────────────────────────────────────────────────────
    def page_path(self, slug: str) -> Path:
        return self.root / "pages" / f"{_check(_SLUG_RE, slug, 'page slug')}.html"

    def session_path(self, guid: str) -> Path:
        return self.root / "sessions" / f"{_check(_GUID_RE, guid, 'session guid')}.json"

    def recording_path(self, game_id: str, guid: str) -> Path:
        return (self.root / "recordings" / _check(_GAME_RE, game_id, "game id")
                / f"{_check(_GUID_RE, guid, 'session guid')}.ndjson")

    # ── public getters ───────────────────────────────────────────────────
    def results_page(self, slug: str) -> Path:
        """Cached HTML of https://arcprize.org/results/<slug>."""
        return self._cached(self.page_path(slug), f"/results/{slug}")

    def session(self, guid: str) -> dict:
        """Cached session JSON from GET /api/sessions/<guid>."""
        path = self._cached(self.session_path(guid), f"/api/sessions/{guid}",
                            validate=_validate_json)
        return json.loads(path.read_text(encoding="utf-8"))

    def recording(self, game_id: str, guid: str) -> Path:
        """Cached NDJSON from GET /api/recordings/<game_id>/<guid> (streamed to disk)."""
        return self._cached(self.recording_path(game_id, guid),
                            f"/api/recordings/{game_id}/{guid}", validate=_validate_ndjson)

    # ── internals ────────────────────────────────────────────────────────
    def _cached(self, path: Path, url: str, validate: Callable[[Path], None] | None = None) -> Path:
        if path.exists() and path.stat().st_size > 0:
            self.n_cache_hits += 1
            return path
        if self.offline:
            raise CacheMiss(f"not cached (offline mode): {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        self._download(url, tmp)
        if validate is not None:
            try:
                validate(tmp)
            except ValueError:
                tmp.unlink(missing_ok=True)
                raise
        os.replace(tmp, path)
        return path

    def _wait_turn(self) -> None:
        gap = self._clock() - _LAST_DONE[0]
        if gap < self.min_interval_s:
            self._sleep(self.min_interval_s - gap)

    def _backoff(self, attempt: int, resp: httpx.Response | None) -> float:
        hinted = _retry_after_seconds(resp) if resp is not None else None
        delay = self.backoff_base_s * (2 ** (attempt - 1))
        if hinted is not None:
            delay = max(delay, hinted)
        return min(delay, BACKOFF_CAP_S)

    def _download(self, url: str, dest: Path) -> None:
        last_err: str = ""
        for attempt in range(1, self.max_attempts + 1):
            resp: httpx.Response | None = None
            with _LOCK:
                self._wait_turn()
                try:
                    self.n_requests += 1
                    with self._http.stream("GET", url) as resp:
                        if resp.status_code == 200:
                            with dest.open("wb") as f:
                                for chunk in resp.iter_bytes():
                                    f.write(chunk)
                            self._log(f"GET {url} -> 200 ({dest.stat().st_size:,} bytes)")
                            return
                        resp.read()
                        last_err = f"HTTP {resp.status_code}"
                        retryable = resp.status_code == 429 or resp.status_code >= 500
                except httpx.TransportError as e:
                    last_err = f"{type(e).__name__}: {e}"
                    retryable = True
                    resp = None
                finally:
                    _LAST_DONE[0] = self._clock()
            dest.unlink(missing_ok=True)
            if not retryable:
                raise FetchError(f"GET {url} failed: {last_err}")
            if attempt == self.max_attempts:
                break
            delay = self._backoff(attempt, resp)
            self.n_retries += 1
            self._log(f"GET {url} -> {last_err}; retry {attempt}/{self.max_attempts - 1} "
                      f"in {delay:.0f} s")
            self._sleep(delay)
        raise FetchError(f"GET {url} failed after {self.max_attempts} attempts: {last_err}")


def _validate_json(path: Path) -> None:
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"response is not JSON: {path}: {e}") from e


def _validate_ndjson(path: Path) -> None:
    """Every non-empty line must parse, so a truncated download is never cached."""
    n = 0
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"line {i + 1} of {path} is not JSON: {e}") from e
            n += 1
    if n == 0:
        raise ValueError(f"empty recording: {path}")
