"""Einstellungen des Dienstes aendern: Werte uebernehmen, Zuhoerer je Schluessel, speichern.

Ein Weg fuer alle Aenderungen (Tray, API ``settings.put``): ``apply({"brightness": 6})``
setzt die Werte, ruft jeden Zuhoerer, dessen Schluessel betroffen sind, genau einmal (in
der Reihenfolge der Anmeldung) und speichert dann einmal. Zuhoerer wirken die Werte aus
(Geraet, Engine, Tray, Theme, Autostart); kann einer einen Wert nicht anwenden, wirft er
``SettingRejected`` – dann gilt fuer seine Schluessel wieder der alte Wert. Jede andere
Ausnahme wird geloggt; die uebrigen Zuhoerer laufen trotzdem.

Ohne Qt; Gruppen wie „Bildschirmschoner“ (vier Schluessel) sind ein Zuhoerer.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping

from ..core.errors import LoupedeckError
from ..core.guard import call_logged
from ..core.settings import FIELDS, Settings

log = logging.getLogger(__name__)

# ``active_profile`` aendert nur der Profilwechsel (laden, anzeigen, merken)
KEYS = frozenset(FIELDS) - {"active_profile"}


class SettingRejected(LoupedeckError):
    """Ein Zuhoerer konnte den neuen Wert nicht anwenden (der alte bleibt)."""


class SettingsController:
    """``save()`` schreibt die Einstellungen (der Dienst merkt dabei auch die Ansichten)."""

    def __init__(self, settings: Settings, save: Callable[[], None]) -> None:
        self.settings = settings
        self._save = save
        self._listeners: list[tuple[frozenset[str], Callable[[], None]]] = []

    def listen(self, keys: Iterable[str], fn: Callable[[], None]) -> None:
        """``fn()`` nach jeder Aenderung eines der ``keys`` (liest die Werte aus
        ``settings``)."""
        keys = frozenset(keys)
        if not keys <= KEYS:
            raise KeyError(", ".join(sorted(keys - KEYS)))
        self._listeners.append((keys, fn))

    def apply(self, changes: Mapping[str, object]) -> None:
        """Werte setzen, Zuhoerer rufen, einmal speichern; unbekannte Schluessel:
        ``KeyError`` (vor jeder Aenderung). Geprueft (Typ, Bereich) wird vorher."""
        unknown = set(changes) - KEYS
        if unknown:
            raise KeyError(", ".join(sorted(unknown)))
        old = {key: getattr(self.settings, key) for key in changes}
        for key, value in changes.items():
            setattr(self.settings, key, value)
        kept = set(changes)
        for keys, fn in self._listeners:
            if keys & kept:
                kept -= self._run(fn, keys, old)
        if kept:
            self._save()

    def _run(self, fn: Callable[[], None], keys: frozenset[str], old: dict) -> set[str]:
        """Zuhoerer rufen; die Schluessel, die er abgelehnt hat (alter Wert zurueck). Andere
        Fehler werden geloggt (der Wert bleibt, die naechsten Zuhoerer laufen)."""
        rejected = False

        def attempt() -> None:
            nonlocal rejected
            try:
                fn()
            except SettingRejected:
                rejected = True

        call_logged(attempt, what="Einstellung %s nicht angewandt",
                    what_args=(", ".join(sorted(keys)),), logger=log)
        if not rejected:
            return set()
        back = {key for key in keys if key in old}
        for key in back:
            setattr(self.settings, key, old[key])
        return back
