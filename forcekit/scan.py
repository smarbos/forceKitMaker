"""Walk the sample library and write index.json."""
from __future__ import annotations

import hashlib
import json
import os
import re
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .audio import AudioError, probe
from .config import Config
from .names import parse_note

AUDIO_EXTS = {".wav", ".aif", ".aiff", ".mp3"}
INDEX_VERSION = 1
_POOL_THRESHOLD = 64  # small scans (tests, re-scans) stay in-process

HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("loop", ("loop", "bpm")),
    ("kick", ("kick", "kik", "bd", "bassdrum")),
    ("snare", ("snare", "snr", "sd")),
    ("clap", ("clap", "clp", "cp")),
    ("hat", ("hat", "hats", "hh", "hihat", "oh", "ch", "chh", "ohh", "hhc", "hho")),
    ("tom", ("tom", "toms")),
    ("cymbal", ("cymbal", "cym", "cy", "crash", "ride", "china", "splash")),
    ("perc", ("perc", "percussion", "conga", "bongo", "shaker", "tamb", "tambourine", "cowbell", "rim",
              "rimshot", "clave", "block", "bell")),
    ("fx", ("fx", "sfx", "effect", "effects", "impact", "riser", "sweep", "noise")),
    ("vocal", ("vox", "vocal", "voice", "speech", "spoken")),
    ("bass", ("bass",)),
    ("synth", ("synth", "lead", "stab", "arp")),
    ("pad", ("pad", "pads", "chord", "chords", "strings")),
]
_WORD = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")


def _tokens(text: str) -> list[str]:
    return [w.lower() for piece in re.split(r"[^A-Za-z0-9]+", text) for w in _WORD.findall(piece)]


def _matches(token: str, keyword: str) -> bool:
    # Short keywords (bd, sd, oh, fx…) must match exactly; longer ones also match as a prefix
    # ("snaredrums", "kicks", "loops").
    return token == keyword or (len(keyword) >= 4 and token.startswith(keyword))


def type_hint(rel_path: str) -> str | None:
    parts = rel_path.split("/")
    stem = os.path.splitext(parts[-1])[0]
    for depth, name in enumerate([stem, *reversed(parts[:-1])]):
        tokens = _tokens(name)
        if any(a == "bass" and b.startswith("drum") for a, b in zip(tokens, tokens[1:])):
            return "kick"
        for hint, keywords in HINTS:
            if any(_matches(t, k) for t in tokens for k in keywords):
                return hint
        if depth == 0 and "808" in tokens:  # "808_BOOM": an 808 bass hit; a folder named 808 says nothing
            return "bass"
    return None


def file_hash(path: Path) -> str:
    h = hashlib.blake2b(digest_size=16)
    h.update(str(path.stat().st_size).encode())
    with open(path, "rb") as f:
        h.update(f.read(1 << 20))
    return h.hexdigest()


def _blank(rel: str) -> dict:
    suffix = os.path.splitext(rel)[1].lower()
    return {
        "path": rel, "folder": rel.rsplit("/", 1)[0] if "/" in rel else "", "size": 0, "mtime": 0.0,
        "duration": None, "samplerate": None, "channels": None, "subtype": None,
        "format": {".aif": "aiff", ".aiff": "aiff"}.get(suffix, suffix.lstrip(".")),
        "hash": "error:" + rel, "type_hint": type_hint(rel),
        "note": parse_note(os.path.splitext(rel.rsplit("/", 1)[-1])[0]), "error": None, "dup_of": None,
    }


def _describe(args: tuple[str, str]) -> dict:
    root, rel = args
    path = Path(root) / rel
    entry = _blank(rel)
    try:
        st = path.stat()
        entry.update(size=st.st_size, mtime=st.st_mtime, hash=file_hash(path))
    except OSError as e:  # unreadable, broken symlink, vanished mid-scan
        entry["error"] = f"cannot read file: {e.strerror or e}"
        return entry
    try:
        info = probe(path)
        entry.update(duration=round(info.duration, 4), samplerate=info.samplerate, channels=info.channels,
                     subtype=info.subtype, format=info.format)
    except AudioError as e:
        entry["error"] = str(e)
    return entry


# Shorter than this is a stub (e.g. a 46-byte WAV with one sample), not a usable sound.
MIN_DURATION = 0.001


def _flag_empty(entry: dict) -> None:
    """Mark near-empty files as errors; runs on reused entries too, so old indexes get fixed."""
    d = entry.get("duration")
    if not entry["error"] and d is not None and d < MIN_DURATION:
        entry["error"] = "empty file: less than 1 ms of audio"


def _walk(cfg: Config) -> list[str]:
    root = cfg.library.resolve()
    skip_dirs = {cfg.data_dir.resolve(), cfg.export_dir.resolve()}
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "__MACOSX"
                       and (Path(dirpath) / d).resolve() not in skip_dirs]
        for name in filenames:
            if not name.startswith(".") and os.path.splitext(name)[1].lower() in AUDIO_EXTS:
                found.append((Path(dirpath) / name).relative_to(root).as_posix())
    return sorted(found)


def scan_library(cfg: Config, progress: Callable[[int, int], None] | None = None) -> dict:
    previous = {}
    if cfg.index_path.is_file():
        try:
            previous = {f["path"]: f for f in json.loads(cfg.index_path.read_text())["files"]}
        except (ValueError, KeyError):
            previous = {}
    root = cfg.library.resolve()
    paths = _walk(cfg)
    entries: dict[str, dict] = {}
    todo = []
    unencodable = []
    for rel in list(paths):
        try:
            rel.encode("utf-8")
        except UnicodeEncodeError:  # e.g. Latin-1 names from old Windows zips
            paths.remove(rel)
            unencodable.append(rel)
            continue
        old = previous.get(rel)
        try:
            st = (root / rel).stat()
        except OSError:
            todo.append(rel)
            continue
        if old and old["size"] == st.st_size and old["mtime"] == st.st_mtime:
            entries[rel] = dict(old, dup_of=None)
        else:
            todo.append(rel)
    done = len(entries)
    if progress:
        progress(done, len(paths))
    jobs = [(str(root), rel) for rel in todo]
    if len(jobs) >= _POOL_THRESHOLD:
        with ProcessPoolExecutor() as pool:
            results = pool.map(_describe, jobs, chunksize=32)
            for entry in results:
                entries[entry["path"]] = entry
                done += 1
                if progress:
                    progress(done, len(paths))
    else:
        for job in jobs:
            entry = _describe(job)
            entries[entry["path"]] = entry
            done += 1
            if progress:
                progress(done, len(paths))
    for rel in unencodable:
        shown = rel.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
        entry = _blank(shown)
        entry["error"] = "filename is not valid UTF-8; rename the file to use it"
        entries[shown] = entry
        paths.append(shown)
    paths.sort()
    first_by_hash: dict[str, str] = {}
    files = []
    for rel in paths:
        entry = entries[rel]
        # Name-based fields are cheap: recompute so rule changes reach reused entries too.
        entry["type_hint"] = type_hint(rel)
        entry["note"] = parse_note(os.path.splitext(rel.rsplit("/", 1)[-1])[0])
        _flag_empty(entry)
        first = first_by_hash.setdefault(entry["hash"], rel)
        entry["dup_of"] = None if first == rel else first
        files.append(entry)
    index = {"version": INDEX_VERSION, "root": str(root),
             "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": files}
    cfg.index_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cfg.index_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False))
    tmp.replace(cfg.index_path)
    return index
