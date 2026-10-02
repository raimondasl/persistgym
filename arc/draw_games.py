"""D15 game draw: a public beacon value published after the PREREG freeze orders the ARC games.

    uv run python -m arc.draw_games <freeze-commit-sha> [--run-id ID] [--no-fetch]
                                    [--fallback-if-nist-unreachable] [--out-root DIR]

Run it ONCE, after the researcher has merged the frozen PREREG.md (PREREG §0.4, §7.3). It makes
no paid calls and needs no key: it reads git and one or two public randomness beacons.

Rule (PREREG D15, D17, D18, D32):
1. T = committer time of the freeze commit + 10 minutes (UTC, whole seconds).
2. SEED = int(outputValue[:16], 16) of the first NIST Randomness Beacon 2.0 pulse with
   timeStamp >= T, fetched from ``https://beacon.nist.gov/beacon/2.0/pulse/time/<T in ms>``.
3. Fallback, only when NIST has no such pulse within 24 h of T (the first pulse at or after T is
   at T + 24 h or later, or none exists once 24 h have passed): the first drand mainnet round at
   or after T (League of Entropy ``default`` chain), from ``https://api.drand.sh/public/<round>``;
   SEED = int(randomness[:16], 16).
4. perm = random.Random(SEED).sample(GAMES, 4). perm[0] is the truncated-pilot game (D17) and
   perm[3] the game dropped under the 3-game fallback (D32).
5. Run orders (D18): random.Random(SEED + 2).sample(units, k=len(units)) for block 2 (replicate 1
   of S0 and S4, 8 runs) and SEED + 3 the same way for block 3 (the other 24 runs). In both,
   units are the (game, config, replicate) tuples sorted lexicographically.

Preconditions (exit 1 when one fails):
- the code checkout has no uncommitted changes to tracked files (the draw is tied to a commit);
- the argument is a hex SHA of a commit on origin/main's first-parent history (fetched first
  unless ``--no-fetch``), i.e. the merge or squash commit of the freeze PR, not a commit inside
  the merged branch;
- PREREG.md at that commit has ``Version: x.y`` with x.y >= 0.2 and no suffix such as
  ``-draft``, and a ``Status:`` line whose text starts with "Frozen" (any case);
- PREREG.md at its first parent is not frozen, so the commit is the freeze itself and not a
  later commit (which would move T);
- no draw for this freeze commit exists under the output root.

Exit codes: 0 drawn; 1 refused (precondition); 2 beacon error (unreachable after retries,
unexpected response or a failed check); 3 too early (T not reached yet, or NIST has no pulse at
or after T yet and fewer than 24 h have passed; re-run later).

Output, ``results/draw/<run_id>/``: ``meta.json``; ``draw.json`` (seed, source URL, permutation,
roles, run orders); the raw beacon responses byte for byte (``nist_pulse.json``,
``nist_prev_pulse.json``, and ``drand_info.json`` and ``drand_round.json`` when the fallback is
used); ``decisions_block.md``, which is also printed for pasting into results/decisions.md.

Sources (checked 2026-10-01):
- NIST Beacon 2.0 REST API,
  https://csrc.nist.gov/projects/interoperable-randomness-beacons/beacon-20 :
  ``https://beacon.nist.gov/beacon/2.0/pulse/time/<unix time>`` gives the "Pulse at a specific
  (Unix) time (or next closest)", with Unix time in milliseconds since 1970-01-01T00:00:00Z, and
  one pulse every 60 s. A request for 1759320030000 (2025-10-01T12:00:30Z) returned the pulse
  stamped 2025-10-01T12:01:00.000Z, the next pulse at or after that time; the script still
  checks timeStamp >= T. A pulse's ``uri`` has the form
  ``https://beacon.nist.gov/beacon/2.0/chain/<chainIndex>/pulse/<pulseIndex>``; the script
  fetches the preceding pulse there and checks that it is before T, so the pulse used is the
  first one at or after T.
- drand HTTP API v1, https://docs.drand.love/developer/API-v1/drand-http-api : ``/info`` and
  ``/public/{round}`` without a chain hash serve the League of Entropy ``default`` chain, whose
  hash is 8990e7a9...2ce (https://docs.drand.love/developer/). https://api.drand.sh/info returned
  period 30, genesis_time 1595431050 and schemeID pedersen-bls-chained; the script checks these.
- drand round timing and output, https://docs.drand.love/docs/specification/ : round 1 is at the
  genesis time and ``round = floor((t - genesis) / period) + 1``, so round r is at
  genesis + (r - 1) * period; the randomness is the SHA-256 of the round's signature (checked on
  round 1000 from api.drand.sh). The script checks that hash.
- Python ``random``: only ``random()`` is guaranteed to reproduce across Python versions, not
  ``sample`` (https://docs.python.org/3.12/library/random.html, "Notes on Reproducibility"). The
  recorded output is authoritative (PREREG §7.3), and the Python version is recorded with it.

Not checked here: the beacons' signatures (NIST's RSA signature and hash chain, drand's BLS
signature). The raw responses are kept so anyone can verify them with the beacons' own tools.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Self

import httpx

from common import runmeta
from common.prereg import prereg_state

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = REPO_ROOT / "results" / "draw"

GAMES = ("FT09", "SB26", "R11L", "CD82")       # D14 pool, in PLAN §8.3 order
CONFIGS = ("S0", "S1", "S2", "S4")
REPLICATES = (1, 2)
BLOCK2_CONFIGS = ("S0", "S4")                  # block 2 = replicate 1 of these (PREREG §1)

DELAY_S = 10 * 60
FALLBACK_AFTER_MS = 24 * 3600 * 1000

NIST_BASE = "https://beacon.nist.gov/beacon/2.0"
DRAND_BASE = "https://api.drand.sh"
DRAND_CHAIN_HASH = "8990e7a9aaed2ffed73dbd7092123d6f289930540d7651336225dc172e51b2ce"
DRAND_GENESIS_S = 1595431050
DRAND_PERIOD_S = 30

USER_AGENT = "persistgym-draw/0.1 (one-off research game draw; a few requests, one at a time)"
MIN_INTERVAL_S = 2.5
MAX_ATTEMPTS = 4
BACKOFF_BASE_S = 10.0
TIMEOUT = httpx.Timeout(30.0)

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_SHA_RE = re.compile(r"[0-9a-fA-F]{7,64}")


class DrawStop(RuntimeError):
    code = 2


class Refused(DrawStop):
    code = 1


class BeaconError(DrawStop):
    code = 2


class BeaconUnreachable(BeaconError):
    pass


class TooEarly(DrawStop):
    code = 3


# ── time ─────────────────────────────────────────────────────────────────
def iso_ms(ms: int) -> str:
    return (EPOCH + timedelta(milliseconds=ms)).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z")


def parse_ts_ms(value: str) -> int:
    """Milliseconds since the epoch of an RFC 3339 UTC timestamp such as 2025-10-01T12:01:00.000Z."""
    try:
        dt = datetime.fromisoformat(value)          # Python >= 3.11 accepts the "Z" suffix
    except (TypeError, ValueError) as e:
        raise BeaconError(f"unparseable timeStamp {value!r}") from e
    if dt.tzinfo is None:
        raise BeaconError(f"timeStamp without a time zone: {value!r}")
    return (dt - EPOCH) // timedelta(milliseconds=1)


def target_ms(committer_time_s: int) -> int:
    """T: the freeze commit's committer time + 10 minutes, in ms."""
    return (committer_time_s + DELAY_S) * 1000


def wall_ms() -> int:
    return time.time_ns() // 1_000_000


# ── git and PREREG checks ────────────────────────────────────────────────
def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)


def _rev(repo: Path, ref: str) -> str | None:
    p = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    return p.stdout.strip() if p.returncode == 0 else None


def _file_at(repo: Path, sha: str, path: str) -> str | None:
    p = _git(repo, "show", f"{sha}:{path}")
    return p.stdout if p.returncode == 0 else None


def check_freeze_commit(repo: Path, ref: str, *, fetch: bool = True) -> dict:
    """Refuse unless ``ref`` is the commit on origin/main that froze PREREG.md (version >= 0.2)."""
    if not _SHA_RE.fullmatch(ref):
        raise Refused(f"expected a hex commit SHA, got {ref!r}")
    if fetch:
        p = _git(repo, "fetch", "--quiet", "origin", "main")
        if p.returncode != 0:
            raise Refused(f"git fetch origin main failed ({p.stderr.strip()}); re-run with "
                          "--no-fetch to check against the local origin/main")
    sha = _rev(repo, ref)
    if sha is None:
        raise Refused(f"{ref} is not a commit in {repo}")
    main = _rev(repo, "origin/main")
    if main is None:
        raise Refused("origin/main does not exist in this repository")
    if sha not in _git(repo, "rev-list", "--first-parent", main).stdout.split():
        on_main = _git(repo, "merge-base", "--is-ancestor", sha, main).returncode == 0
        raise Refused(f"{sha} is on origin/main but not on its first-parent history (a commit "
                      "inside a merged branch); pass the PR's merge commit" if on_main
                      else f"{sha} is not on origin/main ({main})")
    ct, ci, parents, subject = _git(repo, "show", "-s", "--format=%ct%n%cI%n%P%n%s",
                                    sha).stdout.split("\n")[:4]
    state = prereg_state(_file_at(repo, sha, "PREREG.md"))
    if not state.frozen:
        raise Refused(f"PREREG.md at {sha} is not frozen: {state.why_not}")
    parent_list = parents.split()
    if parent_list and prereg_state(_file_at(repo, parent_list[0], "PREREG.md")).frozen:
        raise Refused(f"PREREG.md is already frozen at {sha}'s first parent {parent_list[0]}, so "
                      f"{sha} is not the freeze commit; pass the commit that froze it")
    head_has = _git(repo, "merge-base", "--is-ancestor", sha, "HEAD").returncode == 0
    return {"sha": sha, "subject": subject, "committer_time_s": int(ct),
            "committer_time_iso": ci, "parents": parent_list,
            "is_merge_commit": len(parent_list) > 1, "origin_main": main,
            "prereg_version": state.version, "prereg_status": state.status,
            "checkout_head_contains_it": head_has}


# ── HTTP ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Response:
    url: str
    status: int
    body: bytes


@dataclass
class Fetcher:
    """GETs one at a time, >= MIN_INTERVAL_S apart, retrying 429, 5xx and transport errors."""

    transport: httpx.BaseTransport | None = None
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    log: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._http = httpx.Client(headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                                  timeout=TIMEOUT, follow_redirects=True,
                                  transport=self.transport)
        self._last = float("-inf")

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def get(self, url: str) -> Response:
        err = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            gap = self.clock() - self._last
            if gap < MIN_INTERVAL_S:
                self.sleep(MIN_INTERVAL_S - gap)
            try:
                r = self._http.get(url)
            except httpx.TransportError as e:
                err = f"{type(e).__name__}: {e}"
            else:
                if r.status_code != 429 and r.status_code < 500:
                    self.log.append({"url": url, "status": r.status_code, "attempts": attempt,
                                     "fetched_utc": runmeta.utc_now()})
                    return Response(url, r.status_code, r.content)
                err = f"HTTP {r.status_code}"
            finally:
                self._last = self.clock()
            if attempt < MAX_ATTEMPTS:
                self.sleep(BACKOFF_BASE_S * 2 ** (attempt - 1))
        self.log.append({"url": url, "status": None, "attempts": MAX_ATTEMPTS, "error": err,
                         "fetched_utc": runmeta.utc_now()})
        raise BeaconUnreachable(f"GET {url} failed after {MAX_ATTEMPTS} attempts: {err}")


def _json(resp: Response) -> dict:
    try:
        data = json.loads(resp.body)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise BeaconError(f"GET {resp.url}: response is not JSON: {e}") from e
    if not isinstance(data, dict):
        raise BeaconError(f"GET {resp.url}: expected a JSON object")
    return data


# ── NIST ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class NistPulse:
    uri: str
    chain_index: int
    pulse_index: int
    time_stamp: str
    ts_ms: int
    status_code: int | None
    output_value: str


def parse_nist(resp: Response) -> NistPulse:
    try:
        p = _json(resp)["pulse"]
        out = p["outputValue"]
        if not (isinstance(out, str) and re.fullmatch(r"[0-9A-Fa-f]{128}", out)):
            raise BeaconError(f"GET {resp.url}: outputValue is not 512 bits of hex: {out!r}")
        status = p.get("statusCode")
        return NistPulse(uri=str(p.get("uri")), chain_index=int(p["chainIndex"]),
                         pulse_index=int(p["pulseIndex"]), time_stamp=p["timeStamp"],
                         ts_ms=parse_ts_ms(p["timeStamp"]), output_value=out,
                         status_code=None if status is None else int(status))
    except (KeyError, TypeError, ValueError) as e:
        raise BeaconError(f"GET {resp.url}: unexpected pulse JSON ({type(e).__name__}: {e})") from e


def nist_first_pulse(fetcher: Fetcher, t_ms: int) -> tuple[str, NistPulse | None, dict]:
    """("ok" | "late" | "none", pulse, raw files) for the first NIST pulse at or after T.

    "late": that pulse is 24 h or more after T. "none": NIST has no pulse at or after T (404, or it
    returned an earlier pulse).
    """
    resp = fetcher.get(f"{NIST_BASE}/pulse/time/{t_ms}")
    if resp.status == 404:
        return "none", None, {}
    if resp.status != 200:
        raise BeaconError(f"GET {resp.url} -> HTTP {resp.status}")
    raw = {"nist_pulse.json": resp.body}
    pulse = parse_nist(resp)
    if pulse.ts_ms < t_ms:
        return "none", pulse, raw
    if pulse.ts_ms >= t_ms + FALLBACK_AFTER_MS:
        return "late", pulse, raw
    if pulse.pulse_index > 1:
        prev_resp = fetcher.get(f"{NIST_BASE}/chain/{pulse.chain_index}/pulse/"
                                f"{pulse.pulse_index - 1}")
        if prev_resp.status != 200:
            raise BeaconError(f"GET {prev_resp.url} -> HTTP {prev_resp.status}")
        raw["nist_prev_pulse.json"] = prev_resp.body
        prev = parse_nist(prev_resp)
        if (prev.chain_index, prev.pulse_index) != (pulse.chain_index, pulse.pulse_index - 1):
            raise BeaconError(f"GET {prev_resp.url} returned pulse {prev.chain_index}/"
                              f"{prev.pulse_index}")
        if prev.ts_ms >= t_ms:
            raise BeaconError(f"pulse {pulse.uri} ({pulse.time_stamp}) is not the first at or "
                              f"after T={iso_ms(t_ms)}: its predecessor is at {prev.time_stamp}")
    return "ok", pulse, raw


# ── drand ────────────────────────────────────────────────────────────────
def drand_round_at_or_after(t_s: int) -> int:
    if t_s <= DRAND_GENESIS_S:
        return 1
    return -(-(t_s - DRAND_GENESIS_S) // DRAND_PERIOD_S) + 1


def drand_round_time_s(rnd: int) -> int:
    return DRAND_GENESIS_S + (rnd - 1) * DRAND_PERIOD_S


def drand_round(fetcher: Fetcher, t_ms: int) -> tuple[dict, dict]:
    """(details, raw files) of the first drand ``default``-chain round at or after T, checked."""
    info_resp = fetcher.get(f"{DRAND_BASE}/info")
    if info_resp.status != 200:
        raise BeaconError(f"GET {info_resp.url} -> HTTP {info_resp.status}")
    info = _json(info_resp)
    expected = {"hash": DRAND_CHAIN_HASH, "period": DRAND_PERIOD_S,
                "genesis_time": DRAND_GENESIS_S}
    got = {k: info.get(k) for k in expected}
    if got != expected:
        raise BeaconError(f"GET {info_resp.url}: not the pinned default chain: {got}")
    rnd = drand_round_at_or_after(-(-t_ms // 1000))
    resp = fetcher.get(f"{DRAND_BASE}/public/{rnd}")
    if resp.status != 200:
        raise BeaconError(f"GET {resp.url} -> HTTP {resp.status}")
    data = _json(resp)
    randomness, signature = data.get("randomness"), data.get("signature")
    if data.get("round") != rnd:
        raise BeaconError(f"GET {resp.url} returned round {data.get('round')!r}")
    if not (isinstance(randomness, str) and re.fullmatch(r"[0-9a-f]{64}", randomness)):
        raise BeaconError(f"GET {resp.url}: randomness is not 256 bits of hex: {randomness!r}")
    try:
        digest = hashlib.sha256(bytes.fromhex(signature)).hexdigest()
    except (TypeError, ValueError) as e:
        raise BeaconError(f"GET {resp.url}: signature is not hex") from e
    if digest != randomness:
        raise BeaconError(f"GET {resp.url}: randomness is not SHA-256(signature)")
    details = {"round": rnd, "round_time_utc": iso_ms(drand_round_time_s(rnd) * 1000),
               "randomness": randomness, "chain_hash": DRAND_CHAIN_HASH,
               "info_url": info_resp.url}
    return details, {"drand_info.json": info_resp.body, "drand_round.json": resp.body}


# ── seed ─────────────────────────────────────────────────────────────────
@dataclass
class Seed:
    source: str                 # "nist" or "drand"
    seed: int
    seed_hex: str
    url: str
    details: dict
    raw: dict[str, bytes]
    fallback_reason: str | None = None


def beacon_seed(fetcher: Fetcher, t_ms: int, now_ms: int, *,
                fallback_if_unreachable: bool = False) -> Seed:
    if now_ms < t_ms:
        raise TooEarly(f"T = {iso_ms(t_ms)} has not been reached (now {iso_ms(now_ms)}); "
                       "re-run after T")
    deadline = t_ms + FALLBACK_AFTER_MS
    try:
        state, pulse, raw = nist_first_pulse(fetcher, t_ms)
    except BeaconUnreachable as e:
        if now_ms < deadline:
            raise
        if not fallback_if_unreachable:
            raise BeaconUnreachable(
                f"{e}. More than 24 h have passed since T. If NIST really has no pulse at or "
                "after T, the drand fallback applies: record why in results/decisions.md and "
                "re-run with --fallback-if-nist-unreachable") from e
        return drand_seed(fetcher, t_ms, {}, (
            f"NIST beacon unreachable at {iso_ms(now_ms)}, 24 h or more after T ({e}); "
            "fallback allowed by --fallback-if-nist-unreachable"))
    if state == "ok":
        assert pulse is not None
        return Seed("nist", int(pulse.output_value[:16], 16), pulse.output_value[:16],
                    f"{NIST_BASE}/pulse/time/{t_ms}",
                    {"uri": pulse.uri, "chain_index": pulse.chain_index,
                     "pulse_index": pulse.pulse_index, "time_stamp": pulse.time_stamp,
                     "status_code": pulse.status_code, "output_value": pulse.output_value},
                    raw)
    if state == "late":
        assert pulse is not None
        return drand_seed(fetcher, t_ms, raw, (
            f"the first NIST pulse at or after T is {pulse.uri} at {pulse.time_stamp}, "
            "24 h or more after T"))
    if now_ms < deadline:
        raise TooEarly(f"NIST has no pulse at or after T = {iso_ms(t_ms)} yet; the drand "
                       f"fallback applies only from {iso_ms(deadline)}. Re-run later")
    return drand_seed(fetcher, t_ms, raw, (
        f"NIST had no pulse at or after T by {iso_ms(now_ms)}, 24 h or more after T"))


def drand_seed(fetcher: Fetcher, t_ms: int, nist_raw: dict[str, bytes], reason: str) -> Seed:
    """The fallback seed; NIST's responses (if any) are kept with it as evidence."""
    details, drand_raw = drand_round(fetcher, t_ms)
    randomness = details["randomness"]
    return Seed("drand", int(randomness[:16], 16), randomness[:16],
                f"{DRAND_BASE}/public/{details['round']}", details, {**nist_raw, **drand_raw},
                fallback_reason=reason)


# ── derived draw ─────────────────────────────────────────────────────────
Unit = tuple[str, str, int]


def block_units() -> tuple[list[Unit], list[Unit]]:
    """Block 2 (replicate 1 of S0 and S4) and block 3 (the other runs), each sorted."""
    units = sorted((g, c, r) for g in GAMES for c in CONFIGS for r in REPLICATES)
    block2 = [u for u in units if u[2] == 1 and u[1] in BLOCK2_CONFIGS]
    return block2, [u for u in units if u not in block2]


def derive(seed: int) -> dict:
    perm = random.Random(seed).sample(list(GAMES), len(GAMES))
    block2, block3 = block_units()
    return {"perm": perm, "pilot_game_d17": perm[0], "fallback_drop_game_d32": perm[3],
            "block2_seed": seed + 2,
            "block2_order": random.Random(seed + 2).sample(block2, k=len(block2)),
            "block3_seed": seed + 3,
            "block3_order": random.Random(seed + 3).sample(block3, k=len(block3))}


def _order(units: list[Unit]) -> str:
    return ", ".join(f"{i}. {g} {c} r{r}" for i, (g, c, r) in enumerate(units, 1))


def decisions_block(draw: dict) -> str:
    fz, d, s = draw["freeze"], draw["derived"], draw["seed"]
    if s["source"] == "nist":
        det = s["details"]
        prev = ("; the preceding pulse is before T" if "nist_prev_pulse.json" in draw["raw_files"]
                else "")
        source = (f"- **Seed source:** NIST Randomness Beacon 2.0 pulse {det['uri']} (timeStamp "
                  f"{det['time_stamp']}, statusCode {det['status_code']}), fetched from "
                  f"{s['url']}{prev}. `outputValue[:16]` = `{s['seed_hex']}`, so "
                  f"SEED = {s['seed']}.")
    else:
        det = s["details"]
        source = (f"- **Seed source (drand fallback):** {s['fallback_reason']}. drand `default` "
                  f"chain round {det['round']} (at {det['round_time_utc']}), fetched from "
                  f"{s['url']}; randomness = SHA-256(signature) checked. `randomness[:16]` = "
                  f"`{s['seed_hex']}`, so SEED = {s['seed']}.")
    games = ", ".join(f"'{g}'" for g in GAMES)
    lines = [
        f"## {draw['drawn_utc'][:10]}: ARC game draw (D15, D17, D18, D32)",
        (f"- **Freeze commit:** `{fz['sha']}` (\"{fz['subject']}\"), PREREG.md Version "
         f"{fz['prereg_version']}, status \"{fz['prereg_status']}\". Committer time "
         f"{fz['committer_time_iso']}; T = committer time + 10 min = {draw['target_utc']}."),
        source,
        (f"- **Permutation:** `random.Random(SEED).sample([{games}], 4)` = "
         f"{', '.join(d['perm'])} (Python {draw['python_version']}). The recorded output is "
         "authoritative."),
        (f"- **Truncated-pilot game (D17):** perm[0] = {d['pilot_game_d17']}. **Dropped under "
         f"the 3-game fallback (D32):** perm[3] = {d['fallback_drop_game_d32']}."),
        f"- **Block 2 order (D18, SEED + 2):** {_order(d['block2_order'])}.",
        f"- **Block 3 order (D18, SEED + 3):** {_order(d['block3_order'])}.",
        (f"- **Output:** `{draw['run_dir']}/` from `arc/draw_games.py` at commit "
         f"`{draw['code_commit']}`, drawn {draw['drawn_utc']}."),
        "- **Spend:** $0 (no paid calls).",
    ]
    return "\n".join(lines) + "\n"


# ── main ─────────────────────────────────────────────────────────────────
def _existing_draw(out_root: Path, sha: str) -> Path | None:
    for p in sorted(out_root.glob("*/draw.json")):
        try:
            if json.loads(p.read_text(encoding="utf-8"))["freeze"]["sha"] == sha:
                return p.parent
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def _write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                    newline="\n")


def run(args: argparse.Namespace, *, repo: Path, transport: httpx.BaseTransport | None,
        now_ms: Callable[[], int], sleep: Callable[[float], None]) -> int:
    started = runmeta.utc_now()
    code = runmeta.git_state()
    if code["git_dirty"]:
        raise Refused("the checkout has uncommitted changes to tracked files; commit or discard "
                      "them so the draw is tied to a commit")
    freeze = check_freeze_commit(repo, args.freeze_commit, fetch=not args.no_fetch)
    out_root: Path = args.out_root
    if (prior := _existing_draw(out_root, freeze["sha"])) is not None:
        raise Refused(f"a draw for {freeze['sha']} already exists: {prior}. The draw runs once "
                      "(PREREG §7.3)")
    now = now_ms()
    run_id = args.run_id or (EPOCH + timedelta(milliseconds=now)).strftime("%Y%m%dT%H%M%SZ")
    run_dir = out_root / run_id
    if run_dir.exists():
        raise Refused(f"{run_dir} already exists")
    t_ms = target_ms(freeze["committer_time_s"])

    with Fetcher(transport=transport, sleep=sleep) as fetcher:
        seed = beacon_seed(fetcher, t_ms, now,
                           fallback_if_unreachable=args.fallback_if_nist_unreachable)
        http_log = fetcher.log
    derived = derive(seed.seed)

    try:
        rel_dir = run_dir.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel_dir = run_dir.as_posix()
    draw = {
        "rule": "PREREG D15 (seed), D17 (pilot game), D18 (run orders), D32 (3-game drop)",
        "freeze": freeze, "target_ms": t_ms, "target_utc": iso_ms(t_ms),
        "fallback_deadline_utc": iso_ms(t_ms + FALLBACK_AFTER_MS),
        "drawn_utc": iso_ms(now), "python_version": sys.version.split()[0],
        "seed": {"source": seed.source, "seed": seed.seed, "seed_hex": seed.seed_hex,
                 "url": seed.url, "fallback_reason": seed.fallback_reason,
                 "details": seed.details},
        "games": list(GAMES), "configs": list(CONFIGS), "replicates": list(REPLICATES),
        "derived": derived, "raw_files": sorted(seed.raw),
        "raw_sha256": {k: hashlib.sha256(v).hexdigest() for k, v in sorted(seed.raw.items())},
        "http_log": http_log, "run_dir": rel_dir, "code_commit": code["git_commit"],
    }
    block = decisions_block(draw)

    run_dir.mkdir(parents=True)
    for name, body in seed.raw.items():
        (run_dir / name).write_bytes(body)
    _write_json(run_dir / "draw.json", draw)
    (run_dir / "decisions_block.md").write_text(block, encoding="utf-8", newline="\n")
    runmeta.write_meta(
        run_dir,
        experiment="draw", run_id=run_id, cell_or_config="d15_beacon_draw",
        config={"freeze_commit": freeze["sha"], "games": list(GAMES), "configs": list(CONFIGS),
                "replicates": list(REPLICATES), "block2_configs": list(BLOCK2_CONFIGS),
                "delay_s": DELAY_S, "fallback_after_ms": FALLBACK_AFTER_MS,
                "nist_base": NIST_BASE, "drand_base": DRAND_BASE,
                "drand_chain_hash": DRAND_CHAIN_HASH,
                "fallback_if_nist_unreachable": args.fallback_if_nist_unreachable},
        model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None,
        template_id=None, repeat_index=None,
        seeds={"seed": seed.seed, "block2": seed.seed + 2, "block3": seed.seed + 3},
        started_utc=started, finished_utc=runmeta.utc_now(), exit_reason="completed",
        tokens={"paid_calls": 0}, cost_usd=0.0,
        raw_transcript_path=f"{rel_dir} (raw beacon responses, committed; see raw_sha256)",
        outputs=["draw.json", "decisions_block.md", *sorted(seed.raw)],
        beacon_source=seed.source, pulse_url=seed.url, fallback_reason=seed.fallback_reason,
        freeze_prereg_version=freeze["prereg_version"], python_version=draw["python_version"],
        raw_sha256=draw["raw_sha256"], paid_calls=0,
    )
    print(f"wrote {run_dir}\n\nPaste into results/decisions.md:\n")
    print(block)
    return 0


def main(argv: list[str] | None = None, *, repo: Path = REPO_ROOT,
         transport: httpx.BaseTransport | None = None,
         now_ms: Callable[[], int] = wall_ms, sleep: Callable[[float], None] = time.sleep) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("freeze_commit", help="SHA of the PR merge commit that froze PREREG.md")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--out-root", type=Path, default=OUT_ROOT)
    ap.add_argument("--no-fetch", action="store_true",
                    help="check against the local origin/main without fetching it first")
    ap.add_argument("--fallback-if-nist-unreachable", action="store_true",
                    help="24 h or more after T, use drand when NIST cannot be reached at all "
                         "(record the reason in results/decisions.md first)")
    args = ap.parse_args(argv)
    try:
        return run(args, repo=repo, transport=transport, now_ms=now_ms, sleep=sleep)
    except DrawStop as e:
        print(f"draw_games: {e}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
