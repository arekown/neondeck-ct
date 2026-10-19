"""QtDBus-Hilfen: Methodenaufrufe (blockierend und asynchron) und Signal-Abos.

Ein Ort fuer den Nachrichtenbau (``QDBusMessage.createMethodCall`` + Argumente), die
Zeitgrenze ``CALL_TIMEOUT_MS`` und das An-/Abmelden von Signalen. Ohne Introspektion
(``QDBusInterface`` fragt bei jedem Anlegen blockierend die Schnittstelle ab).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from functools import partial
from typing import Any

from PySide6.QtDBus import (
    QDBus,
    QDBusConnection,
    QDBusMessage,
    QDBusPendingCallWatcher,
    QDBusVariant,
)

from ..core.errors import DBusError
from ..core.guard import call_logged

log = logging.getLogger(__name__)

CALL_TIMEOUT_MS = 2000  # lokale Dienste antworten sofort; haengt einer, nicht ewig warten

# Rueckruf-Form: service, pfad, interface, methode, argumente, fertig(werte | None)
AsyncCaller = Callable[[str, str, str, str, list, Callable[[list | None], None]], None]


def message(service: str, path: str, iface: str, method: str, *args: Any) -> QDBusMessage:
    msg = QDBusMessage.createMethodCall(service, path, iface, method)
    msg.setArguments(list(args))
    return msg


def plain(value: Any) -> Any:
    """``QDBusVariant`` auspacken, alles andere unveraendert."""
    return value.variant() if isinstance(value, QDBusVariant) else value


def call(service: str, path: str, iface: str, method: str, *args: Any,
         bus: QDBusConnection | None = None, timeout: int = CALL_TIMEOUT_MS) -> list:
    """Blockierender Aufruf (Session-Bus, wenn ``bus`` fehlt); Antwortwerte oder
    ``DBusError`` mit der Fehlermeldung des Dienstes."""
    bus = bus if bus is not None else QDBusConnection.sessionBus()
    reply = bus.call(message(service, path, iface, method, *args), QDBus.CallMode.Block,
                     timeout)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        raise DBusError(reply.errorMessage())
    return list(reply.arguments())


class AsyncCall:
    """Asynchrone Aufrufe auf einer Bus-Verbindung (``QDBusPendingCallWatcher``); erfuellt
    ``AsyncCaller``. ``done`` bekommt die Antwortwerte oder ``None`` bei einem Fehler."""

    def __init__(self, bus: QDBusConnection, timeout: int = CALL_TIMEOUT_MS) -> None:
        self._bus = bus
        self._timeout = timeout
        self._watchers: set[QDBusPendingCallWatcher] = set()

    def __call__(self, service: str, path: str, iface: str, method: str, args: list,
                 done: Callable[[list | None], None]) -> None:
        pending = self._bus.asyncCall(message(service, path, iface, method, *args),
                                      self._timeout)
        watcher = QDBusPendingCallWatcher(pending)
        self._watchers.add(watcher)  # bis zur Antwort am Leben halten
        watcher.finished.connect(partial(self._finished, watcher, done))

    def _finished(self, watcher: QDBusPendingCallWatcher, done, *_: Any) -> None:
        self._watchers.discard(watcher)
        values = None if watcher.isError() else [plain(v) for v in watcher.reply().arguments()]
        watcher.deleteLater()
        call_logged(done, values, what="D-Bus-Antwort nicht verarbeitet", logger=log)


# Ein Abo: (bus, service, pfad, interface, signal, slot)
Subscription = tuple[Any, str, str, str, str, str]


class SignalSubscriptions:
    """Signal-Abos eines Empfaengers; merkt sich die gelungenen, damit ``stop`` genau diese
    abmeldet."""

    def __init__(self, receiver: Any, consequence: str) -> None:
        self._receiver = receiver
        self._consequence = consequence  # Warnungstext, wenn ein Abo scheitert
        self.active: list[Subscription] = []

    @property
    def names(self) -> list[str]:
        """Namen der abonnierten Signale."""
        return [s[4] for s in self.active]

    def start(self, wanted: list[Subscription]) -> bool:
        """Alle abonnieren; ``False``, wenn eins davon nicht ging (die anderen bleiben)."""
        ok = True
        for sub in wanted:
            bus, service, path, iface, name, slot = sub
            if bus.connect(service, path, iface, name, self._receiver, slot):
                self.active.append(sub)
            else:
                ok = False
                log.warning("D-Bus-Signal %s.%s nicht abonniert – %s", iface, name,
                            self._consequence)
        return ok

    def stop(self) -> None:
        """Abos aufheben (mehrfach aufrufbar)."""
        active, self.active = self.active, []
        for bus, service, path, iface, name, slot in active:
            bus.disconnect(service, path, iface, name, self._receiver, slot)
