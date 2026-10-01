"""Tests for the offline smoke runner (arc/offline_smoke.py, arc/offline_smoke_inner.py).

Everything here runs without the patched harness: the harness steps are mocked.
The real end-to-end run (builds the patched harness, plays the toy game under
S0, S1, S2 and S4) is opt-in: RUN_OFFLINE_SMOKE=1 uv run pytest -q arc.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
from pathlib import Path

import httpx
import openai
import pytest

from arc import apply_patches as ap
from arc import offline_smoke as smoke
from arc import offline_smoke_inner as inner

OBSERVATION = (
    "State: NOT_FINISHED\nLevels completed: 0\n\nFrame 0:\n  [0, 0]\n\n"
    "Available actions:\n- RESET\n- ACTION1\n- ACTION6 x y  (where x and y are integers 0-63)"
)


# ── Stub model ─────────────────────────────────────────────────────────


class TestStubPolicy:
    def test_parses_the_last_available_actions_block(self):
        assert inner.available_actions(OBSERVATION) == ["RESET", "ACTION1", "ACTION6"]
        assert inner.available_actions("no actions here") == []

    def test_script_repeats_its_last_action(self):
        policy = inner.StubPolicy(script=["ACTION2", "ACTION1"])

        assert [policy.next_action(OBSERVATION) for _ in range(4)] == [
            "ACTION2",
            "ACTION1",
            "ACTION1",
            "ACTION1",
        ]

    def test_seeded_choice_never_resets_and_is_reproducible(self):
        first = [inner.StubPolicy(seed=3).next_action(OBSERVATION) for _ in range(1)]
        policy, again = inner.StubPolicy(seed=3), inner.StubPolicy(seed=3)
        picks = [policy.next_action(OBSERVATION) for _ in range(50)]

        assert picks == [again.next_action(OBSERVATION) for _ in range(50)]
        assert first[0] == picks[0]
        assert not any(pick.startswith("RESET") for pick in picks)
        for pick in picks:
            if pick.startswith("ACTION6"):
                x, y = map(int, pick.split()[1:])
                assert 0 <= x <= 63 and 0 <= y <= 63

    def test_falls_back_to_action1_without_listed_actions(self):
        assert inner.StubPolicy().next_action("") == "ACTION1"


class TestStubUsage:
    def test_fixed_usage_reports_the_trigger_on_chosen_turns(self):
        usage = inner.StubUsage("fixed", {2})

        assert [usage.total_tokens(turn, 10) for turn in (1, 2, 3)] == [120, 180_000, 120]

    def test_chars_usage_counts_request_text(self):
        assert inner.StubUsage("chars").total_tokens(1, 1_000) == 1_020

    def test_unknown_mode_is_rejected(self):
        with pytest.raises(ValueError, match="Unknown usage mode"):
            inner.StubUsage("tokens")


def _interactions_body(system: str, texts: list[str]) -> dict:
    return {
        "model": "gemini-3.8-flash",
        "system_instruction": system,
        "input": [
            {"type": "user_input", "content": [{"type": "text", "text": text}]}
            for text in texts
        ],
    }


class TestStubModel:
    def test_answers_interactions_requests_with_canned_actions(self):
        stub = inner.StubModel(inner.StubPolicy(script=["ACTION1"]), inner.StubUsage())
        with httpx.Client(transport=httpx.MockTransport(stub)) as client:
            response = client.post(
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                json=_interactions_body("play", [OBSERVATION]),
            ).json()

        assert response["status"] == "completed"
        assert [step["type"] for step in response["steps"]] == ["thought", "model_output"]
        assert response["steps"][1]["content"][0]["text"] == "turn 1: ACTION1"
        assert response["usage"]["total_tokens"] == 120
        assert response["model"] == "gemini-3.8-flash-stub"
        assert stub.reported_totals == [120]

    def test_summary_requests_get_a_summary_and_no_turn(self):
        stub = inner.StubModel(inner.StubPolicy(), inner.StubUsage())
        with httpx.Client(transport=httpx.MockTransport(stub)) as client:
            response = client.post(
                "https://example.test/interactions",
                json=_interactions_body(inner.SUMMARY_SYSTEM_PROMPT, ["history", "summarize"]),
            ).json()

        assert response["steps"][1]["content"][0]["text"].startswith("summary 1")
        assert stub.summaries == 1
        assert stub.reported_totals == []

    def test_chat_completions_through_the_openai_sdk(self):
        stub = inner.StubModel(inner.StubPolicy(script=["ACTION1"]), inner.StubUsage())
        client = openai.OpenAI(
            api_key="stub",
            base_url="https://api.openai.com/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(stub)),
        )

        completion = client.chat.completions.create(
            model="stub-model",
            messages=[
                {"role": "system", "content": "play"},
                {"role": "user", "content": OBSERVATION},
            ],
        )

        assert completion.choices[0].message.content == "turn 1: ACTION1"
        assert inner.last_user_text(stub.bodies[0]) == OBSERVATION

    def test_request_texts_cover_both_apis(self):
        chat = {"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]}

        assert inner.request_texts(chat) == ("s", ["u"])
        assert inner.request_texts(_interactions_body("s", ["a", "b"])) == ("s", ["a", "b"])
        assert inner.last_user_text(_interactions_body("s", ["a", "b"])) == "b"


class TestInnerSafety:
    def test_guard_blocks_non_loopback_connections(self, monkeypatch):
        monkeypatch.setattr(socket.socket, "connect", socket.socket.connect)
        monkeypatch.setattr(socket.socket, "connect_ex", socket.socket.connect_ex)
        inner.guard_network()

        with pytest.raises(RuntimeError, match="blocked a connection"):
            socket.create_connection(("192.0.2.1", 443), timeout=0.1)

    def test_refuses_to_run_outside_offline_mode(self, monkeypatch, tmp_path):
        monkeypatch.delenv("OPERATION_MODE", raising=False)

        code = inner.main(["--config", "x", "--game", "toyg", "--out", str(tmp_path)])

        assert code == 2

    def test_summary_prompt_copy_matches_the_runner(self):
        assert inner.SUMMARY_SYSTEM_PROMPT == smoke.SUMMARY_SYSTEM_PROMPT


# ── Runner ─────────────────────────────────────────────────────────────


def _metadata(directory: Path, game_id: str) -> None:
    directory.mkdir(parents=True)
    (directory / "metadata.json").write_text(json.dumps({"game_id": game_id}))


class TestGames:
    def test_local_games_and_missing_games(self, tmp_path):
        _metadata(tmp_path / "ft09" / "v1", "ft09-abc")
        (tmp_path / "broken").mkdir()
        (tmp_path / "broken" / "metadata.json").write_text("{not json")

        assert smoke.local_games(tmp_path) == {"ft09": "ft09-abc"}
        assert smoke.missing_games(tmp_path, ["ft09", "sb26"]) == ["sb26"]
        assert smoke.local_games(tmp_path / "absent") == {}

    def test_toy_game_is_staged_in_arc_agi_layout(self, tmp_path):
        smoke.stage_toy_game(tmp_path)

        metadata = json.loads((tmp_path / "toyg" / "v1" / "metadata.json").read_text())
        assert metadata["class_name"] == "Toyg"
        assert metadata["baseline_actions"] == [3, 3]
        assert (tmp_path / "toyg" / "v1" / "toyg.py").read_text().count("class Toyg(") == 1

    def test_toy_game_matches_the_copy_in_patch_0012(self):
        source = (smoke.TOY_DIR / "toyg.py").read_text()
        body = source[source.index("    def __init__") :].rstrip().splitlines()
        patch = next(ap.PATCH_DIR.glob("0012-*.patch")).read_text(encoding="utf-8")

        for line in body:
            assert "+" + line in patch.splitlines(), line


class TestInnerInvocation:
    def test_environment_has_no_keys_and_forces_offline(self, monkeypatch, tmp_path):
        monkeypatch.setenv("GOOGLE_API_KEY", "real-looking-value")
        monkeypatch.setenv("ARC_API_KEY", "real-looking-value")
        monkeypatch.setenv("OPERATION_MODE", "online")

        env = smoke.inner_env(
            worktree=tmp_path / "wt",
            environments_dir=tmp_path / "envs",
            scratch_dir=tmp_path / "scratch",
            harness_commit="abc123",
        )

        assert env["OPERATION_MODE"] == "offline"
        assert env["ENVIRONMENTS_DIR"] == str(tmp_path / "envs")
        assert env["PYTHONPATH"].split(os.pathsep) == [str(tmp_path / "wt"), str(ap.ARC_DIR)]
        assert env["ARC_HARNESS_COMMIT_SHA"] == "abc123"
        assert not [name for name in env if re.search("KEY|TOKEN|SECRET", name)]

    def test_command_runs_the_inner_script_in_the_worktree_venv(self, tmp_path):
        command = smoke.inner_command(
            worktree=tmp_path,
            config_id="google-gemini-3-8-flash-high",
            game="toyg",
            out_dir=tmp_path / "out",
            usage="fixed",
            trigger_turns="2",
            script="ACTION1",
            seed=7,
        )

        assert command[:6] == ["uv", "run", "--no-sync", "--project", str(tmp_path), "python"]
        assert command[6] == str(smoke.INNER)
        assert command[command.index("--trigger-turns") + 1] == "2"
        assert command[command.index("--seed") + 1] == "7"


def _body(system: str, items: list[tuple[str, str]], max_out: int = 65_536) -> dict:
    return {
        "model": "gemini-3.8-flash",
        "store": False,
        "generation_config": {
            "max_output_tokens": max_out,
            "thinking_level": "high",
            "thinking_summaries": "auto",
        },
        "system_instruction": system,
        "input": [
            {"type": kind, "content": [{"type": "text", "text": text}]} for kind, text in items
        ],
    }


NOTES = "You are playing. " + smoke.NOTES_SENTENCE + ", along with the action."
NO_NOTES = "You are playing."
BRIDGE = smoke.BRIDGE_PREFIX + " Use the following summary."


def _run(label: str) -> tuple[dict, list[dict]]:
    """A three-turn run with a summary after turn 2, as each config should send it."""
    system = NOTES if smoke.EXPECTED[label]["notes"] else NO_NOTES
    thought = [("thought", "t")] if smoke.EXPECTED[label]["thoughts"] else []
    bodies = [
        _body(system, [("user_input", "obs 1")]),
        _body(system, [("user_input", "obs 1"), *thought, ("model_output", "a"), ("user_input", "obs 2")]),
    ]
    runtime: dict = {}
    if smoke.EXPECTED[label]["summaries"]:
        bodies.append(
            _body(smoke.SUMMARY_SYSTEM_PROMPT, [("user_input", "history")], max_out=8_192)
        )
        bodies.append(_body(system, [("user_input", BRIDGE), ("user_input", "obs 3")]))
        runtime = {"compaction_count": 1, "context_trims": 0}
    else:
        bodies.append(_body(system, [("user_input", "obs 1"), ("user_input", "obs 3")]))
    result = {
        "steps": 3,
        "reported_totals": [120, 180_000, 120],
        "run_meta": {
            "exit_reason": "GAME_WIN",
            "agent_exit_reason": "GAME_WIN",
            "reported_models": ["gemini-3.8-flash-stub"],
            "arc_environment": {"kind": "local"},
            **({"runtime": runtime} if runtime else {}),
        },
    }
    return result, bodies


class TestCheckRun:
    @pytest.mark.parametrize("label", list(smoke.PATH_CONFIGS))
    def test_expected_behaviour_passes(self, label):
        result, bodies = _run(label)

        assert smoke.check_run(label, result, bodies) == []

    @pytest.mark.parametrize(
        ("label", "mutate", "problem"),
        [
            ("S0", lambda r, b: b.insert(2, _body(smoke.SUMMARY_SYSTEM_PROMPT, [])), "summary"),
            ("S1", lambda r, b: b[0].update(system_instruction=NO_NOTES), "notes sentence"),
            ("S2", lambda r, b: b[1]["input"].insert(1, {"type": "thought", "content": []}), "thought replay"),
            ("S4", lambda r, b: [b[i]["input"].pop(1) for i in (1,)], "thought replay"),
            ("S1", lambda r, b: r["run_meta"]["runtime"].update(context_trims=2), "context_trims"),
            ("S1", lambda r, b: b[1]["input"].pop(0), "oldest turn dropped"),
            ("S2", lambda r, b: b[3]["input"].pop(0), "oldest turn dropped"),
            ("S1", lambda r, b: b.pop(2), "no summary request"),
            ("S2", lambda r, b: b[3]["input"].pop(0), "bridge"),
            ("S4", lambda r, b: b[2]["generation_config"].update(max_output_tokens=9), "max_output_tokens"),
            ("S0", lambda r, b: r["run_meta"].update(exit_reason="AGENT_ERROR"), "exit_reason"),
            ("S1", lambda r, b: r["run_meta"].update(agent_exit_reason="API_ERROR"), "agent_exit_reason"),
            ("S4", lambda r, b: r["run_meta"].pop("reported_models"), "reported_models"),
            ("S0", lambda r, b: r["run_meta"].update(arc_environment={"kind": "remote"}), "arc_environment"),
            ("S1", lambda r, b: b[0].update(service_tier="flex"), "service_tier"),
            ("S0", lambda r, b: b[0]["generation_config"].update(thinking_level="low"), "thinking_level"),
        ],
    )
    def test_deviations_are_reported(self, label, mutate, problem):
        result, bodies = _run(label)
        mutate(result, bodies)

        problems = smoke.check_run(label, result, bodies)

        assert any(problem in text for text in problems), problems


class TestMain:
    def test_missing_games_stop_before_any_harness_work(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(ap, "create_worktree", lambda *a: pytest.fail("built harness"))

        code = smoke.main(["--games", "ft09", "--environments-dir", str(tmp_path)])

        assert code == 2
        assert "Nothing was downloaded" in capsys.readouterr().err

    def test_unknown_config_label(self, tmp_path):
        assert smoke.main(["--toy", "--configs", "S3", "--out", str(tmp_path)]) == 2

    def test_toy_run_with_mocked_harness(self, monkeypatch, tmp_path):
        calls: list[list[str]] = []
        monkeypatch.setattr(ap, "check_pin", lambda env: None)
        monkeypatch.setattr(ap, "create_worktree", lambda path, env: None)
        monkeypatch.setattr(ap, "apply_series", lambda path, patches, env: None)
        monkeypatch.setattr(ap, "sync_environment", lambda path, env: None)
        monkeypatch.setattr(ap, "remove_worktree", lambda path, env: None)
        monkeypatch.setattr(ap, "_git", lambda args, cwd, env: "f" * 40)

        def fake_run(command, cwd, env, *, capture=False):
            calls.append(command)
            assert env["OPERATION_MODE"] == "offline"
            assert Path(env["ENVIRONMENTS_DIR"], "toyg", "v1", "toyg.py").exists()
            out = Path(command[command.index("--out") + 1])
            label = out.name.split("-")[0]
            result, bodies = _run(label)
            run_dir = out / "run"
            run_dir.mkdir(parents=True)
            result["run_dir"] = str(run_dir)
            (out / "result.json").write_text(json.dumps({**result, "summaries": 1}))
            (out / "bodies.json").write_text(json.dumps(bodies))
            return subprocess.CompletedProcess(command, 0, "", "")

        monkeypatch.setattr(ap, "_run", fake_run)

        code = smoke.main(["--toy", "--out", str(tmp_path)])

        assert code == 0
        assert len(calls) == 4
        assert {call[call.index("--config") + 1] for call in calls} == set(
            smoke.PATH_CONFIGS.values()
        )
        summary = json.loads((tmp_path / "summary.json").read_text())
        assert [run["problems"] for run in summary["runs"]] == [[]] * 4
        assert summary["harness_commit"] == "f" * 40

    def test_toy_options_reach_the_inner_command(self, monkeypatch, tmp_path):
        commands: list[list[str]] = []
        for name in ("check_pin", "create_worktree", "apply_series", "sync_environment"):
            monkeypatch.setattr(ap, name, lambda *a, **k: None)
        monkeypatch.setattr(ap, "remove_worktree", lambda path, env: None)
        monkeypatch.setattr(ap, "_git", lambda args, cwd, env: "f" * 40)
        monkeypatch.setattr(
            ap,
            "_run",
            lambda command, cwd, env, capture=False: commands.append(command)
            or subprocess.CompletedProcess(command, 1, "", ""),
        )

        smoke.main(
            ["--toy", "--configs", "S1", "--usage", "chars", "--script", "ACTION3",
             "--out", str(tmp_path)]
        )  # fmt: skip

        command = commands[0]
        assert command[command.index("--usage") + 1] == "chars"
        assert command[command.index("--script") + 1] == "ACTION3"
        assert "--trigger-turns" not in command

    def test_failed_inner_run_is_reported(self, monkeypatch, tmp_path):
        for name in ("check_pin", "create_worktree", "apply_series", "sync_environment"):
            monkeypatch.setattr(ap, name, lambda *a, **k: None)
        monkeypatch.setattr(ap, "remove_worktree", lambda path, env: None)
        monkeypatch.setattr(ap, "_git", lambda args, cwd, env: "f" * 40)
        monkeypatch.setattr(
            ap,
            "_run",
            lambda command, cwd, env, capture=False: subprocess.CompletedProcess(
                command, 1, "", "boom"
            ),
        )

        code = smoke.main(["--toy", "--configs", "S0", "--out", str(tmp_path)])

        assert code == 1
        assert "boom" in (tmp_path / "S0-toyg" / "inner.log").read_text()


@pytest.mark.skipif(
    os.environ.get("RUN_OFFLINE_SMOKE") != "1"
    or not (ap.UPSTREAM_DIR / ".git").exists(),
    reason="set RUN_OFFLINE_SMOKE=1 to build the patched harness and play the toy game",
)
def test_end_to_end_toy_run(tmp_path):
    assert smoke.main(["--toy", "--out", str(tmp_path)]) == 0
