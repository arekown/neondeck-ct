"""Kopiert die Original-Loupedeck-Grafiken in das Datenverzeichnis der App.

/usr/bin/python3 tools/import_assets.py --source <Pfad zum entpackten Windows-Installer>
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from neondeck.core import assets


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True, help="Pfad zum entpackten Windows-Installer (siehe README)")
    args = ap.parse_args()
    src = Path(args.source).expanduser()
    if not src.is_dir():
        print(f"Quelle nicht gefunden: {src}", file=sys.stderr)
        return 1
    manifest = assets.import_assets(src)
    print(f"Ziel: {assets.assets_dir()}")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
