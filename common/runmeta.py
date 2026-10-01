"""Per-run metadata: results/<experiment>/<run_id>/meta.json (CLAUDE.md "Results are files with metadata")."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
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

SDKS = ["openai", "google-genai", "arc-agi", "tiktoken"]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def git_state(repo: Path = REPO_ROOT) -> dict:
    def run(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                              check=True).stdout.strip()
    return {"git_commit": run("rev-parse", "HEAD"),
            "git_dirty": bool(run("status", "--porcelain", "--untracked-files=no"))}


def prereg_version(repo: Path = REPO_ROOT) -> str | None:
    """Version string from a 'Version: x' line in PREREG.md, or None before it exists."""
    p = repo / "PREREG.md"
    if not p.exists():
        return None
    m = re.search(r"^\**Version:?\**:?\s*(\S+)", p.read_text(encoding="utf-8"), re.MULTILINE)
    return m.group(1) if m else "unversioned"


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


def build_meta(**fields) -> dict:
    missing = [k for k in REQUIRED if k not in fields]
    if missing:
        raise ValueError(f"meta.json missing required fields: {missing}")
    return {
        **fields,
        "config_hash": config_hash(fields["config"]),
        "prereg_version": prereg_version(),
        "sdk_versions": sdk_versions(),
        **git_state(),
    }


def write_meta(run_dir: Path, **fields) -> Path:
    meta = build_meta(**fields)
    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / "meta.json"
    out.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
