"""Irrelevant log filler and exact token-budget fitting.

Every observation is padded to exactly v tokens with a tail of realistic service logs. The
filler never contains a reserved string of its template: any option value, any clue value,
the entity name, the target quantity or a component name. Lines that would contain one are
resampled, so the check is enforced at generation time and re-checked by the audit.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from persistgym import tokens

LOG_HEAD = "--- log tail (earlier lines omitted) ---\n"
LOG_FOOT = "\n--- end of log ---\n"


class FitError(RuntimeError):
    pass


class Reserved:
    """Strings that must never appear in filler or routine text of one template."""

    def __init__(self, numbers: Iterable[int], words: Iterable[str]):
        self.numbers = sorted({int(n) for n in numbers})
        self.words = sorted({w.strip() for w in words if w.strip()}, key=str.lower)
        # Numbers match unless embedded in a longer digit run ("x412y" matches 412, "1412"
        # does not); words match case-insensitively unless embedded in a longer word.
        parts = []
        if self.numbers:
            nums = "|".join(str(n) for n in self.numbers)
            parts.append(rf"(?<![0-9])(?:{nums})(?![0-9])")
        if self.words:
            ws = "|".join(re.escape(w) for w in sorted(self.words, key=len, reverse=True))
            parts.append(rf"(?<![A-Za-z])(?:{ws})(?![A-Za-z])")
        self.regex = (re.compile("|".join(parts), re.IGNORECASE) if parts
                      else re.compile(r"(?!x)x"))

    def hits(self, text: str) -> list[str]:
        return [m.group(0) for m in self.regex.finditer(text)]

    def clean(self, text: str) -> bool:
        return self.regex.search(text) is None


# ---------------------------------------------------------------------------
# Line templates
# ---------------------------------------------------------------------------

def _hex(rng: random.Random, n: int) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))


def _ip(rng: random.Random) -> str:
    return f"10.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"


_PATHS = ("/v2/items/{h}", "/v2/orders/{h}", "/healthz", "/metrics", "/v1/session/{h}",
          "/v2/events", "/v1/batch/{h}/status", "/internal/sync", "/v2/lookup/{h}")
_TABLES = ("events", "audit_log", "sessions", "jobs", "outbox", "leases")
_HOSTS = ("db-primary", "db-replica-2", "cache-1", "queue-0", "objstore", "ldap-1", "ntp-2")
_JOBS = ("logrotate", "backup-verify", "cert-renew", "index-compact", "tmp-clean")
_USERS = ("svc-sync", "svc-report", "svc-backup", "deploy", "monitor")


def _line_templates() -> list[Callable[[random.Random, str, str], str]]:
    def http(r, ts, s):
        p = r.choice(_PATHS).format(h=_hex(r, 8))
        status = r.choice((200, 200, 200, 200, 201, 204, 304, 404))
        return (f"{ts} INFO  {s} {r.choice(('GET', 'GET', 'POST', 'PUT'))} {p} {status} "
                f"{r.randint(2, 2400)}ms req={_hex(r, 8)}")

    def cache(r, ts, s):
        return f"{ts} DEBUG {s} cache hit_ratio=0.{r.randint(10, 99)} keys={r.randint(1000, 99999)}"

    def slowq(r, ts, s):
        return (f"{ts} WARN  {s} slow query took {r.randint(1000, 9000)}ms "
                f"table={r.choice(_TABLES)}")

    def heartbeat(r, ts, s):
        return f"{ts} INFO  {s} heartbeat ok uptime={r.randint(10_000, 9_000_000)}s"

    def worker(r, ts, s):
        return (f"{ts} INFO  {s} worker-{r.randint(1, 9)} picked job {_hex(r, 8)} "
                f"queue={r.choice(('default', 'bulk', 'priority', 'retry'))}")

    def gc(r, ts, s):
        return f"{ts} DEBUG {s} gc pause {r.randint(1, 40)}ms heap={r.randint(1000, 8000)}MB"

    def retry(r, ts, s):
        return (f"{ts} WARN  {s} retry {r.randint(1, 4)}/5 upstream={r.choice(_HOSTS)} "
                f"err={r.choice(('timeout', 'conn_reset', 'unavailable'))}")

    def upstream(r, ts, s):
        return (f"{ts} ERROR {s} upstream {r.choice(_HOSTS)} returned 503 after "
                f"{r.randint(1000, 30000)}ms")

    def json_done(r, ts, s):
        return (f'{{"ts":"{ts}","level":"info","svc":"{s}","msg":"request done",'
                f'"dur_ms":{r.randint(1, 3000)},"trace":"{_hex(r, 16)}"}}')

    def json_flush(r, ts, s):
        return (f'{{"ts":"{ts}","level":"debug","svc":"{s}","msg":"metrics flushed",'
                f'"series":{r.randint(1000, 60000)}}}')

    def tls(r, ts, s):
        return f"{ts} INFO  {s} tls handshake ok peer={_ip(r)}:{r.randint(10000, 65000)}"

    def reload(r, ts, s):
        return f"{ts} INFO  {s} config reload checksum={_hex(r, 12)}"

    def lease(r, ts, s):
        return f"{ts} DEBUG {s} lease renewed holder={r.choice(_HOSTS)} ttl={r.randint(10, 59)}s"

    def batch(r, ts, s):
        return f"{ts} INFO  {s} batch {_hex(r, 6)} committed rows={r.randint(1000, 250000)}"

    def disk(r, ts, s):
        return f"{ts} WARN  {s} disk usage {r.randint(10, 59)}% on /var/lib/{s}"

    def sshd(r, ts, s):
        return (f"{ts} INFO  sshd[{r.randint(1000, 65000)}]: Accepted publickey for "
                f"{r.choice(_USERS)} from {_ip(r)} port {r.randint(10000, 65000)}")

    def rotate(r, ts, s):
        return f"{ts} INFO  {s} rotated log file size={r.randint(10_000, 9_000_000)}B"

    def span(r, ts, s):
        return f"{ts} DEBUG {s} span {_hex(r, 16)} parent={_hex(r, 16)} sampled=true"

    def pool(r, ts, s):
        return f"{ts} INFO  {s} connection pool size={r.randint(10, 59)} idle={r.randint(1, 9)}"

    def cron(r, ts, s):
        return (f"{ts} INFO  cron job={r.choice(_JOBS)} exit=0 "
                f"duration={r.randint(1, 59)}.{r.randint(1, 9)}s")

    def token(r, ts, s):
        return f"{ts} INFO  {s} token refresh user={r.choice(_USERS)} ttl={r.randint(1000, 9000)}s"

    return [http, http, http, cache, slowq, heartbeat, worker, worker, gc, retry, upstream,
            json_done, json_done, json_flush, tls, reload, lease, batch, disk, sshd, rotate,
            span, pool, cron, token]


_TEMPLATES = _line_templates()


def _safe_line(ts: str, svc: str) -> str:
    return f"{ts} INFO  {svc} heartbeat ok"


def fmt_ts(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def make_pool(rng: random.Random, services: tuple[str, ...], reserved: Reserved,
              t_lo: datetime, t_hi: datetime, n_lines: int) -> list[str]:
    """`n_lines` chronological log lines with timestamps in (t_lo, t_hi], all reserved-clean."""
    span = max(1, int((t_hi - t_lo).total_seconds()))
    offsets = sorted(rng.randint(1, span) for _ in range(n_lines))
    lines = []
    for off in offsets:
        ts = fmt_ts(t_lo + timedelta(seconds=off))
        svc = rng.choice(services)
        for _ in range(20):
            line = rng.choice(_TEMPLATES)(rng, ts, svc)
            if reserved.clean(line):
                break
        else:
            line = _safe_line(ts, svc)
            if not reserved.clean(line):
                raise FitError(f"cannot build a reserved-clean filler line for {svc!r}")
        lines.append(line)
    return lines


# ---------------------------------------------------------------------------
# Exact budget fitting
# ---------------------------------------------------------------------------

@dataclass
class Fitted:
    text: str
    n_tokens: int
    filler_start: int  # char span of the log filler (from the cut first line to the last line)
    filler_end: int
    filler_lines: int


class Pool:
    """Chronological filler lines for one observation slot, with cached encodings of the
    pool text without its last `drop` lines."""

    def __init__(self, lines: list[str], enc: str = "o200k_base"):
        self.lines = lines
        self.enc = enc
        self._tok: dict[int, list[int]] = {}

    def tokens(self, drop: int = 0) -> list[int]:
        if drop not in self._tok:
            kept = self.lines[: len(self.lines) - drop] if drop else self.lines
            self._tok[drop] = tokens.encode("\n".join(kept), self.enc)
        return self._tok[drop]


def fit_observation(head: str, pool: Pool, foot: str, v: int, reserved: Reserved,
                    enc: str = "o200k_base", tolerance: int = 0) -> Fitted:
    """Fill `head + <filler> + foot` to exactly v tokens.

    The filler is a token-level suffix of the pool text ("\\n".join(pool lines)): the most
    recent log lines are kept whole and the earliest kept line is cut at a token boundary, as
    a log tail would cut it. `head` ends with the log header and `foot` starts with the log
    footer. Re-encoding at the joins can shift the count by a token, so suffix lengths around
    the estimate are tried; if a merge at the cut skips the exact total, the pool's last line
    is dropped (up to 3 times) to shift the alignment.
    """
    fixed = tokens.count(head + foot, enc)
    if fixed >= v:
        raise FitError(f"event text alone needs {fixed} tokens >= v={v}")
    best: Fitted | None = None
    for drop in range(4):
        pool_tokens = pool.tokens(drop)
        if len(pool_tokens) < v - fixed + 8:
            raise FitError("filler pool too small for the token budget")

        def attempt(n_body: int, pool_tokens: list[int] = pool_tokens) -> tuple[int, str, str]:
            body = tokens.decode(pool_tokens[-n_body:], enc)
            text = head + body + foot
            return tokens.count(text, enc), text, body

        first = v - fixed
        c0, _, _ = attempt(first)
        guess = first + (v - c0)
        for d in (0, -1, 1, -2, 2, -3, 3, -4, 4):
            n_body = guess + d
            if n_body <= 0 or n_body > len(pool_tokens):
                continue
            c, text, body = attempt(n_body)
            if not body.strip() or not reserved.clean(body):
                continue
            fit = Fitted(text, c, len(head), len(head) + len(body), body.count("\n") + 1)
            if c == v:
                return fit
            if c < v and (best is None or c > best.n_tokens):
                best = fit
    if best is not None and v - best.n_tokens <= tolerance:
        return best
    raise FitError(f"could not fit observation to v={v} (best {best and best.n_tokens})")
