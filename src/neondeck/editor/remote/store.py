"""Profilspeicher des Editors (Stellvertreter für den ``ProfileStore`` des Dienstes).

Liest aus dem Zwischenspeicher, den ``RemoteEngine`` füllt (Beschreibung dort); offene Stände
und Speichern kommen von ``puts.ProfilePuts``, Anfragen ueber ``request``.
"""
from __future__ import annotations

import copy
from typing import Protocol

from ...api.client import ApiError
from ...core.i18n import tr
from ...profile.model import Profile
from ...ui.common import Request


class PutHost(Protocol):
    """Offene Speicher-Aufträge (``ProfilePuts``)."""

    def pending_ids(self) -> set[str]: ...
    def pending_json(self, pid: str) -> dict | None: ...
    def put(self, data: dict) -> None: ...
    def drop_puts(self, pid: str) -> None: ...


class RemoteStore:
    """Profilspeicher des Editors: liest aus dem Zwischenspeicher, schreibt ueber den Dienst;
    erfuellt ``api.contracts.ProfileRepository``.

    Fehler kommen wie beim ``ProfileStore`` als ``OSError`` (Dienst nicht erreichbar,
    Profil nicht lesbar …)."""

    def __init__(self, puts: PutHost, request: Request) -> None:
        self._puts = puts
        self._request = request
        self._entries: dict[str, dict] = {}  # profile.list: id -> {"name", "ok"}
        self._cache: dict[str, dict] = {}    # id -> Profil-JSON, wie der Dienst es hat
        self._errors: dict[str, str] = {}    # id -> Fehlertext (Profil nicht lesbar)

    def list(self) -> list[str]:
        return sorted(set(self._entries) | set(self._puts.pending_ids()))

    def load(self, pid: str) -> Profile:
        """Frisches Objekt (aenderbar, ohne den Zwischenspeicher zu beruehren)."""
        data = self._puts.pending_json(pid)
        if data is None:
            data = self._cache.get(pid)
        if data is None:
            if pid in self._errors:
                raise OSError(self._errors[pid])
            try:
                data = self._request("profile.get", {"id": pid})
            except ApiError as e:
                raise OSError(str(e)) from None
            if not isinstance(data, dict):
                raise OSError(tr("Profil {id!r}: unerwartete Antwort des Dienstes", id=pid))
            self._cache[pid] = data
        return Profile.from_json(copy.deepcopy(data))

    def name(self, pid: str) -> str:
        """Anzeigename ohne Anfrage (Zwischenspeicher, sonst Profilliste, sonst Kennung)."""
        data = self._puts.pending_json(pid) or self._cache.get(pid) or {}
        return str(data.get("name") or self._entries.get(pid, {}).get("name") or pid)

    def save(self, profile: Profile) -> None:
        """Speichern im Dienst (gebuendelt, ohne zu warten); ohne Verbindung wird es
        nachgereicht."""
        self._puts.put(profile.to_json())

    def delete(self, pid: str) -> None:
        self._puts.drop_puts(pid)  # nicht nachtraeglich wieder anlegen
        try:
            self._request("profile.delete", {"id": pid})
        except ApiError as e:
            raise OSError(str(e)) from None
        for d in (self._entries, self._cache, self._errors):
            d.pop(pid, None)

    # --- fuer die RemoteEngine (Zwischenspeicher pflegen) ------------------------------

    def remember(self, pid: str, data: dict) -> None:
        """Stand ``data`` des Profils, wie der Dienst ihn hat."""
        self._cache[pid] = data
        self._errors.pop(pid, None)
        entry = self._entries.setdefault(pid, {"name": pid, "ok": True})
        entry.update(name=str(data.get("name") or pid), ok=True)

    def forget(self, pid: str) -> None:
        """Gemerkten Stand verwerfen (beim naechsten ``load`` neu fragen)."""
        self._cache.pop(pid, None)
        self._errors.pop(pid, None)

    def set_error(self, pid: str, text: str) -> None:
        """Profil ist im Dienst nicht lesbar; ``load`` meldet ``text`` als ``OSError``."""
        self._errors[pid] = text

    def set_entries(self, entries: dict[str, dict]) -> None:
        """Neue Profilliste ``{id: {"name", "ok"}}``; Gemerktes zu verschwundenen Profilen
        faellt weg."""
        self._entries = entries
        for pid in [p for p in self._cache if p not in entries]:
            self.forget(pid)

    def missing(self) -> list[str]:
        """Profile der Liste, von denen weder Stand noch Fehler bekannt ist."""
        return [pid for pid in self._entries if pid not in self._cache and pid not in self._errors]

    def signature(self) -> tuple:
        """Vergleichswert der Liste (Kennung, Name, lesbar) – aendert er sich, gibt es
        Neues fuer die Profilauswahl."""
        return tuple((pid, self.name(pid), pid in self._errors) for pid in self.list())
