"""Throwaway git repositories for the paid-guard tests (common/approval.py), shared with the
harness tests. Each test repo gets a local bare repository as its `origin`, so the guard's
`git fetch origin main` never leaves the machine (the test fixtures also set
GIT_ALLOW_PROTOCOL=file, so git refuses any network transport)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from common.approval import format_line

# Experiments the default test approval covers, and a max_usd above every phase cap test.
DEFAULT_EXPERIMENTS = ("toggle_pilot", "replay_probe", "persistgym_pilot")
DEFAULT_MAX_USD = "1000"


def _env(repo: Path) -> dict:
    empty = repo.parent / ".test-gitconfig"
    empty.touch()
    return {**os.environ, "GIT_CONFIG_GLOBAL": str(empty), "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "GIT_ALLOW_PROTOCOL": "file"}


def git_in(repo: Path, *args: str) -> None:
    """Run git in a test repo, isolated from the user's and the system's git config."""
    git_out(repo, *args)


def git_out(repo: Path, *args: str) -> str:
    """`git_in`, returning the command's stdout."""
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          encoding="utf-8", env=_env(repo)).stdout


def approval_line(name: str, experiments=DEFAULT_EXPERIMENTS,
                  max_usd: str = DEFAULT_MAX_USD) -> str:
    return format_line(name, experiments, max_usd)


def decisions_text(*blocks: str, experiments=DEFAULT_EXPERIMENTS,
                   max_usd: str = DEFAULT_MAX_USD) -> str:
    """A results/decisions.md that approves `blocks` the way the paid guard reads it."""
    return "# Decisions log\n\n" + "".join(
        approval_line(b, experiments, max_usd) + "\n" for b in blocks)


def write_decisions(repo: Path, text: str) -> None:
    (repo / "results").mkdir(exist_ok=True)
    (repo / "results" / "decisions.md").write_text(text, encoding="utf-8")


def bare_origin(repo: Path) -> Path:
    """The local bare repository used as `repo`'s origin (next to `repo`, not inside it)."""
    return repo.parent / f"{repo.name}-origin.git"


def add_origin(repo: Path) -> Path:
    bare = bare_origin(repo)
    bare.mkdir()
    git_in(bare, "init", "-q", "--bare")
    git_in(repo, "remote", "add", "origin", str(bare))
    return bare


def push_main(repo: Path) -> None:
    """Publish `repo`'s HEAD as origin/main (what the researcher's merge does)."""
    git_in(repo, "push", "-q", "--force", "origin", "HEAD:refs/heads/main")


def commit_on_origin_only(repo: Path, text: str, message: str = "on main",
                          path: str = "results/decisions.md") -> None:
    """Change `path` (default results/decisions.md) on origin/main from a second clone,
    leaving `repo`'s HEAD and working tree alone (a change merged elsewhere)."""
    other = repo.parent / f"{repo.name}-other"
    if not other.exists():
        subprocess.run(["git", "clone", "-q", str(bare_origin(repo)), str(other)], check=True,
                       capture_output=True, env=_env(repo))
    git_in(other, "fetch", "-q", "origin")
    git_in(other, "checkout", "-q", "-B", "main", "origin/main")
    target = other / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    git_in(other, "add", path)
    git_in(other, "commit", "-q", "-m", message)
    git_in(other, "push", "-q", "origin", "HEAD:refs/heads/main")


def guarded_repo(path: Path, *, prereg: str = "Version: 0.1\n",
                 decisions: str | None = None, push: bool = True) -> Path:
    """`path` as a git repo whose HEAD holds PREREG.md and results/decisions.md (default:
    approving block '1-pilots'), with a local bare `origin` whose main equals HEAD."""
    git_in(path, "init", "-q")
    (path / "PREREG.md").write_text(prereg, encoding="utf-8")
    write_decisions(path, decisions_text("1-pilots") if decisions is None else decisions)
    git_in(path, "add", "PREREG.md", "results/decisions.md")
    git_in(path, "commit", "-q", "-m", "prereg")
    add_origin(path)
    if push:
        push_main(path)
    return path
