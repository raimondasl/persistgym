"""The size rule of amendment R8 (PREREG §17.8): W-n-0 and T for claude-haiku-5-5's main runs.

R8 fixes W-n-0 and T before any main episode, by a rule on F, the forecast billed cost of
Haiku's main runs with their repeats and both controls, made by a committed $0 script from
block `4-haiku`'s measured `results/costs.csv` rows, against R, the block's $180 limit minus
its spend so far:

1. W-n-0 runs, at T = 200, iff F(T = 200, with W-n-0) ≤ 0.85 R;
2. otherwise W-n-0 does not run, and T = 200 iff F(T = 200, without W-n-0) ≤ 0.85 R;
3. otherwise T is the largest multiple of 10 below 200 with F(T, without W-n-0) ≤ 0.85 R;
4. if no T ≥ 10 qualifies, no main run starts, and Claude asks the researcher.

This script computes F and R and applies the rule exactly so (`size_rule`), in exact rational
arithmetic (`fractions.Fraction`: a cost per episode is kept as the runs' billed cost over
their episodes, never rounded), so that a forecast at exactly 0.85 R fits. It decides nothing
else: F, R, the outcome and the script's commit go into `results/decisions.md` before any
main episode, and the pull request that records them sets `harnesses.registered.HAIKU_T` (and
`HAIKU_CELLS` without W-n-0 if it does not run).

**What F counts** (R8, Design and Order): the main runs on main templates 0 to T - 1 at
repeat 0, plus repeat 1 on the templates divisible by 10 (§2.9), controls included:

* F-0 and W-0, and W-n-0 when it is counted, each on all 8 task cells: 8 × (T + T/10)
  episodes per harness cell;
* the restated-at-need control, as full F-0 episodes on all 8 task cells: 8 × (T + T/10);
* the single-turn control on the 4 non-recoverable task cells: 4 × (T + T/10) prompts.

Each line is its number of episodes (prompts) times an estimated billed cost per episode (per
prompt). Spend is measured as every cap measures it (`common.costs.spend_usd`: the billed
estimate, or the list cost where a row has none; on Anthropic billed equals list, but for
refusals Anthropic does not bill).

**R** is $180 (`BLOCK_MAX_USD`, block `4-haiku`'s `max_usd`, `results/decisions.md`,
2026-10-18) minus the block's spend: the sum over the rows whose notes contain
`approved_block=4-haiku;` (`common.approval.block_spend`, the paid guard's own measure). Rows
of any other block count neither toward R nor toward any estimate.

**The input rows.** A `persistgym_haiku` row anywhere in the ledger, of block `4-haiku`, of
another block or of none, means that a main episode has run, after which the rule no longer
applies, so the script refuses; to re-derive the record later, pass the ledger as it was (for
example `git show <commit>:results/costs.csv`). Every row of block `4-haiku` must be a
claude-haiku-5-5 pilot or validity run (`persistgym_pilot`, `persistgym_validity`). Each
row's episode count (`n_episodes_run`), variant (the last part of its episode ids) and task
cells (the middle part) come from its run's `meta.json` at
`<results root>/<experiment>/<run_id>/meta.json`, which is checked against the row (run id,
experiment, cell, model) and the default generator config. A run must have played every
episode it planned (`n_episodes_run` equal to the number of its episode ids): which episodes
a run that stopped early played is not in its meta.json, and its one costs row cannot be
split between them, so the script refuses such a run. Rows of one cell and variant are
pooled (a re-run of a whole pilot, say): their billed cost over their episodes.

**Which rows feed which line** (`per_episode`).

* **W-0 and W-n-0:** their pilot rows (pilot template 0 × the 8 task cells, 8 episodes each),
  the only measurement of either cell on Haiku.
* **The single-turn control:** its pilot row (pilot templates 0-1 × the 4 non-recoverable
  task cells, 8 prompts), per prompt.
* **F-0 and the restated control:** the restated validity run (F-0 on validity templates
  0-19 × the 8 task cells, 160 episodes) once it is in the ledger; until then F-0's pilot
  row. The validity run is the better estimate of both: it is F-0 on 20 templates against the
  pilot's one, with 20 times the episodes, and its episodes are the restated control's own
  variant. On luna it came within 0.5% of the main F-0 run and 0.1% of the main restated
  control (below). The authority is `results/decisions.md` (2026-10-18, item 2: the forecast
  "from the pilots' and validity runs' costs"); PREREG §17.8's own words are "from the
  pilots' `costs.csv` rows", and this choice was committed (2026-10-18, 05:12 UTC) after both
  validity runs' rows were in the ledger (04:51 and 04:56 UTC). So the summary also reports F,
  and what the rule would give, with F-0 and the restated control on F-0's pilot row
  (`per_episode(..., pilot_only=True)`): reported, never applied.
* **The withheld validity run** feeds no line: its episodes withhold the fact that the need
  step asks for, which no main episode does, and on luna it cost 14% more per episode than
  the main F-0 run. It counts toward the block's spend, and the summary reports its cost per
  episode.

**Scaling the pilot sample.** Each multi-turn pilot plays pilot template 0 once on each of the
8 task cells, the mix the main matrix plays on every template, so its mean cost per episode
is taken as the main runs' with no reweighting, and multiplied by their episodes. The script
checks this: the runs that feed a line (and the withheld validity run) must together play
each of the 8 task cells equally often, the single-turn control's each of its 4, or it
refuses, since one costs row per run cannot be reweighted per task cell. One
template cannot show the spread between templates. The summary reports F-0's restated
validity cost per episode (20 templates) over its pilot cost per episode as a check of how
typical pilot template 0 is: a check, not a correction, so it is not applied to the W cells.

**Cold and warm caches.** Every multi-turn request uses automatic prompt caching with the
5-minute TTL (R8): a call reads the prefix that an earlier call cached within 5 minutes, and
writes its new suffix to the cache at 1.25 times the input price (a read costs 0.1 times).
A main run at repeat 0 is cold: no other run has played its episodes in the last 5 minutes
(each main run lasts far longer, and they run one at a time). The bases:

* F-0's pilot and the restated validity run were the first Haiku runs of their episodes, so
  they are cold, like the main runs;
* W-n-0's system prompt adds the notes sentence, so its requests share no prefix with F-0's
  or W-0's: its pilot was cold;
* W-0 sends F-0's system prompt and, until its first eviction, F-0's messages
  (`harnesses/DESIGN.md` §13.2), and its pilot ran right after F-0's on the same episodes
  (R8's order). Its calls before the first eviction may therefore have read prefixes that
  F-0's pilot had just cached, and its estimate may be a little low. After an eviction the
  cached prefix no longer matches, so most of a W cell's input is written to the cache
  either way. At repeat 1 the runs are short (T/10 templates), and W-0's may again follow
  F-0's within the TTL, as in the pilots;
* the single-turn control sends no `cache_control`, so caching does not enter.

**Sensitivity** (reported, never applied). The same rule with every cost per episode × 1.25
(`SENSITIVITY_FACTOR`), and the margin: the factor on every cost per episode at which the
outcome's forecast would stop fitting 0.85 R (F is linear in them). Why 1.25: on luna, which
played the same episodes, each main run's cost per episode at repeat 0 came out above its
pilot row's by 0.8% (F-0), 7.0% (W-0), 7.7% (W-n-0) and 4.6% (single-turn), and the restated
validity run's within 0.5% of the main F-0 run's and 0.1% of the main restated control's
(the block-1 and block-3 rows of `results/costs.csv`;
`analysis/tests/test_haiku_forecast.py` re-derives them). 1.25 is about three times the
largest of these misses.

Blinding (PREREG §11): pilot rows are read for their cost and input-side token counts only,
never their reasoning tokens (`Run` keeps no reasoning-token field); of each run's meta.json
only its identity, generator config, episode count and episode ids are read. No episode
record is read.

Limits (also in the summary): W-0 and W-n-0 rest on 8 episodes of one template each; a
transport failure's re-run (R8, Exclusions) adds episodes that F does not count; a long wait
inside an episode (rate limits, retries) can let its cache expire; a request over 100,000
tokens is priced at 5 times the rate (none in the free token count of main templates 0-4,
R8); the rows' prices are those of 2026-10-17.

Run: ``uv run python -m analysis.haiku_forecast [--costs PATH] [--results-root DIR]``
(``--no-write`` only prints). ``--costs`` defaults to this checkout's `results/costs.csv`,
and the results root to the folder that holds the costs file. It writes
``results/haiku_forecast/<UTC>/forecast.json``, ``forecast.csv``, ``summary.md`` and
``meta.json``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from common import approval, costs, oslock
from harnesses import registered

REPO_ROOT = Path(__file__).resolve().parent.parent
PREREG_REF = registered.R8_REF

# --- R8's budget and rule (PREREG §17.8; results/decisions.md, 2026-10-18) -----------------
BLOCK = "4-haiku"
BLOCK_MAX_USD = Decimal(180)
"""Block 4-haiku's `max_usd` (its approval line in results/decisions.md)."""
FIT_SHARE = Decimal("0.85")
"""F must be at most this share of R."""
T_MAX = 200
"""R8: T = 200 (luna's main templates 0-199) unless the rule lowers it. Fixed here: the
record's pull request may lower `registered.HAIKU_T`, never this."""
T_STEP = 10
"""T is a multiple of 10 (D7), and repeat 1 runs on the templates divisible by 10 (§2.9)."""
T_VALUES = tuple(range(T_MAX, 0, -T_STEP))
SENSITIVITY_FACTOR = Decimal("1.25")

# --- R8's design ----------------------------------------------------------------------------
MODEL = registered.HAIKU_MODEL
PILOT, VALIDITY, MAIN = (registered.PILOT_EXPERIMENT, registered.VALIDITY_EXPERIMENT,
                         registered.HAIKU_EXPERIMENT)
TASK_CELLS = len(registered.HAIKU_TASK_CELLS)                        # 8
SINGLE_TURN_TASK_CELLS = len(registered.HAIKU_SINGLE_TURN_TASK_CELLS)  # 4, non-recoverable
SINGLE_TURN = registered.HAIKU_SINGLE_TURN_CELL
RESTATED = "F-0-restated"
OPTIONAL = "W-n-0"
LINES = ("F-0", "W-0", OPTIONAL, RESTATED, SINGLE_TURN)
"""F's lines, the main runs in R8's order (each also at repeat 1); W-n-0 only when counted."""
PILOT_VARIANT = {"F-0": "base", "W-0": "base", "W-n-0": "base", SINGLE_TURN: "single_turn"}
"""The variant each pilot cell's episode ids end with (`registered.HAIKU_PILOT_CELLS`)."""
VALIDITY_VARIANTS = ("restated", "withheld")


def episodes(line: str, T: int, repeat: int) -> int:
    """Episodes (prompts, for the single-turn control) of one main run at T: repeat 0 plays
    main templates 0 to T - 1, repeat 1 those divisible by 10 (§2.9), each on all 8 task
    cells (the single-turn control on its 4)."""
    if T <= 0 or T % T_STEP:
        raise ValueError(f"T must be a positive multiple of {T_STEP} (D7), got {T}")
    if repeat not in (0, 1):
        raise ValueError(f"repeat must be 0 or 1, got {repeat}")
    templates = T if repeat == 0 else T // T_STEP
    return templates * (SINGLE_TURN_TASK_CELLS if line == SINGLE_TURN else TASK_CELLS)


@dataclass(frozen=True)
class Run:
    """One run of block 4-haiku: its costs row's spend and input-side token counts, and its
    meta.json's episode count, variant and episodes per task cell."""

    run_id: str
    experiment: str
    cell: str
    variant: str
    task_cells: tuple[tuple[str, int], ...]
    billed_usd: Decimal
    input_tokens: int
    cached_input_tokens: int
    cache_write_tokens: int
    calls_over_100000: int | None
    price_source_date: str
    episodes: int
    costs_line: int
    meta_path: Path
    meta_sha256: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.experiment, self.cell, self.variant)

    @property
    def cached_share(self) -> float | None:
        """The share of this run's input tokens read from the cache."""
        return self.cached_input_tokens / self.input_tokens if self.input_tokens else None


def read_ledger(path: Path) -> tuple[list[dict], str]:
    """Every row of the costs file and the sha256 of the bytes they were parsed from, read
    once under the ledger's lock (as `common.costs.read_rows`), so a row another process
    appends meanwhile is in both or in neither."""
    with oslock.locked(path) as fd:
        data = oslock.read_all(fd)
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
    if reader.fieldnames != costs.COLUMNS:
        raise ValueError(f"unexpected costs.csv header in {path}: {reader.fieldnames}")
    return list(reader), hashlib.sha256(data).hexdigest()


def block_rows(rows: list[dict]) -> list[tuple[int, dict]]:
    """The rows of block 4-haiku, with their line numbers (line 1 is the header): those whose
    notes contain `approval.spend_tag(BLOCK)`, as `approval.block_spend` counts them."""
    tag = approval.spend_tag(BLOCK)
    return [(i, r) for i, r in enumerate(rows, 2) if tag in (r.get("notes") or "")]


def _variant(meta: dict, where: str) -> str:
    """The one variant of a run's episodes: the last part of its episode ids."""
    ids = (meta.get("config") or {}).get("episode_ids") or []
    variants = {str(i).rsplit("/", 1)[-1] for i in ids}
    if len(variants) != 1:
        raise ValueError(f"{where}: expected episodes of one variant, got {sorted(variants)}")
    return variants.pop()


def _task_cells(meta: dict, where: str) -> tuple[tuple[str, int], ...]:
    """A run's planned episodes per task cell, the middle part of its episode ids
    (`<split>-<template>/<task cell>/<variant>`), sorted by task cell."""
    ids = (meta.get("config") or {}).get("episode_ids") or []
    parts = [str(i).split("/") for i in ids]
    bad = [i for i, p in zip(ids, parts, strict=True) if len(p) != 3]
    if bad:
        raise ValueError(f"{where}: episode id {bad[0]!r} is not <split>-<template>/<task "
                         "cell>/<variant>")
    return tuple(sorted(Counter(p[1] for p in parts).items()))


def _calls_over_100000(notes: str) -> int | None:
    """The calls over the 100,000-token price threshold a Haiku costs row's notes report
    (`calls_over_100000=<n>`, `harnesses/DESIGN.md` §13.5); None if they report none."""
    m = re.search(r"(?:^|; )calls_over_100000=(\d+)(?:;|$)", notes)
    return int(m[1]) if m else None


def load_runs(rows: list[dict], results_root: Path) -> list[Run]:
    """Block 4-haiku's runs: each row checked against its run's meta.json, which gives its
    episodes, variant and task cells. Refuses a main-run row of any block or none (the rule
    applies before any main episode), a block-4-haiku row of another experiment, model or
    cell, a meta.json that is missing or does not match its row, and a run that did not play
    every episode it planned."""
    for line, r in enumerate(rows, 2):  # line 1 is the header
        if r["experiment"] == MAIN:
            raise ValueError(
                f"costs.csv line {line} ({r['run_id']}): a main run ({MAIN}) is in the ledger, "
                f"whatever its block tag. R8 fixes W-n-0 and T before any main episode, so the "
                "rule no longer applies; to re-derive the record, pass the ledger as it was "
                "(git show <commit>:results/costs.csv)")
    out = []
    for line, r in block_rows(rows):
        where = f"costs.csv line {line} ({r['run_id']})"
        experiment, cell = r["experiment"], r["cell_or_config"]
        if experiment not in (PILOT, VALIDITY):
            raise ValueError(f"{where}: experiment {experiment!r} is neither {PILOT} nor "
                             f"{VALIDITY}, the only runs of block {BLOCK} before its main runs")
        if registered.model_family(r["model_requested"]) != MODEL:
            raise ValueError(f"{where}: model {r['model_requested']!r} is not {MODEL}")
        meta_path = results_root / experiment / r["run_id"] / "meta.json"
        if not meta_path.is_file():
            raise FileNotFoundError(f"{where}: no meta.json at {meta_path}")
        raw = meta_path.read_bytes()
        meta = json.loads(raw.decode("utf-8"))
        got = (meta.get("run_id"), meta.get("experiment"), meta.get("cell_or_config"))
        if got != (r["run_id"], experiment, cell):
            raise ValueError(f"{where}: {meta_path} is run {got}, not its row's")
        if registered.model_family(meta.get("model_requested") or "") != MODEL:
            raise ValueError(f"{where}: {meta_path} is not a {MODEL} run")
        hashes = (meta.get("config") or {}).get("generator_config_hashes")
        if hashes != [registered.HAIKU_GENERATOR_HASH]:
            raise ValueError(f"{where}: not on the default generator config "
                             f"({registered.HAIKU_GENERATOR_HASH[:12]}), R8's")
        variant = _variant(meta, where)
        if experiment == PILOT:
            if cell not in PILOT_VARIANT or variant != PILOT_VARIANT[cell]:
                raise ValueError(f"{where}: a {cell} pilot of variant {variant} is not one "
                                 f"of R8's pilots ({', '.join(PILOT_VARIANT)})")
        elif cell != "F-0" or variant not in VALIDITY_VARIANTS:
            raise ValueError(f"{where}: a validity run of {cell}, {variant} is not R8's "
                             "(F-0, restated or withheld)")
        n = meta.get("n_episodes_run")
        if not isinstance(n, int) or isinstance(n, bool) or n < 0:
            raise ValueError(f"{where}: {meta_path} has no episode count (n_episodes_run)")
        task_cells = _task_cells(meta, where)
        planned = sum(k for _, k in task_cells)
        if n != planned:
            raise ValueError(
                f"{where}: {meta_path} ran {n} of its {planned} episodes. A run's cost per "
                "episode is taken as the main runs' only when it played every episode it "
                "planned: which episodes a run that stopped early played is not in its "
                "meta.json, and its one costs row cannot be split between them")
        out.append(Run(run_id=r["run_id"], experiment=experiment, cell=cell, variant=variant,
                       task_cells=task_cells, billed_usd=approval.row_spend(r, line),
                       input_tokens=int(r["input_tokens"] or 0),
                       cached_input_tokens=int(r["cached_input_tokens"] or 0),
                       cache_write_tokens=int(r["cache_write_tokens"] or 0),
                       calls_over_100000=_calls_over_100000(r.get("notes") or ""),
                       price_source_date=r["price_source_date"],
                       episodes=n, costs_line=line, meta_path=meta_path,
                       meta_sha256=hashlib.sha256(raw).hexdigest()))
    return out


@dataclass(frozen=True)
class Basis:
    """A line's billed cost per episode (per prompt, for the single-turn control) and the runs
    it is measured on."""

    line: str
    usd_per_episode: Fraction
    source: str
    runs: tuple[str, ...]
    episodes: int


def _pooled(line: str, source: str, runs: list[Run]) -> Basis:
    """The runs' billed cost over their episodes, exact (`Fraction`). Refuses unless the runs
    together play each task cell the line's main runs play equally often (the 8, or the
    single-turn control's 4): their mean is taken as the main runs' with no reweighting."""
    names = ", ".join(r.run_id for r in runs)
    n = sum(r.episodes for r in runs)
    if n <= 0:
        raise ValueError(f"{line}: its runs ({names}) played no episode")
    played: Counter[str] = Counter()
    for r in runs:
        played.update(dict(r.task_cells))
    want = (registered.HAIKU_SINGLE_TURN_TASK_CELLS if line == SINGLE_TURN
            else registered.HAIKU_TASK_CELLS)
    if set(played) != set(want) or len(set(played.values())) != 1:
        got = ", ".join(f"{c} {k}" for c, k in sorted(played.items()))
        raise ValueError(
            f"{line}: its runs ({names}) play the task cells {got}, not each of its main "
            f"runs' {len(want)} task cells equally often. The forecast takes their mean cost "
            "per episode as the main runs', which play every task cell equally; one costs row "
            "per run cannot be reweighted per task cell")
    usd = sum((Fraction(r.billed_usd) for r in runs), Fraction(0))
    return Basis(line, usd / n, source, tuple(r.run_id for r in runs), n)


def _of(runs: list[Run], experiment: str, cell: str, variant: str) -> list[Run]:
    return [r for r in runs if r.key == (experiment, cell, variant)]


def per_episode(runs: list[Run], pilot_only: bool = False) -> dict[str, Basis]:
    """Each line's cost per episode (module docstring, "Which rows feed which line"). Refuses
    unless every pilot is in: R8 forecasts after the pilots. `pilot_only` puts F-0 and the
    restated control on F-0's pilot row even once the restated validity run is in (PREREG
    §17.8's own words; reported, never applied)."""
    pilot = {c: _of(runs, PILOT, c, v) for c, v in PILOT_VARIANT.items()}
    missing = [c for c, rs in pilot.items() if not rs]
    if missing:
        raise ValueError(f"block {BLOCK} has no pilot row of {', '.join(missing)}: R8 makes "
                         "the forecast after the pilots")
    restated = [] if pilot_only else _of(runs, VALIDITY, "F-0", "restated")
    f0, f0_source = (restated, "validity, restated") if restated else (pilot["F-0"], "pilot")
    return {"F-0": _pooled("F-0", f0_source, f0),
            "W-0": _pooled("W-0", "pilot", pilot["W-0"]),
            OPTIONAL: _pooled(OPTIONAL, "pilot", pilot[OPTIONAL]),
            RESTATED: _pooled(RESTATED, f0_source, f0),
            SINGLE_TURN: _pooled(SINGLE_TURN, "pilot", pilot[SINGLE_TURN])}


def forecast_lines(bases: dict[str, Basis], T: int, with_w_n_0: bool,
                   factor: Decimal = Decimal(1)) -> dict[str, dict]:
    """F's lines at T: per main run, its episodes at repeats 0 and 1, its cost per episode
    (× `factor`) and its USD, exact (`Fraction`). W-n-0 is left out unless `with_w_n_0`."""
    out = {}
    for line in LINES:
        if line == OPTIONAL and not with_w_n_0:
            continue
        n0, n1 = episodes(line, T, 0), episodes(line, T, 1)
        per = bases[line].usd_per_episode * Fraction(factor)
        out[line] = {"episodes_repeat_0": n0, "episodes_repeat_1": n1, "usd_per_episode": per,
                     "usd": (n0 + n1) * per}
    return out


def total(bases: dict[str, Basis], T: int, with_w_n_0: bool,
          factor: Decimal = Decimal(1)) -> Fraction:
    """F(T, with or without W-n-0): the billed cost of all main runs at T, both repeats."""
    return sum((x["usd"] for x in forecast_lines(bases, T, with_w_n_0, factor).values()),
               Fraction(0))


def limit_of(R: Decimal) -> Fraction:
    """0.85 R, exact."""
    return Fraction(FIT_SHARE) * Fraction(R)


@dataclass(frozen=True)
class Outcome:
    """What the rule gives: whether W-n-0 runs, T (None: no main run starts, Claude asks the
    researcher), the rule's step that decided, F of the outcome, and every comparison made
    in the rule's order."""

    w_n_0: bool
    T: int | None
    step: int
    F_usd: Fraction | None
    limit_usd: Fraction
    comparisons: tuple[dict, ...]

    @property
    def stop(self) -> bool:
        return self.T is None

    @property
    def margin(self) -> Fraction | None:
        """The factor on every cost per episode at which the outcome's F would equal 0.85 R
        (F is linear in them): above 1, it fits with room; None when no T fits."""
        if self.F_usd is None or self.F_usd <= 0:
            return None
        return self.limit_usd / self.F_usd


def size_rule(bases: dict[str, Basis], R: Decimal,
              factor: Decimal = Decimal(1)) -> Outcome:
    """R8's size rule, steps 1-4 as the module docstring states them, with every cost per
    episode × `factor` (1 for the rule itself; the sensitivity reading only reports another).
    A forecast at exactly 0.85 R fits."""
    limit = limit_of(R)
    made: list[dict] = []

    def fits(T: int, with_w_n_0: bool) -> tuple[bool, Fraction]:
        f = total(bases, T, with_w_n_0, factor)
        made.append({"T": T, "w_n_0": with_w_n_0, "F_usd": f, "fits": f <= limit})
        return f <= limit, f

    ok, f = fits(T_MAX, True)
    if ok:
        return Outcome(True, T_MAX, 1, f, limit, tuple(made))
    ok, f = fits(T_MAX, False)
    if ok:
        return Outcome(False, T_MAX, 2, f, limit, tuple(made))
    for T in T_VALUES[1:]:
        ok, f = fits(T, False)
        if ok:
            return Outcome(False, T, 3, f, limit, tuple(made))
    return Outcome(False, None, 4, None, limit, tuple(made))


@dataclass(frozen=True)
class Forecast:
    costs_path: Path
    costs_sha256: str
    results_root: Path
    runs: tuple[Run, ...]
    bases: dict[str, Basis]
    block_rows: int
    spent_usd: Decimal
    R_usd: Decimal
    outcome: Outcome
    sensitivity: Outcome
    provisional: tuple[str, ...]
    pilot_bases: dict[str, Basis] | None
    """The bases with F-0 and the restated control on F-0's pilot row (`per_episode(...,
    pilot_only=True)`), or None while the rule's bases are those anyway."""
    pilot_basis: Outcome | None
    """What the rule would give on `pilot_bases`: reported, never applied."""
    withheld: Basis | None
    """The withheld validity run's cost per episode (it feeds no line), or None before it."""

    @property
    def limit_usd(self) -> Fraction:
        return limit_of(self.R_usd)

    def runs_of(self, experiment: str, cell: str, variant: str) -> list[Run]:
        return _of(list(self.runs), experiment, cell, variant)


def provisional_reasons(runs: list[Run]) -> tuple[str, ...]:
    """Why a reading is not yet the rule's record: R8 makes the forecast after the pilots and
    both validity runs."""
    out = []
    if not _of(runs, VALIDITY, "F-0", "restated"):
        out.append("the restated validity run is not in the ledger: F-0 and the restated "
                   "control rest on F-0's pilot, and R lacks that run's spend")
    if not _of(runs, VALIDITY, "F-0", "withheld"):
        out.append("the withheld validity run is not in the ledger: R lacks its spend")
    return tuple(out)


def build(costs_path: Path = costs.COSTS_CSV, results_root: Path | None = None) -> Forecast:
    """The forecast and the rule's outcome from the costs file and its runs' meta.json (the
    results root defaults to the folder that holds the costs file)."""
    costs_path = Path(costs_path)
    root = Path(results_root) if results_root is not None else costs_path.resolve().parent
    rows, sha = read_ledger(costs_path)
    runs = load_runs(rows, root)
    bases = per_episode(runs)
    spent = approval.block_spend(BLOCK, rows)
    R = BLOCK_MAX_USD - spent
    pilot_bases = (per_episode(runs, pilot_only=True)
                   if bases["F-0"].source != "pilot" else None)
    withheld = _of(runs, VALIDITY, "F-0", "withheld")
    return Forecast(costs_path=costs_path, costs_sha256=sha, results_root=root,
                    runs=tuple(runs), bases=bases, block_rows=len(block_rows(rows)),
                    spent_usd=spent, R_usd=R, outcome=size_rule(bases, R),
                    sensitivity=size_rule(bases, R, SENSITIVITY_FACTOR),
                    provisional=provisional_reasons(runs), pilot_bases=pilot_bases,
                    pilot_basis=size_rule(pilot_bases, R) if pilot_bases else None,
                    withheld=(_pooled("withheld", "validity, withheld", withheld)
                              if withheld else None))


# --- outputs ---------------------------------------------------------------------------------

def _rel(p: Path) -> str:
    p = Path(p).resolve()
    return p.relative_to(REPO_ROOT).as_posix() if p.is_relative_to(REPO_ROOT) else str(p)


def _f(x: Fraction | Decimal | None) -> float | None:
    return None if x is None else float(x)


def _outcome_json(o: Outcome) -> dict:
    return {"w_n_0_runs": o.w_n_0, "T": o.T, "stop_and_ask": o.stop, "step": o.step,
            "F_usd": _f(o.F_usd), "limit_usd": float(o.limit_usd), "margin": _f(o.margin),
            "comparisons": [{**c, "F_usd": float(c["F_usd"])} for c in o.comparisons]}


def template_check(fc: Forecast) -> dict | None:
    """F-0's restated validity cost per episode (20 templates) over its pilot's (pilot
    template 0): a check of the pilot template, never applied. None before the validity run."""
    restated = fc.runs_of(VALIDITY, "F-0", "restated")
    if not restated:
        return None
    val = _pooled("F-0", "validity, restated", restated).usd_per_episode
    pilot = _pooled("F-0", "pilot", fc.runs_of(PILOT, "F-0", "base")).usd_per_episode
    return {"f0_pilot_usd_per_episode": float(pilot),
            "f0_validity_restated_usd_per_episode": float(val),
            "validity_over_pilot": float(val / pilot) if pilot else None}


def withheld_per_episode(fc: Forecast) -> Fraction | None:
    return fc.withheld.usd_per_episode if fc.withheld else None


def table_rows(fc: Forecast) -> list[dict]:
    """forecast.csv: F at every T and with or without W-n-0, on the rule's basis and on the
    sensitivity reading's, against 0.85 R."""
    out = []
    for basis, factor in (("rule", Decimal(1)), ("sensitivity_x1.25", SENSITIVITY_FACTOR)):
        for T in T_VALUES:
            for with_w in (True, False):
                lines = forecast_lines(fc.bases, T, with_w, factor)
                f = sum((x["usd"] for x in lines.values()), Fraction(0))
                row = {"basis": basis, "T": T, "w_n_0": with_w,
                       "episodes_per_harness_cell": episodes("F-0", T, 0) + episodes("F-0", T, 1),
                       "single_turn_prompts": (episodes(SINGLE_TURN, T, 0)
                                               + episodes(SINGLE_TURN, T, 1))}
                for line in LINES:
                    row[f"usd_{line}"] = lines[line]["usd"] if line in lines else Fraction(0)
                row.update(usd_total=f, limit_usd=fc.limit_usd, fits=f <= fc.limit_usd)
                out.append(row)
    return out


CSV_FIELDS = ["basis", "T", "w_n_0", "episodes_per_harness_cell", "single_turn_prompts",
              *(f"usd_{line}" for line in LINES), "usd_total", "limit_usd", "fits"]


def _csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: (f"{v:.6f}" if isinstance(v, (Decimal, Fraction)) else v)
                    for k, v in r.items()})
    return buf.getvalue()


def to_json(fc: Forecast) -> dict:
    feeds = {r.run_id: [b.line for b in fc.bases.values() if r.run_id in b.runs]
             for r in fc.runs}
    o = fc.outcome
    lines = forecast_lines(fc.bases, o.T, o.w_n_0) if not o.stop else {}
    s = fc.sensitivity
    w = withheld_per_episode(fc)
    return {
        "prereg": PREREG_REF,
        "status": "provisional" if fc.provisional else "complete",
        "provisional_reasons": list(fc.provisional),
        "inputs": {
            "costs_csv": _rel(fc.costs_path), "costs_csv_sha256": fc.costs_sha256,
            "results_root": _rel(fc.results_root),
            "runs": [{"run_id": r.run_id, "experiment": r.experiment, "cell": r.cell,
                      "variant": r.variant, "costs_line": r.costs_line,
                      "billed_usd": float(r.billed_usd), "episodes": r.episodes,
                      "input_tokens": r.input_tokens,
                      "cached_input_tokens": r.cached_input_tokens,
                      "cache_write_tokens": r.cache_write_tokens,
                      "calls_over_100000": r.calls_over_100000,
                      "price_source_date": r.price_source_date,
                      "cached_share": r.cached_share, "feeds": feeds[r.run_id],
                      "meta_json": _rel(r.meta_path), "meta_json_sha256": r.meta_sha256}
                     for r in fc.runs]},
        "block": {"name": BLOCK, "max_usd": float(BLOCK_MAX_USD), "rows": fc.block_rows,
                  "spent_usd": float(fc.spent_usd), "R_usd": float(fc.R_usd),
                  "fit_share": float(FIT_SHARE), "limit_usd": float(fc.limit_usd)},
        "per_episode": {k: {"usd": float(b.usd_per_episode), "source": b.source,
                            "runs": list(b.runs), "episodes": b.episodes}
                        for k, b in fc.bases.items()},
        "checks": {"template": template_check(fc),
                   "withheld_usd_per_episode": _f(w)},
        "design": {"T_max": T_MAX, "T_step": T_STEP, "task_cells": TASK_CELLS,
                   "single_turn_task_cells": SINGLE_TURN_TASK_CELLS, "lines": list(LINES),
                   "optional_line": OPTIONAL},
        "outcome": {**_outcome_json(o),
                    "runs": {k: {**v, "usd_per_episode": float(v["usd_per_episode"]),
                                 "usd": float(v["usd"])} for k, v in lines.items()}},
        "sensitivity": {"factor": float(SENSITIVITY_FACTOR), "applied": False,
                        "F_200_with_w_n_0_usd": float(total(fc.bases, T_MAX, True,
                                                            SENSITIVITY_FACTOR)),
                        "F_200_without_w_n_0_usd": float(total(fc.bases, T_MAX, False,
                                                               SENSITIVITY_FACTOR)),
                        "rule_would_give": _outcome_json(s),
                        "note": "reported only: the rule's outcome is `outcome`"},
        "pilot_basis": _pilot_basis_json(fc),
    }


BASIS_AUTHORITY = ("results/decisions.md, 2026-10-18, item 2: the forecast from the pilots' "
                   "and validity runs' costs (PREREG §17.8: from the pilots' costs.csv rows)")


def _pilot_basis_json(fc: Forecast) -> dict | None:
    """F and the rule's outcome with F-0 and the restated control on F-0's pilot row: reported,
    never applied. None while the rule's bases are those anyway."""
    if fc.pilot_bases is None or fc.pilot_basis is None:
        return None
    return {"applied": False, "authority_for_the_rule_basis": BASIS_AUTHORITY,
            "f0_usd_per_episode": float(fc.pilot_bases["F-0"].usd_per_episode),
            "F_200_with_w_n_0_usd": float(total(fc.pilot_bases, T_MAX, True)),
            "F_200_without_w_n_0_usd": float(total(fc.pilot_bases, T_MAX, False)),
            "rule_would_give": _outcome_json(fc.pilot_basis),
            "note": "reported only: the rule's outcome is `outcome`"}


def _usd(x: Fraction | Decimal) -> str:
    """USD to the cent, rounded from the exact value (half to even), never through a float."""
    return f"{x:,.2f}"


def _what(o: Outcome) -> str:
    if o.stop:
        return "no T ≥ 10 fits: no main run starts, and Claude asks the researcher"
    return f"W-n-0 {'runs' if o.w_n_0 else 'does not run'}, T = {o.T}"


def _decisive(o: Outcome) -> str:
    """The rule's last comparison and the one before it, to 6 decimals."""
    def one(c: dict) -> str:
        return (f"F(T = {c['T']}, {'with' if c['w_n_0'] else 'without'} W-n-0) = "
                f"{c['F_usd']:.6f} {'≤' if c['fits'] else '>'} {o.limit_usd:.6f}")
    return "; ".join(one(c) for c in o.comparisons[-2:])


def _pilot_basis_lines(fc: Forecast) -> list[str]:
    """The summary's report of F with F-0 and the restated control on F-0's pilot row, once
    the rule's bases put them on the restated validity run."""
    if fc.pilot_bases is None or fc.pilot_basis is None:
        return []
    o, p = fc.outcome, fc.pilot_basis
    return [
        "", "## F-0's basis (reported only: it does not change the outcome)", "",
        ("- The rule costs F-0 and the restated control from the restated validity run, as "
         "`results/decisions.md` (2026-10-18, item 2) has it: the forecast \"from the pilots' "
         "and validity runs' costs\". PREREG §17.8 says \"from the pilots' `costs.csv` rows\", "
         "and this script's choice was committed after both validity runs' rows were in the "
         "ledger (module docstring)."),
        (f"- On F-0's pilot row instead ({fc.pilot_bases['F-0'].usd_per_episode:.6f} "
         f"USD per episode, against the validity run's "
         f"{fc.bases['F-0'].usd_per_episode:.6f}): F(T = {T_MAX}, with W-n-0) = "
         f"{_usd(total(fc.pilot_bases, T_MAX, True))}, without = "
         f"{_usd(total(fc.pilot_bases, T_MAX, False))}; on that basis the rule would give: "
         f"{_what(p)} (step {p.step})."
         + (" The same as the outcome." if (p.w_n_0, p.T) == (o.w_n_0, o.T) else
            " The outcome stays the rule's, above.")),
    ]


def summary_lines(fc: Forecast) -> list[str]:
    o, s, limit = fc.outcome, fc.sensitivity, fc.limit_usd
    f_with, f_without = total(fc.bases, T_MAX, True), total(fc.bases, T_MAX, False)
    lines = [
        "# claude-haiku-5-5's size rule (PREREG §17.8, amendment R8): W-n-0 and T",
        "",
        (f"Billed estimate from block `{BLOCK}`'s rows of `{_rel(fc.costs_path)}` (sha256 "
         f"`{fc.costs_sha256[:12]}…`), by `uv run python -m analysis.haiku_forecast`. "
         "Forecasts, not measurements. Every T is in `forecast.csv`, every number in "
         "`forecast.json`."),
        "",
    ]
    if fc.provisional:
        lines += [("**Provisional, not the rule's record.** R8 makes the forecast after the "
                   "pilots and both validity runs, and here "
                   + "; ".join(fc.provisional) + "."), ""]
    what = _what(o)
    lines += ["## The rule's outcome", "",
              f"**{what[0].upper()}{what[1:]}** (step {o.step} of the rule: {_decisive(o)}).",
              ""]
    lines += [
        (f"- R = ${_usd(BLOCK_MAX_USD)} − ${_usd(fc.spent_usd)} (block `{BLOCK}`'s spend, "
         f"{fc.block_rows} rows) = ${_usd(fc.R_usd)}; 0.85 R = ${_usd(limit)}."),
        "",
        "| F | USD | ≤ 0.85 R? |",
        "|---|---|---|",
        f"| T = {T_MAX}, with W-n-0 | {_usd(f_with)} | {'yes' if f_with <= limit else 'no'} |",
        (f"| T = {T_MAX}, without W-n-0 | {_usd(f_without)} | "
         f"{'yes' if f_without <= limit else 'no'} |"),
    ]
    if o.step == 3:
        lines.append(f"| T = {o.T}, without W-n-0 (the largest T that fits) | {_usd(o.F_usd)} "
                     "| yes |")
    if o.step == 4:
        f10 = total(fc.bases, T_STEP, False)
        lines.append(f"| T = {T_STEP}, without W-n-0 | {_usd(f10)} | no |")
    if o.stop:
        record = ("Record (R8): F, R and the outcome go into `results/decisions.md`; no main "
                  "run starts, and Claude asks the researcher.")
    else:
        record = ("Record (R8): F, R, the outcome and this script's commit go into "
                  "`results/decisions.md` before any main episode, and the pull request that "
                  f"records them sets `HAIKU_T` = {o.T}"
                  + ("." if o.w_n_0 else ", and `HAIKU_CELLS` without W-n-0, which is "
                     "reported as \"pre-registered, not run (budget)\"."))
    lines += ["", record]
    if not o.stop:
        lines += ["", f"## The outcome's main runs (T = {o.T})", "",
                  "| Run | Episodes, repeat 0 | Repeat 1 | USD per episode | USD |",
                  "|---|---|---|---|---|"]
        for line, v in forecast_lines(fc.bases, o.T, o.w_n_0).items():
            unit = " (prompts)" if line == SINGLE_TURN else ""
            lines.append(f"| {line}{unit} | {v['episodes_repeat_0']:,} | "
                         f"{v['episodes_repeat_1']:,} | {v['usd_per_episode']:.6f} | "
                         f"{_usd(v['usd'])} |")
        lines.append(f"| **F** | | | | **{_usd(o.F_usd)}** |")
    lines += ["", "## Cost per episode", "",
              "| Line | USD per episode | Basis | Episodes in the basis | Runs |",
              "|---|---|---|---|---|"]
    for b in fc.bases.values():
        lines.append(f"| {b.line} | {b.usd_per_episode:.6f} | {b.source} | "
                     f"{b.episodes:,} | {', '.join(f'`{r}`' for r in b.runs)} |")
    tc, w = template_check(fc), withheld_per_episode(fc)
    counted = [r.calls_over_100000 for r in fc.runs if r.calls_over_100000 is not None]
    unreported = len(fc.runs) - len(counted)
    over = (f"the block's rows report {sum(counted)} such calls"
            + (f" ({unreported} rows report no count)" if unreported else ""))
    dates = sorted({r.price_source_date for r in fc.runs})
    lines.append("")
    if tc:
        lines.append(f"- Check of pilot template 0 (not applied): F-0's restated validity cost "
                     f"per episode, on 20 templates, is {tc['validity_over_pilot']:.3f} times "
                     "its pilot's.")
    if w is not None:
        lines.append(f"- The withheld validity run: {w:.6f} USD per episode. It feeds no "
                     "line (its episodes lack the fact) and counts toward the block's spend.")
    shares = "; ".join(f"{r.experiment.removeprefix('persistgym_')} {r.cell}"
                       f"{'' if r.variant in ('base', 'single_turn') else ' ' + r.variant}: "
                       f"{(r.cached_share or 0):.0%} read, {r.cache_write_tokens:,} written"
                       for r in fc.runs)
    lines += [f"- Input from the cache, per run: {shares}.",
              ("- Cold and warm caches (module docstring): F-0's pilot, W-n-0's pilot and the "
               "restated validity run played their episodes cold, as the main runs will; W-0's "
               "pilot followed F-0's on the same episodes with F-0's system prompt, so its calls "
               "before the first eviction may have read F-0's cache, and its estimate may be a "
               "little low."),
              "", "## Sensitivity (reported only: it does not change the outcome)", "",
              (f"- Every cost per episode × {SENSITIVITY_FACTOR}: F(T = {T_MAX}, with W-n-0) = "
               f"{_usd(total(fc.bases, T_MAX, True, SENSITIVITY_FACTOR))}, without = "
               f"{_usd(total(fc.bases, T_MAX, False, SENSITIVITY_FACTOR))}; on that basis the "
               f"rule would give: {_what(s)} (step {s.step})."
               + (" The same as the outcome." if (s.w_n_0, s.T) == (o.w_n_0, o.T) else
                  " The outcome stays the rule's, above.")),
              ("- Margin: " + (f"the outcome's F would still fit 0.85 R with every cost per "
                               f"episode up to × {o.margin:.3f}." if o.margin is not None
                               else "none (no T fits).")),
              ("- Why × 1.25: on luna, on the same episodes, each main run's cost per episode "
               "came out 0.8% to 7.7% above its pilot basis (module docstring)."),
              *_pilot_basis_lines(fc),
              "", "## Limits", "",
              (f"- W-0 and W-n-0 rest on {fc.bases['W-0'].episodes} and "
               f"{fc.bases[OPTIONAL].episodes} pilot episodes, the single-turn control on "
               f"{fc.bases[SINGLE_TURN].episodes} pilot prompts; F-0 and the restated control "
               f"on {fc.bases['F-0'].episodes} episodes ({fc.bases['F-0'].source})."),
              ("- A transport failure's re-run (R8, Exclusions) adds episodes F does not "
               "count; a long wait inside an episode (rate limits, retries) can let its cache "
               "expire, which costs more."),
              (f"- A request over 100,000 tokens is priced at 5 times the rate: {over}. The "
               "free token count found none on main templates 0-4 (R8), and the main runs "
               "play other templates."),
              (f"- Prices as the rows were priced ({', '.join(dates)}); billed equals list on "
               "Anthropic, but for refusals Anthropic does not bill."),
              "", "## What it does not show", "",
              ("- Nothing about Haiku's success or any H1 or H3 quantity: it reads costs and "
               "episode counts only (pilot blinding, PREREG §11)."),
              ("- Not a comparison of models or providers: costs are in each provider's own "
               "tokens and prices (R8)."),
              "- Not a measurement of the main runs' cost: the main runs measure that.",
              ("- Not a guarantee that the main runs stay within the block: each run still "
               "stops at its planned spend, and Claude stops and asks the researcher before "
               f"block spend would pass ${_usd(BLOCK_MAX_USD)} (R8).")]
    return lines


def write(out_dir: Path, run_id: str, started: str, fc: Forecast) -> Path:
    from common import runmeta

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "forecast.json").write_text(
        json.dumps(to_json(fc), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "forecast.csv").write_text(_csv(table_rows(fc)), encoding="utf-8", newline="")
    (out_dir / "summary.md").write_text("\n".join(summary_lines(fc)) + "\n", encoding="utf-8",
                                        newline="\n")
    config = {"prereg": PREREG_REF,
              "inputs": {"costs_csv": _rel(fc.costs_path), "costs_csv_sha256": fc.costs_sha256,
                         "results_root": _rel(fc.results_root),
                         "meta_json": {_rel(r.meta_path): r.meta_sha256 for r in fc.runs}},
              "rule": {"block": BLOCK, "max_usd": str(BLOCK_MAX_USD),
                       "fit_share": str(FIT_SHARE), "T_max": T_MAX, "T_step": T_STEP},
              "design": {"task_cells": TASK_CELLS,
                         "single_turn_task_cells": SINGLE_TURN_TASK_CELLS,
                         "lines": list(LINES), "optional_line": OPTIONAL},
              "sensitivity_factor": str(SENSITIVITY_FACTOR)}
    o = fc.outcome
    return runmeta.write_meta(
        out_dir, experiment="haiku_forecast", run_id=run_id, cell_or_config="r8_size_rule",
        config=config, model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
        repeat_index=None, seeds=None, started_utc=started, finished_utc=runmeta.utc_now(),
        exit_reason="completed", tokens=None, cost_usd=0.0, raw_transcript_path=None,
        status="provisional" if fc.provisional else "complete",
        outcome={"w_n_0_runs": o.w_n_0, "T": o.T, "stop_and_ask": o.stop, "step": o.step},
        outputs=["forecast.json", "forecast.csv", "summary.md"], paid_calls=0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--costs", type=Path, default=costs.COSTS_CSV,
                    help="the costs ledger (default: this checkout's results/costs.csv)")
    ap.add_argument("--results-root", type=Path, default=None,
                    help="where the runs' meta.json are (default: the costs file's folder)")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="default: results/haiku_forecast/<UTC>/")
    ap.add_argument("--no-write", action="store_true", help="print only")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    started = datetime.now(UTC)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    fc = build(args.costs, args.results_root)
    print("\n".join(summary_lines(fc)))
    if not args.no_write:
        out = args.out_dir or REPO_ROOT / "results" / "haiku_forecast" / run_id
        meta = write(out, run_id, started.isoformat(timespec="seconds"), fc)
        print(f"\nwrote {out} ({meta.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
