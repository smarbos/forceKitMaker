# forcekit — auto-fill kits, standard layout, pad colors, "next sound", one-shot filter

## Intent

Damian picks sounds by ear, but starting every kit from 64 empty pads is slow,
and the library is 56k files with many loops mixed in. Borrowing the best ideas
from Kit Maker (an automatic MPC kit builder), forcekit should **give him a good
starting kit in one click, laid out the same way every time, color-coded on the
device**, and make it quick to swap sounds by ear from there.

Requested features (his numbering from the Kit Maker comparison):
1. Auto-fill a kit from a folder.
2. The same pad layout in every kit.
3. Pad colors by sound type, shown in forcekit and carried to the Force.
4. "Next sound of the same type" on a pad.
5. Hide loops and long files in the sample list.

## Goals

- One button turns the open folder (including its subfolders) into a new kit draft.
- The kit follows a fixed layout: the same sound type on the same pad in every
  kit and every bank, so patterns stay usable when kits are swapped.
- Every assigned pad has a color from its sound type, in the UI and in the exported `.xpm`.
- A selected pad can step to the next/previous sample of the same type, hearing it immediately.
- The sample list can hide loops and long files.

## Non-goals

- Fully automatic batch conversion of the whole library (one kit per click is enough for now).
- Editing the layout or the colors in the UI (they live in code / config; can come later).
- Manual per-pad color picking.
- Choke/mute groups, 8 banks, resampling (separate ideas, not requested now).

## Anti-goals

- Auto-fill must never overwrite the kit being worked on; it creates a new draft.
- An export with colors must not stop loading on the Force (device gate below).
- Never modify the sample library.

## Approach

One sensible way: extend what exists. The layout and color rules go in a new
Python module (testable, one source of truth); the server exposes them and does
the auto-fill; the page renders colors and adds the buttons. Doing auto-fill in the
browser instead would duplicate the type rules in JS; a separate batch CLI doesn't
match "pick by ear".

## Design

### Layout and colors — `forcekit/layout.py`

Default layout for each bank (pad 1 = bottom-left, as on the Force). Each slot lists
the types it accepts, in priority order:

| Pads | Slots |
|---|---|
| 1–4 | kick · kick · snare · clap (else snare) |
| 5–8 | closed hat · open hat · hat · cymbal |
| 9–12 | tom · tom · tom · perc |
| 13–16 | perc · perc (else any) · fx (else any) · vocal (else any) |

- "closed hat" / "open hat": a `hat` whose filename contains `open`, `opn` or a
  standalone `oh` is open; other hats are closed. Plain "hat" takes either.
- "any" takes leftover samples of other types, including unclassified ones (no type).
  Bass/synth/pad sounds count as "any".
- **My call:** the layout above; easy to change in one table.

Colors by type (24-bit RGB), **my call** for the palette:
kick red, snare yellow, clap orange, hat cyan, cymbal blue, tom purple, perc green,
fx pink, vocal white, everything else / no type: the current green.

### 1+2. Auto-fill

- Button **"Auto-fill kit from this folder"** above the pads (drum mode).
- Server `POST /api/autofill {folder, one_shots}` gathers the folder's samples
  **recursively** (packs usually have Kicks/, Snares/… subfolders), skips broken
  files and duplicates, applies the one-shot filter if it's on, orders each type
  naturally by filename, and fills bank A from the layout, then B, C, D with the
  next samples of each type. It stops when banks run out or no slot can take a
  remaining sample. Empty slots stay empty.
- The page creates a **new draft** named after the folder (made unique if taken),
  saves it, and opens it. The previous kit is untouched (and saved first).

### 3. Pad colors

- Pads light in their sample's type color instead of the single green.
- Export: `programPads.Universal` → false, `programPads.pads.value<N>` → the color
  of pad N (0-based instrument index) for assigned pads; unassigned pads 0.
  Colors are computed at export time from the index's type hints, so drafts don't
  store them.
- **Unconfirmed:** per-pad values are RGB integers (confirmed by an MPC forum
  thread for MPC programs) and `Universal=false` switches to per-pad colors
  (inferred). `Type` stays as the template has it.

### 4. Next / previous sound of the same type

- With a pad selected: **`]`** next, **`[`** previous (also small ◀ ▶ on the
  selected pad). Candidates: the samples in the pad's current sample's folder with
  the same type (or all samples there if it has no type), skipping broken files.
  The pad is reassigned, the sound plays, the draft autosaves. Wraps around.

### 5. One-shot filter

- Checkbox **"Hide loops & long"** next to the type filter: hides files typed
  `loop` and files longer than **4 s**. **My call:** off by default, because
  vocal kits (e.g. VoX) use samples up to 8 s; remembered in the browser.
- Auto-fill uses the checkbox's current state.

## Verification

- Unit tests: slot matching (open/closed hats, fallbacks, "any"), filling across
  banks, colors in the exported `.xpm`, the autofill API (recursive, skips broken
  and duplicates, one-shot filter).
- UI checked in a browser (auto-fill, colors, `[`/`]`, filter).
- **Device gate:** Damian loads an auto-filled, color-coded kit on the Force and
  confirms the pads show the colors and still play. If colors don't show, he saves
  a drum program with two colored pads on the Force so the encoding can be copied.

## Left to the builder

- Exact color values, button placement and wording, the duplicate-name suffix.
