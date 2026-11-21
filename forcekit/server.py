"""Local HTTP server: JSON API + the static web page. Binds to 127.0.0.1 only."""
from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .audio import AudioError, browser_playable, detect_root, load, write_wav
from .config import Config
from .drafts import DraftError, delete_draft, list_drafts, load_draft, save_draft, validate_draft
from .export import ExportExists, export_program
from .names import natural_key, safe_name

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
                        "/api/root": self.root_note, "/api/drafts": self.drafts}.get(path) or (
                    self.draft_get if path.startswith("/api/drafts/") else None)
            if path.startswith("/api/drafts/"):
                return {"PUT": self.draft_put, "DELETE": self.draft_delete}.get(method)
            if method == "POST" and path == "/api/export":
                return self.export
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

        def export(self, path, query):
            body = self._body()
            if not isinstance(body, dict):
                raise ApiError(400, "invalid request")
            try:
                written = export_program(cfg, body.get("draft"), normalize=bool(body.get("normalize", True)),
                                         overwrite=bool(body.get("overwrite", False)))
            except ExportExists as e:
                raise ApiError(409, "program already exists", exists=True, path=str(e.path))
            except AudioError as e:
                raise ApiError(422, str(e))
            self._json({"path": str(written)})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(cfg: Config) -> ThreadingHTTPServer:
    return make_server(cfg, cfg.port)
