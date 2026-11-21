"""Turn a draft into a Force program on disk."""
from __future__ import annotations

import shutil
from pathlib import Path

from .audio import browser_playable, export_subtype, gain_to, load, peak, probe, write_wav
from .config import Config
from .drafts import DraftError, validate_draft
from .names import key_ranges, safe_name, unique_name
from .xpm import SampleRef, build_drum, build_keygroup, write_xpm

TARGET_PEAK_DB = -1.0


class ExportExists(Exception):
    def __init__(self, path: Path):
        super().__init__(f"{path} already exists")
        self.path = path


def _source(cfg: Config, rel: str) -> Path:
    root = cfg.library.resolve()
    path = (root / rel).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise DraftError(f"sample not found in library: {rel}")
    return path


def export_program(cfg: Config, draft: dict, normalize: bool = True, overwrite: bool = False) -> Path:
    validate_draft(draft)
    is_drum = draft["type"] == "drum"
    name = safe_name(draft["name"])
    folder = cfg.export_dir / ("Drums" if is_drum else "Synths")
    xpm_path = folder / f"{name}.xpm"
    data_dir = folder / f"{name}_[ProgramData]"
    if xpm_path.exists() or data_dir.exists():
        if not overwrite:
            raise ExportExists(xpm_path)
        xpm_path.unlink(missing_ok=True)
        shutil.rmtree(data_dir, ignore_errors=True)

    if is_drum:
        items = [(int(pad), rel) for pad, rel in sorted(draft["pads"].items(), key=lambda kv: int(kv[0]))]
    else:
        items = [(s["root"], s["path"]) for s in sorted(draft["samples"], key=lambda s: s["root"])]
    sources = [(key, _source(cfg, rel)) for key, rel in items]

    data_dir.mkdir(parents=True, exist_ok=True)
    taken: set[str] = set()
    refs: list[tuple[int, SampleRef, Path]] = []
    for key, src in sources:
        sample_name = unique_name(safe_name(src.stem), taken)
        refs.append((key, SampleRef(sample_name, f"{sample_name}.wav"), src))

    shared_gain = 1.0
    if normalize and not is_drum and refs:
        shared_gain = gain_to(TARGET_PEAK_DB, max(peak(load(src)[0]) for _, _, src in refs))

    for _, ref, src in refs:
        dest = data_dir / ref.file
        info = probe(src)
        if not normalize and browser_playable(info.format, info.subtype):
            shutil.copyfile(src, dest)
            continue
        audio, sr, subtype = load(src)
        if normalize:
            audio = audio * (gain_to(TARGET_PEAK_DB, peak(audio)) if is_drum else shared_gain)
        write_wav(dest, audio, sr, export_subtype(subtype))

    if is_drum:
        header, doc = build_drum(name, {key: ref for key, ref, _ in refs})
    else:
        roots = [key for key, _, _ in refs]
        zones = [(ref, root, low, high) for (root, ref, _), (low, high) in zip(refs, key_ranges(roots))]
        header, doc = build_keygroup(name, zones)
    write_xpm(xpm_path, header, doc)
    return xpm_path
