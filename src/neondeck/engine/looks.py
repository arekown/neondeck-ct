"""Geraete-Looks als Strategie fuer den ``DisplayPainter`` (ohne Qt).

``ClassicLook`` zeichnet wie bisher (Fehler/Druck als Rand im Tastenbild, nichts animiert),
``CockpitLook`` legt die Bilder in ``render.look.CockpitLook`` (Rahmen statt Rand,
Lauflicht, atmende LED; der Takt gibt die Bildnummer ``frame``). Beide erfuellen
``ports.Look``: je Display ein Vergleichsschluessel und das Zeichnen dazu.
"""
from __future__ import annotations

from dataclasses import replace
from functools import partial

from PIL import Image

from ..render import look as looks
from ..render import system_strip
from ..render.images import compose_center
from ..render.palette import ERROR_HEX
from .painter import HIGHLIGHT, strip_image
from .ports import Look, Paint, RenderTiles, TileSpecs


def tile_keys(specs: TileSpecs) -> tuple:
    """Vergleichsschluessel der Felder (``None`` = leer)."""
    return tuple(None if s is None else s.key(ref) for s, ref in specs)


def look_mark(flash: str | None) -> str:
    """Rand des klassischen Tastenbilds -> Rahmen im Cockpit-Look."""
    if flash == ERROR_HEX:
        return looks.FAILED
    return looks.PRESSED if flash == HIGHLIGHT else ""


class ClassicLook:
    """Klassisch: Tastenbilder mit Rand, Leisten und Rad ohne Animation."""
    name = looks.CLASSIC
    animated = False

    def center(self, specs: TileSpecs, dot: int, dots: int, frame: int,
               render: RenderTiles) -> tuple[object, Paint]:
        keys = tile_keys(specs)
        return (keys, dot, dots), lambda: compose_center(render(specs, keys), dot, dots)

    def strip(self, sections: list[tuple[str, str | None, float | None]], flashing: tuple,
              pressed: tuple, frame: int, edge: str) -> tuple[object, Paint]:
        return (tuple(sections), flashing), partial(strip_image, sections, flashing, ERROR_HEX)

    def system_strip(self, values: tuple, flashing: tuple, frame: int,
                     edge: str) -> tuple[object, Paint]:
        return ("system", values, flashing), partial(system_strip.classic, values, flashing,
                                                     ERROR_HEX)

    def wheel(self, key: tuple, base: Paint, frame: int) -> tuple[object, Paint]:
        return key, base

    def leds(self, colors: dict[int, tuple], active: set[int],
             frame: int) -> dict[int, tuple]:
        return colors


class CockpitLook:
    """Cockpit: Druck/Fehler zeichnet der Look (Rahmen), nicht das Tastenbild; Leisten und Rad
    wechseln mit jedem langsamen Schritt (``slow_step``), die Mitte mit jedem Bild."""
    animated = True

    def __init__(self, look: looks.CockpitLook) -> None:
        self._look = look
        self.name = look.name
        self._wheel_base: tuple | None = None  # (Inhalt, klassisches Radbild)

    def center(self, specs: TileSpecs, dot: int, dots: int, frame: int,
               render: RenderTiles) -> tuple[object, Paint]:
        marks = tuple(None if s is None else look_mark(s.flash) for s, _ in specs)
        specs = [(None if s is None else replace(s, flash=None), ref) for s, ref in specs]
        keys = tile_keys(specs)

        def paint() -> Image.Image:
            tiles = render(specs, keys)
            layers = [None if tile is None else
                      looks.CenterTile(tile, looks.is_black(spec.bg), mark)
                      for tile, (spec, _), mark in zip(tiles, specs, marks)]
            return self._look.center(layers, dot, dots, frame)
        return (keys, dot, dots, marks, frame), paint

    def strip(self, sections: list[tuple[str, str | None, float | None]], flashing: tuple,
              pressed: tuple, frame: int, edge: str) -> tuple[object, Paint]:
        key = (tuple(sections), flashing, pressed, self._look.slow_step(frame))
        return key, partial(self._look.strip, sections, flashing, frame, edge, pressed)

    def system_strip(self, values: tuple, flashing: tuple, frame: int,
                     edge: str) -> tuple[object, Paint]:
        key = ("system", values, flashing, self._look.slow_step(frame))
        return key, partial(self._look.system_strip, values, flashing, frame, edge)

    def wheel(self, key: tuple, base: Paint, frame: int) -> tuple[object, Paint]:
        def paint() -> Image.Image:
            if self._wheel_base is None or self._wheel_base[0] != key:  # Inhalt neu: einmal
                self._wheel_base = (key, base())
            return self._look.wheel(self._wheel_base[1], frame)
        return (key, self._look.slow_step(frame)), paint

    def leds(self, colors: dict[int, tuple], active: set[int],
             frame: int) -> dict[int, tuple]:
        return self._look.leds(colors, active, frame)


def make_look(name: str) -> Look:
    """Look-Strategie fuer ``name`` (``render.look``; Unbekanntes: klassisch)."""
    cockpit = looks.make(name)
    return CockpitLook(cockpit) if cockpit is not None else ClassicLook()
