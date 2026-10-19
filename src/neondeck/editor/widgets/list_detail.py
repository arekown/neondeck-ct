"""Liste + Detail: Eintraege links (wahlweise mit Hinzufügen/Entfernen/Hoch/Runter), der
gewaehlte Eintrag wird daneben bzw. darunter bearbeitet (Makro-Schritte, Ebenen, Zustände).

Unterklassen liefern ``item_label``, ``show_item`` (Eintrag ins Detail), ``read_item``
(Detail -> Eintrag) und, mit Knoepfen, ``new_item``; das Layout bauen sie selbst aus
``list``, ``buttons`` und ihrem Detail-Widget.
"""
from __future__ import annotations

import copy
from typing import Any

from PySide6.QtWidgets import QListWidget, QVBoxLayout, QWidget

from ...core.i18n import tr
from .base import EditorWidget, tool_button


class ListDetailEditor(EditorWidget, QWidget):
    """``noun`` steht in den Knopf-Tipps („Schritt hinzufügen“); ohne ``noun`` keine Knoepfe."""

    def __init__(self, noun: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self._items: list[Any] = []
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._row_changed)
        self.buttons = QVBoxLayout()
        self.add_button = self.remove_button = self.up_button = self.down_button = None
        if noun is not None:
            self.add_button = tool_button("list-add", "+", tr("{noun} hinzufügen", noun=noun), self._add)
            self.remove_button = tool_button("list-remove", "−", tr("{noun} entfernen", noun=noun),
                                             self._remove)
            self.up_button = tool_button("go-up", "↑", tr("Nach oben"), lambda: self._move(-1))
            self.down_button = tool_button("go-down", "↓", tr("Nach unten"), lambda: self._move(1))
            for b in (self.add_button, self.remove_button, self.up_button, self.down_button):
                self.buttons.addWidget(b)
        self.buttons.addStretch(1)

    # --- von Unterklassen -------------------------------------------------------------

    def new_item(self) -> Any:
        raise NotImplementedError

    def item_label(self, row: int, item) -> str:
        raise NotImplementedError

    def show_item(self, item, valid: bool) -> None:
        """Eintrag (``valid`` False: keiner gewaehlt, ``item`` ist ``None``) ins Detail."""
        raise NotImplementedError

    def read_item(self, item) -> Any:
        """Neuer Stand des gewaehlten Eintrags aus dem Detail."""
        raise NotImplementedError

    # --- Eintraege -----------------------------------------------------------------------

    def items(self) -> list:
        return copy.deepcopy(self._items)

    def set_items(self, items) -> None:
        self._items = copy.deepcopy(list(items))
        self.rebuild(0 if self._items else -1)

    def current_row(self) -> int:
        """Gewaehlte Zeile, ``-1`` ohne gueltige Auswahl."""
        row = self.list.currentRow()
        return row if 0 <= row < len(self._items) else -1

    def rebuild(self, row: int) -> None:
        """Liste neu beschriften, Zeile ``row`` waehlen und ins Detail laden."""
        with self.loading():
            self.list.clear()
            for i, item in enumerate(self._items):
                self.list.addItem(self.item_label(i, item))
            self.list.setCurrentRow(row)
        self._show_row(self.list.currentRow())

    def _row_changed(self, row: int) -> None:
        if not self.is_loading:
            self._show_row(row)

    def _show_row(self, row: int) -> None:
        valid = 0 <= row < len(self._items)
        with self.loading():
            self.show_item(self._items[row] if valid else None, valid)
        self._update_buttons()

    def _update_buttons(self) -> None:
        if self.remove_button is None:
            return
        row = self.current_row()
        self.remove_button.setEnabled(row >= 0)
        self.up_button.setEnabled(row > 0)
        self.down_button.setEnabled(0 <= row < len(self._items) - 1)

    def item_edited(self, *_) -> None:
        """Detail geaendert: Eintrag uebernehmen, Beschriftung nachziehen, melden."""
        row = self.current_row()
        if self.is_loading or row < 0:
            return
        self._items[row] = self.read_item(self._items[row])
        self.list.item(row).setText(self.item_label(row, self._items[row]))
        self.changed.emit()

    def _add(self) -> None:
        self._items.append(self.new_item())
        self.rebuild(len(self._items) - 1)
        self.changed.emit()

    def _remove(self) -> None:
        row = self.current_row()
        if row >= 0:
            del self._items[row]
            self.rebuild(min(row, len(self._items) - 1))
            self.changed.emit()

    def _move(self, delta: int) -> None:
        row = self.current_row()
        new = row + delta
        if row >= 0 and 0 <= new < len(self._items):
            self._items[row], self._items[new] = self._items[new], self._items[row]
            self.rebuild(new)
            self.changed.emit()
