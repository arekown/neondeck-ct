"""Tastennamen (evdev, ``KEY_…``) und ihre deutschen Anzeigenamen, ohne Qt."""
from __future__ import annotations

from ...core.i18n import N_, tr
from ...core.keymap import CHAR_MAP

MODIFIER_ORDER = ["KEY_LEFTCTRL", "KEY_RIGHTCTRL", "KEY_LEFTSHIFT", "KEY_RIGHTSHIFT",
                  "KEY_LEFTALT", "KEY_RIGHTALT", "KEY_LEFTMETA", "KEY_RIGHTMETA"]

KEY_NAMES_DE = {
    "KEY_LEFTCTRL": N_("Strg"), "KEY_RIGHTCTRL": N_("Strg"), "KEY_LEFTSHIFT": N_("Umschalt"),
    "KEY_RIGHTSHIFT": N_("Umschalt"), "KEY_LEFTALT": N_("Alt"), "KEY_RIGHTALT": N_("AltGr"),
    "KEY_LEFTMETA": N_("Super"), "KEY_RIGHTMETA": N_("Super"),
    "KEY_ENTER": N_("Eingabe"), "KEY_SPACE": N_("Leertaste"), "KEY_TAB": N_("Tab"), "KEY_ESC": N_("Esc"),
    "KEY_BACKSPACE": N_("Rücktaste"), "KEY_DELETE": N_("Entf"), "KEY_INSERT": N_("Einfg"),
    "KEY_HOME": N_("Pos1"), "KEY_END": N_("Ende"), "KEY_PAGEUP": N_("Bild hoch"), "KEY_PAGEDOWN": N_("Bild runter"),
    "KEY_UP": N_("Pfeil hoch"), "KEY_DOWN": N_("Pfeil runter"), "KEY_LEFT": N_("Pfeil links"),
    "KEY_RIGHT": N_("Pfeil rechts"), "KEY_CAPSLOCK": N_("Feststelltaste"), "KEY_SYSRQ": N_("Druck"),
    "KEY_PRINT": N_("Druck"), "KEY_PAUSE": N_("Pause"), "KEY_SCROLLLOCK": N_("Rollen"),
    "KEY_NUMLOCK": N_("Num"), "KEY_COMPOSE": N_("Menü"), "KEY_PLAYPAUSE": N_("Wiedergabe/Pause"),
    "KEY_NEXTSONG": N_("Nächster Titel"), "KEY_PREVIOUSSONG": N_("Vorheriger Titel"),
    "KEY_STOPCD": N_("Stopp"), "KEY_VOLUMEUP": N_("Lauter"), "KEY_VOLUMEDOWN": N_("Leiser"),
    "KEY_MUTE": N_("Stumm"), "KEY_KPENTER": N_("Num Eingabe"), "KEY_KPPLUS": N_("Num +"),
    "KEY_KPMINUS": N_("Num -"), "KEY_KPASTERISK": N_("Num *"), "KEY_KPSLASH": N_("Num /"),
    "KEY_KPDOT": N_("Num ,"), }
# Zeichen der Taste im deutschen Layout (ohne Umschalt/AltGr), z. B. KEY_Y -> "Z"
_KEY_CHARS = {name: ch for ch, (name, shift, altgr) in CHAR_MAP.items()
              if not shift and not altgr and ch.isprintable() and not ch.isspace()}


def key_name_de(name: str) -> str:
    if name in KEY_NAMES_DE:
        return tr(KEY_NAMES_DE[name])
    if name.startswith("KEY_KP") and name[6:].isdigit():
        return tr("Num {digit}", digit=name[6:])
    ch = _KEY_CHARS.get(name)
    if ch is not None:
        return ch.upper() if len(ch.upper()) == 1 else ch
    return name[4:] if name.startswith("KEY_") else name


def key_display(combo: str) -> str:
    """``"KEY_LEFTCTRL+KEY_LEFTSHIFT+KEY_T"`` -> ``"Strg+Umschalt+T"``."""
    return "+".join(key_name_de(n) for n in combo.split("+") if n)
