"""Belegung des gewaehlten Elements bearbeiten (Inspector unter der Geraeteansicht).

Je nach Element ein eigener Inspector: Tasten (``inspector_button``: Tippen + Bild,
Doppeltippen/Halten, Zustände), Regler und Rad (``inspector_knob``); er steht in ``content``.
"""
from __future__ import annotations

import copy
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...core.i18n import N_, tr
from ...device.layout import ControlKind, ControlRef
from ...profile.edit import empty_value
from .base import hint_label
from .inspector_button import ButtonInspector
from .inspector_knob import KnobInspector, WheelInspector
from .labels import ref_name
from .nav_targets import NavTargets

Inspector = ButtonInspector | KnobInspector | WheelInspector

HINT = N_("Ein Element am Gerät anklicken, um es zu belegen (Strg-Klick: mehrere).\n"
          "Aktionen aus der Liste rechts aufs Gerät ziehen; Elemente untereinander ziehen "
          "verschiebt sie (mit Strg: kopieren).")
TITLE_SCALE = 1.2


class AssignmentEditor(QWidget):
    """Formular fuer das gewaehlte Element: Titel, Inspector, „Testen“ und „Leeren“.

    Werte: Touch/rund/eckig -> ``Assignment | None``, Regler -> ``Encoder``, Rad -> ``Wheel``.
    ``changed(value)`` nach jeder Aenderung, ``test_requested`` beim Knopf „Testen“.
    """

    changed = Signal(object)
    test_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ref: ControlRef | None = None
        self._value: Any = None
        self._targets: NavTargets | None = None
        self._content: Inspector | None = None

        self.title = QLabel()
        self.title.setObjectName("heading")  # Cockpit/Neutral: Schrift kommt aus dem QSS
        font = QFont(self.title.font())  # Theme „System“ (ohne QSS): fett, etwas groesser
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * TITLE_SCALE)
        self.title.setFont(font)
        self.hint = hint_label(tr(HINT))
        self.test_button = QPushButton(QIcon.fromTheme("media-playback-start"), tr("Testen"))
        self.test_button.setToolTip(tr("Aktion jetzt einmal ausführen"))
        self.test_button.clicked.connect(self.test_requested)
        self.clear_button = QPushButton(QIcon.fromTheme("edit-clear"), tr("Leeren"))
        self.clear_button.setToolTip(tr("Belegung entfernen"))
        self.clear_button.clicked.connect(self._clear)
        top = QHBoxLayout()
        top.addWidget(self.title, 1)
        top.addWidget(self.test_button)
        top.addWidget(self.clear_button)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addLayout(top)
        self._layout.addWidget(self.hint)
        self._content_index = self._layout.count()
        self._layout.addStretch(1)
        self.set_target(None, None)

    # --- Ziel ------------------------------------------------------------------------

    @property
    def ref(self) -> ControlRef | None:
        return self._ref

    @property
    def content(self) -> Inspector | None:
        """Inspector des gezeigten Elements (``None``: nichts gewaehlt oder gesperrt)."""
        return self._content

    def set_nav_targets(self, targets: NavTargets | None) -> None:
        """Ziele fuer Arbeitsbereich-/Profil-/Ordneraktionen und die Listen des Dienstes (gilt
        ab dem naechsten ``set_target``)."""
        self._targets = targets

    def set_target(self, ref: ControlRef | None, value, *, locked: str | None = None,
                   note: str | None = None) -> None:
        """Element anzeigen (``value`` wird kopiert, nie direkt veraendert). ``locked``: Element
        nicht belegbar, statt des Inspectors steht dieser Text da; ``note`` steht darueber."""
        tab = self._content.currentIndex() if self._content is not None else 0
        same_kind = self._ref is not None and ref is not None and self._ref.kind == ref.kind
        self._ref = None if locked else ref
        self._value = copy.deepcopy(value)
        if self._content is not None:
            self._layout.removeWidget(self._content)
            self._content.hide()
            self._content.deleteLater()
            self._content = None
        self.title.setText(ref_name(ref) if ref else tr("Belegung"))
        text = locked or note
        self.hint.setText(text or tr(HINT))
        self.hint.setVisible(ref is None or text is not None)
        self.test_button.setVisible(self._ref is not None)
        self.clear_button.setVisible(self._ref is not None)
        if self._ref is None:
            return
        content = self._inspector(ref)
        content.changed.connect(self._emit)
        if same_kind and 0 <= tab < content.count():
            content.setCurrentIndex(tab)  # gleicher Reiter beim Weiterklicken
        self._content = content
        self._layout.insertWidget(self._content_index, content, 1)

    def _inspector(self, ref: ControlRef) -> Inspector:
        if ref.kind == ControlKind.KNOB:
            return KnobInspector(self._value or empty_value(ControlKind.KNOB), self._targets)
        if ref.kind == ControlKind.WHEEL:
            return WheelInspector(self._value or empty_value(ControlKind.WHEEL), self._targets)
        return ButtonInspector(ref.kind == ControlKind.TOUCH, self._value, self._targets)

    # --- Werte ----------------------------------------------------------------------------

    def value(self):
        return self._content.value() if self._content is not None else None

    def test_action(self) -> tuple[dict | None, int]:
        """Was „Testen“ ausfuehrt: Druckaktion, bei Regler ohne Druck/Rad ein Drehschritt."""
        ref = self._ref
        if ref is None or self._content is None:
            return None, 0
        if ref.kind in (ControlKind.KNOB, ControlKind.WHEEL):
            v = self._content.value()
            press = v.press if ref.kind == ControlKind.KNOB else v.tap
            if press:
                return press, 0
            if v.rotate:
                return v.rotate, 1
            return (v.right or v.left), 0
        return self._content.action_form.value(), 0

    def _emit(self, *_) -> None:
        self.changed.emit(self.value())

    def _clear(self) -> None:
        ref = self._ref
        if ref is None:
            return
        empty = empty_value(ref.kind)
        self.set_target(ref, empty)
        self.changed.emit(copy.deepcopy(empty))
