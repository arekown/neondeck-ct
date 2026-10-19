"""Bildschirmschoner fuer den CT: Animationen ueber alle Displays, das Rad und die LEDs.

Die drei oberen Displays liegen nebeneinander und ergeben eine Flaeche von 480 × 270 Pixeln
(links 0–59, Mitte 60–419, rechts 420–479); dazu kommt das runde Raddisplay (240 × 240) und
die acht runden Tasten (LED-Farben). Jede Variante liefert je Bild ein ``Frame``; der Dienst
verteilt es auf die Displays (``Engine.saver_frame``).

**Raster beachten:** Zwischen den 12 Touch-Feldern (90 × 90) und zu den Seitenleisten hat das
Geraet Stege. Grafik darf darueber laufen, **Schrift nie** – jede Ziffer und jedes Wort steht in
genau einem Feld (``tile_texts``), sonst wird es vom Steg durchgestrichen.

Varianten:

* ``cockpit`` – HUD im Stil des Cyberpunk-Cockpit-Themes: Raster, abgeschraegte Kachelrahmen
  ueber dem Touch-Raster, Leuchtuhr, Scan-Linie, echte CPU-/RAM-Anzeige, Radar auf dem Rad.
* ``synthwave`` – Retro-Sonne mit Streifen, laufendes Gitter, Berge; Neon-Pink/Violett.
* ``matrix`` – fallende Zeichen in Gruen.
* ``warp`` – Sternenflug aus der Mitte heraus, Tunnelringe auf dem Rad.
* ``aurora`` – ruhige, fliessende Farbflaechen mit schlichter Uhr (zum Neutral-Theme).
* ``diashow`` – eigene Bilder aus einem Ordner (auch Unterordner), zufaellige Reihenfolge,
  weich ueberblendet; das Rad zeigt einen runden Ausschnitt, die LEDs Farben des Bildes.
"""
from __future__ import annotations

import time
from collections.abc import Callable

from .aurora import AuroraSaver
from .base import Frame, Saver, SaverOptions
from .cockpit import CockpitSaver
from .matrix import MatrixSaver
from .slideshow import SlideshowSaver, list_images
from .synthwave import SynthwaveSaver
from .tiles import TileText, clock_digits, date_tiles, tile_texts
from .warp import WarpSaver

__all__ = ["AUTO", "SAVERS", "Frame", "Saver", "TileText", "clock_digits", "date_tiles",
           "list_images", "make", "resolve", "tile_texts"]

SAVERS: dict[str, type[Saver]] = {s.name: s for s in (
    CockpitSaver, SynthwaveSaver, MatrixSaver, WarpSaver, AuroraSaver, SlideshowSaver)}
AUTO = "auto"
THEME_SAVER = {"cockpit": "cockpit", "neutral": "aurora", "system": "warp"}


def resolve(name: str, theme: str) -> str:
    """``auto`` → passende Variante zum Editor-Theme; Unbekanntes → Cockpit."""
    if name == AUTO:
        name = THEME_SAVER.get(theme, "cockpit")
    return name if name in SAVERS else "cockpit"


def make(name: str, seed: int | None = None, clock: Callable[[], float] = time.time,
         options: SaverOptions | None = None) -> Saver:
    """``options``: ``folder`` und ``slide_s`` fuer die Diashow."""
    return SAVERS[name if name in SAVERS else "cockpit"](seed, clock, options)

