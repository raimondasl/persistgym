"""Per-run metadata: results/<experiment>/<run_id>/meta.json (CLAUDE.md "Results are files with metadata").

**The git state of a paid run is read once, at its start.** A paid launcher reads it
(`git_state`) before its first paid call and passes that value to everything it writes after
the calls: the costs.csv row and meta.json (`write_meta(..., git=...)`). So no process has to
be started between a run's first paid call and its costs row. On 2026-10-02 a run's costs
row could not be written because `git rev-parse HEAD`, run after the calls, failed to start
(exit 0xC0000142: the run's process had lost its console). The commit recorded is still the
commit of the code that made the calls.

On Windows git is started with `CREATE_NO_WINDOW`, so that a process without a console can
still run it. If git fails anyway, `git_state` raises (`subprocess.CalledProcessError`, or the
OSError of a git that cannot be started): it never records a guess.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Fields every meta.json must carry. Values may be None when they do not apply
# (e.g. reasoning.context for Gemini), but the key must be present.
REQUIRED = [
    "experiment", "run_id", "cell_or_config", "config", "model_requested", "model_returned",
    "reasoning_effort", "reasoning_context_requested", "reasoning_context_echoed",
    "template_id", "repeat_index", "seeds", "started_utc", "finished_utc", "exit_reason",
    "tokens", "cost_usd", "raw_transcript_path",
]

SDKS = ["openai", "anthropic", "google-genai", "arc-agi", "tiktoken"]
GIT_KEYS = ("git_commit", "git_dirty")
# subprocess.CREATE_NO_WINDOW, which exists only on Windows
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def run_git(*args: str, repo: Path = REPO_ROOT) -> str:
    """The stripped standard output of `git <args>` in `repo`. Raises CalledProcessError if
    git fails, OSError if it cannot be started. On Windows git starts without a console
    window (`CREATE_NO_WINDOW`), so that it also starts from a process that has lost its
    console; and with its standard input closed (`DEVNULL`), so that it never inherits a
    console handle of the caller's that is no longer valid."""
    flags = CREATE_NO_WINDOW if sys.platform == "win32" else 0
    return subprocess.run(["git", *args], cwd=repo, stdin=subprocess.DEVNULL,
                          capture_output=True, encoding="utf-8", errors="replace", check=True,
                          creationflags=flags).stdout.strip()


def git_state(repo: Path = REPO_ROOT) -> dict:
    """The commit checked out in `repo` and whether tracked files differ from it. A paid
    run reads it once, before its first paid call (module docstring)."""
    return {"git_commit": run_git("rev-parse", "HEAD", repo=repo),
            "git_dirty": bool(run_git("status", "--porcelain", "--untracked-files=no",
                                      repo=repo))}


def check_git_state(state) -> dict:
    """`state` if it is a git state as `git_state` returns it (exactly its two keys, a
    full commit id and a bool), else ValueError."""
    if (not isinstance(state, dict) or tuple(sorted(state)) != tuple(sorted(GIT_KEYS))
            or not isinstance(state["git_commit"], str)
            or not re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", state["git_commit"])
            or not isinstance(state["git_dirty"], bool)):
        raise ValueError(f"not a git state ({', '.join(GIT_KEYS)}: a full commit id and a "
                         f"bool): {state!r}")
    return state


def prereg_version_in(text: str) -> str:
    """The version string of a 'Version: x' line in PREREG.md's text, or "unversioned"."""
    m = re.search(r"^\**Version:?\**:?\s*(\S+)", text, re.MULTILINE)
    return m.group(1) if m else "unversioned"


def prereg_version(repo: Path = REPO_ROOT) -> str | None:
    """Version string from a 'Version: x' line in PREREG.md, or None before it exists."""
    p = repo / "PREREG.md"
    if not p.exists():
        return None
    return prereg_version_in(p.read_text(encoding="utf-8"))


def config_hash(config: dict) -> str:
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sdk_versions() -> dict:
    out = {}
    for name in SDKS:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


def build_meta(*, git: dict | None = None, **fields) -> dict:
    """meta.json's content: `fields`, the config hash, the PREREG and SDK versions, and the
    git state. `git`: the git state the run read at its start (a paid run passes it, so that
    no git process runs after its calls); None reads it now. `prereg_version` and
    `sdk_versions` may be given in `fields` (`harnesses account-run` passes the run's own);
    otherwise they are read now."""
    missing = [k for k in REQUIRED if k not in fields]
    if missing:
        raise ValueError(f"meta.json missing required fields: {missing}")
    prereg = fields.pop("prereg_version") if "prereg_version" in fields else prereg_version()
    sdks = fields.pop("sdk_versions") if "sdk_versions" in fields else sdk_versions()
    return {
        **fields,
        "config_hash": config_hash(fields["config"]),
        "prereg_version": prereg,
        "sdk_versions": sdks,
        **(git_state() if git is None else check_git_state(dict(git))),
    }


def write_meta(run_dir: Path, *, git: dict | None = None, **fields) -> Path:
    """Write run_dir/meta.json (`build_meta`; `git` as there)."""
    meta = build_meta(git=git, **fields)
    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / "meta.json"
    out.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return out
