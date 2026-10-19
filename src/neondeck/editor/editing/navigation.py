"""Was Fenster und Geraet zeigen: Profil wechseln (immer ueber den Dienst), Arbeitsbereich und
Seite waehlen, eine bearbeitete Stelle am Geraet zeigen. Die Ansicht steuert die Engine
(``EditorBackend.call``); das Fenster zieht danach nach."""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from ...api.protocol import switch_error_text
from ...core.i18n import tr
from ...profile.edit import EditContext, page_index
from ...profile.model import Profile, Workspace
from .commit import CommitScheduler

if TYPE_CHECKING:
    from .host import EditView

log = logging.getLogger(__name__)


class Navigator:
    def __init__(self, view: EditView, commits: CommitScheduler,
                 switch_profile: Callable[[str], None]) -> None:
        self._view = view
        self._commits = commits
        self._switch_profile = switch_profile  # App.switch_profile: laden, Engine, Einstellungen

    @property
    def _engine(self):
        return self._view.engine

    def choose_profile(self, pid: str | None) -> None:
        """Auswahl in der Profilliste (das gezeigte Profil: nichts zu tun)."""
        if pid and pid != self._view.profile.id:
            self.switch_to(pid)

    def switch_to(self, pid: str) -> None:
        """Profil wechseln (ueber den Dienst); Ausstehendes vorher speichern."""
        view = self._view
        self._commits.flush()
        error = None
        try:
            self._switch_profile(pid)
        except Exception as e:  # noqa: BLE001 - nie bis in die Qt-Ereignisschleife
            log.warning("Profilwechsel nach %s fehlgeschlagen: %s", pid, e)
            error = switch_error_text(e)
        if error is not None:
            view.say(error)
        elif view.profile.id != pid:
            view.say(tr("Profil „{name}“ konnte nicht geladen werden",
                         name=view.profile_name(pid)))
        view.reload_profiles()
        view.sync_from_engine(force=True)

    def choose_workspace(self, ws_id: str | None) -> None:
        if ws_id:
            self._engine.show_workspace(ws_id)
            self._view.sync_from_engine(force=True)

    def choose_page(self, index: int) -> None:
        if index >= 0:
            self._engine.show_page(index)
            self._view.sync_from_engine(force=True)

    def show(self, ctx: EditContext, ws: Workspace, index: int) -> None:
        """Seite ``index`` von ``ws`` am Geraet zeigen (wenn ``ctx`` das aktive Profil ist)."""
        if self._engine.profile is ctx.profile:
            if self._engine.workspace_id != ws.id:
                self._engine.show_workspace(ws.id)
            self._engine.show_page(index)
        self._view.sync_from_engine(force=True)

    def show_workspace(self, profile: Profile, ws_id: str) -> None:
        if self._engine.profile is profile:
            self._engine.show_workspace(ws_id)
        self._view.sync_from_engine(force=True)

    def keep_page(self, ws: Workspace | None, page_id: str | None) -> None:
        """Nach dem Umsortieren die vorher gezeigte Seite weiter zeigen (neue Nummer)."""
        if ws is None or page_id is None:
            return
        index = page_index(ws, page_id)
        if index >= 0 and index != self._engine.page_index:
            self._engine.show_page(index)
