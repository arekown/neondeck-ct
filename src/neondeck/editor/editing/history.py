"""Rückgängig/Wiederholen des Einstellungsfensters, ohne Qt: je Profil ein ``UndoStack``, der
zuletzt gemerkte Stand (Basis) und die Bearbeitungssitzung (neue Auswahl = neuer Schritt).

Ein Schritt geht vom gemerkten Stand zum neuen. Hat jemand anderes das Profil inzwischen
geaendert (Verwaltung, API, CLI), passt der Stapel nicht mehr: ``step`` verwirft ihn und
meldet ``stale``.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ...profile.model import Profile
from .undo import UndoStack


@dataclass(frozen=True)
class Step:
    """Ergebnis von ``ProfileHistory.step``: ausgefuehrter Schritt (``label``) oder ``stale``."""
    label: str | None = None
    stale: bool = False


class ProfileHistory:
    """``changed`` (ohne Argumente) nach jeder Aenderung an Stapel oder Basis."""

    def __init__(self, changed: Callable[[], None] | None = None) -> None:
        self.changed = changed
        self._stacks: dict[str, UndoStack] = {}
        self._base: tuple[str, dict] | None = None  # (Profil-ID, JSON) zuletzt gemerkt
        self.session = 0

    def _notify(self) -> None:
        if self.changed is not None:
            self.changed()

    def new_session(self) -> None:
        """Naechste Eingabe wird ein eigener Schritt (neue Auswahl, Ablegen, Seitenaktion)."""
        self.session += 1

    def stack(self, pid: str) -> UndoStack:
        return self._stacks.setdefault(pid, UndoStack())

    def reset_base(self, profile: Profile) -> None:
        self._base = (profile.id, profile.to_json())

    def follow(self, profile: Profile, *, first: bool, replaced: bool) -> None:
        """Das Fenster zeigt ``profile`` (``first``: erstmals, ``replaced``: anderes Objekt).
        Neu von aussen geladen: die alten Schritte passen nicht mehr."""
        base = self._base
        if not (first or replaced or base is None or base[0] != profile.id):
            return
        if not first and base is not None and base[0] == profile.id:
            self.stack(profile.id).clear()
        self.reset_base(profile)
        self._notify()

    def record(self, profile: Profile, label: str, merge=None) -> None:
        """Schritt fuer Rückgängig: Stand vorher (zuletzt gemerkt) -> jetzt."""
        after = profile.to_json()
        base = self._base
        if base is not None and base[0] == profile.id:
            self.stack(profile.id).push(base[1], after, label, merge=merge)
        self._base = (profile.id, after)
        self._notify()

    def step(self, profile: Profile, *, undo: bool) -> Step | None:
        """Rückgängig (``undo``) bzw. Wiederholen am Objekt ``profile``; ``None``: nichts da."""
        self.new_session()
        stack = self.stack(profile.id)
        expected = stack.undo_expects() if undo else stack.redo_expects()
        if expected is None:
            return None
        if profile.to_json() != expected:  # inzwischen anderswo geaendert
            stack.clear()
            self.reset_base(profile)
            self._notify()
            return Step(stale=True)
        label = stack.undo_label() if undo else stack.redo_label()
        data = stack.undo() if undo else stack.redo()
        if data is None:
            return None
        profile.replace_with(Profile.from_json(data))  # gleiches Objekt
        self.reset_base(profile)
        self._notify()
        return Step(label)
