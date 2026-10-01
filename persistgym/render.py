"""Render a template into episodes: 8 task cells x variants {base, restated, withheld}.

All cells of one template share the need step index, the option list, the correct letter,
the routine events and the log filler of every step index. They differ only in where the
target components are revealed (near / far), how (observed / derived) and whether lookup is
available (recoverable). Observations of identical (step, event) pairs are byte-identical
across cells.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from datetime import timedelta
from functools import lru_cache

from common.runmeta import config_hash
from persistgym import tokens
from persistgym.config import GENERATOR_VERSION, SCHEMA_VERSION, GeneratorConfig
from persistgym.episode import (
    ALL_CELLS,
    VARIANTS,
    Component,
    Episode,
    LookupSpec,
    Option,
    Step,
    TaskCell,
)
from persistgym.filler import (
    LOG_FOOT,
    LOG_HEAD,
    FitError,
    Fitted,
    Pool,
    fit_observation,
    make_pool,
)
from persistgym.graph import build_graph
from persistgym.survival import episode_design
from persistgym.template import LABELS, Template, rng, sample_template, split_of_seed

EVENT_PREFIX = "EVENT: "


class GenerationError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Sentence frames (the oracle and the audits parse these; change them together)
# ---------------------------------------------------------------------------

def fact_sentence(kind: str, entity: str, name: str, value: int) -> str:
    return f"For {kind} {entity}, the {name} is {value}."


def rule_sentence(kind: str, quantity: str, names: list[str]) -> str:
    return f"Rule: for every {kind}, {quantity} = {' + '.join(names)}."


def need_event(kind: str, entity: str, quantity: str, verb: str, options: list[Option]) -> str:
    lines = [f"{kind.capitalize()} {entity} needs its {quantity} now. Options:"]
    lines += [f"{o.label}) {o.value}" for o in options]
    lines.append(f"Reply {verb}(<letter>) with the letter of the correct option.")
    return "\n".join(lines)


def memo_event(record: str, record_id: str) -> str:
    return f"{record} Reply ack({record_id}) to acknowledge it."


def lookup_key_matches(key: str, entity: str) -> bool:
    """A lookup key matches if it contains the entity name as a whole word, ignoring case
    ("BEECH", "beech", "sample BEECH" all match; "BEECHES" does not). With one entity per
    episode (k=1) this is unambiguous, and it keeps formatting slips such as
    lookup(sample BEECH) from costing extra turns that are not about memory."""
    return bool(re.search(rf"(?<![A-Za-z]){re.escape(entity)}(?![A-Za-z])", key, re.IGNORECASE))


def restated_block(kind: str, entity: str, record_lines: list[str]) -> str:
    return f"Records on file for {kind} {entity}:\n" + "\n".join(record_lines) + "\n"


def system_prompt_text(cfg: GeneratorConfig, facility: str, site: str, kind: str,
                       recoverable: bool, rule: str | None) -> str:
    lines = [
        f"You are the operator of the {facility} at {site}.",
        ("Each user message is a console update: a tail of recent system logs, then one EVENT. "
         "The logs are routine background output and never need a response."),
        ("Read the EVENT and reply with exactly one action. Put it on the last line of your "
         "reply in the form:"),
        "ACTION: <action>",
        "Use the exact action syntax that the EVENT asks for.",
    ]
    if cfg.warn_future_need:
        lines.append("Some requests depend on records shown in earlier updates.")
    if recoverable:
        lines.append(
            f"Records about a {kind} can be shown again: reply ACTION: lookup(<{kind} name>) "
            "and the records appear in the next update, followed by the pending EVENT again. "
            f"Each lookup uses up one turn; at most {cfg.lookup_max_per_episode} lookups are "
            "allowed per session.")
    if rule:
        lines.append(f"Standing procedure: {rule}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

def component_ids(fact: str, n_clues: int) -> list[str]:
    if fact == "observed":
        return ["fact"]
    return [f"clue{i}" for i in range(n_clues)] + ["rule"]


def schedule(t: Template, cell: TaskCell, cfg: GeneratorConfig) -> dict[str, int | None]:
    """Reveal step of every component. The latest reveal is gap steps before need."""
    n = t.need_index
    g = cfg.near_gap_steps if cell.distance == "near" else cfg.far_gap_steps
    s = cfg.clue_spacing_steps
    if cell.fact == "observed":
        return {"fact": n - g}
    clues = [f"clue{i}" for i in range(t.n_clues)]
    steps: dict[str, int | None] = {}
    if cfg.rule_placement == "separate_step":
        steps["rule"] = n - g
        for i, cid in enumerate(reversed(clues)):
            steps[cid] = n - g - (i + 1) * s
    else:
        for i, cid in enumerate(clues):
            steps[cid] = n - g - (len(clues) - 1 - i) * s
        steps["rule"] = {"with_last_clue": steps[clues[-1]], "with_first_clue": steps[clues[0]],
                         "system_prompt": None}[cfg.rule_placement]
    return {cid: steps[cid] for cid in [*clues, "rule"]}


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class TemplateRenderer:
    def __init__(self, template: Template, cfg: GeneratorConfig):
        self.t = template
        self.cfg = cfg
        self.skin = template.skin_obj
        self.reserved = template.reserved
        self.config_dict = cfg.to_dict()
        self.config_hash = config_hash(self.config_dict)
        self._pools: dict[tuple, Pool] = {}
        self._obs: dict[tuple, Fitted] = {}

    # -- clock and filler -------------------------------------------------
    def step_time(self, t: int):
        return self.t.t0_dt + timedelta(seconds=t * self.cfg.step_seconds)

    def _pool(self, key: tuple) -> Pool:
        """Filler pool for one observation slot: ("step", t) or ("lookup", t, j) (cached).

        Step t's lines have clock times in (T(t-1), T(t)]; lookup j at pending step t uses
        a short slot after T(t)."""
        if key not in self._pools:
            cfg = self.cfg
            if key[0] == "step":
                hi = self.step_time(key[1])
                lo = hi - timedelta(seconds=cfg.step_seconds)
            else:  # ("lookup", pending_step, lookup_no)
                slot = max(1, cfg.step_seconds // (cfg.lookup_max_per_episode + 2))
                lo = self.step_time(key[1]) + timedelta(seconds=key[2] * slot)
                hi = lo + timedelta(seconds=slot)
            r = rng(self.t.seed, "filler:" + ":".join(map(str, key)))
            n_lines = cfg.v_tokens // 12 + 20
            lines = make_pool(r, self.skin.services, self.reserved, lo, hi, n_lines)
            self._pools[key] = Pool(lines, cfg.tokenizer)
        return self._pools[key]

    def observation(self, pool_key: tuple, clock, event: str) -> Fitted:
        key = (pool_key, clock, event)
        if key not in self._obs:
            head = f"=== console update {clock.strftime('%H:%M:%S')} ===\n" + LOG_HEAD
            foot = LOG_FOOT + EVENT_PREFIX + event
            try:
                self._obs[key] = fit_observation(
                    head, self._pool(pool_key), foot, self.cfg.v_tokens, self.reserved,
                    self.cfg.tokenizer, self.cfg.token_tolerance)
            except FitError as e:
                raise GenerationError(f"{self.t.template_id} {pool_key}: {e}") from e
        return self._obs[key]

    # -- components -------------------------------------------------------
    def _components(self, cell: TaskCell, steps: dict[str, int | None]) -> list[Component]:
        t, sk = self.t, self.skin
        kind, ent = sk.kind, t.entity
        if cell.fact == "observed":
            sent = fact_sentence(kind, ent, sk.quantity, t.target_value)
            return [Component("fact", "fact", sk.quantity, t.target_value, sent, "", steps["fact"])]
        comps = []
        names = list(sk.components[: t.n_clues])
        for i in range(t.n_clues):
            sent = fact_sentence(kind, ent, names[i], t.clue_values[i])
            comps.append(Component(f"clue{i}", "clue", names[i], t.clue_values[i], sent, "",
                                   steps[f"clue{i}"]))
        comps.append(Component("rule", "rule", sk.quantity, None,
                               rule_sentence(kind, sk.quantity, names), "", steps["rule"]))
        return comps

    def _records(self, comps: list[Component]) -> tuple[dict[int, str], dict[int, str]]:
        """Record line and record id per reveal step; fills Component.record in place."""
        by_step: dict[int, list[Component]] = {}
        for c in comps:
            if c.step is not None:
                by_step.setdefault(c.step, []).append(c)
        lines, ids = {}, {}
        for st, cs in sorted(by_step.items()):
            first = cs[0]
            src_i = int(first.comp_id[-1]) if first.role == "clue" else 0
            rid = self.t.record_ids[first.comp_id]
            line = f"{self.skin.sources[src_i]} {rid}. " + " ".join(c.sentence for c in cs)
            for c in cs:
                c.record = line
            lines[st], ids[st] = line, rid
        return lines, ids

    def _null_records(self, steps: dict[str, int | None]) -> tuple[dict[int, str], dict[int, str]]:
        lines, ids = {}, {}
        reveal = sorted({s for s in steps.values() if s is not None})
        cids = [cid for cid, s in steps.items() if s is not None]
        for i, st in enumerate(reveal):
            cid = next(c for c in cids if steps[c] == st)
            src_i = int(cid[-1]) if cid.startswith("clue") else 0
            rid = self.t.record_ids[cid]
            sent = self.skin.null_records[self.t.null_choice[i]].format(
                Kind=self.skin.kind.capitalize(), E=self.t.entity)
            lines[st], ids[st] = f"{self.skin.sources[src_i]} {rid}. {sent}", rid
        return lines, ids

    def options(self) -> list[Option]:
        return [Option(LABELS[i], v) for i, v in enumerate(self.t.option_values)]

    # -- episode ----------------------------------------------------------
    def render(self, cell: TaskCell, variant: str = "base") -> Episode:
        if variant not in VARIANTS:
            raise ValueError(f"variant must be one of {VARIANTS}")
        t, sk, cfg = self.t, self.skin, self.cfg
        n = t.need_index
        steps_of = schedule(t, cell, cfg)
        reveal_steps = [s for s in steps_of.values() if s is not None]
        if reveal_steps and min(reveal_steps) < cfg.lead_in_min_steps:
            raise GenerationError(f"{t.template_id} {cell.id}: reveal before lead-in")

        comps = self._components(cell, steps_of)
        rec_lines, rec_ids = self._records(comps)
        if variant == "withheld":
            shown_lines, shown_ids = self._null_records(steps_of)
        else:
            shown_lines, shown_ids = rec_lines, rec_ids
        options = self.options()
        need_ev = need_event(sk.kind, t.entity, sk.quantity, sk.need_verb, options)
        restates: list[str] = []
        if variant == "restated":
            if cfg.restate_mode == "as_revealed":
                block_lines = [rec_lines[s] for s in sorted(rec_lines)]
                if cell.fact == "derived" and steps_of.get("rule") is None:
                    block_lines.append(next(c.sentence for c in comps if c.role == "rule"))
            else:
                block_lines = [fact_sentence(sk.kind, t.entity, sk.quantity, t.target_value)]
            need_ev = restated_block(sk.kind, t.entity, block_lines) + need_ev
            restates = [c.comp_id for c in comps]

        rule_in_prompt = cell.fact == "derived" and steps_of.get("rule") is None
        rule_text = next((c.sentence for c in comps if c.role == "rule"), None)
        system = system_prompt_text(cfg, sk.facility, t.site, sk.kind, cell.recoverable,
                                    rule_text if rule_in_prompt else None)

        steps: list[Step] = []
        for i in range(t.n_steps):
            clock = self.step_time(i)
            if i == n:
                kind, rtype, event = "need", None, need_ev
                expected = f"{sk.need_verb}({t.correct_label})"
            elif i in shown_lines:
                kind, rtype = "reveal", "memo"
                event = memo_event(shown_lines[i], shown_ids[i])
                expected = f"ack({shown_ids[i]})"
            else:
                spec = t.routine[i]
                kind, rtype, event, expected = "routine", spec.type, spec.event, spec.expected_action
            fitted = self.observation(("step", i), clock, event)
            reveals = ([c.comp_id for c in comps if c.step == i] if variant != "withheld" else [])
            steps.append(Step(
                index=i, kind=kind, routine_type=rtype, event=event, observation=fitted.text,
                obs_tokens=fitted.n_tokens, event_start=len(fitted.text) - len(event),
                event_end=len(fitted.text), filler_start=fitted.filler_start,
                filler_end=fitted.filler_end, expected_action=expected, reveals=reveals,
                restates=restates if i == n else [], sim_time=clock.isoformat()))

        carried = comps if variant != "withheld" else []
        lookup_records = ({c.comp_id: c.record for c in carried if c.step is not None}
                          if variant != "withheld" else
                          {f"null{k}": shown_lines[s] for k, s in enumerate(sorted(shown_lines))})
        lookup_steps = ({c.comp_id: c.step for c in carried if c.step is not None}
                        if variant != "withheld" else
                        {f"null{k}": s for k, s in enumerate(sorted(shown_lines))})
        lookup = LookupSpec(available=cell.recoverable, key=t.entity,
                            syntax=f"lookup(<{sk.kind} name>)",
                            max_per_episode=cfg.lookup_max_per_episode,
                            records=lookup_records, reveal_steps=lookup_steps)
        graph = build_graph(
            t.n_steps, n,
            [{"comp_id": c.comp_id, "role": c.role, "step": c.step} for c in carried],
            cell.fact, cell.recoverable, rule_in_system_prompt=rule_in_prompt)
        system_tokens = tokens.count(system, cfg.tokenizer)
        obs_tokens = [s.obs_tokens for s in steps]
        design = episode_design(
            obs_tokens, n, {c.comp_id: c.step for c in carried}, W=cfg.W_tokens,
            v=cfg.v_tokens, far_margin_tokens=cfg.far_margin_tokens,
            assumed_reply_tokens=cfg.assumed_max_reply_tokens, system_tokens=system_tokens,
            count_system=cfg.window_counts_system_prompt)
        design["restated_at_need"] = variant == "restated"
        design["rule_in_system_prompt"] = rule_in_prompt

        ep = Episode(
            schema_version=SCHEMA_VERSION, generator_version=GENERATOR_VERSION,
            config_hash=self.config_hash, config=self.config_dict,
            episode_id=f"{t.template_id}/{cell.id}/{variant}", template_id=t.template_id,
            template_seed=t.seed, split=t.split, cell=cell, variant=variant, skin=sk.name,
            kind=sk.kind, entity=t.entity, quantity=sk.quantity, need_verb=sk.need_verb,
            system_prompt=system, system_tokens=system_tokens, steps=steps, need_step=n,
            n_clues=t.n_clues if cell.fact == "derived" else 0, components=carried,
            target_value=t.target_value, options=options, correct_label=t.correct_label,
            lookup=lookup, graph=graph, design=design)
        validate_episode(ep, cfg)
        return ep

    # -- lookup -------------------------------------------------------------
    def lookup_observation(self, ep: Episode, pending_step: int, lookup_no: int,
                           key: str) -> tuple[str, int, str]:
        """Observation shown after a lookup(key) at `pending_step` (see env.EpisodeEnv)."""
        sk = self.skin
        safe_key = "".join(ch for ch in key if ch.isalnum() or ch in " _-")[:40].strip()
        if lookup_key_matches(safe_key, ep.lookup.key):
            lines: list[str] = []
            for cid, st in sorted(ep.lookup.reveal_steps.items(), key=lambda kv: (kv[1], kv[0])):
                if st <= pending_step and ep.lookup.records[cid] not in lines:
                    lines.append(ep.lookup.records[cid])
            if lines:
                body = f"LOOKUP RESULT for {sk.kind} {ep.entity}:\n" + "\n".join(lines)
            else:
                body = f"LOOKUP RESULT for {sk.kind} {ep.entity}: no records yet."
        else:
            body = f"LOOKUP RESULT for '{safe_key}': no records found."
        event = body + "\nPending request (repeated): " + ep.steps[pending_step].event
        slot = max(1, self.cfg.step_seconds // (self.cfg.lookup_max_per_episode + 2))
        clock = self.step_time(pending_step) + timedelta(seconds=(lookup_no + 1) * slot)
        fitted = self.observation(("lookup", pending_step, lookup_no), clock, event)
        return fitted.text, fitted.n_tokens, event


# ---------------------------------------------------------------------------
# Validation (generation-time; the audit re-checks independently from text)
# ---------------------------------------------------------------------------

def validate_episode(ep: Episode, cfg: GeneratorConfig) -> None:
    errs = []
    for s in ep.steps:
        if abs(s.obs_tokens - cfg.v_tokens) > cfg.token_tolerance:
            errs.append(f"step {s.index}: {s.obs_tokens} tokens != v={cfg.v_tokens}")
    d = ep.design
    if ep.variant != "withheld":
        if ep.cell.distance == "far" and not d["far_by_obs_tokens"]:
            errs.append(f"far cell not beyond W by observation tokens: {d}")
        if ep.cell.distance == "far" and d["S_window_obs_only"]:
            errs.append("far cell survives the window")
        if ep.cell.distance == "near" and not d["S_window_assumed_replies"]:
            errs.append("near cell does not survive the window with assumed replies")
    if errs:
        raise GenerationError(f"{ep.episode_id}: " + "; ".join(errs))


# ---------------------------------------------------------------------------
# Convenience API
# ---------------------------------------------------------------------------

def render_template(template: Template, cfg: GeneratorConfig,
                    cells: Iterable[TaskCell] = ALL_CELLS,
                    variants: Iterable[str] = ("base",)) -> list[Episode]:
    r = TemplateRenderer(template, cfg)
    return [r.render(c, v) for v in variants for c in cells]


def generate(split: str, indices: Iterable[int], cfg: GeneratorConfig,
             cells: Iterable[TaskCell] = ALL_CELLS,
             variants: Iterable[str] = ("base",)) -> Iterator[tuple[Template, list[Episode]]]:
    cells, variants = list(cells), list(variants)
    for i in indices:
        t = sample_template(split, i, cfg)
        yield t, render_template(t, cfg, cells, variants)


@lru_cache(maxsize=64)
def _renderer_cached(seed: int, config_json: str) -> TemplateRenderer:
    cfg = GeneratorConfig.from_dict(json.loads(config_json))
    split, index = split_of_seed(seed)
    return TemplateRenderer(sample_template(split, index, cfg), cfg)


def renderer_for(ep: Episode) -> TemplateRenderer:
    """The renderer that produced `ep` (re-sampled deterministically from seed and config)."""
    r = _renderer_cached(ep.template_seed, json.dumps(ep.config, sort_keys=True))
    if r.config_hash != ep.config_hash:
        raise GenerationError("config hash mismatch while rebuilding the renderer")
    return r
