"""KWin-Scripting ueber D-Bus: Skripte laden, starten und entladen (``org.kde.KWin``
``/Scripting``), ohne Introspektion (``QDBusInterface`` fragt bei jedem Anlegen blockierend
die Schnittstelle ab)."""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtDBus import QDBusConnection

from ..core.errors import DBusError
from . import dbus

log = logging.getLogger(__name__)

KWIN_SERVICE = "org.kde.KWin"
SCRIPTING_PATH = "/Scripting"
SCRIPTING_IFACE = "org.kde.kwin.Scripting"
SCRIPT_IFACE = "org.kde.kwin.Script"

# kwin_iface_factory(pfad, interface) -> Objekt mit call(methode, *args) -> Antwortwerte | None
KWinIfaceFactory = Callable[[str, str], Any]


class KWinRemote:
    """Ein KWin-Objekt; ``call`` liefert die Antwortwerte oder ``None`` (Fehler im Log)."""

    def __init__(self, bus: QDBusConnection, path: str, interface: str) -> None:
        self._bus, self._path, self._iface = bus, path, interface

    def call(self, method: str, *args) -> list | None:
        try:
            return dbus.call(KWIN_SERVICE, self._path, self._iface, method, *args, bus=self._bus)
        except DBusError as e:
            log.warning("KWin %s.%s: %s", self._path, method, e)
            return None


class KWinScripts:
    """Laden/Starten/Entladen ueber ``factory(pfad, interface)`` (Tests: Ersatz-KWin)."""

    def __init__(self, factory: KWinIfaceFactory) -> None:
        self._factory = factory

    def _scripting(self) -> Any:
        return self._factory(SCRIPTING_PATH, SCRIPTING_IFACE)

    def load(self, path: Path, name: str) -> int | None:
        """Skript laden und starten (ein liegengebliebenes gleichen Namens vorher entladen);
        Skriptnummer oder ``None``."""
        scripting = self._scripting()
        scripting.call("unloadScript", name)
        reply = scripting.call("loadScript", str(path), name)
        sid = reply[0] if reply else None
        if not isinstance(sid, int) or sid < 0:
            log.warning("KWin loadScript %s: keine gültige Skriptnummer (%r)", name, reply)
            return None
        if self._factory(f"{SCRIPTING_PATH}/Script{sid}", SCRIPT_IFACE).call("run") is None:
            log.warning("KWin-Skript %s (Nr. %s) ließ sich nicht starten", name, sid)
            scripting.call("unloadScript", name)
            return None
        return sid

    def unload(self, name: str) -> None:
        self._scripting().call("unloadScript", name)
