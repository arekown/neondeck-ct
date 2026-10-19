"""Zwischenspeicher fuer langsame Leser der API (Dateien, Prozesse), nie im GUI-Thread."""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ..core.guard import call_logged
from ..core.i18n import N_, tr
from ..core.workers import Poster, Worker
from .protocol import ErrorText
from .router import Later

log = logging.getLogger(__name__)


class Cached:
    """Ergebnis eines langsamen Lesers: im Hintergrund gelesen, ``ttl`` Sekunden
    zwischengespeichert; gleichzeitige Anfragen teilen sich einen Lesevorgang. ``get``
    liefert das Ergebnis oder ein ``Later`` (Antwort ueber den Poster im GUI-Thread)."""

    def __init__(self, what: str, load: Callable[[], Any], ttl: float,
                 clock: Callable[[], float], poster: Poster) -> None:
        self._what, self._load, self._ttl, self._clock = what, load, ttl, clock
        self._worker = Worker(f"api-{what}", poster=poster)
        self._value: Any = None
        self._time = 0.0
        self._waiting: list[Later] = []
        self._loading = False

    def get(self) -> Any:
        if self._value is not None and self._clock() - self._time < self._ttl:
            return self._value
        later = Later()
        self._waiting.append(later)
        if not self._loading:
            self._loading = True
            self._worker.submit(self._load, self._on_loaded)
        return later

    def _on_loaded(self, result, exc: BaseException | None) -> None:
        """Im GUI-Thread (ueber den Poster)."""
        error = None
        if exc is not None:
            log.error("API: %s nicht gelesen", self._what, exc_info=exc)
            result, error = None, ErrorText(N_("{what} nicht gelesen: {error}"), "read_failed",
                                            {"what": tr(self._what), "error": str(exc)})
        self._loading = False
        if result is not None:
            self._value, self._time = result, self._clock()
        waiting, self._waiting = self._waiting, []
        for later in waiting:
            call_logged(later.finish, result, error, what="API: Antwort (%s) nicht gesendet",
                        what_args=(self._what,), logger=log)
