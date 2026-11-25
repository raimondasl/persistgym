"""Throwaway git repositories for the paid-guard tests (common/approval.py), shared with the
harness tests. Each test repo gets a local bare repository as its `origin`, so the guard's
`git fetch origin main` never leaves the machine (the test fixtures also set
GIT_ALLOW_PROTOCOL=file, so git refuses any network transport).

`guarded_repo` builds each distinct repo (PREREG.md, decisions.md, pushed or not) once per
test process, as a template, and copies it for every call (`copied_repo`, which other test
helpers use too): a copy holds the same files, commits and bare origin as a repo built in
place, with the origin URL pointing at its own bare copy. Building one takes about seven git
processes, which cost 4-6 s per test on a loaded Windows machine (2026-11-25); a copy takes
none. common/tests/test_gitrepo.py checks that a copy equals a repo built in place."""

from __future__ import annotations

import atexit
import os
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from common.approval import format_line

# Experiments the default test approval covers, and a max_usd above every phase cap test.
DEFAULT_EXPERIMENTS = ("toggle_pilot", "replay_probe", "persistgym_pilot")
DEFAULT_MAX_USD = "1000"

# PREREG.md texts in the form of PREREG §0.4: a frozen one, which `require_paid_run` accepts
# (common/prereg.py), and a draft, which it refuses even when merged.
FROZEN_PREREG = "Version: 1.0\n\n**Status: Frozen on 2026-10-03 by the researcher.**\n"
DRAFT_PREREG = "Version: 0.3-draft\n\n**Status: DRAFT for the researcher's sign-off.**\n"


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


def build_guarded_repo(path: Path, *, prereg: str, decisions: str, push: bool) -> Path:
    """`guarded_repo` built in place with git (the templates are built this way)."""
    git_in(path, "init", "-q")
    (path / "PREREG.md").write_text(prereg, encoding="utf-8")
    write_decisions(path, decisions)
    git_in(path, "add", "PREREG.md", "results/decisions.md")
    git_in(path, "commit", "-q", "-m", "prereg")
    add_origin(path)
    if push:
        push_main(path)
    return path


# This process's templates, by key (`copied_repo`), under one temporary folder that is removed
# when the process ends.
_TEMPLATES: dict[tuple, Path] = {}
_TEMPLATE_ROOT: list[Path] = []


def _writable_then_retry(function, path, _exc) -> None:
    os.chmod(path, stat.S_IWRITE)   # git writes its object files read-only
    function(path)


def _template(key: tuple, build: Callable[[Path], object]) -> Path:
    if key not in _TEMPLATES:
        if not _TEMPLATE_ROOT:
            _TEMPLATE_ROOT.append(Path(tempfile.mkdtemp(prefix="persistgym-gitrepo-")))
            atexit.register(shutil.rmtree, _TEMPLATE_ROOT[0], onexc=_writable_then_retry)
        # a folder of its own: `build` may itself copy a template (nested `copied_repo`)
        repo = Path(tempfile.mkdtemp(dir=_TEMPLATE_ROOT[0])) / "repo"
        repo.mkdir()
        build(repo)
        _TEMPLATES[key] = repo
    return _TEMPLATES[key]


def _config_value(path: Path) -> str:
    """`path` as git writes it into a config value (backslashes and quotes escaped)."""
    return str(path).replace("\\", "\\\\").replace('"', '\\"')


def copied_repo(path: Path, key: tuple, build: Callable[[Path], object]) -> Path:
    """`path` as a copy of this process's template for `key`, which `build(template)` makes
    the first time it is asked for: a git repo in `template` with its local bare origin at
    `bare_origin(template)`. The copy's origin is its own copy of that bare repo,
    `bare_origin(path)`. `key` must name everything `build` depends on."""
    template = _template(key, build)
    path.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template, path, dirs_exist_ok=True)
    shutil.copytree(bare_origin(template), bare_origin(path))
    config = path / ".git" / "config"
    old = f"\turl = {_config_value(bare_origin(template))}\n".encode()
    text = config.read_bytes()
    if text.count(old) == 1:
        config.write_bytes(text.replace(
            old, f"\turl = {_config_value(bare_origin(path))}\n".encode()))
    else:
        git_in(path, "remote", "set-url", "origin", str(bare_origin(path)))
    (path.parent / ".test-gitconfig").touch()   # as git_in leaves it for a repo built in place
    return path


def guarded_repo(path: Path, *, prereg: str = "Version: 0.1\n",
                 decisions: str | None = None, push: bool = True) -> Path:
    """`path` as a git repo whose HEAD holds PREREG.md and results/decisions.md (default:
    approving block '1-pilots'), with a local bare `origin` whose main equals HEAD (unless
    `push` is False: then origin has no branch). A copy of this process's template for these
    arguments (`copied_repo`)."""
    decisions = decisions_text("1-pilots") if decisions is None else decisions
    return copied_repo(path, ("guarded_repo", prereg, decisions, push),
                       lambda t: build_guarded_repo(t, prereg=prereg, decisions=decisions,
                                                    push=push))
