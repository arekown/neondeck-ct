"""Text zeichnen: umbrechen, Schrift verkleinern bis es passt, Zeilen und Name+Wert setzen."""
from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from PIL import Image, ImageDraw

from ..core.i18n import N_, tr
from .fonts import font

MIN_SIZE = 7
WEEKDAYS_SHORT = (N_("Mo"), N_("Di"), N_("Mi"), N_("Do"), N_("Fr"), N_("Sa"), N_("So"))
MONTHS_SHORT = (N_("JAN"), N_("FEB"), N_("MÄR"), N_("APR"), N_("MAI"), N_("JUN"), N_("JUL"),
                N_("AUG"), N_("SEP"), N_("OKT"), N_("NOV"), N_("DEZ"))


def weekday_short(weekday: int) -> str:
    """Kurzer Wochentag (``datetime.weekday()``, Montag = 0) in der Sprache der Anzeige."""
    return tr(WEEKDAYS_SHORT[weekday])


def month_short(month: int) -> str:
    """Kurzer Monat in Grossbuchstaben (``month``: 1 – 12)."""
    return tr(MONTHS_SHORT[month - 1])


class Fitted(NamedTuple):
    """Gesetzter Text: Schrift, Zeilen, Zeilenhoehe."""
    font: object
    lines: list[str]
    line_height: int

    @property
    def height(self) -> int:
        return self.line_height * len(self.lines)


@dataclass(frozen=True)
class FitSpec:
    """Platz und Schrift fuer ``fit_text``: groesste Schrift ``start`` … ``MIN_SIZE``, bei der
    der Text in ``max_lines`` Zeilen und ``max_h`` Hoehe passt; ``fixed``: genau ``start``,
    umgebrochen, was nicht in die Hoehe passt, faellt weg."""
    max_w: int
    max_h: int
    max_lines: int
    start: int
    bold: bool = False
    family: str | None = None
    fixed: bool = False


def probe() -> ImageDraw.ImageDraw:
    """Zeichenflaeche nur zum Messen von Text."""
    return ImageDraw.Draw(Image.new("L", (1, 1)))


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, max_w: int) -> list[str] | None:
    """Umbrechen an Leerzeichen; None wenn ein Wort allein nicht passt."""
    lines: list[str] = []
    cur = ""
    for word in text.split():
        if draw.textlength(word, font=fnt) > max_w:
            return None
        trial = f"{cur} {word}".strip()
        if cur and draw.textlength(trial, font=fnt) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def cut(draw: ImageDraw.ImageDraw, text: str, fnt, max_w: int) -> str:
    """``text`` zeichenweise kuerzen, bis es in ``max_w`` passt."""
    shortened = text
    while shortened and draw.textlength(shortened, font=fnt) > max_w:
        shortened = shortened[:-1]
    return shortened


def _line_height(fnt) -> int:
    return fnt.getbbox("Hg")[3] + 1


def _fixed_text(draw, text: str, spec: FitSpec) -> Fitted:
    fnt = font(max(1, spec.start), spec.bold, spec.family)
    lh = _line_height(fnt)
    lines = wrap(draw, text, fnt, spec.max_w)
    if lines is None:  # ein Wort zu breit: Woerter einzeln kuerzen
        lines = [cut(draw, w, fnt, spec.max_w) for w in text.split()]
    return Fitted(fnt, lines[:max(1, spec.max_h // lh)], lh)


def fit_text(draw: ImageDraw.ImageDraw, text: str, spec: FitSpec) -> Fitted:
    """Text nach ``spec`` setzen (groesste passende Schrift)."""
    if spec.fixed:
        return _fixed_text(draw, text, spec)
    for size in range(spec.start, MIN_SIZE - 1, -1):
        fnt = font(size, spec.bold, spec.family)
        lines = wrap(draw, text, fnt, spec.max_w)
        if lines is not None and len(lines) <= spec.max_lines:
            lh = _line_height(fnt)
            if lh * len(lines) <= spec.max_h or size <= MIN_SIZE:
                return Fitted(fnt, lines, lh)
    # Notbremse: Zeichenweise kuerzen
    fnt = font(MIN_SIZE, spec.bold, spec.family)
    return Fitted(fnt, [cut(draw, text, fnt, spec.max_w)], _line_height(fnt))


def fit_font(text: str, max_w: int, start: int, minimum: int, bold: bool, family: str):
    """Einzeilige Schrift: ab ``start`` verkleinern, bis ``text`` in ``max_w`` passt (nicht
    unter ``minimum``)."""
    d = probe()
    size = start
    while size > minimum and d.textlength(text, font=font(size, bold, family)) > max_w:
        size -= 1
    return font(size, bold, family)


def draw_lines(draw: ImageDraw.ImageDraw, fitted: Fitted, cx: float, top: float, fill,
               align: str = "center", left: float = 0, right: float = 0) -> None:
    """Zeilen ab ``top``; ``align`` center um ``cx``, left ab ``left``, right bis ``right``."""
    for i, line in enumerate(fitted.lines):
        w = draw.textlength(line, font=fitted.font)
        x = left if align == "left" else (right - w if align == "right" else cx - w / 2)
        draw.text((x, top + i * fitted.line_height), line, font=fitted.font, fill=fill)


@dataclass(frozen=True)
class NameValueStyle:
    """Aussehen von Name und Wert in einem Leistenabschnitt (``draw_name_value``)."""
    max_w: int
    name_start: int
    value_start: int
    name_color: object
    value_color: object
    name_bold: bool = False
    value_bold: bool = False
    name_family: str | None = None
    value_family: str | None = None
    name_room: tuple[int, int] = (40, 70)  # Hoehe fuer den Namen: mit Wert, allein


def draw_name_value(draw: ImageDraw.ImageDraw, top: int, name: str, value: str | None,
                    style: NameValueStyle, cx: float, section: int) -> None:
    """Name (bis 2 Zeilen) und Wert (1 Zeile) mittig in einem ``section`` hohen Abschnitt."""
    name_fit = value_fit = None
    if name and name.split():
        name_fit = fit_text(draw, name, FitSpec(
            style.max_w, style.name_room[0] if value else style.name_room[1], 2,
            style.name_start, style.name_bold, style.name_family))
    if value:
        value_fit = fit_text(draw, value, FitSpec(
            style.max_w, 22, 1, style.value_start, style.value_bold, style.value_family))
    total = (name_fit.height if name_fit else 0) + ((value_fit.line_height + 2)
                                                    if value_fit else 0)
    y = top + (section - total) // 2
    if name_fit:
        draw_lines(draw, name_fit, cx, y, style.name_color)
        y += name_fit.height + 2
    if value_fit:
        draw_lines(draw, value_fit, cx, y, style.value_color)
