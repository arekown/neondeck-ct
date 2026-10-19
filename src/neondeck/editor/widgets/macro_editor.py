"""Klartext-Modus fuer Makros: Schritte als Text (``actions/macro_text``), zweiwegig.

``hotkey ctrl+c``, ``text …``, ``wait 200``, ``run …``, ``open …``, ``command …``,
``key down/up …`` – je Zeile ein Schritt. Ein Fehler zeigt Zeile und Grund; bis er behoben
ist, bleiben die zuletzt gueltigen Schritte stehen.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from ...actions import macro_text
from ...actions.macro_text import MacroSyntaxError
from ...core.i18n import N_, tr
from .base import EditorWidget, hint_label

HELP = N_("Je Zeile ein Schritt: hotkey ctrl+c · text Hallo · wait 200 · run kate · "
          "open ~/Bilder · command ls · key down shift · key up shift · # Kommentar")


def as_text(steps: list[dict]) -> tuple[str | None, str]:
    """Schritte als Klartext; ``(None, Grund)``, wenn ein Schritt nicht darstellbar ist."""
    try:
        return macro_text.format([s for s in steps if s.get("type")]), ""
    except (ValueError, KeyError) as e:
        return None, tr("Als Text nicht darstellbar: {error}", error=e)


class MacroTextEdit(EditorWidget, QWidget):
    """Textfeld + Fehlerzeile; ``steps_changed(list)`` bei jeder gueltigen Aenderung."""

    steps_changed = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText(tr(HELP))
        self.edit.setMinimumHeight(110)
        self.edit.textChanged.connect(self._changed)
        self.error = QLabel()
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.error.hide()
        help_label = hint_label(tr(HELP))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.edit)
        layout.addWidget(self.error)
        layout.addWidget(help_label)

    def set_text(self, text: str) -> None:
        with self.loading():
            self.edit.setPlainText(text)
        self.error.hide()

    def steps(self) -> list[dict] | None:
        """Geparste Schritte (``None`` bei Fehler; der steht dann in ``error``)."""
        try:
            steps = macro_text.parse(self.edit.toPlainText())
        except MacroSyntaxError as e:
            self.error.setText(tr("Zeile {line}: {message}", line=e.line, message=e.message))
            self.error.show()
            return None
        self.error.hide()
        return steps

    def _changed(self) -> None:
        if self.is_loading:
            return
        steps = self.steps()
        if steps is not None:
            self.steps_changed.emit(steps)
