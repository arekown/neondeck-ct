"""Hintergrundarbeit: benannte Worker mit ``submit(work, done)``.

``work`` laeuft in einem Hintergrund-Thread des Workers; ``done(ergebnis, fehler)`` kommt
ueber den ``Poster`` in den Hauptthread (ohne Poster im Worker-Thread). Jeder Auftrag
liefert ein ``Future`` (Ergebnis oder Ausnahme); geloggt wird hier nichts – Fehler gehen an
``done`` bzw. ins ``Future``. Die Threads sind Daemon-Threads und starten erst beim ersten
Auftrag. Ohne Qt: die Qt-Umsetzung des ``Poster`` steckt in ``ui.poster``.
"""
from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any, Protocol

from .guard import call_logged

log = logging.getLogger(__name__)

Done = Callable[[Any, BaseException | None], None]
_STOP = object()


class Poster(Protocol):
    """Reicht Aufrufe aus beliebigen Threads in den Hauptthread (nicht blockierend)."""

    def post(self, fn: Callable[[], None]) -> None: ...


class Worker:
    """Bis zu ``threads`` Hintergrund-Threads, die Auftraege der Reihe nach abarbeiten."""

    def __init__(self, name: str, *, threads: int = 1, poster: Poster | None = None) -> None:
        self.name = name
        self._max = max(1, threads)
        self._poster = poster
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()
        self._closed = False

    def submit(self, work: Callable[[], Any], done: Done | None = None) -> Future:
        """``work`` einreihen; ``RuntimeError`` nach ``shutdown``."""
        future: Future = Future()
        with self._lock:
            if self._closed:
                raise RuntimeError(f"Worker {self.name} ist beendet")
            self._queue.put((future, work, done))
            if len(self._threads) < self._max:
                t = threading.Thread(target=self._loop, daemon=True,
                                     name=f"{self.name}-{len(self._threads) + 1}")
                self._threads.append(t)
                t.start()
        return future

    def shutdown(self, *, wait: bool = False, cancel: bool = False) -> None:
        """Keine neuen Auftraege mehr; ``cancel`` verwirft noch nicht begonnene, ``wait``
        wartet, bis die Threads alles Begonnene (bzw. ohne ``cancel`` alles) erledigt haben.
        Mehrfach aufrufbar."""
        with self._lock:
            self._closed = True
            threads = list(self._threads)
        if cancel:
            self._cancel_pending()
        for _ in threads:
            self._queue.put(_STOP)
        if wait:
            for t in threads:
                if t is not threading.current_thread():
                    t.join()

    def _cancel_pending(self) -> None:
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            if item is not _STOP:
                item[0].cancel()

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                return
            future, work, done = item
            if not future.set_running_or_notify_cancel():
                continue
            try:
                result, error = work(), None
            except Exception as e:  # noqa: BLE001 - geht an done bzw. ins Future
                result, error = None, e
                future.set_exception(e)
            else:
                future.set_result(result)
            if done is not None:
                self._finish(done, result, error)

    def _finish(self, done: Done, result: Any, error: BaseException | None) -> None:
        if self._poster is not None:
            self._poster.post(lambda: done(result, error))
        else:
            call_logged(done, result, error, what="Worker %s: Rueckruf fehlgeschlagen",
                        what_args=(self.name,), logger=log)
