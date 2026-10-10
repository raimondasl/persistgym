"""Action-matched readings of the ARC path runs (PREREG §17.5, amendment R5).

For each counted ARC path run, this computes from its committed `scorecard.json` how far it
got within its first K actions, so that configs are compared at the same number of actions
rather than inside the same 12 h clock. It is $0: it reads committed files only.

**ARC's game score** (`game_score`), as ARC's toolkit computes it (arc-agi 0.9.8,
https://pypi.org/project/arc-agi/0.9.8/, the release the pinned harness's `uv.lock` resolves:
`EnvironmentScoreCalculator.add_level` and `to_score` in `arc_agi/scorecard.py`; the rule is
stated at https://docs.arcprize.org/methodology, checked 2026-10-07):

* a cleared level ℓ with human baseline b and a > 0 actions scores min(100 (b / a)², 115); an
  uncleared level scores 0;
* the game score is the mean of the level scores weighted by the 1-indexed level number ℓ,
  over all n levels of the game, capped at 100 × (the weights of the levels that scored above
  0) / (all weights).

It reproduces block 2's run 1 exactly (73.02044380603104) and run 2 to the two decimals that
were reported (58.17).

**Actions and resets.** Actions are counted as ARC's scorecard counts them: every command the
harness submits after the play's opening RESET, a later RESET included. The opening RESET,
which the toolkit's environment wrapper sends when the game is made, starts the play and is
not counted; every later RESET adds 1 to both `resets` and `actions` (arc-agi 0.9.8,
`Card.inc_reset_count` and `Scorecard.update_scorecard`), and `level_actions` counts it on the
level being played. So `actions` = Σ `level_actions`, resets included (run 1: 206 actions with
4 resets, and the harness's `action_counter` in its `meta.json` is also 206; run 2: 236 with
4). This module checks Σ `level_actions` = `actions` for every run and flags a run where it
fails.

**At K actions** (`at_k`), for a run with `level_actions` a_1..a_n and L levels completed:

* level ℓ counts as cleared within K iff ℓ ≤ L and a_1 + ... + a_ℓ ≤ K;
* RHAE_K is ARC's game score with the levels cleared within K scored as ARC scores them and
  every other level scored 0: the score ARC would have given the run had it stopped after
  K actions. It never decreases with K, so a value at a run's end is a lower bound of its
  value at any larger K;
* status: `OBSERVED` if the run took at least K actions (the values are exact); `COMPLETE` if
  it took fewer and its own ending (`agent_exit_reason`, PREREG §7.5) is `GAME_WIN` or
  `ACTION_BUDGET`, so under ARC's rules it could take no more actions and its final values
  are its values at K; `CENSORED` otherwise (`TIME_BUDGET`, `COST_CAP`, an error ending or
  `UNKNOWN`): its final values are lower bounds.

The registered matched count is K = 150 (`REGISTERED_K`); the curve adds K = 50, 100 and 200
(`CURVE_K`). `--k` sets another K, which the outputs label exploratory.

**Counted runs** (PREREG §7.5; amendment R7): a run named by another run's `rerun_of` (a D19
re-run) or `r7_replaces` (an R7 replacement: S1 or S2 under R7's summary budget, replacing a
run that ended by the summarizer failure) is replaced by that run in every primary analysis;
all are listed, each replaced run with `counted` false. A unit's chain is original → (D19
re-run) → (R7 replacement) → (its D19 re-run), and its last run is the counted one. The links
are read from every folder's `meta.json`, so a run that is skipped below still replaces the run
it names. `analysis.checkpoint_c.check_links` checks the chains; this module only follows them.
The **replicate** is the seed label mod 100: an original's seed label is its replicate, a D19
re-run's is its original's + 100 (PREREG §7.4) and an R7 replacement's is the replicate + 200,
so 1, 101, 201 and 301 are all replicate 1.

**Runs without matched values** (PREREG §17.5): a run fails the checks (`checks_passed` false)
when its recomputed score or level scores differ from its scorecard's, or its Σ
`level_actions` differs from its `actions`. Such a run, and a counted run that is skipped (a
second play, level lists that do not match the level count, no scorecard), has no matched
values: the readings leave its unit out and list it.

**Pace and cost** per run, from its `meta.json`: wall clock (`wall_clock_s`) / actions, and
billed and list cost / actions. The billed and list costs are checked against the run's
`results/costs.csv` row.

**What is read.** Only `results/arc_path/<run_id>/` folders (or the folders given), and in
them `scorecard.json` and the `meta.json` fields in `META_FIELDS`. A folder whose `meta.json`
is not an `arc_path` run is refused, so pilot folders (`arc_pilot`, blinded, PREREG §11) are
never read. The outputs are built from allowlists (`RUN_FIELDS`, `CURVE_FIELDS`, `OUTPUTS`).

Run: ``uv run python -m analysis.arc_action_matched [--k K] [run folders]`` (``--no-write``
only prints). It writes ``results/arc_action_matched/<UTC>/runs.csv`` (one row per run, at
K), ``curve.csv`` (one row per run and K), ``summary.md`` and ``meta.json``. The H4 path
quantities and Checkpoint C's gap at K (PREREG §17.5) are computed from ``runs.csv`` by the
scripts of the primary readings, not here; neither exists yet.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from common import costs, runmeta

REPO_ROOT = runmeta.REPO_ROOT
ARC_PATH = REPO_ROOT / "results" / "arc_path"
OUT_ROOT = REPO_ROOT / "results" / "arc_action_matched"
EXPERIMENT = "arc_path"

REGISTERED_K = 150                      # PREREG §17.5
CURVE_K = (50, 100, 150, 200)           # descriptive (§17.5)
LEVEL_SCORE_CAP = 115.0                 # arc-agi 0.9.8, EnvironmentScoreCalculator.add_level
COMPLETE_ENDINGS = ("GAME_WIN", "ACTION_BUDGET")
OBSERVED, COMPLETE, CENSORED = "OBSERVED", "COMPLETE", "CENSORED"
COST_TOLERANCE_USD = 1e-6
SCORE_TOLERANCE = 1e-9
SEED_LABEL_STEP = 100                   # PREREG §7.4 (+ 100, a D19 re-run); R7 (+ 200)

META_FIELDS = ("experiment", "run_id", "cell_or_config", "game_requested", "seeds",
               "rerun_of", "r7_replaces", "agent_exit_reason", "exit_reason", "wall_clock_s",
               "cost_usd", "truncation_limits")
"""The only meta.json fields read."""

RUN_FIELDS = ("run_id", "game", "config", "replicate", "seed", "rerun_of", "r7_replaces",
              "replaced_by", "counted", "agent_exit_reason", "exit_reason", "actions", "resets",
              "sum_level_actions", "levels_completed", "level_count", "score_scorecard",
              "score_recomputed", "score_reproduced", "checks_passed", "cleared_at_actions",
              "wall_clock_s", "seconds_per_action", "cost_billed_usd", "cost_list_usd",
              "billed_usd_per_action", "list_usd_per_action", "costs_row", "K", "K_role",
              "status_at_K", "levels_cleared_at_K", "score_at_K")
CURVE_FIELDS = ("run_id", "game", "config", "replicate", "counted", "checks_passed", "K",
                "K_role", "status", "levels_cleared", "score")
OUTPUTS = ("runs.csv", "curve.csv", "summary.md")


# --- ARC's score ---------------------------------------------------------------------------

def level_score(baseline: int, actions: int, cleared: bool) -> float:
    """One level's score, exactly as arc-agi 0.9.8 computes it (`add_level`)."""
    if not cleared or actions <= 0:
        return 0.0
    return min(((baseline / actions) ** 2) * 100, LEVEL_SCORE_CAP)


def game_score(level_scores: list[float]) -> float:
    """The game score from all n level scores (level ℓ has weight ℓ), exactly as arc-agi
    0.9.8 computes it (`to_score`), summation order included."""
    if not level_scores:
        return 0.0
    total_score, total_weights, max_weights = 0.0, 0, 0
    for i, s in enumerate(level_scores):
        weight = i + 1
        total_score += s * weight
        total_weights += weight
        if s > 0:
            max_weights += weight
    return min(total_score / total_weights, max_weights / total_weights * 100)


def cumulative(level_actions: list[int]) -> list[int]:
    out, total = [], 0
    for a in level_actions:
        total += a
        out.append(total)
    return out


def cleared_within(level_actions: list[int], levels_completed: int, k: int) -> int:
    """The number of levels cleared within the first k actions: level ℓ counts iff ℓ ≤
    levels_completed and the actions through level ℓ are at most k (levels clear in order)."""
    n = 0
    for level, through in enumerate(cumulative(level_actions), start=1):
        if level > levels_completed or through > k:
            break
        n = level
    return n


def score_within(baselines: list[int], level_actions: list[int], levels_completed: int,
                 k: int) -> float:
    """RHAE_K: ARC's game score with only the levels cleared within k actions cleared."""
    m = cleared_within(level_actions, levels_completed, k)
    return game_score([level_score(b, a, i < m)
                       for i, (b, a) in enumerate(zip(baselines, level_actions, strict=True))])


def status_at(actions: int, agent_exit_reason: str | None, k: int) -> str:
    if actions >= k:
        return OBSERVED
    return COMPLETE if agent_exit_reason in COMPLETE_ENDINGS else CENSORED


# --- runs ----------------------------------------------------------------------------------

class Refused(ValueError):
    """A folder this module must not read (not an arc_path run)."""


@dataclass
class Run:
    folder: Path
    run_id: str
    game: str
    config: str
    seed: int | None
    replicate: int | None
    rerun_of: str | None
    agent_exit_reason: str
    exit_reason: str | None
    wall_clock_s: float | None
    cost_billed_usd: float | None
    cost_list_usd: float | None
    actions: int
    resets: int | None
    levels_completed: int
    level_count: int
    level_actions: list[int]
    level_baseline_actions: list[int]
    level_scores: list[float]
    score_scorecard: float
    replaced_by: list[str] = field(default_factory=list)
    costs_row: str = "not checked"
    r7_replaces: str | None = None

    @property
    def counted(self) -> bool:
        return not self.replaced_by

    @property
    def sum_level_actions(self) -> int:
        return sum(self.level_actions)

    @property
    def recomputed_level_scores(self) -> list[float]:
        return [level_score(b, a, i < self.levels_completed)
                for i, (b, a) in enumerate(zip(self.level_baseline_actions,
                                               self.level_actions, strict=True))]

    @property
    def score_recomputed(self) -> float:
        return game_score(self.recomputed_level_scores)

    @property
    def score_reproduced(self) -> bool:
        return (abs(self.score_recomputed - self.score_scorecard) <= SCORE_TOLERANCE
                and all(abs(x - y) <= SCORE_TOLERANCE for x, y in
                        zip(self.recomputed_level_scores, self.level_scores, strict=True)))

    @property
    def checks_passed(self) -> bool:
        """Both checks pass: ARC's score is reproduced and Σ level_actions = actions. A run
        that fails either has no matched values (PREREG §17.5)."""
        return self.score_reproduced and self.sum_level_actions == self.actions

    @property
    def cleared_at_actions(self) -> list[int]:
        """The action count at which each completed level was cleared (the curve)."""
        return cumulative(self.level_actions)[: self.levels_completed]

    def at_k(self, k: int) -> dict:
        return {"status": status_at(self.actions, self.agent_exit_reason, k),
                "levels_cleared": cleared_within(self.level_actions, self.levels_completed, k),
                "score": score_within(self.level_baseline_actions, self.level_actions,
                                      self.levels_completed, k)}

    def per_action(self, value: float | None) -> float | None:
        return None if value is None or self.actions <= 0 else value / self.actions


def _meta(folder: Path) -> dict:
    raw = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    return {k: raw.get(k) for k in META_FIELDS}


def _number(value) -> float | None:
    return None if value is None else float(value)


def replicate_of(seed: int | None) -> int | None:
    """The replicate a seed label stands for: the label mod 100 (1, 101, 201 and 301 are all
    replicate 1; module docstring)."""
    return None if seed is None else int(seed) % SEED_LABEL_STEP


def load_run(folder: Path) -> Run | str:
    """The run in `folder`, or the reason it is skipped. Refused unless its meta.json is an
    arc_path run (so no pilot folder is ever read)."""
    folder = Path(folder)
    if not (folder / "meta.json").is_file():
        raise Refused(f"{folder}: no meta.json, not an arc_path run folder")
    meta = _meta(folder)
    if meta["experiment"] != EXPERIMENT:
        raise Refused(f"{folder}: experiment {meta['experiment']!r}, not {EXPERIMENT!r}; only "
                      "arc_path runs are read (pilots are blinded, PREREG §11)")
    if any(v is not None for v in (meta["truncation_limits"] or {}).values()):
        return "truncated (not a counted run)"
    if not (folder / "scorecard.json").is_file():
        return "no scorecard.json"
    card = json.loads((folder / "scorecard.json").read_text(encoding="utf-8"))
    envs = card.get("environments") or []
    if len(envs) != 1:
        return f"{len(envs)} environments on the scorecard, expected 1"
    env = envs[0]
    plays = env.get("runs") or []
    if len(plays) != 1:
        return (f"{len(plays)} plays on the scorecard (a full reset starts a new play); "
                "not handled")
    play = plays[0]
    lists = [play.get(k) or [] for k in ("level_actions", "level_baseline_actions",
                                         "level_scores")]
    level_count = env.get("level_count")
    if level_count is None or any(len(x) != level_count for x in lists):
        return (f"level lists of lengths {[len(x) for x in lists]} against level_count "
                f"{level_count}")
    seeds = meta["seeds"] or {}
    seed = seeds.get("replicate_seed")
    cost = meta["cost_usd"] or {}
    return Run(folder=folder, run_id=meta["run_id"], game=str(meta["game_requested"]).upper(),
               config=meta["cell_or_config"], seed=seed, replicate=replicate_of(seed),
               rerun_of=meta["rerun_of"], r7_replaces=meta["r7_replaces"],
               agent_exit_reason=meta["agent_exit_reason"] or "UNKNOWN",
               exit_reason=meta["exit_reason"], wall_clock_s=_number(meta["wall_clock_s"]),
               cost_billed_usd=_number(cost.get("billed_est")),
               cost_list_usd=_number(cost.get("list")), actions=int(play["actions"]),
               resets=play.get("resets"), levels_completed=int(play["levels_completed"]),
               level_count=int(level_count), level_actions=[int(a) for a in lists[0]],
               level_baseline_actions=[int(b) for b in lists[1]],
               level_scores=[float(s) for s in lists[2]],
               score_scorecard=float(play["score"]))


def run_folders(root: Path = ARC_PATH) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(d for d in root.iterdir() if d.is_dir() and (d / "meta.json").is_file())


def collect(folders: list[Path]) -> tuple[list[Run], list[tuple[str, str]]]:
    """The runs in `folders`, linked to the runs that replace them (a D19 re-run or an R7
    replacement), and the skipped folders with reasons. The links come from every folder's
    meta.json, skipped folders included, so a run whose replacement is skipped is still not
    counted (PREREG §7.5; R7)."""
    runs, skipped, links = [], [], []
    for folder in folders:
        got = load_run(folder)
        meta = _meta(Path(folder))
        links.append((meta["run_id"], (meta["rerun_of"], meta["r7_replaces"])))
        if isinstance(got, str):
            skipped.append((Path(folder).name, got))
        else:
            runs.append(got)
    if len({run_id for run_id, _ in links}) != len(links):
        raise ValueError("two folders hold the same run_id")
    by_id = {r.run_id: r for r in runs}
    for run_id, replaced in links:
        for name in replaced:
            if name in by_id:
                by_id[name].replaced_by.append(run_id)
    return runs, skipped


def check_costs(runs: list[Run], costs_csv: Path = costs.COSTS_CSV) -> None:
    """Set each run's `costs_row`: `match`, `missing` or `mismatch` (billed or list cost in
    its results/costs.csv row differs from its meta.json)."""
    rows = {r["run_id"]: r for r in costs.read_rows(costs_csv)} if costs_csv.is_file() else {}
    for run in runs:
        row = rows.get(run.run_id)
        if row is None:
            run.costs_row = "missing"
            continue
        pairs = ((row.get("cost_usd_billed_est"), run.cost_billed_usd),
                 (row.get("cost_usd_list"), run.cost_list_usd))
        ok = all((a in (None, "") and b is None) or (a not in (None, "") and b is not None
                                                     and abs(float(a) - b) <= COST_TOLERANCE_USD)
                 for a, b in pairs)
        run.costs_row = "match" if ok else "mismatch"


# --- outputs -------------------------------------------------------------------------------

def k_role(k: int) -> str:
    if k == REGISTERED_K:
        return "registered"
    return "curve" if k in CURVE_K else "exploratory"


def curve_ks(k: int) -> list[int]:
    return sorted(set(CURVE_K) | {k})


def run_row(run: Run, k: int) -> dict:
    at = run.at_k(k)
    row = {"run_id": run.run_id, "game": run.game, "config": run.config,
           "replicate": run.replicate, "seed": run.seed, "rerun_of": run.rerun_of or "",
           "r7_replaces": run.r7_replaces or "", "replaced_by": ";".join(run.replaced_by),
           "counted": run.counted,
           "agent_exit_reason": run.agent_exit_reason, "exit_reason": run.exit_reason or "",
           "actions": run.actions, "resets": run.resets,
           "sum_level_actions": run.sum_level_actions,
           "levels_completed": run.levels_completed, "level_count": run.level_count,
           "score_scorecard": run.score_scorecard, "score_recomputed": run.score_recomputed,
           "score_reproduced": run.score_reproduced, "checks_passed": run.checks_passed,
           "cleared_at_actions": ";".join(str(x) for x in run.cleared_at_actions),
           "wall_clock_s": run.wall_clock_s,
           "seconds_per_action": run.per_action(run.wall_clock_s),
           "cost_billed_usd": run.cost_billed_usd, "cost_list_usd": run.cost_list_usd,
           "billed_usd_per_action": run.per_action(run.cost_billed_usd),
           "list_usd_per_action": run.per_action(run.cost_list_usd),
           "costs_row": run.costs_row, "K": k, "K_role": k_role(k),
           "status_at_K": at["status"], "levels_cleared_at_K": at["levels_cleared"],
           "score_at_K": at["score"]}
    assert tuple(row) == RUN_FIELDS
    return row


def curve_rows(run: Run, k: int) -> list[dict]:
    rows = []
    for kk in curve_ks(k):
        at = run.at_k(kk)
        row = {"run_id": run.run_id, "game": run.game, "config": run.config,
               "replicate": run.replicate, "counted": run.counted,
               "checks_passed": run.checks_passed, "K": kk,
               "K_role": k_role(kk), "status": at["status"],
               "levels_cleared": at["levels_cleared"], "score": at["score"]}
        assert tuple(row) == CURVE_FIELDS
        rows.append(row)
    return rows


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return repr(v)
    return str(v)


def to_csv(rows: list[dict], fields: tuple[str, ...]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(fields), lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({f: _cell(r[f]) for f in fields})
    return buf.getvalue()


def _f(v, digits=2) -> str:
    return "n/a" if v is None else f"{v:.{digits}f}"


def summary_lines(runs: list[Run], skipped: list[tuple[str, str]], k: int,
                  generated: str, git: dict) -> list[str]:
    role = k_role(k)
    L = ["# Action-matched readings of the ARC path runs (PREREG §17.5, amendment R5)", "",
         (f"Computed {generated} at commit {git['git_commit'][:7]} (dirty: {git['git_dirty']}) "
          f"by `uv run python -m analysis.arc_action_matched`. K = {k}: "
          + ("the registered matched count." if role == "registered"
             else f"not the registered count ({REGISTERED_K}); readings at this K are "
                  "exploratory.")), "",
         "Rules (module docstring; PREREG §17.5):",
         ("- **RHAE_K** is ARC's game score with only the levels cleared within the first K "
          "actions cleared: a cleared level scores min(100 (baseline / actions)², 115), "
          "others 0, weighted by the 1-indexed level number, capped at 100 × the weight "
          "share of levels above 0 (arc-agi 0.9.8 `arc_agi/scorecard.py`; "
          "https://docs.arcprize.org/methodology)."),
         ("- **Actions** are the scorecard's: every RESET after the opening one counts, so "
          "Σ level_actions = actions."),
         ("- **Status at K:** OBSERVED (the run took ≥ K actions; exact), COMPLETE (fewer, "
          "ended GAME_WIN or ACTION_BUDGET; final values hold at K), CENSORED (fewer, ended "
          "any other way; values are lower bounds)."),
         ("- Only counted runs enter the H4 readings; a run replaced by its re-run or by its "
          "R7 replacement is listed with counted = False (PREREG §7.5; R7). Rep. is the seed "
          "label mod 100."),
         ("- A run that fails a check below, or a counted run that is skipped, has no matched "
          "values: the readings leave its unit out and list it."), "",
         f"## Runs at K = {k}", "",
         ("| Run | Game | Config | Rep. | Counted | Ending (agent) | Actions (resets) | "
          "Levels | Score: scorecard; recomputed | Checks | Status at K | "
          "Levels cleared within K | RHAE_K |"),
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        at = r.at_k(k)
        L.append(f"| `{r.run_id}` | {r.game} | {r.config} | {r.replicate} | {r.counted} | "
                 f"{r.agent_exit_reason} | {r.actions} ({r.resets}) | "
                 f"{r.levels_completed} of {r.level_count} | {r.score_scorecard:.2f}; "
                 f"{r.score_recomputed:.2f} | {'pass' if r.checks_passed else '**fail**'} | "
                 f"{at['status']} | {at['levels_cleared']} | {at['score']:.2f} |")
    ks = curve_ks(k)
    L += ["", "## Levels cleared and RHAE_K by action count", "",
          "Each cell: levels cleared within K; RHAE_K; status. Descriptive.", "",
          "| Run | Cleared at actions | " + " | ".join(f"K = {kk}" for kk in ks) + " |",
          "|---|---|" + "---|" * len(ks)]
    for r in runs:
        cells = []
        for kk in ks:
            at = r.at_k(kk)
            cells.append(f"{at['levels_cleared']}; {at['score']:.2f}; {at['status']}")
        cleared = ", ".join(str(x) for x in r.cleared_at_actions) or "none"
        L.append(f"| `{r.run_id}` | {cleared} | " + " | ".join(cells) + " |")
    L += ["", "## Pace and cost", "",
          ("| Run | Wall clock (h) | Seconds per action | Billed USD | Billed USD per action | "
           "List USD per action | costs.csv row |"),
          "|---|---|---|---|---|---|---|"]
    for r in runs:
        hours = None if r.wall_clock_s is None else r.wall_clock_s / 3600
        L.append(f"| `{r.run_id}` | {_f(hours)} | {_f(r.per_action(r.wall_clock_s), 1)} | "
                 f"{_f(r.cost_billed_usd)} | {_f(r.per_action(r.cost_billed_usd), 4)} | "
                 f"{_f(r.per_action(r.cost_list_usd), 4)} | {r.costs_row} |")
    bad_score = [r.run_id for r in runs if not r.score_reproduced]
    bad_actions = [r.run_id for r in runs if r.sum_level_actions != r.actions]
    bad_costs = [r.run_id for r in runs if r.costs_row != "match"]
    L += ["", "## Checks", "",
          ("- ARC's score reproduced from the level lists: "
           + ("every run." if not bad_score else f"**not for {', '.join(bad_score)}**.")),
          ("- Σ level_actions = actions: "
           + ("every run." if not bad_actions else f"**fails for {', '.join(bad_actions)}**.")),
          ("- A run that fails either check has no matched values until the difference is "
           "explained in `results/decisions.md`, and any change of rule it needs is made by "
           "a dated amendment; until then its unit is left out of every matched reading "
           "(PREREG §17.5)."),
          ("- costs.csv row matches meta.json: "
           + ("every run." if not bad_costs else
              "; ".join(f"{r.run_id}: {r.costs_row}" for r in runs if r.costs_row != "match")
              + "."))]
    if skipped:
        L += ["- Folders skipped: " + "; ".join(f"`{n}`: {why}" for n, why in skipped) + "."]
    L += ["", "## What this does not show", "",
          ("- Matching actions removes the 12 h clock's effect of speed, not the effects of "
           "context length: a config whose history is longer at action K is also slower per "
           "call, and its play up to K comes from that history."),
          ("- The clock-based primary readings (PREREG §3 H4) remain what ARC's harness "
           "rewards; every prediction and rule reads them."),
          ("- A run's first K actions are not a random sample of its play: early levels come "
           "first, and RHAE_K weights each level by its number over all levels of the game."),
          "- Per-run values only; the H4 path quantities at K are computed from `runs.csv`."]
    return L


def write(out_dir: Path, run_id: str, started: str, runs: list[Run],
          skipped: list[tuple[str, str]], k: int, git: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "runs.csv").write_text(to_csv([run_row(r, k) for r in runs], RUN_FIELDS),
                                      encoding="utf-8", newline="")
    (out_dir / "curve.csv").write_text(
        to_csv([row for r in runs for row in curve_rows(r, k)], CURVE_FIELDS),
        encoding="utf-8", newline="")
    (out_dir / "summary.md").write_text(
        "\n".join(summary_lines(runs, skipped, k, started, git)) + "\n", encoding="utf-8",
        newline="\n")

    def rel(p: Path) -> str:
        p = p.resolve()
        return p.relative_to(REPO_ROOT).as_posix() if p.is_relative_to(REPO_ROOT) else str(p)

    config = {"prereg": "PREREG.md §17.5 (amendment R5)", "K": k, "K_role": k_role(k),
              "registered_K": REGISTERED_K, "curve_K": list(CURVE_K),
              "complete_endings": list(COMPLETE_ENDINGS),
              "score_rule": "arc-agi 0.9.8 arc_agi/scorecard.py (add_level, to_score); "
                            "https://docs.arcprize.org/methodology",
              "inputs": [rel(r.folder) for r in runs],
              "skipped": [{"folder": n, "reason": why} for n, why in skipped]}
    return runmeta.write_meta(
        out_dir, git=git, experiment="arc_action_matched", run_id=run_id,
        cell_or_config=f"K={k}", config=config, model_requested=None, model_returned=None,
        reasoning_effort=None, reasoning_context_requested=None, reasoning_context_echoed=None,
        template_id=None, repeat_index=None, seeds=None, started_utc=started,
        finished_utc=runmeta.utc_now(), exit_reason="completed", tokens=None, cost_usd=0.0,
        raw_transcript_path=None, outputs=list(OUTPUTS), paid_calls=0,
        runs=[r.run_id for r in runs])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("folders", nargs="*", type=Path,
                    help="arc_path run folders (default: every folder in results/arc_path/)")
    ap.add_argument("--k", type=int, default=REGISTERED_K,
                    help=f"matched action count (registered: {REGISTERED_K})")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="default: results/arc_action_matched/<UTC>/")
    ap.add_argument("--costs-csv", type=Path, default=costs.COSTS_CSV)
    ap.add_argument("--no-write", action="store_true", help="print only")
    a = ap.parse_args(argv)
    if a.k <= 0:
        ap.error("--k must be a positive number of actions")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    started = datetime.now(UTC)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    git = runmeta.git_state()
    runs, skipped = collect(a.folders or run_folders())
    check_costs(runs, a.costs_csv)
    stamp = started.isoformat(timespec="seconds")
    print("\n".join(summary_lines(runs, skipped, a.k, stamp, git)))
    if not a.no_write:
        out = a.out_dir or OUT_ROOT / run_id
        write(out, run_id, stamp, runs, skipped, a.k, git)
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
