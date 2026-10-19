"""Transport der JSON-API: ``QLocalServer``, Verbindungen, Zeilen, Ereignisse.

Laeuft im GUI-Thread (Signale des QLocalServer); nichts hier blockiert die Ereignisschleife.
Vollstaendige Zeilen gehen an ``on_line(verbindung, zeile)``; was dort passiert (Methoden,
Antworten), weiss der Transport nicht.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QAbstractSocket, QLocalServer, QLocalSocket

from .protocol import EDITOR_ROLE, LineBuffer, LineTooLong, encode

log = logging.getLogger(__name__)

PROBE_TIMEOUT_MS = 500
MAX_EVENT_BACKLOG = 4 * 1024 * 1024  # liest ein Abonnent nicht mehr: Verbindung trennen


class Connection:
    """Eine Client-Verbindung: Socket, Zeilenpuffer, Abo und Rolle (``editor``)."""

    def __init__(self, sock: QLocalSocket) -> None:
        self.sock = sock
        self.buf = LineBuffer()
        self.subscribed = False
        self.role: str | None = None
        self.closed = False


class LocalServer(QObject):
    """Lauscht unter ``name``; ``on_line`` bekommt jede vollstaendige Anfragezeile."""

    def __init__(self, name: str, on_line: Callable[[Connection, bytes], None]) -> None:
        super().__init__()
        self.name = name
        self._on_line = on_line
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._accept)
        self._conns: list[Connection] = []
        self.accepted = 0  # angenommene Verbindungen insgesamt

    @property
    def connections(self) -> list[Connection]:
        """Offene Verbindungen (Kopie)."""
        return list(self._conns)

    @property
    def full_name(self) -> str:
        """Voller Socket-Pfad (leer, solange nicht gelauscht wird)."""
        return self._server.fullServerName()

    def listen(self) -> bool:
        """Socket belegen. ``False``, wenn schon eine Instanz lauscht (oder ein anderer Fehler).

        Ein liegengebliebener Socket wird nur entfernt, wenn ihn ein frischer
        Verbindungsversuch als tot bestaetigt – nie der Socket einer laufenden Instanz.
        """
        if self._server.isListening():
            return True
        ok = self._server.listen(self.name)
        if not ok and self._server.serverError() == \
                QAbstractSocket.SocketError.AddressInUseError:
            if self._alive():
                log.info("API-Socket %s: es läuft schon eine Instanz", self.name)
                return False
            log.info("API-Socket %s: liegengebliebener Socket wird entfernt", self.name)
            QLocalServer.removeServer(self.name)
            ok = self._server.listen(self.name)
        if not ok:
            log.warning("API-Socket %s: %s", self.name, self._server.errorString())
            return False
        try:  # nur der eigene Benutzer darf verbinden (die API kann Befehle ausloesen)
            Path(self._server.fullServerName()).chmod(0o600)
        except OSError as e:
            log.warning("API-Socket %s: Rechte nicht gesetzt: %s", self.name, e)
        return True

    def _alive(self) -> bool:
        probe = QLocalSocket()
        probe.connectToServer(self.name)
        alive = probe.waitForConnected(PROBE_TIMEOUT_MS)
        probe.abort()
        return alive

    def close(self) -> None:
        for conn in list(self._conns):
            self._kill(conn)
        self._server.close()

    # --- Verbindungen ----------------------------------------------------------------

    def _accept(self) -> None:
        while self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            conn = Connection(sock)
            self._conns.append(conn)
            self.accepted += 1
            sock.readyRead.connect(lambda c=conn: self._read(c))
            sock.disconnected.connect(lambda c=conn: self._drop(c))
            if sock.bytesAvailable():
                self._read(conn)

    def _read(self, conn: Connection) -> None:
        if conn.closed:
            return
        try:
            lines = conn.buf.feed(bytes(conn.sock.readAll()))
        except LineTooLong:
            log.warning("API: Zeile zu lang – Verbindung geschlossen")
            self._kill(conn)
            return
        for line in lines:
            if conn.closed:
                return
            self._on_line(conn, line)

    def _drop(self, conn: Connection) -> None:
        """Gegenstelle hat getrennt: zuletzt Gesendetes noch verarbeiten, dann aufraeumen."""
        self._read(conn)
        self._kill(conn)

    def _kill(self, conn: Connection) -> None:
        if conn.closed:
            return
        conn.closed = True
        if conn in self._conns:
            self._conns.remove(conn)
        sock = conn.sock
        sock.abort()  # kann disconnected sofort ausloesen (-> _drop, dann ohne Wirkung)
        sock.deleteLater()

    def send(self, conn: Connection, data: bytes) -> None:
        if conn.closed or conn.sock.state() != QLocalSocket.LocalSocketState.ConnectedState:
            return
        conn.sock.write(data)

    # --- Ereignisse ------------------------------------------------------------------

    def emit_event(self, name: str, data: dict) -> None:
        """Ereignis an alle Verbindungen, die ``subscribe`` aufgerufen haben."""
        msg = None
        for conn in list(self._conns):
            if not conn.subscribed or conn.closed:
                continue
            if conn.sock.bytesToWrite() > MAX_EVENT_BACKLOG:
                log.warning("API: Abonnent liest nicht (%d Bytes offen) – Verbindung getrennt",
                            conn.sock.bytesToWrite())
                self._kill(conn)
                continue
            msg = msg or encode({"event": name, "data": data})
            self.send(conn, msg)

    def editors(self, exclude: Connection | None = None) -> list[Connection]:
        """Angemeldete Editoren (``subscribe`` mit Rolle ``editor``)."""
        return [c for c in self._conns if c is not exclude and c.subscribed and not c.closed
                and c.role == EDITOR_ROLE]

    def raise_editor(self) -> bool:
        """Angemeldete Editoren nach vorn holen (Ereignis ``raise``); ``False``, wenn keiner
        laeuft."""
        editors = self.editors()
        msg = encode({"event": "raise", "data": {}})
        for conn in editors:
            self.send(conn, msg)
        return bool(editors)
