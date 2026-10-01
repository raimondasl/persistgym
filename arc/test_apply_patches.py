"""Tests for the ARC patch workflow (pin, patch series, sanitized test runs)."""

from __future__ import annotations

import importlib
import re
import shutil
import sys
import types
from pathlib import Path

import pytest

from arc import apply_patches as ap

UPSTREAM_URL = "https://github.com/arcprize/arc-agi-3-benchmarking"
needs_submodule = pytest.mark.skipif(
    not (ap.UPSTREAM_DIR / ".git").exists() or shutil.which("git") is None,
    reason="arc/upstream submodule is not checked out",
)


def test_gitmodules_points_at_upstream_harness():
    text = (ap.REPO_ROOT / ".gitmodules").read_text()

    assert '[submodule "arc/upstream"]' in text
    assert "path = arc/upstream" in text
    assert f"url = {UPSTREAM_URL}" in text


@needs_submodule
def test_superproject_records_pinned_commit():
    assert ap.PINNED_COMMIT.startswith("4ca00e6")
    assert ap.recorded_pin(ap.sanitized_env()) == ap.PINNED_COMMIT


def test_patch_series_is_numbered_and_each_patch_has_tests():
    patches = ap.patch_files()

    assert len(patches) >= 5
    for index, patch in enumerate(patches, start=1):
        text = patch.read_text(encoding="utf-8")
        assert f"[PATCH {index}/{len(patches)}]" in text
        changed = re.findall(r"^diff --git a/(\S+) b/", text, flags=re.MULTILINE)
        assert any(path.startswith("tests/unit/test_") for path in changed), patch.name
        assert "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" in text


def test_patch_files_rejects_gaps_and_unnumbered_files(tmp_path):
    (tmp_path / "0001-first.patch").write_text("x")
    (tmp_path / "0003-third.patch").write_text("x")
    with pytest.raises(ap.PatchError, match="must run 0001..0002"):
        ap.patch_files(tmp_path)

    (tmp_path / "0003-third.patch").rename(tmp_path / "0002-second.patch")
    (tmp_path / "fixup.patch").write_text("x")
    with pytest.raises(ap.PatchError, match="Unnumbered"):
        ap.patch_files(tmp_path)


def test_series_digest_tracks_names_and_bytes(tmp_path):
    first = tmp_path / "0001-a.patch"
    first.write_bytes(b"one\n")
    before = ap.series_digest([first])

    first.write_bytes(b"one\r\n")

    assert ap.series_digest([first]) != before


def test_sanitized_env_drops_credentials_and_live_switches():
    base = {
        "PATH": "/bin",
        "HOME": "/home/me",
        "UV_CACHE_DIR": "/cache",
        "OPENAI_API_KEY": "x",
        "GOOGLE_API_KEY": "x",
        "GEMINI_API_KEY": "x",
        "ARC_API_KEY": "x",
        "ARC_BASE_URL": "http://localhost",
        "RUNPOD_API_KEY": "x",
        "GOOGLE_GENAI_USE_VERTEXAI": "true",
        "GOOGLE_APPLICATION_CREDENTIALS": "/creds.json",
        "AZURE_SPEECH_KEY": "x",
        "SOME_SERVICE_TOKEN": "x",
        "RUN_GOOGLE_LIVE_TESTS": "1",
        "RUN_OPENAI_COMPACTION_LIVE_TESTS": "1",
        "HOST": "localhost",
        "VIRTUAL_ENV": "/root/.venv",
    }

    env = ap.sanitized_env(base)

    assert env == {
        "PATH": "/bin",
        "HOME": "/home/me",
        "UV_CACHE_DIR": "/cache",
        **ap.COMMITTER,
        "PYTHONPATH": str(ap.ARC_DIR),
    }


def test_no_dotenv_plugin_disables_load_dotenv(monkeypatch):
    calls: list[tuple] = []
    fake = types.ModuleType("dotenv")
    fake_main = types.ModuleType("dotenv.main")
    fake.load_dotenv = fake_main.load_dotenv = lambda *a, **k: calls.append(a) or True
    fake.main = fake_main
    monkeypatch.setitem(sys.modules, "dotenv", fake)
    monkeypatch.setitem(sys.modules, "dotenv.main", fake_main)
    monkeypatch.delitem(sys.modules, "arc.no_dotenv_plugin", raising=False)

    importlib.import_module("arc.no_dotenv_plugin")

    assert fake.load_dotenv() is False
    assert fake_main.load_dotenv(dotenv_path=".env") is False
    assert calls == []


def test_gitattributes_keeps_patches_byte_exact():
    rules = (ap.ARC_DIR / ".gitattributes").read_text().splitlines()

    assert "patches/*.patch -text" in rules


@needs_submodule
def test_series_applies_cleanly_to_the_pin():
    assert ap.main(["--no-tests", "--name", "root-test-apply"]) == 0
    assert not (ap.WORK_DIR / "root-test-apply").exists()


def test_scratch_area_is_ignored_by_git_and_root_pytest():
    assert ".work/" in (ap.ARC_DIR / ".gitignore").read_text().splitlines()
    conftest = (ap.ARC_DIR / "conftest.py").read_text()
    assert 'collect_ignore = ["upstream", ".work"]' in conftest


def test_module_constants_point_inside_the_repository():
    assert ap.ARC_DIR == Path(ap.__file__).resolve().parent
    assert ap.WORK_DIR.parent == ap.ARC_DIR
    assert ap.PATCH_DIR.parent == ap.ARC_DIR
