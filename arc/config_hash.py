"""The config freeze record of the four ARC path profiles (PREREG §7.1, PLAN §16.4).

Run from the repository root:

    uv run python -m arc.config_hash            # rebuild and write arc/config_freeze.json
    uv run python -m arc.config_hash --check    # rebuild and compare with the committed file

It builds the patched harness in a scratch worktree (arc/.work/freeze) from the pinned
submodule and arc/patches, resolves S0, S1, S2 and S4 with the harness's own
``get_model_config`` (``arc/run_path_inner.py resolve``, which validates them), and writes
per profile its config ID, the resolved config and the SHA-256 of its canonical JSON
(``common.runmeta.config_hash``, the same hash every meta.json carries), plus the submodule
pin, the patch series (file names and SHA-256) and the patched commit and tree IDs.

The file has no timestamps, so the same patches always give the same bytes. The paid
launcher (arc/run_path.py) refuses to run unless the patch files, the patched tree and the
resolved profile all match this record. No key is read and nothing is called except
``uv sync --locked`` for the harness's dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arc import apply_patches as ap
from common import runmeta

UPSTREAM_URL = "https://github.com/arcprize/arc-agi-3-benchmarking"
PROFILES = {
    "S0": "google-gemini-3-8-flash-high",
    "S1": "google-gemini-3-8-flash-high-rolling-summary",
    "S2": "google-gemini-3-8-flash-high-rolling-summary-notes-off",
    "S4": "google-gemini-3-8-flash-high-provider-adapter",
}
FREEZE_PATH = ap.ARC_DIR / "config_freeze.json"
INNER = ap.ARC_DIR / "run_path_inner.py"
WORKTREE_NAME = "freeze"
HASH_RULE = ("sha256 of json.dumps(config, sort_keys=True, separators=(',', ':'), "
             "ensure_ascii=False) encoded as UTF-8 (common.runmeta.config_hash)")


class FreezeError(RuntimeError):
    pass


def build_record(configs: Mapping[str, dict], *, patches: Sequence[Path], commit: str,
                 tree: str) -> dict[str, Any]:
    """The freeze record for resolved `configs` (config ID -> config)."""
    missing = [cid for cid in PROFILES.values() if cid not in configs]
    if missing:
        raise FreezeError(f"profiles not resolved: {missing}")
    return {
        "what": "ARC path profiles frozen for the paid runs (PREREG §7.1); written by "
                "`uv run python -m arc.config_hash`, do not edit by hand",
        "hash_rule": HASH_RULE,
        "upstream": {"repository": UPSTREAM_URL, "pinned_commit": ap.PINNED_COMMIT},
        "patch_series": {"files": [p.name for p in patches],
                         "sha256": ap.series_digest(patches)},
        "patched_commit": commit,
        "patched_tree": tree,
        "profiles": {
            label: {"config_id": cid, "sha256": runmeta.config_hash(configs[cid]),
                    "config": configs[cid]}
            for label, cid in PROFILES.items()
        },
    }


def render(record: Mapping[str, Any]) -> str:
    return json.dumps(record, indent=2, ensure_ascii=False) + "\n"


def load_record(path: Path = FREEZE_PATH) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise FreezeError(f"cannot read the freeze record {path}: {e}") from None


def record_problems(record: Mapping[str, Any], patches: Sequence[Path]) -> list[str]:
    """How `record` disagrees with itself, the pin or the current patch files."""
    problems = []
    if record.get("upstream", {}).get("pinned_commit") != ap.PINNED_COMMIT:
        problems.append("pinned commit differs from arc/apply_patches.py PINNED_COMMIT")
    series = record.get("patch_series", {})
    if series.get("files") != [p.name for p in patches]:
        problems.append("patch file names differ from arc/patches")
    if series.get("sha256") != ap.series_digest(patches):
        problems.append("patch series SHA-256 differs from arc/patches")
    profiles = record.get("profiles", {})
    if {k: v.get("config_id") for k, v in profiles.items()} != PROFILES:
        problems.append("profile labels or config IDs differ from PROFILES")
    for label, entry in profiles.items():
        if runmeta.config_hash(entry.get("config")) != entry.get("sha256"):
            problems.append(f"{label}: sha256 does not match its config")
    return problems


def resolve_profiles(worktree: Path, env: Mapping[str, str],
                     config_ids: Sequence[str]) -> dict[str, dict]:
    """The profiles as the patched harness's get_model_config returns them. Runs
    run_path_inner.py resolve with `env` (sanitized: no keys) and a short scratch cwd."""
    with tempfile.TemporaryDirectory(prefix="arcfreeze-", ignore_cleanup_errors=True) as tmp:
        out = Path(tmp) / "configs.json"
        command = ["uv", "run", "--no-sync", "--project", str(worktree), "python", str(INNER),
                   "resolve", "--configs", ",".join(config_ids), "--out", str(out)]
        run_env = {**env, "PYTHONPATH": os.pathsep.join([str(worktree), str(ap.ARC_DIR)]),
                   "PYTHONUTF8": "1"}
        result = ap._run(command, Path(tmp), run_env, capture=True)
        if result.returncode != 0 or not out.exists():
            raise FreezeError(f"resolving the profiles failed (exit {result.returncode}):\n"
                              f"{result.stdout}{result.stderr}")
        return json.loads(out.read_text(encoding="utf-8"))


def build(*, keep: bool = False, name: str = WORKTREE_NAME) -> dict[str, Any]:
    """Apply the series in arc/.work/<name>, resolve the profiles, return the record."""
    env = ap.sanitized_env()
    worktree = ap.WORK_DIR / name
    ap.check_pin(env)
    patches = ap.patch_files()
    try:
        ap.create_worktree(worktree, env)
        ap.apply_series(worktree, patches, env)
        commit = ap._git(["rev-parse", "HEAD"], worktree, env)
        tree = ap._git(["rev-parse", "HEAD^{tree}"], worktree, env)
        ap.sync_environment(worktree, env)
        configs = resolve_profiles(worktree, env, list(PROFILES.values()))
    finally:
        if not keep:
            try:
                ap.remove_worktree(worktree, env)
            except ap.PatchError as e:
                print(f"warning: could not remove {worktree}: {e}", file=sys.stderr)
    return build_record(configs, patches=patches, commit=commit, tree=tree)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="compare with the committed record instead of writing it")
    parser.add_argument("--keep", action="store_true", help="keep arc/.work/freeze")
    parser.add_argument("--out", type=Path, default=FREEZE_PATH)
    args = parser.parse_args(argv)
    try:
        record = build(keep=args.keep)
    except (ap.PatchError, FreezeError, subprocess.SubprocessError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    text = render(record)
    if args.check:
        current = args.out.read_text(encoding="utf-8") if args.out.exists() else None
        if current != text:
            print(f"{args.out} is out of date: run `uv run python -m arc.config_hash` and "
                  "commit the result", file=sys.stderr)
            return 1
        print(f"{args.out} matches the patched harness")
    else:
        args.out.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.out}")
    for label, entry in record["profiles"].items():
        print(f"  {label}  {entry['sha256']}  {entry['config_id']}")
    print(f"  patch series {record['patch_series']['sha256']}  "
          f"({len(record['patch_series']['files'])} files)")
    print(f"  patched commit / tree {record['patched_commit']} / {record['patched_tree']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
