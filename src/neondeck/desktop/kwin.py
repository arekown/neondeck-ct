"""KWin-Fensterwaechter: aktives Fenster und Fensterliste, ereignisgesteuert per KWin-Skript.

Der Dienst belegt auf dem Session-Bus ``io.github.arekown.NeondeckCT`` und stellt ``/Window``
(Interface ``io.github.arekown.NeondeckCT.Window``) bereit. Das dauerhaft geladene KWin-Skript
``data/kwin/neondeck-ct.js`` ruft dort per ``callDBus`` auf:

* ``activated(resourceClass, desktopFileName, caption, pid)`` bei jedem Fensterwechsel,
* ``windowsChanged(json)`` beim Start und wenn ein Anwendungsfenster dazukommt/verschwindet,
* ``placement(resourceClass, desktopFileName, pid)`` fuer jedes neue Anwendungsfenster:
  die Antwort (JSON ``{"screen", "place"}`` oder leer) sagt, wohin es soll
  (``core.placement``; die Geometrie rechnet das Skript).

Es gibt keine Abfrage im Takt (Polling legte bei anderen Werkzeugen Plasma lahm) und keine
D-Bus-Verbindung je Ereignis: alles laeuft ueber die eine Session-Bus-Verbindung.

Teile: ``KWinScripts`` (Skripte laden/entladen), ``WindowFocus`` (Einmal-Skript zum
Fokussieren), ``core.placement.PlacementBook`` (Platzierungswuensche); ``KWinWatcher``
setzt sie mit dem D-Bus-Objekt zusammen.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import ClassInfo, QObject, Signal, Slot
from PySide6.QtDBus import QDBusConnection

from ..core import paths
from ..core.placement import PlacementBook, Ticket
from ..core.windows import WindowInfo
from .focus import FOCUS_SCRIPT_NAME, WindowFocus
from .kwin_scripts import KWinIfaceFactory, KWinRemote, KWinScripts

log = logging.getLogger(__name__)

SERVICE = "io.github.arekown.NeondeckCT"
OBJECT_PATH = "/Window"
INTERFACE = "io.github.arekown.NeondeckCT.Window"
SCRIPT_NAME = "neondeck-ct"
LEGACY_SCRIPT_NAME = "loupedeck-linux"  # Name vor der Umbenennung: beim Start entladen

__all__ = ["FOCUS_SCRIPT_NAME", "LEGACY_SCRIPT_NAME", "OBJECT_PATH", "SCRIPT_NAME", "SERVICE",
           "KWinWatcher"]


def script_path() -> Path:
    return paths.bundled_dir() / "kwin" / "neondeck-ct.js"


@ClassInfo({"D-Bus Interface": INTERFACE})
class _Receiver(QObject):
    """Das auf dem Bus veroeffentlichte Objekt; die Slot-Namen sind die D-Bus-Methoden.
    Jeder Aufruf geht an einen Rueckruf; Fehler bleiben im Log (nie zurueck nach KWin)."""

    def __init__(self, on_activated: Callable[[WindowInfo], None],
                 on_windows: Callable[[str], None],
                 on_placement: Callable[[str, str, int], str]) -> None:
        super().__init__()
        self._on_activated, self._on_windows = on_activated, on_windows
        self._on_placement = on_placement

    @Slot(str, str, str, int)
    def activated(self, resource_class: str, desktop_file: str, caption: str, pid: int) -> None:
        try:
            self._on_activated(WindowInfo(resource_class, desktop_file, caption, pid))
        except Exception:
            log.exception("Fensterwechsel nicht verarbeitet")

    @Slot(str)
    def windowsChanged(self, data: str) -> None:
        try:
            self._on_windows(data)
        except Exception:
            log.exception("Fensterliste nicht verarbeitet")

    @Slot(str, str, int, result=str)
    def placement(self, resource_class: str, desktop_file: str, pid: int) -> str:
        try:
            return self._on_placement(resource_class, desktop_file, pid)
        except Exception:
            log.exception("Platzierung nicht beantwortet")
            return ""


def parse_windows(data: str) -> list[WindowInfo] | None:
    """JSON-Liste aus dem KWin-Skript; ``None`` bei jeder Abweichung vom Format."""
    try:
        raw = json.loads(data)
    except ValueError:
        return None
    if not isinstance(raw, list):
        return None
    out = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        texts = [item.get(k, "") for k in ("resourceClass", "desktopFileName", "caption",
                                            "internalId")]
        pid = item.get("pid", 0)
        if not all(isinstance(t, str) for t in texts) or isinstance(pid, bool) \
                or not isinstance(pid, (int, float)):
            return None
        rc, df, cap, iid = texts
        out.append(WindowInfo(rc, df, cap, int(pid), iid))
    return out


class KWinWatcher(QObject):
    """Meldet Fensterwechsel (``activated``) und die Fensterliste (``windows_changed``)."""

    activated = Signal(object)        # WindowInfo
    windows_changed = Signal(list)    # list[WindowInfo]

    def __init__(self, bus: QDBusConnection | None = None,
                 kwin_iface_factory: KWinIfaceFactory | None = None, *,
                 script: Path | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._bus = bus if bus is not None else QDBusConnection.sessionBus()
        self._scripts = KWinScripts(kwin_iface_factory or (
            lambda path, iface: KWinRemote(self._bus, path, iface)))
        self._focus = WindowFocus(self._scripts)
        self._script = Path(script) if script is not None else script_path()
        self._receiver = _Receiver(self.handle_activated, self.handle_windows,
                                   self.handle_placement)
        self._registered = False
        self._loaded = False
        self.windows: list[WindowInfo] = []
        self.active: WindowInfo | None = None
        self.placements = PlacementBook()

    @property
    def running(self) -> bool:
        return self._loaded

    @property
    def registered(self) -> bool:
        """D-Bus-Dienst und -Objekt fuer das KWin-Skript angemeldet."""
        return self._registered

    # --- Start / Ende --------------------------------------------------------------------

    def start(self) -> bool:
        """Dienst und Objekt anmelden, dann das KWin-Skript laden. ``False``, wenn etwas
        davon scheitert."""
        if self._loaded:
            return True
        if not self._register():
            return False
        self._scripts.unload(LEGACY_SCRIPT_NAME)  # ruft sonst den alten D-Bus-Namen auf
        sid = self._scripts.load(self._script, SCRIPT_NAME)
        if sid is None:
            log.warning("KWin-Skript %s nicht geladen – Dynamic Mode aus", self._script)
            self._unregister()
            return False
        self._loaded = True
        log.info("KWin-Fensterwächter aktiv (Skript %s)", sid)
        return True

    def _register(self) -> bool:
        if not self._bus.registerService(SERVICE):
            log.warning("D-Bus-Dienst %s nicht belegt (läuft schon ein Dienst?) – "
                        "Dynamic Mode aus", SERVICE)
            return False
        if not self._bus.registerObject(OBJECT_PATH, self._receiver,
                                        QDBusConnection.RegisterOption.ExportAllSlots):
            log.warning("D-Bus-Objekt %s nicht angemeldet – Dynamic Mode aus", OBJECT_PATH)
            self._bus.unregisterService(SERVICE)
            return False
        self._registered = True
        return True

    def stop(self) -> None:
        """KWin-Skript entladen, Dienst abmelden (mehrfach aufrufbar)."""
        if self._loaded:
            self._loaded = False
            try:
                self._scripts.unload(SCRIPT_NAME)
            except Exception:
                log.exception("KWin-Skript nicht entladen")
        self._unregister()

    def _unregister(self) -> None:
        if self._registered:
            self._registered = False
            self._bus.unregisterObject(OBJECT_PATH)
            self._bus.unregisterService(SERVICE)

    # --- Aufrufe aus dem KWin-Skript ---------------------------------------------------

    def handle_activated(self, info: WindowInfo) -> None:
        self.active = info
        self.activated.emit(info)

    def handle_windows(self, data: str) -> None:
        """Fensterliste als JSON (``windowsChanged``); Unlesbares wird verworfen."""
        windows = parse_windows(data)
        if windows is None:
            log.warning("Fensterliste von KWin unlesbar: %.200s", data)
            return
        self.windows = windows
        self.windows_changed.emit(windows)

    def handle_placement(self, resource_class: str, desktop_file: str, pid: int) -> str:
        """Neues Fenster: Antwort ``{"screen", "place"}`` als JSON oder leer."""
        ticket = self.placements.claim(resource_class, desktop_file, pid)
        if ticket is None:
            return ""
        log.info("Fenster %s (pid %s) -> %s", desktop_file or resource_class, pid,
                 ticket.reply())
        return json.dumps(ticket.reply())

    # --- Platzieren, Fokus (Aktions-Threads) ---------------------------------------------

    def expect_window(self, app_key: str, screen: str = "", place: str = "none"
                      ) -> Ticket | None:
        """Das naechste neue Fenster der App ``app_key`` auf ``screen``/``place`` setzen
        (Aktions-Thread); ``None`` ohne laufendes KWin-Skript oder ohne Wunsch."""
        if not self._loaded:
            return None
        return self.placements.expect(app_key, screen, place)

    def focus(self, app_id: str, window_id: str = "") -> bool:
        """Ein laufendes Fenster nach vorn holen: das mit der KWin-``internalId``
        ``window_id``, sonst (oder wenn es weg ist) das erste der App ``app_id``
        (desktopFileName/resourceClass). ``False``, wenn keins bekannt ist (dann startet der
        Aufrufer die App). Laeuft im Aktions-Thread (blockierende D-Bus-Aufrufe)."""
        windows = self.windows  # die Liste wird ersetzt, nie veraendert
        target = next((w for w in windows if window_id and w.internal_id == window_id), None)
        if target is None:
            target = next((w for w in windows if w.matches(app_id)), None)
        if target is None or not self._loaded:
            return False
        return self._focus.focus(target, app_id)
