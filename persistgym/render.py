"""Render a template into episodes: 8 task cells x variants {base, restated, withheld}.

All cells of one template share the need step index, the option list, the correct letter,
the routine events, the distractor bindings and the log filler of every step index. They
differ only in where the target components are revealed (near / far), how (observed /
derived) and whether lookup is available (recoverable). Observations of identical
(step, event) pairs are byte-identical across cells.

The withheld variant (PREREG §4.3, D39) shows, at each evidence step, bindings of equal token
length about a stand-in entity instead of the target's bindings (the rule sentence, which
binds no entity, is kept). Every other observation, and the log filler of the evidence steps,
is byte-identical to the base episode of the same cell.

Generator 0.4.0 (PREREG §17.3; gpt-6.1-sol's preset `sol-chain`): in chain form a clue's
binding is its four-sentence chain record (`chain_text`), whose withheld version changes only
the near hop; with `evidence_notice`, each evidence step's event carries the notice
(`notice_text`) after its record, and each helper of a chain record is a lookup key of it.
Neither applies to the default config, whose episodes are those of generator 0.3.0.
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
    LOOKUP_EVENT_MARKER,
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
from persistgym.template import (
    LABELS,
    ChainSpec,
    Template,
    component_schedule,
    rng,
    sample_template,
    split_of_seed,
)

EVENT_PREFIX = "EVENT: "


class GenerationError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Sentence frames (the oracle and the audits parse these; change them together)
# ---------------------------------------------------------------------------

def fact_sentence(kind: str, entity: str, name: str, value: int) -> str:
    return f"For {kind} {entity}, the {name} is {value}."


def relation_sentence(kind: str, entity: str, name: str, delta: int, direction: str,
                      other: str) -> str:
    """Chain form (PREREG §17.3): entity's value = other's value + delta ("more") or
    - delta ("less"). No period follows the number, so `oracle.FACT_RE` never matches it."""
    if direction not in ("more", "less"):
        raise ValueError(f"direction must be 'more' or 'less', got {direction!r}")
    return f"For {kind} {entity}, the {name} is {delta} {direction} than for {kind} {other}."


def chain_sentences(kind: str, name: str, entity: str, near: int,
                    chain: ChainSpec) -> dict[str, str]:
    """The four sentences of a clue's chain record (`template.ChainSpec`) about `entity`
    (the target, or the stand-in with its near delta in the withheld control)."""
    h1, h2, h3 = chain.helpers
    return {
        "near": relation_sentence(kind, entity, name, near, "less", h1),
        "far": relation_sentence(kind, h1, name, chain.far, "more", h2),
        "anchor": fact_sentence(kind, h2, name, chain.anchor),
        "decoy": relation_sentence(kind, h3, name, chain.decoy, "more", h2),
    }


def chain_text(kind: str, name: str, entity: str, near: int, chain: ChainSpec) -> str:
    """A clue's chain record: its four sentences in `chain.order`."""
    s = chain_sentences(kind, name, entity, near, chain)
    return " ".join(s[k] for k in chain.order)


def rule_sentence(kind: str, quantity: str, names: list[str]) -> str:
    return f"Rule: for every {kind}, {quantity} = {' + '.join(names)}."


DERIVED_NOTICE = ("The {quantity} of {kind} {entity} will be requested in a later update. "
                  "Before replying, work out as much of it as the records so far allow and "
                  "keep the result in mind; do not write it in your reply.")
OBSERVED_NOTICE = ("The {quantity} of {kind} {entity} will be requested in a later update. "
                   "Keep it in mind; do not write it in your reply.")


def notice_text(fact: str, kind: str, quantity: str, entity: str) -> str:
    """The evidence notice (PREREG §17.3; `GeneratorConfig.evidence_notice`), shown after
    the record at each evidence step: the derived text at a clue (or rule) step, the
    observed text at an observed fact's reveal. It names the entity, since a chain record
    names four."""
    text = DERIVED_NOTICE if fact == "derived" else OBSERVED_NOTICE
    return text.format(quantity=quantity, kind=kind, entity=entity)


def need_event(kind: str, entity: str, quantity: str, verb: str, options: list[Option]) -> str:
    lines = [f"{kind.capitalize()} {entity} needs its {quantity} now. Options:"]
    lines += [f"{o.label}) {o.value}" for o in options]
    lines.append(f"Reply {verb}(<letter>) with the letter of the correct option.")
    return "\n".join(lines)


def memo_event(record: str, record_id: str, notice: str = "") -> str:
    """A memo step's event: the record, the evidence notice if any, then the ack request.
    Without a notice the text is that of generator 0.3.0."""
    if notice:
        return f"{record} {notice} Reply ack({record_id}) to acknowledge it."
    return f"{record} Reply ack({record_id}) to acknowledge it."


def lookup_key_matches(key: str, entity: str) -> bool:
    """A lookup key matches an entity if it contains the entity name as a whole word,
    ignoring case ("BEECH", "beech", "sample BEECH" all match; "BEECHES" does not). Entity
    names are single distinct words, so this never confuses the target with a distractor,
    and it keeps formatting slips such as lookup(sample BEECH) from costing extra turns that
    are not about memory (PREREG D3)."""
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
    return component_schedule(t.need_index, t.n_clues, cell.fact, cell.distance, cfg)


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
            return [Component("fact", "fact", sk.quantity, t.target_value, sent, "", steps["fact"],
                              ent)]
        comps = []
        names = list(sk.components[: t.n_clues])
        for i in range(t.n_clues):
            if t.chains:  # chain form: the record gives the value through a relay
                ch = t.chains[i]
                sent = chain_text(kind, names[i], ent, ch.near, ch)
            else:
                sent = fact_sentence(kind, ent, names[i], t.clue_values[i])
            comps.append(Component(f"clue{i}", "clue", names[i], t.clue_values[i], sent, "",
                                   steps[f"clue{i}"], ent))
        comps.append(Component("rule", "rule", sk.quantity, None,
                               rule_sentence(kind, sk.quantity, names), "", steps["rule"], ent))
        return comps

    def distractors(self) -> list[Component]:
        """Distractor bindings (PREREG D1): the target's sentence frame about another entity,
        in a memo from the same source as an observed fact. Identical in every cell."""
        sk = self.skin
        out = []
        for k, d in enumerate(self.t.distractors):
            sent = fact_sentence(sk.kind, d.entity, sk.quantity, d.value)
            out.append(Component(f"dist{k}", "distractor", sk.quantity, d.value, sent,
                                 f"{sk.sources[0]} {d.record_id}. {sent}", d.step, d.entity))
        return out

    def _records(self, comps: list[Component]) -> tuple[dict[int, str], dict[int, str]]:
        """Record line and record id per reveal step; fills Component.record in place.
        A stand-in (`sub_<id>`) uses the source and record id of the component it replaces."""
        by_step: dict[int, list[Component]] = {}
        for c in comps:
            if c.step is not None:
                by_step.setdefault(c.step, []).append(c)
        lines, ids = {}, {}
        for st, cs in sorted(by_step.items()):
            first = cs[0].comp_id.removeprefix("sub_")
            src_i = int(first[-1]) if first.startswith("clue") else 0
            rid = self.t.record_ids[first]
            line = f"{self.skin.sources[src_i]} {rid}. " + " ".join(c.sentence for c in cs)
            for c in cs:
                c.record = line
            lines[st], ids[st] = line, rid
        return lines, ids

    def _substitutes(self, comps: list[Component]) -> list[Component]:
        """The withheld control's stand-ins (PREREG §4.3, D39), one per evidence component
        shown at a step: a fact or clue binding becomes the same sentence frame about the
        stand-in entity with the stand-in's value (equal token length, checked in `render`);
        the rule sentence binds no entity and is kept verbatim. A rule in the system prompt
        stays there, as in every variant."""
        s, sk = self.t.substitute, self.skin
        out = []
        for c in comps:
            if c.step is None:
                continue
            if c.role == "rule":
                sent, value = c.sentence, None
            elif c.role == "clue" and self.t.chains:
                # chain form (PREREG §17.3): only the near hop changes, to the stand-in with
                # its own near delta n' (same position in the order); value = its clue c'
                i = int(c.comp_id[-1])
                ch = self.t.chains[i]
                value = s.clue_values[i]
                sent = chain_text(sk.kind, c.name, s.entity, ch.stand_in_near, ch)
            else:
                value = s.value if c.role == "fact" else s.clue_values[int(c.comp_id[-1])]
                sent = fact_sentence(sk.kind, s.entity, c.name, value)
            out.append(Component(f"sub_{c.comp_id}", "substitute", c.name, value, sent, "",
                                 c.step, s.entity))
        return out

    def _check_equal_length(self, comps: list[Component], subs: list[Component],
                            rec_lines: dict[int, str], sub_lines: dict[int, str],
                            events: dict[int, tuple[str, str]]) -> None:
        """D39: every stand-in sentence, record line and evidence event (`events`: step ->
        (base event, withheld event), the notice included) has the token count of the one it
        replaces, so the evidence observations keep their filler and their v tokens."""
        enc = self.cfg.tokenizer
        orig = {c.comp_id: c for c in comps}
        bad = [s.comp_id for s in subs if tokens.count(s.sentence, enc)
               != tokens.count(orig[s.comp_id.removeprefix("sub_")].sentence, enc)]
        bad += [f"step {st}" for st in rec_lines
                if tokens.count(sub_lines[st], enc) != tokens.count(rec_lines[st], enc)]
        bad += [f"event {st}" for st, (a, b) in events.items()
                if tokens.count(a, enc) != tokens.count(b, enc)]
        if bad or set(sub_lines) != set(rec_lines):
            raise GenerationError(f"{self.t.template_id}: withheld stand-ins are not of equal "
                                  f"token length: {bad}")

    def notice(self, cell: TaskCell, entity: str) -> str:
        """The evidence notice about `entity` for this cell's fact kind, or "" when the config
        has none (`GeneratorConfig.evidence_notice`)."""
        if not self.cfg.evidence_notice:
            return ""
        return notice_text(cell.fact, self.skin.kind, self.skin.quantity, entity)

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
        dists = self.distractors()
        dist_at = {d.step: (d, t.distractors[k].record_id) for k, d in enumerate(dists)}
        if set(dist_at) & set(reveal_steps) or len(dist_at) != len(dists):
            raise GenerationError(f"{t.template_id} {cell.id}: distractor step collides")
        rec_lines, rec_ids = self._records(comps)
        base_notice = self.notice(cell, t.entity)
        base_events = {st: memo_event(rec_lines[st], rec_ids[st], base_notice)
                       for st in rec_lines}
        subs: list[Component] = []
        if variant == "withheld":  # PREREG §4.3, D39: equal-length stand-in bindings
            subs = self._substitutes(comps)
            shown_lines, shown_ids = self._records(subs)
            # the notice names the stand-in, which has the target's token length
            notice = self.notice(cell, t.substitute.entity)
            shown_events = {st: memo_event(shown_lines[st], shown_ids[st], notice)
                            for st in shown_lines}
            self._check_equal_length(comps, subs, rec_lines, shown_lines,
                                     {st: (base_events[st], shown_events.get(st, ""))
                                      for st in base_events})
        else:
            shown_lines, shown_ids, shown_events = rec_lines, rec_ids, base_events
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
                event = shown_events[i]
                expected = f"ack({shown_ids[i]})"
            elif i in dist_at:
                d, rid = dist_at[i]
                kind, rtype = "distractor", "memo"
                event, expected = memo_event(d.record, rid), f"ack({rid})"
            else:
                spec = t.routine[i]
                kind, rtype, event, expected = "routine", spec.type, spec.event, spec.expected_action
            fitted = self.observation(("step", i), clock, event)
            if subs and i in shown_lines:
                # D39: the stand-in leaves the head and the log filler of the base observation
                # unchanged, so the observations differ only in the bindings
                base = self.observation(("step", i), clock, base_events[i])
                if fitted.text[: fitted.filler_end] != base.text[: base.filler_end]:
                    raise GenerationError(f"{t.template_id} {cell.id}: withheld step {i} "
                                          "does not keep the base filler")
            reveals = ([c.comp_id for c in comps if c.step == i] if variant != "withheld" else [])
            steps.append(Step(
                index=i, kind=kind, routine_type=rtype, event=event, observation=fitted.text,
                obs_tokens=fitted.n_tokens, event_start=len(fitted.text) - len(event),
                event_end=len(fitted.text), filler_start=fitted.filler_start,
                filler_end=fitted.filler_end, expected_action=expected, reveals=reveals,
                restates=restates if i == n else [], sim_time=clock.isoformat(),
                distractors=[dist_at[i][0].comp_id] if i in dist_at else [],
                substitutes=[s.comp_id for s in subs if s.step == i]))

        carried = comps if variant != "withheld" else []
        # Lookup re-shows records by the entity they are about: the target's records, or in
        # the withheld control the stand-in's (the target then has none: "no such record").
        shown = [c for c in (subs if variant == "withheld" else carried) if c.step is not None]
        lookup_records = {c.comp_id: c.record for c in shown}
        lookup_steps = {c.comp_id: c.step for c in shown}
        record_keys = {c.comp_id: c.entity for c in shown}
        # Chain form (PREREG §2.5 fidelity, §17.3): every helper named in a clue's record is
        # a key of that record too, so lookup(<helper>) re-shows it from its step on.
        for c in shown:
            cid = c.comp_id.removeprefix("sub_")
            if t.chains and cid.startswith("clue"):
                for h in t.chains[int(cid[-1])].helpers:
                    lookup_records[f"{c.comp_id}@{h}"] = c.record
                    lookup_steps[f"{c.comp_id}@{h}"] = c.step
                    record_keys[f"{c.comp_id}@{h}"] = h
        for d in dists:  # lookup serves the distractor keys too (PREREG D3)
            lookup_records[d.comp_id] = d.record
            lookup_steps[d.comp_id] = d.step
            record_keys[d.comp_id] = d.entity
        lookup = LookupSpec(available=cell.recoverable, key=t.entity,
                            syntax=f"lookup(<{sk.kind} name>)",
                            max_per_episode=cfg.lookup_max_per_episode,
                            records=lookup_records, reveal_steps=lookup_steps,
                            record_keys=record_keys)
        graph = build_graph(
            t.n_steps, n,
            [{"comp_id": c.comp_id, "role": c.role, "step": c.step} for c in carried],
            cell.fact, cell.recoverable, rule_in_system_prompt=rule_in_prompt,
            distractors=[{"comp_id": d.comp_id, "step": d.step} for d in dists]
            + [{"comp_id": s.comp_id, "step": s.step, "role": "substitute"} for s in subs])
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
            lookup=lookup, graph=graph, design=design, distractors=dists, substitutes=subs)
        validate_episode(ep, cfg)
        return ep

    # -- lookup -------------------------------------------------------------
    def lookup_observation(self, ep: Episode, pending_step: int, lookup_no: int,
                           key: str) -> tuple[str, int, str]:
        """Observation shown after a served lookup(key) at `pending_step` (env.EpisodeEnv).

        Re-shows, verbatim and in display order, every record shown at or before the pending
        step about an entity whose name the key contains as a whole word: the target's
        records (fact, or clues and rule), a distractor's binding (PREREG D3) or, in the
        withheld control, the stand-in's records (D39). Any other key, or a key whose records
        are not shown yet, gets "no such record"; so does the target in the withheld control,
        where none of its records is ever shown.

        The key is matched as the agent wrote it. `safe_key` (punctuation dropped, at most 40
        characters) is only echoed back: matching it instead would glue words together
        (`key="BEECH"` -> `keyBEECH`, `sample:BEECH` -> `sampleBEECH`, `BEECH's` -> `BEECHs`)
        or cut the name off a long key, and refuse keys that name the entity as a word."""
        sk = self.skin
        key = key or ""
        safe_key = "".join(ch for ch in key if ch.isalnum() or ch in " _-")[:40].strip()
        lines: list[str] = []
        about: list[str] = []
        for rid, st in sorted(ep.lookup.reveal_steps.items(), key=lambda kv: (kv[1], kv[0])):
            ent = ep.lookup.key_of(rid)
            if (st <= pending_step and lookup_key_matches(key, ent)
                    and ep.lookup.records[rid] not in lines):
                lines.append(ep.lookup.records[rid])
                if ent not in about:
                    about.append(ent)
        if lines:
            names = " and ".join(f"{sk.kind} {e}" for e in about)
            body = f"LOOKUP RESULT for {names}:\n" + "\n".join(lines)
        else:
            body = f"LOOKUP RESULT for '{safe_key}': no such record."
        return self._lookup_slot(ep, pending_step, lookup_no, body)

    def lookup_unavailable_observation(self, ep: Episode,
                                       pending_step: int) -> tuple[str, int, str]:
        """Observation shown after a lookup once all `lookup_max_per_episode` lookups are used
        (PREREG D3): "lookup unavailable", then the pending request again. It costs one turn,
        like a lookup, and is not an answer to the pending step."""
        cap = self.cfg.lookup_max_per_episode
        body = (f"LOOKUP RESULT: lookup unavailable. All {cap} lookups allowed per session "
                "have been used.")
        return self._lookup_slot(ep, pending_step, cap, body)

    def _lookup_slot(self, ep: Episode, pending_step: int, slot_no: int,
                     body: str) -> tuple[str, int, str]:
        """Pad a lookup response to v tokens. Slot j of pending step t has its clock at
        T(t) + (j + 1) * slot, before the next step's clock."""
        event = body + "\nPending request (repeated): " + ep.steps[pending_step].event
        slot = max(1, self.cfg.step_seconds // (self.cfg.lookup_max_per_episode + 2))
        clock = self.step_time(pending_step) + timedelta(seconds=(slot_no + 1) * slot)
        fitted = self.observation(("lookup", pending_step, slot_no), clock, event)
        if LOOKUP_EVENT_MARKER not in fitted.text:  # survival_from_payload relies on it
            raise GenerationError(f"{self.t.template_id}: lookup response without its marker")
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
