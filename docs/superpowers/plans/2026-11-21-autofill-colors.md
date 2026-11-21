# Auto-fill, layout, pad colors, next sound, one-shot filter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One-click starting kits in a fixed layout, colored by sound type on screen and on the Force, plus quick same-type swapping and a loop/long-file filter.

**Architecture:** A new pure module `forcekit/layout.py` owns the layout, type colors, one-shot rule and the auto-fill algorithm. The xpm writer gains per-pad colors; the server exposes auto-fill, layout/colors and type lookups; the page uses them.

**Tech Stack:** Python 3 stdlib + numpy/soundfile (existing), vanilla JS, pytest, Playwright (scratch venv) for UI checks.

**Spec:** `docs/superpowers/specs/2026-11-21-autofill-colors-design.md` (base spec: `docs/superpowers/specs/2026-11-20-forcekit-design.md`)

## Global Constraints

- Never modify the sample library.
- Auto-fill creates a new draft; it never overwrites the open one.
- Pad 1 = bottom-left; pad index `p` (0-based) = `bank * 16 + pad_in_bank`; 4 banks (64 pads).
- Colors are 24-bit RGB ints in the `.xpm`; computed at export from the index, not stored in drafts.
- One-shot rule: `type_hint != "loop"` and (`duration` is None or `duration <= 4.0`).
- Run tests with `.venv/bin/pytest -q` from `~/dev/forcekit`.

## Review Focus

1. Auto-fill of the library root (56k files) — must answer in well under a few seconds.
2. A draft whose sample paths are no longer in the index — pads render with the default color, `[`/`]` does nothing harmful, export still works.
3. Hat open/closed detection on names like `Shoe.wav`, `HH_OH_01.wav`, `open hat.wav`, `Hat Opn.wav` — `oh` only as a standalone token.
4. Auto-fill of a folder that only has loops while the filter is on — clear "nothing to fill" message, no empty draft created.
5. Auto-fill when a draft with the folder's name already exists — a unique name (" 2", " 3"…), no 409 dead end.

---

### Task 1: `forcekit/layout.py` — layout, colors, one-shot rule, auto-fill

**Files:**
- Create: `forcekit/layout.py`
- Modify: `forcekit/names.py` (add `natural_key`), `forcekit/server.py` (use `natural_key` instead of its private `_natural`)
- Test: `tests/test_layout.py`

**Interfaces:**
- Produces:
  - `SLOTS: list[tuple[str, ...]]` — 16 entries, index = pad in bank (0 = pad 1):
    `("kick",), ("kick",), ("snare",), ("clap","snare"), ("hat:closed",), ("hat:open",), ("hat",), ("cymbal",), ("tom",), ("tom",), ("tom",), ("perc",), ("perc",), ("perc","any"), ("fx","any"), ("vocal","any")`
  - `TYPE_COLORS: dict[str, int]` = kick `0xFF2A2A`, snare `0xFFD21A`, clap `0xFF8A1A`, hat `0x1AD8FF`, cymbal `0x3A6BFF`, tom `0xA64DFF`, perc `0x9DFF1A`, fx `0xFF4DC4`, vocal `0xF0F0F0`; `DEFAULT_COLOR = 0x3CFF5A`
  - `MAX_ONE_SHOT = 4.0`
  - `color_for(type_hint: str | None) -> int`
  - `is_one_shot(entry: dict) -> bool`
  - `kind(entry: dict) -> str` — `type_hint`, except hats → `"hat:open"` if the basename (no extension) has a token `open`/`opn`/`oh` (tokens split on non-letters/digits and camelCase, case-insensitive), else `"hat:closed"`; types without a slot (None, bass, synth, pad, loop…) → `"any"`
  - `autofill(entries: list[dict]) -> dict[int, str]` — pad index → path
  - `natural_key(text: str) -> list` in `names.py`

Auto-fill algorithm (not determined by the signature):
```
usable = entries without error and without dup_of, sorted by natural_key(path)
queues = {kind: deque of paths}
for bank in 0..3:
    filled = {}
    for choice in 0..1:                       # first choices across the bank, then fallbacks
        for i, options in enumerate(SLOTS):
            if i in filled or choice >= len(options): continue
            opt = options[choice]
            take from: "hat" -> queues["hat:closed"] then queues["hat:open"]; others -> queues[opt]
            if taken: filled[i] = path
    if not filled: stop
    pads.update({bank*16 + i: p for i, p in filled.items()})
```

- [ ] **Step 1: Write the failing tests** in `tests/test_layout.py`:
  - `test_kind_hats`: `kind` of hats named `HH_OH_01.wav`, `open hat.wav`, `Hat Opn.wav`, `ClosedHat.wav`, `Shoe hat.wav` → open, open, open, closed, closed; `kind({"type_hint": "bass", ...}) == "any"`, `kind` of `None` → `"any"`.
  - `test_is_one_shot`: loop → False; duration 4.0 → True; 4.01 → False; duration None → True.
  - `test_color_for`: `color_for("kick") == 0xFF2A2A`, `color_for(None) == color_for("bass") == 0x3CFF5A`.
  - `test_autofill_layout`: 3 kicks, 1 snare, 1 clap, 1 closed hat, 1 open hat → pads 0,1 = first two kicks; 2 = snare; 3 = clap; 4 = closed hat; 5 = open hat; bank B pad 16 = third kick; nothing else.
  - `test_autofill_fallbacks`: 2 snares, no clap → pad 2 = snare 1, pad 3 = snare 2; unclassified files fill pads 13,14,15 (no perc/fx/vocal present).
  - `test_autofill_skips_broken_and_duplicates`: entries with `error` or `dup_of` never appear.
  - `test_autofill_caps_at_four_banks`: 10 kicks → pads 0,1,16,17,32,33,48,49 only.
  - `test_natural_key`: `sorted(["Kick 10", "Kick 2"], key=natural_key) == ["Kick 2", "Kick 10"]`.
  Entries are dicts `{"path", "type_hint", "duration", "error": None, "dup_of": None}`.

- [ ] **Step 2: Run** `.venv/bin/pytest -q tests/test_layout.py` — Expected: FAIL (`ModuleNotFoundError: forcekit.layout`).
- [ ] **Step 3: Implement** `forcekit/layout.py` and `names.natural_key`; switch `server.py` to `natural_key`.
- [ ] **Step 4: Run** `.venv/bin/pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `git commit -m "Add layout module: standard pad layout, type colors, one-shot rule, auto-fill"`

### Task 2: Per-pad colors in the exported `.xpm`

**Files:**
- Modify: `forcekit/xpm.py` (`build_drum`), `forcekit/export.py` (`export_program`), `forcekit/server.py` (`export` route)
- Test: `tests/test_xpm.py`, `tests/test_export.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `layout.color_for`
- Produces:
  - `build_drum(name, pads: dict[int, SampleRef], colors: dict[int, int] | None = None)` — when `colors` is given: `programPads["Universal"]["value0"] = False` and `programPads["pads"][f"value{p}"] = colors.get(p, 0)` for every key already in `pads` (0..127); when None, template unchanged.
  - `export_program(cfg, draft, normalize=True, overwrite=False, colors: dict[int, int] | None = None)` — passes `colors` to `build_drum` (ignored for synths).
  - Server `export` computes `colors = {int(k): color_for(library.files.get(p, {}).get("type_hint")) for k, p in draft["pads"].items()}` for drum drafts.

- [ ] **Step 1: Failing tests:**
  - `test_xpm.py::test_drum_pad_colors`: `build_drum("K", {0: ref, 5: ref2}, colors={0: 0xFF2A2A, 5: 0x1AD8FF})` → `programPads.Universal.value0 is False`, `pads.value0 == 0xFF2A2A`, `pads.value5 == 0x1AD8FF`, `pads.value1 == 0`; `build_drum` without colors keeps `Universal.value0 is True`.
  - `test_export.py::test_export_writes_colors`: export with `colors={0: 0xFF2A2A}` → read back, `pads.value0 == 0xFF2A2A`.
  - `test_server.py::test_export_colors_by_type`: POST `/api/export` with pad 0 = `Drums/Kick 01.wav`, pad 1 = `Drums/Snare 01.wav` → exported file has `value0 == 0xFF2A2A`, `value1 == 0xFFD21A`.
- [ ] **Step 2: Run** `.venv/bin/pytest -q tests/test_xpm.py tests/test_export.py tests/test_server.py` — Expected: the 3 new tests FAIL (unexpected keyword `colors` / wrong values).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `.venv/bin/pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `git commit -m "Write per-pad colors by sound type into exported drum programs"`

### Task 3: Server API — auto-fill, layout info, type lookup

**Files:**
- Modify: `forcekit/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `layout.autofill`, `layout.is_one_shot`, `layout.TYPE_COLORS`, `layout.DEFAULT_COLOR`, `layout.MAX_ONE_SHOT`
- Produces:
  - `POST /api/autofill {"folder": str, "one_shots": bool}` → `{"pads": {"<idx>": path}}`. Entries: `folder == f["folder"]` or `f["folder"].startswith(folder + "/")`; `""` = whole library; `one_shots` → keep only `is_one_shot`. 400 if body isn't an object or `folder` isn't a string.
  - `GET /api/layout` → `{"colors": {type: "#rrggbb"}, "default": "#rrggbb", "max_one_shot": 4.0}`
  - `POST /api/hints {"paths": [str]}` → `{path: type_hint_or_null}` for paths in the index (unknown paths omitted).

- [ ] **Step 1: Failing tests** in `tests/test_server.py`:
  - `test_autofill_recursive`: `{"folder": "", "one_shots": False}` → pad `"0"` is `"Drums/Kick 01.wav"` (the duplicate `Other/Kick 01.wav` absent), pad `"2"` is `"Drums/Snare 01.wav"`, `"Old/corrupt.wav"` absent from values; `{"folder": "Drums"}` → only paths starting with `Drums/`.
  - `test_autofill_one_shot_filter` (own server, not the `srv` fixture): write a 5 s sine to `library/Drums/Long hit.wav`, `scan_library(cfg)`, start `make_server(cfg)` in a thread. `{"folder": "Drums", "one_shots": True}` → `"Drums/Long hit.wav"` not in the values; with `False` → present.
  - `test_layout_and_hints`: `/api/layout` colors `kick == "#ff2a2a"`, `max_one_shot == 4.0`; `/api/hints` with `["Drums/Kick 01.wav", "nope.wav"]` → `{"Drums/Kick 01.wav": "kick"}`.
  - `test_autofill_bad_request`: body `{"folder": 3}` → 400.
- [ ] **Step 2: Run** `.venv/bin/pytest -q tests/test_server.py` — Expected: new tests FAIL with 404.
- [ ] **Step 3: Implement** the three routes.
- [ ] **Step 4: Run** `.venv/bin/pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `git commit -m "Add auto-fill, layout and type-hint API endpoints"`

### Task 4: Page — colors, auto-fill button, `[`/`]`, one-shot filter

**Files:**
- Modify: `forcekit/web/index.html`, `forcekit/web/app.js`, `forcekit/web/style.css`
- Test: browser check script in the scratchpad (`autofill-ui.py`, Playwright Firefox) against a server on a scratch data dir.

**Interfaces:**
- Consumes: `/api/layout`, `/api/autofill`, `/api/hints`, `/api/folder`, existing draft API.

Behaviour:
- Init loads `/api/layout` into `state.layout`; `state.hints` caches path → type_hint (filled from folder listings, auto-fill and `/api/hints` for pads with unknown paths after a draft opens).
- Filled pads use their type color via a CSS custom property (`--pad-color`) instead of the fixed green; the bank button marker unchanged.
- Button `#autofill` "Auto-fill kit from this folder" above the banks (drum mode): `flushSave()`, POST `/api/autofill` with the current folder and the filter state; empty → status "Nothing to fill from this folder", no draft; else new drum program named after the folder's last segment (`"Library"` for root), saved with PUT `""`; on 409 retry with " 2", " 3"… ; opened; status "Auto-filled N pads from <folder>".
- `[` / `]` (and ◀ ▶ buttons on the selected filled pad): fetch `/api/folder?path=<dirname of pad's sample>`, candidates = entries without error with the same type_hint (all non-error entries if the pad's hint is null), step with wrap-around, assign, play, flash, autosave. No-op with a status message if the sample isn't in the index.
- Checkbox `#one-shots` "Hide loops & long" after `#hint-filter`; filters the list with the one-shot rule using `state.layout.max_one_shot`; state remembered in `localStorage` (wrapped in try/catch); default off.

- [ ] **Step 1: Write the browser check** `autofill-ui.py` asserting: after clicking `#autofill` on the `drums/808` folder a new draft appears in `#drafts`, pad A01 has a sample and its computed `--pad-color` is `#ff2a2a`-ish for a kick; pressing `]` with A01 selected changes its sample to another kick; ticking `#one-shots` doesn't increase the file count and hides any `loop` row; no page errors.
- [ ] **Step 2: Run it** — Expected: FAIL (`#autofill` not found).
- [ ] **Step 3: Implement** markup, styles, JS.
- [ ] **Step 4: Run it again** — Expected: all assertions pass; also `.venv/bin/pytest -q` all pass. Take a screenshot and look at it.
- [ ] **Step 5: Commit** `git commit -m "Page: auto-fill button, type-colored pads, [ ] to swap sounds, one-shot filter"`
