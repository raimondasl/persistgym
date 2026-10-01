"""$0 validity checks (PLAN §5 validity gate, amendment §16.3).

1. `shortcut_audit`: re-derives from the rendered text, independently of the generator's own
   bookkeeping, that the target and its clues never leak through filler, routine text or
   option ordering, and that the cell manipulation is what it claims to be.
2. `heuristic_baselines`: no-memory heuristics (most-frequent option, last-seen option and
   position/prior guesses) on views without the fact. Each must score <= chance + margin.
3. `oracle_scores`: the programmatic oracles (must be 100%; see oracle.py).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Sequence

from scipy import stats

from persistgym import tokens
from persistgym.episode import Episode
from persistgym.oracle import KeyOracle, TextOracle, run_episode
from persistgym.skins import get_skin
from persistgym.survival import window_keep_start

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
    words = [ep.entity, ep.quantity, *skin.components]
    return sorted(nums), words


def _check(name: str, ok: bool, detail) -> dict:
    return {"check": name, "pass": bool(ok), "detail": detail}


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
    option_bad, clue_in_options, design_bad, too_long = [], [], [], []
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
        if set(vals) & clue_vals[ep.template_id]:
            clue_in_options.append(ep.episode_id)

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

    # Cross-cell consistency within a template.
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
                if s.kind == "routine":
                    per_step[s.index].add(s.observation)
        if any(len(obs) > 1 for obs in per_step.values()):
            inconsistent.append(tid + ":routine")

    # Balance of the correct letter and the correct value's rank across templates.
    one = [eps[0] for eps in by_template.values()]
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

    return [
        _check("filler_has_no_reserved_strings", not filler_hits, filler_hits[:10]),
        _check("routine_events_have_no_reserved_strings", not routine_hits, routine_hits[:10]),
        _check("observation_tokens_equal_v", not budget_bad, budget_bad[:10]),
        _check("derived_and_withheld_never_show_target_before_need", not final_form,
               final_form[:10]),
        _check("observed_target_only_at_reveal", not observed_extra, observed_extra[:10]),
        _check("options_valid_and_distinct", not option_bad, option_bad[:10]),
        _check("options_exclude_clue_values", not clue_in_options, clue_in_options[:10]),
        _check("near_far_hold_when_recomputed_from_text", not design_bad, design_bad[:10]),
        _check("full_history_context_within_max", not too_long, too_long[:10]),
        _check("cells_share_need_step_options_and_routine_text", not inconsistent,
               inconsistent[:10]),
        _check("correct_letter_balanced", letter_bal["chi2_p"] is None or
               letter_bal["chi2_p"] > 0.01, letter_bal),
        _check("correct_rank_balanced", rank_bal["chi2_p"] is None or rank_bal["chi2_p"] > 0.01,
               rank_bal),
    ]


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
# Partial memory in derived cells (reported, not gated)
# ---------------------------------------------------------------------------

def partial_memory_diagnostic(items: Sequence[tuple[int, int, Sequence[int], int]],
                              minor_range: tuple[int, int], K: int) -> dict:
    """How much the base clue alone gives away in derived cells.

    This is not a no-memory shortcut: it measures what an agent that kept *part* of the
    derived state can do, which matters for rescue rates and P(rescued | not carried) in
    notes and summary cells. `items` holds one (n_clues, base clue value, option values,
    target value) per template; all derived cells of a template share them.

    * `base_and_range`: the agent kept the base clue and the rule, and knows the range of the
      addends (`minor_component_range`, which agents are never told). It drops every option
      outside [base + smallest addend sum, base + largest addend sum]. Reports how often one
      option remains and the expected accuracy of a uniform pick among those that remain.
    * `nearest_above_base`: the agent kept the base clue and picks the smallest option above
      it (no knowledge of the range).
    """
    lo_m, hi_m = minor_range
    rows: dict[int, list[tuple[int, float, bool]]] = defaultdict(list)
    for n_clues, base, values, target in items:
        k = n_clues - 1
        lo = base + sum(range(lo_m, lo_m + k))
        hi = base + sum(range(hi_m - k + 1, hi_m + 1))
        cands = [v for v in values if lo <= v <= hi]
        if target not in cands:  # cannot happen if the generator is right
            raise ValueError(f"target {target} outside the base-consistent window")
        above = sorted(v for v in values if v > base)
        rows[n_clues].append((len(cands), 1 / len(cands), bool(above) and above[0] == target))

    def agg(rs: list[tuple[int, float, bool]]) -> dict:
        n = len(rs)
        return {"n_templates": n,
                "base_and_range_unique_rate": sum(c == 1 for c, _, _ in rs) / n,
                "base_and_range_expected_accuracy": sum(a for _, a, _ in rs) / n,
                "base_and_range_mean_options_left": sum(c for c, _, _ in rs) / n,
                "nearest_above_base_accuracy": sum(x for _, _, x in rs) / n}

    out: dict = {"chance": 1 / K, "by_n_clues": {str(k): agg(v) for k, v in sorted(rows.items())}}
    every = [r for v in rows.values() for r in v]
    out["all"] = agg(every) if every else None
    return out


def partial_memory_from_episodes(episodes: Sequence[Episode]) -> dict | None:
    """`partial_memory_diagnostic` over the derived base episodes (one per template)."""
    per_t: dict[str, Episode] = {}
    for ep in episodes:
        if ep.variant == "base" and ep.cell.fact == "derived":
            per_t.setdefault(ep.template_id, ep)
    if not per_t:
        return None
    first = next(iter(per_t.values()))
    items = [(e.n_clues, e.component("clue0").value, [o.value for o in e.options],
              e.target_value) for e in per_t.values()]
    return partial_memory_diagnostic(items, tuple(first.config["minor_component_range"]),
                                     first.config["K_options"])


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
