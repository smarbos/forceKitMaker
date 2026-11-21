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
  program: null, stem: null, pad: 0, kbOctave: 3, kbShown: null, saveTimer: null, folderSeq: 0,
  layout: { colors: {}, default: "#3cff5a", max_one_shot: 4 },
  hints: new Map(),
  padNames: {}, padNamesSig: null,  // short auto names for the current pads  // library path → type hint (null = untyped); filled from listings and /api/hints
};
const store = {  // per-browser conveniences; storage can be unavailable
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
};
const player = $("player");

// ---------- helpers ----------
function status(msg, isError = false) {
  const s = $("status");
  s.textContent = msg || "";
  s.classList.toggle("error", isError);
}

async function api(path, opts = {}) {
  let res;
  try { res = await fetch(path, opts); } catch {
    return { ok: false, status: 0, body: { error: "forcekit server not reachable" } };
  }
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
  state.stem = null; state.pad = 0;
  renderProgram();
}

function scheduleSave() {
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(saveDraft, 800);
}

// Save now if an autosave is pending — call before leaving the current program.
async function flushSave() {
  if (state.saveTimer) await saveDraft();
}

async function saveDraft() {
  clearTimeout(state.saveTimer);
  state.saveTimer = null;
  const p = state.program;
  if (!p.name.trim()) return;
  // An empty stem means "new draft"; the server refuses to overwrite another draft.
  const r = await api("/api/drafts/" + q(state.stem || ""), {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p),
  });
  if (p !== state.program) return;  // user moved on while saving
  if (r.status === 409) {
    status(`A draft named "${r.body.stem}" already exists — give this one another name`, true);
    return;
  }
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
  await flushSave();
  const r = await api("/api/drafts/" + q(stem));
  if (!r.ok) { status("Couldn't open draft", true); return; }
  state.program = r.body;
  if (state.program.type === "drum") state.program.pads = state.program.pads || {};
  else state.program.samples = state.program.samples || [];
  state.stem = stem; state.pad = 0;
  renderProgram();
  status("Opened " + r.body.name);
});

$("delete-draft").addEventListener("click", async () => {
  clearTimeout(state.saveTimer);
  state.saveTimer = null;
  if (state.stem) await api("/api/drafts/" + q(state.stem), { method: "DELETE" });
  newProgram(state.program.type);
  loadDraftList();
  status("Draft deleted");
});

$("new-program").addEventListener("click", async () => {
  await flushSave();
  newProgram(state.program.type);
  await saveDraft();  // saved right away so it shows in the drafts list
  status("New " + (state.program.type === "drum" ? "kit" : "synth") + " created: " + state.program.name);
});

$("type-drum").addEventListener("click", async () => {
  if (state.program.type !== "drum") { await flushSave(); newProgram("drum"); }
});
$("type-synth").addEventListener("click", async () => {
  if (state.program.type !== "synth") { await flushSave(); newProgram("synth"); }
});
$("program-name").addEventListener("input", (e) => { state.program.name = e.target.value; scheduleSave(); });

// ---------- assigning ----------
async function assign(entry, target) {
  if (!entry || entry.error) return;
  const p = state.program;
  if (p.type === "drum") {
    const pad = target != null ? target : state.pad;
    p.pads[String(pad)] = entry.path;
    delete customNames()[String(pad)];  // a custom name described the old sound; a picked color stays
    state.pad = Math.min(pad + 1, 63);
    renderProgram();
    flashPad(pad);
    scheduleSave();
    return;
  }
  if (p.samples.length >= MAX_SYNTH) { status(`A synth holds at most ${MAX_SYNTH} samples`, true); return; }
  if (p.samples.some((s) => s.path === entry.path)) { status("Already in this synth"); return; }
  const r = await api("/api/root?path=" + q(entry.path));
  if (p !== state.program) return;  // switched program while the note was being detected
  if (!r.ok) { status("Couldn't read the note", true); return; }
  if (p.samples.some((s) => s.path === entry.path)) return;  // added twice in quick succession
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
    resetExportButton();  // a pending "Overwrite?"/"Replace?" belongs to the previous program
    resetSendButton();
  }
  $("type-drum").classList.toggle("on", p.type === "drum");
  $("type-synth").classList.toggle("on", p.type === "synth");
  $("program-name").value = p.name;
  $("drum-panel").hidden = p.type !== "drum";
  $("synth-panel").hidden = p.type !== "synth";
  if (p.type === "drum") renderPads(); else renderSynth();
}

function padColor(idx, path) {
  const custom = (state.program.colors || {})[String(idx)];
  if (custom) return custom;
  const hint = state.hints.get(path);
  return (hint && state.layout.colors[hint]) || state.layout.default;
}

// Colors offered for a pad: the type colors plus a few extras (all strong enough for the pad LEDs).
const SWATCHES = ["#ff0000", "#ff4000", "#ff8800", "#ffd21a", "#9dff1a", "#3cff5a", "#00ffaa",
                  "#1ad8ff", "#3a6bff", "#a64dff", "#ff4dc4", "#f0f0f0"];

const customNames = () => (state.program.names = state.program.names || {});
const customColors = () => (state.program.colors = state.program.colors || {});

// What the Force will show on a pad: the custom name, else the short auto name.
function padName(idx, path) {
  return customNames()[String(idx)] || state.padNames[String(idx)] || baseName(path).replace(/\.[^.]+$/, "");
}

// The selected pad, spelled out under the grid, with its actions.
function renderPadInfo() {
  const box = $("pad-info");
  box.textContent = "";
  const idx = state.pad;
  const key = String(idx);
  const path = state.program.pads[key];
  const hint = path ? state.hints.get(path) : null;
  const line = el("div", "info-line");
  line.append(el("strong", "", padLabel(idx)));
  line.append(el("span", "muted", path ? ` · ${hint || "untyped"} · ` : " · empty — double-click, Enter or drag a sample here"));
  box.append(line);
  if (!path) return;
  const file = el("span", "info-name", baseName(path));
  file.title = path;
  line.append(file);
  const actions = el("span", "info-actions");
  for (const [label, fn, tip] of [
    ["◀", () => stepPad(-1), "Previous sound of this type ([)"],
    ["▶", () => stepPad(1), "Next sound of this type (])"],
    ["Clear", () => {
      delete state.program.pads[key]; delete customNames()[key]; delete customColors()[key];
      renderPads(); scheduleSave();
    }, "Remove the sample from this pad"],
  ]) {
    const b = el("button", "", label);
    b.type = "button"; b.title = tip;
    b.addEventListener("click", fn);
    actions.append(b);
  }
  line.append(actions);

  const edit = el("div", "info-edit");
  const name = el("input");
  name.id = "pad-name"; name.type = "text"; name.maxLength = 64; name.spellcheck = false;
  name.placeholder = state.padNames[key] || baseName(path).replace(/\.[^.]+$/, "");
  name.value = customNames()[key] || "";
  name.title = "Name shown on the Force (empty = automatic short name)";
  name.setAttribute("aria-label", "Pad name");
  name.addEventListener("change", () => {
    const v = name.value.trim();
    if (v) customNames()[key] = v; else delete customNames()[key];
    renderPads(); scheduleSave();
  });
  name.addEventListener("keydown", (e) => { if (e.key === "Enter") name.blur(); });
  edit.append(name);
  const sw = el("span", "swatches");
  const current = customColors()[key];
  const setColor = (c) => {
    if (c) customColors()[key] = c; else delete customColors()[key];
    renderPads(); scheduleSave();
  };
  for (const c of SWATCHES) {
    const b = el("button", "swatch" + (current === c ? " on" : ""));
    b.type = "button"; b.dataset.color = c; b.title = c; b.style.background = c;
    b.addEventListener("click", () => setColor(c));
    sw.append(b);
  }
  const pick = el("input");
  pick.type = "color"; pick.id = "pad-color-custom"; pick.title = "Any color";
  pick.value = current || padColor(idx, path);
  pick.addEventListener("change", () => setColor(pick.value.toLowerCase()));
  const auto = el("button", current ? "" : "on", "Auto");
  auto.type = "button"; auto.id = "pad-color-auto"; auto.title = "Use the sound type's color";
  auto.addEventListener("click", () => setColor(null));
  sw.append(pick, auto);
  edit.append(sw);
  box.append(edit);
}

// Short auto names come from the server (the same rule the export uses).
async function ensurePadNames() {
  const p = state.program;
  if (!p || p.type !== "drum") return;
  const sig = JSON.stringify(p.pads);
  if (sig === state.padNamesSig) return;
  state.padNamesSig = sig;
  const r = await api("/api/padnames", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pads: p.pads }),
  });
  if (p !== state.program || sig !== state.padNamesSig) return;  // changed meanwhile
  if (!r.ok) { state.padNamesSig = null; return; }
  state.padNames = r.body;
  renderPads();
}

// Look up type hints for pad samples we haven't seen in a listing (e.g. after opening a draft).
let hintsPending = false;
async function ensureHints() {
  if (hintsPending || !state.program || state.program.type !== "drum") return;
  const missing = Object.values(state.program.pads).filter((p) => !state.hints.has(p));
  if (!missing.length) return;
  hintsPending = true;
  const r = await api("/api/hints", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ paths: missing }),
  });
  hintsPending = false;
  for (const p of missing) state.hints.set(p, r.ok && p in r.body ? r.body[p] : null);
  if (state.program.type === "drum") renderPads();
}

// Swap the selected pad's sample for the next/previous one of the same type in its folder.
async function stepPad(dir) {
  const p = state.program;
  if (p.type !== "drum") return;
  const idx = state.pad;
  const path = p.pads[String(idx)];
  if (!path) { status("Select a pad that has a sample"); return; }
  const folder = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";
  const r = await api("/api/folder?path=" + q(folder));
  if (p !== state.program || p.pads[String(idx)] !== path) return;  // changed meanwhile
  const entries = (r.body || []).filter((f) => !f.error);
  entries.forEach((f) => state.hints.set(f.path, f.type_hint));
  const me = entries.find((f) => f.path === path);
  if (!me) { status("This sample is no longer in the library index", true); return; }
  const pool = entries.filter((f) => !me.type_hint || f.type_hint === me.type_hint);
  if (pool.length < 2) { status(`No other ${me.type_hint || "sample"} in this folder`); return; }
  const next = pool[(pool.indexOf(me) + dir + pool.length) % pool.length];
  p.pads[String(idx)] = next.path;
  delete customNames()[String(idx)];
  renderPads();
  play(next.path);
  flashPad(idx);
  status(`${BANKS[Math.floor(idx / 16)]}${String(idx % 16 + 1).padStart(2, "0")}: ${baseName(next.path)}`);
  scheduleSave();
}

// New kit from the open folder (and subfolders) in the standard layout; never touches the open kit.
async function autofillKit() {
  if (state.folder == null) return;
  await flushSave();
  const folder = state.folder;
  const r = await api("/api/autofill", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder, one_shots: $("one-shots").checked }),
  });
  if (!r.ok) { status("Auto-fill failed: " + (r.body && r.body.error), true); return; }
  const pads = r.body.pads;
  const count = Object.keys(pads).length;
  if (!count) { status("Nothing to fill from this folder", true); return; }
  const missing = Object.values(pads).filter((p) => !state.hints.has(p));
  if (missing.length) {
    const h = await api("/api/hints", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ paths: missing }),
    });
    for (const p of missing) state.hints.set(p, h.ok && p in h.body ? h.body[p] : null);
  }
  const base = r.body.name;  // server picks a free, length-safe name
  const program = { type: "drum", name: base, pads };
  for (let n = 2; ; n++) {  // find a free draft name: "808", "808 2", "808 3"…
    const s = await api("/api/drafts/", {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(program),
    });
    if (s.ok) { state.stem = s.body.stem; break; }
    if (s.status !== 409 || n > 200) { status("Couldn't save the new kit: " + (s.body && s.body.error), true); return; }
    program.name = `${base} ${n}`;
  }
  state.program = program;
  state.pad = 0;
  renderProgram();
  loadDraftList();
  status(`Auto-filled ${count} pads from ${folder || "the whole library"}`);
}
$("autofill").addEventListener("click", autofillKit);

// The Force's 8×8 grid: bank A bottom-left, B bottom-right, C top-left, D top-right;
// within each bank pad 1 is bottom-left and pad 16 top-right.
const padLabel = (idx) => BANKS[Math.floor(idx / 16)] + String(idx % 16 + 1).padStart(2, "0");

function renderPads() {
  const grid = $("pads");
  grid.textContent = "";
  for (let r = 0; r < 8; r++) {        // r = 0 is the top row
    for (let c = 0; c < 8; c++) {
      const bank = (r < 4 ? 2 : 0) + (c < 4 ? 0 : 1);  // C D over A B
      const idx = bank * 16 + (3 - (r % 4)) * 4 + (c % 4);
      const path = state.program.pads[String(idx)];
      const pad = el("div", "pad" + (path ? " filled" : "") + (idx === state.pad ? " selected" : ""));
      pad.dataset.idx = idx;
      pad.style.gridColumn = String(c < 4 ? c + 1 : c + 2);  // column/row 5 is the gap between banks
      pad.style.gridRow = String(r < 4 ? r + 1 : r + 2);
      if (path) pad.style.setProperty("--pad-color", padColor(idx, path));
      pad.append(el("span", "label", padLabel(idx)));
      pad.append(el("span", "sample", path ? padName(idx, path) : ""));
      if (path) pad.title = `${padLabel(idx)} · ${path}`;
      pad.addEventListener("click", () => { state.pad = idx; renderPads(); if (path) { play(path); flashPad(idx); } });
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
  renderPadInfo();
  ensureHints();
  ensurePadNames();
}

// Light a pad up briefly, like hitting it on the device.
function flashPad(idx) {
  const pad = $("pads").querySelector(`[data-idx="${idx}"]`);
  if (!pad) return;
  pad.classList.add("hit");
  setTimeout(() => pad.classList.remove("hit"), 160);
}

// ---------- synth: sections, keyboard, pitched playback ----------
const SECTION_COLORS = ["#ff6a1a", "#1ad8ff", "#9dff1a", "#ff4dc4", "#ffd21a", "#a64dff", "#3a6bff", "#f0f0f0"];
const WHITE_W = 18, BLACK_W = 12;
const KEY_OFFSETS = { a: 0, w: 1, s: 2, e: 3, d: 4, f: 5, t: 6, g: 7, y: 8, h: 9, u: 10, j: 11, k: 12 };
const isBlack = (n) => [1, 3, 6, 8, 10].includes(n % 12);
const whitesBefore = (n) => { let c = 0; for (let m = 0; m < n; m++) if (!isBlack(m)) c++; return c; };
const noteLeft = (n) => whitesBefore(n) * WHITE_W - (isBlack(n) ? BLACK_W / 2 : 0);
const noteRight = (n) => isBlack(n) ? whitesBefore(n) * WHITE_W + BLACK_W / 2 : (whitesBefore(n) + 1) * WHITE_W;
const sectionColor = (i) => SECTION_COLORS[i % SECTION_COLORS.length];
const isManual = (samples) => samples.length > 0 && "low" in samples[0];

// [low, high] of each sample (samples already in display order): hand-set, else the automatic split
function sections(samples) {
  return isManual(samples) ? samples.map((s) => [s.low, s.high]) : keyRanges(samples.map((s) => s.root));
}

function sampleForNote(note) {
  const samples = state.program.samples;
  const i = sections(samples).findIndex(([lo, hi]) => lo <= note && note <= hi);
  return i < 0 ? null : samples[i];
}

let audioCtx = null;
const buffers = new Map();  // path → Promise<AudioBuffer>
function playNote(note) {
  const s = sampleForNote(note);
  flashKey(note);
  if (!s) return;
  const rate = Math.pow(2, (note - s.root) / 12);
  window.__lastPlay = { path: s.path, rate, note };
  audioCtx = audioCtx || new AudioContext();
  if (!buffers.has(s.path)) {
    buffers.set(s.path, fetch("/api/audio?path=" + q(s.path))
      .then((r) => { if (!r.ok) throw new Error(r.status); return r.arrayBuffer(); })
      .then((b) => audioCtx.decodeAudioData(b))
      .catch((e) => { buffers.delete(s.path); throw e; }));
  }
  buffers.get(s.path).then((buf) => {
    const src = audioCtx.createBufferSource();
    src.buffer = buf; src.playbackRate.value = rate;
    src.connect(audioCtx.destination); src.start();
  }).catch(() => status("Can't play " + baseName(s.path), true));
}

function flashKey(note) {
  const k = $("keys").querySelector(`[data-note="${note}"]`);
  if (!k) return;
  k.classList.add("down");
  setTimeout(() => k.classList.remove("down"), 160);
}

function renderKeyboard(samples, ranges) {
  const keys = $("keys"), bands = $("bands");
  keys.textContent = ""; bands.textContent = "";
  const width = whitesBefore(128) * WHITE_W;
  keys.style.width = bands.style.width = width + "px";
  const base = (state.kbOctave + 2) * 12;
  const roots = new Map(samples.map((s, i) => [s.root, i]));
  for (let n = 0; n < 128; n++) {
    const k = el("div", "key " + (isBlack(n) ? "black" : "white"));
    k.dataset.note = n;
    k.title = noteName(n);
    k.style.left = noteLeft(n) + "px";
    if (!ranges.some(([lo, hi]) => lo <= n && n <= hi)) k.classList.add("off");
    if (n >= base && n <= base + 12) k.classList.add("kb-range");
    if (n % 12 === 0) k.append(el("span", "cname", noteName(n)));
    if (roots.has(n)) {
      const dot = el("span", "root-mark");
      dot.style.background = sectionColor(roots.get(n));
      dot.title = "Root of " + baseName(samples[roots.get(n)].path);
      k.append(dot);
    }
    k.addEventListener("pointerdown", (e) => { e.preventDefault(); playNote(n); });
    keys.append(k);
  }
  ranges.forEach(([lo, hi], i) => {
    const b = el("div", "band");
    b.append(el("span", "label", baseName(samples[i].path)));
    b.dataset.idx = i;
    b.style.left = noteLeft(lo) + "px";
    b.style.width = (noteRight(hi) - noteLeft(lo)) + "px";
    b.style.background = sectionColor(i);
    b.title = `${baseName(samples[i].path)}: ${noteName(lo)}–${noteName(hi)}`;
    bands.append(b);
  });
  $("kb-octave").textContent = `Keys: ${noteName(base)}–${noteName(Math.min(base + 12, 127))}`;
  $("auto-split").hidden = !isManual(samples);
  const shown = state.stem || state.program.name;
  if (state.kbShown !== shown) {  // new program: start the view at C1
    state.kbShown = shown;
    $("keyboard").scrollLeft = noteLeft(36);
  }
}

function renderSynth() {
  const samples = state.program.samples;
  const manual = isManual(samples);
  samples.sort((a, b) => manual ? a.low - b.low : a.root - b.root);
  const ranges = sections(samples);
  renderKeyboard(samples, ranges);
  const list = $("synth-list");
  list.textContent = "";
  if (!samples.length) list.append(el("p", "muted", "Add samples: double-click, Enter, or drag them here."));
  samples.forEach((s, i) => {
    const row = el("div", "synth-row");
    row.style.borderLeftColor = sectionColor(i);
    const sel = el("select");
    sel.setAttribute("aria-label", "Root note");
    for (let m = 0; m < 128; m++) sel.append(new Option(noteName(m), String(m), false, m === s.root));
    sel.addEventListener("change", () => {
      const m = +sel.value;
      if (!manual && samples.some((o, j) => j !== i && o.root === m)) {
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

// ---------- send to Force ----------
async function doSend(overwrite = false, program = null) {
  const p = program || state.program;  // Replace sends the program that was asked about
  const area = $("send-area");
  area.textContent = "";
  area.append(el("span", "small", "Sending…"));
  status("Exporting and sending to the Force…");
  const r = await api("/api/send", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ draft: p, normalize: $("normalize").checked, overwrite }),
  });
  if (r.status === 409 && r.body && r.body.exists) {
    area.textContent = "";
    area.append(el("span", "small", "Already on the Force. "));
    const yes = el("button", "primary", "Replace"); yes.type = "button"; yes.id = "send-replace";
    const no = el("button", "", "Cancel"); no.type = "button";
    yes.addEventListener("click", () => doSend(true, p));
    no.addEventListener("click", () => { resetSendButton(); status(""); });
    area.append(yes, " ", no);
    status(`"${p.name}" is already on the Force`);
    return;
  }
  if (p !== state.program) { if (r.ok) status(`Sent "${p.name}" to the Force`); return; }
  resetSendButton();
  if (r.ok) {
    $("export-result").textContent = `On the Force (${r.body.host}): ${r.body.path}`;
    status(`Sent "${p.name}" to the Force`);
  } else {
    status("Send to Force failed: " + ((r.body && r.body.error) || r.status), true);
  }
}

function resetSendButton() {
  const area = $("send-area");
  area.textContent = "";
  const b = el("button", "primary", "Send to Force");
  b.id = "send"; b.type = "button";
  b.addEventListener("click", () => doSend(false));
  area.append(b);
}

// ---------- settings ----------
function settingsResult(msg, kind) {
  const r = $("settings-result");
  r.textContent = msg;
  r.className = "small " + (kind || "");
}

async function openSettings() {
  const panel = $("settings");
  if (!panel.hidden) { panel.hidden = true; return; }
  const r = await api("/api/settings");
  if (r.ok) {
    $("force-host").value = r.body.force_host;
    $("force-user").value = r.body.force_user;
    $("force-dir").value = r.body.force_dir;
  }
  settingsResult("");
  panel.hidden = false;
  $("force-host").focus();
}

async function saveSettings() {
  const r = await api("/api/settings", {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force_host: $("force-host").value, force_user: $("force-user").value,
                           force_dir: $("force-dir").value }),
  });
  if (r.ok) settingsResult("Saved", "ok");
  else settingsResult((r.body && r.body.error) || "Couldn't save", "error");
  return r.ok;
}

async function testSettings() {
  if (!(await saveSettings())) return;  // test what's in the fields
  settingsResult("Connecting…");
  const r = await api("/api/settings/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  if (r.ok) settingsResult("OK — connected. Free space: " + r.body.info, "ok");
  else settingsResult((r.body && r.body.error) || "Connection failed", "error");
}

$("settings-open").addEventListener("click", openSettings);
$("settings-close").addEventListener("click", () => { $("settings").hidden = true; });
$("settings-save").addEventListener("click", saveSettings);
$("settings-test").addEventListener("click", testSettings);

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
  const seq = ++state.folderSeq;
  const r = await api("/api/folder?path=" + q(path));
  if (seq !== state.folderSeq) return;  // a newer folder was clicked meanwhile
  state.files = r.body || [];
  state.files.forEach((f) => state.hints.set(f.path, f.type_hint));
  state.selected = -1;
  $("folder-title").textContent = (path || "(top level)") + ` — ${state.files.length} samples`;
  renderFiles();
}

// ---------- files ----------
function renderFiles() {
  const text = $("file-filter").value.trim().toLowerCase();
  const hint = $("hint-filter").value;
  const oneShots = $("one-shots").checked;
  const isOneShot = (f) => f.type_hint !== "loop" && (f.duration == null || f.duration <= state.layout.max_one_shot);
  state.visible = state.files.filter((f) =>
    (!text || baseName(f.path).toLowerCase().includes(text)) && (!hint || f.type_hint === hint)
    && (!oneShots || isOneShot(f)));
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
  else if (e.key === "]" || e.key === "[") { e.preventDefault(); stepPad(e.key === "]" ? 1 : -1); }
  else if (state.program && state.program.type === "synth" && !e.ctrlKey && !e.metaKey && !e.altKey) {
    const key = e.key.toLowerCase();
    if (key === "z" || key === "x") {
      state.kbOctave = Math.max(-2, Math.min(7, state.kbOctave + (key === "x" ? 1 : -1)));
      renderSynth();
    } else if (key in KEY_OFFSETS && !e.repeat) {
      const note = (state.kbOctave + 2) * 12 + KEY_OFFSETS[key];
      if (note <= 127) playNote(note);
    }
  }
});

$("tree-filter").addEventListener("input", renderTree);
$("file-filter").addEventListener("input", () => { state.selected = -1; renderFiles(); });
$("hint-filter").addEventListener("change", () => { state.selected = -1; renderFiles(); });
$("one-shots").addEventListener("change", () => {
  store.set("forcekit.oneShots", $("one-shots").checked ? "1" : "0");
  state.selected = -1; renderFiles();
});

// ---------- start ----------
(async function init() {
  for (const h of ["kick", "snare", "clap", "hat", "tom", "cymbal", "perc", "fx", "vocal", "bass", "synth", "pad", "loop"]) {
    $("hint-filter").append(new Option(h, h));
  }
  $("one-shots").checked = store.get("forcekit.oneShots") === "1";
  const lay = await api("/api/layout");
  if (lay.ok) state.layout = lay.body;
  resetExportButton();
  resetSendButton();
  newProgram("drum");
  loadDraftList();
  const r = await api("/api/tree");
  state.tree = r.body;
  renderTree();
  openFolder("");
})();
