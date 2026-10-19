"""Auftraege an den Dienst der Reihe nach (hoechstens einer unterwegs), damit z. B. „neue Seite
speichern, dann zeigen“ in dieser Reihenfolge ankommt; Warten auf Antworten, ohne die
Ereignisschleife anzuhalten.

Bricht die Verbindung ab, bleiben Speicher-Auftraege (``Op.pid``) in der Warteschlange und gehen
nach dem Wiederverbinden raus; alle anderen verfallen mit ``LOST``.
"""
from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QEventLoop, QObject, QTimer

from ...api.client import NOT_CONNECTED, ApiClient, ApiError, lost
from ...api.protocol import ERR_NO_REPLY, ERR_NOT_CONNECTED, ErrorText
from ...core.guard import call_logged
from ...core.i18n import N_

log = logging.getLogger(__name__)

REQUEST_TIMEOUT_S = 5.0
POLL_MS = 10

Callback = Callable[[Any, str | None], None]


@dataclass
class Op:
    """Ein Auftrag an den Dienst; ``pid`` nur bei ``profile.put`` (ueberlebt Trennungen)."""
    method: str
    params: dict
    callback: Callback | None = None
    pid: str | None = None


def wait_for(pred: Callable[[], bool], timeout: float) -> bool:
    """Bis ``pred()`` wahr ist oder ``timeout`` Sekunden um sind; die Ereignisschleife laeuft
    weiter (ohne Benutzereingaben)."""
    if pred():
        return True
    loop = QEventLoop()
    check = QTimer()
    check.setInterval(POLL_MS)
    check.timeout.connect(lambda: loop.quit() if pred() else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    check.start()
    deadline.start(max(1, round(timeout * 1000)))
    loop.exec(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
    check.stop()
    deadline.stop()
    return pred()


def run_callback(op: Op, result, error) -> None:
    if op.callback is None:
        return
    call_logged(op.callback, result, error, what="API-Rückruf %s fehlgeschlagen",
                what_args=(op.method,), logger=log)


class RequestQueue:
    """``owner`` ist das QObject, ueber dessen Ereignisschleife Rueckrufe von ``request_async``
    laufen; ``put_done(op, result, error)`` bekommt die Antworten der Speicher-Auftraege."""

    def __init__(self, client: ApiClient, owner: QObject) -> None:
        self._client = client
        self._owner = owner
        self.put_done: Callable[[Op, Any, str | None], None] = run_callback
        self.online = False
        self._queue: deque[Op] = deque()
        self._inflight: Op | None = None

    def enqueue(self, op: Op) -> None:
        self._queue.append(op)
        self.pump()

    def requeue(self, op: Op) -> None:
        """Vor alle wartenden stellen, ohne gleich zu senden (Wiederverbinden, Nachreichen)."""
        self._queue.appendleft(op)

    def pump(self) -> None:
        if self._inflight is not None or not self.online or not self._queue:
            return
        op = self._queue.popleft()
        self._inflight = op
        try:
            self._client.call(op.method, op.params, lambda r, e, op=op: self._done(op, r, e))
        except ApiError:  # eben getrennt: der Abbruch kommt gleich
            self._inflight = None
            self._queue.appendleft(op)

    def _done(self, op: Op, result, error) -> None:
        if self._inflight is op:
            self._inflight = None
        try:
            if op.pid is not None:
                self.put_done(op, result, error)
            else:
                run_callback(op, result, error)
        finally:
            self.pump()

    def disconnected(self) -> None:
        """Verbindung weg: nur Speicher-Auftraege bleiben, die anderen verfallen mit ``LOST``."""
        self.online = False
        dropped = [op for op in self._queue if op.pid is None]
        self._queue = deque(op for op in self._queue if op.pid is not None)
        for op in dropped:
            run_callback(op, None, lost())

    # --- Speicher-Auftraege ------------------------------------------------------------

    def pending_puts(self) -> list[Op]:
        """Speicher-Auftraege unterwegs und wartend, in Reihenfolge."""
        ops = [self._inflight] if self._inflight is not None else []
        return [op for op in ops + list(self._queue) if op.pid is not None]

    def waiting_put(self, pid: str) -> Op | None:
        """Noch nicht gesendeter Speicher-Auftrag fuer ``pid``."""
        return next((op for op in self._queue if op.pid == pid), None)

    def inflight_put(self, pid: str) -> Op | None:
        op = self._inflight
        return op if op is not None and op.pid == pid else None

    def drop_puts(self, pid: str) -> None:
        self._queue = deque(op for op in self._queue if op.pid != pid)

    # --- Anfragen ----------------------------------------------------------------------

    def request(self, method: str, params: dict | None = None,
                timeout: float = REQUEST_TIMEOUT_S) -> Any:
        """Auftrag einreihen und auf die Antwort warten (Ereignisschleife laeuft weiter);
        alles vorher Eingereihte kommt zuerst an. ``ApiError`` bei Fehler/Trennung."""
        if not self.online:
            raise ApiError(ERR_NOT_CONNECTED, NOT_CONNECTED)
        got: list = []
        self.enqueue(Op(method, params or {}, lambda r, e: got.append((r, e))))
        if not wait_for(lambda: bool(got), timeout):
            raise ApiError(ERR_NO_REPLY, N_("Keine Antwort vom Dienst ({method})"),
                           {"method": method})
        result, error = got[0]
        if error is not None:
            raise ApiError.from_error(error)
        return result

    def request_async(self, method: str, params: dict | None, callback: Callback) -> None:
        """Auftrag ohne zu warten; ``callback(result, error)`` kommt spaeter ueber die
        Ereignisschleife (nie mitten im Lesen)."""
        def done(result, error):
            QTimer.singleShot(0, self._owner, lambda: callback(result, error))

        if not self.online:
            done(None, ErrorText(NOT_CONNECTED, ERR_NOT_CONNECTED))
            return
        self.enqueue(Op(method, params or {}, done))
