import io
import json
import threading
import urllib.error
import urllib.request
from urllib.parse import quote

import pytest
import soundfile as sf

from forcekit.scan import scan_library
from forcekit.server import make_server


@pytest.fixture
def srv(cfg):
    scan_library(cfg)
    server = make_server(cfg, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _request(base, path, method="GET", body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"} if data else {})
    try:
        return urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        return e


def get(base, path):
    return _request(base, path)


def get_status(base, path):
    return _request(base, path).status


def get_json(base, path):
    r = _request(base, path)
    assert r.status == 200
    return json.loads(r.read())


def put_json(base, path, body):
    r = _request(base, path, "PUT", body)
    assert r.status == 200
    return json.loads(r.read())


def post_json(base, path, body):
    r = _request(base, path, "POST", body)
    return r.status, json.loads(r.read())


def test_tree_and_folder(srv):
    tree = get_json(srv, "/api/tree")
    names = {c["name"] for c in tree["children"]}
    assert {"Drums", "Synth", "Old", "sonidios de dios"} <= names and "__MACOSX" not in names
    files = get_json(srv, "/api/folder?path=" + quote("sonidios de dios"))
    assert files[0]["path"] == "sonidios de dios/Golpe ñandú #1.wav"


def test_audio_passthrough_and_transcode(srv, library):
    r = get(srv, "/api/audio?path=" + quote("Drums/Kick 01.wav"))
    assert r.status == 200 and r.read() == (library / "Drums/Kick 01.wav").read_bytes()
    r = get(srv, "/api/audio?path=" + quote("Old/adpcm.wav"))
    assert sf.info(io.BytesIO(r.read())).subtype == "PCM_16"
    r = get(srv, "/api/audio?path=" + quote("Synth/Lead_A3.aif"))
    assert r.headers["Content-Type"] == "audio/wav"


def test_audio_errors(srv):
    assert get_status(srv, "/api/audio?path=" + quote("Old/corrupt.wav")) == 422
    assert get_status(srv, "/api/audio?path=" + quote("../etc/passwd")) == 403
    assert get_status(srv, "/api/audio?path=" + quote("/etc/passwd")) == 403
    assert get_status(srv, "/api/audio?path=" + quote("Drums/nope.wav")) == 404


def test_root(srv):
    assert get_json(srv, "/api/root?path=" + quote("Synth/Lead_C3.wav")) == {"root": 60, "source": "filename"}
    assert get_json(srv, "/api/root?path=" + quote("Synth/Lead_A3.aif")) == {"root": 69, "source": "filename"}
    assert get_json(srv, "/api/root?path=" + quote("sonidios de dios/Golpe ñandú #1.wav")) == {
        "root": 45, "source": "detected"}
    assert get_json(srv, "/api/root?path=" + quote("Drums/Snare 01.wav")) == {"root": 60, "source": "default"}


def test_drafts_and_export(srv):
    d = {"type": "drum", "name": "Web Kit", "pads": {"0": "Drums/Kick 01.wav"}}
    assert put_json(srv, "/api/drafts/" + quote("Web Kit"), d)["stem"] == "Web Kit"
    assert get_json(srv, "/api/drafts")[0]["name"] == "Web Kit"
    assert get_json(srv, "/api/drafts/" + quote("Web Kit"))["pads"] == {"0": "Drums/Kick 01.wav"}
    assert post_json(srv, "/api/export", {"draft": d, "normalize": True, "overwrite": False})[0] == 200
    status, body = post_json(srv, "/api/export", {"draft": d, "normalize": True, "overwrite": False})
    assert status == 409 and body["exists"]
    assert post_json(srv, "/api/export", {"draft": {"type": "zzz"}, "normalize": True, "overwrite": False})[0] == 400
    assert _request(srv, "/api/drafts/" + quote("Web Kit"), "DELETE").status == 204
    assert get_json(srv, "/api/drafts") == []


def test_index_page(srv):
    html = get(srv, "/").read().decode()
    for el in ['id="tree"', 'id="files"', 'id="program"', 'id="pads"', 'id="synth-list"', 'id="export"',
               "/static/app.js"]:
        assert el in html
    assert get_status(srv, "/static/app.js") == 200
    assert get_status(srv, "/static/style.css") == 200
    assert get_status(srv, "/static/../server.py") in (403, 404)
    assert get_status(srv, "/static/%2e%2e/server.py") in (403, 404)


def test_first_save_of_accented_name_keeps_draft(srv, cfg):
    d = {"type": "drum", "name": "Café", "pads": {}}
    assert put_json(srv, "/api/drafts/" + quote("Café"), d)["stem"] == "Cafe"
    assert (cfg.drafts_dir / "Cafe.json").exists()
    assert put_json(srv, "/api/drafts/Cafe", dict(d, pads={"0": "Drums/Kick 01.wav"}))["stem"] == "Cafe"
    assert (cfg.drafts_dir / "Cafe.json").exists()


def test_save_refuses_to_clobber_other_draft(srv, cfg):
    put_json(srv, "/api/drafts/", {"type": "drum", "name": "Techno", "pads": {"0": "Drums/Kick 01.wav"}})
    r = _request(srv, "/api/drafts/", "PUT", {"type": "drum", "name": "Techno", "pads": {}})
    assert r.status == 409 and json.loads(r.read())["exists"]
    put_json(srv, "/api/drafts/", {"type": "drum", "name": "Other", "pads": {}})
    r = _request(srv, "/api/drafts/Other", "PUT", {"type": "drum", "name": "Techno", "pads": {}})
    assert r.status == 409
    assert get_json(srv, "/api/drafts/Techno")["pads"] == {"0": "Drums/Kick 01.wav"}


def test_unexpected_errors_return_json_500(srv, cfg):
    cfg.export_dir.parent.mkdir(parents=True, exist_ok=True)
    cfg.export_dir.write_text("not a folder")
    status, body = post_json(srv, "/api/export", {"draft": {"type": "drum", "name": "X", "pads": {
        "0": "Drums/Kick 01.wav"}}, "normalize": True, "overwrite": False})
    assert status == 500 and body["error"]


def test_export_colors_by_type(srv, cfg):
    from forcekit.xpm import read_xpm
    d = {"type": "drum", "name": "Typed", "pads": {"0": "Drums/Kick 01.wav", "1": "Drums/Snare 01.wav"}}
    status, body = post_json(srv, "/api/export", {"draft": d, "normalize": True, "overwrite": False})
    assert status == 200
    pads = read_xpm(body["path"])[1]["data"]["programPads"]["pads"]
    assert pads["value0"] == 0xFF0000 and pads["value1"] == 0xFFD21A


def test_autofill_recursive(srv):
    status, body = post_json(srv, "/api/autofill", {"folder": "", "one_shots": False})
    assert status == 200
    pads = body["pads"]
    assert pads["0"] == "Drums/Kick 01.wav" and pads["2"] == "Drums/Snare 01.wav"
    assert "Other/Kick 01.wav" not in pads.values() and "Old/corrupt.wav" not in pads.values()
    _, body = post_json(srv, "/api/autofill", {"folder": "Drums", "one_shots": False})
    assert body["pads"] and all(p.startswith("Drums/") for p in body["pads"].values())


def test_autofill_one_shot_filter(cfg, library):
    import numpy as np
    sr = 44100
    sf.write(library / "Drums/Long hit.wav", (0.3 * np.sin(np.arange(sr * 5) / 10)).astype(np.float32), sr)
    scan_library(cfg)
    server = make_server(cfg, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        _, on = post_json(base, "/api/autofill", {"folder": "Drums", "one_shots": True})
        _, off = post_json(base, "/api/autofill", {"folder": "Drums", "one_shots": False})
    finally:
        server.shutdown()
        server.server_close()
    assert "Drums/Long hit.wav" not in on["pads"].values()
    assert "Drums/Long hit.wav" in off["pads"].values()


def test_layout_and_hints(srv):
    layout = get_json(srv, "/api/layout")
    assert layout["colors"]["kick"] == "#ff0000" and layout["default"] == "#3cff5a"
    assert layout["max_one_shot"] == 4.0
    status, hints = post_json(srv, "/api/hints", {"paths": ["Drums/Kick 01.wav", "nope.wav"]})
    assert status == 200 and hints == {"Drums/Kick 01.wav": "kick"}


def test_autofill_bad_request(srv):
    assert post_json(srv, "/api/autofill", {"folder": 3})[0] == 400
    assert post_json(srv, "/api/hints", {"paths": "x"})[0] == 400


def test_autofill_suggests_unique_name(srv):
    long = "A" * 60
    put_json(srv, "/api/drafts/", {"type": "drum", "name": "Drums", "pads": {}})
    _, body = post_json(srv, "/api/autofill", {"folder": "Drums", "one_shots": False})
    assert body["name"] == "Drums 2"
    _, body = post_json(srv, "/api/autofill", {"folder": "", "one_shots": False})
    assert body["name"] == "Library"
    # a long base must leave room for the suffix, so the suggestion is always free after safe_name
    put_json(srv, "/api/drafts/", {"type": "drum", "name": long[:40], "pads": {}})
    from forcekit.server import _suggest_name
    assert len(_suggest_name(long, {long[:40]})) <= 48 and _suggest_name(long, {long[:40]}).endswith(" 2")


@pytest.fixture
def force_srv(force_cfg):
    scan_library(force_cfg)
    server = make_server(force_cfg, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_settings_round_trip_and_validation(force_srv, force_cfg):
    s = get_json(force_srv, "/api/settings")
    assert s == {"force_host": "192.168.0.27", "force_user": "root", "force_dir": force_cfg.force_dir}
    new = {"force_host": "10.0.0.9", "force_user": "root", "force_dir": "/media/X/forcekit"}
    assert put_json(force_srv, "/api/settings", new) == new
    assert json.loads(force_cfg.config_path.read_text())["force_host"] == "10.0.0.9"
    for bad in [dict(new, force_host=""), dict(new, force_host="a b"), dict(new, force_dir="rel/dir"),
                dict(new, force_user="")]:
        assert _request(force_srv, "/api/settings", "PUT", bad).status == 400
    assert get_json(force_srv, "/api/settings") == new


def test_send_to_force(force_srv, force_cfg):
    from pathlib import Path
    d = {"type": "drum", "name": "Sent Kit", "pads": {"0": "Drums/Kick 01.wav"}}
    req = {"draft": d, "normalize": True, "overwrite": False}
    status, body = post_json(force_srv, "/api/send", req)
    assert status == 200, body
    assert (Path(force_cfg.force_dir) / "Drums/Sent Kit/Sent Kit.xpm").is_file()
    assert (force_cfg.export_dir / "Drums/Sent Kit/Sent Kit.xpm").is_file()  # local export too
    status, body = post_json(force_srv, "/api/send", req)
    assert status == 409 and body["exists"]
    assert post_json(force_srv, "/api/send", dict(req, overwrite=True))[0] == 200
    assert post_json(force_srv, "/api/settings/test", {})[0] == 200


def test_send_reports_unreachable_force(force_srv, force_cfg):
    force_cfg.ssh_command = ["false"]
    d = {"type": "drum", "name": "X", "pads": {"0": "Drums/Kick 01.wav"}}
    status, body = post_json(force_srv, "/api/send", {"draft": d, "normalize": True, "overwrite": False})
    assert status == 502 and body["error"]
    status, body = post_json(force_srv, "/api/settings/test", {})
    assert status == 502 and body["error"]


def test_cross_site_requests_refused(srv):
    d = json.dumps({"folder": "", "one_shots": False}).encode()
    def post(headers):
        req = urllib.request.Request(srv + "/api/autofill", data=d, method="POST", headers=headers)
        try:
            return urllib.request.urlopen(req).status
        except urllib.error.HTTPError as e:
            return e.code
    assert post({"Content-Type": "text/plain"}) == 415
    assert post({"Content-Type": "application/json", "Origin": "https://evil.example"}) == 403
    assert post({"Content-Type": "application/json", "Host": "evil.example:80"}) == 403
    assert post({"Content-Type": "application/json", "Origin": srv}) == 200
