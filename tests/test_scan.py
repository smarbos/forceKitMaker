import json

import pytest

from forcekit.config import Config
from forcekit.scan import scan_library, type_hint


@pytest.mark.parametrize("path,hint", [
    ("Drums/Kick 01.wav", "kick"), ("x/BD_808.wav", "kick"), ("Yamaha/Snaredrums/s1.wav", "snare"),
    ("x/closedHat.wav", "hat"), ("x/Bass Drum 2.wav", "kick"), ("x/Sub Bass.wav", "bass"),
    ("Drum loops/Funk 98bpm.wav", "loop"), ("x/random thing.wav", None)])
def test_type_hint(path, hint):
    assert type_hint(path) == hint


def test_scan(library, tmp_path):
    cfg = Config(library=library, data_dir=tmp_path / "data", export_dir=tmp_path / "out")
    idx = scan_library(cfg)
    by = {f["path"]: f for f in idx["files"]}
    assert "__MACOSX/Drums/._Kick 01.wav" not in by and "Drums/.hidden.wav" not in by
    assert "Drums/readme.txt" not in by
    assert by["Synth/Lead_C3.wav"]["note"] == 60 and by["Synth/Lead_A3.aif"]["format"] == "aiff"
    assert by["Old/corrupt.wav"]["error"] and by["Old/corrupt.wav"]["duration"] is None
    assert by["Other/Kick 01.wav"]["dup_of"] == "Drums/Kick 01.wav" and by["Drums/Kick 01.wav"]["dup_of"] is None
    assert "sonidios de dios/Golpe ñandú #1.wav" in by
    assert json.loads(cfg.index_path.read_text())["files"] == idx["files"]


def test_rescan_reuses_unchanged(library, tmp_path, monkeypatch):
    cfg = Config(library=library, data_dir=tmp_path / "d", export_dir=tmp_path / "o")
    scan_library(cfg)
    calls = []
    monkeypatch.setattr("forcekit.scan.probe", lambda p: calls.append(p) or pytest.fail("re-probed"))
    scan_library(cfg)
    assert calls == []
