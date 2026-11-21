# Synth keyboard and manual sections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An on-screen keyboard that plays a synth pitched like the Force, with sections set by dragging split points, carried into the export.

**Architecture:** Synth draft samples gain optional `low`/`high`; validation and export honour them (else the automatic midpoint split). The page renders a scrollable 128-key keyboard with colored section bands, plays notes with Web Audio at `2^((note−root)/12)`, and edits sections by dragging band edges.

**Tech Stack:** Python stdlib server + pytest; vanilla JS/CSS; Playwright + Firefox (scratch venv) for browser checks.

**Spec:** `docs/superpowers/specs/2026-11-21-synth-keyboard-design.md`

## Global Constraints

- Notes 0–127; names as today (`noteName`, C3 = 60).
- All synth samples have `low` and `high`, or none do. None = automatic split (`key_ranges` / `keyRanges`), unchanged behaviour.
- Manual sections: `0 ≤ low ≤ high ≤ 127`, no overlap; shared roots allowed only when manual.
- Drags snap to C (multiples of 12); Shift = single keys; a section is at least 1 key.
- Never modify the sample library.

## Review Focus

1. A legacy synth draft (no low/high) loads, renders and exports exactly as before — export test pins `(0,64,60),(65,127,69)` (already exists, must stay green).
2. Two manual sections sharing a root export both samples (export must not key samples by root) — Task 2 test.
3. Mixed drafts (some samples with low/high, some without) are rejected, not silently half-applied — Task 1 test.
4. Dragging a split past a neighbour's far edge never produces an empty or overlapping section — Task 4 browser check drags beyond the neighbour.
5. Computer-key playing doesn't fire while typing in the program name or search box — Task 3 browser check types into `#program-name`.

---

### Task 1: Draft validation for manual sections

**Files:** Modify `forcekit/drafts.py` (synth branch of `validate_draft`); Test `tests/test_drafts.py`

**Interfaces:** Produces: a valid synth draft may have `low:int`, `high:int` on every sample.

- [ ] **Step 1: Failing tests** in `tests/test_drafts.py`:
  - `test_synth_manual_sections_valid`: samples `[{path a, root 48, low 36, high 59}, {path b, root 48, low 60, high 83}]` → `validate_draft` passes (shared root OK).
  - `test_synth_sections_all_or_none`: one sample with low/high, one without → `DraftError`.
  - `test_synth_sections_bad`: each of `low 60 high 59`; `low -1`; `high 128`; `low` as `"36"`; two sections `36–60` and `60–83` (overlap) → `DraftError`.
  - Existing `two samples share root note` rejection still holds when no low/high.
- [ ] **Step 2:** `.venv/bin/pytest tests/test_drafts.py -q` → new tests FAIL.
- [ ] **Step 3:** Implement: ints in range, low ≤ high, sorted by low each `low > previous high`; unique-root check only when no sections.
- [ ] **Step 4:** `.venv/bin/pytest -q` → all pass.
- [ ] **Step 5:** Commit `feat: allow manual key sections in synth drafts`.

### Task 2: Export uses manual sections

**Files:** Modify `forcekit/export.py` (synth items/zones), `forcekit/xpm.py` (`build_keygroup` sorts by low); Test `tests/test_export.py`

**Interfaces:** Consumes Task 1. `build_keygroup(name, zones)` unchanged signature; instruments ordered by `low`.

- [ ] **Step 1: Failing test** `test_export_synth_manual_sections`: draft `Split` with `Synth/Lead_C3.wav` root 60 low 36 high 59 and `Synth/Lead_A3.aif` root 60 low 60 high 83 → instruments `(lowNote, highNote, rootNote)` == `[(36,59,60),(60,83,60)]`, sample files of layers == `["Lead_C3.wav","Lead_A3.wav"]`, and both files exist in `Synths/Split/Split_[ProgramData]`.
- [ ] **Step 2:** Run → FAIL (shared root collapses / ranges ignored).
- [ ] **Step 3:** Key synth items by position (sorted by low when manual, else by root), zones from draft low/high when present else `key_ranges(roots)`; `build_keygroup` sorts zones by `low`.
- [ ] **Step 4:** `.venv/bin/pytest -q` → all pass (including `test_export_synth_shared_gain`).
- [ ] **Step 5:** Commit `feat: export synth key sections`.

### Task 3: On-screen keyboard that plays pitched

**Files:** Modify `forcekit/web/index.html` (replace `#keymap` with `#keyboard` container + octave label + `#auto-split` button), `forcekit/web/app.js`, `forcekit/web/style.css`; browser check `scratchpad/kb-ui.py`

**Interfaces:** Produces in app.js: `sections(samples) -> [[lo,hi],...]` (manual or `keyRanges`), `sampleForNote(note) -> sample|null`, `playNote(note)` (Web Audio, decoded buffers cached by path from `/api/audio`), `state.kbOctave` (default 3 → computer keys start at C3), `SECTION_COLORS` (8 distinct colors, by sample index), `renderKeyboard()` called from `renderSynth()`.

- [ ] **Step 1: Browser check first** (`kb-ui.py` on fresh scratch server, synth with two samples): asserts 128 `.key` elements, 75 white; band count == samples; clicking key for C3 calls playNote with rate 1 for a sample rooted at C3 and rate 2 at C4 (instrument via `window.__lastPlay = {path, rate}` set in `playNote`); pressing `a` plays C3, `x` then `a` plays C4; typing `a` into `#program-name` plays nothing; synth-row has a colored left border matching its band.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement keyboard (horizontal scroll, initial scroll to C1), bands above keys with name + root mark, dimmed out-of-section keys, key mapping A S D F G H J K / W E T Y U, Z/X octave shift (0..8) with outlined playable range, ignore keys when focus is in an input/select/textarea or modifier held. Keep existing click-name-to-play.
- [ ] **Step 4:** Run check → PASS; `.venv/bin/pytest -q` green; screenshot looked at.
- [ ] **Step 5:** Commit `feat: on-screen synth keyboard with pitched playback`.

### Task 4: Drag sections, add/remove, Auto split

**Files:** Modify `forcekit/web/app.js`, `style.css`; browser check `scratchpad/kb-drag.py`

**Interfaces:** Consumes Task 1 data shape and Task 3 `sections()`. Produces `makeManual(samples)` (copies current `sections()` into low/high, sorts samples by low), `moveEdge(i, side, note)`.

- [ ] **Step 1: Browser check first** (`kb-drag.py`): synth with 2 samples (auto). Drag the shared border to the key at C4 → ranges row texts `C-2–B3` / `C4–G8`; draft on server has low/high; reload keeps them. Drag with Shift to D4 → `C-2–C♯4`/`D4–G8` (single-key). Drag far past the right end → second section keeps ≥1 key. Drag lowest band's left edge to C1 → keys below C1 dimmed; Auto split clears low/high (server draft has none). Add a third sample while manual → it takes the upper half of the top section; remove the middle → lower neighbour grows.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement pointer-drag on band edges (handles), snapping rules from Global Constraints, clamping between neighbours, add/remove rules from the spec, `#auto-split` (shown only when manual), root select no longer blocks shared roots when manual, scheduleSave after each change.
- [ ] **Step 4:** Run check → PASS; `.venv/bin/pytest -q` green; screenshot looked at.
- [ ] **Step 5:** Commit `feat: drag synth sections on the keyboard`.
