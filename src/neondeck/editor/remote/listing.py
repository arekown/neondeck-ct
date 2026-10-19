"""Profilliste des Editors: ``profile.list`` und das Vorab-Laden der Profile im Hintergrund,
damit die Profilauswahl Namen zeigt (``changed`` nur, wenn sich die Liste wirklich aendert)."""
from __future__ import annotations

from collections.abc import Callable

from ...api.protocol import ERR_DISCONNECTED, error_code
from .queue import Op, RequestQueue
from .store import RemoteStore


class ProfileListing:
    def __init__(self, queue: RequestQueue, store: RemoteStore,
                 pending_ids: Callable[[], set[str]], changed: Callable[[], None]) -> None:
        self._queue = queue
        self._store = store
        self._pending_ids = pending_ids
        self._changed = changed
        self._prefetch: set[str] = set()
        self._queued = False
        self._signature: tuple | None = None

    def reset(self) -> None:
        self._prefetch.clear()
        self._queued = False

    def refresh(self) -> None:
        if not self._queued:
            self._queued = True
            self._queue.enqueue(Op("profile.list", {}, self._got_list))

    def _got_list(self, result, error) -> None:
        self._queued = False
        if error is not None or not isinstance(result, list):
            return
        entries = {}
        for e in result:
            if isinstance(e, dict) and isinstance(e.get("id"), str):
                entries[e["id"]] = {"name": str(e.get("name") or e["id"]),
                                    "ok": bool(e.get("ok", True))}
        self._store.set_entries(entries)
        pending = self._pending_ids()
        for pid in self._store.missing():
            if pid not in pending and pid not in self._prefetch:
                self._prefetch.add(pid)
                self._queue.enqueue(Op("profile.get", {"id": pid},
                                       lambda r, e, pid=pid: self._got_stored(pid, r, e)))
        self._done()

    def _got_stored(self, pid: str, result, error) -> None:
        self._prefetch.discard(pid)
        if error is None and isinstance(result, dict):
            self._store.remember(pid, result)
        elif error is not None and error_code(error) != ERR_DISCONNECTED:
            self._store.set_error(pid, str(error))
        self._done()

    def _done(self) -> None:
        if self._prefetch or self._queued:
            return
        sig = self._store.signature()
        if sig != self._signature:
            self._signature = sig
            self._changed()
