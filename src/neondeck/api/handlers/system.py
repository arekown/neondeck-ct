"""API-Methoden rund um den Dienst: ``ping``, ``status``, ``subscribe``, ``open_config``,
``diag``, ``screensaver.start`` und die Auswahllisten ``apps.list``/``kde.shortcuts``."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from PySide6.QtCore import QObject, QTimer

from ...actions import kde_shortcuts
from ...core import desktop_apps
from ...core.i18n import N_
from ...core.workers import Poster
from ..cache import Cached
from ..contracts import ServiceFacade
from ..params import Setting, Spec, api_method
from ..protocol import ApiError, ErrorText
from ..router import Later
from ..transport import Connection
from . import Handlers

log = logging.getLogger(__name__)

APPS_TTL_S = 60.0  # .desktop-Liste so lange zwischenspeichern
SHORTCUTS_TTL_S = 60.0  # Liste der KDE-Kuerzel ebenso
FIRMWARE_WAIT_S = 0.8  # diag: so lange auf die Firmware-Antwort des Geraets warten
FIRMWARE_POLL_MS = 50


def read_apps() -> list[dict]:
    return [asdict(a) for a in desktop_apps.list_apps()]


def read_shortcuts() -> list[dict]:
    return [{"component": c, "name": n, "friendly": f}
            for c, n, f in kde_shortcuts.list_shortcuts()]


class SystemHandlers(Handlers):
    """``editors(ausser)`` zaehlt angemeldete Editoren, ``socket()`` nennt den Socket-Pfad;
    ``context`` ist das QObject fuer die Diagnose-Timer."""

    def __init__(self, service: Callable[[], ServiceFacade], *,
                 editors: Callable[[Connection], int], socket: Callable[[], str],
                 context: QObject, clock: Callable[[], float], poster: Poster) -> None:
        super().__init__(service)
        self._editors, self._socket, self._context, self._clock = editors, socket, context, clock
        self._apps = Cached(N_("Anwendungen"), read_apps, APPS_TTL_S, clock, poster)
        self._shortcuts = Cached(N_("KDE-Kürzel"), read_shortcuts, SHORTCUTS_TTL_S, clock, poster)

    @api_method("ping")
    def ping(self) -> str:
        return "pong"

    @api_method("status")
    def status(self) -> dict:
        f, e = self.facade, self.engine
        dev = f.device_status()
        return {"connected": dev["connected"], "serial": dev["serial"],
                "profile": e.profile.id, "profile_name": e.profile.name,
                "workspace": e.workspace_id, "page": e.page_index, **e.folder_state(),
                "theme": f.settings.theme, "dynamic_mode": f.dynamic_mode,
                "locked": e.locked, "display_asleep": e.display_asleep}

    @api_method("subscribe", with_conn=True, role=Spec())
    def subscribe(self, conn: Connection, role: Any) -> dict:
        """Ereignisse abonnieren; Antwort: wie viele *andere* Editoren angemeldet sind."""
        others = self._editors(conn)
        conn.subscribed = True
        conn.role = role if isinstance(role, str) else None
        return {"editors": others}

    @api_method("open_config")
    def open_config(self) -> dict:
        self.facade.open_config()
        return {}

    @api_method("apps.list")
    def apps(self) -> Any:
        return self._apps.get()

    @api_method("kde.shortcuts")
    def shortcuts(self) -> Any:
        return self._shortcuts.get()

    @api_method("screensaver.start", name=Setting(key="screensaver"))
    def screensaver(self, name: str | None) -> dict:
        if not self.facade.start_screensaver(name):
            raise ApiError("screensaver.dark",
                           N_("Gerät ist gesperrt oder schläft – kein Bildschirmschoner"))
        return {"started": True}

    # --- Diagnose --------------------------------------------------------------------

    def _info(self) -> dict:
        data = dict(self.facade.diag_info())
        data["socket"] = self._socket()
        return data

    @staticmethod
    def _result(info: dict) -> dict:
        from ...diagnose import run_checks  # Diagnose laedt viel: erst bei Bedarf
        return {"service": info, "checks": [asdict(c) for c in run_checks(service=info)]}

    @api_method("diag")
    def diag(self) -> Any:
        """Diagnose aus Sicht des Dienstes: dessen Zustand plus alle Pruefungen. Ist das
        Geraet verbunden, aber die Firmware noch unbekannt, kommt die Antwort, sobald das
        Geraet sie gemeldet hat (hoechstens ``FIRMWARE_WAIT_S``)."""
        info = self._info()
        if not info.get("connected") or info.get("firmware"):
            return self._result(info)
        later = Later()
        deadline = self._clock() + FIRMWARE_WAIT_S

        def check() -> None:
            try:
                now = self._info()
                if now.get("firmware") or not now.get("connected") or \
                        self._clock() >= deadline:
                    later.finish(self._result(now))
                else:
                    QTimer.singleShot(FIRMWARE_POLL_MS, self._context, check)
            except Exception as e:
                log.exception("API: Diagnose fehlgeschlagen")
                later.finish(None, ErrorText(N_("Diagnose fehlgeschlagen: {error}"), "diag.failed",
                                                {"error": str(e)}))

        QTimer.singleShot(FIRMWARE_POLL_MS, self._context, check)
        return later
