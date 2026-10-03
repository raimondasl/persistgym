"""The engagement check of PREREG §17.2 (amendment R2), as amended by R3 (§17.3): does sol's
reasoning engage at high effort on its derived-fact variant? $0; CLI
`python -m harnesses reasoning-check <run_id> <run_id> [--reference ...]`.

The check runs are two `persistgym_pilot` runs of gpt-6.1-sol at `reasoning.effort: high`,
one in F-r and one in F-0, on the same generated episodes: pilot templates 0 and 1 (2 and 3
for the one re-run after an unscorable check; `registered.CHECK_TEMPLATES`) x the 4 D11 far
task cells (8 episodes per run), rendered with the generator preset `sol-chain` (R3): both
runs' `meta.json` must give exactly the config hash `registered.rule()` records, so no
other design is scored. Reference runs (such as R2's own check runs on the default config)
may use any config. From their raw episodes and transcripts (the gitignored
results/raw/persistgym_pilot/<run_id>/), this module computes the rule's statistic:

* **evidence-step calls:** in each derived-far episode that is not excluded (an echo
  mismatch, PREREG §13), the first step call at each evidence step (the episode's
  `designed.evidence_steps`, the steps whose observation shows a clue or the rule), not a
  lookup result and not a summary call. An episode that stopped early for another reason
  (an API error, the planned spend, the turn limit) counts with the calls it made; no
  episode is re-run;
* **E** = the share of those calls, pooled over both arms and both derived-far task cells,
  whose provider-reported reasoning tokens (`harnesses.pricing.usage_numbers`, as the runner
  counts them) are at least `REASONING_TOKEN_FLOOR` (32);
* **verdict:** `UNSCORABLE` if fewer than 6 of the 8 derived-far episodes ended normally
  (`DONE`, not excluded) or either run stopped on an echo mismatch (`runner.ECHO_ABORTS`);
  otherwise `ENGAGED` iff E >= 0.50, else `NOT_ENGAGED`.

Next to it, descriptive only, it reports for the check runs (and for reference runs, such as
R2's check runs) quantities pooled over both arms: the step calls before the need step with
their reasoning tokens (mean, median, share with at least 1), E with its numerator and
denominator, output tokens, billed cost per episode, errors, the echo-match counts of
`reasoning.context` and `reasoning.effort`, and (R3) how many of the counted evidence-step
calls wrote a value the episode never shows before its need step (`_hidden`: the template's
`persistgym.template.hidden_values`, such as a clue's worked-out value, a running total, a
helper's value or the target, less any number the episode shows) in their visible reply, as
whole numbers matched as in D6: whether the notice's "do not write it" held. The list also
holds the stand-in's values, which a base episode never derives (a reply can hold one only
by chance). No threshold applies to it.

Blinding (PREREG §11). The output is built from explicit allowlists (`OUTPUT_KEYS`,
`POOL_KEYS`). Every number in it pools both arms of a pair: there is no per-arm value, no
need-step quantity (the need step's index only bounds the "before the need step" calls) and
no success or correctness measure. Each raw episode record is cut down to `EPISODE_FIELDS`
and its evidence steps as it is read, so the outcome fields in it (`need_correct`,
`need_phase`, ...) reach no computation; each transcript record is cut down to a `Call`.
Reference runs must also come as one F-r and one F-0 run, so that their pool is never one
arm.

The need step of each episode comes from the generator: each run's episodes are re-generated
from the generator config and episode ids in its `meta.json`, and checked against the
config hashes and evidence steps the run recorded.

`echo_counts` (CLI `echo-count`) counts, from the raw transcripts of PersistGym-stream runs,
the responses and how many echoed the requested `reasoning.context` and `reasoning.effort`,
reading those four echo fields only (PREREG §17.2's block-1 count).
"""

from __future__ import annotations

import gzip
import json
import re
import statistics
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from common import paidlock, runmeta
from harnesses import blinding, registered
from harnesses.items import output_text
from harnesses.matrix import DERIVED_FAR, OBSERVED_FAR
from harnesses.pricing import usage_numbers
from harnesses.runner import ECHO_ABORTS
from persistgym.config import GeneratorConfig
from persistgym.episode import Episode, TaskCell
from persistgym.render import generate
from persistgym.template import hidden_values, sample_template

PILOT_EXPERIMENT = registered.PILOT_EXPERIMENT
CHECK_CELLS = ("F-r", "F-0")
FAR_CELLS = frozenset((*OBSERVED_FAR, *DERIVED_FAR))
BLINDING_NOTE = ("PREREG §11 pilot blinding: every quantity pools both arms (F-r and F-0); no "
                 "per-arm value, need-step quantity or success measure")

EPISODE_FIELDS = ("episode_id", "template_id", "task_cell", "variant", "harness_cell", "model",
                  "exit_reason", "excluded", "cost_usd_list", "cost_usd_billed_est",
                  "n_summary_failures", "n_unparsed_routine", "n_incomplete_routine")
"""The fields read from a raw episode record (plus `designed.evidence_steps`)."""

OUTPUT_KEYS = ("rule", "check_run_ids", "check_templates", "reference_run_ids", "model",
               "effort", "derived_far_episodes", "derived_far_ended_normally",
               "runs_stopped_on_echo_mismatch", "evidence_step_calls",
               "evidence_step_calls_at_floor", "E", "verdict", "verdict_reason", "descriptive",
               "blinding", "generated_utc", "prereg_version", "git_commit", "git_dirty")
"""reasoning_check.json's keys, exactly."""
POOL_KEYS = ("run_ids", "model", "effort", "n_episodes", "derived_far_episodes",
             "derived_far_ended_normally", "runs_stopped_on_echo_mismatch",
             "evidence_step_calls", "evidence_step_calls_at_floor", "E",
             "pre_need_step_calls", "n_calls", "output_tokens", "cost_usd_billed_est",
             "cost_usd_billed_est_per_episode", "errors", "echo_match",
             "evidence_step_replies_with_hidden_value")
"""The keys of each pool under `descriptive` (the check runs; the reference runs), exactly."""


class CheckError(ValueError):
    """The runs given cannot be scored by the check (the CLI refuses with exit code 2)."""


@dataclass(frozen=True)
class Call:
    """What the check reads from one transcript record."""

    episode_id: str
    kind: str
    pending_step: int
    is_lookup_result: bool
    reasoning_tokens: int
    output_tokens: int
    context_ok: bool
    effort_ok: bool
    reply_numbers: frozenset[int] = frozenset()
    """The whole numbers in the visible reply (`items.output_text`), matched as in D6."""


@dataclass
class Run:
    run_id: str
    meta: dict
    episodes: list[dict]  # raw episode records, EPISODE_FIELDS and evidence_steps only
    calls: list[Call]
    design: dict[str, Episode]  # episode id -> the generated episode (need step, evidence)
    hidden: dict[str, frozenset[int]]  # episode id -> what it never shows before need (`_hidden`)

    @property
    def cell(self) -> str:
        return self.meta.get("cell_or_config")


# --- reading -------------------------------------------------------------------------------

def _read_jsonl(path: Path) -> Iterator[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _echo_ok(echo: dict, kind: str) -> bool:
    return echo.get(f"{kind}_requested") == echo.get(f"{kind}_echoed")


_WHOLE_NUMBER = re.compile(r"(?<![0-9A-Za-z])[1-9][0-9]*(?![0-9A-Za-z])")
"""A whole number in a reply, by D6's rule (`survival.whole_word_regex`): not part of a
longer run of digits or letters. A run with a leading zero ("064") is not the value 64
under that rule, so it is not read as one."""
_SHOWN_NUMBER = re.compile(r"(?<![0-9])[1-9][0-9]*(?![0-9])")
"""A number an observation shows, by the reserved-string rule (`filler.Reserved`): not part
of a longer run of digits, whatever letters stand next to it."""


def _call(rec: dict) -> Call:
    response = rec.get("response") or {}
    u = usage_numbers(response.get("usage"))
    echo = rec.get("echo") or {}
    numbers = frozenset(int(x) for x in _WHOLE_NUMBER.findall(output_text(response)))
    return Call(rec["episode_id"], rec["kind"], int(rec["pending_step"]),
                bool(rec["is_lookup_result"]), u["reasoning_tokens"], u["output_tokens"],
                _echo_ok(echo, "context"), _echo_ok(echo, "effort"), numbers)


def _episode(rec: dict) -> dict:
    out = {k: rec.get(k) for k in EPISODE_FIELDS}
    out["evidence_steps"] = list((rec.get("designed") or {}).get("evidence_steps") or [])
    return out


def _design(meta: dict, run_id: str) -> dict[str, Episode]:
    """The run's episodes, re-generated from its meta.json (generator config, episode ids),
    each checked against the config hashes the run recorded."""
    cfg = meta.get("config") or {}
    gen, ids = cfg.get("generator_config"), cfg.get("episode_ids") or []
    if not gen or not ids:
        raise CheckError(f"{run_id}: meta.json has no generator config or episode ids")
    gen_cfg = GeneratorConfig.from_dict(gen)
    by_template: dict[str, list[tuple[str, str]]] = {}
    for eid in ids:
        template, cell, variant = eid.split("/")
        by_template.setdefault(template, []).append((cell, variant))
    out = {}
    for template, pairs in by_template.items():
        split, _, index = template.rpartition("-")
        cells = list(dict.fromkeys(TaskCell.from_id(c) for c, _ in pairs))
        variants = list(dict.fromkeys(v for _, v in pairs))
        for _, eps in generate(split, [int(index)], gen_cfg, cells, variants):
            for ep in eps:
                if ep.config_hash not in cfg.get("generator_config_hashes", []):
                    raise CheckError(f"{run_id}: {ep.episode_id} does not re-generate with the "
                                     "run's generator config")
                out[ep.episode_id] = ep
    missing = set(ids) - set(out)
    if missing:
        raise CheckError(f"{run_id}: episodes {sorted(missing)} do not re-generate")
    return {eid: out[eid] for eid in ids}


def _hidden(meta: dict, design: dict[str, Episode]) -> dict[str, frozenset[int]]:
    """Per episode, the values it never shows before its need step: its template's
    `persistgym.template.hidden_values` (re-sampled with the run's generator config), less
    any number the episode's system prompt or observations before the need step show. On
    `sol-chain` that takes nothing away (the audit `chain_hidden_values_never_shown`); in
    the direct form (a reference run on the default config) it drops a running total that
    the log filler happens to show, since the direct form does not reserve them."""
    cfg = GeneratorConfig.from_dict(meta["config"]["generator_config"])
    by_template = {}
    out = {}
    for eid, ep in design.items():
        if ep.template_id not in by_template:
            split, _, index = ep.template_id.rpartition("-")
            by_template[ep.template_id] = frozenset(
                hidden_values(sample_template(split, int(index), cfg)))
        shown = {int(x) for text in [ep.system_prompt, *(s.observation for s in
                                                         ep.steps[: ep.need_step])]
                 for x in _SHOWN_NUMBER.findall(text)}
        out[eid] = by_template[ep.template_id] - shown
    return out


def load_run(run_id: str, *, results_root: Path, raw_root: Path) -> Run:
    """One pilot run: its meta.json, its raw episode records (allowlisted fields) and the
    calls of its transcript."""
    out_dir = results_root / PILOT_EXPERIMENT / run_id
    raw_dir = raw_root / PILOT_EXPERIMENT / run_id
    try:
        meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
        episodes = [_episode(r) for r in _read_jsonl(raw_dir / "episodes.jsonl")]
        calls = [_call(r) for r in _read_jsonl(raw_dir / "transcript.jsonl.gz")]
    except FileNotFoundError as e:
        raise CheckError(f"{run_id}: {e.filename} is missing") from e
    if meta.get("experiment") != PILOT_EXPERIMENT:
        raise CheckError(f"{run_id}: not a {PILOT_EXPERIMENT} run")
    ids = [e["episode_id"] for e in episodes]
    if len(ids) != len(set(ids)):  # a run id reused: its raw files were appended to
        raise CheckError(f"{run_id}: episodes.jsonl holds an episode more than once")
    design = _design(meta, run_id)
    run = Run(run_id, meta, episodes, calls, design, _hidden(meta, design))
    for e in episodes:
        ep = run.design.get(e["episode_id"])
        if ep is None or e["evidence_steps"] != ep.reveal_steps:
            raise CheckError(f"{run_id}: {e['episode_id']} does not match its generated "
                             "episode")
    return run


# --- the pair checks -------------------------------------------------------------------------

def _pair(runs: list[Run], what: str) -> list[Run]:
    """Two runs of one model, F-r and F-0 (in that order), on the same episodes."""
    if len(runs) != 2 or sorted(str(r.cell) for r in runs) != sorted(CHECK_CELLS):
        raise CheckError(f"{what}: give exactly one F-r run and one F-0 run, so that every "
                         f"figure pools both arms; got cells {[r.cell for r in runs]}")
    runs = sorted(runs, key=lambda r: CHECK_CELLS.index(r.cell))
    models = {r.meta.get("model_requested") for r in runs}
    efforts = {r.meta.get("reasoning_effort") for r in runs}
    if len(models) != 1 or len(efforts) != 1:
        raise CheckError(f"{what}: the two runs differ in model or effort ({sorted(models)}, "
                         f"{sorted(efforts)})")
    if list(runs[0].design) != list(runs[1].design):
        raise CheckError(f"{what}: the two runs did not play the same episodes")
    return runs


def _check_pair(runs: list[Run]) -> list[Run]:
    runs = _pair(runs, "check runs")
    meta = runs[0].meta
    want = [registered.rule()["generator_config_hash"]]
    got = [(r.meta.get("config") or {}).get("generator_config_hashes") for r in runs]
    if any(g != want for g in got):
        raise CheckError(f"check runs: the check scores runs on the generator preset "
                         f"{registered.VARIANT_PRESET!r} only (config {want[0][:12]}; "
                         f"{registered.PREREG_REF}); got configs {got}")
    if (meta.get("model_requested"), meta.get("reasoning_effort")) != (
            registered.ENGAGEMENT_MODEL, registered.ENGAGEMENT_EFFORT):
        raise CheckError(f"check runs: the check scores {registered.ENGAGEMENT_MODEL} at "
                         f"effort {registered.ENGAGEMENT_EFFORT} ({registered.PREREG_REF}); "
                         f"got {meta.get('model_requested')} at "
                         f"{meta.get('reasoning_effort')}")
    eps = list(runs[0].design.values())
    if ({ep.cell.id for ep in eps} != FAR_CELLS
            or _templates(runs[0]) not in registered.CHECK_TEMPLATES
            or len(eps) != len(registered.CHECK_TEMPLATES[0]) * len(FAR_CELLS)
            or any(ep.variant != "base" for ep in eps)):
        raise CheckError(f"check runs: each must play the base episodes of pilot templates "
                         f"{' or '.join(' and '.join(t) for t in registered.CHECK_TEMPLATES)} "
                         f"on the 4 far task cells ({sorted(FAR_CELLS)}; "
                         f"{registered.PREREG_REF})")
    return runs


def _templates(run: Run) -> tuple[str, ...]:
    return tuple(sorted({ep.template_id for ep in run.design.values()}))


# --- the statistic -------------------------------------------------------------------------------

def _usable(run: Run) -> dict[str, dict]:
    """The run's episodes that are not excluded, by id."""
    return {e["episode_id"]: e for e in run.episodes if not e["excluded"]}


def _evidence_calls(run: Run) -> list[Call]:
    out = []
    usable = _usable(run)
    seen: set[tuple[str, int]] = set()
    for c in run.calls:
        e = usable.get(c.episode_id)
        if (e is None or e["task_cell"] not in DERIVED_FAR or c.kind != "step"
                or c.is_lookup_result or c.pending_step not in e["evidence_steps"]
                or (c.episode_id, c.pending_step) in seen):
            continue
        seen.add((c.episode_id, c.pending_step))
        out.append(c)
    return out


def _pre_need_calls(run: Run) -> list[Call]:
    usable = _usable(run)
    return [c for c in run.calls if c.episode_id in usable and c.kind == "step"
            and c.pending_step < run.design[c.episode_id].need_step]


def _share(k: int, n: int) -> float | None:
    return round(k / n, 4) if n else None


def _pool(runs: list[Run]) -> dict:
    """Quantities pooled over both runs of a pair (POOL_KEYS)."""
    eps = [e for r in runs for e in r.episodes]
    derived = sum(ep.cell.id in DERIVED_FAR for r in runs for ep in r.design.values())
    normal = sum(e["task_cell"] in DERIVED_FAR and e["exit_reason"] == "DONE"
                 and not e["excluded"] for e in eps)
    evidence = [c for r in runs for c in _evidence_calls(r)]
    carried = sum(bool(c.reply_numbers & r.hidden[c.episode_id])
                  for r in runs for c in _evidence_calls(r))
    at_floor = sum(c.reasoning_tokens >= registered.REASONING_TOKEN_FLOOR for c in evidence)
    pre = [c.reasoning_tokens for r in runs for c in _pre_need_calls(r)]
    calls = [c for r in runs for c in r.calls]
    billed = [e["cost_usd_billed_est"] for e in eps]
    cost = None if not eps or None in billed else sum(billed)
    out = {
        "run_ids": [r.run_id for r in runs],
        "model": runs[0].meta.get("model_requested"),
        "effort": runs[0].meta.get("reasoning_effort"),
        "n_episodes": len(eps),
        "derived_far_episodes": derived,
        "derived_far_ended_normally": normal,
        "runs_stopped_on_echo_mismatch": sum(r.meta.get("exit_reason") in ECHO_ABORTS
                                             for r in runs),
        "evidence_step_calls": len(evidence),
        "evidence_step_calls_at_floor": at_floor,
        "E": _share(at_floor, len(evidence)),
        "pre_need_step_calls": {
            "n_calls": len(pre),
            "reasoning_tokens_mean": round(statistics.fmean(pre), 3) if pre else None,
            "reasoning_tokens_median": statistics.median(pre) if pre else None,
            "share_with_reasoning": _share(sum(x >= 1 for x in pre), len(pre)),
        },
        "n_calls": len(calls),
        "output_tokens": sum(c.output_tokens for c in calls),
        "cost_usd_billed_est": None if cost is None else round(cost, 6),
        "cost_usd_billed_est_per_episode": None if cost is None else round(cost / len(eps), 6),
        "errors": blinding._errors(eps),
        "echo_match": {"responses": len(calls),
                       "context_matched": sum(c.context_ok for c in calls),
                       "effort_matched": sum(c.effort_ok for c in calls)},
        # R3 (§17.3), descriptive: did "do not write it" hold at the evidence steps?
        "evidence_step_replies_with_hidden_value": {"calls": len(evidence),
                                                    "with_hidden_value": carried},
    }
    assert tuple(out) == POOL_KEYS
    return out


def verdict(pool: dict) -> tuple[str, str]:
    """The rule of PREREG §17.2 on a check pool: (verdict, reason)."""
    floor, threshold = registered.REASONING_TOKEN_FLOOR, registered.E_THRESHOLD
    n, k = pool["evidence_step_calls"], pool["evidence_step_calls_at_floor"]
    why = []
    if pool["derived_far_ended_normally"] < registered.MIN_DERIVED_FAR_NORMAL:
        why.append(f"{pool['derived_far_ended_normally']} of {pool['derived_far_episodes']} "
                   f"derived-far episodes ended normally (at least "
                   f"{registered.MIN_DERIVED_FAR_NORMAL} needed)")
    if pool["runs_stopped_on_echo_mismatch"]:
        why.append(f"{pool['runs_stopped_on_echo_mismatch']} run(s) stopped on an echo "
                   "mismatch")
    if not why and n == 0:
        why.append("no evidence-step calls")
    if why:
        return "UNSCORABLE", "; ".join(why)
    e = f"E = {k}/{n} = {k / n:.4f} (evidence-step calls with >= {floor} reasoning tokens)"
    if Fraction(k, n) >= Fraction(str(threshold)):
        return "ENGAGED", f"{e} >= {threshold:.2f}"
    return "NOT_ENGAGED", f"{e} < {threshold:.2f}"


def check(check_run_ids: list[str], reference_run_ids: Iterable[str] = (), *,
          results_root: Path, raw_root: Path) -> dict:
    """reasoning_check.json for the two check runs (and the reference runs, descriptive
    only). Raises CheckError when the runs cannot be scored by the check."""
    check_run_ids, reference_run_ids = list(check_run_ids), list(reference_run_ids)
    if len(set(check_run_ids) | set(reference_run_ids)) != len(check_run_ids) + len(
            reference_run_ids):
        raise CheckError("a run is given twice")

    def load(ids):
        return [load_run(i, results_root=results_root, raw_root=raw_root) for i in ids]
    runs = _check_pair(load(check_run_ids))
    reference = _pair(load(reference_run_ids), "reference runs") if reference_run_ids else None
    if reference and reference[0].meta.get("model_requested") != registered.ENGAGEMENT_MODEL:
        raise CheckError(f"reference runs: {registered.ENGAGEMENT_MODEL} runs only")
    pool = _pool(runs)
    if pool["derived_far_episodes"] != registered.DERIVED_FAR_EPISODES:
        raise CheckError(f"check runs: {pool['derived_far_episodes']} derived-far episodes, "
                         f"the rule needs {registered.DERIVED_FAR_EPISODES}")
    result, reason = verdict(pool)
    out = {
        "rule": registered.rule(),
        "check_run_ids": pool["run_ids"],
        "check_templates": list(_templates(runs[0])),
        "reference_run_ids": [r.run_id for r in reference] if reference else [],
        "model": pool["model"],
        "effort": pool["effort"],
        "derived_far_episodes": pool["derived_far_episodes"],
        "derived_far_ended_normally": pool["derived_far_ended_normally"],
        "runs_stopped_on_echo_mismatch": pool["runs_stopped_on_echo_mismatch"],
        "evidence_step_calls": pool["evidence_step_calls"],
        "evidence_step_calls_at_floor": pool["evidence_step_calls_at_floor"],
        "E": pool["E"],
        "verdict": result,
        "verdict_reason": reason,
        "descriptive": {"check": pool, "reference": _pool(reference) if reference else None},
        "blinding": BLINDING_NOTE,
        "generated_utc": runmeta.utc_now(),
        "prereg_version": runmeta.prereg_version(),
        **runmeta.git_state(),
    }
    assert tuple(out) == OUTPUT_KEYS and result in registered.VERDICTS
    return out


# --- echo counts ---------------------------------------------------------------------------------

PERSISTGYM_EXPERIMENTS = tuple(e for e, s in paidlock.EXPERIMENT_STREAM.items()
                               if s == paidlock.PERSISTGYM)


def _echoes(rec: dict) -> list[dict]:
    """The echo dicts of one transcript record: one per request (`run_batch`) or one per
    response of a probe trial (`echoes`)."""
    return [rec["echo"]] if "echo" in rec else list(rec.get("echoes") or [])


def echo_counts(raw_root: Path, experiments: Iterable[str] = PERSISTGYM_EXPERIMENTS) -> dict:
    """Per run under results/raw/<experiment>/, and in total: responses, and how many echoed
    the requested `reasoning.context` and `reasoning.effort`. Only those four echo fields are
    read from each record."""
    runs: dict[str, dict] = {}
    total = {"responses": 0, "context_matched": 0, "effort_matched": 0}
    for exp in experiments:
        for path in sorted((raw_root / exp).glob("*/transcript.jsonl.gz")):
            d = {"responses": 0, "context_matched": 0, "effort_matched": 0}
            for rec in _read_jsonl(path):
                for echo in _echoes(rec):
                    d["responses"] += 1
                    d["context_matched"] += _echo_ok(echo, "context")
                    d["effort_matched"] += _echo_ok(echo, "effort")
            runs[f"{exp}/{path.parent.name}"] = d
            for k in total:
                total[k] += d[k]
    return {"experiments": list(experiments), "runs": runs, "total": total}
