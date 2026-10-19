"""Rückgängig/Wiederholen im Editor: Schnappschüsse des Profil-JSON (ohne Qt).

Jeder Schritt merkt sich das ganze Profil davor und danach. Das ist bei Profilen dieser
Groesse billig und immer richtig, egal welche Bearbeitung es war (Belegung, Seite,
Arbeitsbereich, Einfuegen …). Aufeinanderfolgende Schritte mit gleichem ``merge``-Schluessel
(z. B. Tippen im selben Textfeld derselben Taste) werden zu einem zusammengefasst.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

MAX_STEPS = 100


@dataclass
class _Step:
    before: dict
    after: dict
    label: str
    merge: object | None = None


class UndoStack:
    def __init__(self, max: int = MAX_STEPS) -> None:
        self.max = max
        self._done: list[_Step] = []
        self._undone: list[_Step] = []

    def push(self, profile_json_before: dict, profile_json_after: dict, label: str, *,
             merge: object | None = None) -> None:
        """Neuer Schritt; ``Wiederholen`` verfaellt. Gleicher ``merge`` wie der letzte
        Schritt: dessen „danach“ wird ersetzt (ein Schritt fuer eine Eingabe)."""
        if profile_json_before == profile_json_after:
            return
        self._undone.clear()
        top = self._done[-1] if self._done else None
        if merge is not None and top is not None and top.merge == merge:
            top.after = copy.deepcopy(profile_json_after)
            return
        self._done.append(_Step(copy.deepcopy(profile_json_before),
                                copy.deepcopy(profile_json_after), label, merge))
        del self._done[:-self.max]

    def clear(self) -> None:
        self._done.clear()
        self._undone.clear()

    def can_undo(self) -> bool:
        return bool(self._done)

    def can_redo(self) -> bool:
        return bool(self._undone)

    def undo_expects(self) -> dict | None:
        """Stand, auf dem das naechste Rückgängig aufsetzt (``danach`` des letzten Schritts)."""
        return self._done[-1].after if self._done else None

    def redo_expects(self) -> dict | None:
        """Stand, auf dem das naechste Wiederholen aufsetzt (``davor`` des Schritts)."""
        return self._undone[-1].before if self._undone else None

    def undo_label(self) -> str:
        return self._done[-1].label if self._done else ""

    def redo_label(self) -> str:
        return self._undone[-1].label if self._undone else ""

    def undo(self) -> dict | None:
        """Profil-JSON vor dem letzten Schritt (``None``: nichts rueckgaengig zu machen)."""
        if not self._done:
            return None
        step = self._done.pop()
        step.merge = None  # nach Rueckgaengig nie mehr mit neuen Eingaben verschmelzen
        self._undone.append(step)
        return copy.deepcopy(step.before)

    def redo(self) -> dict | None:
        if not self._undone:
            return None
        step = self._undone.pop()
        self._done.append(step)
        return copy.deepcopy(step.after)

    def __len__(self) -> int:
        return len(self._done)
