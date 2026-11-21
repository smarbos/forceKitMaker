"""Drafts: programs being built, stored as JSON in the data dir."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from .config import Config
from .names import safe_name

DRUM_PADS = 64
MAX_SYNTH_SAMPLES = 128


class DraftError(Exception):
    pass


def _check_path(path: object) -> None:
    if not isinstance(path, str) or not path:
        raise DraftError("sample path missing")
    p = PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts or path.startswith("\\"):
        raise DraftError(f"invalid sample path: {path}")


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
    elif kind == "synth":
        samples = draft.get("samples", [])
        if not isinstance(samples, list) or len(samples) > MAX_SYNTH_SAMPLES:
            raise DraftError(f"a synth holds at most {MAX_SYNTH_SAMPLES} samples")
        roots = set()
        for s in samples:
            _check_path(s.get("path") if isinstance(s, dict) else None)
            root = s.get("root")
            if not isinstance(root, int) or not 0 <= root <= 127:
                raise DraftError(f"invalid root note: {root}")
            if root in roots:
                raise DraftError(f"two samples share root note {root}")
            roots.add(root)
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
