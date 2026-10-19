#!/usr/bin/env python3
"""Laedt die Theme-Schriften (SIL OFL) aus github.com/google/fonts nach data/fonts/.

Einmalig von Hand ausfuehren; die Dateien werden mit ins Repo eingecheckt, die App
selbst greift nie aufs Netz zu.

    python3 tools/fetch_fonts.py [--force]
"""
from __future__ import annotations

import argparse
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://github.com/google/fonts/raw/main/ofl"
DEST = Path(__file__).resolve().parents[1] / "data" / "fonts"

# Ordner im google/fonts-Repo -> [(Datei dort, Datei bei uns)]
FONTS: dict[str, list[tuple[str, str]]] = {
    "orbitron": [("Orbitron[wght].ttf", "Orbitron-VariableFont_wght.ttf")],
    "rajdhani": [("Rajdhani-Medium.ttf", "Rajdhani-Medium.ttf"),
                 ("Rajdhani-SemiBold.ttf", "Rajdhani-SemiBold.ttf"),
                 ("Rajdhani-Bold.ttf", "Rajdhani-Bold.ttf")],
    "sharetechmono": [("ShareTechMono-Regular.ttf", "ShareTechMono-Regular.ttf")],
    "inter": [("Inter[opsz,wght].ttf", "Inter-VariableFont_opsz,wght.ttf")],
}
LICENSE = "OFL.txt"
TIMEOUT_S = 30


def _download(url: str, target: Path) -> None:
    with urllib.request.urlopen(url, timeout=TIMEOUT_S) as r:
        data = r.read()
    if target.suffix == ".ttf" and data[:4] not in (b"\x00\x01\x00\x00", b"true", b"OTTO"):
        raise ValueError(f"{url}: keine TrueType-Datei")
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(target)


def fetch(dest: Path = DEST, force: bool = False) -> list[Path]:
    written: list[Path] = []
    for family, files in FONTS.items():
        folder = dest / family
        folder.mkdir(parents=True, exist_ok=True)
        for remote, local in [*files, (LICENSE, LICENSE)]:
            target = folder / local
            if target.is_file() and not force:
                continue
            url = f"{BASE}/{family}/{urllib.parse.quote(remote)}"
            print(f"lade {url}")
            _download(url, target)
            written.append(target)
    return written


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--force", action="store_true", help="vorhandene Dateien neu laden")
    args = p.parse_args(argv)
    written = fetch(force=args.force)
    print(f"{len(written)} Datei(en) geschrieben nach {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
