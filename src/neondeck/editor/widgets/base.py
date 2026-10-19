"""Gemeinsame Grundlage der Bearbeitungs-Widgets und kleine Bauhelfer (Knoepfe, Gruppen,
Hinweise, Auswahllisten, Menueeintraege, Dialoge).

``EditorWidget`` ist ein Mixin vor der Qt-Klasse (``class X(EditorWidget, QTabWidget)``):
``changed`` nach jeder Benutzeraenderung; was das Programm selbst in die Felder schreibt,
steht in ``with self.loading():`` und meldet nichts (verschachtelbar).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class EditorWidget:
    """Mixin: ``changed``-Signal, ``loading()``-Kontext und ``_emit`` (meldet nur ausserhalb
    von ``loading``)."""

    changed = Signal()
    _loading_depth = 0

    @contextmanager
    def loading(self) -> Iterator[None]:
        """Felder setzen, ohne ``changed`` auszuloesen; verschachtelt endet erst der aeusserste
        Block."""
        self._loading_depth += 1
        try:
            yield
        finally:
            self._loading_depth -= 1

    @property
    def is_loading(self) -> bool:
        return self._loading_depth > 0

    def _emit(self, *_) -> None:
        if not self.is_loading:
            self.changed.emit()


# --- Bauhelfer -------------------------------------------------------------------------

def tool_button(icon: str, fallback: str, tip: str, slot) -> QToolButton:
    """Symbolknopf aus dem Systemthema; ohne passendes Symbol mit Text."""
    b = QToolButton()
    themed = QIcon.fromTheme(icon)
    if themed.isNull():
        b.setText(fallback)
    else:
        b.setIcon(themed)
    b.setToolTip(tip)
    b.setAccessibleName(tip)
    b.setAutoRaise(True)
    b.clicked.connect(slot)
    return b


def push_button(icon: str, text: str, slot) -> QPushButton:
    b = QPushButton(QIcon.fromTheme(icon), text)
    b.clicked.connect(slot)
    return b


def group_box(title: str, widget: QWidget) -> QGroupBox:
    box = QGroupBox(title)
    QVBoxLayout(box).addWidget(widget)
    return box


def hint_label(text: str = "") -> QLabel:
    """Umbrechender Hinweistext (Stil ``hint`` aus dem Theme)."""
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


def combo(choices: Iterable[tuple[object, str]]) -> QComboBox:
    """Auswahlfeld aus ``(Wert, Beschriftung)``-Paaren."""
    c = QComboBox()
    for value, label in choices:
        c.addItem(label, value)
    return c


def select_or_add(box: QComboBox, value) -> None:
    """``value`` waehlen; unbekannte Werte (handbearbeitet, neuere Version) als eigenen
    Eintrag zeigen statt sie still auf den ersten Eintrag zu setzen."""
    i = box.findData(value)
    if i < 0:
        box.addItem(str(value), value)
        i = box.count() - 1
    box.setCurrentIndex(i)


def hbox(*widgets) -> QHBoxLayout:
    """Waagerechte Zeile; ``(widget, stretch)`` dehnt ein Element."""
    row = QHBoxLayout()
    for w in widgets:
        widget, stretch = w if isinstance(w, tuple) else (w, 0)
        row.addWidget(widget, stretch)
    return row


def close_buttons(dialog) -> QDialogButtonBox:
    """Knopfleiste „Schließen“ fuer ``dialog``."""
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dialog.reject)
    return buttons


def ok_cancel_buttons(dialog) -> QDialogButtonBox:
    """Knopfleiste „OK“/„Abbrechen“ fuer ``dialog``."""
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    return buttons


def menu_action(menu, icon: str | None, text: str, slot: Callable | None = None) -> QAction:
    """Menueeintrag als selbst erzeugtes QAction.

    ``QMenu.addAction(…)`` holt das neue C++-Objekt ueber die Adresstabelle von PySide
    und kann dort einen veralteten Wrapper (z. B. eines geloeschten QStandardItem)
    treffen; ein in Python erzeugtes QAction bekommt immer einen frischen."""
    action = QAction(QIcon.fromTheme(icon) if icon else QIcon(), text, menu)
    if slot is not None:
        action.triggered.connect(slot)
    menu.addAction(action)
    return action


@contextmanager
def disposing[T](obj: T) -> Iterator[T]:
    """Dialog oder Menue benutzen und danach freigeben (``deleteLater``)."""
    try:
        yield obj
    finally:
        obj.deleteLater()
