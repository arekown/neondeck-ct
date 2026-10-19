"""Einzelinstanz des Dienstes: bei einer laufenden Instanz melden, Sperrdatei halten."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path

from PySide6.QtNetwork import QLocalSocket

from ..api import protocol
from ..core import paths

CONNECT_TIMEOUT_MS = 1000
LOCK_FILE = "service.lock"


def notify_running(name: str | None = None) -> bool:
    """Meldet sich bei einer laufenden Instanz: Anfrage ``open_config`` (die laufende
    Instanz oeffnet dann die Einstellungen). ``False``, wenn keine laeuft.

    Ohne ``name``: Standardadresse und die Adresse aelterer Versionen."""
    names = [name] if name else [protocol.socket_path(), *protocol.legacy_names()]
    return any(_notify(n) for n in names)


def lock_path() -> Path:
    return paths.state_dir() / LOCK_FILE


def acquire_instance_lock() -> int | None:
    """Sperre fuer die Laufzeit des Dienstes (``flock`` im Zustandsordner, unabhaengig von
    Socket-Adresse und ``XDG_RUNTIME_DIR``); ``None``, wenn schon ein Dienst sie haelt."""
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


def _notify(name: str) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(name)
    if not sock.waitForConnected(CONNECT_TIMEOUT_MS):
        return False
    sock.write(protocol.encode({"id": 1, "method": "open_config", "params": {}}))
    sock.waitForBytesWritten(CONNECT_TIMEOUT_MS)
    sock.disconnectFromServer()  # die Antwort wird nicht abgewartet
    if sock.state() != QLocalSocket.LocalSocketState.UnconnectedState:
        sock.waitForDisconnected(CONNECT_TIMEOUT_MS)
    return True
