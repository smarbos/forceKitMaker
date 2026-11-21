from pathlib import Path

from forcekit.config import load_config


def test_load_config_defaults_and_override(tmp_path):
    c = load_config(tmp_path / "missing.json")
    assert c.library == Path.home() / "Samples/samples" and c.port == 8765
    assert c.index_path == Path.home() / "Samples/forcekit/index.json"
    f = tmp_path / "c.json"
    f.write_text('{"library": "~/x", "port": 9000}')
    c = load_config(f)
    assert c.library == Path.home() / "x" and c.port == 9000
