"""Parse published session JSON and infer how each run ended (operational, descriptive).

ARC does not publish the harness exit reason (PLAN.md §16.6: "Exit reasons are never sent to
ARC; published runs show only a game state"). We infer it from the session's per-level action
counts, human baselines, game state and timestamps, using the stopping rules of the pinned
harness (arcprize/arc-agi-3-benchmarking @ 4ca00e6):

- ``benchmarking/agent.py`` L140-148: per-level budgets are
  ``math.ceil(b * MAX_ACTIONS_BASELINE_MULTIPLIER)`` for each human baseline ``b``;
  all 15 configs in ``benchmarking/model_configs.yaml`` set the multiplier to 5.0, read at
  L125-127 (the class default at L69 is 2.0, so the config value matters).
- ``benchmarking/agent.py`` L734-751 (``is_done``): stop with ``ExitReason.GAME_WIN`` when the
  state is ``WIN``; stop with ``ExitReason.ACTION_BUDGET`` when the current level's action
  counter reaches its budget. The counter is reset only when ``levels_completed`` rises
  (L723-732) and is incremented for every action, including forced RESETs (L678-679, L767-768).
- ``benchmarking/base.py`` L33 and L90-98: a 12 h wall-clock budget (``MAX_RUNTIME_SECONDS``,
  not set by any config in ``model_configs.yaml``) ends the run with ``ExitReason.TIME_BUDGET``.
  A total cap ``MAX_ACTIONS`` = sum of the level budgets also applies (agent.py L148;
  base.py L86-89, L116-117); hitting it is also reported as ACTION_BUDGET.
- ``benchmarking/base.py`` L112-114 and ``benchmarking/swarm.py`` ``close_scorecard``: any
  exception ends the run with ``API_ERROR`` / ``AGENT_ERROR``, or ``SCORECARD_CLOSED`` if the
  server closed the scorecard. These are indistinguishable in published data, so they are
  pooled as ``ERROR_OR_CLOSED``. ``agent.py`` L1098-1100 raises after ``MAX_RETRIES + 1``
  failed attempts to get a parseable action.

Inference order: GAME_WIN (state WIN) > ACTION_BUDGET (final-level actions >= ceil(5 x
baseline)) > TIME_BUDGET (duration >= 11.9 h) > ERROR_OR_CLOSED.

Checks on the published data (run by ``ops.py``): the server's ``level_actions`` include
model-chosen and forced RESETs but not the opening RESET, the same actions the harness counter
counts (per-level counts re-derived from the 16 recordings match the sessions exactly), and
every run inferred as ACTION_BUDGET has final-level actions exactly equal to its budget
(``budget_margin`` 0), so the rule has no off-by-one slack.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime

BUDGET_MULTIPLIER = 5.0
TIME_BUDGET_S = 12 * 3600
TIME_BUDGET_THRESHOLD_S = 11.9 * 3600

GAME_WIN = "GAME_WIN"
ACTION_BUDGET = "ACTION_BUDGET"
TIME_BUDGET = "TIME_BUDGET"
ERROR_OR_CLOSED = "ERROR_OR_CLOSED"
ENDINGS = (GAME_WIN, ACTION_BUDGET, TIME_BUDGET, ERROR_OR_CLOSED)


def level_budget(baseline: float, multiplier: float = BUDGET_MULTIPLIER) -> int:
    """Per-level action budget exactly as agent.py L144-147 computes it."""
    return math.ceil(baseline * multiplier)


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass
class SessionRun:
    guid: str
    game_id: str
    config: str
    model: str | None
    state: str
    score: float | None
    levels_completed: int
    level_count: int
    total_actions: int
    resets: int | None
    level_actions: list[int]
    level_baselines: list[int]
    open_at: str
    last_update: str
    duration_s: float
    final_level_index: int        # 0-based index of the level the run stopped on
    final_level_actions: int
    final_level_baseline: int
    final_level_budget: int
    budget_margin: int            # final_level_budget - final_level_actions
    inferred_ending: str

    def as_dict(self) -> dict:
        d = asdict(self)
        d["level_actions"] = " ".join(map(str, self.level_actions))
        d["level_baselines"] = " ".join(map(str, self.level_baselines))
        return d


def infer_ending(state: str, final_level_actions: int, final_level_budget: int,
                 duration_s: float, time_threshold_s: float = TIME_BUDGET_THRESHOLD_S) -> str:
    if state == "WIN":
        return GAME_WIN
    if final_level_actions >= final_level_budget:
        return ACTION_BUDGET
    if duration_s >= time_threshold_s:
        return TIME_BUDGET
    return ERROR_OR_CLOSED


def parse_session(session: dict, multiplier: float = BUDGET_MULTIPLIER) -> SessionRun:
    envs = session.get("environments") or []
    if len(envs) != 1:
        raise ValueError(f"expected exactly one environment, got {len(envs)}")
    env = envs[0]
    runs = env.get("runs") or []
    if len(runs) != 1:
        raise ValueError(f"expected exactly one run in {env.get('id')}, got {len(runs)}")
    run = runs[0]

    level_actions = [int(x) for x in run["level_actions"]]
    baselines = [int(x) for x in run["level_baseline_actions"]]
    if len(level_actions) != len(baselines):
        raise ValueError("level_actions and level_baseline_actions differ in length")
    level_count = int(env.get("level_count") or len(baselines))
    if level_count != len(baselines):
        raise ValueError(f"level_count {level_count} != {len(baselines)} baselines")

    total_actions = int(run["actions"])
    if total_actions != sum(level_actions):
        raise ValueError(f"actions {total_actions} != sum(level_actions) {sum(level_actions)}")
    levels_completed = int(run["levels_completed"])
    state = str(run["state"])

    # The level being played when the run stopped. A won game stops on its last level.
    final_idx = min(levels_completed, level_count - 1)
    if state != "WIN" and levels_completed >= level_count:
        raise ValueError("all levels completed but state is not WIN")
    final_actions = level_actions[final_idx]
    final_baseline = baselines[final_idx]
    final_budget = level_budget(final_baseline, multiplier)

    open_at, last_update = session["open_at"], session["last_update"]
    duration = (parse_ts(last_update) - parse_ts(open_at)).total_seconds()
    resets = run.get("resets")
    margin = final_budget - final_actions

    return SessionRun(
        guid=run["guid"],
        game_id=env["id"],
        config=session.get("config") or "",
        model=session.get("model"),
        state=state,
        score=run.get("score"),
        levels_completed=levels_completed,
        level_count=level_count,
        total_actions=total_actions,
        resets=None if resets is None else int(resets),
        level_actions=level_actions,
        level_baselines=baselines,
        open_at=open_at,
        last_update=last_update,
        duration_s=duration,
        final_level_index=final_idx,
        final_level_actions=final_actions,
        final_level_baseline=final_baseline,
        final_level_budget=final_budget,
        budget_margin=margin,
        inferred_ending=infer_ending(state, final_actions, final_budget, duration),
    )


def config_matches(config: str, harness: str, effort: str) -> bool:
    """Does a session's config tag agree with the results-page variant?"""
    is_pa = config.endswith("-provider-adapter")
    eff = config.removesuffix("-provider-adapter").rsplit("-", 1)[-1]
    return is_pa == (harness == "provider_adapter") and eff == effort
