"""One-off: strip sample references from Force-saved programs to make our templates.

usage: python tools/make_templates.py ~/Samples/xpm forcekit/templates
"""
import sys
from pathlib import Path

from forcekit.xpm import read_xpm, write_xpm

SOURCES = {"DrumTest.xpm": "drum.xpm", "Keygrouptes.xpm": "keygroup.xpm"}


def main(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for source, target in SOURCES.items():
        header, doc = read_xpm(src / source)
        data = doc["data"]
        for inst in data["drum"]["instruments"]:
            for layer in inst["layersv"]:
                layer["sampleName"] = ""
                layer["sampleFile"] = ""
        data["samples"] = []
        data["name"] = target.removesuffix(".xpm")
        write_xpm(dest / target, header, doc)
        print(f"{source} -> {dest / target}")


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser(), Path(sys.argv[2]))
