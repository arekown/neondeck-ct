"""Rad im Cockpit-Look: drehender Tick-Ring und Radar-Strahl um das klassische Radbild."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from ...device.layout import WHEEL_SIZE as WHEEL
from ..draw import mix, to_round
from ..palette import C_BG, C_CYAN, C_CYAN_DIM, C_MAGENTA
from .timing import FPS, SLOW_EVERY, slow_step

RING_DEG_S = 6.0        # Rad-Ring: Grad je Sekunde
SWEEP_DEG_S = 30.0      # Radar-Strahl im Ring
SWEEP_TAIL = 8
RING_R0, RING_R1 = 110, 119  # Rad-Ring: innen/aussen (der klassische Inhalt endet bei 108)
TICKS = 36


def _band() -> Image.Image:
    """Maske: aussen ab ``RING_R0`` (Platz fuer den Ring)."""
    ring = Image.new("L", (WHEEL, WHEEL), 255)
    c = WHEEL / 2
    r = RING_R0 - 1
    ImageDraw.Draw(ring).ellipse((c - r, c - r, c + r, c + r), fill=0)
    return ring


def _box(r: float) -> tuple[float, float, float, float]:
    c = WHEEL / 2
    return c - r, c - r, c + r, c + r


def _radar(d: ImageDraw.ImageDraw, sweep: float) -> None:
    band = RING_R1 - RING_R0 - 1  # PIL: Bogenbreite zaehlt vom Radius nach innen
    for k in range(SWEEP_TAIL):  # Radar-Strahl: Schweif hinter dem Kopf
        a0 = sweep - (k + 1) * 4
        d.arc(_box(RING_R1 - 1), a0, a0 + 4.5,
              fill=mix(C_BG, C_CYAN, 0.55 * (1 - k / SWEEP_TAIL)), width=band)
    for r in (RING_R0, RING_R1):
        d.ellipse(_box(r), outline=mix(C_BG, C_CYAN_DIM, 0.55))


def _ticks(d: ImageDraw.ImageDraw, rot: float) -> None:
    c = WHEEL / 2
    for n in range(TICKS):
        a = math.radians(rot + n * 10)
        major = n % 3 == 0
        r0, r1 = (RING_R0 + 1, RING_R1 - 1) if major else (RING_R0 + 3, RING_R1 - 3)
        color = (C_MAGENTA if n % 9 == 0 else C_CYAN) if major else C_CYAN_DIM
        d.line((c + r0 * math.cos(a), c + r0 * math.sin(a),
                c + r1 * math.cos(a), c + r1 * math.sin(a)),
               fill=color, width=2 if major else 1)


class WheelRing:
    def __init__(self) -> None:
        self._band = _band()

    def render(self, base: Image.Image, frame: int) -> Image.Image:
        """Klassisches Radbild ``base`` mit drehendem Tick-Ring und Radar-Strahl aussen."""
        img = base.convert("RGB").copy()
        img.paste(C_BG, (0, 0), self._band)
        d = ImageDraw.Draw(img)
        t = slow_step(frame) * SLOW_EVERY / FPS
        rot = t * RING_DEG_S
        sweep = (t * SWEEP_DEG_S) % 360
        _radar(d, sweep)
        _ticks(d, rot)
        for start in (-rot * 2, -rot * 2 + 180):  # zwei Marken, gegenlaeufig
            d.arc(_box((RING_R0 + RING_R1) / 2), start, start + 18, fill=C_MAGENTA, width=3)
        d.arc(_box(RING_R1 - 1), sweep - 1, sweep + 1, fill=mix(C_CYAN, (255, 255, 255), 0.4),
              width=RING_R1 - RING_R0 - 1)  # Kopf des Strahls
        return to_round(img)
