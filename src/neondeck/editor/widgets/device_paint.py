"""Zeichnen der Geraeteansicht: Farben und Effekte aus dem aktiven Theme (abgeschraegte
Ecken, Leuchtrand, Rasterhintergrund, Scanlines); beim Theme „System“ aus der Widget-Palette.
Gezeichnet wird in Geraete-Einheiten (``device_geometry``); die Displays zeigen die Bilder
der ``DevicePreview``."""
from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPolygonF,
    QRadialGradient,
)

from ...device.layout import ControlKind, ControlRef
from ...ui import theme as themes
from ...ui.theme import Theme
from .device_geometry import (
    BODY_RADIUS,
    HEIGHT,
    SCREEN,
    WHEEL,
    WHEEL_RIM,
    WIDTH,
    button_label_area,
    control_shape,
    knob_rect,
    round_rect,
    square_rect,
    strip_rect,
    tile_rect,
)
from .device_preview import DevicePreview
from .label_fit import LabelFitter

# Effekte (Widget-Pixel bzw. Deckkraft)
GRID_PX = 40
SCANLINE_PX = 3
SCANLINE_ALPHA = 0.22
GLOW_STEPS = ((14, 0.06), (10, 0.10), (6, 0.18))   # (Strichbreite, Deckkraft)
PIN = 14                # Sticky-Kennzeichen (Geraete-Einheiten)
LABEL_PX_PER_PT = 1.15  # Beschriftung am Geraet je Punkt Oberflaechenschrift
SYSTEM_LABEL_PX = 11
NUMBER_PX = 12
KNOBS, ROUND_BUTTONS, SQUARE_BUTTONS = 6, 8, 12


@dataclass(frozen=True)
class Look:
    """Farben der Geraetezeichnung (aus dem Theme bzw. der Systempalette)."""
    body: QColor
    body_line: QColor
    screen: QColor
    screen_line: QColor
    control: QColor
    control_line: QColor
    control_inner: QColor
    control_text: QColor
    label: QColor
    empty: QColor
    selection: QColor
    indicator: QColor


def look_for(t: Theme, pal: QPalette) -> Look:
    if t.name == themes.SYSTEM:  # bisheriges Verhalten: Rollen der Widget-Palette
        R = QPalette.ColorRole
        return Look(body=pal.color(R.Mid), body_line=pal.color(R.Dark),
                    screen=pal.color(R.Shadow), screen_line=pal.color(R.Dark),
                    control=pal.color(R.Button), control_line=pal.color(R.Dark),
                    control_inner=pal.color(R.Midlight),
                    control_text=pal.color(R.ButtonText), label=pal.color(R.Text),
                    empty=pal.color(R.Mid), selection=pal.color(R.Highlight),
                    indicator=pal.color(R.ButtonText))
    return Look(body=t.color("panel"), body_line=t.color("line"),
                screen=t.solid("bg"), screen_line=t.color("accent_dim"),
                control=t.solid("bg2"), control_line=t.color("line"),
                control_inner=t.solid("panel"), control_text=t.color("text"),
                label=t.color("text_dim"), empty=t.color("line"),
                selection=t.color("accent"), indicator=t.color("accent"))


def fonts(t: Theme, widget_font: QFont) -> tuple[QFont, QFont]:
    """Schrift fuer Beschriftungen und fuer Nummern (Geraete-Einheiten)."""
    if t.name == themes.SYSTEM:
        font = QFont(widget_font)
        font.setPixelSize(SYSTEM_LABEL_PX)
        return font, font
    ui = QFont(t.font_ui)
    ui.setPixelSize(round(t.font_pt * LABEL_PX_PER_PT))  # mit der Theme-Schrift wachsen
    ui.setWeight(QFont.Weight.Medium)
    mono = QFont(t.font_mono)
    mono.setPixelSize(NUMBER_PX)
    return ui, mono


def shape(r: QRectF, round_: bool, t: Theme, radius: float, room: bool = False) -> QPainterPath:
    """Umriss eines Elements: Kreis, abgeschraegte Ecken (Cockpit) oder abgerundet.

    Abgeschraegt wird wie im Cockpit: Kacheln/Knoepfe oben links und unten rechts,
    das Gehaeuse (``room``) oben rechts und unten links.
    """
    path = QPainterPath()
    if round_:
        path.addEllipse(r)
        return path
    if t.cut_corners:
        if room:
            c = t.corner * 1.5
            points = [r.topLeft(), QPointF(r.right() - c, r.top()),
                      QPointF(r.right(), r.top() + c), r.bottomRight(),
                      QPointF(r.left() + c, r.bottom()), QPointF(r.left(), r.bottom() - c)]
        else:
            c = min(radius, r.width() / 3, r.height() / 3)
            points = [QPointF(r.left() + c, r.top()), r.topRight(),
                      QPointF(r.right(), r.bottom() - c), QPointF(r.right() - c, r.bottom()),
                      r.bottomLeft(), QPointF(r.left(), r.top() + c)]
        path.addPolygon(QPolygonF(points))
        path.closeSubpath()
        return path
    path.addRoundedRect(r, radius, radius)
    return path


def _line_width(t: Theme) -> float:
    return 2 if t.name == themes.SYSTEM else 1.5


def glow(p: QPainter, path: QPainterPath, color: QColor, strength: float = 1.0) -> None:
    """Weicher Leuchtrand: einige breiter werdende, durchscheinende Striche."""
    p.save()
    p.setBrush(Qt.BrushStyle.NoBrush)
    for width, alpha in GLOW_STEPS:
        c = QColor(color)
        c.setAlphaF(color.alphaF() * alpha * strength)
        pen = QPen(c, width)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(pen)
        p.drawPath(path)
    p.restore()


def paint_backdrop(p: QPainter, t: Theme, w: float, h: float) -> None:
    """Hintergrund wie das Cockpit: Verlauf, Neon-Dunst, feines 40-px-Raster."""
    area = QRectF(0, 0, w, h)
    base = QLinearGradient(0, 0, 0, h)
    base.setColorAt(0, t.solid("bg2"))
    base.setColorAt(1, t.solid("bg"))
    p.fillRect(area, base)
    size = max(w, h)
    for fx, fy, key, radius in ((0.18, -0.10, "accent2", 0.45), (0.92, 0.08, "accent", 0.42)):
        haze = QRadialGradient(QPointF(w * fx, h * fy), size * radius)
        haze.setColorAt(0, t.color(key, 0.16))
        haze.setColorAt(1, t.color(key, 0))
        p.fillRect(area, haze)
    center = QPointF(w * 0.5, h * 0.3)
    reach = math.hypot(w * 0.5, h * 0.7)  # bis zur fernsten Ecke
    fade = QRadialGradient(center, reach)
    fade.setColorAt(0.3, t.color("accent", 0.07))
    fade.setColorAt(0.9, t.color("accent", 0))
    p.setPen(QPen(QBrush(fade), 1))
    x = 0.5
    while x < w:
        p.drawLine(QPointF(x, 0), QPointF(x, h))
        x += GRID_PX
    y = 0.5
    while y < h:
        p.drawLine(QPointF(0, y), QPointF(w, y))
        y += GRID_PX


def paint_scanlines(p: QPainter, t: Theme, w: float, h: float) -> None:
    p.setPen(QPen(t.color("bg", SCANLINE_ALPHA), 1))
    y = 0.5
    while y < h:
        p.drawLine(QPointF(0, y), QPointF(w, y))
        y += SCANLINE_PX


@dataclass
class DevicePainter:
    """Zeichnet Gehaeuse, Displays, Regler, Tasten, Rad und Auswahl in Geraete-Einheiten
    (der Painter ist schon verschoben und skaliert)."""
    p: QPainter
    t: Theme
    look: Look
    preview: DevicePreview
    label_font: QFont
    number_font: QFont
    fitter: LabelFitter

    def paint(self, selection: list[ControlRef], simulating: bool) -> None:
        self.p.setFont(self.label_font)
        self._body()
        self._screen()
        for i in range(KNOBS):
            self._knob(knob_rect(i))
        for i in range(ROUND_BUTTONS):
            self._button(ControlRef(ControlKind.ROUND, i), round_rect(i), True)
        for i in range(SQUARE_BUTTONS):
            self._button(ControlRef(ControlKind.SQUARE, i), square_rect(i), False)
        self._wheel()
        self._selection(selection)
        if simulating:
            self._simulating_frame()

    def _body(self) -> None:
        p, t, look = self.p, self.t, self.look
        body = QRectF(1, 1, WIDTH - 2, HEIGHT - 2)
        if t.glow:
            glow(p, shape(body, False, t, BODY_RADIUS, room=True), look.selection, 0.35)
        p.setPen(QPen(look.body_line, _line_width(t)))
        p.setBrush(look.body)
        p.drawPath(shape(body, False, t, BODY_RADIUS, room=True))

    def _screen(self) -> None:
        p, t, look = self.p, self.t, self.look
        bezel = SCREEN.adjusted(-6, -6, 6, 6)
        p.setBrush(look.screen)
        if t.name == themes.SYSTEM:
            p.setPen(QPen(look.screen_line, 2))
            p.drawRect(bezel)
        else:
            p.setPen(QPen(look.screen_line, 1.5))
            p.drawPath(shape(bezel, False, t, t.corner * 0.5))
        left, right = self.preview.strips
        if left is not None:
            p.drawImage(strip_rect(0).topLeft(), left)
        if right is not None:
            p.drawImage(strip_rect(3).topLeft(), right)
        empty = QPen(look.empty, 1, Qt.PenStyle.DotLine)
        for i, img in enumerate(self.preview.tiles):
            r = tile_rect(i)
            if img is not None:
                p.drawImage(r, img)
                if self.preview.is_sticky(i):
                    self._pin(r)
            else:
                p.setPen(empty)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(r.adjusted(4, 4, -4, -4))

    def _pin(self, r: QRectF) -> None:
        """Kennzeichen einer Sticky-Kachel (gilt auf allen Seiten): Ecke unten links."""
        p = self.p
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.look.selection)
        p.drawPolygon(QPolygonF([r.bottomLeft(), QPointF(r.left(), r.bottom() - PIN),
                                 QPointF(r.left() + PIN, r.bottom())]))
        p.restore()

    def _knob(self, r: QRectF) -> None:
        p, look = self.p, self.look
        p.setPen(QPen(look.control_line, _line_width(self.t)))
        p.setBrush(look.control)
        p.drawEllipse(r)
        p.setBrush(look.control_inner)
        p.drawEllipse(r.adjusted(10, 10, -10, -10))
        c = r.center()
        pen = QPen(look.indicator, 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(c.x(), r.top() + 13), QPointF(c.x(), r.top() + 24))

    def _button(self, ref: ControlRef, r: QRectF, round_: bool) -> None:
        p, look = self.p, self.look
        p.setPen(QPen(look.control_line, _line_width(self.t)))
        p.setBrush(look.control)
        p.drawPath(shape(r, round_, self.t, 6))
        label = self.preview.control_label(ref)
        p.setPen(look.control_text)
        if round_:
            p.setFont(self.number_font)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, str(ref.index + 1))
            if label:
                p.setPen(look.label)
        if label:
            area = button_label_area(r, round_)
            font, shown = self.fitter.fit(self.label_font, area, label, wrap=not round_)
            p.setFont(font)
            p.drawText(area, Qt.AlignmentFlag.AlignCenter, shown)
        p.setFont(self.label_font)

    def _wheel(self) -> None:
        p, t, look = self.p, self.t, self.look
        rim = WHEEL.adjusted(-WHEEL_RIM, -WHEEL_RIM, WHEEL_RIM, WHEEL_RIM)
        if t.glow:
            ring = QPainterPath()
            ring.addEllipse(rim)
            glow(p, ring, look.selection, 0.5)
        p.setPen(QPen(look.control_line, _line_width(t)))
        p.setBrush(look.control)
        p.drawEllipse(rim)
        p.setPen(QPen(look.screen_line, 1) if t.name != themes.SYSTEM
                 else QPen(look.control_line, 2))
        p.setBrush(look.screen)
        p.drawEllipse(WHEEL)
        if self.preview.wheel is not None:
            path = QPainterPath()
            path.addEllipse(WHEEL)
            p.save()
            p.setClipPath(path)
            p.drawImage(WHEEL, self.preview.wheel)
            p.restore()

    def _selection(self, selection: list[ControlRef]) -> None:
        shapes = []
        for ref in selection:
            shapes.append(control_shape(ref))
            if ref.kind == ControlKind.KNOB:
                shapes.append(control_shape(ControlRef(ControlKind.STRIP, ref.index)))
        draw = self._system_mark if self.t.name == themes.SYSTEM else self._themed_mark
        for shape_rect, round_ in shapes:
            draw(shape_rect.adjusted(-3, -3, 3, 3), round_)

    def _system_mark(self, r: QRectF, round_: bool) -> None:
        self.p.setPen(QPen(self.look.selection, 4))
        self.p.setBrush(Qt.BrushStyle.NoBrush)
        if round_:
            self.p.drawEllipse(r)
        else:
            self.p.drawRect(r)

    def _themed_mark(self, r: QRectF, round_: bool) -> None:
        path = shape(r, round_, self.t, self.t.corner * 0.5)
        if self.t.glow:
            glow(self.p, path, self.look.selection)
        pen = QPen(self.look.selection, 2.5)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        self.p.setPen(pen)
        self.p.setBrush(Qt.BrushStyle.NoBrush)
        self.p.drawPath(path)

    def _simulating_frame(self) -> None:
        pen = QPen(self.t.color("accent2"), 4)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        self.p.setPen(pen)
        self.p.setBrush(Qt.BrushStyle.NoBrush)
        self.p.drawPath(shape(QRectF(3, 3, WIDTH - 6, HEIGHT - 6), False, self.t, BODY_RADIUS,
                              room=True))
