"""Configuration: where the library, data and exports live."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".config/forcekit/config.json"


@dataclass
class Config:
    library: Path
    data_dir: Path
    export_dir: Path
    port: int = 8765

    @property
    def index_path(self) -> Path:
        return self.data_dir / "index.json"

    @property
    def drafts_dir(self) -> Path:
        return self.data_dir / "drafts"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"


def load_config(path: Path | None = None) -> Config:
    home = Path.home()
    values = {
        "library": home / "Samples/samples",
        "data_dir": home / "Samples/forcekit",
        "export_dir": home / "Samples/force-out",
        "port": 8765,
    }
    path = DEFAULT_CONFIG_PATH if path is None else Path(path)
    if path.is_file():
        for key, value in json.loads(path.read_text()).items():
            if key in values:
                values[key] = value
    return Config(
        library=Path(values["library"]).expanduser(),
        data_dir=Path(values["data_dir"]).expanduser(),
        export_dir=Path(values["export_dir"]).expanduser(),
        port=int(values["port"]),
    )
