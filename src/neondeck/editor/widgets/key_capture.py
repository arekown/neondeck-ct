"""Eingabefeld, das eine Tastenkombination aufnimmt (Wert: evdev-Namen, Anzeige deutsch).

Solange das Feld den Fokus hat, sind die globalen KDE-Kuerzel gesperrt (``shortcut_block``);
die Sperre endet mit dem Fokus, beim Verstecken oder Zerstoeren des Felds und beim Beenden
des Editors. Tastennamen: ``key_names``, Ereignis -> Name: ``key_events``.
"""
from __future__ import annotations

from functools import partial

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QLineEdit

from ...core.i18n import tr
from . import shortcut_block
from .key_events import event_key_name, modifier_names
from .key_names import MODIFIER_ORDER, key_display
from .shortcut_block import ShortcutBlock


class KeyCaptureEdit(QLineEdit):
    """Nimmt eine Tastenkombination auf; Wert = evdev-Namen (``KEY_LEFTCTRL+KEY_T``)."""

    changed = Signal()

    def __init__(self, parent=None, *, block: ShortcutBlock | None = None):
        super().__init__(parent)
        self._value = ""
        self._held: set[str] = set()
        self._used = False
        self._updating = False
        self._block = block or shortcut_block.shared()
        self._key = id(self)
        self.destroyed.connect(partial(self._block.release, self._key))
        self.setPlaceholderText(tr("Tastenkombination drücken …"))
        self.setClearButtonEnabled(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setAcceptDrops(False)
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, False)
        self.textChanged.connect(self._on_text)

    def value(self) -> str:
        return self._value

    def set_value(self, combo) -> None:
        if isinstance(combo, (list, tuple)):
            combo = "+".join(combo)
        self._value = combo or ""
        self._show(key_display(self._value))

    def _show(self, text: str) -> None:
        self._updating = True
        try:
            self.setText(text)
        finally:
            self._updating = False

    def _on_text(self, text: str) -> None:
        if not self._updating and not text and self._value:  # Leeren-Knopf im Feld
            self._value = ""
            self.changed.emit()

    def _commit(self, combo: str) -> None:
        self.set_value(combo)
        self.changed.emit()

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ShortcutOverride:
            event.accept()  # keine Programm-Kuerzel, solange hier aufgenommen wird
            return True
        if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Tab,
                                                                   Qt.Key.Key_Backtab):
            self.keyPressEvent(event)  # Tab ist eine Taste, kein Fokuswechsel
            return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:
        event.accept()
        if event.isAutoRepeat():
            return
        name = event_key_name(event)
        if name is None:
            return
        if name in MODIFIER_ORDER:
            if not self._held:
                self._used = False
            self._held.add(name)
            self._show(key_display("+".join(modifier_names(self._held, event.modifiers())))
                       + "+…")
            return
        self._commit("+".join(modifier_names(self._held, event.modifiers()) + [name]))
        self._used = True

    def keyReleaseEvent(self, event) -> None:
        event.accept()
        if event.isAutoRepeat():
            return
        name = event_key_name(event)
        if name not in MODIFIER_ORDER:
            return
        if not self._used and self._held:  # nur Zusatztasten, z. B. Super allein
            self._commit("+".join(n for n in MODIFIER_ORDER if n in self._held))
            self._used = True
        self._held.discard(name)

    def focusInEvent(self, event) -> None:
        self._block.hold(self._key)
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self._block.release(self._key)
        self._held.clear()
        self._show(key_display(self._value))
        super().focusOutEvent(event)

    def hideEvent(self, event) -> None:
        self._block.release(self._key)
        super().hideEvent(event)
