"""Shared fixtures: a small sample library with the awkward cases we care about."""
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

SR = 44100


def _sine(freq: float, seconds: float, amp: float, decay: float = 0.0) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    env = np.exp(-decay * t) if decay else 1.0
    return (amp * env * np.sin(2 * np.pi * freq * t)).astype(np.float32)


@pytest.fixture
def library(tmp_path) -> Path:
    root = tmp_path / "library"
    files = {
        "Drums/Kick 01.wav": (_sine(60, 0.3, 0.5, decay=8), "PCM_16", "WAV"),
        "Drums/Snare 01.wav": ((np.random.default_rng(1).uniform(-0.4, 0.4, int(SR * 0.25))).astype(np.float32), "PCM_16", "WAV"),
        "Drums/Hats/HH closed.wav": ((np.random.default_rng(2).uniform(-0.2, 0.2, int(SR * 0.1))).astype(np.float32), "PCM_24", "WAV"),
        "Synth/Lead_C3.wav": (_sine(261.63, 1.0, 0.5), "PCM_16", "WAV"),
        "Synth/Lead_A3.aif": (_sine(440.0, 1.0, 0.25), "PCM_16", "AIFF"),
        "Old/adpcm.wav": (_sine(220, 0.5, 0.3), "IMA_ADPCM", "WAV"),
        "sonidios de dios/Golpe ñandú #1.wav": (_sine(110, 0.2, 0.3, decay=10), "PCM_16", "WAV"),
    }
    for rel, (data, subtype, fmt) in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        sf.write(p, data, SR, subtype=subtype, format=fmt)
    (root / "Old/corrupt.wav").write_bytes(b"RIFF\x00\x00garbage")
    (root / "Other").mkdir()
    (root / "Other/Kick 01.wav").write_bytes((root / "Drums/Kick 01.wav").read_bytes())
    (root / "__MACOSX/Drums").mkdir(parents=True)
    (root / "__MACOSX/Drums/._Kick 01.wav").write_bytes(b"\x00\x05\x16\x07")
    (root / "Drums/.hidden.wav").write_bytes((root / "Drums/Kick 01.wav").read_bytes())
    (root / "Drums/readme.txt").write_text("not audio")
    return root


@pytest.fixture
def cfg(library, tmp_path):
    from forcekit.config import Config
    return Config(library=library, data_dir=tmp_path / "data", export_dir=tmp_path / "out")
