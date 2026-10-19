"""Modus „Simulieren“: Klicks und Mausrad am Geraetebild wirken wie das echte Geraet.

Eingeschaltet faengt ``Simulator`` die Maus am ``DeviceView`` ab (keine Auswahl, kein
Ziehen) und schickt Geraete-Ereignisse (wie ``api.protocol.event_to_dict``) an ``send`` –
im Editor-Prozess ``RemoteEngine.simulate`` (API ``simulate``), der Dienst behandelt sie wie
Ereignisse vom CT. Das Display (Kacheln und Leisten) bekommt Beruehrungen mit Koordinaten
(Wischen geht also auch), runde/eckige Tasten und Reglerknoepfe Tastenereignisse, das
Raddisplay Rad-Beruehrungen; das Mausrad dreht Regler (ueber Knopf oder Leiste) und das Rad.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, QPointF, Qt, Signal
from PySide6.QtWidgets import QToolButton

from ...core.i18n import N_, tr
from ...device.layout import KNOB_FIRST, ROUND_FIRST, SQUARE_CODES, ControlKind
from ..widgets.device_geometry import SCREEN, WHEEL
from ..widgets.device_view import DeviceView

TOOLTIP = N_("Simulieren: Klicks und Mausrad am Gerätebild lösen über den Dienst echte "
             "Ereignisse aus – wie am Gerät (auch ohne angeschlossenes Gerät)")
_SWALLOW = (QEvent.Type.MouseMove, QEvent.Type.ContextMenu, QEvent.Type.DragEnter,
            QEvent.Type.DragMove, QEvent.Type.Drop)


def _clamp(v: float, hi: int) -> int:
    return max(0, min(hi - 1, int(v)))


class Simulator(QObject):
    toggled = Signal(bool)

    def __init__(self, view: DeviceView, send: Callable[[dict], None],
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.view = view
        self._send = send
        self.active = False
        self._down: tuple | None = None  # ("touch",) | ("wheel",) | ("button", code)
        self.button = QToolButton()
        self.button.setObjectName("simulate")
        self.button.setText(tr("Simulieren"))
        self.button.setCheckable(True)
        self.button.setToolTip(tr(TOOLTIP))
        self.button.toggled.connect(self.set_active)

    def set_active(self, on: bool) -> None:
        if on == self.active:
            return
        if self._down is not None:  # nichts gedrueckt zuruecklassen
            self._release(None)
        self.active = on
        if self.button.isChecked() != on:
            self.button.setChecked(on)
        self.view.set_simulating(on)
        if on:
            self.view.installEventFilter(self)
        else:
            self.view.removeEventFilter(self)
        self.toggled.emit(on)

    # --- Maus -> Geraete-Ereignisse ----------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        if obj is not self.view or not self.active:
            return False
        t = event.type()
        if t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            if event.button() == Qt.MouseButton.LeftButton:
                self.press(event.position())
            return True
        if t == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                self._release(event.position())
            return True
        if t == QEvent.Type.Wheel:
            notches = round(event.angleDelta().y() / 120) or (
                1 if event.angleDelta().y() > 0 else -1 if event.angleDelta().y() < 0 else 0)
            self.rotate(event.position(), notches)
            return True
        return t in _SWALLOW

    def press(self, pos: QPointF) -> None:
        p = self.view.device_pos(pos)
        if SCREEN.contains(p):
            self._down = ("touch",)
            self._touch(p, True)
            return
        ref = self.view.control_at(pos)
        if ref is None:
            return
        if ref.kind == ControlKind.WHEEL:
            self._down = ("wheel",)
            self._wheel_touch(p, True)
            return
        code = {ControlKind.ROUND: lambda i: ROUND_FIRST + i,
                ControlKind.SQUARE: lambda i: SQUARE_CODES[i],
                ControlKind.KNOB: lambda i: KNOB_FIRST + i}.get(ref.kind)
        if code is not None:
            self._down = ("button", code(ref.index))
            self._send({"type": "button", "code": code(ref.index), "pressed": True})

    def release(self, pos: QPointF) -> None:
        self._release(pos)

    def _release(self, pos: QPointF | None) -> None:
        down, self._down = self._down, None
        if down is None:
            return
        p = self.view.device_pos(pos) if pos is not None else None
        if down[0] == "touch":
            self._touch(p if p is not None else SCREEN.center(), False)
        elif down[0] == "wheel":
            self._wheel_touch(p if p is not None else WHEEL.center(), False)
        else:
            self._send({"type": "button", "code": down[1], "pressed": False})

    def rotate(self, pos: QPointF, steps: int) -> None:
        """Mausrad: ``steps`` Rasten am Regler bzw. Rad unter ``pos`` (oben = rechts)."""
        ref = self.view.control_at(pos)
        if ref is None or not steps:
            return
        if ref.kind in (ControlKind.KNOB, ControlKind.STRIP):
            code = KNOB_FIRST + ref.index
        elif ref.kind == ControlKind.WHEEL:
            code = 0
        else:
            return
        delta = 1 if steps > 0 else -1
        for _ in range(abs(steps)):
            self._send({"type": "rotate", "code": code, "delta": delta})

    def _touch(self, p: QPointF, down: bool) -> None:
        self._send({"type": "touch", "finger": 0,
                    "x": _clamp(p.x() - SCREEN.x(), int(SCREEN.width())),
                    "y": _clamp(p.y() - SCREEN.y(), int(SCREEN.height())), "down": down})

    def _wheel_touch(self, p: QPointF, down: bool) -> None:
        self._send({"type": "wheel_touch", "finger": 0,
                    "x": _clamp(p.x() - WHEEL.x(), int(WHEEL.width())),
                    "y": _clamp(p.y() - WHEEL.y(), int(WHEEL.height())), "down": down})
