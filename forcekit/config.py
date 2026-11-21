"""Configuration: where the library, data and exports live."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".config/forcekit/config.json"


@dataclass
class Config:
    library: Path
    data_dir: Path
    export_dir: Path
    port: int = 8765
    # Send to Force (SSH)
    force_host: str = "192.168.0.27"
    force_user: str = "root"
    force_dir: str = "/media/96B6-573E/forcekit"
    ssh_command: list[str] = field(default_factory=lambda: ["ssh"])  # internal; replaced in tests
    config_path: Path = DEFAULT_CONFIG_PATH

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
        "force_host": "192.168.0.27",
        "force_user": "root",
        "force_dir": "/media/96B6-573E/forcekit",
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
        force_host=str(values["force_host"]),
        force_user=str(values["force_user"]),
        force_dir=str(values["force_dir"]),
        config_path=path,
    )


def save_force_settings(cfg: Config, host: str, user: str, force_dir: str) -> None:
    """Update the Force settings in memory and in the config file, keeping its other keys."""
    path = Path(cfg.config_path)
    data = json.loads(path.read_text()) if path.is_file() else {}
    data.update(force_host=host, force_user=user, force_dir=force_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)
    cfg.force_host, cfg.force_user, cfg.force_dir = host, user, force_dir
