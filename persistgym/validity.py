"""$0 validity checks (PLAN §5 validity gate, amendment §16.3, PREREG D1-D3).

1. `shortcut_audit`: re-derives from the rendered text, independently of the generator's own
   bookkeeping, that the target, its clues and the distractor bindings never leak through
   filler, routine text or option ordering, that the cell manipulation is what it claims to
   be, and that templates are balanced within their blocks.
2. `lookup_audit`: lookup re-shows the target's records or a distractor's binding by key,
   answers unknown keys with "no such record" and answers a lookup over the cap with "lookup
   unavailable" without scoring it (D3).
3. `heuristic_baselines`: no-memory heuristics (most-frequent option, last-seen option and
   position/prior guesses) on views without the fact. Each must score <= chance + margin.
4. `partial_memory_diagnostic`: in derived cells, no proper subset of the clues (with the
   rule) rules out any option, and the partial-memory heuristics score <= chance + margin
   (D2; gated).
5. `oracle_scores`: the programmatic oracles (must be 100%; see oracle.py).
"""

from __future__ import annotations

import itertools
import re
from collections import Counter, defaultdict
from collections.abc import Sequence

from scipy import stats

from persistgym import tokens
from persistgym.env import EpisodeEnv
from persistgym.episode import Episode
from persistgym.oracle import KeyOracle, TextOracle, run_episode
from persistgym.skins import get_skin
from persistgym.survival import window_keep_start
from persistgym.template import BASE_CLUE_RANGE, split_of_seed

OPTION_LINE = re.compile(r"^[A-Z]\) \d+$", re.MULTILINE)


def _num_re(values: Sequence[int]) -> re.Pattern:
    return re.compile(r"(?<![0-9])(?:" + "|".join(str(v) for v in values) + r")(?![0-9])")


def _word_re(words: Sequence[str]) -> re.Pattern:
    ws = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
    return re.compile(rf"(?<![A-Za-z])(?:{ws})(?![A-Za-z])", re.IGNORECASE)


def reserved_of(ep: Episode, clue_values: Sequence[int] = ()) -> tuple[list[int], list[str]]:
    """Reserved numbers and words, derived from the episode alone."""
    skin = get_skin(ep.skin)
    nums = {o.value for o in ep.options} | {ep.target_value} | set(clue_values)
    nums |= {c.value for c in ep.components if c.value is not None}
    nums |= {d.value for d in ep.distractors}
    words = [ep.entity, ep.quantity, *skin.components, *(d.entity for d in ep.distractors)]
    return sorted(nums), words


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
    # Clue values are visible only in derived base episodes; collect them per template.
    clue_vals: dict[str, set[int]] = defaultdict(set)
    for ep in episodes:
        clue_vals[ep.template_id] |= {c.value for c in ep.components if c.role == "clue"}

    filler_hits, routine_hits, budget_bad, final_form, observed_extra = [], [], [], [], []
    option_bad, clue_in_options, design_bad, too_long, not_cluster = [], [], [], [], []
    distractor_bad = []
    recounted: dict[str, int] = {}  # observation text -> recounted tokens (deduplicated)
    regexes: dict[str, tuple[re.Pattern, re.Pattern]] = {}
    for ep in episodes:
        cfg = ep.config
        if ep.template_id not in regexes:
            nums, words = reserved_of(ep, sorted(clue_vals[ep.template_id]))
            regexes[ep.template_id] = (_num_re(nums), _word_re(words))
        num_re, word_re = regexes[ep.template_id]
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

    # Balance of the correct letter, the correct value's rank and the number of clues (one
    # episode per template; a derived one where possible, since it knows the clue count).
    one = [next((e for e in eps if e.cell.fact == "derived"), eps[0])
           for eps in by_template.values()]
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
        _check("near_far_hold_when_recomputed_from_text", not design_bad, design_bad[:10]),
        _check("full_history_context_within_max", not too_long, too_long[:10]),
        _check("cells_share_need_step_options_routine_and_distractors", not inconsistent,
               inconsistent[:10]),
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

def _play(ep: Episode, at_need: list[str]) -> tuple[EpisodeEnv, list[str]]:
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


def lookup_audit(episodes: Sequence[Episode]) -> list[dict]:
    """Play recoverable base episodes with lookups at the need step and check D3:
    * lookup(target) re-shows every target record, and no distractor binding;
    * lookup(distractor) re-shows that distractor's binding, and no target record;
    * lookup(unknown key) answers "no such record";
    * after the cap, a lookup answers "lookup unavailable", costs one turn, is not scored,
      and the next answer is scored as usual; a second over-cap lookup at the same step is
      an invalid action.
    """
    bad: list[tuple] = []
    n = 0
    for ep in episodes:
        if ep.variant != "base" or not ep.cell.recoverable:
            continue
        n += 1
        cap = ep.lookup.max_per_episode
        answer = f"ACTION: {ep.need.expected_action}"
        keys = [ep.entity.lower(), *(f"{ep.kind} {d.entity}" for d in ep.distractors)]
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
    return [_check("lookup_serves_keys_and_refuses_after_cap", not bad,
                   {"n_episodes": n, "problems": bad[:10]})]


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
    results["pass"] = ok
    return results


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
    return {"cells": cells, "pass": all(c["pass"] for c in cells.values())}


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
