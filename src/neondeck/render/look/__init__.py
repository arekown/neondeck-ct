"""Geraete-Look: wie die Displays im Normalbetrieb aussehen (ohne Qt).

``classic`` ist das bisherige Aussehen (``render.images`` und ``engine.painter`` unveraendert, kein
Takt). ``cockpit`` legt die Inhalte in ein animiertes HUD in der Stimmung von
``savers.CockpitSaver`` – Cyan und Magenta gemischt:

* Mitte (``center``): Raster, Scan-Linie, Neonrahmen je Feld, Pings.
* Leisten (``strips``): Name Cyan, Wert Magenta, Rahmen im Verlauf, Neon-Lauflicht an der
  Kante zur Mitte; auch die Anzeige „system“ (``render.system_strip``).
* Rad (``wheel``): Inhalt wie bisher, aussen ein drehender Ring mit Radar-Strahl.
* LEDs (``leds``): Farben wie bisher, die Taste des aktiven Arbeitsbereichs atmet (60–100 %).

Der Takt (``timing``) laeuft ueber eine Bildnummer, nicht ueber die Uhr: gleiche Nummer,
gleiches Bild – die Engine sendet dann nichts.
"""
from __future__ import annotations

from PIL import Image, ImageColor

from .. import system_strip
from ..palette import ERROR, RGB
from . import leds, strips, timing, wheel
from .center import FAILED, PRESSED, CenterRenderer, CenterTile
from .timing import FPS, FRAME_S, PING_EVERY, SLOW_EVERY, ping_tiles

__all__ = ["AUTO", "CLASSIC", "COCKPIT", "ERROR", "FAILED", "FPS", "FRAME_S", "LOOKS",
           "PING_EVERY", "PRESSED", "SLOW_EVERY", "CenterTile", "CockpitLook", "is_black",
           "make", "ping_tiles", "resolve"]

CLASSIC, COCKPIT, AUTO = "classic", "cockpit", "auto"
LOOKS = (CLASSIC, COCKPIT)  # settings.LOOK_NAMES = ("auto", *LOOKS); ein Test prueft das


def resolve(name: str, theme: str) -> str:
    """``auto`` → ``cockpit`` zum Editor-Theme ``cockpit``, sonst ``classic``; Unbekanntes →
    ``classic``."""
    if name == AUTO:
        return COCKPIT if theme == "cockpit" else CLASSIC
    return name if name in LOOKS else CLASSIC


def make(name: str) -> CockpitLook | None:
    """Look-Objekt fuer ``name`` (``None`` = klassisch, nichts animiert)."""
    return CockpitLook() if name == COCKPIT else None


def is_black(color: str) -> bool:
    """Tastenhintergrund schwarz (= im Cockpit-Look durchsichtig)?"""
    try:
        return ImageColor.getrgb(color)[:3] == (0, 0, 0)
    except (ValueError, TypeError, AttributeError):
        return False


class CockpitLook:
    """Der animierte Look: duenne Fassade ueber Mitte, Leisten, Rad und LEDs. Nur im
    Engine-Thread benutzen (die Teile halten Caches)."""

    name = COCKPIT

    def __init__(self) -> None:
        self._center = CenterRenderer()
        self._strips = strips.StripRenderer()
        self._wheel = wheel.WheelRing()

    slow_step = staticmethod(timing.slow_step)
    breath = staticmethod(leds.breath)

    def background(self, frame: int) -> Image.Image:
        """Raster (pulsierend, mit Scanlines) und Scan-Linie mit Schweif."""
        return self._center.background(frame)

    def center(self, tiles: list[CenterTile | None], page_index: int, page_count: int,
               frame: int) -> Image.Image:
        """Mittleres Display (360 × 270) zur Bildnummer ``frame``."""
        return self._center.render(tiles, page_index, page_count, frame)

    def strip(self, sections: list[tuple[str, str | None, float | None]],
              flashing: tuple, frame: int, edge: str, pressed: tuple = ()) -> Image.Image:
        """Eine Leiste (60 × 270, drei Abschnitte aus ``screens.strip_section``); ``edge``
        ``"right"`` (linke Leiste) oder ``"left"``: Kante zur Mitte mit Lauflicht."""
        return self._strips.strip(sections, flashing, frame, edge, pressed)

    def system_strip(self, values: system_strip.Values, flashing: tuple, frame: int,
                     edge: str) -> Image.Image:
        """Leiste „system“ (CPU, RAM, GPU 1, GPU 2) im Neon-Stil mit Lauflicht."""
        return self._strips.system(values, flashing, frame, edge)

    def wheel(self, base: Image.Image, frame: int) -> Image.Image:
        """Klassisches Radbild ``base`` mit drehendem Tick-Ring und Radar-Strahl aussen."""
        return self._wheel.render(base, frame)

    @staticmethod
    def leds(colors: dict[int, RGB], active: set[int], frame: int) -> dict[int, RGB]:
        """Farben wie klassisch; ``active`` (Taste des aktiven Arbeitsbereichs) atmet."""
        return leds.leds(colors, active, frame)
