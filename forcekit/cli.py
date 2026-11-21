"""forcekit command line: `forcekit scan` and `forcekit serve`."""
from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path

from .config import load_config
from .scan import scan_library


def _progress(done: int, total: int) -> None:
    print(f"\r{done}/{total}", end="", flush=True)


def cmd_scan(args) -> int:
    cfg = load_config(args.config)
    if args.library:
        cfg.library = Path(args.library).expanduser()
    if not cfg.library.is_dir():
        print(f"library not found: {cfg.library}", file=sys.stderr)
        return 1
    print(f"Scanning {cfg.library}")
    start = time.monotonic()
    index = scan_library(cfg, progress=_progress)
    files = index["files"]
    print(f"\nfiles: {len(files)}  errors: {sum(1 for f in files if f['error'])}  "
          f"duplicates: {sum(1 for f in files if f['dup_of'])}  time: {time.monotonic() - start:.1f}s")
    print(f"index: {cfg.index_path}")
    return 0


def cmd_serve(args) -> int:
    from .server import make_server

    cfg = load_config(args.config)
    if not cfg.index_path.is_file():
        print(f"No index at {cfg.index_path}. Run `forcekit scan` first.", file=sys.stderr)
        return 1
    cfg.library = Path(json.loads(cfg.index_path.read_text())["root"])  # serve what was scanned
    port = args.port if args.port is not None else cfg.port
    server = make_server(cfg, port)
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"forcekit: {url}  (library {cfg.library}, exports to {cfg.export_dir})  Ctrl+C to stop")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forcekit", description="Build Akai Force programs from your samples.")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="index the sample library")
    scan.add_argument("--library", help="library folder (default from config)")
    scan.add_argument("--config", type=Path, help="config file")
    scan.set_defaults(func=cmd_scan)
    serve = sub.add_parser("serve", help="open the web UI")
    serve.add_argument("--port", type=int)
    serve.add_argument("--no-browser", action="store_true")
    serve.add_argument("--config", type=Path, help="config file")
    serve.set_defaults(func=cmd_serve)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
