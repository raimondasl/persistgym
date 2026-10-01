"""Apply arc/patches to the pinned ARC harness in a scratch worktree and test it.

Run from the repository root:

    uv run arc/apply_patches.py              # apply every patch, run upstream unit tests
    uv run arc/apply_patches.py --each       # also run the unit tests after each patch
    uv run arc/apply_patches.py --no-tests   # only check that the series applies
    uv run arc/apply_patches.py --keep       # keep arc/.work/<name> for inspection

The scratch worktree is a `git worktree` of the arc/upstream submodule, created at
the pinned commit under arc/.work/ (gitignored). Patches are applied with
`git am` using a fixed committer and the author dates, so the same series always
produces the same commit IDs. Tests run with every API key and live-test switch
removed from the environment and with python-dotenv disabled, so they cannot
reach a paid API. Only tests/unit is run.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

PINNED_COMMIT = "4ca00e607e3364a501fcbf7d1b7537dd2729cec3"
ARC_DIR = Path(__file__).resolve().parent
REPO_ROOT = ARC_DIR.parent
UPSTREAM_DIR = ARC_DIR / "upstream"
PATCH_DIR = ARC_DIR / "patches"
WORK_DIR = ARC_DIR / ".work"
PATCH_NAME = re.compile(r"^(\d{4})-.+\.patch$")
COMMITTER = {
    "GIT_COMMITTER_NAME": "persistgym apply_patches",
    "GIT_COMMITTER_EMAIL": "apply-patches@persistgym.invalid",
}
# Environment variables never passed to the harness tests: anything that looks
# like a credential, provider settings, live-test switches and harness targets.
_DROPPED_ENV = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)"
    r"|^(OPENAI|ANTHROPIC|GOOGLE|GEMINI|XAI|GROK|DEEPSEEK|OPENROUTER|GROQ|FIREWORKS"
    r"|RUNPOD|ARC)_"
    r"|^RUN_.*_LIVE_TESTS$"
    r"|^(SCHEME|HOST|PORT|RECORDINGS_DIR|VIRTUAL_ENV)$",
    re.IGNORECASE,
)


class PatchError(RuntimeError):
    pass


def patch_files(patch_dir: Path = PATCH_DIR) -> list[Path]:
    """Return NNNN-*.patch files in order; the numbers must run 0001, 0002, ..."""
    patches = sorted(p for p in patch_dir.glob("*.patch") if PATCH_NAME.match(p.name))
    numbers = [int(p.name[:4]) for p in patches]
    if numbers != list(range(1, len(patches) + 1)):
        raise PatchError(f"Patch numbers must run 0001..{len(patches):04d}: {numbers}")
    stray = sorted(p.name for p in patch_dir.glob("*.patch") if not PATCH_NAME.match(p.name))
    if stray:
        raise PatchError(f"Unnumbered patch files in {patch_dir}: {stray}")
    return patches


def series_digest(patches: Sequence[Path]) -> str:
    """SHA-256 over every patch name and its exact bytes, in order."""
    digest = hashlib.sha256()
    for patch in patches:
        digest.update(patch.name.encode("utf-8") + b"\0")
        digest.update(patch.read_bytes() + b"\0")
    return digest.hexdigest()


def sanitized_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Copy of the environment without keys, tokens or live-test switches."""
    source = os.environ if base is None else base
    env = {name: value for name, value in source.items() if not _DROPPED_ENV.search(name)}
    env.update(COMMITTER)
    env["PYTHONPATH"] = str(ARC_DIR)
    return env


def _run(
    args: Sequence[str], cwd: Path, env: Mapping[str, str], *, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(args)}  (in {cwd})", flush=True)
    return subprocess.run(
        list(args),
        cwd=cwd,
        env=dict(env),
        text=True,
        capture_output=capture,
        check=False,
    )


def _git(args: Sequence[str], cwd: Path, env: Mapping[str, str]) -> str:
    result = _run(["git", *args], cwd, env, capture=True)
    if result.returncode != 0:
        raise PatchError(f"git {' '.join(args)} failed:\n{result.stdout}{result.stderr}")
    return result.stdout.strip()


def recorded_pin(env: Mapping[str, str]) -> str:
    """Commit the superproject's HEAD records for arc/upstream."""
    line = _git(["ls-tree", "HEAD", "arc/upstream"], REPO_ROOT, env)
    parts = line.split()
    if len(parts) < 3 or parts[1] != "commit":
        raise PatchError(f"arc/upstream is not a submodule at HEAD: {line!r}")
    return parts[2]


def check_pin(env: Mapping[str, str]) -> None:
    if not (UPSTREAM_DIR / ".git").exists():
        raise PatchError(
            "arc/upstream is not checked out. Run: git submodule update --init arc/upstream"
        )
    pin = recorded_pin(env)
    if pin != PINNED_COMMIT:
        raise PatchError(f"Superproject records arc/upstream at {pin}, not {PINNED_COMMIT}.")


def remove_worktree(path: Path, env: Mapping[str, str]) -> None:
    if path.exists():
        result = _run(
            ["git", "worktree", "remove", "--force", str(path)], UPSTREAM_DIR, env, capture=True
        )
        if result.returncode != 0 and path.exists():
            shutil.rmtree(path)
    _git(["worktree", "prune"], UPSTREAM_DIR, env)


def create_worktree(path: Path, env: Mapping[str, str]) -> None:
    remove_worktree(path, env)
    path.parent.mkdir(parents=True, exist_ok=True)
    _git(["worktree", "add", "--detach", str(path), PINNED_COMMIT], UPSTREAM_DIR, env)


def apply_series(path: Path, patches: Sequence[Path], env: Mapping[str, str]) -> None:
    result = _run(
        ["git", "am", "--committer-date-is-author-date", *map(str, patches)],
        path,
        env,
        capture=True,
    )
    if result.returncode != 0:
        _run(["git", "am", "--abort"], path, env, capture=True)
        names = ", ".join(p.name for p in patches)
        raise PatchError(f"git am failed for {names}:\n{result.stdout}{result.stderr}")


def sync_environment(path: Path, env: Mapping[str, str]) -> None:
    for attempt in (1, 2):
        if _run(["uv", "sync", "--locked"], path, env).returncode == 0:
            return
        if attempt == 1:
            # Windows can briefly deny access to uv's launcher files; retry once.
            time.sleep(2)
    raise PatchError("uv sync --locked failed in the scratch worktree.")


def run_unit_tests(path: Path, env: Mapping[str, str], extra: Sequence[str]) -> int:
    args = [
        "uv", "run", "--no-sync", "pytest", "-q", "--color=no",
        "-p", "no_dotenv_plugin", "-p", "no:cacheprovider",
        "tests/unit", *extra,
    ]  # fmt: skip
    return _run(args, path, env).returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--name", default="patched", help="scratch worktree name under arc/.work")
    parser.add_argument("--keep", action="store_true", help="keep the scratch worktree")
    parser.add_argument("--no-tests", action="store_true", help="only apply the patches")
    parser.add_argument("--each", action="store_true", help="test after every patch")
    parser.add_argument("pytest_args", nargs="*", help="extra pytest arguments (after --)")
    args = parser.parse_args(argv)

    env = sanitized_env()
    path = WORK_DIR / args.name
    failures: list[str] = []
    try:
        check_pin(env)
        patches = patch_files()
        create_worktree(path, env)
        if not args.no_tests:
            sync_environment(path, env)
        steps = [[p] for p in patches] if args.each else [patches]
        for step in steps:
            apply_series(path, step, env)
            if args.no_tests:
                continue
            label = step[-1].name if args.each else "full series"
            if run_unit_tests(path, env, args.pytest_args) != 0:
                failures.append(label)
        head = _git(["rev-parse", "HEAD"], path, env)
        tree = _git(["rev-parse", "HEAD^{tree}"], path, env)
    except PatchError as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        return 1
    finally:
        if not args.keep:
            try:
                remove_worktree(path, env)
            except PatchError as error:
                print(f"warning: could not remove {path}: {error}", file=sys.stderr)

    print("\nSummary")
    print(f"  pinned upstream commit : {PINNED_COMMIT}")
    for patch in patches:
        print(f"  applied                : {patch.name}")
    print(f"  patch series sha256    : {series_digest(patches)}")
    print(f"  patched HEAD / tree    : {head} / {tree}")
    if args.no_tests:
        print("  upstream unit tests    : not run (--no-tests)")
    elif failures:
        print(f"  upstream unit tests    : FAILED after {', '.join(failures)}")
    else:
        print("  upstream unit tests    : passed")
    if args.keep:
        print(f"  scratch worktree       : {path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
