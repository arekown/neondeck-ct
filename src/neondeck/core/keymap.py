"""German keyboard layout (xkb ``de``): character -> (evdev key name, shift, altgr).

evdev key codes name key *positions* (US labels); the compositor's layout turns
them into characters. On a German keyboard Y and Z are swapped, so ``"y"`` is
typed with ``KEY_Z``.
"""
from __future__ import annotations

import string

CHAR_MAP: dict[str, tuple[str, bool, bool]] = {}


def _put(chars: str, keys: list[str], *, shift: bool = False, altgr: bool = False) -> None:
    for ch, key in zip(chars, keys, strict=True):
        CHAR_MAP[ch] = (key, shift, altgr)


_LETTERS = [f"KEY_{c.upper()}" for c in string.ascii_lowercase]
_LETTERS[string.ascii_lowercase.index("y")] = "KEY_Z"
_LETTERS[string.ascii_lowercase.index("z")] = "KEY_Y"
_DIGITS = [f"KEY_{d}" for d in "1234567890"]

_put(string.ascii_lowercase, _LETTERS)
_put(string.ascii_uppercase, _LETTERS, shift=True)
_put("1234567890", _DIGITS)
_put('!"§$%&/()=', _DIGITS, shift=True)
_put(" \n\t", ["KEY_SPACE", "KEY_ENTER", "KEY_TAB"])
_put("äöü", ["KEY_APOSTROPHE", "KEY_SEMICOLON", "KEY_LEFTBRACE"])
_put("ÄÖÜ", ["KEY_APOSTROPHE", "KEY_SEMICOLON", "KEY_LEFTBRACE"], shift=True)
_put("ß", ["KEY_MINUS"])
_put("?", ["KEY_MINUS"], shift=True)
_put(".,-", ["KEY_DOT", "KEY_COMMA", "KEY_SLASH"])
_put(":;_", ["KEY_DOT", "KEY_COMMA", "KEY_SLASH"], shift=True)
_put("+#", ["KEY_RIGHTBRACE", "KEY_BACKSLASH"])
_put("*'", ["KEY_RIGHTBRACE", "KEY_BACKSLASH"], shift=True)
_put("<", ["KEY_102ND"])
_put(">", ["KEY_102ND"], shift=True)
_put("|", ["KEY_102ND"], altgr=True)
_put("@€", ["KEY_Q", "KEY_E"], altgr=True)
_put("{[]}", ["KEY_7", "KEY_8", "KEY_9", "KEY_0"], altgr=True)
_put("\\~", ["KEY_MINUS", "KEY_RIGHTBRACE"], altgr=True)
_put("^", ["KEY_GRAVE"])
_put("°", ["KEY_GRAVE"], shift=True)

# Dead keys: they only combine with the next key, a following space yields the character.
DEAD_KEYS = frozenset("^")

# Letter a-z -> evdev key name (Windows virtual key codes mean the letter, evdev the position).
LETTER_KEY: dict[str, str] = {c: CHAR_MAP[c][0] for c in string.ascii_lowercase}

# Tastennamen (klein geschrieben) -> evdev: eine Tabelle fuer die Vorlagen (deutsch/englisch,
# ``Strg+Umschalt+Z``) und den Windows-Import (``ControlOrCommand+ArrowLeft``).
MODIFIER_KEYS: dict[str, str] = {
    "strg": "KEY_LEFTCTRL", "ctrl": "KEY_LEFTCTRL", "cmd": "KEY_LEFTCTRL",
    "control": "KEY_LEFTCTRL", "controlorcommand": "KEY_LEFTCTRL",
    "umschalt": "KEY_LEFTSHIFT", "shift": "KEY_LEFTSHIFT", "alt": "KEY_LEFTALT",
    "altgr": "KEY_RIGHTALT", "meta": "KEY_LEFTMETA", "super": "KEY_LEFTMETA",
    "windows": "KEY_LEFTMETA",
}
NAMED_KEYS: dict[str, str] = {
    "esc": "KEY_ESC", "escape": "KEY_ESC", "enter": "KEY_ENTER", "return": "KEY_ENTER",
    "tab": "KEY_TAB", "space": "KEY_SPACE", "leertaste": "KEY_SPACE",
    "backspace": "KEY_BACKSPACE", "entf": "KEY_DELETE", "delete": "KEY_DELETE",
    "del": "KEY_DELETE", "einfg": "KEY_INSERT", "insert": "KEY_INSERT", "pos1": "KEY_HOME",
    "home": "KEY_HOME", "ende": "KEY_END", "end": "KEY_END", "bildauf": "KEY_PAGEUP",
    "pageup": "KEY_PAGEUP", "bildab": "KEY_PAGEDOWN", "pagedown": "KEY_PAGEDOWN",
    "links": "KEY_LEFT", "left": "KEY_LEFT", "arrowleft": "KEY_LEFT",
    "rechts": "KEY_RIGHT", "right": "KEY_RIGHT", "arrowright": "KEY_RIGHT",
    "hoch": "KEY_UP", "up": "KEY_UP", "arrowup": "KEY_UP",
    "runter": "KEY_DOWN", "down": "KEY_DOWN", "arrowdown": "KEY_DOWN",
    "druck": "KEY_SYSRQ", "print": "KEY_SYSRQ", "kp+": "KEY_KPPLUS", "kp-": "KEY_KPMINUS",
    "kp*": "KEY_KPASTERISK", "kp/": "KEY_KPSLASH", "kpenter": "KEY_KPENTER",
    "kp.": "KEY_KPDOT", **{f"kp{d}": f"KEY_KP{d}" for d in range(10)},
    **{f"f{n}": f"KEY_F{n}" for n in range(1, 25)},
}
