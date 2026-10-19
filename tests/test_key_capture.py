"""Tastenaufnahme: Qt-Tastenereignis -> evdev-Namen, deutsche Anzeige, KDE-Kürzelsperre."""
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFocusEvent, QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from neondeck.editor.widgets import shortcut_block
from neondeck.editor.widgets.key_capture import KeyCaptureEdit
from neondeck.editor.widgets.key_names import key_display
from neondeck.editor.widgets.shortcut_block import ShortcutBlock


def test_keycapture_names():
    edit = KeyCaptureEdit()
    QTest.keyClick(edit, Qt.Key.Key_T,
                   Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert edit.value() == "KEY_LEFTCTRL+KEY_LEFTSHIFT+KEY_T"
    assert edit.text() == "Strg+Umschalt+T"


def test_keycapture_prefers_scancode_position():
    """Linux (Wayland/X11): nativeScanCode - 8 = evdev-Code; deutsches Z liegt auf KEY_Y."""
    edit = KeyCaptureEdit()
    QApplication.sendEvent(edit, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Z,
                                           Qt.KeyboardModifier.NoModifier, 21 + 8, 0, 0, "z"))
    assert edit.value() == "KEY_Y" and edit.text() == "Z"


def test_keycapture_german_fallback_and_specials():
    edit = KeyCaptureEdit()
    QTest.keyClick(edit, Qt.Key.Key_Z, Qt.KeyboardModifier.AltModifier)
    assert edit.value() == "KEY_LEFTALT+KEY_Y" and edit.text() == "Alt+Z"
    QTest.keyClick(edit, Qt.Key.Key_Return, Qt.KeyboardModifier.MetaModifier)
    assert edit.value() == "KEY_LEFTMETA+KEY_ENTER" and edit.text() == "Super+Eingabe"
    QTest.keyClick(edit, Qt.Key.Key_Tab)  # Tab wechselt nicht den Fokus, sondern wird Taste
    assert edit.value() == "KEY_TAB"


def test_keycapture_modifier_alone():
    edit = KeyCaptureEdit()
    QTest.keyClick(edit, Qt.Key.Key_Meta)
    assert edit.value() == "KEY_LEFTMETA" and edit.text() == "Super"


def test_keycapture_set_value_and_clear():
    edit = KeyCaptureEdit()
    edit.set_value("KEY_LEFTCTRL+KEY_RIGHTALT+KEY_UP")
    assert edit.text() == "Strg+AltGr+Pfeil hoch"
    changed = []
    edit.changed.connect(lambda: changed.append(edit.value()))
    edit.clear()
    assert edit.value() == "" and changed == [""]


def test_key_display_names():
    assert key_display("KEY_LEFTCTRL+KEY_SPACE") == "Strg+Leertaste"
    assert key_display("KEY_SEMICOLON") == "Ö"
    assert key_display("KEY_F5") == "F5"


def test_key_capture_blocks_global_shortcuts_while_focused(_no_real_shortcut_block):
    """Alt+F4 & Co. duerfen beim Aufnehmen nicht ausgeloest werden: KDE-Kuerzel gesperrt,
    solange das Feld den Fokus hat; zwei Felder nacheinander geben genau einmal frei."""
    calls = _no_real_shortcut_block
    a, b = KeyCaptureEdit(), KeyCaptureEdit()
    try:
        a.focusInEvent(QFocusEvent(QEvent.Type.FocusIn))
        b.focusInEvent(QFocusEvent(QEvent.Type.FocusIn))
        assert calls == [True]
        a.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))
        assert calls == [True]
        b.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))
        assert calls == [True, False]
        shortcut_block.shared().hold(1)
        shortcut_block.shared().release_all()  # Programmende
        assert calls == [True, False, True, False]
    finally:
        a.deleteLater()
        b.deleteLater()
    broken = ShortcutBlock(lambda on: (_ for _ in ()).throw(RuntimeError("kein Bus")))
    broken.hold(1)  # ohne KDE: kein Fehler nach aussen
    broken.release(1)
