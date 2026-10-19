"""Farbwahl an einer Stelle: Farbfeld-Symbol, Farbdialog und der Knopf, der beides zeigt."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QColorDialog, QPushButton, QWidget

DEFAULT_COLOR = "#ffffff"
SWATCH_PX = 16


def color_icon(color: str) -> QIcon:
    """Kleines Farbfeld als Symbol."""
    pix = QPixmap(SWATCH_PX, SWATCH_PX)
    pix.fill(QColor(color))
    return QIcon(pix)


def pick_color(parent: QWidget | None, current: str | None, title: str) -> str | None:
    """Farbdialog; gewaehlte Farbe als ``#rrggbb`` oder ``None`` (abgebrochen)."""
    color = QColorDialog.getColor(QColor(current or DEFAULT_COLOR), parent, title)
    return color.name() if color.isValid() else None


class ColorButton(QPushButton):
    """Zeigt eine Farbe (Feld + Text); Klick oeffnet den Farbdialog, ``color_chosen(str)``
    meldet die neue Farbe."""

    color_chosen = Signal(str)

    def __init__(self, title: str, color: str = DEFAULT_COLOR, parent=None) -> None:
        super().__init__(parent)
        self._title = title
        self._color = color
        self.set_color(color)
        self.clicked.connect(self.choose)

    def color(self) -> str:
        return self._color

    def set_color(self, color: str) -> None:
        self._color = color
        self.setIcon(color_icon(color))
        self.setText(color)

    def choose(self) -> None:
        color = pick_color(self, self._color, self._title)
        if color is not None:
            self.set_color(color)
            self.color_chosen.emit(color)
