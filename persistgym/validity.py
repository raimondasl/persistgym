"""$0 validity checks (PLAN §5 validity gate, amendment §16.3, PREREG D1-D3, D39).

1. `shortcut_audit`: re-derives from the rendered text, independently of the generator's own
   bookkeeping, that the target, its clues and the distractor bindings never leak through
   filler, routine text or option ordering, that the cell manipulation is what it claims to
   be, that the fact-withheld control never names the target and replaces its bindings with
   equal-length stand-in bindings (D39), and that templates are balanced within their blocks.
2. `lookup_audit`: lookup re-shows the target's records or a distractor's binding by key,
   answers unknown keys with "no such record" and answers a lookup over the cap with "lookup
   unavailable" without scoring it (D3); in the withheld control it re-shows the stand-in's
   records and answers the target's key with "no such record".
3. `heuristic_baselines`: no-memory heuristics (most-frequent option, last-seen option and
   position/prior guesses) on views without the fact, and the option nearest the withheld
   control's stand-in value (`stand_in_value_baseline`). Each must score <= chance + margin.
4. `partial_memory_diagnostic`: in derived cells, no proper subset of the clues (with the
   rule) rules out any option, and the partial-memory heuristics score <= chance + margin
   (D2; gated). In chain form (PREREG §17.3) also `chain_partial_memory`: no proper subset of
   the chains' atoms rules out an option, and six misreadings of the records score <= chance
   + margin (gated).
5. `oracle_scores`: the programmatic oracles (must be 100%; see oracle.py).

Generator 0.4.0 adds three shortcut-audit checks (chain records well formed and resolving,
worked-out values never shown, the evidence notice only at evidence steps), a chain branch of
the withheld-control check and helper keys in the lookup audit (PREREG §17.3).
"""

from __future__ import annotations

import itertools
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from scipy import stats

from persistgym import tokens
from persistgym.config import GeneratorConfig
from persistgym.env import EpisodeEnv
from persistgym.episode import Component, Episode
from persistgym.oracle import FACT_RE, RELATION_RE, KeyOracle, TextOracle, run_episode
from persistgym.render import notice_text
from persistgym.skins import get_skin
from persistgym.survival import window_keep_start
from persistgym.template import (
    BASE_CLUE_RANGE,
    CHAIN_ANCHOR_RANGE,
    CHAIN_DELTA_RANGE,
    CHAIN_MARGIN,
    CHAIN_MIN_GAP,
    component_schedule,
    entity_token_length,
    names_overlap,
    split_of_seed,
)

OPTION_LINE = re.compile(r"^[A-Z]\) \d+$", re.MULTILINE)
NOTICE_MARK = "will be requested in a later update."
"""The evidence notice's first sentence ends so (`render.notice_text`); no other text of an
episode contains it."""
_NUMBER = re.compile(r"(?<![0-9])[0-9]+(?![0-9])")
_CAPS_WORD = re.compile(r"(?<![A-Za-z])[A-Z][A-Z]+(?![A-Za-z])")


def _num_re(values: Sequence[int]) -> re.Pattern:
    return re.compile(r"(?<![0-9])(?:" + "|".join(str(v) for v in values) + r")(?![0-9])")


def _word_re(words: Sequence[str]) -> re.Pattern:
    ws = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
    return re.compile(rf"(?<![A-Za-z])(?:{ws})(?![A-Za-z])", re.IGNORECASE)


def is_chain(ep: Episode) -> bool:
    """Whether the episode's config gives clues in chain form (PREREG §17.3)."""
    return ep.config.get("clue_form", "direct") == "chain"


def reserved_of(ep: Episode, clue_values: Sequence[int] = (),
                substitutes: Sequence[Component] = (),
                evidence: Sequence[Component] = ()) -> tuple[list[int], list[str]]:
    """Reserved numbers and words, derived from the episode, plus the clue values, the
    withheld control's stand-ins (D39) and the evidence components seen in other episodes of
    its template: every number and every all-caps entity name in an evidence or stand-in
    sentence (in direct form these are the values and names above; in chain form they add
    the chains' atoms and helper names, PREREG §17.3), and in chain form the values an
    agent never sees (`text_hidden_values`)."""
    skin = get_skin(ep.skin)
    subs = [*ep.substitutes, *substitutes]
    evid = [*ep.components, *evidence]
    nums = {o.value for o in ep.options} | {ep.target_value} | set(clue_values)
    nums |= {c.value for c in ep.components if c.value is not None}
    nums |= {d.value for d in ep.distractors}
    nums |= {s.value for s in subs if s.value is not None}
    sents = [c.sentence for c in (*evid, *subs)]
    nums |= {int(x) for s in sents for x in _NUMBER.findall(s)}
    names = {w for s in sents for w in _CAPS_WORD.findall(s)}
    if is_chain(ep):
        nums |= text_hidden_values(ep.target_value, evid, subs, ep.kind)
    words = [ep.entity, ep.quantity, *skin.components, *(d.entity for d in ep.distractors),
             *sorted({s.entity for s in subs}),
             *sorted(names - {ep.entity, *(d.entity for d in ep.distractors)})]
    return sorted(nums), words


# ---------------------------------------------------------------------------
# Chain records (PREREG §17.3), parsed from the text
# ---------------------------------------------------------------------------

_SENTENCE = re.compile(r"For [a-z]+ [A-Z][A-Z]+, the [a-z ]+? is \d+(?: (?:more|less) than "
                       r"for [a-z]+ [A-Z][A-Z]+)?\.")


@dataclass(frozen=True)
class ChainParse:
    """One chain record parsed from its text: subject (the target or the stand-in), clue
    name, helpers (H1, H2, H3), the printed atoms and the sentence kinds in display order."""

    subject: str
    name: str
    helpers: tuple[str, str, str]
    anchor: int
    far: int
    near: int
    decoy: int
    order: tuple[str, ...]

    @property
    def h1_value(self) -> int:
        return self.anchor + self.far

    @property
    def decoy_value(self) -> int:
        return self.anchor + self.decoy

    @property
    def value(self) -> int:
        return self.anchor + self.far - self.near


def parse_chain(text: str, kind: str) -> ChainParse | None:
    """The chain record in `text` (exactly four sentences, `render.chain_text`), or None if
    it is not one: one anchor binding about H2, a "more" relation from H1 to H2, a "less"
    relation from the subject to H1, and a "more" relation from H3 to H2, all about one clue
    name, with H1, H2, H3 and the subject distinct."""
    parts = _SENTENCE.findall(text)
    if len(parts) != 4 or " ".join(parts) != text:
        return None
    facts = [(m.group(2), m.group(3), int(m.group(4)))
             for p in parts for m in [FACT_RE.fullmatch(p)] if m]
    rels = [(m.group(2), m.group(3), int(m.group(4)), m.group(5), m.group(6))
            for p in parts for m in [RELATION_RE.fullmatch(p)] if m]
    kinds_ok = all(p.startswith(f"For {kind} ") for p in parts)
    if len(facts) != 1 or len(rels) != 3 or not kinds_ok:
        return None
    h2, name, anchor = facts[0]
    less = [r for r in rels if r[3] == "less"]
    more = [r for r in rels if r[3] == "more"]
    if len(less) != 1 or len(more) != 2 or {r[1] for r in rels} != {name}:
        return None
    subject, _, near, _, h1 = less[0]
    far_rel = [r for r in more if r[0] == h1 and r[4] == h2]
    decoy_rel = [r for r in more if r[0] != h1 and r[4] == h2]
    if len(far_rel) != 1 or len(decoy_rel) != 1:
        return None
    h3, far, decoy = decoy_rel[0][0], far_rel[0][2], decoy_rel[0][2]
    if len({subject, h1, h2, h3}) != 4:
        return None
    by_subject = {subject: "near", h1: "far", h2: "anchor", h3: "decoy"}
    order = tuple(by_subject[re.match(r"For [a-z]+ ([A-Z]+),", p).group(1)] for p in parts)
    return ChainParse(subject, name, (h1, h2, h3), anchor, far, near, decoy, order)


def _clue_index(c: Component) -> int:
    return int(c.comp_id[-1])


def _chain_clues(comps: Sequence[Component], kind: str) -> dict[int, ChainParse | None]:
    """Clue index -> the parse of its chain record (target clues or stand-in clues)."""
    out: dict[int, ChainParse | None] = {}
    for c in comps:
        if c.comp_id.removeprefix("sub_").startswith("clue"):
            out[_clue_index(c)] = parse_chain(c.sentence, kind)
    return out


def text_hidden_values(target: int, evidence: Sequence[Component],
                       substitutes: Sequence[Component], kind: str,
                       shown: Sequence[int] = ()) -> set[int]:
    """Chain form: what an agent never sees before the need step, re-derived from the chain
    records: the target, each resolved clue and running total, each chain's H1 and H3
    values, and the same for the stand-in, less `shown` (the distractor values, which a
    3-clue running total can equal; `template.hidden_values` from the generator's side)."""
    out = {target}
    for comps in (evidence, substitutes):
        chains = _chain_clues(comps, kind)
        if not chains or None in chains.values():
            continue
        total = 0
        for i in sorted(chains):
            ch = chains[i]
            total += ch.value
            out |= {ch.value, total, ch.h1_value, ch.decoy_value}
    return out - set(shown)


def _check(name: str, ok: bool, detail) -> dict:
    return {"check": name, "pass": bool(ok), "detail": detail}


def _template_index(ep: Episode) -> int:
    return split_of_seed(ep.template_seed)[1]


def shortcut_audit(episodes: Sequence[Episode], v_tokens: int | None = None,
                   tolerance: int | None = None) -> list[dict]:
    """Run every audit check over `episodes` (any mix of templates, cells and variants)."""
    by_template: dict[str, list[Episode]] = defaultdict(list)
    for ep in episodes:
        by_template[ep.template_id].append(ep)
    # Clue values are visible only in derived base episodes and the withheld stand-ins only in
    # withheld episodes; collect both per template.
    clue_vals: dict[str, set[int]] = defaultdict(set)
    subs_of: dict[str, list[Component]] = defaultdict(list)
    evid_of: dict[str, list[Component]] = defaultdict(list)
    base_of: dict[tuple[str, str], Episode] = {}
    for ep in episodes:
        clue_vals[ep.template_id] |= {c.value for c in ep.components if c.role == "clue"}
        subs_of[ep.template_id] += ep.substitutes
        evid_of[ep.template_id] += ep.components
        if ep.variant == "base":
            base_of[(ep.template_id, ep.cell.id)] = ep

    filler_hits, routine_hits, budget_bad, final_form, observed_extra = [], [], [], [], []
    option_bad, clue_in_options, design_bad, too_long, not_cluster = [], [], [], [], []
    distractor_bad, withheld_named, withheld_bad = [], [], []
    chain_bad, hidden_shown, notice_bad = [], [], []
    n_chain_records = 0
    recounted: dict[str, int] = {}  # observation text -> recounted tokens (deduplicated)
    regexes: dict[str, tuple[re.Pattern, re.Pattern]] = {}
    hidden_res: dict[tuple[str, str], re.Pattern | None] = {}
    for ep in episodes:
        cfg = ep.config
        tid = ep.template_id
        if tid not in regexes:
            nums, words = reserved_of(ep, sorted(clue_vals[tid]), subs_of[tid], evid_of[tid])
            regexes[tid] = (_num_re(nums), _word_re(words))
        num_re, word_re = regexes[tid]
        # PREREG §17.3: chain records parse and resolve; no hidden value is ever shown; the
        # evidence notice is exactly where it belongs
        if is_chain(ep) and ep.cell.fact == "derived" and ep.variant != "withheld":
            n_chain_records += sum(c.role == "clue" for c in ep.components)
            chain_bad += _chain_problems(ep, subs_of[tid])
        if is_chain(ep):
            key = (tid, ep.cell.fact)
            if key not in hidden_res:
                hidden = text_hidden_values(ep.target_value, evid_of[tid], subs_of[tid],
                                            ep.kind, [d.value for d in ep.distractors])
                if ep.cell.fact == "observed":  # an observed fact shows these at its reveal
                    hidden -= {ep.target_value, *(s.value for s in subs_of[tid]
                                                  if s.comp_id == "sub_fact")}
                hidden_res[key] = _num_re(sorted(hidden)) if hidden else None
            rx = hidden_res[key]
            texts = [("system prompt", ep.system_prompt)] + [
                (s.index, s.observation) for s in ep.steps[: ep.need_step]]
            hits = [(w, m) for w, text in texts for m in (rx.findall(text) if rx else [])]
            if hits:
                hidden_shown.append((ep.episode_id, hits[:5]))
        notice_bad += _notice_problems(ep)
        v = v_tokens or cfg["v_tokens"]
        tol = cfg["token_tolerance"] if tolerance is None else tolerance
        target_re = _num_re([ep.target_value])
        counts = []
        for s in ep.steps:
            if s.observation not in recounted:  # text-level checks once per distinct text
                recounted[s.observation] = tokens.count(s.observation, cfg["tokenizer"])
                filler = s.observation[s.filler_start: s.filler_end]
                hits = num_re.findall(filler) + word_re.findall(filler)
                if hits:
                    filler_hits.append((ep.episode_id, s.index, hits[:5]))
                if s.kind == "routine":
                    rh = num_re.findall(s.event) + word_re.findall(s.event)
                    if rh:
                        routine_hits.append((ep.episode_id, s.index, rh[:5]))
            n_tok = recounted[s.observation]
            counts.append(n_tok)
            if abs(n_tok - v) > tol or n_tok != s.obs_tokens:
                budget_bad.append((ep.episode_id, s.index, n_tok, s.obs_tokens))
            if s.index < ep.need_step and target_re.search(s.observation):
                shown_ok = (ep.cell.fact == "observed" and ep.variant != "withheld"
                            and "fact" in s.reveals)
                if not shown_ok:
                    (final_form if ep.cell.fact == "derived" or ep.variant == "withheld"
                     else observed_extra).append((ep.episode_id, s.index))
        vals = [o.value for o in ep.options]
        if (len(vals) != cfg["K_options"] or len(set(vals)) != len(vals)
                or any(not (100 <= x <= 999) for x in vals)
                or ep.target_value not in vals
                or ep.correct_option.value != ep.target_value):
            option_bad.append(ep.episode_id)
        gaps = {b - a for a, b in itertools.pairwise(sorted(vals))}
        if gaps != {cfg.get("option_spacing", 1)}:
            not_cluster.append((ep.episode_id, sorted(gaps)))
        if set(vals) & clue_vals[ep.template_id]:
            clue_in_options.append(ep.episode_id)
        distractor_bad += _distractor_problems(ep, clue_vals[ep.template_id])
        if ep.variant == "withheld":
            if named := _names_target_before_need(ep):
                withheld_named.append((ep.episode_id, named[:5]))
            withheld_bad += _withheld_problems(ep, base_of.get((ep.template_id, ep.cell.id)),
                                               clue_vals[ep.template_id])

        # Near/far re-derived from the text: where each component sentence first appears,
        # recounted observation tokens, and the drop-oldest window model.
        n = ep.need_step
        if ep.variant != "withheld" and ep.components:
            first_seen = {}
            for c in ep.components:
                where = [s.index for s in ep.steps[:n] if c.sentence in s.observation]
                first_seen[c.comp_id] = (min(where) if where else
                                         (None if c.sentence in ep.system_prompt else -1))
            if -1 in first_seen.values():
                design_bad.append((ep.episode_id, "component never shown"))
            else:
                shown = [st for st in first_seen.values() if st is not None]
                W, R = cfg["W_tokens"], cfg["assumed_max_reply_tokens"]
                sys_t = (tokens.count(ep.system_prompt, cfg["tokenizer"])
                         if cfg["window_counts_system_prompt"] else 0)
                keep_obs = window_keep_start(counts[: n + 1], [0] * n, W, sys_t)
                keep_r = window_keep_start(counts[: n + 1], [R] * n, W, sys_t)
                if ep.cell.distance == "far":
                    beyond = sum(counts[max(shown): n + 1]) > W + cfg["far_margin_tokens"]
                    if not beyond or max(shown) >= keep_obs:
                        design_bad.append((ep.episode_id, "far not beyond W"))
                elif min(shown) < keep_r:
                    design_bad.append((ep.episode_id, "near evicted with assumed replies"))
        ctx = (tokens.count(ep.system_prompt, cfg["tokenizer"]) + sum(counts[: n + 1])
               + n * cfg["assumed_max_reply_tokens"])
        if ctx > cfg["max_context_tokens"]:
            too_long.append((ep.episode_id, ctx))

    # Cross-cell consistency within a template: need step, options, routine text and the
    # distractor bindings (same steps, same observations) in every cell and variant.
    inconsistent = []
    for tid, eps in by_template.items():
        base_like = [e for e in eps if e.variant in ("base", "withheld")]
        keys = {(e.need_step, e.correct_label, tuple(o.value for o in e.options),
                 e.need.observation) for e in base_like}
        if len(keys) > 1:
            inconsistent.append(tid)
        per_step: dict[int, set[str]] = defaultdict(set)
        for e in eps:
            for s in e.steps:
                if s.kind in ("routine", "distractor"):
                    per_step[s.index].add(f"{s.kind}:{s.observation}")
        if any(len(obs) > 1 for obs in per_step.values()):
            inconsistent.append(tid + ":routine_or_distractor")
        if len({tuple((d.comp_id, d.step, d.sentence) for d in e.distractors) for e in eps}) > 1:
            inconsistent.append(tid + ":distractors")
        # D39: one stand-in entity per template, in every withheld cell
        if len({s.entity for e in eps for s in e.substitutes}) > 1:
            withheld_bad.append((tid, "the withheld cells use different stand-in entities"))

    one = [one_per_template(eps) for eps in by_template.values()]
    return [
        _check("filler_has_no_reserved_strings", not filler_hits, filler_hits[:10]),
        _check("routine_events_have_no_reserved_strings", not routine_hits, routine_hits[:10]),
        _check("observation_tokens_equal_v", not budget_bad, budget_bad[:10]),
        _check("derived_and_withheld_never_show_target_before_need", not final_form,
               final_form[:10]),
        _check("observed_target_only_at_reveal", not observed_extra, observed_extra[:10]),
        _check("options_valid_and_distinct", not option_bad, option_bad[:10]),
        _check("options_form_one_evenly_spaced_cluster", not not_cluster, not_cluster[:10]),
        _check("options_exclude_clue_values", not clue_in_options, clue_in_options[:10]),
        _check("distractor_bindings_valid", not distractor_bad, distractor_bad[:10]),
        _check("withheld_never_names_target_before_need", not withheld_named,
               withheld_named[:10]),
        _check("withheld_stand_ins_equal_length_and_valid", not withheld_bad, withheld_bad[:10]),
        _check("near_far_hold_when_recomputed_from_text", not design_bad, design_bad[:10]),
        _check("full_history_context_within_max", not too_long, too_long[:10]),
        _check("cells_share_need_step_options_routine_and_distractors", not inconsistent,
               inconsistent[:10]),
        *balance_checks(one),
        _check("chain_records_well_formed_and_resolve", not chain_bad,
               {"n_chain_records": n_chain_records, "problems": chain_bad[:10]}),
        _check("chain_hidden_values_never_shown", not hidden_shown, hidden_shown[:10]),
        _check("evidence_notice_only_at_evidence_steps", not notice_bad, notice_bad[:10]),
    ]


BALANCE_CHECKS = ("correct_letter_balanced", "correct_rank_balanced",
                  "letter_rank_and_n_clues_exact_within_complete_blocks")


def one_per_template(eps: Sequence[Episode]) -> Episode:
    """The episode of a template that the balance checks read: a derived one where possible,
    since it knows the clue count."""
    return next((e for e in eps if e.cell.fact == "derived"), eps[0])


def balance_checks(one: Sequence[Episode]) -> list[dict]:
    """Balance of the correct letter, the correct value's rank and the number of clues, one
    episode per template (`one_per_template`): chi-square tests once there are 5 templates
    per category, and the exact per-block check (`block_balance`)."""
    K = one[0].config["K_options"] if one else 10
    letters = Counter(e.correct_label for e in one)
    ranks = Counter(sorted(o.value for o in e.options).index(e.target_value) for e in one)

    def balance(counter: Counter, cats: Sequence) -> dict:
        obs = [counter.get(c, 0) for c in cats]
        n = sum(obs)
        p = float(stats.chisquare(obs).pvalue) if n >= 5 * len(cats) else None
        return {"n_templates": n, "counts": obs, "max_dev_pp":
                (100 * max(abs(o / n - 1 / len(cats)) for o in obs) if n else None),
                "chi2_p": p}

    letter_bal = balance(letters, [chr(65 + i) for i in range(K)])
    rank_bal = balance(ranks, list(range(K)))
    blocks = block_balance(one)
    return [
        _check("correct_letter_balanced", letter_bal["chi2_p"] is None or
               letter_bal["chi2_p"] > 0.01, letter_bal),
        _check("correct_rank_balanced", rank_bal["chi2_p"] is None or rank_bal["chi2_p"] > 0.01,
               rank_bal),
        _check("letter_rank_and_n_clues_exact_within_complete_blocks", blocks["pass"], blocks),
    ]


def _distractor_problems(ep: Episode, clue_values: set[int]) -> list[tuple]:
    """PREREG D1: the configured number of distractor bindings about other entities, with
    values that are neither options nor clue values (nor each other), each shown once, at its
    own step, before the need step, and never at an evidence step."""
    cfg = ep.config
    out: list[tuple] = []
    ds = ep.distractors
    if len(ds) != cfg.get("n_distractors", 0):
        out.append((ep.episode_id, f"{len(ds)} distractors"))
    vals = [d.value for d in ds]
    ents = [d.entity for d in ds]
    lo, hi = cfg["value_range"]
    taken = {o.value for o in ep.options} | clue_values | {ep.target_value}
    if (len(set(vals)) != len(vals) or set(vals) & taken
            or any(not lo <= x <= hi for x in vals)):
        out.append((ep.episode_id, "distractor values collide or leave the value range"))
    if len(set(ents)) != len(ents) or ep.entity in ents:
        out.append((ep.episode_id, "distractor entities repeat or equal the target"))
    evidence = {c.step for c in ep.components if c.step is not None}
    for d in ds:
        where = [s.index for s in ep.steps if d.sentence in s.observation]
        if (where != [d.step] or d.step >= ep.need_step or d.step in evidence
                or ep.steps[d.step].kind != "distractor"):
            out.append((ep.episode_id, d.comp_id, where))
    return out


def _names_target_before_need(ep: Episode) -> list:
    """Steps before need (and the system prompt) whose text names the target entity as a
    word. The fact-withheld control must name it only at the need step (D39)."""
    rx = re.compile(rf"(?<![A-Za-z]){re.escape(ep.entity)}(?![A-Za-z])", re.IGNORECASE)
    hits: list = [s.index for s in ep.steps[: ep.need_step] if rx.search(s.observation)]
    if rx.search(ep.system_prompt):
        hits.append("system_prompt")
    return hits


def _chain_problems(ep: Episode, substitutes: Sequence[Component]) -> list[tuple]:
    """PREREG §17.3, chain form: each clue record of a derived episode parses into exactly
    one near, far, anchor and decoy sentence about the clue's name, with the target as the
    near hop's subject (`parse_chain`); the helpers are distinct, overlap neither each other
    nor the target, a distractor or the stand-in (`names_overlap`); the anchor lies in
    `CHAIN_ANCHOR_RANGE` and the deltas in `CHAIN_DELTA_RANGE`, at least `CHAIN_MARGIN`
    inside; the far delta differs from the near deltas (target and, when the template's
    withheld episode is audited too, stand-in) and the decoy delta by at least
    `CHAIN_MIN_GAP`; the chain's numbers (atoms, H1 and H3) are distinct; anchor + far - near
    equals the clue's value; and the rule over the resolved clues gives the target."""
    out: list[tuple] = []
    eid = ep.episode_id
    stand_ins = _chain_clues(substitutes, ep.kind)
    others = {ep.entity, *(d.entity for d in ep.distractors), *(s.entity for s in substitutes)}
    a_lo, a_hi = CHAIN_ANCHOR_RANGE[0] + CHAIN_MARGIN, CHAIN_ANCHOR_RANGE[1] - CHAIN_MARGIN
    d_lo, d_hi = CHAIN_DELTA_RANGE[0] + CHAIN_MARGIN, CHAIN_DELTA_RANGE[1] - CHAIN_MARGIN
    helpers: list[str] = []
    resolved: list[int] = []
    clues = [c for c in ep.components if c.role == "clue"]
    for c in clues:
        p = parse_chain(c.sentence, ep.kind)
        if p is None or p.subject != ep.entity or p.name != c.name:
            out.append((eid, c.comp_id, "not a chain record about the target and its clue"))
            continue
        helpers += p.helpers
        if any(names_overlap(h, o) for h in p.helpers for o in others):
            out.append((eid, c.comp_id, ("a helper is or overlaps the target, a distractor "
                                         "or the stand-in"), p.helpers))
        sp = stand_ins.get(_clue_index(c))
        nums = [p.anchor, p.far, p.decoy, p.near, p.h1_value, p.decoy_value]
        nums += [sp.near] if sp is not None else []
        if not (a_lo <= p.anchor <= a_hi and all(d_lo <= x <= d_hi
                                                  for x in (p.far, p.near, p.decoy))):
            out.append((eid, c.comp_id, "an atom is outside its range and margin"))
        if (abs(p.far - p.near) < CHAIN_MIN_GAP or abs(p.decoy - p.far) < CHAIN_MIN_GAP
                or (sp is not None and abs(p.far - sp.near) < CHAIN_MIN_GAP)):
            out.append((eid, c.comp_id, "the far delta is within the gap of another delta"))
        if len(set(nums)) != len(nums):
            out.append((eid, c.comp_id, "the chain's numbers repeat", nums))
        if p.value != c.value:
            out.append((eid, c.comp_id, "anchor + far - near is not the clue's value",
                        p.value, c.value))
        resolved.append(p.value)
    if len(set(helpers)) != len(helpers) or any(
            names_overlap(a, b) for a, b in itertools.combinations(helpers, 2)):
        out.append((eid, "the helpers repeat or overlap", helpers))
    if len(resolved) == len(clues) and clues and sum(resolved) != ep.target_value:
        out.append((eid, "the rule over the resolved clues is not the target"))
    return out


def _notice_problems(ep: Episode) -> list[tuple]:
    """PREREG §17.3: with `evidence_notice`, the exact notice (`render.notice_text`, about
    the target, or the stand-in in the withheld control) occurs once in the event of each
    of the cell's evidence steps (re-derived from the config) and nowhere else: not in the
    system prompt or at a routine, distractor or need step (so not in the restated block).
    Without it, no text of the episode holds the notice."""
    on = ep.config.get("evidence_notice", False)
    sched = component_schedule(ep.need_step, ep.n_clues, ep.cell.fact, ep.cell.distance,
                               GeneratorConfig.from_dict(ep.config))
    evidence = {st for st in sched.values() if st is not None} if on else set()
    entity = (ep.substitutes[0].entity if ep.variant == "withheld" and ep.substitutes
              else ep.entity)
    want = notice_text(ep.cell.fact, ep.kind, ep.quantity, entity)
    out: list[tuple] = []
    if NOTICE_MARK in ep.system_prompt:
        out.append((ep.episode_id, "system prompt"))
    for s in ep.steps:
        n_mark = s.observation.count(NOTICE_MARK)
        if s.index in evidence:
            if not (n_mark == 1 and s.event.count(want) == 1):
                out.append((ep.episode_id, s.index, "evidence step without its notice"))
        elif n_mark:
            out.append((ep.episode_id, s.index, f"notice at a {s.kind} step"))
    return out


def _withheld_problems(ep: Episode, base: Episode | None, clue_values: set[int]) -> list[tuple]:
    """PREREG §4.3, D39: at each step that shows evidence in the base episode of its cell,
    the withheld episode shows instead a binding in the same frame about one stand-in entity
    (another entity of the skin, not a distractor, with the target's token length, whose name
    neither contains nor is contained in the target's) whose value has the replaced value's
    format and is no option, clue value or distractor value; the rule sentence, which binds
    no entity, is kept. The stand-in's own value (observed) or the sum its clues give under
    the rule (derived) is never an option. Each stand-in is shown once, at its step. When the
    base episode of the cell is among the audited episodes, the two must be identical except
    for these bindings, which keep the token count of the sentences they replace: swapping
    them back gives the base observation, and the evidence steps keep the base log filler,
    token count and expected action."""
    out: list[tuple] = []
    eid, subs, n = ep.episode_id, ep.substitutes, ep.need_step
    enc = ep.config["tokenizer"]
    skin = get_skin(ep.skin)
    sched = component_schedule(n, ep.n_clues, ep.cell.fact, ep.cell.distance,
                               GeneratorConfig.from_dict(ep.config))
    want = {cid: st for cid, st in sched.items() if st is not None}
    got = {s.comp_id.removeprefix("sub_"): s.step for s in subs}
    if got != want or len(subs) != len(want) or ep.components:
        out.append((eid, "stand-ins are not exactly at the evidence steps", got, want))
    ents = {s.entity for s in subs}
    if len(ents) != 1:
        out.append((eid, "not exactly one stand-in entity", sorted(ents)))
    else:
        e = next(iter(ents))
        if e in {ep.entity, *(d.entity for d in ep.distractors)} or (
                e not in skin.entities
                or entity_token_length(e, enc) != entity_token_length(ep.entity, enc)):
            out.append((eid, "stand-in entity", e))
        if names_overlap(e, ep.entity):  # e.g. stand-in BITTERN for target TERN spells it
            out.append((eid, "stand-in name overlaps the target name", e, ep.entity))
    options = {o.value for o in ep.options}
    taken = options | clue_values | {ep.target_value} | {d.value for d in ep.distractors}
    names = {"sub_fact": ep.quantity, **{f"sub_clue{i}": nm
                                         for i, nm in enumerate(skin.components)}}
    rule = (f"Rule: for every {ep.kind}, {ep.quantity} = "
            f"{' + '.join(skin.components[: ep.n_clues])}.")
    bound = [s for s in subs if s.comp_id != "sub_rule"]
    chain = is_chain(ep) and ep.cell.fact == "derived"
    orig = {c.comp_id: c.sentence for c in base.components} if base is not None else {}
    for s in subs:
        digits = 2 if s.comp_id in ("sub_clue1", "sub_clue2") else 3
        if s.comp_id == "sub_rule":
            ok = s.sentence == rule and s.value is None
        elif chain:
            # PREREG §17.3: the base clue's chain record with only the near hop swapped, to
            # the stand-in with its own 3-digit near delta n'; H1 - n' is the stand-in's clue
            p = parse_chain(s.sentence, ep.kind)
            ok = (p is not None and s.value is not None and p.subject == s.entity
                  and p.name == names.get(s.comp_id) and 100 <= p.near <= 999
                  and p.near not in taken and p.value == s.value
                  and s.value not in taken and len(str(s.value)) == digits)
            o = orig.get(s.comp_id.removeprefix("sub_"))
            q = parse_chain(o, ep.kind) if o else None
            if ok and q is not None:
                near_base = (f"For {ep.kind} {q.subject}, the {q.name} is {q.near} less than "
                             f"for {ep.kind} {q.helpers[0]}.")
                near_sub = (f"For {ep.kind} {s.entity}, the {q.name} is {p.near} less than "
                            f"for {ep.kind} {q.helpers[0]}.")
                ok = (o.count(near_base) == 1 and s.sentence == o.replace(near_base, near_sub)
                      and abs(q.far - p.near) >= CHAIN_MIN_GAP
                      and p.near not in (q.anchor, q.far, q.decoy, q.near, q.h1_value,
                                         q.decoy_value))
        else:
            ok = (s.value is not None and s.value not in taken and len(str(s.value)) == digits
                  and s.sentence == f"For {ep.kind} {s.entity}, the {names.get(s.comp_id)} "
                                    f"is {s.value}.")
        where = [st.index for st in ep.steps if s.sentence in st.observation]
        if not ok or where != [s.step] or ep.steps[s.step].kind != "reveal":
            out.append((eid, s.comp_id, s.value, where))
    if bound and all(s.value is not None for s in bound):
        stand_in = sum(s.value for s in bound) if ep.cell.fact == "derived" else bound[0].value
        if stand_in in options or stand_in == ep.target_value:
            out.append((eid, "the stand-in's value is an option", stand_in))
    if base is None:
        return out
    swap = {s.sentence: orig.get(s.comp_id.removeprefix("sub_"), "") for s in subs}
    if ep.config.get("evidence_notice", False) and subs:  # the notice names the stand-in
        swap[notice_text(ep.cell.fact, ep.kind, ep.quantity, subs[0].entity)] = notice_text(
            ep.cell.fact, ep.kind, ep.quantity, ep.entity)
    if any(tokens.count(a, enc) != tokens.count(b, enc) for a, b in swap.items()):
        out.append((eid, "a stand-in sentence does not keep the token count it replaces"))
    if ([s.kind for s in ep.steps] != [s.kind for s in base.steps]
            or ep.system_prompt != base.system_prompt):
        return [*out, (eid, "steps or system prompt differ from the base episode")]
    evidence = {s.step for s in subs}
    for a, b in zip(ep.steps, base.steps, strict=True):
        if a.index not in evidence:
            if a.observation != b.observation:
                out.append((eid, a.index, "differs from the base episode"))
            continue
        restored, restored_obs = a.event, a.observation
        for x, y in swap.items():
            restored, restored_obs = restored.replace(x, y), restored_obs.replace(x, y)
        if (a.observation[: a.filler_end] != b.observation[: b.filler_end]
                or restored != b.event or restored_obs != b.observation
                or tokens.count(a.event, enc) != tokens.count(b.event, enc)
                or a.obs_tokens != b.obs_tokens or a.expected_action != b.expected_action):
            out.append((eid, a.index, "evidence step differs beyond equal-length bindings"))
    return out


def block_balance(templates: Sequence[Episode]) -> dict:
    """Within each complete block of K templates (index // K), every letter and every rank
    is correct exactly once and the numbers of clues are split as evenly as possible
    (PREREG D2, D7). `templates`: one episode per template. Incomplete blocks are listed and
    not judged; template counts in whole blocks avoid them (D7)."""
    if not templates:
        return {"pass": True, "complete_blocks": 0, "incomplete_blocks": [], "bad_blocks": []}
    cfg = templates[0].config
    K = cfg["K_options"]
    choices = list(cfg["n_clues_choices"])
    blocks: dict[tuple[str, int], list[Episode]] = defaultdict(list)
    for e in templates:
        blocks[(e.split, _template_index(e) // K)].append(e)
    bad, incomplete, n_split = [], [], []
    for key, eps in sorted(blocks.items()):
        if len(eps) != K:
            incomplete.append(list(key))
            continue
        letters = {e.correct_label for e in eps}
        ranks = {sorted(o.value for o in e.options).index(e.target_value) for e in eps}
        m = Counter(e.n_clues if e.cell.fact == "derived" else _n_clues_of(e) for e in eps)
        want = Counter(choices[i % len(choices)] for i in range(K))
        if len(letters) != K or len(ranks) != K or m != want:
            bad.append({"block": list(key), "n_clues": dict(m)})
        n_split.append(dict(sorted(m.items())))
    return {"pass": not bad, "complete_blocks": len(blocks) - len(incomplete),
            "incomplete_blocks": incomplete, "bad_blocks": bad[:10],
            "n_clues_per_block": n_split[:3]}


def _n_clues_of(ep: Episode) -> int:
    """Number of clues of the template of an observed episode (which carries n_clues = 0),
    by re-sampling the template."""
    from persistgym.config import GeneratorConfig
    from persistgym.template import sample_template

    split, index = split_of_seed(ep.template_seed)
    return sample_template(split, index, GeneratorConfig.from_dict(ep.config)).n_clues


# ---------------------------------------------------------------------------
# Lookup semantics (PREREG D3)
# ---------------------------------------------------------------------------

def _play_episode(ep: Episode, at_need: list[str]) -> tuple[EpisodeEnv, list[str]]:
    """Answer every step correctly, but send `at_need` (in order) at the need step first.
    Returns the env and the observations shown at the need step after each of them."""
    env = EpisodeEnv(ep)
    queue = list(at_need)
    seen: list[str] = []
    done = False
    while not done:
        if env.pending == ep.need_step and queue:
            reply = queue.pop(0)
        else:
            reply = f"ACTION: {ep.steps[env.pending].expected_action}"
        was_need = env.pending == ep.need_step
        obs, done = env.step(reply)
        if was_need and obs is not None and env.pending == ep.need_step:
            seen.append(obs)
    return env, seen


def _helper_lookup_problems(ep: Episode, comps: Sequence[Component], answer: str,
                            play) -> list[tuple]:
    """Chain form (PREREG §2.5, §17.3): lookup(H1 of clue 0) at the need step re-shows clue
    0's record and no other clue's, and the episode is then answered as usual."""
    if not is_chain(ep) or ep.cell.fact != "derived":
        return []
    clues = {_clue_index(c): c for c in comps if c.comp_id.removeprefix("sub_").startswith("clue")}
    p = parse_chain(clues[0].sentence, ep.kind) if 0 in clues else None
    if p is None:
        return [(ep.episode_id, "no chain record of clue 0 to look up by its helper")]
    env, seen = play(ep, [f"ACTION: lookup({p.helpers[0]})", answer])
    ok = (clues[0].sentence in seen[0]
          and not any(c.sentence in seen[0] for i, c in clues.items() if i != 0)
          and env.result().need_correct)
    return [] if ok else [(ep.episode_id, "lookup by a helper key")]


def lookup_audit(episodes: Sequence[Episode]) -> list[dict]:
    """Play recoverable base episodes with lookups at the need step and check D3:
    * lookup(target) re-shows every target record, and no distractor binding (the key is
      written `key="<name in lower case>"`, so the whole-word match on the key as written is
      exercised too);
    * lookup(distractor) re-shows that distractor's binding, and no target record;
    * lookup(unknown key) answers "no such record";
    * after the cap, a lookup answers "lookup unavailable", costs one turn, is not scored,
      and the next answer is scored as usual; a second over-cap lookup at the same step is
      an invalid action.
    In recoverable withheld episodes (D39), lookup(target) answers "no such record" (the
    target has no record) and lookup(stand-in) re-shows every stand-in record and no
    distractor.
    In chain form (PREREG §17.3), lookup(H1 of clue 0) re-shows clue 0's record (the
    stand-in's in the withheld control) and no other clue's. No lookup response holds the
    evidence notice.
    """
    bad: list[tuple] = []
    n = n_withheld = 0
    responses: list[tuple[str, str]] = []  # (episode id, lookup response) for the notice check

    def _play(ep: Episode, at_need: list[str]) -> tuple[EpisodeEnv, list[str]]:
        env, seen = _play_episode(ep, at_need)
        responses.extend((ep.episode_id, x) for x in seen)
        return env, seen

    for ep in episodes:
        if not ep.cell.recoverable or ep.variant not in ("base", "withheld"):
            continue
        cap = ep.lookup.max_per_episode
        answer = f"ACTION: {ep.need.expected_action}"
        if ep.variant == "withheld":
            n_withheld += 1
            subs = ep.substitutes
            if cap < 2 or not subs:
                bad.append((ep.episode_id, "withheld lookup not testable"))
                continue
            env, seen = _play(ep, [f"ACTION: lookup({ep.entity})",
                                   f"ACTION: lookup({ep.kind} {subs[0].entity})", answer])
            if not ("no such record" in seen[0]
                    and not any(s.sentence in seen[0] for s in subs)
                    and all(s.sentence in seen[1] for s in subs)
                    and not any(d.sentence in seen[1] for d in ep.distractors)
                    and env.result().need_correct):
                bad.append((ep.episode_id, "withheld lookup by key"))
            bad += _helper_lookup_problems(ep, subs, answer, _play)
            continue
        n += 1
        keys = [f'key="{ep.entity.lower()}"', *(f"{ep.kind} {d.entity}" for d in ep.distractors)]
        env, seen = _play(ep, [f"ACTION: lookup({k})" for k in keys[:cap]] + [answer])
        target_ok = (all(c.sentence in seen[0] for c in ep.components)
                     and not any(d.sentence in seen[0] for d in ep.distractors))
        dist_ok = all(d.sentence in seen[i + 1]
                      and not any(c.sentence in seen[i + 1] for c in ep.components)
                      for i, d in enumerate(ep.distractors[: cap - 1]))
        if not (target_ok and dist_ok and env.result().need_correct):
            bad.append((ep.episode_id, "lookup by key"))
        env, seen = _play(ep, ["ACTION: lookup(NOSUCHKEY)", answer])
        if "no such record" not in seen[0] or not env.result().need_correct:
            bad.append((ep.episode_id, "unknown key"))
        over = [f"ACTION: lookup({ep.entity})"] * (cap + 1)
        env, seen = _play(ep, [*over, answer])
        r = env.result()
        if not ("lookup unavailable" in seen[cap] and r.need_correct and r.n_lookups == cap
                and r.n_lookups_unavailable == 1 and r.n_turns == ep.n_steps + cap + 1):
            bad.append((ep.episode_id, "over-cap lookup"))
        env, _ = _play(ep, [*over, f"ACTION: lookup({ep.entity})", answer])
        if env.result().step_outcomes[ep.need_step] != "invalid_lookup":
            bad.append((ep.episode_id, "second over-cap lookup"))
        bad += _helper_lookup_problems(ep, ep.components, answer, _play)
    bad += [(eid, "a lookup response holds the evidence notice") for eid, x in responses
            if NOTICE_MARK in x]
    return [_check("lookup_serves_keys_and_refuses_after_cap", not bad,
                   {"n_episodes": n, "n_withheld_episodes": n_withheld, "problems": bad[:10]})]


# ---------------------------------------------------------------------------
# No-memory heuristic baselines
# ---------------------------------------------------------------------------

def option_hits(text: str, ep: Episode) -> dict[str, tuple[int, int]]:
    """Occurrences of each option value in `text` outside the option list:
    label -> (count, position of the last occurrence)."""
    body = OPTION_LINE.sub("", text)
    to_label = {str(o.value): o.label for o in ep.options}
    rx = re.compile(r"(?<![0-9])(" + "|".join(to_label) + r")(?![0-9])")
    hits: dict[str, tuple[int, int]] = {}
    for m in rx.finditer(body):
        lab = to_label[m.group(1)]
        hits[lab] = (hits.get(lab, (0, -1))[0] + 1, m.start())
    return hits


def most_frequent_option(hits: dict, ep: Episode) -> str:
    """Option whose value occurs most often in the view (outside the option list); ties go to
    the earliest-listed option."""
    return max((hits.get(o.label, (0, -1))[0], -i, o.label) for i, o in enumerate(ep.options))[2]


def last_seen_option(hits: dict, ep: Episode) -> str:
    """Option whose value occurs last in the view (outside the option list); if none occurs,
    the last-listed option."""
    if not hits:
        return ep.options[-1].label
    return max(hits.items(), key=lambda kv: kv[1][1])[0]


def first_option(hits: dict, ep: Episode) -> str:
    return ep.options[0].label


def median_value_option(hits: dict, ep: Episode) -> str:
    vals = sorted(ep.options, key=lambda o: o.value)
    return vals[(len(vals) - 1) // 2].label


BASELINES = {
    "most_frequent_option": most_frequent_option,
    "last_seen_option": last_seen_option,
    "first_option": first_option,
    "median_value_option": median_value_option,
}


def views(episodes: Sequence[Episode]) -> dict[str, list[tuple[Episode, str]]]:
    """Views an agent without the fact could have:
    need_only: the need observation alone (base episodes);
    withheld_transcript: every observation up to need in the fact-withheld control;
    derived_transcript: every observation up to need in derived base episodes (the target
    is never shown in final form there)."""
    out: dict[str, list[tuple[Episode, str]]] = {
        "need_only": [], "withheld_transcript": [], "derived_transcript": []}
    for ep in episodes:
        upto = "\n".join(s.observation for s in ep.steps[: ep.need_step + 1])
        if ep.variant == "base":
            out["need_only"].append((ep, ep.need.observation))
            if ep.cell.fact == "derived":
                out["derived_transcript"].append((ep, upto))
        elif ep.variant == "withheld":
            out["withheld_transcript"].append((ep, upto))
    return out


def prior_label_baseline(calibration_labels: Sequence[str], episodes: Sequence[Episode]) -> dict:
    """Most frequent correct letter in a calibration set (e.g. the other split's templates),
    applied to `episodes`."""
    cal = Counter(calibration_labels)
    if not cal:
        return {"accuracy": None, "n": 0}
    guess = min(cal.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    per_t = {e.template_id: e for e in episodes}
    n = len(per_t)
    acc = sum(e.correct_label == guess for e in per_t.values()) / n if n else None
    return {"guess": guess, "accuracy": acc, "n": n, "n_calibration": sum(cal.values())}


def heuristic_baselines(episodes: Sequence[Episode], margin_pp: float | None = None,
                        calibration_labels: Sequence[str] = ()) -> dict:
    """Accuracy of every baseline on every view. One score per template and view (cells of
    a template share the need step), so n = templates."""
    if not episodes:
        return {}
    K = episodes[0].config["K_options"]
    margin = episodes[0].config["validity_margin_pp"] if margin_pp is None else margin_pp
    threshold = 1 / K + margin / 100
    results: dict = {"chance": 1 / K, "threshold": threshold, "views": {}}
    ok = True
    for view, items in views(episodes).items():
        res = {}
        hits = [(ep, option_hits(text, ep)) for ep, text in items]
        for name, fn in BASELINES.items():
            per_template: dict[str, list[bool]] = defaultdict(list)
            for ep, h in hits:
                per_template[ep.template_id].append(fn(h, ep) == ep.correct_label)
            if not per_template:
                continue
            acc = sum(sum(v) / len(v) for v in per_template.values()) / len(per_template)
            res[name] = {"accuracy": acc, "n_templates": len(per_template),
                         "pass": acc <= threshold}
            ok &= acc <= threshold
        results["views"][view] = res
    if calibration_labels:
        pl = prior_label_baseline(calibration_labels, episodes)
        pl["pass"] = pl["accuracy"] is None or pl["accuracy"] <= threshold
        ok &= pl["pass"]
        results["prior_label"] = pl
    stand_in = stand_in_value_baseline(episodes, threshold)
    if stand_in["by_cell"]:
        ok &= stand_in["pass"]
        results["nearest_to_stand_in_value"] = stand_in
    results["pass"] = ok
    return results


def stand_in_value_baseline(episodes: Sequence[Episode], threshold: float) -> dict:
    """`nearest_to_stand_in_value` (PREREG §17.3; gated in every config and task cell): on
    the withheld view, the option nearest the stand-in's value as the text oracle derives it
    from the observations before the need step (its observed value, or the rule over its
    clues, direct or in chain form). The stand-in's value is never an option and is drawn
    whatever the rank, so this picks the lowest or the highest option and is correct about
    once per block of 10. One score per template and task cell."""
    by_cell: dict[str, dict[str, bool]] = defaultdict(dict)
    unresolved = []
    for ep in episodes:
        if ep.variant != "withheld" or not ep.substitutes:
            continue
        oracle = TextOracle()
        oracle.reset(ep.system_prompt)
        for s in ep.steps[: ep.need_step]:
            oracle.act(s.observation, {})
        value = oracle.value_of(ep.substitutes[0].entity, ep.quantity)
        if value is None:
            unresolved.append(ep.episode_id)
            continue
        nearest = min(ep.options, key=lambda o, v=value: (abs(o.value - v), o.value))
        by_cell[ep.cell.id][ep.template_id] = nearest.label == ep.correct_label
    cells = {cid: {"accuracy": sum(v.values()) / len(v), "n_templates": len(v),
                   "pass": sum(v.values()) / len(v) <= threshold}
             for cid, v in sorted(by_cell.items())}
    return {"by_cell": cells, "unresolved": unresolved[:10],
            "pass": not unresolved and all(c["pass"] for c in cells.values())}


# ---------------------------------------------------------------------------
# Partial memory in derived cells (PREREG D2; gated)
# ---------------------------------------------------------------------------

def clue_subsets(n_clues: int) -> list[tuple[int, ...]]:
    """Every proper subset of the clue indices (0 = base), the empty one included. The rule
    is kept in every subset."""
    return [c for r in range(n_clues) for c in itertools.combinations(range(n_clues), r)]


def subset_label(subset: tuple[int, ...]) -> str:
    return "+".join(f"clue{i}" for i in subset) or "rule_only"


def consistent_options(known: dict[int, int], n_clues: int, options: Sequence[int],
                       minor_range: Sequence[int]) -> list[int]:
    """Options that some completion of the missing clues reaches under the rule (a sum),
    with the base clue in BASE_CLUE_RANGE and each addend in `minor_range`."""
    lo = hi = sum(known.values())
    for i in range(n_clues):
        if i not in known:
            r = BASE_CLUE_RANGE if i == 0 else minor_range
            lo += r[0]
            hi += r[1]
    return [o for o in options if lo <= o <= hi]


def _count_sum(total: int, k: int, lo: int, hi: int) -> int:
    """Number of k-tuples of integers in [lo, hi] that sum to `total` (k <= 2)."""
    if k == 0:
        return int(total == 0)
    if k == 1:
        return int(lo <= total <= hi)
    if k == 2:
        return max(0, min(hi, total - lo) - max(lo, total - hi) + 1)
    raise ValueError("at most 2 missing addends")


def generator_aware_weights(known: dict[int, int], n_clues: int, options: Sequence[int],
                            spacing: int, core_range: Sequence[int]) -> list[int]:
    """Likelihood (up to one common factor) of each rank j of the target, for an agent that
    knows the generator exactly (`template._clustered_options` and `template._clues`) and
    kept the clues in `known` (index -> value; 0 = base) plus the rule.

    Under rank j the target is L + j*s (L = lowest option, uniform whatever j) and each
    addend is core + j*s with the core uniform in `core_range`. A known addend needs its
    core in range; a known base fixes the sum of the missing cores."""
    L = min(options)
    clo, chi = core_range
    m = n_clues
    weights = []
    for j in range(len(options)):
        w = 1
        known_cores = 0
        for i, a in known.items():
            if i == 0:
                continue
            c = a - j * spacing
            if not clo <= c <= chi:
                w = 0
            known_cores += c
        if w and 0 in known:
            missing = (m - 1) - sum(1 for i in known if i != 0)
            rest = L - known[0] - (m - 2) * j * spacing - known_cores
            w = _count_sum(rest, missing, clo, chi)
        weights.append(w)
    return weights


def partial_memory_diagnostic(items: Sequence[tuple[int, Sequence[int], Sequence[int], int]],
                              cfg: dict) -> dict:
    """What an agent that kept only part of a derived fact can do (PREREG D2).

    `items`: one (n_clues, clue values [base, addends...], option values, target) per
    template. `cfg`: the generator config dict. Gated (each must hold):
    * `narrowing_templates` = 0: no proper subset of the clues (with the rule) leaves fewer
      than K options consistent (`consistent_options`), enumerated over every subset;
    * `base_and_rule_uniform_accuracy` <= chance + margin: the agent kept the base clue and
      the rule, knows the addend range, and picks uniformly among the consistent options;
    * `smallest_above_base_accuracy` <= chance + margin: the agent kept the base clue and
      picks the smallest option above it.
    Reported, not gated:
    * `nearest_to_midrange_accuracy`: base + the addends' mid-range value, nearest option;
    * `generator_aware_bayes`: per subset, the accuracy of the Bayes-optimal guess of an
      agent that knows the generator's sampling exactly (`generator_aware_weights`). This is
      an upper bound for partial memory that no agent is told how to reach.
    """
    K = cfg["K_options"]
    margin = cfg["validity_margin_pp"]
    threshold = 1 / K + margin / 100
    minor = tuple(cfg["minor_component_range"])
    spacing = cfg.get("option_spacing", 1)
    core = (minor[0], minor[1] - (K - 1) * spacing)
    mid = (minor[0] + minor[1]) / 2
    rows: dict[int, list[dict]] = defaultdict(list)
    for n_clues, clues, values, target in items:
        base = clues[0]
        narrowing = [subset_label(sub) for sub in clue_subsets(n_clues)
                     if len(consistent_options({i: clues[i] for i in sub}, n_clues, values,
                                               minor)) < len(values)]
        cands = consistent_options({0: base}, n_clues, values, minor)
        above = sorted(v for v in values if v > base)
        guess = base + (n_clues - 1) * mid
        nearest = min(values, key=lambda v: (abs(v - guess), v))
        j_true = sorted(values).index(target)
        bayes = {}
        for sub in clue_subsets(n_clues):
            w = generator_aware_weights({i: clues[i] for i in sub}, n_clues, values, spacing,
                                        core)
            best = [j for j, x in enumerate(w) if x == max(w)]
            bayes[subset_label(sub)] = 1 / len(best) if j_true in best else 0.0
        rows[n_clues].append({
            "narrowing": narrowing, "n_cands": len(cands),
            "uniform": (1 / len(cands)) if target in cands else 0.0,
            "smallest_above": bool(above) and above[0] == target,
            "nearest": nearest == target, "bayes": bayes})

    def agg(rs: list[dict]) -> dict:
        n = len(rs)
        labels = sorted({k for r in rs for k in r["bayes"]})
        bayes = {k: sum(r["bayes"][k] for r in rs if k in r["bayes"])
                 / sum(1 for r in rs if k in r["bayes"]) for k in labels}
        return {
            "n_templates": n,
            "narrowing_templates": sum(bool(r["narrowing"]) for r in rs),
            "narrowing_examples": sorted({x for r in rs for x in r["narrowing"]})[:5],
            "base_and_rule_options_left_mean": sum(r["n_cands"] for r in rs) / n,
            "base_and_rule_uniform_accuracy": sum(r["uniform"] for r in rs) / n,
            "smallest_above_base_accuracy": sum(r["smallest_above"] for r in rs) / n,
            "nearest_to_midrange_accuracy": sum(r["nearest"] for r in rs) / n,
            "generator_aware_bayes": bayes,
            "generator_aware_bayes_max": max(bayes.values()) if bayes else None,
        }

    out: dict = {"chance": 1 / K, "threshold": threshold,
                 "by_n_clues": {str(k): agg(v) for k, v in sorted(rows.items())}}
    every = [r for v in rows.values() for r in v]
    out["all"] = agg(every) if every else None
    a = out["all"]
    out["pass"] = a is None or (a["narrowing_templates"] == 0
                                and a["base_and_rule_uniform_accuracy"] <= threshold
                                and a["smallest_above_base_accuracy"] <= threshold)
    return out


def _derived_items(eps: Sequence[Episode]) -> list[tuple]:
    out = []
    for e in eps:
        clues = [c.value for c in sorted((c for c in e.components if c.role == "clue"),
                                         key=lambda c: c.comp_id)]
        out.append((e.n_clues, clues, [o.value for o in e.options], e.target_value))
    return out


def partial_memory_from_episodes(episodes: Sequence[Episode]) -> dict | None:
    """`partial_memory_diagnostic` per derived task cell (base episodes, one per template).
    The gate holds only if it holds in every derived cell (PREREG D2)."""
    by_cell: dict[str, dict[str, Episode]] = defaultdict(dict)
    for ep in episodes:
        if ep.variant == "base" and ep.cell.fact == "derived":
            by_cell[ep.cell.id].setdefault(ep.template_id, ep)
    if not by_cell:
        return None
    cfg = next(iter(next(iter(by_cell.values())).values())).config
    cells = {cid: partial_memory_diagnostic(_derived_items(list(eps.values())), cfg)
             for cid, eps in sorted(by_cell.items())}
    if cfg.get("clue_form", "direct") == "chain":  # PREREG §17.3: atoms parsed from the text
        for cid, eps in by_cell.items():
            pm = cells[cid]
            pm["chain"] = chain_partial_memory(_chain_items(list(eps.values())), cfg)
            pm["pass"] = pm["pass"] and pm["chain"]["pass"]
    return {"cells": cells, "pass": all(c["pass"] for c in cells.values())}


# ---------------------------------------------------------------------------
# Partial memory of chain records (PREREG §17.3; gated in chain form)
# ---------------------------------------------------------------------------

CHAIN_HEURISTICS = {
    "flat_signed_sum": lambda a, f, n, x: a + f - n + x,
    "sign_blind": lambda a, f, n, x: a + f + n,
    "anchors_only": lambda a, f, n, x: a,
    "h1_as_clue": lambda a, f, n, x: a + f,
    "one_hop": lambda a, f, n, x: a - n,
    "decoy_pointer": lambda a, f, n, x: a + x - n,
}
"""Structural misreadings of a chain record, each giving a value per clue from its anchor a,
far delta f, near delta n and decoy delta x (the clue's value is a + f - n): every number of
the record signed by its word (error +x per clue); signs ignored (+2n); the anchor alone
(n - f); H1's value as the clue (+n); one hop from the anchor (-f); the decoy as the near
hop's base (x - f). The guess is the rule over these values; the pick is the nearest option
(ties to the lower)."""


def atom_narrowing(atoms: Sequence[tuple[int, int, int]], options: Sequence[int]) -> int:
    """Chain form: the number of proper subsets of the needed atoms (each clue's anchor, far
    delta and near delta; 3m in all) that, with the rule and the chain structure known,
    leave some option out of reach when every missing anchor ranges over
    `CHAIN_ANCHOR_RANGE` and every missing delta over `CHAIN_DELTA_RANGE`. The value is
    the sum of the atoms' contributions (+a, +f, -n), so the reachable values form an
    interval and this test is exact."""
    alo, ahi = CHAIN_ANCHOR_RANGE
    dlo, dhi = CHAIN_DELTA_RANGE
    contrib = []  # (value, lowest, highest) of each atom's contribution
    for a, f, n in atoms:
        contrib += [(a, alo, ahi), (f, dlo, dhi), (-n, -dhi, -dlo)]
    omin, omax = min(options), max(options)
    count = 0
    for mask in range(2 ** len(contrib) - 1):  # bit set = atom kept; all kept excluded
        lo = hi = 0
        for k, (v, low, high) in enumerate(contrib):
            if mask >> k & 1:
                lo, hi = lo + v, hi + v
            else:
                lo, hi = lo + low, hi + high
        count += not (lo <= omin and omax <= hi)
    return count


def chain_partial_memory(items: Sequence[tuple[int, Sequence[tuple[int, int, int, int]],
                                               Sequence[int], int]], cfg: dict) -> dict:
    """What partial memory or a misreading of chain records gives (PREREG §17.3). `items`:
    one (n_clues, [(anchor, far, near, decoy) per clue], option values, target) per
    template. Gated (each must hold): `atom_narrowing_templates` = 0 (`atom_narrowing`) and
    every `CHAIN_HEURISTICS` accuracy <= chance + margin."""
    K = cfg["K_options"]
    threshold = 1 / K + cfg["validity_margin_pp"] / 100
    rows: dict[int, list[dict]] = defaultdict(list)
    for n_clues, chains, values, target in items:
        hits = {}
        for name, fn in CHAIN_HEURISTICS.items():
            guess = sum(fn(*ch) for ch in chains)
            hits[name] = min(values, key=lambda v, g=guess: (abs(v - g), v)) == target
        rows[n_clues].append({"narrowing": atom_narrowing([ch[:3] for ch in chains], values),
                              "hits": hits})

    def agg(rs: list[dict]) -> dict:
        n = len(rs)
        return {"n_templates": n,
                "atom_narrowing_templates": sum(bool(r["narrowing"]) for r in rs),
                "heuristics": {k: sum(r["hits"][k] for r in rs) / n for k in CHAIN_HEURISTICS}}

    out: dict = {"chance": 1 / K, "threshold": threshold,
                 "by_n_clues": {str(k): agg(v) for k, v in sorted(rows.items())}}
    every = [r for v in rows.values() for r in v]
    out["all"] = agg(every) if every else None
    a = out["all"]
    out["pass"] = a is None or (a["atom_narrowing_templates"] == 0
                                and all(x <= threshold for x in a["heuristics"].values()))
    return out


def _chain_items(eps: Sequence[Episode]) -> list[tuple]:
    """`chain_partial_memory` items from the episode text (the atoms parsed from each clue's
    chain record), one per base episode."""
    out = []
    for e in eps:
        chains = _chain_clues(e.components, e.kind)
        parsed = [chains[i] for i in sorted(chains)]
        if None in parsed:
            raise ValueError(f"{e.episode_id}: a clue record is not a chain record")
        out.append((e.n_clues, [(p.anchor, p.far, p.near, p.decoy) for p in parsed],
                    [o.value for o in e.options], e.target_value))
    return out


# ---------------------------------------------------------------------------
# Oracles
# ---------------------------------------------------------------------------

def oracle_scores(episodes: Sequence[Episode]) -> dict:
    """Need-step and routine accuracy of the oracles, by variant. Expected: key and text
    oracles 100% on base and restated; lookup oracle 100% on recoverable base cells."""
    rows: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for ep in episodes:
        for name, pol in (("key", KeyOracle(ep)), ("text", TextOracle()),
                          ("lookup_no_memory", TextOracle(memory=False, use_lookup=True))):
            r = run_episode(ep, pol)
            key = f"{ep.variant}/{'rec' if ep.cell.recoverable else 'nonrec'}"
            rows[name][key].append((r.need_correct, r.routine_accuracy, r.n_lookups))
    out: dict = {}
    for name, groups in rows.items():
        out[name] = {k: {"n": len(v), "need_acc": sum(x[0] for x in v) / len(v),
                         "routine_acc": sum(x[1] for x in v) / len(v),
                         "mean_lookups": sum(x[2] for x in v) / len(v)}
                     for k, v in sorted(groups.items())}
    must = [out["key"].get(k, {}).get("need_acc", 1.0) for k in out["key"]
            if not k.startswith("withheld")]
    must += [out["text"].get(k, {}).get("need_acc", 1.0) for k in out["text"]
             if not k.startswith("withheld")]
    must += [v["need_acc"] for k, v in out["lookup_no_memory"].items()
             if k in ("base/rec", "restated/rec", "restated/nonrec")]
    routine = [v["routine_acc"] for o in ("key", "text") for v in out[o].values()]
    out["pass"] = all(x == 1.0 for x in must) and all(x == 1.0 for x in routine)
    return out
