"""LEDs der runden Tasten (ohne Qt): Farben aus dem Profil, nur Geaendertes senden.

Runde Tasten mit Aktion ``workspace``: der aktive Arbeitsbereich in seiner Farbe
(``led_color``, Standard weiss), andere Arbeitsbereiche in ihrer Farbe mit ``LED_INACTIVE``;
andere Aktionen gedimmt weiss, unbelegt oder Ziel fehlt: aus.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from PIL import ImageColor

from ..device.layout import ROUND_CODES
from ..profile.model import Profile
from .kinds import action_type

log = logging.getLogger(__name__)

LED_ACTIVE = (255, 255, 255)  # Standard-LED-Farbe eines Arbeitsbereichs (``led_color``)
LED_DIM = (40, 40, 40)        # runde Taste mit anderer Aktion
LED_OFF = (0, 0, 0)
LED_INACTIVE = 0.2            # Taste eines anderen Arbeitsbereichs: seine Farbe mit 20 %
WORKSPACE = "workspace"       # Aktion, deren Taste den Arbeitsbereich zeigt


def device_write(fn: Callable[..., object], *args: object, what: str) -> bool:
    """Geraet beschreiben; ein Fehler (z. B. Geraet getrennt) wird nur als Warnung geloggt."""
    try:
        fn(*args)
    except Exception as e:  # noqa: BLE001 - z. B. Geraet getrennt; nie in die Ereignisschleife
        log.warning("%s: %s", what, e)
        return False
    return True


def workspace_led(profile: Profile, ws_id: object) -> tuple | None:
    """LED-Farbe des Arbeitsbereichs (``led_color``, Standard weiss); ``None``, wenn es ihn
    nicht gibt."""
    ws = next((w for w in profile.workspaces if w.id == ws_id), None)
    if ws is None:
        return None
    try:
        return ImageColor.getrgb(ws.led_color)[:3] if ws.led_color else LED_ACTIVE
    except (ValueError, TypeError, AttributeError):
        return LED_ACTIVE


def round_colors(profile: Profile, workspace_id: str) -> tuple[dict[int, tuple], set[int]]:
    """Farbe je runder Taste und die Tasten des aktiven Arbeitsbereichs (Cockpit: atmen)."""
    colors: dict[int, tuple] = {}
    active: set[int] = set()
    for code in ROUND_CODES:
        a = profile.round.get(code)
        action = a.action if a else {}
        t = action_type(action)
        if t == WORKSPACE:
            color = workspace_led(profile, action.get("id"))
            if color is None:  # Ziel gibt es nicht
                color = LED_OFF
            elif action.get("id") != workspace_id:
                color = tuple(round(c * LED_INACTIVE) for c in color)
            else:
                active.add(code)
            colors[code] = color
        else:
            colors[code] = LED_DIM if t else LED_OFF
    return colors, active


class LedController:
    """Sendet LED-Farben an das Geraet, unveraenderte nicht noch einmal."""

    def __init__(self, leds: Callable[[dict[int, tuple]], None]) -> None:
        self._leds = leds
        self._last: dict[int, tuple] | None = None

    def update(self, colors: dict[int, tuple]) -> None:
        """``colors`` senden, wenn sie sich geaendert haben (Fehler: beim naechsten Mal neu)."""
        if colors == self._last:
            return
        self._last = colors
        if not device_write(self._leds, colors, what="LEDs setzen fehlgeschlagen"):
            self._last = None

    def show(self, colors: dict[int, tuple]) -> None:
        """``colors`` direkt senden (Bildschirmschoner); danach sendet ``update`` wieder."""
        self._last = None
        device_write(self._leds, colors, what="LEDs setzen fehlgeschlagen")

    def off(self) -> None:
        """Alle LEDs aus; danach sendet ``update`` wieder."""
        self._last = None
        device_write(self._leds, dict.fromkeys(ROUND_CODES, LED_OFF),
                     what="LEDs nicht ausgeschaltet")

    def forget(self) -> None:
        """Beim naechsten ``update`` alles neu senden."""
        self._last = None
