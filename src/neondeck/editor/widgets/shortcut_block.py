"""Globale KDE-Kuerzel sperren, solange eine Tastenaufnahme den Fokus hat
(``org.kde.KGlobalAccel.blockGlobalShortcuts``) – sonst wuerde z. B. Alt+F4 beim Aufnehmen
gleich das Fenster schliessen.

Eine gemeinsame Sperre je Prozess (``shared``); ``install`` (beim Start des Editors) sorgt
dafuer, dass sie beim Programmende frei wird. Tests tauschen sie mit ``replace`` aus.
"""
from __future__ import annotations

import atexit
import logging
from collections.abc import Callable

from ...core.errors import DBusError
from ...desktop import dbus

log = logging.getLogger(__name__)

BLOCK_TIMEOUT_MS = 500  # Sperre beim Aufnehmen: kurz, sonst ohne Sperre weiter


def kglobalaccel_block(on: bool) -> None:
    """Globale KDE-Kuerzel sperren/freigeben (Session-Bus, kurz und blockierend)."""
    try:
        dbus.call("org.kde.kglobalaccel", "/kglobalaccel", "org.kde.KGlobalAccel",
                  "blockGlobalShortcuts", on, timeout=BLOCK_TIMEOUT_MS)
    except DBusError as e:
        log.info("Globale Kuerzel nicht %s: %s", "gesperrt" if on else "freigegeben", e)


class ShortcutBlock:
    """Zaehlt Sperr-Wuensche; nur der Wechsel 0 <-> 1 geht an KDE."""

    def __init__(self, call: Callable[[bool], None] = kglobalaccel_block) -> None:
        self._call = call
        self._holders: set[int] = set()

    def hold(self, key: int) -> None:
        if key not in self._holders:
            self._holders.add(key)
            if len(self._holders) == 1:
                self._safe(True)

    def release(self, key: int) -> None:
        if key in self._holders:
            self._holders.discard(key)
            if not self._holders:
                self._safe(False)

    def release_all(self) -> None:
        if self._holders:
            self._holders.clear()
            self._safe(False)

    def _safe(self, on: bool) -> None:
        try:
            self._call(on)
        except Exception as e:  # noqa: BLE001 - ohne KDE/Bus: nur ohne Sperre aufnehmen
            log.info("Globale Kuerzel: %s", e)


class _Shared:
    """Die gemeinsame Sperre des Prozesses (erst bei Bedarf angelegt)."""

    def __init__(self) -> None:
        self.block: ShortcutBlock | None = None
        self.installed = False

    def get(self) -> ShortcutBlock:
        if self.block is None:
            self.block = ShortcutBlock()
        return self.block


_SHARED = _Shared()


def shared() -> ShortcutBlock:
    return _SHARED.get()


def replace(block: ShortcutBlock | None) -> ShortcutBlock | None:
    """Gemeinsame Sperre austauschen (Tests); gibt die bisherige zurueck."""
    old, _SHARED.block = _SHARED.block, block
    return old


def install() -> None:
    """Beim Programmende alle Sperren freigeben (einmal je Prozess, beim Start aufrufen)."""
    if not _SHARED.installed:
        _SHARED.installed = True
        atexit.register(lambda: shared().release_all())
