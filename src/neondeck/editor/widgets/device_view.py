"""Massstaebliche Zeichnung des Loupedeck CT zum Anklicken und Belegen.

Das Widget behaelt Auswahl, Maus, Tooltip und Ziehen & Ablegen; Geometrie steht in
``device_geometry``, die Bilder der Displays in ``device_preview`` (gezeichnet wie am Geraet),
das Zeichnen mit Theme-Farben und -Effekten in ``device_paint``.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QMimeData, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QDrag, QFont, QPainter
from PySide6.QtWidgets import QApplication, QSizePolicy, QToolTip, QWidget

from ...core.i18n import tr
from ...device.layout import ControlRef
from ...profile.model import Profile, TouchPage, Workspace
from ...ui import theme as themes
from ..editing.file_drop import local_paths
from ..editing.mime import ACTION_MIME, CONTROLS_MIME, get_json, put_json
from . import device_geometry as geo
from .device_paint import DevicePainter, fonts, look_for, paint_backdrop, paint_scanlines
from .device_preview import DevicePreview, IconLoader
from .label_fit import LabelFitter
from .labels import ref_name

log = logging.getLogger(__name__)


def parse_controls(mime) -> list[ControlRef]:
    """Quellen eines Ziehens zwischen Elementen (ungueltige Eintraege fallen weg)."""
    try:
        raw = get_json(mime, CONTROLS_MIME)
    except ValueError:
        return []
    refs = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, list) and len(item) == 2 and isinstance(item[1], int):
            ref = ControlRef(str(item[0]), item[1])
            if ref in geo.ALL_CONTROLS:
                refs.append(ref)
    return refs


def parse_action(mime) -> dict | None:
    """Abgelegte Aktionsvorlage aus der Bibliothek (``None``: keine oder ungueltig)."""
    if not mime.hasFormat(ACTION_MIME):
        return None
    try:
        action = get_json(mime, ACTION_MIME)
    except ValueError:
        log.warning("Abgelegte Aktion ist kein gueltiges JSON")
        return None
    if not isinstance(action, dict) or not isinstance(action.get("type"), str):
        return None
    return action


def drop_payload(mime) -> tuple[str, object] | None:
    """Was abgelegt wird: ``("controls", Quellen)`` (Ziehen zwischen Elementen),
    ``("files", Pfade)`` (Dateimanager) oder ``("action", Vorlage)`` (Bibliothek); ``None``:
    nichts Brauchbares."""
    if mime.hasFormat(CONTROLS_MIME):
        refs = parse_controls(mime)
        return ("controls", refs) if refs else None
    if mime.hasUrls() and not mime.hasFormat(ACTION_MIME):
        paths = local_paths(mime.urls())
        return ("files", paths) if paths else None
    action = parse_action(mime)
    return ("action", action) if action is not None else None


def _drop_action(event) -> Qt.DropAction:
    copy = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
    return Qt.DropAction.CopyAction if copy else Qt.DropAction.MoveAction


class DeviceView(QWidget):
    """Klick waehlt ein Element (``selected``), Strg-Klick mehrere (``selection_changed``);
    Ablegen einer Aktion (``action_dropped``); Ziehen zwischen Elementen
    (``controls_dropped``: Quellen, Ziel, kopieren?); Rechtsklick (``context_requested``)."""

    selected = Signal(object)              # ControlRef; Leistenabschnitt -> Regler
    selection_changed = Signal(list)       # alle gewaehlten ControlRefs, zuletzt gewaehlt hinten
    action_dropped = Signal(object, dict)  # ControlRef, Aktion
    controls_dropped = Signal(list, object, bool)  # Quellen, Ziel, kopieren (Strg)
    files_dropped = Signal(object, list)   # ControlRef, lokale Pfade (Dateimanager)
    context_requested = Signal(object, object)     # ControlRef, globale Position (QPoint)

    def __init__(self, icon_loader: IconLoader | None = None, parent=None):
        super().__init__(parent)
        self.preview = DevicePreview(icon_loader)
        self._selection: list[ControlRef] = []
        self._press: tuple[ControlRef, QPointF] | None = None  # Beginn eines Ziehens
        self._simulating = False  # Modus „Simulieren“: Rahmen in der Akzentfarbe
        self._fitter = LabelFitter()
        self.setAcceptDrops(True)
        self.setMouseTracking(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(geo.WIDTH // 2, geo.HEIGHT // 2)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        themes.notifier.changed.connect(self._theme_changed)

    def sizeHint(self) -> QSize:
        return QSize(geo.WIDTH, geo.HEIGHT)

    # --- Inhalt und Auswahl ------------------------------------------------------------

    def set_view(self, profile: Profile | None, workspace: Workspace | None,
                 page: TouchPage | None) -> None:
        self.preview.set_view(profile, workspace, page)
        self.update()

    def refresh(self) -> None:
        """Bilder neu berechnen (nach jeder Aenderung am Profil)."""
        self.preview.refresh()
        self.update()

    def set_selection(self, ref) -> None:
        """Ein Element, eine Liste oder ``None``."""
        refs = [] if ref is None else (list(ref) if isinstance(ref, (list, tuple)) else [ref])
        self._selection = [geo.knob_target(r) for r in refs]
        self.update()

    def selection(self) -> list[ControlRef]:
        return list(self._selection)

    @property
    def simulating(self) -> bool:
        return self._simulating

    def set_simulating(self, on: bool) -> None:
        """Modus „Simulieren“ deutlich zeigen (Rahmen in ``accent2`` des Themes)."""
        self._simulating = on
        self.update()

    # --- Koordinaten -------------------------------------------------------------------

    def _scale(self) -> tuple[float, float, float]:
        s = min(self.width() / geo.WIDTH, self.height() / geo.HEIGHT)
        return s, (self.width() - geo.WIDTH * s) / 2, (self.height() - geo.HEIGHT * s) / 2

    def control_rect(self, ref: ControlRef) -> QRect:
        """Rechteck eines Elements in Widget-Koordinaten."""
        s, dx, dy = self._scale()
        r, _ = geo.control_shape(ref)
        return QRectF(dx + r.x() * s, dy + r.y() * s, r.width() * s, r.height() * s).toRect()

    def device_pos(self, pos: QPointF) -> QPointF:
        """Widget-Koordinaten -> Geraete-Einheiten (1 = 1 Display-Pixel)."""
        s, dx, dy = self._scale()
        s = s or 1.0
        return QPointF((pos.x() - dx) / s, (pos.y() - dy) / s)

    def control_at(self, pos: QPointF) -> ControlRef | None:
        if self._scale()[0] <= 0:
            return None
        return geo.control_at(self.device_pos(pos))

    # --- Maus, Tooltip -------------------------------------------------------------------

    def _choose(self, refs: list[ControlRef], current: ControlRef | None) -> None:
        self.set_selection(refs)
        self.selection_changed.emit(self.selection())
        if current is not None:
            self.selected.emit(current)

    def mousePressEvent(self, event) -> None:
        ref = self.control_at(event.position())
        if event.button() != Qt.MouseButton.LeftButton or ref is None:
            super().mousePressEvent(event)
            return
        ref = geo.knob_target(ref)
        self._press = (ref, event.position())
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            refs = [r for r in self._selection if r != ref]
            if len(refs) == len(self._selection):
                refs.append(ref)  # dazu
            self._choose(refs, refs[-1] if refs else None)
            return
        keep = ref in self._selection and len(self._selection) > 1
        self._choose(self._selection if keep else [ref], ref)

    def mouseReleaseEvent(self, event) -> None:
        press, self._press = self._press, None
        if press is not None and not event.modifiers() & Qt.KeyboardModifier.ControlModifier \
                and len(self._selection) > 1 and press[0] in self._selection:
            self._choose([press[0]], None)  # Klick ohne Ziehen in eine Mehrfachauswahl
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event) -> None:
        press = self._press
        if press is None or not event.buttons() & Qt.MouseButton.LeftButton:
            return
        if (event.position() - press[1]).manhattanLength() < QApplication.startDragDistance():
            return
        self._press = None
        ref = press[0]
        self.start_drag(self._selection if ref in self._selection else [ref])

    def drag_mime(self, refs: list[ControlRef]) -> QMimeData:
        return put_json(QMimeData(), CONTROLS_MIME, [[r.kind, r.index] for r in refs])

    def start_drag(self, refs: list[ControlRef]) -> None:
        drag = QDrag(self)
        drag.setMimeData(self.drag_mime(refs))
        drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction, Qt.DropAction.MoveAction)

    def contextMenuEvent(self, event) -> None:
        ref = self.control_at(QPointF(event.pos()))
        if ref is None:
            return
        ref = geo.knob_target(ref)
        if ref not in self._selection:
            self._choose([ref], ref)
        self.context_requested.emit(ref, event.globalPos())

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            ref = self.control_at(QPointF(event.pos()))
            if ref is None:
                QToolTip.hideText()
                event.ignore()
                return True
            label = self.preview.control_label(ref)
            QToolTip.showText(event.globalPos(),
                              ref_name(ref) + (f": {label}" if label else tr(" (frei)")), self)
            return True
        return super().event(event)

    # --- Ablegen -------------------------------------------------------------------------

    def _accept_drag(self, event) -> None:
        mime = event.mimeData()
        if mime.hasFormat(CONTROLS_MIME):
            event.setDropAction(_drop_action(event))
            event.accept()
        elif mime.hasFormat(ACTION_MIME) or mime.hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragEnterEvent(self, event) -> None:
        self._accept_drag(event)

    def dragMoveEvent(self, event) -> None:
        if not self.control_at(event.position()):
            event.ignore()
        else:
            self._accept_drag(event)

    def dropEvent(self, event) -> None:
        ref = self.control_at(event.position())
        payload = drop_payload(event.mimeData()) if ref is not None else None
        if payload is None:
            event.ignore()
            return
        kind, data = payload
        target = geo.knob_target(ref)
        if kind == "controls":
            action = _drop_action(event)
            event.setDropAction(action)
            event.accept()
            self.controls_dropped.emit(data, target, action == Qt.DropAction.CopyAction)
            return
        event.acceptProposedAction()
        (self.files_dropped if kind == "files" else self.action_dropped).emit(target, data)

    # --- Zeichnen -----------------------------------------------------------------------

    def _theme_changed(self, _theme) -> None:
        self._fitter.clear()
        self.update()

    def paintEvent(self, event) -> None:
        t = themes.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if t.grid:
            paint_backdrop(p, t, float(self.width()), float(self.height()))
        s, dx, dy = self._scale()
        p.save()
        p.translate(dx, dy)
        p.scale(s, s)
        label_font, number_font = fonts(t, QFont(self.font()))
        DevicePainter(p, t, look_for(t, self.palette()), self.preview, label_font, number_font,
                      self._fitter).paint(self._selection, self._simulating)
        p.restore()
        if t.scanlines:
            paint_scanlines(p, t, float(self.width()), float(self.height()))
        p.end()
