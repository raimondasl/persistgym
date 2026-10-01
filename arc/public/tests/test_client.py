import json

import httpx
import pytest

from arc.public import client as client_mod
from arc.public.client import CacheMiss, FetchError, PoliteClient

GUID = "484de130-939a-4773-b771-d0108ed46a56"


class FakeTime:
    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s


@pytest.fixture(autouse=True)
def _reset_throttle():
    client_mod._LAST_DONE[0] = float("-inf")
    yield
    client_mod._LAST_DONE[0] = float("-inf")


def make_client(tmp_path, handler, **kw):
    ft = FakeTime()
    c = PoliteClient(tmp_path, transport=httpx.MockTransport(handler), sleep=ft.sleep,
                     clock=ft.clock, log=None, **kw)
    return c, ft


def test_cache_is_never_redownloaded(tmp_path):
    calls = []

    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(200, json={"config": "x"})

    c, _ = make_client(tmp_path, handler)
    assert c.session(GUID) == {"config": "x"}
    assert c.session(GUID) == {"config": "x"}
    assert len(calls) == 1 and calls[0].endswith(f"/api/sessions/{GUID}")
    assert c.n_requests == 1 and c.n_cache_hits == 1
    assert (tmp_path / "arc_public" / "sessions" / f"{GUID}.json").exists()


def test_existing_cache_file_is_used_without_any_request(tmp_path):
    p = tmp_path / "arc_public" / "sessions" / f"{GUID}.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"cached": True}), encoding="utf-8")

    def handler(req):  # pragma: no cover - must not be called
        raise AssertionError("network used despite cache")

    c, _ = make_client(tmp_path, handler)
    assert c.session(GUID) == {"cached": True}


def test_user_agent_and_throttle(tmp_path):
    seen = []

    def handler(req):
        seen.append(req.headers["user-agent"])
        return httpx.Response(200, json={})

    c, ft = make_client(tmp_path, handler)
    c.session(GUID)
    c.session("00000000-0000-4000-8000-000000000000")
    assert all("persistgym" in ua for ua in seen)
    # second request waited for the full interval since the first finished
    assert ft.sleeps and ft.sleeps[-1] >= 2.0


def test_retries_429_and_5xx_with_backoff_honouring_retry_after(tmp_path):
    responses = [httpx.Response(429, headers={"Retry-After": "30"}),
                 httpx.Response(503), httpx.Response(200, json={"ok": 1})]

    def handler(req):
        return responses.pop(0)

    c, ft = make_client(tmp_path, handler)
    assert c.session(GUID) == {"ok": 1}
    assert c.n_requests == 3 and c.n_retries == 2
    assert 30 in ft.sleeps            # Retry-After honoured over the 5 s base
    assert 10 in ft.sleeps            # exponential backoff on the 2nd retry


def test_non_retryable_status_raises_and_caches_nothing(tmp_path):
    c, _ = make_client(tmp_path, lambda req: httpx.Response(404))
    with pytest.raises(FetchError):
        c.session(GUID)
    assert c.n_requests == 1
    assert not list((tmp_path / "arc_public" / "sessions").glob("*"))


def test_gives_up_after_max_attempts(tmp_path):
    c, _ = make_client(tmp_path, lambda req: httpx.Response(500), max_attempts=3)
    with pytest.raises(FetchError):
        c.session(GUID)
    assert c.n_requests == 3


def test_invalid_json_is_not_cached(tmp_path):
    c, _ = make_client(tmp_path, lambda req: httpx.Response(200, text="<html>oops"))
    with pytest.raises(ValueError):
        c.session(GUID)
    assert not list((tmp_path / "arc_public" / "sessions").glob("*"))


def test_truncated_ndjson_is_not_cached(tmp_path):
    c, _ = make_client(tmp_path, lambda req: httpx.Response(200, text='{"a": 1}\n{"b": '))
    with pytest.raises(ValueError):
        c.recording("lp85-305b61c3", GUID)
    assert not c.recording_path("lp85-305b61c3", GUID).exists()


def test_recording_path_and_offline_mode(tmp_path):
    c, _ = make_client(tmp_path, lambda req: httpx.Response(200, text='{"a": 1}\n'),
                       offline=True)
    with pytest.raises(CacheMiss):
        c.recording("lp85-305b61c3", GUID)
    assert c.n_requests == 0
    assert c.recording_path("lp85-305b61c3", GUID).parts[-3:] == (
        "recordings", "lp85-305b61c3", f"{GUID}.ndjson")


def test_rejects_bad_ids_and_impolite_interval(tmp_path):
    c, _ = make_client(tmp_path, lambda req: httpx.Response(200, json={}))
    with pytest.raises(ValueError):
        c.session("../../etc/passwd")
    with pytest.raises(ValueError):
        c.recording("LP85/../x", GUID)
    with pytest.raises(ValueError):
        PoliteClient(tmp_path, min_interval_s=0.5)


def test_raw_dir_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PERSISTGYM_RAW_DIR", str(tmp_path))
    assert client_mod.cache_root() == tmp_path / "arc_public"
