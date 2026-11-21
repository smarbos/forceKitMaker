# forcekit — short pad names, manual pad colors, pad renaming (short design)

**Intent:** pads on screen (and on the Force) should read usefully ("KICK 808", not
"DRUMBOII_KICK_808"); Damian wants to pick a pad's color and rename a pad himself.

**Approaches:** names computed once in Python and served to the page (chosen — one rule for screen and
export); a JS copy of the rule (rejected — two implementations to keep identical).

**Design (drum kits only)**
- Auto name: file stem split on `_ - . space`; tokens shared by *every* sample in the kit are removed from
  the start and end (each name keeps ≥1 token); joined with spaces. Exported as the sample name and file
  name (made unique), so the Force shows the same names.
- Draft gains optional `names` {pad: text} and `colors` {pad: "#rrggbb"}. Export: name = custom or auto;
  color = custom or type color.
- Page: line under the grid gets a name field (empty = auto name), color swatches (type colors + extras),
  a free color picker and "Auto". Pads show the custom/auto name.
- Changing a pad's sound (assign, [ ], Clear) drops its custom name; swapping keeps its custom color,
  Clear drops it.

**Verification:** pytest for the name rule, validation, export names/colors, the names API; browser check
of short names, renaming, color pick/Auto, and the drop/keep rules.
