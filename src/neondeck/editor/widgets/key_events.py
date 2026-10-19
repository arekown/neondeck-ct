"""Qt-Tastenereignis -> evdev-Name (``KEY_…``) der gedrueckten Taste und der Zusatztasten."""
from __future__ import annotations

from evdev import ecodes
from PySide6.QtCore import Qt

from ...core.keymap import CHAR_MAP, LETTER_KEY
from .key_names import MODIFIER_ORDER

_QT_MODIFIER_KEYS = {int(k): v for k, v in {
    Qt.Key.Key_Control: "KEY_LEFTCTRL", Qt.Key.Key_Shift: "KEY_LEFTSHIFT",
    Qt.Key.Key_Alt: "KEY_LEFTALT", Qt.Key.Key_AltGr: "KEY_RIGHTALT",
    Qt.Key.Key_Meta: "KEY_LEFTMETA", Qt.Key.Key_Super_L: "KEY_LEFTMETA",
    Qt.Key.Key_Super_R: "KEY_RIGHTMETA",
}.items()}
_MODIFIER_FLAGS = [
    (Qt.KeyboardModifier.ControlModifier, ("KEY_LEFTCTRL", "KEY_RIGHTCTRL")),
    (Qt.KeyboardModifier.ShiftModifier, ("KEY_LEFTSHIFT", "KEY_RIGHTSHIFT")),
    (Qt.KeyboardModifier.AltModifier, ("KEY_LEFTALT",)),
    (Qt.KeyboardModifier.MetaModifier, ("KEY_LEFTMETA", "KEY_RIGHTMETA")),
]


def _qt_key_table() -> dict[int, str]:
    k = Qt.Key
    table = {
        k.Key_Return: "KEY_ENTER", k.Key_Enter: "KEY_KPENTER", k.Key_Space: "KEY_SPACE",
        k.Key_Tab: "KEY_TAB", k.Key_Backtab: "KEY_TAB", k.Key_Escape: "KEY_ESC",
        k.Key_Backspace: "KEY_BACKSPACE", k.Key_Delete: "KEY_DELETE",
        k.Key_Insert: "KEY_INSERT", k.Key_Home: "KEY_HOME", k.Key_End: "KEY_END",
        k.Key_PageUp: "KEY_PAGEUP", k.Key_PageDown: "KEY_PAGEDOWN", k.Key_Up: "KEY_UP",
        k.Key_Down: "KEY_DOWN", k.Key_Left: "KEY_LEFT", k.Key_Right: "KEY_RIGHT",
        k.Key_Print: "KEY_SYSRQ", k.Key_Pause: "KEY_PAUSE", k.Key_CapsLock: "KEY_CAPSLOCK",
        k.Key_ScrollLock: "KEY_SCROLLLOCK", k.Key_NumLock: "KEY_NUMLOCK",
        k.Key_Menu: "KEY_COMPOSE", k.Key_MediaPlay: "KEY_PLAYPAUSE",
        k.Key_MediaTogglePlayPause: "KEY_PLAYPAUSE", k.Key_MediaNext: "KEY_NEXTSONG",
        k.Key_MediaPrevious: "KEY_PREVIOUSSONG", k.Key_MediaStop: "KEY_STOPCD",
        k.Key_VolumeUp: "KEY_VOLUMEUP", k.Key_VolumeDown: "KEY_VOLUMEDOWN",
        k.Key_VolumeMute: "KEY_MUTE",
        # deutsches Layout: Zeichen -> Tastenposition
        k.Key_Adiaeresis: "KEY_APOSTROPHE", k.Key_Odiaeresis: "KEY_SEMICOLON",
        k.Key_Udiaeresis: "KEY_LEFTBRACE", k.Key_ssharp: "KEY_MINUS", k.Key_Plus: "KEY_RIGHTBRACE",
        k.Key_NumberSign: "KEY_BACKSLASH", k.Key_Comma: "KEY_COMMA", k.Key_Period: "KEY_DOT",
        k.Key_Minus: "KEY_SLASH", k.Key_Less: "KEY_102ND", k.Key_AsciiCircum: "KEY_GRAVE",
        k.Key_Dead_Circumflex: "KEY_GRAVE", k.Key_Dead_Acute: "KEY_EQUAL",
    }
    for c, name in LETTER_KEY.items():  # Y/Z vertauscht wie auf der deutschen Tastatur
        table[k.Key_A + ord(c) - ord("a")] = name
    for d in range(10):
        table[k.Key_0 + d] = f"KEY_{d}"
    for n in range(1, 25):
        table[k.Key_F1 + n - 1] = f"KEY_F{n}"
    return {int(key): name for key, name in table.items()}


_QT_KEYS = _qt_key_table()


def scancode_key_name(scancode: int) -> str | None:
    """Linux (Wayland und X11): ``nativeScanCode`` ist der xkb-Keycode = evdev-Code + 8."""
    if scancode <= 8:
        return None
    names = ecodes.KEY.get(scancode - 8)
    if names is None:
        return None
    names = [names] if isinstance(names, str) else list(names)
    names = [n for n in names if n.startswith("KEY_") and n != "KEY_MIN_INTERESTING"]
    return names[0] if names else None


def event_key_name(event) -> str | None:
    """evdev-Name der Taste eines ``QKeyEvent``.

    Bevorzugt die Tastenposition aus dem Scancode (layoutunabhaengig, genau das, was die
    virtuelle Tastatur spaeter sendet). Ohne Scancode (z. B. synthetische Ereignisse):
    Tabelle ``Qt.Key`` -> evdev fuer das deutsche Layout, zuletzt das Zeichen ueber ``CHAR_MAP``.
    """
    name = scancode_key_name(event.nativeScanCode())
    if name:
        return name
    key = int(event.key())
    if key in _QT_MODIFIER_KEYS:
        return _QT_MODIFIER_KEYS[key]
    if key in _QT_KEYS:
        return _QT_KEYS[key]
    text = event.text()
    if len(text) == 1 and text in CHAR_MAP:
        return CHAR_MAP[text][0]
    return None


def modifier_names(held: set[str], modifiers) -> list[str]:
    """Gehaltene Zusatztasten plus die, die nur die Ereignis-Flags melden, in fester
    Reihenfolge (Strg, Umschalt, Alt, Super)."""
    names = set(held)
    for flag, group in _MODIFIER_FLAGS:
        if modifiers & flag and not names.intersection(group):
            names.add(group[0])
    return [n for n in MODIFIER_ORDER if n in names]
