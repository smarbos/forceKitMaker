"""Akai Force 3.10 program files (.xpm): gzip(header + JSON).

Every program we write is a modified copy of a template saved by Damian's Force,
so fields we don't understand keep the Force's own defaults.
"""
from __future__ import annotations

import copy
import gzip
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

TEMPLATES = Path(__file__).parent / "templates"
DRUM_PADS = 64


@dataclass(frozen=True)
class SampleRef:
    name: str  # shown on the Force
    file: str  # filename inside <Program>_[ProgramData]/
    start: int = 0  # first frame played (layer sliceInfo.Start)
    end: int = 0  # last frame played, inclusive (layer sliceInfo.End); the Force saves frames - 1


def read_xpm(path: Path) -> tuple[bytes, dict]:
    raw = gzip.decompress(Path(path).read_bytes())
    start = raw.index(b"{")
    return raw[:start], json.loads(raw[start:].decode("utf-8"))


def write_xpm(path: Path, header: bytes, doc: dict) -> None:
    body = json.dumps(doc, indent=4, ensure_ascii=False).encode("utf-8")
    Path(path).write_bytes(gzip.compress(header + body))


@lru_cache(maxsize=None)
def _template(name: str) -> tuple[bytes, dict]:
    return read_xpm(TEMPLATES / name)


def _sample_entry(ref: SampleRef, root: int = 60) -> dict:
    return {"version": 1, "name": ref.name, "path": ref.file, "loadImpl": 0,
            "metadata": {"tempo": 120.0, "rootNote": root, "tune": 0.0, "key": ""}}


def _set_layer(layer: dict, ref: SampleRef) -> None:
    layer["sampleName"] = ref.name
    layer["sampleFile"] = ref.file
    layer["active"] = True
    layer["sliceInfo"]["Start"] = ref.start
    layer["sliceInfo"]["End"] = ref.end


def build_drum(name: str, pads: dict[int, SampleRef]) -> tuple[bytes, dict]:
    header, doc = _template("drum.xpm")
    doc = copy.deepcopy(doc)
    data = doc["data"]
    data["name"] = name
    instruments = data["drum"]["instruments"]
    for pad in sorted(pads):
        if not 0 <= pad < DRUM_PADS:
            raise ValueError(f"pad {pad} out of range")
        _set_layer(instruments[pad]["layersv"][0], pads[pad])
        data["samples"].append(_sample_entry(pads[pad]))
    return header, doc


def build_keygroup(name: str, zones: list[tuple[SampleRef, int, int, int]]) -> tuple[bytes, dict]:
    header, doc = _template("keygroup.xpm")
    doc = copy.deepcopy(doc)
    data = doc["data"]
    data["name"] = name
    blank = data["drum"]["instruments"][0]
    instruments = []
    for ref, root, low, high in sorted(zones, key=lambda z: z[1]):
        inst = copy.deepcopy(blank)
        inst["lowNote"], inst["highNote"] = low, high
        layer = inst["layersv"][0]
        _set_layer(layer, ref)
        layer["rootNote"] = root
        layer["keyTrackEnable"] = True
        instruments.append(inst)
        data["samples"].append(_sample_entry(ref, root))
    data["drum"]["instruments"] = instruments
    data["keygroup"]["numKeygroups"] = len(instruments)
    return header, doc
