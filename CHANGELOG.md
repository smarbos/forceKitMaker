# Changelog

## v0.1.0 — first release

Build Akai Force drum kits and keygroup synths from your own sample library, in the browser.

**Browse**
- Index a sample folder of any size: length, format, a guessed sound type, and duplicate and broken-file detection.
- Preview with the arrow keys; filter by name or type; hide loops and long files.

**Drum kits**
- An 8×8 pad grid laid out like the Force (banks A–D).
- Auto-fill a kit from a folder in a fixed layout repeated across the four banks.
- Pads colored by sound type, on screen and on the Force; custom colors and names per pad.
- Short pad names made automatically; `[` / `]` swaps a pad to the previous or next sound of the same type.

**Synths**
- Keygroup programs with root notes read from filenames or detected from the audio.
- An on-screen keyboard that plays the synth pitched, like the Force (mouse or computer keys).
- Keyboard sections set by dragging split lines, or an automatic split.

**Export**
- Force 3.10 programs: one folder per program, with the `.xpm` file and a samples subfolder.
- 16-bit WAV, optional normalizing, start and end points detected.
- **Send to Force** over SSH (key login), copied safely so a dropped connection never leaves a half-copied kit.

Runs on Linux, macOS and Windows (Python 3.11+). Tested on a Force running firmware 3.10.1.12.
