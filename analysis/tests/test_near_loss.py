"""analysis.near_loss: pooled near losses per model, from synthetic raw pilot folders ($0)."""

import json

from analysis import near_loss


def _run(root, name, episodes):
    d = root / "persistgym_pilot" / name
    d.mkdir(parents=True)
    (d / "episodes.jsonl").write_text(
        "\n".join(json.dumps(e) for e in episodes) + "\n", encoding="utf-8")


def _ep(task_cell, s):
    return {"task_cell": task_cell, "need_payload": {"S": s}}


def test_counts_only_the_named_models_window_cells(tmp_path):
    _run(tmp_path, "20261002T082913Z-W-0-gpt-6-luna",
         [_ep("observed-rec-near", True), _ep("observed-rec-far", False)])
    _run(tmp_path, "20261018T043926Z-W-0-claude-haiku-5-5",
         [_ep("observed-rec-near", False), _ep("derived-nonrec-near", True)])
    _run(tmp_path, "20261018T043551Z-F-0-claude-haiku-5-5", [_ep("observed-rec-near", False)])

    luna = near_loss.pooled_near_losses(tmp_path / "persistgym_pilot")
    assert luna["runs"] == ["20261002T082913Z-W-0-gpt-6-luna"]
    assert (luna["near_window_episodes"], luna["near_lost_pooled"]) == (1, 0)
    assert luna["rule_cannot_fire"] is True

    haiku = near_loss.pooled_near_losses(tmp_path / "persistgym_pilot", "claude-haiku-5-5")
    assert haiku["runs"] == ["20261018T043926Z-W-0-claude-haiku-5-5"]   # F-0 is not a window cell
    assert (haiku["near_window_episodes"], haiku["near_lost_pooled"]) == (2, 1)
    assert haiku["rule_cannot_fire"] is False


def test_harness_cell_strips_the_model():
    assert near_loss.harness_cell("20261002T082913Z-W-n-0-gpt-6-luna") == "W-n-0"
    assert near_loss.harness_cell("20261018T044223Z-W-n-0-claude-haiku-5-5",
                                  "claude-haiku-5-5") == "W-n-0"
