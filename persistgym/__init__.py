"""PersistGym-lite: a generated environment that varies whether the state an agent needs is
observed or derived, recoverable or not, and near or far from where it is needed, at a fixed
volume per observation (PLAN.md §5). See persistgym/DESIGN.md.

Typical use:

    from persistgym import GeneratorConfig, ALL_CELLS, sample_template, render_template
    cfg = GeneratorConfig()
    t = sample_template("main", 0, cfg)
    episodes = render_template(t, cfg, ALL_CELLS, ("base", "restated", "withheld"))
"""

from persistgym.config import DEFAULT_CONFIG, RESEARCHER_DECISIONS, GeneratorConfig
from persistgym.controls import score_single_turn, single_turn_control
from persistgym.env import EpisodeEnv, EpisodeResult, parse_action
from persistgym.episode import ALL_CELLS, VARIANTS, Episode, Step, TaskCell, read_jsonl
from persistgym.oracle import KeyOracle, TextOracle, run_episode
from persistgym.render import generate, render_template
from persistgym.survival import (
    carried_in_text,
    designed_survival,
    survival_from_payload,
    window_keep_start,
)
from persistgym.template import sample_template

__all__ = [
    "ALL_CELLS",
    "DEFAULT_CONFIG",
    "RESEARCHER_DECISIONS",
    "VARIANTS",
    "Episode",
    "EpisodeEnv",
    "EpisodeResult",
    "GeneratorConfig",
    "KeyOracle",
    "Step",
    "TaskCell",
    "TextOracle",
    "carried_in_text",
    "designed_survival",
    "generate",
    "parse_action",
    "read_jsonl",
    "render_template",
    "run_episode",
    "sample_template",
    "score_single_turn",
    "single_turn_control",
    "survival_from_payload",
    "window_keep_start",
]
