"""Medien-Zustand ueber MPRIS (Zustandsquelle ``media``).

Auf dem Session-Bus werden alle Namen ``org.mpris.MediaPlayer2.*`` verfolgt
(``ListNames`` beim Start, danach ``NameOwnerChanged``) und je Player
``org.mpris.MediaPlayer2.Player.PlaybackStatus`` gelesen (``Properties.Get``).
``PropertiesChanged`` an ``/org/mpris/MediaPlayer2`` (von irgendeinem Absender) loest nach
kurzer Sammelpause ein erneutes Lesen aller Player aus – so muss der eindeutige Absendername
nicht den Playern zugeordnet und das ``a{sv}`` nicht entpackt werden.

„Spielt“ heisst: **irgendein** Player meldet ``Playing``. Belegt am 18.10.2026: hier laufen
oft mehrere Player gleichzeitig (Spotify ``Playing``, Brave ``Paused``) – „der erste Player“
waere von der Reihenfolge der Namen abhaengig.

„Wiederholen“ (``cycle_loop``) schaltet ``LoopStatus`` None -> Playlist -> Track -> None beim
spielenden Player weiter (mehrere spielen: der zuletzt angefangene), sonst beim zuletzt
spielenden, sonst beim ersten pausierten.

Alle Aufrufe sind asynchron (``asyncCall``), der GUI-Thread wartet nie. Tests geben einen
Ersatz-Bus (``connect``/``disconnect``) und einen Ersatz fuer die Aufrufe mit.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from functools import partial

from PySide6.QtCore import SLOT, QObject, QTimer, Signal, Slot
from PySide6.QtDBus import QDBusConnection, QDBusMessage, QDBusVariant

from .dbus import AsyncCall, AsyncCaller, SignalSubscriptions, Subscription

log = logging.getLogger(__name__)

PLAYER_PREFIX = "org.mpris.MediaPlayer2."
MPRIS_PATH = "/org/mpris/MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
PROPS_IFACE = "org.freedesktop.DBus.Properties"
DBUS_SERVICE = DBUS_IFACE = "org.freedesktop.DBus"
DBUS_PATH = "/org/freedesktop/DBus"
REFRESH_DELAY_S = 0.1  # PropertiesChanged kommen oft gehaeuft (Metadaten, Status)
LOOP_ORDER = ("None", "Playlist", "Track")


def next_loop(status: str) -> str:
    """Naechster ``LoopStatus`` im Kreis; Unbekanntes faengt bei ``Playlist`` an."""
    if status not in LOOP_ORDER:
        return LOOP_ORDER[1]
    return LOOP_ORDER[(LOOP_ORDER.index(status) + 1) % len(LOOP_ORDER)]


class Mpris(QObject):
    """Meldet ``changed(spielt)``, sobald sich „irgendein Player spielt“ aendert."""

    changed = Signal(bool)

    def __init__(self, bus: QDBusConnection | None = None,
                 caller: AsyncCaller | None = None,
                 call_later: Callable[[float, Callable[[], None]], None] | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._bus = bus if bus is not None else QDBusConnection.sessionBus()
        self._caller = caller or AsyncCall(self._bus)
        self._call_later = call_later or (
            lambda delay, fn: QTimer.singleShot(round(delay * 1000), self, fn))
        self._players: dict[str, str | None] = {}  # Busname -> PlaybackStatus
        self._last_playing: str | None = None  # zuletzt auf „Playing“ gewechselt
        self._playing: bool | None = None
        self._subs = SignalSubscriptions(self, "Medien-Zustand wird nicht aktualisiert")
        self._running = False
        self._refresh_pending = False

    @property
    def playing(self) -> bool | None:
        """Spielt ein Player? ``None``: noch unbekannt."""
        return self._playing

    def _wanted(self) -> list[Subscription]:
        return [(self._bus, DBUS_SERVICE, DBUS_PATH, DBUS_IFACE, "NameOwnerChanged",
                 SLOT("onNameOwnerChanged(QString,QString,QString)")),
                (self._bus, "", MPRIS_PATH, PROPS_IFACE, "PropertiesChanged",
                 SLOT("onPropertiesChanged(QDBusMessage)"))]

    def start(self) -> bool:
        """Signale abonnieren und die Player abfragen; ``False``, wenn ein Abo scheitert."""
        if self._running:
            return True
        ok = self._subs.start(self._wanted())
        self._running = True
        self._caller(DBUS_SERVICE, DBUS_PATH, DBUS_IFACE, "ListNames", [], self._on_names)
        return ok

    def stop(self) -> None:
        """Abos aufheben (mehrfach aufrufbar); spaete Antworten werden ignoriert."""
        self._running = False
        self._subs.stop()
        self._players.clear()

    # --- Abfragen -------------------------------------------------------------------------

    def _on_names(self, values: list | None) -> None:
        if not self._running or not values or not isinstance(values[0], (list, tuple)):
            return  # Fehler: Zustand bleibt unbekannt (NameOwnerChanged meldet neue Player)
        names = values[0]
        for name in names:
            if isinstance(name, str) and name.startswith(PLAYER_PREFIX):
                self._players.setdefault(name, None)
                self._query(name)
        self._update()

    def _query(self, name: str) -> None:
        self._caller(name, MPRIS_PATH, PROPS_IFACE, "Get", [PLAYER_IFACE, "PlaybackStatus"],
                     partial(self._on_status, name))

    def _on_status(self, name: str, values: list | None) -> None:
        if not self._running or name not in self._players:
            return
        status = values[0] if values and isinstance(values[0], str) else None
        if status == "Playing" and self._players.get(name) != "Playing":
            self._last_playing = name
        self._players[name] = status
        self._update()

    def _update(self) -> None:
        playing = any(s == "Playing" for s in self._players.values())
        if playing != self._playing:
            self._playing = playing
            self.changed.emit(playing)

    # --- Wiederholen ----------------------------------------------------------------------

    def loop_target(self) -> str | None:
        """Player fuer „Wiederholen“: spielend (der zuletzt angefangene zuerst), sonst der
        zuletzt spielende, sonst der erste pausierte; ``None``: keiner da."""
        playing = [n for n, s in self._players.items() if s == "Playing"]
        last = self._last_playing
        if last in playing or (not playing and last in self._players):
            return last
        if playing:
            return playing[0]
        return next((n for n, s in self._players.items() if s == "Paused"), None)

    def target(self, prefer: str = "") -> str | None:
        """Player fuer eine Medien-Aktion: enthaelt ein Player-Name ``prefer`` (z. B.
        ``spotify``), dieser, sonst wie ``loop_target``."""
        if not self._running:
            return None
        if prefer:
            hit = next((n for n in self._players if prefer.lower() in n.lower()), None)
            if hit is not None:
                return hit
        return self.loop_target()

    def control(self, method: str, prefer: str = "") -> bool:
        """``PlayPause``/``Next``/``Previous``/``Stop`` direkt beim Player aufrufen (GUI-Thread,
        asynchron) – Medientasten landen sonst beim Player, den Plasma gerade waehlt (oft der
        Browser). ``False`` ohne Player."""
        name = self.target(prefer)
        if name is None:
            log.info("Medien %s: kein MPRIS-Player", method)
            return False
        self._caller(name, MPRIS_PATH, PLAYER_IFACE, method, [],
                     partial(self._on_control, name, method))
        return True

    def _on_control(self, name: str, method: str, values: list | None) -> None:
        if values is None:
            log.warning("Medien: %s nimmt %s nicht an", name, method)

    def cycle_loop(self, prefer: str = "") -> bool:
        """``LoopStatus`` des Players weiterschalten (GUI-Thread, asynchron); ``False``
        ohne Player."""
        name = self.target(prefer)
        if name is None:
            log.info("Wiederholen: kein MPRIS-Player")
            return False
        self._caller(name, MPRIS_PATH, PROPS_IFACE, "Get", [PLAYER_IFACE, "LoopStatus"],
                     partial(self._on_loop, name))
        return True

    def _on_loop(self, name: str, values: list | None) -> None:
        if not self._running:
            return
        if not values or not isinstance(values[0], str):
            log.warning("Wiederholen: %s meldet kein LoopStatus", name)
            return
        new = next_loop(values[0])
        self._caller(name, MPRIS_PATH, PROPS_IFACE, "Set",
                     [PLAYER_IFACE, "LoopStatus", QDBusVariant(new)],
                     partial(self._on_loop_set, name, new))

    def _on_loop_set(self, name: str, new: str, values: list | None) -> None:
        if values is None:
            log.warning("Wiederholen: %s nimmt LoopStatus %s nicht an", name, new)
        else:
            log.info("Wiederholen: %s -> %s", name, new)

    def _refresh(self) -> None:
        self._refresh_pending = False
        if self._running:
            for name in list(self._players):
                self._query(name)

    # --- Signale (Slot-Namen = Signaturen fuer QDBusConnection.connect) ---------------------

    @Slot(str, str, str)
    def onNameOwnerChanged(self, name: str, old: str, new: str) -> None:
        try:
            if not self._running or not name.startswith(PLAYER_PREFIX):
                return
            if new:
                self._players[name] = None
                self._query(name)
            else:
                self._players.pop(name, None)
                self._update()
        except Exception:
            log.exception("NameOwnerChanged nicht verarbeitet")

    @Slot(QDBusMessage)
    def onPropertiesChanged(self, msg: QDBusMessage) -> None:
        try:
            args = msg.arguments()
            if not self._running or not args or args[0] != PLAYER_IFACE \
                    or self._refresh_pending:
                return
            self._refresh_pending = True
            self._call_later(REFRESH_DELAY_S, self._refresh)
        except Exception:
            log.exception("PropertiesChanged nicht verarbeitet")
