"""Committed cost model for the persistgym budget (PLAN.md §12 and amendment A1, §16).

Every number is derived from the committed inputs in ``analysis/data/``:

- ``arc_gemini38flash_high_public.csv``: the published per-game Gemini 3.8 Flash high-effort
  public-set runs (docs/background.md §4), in ARC's no-cache list accounting.
- ``prices.csv``: token prices (PLAN.md §12, docs/background.md §6), checked 2026-09-30.
- ``parameters.csv``: every other assumption, one row each, with its source.

``plan_a1_reference.csv`` holds the numbers stated in PLAN.md §16 and in the 2026-09-30
low-spend review. It is read only to build the final comparison table and never feeds a
computation.

What it produces (printed, and written to ``results/cost_model/<run_id>/`` with ``meta.json``):

(a) ARC path (phase 1b) cost for all 15 four-of-six draws, S1 and S2 at the S0/S4 midpoint, in
    every billing case, and the number of draws above the $900 cap;
(b) held-out StateCarry costs (phase 2) for every undrawn pair plus VC33 or RE86;
(c) PersistGym per-episode costs for luna and sol (Flex and standard tier, with and without
    OpenAI cache writes) at 1k/2k/3k output tokens per call;
(d) totals by phase and payee for the three ARC billing cases of amendment §16.1;
(e) the cost of each staged approval block of amendment §16.2;
plus a comparison with the numbers stated in the plan.

Run: ``uv run python -m analysis.cost_model`` (``--no-write`` only prints).
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import math
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILES = ("arc_gemini38flash_high_public.csv", "prices.csv", "parameters.csv")
REFERENCE_FILE = "plan_a1_reference.csv"

GEMINI, LUNA, SOL = "gemini-3.8-flash", "gpt-6-luna", "gpt-6.1-sol"

# The three ARC billing cases of amendment §16.1, plus Flex applied to the no-cache list costs,
# which some of the plan's numbers use.
ARC_CASES = ("flex_cached", "standard_cached", "list_nocache")
ALL_ARC_CASES = (*ARC_CASES, "flex_nocache")
ARC_CASE_LABELS = {
    "flex_cached": "Gemini Flex, billed with implicit caching",
    "standard_cached": "Gemini standard tier with implicit caching",
    "list_nocache": "ARC's no-cache list accounting (published costs)",
    "flex_nocache": "Gemini Flex applied to the no-cache list costs",
}
PAYEES = ("Google", "OpenAI", "ARC Prize", "GPU")
PHASES = ("0", "1a", "1b", "2")
B1, B2, B3, B4 = "1 pilots", "2 seed-1 S0+S4", "3 commitment", "4 phase 2"
BLOCKS = (B1, B2, B3, B4)
SWEEP_ITEMS = ("luna sweep", "luna control prompts", "sol H2 core")


# --------------------------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Price:
    """USD per million tokens."""

    input: float
    cached: float
    output: float


@dataclass(frozen=True)
class Inputs:
    games: pd.DataFrame
    prices: dict[str, Price]
    params: dict[str, float | str]

    def num(self, name: str) -> float:
        value = self.params[name]
        if isinstance(value, str):
            raise TypeError(f"parameter {name!r} is not numeric: {value!r}")
        return value

    def names(self, name: str) -> list[str]:
        return [x for x in str(self.params[name]).split(";") if x]


def load_parameters(path: Path) -> dict[str, float | str]:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    out: dict[str, float | str] = {}
    for name, value in zip(df["name"], df["value"], strict=True):
        if name in out:
            raise ValueError(f"duplicate parameter {name!r}")
        try:
            out[name] = float(value)
        except ValueError:
            out[name] = value
    return out


def load_inputs(data_dir: Path = DATA_DIR) -> Inputs:
    games = pd.read_csv(data_dir / "arc_gemini38flash_high_public.csv")
    prices = {}
    for row in pd.read_csv(data_dir / "prices.csv").itertuples(index=False):
        if row.tier == "standard":
            prices[row.model] = Price(float(row.input_usd_per_m), float(row.cached_usd_per_m),
                                      float(row.output_usd_per_m))
    return Inputs(games, prices, load_parameters(data_dir / "parameters.csv"))


def input_hashes(data_dir: Path = DATA_DIR) -> dict[str, str]:
    return {f: hashlib.sha256((data_dir / f).read_bytes()).hexdigest() for f in INPUT_FILES}


# --------------------------------------------------------------------------------------------
# ARC (Gemini 3.8 Flash) costs
# --------------------------------------------------------------------------------------------
def cache_billed_factor(input_tokens: float, output_tokens: float, cached_share: float,
                        price: Price) -> float:
    """Billed cost with implicit caching, as a fraction of the no-cache list cost."""
    listed = input_tokens * price.input + output_tokens * price.output
    billed = (input_tokens * ((1 - cached_share) * price.input + cached_share * price.cached)
              + output_tokens * price.output)
    return billed / listed


def arc_case_factors(inp: Inputs) -> dict[str, dict[str, float]]:
    """Multiplier on the published (no-cache list) S0 and S4 run costs, per billing case.

    The cached shares measured on the published runs (17% Standard, 53% Adapter) and the
    per-game token totals give one cache-billing factor per harness, applied to every game.
    """
    g = inp.prices[GEMINI]
    flex = 1 - inp.num("flex_discount")
    f_std = cache_billed_factor(inp.num("arc_std_input_tokens_per_game"),
                                inp.num("arc_std_output_tokens_per_game"),
                                inp.num("arc_std_cached_share"), g)
    f_pa = cache_billed_factor(inp.num("arc_pa_input_tokens_per_game"),
                               inp.num("arc_pa_output_tokens_per_game"),
                               inp.num("arc_pa_cached_share"), g)
    return {
        "list_nocache": {"S0": 1.0, "S4": 1.0},
        "flex_nocache": {"S0": flex, "S4": flex},
        "standard_cached": {"S0": f_std, "S4": f_pa},
        "flex_cached": {"S0": f_std * flex, "S4": f_pa * flex},
    }


def eligible_games(inp: Inputs) -> list[str]:
    """PLAN §8.3: both published high runs cost at most $60 and the gap is at least 20."""
    g = inp.games
    cap, gap = inp.num("arc_eligible_max_cost_usd"), inp.num("arc_eligible_min_gap")
    mask = (g.std_cost_usd <= cap) & (g.pa_cost_usd <= cap) & (g.gap >= gap)
    return sorted(g.loc[mask, "game"])


def arc_run_costs(inp: Inputs) -> pd.DataFrame:
    """Cost of one run per game, config and billing case.

    S0 is the published Standard run and S4 the published Adapter run (times the case factor).
    S1, S2 and S0+StateCarry (SC) are costed at the S0/S4 midpoint. For SC this equals the
    plan's own "every held-out run costs the game's mean published run".
    """
    rows = []
    for case, f in arc_case_factors(inp).items():
        for g in inp.games.itertuples(index=False):
            s0, s4 = g.std_cost_usd * f["S0"], g.pa_cost_usd * f["S4"]
            mid = (s0 + s4) / 2
            rows.append({"case": case, "game": g.game, "S0": s0, "S1": mid, "S2": mid,
                         "S4": s4, "SC": mid})
    return pd.DataFrame(rows).set_index(["case", "game"])


def arc_draws(inp: Inputs, run_costs: pd.DataFrame) -> pd.DataFrame:
    """(a) Phase-1b path cost for every draw of 4 of the 6 eligible games, per billing case."""
    elig = eligible_games(inp)
    k, seeds = int(inp.num("arc_path_games")), int(inp.num("arc_seeds"))
    rows = []
    for i, drawn in enumerate(itertools.combinations(elig, k), start=1):
        undrawn = tuple(x for x in elig if x not in drawn)
        for case in ALL_ARC_CASES:
            c = run_costs.loc[case].loc[list(drawn)]
            seed1_s0s4 = float((c.S0 + c.S4).sum())
            seed1_path = float((c.S0 + c.S1 + c.S2 + c.S4).sum())
            path = seeds * seed1_path
            rows.append({"draw": i, "drawn": "+".join(drawn), "undrawn": "+".join(undrawn),
                         "case": case, "seed1_s0s4": seed1_s0s4, "seed1_path": seed1_path,
                         "path_1b": path, "remainder_1b": path - seed1_s0s4})
    return pd.DataFrame(rows)


def arc_heldout(inp: Inputs, run_costs: pd.DataFrame, draws: pd.DataFrame) -> pd.DataFrame:
    """(b) Held-out runs: undrawn pair + third game x {S0, S4, S0+StateCarry} x seeds."""
    seeds = int(inp.num("arc_seeds"))
    rows = []
    for d in draws.loc[draws.case == ALL_ARC_CASES[0]].itertuples(index=False):
        for third in inp.names("arc_heldout_third_candidates"):
            games = [*d.undrawn.split("+"), third]
            for case in ALL_ARC_CASES:
                c = run_costs.loc[case].loc[games]
                rows.append({"draw": d.draw, "undrawn": d.undrawn, "third": third, "case": case,
                             "heldout": seeds * float((c.S0 + c.S4 + c.SC).sum())})
    return pd.DataFrame(rows)


def arc_pooled_usd_per_action(inp: Inputs) -> dict[str, float]:
    """Published $/action pooled over the eligible games (no-cache list)."""
    g = inp.games.set_index("game").loc[eligible_games(inp)]
    return {"S0": g.std_cost_usd.sum() / g.std_actions.sum(),
            "S4": g.pa_cost_usd.sum() / g.pa_actions.sum()}


def arc_pilot_actions(inp: Inputs) -> dict[str, int]:
    """Truncated pilot (§16.3). S1 runs until its first compaction plus 5 turns."""
    to_compaction = math.ceil(inp.num("arc_compaction_trigger_tokens")
                              / inp.num("arc_turn_growth_tokens"))
    return {"S0": int(inp.num("arc_pilot_actions_s0")),
            "S1": to_compaction + int(inp.num("arc_pilot_turns_after_compaction_s1")),
            "S2": int(inp.num("arc_pilot_actions_s2")),
            "S4": int(inp.num("arc_pilot_actions_s4"))}


def arc_pilot_costs(inp: Inputs) -> pd.DataFrame:
    """Truncated ARC pilot per config and billing case, at the pooled published $/action."""
    per_action = arc_pooled_usd_per_action(inp)
    actions = arc_pilot_actions(inp)
    rows = []
    for case, f in arc_case_factors(inp).items():
        c0, c4 = per_action["S0"] * f["S0"], per_action["S4"] * f["S4"]
        rate = {"S0": c0, "S1": (c0 + c4) / 2, "S2": (c0 + c4) / 2, "S4": c4}
        for cfg in ("S0", "S1", "S2", "S4"):
            rows.append({"case": case, "config": cfg, "actions": actions[cfg],
                         "usd_per_action": rate[cfg], "usd": actions[cfg] * rate[cfg]})
    return pd.DataFrame(rows)


def gemini_probe_cost(inp: Inputs) -> float:
    """Gemini acceptance and Flex latency probe (§16.2 block 1). Output per call is the
    published Standard average (reasoning + visible); no caching."""
    g = inp.prices[GEMINI]
    out = (inp.num("arc_std_reasoning_tokens_per_action")
           + inp.num("arc_std_visible_tokens_per_action"))
    big = (inp.num("arc_std_input_tokens_per_action") * g.input + out * g.output) / 1e6
    small = (inp.num("arc_frame_tokens") * g.input + out * g.output) / 1e6
    flex = 1 - inp.num("flex_discount")
    return (inp.num("gemini_probe_flex_calls") * big * flex
            + inp.num("gemini_probe_standard_calls") * big
            + inp.num("gemini_probe_small_calls") * small)


# --------------------------------------------------------------------------------------------
# PersistGym (OpenAI) costs
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class CellSpec:
    history: str  # "full", "window" (drop oldest at W) or "summary" (compact at W)
    replay: bool  # earlier turns' reasoning replayed as input (reasoning.context=all_turns)
    digest: bool = False  # StateCarry: +digest visible tokens per turn, kept in history


PG_CELLS: dict[str, CellSpec] = {
    "F-r": CellSpec("full", True),
    "F-0": CellSpec("full", False),
    "W-n-r": CellSpec("window", True),
    "W-n-0": CellSpec("window", False),
    "Sum-n-r": CellSpec("summary", True),
    "Sum-n-0": CellSpec("summary", False),
    "W-0": CellSpec("window", False),
    "Sum-0-r": CellSpec("summary", True),
    "StateCarry": CellSpec("summary", False, digest=True),
}


@dataclass(frozen=True)
class Call:
    input: float
    cached: float
    output: float


def simulate_episode(spec: CellSpec, output_tokens: float, inp: Inputs) -> list[Call]:
    """Token accounting for one PersistGym episode under the PLAN §12 assumptions.

    - 28 agent calls; the carried history (observations + visible replies) grows linearly so
      that it reaches 64k tokens at the last call under full history.
    - Each call outputs ``output_tokens``, of which ``pg_visible_tokens_per_call`` are visible;
      the rest is reasoning, which replay cells carry forward as input.
    - A call whose prefix is unchanged since the previous call has ``pg_cached_share`` of its
      input cached (the first call too: its prefix is the system prompt and task instructions,
      shared across episodes).
    - Window cells send at most W tokens and lose the whole cache once the window is full
      (drop-oldest shifts the prefix every call; no system-prompt cache is kept).
    - Summary cells (and StateCarry) make one extra summary call (input = the stable prefix,
      output = reasoning + summary) when the context would exceed W, then restart from the
      summary; that first call after a compaction is uncached.
    - Notes on/off does not change the token accounting here.
    """
    n = int(inp.num("pg_calls_per_episode"))
    k = inp.num("pg_cached_share")
    window = inp.num("pg_window_tokens")
    summary = inp.num("pg_summary_tokens")
    digest = inp.num("pg_digest_tokens") if spec.digest else 0.0
    growth = inp.num("pg_context_max_tokens") / n + digest
    out = output_tokens + digest
    reasoning = max(output_tokens - inp.num("pg_visible_tokens_per_call"), 0.0)

    calls: list[Call] = []
    history = replayed = 0.0
    for _ in range(n):
        history += growth
        ctx = history + replayed
        if ctx > window and spec.history == "window":
            calls.append(Call(window, 0.0, out))
        elif ctx > window and spec.history == "summary":
            prefix = ctx - growth
            calls.append(Call(prefix, k * prefix, reasoning + summary))
            history, replayed = summary + growth, 0.0
            calls.append(Call(history, 0.0, out))
        else:
            calls.append(Call(ctx, k * ctx, out))
        if spec.replay:
            replayed += reasoning
    return calls


def openai_call_cost(call: Call, price: Price, flex_mult: float, write_mult: float) -> float:
    uncached = call.input - call.cached
    return (uncached * price.input * write_mult + call.cached * price.cached
            + call.output * price.output) / 1e6 * flex_mult


# --------------------------------------------------------------------------------------------
# Scenarios, line items and aggregation
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Scenario:
    name: str = "central"
    arc_case: str = "flex_cached"
    openai_flex: bool = True
    output_tokens: int = 1000
    luna_cells: str = "all"  # "all" (8 cells) or "replay_off" (4 cells)
    replicates: bool = True  # PLAN §5: 2 repeats on a 10% subset of template x cell
    rerun_rate: float | None = None  # None = arc_rerun_rate_moderate
    rerun_heldout: bool = True  # apply the §8.3 re-run rule to held-out runs too
    cache_writes: bool = True
    cap_1a: bool = False  # size the 1a sweep down so phase 1a stays within its cap (A1 §16.1)
    draw: int | None = None  # draw index; None = mean over the 15 draws
    third: str | None = None  # third held-out game; None = mean over the candidates


# Central case of amendment §16.1: 1k output per call, 8-cell luna, mean draw, moderate
# re-runs, OpenAI cache writes, OpenAI on Flex.
CENTRAL = Scenario()

Item = tuple[str, str, str, str, float]  # phase, block, payee, item, usd


class CostModel:
    def __init__(self, inp: Inputs | None = None):
        self.inp = inp or load_inputs()
        self.factors = arc_case_factors(self.inp)
        self.eligible = eligible_games(self.inp)
        self.run_costs = arc_run_costs(self.inp)
        self.draws = arc_draws(self.inp, self.run_costs)
        self.heldout = arc_heldout(self.inp, self.run_costs, self.draws)
        self.pilot = arc_pilot_costs(self.inp)
        self.gemini_probe = gemini_probe_cost(self.inp)
        self._draw_rows = {(r.draw, r.case): r for r in self.draws.itertuples(index=False)}
        self._heldout_usd = {(r.draw, r.third, r.case): r.heldout
                             for r in self.heldout.itertuples(index=False)}
        self.pilot_by_case = self.pilot.groupby("case").usd.sum().to_dict()
        self._episodes: dict[tuple, float] = {}
        self._blocks: pd.DataFrame | None = None

    # ---- PersistGym ----------------------------------------------------------------------
    def price(self, model: str) -> Price:
        return self.inp.prices[model]

    def _mults(self, flex: bool, writes: bool) -> tuple[float, float]:
        flex_mult = (1 - self.inp.num("flex_discount")) if flex else 1.0
        write_mult = self.inp.num("openai_cache_write_multiplier") if writes else 1.0
        return flex_mult, write_mult

    def calls_cost(self, model: str, calls: Iterable[Call], flex: bool, writes: bool) -> float:
        fm, wm = self._mults(flex, writes)
        return sum(openai_call_cost(c, self.price(model), fm, wm) for c in calls)

    def episode(self, model: str, cell: str, output_tokens: float, flex: bool = True,
                writes: bool = True) -> float:
        key = (model, cell, output_tokens, flex, writes)
        if key not in self._episodes:
            calls = simulate_episode(PG_CELLS[cell], output_tokens, self.inp)
            self._episodes[key] = self.calls_cost(model, calls, flex, writes)
        return self._episodes[key]

    def control_prompt(self, model: str, output_tokens: float, flex: bool, writes: bool) -> float:
        call = Call(self.inp.num("pg_control_prompt_tokens"), 0.0, output_tokens)
        return self.calls_cost(model, [call], flex, writes)

    def probe_call(self, model: str, output_tokens: float, flex: bool, writes: bool) -> float:
        call = Call(self.inp.num("openai_probe_input_tokens"), 0.0, output_tokens)
        return self.calls_cost(model, [call], flex, writes)

    def per_episode_table(self) -> pd.DataFrame:
        """(c) Per-episode tokens and cost for every cell, model and output level."""
        rows = []
        for model in (LUNA, SOL):
            for cell, spec in PG_CELLS.items():
                for o in self.output_grid:
                    calls = simulate_episode(spec, o, self.inp)
                    tin = sum(c.input for c in calls)
                    tcached = sum(c.cached for c in calls)
                    flex_w = self.episode(model, cell, o, True, True)
                    flex_nw = self.episode(model, cell, o, True, False)
                    rows.append({
                        "model": model, "cell": cell, "output_per_call": o,
                        "n_calls": len(calls), "input_tokens": round(tin),
                        "cached_share": tcached / tin,
                        "output_tokens": round(sum(c.output for c in calls)),
                        "usd_flex_writes": flex_w, "usd_flex_no_writes": flex_nw,
                        "usd_standard_writes": self.episode(model, cell, o, False, True),
                        "write_uplift": flex_w / flex_nw - 1,
                    })
        return pd.DataFrame(rows)

    @property
    def output_grid(self) -> list[int]:
        return [int(float(x)) for x in self.inp.names("pg_output_tokens_grid")]

    def luna_cells(self, which: str) -> list[str]:
        return self.inp.names("pg_luna_cells_all" if which == "all" else "pg_luna_cells_replay_off")

    # ---- line items -----------------------------------------------------------------------
    def combos(self) -> list[tuple[int, str]]:
        return [(d, t) for d in sorted(self.draws.draw.unique())
                for t in self.inp.names("arc_heldout_third_candidates")]

    def items(self, s: Scenario) -> list[Item]:
        """Line items for a scenario; averaged over draws/third games when those are None."""
        draws = [s.draw] if s.draw is not None else sorted(self.draws.draw.unique())
        thirds = ([s.third] if s.third is not None
                  else self.inp.names("arc_heldout_third_candidates"))
        combos = [(d, t) for d in draws for t in thirds]
        if len(combos) == 1:
            return self._items(s, *combos[0])
        sums: dict[tuple, float] = {}
        for d, t in combos:
            for phase, block, payee, item, usd in self._items(s, d, t):
                sums[(phase, block, payee, item)] = sums.get((phase, block, payee, item), 0.0) + usd
        return [(*key, usd / len(combos)) for key, usd in sums.items()]

    def _items(self, s: Scenario, draw: int, third: str) -> list[Item]:
        inp, o, fx, wr = self.inp, s.output_tokens, s.openai_flex, s.cache_writes

        def ep(model: str, cell: str) -> float:
            return self.episode(model, cell, o, fx, wr)

        rep = 1 + (inp.num("pg_replicate_fraction") if s.replicates else 0.0)
        rerun = inp.num("arc_rerun_rate_moderate") if s.rerun_rate is None else s.rerun_rate
        luna_cells = self.luna_cells(s.luna_cells)
        sol_cells = inp.names("pg_sol_core_cells")
        task_cells = inp.num("pg_task_cells")
        pilot_eps = inp.num("pg_pilot_episodes_per_cell")
        echo_n = inp.num("openai_echo_calls_per_model")
        probe_n = inp.num("openai_probe_conversations") * inp.num("openai_probe_turns")
        d = self._draw_rows[(draw, s.arc_case)]
        heldout = float(self._heldout_usd[(draw, third, s.arc_case)])

        items: list[Item] = [
            # Block 1: pilots. Toggle and ARC probes count toward phase 0; PersistGym pilots
            # and validity runs toward phase 1a (common/costs.py EXPERIMENT_PHASE).
            ("0", B1, "OpenAI", "echo check (sol)", echo_n * self.probe_call(SOL, o, fx, wr)),
            ("0", B1, "OpenAI", "echo check (luna)", echo_n * self.probe_call(LUNA, o, fx, wr)),
            ("0", B1, "OpenAI", "replay probe (sol)", probe_n * self.probe_call(SOL, o, fx, wr)),
            ("0", B1, "OpenAI", "replay probe (luna)", probe_n * self.probe_call(LUNA, o, fx, wr)),
            ("0", B1, "Google", "Gemini acceptance + Flex latency probe", self.gemini_probe),
            ("0", B1, "Google", "truncated ARC pilot", self.pilot_by_case[s.arc_case]),
            ("1a", B1, "OpenAI", "luna pilots", pilot_eps * sum(ep(LUNA, c) for c in luna_cells)),
            ("1a", B1, "OpenAI", "luna validity",
             inp.num("pg_luna_validity_episodes") * ep(LUNA, "F-0")),
            ("1a", B1, "OpenAI", "sol pilot", pilot_eps * sum(ep(SOL, c) for c in sol_cells)),
            ("1a", B1, "OpenAI", "sol validity",
             inp.num("pg_sol_validity_episodes") * ep(SOL, "F-0")),
            # Block 2: seed-1 S0+S4 on the 4 drawn games.
            ("1b", B2, "Google", "seed-1 S0+S4 (8 runs)", float(d.seed1_s0s4)),
            ("1b", B2, "Google", "seed-1 re-runs", rerun * float(d.seed1_s0s4)),
            # Block 3: the commitment.
            ("1b", B3, "Google", "path remainder (24 runs)", float(d.remainder_1b)),
            ("1b", B3, "Google", "remainder re-runs", rerun * float(d.remainder_1b)),
            ("1a", B3, "OpenAI", "luna sweep", inp.num("pg_templates_luna") * task_cells * rep
             * sum(ep(LUNA, c) for c in luna_cells)),
            ("1a", B3, "OpenAI", "luna control prompts",
             inp.num("pg_control_prompts") * self.control_prompt(LUNA, o, fx, wr)),
            ("1a", B3, "OpenAI", "sol H2 core",
             inp.num("pg_templates_sol") * task_cells * rep * sum(ep(SOL, c) for c in sol_cells)),
            # Block 4: phase 2.
            ("2", B4, "OpenAI", "StateCarry PersistGym cell (luna)",
             inp.num("pg_templates_luna") * task_cells * rep * ep(LUNA, "StateCarry")),
            ("2", B4, "Google", "ARC dev games (at cap)", inp.num("arc_dev_cap_usd")),
            ("2", B4, "Google", "held-out runs (18)", heldout),
            ("2", B4, "Google", "held-out re-runs", rerun * heldout if s.rerun_heldout else 0.0),
            ("1b", B2, "ARC Prize", "ARC API (free research preview)", 0.0),
            ("2", B4, "GPU", "GPU (E1 not in this scenario)", 0.0),
        ]
        if s.cap_1a:
            items = self._cap_1a(items)
        return items

    def _cap_1a(self, items: list[Item]) -> list[Item]:
        """A1 §16.1 sizing rule: shrink the 1a sweep (fewer templates) to fit the 1a cap."""
        cap = self.inp.num("cap_phase_1a")
        fixed = sum(i[4] for i in items if i[0] == "1a" and i[3] not in SWEEP_ITEMS)
        sweep = sum(i[4] for i in items if i[0] == "1a" and i[3] in SWEEP_ITEMS)
        if fixed + sweep <= cap or sweep == 0:
            return items
        scale = max(cap - fixed, 0.0) / sweep
        return [(p, b, y, n, u * scale if p == "1a" and n in SWEEP_ITEMS else u)
                for p, b, y, n, u in items]


def items_frame(items: list[Item]) -> pd.DataFrame:
    return pd.DataFrame(items, columns=["phase", "block", "payee", "item", "usd"])


def total(items: list[Item], *, phase: str | None = None, block: str | None = None,
          payee: str | None = None, blocks: Iterable[str] | None = None) -> float:
    bset = set(blocks) if blocks is not None else None
    return sum(u for p, b, y, _, u in items
               if (phase is None or p == phase) and (block is None or b == block)
               and (payee is None or y == payee) and (bset is None or b in bset))


def pivot_payee(items: list[Item], by: str) -> pd.DataFrame:
    keys = PHASES if by == "phase" else BLOCKS
    rows = []
    for key in keys:
        row = {by: key}
        for payee in PAYEES:
            row[payee] = total(items, payee=payee, **{by: key})
        row["total"] = sum(row[p] for p in PAYEES)
        rows.append(row)
    df = pd.DataFrame(rows)
    sums = {by: "total", **{c: df[c].sum() for c in [*PAYEES, "total"]}}
    return pd.concat([df, pd.DataFrame([sums])], ignore_index=True)


# --------------------------------------------------------------------------------------------
# Report tables
# --------------------------------------------------------------------------------------------
def draws_table(m: CostModel) -> pd.DataFrame:
    """(a) One row per draw: 1b cost per billing case and the cap flags."""
    cap = m.inp.num("cap_phase_1b")
    reserve = m.inp.num("arc_rerun_rate_moderate")
    wide = m.draws.pivot_table(index=["draw", "drawn", "undrawn"], columns="case",
                               values="path_1b").reset_index()
    wide.columns.name = None
    for case in ALL_ARC_CASES:
        wide[f"above_cap_{case}"] = wide[case] > cap
        wide[f"above_cap_with_reserve_{case}"] = wide[case] * (1 + reserve) > cap
    return wide


def draws_summary(m: CostModel) -> pd.DataFrame:
    cap = m.inp.num("cap_phase_1b")
    reserve = m.inp.num("arc_rerun_rate_moderate")
    rows = []
    for case in ALL_ARC_CASES:
        d = m.draws.loc[m.draws.case == case]
        for metric in ("seed1_s0s4", "seed1_path", "remainder_1b", "path_1b"):
            row = {"case": case, "metric": metric, "min": d[metric].min(),
                   "mean": d[metric].mean(), "max": d[metric].max()}
            if metric == "path_1b":
                row["n_draws_above_cap"] = int((d[metric] > cap).sum())
                row["n_above_cap_with_reserve"] = int((d[metric] * (1 + reserve) > cap).sum())
            rows.append(row)
    return pd.DataFrame(rows)


def overcap_games(m: CostModel, case: str = "list_nocache") -> tuple[list[str], bool]:
    """Games common to every draw whose 1b exceeds the cap, and whether 'contains all of them'
    is exactly the over-cap condition."""
    cap = m.inp.num("cap_phase_1b")
    d = m.draws.loc[m.draws.case == case]
    over = d.loc[d.path_1b > cap, "drawn"].map(lambda s: set(s.split("+")))
    if over.empty:
        return [], True
    common = set.intersection(*over)
    contains = d.drawn.map(lambda s: common <= set(s.split("+")))
    return sorted(common), bool((contains == (d.path_1b > cap)).all())


def heldout_table(m: CostModel, cell_costs: Iterable[float] = (10.0, 25.0, 40.0)) -> pd.DataFrame:
    """(b) One row per undrawn pair and third game: held-out cost per billing case, phase 2 at
    no-cache list (dev at its cap, no re-runs) for several PersistGym cell costs."""
    wide = m.heldout.pivot_table(index=["draw", "undrawn", "third"], columns="case",
                                 values="heldout").reset_index()
    wide.columns.name = None
    dev, cap = m.inp.num("arc_dev_cap_usd"), m.inp.num("cap_phase_2")
    path = m.draws.loc[m.draws.case == "list_nocache"].set_index("draw").path_1b
    wide["list_1b_plus_heldout"] = wide["draw"].map(path) + wide["list_nocache"]
    for cell in cell_costs:
        phase2 = wide["list_nocache"] + dev + cell
        wide[f"phase2_list_cell{int(cell)}"] = phase2
        wide[f"over_cap_cell{int(cell)}"] = phase2 > cap
    return wide


PRE_COMMIT, BY_G2 = "blocks 1-2 (before commitment)", "blocks 1-3 (by G2)"


def block_metrics(items: list[Item]) -> dict[tuple[str, str], float]:
    """Block totals by payee, plus cumulative spend before the commitment and by G2."""
    out = {}
    for block in BLOCKS:
        out[(block, "total")] = total(items, block=block)
        for payee in ("Google", "OpenAI"):
            out[(block, payee)] = total(items, block=block, payee=payee)
    out[(PRE_COMMIT, "total")] = total(items, blocks=(B1, B2))
    out[(BY_G2, "total")] = total(items, blocks=(B1, B2, B3))
    return out


def grid_metrics(m: CostModel, arc_case: str, cap_1a: bool) -> list[dict[tuple[str, str], float]]:
    """block_metrics over draws x third games x 1k/2k/3k output x 4 or 8 luna cells."""
    out = []
    for o in m.output_grid:
        for cells in ("replay_off", "all"):
            for d, t in m.combos():
                s = Scenario(arc_case=arc_case, output_tokens=o, luna_cells=cells, cap_1a=cap_1a,
                             draw=d, third=t)
                out.append(block_metrics(m.items(s)))
    return out


def blocks_table(m: CostModel) -> pd.DataFrame:
    """(e) Each staged approval block: low / central / high, by payee, per ARC billing case.

    low and high range over the 15 draws x 2 third games x 1k/2k/3k output per call x 4 or 8
    luna cells, with moderate re-runs. 'high_1a_capped' applies the A1 sizing rule (phase 1a
    held to its cap by running fewer PersistGym templates).
    """
    if m._blocks is not None:
        return m._blocks
    rows = []
    for case in ALL_ARC_CASES:
        central = block_metrics(m.items(replace(CENTRAL, arc_case=case)))
        free, capped = grid_metrics(m, case, False), grid_metrics(m, case, True)
        for key, value in central.items():
            rows.append({"case": case, "block": key[0], "payee": key[1],
                         "low": min(g[key] for g in free), "central": value,
                         "high": max(g[key] for g in free),
                         "high_1a_capped": max(g[key] for g in capped)})
    m._blocks = pd.DataFrame(rows)
    return m._blocks


def pessimistic_rerun_rate(inp: Inputs) -> float:
    """Published early-ending shares averaged over the path's configs (S1, S2 at the midpoint)."""
    std, pa = inp.num("arc_early_end_share_std"), inp.num("arc_early_end_share_pa")
    return (std + 2 * (std + pa) / 2 + pa) / 4


def scenario_set(m: CostModel) -> dict[str, Scenario]:
    """Named scenarios for the totals table (d)."""
    out = {f"central / ARC {case}": replace(CENTRAL, name=f"central_{case}", arc_case=case)
           for case in ARC_CASES}
    out["everything at list (ARC no-cache list, OpenAI standard tier)"] = replace(
        CENTRAL, name="everything_list", arc_case="list_nocache", openai_flex=False)
    worst = max(m.combos(), key=lambda c: total(m.items(replace(
        CENTRAL, arc_case="list_nocache", openai_flex=False, output_tokens=3000,
        rerun_rate=pessimistic_rerun_rate(m.inp), draw=c[0], third=c[1]))))
    label = "pessimistic (everything at list, 3k output, costliest draw, published re-run rate)"
    out[label] = replace(
        CENTRAL, name="pessimistic", arc_case="list_nocache", openai_flex=False, output_tokens=3000,
        rerun_rate=pessimistic_rerun_rate(m.inp), draw=worst[0], third=worst[1])
    for case in ARC_CASES:
        out[f"like-for-like / ARC {case}: no §5 repeat subset, no held-out re-runs"] = replace(
            CENTRAL, name=f"lean_{case}", arc_case=case, replicates=False, rerun_heldout=False)
    out["sensitivity: central / ARC flex_cached, 1a sized to its cap"] = replace(
        CENTRAL, name="central_flex_cap1a", cap_1a=True)
    return out


def totals_table(m: CostModel) -> pd.DataFrame:
    """(d) Totals by phase and payee for each named scenario, with the phase caps."""
    caps = {p: m.inp.num(f"cap_phase_{p}") for p in PHASES}
    frames = []
    for label, s in scenario_set(m).items():
        df = pivot_payee(m.items(s), "phase")
        df.insert(0, "scenario", label)
        df["cap"] = df["phase"].map(caps)
        df["over_cap"] = df["total"] > df["cap"]
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


# --------------------------------------------------------------------------------------------
# Comparison with the numbers stated in PLAN §16 and the low-spend review
# --------------------------------------------------------------------------------------------
def computed_values(m: CostModel) -> dict[str, tuple[float, float]]:
    """Computed counterpart of every reference key, as (low, high)."""
    inp = m.inp
    v: dict[str, tuple[float, float]] = {}

    def rng(series) -> tuple[float, float]:
        return float(series.min()), float(series.max())

    def dcase(case: str) -> pd.DataFrame:
        return m.draws.loc[m.draws.case == case]

    def hcase(case: str) -> pd.DataFrame:
        return m.heldout.loc[m.heldout.case == case]

    # (a) ARC path
    v["arc_1b_list"] = rng(dcase("list_nocache").path_1b)
    mean = float(dcase("list_nocache").path_1b.mean())
    v["arc_1b_list_mean"] = (mean, mean)
    n_over = float((dcase("list_nocache").path_1b > inp.num("cap_phase_1b")).sum())
    v["arc_draws_above_900_list"] = (n_over, n_over)
    v["arc_1b_flex"] = rng(dcase("flex_nocache").path_1b)
    per_action = arc_pooled_usd_per_action(inp)
    v["arc_pooled_usd_per_action_s0"] = (per_action["S0"],) * 2
    v["arc_pooled_usd_per_action_s4"] = (per_action["S4"],) * 2
    for case, key in (("flex_cached", "flex_cached"), ("flex_nocache", "flex_nocache"),
                      ("standard_cached", "standard_cached"), ("list_nocache", "list")):
        v[f"arc_seed1_s0s4_{key}"] = rng(dcase(case).seed1_s0s4)
        v[f"arc_remainder_{key}"] = rng(dcase(case).remainder_1b)
    top = float(dcase("flex_nocache").seed1_path.max())
    v["arc_seed1_path_flex_nocache_max"] = (top, top)
    rate = inp.num("arc_rerun_rate_moderate")
    v["rerun_reserve_flex"] = tuple(rate * x for x in rng(dcase("flex_cached").path_1b))
    v["rerun_reserve_standard"] = tuple(rate * x for x in rng(dcase("standard_cached").path_1b))
    runs = inp.num("arc_path_games") * inp.num("arc_path_configs") * inp.num("arc_seeds")
    cap1b = inp.num("cap_phase_1b")
    v["g0_rule_usd_per_run_reserve"] = (cap1b / (runs * (1 + rate)),) * 2
    v["g0_rule_usd_per_run_no_reserve"] = (cap1b / runs,) * 2
    # (b) held-out
    v["heldout_list"] = rng(hcase("list_nocache").heldout)
    v["heldout_flex"] = rng(hcase("flex_nocache").heldout)
    mean = float(hcase("standard_cached").heldout.mean())
    v["heldout_standard_cached"] = (mean, mean)
    ht = heldout_table(m)
    v["arc_1b_plus_heldout_list"] = rng(ht.list_1b_plus_heldout)
    for cell in (10, 25, 40):
        n = float(ht[f"over_cap_cell{cell}"].sum())
        v[f"phase2_overcap_cell{cell}"] = (n, n)
    o_lo, o_hi = min(m.output_grid), max(m.output_grid)
    reps = inp.num("pg_templates_luna") * inp.num("pg_task_cells")
    v["statecarry_pg_cell"] = (reps * m.episode(LUNA, "StateCarry", o_lo),
                               reps * m.episode(LUNA, "StateCarry", o_hi))
    # (c) PersistGym per episode (Flex)
    sol = m.price(SOL)
    out = inp.num("pg_calls_per_episode") * 1000 * sol.output / 1e6 * (1 - inp.num("flex_discount"))
    v["sol_output_per_episode_flex_1k"] = (out, out)
    for key, cell in (("F0", "F-0"), ("Fr", "F-r"), ("W", "W-n-0")):
        nw, w = m.episode(SOL, cell, 1000, True, False), m.episode(SOL, cell, 1000, True, True)
        v[f"sol_{key}_flex_1k_nowrites"] = (nw, nw)
        v[f"sol_{key}_flex_1k_writes"] = (w, w)
    up_f = m.episode(SOL, "F-0", 1000) / m.episode(SOL, "F-0", 1000, True, False) - 1
    up_w = m.episode(SOL, "W-n-0", 1000) / m.episode(SOL, "W-n-0", 1000, True, False) - 1
    v["cache_write_uplift_sol_F"] = (up_f, up_f)
    v["cache_write_uplift_sol_W"] = (up_w, up_w)
    sol_eps = inp.num("pg_templates_sol") * inp.num("pg_task_cells")  # 640 = 320 per cell pair
    for o in m.output_grid:
        core = sol_eps * sum(m.episode(SOL, c, o) for c in inp.names("pg_sol_core_cells"))
        v[f"sol_core_flex_{o // 1000}k"] = (core, core)
    for key, writes in (("nowrites", False), ("writes", True)):
        cells = inp.names("pg_sol_h1_cells")
        vals = [sol_eps * sum(m.episode(SOL, c, o, True, writes) for c in cells)
                for o in (o_lo, o_hi)]
        v[f"sol_h1_replication_flex_{key}"] = (vals[0], vals[1])
    luna_eps = inp.num("pg_templates_luna") * inp.num("pg_task_cells")
    for key, cells in (("luna_sweep_4cells", "replay_off"), ("luna_sweep_8cells", "all")):
        x = luna_eps * sum(m.episode(LUNA, c, 1000) for c in m.luna_cells(cells))
        v[key] = (x, x)
    x = inp.num("pg_control_prompts") * m.control_prompt(LUNA, 1000, True, True)
    v["luna_controls"] = (x, x)
    lean = {"replicates": False, "rerun_heldout": False}
    v["phase_1a_total"] = (
        total(m.items(replace(CENTRAL, luna_cells="replay_off", **lean)), phase="1a"),
        total(m.items(replace(CENTRAL, **lean)), phase="1a"))
    # Block 1 items: low at 1k output and 4 luna cells, high at 3k and 8 cells; ARC pilot at
    # Flex (cache-billed) for low and at no-cache list for high.
    lo_s = replace(CENTRAL, luna_cells="replay_off", output_tokens=o_lo)
    hi_s = replace(CENTRAL, arc_case="list_nocache", output_tokens=o_hi)
    lo_i, hi_i = m.items(lo_s), m.items(hi_s)

    def item(items, *names):
        return sum(u for *_, n, u in items if n in names)

    for key, names in (("echo_check", ("echo check (sol)", "echo check (luna)")),
                       ("replay_probe", ("replay probe (sol)", "replay probe (luna)")),
                       ("luna_pilots", ("luna pilots",)), ("luna_validity", ("luna validity",)),
                       ("sol_pilot", ("sol pilot",)), ("sol_validity", ("sol validity",))):
        v[key] = (item(lo_i, *names), item(hi_i, *names))
    v["gemini_probe"] = (m.gemini_probe, m.gemini_probe)
    # The plan's "$13 at Flex" is the no-cache list cost halved; compare like for like.
    v["arc_pilot_flex"] = (m.pilot_by_case["flex_nocache"],) * 2
    v["arc_pilot_list"] = (m.pilot_by_case["list_nocache"],) * 2
    pl = m.pilot.loc[m.pilot.case == "list_nocache"].set_index("config").usd
    v["arc_pilot_s0s4_list"] = (float(pl.S0 + pl.S4),) * 2
    v["arc_pilot_s1s2_list"] = (float(pl.S1 + pl.S2),) * 2
    v["block1_total"] = (total(lo_i, block=B1), total(hi_i, block=B1))
    v["block1_openai"] = (total(lo_i, block=B1, payee="OpenAI"),
                          total(hi_i, block=B1, payee="OpenAI"))
    v["block1_google"] = (total(lo_i, block=B1, payee="Google"),
                          total(hi_i, block=B1, payee="Google"))
    # Block 2 as the plan states it: the 8 runs alone, low end cache-billed, high end no-cache.
    v["block2_flex"] = (float(dcase("flex_cached").seed1_s0s4.min()),
                        float(dcase("flex_nocache").seed1_s0s4.max()))
    v["block2_standard"] = (float(dcase("standard_cached").seed1_s0s4.min()),
                            float(dcase("list_nocache").seed1_s0s4.max()))
    v["block2_reruns"] = (0.0, max(rate * float(dcase(c).seed1_s0s4.max()) for c in ARC_CASES))
    # Blocks 3-4 and cumulative spend, from the blocks table (moderate re-runs included).
    bt = blocks_table(m).set_index(["case", "block", "payee"])

    def b(case: str, block: str, col: str = "low") -> float:
        return float(bt.loc[(case, block, "total"), col])

    v["block3_flex"] = (b("flex_cached", B3), b("flex_cached", B3, "high_1a_capped"))
    v["block3_standard"] = (b("standard_cached", B3), b("standard_cached", B3, "high_1a_capped"))
    x = b("list_nocache", B3, "high_1a_capped")
    v["block3_list_max"] = (x, x)
    v["block4"] = (b("flex_cached", B4), b("list_nocache", B4, "high"))
    v["before_g2"] = (b("flex_cached", BY_G2), b("standard_cached", BY_G2, "high_1a_capped"))
    for key, case in (("flex", "flex_cached"), ("standard", "standard_cached"),
                      ("list", "list_nocache")):
        v[f"cum_by_g2_{key}"] = (b(case, BY_G2), b(case, BY_G2, "high_1a_capped"))
    for key, case in (("flex", "flex_cached"), ("standard", "standard_cached")):
        v[f"pre_commit_{key}"] = (b(case, PRE_COMMIT), b(case, PRE_COMMIT, "high"))
    # (d) totals
    for case in ARC_CASES:
        items = m.items(replace(CENTRAL, arc_case=case))
        t = total(items)
        v[f"total_{case}"] = (t, t)
        for payee in ("Google", "OpenAI"):
            x = total(items, payee=payee)
            v[f"total_{case}_{payee.lower()}"] = (x, x)
    sc = scenario_set(m)
    x = total(m.items(sc["everything at list (ARC no-cache list, OpenAI standard tier)"]))
    v["total_everything_list"] = (x, x)
    pess = next(s for s in sc.values() if s.name == "pessimistic")
    x = total(m.items(pess))
    v["total_pessimistic"] = (x, x)
    x = total(m.items(replace(CENTRAL, output_tokens=o_hi)), payee="OpenAI")
    v["openai_uncapped_3k"] = (x, x)
    v["e1_gpu"] = (inp.num("e1_gpu_hours_low") * inp.num("gpu_a100_usd_per_hour_low"),
                   inp.num("e1_gpu_hours_high") * inp.num("gpu_a100_usd_per_hour_high"))
    return v


def comparison_table(m: CostModel, threshold: float = 0.05,
                     ref_path: Path = DATA_DIR / REFERENCE_FILE) -> pd.DataFrame:
    ref = pd.read_csv(ref_path)
    comp = computed_values(m)
    missing = sorted(set(ref.key) - set(comp))
    if missing:
        raise KeyError(f"no computed value for reference keys: {missing}")
    rows = []
    for r in ref.itertuples(index=False):
        lo, hi = comp[r.key]

        def rel(ours: float, theirs: float) -> float:
            if theirs == 0:
                return 0.0 if abs(ours) < 1e-9 else math.inf
            return ours / theirs - 1

        d_lo, d_hi = rel(lo, r.ref_low), rel(hi, r.ref_high)
        rows.append({"key": r.key, "ref_low": r.ref_low, "ref_high": r.ref_high,
                     "computed_low": lo, "computed_high": hi, "diff_low": d_lo,
                     "diff_high": d_hi, "flag_over_5pct": max(abs(d_lo), abs(d_hi)) > threshold,
                     "source": r.source, "stated_as": r.stated_as})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------
def build_report(m: CostModel) -> dict[str, pd.DataFrame]:
    games = m.run_costs.reset_index()
    games = games.loc[games.game.isin(m.eligible)]
    common, exact = overcap_games(m)
    summary = draws_summary(m)
    summary.attrs["note"] = (f"1b above cap at no-cache list exactly when the draw contains "
                             f"{' and '.join(common)}: {exact}")
    return {
        "arc_case_factors": pd.DataFrame(m.factors).T.rename_axis("case").reset_index(),
        "arc_eligible_run_costs": games,
        "arc_draws": draws_table(m),
        "arc_draws_summary": summary,
        "arc_heldout": heldout_table(m),
        "arc_pilot": m.pilot,
        "persistgym_per_episode": m.per_episode_table(),
        "central_line_items": items_frame(m.items(CENTRAL)),
        "totals_by_phase_payee": totals_table(m),
        "approval_blocks": blocks_table(m),
        "compare_plan_a1": comparison_table(m),
    }


def _print(name: str, df: pd.DataFrame) -> None:
    print(f"\n=== {name} ===")
    if df.attrs.get("note"):
        print(df.attrs["note"])
    with pd.option_context("display.max_rows", 500, "display.max_columns", 50,
                           "display.width", 250):
        print(df.to_string(index=False, float_format=lambda x: f"{x:,.3f}"))


def write_report(tables: dict[str, pd.DataFrame], out_dir: Path, run_id: str, started: str,
                 m: CostModel) -> Path:
    from common import runmeta

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(out_dir / f"{name}.csv", index=False, float_format="%.6g")
    ref_bytes = (DATA_DIR / REFERENCE_FILE).read_bytes()
    config = {"parameters": m.inp.params, "input_sha256": input_hashes(),
              "reference_sha256": hashlib.sha256(ref_bytes).hexdigest(),
              "central_scenario": asdict(CENTRAL)}
    return runmeta.write_meta(
        out_dir, experiment="cost_model", run_id=run_id, cell_or_config="cost_model_v1",
        config=config, model_requested=None, model_returned=None, reasoning_effort=None,
        reasoning_context_requested=None, reasoning_context_echoed=None, template_id=None,
        repeat_index=None, seeds=None, started_utc=started, finished_utc=runmeta.utc_now(),
        exit_reason="completed", tokens=None, cost_usd=0.0, raw_transcript_path=None,
        outputs=sorted(f"{n}.csv" for n in tables), paid_calls=0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="default: results/cost_model/<run_id>/")
    ap.add_argument("--no-write", action="store_true", help="print only")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    started = datetime.now(UTC)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    m = CostModel()
    tables = build_report(m)
    for name, df in tables.items():
        _print(name, df)
    flagged = tables["compare_plan_a1"]
    flagged = flagged.loc[flagged.flag_over_5pct, "key"].tolist()
    print(f"\n{len(flagged)} reference numbers differ by more than 5%: {', '.join(flagged)}")
    if not args.no_write:
        out = args.out_dir or REPO_ROOT / "results" / "cost_model" / run_id
        meta = write_report(tables, out, run_id, started.isoformat(timespec="seconds"), m)
        print(f"\nwrote {out} ({meta.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
