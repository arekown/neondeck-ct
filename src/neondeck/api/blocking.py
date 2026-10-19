"""Blockierender Client der JSON-API ohne Qt (CLI): ``socket.AF_UNIX``, eine JSON-Zeile je
Nachricht (``protocol``). Nie im Dienst oder Editor benutzen (wartet ohne Ereignisschleife).
"""
from __future__ import annotations

import socket
import time
from typing import Any

from ..core.i18n import N_, tr
from .protocol import (
    DISCONNECTED,
    ERR_DISCONNECTED,
    ERR_NO_REPLY,
    ERR_NOT_CONNECTED,
    NOT_CONNECTED,
    ApiError,
    LineBuffer,
    decode,
    encode,
    local_socket_file,
    reply_error,
    socket_path,
)

READ_SIZE = 64 * 1024


class BlockingClient:
    """Eine Verbindung zum Dienst unter ``name`` (ohne Angabe die Standardadresse)."""

    def __init__(self, name: str | None = None) -> None:
        self.name = name or socket_path()
        self._sock: socket.socket | None = None
        self._buf = LineBuffer()
        self._next_id = 0

    def connect(self, timeout: float) -> bool:
        """Ein Verbindungsversuch (hoechstens ``timeout`` Sekunden)."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(str(local_socket_file(self.name)))
        except OSError:
            sock.close()
            return False
        self._sock, self._buf = sock, LineBuffer()
        return True

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def call(self, method: str, params: dict | None = None, timeout: float = 5.0) -> Any:
        """Anfrage senden und auf die Antwort warten; ``ApiError`` bei Fehlerantwort,
        Trennung oder Zeitueberschreitung."""
        if self._sock is None:
            raise ApiError(ERR_NOT_CONNECTED, NOT_CONNECTED)
        self._next_id += 1
        rid = self._next_id
        deadline = time.monotonic() + timeout
        try:
            self._sock.settimeout(timeout)
            self._sock.sendall(encode({"id": rid, "method": method, "params": params or {}}))
            msg = self._reply(rid, deadline)
        except TimeoutError:
            raise ApiError(ERR_NO_REPLY, N_("Keine Antwort vom Dienst ({method})"),
                           {"method": method}) from None
        except OSError:
            raise ApiError(ERR_DISCONNECTED, DISCONNECTED) from None
        error = reply_error(msg)
        if error is not None:
            raise ApiError.from_error(error)
        return msg.get("result")

    def _reply(self, rid: int, deadline: float) -> dict:
        """Zeilen lesen, bis die Antwort ``rid`` kommt (Ereignisse und Fremdes uebergehen)."""
        while True:
            for line in self._lines(deadline):
                try:
                    msg = decode(line)
                except ValueError:
                    continue  # kaputte Zeile: wie der Qt-Client uebergehen
                if isinstance(msg, dict) and "event" not in msg and msg.get("id") == rid:
                    return msg

    def _lines(self, deadline: float) -> list[bytes]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        self._sock.settimeout(remaining)
        data = self._sock.recv(READ_SIZE)
        if not data:
            raise ConnectionResetError(tr(DISCONNECTED))
        return self._buf.feed(data)
