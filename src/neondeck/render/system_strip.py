"""Leistenanzeige „system“ (60 × 270): vier senkrechte Balken mit Beschriftung und Prozent.

Obere Haelfte CPU | RAM, untere Haelfte GPU 1 | GPU 2 (``core.sysload.SystemLoad.values``).

**Raster beachten:** Die Leiste hat Stege bei y = 90 und 180 (Touch-Abschnitte). Die Balken
(Grafik) laufen darueber, die Schrift nie: oben stehen Name und Wert in Abschnitt 0
(y < 90), unten in Abschnitt 2 (y ≥ 180).

``classic`` zeichnet schlicht (wie ``render_strip``), ``cockpit`` in Neon (Segmente,
Rahmen mit Verlauf Cyan → Magenta; das Lauflicht legt ``render.look`` darueber).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from PIL import Image, ImageDraw

from ..device.layout import DISPLAY_HEIGHT, STRIP_WIDTH
from ..device.layout import FIELD_SIZE as SECTION
from .draw import bevel, mix, vertical_gradient
from .palette import (
    C_BG,
    C_CYAN,
    C_CYAN_DIM,
    C_MAGENTA,
    C_YELLOW,
    ERROR,
    ERROR_HEX,
    RGB,
    TRACK_COLOR,
    VALUE_COLOR,
)
from .text import fit_font

W, H = STRIP_WIDTH, DISPLAY_HEIGHT
LABELS = ("CPU", "RAM", "GPU1", "GPU2")
COLS = (16, 44)              # Mitte der beiden Spalten
BAR_HALF = 10                # Balken: x = Mitte − 10 … Mitte + 9
TEXT_W = 26                  # Schriftbreite je Spalte (passt zwischen die Stege)
# Balken (oben, unten) je Haelfte; Text: (Name, Wert) als Mitte in y
BARS = ((34, 129), (141, 236))
TEXT_Y = ((12, 27), (258, 243))
SEGMENTS = 12
HOT = 0.8                    # ab hier gelb (Cockpit)
NONE_TEXT = "–"

Values = tuple[int | None, int | None, int | None, int | None]


def _cells(values: Values):
    """Je Balken: (Name, Wert 0–100 oder None, Spaltenmitte, Haelfte)."""
    for n, (label, value) in enumerate(zip(LABELS, values)):
        yield label, value, COLS[n % 2], n // 2


@dataclass(frozen=True)
class _TextStyle:
    label_color: RGB | str
    value_color: RGB | str
    family: str
    bold_label: bool


def _texts(d: ImageDraw.ImageDraw, label: str, value: int | None, cx: int, half: int,
           style: _TextStyle) -> None:
    ly, vy = TEXT_Y[half]
    d.text((cx, ly), label, font=fit_font(label, TEXT_W, 12, 7, style.bold_label, style.family),
           fill=style.label_color, anchor="mm")
    text = NONE_TEXT if value is None else f"{value:d}"
    d.text((cx, vy), text, font=fit_font(text, TEXT_W, 14, 7, True, style.family),
           fill=style.value_color, anchor="mm")


def _flash(d: ImageDraw.ImageDraw, flashing: tuple, color, width: int) -> None:
    for section, on in enumerate(flashing[:3]):
        if on:
            top = section * SECTION
            d.rectangle((0, top, W - 1, top + SECTION - 1), outline=color, width=width)


_CLASSIC_TEXT = _TextStyle("#ffffff", VALUE_COLOR, "Inter", True)


def classic(values: Values, flashing: tuple = (), flash_color: str = ERROR_HEX) -> Image.Image:
    """Schlicht: weisse Namen, Werte und Balken in ``VALUE_COLOR`` auf dunkler Spur."""
    img = Image.new("RGB", (W, H), "#000000")
    d = ImageDraw.Draw(img)
    d.line((6, H // 2, W - 7, H // 2), fill=TRACK_COLOR)
    for label, value, cx, half in _cells(values):
        top, bottom = BARS[half]
        x0, x1 = cx - BAR_HALF, cx + BAR_HALF - 1
        d.rectangle((x0, top, x1, bottom), fill=TRACK_COLOR)
        if value is not None and value > 0:
            h = round((bottom - top + 1) * min(100, value) / 100)
            d.rectangle((x0, bottom - h + 1, x1, bottom), fill=VALUE_COLOR)
        _texts(d, label, value, cx, half, _CLASSIC_TEXT)
    _flash(d, flashing, flash_color, 6)
    return img


@cache
def _cockpit_base() -> Image.Image:
    """Hintergrund mit zwei abgeschraegten Halbrahmen im Verlauf Cyan → Magenta (einmal je
    Prozess; nur lesen)."""
    img = Image.new("RGB", (W, H), C_BG)
    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    md.polygon(bevel(3, 2, W - 4, H // 2 - 3, 7), outline=150)
    md.polygon(bevel(3, H // 2 + 2, W - 4, H - 3, 7), outline=150)
    gradient = vertical_gradient(W, H, lambda y: mix(C_CYAN_DIM, C_MAGENTA, y / max(1, H - 1)))
    img.paste(gradient, (0, 0), mask)
    return img


def cockpit(values: Values, flashing: tuple = (), error: RGB = ERROR) -> Image.Image:
    """Neon: Segmentbalken (CPU/GPU 1 Cyan, RAM/GPU 2 Magenta, ab 80 % gelb), Werte in
    Share Tech Mono."""
    img = _cockpit_base().copy()
    d = ImageDraw.Draw(img)
    pitch = (BARS[0][1] - BARS[0][0] + 1) / SEGMENTS
    for n, (label, value, cx, half) in enumerate(_cells(values)):
        color = C_CYAN if n % 2 == 0 else C_MAGENTA
        top, bottom = BARS[half]
        lit = 0 if value is None else round(SEGMENTS * min(100, max(0, value)) / 100)
        for s in range(SEGMENTS):
            y1 = round(bottom - s * pitch)
            y0 = round(y1 - pitch + 3)
            on = s < lit
            c = (C_YELLOW if s >= SEGMENTS * HOT else color) if on else mix(C_BG, color, 0.14)
            d.rectangle((cx - BAR_HALF, y0, cx + BAR_HALF - 1, y1), fill=c)
        _texts(d, label, value, cx, half, _TextStyle(
            mix(C_BG, color, 0.7), color if value is not None else mix(C_BG, color, 0.5),
            "Share Tech Mono", False))
    _flash(d, flashing, error, 3)
    return img
