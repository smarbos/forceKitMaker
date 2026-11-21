import json

from forcekit.cli import main


def test_cli_scan(library, tmp_path, capsys):
    cfgf = tmp_path / "c.json"
    cfgf.write_text(json.dumps({"library": str(library), "data_dir": str(tmp_path / "d"),
                                "export_dir": str(tmp_path / "o")}))
    assert main(["scan", "--config", str(cfgf)]) == 0
    out = capsys.readouterr().out
    assert "errors: 1" in out and "duplicates: 1" in out and (tmp_path / "d/index.json").exists()


def test_cli_scan_library_override(library, tmp_path, capsys):
    cfgf = tmp_path / "c.json"
    cfgf.write_text(json.dumps({"library": "/nonexistent", "data_dir": str(tmp_path / "d"),
                                "export_dir": str(tmp_path / "o")}))
    assert main(["scan", "--config", str(cfgf), "--library", str(library / "Synth")]) == 0
    assert "files: 2" in capsys.readouterr().out


def test_cli_scan_missing_library(tmp_path, capsys):
    cfgf = tmp_path / "c.json"
    cfgf.write_text(json.dumps({"library": str(tmp_path / "nope"), "data_dir": str(tmp_path / "d")}))
    assert main(["scan", "--config", str(cfgf)]) == 1
    assert "not found" in capsys.readouterr().err
