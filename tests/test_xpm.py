from forcekit.xpm import TEMPLATES, SampleRef, build_drum, build_keygroup, read_xpm, write_xpm


def test_templates_are_stripped():
    for name in ("drum.xpm", "keygroup.xpm"):
        _, doc = read_xpm(TEMPLATES / name)
        assert doc["data"]["samples"] == []
        assert all(l["sampleFile"] == "" for i in doc["data"]["drum"]["instruments"] for l in i["layersv"])


def test_roundtrip(tmp_path):
    h, d = read_xpm(TEMPLATES / "drum.xpm")
    write_xpm(tmp_path / "x.xpm", h, d)
    assert read_xpm(tmp_path / "x.xpm") == (h, d) and h.startswith(b"ACVS\n")


def test_build_drum():
    h, d = build_drum("My Kit ñ", {0: SampleRef("Kick 01", "Kick 01.wav"), 17: SampleRef("Snare", "Snare.wav")})
    data = d["data"]
    ins = data["drum"]["instruments"]
    assert data["type"] == 0 and data["name"] == "My Kit ñ" and len(ins) == 128
    assert ins[0]["layersv"][0]["sampleFile"] == "Kick 01.wav" and ins[17]["layersv"][0]["sampleName"] == "Snare"
    assert ins[1]["layersv"][0]["sampleFile"] == ""
    assert [s["path"] for s in data["samples"]] == ["Kick 01.wav", "Snare.wav"]


def test_build_keygroup():
    zones = [(SampleRef("A", "A.wav"), 48, 0, 54), (SampleRef("B", "B.wav"), 60, 55, 127)]
    data = build_keygroup("Keys", zones)[1]["data"]
    assert data["type"] == 1 and data["keygroup"]["numKeygroups"] == 2
    i0, i1 = data["drum"]["instruments"]
    assert (i0["lowNote"], i0["highNote"], i1["lowNote"], i1["highNote"]) == (0, 54, 55, 127)
    assert i1["layersv"][0]["rootNote"] == 60 and i1["layersv"][0]["keyTrackEnable"] is True
    assert data["samples"][1]["metadata"]["rootNote"] == 60


def test_templates_not_mutated():
    build_drum("a", {0: SampleRef("x", "x.wav")})
    assert build_drum("b", {})[1]["data"]["drum"]["instruments"][0]["layersv"][0]["sampleFile"] == ""


def test_layers_get_start_and_end():
    d = build_drum("k", {3: SampleRef("x", "x.wav", start=10, end=16606)})[1]["data"]
    assert d["drum"]["instruments"][3]["layersv"][0]["sliceInfo"]["Start"] == 10
    assert d["drum"]["instruments"][3]["layersv"][0]["sliceInfo"]["End"] == 16606
    k = build_keygroup("s", [(SampleRef("a", "a.wav", start=0, end=999), 60, 0, 127)])[1]["data"]
    assert k["drum"]["instruments"][0]["layersv"][0]["sliceInfo"]["End"] == 999


def test_drum_pad_colors():
    a, b = SampleRef("A", "A.wav", 0, 9), SampleRef("B", "B.wav", 0, 9)
    _, doc = build_drum("K", {0: a, 5: b}, colors={0: 0xFF2A2A, 5: 0x1AD8FF})
    pp = doc["data"]["programPads"]
    assert pp["Universal"]["value0"] is False
    assert pp["pads"]["value0"] == 0xFF2A2A and pp["pads"]["value5"] == 0x1AD8FF and pp["pads"]["value1"] == 0
    _, plain = build_drum("K", {0: a})
    assert plain["data"]["programPads"]["Universal"]["value0"] is True
