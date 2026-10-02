"""Render PersistGym-lite templates to JSONL and run the $0 validity checks.

    uv run python -m persistgym render --n 20
    uv run python -m persistgym render --split validity --n 10 --single-turn --gzip
    uv run python -m persistgym render --n 50 --W 24000 --v 1500 --out results/raw/persistgym/x
    uv run python -m persistgym partial-memory --n 2000
    uv run python -m persistgym spotcheck            # G1 spot-check pages (persistgym/spotcheck.py)

Template counts and start indices come in whole balance blocks of K templates (PREREG D7);
`--partial-blocks` allows other counts for quick $0 checks. Splits: main [0, 50000),
validity [50000, 60000), pilot [90000, 100000) (seed = range start + index).

Writes into the output folder (default results/raw/persistgym/<split>-<start>-<n>-<hash8>,
gitignored): episodes.jsonl[.gz] (one Episode per line), single_turn.jsonl[.gz] (optional),
summary.json and manifest.json. No API calls; nothing here costs money.
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

from common.runmeta import REPO_ROOT, config_hash, git_state
from persistgym import spotcheck
from persistgym.config import GENERATOR_VERSION, SCHEMA_VERSION, SEED_RANGES, GeneratorConfig
from persistgym.controls import single_turn_control
from persistgym.episode import ALL_CELLS, VARIANTS, Episode
from persistgym.render import generate
from persistgym.template import sample_template
from persistgym.validity import (
    heuristic_baselines,
    lookup_audit,
    oracle_scores,
    partial_memory_diagnostic,
    partial_memory_from_episodes,
    shortcut_audit,
)

DEFAULT_OUT = REPO_ROOT / "results" / "raw" / "persistgym"


def _open(path: Path, gz: bool):
    return gzip.open(path, "wt", encoding="utf-8") if gz else path.open("w", encoding="utf-8")


def _rng(xs: list) -> list:
    return [min(xs), max(xs)] if xs else [None, None]


def cell_summary(episodes: list[Episode]) -> dict:
    by_cell: dict[str, list[Episode]] = defaultdict(list)
    for ep in episodes:
        if ep.variant == "base":
            by_cell[ep.cell.id].append(ep)
    out = {}
    for cid in [c.id for c in ALL_CELLS]:
        eps = by_cell.get(cid, [])
        if not eps:
            continue
        d = [e.design for e in eps]
        out[cid] = {
            "n": len(eps),
            "steps": _rng([e.n_steps for e in eps]),
            "need_step": _rng([e.need_step for e in eps]),
            "gap_steps_latest": _rng([x["gap_steps_latest"] for x in d]),
            "gap_steps_earliest": _rng([x["gap_steps_earliest"] for x in d]),
            "obs_tokens_latest_to_need": _rng([x["obs_tokens_latest_to_need"] for x in d]),
            "obs_tokens_per_observation": _rng([t for e in eps for t in e.obs_tokens]),
            "S_window_obs_only_rate": statistics.mean(bool(x["S_window_obs_only"]) for x in d),
            "S_window_assumed_replies_rate":
                statistics.mean(bool(x["S_window_assumed_replies"]) for x in d),
            "context_obs_tokens_at_need_max": max(x["context_obs_tokens_at_need"] for x in d),
            "context_tokens_at_need_assumed_replies_max":
                max(x["context_tokens_at_need_assumed_replies"] for x in d),
        }
    return out


def parse_overrides(items: list[str]) -> dict:
    """'key=value' pairs; values are parsed as JSON when possible (lists become tuples)."""
    out = {}
    for item in items:
        key, sep, raw = item.partition("=")
        if not sep:
            raise ValueError(f"--set expects key=value, got {item!r}")
        try:
            val = json.loads(raw)
        except json.JSONDecodeError:
            val = raw
        out[key.strip()] = tuple(val) if isinstance(val, list) else val
    return out


def whole_blocks_error(start: int, n: int, K: int) -> str | None:
    """PREREG D7: template counts come in whole balance blocks of K templates."""
    if start % K or n % K or n <= 0:
        return (f"--start {start} and --n {n} must be multiples of the balance block K={K} "
                "(PREREG D7); pass --partial-blocks for a quick $0 check")
    return None


def run(args: argparse.Namespace) -> int:
    overrides = parse_overrides(args.set or [])
    overrides.update({k: v for k, v in (("W_tokens", args.W), ("v_tokens", args.v))
                      if v is not None})
    cfg = GeneratorConfig.from_dict({**GeneratorConfig().to_dict(), **overrides})
    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    bad = [v for v in variants if v not in VARIANTS]
    if bad:
        print(f"unknown variants {bad}; choose from {VARIANTS}", file=sys.stderr)
        return 2
    if not args.partial_blocks and (err := whole_blocks_error(args.start, args.n,
                                                                cfg.K_options)):
        print(err, file=sys.stderr)
        return 2
    indices = range(args.start, args.start + args.n)
    chash = config_hash(cfg.to_dict())
    out = Path(args.out) if args.out else DEFAULT_OUT / f"{args.split}-{args.start}-{args.n}-{chash[:8]}"
    out.mkdir(parents=True, exist_ok=True)
    suffix = ".jsonl.gz" if args.gzip else ".jsonl"

    all_eps: list[Episode] = []
    n_single = 0
    st_file = _open(out / f"single_turn{suffix}", args.gzip) if args.single_turn else None
    with _open(out / f"episodes{suffix}", args.gzip) as f:
        for t, eps in generate(args.split, indices, cfg, ALL_CELLS, variants):
            for ep in eps:
                f.write(json.dumps(ep.to_dict(), ensure_ascii=False) + "\n")
                if st_file and ep.variant == "base" and not ep.cell.recoverable:
                    st_file.write(json.dumps(single_turn_control(ep), ensure_ascii=False) + "\n")
                    n_single += 1
            all_eps.extend(eps)
            if args.verbose:
                print(f"rendered {t.template_id} ({t.skin}, need {t.need_index}, "
                      f"{t.n_clues} clues)")
    if st_file:
        st_file.close()

    summary: dict = {
        "n_templates": args.n, "split": args.split, "indices": [args.start, args.start + args.n],
        "variants": variants, "n_episodes": len(all_eps), "n_single_turn_controls": n_single,
        "skins": dict(Counter(e.skin for e in all_eps if e.variant == variants[0]
                              and e.cell == ALL_CELLS[0])),
        "n_clues": dict(Counter(e.n_clues for e in all_eps
                                if e.variant == variants[0] and e.cell.id == "derived-nonrec-near")),
        "cells": cell_summary(all_eps),
    }
    if not args.no_checks:
        other = "pilot" if args.split == "main" else "main"
        cal = [sample_template(other, i, cfg).correct_label for i in range(min(args.n, 100))]
        summary["shortcut_audit"] = shortcut_audit(all_eps) + lookup_audit(all_eps)
        summary["heuristic_baselines"] = heuristic_baselines(all_eps, calibration_labels=cal)
        summary["oracles"] = oracle_scores(all_eps)
        # Gated (PREREG D2): no proper clue subset narrows the options, and the partial-
        # memory heuristics stay <= chance + margin in every derived cell.
        summary["partial_memory"] = partial_memory_from_episodes(all_eps)
        summary["validity_pass"] = (all(c["pass"] for c in summary["shortcut_audit"])
                                    and summary["heuristic_baselines"].get("pass", True)
                                    and summary["oracles"]["pass"]
                                    and (summary["partial_memory"] or {}).get("pass", True))
    manifest = {
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "generator_version": GENERATOR_VERSION, "schema_version": SCHEMA_VERSION,
        "config": cfg.to_dict(), "config_hash": chash, "seed_ranges": SEED_RANGES,
        "tiktoken": metadata.version("tiktoken"), "command": " ".join(sys.argv),
        **git_state(),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print_summary(summary, out)
    return 0 if summary.get("validity_pass", True) else 1


def print_summary(summary: dict, out: Path) -> None:
    print(f"wrote {summary['n_episodes']} episodes from {summary['n_templates']} templates "
          f"to {out}")
    # gapL/gapE: steps from the latest/earliest reveal to need; obsL: observation tokens from
    # the latest reveal through need (min); S_obs / S_R: designed window survival with empty
    # replies / assumed replies; ctx: max full-history context at need with assumed replies.
    print(f"{'cell':<22}{'n':>4}{'steps':>8}{'gapL':>7}{'gapE':>7}{'obsL':>8}"
          f"{'S_obs':>7}{'S_R':>6}{'ctx':>8}")
    def span(xs: list) -> str:
        return f"{xs[0]}-{xs[1]}"

    for cid, c in summary["cells"].items():
        print(f"{cid:<22}{c['n']:>4}{span(c['steps']):>8}"
              f"{span(c['gap_steps_latest']):>7}"
              f"{span(c['gap_steps_earliest']):>7}"
              f"{c['obs_tokens_latest_to_need'][0]:>8}{c['S_window_obs_only_rate']:>7.2f}"
              f"{c['S_window_assumed_replies_rate']:>6.2f}"
              f"{c['context_tokens_at_need_assumed_replies_max']:>8}")
    if "shortcut_audit" in summary:
        for chk in summary["shortcut_audit"]:
            print(f"  [{'ok' if chk['pass'] else 'FAIL'}] {chk['check']}")
        hb = summary["heuristic_baselines"]
        for view, res in hb.get("views", {}).items():
            accs = ", ".join(f"{k}={v['accuracy']:.2f}" for k, v in res.items())
            print(f"  baselines {view}: {accs} (threshold {hb['threshold']:.2f})")
        if "prior_label" in hb:
            print(f"  baselines prior_label: {hb['prior_label']['accuracy']:.2f}")
        orc = summary["oracles"]
        for name in ("key", "text", "lookup_no_memory"):
            accs = ", ".join(f"{k}={v['need_acc']:.2f}" for k, v in orc[name].items())
            print(f"  oracle {name}: {accs}")
        if summary.get("partial_memory"):
            for cid, pm in summary["partial_memory"]["cells"].items():
                print(f"  {cid}:")
                print_partial_memory(pm, indent="    ")
        print(f"validity_pass={summary['validity_pass']}")


def print_partial_memory(pm: dict, indent: str = "") -> None:
    print(f"{indent}partial memory (gated: narrowing = 0, base+rule uniform and smallest "
          f"above base <= {pm['threshold']:.2f}; chance {pm['chance']:.2f}): "
          f"{'pass' if pm['pass'] else 'FAIL'}")
    for key, row in [*pm["by_n_clues"].items(), ("all", pm["all"])]:
        label = f"{key} clues" if key != "all" else "all"
        print(f"{indent}  {label:<8} n={row['n_templates']:<5} narrowing="
              f"{row['narrowing_templates']} options left={row['base_and_rule_options_left_mean']:.1f}"
              f" base+rule uniform={row['base_and_rule_uniform_accuracy']:.3f} smallest above "
              f"base={row['smallest_above_base_accuracy']:.3f} | reported: nearest mid-range="
              f"{row['nearest_to_midrange_accuracy']:.3f} generator-aware Bayes max="
              f"{row['generator_aware_bayes_max']:.3f}")
    bayes = pm["all"]["generator_aware_bayes"] if pm["all"] else {}
    if bayes:
        print(f"{indent}  generator-aware Bayes by kept clues (reported): "
              + ", ".join(f"{k}={v:.3f}" for k, v in bayes.items()))


def run_partial_memory(args: argparse.Namespace) -> int:
    """Template-only (no rendering), so it is cheap for large N."""
    cfg = GeneratorConfig.from_dict({**GeneratorConfig().to_dict(),
                                     **parse_overrides(args.set or [])})
    items = []
    for i in range(args.start, args.start + args.n):
        t = sample_template(args.split, i, cfg)
        items.append((t.n_clues, t.clue_values, t.option_values, t.target_value))
    pm = partial_memory_diagnostic(items, cfg.to_dict())
    pm.update(split=args.split, indices=[args.start, args.start + args.n],
              config_hash=config_hash(cfg.to_dict()), generator_version=GENERATOR_VERSION)
    if args.out:
        Path(args.out).write_text(json.dumps(pm, indent=2) + "\n", encoding="utf-8")
    print_partial_memory(pm)
    return 0 if pm["pass"] else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="persistgym", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render", help="render N templates to JSONL and run the $0 checks")
    r.add_argument("--n", type=int, default=20, help="number of templates")
    r.add_argument("--split", choices=sorted(SEED_RANGES), default="main")
    r.add_argument("--start", type=int, default=0, help="first template index in the split")
    r.add_argument("--variants", default="base,restated,withheld",
                   help=f"comma-separated subset of {','.join(VARIANTS)}")
    r.add_argument("--single-turn", action="store_true",
                   help="also write the position-matched single-turn controls")
    r.add_argument("--W", type=int, default=None, help="override W_tokens")
    r.add_argument("--v", type=int, default=None, help="override v_tokens")
    r.add_argument("--set", action="append", metavar="KEY=VALUE",
                   help="override any GeneratorConfig field (value parsed as JSON), repeatable")
    r.add_argument("--out", default=None, help="output folder")
    r.add_argument("--gzip", action="store_true")
    r.add_argument("--partial-blocks", action="store_true",
                   help="allow --start/--n that are not whole balance blocks (quick $0 checks)")
    r.add_argument("--no-checks", action="store_true", help="skip audit, baselines, oracles")
    r.add_argument("--verbose", action="store_true")
    pm = sub.add_parser("partial-memory",
                        help="what partial memory of a derived fact gives away (PREREG D2; "
                             "templates only, no rendering)")
    pm.add_argument("--n", type=int, default=2000, help="number of templates")
    pm.add_argument("--split", choices=sorted(SEED_RANGES), default="main")
    pm.add_argument("--start", type=int, default=0)
    pm.add_argument("--set", action="append", metavar="KEY=VALUE",
                    help="override any GeneratorConfig field (value parsed as JSON)")
    pm.add_argument("--out", default=None, help="optional JSON output file")
    spotcheck.add_parsers(sub)
    args = p.parse_args(argv)
    return {"partial-memory": run_partial_memory, "spotcheck": spotcheck.run,
            "spotcheck-findings": spotcheck.run_findings}.get(args.cmd, run)(args)


if __name__ == "__main__":
    sys.exit(main())
