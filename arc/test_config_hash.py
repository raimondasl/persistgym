"""The config freeze record (arc/config_hash.py, arc/config_freeze.json)."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from arc import apply_patches as ap
from arc import config_hash as freeze
from arc import offline_smoke
from common import runmeta

needs_submodule = pytest.mark.skipif(
    not (ap.UPSTREAM_DIR / ".git").exists() or shutil.which("git") is None,
    reason="arc/upstream submodule is not checked out",
)


def _configs(tier: str = "standard") -> dict[str, dict]:
    return {cid: {"id": cid, "request": {"model": "gemini-3.8-flash", "service_tier": tier,
                                         "max_output_tokens": 65_536},
                  "client": {"transport_retry": {"max_wait_seconds": 1_800.0}}}
            for cid in freeze.PROFILES.values()}


def test_profiles_are_the_path_configs():
    assert freeze.PROFILES == offline_smoke.PATH_CONFIGS


def test_build_record_hashes_each_resolved_profile(tmp_path):
    patches = [tmp_path / "0001-a.patch", tmp_path / "0002-b.patch"]
    for p in patches:
        p.write_bytes(p.name.encode())
    configs = _configs()

    record = freeze.build_record(configs, patches=patches, commit="c" * 40, tree="t" * 40)

    assert record["upstream"]["pinned_commit"] == ap.PINNED_COMMIT
    assert record["patch_series"] == {"files": ["0001-a.patch", "0002-b.patch"],
                                      "sha256": ap.series_digest(patches)}
    assert (record["patched_commit"], record["patched_tree"]) == ("c" * 40, "t" * 40)
    for label, cid in freeze.PROFILES.items():
        entry = record["profiles"][label]
        assert entry == {"config_id": cid, "sha256": runmeta.config_hash(configs[cid]),
                         "config": configs[cid]}
    assert len({e["sha256"] for e in record["profiles"].values()}) == 4
    assert freeze.render(record) == freeze.render(json.loads(freeze.render(record)))


def test_build_record_needs_every_profile(tmp_path):
    configs = _configs()
    configs.pop(freeze.PROFILES["S2"])
    with pytest.raises(freeze.FreezeError, match="not resolved"):
        freeze.build_record(configs, patches=[], commit="c", tree="t")


def test_committed_record_matches_the_patches_and_hashes():
    record = freeze.load_record()

    assert freeze.record_problems(record, ap.patch_files()) == []
    assert freeze.FREEZE_PATH.read_text(encoding="utf-8") == freeze.render(record)


def test_committed_profiles_request_the_standard_tier_at_high_thinking():
    record = freeze.load_record()
    for label, entry in record["profiles"].items():
        request = entry["config"]["request"]
        assert request["service_tier"] == "standard", label
        assert request["generation_config"]["thinking_level"] == "high", label
        assert request["model"] == "gemini-3.8-flash", label
        assert entry["config"]["id"] == entry["config_id"]
    # The path changes one thing at a time; the request block is shared.
    requests = [e["config"]["request"] for e in record["profiles"].values()]
    assert all(r == requests[0] for r in requests)


@pytest.mark.parametrize("change, problem", [
    (lambda r: r["profiles"]["S1"]["config"]["request"].update(service_tier="flex"),
     "S1: sha256"),
    (lambda r: r["patch_series"].update(sha256="0" * 64), "SHA-256 differs"),
    (lambda r: r["patch_series"]["files"].pop(), "file names differ"),
    (lambda r: r["upstream"].update(pinned_commit="0" * 40), "pinned commit"),
    (lambda r: r["profiles"]["S4"].update(config_id="other"), "config IDs"),
])
def test_record_problems_names_each_disagreement(change, problem):
    record = freeze.load_record()
    change(record)

    problems = freeze.record_problems(record, ap.patch_files())

    assert any(problem in p for p in problems), problems


def test_load_record_reports_a_missing_file(tmp_path):
    with pytest.raises(freeze.FreezeError, match="cannot read"):
        freeze.load_record(tmp_path / "nope.json")


def test_main_writes_and_checks_with_a_mocked_build(monkeypatch, tmp_path, capsys):
    record = freeze.load_record()
    monkeypatch.setattr(freeze, "build", lambda keep=False: record)
    out = tmp_path / "freeze.json"

    assert freeze.main(["--check", "--out", str(out)]) == 1       # missing file
    assert freeze.main(["--out", str(out)]) == 0
    assert out.read_bytes() == freeze.FREEZE_PATH.read_bytes()
    assert freeze.main(["--check", "--out", str(out)]) == 0
    out.write_text("{}", encoding="utf-8")
    assert freeze.main(["--check", "--out", str(out)]) == 1
    assert "out of date" in capsys.readouterr().err


def test_build_runs_the_patched_harness_without_keys(monkeypatch):
    calls: list[str] = []
    resolved = _configs()
    monkeypatch.setattr(ap, "check_pin", lambda env: calls.append("pin"))
    monkeypatch.setattr(ap, "create_worktree", lambda path, env: calls.append("create"))
    monkeypatch.setattr(ap, "apply_series", lambda path, patches, env: calls.append("apply"))
    monkeypatch.setattr(ap, "sync_environment", lambda path, env: calls.append("sync"))
    monkeypatch.setattr(ap, "remove_worktree", lambda path, env: calls.append("remove"))
    monkeypatch.setattr(ap, "_git", lambda args, cwd, env: "a" * 40 if args[-1] == "HEAD"
                        else "b" * 40)
    monkeypatch.setenv("GOOGLE_API_KEY", "must-not-reach-the-inner-process")
    seen: dict = {}

    def fake_resolve(worktree, env, ids):
        seen.update(env=env, ids=ids, worktree=worktree)
        return resolved

    monkeypatch.setattr(freeze, "resolve_profiles", fake_resolve)

    record = freeze.build()

    assert calls == ["pin", "create", "apply", "sync", "remove"]
    assert seen["ids"] == list(freeze.PROFILES.values())
    assert seen["worktree"] == ap.WORK_DIR / freeze.WORKTREE_NAME
    assert "GOOGLE_API_KEY" not in seen["env"]
    assert record["patched_commit"] == "a" * 40 and record["patched_tree"] == "b" * 40


def test_resolve_profiles_command(monkeypatch, tmp_path):
    seen: dict = {}

    def fake_run(command, cwd, env, *, capture=False):
        seen.update(command=command, cwd=cwd, env=env)
        out = Path(command[command.index("--out") + 1])
        out.write_text(json.dumps({"x": {"id": "x"}}), encoding="utf-8")
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(ap, "_run", fake_run)

    assert freeze.resolve_profiles(tmp_path, {"PATH": "p"}, ["x"]) == {"x": {"id": "x"}}
    command = seen["command"]
    assert command[:6] == ["uv", "run", "--no-sync", "--project", str(tmp_path), "python"]
    assert command[6:9] == [str(freeze.INNER), "resolve", "--configs"]
    assert seen["env"]["PYTHONPATH"].split(os.pathsep) == [str(tmp_path), str(ap.ARC_DIR)]
    assert seen["cwd"] != tmp_path                      # a short scratch directory


@needs_submodule
def test_the_series_still_gives_the_frozen_commit_and_tree():
    env = ap.sanitized_env()
    worktree = ap.WORK_DIR / "root-test-freeze"
    record = freeze.load_record()
    try:
        ap.create_worktree(worktree, env)
        ap.apply_series(worktree, ap.patch_files(), env)
        commit = ap._git(["rev-parse", "HEAD"], worktree, env)
        tree = ap._git(["rev-parse", "HEAD^{tree}"], worktree, env)
        configs_blob = ap._git(["show", "HEAD:benchmarking/model_configs.yaml"], worktree, env)
    finally:
        ap.remove_worktree(worktree, env)

    assert (commit, tree) == (record["patched_commit"], record["patched_tree"])
    for entry in record["profiles"].values():
        assert f'- id: "{entry["config_id"]}"' in configs_blob
