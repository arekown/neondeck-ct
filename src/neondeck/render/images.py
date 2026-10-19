"""Zeichnen der Tasten-, Seiten-, Leisten- und Radbilder (reines Pillow; Symbole laden:
``render.icons``)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from PIL import Image, ImageDraw

from ..core.i18n import tr
from ..core.values import MUTED_MESSAGE
from ..device.layout import CENTER_WIDTH, DISPLAY_HEIGHT, STRIP_WIDTH, TOUCH_BUTTONS, WHEEL_SIZE
from ..device.layout import FIELD_SIZE as TILE
from ..profile.model import ALIGN_H, ALIGN_V, LAYOUTS
from .draw import draw_page_dots
from .palette import (
    BACK_COLOR,
    BADGE_COLOR,
    MUTED_COLOR,
    TRACK_COLOR,
    VALUE_COLOR,
)
from .text import FitSpec, NameValueStyle, draw_lines, draw_name_value, fit_text

__all__ = [
    "TILE", "WHEEL_TILE", "FLASH_WIDTH", "TileSpec", "back_arrow", "compose_center",
    "render_strip", "render_tile", "render_wheel", "tint", "to_rgb565",
    "wheel_tile",
]

FLASH_WIDTH = 6
TEXT_MARGIN = 4
ICON_TEXT_GAP = 2
BADGE = 16                 # Ordner-Kennzeichen: Eckdreieck oben rechts
STRIP_BAR_X0, STRIP_BAR_X1 = 6, 54   # Leisten-Balken: waagrecht, im Abschnitt unten
STRIP_BAR_Y, STRIP_BAR_H = 62, 10
WHEEL_TILE = 170                     # Rad-Bild: Quadrat im runden Display (240 / √2)
WHEEL_ARC_R, WHEEL_ARC_W = 108, 14   # Rad-Bogen: Aussenradius und Breite
WHEEL_ARC_START, WHEEL_ARC_SWEEP = 135, 270  # Grad (PIL: 0 = 3 Uhr, im Uhrzeigersinn)
TEXT_START = 15      # Startgroesse der Schrift auf einer 90er-Kachel (wird kleiner, bis es passt)
BIG_TEXT_START = 30  # Layout „grosser Text“


@dataclass
class TileSpec:
    bg: str = "#000000"
    icon: Image.Image | None = None
    text: str = ""
    text_color: str = "#ffffff"
    value: str | None = None
    flash: str | None = None
    badge: str | None = None  # "folder": Taste oeffnet einen Ordner
    layout: str = "auto"         # LAYOUTS: Symbol und/oder Text, grosser Text
    font: str | None = None   # Familie aus ``fonts.FAMILIES`` (None: Noto Sans)
    font_size: int | None = None  # feste Groesse in Pixeln (None: so gross, wie es passt)
    align_h: str = "center"
    align_v: str = "center"
    icon_color: str | None = None  # Symbol in dieser Farbe einfaerben

    def key(self, icon_ref) -> tuple:
        """Alles, was das Bild bestimmt; das Symbol als ``icon_ref`` (Bilder sind nicht
        vergleichbar)."""
        return (self.bg, icon_ref, self.text, self.text_color, self.value, self.flash,
                self.badge, self.layout, self.font, self.font_size, self.align_h, self.align_v,
                self.icon_color)


def to_rgb565(img: Image.Image, big_endian: bool = False) -> bytes:
    a = np.asarray(img.convert("RGB"), dtype=np.uint16)
    v = ((a[..., 0] & 0xF8) << 8) | ((a[..., 1] & 0xFC) << 3) | (a[..., 2] >> 3)
    return v.astype(">u2" if big_endian else "<u2").tobytes()


def tint(icon: Image.Image, color: str) -> Image.Image:
    """Symbol einfarbig in ``color`` (Form aus dem Alphakanal)."""
    rgba = icon.convert("RGBA")
    solid = Image.new("RGBA", rgba.size, color)
    solid.putalpha(rgba.getchannel("A"))
    return solid


def _fit_block(draw: ImageDraw.ImageDraw, spec: TileSpec, text: str, layout: str,
               has_icon: bool, size: int):
    """Textblock der Taste (``text.Fitted``); ohne Text ``None``."""
    if not text:
        return None
    big = layout == "big_text"
    avail_h = int(size * (0.62 if has_icon else (0.9 if big else 0.8)))
    start = spec.font_size or max(7, round((BIG_TEXT_START if big else TEXT_START)
                                           * size / TILE))  # waechst mit (Rad 240 px)
    return fit_text(draw, text, FitSpec(size - 2 * TEXT_MARGIN, avail_h, 3 if big else 2, start,
                                        family=spec.font, fixed=spec.font_size is not None))


def _place_icon(img: Image.Image, spec: TileSpec, text_h: int, align_v: str) -> int | None:
    """Symbol aufs Bild setzen; liefert den oberen Rand des Textblocks (``None``: kein Text)."""
    size, margin = img.width, TEXT_MARGIN
    if text_h:  # Symbol + Abstand + Textblock + Raender muessen uebereinander passen
        max_icon = max(1, min(int(size * 0.6), size - text_h - 2 * margin - ICON_TEXT_GAP))
    else:
        max_icon = int(size * 0.8)
    icon = spec.icon.copy()
    icon.thumbnail((max_icon, max_icon), Image.LANCZOS)
    if spec.icon_color:
        icon = tint(icon, spec.icon_color)
    text_top = None
    if text_h and align_v == "top":  # Text oben, Symbol darunter
        text_top = margin
        area_top = margin + text_h + ICON_TEXT_GAP
        y = area_top + max(0, (size - margin - area_top - icon.height) // 2)
    elif text_h:
        y = max(margin, ((size - text_h - margin) - icon.height) // 2)
        text_top = size - margin - text_h
    else:
        y = (size - icon.height) // 2
    rgba = icon.convert("RGBA")
    img.paste(rgba, ((size - icon.width) // 2, y), rgba)
    return text_top


def render_tile(spec: TileSpec, size: int = TILE) -> Image.Image:
    """Tastenbild: Symbol und/oder Text nach ``spec.layout``, Schrift, Groesse und
    Ausrichtung aus ``spec``. ``auto``: Symbol oben, Text unten (oder eines allein)."""
    img = Image.new("RGB", (size, size), spec.bg)
    draw = ImageDraw.Draw(img)
    margin = TEXT_MARGIN
    layout = spec.layout if spec.layout in LAYOUTS else "auto"
    align_h = spec.align_h if spec.align_h in ALIGN_H else "center"
    align_v = spec.align_v if spec.align_v in ALIGN_V else "center"
    has_icon = spec.icon is not None and layout not in ("text", "big_text")
    text = "" if layout == "icon" else " ".join(x for x in (spec.text.strip(), spec.value) if x)

    block = _fit_block(draw, spec, text, layout, has_icon, size)
    text_h = block.height if block else 0
    if has_icon:
        text_top = _place_icon(img, spec, text_h, align_v)
    else:
        text_top = {"top": margin, "bottom": size - margin - text_h}.get(
            align_v, (size - text_h) // 2)
    if block:
        draw_lines(draw, block, size / 2, text_top, spec.text_color, align_h, margin,
                   size - margin)
    if spec.badge == "folder":
        draw.polygon([(size - BADGE, 0), (size - 1, 0), (size - 1, BADGE - 1)], fill=BADGE_COLOR)
    if spec.flash:
        draw.rectangle((0, 0, size - 1, size - 1), outline=spec.flash, width=FLASH_WIDTH)
    return img


def back_arrow(size: int = TILE) -> Image.Image:
    """Pfeil nach links (Symbol der „Zurück“-Kachel im Ordner), RGBA size x size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    c, r = size / 2, size * 0.36
    shaft = size * 0.08
    draw.polygon([(c - r, c), (c - r * 0.1, c - r * 0.8), (c - r * 0.1, c + r * 0.8)],
                 fill=BACK_COLOR)
    draw.rectangle((c - r * 0.2, c - shaft, c + r, c + shaft), fill=BACK_COLOR)
    return img


def compose_center(tiles: list[Image.Image | None], page_index: int, page_count: int) -> Image.Image:
    img = Image.new("RGB", (CENTER_WIDTH, DISPLAY_HEIGHT), "#000000")
    for i, tile in enumerate(tiles[:TOUCH_BUTTONS]):
        if tile is not None:
            img.paste(tile.convert("RGB"), ((i % 4) * TILE, (i // 4) * TILE))
    draw_page_dots(ImageDraw.Draw(img), CENTER_WIDTH, page_count, page_index, "#ffffff",
                   "#555555")
    return img


# --- Seitenleisten -------------------------------------------------------

_STRIP_TEXT = NameValueStyle(max_w=54, name_start=13, value_start=16, name_color="#ffffff",
                             value_color=VALUE_COLOR, value_bold=True)
STRIP_CENTER_X = STRIP_WIDTH // 2


def render_strip(labels: list[tuple[str, str | None]],
                 bars: list[float | None] | None = None) -> Image.Image:
    """Drei Abschnitte (Name, Wert); ist ``bars[i]`` gesetzt (0–100), zeigt Abschnitt ``i``
    Name und Balken statt des Werts."""
    img = Image.new("RGB", (STRIP_WIDTH, DISPLAY_HEIGHT), "#000000")
    draw = ImageDraw.Draw(img)
    for i, (name, value) in enumerate(labels[:3]):
        top = i * TILE
        if i:
            draw.line((6, top, 53, top), fill=TRACK_COLOR)
        bar = bars[i] if bars and i < len(bars) else None
        if bar is not None:
            _strip_bar(draw, top, name, bar)
        else:
            draw_name_value(draw, top, name, value, _STRIP_TEXT, STRIP_CENTER_X, TILE)
    return img


def _strip_bar(draw: ImageDraw.ImageDraw, top: int, name: str, pct: float) -> None:
    """Name ueber dem Balken, Balken an fester Stelle (``STRIP_BAR_*``)."""
    if name:
        name_fit = fit_text(draw, name, FitSpec(54, STRIP_BAR_Y - 8, 2, 13))
        draw_lines(draw, name_fit, STRIP_CENTER_X,
                   top + (STRIP_BAR_Y - name_fit.height) // 2, "#ffffff")
    y0, y1 = top + STRIP_BAR_Y, top + STRIP_BAR_Y + STRIP_BAR_H - 1
    draw.rectangle((STRIP_BAR_X0, y0, STRIP_BAR_X1 - 1, y1), fill=TRACK_COLOR)
    w = round((STRIP_BAR_X1 - STRIP_BAR_X0) * min(100.0, max(0.0, pct)) / 100)
    if w > 0:
        draw.rectangle((STRIP_BAR_X0, y0, STRIP_BAR_X0 + w - 1, y1), fill=VALUE_COLOR)


# --- Rad -----------------------------------------------------------------

def _wheel_clock(draw: ImageDraw.ImageDraw, now: datetime) -> None:
    c = WHEEL_SIZE // 2

    def pt(angle_deg: float, r: float):
        a = math.radians(angle_deg)
        return c + r * math.sin(a), c - r * math.cos(a)

    draw.ellipse((6, 6, 233, 233), outline="#444444", width=2)
    for k in range(12):
        draw.line((*pt(k * 30, 100 if k % 3 else 92), *pt(k * 30, 108)),
                  fill="#cccccc", width=4 if k % 3 == 0 else 2)
    hour = (now.hour % 12 + now.minute / 60) * 30
    minute = (now.minute + now.second / 60) * 6
    draw.line((c, c, *pt(hour, 62)), fill="#ffffff", width=7)
    draw.line((c, c, *pt(minute, 90)), fill="#ffffff", width=4)
    draw.ellipse((c - 6, c - 6, c + 6, c + 6), fill="#ffffff")


def render_wheel(mode: str, label: str = "", now: datetime | None = None, *,
                 value: float | None = None,
                 image: Image.Image | None = None, muted: bool = False) -> Image.Image:
    """Raddisplay: ``clock``, ``label`` (Text), ``arc`` (``value`` 0–100 als Bogen + Zahl,
    darunter ``label``; ``muted``: Bogen grau, darunter „stumm“), ``image`` (fertiges 240er-Bild,
    z. B. ``wheel_tile(spec)``), sonst schwarz."""
    img = Image.new("RGB", (WHEEL_SIZE, WHEEL_SIZE), "#000000")
    draw = ImageDraw.Draw(img)
    if mode == "image":
        if image is not None:
            src = image.convert("RGB")
            img.paste(src if src.size == img.size else src.resize(img.size, Image.LANCZOS))
    elif mode == "arc":
        _wheel_arc(draw, value, label, muted)
    elif mode == "clock":
        _wheel_clock(draw, now or datetime.now())
    elif mode == "label" and label.strip():
        fitted = fit_text(draw, label, FitSpec(200, 180, 4, 40, bold=True))
        c = WHEEL_SIZE // 2
        draw_lines(draw, fitted, c, c - fitted.height / 2, "#ffffff")
    return img


def _wheel_arc(draw: ImageDraw.ImageDraw, value: float | None, label: str,
               muted: bool = False) -> None:
    c, r = WHEEL_SIZE // 2, WHEEL_ARC_R
    box = (c - r, c - r, c + r, c + r)
    end = WHEEL_ARC_START + WHEEL_ARC_SWEEP
    draw.arc(box, WHEEL_ARC_START, end, fill=TRACK_COLOR, width=WHEEL_ARC_W)
    if value is not None:
        pct = min(100.0, max(0.0, value))
        if pct > 0:
            draw.arc(box, WHEEL_ARC_START, WHEEL_ARC_START + WHEEL_ARC_SWEEP * pct / 100,
                     fill=MUTED_COLOR if muted else VALUE_COLOR, width=WHEEL_ARC_W)
    text = f"{round(value)} %" if value is not None else "–"
    big = fit_text(draw, text, FitSpec(150, 70, 1, 52, bold=True))
    draw_lines(draw, big, c, c - big.line_height * 0.6, MUTED_COLOR if muted else "#ffffff")
    if muted:
        label = tr(MUTED_MESSAGE)
    if label.strip():
        small = fit_text(draw, label, FitSpec(140, 50, 2, 22))
        draw_lines(draw, small, c, c + big.line_height * 0.55, "#aaaaaa")


def wheel_tile(spec: TileSpec) -> Image.Image:
    """Tastenbild fuers runde Raddisplay: ``render_tile`` im einbeschriebenen Quadrat
    (``WHEEL_TILE``), damit Text und Symbol nicht am Rand abgeschnitten werden; der Rest
    in der Hintergrundfarbe."""
    img = Image.new("RGB", (WHEEL_SIZE, WHEEL_SIZE), spec.bg)
    off = (WHEEL_SIZE - WHEEL_TILE) // 2
    img.paste(render_tile(spec, WHEEL_TILE), (off, off))
    return img
