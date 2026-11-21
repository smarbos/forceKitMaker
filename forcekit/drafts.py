"""Drafts: programs being built, stored as JSON in the data dir."""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

from .config import Config
from .names import safe_name

DRUM_PADS = 64
MAX_PAD_NAME = 64
MAX_SYNTH_SAMPLES = 128


class DraftError(Exception):
    pass


def _check_path(path: object) -> None:
    if not isinstance(path, str) or not path:
        raise DraftError("sample path missing")
    p = PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts or path.startswith("\\"):
        raise DraftError(f"invalid sample path: {path}")


def _is_note(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 127


def validate_draft(draft: dict) -> None:
    if not isinstance(draft, dict) or not isinstance(draft.get("name"), str):
        raise DraftError("draft needs a name")
    kind = draft.get("type")
    if kind == "drum":
        pads = draft.get("pads", {})
        if not isinstance(pads, dict):
            raise DraftError("pads must be an object")
        for key, path in pads.items():
            if not (isinstance(key, str) and key.isdigit() and 0 <= int(key) < DRUM_PADS):
                raise DraftError(f"invalid pad: {key}")
            _check_path(path)
        names, colors = draft.get("names", {}), draft.get("colors", {})
        if not isinstance(names, dict) or not isinstance(colors, dict):
            raise DraftError("names and colors must be objects")
        for key, value in [*names.items(), *colors.items()]:
            if not (isinstance(key, str) and key.isdigit() and 0 <= int(key) < DRUM_PADS):
                raise DraftError(f"invalid pad: {key}")
        for value in names.values():
            if not isinstance(value, str) or len(value) > MAX_PAD_NAME:
                raise DraftError(f"a pad name is text of at most {MAX_PAD_NAME} characters")
        for value in colors.values():
            if not (isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value)):
                raise DraftError(f"invalid pad color: {value}")
    elif kind == "synth":
        samples = draft.get("samples", [])
        if not isinstance(samples, list) or len(samples) > MAX_SYNTH_SAMPLES:
            raise DraftError(f"a synth holds at most {MAX_SYNTH_SAMPLES} samples")
        roots = set()
        for s in samples:
            _check_path(s.get("path") if isinstance(s, dict) else None)
            root = s.get("root")
            if not _is_note(root):
                raise DraftError(f"invalid root note: {root}")
            roots.add(root)
        manual = [("low" in s or "high" in s) for s in samples]
        if any(manual):  # hand-set sections: all samples have one, no overlaps; roots may repeat
            if not all(manual):
                raise DraftError("either every sample has a key section or none does")
            previous = -1
            for s in sorted(samples, key=lambda s: s.get("low") if _is_note(s.get("low")) else -1):
                low, high = s.get("low"), s.get("high")
                if not (_is_note(low) and _is_note(high) and low <= high):
                    raise DraftError(f"invalid key section: {low}–{high}")
                if low <= previous:
                    raise DraftError("key sections overlap")
                previous = high
        elif len(roots) < len(samples):
            raise DraftError("two samples share a root note")
    else:
        raise DraftError(f"unknown program type: {kind}")


def _file(cfg: Config, stem: str) -> Path:
    return cfg.drafts_dir / f"{safe_name(stem)}.json"


def save_draft(cfg: Config, draft: dict) -> str:
    validate_draft(draft)
    stem = safe_name(draft["name"])
    cfg.drafts_dir.mkdir(parents=True, exist_ok=True)
    _file(cfg, stem).write_text(json.dumps(draft, ensure_ascii=False, indent=1))
    return stem


def load_draft(cfg: Config, stem: str) -> dict:
    path = _file(cfg, stem)
    if not path.is_file():
        raise DraftError(f"no draft named {stem}")
    draft = json.loads(path.read_text())
    validate_draft(draft)
    return draft


def list_drafts(cfg: Config) -> list[dict]:
    if not cfg.drafts_dir.is_dir():
        return []
    items = []
    for path in cfg.drafts_dir.glob("*.json"):
        try:
            draft = json.loads(path.read_text())
        except ValueError:
            continue
        items.append({"stem": path.stem, "name": draft.get("name", path.stem), "type": draft.get("type"),
                      "mtime": path.stat().st_mtime})
    return sorted(items, key=lambda d: d["mtime"], reverse=True)


def delete_draft(cfg: Config, stem: str) -> None:
    _file(cfg, stem).unlink(missing_ok=True)
