"""Standard drum-kit layout, sound-type colors, and auto-filling a kit from a folder.

Every bank uses the same layout so a pattern keeps working when kits are swapped.
Index = pad within the bank (0 = pad 1, bottom-left). Each slot lists the kinds it
accepts in priority order; "any" takes sounds whose type has no slot of its own.
"""
from __future__ import annotations

import os
from collections import deque

from .names import natural_key
from .scan import _tokens as name_tokens  # same word splitting as the type hints

SLOTS: list[tuple[str, ...]] = [
    ("kick",), ("kick",), ("snare",), ("clap", "snare"),
    ("hat:closed",), ("hat:open",), ("hat",), ("cymbal",),
    ("tom",), ("tom",), ("tom",), ("perc",),
    ("perc",), ("perc", "any"), ("fx", "any"), ("vocal", "any"),
]
BANKS = 4

TYPE_COLORS: dict[str, int] = {
    "kick": 0xFF2A2A, "snare": 0xFFD21A, "clap": 0xFF8A1A, "hat": 0x1AD8FF, "cymbal": 0x3A6BFF,
    "tom": 0xA64DFF, "perc": 0x9DFF1A, "fx": 0xFF4DC4, "vocal": 0xF0F0F0,
}
DEFAULT_COLOR = 0x3CFF5A  # untyped / other sounds: the Force template's green family

MAX_ONE_SHOT = 4.0  # seconds; longer files count as loops/phrases for the one-shot filter

_SLOTTED = {opt.split(":")[0] for slot in SLOTS for opt in slot} - {"any"}
_OPEN_TOKENS = {"open", "opn", "oh", "ohh", "hho"}
_CLOSED_TOKENS = {"closed", "close", "clsd", "cl", "ch", "chh", "hhc"}


def color_for(type_hint: str | None) -> int:
    return TYPE_COLORS.get(type_hint or "", DEFAULT_COLOR)


def is_one_shot(entry: dict) -> bool:
    d = entry.get("duration")
    return entry.get("type_hint") != "loop" and (d is None or d <= MAX_ONE_SHOT)


def _is_open(tokens: list[str]) -> bool:
    return any(t in _OPEN_TOKENS or t.startswith("open") for t in tokens)


def _is_closed(tokens: list[str]) -> bool:
    return any(t in _CLOSED_TOKENS or t.startswith("clos") for t in tokens)


def kind(entry: dict) -> str:
    hint = entry.get("type_hint")
    if hint == "hat":
        folder, _, name = entry["path"].rpartition("/")
        stem = name_tokens(os.path.splitext(name)[0])
        if _is_open(stem):
            return "hat:open"
        if not _is_closed(stem) and _is_open(name_tokens(folder)):  # e.g. "Open Hats/Hat 01.wav"
            return "hat:open"
        return "hat:closed"
    return hint if hint in _SLOTTED else "any"


def autofill(entries: list[dict]) -> dict[int, str]:
    """Pad index → library path, filling bank A from SLOTS, then B, C, D with the next sounds."""
    usable = sorted((f for f in entries if not f.get("error") and not f.get("dup_of")),
                    key=lambda f: natural_key(f["path"]))
    queues: dict[str, deque] = {}
    for f in usable:
        queues.setdefault(kind(f), deque()).append(f["path"])

    def take(option: str) -> str | None:
        for k in (("hat:closed", "hat:open") if option == "hat" else (option,)):
            if queues.get(k):
                return queues[k].popleft()
        return None

    pads: dict[int, str] = {}
    for bank in range(BANKS):
        filled: dict[int, str] = {}
        for choice in range(max(len(s) for s in SLOTS)):  # first choices across the bank, then fallbacks
            for i, options in enumerate(SLOTS):
                if i in filled or choice >= len(options):
                    continue
                path = take(options[choice])
                if path:
                    filled[i] = path
        if not filled:
            break
        pads.update({bank * 16 + i: p for i, p in filled.items()})
    return pads
