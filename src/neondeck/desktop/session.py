"""Sitzungswaechter: Standby (logind) und Bildschirmsperre (Bildschirmschoner) per D-Bus.

* System-Bus, ``org.freedesktop.login1.Manager.PrepareForSleep(bool)``: ``true`` kurz vor dem
  Standby (-> ``about_to_sleep``), ``false`` nach dem Aufwachen (-> ``resumed``).
* Session-Bus, ``org.freedesktop.ScreenSaver.ActiveChanged(bool)`` auf
  ``/org/freedesktop/ScreenSaver``: KDE meldet dort Sperren/Entsperren (-> ``locked``).

Die Signale von logind ``Session.Lock``/``Unlock`` sind *Aufforderungen* an den Sperrbildschirm,
kein Zustand (Sperren per Meta+L sendet sie nicht); ``ActiveChanged`` meldet den Zustand selbst.
Belegt am 18.10.2026 per ``busctl introspect`` an Plasma 6.7 / systemd-logind.

Nur Abos auf den vorhandenen Bus-Verbindungen – es wird nichts aufgerufen, gesperrt oder in
den Standby geschickt. Tests geben Ersatz-Busse (``connect``/``disconnect``) mit.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import SLOT, QObject, Signal, Slot
from PySide6.QtDBus import QDBusConnection

from .dbus import SignalSubscriptions, Subscription

log = logging.getLogger(__name__)

LOGIN1_SERVICE = "org.freedesktop.login1"
LOGIN1_PATH = "/org/freedesktop/login1"
LOGIN1_MANAGER = "org.freedesktop.login1.Manager"
SCREENSAVER_SERVICE = "org.freedesktop.ScreenSaver"
SCREENSAVER_PATH = "/org/freedesktop/ScreenSaver"
SCREENSAVER_IFACE = "org.freedesktop.ScreenSaver"


class SessionWatcher(QObject):
    """Meldet Standby (``about_to_sleep``/``resumed``) und Sperre (``locked(bool)``)."""

    about_to_sleep = Signal()
    resumed = Signal()
    locked = Signal(bool)

    def __init__(self, bus: QDBusConnection | None = None,
                 system_bus: QDBusConnection | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._bus = bus if bus is not None else QDBusConnection.sessionBus()
        self._system_bus = system_bus if system_bus is not None else QDBusConnection.systemBus()
        self._subs = SignalSubscriptions(self, "Standby/Sperre wird dafür nicht erkannt")

    def _wanted(self) -> list[Subscription]:
        return [
            (self._system_bus, LOGIN1_SERVICE, LOGIN1_PATH, LOGIN1_MANAGER, "PrepareForSleep",
             SLOT("onPrepareForSleep(bool)")),
            (self._bus, SCREENSAVER_SERVICE, SCREENSAVER_PATH, SCREENSAVER_IFACE,
             "ActiveChanged", SLOT("onActiveChanged(bool)")),
        ]

    @property
    def active_signals(self) -> list[str]:
        """Namen der abonnierten Signale (leer: Waechter laeuft nicht)."""
        return self._subs.names

    def start(self) -> bool:
        """Signale abonnieren; ``False``, wenn eins davon nicht ging (die anderen bleiben)."""
        if self._subs.active:
            return True
        ok = self._subs.start(self._wanted())
        if self._subs.active:
            log.info("Sitzungswächter aktiv (%s)", ", ".join(self._subs.names))
        return ok

    def stop(self) -> None:
        """Abos aufheben (mehrfach aufrufbar)."""
        self._subs.stop()

    @Slot(bool)
    def onPrepareForSleep(self, starting: bool) -> None:
        try:
            if starting:
                log.info("Standby beginnt")
                self.about_to_sleep.emit()
            else:
                log.info("Aus dem Standby aufgewacht")
                self.resumed.emit()
        except Exception:
            log.exception("Standby-Signal nicht verarbeitet")

    @Slot(bool)
    def onActiveChanged(self, active: bool) -> None:
        try:
            log.info("Bildschirm %s", "gesperrt" if active else "entsperrt")
            self.locked.emit(bool(active))
        except Exception:
            log.exception("Sperr-Signal nicht verarbeitet")
