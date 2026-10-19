"""JSON-API des Dienstes: setzt Transport (``transport.LocalServer``), Methodentabelle
(``router.Router``) und Handler-Gruppen (``handlers``) zusammen.

Laeuft im GUI-Thread (Signale des QLocalServer), wie die Engine; kein Aufruf blockiert die
Ereignisschleife. Der Socket (``protocol.socket_path``) ist zugleich die Einzelinstanz-Sperre:
ein zweiter Start meldet sich mit ``open_config`` und beendet sich.

Die *Fassade* ist der laufende Dienst (Vertrag ``contracts.ServiceFacade``; ``api`` zeigt
nach ``attach`` auf den Server).

Der Editor (eigener Prozess) meldet sich mit ``subscribe {"role": "editor"}`` an;
``raise_editor`` holt ihn mit dem Ereignis ``raise`` nach vorn.
"""
from __future__ import annotations

import time
from collections.abc import Callable

from ..core.workers import Poster
from .contracts import ServiceFacade
from .handlers.profiles import ProfileHandlers
from .handlers.settings import SettingsHandlers
from .handlers.system import SystemHandlers
from .handlers.view import ViewHandlers
from .protocol import socket_path
from .router import Handler, Router
from .transport import Connection, LocalServer


class ApiServer:
    """``clock``: Uhr fuer Zwischenspeicher und Diagnose-Frist (Tests geben eine eigene)."""

    def __init__(self, facade: ServiceFacade | None = None, name: str | None = None, *,
                 poster: Poster, clock: Callable[[], float] = time.monotonic) -> None:
        self.facade: ServiceFacade | None = None
        self.transport = LocalServer(name or socket_path(), self._dispatch)
        self._router = Router(self.transport.send, lambda: self.facade is not None)
        service = self._facade
        self._router.add(
            SystemHandlers(service, editors=lambda conn: len(self.transport.editors(conn)),
                           socket=lambda: self.transport.full_name or self.name,
                           context=self.transport, clock=clock, poster=poster),
            ProfileHandlers(service, self.emit_event), ViewHandlers(service),
            SettingsHandlers(service))
        if facade is not None:
            self.attach(facade)

    def _facade(self) -> ServiceFacade:
        return self.facade

    def attach(self, facade: ServiceFacade) -> None:
        """Fassade setzen (vorher beantwortet der Server nur ``ping``)."""
        self.facade = facade
        facade.add_listener(self.emit_event)
        facade.api = self

    @property
    def name(self) -> str:
        return self.transport.name

    @property
    def methods(self) -> dict[str, Handler]:
        """Methodentabelle ``name -> (verbindung, params) -> ergebnis``."""
        return self._router.methods

    @property
    def connections(self) -> list[Connection]:
        return self.transport.connections

    def listen(self) -> bool:
        return self.transport.listen()

    def close(self) -> None:
        self.transport.close()

    def emit_event(self, name: str, data: dict) -> None:
        self.transport.emit_event(name, data)

    def raise_editor(self) -> bool:
        return self.transport.raise_editor()

    def _dispatch(self, conn: Connection, line: bytes) -> None:
        self.handle_line(conn, line)  # zur Laufzeit nachgeschlagen: Tests halten Zeilen an

    def handle_line(self, conn: Connection, line: bytes) -> None:
        """Eine Anfragezeile beantworten."""
        self._router.handle_line(conn, line)
