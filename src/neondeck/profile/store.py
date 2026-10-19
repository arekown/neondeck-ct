"""Profile als JSON-Dateien in einem Verzeichnis."""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

from ..core.fileio import read_json, write_atomic
from ..core.i18n import N_, tr
from .model import Profile, empty_profile
from .versions import ProfileVersions, VersionInfo

log = logging.getLogger(__name__)

DEFAULT_ID = "default"
DEFAULT_NAME = N_("Standard (CT)")  # beim Anlegen mit tr() übersetzen

# Was beim Laden eines Profils aus einer (fremden, kaputten) Datei auftreten kann: Datei nicht
# lesbar, kein JSON, Format falsch (``ProfileFormatError`` ist ein ``ValueError``)
PROFILE_LOAD_ERRORS = (OSError, ValueError)


class ProfileStore:
    """Erfuellt ``api.contracts.ProfileRepository``."""

    def __init__(self, dir: Path):
        self.dir = Path(dir)
        self._versions = ProfileVersions(self.dir)

    def path(self, id: str) -> Path:
        """Datei des Profils ``id`` (muss nicht existieren)."""
        return self.dir / f"{id}.json"

    def list(self) -> list[str]:
        if not self.dir.is_dir():
            return []
        return sorted(p.stem for p in self.dir.glob("*.json"))

    def load(self, id: str) -> Profile:
        return Profile.from_json(read_json(self.path(id)))

    def name(self, id: str) -> str:
        """Anzeigename aus der Datei; nicht lesbar: die Kennung."""
        try:
            return self.load(id).name or id
        except PROFILE_LOAD_ERRORS:
            return id

    @staticmethod
    def _dump(p: Profile) -> str:
        return json.dumps(p.to_json(), ensure_ascii=False, indent=2)

    def versions(self, id: str) -> list[VersionInfo]:
        """Snapshots des Profils, neueste zuerst."""
        return self._versions.list(id)

    def version_json(self, id: str, name: str):
        """Inhalt des Snapshots ``name`` als JSON (zum Pruefen vor ``restore``)."""
        return self._versions.read_json(id, name)

    def restore(self, id: str, name: str) -> Profile:
        """Stellt Snapshot ``name`` wieder her; der aktuelle Stand wird vorher gesichert."""
        text = self._versions.file(id, name).read_text(encoding="utf-8")
        profile = Profile.from_json(json.loads(text))
        self._versions.snapshot(id, self.path(id), text)
        write_atomic(self.path(id), text)
        return profile

    def save(self, p: Profile) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        text = self._dump(p)
        self._versions.snapshot(p.id, self.path(p.id), text)
        write_atomic(self.path(p.id), text)

    def delete(self, id: str) -> None:
        """Profildatei entfernen.

        Sicherungskopien ``*.kaputt-*`` und ``.versionen/<id>`` bleiben absichtlich
        erhalten (Weg zum Wiederherstellen).
        """
        self.path(id).unlink(missing_ok=True)

    def load_or_recover(self, id: str) -> tuple[Profile, str | None]:
        path = self.path(id)
        if not path.exists():
            return empty_profile(id), None
        try:
            return self.load(id), None
        except Exception as e:  # noqa: BLE001 - auch OverflowError/RecursionError: nie Startabbruch
            err = tr("Profil '{id}' ist kaputt: {e}", id=id, e=e)
            log.error("Profil '%s' ist kaputt: %s", id, e)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            try:
                shutil.copy2(path, path.with_name(f"{path.name}.kaputt-{stamp}"))
            except OSError as ce:
                log.error("Sicherungskopie von %s fehlgeschlagen: %s", path, ce)
            return empty_profile(id), err
