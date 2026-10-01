import json

import pytest

from persistgym.env import EpisodeEnv, parse_action
from persistgym.episode import Episode
from persistgym.oracle import KeyOracle, TextOracle, run_episode

from .conftest import pick

VERBS = {"route", "alert", "ok", "ack", "lookup", "assign"}


def test_parse_action():
    p = parse_action("thinking...\nACTION: route(billing)", VERBS)
    assert (p.verb, p.arg) == ("route", "billing")
    p = parse_action("ACTION: assign(B)\nnotes\nACTION: assign( 'C' )", VERBS)
    assert (p.verb, p.arg) == ("assign", "C")
    p = parse_action("I will ack(M-1234) now", VERBS)
    assert (p.verb, p.arg) == ("ack", "M-1234")
    assert parse_action("I will ack(M-1234) now", VERBS, strict=True) is None
    assert parse_action("nothing here", VERBS) is None
    p = parse_action("ACTION: C", VERBS)
    assert p.verb is None and p.raw == "C"


def _play(ep: Episode, replies_for):
    env = EpisodeEnv(ep)
    obs, done = env.observation, False
    seen = [obs]
    while not done:
        obs, done = env.step(replies_for(env))
        if obs:
            seen.append(obs)
    return env, seen


def _key(env: EpisodeEnv) -> str:
    return f"ACTION: {env.ep.steps[env.pending].expected_action}"


def test_key_play_scores_everything(small_eps):
    ep = pick(small_eps, "derived-nonrec-far")
    env, seen = _play(ep, _key)
    r = env.result()
    assert r.need_correct and r.routine_accuracy == 1.0
    assert r.n_turns == ep.n_steps and r.n_lookups == 0
    assert seen == ep.observations


def test_value_answer_accepted_and_wrong_answer_scored(small_eps):
    ep = pick(small_eps, "observed-nonrec-near")

    def by_value(env):
        if env.pending == ep.need_step:
            return f"ACTION: {ep.need_verb}({ep.target_value})"
        return _key(env)

    assert _play(ep, by_value)[0].result().need_correct
    wrong = next(o.label for o in ep.options if o.label != ep.correct_label)

    def wrong_letter(env):
        return f"ACTION: {ep.need_verb}({wrong})" if env.pending == ep.need_step else _key(env)

    r = _play(ep, wrong_letter)[0].result()
    assert not r.need_correct and r.need_label == wrong

    r = _play(ep, lambda env: "no idea" if env.pending == ep.need_step else _key(env))[0]
    assert r.result().step_outcomes[ep.need_step] == "unparsed"


def test_lookup_costs_one_turn_and_reshows_records(small_eps):
    ep = pick(small_eps, "derived-rec-far")
    looked = []

    def policy(env):
        if env.pending == ep.need_step and not looked:
            looked.append(True)
            return f"ACTION: lookup({ep.entity.lower()})"
        return _key(env)

    env, seen = _play(ep, policy)
    r = env.result()
    assert r.need_correct and r.n_lookups == 1 and r.lookup_steps == [ep.need_step]
    assert r.n_turns == ep.n_steps + 1
    lookup_obs = seen[ep.need_step + 1]
    for c in ep.components:
        assert c.sentence in lookup_obs
    assert "Pending request (repeated): " + ep.need.event in lookup_obs
    turn = r.turns[ep.need_step + 1]
    assert turn.is_lookup_result and turn.observation_tokens == ep.config["v_tokens"]


def test_lookup_before_reveal_and_wrong_key(small_eps):
    ep = pick(small_eps, "observed-rec-near")
    calls = []

    def policy(env):
        if env.pending == 0 and len(calls) == 0:
            calls.append("early")
            return "ACTION: lookup(" + ep.entity + ")"
        if env.pending == 1 and len(calls) == 1:
            calls.append("wrong")
            return "ACTION: lookup(SOMETHING)"
        return _key(env)

    env, seen = _play(ep, policy)
    # PREREG §2.5: a key without a record shown so far returns "no such record", whether it
    # appears later (the target before its reveal) or never
    assert "no such record" in seen[1] and ep.components[0].sentence not in seen[1]
    assert "no such record" in seen[3]
    assert env.result().n_turns == ep.n_steps + 2


def test_lookup_key_matches_entity_as_a_word(small_eps):
    ep = pick(small_eps, "observed-rec-far")
    long_key = f"the {ep.quantity} record that was logged a while ago for {ep.kind} {ep.entity}"
    assert len(long_key) > 40 and long_key.find(ep.entity) > 40
    for key, ok in ((ep.entity, True), (ep.entity.lower(), True),
                    (f"{ep.kind} {ep.entity}", True), (f"'{ep.entity}' records", True),
                    # punctuation next to the name, and long keys, still name it as a word
                    (f'key="{ep.entity}"', True), (f"{ep.kind}:{ep.entity}", True),
                    (f"{ep.entity}'s {ep.quantity}", True), (long_key, True),
                    (ep.entity + "S", False), ("x" + ep.entity, False), ("everything", False),
                    (f"{ep.kind}{ep.entity}", False)):
        def policy(env, key=key):
            if env.pending == ep.need_step and env.lookups_used == 0:
                return f"ACTION: lookup({key})"
            return _key(env)

        env, seen = _play(ep, policy)
        lookup_obs = seen[ep.need_step + 1]
        assert (ep.components[0].sentence in lookup_obs) is ok, key
        assert ("no such record" in lookup_obs) is (not ok), key
        assert env.result().n_turns == ep.n_steps + 1


def test_lookup_serves_distractor_keys(small_eps):
    """D3: lookup(key) re-shows a distractor's binding for its key, never the target's
    records; a key naming two entities re-shows both, in display order."""
    ep = pick(small_eps, "derived-rec-far")
    d0, d1 = ep.distractors
    for key, shows, hides in (
            (d0.entity, [d0.sentence], [c.sentence for c in ep.components] + [d1.sentence]),
            (f"{ep.kind} {d1.entity.lower()}", [d1.sentence], [d0.sentence]),
            (f"{ep.entity}, {d0.entity}", [d0.sentence, *(c.sentence for c in ep.components)],
             [d1.sentence])):
        def policy(env, key=key):
            if env.pending == ep.need_step and env.lookups_used == 0:
                return f"ACTION: lookup({key})"
            return _key(env)

        env, seen = _play(ep, policy)
        lookup_obs = seen[ep.need_step + 1]
        assert all(s in lookup_obs for s in shows), key
        assert not any(s in lookup_obs for s in hides), key
        assert env.result().need_correct and env.result().n_lookups == 1
    # records in display order: the earlier record comes first
    both = [(d0.step, d0.sentence), (min(c.step for c in ep.components),
                                     ep.components[0].sentence)]
    first, second = (s for _, s in sorted(both))
    assert lookup_obs.index(first) < lookup_obs.index(second)


def test_lookup_over_the_cap_is_unavailable_not_wrong(small_eps):
    """D3: the 4th lookup returns 'lookup unavailable' at the cost of one turn and is not
    scored; the agent's next action at the need step is. A second over-cap lookup at the
    same step is an invalid action."""
    rec = pick(small_eps, "observed-rec-far")
    cap = rec.lookup.max_per_episode
    n = rec.need_step

    def then_answer(env):
        if env.pending == n:
            if env.lookups_used < cap or not env.unavailable_steps:
                return f"ACTION: lookup({rec.entity})"
            return f"ACTION: {rec.need.expected_action}"
        return _key(env)

    env, seen = _play(rec, then_answer)
    r = env.result()
    assert r.need_correct and r.step_outcomes[n] == "correct"
    assert r.n_lookups == cap and r.n_lookups_unavailable == 1
    assert r.lookup_unavailable_steps == [n] and r.n_turns == rec.n_steps + cap + 1
    refusal = seen[n + cap + 1]
    assert "lookup unavailable" in refusal and rec.components[0].sentence not in refusal
    assert "Pending request (repeated): " + rec.need.event in refusal
    turn = r.turns[n + cap + 1]
    assert turn.is_lookup_result and turn.is_lookup_unavailable
    assert turn.observation_tokens == rec.config["v_tokens"]
    assert [t.outcome for t in r.turns[n: n + cap + 2]] == (
        ["lookup"] * cap + ["lookup_unavailable", "correct"])

    # lookups used up before the need step: one refusal per pending step, then invalid
    def spam(env):
        return f"ACTION: lookup({rec.entity})" if env.pending in (n - 1, n) else _key(env)

    r = _play(rec, spam)[0].result()
    assert r.n_lookups == cap and r.lookup_steps == [n - 1] * cap
    assert r.lookup_unavailable_steps == [n - 1, n]
    assert r.step_outcomes[n - 1] == r.step_outcomes[n] == "invalid_lookup"
    assert not r.need_correct and r.n_turns == rec.n_steps + cap + 2


def test_lookup_in_nonrecoverable_cell_is_invalid(small_eps):
    """PREREG §2.5: lookup is not offered, so it is an invalid action (scored 0 at need)."""
    non = pick(small_eps, "observed-nonrec-far")

    def one_lookup(env):
        return f"ACTION: lookup({non.entity})" if env.pending == non.need_step else _key(env)

    r = _play(non, one_lookup)[0].result()
    assert r.n_lookups == 0 and r.n_turns == non.n_steps
    assert r.step_outcomes[non.need_step] == "invalid_lookup"


def test_env_works_on_episode_loaded_from_json(small_eps):
    ep = pick(small_eps, "observed-rec-far")
    back = Episode.from_dict(json.loads(json.dumps(ep.to_dict())))
    r = run_episode(back, TextOracle(memory=False, use_lookup=True))
    assert r.need_correct and r.n_lookups == 1


def test_oracles_score_100_percent(small_eps):
    for ep in small_eps:
        k = run_episode(ep, KeyOracle(ep))
        assert k.need_correct and k.routine_accuracy == 1.0
        t = run_episode(ep, TextOracle())
        assert t.routine_accuracy == 1.0
        if ep.variant != "withheld":
            assert t.need_correct, ep.episode_id
        if ep.variant != "withheld" and (ep.cell.recoverable or ep.variant == "restated"):
            assert run_episode(ep, TextOracle(memory=False, use_lookup=True)).need_correct


def test_no_memory_oracle_is_at_chance_without_lookup(small_eps):
    far = [e for e in small_eps if e.variant == "base" and not e.cell.recoverable]
    acc = sum(run_episode(e, TextOracle(memory=False)).need_correct for e in far) / len(far)
    assert acc <= 0.2


def test_finished_episode_rejects_more_steps(small_eps):
    ep = pick(small_eps, "observed-nonrec-near")
    env, _ = _play(ep, _key)
    with pytest.raises(RuntimeError):
        env.step("ACTION: ok(x)")
