"""The preprint's figures, from committed outputs only (CLAUDE.md: figures come from committed
scripts).

Run: ``uv run python -m analysis.figures [--results-root DIR] [--out-dir DIR]`` ($0). It writes
``<results root>/figures/<UTC>/`` with one PNG and one PDF per figure, and ``meta.json``.

1. ``fig1_arc_path``: ARC-AGI-3 RHAE by configuration (S0, S1, S2, S4), one line per path game
   and the mean; each config's counted run, found by ``analysis.arc_h4.load`` (H4's own rule).
2. ``fig2_h5_depth``: P(clear | reached) by level band and harness, published high-effort runs
   and ours (``results/arc_h5/<H5_OUTPUT>/h5.json``, the raw band tables).
3. ``fig3_persistgym``: success rate by harness cell and task cell, repeat 0
   (``results/persistgym_h1h3/<H1H3_OUTPUT>/h1h3.json``, its cell table).

Colors: the categorical slots 1-4 of the reference palette, validated (light mode, all checks
pass; aqua and yellow are below 3:1 contrast, so every line is labelled directly); the heatmap is
one blue ramp, light to dark. The figures plot effects against configurations and task
properties; nothing compares models.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

from analysis import arc_h4
from common import runmeta

RESULTS = Path(__file__).resolve().parents[1] / "results"
H5_OUTPUT = "20261011T055415Z"
H1H3_OUTPUT = "20261010T232227Z"
SLOTS = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100")   # categorical slots 1-4 (light)
INK, INK_2, GRID, SURFACE = "#1f1f1e", "#5f5e58", "#e6e5e0", "#ffffff"
BLUES = ("#eef4fd", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#104281")
CONFIGS = ("S0", "S1", "S2", "S4")
HARNESS_CELLS = (("F-0", "F-0 (full history)"), ("W-0", "W-0 (window)"),
                 ("W-n-0", "W-n-0 (window + notes)"), ("Σ-n-0", "Σ-n-0 (summary + notes; expl.)"))
TASK_CELLS = ("observed-nonrec-far", "observed-rec-far", "derived-nonrec-far", "derived-rec-far",
              "observed-nonrec-near", "observed-rec-near", "derived-nonrec-near",
              "derived-rec-near")
OUTPUTS = ("fig1_arc_path.png", "fig1_arc_path.pdf", "fig2_h5_depth.png", "fig2_h5_depth.pdf",
           "fig3_persistgym.png", "fig3_persistgym.pdf", "meta.json")


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def arc_scores(root: Path) -> dict[str, dict[str, float]]:
    """{game: {config: RHAE}} from each unit's counted run (H4's rule)."""
    d = arc_h4.load(root, with_s1=True)
    if d.incomplete:
        raise SystemExit("a unit lacks a counted run: " + "; ".join(d.incomplete))
    out: dict[str, dict[str, float]] = {}
    for (g, c), u in d.units.items():
        v, why = arc_h4._rhae(u.counted)
        if v is None:
            raise SystemExit(f"{g} {c}: no RHAE ({why})")
        out.setdefault(g, {})[c] = v
    return out


def fig1(scores: dict[str, dict[str, float]], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=200)
    _style(ax)
    x = range(len(CONFIGS))
    for i, (g, by) in enumerate(scores.items()):
        y = [by[c] for c in CONFIGS]
        xo = [xi + (i - 1.5) * 0.05 for xi in x]   # games that tie (e.g. at 100) stay visible
        ax.plot(xo, y, color=SLOTS[i], linewidth=2, marker="o", markersize=7, label=g,
                markeredgecolor=SURFACE, markeredgewidth=1.5, zorder=3)
        ax.annotate(g, (3, y[-1]), xytext=(8, (i - 1.5) * 7), textcoords="offset points",
                    color=INK, fontsize=9, va="center")
    mean = [sum(by[c] for by in scores.values()) / len(scores) for c in CONFIGS]
    ax.plot(x, mean, color=INK, linewidth=2.5, linestyle="--", marker="s", markersize=7,
            label="mean", zorder=4)
    for xi, m in zip(x, mean, strict=True):
        ax.annotate(f"{m:.1f}", (xi, m), xytext=(0, -14), textcoords="offset points",
                    ha="center", color=INK, fontsize=8)
    ax.set_xticks(list(x), ["S0\nStandard", "S1\nsummary + notes", "S2\nsummary", "S4\nAdapter"])
    ax.set_ylabel("RHAE (ARC per-game score)", color=INK_2, fontsize=9)
    ax.set_ylim(-5, 108)
    ax.set_xlim(-0.3, 3.6)
    ax.legend(frameon=False, fontsize=8, loc="upper left", labelcolor=INK)
    ax.set_title("ARC-AGI-3 path: score by harness configuration (4 games, 1 run each)",
                 color=INK, fontsize=10, loc="left")
    _save(fig, out / "fig1_arc_path")


def fig2(h5: dict, out: Path) -> None:
    bands = (("early", "levels 1-2"), ("level_3", "level 3"), ("deep", "levels ≥ 4"))
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.4), dpi=200, sharey=True,
                             gridspec_kw={"width_ratios": [1, 1]})
    for ax, key, title in ((axes[0], "published", "Published runs (25 games)"),
                           (axes[1], "ours", "Our runs (4 games)")):
        _style(ax)
        r = h5[key]
        names = r["harnesses"]
        for j, h in enumerate(("standard", "provider_adapter")):
            xs, ys = [], []
            for i, (b, _) in enumerate(bands):
                c = r["raw"]["bands"][b][h]
                if c["reached"]:
                    xs.append(i + (j - 0.5) * 0.18)
                    ys.append(c["rate"])
                    ax.annotate(f"{c['cleared']}/{c['reached']}", (xs[-1], ys[-1]),
                                xytext=(0, 8 if j else -14), textcoords="offset points",
                                ha="center", fontsize=7, color=INK_2)
            ax.plot(xs, ys, color=SLOTS[j], linewidth=2, marker="o", markersize=7,
                    markeredgecolor=SURFACE, markeredgewidth=1.5, label=names[h], zorder=3)
        ax.set_xticks(range(len(bands)), [lbl for _, lbl in bands])
        ax.set_ylim(-0.08, 1.12)
        ax.set_title(title, color=INK, fontsize=9, loc="left")
    axes[0].set_ylabel("P(clear | reached)", color=INK_2, fontsize=9)
    axes[0].legend(frameon=False, fontsize=8, loc="lower left", labelcolor=INK)
    fig.suptitle("Where the harness gap arises: clear rate by level band", color=INK,
                 fontsize=10, x=0.01, ha="left")
    _save(fig, out / "fig2_h5_depth")


def fig3(h: dict, out: Path) -> None:
    rate = {(c["kind"], c["task_cell"]): c["rate"] for c in h["cells"]
            if c.get("variant") == "base"}
    rows = [k for k, _ in HARNESS_CELLS if any((k, t) in rate for t in TASK_CELLS)]
    grid = [[rate.get((k, t)) for t in TASK_CELLS] for k in rows]
    cmap = LinearSegmentedColormap.from_list("blues", BLUES)
    fig, ax = plt.subplots(figsize=(7.4, 3.3), dpi=200)
    masked = [[float("nan") if v is None else v for v in row] for row in grid]
    ax.imshow(masked, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    for i, row in enumerate(grid):
        for j, v in enumerate(row):
            if v is not None:
                ax.text(j, i, f"{100 * v:.1f}%", ha="center", va="center", fontsize=8,
                        color=SURFACE if v > 0.6 else INK)
    label = dict(HARNESS_CELLS)
    ax.set_yticks(range(len(rows)), [label[k] for k in rows], fontsize=8, color=INK)
    ax.set_xticks(range(len(TASK_CELLS)),
                  [t.replace("-nonrec-", "\nnot recov.\n").replace("-rec-", "\nrecov.\n")
                   for t in TASK_CELLS], fontsize=7, color=INK_2)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    fig.suptitle("PersistGym-lite: success by harness and task cell (gpt-6-luna, 200 templates;"
                 " chance 10%)", color=INK, fontsize=9, x=0.01, ha="left")
    _save(fig, out / "fig3_persistgym")


def _save(fig, stem: Path) -> None:
    fig.tight_layout()
    fig.savefig(stem.with_suffix(".png"), facecolor=SURFACE)
    fig.savefig(stem.with_suffix(".pdf"), facecolor=SURFACE)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--results-root", type=Path, default=RESULTS)
    ap.add_argument("--out-dir", type=Path, default=None)
    a = ap.parse_args(argv)
    root = a.results_root
    now = datetime.now(UTC)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    out = a.out_dir or root / "figures" / run_id
    out.mkdir(parents=True, exist_ok=True)
    git = runmeta.git_state()
    h5 = json.loads((root / "arc_h5" / H5_OUTPUT / "h5.json").read_text(encoding="utf-8"))
    h13 = json.loads((root / "persistgym_h1h3" / H1H3_OUTPUT / "h1h3.json")
                     .read_text(encoding="utf-8"))
    fig1(arc_scores(root), out)
    fig2(h5, out)
    fig3(h13, out)
    runmeta.write_meta(
        out, git=git, experiment="figures", run_id=run_id, cell_or_config="preprint",
        config={"h5_output": H5_OUTPUT, "h1h3_output": H1H3_OUTPUT, "arc": "arc_h4.load"},
        model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
        repeat_index=None, seeds=None, started_utc=now.isoformat(timespec="seconds"),
        finished_utc=runmeta.utc_now(), exit_reason="completed", tokens=None, cost_usd=0.0,
        raw_transcript_path=None, outputs=list(OUTPUTS), paid_calls=0, runs=[])
    print(f"written: {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
