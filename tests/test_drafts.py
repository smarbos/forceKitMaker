import pytest

from forcekit.drafts import DraftError, delete_draft, list_drafts, load_draft, save_draft, validate_draft


def test_validate_rejects():
    for bad in [{"type": "x", "name": "a"},
                {"type": "drum", "name": "a", "pads": {"64": "a.wav"}},
                {"type": "drum", "name": "a", "pads": {"0": "../x.wav"}},
                {"type": "drum", "name": "a", "pads": {"0": "/etc/passwd"}},
                {"type": "synth", "name": "a", "samples": [{"path": "a.wav", "root": 60},
                                                           {"path": "b.wav", "root": 60}]},
                {"type": "synth", "name": "a", "samples": [{"path": "a.wav", "root": 128}]}]:
        with pytest.raises(DraftError):
            validate_draft(bad)


def test_draft_crud(cfg):
    stem = save_draft(cfg, {"type": "drum", "name": "Kit/1", "pads": {}})
    assert stem == "Kit1" and load_draft(cfg, stem)["name"] == "Kit/1"
    assert [d["stem"] for d in list_drafts(cfg)] == ["Kit1"]
    delete_draft(cfg, stem)
    assert list_drafts(cfg) == []


def test_load_draft_cannot_escape(cfg):
    with pytest.raises(DraftError):
        load_draft(cfg, "../../etc/passwd")


def test_validate_names_and_colors():
    from forcekit.drafts import DraftError, validate_draft
    ok = {"type": "drum", "name": "K", "pads": {"0": "a.wav"}, "names": {"0": "Big Kick"}, "colors": {"0": "#ff0000"}}
    validate_draft(ok)
    for bad in [dict(ok, names={"99": "x"}), dict(ok, names={"0": 3}), dict(ok, names={"0": "x" * 65}),
                dict(ok, colors={"0": "red"}), dict(ok, colors={"64": "#ff0000"}), dict(ok, names=[])]:
        with pytest.raises(DraftError):
            validate_draft(bad)
