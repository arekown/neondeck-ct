"""Geometrie der Geraetezeichnung in Geraete-Einheiten (1 = 1 Display-Pixel), ohne Widget."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF

from ...device.layout import (
    DISPLAY_HEIGHT,
    STRIP_WIDTH,
    SURFACE_WIDTH,
    WHEEL_SIZE,
    ControlKind,
    ControlRef,
    all_controls,
)
from ...render.images import TILE

WIDTH, HEIGHT = 740, 650
SCREEN = QRectF(130, 20, SURFACE_WIDTH, DISPLAY_HEIGHT)  # linke Leiste | 4x3 Kacheln | rechte
STRIP_W = STRIP_WIDTH
KNOB_D = 66
KNOB_X = (75, 665)                          # Mitte der Reglerspalten links/rechts
ROUND_D = 44
ROUND_Y = 335
ROUND_X0, ROUND_X1 = 75, 665
WHEEL = QRectF(250, 390, WHEEL_SIZE, WHEEL_SIZE)  # rundes Display
WHEEL_RIM = 10
SQUARE = 58
SQUARE_GAP = 14
SQUARE_LEFT_X = 92                          # linker Block, rechter Block spiegelbildlich
SQUARE_RIGHT_X = 518
SQUARE_Y = 409                              # Bloecke mittig neben dem Rad
BODY_RADIUS = 28
ROUND_LABEL_W, ROUND_LABEL_H = 80, 16      # Beschriftung unter runden Tasten
LABEL_INSET = 4                             # Beschriftung in eckigen Tasten

ALL_CONTROLS = all_controls()


def tile_rect(index: int) -> QRectF:
    return QRectF(SCREEN.x() + STRIP_W + (index % 4) * TILE, SCREEN.y() + (index // 4) * TILE,
                  TILE, TILE)


def strip_rect(index: int) -> QRectF:
    """Abschnitt ``index`` (0-2 links, 3-5 rechts) der Leisten."""
    x = SCREEN.x() if index < 3 else SCREEN.right() - STRIP_W
    return QRectF(x, SCREEN.y() + (index % 3) * TILE, STRIP_W, TILE)


def knob_rect(index: int) -> QRectF:
    cx = KNOB_X[0 if index < 3 else 1]
    cy = SCREEN.y() + (index % 3) * TILE + TILE / 2
    return QRectF(cx - KNOB_D / 2, cy - KNOB_D / 2, KNOB_D, KNOB_D)


def round_rect(index: int) -> QRectF:
    cx = ROUND_X0 + index * (ROUND_X1 - ROUND_X0) / 7
    return QRectF(cx - ROUND_D / 2, ROUND_Y - ROUND_D / 2, ROUND_D, ROUND_D)


def square_rect(index: int) -> QRectF:
    block, pos = divmod(index, 6)
    row, col = divmod(pos, 2)
    x0 = SQUARE_LEFT_X if block == 0 else SQUARE_RIGHT_X
    return QRectF(x0 + col * (SQUARE + SQUARE_GAP), SQUARE_Y + row * (SQUARE + SQUARE_GAP),
                  SQUARE, SQUARE)


# Art -> (Rechteck je Nummer, rund?)
_SHAPES = {ControlKind.TOUCH: (tile_rect, False), ControlKind.STRIP: (strip_rect, False),
           ControlKind.KNOB: (knob_rect, True), ControlKind.ROUND: (round_rect, True),
           ControlKind.SQUARE: (square_rect, False)}


def control_shape(ref: ControlRef) -> tuple[QRectF, bool]:
    """Rechteck in Geraete-Einheiten und ob das Element rund ist."""
    if ref.kind in _SHAPES:
        rect, round_ = _SHAPES[ref.kind]
        return rect(ref.index), round_
    return QRectF(WHEEL), True


def control_at(p: QPointF) -> ControlRef | None:
    """Element unter dem Punkt ``p`` (Geraete-Einheiten)."""
    for ref in ALL_CONTROLS:
        r, round_ = control_shape(ref)
        if round_:
            c = r.center()
            if (p.x() - c.x()) ** 2 + (p.y() - c.y()) ** 2 <= (r.width() / 2) ** 2:
                return ref
        elif r.contains(p):
            return ref
    return None


def knob_target(ref: ControlRef) -> ControlRef:
    """Leistenabschnitt -> sein Regler (belegt und gewaehlt wird der Regler)."""
    return ControlRef(ControlKind.KNOB, ref.index) if ref.kind == ControlKind.STRIP else ref


def button_label_area(r: QRectF, round_: bool) -> QRectF:
    """Feld fuer die Beschriftung einer Taste: unter runden Tasten, in eckigen Tasten."""
    if round_:
        return QRectF(r.center().x() - ROUND_LABEL_W / 2, r.bottom() + 3, ROUND_LABEL_W,
                      ROUND_LABEL_H)
    return r.adjusted(LABEL_INSET, LABEL_INSET, -LABEL_INSET, -LABEL_INSET)
