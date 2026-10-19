"""Windows-Tastennamen -> evdev-Tastenkombination."""
from __future__ import annotations

import re

from ....core.keymap import LETTER_KEY, MODIFIER_KEYS, NAMED_KEYS
from .context import SEP

_KEY_TOKENS = {**MODIFIER_KEYS, **NAMED_KEYS}


def _key(token: str) -> str | None:
    t = token.strip().lower()
    if t in _KEY_TOKENS:
        return _KEY_TOKENS[t]
    if re.fullmatch(r"key[a-z]", t):
        # Windows meint den Buchstaben, evdev die Tastenposition (deutsch: Y/Z vertauscht).
        return LETTER_KEY[t[3]]
    if re.fullmatch(r"digit[0-9]", t):
        return f"KEY_{t[5]}"
    if re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", t):
        return f"KEY_{t.upper()}"
    return None


def keyboard_combo(windows_key: str | None) -> str | None:
    """``ControlOrCommand+Shift+KeyZ___…`` -> ``KEY_LEFTCTRL+KEY_LEFTSHIFT+KEY_Y``;
    unbekannt -> None."""
    if not windows_key:
        return None
    keys = [_key(token) for token in windows_key.split(SEP)[0].split("+")]
    if None in keys:
        return None
    return "+".join(keys) if keys else None
