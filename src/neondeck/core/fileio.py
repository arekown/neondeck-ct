"""Dateien lesen und schreiben: atomar ersetzen, JSON laden, Temp-Dateien im Laufzeitordner."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from . import paths


def write_atomic(path: Path, data: str | bytes, *, fsync: bool = True) -> None:
    """``path`` ueber eine ``.tmp``-Datei daneben ersetzen (Text als UTF-8).

    Mit ``fsync`` liegen die Daten auf der Platte, bevor der Name umzieht; bei jedem Fehler
    wird die ``.tmp``-Datei entfernt und der Fehler weitergereicht."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    raw = data.encode("utf-8") if isinstance(data, str) else data
    try:
        with tmp.open("wb") as f:
            f.write(raw)
            if fsync:
                f.flush()
                os.fsync(f.fileno())
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)  # nie eine halbe Datei liegen lassen
        raise


def read_json(path: Path):
    """JSON-Datei lesen (UTF-8, ein BOM am Anfang ist erlaubt); ``OSError``/``ValueError``."""
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def runtime_tempfile(prefix: str, suffix: str, text: str) -> Path:
    """Neue Datei mit ``text`` im Laufzeitordner (sonst im Temp-Ordner) anlegen.

    Nur fuer den Benutzer lesbar (``mkstemp``); der Aufrufer loescht sie wieder."""
    runtime = paths.runtime_dir()
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=suffix,
                                dir=str(runtime) if runtime else None)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    return Path(name)
