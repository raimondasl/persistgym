"""G1 spot-check package (persistgym/spotcheck.py, PREREG §4.4): the 160 validity episodes
the luna validity runs used, the static review pages, the committed manifest and findings
template, and the findings check. Everything is written under pytest's temporary folders;
no test reaches the network."""

import copy
import csv
import io
import json
import re
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

from common.runmeta import REPO_ROOT, config_hash, prereg_version
from persistgym import spotcheck, tokens
from persistgym.cli import main
from persistgym.config import GENERATOR_VERSION, PRESET_HASHES, PRESETS, GeneratorConfig
from persistgym.episode import ALL_CELLS, VARIANTS, TaskCell
from persistgym.render import generate, notice_text
from persistgym.template import template_id

PKG = "g1-test"
CELL_IDS = [c.id for c in ALL_CELLS]


class NetworkBlocked(RuntimeError):
    pass


@pytest.fixture(scope="module", autouse=True)
def no_network():
    """Outbound connections and DNS lookups fail in this module, so the build is shown to
    need no network. The tokenizer is loaded first (tiktoken may download o200k_base once,
    a free public file)."""
    tokens.encoding("o200k_base")

    def refuse(*args, **kwargs):
        raise NetworkBlocked("network access in a spot-check test")

    mp = pytest.MonkeyPatch()
    for name in ("connect", "connect_ex"):
        mp.setattr(socket.socket, name, refuse)
    mp.setattr(socket, "getaddrinfo", refuse)
    mp.setattr(socket, "create_connection", refuse)
    yield
    mp.undo()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """The full package (20 templates x 8 task cells, with the audits)."""
    root = tmp_path_factory.mktemp("spotcheck")
    manifest = spotcheck.build(PKG, 20, raw_root=root / "raw", results_root=root / "results")
    return manifest, root / "raw" / PKG, root / "results" / PKG


def _flat(manifest) -> list[str]:
    return [eid for cid in CELL_IDS for eid in manifest["episode_ids_by_task_cell"][cid]]


def _validity_meta() -> list[dict]:
    return [json.loads((REPO_ROOT / run / "meta.json").read_text(encoding="utf-8"))
            for run in spotcheck.VALIDITY_RUNS]


# ---------------------------------------------------------------------------
# The episodes are those of the validity runs
# ---------------------------------------------------------------------------

def test_no_network_in_this_module():
    with pytest.raises(NetworkBlocked):
        socket.create_connection(("example.org", 443))


def test_default_config_is_the_validity_runs_config():
    """The default generator config hashes to the luna validity runs' config hash (the same
    hash function, `common.runmeta.config_hash` of `GeneratorConfig().to_dict()`)."""
    assert config_hash(GeneratorConfig().to_dict()) == spotcheck.EXPECTED_CONFIG_HASH
    for meta in _validity_meta():
        assert meta["config"]["generator_config_hashes"] == [spotcheck.EXPECTED_CONFIG_HASH]
        assert meta["config"]["generator_config"] == GeneratorConfig().to_dict()
        assert meta["seeds"]["template_seeds"] == list(range(50_000, 50_020))


def test_episode_ids_are_those_of_the_validity_runs(built):
    """160 unique ids: template ids as the generator names them (`template_id`), in every
    task cell, base variant (render.py: `<template_id>/<cell id>/<variant>`). The validity
    runs sent the restated and withheld variants of exactly these template-cell pairs."""
    manifest, _, _ = built
    ids = _flat(manifest)
    assert len(ids) == 160 == len(set(ids)) == manifest["n_episodes"]
    expected = {cid: [f"{template_id('validity', i)}/{cid}/base" for i in range(20)]
                for cid in CELL_IDS}
    assert manifest["episode_ids_by_task_cell"] == expected
    for meta in _validity_meta():
        run_ids = meta["config"]["episode_ids"]
        assert len(run_ids) == 160
        assert {e.rsplit("/", 1)[1] for e in run_ids} <= {"restated", "withheld"}
        assert {e.rsplit("/", 1)[0] for e in run_ids} == {e.rsplit("/", 1)[0] for e in ids}
    assert manifest["template_seeds"] == list(range(50_000, 50_020))
    assert manifest["indices"] == list(range(20))
    assert manifest["template_ids"] == [template_id("validity", i) for i in range(20)]


def test_base_differs_from_the_runs_renderings_as_the_index_says(built):
    """The index page says the base rendering differs from the restated one only at the need
    step (records before the question, a shorter log filler) and from the withheld one only
    in the evidence bindings (the same log filler)."""
    _, html_dir, _ = built
    index = " ".join((html_dir / "index.html").read_text(encoding="utf-8").split())
    assert "keeps a shorter log filler" in index and "stand-in bindings of equal length" in index
    for _, eps in generate("validity", range(2), GeneratorConfig(), ALL_CELLS, VARIANTS):
        by = {(e.cell.id, e.variant): e for e in eps}
        for c in ALL_CELLS:
            b, r, w = (by[(c.id, v)] for v in ("base", "restated", "withheld"))
            assert b.system_prompt == r.system_prompt == w.system_prompt
            pairs_r = list(zip(b.steps, r.steps, strict=True))
            pairs_w = list(zip(b.steps, w.steps, strict=True))
            assert [s.index for s, x in pairs_r if s.observation != x.observation] == [
                b.need_step]
            assert r.need.event.endswith(b.need.event) and len(r.need.event) > len(b.need.event)
            assert (r.need.filler_end - r.need.filler_start
                    < b.need.filler_end - b.need.filler_start)
            assert [s.index for s, x in pairs_w if s.observation != x.observation] == (
                b.reveal_steps)
            assert all(s.observation[: s.filler_end] == x.observation[: x.filler_end]
                       for s, x in pairs_w)


# ---------------------------------------------------------------------------
# Committed files
# ---------------------------------------------------------------------------

def test_manifest_fields(built):
    manifest, html_dir, pkg_dir = built
    on_disk = json.loads((pkg_dir / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk == manifest
    for key in ("git_commit", "git_dirty", "prereg_version", "generator_version",
                "config_hash", "split", "indices", "template_seeds", "variant",
                "episode_ids_by_task_cell", "html_dir", "html_index", "html_pages",
                "started_utc", "finished_utc", "findings_template", "findings_path",
                "audits", "storage_namespace"):
        assert key in manifest, key
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["git_commit"])
    assert isinstance(manifest["git_dirty"], bool)
    assert manifest["prereg_version"] == prereg_version()
    assert manifest["generator_version"] == GENERATOR_VERSION
    assert manifest["config_hash"] == spotcheck.EXPECTED_CONFIG_HASH
    assert (manifest["split"], manifest["variant"]) == ("validity", "base")
    assert Path(manifest["html_index"]) == html_dir / "index.html"
    assert set(manifest["html_pages"]) == set(CELL_IDS)
    assert manifest["findings_path"].endswith(f"{PKG}/findings.csv")
    assert manifest["html_bytes"] == sum(p.stat().st_size for p in html_dir.iterdir())
    audits = manifest["audits"]
    assert audits["pass"] is True and audits["n_episodes"] == 480
    names = {c["check"] for c in audits["checks"]}
    assert {"filler_has_no_reserved_strings", "lookup_serves_keys_and_refuses_after_cap",
            "heuristic_baselines", "partial_memory", "oracles"} <= names
    assert all(c["what"] for c in audits["checks"])
    readme = (pkg_dir / "README.md").read_text(encoding="utf-8")
    assert manifest["findings_path"] in readme and "spotcheck-findings" in readme


def test_git_keeps_the_spotcheck_csvs_byte_for_byte():
    """`.gitattributes` turns off line-end conversion for the package CSVs, so the committed
    findings template and the researcher's export keep their CRLF record ends."""
    res = subprocess.run(
        ["git", "check-attr", "text", "--", "results/spotcheck/x/findings.csv",
         "results/spotcheck/x/findings_template.csv"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    assert [line.rsplit(": ", 1)[1] for line in res.stdout.splitlines()] == ["unset", "unset"]


def test_findings_template_shape(built):
    manifest, _, pkg_dir = built
    raw = (pkg_dir / "findings_template.csv").read_bytes()
    assert raw.endswith(b"\r\n") and raw.count(b"\n") == raw.count(b"\r\n") == 161  # RFC 4180
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8"), newline="")))
    assert tuple(rows[0]) == spotcheck.FINDINGS_COLUMNS
    body = rows[1:]
    assert len(body) == 160
    assert [r[0] for r in body] == _flat(manifest)
    seeds = dict(zip(manifest["template_ids"], manifest["template_seeds"], strict=True))
    for eid, cell, seed, verdict, notes in body:
        assert cell == eid.split("/")[1] and seed == str(seeds[eid.split("/")[0]])
        assert verdict == "" and notes == ""
    assert spotcheck.read_findings(pkg_dir / "findings_template.csv", manifest)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def _pages(html_dir: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(html_dir.glob("*.html"))}


def test_pages_hold_every_episode_and_nothing_external(built):
    manifest, html_dir, _ = built
    pages = _pages(html_dir)
    assert set(pages) == {"index.html", *(f"{c}.html" for c in CELL_IDS)}
    local = {"index.html", *(f"{c}.html" for c in CELL_IDS)}
    for name, text in pages.items():
        assert "http://" not in text and "https://" not in text, name
        assert not re.search(r"(?i)\bsrc\s*=", text), name
        assert not re.search(r"(?i)(?<![a-z])url\(|@import", text), name  # CSS loads
        assert spotcheck.CSP in text
        for href in re.findall(r'href="([^"]*)"', text):
            assert href.startswith("#") or href.split("#")[0] in local, (name, href)
        assert not re.search(r"<input[^>]*\bchecked\b", text), name  # nothing pre-filled
        data = json.loads(re.search(r'<script type="application/json" id="spotcheck-data">'
                                    r"(.*?)</script>", text, re.DOTALL).group(1))
        assert [e[0] for e in data["episodes"]] == _flat(manifest)
        assert data["ns"] == f"persistgym-spotcheck/{PKG}/"
    for cid in CELL_IDS:
        text = pages[f"{cid}.html"]
        ids = re.findall(r'<article class="card" id="[^"]+" data-episode="([^"]+)"', text)
        assert ids == manifest["episode_ids_by_task_cell"][cid]
        assert text.count("✓ correct</li>") == 20
        assert text.count('class="scan ok"') == 20 and 'class="scan bad"' not in text
        assert text.count('name="v-validity-') == 20 * len(spotcheck.VERDICTS)
        assert f'href="{cid}.html"' in pages["index.html"]
    index = " ".join(pages["index.html"].split())
    assert "<strong>The pages show the answer.</strong>" in index
    assert "<strong>There is no model output here</strong>" in index
    # 20 templates are too few for the chi-square balance checks: shown as not run, not as
    # passed; every other check ran and passed
    assert "Every check that ran passed" in index and "Every check passed" not in index
    not_run = {c["check"] for c in manifest["audits"]["checks"] if not c["ran"]}
    assert not_run == {"correct_letter_balanced", "correct_rank_balanced"}
    assert index.count("not run: the chi-square test") == 2
    assert all(c["pass"] for c in manifest["audits"]["checks"])
    for name in {c["check"] for c in manifest["audits"]["checks"]}:
        assert f"<code>{name}</code>" in index


def test_skim_shows_evidence_distractor_and_need_steps(built):
    """Skim keeps the system prompt, the evidence steps, the distractor bindings and the
    need step, and hides plain routine steps (none of which holds a marked string here)."""
    _, html_dir, _ = built
    for cid in ("observed-nonrec-far", "derived-rec-near"):
        ep = _one(cid)
        text = (html_dir / f"{cid}.html").read_text(encoding="utf-8")
        card = text.split(f'data-episode="{ep.episode_id}"')[1].split("</article>")[0]
        flagged = [int(i) for i in re.findall(r'<div class="step flag" data-step="(\d+)"', card)]
        want = sorted({*ep.reveal_steps, *(d.step for d in ep.distractors), ep.need_step})
        assert flagged == want
        assert f"Skim is on: showing {len(want)} of {ep.n_steps} steps." in card


def test_summary_box_shows_the_answer(built):
    _, html_dir, _ = built
    pages = _pages(html_dir)
    ep = next(e for _, eps in generate("validity", [0], GeneratorConfig(),
                                       [TaskCell.from_id("derived-nonrec-near")]) for e in eps)
    card = pages["derived-nonrec-near.html"].split(f'data-episode="{ep.episode_id}"')[1]
    card = card.split("</article>")[0]
    clues = [c.value for c in ep.components if c.role == "clue"]
    assert " + ".join(map(str, clues)) + f" = <strong>{ep.target_value}</strong>" in card
    assert f"{ep.correct_label}) {ep.target_value} ✓ correct" in card
    assert f'<mark class="key">{ep.entity}</mark>' in card


# ---------------------------------------------------------------------------
# Scan and highlights
# ---------------------------------------------------------------------------

def _one(cell_id: str):
    return next(e for _, eps in generate("validity", [0], GeneratorConfig(),
                                         [TaskCell.from_id(cell_id)]) for e in eps)


def test_scan_allows_the_option_list_and_the_observed_binding():
    for cid in ("observed-nonrec-far", "derived-rec-near"):
        assert spotcheck.scan_episode(_one(cid)) == {"options_outside": [], "key_outside": []}


def test_scan_and_page_flag_a_leak():
    """An option value in a routine step's log filler and the target key in a routine event
    are reported by the scan, marked on the page, and the leaking filler opens by itself."""
    ep = copy.deepcopy(_one("observed-nonrec-far"))
    wrong = next(o for o in ep.options if o.label != ep.correct_label).value
    st = next(s for s in ep.steps if s.kind == "routine")
    cut = st.filler_start + 40
    st.observation = st.observation[:cut] + f" took {wrong}ms " + st.observation[cut:]
    shift = len(f" took {wrong}ms ")
    st.filler_end += shift
    st.event_start += shift
    st.event_end += shift
    st2 = next(s for s in ep.steps if s.kind == "routine" and s.index > st.index)
    st2.observation = st2.observation + f" (ask {ep.entity.lower()})"
    scan = spotcheck.scan_episode(ep)
    assert [h["match"] for h in scan["options_outside"]] == [str(wrong)]
    assert scan["options_outside"][0]["where"] == f"step {st.index} (log filler)"
    assert [h["match"] for h in scan["key_outside"]] == [ep.entity.lower()]
    assert scan["key_outside"][0]["where"] == f"step {st2.index} (event)"
    card = spotcheck.render_card(ep)
    assert 'class="scan bad"' in card and "1 option string(s) and 1 target key" in card
    step = card.split(f'data-step="{st.index}"')[1].split('data-step="')[0]
    assert '<details class="filler leak" open>' in step
    assert f'<mark class="opt">{wrong}</mark>' in step
    assert re.search(rf'<div class="step flag" data-step="{st.index}"', card)


def _insert(st, at: int, s: str) -> None:
    """Insert `s` into a step's observation at `at`, keeping the char spans right (a span
    that ends at `at` takes the inserted text)."""
    st.observation = st.observation[:at] + s + st.observation[at:]
    for name in ("filler_start", "filler_end", "event_start", "event_end"):
        if getattr(st, name) >= at:
            setattr(st, name, getattr(st, name) + len(s))


def test_scan_flags_a_repeated_binding_and_leaks_anywhere():
    """The binding repeated at a routine step, an option string in the system prompt, the
    correct value in the need step's own log filler and a clue's binding repeated in a
    derived episode are each reported, with where they are. Digits glued to an option
    string and the key inside a longer word are not."""
    ep = copy.deepcopy(_one("observed-rec-near"))
    fact = ep.components[0]
    routine = next(s for s in ep.steps if s.kind == "routine" and s.index > fact.step)
    _insert(routine, routine.event_end, " " + fact.sentence)
    ep.system_prompt += f"\nQueue {ep.options[0].value} is closed."
    need = ep.need
    _insert(need, need.filler_start + 10, f" retry={ep.target_value} ")
    _insert(need, need.filler_start + 5, f" id={ep.target_value}7 {ep.entity}S ")
    scan = spotcheck.scan_episode(ep)
    opt = [(h["where"], h["match"]) for h in scan["options_outside"]]
    assert sorted(opt) == sorted([("system prompt", str(ep.options[0].value)),
                                  (f"step {routine.index} (event)", str(ep.target_value)),
                                  (f"step {need.index} (log filler)", str(ep.target_value))])
    assert [(h["where"], h["match"]) for h in scan["key_outside"]] == [
        (f"step {routine.index} (event)", ep.entity)]
    card = spotcheck.render_card(ep)
    assert 'class="scan bad"' in card and "3 option string(s) and 1 target key" in card

    ep = copy.deepcopy(_one("derived-nonrec-far"))
    clue = next(c for c in ep.components if c.role == "clue")
    other = next(s for s in ep.steps if s.kind == "routine" and s.index > clue.step)
    _insert(other, other.event_end, " " + clue.sentence)
    scan = spotcheck.scan_episode(ep)
    assert scan["options_outside"] == []  # a clue value is never an option
    assert [(h["where"], h["match"]) for h in scan["key_outside"]] == [
        (f"step {other.index} (event)", ep.entity)]


def test_highlight_nests_key_and_option_inside_the_binding():
    ep = _one("observed-rec-near")
    m = spotcheck.Marks.of(ep)
    html_, found = spotcheck.highlight(ep.components[0].sentence, m)
    assert found == {"ev", "key", "opt"}
    assert html_.startswith('<mark class="ev">') and html_.endswith("</mark>")
    assert f'<mark class="opt correct">{ep.target_value}</mark>' in html_
    assert spotcheck.highlight("a < b & 4250ms", m)[0] == "a &lt; b &amp; 4250ms"


# ---------------------------------------------------------------------------
# Determinism, refusals and the CLI
# ---------------------------------------------------------------------------

def _files(*dirs: Path) -> dict[str, bytes]:
    return {f"{d.name}/{p.name}": p.read_bytes() for d in dirs for p in sorted(d.iterdir())}


def test_build_is_deterministic(tmp_path):
    raw, res = tmp_path / "raw", tmp_path / "results"
    kw = {"raw_root": raw, "results_root": res, "audits": False}
    m1 = spotcheck.build("det", 2, **kw)
    first = _files(raw / "det", res / "det")
    shutil.rmtree(raw)
    shutil.rmtree(res)
    m2 = spotcheck.build("det", 2, **kw)
    second = _files(raw / "det", res / "det")
    volatile = {"started_utc", "finished_utc"}
    assert {k: v for k, v in m1.items() if k not in volatile} == {
        k: v for k, v in m2.items() if k not in volatile}
    assert {k: v for k, v in first.items() if not k.endswith("manifest.json")} == {
        k: v for k, v in second.items() if not k.endswith("manifest.json")}
    # A rebuild with the package present rebuilds the pages and keeps the committed files.
    m3 = spotcheck.build("det", 2, **kw)
    assert m3["kept_committed_files"] is True
    assert _files(raw / "det", res / "det") == second
    with pytest.raises(spotcheck.SpotcheckError, match="describes other episodes"):
        spotcheck.build("det", 3, **kw)


def test_build_refuses_another_config_and_bad_ids(tmp_path):
    with pytest.raises(spotcheck.SpotcheckError, match=spotcheck.EXPECTED_CONFIG_HASH):
        spotcheck.build("x", 1, cfg=GeneratorConfig(v_tokens=400, W_tokens=6_400),
                        raw_root=tmp_path, results_root=tmp_path)
    for bad in ("../x", "a/b", "a\\b", "..", ""):
        with pytest.raises(spotcheck.SpotcheckError):
            spotcheck.check_id(bad)
    assert not any(tmp_path.iterdir())


def test_cli_spotcheck_and_findings(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(spotcheck, "RAW_ROOT", tmp_path / "raw")
    monkeypatch.setattr(spotcheck, "RESULTS_ROOT", tmp_path / "results")
    assert main(["spotcheck", "--n", "5", "--out-id", "cli"]) == 2  # D7: whole blocks
    assert "multiple of the balance block K=10" in capsys.readouterr().err
    assert not (tmp_path / "raw").exists()
    assert main(["spotcheck", "--n", "10", "--out-id", "cli"]) == 0
    out = capsys.readouterr().out
    assert "80 episodes (10 templates x 8 task cells)" in out and "pass" in out
    pkg = tmp_path / "results" / "cli"
    assert sorted(p.name for p in pkg.iterdir()) == [
        "README.md", "findings_template.csv", "manifest.json"]
    assert main(["spotcheck-findings", "--out-id", "cli"]) == 2  # no findings.csv yet
    assert "refused" in capsys.readouterr().err

    rows = list(csv.reader(io.StringIO((pkg / "findings_template.csv").read_text(
        encoding="utf-8"), newline="")))
    rows[1][3:] = ["shortcut", 'value in filler, step 7: "331"\nsee step 9']
    rows[2][3] = "no_shortcut"
    findings = pkg / "findings.csv"
    findings.write_bytes(spotcheck.findings_csv(rows[1:]).encode("utf-8"))
    assert main(["spotcheck-findings", "--out-id", "cli"]) == 1  # 78 still unreviewed
    out = capsys.readouterr().out
    assert "complete=False" in out and 'shortcut: validity-000000/observed-nonrec-near' in out
    manifest = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["command"] == "uv run python -m persistgym spotcheck --n 10 --out-id cli"
    summary = spotcheck.summarize_findings(spotcheck.read_findings(findings, manifest), manifest)
    assert summary["totals"] == {"no_shortcut": 1, "possible_shortcut": 0, "shortcut": 1,
                                 "unreviewed": 78}
    assert summary["cells"]["observed-nonrec-near"] == {
        "no_shortcut": 1, "possible_shortcut": 0, "shortcut": 1, "unreviewed": 8}
    assert summary["flagged"][0]["notes"] == 'value in filler, step 7: "331"\nsee step 9'

    for r in rows[1:]:
        r[3] = r[3] or "no_shortcut"
    findings.write_bytes(spotcheck.findings_csv(rows[1:]).encode("utf-8"))
    assert main(["spotcheck-findings", "--out-id", "cli"]) == 0
    assert "complete=True" in capsys.readouterr().out

    rows[3][3] = "maybe"
    findings.write_bytes(spotcheck.findings_csv(rows[1:]).encode("utf-8"))
    assert main(["spotcheck-findings", "--out-id", "cli"]) == 2
    assert "unknown verdict 'maybe'" in capsys.readouterr().err
    findings.write_bytes(spotcheck.findings_csv(rows[1:-1]).encode("utf-8"))
    assert main(["spotcheck-findings", "--out-id", "cli"]) == 2
    assert "1 episode(s) missing" in capsys.readouterr().err


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_page_csv_matches_python_csv(tmp_path):
    """The pages' export (spotcheck_page.js) writes the same RFC 4180 text as Python's csv
    module, and its parser reads that text back."""
    rows = [["validity-000000/observed-nonrec-near/base", "observed-nonrec-near", "50000",
             "possible_shortcut", 'comma, "quote"\nnew line\r\nand CRLF']]
    rows += [["validity-000001/derived-rec-far/base", "derived-rec-far", "50001", "", ""],
             ["validity-000002/derived-rec-far/base", "derived-rec-far", "50002", "shortcut",
              "plain ünïcode ≤"]]
    js = (Path(spotcheck.__file__).parent / "spotcheck_page.js").as_posix()
    script = ("const S = require(process.argv[1]);"
              "const rows = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
              "const text = S.toCsv(rows);"
              "process.stdout.write(JSON.stringify({text, back: S.parse(text)}));")
    res = subprocess.run(["node", "-e", script, js], input=json.dumps(rows), text=True,
                         encoding="utf-8", capture_output=True, check=True, timeout=60)
    out = json.loads(res.stdout)
    assert out["text"] == spotcheck.findings_csv(rows)
    assert out["back"] == [list(spotcheck.FINDINGS_COLUMNS), *rows]


# ---------------------------------------------------------------------------
# Generator 0.4.0: luna's package, sol's variant (PREREG §17.3)
# ---------------------------------------------------------------------------

LUNA_PKG = "g1-validity-0-20-3d6bc648"


def test_lunas_committed_manifest_is_accepted_under_0_4_0(tmp_path):
    """luna's committed manifest (generator 0.3.0, no episodes_sha256) still describes the
    episodes: a rebuild with its id keeps it, since the current episodes have its pinned
    digest; with that digest changed, or other episodes, the rebuild refuses."""
    committed = REPO_ROOT / "results" / "spotcheck" / LUNA_PKG / "manifest.json"
    old = json.loads(committed.read_text(encoding="utf-8"))
    assert old["generator_version"] == "0.3.0" and "episodes_sha256" not in old
    res = tmp_path / "results"
    (res / LUNA_PKG).mkdir(parents=True)
    shutil.copyfile(committed, res / LUNA_PKG / "manifest.json")
    kw = {"raw_root": tmp_path / "raw", "results_root": res, "audits": False}
    m = spotcheck.build(LUNA_PKG, 20, **kw)
    assert m["kept_committed_files"] is True and m["generator_version"] == "0.3.0"
    new = {**old, "episodes_sha256": spotcheck.GOLDEN_0_3_0_SPOTCHECK_SHA256}
    assert spotcheck._same_episodes(old, new)
    assert not spotcheck._same_episodes(old, {**new, "episodes_sha256": "0" * 64})
    assert not spotcheck._same_episodes({**old, "episodes_sha256": "1" * 64}, new)
    with pytest.raises(spotcheck.SpotcheckError, match="describes other episodes"):
        spotcheck.build(LUNA_PKG, 10, **kw)


def test_the_sol_chain_package(tmp_path):
    """`spotcheck --preset sol-chain`: sol's variant, pinned hash, the 4 far task cells (80
    episodes at n = 20; here n = 10), the audits on all 8 cells and 3 variants, the notice
    and the chain records allowed by the scan, and each clue's relay worked out in the
    summary box."""
    m = spotcheck.build("sol", 10, raw_root=tmp_path / "raw",
                        results_root=tmp_path / "results", preset="sol-chain")
    assert m["preset"] == "sol-chain" and m["config_hash"] == PRESET_HASHES["sol-chain"]
    assert m["task_cells"] == [c.id for c in ALL_CELLS if c.distance == "far"]
    assert m["n_episodes"] == 40 and m["validity_runs"] == []
    assert m["audits"]["pass"] is True and m["audits"]["n_episodes"] == 10 * 8 * 3
    assert len(m["episodes_sha256"]) == 64
    index = (tmp_path / "raw" / "sol" / "index.html").read_text(encoding="utf-8")
    assert "20 episodes per D11 task cell" in index and "--preset sol-chain" in index
    readme = (tmp_path / "results" / "sol" / "README.md").read_text(encoding="utf-8")
    assert "--preset sol-chain --out-id sol" in readme
    page = (tmp_path / "raw" / "sol" / "derived-rec-far.html").read_text(encoding="utf-8")
    assert page.count('class="scan ok"') == 10 and 'class="scan bad"' not in page
    assert "are not shown in the episode" in page and "Evidence notice" in page
    with pytest.raises(spotcheck.SpotcheckError, match="pinned"):
        spotcheck.build("x", 10, cfg=PRESETS["sol-chain"].replace(v_tokens=400,
                                                                 W_tokens=6_400),
                        raw_root=tmp_path, results_root=tmp_path, preset="sol-chain")
    for _, eps in generate("validity", range(2), PRESETS["sol-chain"], ALL_CELLS):
        for ep in eps:
            assert spotcheck.scan_episode(ep) == {"options_outside": [], "key_outside": []}
            # the notice names the target: outside an evidence step it is a leak
            st = next(s for s in ep.steps if s.kind == "routine")
            bad = copy.deepcopy(ep)
            bad.steps[st.index].observation += " " + notice_text(
                ep.cell.fact, ep.kind, ep.quantity, ep.entity)
            assert spotcheck.scan_episode(bad)["key_outside"]
