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
    assert "no records yet" in seen[1]
    assert "no records found" in seen[3]
    assert env.result().n_turns == ep.n_steps + 2


def test_lookup_key_matches_entity_as_a_word(small_eps):
    ep = pick(small_eps, "observed-rec-far")
    for key, ok in ((ep.entity, True), (ep.entity.lower(), True),
                    (f"{ep.kind} {ep.entity}", True), (f"'{ep.entity}' records", True),
                    (ep.entity + "S", False), ("x" + ep.entity, False), ("everything", False)):
        def policy(env, key=key):
            if env.pending == ep.need_step and env.lookups_used == 0:
                return f"ACTION: lookup({key})"
            return _key(env)

        env, seen = _play(ep, policy)
        lookup_obs = seen[ep.need_step + 1]
        assert (ep.components[0].sentence in lookup_obs) is ok, key
        assert ("no records found" in lookup_obs) is (not ok), key
        assert env.result().n_turns == ep.n_steps + 1


def test_lookup_limit_and_nonrecoverable(small_eps):
    rec = pick(small_eps, "observed-rec-far")
    cap = rec.lookup.max_per_episode

    def spam(env):
        return f"ACTION: lookup({rec.entity})" if env.pending == rec.need_step else _key(env)

    r = _play(rec, spam)[0].result()
    assert r.n_lookups == cap
    assert r.step_outcomes[rec.need_step] == "invalid_lookup" and not r.need_correct

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
