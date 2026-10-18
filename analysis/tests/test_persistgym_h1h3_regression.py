"""The luna regression check (analysis/persistgym_h1h3_regression.py; PREREG §17.8, R8): the
comparison of an output folder with luna's cited H1/H3 output (what it ignores, what it
resolves, what it reports), the re-run's arguments, and its command line, on copies of the
committed cited output. No test re-runs luna's sweep: its raw transcripts are gitignored.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

from analysis import persistgym_h1h3 as hh
from analysis import persistgym_h1h3_regression as rg
from common import runmeta

GIT = {"git_commit": "1" * 40, "git_dirty": False}


@pytest.fixture
def copy(tmp_path):
    """A copy of the cited output folder, as a re-run would write it."""
    out = tmp_path / "rerun"
    shutil.copytree(rg.CITED, out)
    return out


def _edit(folder, name, change) -> None:
    d = json.loads((folder / name).read_text(encoding="utf-8"))
    change(d)
    (folder / name).write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")


def test_a_copy_is_reproduced_and_the_run_identity_is_ignored(copy):
    assert rg.compare(rg.CITED, copy)["differences"] == []

    def identity(d):
        d.update(generated_utc="2026-10-18T00:00:00+00:00", git_commit="f" * 40,
                 git_dirty=True)

    def meta_identity(d):
        d.update(run_id="x", started_utc="y", finished_utc="z", git_commit="f" * 40,
                 git_dirty=True, sdk_versions={**d["sdk_versions"], "anthropic": "1.15.0"})

    _edit(copy, "h1h3.json", identity)
    _edit(copy, "meta.json", meta_identity)
    text = (copy / "summary.md").read_text(encoding="utf-8")
    new = re.sub(r"^Computed \S+ at commit [0-9a-f]{7} \(dirty: False\)",
                 "Computed 2026-10-18T00:00:00+00:00 at commit abcdef0 (dirty: True)", text,
                 count=1, flags=re.MULTILINE)
    assert new != text
    (copy / "summary.md").write_text(new, encoding="utf-8")
    res = rg.compare(rg.CITED, copy)
    assert res["differences"] == [] and res["per_file"] == {"h1h3.json": 0, "meta.json": 0,
                                                            "summary.md": 0}
    assert res["ignored"]["meta.json"]["sdk_versions"][1]["anthropic"] == "1.15.0"
    assert res["sha256"]["cited"]["h1h3.json"] != res["sha256"]["re-run"]["h1h3.json"]
    assert rg.report_lines(res)[-1] == "REPRODUCED: every number and label of the cited output"


def test_numbers_labels_and_key_order_are_compared(copy):
    def number(d):
        d["h1"]["delta_h1"]["estimate"] += 1e-12            # a number, bit for bit

    _edit(copy, "h1h3.json", number)
    res = rg.compare(rg.CITED, copy)
    assert len(res["differences"]) == 1
    assert res["differences"][0].startswith("h1h3.json.h1.delta_h1.estimate: ")
    shutil.copy(rg.CITED / "h1h3.json", copy / "h1h3.json")

    def order(d):
        d["h3"] = dict(reversed(list(d["h3"].items())))

    _edit(copy, "h1h3.json", order)
    (diff,) = rg.compare(rg.CITED, copy)["differences"]
    assert diff.startswith("h1h3.json.h3: keys differ") and "other order: True" in diff
    shutil.copy(rg.CITED / "h1h3.json", copy / "h1h3.json")
    text = (copy / "summary.md").read_text(encoding="utf-8")
    (copy / "summary.md").write_text(text.replace("Status: FINAL", "Status: PROVISIONAL", 1),
                                     encoding="utf-8")
    res = rg.compare(rg.CITED, copy)
    assert res["per_file"]["summary.md"] == 1 and "Status: PROVISIONAL" in res["differences"][0]
    assert rg.report_lines(res)[-1] == "DIFFERS: 1 difference(s) from the cited output"
    (copy / "summary.md").unlink()
    assert rg.compare(rg.CITED, copy)["differences"] == [f"{copy}: no summary.md"]


@pytest.mark.skipif(sys.platform != "win32", reason="the cited output's paths are Windows paths")
def test_input_paths_are_compared_as_the_files_they_name(copy):
    """The cited output was computed from another checkout than the data's, so its input paths
    are absolute; a re-run from the data's checkout spells the same folders relative to it.
    Both name the same files: no difference, and the config digest agrees once they are
    resolved. Another folder is a difference."""
    cited = json.loads((rg.CITED / "h1h3.json").read_text(encoding="utf-8"))
    root = rg._abs(cited["inputs"]["results_root"]).parent       # the data's checkout

    def relative(d):
        for k in rg.PATH_KEYS:
            d["inputs"][k] = rg._abs(d["inputs"][k]).relative_to(root).as_posix()

    def meta_relative(d):
        relative(d["config"])
        d["config_hash"] = runmeta.config_hash(d["config"])

    _edit(copy, "h1h3.json", relative)
    _edit(copy, "meta.json", meta_relative)
    text = (copy / "summary.md").read_text(encoding="utf-8")
    (copy / "summary.md").write_text(
        text.replace(f"from `{cited['inputs']['results_root']}`", "from `results`", 1),
        encoding="utf-8")
    assert rg.compare(rg.CITED, copy, root)["differences"] == []
    # resolved against another checkout they name other folders
    res = rg.compare(rg.CITED, copy, root / "elsewhere")
    assert res["per_file"] == {"h1h3.json": 3, "meta.json": 4, "summary.md": 1}
    # a hash that is not its config's digest is reported
    _edit(copy, "meta.json", lambda d: d.update(config_hash="0" * 64))
    diffs = rg.compare(rg.CITED, copy, root)["differences"]
    assert any("the re-run hash is not the digest of its own config" in x for x in diffs)


def test_rerun_args_are_the_cited_outputs_inputs(tmp_path):
    meta = json.loads((rg.CITED / "meta.json").read_text(encoding="utf-8"))
    args = rg.rerun_args(meta, tmp_path / "results", tmp_path / "raw", tmp_path / "out")
    cfg = meta["config"]
    assert args[:6] == ["--results-root", str(tmp_path / "results"), "--raw-root",
                        str(tmp_path / "raw"), "--out-dir", str(tmp_path / "out")]
    assert args[args.index("--sweep-closed") + 1] == cfg["sweep_closed"]
    assert [args[i + 1] for i, a in enumerate(args) if a == "--run"] == \
        cfg["inputs"]["input_list"]
    assert [args[i + 1] for i, a in enumerate(args) if a == "--rerun"] == \
        [f"{k}={v}" for k, v in cfg["rerun_links"].items()]
    # every other option at its registered default: no --boot, --no-bayes, --allow-incomplete
    assert not {"--boot", "--no-bayes", "--allow-incomplete", "--model"} & set(args)


def test_main_reruns_compares_and_records(tmp_path, monkeypatch, capsys):
    """The command line, with the analysis stubbed by a copy of the cited output (its real
    re-run needs luna's raw transcripts): the re-run's arguments, regression.json and
    meta.json, and the exit codes."""
    seen = {}

    def fake_main(args):
        seen["args"] = args
        out = Path(args[args.index("--out-dir") + 1])
        shutil.copytree(rg.CITED, out)
        return 0

    monkeypatch.setattr(hh, "main", fake_main)
    monkeypatch.setattr(runmeta, "git_state", lambda repo=runmeta.REPO_ROOT: dict(GIT))
    out = tmp_path / "reg"
    assert rg.main(["--out-dir", str(out), "--results-root", str(tmp_path / "r"),
                    "--raw-root", str(tmp_path / "raw")]) == 0
    assert seen["args"][:4] == ["--results-root", str((tmp_path / "r").resolve()),
                                "--raw-root", str((tmp_path / "raw").resolve())]
    reg = json.loads((out / "regression.json").read_text(encoding="utf-8"))
    assert reg["reproduced"] is True and reg["differences"] == []
    assert reg["cited"] == hh.LUNA_CITED_OUTPUT
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["experiment"] == rg.OUT_NAME and meta["exit_reason"] == "reproduced"
    assert meta["paid_calls"] == 0 and meta["cost_usd"] == 0.0
    assert meta["git_commit"] == GIT["git_commit"]
    assert meta["config"]["rerun_args"] == seen["args"]
    assert "REPRODUCED" in capsys.readouterr().out
    # --compare: an existing folder only, nothing written
    assert rg.main(["--compare", str(out / "rerun")]) == 0
    _edit(out / "rerun", "h1h3.json", lambda d: d["h3"].update(prediction_holds="changed"))
    assert rg.main(["--compare", str(out / "rerun")]) == 1
    assert "h1h3.json.h3.prediction_holds" in capsys.readouterr().out
    # the analysis refuses: nothing is compared
    monkeypatch.setattr(hh, "main", lambda args: 2)
    assert rg.main(["--out-dir", str(tmp_path / "reg2")]) == 2
    assert not (tmp_path / "reg2" / "regression.json").exists()
