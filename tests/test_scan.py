import json

import pytest

from forcekit.config import Config
from forcekit.scan import scan_library, type_hint


@pytest.mark.parametrize("path,hint", [
    ("Drums/Kick 01.wav", "kick"), ("x/BD_808.wav", "kick"), ("Yamaha/Snaredrums/s1.wav", "snare"),
    ("x/closedHat.wav", "hat"), ("x/Bass Drum 2.wav", "kick"), ("x/Sub Bass.wav", "bass"),
    ("Drum loops/Funk 98bpm.wav", "loop"), ("808/CHH.wav", "hat"), ("808/OHH.wav", "hat"), ("x/random thing.wav", None)])
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


def test_rescan_of_other_library_ignores_old_index(library, tmp_path):
    data = tmp_path / "d"
    scan_library(Config(library=library, data_dir=data, export_dir=tmp_path / "o"))
    idx = scan_library(Config(library=library / "Synth", data_dir=data, export_dir=tmp_path / "o"))
    assert sorted(f["path"] for f in idx["files"]) == ["Lead_A3.aif", "Lead_C3.wav"]
    assert all(f["folder"] == "" for f in idx["files"])


def test_scan_survives_unreadable_files(library, tmp_path):
    import os
    locked = library / "Drums/locked.wav"
    locked.write_bytes((library / "Drums/Kick 01.wav").read_bytes())
    locked.chmod(0)
    (library / "Drums/broken.wav").symlink_to(library / "Drums/missing-target.wav")
    os.close(os.open(os.fsencode(library / "Drums") + b"/caf\xe9.wav", os.O_CREAT | os.O_WRONLY))
    try:
        idx = scan_library(Config(library=library, data_dir=tmp_path / "d", export_dir=tmp_path / "o"))
    finally:
        locked.chmod(0o644)
    by = {f["path"]: f for f in idx["files"]}
    assert by["Drums/locked.wav"]["error"] and by["Drums/broken.wav"]["error"]
    bad = [f for f in idx["files"] if f["path"].startswith("Drums/caf")]
    assert len(bad) == 1 and "UTF-8" in bad[0]["error"]
    assert by["Drums/Kick 01.wav"]["error"] is None


def test_near_empty_files_are_flagged(library, tmp_path):
    import numpy as np
    import soundfile as sf
    sf.write(library / "Drums/stub.wav", np.zeros(1, dtype=np.float32), 48000, subtype="PCM_16")
    cfg = Config(library=library, data_dir=tmp_path / "d", export_dir=tmp_path / "o")
    for _ in range(2):  # fresh scan, then a re-scan that reuses the entry
        by = {f["path"]: f for f in scan_library(cfg)["files"]}
        assert "empty" in by["Drums/stub.wav"]["error"]
        assert by["Drums/Hats/HH closed.wav"]["error"] is None


def test_rescan_refreshes_name_based_fields(library, tmp_path):
    cfg = Config(library=library, data_dir=tmp_path / "d", export_dir=tmp_path / "o")
    scan_library(cfg)
    idx = json.loads(cfg.index_path.read_text())
    for f in idx["files"]:  # simulate an index written by an older hint table / note parser
        f["type_hint"], f["note"] = "fx", None
    cfg.index_path.write_text(json.dumps(idx))
    by = {f["path"]: f for f in scan_library(cfg)["files"]}
    assert by["Drums/Kick 01.wav"]["type_hint"] == "kick" and by["Synth/Lead_C3.wav"]["note"] == 60
