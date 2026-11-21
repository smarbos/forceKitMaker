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
