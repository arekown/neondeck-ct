"""Das aktive Profil und die Ansicht des Dienstes im Editor nachfuehren.

Antworten und Ereignisse (``view.changed``, ``profile.changed``) halten Profil, Arbeitsbereich
und Seite der ``RemoteEngine`` aktuell. Aendert jemand anderes das aktive Profil, waehrend der
Editor ungespeicherte Aenderungen hat (in der Warteschlange oder noch im Fenster gebuendelt),
gewinnt der Editor: sein Stand wird nicht ersetzt und geht danach an den Dienst. Eigene
Ansichtswechsel unterwegs haben Vorrang vor ``view.changed``.
"""
from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from typing import Protocol

from ...api.protocol import ERR_DISCONNECTED, error_code
from ...core.values import is_int
from ...profile.model import Profile
from .listing import ProfileListing
from .puts import ProfilePuts
from .queue import Op, RequestQueue
from .store import RemoteStore

log = logging.getLogger(__name__)


class ViewHost(Protocol):
    """Was der Editor zeigt (die ``RemoteEngine``)."""
    profile: Profile | None
    workspace_id: str | None
    page_index: int


class ActiveFollower:
    """``view_changed()`` meldet (ueber die Ereignisschleife), dass das Fenster nachziehen soll."""

    def __init__(self, host: ViewHost, queue: RequestQueue, puts: ProfilePuts,
                 store: RemoteStore, listing: ProfileListing,
                 view_changed: Callable[[], None]) -> None:
        self._host = host
        self._queue = queue
        self._puts = puts
        self._store = store
        self._listing = listing
        self._view_changed = view_changed
        self._view: dict | None = None
        self._view_ops = 0              # eigene Ansichtswechsel unterwegs
        self._fetching: set[str] = set()

    def reset(self) -> None:
        self._view_ops = 0
        self._fetching.clear()

    def _active_is(self, pid) -> bool:
        return self._host.profile is not None and self._host.profile.id == pid

    # --- Ansicht -------------------------------------------------------------------------

    def view_set(self, params: dict) -> None:
        """Eigener Ansichtswechsel am Geraet (``view.set``)."""
        def done(result, error):
            self._view_ops -= 1
            if error is not None:
                if error_code(error) != ERR_DISCONNECTED:
                    log.warning("Ansicht nicht gewechselt: %s", error)
                    self._queue.enqueue(Op("view.get", {}, self.view_reply))
            elif self._view_ops == 0:
                self.apply_view(result)

        self._view_ops += 1
        self._queue.enqueue(Op("view.set", params, done))

    def view_reply(self, result, error) -> None:
        if error is None:
            self.apply_view(result)

    def resync_view(self, result, error) -> None:
        """Antwort auf ``view.get`` nach dem (Wieder-)Verbinden; danach die Profilliste."""
        if error is None and isinstance(result, dict):
            self.apply_view(result)
            pid = result.get("profile")
            if self._active_is(pid):
                self.fetch_active(pid)  # waehrend der Trennung anderswo geaendert?
        if error_code(error) != ERR_DISCONNECTED:
            self._listing.refresh()

    def apply_view(self, view, from_event: bool = False) -> None:
        if not isinstance(view, dict) or not isinstance(view.get("profile"), str):
            return
        pid = view["profile"]
        same = self._active_is(pid)
        if from_event and same and self._view_ops:
            return  # eigener Ansichtswechsel unterwegs: dessen Antwort zaehlt
        self._view = view
        if same:
            self.take_view(view)
        else:
            self.fetch_active(pid)

    def take_view(self, view: dict, force: bool = False) -> None:
        host = self._host
        ws, page = view.get("workspace"), view.get("page")
        if not is_int(page):
            page = 0
        changed = force or (ws, page) != (host.workspace_id, host.page_index)
        host.workspace_id, host.page_index = ws, page
        if changed:
            self._view_changed()

    # --- Aktives Profil ------------------------------------------------------------------

    def adopt(self, pid: str, data: dict, view: dict) -> None:
        """Profil ``pid`` (Stand ``data``) ist jetzt aktiv, der Dienst zeigt ``view``."""
        self._store.remember(pid, data)
        self._view = view
        self._puts.base = data
        self._host.profile = Profile.from_json(copy.deepcopy(data))
        self.take_view(view, force=True)

    def fetch_active(self, pid: str) -> None:
        if pid not in self._fetching:
            self._fetching.add(pid)
            self._queue.enqueue(Op("profile.get", {"id": pid},
                                   lambda r, e: self.got_active(pid, r, e)))

    def got_active(self, pid: str, result, error) -> None:
        self._fetching.discard(pid)
        if error is not None or not isinstance(result, dict):
            if error is not None and error_code(error) != ERR_DISCONNECTED:
                log.warning("Profil %s nicht geholt: %s", pid, error)
            return
        self._store.remember(pid, result)
        view = self._view
        if view is None or view.get("profile") != pid:
            return  # inzwischen ein anderes Profil
        host = self._host
        if self._active_is(pid):
            dirty = self._puts.dirty(host.profile)
            self._puts.base = result
            if not dirty and host.profile.to_json() != result:  # anderswo geaendert
                host.profile = Profile.from_json(copy.deepcopy(result))
                self.take_view(view, force=True)
            else:  # gleich, oder der Editor hat Ungespeichertes: sein Stand gewinnt
                self.take_view(view)
            return
        local = self._puts.pending_json(pid)
        self._puts.base = result
        host.profile = Profile.from_json(copy.deepcopy(local if local is not None else result))
        self.take_view(view, force=True)

    def foreign_change(self, pid: str) -> None:
        """Jemand anderes hat ``pid`` geaendert, waehrend eigene Auftraege liefen."""
        self._store.forget(pid)
        if self._active_is(pid):
            self.fetch_active(pid)

    def profile_changed(self, data: dict) -> None:
        pid, active = data.get("id"), data.get("active")
        if isinstance(pid, str) and not self._puts.note_change(pid):
            self._store.forget(pid)
            if self._active_is(pid) and pid == active:
                self.fetch_active(pid)
        profile = self._host.profile
        if profile is not None and isinstance(active, str) and active != profile.id:
            self._queue.enqueue(Op("view.get", {}, self.view_reply))
        self._listing.refresh()
