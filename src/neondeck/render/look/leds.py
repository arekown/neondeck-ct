"""LEDs im Cockpit-Look: die Taste des aktiven Arbeitsbereichs atmet."""
from __future__ import annotations

from ..draw import pulse, scale
from ..palette import RGB
from .timing import FPS

BREATH_S = 3.0          # LED der aktiven Taste: ein Atemzug
BREATH_MIN = 0.6


def breath(frame: int) -> float:
    """Helligkeit der aktiven Taste: ``BREATH_MIN`` … 1, in 5-%-Stufen."""
    k = BREATH_MIN + (1 - BREATH_MIN) * pulse(frame / FPS, BREATH_S)
    return round(k * 20) / 20


def leds(colors: dict[int, RGB], active: set[int], frame: int) -> dict[int, RGB]:
    """Farben wie klassisch; ``active`` (Taste des aktiven Arbeitsbereichs) atmet."""
    k = breath(frame)
    return {code: scale(c, k) if code in active else c for code, c in colors.items()}
