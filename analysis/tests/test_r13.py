"""analysis.r13 (R13's descriptive readings, PREREG §17.13) and R13's cells in
analysis.persistgym_h1h3's accounting and §2.8 replay, on fake runs.

R13's runs here are played by the harness's runner (`harnesses.runner.run_batch`) with the fake
model on real episodes of the default generator config, into a temporary results root with their
raw transcripts, as a run would write them: Σ-n-0 on templates 0-2 in all 8 task cells
(experiment 4), and W-nk-0 and W-n-0 in two rounds, templates 200-201 and 225-226, with the
registered arm order (experiment 5). The fake's replies are scripted from the request alone
(`reply`, `summary`). It copies each observation's fact sentences into its reply and keeps in
later replies the ones whose value is divisible by 3. At the need step it answers from the fact
sentences it can see (the sum of the clues for a derived fact), except that a value it sees only
in W-nk-0's pinned block is disowned when odd. Every third summary drops the facts. Chosen calls
are refused (`SIGMA_REFUSED`, `PINNED_REFUSED`): one step call in each run, and in experiment 4
one summary call, then four in a row, so one episode ends AGENT_ERROR.

The comparators (R8's, R9's, R12's and luna's runs) are read from the committed records
(`comparators_root`). Each reading is checked against a calculation here from the records and
transcripts the runner wrote, and a few on made-up records small enough to check by hand. No test
reads an outcome of R13's own runs. The last tests check that luna's and R12's arms, as this
script resolves them, give their cited outputs."""

from __future__ import annotations

import gzip
import json
import re
import shutil
import statistics
import warnings
from dataclasses import replace
from functools import cache

import numpy as np
import pytest

from analysis import haiku_notes as hn
from analysis import haiku_notes_replies as hnr
from analysis import haiku_provenance as hp
from analysis import persistgym_h1h3 as hh
from analysis import r13
from harnesses import registered
from harnesses.cells import PINNED_REPLIES_TEMPLATE, get_cell
from harnesses.config import ARC_SUMMARY_BRIDGE_TEMPLATE, HarnessConfig
from harnesses.fake import FakeModel
from harnesses.items import item_text
from harnesses.runner import run_batch
from harnesses.wire import LEADING_HARNESS_PREFIXES
from persistgym.config import PRESETS
from persistgym.episode import TaskCell
from persistgym.render import generate

ROOT = r13.REPO_ROOT
HAIKU = registered.HAIKU_MODEL
SIGMA, PINNED = r13.SIGMA, r13.PINNED
NR_FAR = registered.HAIKU_CONTROL_TASK_CELLS
ALL8 = registered.HAIKU_TASK_CELLS
CFG = HarnessConfig(model=HAIKU, reasoning_effort="medium", service_tier="standard")
SIGMA_TEMPLATES = range(3)
ROUNDS = (range(200, 202), range(225, 227))
PINNED_READ = [200, 201, 225, 226]
SIGMA_RUN = "20261120T000000Z-sigma-n-0-claude-haiku-5-5"
SIGMA_REFUSED = frozenset({"t7", "s2", "s5", "s6", "s7", "s8"})
"""Experiment 4's refused calls: step call 7, summary call 2 (retried), and summary calls 5 to
8, four failed attempts in a row in one episode, which then ends AGENT_ERROR."""
PINNED_REFUSED = frozenset({"t3"})


# --- the fake model: replies scripted from the request ------------------------------------------

FACT = re.compile(r"For [a-z]+ [A-Z]+, the [a-z ]+ is (\d+)\.")
OPTION = re.compile(r"^([A-J])\) (\d+)$", re.MULTILINE)
NEED = re.compile(r"Reply (\w+)\(<letter>\)")
DISOWN_REPLY = "The figure I noted for it earlier was made up, so I cannot verify it."
NONE_REPLY = "No figure for it is in view.\nACTION: ack(none)"


def known(text: str) -> set[int]:
    """The values of the fact sentences in `text`, and their sums of two or three."""
    vals = sorted({int(v) for v in FACT.findall(text)})
    sums = {a + b for i, a in enumerate(vals) for b in vals[i + 1:]}
    sums |= {a + b + c for i, a in enumerate(vals) for j, b in enumerate(vals[i + 1:], i + 1)
             for c in vals[j + 1:]}
    return set(vals) | sums


def reply(payload: dict, i: int) -> str:
    msgs = payload["messages"]
    lead = item_text(msgs[0]) if hh.is_pinned_block(msgs[0]) else ""
    body = msgs[1 if lead else 0:-1]
    rest = "\n".join(item_text(m) for m in body)
    mine = "\n".join(item_text(m) for m in body if m["role"] == "assistant") + "\n" + lead
    last = item_text(msgs[-1])
    m = NEED.search(last)
    if m is None:
        now = [x.group(0) for x in FACT.finditer(last)]
        kept = [x.group(0) for x in FACT.finditer(mine) if int(x.group(1)) % 3 == 0]
        notes = list(dict.fromkeys(now + kept))
        return ("Notes: " + " ".join(notes) + "\n" if notes else "") + "ACTION: ack(none)"
    options = [(lab, int(v)) for lab, v in OPTION.findall(last)]
    elsewhere, pinned = known(rest), known(lead)
    for lab, v in options:
        if v in elsewhere:
            return f"ACTION: {m.group(1)}({lab})"
    for lab, v in options:
        if v in pinned:
            return DISOWN_REPLY if v % 2 else f"ACTION: {m.group(1)}({lab})"
    return NONE_REPLY


def summary(payload: dict, j: int) -> str:
    text = "\n".join(item_text(m) for m in payload["messages"])
    facts = [x.group(0) for x in FACT.finditer(text)] if j % 3 else []
    return f"SUMMARY s{j}: " + (" ".join(dict.fromkeys(facts)) or "routine log traffic only.")


def fake(refused: frozenset, category: str = "general_harms") -> FakeModel:
    return FakeModel(reply, summary_fn=summary, refusal_category=category,
                     status_fn=lambda p, tag: "refusal" if tag in refused else "completed")


@cache
def episodes(templates: tuple[int, ...], task_cells: tuple[str, ...]) -> list:
    return [e for _, es in generate("main", templates, PRESETS["default"],
                                    [TaskCell.from_id(c) for c in task_cells], ("base",))
            for e in es]


def play(root, experiment, cell, templates, task_cells, refused, run_id, category="general_harms"):
    run_batch(episodes(tuple(templates), tuple(task_cells)), get_cell(cell), CFG,
              fake(refused, category), experiment=experiment, run_id=run_id,
              results_root=root / "results", raw_root=root / "results" / "raw")


@pytest.fixture(scope="module")
def played(tmp_path_factory):
    """A results root with the draw and R13's fake runs."""
    root = tmp_path_factory.mktemp("played")
    shutil.copytree(ROOT / "results" / "draw", root / "results" / "draw")
    play(root, SIGMA, "Σ-n-0", SIGMA_TEMPLATES, ALL8, SIGMA_REFUSED, SIGMA_RUN)
    n = 0
    for k, ts in enumerate(ROUNDS):
        for cell in registered.r13_round_arms(k):
            n += 1
            play(root, PINNED, cell, ts, NR_FAR, PINNED_REFUSED,
                 f"20261121T00000{n}Z-{get_cell(cell).ascii_id}-claude-haiku-5-5", "cyber")
    return root


@pytest.fixture
def root(played, tmp_path):
    shutil.copytree(played, tmp_path / "root")
    return tmp_path / "root"


def _read(root, closed=frozenset(r13.EXPERIMENTS), **kw):
    kw.setdefault("comparators_root", ROOT)
    return r13.readings(root, {}, closed, **kw)


def _seed() -> int:
    return hh.read_seed(ROOT / "results")[0] + hh.BOOT_SEED_OFFSET


def at_t(s: np.ndarray, templates) -> np.ndarray:
    """Experiment 4's arrays: R8 to R12's T = 200 positions, by template number, NaN where a
    template is not read."""
    out = np.full(registered.HAIKU_T, np.nan)
    out[list(templates)] = s
    return out


def _arm(x: dict, name: str) -> dict:
    return next(a for a in x["arms"] if a["arm"] == name)


def _cell(arm: dict, tc: str) -> dict:
    return next(c for c in arm["cells"] if c["task_cell"] == tc)


def _runs(root, experiment):
    return sorted(p for p in (root / "results" / experiment).iterdir() if p.is_dir())


def records(root, experiment, cell=None) -> dict[str, dict]:
    """The episodes.jsonl records the runner wrote, by episode id (of one cell's runs)."""
    out = {}
    for folder in _runs(root, experiment):
        for line in (folder / "episodes.jsonl").read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if cell is None or rec["harness_cell"] == cell:
                out[rec["episode_id"]] = rec
    return out


def lines(root, experiment, run_id) -> list[dict]:
    path = root / "results" / "raw" / experiment / run_id / "transcript.jsonl.gz"
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def _template(rec: dict) -> int:
    return hh.template_index(rec["template_id"])


def success(recs: dict[str, dict], tc: str, templates) -> np.ndarray:
    by = {_template(r): float(bool(r["need_correct"])) for r in recs.values()
          if r["task_cell"] == tc}
    return np.array([by[t] for t in templates])


@cache
def committed(arm: str) -> dict[tuple[int, str], dict]:
    """A comparator's counted repeat-0 base records, by (template, task cell), read here from its
    committed resolution."""
    if arm in ("W-0", "F-0"):
        resolved = hn.r8_counted(ROOT)[1]
    elif arm == "W-n-0 (R9)":
        resolved = hp.r9_read(ROOT)[1]
    elif arm == "W-b-0":
        resolved = r13.r12_counted(ROOT, registered.R12_BLOCK_EXPERIMENT)[1]
    elif arm == "luna":
        resolved = r13.luna_arm(ROOT).resolved
    else:
        resolved = r13.r12_counted(ROOT, registered.R12_NOTES_EXPERIMENT)[1]
    cell = {"W-n-0 (R9)": "W-n-0", "luna": "Σ-n-0"}.get(arm, arm)
    return {(_template(r.record), r.record["task_cell"]): r.record for r in resolved.values()
            if r.status == "counted" and r.record is not None and r.key[0] == cell
            and r.key[2] == 0 and (r.record.get("variant") or "base") == "base"}


def committed_success(arm: str, tc: str, templates) -> np.ndarray:
    return np.array([float(bool(committed(arm)[(t, tc)]["need_correct"])) for t in templates])


def _edit(root, experiment, run_id, change):
    path = root / "results" / experiment / run_id / "episodes.jsonl"
    recs = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    for rec in recs:
        change(rec)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs),
                    encoding="utf-8")


# --- R13's registered readings -----------------------------------------------------------------

def test_the_experiments_are_r13s():
    assert r13.EXPERIMENTS == (SIGMA, PINNED)
    assert (r13.templates_of(SIGMA), r13.templates_of(PINNED)) == (range(200), range(200, 300))
    assert r13.CONTRASTS[SIGMA] == (("Σ-n-0", "W-0 (R8)"), ("Σ-n-0", "F-0 (R8)"),
                                    ("Σ-n-0", "W-b-0 (R12)"))
    assert r13.CONTRASTS[PINNED] == (("W-nk-0", "W-n-0"),)
    assert r13.R9_CONTRAST == ("Σ-n-0", "W-n-0 (R9)")
    assert (r13.BOOT, r13.BOOT_SEED_OFFSET, r13.ROUND) == (10_000, 10, 25)
    assert r13.BOOT_SEED_OFFSET == hh.BOOT_SEED_OFFSET
    assert r13.R12_OUTPUT == "results/r12/20261113T065503Z"


def test_experiment_4_indexes_by_template_number_and_experiment_5_maps_to_0_n_minus_1():
    assert r13.positions(PINNED, [205, 200, 201]) == ({200: 0, 201: 1, 205: 2}, 3)
    assert r13.positions(SIGMA, [0, 7, 199]) == ({0: 0, 7: 7, 199: 199}, registered.HAIKU_T)


def test_with_no_r13_run_it_names_both_experiments_and_writes_nothing(tmp_path, capsys):
    root = tmp_path / "root"
    shutil.copytree(ROOT / "results" / "draw", root / "results" / "draw")
    for allow in (False, True):
        with pytest.raises(hh.Refusal, match="nothing is written") as e:
            r13.readings(root, {}, allow_incomplete=allow, comparators_root=ROOT)
        assert f"Experiment 4 ({SIGMA}): no run under results/{SIGMA}/" in str(e.value)
        assert f"Experiment 5 ({PINNED}): no run under results/{PINNED}/" in str(e.value)
    with pytest.raises(hh.Refusal) as e:
        r13.readings(root, {}, experiments=(PINNED,), comparators_root=ROOT)
    assert "Experiment 5" in str(e.value) and "Experiment 4" not in str(e.value)
    out = tmp_path / "out"
    assert r13.main(["--results-root", str(root), "--allow-incomplete",
                     "--out-dir", str(out)]) == 2
    assert not out.exists()
    err = capsys.readouterr().err
    assert "Experiment 4" in err and "Experiment 5" in err and "has no run to read yet" in err


# --- experiment 4: Σ-n-0 ---------------------------------------------------------------------

def test_experiment_4_reads_sigma_and_its_comparators_on_the_same_templates(root):
    r = _read(root)
    assert r["status"] == "FINAL" and r["incomplete"] == []
    assert r["bootstrap"]["seed"] == _seed() and r["bootstrap"]["seed_offset"] == 10
    assert r["bootstrap"]["seed"] == hh.read_seed(ROOT / "results")[0] + hh.BOOT_SEED_OFFSET
    x = r["experiments"][SIGMA]
    assert (x["templates_read"], x["templates"], x["resamples_over"]) == (
        3, "0-2", registered.HAIKU_T)
    assert [a["arm"] for a in x["arms"]] == ["Σ-n-0", "W-0 (R8)", "F-0 (R8)", "W-b-0 (R12)"]
    mine = records(root, SIGMA)
    for tc in ALL8:
        c = _cell(_arm(x, "Σ-n-0"), tc)
        assert (c["successes"], c["n"]) == (int(success(mine, tc, SIGMA_TEMPLATES).sum()), 3)
        for name, src in (("W-0 (R8)", "W-0"), ("F-0 (R8)", "F-0"), ("W-b-0 (R12)", "W-b-0")):
            c = _cell(_arm(x, name), tc)
            assert (c["successes"], c["n"]) == (
                int(committed_success(src, tc, SIGMA_TEMPLATES).sum()), 3)
    assert x["comparators"]["r8_runs"] == [
        "20261018T141157Z-F-0-claude-haiku-5-5", "20261018T144829Z-W-0-claude-haiku-5-5",
        "20261018T154817Z-W-0-claude-haiku-5-5", "20261018T154918Z-W-0-claude-haiku-5-5"]
    assert x["comparators"]["r12_runs"] == [
        "20261112T235047Z-W-b-0-claude-haiku-5-5", "20261113T011523Z-W-b-0-claude-haiku-5-5",
        "20261113T023608Z-W-b-0-claude-haiku-5-5", "20261113T035847Z-W-b-0-claude-haiku-5-5"]
    assert x["accounting_check"] == {"checked": 0, "bugs": [], "missing_transcripts": []}


def test_experiment_4_intervals_and_contrasts_by_a_calculation_here(root):
    """SEED + 10, 10,000 resamples over R8 to R12's T = 200 positions, by template number, with
    the 3 templates read at positions 0-2 and the rest left out of each mean (NaN); the same
    resamples for every arm."""
    x = _read(root)["experiments"][SIGMA]
    idx = hh.resample_indices(registered.HAIKU_T, _seed(), 10_000)
    mine = records(root, SIGMA)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # resamples that hold no template read
        for tc in ALL8:
            s = at_t(success(mine, tc, SIGMA_TEMPLATES), SIGMA_TEMPLATES)
            means = np.nanmean(s[idx], axis=1)
            assert _cell(_arm(x, "Σ-n-0"), tc)["interval_90"] == pytest.approx(
                [np.nanpercentile(means, 5), np.nanpercentile(means, 95)])
            for name, src in (("W-0 (R8)", "W-0"), ("F-0 (R8)", "F-0"),
                              ("W-b-0 (R12)", "W-b-0")):
                b = at_t(committed_success(src, tc, SIGMA_TEMPLATES), SIGMA_TEMPLATES)
                v = x["contrasts"][f"Σ-n-0 - {name}"][tc]
                d = 100 * (np.nanmean(s[idx], axis=1) - np.nanmean(b[idx], axis=1))
                assert v["pp"] == pytest.approx(100 * (np.nanmean(s) - np.nanmean(b)))
                assert v["ci90"] == pytest.approx([np.nanpercentile(d, 5),
                                                   np.nanpercentile(d, 95)])
    assert set(x["contrasts"]) == {"Σ-n-0 - W-0 (R8)", "Σ-n-0 - F-0 (R8)",
                                   "Σ-n-0 - W-b-0 (R12)", "Σ-n-0 - W-n-0 (R9)"}


def test_the_r9_contrast_is_on_the_not_recoverable_far_cells_with_the_same_resamples(root):
    x = _read(root)["experiments"][SIGMA]
    v = x["contrasts"]["Σ-n-0 - W-n-0 (R9)"]
    assert set(v) == set(NR_FAR)
    assert (x["r9_contrast"]["templates"], x["r9_contrast"]["left_out"]) == ("0-2", [])
    assert x["r9_contrast"]["runs"] == ["20261024T060051Z-W-n-0-claude-haiku-5-5"]
    idx = hh.resample_indices(registered.HAIKU_T, _seed(), 10_000)
    mine = records(root, SIGMA)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # resamples that hold no template read
        for tc in NR_FAR:
            s = at_t(success(mine, tc, SIGMA_TEMPLATES), SIGMA_TEMPLATES)
            b = at_t(committed_success("W-n-0 (R9)", tc, SIGMA_TEMPLATES), SIGMA_TEMPLATES)
            d = 100 * (np.nanmean(s[idx], axis=1) - np.nanmean(b[idx], axis=1))
            assert v[tc]["pp"] == pytest.approx(100 * (np.nanmean(s) - np.nanmean(b)))
            assert v[tc]["ci90"] == pytest.approx([np.nanpercentile(d, 5),
                                                   np.nanpercentile(d, 95)])


def test_a_contrast_on_the_templates_both_finished_leaves_the_rest_out_of_both_sides():
    """Position 0 is the only one both sides hold: every resample that draws it gives 100 pp, and
    the others give no difference at all (NaN, left out)."""
    a, b = np.array([1.0, 0.0, np.nan]), np.array([0.0, np.nan, 1.0])
    idx = hh.resample_indices(3, 7, 2_000)
    with np.errstate(all="ignore"), pytest.warns(RuntimeWarning):
        v = r13.contrast_both(a, b, idx)
    assert v == {"pp": 100.0, "ci90": [100.0, 100.0]}


def test_side_read_names_the_keys_that_leave_a_template_read_out():
    def res(t, tc, status, rec=True):
        key = r13.r12._key("W-n-0", t, tc)
        return key, hh.Resolved(key, status, {"x": 1} if rec else None, "run",
                                None if status == "counted" else "made up")
    resolved = dict([res(0, NR_FAR[0], "counted"), res(0, NR_FAR[1], "counted"),
                     res(1, NR_FAR[0], "counted"), res(1, NR_FAR[1], "excluded", False),
                     res(2, NR_FAR[1], "counted")])
    arm = r13.r12.Arm("W-n-0 (R9)", "W-n-0", HAIKU, "e", resolved, [])
    keep, rows = r13.side_read(arm, [0, 1, 2], NR_FAR)
    assert keep == [0]
    assert [(r["template"], r["task_cell"], r["status"]) for r in rows] == [
        (1, NR_FAR[1], "excluded"), (2, NR_FAR[0], "no record")]
    assert rows[0]["reason"] == "made up" and rows[0]["arm"] == "W-n-0 (R9)"


def test_a_hole_in_sigma_leaves_the_template_out_of_every_arm_and_names_it(root):
    def exclude(rec):
        if (rec["template_id"], rec["task_cell"]) == ("main-000001", "derived-rec-far"):
            rec.update(excluded=True, exclusion_reason="made up")
    _edit(root, SIGMA, SIGMA_RUN, exclude)
    r = _read(root)
    x = r["experiments"][SIGMA]
    assert (x["templates_read"], x["templates"], x["resamples_over"]) == (
        2, "0, 2", registered.HAIKU_T)
    (row,) = x["left_out"]
    assert (row["template"], row["arm"], row["task_cell"], row["status"]) == (
        1, "Σ-n-0", "derived-rec-far", "excluded")
    assert "made up" in row["reason"]
    assert all(c["n"] == 2 for a in x["arms"] for c in a["cells"])
    idx = hh.resample_indices(registered.HAIKU_T, _seed(), 10_000)  # by template number
    s = at_t(success(records(root, SIGMA), NR_FAR[0], [0, 2]), [0, 2])
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # resamples that hold no template read
        means = np.nanmean(s[idx], axis=1)
        want = [np.nanpercentile(means, 5), np.nanpercentile(means, 95)]
    assert _cell(_arm(x, "Σ-n-0"), NR_FAR[0])["interval_90"] == pytest.approx(want)
    assert "template 1, Σ-n-0, derived-rec-far: excluded" in r13.summary(r)
    assert sum(e["excluded_by_runner"] for e in x["exclusions"]) == 1


def _lost(recs):
    return [r for r in recs if (r.get("need_payload") or {}).get("S") is False]


def test_sigma_reads_the_bridge_as_carried_text(root):
    """Reading 3: the bridge and the retained replies apart, and either, which is §2.8's
    S_carried as persistgym_h1h3 reads it for Σ-n-0 on the Messages wire."""
    x = _read(root)["experiments"][SIGMA]
    sig = _arm(x, "Σ-n-0")
    mine = records(root, SIGMA)
    acc = {row["task_cell"]: row for row in sig["accounting"]}
    total = 0
    for tc in ALL8:
        recs = [r for r in mine.values() if r["task_cell"] == tc and r["need_payload"]]
        lost = _lost(recs)
        bridge = [r for r in lost if (r.get("need_bridge_carried") or {}).get("carried")]
        kept = [r for r in lost if r["need_payload"]["assistant_carried"]["carried"]]
        either = [r for r in lost if r in bridge or r in kept]
        c = sig["carried"][tc]
        assert c["S_verbatim_0"] == len(lost) == acc[tc]["S_verbatim_0"]
        assert c["bridge"]["carried"] == len(bridge) and c["retained"]["carried"] == len(kept)
        assert c["either"]["carried"] == len(either) == acc[tc]["P_carried"]["carried"]
        assert c["either"]["success_given_carried"] == acc[tc]["used_given_carried"]
        assert c["bridge"]["success_given_carried"]["successes"] == sum(
            r["need_correct"] for r in bridge)
        assert c["bridge"]["present_at_need"] == sum(r.get("need_bridge_carried") is not None
                                                     for r in lost)
        assert "pinned" not in c
        total += len(bridge)
    assert total > 0                                  # the fake's summaries carry some facts
    # the episode table reads the bridge on the Messages wire, and compacted_between
    resolved = hh.resolve(r13.discover(root, SIGMA), {}, echo=False)[0]
    table, _ = hh.episode_table(resolved, api=hh.MESSAGES_API)
    for row in table.itertuples():
        rec = mine[row.episode_id]
        want = rec.get("compacted_between")
        assert (np.isnan(row.compacted_between) if want is None
                else row.compacted_between == want)
        if (rec.get("need_payload") or {}).get("S") is False:
            assert row.s_carried == int(bool(
                (rec.get("need_bridge_carried") or {}).get("carried")
                or rec["need_payload"]["assistant_carried"]["carried"]))


def test_compaction_and_compacted_between_per_task_cell(root):
    x = _read(root)["experiments"][SIGMA]
    mine = records(root, SIGMA)
    for tc in ALL8:
        recs = [r for r in mine.values() if r["task_cell"] == tc]
        c = x["compaction"][tc]
        assert c["episodes"] == 3
        assert c["compactions_per_episode"] == pytest.approx(
            np.mean([len(r["compactions"]) for r in recs]))
        groups = {}
        for r in recs:
            k = "none" if r.get("compacted_between") is None else str(r["compacted_between"])
            groups.setdefault(k, []).append(r)
        assert {k: (v["n"], v["success"]["successes"])
                for k, v in c["compacted_between"].items()} == {
            k: (len(v), sum(r["need_correct"] for r in v)) for k, v in groups.items()}
    near = _arm(x, "Σ-n-0")["near_need_payload_S_false"]
    assert set(near) == {tc for tc in ALL8 if tc.endswith("-near")}
    for tc, v in near.items():
        recs = [r for r in mine.values() if r["task_cell"] == tc]
        assert (v["n"], v["S_false"]) == (3, len(_lost(recs)))


def test_near_cells_whose_evidence_was_not_in_the_request():
    recs = [{"task_cell": "observed-nonrec-near", "need_payload": {"S": False},
             "need_correct": True},
            {"task_cell": "observed-nonrec-near", "need_payload": {"S": False},
             "need_correct": False},
            {"task_cell": "observed-nonrec-near", "need_payload": {"S": True}, "need_correct": True},
            {"task_cell": "observed-nonrec-far", "need_payload": {"S": False}}]
    assert r13.near_s_false(recs) == {"observed-nonrec-near": {
        "n": 3, "S_false": 2, "success_given_S_false": {"n": 2, "successes": 1, "rate": 0.5}}}


def test_summary_calls_from_the_records_and_transcripts(root):
    x = _read(root)["experiments"][SIGMA]
    mine = records(root, SIGMA)
    s = x["summary_calls"]["all"]
    assert s["episodes"] == 24
    assert s["summary_requests_per_episode"] == pytest.approx(
        np.mean([r["n_summary_requests"] for r in mine.values()]))
    assert s["failed_attempts"] == 5                 # summary calls 2 and 5 to 8
    assert s["summary_stopped"] == s["summary_refusals"] == {"refusal:general_harms": 5}
    (agent_error,) = s["agent_error_episodes"]
    rec = mine[agent_error]
    assert rec["exit_reason"] == "AGENT_ERROR" and rec["n_summary_failures"] == 4
    tc = rec["task_cell"]
    assert x["summary_calls"][tc]["agent_error_episodes"] == [agent_error]
    assert _cell(_arm(x, "Σ-n-0"), tc)["n"] == 3     # counted, and scored 0
    assert s["summary_responses"] == sum(r["n_summary_requests"] for r in mine.values())
    bridges = [c["bridge_tokens"] for r in mine.values() for c in r["compactions"]]
    assert s["bridges"] == len(bridges)
    assert s["bridge_tokens_median"] == statistics.median(bridges)
    calls = [d for d in lines(root, SIGMA, SIGMA_RUN) if d["kind"] == "summary"]
    tokens = [d["response"]["usage"]["output_tokens"] for d in calls]
    assert s["summary_output_tokens_median_per_call"] == statistics.median(tokens)
    assert s["summary_output_tokens_mean_per_episode"] == pytest.approx(sum(tokens) / 24)
    assert s["summary_with_thinking"] == len(calls)   # every fake response holds one


def test_summary_transcript_on_a_made_up_transcript(tmp_path):
    def resp(stop, text="S", category=None, out=7, thinking=True):
        content = ([{"type": "thinking", "thinking": ""}] if thinking else []) + (
            [{"type": "text", "text": text}] if text is not None else [])
        return {"content": content, "stop_reason": stop,
                "stop_details": {"category": category} if category else None,
                "usage": {"input_tokens": 1, "output_tokens": out}}
    path = tmp_path / "t.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for kind, eid, r in (("summary", "e", resp("end_turn", out=10)),
                             ("summary", "e", resp("refusal", category="bio", out=3)),
                             ("summary", "e", resp("end_turn", text="  ", out=1)),
                             ("summary", "e", resp("max_tokens", text=None, out=32000,
                                                   thinking=False)),
                             ("step", "e", resp("end_turn", out=99)),
                             ("summary", "other", resp("end_turn"))):
            f.write(json.dumps({"episode_id": eid, "kind": kind, "response": r}) + "\n")
    got = r13.summary_transcript(path, {"e": {}})
    assert got["e"]["calls"] == 4 and got["e"]["output_tokens"] == [10, 3, 1, 32000]
    assert dict(got["e"]["stopped"]) == {"refusal:bio": 1, "empty": 1, "max_output_tokens": 1}
    assert got["e"]["thinking"] == 3


def test_sigma_responses_read_step_and_summary_calls_apart(root):
    x = _read(root)["experiments"][SIGMA]
    s = _arm(x, "Σ-n-0")["responses"]
    mine = records(root, SIGMA)
    n_summary = sum(r["n_summary_requests"] for r in mine.values())
    steps = sum(r["n_requests"] for r in mine.values()) - n_summary
    assert (s["step_responses"], s["summary_responses"]) == (steps, n_summary)
    assert (s["step_responses_in_transcript"], s["summary_responses_in_transcript"]) == (
        steps, n_summary)
    assert (s["refused_responses"], s["refusal_categories"]) == (1, {"refusal:general_harms": 1})
    assert s["refused_share"] == pytest.approx(1 / steps)
    assert s["with_thinking"] == steps and s["summary_with_thinking"] == n_summary
    assert "responses" not in _arm(x, "W-0 (R8)")    # comparators: records only
    c = _arm(x, "Σ-n-0")["costs"]["all"]
    assert c["n"] == 24 and c["cost_usd_billed_mean"] == pytest.approx(
        np.mean([r["cost_usd_billed_est"] for r in mine.values()]))
    assert c["cache_read_share"] == pytest.approx(
        sum(r["usage"]["cached_input_tokens"] for r in mine.values())
        / sum(r["usage"]["input_tokens"] for r in mine.values()))


def test_a_transcript_that_disagrees_with_the_records_refuses(root):
    path = root / "results" / "raw" / SIGMA / SIGMA_RUN / "transcript.jsonl.gz"
    kept = [d for d in lines(root, SIGMA, SIGMA_RUN)]
    first = next(i for i, d in enumerate(kept) if d["kind"] == "summary")
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for d in kept[:first] + kept[first + 1:]:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    with pytest.raises(hh.Refusal, match="summary responses, its records"):
        _read(root)


def test_luna_is_set_beside_on_the_same_task_cells_and_templates(root):
    r = _read(root)
    b = r["experiments"][SIGMA]["beside_luna"]
    assert (b["arm"], b["model"], b["templates"], b["left_out"]) == (
        "Σ-n-0 (luna)", registered.LUNA_MODEL, "0-2", [])
    for c in b["cells"]:
        recs = [committed("luna")[(t, c["task_cell"])] for t in SIGMA_TEMPLATES]
        assert (c["successes"], c["n"]) == (sum(x["need_correct"] for x in recs), 3)
        lost = _lost(recs)
        assert b["carried"][c["task_cell"]]["bridge"]["carried"] == sum(
            bool((x.get("need_bridge_carried") or {}).get("carried")) for x in lost)
    assert set(b["compacted_between"]) == set(ALL8)
    assert "contrast" not in json.dumps(b)
    text = r13.summary(r)
    assert text.index(r13.NOTE_LUNA) > text.index("**8. Beside luna's Σ-n-0**")


# --- experiment 5: W-nk-0 and W-n-0 ------------------------------------------------------------

def test_experiment_5_reads_both_arms_with_their_contrast(root):
    r = _read(root)
    x = r["experiments"][PINNED]
    assert (x["templates_read"], x["templates"], x["resamples_over"]) == (
        4, "200-201, 225-226", 4)
    assert [a["arm"] for a in x["arms"]] == ["W-nk-0", "W-n-0"]
    assert x["accounting_check"] == {"checked": 16, "bugs": [], "missing_transcripts": []}
    idx = hh.resample_indices(4, _seed(), 10_000)
    s = {c: records(root, PINNED, c) for c in ("W-nk-0", "W-n-0")}
    for tc in NR_FAR:
        a, b = success(s["W-nk-0"], tc, PINNED_READ), success(s["W-n-0"], tc, PINNED_READ)
        assert _cell(_arm(x, "W-nk-0"), tc)["successes"] == a.sum()
        assert _cell(_arm(x, "W-n-0"), tc)["successes"] == b.sum()
        means = a[idx].mean(axis=1)
        assert _cell(_arm(x, "W-nk-0"), tc)["interval_90"] == pytest.approx(
            [np.percentile(means, 5), np.percentile(means, 95)])
        v = x["contrasts"]["W-nk-0 - W-n-0"][tc]
        d = 100 * (a[idx].mean(axis=1) - b[idx].mean(axis=1))
        assert v["pp"] == pytest.approx(100 * (a.mean() - b.mean()))
        assert v["ci90"] == pytest.approx([np.percentile(d, 5), np.percentile(d, 95)])
    assert list(x["contrasts"]) == ["W-nk-0 - W-n-0"]
    # after the last template played (226), 73 were never played, and every key of templates
    # 202-224 before it is named as left out
    assert x["templates_never_played"] == 73
    assert {(row["template"], row["status"]) for row in x["left_out"]} == {
        (t, "no record") for t in range(202, 225)}


def test_a_hole_in_w_n_0_leaves_the_template_out_of_both_arms(root):
    run = next(p.name for p in _runs(root, PINNED) if "-W-n-0-" in p.name)
    _edit(root, PINNED, run, lambda rec: rec.update(excluded=True, exclusion_reason="made up")
          if (rec["template_id"], rec["task_cell"]) == ("main-000200", NR_FAR[0]) else None)
    x = _read(root)["experiments"][PINNED]
    assert (x["templates_read"], x["templates"]) == (3, "201, 225-226")
    assert ({(r["template"], r["arm"], r["status"]) for r in x["left_out"]
             if r["template"] == 200} == {(200, "W-n-0", "excluded")})
    assert all(c["n"] == 3 for a in x["arms"] for c in a["cells"])


def test_experiment_5_reads_the_pinned_block_and_the_retained_replies_apart(root):
    x = _read(root)["experiments"][PINNED]
    for cell in ("W-nk-0", "W-n-0"):
        arm = _arm(x, cell)
        acc = {row["task_cell"]: row for row in arm["accounting"]}
        mine = records(root, PINNED, cell)
        for tc in NR_FAR:
            lost = _lost([r for r in mine.values() if r["task_cell"] == tc])
            assert len(lost) == 4                           # far: never in the window
            kept = [r for r in lost if r["need_payload"]["assistant_carried"]["carried"]]
            pinned = [r for r in lost if (r.get("need_pinned_carried") or {}).get("carried")]
            c = arm["carried"][tc]
            assert c["retained"]["carried"] == len(kept)
            assert c["either"]["carried"] == len({r["episode_id"] for r in kept + pinned})
            assert c["either"]["carried"] == acc[tc]["P_carried"]["carried"]
            assert c["either"]["success_given_carried"] == acc[tc]["used_given_carried"]
            if cell == "W-nk-0":
                assert c["pinned"]["carried"] == len(pinned) > 0
                assert c["pinned"]["success_given_carried"]["successes"] == sum(
                    r["need_correct"] for r in pinned)
                assert c["pinned"]["present_at_need"] == sum(
                    r.get("need_pinned_carried") is not None for r in lost)
            else:
                assert "pinned" not in c and not pinned
    assert sum(_arm(x, "W-n-0")["carried"][tc]["retained"]["carried"] for tc in NR_FAR) > 0


def test_the_block_at_the_need_step_from_the_records(root):
    x = _read(root)["experiments"][PINNED]
    mine = records(root, PINNED, "W-nk-0")
    assert "block_at_need" not in _arm(x, "W-n-0")
    for tc in NR_FAR:
        infos = [r["need_info"] for r in mine.values() if r["task_cell"] == tc]
        block = [i for i in infos if i["pinned_index"] == 0]
        c = _arm(x, "W-nk-0")["block_at_need"][tc]
        assert (c["reached_need"], c["with_block"]) == (4, len(block)) and block
        assert c["block_tokens_median"] == statistics.median(i["pinned_tokens"] for i in block)
        assert c["block_replies_median"] == statistics.median(len(i["pinned_turns"])
                                                              for i in block)
        assert c["newest_reply_over_cap"] == sum(i["pinned_over_cap"] for i in block)
        assert c["replies_left_out"] == sum(i["pinned_left_out"] for i in block)


def test_block_at_need_on_made_up_records():
    def rec(index, tokens=0, turns=(), over=False, left=0):
        return {"need_info": {"pinned_index": index, "pinned_tokens": tokens,
                              "pinned_turns": list(turns), "pinned_over_cap": over,
                              "pinned_left_out": left}}
    recs = [rec(0, 100, (1, 2, 3)), rec(0, 700, (4,), over=True, left=2), rec(None),
            {"need_info": None}, rec(0, 300, (5, 6), left=1)]
    assert r13.block_at_need({"tc": recs}) == {"tc": {
        "episodes": 5, "reached_need": 4, "with_block": 3, "block_tokens_median": 300.0,
        "block_replies_median": 2.0, "newest_reply_over_cap": 1, "replies_left_out": 3,
        "left_out_median": 1.0, "episodes_with_replies_left_out": 2}}


def _need_reply(root, experiment, rec) -> str:
    step = hnr.need_step(rec)
    for folder in _runs(root, experiment):
        for d in lines(root, experiment, folder.name):
            if (d["episode_id"], d["kind"], d["pending_step"]) == (rec["episode_id"], "step",
                                                                   step) \
                    and d["harness_cell"] == rec["harness_cell"]:
                return hnr.reply_text(d["response"])
    raise AssertionError(rec["episode_id"])


def test_declines_read_r10s_pattern_on_the_transcripts(root):
    x = _read(root)["experiments"][PINNED]
    for cell in ("W-nk-0", "W-n-0"):
        d = _arm(x, cell)["declines"]
        mine = records(root, PINNED, cell)
        for tc in NR_FAR:
            recs = [r for r in mine.values() if r["task_cell"] == tc]
            failed = [r for r in recs if hh._carried(cell, r) and not r["need_correct"]]
            hit = [r for r in failed if r["need_label"] is None
                   or hnr.DISOWN.search(_need_reply(root, PINNED, r))]
            c = d["by_task_cell"][tc]
            assert (c["episodes"], c["failed_carried"], c["declined_or_disowns"]) == (
                4, len(failed), len(hit))
            assert c["declined"] == sum(r["need_label"] is None for r in failed)
            assert sorted(c["declined_or_disowns_ids"]) == sorted(r["episode_id"] for r in hit)
        both = d["by_task_cell"]["both"]
        assert both["failed_carried"] == sum(d["by_task_cell"][tc]["failed_carried"]
                                             for tc in NR_FAR)
        assert set(d["tally"]) == {f"{tc} carried={c}" for tc in NR_FAR for c in (True, False)}
    # the fake disowns the odd values it sees only in the block
    assert _arm(x, "W-nk-0")["declines"]["by_task_cell"]["both"]["disowns"] > 0


def test_experiment_5_responses_and_retained_replies(root):
    x = _read(root)["experiments"][PINNED]
    for cell in ("W-nk-0", "W-n-0"):
        s = _arm(x, cell)["responses"]
        mine = records(root, PINNED, cell)
        assert s["step_responses"] == sum(r["n_requests"] for r in mine.values())
        assert s["summary_responses"] == 0 and s["summary_responses_in_transcript"] == 0
        assert (s["refused_responses"], s["refusal_categories"]) == (2, {"refusal:cyber": 2})
        for tc in NR_FAR:
            # the retained replies are the assistant messages of the need step's first request:
            # the pinned block is a user message and is not among them
            lengths = []
            for rec in (r for r in mine.values() if r["task_cell"] == tc):
                step = hnr.need_step(rec)
                d = next(d for f in _runs(root, PINNED) for d in lines(root, PINNED, f.name)
                         if d["episode_id"] == rec["episode_id"] and d["pending_step"] == step
                         and d["harness_cell"] == cell)
                lengths += [len(item_text(m)) for m in d["payload"]["messages"]
                            if m["role"] == "assistant"]
            assert s["at_need"][tc]["reply_chars_median"] == statistics.median(lengths)
            assert s["at_need"][tc]["retained_replies_pooled"] == len(lengths)


def test_rounds_and_run_times(root):
    r = _read(root)
    x = r["experiments"][PINNED]
    rows = x["rounds"]["success"]
    assert len(rows) == 4 * 2 * 3
    assert [r["templates_read"] for r in rows if r["arm"] == "W-nk-0" and r["task_cell"] == "all"
            ] == [2, 2, 0, 0]
    # the arm that started a round is read from the runs: rounds 3 and 4 have none
    pooled = [r for r in rows if r["arm"] == "W-n-0" and r["task_cell"] == "all"]
    assert [r["first_arm"] for r in pooled] == ["W-nk-0", "W-n-0", None, None]
    assert [r["registered_first_arm"] for r in pooled] == ["W-nk-0", "W-n-0", "W-nk-0", "W-n-0"]
    assert not any("round" in w and "started with" in w for w in r["warnings"])
    for cell in ("W-nk-0", "W-n-0"):
        mine = records(root, PINNED, cell)
        pooled = [r for r in rows if r["arm"] == cell and r["task_cell"] == "all"]
        for k, ts in enumerate(ROUNDS):
            want = [r for r in mine.values() if _template(r) in ts]
            assert (pooled[k]["n"], pooled[k]["successes"]) == (
                len(want), sum(r["need_correct"] for r in want))
    runs = x["rounds"]["runs"]
    assert [r["arm"] for r in runs] == ["W-nk-0", "W-n-0", "W-n-0", "W-nk-0"]
    assert [r["templates"] for r in runs] == ["200-201", "200-201", "225-226", "225-226"]
    assert all(r["started_utc"] <= r["finished_utc"] for r in runs)


def test_a_round_played_out_of_the_registered_order_is_read_from_the_runs(root):
    """Round 1's W-n-0 run is made to start first: the reading says so, beside the registered
    order, and warns. Round 2 keeps its order."""
    (wn,) = [f for f in _runs(root, PINNED) if "-W-n-0-" in f.name
             and "main-000200" in (f / "episodes.jsonl").read_text(encoding="utf-8")]
    meta = json.loads((wn / "meta.json").read_text(encoding="utf-8"))
    meta["started_utc"] = "2026-01-01T00:00:00+00:00"            # before every other run
    (wn / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    r = _read(root)
    rows = [x for x in r["experiments"][PINNED]["rounds"]["success"] if x["task_cell"] == "all"
            and x["arm"] == "W-nk-0"]
    assert [x["first_arm"] for x in rows[:2]] == ["W-n-0", "W-n-0"]
    assert [x["registered_first_arm"] for x in rows[:2]] == ["W-nk-0", "W-n-0"]
    (w,) = [w for w in r["warnings"] if "started with" in w]
    assert w.startswith("Experiment 5: round 1 (200-224) started with W-n-0")
    assert "registered order has W-nk-0 first" in w
    assert r13.summary(r).count(f"warning: {w}") == 1


def test_r12_experiment_1_is_set_beside_on_the_same_templates(root):
    r = _read(root)
    b = r["experiments"][PINNED]["beside_r12"]
    assert [x["arm"] for x in b] == ["W-n-0 (R12)", "W-np-0 (R12)", "W-nd-0 (R12)",
                                     "W-nx-0 (R12)"]
    for x in b:
        assert (x["templates"], x["n_templates"], x["left_out"]) == ("200-201, 225-226", 4, [])
        for c in x["cells"]:
            want = committed_success(x["arm"].split()[0], c["task_cell"], PINNED_READ)
            assert (c["successes"], c["n"]) == (int(want.sum()), 4)
    assert "contrast" not in json.dumps(b)
    text = r13.summary(r)
    assert text.index(r13.NOTE_R12) > text.index("**9. Beside R12 experiment 1's arms**")


# --- §2.8's replay with the pinned block ---------------------------------------------------------

def test_the_replay_takes_the_pinned_block_off_and_checks_w_nk_0_as_w_n_0(root, monkeypatch):
    runs = r13.discover(root, PINNED)
    raw = root / "results" / "raw"
    check = hh.accounting_check(runs, raw, PINNED, hh.MESSAGES_API)
    assert (check["checked"], check["bugs"], check["warnings"]) == (16, [], [])
    # left in, the block is one more user message than the replay expects, in every W-nk-0
    # episode whose need request holds it, and S and the window start still agree
    monkeypatch.setitem(hh.SPECS, "W-nk-0", replace(hh.SPECS["W-nk-0"], pinned_tokens=0))
    left_in = hh.accounting_check(runs, raw, PINNED, hh.MESSAGES_API)
    assert left_in["bugs"] == []
    pinned_runs = {r.run_id for r in runs if r.cell == "W-nk-0"}
    assert {w.split(":")[0] for w in left_in["warnings"]} == pinned_runs
    assert all("the need payload's user messages differ from the replay's count" in w
               for w in left_in["warnings"])


def test_window_recheck_with_and_without_the_pinned_block(root):
    run = next(r for r in r13.discover(root, PINNED) if r.cell == "W-nk-0")
    path = root / "results" / "raw" / PINNED / run.run_id / "transcript.jsonl.gz"
    wanted = {rec["episode_id"]: {"need_step": hh.need_step_of(rec),
                                  "evidence_steps": rec["designed"]["evidence_steps"]}
              for rec in run.records}
    kw = {"notes": True, "settings": run.window, "api": hh.MESSAGES_API}
    off = hh.window_recheck(path, wanted, pinned=True, **kw)
    on = hh.window_recheck(path, wanted, **kw)
    for rec in run.records:
        a, b = off[rec["episode_id"]], on[rec["episode_id"]]
        assert (a["S"], a["keep"]) == (b["S"], b["keep"]) == (
            rec["need_payload"]["S"], rec["need_info"]["keep_start"])
        assert a["user_messages_sent"] == a["user_messages_expected"]
        block = rec["need_info"]["pinned_index"] == 0
        assert b["user_messages_sent"] == a["user_messages_sent"] + block


def test_only_a_pinned_block_is_taken_off():
    def user(text):
        return {"role": "user", "content": [{"type": "text", "text": text}]}
    assert hh.PINNED_PREFIX == LEADING_HARNESS_PREFIXES[1]
    assert hh.is_pinned_block(user(PINNED_REPLIES_TEMPLATE.format(replies="R")))
    assert not hh.is_pinned_block(user(ARC_SUMMARY_BRIDGE_TEMPLATE.format(summary="S")))
    assert not hh.is_pinned_block(user("=== console update 10:30:08 ==="))
    assert not hh.is_pinned_block({"role": "assistant", "content": [
        {"type": "text", "text": PINNED_REPLIES_TEMPLATE.format(replies="R")}]})


def test_a_far_w_nk_0_episode_with_its_fact_in_the_window_is_a_bug():
    rec = {"episode_id": "e", "task_cell": "observed-nonrec-far", "need_payload": {"S": True}}
    run = hh.Run(run_id="r", folder=ROOT, cell="W-nk-0", variants=("base",), repeat_index=0,
                 started=None, exit_reason="COMPLETED", model_returned=[HAIKU], records=[rec],
                 window={})
    assert hh.far_window_bugs([run])


def test_the_cell_lists_gain_w_nk_0_only():
    assert hh.WINDOW_CELLS == ("W-0", "W-n-0", "W-np-0", "W-npd-0", "W-nd-0", "W-nx-0", "W-b-0",
                               "W-nk-0")
    assert hh.CARRY_CELLS == ("W-n-0", "Σ-n-0", "W-np-0", "W-npd-0", "W-nd-0", "W-nx-0",
                              "W-nk-0")
    assert hh.SUMMARY_CELLS == ("Σ-n-0",) and hh.PINNED_CELLS == ("W-nk-0",)
    assert hh.s_planned("W-nk-0", "near") == 1 and hh.s_planned("W-nk-0", "far") == 0
    lost = {"need_payload": {"S": False, "assistant_carried": {"carried": False}},
            "need_pinned_carried": {"carried": True}, "need_bridge_carried": {"carried": True}}
    assert hh._carried("W-nk-0", lost) is True
    assert hh._carried("W-n-0", lost) is False        # no block in W-n-0, no bridge outside Σ
    assert hh._carried("Σ-n-0", lost) is True
    assert hh._carried("W-0", lost) is None


def test_carried_on_made_up_records():
    def rec(S, kept, pinned, correct):
        return {"need_payload": {"S": S, "assistant_carried": {"carried": kept}},
                "need_pinned_carried": None if pinned is None else {"carried": pinned},
                "need_correct": correct}
    recs = [rec(False, True, False, True), rec(False, False, True, False),
            rec(False, False, None, False), rec(True, True, True, True)]
    c = r13.carried(recs, "W-nk-0")
    assert (c["n"], c["S_verbatim_0"]) == (4, 3)
    assert c["retained"] == {"carried": 1, "rate": 1 / 3,
                             "success_given_carried": {"n": 1, "successes": 1, "rate": 1.0}}
    assert c["pinned"] == {"carried": 1, "rate": 1 / 3, "present_at_need": 2,
                           "success_given_carried": {"n": 1, "successes": 0, "rate": 0.0}}
    assert c["either"] == {"carried": 2, "rate": 2 / 3,
                           "success_given_carried": {"n": 2, "successes": 1, "rate": 0.5}}
    assert r13.carried(recs, "W-0") is None
    assert set(r13.carried(recs, "W-n-0")) == {"n", "S_verbatim_0", "retained", "either"}


# --- refusals and incomplete sweeps --------------------------------------------------------------

def test_a_record_off_the_registered_task_cells_refuses(root):
    play(root, PINNED, "W-nk-0", [200], ("observed-nonrec-near",), frozenset(), "x-near")
    with pytest.raises(hh.Refusal, match="plays observed-nonrec-far, derived-nonrec-far only"):
        _read(root)


def test_a_record_off_the_registered_templates_refuses(root):
    _edit(root, SIGMA, SIGMA_RUN, lambda rec: rec.update(template_id="main-000200")
          if rec["template_id"] == "main-000002" else None)
    with pytest.raises(hh.Refusal, match="main templates 0-199 only"):
        _read(root)


def test_a_sigma_run_of_another_model_refuses(root):
    """Σ-n-0 is luna's cell too: a run of it in R13's folder counts only on Haiku."""
    src = root / "results" / SIGMA / SIGMA_RUN
    dst = root / "results" / SIGMA / "luna-copy"
    shutil.copytree(src, dst)
    meta = json.loads((dst / "meta.json").read_text(encoding="utf-8"))
    meta.update(run_id="luna-copy", model_requested=registered.LUNA_MODEL)
    (dst / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(hh.Refusal, match="not R13's runs of it"):
        _read(root)


def test_a_short_sweep_needs_the_researchers_close(root):
    with pytest.raises(hh.Refusal, match="1576 of 1600 repeat-0 episodes have no record"):
        _read(root, closed=frozenset())
    r = _read(root, closed=frozenset(), allow_incomplete=True)
    assert r["status"] == "PROVISIONAL"
    assert any("have no record" in z for z in r["incomplete"])
    closed = _read(root)
    assert any("never played" in d for d in closed["experiments"][SIGMA]["deviations"])


def test_a_missing_transcript_is_provisional_and_names_the_readings(root):
    shutil.rmtree(root / "results" / "raw" / PINNED)
    with pytest.raises(hh.Refusal, match="§2.8's replay cannot be made"):
        _read(root)
    r = _read(root, allow_incomplete=True)
    assert r["status"] == "PROVISIONAL"
    x = r["experiments"][PINNED]
    assert all(a["responses"] is None and a["declines"] is None for a in x["arms"])
    assert any("reading 5 cannot be made" in z for z in r["incomplete"])
    assert any("reading 7 cannot be made" in z for z in r["incomplete"])
    assert "(no transcripts)" in r13.summary(r)


def test_one_experiment_alone(root):
    shutil.rmtree(root / "results" / PINNED)
    with pytest.raises(hh.Refusal, match=f"no run under results/{PINNED}/"):
        _read(root, closed=frozenset({SIGMA}))
    r = _read(root, closed=frozenset({SIGMA}), allow_incomplete=True)
    assert r["status"] == "PROVISIONAL" and r["experiments"][PINNED] is None
    assert "Not read: no run." in r13.summary(r)
    alone = _read(root, closed=frozenset({SIGMA}), experiments=(SIGMA,))
    assert alone["status"] == "FINAL" and set(alone["experiments"]) == {SIGMA}
    assert "Not part of this reading" in r13.summary(alone)
    with pytest.raises(hh.Refusal, match="leaves out"):
        _read(root, closed=frozenset({PINNED}), experiments=(SIGMA,))
    with pytest.raises(hh.Refusal, match="names no R13 experiment"):
        _read(root, closed=frozenset({"persistgym_haiku"}))


def test_a_bug_in_the_replay_stops_the_analysis_even_as_provisional(root, monkeypatch):
    monkeypatch.setattr(hh, "accounting_check", lambda *a, **k: {
        "checked": 1, "bugs": ["made up"], "missing_transcripts": [], "warnings": []})
    with pytest.raises(hh.AccountingBug, match="made up"):
        _read(root, allow_incomplete=True)


# --- the output ----------------------------------------------------------------------------------

def test_the_summary_names_every_reading_and_the_caveats(root):
    r = _read(root)
    text = r13.summary(r)
    for needle in ("**FINAL.**", "Exploratory: no test", "Not a model comparison",
                   "seed SEED + 10", "## What it does not show",
                   "## Experiment 4: claude-haiku-5-5", "## Experiment 5: claude-haiku-5-5",
                   "**1. Success:**", "**2. Contrasts**", "**3. §2.8 accounting in the bridge**",
                   "**4. Compaction and near cells:**", "**5. Summary calls**",
                   "**6. Choices", "**7. Responses:**", "**8. Beside luna's Σ-n-0**",
                   "**3. §2.8 accounting** (each source apart", "**4. The block at the need step",
                   "**5. Declines**", "**8. Rounds**", "**9. Beside R12 experiment 1's arms**",
                   "Σ-n-0 - W-n-0 (R9), derived-nonrec-far", "W-nk-0 - W-n-0, observed-nonrec-far"):
        assert needle in text, needle
    assert r["does_not_show"] == list(r13.DOES_NOT_SHOW)
    for x in r13.DOES_NOT_SHOW:
        assert x in text
    for needle in (r13.NOTE_NOT_CONCURRENT, r13.NOTE_LABEL, r13.NOTE_LOWER_BOUND, r13.NOTE_LUNA,
                   r13.NOTE_R12, r13.NOTE_PATTERN):
        assert needle in text, needle
    assert text.index(r13.NOTE_NOT_CONCURRENT) < text.index("## Experiment 5")
    assert text.index(r13.NOTE_LABEL) > text.index("## Experiment 5")
    assert text.index(r13.NOTE_PATTERN) > text.index("**5. Declines**")


def test_main_writes_its_three_files_with_their_metadata(root, tmp_path, capsys):
    out = tmp_path / "out"
    args = ["--results-root", str(root), "--comparators-root", str(ROOT)]
    assert r13.main([*args, "--sweep-closed", "sigma", "--sweep-closed", "pinned",
                     "--out-dir", str(out)]) == 0
    assert {p.name for p in out.iterdir()} == set(r13.OUTPUTS)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["paid_calls"] == 0 and meta["config"]["status"] == "FINAL"
    assert {"git_commit", "git_dirty", "prereg_version"} <= set(meta)
    assert meta["seeds"] == {"bootstrap": _seed()}
    inputs = meta["config"]["inputs"]
    assert inputs["runs"][SIGMA] == [SIGMA_RUN] and len(inputs["runs"][PINNED]) == 4
    assert inputs["comparators"]["r12_output"] == r13.R12_OUTPUT
    readings = json.loads((out / "readings.json").read_text(encoding="utf-8"))
    assert readings["experiments_in_reading"] == [SIGMA, PINNED]
    again = tmp_path / "again"
    assert r13.main([*args, "--out-dir", str(again)]) == 2        # the sweeps are not closed
    assert not again.exists()
    assert r13.main([*args, "--sweep-closed", "sigma", "--sweep-closed", "pinned",
                     "--no-write", "--out-dir", str(again)]) == 0
    assert not again.exists()
    assert "# R13:" in capsys.readouterr().out


# --- the comparators, as their cited outputs counted them ----------------------------------------

def _json(x):
    return json.loads(json.dumps(hh._clean(x), default=hh._json_default))


def _templates(ranges: str) -> list[int]:
    """The templates of an output's ``templates`` field ("0-199", "201, 225-226")."""
    out: list[int] = []
    for part in ranges.split(", "):
        lo, _, hi = part.partition("-")
        out += range(int(lo), int(hi or lo) + 1)
    return out


def test_lunas_sigma_is_its_cited_output():
    """luna's Σ-n-0 as `luna_arm` resolves it and `beside` reads it, on main templates 0-199,
    equals the Σ-n-0 rows of luna's cited output: success, §2.8's accounting and
    compacted_between per task cell."""
    h = json.loads((ROOT / hh.LUNA_CITED_OUTPUT / "h1h3.json").read_text(encoding="utf-8"))
    assert h["templates"] == 200
    b = r13.beside(r13.luna_arm(ROOT), list(range(200)), ALL8, 200, hh.RESPONSES_API)
    assert (b["templates"], b["n_templates"], b["left_out"]) == ("0-199", 200, [])
    want = {c["task_cell"]: c for c in h["cells"]
            if (c["kind"], c["variant"]) == ("Σ-n-0", "base")}
    assert {c["task_cell"]: (c["n"], c["successes"]) for c in _json(b["cells"])} == {
        tc: (c["n"], c["successes"]) for tc, c in want.items()}
    acc = {x["task_cell"]: x for x in h["accounting"] if x["cell"] == "Σ-n-0"}
    assert set(acc) == set(ALL8)
    for x in _json(b["accounting"]):
        w = acc[x["task_cell"]]
        assert x == {k: w[k] for k in x}, x["task_cell"]
        assert _json(b["compacted_between"])[x["task_cell"]] == w["by_compacted_between"]


R12_CITED = [(registered.R12_BLOCK_EXPERIMENT, "W-b-0"),
             *((registered.R12_NOTES_EXPERIMENT, c) for c in r13.R12_NOTES_CELLS)]


@pytest.mark.parametrize(("experiment", "cell"), R12_CITED)
def test_r12s_arms_are_its_cited_output(experiment, cell):
    """R12's W-b-0 and experiment 1's four arms, as `r12_arm` resolves them and `beside` reads
    them on the templates R12's cited output read, equal that output's arm cells and §2.8
    accounting."""
    x = json.loads((ROOT / r13.R12_OUTPUT / "readings.json").read_text(
        encoding="utf-8"))["experiments"][experiment]
    read = _templates(x["templates"])
    assert len(read) == x["templates_read"]
    task_cells = tuple(x["task_cells"])
    b = r13.beside(r13.r12_arm(ROOT, experiment, cell), read, task_cells, read[-1] + 1,
                   hh.MESSAGES_API)
    assert (b["templates"], b["n_templates"], b["left_out"]) == (x["templates"], len(read), [])
    want = next(a for a in x["arms"] if a["arm"] == cell)
    assert [(c["task_cell"], c["n"], c["successes"]) for c in _json(b["cells"])] == [
        (c["task_cell"], c["n"], c["successes"]) for c in want["cells"]]
    got = _json(b["accounting"])
    assert [g["task_cell"] for g in got] == [w["task_cell"] for w in want["accounting"]]
    for g, w in zip(got, want["accounting"], strict=True):
        assert g == {k: w[k] for k in g}, (cell, g["task_cell"])
