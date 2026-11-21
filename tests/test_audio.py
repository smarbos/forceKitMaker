import pytest

from forcekit.audio import (AudioError, browser_playable, detect_root, export_subtype, gain_to,
                            load, probe)


def test_probe_wav_and_aiff(library):
    i = probe(library / "Drums/Kick 01.wav")
    assert (i.samplerate, i.channels, i.subtype) == (44100, 1, "PCM_16")
    assert abs(i.duration - 0.3) < 0.01
    assert probe(library / "Synth/Lead_A3.aif").format == "aiff"


def test_probe_corrupt_raises(library):
    with pytest.raises(AudioError):
        probe(library / "Old/corrupt.wav")


def test_load_adpcm(library):
    data, sr, subtype = load(library / "Old/adpcm.wav")
    assert data.ndim == 2 and data.shape[0] > 0 and subtype == "IMA_ADPCM"


def test_browser_playable():
    assert browser_playable("wav", "PCM_24") and browser_playable("mp3", "MPEG_LAYER_III")
    assert not browser_playable("wav", "IMA_ADPCM") and not browser_playable("aiff", "PCM_16")


def test_export_subtype():
    assert export_subtype("FLOAT") == "PCM_24" and export_subtype("PCM_U8") == "PCM_16"


def test_gain_to():
    assert abs(gain_to(-1.0, 0.5) - 10 ** (-1 / 20) / 0.5) < 1e-6 and gain_to(-1.0, 0.0) == 1.0


def test_detect_root(library):
    assert detect_root(library / "Synth/Lead_C3.wav") == 60
    assert detect_root(library / "Synth/Lead_A3.aif") == 69
    assert detect_root(library / "Drums/Snare 01.wav") is None
