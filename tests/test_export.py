import numpy as np
import pytest
import soundfile as sf

from forcekit.audio import AudioError
from forcekit.drafts import DraftError
from forcekit.export import ExportExists, export_program
from forcekit.xpm import read_xpm


def test_export_drum(cfg):
    draft = {"type": "drum", "name": "Test Kit", "pads": {
        "0": "Drums/Kick 01.wav", "1": "Other/Kick 01.wav", "2": "Old/adpcm.wav",
        "3": "sonidios de dios/Golpe ñandú #1.wav"}}
    xpm = export_program(cfg, draft)
    assert xpm == cfg.export_dir / "Drums/Test Kit/Test Kit.xpm"
    pd = cfg.export_dir / "Drums/Test Kit/Test Kit_[ProgramData]"
    assert sorted(p.name for p in pd.iterdir()) == ["Golpe nandu #1.wav", "Kick 01 2.wav", "Kick 01.wav", "adpcm.wav"]
    assert sf.info(pd / "adpcm.wav").subtype == "PCM_16"
    data, _ = sf.read(pd / "Kick 01.wav")
    assert abs(np.abs(data).max() - 10 ** (-1 / 20)) < 1e-3
    assert read_xpm(xpm)[1]["data"]["drum"]["instruments"][1]["layersv"][0]["sampleFile"] == "Kick 01 2.wav"
    for p in cfg.library.rglob("*"):
        assert p.stat().st_mtime < xpm.stat().st_mtime  # library untouched


def test_export_without_normalize_copies_bytes(cfg):
    draft = {"type": "drum", "name": "Raw", "pads": {"0": "Drums/Kick 01.wav"}}
    export_program(cfg, draft, normalize=False)
    copied = cfg.export_dir / "Drums/Raw/Raw_[ProgramData]/Kick 01.wav"
    assert copied.read_bytes() == (cfg.library / "Drums/Kick 01.wav").read_bytes()


def test_export_exists(cfg):
    draft = {"type": "drum", "name": "K", "pads": {"0": "Drums/Kick 01.wav"}}
    export_program(cfg, draft)
    with pytest.raises(ExportExists):
        export_program(cfg, draft)
    export_program(cfg, draft, overwrite=True)


def test_export_synth_shared_gain(cfg):
    draft = {"type": "synth", "name": "Lead", "samples": [{"path": "Synth/Lead_A3.aif", "root": 69},
                                                         {"path": "Synth/Lead_C3.wav", "root": 60}]}
    xpm = export_program(cfg, draft)
    ins = read_xpm(xpm)[1]["data"]["drum"]["instruments"]
    assert [(i["lowNote"], i["highNote"], i["layersv"][0]["rootNote"]) for i in ins] == [(0, 64, 60), (65, 127, 69)]
    pd = cfg.export_dir / "Synths/Lead/Lead_[ProgramData]"
    peaks = [np.abs(sf.read(pd / f)[0]).max() for f in ("Lead_C3.wav", "Lead_A3.wav")]
    assert abs(max(peaks) - 10 ** (-1 / 20)) < 1e-3
    assert abs(peaks[1] / peaks[0] - 0.5) < 0.01  # relative level kept


def test_export_mp3_without_normalize_is_real_wav(cfg):
    sf.write(cfg.library / "Synth/tone.mp3", np.zeros(4410, dtype=np.float32) + 0.1, 44100, format="MP3")
    export_program(cfg, {"type": "drum", "name": "Mp3", "pads": {"0": "Synth/tone.mp3"}}, normalize=False)
    info = sf.info(cfg.export_dir / "Drums/Mp3/Mp3_[ProgramData]/tone.wav")
    assert info.format == "WAV" and info.subtype == "PCM_16"


def test_failed_overwrite_keeps_previous_export(cfg):
    draft = {"type": "drum", "name": "Keep", "pads": {"0": "Drums/Kick 01.wav", "1": "Drums/Snare 01.wav"}}
    xpm = export_program(cfg, draft)
    (cfg.library / "Drums/Snare 01.wav").unlink()
    with pytest.raises(DraftError):
        export_program(cfg, draft, overwrite=True)
    assert xpm.exists() and (cfg.export_dir / "Drums/Keep/Keep_[ProgramData]/Snare 01.wav").exists()


def test_failed_export_leaves_nothing_behind(cfg):
    draft = {"type": "drum", "name": "Broken", "pads": {"0": "Drums/Kick 01.wav", "1": "Old/corrupt.wav"}}
    with pytest.raises(AudioError):
        export_program(cfg, draft)
    assert list((cfg.export_dir / "Drums").iterdir()) == []


def test_export_sets_sample_start_and_end(cfg):
    sr = 44100
    hit = np.concatenate([np.zeros(2205), 0.5 * np.sin(2 * np.pi * 200 * np.arange(4410) / sr), np.zeros(22050)])
    sf.write(cfg.library / "Drums/late hit.wav", hit.astype(np.float32), sr, subtype="PCM_16")
    for normalize in (True, False):
        xpm = export_program(cfg, {"type": "drum", "name": f"Ends {normalize}", "pads": {
            "0": "Drums/Kick 01.wav", "1": "Drums/late hit.wav"}}, normalize=normalize)
        ins = read_xpm(xpm)[1]["data"]["drum"]["instruments"]
        kick = ins[0]["layersv"][0]["sliceInfo"]
        assert (kick["Start"], kick["End"]) == (0, int(0.3 * sr) - 1)
        late = ins[1]["layersv"][0]["sliceInfo"]
        assert late["Start"] == 2206 - 44 and abs(late["End"] - (2205 + 4410 - 1 + 441)) <= 2


def test_export_writes_colors(cfg):
    draft = {"type": "drum", "name": "Colors", "pads": {"0": "Drums/Kick 01.wav"}}
    _, doc = read_xpm(export_program(cfg, draft, colors={0: 0xFF0000}))
    assert doc["data"]["programPads"]["pads"]["value0"] == 0xFF0000


def test_dot_dot_name_does_not_touch_other_exports(cfg):
    keep = export_program(cfg, {"type": "drum", "name": "Keep", "pads": {"0": "Drums/Kick 01.wav"}})
    out = export_program(cfg, {"type": "drum", "name": "..", "pads": {"0": "Drums/Kick 01.wav"}}, overwrite=True)
    assert keep.is_file() and out.parent.name == "untitled"
