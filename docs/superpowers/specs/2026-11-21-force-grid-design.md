# forcekit — drum pads shown as the Force's 8×8 grid (short design)

**Intent:** Damian wants the screen to show exactly what the Force will show: the same grid, every
sample in the same position, the same colors.

**Approaches:** (1) replace the 4×4 view + bank buttons with one 8×8 grid laid out like the Force —
chosen; (2) keep 4×4 and add a toggle — rejected: two layouts to keep in sync, and he wants the screen
to match the device.

**Design**
- One 8×8 grid: bank A bottom-left, B bottom-right, C top-left, D top-right; pad 1 of each bank is
  its bottom-left corner (confirmed by device photos of VoX and 808_v2). Thin gap between quadrants.
- Pads keep their type color; empty pads stay dark; pads are wider than tall like the hardware.
- Pads show a short name; a line under the grid shows the selected pad: "B07 · hat · file.wav" with
  ◀ ▶ (same-type swap) and Clear. Bank buttons removed.
- Program column wider. Click to play, drag/Enter/double-click to assign, [ ], auto-fill unchanged;
  assigning still advances to the next pad (A16 → B01…).
- Synth view unchanged.

**Verification:** browser check of pad positions (A01 bottom-left, B01 right of A01, C01 above A13,
D16 top-right), colors, info line, assign/advance, [ ]; screenshot.
