"""Sicherungskopien (Versionen) eines Profils: ``<profile-dir>/.versionen/<id>/<stamp>.json``."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..core.fileio import read_json, write_atomic

log = logging.getLogger(__name__)

VERSIONS_DIR = ".versionen"
MAX_VERSIONS = 100
MAX_AGE_DAYS = 60
KEEP_NEWEST = 10


@dataclass(frozen=True)
class VersionInfo:
    name: str  # Dateiname YYYYmmdd-HHMMSS-ffffff.json
    time: float  # Zeitstempel (Epoche) aus dem Namen
    size: int


def _parse_stamp(name: str) -> float:
    try:
        return datetime.strptime(name.removesuffix(".json"), "%Y%m%d-%H%M%S-%f").timestamp()
    except ValueError:
        return 0.0


class ProfileVersions:
    """Snapshots der Profile eines Ordners (anlegen, aufraeumen, auflisten, lesen)."""

    def __init__(self, profile_dir: Path):
        self.root = Path(profile_dir) / VERSIONS_DIR

    def _dir(self, id: str) -> Path:
        return self.root / id

    def snapshot(self, id: str, path: Path, new_text: str | None) -> None:
        """Kopiert die bisherige Datei ``path`` in die Versionen (nur wenn sie von ``new_text``
        abweicht).

        Best effort: ein Fehler hier darf das eigentliche Speichern nie verhindern.
        """
        try:
            old = path.read_bytes()
        except OSError:
            return
        if new_text is not None and old == new_text.encode("utf-8"):
            return
        try:
            d = self._dir(id)
            d.mkdir(parents=True, exist_ok=True)
            name = datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json"
            write_atomic(d / name, old)
            self._prune(id)
        except Exception as e:  # noqa: BLE001 - Snapshot ist optional
            log.warning("Snapshot von Profil '%s' fehlgeschlagen: %s", id, e)

    def _prune(self, id: str) -> None:
        cutoff = time.time() - MAX_AGE_DAYS * 86400
        for rank, v in enumerate(self.list(id)):
            if rank >= KEEP_NEWEST and (rank >= MAX_VERSIONS or v.time < cutoff):
                (self._dir(id) / v.name).unlink(missing_ok=True)

    def list(self, id: str) -> list[VersionInfo]:
        """Snapshots des Profils, neueste zuerst."""
        d = self._dir(id)
        if not d.is_dir():
            return []
        out = [VersionInfo(p.name, _parse_stamp(p.name), p.stat().st_size)
               for p in d.glob("*.json")]
        return sorted(out, key=lambda v: v.name, reverse=True)

    def file(self, id: str, name: str) -> Path:
        return self._dir(id) / Path(name).name

    def read_json(self, id: str, name: str):
        """Inhalt des Snapshots ``name`` als JSON (zum Pruefen vor dem Wiederherstellen)."""
        return read_json(self.file(id, name))
