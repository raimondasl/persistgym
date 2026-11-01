"""analysis.arc_trigger on hand-written steps (synthetic; no real run is read)."""

from __future__ import annotations

import json

import pytest

from analysis import arc_trigger as at
from analysis import checkpoint_c as cc


def _m(role, n, tag=""):
    return {"role": role, "content": (tag + "x" * n)[:max(n, len(tag))]}


def _step(step, sent, reply="r", prompt=100, retries=0):
    return {"step": step, "messages_sent": sent, "assistant_response": reply,
            "usage": {"prompt_tokens": prompt, "total_tokens": prompt + 10}, "retries": retries}


def test_trim_follows_the_harness_rule():
    conv = [("system", "s"), ("user", "u1"), ("assistant", "a1"), ("user", "u2"),
            ("assistant", "a2"), ("user", "u3")]
    # drop the oldest pair while over the limit (here: more than 4 messages)
    assert at.trim(conv, lambda c: len(c) > 4) == [("system", "s"), ("user", "u2"),
                                                   ("assistant", "a2"), ("user", "u3")]
    # never below system + the current user turn
    assert at.trim(conv, lambda c: True) == [("system", "s"), ("user", "u3")]


def test_rebuild_aligns_trimmed_requests():
    s, u1, u2, u3 = _m("system", 3, "S"), _m("user", 5, "1"), _m("user", 5, "2"), _m("user", 5, "3")
    a = lambda t: {"role": "assistant", "content": t}
    steps = [_step(1, [s, u1], reply="A1"),
             _step(2, [s, u1, a("A1"), u2], reply="A2"),
             _step(3, [s, u2, a("A2"), u3], reply="A3")]  # the oldest pair was trimmed
    full = [f for _, f in at.rebuild(steps)]
    assert [c for _, c in full[2]] == [s["content"], u1["content"], "A1", u2["content"], "A2",
                                       u3["content"]]


def test_rebuild_refuses_a_request_that_does_not_extend_the_history():
    s, u1, u2, u3 = _m("system", 4, "S"), _m("user", 5, "1"), _m("user", 5, "2"), _m("user", 5, "3")
    a = lambda t: {"role": "assistant", "content": t}
    # step 3 carries an earlier reply that differs from the recorded one
    steps = [_step(1, [s, u1], reply="a1"),
             _step(2, [s, u1, a("a1"), u2], reply="a2"),
             _step(3, [s, u2, a("b2"), u3], reply="a3")]
    with pytest.raises(cc.Refusal):
        at.rebuild(steps)
    # a window of just the system prompt and the new observation is a valid suffix
    steps[2]["messages_sent"] = [s, u3]
    assert len(at.rebuild(steps)) == 3


def test_replay_reproduces_what_was_sent_and_counts_extra_replies(monkeypatch):
    monkeypatch.setattr(at, "LIMIT", 30)
    s = {"role": "system", "content": "s" * 4}
    us = [{"role": "user", "content": str(i) * 10} for i in range(1, 5)]
    a = lambda i: {"role": "assistant", "content": f"a{i}"}
    # at 30 characters the harness keeps the system prompt, one earlier pair and the new turn
    steps = [_step(1, [s, us[0]], reply="a1"),
             _step(2, [s, us[0], a(1), us[1]], reply="a2"),
             _step(3, [s, us[1], a(2), us[2]], reply="a3"),
             _step(4, [s, us[2], a(3), us[3]], reply="a4")]
    r = at.replay(steps, rate=0.5)  # at 0.5 tokens per character, 60 characters fit
    assert (r["call_steps"], r["reproduced"]) == (4, 4)
    assert r["limit_chars_equivalent"] == 60
    # under the token limit step 3 keeps one more earlier pair and step 4 two more
    assert r["steps_changed"] == 2 and r["extra_replies_mean"] == 0.75
    # a request the character rule does not reproduce is refused
    steps[3]["messages_sent"] = [s, us[3]]
    with pytest.raises(cc.Refusal):
        at.replay(steps, rate=0.5)


def test_tokens_per_char_skips_retries_and_the_step_after_a_summary():
    sent = [{"role": "system", "content": "x" * 50}, {"role": "user", "content": "y" * 50}]
    steps = [_step(1, sent, prompt=90), _step(2, sent, prompt=500, retries=1),
             _step(3, sent, prompt=10), _step(4, sent, prompt=80)]
    assert at.tokens_per_char(steps, after_compaction={3}) == [0.9, 0.8]


def test_reply_shares_count_only_earlier_replies():
    sent = [{"role": "system", "content": "s" * 10}, {"role": "user", "content": "u" * 60},
            {"role": "assistant", "content": "a" * 30}, {"role": "user", "content": "v" * 100}]
    steps = [_step(1, sent), _step(2, sent, retries=1)]
    assert at.reply_shares(steps, after_compaction=set()) == [0.15]


def _h(changed_steps):
    """A minimal compute() result for summary_lines: two games, one whose replay changes."""
    def cfg(rhae, chars_, replies_):
        return {"run_id": "r", "rhae": rhae, "call_steps": 10, "first_loss_before": 5,
                "compactions": 1, "verbatim_chars_mean": chars_, "verbatim_replies_mean": replies_,
                "verbatim_chars_vs_S0": 0.5, "verbatim_replies_vs_S0": 0.5}
    q = {"n": 3, "median": 0.98, "q1": 0.97, "q3": 0.99, "min": 0.9, "max": 1.0, "mean": 0.98}
    per_game = {}
    for g, ch in (("AA01", 0), ("BB02", changed_steps)):
        rp = {"call_steps": 10, "reproduced": 10, "steps_changed": ch,
              "extra_replies_mean": 0.5 if ch else 0.0, "replies_mean_at_chars": 2.0,
              "limit_chars_equivalent": 178_000}
        row = {c: cfg(10.0 if c == "S0" else 50.0, 1000, 4) for c in at.CONFIGS}
        for c in at.RATE_CONFIGS:
            row[c].update(tokens_per_char=dict(q, median=0.98 if g == "AA01" else 0.86),
                          reply_share=dict(q, median=0.01 if g == "AA01" else 0.25))
        row["S0"].update(replay=rp, replay_q1=rp, limit_ratio=1.017)
        row["delta_S1_minus_S0"] = 40.0
        per_game[g] = row
    pooled = {c: {"verbatim_chars_per_step": 1000, "verbatim_replies_per_step": 4}
              for c in at.CONFIGS}
    for c in at.CONFIGS[1:]:
        pooled[c].update(verbatim_chars_vs_S0=0.6, verbatim_replies_vs_S0=0.6, triggers=2,
                         triggers_prompt_under_limit=1,
                         trigger_request_chars_over_limit=dict(q, median=1.09))
    return {"generated_utc": "t", "git_commit": "abcdef0", "git_dirty": False, "limit": 175_000,
            "path_games": ["AA01", "BB02"], "per_game": per_game, "pooled": pooled,
            "games_replay_unchanged": ["AA01"], "delta_sum": 80.0,
            "delta_share_replay_unchanged": 0.5}


def test_summary_names_the_game_whose_window_changes():
    text = "\n".join(at.summary_lines(_h(changed_steps=4)))
    assert "changes no window on AA01. On BB02 it changes 4 of 10 windows" in text
    assert "The lowest S0 rate is BB02's" in text and ";" not in text.split("## What")[1]


def test_verbatim_leaves_out_system_bridge_and_current_observation():
    msgs = [{"role": "system", "content": "s" * 7},
            {"role": "user", "content": at.BRIDGE + " summary"},
            {"role": "user", "content": "o" * 10}, {"role": "assistant", "content": "a" * 3},
            {"role": "user", "content": "now" * 5}]
    assert at.verbatim(msgs) == (13, 1)


def test_first_trim_before_reads_the_log(tmp_path):
    (tmp_path / "harness.log").write_text(
        "x | INFO | Saved step 1 to a\nx | INFO | Saved step 2 to a\n"
        "x | INFO | Trimmed oldest turn: ['user', 'assistant']\nx | INFO | Saved step 3 to a\n",
        encoding="utf-8")
    assert at.first_trim_before(tmp_path) == 3
    (tmp_path / "harness.log").write_text("x | INFO | Saved step 1 to a\n", encoding="utf-8")
    assert at.first_trim_before(tmp_path) is None


def test_read_run_reads_triggers(tmp_path):
    h = tmp_path / "harness"
    h.mkdir()
    big = {"role": "user", "content": "g" * 200}
    sent = [{"role": "system", "content": "s"}, big]
    for d in (_step(1, sent, prompt=180), _step(2, sent, prompt=170, retries=0)):
        (h / f"step_{d['step']:03d}.json").write_text(json.dumps(d), encoding="utf-8")
    (h / "compaction_001.json").write_text(json.dumps({"before_step": 3, "trigger_tokens": 180}),
                                           encoding="utf-8")
    (tmp_path / "harness.log").write_text("", encoding="utf-8")
    r = at.read_run(tmp_path, "S1")
    assert r["first_loss_before"] == 3 and r["compactions"] == 1
    assert r["triggers"] == [{"prompt_tokens": 170, "trigger_tokens": 180, "request_chars": 201}]
