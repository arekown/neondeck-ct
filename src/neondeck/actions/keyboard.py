"""Virtuelle Tastatur ueber uinput: Tastenkuerzel, gehaltene Tasten und getippter Text."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable

from evdev import UInput, ecodes

from ..core.i18n import tr
from ..core.keymap import CHAR_MAP, DEAD_KEYS

DEVICE_NAME = "Neondeck CT Tastatur"
TAP_DELAY = 0.008  # Sekunden zwischen Druecken und Loslassen
# Ein neues uinput-Geraet uebernimmt der Compositor nicht sofort; Ereignisse direkt nach dem
# Anlegen gingen verloren.
SETTLE_DELAY = 0.3


def _key_codes() -> list[int]:
    """Alle Codes aus ``ecodes.keys`` mit ``KEY_*``-Namen (keine BTN_*)."""
    codes = []
    for code, raw in ecodes.keys.items():
        names = raw if isinstance(raw, (list, tuple)) else [raw]
        if any(n.startswith("KEY_") for n in names):
            codes.append(code)
    return sorted(codes)


def _code(name: str) -> int:
    code = ecodes.ecodes.get(name) if name.startswith("KEY_") else None
    if code is None:
        raise ValueError(tr("Unbekannte Taste: {name}", name=name))
    return code


def parse_combo(combo: str) -> list[int]:
    """``"KEY_LEFTCTRL+KEY_T"`` -> Tastencodes; Modifikatoren zuerst, Haupttaste zuletzt."""
    names = [p.strip() for p in (combo or "").split("+") if p.strip()]
    if not names:
        raise ValueError(tr("Keine Tasten angegeben"))
    return [_code(n) for n in names]


class Keyboard:
    """Schreibt Tastenereignisse an ein uinput-Geraet, das beim ersten Gebrauch entsteht.

    ``device`` kann mitgegeben werden (alles mit ``write(type, code, value)`` und ``syn()``).
    """

    def __init__(self, device=None, *, sleep: Callable[[float], None] = time.sleep):
        self._device = device
        self._sleep = sleep
        self._lock = threading.Lock()  # eine Kombination nach der anderen, nie verschraenkt

    def _dev(self):
        if self._device is None:
            self._device = UInput({ecodes.EV_KEY: _key_codes()}, name=DEVICE_NAME)
            self._sleep(SETTLE_DELAY)
        return self._device

    def _emit(self, code: int, value: int) -> None:
        dev = self._dev()
        dev.write(ecodes.EV_KEY, code, value)
        dev.syn()

    def _tap_codes(self, codes: list[int]) -> None:
        *mods, main = codes
        for c in mods:
            self._emit(c, 1)
        self._emit(main, 1)
        self._sleep(TAP_DELAY)
        self._emit(main, 0)
        for c in reversed(mods):
            self._emit(c, 0)

    def tap(self, combo: str) -> None:
        codes = parse_combo(combo)
        with self._lock:
            self._tap_codes(codes)

    def press(self, combo: str) -> None:
        codes = parse_combo(combo)
        with self._lock:
            for c in codes:
                self._emit(c, 1)

    def release(self, combo: str) -> None:
        codes = parse_combo(combo)
        with self._lock:
            for c in reversed(codes):
                self._emit(c, 0)

    def type_text(self, text: str) -> None:
        unknown = sorted({ch for ch in text if ch not in CHAR_MAP})
        if unknown:
            raise ValueError(tr("Zeichen nicht tippbar: {chars}", chars="".join(unknown)))
        shift, altgr, space = ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTALT, ecodes.KEY_SPACE
        with self._lock:
            for ch in text:
                name, use_shift, use_altgr = CHAR_MAP[ch]
                mods = [shift] * use_shift + [altgr] * use_altgr
                self._tap_codes(mods + [_code(name)])
                if ch in DEAD_KEYS:
                    self._tap_codes([space])

    def close(self) -> None:
        with self._lock:
            if self._device is not None and hasattr(self._device, "close"):
                self._device.close()
            self._device = None
