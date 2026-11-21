"use strict";
// forcekit web UI — plain JS, talks to the local API only.

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const noteName = (m) => NOTE_NAMES[m % 12] + (Math.floor(m / 12) - 2);
const BANKS = ["A", "B", "C", "D"];
const MAX_SYNTH = 128;
const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};
const q = (path) => encodeURIComponent(path);
const baseName = (path) => path.split("/").pop();

const state = {
  tree: null, expanded: new Set([""]), folder: null, files: [], visible: [], selected: -1,
  program: null, stem: null, bank: 0, pad: 0, saveTimer: null,
};
const player = $("player");

// ---------- helpers ----------
function status(msg, isError = false) {
  const s = $("status");
  s.textContent = msg || "";
  s.classList.toggle("error", isError);
}

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  let body = null;
  if (res.status !== 204) {
    try { body = await res.json(); } catch { body = null; }
  }
  return { ok: res.ok, status: res.status, body };
}

function play(path) {
  player.src = "/api/audio?path=" + q(path);
  player.play().catch(() => {});
}
player.addEventListener("error", () => status("Can't play this sample", true));

// ---------- program / drafts ----------
function stamp() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}-${p(d.getMinutes())}-${p(d.getSeconds())}`;
}

function newProgram(type) {
  state.program = type === "drum"
    ? { type: "drum", name: "Kit " + stamp(), pads: {} }
    : { type: "synth", name: "Synth " + stamp(), samples: [] };
  state.stem = null; state.bank = 0; state.pad = 0;
  renderProgram();
}

function scheduleSave() {
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(saveDraft, 800);
}

async function saveDraft() {
  const p = state.program;
  if (!p.name.trim()) return;
  const r = await api("/api/drafts/" + q(state.stem || p.name), {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p),
  });
  if (r.ok) {
    state.stem = r.body.stem;
    state.shownStem = r.body.stem;
    loadDraftList();
  } else {
    status("Couldn't save draft: " + (r.body && r.body.error), true);
  }
}

async function loadDraftList() {
  const r = await api("/api/drafts");
  const sel = $("drafts");
  sel.textContent = "";
  sel.append(new Option("Drafts…", ""));
  for (const d of r.body || []) {
    const o = new Option(`${d.type === "drum" ? "🥁" : "🎹"} ${d.name}`, d.stem);
    if (d.stem === state.stem) o.selected = true;
    sel.append(o);
  }
}

$("drafts").addEventListener("change", async (e) => {
  const stem = e.target.value;
  if (!stem) return;
  const r = await api("/api/drafts/" + q(stem));
  if (!r.ok) { status("Couldn't open draft", true); return; }
  state.program = r.body;
  if (state.program.type === "drum") state.program.pads = state.program.pads || {};
  else state.program.samples = state.program.samples || [];
  state.stem = stem; state.bank = 0; state.pad = 0;
  renderProgram();
  status("Opened " + r.body.name);
});

$("delete-draft").addEventListener("click", async () => {
  if (state.stem) await api("/api/drafts/" + q(state.stem), { method: "DELETE" });
  newProgram(state.program.type);
  loadDraftList();
  status("Draft deleted");
});

$("type-drum").addEventListener("click", () => { if (state.program.type !== "drum") newProgram("drum"); });
$("type-synth").addEventListener("click", () => { if (state.program.type !== "synth") newProgram("synth"); });
$("program-name").addEventListener("input", (e) => { state.program.name = e.target.value; scheduleSave(); });

// ---------- assigning ----------
async function assign(entry, target) {
  if (!entry || entry.error) return;
  const p = state.program;
  if (p.type === "drum") {
    const pad = target != null ? target : state.pad;
    p.pads[String(pad)] = entry.path;
    state.pad = Math.min(pad + 1, 63);
    state.bank = Math.floor(state.pad / 16);
    renderProgram();
    scheduleSave();
    return;
  }
  if (p.samples.length >= MAX_SYNTH) { status(`A synth holds at most ${MAX_SYNTH} samples`, true); return; }
  if (p.samples.some((s) => s.path === entry.path)) { status("Already in this synth"); return; }
  const r = await api("/api/root?path=" + q(entry.path));
  if (!r.ok) { status("Couldn't read the note", true); return; }
  let root = r.body.root;
  if (p.samples.some((s) => s.root === root)) {
    status(`${noteName(root)} is already used — pick another note for ${baseName(entry.path)}`, true);
    const used = new Set(p.samples.map((s) => s.root));
    let free = root;
    for (let d = 1; used.has(free) && d < 128; d++) {
      if (root + d <= 127 && !used.has(root + d)) free = root + d;
      else if (root - d >= 0 && !used.has(root - d)) free = root - d;
    }
    root = free;
  } else {
    const how = { filename: "from filename", detected: "detected", default: "unknown, set to C3" }[r.body.source];
    status(`${baseName(entry.path)}: ${noteName(root)} (${how})`);
  }
  p.samples.push({ path: entry.path, root });
  renderProgram();
  scheduleSave();
}

function keyRanges(roots) {
  return roots.map((r, i) => [
    i === 0 ? 0 : Math.floor((roots[i - 1] + r) / 2) + 1,
    i === roots.length - 1 ? 127 : Math.floor((r + roots[i + 1]) / 2),
  ]);
}

// ---------- rendering: program ----------
function renderProgram() {
  const p = state.program;
  if (state.shownStem !== (state.stem || p.name)) {  // switched program: drop stale export message
    state.shownStem = state.stem || p.name;
    $("export-result").textContent = "";
  }
  $("type-drum").classList.toggle("on", p.type === "drum");
  $("type-synth").classList.toggle("on", p.type === "synth");
  $("program-name").value = p.name;
  $("drum-panel").hidden = p.type !== "drum";
  $("synth-panel").hidden = p.type !== "synth";
  if (p.type === "drum") renderPads(); else renderSynth();
}

function renderPads() {
  const banks = $("banks");
  banks.textContent = "";
  BANKS.forEach((b, i) => {
    const used = Object.keys(state.program.pads).some((k) => Math.floor(+k / 16) === i);
    const btn = el("button", state.bank === i ? "on" : "", b + (used ? " •" : ""));
    btn.type = "button";
    btn.addEventListener("click", () => { state.bank = i; renderPads(); });
    banks.append(btn);
  });
  const grid = $("pads");
  grid.textContent = "";
  // Force/MPC layout: pad 1 bottom-left, pad 16 top-right.
  for (const row of [3, 2, 1, 0]) {
    for (let col = 0; col < 4; col++) {
      const idx = state.bank * 16 + row * 4 + col;
      const path = state.program.pads[String(idx)];
      const pad = el("div", "pad" + (path ? " filled" : "") + (idx === state.pad ? " selected" : ""));
      pad.append(el("span", "label", BANKS[state.bank] + String(row * 4 + col + 1).padStart(2, "0")));
      pad.append(el("span", "sample", path ? baseName(path).replace(/\.[^.]+$/, "") : ""));
      if (path) {
        pad.title = path;
        const x = el("button", "clear", "×");
        x.type = "button"; x.title = "Clear pad";
        x.addEventListener("click", (e) => {
          e.stopPropagation();
          delete state.program.pads[String(idx)];
          renderPads(); scheduleSave();
        });
        pad.append(x);
      }
      pad.addEventListener("click", () => { state.pad = idx; renderPads(); if (path) play(path); });
      pad.addEventListener("dragover", (e) => { e.preventDefault(); pad.classList.add("drop"); });
      pad.addEventListener("dragleave", () => pad.classList.remove("drop"));
      pad.addEventListener("drop", (e) => {
        e.preventDefault();
        pad.classList.remove("drop");
        const entry = state.files.find((f) => f.path === e.dataTransfer.getData("text/plain"));
        assign(entry, idx);
      });
      grid.append(pad);
    }
  }
}

function renderSynth() {
  const samples = state.program.samples;
  samples.sort((a, b) => a.root - b.root);
  const ranges = keyRanges(samples.map((s) => s.root));
  const map = $("keymap");
  map.textContent = "";
  ranges.forEach(([lo, hi]) => {
    const seg = el("span");
    seg.style.width = ((hi - lo + 1) / 128 * 100) + "%";
    map.append(seg);
  });
  const list = $("synth-list");
  list.textContent = "";
  if (!samples.length) list.append(el("p", "muted", "Add samples: double-click, Enter, or drag them here."));
  samples.forEach((s, i) => {
    const row = el("div", "synth-row");
    const sel = el("select");
    sel.setAttribute("aria-label", "Root note");
    for (let m = 0; m < 128; m++) sel.append(new Option(noteName(m), String(m), false, m === s.root));
    sel.addEventListener("change", () => {
      const m = +sel.value;
      if (samples.some((o, j) => j !== i && o.root === m)) {
        status(`${noteName(m)} is already used by another sample`, true);
        sel.value = String(s.root);
        return;
      }
      s.root = m; renderSynth(); scheduleSave();
    });
    const name = el("span", "name", baseName(s.path));
    name.title = s.path;
    name.addEventListener("click", () => play(s.path));
    const [lo, hi] = ranges[i];
    const x = el("button", "clear", "×");
    x.type = "button"; x.title = "Remove";
    x.addEventListener("click", () => { samples.splice(i, 1); renderSynth(); scheduleSave(); });
    row.append(sel, name, el("span", "range", `${noteName(lo)}–${noteName(hi)}`), x);
    list.append(row);
  });
}

const synthList = $("synth-list");
synthList.addEventListener("dragover", (e) => { e.preventDefault(); synthList.classList.add("drop"); });
synthList.addEventListener("dragleave", () => synthList.classList.remove("drop"));
synthList.addEventListener("drop", (e) => {
  e.preventDefault();
  synthList.classList.remove("drop");
  assign(state.files.find((f) => f.path === e.dataTransfer.getData("text/plain")));
});

// ---------- export ----------
async function doExport(overwrite = false) {
  const r = await api("/api/export", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ draft: state.program, normalize: $("normalize").checked, overwrite }),
  });
  const area = $("export-area");
  const result = $("export-result");
  if (r.status === 409) {
    area.textContent = "";
    area.append(el("span", "small", "Already exported. "));
    const yes = el("button", "primary", "Overwrite"); yes.type = "button";
    const no = el("button", "", "Cancel"); no.type = "button";
    yes.addEventListener("click", () => { resetExportButton(); doExport(true); });
    no.addEventListener("click", resetExportButton);
    area.append(yes, " ", no);
    result.textContent = r.body.path;
    return;
  }
  resetExportButton();
  if (r.ok) { result.textContent = "Exported to " + r.body.path; status("Exported"); }
  else { result.textContent = ""; status("Export failed: " + ((r.body && r.body.error) || r.status), true); }
}

function resetExportButton() {
  const area = $("export-area");
  area.textContent = "";
  const b = el("button", "primary", "Export");
  b.id = "export"; b.type = "button";
  b.addEventListener("click", () => doExport(false));
  area.append(b);
}

// ---------- tree ----------
function renderTree() {
  const box = $("tree");
  box.textContent = "";
  const filter = $("tree-filter").value.trim().toLowerCase();
  if (filter) {
    const hits = [];
    (function walk(n) {
      if (n.path && n.path.toLowerCase().includes(filter)) hits.push(n);
      n.children.forEach(walk);
    })(state.tree);
    hits.slice(0, 500).forEach((n) => box.append(treeRow(n, 0, n.path)));
    if (!hits.length) box.append(el("p", "muted small", " No folders match."));
    return;
  }
  (function walk(n, depth) {
    box.append(treeRow(n, depth, depth === 0 ? n.name : n.name));
    if (state.expanded.has(n.path)) n.children.forEach((c) => walk(c, depth + 1));
  })(state.tree, 0);
}

function treeRow(node, depth, label) {
  const row = el("div", "tree-item" + (node.path === state.folder ? " active" : ""));
  row.style.paddingLeft = 6 + depth * 14 + "px";
  const open = state.expanded.has(node.path);
  row.append(el("span", "twisty", node.children.length ? (open ? "▾" : "▸") : ""));
  row.append(el("span", "", label));
  if (node.count) row.append(el("span", "count", String(node.count)));
  row.title = node.path || node.name;
  row.addEventListener("click", () => {
    if (node.children.length) {
      if (open && state.folder === node.path) state.expanded.delete(node.path); else state.expanded.add(node.path);
    }
    openFolder(node.path);
  });
  return row;
}

async function openFolder(path) {
  state.folder = path;
  renderTree();
  const r = await api("/api/folder?path=" + q(path));
  state.files = r.body || [];
  state.selected = -1;
  $("folder-title").textContent = (path || "(top level)") + ` — ${state.files.length} samples`;
  renderFiles();
}

// ---------- files ----------
function renderFiles() {
  const text = $("file-filter").value.trim().toLowerCase();
  const hint = $("hint-filter").value;
  state.visible = state.files.filter((f) =>
    (!text || baseName(f.path).toLowerCase().includes(text)) && (!hint || f.type_hint === hint));
  const box = $("files");
  box.textContent = "";
  state.visible.forEach((f, i) => {
    const row = el("div", "file" + (f.error ? " broken" : "") + (i === state.selected ? " selected" : ""));
    const name = el("span", "name", baseName(f.path));
    if (f.dup_of) { name.append(el("span", "dup", "dup")); row.title = "Duplicate of " + f.dup_of; }
    if (f.error) row.title = f.error;
    row.append(name,
      el("span", "meta", f.duration != null ? f.duration.toFixed(2) + "s" : "—"),
      el("span", "meta", f.type_hint || ""),
      el("span", "meta", f.note != null ? noteName(f.note) : ""));
    row.draggable = !f.error;
    row.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/plain", f.path));
    row.addEventListener("click", () => select(i));
    row.addEventListener("dblclick", () => assign(f));
    box.append(row);
  });
  if (!state.visible.length) box.append(el("p", "muted small", " Nothing here."));
}

function select(i) {
  if (i < 0 || i >= state.visible.length) return;
  state.selected = i;
  const rows = $("files").children;
  for (const r of rows) r.classList.remove("selected");
  rows[i].classList.add("selected");
  rows[i].scrollIntoView({ block: "nearest" });
  const f = state.visible[i];
  if (f.error) { status(f.error, true); return; }
  status("");
  play(f.path);
}

document.addEventListener("keydown", (e) => {
  const tag = e.target.tagName;
  if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
  if (e.key === "ArrowDown") { e.preventDefault(); select(Math.min(state.selected + 1, state.visible.length - 1)); }
  else if (e.key === "ArrowUp") { e.preventDefault(); select(Math.max(state.selected - 1, 0)); }
  else if (e.key === " ") {
    e.preventDefault();
    if (player.src) { player.currentTime = 0; player.play().catch(() => {}); }
  } else if (e.key === "Enter" && state.selected >= 0) { e.preventDefault(); assign(state.visible[state.selected]); }
});

$("tree-filter").addEventListener("input", renderTree);
$("file-filter").addEventListener("input", () => { state.selected = -1; renderFiles(); });
$("hint-filter").addEventListener("change", () => { state.selected = -1; renderFiles(); });

// ---------- start ----------
(async function init() {
  for (const h of ["kick", "snare", "clap", "hat", "tom", "cymbal", "perc", "fx", "vocal", "bass", "synth", "pad", "loop"]) {
    $("hint-filter").append(new Option(h, h));
  }
  resetExportButton();
  newProgram("drum");
  loadDraftList();
  const r = await api("/api/tree");
  state.tree = r.body;
  renderTree();
  openFolder("");
})();
