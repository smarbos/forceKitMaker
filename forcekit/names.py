"""Note names, key ranges and filename helpers. MIDI 60 = C3 (Akai convention)."""
from __future__ import annotations

import re
import unicodedata

_PITCH = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}
_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_SPLIT = re.compile(r"[\s_\-.()\[\]]+")
_NOTE = re.compile(r"([A-Ga-g])([#b]?)(-?\d)")
_BAD = re.compile(r'[/\\:*?"<>|\x00-\x1f\x7f]')


def parse_note(text: str) -> int | None:
    """MIDI note of the last token in `text` that is a note name like C3, F#2, Db4."""
    for token in reversed([t for t in _SPLIT.split(text) if t]):
        # "-" is a separator, so "C-1" arrives as tokens "C", "1"; handle that pair too.
        m = _NOTE.fullmatch(token)
        if m:
            return _to_midi(*m.groups())
    m = re.search(r"(?:^|[\s_.()\[\]])([A-Ga-g])([#b]?)(-\d)(?=$|[\s_\-.()\[\]])", text)
    if m:
        return _to_midi(*m.groups())
    return None


def _to_midi(letter: str, accidental: str, octave: str) -> int | None:
    pc = _PITCH[letter.lower()] + (1 if accidental == "#" else -1 if accidental == "b" else 0)
    midi = 12 * (int(octave) + 2) + pc
    return midi if 0 <= midi <= 127 else None


def note_name(midi: int) -> str:
    return f"{_NAMES[midi % 12]}{midi // 12 - 2}"


def key_ranges(roots: list[int]) -> list[tuple[int, int]]:
    ranges = []
    for i, root in enumerate(roots):
        low = 0 if i == 0 else (roots[i - 1] + root) // 2 + 1
        high = 127 if i == len(roots) - 1 else (root + roots[i + 1]) // 2
        ranges.append((low, high))
    return ranges


def safe_name(text: str, max_len: int = 48) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    cleaned = " ".join(_BAD.sub("", ascii_text).split())[:max_len].strip()
    cleaned = cleaned.lstrip(". ")  # never ".", ".." or a hidden file/folder
    return cleaned or "untitled"


def unique_name(name: str, taken: set[str]) -> str:
    candidate, n = name, 1
    while candidate.lower() in {t.lower() for t in taken}:
        n += 1
        candidate = f"{name} {n}"
    taken.add(candidate)
    return candidate


def natural_key(text: str) -> list:
    """Sort key that orders "Kick 2" before "Kick 10"."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text)]
