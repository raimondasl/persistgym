/* G1 spot-check pages (persistgym/spotcheck.py inlines this file into every page).

   Findings live in this browser's localStorage, one key per episode, under one namespace that
   every page of the package shares, so each page can export all of them. Every storage access
   is wrapped in try/catch: a finding this page cannot write is kept in memory until the page
   is closed (the page says so and asks before closing), and findings already in storage
   are still read and exported. Nothing is ever pre-filled: an episode has a verdict only
   after the reviewer picks one. */
"use strict";

var SpotCSV = (function () {
  var COLUMNS = ["episode_id", "task_cell", "template_seed", "verdict", "notes"];

  // RFC 4180: a field holding a comma, a double quote, CR or LF is quoted and its double
  // quotes doubled; every record ends with CRLF. This is what Python's csv module writes.
  function field(value) {
    var s = value === null || value === undefined ? "" : String(value);
    return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }

  function toCsv(rows) {
    return [COLUMNS].concat(rows).map(function (r) {
      return r.map(field).join(",");
    }).join("\r\n") + "\r\n";
  }

  // Records of an RFC 4180 text (a leading byte-order mark is ignored).
  function parse(text) {
    var rows = [], row = [], f = "", quoted = false, i = 0, n = text.length, c;
    if (text.charCodeAt(0) === 0xfeff) i = 1;
    for (; i < n; i++) {
      c = text[i];
      if (quoted) {
        if (c === '"') {
          if (text[i + 1] === '"') { f += '"'; i++; } else { quoted = false; }
        } else {
          f += c;
        }
      } else if (c === '"') {
        quoted = true;
      } else if (c === ",") {
        row.push(f); f = "";
      } else if (c === "\r" || c === "\n") {
        if (c === "\r" && text[i + 1] === "\n") i++;
        row.push(f); rows.push(row); row = []; f = "";
      } else {
        f += c;
      }
    }
    if (f !== "" || row.length) { row.push(f); rows.push(row); }
    return rows;
  }

  return { COLUMNS: COLUMNS, field: field, toCsv: toCsv, parse: parse };
})();

if (typeof module !== "undefined" && module.exports) module.exports = SpotCSV;

(function () {
  if (typeof document === "undefined") return;
  var data = JSON.parse(document.getElementById("spotcheck-data").textContent);
  var NS = data.ns;
  var VERDICTS = data.verdicts;
  var unsaved = {};  // findings this page could not write to storage, by episode id
  var timers = {};

  // ---- storage ------------------------------------------------------------------------
  function probe() {
    try {
      var k = NS + "__probe__";
      window.localStorage.setItem(k, "1");
      window.localStorage.removeItem(k);
      return true;
    } catch (e) {
      return false;
    }
  }

  function isVerdict(v) {
    return typeof v === "string" && Object.prototype.hasOwnProperty.call(VERDICTS, v);
  }

  function has(obj, key) {
    return Object.prototype.hasOwnProperty.call(obj, key);
  }

  // The finding of one episode: this page's unsaved one if any, else the stored one.
  function load(id) {
    if (has(unsaved, id)) return unsaved[id];
    var raw = null;
    try {
      raw = window.localStorage.getItem(NS + id);
    } catch (e) {
      return null;  // storage cannot be read at all
    }
    try {
      var rec = raw ? JSON.parse(raw) : null;
      return rec && typeof rec === "object" ? rec : null;
    } catch (e) {
      return null;  // an unreadable entry counts as not reviewed
    }
  }

  function save(id, rec) {
    try {
      window.localStorage.setItem(NS + id, JSON.stringify(rec));
      delete unsaved[id];
      return true;
    } catch (e) {
      unsaved[id] = rec;
      showStorageWarning();
      return false;
    }
  }

  function showStorageWarning() {
    var w = document.getElementById("storage-warning");
    if (w) w.hidden = false;
  }

  // ---- cards --------------------------------------------------------------------------
  function cards() {
    return Array.prototype.slice.call(document.querySelectorAll(".card[data-episode]"));
  }

  function statusText(rec) {
    if (rec && isVerdict(rec.verdict)) return VERDICTS[rec.verdict];
    if (rec && rec.notes) return "Notes only, no verdict yet";
    return "Not reviewed";
  }

  function paint(card, rec) {
    var v = rec && isVerdict(rec.verdict) ? rec.verdict : "";
    card.setAttribute("data-verdict", v);
    var st = card.querySelector(".status");
    if (st) st.textContent = statusText(rec);
    var chip = document.querySelector('.toc a[href="#' + card.id + '"]');
    if (chip) {
      chip.setAttribute("data-verdict", v);
      chip.title = statusText(rec);
    }
  }

  function restore(card) {
    var rec = load(card.getAttribute("data-episode")) || {};
    card.querySelectorAll(".verdict input[type=radio]").forEach(function (r) {
      r.checked = r.value === rec.verdict;
    });
    var notes = card.querySelector("textarea");
    if (notes && document.activeElement !== notes) notes.value = rec.notes || "";
    paint(card, rec);
  }

  function commit(card) {
    var checked = card.querySelector(".verdict input[type=radio]:checked");
    var rec = {
      verdict: checked ? checked.value : "",
      notes: card.querySelector("textarea").value,
      updated_utc: new Date().toISOString()
    };
    var ok = save(card.getAttribute("data-episode"), rec);
    paint(card, rec);
    var saved = card.querySelector(".saved");
    if (saved) {
      saved.textContent = ok
        ? "Saved in this browser at " + new Date().toLocaleTimeString()
        : "Not saved: browser storage is blocked. Export before closing this page.";
    }
    progress();
  }

  // ---- progress -----------------------------------------------------------------------
  function verdictOf(id) {
    var rec = load(id);
    return rec && isVerdict(rec.verdict) ? rec.verdict : "";
  }

  function progress() {
    var all = data.episodes, done = 0, byCell = {};
    all.forEach(function (e) {
      var v = verdictOf(e[0]);
      var c = byCell[e[1]] || (byCell[e[1]] = { n: 0, done: 0, counts: {} });
      c.n++;
      if (v) { done++; c.done++; c.counts[v] = (c.counts[v] || 0) + 1; }
    });
    var here = cards(), hereDone = here.filter(function (c) {
      return verdictOf(c.getAttribute("data-episode"));
    }).length;
    var el = document.getElementById("progress");
    if (el) {
      el.textContent = here.length
        ? "Reviewed " + hereDone + " of " + here.length + " on this page; " + done + " of " + all.length + " in all"
        : "Reviewed " + done + " of " + all.length;
    }
    document.querySelectorAll("[data-cell-progress]").forEach(function (td) {
      var c = byCell[td.getAttribute("data-cell-progress")];
      td.textContent = c ? c.done + " / " + c.n : "";
    });
    document.querySelectorAll("[data-cell-count]").forEach(function (td) {
      var parts = td.getAttribute("data-cell-count").split("|");
      var c = byCell[parts[0]];
      td.textContent = c ? String(c.counts[parts[1]] || 0) : "";
    });
  }

  function refreshAll() {
    cards().forEach(restore);
    progress();
  }

  // ---- export and import --------------------------------------------------------------
  function message(text) {
    var el = document.getElementById("message");
    if (el) { el.textContent = text; el.hidden = false; }
  }

  function exportCsv() {
    var done = 0;
    var rows = data.episodes.map(function (e) {
      var rec = load(e[0]) || {};
      var v = isVerdict(rec.verdict) ? rec.verdict : "";
      if (v) done++;
      return [e[0], e[1], String(e[2]), v, rec.notes || ""];
    });
    var blob = new Blob([SpotCSV.toCsv(rows)], { type: "text/csv;charset=utf-8" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "findings.csv";
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
    message("Exported " + rows.length + " rows (" + done + " with a verdict) as findings.csv. " +
            "Save it as " + data.findings_path + ".");
  }

  function importCsv(file) {
    var reader = new FileReader();
    reader.onload = function () {
      var rows = SpotCSV.parse(String(reader.result));
      var head = rows.shift() || [];
      if (head.join(",") !== SpotCSV.COLUMNS.join(",")) {
        message("Not imported: the first row must be " + SpotCSV.COLUMNS.join(",") + ".");
        return;
      }
      var known = {};
      data.episodes.forEach(function (e) { known[e[0]] = e; });
      var updates = [], unknown = 0, bad = 0, conflicts = 0;
      rows.forEach(function (r) {
        if (r.length === 1 && r[0] === "") return;
        var e = r.length === SpotCSV.COLUMNS.length && has(known, r[0]) ? known[r[0]] : null;
        if (!e || r[1] !== e[1] || r[2] !== String(e[2])) { unknown++; return; }
        var v = r[3], notes = r[4];
        if (v && !isVerdict(v)) { bad++; return; }
        if (!v && !notes) return;
        var old = load(r[0]);
        if (old && (old.verdict || old.notes) && (old.verdict !== v || (old.notes || "") !== notes)) conflicts++;
        updates.push([r[0], v, notes]);
      });
      if (conflicts && !window.confirm(conflicts + " episode(s) already have different findings " +
          "in this browser. Replace them with the file's?")) {
        message("Import cancelled; nothing changed.");
        return;
      }
      var now = new Date().toISOString();
      updates.forEach(function (u) { save(u[0], { verdict: u[1], notes: u[2], updated_utc: now }); });
      refreshAll();
      message("Imported " + updates.length + " row(s) with a verdict or notes" +
              (unknown ? "; skipped " + unknown + " row(s) whose episode id, task cell or " +
                         "seed is not in this package" : "") +
              (bad ? "; skipped " + bad + " row(s) with an unknown verdict" : "") + ".");
    };
    reader.onerror = function () { message("Could not read the file."); };
    reader.readAsText(file);
  }

  // ---- events -------------------------------------------------------------------------
  function setSkim(card, on) {
    card.classList.toggle("skim", on);
    var cb = card.querySelector(".skim-toggle");
    if (cb) cb.checked = on;
  }

  document.addEventListener("change", function (ev) {
    var t = ev.target;
    if (t.matches(".skim-toggle")) {
      setSkim(t.closest(".card"), t.checked);
    } else if (t.id === "skim-all") {
      cards().forEach(function (c) { setSkim(c, t.checked); });
    } else if (t.matches(".verdict input[type=radio]")) {
      commit(t.closest(".card"));
    } else if (t.matches(".findings textarea")) {
      var card = t.closest(".card");
      clearTimeout(timers[card.getAttribute("data-episode")]);
      timers[card.getAttribute("data-episode")] = null;
      commit(card);
    } else if (t.id === "import-file" && t.files && t.files[0]) {
      importCsv(t.files[0]);
      t.value = "";
    }
  });

  document.addEventListener("input", function (ev) {
    var t = ev.target;
    if (!t.matches(".findings textarea")) return;
    var card = t.closest(".card"), id = card.getAttribute("data-episode");
    clearTimeout(timers[id]);
    timers[id] = setTimeout(function () { timers[id] = null; commit(card); }, 400);
  });

  document.addEventListener("click", function (ev) {
    var b = ev.target.closest("[data-action]");
    if (!b) return;
    var action = b.getAttribute("data-action"), card = b.closest(".card");
    if (action === "export") {
      exportCsv();
    } else if (action === "import") {
      var input = document.getElementById("import-file");
      if (input) input.click();
    } else if (action === "expand-logs" || action === "collapse-logs") {
      card.querySelectorAll("details.filler").forEach(function (d) {
        d.open = action === "expand-logs";
      });
    } else if (action === "clear-verdict") {
      card.querySelectorAll(".verdict input[type=radio]").forEach(function (r) { r.checked = false; });
      commit(card);
    }
  });

  window.addEventListener("storage", function (ev) {
    if (ev.key === null || ev.key.indexOf(NS) === 0) refreshAll();
  });

  // Notes typed less than the debounce delay before the page closes are saved too.
  window.addEventListener("pagehide", function () {
    cards().forEach(function (card) {
      var id = card.getAttribute("data-episode");
      if (timers[id]) { clearTimeout(timers[id]); timers[id] = null; commit(card); }
    });
  });

  // Findings that only this page holds are lost when it closes: the browser asks first.
  window.addEventListener("beforeunload", function (ev) {
    if (Object.keys(unsaved).length) {
      ev.preventDefault();
      ev.returnValue = "";
    }
  });

  if (!probe()) showStorageWarning();
  refreshAll();
})();
