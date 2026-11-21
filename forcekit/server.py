"""Local HTTP server: JSON API + the static web page. Binds to 127.0.0.1 only."""
from __future__ import annotations

import json
import mimetypes
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .audio import AudioError, browser_playable, detect_root, load, write_wav
from .config import Config, save_force_settings
from .drafts import DraftError, delete_draft, list_drafts, load_draft, save_draft, validate_draft
from .export import ExportExists, export_program
from .send import ForceError, SendExists, send_program, test_connection
from .layout import DEFAULT_COLOR, MAX_ONE_SHOT, TYPE_COLORS, autofill, color_for, is_one_shot
from .names import natural_key, safe_name, unique_name

WEB_DIR = Path(__file__).parent / "web"
DEFAULT_ROOT = 60


class Library:
    """The index, plus lookups the API needs."""

    def __init__(self, cfg: Config):
        if not cfg.index_path.is_file():
            raise SystemExit(f"No index at {cfg.index_path}. Run `forcekit scan` first.")
        index = json.loads(cfg.index_path.read_text())
        self.root = cfg.library.resolve()
        self.files = {f["path"]: f for f in index["files"]}
        self.by_folder: dict[str, list[dict]] = {}
        for f in index["files"]:
            self.by_folder.setdefault(f["folder"], []).append(f)
        for entries in self.by_folder.values():
            entries.sort(key=lambda f: natural_key(f["path"].rsplit("/", 1)[-1]))
        self.tree = self._build_tree()

    def _build_tree(self) -> dict:
        root = {"name": self.root.name, "path": "", "count": len(self.by_folder.get("", [])), "children": []}
        nodes = {"": root}
        for folder in sorted(self.by_folder, key=natural_key):
            if not folder:
                continue
            parts = folder.split("/")
            for i in range(1, len(parts) + 1):
                path = "/".join(parts[:i])
                if path not in nodes:
                    node = {"name": parts[i - 1], "path": path, "count": len(self.by_folder.get(path, [])),
                            "children": []}
                    nodes[path] = node
                    nodes["/".join(parts[: i - 1])]["children"].append(node)
        return root


def _suggest_name(base: str, taken: set[str]) -> str:
    """A draft name not in `taken`; long bases are cut so a " 2" suffix survives safe_name's 48 chars."""
    base = safe_name(base)[:40].rstrip() or "Kit"
    return unique_name(base, set(taken))


class ApiError(Exception):
    def __init__(self, status: int, message: str, **extra):
        super().__init__(message)
        self.status, self.body = status, {"error": message, **extra}


def make_server(cfg: Config, port: int = 0) -> ThreadingHTTPServer:
    library = Library(cfg)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the terminal quiet
            pass

        # ---- plumbing -------------------------------------------------
        def _send(self, status: int, body: bytes = b"", content_type: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if body and self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, obj, status: int = 200) -> None:
            self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(length) or b"null")
            except ValueError:
                raise ApiError(400, "invalid JSON")

        def _entry(self, query: dict) -> dict:
            rel = (query.get("path") or [""])[0]
            if not (library.root / rel).resolve().is_relative_to(library.root):
                raise ApiError(403, "outside the library")
            entry = library.files.get(rel)
            if not entry:
                raise ApiError(404, "not in the index")
            return entry

        def _dispatch(self, method: str) -> None:
            url = urlsplit(self.path)
            path, query = unquote(url.path), parse_qs(url.query)
            try:
                route = self._route(method, path)
                if route is None:
                    raise ApiError(404, "not found")
                route(path, query)
            except ApiError as e:
                self._json(e.body, e.status)
            except (DraftError, ValueError) as e:
                self._json({"error": str(e)}, 400)
            except Exception as e:  # disk full, permissions… — always answer with JSON
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)

        def do_GET(self):
            self._dispatch("GET")

        def do_PUT(self):
            self._dispatch("PUT")

        def do_POST(self):
            self._dispatch("POST")

        def do_DELETE(self):
            self._dispatch("DELETE")

        def _route(self, method: str, path: str):
            if method == "GET":
                if path == "/" or path.startswith("/static/"):
                    return self.static
                return {"/api/tree": self.tree, "/api/folder": self.folder, "/api/audio": self.audio,
                        "/api/root": self.root_note, "/api/drafts": self.drafts,
                        "/api/layout": self.layout, "/api/settings": self.settings_get}.get(path) or (
                    self.draft_get if path.startswith("/api/drafts/") else None)
            if path.startswith("/api/drafts/"):
                return {"PUT": self.draft_put, "DELETE": self.draft_delete}.get(method)
            if method == "PUT" and path == "/api/settings":
                return self.settings_put
            if method == "POST":
                return {"/api/export": self.export, "/api/autofill": self.autofill, "/api/hints": self.hints,
                        "/api/send": self.send, "/api/settings/test": self.settings_test}.get(path)
            return None

        # ---- routes ---------------------------------------------------
        def static(self, path, query):
            name = "index.html" if path == "/" else path[len("/static/"):]
            target = (WEB_DIR / name).resolve()
            if not target.is_relative_to(WEB_DIR.resolve()):
                raise ApiError(403, "forbidden")
            if not target.is_file():
                raise ApiError(404, "not found")
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self._send(200, target.read_bytes(), ctype)

        def tree(self, path, query):
            self._json(library.tree)

        def folder(self, path, query):
            self._json(library.by_folder.get((query.get("path") or [""])[0], []))

        def audio(self, path, query):
            entry = self._entry(query)
            source = library.root / entry["path"]
            if entry["error"] is None and browser_playable(entry["format"], entry["subtype"]):
                ctype = "audio/mpeg" if entry["format"] == "mp3" else "audio/wav"
                self._send(200, source.read_bytes(), ctype)
                return
            cached = cfg.cache_dir / f"{entry['hash']}.wav"
            if not cached.is_file():
                try:
                    data, sr, _ = load(source)
                except AudioError as e:
                    raise ApiError(422, str(e))
                cfg.cache_dir.mkdir(parents=True, exist_ok=True)
                tmp = cached.with_suffix(".tmp")
                write_wav(tmp, data, sr, "PCM_16")
                tmp.replace(cached)
            self._send(200, cached.read_bytes(), "audio/wav")

        def root_note(self, path, query):
            entry = self._entry(query)
            if entry["note"] is not None:
                self._json({"root": entry["note"], "source": "filename"})
                return
            try:
                detected = detect_root(library.root / entry["path"])
            except AudioError:
                detected = None
            if detected is None:
                self._json({"root": DEFAULT_ROOT, "source": "default"})
            else:
                self._json({"root": detected, "source": "detected"})

        def drafts(self, path, query):
            self._json(list_drafts(cfg))

        def draft_get(self, path, query):
            self._json(load_draft(cfg, path[len("/api/drafts/"):]))

        def draft_put(self, path, query):
            raw_old = path[len("/api/drafts/"):]  # empty for a program never saved before
            old = safe_name(raw_old) if raw_old else None
            draft = self._body()
            validate_draft(draft)
            target = safe_name(draft["name"])
            if target != old and (cfg.drafts_dir / f"{target}.json").exists():
                raise ApiError(409, f"a draft named {target} already exists", exists=True, stem=target)
            stem = save_draft(cfg, draft)
            if old and old != stem:  # renamed: drop the old file
                delete_draft(cfg, old)
            self._json({"stem": stem})

        def draft_delete(self, path, query):
            delete_draft(cfg, path[len("/api/drafts/"):])
            self._send(204)

        def layout(self, path, query):
            self._json({"colors": {t: f"#{c:06x}" for t, c in TYPE_COLORS.items()},
                        "default": f"#{DEFAULT_COLOR:06x}", "max_one_shot": MAX_ONE_SHOT})

        def autofill(self, path, query):
            body = self._body()
            folder = body.get("folder") if isinstance(body, dict) else None
            if not isinstance(folder, str):
                raise ApiError(400, "folder must be a string")
            prefix = folder + "/"
            entries = [f for f in library.files.values()
                       if not folder or f["folder"] == folder or f["folder"].startswith(prefix)]
            if body.get("one_shots"):
                entries = [f for f in entries if is_one_shot(f)]
            name = _suggest_name(folder.rsplit("/", 1)[-1] if folder else "Library",
                                 {d["stem"] for d in list_drafts(cfg)})
            self._json({"pads": {str(k): p for k, p in autofill(entries).items()}, "name": name})

        def hints(self, path, query):
            body = self._body()
            paths = body.get("paths") if isinstance(body, dict) else None
            if not isinstance(paths, list):
                raise ApiError(400, "paths must be a list")
            self._json({p: library.files[p]["type_hint"] for p in paths
                        if isinstance(p, str) and p in library.files})

        def _export(self, body: dict, overwrite: bool) -> Path:
            draft = body.get("draft")
            colors = None
            if isinstance(draft, dict) and draft.get("type") == "drum" and isinstance(draft.get("pads"), dict):
                colors = {int(k): color_for(library.files.get(p, {}).get("type_hint"))
                          for k, p in draft["pads"].items() if str(k).isdigit() and isinstance(p, str)}
            try:
                return export_program(cfg, draft, normalize=bool(body.get("normalize", True)),
                                      overwrite=overwrite, colors=colors)
            except ExportExists as e:
                raise ApiError(409, "program already exists", exists=True, path=str(e.path))
            except AudioError as e:
                raise ApiError(422, str(e))

        def export(self, path, query):
            body = self._body()
            if not isinstance(body, dict):
                raise ApiError(400, "invalid request")
            self._json({"path": str(self._export(body, bool(body.get("overwrite", False))))})

        def send(self, path, query):
            body = self._body()
            if not isinstance(body, dict):
                raise ApiError(400, "invalid request")
            written = self._export(body, overwrite=True)  # local copy is just the staging area for the Force
            try:
                remote = send_program(cfg, written.parent, overwrite=bool(body.get("overwrite", False)))
            except SendExists as e:
                raise ApiError(409, "program already exists on the Force", exists=True, path=e.path)
            except ForceError as e:
                raise ApiError(502, str(e))
            self._json({"path": remote, "host": cfg.force_host})

        def _settings(self) -> dict:
            return {"force_host": cfg.force_host, "force_user": cfg.force_user, "force_dir": cfg.force_dir}

        def settings_get(self, path, query):
            self._json(self._settings())

        def settings_put(self, path, query):
            body = self._body()
            if not isinstance(body, dict):
                raise ApiError(400, "invalid request")
            host, user, folder = (body.get(k) for k in ("force_host", "force_user", "force_dir"))
            if not all(isinstance(v, str) and v.strip() for v in (host, user, folder)):
                raise ApiError(400, "IP address, user and folder are all required")
            host, user, folder = host.strip(), user.strip(), folder.strip()
            if not re.fullmatch(r"[A-Za-z0-9.:\-]+", host):
                raise ApiError(400, "the IP address may only contain letters, digits, dots, colons and dashes")
            if not re.fullmatch(r"[A-Za-z0-9._\-]+", user):
                raise ApiError(400, "invalid user name")
            if not folder.startswith("/"):
                raise ApiError(400, "the folder on the Force must be a full path starting with /")
            save_force_settings(cfg, host, user, folder.rstrip("/") or "/")
            self._json(self._settings())

        def settings_test(self, path, query):
            try:
                info = test_connection(cfg)
            except ForceError as e:
                raise ApiError(502, str(e))
            self._json({"ok": True, "info": info})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(cfg: Config) -> ThreadingHTTPServer:
    return make_server(cfg, cfg.port)
