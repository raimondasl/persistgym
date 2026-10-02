"""Registered request settings and the engagement check's rule (PREREG §6 as amended by R2,
§17.2).

* `REGISTERED_EFFORT`: the `reasoning.effort` every non-pilot run of a model must send. luna
  stays at `medium` (D13). sol runs at `high` (R2), and only once a blinded engagement check
  has found that its reasoning engages: `ENGAGEMENT_REQUIRED`.
* The engagement check (`harnesses.reasoning_check`, CLI `reasoning-check`) scores two pilot
  runs of sol at high effort, F-r and F-0 on the four D11 far task cells, by E, the share of
  evidence-step calls whose provider-reported reasoning tokens are at least
  `REASONING_TOKEN_FLOOR`, pooled over both arms. Reasoning engages iff E >= `E_THRESHOLD`.
  The check is unscorable when fewer than `MIN_DERIVED_FAR_NORMAL` of its
  `DERIVED_FAR_EPISODES` derived-far episodes end normally, or either run stops on an echo
  mismatch.

`check_run_settings` is the guard `harnesses run` applies before it takes the paid-run lock:
pilots (`persistgym_pilot`) may use any explicit effort; every other experiment (validity runs,
the main sweep, any later one) must send the model's registered effort, and a model in
`ENGAGEMENT_REQUIRED` also needs an ENGAGED `reasoning_check.json` for that model and effort
under results/persistgym_pilot/ and none that says NOT_ENGAGED. The probes keep their own
registered settings (`harnesses.probes.ECHO_CONFIG`, `REPLAY_CONFIG`; PREREG §17.1: medium on
both models) and are not covered here.
"""

from __future__ import annotations

import json
from pathlib import Path

PREREG_REF = "PREREG.md §17.2 (amendment R2)"
PILOT_EXPERIMENT = "persistgym_pilot"

REGISTERED_EFFORT: dict[str, str] = {"gpt-6-luna": "medium", "gpt-6.1-sol": "high"}
"""PREREG §6 (D13) as amended by R2 (§17.2): sol at high, luna at medium."""
DEFAULT_EFFORT = "medium"
"""The effort of a model not in `REGISTERED_EFFORT` (the documented default, D13)."""

ENGAGEMENT_REQUIRED = frozenset({"gpt-6.1-sol"})
"""Models whose non-pilot runs need an ENGAGED engagement check (R2: no sol validity or
main-sweep run, at either effort, unless reasoning engages)."""
ENGAGEMENT_MODEL = "gpt-6.1-sol"
ENGAGEMENT_EFFORT = "high"

REASONING_TOKEN_FLOOR = 32  # an evidence-step call counts toward E at >= 32 reasoning tokens
E_THRESHOLD = 0.50  # reasoning engages iff E >= 0.50
DERIVED_FAR_EPISODES = 8  # 2 derived-far task cells x 2 pilot templates x 2 arms
MIN_DERIVED_FAR_NORMAL = 6  # fewer of the 8 ending normally makes the check unscorable

VERDICTS = ("ENGAGED", "NOT_ENGAGED", "UNSCORABLE")
CHECK_FILE = "reasoning_check.json"


def rule() -> dict:
    """The rule's constants, as every reasoning_check.json records them."""
    return {"prereg": PREREG_REF, "model": ENGAGEMENT_MODEL, "effort": ENGAGEMENT_EFFORT,
            "reasoning_token_floor": REASONING_TOKEN_FLOOR, "e_threshold": E_THRESHOLD,
            "derived_far_episodes": DERIVED_FAR_EPISODES,
            "min_derived_far_ended_normally": MIN_DERIVED_FAR_NORMAL}


def registered_effort(model: str) -> str:
    """The `reasoning.effort` a model's runs send by default and its non-pilot runs must
    send."""
    return REGISTERED_EFFORT.get(model, DEFAULT_EFFORT)


def engagement_refusal(results_root: Path, model: str) -> str | None:
    """Why a non-pilot run of `model` must refuse for want of an engagement check, or None.
    Reads every results/persistgym_pilot/*/reasoning_check.json under `results_root` for this
    model at the registered check effort: any NOT_ENGAGED or unreadable one refuses, and at
    least one ENGAGED one under the registered rule is needed."""
    if model not in ENGAGEMENT_REQUIRED:
        return None
    paths = sorted((results_root / PILOT_EXPERIMENT).glob(f"*/{CHECK_FILE}"))
    engaged, other_rule = [], []
    for path in paths:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            verdict, doc_model, effort = doc["verdict"], doc["model"], doc["effort"]
        except (OSError, ValueError, KeyError, TypeError) as e:
            return (f"cannot read the engagement check {path} ({type(e).__name__}); fix or "
                    "remove it first")
        if (doc_model, effort) != (model, ENGAGEMENT_EFFORT):
            continue
        if verdict == "NOT_ENGAGED":
            return (f"the engagement check {path} found that {model}'s reasoning does not "
                    f"engage at effort {ENGAGEMENT_EFFORT} ({PREREG_REF}): no {model} validity "
                    "or main-sweep run, at either effort, unless a further amendment says so")
        if verdict == "ENGAGED":
            (engaged if doc.get("rule") == rule() else other_rule).append(path)
    if engaged:
        return None
    note = (f"; these say ENGAGED under another rule and do not count: "
            f"{', '.join(str(p) for p in other_rule)}" if other_rule else "")
    return (f"{model}'s non-pilot runs need an ENGAGED engagement check at effort "
            f"{ENGAGEMENT_EFFORT} ({PREREG_REF}), and {results_root / PILOT_EXPERIMENT} has no "
            f"{CHECK_FILE} that says so: run the two check runs and "
            f"`python -m harnesses reasoning-check` first{note}")


def check_run_settings(experiment: str, model: str, effort: str,
                       results_root: Path) -> str | None:
    """Why `harnesses run` must refuse these settings before any paid call, or None. Pilots
    may use any effort; every other experiment sends the model's registered effort, and a
    model in `ENGAGEMENT_REQUIRED` needs an ENGAGED engagement check (`engagement_refusal`)."""
    if experiment == PILOT_EXPERIMENT:
        return None
    want = registered_effort(model)
    if effort != want:
        return (f"{experiment} runs {model} at its registered reasoning effort {want!r} only "
                f"(PREREG §6 as amended by R2, §17.2), got {effort!r}; only "
                f"{PILOT_EXPERIMENT} runs may use another effort")
    return engagement_refusal(results_root, model)
