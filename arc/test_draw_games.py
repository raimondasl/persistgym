"""Tests for the D15 game draw (arc/draw_games.py).

No network: beacon HTTP goes through httpx.MockTransport, outbound sockets are blocked for the
whole module, and git runs on throwaway local repositories (origin is a local bare repo).
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import random
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from arc import draw_games as dg
from common import runmeta

FREEZE_CT = 1_791_000_000                      # 2026-10-03T04:00:00Z
T_MS = (FREEZE_CT + 600) * 1000                # 2026-10-03T04:10:00Z
DAY_MS = 24 * 3600 * 1000
OUT_HEX = "0123456789ABCDEF" + "AB" * 56       # outputValue; SEED = 0x0123456789ABCDEF
DRAFT = "Version: 0.1-draft\n\n**Status: DRAFT for the researcher's review. Not yet frozen.**\n"
FROZEN = "Version: 0.2\n\n**Status: Frozen on 2026-10-03 by the researcher.**\n"


# ── no network ───────────────────────────────────────────────────────────

class NetworkBlocked(RuntimeError):
    pass


def _loopback(address) -> bool:
    host = address[0] if isinstance(address, tuple) else address
    if not isinstance(host, str):
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False


@pytest.fixture(scope="module", autouse=True)
def no_network():
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def connect(self, address):
        if not _loopback(address):
            raise NetworkBlocked(f"network access in a draw test: {address!r}")
        return real_connect(self, address)

    def connect_ex(self, address):
        if not _loopback(address):
            raise NetworkBlocked(f"network access in a draw test: {address!r}")
        return real_connect_ex(self, address)

    def getaddrinfo(host, *args, **kwargs):
        if not _loopback((host,)):
            raise NetworkBlocked(f"DNS lookup in a draw test: {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)

    mp = pytest.MonkeyPatch()
    mp.setattr(socket.socket, "connect", connect)
    mp.setattr(socket.socket, "connect_ex", connect_ex)
    mp.setattr(socket, "getaddrinfo", getaddrinfo)
    yield
    mp.undo()


@pytest.fixture(autouse=True)
def clean_code_checkout(monkeypatch):
    """The dirty-tree refusal and meta.json read the real checkout; pin them for tests."""
    monkeypatch.setattr(runmeta, "git_state",
                        lambda repo=None: {"git_commit": "c0de" * 10, "git_dirty": False})


# ── a throwaway repo: draft, freeze PR (merge commit), a later commit, a side branch ─────

def git(repo: Path, *args: str, date: int | None = None) -> str:
    """git in a test repo, isolated from the user's and the system's git config."""
    cfg = repo.parent / "empty.gitconfig"
    cfg.touch()
    env = {**os.environ, "GIT_CONFIG_GLOBAL": str(cfg), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
           "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.invalid"}
    if date is not None:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"@{date} +0000"
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env=env).stdout.strip()


def commit_file(repo: Path, name: str, text: str, msg: str, date: int) -> str:
    (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", msg, date=date)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture(scope="module")
def repo(tmp_path_factory) -> SimpleNamespace:
    """Built once per module (git is slow on Windows); tests only read it and fetch origin."""
    tmp_path = tmp_path_factory.mktemp("repo")
    work, origin = tmp_path / "work", tmp_path / "origin.git"
    work.mkdir()
    git(work, "init", "-q", "-b", "main")
    git(work, "init", "-q", "--bare", "-b", "main", str(origin))
    draft = commit_file(work, "PREREG.md", DRAFT, "m0: PREREG draft", FREEZE_CT - 7200)
    git(work, "checkout", "-q", "-b", "freeze")
    branch = commit_file(work, "PREREG.md", FROZEN, "m0: freeze PREREG", FREEZE_CT - 600)
    git(work, "checkout", "-q", "main")
    git(work, "merge", "-q", "--no-ff", "freeze", "-m", "Merge pull request #20", date=FREEZE_CT)
    merge = git(work, "rev-parse", "HEAD")
    later = commit_file(work, "README.md", "later\n", "m0: later change", FREEZE_CT + 3600)
    git(work, "checkout", "-q", "-b", "side", draft)
    side = commit_file(work, "PREREG.md", FROZEN, "m0: unmerged freeze", FREEZE_CT)
    git(work, "checkout", "-q", "main")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-q", "origin", "main")
    git(work, "fetch", "-q", "origin")
    return SimpleNamespace(work=work, draft=draft, branch=branch, merge=merge, later=later,
                           side=side)


# ── mocked beacons ───────────────────────────────────────────────────────

def nist_pulse(idx: int, ts_ms: int, out: str = OUT_HEX, chain: int = 2) -> bytes:
    return json.dumps({"pulse": {
        "uri": f"https://beacon.nist.gov/beacon/2.0/chain/{chain}/pulse/{idx}",
        "version": "2.0", "cipherSuite": 0, "period": 60000, "chainIndex": chain,
        "pulseIndex": idx, "timeStamp": dg.iso_ms(ts_ms), "statusCode": 0,
        "outputValue": out}}).encode()


SIGNATURE = bytes(range(96)).hex()
RANDOMNESS = hashlib.sha256(bytes.fromhex(SIGNATURE)).hexdigest()
DRAND_INFO = json.dumps({"public_key": "868f", "period": 30, "genesis_time": 1595431050,
                         "hash": dg.DRAND_CHAIN_HASH, "groupHash": "176f",
                         "schemeID": "pedersen-bls-chained",
                         "metadata": {"beaconID": "default"}}).encode()


def drand_round(rnd: int, randomness: str = RANDOMNESS) -> bytes:
    return json.dumps({"round": rnd, "randomness": randomness, "signature": SIGNATURE,
                       "previous_signature": "00"}).encode()


class Beacons:
    """MockTransport serving fixed (status, body) per URL; anything else is a 404."""

    def __init__(self, routes: dict[str, tuple[int, bytes]]):
        self.routes, self.urls = routes, []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.urls.append(url)
        status, body = self.routes.get(url, (404, b'{"error": "not found"}'))
        return httpx.Response(status, content=body)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


NIST_T = f"https://beacon.nist.gov/beacon/2.0/pulse/time/{T_MS}"
ROUND_T = dg.drand_round_at_or_after(T_MS // 1000)


def nist_ok(ts_ms: int = T_MS + 30_000, prev_ts_ms: int = T_MS - 30_000) -> Beacons:
    return Beacons({
        NIST_T: (200, nist_pulse(1000, ts_ms)),
        "https://beacon.nist.gov/beacon/2.0/chain/2/pulse/999": (200, nist_pulse(999, prev_ts_ms,
                                                                                  "CD" * 64)),
    })


def drand_routes(rnd: int = ROUND_T, **extra) -> dict:
    return {"https://api.drand.sh/info": (200, DRAND_INFO),
            f"https://api.drand.sh/public/{rnd}": (200, drand_round(rnd)), **extra}


def run_draw(repo, tmp_path, beacons: Beacons, now_ms: int, *extra: str, sha: str | None = None):
    out = tmp_path / "draw"
    code = dg.main([sha or repo.merge, "--out-root", str(out), "--run-id", "r1", *extra],
                   repo=repo.work, transport=beacons.transport, now_ms=lambda: now_ms,
                   sleep=lambda s: None)
    return code, out / "r1"


# ── the draw itself ──────────────────────────────────────────────────────

def test_derive_matches_an_independent_computation():
    seed = 0x0123456789ABCDEF
    d = dg.derive(seed)
    games = ["FT09", "SB26", "R11L", "CD82"]
    perm = random.Random(seed).sample(games, 4)
    units = sorted((g, c, r) for g in games for c in ["S0", "S1", "S2", "S4"] for r in [1, 2])
    b2 = [u for u in units if u[2] == 1 and u[1] in ("S0", "S4")]
    b3 = [u for u in units if u not in b2]

    assert d["perm"] == perm and sorted(perm) == sorted(games)
    assert d["pilot_game_d17"] == perm[0] and d["fallback_drop_game_d32"] == perm[3]
    assert (len(b2), len(b3)) == (8, 24)
    assert d["block2_order"] == random.Random(seed + 2).sample(b2, k=8)
    assert d["block3_order"] == random.Random(seed + 3).sample(b3, k=24)
    assert sorted(d["block2_order"] + d["block3_order"]) == units


def test_drand_round_numbering_matches_live_rounds():
    # Round 1 at genesis; round r at genesis + (r - 1) * 30 (docs.drand.love specification).
    assert dg.drand_round_at_or_after(dg.DRAND_GENESIS_S - 5) == 1
    assert dg.drand_round_at_or_after(dg.DRAND_GENESIS_S) == 1
    assert dg.drand_round_at_or_after(dg.DRAND_GENESIS_S + 1) == 2
    assert dg.drand_round_at_or_after(dg.DRAND_GENESIS_S + 30) == 2
    assert dg.drand_round_at_or_after(dg.DRAND_GENESIS_S + 31) == 3
    # api.drand.sh/public/latest returned round 6514981 at 2026-10-01T18:47:30Z.
    assert dg.drand_round_time_s(6514981) == 1790880450
    for t in (T_MS // 1000, T_MS // 1000 + 1, T_MS // 1000 + 29):
        r = dg.drand_round_at_or_after(t)
        assert dg.drand_round_time_s(r) >= t > dg.drand_round_time_s(r - 1)


def test_timestamps():
    assert dg.parse_ts_ms("2025-10-01T12:01:00.000Z") == 1_759_320_060_000
    assert dg.iso_ms(T_MS) == "2026-10-03T04:10:00.000Z"
    assert dg.target_ms(FREEZE_CT) == T_MS
    for bad in ("2025-10-01T12:01:00", "yesterday", None):
        with pytest.raises(dg.BeaconError):
            dg.parse_ts_ms(bad)


@pytest.mark.parametrize("text, frozen", [
    (DRAFT, False),
    (FROZEN, True),
    ("Version: 1.0\n**Status:** Frozen on 2026-10-03 by R.\n", True),
    ("Version: 0.10\nStatus: Frozen on 2026-10-03\n", True),
    ("Version: 0.2\n**Status: FROZEN on 2026-10-03.**\n", True),
    ("Version: 0.1\n**Status: Frozen on 2026-10-03 by R.**\n", False),
    ("Version: 0.2-draft\n**Status: Frozen on 2026-10-03 by R.**\n", False),
    ("Version: 0.2\n**Status: DRAFT. Not yet frozen.**\n", False),
    ("Version: 0.2\nno status line\n", False),
    ("no version line\n**Status: Frozen**\n", False),
    (None, False),
])
def test_prereg_state(text, frozen):
    assert dg.prereg_state(text).frozen is frozen


def test_the_draw_and_the_paid_launchers_share_one_freeze_rule():
    """The draw and both paid launchers read "frozen" the same way (common/prereg.py)."""
    from arc import run_path
    from common import approval, prereg
    assert dg.prereg_state is prereg.prereg_state is approval.prereg_state
    assert run_path.prereg_not_frozen is approval.prereg_not_frozen


def test_nist_draw_end_to_end(repo, tmp_path, capsys):
    beacons = nist_ok()
    code, run_dir = run_draw(repo, tmp_path, beacons, T_MS + 3_600_000)

    assert code == 0
    assert beacons.urls == [NIST_T, "https://beacon.nist.gov/beacon/2.0/chain/2/pulse/999"]
    draw = json.loads((run_dir / "draw.json").read_text(encoding="utf-8"))
    seed = 0x0123456789ABCDEF
    assert draw["seed"]["source"] == "nist" and draw["seed"]["seed"] == seed
    assert draw["seed"]["url"] == NIST_T and draw["target_utc"] == "2026-10-03T04:10:00.000Z"
    assert draw["derived"]["perm"] == random.Random(seed).sample(list(dg.GAMES), 4)
    assert draw["freeze"]["sha"] == repo.merge and draw["freeze"]["is_merge_commit"]
    assert draw["freeze"]["prereg_version"] == "0.2"
    assert (run_dir / "nist_pulse.json").read_bytes() == beacons.routes[NIST_T][1]
    assert draw["raw_sha256"]["nist_pulse.json"] == hashlib.sha256(
        beacons.routes[NIST_T][1]).hexdigest()
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    assert set(runmeta.REQUIRED) <= set(meta)
    assert meta["experiment"] == "draw" and meta["cost_usd"] == 0.0
    assert meta["pulse_url"] == NIST_T and meta["seeds"]["block3"] == seed + 3
    block = (run_dir / "decisions_block.md").read_text(encoding="utf-8")
    out = capsys.readouterr().out
    assert block in out and f"SEED = {seed}" in block
    assert f"perm[0] = {draw['derived']['perm'][0]}" in block
    assert block.count(" r1") + block.count(" r2") == 32


def test_pulse_exactly_at_t_counts(repo, tmp_path):
    code, run_dir = run_draw(repo, tmp_path, nist_ok(ts_ms=T_MS, prev_ts_ms=T_MS - 60_000),
                             T_MS + 1)
    assert code == 0
    assert json.loads((run_dir / "draw.json").read_text())["seed"]["source"] == "nist"


def test_fetches_origin_main_by_default_and_runs_once(repo, tmp_path):
    out = tmp_path / "draw"
    args = [repo.merge, "--out-root", str(out)]
    kw = {"repo": repo.work, "now_ms": lambda: T_MS + 120_000, "sleep": lambda s: None}
    assert dg.main([*args, "--run-id", "a"], transport=nist_ok().transport, **kw) == 0
    beacons = nist_ok()
    assert dg.main([*args, "--run-id", "b"], transport=beacons.transport, **kw) == 1
    assert beacons.urls == [] and not (out / "b").exists()


def test_too_early_makes_no_request(repo, tmp_path):
    beacons = nist_ok()
    code, run_dir = run_draw(repo, tmp_path, beacons, T_MS - 1)
    assert code == 3 and beacons.urls == [] and not run_dir.exists()


@pytest.mark.parametrize("nist_route", [
    (404, b"{}"),                                    # no pulse yet
    (200, nist_pulse(990, T_MS - 600_000)),          # an earlier pulse: none at or after T
])
def test_no_nist_pulse_waits_then_falls_back_to_drand(repo, tmp_path, nist_route):
    early = Beacons({NIST_T: nist_route, **drand_routes()})
    code, run_dir = run_draw(repo, tmp_path, early, T_MS + DAY_MS - 1)
    assert code == 3 and not run_dir.exists() and early.urls == [NIST_T]

    late = Beacons({NIST_T: nist_route, **drand_routes()})
    code, run_dir = run_draw(repo, tmp_path, late, T_MS + DAY_MS)
    assert code == 0
    draw = json.loads((run_dir / "draw.json").read_text())
    assert draw["seed"]["source"] == "drand"
    assert draw["seed"]["seed"] == int(RANDOMNESS[:16], 16)
    assert draw["seed"]["url"] == f"https://api.drand.sh/public/{ROUND_T}"
    assert dg.drand_round_time_s(ROUND_T) * 1000 >= T_MS
    assert late.urls == [NIST_T, "https://api.drand.sh/info",
                         f"https://api.drand.sh/public/{ROUND_T}"]
    assert (run_dir / "drand_round.json").read_bytes() == drand_round(ROUND_T)
    assert "drand fallback" in (run_dir / "decisions_block.md").read_text()


def test_nist_pulse_24h_after_t_falls_back(repo, tmp_path):
    beacons = Beacons({NIST_T: (200, nist_pulse(5000, T_MS + DAY_MS)), **drand_routes()})
    code, run_dir = run_draw(repo, tmp_path, beacons, T_MS + DAY_MS + 60_000)
    assert code == 0
    draw = json.loads((run_dir / "draw.json").read_text())
    assert draw["seed"]["source"] == "drand" and "24 h or more" in draw["seed"]["fallback_reason"]
    assert (run_dir / "nist_pulse.json").exists()   # kept as evidence for the fallback


def test_pulse_that_is_not_the_first_after_t_is_an_error(repo, tmp_path):
    code, run_dir = run_draw(repo, tmp_path, nist_ok(prev_ts_ms=T_MS), T_MS + 120_000)
    assert code == 2 and not run_dir.exists()


def test_drand_checks(repo, tmp_path):
    bad_hash = Beacons({NIST_T: (404, b"{}"), **drand_routes(**{
        f"https://api.drand.sh/public/{ROUND_T}": (200, drand_round(ROUND_T, "ab" * 32))})})
    assert run_draw(repo, tmp_path, bad_hash, T_MS + DAY_MS)[0] == 2
    other_chain = Beacons({NIST_T: (404, b"{}"), **drand_routes(**{
        "https://api.drand.sh/info": (200, DRAND_INFO.replace(b"8990e7a9", b"52db9ba7"))})})
    assert run_draw(repo, tmp_path, other_chain, T_MS + DAY_MS)[0] == 2


def test_unreachable_nist_needs_the_flag_to_fall_back(repo, tmp_path):
    down = {NIST_T: (503, b"")}
    beacons = Beacons({**down, **drand_routes()})
    assert run_draw(repo, tmp_path, beacons, T_MS + 60_000)[0] == 2
    assert beacons.urls == [NIST_T] * dg.MAX_ATTEMPTS
    assert run_draw(repo, tmp_path, Beacons({**down, **drand_routes()}), T_MS + DAY_MS)[0] == 2
    code, run_dir = run_draw(repo, tmp_path, Beacons({**down, **drand_routes()}), T_MS + DAY_MS,
                             "--fallback-if-nist-unreachable")
    assert code == 0
    draw = json.loads((run_dir / "draw.json").read_text())
    assert draw["seed"]["source"] == "drand" and "unreachable" in draw["seed"]["fallback_reason"]


def test_bad_nist_json_is_an_error(repo, tmp_path):
    beacons = Beacons({NIST_T: (200, b'{"pulse": {"outputValue": "zz"}}')})
    assert run_draw(repo, tmp_path, beacons, T_MS + 60_000)[0] == 2


# ── refusals ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("which, why", [
    ("draft", "PREREG.md at the draft commit is not frozen"),
    ("branch", "inside the merged branch, not on origin/main's first-parent history"),
    ("later", "PREREG.md was already frozen at its first parent"),
    ("side", "not on origin/main"),
])
def test_refuses_anything_but_the_freeze_commit(repo, tmp_path, capsys, which, why):
    beacons = nist_ok()
    code, run_dir = run_draw(repo, tmp_path, beacons, T_MS + 120_000, sha=getattr(repo, which))
    assert code == 1, why
    assert beacons.urls == [] and not run_dir.exists()
    assert "draw_games:" in capsys.readouterr().err


@pytest.mark.parametrize("sha", ["main", "HEAD~1", "ffffffffffffffffffffffffffffffffffffffff"])
def test_refuses_non_sha_and_unknown_commits(repo, tmp_path, sha):
    assert run_draw(repo, tmp_path, nist_ok(), T_MS + 120_000, "--no-fetch", sha=sha)[0] == 1


def test_option_like_ref_never_reaches_git(repo):
    with pytest.raises(dg.Refused, match="hex commit SHA"):
        dg.check_freeze_commit(repo.work, "--output=x", fetch=False)


def test_refuses_a_dirty_checkout(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(runmeta, "git_state",
                        lambda repo=None: {"git_commit": "c0de" * 10, "git_dirty": True})
    beacons = nist_ok()
    assert run_draw(repo, tmp_path, beacons, T_MS + 120_000)[0] == 1
    assert beacons.urls == []
