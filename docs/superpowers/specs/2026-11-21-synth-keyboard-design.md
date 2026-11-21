# forcekit — on-screen keyboard and manual sections for synths

## Intent

Damian wants to build split synths: e.g. two octaves of one sound and two
octaves of another. Today forcekit splits the keyboard automatically halfway
between root notes, and the browser can't play a synth pitched, so he can only
hear the result on the Force.

## Goals

- A keyboard under the synth that plays the program like the Force will: each
  note uses the sample whose section holds it, pitched from that sample's root.
- Sections chosen by hand by dragging split points on that keyboard.
- The export uses those sections.

## Non-goals / anti-goals

- No overlapping sections (layers), no velocity layers.
- Synths that were never edited keep the automatic split; nothing about existing
  drafts or exports changes unless the user drags.

## Approaches

- **A. Drag split points on the keyboard (picked).** Fast for "2 octaves each",
  overlaps are impossible.
- B. Low/high menus per sample row: fiddly, needs overlap handling.
- C. Paint keys per sample: flexible but leaves stray keys, harder to read.

## Design

**Data.** A synth draft's samples may carry `low` and `high` (0–127). Either all
samples have them or none do (none = automatic split, as today). When present:
`low ≤ high`, sections don't overlap, and the unique-root rule is dropped (two
sections may share a root). Export uses `low/high` when present, else `key_ranges`.

**Keyboard.** All 128 notes (C-2–G8, C3 = 60 as on the Force), horizontally
scrollable, initially showing C1–C6. A band above the keys shows each sample's
section in its own color with its name; a small mark shows its root. Keys outside
every section are dimmed and silent. Each row in the sample list gets the same
color and shows its range.

**Playing.** Click a key, or use computer keys: A S D F G H J K = white keys,
W E T Y U = black keys, Z / X = octave down / up (the playable octave is
outlined). Playback in Web Audio: the sample is decoded once and played with
`playbackRate = 2^((note − root) / 12)`, several notes at once allowed.

**Editing sections.** Drag the border between two bands to move the split; drag
the outer edge of the lowest/highest band to leave keys silent below/above.
Drags snap to whole octaves (on C); hold Shift for single keys. A band is never
shorter than one key. The first drag turns the automatic split into explicit
sections (all samples get `low/high`). A **"Auto split"** button returns to the
automatic split.
- Adding a sample while sections are manual: it takes the upper half of the
  highest section (or the silent keys above it, if there are any).
- Removing one: the section below grows into its keys (the one above if it was
  the lowest).
- Sample order follows the sections (low to high) when manual, roots otherwise.

## Verification

- Unit tests: draft validation (all-or-none, overlap, bounds), export uses manual
  ranges, shared roots allowed only with manual ranges.
- Browser check (Playwright): drag a split, ranges update and persist after reload;
  keyboard press triggers playback at the right rate; Auto split restores.
- Device check: a two-section synth on the Force switches sounds at the split.

## Left to the builder

Band colors, exact key sizes, drag handle look, how the root mark is drawn.
