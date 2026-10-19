"""Qt-Client der JSON-API (Editor-Prozess, Tests) und Starten von Dienst und Editor.

Asynchron ueber Rueckrufe (``call``) fuer Prozesse mit Ereignisschleife; ``call_wait``
wartet mit laufender Ereignisschleife (ohne Benutzereingaben) auf die Antwort (Editor, Tests
mit Dienst im selben Prozess). Die CLI nimmt den blockierenden Client ohne Qt
(``api.blocking``).
"""
from __future__ import annotations

import logging
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEventLoop, QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalSocket

from ..core import proc
from ..core.guard import call_logged
from ..core.i18n import N_
from ..core.paths import launcher_path
from . import protocol
from .protocol import (
    CONNECT_TIMEOUT_S,
    DISCONNECTED,
    EDITOR_CONNECT_TIMEOUT_S,
    ERR_DISCONNECTED,
    ERR_NO_REPLY,
    ERR_NOT_CONNECTED,
    NOT_CONNECTED,
    ApiError,
    ErrorText,
    LineBuffer,
    LineTooLong,
    decode,
    encode,
    reply_error,
    socket_path,
)

log = logging.getLogger(__name__)

Callback = Callable[[Any, str | None], None]  # (result, error); error als ErrorText


def lost() -> ErrorText:
    """Rueckruf-Fehler bei Trennung (erst bei Gebrauch gebaut: Sprache des Prozesses)."""
    return ErrorText(DISCONNECTED, ERR_DISCONNECTED)


POLL_S = 0.05

__all__ = ["CONNECT_TIMEOUT_S", "DISCONNECTED", "EDITOR_CONNECT_TIMEOUT_S",
           "NOT_CONNECTED", "ApiClient", "ApiError", "start_editor", "start_service"]


def _command(args: list[str]) -> tuple[list[str], dict | None]:
    """``~/.local/bin/neondeck-ct <args>``, sonst ``python -m neondeck <args>``
    aus diesem Quellbaum (dann mit passendem ``PYTHONPATH``)."""
    launcher = launcher_path()
    if launcher.is_file() and os.access(launcher, os.X_OK):
        return [str(launcher), *args], None
    src = str(Path(__file__).resolve().parents[2])
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(
        x for x in (src, os.environ.get("PYTHONPATH")) if x))
    return [sys.executable, "-m", "neondeck", *args], env


def _spawn(cmd: list[str], env: dict | None) -> None:
    """Losgeloest starten (eigene Sitzung, keine geerbten Ein-/Ausgaben)."""
    proc.spawn_detached(cmd, env=env)


def _server_args(server_name: str | None) -> list[str]:
    return ["--server", server_name] if server_name and server_name != socket_path() else []


def start_service(server_name: str | None = None) -> None:
    """Dienst losgeloest starten; ``server_name`` nur, wenn er nicht unter der
    Standardadresse lauschen soll."""
    cmd, env = _command(_server_args(server_name))
    log.info("Dienst wird gestartet: %s", " ".join(cmd))
    _spawn(cmd, env)


def start_editor(server_name: str | None = None) -> None:
    """Editor-Prozess (``--config``) losgeloest starten; ``server_name`` nur, wenn der
    Dienst nicht unter der Standardadresse lauscht."""
    cmd, env = _command(["--config", *_server_args(server_name)])
    log.info("Editor wird gestartet: %s", " ".join(cmd))
    _spawn(cmd, env)


def _pause(seconds: float) -> None:
    """Warten, ohne die Ereignisschleife anzuhalten."""
    loop = QEventLoop()
    QTimer.singleShot(max(1, round(seconds * 1000)), loop.quit)
    loop.exec()


class ApiClient(QObject):
    connected = Signal()
    disconnected = Signal()
    event = Signal(str, object)  # Name, Daten (nach ``subscribe``)

    def __init__(self, name: str | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._default = not name  # Standardadresse: auch aeltere Instanzen suchen
        self.name = name or socket_path()
        self._sock = QLocalSocket(self)
        self._sock.readyRead.connect(self._read)
        self._sock.connected.connect(self.connected)
        self._sock.disconnected.connect(self._on_disconnected)
        self._buf = LineBuffer()
        self._next_id = 0
        self._pending: dict[int, Callback | None] = {}

    # --- Verbindung -------------------------------------------------------------------

    def is_connected(self) -> bool:
        return self._sock.state() == QLocalSocket.LocalSocketState.ConnectedState

    def connect_to_server(self, timeout: float = 1.0) -> bool:
        """Ein Verbindungsversuch (blockiert hoechstens ``timeout`` Sekunden)."""
        if self.is_connected():
            return True
        self._sock.abort()
        self._buf = LineBuffer()
        self._sock.connectToServer(self.name)
        return self._sock.waitForConnected(max(1, round(timeout * 1000)))

    def connect_or_start(self, timeout: float = 5.0,
                         starter: Callable[[], None] | None = None) -> bool:
        """Verbinden; laeuft der Dienst nicht, ihn starten (``starter``, Standard
        ``start_service`` mit dieser Adresse) und bis ``timeout`` Sekunden auf ihn warten.
        Die Ereignisschleife laeuft dabei weiter.

        Bei der Standardadresse wird vor dem Starten auch die Adresse aelterer Versionen
        probiert: Laeuft dort noch eine Instanz, wird sie benutzt statt eine zweite zu starten.
        """
        if self.connect_to_server(min(timeout, 0.5)):
            return True
        if self._default:
            own = self.name
            for legacy in protocol.legacy_names():
                self.name = legacy
                if self.connect_to_server(min(timeout, 0.5)):
                    log.warning("Dienst läuft noch unter der alten Adresse %s – bitte neu "
                                "starten", legacy)
                    return True
            self.name = own
        try:
            (starter or (lambda: start_service(self.name)))()
        except OSError as e:
            log.error("Dienst nicht gestartet: %s", e)
            return False
        deadline = time.monotonic() + timeout
        while True:
            if self.connect_to_server(0.1):
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                log.warning("Dienst %s nach %.1f s nicht erreichbar", self.name, timeout)
                return False
            _pause(min(POLL_S, remaining))

    def close(self) -> None:
        if self._sock.state() != QLocalSocket.LocalSocketState.UnconnectedState:
            self._sock.disconnectFromServer()

    # --- Aufrufe ----------------------------------------------------------------------

    def call(self, method: str, params: dict | None = None,
             callback: Callback | None = None) -> int:
        """Anfrage senden; ``callback(result, error)`` kommt aus der Ereignisschleife
        (``error`` ist ``None`` oder ein ``ErrorText``: Text mit ``code``)."""
        if not self.is_connected():
            raise ApiError(ERR_NOT_CONNECTED, NOT_CONNECTED)
        self._next_id += 1
        rid = self._next_id
        data = encode({"id": rid, "method": method, "params": params or {}})
        self._pending[rid] = callback
        self._sock.write(data)
        self._sock.flush()
        return rid

    def call_wait(self, method: str, params: dict | None = None,
                  timeout: float = 5.0) -> Any:
        """Anfrage senden und mit laufender Ereignisschleife auf die Antwort warten.

        Benutzereingaben bleiben solange liegen; Sockets und Timer laufen weiter (auch ein
        Dienst im selben Prozess). Wirft ``ApiError`` bei Fehlerantwort, Trennung oder
        Zeitueberschreitung.
        """
        got: list = []
        loop = QEventLoop()

        def done(result, error):
            got.append((result, error))
            loop.quit()

        rid = self.call(method, params, done)
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(max(1, round(timeout * 1000)))
        if not got:
            loop.exec(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        timer.stop()
        if not got:
            self._pending.pop(rid, None)
            raise ApiError(ERR_NO_REPLY, N_("Keine Antwort vom Dienst ({method})"),
                           {"method": method})
        result, error = got[0]
        if error is not None:
            raise ApiError.from_error(error)
        return result

    # --- Empfang ----------------------------------------------------------------------

    def _read(self) -> None:
        try:
            lines = self._buf.feed(bytes(self._sock.readAll()))
        except LineTooLong:
            log.warning("API: Antwortzeile zu lang – Verbindung getrennt")
            self._sock.abort()
            return
        for line in lines:
            try:
                msg = decode(line)
            except Exception:  # noqa: BLE001 - kaputtes JSON, UTF-8, Verschachtelung …
                log.warning("API: kaputte Antwortzeile ignoriert")
                continue
            if not isinstance(msg, dict):
                continue
            if "event" in msg:
                data = msg.get("data")
                self.event.emit(str(msg["event"]), data if isinstance(data, dict) else {})
                continue
            rid = msg.get("id")
            if rid not in self._pending:
                continue
            cb = self._pending.pop(rid)
            if cb is not None:
                self._deliver(cb, msg.get("result"), reply_error(msg))

    def _on_disconnected(self) -> None:
        self._read()  # zuletzt Empfangenes noch zustellen
        pending, self._pending = self._pending, {}
        for cb in pending.values():
            if cb is not None:
                self._deliver(cb, None, lost())
        self.disconnected.emit()

    @staticmethod
    def _deliver(cb: Callback, result: Any, error: str | None) -> None:
        call_logged(cb, result, error, what="API-Rückruf fehlgeschlagen", logger=log)
