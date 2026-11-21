from pathlib import Path

import pytest

from forcekit.send import ForceError, SendExists, send_program, test_connection as check_connection


def make_program(root: Path, name: str, samples: list[str]) -> Path:
    folder = root / "Drums" / name
    data = folder / f"{name}_[ProgramData]"
    data.mkdir(parents=True)
    (folder / f"{name}.xpm").write_bytes(b"xpm-" + name.encode())
    for s in samples:
        (data / s).write_bytes(b"wav")
    return folder


def remote(cfg, name):
    return Path(cfg.force_dir) / "Drums" / name


def test_send_first_time(force_cfg, tmp_path):
    folder = make_program(tmp_path / "out", "Kit", ["a.wav", "b.wav"])
    path = send_program(force_cfg, folder)
    r = remote(force_cfg, "Kit")
    assert path == str(r)
    assert (r / "Kit.xpm").read_bytes() == b"xpm-Kit"
    assert sorted(p.name for p in (r / "Kit_[ProgramData]").iterdir()) == ["a.wav", "b.wav"]


def test_send_refuses_existing_without_overwrite(force_cfg, tmp_path):
    folder = make_program(tmp_path / "out", "Kit", ["a.wav"])
    send_program(force_cfg, folder)
    with pytest.raises(SendExists):
        send_program(force_cfg, folder)


def test_send_overwrite_replaces(force_cfg, tmp_path):
    send_program(force_cfg, make_program(tmp_path / "v1", "Kit", ["old.wav"]))
    send_program(force_cfg, make_program(tmp_path / "v2", "Kit", ["new.wav"]), overwrite=True)
    assert [p.name for p in (remote(force_cfg, "Kit") / "Kit_[ProgramData]").iterdir()] == ["new.wav"]


def test_failed_send_keeps_old(force_cfg, tmp_path, monkeypatch):
    send_program(force_cfg, make_program(tmp_path / "v1", "Kit", ["old.wav"]))
    monkeypatch.setattr("forcekit.send._tar_stream", lambda folder: b"not a tar archive" * 100)
    with pytest.raises(ForceError):
        send_program(force_cfg, make_program(tmp_path / "v2", "Kit", ["new.wav"]), overwrite=True)
    drums = Path(force_cfg.force_dir) / "Drums"
    assert [p.name for p in (drums / "Kit" / "Kit_[ProgramData]").iterdir()] == ["old.wav"]
    assert [p.name for p in drums.iterdir()] == ["Kit"]  # no temp folder left


def test_send_quotes_names(force_cfg, tmp_path):
    name = 'It\'s a "$kit" [1]'
    send_program(force_cfg, make_program(tmp_path / "out", name, ["x.wav"]))
    assert (remote(force_cfg, name) / f"{name}.xpm").is_file()


def test_connection_ok_and_failure(force_cfg):
    assert "forcekit" in check_connection(force_cfg) or check_connection(force_cfg)
    force_cfg.ssh_command = ["false"]
    with pytest.raises(ForceError):
        check_connection(force_cfg)
