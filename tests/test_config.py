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


def test_force_defaults_and_save_keeps_other_keys(tmp_path):
    import json
    from forcekit.config import save_force_settings
    f = tmp_path / "c.json"
    f.write_text('{"port": 9000}')
    c = load_config(f)
    assert (c.force_host, c.force_user, c.force_dir) == ("192.168.0.27", "root", "/media/96B6-573E/forcekit")
    save_force_settings(c, "10.0.0.5", "root", "/media/X/forcekit")
    assert json.loads(f.read_text()) == {"port": 9000, "force_host": "10.0.0.5", "force_user": "root",
                                         "force_dir": "/media/X/forcekit"}
    c2 = load_config(f)
    assert c2.force_host == "10.0.0.5" and c2.port == 9000 and c.force_host == "10.0.0.5"
