"""Virtuelle Maus ueber uinput, nur fuer das Mausrad (Regler/Rad -> scrollen, mit Strg zoomen).

Ein eigenes Geraet neben der Tastatur: libinput erkennt ein Geraet erst mit X/Y-Achsen und
Maustasten als Zeigegeraet (sonst verwirft es die Radereignisse); bewegt wird der Zeiger
nie. Modifikatoren haelt die Tastatur – der Compositor fuehrt sie je Sitz zusammen.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable

from evdev import UInput, ecodes

from .keyboard import SETTLE_DELAY

DEVICE_NAME = "Neondeck CT Maus"
CAPABILITIES = {
    ecodes.EV_KEY: [ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE],
    ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y, ecodes.REL_WHEEL, ecodes.REL_HWHEEL],
}


class Mouse:
    """Schreibt Radereignisse auf ein beim ersten Gebrauch angelegtes uinput-Geraet.

    ``device`` laesst sich einsetzen (alles mit ``write(type, code, value)`` und ``syn()``).
    """

    def __init__(self, device=None, *, sleep: Callable[[float], None] = time.sleep):
        self._device = device
        self._sleep = sleep
        self._lock = threading.Lock()

    def _dev(self):
        if self._device is None:
            self._device = UInput(CAPABILITIES, name=DEVICE_NAME)
            self._sleep(SETTLE_DELAY)
        return self._device

    def scroll(self, vertical: int = 0, horizontal: int = 0) -> None:
        """Rastungen drehen: ``vertical`` > 0 nach oben, ``horizontal`` > 0 nach rechts
        (Vorzeichen wie ``REL_WHEEL``/``REL_HWHEEL``). Jede Rastung ist ein eigenes
        Ereignis, wie bei einem echten Rad."""
        with self._lock:
            dev = self._dev()
            for code, amount in ((ecodes.REL_WHEEL, vertical), (ecodes.REL_HWHEEL, horizontal)):
                step = 1 if amount > 0 else -1
                for _ in range(abs(amount)):
                    dev.write(ecodes.EV_REL, code, step)
                    dev.syn()

    def close(self) -> None:
        with self._lock:
            if self._device is not None and hasattr(self._device, "close"):
                self._device.close()
            self._device = None
