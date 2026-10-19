"""Windows-Profil-Archive (.lp5) fuer Tests."""
from __future__ import annotations

import zipfile
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def make_lp5(path: Path, *, extra: dict | None = None) -> Path:
    """Archiv aus dem synthetischen Windows-Profil; ``extra``: weitere Eintraege (Name -> Inhalt)."""
    with zipfile.ZipFile(path, "w") as z:
        z.write(DATA / "synthetic-profile" / "ProfileInfo.json", "ProfileInfo.json")
        for f in sorted((DATA / "synthetic-profile" / "ActionIcons").iterdir()):
            z.write(f, f"ActionIcons/{f.name}")
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return path


def corrupt_lp5(path: Path) -> Path:
    """Gespeicherter (unkomprimierter) Eintrag mit kaputter Pruefsumme."""
    content = b'{"displayName": "Kaputt", "layout": {}}' + b" " * 64
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as z:
        z.writestr("ProfileInfo.json", content)
    raw = bytearray(path.read_bytes())
    i = raw.index(content)
    raw[i + 2] ^= 0x01
    path.write_bytes(bytes(raw))
    return path
