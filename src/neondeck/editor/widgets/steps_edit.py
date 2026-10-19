"""Makro-Schritte: Liste mit Hinzufügen/Entfernen/Hoch/Runter, der gewaehlte Schritt darunter
in einem eigenen Aktionsformular. „Als Klartext“ zeigt dieselben Schritte als Text
(``macro_editor``); Aenderungen dort gehen zurueck in die Liste."""
from __future__ import annotations

import copy
from collections.abc import Callable

from PySide6.QtWidgets import QCheckBox, QGroupBox, QHBoxLayout, QVBoxLayout, QWidget

from ...core.i18n import tr
from .action_meta import action_summary
from .base import hint_label
from .list_detail import ListDetailEditor
from .macro_editor import MacroTextEdit, as_text

STEPS_MIN_HEIGHT = 90


class StepsEdit(ListDetailEditor):
    """``nested_form()`` baut das Formular fuer einen Schritt (ein ``ActionForm`` fuer
    Druckaktionen); ``value`` sind die Schritte mit Typ."""

    def __init__(self, nested_form: Callable[[], QWidget], parent=None):
        super().__init__(tr("Schritt"), parent)
        self.list.setMinimumHeight(STEPS_MIN_HEIGHT)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.list, 1)
        top.addLayout(self.buttons)
        self.step_form = nested_form()
        self.step_form.changed.connect(self.item_edited)
        self.step_box = QGroupBox(tr("Schritt"))
        QVBoxLayout(self.step_box).addWidget(self.step_form)
        self.text_mode = QCheckBox(tr("Als Klartext bearbeiten"))
        self.text_mode.toggled.connect(self._mode_toggled)
        self.mode_note = hint_label()
        self.mode_note.hide()
        self.text_edit = MacroTextEdit()
        self.text_edit.steps_changed.connect(self._text_steps)
        self.text_edit.hide()
        self._list_host = QWidget()
        host = QVBoxLayout(self._list_host)
        host.setContentsMargins(0, 0, 0, 0)
        host.addLayout(top)
        host.addWidget(self.step_box)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.text_mode)
        layout.addWidget(self.mode_note)
        layout.addWidget(self._list_host)
        layout.addWidget(self.text_edit)
        self._update_buttons()

    # --- ListDetailEditor ----------------------------------------------------------------

    def new_item(self) -> dict:
        return {}

    def item_label(self, row: int, item: dict) -> str:
        return f"{row + 1}. {action_summary(item)}"

    def show_item(self, item: dict | None, valid: bool) -> None:
        self.step_form.set_value(item)
        self.step_box.setEnabled(valid)

    def read_item(self, item: dict) -> dict:
        return self.step_form.value() or {}

    # --- Wert ----------------------------------------------------------------------------

    def value(self) -> list[dict]:
        return [s for s in self.items() if s.get("type")]

    def set_value(self, steps) -> None:
        self.set_items(s for s in (steps or []) if isinstance(s, dict))
        if self.text_mode.isChecked():
            text, _ = as_text(self._items)
            if text is None:
                self.text_mode.setChecked(False)
            else:
                self.text_edit.set_text(text)

    # --- Klartext ----------------------------------------------------------------------

    def _mode_toggled(self, on: bool) -> None:
        if on:
            text, why = as_text(self._items)
            if text is None:
                self.mode_note.setText(why)
                self.mode_note.show()
                self.text_mode.blockSignals(True)
                self.text_mode.setChecked(False)
                self.text_mode.blockSignals(False)
                return
            self.text_edit.set_text(text)
        self.mode_note.hide()
        self._list_host.setVisible(not on)
        self.text_edit.setVisible(on)

    def _text_steps(self, steps: list) -> None:
        self._items = [copy.deepcopy(s) for s in steps]
        self.rebuild(0 if self._items else -1)
        self.changed.emit()
