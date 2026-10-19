"""Speicher-Auftraege des Editors (``profile.put``) und ihr Abgleich mit fremden Aenderungen.

Je Profil wartet hoechstens ein Stand (der neueste). Lehnt der Dienst ein Profil ab, bleibt es
als „ungespeichert“ stehen (das naechste Speichern versucht es neu, Schliessen fragt nach).
Eigene ``profile.changed`` (der Dienst schickt je gespeichertem Profil eines, vor der Antwort)
werden mitgezaehlt und nicht fuer fremde gehalten: kamen waehrend eigener Auftraege mehr
Aenderungen als eigene Bestaetigungen, hat jemand anderes das Profil geaendert (``foreign``).
"""
from __future__ import annotations

import copy
import logging
from collections.abc import Callable

from ...api.protocol import ERR_DISCONNECTED, error_code
from ...core.i18n import tr
from ...profile.model import Profile
from .queue import Op, RequestQueue

log = logging.getLogger(__name__)


def _ignore(*_) -> None:
    pass


class ProfilePuts:
    """``active()`` ist das Profil, das der Editor zeigt, ``failed(text)`` meldet in der
    Statuszeile. Zu verbinden: ``saved(pid, data)`` merkt einen vom Dienst bestaetigten Stand,
    ``foreign(pid)`` meldet eine fremde Aenderung."""

    def __init__(self, queue: RequestQueue, active: Callable[[], Profile | None],
                 failed: Callable[[str], None]) -> None:
        self._queue = queue
        self._active = active
        self._failed_text = failed
        self.saved: Callable[[str, dict], None] = _ignore
        self.foreign: Callable[[str], None] = _ignore
        self._seen: dict[str, int] = {}  # profile.changed je Profil, waehrend es aussteht
        self._own: dict[str, int] = {}   # davon eigene: bestaetigte profile.put
        self._failed: dict[str, dict] = {}  # vom Dienst abgelehnt: ungespeichert
        self.base: dict | None = None    # aktives Profil, wie der Dienst es zuletzt hatte

    def pending_ids(self) -> set[str]:
        return {op.pid for op in self._queue.pending_puts()} | set(self._failed)

    def pending_count(self) -> int:
        """Profile, die noch nicht beim Dienst gespeichert sind (auch abgelehnte)."""
        return len(self.pending_ids())

    def pending_json(self, pid: str) -> dict | None:
        """Neuester noch nicht bestaetigter Stand von ``pid`` (oder ``None``)."""
        ops = [op for op in self._queue.pending_puts() if op.pid == pid]
        return ops[-1].params["profile"] if ops else self._failed.get(pid)

    def dirty(self, profile: Profile | None) -> bool:
        """Hat ``profile`` Aenderungen, die der Dienst noch nicht bestaetigt hat (in der
        Warteschlange, abgelehnt oder noch im Fenster gebuendelt)?"""
        if profile is None:
            return False
        return self.pending_json(profile.id) is not None or profile.to_json() != self.base

    def put(self, data: dict) -> None:
        """Profil an den Dienst; ein noch wartender Stand desselben Profils wird ersetzt."""
        data = copy.deepcopy(data)
        pid = data.get("id")
        self._failed.pop(pid, None)  # neuer Versuch
        waiting = self._queue.waiting_put(pid)
        if waiting is not None:
            waiting.params = {"profile": data}
            return
        inflight = self._queue.inflight_put(pid)
        if inflight is not None and inflight.params["profile"] == data:
            return  # genau das ist schon unterwegs (Fenster: speichern + anzeigen)
        self._queue.enqueue(Op("profile.put", {"profile": data}, pid=pid))

    def drop_puts(self, pid: str) -> None:
        self._queue.drop_puts(pid)
        self._failed.pop(pid, None)

    def note_change(self, pid: str) -> bool:
        """``profile.changed`` fuer ``pid``; ``True``, wenn es aussteht (wird abgerechnet)."""
        if pid not in self.pending_ids():
            return False
        self._seen[pid] = self._seen.get(pid, 0) + 1
        return True

    def reset(self) -> None:
        """Nach einer Trennung: was dabei geschah, klaert das Wiederverbinden."""
        self._seen.clear()
        self._own.clear()

    def put_done(self, op: Op, result, error) -> None:
        pid, data = op.pid, op.params["profile"]
        newer = self._queue.waiting_put(pid) is not None
        if error_code(error) == ERR_DISCONNECTED:  # nachreichen (ausser es wartet schon ein neuerer Stand)
            if not newer:
                self._queue.requeue(op)
            return
        if error is not None:
            log.warning("Profil %s nicht gespeichert: %s", pid, error)
            if not newer:
                self._failed[pid] = data
            self._failed_text(tr("Speichern fehlgeschlagen: {error}", error=error))
            return
        self._own[pid] = self._own.get(pid, 0) + 1
        self.saved(pid, data)
        active = self._active()
        if active is not None and active.id == pid:
            self.base = data
        if newer or pid in self._failed:
            return  # weitere eigene Staende folgen: erst danach abrechnen
        if self._seen.pop(pid, 0) - self._own.pop(pid, 0) > 0:
            self.foreign(pid)  # zwischendurch hat jemand anderes das Profil geaendert
