"""Qt-Umsetzung von ``core.workers.Poster``: Aufrufe aus beliebigen Threads in den GUI-Thread."""
from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, Signal, Slot

from ..core.guard import call_logged

log = logging.getLogger(__name__)


class QtPoster(QObject):
    """Reicht Aufrufe aus beliebigen Threads in den GUI-Thread (QueuedConnection).

    ``run`` fuehrt im GUI-Thread direkt und abgesichert aus; nach ``enabled = False``
    (Beenden) passiert nichts mehr."""

    _call = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.enabled = True
        self._call.connect(self.run, Qt.ConnectionType.QueuedConnection)

    def post(self, fn: Callable[[], None]) -> None:
        self._call.emit(fn)

    @Slot(object)
    def run(self, fn: Callable[[], None]) -> None:
        if not self.enabled:
            return  # nach dem Beenden nichts mehr ausfuehren
        call_logged(fn, what="Aufruf im GUI-Thread fehlgeschlagen", logger=log)
