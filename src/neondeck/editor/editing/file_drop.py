"""Dateien aus dem Dateimanager auf eine Taste ziehen: ``.desktop``-Verknuepfungen,
Programme, Ordner, Dokumente werden zu einer Aktion „Öffnen“ mit Name und Symbol."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ...core.desktop_apps import describe_file
from ...profile.model import Assignment, ButtonImage

ICON_SUFFIXES = (".png", ".svg", ".jpg", ".jpeg", ".webp")


def assignment_for(path: Path) -> Assignment:
    """Taste zu einer abgelegten Datei: Text = Name (bei ``.desktop`` aus der Datei),
    Symbol = ``Icon`` der Verknuepfung, wenn es ein vorhandener Bildpfad ist."""
    text, icon = path.stem if path.is_file() else path.name, None
    if path.suffix == ".desktop":
        info = describe_file(path)
        if info is not None:
            text = info[0]
            icon_path = Path(info[1])
            if icon_path.is_absolute() and icon_path.is_file() \
                    and icon_path.suffix.lower() in ICON_SUFFIXES:
                icon = f"file:{icon_path}"
    image = ButtonImage(icon=icon, text=text, layout="icon_text" if icon else "text")
    return Assignment({"type": "open", "target": str(path)}, image)


def local_paths(urls: Iterable) -> list[Path]:
    """Lokale Pfade aus den URLs eines Ablegens (andere werden ignoriert)."""
    return [Path(u.toLocalFile()) for u in urls if u.isLocalFile() and u.toLocalFile()]
