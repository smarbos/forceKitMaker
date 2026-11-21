"""Reading, writing and analysing audio files."""
from __future__ import annotations

import io
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

BROWSER_WAV_SUBTYPES = {"PCM_16", "PCM_24", "PCM_32", "FLOAT"}
_FORMATS = {"WAV": "wav", "WAVEX": "wav", "AIFF": "aiff", "MP3": "mp3"}
_EXT_FORMATS = {".wav": "wav", ".aif": "aiff", ".aiff": "aiff", ".mp3": "mp3"}


class AudioError(Exception):
    pass


@dataclass
class AudioInfo:
    duration: float
    samplerate: int
    channels: int
    subtype: str
    format: str


def probe(path: Path) -> AudioInfo:
    path = Path(path)
    try:
        info = sf.info(str(path))
        fmt = _FORMATS.get(info.format, _EXT_FORMATS.get(path.suffix.lower(), info.format.lower()))
        return AudioInfo(info.frames / info.samplerate, info.samplerate, info.channels, info.subtype, fmt)
    except Exception as sf_error:  # libsndfile can't read it; ask ffprobe
        try:
            out = subprocess.run(
                ["ffprobe", "-v", "error", "-show_streams", "-select_streams", "a:0", "-of", "json", str(path)],
                capture_output=True, check=True, timeout=30,
            ).stdout
            stream = json.loads(out)["streams"][0]
            return AudioInfo(
                float(stream.get("duration") or 0.0),
                int(stream["sample_rate"]),
                int(stream["channels"]),
                str(stream.get("codec_name", "unknown")).upper(),
                _EXT_FORMATS.get(path.suffix.lower(), path.suffix.lower().lstrip(".")),
            )
        except Exception:
            raise AudioError(f"cannot read audio: {sf_error}") from sf_error


def load(path: Path) -> tuple[np.ndarray, int, str]:
    path = Path(path)
    try:
        with sf.SoundFile(str(path)) as f:
            data = f.read(dtype="float32", always_2d=True)
            return data, f.samplerate, f.subtype
    except Exception as sf_error:
        try:
            wav = subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(path), "-f", "wav", "-c:a", "pcm_f32le", "-"],
                capture_output=True, check=True, timeout=120,
            ).stdout
            data, sr = sf.read(io.BytesIO(wav), dtype="float32", always_2d=True)
            return data, sr, probe(path).subtype
        except Exception:
            raise AudioError(f"cannot decode audio: {sf_error}") from sf_error


def browser_playable(entry_format: str, subtype: str | None) -> bool:
    if entry_format == "mp3":
        return True
    return entry_format == "wav" and subtype in BROWSER_WAV_SUBTYPES


def export_subtype(subtype: str) -> str:
    return "PCM_24" if subtype in {"PCM_24", "PCM_32", "FLOAT", "DOUBLE"} else "PCM_16"


def write_wav(path: Path, data: np.ndarray, samplerate: int, subtype: str) -> None:
    sf.write(str(path), np.clip(data, -1.0, 1.0), samplerate, subtype=subtype, format="WAV")


def peak(data: np.ndarray) -> float:
    return float(np.max(np.abs(data))) if data.size else 0.0


def gain_to(target_peak_db: float, current_peak: float) -> float:
    if current_peak <= 0:
        return 1.0
    return 10 ** (target_peak_db / 20) / current_peak


def detect_root(path: Path) -> int | None:
    """Root note via YIN on the first second; None if not clearly pitched."""
    data, sr, _ = load(path)
    x = data[: sr].mean(axis=1).astype(np.float64)
    window, hop, threshold = 1024, 512, 0.15
    min_tau, max_tau = max(2, int(sr / 2000)), int(sr / 30)
    frame_len = window + max_tau
    if len(x) < frame_len:
        x = np.pad(x, (0, frame_len - len(x)))
    f0s, frames = [], 0
    for start in range(0, len(x) - frame_len + 1, hop):
        frames += 1
        frame = x[start: start + frame_len]
        if np.sqrt(np.mean(frame[:window] ** 2)) < 1e-4:
            continue
        tau = _yin_tau(frame, window, min_tau, max_tau, threshold)
        if tau:
            f0s.append(sr / tau)
    if not frames or len(f0s) < 0.3 * frames:
        return None
    midi = round(69 + 12 * math.log2(float(np.median(f0s)) / 440.0))
    return midi if 0 <= midi <= 127 else None


def _yin_tau(frame: np.ndarray, window: int, min_tau: int, max_tau: int, threshold: float) -> float | None:
    n = len(frame)
    size = 1 << (n + window).bit_length()
    acf = np.fft.irfft(np.fft.rfft(frame, size) * np.conj(np.fft.rfft(frame[:window], size)), size)[: max_tau + 1]
    sq = np.concatenate([[0.0], np.cumsum(frame ** 2)])
    energy = sq[window: window + max_tau + 1] - sq[: max_tau + 1]  # sum x[tau:tau+window]^2
    diff = energy[0] + energy - 2 * acf
    diff[0] = 0.0
    cumulative = np.cumsum(diff[1:])
    cmndf = np.ones_like(diff)
    with np.errstate(divide="ignore", invalid="ignore"):
        cmndf[1:] = np.where(cumulative > 0, diff[1:] * np.arange(1, max_tau + 1) / cumulative, 1.0)
    below = np.nonzero(cmndf[min_tau: max_tau] < threshold)[0]
    if not below.size:
        return None
    tau = int(below[0]) + min_tau
    while tau + 1 < max_tau and cmndf[tau + 1] < cmndf[tau]:
        tau += 1
    a, b, c = cmndf[tau - 1], cmndf[tau], cmndf[tau + 1]
    denom = a - 2 * b + c
    return tau + (0.5 * (a - c) / denom if denom else 0.0)
