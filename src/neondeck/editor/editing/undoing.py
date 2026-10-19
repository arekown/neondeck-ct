"""Rückgängig/Wiederholen im Menue „Bearbeiten“: zwei Menueeintraege mit dem Namen des
naechsten Schritts, ausgefuehrt ueber ``ProfileHistory``."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QKeySequence

from ...core.i18n import N_, tr
from ..widgets.base import menu_action
from .commit import CommitScheduler
from .history import ProfileHistory

if TYPE_CHECKING:
    from .host import EditView

STALE_UNDO = N_("Rückgängig nicht möglich: das Profil wurde inzwischen anderswo geändert – "
                "ab hier wird neu mitgeschrieben")


class UndoController:
    def __init__(self, view: EditView, history: ProfileHistory,
                 commits: CommitScheduler) -> None:
        self._view = view
        self._history = history
        self._commits = commits
        self.undo_action = None
        self.redo_action = None
        history.changed = self.update_actions

    def add_actions(self, menu) -> None:
        self.undo_action = menu_action(menu, "edit-undo", tr("&Rückgängig"), self.undo)
        self.undo_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Undo))
        self.redo_action = menu_action(menu, "edit-redo", tr("&Wiederholen"), self.redo)
        self.redo_action.setShortcuts([QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")])
        self.update_actions()

    def stack(self):
        """Stapel des Profils, das die Engine zeigt."""
        return self._history.stack(self._view.engine.profile.id)

    def undo(self) -> None:
        self._step(undo=True)

    def redo(self) -> None:
        self._step(undo=False)

    def _step(self, *, undo: bool) -> None:
        self._commits.flush()
        profile = self._view.engine.profile
        step = self._history.step(profile, undo=undo)
        if step is None:
            return
        if step.stale:
            self._view.say(tr(STALE_UNDO))
            return
        self._commits.schedule(profile, record=False)
        self._commits.flush()
        self._view.sync_from_engine(force=True)
        text = (tr("Rückgängig: {step}", step=step.label) if undo
                else tr("Wiederholt: {step}", step=step.label))
        self._view.say(text)
        self.update_actions()

    def update_actions(self) -> None:
        if self.undo_action is None:
            return
        stack = self.stack()
        self.undo_action.setEnabled(stack.can_undo())
        self.redo_action.setEnabled(stack.can_redo())
        self.undo_action.setText(
            tr("&Rückgängig: {step}", step=stack.undo_label()) if stack.can_undo()
            else tr("&Rückgängig"))
        self.redo_action.setText(
            tr("&Wiederholen: {step}", step=stack.redo_label()) if stack.can_redo()
            else tr("&Wiederholen"))
