"""Beschriftungen am Geraetebild in ihr Feld einpassen (verkleinern, umbrechen, kuerzen)."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QFontInfo, QFontMetricsF

MIN_LABEL_PX = 8        # kleiner wird keine Beschriftung; erst dann wird gekuerzt
FIT_CACHE_SIZE = 512


def _wrap(fm: QFontMetricsF, text: str, width: float) -> list[str]:
    """Woerter gierig auf Zeilen verteilen; eigene Zeilenumbrueche bleiben erhalten."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}" if line else word
            if line and fm.horizontalAdvance(candidate) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
    return lines


def _block_height(fm: QFontMetricsF, lines: int) -> float:
    return fm.height() + (lines - 1) * fm.lineSpacing()


def _fits(fm: QFontMetricsF, lines: list[str], area: QRectF) -> bool:
    return (all(fm.horizontalAdvance(line) <= area.width() for line in lines)
            and _block_height(fm, len(lines)) <= area.height())


def fit_label(font: QFont, area: QRectF, text: str, wrap: bool = True) -> tuple[QFont, str]:
    """Schrift und Text so, dass ``text`` in ``area`` passt.

    Beginnt bei der Theme-Groesse und verkleinert bis ``MIN_LABEL_PX``, bis jede Zeile
    (auch das laengste Wort) in die Breite und alle Zeilen in die Hoehe passen. Erst bei
    der Mindestgroesse wird gekuerzt (…), passend zur Zahl der Zeilen, die ins Feld gehen.
    Rueckgabe: Schrift und Text mit festen Zeilenumbruechen (ohne TextWordWrap zeichnen).
    """
    if not wrap:
        text = " ".join(text.split())
    width = area.width()
    fitted = QFont(font)
    px = fitted.pixelSize() if fitted.pixelSize() > 0 else QFontInfo(fitted).pixelSize()
    for size in range(max(px, MIN_LABEL_PX), MIN_LABEL_PX - 1, -1):
        fitted.setPixelSize(size)
        fm = QFontMetricsF(fitted)
        lines = _wrap(fm, text, width) if wrap else [text]
        if _fits(fm, lines, area):
            return fitted, "\n".join(lines)
    room = max(1, int((area.height() - fm.height()) // fm.lineSpacing()) + 1) if wrap else 1
    kept = lines if len(lines) <= room else lines[:room - 1] + [" ".join(lines[room - 1:])]
    elided = [fm.elidedText(line, Qt.TextElideMode.ElideRight, width) for line in kept]
    return fitted, "\n".join(elided)


class LabelFitter:
    """``fit_label`` mit Zwischenspeicher (Zeichnen fragt dieselben Texte immer wieder)."""

    def __init__(self) -> None:
        self._cache: dict[tuple, tuple[QFont, str]] = {}

    def clear(self) -> None:
        self._cache.clear()

    def fit(self, font: QFont, area: QRectF, text: str, wrap: bool) -> tuple[QFont, str]:
        key = (font.key(), text, area.width(), area.height(), wrap)
        if key not in self._cache:
            if len(self._cache) > FIT_CACHE_SIZE:
                self._cache.clear()
            self._cache[key] = fit_label(font, area, text, wrap)
        return self._cache[key]
