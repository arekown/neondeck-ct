"""Klartext-Makros: one step per line <-> macro step dicts.

    hotkey ctrl+shift+t | text Hallo Welt | wait 200 | run firefox | open https://x.de
    command htop (Konsole) | shell notify-send hi (still) | key down shift | key up shift
    # Kommentar, Leerzeilen werden ignoriert
"""
from __future__ import annotations

import re

from ..core.errors import LoupedeckError
from ..core.i18n import N_, tr
from ..core.keymap import LETTER_KEY

_MODS = {
    "ctrl": "KEY_LEFTCTRL", "strg": "KEY_LEFTCTRL", "shift": "KEY_LEFTSHIFT",
    "umschalt": "KEY_LEFTSHIFT", "alt": "KEY_LEFTALT", "altgr": "KEY_RIGHTALT",
    "super": "KEY_LEFTMETA", "meta": "KEY_LEFTMETA", "win": "KEY_LEFTMETA",
}
_NAMED = {
    "enter": "KEY_ENTER", "return": "KEY_ENTER", "tab": "KEY_TAB", "esc": "KEY_ESC",
    "escape": "KEY_ESC", "space": "KEY_SPACE", "backspace": "KEY_BACKSPACE",
    "delete": "KEY_DELETE", "entf": "KEY_DELETE", "up": "KEY_UP", "down": "KEY_DOWN",
    "left": "KEY_LEFT", "right": "KEY_RIGHT",
}
_TO_EVDEV = {**_MODS, **_NAMED}
# canonical short form per evdev name (first entry wins)
_TO_SHORT: dict[str, str] = {}
for _k, _v in {**_NAMED, **_MODS}.items():
    _TO_SHORT.setdefault(_v, _k)
_TO_SHORT.update({"KEY_LEFTCTRL": "ctrl", "KEY_LEFTSHIFT": "shift", "KEY_LEFTALT": "alt",
                  "KEY_RIGHTALT": "altgr", "KEY_LEFTMETA": "super", "KEY_ENTER": "enter",
                  "KEY_ESC": "esc", "KEY_DELETE": "delete"})
_TO_SHORT.update({_v: _c for _c, _v in LETTER_KEY.items()})
for _d in "0123456789":
    _TO_SHORT[f"KEY_{_d}"] = _d
for _n in range(1, 25):
    _TO_SHORT[f"KEY_F{_n}"] = f"f{_n}"

_FKEY = re.compile(r"f([1-9]|1\d|2[0-4])")


class MacroSyntaxError(LoupedeckError, ValueError):
    def __init__(self, line: int, message: str):
        super().__init__(tr("Zeile {line}: {message}", line=line, message=message))
        self.line = line
        self.message = message


def _key(name: str) -> str:
    low = name.lower()
    if name.startswith("KEY_"):
        return name
    if low in _TO_EVDEV:
        return _TO_EVDEV[low]
    if low in LETTER_KEY:
        return LETTER_KEY[low]
    if low.isdigit() and len(low) == 1:
        return f"KEY_{low}"
    if _FKEY.fullmatch(low):
        return f"KEY_{low.upper()}"
    raise ValueError(tr("Unbekannte Taste: {name}", name=name))


def _combo(text: str) -> str:
    parts = [p.strip() for p in text.split("+")]
    if not text.strip() or not all(parts):
        raise ValueError(tr("Keine Tasten angegeben"))
    return "+".join(_key(p) for p in parts)


def _short_combo(keys: str) -> str:
    return "+".join(_TO_SHORT.get(k, k) for k in keys.split("+"))


def _int_ms(arg: str) -> int:
    try:
        ms = int(arg.strip())
    except ValueError:
        raise ValueError(tr("Wartezeit muss eine ganze Zahl in Millisekunden sein")) from None
    if ms < 0:
        raise ValueError(tr("Wartezeit darf nicht negativ sein"))
    return ms


def _need(arg: str, what: str) -> str:
    """``what``: Name des Arguments (Quelltext, ``N_``-markiert am Aufruf)."""
    if not arg.strip():
        raise ValueError(tr("{what} fehlt", what=tr(what)))
    return arg.strip()


def _parse_line(line: str) -> dict:
    # nur links strippen: ``text a `` behaelt Leerzeichen am Ende, die uebrigen Befehle
    # strippen ihr Argument selbst (``_need``, ``_int_ms``, ``_combo``)
    cmd, _, rest = line.lstrip().partition(" ")
    cmd = cmd.lower()
    if cmd == "hotkey":
        return {"type": "hotkey", "keys": _combo(rest)}
    if cmd == "text":
        return {"type": "text", "text": (_need(rest, N_("Text")), rest)[1]}
    if cmd == "wait":
        return {"type": "sleep", "ms": _int_ms(rest)}
    if cmd == "run":
        return {"type": "run", "command": _need(rest, N_("Befehl"))}
    if cmd == "open":
        return {"type": "open", "target": _need(rest, N_("Ziel"))}
    if cmd in ("command", "shell"):
        return {"type": "command", "command": _need(rest, N_("Befehl")), "terminal": cmd == "command"}
    if cmd == "key":
        direction, _, keys = rest.strip().partition(" ")
        if direction.lower() == "down":
            return {"type": "hold_key", "keys": _combo(keys)}
        if direction.lower() == "up":
            return {"type": "hold_key", "keys": _combo(keys), "release": True}
        raise ValueError(tr("Nach 'key' muss 'down' oder 'up' folgen"))
    raise ValueError(tr("Unbekannter Befehl: {command}", command=cmd))


def parse(text: str) -> list[dict]:
    steps = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            steps.append(_parse_line(line))
        except ValueError as e:
            raise MacroSyntaxError(n, str(e)) from None
    return steps


def _format_step(s: dict) -> str:
    t = s.get("type")
    if t == "hotkey":
        return f"hotkey {_short_combo(s['keys'])}"
    if t == "text":
        if "\n" in s["text"] or "\r" in s["text"]:
            raise ValueError(tr("Text mit Zeilenumbruch nicht darstellbar"))
        return f"text {s['text']}"
    if t == "sleep":
        return f"wait {s['ms']}"
    if t == "run":
        return f"run {s['command']}"
    if t == "open":
        return f"open {s['target']}"
    if t == "command":
        return f"{'command' if s.get('terminal', True) else 'shell'} {s['command']}"
    if t == "hold_key":
        return f"key {'up' if s.get('release') else 'down'} {_short_combo(s['keys'])}"
    raise ValueError(tr("Schritt nicht als Klartext darstellbar: {type}", type=t))


def format(steps: list[dict]) -> str:
    return "".join(_format_step(s) + "\n" for s in steps)
