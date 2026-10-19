"""Text in den Touch-Feldern: jede Ziffer und jedes Wort steht in genau einem Feld.

Zwischen den 12 Touch-Feldern (90 × 90) und zu den Seitenleisten hat das Geraet Stege; Grafik
darf darueber laufen, **Schrift nie** (``tile_texts``). ``MinuteCache`` baut eine Uhr-Ebene
einmal je Minute.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ...device.layout import FIELD_SIZE as TILE
from ...device.layout import STRIP_WIDTH as STRIP
from ..palette import RGB
from ..text import fit_font, month_short, weekday_short
from .base import HEIGHT, WIDTH

TILE_INSET = 8  # Abstand der Schrift zum Steg zwischen den Feldern


def centered(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, fnt, fill) -> None:
    draw.text(xy, text, font=fnt, fill=fill, anchor="mm")


def tile_center(col: int, row: int) -> tuple[float, float]:
    """Mitte des Touch-Felds (Spalte 0–3, Reihe 0–2) auf der 480er-Flaeche."""
    return STRIP + col * TILE + TILE / 2, row * TILE + TILE / 2


@dataclass(frozen=True)
class TileText:
    col: int
    row: int
    text: str
    size: int
    color: RGB
    family: str = "Inter"
    bold: bool = False
    dy: float = 0


def tile_texts(items: list[TileText], glow: float = 0.0) -> Image.Image:
    """RGB-Ebene (480 × 270, schwarz) mit jedem Text mittig in seinem Feld; zu breite Texte
    werden kleiner statt ueber den Steg zu laufen. Mit ``glow`` leuchtet die Schrift – das
    Leuchten bleibt ebenfalls im eigenen Feld."""
    layer = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    d = ImageDraw.Draw(layer)
    for it in items:
        fnt = fit_font(it.text, TILE - 2 * TILE_INSET, it.size, 8, it.bold, it.family)
        x, y = tile_center(it.col, it.row)
        centered(d, (x, y + it.dy), it.text, fnt, it.color)
    if glow <= 0:
        return layer
    halo = layer.filter(ImageFilter.GaussianBlur(glow))
    halo = ImageChops.add(halo, halo, scale=1.4)
    mask = Image.new("L", (WIDTH, HEIGHT), 0)
    md = ImageDraw.Draw(mask)
    for it in items:
        x, y = tile_center(it.col, it.row)
        h = TILE / 2 - 3
        md.rectangle((x - h, y - h, x + h, y + h), fill=255)
    clipped = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    clipped.paste(halo, (0, 0), mask)
    core = Image.eval(layer, lambda v: v * 3 // 4)  # Kern etwas dunkler: bleibt farbig
    return ImageChops.add(core, clipped)


def clock_digits(now: datetime, row: int, size: int, color: RGB, family: str,
                 bold: bool = True) -> list[TileText]:
    """HH MM: je Ziffer ein Feld der Reihe ``row``."""
    return [TileText(col, row, ch, size, color, family, bold)
            for col, ch in enumerate(now.strftime("%H%M"))]


def date_tiles(now: datetime, row: int, size: int, color: RGB, family: str,
               bold: bool = False, upper: bool = True) -> list[TileText]:
    """Wochentag | Tag | Monat | Jahr, je ein Feld."""
    day = weekday_short(now.weekday())
    month = month_short(now.month)
    day, month = (day.upper(), month.upper()) if upper else (day, month.title())
    return [TileText(col, row, text, size, color, family, bold)
            for col, text in enumerate((day, f"{now.day}.", month, f"{now.year}"))]



class MinuteCache:
    """Eine Ebene, die sich nur einmal je Minute aendert (Uhr, Datum): ``get(now)``."""

    def __init__(self, build: Callable[[datetime], Image.Image]) -> None:
        self._build = build
        self._key: str | None = None
        self._img: Image.Image | None = None

    def get(self, now: datetime) -> Image.Image:
        key = now.strftime("%Y%m%d%H%M")
        if key != self._key or self._img is None:
            self._img, self._key = self._build(now), key
        return self._img
