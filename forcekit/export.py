"""Turn a draft into a Force program on disk."""
from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

from .audio import detect_bounds, export_subtype, force_copyable, gain_to, load, peak, probe, write_wav
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


def export_program(cfg: Config, draft: dict, normalize: bool = True, overwrite: bool = False,
                   colors: dict[int, int] | None = None) -> Path:
    validate_draft(draft)
    is_drum = draft["type"] == "drum"
    name = safe_name(draft["name"])
    type_dir = cfg.export_dir / ("Drums" if is_drum else "Synths")
    folder = type_dir / name  # one folder per program: <name>.xpm + <name>_[ProgramData]/
    xpm_path = folder / f"{name}.xpm"
    data_dir = folder / f"{name}_[ProgramData]"
    if folder.exists() and not overwrite:
        raise ExportExists(xpm_path)

    if is_drum:
        items = [(int(pad), rel) for pad, rel in sorted(draft["pads"].items(), key=lambda kv: int(kv[0]))]
    else:
        items = [(s["root"], s["path"]) for s in sorted(draft["samples"], key=lambda s: s["root"])]
    sources = [(key, _source(cfg, rel)) for key, rel in items]  # fails before anything is touched

    taken: set[str] = set()
    refs: list[tuple[int, SampleRef, Path]] = []
    for key, src in sources:
        sample_name = unique_name(safe_name(src.stem), taken)
        refs.append((key, SampleRef(sample_name, f"{sample_name}.wav"), src))

    type_dir.mkdir(parents=True, exist_ok=True)
    staging = type_dir / f".{name}.forcekit-tmp"  # becomes the program folder once complete
    shutil.rmtree(staging, ignore_errors=True)
    staged_data = staging / data_dir.name
    staged_data.mkdir(parents=True)
    try:
        refs = _write_samples(refs, staged_data, normalize, is_drum)
        if is_drum:
            header, doc = build_drum(name, {key: ref for key, ref, _ in refs}, colors)
        else:
            roots = [key for key, _, _ in refs]
            zones = [(ref, root, low, high) for (root, ref, _), (low, high) in zip(refs, key_ranges(roots))]
            header, doc = build_keygroup(name, zones)
        write_xpm(staging / xpm_path.name, header, doc)
        # Everything is built; only now replace the previous export.
        shutil.rmtree(folder, ignore_errors=True)
        staging.rename(folder)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return xpm_path


def _write_samples(refs: list[tuple[int, SampleRef, Path]], dest_dir: Path, normalize: bool,
                   is_drum: bool) -> list[tuple[int, SampleRef, Path]]:
    """Write each sample; return refs with playback start/end detected from the written audio."""
    shared_gain = 1.0
    if normalize and not is_drum and refs:
        shared_gain = gain_to(TARGET_PEAK_DB, max(peak(load(src)[0]) for _, _, src in refs))
    done = []
    for key, ref, src in refs:
        dest = dest_dir / ref.file
        info = probe(src)
        audio, sr, subtype = load(src)
        if not normalize and force_copyable(info.format, info.subtype):
            shutil.copyfile(src, dest)
        else:
            if normalize:
                audio = audio * (gain_to(TARGET_PEAK_DB, peak(audio)) if is_drum else shared_gain)
            write_wav(dest, audio, sr, export_subtype(subtype))
        start, end = detect_bounds(audio, sr)
        done.append((key, replace(ref, start=start, end=end), src))
    return done
