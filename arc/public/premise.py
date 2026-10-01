"""Read the premise check's published-run table from docs/background.md §4.

The premise check's own scripts are not in this repo (PLAN.md §8.1), so its numbers are only
available as that table. ``ops.py`` compares them with values re-derived from the pulled data.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKGROUND_MD = REPO_ROOT / "docs" / "background.md"

HEADER = ("| Game | Std score | PA score | Gap | Std $ | PA $ | Std actions | PA actions | "
          "Human baseline actions |")
COLUMNS = ["game", "std_score", "pa_score", "gap", "std_cost", "pa_cost", "std_actions",
           "pa_actions", "baseline_actions"]

# The premise check's claims that the operational slice re-checks.
CLAIM_EARLY_STD_HIGH = 11   # "11 of 25 Standard-high runs ended early without a win"
CLAIM_EARLY_PA_HIGH = 5     # "vs 5 of 25 for the Adapter"
CLAIM_ELIGIBLE = ("FT09", "SB26", "R11L", "LP85", "SC25", "CD82")

# Per-action claims in docs/background.md §4 ("Tokens per action", "Caching", "Compaction"),
# high effort, pooled over all 25 public games. Quoted here so ops.py can set them next to
# values re-derived from the 8 recorded games; the game sets differ.
CLAIM_PER_ACTION = {
    "standard": {"input": 148_000, "reasoning": 15_900, "visible_out": 907,
                 "cached_share": 0.17},
    "provider_adapter": {"input": 137_000, "reasoning": 6_100, "visible_out": 200,
                         "cached_share": 0.53},
}
CLAIM_COMPACTIONS = (2611, 17215)   # Adapter compactions, actions ("about every 6.6 actions")


def _num(cell: str) -> float:
    return float(cell.strip().replace("−", "-").replace(",", ""))


def parse_premise_table(text: str) -> list[dict]:
    lines = text.splitlines()
    try:
        start = lines.index(HEADER)
    except ValueError as e:
        raise ValueError("premise-check table header not found") from e
    rows = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != len(COLUMNS) or not re.fullmatch(r"[A-Z0-9]{4}", cells[0]):
            raise ValueError(f"unexpected premise table row: {line!r}")
        row = {"game": cells[0]}
        for k, v in zip(COLUMNS[1:], cells[1:], strict=True):
            row[k] = _num(v)
        rows.append(row)
    return rows


def load_premise_table(path: Path = BACKGROUND_MD) -> list[dict]:
    return parse_premise_table(path.read_text(encoding="utf-8"))
