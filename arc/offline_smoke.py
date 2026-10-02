"""$0 end-to-end runs of the patched ARC harness on local games with a stub model.

Run from the repository root:

    uv run arc/offline_smoke.py --toy
    uv run arc/offline_smoke.py --games ft09 --environments-dir results/raw/arc_games

``--toy`` plays the two-level toy game in arc/toy_game (written for this repo;
not an ARC game) and needs nothing else. ARC's public games need their files
(``metadata.json`` plus the game class) under ``--environments-dir``.
Downloading ARC game sources and executing them needs the researcher's
approval first (arc/README.md); this script never downloads anything and
stops when a game is missing.

For each path config (S0, S1, S2, S4) and game the script builds the patched
harness in a scratch worktree (arc/.work/offline-smoke), then runs
offline_smoke_inner.py there with OPERATION_MODE=offline, a sanitized
environment and a stub model behind a loopback-only socket guard. It then
checks every captured request and run_meta.json against the config's
expected behaviour, writes summary.json and prints one line per run.
No model provider or ARC API is called and no key is read.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arc import apply_patches as ap

PATH_CONFIGS = {
    "S0": "google-gemini-3-8-flash-high",
    "S1": "google-gemini-3-8-flash-high-rolling-summary",
    "S2": "google-gemini-3-8-flash-high-rolling-summary-notes-off",
    "S4": "google-gemini-3-8-flash-high-provider-adapter",
}
EXPECTED = {
    # notes sentence, thought replay, harness summaries
    "S0": {"notes": True, "thoughts": False, "summaries": False},
    "S1": {"notes": True, "thoughts": False, "summaries": True},
    "S2": {"notes": False, "thoughts": False, "summaries": True},
    "S4": {"notes": False, "thoughts": True, "summaries": True},
}
NOTES_SENTENCE = "Include any context you want to carry forward in your reply"
BRIDGE_PREFIX = "Earlier conversation history was compacted."
SUMMARY_SYSTEM_PROMPT = (
    "You create concise conversation summaries for reliable continuation. "
    "Return only the requested summary."
)
SUMMARY_TRIGGER_TOKENS = 175_000
SUMMARY_MAX_OUTPUT_TOKENS = 8_192
# Patch 0017 (D21): every request of every path config asks for the standard tier.
SERVICE_TIER = "standard"
TOY_DIR = ap.ARC_DIR / "toy_game"
TOY_GAME = "toyg"
# Toy run: two moves, a lost life (forced RESET), then six moves to the win.
# Turn 2 reports usage above the summary trigger, so S1, S2 and S4 compact
# right after the GAME_OVER frame is buffered.
TOY_SCRIPT = "ACTION1,ACTION2," + ",".join(["ACTION1"] * 6)
TOY_TRIGGER_TURNS = "2"
WORKTREE_NAME = "offline-smoke"
DEFAULT_OUT = ap.REPO_ROOT / "results" / "raw" / "arc_offline_smoke"
DEFAULT_ENVIRONMENTS = ap.REPO_ROOT / "results" / "raw" / "arc_games"
INNER = ap.ARC_DIR / "offline_smoke_inner.py"
ENDINGS = frozenset({"GAME_WIN", "ACTION_BUDGET"})


# ── Games ──────────────────────────────────────────────────────────────


def local_games(environments_dir: Path) -> dict[str, str]:
    """Map base game ID (e.g. 'ft09') to full ID for every metadata.json."""
    games: dict[str, str] = {}
    if not environments_dir.is_dir():
        return games
    for metadata in sorted(environments_dir.rglob("metadata.json")):
        try:
            game_id = str(json.loads(metadata.read_text(encoding="utf-8"))["game_id"])
        except (OSError, ValueError, KeyError):
            continue
        games.setdefault(game_id.split("-", 1)[0], game_id)
    return games


def missing_games(environments_dir: Path, games: Sequence[str]) -> list[str]:
    available = local_games(environments_dir)
    return [game for game in games if game.split("-", 1)[0] not in available]


def stage_toy_game(environments_dir: Path) -> None:
    target = environments_dir / TOY_GAME / "v1"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("metadata.json", "toyg.py"):
        shutil.copyfile(TOY_DIR / name, target / name)


# ── Inner runs ─────────────────────────────────────────────────────────


def inner_env(
    *, worktree: Path, environments_dir: Path, scratch_dir: Path, harness_commit: str
) -> dict[str, str]:
    """Sanitized environment for one inner run: no keys, offline mode only."""
    env = ap.sanitized_env()
    env.update(
        {
            "OPERATION_MODE": "offline",
            "ENVIRONMENTS_DIR": str(environments_dir),
            "RECORDINGS_DIR": str(scratch_dir / "arc_recordings"),
            "PYTHONPATH": os.pathsep.join([str(worktree), str(ap.ARC_DIR)]),
            "ARC_HARNESS_COMMIT_SHA": harness_commit,
            "PYTHONUTF8": "1",
        }
    )
    return env


def inner_command(
    *,
    worktree: Path,
    config_id: str,
    game: str,
    out_dir: Path,
    usage: str,
    trigger_turns: str,
    script: str,
    seed: int,
) -> list[str]:
    command = [
        "uv", "run", "--no-sync", "--project", str(worktree), "python", str(INNER),
        "--config", config_id, "--game", game, "--out", str(out_dir),
        "--usage", usage, "--seed", str(seed),
    ]  # fmt: skip
    if trigger_turns:
        command += ["--trigger-turns", trigger_turns]
    if script:
        command += ["--script", script]
    return command


# ── Checks ─────────────────────────────────────────────────────────────


def _is_summary(body: dict[str, Any]) -> bool:
    return body.get("system_instruction") == SUMMARY_SYSTEM_PROMPT


def _first_text(body: dict[str, Any]) -> str:
    items = body.get("input") or [{}]
    parts = items[0].get("content") or [{}]
    return str(parts[0].get("text", ""))


def check_run(label: str, result: dict[str, Any], bodies: list[dict[str, Any]]) -> list[str]:
    """Problems with one run, compared with what its path config must do."""
    expected = EXPECTED[label]
    meta = result.get("run_meta", {})
    problems: list[str] = []
    if meta.get("exit_reason") not in ENDINGS:
        problems.append(f"exit_reason {meta.get('exit_reason')!r}")
    if meta.get("agent_exit_reason") != meta.get("exit_reason"):
        problems.append(
            f"agent_exit_reason {meta.get('agent_exit_reason')!r} != exit_reason"
        )
    if not meta.get("reported_models"):
        problems.append("run_meta has no reported_models")
    if meta.get("arc_environment") != {"kind": "local"}:
        problems.append(f"arc_environment {meta.get('arc_environment')!r}")
    actions = [body for body in bodies if not _is_summary(body)]
    summaries = [body for body in bodies if _is_summary(body)]
    if not actions or len(actions) != result.get("steps", -1) - _forced_steps(result):
        problems.append(f"{len(actions)} action requests for {result.get('steps')} steps")
    for index, body in enumerate(actions, start=1):
        if (NOTES_SENTENCE in body.get("system_instruction", "")) is not expected["notes"]:
            problems.append(f"request {index}: notes sentence presence is wrong")
        config = body.get("generation_config", {})
        if config.get("thinking_level") != "high":
            problems.append(f"request {index}: thinking_level {config.get('thinking_level')!r}")
    for index, body in enumerate(bodies, start=1):
        if body.get("service_tier") != SERVICE_TIER:
            kind = "summary request" if _is_summary(body) else "request"
            problems.append(f"{kind} body {index}: service_tier {body.get('service_tier')!r}, "
                            f"expected {SERVICE_TIER!r}")
    replayed = any(
        item.get("type") == "thought" for body in actions for item in body.get("input", [])
    )
    if replayed is not expected["thoughts"]:
        problems.append(f"thought replay {replayed}, expected {expected['thoughts']}")

    totals = result.get("reported_totals", [])
    triggered = any(total >= SUMMARY_TRIGGER_TOKENS for total in totals[:-1])
    runtime = meta.get("runtime") or {}
    if not expected["summaries"]:
        if summaries:
            problems.append(f"{len(summaries)} summary requests in a config without them")
    else:
        if triggered and not summaries:
            problems.append("usage reached the trigger but no summary request was sent")
        if runtime.get("compaction_count", 0) != len(summaries):
            problems.append(
                f"compaction_count {runtime.get('compaction_count')} != "
                f"{len(summaries)} summary requests"
            )
        for body in summaries:
            cap = body.get("generation_config", {}).get("max_output_tokens")
            if cap != SUMMARY_MAX_OUTPUT_TOKENS:
                problems.append(f"summary max_output_tokens {cap}")
        position = 0
        for body in bodies:
            if _is_summary(body):
                position = 1
                continue
            if position == 1 and not _first_text(body).startswith(BRIDGE_PREFIX):
                problems.append("request after a summary does not start with the bridge")
            position = 0
    if label in {"S1", "S2"}:
        if runtime.get("context_trims") != 0:
            problems.append(f"context_trims {runtime.get('context_trims')!r}")
        problems += _dropped_turn_problems(bodies)
    return problems


def _dropped_turn_problems(bodies: list[dict[str, Any]]) -> list[str]:
    """S1/S2 (patch 0016) lose history only by summarizing, never by dropping turns.

    Every action request starts with the first observation or a summary bridge,
    and until the next summary each one resends the previous action request in
    full and adds to it. Comparing first texts alone would miss a dropped pair
    whose next observation reads the same as the first, as after a no-op move.
    check_run separately requires one action request per step, so an action
    request never repeats the one before it.
    """
    actions = [body for body in bodies if not _is_summary(body)]
    first = _first_text(actions[0]) if actions else ""
    previous: list[Any] | None = None
    index = 0
    for body in bodies:
        if _is_summary(body):
            previous = None
            continue
        index += 1
        items = list(body.get("input") or [])
        text = _first_text(body)
        dropped = text != first and not text.startswith(BRIDGE_PREFIX)
        if previous is not None and (
            len(items) <= len(previous) or items[: len(previous)] != previous
        ):
            dropped = True
        if dropped:
            return [f"request {index}: oldest turn dropped"]
        previous = items
    return []


def _forced_steps(result: dict[str, Any]) -> int:
    """Steps without a model request (forced RESET after a lost life)."""
    return int(result.get("forced_steps", 0))


def count_forced_steps(run_dir: Path) -> int:
    count = 0
    for path in run_dir.glob("step_*.json"):
        step = json.loads(path.read_text())
        if step.get("parsed_action") == "RESET" and not step.get("assistant_response"):
            count += 1
    return count


# ── Main ───────────────────────────────────────────────────────────────


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--toy", action="store_true", help="play arc/toy_game")
    source.add_argument("--games", help="comma-separated ARC game IDs, e.g. ft09,sb26")
    parser.add_argument("--environments-dir", type=Path, default=DEFAULT_ENVIRONMENTS)
    parser.add_argument("--configs", default="S0,S1,S2,S4")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--usage",
        choices=["fixed", "chars"],
        default=None,
        help="stub usage: fixed (toy default) or one token per character (games default)",
    )
    parser.add_argument("--trigger-turns", default=None, help="turns reporting 180k tokens")
    parser.add_argument(
        "--script",
        default=None,
        help="comma-separated stub actions (toy default: two moves, a lost life, six moves)",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--keep", action="store_true", help="keep the scratch worktree")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    labels = [label.strip() for label in args.configs.split(",") if label.strip()]
    unknown = [label for label in labels if label not in PATH_CONFIGS]
    if unknown or not labels:
        print(f"Unknown configs {unknown}; use {', '.join(PATH_CONFIGS)}.", file=sys.stderr)
        return 2
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_root = (args.out or DEFAULT_OUT / stamp).resolve()

    if args.toy:
        environments_dir = out_root / "environment_files"
        stage_toy_game(environments_dir)
        games = [TOY_GAME]
        usage = args.usage or "fixed"
        if args.trigger_turns is not None:
            trigger_turns = args.trigger_turns
        else:
            trigger_turns = TOY_TRIGGER_TURNS if usage == "fixed" else ""
        script = TOY_SCRIPT if args.script is None else args.script
    else:
        environments_dir = args.environments_dir.resolve()
        games = [game.strip() for game in args.games.split(",") if game.strip()]
        missing = missing_games(environments_dir, games)
        if missing:
            print(
                f"Game files for {', '.join(missing)} are not under {environments_dir}.\n"
                "Downloading and running ARC game sources needs the researcher's "
                "approval first; see arc/README.md (Offline smoke runs). "
                "Nothing was downloaded.",
                file=sys.stderr,
            )
            return 2
        usage = args.usage or "chars"
        trigger_turns = args.trigger_turns or ""
        script = args.script or ""

    env = ap.sanitized_env()
    worktree = ap.WORK_DIR / WORKTREE_NAME
    rows: list[dict[str, Any]] = []
    try:
        ap.check_pin(env)
        patches = ap.patch_files()
        ap.create_worktree(worktree, env)
        ap.apply_series(worktree, patches, env)
        harness_commit = ap._git(["rev-parse", "HEAD"], worktree, env)
        ap.sync_environment(worktree, env)
        for label in labels:
            for game in games:
                run_dir = out_root / f"{label}-{game}"
                run_dir.mkdir(parents=True, exist_ok=True)
                command = inner_command(
                    worktree=worktree,
                    config_id=PATH_CONFIGS[label],
                    game=game,
                    out_dir=run_dir,
                    usage=usage,
                    trigger_turns=trigger_turns,
                    script=script,
                    seed=args.seed,
                )
                # Short working directory: the harness writes
                # recordings/<long agent name>/ relative to it (Windows MAX_PATH).
                with tempfile.TemporaryDirectory(
                    prefix="arcsmoke-", ignore_cleanup_errors=True
                ) as scratch:
                    run_env = inner_env(
                        worktree=worktree,
                        environments_dir=environments_dir,
                        scratch_dir=Path(scratch),
                        harness_commit=harness_commit,
                    )
                    completed = ap._run(command, Path(scratch), run_env, capture=True)
                (run_dir / "inner.log").write_text(
                    completed.stdout + completed.stderr, encoding="utf-8"
                )
                rows.append(_collect(label, game, run_dir, completed.returncode))
    except ap.PatchError as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        return 1
    finally:
        if not args.keep:
            try:
                ap.remove_worktree(worktree, env)
            except ap.PatchError as error:
                print(f"warning: could not remove {worktree}: {error}", file=sys.stderr)

    summary = {
        "created_utc": stamp,
        "harness_commit": harness_commit,
        "patch_series_sha256": ap.series_digest(patches),
        "games": games,
        "usage": usage,
        "runs": rows,
    }
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nOffline smoke runs ({out_root})")
    for row in rows:
        status = "PASS" if not row["problems"] else "FAIL"
        print(
            f"  {status} {row['config']:<3} {row['game']:<6} {row['exit_reason']:<14} "
            f"steps={row['steps']:<4} summaries={row['summaries']} "
            + "; ".join(row["problems"])
        )
    return 0 if rows and all(not row["problems"] for row in rows) else 1


def _collect(label: str, game: str, run_dir: Path, returncode: int) -> dict[str, Any]:
    row: dict[str, Any] = {"config": label, "game": game, "run_dir": str(run_dir)}
    result_path = run_dir / "result.json"
    if returncode != 0 or not result_path.exists():
        row.update(exit_reason="NO_RESULT", steps=0, summaries=0)
        row["problems"] = [f"inner run exited {returncode}; see {run_dir / 'inner.log'}"]
        return row
    result = json.loads(result_path.read_text())
    bodies = json.loads((run_dir / "bodies.json").read_text())
    result["forced_steps"] = count_forced_steps(Path(result["run_dir"]))
    row.update(
        exit_reason=result["run_meta"].get("exit_reason"),
        steps=result["steps"],
        summaries=result["summaries"],
        problems=check_run(label, result, bodies),
    )
    return row


if __name__ == "__main__":
    raise SystemExit(main())
