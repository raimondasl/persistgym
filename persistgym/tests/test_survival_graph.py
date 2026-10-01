import pytest

from persistgym import tokens
from persistgym.survival import (
    carried_in_text,
    designed_survival,
    flatten_payload,
    max_reply_tokens_for_survival,
    reference_window_payload,
    survival_from_payload,
    window_keep_start,
)

from .conftest import pick


def test_window_keep_start_toy():
    obs = [10, 10, 10, 10]  # current observation is index 3
    assert window_keep_start(obs, [0, 0, 0], W=40) == 0
    assert window_keep_start(obs, [0, 0, 0], W=39) == 1
    assert window_keep_start(obs, [5, 5, 5], W=40) == 1  # 10 + (10+5) + (10+5) = 40
    assert window_keep_start(obs, [5, 5, 5], W=39) == 2
    assert window_keep_start(obs, [5, 5, 5], W=9) == 3  # current turn always kept
    assert window_keep_start(obs, [0, 0, 0], W=40, system_tokens=10) == 1
    with pytest.raises(ValueError):
        window_keep_start(obs, [0], W=40)


def test_designed_survival_toy():
    obs = [10] * 6
    r = designed_survival(obs, 5, {"a": 1, "b": 4}, W=40, reply_tokens=0)
    assert r["keep_start"] == 2 and r["components"] == {"a": False, "b": True} and not r["S"]
    r = designed_survival(obs, 5, {"b": 4, "rule": None}, W=40, reply_tokens=0)
    assert r["S"]


def test_payload_survival_matches_design(small_eps, small_cfg):
    """A reference drop-oldest payload reproduces the designed S when replies are at the
    assumed maximum length."""
    R = small_cfg.assumed_max_reply_tokens
    filler_reply = ("x " * (R * 2))
    for ep in small_eps:
        if ep.variant != "base":
            continue
        n = ep.need_step
        # replies of exactly R tokens
        enc = tokens.encode(filler_reply)[:R]
        reply = tokens.decode(enc)
        assert tokens.count(reply) == R
        payload = reference_window_payload(ep, [reply] * n)
        s = survival_from_payload(ep, payload)
        assert s["S"] == ep.design["S_window_assumed_replies"], ep.episode_id
        short = reference_window_payload(ep, ["ACTION: ok(x)"] * n)
        if ep.cell.distance == "far":
            assert survival_from_payload(ep, short)["S"] is False  # far: evicted regardless


def test_far_cells_evicted_for_any_reply_length(small_eps):
    for ep in small_eps:
        if ep.variant == "base" and ep.cell.distance == "far":
            assert max_reply_tokens_for_survival(ep) is None
        if ep.variant == "base" and ep.cell.distance == "near":
            assert max_reply_tokens_for_survival(ep) >= ep.config["assumed_max_reply_tokens"]


def test_near_reply_budget_at_defaults_matches_design_doc(default_eps):
    """DESIGN.md §11: with the system prompt (95-150 tokens) counted toward W (D5), near
    cells keep S=1 up to uniform replies of 4,087-4,101 tokens (observed), 2,970-2,981
    (2 clues) and 2,225-2,234 (3 clues) at W=24,000 and v=1,500."""
    expected = {0: (4_087, 4_101), 2: (2_970, 2_981), 3: (2_225, 2_234)}
    for ep in default_eps:
        if ep.variant == "base" and ep.cell.distance == "near":
            assert ep.config["window_counts_system_prompt"]
            assert 95 <= ep.system_tokens <= 150
            gap = ep.design["gap_steps_earliest"]
            budget = max_reply_tokens_for_survival(ep)
            assert budget == (24_000 - ep.system_tokens - (gap + 1) * 1_500) // gap
            lo, hi = expected[ep.n_clues]
            assert lo <= budget <= hi
            assert budget > max_reply_tokens_for_survival(ep, count_system=False) - 40


def test_flatten_payload_formats():
    msgs = [
        {"role": "system", "content": "sys"},
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "u1"}]},
        {"type": "reasoning", "encrypted_content": "opaque"},
        {"role": "model", "parts": [{"text": "m1"}, {"thought_signature": "sig"}]},
        {"role": "assistant", "content": [{"type": "output_text", "text": "a1"}]},
    ]
    assert flatten_payload(msgs) == [("system", "sys"), ("user", "u1"), ("opaque", ""),
                                     ("assistant", "m1"), ("assistant", "a1")]


def test_survival_from_payload_separates_notes_and_summaries(small_eps):
    ep = pick(small_eps, "derived-nonrec-far")
    need = ep.need.observation
    notes = (f"Notes: {ep.entity} {ep.components[0].name} {ep.components[0].value}, "
             f"{ep.components[1].name} {ep.components[1].value}"
             + (f", {ep.components[2].name} {ep.components[2].value}" if ep.n_clues == 3 else ""))
    payload = [{"role": "system", "content": ep.system_prompt},
               {"role": "user", "content": "Summary: " + " ".join(c.sentence
                                                                  for c in ep.components)},
               {"role": "assistant", "content": notes + "\nACTION: ok(x)"},
               {"role": "user", "content": need}]
    s = survival_from_payload(ep, payload)
    assert s["S"] is True  # summary text counted when not excluded
    s = survival_from_payload(ep, payload, exclude_indices=[1])
    assert s["S"] is False
    assert s["assistant_carried"]["carried"] and s["assistant_carried"]["all_clues"]
    assert not s["assistant_carried"]["final_value"]


def test_survival_from_payload_ignores_lookup_responses(small_eps):
    """PREREG §2.8: S_verbatim leaves out every lookup response. A far window episode whose
    agent looked up two steps before need still has S = 0 at need (S = 1 there is the
    window-accounting bug stop), although the lookup response re-shows the records."""
    from persistgym.env import EpisodeEnv
    from persistgym.episode import LOOKUP_EVENT_MARKER

    for ep in small_eps:  # no scripted observation carries the marker
        assert not any(LOOKUP_EVENT_MARKER in s.observation for s in ep.steps), ep.episode_id
    ep = pick(small_eps, "derived-rec-far")
    n = ep.need_step
    env = EpisodeEnv(ep)
    shown = [(env.pending, env.observation)]
    while env.pending < n:
        lookup = env.pending == n - 2 and env.lookups_used == 0
        reply = (f"ACTION: lookup({ep.entity})" if lookup
                 else f"ACTION: {ep.steps[env.pending].expected_action}")
        obs, _ = env.step(reply)
        shown.append((env.pending, obs))
    lookup_text = next(o for p, o in shown if LOOKUP_EVENT_MARKER in o)
    assert all(c.sentence in lookup_text for c in ep.components)
    # what a drop-oldest window sends at need: the last few turns, lookup response included
    tail = [o for p, o in shown if p >= n - 3]
    payload = [{"role": "system", "content": ep.system_prompt}]
    for o in tail[:-1]:
        payload += [{"role": "user", "content": o}, {"role": "assistant", "content": "ok"}]
    payload.append({"role": "user", "content": tail[-1]})
    s = survival_from_payload(ep, payload)
    assert s["S"] is False and s["n_lookup_responses"] == 1
    # the same text as an ordinary observation would count, so the exclusion is what bites
    plain = [dict(m, content=m["content"].replace(LOOKUP_EVENT_MARKER, "EVENT: RECORDS"))
             for m in payload]
    assert survival_from_payload(ep, plain)["S"] is True


def test_carried_in_text(small_eps):
    """PREREG §2.8 (D6): whole-word `(?<![0-9A-Za-z])VALUE(?![0-9A-Za-z])` anywhere in the
    model's text; the value, or for a derived fact every clue value; rule not required."""
    obs = pick(small_eps, "observed-nonrec-far")
    v, e = obs.target_value, obs.entity
    assert carried_in_text(f"{e} goes to {v}", obs)["carried"]
    assert not carried_in_text(f"{e} goes somewhere", obs)["carried"]
    far_away = f"{e}" + " filler" * 100 + f" {v}"
    assert carried_in_text(far_away, obs)["carried"]  # no proximity window any more
    assert carried_in_text(f"slot={v}; ({v}) [{v}].", obs)["carried"]
    assert carried_in_text(f"remember {v}", obs)["carried"]  # entity need not appear
    for miss in (f"{v}1", f"1{v}", f"x{v}", f"{v}b", f"A{v}"):  # digits or letters adjacent
        assert not carried_in_text(f"{e} goes to {miss}", obs)["carried"], miss
    assert not carried_in_text(" ".join(str(d.value) for d in obs.distractors), obs)["carried"]
    der = pick(small_eps, "derived-nonrec-near")
    assert carried_in_text(f"{der.entity}: {der.target_value}", der)["carried"]
    clue_vals = [c.value for c in der.components if c.role == "clue"]
    nums_only = " ".join(map(str, clue_vals))
    res = carried_in_text(nums_only, der)  # no names, no rule, no entity: still carried
    assert res["carried"] and res["all_clues"] and not res["final_value"]
    assert not res["entity_mentioned"]
    res = carried_in_text(" ".join(map(str, clue_vals[1:])), der)  # base clue lost
    assert not res["carried"] and not res["all_clues"]


def test_dependency_graph(small_eps):
    ep = pick(small_eps, "derived-rec-far")
    g = ep.graph
    assert g.needed_step("fact") == ep.need_step
    assert sorted(g.required_components()) == sorted(f"comp:{c.comp_id}" for c in ep.components)
    latest = max(c.step for c in ep.components)
    assert g.live["fact"] == [latest, ep.need_step]
    for c in ep.components:
        assert g.live[f"comp:{c.comp_id}"] == [c.step, ep.need_step]
        assert {"src": f"obs:{c.step}", "dst": f"comp:{c.comp_id}", "rel": "reveals"} in g.edges
        assert {"src": "env:lookup", "dst": f"comp:{c.comp_id}", "rel": "re-shows"} in g.edges
    assert "fact" in g.live_at(ep.need_step) and "fact" not in g.live_at(latest - 1)
    assert not [e for e in g.edges if e["dst"] == f"act:{ep.need_step - 1}"
                and e["src"] != f"obs:{ep.need_step - 1}"]  # routine needs only its own obs
    wh = pick(small_eps, "derived-rec-far", "withheld")
    assert wh.graph.required_components() == []
    non = pick(small_eps, "observed-nonrec-near")
    assert not [e for e in non.graph.edges if e["src"] == "env:lookup"]
