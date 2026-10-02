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
  mismatch. It runs on pilot templates 0 and 1, and once more on 2 and 3 only if it was
  unscorable there (`CHECK_TEMPLATES`).

`check_run_settings` is the guard `harnesses run` applies before it takes the paid-run lock:
pilots (`persistgym_pilot`) may use any explicit effort; every other experiment (validity runs,
the main sweep, any later one) must send the model's registered effort, and a model in
`ENGAGEMENT_REQUIRED` also needs the engagement check to have found ENGAGED in the order R2
registers (`engagement_refusal`). A model string counts as a registered model when it is that
model or starts with it and a hyphen (`model_family`, as `harnesses.pricing.price_for` reads
it), so a dated snapshot or alias of sol is sol. The probes keep their own registered settings
(`harnesses.probes.ECHO_CONFIG`, `REPLAY_CONFIG`; PREREG §17.1: medium on both models) and are
not covered here.
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
CHECK_TEMPLATES = (("pilot-000000", "pilot-000001"), ("pilot-000002", "pilot-000003"))
"""The check's pilot templates (R2): indices 0 and 1; indices 2 and 3 once more, only after
an UNSCORABLE check on 0 and 1."""


def rule() -> dict:
    """The rule's constants, as every reasoning_check.json records them."""
    return {"prereg": PREREG_REF, "model": ENGAGEMENT_MODEL, "effort": ENGAGEMENT_EFFORT,
            "reasoning_token_floor": REASONING_TOKEN_FLOOR, "e_threshold": E_THRESHOLD,
            "derived_far_episodes": DERIVED_FAR_EPISODES,
            "min_derived_far_ended_normally": MIN_DERIVED_FAR_NORMAL}


def model_family(model: str) -> str:
    """The registered model a model string names: the longest `REGISTERED_EFFORT` model that
    it equals or starts with followed by a hyphen (a dated snapshot or alias, as
    `harnesses.pricing.price_for` reads it), else the string itself."""
    best = None
    for name in REGISTERED_EFFORT:
        if (model == name or model.startswith(name + "-")) and len(name) > len(best or ""):
            best = name
    return best or model


def registered_effort(model: str) -> str:
    """The `reasoning.effort` a model's runs send by default and its non-pilot runs must
    send."""
    return REGISTERED_EFFORT.get(model_family(model), DEFAULT_EFFORT)


def _sequence_refusal(model: str, verdicts: list[tuple[tuple[str, ...], str]]) -> str | None:
    """R2's order on the checks under the registered rule, one (templates, verdict) per
    template set of `CHECK_TEMPLATES` that has one, in that order: why it does not let
    `model`'s non-pilot runs go, or None."""
    first, second = (", ".join(t) for t in CHECK_TEMPLATES)
    got = [v for _, v in verdicts]
    if verdicts and verdicts[0][0] == CHECK_TEMPLATES[1]:
        return (f"an engagement check on {second} counts only after an UNSCORABLE one on "
                f"{first} ({PREREG_REF})")
    if got in (["ENGAGED"], ["UNSCORABLE", "ENGAGED"]):
        return None
    if got[:1] == ["ENGAGED"]:
        return (f"the engagement check on {first} found ENGAGED, so none was due on {second} "
                f"({PREREG_REF}); the researcher decides what the second one means")
    if got == ["UNSCORABLE", "UNSCORABLE"]:
        return (f"the engagement check was UNSCORABLE on {first} and again on {second}: "
                f"nothing runs at effort {ENGAGEMENT_EFFORT}, and the researcher is told "
                f"({PREREG_REF})")
    then = (f"; it was UNSCORABLE on {first}, so it runs once more on {second}"
            if got == ["UNSCORABLE"] else "")
    return (f"{model}'s non-pilot runs need an ENGAGED engagement check at effort "
            f"{ENGAGEMENT_EFFORT} ({PREREG_REF}): run the two check runs and "
            f"`python -m harnesses reasoning-check` first{then}")


def engagement_refusal(results_root: Path, model: str) -> str | None:
    """Why a non-pilot run of `model` must refuse for want of an engagement check, or None.
    Reads every results/persistgym_pilot/*/reasoning_check.json under `results_root` for this
    model at the registered check effort. Any unreadable one refuses, and so does any that
    says NOT_ENGAGED. Of the others, those under the registered rule decide in R2's order
    (`_sequence_refusal`): the check on pilot templates 0 and 1, then, only if it was
    UNSCORABLE, the one on 2 and 3. Two check pairs on the same templates refuse, and so do
    two files on the same pair that disagree."""
    model = model_family(model)
    if model not in ENGAGEMENT_REQUIRED:
        return None
    base = results_root / PILOT_EXPERIMENT
    checks: dict[tuple[str, ...], dict[tuple[str, ...], str]] = {t: {} for t in CHECK_TEMPLATES}
    other = []
    for path in sorted(base.glob(f"*/{CHECK_FILE}")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            verdict, doc_model, effort = doc["verdict"], str(doc["model"]), doc["effort"]
            templates, pair = tuple(doc["check_templates"]), tuple(doc["check_run_ids"])
        except (OSError, ValueError, KeyError, TypeError) as e:
            return (f"cannot read the engagement check {path} ({type(e).__name__}); fix or "
                    "remove it first")
        if (model_family(doc_model), effort) != (model, ENGAGEMENT_EFFORT):
            continue
        if verdict == "NOT_ENGAGED":
            return (f"the engagement check {path} found that {model}'s reasoning does not "
                    f"engage at effort {ENGAGEMENT_EFFORT} ({PREREG_REF}): no {model} validity "
                    "or main-sweep run, at either effort, unless a further amendment says so")
        if doc.get("rule") != rule() or templates not in checks:
            other.append(path)
            continue
        if checks[templates].setdefault(pair, verdict) != verdict:
            return (f"the engagement check files of runs {list(pair)} disagree ({path}); fix "
                    "or remove the wrong one first")
    verdicts = []
    for templates, pairs in checks.items():
        if len(pairs) > 1:
            return (f"more than one engagement check on {', '.join(templates)} (runs "
                    f"{sorted(map(list, pairs))}); {PREREG_REF} runs it there once")
        verdicts += [(templates, v) for v in pairs.values()]
    why = _sequence_refusal(model, verdicts)
    if why and other:
        why += (f"; these are under another rule or on other templates and do not count: "
                f"{', '.join(str(p) for p in other)}")
    return why


def check_run_settings(experiment: str, model: str, effort: str,
                       results_root: Path) -> str | None:
    """Why `harnesses run` must refuse these settings before any paid call, or None. Pilots
    may use any effort; every other experiment sends the model's registered effort (a dated
    snapshot or alias counts as its model, `model_family`), and a model in
    `ENGAGEMENT_REQUIRED` needs an ENGAGED engagement check (`engagement_refusal`)."""
    if experiment == PILOT_EXPERIMENT:
        return None
    want = registered_effort(model)
    if effort != want:
        return (f"{experiment} runs {model} at its registered reasoning effort {want!r} only "
                f"(PREREG §6 as amended by R2, §17.2), got {effort!r}; only "
                f"{PILOT_EXPERIMENT} runs may use another effort")
    return engagement_refusal(results_root, model)
