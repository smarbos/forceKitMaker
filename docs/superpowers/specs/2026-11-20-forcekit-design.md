# forcekit — browse samples, build Akai Force drum kits and synths

## Intent

Damian has ~15 GB / 88k files of samples in `~/Samples/samples` (~60 top-level
packs, 1,593 folders with audio, 54k WAV + ~750 AIFF + ~5.8k MP3, plus a lot of
junk and legacy formats). He wants to start playing them on his Akai Force.

Rather than converting everything automatically, he wants to **pick by ear**:
browse the library, listen, and assemble programs by hand, then export them in
the Force's own format and copy them to the SD card. Later this can grow into
more curation, and possibly a desktop app if the web version works out.

## Goals

1. **Scan** the library into a JSON index of every usable audio file with the
   information we can cheaply extract.
2. **Web UI** (local) to navigate the library as a folder tree and listen to
   samples.
3. **Drum builder:** a pad grid; assign samples to pads.
4. **Synth builder:** a keygroup program from one or more samples; each sample
   has a root note, key ranges are computed automatically.
5. **Export** a drum or synth program in the Force 3.10 format (`.xpm` +
   `<Name>_[ProgramData]/` folder) to an output folder, ready to copy to the SD card.

## Non-goals

- Sample editing: no start/end, trim, loop points, envelopes, tuning, pan, volume.
  The **only** per-sample setting is a synth sample's root note (without it the
  synth is out of tune).
- Velocity layers, mute/choke groups, multiple layers per pad.
- Loops / slicing, single-cycle oscillators.
- Writing directly to the SD card, desktop packaging.
- Legacy formats (`.raw`, `.8svx`, `.256`, `.add`, `.xa`, `.rx2`, `.sxt`, `.wt`).

## Anti-goals

- Never modify, move or delete anything in the sample library.
- No exported program that fails to load on the Force — export is only "done"
  once a test kit and a test synth have loaded and played on the device.
- Not a slow tool: browsing and auditioning must feel instant; the full scan
  must not take hours.

## Approaches considered

1. **Python server + plain HTML/JS page (chosen).** One language for the scan,
   audio handling and the Force format; no frontend build step; run one command
   and open `localhost`.
2. Python backend + React/Vite frontend. Nicer to grow a richer UI, but two
   toolchains and a build step for a simple UI.
3. Desktop app (Electron/Tauri). Most setup for no gain while it runs on one
   machine. Possible later step; keeping the backend a clean JSON API makes
   that move cheap.

## Design

### Project

- `~/dev/forcekit`, Python 3 package with a CLI:
  - `forcekit scan [LIBRARY]` — build/update the index.
  - `forcekit serve` — start the web UI on `http://127.0.0.1:8765`.
- Config (library root, index path, drafts dir, export dir) in
  `~/.config/forcekit/config.json`, defaults:
  library `~/Samples/samples`, data dir `~/Samples/forcekit/`
  (`index.json`, `drafts/`), export dir `~/Samples/force-out/`.
- Dependencies: `soundfile`, `numpy`, `librosa` (pitch detection only), in a
  project venv. `ffmpeg` (installed) for decoding AIFF/MP3 and converting.
  Web server: Python stdlib (`http.server`, threaded) — no framework needed.
- Server binds to 127.0.0.1 only and serves files only from inside the
  library root (reject paths that resolve outside it).

### 1. Scan → `index.json`

- Walk the library; include `.wav .aif .aiff .mp3` (case-insensitive).
  Skip `__MACOSX`, `._*`, hidden files/folders, and the data/export dirs.
- Per file: relative path, folder, size, mtime, duration, sample rate,
  channels, bit depth, format; a content hash for duplicate detection;
  `type_hint` from filename/folder keywords (kick, snare, clap, hat, tom,
  cymbal, perc, fx, vocal, bass, synth, pad, loop…) or `null`;
  `note` parsed from the filename (`C3`, `F#2`, `Db4`, MIDI `_60_`) or `null`.
- Unreadable files are listed with an `error` field, not dropped silently.
- Incremental: re-scan reuses entries whose size + mtime haven't changed.
- Pitch detection is **not** run during the scan (too slow for 60k files);
  it runs on demand when a sample is added to a synth (see 4).
- Scan prints progress and a summary (files, errors, duplicate groups).

### 2. Web UI layout

```
┌──────────────┬──────────────────────────────┬─────────────────────────┐
│ Folder tree  │ Files in folder              │ Program                 │
│              │ ▶ Kick 01.wav   0.4s  kick   │ [Drum | Synth]  Name:__ │
│ ▸ Oid Mort.. │ ▶ Kick 02.wav   0.5s  kick   │                         │
│ ▾ drums      │ ▶ Snare 01.wav  0.3s  snare  │ Drum: 4×4 pads,         │
│   ▸ Yamaha.. │   …                          │ banks A B C D (64 pads) │
│ filter: ___  │ filter: ___  type: [all ▾]   │ Synth: sample list with │
│              │                              │ root note + key map     │
│              │                              │ [Export]                │
└──────────────┴──────────────────────────────┴─────────────────────────┘
```

- **Folder tree:** lazy-loaded from the index; shows file counts; text filter.
- **File list:** name, duration, type hint, note; filter by text and type hint.
  Click a file to play it. ↑/↓ moves the selection **and plays** (fast
  auditioning). Space replays. Duplicates marked.
- **Playback:** WAV/MP3 streamed as-is; AIFF and anything the browser can't
  play transcoded to WAV by the server with ffmpeg on request (cached in the
  data dir).

### 3. Drum builder

- Force-style 4×4 grid, bank switcher A–D (64 pads).
- Assign: select a pad, then double-click a file (or press Enter / drag a file
  onto a pad). Pad shows the sample name; click a pad to play it; clear button
  per pad. One sample per pad.

### 4. Synth builder

- Add samples from the file list (same gestures as above).
- Each sample shows its root note: from the filename if present, else pitch
  detection (librosa pyin on the first ~1 s) when added, else C3. A dropdown
  changes it.
- Two samples may not share a root note (UI blocks it with a message).
- Key ranges computed automatically: each sample covers up to the midpoint
  between its root and its neighbours'; lowest extends to note 0, highest to
  127. One sample = the whole keyboard. Shown as a simple key-range strip.
- Max 128 samples.

### 5. Drafts

- The program being built autosaves to `drafts/<name>.json` (type, name,
  pad/sample assignments, root notes). A drafts list lets you reopen or delete
  one. A draft references library paths; it doesn't copy audio.

### 6. Export (Force 3.10 format)

Format reverse-engineered from Damian's templates in `~/Samples/xpm/`
(`DrumTest.xpm`, `Keygrouptes.xpm`, saved by firmware 3.10.1.12):

- `.xpm` = gzip of the header
  `ACVS\n3.10.1.12\nSerialisableProgramData\njson\nLinux\n` followed by JSON
  `{"data": {...}}`.
- `data.type`: 0 = drum, 1 = keygroup. `data.name` = program name.
- Samples go in `<Name>_[ProgramData]/` next to the `.xpm`; `layersv[].sampleFile`
  and `data.samples[].path` are bare filenames.
- Drum: `data.drum.instruments` has 128 entries, each with 8 `layersv`;
  `padNoteMap.noteForPad` maps pads → notes (pad 1 → note 36).
- Keygroup: `data.keygroup.numKeygroups`; keygroups live in
  `data.drum.instruments`, each with `lowNote`/`highNote`; layer has
  `rootNote`, `keyTrackEnable`.
- `data.samples[]` lists every sample (`name`, `path`, `metadata.rootNote`).

Rules:
- The two templates are copied into the project with their sample references
  removed. Every export is a modified copy of a template, so all fields we don't
  understand keep the Force's own defaults.
- Audio: WAV files are copied as-is; AIFF/MP3 are converted to WAV (keeping the
  source rate and bit depth, 16-bit for MP3).
- **Normalize on export** checkbox, on by default (Damian's original goal
  included normalizing): drums → each sample peak-normalized to −1 dBFS;
  synth → one shared gain so the loudest sample peaks at −1 dBFS. This is
  the only audio change and it happens on the exported copy only.
- Sample filenames sanitized (ASCII, no `/\:*?"<>|`) and made unique within
  the program; program name sanitized the same way.
- Output: `<export dir>/Drums/<Name>.xpm` or `<export dir>/Synths/<Name>.xpm`
  plus its `_[ProgramData]` folder. Exporting over an existing program asks
  for confirmation in the UI.

### Verification

- Unit tests: filename note parsing, key-range math, name sanitizing, path
  containment check, `.xpm` writer (write → read back → structure matches the
  template, sample references in the right places).
- **Device gate:** export a small drum kit (samples on pads A01, A02, A16, B01)
  and a 3-sample synth; Damian loads both on the Force and confirms pads and
  notes play the right samples. Until that passes, the export isn't done.

## Left to the builder

- Exact pad ↔ instrument index mapping: the template's samples sit on
  instruments 32 and 33 while `padNoteMap` maps pad 1 → note 36. Work it out
  from the template; the device gate confirms it.
- The keygroup template has no samples assigned, so keygroup field usage is
  inferred. If the device gate fails for synths, ask Damian to save a keygroup
  with 2 samples on different root notes.
- Visual styling of the UI; keep it plain and fast.
- Pitch-detection fallback details and thresholds.
