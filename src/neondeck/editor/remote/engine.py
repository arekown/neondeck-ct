"""Engine und Profilspeicher des Editor-Prozesses als Stellvertreter des Dienstes (JSON-API).

``RemoteEngine`` bietet dem Einstellungsfenster die Engine-Schnittstelle, die es benutzt
(``profile``, ``workspace``, ``workspace_id``, ``page_index``, ``set_profile``, ``call``,
``trigger``, ``simulate``, ``switch_profile``), ``RemoteStore`` die des Profilspeichers
(``list``, ``load``, ``save``, ``delete``). Gelesen wird aus einem Zwischenspeicher, den
Antworten und Ereignisse des Dienstes aktuell halten; jede Aenderung geht als Auftrag an den
Dienst (``profile.put`` …), der speichert (atomar, mit Snapshot) und am Geraet zeigt. Der
Editor schreibt selbst nie in den Profilordner.

Teile: ``queue`` (Auftraege der Reihe nach, Warten auf Antworten), ``puts`` (Speicher-Auftraege,
abgelehnte Profile, eigene gegen fremde Aenderungen), ``follow`` (aktives Profil und Ansicht
nachfuehren), ``listing`` (Profilliste). Bricht die Verbindung ab, bleiben ungesendete Profile
in der Warteschlange und gehen nach dem Wiederverbinden raus; Ansichtswechsel und Testen
verfallen dann.

Rueckrufe und Ereignisse kommen aus ``ApiClient._read``: dort wird nur der Zwischenspeicher
angepasst; die Qt-Signale nach aussen laufen ueber die Ereignisschleife (nie mitten im
Lesen), und kein Rueckruf wartet selbst auf eine Antwort.
"""
from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from ...api.client import NOT_CONNECTED, ApiClient, ApiError
from ...api.protocol import EDITOR_ROLE, ERR_DISCONNECTED, error_code, event_to_dict, format_ref
from ...core.i18n import N_, tr
from ...core.values import is_int
from ...device.layout import ControlRef
from ...device.protocol import Event
from ...profile.model import Profile, Workspace
from .follow import ActiveFollower
from .listing import ProfileListing
from .puts import ProfilePuts
from .queue import REQUEST_TIMEOUT_S, Callback, Op, RequestQueue, wait_for
from .store import RemoteStore

log = logging.getLogger(__name__)

RECONNECT_MS = 500
READY_TIMEOUT_S = 5.0   # Ansicht + aktives Profil nach dem Verbinden


class RemoteEngine(QObject):
    """Die Engine des Dienstes, wie das Einstellungsfenster sie braucht (ueber die API);
    erfuellt ``api.contracts.EditorBackend`` und ``api.contracts.ServiceLink``."""

    view_changed = Signal()
    device_state = Signal(dict)
    value = Signal(str, str)
    profiles_changed = Signal()
    online_changed = Signal(bool)
    failed = Signal(str)          # Meldung fuer die Statuszeile
    raise_requested = Signal()    # Dienst: Fenster nach vorn holen

    def __init__(self, client: ApiClient, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.client = client
        self.profile: Profile | None = None
        self.workspace_id: str | None = None
        self.page_index = 0
        self.other_editors = 0
        self.settings_snapshot: dict | None = None  # settings.get beim (Wieder-)Verbinden
        self._closing = False
        self.queue = RequestQueue(client, self)
        self.puts = ProfilePuts(self.queue, lambda: self.profile,
                                lambda text: self._emit_later(self.failed, text))
        self.store = RemoteStore(self.puts, self.queue.request)
        self.listing = ProfileListing(self.queue, self.store, self.puts.pending_ids,
                                      lambda: self._emit_later(self.profiles_changed))
        self.follower = ActiveFollower(self, self.queue, self.puts, self.store, self.listing,
                                       lambda: self._emit_later(self.view_changed))
        self.queue.put_done = self.puts.put_done
        self.puts.saved = self.store.remember
        self.puts.foreign = self.follower.foreign_change
        self._reconnect = QTimer(self)
        self._reconnect.setInterval(RECONNECT_MS)
        self._reconnect.timeout.connect(self._try_reconnect)
        client.event.connect(self._on_event)
        client.disconnected.connect(self._on_disconnected)

    @property
    def online(self) -> bool:
        return self.queue.online

    # --- Verbindung --------------------------------------------------------------------

    def start(self, timeout: float = READY_TIMEOUT_S,
              starter: Callable[[], None] | None = None) -> bool:
        """Verbinden (Dienst notfalls starten), anmelden, Ansicht und aktives Profil holen;
        die Profilliste laedt danach im Hintergrund (``profiles_changed``).

        ``False``, wenn der Dienst binnen ``timeout`` nicht erreichbar ist oder nicht antwortet.
        """
        if not self.client.connect_or_start(timeout=timeout, starter=starter):
            return False
        self._resync()
        wait_for(lambda: (self.profile is not None and self.settings_snapshot is not None)
                 or not self.online, READY_TIMEOUT_S)
        return self.online and self.profile is not None  # Profilnamen kommen nach

    def close(self) -> None:
        self._closing = True
        self._reconnect.stop()
        self.client.close()

    def _resync(self) -> None:
        """Nach dem (Wieder-)Verbinden: anmelden, Einstellungen, Ausstehendes senden, Ansicht
        und aktives Profil holen; die Profilliste (und ihr Vorab-Laden) erst danach, damit sie
        den Start nie aufhaelt."""
        self.queue.online = True
        self.queue.requeue(Op("settings.get", {}, self._on_settings))
        self.queue.requeue(Op("subscribe", {"role": EDITOR_ROLE}, self._on_subscribed))
        self.queue.enqueue(Op("view.get", {}, self.follower.resync_view))
        self._emit_later(self.online_changed, True)

    def _try_reconnect(self) -> None:
        if self.client.connect_to_server(0.2):
            self._reconnect.stop()
            log.info("Verbindung zum Dienst wieder da (%d Profile ausstehend)",
                     self.pending_count())
            self._resync()

    def _on_disconnected(self) -> None:
        self.queue.disconnected()
        self.listing.reset()
        self.follower.reset()
        self.puts.reset()
        if self._closing:
            return
        log.warning("Verbindung zum Dienst getrennt (%d Profile ausstehend)",
                    self.pending_count())
        self._emit_later(self.online_changed, False)
        self._reconnect.start()

    def _on_settings(self, result, error) -> None:
        if error is None and isinstance(result, dict):
            self.settings_snapshot = result

    def _on_subscribed(self, result, error) -> None:
        if error is None and isinstance(result, dict):
            editors = result.get("editors", 0)
            self.other_editors = editors if isinstance(editors, int) else 0

    # --- ServiceLink ---------------------------------------------------------------------

    def request(self, method: str, params: dict | None = None,
                timeout: float = REQUEST_TIMEOUT_S) -> Any:
        """Auftrag einreihen und auf die Antwort warten; ``ApiError`` bei Fehler/Trennung."""
        return self.queue.request(method, params, timeout)

    def request_async(self, method: str, params: dict | None, callback: Callback) -> None:
        """Auftrag ohne zu warten (z. B. ``apps.list``); Antwort ueber die Ereignisschleife."""
        self.queue.request_async(method, params, callback)

    def drain(self, timeout: float) -> bool:
        """Warten, bis kein Profil mehr unterwegs ist; ``True``, wenn danach alles beim Dienst
        gespeichert ist (``False`` nach ``timeout`` oder bei abgelehnten Profilen)."""
        wait_for(lambda: not self.queue.pending_puts(), timeout)
        return self.pending_count() == 0

    def pending_count(self) -> int:
        """Profile, die noch nicht beim Dienst gespeichert sind (auch abgelehnte)."""
        return self.puts.pending_count()

    # --- Engine-Schnittstelle fuer das Fenster -----------------------------------------

    @property
    def workspace(self) -> Workspace | None:
        if self.profile is None:
            return None
        return next((w for w in self.profile.workspaces if w.id == self.workspace_id), None)

    def set_profile(self, profile: Profile, *, keep_view: bool = False) -> None:
        """Bearbeitetes Profil an den Dienst (speichert und zeigt es am Geraet)."""
        self.profile = profile
        if self.workspace is None:  # Arbeitsbereich geloescht: wie die Engine zum Heim
            ids = [w.id for w in profile.workspaces]
            home = profile.home_workspace
            self.workspace_id = home if home in ids else (ids[0] if ids else None)
            self.page_index = 0
        else:
            self.page_index = max(0, min(self.page_index, len(self.workspace.touch_pages) - 1))
        self.puts.put(profile.to_json())

    def show_workspace(self, ws_id: str) -> None:
        """Arbeitsbereich ``ws_id`` (Seite 1): sofort im Fenster, dann am Geraet (``view.set``)."""
        if self.profile is None:
            return
        if not any(w.id == ws_id for w in self.profile.workspaces):
            log.warning("Arbeitsbereich %r gibt es nicht", ws_id)
            return
        self.workspace_id, self.page_index = ws_id, 0
        if self.online:  # sonst zeigt der Dienst nach dem Wiederverbinden seine Ansicht
            self.follower.view_set({"workspace": ws_id})

    def show_page(self, index: int) -> None:
        """Seite ``index`` des aktuellen Arbeitsbereichs, wie ``show_workspace``."""
        ws = self.workspace if self.profile is not None else None
        if ws is None or not ws.touch_pages:
            return
        if not is_int(index) or not 0 <= index < len(ws.touch_pages):
            log.warning("Seite %r gibt es nicht", index)
            return
        self.page_index = index
        if self.online:
            self.follower.view_set({"workspace": ws.id, "page": index})

    def _send(self, what: str, method: str, params: dict, *,
              quiet_disconnect: bool = False) -> None:
        """Auftrag ohne Antwort; Fehler als „<what> …“ in der Statuszeile."""
        if not self.online:
            self._emit_later(self.failed, tr("{what} nicht möglich: {reason}", what=what,
                                             reason=tr(NOT_CONNECTED)))
            return

        def done(result, error):
            if error is not None and not (quiet_disconnect
                                          and error_code(error) == ERR_DISCONNECTED):
                self._emit_later(self.failed, tr("{what} fehlgeschlagen: {error}",
                                                 what=what, error=error))

        self.queue.enqueue(Op(method, params, done))

    def trigger(self, ref: ControlRef, action: dict | None, *, steps: int = 0) -> None:
        """„Testen“: die gezeigte Aktion im Dienst ausloesen (auch ungespeichert)."""
        if (action or {}).get("type"):
            self._send(tr("Testen"), "trigger", {"ref": format_ref(ref),
                                             "action": copy.deepcopy(action), "steps": steps})

    def simulate(self, event: dict) -> None:
        """Modus „Simulieren“: ``event`` (wie ``protocol.event_to_dict``) geht an den Dienst,
        als kaeme es vom Geraet."""
        self._send(tr("Simulieren"), "simulate", {"event": dict(event)}, quiet_disconnect=True)

    def handle(self, event: Event) -> None:
        """``EditorBackend.handle``: Ereignis an den Dienst (``simulate``)."""
        self.simulate(event_to_dict(event))

    def switch_profile(self, pid: str) -> None:
        """Profil im Dienst aktivieren und abwarten; Fehler als ``ApiError`` (deutsch)."""
        self.request("profile.activate", {"id": pid})
        data = self.request("profile.get", {"id": pid})
        view = self.request("view.get")
        if not isinstance(data, dict) or not isinstance(view, dict):
            raise ApiError("reply.unexpected", N_("Unerwartete Antwort des Dienstes"))
        self.follower.adopt(pid, data, view)

    def set_theme(self, name: str, scanlines: bool) -> None:
        """Theme im Dienst merken (und dort anwenden); das Fenster hat es schon."""
        if not self.online:
            self._emit_later(self.failed, tr("Theme nicht gespeichert: {error}",
                                             error=tr(NOT_CONNECTED)))
            return

        def done(result, error):
            if error is not None:
                self._emit_later(self.failed, tr("Theme nicht gespeichert: {error}", error=error))

        self.queue.enqueue(Op("settings.put", {"theme": name, "theme_scanlines": scanlines},
                              done))

    # --- Ereignisse ----------------------------------------------------------------------

    def _emit_later(self, signal, *args) -> None:
        QTimer.singleShot(0, self, lambda: signal.emit(*args))

    def _on_event(self, name: str, data: dict) -> None:
        if name == "view.changed":
            self.follower.apply_view(data, from_event=True)
        elif name == "profile.changed":
            self.follower.profile_changed(data)
        elif name == "device.state":
            self._emit_later(self.device_state, data)
        elif name == "value":
            self._emit_later(self.value, str(data.get("ref", "")), str(data.get("text", "")))
        elif name == "raise":
            self._emit_later(self.raise_requested)
