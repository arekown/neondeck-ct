"""Profile und Arbeitsbereiche verwalten, ohne Qt (fuer den Dialog ``ProfileManager``).

Das aktive Profil wird direkt am Objekt der Engine geaendert und ueber ``commit``
(Einstellungsfenster: speichern + am Geraet zeigen) uebernommen; andere Profile werden aus dem
Speicher geladen, geaendert und ueber ``commit`` gespeichert. Ein Profilwechsel geht immer ueber
``switch_profile`` (den Dienst), damit Einstellungen und Meldungen stimmen. Fehler beim Laden
kommen als ``PROFILE_LOAD_ERRORS``, beim Loeschen als Text.
"""
from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from ...api.protocol import switch_error_text
from ...core.i18n import tr
from ...profile.ids import new_profile_id, new_workspace_id
from ...profile.importers.lp5 import import_lp5
from ...profile.model import Profile, TouchPage, Workspace, empty_profile
from ...profile.store import DEFAULT_ID, PROFILE_LOAD_ERRORS

if TYPE_CHECKING:
    from ...api.contracts import EditorBackend, ProfileRepository

log = logging.getLogger(__name__)


class ProfileOps:
    def __init__(self, store: ProfileRepository, engine: EditorBackend,
                 commit: Callable[[Profile], None],
                 switch_profile: Callable[[str], None]) -> None:
        self.store = store
        self.engine = engine
        self._commit = commit
        self._switch = switch_profile

    @property
    def active_id(self) -> str:
        return self.engine.profile.id

    def ids(self) -> list[str]:
        """Profile im Speicher, dazu das aktive (auch wenn es dort noch fehlt)."""
        ids = self.store.list()
        if self.active_id not in ids:
            ids.append(self.active_id)
        return ids

    def profile(self, pid: str) -> Profile:
        """Das aktive Profil ist das Objekt der Engine, alle anderen frisch aus dem Speicher
        (``PROFILE_LOAD_ERRORS``, wenn nicht lesbar)."""
        if pid == self.active_id:
            return self.engine.profile
        return self.store.load(pid)

    def name(self, pid: str) -> tuple[str, bool]:
        """Anzeigename und ob das Profil lesbar ist."""
        try:
            return self.profile(pid).name or pid, True
        except PROFILE_LOAD_ERRORS:
            return pid, False

    def save(self, profile: Profile) -> None:
        self._commit(profile)

    # --- Profile --------------------------------------------------------------------------

    def new_profile(self, name: str) -> Profile:
        profile = empty_profile(new_profile_id(name, set(self.store.list())), name)
        self.save(profile)
        return profile

    def rename_profile(self, profile: Profile, name: str) -> None:
        profile.name = name
        self.save(profile)

    def duplicate_profile(self, profile: Profile, name: str) -> Profile:
        dup = copy.deepcopy(profile)
        dup.id, dup.name = new_profile_id(name, set(self.store.list())), name
        self.save(dup)
        return dup

    def can_delete(self, pid: str | None) -> bool:
        """Das letzte Profil bleibt."""
        return pid is not None and len(set(self.store.list()) | {self.active_id}) > 1

    def delete_profile(self, pid: str, name: str) -> str | None:
        """Profil loeschen (das aktive: erst auf ein anderes wechseln, nie das aktive
        loeschen); Fehlertext oder ``None``."""
        if pid == self.active_id:
            others = [i for i in self.store.list() if i != pid]
            try:
                self._switch(DEFAULT_ID if DEFAULT_ID in others else others[0])
            except Exception as e:  # noqa: BLE001 - nie bis in die Qt-Ereignisschleife
                log.warning("Profilwechsel vor dem Löschen fehlgeschlagen: %s", e)
                return switch_error_text(e)
            if self.active_id == pid:
                return tr("Wechsel auf ein anderes Profil fehlgeschlagen – „{name}“ wurde nicht "
                          "gelöscht.", name=name)
        try:
            self.store.delete(pid)  # im Dienst; der raeumt auch nicht mehr benutzte Importe auf
        except OSError as e:
            return tr("Löschen fehlgeschlagen: {error}", error=e)
        return None

    def import_lp5(self, path: Path) -> tuple[Profile, list[str]]:
        """Windows-Profil als neues Profil; nicht Uebernommenes als Meldungen
        (``ValueError``/``OSError`` bei kaputter Datei)."""
        return import_lp5(path, self.store)

    # --- Arbeitsbereiche --------------------------------------------------------------------

    def new_workspace(self, profile: Profile, name: str) -> Workspace:
        ws = Workspace(new_workspace_id(profile), name, [TouchPage("p1", tr("Seite {n}", n=1))])
        profile.workspaces.append(ws)
        self.save(profile)
        return ws

    def rename_workspace(self, profile: Profile, ws: Workspace, name: str) -> None:
        ws.name = name
        self.save(profile)

    def delete_workspace(self, profile: Profile, ws: Workspace) -> None:
        """Arbeitsbereich entfernen (war er der Heim-Arbeitsbereich: Heim wird der erste)."""
        profile.workspaces.remove(ws)
        if profile.home_workspace == ws.id:
            profile.home_workspace = profile.workspaces[0].id
        self.save(profile)

    def move_workspace(self, profile: Profile, ws: Workspace, delta: int) -> bool:
        i = profile.workspaces.index(ws)
        j = i + delta
        if not 0 <= j < len(profile.workspaces):
            return False
        profile.workspaces[i], profile.workspaces[j] = profile.workspaces[j], ws
        self.save(profile)
        return True

    def set_home(self, profile: Profile, ws: Workspace) -> None:
        profile.home_workspace = ws.id
        self.save(profile)
