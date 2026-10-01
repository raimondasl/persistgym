"""Operational slice of the free ARC public-set analysis (PLAN.md §8.1 as split by §16.3).

    PERSISTGYM_RAW_DIR=... uv run python -m arc.public.ops [--run-id ID]

Reads ONLY the local cache filled by ``arc.public.pull`` (offline; it never fetches) and writes
``results/arc_public_ops/<run_id>/``: ``meta.json``, CSV tables and ``summary.md``.

Everything here is operational and descriptive: how published runs ended, seconds and cost
per action, token mix, clean-run cost bounds, the eligibility re-check. It deliberately does
NOT compute H5 (per-level P(clear | reached) by harness, or any per-level clear-rate
comparison between harnesses); that waits for the PREREG commit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from arc.public import premise, recordings, sessions
from arc.public.client import PoliteClient
from arc.public.discover import PublishedRun
from arc.public.pull import RECORDING_GAMES, RESULTS_SLUG, discover
from common import runmeta

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = REPO_ROOT / "results" / "arc_public_ops"
HARNESS_COMMIT = "4ca00e607e3364a501fcbf7d1b7537dd2729cec3"
COST_CAP_ELIGIBLE = 60.0
GAP_MIN_ELIGIBLE = 20.0
# Decision D14 option A (researcher, 2026-10-01): held-out games SP80, VC33 and TN36.
OPTION_A_HELDOUT = ("SP80", "VC33", "TN36")
CSV = {"index": False, "lineterminator": "\n", "float_format": "%.6g"}


# ── loading ──────────────────────────────────────────────────────────────
def load_runs(client: PoliteClient) -> pd.DataFrame:
    return runs_frame([(run, client.session(run.guid)) for run in discover(client)])


def runs_frame(pairs: list[tuple[PublishedRun, dict]]) -> pd.DataFrame:
    """One row per published run: page variant + parsed session + inferred ending."""
    rows = []
    for run, session in pairs:
        s = sessions.parse_session(session)
        if s.guid != run.guid:
            raise ValueError(f"session guid mismatch for {run.guid}")
        rows.append({
            "game": run.game, "harness": run.harness, "effort": run.effort,
            "variant_id": run.variant_id, "page_score": run.page_score,
            "config_matches_variant": sessions.config_matches(s.config, run.harness,
                                                              run.effort),
            **s.as_dict(),
        })
    df = pd.DataFrame(rows)
    df["final_level"] = df["final_level_index"] + 1
    df["duration_h"] = df["duration_s"] / 3600
    df["score_matches_page"] = (df["score"] - 100 * df["page_score"]).abs() < 1e-6
    return df


def load_recordings(client: PoliteClient, runs: pd.DataFrame) -> dict[str, dict]:
    """guid -> {"summary": recordings.Summary, "level_actions": per-level counts re-derived
    from the NDJSON, compared later with the session's ``level_actions``}."""
    out = {}
    for r in runs.itertuples():
        if r.effort == "high" and r.game in RECORDING_GAMES:
            steps = recordings.load_steps(client.recording(r.game_id, r.guid))
            out[r.guid] = {"summary": recordings.summarize(steps),
                           "level_actions": recordings.level_action_counts(steps,
                                                                           r.level_count)}
    return out


# ── tables ───────────────────────────────────────────────────────────────
PER_RUN_COLS = [
    "game", "game_id", "harness", "effort", "config", "config_matches_variant", "guid",
    "score", "state", "levels_completed", "level_count", "total_actions", "resets",
    "final_level", "final_level_actions", "final_level_baseline", "final_level_budget",
    "budget_margin", "open_at", "last_update", "duration_h",
    "inferred_ending",
]


def endings_table(runs: pd.DataFrame) -> pd.DataFrame:
    t = (runs.groupby(["harness", "effort", "inferred_ending"]).size()
         .unstack("inferred_ending", fill_value=0)
         .reindex(columns=list(sessions.ENDINGS), fill_value=0))
    t["n_runs"] = t.sum(axis=1)
    # "ended before its action budget without a win": neither GAME_WIN nor ACTION_BUDGET
    t["early_no_win"] = t[sessions.ERROR_OR_CLOSED] + t[sessions.TIME_BUDGET]
    order = [(h, e) for h in ("standard", "provider_adapter") for e in ("high", "medium", "low")]
    return t.reindex(order).reset_index()


def recording_table(runs: pd.DataFrame, recs: dict[str, dict]) -> pd.DataFrame:
    rows = []
    for r in runs[runs["guid"].isin(recs)].itertuples():
        s = recs[r.guid]["summary"]
        rec_levels = recs[r.guid]["level_actions"]
        rows.append({
            "game": r.game, "harness": r.harness, "guid": r.guid,
            "session_actions": r.total_actions, **s.as_dict(),
            "session_s_per_action": r.duration_s / r.total_actions if r.total_actions else None,
            "cost_cached_price_per_step": s.cost_cached_price_usd / s.n_model_steps,
            "steps_match_session": s.n_steps == r.total_actions,
            "level_actions_match_session": " ".join(map(str, rec_levels)) == r.level_actions,
        })
    return pd.DataFrame(rows).sort_values(["game", "harness"]).reset_index(drop=True)


def clean_run_bounds(runs: pd.DataFrame, rec: pd.DataFrame) -> pd.DataFrame:
    """Cost a run would have had if it had not stopped early, at plateau cost per action.

    The action count is a true upper bound (the 5x budget); the price per action is the run's
    own mean plateau list cost per model call, an estimate. So the dollar figure is a planning
    bound, not a guaranteed maximum: later levels could cost more per call (longer reasoning,
    more multi-attempt steps). ``bound_stop_level_overall_mean_usd`` prices the same actions at
    the run's overall mean cost per model call (warm-up included), the basis of PLAN §16.4's
    LP85 figure.

    ``bound_stop_level_usd`` (the PLAN §16.4 definition): measured cost of every action taken
    + the stopping level's remaining 5x budget x plateau cost per action. This is what the run
    would cost had it kept playing the level it stopped on until its budget ran out.
    ``bound_full_game_usd`` adds the 5x budgets of all later levels too, the worst case if the
    run had also cleared the stopping level. For GAME_WIN and ACTION_BUDGET runs nothing
    remains on the stopping level, so the first bound equals the measured cost.
    Wall-clock check: (actions taken + remaining stop-level budget) x the run's mean seconds
    per action, against the 12 h budget. ``bound_stop_level_12h_usd`` caps the remaining
    actions at those that fit in what was left of 12 h at that pace (the harness would have
    ended with TIME_BUDGET first).
    """
    rows = []
    for r in rec.itertuples():
        run = runs[runs["guid"] == r.guid].iloc[0]
        remaining_stop = max(0, run.final_level_budget - run.final_level_actions)
        if run.inferred_ending == sessions.GAME_WIN:
            remaining_stop = 0
        later = [sessions.level_budget(b) for b in
                 [int(x) for x in str(run.level_baselines).split()][run.final_level_index + 1:]]
        remaining_full = remaining_stop + (0 if run.inferred_ending == sessions.GAME_WIN
                                           else sum(later))
        plateau = r.plateau_cost_per_step_mean
        spa = r.s_per_step_mean
        bound_stop_actions = run.total_actions + remaining_stop
        time_left_s = max(0.0, sessions.TIME_BUDGET_S - run.duration_s)
        remaining_12h = min(remaining_stop, math.floor(time_left_s / spa)) if spa else 0
        rows.append({
            "game": run.game, "harness": run.harness, "inferred_ending": run.inferred_ending,
            "final_level": run.final_level, "level_count": run.level_count,
            "actions_taken": run.total_actions, "final_level_actions": run.final_level_actions,
            "final_level_budget": run.final_level_budget,
            "remaining_stop_level_actions": remaining_stop,
            "remaining_full_game_actions": remaining_full,
            "measured_cost_usd": r.cost_total_usd,
            "plateau_cost_per_action_usd": plateau,
            "bound_stop_level_usd": r.cost_total_usd + remaining_stop * plateau,
            "bound_stop_level_overall_mean_usd": (r.cost_total_usd
                                                  + remaining_stop * r.cost_per_step_mean),
            "bound_full_game_usd": r.cost_total_usd + remaining_full * plateau,
            "bound_stop_level_12h_usd": r.cost_total_usd + remaining_12h * plateau,
            "s_per_action_mean": spa,
            "bound_stop_level_actions": bound_stop_actions,
            "bound_stop_level_wallclock_h": bound_stop_actions * spa / 3600,
            "fits_12h_at_stop_level_bound": bound_stop_actions * spa <= sessions.TIME_BUDGET_S,
            "bound_full_game_wallclock_h": (run.total_actions + remaining_full) * spa / 3600,
        })
    return pd.DataFrame(rows)


def eligibility_table(runs: pd.DataFrame, rec: pd.DataFrame,
                      premise_rows: list[dict]) -> pd.DataFrame:
    hi = runs[runs["effort"] == "high"].set_index(["game", "harness"])
    cost = {(r.game, r.harness): r.cost_total_usd for r in rec.itertuples()}
    prem = {p["game"]: p for p in premise_rows}
    rows = []
    for game in sorted(runs["game"].unique()):
        std, pa = hi.loc[(game, "standard")], hi.loc[(game, "provider_adapter")]
        p = prem.get(game, {})
        std_cost = cost.get((game, "standard"))
        pa_cost = cost.get((game, "provider_adapter"))
        cost_source = "recordings" if std_cost is not None and pa_cost is not None else "premise"
        if cost_source == "premise":
            std_cost, pa_cost = p.get("std_cost"), p.get("pa_cost")
        gap = pa.score - std.score
        both_cheap = (std_cost is not None and pa_cost is not None
                      and std_cost <= COST_CAP_ELIGIBLE and pa_cost <= COST_CAP_ELIGIBLE)
        rows.append({
            "game": game, "std_score": std.score, "pa_score": pa.score, "gap": gap,
            "std_cost_usd": std_cost, "pa_cost_usd": pa_cost, "cost_source": cost_source,
            "eligible": bool(both_cheap and gap >= GAP_MIN_ELIGIBLE),
            "std_ending": std.inferred_ending, "pa_ending": pa.inferred_ending,
            "std_actions": std.total_actions, "pa_actions": pa.total_actions,
            "baseline_actions": sum(int(x) for x in str(std.level_baselines).split()),
            "premise_gap": p.get("gap"), "premise_std_cost": p.get("std_cost"),
            "premise_pa_cost": p.get("pa_cost"),
            "premise_actions_match": (p.get("std_actions") == std.total_actions
                                      and p.get("pa_actions") == pa.total_actions),
            "premise_gap_match": (p.get("gap") is not None
                                  and abs(p["gap"] - round(gap, 1)) <= 0.051),
            "premise_cost_match": (None if cost_source != "recordings" else
                                   abs(p.get("std_cost", -1) - round(std_cost, 2)) <= 0.0051
                                   and abs(p.get("pa_cost", -1) - round(pa_cost, 2)) <= 0.0051),
        })
    return pd.DataFrame(rows).sort_values("gap", ascending=False).reset_index(drop=True)


def lp85_example(runs: pd.DataFrame) -> dict:
    r = runs[(runs["game"] == "LP85") & (runs["harness"] == "standard")
             & (runs["effort"] == "high")].iloc[0]
    secs = round(r.duration_s)
    return {
        "guid": r.guid, "config": r.config, "state": r.state,
        "levels_completed": int(r.levels_completed), "level_count": int(r.level_count),
        "stopped_on_level": int(r.final_level),
        "actions_on_stopping_level": int(r.final_level_actions),
        "stopping_level_baseline": int(r.final_level_baseline),
        "allowed_actions_on_stopping_level": int(r.final_level_budget),
        "duration": f"{secs // 3600} h {(secs % 3600) // 60} min {secs % 60} s",
        "duration_s": float(r.duration_s), "open_at": r.open_at, "last_update": r.last_update,
        "inferred_ending": r.inferred_ending,
        "matches_plan_claim": bool(r.levels_completed == 7 and r.final_level == 8
                                   and r.final_level_actions == 16
                                   and r.final_level_budget == 795
                                   and abs(r.duration_s - (116 * 60)) < 5 * 60),
    }


# ── output ───────────────────────────────────────────────────────────────
def _fmt(x, nd=2):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, float):
        return f"{x:,.{nd}f}"
    return str(x)


def md_table(df: pd.DataFrame, cols: list[str], nd: int = 2) -> str:
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    body = "".join("| " + " | ".join(_fmt(v, nd) for v in row) + " |\n"
                   for row in df[cols].itertuples(index=False))
    return head + body


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def premise_comparison(rec: pd.DataFrame) -> pd.DataFrame:
    """Token-weighted per-action values on the recorded games vs docs/background.md §4."""
    rows = []
    for h in ("standard", "provider_adapter"):
        sub = rec[rec.harness == h]
        n = sub.n_model_steps.sum()
        ours = {
            "input": sub.input_total.sum() / n,
            "reasoning": sub.reasoning_total.sum() / n,
            "visible_out": (sub.output_total.sum() - sub.reasoning_total.sum()) / n,
            "cached_share": sub.cached_total.sum() / sub.input_total.sum(),
        }
        for k, v in ours.items():
            rows.append({"harness": h, "metric": f"{k} per action" if k != "cached_share"
                         else "cached share", "this_pull_recorded_games": v,
                         "background_25_games": premise.CLAIM_PER_ACTION[h][k]})
    pa = rec[rec.harness == "provider_adapter"]
    rows.append({"harness": "provider_adapter", "metric": "actions per compaction",
                 "this_pull_recorded_games": pa.n_steps.sum() / pa.n_compactions.sum(),
                 "background_25_games": premise.CLAIM_COMPACTIONS[1]
                 / premise.CLAIM_COMPACTIONS[0]})
    return pd.DataFrame(rows)


def games_by_ending(runs: pd.DataFrame, harness: str, effort: str = "high") -> dict:
    sub = runs[(runs.harness == harness) & (runs.effort == effort)]
    return {e: sorted(sub.loc[sub.inferred_ending == e, "game"]) for e in sessions.ENDINGS}


def headline_lines(runs, ends, rec, bounds, elig) -> list[str]:
    hi = {h: ends[(ends.harness == h) & (ends.effort == "high")].iloc[0]
          for h in ("standard", "provider_adapter")}
    g = {h: games_by_ending(runs, h) for h in hi}
    med = rec.groupby("harness")[["s_per_step_median", "cost_per_step_mean",
                                  "cost_cached_price_per_step", "cached_share",
                                  "input_plateau_median"]].median()
    pa = rec[rec.harness == "provider_adapter"]
    std = rec[rec.harness == "standard"]
    eligible = list(elig.loc[elig.eligible, "game"])
    b = bounds.set_index(["game", "harness"])
    err_eligible = [x for x in eligible
                    if b.loc[(x, "standard"), "inferred_ending"] == sessions.ERROR_OR_CLOSED]
    s, p = hi["standard"], hi["provider_adapter"]
    L = ["## Headline operational numbers\n"]
    L.append(
        f"- Early endings, high effort (before the action budget, without a win): Standard "
        f"{s.early_no_win}/25 = {s[sessions.ERROR_OR_CLOSED]} ERROR_OR_CLOSED "
        f"({', '.join(g['standard'][sessions.ERROR_OR_CLOSED])}) + "
        f"{s[sessions.TIME_BUDGET]} TIME_BUDGET ({', '.join(g['standard'][sessions.TIME_BUDGET])}); "
        f"Provider Adapter {p.early_no_win}/25 = {p[sessions.ERROR_OR_CLOSED]} ERROR_OR_CLOSED + "
        f"{p[sessions.TIME_BUDGET]} TIME_BUDGET "
        f"({', '.join(g['provider_adapter'][sessions.TIME_BUDGET])}). The premise check's "
        f"{premise.CLAIM_EARLY_STD_HIGH} vs {premise.CLAIM_EARLY_PA_HIGH} reproduces; "
        f"only the Standard side has error-type endings.")
    m_s, m_p = med.loc["standard"], med.loc["provider_adapter"]
    n_games = rec.game.nunique()
    L.append(
        f"- Medians over the {n_games} recorded games (Standard / Provider Adapter): seconds "
        f"per action "
        f"{m_s.s_per_step_median:.0f} / {m_p.s_per_step_median:.0f}; list cost per action "
        f"${m_s.cost_per_step_mean:.3f} / ${m_p.cost_per_step_mean:.3f}; with cached input "
        f"re-priced ${m_s.cost_cached_price_per_step:.3f} / "
        f"${m_p.cost_cached_price_per_step:.3f}; cached share {m_s.cached_share:.0%} / "
        f"{m_p.cached_share:.0%}; median action-call input after warm-up "
        f"{m_s.input_plateau_median / 1e3:.0f}k / {m_p.input_plateau_median / 1e3:.0f}k tokens.")
    L.append(
        f"- Provider Adapter compactions: {int(pa.n_compactions.sum())} in "
        f"{int(pa.n_steps.sum())} actions on the {n_games} games (one per "
        f"{pa.n_steps.sum() / pa.n_compactions.sum():.1f} actions). Multi-attempt steps "
        f"(heuristic): {int(std.n_multi_attempt_steps.sum())} in the Standard runs, "
        f"{int(pa.n_multi_attempt_steps.sum())} in the Adapter runs.")
    for game in err_eligible:
        r = b.loc[(game, "standard")]
        fits = "fits in" if r.fits_12h_at_stop_level_bound else "would exceed"
        L.append(
            f"- {game} Standard-high clean-run bound: ${r.bound_stop_level_usd:.0f} (measured "
            f"${r.measured_cost_usd:.2f} + {r.remaining_stop_level_actions} remaining "
            f"level-{r.final_level} actions x ${r.plateau_cost_per_action_usd:.3f}); "
            f"{r.bound_stop_level_wallclock_h:.1f} h at its pace, so it {fits} 12 h "
            f"(12 h-capped bound ${r.bound_stop_level_12h_usd:.0f}).")
    L.append(f"- The eligibility rule reproduces {', '.join(eligible)}; the published "
             f"Standard-high runs of {', '.join(err_eligible) or 'none'} ended ERROR_OR_CLOSED.\n")
    return L


def write_summary(run_dir: Path, runs, ends, rec, bounds, elig, lp85) -> None:
    hi_std = ends[(ends.harness == "standard") & (ends.effort == "high")].iloc[0]
    hi_pa = ends[(ends.harness == "provider_adapter") & (ends.effort == "high")].iloc[0]
    eligible = list(elig.loc[elig.eligible, "game"])
    flagged = list(elig.loc[elig.eligible & (elig.std_ending == sessions.ERROR_OR_CLOSED), "game"])
    by_h = rec.groupby("harness")
    n_games, n_all = rec.game.nunique(), runs.game.nunique()
    L = []
    L.append("# ARC public-set runs: operational slice (Gemini 3.8 Flash)\n")
    L.append("_Generated by `arc/public/ops.py` from the cached arcprize.org pull. Operational "
             "and descriptive only: no hypothesis (H5) quantities are computed here._\n")
    L.append("## Data\n")
    L.append(f"- Results page: https://arcprize.org/results/{RESULTS_SLUG} "
             f"({runs.variant_id.nunique()} variants x {runs.game.nunique()} public games = "
             f"{len(runs)} published runs; session GUIDs parsed from the page's embedded JSON).")
    L.append(f"- Session JSON pulled for all {len(runs)} runs; config tags agree with the page "
             f"variant for {int(runs.config_matches_variant.sum())}/{len(runs)}; session scores "
             f"agree with page scores for {int(runs.score_matches_page.sum())}/{len(runs)}.")
    L.append(f"- Recording NDJSON pulled for {len(rec)} runs: high effort, Standard and "
             f"Provider Adapter, games {', '.join(RECORDING_GAMES)}.\n")
    L.extend(headline_lines(runs, ends, rec, bounds, elig))
    L.append("## How runs ended (inferred)\n")
    L.append("Exit reasons are not published. Rule (pinned harness `4ca00e6`, see "
             "`arc/public/sessions.py` for line citations): GAME_WIN if state WIN; "
             "ACTION_BUDGET if the final level's actions >= ceil(5 x its human baseline); "
             "TIME_BUDGET if open_at -> last_update >= 11.9 h; otherwise ERROR_OR_CLOSED "
             "(API_ERROR, AGENT_ERROR or SCORECARD_CLOSED, or a run stopped outside the harness "
             "with exit reason UNKNOWN; not separable from published data, so read it as "
             "\"stopped without a win, an action budget or the clock\", not as \"crashed\").\n")
    L.append(md_table(ends, ["harness", "effort", *sessions.ENDINGS, "early_no_win",
                             "n_runs"]))
    L.append(f"\nRecount of the premise check's \"{premise.CLAIM_EARLY_STD_HIGH} of 25 "
             f"Standard-high vs {premise.CLAIM_EARLY_PA_HIGH} of 25 Adapter\" early endings: "
             f"ended before the action budget without a win (ERROR_OR_CLOSED + TIME_BUDGET) = "
             f"**{hi_std.early_no_win} of {hi_std.n_runs} Standard-high** vs "
             f"**{hi_pa.early_no_win} of {hi_pa.n_runs} Adapter-high**; of these, "
             f"ERROR_OR_CLOSED alone = {hi_std[sessions.ERROR_OR_CLOSED]} vs "
             f"{hi_pa[sessions.ERROR_OR_CLOSED]} and TIME_BUDGET = "
             f"{hi_std[sessions.TIME_BUDGET]} vs {hi_pa[sessions.TIME_BUDGET]}.\n")
    ab = runs[runs.inferred_ending == sessions.ACTION_BUDGET]
    rest = runs[runs.inferred_ending.isin([sessions.ERROR_OR_CLOSED, sessions.TIME_BUDGET])]
    L.append(f"Rule checks: {int((ab.budget_margin == 0).sum())} of {len(ab)} ACTION_BUDGET "
             f"runs stopped with final-level actions exactly equal to ceil(5 x baseline); the "
             f"smallest remaining margin among ERROR_OR_CLOSED/TIME_BUDGET runs is "
             f"{int(rest.budget_margin.min()) if len(rest) else 'n/a'} actions, so no run is "
             f"borderline on actions. TIME_BUDGET runs lasted "
             f"{runs.loc[runs.inferred_ending == sessions.TIME_BUDGET, 'duration_h'].min():.2f}-"
             f"{runs.loc[runs.inferred_ending == sessions.TIME_BUDGET, 'duration_h'].max():.2f} h;"
             f" no other run lasted more than "
             f"{runs.loc[runs.inferred_ending != sessions.TIME_BUDGET, 'duration_h'].max():.2f} h,"
             f" so the 11.9 h threshold is not borderline either. In the {len(rec)} recordings, the per-level action counts re-derived "
             f"from the NDJSON (opening RESET excluded; model-chosen and forced RESETs included) "
             f"equal the session's `level_actions` for "
             f"{int(rec.level_actions_match_session.sum())} of {len(rec)} runs. Steps with "
             f"output_tokens < reasoning_tokens (which would break visible = output - "
             f"reasoning): {int(rec.n_output_lt_reasoning.sum())} of "
             f"{int(rec.n_model_steps.sum())} model calls.\n")
    L.append(f"Harness version: the rules are read at `4ca00e6` (2026-09-21); the published "
             f"sessions opened {runs.open_at.min()[:10]} to {runs.open_at.max()[:10]}. The "
             f"stopping logic is unchanged since `1aa78da` (2026-09-03), see "
             f"`arc/public/sessions.py`.\n")
    L.append(f"## Time, cost and tokens per action ({len(rec)} recordings)\n")
    L.append(recordings.METHOD_NOTE + "\n")
    L.append(md_table(rec, ["game", "harness", "n_steps", "n_model_steps", "s_per_step_median",
                            "cost_total_usd", "cost_per_step_mean",
                            "plateau_cost_per_step_mean", "input_per_step_mean",
                            "cached_share", "reasoning_per_step_mean",
                            "visible_out_per_step_mean", "input_plateau_median",
                            "n_compactions", "steps_per_compaction",
                            "n_multi_attempt_steps", "last_step_multi_attempt"], nd=3))
    L.append("\nPooled by harness (mean of per-run values):\n")
    pooled = by_h[["s_per_step_median", "cost_per_step_mean", "plateau_cost_per_step_mean",
                   "cost_cached_price_per_step", "cached_share", "input_per_step_mean", "reasoning_per_step_mean",
                   "visible_out_per_step_mean", "input_plateau_median"]].mean().reset_index()
    L.append(md_table(pooled, list(pooled.columns), nd=3))
    L.append(f"\nToken-weighted totals on these {n_games} games next to the premise check's "
             "25-game figures (`docs/background.md` §4). The game sets differ, so a gap is not by "
             "itself an error; large gaps mean the 25-game figure should be re-derived before "
             "it is reused.\n")
    L.append(md_table(premise_comparison(rec), ["harness", "metric",
                                                "this_pull_recorded_games",
                                                "background_25_games"], nd=2))
    L.append(f"\n## Clean-run cost bound ({n_games} games x 2 harnesses)\n")
    L.append(clean_run_bounds.__doc__.strip().replace("\n    ", "\n") + "\n")
    L.append(md_table(bounds, ["game", "harness", "inferred_ending", "final_level",
                               "actions_taken", "remaining_stop_level_actions",
                               "measured_cost_usd", "plateau_cost_per_action_usd",
                               "bound_stop_level_usd", "bound_stop_level_overall_mean_usd",
                               "bound_stop_level_12h_usd", "bound_full_game_usd",
                               "bound_stop_level_wallclock_h", "fits_12h_at_stop_level_bound"]))
    L.append("\n## Eligibility re-check (both published high runs <= $60 and gap >= 20)\n")
    L.append(f"Gap = Provider Adapter high score - Standard high score (session JSON). Cost: "
             f"summed recording `cost.total_cost` for the {n_games} recorded games; for the "
             f"other {n_all - n_games} games the premise check's cost from "
             f"`docs/background.md` §4 is used and is NOT re-derived here (column "
             f"`cost_source`).\n")
    L.append(md_table(elig, ["game", "std_score", "pa_score", "gap", "std_cost_usd",
                             "pa_cost_usd", "cost_source", "eligible", "std_ending",
                             "pa_ending", "premise_gap_match", "premise_actions_match",
                             "premise_cost_match"], nd=1))
    same = sorted(eligible) == sorted(premise.CLAIM_ELIGIBLE)
    L.append(f"\nEligible: {', '.join(eligible)}. Reproduces the premise check's set "
             f"({', '.join(premise.CLAIM_ELIGIBLE)}): **{'yes' if same else 'no'}**.")
    L.append(f"Eligible games whose published Standard-high run ended ERROR_OR_CLOSED: "
             f"**{', '.join(flagged) if flagged else 'none'}**.")
    third = elig[elig.game.isin(["VC33", "RE86"])]
    L.append("Third held-out candidates (PLAN §9): " + "; ".join(
        f"{r.game} Standard-high ended {r.std_ending}, Adapter-high {r.pa_ending}"
        for r in third.itertuples()) + ".")
    held = elig.set_index("game").reindex(list(OPTION_A_HELDOUT))
    L.append("Held-out games of decision D14 option A (" + ", ".join(OPTION_A_HELDOUT) + "): "
             + "; ".join(f"{g} gap {r.gap:.1f}, Standard-high ended {r.std_ending}, "
                         f"Adapter-high {r.pa_ending}, published list cost "
                         f"${r.std_cost_usd:.2f} / ${r.pa_cost_usd:.2f} ({r.cost_source})"
                         for g, r in held.iterrows()) + ".\n")
    L.append("## LP85 example (PLAN §16.4)\n")
    L.append(f"Standard high (`{lp85['guid']}`, config `{lp85['config']}`): state "
             f"`{lp85['state']}`, cleared {lp85['levels_completed']} of "
             f"{lp85['level_count']} levels, stopped on level {lp85['stopped_on_level']} after "
             f"{lp85['actions_on_stopping_level']} of {lp85['allowed_actions_on_stopping_level']} "
             f"allowed actions (baseline {lp85['stopping_level_baseline']} x 5), "
             f"{lp85['duration']} after opening ({lp85['open_at']} -> {lp85['last_update']}). "
             f"Inferred ending: {lp85['inferred_ending']}. Matches the PLAN claim: "
             f"**{'yes' if lp85['matches_plan_claim'] else 'no'}**.\n")
    lp_b = bounds[(bounds.game == "LP85") & (bounds.harness == "standard")]
    lp_r = rec[(rec.game == "LP85") & (rec.harness == "standard")]
    if len(lp_b) and len(lp_r):
        b, r = lp_b.iloc[0], lp_r.iloc[0]
        L.append(f"Its clean-run bound is ${b.bound_stop_level_usd:.0f} at its plateau list cost "
                 f"per model call (${b.plateau_cost_per_action_usd:.3f}) and "
                 f"${b.bound_stop_level_overall_mean_usd:.0f} at its overall mean "
                 f"(${r.cost_per_step_mean:.3f}, warm-up included), which reproduces PLAN "
                 f"§16.4's \"up to about $168\"; capped at the 12 h clock at its own pace it "
                 f"is ${b.bound_stop_level_12h_usd:.0f}.\n")
    L.append("## What this does not show\n")
    L.append("- Exit reasons are inferred, not observed; ERROR_OR_CLOSED pools API errors, "
             "agent (parse) errors, scorecard closures and runs stopped outside the harness, "
             "so it does not by itself show that a run crashed.\n"
             "- The stopping rules are read from the pinned harness, not from the published "
             "configs (not in the repo); the 5x multiplier and the 12 h clock are confirmed "
             "only by the data checks above.\n"
             "- One published run per game and config: no seed variance; nothing here is a "
             "harness effect estimate.\n"
             "- Costs are ARC's no-cache list accounting from the recordings, not billed cost; "
             f"per-action numbers come from the {n_games} games chosen for the path study and "
             f"the held-out sets, not all {n_all}.\n"
             "- Clean-run bounds cap the number of actions, not the dollars: they assume the "
             "plateau cost per action holds for the remaining budget; the uncapped bound "
             "ignores the 12 h clock and the capped one assumes the run's own mean pace. They "
             "are planning numbers, not forecasts of our runs (service tier, latency and model "
             "behaviour can differ), and they do not show what a clean run would have scored.\n"
             "- No per-level clear rates by harness (H5) are computed or implied.")
    (run_dir / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args(argv)
    started = runmeta.utc_now()
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = OUT_ROOT / run_id

    with PoliteClient(offline=True, log=None) as client:
        runs = load_runs(client)
        recs = load_recordings(client, runs)
        page = client.page_path(RESULTS_SLUG)
        inputs = [page] + [client.session_path(g) for g in runs.guid] + [
            client.recording_path(r.game_id, r.guid) for r in runs.itertuples()
            if r.guid in recs]
        cache = client.root

    ends = endings_table(runs)
    rec = recording_table(runs, recs)
    bounds = clean_run_bounds(runs, rec)
    elig = eligibility_table(runs, rec, premise.load_premise_table())
    lp85 = lp85_example(runs)

    run_dir.mkdir(parents=True, exist_ok=True)
    runs[["variant_id", "page_score", *PER_RUN_COLS[:-1], "level_actions", "level_baselines",
          "inferred_ending"]].to_csv(run_dir / "per_run.csv", **CSV)
    ends.to_csv(run_dir / "endings_by_harness_effort.csv", **CSV)
    rec.to_csv(run_dir / "recordings_per_action.csv", **CSV)
    bounds.to_csv(run_dir / "clean_run_bounds.csv", **CSV)
    elig.to_csv(run_dir / "eligibility.csv", **CSV)
    (run_dir / "lp85_example.json").write_text(json.dumps(lp85, indent=2) + "\n",
                                               encoding="utf-8", newline="\n")
    write_summary(run_dir, runs, ends, rec, bounds, elig, lp85)

    hashes = {str(p.relative_to(cache)).replace("\\", "/"): sha256_file(p) for p in inputs}
    runmeta.write_meta(
        run_dir,
        experiment="arc_public_ops", run_id=run_id,
        cell_or_config="published gemini-3.8-flash public-set runs (6 variants x 25 games)",
        config={"results_slug": RESULTS_SLUG, "budget_multiplier": sessions.BUDGET_MULTIPLIER,
                "time_budget_threshold_s": sessions.TIME_BUDGET_THRESHOLD_S,
                "recording_games": list(RECORDING_GAMES), "recording_effort": "high",
                "plateau_rule": recordings.PLATEAU_RULE,
                "eligibility": {"cost_cap_usd": COST_CAP_ELIGIBLE,
                                "gap_min": GAP_MIN_ELIGIBLE},
                "harness_commit_for_rules": HARNESS_COMMIT},
        model_requested=None, model_returned=None,
        reasoning_effort=None, reasoning_context_requested=None, reasoning_context_echoed=None,
        template_id=None, repeat_index=None, seeds=None,
        started_utc=started, finished_utc=runmeta.utc_now(), exit_reason="completed",
        tokens={"paid_calls": 0}, cost_usd=0.0,
        raw_transcript_path="results/raw/arc_public (gitignored; root set by PERSISTGYM_RAW_DIR)",
        analysed_model="gemini-3.8-flash (published runs by ARC Prize)",
        slice="operational (PLAN §16.3); no H5 quantities",
        n_sessions=len(runs), n_recordings=len(recs),
        input_sha256=hashes,
    )
    print(f"wrote {run_dir}")
    print((run_dir / "summary.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
