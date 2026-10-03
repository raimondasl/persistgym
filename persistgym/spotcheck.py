"""G1 spot-check package (PREREG §4.4): the researcher reviews generated validity episodes for
shortcuts, without model output.

    uv run python -m persistgym spotcheck                 # validity templates 0-19, 8 task cells
    uv run python -m persistgym spotcheck --n 20 --out-id g1-validity-0-20-3d6bc648
    uv run python -m persistgym spotcheck-findings --out-id g1-validity-0-20-3d6bc648

`spotcheck` renders the base variant of validity templates 0..n-1 (seeds 50000..) in all 8
task cells with the default generator config, which must be the config of the luna validity
runs (`EXPECTED_CONFIG_HASH`), so the researcher reviews the templates those runs used. It
re-runs the $0 audits on these templates (base, restated and withheld) and writes:

* results/raw/spotcheck/<id>/ (gitignored, large, regenerable): index.html and one page per
  task cell, static HTML with inline CSS and JS and nothing loaded from elsewhere;
* results/spotcheck/<id>/ (committed): manifest.json, findings_template.csv and README.md.
  If manifest.json already exists it must describe the same episodes; the committed files are
  then kept as they are and only the pages are rebuilt.

The pages show the answer and the evidence of each episode, so the reviewer can judge what
else gives the answer away; they never suggest a verdict. Findings are kept in the browser
and exported as findings.csv, which `spotcheck-findings` checks against the manifest and
counts per task cell for the G1 report. No API calls; nothing here costs money.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import itertools
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

from common.runmeta import REPO_ROOT, config_hash, git_state, prereg_version, utc_now
from persistgym.config import GENERATOR_VERSION, SCHEMA_VERSION, SEED_RANGES, GeneratorConfig
from persistgym.episode import ALL_CELLS, VARIANTS, Episode, versionless_json
from persistgym.render import EVENT_PREFIX, generate
from persistgym.template import sample_template
from persistgym.validity import (
    heuristic_baselines,
    lookup_audit,
    oracle_scores,
    partial_memory_from_episodes,
    shortcut_audit,
)

EXPECTED_CONFIG_HASH = "3d6bc648eaa9b9e843fe6e70060495cd197630b0f2d585e66b3cd280b7a3968b"
"""`generator_config_hashes` of the luna validity runs (`VALIDITY_RUNS`): the default
`GeneratorConfig()` of generator 0.3.0, hashed by `common.runmeta.config_hash`."""
VALIDITY_RUNS = (
    "results/persistgym_validity/20261002T084243Z-F-0-gpt-6-luna",
    "results/persistgym_validity/20261002T095135Z-F-0-gpt-6-luna",
)
GOLDEN_0_3_0_SPOTCHECK_SHA256 = "7d79178592c214e795c489412d6ec963e7112587468f7be57aa65931677fa9dc"
"""`episodes_sha256` of the committed package `g1-validity-0-20-3d6bc648`'s 160 base episodes
(validity templates 0-19 x 8 task cells, default config), taken with generator 0.3.0 before
any change of generator 0.4.0. Its manifest predates `episodes_sha256`, so a rebuild matches
it only while the current episodes still have this digest."""
SPLIT = "validity"
VARIANT = "base"
DEFAULT_N = 20
RAW_ROOT = REPO_ROOT / "results" / "raw" / "spotcheck"
RESULTS_ROOT = REPO_ROOT / "results" / "spotcheck"
FINDINGS_COLUMNS = ("episode_id", "task_cell", "template_seed", "verdict", "notes")
VERDICTS = {"no_shortcut": "No shortcut", "possible_shortcut": "Possible shortcut",
            "shortcut": "Shortcut"}
CSP = ("default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
       "base-uri 'none'; form-action 'none'")
"""The pages may run only their own inline style and script and load nothing."""
_ASSETS = Path(__file__).resolve().parent
OPTION_LINE = re.compile(r"^[A-Z]\) \d+$", re.MULTILINE)


class SpotcheckError(RuntimeError):
    pass


def episodes_sha256(eps: list[Episode]) -> str:
    """sha256 over the episodes, in order, as canonical JSON lines without
    `generator_version` (`episode.versionless_json`)."""
    h = hashlib.sha256()
    for ep in eps:
        h.update(versionless_json(ep).encode("utf-8") + b"\n")
    return h.hexdigest()


def default_id(n: int, chash: str) -> str:
    return f"g1-{SPLIT}-0-{n}-{chash[:8]}"


def check_id(out_id: str) -> str:
    if (not out_id or out_id in (".", "..") or ".." in out_id
            or not re.fullmatch(r"[A-Za-z0-9._-]+", out_id)):
        raise SpotcheckError(f"--out-id must be a plain folder name (letters, digits, '.', '_' "
                             f"and '-'), got {out_id!r}")
    return out_id


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def cell_label(cell_id: str) -> str:
    fact, rec, dist = cell_id.split("-")
    return (f"{fact} fact · {'recoverable (lookup offered)' if rec == 'rec' else 'not recoverable'}"
            f" · {dist}")


# ---------------------------------------------------------------------------
# What the reviewer's highlights and the scan look for
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Marks:
    """Per episode: the binding sentences to mark (evidence and distractor bindings) and one
    regex for the target key (a whole word, any case) and the option strings (whole numbers:
    not part of a longer digit run), the same matching rules as the audits."""

    bindings: tuple[tuple[str, str], ...]  # (sentence, "ev" | "dist")
    inner: re.Pattern
    correct: str

    @classmethod
    def of(cls, ep: Episode) -> Marks:
        bindings = tuple([(c.sentence, "ev") for c in ep.components]
                         + [(d.sentence, "dist") for d in ep.distractors])
        opts = "|".join(str(o.value) for o in ep.options)
        inner = re.compile(rf"(?P<key>(?<![A-Za-z]){re.escape(ep.entity)}(?![A-Za-z]))"
                           rf"|(?P<opt>(?<![0-9])(?:{opts})(?![0-9]))", re.IGNORECASE)
        return cls(bindings, inner, str(ep.target_value))


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def _attr(s: str) -> str:
    return html.escape(s, quote=True)


def _find_all(text: str, sub: str) -> list[tuple[int, int]]:
    spans, i = [], text.find(sub)
    while i >= 0:
        spans.append((i, i + len(sub)))
        i = text.find(sub, i + 1)
    return spans


def binding_spans(text: str, m: Marks) -> list[tuple[int, int, str]]:
    """Non-overlapping (start, end, class) of every binding sentence in `text`."""
    spans = [(a, b, cls) for sent, cls in m.bindings for a, b in _find_all(text, sent)]
    out, pos = [], 0
    for a, b, cls in sorted(spans):
        if a >= pos:
            out.append((a, b, cls))
            pos = b
    return out


def _inner_html(s: str, m: Marks, found: set[str]) -> str:
    parts, pos = [], 0
    for mt in m.inner.finditer(s):
        if mt.lastgroup == "key":
            cls = "key"
        else:
            cls = "opt correct" if mt.group() == m.correct else "opt"
        found.add(cls.split()[0])
        parts += [_esc(s[pos:mt.start()]), f'<mark class="{cls}">{_esc(mt.group())}</mark>']
        pos = mt.end()
    parts.append(_esc(s[pos:]))
    return "".join(parts)


def highlight(text: str, m: Marks) -> tuple[str, set[str]]:
    """HTML of `text` with the bindings, the target key and the option strings marked, and
    the set of mark classes used ("ev", "dist", "key", "opt")."""
    found: set[str] = set()
    out, pos = [], 0
    for a, b, cls in binding_spans(text, m):
        out.append(_inner_html(text[pos:a], m, found))
        out.append(f'<mark class="{cls}">{_inner_html(text[a:b], m, found)}</mark>')
        found.add(cls)
        pos = b
    out.append(_inner_html(text[pos:], m, found))
    return "".join(out), found


def _context(text: str, a: int, b: int, width: int = 32) -> str:
    left = text[max(0, a - width):a].replace("\n", " ⏎ ")
    right = text[b:b + width].replace("\n", " ⏎ ")
    return f"…{left}[{text[a:b]}]{right}…"


def scan_episode(ep: Episode, m: Marks | None = None) -> dict:
    """Where an option string or the target key occurs in the episode text (system prompt and
    every observation) outside the places it belongs. Option strings belong in the need
    step's option list and, for an observed fact, in its binding at the step that reveals
    it; the key belongs in the evidence bindings at the steps that reveal them (a rule in the
    system prompt binds no entity) and in the need question. So a binding repeated at
    another step is reported too. Both lists should be empty."""
    m = m or Marks.of(ep)
    out: dict[str, list[dict]] = {"options_outside": [], "key_outside": []}
    texts = [("system prompt", ep.system_prompt, None)] + [
        (f"step {s.index}", s.observation, s) for s in ep.steps]
    for where, text, st in texts:
        here = [c for c in ep.components if c.step == (None if st is None else st.index)]
        allowed_opt = [(a, b) for c in here if c.role == "fact"
                       for a, b in _find_all(text, c.sentence)]
        allowed_key = [(a, b) for c in here for a, b in _find_all(text, c.sentence)]
        if st is not None and st.kind == "need":
            allowed_opt += [(x.start(), x.end()) for x in OPTION_LINE.finditer(text)
                            if x.start() >= st.event_start]
            question = st.event.split("\n", 1)[0]
            allowed_key += [(st.event_start, st.event_start + len(question))]
        for mt in m.inner.finditer(text):
            a, b = mt.start(), mt.end()
            allowed = allowed_key if mt.lastgroup == "key" else allowed_opt
            if any(x <= a and b <= y for x, y in allowed):
                continue
            region = ""
            if st is not None:
                region = (" (header)" if a < st.filler_start else
                          " (log filler)" if a < st.filler_end else
                          " (event)" if a >= st.event_start else " (end of log)")
            out["key_outside" if mt.lastgroup == "key" else "options_outside"].append(
                {"where": where + region, "match": mt.group(), "context": _context(text, a, b)})
    return out


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def _asset(name: str) -> str:
    return (_ASSETS / name).read_text(encoding="utf-8")


def _json_for_script(data) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _page(title: str, bar: str, body: str, data: dict) -> str:
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<meta http-equiv=\"Content-Security-Policy\" content=\"{CSP}\">\n"
        "<meta name=\"robots\" content=\"noindex\">\n"
        f"<title>{_esc(title)}</title>\n<style>\n{_asset('spotcheck_page.css')}</style>\n"
        f"</head>\n<body>\n<header class=\"bar\"><div class=\"bar-row\">{bar}</div></header>\n"
        f"<main>\n{body}\n</main>\n"
        f"<script type=\"application/json\" id=\"spotcheck-data\">{_json_for_script(data)}"
        f"</script>\n<script>\n{_asset('spotcheck_page.js')}</script>\n</body>\n</html>\n")


LEGEND = (
    '<ul class="legend" aria-label="Legend">'
    '<li><mark class="ev">evidence binding</mark> (fact, clue or rule)</li>'
    '<li><mark class="key">TARGET KEY</mark> (the entity asked about)</li>'
    '<li><mark class="opt">option string</mark>, '
    '<mark class="opt correct">correct option</mark></li>'
    '<li><mark class="dist">distractor binding</mark> (never needed)</li>'
    "</ul>")

STORAGE_WARNING = (
    '<div class="notice warn" id="storage-warning" hidden>This browser is not saving findings '
    "for this page (its storage is blocked or full). Verdicts and notes stay only until the "
    "page is closed: export the CSV before closing it, or open the folder through a local "
    "server (README.md).</div>")


def _ordinal(k: int) -> str:
    suffix = "th" if 10 <= k % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(k % 10, "th")
    return f"{k}{suffix}"


def _summary(ep: Episode, m: Marks) -> str:
    """The answer box: target key, value (or clues, rule and derived value), the options with
    the correct one marked, and where the evidence, the need step and the distractors are."""
    n = ep.need_step
    rows: dict[str, str] = {}
    rows["Target key"] = (f'<mark class="key">{_esc(ep.entity)}</mark> (a {_esc(ep.kind)}); '
                          f"quantity asked: {_esc(ep.quantity)}")
    if ep.cell.fact == "observed":
        c = ep.components[0]
        rows["True value"] = (f"<strong>{ep.target_value}</strong>, shown once at step {c.step}: "
                              f"{highlight(c.sentence, m)[0]}")
    else:
        clues = [c for c in ep.components if c.role == "clue"]
        rule = next(c for c in ep.components if c.role == "rule")
        rows["Clues"] = "; ".join(
            f"{_esc(c.name)} = <strong>{c.value}</strong> (step {c.step})" for c in clues)
        where = f"step {rule.step}" if rule.step is not None else "system prompt"
        rows["Rule"] = f"{highlight(rule.sentence, m)[0]} ({where})"
        total = sum(c.value for c in clues)
        check = ("" if total == ep.target_value else
                 f' <span class="fail">does not equal the target {ep.target_value}</span>')
        rows["Derived value"] = (" + ".join(str(c.value) for c in clues)
                                 + f" = <strong>{total}</strong>{check}")
    chips = "".join(
        f'<li class="correct">{o.label}) {o.value} ✓ correct</li>' if o.label == ep.correct_label
        else f"<li>{o.label}) {o.value}</li>" for o in ep.options)
    vals = sorted(o.value for o in ep.options)
    rank = vals.index(ep.target_value) + 1
    spacing = {b - a for a, b in itertools.pairwise(vals)}
    shape = "consecutive" if spacing == {1} else f"spacings {sorted(spacing)}"
    rows[f"Options (K = {len(ep.options)})"] = (
        f'<ul class="options">{chips}</ul><span class="small muted">Values {vals[0]}-{vals[-1]}, '
        f"{shape}; the correct value is the {_ordinal(rank)} smallest.</span>")
    ev_steps = ep.reveal_steps
    gaps = ", ".join(str(n - s) for s in ev_steps)
    rows["Evidence steps"] = (f"{', '.join(map(str, ev_steps))} ({gaps} steps before the need "
                              f"step; {ep.cell.distance})")
    tail = ep.n_steps - 1 - n
    rows["Need step"] = (f"{n} (steps are numbered from 0; {tail} routine "
                         f"step{'' if tail == 1 else 's'} after it)")
    rows["Distractor bindings"] = ("; ".join(f"{_esc(d.entity)} {d.value} (step {d.step})"
                                             for d in ep.distractors)
                                   + ' <span class="small muted">(other entities, never '
                                   "needed)</span>")
    rows["Lookup"] = (f"offered (at most {ep.lookup.max_per_episode} per episode)"
                      if ep.lookup.available else "not offered")
    return '<dl class="summary">' + "".join(
        f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows.items()) + "</dl>"


def _scan_html(ep: Episode, scan: dict) -> str:
    opt, key = scan["options_outside"], scan["key_outside"]
    if not opt and not key:
        where = ("the option list and the fact's binding at its evidence step"
                 if ep.cell.fact == "observed" else "the option list")
        return ('<p class="scan ok">Automated scan of the whole episode text (system prompt and '
                f"every observation, log filler included): no option string outside {where}; "
                "the target key only in the evidence bindings at their evidence steps and in "
                "the need question.</p>")
    items = "".join(
        f"<li>{what} <code>{_esc(h['match'])}</code> at {_esc(h['where'])}: "
        f"<code>{_esc(h['context'])}</code></li>"
        for what, hits in (("option string", opt), ("target key", key)) for h in hits)
    return (f'<div class="scan bad"><strong>Automated scan found {len(opt)} option string(s) and '
            f"{len(key)} target key occurrence(s) outside the places they belong:</strong>"
            f"<ul>{items}</ul></div>")


def _step_html(s, m: Marks) -> tuple[str, bool]:
    """One step of the full episode, and whether Skim shows it (evidence, a distractor
    binding, the target key or an option string anywhere in its observation). The log tail
    (console header, filler and end-of-log line) is collapsed and opens by itself when it
    holds a marked string; the EVENT line is always shown."""
    ev_at = s.event_start - len(EVENT_PREFIX)
    log, f_log = highlight(s.observation[:ev_at], m)
    event, f_event = highlight(s.observation[ev_at:], m)
    flag = (s.kind in ("reveal", "distractor", "need")
            or bool((f_log | f_event) & {"ev", "dist", "key", "opt"}))
    kind = {"routine": f"routine ({s.routine_type})", "reveal": "evidence",
            "distractor": "distractor binding", "need": "need step"}[s.kind]
    labels = ", ".join(s.reveals)
    n_lines = s.observation[s.filler_start:s.filler_end].count("\n") + 1
    marked = bool(f_log)
    return (
        f'<div class="step{" flag" if flag else ""}" data-step="{s.index}">'
        f'<div class="step-head"><strong>Step {s.index}</strong>'
        f'<span class="kind {s.kind}">{kind}{": " + labels if labels else ""}</span>'
        f"<span>{_esc(s.sim_time[11:19])}</span>"
        f"<span>expected <code>{_esc(s.expected_action)}</code></span></div>"
        f'<details class="filler{" leak" if marked else ""}"{" open" if marked else ""}>'
        f"<summary>Log tail: {n_lines} lines{' (holds a marked string)' if marked else ''}"
        f"</summary><pre>{log}</pre></details>"
        f"<pre>{event}</pre></div>"), flag


def render_card(ep: Episode) -> str:
    m = Marks.of(ep)
    scan = scan_episode(ep, m)
    need = ep.need
    head, _ = highlight(need.observation[:need.filler_start], m)
    filler, _ = highlight(need.observation[need.filler_start:need.filler_end], m)
    foot, _ = highlight(need.observation[need.filler_end:], m)
    sys_html, _ = highlight(ep.system_prompt, m)
    parts = [_step_html(s, m) for s in ep.steps]
    steps = "".join(h for h, _ in parts)
    n_flag = sum(f for _, f in parts)
    tid, eid = _attr(ep.template_id), _attr(ep.episode_id)
    radios = "".join(f'<label><input type="radio" name="v-{tid}" value="{v}"> {label}</label>'
                     for v, label in VERDICTS.items())
    return (
        f'<article class="card" id="ep-{tid}" data-episode="{eid}" data-cell="{ep.cell.id}" '
        f'data-seed="{ep.template_seed}">\n'
        f'<div class="card-head"><h2>{_esc(ep.episode_id)}</h2>'
        f'<span><span class="status">Not reviewed</span> · <a class="small" href="#f-{tid}">'
        f"Jump to verdict</a></span></div>\n"
        f'<div class="small muted">Task cell {ep.cell.id} ({_esc(cell_label(ep.cell.id))}) · '
        f"template seed {ep.template_seed} · skin {_esc(ep.skin)} · {ep.n_steps} steps</div>\n"
        f"{_summary(ep, m)}\n{_scan_html(ep, scan)}\n"
        f"<h3>Need-step observation (step {ep.need_step}, full text)</h3>\n"
        f'<pre class="head-line">{head.rstrip()}</pre>'
        f'<pre class="need-filler">{filler}</pre><pre>{foot.lstrip()}</pre>\n'
        f"<h3>Full episode, step by step</h3>\n"
        f'<div class="step-tools"><label><input type="checkbox" class="skim-toggle"> Skim: only '
        f"steps with evidence, a distractor binding, the target key or an option string</label>"
        f'<button type="button" data-action="expand-logs">Expand all logs</button>'
        f'<button type="button" data-action="collapse-logs">Collapse all logs</button>'
        f"</div>\n"
        f'<p class="skim-note">Skim is on: showing {n_flag} of {ep.n_steps} steps.</p>\n'
        f'<div class="step flag"><div class="step-head"><strong>System prompt</strong></div>'
        f"<pre>{sys_html}</pre></div>\n{steps}\n"
        f'<div class="findings" id="f-{tid}"><fieldset><legend>Your verdict for this episode'
        f'</legend><div class="verdict">{radios}</div></fieldset>'
        f'<label class="small" for="notes-{tid}">Notes: what you saw and where (step, text)'
        f"</label>"
        f'<textarea id="notes-{tid}" spellcheck="true"></textarea>'
        f'<div class="findings-foot"><span class="saved muted"></span>'
        f'<button type="button" data-action="clear-verdict">Clear verdict</button></div>'
        f"</div>\n</article>\n")


def _bar(title: str, back: bool) -> str:
    return (('<a href="index.html">All task cells</a>' if back else "")
             + f"<strong>{_esc(title)}</strong>"
             + '<span class="progress grow" id="progress"></span>'
             + ('<label class="small"><input type="checkbox" id="skim-all"> Skim all</label>'
                if back else "")
             + '<button type="button" data-action="export">Export findings CSV</button>')


def _data(pkg: dict, page: str) -> dict:
    return {"ns": pkg["storage_namespace"], "package": pkg["id"], "page": page,
            "verdicts": VERDICTS, "findings_path": pkg["findings_path"],
            "episodes": pkg["episodes"]}


REMINDER = (
    "<p>Look for anything that gives away the correct option without the evidence bindings: the "
    "value in the log filler or routine events, the entity or skin names, the question wording, "
    "the option list's order or spacing; for derived facts, a subset of the clues already "
    "narrowing the options; and anything broken or odd (duplicated facts, garbled text, a wrong "
    "option list). The full checklist is on the <a href=\"index.html#instructions\">index "
    "page</a>.</p>")


def render_cell_page(cell_id: str, eps: list[Episode], pkg: dict) -> str:
    toc = "".join(f'<li><a href="#ep-{_attr(e.template_id)}">{_esc(e.template_id)}</a></li>'
                  for e in eps)
    body = (
        f"<h1>Task cell {cell_id}</h1>\n"
        f'<p class="muted">{_esc(cell_label(cell_id))}. {len(eps)} base-variant episodes, '
        f"templates {_esc(eps[0].template_id)} to {_esc(eps[-1].template_id)} (seeds "
        f"{eps[0].template_seed}-{eps[-1].template_seed}). Each card shows the answer; there is "
        "no model output on this page.</p>\n"
        f"{STORAGE_WARNING}\n{REMINDER}\n{LEGEND}\n"
        f'<p id="message" class="notice" hidden></p>\n'
        f'<nav aria-label="Episodes on this page"><ul class="toc">{toc}</ul></nav>\n'
        + "".join(render_card(e) for e in eps)
        + f'<p class="small muted">Package {_esc(pkg["id"])} · generator '
        f"{_esc(pkg['generator_version'])} · config {pkg['config_hash'][:12]}</p>")
    return _page(f"Spot-check {cell_id}", _bar(cell_id, back=True), body,
                 _data(pkg, cell_id))


def _audit_rows(audits: dict) -> str:
    rows = []
    for c in audits["checks"]:
        res = ('<span class="fail">FAIL</span>' if not c["pass"] else
               '<span class="pass">pass</span>' if c.get("ran", True) else
               '<span class="muted">not run: the chi-square test needs at least 5 templates '
               "per category</span>")
        rows.append(f"<tr><td><code>{_esc(c['check'])}</code></td><td>{_esc(c['what'])}</td>"
                    f"<td>{res}</td></tr>")
    return "".join(rows)


def render_index(pkg: dict) -> str:
    cells = "".join(
        f'<tr><td><a href="{cell}.html">{cell}</a><div class="small muted">'
        f"{_esc(cell_label(cell))}</div></td>"
        f'<td class="num" data-cell-progress="{cell}"></td>'
        + "".join(f'<td class="num" data-cell-count="{cell}|{v}"></td>' for v in VERDICTS)
        + "</tr>" for cell in pkg["task_cells"])
    a = pkg["audits"]
    not_run = [c["check"] for c in a["checks"] if c["pass"] and not c.get("ran", True)]
    audit_note = (
        '<p class="fail">At least one check FAILED: tell Claude before reviewing.</p>'
        if a["pass"] is False else
        '<p class="fail">The audits were not run for this build.</p>' if a["pass"] is None else
        f'<p class="pass">Every check that ran passed on these templates.</p><p class="small '
        f'muted">Not run here: {", ".join(not_run)}. Their chi-square test needs more '
        "templates than this package has. The exact check that each block of 10 templates "
        "uses every letter and rank once did run.</p>"
        if not_run else '<p class="pass">Every check passed on these templates.</p>')
    seeds = pkg["template_seeds"]
    n_shortcut = sum(c["audit"] == "shortcut_audit" for c in a["checks"])
    body = f"""<h1>G1 spot-check: PersistGym-lite validity episodes</h1>
<p class="small">Jump to: <a href="#instructions">instructions</a> ·
<a href="#cells">task cells and progress</a> · <a href="#export">saving and exporting</a></p>
{STORAGE_WARNING}
<p id="message" class="notice" hidden></p>
<section id="instructions">
<h2>What you are checking</h2>
<p>PREREG §4.4: the researcher spot-checks 20 episodes per task cell for shortcuts. These pages hold
the base variant of validity templates {_esc(pkg["template_ids"][0])} to
{_esc(pkg["template_ids"][-1])} (seeds {seeds[0]}-{seeds[-1]}) in all {len(pkg["task_cells"])} task
cells, {pkg["n_episodes"]} episodes, rendered with the default generator config (generator
{_esc(pkg["generator_version"])}, config hash <code>{pkg["config_hash"][:12]}</code>), the
same templates and config as the luna validity runs. Those runs sent the restated and withheld
renderings of these templates. The base rendering shown here differs from the restated one only
at the need step, where the restated one puts the evidence records before the question and keeps
a shorter log filler to stay at v tokens, and from the withheld one only in the fact and clue
bindings, which the withheld one replaces with stand-in bindings of equal length (the rule is
kept).</p>
<p><strong>The pages show the answer.</strong> Every card marks the correct option and the evidence,
so you can judge whether anything else gives the answer away. <strong>There is no model output
here</strong>: no replies, transcripts or scores.</p>
<h2>What counts as a shortcut</h2>
<p>Any way to pick the correct option at the need step, or to narrow the options, without the
evidence bindings. Look for:</p>
<ul>
<li>the target value (observed facts) or the derived value guessable without the evidence: from
the log filler, the routine events, the entity or skin names, the question wording, or the
structure of the option list (order, spacing, a value that stands out);</li>
<li>for derived facts: a subset of the clues (with the rule) already narrowing the options, or a
clue or the rule that gives the value away on its own;</li>
<li>a distractor binding that points at the correct option;</li>
<li>anything broken or odd: a duplicated fact, garbled text, a wrong option list (the value
missing, two equal options), evidence at an unexpected step, a routine event whose expected
action looks wrong, lookup described in a cell that does not offer it.</li>
</ul>
<h2>Already checked by program</h2>
<p>These $0 audits (<code>persistgym/validity.py</code>) ran on exactly these {len(seeds)}
templates, in their base, restated and withheld renderings ({a["n_episodes"]} episodes), when this
package was built: the <strong>shortcut audit</strong> ({n_shortcut} checks re-derived from the
text, among them that no option, clue or distractor value, entity name or clue name appears in
the log filler or routine events), the <strong>lookup audit</strong>, the <strong>no-memory
heuristic baselines</strong>, the <strong>partial-memory gate</strong> for derived facts and the
<strong>programmatic oracles</strong>. <strong>So spend your time on what a program would
miss</strong>: meaning, salience, wording, and patterns a person would notice.</p>
{audit_note}
<details><summary>The {len(a["checks"])} checks and their results</summary>
<div class="table-wrap"><table><thead><tr><th>Check</th><th>What it verifies</th><th>Result</th>
</tr></thead><tbody>{_audit_rows(a)}</tbody></table></div></details>
<h2>How to review</h2>
<ol>
<li>Read the summary box: target key, true or derived value, options with the correct one marked,
evidence steps.</li>
<li>Check the automated scan line under it (it should find nothing).</li>
<li>Read the need-step observation in full.</li>
<li>Go through the episode: <em>Skim</em> shows only the steps with evidence, a distractor
binding, the target key or an option string; every step's log filler is collapsed and opens with
a click (a filler that holds a marked string opens by itself and its label turns red).</li>
<li>Pick a verdict and write a note: what you saw and where (step and text).</li>
</ol>
<p>Verdicts: <strong>No shortcut</strong>: nothing in the episode text other than the evidence
bindings lets an agent beat chance (10%). <strong>Possible shortcut</strong>: something might
help; describe it.
<strong>Shortcut</strong>: the evidence is not needed, or the episode is broken; describe it. No
verdict is pre-filled or suggested.</p>
<h2>Highlights</h2>
{LEGEND}
<p class="small muted">Option strings are matched as whole numbers (331 inside 13310 does not
count) and the target key as a whole word in any case, the rules the audits use.</p>
</section>
<section id="cells">
<h2>Task cells</h2>
<div class="table-wrap"><table><thead><tr><th>Task cell (page)</th><th class="num">Reviewed</th>
<th class="num">No shortcut</th><th class="num">Possible</th><th class="num">Shortcut</th></tr>
</thead><tbody>{cells}</tbody></table></div>
</section>
<section id="export">
<h2>Saving and exporting findings</h2>
<p>Verdicts and notes are saved in this browser as you go (localStorage, keys under
<code>{_esc(pkg["storage_namespace"])}</code>, shared by every page of this package). Nothing
leaves your computer. <strong>Export findings CSV</strong> (on every page) downloads
<code>findings.csv</code> with all {pkg["n_episodes"]} rows; unreviewed episodes have an empty
verdict. Save it as <code>{_esc(pkg["findings_path"])}</code> and tell Claude, who commits it and
reports the outcome at G1. The go/no-go call is yours.</p>
<p>If the counts above stay at 0 after you review on a task-cell page, this browser keeps
storage per file: open the folder through a local server instead (README.md), or export from
each page and import the files here. <button type="button" data-action="import">Import findings
CSV</button><input type="file" id="import-file" accept=".csv,text/csv" hidden></p>
</section>
<section>
<h2>About this package</h2>
<p class="small">Package <code>{_esc(pkg["id"])}</code>; split {pkg["split"]}, template indices
{pkg["indices"][0]}-{pkg["indices"][-1]}, variant {pkg["variant"]}; generator
{_esc(pkg["generator_version"])} (schema {pkg["schema_version"]}); config hash
<code>{pkg["config_hash"]}</code>; PREREG version {_esc(str(pkg["prereg_version"]))}. The
committed manifest is <code>{_esc(pkg["manifest_path"])}</code>. Rebuild these pages with
<code>uv run python -m persistgym spotcheck --n {pkg["n_templates"]} --out-id
{_esc(pkg["id"])}</code>.</p>
</section>"""
    return _page("G1 spot-check", _bar("G1 spot-check", back=False), body,
                 _data(pkg, "index"))


# ---------------------------------------------------------------------------
# Audits, files and the build
# ---------------------------------------------------------------------------

AUDIT_WHAT = {
    "filler_has_no_reserved_strings":
        "no option, clue, distractor or stand-in value, entity name or clue name in log filler",
    "routine_events_have_no_reserved_strings": "the same for routine events",
    "observation_tokens_equal_v": "every observation re-counts to exactly v tokens",
    "derived_and_withheld_never_show_target_before_need":
        "derived and withheld episodes never show the target value before the need step",
    "observed_target_only_at_reveal": "an observed target value appears only at its reveal",
    "options_valid_and_distinct": "K distinct 3-digit options, exactly one equal to the target",
    "options_form_one_evenly_spaced_cluster": "options are one cluster of consecutive values",
    "options_exclude_clue_values": "no clue value is an option",
    "distractor_bindings_valid":
        "2 distractor bindings, other entities, values never options or clues, shown once",
    "withheld_never_names_target_before_need":
        "the withheld control never names the target before the need step",
    "withheld_stand_ins_equal_length_and_valid":
        "withheld stand-in bindings have equal token length and valid values",
    "near_far_hold_when_recomputed_from_text": "near and far re-derived from the text",
    "full_history_context_within_max": "full history at the need step stays within 64k",
    "cells_share_need_step_options_routine_and_distractors":
        "the 8 cells of a template share need step, options, routine text and distractors",
    "correct_letter_balanced": "the correct letter is balanced (chi-square test)",
    "correct_rank_balanced":
        "the correct value's rank among the options is balanced (chi-square test)",
    "letter_rank_and_n_clues_exact_within_complete_blocks":
        "each block of 10 templates uses every letter and rank once and 5/5 clue counts",
    "lookup_serves_keys_and_refuses_after_cap":
        "lookup re-shows the right records, 'no such record' and the cap of 3",
    "heuristic_baselines": "no-memory baselines (most frequent, last seen, first, median "
                           "option, prior letter) score ≤ chance + 10pp on every view",
    "partial_memory": "derived cells: no proper subset of the clues narrows the options; "
                      "partial-memory heuristics ≤ chance + 10pp",
    "oracles": "the key and text oracles answer every routine step, and every need step of "
               "the base and restated episodes, correctly; the no-memory lookup oracle answers "
               "every need step where lookup is offered (base) or the records are restated",
}


def run_audits(eps: list[Episode], cfg: GeneratorConfig, n: int) -> dict:
    """The $0 audits of `persistgym render` (validity.py) on these templates."""
    # The chi-square balance checks pass without a test below 5 templates per category
    # (chi2_p is None); they are marked as not run, so the index does not count them as
    # passed. The exact per-block check covers these templates.
    checks = [{"audit": name, "check": c["check"], "pass": c["pass"],
               "ran": not (isinstance(c["detail"], dict) and "chi2_p" in c["detail"]
                           and c["detail"]["chi2_p"] is None)}
              for name, report in (("shortcut_audit", shortcut_audit(eps)),
                                   ("lookup_audit", lookup_audit(eps))) for c in report]
    cal = [sample_template("main", i, cfg).correct_label for i in range(min(n, 100))]
    hb = heuristic_baselines(eps, calibration_labels=cal)
    pm = partial_memory_from_episodes(eps) or {}
    orc = oracle_scores(eps)
    checks += [{"audit": name, "check": name, "pass": ok, "ran": True}
               for name, ok in (("heuristic_baselines", bool(hb.get("pass", True))),
                                ("partial_memory", bool(pm.get("pass", True))),
                                ("oracles", bool(orc["pass"])))]
    for c in checks:
        c["what"] = AUDIT_WHAT.get(c["check"], "")
    return {"variants": list(VARIANTS), "n_episodes": len(eps), "checks": checks,
            "pass": all(c["pass"] for c in checks)}


def findings_csv(rows: list[list]) -> str:
    """RFC 4180 text (CRLF line ends, minimal quoting), the same as the pages' export."""
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(FINDINGS_COLUMNS)
    w.writerows(rows)
    return buf.getvalue()


def readme_text(pkg: dict) -> str:
    html_dir, n = pkg["html_dir"], pkg["n_templates"]
    return f"""# G1 spot-check package `{pkg["id"]}`

PREREG §4.4: the researcher spot-checks 20 episodes per task cell for shortcuts, using generated
episodes from the validity range and no model output.

This package holds {pkg["n_episodes"]} episodes: the base variant of validity templates
{pkg["template_ids"][0]} to {pkg["template_ids"][-1]} (seeds {pkg["template_seeds"][0]}-{pkg["template_seeds"][-1]}) in all 8 task cells. They are rendered
with the default generator config, the templates and config of the luna validity runs:
- generator {pkg["generator_version"]};
- config hash `{pkg["config_hash"]}`.

Files here (committed):
- `manifest.json`: commit, PREREG version, generator version and config hash, split, indices,
  seeds, variant, the episode ids by task cell, where the pages are, and the $0 audits that ran
  on these templates when the package was built.
- `findings_template.csv`: the {pkg["n_episodes"]} rows with an empty verdict and notes.
- `findings.csv`: your exported findings, once you have saved them here.

## Open the pages

The pages are in this folder (gitignored, about {pkg["html_mb"]:.0f} MB):

    {html_dir}/

If it is missing, rebuild it from the repository root. The episodes are regenerated from their
seeds, and the committed files here are kept:

    uv run python -m persistgym spotcheck --n {n} --out-id {pkg["id"]}

Open `index.html` in that folder in Chrome or Edge. It has the instructions, the audit results
and a link to each task cell's page (20 episodes each). The pages are static: they load nothing
from the network and send nothing anywhere.

Findings are saved in the browser's local storage, which every page of the package shares. Some
browsers (Firefox, Safari) may keep the storage of each local file apart: if the counts on the
index page stay at 0 after you review on a cell page, serve the folder locally and use that
address throughout:

    uv run python -m http.server 8765 --bind 127.0.0.1 --directory {html_dir}

then open http://127.0.0.1:8765/. Storage belongs to the address, so findings saved under one
address do not show under another; move them with Export and Import.

## Record and export findings

1. On each task cell's page, read each episode's card (summary box, scan line, need-step
   observation, then the episode, with Skim if you like), pick a verdict and write a note: what
   you saw and where (step and text). Verdicts: `no_shortcut`, `possible_shortcut`, `shortcut`.
   Nothing is pre-filled.
2. Click **Export findings CSV** (on any page). It downloads `findings.csv` with all
   {pkg["n_episodes"]} rows and the columns `{",".join(FINDINGS_COLUMNS)}` (RFC 4180);
   unreviewed episodes have an empty verdict.
3. Save it as `{pkg["findings_path"]}`. Move the downloaded file as it is: a spreadsheet
   program may change its encoding or separators when it saves.
4. Tell Claude. Claude commits the file, checks it and counts the verdicts per task cell with
   the command below, and reports the outcome at G1 in `results/decisions.md`. The go/no-go
   call is yours.

       uv run python -m persistgym spotcheck-findings --out-id {pkg["id"]}

**Import findings CSV** on the index page loads an exported file back, for example to move
findings to another browser.
"""


def _verify_runs(chash: str) -> None:
    if chash != EXPECTED_CONFIG_HASH:
        raise SpotcheckError(
            f"the generator config hash is {chash}, not the luna validity runs' "
            f"{EXPECTED_CONFIG_HASH} (generator_config_hashes in {', '.join(VALIDITY_RUNS)}): "
            "the default GeneratorConfig changed, so these would not be the episodes those "
            "runs used")


def _same_episodes(old: dict, new: dict) -> bool:
    keys = ("split", "variant", "config_hash", "generator_version", "episode_ids_by_task_cell")
    return all(old.get(k) == new.get(k) for k in keys)


def build(out_id: str | None = None, n: int = DEFAULT_N, cfg: GeneratorConfig | None = None,
          raw_root: Path | None = None, results_root: Path | None = None,
          audits: bool = True, command: str | None = None) -> dict:
    """Write the review pages (under `raw_root`, default `RAW_ROOT`) and the package files
    (under `results_root`, default `RESULTS_ROOT`); returns the manifest. `audits=False`
    skips the $0 audits (quick tests only: the index page then says they did not run)."""
    started = utc_now()
    cfg = cfg or GeneratorConfig()
    chash = config_hash(cfg.to_dict())
    _verify_runs(chash)
    lo, hi = SEED_RANGES[SPLIT]
    if not 1 <= n <= hi - lo:
        raise SpotcheckError(f"--n must be between 1 and {hi - lo}, got {n}")
    out_id = check_id(out_id or default_id(n, chash))
    html_dir = Path(raw_root or RAW_ROOT) / out_id
    pkg_dir = Path(results_root or RESULTS_ROOT) / out_id

    variants = list(VARIANTS) if audits else [VARIANT]
    all_eps = [e for _, eps in generate(SPLIT, range(n), cfg, ALL_CELLS, variants) for e in eps]
    base = {c.id: [e for e in all_eps if e.variant == VARIANT and e.cell == c] for c in ALL_CELLS}
    by_cell = {cid: [e.episode_id for e in eps] for cid, eps in base.items()}
    rows = [[e.episode_id, cid, e.template_seed, "", ""] for cid, eps in base.items()
            for e in eps]
    audit = (run_audits(all_eps, cfg, n) if audits else
             {"variants": [], "n_episodes": 0, "checks": [], "pass": None})

    manifest_path = pkg_dir / "manifest.json"
    pkg = {
        "package": "PersistGym-lite G1 spot-check (PREREG §4.4)",
        "id": out_id,
        "split": SPLIT, "indices": list(range(n)), "n_templates": n,
        "template_ids": [e.template_id for e in base[ALL_CELLS[0].id]],
        "template_seeds": [e.template_seed for e in base[ALL_CELLS[0].id]],
        "variant": VARIANT, "task_cells": [c.id for c in ALL_CELLS], "n_episodes": len(rows),
        "generator_version": GENERATOR_VERSION, "schema_version": SCHEMA_VERSION,
        "config_hash": chash, "config": cfg.to_dict(), "validity_runs": list(VALIDITY_RUNS),
        "prereg_version": prereg_version(),
        "episode_ids_by_task_cell": by_cell,
        "html_dir": _rel(html_dir), "html_index": _rel(html_dir / "index.html"),
        "html_pages": {cid: _rel(html_dir / f"{cid}.html") for cid in by_cell},
        "manifest_path": _rel(manifest_path),
        "findings_template": _rel(pkg_dir / "findings_template.csv"),
        "findings_path": _rel(pkg_dir / "findings.csv"),
        "findings_columns": list(FINDINGS_COLUMNS), "verdicts": list(VERDICTS),
        "storage_namespace": f"persistgym-spotcheck/{out_id}/",
        "audits": audit,
        "episodes": [[r[0], r[1], r[2]] for r in rows],
    }
    old = None
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not _same_episodes(old, pkg):
            raise SpotcheckError(f"{_rel(manifest_path)} describes other episodes; choose "
                                 "another --out-id")

    html_dir.mkdir(parents=True, exist_ok=True)
    pages = {"index.html": render_index(pkg)}
    pages |= {f"{cid}.html": render_cell_page(cid, eps, pkg) for cid, eps in base.items()}
    size = 0
    for name, text in pages.items():
        data = text.encode("utf-8")
        (html_dir / name).write_bytes(data)
        size += len(data)
    pkg["html_bytes"] = size
    pkg["html_mb"] = size / 1e6

    if old is not None:  # the committed files stay as they are
        return {**old, "audits": audit, "html_bytes": size, "kept_committed_files": True}
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "findings_template.csv").write_bytes(findings_csv(rows).encode("utf-8"))
    (pkg_dir / "README.md").write_text(readme_text(pkg), encoding="utf-8", newline="\n")
    manifest = {k: v for k, v in pkg.items() if k not in ("episodes", "html_mb")}
    manifest.update(
        tiktoken=metadata.version("tiktoken"), command=command, **git_state(),
        started_utc=started, finished_utc=datetime.now(UTC).isoformat(timespec="seconds"))
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8", newline="\n")
    return manifest


def run(args: argparse.Namespace) -> int:
    K = GeneratorConfig().K_options
    if args.n <= 0 or args.n % K:
        # PREREG D7: whole balance blocks; the position baselines need them to sit at chance
        print(f"refused: --n must be a positive multiple of the balance block K={K} "
              f"(PREREG D7), got {args.n}", file=sys.stderr)
        return 2
    # the command as typed from the repository root, without this machine's paths
    command = (f"uv run python -m persistgym spotcheck --n {args.n}"
               + (f" --out-id {args.out_id}" if args.out_id else ""))
    try:
        manifest = build(args.out_id, args.n, command=command)
    except SpotcheckError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    a = manifest["audits"]
    print(f"spot-check package {manifest['id']}: {manifest['n_episodes']} episodes "
          f"({manifest['n_templates']} templates x {len(manifest['task_cells'])} task cells), "
          f"config {manifest['config_hash'][:12]}")
    print(f"  pages:    {manifest['html_index']} (+ {len(manifest['html_pages'])} task-cell "
          f"pages, {manifest['html_bytes'] / 1e6:.1f} MB)")
    print(f"  package:  {manifest['manifest_path']}"
          + (" (kept as committed: same episodes)" if manifest.get("kept_committed_files")
             else ""))
    for c in a["checks"]:
        if not c["pass"]:
            print(f"  [FAIL] {c['check']}")
        elif not c.get("ran", True):
            print(f"  [not run: too few templates for chi-square] {c['check']}")
    print(f"  audits on {a['n_episodes']} episodes ({','.join(a['variants'])}): "
          f"{'pass' if a['pass'] else 'FAIL'}")
    return 0 if a["pass"] else 1


# ---------------------------------------------------------------------------
# Findings (the researcher's export)
# ---------------------------------------------------------------------------

def read_findings(path: Path, manifest: dict) -> list[dict]:
    """The exported findings.csv, checked against the manifest: the header, every episode
    exactly once with its task cell and seed, and verdicts from `VERDICTS` or empty."""
    text = Path(path).read_text(encoding="utf-8-sig")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if not rows or tuple(rows[0]) != FINDINGS_COLUMNS:
        raise SpotcheckError(f"{path}: the first row must be {','.join(FINDINGS_COLUMNS)}")
    want = {eid: cell for cell, ids in manifest["episode_ids_by_task_cell"].items()
            for eid in ids}
    seeds = dict(zip(manifest["template_ids"], manifest["template_seeds"], strict=True))
    out, seen, problems = [], set(), []
    for k, r in enumerate(rows[1:], start=2):
        if not any(r):
            continue
        if len(r) != len(FINDINGS_COLUMNS):
            problems.append(f"row {k}: {len(r)} fields")
            continue
        rec = dict(zip(FINDINGS_COLUMNS, r, strict=True))
        eid = rec["episode_id"]
        if eid not in want:
            problems.append(f"row {k}: unknown episode id {eid!r}")
        elif eid in seen:
            problems.append(f"row {k}: {eid} given twice")
        elif (rec["task_cell"] != want[eid]
              or rec["template_seed"] != str(seeds[eid.split("/")[0]])):
            problems.append(f"row {k}: task cell or seed of {eid} differ from the manifest")
        elif rec["verdict"] not in ("", *VERDICTS):
            problems.append(f"row {k}: unknown verdict {rec['verdict']!r}")
        seen.add(eid)
        out.append(rec)
    missing = sorted(set(want) - seen)
    if missing:
        problems.append(f"{len(missing)} episode(s) missing, e.g. {missing[0]}")
    if problems:
        raise SpotcheckError(f"{path}: " + "; ".join(problems[:10]))
    return out


def summarize_findings(rows: list[dict], manifest: dict) -> dict:
    """Verdict counts per task cell, and every episode with a (possible) shortcut or notes."""
    cells = {}
    for cid in manifest["task_cells"]:
        c = Counter(r["verdict"] or "unreviewed" for r in rows if r["task_cell"] == cid)
        cells[cid] = {v: c.get(v, 0) for v in (*VERDICTS, "unreviewed")}
    total = Counter(r["verdict"] or "unreviewed" for r in rows)
    flagged = [r for r in rows if r["verdict"] in ("possible_shortcut", "shortcut")]
    return {"id": manifest["id"], "n_episodes": len(rows),
            "complete": total.get("unreviewed", 0) == 0,
            "totals": {v: total.get(v, 0) for v in (*VERDICTS, "unreviewed")},
            "cells": cells, "flagged": flagged,
            "notes_only": [r for r in rows if not r["verdict"] and r["notes"]]}


def run_findings(args: argparse.Namespace) -> int:
    try:
        pkg_dir = RESULTS_ROOT / check_id(args.out_id)
        manifest = json.loads((pkg_dir / "manifest.json").read_text(encoding="utf-8"))
        path = Path(args.findings) if args.findings else pkg_dir / "findings.csv"
        rows = read_findings(path, manifest)
    except (SpotcheckError, OSError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    s = summarize_findings(rows, manifest)
    cols = (*VERDICTS, "unreviewed")
    print(f"{'task cell':<22}" + "".join(f"{v:>19}" for v in cols))
    for cid, c in s["cells"].items():
        print(f"{cid:<22}" + "".join(f"{c[v]:>19}" for v in cols))
    print(f"{'all':<22}" + "".join(f"{s['totals'][v]:>19}" for v in cols))
    for r in s["flagged"]:
        print(f"  {r['verdict']}: {r['episode_id']}: {r['notes']}")
    print(f"complete={s['complete']}")
    return 0 if s["complete"] else 1


def add_parsers(sub) -> None:
    sc = sub.add_parser("spotcheck", help="G1 spot-check package: review pages for validity "
                                          "episodes (PREREG §4.4)")
    sc.add_argument("--n", type=int, default=DEFAULT_N,
                    help="validity templates 0..n-1 (default 20, the validity runs' templates)")
    sc.add_argument("--out-id", default=None,
                    help="package id (default g1-validity-0-<n>-<confighash8>)")
    sf = sub.add_parser("spotcheck-findings",
                        help="check an exported findings.csv and count verdicts per task cell")
    sf.add_argument("--out-id", required=True, help="package id")
    sf.add_argument("--findings", default=None,
                    help="findings file (default results/spotcheck/<id>/findings.csv)")
