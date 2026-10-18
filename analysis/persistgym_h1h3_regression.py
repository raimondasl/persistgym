"""luna's cited H1/H3 output, re-derived by the current analysis code (PREREG §17.8, amendment
R8: "Run on luna's sweep, the extended code must reproduce every number and label of luna's
cited output, `results/persistgym_h1h3/20261010T232227Z/`").

Run: ``uv run python -m analysis.persistgym_h1h3_regression [--results-root DIR]
[--raw-root DIR] [--out-dir DIR] [--compare DIR]`` ($0: it reads files only and makes no API
call). It re-runs `analysis.persistgym_h1h3` on luna's sweep with the inputs the cited output's
meta.json records (its ``--run`` input list, its ``--rerun`` links and its ``--sweep-closed``
entry) and every other option at its registered default, writing that output to
``<out>/rerun/``; it then compares the output with the cited one and writes
``<out>/regression.json`` and ``<out>/meta.json`` (default out:
``results/persistgym_h1h3_regression/<UTC>/`` of this checkout). Exit 0 when nothing differs,
1 when something does (each difference is listed), 2 when the analysis refuses or stops.
``--compare DIR`` only compares an existing output folder with the cited one, and writes
nothing.

**Inputs.** The results root and the raw root default to the ones the cited output records
(``inputs.results_root``, ``inputs.raw_root``). luna's raw transcripts are gitignored, so the
re-run needs the checkout that holds them, and its §2.8 replay reads about 2 GB of them; with
the Bayesian fit, it takes tens of minutes.

**What is compared** (`compare`): h1h3.json, meta.json and summary.md, value by value (JSON
values, so numbers bit for bit, and key order). Ignored, because they record the run itself
(`IGNORED`): h1h3.json's ``generated_utc``, ``git_commit`` and ``git_dirty``; meta.json's
``run_id``, ``started_utc``, ``finished_utc``, ``git_commit``, ``git_dirty`` and
``sdk_versions`` (reported with the result: the second model's code added ``anthropic`` to
the list); and the time, commit and dirty flag of summary.md's "Computed" line. The input paths
(`PATH_KEYS` in both JSON files, and the "from `...`" of the "Computed" line) are compared as
the files they name, a relative one resolved against this checkout: the cited output was
computed from another checkout than the one holding the data, so the same folder may be
spelled differently. meta.json's ``config_hash``, the digest of its ``config``, is compared as
the digest of the config with those paths resolved, after each file's own hash is checked
against its own config.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from analysis import persistgym_h1h3 as hh
from common import runmeta

REPO_ROOT = runmeta.REPO_ROOT
CITED = REPO_ROOT / hh.LUNA_CITED_OUTPUT
OUT_NAME = "persistgym_h1h3_regression"
FILES = ("h1h3.json", "meta.json", "summary.md")
IGNORED = {"h1h3.json": ("generated_utc", "git_commit", "git_dirty"),
           "meta.json": ("run_id", "started_utc", "finished_utc", "git_commit", "git_dirty",
                         "sdk_versions")}
"""The fields that record the run itself, not its result (module docstring)."""
PATH_KEYS = ("results_root", "raw_root", "draw_json")
COMPUTED = re.compile(r"^Computed \S+ at commit [0-9a-f]{7} \(dirty: (?:True|False)\) by "
                      r"(?P<command>.*?), from `(?P<root>[^`]*)`")


def _abs(p: str | Path, root: Path = REPO_ROOT) -> Path:
    """The folder or file a recorded path names: a relative one resolved against `root`."""
    q = Path(p)
    return (q if q.is_absolute() else root / q).resolve()


def _path(p: str, root: Path = REPO_ROOT) -> str:
    """`_abs`, as a string compared case-insensitively where the file system is (Windows)."""
    return os.path.normcase(str(_abs(p, root)))


def _paths_resolved(o, root: Path = REPO_ROOT):
    """`o` with every `PATH_KEYS` string resolved (`_path`), keys in their order."""
    if isinstance(o, dict):
        return {k: (_path(v, root) if k in PATH_KEYS and isinstance(v, str)
                    else _paths_resolved(v, root)) for k, v in o.items()}
    if isinstance(o, list):
        return [_paths_resolved(v, root) for v in o]
    return o


def _walk(a, b, where: str, out: list[str]) -> None:
    """Every difference between `a` (cited) and `b` (re-run): types, key order, lengths and
    values, as JSON values."""
    if type(a) is not type(b):
        out.append(f"{where}: type {type(a).__name__} vs {type(b).__name__}: {a!r} vs {b!r}")
        return
    if isinstance(a, dict):
        if list(a) != list(b):
            out.append(f"{where}: keys differ (only cited: {sorted(set(a) - set(b))}; only "
                       f"re-run: {sorted(set(b) - set(a))}; same set, other order: "
                       f"{set(a) == set(b)})")
        for k in a:
            if k in b:
                _walk(a[k], b[k], f"{where}.{k}", out)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{where}: length {len(a)} vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b, strict=False)):
            _walk(x, y, f"{where}[{i}]", out)
    elif a != b:
        out.append(f"{where}: {a!r} vs {b!r}")


def compare_json(cited: dict, new: dict, name: str,
                 root: Path = REPO_ROOT) -> tuple[list[str], dict]:
    """The differences between two outputs' `name` (h1h3.json or meta.json), and the ignored
    fields' values (cited, re-run)."""
    ignored = {k: [cited.get(k), new.get(k)] for k in IGNORED[name]}
    out = []
    sides = []
    for label, d in (("cited", cited), ("re-run", new)):
        d = {k: v for k, v in d.items() if k not in IGNORED[name]}
        if name == "meta.json" and "config" in d:
            if d.get("config_hash") != runmeta.config_hash(d["config"]):
                out.append(f"meta.json.config_hash: the {label} hash is not the digest of its "
                           "own config")
            d["config_hash"] = runmeta.config_hash(_paths_resolved(d["config"], root))
        sides.append(_paths_resolved(d, root))
    _walk(*sides, name, out)
    return out, ignored


def _computed_line(line: str, root: Path = REPO_ROOT) -> str:
    m = COMPUTED.match(line)
    if not m:
        return line
    return (f"Computed <ignored> by {m['command']}, from `{_path(m['root'], root)}`"
            + line[m.end():])


def compare_summary(cited: str, new: str, root: Path = REPO_ROOT) -> list[str]:
    """The differences between two summary.md texts, line by line (`_computed_line`)."""
    a = [_computed_line(x, root) for x in cited.splitlines()]
    b = [_computed_line(x, root) for x in new.splitlines()]
    out = [f"summary.md line {i + 1}: {x!r} vs {y!r}"
           for i, (x, y) in enumerate(zip(a, b, strict=False)) if x != y]
    if len(a) != len(b):
        out.append(f"summary.md: {len(a)} vs {len(b)} lines")
    return out


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(cited_dir: Path, new_dir: Path, root: Path = REPO_ROOT) -> dict:
    """The cited output folder against a re-run's (module docstring)."""
    missing = [f for f in FILES if not (new_dir / f).is_file()]
    if missing:
        return {"differences": [f"{new_dir}: no {f}" for f in missing], "per_file": {},
                "ignored": {}}
    per_file, ignored, diffs = {}, {}, []
    for name in ("h1h3.json", "meta.json"):
        d, ign = compare_json(json.loads((cited_dir / name).read_text(encoding="utf-8")),
                              json.loads((new_dir / name).read_text(encoding="utf-8")),
                              name, root)
        per_file[name], ignored[name] = len(d), ign
        diffs += d
    d = compare_summary((cited_dir / "summary.md").read_text(encoding="utf-8"),
                        (new_dir / "summary.md").read_text(encoding="utf-8"), root)
    per_file["summary.md"] = len(d)
    diffs += d
    return {"differences": diffs, "per_file": per_file, "ignored": ignored,
            "sha256": {"cited": {f: _sha256(cited_dir / f) for f in FILES},
                       "re-run": {f: _sha256(new_dir / f) for f in FILES}}}


def rerun_args(cited_meta: dict, results_root: Path, raw_root: Path, out: Path) -> list[str]:
    """`analysis.persistgym_h1h3`'s arguments for a re-run with the cited output's inputs."""
    cfg = cited_meta["config"]
    args = ["--results-root", str(results_root), "--raw-root", str(raw_root),
            "--out-dir", str(out)]
    if cfg.get("sweep_closed") is not None:
        args += ["--sweep-closed", cfg["sweep_closed"]]
    for run in cfg["inputs"]["input_list"]:
        args += ["--run", run]
    for run, orig in (cfg.get("rerun_links") or {}).items():
        args += ["--rerun", f"{run}={orig}"]
    return args


def report_lines(res: dict) -> list[str]:
    if not res.get("per_file"):
        return ["Not compared: " + "; ".join(res["differences"])]
    lines = [f"{name}: {n} difference(s)" for name, n in res["per_file"].items()]
    meta_ign = res["ignored"].get("meta.json", {})
    if "sdk_versions" in meta_ign:
        lines.append(f"sdk_versions (ignored), cited / re-run: {meta_ign['sdk_versions'][0]} / "
                     f"{meta_ign['sdk_versions'][1]}")
    lines += [f"  {x}" for x in res["differences"]]
    lines.append("REPRODUCED: every number and label of the cited output"
                 if not res["differences"] else
                 f"DIFFERS: {len(res['differences'])} difference(s) from the cited output")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--results-root", type=Path, default=None,
                    help="the results folder holding luna's sweep (default: the cited "
                         "output's inputs.results_root)")
    ap.add_argument("--raw-root", type=Path, default=None,
                    help="where luna's raw transcripts are (default: the cited output's "
                         "inputs.raw_root)")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help=f"default: results/{OUT_NAME}/<UTC>/ of this checkout")
    ap.add_argument("--compare", type=Path, default=None, metavar="DIR",
                    help="only compare an existing output folder with the cited one")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.compare is not None:
        res = compare(CITED, a.compare)
        print("\n".join(report_lines(res)))
        return 1 if res["differences"] else 0
    cited_meta = json.loads((CITED / "meta.json").read_text(encoding="utf-8"))
    recorded = cited_meta["config"]["inputs"]
    root = _abs(a.results_root or recorded["results_root"])
    raw = _abs(a.raw_root or recorded["raw_root"])
    started = datetime.now(UTC)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    out = a.out_dir or REPO_ROOT / "results" / OUT_NAME / run_id
    git = runmeta.git_state()
    args = rerun_args(cited_meta, root, raw, out / "rerun")
    code = hh.main(args)
    if code != 0:
        print(f"the re-run did not complete (exit {code}): nothing compared", file=sys.stderr)
        return 2
    res = compare(CITED, out / "rerun")
    (out / "regression.json").write_text(json.dumps(
        {"cited": hh.LUNA_CITED_OUTPUT, "rerun": "rerun/", "reproduced": not res["differences"],
         **res}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    runmeta.write_meta(
        out, git=git, experiment=OUT_NAME, run_id=run_id, cell_or_config="luna-cited-output",
        config={"cited": hh.LUNA_CITED_OUTPUT, "rerun_args": args,
                "ignored": {k: list(v) for k, v in IGNORED.items()},
                "path_keys": list(PATH_KEYS)},
        model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
        repeat_index=None, seeds=None, started_utc=started.isoformat(timespec="seconds"),
        finished_utc=runmeta.utc_now(),
        exit_reason="reproduced" if not res["differences"] else "differs", tokens=None,
        cost_usd=0.0, raw_transcript_path=None, outputs=["regression.json", "rerun/"],
        paid_calls=0)
    print("\n".join(report_lines(res)))
    print(f"written: {out}")
    return 1 if res["differences"] else 0


if __name__ == "__main__":
    sys.exit(main())
