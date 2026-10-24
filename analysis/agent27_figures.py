"""Figures for the AGENT'27 workshop paper, sized for one IEEE column, from committed outputs only.

Run: ``uv run python -m analysis.agent27_figures [--results-root DIR] [--out-dir DIR]`` ($0). It writes
``<results root>/figures_agent27/<UTC>/`` with one PNG and one PDF per figure, and ``meta.json``.

1. ``fig_persistgym_two_models``: success rate by task cell (rows) and harness cell (columns), repeat
   0, in two panels of the same form: gpt-6-luna (the confirmatory model, from
   ``results/persistgym_h1h3/<H1H3_OUTPUT>``) and claude-haiku-5-5 (the replication, from
   ``results/persistgym_h1h3_haiku/<H1H3_HAIKU_OUTPUT>``), with W-n-0 from amendment R9's
   exploratory run (``results/haiku_notes/<HAIKU_NOTES_OUTPUT>/notes.json``, PREREG §17.9). Each
   panel shows only the harness cells that model ran. The panels follow the study's order
   (confirmatory, then replication), share one color scale, and are not compared: the figure
   plots effects against task properties.

The ARC path figure is ``analysis.figures``' ``fig1_arc_path``, which already fits a column.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from matplotlib.colors import LinearSegmentedColormap

from analysis.figures import BLUES, HARNESS_CELLS, INK, SURFACE, _save, plt
from common import runmeta

RESULTS = Path(__file__).resolve().parents[1] / "results"
H1H3_OUTPUT = "20261010T232227Z"
H1H3_HAIKU_OUTPUT = "20261019T003254Z"
HAIKU_NOTES_OUTPUT = "20261024T073307Z"
"""R9's readings (FINAL): Haiku's W-n-0 per task cell, exploratory (PREREG §17.9)."""
PANELS = (("gpt-6-luna", "persistgym_h1h3", H1H3_OUTPUT),
          ("claude-haiku-5-5", "persistgym_h1h3_haiku", H1H3_HAIKU_OUTPUT))
TASK_ROWS = (("observed-nonrec-far", "observed, not recov., far"),
             ("derived-nonrec-far", "derived, not recov., far"),
             ("observed-rec-far", "observed, recov., far"),
             ("derived-rec-far", "derived, recov., far"),
             ("observed-nonrec-near", "observed, not recov., near"),
             ("derived-nonrec-near", "derived, not recov., near"),
             ("observed-rec-near", "observed, recov., near"),
             ("derived-rec-near", "derived, recov., near"))
OUTPUTS = ("fig_persistgym_two_models.png", "fig_persistgym_two_models.pdf", "meta.json")


def rates(h: dict) -> dict[tuple[str, str], float]:
    """(harness cell, task cell) -> success rate, repeat 0, base variant."""
    return {(c["kind"], c["task_cell"]): c["rate"] for c in h["cells"] if c.get("variant") == "base"}


def notes_rates(notes: dict) -> dict[tuple[str, str], float]:
    """(W-n-0, task cell) -> success rate, from R9's readings (`analysis.haiku_notes`)."""
    return {(notes["cell"], c["task_cell"]): c["rate"] for c in notes["cells"]}


def label(v: float) -> str:
    """A percentage without the sign: '100', '7.5', '28.5'."""
    pct = round(100 * v, 1)
    return f"{pct:.0f}" if pct == int(pct) else f"{pct:.1f}"


def fig_two_models(panels: list[tuple[str, dict]], out: Path) -> None:
    cols = [[k for k, _ in HARNESS_CELLS if any((k, t) in r for t, _ in TASK_ROWS)] for _, r in panels]
    cmap = LinearSegmentedColormap.from_list("blues", BLUES)
    fig, axes = plt.subplots(1, len(panels), figsize=(3.45, 2.75), dpi=200,
                             gridspec_kw={"width_ratios": [len(c) for c in cols]})
    for p, (ax, (name, r), keys) in enumerate(zip(axes, panels, cols)):
        grid = [[r.get((k, t), float("nan")) for k in keys] for t, _ in TASK_ROWS]
        ax.imshow(grid, cmap=cmap, vmin=0, vmax=1, aspect="auto")
        for i, row in enumerate(grid):
            for j, v in enumerate(row):
                ax.text(j, i, label(v), ha="center", va="center", fontsize=6.5,
                        color=SURFACE if v > 0.6 else INK)
        ax.set_title(name, fontsize=7.5, color=INK, pad=3)
        ax.set_xticks(range(len(keys)), keys, fontsize=6.5, color=INK)
        ax.xaxis.tick_top()
        ax.set_yticks(range(len(TASK_ROWS)), [lab for _, lab in TASK_ROWS] if p == 0 else [],
                      fontsize=6.5, color=INK)
        ax.tick_params(length=0, pad=2)
        for s in ax.spines.values():
            s.set_visible(False)
    _save(fig, out / "fig_persistgym_two_models")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--results-root", type=Path, default=RESULTS)
    ap.add_argument("--out-dir", type=Path, default=None)
    a = ap.parse_args(argv)
    root = a.results_root
    now = datetime.now(UTC)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    out = a.out_dir or root / "figures_agent27" / run_id
    out.mkdir(parents=True, exist_ok=True)
    git = runmeta.git_state()
    panels = [(name, rates(json.loads((root / exp / run / "h1h3.json").read_text(encoding="utf-8"))))
              for name, exp, run in PANELS]
    notes = json.loads((root / "haiku_notes" / HAIKU_NOTES_OUTPUT / "notes.json")
                       .read_text(encoding="utf-8"))
    panels[1][1].update(notes_rates(notes))  # Haiku's panel gains R9's W-n-0
    fig_two_models(panels, out)
    runmeta.write_meta(
        out, git=git, experiment="figures_agent27", run_id=run_id, cell_or_config="agent27",
        config={"h1h3_output": H1H3_OUTPUT, "h1h3_haiku_output": H1H3_HAIKU_OUTPUT,
                "haiku_notes_output": HAIKU_NOTES_OUTPUT},
        model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
        repeat_index=None, seeds=None, started_utc=now.isoformat(timespec="seconds"),
        finished_utc=runmeta.utc_now(), exit_reason="completed", tokens=None, cost_usd=0.0,
        raw_transcript_path=None, outputs=list(OUTPUTS), paid_calls=0, runs=[])
    print(f"written: {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
