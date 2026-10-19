"""Render PersistGym-lite templates to JSONL and run the $0 validity checks.

    uv run python -m persistgym render --n 20
    uv run python -m persistgym render --split validity --n 10 --single-turn --gzip
    uv run python -m persistgym render --n 50 --W 24000 --v 1500 --out results/raw/persistgym/x
    uv run python -m persistgym partial-memory --n 2000
    uv run python -m persistgym audit --n 1000       # every $0 check, in chunks of 50 templates
    uv run python -m persistgym spotcheck            # G1 spot-check pages (persistgym/spotcheck.py)
    # gpt-6.1-sol's derived-fact variant (PREREG §17.3, amendment R3): chain clues and the
    # evidence notice (config.PRESETS["sol-chain"]); --set still overrides single fields
    uv run python -m persistgym render --preset sol-chain --split validity --n 20 --gzip
    uv run python -m persistgym partial-memory --preset sol-chain --n 2000
    uv run python -m persistgym spotcheck --preset sol-chain

Template counts and start indices come in whole balance blocks of K templates (PREREG D7);
`--partial-blocks` allows other counts for quick $0 checks. Splits: main [0, 50000),
validity [50000, 60000), pilot [90000, 100000) (seed = range start + index).

Writes into the output folder (default results/raw/persistgym/<split>-<start>-<n>-<hash8>,
gitignored): episodes.jsonl[.gz] (one Episode per line), single_turn.jsonl[.gz] (optional),
summary.json and manifest.json. No API calls; nothing here costs money.
"""

from __future__ import annotations

import argparse
import dataclasses
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
from persistgym.config import (
    GENERATOR_VERSION,
    PRESETS,
    SCHEMA_VERSION,
    SEED_RANGES,
    GeneratorConfig,
)
from persistgym.controls import single_turn_control
from persistgym.episode import ALL_CELLS, VARIANTS, Episode
from persistgym.render import generate
from persistgym.template import sample_template
from persistgym.validity import (
    BALANCE_CHECKS,
    _chain_items,
    _derived_items,
    balance_checks,
    chain_partial_memory,
    heuristic_baselines,
    lookup_audit,
    one_per_template,
    oracle_scores,
    partial_memory_diagnostic,
    partial_memory_from_episodes,
    prior_label_baseline,
    shortcut_audit,
)

DEFAULT_OUT = REPO_ROOT / "results" / "raw" / "persistgym"


def _open(path: Path, gz: bool):
    return gzip.open(path, "wt", encoding="utf-8", newline="\n") if gz else path.open("w", encoding="utf-8", newline="\n")


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


def config_of(preset: str, overrides: dict) -> GeneratorConfig:
    """The preset's config (`config.PRESETS`) with `overrides` (field -> value)."""
    return GeneratorConfig.from_dict({**PRESETS[preset].to_dict(), **overrides})


def run(args: argparse.Namespace) -> int:
    overrides = parse_overrides(args.set or [])
    overrides.update({k: v for k, v in (("W_tokens", args.W), ("v_tokens", args.v))
                      if v is not None})
    cfg = config_of(args.preset, overrides)
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
        "preset": args.preset, "config": cfg.to_dict(), "config_hash": chash,
        "seed_ranges": SEED_RANGES,
        "tiktoken": metadata.version("tiktoken"), "command": " ".join(sys.argv),
        **git_state(),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
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
        if "nearest_to_stand_in_value" in hb:
            si = hb["nearest_to_stand_in_value"]["by_cell"]
            print("  baselines nearest_to_stand_in_value (withheld): "
                  + ", ".join(f"{cid}={c['accuracy']:.2f}" for cid, c in si.items()))
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
    if pm.get("chain"):
        print_chain_partial_memory(pm["chain"], indent)


def print_chain_partial_memory(cm: dict, indent: str = "") -> None:
    print(f"{indent}chain records (amendment R3; gated: atom narrowing = 0, each misreading "
          f"<= {cm['threshold']:.2f}): {'pass' if cm['pass'] else 'FAIL'}")
    for key, row in [*cm["by_n_clues"].items(), ("all", cm["all"])]:
        label = f"{key} clues" if key != "all" else "all"
        print(f"{indent}  {label:<8} n={row['n_templates']:<5} atom narrowing="
              f"{row['atom_narrowing_templates']} | "
              + " ".join(f"{k}={v:.3f}" for k, v in row["heuristics"].items()))


def run_partial_memory(args: argparse.Namespace) -> int:
    """Template-only (no rendering), so it is cheap for large N. In chain form it also
    gives the atom-level and misreading figures, from `Template.chains` (the render summary
    computes them from the episode text instead)."""
    cfg = config_of(args.preset, parse_overrides(args.set or []))
    items, chain_items = [], []
    for i in range(args.start, args.start + args.n):
        t = sample_template(args.split, i, cfg)
        items.append((t.n_clues, t.clue_values, t.option_values, t.target_value))
        chain_items.append((t.n_clues, [(c.anchor, c.far, c.near, c.decoy) for c in t.chains],
                            t.option_values, t.target_value))
    pm = partial_memory_diagnostic(items, cfg.to_dict())
    if cfg.clue_form == "chain":
        pm["chain"] = chain_partial_memory(chain_items, cfg.to_dict())
        pm["pass"] = pm["pass"] and pm["chain"]["pass"]
    pm.update(split=args.split, indices=[args.start, args.start + args.n], preset=args.preset,
              config_hash=config_hash(cfg.to_dict()), generator_version=GENERATOR_VERSION)
    if args.out:
        Path(args.out).write_text(json.dumps(pm, indent=2) + "\n", encoding="utf-8", newline="\n")
    print_partial_memory(pm)
    return 0 if pm["pass"] else 1


def _add(acc: dict, key, value: float, n: int) -> None:
    """Accumulate a mean over `n` units: acc[key] = [sum of value * n, sum of n]."""
    total = acc.setdefault(key, [0.0, 0])
    total[0] += value * n
    total[1] += n


def _mean(acc: dict) -> dict:
    return {k: {"accuracy": round(v[0] / v[1], 4), "n": v[1]} for k, v in sorted(acc.items())}


ORACLE_MUST_BE_ONE = ("lookup_no_memory/base/rec", "lookup_no_memory/restated/rec",
                      "lookup_no_memory/restated/nonrec")


def _oracles_pass(oracles: dict) -> bool:
    """`validity.oracle_scores`'s rule on pooled means: the key and text oracles answer every
    need step of base and restated episodes and every routine step; the no-memory lookup
    oracle every need step where lookup is offered (base) or the records are restated."""
    must = []
    for k, v in oracles.items():
        name, group = k.split("/", 1)
        if k.endswith("/routine"):
            if name in ("key", "text"):
                must.append(v["accuracy"])
        elif ((name in ("key", "text") and not group.startswith("withheld"))
              or k in ORACLE_MUST_BE_ONE):
            must.append(v["accuracy"])
    return all(x == 1.0 for x in must)


def run_audit(args: argparse.Namespace) -> int:
    """Every $0 audit of `render` on many templates, rendered and audited in chunks of whole
    balance blocks so that memory stays small: the shortcut and lookup audits per chunk; the
    no-memory baselines pooled over the chunks (each chunk is whole blocks, and each
    accuracy is a mean over templates, so the pooled mean is exact); the oracles (means
    over episodes); the partial-memory gates on the items of every chunk (exact); and the
    balance checks once, on all templates. Writes nothing but `--out`, if given."""
    cfg = config_of(args.preset, parse_overrides(args.set or []))
    K = cfg.K_options
    if (err := whole_blocks_error(args.start, args.n, K)) or args.chunk % K or args.chunk <= 0:
        print(err or f"--chunk must be a positive multiple of K={K}", file=sys.stderr)
        return 2
    checks: dict[str, dict] = {}
    views: dict = {}
    stand_in: dict = {}
    oracles: dict = {}
    pm_items: dict[str, list] = defaultdict(list)
    chain_items: dict[str, list] = defaultdict(list)
    one = []
    n_eps = 0
    for lo in range(args.start, args.start + args.n, args.chunk):
        indices = range(lo, min(lo + args.chunk, args.start + args.n))
        eps = [e for _, es in generate(args.split, indices, cfg, ALL_CELLS, VARIANTS)
               for e in es]
        n_eps += len(eps)
        for c in shortcut_audit(eps) + lookup_audit(eps):
            if c["check"] in BALANCE_CHECKS:
                continue
            row = checks.setdefault(c["check"], {"pass": True, "failed_chunks": []})
            if not c["pass"]:
                row["pass"] = False
                row["failed_chunks"].append({"indices": [indices[0], indices[-1]],
                                             "detail": c["detail"]})
        hb = heuristic_baselines(eps)
        for view, res in hb["views"].items():
            for name, r in res.items():
                _add(views, f"{view}/{name}", r["accuracy"], r["n_templates"])
        for cid, r in hb.get("nearest_to_stand_in_value", {}).get("by_cell", {}).items():
            _add(stand_in, cid, r["accuracy"], r["n_templates"])
        orc = oracle_scores(eps)
        for name in ("key", "text", "lookup_no_memory"):
            for group, r in orc[name].items():
                _add(oracles, f"{name}/{group}", r["need_acc"], r["n"])
                _add(oracles, f"{name}/{group}/routine", r["routine_acc"], r["n"])
        by_template: dict[str, list[Episode]] = defaultdict(list)
        for e in eps:
            by_template[e.template_id].append(e)
            if e.variant == "base" and e.cell.fact == "derived":
                pm_items[e.cell.id] += _derived_items([e])
                if cfg.clue_form == "chain":
                    chain_items[e.cell.id] += _chain_items([e])
        one += [dataclasses.replace(one_per_template(es), steps=[], system_prompt="")
                for es in by_template.values()]
        del eps, by_template
        if args.verbose:
            print(f"audited templates {indices[0]}-{indices[-1]}", file=sys.stderr)
    for c in balance_checks(one):
        checks[c["check"]] = {"pass": c["pass"], "detail": c["detail"]}
    threshold = 1 / K + cfg.validity_margin_pp / 100
    other = "pilot" if args.split == "main" else "main"
    prior = prior_label_baseline([sample_template(other, i, cfg).correct_label
                                  for i in range(min(args.n, 1000))], one)
    pm = {cid: partial_memory_diagnostic(items, cfg.to_dict())
          for cid, items in sorted(pm_items.items())}
    for cid, items in chain_items.items():
        pm[cid]["chain"] = chain_partial_memory(items, cfg.to_dict())
        pm[cid]["pass"] = pm[cid]["pass"] and pm[cid]["chain"]["pass"]
    views_out, stand_in_out, oracles_out = _mean(views), _mean(stand_in), _mean(oracles)
    summary = {
        "preset": args.preset, "split": args.split,
        "indices": [args.start, args.start + args.n], "n_templates": args.n,
        "n_episodes": n_eps, "episodes_per_task_cell": n_eps // len(ALL_CELLS),
        "generator_version": GENERATOR_VERSION, "config_hash": config_hash(cfg.to_dict()),
        "threshold": threshold, "checks": checks, "baselines": views_out,
        "prior_label": prior, "nearest_to_stand_in_value": stand_in_out,
        "oracles": oracles_out, "partial_memory": pm,
    }
    summary["pass"] = (all(c["pass"] for c in checks.values())
                       and all(v["accuracy"] <= threshold
                               for v in [*views_out.values(), *stand_in_out.values()])
                       and (prior["accuracy"] or 0) <= threshold
                       and _oracles_pass(oracles_out)
                       and all(p["pass"] for p in pm.values()))
    if args.out:
        Path(args.out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"audited {n_eps} episodes ({summary['episodes_per_task_cell']} per task cell) from "
          f"{args.n} templates, {args.split} {args.start}-{args.start + args.n - 1}, preset "
          f"{args.preset}")
    for name, c in checks.items():
        print(f"  [{'ok' if c['pass'] else 'FAIL'}] {name}")
    print("  baselines: " + ", ".join(f"{k}={v['accuracy']:.3f}"
                                      for k, v in views_out.items()))
    print(f"  baselines prior_label: {prior['accuracy']:.3f}; nearest_to_stand_in_value: "
          + ", ".join(f"{k}={v['accuracy']:.3f}" for k, v in stand_in_out.items()))
    print("  oracles: " + ", ".join(f"{k}={v['accuracy']:.2f}" for k, v in oracles_out.items()
                                    if not k.endswith("/routine")))
    for cid, p in pm.items():
        print(f"  {cid}:")
        print_partial_memory(p, indent="    ")
    print(f"validity_pass={summary['pass']} (threshold {threshold:.2f})")
    return 0 if summary["pass"] else 1


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
    r.add_argument("--preset", choices=sorted(PRESETS), default="default",
                   help="generator config to start from (persistgym/config.py PRESETS; "
                        "sol-chain: gpt-6.1-sol's variant, PREREG §17.3)")
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
    pm.add_argument("--preset", choices=sorted(PRESETS), default="default",
                    help="generator config to start from (persistgym/config.py PRESETS)")
    pm.add_argument("--set", action="append", metavar="KEY=VALUE",
                    help="override any GeneratorConfig field (value parsed as JSON)")
    pm.add_argument("--out", default=None, help="optional JSON output file")
    au = sub.add_parser("audit", help="every $0 audit on many templates, in chunks of whole "
                                      "balance blocks (memory stays small)")
    au.add_argument("--n", type=int, default=1000, help="number of templates")
    au.add_argument("--split", choices=sorted(SEED_RANGES), default="main")
    au.add_argument("--start", type=int, default=0)
    au.add_argument("--chunk", type=int, default=50, help="templates per chunk (whole blocks)")
    au.add_argument("--preset", choices=sorted(PRESETS), default="default",
                    help="generator config to start from (persistgym/config.py PRESETS)")
    au.add_argument("--set", action="append", metavar="KEY=VALUE",
                    help="override any GeneratorConfig field (value parsed as JSON)")
    au.add_argument("--out", default=None, help="optional JSON output file")
    au.add_argument("--verbose", action="store_true")
    spotcheck.add_parsers(sub)
    args = p.parse_args(argv)
    return {"partial-memory": run_partial_memory, "audit": run_audit,
            "spotcheck": spotcheck.run,
            "spotcheck-findings": spotcheck.run_findings}.get(args.cmd, run)(args)


if __name__ == "__main__":
    sys.exit(main())
