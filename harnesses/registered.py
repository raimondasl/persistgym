"""Registered request settings, generator config and the engagement check's rule (PREREG §6
as amended by R2, §17.2, and R3, §17.3), and what luna's main sweep may run (§4.6, R6).

* `REGISTERED_EFFORT`: the `reasoning.effort` every non-pilot run of a model must send. luna
  stays at `medium` (D13). sol runs at `high` (R2), and only once a blinded engagement check
  has found that its reasoning engages: `ENGAGEMENT_REQUIRED`.
* `REGISTERED_GENERATOR` (R3): the generator preset (`persistgym.config.PRESETS`) every
  non-pilot run of a model must use. sol uses `sol-chain`, the derived-fact variant whose
  clues are given by chain records and whose evidence steps carry the evidence notice. luna
  is not listed: its pilots keep any config, and its main sweep and controls play the
  default config (`luna_refusal`).
* `REGISTERED_CELLS` (R3): sol runs the H2 core only, F-r and F-0; its exploratory W-n and
  Σ-n replay pairs do not run on the variant, whose notice asks the agent not to write the
  value, which the notes instruction would contradict.
* The engagement check (`harnesses.reasoning_check`, CLI `reasoning-check`) scores two pilot
  runs of sol at high effort, F-r and F-0 on the four D11 far task cells, by E, the share of
  evidence-step calls whose provider-reported reasoning tokens are at least
  `REASONING_TOKEN_FLOOR`, pooled over both arms. Reasoning engages iff E >= `E_THRESHOLD`.
  The check is unscorable when fewer than `MIN_DERIVED_FAR_NORMAL` of its
  `DERIVED_FAR_EPISODES` derived-far episodes end normally, or either run stops on an echo
  mismatch. It runs on pilot templates 0 and 1, and once more on 2 and 3 only if it was
  unscorable there (`CHECK_TEMPLATES`). Each reasoning_check.json is keyed by the generator
  config its runs played (`rule()["generator_config_hash"]`; R2's file, written before R3,
  has none and so belongs to the default config): a check decides only for its own config.
  R2's NOT_ENGAGED check therefore binds the default config only, and R3's check, on
  `sol-chain`, is scored under `rule()`.
* R3's hard stop: a NOT_ENGAGED check on `sol-chain`, or an UNSCORABLE one there twice, ends
  H2 on sol for good: every non-pilot sol run refuses, and so does every further sol pilot
  at an effort above medium (high, and the higher ones: "no further variant or effort").
  So does a G1 failure on the variant: `G1_PASSED` stays empty.
* `G1_PASSED`: model -> the generator config hash on which the researcher recorded G1 as
  passed (§4.4). Each entry is a G1 GO in results/decisions.md, added by a PR the
  researcher merges; a model without one runs no main sweep (fail closed). luna's is the
  default config (G1 GO, 2026-10-09). sol has none, so sol's main sweep refuses. sol's
  validity run (`persistgym_validity`) needs no entry, so it must be exactly a validity run
  (`VALIDITY_RUN`: F-0 on the validity split, restated or withheld; §4.4): a base-variant or
  F-r run there would be H2's contrast before G1.
* luna (§4.6, R6 change 1, §17.6): outside its pilots it runs its main sweep and controls
  only (`luna_refusal`). Its validity runs are finished, with G1 recorded on them, so
  `persistgym_validity` refuses luna: R6 change 1 allows no other paid runs. Its pilots stay
  open (the single-turn control's pilot of at most 10 prompts among them). The main sweep
  and controls are: experiment `persistgym`, the replay-off cells
  `LUNA_CELLS` (F-0, W-0, W-n-0, Σ-n-0; its replay toggle was not verified at G0) or the
  single-turn control (`LUNA_SINGLE_TURN_CELL`), main templates 0 to `LUNA_T` - 1 (T =
  200, §4.2 capped by R6 change 6), base episodes or the restated-at-need control in F-0,
  on the default generator config, with D13's request settings (`LUNA_REQUEST`: --mode
  standard, --service-tier flex, no --W), and only once `G1_PASSED` records luna on that
  config.

* R4 (§17.4), sol's replication of H1: gpt-6.1-sol at `medium` effort on the default
  generator config, with D13's other request settings (`H1_REPLICATION_REQUEST`), in F-0,
  W-0 and W-n-0 on the 4 observed task cells (`OBSERVED_TASK_CELLS`). Its main runs are their
  own experiment, `H1_REPLICATION_EXPERIMENT` (`persistgym_sol_h1`), exactly
  `H1_REPLICATION_RUN` (main split, base variant), and need `REPLICATION_G1_PASSED`, which
  only the researcher's G1 decision PR for the replication sets (fail closed). Its validity
  run is `persistgym_validity` on the default config at medium: exactly `VALIDITY_RUN` on
  validity templates 0-19 and the observed task cells, and it needs no G1. The engagement
  checks and R3's hard stop concern H2 only and are not read for these runs, which can never
  run H2's contrast: no F-r, no `sol-chain`, no derived task cell, no effort above medium.
  Its pilot (W-0 and W-n-0, `H1_REPLICATION_PILOT_CELLS`) runs as any sol pilot at medium
  does, and the pooled pilot report leaves it out (`harnesses.blinding.is_left_out`).

`check_run_settings` is the guard `harnesses run` applies before it takes the paid-run lock:
pilots (`persistgym_pilot`) may use any settings, except that a sol pilot at high effort is
R3's engagement check and must play `sol-chain` in F-r or F-0, and a sol pilot above medium
effort refuses after the hard stop; R4's replication runs must be exactly what R4
registers (`replication_refusal`); every other experiment must send the model's registered
effort, a model in `REGISTERED_GENERATOR` must use its preset and a model in
`REGISTERED_CELLS` one of its cells, sol's validity run must be `VALIDITY_RUN`, a model in
`ENGAGEMENT_REQUIRED` needs an ENGAGED check on that config in the order R2 registers
(`engagement_refusal`), sol's main sweep needs `G1_PASSED`, and luna is held to its main
sweep and controls (`luna_refusal`; its validity runs refuse). A model string counts as a
registered model when it is that model or starts with it and a hyphen (`model_family`, as
`harnesses.pricing.price_for` reads it), so a dated snapshot or alias of sol is sol, and one
of luna is luna. The probes keep their own registered settings
(`harnesses.probes.ECHO_CONFIG`, `REPLAY_CONFIG`; PREREG §17.1: medium on both models) and
are not covered here.
"""

from __future__ import annotations

import json
from pathlib import Path

from harnesses.config import REASONING_EFFORTS
from persistgym.config import PRESET_HASHES
from persistgym.episode import ALL_CELLS

PREREG_REF = "PREREG.md §17.3 (amendment R3)"
R2_REF = "PREREG.md §17.2 (amendment R2)"
R4_REF = "PREREG.md §17.4 (amendment R4)"
PILOT_EXPERIMENT = "persistgym_pilot"
VALIDITY_EXPERIMENT = "persistgym_validity"

REGISTERED_EFFORT: dict[str, str] = {"gpt-6-luna": "medium", "gpt-6.1-sol": "high"}
"""PREREG §6 (D13) as amended by R2 (§17.2): sol at high, luna at medium."""
DEFAULT_EFFORT = "medium"
"""The effort of a model not in `REGISTERED_EFFORT` (the documented default, D13)."""

REGISTERED_GENERATOR: dict[str, str] = {"gpt-6.1-sol": "sol-chain"}
"""PREREG §17.3 (R3): the generator preset of every non-pilot run of these models."""
REGISTERED_CELLS: dict[str, tuple[str, ...]] = {"gpt-6.1-sol": ("F-r", "F-0")}
"""PREREG §17.3 (R3): the only harness cells these models run outside pilots."""
G1_PASSED: dict[str, str] = {
    # The researcher's G1 GO for luna, 2026-10-09: results/decisions.md, "2026-10-09: G1: GO
    # (researcher)", after "G1 gate for gpt-6-luna" (PR #53, branch m1/g1-gate). Its validity
    # runs and spot-check played the default config, 3d6bc648... (PRESET_HASHES["default"]).
    "gpt-6-luna": "3d6bc648eaa9b9e843fe6e70060495cd197630b0f2d585e66b3cd280b7a3968b",
}
"""Model -> the generator config hash on which the researcher recorded G1 (§4.4) as passed.
Each entry is a G1 GO in results/decisions.md, added by a PR the researcher merges. luna:
the default config. sol: none (R3's hard stop), so sol's main sweep refuses (fail closed),
and so does luna's on any other config (`luna_refusal`)."""
VALIDITY_RUN = {"cell": ("F-0",), "split": ("validity",), "variant": ("restated", "withheld")}
"""PREREG §4.4 (§17.3 for sol): a validity run is F-0 on the validity split, restated or
withheld. sol's `persistgym_validity` runs need no `G1_PASSED`, so they are held to exactly
this."""

ENGAGEMENT_REQUIRED = frozenset({"gpt-6.1-sol"})
"""Models whose non-pilot runs need an ENGAGED engagement check (R2: no sol validity or
main-sweep run, at either effort, unless reasoning engages)."""
ENGAGEMENT_MODEL = "gpt-6.1-sol"
ENGAGEMENT_EFFORT = "high"
DEFAULT_GENERATOR_HASH = PRESET_HASHES["default"]
VARIANT_PRESET = REGISTERED_GENERATOR[ENGAGEMENT_MODEL]
VARIANT_GENERATOR_HASH = PRESET_HASHES[VARIANT_PRESET]

H1_REPLICATION_EXPERIMENT = "persistgym_sol_h1"
"""PREREG §17.4 (R4): the experiment of sol's H1 replication's main runs."""
H1_REPLICATION_MODEL = "gpt-6.1-sol"
H1_REPLICATION_EFFORT = "medium"
"""R4: D13's frozen effort, luna's; H1 does not rely on reasoning."""
H1_REPLICATION_GENERATOR_HASH = DEFAULT_GENERATOR_HASH
"""R4: the default generator config, the one luna plays (not `sol-chain`)."""
H1_REPLICATION_RUN = {"cell": ("F-0", "W-0", "W-n-0"), "split": ("main",),
                      "variant": ("base",)}
"""R4: the replication's main runs are luna's H1 rows (§3 H1): F-0, W-0 and W-n-0 on the
main split, base episodes."""
H1_REPLICATION_REQUEST = {"mode": "standard", "service_tier": "flex", "W": None}
"""R4: D13's other request settings as frozen (§6), which `run` takes as --mode,
--service-tier and --W: `reasoning.mode` standard, Flex, and the episode's own W (no --W)."""
H1_REPLICATION_VALIDITY_TEMPLATES = 20
"""R4: the replication's validity run plays validity templates 0-19 only (the templates of
the spot-check package that covers it)."""
H1_REPLICATION_PILOT_CELLS = ("W-0", "W-n-0")
"""R4: the harness cells of the replication's pilot (sol at medium on the default config),
which the pooled pilot report leaves out (`harnesses.blinding.is_left_out`)."""
OBSERVED_TASK_CELLS = tuple(c.id for c in ALL_CELLS if c.fact == "observed")
"""R4: the 4 observed task cells, observed x {near, far} x {R, NR}: every H1 quantity."""
REPLICATION_G1_PASSED: dict[str, str] = {}
"""Model -> the generator config hash on which the researcher recorded the replication's G1
gate (§17.4: sol at medium on the default config, the 4 observed task cells) as passed. Set
only by the researcher's G1 decision PR for the replication; empty, its main runs refuse."""

LUNA_MODEL = "gpt-6-luna"
LUNA_EXPERIMENT = "persistgym"
"""PREREG §4.6, §17.6 change 1: outside its pilots, luna runs its main sweep and controls
only, in experiment `persistgym` (block `3-persistgym`); its validity runs are finished."""
LUNA_CELLS = ("F-0", "W-0", "W-n-0", "Σ-n-0")
"""PREREG §4.6 (row 1), §17.6 change 1: luna's replay-off cells (`Σ-n-0` is `sigma-n-0` on
the command line). Its replay-on cells (F-r, W-n-r, Σ-n-r) and Σ-0-r never run: G0 did not
verify luna's replay toggle (§4.6 row 2)."""
LUNA_SINGLE_TURN_CELL = "single-turn"
"""The cell id `harnesses single-turn` (harnesses/single_turn.py), which sends the
position-matched single-turn control (§3 H3, §4.3), gives this guard: its prompts'
`harness_cell`, `single_turn.RECORD_CELL` (harnesses/tests/test_single_turn.py checks that the
two are the same). It is not a harness cell: one prompt per template, built from base
episodes (`persistgym.controls`)."""
LUNA_RUN = {"split": ("main",), "variant": ("base", "restated")}
"""luna's main sweep plays main templates, base episodes, and the restated-at-need control
(§4.3) as full F-0 episodes (§4.6, D36): --variant restated in cell F-0 only."""
# PREREG §4.2 rule capped at 200 by R6 change 6; recorded in results/decisions.md in this PR
LUNA_T = 200
"""luna's template count T per task cell (§4.2's rule, capped at 200 by R6 change 6, §17.6;
the power re-simulation in results/power_sim/ finds no T <= 200 that meets the rule). Its
main runs and controls play main templates 0 to `LUNA_T` - 1 only: a run whose --start +
--n passes `LUNA_T` refuses (its repeat-1 runs play a subset of that range)."""
LUNA_RESTATED_CELL = "F-0"
LUNA_REQUEST = {"mode": "standard", "service_tier": "flex", "W": None}
"""D13's other request settings as frozen (§6; R6 change 10 keeps luna's effort and Flex
tier), which luna's main runs and controls send and `run` takes as --mode, --service-tier and
--W: `reasoning.mode` standard, Flex, and the episode's own W (no --W; the single-turn control
has none). The same values as R4's `H1_REPLICATION_REQUEST`."""
LUNA_GENERATOR_HASH = DEFAULT_GENERATOR_HASH
"""luna plays the default generator config: the one its validity runs and the G1 spot-check
played (§4.4), on which `G1_PASSED` records its G1."""
R6_REF = "PREREG.md §17.6 (amendment R6)"

REASONING_TOKEN_FLOOR = 32  # an evidence-step call counts toward E at >= 32 reasoning tokens
E_THRESHOLD = 0.50  # reasoning engages iff E >= 0.50
DERIVED_FAR_EPISODES = 8  # 2 derived-far task cells x 2 pilot templates x 2 arms
MIN_DERIVED_FAR_NORMAL = 6  # fewer of the 8 ending normally makes the check unscorable

VERDICTS = ("ENGAGED", "NOT_ENGAGED", "UNSCORABLE")
CHECK_FILE = "reasoning_check.json"
CHECK_TEMPLATES = (("pilot-000000", "pilot-000001"), ("pilot-000002", "pilot-000003"))
"""The check's pilot templates (R2): indices 0 and 1; indices 2 and 3 once more, only after
an UNSCORABLE check on 0 and 1."""
HARD_STOP = (f"R3's hard stop ({PREREG_REF}): H2 on sol is not testable in this task "
             "family; no further variant or effort")
ABOVE_DEFAULT_EFFORT = REASONING_EFFORTS[REASONING_EFFORTS.index(DEFAULT_EFFORT) + 1:]
"""The efforts above medium (high, xhigh, max): after R3's hard stop no sol pilot runs at
any of them ("no further variant or effort is tried")."""


def _r2_rule() -> dict:
    """The rule R2's reasoning_check.json records (§17.2): the same constants, for the
    default generator config, before R3 keyed the files by config."""
    return {"prereg": R2_REF, "model": ENGAGEMENT_MODEL, "effort": ENGAGEMENT_EFFORT,
            "reasoning_token_floor": REASONING_TOKEN_FLOOR, "e_threshold": E_THRESHOLD,
            "derived_far_episodes": DERIVED_FAR_EPISODES,
            "min_derived_far_ended_normally": MIN_DERIVED_FAR_NORMAL}


def rule() -> dict:
    """The rule's constants, as every reasoning_check.json under R3 records them: R2's, with
    R3's reference and the generator config hash of the check's runs (`sol-chain`)."""
    return {**_r2_rule(), "prereg": PREREG_REF, "generator_config_hash": VARIANT_GENERATOR_HASH}


def _rule_for(generator_hash: str) -> dict | None:
    """The rule a check file on `generator_hash` must record to count: R3's on the variant,
    R2's on the default config, none on any other config."""
    return {VARIANT_GENERATOR_HASH: rule(), DEFAULT_GENERATOR_HASH: _r2_rule()}.get(
        generator_hash)


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


def _ref(generator_hash: str) -> str:
    return PREREG_REF if generator_hash == VARIANT_GENERATOR_HASH else R2_REF


def _sequence_refusal(model: str, verdicts: list[tuple[tuple[str, ...], str]],
                      generator_hash: str) -> str | None:
    """R2's order on the checks under the registered rule, one (templates, verdict) per
    template set of `CHECK_TEMPLATES` that has one, in that order: why it does not let
    `model`'s non-pilot runs on `generator_hash` go, or None."""
    first, second = (", ".join(t) for t in CHECK_TEMPLATES)
    ref = _ref(generator_hash)
    got = [v for _, v in verdicts]
    if verdicts and verdicts[0][0] == CHECK_TEMPLATES[1]:
        return (f"an engagement check on {second} counts only after an UNSCORABLE one on "
                f"{first} ({ref})")
    if got in (["ENGAGED"], ["UNSCORABLE", "ENGAGED"]):
        return None
    if got[:1] == ["ENGAGED"]:
        return (f"the engagement check on {first} found ENGAGED, so none was due on {second} "
                f"({ref}); the researcher decides what the second one means")
    if got == ["UNSCORABLE", "UNSCORABLE"]:
        if generator_hash == VARIANT_GENERATOR_HASH:
            return (f"the engagement check was UNSCORABLE on {first} and again on {second}: "
                    f"{HARD_STOP}")
        return (f"the engagement check was UNSCORABLE on {first} and again on {second}: "
                f"nothing runs at effort {ENGAGEMENT_EFFORT}, and the researcher is told "
                f"({ref})")
    then = (f"; it was UNSCORABLE on {first}, so it runs once more on {second}"
            if got == ["UNSCORABLE"] else "")
    return (f"{model}'s non-pilot runs need an ENGAGED engagement check at effort "
            f"{ENGAGEMENT_EFFORT} on generator config {generator_hash[:12]} ({ref}): run the "
            f"two check runs and `python -m harnesses reasoning-check` first{then}")


def _file_hash(doc: dict) -> str:
    """The generator config a check file belongs to; R2's file, without the key, belongs to
    the default config."""
    rule_doc = doc["rule"]
    if not isinstance(rule_doc, dict):
        raise TypeError("rule is not an object")
    return str(rule_doc.get("generator_config_hash", DEFAULT_GENERATOR_HASH))


def engagement_refusal(results_root: Path, model: str, generator_hash: str) -> str | None:
    """Why a non-pilot run of `model` on the generator config `generator_hash` must refuse
    for want of an engagement check, or None. Reads every
    results/persistgym_pilot/*/reasoning_check.json under `results_root` for this model at
    the registered check effort. Any unreadable one refuses. A file on another generator
    config never decides. Of the files on this config, any that says NOT_ENGAGED refuses for
    good (on the variant: R3's hard stop). The others count only under the config's rule
    (`_rule_for`) and decide in R2's order (`_sequence_refusal`): the check on pilot
    templates 0 and 1, then, only if it was UNSCORABLE, the one on 2 and 3 (UNSCORABLE twice
    refuses for good). Two check pairs on the same templates refuse, and so do two files on
    the same pair that disagree."""
    model = model_family(model)
    if model not in ENGAGEMENT_REQUIRED:
        return None
    base = results_root / PILOT_EXPERIMENT
    want = _rule_for(generator_hash)
    ref = _ref(generator_hash)
    checks: dict[tuple[str, ...], dict[tuple[str, ...], str]] = {t: {} for t in CHECK_TEMPLATES}
    other = []
    for path in sorted(base.glob(f"*/{CHECK_FILE}")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            verdict, doc_model, effort = doc["verdict"], str(doc["model"]), doc["effort"]
            templates, pair = tuple(doc["check_templates"]), tuple(doc["check_run_ids"])
            file_hash = _file_hash(doc)
        except (OSError, ValueError, KeyError, TypeError) as e:
            return (f"cannot read the engagement check {path} ({type(e).__name__}); fix or "
                    "remove it first")
        if (model_family(doc_model), effort) != (model, ENGAGEMENT_EFFORT):
            continue
        if file_hash != generator_hash:
            continue  # a check on another generator config never decides for this one
        if verdict == "NOT_ENGAGED":
            if generator_hash == VARIANT_GENERATOR_HASH:
                return f"the engagement check {path} found NOT_ENGAGED: {HARD_STOP}"
            return (f"the engagement check {path} found that {model}'s reasoning does not "
                    f"engage at effort {ENGAGEMENT_EFFORT} on generator config "
                    f"{generator_hash[:12]} ({ref}): no {model} validity or main-sweep run "
                    "on it, at either effort")
        if want is None or doc.get("rule") != want or templates not in checks:
            other.append(path)
            continue
        if checks[templates].setdefault(pair, verdict) != verdict:
            return (f"the engagement check files of runs {list(pair)} disagree ({path}); fix "
                    "or remove the wrong one first")
    verdicts = []
    for templates, pairs in checks.items():
        if len(pairs) > 1:
            return (f"more than one engagement check on {', '.join(templates)} (runs "
                    f"{sorted(map(list, pairs))}); {ref} runs it there once")
        verdicts += [(templates, v) for v in pairs.values()]
    why = _sequence_refusal(model, verdicts, generator_hash)
    if why and other:
        why += (f"; these are under another rule or on other templates and do not count: "
                f"{', '.join(str(p) for p in other)}")
    return why


def hard_stop(results_root: Path, model: str = ENGAGEMENT_MODEL) -> str | None:
    """R3's hard stop, if it has fired: a NOT_ENGAGED check on the variant, or an UNSCORABLE
    one there twice (or an unreadable check file, which refuses until fixed); else None.
    `check_run_settings` applies it to every sol pilot above medium effort."""
    why = engagement_refusal(results_root, model, VARIANT_GENERATOR_HASH)
    if why and (HARD_STOP in why or "cannot read the engagement check" in why):
        return why
    return None


def is_replication_run(experiment: str, model: str, effort: str,
                       generator_hash: str) -> bool:
    """Whether a non-pilot run belongs to R4's sol H1 replication (§17.4) and is judged by
    `replication_refusal`: any run of `H1_REPLICATION_EXPERIMENT`, and a sol run of
    `persistgym_validity` on the default config at medium effort (its validity run). Other
    sol validity runs stay R3's (`sol-chain` at high)."""
    if experiment == H1_REPLICATION_EXPERIMENT:
        return True
    return (experiment == VALIDITY_EXPERIMENT
            and model_family(model) == H1_REPLICATION_MODEL
            and effort == H1_REPLICATION_EFFORT
            and generator_hash == H1_REPLICATION_GENERATOR_HASH)


def _request_wrong(request: dict | None,
                   registered: dict = H1_REPLICATION_REQUEST) -> list[str]:
    """The request settings a run gives otherwise than `registered` (R4's replication runs:
    `H1_REPLICATION_REQUEST`; luna's main runs and controls: `LUNA_REQUEST`); None (not
    given) is wrong."""
    if request is None:
        return ["--mode, --service-tier and --W (not given)"]
    flags = {"mode": "--mode", "service_tier": "--service-tier", "W": "--W"}
    return [f"{flags[k]} {request.get(k)}" for k, want in registered.items()
            if request.get(k) != want]


def _templates_wrong(templates: tuple[int, int] | None) -> list[str]:
    """The replication's validity run plays validity templates 0-19 only: `templates` is the
    run's (first index, last index + 1); None (not given) is wrong."""
    if templates is None:
        return ["validity templates (not given)"]
    start, stop = templates
    if 0 <= start < stop <= H1_REPLICATION_VALIDITY_TEMPLATES:
        return []
    return [f"validity templates {start}-{stop - 1}"]


def replication_refusal(experiment: str, model: str, effort: str, cell: str,
                        generator_hash: str, *, split: str, variant: str,
                        task_cells: tuple[str, ...] | None, request: dict | None = None,
                        templates: tuple[int, int] | None = None) -> str | None:
    """Why a run of R4's sol H1 replication must refuse, or None (§17.4). Its validity run
    (`persistgym_validity`) is exactly `VALIDITY_RUN` on validity templates 0-19
    (`templates`, the run's first index and last index + 1) and its main runs
    (`H1_REPLICATION_EXPERIMENT`) exactly `H1_REPLICATION_RUN`; both play sol at medium
    effort on the default generator config with D13's other request settings
    (`H1_REPLICATION_REQUEST`, `request`), on the observed task cells only (`task_cells`,
    the run's task cells with at least one template). Any of `task_cells`, `request` and,
    for the validity run, `templates` left as None refuses. The main runs also need
    `REPLICATION_G1_PASSED` on that config. The engagement checks and R3's hard stop are
    not read: they concern H2's runs, and these runs cannot run H2's contrast."""
    validity = experiment == VALIDITY_EXPERIMENT
    run = VALIDITY_RUN if validity else H1_REPLICATION_RUN
    got = {"cell": cell, "split": split, "variant": variant}
    wrong = [what for what, bad in (
        (f"model {model}", model_family(model) != H1_REPLICATION_MODEL),
        (f"--effort {effort}", effort != H1_REPLICATION_EFFORT),
        (f"generator config {generator_hash[:12]}",
         generator_hash != H1_REPLICATION_GENERATOR_HASH),
        *((f"{'cell' if k == 'cell' else '--' + k} {got[k]}", got[k] not in run[k])
          for k in ("cell", "split", "variant")),
        (f"task cells {', '.join(task_cells) if task_cells else '(none given)'}",
         not task_cells or not set(task_cells) <= set(OBSERVED_TASK_CELLS))) if bad]
    wrong += _request_wrong(request)
    if validity:
        wrong += _templates_wrong(templates)
    if wrong:
        part = "validity run" if validity else "main runs"
        return (f"{experiment} runs sol's H1 replication's {part} only ({R4_REF}): "
                f"{H1_REPLICATION_MODEL} at --effort {H1_REPLICATION_EFFORT} on the default "
                f"generator config (--gen-preset default, config "
                f"{H1_REPLICATION_GENERATOR_HASH[:12]}), cell {' or '.join(run['cell'])}, "
                f"--split {' or '.join(run['split'])}, --variant {' or '.join(run['variant'])}"
                f"{', templates 0-19' if validity else ''}, on the observed task cells only "
                f"({', '.join(OBSERVED_TASK_CELLS)}), with --mode standard, --service-tier "
                f"flex and no --W (D13); got "
                + "; ".join(wrong))
    if not validity and REPLICATION_G1_PASSED.get(H1_REPLICATION_MODEL) != generator_hash:
        return (f"{experiment} runs only after the researcher has recorded the H1 "
                f"replication's G1 gate (sol at medium on the default config, the observed "
                f"task cells) as passed on generator config {generator_hash[:12]} "
                f"(harnesses/registered.py REPLICATION_G1_PASSED, set by its G1 decision PR; "
                f"{R4_REF})")
    return None


def _luna_templates_wrong(templates: tuple[int, int] | None) -> list[str]:
    """luna's main runs and controls play main templates 0 to `LUNA_T` - 1 only: `templates`
    is the run's (first index, last index + 1); None (not given) is wrong."""
    if templates is None:
        return ["main templates (not given)"]
    start, stop = templates
    if 0 <= start < stop <= LUNA_T:
        return []
    return [f"main templates {start}-{stop - 1}"]


def luna_refusal(experiment: str, cell: str, generator_hash: str, *, split: str,
                 variant: str, request: dict | None = None,
                 templates: tuple[int, int] | None = None) -> str | None:
    """Why a luna run outside `persistgym_pilot` must refuse, or None (§4.6, R6 change 1;
    fail closed). Its validity runs (`persistgym_validity`) refuse: they are finished, G1 is
    recorded on them (`G1_PASSED`), and R6 change 1 allows no other paid runs. Otherwise it
    is luna's main sweep or one of its controls only: experiment `persistgym`, a replay-off
    cell (`LUNA_CELLS`) or the single-turn control (`LUNA_SINGLE_TURN_CELL`), on main
    templates 0 to `LUNA_T` - 1 (`templates`, the run's first index and last index + 1),
    base episodes or the restated-at-need control in F-0 (`LUNA_RUN`), on the default
    generator config, with D13's request settings (`LUNA_REQUEST`), and only once
    `G1_PASSED` records luna's G1 on that config. `request` or `templates` left as None
    refuses."""
    if experiment == VALIDITY_EXPERIMENT:
        return (f"{VALIDITY_EXPERIMENT} runs no {LUNA_MODEL} run any more: luna's validity runs "
                f"are finished and G1 is recorded on them (harnesses/registered.py G1_PASSED; "
                f"results/decisions.md, 2026-10-09: G1: GO), and {R6_REF} change 1 allows no "
                f"other paid runs. luna's pilots stay open as --experiment {PILOT_EXPERIMENT}, "
                f"and its main sweep and controls run as --experiment {LUNA_EXPERIMENT}")
    wrong = [what for what, bad in (
        (f"--experiment {experiment}", experiment != LUNA_EXPERIMENT),
        (f"cell {cell}", cell not in (*LUNA_CELLS, LUNA_SINGLE_TURN_CELL)),
        (f"--split {split}", split not in LUNA_RUN["split"]),
        (f"--variant {variant}", variant not in LUNA_RUN["variant"]),
        (f"--variant {variant} in cell {cell}",
         variant == "restated" and cell != LUNA_RESTATED_CELL),
        (f"generator config {generator_hash[:12]}", generator_hash != LUNA_GENERATOR_HASH))
        if bad]
    wrong += _luna_templates_wrong(templates)
    wrong += _request_wrong(request, LUNA_REQUEST)
    if wrong:
        return (f"outside {PILOT_EXPERIMENT}, {LUNA_MODEL} runs its main sweep and controls "
                f"only ({R6_REF} change 1; PREREG §4.6): --experiment "
                f"{LUNA_EXPERIMENT}, a replay-off cell ({', '.join(LUNA_CELLS)}; luna's "
                f"replay toggle was not verified at G0) or the single-turn control, "
                f"--split main, main templates 0-{LUNA_T - 1} (T = {LUNA_T}: PREREG §4.2's "
                f"rule, capped by R6 change 6), --variant base, or restated in cell "
                f"{LUNA_RESTATED_CELL} (the restated-at-need control), on the default "
                f"generator config (--gen-preset "
                f"default, config {LUNA_GENERATOR_HASH[:12]}), with --mode standard, "
                f"--service-tier flex and no --W (D13); got " + "; ".join(wrong))
    if G1_PASSED.get(LUNA_MODEL) != generator_hash:
        return (f"{experiment} runs {LUNA_MODEL} only after the researcher has recorded G1 "
                f"(PREREG §4.4, §10.2) as passed on generator config {generator_hash[:12]} "
                f"(harnesses/registered.py G1_PASSED, set from the G1 decision in "
                f"results/decisions.md)")
    return None


def check_run_settings(experiment: str, model: str, effort: str, cell: str,
                       generator_hash: str, results_root: Path, *, split: str,
                       variant: str, task_cells: tuple[str, ...] | None = None,
                       request: dict | None = None,
                       templates: tuple[int, int] | None = None) -> str | None:
    """Why `harnesses run` must refuse these settings before any paid call, or None. In
    order:
    1. pilots may use any settings, except a sol pilot at high effort (R3's engagement
       check), which must play the `sol-chain` config in F-r or F-0, and a sol pilot at any
       effort above medium after R3's hard stop;
    R4. a run of sol's H1 replication (`is_replication_run`: any `persistgym_sol_h1` run,
       and a sol `persistgym_validity` run at medium on the default config) must be exactly
       what R4 registers, on the observed task cells (`task_cells`), with D13's request
       settings (`request`) and, for its validity run, on validity templates 0-19
       (`templates`), and its main runs need `REPLICATION_G1_PASSED`
       (`replication_refusal`); steps 2-7 do not apply to it;
    2. every other experiment sends the model's registered effort (a dated snapshot or alias
       counts as its model, `model_family`);
    R6. a luna run is its main sweep or a control, on main templates 0 to `LUNA_T` - 1
       (`templates`) of the default config, with D13's request settings (`request`), after
       `G1_PASSED`, and its validity runs refuse (they are finished: G1 is recorded)
       (`luna_refusal`; §4.6, R6 change 1); steps 3-7 do not apply to it;
    3. a model in `REGISTERED_GENERATOR` uses its preset's config;
    4. a model in `REGISTERED_CELLS` runs one of its cells;
    5. in `persistgym_validity`, a model in `ENGAGEMENT_REQUIRED` runs exactly a validity
       run (`VALIDITY_RUN`: cell F-0, `split` validity, `variant` restated or withheld);
    6. such a model needs an ENGAGED check on that config (`engagement_refusal`);
    7. outside `persistgym_validity`, such a model also needs `G1_PASSED` on that config."""
    family = model_family(model)
    sol = family in ENGAGEMENT_REQUIRED
    if experiment == PILOT_EXPERIMENT:
        if not (sol and effort in ABOVE_DEFAULT_EFFORT):
            return None
        if effort == ENGAGEMENT_EFFORT and generator_hash != VARIANT_GENERATOR_HASH:
            return (f"a {family} pilot at effort {ENGAGEMENT_EFFORT} is {PREREG_REF}'s "
                    f"engagement check: it plays the generator preset {VARIANT_PRESET!r} only "
                    f"(--gen-preset {VARIANT_PRESET}, config {VARIANT_GENERATOR_HASH[:12]}), "
                    f"got config {generator_hash[:12]}")
        if effort == ENGAGEMENT_EFFORT and cell not in REGISTERED_CELLS[ENGAGEMENT_MODEL]:
            return (f"a {family} pilot at effort {ENGAGEMENT_EFFORT} is {PREREG_REF}'s "
                    f"engagement check: it runs in the harness cells "
                    f"{', '.join(REGISTERED_CELLS[ENGAGEMENT_MODEL])} only, got {cell}")
        return hard_stop(results_root, family)
    if is_replication_run(experiment, model, effort, generator_hash):
        return replication_refusal(experiment, model, effort, cell, generator_hash,
                                   split=split, variant=variant, task_cells=task_cells,
                                   request=request, templates=templates)
    replication = (f"; sol's H1 replication ({R4_REF}) runs at --effort "
                   f"{H1_REPLICATION_EFFORT} on the default config, as --experiment "
                   f"{H1_REPLICATION_EXPERIMENT} or its validity run"
                   if family == H1_REPLICATION_MODEL else "")
    want = registered_effort(model)
    if effort != want:
        return (f"{experiment} runs {model} at its registered reasoning effort {want!r} only "
                f"(PREREG §6 as amended by R2, §17.2), got {effort!r}; only "
                f"{PILOT_EXPERIMENT} runs may use another effort{replication}")
    if family == LUNA_MODEL:
        return luna_refusal(experiment, cell, generator_hash, split=split, variant=variant,
                            request=request, templates=templates)
    preset = REGISTERED_GENERATOR.get(family)
    if preset is not None and generator_hash != PRESET_HASHES[preset]:
        return (f"{experiment} runs {family} on the generator preset {preset!r} only "
                f"({PREREG_REF}; --gen-preset {preset}, config {PRESET_HASHES[preset][:12]}), "
                f"got config {generator_hash[:12]}{replication}")
    cells = REGISTERED_CELLS.get(family)
    if cells is not None and cell not in cells:
        return (f"{experiment} runs {family} in the harness cells {', '.join(cells)} only "
                f"({PREREG_REF}), got {cell}")
    got = {"cell": cell, "split": split, "variant": variant}
    if sol and experiment == VALIDITY_EXPERIMENT and any(
            got[k] not in allowed for k, allowed in VALIDITY_RUN.items()):
        return (f"{experiment} runs {family} as its validity run only (PREREG §4.4, "
                f"{PREREG_REF}): cell F-0, --split validity, --variant restated or withheld; "
                f"got cell {cell}, --split {split}, --variant {variant}. Other sol runs "
                "need G1 (harnesses/registered.py G1_PASSED)")
    why = engagement_refusal(results_root, model, generator_hash)
    if why:
        return why
    if sol and experiment != VALIDITY_EXPERIMENT and G1_PASSED.get(family) != generator_hash:
        return (f"{experiment} runs {family} only after the researcher has recorded G1 "
                f"(PREREG §4.4) as passed on generator config {generator_hash[:12]} "
                f"(harnesses/registered.py G1_PASSED, set by the G1 decision PR; "
                f"{PREREG_REF})")
    return None
