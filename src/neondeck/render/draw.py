"""Zeichen-Helfer, die mehrere Anzeigen teilen (Farbmischen, Formen, Verlaeufe, Seitenpunkte)."""
from __future__ import annotations

import math
from collections.abc import Callable
from functools import cache

from PIL import Image, ImageDraw

from ..device.layout import DISPLAY_HEIGHT, WHEEL_SIZE
from .palette import RGB

PAGE_DOT_GAP = 10
PAGE_DOT_Y = (DISPLAY_HEIGHT - 6, DISPLAY_HEIGHT - 3)  # Seitenpunkte: Zeilen unten in der Mitte


def mix(a: RGB, b: RGB, t: float) -> RGB:
    t = max(0.0, min(1.0, t))
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))  # type: ignore[return-value]


def scale(c: RGB, k: float) -> RGB:
    return tuple(max(0, min(255, round(x * k))) for x in c)  # type: ignore[return-value]


def pulse(t: float, period: float) -> float:
    """0 … 1, weich."""
    return 0.5 + 0.5 * math.sin(2 * math.pi * t / period)


def bevel(x0: int, y0: int, x1: int, y1: int, cut: int) -> list[tuple[int, int]]:
    """Rechteck mit abgeschraegter Ecke oben links und unten rechts (wie im Cockpit-CSS)."""
    return [(x0 + cut, y0), (x1, y0), (x1, y1 - cut), (x1 - cut, y1), (x0, y1), (x0, y0 + cut)]


@cache
def round_mask() -> Image.Image:
    """Kreis ueber das ganze Raddisplay (nur lesen, nicht veraendern)."""
    m = Image.new("L", (WHEEL_SIZE, WHEEL_SIZE), 0)
    ImageDraw.Draw(m).ellipse((0, 0, WHEEL_SIZE - 1, WHEEL_SIZE - 1), fill=255)
    return m


def to_round(img: Image.Image) -> Image.Image:
    """Radbild auf den Kreis zuschneiden (ausserhalb schwarz)."""
    out = Image.new("RGB", (WHEEL_SIZE, WHEEL_SIZE), (0, 0, 0))
    out.paste(img, (0, 0), round_mask())
    return out


def vertical_gradient(width: int, height: int, color_at: Callable[[int], RGB]) -> Image.Image:
    """Bild, dessen Zeile ``y`` die Farbe ``color_at(y)`` hat."""
    img = Image.new("RGB", (width, height))
    d = ImageDraw.Draw(img)
    for y in range(height):
        d.line((0, y, width - 1, y), fill=color_at(y))
    return img


def draw_page_dots(draw: ImageDraw.ImageDraw, width: int, count: int, index: int,
                   on, off) -> None:
    """Seitenpunkte unten in der Mitte eines ``width`` breiten Displays (nur bei > 1 Seite)."""
    if count <= 1:
        return
    x0 = width / 2 - (count - 1) * PAGE_DOT_GAP / 2
    for i in range(count):
        cx = x0 + i * PAGE_DOT_GAP
        draw.rectangle((cx - 2, PAGE_DOT_Y[0], cx + 1, PAGE_DOT_Y[1]),
                       fill=on if i == index else off)
