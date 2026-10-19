"""Leisten im Cockpit-Look: Neon-Rahmen im Verlauf, Name/Wert, Lauflicht an der Kante zur Mitte.

Die Anzeige „system“ (``render.system_strip``) bekommt dasselbe Lauflicht. Schrift bleibt im
Leistenabschnitt (Stege bei y = 90 und 180); Grafik darf durchlaufen.
"""
from __future__ import annotations

import math
from functools import cache

from PIL import Image, ImageDraw

from ...device.layout import DISPLAY_HEIGHT as STRIP_H
from ...device.layout import FIELD_SIZE as TILE
from ...device.layout import STRIP_WIDTH as STRIP_W
from .. import system_strip
from ..draw import bevel, mix, vertical_gradient
from ..palette import C_BG, C_CYAN, C_MAGENTA, ERROR
from ..text import FitSpec, NameValueStyle, draw_lines, draw_name_value, fit_text
from .timing import slow_step

CHASE_SEGMENTS = 9      # Leisten-Lauflicht: drei Stuecke je Abschnitt
STRIP_TEXT_W = 48       # Leistenschrift: Breite (x 6–54, im Rahmen)
BAR_SEGMENTS = 8
_TEXT = NameValueStyle(
    max_w=STRIP_TEXT_W, name_start=15, value_start=16, name_color=C_CYAN, value_color=C_MAGENTA,
    name_bold=True, name_family="Rajdhani", value_family="Share Tech Mono", name_room=(40, 66))


@cache
def _frame_gradient() -> Image.Image:
    """Senkrechter Verlauf Cyan → Magenta → Cyan fuer die Abschnittsrahmen (nur lesen)."""
    def color(y: int):
        k = 0.5 - 0.5 * math.cos(2 * math.pi * y / STRIP_H)
        return mix(C_BG, mix(C_CYAN, C_MAGENTA, k), 0.7)
    return vertical_gradient(STRIP_W, STRIP_H, color)


def _bar(d: ImageDraw.ImageDraw, top: int, name: str, pct: float) -> None:
    """Name ueber einem Segmentbalken (Cyan → Magenta)."""
    bar_y = top + 60
    if name:
        fitted = fit_text(d, name, FitSpec(STRIP_TEXT_W, 44, 2, 15, True, "Rajdhani"))
        draw_lines(d, fitted, STRIP_W / 2, top + 8 + (50 - fitted.height) // 2, C_CYAN)
    lit = round(BAR_SEGMENTS * min(100.0, max(0.0, pct)) / 100)
    w = STRIP_TEXT_W // BAR_SEGMENTS
    for s in range(BAR_SEGMENTS):
        x0 = 6 + s * w
        color = mix(C_CYAN, C_MAGENTA, s / (BAR_SEGMENTS - 1)) if s < lit \
            else mix(C_BG, C_CYAN, 0.15)
        d.rectangle((x0, bar_y, x0 + w - 2, bar_y + 11), fill=color)


def _base(sections, flashing, pressed=()) -> Image.Image:
    img = Image.new("RGB", (STRIP_W, STRIP_H), C_BG)
    d = ImageDraw.Draw(img)
    frames = Image.new("L", (STRIP_W, STRIP_H), 0)
    fd = ImageDraw.Draw(frames)
    marked = []
    for i, (name, value, bar) in enumerate(sections[:3]):
        top = i * TILE
        pts = bevel(4, top + 4, STRIP_W - 5, top + TILE - 5, 8)
        failed = i < len(flashing) and flashing[i]
        touched = i < len(pressed) and pressed[i]
        accent = ERROR if failed else C_MAGENTA if touched else None
        if accent is not None:
            d.polygon(pts, fill=mix(C_BG, accent, 0.3))
            marked.append((pts, accent))
        else:
            fd.polygon(pts, outline=255)
        if bar is not None:
            _bar(d, top, name, bar)
        else:
            draw_name_value(d, top, name, value, _TEXT, STRIP_W / 2, TILE)
    img.paste(_frame_gradient(), (0, 0), frames)
    for pts, accent in marked:
        d.polygon(pts, outline=accent, width=3 if accent == ERROR else 2)
    return img


def _chaser(d: ImageDraw.ImageDraw, step: int, edge: str) -> None:
    """Neon-Lauflicht an der Kante zur Mitte: Kopf Magenta, Schweif Cyan."""
    x = STRIP_W - 2 if edge == "right" else 0
    seg = STRIP_H // CHASE_SEGMENTS
    head = step % CHASE_SEGMENTS
    for s in range(CHASE_SEGMENTS):
        behind = (head - s) % CHASE_SEGMENTS
        color = C_MAGENTA if behind == 0 else mix(C_BG, C_CYAN, {1: 0.85, 2: 0.45}.get(behind, 0.12))
        y0 = s * seg + 2
        d.rectangle((x, y0, x + 1, y0 + seg - 5), fill=color)


class StripRenderer:
    """Zeichnet beide Leisten; das Grundbild je Kante bleibt, solange sich der Inhalt nicht
    aendert (nur das Lauflicht kommt je Bild dazu). Nur im Engine-Thread benutzen."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[tuple, Image.Image]] = {}

    def _base(self, edge: str, key: tuple, build) -> Image.Image:
        cached = self._cache.get(edge)
        if cached is None or cached[0] != key:
            cached = self._cache[edge] = (key, build())
        return cached[1]

    def strip(self, sections: list[tuple[str, str | None, float | None]],
              flashing: tuple, frame: int, edge: str, pressed: tuple = ()) -> Image.Image:
        """Eine Leiste (60 × 270, drei Abschnitte aus ``screens.strip_section``);
        ``edge`` ``"right"`` (linke Leiste) oder ``"left"``: Kante zur Mitte mit Lauflicht;
        ``pressed``: beruehrte Abschnitte (Magenta)."""
        key = ("knobs", tuple(sections), tuple(flashing), tuple(pressed))
        img = self._base(edge, key, lambda: _base(sections, flashing, pressed)).copy()
        _chaser(ImageDraw.Draw(img), slow_step(frame), edge)
        return img

    def system(self, values: system_strip.Values, flashing: tuple, frame: int,
               edge: str) -> Image.Image:
        """Leiste „system“ (CPU, RAM, GPU 1, GPU 2) im Neon-Stil mit Lauflicht."""
        key = ("system", tuple(values), tuple(flashing))
        img = self._base(edge, key, lambda: system_strip.cockpit(values, flashing, ERROR)).copy()
        _chaser(ImageDraw.Draw(img), slow_step(frame), edge)
        return img
